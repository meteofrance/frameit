# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
from pathlib import Path

import cfgrib
import numpy as np
import xarray as xr

from frameit.check.check_functions import drop_time_dupes

logger = logging.getLogger(__name__)
logging.getLogger("cfgrib").setLevel(logging.WARNING)


def _parse_and_normalize(yaml_req: dict | None, dims_seen: set[str]) -> dict[str, dict]:
    """
    Normalise the YAML into:
      group_name -> {
        "dimension": str | None,
        "variables": list[str],
        "all_levels": bool,
        "levels": list[float|int],
        "level_indices": list[int],
      }
    - 'dimension' is taken from the YAML if provided, otherwise inferred when
      the group name matches a known coordinate.
    - If no dimension is found, the group is treated as surface-like.
    """
    if not yaml_req:
        return {}
    out: dict[str, dict] = {}
    for group, spec in yaml_req.items():
        spec = spec or {}
        dim = spec.get("dimension", None)
        if dim is None and group in dims_seen:
            dim = group
        sel = str(spec.get("level_selection", "")).lower().strip()
        all_levels = sel == "all"
        if sel not in {"", "values", "indices", "all"}:
            sel = "values" if spec.get("level_values") else "indices"
        levels = list(spec.get("level_values", [])) if sel == "values" else []
        idxs = list(spec.get("level_indices", [])) if sel == "indices" else []
        out[group] = {
            "dimension": dim,
            "variables": list(spec.get("variables", [])),
            "all_levels": bool(all_levels),
            "levels": levels,
            "level_indices": idxs,
        }
    return out


def _match_levels(avail_vals, requested, tol: float) -> list[float]:
    if not requested:
        return []
    vals = np.asarray(avail_vals, dtype=float)
    out = []
    for lv in requested:
        lvf = float(lv)
        j = int(np.argmin(np.abs(vals - lvf)))
        if abs(float(vals[j]) - lvf) <= tol:
            out.append(float(vals[j]))
    seen = set()
    uniq = []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def _collect_parts_for_req(
    dsets: list[xr.Dataset],
    req_map: dict[str, dict],
    float_tol: float,
    tag: str,  # "user variables dict" | "tracker variables dict"
) -> dict[str, list[xr.Dataset]]:
    """
    Filter GRIB dataset blocks for a single request map.

    Parameters
    ----------
    dsets : list[xr.Dataset]
        All xarray Datasets opened from one GRIB file (one per message type).
    req_map : dict[str, dict]
        Normalized request map ``{group: spec}`` as returned by
        :func:`_parse_and_normalize`.
    float_tol : float
        Tolerance for numeric vertical level matching.
    tag : str
        Label used in log messages (e.g. "user variables dict" or
        "tracker variables dict:<method>").

    Returns
    -------
    dict[str, list[xr.Dataset]]
        ``{group: [filtered datasets]}`` — one list per group, with one
        entry per matching GRIB block.
    """
    file_parts: dict[str, list[xr.Dataset]] = {}

    for ds in dsets:
        for g, req in req_map.items():
            dim = req.get("dimension")
            if dim and dim not in ds.dims:
                continue
            sel = ds
            if "valid_time" in sel.coords:
                sel = sel.assign_coords(time=sel["valid_time"])

            # Vertical selection
            if dim and dim in sel.dims and not req.get("all_levels", False):
                if req.get("level_indices"):
                    idx_list = [int(i) for i in req["level_indices"]]
                    n = int(sel.sizes[dim])
                    valid_idx = [i for i in idx_list if -n <= i < n]
                    if not valid_idx:
                        continue
                    sel = sel.isel({dim: valid_idx})
                elif req.get("levels"):
                    matched = _match_levels(sel[dim].values, req["levels"], tol=float_tol)
                    if not matched:
                        continue
                    sel = sel.sel({dim: matched})

            # Variables
            keep = [v for v in req.get("variables", []) if v in sel.data_vars]
            if keep:
                file_parts.setdefault(g, []).append(sel[keep])

    return file_parts


