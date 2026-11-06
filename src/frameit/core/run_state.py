"""Exclusive run-directory ownership and an authoritative final status record."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from frameit.utils.atomic import write_yaml_atomic


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def owned_run(root, *, overwrite, initial):
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
        if not overwrite:
            existing = [root / name for name in (
                "resolved-config.yaml", "run-provenance.yaml", "run-status.yaml",
            ) if (root / name).exists()]
            products = root / "products"
            if products.exists() and any(products.iterdir()):
                existing.append(products)
            if existing:
                raise FileExistsError(
                    f"Existing run artifacts with overwrite=False: {existing[0]}; "
                    "use a fresh attempt directory"
                )
        status = {
            "schema_version": 1, "state": "running", "started_at": utc_now(),
            "finished_at": None, "products": [], **initial,
        }
        path = root / "run-status.yaml"
        write_yaml_atomic(path, status)
        try:
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
            write_yaml_atomic(path, status)
    finally:
        lock.unlink()
