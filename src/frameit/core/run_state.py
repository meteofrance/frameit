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
