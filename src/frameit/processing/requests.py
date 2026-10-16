# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
import re
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
    - level_selection: "all" | "stored" | "physical" | "indices" | "values" (optional)
    - level_indices: list[int] (used if selection == "indices")
    - level_values:  list[Any] (used if selection == "values")
    Legacy keys:
    - all_levels: bool
    - level_domain: "stored" | "physical" (all is an alias for stored)
    - levels: list[Any] (alias of level_values)

    Output schema (per group)
    -------------------------
    - variables: list[str]
    - all_levels: bool
    - level_domain: "stored" | "physical"
    - level_indices: list[int]
    - levels: list[Any]
    """
    if not raw:
        return {}

    out: dict[str, dict[str, Any]] = {}
    for group, spec in raw.items():
        spec = spec or {}
        sel = str(spec.get("level_selection", "")).lower().strip()

        if sel not in {"", "all", "stored", "physical", "indices", "values"}:
            raise ValueError(f"Unknown level_selection {sel!r} for {group}")
        domain = spec.get("level_domain", "physical" if sel == "physical" else "stored")
        if domain not in {"stored", "physical"}:
            raise ValueError(f"level_domain must be stored or physical for {group}")
        if sel in {"all", "stored", "physical"} and domain != (
            "physical" if sel == "physical" else "stored"
        ):
            raise ValueError(f"Conflicting level_selection and level_domain for {group}")
        all_levels = bool(spec.get("all_levels", False) or sel in {"all", "stored", "physical"})

        level_indices: list[int] = []
        levels: list[Any] = []

        if sel == "indices" or (not sel and spec.get("level_indices")):
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
            "level_domain": domain,
            "level_indices": level_indices,
            "levels": levels,
        }

    return out


def selected_native_indices(ds: xr.Dataset, req: dict[str, Any], vert_dim: str) -> list[int]:
    """Return positional indices without renumbering source levels.

    COMODO ``c_grid_dynamic_range`` is one-based and inclusive on each axis.
    An optional zero-based ``source_native_index`` (or axis-prefixed coordinate
    ``<axis>_source_native_index``) maps a previously selected axis to its original
    positions. Ordinary GRIB pressure/height axes have no vertical halo. MNH
    physical selection requires explicit range evidence, never positive heights.
    Value-based requests use exact matches here; :func:`build_group_ds` also
    supports its explicit numeric matching tolerance.
    """
    n = ds.sizes[vert_dim]
    domain = req.get("level_domain", "physical" if req.get("level_selection") == "physical"
                     else "stored")
    if domain not in {"stored", "physical"}:
        raise ValueError("level_domain must be stored or physical")
    positions = list(range(n))
    if domain == "physical":
        coord = ds.coords.get(vert_dim)
        dynamic_range = None if coord is None else coord.attrs.get("c_grid_dynamic_range")
        if dynamic_range is None:
            if vert_dim not in {"isobaricInhPa", "isobaricInPa", "heightAboveGround",
                                "heightAboveSea"}:
                raise ValueError(
                    f"Physical selection for {vert_dim} requires "
                    f"{vert_dim}.c_grid_dynamic_range; stored levels remain available"
                )
        else:
            if isinstance(dynamic_range, str):
                match = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", dynamic_range)
                bounds = [int(v) for v in match.groups()] if match else []
            else:
                # Object dtype preserves booleans for strict validation.
                values = np.asarray(dynamic_range, dtype=object)
                bounds = values.tolist() if values.shape == (2,) else []
            if (len(bounds) != 2 or any(isinstance(v, bool) or not isinstance(
                    v, (int, np.integer)) for v in bounds)
                    or not 1 <= bounds[0] <= bounds[1]):
                raise ValueError(f"Invalid {vert_dim}.c_grid_dynamic_range: {dynamic_range!r}")
            native = np.arange(n)
            for name in (f"{vert_dim}_source_native_index", "source_native_index"):
                if name in ds.coords and ds[name].dims == (vert_dim,):
                    native = np.asarray(ds[name].values)
                    if (native.dtype.kind not in "iu" or np.any(native < 0)
                            or len(np.unique(native)) != n):
                        raise ValueError(f"{name} must contain unique nonnegative native indices")
                    break
            else:
                if bounds[1] > n:
                    raise ValueError(f"{vert_dim}.c_grid_dynamic_range exceeds axis size {n}")
            positions = np.flatnonzero((native >= bounds[0] - 1) & (native < bounds[1])).tolist()
            if not positions:
                raise ValueError(f"No physical levels remain on {vert_dim}")
    indices = req.get("level_indices")
    if indices and not req.get("all_levels", False):
        # Indices always address stored positions, not a renumbered physical axis.
        positions = [int(i) % n for i in indices if -n <= int(i) < n
                     and int(i) % n in positions]
    elif not req.get("all_levels", False):
        levels = req.get("level_values", req.get("levels", []))
        if levels:
            if vert_dim not in ds.coords:
                raise ValueError(f"Value selection requires the {vert_dim} coordinate")
            available = ds[vert_dim].values.tolist()
            matched = _match_levels([available[i] for i in positions], levels, tol=None)
            positions = [i for value in matched for i in positions if available[i] == value]
    return positions


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

        return preserve_coordinate_dependencies(
            ds, xr.Dataset(var_map, attrs=dict(ds.attrs))
        ) if var_map else None

    # vertical group
    vert_dim = group_key
    keep = [v for v in vars_req if v in ds.data_vars and (vert_dim in ds[v].dims)]
    if not keep:
        return None

    var_map: dict[str, xr.DataArray] = {}
    physical = req.get("level_domain") == "physical" or req.get("level_selection") == "physical"
    native_positions = selected_native_indices(
        ds, {"level_domain": "physical", "all_levels": True}, vert_dim
    ) if physical else None

    for v in keep:
        da = ds[v]
        if physical and (all_levels or not level_indices):
            da = da.isel({vert_dim: native_positions})

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

                if physical:
                    valid = [i for i in valid if i % n in native_positions]

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

    return preserve_coordinate_dependencies(
        ds, xr.Dataset(var_map, attrs=dict(ds.attrs))
    ) if var_map else None
