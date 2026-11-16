# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from frameit.core.configuration import field_selection
from frameit.processing.polar.metadata import preserve_coordinate_dependencies
from frameit.utils.units import UNITS, convert_units, unit_key

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
        vertical_dims = {"level", "level_w", "isobaricInhPa", "heightAboveGround",
                         "deptht", "depthu", "depthv", "depthw", "s_rho", "s_w"}

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


_VERTICAL_DIMENSIONS = {
    "level", "level_w", "heightAboveGround", "heightAboveSea", "isobaricInhPa",
    "isobaricInPa", "deptht", "depthu", "depthv", "depthw", "s_rho", "s_w",
}


def _vertical_axis(field, grid):
    """Use selectable dimensions and coordinate evidence, never array rank."""
    dimensions = set(field["dimensions"] or ()) & grid["dimensions"].keys()
    coordinates = grid["coordinates"]
    labelled = {
        name: coord for name, coord in coordinates.items()
        if len(coord["dimensions"]) == 1 and coord["dimensions"][0] in dimensions
        and (coord["attributes"].get("axis") == "Z"
             or coord["attributes"].get("positive") in {"up", "down"}
             or coord["attributes"].get("standard_name") in {
                 "air_pressure", "height", "altitude", "depth"})
    }
    axes = (dimensions & _VERTICAL_DIMENSIONS) | {
        coord["dimensions"][0] for coord in labelled.values()}
    if len(axes) > 1:
        raise ValueError(f"{field['name']}: several selectable vertical dimensions {sorted(axes)}")
    if not axes:
        return None
    dim = next(iter(axes))
    names = [name for name, coord in labelled.items() if coord["dimensions"] == [dim]]
    if len(names) > 1:
        raise ValueError(f"{field['name']}: ambiguous vertical coordinates {names} on {dim}")
    name = names[0] if names else dim if dim in coordinates else None
    size = grid["dimensions"][dim]
    coord = coordinates.get(name)
    if coord is not None and np.asarray(coord["values"]).shape != (size,):
        raise ValueError(f"{field['name']}: invalid vertical coordinate {name} shape")
    native = np.arange(size)
    for auxiliary in (f"{dim}_source_native_index", "source_native_index"):
        if auxiliary in coordinates and coordinates[auxiliary]["dimensions"] == [dim]:
            native = np.asarray(coordinates[auxiliary]["values"])
            if (native.shape != (size,) or native.dtype.kind not in "iu"
                    or np.any(native < 0) or len(np.unique(native)) != size):
                raise ValueError(f"{auxiliary}: require unique nonnegative original indices")
            break
    return {"dimension": dim, "coordinate": name, "size": size,
            "native": native, "descriptor": coord, "grid": grid}


def _unit_identity(units):
    key = unit_key(units)
    return next(((quantity, factors[key]) for quantity, (_, factors) in UNITS.items()
                 if key in factors), key)


def _coordinate_units(descriptor, target, *, inherited=None):
    attrs = dict(descriptor["attributes"])
    source = attrs.get("units") if unit_key(attrs.get("units")) else inherited
    values = np.asarray(descriptor["values"])
    factor = 1.
    if source and target and unit_key(source) != unit_key(target):
        quantity = next((q for q, (_, factors) in UNITS.items()
                         if unit_key(source) in factors and unit_key(target) in factors), None)
        if quantity is None:
            raise ValueError(f"Incompatible vertical coordinate units {source!r} and {target!r}")
        factors = UNITS[quantity][1]
        factor = factors[unit_key(source)] / factors[unit_key(target)]
        converted = convert_units(xr.DataArray(0., attrs={**attrs, "units": source}),
                                  quantity, target=target)
        # Coordinate arithmetic uses binary64; preserve field/storage precision elsewhere.
        values = values.astype("float64") * factor
        attrs = converted.attrs
    if target:
        attrs["units"] = target
        if not source:
            attrs["unit_assumption"] = target
            attrs["unit_assumption_source"] = "user_supplied_vertical_units"
    return values, attrs, factor


def _coordinate_ulp(values, dtype):
    labels = np.asarray(values, dtype=dtype)
    with np.errstate(over="ignore"):
        up = np.nextafter(labels, np.array(np.inf, dtype=dtype)).astype("float64")
        down = np.nextafter(labels, np.array(-np.inf, dtype=dtype)).astype("float64")
    upper, lower = up - labels, labels - down
    # At the finite extremes use the inward neighbour, not an infinite tolerance.
    return np.maximum(np.where(np.isfinite(upper), upper, 0),
                      np.where(np.isfinite(lower), lower, 0))


def _level_roundoff(descriptor, converted, factor):
    """Half a stored ULP plus four binary64 conversion/comparison ULPs."""
    dtype = np.dtype(descriptor["dtype"])
    error = (.5 * _coordinate_ulp(descriptor["values"], dtype) * abs(factor)
             if dtype.kind == "f" else 0.)
    return error + 4 * _coordinate_ulp(converted, np.dtype("float64"))


def _bind_vertical(axis, selector, context, warnings):
    dim, name = axis["dimension"], axis["coordinate"]
    descriptor = axis["descriptor"]
    source_units = descriptor["attributes"].get("units") if descriptor else None
    source_units = source_units if unit_key(source_units) else None
    units = selector.get("units") or source_units
    origin = "input" if source_units else "user_assumption" if units else "unknown"
    if not source_units:
        warning = (f"{context}: {name or dim} has no source units; stored numbers are assumed "
                   f"to use requested {units!r} without rescaling (user-supplied assumption)."
                   if units else f"{context}: {name or dim} has no source or requested units; "
                   "vertical units remain unknown.")
        if warning not in warnings:
            warnings.append(warning)
    values, tolerance = None, None
    if descriptor:
        values, _, factor = _coordinate_units(descriptor, units)
        if values.dtype.kind in "iuf":
            if not np.isfinite(values).all():
                raise ValueError(f"{context}: nonfinite vertical labels on {name}")
            tolerance = _level_roundoff(descriptor, values, factor)
    positions = list(range(axis["size"]))
    if len(selector.keys() & {"indices", "values", "domain"}) > 1:
        raise ValueError(f"{context}: use exactly one level selection strategy")
    if "indices" in selector:
        indices = selector["indices"]
        if isinstance(indices, dict):
            indices = list(range(indices["start"], indices["end"] + 1, indices.get("step", 1)))
        if len(set(indices)) != len(indices):
            raise ValueError(f"{context}: duplicate level indices")
        positions = []
        for index in indices:
            if isinstance(index, bool) or not isinstance(index, (int, np.integer)) or index < 0:
                raise ValueError(f"{context}: level indices must be nonnegative original positions")
            matches = np.flatnonzero(axis["native"] == index)
            if not len(matches):
                raise ValueError(f"{context}: unavailable level index {index} on {dim}")
            positions.append(int(matches[0]))
    elif "values" in selector:
        if values is None:
            raise ValueError(f"{context}: value selection requires coordinate labels on {dim}")
        if tolerance is None:
            raise ValueError(f"{context}: value selection requires numeric coordinate "
                             f"labels on {dim}")
        requested = selector["values"]
        if isinstance(requested, dict):
            low, high = requested["min"], requested["max"]
            positions = [i for i, value in enumerate(values)
                         if low - tolerance[i] <= value <= high + tolerance[i]]
        else:
            positions = []
            for value in requested:
                matching = np.flatnonzero(
                    np.abs(values - value) <= tolerance
                    + 4 * _coordinate_ulp(value, np.dtype("float64")))
                if not len(matching):
                    raise ValueError(f"{context}: unavailable level value {value} on {name}")
                if len(matching) > 1:
                    original = axis["native"][matching].tolist()
                    raise ValueError(f"{context}: ambiguous level value {value} on {name}; "
                                     f"matches original positions {original}")
                position = int(matching[0])
                if position in positions:
                    raise ValueError(f"{context}: duplicate resolved level {value} on {name}")
                positions.append(position)
    elif selector.get("domain") == "physical":
        coord = axis["grid"]["coordinates"].get(dim, descriptor)
        attrs = {} if coord is None else coord["attributes"]
        coords = {dim: (dim, np.arange(axis["size"]), attrs)}
        if any(n in axis["grid"]["coordinates"]
               and axis["grid"]["coordinates"][n]["dimensions"] == [dim]
               for n in (f"{dim}_source_native_index", "source_native_index")):
            coords["source_native_index"] = (dim, axis["native"])
        probe = xr.Dataset(coords=coords)
        positions = selected_native_indices(probe, {"level_domain": "physical"}, dim)
    if not positions:
        raise ValueError(f"{context}: empty level selection on {dim}")
    coordinates = {}
    bounds = descriptor["attributes"].get("bounds") if descriptor else None
    for coord_name, coord in axis["grid"]["coordinates"].items():
        if dim not in coord["dimensions"]:
            continue
        data, attrs = np.asarray(coord["values"]), dict(coord["attributes"])
        if coord_name == name or coord_name == bounds:
            data, attrs, _ = _coordinate_units(coord, units, inherited=source_units)
        data = np.take(data, positions, axis=coord["dimensions"].index(dim))
        if "actual_range" in attrs:
            if data.size and data.dtype.kind in "iuf" and np.isfinite(data).all():
                attrs["actual_range"] = np.asarray([data.min(), data.max()])
            else:
                attrs.pop("actual_range")
        coordinates[coord_name] = {
            **coord, "values": data, "attributes": attrs, "dtype": str(data.dtype)}
    if bounds and bounds not in coordinates:
        raise ValueError(f"{context}: missing vertical coordinate bounds {bounds}")
    return {"dimension": dim, "coordinate": name, "positions": positions,
            "source_native_indices": axis["native"][positions].tolist(),
            "values": values[positions].tolist() if values is not None else None,
            "source_units": source_units, "units": units, "units_origin": origin,
            "coordinates": coordinates}