def concat_grib2ds_by_vert_coord(
    files,
    user_requested_variables_yaml: dict,
    tracker_requested_variables_by_method_yaml: dict,
    method: str | None = None,
    index_dir: str | Path = ".cfgrib",
    float_tol: float = 0.51,
    warn: bool = True,
) -> tuple[dict[str, xr.Dataset], dict[str, dict[str, xr.Dataset]]]:
    """
    Open a list of GRIB files and build per-group user and tracker Datasets.

    Files are opened once with cfgrib; datasets are then filtered, merged, and
    concatenated along the time axis.

    Parameters
    ----------
    files : list[str or Path]
        Ordered list of GRIB files (one per time step or a time sequence).
    user_requested_variables_yaml : dict
        YAML-like request block for user variables, ``{group: spec}``.
    tracker_requested_variables_by_method_yaml : dict
        YAML-like request block for tracker variables,
        ``{method: {group: spec}}``.
    method : str or None, optional
        Restrict tracker loading to this method only.  ``None`` loads all
        methods present in the tracker YAML.
    index_dir : str or Path, optional
        Directory for cfgrib index files.  Created if absent. Default ".cfgrib".
    float_tol : float, optional
        Tolerance for numeric vertical level matching. Default 0.51.
    warn : bool, optional
        Emit a warning when the requested tracking method is absent from the
        tracker YAML. Default True.

    Returns
    -------
    by_group_user : dict[str, xr.Dataset]
        ``{group -> xr.Dataset}`` for user-requested variables.
    by_group_trk : dict[str, dict[str, xr.Dataset]]
        ``{method -> {group -> xr.Dataset}}`` for tracker-requested variables.
    """

    files = [Path(f) for f in files]
    idx_dir = Path(index_dir)
    idx_dir.mkdir(parents=True, exist_ok=True)

    # 1) Open files and inventory coordinates
    opened_per_file: dict[Path, list[xr.Dataset]] = {}
    dims_seen: set[str] = set()
    for f in files:
        dsets = cfgrib.open_datasets(str(f), indexpath=str(idx_dir / (f.name + ".idx")))
        opened_per_file[f] = dsets
        for ds in dsets:
            dims_seen.update(ds.sizes.keys())

    # 2) Normalisation YAML
    user_req = _parse_and_normalize(user_requested_variables_yaml, dims_seen)

    tracker_yaml = tracker_requested_variables_by_method_yaml or {}
    if method is None:
        methods = list(tracker_yaml.keys())
    else:
        methods = [m for m in tracker_yaml.keys() if m == method]
        if not methods and warn:
            logger.warning(
                "Tracker method '%s' not found; no tracker block will be produced.", method
            )
    tracker_req_by_method: dict[str, dict[str, dict]] = {
        m: _parse_and_normalize(tracker_yaml.get(m, {}), dims_seen) for m in methods
    }

    # 3) Union pour inventaire global
    all_groups: dict[str, dict] = dict(user_req)
    for _m, blk in tracker_req_by_method.items():
        for k, v in blk.items():
            if k not in all_groups:
                all_groups[k] = v

    global_levels: dict[str, set] = {g: set() for g, s in all_groups.items() if s.get("dimension")}
    global_depth: dict[str, int] = {g: 0 for g, s in all_groups.items() if s.get("dimension")}

    for _, dsets in opened_per_file.items():
        for ds in dsets:
            for g, spec in all_groups.items():
                dim = spec.get("dimension")
                if dim and dim in ds.dims:
                    global_depth[g] = max(global_depth[g], int(ds.sizes[dim]))
                    try:
                        vals = np.asarray(ds[dim].values, dtype=float).ravel().tolist()
                    except Exception:
                        vals = [float(v) for v in ds[dim].values]
                    global_levels[g].update(vals)

    # 4) Collect per-file pieces into lists.
    # Memory fix: accumulate datasets per file in lists, then do a single
    # xr.concat at the end — avoids O(N²) intermediate copies.
    # Before: xr.concat([accumulated, ds_file], dim="time") at each iteration
    # After: list accumulation + single final concat
    parts_user_all: dict[str, list[xr.Dataset]] = {}
    parts_trk_all: dict[str, dict[str, list[xr.Dataset]]] = {m: {} for m in methods}

    for _f, dsets in opened_per_file.items():
        parts_user = _collect_parts_for_req(dsets, user_req, float_tol, tag="user variables dict")
        parts_trk_by_m: dict[str, dict[str, list[xr.Dataset]]] = {
            m: _collect_parts_for_req(
                dsets, tracker_req_by_method[m], float_tol, tag=f"tracker variables dict:{m}"
            )
            for m in methods
        }

        for g, parts in parts_user.items():
            ds_file = xr.merge(
                parts, compat="override", join="outer", combine_attrs="drop_conflicts"
            )
            parts_user_all.setdefault(g, []).append(ds_file)

        for m, parts_trk in parts_trk_by_m.items():
            for g, parts in parts_trk.items():
                ds_file = xr.merge(
                    parts, compat="override", join="outer", combine_attrs="drop_conflicts"
                )
                parts_trk_all[m].setdefault(g, []).append(ds_file)

    # Concat unique en fin de boucle — une seule allocation par groupe
    by_group_user: dict[str, xr.Dataset] = {
        g: xr.concat(parts, 
                     dim="time",
                     compat="no_conflicts",
                     data_vars="all",
                     coords="different",
                     join="outer",
                     combine_attrs="override",
                     ).sortby("time") for g, parts in parts_user_all.items()
    }
    by_group_trk: dict[str, dict[str, xr.Dataset]] = {
        m: {g: xr.concat(parts,
                         dim="time",
                         compat="no_conflicts",
                         data_vars="all",
                         coords="different",
                         join="outer",
                         combine_attrs="override", 
                         ).sortby("time") for g, parts in grp.items()}
        for m, grp in parts_trk_all.items()
    }

    # 5) Post-processing: geometric trackers.
    # Bug fix: this block was previously inside the per-file loop, so it ran once
    # per file. Moved here, after the loop, so it runs only once.
    geo_methods = {"fixed_box", "prescribed_track"}

    if by_group_user:
        g_user_ref, ds_user_ref = next(iter(by_group_user.items()))

        data_vars = list(ds_user_ref.data_vars)
        if data_vars:
            ds_geo = ds_user_ref.drop_vars(data_vars)
        else:
            ds_geo = ds_user_ref

        for m in methods:
            if m in geo_methods:
                if m not in by_group_trk:
                    by_group_trk[m] = {}
                by_group_trk[m]["surface"] = ds_geo
    else:
        logger.warning(
            "No user Dataset available to build coordinates for"
            " 'fixed_box'/'prescribed_track' methods."
            " No tracker block will be produced for these methods."
        )

    # 6) Final deduplication
    by_group_user = {g: drop_time_dupes(ds, keep="first") for g, ds in by_group_user.items()}
    by_group_trk = {
        m: {g: drop_time_dupes(ds, keep="first") for g, ds in grp.items()}
        for m, grp in by_group_trk.items()
    }
    return by_group_user, by_group_trk
