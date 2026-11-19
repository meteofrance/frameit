"""Optional lossless, sharded Zarr v3 export to local directory stores."""

from __future__ import annotations

import math
from pathlib import Path

from frameit.utils.atomic import atomic_directory_output
from frameit.utils.diagnostics import tag_error


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
    raise tag_error(ValueError(
        "Zarr output requires xarray>=2026.9.0 and zarr>=3.4.2,<4; "
        "install FrameIt's optional extra: pip install 'frameit[zarr]'"
    ), "E1005")


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
            raise tag_error(ValueError(
                f"Zarr shard size for {dim} must be a multiple of chunk size"
            ), "E1805")


def _spatial_block_dims(ds):
    other = {"time", "level", "lev", "member", "ensemble", "number", "bounds", "bnds", "nv"}
    for coord in ds.coords.values():
        if coord.ndim == 1 and (
                coord.attrs.get("axis") in {"T", "Z"}
                or coord.attrs.get("positive") in {"up", "down"}
                or coord.attrs.get("standard_name") in {"realization", "time", "forecast_period"}):
            other.update(coord.dims)
        if isinstance(bounds := coord.attrs.get("bounds"), str) and bounds in ds.variables:
            other.update(set(ds[bounds].dims) - set(coord.dims))

    blocks = set()
    for polar in ({"radius", "azimuth"}, {"radius_cell", "azimuth_cell"}):
        if polar <= ds.sizes.keys():
            blocks.update(polar)
    layout = ds.attrs.get("frameit_output_coordinates")
    if isinstance(layout, dict):
        for grid in layout.values():
            blocks.update(grid["dimensions"][axis] for axis in grid.get("original_coordinates", {}))
            geographic = {axis for name in grid.get("geography", {}).values()
                          if name in ds for axis in ds[name].dims} - other
            if len(geographic) == 2:
                blocks.update(geographic)
            for name in ("lat_rho", "lon_rho"):
                view = grid.get("support_views", {}).get(name)
                if view and view["stored_name"] in ds:
                    blocks.update(view["dimensions"][axis] for axis in ("eta_rho", "xi_rho"))
        return blocks - other
    # shortcut: unannotated arrays use their trailing spatial pair; supply layout metadata for transposed grids.
    for value in ds.data_vars.values():
        axes = [dim for dim in value.dims if dim not in other]
        if len(axes) >= 2:
            blocks.update(axes[-2:])
    return blocks


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
    block_dims = _spatial_block_dims(ds)
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
                        if key in {"_FillValue", "units", "calendar", "coordinates", "grid_mapping"}
                        or key == "dtype" and var.dtype.kind in "Mm"}
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
