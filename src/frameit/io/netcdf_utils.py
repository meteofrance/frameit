# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import xarray as xr

from frameit.check.check_functions import drop_time_dupes
from frameit.io.loader import managed_loading, resolve_input_files
from frameit.processing.requests import build_group_ds, normalize_requests

logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# Minimal, reusable NetCDF opener
# -------------------------------------------------------------


@managed_loading
def concat_nc2ds(
    files_list: Iterable[str | Path],
    variables: Iterable[str],
    concat_dimension: str | None = None,
    parallel: bool = False,
    strict: bool = False,
    resources=None,
) -> xr.Dataset:
    """
    Open and concatenate a list of NetCDF files into a single Dataset.

    Uses ``xr.open_dataset`` for each original input, then combines the
    lazy arrays. Loading is lazy (Dask): data is read only on
    explicit ``.compute()`` calls.

    Parameters
    ----------
    files_list : Iterable[str or Path]
        Ordered list of NetCDF file paths. With ``strict=True`` the order is
        preserved and missing entries fail; otherwise paths are sorted and
        non-existent entries are skipped for compatibility.
    variables : Iterable[str]
        Variable names to keep.  All other data variables are dropped before
        loading to reduce memory usage.
    concat_dimension : str or None, optional
        Dimension along which to concatenate (e.g. "time").  When None,
        ``xr.open_mfdataset`` uses ``combine="by_coords"``.
    parallel : bool, optional
        Retained for API compatibility. Original handles are opened serially;
        array computation remains lazy and can use Dask scheduling.
    strict : bool, optional
        Consume an explicit inventory without sorting or omitting missing
        paths. Default False preserves ordinary discovery behaviour.

    Returns
    -------
    xr.Dataset
        Lazily-loaded concatenated dataset containing the requested variables
        plus any coordinates present in the files.

    Raises
    ------
    FileNotFoundError
        If no existing files are found after filtering.
    """
    files = resolve_input_files(files_list, strict=strict)

    # List variables from the first file (used to build drop_variables)
    with xr.open_dataset(files[0], decode_cf=False, engine="h5netcdf") as t0:
        all_vars = list(t0.data_vars)
    keep_vars = list(dict.fromkeys([v for v in variables if v in all_vars]))
    drop_vars = [v for v in all_vars if v not in keep_vars]

    if len(files) == 1:
        if logger:
            logger.info("Single-file mode: xr.open_dataset")
        ds = resources.add(
            xr.open_dataset(
                files[0],
                engine="h5netcdf",
                drop_variables=drop_vars or None,
                chunks={},  # lazy Dask loading — avoids immediate memory allocation
            )
        )
    else:
        if logger:
            logger.info(
                "Multi-file mode: original-handle loading (combine=%s, concat_dim=%s)",
                "nested" if concat_dimension else "by_coords",
                concat_dimension,
            )
        # Keep each original handle alive, rather than relying on a derived
        # merged Dataset to inherit all backend close callbacks.
        opened = [
            resources.add(
                xr.open_dataset(
                    file, engine="h5netcdf", drop_variables=drop_vars or None, chunks={}
                )
            )
            for file in files
        ]
        if concat_dimension:
            ds = xr.concat(
                opened,
                dim=concat_dimension,
                data_vars="all",
                coords="different",
                compat="no_conflicts",
                join="outer",
            )
        else:
            ds = xr.combine_by_coords(opened)

    if logger:
        present = ", ".join(sorted(ds.data_vars))
        logger.info("Variables in dataset: %s", present)
    return ds


# -------------------------------------------------------------
# Main API: 2 requests (user + tracker)
# -------------------------------------------------------------


