# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import numpy as np
import xarray as xr

from frameit.processing.polar.metadata import preserve_coordinate_dependencies

logger = logging.getLogger(__name__)


def normalize_requests(raw: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """
    Normalize a YAML-like request block into a canonical structure.

    Input schema (per group)
    ------------------------
    - variables: list[str]
    - level_selection: "all" | "indices" | "values" (optional)
    - level_indices: list[int] (used if selection == "indices")
    - level_values:  list[Any] (used if selection == "values")
    Legacy keys:
    - all_levels: bool
    - levels: list[Any] (alias of level_values)

    Output schema (per group)
    -------------------------
    - variables: list[str]
    - all_levels: bool
    - level_indices: list[int]
    - levels: list[Any]
    """
    if not raw:
        return {}

    out: dict[str, dict[str, Any]] = {}
    for group, spec in raw.items():
        spec = spec or {}
        sel = str(spec.get("level_selection", "")).lower().strip()

        all_levels = bool(spec.get("all_levels", False) or sel == "all")

        level_indices: list[int] = []
        levels: list[Any] = []

        if sel == "indices":
            level_indices = list(spec.get("level_indices", []) or [])
        elif sel in {"values", ""}:
            # "" means keep legacy behavior (values-based selection when provided)
            lv = spec.get("level_values", None)
            if lv is None:
                lv = spec.get("levels", [])
            levels = list(lv or [])

        out[group] = {
            "variables": list(spec.get("variables", []) or []),
            "all_levels": all_levels,
            "level_indices": level_indices,
            "levels": levels,
        }

    return out


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float, np.integer, np.floating)) and np.isfinite(x)


def _match_levels(
    available: Sequence[Any],
    requested: Sequence[Any],
    *,
    tol: float | None,
) -> list[Any]:
    """
    Match requested vertical coordinate values to available ones.

    Parameters
    ----------
    available : Sequence[Any]
        Values present in the dataset's vertical coordinate.
    requested : Sequence[Any]
        Values requested by the user.
    tol : float or None
        Matching tolerance for numeric values.  When ``None`` exact equality
        is used; when a float, the closest available value within ``tol`` is
        accepted.

    Returns
    -------
    list[Any]
        Subset of ``available`` matching the requested values, in the order
        they appeared in ``requested``.  Duplicates are removed (first kept).

    Notes
    -----
    Non-numeric requested values are always matched by exact equality,
    regardless of ``tol``.
    """
    if not requested:
        return []

    avail = list(available)

    matched: list[Any] = []
    seen = set()

    if tol is None:
        avail_set = set(avail)
        for rv in requested:
            if rv in avail_set and rv not in seen:
                matched.append(rv)
                seen.add(rv)
        return matched

    # tol provided
    avail_num = np.array([a if _is_number(a) else np.nan for a in avail], dtype=float)

    for rv in requested:
        if _is_number(rv):
            diffs = np.abs(avail_num - float(rv))
            if np.all(np.isnan(diffs)):
                continue
            j = int(np.nanargmin(diffs))
            if np.isfinite(diffs[j]) and diffs[j] <= float(tol):
                val = avail[j]
                if val not in seen:
                    matched.append(val)
                    seen.add(val)
        else:
            if rv in avail and rv not in seen:
                matched.append(rv)
                seen.add(rv)

    return matched


def build_group_ds(
    ds: xr.Dataset,
    req: dict[str, Any],
    group_key: str,
    concat_dimension: str,
    float_tol: float | None,
    *,
    vertical_dims: set[str] | None = None,
) -> xr.Dataset | None:
    """
    Build a group dataset from a global dataset according to a normalized request.

    Parameters
    ----------
    ds:
        Source dataset that contains requested variables (and coords).
    req:
        Normalized request for this group, produced by _normalize_requests.
    group_key:
        Group name. For vertical groups, it is also the vertical dimension name
        (example: "level", "level_w", "isobaricInhPa", "heightAboveGround").
        For surface group: use "surface".
    concat_dimension:
        Name of the time dimension to enforce on outputs (expand_dims if missing).
    float_tol:
        Tolerance for numeric level matching when req specifies values.
    vertical_dims:
        Set of known vertical dimensions used to identify surface variables.
        If None, defaults to {"level","level_w","isobaricInhPa","heightAboveGround"}.

    Returns
    -------
    xr.Dataset or None
        Dataset containing only requested variables and requested vertical selection.
        Returns None if nothing can be built.
    """
    vars_req = list(req.get("variables", []) or [])
    all_levels = bool(req.get("all_levels", False))
    level_indices = req.get("level_indices", None)
    levels = req.get("levels", None)

    if not vars_req:
        return None

    if vertical_dims is None:
        vertical_dims = {"level", "level_w", "isobaricInhPa", "heightAboveGround"}

    def _warn(msg: str) -> None:
        if logger is not None:
            logger.warning(msg)
        else:
            print(msg)

    if group_key == "surface":
        keep: list[str] = []
        for v in vars_req:
            if v not in ds.data_vars:
                continue
            vdims = set(ds[v].dims)
            if vdims.intersection(vertical_dims):
                continue
            keep.append(v)

        if not keep:
            return None

        var_map: dict[str, xr.DataArray] = {}
        for v in keep:
            da = ds[v]
            if concat_dimension in ds.dims and concat_dimension not in da.dims:
                da = da.expand_dims({concat_dimension: ds[concat_dimension]})
            var_map[v] = da

        return preserve_coordinate_dependencies(ds, xr.Dataset(var_map)) if var_map else None

    # vertical group
    vert_dim = group_key
    keep = [v for v in vars_req if v in ds.data_vars and (vert_dim in ds[v].dims)]
    if not keep:
        return None

    var_map: dict[str, xr.DataArray] = {}

    for v in keep:
        da = ds[v]

        if not all_levels and vert_dim in da.dims:
            if level_indices is not None and len(level_indices) > 0:
                n = int(da.sizes.get(vert_dim, 0))
                idx_list = [int(i) for i in level_indices]
                valid = [i for i in idx_list if -n <= i < n]

                if len(valid) < len(idx_list):
                    bad = [i for i in idx_list if i not in valid]
                    _warn(
                        f"[requests._build_group_ds] indices out of range {bad} "
                        f"for size {n} (var={v}, dim={vert_dim})"
                    )

                if valid:
                    da = da.isel({vert_dim: valid})
                else:
                    continue

            elif levels is not None and len(levels) > 0:
                if vert_dim not in da.coords:
                    _warn(
                        f"[requests._build_group_ds] coord '{vert_dim}' is missing "
                        f"(var={v}, dim={vert_dim})"
                    )
                    continue

                avail = da[vert_dim].values.tolist()
                matched = _match_levels(avail, list(levels), tol=float_tol)

                missing = [lv for lv in list(levels) if lv not in matched]
                if missing:
                    _warn(
                        f"[requests._build_group_ds] unmatched levels {missing} "
                        f"(var={v}, dim={vert_dim})"
                    )

                if matched:
                    da = da.sel({vert_dim: matched})
                else:
                    continue

        if concat_dimension in ds.dims and concat_dimension not in da.dims:
            da = da.expand_dims({concat_dimension: ds[concat_dimension]})

        var_map[v] = da

    return preserve_coordinate_dependencies(ds, xr.Dataset(var_map)) if var_map else None