def _coordinate_support(source, field, record):
    grid = source["native_grids"][record["grid_id"]]
    needed = set(field.get("coordinate_dependencies", {}))
    if record["locator"]["format"] == "netcdf":
        needed.update(grid["coordinates"])
    for name in sorted(needed):
        if name not in grid["coordinates"]:
            raise ValueError(f"{field['name']}: coordinate {name} support missing on owning grid "
                             f"{record['grid_id']}")
        providers = grid.get("coordinate_providers", {}).get(name, [])
        locator = record["locator"]
        available = any(
            provider["path"] == locator["path"] and provider["variable"] == name
            and any(sample["time"] == record["time"] and sample["cycle"] == record["cycle"]
                    and sample["clock"] == record["clock"]
                    and sample["coordinate_indexers"] == locator["coordinate_indexers"]
                    and sample["indexers"] == {
                        dim: i for dim, i in locator["coordinate_indexers"].items()
                        if dim in grid["coordinates"][name]["dimensions"]}
                    for sample in provider["samples"])
            for provider in providers)
        if not available:
            raise ValueError(f"{field['name']}: coordinate {name} support unavailable for owning "
                             f"provider/sample {locator} at {record['time']}")


def _array_vertical_support(parent, positions, dependency, support, units, context):
    """Shared native dimensions need the requested original positions and labels."""
    if parent["dimension"] != dependency["dimension"]:
        return
    by_native = {int(dependency["native"][i]): i for i in support}
    indices = parent["native"][positions].tolist()
    if any(i not in by_native for i in indices):
        raise ValueError(f"{context}: vertical index support unavailable for {indices}")
    left, right = parent["descriptor"], dependency["descriptor"]
    if left is None or right is None:
        return
    left_units, right_units = (c["attributes"].get("units") for c in (left, right))
    if not units and bool(unit_key(left_units)) != bool(unit_key(right_units)):
        raise ValueError(f"{context}: vertical unit support needs explicit variables.levels.units")
    target = units or left_units
    lv, _, lf = _coordinate_units(left, target)
    rv, _, rf = _coordinate_units(right, target)
    other_positions = [by_native[i] for i in indices]
    if lv.dtype.kind in "iuf" and rv.dtype.kind in "iuf":
        tolerance = (_level_roundoff(left, lv, lf)[positions]
                     + _level_roundoff(right, rv, rf)[other_positions])
        equal = np.all(np.abs(lv[positions] - rv[other_positions]) <= tolerance)
    else:
        equal = np.array_equal(lv[positions], rv[other_positions])
    if not equal:
        raise ValueError(f"{context}: vertical coordinate support differs at original "
                         f"indices {indices}")


def _fa_gridpoint(source, record):
    from frameit.io.fa_contracts import validate_descriptor

    context = (f"{record['locator']['path']}: {record['name']} record at {record['time']}, "
               f"cycle {record['cycle']}")
    descriptor = record.get("native_descriptor")
    try:
        validate_descriptor(descriptor)
    except ValueError as exc:
        raise ValueError(f"{context}: missing or invalid record descriptor: {exc}") from exc
    if (descriptor["native_id"] != record["name"]
            or record["locator"]["records"] != [record["name"]]):
        raise ValueError(f"{context}: record descriptor native_id contradicts "
                         "native record identity")
    native = descriptor["native"]
    if (native.get("representation") != "gridpoint" or native.get("shape") is None
            or descriptor["eligibility"].get("decode") != "conditional"):
        raise ValueError(f"{context}: FA native gridpoint eligibility unresolved/blocked: "
                         f"{descriptor['eligibility'].get('reasons', [])}")
    grid = source["native_grids"][record["grid_id"]]
    shape = grid.get("fa_geometry", {}).get(
        "fa_native_shape", [grid["dimensions"].get("y"), grid["dimensions"].get("x")])
    if native["shape"] != shape:
        raise ValueError(f"{context}: native shape contradicts owning grid {record['grid_id']}")
    for key, clock in (("valid_time", "time"), ("reference_time", "cycle")):
        value = descriptor["temporal_support"].get(key)
        if value is not None and np.datetime64(value) != record[clock]:
            raise ValueError(f"{context}: record descriptor {key} contradicts the sample clock")
    header = grid.get("fa_header", grid.get("native_vertical_header", {}))
    for key, value in descriptor["sampling"].get("native_vertical_header", {}).items():
        if key in header and not np.array_equal(value, header[key]):
            raise ValueError(f"{context}: record descriptor {key} contradicts the owning FA header")
    return descriptor


def _fa_cube_axis(source, field, record, records_by_name):
    from frameit.io.fa_cubes import cube_layouts

    grid, cube = source["native_grids"][record["grid_id"]], field["native_cube"]
    context = (f"{record['locator']['path']}: {field['name']} cube at {record['time']}, "
               f"cycle {record['cycle']}")
    parts = {}
    for name in cube["records"]:
        candidates = [r for _, r in records_by_name.get(name, ())
                      if r["time"] == record["time"]
                      and r["cycle"] == record["cycle"]
                      and r["locator"]["path"] == record["locator"]["path"]]
        if len(candidates) != 1:
            raise ValueError(f"{context}: FA cube record {name} needs one evidenced "
                             "provider/sample in its owning file")
        parts[name] = deepcopy(_fa_gridpoint(source, candidates[0]))
    count = grid["native_vertical_header"].get("KNIVER")
    if not isinstance(count, int) or count < 1:
        raise ValueError(f"{context}: FA cube has no evidenced native vertical header")
    try:
        layout = cube_layouts(
            {"field_descriptors": parts,
             "hybrid_contract": {"interface_indices": list(range(count + 1))}},
            {"native_cubes": {field["name"]: cube}}, [field["name"]])[field["name"]]
    except ValueError as exc:
        raise ValueError(f"{context}: {exc}") from exc
    dim, labels = layout["group"], np.asarray(layout["levels"])
    grid = {**grid, "dimensions": {**grid["dimensions"], dim: len(labels)},
            "coordinates": {**grid["coordinates"],
                dim: {"dimensions": [dim], "values": labels, "dtype": str(labels.dtype),
                      "attributes": {"axis": "Z", "units": "1"}},
                f"{dim}_source_native_index": {
                    "dimensions": [dim], "values": np.asarray(layout["source_native_indices"]),
                    "dtype": "int64", "attributes": {"units": "1"}}}}
    return _vertical_axis({**field, "dimensions": [dim, "y", "x"]}, grid)


def _field_axis(source, field, record, records_by_name):
    grid = source["native_grids"][record["grid_id"]]
    if record["locator"]["format"] == "grib":
        group = field["group"]
        # These are adapter-identified single-height parameters, not a singleton-axis rule.
        if group in {"surface", "meanSea"} or field["attributes"].get("GRIB_paramId") in {165, 166}:
            return None
        if group not in {"isobaricInhPa", "isobaricInPa", "heightAboveGround",
                         "heightAboveSea", "hybrid"}:
            raise ValueError(f"{field['name']}: unresolved GRIB selectable axis {group!r}")
        # cfgrib's admitted coordinate convention is decreasing pressure, otherwise
        # increasing labels. The selected field's messages establish availability.
        labels = np.asarray(sorted(
            {r["level"] for _, r in records_by_name[record["name"]]
             if r["field_id"] == record["field_id"]},
            reverse=group in {"isobaricInhPa", "isobaricInPa"}))
        units = {"isobaricInhPa": "hPa", "isobaricInPa": "Pa",
                 "heightAboveGround": "m", "heightAboveSea": "m", "hybrid": "1"}[group]
        # Use this field's inventoried axis, not levels shared by horizontal geometry.
        grid = {**grid, "dimensions": {**grid["dimensions"], group: len(labels)},
                "coordinates": {**grid["coordinates"], group: {
                    "dimensions": [group], "values": labels, "dtype": str(labels.dtype),
                    "attributes": {"axis": "Z", "units": units}}}}
        return _vertical_axis({**field, "dimensions": [group, *field["dimensions"]]}, grid)
    if field.get("native_cube"):
        return _fa_cube_axis(source, field, record, records_by_name)
    if record["locator"]["format"] == "fa":
        _fa_gridpoint(source, record)
        return None
    return _vertical_axis(field, grid)


def native_field_group(source, field, record=None):
    """Use native identity evidence, not a request label or transformed grid."""
    if source["format"] == "grib":
        return field["group"]
    if field.get("native_cube"):
        return "level_w" if field["native_cube"]["vertical_position"] == "interface" else "level"
    grid = source["native_grids"][record["grid_id"] if record else field["grid_id"]]
    axis = _vertical_axis(field, grid)
    return axis["dimension"] if axis else None


def field_candidates(source, request, reference, records_by_name):
    """Return original inventory positions, restricted only by explicit native identity."""
    name, group, _ = field_selection(request, reference)
    candidates = records_by_name.get(name, [])
    if group is None:
        return candidates
    return [(index, record) for index, record in candidates
            if native_field_group(source, source["fields"][record["field_id"]], record) == group]