@managed_loading
def concat_nc2ds_by_vert_coord(
    files: Iterable[str | Path],
    user_requested_variables_yaml: dict[str, dict[str, Any]],
    tracker_requested_variables_by_method_yaml: dict[str, dict[str, Any]] | None,
    method: str | None = None,
    *,
    concat_dimension: str = "time",
    parallel: bool = False,
    strict: bool = False,
    keep_geovars: bool = True,
    geovar_candidates: tuple[str, ...] = ("latitude", "longitude"),
    float_tol: float | None = None,
    resources=None,
) -> tuple[dict[str, xr.Dataset], dict[str, dict[str, xr.Dataset]]]:
    """
    Open the NetCDF files once then apply two independent requests.
    Returns (by_group_user, by_group_tracker), where:
      - by_group_user: {group -> xr.Dataset}
      - by_group_tracker: {method -> {group -> xr.Dataset}}

    Supported groups: "level", "level_w", "surface".
    - Vertical selection by indices or values. `float_tol=None` enforces exact equality.
    - The variables actually read are the union of those requested by the user
      and all selected tracker methods, plus geographic variables if present.
    - `method=None` processes all methods present in `tracker_requested_variables_by_method_yaml`.
    - Loading is lazy (Dask): data is only read on explicit .compute() calls
      downstream, avoiding MemoryError on large datasets.
    """

    # Normalise the user request
    user_req = normalize_requests(user_requested_variables_yaml)

    # Select and normalise tracker methods
    tracker_yaml = tracker_requested_variables_by_method_yaml or {}
    if method is None:
        methods = list(tracker_yaml.keys())
    else:
        methods = [m for m in tracker_yaml.keys() if m == method]
        if not methods:
            logger.warning(
                "Tracker method '%s' not found. No tracker group will be produced.", method
            )
    tracker_req_by_method: dict[str, dict[str, Any]] = {
        m: normalize_requests(tracker_yaml.get(m, {})) for m in methods
    }

    # Minimal union of variables to read
    requested_vars_all: set[str] = set()
    for _, spec in user_req.items():
        requested_vars_all.update(spec.get("variables", []))
    for _m, blk in tracker_req_by_method.items():
        for _, spec in blk.items():
            requested_vars_all.update(spec.get("variables", []))

    # Prepare the file list
    files = resolve_input_files(files, strict=strict)

    # Automatically add geographic variables
    auto_geo = []
    if keep_geovars:
        with xr.open_dataset(files[0], decode_cf=False, engine="h5netcdf") as t0:
            present = set(t0.data_vars) | set(t0.coords)
        auto_geo = [name for name in geovar_candidates if name in present]
        if auto_geo:
            logger.info("Auto-adding geographic variables: %s", ", ".join(auto_geo))
        requested_vars_all.update(auto_geo)

    # Single lazy read (Dask via chunks={} in concat_nc2ds)
    ds = concat_nc2ds(
        files_list=files,
        variables=sorted(requested_vars_all),
        concat_dimension=concat_dimension,
        parallel=parallel,
        strict=strict,
        resources=resources,
    )

    # Promote geographic variables to coordinates if needed
    if auto_geo:
        keep_as_coords = [v for v in auto_geo if v in ds]
        if keep_as_coords:
            ds = ds.set_coords(keep_as_coords)

    # Build groups
    out_user: dict[str, xr.Dataset] = {}
    out_trk: dict[str, dict[str, xr.Dataset]] = {}

    for g in ("level", "level_w", "surface"):
        if g in user_req:
            ds_u = build_group_ds(ds, user_req[g], g, concat_dimension, float_tol)
            if ds_u is not None:
                out_user[g] = ds_u

    for m, blk in tracker_req_by_method.items():
        grp_map: dict[str, xr.Dataset] = {}

        # Special cases: fixed_box and prescribed_track
        if m in {"fixed_box", "prescribed_track"}:
            # Minimal Dataset: no data_vars, coordinates only (time, latitude, longitude, etc.)
            data_vars = list(ds.data_vars)
            if data_vars:
                ds_t = ds.drop_vars(data_vars)
            else:
                ds_t = ds

            # Store under an arbitrary group name, e.g. "surface"
            grp_map["surface"] = ds_t

        else:
            # General case: go through build_group_ds
            for g in ("level", "level_w", "surface"):
                if g in blk:
                    ds_t = build_group_ds(ds, blk[g], g, concat_dimension, float_tol)
                    if ds_t is not None:
                        grp_map[g] = ds_t

        if grp_map:
            out_trk[m] = grp_map

    # Final deduplication
    out_user = {g: drop_time_dupes(ds, keep="first") for g, ds in out_user.items()}
    out_trk = {
        m: {g: drop_time_dupes(ds, keep="first") for g, ds in grp.items()}
        for m, grp in out_trk.items()
    }

    return out_user, out_trk
