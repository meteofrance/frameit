"""Scoped serial reads and access evidence for local FrameIt v3 stores."""

import json
from contextlib import contextmanager
from math import prod
from pathlib import Path

from frameit.diagnostics.contracts import diagnostic_error


def _error(message):
    return diagnostic_error(
        "E2003",
        "diagnostics.best_track.input",
        message,
        repair="Use an unchanged FrameIt sharded Zarr v3 or NetCDF product.",
    )


def check_layout(root):
    import numpy as np

    # The FrameIt writer uses bytes, optional Gzip, and a CRC32C shard index.
    def verify(codecs):
        for codec in codecs:
            if codec["name"] == "sharding_indexed":
                verify(codec["configuration"]["codecs"])
                verify(codec["configuration"]["index_codecs"])
            elif codec["name"] not in {"bytes", "gzip", "crc32c"}:
                raise _error(f"Unsupported diagnostic Zarr codec: {codec['name']}")

    units = {}
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        doc = path / "zarr.json"
        if path.is_symlink() or doc.is_symlink() or not doc.is_file():
            raise _error(f"Unsafe Zarr array metadata: {path.name}")
        details = json.loads(doc.read_text(encoding="utf-8"))
        if (
            details["zarr_format"] != 3
            or details["node_type"] != "array"
            or details["chunk_grid"]["name"] != "regular"
            or details.get("storage_transformers")
        ):
            raise _error(f"Unsupported Zarr layout for {path.name}")
        codecs = details["codecs"]
        verify(codecs)
        shape = details["chunk_grid"]["configuration"]["chunk_shape"]
        # Count the full outer storage unit conservatively, even with range reads.
        units[path.name] = 3 * prod(shape) * np.dtype(details["data_type"]).itemsize
    return units


def object_stamp(root, key):
    relative = Path(key)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise _error(f"Unsafe accessed Zarr object: {key}")
    path = root / relative
    if any(
        candidate.is_symlink()
        for candidate in (path, *path.parents)
        if candidate.is_relative_to(root)
    ):
        raise _error(f"Unsafe symlink at accessed Zarr object: {key}")
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return info.st_size, info.st_mtime_ns


@contextmanager
def open_store(path, *, evidence, max_objects):
    import zarr
    from zarr.storage import LocalStore

    class TrackedStore(LocalStore):
        def with_read_only(self, read_only=True):
            if not read_only:
                raise _error("Diagnostic Zarr store is read-only")
            return self

        async def get(self, key, prototype=None, byte_range=None):
            if key not in evidence and len(evidence) >= max_objects:
                raise _error("Accessed Zarr object evidence exceeds the working-buffer allowance")
            observed = object_stamp(path, key)
            if evidence.setdefault(key, observed) != observed:
                raise _error(f"An accessed Zarr object changed during reading: {key}")
            return await super().get(key, prototype, byte_range)

        async def get_partial_values(self, prototype, key_ranges):
            # LocalStore's bulk helper otherwise dispatches overlapping range reads.
            return [await self.get(key, prototype, extent) for key, extent in key_ranges]

    with zarr.config.set({"async.concurrency": 1, "threading.max_workers": 1}):
        store = TrackedStore(path, read_only=True)
        try:
            yield store
        finally:
            store.close()


def verify_accesses(root, evidence):
    for key, stamp in evidence.items():
        if object_stamp(root, key) != stamp:
            raise _error(f"An accessed Zarr object changed after reading: {key}")
