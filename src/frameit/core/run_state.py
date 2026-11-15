"""Exclusive run-directory ownership and an authoritative final status record."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from frameit.utils.atomic import write_yaml_atomic


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def checkpoint_run(root, status, provenance=None):
    """Persist last-known facts, without a cross-record transaction or heartbeat."""
    root = Path(root)
    status["updated_at"] = utc_now()
    try:
        if provenance is not None:
            for key in ("state", "request_record", "planned_products", "products", "pending",
                        "updated_at", "error", "tracking_complete", "tracking_termination_reason"):
                if key in status:
                    provenance[key] = status[key]
            write_yaml_atomic(root / "run-provenance.yaml", provenance)
    except BaseException as exc:
        if status["state"] in {"completed", "incomplete"}:
            status.update(
                state=("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit))
                       else "failed"),
                pending=["cleanup"],
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        raise
    finally:
        write_yaml_atomic(root / "run-status.yaml", status)


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
        raise ValueError(f"Missing or unsafe required record: {path}. "
                         "Select a run directory containing run-status.yaml; do not recreate "
                         "records or remove a lock to infer completion.")
    try:
        status = read_yaml(path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read required record {path}: {exc}") from exc
    if not (
        type(status.get("schema_version")) is int and status["schema_version"] == 1
        and status.get("state") in {"running", "completed", "incomplete", "failed", "interrupted"}
        and isinstance(status.get("started_at"), str) and isinstance(status.get("products"), list)
        and all(isinstance(item, dict) and isinstance(item.get("path"), str)
                for item in status["products"])
    ):
        raise ValueError(f"Unrecognized required record: {path}. "
                         "Use the original version-1 run-status.yaml, "
                         "not an effective configuration.")
    notes = []
    provenance = None
    optional = root / "run-provenance.yaml"
    if optional.is_file() and not optional.is_symlink():
        try:
            candidate = read_yaml(optional)
            shared = ("updated_at", "state", "products", "pending")
            if status.get("updated_at") and all(
                key in status and candidate.get(key) == status[key] for key in shared
            ):
                provenance = candidate
            else:
                notes.append("Provenance checkpoint does not match authoritative status; "
                             "its supplemental facts are unavailable.")
        except (OSError, ValueError) as exc:
            notes.append(f"Optional provenance record unavailable: {exc}")
    else:
        notes.append("Optional provenance record unavailable.")
    # Checkpoint files are not a cross-record transaction; refuse a torn read.
    if read_yaml(path) != status:
        raise ValueError(f"Required record {path} changed during reading. Retry status; "
                         "no current-attempt inventory was inferred.")
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


@contextmanager
def owned_run(root, *, overwrite, initial, request=None, provenance=None):
    """Claim a directory before logging/processing; never steal an existing lock."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".frameit-run.lock"
    try:
        stream = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise FileExistsError(
            f"Run directory is locked: {root}. Use a fresh attempt directory. "
            "Remove a stale .frameit-run.lock only after confirming its owner has stopped."
        ) from exc
    try:
        with stream:
            stream.write(f"pid: {os.getpid()}\n")
        existing = [root / name for name in (
            "run-request.yaml", "resolved-config.yaml", "run-provenance.yaml", "run-status.yaml",
        ) if (root / name).exists() or (root / name).is_symlink()]
        if not overwrite:
            products = root / "products"
            if products.exists() and (not products.is_dir() or any(products.iterdir())):
                existing.append(products)
            if existing:
                raise FileExistsError(
                    f"Existing run artifacts with overwrite=False: {existing[0]}; "
                    "use a fresh attempt directory"
                )
        else:
            for path in existing:
                if not _recognized_record(path):
                    raise ValueError(f"Refusing to replace an unrecognized run record: {path}")
        status = {
            "schema_version": 1, "state": "running", "started_at": utc_now(),
            "finished_at": None, "products": [], **initial,
        }
        if request is not None:
            status["request_record"] = "run-request.yaml"
        try:
            if request is not None:
                write_yaml_atomic(root / "run-request.yaml", request, overwrite=overwrite)
            checkpoint_run(root, status, provenance)
            yield status
        except BaseException as exc:
            status.update(
                state=("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit))
                       else "failed"),
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise
        finally:
            status["finished_at"] = utc_now()
            checkpoint_run(root, status, provenance)
    finally:
        lock.unlink()