def resolve_field_metadata(attributes, declaration, context, *, temporal_names=("time",)):
    """Complete stored-value metadata, never convert values or replace known facts."""
    import re

    from frameit.io.surfex_utils import _unit_identity as stored_unit_identity
    from frameit.utils.units import UNITS

    attrs = deepcopy(attributes)
    origins = {key: "input" for key in (
        "units", "kind", "temporal_kind", "long_name", "standard_name")
        if attrs.get(key) is not None and str(attrs[key]).strip()}
    kinds = {"instant": "instantaneous", "instantaneous": "instantaneous",
             "point": "instantaneous", "once": "instantaneous",
             "avg": "mean", "average": "mean", "mean": "mean",
             "accum": "accumulated", "accumulate": "accumulated", "sum": "accumulated"}
    temporal = [attrs.get("temporal_kind")]
    temporal.extend(kinds.get(str(attrs[key]).lower(), str(attrs[key]).lower())
                    for key in ("GRIB_stepType", "online_operation") if attrs.get(key))
    methods = re.sub(r"\([^)]*\)", "", str(attrs.get("cell_methods", "")))
    for axes, method in re.findall(r"((?:[^\s:()]+\s*:\s*)+)(\w+)", methods):
        if set(axis.strip() for axis in axes.split(":") if axis.strip()) & set(temporal_names):
            temporal.append(kinds.get(method, method))
    facts = {value for value in temporal if value is not None}
    if len(facts) > 1:
        raise ValueError(f"{context}: contradictory source temporal metadata {sorted(facts)}")
    if facts:
        attrs["temporal_kind"] = next(iter(facts))
        origins["temporal_kind"] = "input"
    if attrs.keys() & {"flag_values", "flag_masks", "flag_meanings"}:
        if attrs.get("kind") not in {None, "categorical"}:
            raise ValueError(f"{context}: kind contradicts source categorical flags")
        attrs["kind"], origins["kind"] = "categorical", "input"
    for key, value in declaration.items():
        if key == "allow_unscaled":
            continue
        fact = attrs.get(key)
        equal = fact == value
        if key == "units" and fact:
            left, right = stored_unit_identity(fact), stored_unit_identity(value)
            equal = left == right or any(
                left in factors and right in factors and factors[left] == factors[right]
                for _, factors in UNITS.values())
        if key in origins and not equal:
            raise ValueError(f"{context}: declared {key} {value!r} contradicts input "
                             f"{fact!r}; no relabelling or implicit conversion")
        if key not in origins:
            attrs[key], origins[key] = value, "declaration"
    return {"attributes": attrs, "origins": origins}


def source_field_declaration(source, field, *, record=None):
    """Match declarations by actual identity, without converting or relabelling data."""
    declaration = source.get("declaration", {})
    name = field["name"]
    context = f"sources.{source.get('name', '<id>')}.field_metadata"
    declarations = declaration.get("field_metadata", {})
    metadata = declarations.get(name, {})
    if metadata and len({r["field_id"] for r in source["record_inventory"]
                         if r["name"] == name}) > 1:
        raise ValueError(f"{context}.{name}: ambiguous native name; "
                         "use an explicit vertical-group.field reference")
    groups = source.get("requests", {}).get("groups", {})
    if groups:
        group = native_field_group(source, field, record)
        qualified = declarations.get(f"{group}.{name}", {}) if group in groups else {}
        if metadata and qualified and metadata != qualified:
            raise ValueError(f"{context}.{group}.{name}: conflicting declarations")
        metadata = qualified or metadata
    return metadata


def source_field_metadata(source, field, *, record=None):
    """Resolve only this selected field's declaration and admitted SEA metadata."""
    declaration = source.get("declaration", {})
    name, attrs = field["name"], field["attributes"]
    if record is not None:
        attrs = record.get("observed_attributes", attrs)
    metadata = source_field_declaration(source, field, record=record)
    interpreted = False
    if declaration.get("interpretation") == "mesonh_surfex_sea":
        from frameit.io.surfex_utils import SURFEX_FIELDS, surfex_metadata

        if name in SURFEX_FIELDS:
            attrs = surfex_metadata(source, {**field, "attributes": attrs})
            interpreted = True
    if not metadata and not interpreted:
        return None
    temporal_names = {"time"}
    records = [record] if record is not None else source["record_inventory"]
    for sample in records:
        if sample["name"] == name:
            temporal_names.update(sample.get("temporal_names", [
                sample["clock"], *sample["locator"].get("coordinate_indexers", {})]))
    groups = source.get("requests", {}).get("groups", {})
    if groups:
        group = native_field_group(source, field, record)
        if f"{group}.{name}" in declaration.get("field_metadata", {}):
            name = f"{group}.{name}"
    result = resolve_field_metadata(
        attrs, metadata, f"sources.{source.get('name', '<id>')}.field_metadata.{name}",
        temporal_names=temporal_names)
    if interpreted:
        result["origins"]["units"] = attrs["surfex_units_source"]
    return result


def sea_interpretation(records):
    """Retain selected snapshot evidence separately from representative field metadata."""
    evidence = {}
    for record in records:
        metadata = record.get("field_metadata", {})
        if "surfex_units_source" not in metadata.get("attributes", {}):
            continue
        key = record["name"], record["time"], record["cycle"], record["locator"]["path"]
        evidence[key] = {
            "field": record["name"], "source_id": Path(record["locator"]["path"]).name,
            "time": str(record["time"]), "cycle": (
                str(record["cycle"]) if record["cycle"] is not None else None),
            "clock": record["clock"],
            "observed_attributes": {
                name: value.tolist() if isinstance(value, (np.ndarray, np.generic)) else value
                for name, value in record["observed_attributes"].items()},
            "units": metadata["attributes"]["units"], "origins": dict(metadata["origins"])}
    fields = sorted({entry["field"] for entry in evidence.values()})
    return {
        "method": "mesonh_surfex_sea", "fields": fields,
        "pending_value_checks": ["selected FRAC_SEA physical support finite within [0,1]"]
        if fields else [],
        **({"metadata_records": list(evidence.values())} if evidence else {})}


def _sample_context(record):
    return record["time"], record["cycle"], tuple(sorted(record.get("native_axes", {}).items()))


def _operation_units(value, target, *, model=None):
    """Use the admitted scale conversions, never case-fold an unknown symbol."""
    source = value.attrs.get("units")
    if source == target and source:
        return value.copy(deep=False)
    if model == "croco":
        from frameit.io.croco_utils import _velocity

        if source in {"meter second-1", "metre second-1"}:
            value = _velocity(value)
            source = value.attrs["units"]
        if target in {"meter second-1", "metre second-1"}:
            return _operation_units(value, "m s-1").assign_attrs(
                {**value.attrs, "units": target})
    quantity = next((q for q, (_, factors) in UNITS.items()
                     if unit_key(source) in factors and unit_key(target) in factors), None)
    if quantity is None:
        raise ValueError(
            f"{value.name}: incompatible or unsupported units {source!r} -> {target!r}")
    return convert_units(value, quantity, target=target)


def _merge_operation_dependencies(source, binding, addition):
    """Union genuine native read bindings, without changing any product selector."""
    by_name = {}
    for i, record in enumerate(source["record_inventory"]):
        by_name.setdefault(record["name"], []).append((i, record))
    for name, descriptor in addition["dependencies"].items():
        if name not in binding["dependencies"]:
            binding["dependencies"][name] = deepcopy(descriptor)
            continue
        target = binding["dependencies"][name]
        if target["field_id"] != descriptor["field_id"]:
            raise ValueError(f"{name}: operation inputs resolve to conflicting field identities")
        for record in descriptor["records"]:
            previous = next((r for r in target["records"] if
                             _sample_context(r) == _sample_context(record)
                             and r["locator"] == record["locator"]), None)
            if previous is None:
                target["records"].append(deepcopy(record))
            elif record["vertical"] is not None:
                positions = sorted(
                    set(previous["source_positions"]) | set(record["source_positions"]))
                axis = _field_axis(source, source["fields"][record["field_id"]], record, by_name)
                previous["source_positions"] = positions
                previous["vertical"] = _bind_vertical(
                    axis, {"indices": axis["native"][positions].tolist()},
                    f"internal.{name}", binding["warnings"])
    for record in addition["records"]:
        if not any(r["field_id"] == record["field_id"] and r["locator"] == record["locator"]
                   and _sample_context(r) == _sample_context(record) for r in binding["records"]):
            binding["records"].append(deepcopy(record))
    binding["warnings"].extend(addition["warnings"])
    binding["deferred_checks"].extend(addition["deferred_checks"])
    if "interpretation" in addition:
        combined = binding.setdefault("interpretation", deepcopy(addition["interpretation"]))
        if "fields" in combined:
            combined["fields"] = sorted(
                set(combined["fields"]) | set(addition["interpretation"]["fields"]))
        if addition["interpretation"].get("metadata_records"):
            evidence = combined.setdefault("metadata_records", [])
            for record in addition["interpretation"]["metadata_records"]:
                if record not in evidence:
                    evidence.append(deepcopy(record))


