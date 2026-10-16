# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Preserve scientific auxiliaries while removing source-cell metadata from point samples."""

from __future__ import annotations

import xarray as xr

HORIZONTAL_DIMS = {"y_box", "x_box"}
TEMPORAL_ARTEFACTS = {"step", "valid_time"}


def coordinate_dependency_names(source, variables, *, coordinates=None):
    """Follow CF coordinate/bounds/formula references without loading field data."""
    pending = list(variables) + list(source.coords if coordinates is None else coordinates)
    visited, dependencies = set(), set()
    while pending:
        name = pending.pop()
        if name in visited or name not in source:
            continue
        visited.add(name)
        value = source[name]
        refs = str(value.attrs.get("coordinates", value.encoding.get("coordinates", ""))).split()
        if value.attrs.get("bounds"):
            refs.append(value.attrs["bounds"])
        refs += str(value.attrs.get("ancillary_variables", "")).split()
        mapping = str(value.attrs.get("grid_mapping", "")).split()
        refs += [token.rstrip(":") for token in mapping]
        for key in ("formula_terms", "cell_measures"):
            tokens = str(value.attrs.get(key, "")).split()
            refs += [tokens[i + 1] for i, token in enumerate(tokens[:-1]) if token.endswith(":")]
        for ref in refs:
            if ref in source:
                dependencies.add(ref)
                pending.append(ref)
    return dependencies


def preserve_coordinate_dependencies(source, result):
    """Keep selected vertical/scalar auxiliaries and bounds through group selection."""
    source_horizontal = HORIZONTAL_DIMS | {
        "ni", "nj", "ni_u", "nj_u", "ni_v", "nj_v", "x", "y"}
    for name, coord in source.coords.items():
        if (name.lower() in {"latitude", "longitude", "lat", "lon", "latitude_u",
                             "longitude_u", "latitude_v", "longitude_v"}
                or coord.attrs.get("standard_name") in {"latitude", "longitude"}
                or coord.attrs.get("axis") in {"X", "Y"}):
            source_horizontal.update(dim for dim in coord.dims if dim != "time")
    # Only coordinates belonging to retained fields seed this walk. Seeding
    # every source coordinate can resurrect an unselected mass/interface axis
    # through its formula_terms, then silently expand W on assignment.
    for name in coordinate_dependency_names(source, result.data_vars, coordinates=result.coords):
        if name in result or name in result.data_vars:
            continue
        value = source[name]
        # A new vertex dimension is valid for retained vertical bounds, but a
        # missing source horizontal dimension denotes transformed/cropped data.
        # Never let a bounds reference resurrect that full source domain.
        missing = set(value.dims) - set(result.dims)
        if missing & source_horizontal:
            continue
        indexers = {dim: result[dim] for dim in value.dims
                    if dim in result.coords and result[dim].dims == (dim,)}
        if indexers:
            value = value.sel(indexers)
        result = result.assign_coords({name: value})
    result = result.copy(deep=False)
    for name in result.variables:
        attrs = dict(result[name].attrs)
        if attrs.get("bounds") and attrs["bounds"] not in result:
            attrs["source_bounds"] = attrs.pop("bounds")
        result[name].attrs = attrs
    return result


def point_attributes(attrs, available=(), *, retain_bounds=False):
    result = dict(attrs)
    for key in ("grid_mapping", "coordinates", "cell_measures", "ancillary_variables"):
        result.pop(key, None)
    if "grid" in result:
        result.setdefault("source_grid", result.pop("grid"))
    for key in ("c_grid_dynamic_range", "c_grid_axis_shift", "grid_position"):
        if key in result:
            result[f"source_{key}"] = str(result.pop(key))
    if not retain_bounds or result.get("bounds") not in available:
        result.pop("bounds", None)
    tokens = str(result.get("formula_terms", "")).split()
    if any(tokens[i + 1] not in available for i, token in enumerate(tokens[:-1])
           if token.endswith(":")):
        result.pop("formula_terms", None)
    return result


def source_auxiliaries(source, lon_name, lat_name, *, field_names):
    """Separate leading/scalar coordinates from horizontally transformed auxiliaries."""
    excluded = HORIZONTAL_DIMS | TEMPORAL_ARTEFACTS | {lon_name, lat_name}
    horizontal_bounds = set()
    coordinates = source[list(field_names)].coords
    for _name, coord in coordinates.items():
        if HORIZONTAL_DIMS.intersection(coord.dims) and not (
            set(coord.dims) - HORIZONTAL_DIMS - {"time"}
        ) and coord.attrs.get("axis") != "Z":
            if coord.attrs.get("bounds"):
                horizontal_bounds.add(coord.attrs["bounds"])
    excluded |= horizontal_bounds
    scalar, horizontal = {}, {}
    mapping = {}
    for name, variable in source.variables.items():
        if "grid_mapping_name" in variable.attrs:
            mapping[name] = dict(variable.attrs)
            excluded.add(name)
    references = {
        coord.attrs["bounds"] for name, coord in coordinates.items()
        if name not in excluded and coord.attrs.get("bounds")
    }
    for name in set(coordinates) | references:
        if name in excluded or name not in source:
            continue
        value = source[name]
        if HORIZONTAL_DIMS.intersection(value.dims):
            horizontal[name] = value
        else:
            scalar[name] = value
            for dim in value.dims:
                if dim in source.coords and dim not in HORIZONTAL_DIMS:
                    scalar.setdefault(dim, source[dim])
    return scalar, horizontal, mapping


def restore_auxiliaries(result: xr.Dataset, leading, transformed):
    available = set(leading) | set(transformed) | set(result.variables)
    for name, coord in leading.items():
        if name in {"time", "rr", "theta", "theta_deg"}:
            continue
        # Horizontal fields were reconstructed separately; leading/scalar
        # metadata must not bring back the native source geography.
        clean = xr.DataArray(coord.variable)
        clean.attrs = point_attributes(coord.attrs, available, retain_bounds=True)
        clean.encoding = {}
        result = result.assign_coords({name: clean})
    for name, coord in transformed.items():
        clean = xr.DataArray(coord.variable)
        clean.attrs = point_attributes(coord.attrs, available, retain_bounds=True)
        clean.attrs["coordinate_interpolation"] = "sampled_from_source_grid"
        result = result.assign_coords({name: clean})
    for name in result.data_vars:
        result[name].attrs = point_attributes(result[name].attrs, available)
        result[name].encoding = {}
    return result
