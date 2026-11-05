"""Optional lossless, sharded Zarr v3 export to local directory stores."""

from __future__ import annotations

import math
from pathlib import Path

from frameit.utils.atomic import atomic_directory_output


def check_zarr_dependencies() -> None:
    from importlib.metadata import PackageNotFoundError, version

    from packaging.version import Version

    try:
        supported = (Version(version("xarray")) >= Version("2026.9.0")
                     and Version("3.4.2") <= Version(version("zarr")) < Version("4"))
        if supported:
            import zarr  # noqa: F401

            return
    except (PackageNotFoundError, ImportError):
        pass
    raise ValueError(
        "output.backend: zarr requires xarray>=2026.9.0 and zarr>=3.4.2,<4; "
        "install FrameIt's optional extra: pip install 'frameit[zarr]'"
    )


def validate_zarr_sizes(chunk_size, shard_size):
    """Validate even dimensions absent from an individual product."""
    for name, sizes in (("zarr_chunk_size", chunk_size), ("zarr_shard_size", shard_size)):
        if not isinstance(sizes, dict):
            raise ValueError(f"output.{name} must be a dimension-to-size mapping")
        for dim, size in sizes.items():
            if not isinstance(dim, str) or not dim or type(size) is not int or size < 1:
                raise ValueError(f"output.{name}: dimensions need positive integer sizes")
    for dim in chunk_size.keys() & shard_size.keys():
        if shard_size[dim] % chunk_size[dim]:
            raise ValueError(f"Zarr shard size for {dim} must be a multiple of chunk size")


def write_dataset_zarr(
    ds, path, *, metadata, product_type, group=None, track_filename=None,
    overwrite=True, compress_level=1, compress_coords=False, chunk_size=None, shard_size=None,
) -> Path:
    """Write v3 with independent compressed chunks grouped into larger shards.

    Sizes count elements, not bytes. Each Dask write owns whole shards to avoid
    races between tasks. Coordinates use the same layout, optionally compressed.
    """
    check_zarr_dependencies()
    import zarr
    from zarr.codecs import GzipCodec

    from frameit.io.netcdf_export import _append_history, _prepare_dataset, _utc_now_iso

    chunk_size = {} if chunk_size is None else chunk_size
    shard_size = {} if shard_size is None else shard_size
    validate_zarr_sizes(chunk_size, shard_size)
    if type(compress_level) is not int or not 0 <= compress_level <= 9:
        raise ValueError("compress_level must be an integer in [0, 9]")
    chunks, shards = {}, {}
    block_dims = [dim for dim in ds.sizes if dim != "time"][-2:]
    for dim, size in ds.sizes.items():
        if size == 0:
            raise ValueError(f"Cannot export Zarr with empty dimension {dim!r}")
        default = min(size, 128) if dim in block_dims else 1
        chunk = chunk_size.get(dim, default)
        if dim in shard_size and dim not in chunk_size:
            chunk = math.gcd(chunk, shard_size[dim])
        chunks[dim] = chunk
        count = 8 if dim == "time" else (4 if dim in block_dims else 1)
        shards[dim] = shard_size.get(dim, chunk * count)

    ds_out = _prepare_dataset(ds, metadata, product_type, group, track_filename)
    ds_out.encoding = {}
    encoding = {}
    for name, var in ds_out.variables.items():
        # Retain CF missing/time/coordinate declarations, not source packing or storage layout.
        var.encoding = {key: value for key, value in var.encoding.items()
                        if key in {"_FillValue", "units", "calendar", "coordinates", "grid_mapping"}}
        compressed = compress_level > 0 and (name in ds_out.data_vars or compress_coords)
        enc = {"compressors": [GzipCodec(level=compress_level)] if compressed else []}
        if var.ndim:
            enc.update(chunks=tuple(chunks[d] for d in var.dims),
                       shards=tuple(shards[d] for d in var.dims))
        encoding[name] = enc
    ds_out = _append_history(ds_out, f"{_utc_now_iso()}: written by frameit io.zarr_export")
    # Never disable safe_chunks: align processing tasks to the outer storage unit.
    ds_out = ds_out.chunk(shards)
    path = Path(path)
    with atomic_directory_output(path, overwrite=overwrite) as temporary:
        # Dask/export workers already own the CPU budget; do not add a codec pool per worker.
        with zarr.config.set({"async.concurrency": 1, "threading.max_workers": 1}):
            ds_out.to_zarr(temporary, mode="w", zarr_format=3, consolidated=False,
                           encoding=encoding, safe_chunks=True)
    return path