def _operation_geometry(source, records, operation, conf):
    """Read only selected-sample coordinates and required admitted rotation geometry."""
    from frameit.io.loader import DatasetResources

    coordinates, attributes = {}, {}
    for record in (sequence[0] for sequence in records.values()):
        grid = source["native_grids"][record["grid_id"]]
        for name, descriptor in grid["coordinates"].items():
            value = xr.DataArray(xr.Variable(
                descriptor["dimensions"], descriptor["values"], descriptor["attributes"]))
            indexers = record["locator"].get("coordinate_indexers", {})
            value = value.isel({dim: i for dim, i in indexers.items() if dim in value.dims},
                               drop=True)
            if name in coordinates and not coordinates[name].identical(value):
                raise ValueError(f"{name}: conflicting operation coordinate geometry")
            coordinates[name] = value
        attributes.update(grid.get("fa_geometry", {}))
    if source["format"] == "netcdf" and (
            operation["sampling"] == "mass" or operation["basis"] == "earth"):
        pairs = source["declaration"].get("wind_pairs", [])
        rotations = [p.get("rotation", {}) for p in pairs
                     if set(records) & {p["u"], p["v"]}]
        names = {conf.name_lon_dim, conf.name_lat_dim, conf.name_vertical_dim,
                 conf.name_latitude, conf.name_longitude, "BETA", "RPK", "LON0", "CARTESIAN"}
        names.update(f"{dim}_source_native_index" for dim in (
            conf.name_lon_dim, conf.name_lat_dim, conf.name_vertical_dim))
        if source["model"] == "croco":
            names.update(("xi_rho", "eta_rho", "lat_rho", "lon_rho", "angle"))
        names.update(r["coordinate"] for r in rotations if r.get("coordinate"))
        with DatasetResources() as resources:
            for record in (sequence[0] for sequence in records.values()):
                original = resources.open_netcdf(
                    record["locator"]["path"], engine=conf.netcdf_engine, chunks=None)
                for key in ("BETA", "RPK", "LON0", "CARTESIAN", "wind_reference_frame",
                            "GRIB_uvRelativeToGrid", "uvRelativeToGrid", "CPP-options"):
                    if key in original.attrs:
                        if key in attributes and attributes[key] != original.attrs[key]:
                            raise ValueError(f"{key}: conflicting selected operation geometry")
                        attributes[key] = original.attrs[key]
                for name in names & set(original.variables):
                    value = original[name]
                    if name in {"BETA", "RPK", "LON0", "CARTESIAN"} and value.size != 1:
                        raise ValueError(f"{name}: rotation geometry must be scalar")
                    if name in {r.get("coordinate") for r in rotations}:
                        convert_units(xr.DataArray(0., attrs=value.attrs, name=name), "angle")
                    if value.attrs.keys() & {"flag_values", "flag_masks", "flag_meanings"}:
                        raise ValueError(
                            f"{name}: categorical data cannot supply rotation geometry")
                    indexers = record["locator"]["coordinate_indexers"]
                    selected = value.isel({dim: i for dim, i in indexers.items()
                                           if dim in value.dims}, drop=True)
                    selected = xr.DataArray(
                        np.asarray(selected.values), dims=selected.dims, attrs=dict(selected.attrs))
                    if name in coordinates and not coordinates[name].variable.equals(
                            selected.variable):
                        raise ValueError(
                            f"{name}: conflicting selected operation coordinate geometry")
                    coordinates[name] = selected
    geometry = xr.Dataset(coords=coordinates, attrs=attributes)
    if source["format"] == "grib":
        grid = source["native_grids"][next(iter(records.values()))[0]["grid_id"]]
        if grid.get("grid_type") == "regular_ll":
            lat, lon = geometry.latitude.values, geometry.longitude.values
            if np.array_equal(lat, np.broadcast_to(lat[:, :1], lat.shape)) and np.array_equal(
                    lon, np.broadcast_to(lon[:1], lon.shape)):
                geometry = geometry.assign_coords(
                    y=("y", lat[:, 0]), x=("x", lon[0]))
    return geometry


def _grid_from_geometry(geometry, dimensions, *, rotation_coordinate=None):
    coords = {}
    bounds = {value.attrs.get("bounds") for value in geometry.coords.values()
              if set(value.dims) <= set(dimensions)}
    for name, value in geometry.coords.items():
        if (set(value.dims) <= set(dimensions) or name in bounds) and name not in {
                "BETA", "RPK", "LON0", "CARTESIAN", rotation_coordinate}:
            coords[name] = {"dimensions": list(value.dims), "values": np.asarray(value.values),
                           "attributes": deepcopy(value.attrs), "dtype": str(value.dtype),
                           "role": "coordinate_metadata"}
    return {"dimensions": dict(dimensions), "coordinates": coords, "grid_mapping": None}


