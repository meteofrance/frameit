# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from frameit._version import __version__ as frameit_version

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return (
        dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


class _JSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        if isinstance(obj, (dt.datetime, dt.date)):
            return obj.isoformat()
        return super().default(obj)


def _sanitize_filename_token(token: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return "".join(ch if ch in allowed else "_" for ch in token)


def _jsonify_if_needed(value: Any) -> str | None:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, cls=_JSONEncoder, ensure_ascii=False, sort_keys=True)
    return None


def _sanitize_attrs(attrs: Mapping[str, Any]) -> dict[str, Any]:
    """
    NetCDF attrs must be scalar strings/numbers (or arrays of those).
    Convert dict/list-like attrs into JSON strings with *_json suffix.
    """
    out: dict[str, Any] = {}
    for k, v in (attrs or {}).items():
        if v is None:
            continue

        js = _jsonify_if_needed(v)
        if js is not None:
            out[f"{k}_json"] = js
            continue

        if isinstance(v, Path):
            out[k] = str(v)

        # IMPORTANT: netCDF4 does not allow boolean attributes
        elif isinstance(v, (bool, np.bool_)):
            out[k] = np.int8(v)

        elif isinstance(v, (np.integer,)):
            out[k] = int(v)
        elif isinstance(v, (np.floating,)):
            out[k] = float(v)
        elif isinstance(v, (dt.datetime, dt.date)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _append_history(ds: xr.Dataset, entry: str) -> xr.Dataset:
    hist = ds.attrs.get("history", "")
    ds.attrs["history"] = f"{hist}\n{entry}" if hist else entry
    return ds


def _make_encoding(
    ds: xr.Dataset,
    compress_level: int = 1,
    compress_coords: bool = False,
) -> dict[str, dict[str, Any]]:
    enc: dict[str, dict[str, Any]] = {}
    for v in ds.data_vars:
        enc[v] = {"zlib": True, "complevel": int(compress_level), "shuffle": True}
    if compress_coords:
        for c in ds.coords:
            if ds[c].ndim >= 1:
                enc[c] = {"zlib": True, "complevel": int(compress_level), "shuffle": True}
    return enc


@dataclass
class ExportMetadata:
    simulation_id: str
    title: str
    summary: str
    institution: str
    source: str
    conventions: str = "CF-1.8"
    frameit_version: str = frameit_version

    def base_attrs(self) -> dict[str, Any]:
        """
        Build the base CF global attribute dictionary.

        Returns
        -------
        dict[str, Any]
            Global attribute mapping ready to merge into ``ds.attrs``.
        """
        attrs = {
            "Conventions": self.conventions,
            "title": self.title,
            "summary": self.summary,
            "institution": self.institution,
            "source": self.source,
            "simulation_id": self.simulation_id,
            "frameit_version": self.frameit_version,
        }
        return attrs


def build_metadata_from_conf(
    conf: Any,
    *,
    frameit_version: str = frameit_version,
    institution: str,
) -> ExportMetadata:
    """
    Build an :class:`ExportMetadata` instance from a loaded configuration.

    Parameters
    ----------
    conf : object
        Configuration object (typically a :class:`SimulationConfig`).
        Accessed with ``getattr``; missing attributes fall back to "unknown".
    frameit_version : str, optional
        FrameIt version string to embed in metadata.  Defaults to the
        installed package version.
    institution : str
        Institution string to embed in the NetCDF global attributes.

    Returns
    -------
    ExportMetadata
        Populated metadata object ready to pass to :func:`write_dataset_netcdf`.
    """
    simu = str(getattr(conf, "simulation_name", "UNKNOWN_SIMU"))
    comment = str(getattr(conf, "comment", "")).strip()

    atm = str(getattr(conf, "atm_model", "unknown"))
    oce = str(getattr(conf, "ocean_model", "unknown"))
    wav = str(getattr(conf, "wave_model", "unknown"))
    ftype = str(getattr(conf, "file_type", "unknown"))
    trk = str(getattr(conf, "tracking_method", "unknown"))

    source = (
        f"file_type={ftype}; tracking_method={trk};"
        f" atm_model={atm}; ocean_model={oce}; wave_model={wav}"
    )

    title = f"FrameIt outputs for {simu}"
    summary = (
        comment
        if comment
        else "Cyclone-centric extraction and derived products generated by FrameIt."
    )

    meta = ExportMetadata(
        simulation_id=simu,
        title=title,
        summary=summary,
        institution=institution,
        source=source,
        frameit_version=frameit_version,
    )

    logger.debug(
        "Built metadata from conf: simulation_id=%s, institution=%s,"
        " conventions=%s, frameit_version=%s.",
        meta.simulation_id,
        meta.institution,
        meta.conventions,
        meta.frameit_version,
    )
    logger.debug("Metadata source string: %s", meta.source)
    return meta


def write_dataset_netcdf(
    ds: xr.Dataset,
    path: str | Path,
    *,
    metadata: ExportMetadata,
    product_type: str,
    group: str | None = None,
    track_filename: str | None = None,
    engine: str = "netcdf4",
    fmt: str = "NETCDF4",
    overwrite: bool = True,
    compress_level: int = 1,
    compress_coords: bool = False,
    unlimited_time: bool = True,
) -> Path:
    """
    Write a single xarray Dataset to a NetCDF file with CF-compliant metadata.

    Global attributes are taken from ``metadata.base_attrs()`` merged with
    ``product_type`` (and optionally ``group`` and ``track_filename``).
    All variable and coordinate attributes are sanitized to be NetCDF-compatible
    before writing.

    Parameters
    ----------
    ds : xr.Dataset
        Dataset to export.
    path : str or Path
        Destination file path.  Parent directory is created if absent.
    metadata : ExportMetadata
        Global CF-compliant attributes (title, institution, etc.).
    product_type : str
        Product category stored as a global attribute (e.g. "track", "polar").
    group : str or None, optional
        Vertical group name stored as a global attribute. Default None.
    track_filename : str or None, optional
        Name of the associated track file stored as a global attribute.
        Default None.
    engine : str, optional
        NetCDF writing engine passed to ``xr.Dataset.to_netcdf``. Default "netcdf4".
    fmt : str, optional
        NetCDF format string (e.g. "NETCDF4"). Default "NETCDF4".
    overwrite : bool, optional
        If False, raise :exc:`FileExistsError` when the destination exists.
        Default True.
    compress_level : int, optional
        zlib compression level (0–9). Default 1.
    compress_coords : bool, optional
        Apply compression to coordinate variables as well. Default False.
    unlimited_time : bool, optional
        Declare the "time" dimension unlimited. Default True.

    Returns
    -------
    Path
        Path to the written NetCDF file.

    Raises
    ------
    FileExistsError
        If ``path`` already exists and ``overwrite=False``.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not overwrite:
        logger.error("Refusing to overwrite existing file (overwrite=False): %s", str(path))
        raise FileExistsError(f"File exists and overwrite=False: {path}")

    logger.info(
        "Writing NetCDF: %s (product_type=%s, group=%s, engine=%s, fmt=%s,"
        " compress_level=%s, compress_coords=%s, unlimited_time=%s).",
        str(path),
        str(product_type),
        str(group) if group is not None else None,
        engine,
        fmt,
        int(compress_level),
        bool(compress_coords),
        bool(unlimited_time),
    )

    ds_out = ds.copy()
    # Sanitize global attrs
    ds_out.attrs = _sanitize_attrs(ds_out.attrs)
    # Sanitize attrs on all variables and coords (fixes units=None, etc.)
    for name in list(ds_out.data_vars) + list(ds_out.coords):
        ds_out[name].attrs = _sanitize_attrs(ds_out[name].attrs)

    ds_out.attrs.update(metadata.base_attrs())
    ds_out.attrs["product_type"] = str(product_type)
    if group is not None:
        ds_out.attrs["group"] = str(group)
    if track_filename is not None:
        ds_out.attrs["track_filename"] = str(track_filename)

    ds_out = _append_history(ds_out, f"{_utc_now_iso()}: written by frameit io.netcdf_export")

    encoding = _make_encoding(
        ds_out, compress_level=compress_level, compress_coords=compress_coords
    )
    unlimited_dims = ["time"] if (unlimited_time and ("time" in ds_out.dims)) else None

    logger.debug("NetCDF dims: %s", dict(ds_out.sizes))
    logger.debug(
        "NetCDF vars: n_data_vars=%s, n_coords=%s.", len(ds_out.data_vars), len(ds_out.coords)
    )
    if unlimited_dims is not None:
        logger.debug("Unlimited dims: %s", unlimited_dims)

    ds_out.to_netcdf(
        path,
        mode="w",
        engine=engine,
        format=fmt,
        encoding=encoding,
        unlimited_dims=unlimited_dims,
    )

    logger.info("NetCDF written: %s", str(path))
    return path


def _write_single_group(
    args: tuple[str, xr.Dataset, Path, str, ExportMetadata, str, str, str, bool, int, bool, bool],
) -> Path:
    """
    Worker function for ProcessPoolExecutor — must be a top-level callable.
    Unpacks all arguments and calls write_dataset_netcdf.
    """
    (
        group,
        ds,
        out_path,
        grid,
        metadata,
        track_filename,
        engine,
        fmt,
        overwrite,
        compress_level,
        compress_coords,
        unlimited_time,
    ) = args

    return write_dataset_netcdf(
        ds,
        out_path,
        metadata=metadata,
        product_type=grid,
        group=str(group),
        track_filename=track_filename,
        engine=engine,
        fmt=fmt,
        overwrite=overwrite,
        compress_level=compress_level,
        compress_coords=compress_coords,
        unlimited_time=unlimited_time,
    )


def write_group_dict(
    ds_dict: Mapping[str, xr.Dataset],
    out_dir: str | Path,
    *,
    simu_name: str,
    grid: str,  # "polar" or "cart"
    metadata: ExportMetadata,
    track_filename: str,
    engine: str = "netcdf4",
    fmt: str = "NETCDF4",
    overwrite: bool = True,
    compress_level: int = 1,
    compress_coords: bool = False,
    unlimited_time: bool = True,
    max_workers: int | None = None,
    synchronous: bool = False,
) -> list[Path]:
    """
    Write a dictionary of Datasets to individual NetCDF files, optionally in parallel.

    Each group produces one file named ``{simu_name}.{grid}.{group}.nc``
    inside ``out_dir``.

    Parameters
    ----------
    ds_dict : Mapping[str, xr.Dataset]
        Group datasets to export, keyed by group name.
    out_dir : str or Path
        Output directory.  Created if absent.
    simu_name : str
        Simulation identifier used as the file name prefix.
    grid : str
        Grid type label used in the file name (e.g. "polar" or "cart").
    metadata : ExportMetadata
        Global CF-compliant attributes forwarded to each file.
    track_filename : str
        Name of the associated track file stored as a global attribute.
    engine : str, optional
        NetCDF writing engine. Default "netcdf4".
    fmt : str, optional
        NetCDF format string. Default "NETCDF4".
    overwrite : bool, optional
        Overwrite existing files. Default True.
    compress_level : int, optional
        zlib compression level (0–9). Default 1.
    compress_coords : bool, optional
        Apply compression to coordinate variables. Default False.
    unlimited_time : bool, optional
        Declare the "time" dimension unlimited. Default True.
    max_workers : int or None, optional
        Maximum number of parallel worker processes.  ``None`` lets Python
        choose based on available CPU cores. Default None.

    Returns
    -------
    list[Path]
        Paths to the written NetCDF files (order reflects completion order).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Writing group dictionary: out_dir=%s, simu_name=%s, grid=%s, n_groups=%s, max_workers=%s.",
        str(out_dir),
        simu_name,
        grid,
        len(ds_dict),
        max_workers,
    )

    # Build the list of argument tuples for each worker
    tasks_args = []
    for group, ds in ds_dict.items():
        group_token = _sanitize_filename_token(str(group))
        fn = f"{simu_name}.{grid}.{group_token}.nc"
        out_path = out_dir / fn

        logger.debug(
            "Queuing group=%s -> %s (vars=%s, dims=%s).",
            str(group),
            str(out_path),
            len(ds.data_vars),
            dict(ds.sizes),
        )

        tasks_args.append(
            (
                group,
                ds.compute() if hasattr(ds, "dask") else ds,
                out_path,
                grid,
                metadata,
                track_filename,
                engine,
                fmt,
                overwrite,
                compress_level,
                compress_coords,
                unlimited_time,
            )
        )

    if synchronous:
        # A matrix case already runs in an isolated worker. Do not create a
        # nested process pool, even a one-worker pool, for group serialization.
        return [_write_single_group(args) for args in tasks_args]

    written: list[Path] = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_write_single_group, args): args[0]  # args[0] = group name
            for args in tasks_args
        }
        for future in as_completed(futures):
            group_name = futures[future]
            try:
                path = future.result()
                written.append(path)
            except Exception:
                logger.exception("Failed to write group=%s.", group_name)
                raise

    logger.info("Group dictionary written: n_files=%s.", len(written))
    return written


