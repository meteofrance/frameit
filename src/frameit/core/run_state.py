"""Exclusive run-directory ownership and an authoritative final status record."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from frameit.core.reports import error_record, primary_error_code
from frameit.utils.atomic import write_yaml_atomic
from frameit.utils.diagnostics import format_message, tag_error


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_run_record(path, value, *, overwrite=True, **yaml_options):
    try:
        write_yaml_atomic(path, value, overwrite=overwrite, **yaml_options)
    except Exception as exc:
        raise tag_error(exc, "E1808")


@contextmanager
def finalize_after(failure, message):
    """Report a finalization failure without replacing an active run error."""
    try:
        yield
    except BaseException as exc:
        if isinstance(exc, Exception):
            tag_error(exc, "E1808")
        if failure is None:
            raise
        message = format_message(primary_error_code(exc), message)
        failure.add_note(f"{message}: {type(exc).__name__}: {exc}")
        logging.getLogger("frameit").exception("%s", message)


def checkpoint_run(root, status, provenance=None, *, stable_sources=None):
    """Persist last-known facts, without a cross-record transaction or heartbeat."""
    root = Path(root)
    status["updated_at"] = utc_now()
    failure = None
    try:
        if provenance is not None:
            for key in ("state", "request_record", "run_attempt_id", "run_context", "records",
                        "planned_products", "products", "pending",
                        "updated_at", "error", "tracking_complete", "tracking_termination_reason"):
                if key in status:
                    provenance[key] = status[key]
            write_run_record(root / "run-provenance.yaml", provenance,
                             **({} if stable_sources is None else {"stable": stable_sources}))
    except BaseException as exc:
        failure = exc
        if status["state"] in {"completed", "incomplete"}:
            status.update(
                state=("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit))
                       else "failed"),
                pending=["cleanup"],
                error=error_record(exc),
            )
        raise
    finally:
        with finalize_after(failure, "Writing run status also failed"):
            write_run_record(root / "run-status.yaml", status)


def _recognized_record(path):
    import yaml

    if path.is_symlink() or not path.is_file():
        return False
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return False
        if path.name == "resolved-config.yaml":
            from frameit.core.configuration import resolve_schema

            resolve_schema(value)
            return True
        if path.name == "run-status.yaml":
            return (type(value.get("schema_version")) is int and value["schema_version"] == 1
                    and value.get("state") in {
                        "running", "completed", "incomplete", "failed", "interrupted"}
                    and isinstance(value.get("started_at"), str)
                    and isinstance(value.get("products"), list))
        if path.name == "run-request.yaml":
            return (type(value.get("record_version")) is int and value["record_version"] == 1
                    and value.get("request_kind") in {"yaml", "mapping", "runtime"}
                    and isinstance(value.get("path_bases"), dict)
                    and isinstance(value.get("overrides"), dict)
                    and isinstance(value.get("requested_execution_options"), dict)
                    and isinstance(value.get("runtime"), dict))
        return (isinstance(value.get("runtime"), dict)
                and bool(value["runtime"].get("frameit_version"))
                and isinstance(value.get("execution_options"), dict)
                and isinstance(value.get("execution_resources"), dict)
                and isinstance(value.get("sources"), dict))
    except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError):
        return False


def read_run_status(root):
    """Read fixed portable checkpoints only; never inspect archives or product payloads."""
    from frameit.core.configuration import read_yaml

    root = Path(root)
    path = root / "run-status.yaml"
    if path.is_symlink() or not path.is_file():
        raise tag_error(ValueError(
            f"Missing or unsafe required record: {path}. "
            "Select a run directory containing run-status.yaml; do not recreate "
            "records or remove a lock to infer completion."
        ), "E1807")
    try:
        status = read_yaml(path, error_code="E1807")
    except (OSError, ValueError) as exc:
        raise tag_error(ValueError(f"Cannot read required record {path}: {exc}"), "E1807") from exc
    if not (
        type(status.get("schema_version")) is int and status["schema_version"] == 1
        and status.get("state") in {"running", "completed", "incomplete", "failed", "interrupted"}
        and isinstance(status.get("started_at"), str) and isinstance(status.get("products"), list)
        and all(isinstance(item, dict) and isinstance(item.get("path"), str)
                for item in status["products"])
    ):
        raise tag_error(ValueError(
            f"Unrecognized required record: {path}. Use the original version-1 run-status.yaml, "
            "not an effective configuration."
        ), "E1807")
    notes = []
    provenance = None
    optional = root / "run-provenance.yaml"
    if optional.is_file() and not optional.is_symlink():
        try:
            candidate = read_yaml(optional)
            shared = ("updated_at", "state", "products", "pending",
                      *[key for key in ("run_attempt_id", "run_context", "records")
                        if key in status or key in candidate])
            if status.get("updated_at") and all(
                key in status and candidate.get(key) == status[key] for key in shared
            ):
                provenance = candidate
            else:
                notes.append(format_message(
                    "W1801", "Provenance checkpoint does not match authoritative status; "
                    "its supplemental facts are unavailable."))
        except (OSError, ValueError) as exc:
            notes.append(format_message("W1801", f"Optional provenance record unavailable: {exc}"))
    else:
        notes.append(format_message("W1801", "Optional provenance record unavailable."))
    # Checkpoint files are not a cross-record transaction; refuse a torn read.
    current = read_yaml(path, error_code="E1809")
    if current != status:
        raise tag_error(ValueError(
            f"Required record {path} changed during reading. Retry status; "
            "no current-attempt inventory was inferred."
        ), "E1809")
    return {
        **status,
        "planned_products": status.get("planned_products"),
        "pending": status.get("pending"),
        "warnings": status.get("warnings", (provenance or {}).get("warnings")),
        "record_notes": notes,
        "recorded_processing": {key: provenance.get(key) for key in (
            "binding", "sources", "time_alignment", "unit_provenance")}
        if provenance is not None else None,
    }


def _previous_trajectory(root, *, overwrite):
    from frameit.core.configuration import read_yaml
    from frameit.core.run_context import file_sha256
    from frameit.utils.output_paths import TRAJECTORY_RECORD, OutputPaths

    path = OutputPaths(root).trajectory_record()
    if not path.exists():
        return None
    status = root / "run-status.yaml"
    if overwrite and path.is_file() and _recognized_record(status):
        former = read_yaml(status, error_code="E1807")
        retired = former.get("retained_trajectory_record")
        if retired is None:
            retired = next((entry for entry in former.get("records", [])
                            if isinstance(entry, dict) and entry.get("role") == "trajectory"
                            and entry.get("run_attempt_id") == former.get("run_attempt_id")), None)
        if (isinstance(retired, dict) and retired.get("role") == "trajectory"
                and retired.get("path") == TRAJECTORY_RECORD and retired.get("run_attempt_id")
                and retired.get("sha256") == file_sha256(path)):
            return retired
    raise tag_error(FileExistsError(f"Refusing to replace an unrecognized trajectory record: {path}"),
                    "E1802")


@contextmanager
def directory_lock(root, *, lock_name=".frameit-run.lock"):
    """Lease an existing directory without writing any run records."""
    root = Path(root)
    lock = root / lock_name
    try:
        stream = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise tag_error(FileExistsError(
            f"Run directory is locked: {root}. Use a fresh attempt directory. "
            f"Remove a stale {lock_name} only after confirming its owner has stopped."
        ), "E1801") from exc
    except OSError as exc:
        raise tag_error(exc, "E1803")
    failure = None
    try:
        with stream:
            stream.write(f"pid: {os.getpid()}\n")
        yield
    except BaseException as exc:
        failure = exc
        raise
    finally:
        with finalize_after(failure, "Releasing the run lock also failed"):
            lock.unlink()


@contextmanager
def owned_run(root, *, overwrite, initial, request=None, provenance=None):
    """Claim a directory before logging/processing; never steal an existing lock."""
    root = Path(root)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise tag_error(exc, "E1803")
    with directory_lock(root):
        existing = [root / name for name in (
            "run-request.yaml", "resolved-config.yaml", "run-provenance.yaml", "run-status.yaml",
        ) if (root / name).exists() or (root / name).is_symlink()]
        if not overwrite:
            products = root / "products"
            if products.exists() and (not products.is_dir() or any(products.iterdir())):
                existing.append(products)
            if existing:
                raise tag_error(FileExistsError(
                    f"Existing run artifacts with overwrite=False: {existing[0]}; "
                    "use a fresh attempt directory"
                ), "E1802")
        else:
            for path in existing:
                if not _recognized_record(path):
                    raise tag_error(ValueError(
                        f"Refusing to replace an unrecognized run record: {path}"
                    ), "E1802")
        status = {
            "schema_version": 1, "state": "running", "started_at": utc_now(),
            "finished_at": None, "products": [], **initial,
        }
        if "run_attempt_id" in initial:
            retained = _previous_trajectory(root, overwrite=overwrite)
            if retained:
                # Do not misidentify an older record as this attempt's trajectory.
                status["retained_trajectory_record"] = retained
        if request is not None:
            status["request_record"] = "run-request.yaml"
        failure = None
        try:
            if request is not None:
                write_run_record(root / "run-request.yaml", request, overwrite=overwrite)
            checkpoint_run(root, status, provenance)
            yield status
        except BaseException as exc:
            failure = exc
            with finalize_after(exc, "Preparing the run failure record also failed"):
                status.update(
                    state=("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit))
                           else "failed"),
                    error=error_record(exc),
                )
            raise
        finally:
            with finalize_after(failure, "Finalizing run records also failed"):
                status["finished_at"] = utc_now()
                checkpoint_run(root, status, provenance)