def bind_source_operations(source, request, conf, *, representations=None, required_inputs=()):
    """Bind explicit result preparation separately from native exports and trackers.

    Every operation's input binding is produced by ``bind_requests`` on actual
    selected records. Result coordinates are bound on the actual preparation grid.
    No polar target or unrelated pending method is granted execution clearance.
    """
    from copy import copy

    import dask.array as da

    from frameit.core.preflight import _metadata_id
    from frameit.processing.derived.wind import align_wind_pair
    from frameit.processing.wind_collocation import collocate_mnh_component, staggered_support
    from frameit.processing.wind_reference import _metadata_frames, operation_pair

    exports = request["exports"]
    active = {}
    for product, names in exports.items():
        for name in names:
            if name in request["derived"]:
                sampling = "mass" if source["model"] == "mesonh" else "native"
                input_sampling = {}
                if product == "polar":
                    input_sampling = {
                        field: request["polar_options"].get(field, {}).get("sampling", sampling)
                        for field in request["derived"][name]["inputs"].values()}
                    sampling = "mass" if "mass" in input_sampling.values() else "native"
                active[product, name] = {
                    "method": request["derived"][name]["method"],
                    "inputs": request["derived"][name]["inputs"],
                    "sampling": sampling,
                    **({"input_sampling": input_sampling} if input_sampling else {}),
                    "basis": "earth", "units": "m s-1"}
            elif product == "model_grid":
                transforms = [t for t in request["transforms"] if name in t["fields"]]
                if len(transforms) > 1:
                    raise ValueError(f"model_grid.{name}: overlapping transforms are unsupported")
                if transforms:
                    active[product, name] = {
                        "method": "transform", "inputs": {"field": name},
                        "sampling": "native", "basis": "native",
                        **{k: v for k, v in transforms[0].items() if k != "fields"}}
            elif product == "polar":
                active[product, name] = {
                    "method": "polar_input", "inputs": {"field": name},
                    "sampling": request["polar_options"].get(name, {}).get("sampling", "native"),
                    "basis": request["polar_options"].get(name, {}).get("basis", "native"),
                    **{key: value for key, value in request["polar_options"].get(name, {}).items()
                       if key == "units"}}
    native = deepcopy(request)
    native["exports"] = {p: [n for n in names if (p, n) not in active]
                         for p, names in exports.items()}
    native["exports"] = {p: names for p, names in native["exports"].items() if names}
    native["transforms"] = []
    native["internal_inputs"] = []
    remaining = [p for p in source.get("pending_operations", [])
                 if p not in {"transforms", "derived", "polar"}]
    native_source = {**source, "pending_operations": remaining,
                     "dependency_resolution": "pending_method_binding" if remaining else "declared"}
    binding = (bind_requests(native_source, native, representations=representations,
                             required_inputs=required_inputs)
               if (native["exports"] or required_inputs
                   or not active and conf.yaml_config["products"]) else
               {"status": "bound", "products": {}, "dependencies": {}, "records": [],
                "warnings": [], "deferred_checks": []})
    binding["operations"] = []
    binding["operation_plans"] = []
    binding["representation_grids"] = {}
    pool = source["record_inventory"]
    all_by_name = {}
    for i, record in enumerate(pool):
        all_by_name.setdefault(record["name"], []).append((i, record))
    for (product, name), operation in active.items():
        wind = operation["method"] in {"wind_speed", "radial_wind", "tangential_wind"}
        loc = f"sources.{source['name']}.derived.{name}" if wind else name
        if wind and any(r["name"] == name for r in pool):
            raise ValueError(f"{loc}: result name collides with a source field")
        if wind and source["physical_type"] != "atmosphere":
            raise ValueError(f"{loc}: {operation['method']} admits atmospheric winds only")
        if operation["method"] in {"radial_wind", "tangential_wind"}:
            if product != "polar" or source["format"] not in {"grib", "netcdf"}:
                raise ValueError(
                    f"{loc}: {operation['method']} requires products.polar.fields and "
                    "AROME GRIB/NetCDF or Meso-NH NetCDF, not FA")
        inputs = dict(operation["inputs"])
        if operation["method"] in {"transform", "polar_input"} and operation["basis"] == "earth":
            declarations = [p for p in source["declaration"].get("wind_pairs", [])
                            if name in (p["u"], p["v"])]
            evidence = [r for _, r in field_candidates(source, request, name, all_by_name)]
            frames = set().union(*(
                set(_metadata_frames(source["fields"][r["field_id"]]["attributes"], name))
                for r in evidence))
            if declarations:
                inputs.update(u=declarations[0]["u"], v=declarations[0]["v"])
            elif frames != {"earth"}:
                raise ValueError(
                    f"{name}: Earth basis requires an unambiguous wind_pairs declaration")
        croco = source["model"] == "croco" and operation["sampling"] == "mass"
        if source["model"] == "croco" and product == "polar":
            inputs["mask_rho"] = "mask_rho"
        if croco:
            for mask in ("mask_rho", "mask_u", "mask_v"):
                if mask == "mask_rho" or any(r["name"] == mask for r in pool):
                    inputs[mask] = mask
        by_name = {n: field_candidates(source, request, n, all_by_name) for n in inputs.values()}
        for field_name, candidates in by_name.items():
            if len({r["field_id"] for _, r in candidates}) != 1:
                raise ValueError(
                    f"{loc}: input {field_name} missing or ambiguous in selected inventory")
        if croco:
            native_pair = tuple(source["fields"][by_name[inputs[component]][0][1]["field_id"]][
                "name"] if component in inputs else None for component in ("u", "v"))
            if operation["basis"] != "earth" or native_pair not in {("u", "v"), ("ubar", "vbar")}:
                raise ValueError(
                    "CROCO current transforms require admitted U/V mass/Earth preparation")
            declared = next(p for p in source["declaration"]["wind_pairs"]
                            if (p["u"], p["v"]) == (inputs["u"], inputs["v"]))
            rotation = declared.get("rotation", {"method": "coordinate", "coordinate": "angle"})
            if declared["basis"] != "grid" or rotation != {
                    "method": "coordinate", "coordinate": "angle"}:
                raise ValueError("CROCO native currents require grid basis and rho angle rotation")
        contexts = {_sample_context(r) for _, r in by_name[next(iter(inputs.values()))]}
        output = {"operation": name, "method": operation["method"], "records": [], "category": None}
        if product == "polar":
            output.update(execution="pending_polar_sampling",
                          magnitude_order="after_sampling_components" if (
                              operation["method"] == "wind_speed") else "not_applicable")
        binding["products"].setdefault(product, {})[name] = output
        for context in sorted(contexts, key=str):
            records = {n: [r for _, r in candidates if _sample_context(r) == context]
                       for n, candidates in by_name.items()}
            if any(not sequence for sequence in records.values()):
                raise ValueError(f"{name}: missing input support at selected time/cycle {context}")
            geometry = _operation_geometry(source, records, operation, conf)
            attrs, axes, grids, probes = {}, {}, {}, {}
            for field_name, sequence in records.items():
                record = sequence[0]
                field = source["fields"][record["field_id"]]
                metadata = record.get("field_metadata") or source_field_metadata(
                    source, field, record=record)
                attrs[field_name] = deepcopy(
                    metadata["attributes"] if metadata else field["attributes"])
                if source["model"] == "nemo" and product == "polar":
                    from frameit.io.nemo_utils import COMPONENT_STANDARD_NAMES, NATIVE_COMPONENTS

                    if field["name"] in NATIVE_COMPONENTS or (
                            attrs[field_name].get("standard_name") in COMPONENT_STANDARD_NAMES):
                        raise ValueError(
                            "NEMO polar component analysis is unqualified; "
                            "native extraction remains available")
                if field.get("native_cube", {}).get("vector_basis"):
                    attrs[field_name]["wind_reference_frame"] = field["native_cube"]["vector_basis"]
                axes[field_name] = _field_axis(source, field, record, all_by_name)
                grids[field_name] = (axes[field_name]["grid"] if axes[field_name] else
                                     source["native_grids"][record["grid_id"]])
                if axes[field_name]:
                    for n, c in grids[field_name]["coordinates"].items():
                        if n not in geometry:
                            geometry = geometry.assign_coords({n: xr.Variable(
                                c["dimensions"], c["values"], c["attributes"])})
                coords = dict(geometry.coords)
                dims = tuple(grids[field_name]["dimensions"])
                probes[field_name] = xr.DataArray(
                    da.zeros(tuple(grids[field_name]["dimensions"].values()), chunks="auto"),
                    dims=dims, coords={n: c for n, c in coords.items() if set(c.dims) <= set(dims)},
                    attrs=attrs[field_name], name=field_name)
                if operation.get("units") and field_name not in {"mask_rho", "mask_u", "mask_v"}:
                    _operation_units(xr.DataArray(0., attrs=attrs[field_name], name=field_name),
                                     operation["units"], model=source["model"])
            if wind:
                selectors = [field_selection(request, field_name)[2]
                             for field_name, axis in axes.items() if axis is not None]
                if selectors and any(selector != selectors[0] for selector in selectors[1:]):
                    raise ValueError(
                        f"{name}: 3d derived inputs prescribe different level selectors; "
                        "use one common selector in their source groups")
            prepared = dict(probes)
            if croco:
                from frameit.io.croco_utils import _validate_faces, _velocity

                headers = xr.Dataset(probes).assign_coords(geometry.coords)
                _validate_faces(headers, (inputs["u"], inputs["v"]))
                for component, direction, horizontal in (
                        (inputs["u"], "x", {"eta_rho", "xi_u"}),
                        (inputs["v"], "y", {"eta_v", "xi_rho"})):
                    try:
                        _velocity(xr.DataArray(0., attrs=attrs[component], name=component))
                    except ValueError as error:
                        raise ValueError(f"CROCO current analysis: {error}") from error
                    field = source["fields"][records[component][0]["field_id"]]
                    native_component = field["name"]
                    prefix = "barotropic_" if native_component in {"ubar", "vbar"} else ""
                    standard = f"{prefix}sea_water_{direction}_velocity"
                    location = "u" if direction == "x" else "v"
                    if attrs[component].get("standard_name") not in {
                            None, standard, f"{standard}_at_{location}_location"}:
                        raise ValueError(f"CROCO {component}: conflicting current quantity")
                    expected = horizontal | (
                        {"s_rho"} if native_component in {"u", "v"} else set())
                    if set(probes[component].dims) != expected or not field["time_varying"]:
                        raise ValueError(f"CROCO {component}: incompatible current dimensions")
                if any(attrs[inputs["u"]].get(key) != attrs[inputs["v"]].get(key)
                       for key in ("cell_methods", "online_operation",
                                   "interval_operation", "interval_write")):
                    raise ValueError("CROCO current companions have incompatible statistics")
                if "MASKING" not in str(geometry.attrs.get("CPP-options", "")).split() or (
                        "WET_DRY" in str(geometry.attrs.get("CPP-options", "")).split()):
                    raise ValueError(
                        "CROCO current analysis requires static MASKING without WET_DRY")
                mask_attrs = attrs["mask_rho"]
                if (mask_attrs.get("option_0") != "land" or mask_attrs.get("option_1") != "water"
                        or probes["mask_rho"].dims != ("eta_rho", "xi_rho")):
                    raise ValueError("CROCO mask_rho requires explicit static land/water support")
                if "angle" not in geometry or geometry.angle.dims != ("eta_rho", "xi_rho"):
                    raise ValueError("CROCO current analysis requires rho-point angle")
                convert_units(geometry.angle, "angle")
                if not np.isfinite(geometry.angle.values).all():
                    raise ValueError("CROCO rho-point angle must be finite")
                for field_name in (inputs["u"], inputs["v"]):
                    dims = tuple({"xi_u": "xi_rho", "eta_v": "eta_rho"}.get(d, d)
                                 for d in probes[field_name].dims)
                    prepared[field_name] = xr.DataArray(
                        da.zeros(tuple(geometry.sizes[d] for d in dims), chunks="auto"),
                        dims=dims, coords={d: geometry[d] for d in dims if d in geometry},
                        attrs=attrs[field_name], name=field_name)
            elif operation["sampling"] == "mass":
                if source["model"] != "mesonh":
                    raise ValueError(
                        f"{name}: mass sampling is unsupported for this model/quantity")
                for field_name, value in probes.items():
                    if operation.get("input_sampling", {}).get(
                            field_name, operation["sampling"]) != "mass":
                        prepared[field_name] = value.reset_coords(drop=True)
                        continue
                    vertical_w = "level_w" in value.dims
                    native_name = source["fields"][records[field_name][0]["field_id"]]["name"]
                    if vertical_w and native_name != getattr(
                            conf, "velocity_aliases", {}).get("w_velocity", "WT") and (
                            value.attrs.get("standard_name") not in {
                                "upward_air_velocity", "lagrangian_tendency_of_air_pressure"}):
                        raise ValueError(
                            f"{field_name}: only admitted W quantities support mass remapping")
                    prepared[field_name] = collocate_mnh_component(
                        value.reset_coords(drop=True), geometry, conf, vertical=vertical_w)
            pair = None
            if "u" in inputs and "v" in inputs and not croco:
                u, v = inputs["u"], inputs["v"]
                align_wind_pair(prepared[u], prepared[v])
                for field_name in (u, v):
                    _operation_units(xr.DataArray(0., attrs=attrs[field_name], name=field_name),
                                     "m s-1")
                if any(records[u][0].get(key) != records[v][0].get(key)
                       for key in ("time_bounds", "temporal_metadata", "calendar")):
                    raise ValueError(f"{name}: wind inputs have incompatible temporal definitions")
                headers = xr.Dataset({n: prepared[n] for n in (u, v)}).assign_coords(
                    geometry.coords)
                headers.attrs = dict(geometry.attrs)
                rotation_settings = copy(conf)
                if source["format"] == "grib":
                    rotation_settings.name_lat_dim, rotation_settings.name_lon_dim = "y", "x"
                pair = operation_pair(headers, source, (u, v), rotation_settings)
            anchor = next(iter(inputs.values()))
            result = prepared[anchor]
            result_geometry = geometry.assign_coords({
                dim: result[dim] for dim in result.dims if dim in result.coords})
            coordinate = ("angle" if croco else
                          ((pair or {}).get("rotation") or {}).get("coordinate"))
            destination = _grid_from_geometry(
                result_geometry, result.sizes, rotation_coordinate=coordinate)
            grid_id = (records[anchor][0]["grid_id"]
                       if operation["sampling"] == "native" else _metadata_id("grid_", destination))
            axis = _vertical_axis(
                {"name": name, "dimensions": list(result.dims)}, destination)
            category = "3d" if axis else "2d"
            output.update(field_id=records[anchor][0]["field_id"], category=category)
            local_pool = [r for r in pool if _sample_context(r) == context]
            local = {**source, "record_inventory": local_pool,
                     "records": local_pool, "selected_times": [context[0]],
                     "pending_operations": [], "dependency_resolution": "declared"}
            anchor_axis = axes[anchor]
            source_positions = {}
            if axis is not None and anchor_axis is not None:
                source_positions = (
                    {i: [i] for i in range(axis["size"])}
                    if axis["dimension"] == anchor_axis["dimension"] else
                    staggered_support(geometry[anchor_axis["dimension"]],
                                      result_geometry[axis["dimension"]]))
            representation = {
                "grid_id": grid_id, "grid": destination, "sampling": operation["sampling"],
                "source_positions": source_positions}
            result_request = {
                **native, "fields": {key: [anchor] if key == category else []
                                    for key in ("2d", "3d")},
                "exports": {product: [anchor]}, "derived": {}, "internal_inputs": [],
                "transforms": [{"fields": [anchor], "sampling": operation["sampling"]}],
                "polar_options": {anchor: {"sampling": operation["sampling"]}},
            }
            result_binding = bind_requests(
                local, result_request, representations={
                    product: {anchor: {records[anchor][0]["grid_id"]: representation}}})
            bound_result = result_binding["products"][product][anchor]
            if not bound_result["records"]:
                raise ValueError(
                    f"{name}: result representation support remains pending method binding")
            selected = bound_result["records"][0]["vertical"]
            binding["warnings"].extend(result_binding["warnings"])
            binding["deferred_checks"].extend(result_binding["deferred_checks"])
            selectors = {}
            for field_name, native_axis in axes.items():
                if native_axis is None:
                    selectors[field_name] = {}
                    continue
                if axis is None:
                    raise ValueError(f"{name}: operation must preserve the input field category")
                if native_axis["dimension"] == axis["dimension"]:
                    positions = selected["positions"]
                else:
                    target = result_geometry[axis["dimension"]].isel(
                        {axis["dimension"]: selected["positions"]})
                    support_map = staggered_support(
                        geometry[native_axis["dimension"]], target)
                    if any(not support for support in support_map.values()):
                        raise ValueError(
                            f"{name}: source support unavailable for selected mass levels")
                    positions = sorted({i for support in support_map.values() for i in support})
                selectors[field_name] = {"indices": native_axis["native"][positions].tolist()}
            subrequest = {**native, "fields": {key: [n for n in dict.fromkeys(inputs.values())
                                                   if n in request["fields"][key]]
                                             for key in ("2d", "3d")},
                          "exports": {}, "internal_inputs": list(dict.fromkeys(inputs.values())),
                          "derived": {}, "levels": {}}
            support = bind_requests(local, subrequest, required_inputs=selectors)
            _merge_operation_dependencies(source, binding, support)
            output["records"].extend(deepcopy(bound_result["records"]))
            binding["representation_grids"][grid_id] = destination
            planned = {
                **deepcopy(operation), "name": name, "product": product,
                "inputs": inputs, "input_binding": support, "pair": pair,
                "vertical": selected, "grid_id": grid_id,
                "grid": destination, "geometry": {
                    "coordinates": {
                        n: {"dimensions": list(c.dims), "values": np.asarray(c.values),
                            "attributes": dict(c.attrs)} for n, c in geometry.coords.items()},
                    "attributes": dict(geometry.attrs)},
                "context": context, "model": source["model"], "preparation": (
                    "croco_midpoint_both_valid_then_rho_angle" if croco else
                    "native_coordinate_linear_strict_then_earth_preparation" if pair
                    and operation["sampling"] == "mass" else
                    "native_coordinate_linear_strict" if operation["sampling"] == "mass" else
                    "native_collocated_components" if pair else "native_samples"),
                "rotation_coordinate": {
                    "name": coordinate, "dimensions": list(geometry[coordinate].dims),
                    "values": np.asarray(geometry[coordinate].values).tolist(),
                    "attributes": {
                        key: value.tolist() if isinstance(value, (np.ndarray, np.generic))
                        else deepcopy(value)
                        for key, value in geometry[coordinate].attrs.items()}
                } if coordinate else None,
            }
            planned["result_units"] = operation.get("units", attrs[anchor].get("units"))
            output["result_units"] = planned["result_units"]
            output.setdefault("representations", []).append({
                "time": context[0], "cycle": context[1], "grid_id": grid_id,
                "units": planned["result_units"], "preparation": planned["preparation"],
                "sampling": operation["sampling"], "basis": operation["basis"],
                "levels": {key: selected[key] for key in (
                    "dimension", "source_native_indices", "values", "units", "units_origin")}
                if selected else None})
            binding["operation_plans"].append(planned)
            if product == "model_grid":
                binding["operations"].append(planned)
    if request.get("groups"):
        from frameit.io.netcdf_export import _output_grid_facts, output_grid_layout

        layout = output_grid_layout({
            **source, "representation_grids": binding["representation_grids"],
            "requests": {**request, "binding": binding}})
        selections = {}
        for product, fields in binding["products"].items():
            for name, descriptor in fields.items():
                for record in descriptor["records"]:
                    vertical = record.get("vertical")
                    if vertical is None:
                        continue
                    facts = _output_grid_facts(layout, record["selection_grid_id"], name)
                    axis = facts["dimensions"][vertical["dimension"]]
                    key = product, axis, _sample_context(record)
                    coordinates = {k: vertical[k] for k in (
                        "values", "source_native_indices", "units")}
                    previous = selections.setdefault(key, (name, coordinates))
                    if previous[1] != coordinates:
                        raise ValueError(
                            f"{product}.{name}: different group level selections target the same "
                            f"output axis {axis} as {previous[0]}; "
                            "use matching selections on that destination grid or separate runs")
    if "polar" in exports:
        from frameit.processing.polar.sampling import bind_polar_plan

        bind_polar_plan(source, request, binding, conf)
    binding["warnings"] = list(dict.fromkeys(binding["warnings"]))
    binding["deferred_checks"] = list(dict.fromkeys(binding["deferred_checks"]))
    binding["status"] = (
        "pending_method_binding" if binding["deferred_checks"] else
        "pending_polar_target" if binding.get("polar_plan", {}).get("status") == "prepared" else
        "bound")
    return binding


