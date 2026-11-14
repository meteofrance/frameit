# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from copy import deepcopy
from typing import Any

import numpy as np
import xarray as xr

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
        for key in ("valid_min", "valid_max", "valid_range", "actual_range"):
            if key in attrs:
                scaled = np.asarray(attrs[key], dtype=float) * factor
                attrs[key] = scaled.item() if scaled.ndim == 0 else scaled
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
        + [name for name in request["internal_inputs"] if name not in request["derived"]]
        + list(method_inputs)))
    resolved, pending = {}, list(needed)
    clocks = {(r["time"], r["cycle"]) for r in source["records"]}
    while pending:
        name = pending.pop(0)
        if name in resolved:
            continue
        candidates = records_by_name.get(name, [])
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
                             "qualified selectors are unsupported")
        field_id = next(iter(identities))
        if any(field_id == value[0] for value in resolved.values()):
            raise ValueError(f"{context}: duplicate field request by resolved identity {field_id}")
        field = source["fields"][field_id]
        available = {(r["time"], r["cycle"], tuple(sorted(r.get("native_axes", {}).items())))
                     for _, r in candidates}
        axes = {entry[2] for entry in available}
        missing = {(time, cycle, axis) for time, cycle in clocks for axis in axes} - available
        if missing or set(source["selected_times"]) - {r["time"] for _, r in candidates}:
            raise ValueError(f"{context}: {name} unavailable at selected times/cycles/native axes; "
                             f"missing support {sorted(missing, key=str)}")
        resolved[name] = field_id, field, candidates
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
                    raise ValueError(
                        f"{context}: {source['physical_type']} field {name!r} has category "
                        f"{category}; use corrected YAML: variables: {{{category}: [{name}]}}")
                _coordinate_support(source, field, record)
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

    if "values" in request["levels"] and "units" not in request["levels"]:
        units = {_unit_identity(axis["descriptor"]["attributes"]["units"])
                 for product, name, _, _, axis, _, _ in jobs
                 if axis and axis["descriptor"]
                 and not (product == "_dependencies" and name in ancillary_names)
                 and unit_key(axis["descriptor"]["attributes"].get("units"))}
        if len(units) > 1:
            raise ValueError(f"{context}: value selection across different known units requires "
                             "explicit variables.levels.units")
    chosen, required_levels, bound_jobs, vertical_cache = set(), {}, {}, {}
    for product, name, index, record, axis, representation, descriptor in jobs:
        ancillary = product == "_dependencies" and name in ancillary_names and axis is not None
        key = (product, name, record["grid_id"],
               index if record["locator"]["format"] == "fa" else None)
        if key not in vertical_cache:
            sample = (f" at {record['locator']['path']}, time {record['time']}, "
                      f"cycle {record['cycle']}" if record["locator"]["format"] == "fa" else "")
            selector = (method_selectors[name] if product == "_dependencies"
                        and name in method_selectors else request["levels"])
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
            **deepcopy(record), "selection_grid_id": (
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
                    if "units" in request["levels"]:
                        selector["units"] = request["levels"]["units"]
                    other["vertical"] = _bind_vertical(
                        axis, selector, f"{context}._dependencies.{dependency}",
                        binding["warnings"])
                    other["source_positions"] = positions
                    pending_support.append((("_dependencies", other_index), other))
                _array_vertical_support(
                    parent, bound["source_positions"], axis, other["source_positions"],
                    request["levels"].get("units"), support_context)
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
    tracker_resolved = (source.get("pending_operations") == ["tracker"]
                        and source.get("tracker_support", {}).get("inputs") == method_inputs)
    if source["dependency_resolution"] == "pending_method_binding" and not tracker_resolved:
        binding["deferred_checks"].append(
            "Operation-specific derived/tracker/transform/polar/source-interpretation support "
            "remains pending method binding; field inventory alone does not resolve it.")
    if any(record["locator"]["format"] == "fa"
           for _, _, candidates in resolved.values() for _, record in candidates):
        binding["deferred_checks"].append("FA source interpretation and decode-time scaling "
                                           "eligibility remain required.")
    binding["deferred_checks"] = list(dict.fromkeys(binding["deferred_checks"]))
    if binding["deferred_checks"]:
        binding["status"] = "pending_method_binding"
    return binding
