# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import cfgrib
import numpy as np
import xarray as xr

from frameit.check.check_functions import drop_time_dupes
from frameit.io.loader import managed_loading, resolve_input_files
from frameit.processing.derived.wind import normalize_native_wind_units, normalize_winds
from frameit.processing.polar.metadata import preserve_coordinate_dependencies
from frameit.processing.wind_reference import wind_pairs

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
        # "surface" is a logical group spanning GRIB surface/meanSea/10-m
        # blocks, not the scalar "surface" coordinate on some messages.
        if dim is None and group != "surface" and group in dims_seen:
            dim = group
        from frameit.processing.requests import normalize_requests

        normalized = normalize_requests({group: spec})[group]
        out[group] = {
            "dimension": dim,
            "variables": list(spec.get("variables", [])),
            # GRIB pressure/height axes have no native halo levels.
            "all_levels": normalized["all_levels"],
            "levels": normalized["levels"],
            "level_indices": normalized["level_indices"],
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
    *,
    select_levels: bool = True,
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
            if dim and dim not in ds.dims and dim not in ds.coords:
                continue
            keep = [v for v in req.get("variables", []) if v in ds.data_vars]
            if not keep:
                continue
            # Expanding an unchunked backend can materialize its variables.
            # Restrict first: unrelated atmospheric fields are not dependencies
            # of a small coupled-source extraction.
            sel = preserve_coordinate_dependencies(ds, ds[keep])
            if dim and dim not in sel.dims:
                if sel[dim].ndim != 0:
                    continue
                sel = sel.expand_dims(dim)
            if "valid_time" in sel.coords:
                valid_dims = sel["valid_time"].dims
                if len(valid_dims) > 1:
                    raise ValueError("GRIB inputs with multiple forecast initializations and "
                                     "lead-time axes require an explicit single-cycle selection")
                sel = sel.assign_coords(time=sel["valid_time"])
                if valid_dims and valid_dims != ("time",):
                    sel = sel.swap_dims({valid_dims[0]: "time"})

            # Vertical selection
            if select_levels and dim and dim in sel.dims and not req.get("all_levels", False):
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
                file_parts.setdefault(g, []).append(
                    preserve_coordinate_dependencies(sel, sel[keep]))

    return file_parts


def _select_group_levels(ds, req, float_tol):
    """Select only after the file's components have been merged and prepared."""
    dim = req.get("dimension")
    if not dim or req.get("all_levels", False):
        return ds
    if req.get("level_indices"):
        n = ds.sizes[dim]
        indices = [int(i) for i in req["level_indices"] if -n <= int(i) < n]
        return ds.isel({dim: indices}) if indices else None
    if req.get("levels"):
        levels = _match_levels(ds[dim].values, req["levels"], tol=float_tol)
        return ds.sel({dim: levels}) if levels else None
    return ds


def _retain_wind_geometry(ds, dsets, conf, group):
    """Retain declared rotation inputs even when cfgrib puts them in another block."""
    if conf is None:
        return ds
    names = {conf.name_latitude, conf.name_longitude}
    for pair in wind_pairs(conf, group):
        rotation = pair.get("rotation") or {}
        if rotation.get("coordinate"):
            names.add(rotation["coordinate"])
        if rotation.get("method") == "mesonh_projection":
            names.update(("BETA", "RPK", "LON0", "CARTESIAN"))
    # The explicit scalar compatibility path names grid_rotation.
    if getattr(conf, "wind_reference_frame", None) == "grid":
        names.add("grid_rotation")
    for source in dsets:
        for name in names:
            if name not in ds and name in source:
                ds = ds.assign_coords({name: source[name]})
            elif name not in ds and name not in ds.attrs and name in source.attrs:
                ds = ds.assign_attrs({name: source.attrs[name]})
    return ds


@managed_loading
def concat_grib2ds_by_vert_coord(
    files,
    user_requested_variables_yaml: dict,
    tracker_requested_variables_by_method_yaml: dict,
    method: str | None = None,
    index_dir: str | Path = "cache",
    float_tol: float = 0.51,
    warn: bool = True,
    *,
    strict: bool = False,
    resources=None,
    duplicate_time_policy="first",
    wind_conf=None,
    native_output_groups: dict[str, xr.Dataset] | None = None,
    filter_requested: bool = False,
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
        Directory for cfgrib index files. Created if absent. Default "cache".
    float_tol : float, optional
        Tolerance for numeric vertical level matching. Default 0.51.
    warn : bool, optional
        Emit a warning when the requested tracking method is absent from the
        tracker YAML. Default True.
    wind_conf : optional
        Explicit wind declarations. Normalize each file's merged group to
        Earth-relative m/s before vertical selection and time concatenation.
        None preserves the historical unprepared loader API.
    native_output_groups : mutable dict, optional
        When supplied with wind_conf, populate user groups from the same source
        pieces with m/s units but original names, locations and source vector
        basis. Uses the same vertical/time selection, without derived speed.

    Returns
    -------
    by_group_user : dict[str, xr.Dataset]
        ``{group -> xr.Dataset}`` for user-requested variables.
    by_group_trk : dict[str, dict[str, xr.Dataset]]
        ``{method -> {group -> xr.Dataset}}`` for tracker-requested variables.
    """

    files = resolve_input_files(files, strict=strict)
    idx_dir = Path(index_dir)
    idx_dir.mkdir(parents=True, exist_ok=True)

    # 1) Open files and inventory coordinates
    opened_per_file: dict[Path, list[xr.Dataset]] = {}
    dims_seen: set[str] = set()
    for f in files:
        source_id = hashlib.sha256(str(f.resolve()).encode()).hexdigest()[:16]
        backend_kwargs = {
            "read_keys": ["uvRelativeToGrid"],
            "indexpath": str(idx_dir / (f.name + f".{source_id}.{{short_hash}}.idx")),
        }
        selectors = None
        if filter_requested:
            import eccodes as ec

            blocks = [user_requested_variables_yaml]
            tracker_blocks = tracker_requested_variables_by_method_yaml or {}
            blocks.extend(block for key, block in tracker_blocks.items()
                          if method is None or key == method)
            wanted = {name for block in blocks for spec in block.values()
                      for name in spec.get("variables", []) if name != "wind_speed"}
            if wind_conf is not None:
                if wind_conf.wind_reference_frame == "grid":
                    wanted.add("grid_rotation")
                for pair in wind_conf.wind_pairs:
                    if wanted.intersection((pair["u"], pair["v"])):
                        rotation = pair.get("rotation") or {}
                        if rotation.get("coordinate"):
                            wanted.add(rotation["coordinate"])
            if wanted:
                selectors = set()
                with Path(f).open("rb") as stream:
                    while True:
                        handle = ec.codes_grib_new_from_file(stream, headers_only=True)
                        if handle is None:
                            break
                        try:
                            short = str(ec.codes_get(handle, "shortName"))
                            try:
                                canonical = str(ec.codes_get(handle, "cfVarName"))
                            except ec.CodesInternalError:
                                canonical = short
                            aliases = {"msl": "prmsl", "10u": "u10", "10v": "v10"}
                            if short not in {"unknown", "undef", ""} and wanted.intersection(
                                {short, canonical, aliases.get(short, short)}
                            ):
                                selectors.add(short)
                        finally:
                            ec.codes_release(handle)
            else:
                # Coordinate-only coupled requests need no arbitrary data field.
                from frameit.core.preflight import _grib_metadata

                metadata = _grib_metadata(f)[0]
                lat, lon = metadata.latitude.values, metadata.longitude.values
                if not (np.allclose(lat, lat[:, :1], rtol=0, atol=1.e-12)
                        and np.allclose(lon, lon[:1, :], rtol=0, atol=1.e-12)):
                    raise ValueError("Coordinate-only coupled GRIB requires a regular lon/lat grid")
                dsets = [xr.Dataset(coords={
                    "latitude": ("latitude", lat[:, 0], {"units": "degrees_north"}),
                    "longitude": ("longitude", lon[0], {"units": "degrees_east"}),
                    "valid_time": metadata.valid_time.variable,
                })]
                selectors = set()
        if selectors is None:
            dsets = cfgrib.open_datasets(str(f), backend_kwargs=backend_kwargs)
        elif wanted:
            dsets = []
            for short in sorted(selectors):
                dsets.extend(cfgrib.open_datasets(str(f), backend_kwargs={
                    **backend_kwargs, "filter_by_keys": {"shortName": short}}))
        for ds in dsets:
            resources.add(ds)
        # Match the canonical aliases already used by metadata preflight, while
        # retaining original variables for callers that request native names.
        aliases = {"msl": "prmsl", "10u": "u10", "10v": "v10"}
        dsets = [ds.assign({new: ds[old].assign_attrs(source_variable_name=old)
                            for old, new in aliases.items() if old in ds and new not in ds})
                 for ds in dsets]
        opened_per_file[f] = dsets
        for ds in dsets:
            dims_seen.update(ds.sizes.keys())
            dims_seen.update(ds.coords)

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
                if dim and dim in ds.coords:
                    global_depth[g] = max(global_depth[g], int(ds[dim].size))
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
    parts_native_all: dict[str, list[xr.Dataset]] = {}
    parts_trk_all: dict[str, dict[str, list[xr.Dataset]]] = {m: {} for m in methods}

    for _f, dsets in opened_per_file.items():
        parts_user = _collect_parts_for_req(
            dsets, user_req, float_tol, tag="user variables dict", select_levels=False
        )
        parts_trk_by_m: dict[str, dict[str, list[xr.Dataset]]] = {
            m: _collect_parts_for_req(
                dsets, tracker_req_by_method[m], float_tol, tag=f"tracker variables dict:{m}",
                select_levels=False,
            )
            for m in methods
        }

        for g, parts in parts_user.items():
            ds_file = xr.merge(
                parts, compat="override", join="outer", combine_attrs="drop_conflicts"
            )
            ds_file = _retain_wind_geometry(ds_file, dsets, wind_conf, g)
            if wind_conf is not None:
                if native_output_groups is not None:
                    native = normalize_native_wind_units(ds_file, wind_conf, g)
                    native = _select_group_levels(native, user_req[g], float_tol)
                    if native is not None:
                        parts_native_all.setdefault(g, []).append(native)
                ds_file = normalize_winds(ds_file, wind_conf, g)
            ds_file = _select_group_levels(ds_file, user_req[g], float_tol)
            if ds_file is not None:
                parts_user_all.setdefault(g, []).append(ds_file)

        for m, parts_trk in parts_trk_by_m.items():
            for g, parts in parts_trk.items():
                ds_file = xr.merge(
                    parts, compat="override", join="outer", combine_attrs="drop_conflicts"
                )
                ds_file = _retain_wind_geometry(ds_file, dsets, wind_conf, g)
                if wind_conf is not None:
                    ds_file = normalize_winds(ds_file, wind_conf, g)
                ds_file = _select_group_levels(ds_file, tracker_req_by_method[m][g], float_tol)
                if ds_file is not None:
                    parts_trk_all[m].setdefault(g, []).append(ds_file)

    # Concat unique en fin de boucle — une seule allocation par groupe
    by_group_user: dict[str, xr.Dataset] = {
        g: xr.concat(
            parts,
            dim="time",
            # compat="equals",
            compat="no_conflicts",
            data_vars="all",
            coords="different",
            join="outer",
            combine_attrs="override",
        ).sortby("time")
        for g, parts in parts_user_all.items()
    }
    by_group_trk: dict[str, dict[str, xr.Dataset]] = {
        m: {
            g: xr.concat(
                parts,
                dim="time",
                # compat="equals",
                compat="no_conflicts",
                data_vars="all",
                coords="different",
                join="outer",
                combine_attrs="override",
            ).sortby("time")
            for g, parts in grp.items()
        }
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
        # Coordinate-only runs must not depend on an arbitrary user field.
        geometry_parts = []
        for dsets in opened_per_file.values():
            reference = next((ds for ds in dsets if all(
                name in ds.coords for name in ("latitude", "longitude", "valid_time")
            )), None)
            if reference is not None:
                geometry_parts.append(xr.Dataset(coords={
                    "time": np.atleast_1d(reference.valid_time.values),
                    "latitude": reference.latitude.reset_coords(drop=True),
                    "longitude": reference.longitude.reset_coords(drop=True),
                }))
        if geometry_parts:
            ds_geo = xr.concat(geometry_parts, dim="time").sortby("time")
            for m in methods:
                if m in geo_methods:
                    by_group_trk.setdefault(m, {})["surface"] = ds_geo

    # 6) Final deduplication
    by_group_user = {
        g: drop_time_dupes(ds, keep=duplicate_time_policy) for g, ds in by_group_user.items()
    }
    by_group_trk = {
        m: {g: drop_time_dupes(ds, keep=duplicate_time_policy) for g, ds in grp.items()}
        for m, grp in by_group_trk.items()
    }
    if native_output_groups is not None and wind_conf is not None:
        native_output_groups.update({
            g: drop_time_dupes(xr.concat(
                parts, dim="time", compat="no_conflicts", data_vars="all", coords="different",
                join="outer", combine_attrs="override",
            ).sortby("time"), keep=duplicate_time_policy)
            for g, parts in parts_native_all.items()
        })
    return by_group_user, by_group_trk