def initial_gap_times(source, name, records):
    """Permit only an explicitly declared whole-field initial absence on a proven grid."""
    times = source["selected_times"]
    missing = set(times) - {record["time"] for record in records}
    if (not times or missing != {min(times)} or not records
            or name not in source.get("declaration", {}).get("allow_initial_gaps", [])
            or source.get("format") not in {"grib", "netcdf"}):
        return set()
    grids = {record["grid_id"] for record in records}
    support = [record for record in source["records"]
               if record["time"] == min(times) and record["grid_id"] in grids]
    if len(grids) == 1 and not support and source["format"] == "grib":
        from frameit.core.preflight import _metadata_id

        field = source["fields"][records[0]["field_id"]]
        axis = _field_axis(source, field, records[0], {field["name"]: list(enumerate(records))})
        if axis is None:
            # A surface parameter's GRIB level type is identity, not horizontal geometry.
            horizontal = {
                key: _metadata_id("horizontal_", {k: v for k, v in grid.items()
                                                  if k != "vertical_group"})
                for key, grid in source["native_grids"].items()}
            target = horizontal[records[0]["grid_id"]]
            support = [record for record in source["records"] if record["time"] == min(times)
                       and horizontal[record["grid_id"]] == target]
    axes = {tuple(sorted(record.get("native_axes", {}).items())) for record in records}
    proven_axes = {tuple(sorted(record.get("native_axes", {}).items())) for record in support}
    if len(grids) != 1 or not axes <= proven_axes:
        raise ValueError(f"{name}: initial absence requires a proven unchanged native grid")
    return missing


def align_initial_gap(dataset, name, source):
    """Align declared missing output only; never create physical input records."""
    gaps = [gap for gap in source.get("allowed_gaps", []) if gap["field"] == name]
    if not source.get("allowed_gaps"):
        return dataset
    if gaps and dataset.time.dims != ("time",):
        raise ValueError(f"{name}: initial absence requires a one-dimensional output clock")
    result = dataset
    if gaps:
        times = source["selected_times"]
        missing = set(times) - set(dataset.time.values)
        if missing != {gap["time"] for gap in gaps}:
            raise ValueError(f"{name}: output absence differs from its bound initial-gap contract")
        if "time" not in dataset[name].dims:
            result = dataset.assign({name: dataset[name].expand_dims(time=dataset.time)})
        result = _initial_gap_clock(result.reindex(time=times), source)
        result[name].attrs["frameit_initial_absence"] = str(gaps[0]["time"])
    # Temporal evidence belongs to a field, not to a missing neighbour's record.
    names = {key: f"{name}_{key}" for key, value in result.coords.items()
             if key.startswith("GRIB_") and "time" in value.dims}
    bounds = result.time.attrs.get("bounds")
    if bounds in result:
        owned = f"{name}_time"
        names[bounds] = f"{name}_{bounds}"
        result = result.assign_coords({owned: result.time.variable.copy(deep=False)})
        result[owned].attrs = {**result.time.attrs, "bounds": names[bounds]}
        result.time.attrs = {key: value for key, value in result.time.attrs.items()
                             if key != "bounds"}
    return result.rename(names)


