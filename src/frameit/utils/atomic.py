"""Same-filesystem publication of complete files, including no-clobber writes."""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


@contextmanager
def atomic_output(path, *, overwrite=True):
    """Yield a private temporary path; publish only after the writer closes it.

    No-clobber publication uses a POSIX hard link, so an intervening writer cannot
    be overwritten. A killed process may leave a hidden ``*.partial`` file, but
    never publishes that file under the final name. This is not an fsync/durable
    storage guarantee or a transaction across multiple products.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and path.exists():
        raise FileExistsError(f"File exists and overwrite=False: {path}")
    # Honor the job's umask (mkstemp's fixed 0600 would break group sharing).
    # Overwriting an existing product retains its permissions, as truncation did.
    previous_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    temporary = path.parent / f".frameit-{uuid4().hex}.partial"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    os.close(descriptor)
    try:
        if overwrite and previous_mode is not None:
            temporary.chmod(previous_mode)
        yield temporary
        if overwrite:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_yaml_atomic(path, value, *, overwrite=True):
    import yaml

    with atomic_output(path, overwrite=overwrite) as temporary:
        temporary.write_text(
            yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