def export_outputs(
    runner: Any,
    *,
    frameit_version: str = frameit_version,
    institution: str,
    out_dir: Path | None = None,
    out_subdir: str = "",
    export_polar: bool = True,
    export_cart: bool = True,
    engine: str = "netcdf4",
    fmt: str = "NETCDF4",
    overwrite: bool = True,
    compress_level: int = 1,
    compress_coords: bool = False,
    unlimited_time: bool = True,
    max_workers: int | None = None,
    synchronous: bool = False,
) -> dict[str, Path | list[Path]]:
    """
    Export all FrameIt products (track, polar, Cartesian) from a completed run.

    The track file is always written.  Polar and Cartesian exports are
    conditional on the corresponding flag and on data being available.

    Parameters
    ----------
    runner : FrameitRunner
        A runner instance on which :meth:`~FrameitRunner.run` has already been
        called.
    frameit_version : str, optional
        Version string embedded in global NetCDF attributes.  Defaults to the
        installed package version.
    institution : str
        Institution string stored in global NetCDF attributes.
    out_dir : Path or None, optional
        Root output directory.  Falls back to ``runner.output_dir`` when None.
    out_subdir : str, optional
        Sub-directory appended to ``out_dir``.  Default "" (no sub-directory).
    export_polar : bool, optional
        Write polar-projection datasets when available. Default True.
    export_cart : bool, optional
        Write Cartesian (box) datasets when available. Default True.
    engine : str, optional
        NetCDF writing engine. Default "netcdf4".
    fmt : str, optional
        NetCDF format string. Default "NETCDF4".
    overwrite : bool, optional
        Overwrite existing output files. Default True.
    compress_level : int, optional
        zlib compression level (0–9). Default 1.
    compress_coords : bool, optional
        Apply compression to coordinate variables. Default False.
    unlimited_time : bool, optional
        Declare the "time" dimension unlimited. Default True.
    max_workers : int or None, optional
        Maximum parallel workers for group export. Default None.

    Returns
    -------
    dict[str, Path or list[Path]]
        Keys present depend on what was exported:

        - ``"track"``: Path to the track file.
        - ``"polar"``: list of Path for polar files (if exported).
        - ``"cart"``:  list of Path for Cartesian files (if exported).
    """
    conf = runner.conf
    simu_name = str(getattr(conf, "simulation_name", "UNKNOWN_SIMU"))

    base_out = Path(out_dir) if out_dir is not None else Path(runner.output_dir)
    out_path = base_out / out_subdir if out_subdir else base_out
    out_path.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Export outputs: simu_name=%s, out_path=%s, export_polar=%s, export_cart=%s,"
        " engine=%s, fmt=%s, overwrite=%s, compress_level=%s, max_workers=%s.",
        simu_name,
        str(out_path),
        bool(export_polar),
        bool(export_cart),
        engine,
        fmt,
        bool(overwrite),
        int(compress_level),
        max_workers,
    )

    meta = build_metadata_from_conf(conf, frameit_version=frameit_version, institution=institution)

    # Track
    track_file = out_path / f"{simu_name}.track.nc"
    logger.info("Exporting track to %s.", str(track_file))

    track_written = write_dataset_netcdf(
        runner.track,
        track_file,
        metadata=meta,
        product_type="track",
        engine=engine,
        fmt=fmt,
        overwrite=overwrite,
        compress_level=compress_level,
        compress_coords=compress_coords,
        unlimited_time=unlimited_time,
    )

    results: dict[str, Path | list[Path]] = {"track": track_written}

    # Polar
    if export_polar and getattr(runner, "dict_polar_user", None):
        logger.info("Exporting polar groups (n_groups=%s).", len(runner.dict_polar_user))
        results["polar"] = write_group_dict(
            runner.dict_polar_user,
            out_path,
            simu_name=simu_name,
            grid="polar",
            metadata=meta,
            track_filename=track_written.name,
            engine=engine,
            fmt=fmt,
            overwrite=overwrite,
            compress_level=compress_level,
            compress_coords=compress_coords,
            unlimited_time=unlimited_time,
            max_workers=max_workers,
            synchronous=synchronous,
        )
    else:
        logger.debug(
            "Polar export skipped (export_polar=%s, dict_polar_user present=%s).",
            bool(export_polar),
            bool(getattr(runner, "dict_polar_user", None)),
        )

    # Cartesian crop
    if export_cart and getattr(runner, "dict_crop_user", None):
        logger.info("Exporting cart groups (n_groups=%s).", len(runner.dict_crop_user))
        results["cart"] = write_group_dict(
            runner.dict_crop_user,
            out_path,
            simu_name=simu_name,
            grid="cart",
            metadata=meta,
            track_filename=track_written.name,
            engine=engine,
            fmt=fmt,
            overwrite=overwrite,
            compress_level=compress_level,
            compress_coords=compress_coords,
            unlimited_time=unlimited_time,
            max_workers=max_workers,
            synchronous=synchronous,
        )
    else:
        logger.debug(
            "Cart export skipped (export_cart=%s, dict_crop_user present=%s).",
            bool(export_cart),
            bool(getattr(runner, "dict_crop_user", None)),
        )

    logger.info("Export completed. Results keys: %s.", list(results.keys()))
    return results