def _initial_gap_clock(dataset, source):
    """Restore only shared clocks from actual records, never interval evidence."""
    result = dataset
    times = dataset.time.values
    # Reference clocks come from actual selected source records, not the absent field.
    cycles = {time: {r["cycle"] for r in source["records"] if r["time"] == time}
              for time in times}
    for coordinate in ("forecast_reference_time", "step"):
        if coordinate in result and result[coordinate].dims == ("time",):
            if any(len(values) != 1 or None in values for values in cycles.values()):
                raise ValueError("Initial absence has ambiguous source reference clocks")
            references = np.array([next(iter(cycles[time])) for time in times])
            values = references if coordinate == "forecast_reference_time" else (
                np.asarray(times) - references)
            result = result.assign_coords({
                coordinate: ("time", values, dataset[coordinate].attrs)})
    return result


def bind_requests(source, request, *, representations=None, required_inputs=()):
    """Bind v3 declarations using only a closed, metadata-only record inventory.

    Representation fixtures/planners supply destination grids and per-destination
    source positions. This function neither performs transforms nor resolves methods.
    Existing numerical group requests use the separate, unchanged helpers above.
    """
    context = f"sources.{source.get('name', 'source')}"
    pool = source.get("record_inventory")
    if pool is None:
        raise ValueError(f"{context}: inventory sources before binding fields")
    records_by_name = {}
    for index, record in enumerate(pool):
        records_by_name.setdefault(record["name"], []).append((index, record))
    representations = representations or {}
    binding = {"status": "bound", "products": {}, "dependencies": {}, "records": [],
               "warnings": [], "deferred_checks": []}
    declared = {}
    for category, names in request["fields"].items():
        for name in names:
            if name in declared:
                raise ValueError(f"{context}: duplicate field request by identity: {name}")
            declared[name] = category
    method_selectors = required_inputs if isinstance(required_inputs, dict) else {}
    method_inputs = required_inputs if isinstance(required_inputs, dict) else {
        name: {} for name in required_inputs}
    needed = list(dict.fromkeys(
        [name for names in request["exports"].values() for name in names
         if name not in request["derived"]]
        + [name for name in request["internal_inputs"] if name not in request["derived"]]))
    generated = set(method_inputs) - declared.keys() - set(needed)
    needed = list(dict.fromkeys([*needed, *method_inputs]))
    resolved, pending = {}, list(needed)
    clocks = {(r["time"], r["cycle"]) for r in source["records"]}
    while pending:
        name = pending.pop(0)
        if name in resolved:
            continue
        candidates = field_candidates(source, request, name, records_by_name)
        group = source.get("tracker_input_groups", {}).get(name) if name in generated else None
        if group:
            candidates = [(i, r) for i, r in candidates
                          if native_field_group(source, source["fields"][r["field_id"]], r) == group]
        identities = {r["field_id"] for _, r in candidates}
        if not identities:
            raise ValueError(f"{context}: {name} unavailable in selected record inventory; "
                             "dependencies cannot widen files or times")
        if len(identities) > 1:
            definitions = [{"identity": identity, **{
                key: source["fields"][identity].get(key) for key in ("dimensions", "grid_ids")},
                "providers": sorted({r["locator"]["path"] for _, r in candidates
                                     if r["field_id"] == identity})}
                for identity in sorted(identities)]
            raise ValueError(f"{context}: distinct fields share requested name {name!r}; "
                             f"conflicting fields {definitions}; "
                              "use an explicit vertical group; qualification must identify "
                              "exactly one field")
        field_id = next(iter(identities))
        # Generated method support keeps its native key and independent selector.
        if any(field_id == value[0] and name not in generated and other not in generated
               for other, value in resolved.items()):
            raise ValueError(f"{context}: duplicate field request by resolved identity {field_id}")
        field = source["fields"][field_id]
        available = {(r["time"], r["cycle"], tuple(sorted(r.get("native_axes", {}).items())))
                     for _, r in candidates}
        axes = {entry[2] for entry in available}
        missing = {(time, cycle, axis) for time, cycle in clocks for axis in axes} - available
        allowed = (initial_gap_times(source, name, [r for _, r in candidates])
                   if name not in method_inputs else set())
        if ({entry for entry in missing if entry[0] not in allowed}
                or set(source["selected_times"]) - {r["time"] for _, r in candidates} - allowed):
            raise ValueError(f"{context}: {name} unavailable at selected times/cycles/native axes; "
                             f"missing support {sorted(missing, key=str)}")
        resolved[name] = field_id, field, candidates
        collisions = [dependency for dependency in field.get("dependencies", {})
                      if field_selection(request, dependency)[1] is not None]
        if collisions:
            raise ValueError(f"{context}: required native support names {collisions} collide "
                             "with qualified field references; use unambiguous flat requests "
                             "rather than replacing source support")
        pending.extend(field.get("dependencies", {}))

    for name, (_, field, candidates) in resolved.items():
        overlap = set(field.get("native_cube", {}).get("records", ())) & resolved.keys()
        if overlap:
            raise ValueError(f"{context}: repeated FA native records via cube {name}: "
                             f"{sorted(overlap)}")
        for dependency in field.get("dependencies", {}):
            for _, record in candidates:
                if not any(
                    other["time"] == record["time"] and other["cycle"] == record["cycle"]
                    and other.get("native_axes", {}) == record.get("native_axes", {})
                    for _, other in resolved[dependency][2]
                ):
                    raise ValueError(f"{context}: {name} dependency {dependency} native-axis "
                                     f"support unavailable at {record['time']}, "
                                     f"cycle {record['cycle']}, "
                                     f"native axes {record.get('native_axes', {})}")

    jobs, native_axes, axis_cache = [], {}, {}
    products = dict(request["exports"])
    ancillary_names = {name for _, field, _ in resolved.values()
                       for name in field.get("dependencies", {})}
    # Ancillary read support is separate even when that array is also exported.
    dependencies = [name for name in resolved
                    if name in ancillary_names or name in method_inputs or not any(
        name in names for names in request["exports"].values())]
    products["_dependencies"] = dependencies
    for product, names in products.items():
        target = binding["dependencies"] if product == "_dependencies" else (
            binding["products"].setdefault(product, {}))
        for name in names:
            if name in request["derived"]:
                binding["deferred_checks"].append(f"{name}: derived method representation/support "
                                                   "requires method binding.")
                continue
            field_id, field, candidates = resolved[name]
            descriptor = {"field_id": field_id, "category": None, "records": []}
            target[name] = descriptor
            for index, record in candidates:
                key = (field_id, record["grid_id"],
                       index if record["locator"]["format"] == "fa" else None)
                if key not in axis_cache:
                    axis_cache[key] = _field_axis(source, field, record, records_by_name)
                axis = axis_cache[key]
                category = "3d" if axis else "2d"
                descriptor["category"] = category
                if name in declared and declared[name] != category:
                    corrected = field["name"] if category == "2d" else name
                    raise ValueError(
                        f"{context}: {source['physical_type']} field {name!r} has category "
                        f"{category}; use corrected YAML: variables: {{{category}: [{corrected}]}}")
                _coordinate_support(source, field, record)
                if name != field["name"] and name in source["native_grids"][
                        record["grid_id"]]["coordinates"]:
                    raise ValueError(f"{context}: stored field name {name!r} collides "
                                     "with required native coordinates")
                native_axes[index] = axis
                transform = next((t for t in request["transforms"]
                                  if product == "model_grid" and name in t["fields"]), {})
                sampling = (request["polar_options"].get(name, {}).get("sampling", "native")
                            if product == "polar" else transform.get("sampling", "native"))
                representation = representations.get(product, {}).get(name, {}).get(
                    record["grid_id"])
                if sampling != "native" and representation is None:
                    binding["deferred_checks"].append(
                        f"{product}.{name}: destination grid/source support for {sampling} "
                        "sampling requires transform binding.")
                    continue
                if representation:
                    if representation["sampling"] != sampling:
                        raise ValueError(f"{product}.{name}: representation contradicts "
                                         f"requested {sampling} sampling")
                    axis = _vertical_axis(
                        {**field, "dimensions": list(representation["grid"]["dimensions"])},
                        representation["grid"])
                    if bool(axis) != bool(native_axes[index]):
                        raise ValueError(f"{product}.{name}: destination vertical axis must "
                                         "preserve the source field category")
                jobs.append((product, name, index, record, axis, representation, descriptor))

    selectors = {None: request["levels"], **{
        group: spec.get("levels", {}) for group, spec in request.get("groups", {}).items()}}
    for group, selector in selectors.items():
        if "values" in selector and "units" not in selector:
            units = {_unit_identity(axis["descriptor"]["attributes"]["units"])
                     for product, name, _, _, axis, _, _ in jobs
                     if axis and axis["descriptor"] and field_selection(request, name)[1] == group
                     and not (product == "_dependencies" and name in ancillary_names)
                     and unit_key(axis["descriptor"]["attributes"].get("units"))}
            if len(units) > 1:
                raise ValueError(
                    f"{context}: value selection across different known units requires "
                    "explicit variables.levels.units or group levels.units")
    chosen, required_levels, bound_jobs, vertical_cache = set(), {}, {}, {}
    for product, name, index, record, axis, representation, descriptor in jobs:
        ancillary = product == "_dependencies" and name in ancillary_names and axis is not None
        key = (product, name, record["grid_id"],
               index if record["locator"]["format"] == "fa" else None)
        if key not in vertical_cache:
            sample = (f" at {record['locator']['path']}, time {record['time']}, "
                      f"cycle {record['cycle']}" if record["locator"]["format"] == "fa" else "")
            selector = (method_selectors[name] if product == "_dependencies"
                        and name in method_selectors else field_selection(request, name)[2])
            vertical_cache[key] = _bind_vertical(
                axis, selector, f"{context}.{product}.{name}{sample}",
                binding["warnings"]) if axis and not ancillary else None
        vertical = vertical_cache[key]
        positions = vertical["positions"] if vertical else None
        support = [] if ancillary else positions
        if representation and positions is not None:
            support = []
            for position in positions:
                neighbours = representation["source_positions"].get(position, [])
                if not neighbours or any(isinstance(i, bool) or not isinstance(i, (int, np.integer))
                                         or i < 0 or native_axes[index] is None
                                         or i >= native_axes[index]["size"] for i in neighbours):
                    raise ValueError(f"{product}.{name}: source support unavailable for "
                                     f"destination index {position}")
                support.extend(i for i in neighbours if i not in support)
        if record["level"] is not None and native_axes[index] is not None and not ancillary:
            labels = np.asarray(native_axes[index]["descriptor"]["values"])[support].tolist()
            key = product, name
            required_levels.setdefault(key, set()).update(labels)
            if record["level"] not in labels:
                continue
        bound_record = {
            **deepcopy(record), "request_reference": name, "selection_grid_id": (
                representation["grid_id"] if representation else record["grid_id"]),
            "vertical": vertical, "source_positions": support,
        }
        field = resolved[name][1]
        if field.get("native_cube"):
            part_names = [field["native_cube"]["records"][i] for i in support]
            bound_record["locator"]["records"] = part_names
            for part_name in part_names:
                parts = [(i, r) for i, r in records_by_name[part_name]
                         if r["time"] == record["time"]
                         and r["cycle"] == record["cycle"]]
                identities = {r["field_id"] for _, r in parts}
                if len(identities) != 1:
                    raise ValueError(f"{context}: distinct fields share requested FA support name "
                                     f"{part_name}: {sorted(identities)}; "
                                     "qualified selectors are unsupported")
                chosen.update(i for i, _ in parts)
        descriptor["records"].append(bound_record)
        bound_jobs[product, index] = bound_record
        if not ancillary:
            chosen.add(index)
    pending_support = [(key, bound) for key, bound in bound_jobs.items()
                       if bound["source_positions"] != []]
    while pending_support:
        (product, index), bound = pending_support.pop(0)
        record, parent = pool[index], native_axes[index]
        field = source["fields"][record["field_id"]]
        for dependency in field.get("dependencies", {}):
            for other_index, other_record in resolved[dependency][2]:
                if (other_record["time"] != record["time"]
                        or other_record["cycle"] != record["cycle"]
                        or other_record.get("native_axes", {}) != record.get("native_axes", {})):
                    continue
                other = bound_jobs.get(("_dependencies", other_index))
                axis = native_axes.get(other_index)
                if other is None or axis is None:
                    continue
                support_context = f"{context}.{record['name']} dependency {dependency}"
                if parent is None or parent["dimension"] != axis["dimension"]:
                    binding["deferred_checks"].append(
                        f"{support_context}: native vertical support requires method binding "
                        "for different axes.")
                    continue
                indices = parent["native"][bound["source_positions"]].tolist()
                by_native = {int(value): i for i, value in enumerate(axis["native"])}
                missing = [i for i in indices if i not in by_native]
                if missing:
                    raise ValueError(f"{support_context}: vertical index support unavailable "
                                     f"for {missing}")
                needed_positions = [by_native[i] for i in indices]
                # Propagate only newly required native neighbours, including nested support.
                if set(needed_positions) - set(other["source_positions"]):
                    positions = list(dict.fromkeys(other["source_positions"] + needed_positions))
                    selector = {"indices": axis["native"][positions].tolist()}
                    units = field_selection(request, bound["request_reference"])[2].get("units")
                    if units:
                        selector["units"] = units
                    other["vertical"] = _bind_vertical(
                        axis, selector, f"{context}._dependencies.{dependency}",
                        binding["warnings"])
                    other["source_positions"] = positions
                    pending_support.append((("_dependencies", other_index), other))
                _array_vertical_support(
                    parent, bound["source_positions"], axis, other["source_positions"],
                    field_selection(request, bound["request_reference"])[2].get("units"),
                    support_context)
    for name in ancillary_names:
        records = []
        for (product, index), bound in bound_jobs.items():
            if product != "_dependencies" or pool[index]["name"] != name:
                continue
            axis = native_axes[index]
            if axis is not None:
                if not bound["source_positions"]:
                    binding["deferred_checks"].append(
                        f"{context}.{name}: native ancillary support at {bound['time']} "
                        "remains pending method binding.")
                    continue
                if bound["level"] is not None:
                    labels = np.asarray(axis["descriptor"]["values"])[
                        bound["source_positions"]].tolist()
                    required_levels.setdefault(("_dependencies", name), set()).update(labels)
                    if bound["level"] not in labels:
                        continue
            records.append(bound)
            chosen.add(index)
        binding["dependencies"][name]["records"] = records
    for (product, name), labels in required_levels.items():
        target = (binding["dependencies"] if product == "_dependencies"
                  else binding["products"][product])
        records = target[name]["records"]
        contexts = {(r["time"], r["cycle"], tuple(sorted(r.get("native_axes", {}).items())))
                    for _, r in resolved[name][2]}
        for time, cycle, axes in contexts:
            available = {r["level"] for r in records if r["time"] == time and r["cycle"] == cycle
                         and tuple(sorted(r.get("native_axes", {}).items())) == axes}
            if labels - available:
                raise ValueError(f"{context}: {name} unavailable levels "
                                 f"{sorted(labels - available)} "
                                 f"at selected time {time}, cycle {cycle}, native axes {axes}")
    providers = {}
    for index in sorted(chosen):
        record = pool[index]
        key = (record["field_id"], record["time"], record["cycle"], record["level"],
               tuple(sorted(record.get("native_axes", {}).items())))
        if key in providers:
            raise ValueError(f"{context}: competing physical-field providers for {record['name']} "
                             f"at {record['time']}, cycle {record['cycle']}, "
                             f"level {record['level']}, "
                             f"native axes {record.get('native_axes', {})}: "
                             f"{providers[key]} and {record['locator']}. "
                             "Use files, exclude or time.cycle; if whole-file exclusion loses "
                             "needed records, make inputs unambiguous upstream.")
        providers[key] = record["locator"]
    binding["records"] = sorted(
        (pool[i] for i in chosen),
        key=lambda r: (r["time"], r["name"], r["field_id"], str(r["level"])))
    if not needed:
        binding["deferred_checks"].append("No fields are requested; finish source/method requests "
                                           "before execution.")
    declaration = source.get("declaration", {})
    interpreted = declaration.get("interpretation") == "mesonh_surfex_sea"
    sea_records = []
    for descriptors in (*binding["products"].values(), binding["dependencies"]):
        for descriptor in descriptors.values():
            field = source["fields"][descriptor["field_id"]]
            for record in descriptor["records"]:
                metadata = source_field_metadata(source, field, record=record)
                if metadata is not None:
                    descriptor.setdefault("field_metadata", metadata)
                    if interpreted and "surfex_units_source" in metadata["attributes"]:
                        record["field_metadata"] = metadata
                        sea_records.append(record)
    if interpreted:
        binding["interpretation"] = sea_interpretation(sea_records)
    fa_resolved = False
    if source.get("format") == "fa" and declaration:
        from frameit.core.configuration import _fa_runtime_options
        from frameit.io.fa_utils import fa_selected_array

        options = _fa_runtime_options(declaration)
        for descriptors in (*binding["products"].values(), binding["dependencies"]):
            for name, descriptor in descriptors.items():
                for record in descriptor["records"]:
                    # Construction checks the original record, declarations and geometry;
                    # native scaling/masks are checked only when this lazy payload executes.
                    fa_selected_array(record, source, options=options)
                    field = source["fields"][record["field_id"]]
                    metadata = source_field_declaration(source, field, record=record)
                    descriptor["field_metadata"] = {
                        "attributes": deepcopy(metadata),
                        "origins": {key: "declaration"
                                    for key in metadata}}
                    if record.get("vertical") is not None:
                        grid = source["native_grids"][record["grid_id"]]
                        if not grid.get("fa_hybrid_contract"):
                            binding["deferred_checks"].append(
                                f"{context}.{name}: native hybrid/scaling interpretation "
                                "requires the evidenced EPyGrAM hybrid contract.")
        binding["interpretation"] = {
            "method": "explicit_fa", "profile": options["profile"],
            "pending_value_checks": ["native decoder scaling and returned masks"]}
        fa_resolved = True
    pending_operations = [operation for operation in source.get("pending_operations", [])
                          if operation != "interpretation" or not interpreted]
    tracker_resolved = (pending_operations == ["tracker"]
                         and source.get("tracker_support", {}).get("inputs") == method_inputs)
    interpretation_resolved = interpreted and not pending_operations
    if (source["dependency_resolution"] == "pending_method_binding"
            and not tracker_resolved and not interpretation_resolved):
        binding["deferred_checks"].append(
            "Operation-specific derived/tracker/transform/polar/source-interpretation support "
            "remains pending method binding; field inventory alone does not resolve it.")
    if not fa_resolved and any(record["locator"]["format"] == "fa"
           for _, _, candidates in resolved.values() for _, record in candidates):
        binding["deferred_checks"].append("FA source interpretation and decode-time scaling "
                                           "eligibility remain required.")
    binding["deferred_checks"] = list(dict.fromkeys(binding["deferred_checks"]))
    if binding["deferred_checks"]:
        binding["status"] = "pending_method_binding"
    return binding
