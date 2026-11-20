"""Dataset metadata/coordinate inspection shared by validation and execution."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import re
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path

import numpy as np
import xarray as xr

from frameit.core.grid_geometry import resolve_geometry
from frameit.core.reports import (
    Diagnostic,
    PreflightError,
    PreflightResult,
    blocked_check,
    exception_diagnostics,
)
from frameit.io.loader import (
    DatasetResources,
    discover_input_files,
    input_path_excluded,
    inventory_source_files,
    resolve_input_files,
)
from frameit.processing.requests import (
    _field_axis,
    bind_requests,
    field_candidates,
    native_field_group,
    normalize_requests,
    selected_native_indices,
)
from frameit.processing.wind_reference import (
    MESONH_PROJECTION_METADATA,
    inspect_wind_metadata,
    pair_definition,
    rotation_angle,
    validate_pair_frame,
    wind_frame_override,
    wind_pairs,
)
from frameit.utils.diagnostics import exception_code, tag_error
from frameit.utils.units import UNITS, convert_units, unit_key


def _metadata_id(prefix, value):
    """Hash coordinate/identity metadata only, never scientific field contents."""
    def encode(item):
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.generic):
            return str(item) if item.dtype.kind in "mM" else item.item()
        return str(item)

    encoded = json.dumps(value, default=encode, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(encoded.encode()).hexdigest()


def _source_model(source, datasets, path, *, fmt):
    evidence = []
    models = set()
    for ds in datasets:
        for key in ("model", "model_id", "source", "title", "type",
                    "producer", "program", "PROGRAM"):
            value = str(ds.attrs.get(key, ""))
            for model, pattern in (("mesonh", r"\bmeso[-_ ]?nh\b"), ("arome", r"\barome\b"),
                                   ("nemo", r"\bnemo\b"), ("croco", r"\bcroco\b")):
                if re.search(pattern, value, re.I):
                    models.add(model)
                    evidence.append({"attribute": key, "value": value, "model": model})
        if "MNH_cleanly_closed" in ds.attrs:
            models.add("mesonh")
            evidence.append({"attribute": "MNH_cleanly_closed",
                             "value": ds.attrs["MNH_cleanly_closed"], "model": "mesonh"})
    declared = source.get("model")
    if len(models) > 1 or declared and models and models != {declared}:
        raise PreflightError([Diagnostic(
            "input.model",
            f"source model declaration {declared!r} conflicts with input metadata",
            {"model": declared} if declared else "one unambiguous source model",
            {"models": sorted(models), "evidence": evidence},
            ["Select files with consistent model evidence; "
              "correct model only from producer evidence."], code="E1203")])
    model = declared or next(iter(models), None)
    if model is None:
        raise tag_error(ValueError(
            f"{path}: model has no unambiguous metadata evidence; declare sources.*.model"
        ), "E1203")
    if model in {"nemo", "croco", "mesonh"} and fmt != "netcdf":
        raise tag_error(ValueError(f"{path}: {model} requires its admitted NetCDF file profile"),
                        "E1203")
    if not evidence:
        evidence.append({"declaration": model, "file_profile": fmt,
                         "scope": "declared model; not automatic model detection"})
    return model, evidence


def _decoded_clock(ds, path, *, model):
    """Keep native decoded types, clocks, cycles and interval endpoints separate."""
    references = [name for name in ds.variables if (
        name == "forecast_reference_time"
        or ds[name].attrs.get("standard_name") == "forecast_reference_time")]
    candidates = [name for name in ds.variables if name not in references and (
        name in {"time", "valid_time", "time_counter", "time_centered", "scrum_time"}
        or ds[name].attrs.get("standard_name") == "time" or ds[name].attrs.get("axis") == "T")]
    if not candidates:
        # A readable file can still be proven irrelevant after dependency discovery.
        return [], set(references)
    name = next((n for n in ("valid_time", "time_counter", "time") if n in candidates),
                candidates[0])
    clock = ds[name]
    values = np.asarray(clock.values)
    import cftime

    if not (values.dtype.kind == "M" or values.dtype.kind == "O" and all(
            isinstance(t, cftime.datetime) for t in values.flat)):
        raise PreflightError([Diagnostic(
            "input.clock", f"{name} must contain decoded timestamps",
            {"clock": "decoded timestamps"}, {"clock": name, "dtype": str(values.dtype)},
            [f"Provide a CF-decodable {name} coordinate with units and calendar metadata."],
            code="E1401")])
    if values.size == 0 or values.dtype.kind == "M" and np.isnat(values).any():
        raise ValueError(f"{path}: missing sample timestamps in {name}")
    calendar = clock.encoding.get("calendar", clock.attrs.get("calendar", "standard"))
    scalar_dtcur_alias = False
    for other in candidates:
        candidate = ds[other]
        other_calendar = candidate.encoding.get("calendar", candidate.attrs.get("calendar", "standard"))
        if other_calendar != calendar:
            raise ValueError(f"{path}: conflicting calendars on {name} and {other}")
        if (model == "mesonh" and name == "time" and clock.dims == ("time",)
                and values.shape == (1,) and other == "DTCUR" and candidate.ndim == 0):
            alias = candidate.values[()]
            equal = type(alias) is type(values[0]) and alias == values[0]
            scalar_dtcur_alias = equal
        else:
            equal = candidate.dims == clock.dims and np.array_equal(candidate.values, values)
        if not equal:
            raise ValueError(f"{path}: conflicting or unidentified sample/forecast clocks "
                             f"{name}, {other}")
    reference, reference_calendar = None, None
    for ref in references:
        da = ds[ref]
        declared_calendar = da.encoding.get("calendar", da.attrs.get("calendar", "standard"))
        if reference_calendar is not None and declared_calendar != reference_calendar:
            raise ValueError(f"{path}: conflicting forecast reference calendars")
        if not set(da.dims) <= set(clock.dims):
            raise ValueError(f"{path}: forecast reference clock {ref} does not index {name}")
        broadcast = da.broadcast_like(clock).transpose(*clock.dims).values
        if reference is not None and not np.array_equal(broadcast, reference):
            raise ValueError(f"{path}: conflicting forecast reference clocks")
        if np.asarray(broadcast).dtype.kind != "M" and not all(
                isinstance(t, cftime.datetime) for t in np.asarray(broadcast).flat):
            raise ValueError(f"{path}: forecast reference clock is not decoded")
        if np.asarray(broadcast).dtype.kind == "M" and np.isnat(broadcast).any():
            raise ValueError(f"{path}: missing forecast reference timestamp")
        reference, reference_calendar = broadcast, declared_calendar
    bound_names = list(dict.fromkeys(ds[n].attrs["bounds"] for n in candidates
                                    if ds[n].attrs.get("bounds")))
    bounds = None
    for bound_name in bound_names:
        if (bound_name not in ds or ds[bound_name].shape != (*clock.shape, 2)
                or ds[bound_name].dims[:-1] != clock.dims
                or ds[bound_name].dims[-1] in clock.dims):
            raise ValueError(f"{path}: missing or invalid {name} bounds {bound_name}; "
                             f"bounds dimensions must be {clock.dims} followed by "
                             "a distinct endpoint axis of length 2")
        current = np.asarray(ds[bound_name].values)
        if current.dtype.kind != "M" and not all(
                isinstance(t, cftime.datetime) for t in current.flat):
            raise ValueError(f"{path}: {bound_name} must contain decoded interval bounds")
        if current.dtype.kind == "M" and np.isnat(current).any():
            raise ValueError(f"{path}: missing interval endpoints in {bound_name}")
        if bounds is not None and not np.array_equal(bounds, current):
            raise ValueError(f"{path}: conflicting sample clock bounds {bound_names}")
        bounds = current
    samples = []
    for position in np.ndindex(values.shape):
        samples.append({"time": values[position], "calendar": calendar,
                         "cycle": reference[position] if reference is not None else None,
                         **({"reference_calendar": reference_calendar} if reference is not None else {}),
                         "time_bounds": tuple(bounds[position]) if bounds is not None else None,
                          "clock": name, "temporal_names": sorted(set(candidates) | set(clock.dims)),
                          **({"scalar_dtcur_alias": True} if scalar_dtcur_alias else {}),
                          "indexers": dict(zip(clock.dims, position, strict=True))})
    return samples, set(candidates + references + bound_names)


def _cf_coordinate_metadata(ds, *, model):
    """Recognize declared coordinate labels/constants, not scientific formula inputs."""
    metadata = {}
    ancillary = {name for var in ds.variables.values()
                 for name in str(var.attrs.get("ancillary_variables", "")).split()}
    if model == "arome":
        scientific = {name for var in ds.variables.values()
                      for key in ("cell_measures", "formula_terms")
                      for name in str(var.attrs.get(key, "")).split()[1::2]}
        linked = {name for var in ds.data_vars.values() for name in str(var.attrs.get(
            "coordinates", var.encoding.get("coordinates", ""))).split()}
    for name, coord in ds.coords.items():
        if name in ancillary or coord.attrs.keys() & {"flag_values", "flag_masks", "flag_meanings"}:
            continue
        standard, units = coord.attrs.get("standard_name"), unit_key(coord.attrs.get("units"))
        scalar_level = coord.ndim == 0 and coord.dtype.kind in "iuf" and (
            (standard == "height" and units in UNITS["distance"][1])
            or (name == "meanSea" and units == "1" and coord.attrs.get("long_name")
                == "original GRIB coordinate for key: level(meanSea)"))
        if (model == "arome" and name in linked and name not in scientific
                and (scalar_level or (standard == "forecast_period" and coord.dtype.kind == "m"))):
            metadata[name] = set()
            continue
        if coord.ndim != 1 or coord.attrs.get("axis") != "Z":
            continue
        if standard == "air_pressure" and units in UNITS["pressure"][1]:
            metadata[name] = set()
        elif (standard == "atmosphere_hybrid_sigma_pressure_coordinate"
              and units in {"", "1"}):
            metadata[name] = set()
            tokens = str(coord.attrs.get("formula_terms", "")).split()
            if len(tokens) % 2 or any(not term.endswith(":") for term in tokens[::2]):
                raise ValueError(f"{name}: invalid CF formula_terms; use paired 'term: variable'")
            for term, dependency in zip(tokens[::2], tokens[1::2], strict=True):
                term = term.removesuffix(":")
                if dependency not in ds or dependency in ancillary:
                    continue
                value = ds[dependency]
                if value.attrs.keys() & {"flag_values", "flag_masks"}:
                    continue
                units = unit_key(value.attrs.get("units"))
                if ((term in {"a", "b"} and value.dims == coord.dims and units in {"", "1"})
                        or (term == "ap" and value.dims == coord.dims
                            and units in UNITS["pressure"][1])
                        or (term == "p0" and value.ndim == 0 and units in UNITS["pressure"][1])):
                    metadata[name].add(dependency)
    return metadata


def _native_grid(ds, variable, temporal_dims, coordinate_metadata=None):
    spatial = tuple(dim for dim in variable.dims if dim not in temporal_dims)
    # Auxiliary arrays can be scientific support, even when xarray calls them coordinates.
    names = set(spatial)
    coordinate_metadata = coordinate_metadata or {}
    known = (set(coordinate_metadata)
             | {n for values in coordinate_metadata.values() for n in values})
    explicit = str(variable.attrs.get(
        "coordinates", variable.encoding.get("coordinates", ""))).split()
    names.update(n for n in known & set(explicit)
                 if set(ds[n].dims) - temporal_dims <= set(spatial))
    for owner in set(names) & coordinate_metadata.keys():
        names.update(coordinate_metadata[owner])
    for name, coord in ds.variables.items():
        geographic = (coord.attrs.get("standard_name") in {"latitude", "longitude"}
                      or name in {"latitude", "longitude", "nav_lat", "nav_lon",
                                  "latitude_u", "longitude_u", "latitude_v", "longitude_v",
                                  "lat_rho", "lon_rho", "lat_u", "lon_u", "lat_v", "lon_v"})
        if geographic and set(coord.dims) - temporal_dims <= set(spatial):
            names.add(name)
    mapping = variable.attrs.get("grid_mapping")
    if mapping:
        names.add(mapping)
    names = sorted((names & set(ds.variables)) - temporal_dims)
    scientific = {name for var in ds.variables.values()
                  for name in str(var.attrs.get("ancillary_variables", "")).split()}
    scientific.update(name for var in ds.variables.values()
                      for name in str(var.attrs.get("cell_measures", "")).split()[1::2])
    scientific.update(name for var in ds.variables.values()
                      for name in str(var.attrs.get("formula_terms", "")).split()[1::2]
                      if name not in names)
    # Validate every bounds reference before materializing any grid coordinate.
    for name in names:
        coord = ds[name]
        bounds = coord.attrs.get("bounds")
        if not bounds:
            continue
        context = f"{name} bounds {bounds!r}"
        if bounds not in ds:
            raise ValueError(f"{context}: missing bounds variable")
        target = ds[bounds]
        if (target.ndim != coord.ndim + 1 or target.dims[:-1] != coord.dims
                or target.dims[-1] in coord.dims):
            raise ValueError(f"{context}: invalid dimensions {target.dims}; expected "
                             f"{coord.dims} followed by a distinct endpoint/vertex axis")
        if coord.attrs.get("axis") == "Z" and target.shape[-1] != 2:
            raise ValueError(f"{context}: vertical bounds require two endpoints")
        if (bounds in scientific
                or target.attrs.keys() & {"flag_values", "flag_masks", "flag_meanings"}):
            raise ValueError(f"{context}: conflicting scientific input/ancillary/flag role; "
                             "provide coordinate bounds instead of reusing a scientific input")
    coordinates = {}
    for name in names:
        coord = ds[name]
        coordinates[name] = {"dimensions": list(coord.dims), "values": np.asarray(coord.values),
                             "attributes": deepcopy(coord.attrs), "dtype": str(coord.dtype),
                             "role": "coordinate_metadata"}
        bounds = coord.attrs.get("bounds")
        if bounds:
            coordinates[bounds] = {
                "dimensions": list(ds[bounds].dims), "values": np.asarray(ds[bounds].values),
                "attributes": deepcopy(ds[bounds].attrs), "dtype": str(ds[bounds].dtype),
                "role": "coordinate_metadata"}
    grid = {"dimensions": {dim: ds.sizes[dim] for dim in spatial}, "coordinates": coordinates,
            "grid_mapping": mapping}
    return _metadata_id("grid_", grid), grid


def _netcdf_inventory(path, source, resources, *, check_croco_zeta=False):
    from frameit.io.grib_utils import normalize_isobaric_coordinates
    from frameit.io.netcdf_utils import mnh_altitude_terms

    try:
        ds = resources.open_netcdf(path, engine=source.get("reader", {}).get("engine", "h5netcdf"))
    except ImportError as exc:
        raise tag_error(exc, "E1006")
    except OSError as exc:
        raise tag_error(exc, "E1202")
    ds = normalize_isobaric_coordinates(ds)
    model, evidence = _source_model(source, [ds], path, fmt="netcdf")
    if model == "nemo":
        if "time_counter" not in ds or ds.time_counter.dims != ("time_counter",):
            raise tag_error(ValueError(f"{path}: NEMO requires its native time_counter sample clock"),
                            "E1401")
        if any(n not in ds or ds[n].dims != ("y", "x") for n in ("nav_lat", "nav_lon")):
            raise tag_error(ValueError(
                f"{path}: NEMO requires source-local (y, x) nav_lat/nav_lon geography"
            ), "E1204")
    if model == "croco" and ds.attrs.get("type") != "CROCO history file":
        raise tag_error(ValueError(f"{path}: CROCO requires the admitted CROCO history file profile"),
                        "E1203")
    try:
        samples, time_names = _decoded_clock(ds, path, model=model)
    except PreflightError:
        raise
    except ValueError as exc:
        raise tag_error(exc, "E1401")
    zeta_history = False
    if model == "croco" and check_croco_zeta:
        from frameit.io.croco_utils import croco_zeta_history_support

        zeta_history = croco_zeta_history_support(ds)
    temporal_dims = {dim for sample in samples for dim in sample["indexers"]}
    altitude_axes = {name: terms for name in ("level", "level_w") if model == "mesonh"
                     and name in ds.coords
                     and (terms := mnh_altitude_terms(name, ds[name].dims, ds[name].attrs))}
    altitude_height_terms = {terms["height:"] for terms in altitude_axes.values()}
    coordinate_metadata = _cf_coordinate_metadata(ds, model=model)
    scalar_leads = set()
    if len(samples) == len(temporal_dims) == 1:
        scalar_leads = {name for name in coordinate_metadata if ds[name].ndim == 0
                        and ds[name].attrs.get("standard_name") == "forecast_period"
                        and "bounds" not in ds[name].attrs}
        if scalar_leads:
            axis, = temporal_dims
            # Store sample-aligned geometry without changing the native scalar locator.
            ds = ds.assign_coords({n: ds[n].variable.set_dims((axis,)) for n in scalar_leads})
    metadata = (set(time_names) | set(ds.dims) | set(coordinate_metadata)
                | {n for values in coordinate_metadata.values() for n in values})
    for name, value in ds.variables.items():
        if value.attrs.get("standard_name") in {"latitude", "longitude"} or name in {
                "latitude", "longitude", "nav_lat", "nav_lon", "lat_rho", "lon_rho",
                "lat_u", "lon_u", "lat_v", "lon_v",
                "latitude_u", "longitude_u", "latitude_v", "longitude_v"}:
            metadata.add(name)
        if value.attrs.get("bounds"):
            metadata.add(value.attrs["bounds"])
        if value.attrs.get("grid_mapping"):
            metadata.add(value.attrs["grid_mapping"])
    from frameit.processing.wind_reference import inspect_wind_metadata

    dataset_attributes = inspect_wind_metadata({}, ds.attrs).get("dataset_attributes", {})
    fields, grids, records, cache = {}, {}, [], {}
    for name in ds.variables:
        if name in metadata:
            continue
        var = ds[name]
        key = (tuple(d for d in var.dims if d not in temporal_dims),
               str(var.attrs.get("coordinates", var.encoding.get("coordinates", ""))),
               var.attrs.get("grid_mapping"))
        if key not in cache:
            cache[key] = _native_grid(ds, var, temporal_dims | time_names, coordinate_metadata)
        grid_id, grid = cache[key]
        # Provenance is outside the geometry hash and the clean cached grid.
        if grid_id not in grids:
            grids[grid_id] = {**grid, "coordinate_providers": {
                coordinate: [{
                    "format": "netcdf", "path": str(path), "variable": coordinate,
                    **({"native_dimensions": []} if coordinate in scalar_leads else {}),
                    "samples": [{**sample,
                                  "indexers": {d: i for d, i in sample["indexers"].items()
                                               if d in ds[coordinate].dims and coordinate not in scalar_leads},
                                 "coordinate_indexers": dict(sample["indexers"])}
                                for sample in samples],
                }] for coordinate in grid["coordinates"]}}
        field = {"name": name, "dimensions": list(var.dims), "dtype": str(var.dtype),
                  "attributes": deepcopy(var.attrs), "grid_id": grid_id,
                  **({"dataset_attributes": dataset_attributes} if dataset_attributes else {}),
                 "coordinate_names": list(grid["coordinates"]),
                 "role": "array",
                 "xarray_coordinate": name in ds.coords,
                 "time_varying": bool(set(var.dims) & temporal_dims)}
        identity_grid = grid_id
        if any(set(c["dimensions"]) & temporal_dims for c in grid["coordinates"].values()):
            # Time-labelled moving coordinates change record geometry, not field identity.
            topology = {**grid, "coordinates": {
                n: {k: v for k, v in c.items()
                    if k != "values" or not set(c["dimensions"]) & temporal_dims}
                for n, c in grid["coordinates"].items()}}
            identity_grid = _metadata_id("grid_", topology)
        identity_attributes = field["attributes"]
        interpreted = False
        if source.get("interpretation") == "mesonh_surfex_sea":
            from frameit.io.surfex_utils import SURFEX_FIELDS, _unit_identity, _units

            interpreted = name in SURFEX_FIELDS
            if interpreted:
                try:
                    units, _ = _units(field["attributes"], name)
                except ValueError:
                    pass  # Selected metadata validation reports invalid/missing evidence.
                else:
                    identity_attributes = dict(identity_attributes, units=_unit_identity(units))
        explicit = str(var.attrs.get(
            "coordinates", var.encoding.get("coordinates", ""))).split()
        dependencies = {dep: "coordinates" for dep in explicit
                        if dep not in time_names and dep != name and dep not in ds.dims}
        linked_tops = sorted(dependencies.keys() & altitude_height_terms)
        field_id = _metadata_id("field_", {
            "name": name, "grid_id": identity_grid, "attributes": identity_attributes,
            **({"dataset_attributes": dataset_attributes} if dataset_attributes else {}),
            **({"linked_altitude_tops": linked_tops} if linked_tops else {}),
            "dimensions": [d for d in var.dims if d not in temporal_dims]})
        fields[field_id] = field
        strict, altitude = set(dependencies), {}
        for owner in (var, *(ds[n] for n in grid["coordinates"] if n in ds)):
            height = altitude_axes.get(owner.name, {}).get("height:")
            for attr in ("ancillary_variables", "formula_terms", "cell_measures"):
                tokens = str(owner.attrs.get(attr, "")).split()
                references = ((attr, dep) for dep in tokens) if attr == "ancillary_variables" else (
                    zip(tokens[::2], tokens[1::2]))
                for term, dep in references:
                    if dep not in {"or", "orog:"}:
                        dependencies[dep] = attr
                        if attr == "formula_terms" and term == "height:" and dep == height:
                            altitude[owner.name] = height
                        else:
                            strict.add(dep)
        field["coordinate_dependencies"] = {
            dep: attr for dep, attr in dependencies.items() if dep in grid["coordinates"]}
        field["dependencies"] = {
            dep: attr for dep, attr in dependencies.items() if dep not in grid["coordinates"]}
        if optional := {axis: dep for axis, dep in altitude.items()
                        if dep in field["dependencies"] and dep not in strict}:
            field["altitude_formula_operands"] = optional
        if source.get("interpretation") == "mesonh_surfex_sea":
            from frameit.io.surfex_utils import SURFEX_FIELDS

            if name in SURFEX_FIELDS - {"FRAC_SEA"}:
                field["dependencies"]["FRAC_SEA"] = "sea_support"
        for sample in samples:
            indexers = {dim: index for dim, index in sample["indexers"].items() if dim in var.dims}
            records.append({
                **{k: v for k, v in sample.items() if k != "indexers"},
                **({"observed_attributes": deepcopy(var.attrs)} if interpreted else {}),
                "field_id": field_id, "name": name, "grid_id": grid_id, "level": None,
                "stored_dtype": np.dtype(var.encoding.get("dtype", var.dtype)).name,
                "decoded_dtype": var.dtype.name,
                **({"croco_zeta_history": True} if zeta_history and name == "zeta" else {}),
                "temporal_metadata": {k: var.attrs[k] for k in (
                    "cell_methods", "GRIB_stepType", "online_operation",
                    "interval_operation", "interval_write")
                    if k in var.attrs},
                "locator": {"format": "netcdf", "path": str(path), "variable": name,
                            "indexers": indexers,
                            "coordinate_indexers": dict(sample["indexers"])}})
    return {"model": model,
             "physical_type": "ocean" if model in {"nemo", "croco"} else "atmosphere",
             "dataset_attributes": dataset_attributes,
             "altitude_height_terms": altitude_height_terms,
            "profile": None, "evidence": evidence, "fields": fields,
            "native_grids": grids, "records": records}


def _grib_source_inventory(path, source):
    """Scan each message once; message offsets are the future payload read boundary."""
    from datetime import datetime

    try:
        import eccodes as ec
    except (ImportError, RuntimeError, OSError) as exc:
        raise tag_error(exc, "E1002")

    from frameit.io.grib_utils import GRIB_PRESSURE_UNITS, grib_wind10m_kind_evidence

    model, evidence = _source_model(source, [], path, fmt="grib")
    fields, grids, records, horizontal = {}, {}, [], {}
    aliases = {"10u": "u10", "10v": "v10", "msl": "prmsl"}
    with path.open("rb") as stream:
        index = 0
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                def get(key, default=None):
                    return (ec.codes_get(handle, key)
                            if ec.codes_is_defined(handle, key) else default)

                shape = int(get("Nj", 0)), int(get("Ni", 0))
                if min(shape) < 1 or np.prod(shape, dtype=object) != int(get("numberOfPoints", 0)):
                    raise tag_error(ValueError(
                        f"{path}: GRIB grid is not an admitted rectangular Ni/Nj grid"
                    ), "E1204")
                signature = get("md5GridSection")
                if not signature:
                    raise tag_error(ValueError(f"{path}: GRIB has no identifiable grid section"),
                                    "E1204")
                if signature not in horizontal:
                    lat = np.asarray(ec.codes_get_array(handle, "latitudes"))
                    lon = np.asarray(ec.codes_get_array(handle, "longitudes"))
                    jfast = int(get("jPointsAreConsecutive", 0))
                    lat = lat.reshape(shape[::-1]).T if jfast else lat.reshape(shape)
                    lon = lon.reshape(shape[::-1]).T if jfast else lon.reshape(shape)
                    horizontal[signature] = {
                        "dimensions": {"y": shape[0], "x": shape[1]},
                        "coordinates": {
                            name: {"dimensions": ["y", "x"], "values": values,
                                   "attributes": {"units": units}, "dtype": str(values.dtype)}
                            for name, values, units in (("latitude", lat, "degrees_north"),
                                                       ("longitude", lon, "degrees_east"))},
                        "grid_mapping": None, "grib_grid_section": signature,
                        "grid_type": get("gridType")}
                native_group = get("typeOfLevel")
                group = "isobaric" if native_group in GRIB_PRESSURE_UNITS else native_group
                grid = {**horizontal[signature], "vertical_group": group,
                        "vertical_units": GRIB_PRESSURE_UNITS.get(native_group)}
                grid_id = _metadata_id("grid_", grid)
                grids[grid_id] = grid
                short, name = str(get("shortName", "")), str(get("cfVarName", ""))
                if name in {"unknown", "undef", ""} or short in {"u", "v"}:
                    name = short
                name = aliases.get(name, aliases.get(short, name))
                if name in {"unknown", "undef", ""}:
                    # Unknown parameters remain inspectable, without invented field aliases.
                    name = None
                attributes = {"units": get("units"), "GRIB_paramId": get("paramId"),
                              "GRIB_typeOfLevel": native_group, "GRIB_stepType": get("stepType")}
                if (value := get("uvRelativeToGrid")) is not None:
                    attributes["GRIB_uvRelativeToGrid"] = value
                native_axes = ({"number": int(get("number"))}
                               if get("number") is not None else {})
                ensemble = {key: get(key) for key in (
                    "perturbationNumber", "typeOfEnsembleForecast", "numberOfForecastsInEnsemble")
                    if get(key) is not None}
                field = {"name": name, "dimensions": ["y", "x"], "dtype": "float64",
                         "grid_id": grid_id, "attributes": attributes, "group": group,
                         "coordinate_names": list(grid["coordinates"]), "time_varying": True,
                         "dependencies": {}}
                field_id = _metadata_id("field_", {"name": name, "grid_id": grid_id,
                                                   "attributes": attributes})
                fields[field_id] = field

                cycle = np.datetime64(datetime(*(int(get(key, 0)) for key in (
                    "year", "month", "day", "hour", "minute", "second"))), "ns")
                unit = ec.codes_get_string(handle, "stepUnits")
                seconds = {"s": 1, "m": 60, "h": 3600, "3h": 10800, "6h": 21600,
                           "12h": 43200, "D": 86400}.get(unit)
                if seconds is None:
                    raise tag_error(ValueError(
                        f"{path}: unsupported GRIB forecast step unit {unit!r}"
                    ), "E1401")
                endpoints = tuple(
                    cycle + np.timedelta64(
                        round(ec.codes_get_double(handle, key) * seconds * 1e6), "us")
                    for key in ("startStep", "endStep"))
                valid = endpoints[1]
                temporal = {"GRIB_" + key: get(key) for key in (
                    "stepType", "startStep", "endStep", "stepUnits", "typeOfStatisticalProcessing")
                    if get(key) is not None}
                bounds = endpoints if get("stepType") != "instant" else None
                kind_evidence = grib_wind10m_kind_evidence(handle)
                records.append({
                    "field_id": field_id, "name": name, "grid_id": grid_id,
                    "level": get("level"), "time": valid, "calendar": "proleptic_gregorian",
                    "cycle": cycle, "time_bounds": bounds, "clock": "GRIB_reference_plus_endStep",
                    "temporal_metadata": temporal, "native_axes": native_axes,
                    "ensemble_metadata": ensemble,
                    **({"grib_wind10m_kind": kind_evidence} if kind_evidence else {}),
                    "locator": {"format": "grib", "path": str(path), "message_index": index,
                                "offset": int(ec.codes_get_message_offset(handle)),
                                "length": int(ec.codes_get_message_size(handle))}})
            finally:
                ec.codes_release(handle)
            index += 1
    if not records:
        raise tag_error(ValueError(f"{path}: no GRIB records"), "E1202")
    for field_id, field in fields.items():
        field["levels"] = sorted({r["level"] for r in records if r["field_id"] == field_id})
    return {"model": model, "physical_type": "atmosphere", "profile": None,
            "evidence": evidence, "fields": fields, "native_grids": grids, "records": records}


def _fa_source_inventory(path, source, conf):
    from frameit.core.configuration import _fa_runtime_options
    from frameit.io.fa_backend import inspect_fa
    from frameit.io.fa_contracts import layout_definition
    from frameit.io.fa_geometry import fa_geometry

    options = conf.fa_options or _fa_runtime_options(source)
    conf.fa_options = deepcopy(options)
    arguments = {key: options[key] for key in (
        "profile", "expected_source", "backend", "python_executable", "earth_radius_m",
        "timeout_seconds")}
    arguments["geometry_options"] = {key: options[key] for key in (
        "subdomain", "earth_radius_m", "max_points")}
    header = inspect_fa(path, **arguments)
    info = inspect_fa(path, fields=list(header["records"]), validate_selection=False, **arguments)
    surface = bool(info["surfex_metadata"])
    if surface and (not layout_definition(info["surfex_metadata"])
                    or info["surfex_metadata"].get("PACK") != 0):
        raise tag_error(ValueError(
            f"{path}: only the admitted AROME-47 SURFEX-8.1 PACK=0 profile is supported"
        ), "E1205")
    profile = "surfex_history" if surface else "arome_history"
    model = source.get("model")
    if model not in {None, "arome"}:
        raise tag_error(ValueError(f"{path}: model conflicts with admitted FA profile {profile}"),
                        "E1203")
    if model is None and not source.get("profile") and not surface:
        raise tag_error(ValueError(
            f"{path}: model has no unambiguous FA producer evidence; declare model/profile"
        ), "E1203")
    try:
        geometry = fa_geometry(info["geometry"], options)
    except ValueError as exc:
        raise tag_error(exc, "E1205")
    horizontal = geometry.latitude.broadcast_like(geometry.longitude).transpose("y", "x")
    _, grid = _native_grid(
        geometry, horizontal.assign_attrs(grid_mapping="crs"), set())
    grid.update(fa_header=deepcopy(info["geometry"]),
                fa_geometry=deepcopy(geometry.attrs))
    for name in ("source_i", "source_j"):
        grid["coordinates"][name] = {
            "dimensions": list(geometry[name].dims), "values": geometry[name].values,
            "attributes": deepcopy(geometry[name].attrs), "dtype": str(geometry[name].dtype)}
    grid_id = _metadata_id("grid_", grid)
    grids, fields, records = {grid_id: grid}, {}, []
    for name, descriptor in info["field_descriptors"].items():
        if descriptor["native"]["representation"] == "typed_metadata":
            continue
        dimensions = (["y", "x"] if descriptor["native"]["representation"] == "gridpoint"
                      and descriptor["native"]["shape"] is not None else None)
        # Field summaries may span providers; only records retain sample-local evidence.
        field = {"name": name, "dimensions": dimensions,
                 "dtype": descriptor["native"]["decoded_dtype"],
                 "grid_id": grid_id, "attributes": {},
                 "coordinate_names": list(grid["coordinates"]),
                 "time_varying": False, "dependencies": {}, "native_descriptor": descriptor}
        field_id = _metadata_id("field_", {"name": name, "grid_id": grid_id})
        fields[field_id] = field
        records.append({
            "field_id": field_id, "name": name, "grid_id": grid_id, "level": None,
            "time": np.datetime64(info["valid_time"]), "calendar": "proleptic_gregorian",
            "cycle": np.datetime64(info["reference_time"]), "time_bounds": None,
            "clock": "FA_validity", "temporal_metadata": {},
            "native_descriptor": deepcopy(descriptor),
            "locator": {"format": "fa", "path": str(path), "records": [name],
                        "zone": list(geometry.attrs["fa_zone_indices"]),
                        "identity": list(info["identity"])}})
    # Cubes are explicit associations, not a vertical meaning inferred from record names.
    for name, cube in source.get("native_cubes", {}).items():
        missing = set(cube["records"]) - info["records"].keys()
        if missing:
            continue
        cube_grid = {**grid, "native_vertical_header": {key: info["geometry"].get(key) for key in (
            "KNIVER", "PREFER", "PAHYBR", "PBHYBR")},
                      "fa_hybrid_contract": deepcopy(info.get("hybrid_contract")),
                     "vertical_position": cube["vertical_position"], "sampling": cube["sampling"]}
        cube_grid_id = _metadata_id("grid_", cube_grid)
        grids[cube_grid_id] = cube_grid
        field_id = _metadata_id("field_", {"name": name, "grid_id": cube_grid_id})
        fields[field_id] = {
            "name": name, "dimensions": ["native_level", "y", "x"], "grid_id": cube_grid_id,
            "attributes": {}, "coordinate_names": list(grid["coordinates"]), "dependencies": {},
            "native_cube": deepcopy(cube), "time_varying": False,
        }
        records.append({**{k: v for k, v in records[0].items() if k != "native_descriptor"},
                        "field_id": field_id, "name": name,
                        "grid_id": cube_grid_id,
                        "locator": {"format": "fa", "path": str(path),
                                    "records": list(cube["records"]),
                                    "zone": list(geometry.attrs["fa_zone_indices"]),
                                    "identity": list(info["identity"])}})
    return {"model": "arome", "physical_type": "surface" if surface else "atmosphere",
            "profile": profile, "evidence": [
                {"profile": profile, "producer_metadata": deepcopy(info["surfex_metadata"]),
                 "model_basis": "native producer metadata" if surface else "declared profile",
                 "identifier": info["identifier"], "backend_versions": info["backend_versions"]}],
            "fields": fields, "native_grids": grids, "records": records}


def _selection_stamp(value, example):
    from datetime import timedelta

    from frameit.core.configuration import _timestamp

    parts, zone = _timestamp(value, "sources.*.time")
    year, month, day, hour, minute, second, fraction = parts
    if isinstance(example, np.datetime64):
        digits = format(fraction, "f")[2:].rstrip("0")
        try:
            if len(digits) > 9:
                raise ValueError
            seconds = np.datetime64(
                f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}", "s")
            if _timestamp(str(seconds), "sources.*.time")[0] != (*parts[:6], 0):
                raise ValueError
            if zone and zone != "Z":
                minutes = (int(zone[1:3]) * 60 + int(zone[4:])) * (1 if zone[0] == "+" else -1)
                seconds = np.datetime64(int(seconds.astype("int64")) - minutes * 60, "s")
            normalized = str(seconds) + ("." + digits if digits else "")
            stamp = np.datetime64(normalized)
            stamp = stamp.astype(np.promote_types(stamp.dtype, example.dtype))
            # NumPy casts may wrap silently; compare decoded parts before any selection.
            if (_timestamp(str(stamp), "sources.*.time")[0]
                    != _timestamp(normalized, "sources.*.time")[0]):
                raise ValueError
            return stamp
        except (ValueError, OverflowError):
            raise ValueError(f"Requested timestamp {value!r} is not representable at "
                             "supported source-clock precision/range") from None
    if fraction * 1_000_000 != int(fraction * 1_000_000):
        raise ValueError("Requested timestamp precision is unavailable in this source calendar")
    stamp = type(example)(year, month, day, hour, minute, second, int(fraction * 1_000_000))
    if zone and zone != "Z":
        offset = timedelta(hours=int(zone[1:3]), minutes=int(zone[4:]))
        stamp -= offset if zone[0] == "+" else -offset
    return stamp


def _select_source_records(records, selection, context):
    if not records:
        raise tag_error(ValueError(
            f"{context}: no selected decoded records; required fields need a sample clock"
        ), "E1401")
    calendars = {r["calendar"] for r in records}
    if len(calendars) != 1:
        raise tag_error(ValueError(f"{context}: source has conflicting calendars {sorted(calendars)}"),
                        "E1401")
    cycles = {r["cycle"] for r in records if r["cycle"] is not None}
    if "cycle" in selection:
        if not cycles:
            raise tag_error(ValueError(
                f"{context}: time.cycle unavailable; inputs have no forecast reference clock"
            ), "E1403")
        cycle = _selection_stamp(selection["cycle"], next(iter(cycles)))
        if not any(cycle == c for c in cycles):
            raise tag_error(ValueError(
                f"{context}: time.cycle {selection['cycle']} unavailable in selected files"
            ), "E1403")
        records = [r for r in records if r["cycle"] == cycle]
    elif len(cycles) > 1:
        raise tag_error(ValueError(
            f"{context}: several forecast cycles; select an exact sources.*.time.cycle"
        ), "E1403")
    times = sorted({r["time"] for r in records})
    if not times:
        raise tag_error(ValueError(f"{context}: no selected decoded records"), "E1402")
    if "values" in selection:
        wanted = [_selection_stamp(value, times[0]) for value in selection["values"]]
        missing = [value for value in wanted if not any(value == t for t in times)]
        if missing:
            raise tag_error(ValueError(
                f"{context}: time.values unavailable in selected files: {sorted(missing)}"
            ), "E1402")
        selected = [t for t in times if any(t == value for value in wanted)]
    else:
        start = _selection_stamp(selection["start"], times[0]) if "start" in selection else times[0]
        end = _selection_stamp(selection["end"], times[0]) if "end" in selection else times[-1]
        selected = [t for t in times if start <= t <= end][::selection.get("stride", 1)]
    if not selected:
        raise tag_error(ValueError(f"{context}: empty time selection; no selected records"), "E1402")
    selected_times = set(selected)
    return [r for r in records if r["time"] in selected_times], selected


def _source_file_entries(source, name):
    """A failed pattern must not hide independent metadata errors in other patterns."""
    patterns = source["files"] if isinstance(source["files"], list) else [source["files"]]

    def failure(exc, patterns):
        return Diagnostic(
            f"sources.{name}.files", str(exc), "readable selected input files",
            {"files": patterns, "exclude": source["exclude"], "cause": str(exc)},
            [f"Correct sources.{name}.files/exclude so required input files exist and match."],
            contexts=[{"source": name, "patterns": patterns}], code=exception_code(exc))

    try:
        entries, excluded, overlaps = inventory_source_files(source)
        return entries, excluded, overlaps, []
    except (OSError, ValueError) as original:
        if len(patterns) == 1:
            return [], [], [], [failure(original, patterns)]
        entries, excluded, overlaps, errors, identities = [], [], [], [], {}
        # Reuse discovery only after failure; these partial entries cannot grant clearance.
        for pattern in patterns:
            try:
                part, skipped, repeated = inventory_source_files({**source, "files": pattern})
            except (OSError, ValueError) as exc:
                errors.append(failure(exc, [pattern]))
                continue
            excluded.extend(skipped)
            overlaps.extend(repeated)
            for entry in part:
                identity = tuple(entry["identity"][key] for key in ("device", "inode"))
                if identity not in identities:
                    identities[identity] = entry
                    entries.append(entry)
                else:
                    known = identities[identity]
                    known["patterns"].extend(
                        item for item in entry["patterns"] if item not in known["patterns"])
        return entries, excluded, overlaps, errors or [failure(original, patterns)]


def _incomplete_mnh_altitude(fields, grids, selected, records, candidates):
    """Use the whole closed selection so per-sample operations see the same contract."""
    from frameit.io.netcdf_utils import mnh_native_level_attributes
    from frameit.processing.requests import _sample_context

    if not candidates or not selected:
        return []
    providers = {term: [] for term in candidates}
    for record in records:
        if record["name"] in providers:
            providers[record["name"]].append(record)
    samples = {_sample_context(record) for record in selected}
    missing = set()
    for term, matches in providers.items():
        available = {_sample_context(record) for record in matches}
        # Leave competing providers to the usual strict dependency checks.
        if (len({r["field_id"] for r in matches}) <= 1 and len(available) == len(matches)
                and samples - available):
            missing.add(term)
    if not missing:
        return []
    for field in fields.values():
        if omitted := {axis: term for axis, term in field.get(
                "altitude_formula_operands", {}).items() if term in missing}:
            field["incomplete_altitude_formulas"] = omitted
            for term in omitted.values():
                field["dependencies"].pop(term, None)
    for grid in grids.values():
        for axis, coordinate in grid["coordinates"].items():
            original = coordinate["attributes"]
            attrs = mnh_native_level_attributes(axis, coordinate["dimensions"], original, missing)
            if attrs is not original:
                coordinate.update(attributes=attrs, incomplete_altitude_formula=True)
    return sorted(missing)


def inventory_source(conf, name, *, resources=None):
    """Populate a v3 source's metadata handoff without binding or processing fields."""
    source = conf.sources[name]
    request = conf.source_requests[name]
    check_croco_zeta = ("zeta" in request["exports"].get("polar", [])
                        and "kind" not in source.get("field_metadata", {}).get("zeta", {}))
    entries, excluded, overlaps, errors = _source_file_entries(source, name)
    fields, grids, records, facts = {}, {}, [], []
    altitude_height_terms = set()
    with (DatasetResources() if resources is None else nullcontext(resources)) as owned:
        for entry in entries:
            path = Path(entry["path"])
            try:
                declared_format = source.get("format") or ("fa" if "profile" in source else None)
                fmt = infer_format([path], declared_format)
                reader = source.get("reader", {})
                if fmt != "fa" and reader.keys() & {
                        "python_executable", "timeout_seconds", "max_points"}:
                    raise ValueError("sources.*.reader: "
                                     "python_executable/timeout_seconds/max_points are FA-only")
                if fmt != "netcdf" and reader.keys() & {"engine", "chunks"}:
                    raise ValueError("sources.*.reader: engine/chunks are NetCDF-only")
                if fmt != "fa" and source.keys() & {"profile", "fa", "native_cubes"}:
                    raise ValueError("sources.*.profile/fa/native_cubes require FA inputs")
                engine = reader.get("engine", "h5netcdf")
                module = ({"netcdf4": "netCDF4"}.get(engine, engine) if fmt == "netcdf"
                          else "eccodes" if fmt == "grib" else None)
                if module:
                    _, dependency_error = _installed_dependency(
                        f"sources.{name}.reader.engine" if fmt == "netcdf"
                        else f"sources.{name}.format",
                        module, f"Install the selected {module} reader "
                        "in the selected environment.", code="E1006" if fmt == "netcdf" else "E1002")
                    if dependency_error:
                        raise PreflightError([dependency_error])
                if fmt == "netcdf":
                    info = _netcdf_inventory(path, source, owned, check_croco_zeta=check_croco_zeta)
                elif fmt == "grib":
                    info = _grib_source_inventory(path, source)
                else:
                    info = _fa_source_inventory(path, source, conf)
                facts.append((fmt, info["model"], info["physical_type"],
                              info["profile"], info["evidence"]))
                altitude_height_terms.update(info.get("altitude_height_terms", ()))
                for field_id, field in info["fields"].items():
                    previous = fields.get(field_id, {})
                    ids = set(previous.get("grid_ids", ())) | {field["grid_id"]}
                    if "levels" in field:
                        field["levels"] = sorted(
                            set(previous.get("levels", ())) | set(field["levels"]))
                    fields[field_id] = {**field, "grid_ids": sorted(ids),
                                        "grid_id": next(iter(ids)) if len(ids) == 1 else None}
                for grid_id, grid in info["native_grids"].items():
                    if grid_id not in grids:
                        grids[grid_id] = grid
                    else:
                        for coordinate, providers in grid.get("coordinate_providers", {}).items():
                            known = grids[grid_id]["coordinate_providers"][coordinate]
                            known.extend(
                                provider for provider in providers if provider not in known)
                records.extend(info["records"])
                if info.get("dataset_attributes"):
                    entry["dataset_attributes"] = info["dataset_attributes"]
                entry["fields"] = sorted({f["name"] for f in info["fields"].values()
                                          if f["name"] is not None})
                entry["unmapped_records"] = [r for r in info["records"] if r["name"] is None]
            except (OSError, ValueError, ImportError) as exc:
                if isinstance(exc, OSError):
                    tag_error(exc, "E1202")
                elif (isinstance(exc, ValueError) and not isinstance(exc, PreflightError)
                      and getattr(exc, "frameit_code", None) is None):
                    tag_error(exc, "E1207")
                diagnostics = exception_diagnostics(
                    exc, path=f"sources.{name}.files",
                    expected="readable admitted source metadata", observed={"cause": str(exc)},
                    repairs=[f"Correct the input or source declaration: {exc}"])
                for error in diagnostics:
                    if error.path.startswith("input."):
                        error.path = f"sources.{name}." + (
                            "model" if error.path == "input.model" else "files")
                    error.contexts.append({
                        "source": name, "file": str(path), "patterns": entry["patterns"]})
                errors.extend(diagnostics)
    if errors:
        raise PreflightError(errors)
    profiles = {fact[:4] for fact in facts}
    if len(profiles) != 1:
        raise tag_error(ValueError(
            f"sources.{name}: selected files have conflicting "
            f"model/format/physical profiles: {profiles}"
        ), "E1203")
    fmt, model, physical, profile = next(iter(profiles))
    if source.get("interpretation") and (fmt != "netcdf" or model != "mesonh"):
        raise ValueError(f"sources.{name}.interpretation requires Meso-NH NetCDF")
    request.pop("literal_product_fields", None)
    needed = {field for exports in request["exports"].values() for field in exports
              if field not in request["derived"]}
    product_only = needed.difference(*request["fields"].values())
    needed.update(set(request["internal_inputs"]) - request["derived"].keys())
    declared_needed = set(needed)
    strict_inputs = set(request["internal_inputs"]) - request["derived"].keys()
    required = set(needed)
    dependency_resolution = "declared"
    tracker = conf.yaml_config["region"].get("tracker")
    tracker_groups = {}
    if tracker and physical == "atmosphere":
        from frameit.io.loader import DEFAULT_PRESETS_ROOT, _load_yaml

        method = conf.tracking_method
        preset = (DEFAULT_PRESETS_ROOT / {"mesonh": "MNH", "arome": "AROME"}[model]
                  / "vars_trackers.yaml")
        if method in {"wind_pressure", "utrack"} or model == "arome":
            requirements = _load_yaml(preset)["requested_variables_by_method"][method]
            tracker_fields = {
                n for spec in requirements.values() for n in spec.get("variables", [])}
            if model == "arome":
                tracker_groups = {n: group for group, spec in requirements.items()
                                  if group != "surface" for n in spec.get("variables", [])}
            strict_inputs.update(tracker_fields)
            needed.update(tracker_fields)
            required.update(needed)
        else:
            # Preserve candidates for method binding, without choosing scientific alternatives.
            needed.update(field["name"] for field in fields.values())
            dependency_resolution = "pending_method_binding"
    if not needed:
        # An unfinished inspect request inventories all fields, not an invented selection.
        needed = {f["name"] for f in fields.values() if f["name"] is not None}
    if (source.get("interpretation") or source["transforms"] or request["internal_inputs"]
            or "polar" in request["exports"]
            or tracker and physical == "atmosphere"):
        dependency_resolution = "pending_method_binding"
    from frameit.core.configuration import field_selection

    selection_source = {"fields": fields, "native_grids": grids, "format": fmt}
    by_name = {}
    for index, record in enumerate(records):
        by_name.setdefault(record["name"], []).append((index, record))
    candidates = {ref: field_candidates(
        selection_source, request, ref, by_name, include_literal=ref in product_only)
        for ref in needed}
    for ref, group in tracker_groups.items():
        if ref not in declared_needed:
            candidates[ref] = [(i, r) for i, r in candidates[ref]
                               if fields[r["field_id"]].get("group") == group
                               or fmt == "netcdf" and group in fields[r["field_id"]]["dimensions"]]
    by_field_name = {}
    for field_id, field in fields.items():
        by_field_name.setdefault(field["name"], []).append(field_id)
    pending = list(required)
    while pending:
        field_name = pending.pop()
        for _, record in candidates.get(field_name, []):
            field = fields[record["field_id"]]
            altitude = field.get("altitude_formula_operands", {}).values()
            for dep in field.get("dependencies", {}):
                if dep in altitude:
                    continue  # Evaluate this metadata edge after closing the sample selection.
                if dep not in required:
                    required.add(dep)
                    needed.add(dep)
                    candidates[dep] = field_candidates(selection_source, request, dep, by_name)
                    pending.append(dep)
                strict_inputs.add(dep)
    missing = {ref for ref in required if not candidates.get(ref)}
    if missing:
        raise PreflightError([Diagnostic(
            f"sources.{name}.variables",
            f"required fields/dependencies {sorted(missing)} unavailable in selected files",
            {"required_fields": sorted(required)},
            {"available_fields": sorted(n for n in by_field_name if n is not None),
             "missing_fields": sorted(missing)},
            [f"Select files containing {', '.join(sorted(missing))}, "
             "or correct the required field names. "
             "Dependencies cannot widen the authored files/time selection."],
             contexts=[{"source": name, "files": [entry["path"] for entry in entries]}],
             code="E1302")])
    relevant_indices = {i for ref in needed for i, _ in candidates.get(ref, [])}
    relevant = [r for i, r in enumerate(records) if i in relevant_indices]
    if not relevant and not required and not tracker and not source.get("time"):
        selected, times = [], []
    else:
        selected, times = _select_source_records(
            relevant, source.get("time", {}), f"sources.{name}")
    errors, providers, conflicts, allowed_gaps = [], {}, [], []
    required_ids = {ref: {r["field_id"] for _, r in candidates[ref]} for ref in required}
    grouped_levels = {group for group, spec in request.get("groups", {}).items()
                      if spec.get("levels")}
    for field_name in sorted(required):
        matching = [r for r in selected if r["field_id"] in required_ids[field_name]]
        identities = {r["field_id"] for r in matching}
        if len(identities) > 1:
            definitions = [
                 {"identity": identity, "dimensions": fields[identity]["dimensions"],
                  "group": fields[identity].get("group"), "grids": fields[identity]["grid_ids"],
                  "attributes": fields[identity]["attributes"],
                  "coordinate_attributes": {
                      grid_id: {key: coordinate["attributes"]
                                for key, coordinate in grids[grid_id]["coordinates"].items()}
                      for grid_id in fields[identity]["grid_ids"]},
                  "dataset_attributes": fields[identity].get("dataset_attributes", {}),
                 "providers": sorted({r["locator"]["path"] for r in selected
                                      if r["field_id"] == identity})}
                for identity in sorted(identities)]
            errors.append(f"sources.{name}: distinct fields share requested name {field_name!r}; "
                          f"conflicting fields {definitions}; "
                          "use an explicit vertical group; qualification must identify "
                            "exactly one field. For files in the same group, "
                            "select or regenerate a consistent sequence")
        elif matching and field_name in product_only:
            record = matching[0]
            if record["name"] == field_name and field_selection(request, field_name)[1] is not None:
                request.setdefault("literal_product_fields", []).append(field_name)
            if grouped_levels and field_selection(request, field_name)[1] is None:
                field = fields[record["field_id"]]
                group = native_field_group(selection_source, field, record)
                if group in grouped_levels and (fmt != "grib" or _field_axis(
                        selection_source, field, record, by_name) is not None):
                    errors.append(
                        f"sources.{name}: use {group}.{field_name} to retain group levels")
        available = {r["time"] for r in matching}
        from frameit.processing.requests import initial_gap_times

        allowed = (initial_gap_times({
            **selection_source, "selected_times": times, "records": selected,
            "declaration": source},
            field_name, matching) if field_name not in strict_inputs else set())
        allowed_gaps.extend({"field": field_name, "time": time,
                             "reason": "declared_initial_absence"} for time in sorted(allowed))
        if field_name in required and set(times) - available - allowed:
            errors.append(f"sources.{name}: {field_name} unavailable at selected times "
                          f"{sorted(set(times) - available)}; "
                          "dependencies cannot widen the inventory")
    for record in selected:
        key = (record["field_id"], record["time"], record["cycle"], record["level"],
               tuple(sorted(record.get("native_axes", {}).items())))
        if key in providers:
            pending_status = None
            references = [ref for ref, ids in required_ids.items() if record["field_id"] in ids]
            if not references:
                pending_status = ("pending_method_binding"
                                  if dependency_resolution == "pending_method_binding"
                                  else "pending_field_binding")
            elif fmt == "grib" and any(
                    ref in (product_only | set(request["fields"]["3d"])
                            | set(request["internal_inputs"]) - set(request["fields"]["2d"]))
                    and field_selection(request, ref)[2].keys() & {"indices", "values", "domain"}
                    for ref in references):
                pending_status = "pending_level_binding"
            if pending_status:
                # Binding must reject any required conflict; neither provider is chosen here.
                conflicts.append({**{k: record[k] for k in (
                    "field_id", "name", "time", "cycle", "level")},
                    "native_axes": record.get("native_axes", {}),
                    "locators": [providers[key], record["locator"]],
                    "status": pending_status})
            else:
                errors.append(
                    f"sources.{name}: competing physical-field providers for {record['name']} "
                    f"at {record['time']}, cycle {record['cycle']}, level {record['level']}, "
                    f"native axes {record.get('native_axes', {})}: "
                    f"{providers[key]} and {record['locator']}. Use files, exclude or time.cycle; "
                    "if whole-file exclusion loses needed records, "
                    "make inputs unambiguous upstream.")
        providers[key] = record["locator"]
    if errors:
        raise tag_error(ValueError("\n".join(errors)), "E1302")
    selected.sort(key=lambda r: (r["time"], r["name"], r["field_id"], str(r["level"])))
    selected_times = set(times)
    selected_cycles = {r["cycle"] for r in selected}
    record_inventory = sorted(
        (r for r in records if r["time"] in selected_times and r["cycle"] in selected_cycles),
        key=lambda r: (r["time"], r["name"] or "", r["field_id"], str(r["level"])))
    missing_altitude = (_incomplete_mnh_altitude(
        fields, grids, selected, record_inventory, altitude_height_terms)
                         if model == "mesonh" and fmt == "netcdf" else [])
    for grid in grids.values():
        for providers in grid.get("coordinate_providers", {}).values():
            for provider in providers:
                provider["samples"] = [
                    sample for sample in provider["samples"]
                    if sample["time"] in selected_times and sample["cycle"] in selected_cycles]
    selected_paths = list(dict.fromkeys(r["locator"]["path"] for r in selected))
    relevant_paths = {r["locator"]["path"] for r in relevant}
    candidate_paths = {r["locator"]["path"] for r in record_inventory}
    for entry in entries:
        entry["status"] = ("metadata_only" if not records and not required else
                           "selected" if entry["path"] in selected_paths else
                           "time_excluded" if entry["path"] in relevant_paths else
                           "dependency_pending" if dependency_resolution == "pending_method_binding"
                           and entry["path"] in candidate_paths else "irrelevant")
        entry["reason"] = {
            "metadata_only": "available field metadata; no decoded sample clock",
            "selected": "supplies selected records",
            "time_excluded": "no records in the source time/cycle selection",
            "irrelevant": "metadata proves no requested field or required dependency",
            "dependency_pending": "method dependency binding must decide relevance",
        }[entry["status"]]
    result = conf.simulation_parameter["request_plan"]["sources"][name]
    result["requests"].pop("literal_product_fields", None)
    if "literal_product_fields" in request:
        result["requests"]["literal_product_fields"] = list(request["literal_product_fields"])
    result.update(model=model, physical_type=physical, format=fmt, profile=profile,
                  files=selected_paths, file_inventory=entries, excluded_files=excluded,
                  overlapping_patterns=overlaps, fields=fields, native_grids=grids,
                  records=selected, record_inventory=record_inventory, selected_times=times,
                  dependency_resolution=dependency_resolution, provider_conflicts=conflicts,
                  tracker_input_groups=tracker_groups)
    if missing_altitude:
        result["missing_mnh_altitude_operands"] = missing_altitude
    else:
        result.pop("missing_mnh_altitude_operands", None)
    if allowed_gaps:
        result["allowed_gaps"] = allowed_gaps
    result["pending_operations"] = [
        operation for operation, pending in (
            ("interpretation", source.get("interpretation")),
            ("transforms", source["transforms"]), ("derived", request["internal_inputs"]),
            ("polar", "polar" in request["exports"]),
            ("tracker", tracker and physical == "atmosphere"))
        if pending]
    result["metadata_origins"] = {
        "model": {"origin": "yaml" if ("model" in source or fmt == "fa"
                                     and profile == "arome_history") else "input",
                  "evidence": [item for fact in facts for item in fact[4]]},
        "physical_type": {"origin": "input",
                          "evidence": {"model": model, "format": fmt, "profile": profile}},
        "format": {"origin": "yaml" if "format" in source else "input", "evidence": "file header"},
    }
    if fmt != "fa":
        from frameit.processing.requests import sea_interpretation, source_field_metadata

        origins = {}
        for record in selected:
            if not any(record["field_id"] in ids for ids in required_ids.values()):
                continue
            field = fields[record["field_id"]]
            metadata = source_field_metadata(result, field, record=record)
            if metadata is not None:
                origins.setdefault(field["name"], metadata["origins"])
                if "observed_attributes" in record:
                    record["field_metadata"] = metadata
        result["metadata_origins"]["field_metadata"] = origins
        if source.get("interpretation"):
            result["interpretation"] = sea_interpretation(selected)
    conf.file_type = fmt
    conf.atm_model = {"mesonh": "MNH", "arome": "AROME", "nemo": "NEMO", "croco": "CROCO"}[model]
    conf.input_files = selected_paths
    conf.add_parameter("input_inventory", list(selected_paths))
    _available_source_selectors(result)
    return result


def _available_source_selectors(source):
    """Reuse the binder's axis evidence, without binding or checking scientific values."""
    from frameit.processing.requests import _field_axis, _vertical_axis, native_field_group

    source["available_selectors"], source["selection_pending"] = [], []
    by_name, records_by_name = {}, {}
    for field_id, field in source["fields"].items():
        by_name.setdefault(field["name"], []).append((field_id, field))
    for index, record in enumerate(source["record_inventory"]):
        records_by_name.setdefault(record["name"], []).append((index, record))
    for name, fields in by_name.items():
        if name is None:
            continue
        evidenced = []
        for field_id, field in fields:
            records = [(i, r) for i, r in records_by_name.get(name, [])
                       if r["field_id"] == field_id]
            if source["record_inventory"] and not records:
                continue
            try:
                if source["format"] == "fa":
                    if field.get("dimensions") is None:
                        raise ValueError(f"{name}: native shape is unresolved")
                    axis = field.get("native_cube")
                elif records:
                    axis = _field_axis(source, field, records[0][1], records_by_name)
                else:
                    axis = _vertical_axis(field, source["native_grids"][field["grid_id"]])
                group = native_field_group(source, field, records[0][1] if records else None)
            except ValueError as exc:
                source["selection_pending"].append(str(exc))
                continue
            evidenced.append((field_id, axis, group))
        for field_id, axis, group in evidenced:
            conflict = any(c["field_id"] == field_id for c in source["provider_conflicts"])
            if len(fields) > 1:
                matching = [entry for entry in evidenced if entry[2] == group]
                if (axis is None or not group or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", group)
                        or len(matching) != 1 or conflict):
                    source["selection_pending"].append(
                        f"{name}: select unambiguous files/exclude/time.cycle; "
                        "the native vertical group does not identify one available field.")
                    continue
                selector = {"field": f"{group}.{name}",
                            "variables": {"3d": {group: {"names": [name]}}}}
            elif conflict:
                source["selection_pending"].append(
                    f"{name}: select unambiguous files/exclude/time.cycle "
                    "before selecting this field.")
                continue
            else:
                selector = {
                    "field": name, "variables": {"3d" if axis is not None else "2d": [name]}}
            source["available_selectors"].append(selector)
    if not source["selected_times"]:
        source["selection_pending"].append("A decoded sample clock is required before execution.")


def _installed_dependency(path, module, repair, *, code):
    available = importlib.util.find_spec(module) is not None
    fact = {"path": path, "module": module, "available": available,
            "scope": "installed module; runtime initialization remains deferred"}
    error = None if available else Diagnostic(
        path, f"Selected feature requires {module}", {"module": module, "available": True},
        {"module": module, "available": False}, [repair], code=code)
    return fact, error


def _required_dependencies(conf, execution_options=None):
    """Probe only consumers selected by the request, without importing optional backends."""
    from frameit.core.configuration import resolved_configuration

    selected = []
    if any("polar" in request["exports"] for request in conf.source_requests.values()):
        selected.append(("products.polar", "xesmf", "FrameIt's polar extra"))
    if conf.tracking_method == "utrack":
        selected.extend(("region.tracker", module, "the selected UTrack environment")
                        for module in ("torch", "utrack"))
    products = conf.simulation_parameter["request_plan"]["products"]
    export = execution_options is None or execution_options.export_netcdf
    output = resolved_configuration(conf, execution_options)["output"]
    if products and export and output["format"] == "netcdf":
        engine = output["writer"]["engine"]
        selected.append(("output.writer.engine", {"netcdf4": "netCDF4"}.get(engine, engine),
                         f"the {engine} writer dependency"))
    facts, errors = [], []
    for path, module, installation in selected:
        repair = ("UTrack v3 execution is unavailable; select another tracker."
                  if path == "region.tracker" else
                  f"Install {installation} in the selected environment, or deselect this feature.")
        code = "E1004" if module == "xesmf" else (
            "E1006" if path == "output.writer.engine" else "E1502")
        fact, error = _installed_dependency(path, module, repair, code=code)
        facts.append(fact)
        if error:
            errors.append(error)
    if products and export and output["format"] == "zarr":
        from frameit.io.zarr_export import check_zarr_dependencies

        try:
            check_zarr_dependencies()
        except (ValueError, ImportError) as exc:
            errors.append(Diagnostic(
                "output.format", str(exc), "xarray>=2026.9.0 and zarr>=3.4.2,<4",
                {"cause": str(exc)}, ["Install FrameIt's zarr extra, or select NetCDF output."],
                code="E1005"))
        else:
            facts.append({"path": "output.format", "module": "zarr", "available": True,
                          "scope": "supported installed xarray/Zarr versions"})
    return facts, errors


def bind_source(conf, name, *, representations=None, required_inputs=(), resources=None):
    """Bind inventoried inputs using coordinate/static support, not scientific field payloads."""
    source = conf.simulation_parameter["request_plan"]["sources"][name]
    request = conf.source_requests[name]
    # A failed rebind must never retain executable clearance from an earlier selection.
    request["binding"] = None
    source["requests"]["binding"] = None
    source["field_binding"] = None
    if conf.yaml_config["region"].get("tracker") and source["physical_type"] == "atmosphere":
        from frameit.tracking.tracker_core import resolve_tracker_support

        source.pop("tracker_support", None)
        try:
            source["tracker_support"] = resolve_tracker_support(conf, source)
        except ValueError as exc:
            raise tag_error(exc, "E1503")
        required_inputs = source["tracker_support"]["inputs"]
    from frameit.processing.requests import bind_source_operations

    binding = (bind_requests({**source, "name": name}, request,
                             representations=representations, required_inputs=required_inputs)
               if representations is not None else
                bind_source_operations(
                    {**source, "name": name}, request, conf, required_inputs=required_inputs))
    if source["model"] == "croco" and source["format"] == "netcdf":
        from frameit.io.croco_utils import validate_bound_support

        validate_bound_support(source, binding, engine=conf.netcdf_engine, resources=resources)
    source["field_binding"] = binding
    source["representation_grids"] = deepcopy(binding.get("representation_grids", {}))
    source["metadata_origins"]["field_metadata"] = {
        field: descriptor["field_metadata"]["origins"]
        for descriptors in (*binding["products"].values(), binding["dependencies"])
        for field, descriptor in descriptors.items() if "field_metadata" in descriptor}
    if "interpretation" in binding:
        source["interpretation"] = deepcopy(binding["interpretation"])
    for warning in binding["warnings"]:
        logging.getLogger(__name__).warning(warning)
    plan = conf.simulation_parameter["request_plan"]
    plan["warnings"] = list(dict.fromkeys([*plan["warnings"], *binding["warnings"]]))
    if binding["status"] == "bound":
        _publish_source_binding(conf, name, binding)
    return binding


def _publish_source_binding(conf, name, binding):
    """Publish an already-finalized binding without rediscovery or a second bind."""
    if binding["status"] != "bound":
        raise ValueError("Cannot publish unfinished source binding")
    plan = conf.simulation_parameter["request_plan"]
    source = plan["sources"][name]
    source["records"] = binding["records"]
    source["files"] = list(dict.fromkeys(r["locator"]["path"] for r in source["records"]))
    source["provider_conflicts"] = []
    for entry in source["file_inventory"]:
        if entry["path"] in source["files"]:
            entry.update(status="selected", reason="supplies bound fields or required support")
        elif entry["status"] != "time_excluded":
            entry.update(status="irrelevant",
                         reason="metadata proves no bound field or required dependency")
    conf.source_requests[name]["binding"] = binding
    source["requests"]["binding"] = binding
    if conf.source_name == name:
        conf.input_files = list(source["files"])
    conf.add_parameter("input_inventory", {
        n: list(s["files"]) for n, s in plan["sources"].items()})
    for product in plan["products"]:
        if product["source"] == name and product["product"] == "model_grid":
            describe_model_grid_output(
                source, binding, product, regional=bool(conf.x_boxsize_km and conf.y_boxsize_km))


def describe_model_grid_output(source, binding, product, *, regional=False):
    """Preview the same exported axis names used by dataset assembly."""
    from frameit.io.netcdf_export import _output_grid_facts, output_grid_layout

    layout = output_grid_layout(source, regional=regional)
    product.update(stored_names={}, dimensions={}, units={})
    for name in product["fields"]:
        descriptor = binding["products"]["model_grid"][name]
        for record in descriptor["records"]:
            grid_id = record["selection_grid_id"]
            grid = (source["native_grids"].get(grid_id)
                    or source.get("representation_grids", {})[grid_id])
            vertical = record.get("vertical")
            field = source["fields"][record["field_id"]]
            # FA summaries can include an excluded record with unknown shape.
            dims = (list(grid["dimensions"]) if source["format"] == "fa"
                    or descriptor.get("operation") else
                    [dim for dim in field["dimensions"]
                     if dim in grid["dimensions"] or dim in record.get("native_axes", {})])
            if vertical and vertical["dimension"] not in dims:
                dims.insert(0, vertical["dimension"])
            if source["format"] in {"grib", "fa"}:
                dims = [*record.get("native_axes", {}), *dims]
            if descriptor.get("operation"):
                dims = [dim for dim in dims if dim in grid["dimensions"]]
                if vertical and vertical["dimension"] not in dims:
                    dims.insert(0, vertical["dimension"])
            facts = _output_grid_facts(layout, grid_id, name)
            exported = [facts["dimensions"].get(dim, dim) for dim in dims]
            if (field["time_varying"] or descriptor.get("operation")
                    or len({r["locator"]["path"] for r in descriptor["records"]}) > 1
                    or any(gap["field"] == name for gap in source.get("allowed_gaps", []))
                    or source["format"] in {"grib", "fa"}):
                exported.insert(0, "time")
            previous = product["dimensions"].setdefault(name, exported)
            if previous != exported:
                # The owning reader still rejects unrepresentable native-axis mixtures.
                product["dimensions"][name] = None
        product["stored_names"][name] = name
        product["units"][name] = descriptor.get(
            "result_units", field["attributes"].get("units"))


def _describe_v3_unbound_resources(conf, execution_options=None):
    """Resolve execution budgets without selecting fields or claiming applied layouts."""
    from frameit.core.configuration import resolved_configuration, resolved_sources
    from frameit.core.execution import ExecutionOptions
    from frameit.core.runtime import resolve_execution_resources

    options, resources = resolve_execution_resources(
        execution_options or ExecutionOptions.from_config(conf))
    layouts = {
        "pending": "field/method binding",
        "inputs": {
            name: {"requested": dict(source.get("reader", {}).get("chunks", {})),
                   "applications": [], "estimates": None}
            for name, source in conf.sources.items()
        },
        "products": {},
        "writer": {
            "requested": {
                "chunks": dict(options.zarr_chunk_size if options.engine == "zarr"
                               else options.netcdf_chunk_size),
                "shards": dict(options.zarr_shard_size),
            },
            "chunks": None, "shards": None,
        },
    }
    for item in conf.simulation_parameter["request_plan"]["products"]:
        key = f"{item['source']}.{item['product']}" if item["source"] else "track"
        spec = conf.yaml_config["products"][item["product"]]
        chunks = spec.get("processing", {}).get("chunks", {}) if isinstance(spec, dict) else {}
        layouts["products"][key] = {
            "requested": dict(chunks), "applicable_dimensions": None, "applied_settings": None,
            "resolved_chunks": "pending field/method binding",
        }
    return {"execution_resources": resources, "layouts": layouts,
            "configuration": resolved_configuration(conf, options),
            "setting_sources": resolved_sources(conf, options)}


def describe_v3_resources(conf, sources, execution_options=None):
    """Describe bounded concurrency and match layout namespaces on already-bound metadata."""
    from frameit.core.execution import ExecutionOptions
    from frameit.core.runtime import resolve_execution_resources
    from frameit.io.netcdf_utils import input_chunk_plan

    options, resources = resolve_execution_resources(
        execution_options or ExecutionOptions.from_config(conf))
    products = conf.simulation_parameter["request_plan"]["products"]
    layouts = {"inputs": {}, "products": {}, "writer": {}}
    for name, source in sources.items():
        binding = source["requests"]["binding"]
        chunks = conf.sources[name].get("reader", {}).get("chunks", {})
        layout = (input_chunk_plan(source, chunks) if source["format"] == "netcdf" else {
            "requested": {}, "applications": [],
            "decoder": "full native record per selected locator"})
        estimates = []
        full_records = []
        unknown_dtypes = set()
        for record in binding["records"]:
            field = source["fields"][record["field_id"]]
            grid = source["native_grids"][record["grid_id"]]
            sizes = dict(grid["dimensions"])
            if not field.get("dtype"):
                unknown_dtypes.add(field["name"])
                continue
            itemsize = np.dtype(field["dtype"]).itemsize
            full_records.append(int(np.prod(list(sizes.values()), dtype=object)) * itemsize)
            if record.get("vertical"):
                sizes[record["vertical"]["dimension"]] = len(record["source_positions"])
            estimates.append(int(np.prod(list(sizes.values()), dtype=object)) * itemsize)
        layout["estimates"] = {
            "selected_native_arrays_bytes": None if unknown_dtypes else sum(estimates),
            "largest_full_native_record_bytes": (None if unknown_dtypes
                                                else max(full_records, default=0)),
            "unresolved_dtype_fields": sorted(unknown_dtypes),
            "scope": "uncompressed bound input records; repeated consumers may reuse data",
            "unresolved": (
                "decoder workspace, backend caches, transform/mask/interpolation temporaries "
                "and compressed storage; these estimates are not a memory ceiling"
            ),
        }
        layouts["inputs"][name] = layout
    dimensions = {}
    for item in products:
        key = f"{item['source']}.{item['product']}" if item["source"] else "track"
        dims = ({"time"} if item["product"] == "track" else {
            dim for axes in item["dimensions"].values() if axes for dim in axes})
        if item["source"]:
            from frameit.io.netcdf_export import _output_grid_facts, output_grid_layout

            source = sources[item["source"]]
            binding = source["requests"]["binding"]
            layout = output_grid_layout(
                source, regional=(item["product"] == "model_grid"
                                  and bool(conf.x_boxsize_km and conf.y_boxsize_km)))
            for descriptor in binding["products"][item["product"]].values():
                for record in descriptor["records"]:
                    facts = _output_grid_facts(layout, record["selection_grid_id"],
                                               descriptor.get("operation") or record["name"])
                    dims.update(target for view in facts.get("support_views", {}).values()
                                for target in view["dimensions"].values())
                    vertical = record.get("vertical")
                    if vertical:
                        dims.update(facts["dimensions"].get(dim, dim)
                                    for coord in vertical["coordinates"].values()
                                    for dim in coord["dimensions"])
        dimensions[key] = dims
        spec = conf.yaml_config["products"][item["product"]]
        requested = spec.get("processing", {}).get("chunks", {}) if isinstance(spec, dict) else {}
        layouts["products"][key] = {
            "requested": dict(requested), "applicable_dimensions": sorted(dims),
            "applied_settings": {dim: size for dim, size in requested.items() if dim in dims},
            "resolved_chunks": "pending selected lazy product construction",
        }
    for product, spec in conf.yaml_config["products"].items():
        requested = spec.get("processing", {}).get("chunks", {}) if isinstance(spec, dict) else {}
        applicable = {dim for item in products if item["product"] == product
                      for dim in dimensions[
                          f"{item['source']}.{product}" if item["source"] else "track"]}
        unknown = set(requested) - applicable
        if unknown:
            raise tag_error(ValueError(
                f"Unknown {product} processing chunks dimensions: {sorted(unknown)}"
            ), "E1805")
    field_keys = [key for key in dimensions if key != "track"] or list(dimensions)
    storage_chunks = (options.zarr_chunk_size if options.engine == "zarr"
                      else options.netcdf_chunk_size)
    for setting, sizes in (("chunks", storage_chunks), ("shards", options.zarr_shard_size)):
        unknown = set(sizes) - {dim for key in field_keys for dim in dimensions[key]}
        if unknown:
            raise tag_error(ValueError(
                f"Unknown output writer {setting} dimensions: {sorted(unknown)}"
            ), "E1805")
        layouts["writer"][setting] = {
            key: {dim: size for dim, size in sizes.items() if dim in dimensions[key]}
            for key in field_keys}
    from frameit.core.configuration import resolved_configuration, resolved_sources

    return {"execution_resources": resources, "layouts": layouts,
            "configuration": resolved_configuration(conf, options),
            "setting_sources": resolved_sources(conf, options)}


def open_metadata(files, conf, resources, *, chunks=None):
    """Open lazily with no disk indexes, closing originals on all error paths."""
    if conf.file_type == "netcdf" and getattr(conf, "netcdf_file_layout", "time_series") == "variables":
        from frameit.io.netcdf_utils import _merge_variable_shards, normalize_netcdf_time

        opened = [normalize_netcdf_time(resources.open_netcdf(
            path, engine=conf.netcdf_engine, chunks=chunks), conf) for path in files]
        requested = set()
        selected_pairs = []
        for native, request in (
                (conf.cartesian_horizontal_winds == "native", conf.requests_user()),
                (False, conf.requests_tracker().get(conf.tracking_method, {}))):
            expanded, pairs = wind_dependencies(conf, request, native=native)
            selected_pairs.extend(pairs)
            requested.update(name for spec in expanded.values() for name in spec.get("variables", [])
                             if name != "wind_speed")
        requested.update(name for name in (conf.name_latitude, conf.name_longitude)
                         if any(name in ds for ds in opened))
        metadata = MESONH_PROJECTION_METADATA if conf.atm_model == "MNH" and selected_pairs else ()
        merged = _merge_variable_shards(opened, requested, metadata=metadata)
        merged.attrs = dict(merged.attrs, _frameit_variable_providers={
            name: str(path) for path, ds in zip(files, opened) for name in ds.data_vars
            if name in requested})
        yield files[0], [merged]
        return
    fa_geometries = {}
    fa_vertical_signature = None
    for path in files:
        if conf.file_type == "fa":
            from frameit.io.fa_geometry import fa_geometry, geometry_signature
            from frameit.io.fa_utils import (
                fa_field_names,
                fa_metadata_dataset,
                inspect_fa_inputs,
            )

            dependencies, _ = wind_dependencies(
                conf, conf.requests_user(), native=conf.cartesian_horizontal_winds == "native")
            info = inspect_fa_inputs(path, conf, fa_field_names(dependencies))
            if info["native_cubes"]:
                from frameit.io.fa_cubes import vertical_signature

                current = vertical_signature(info)
                if fa_vertical_signature is not None and current != fa_vertical_signature:
                    raise ValueError("Selected FA inputs have incompatible "
                                     "native vertical definitions")
                fa_vertical_signature = current
            signature = geometry_signature(info["geometry"], conf.fa_options)
            if signature not in fa_geometries:
                fa_geometries[signature] = fa_geometry(info["geometry"], conf.fa_options)
            datasets = [fa_metadata_dataset(info, conf.fa_options, fa_geometries[signature])]
            records = conf.simulation_parameter.setdefault("fa_inventory", [])
            model = info["geometry"]["epygram"]["earth_model"]
            records.append({"source_id": path.name, "valid_time": info["valid_time"],
                            "reference_time": info["reference_time"],
                            "backend_versions": info["backend_versions"],
                            "fields": info["field_definitions"], "encoding": info["fields"],
                            "protocol_version": info["protocol_version"],
                            "field_descriptors": info["field_descriptors"],
                            "expected_source": conf.fa_options["expected_source"],
                            "producer_metadata": info["surfex_metadata"],
                            "profile": conf.fa_options["profile"],
                            "subdomain": conf.fa_options["subdomain"],
                            "earth_radius_m": model["radius_m"],
                            "earth_model_origin": model["origin"]})
            records[-1]["horizontal_header_signature"] = signature
            records[-1]["grid_lookup"] = fa_geometries[signature].attrs["fa_grid_lookup"]
            records[-1]["geometry_contract"] = info["geometry"].get("epygram")
            records[-1].update(native_cubes=info["native_cubes"],
                               hybrid_contract=info.get("hybrid_contract"),
                               backend=info["backend_versions"]["FA_backend"],
                               requested_backend=conf.fa_options["backend"])
        elif conf.file_type == "grib":
            datasets = _grib_metadata(path)
        else:
            from frameit.io.netcdf_utils import normalize_netcdf_time

            original = resources.open_netcdf(path, engine=conf.netcdf_engine, chunks=chunks)
            datasets = [normalize_netcdf_time(original, conf)]
        for ds in datasets:
            resources.add(ds)
        yield path, datasets


def _grib_metadata(path):
    """One header scan, no field decoding or repeated cfgrib index builds."""
    from datetime import datetime

    import eccodes as ec

    from frameit.io.grib_utils import GRIB_PRESSURE_UNITS

    aliases = {"10u": "u10", "10v": "v10", "msl": "prmsl"}
    groups, geometry, signature = {}, None, None
    unmapped, all_times = [], set()
    with Path(path).open("rb") as stream:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                def get(key):
                    return ec.codes_get(handle, key)

                shape = int(get("Nj")), int(get("Ni"))
                current = tuple(get(k) for k in (
                    "gridType", "Nj", "Ni", "latitudeOfFirstGridPointInDegrees",
                    "longitudeOfFirstGridPointInDegrees", "latitudeOfLastGridPointInDegrees",
                    "longitudeOfLastGridPointInDegrees", "scanningMode"))
                if signature is not None and current != signature:
                    raise ValueError(f"{path}: inconsistent GRIB message grids")
                signature = current
                if (ec.codes_is_defined(handle, "productDefinitionTemplateNumber")
                        and int(get("productDefinitionTemplateNumber")) == 32):
                    # Satellite products do not carry atmospheric level keys.
                    continue
                if geometry is None:
                    lat = np.asarray(ec.codes_get_array(handle, "latitudes"))
                    lon = np.asarray(ec.codes_get_array(handle, "longitudes"))
                    jfast = int(get("jPointsAreConsecutive"))
                    lat = lat.reshape(shape[::-1]).T if jfast else lat.reshape(shape)
                    lon = lon.reshape(shape[::-1]).T if jfast else lon.reshape(shape)
                    geometry = xr.Dataset(coords={
                        "latitude": (("y", "x"), lat, {"units": "degrees_north"}),
                        "longitude": (("y", "x"), lon, {"units": "degrees_east"})})
                short = str(get("shortName"))
                try:
                    name = str(get("cfVarName"))
                except ec.CodesInternalError:
                    name = short
                if name in {"unknown", "undef", ""} or short in {"u", "v"}:
                    name = short
                name = aliases.get(name, aliases.get(short, name))
                group = str(get("typeOfLevel"))
                date = f"{int(get('validityDate')):08d}{int(get('validityTime')):04d}"
                stamp = np.datetime64(datetime.strptime(date, "%Y%m%d%H%M"), "ns")
                all_times.add(stamp)
                if name in {"unknown", "undef", ""}:
                    unmapped.append({"param_id": int(get("paramId")), "short_name": short,
                                     "type_of_level": group, "level": float(get("level")),
                                     "valid_time": str(stamp)})
                    continue
                if name in {"u10", "v10", "prmsl"} or group in {"surface", "meanSea"}:
                    group = "surface"
                entry = groups.setdefault(group, {"fields": {}, "levels": set(), "times": set(),
                                                  "coverage": {}, "references": set()})
                attrs = {"units": str(get("units"))}
                if ec.codes_is_defined(handle, "uvRelativeToGrid"):
                    attrs["GRIB_uvRelativeToGrid"] = int(get("uvRelativeToGrid"))
                if name in entry["fields"] and entry["fields"][name].attrs != attrs:
                    raise ValueError(f"{path}: inconsistent units/wind flags on {group}.{name}")
                entry["fields"][name] = xr.DataArray(0., attrs=attrs)
                entry["levels"].add(float(get("level")))
                basis = f"{int(get('dataDate')):08d}{int(get('dataTime')):04d}"
                entry["references"].add(str(np.datetime64(
                    datetime.strptime(basis, "%Y%m%d%H%M"), "ns")))
                entry["times"].add(stamp)
                entry["coverage"].setdefault(name, []).append((float(get("level")), str(stamp)))
            finally:
                ec.codes_release(handle)
    if geometry is None:
        raise ValueError(f"{path}: no GRIB messages")
    geometry = geometry.assign_coords(valid_time=("valid_time", sorted(all_times)))
    geometry.attrs["_frameit_unmapped_grib_records"] = unmapped
    datasets = [geometry]
    for group, entry in groups.items():
        for name, value in entry["fields"].items():
            value.attrs["_frameit_level_times"] = entry["coverage"][name]
        coords = {"valid_time": sorted(entry["times"])}
        if group != "surface":
            units = {**GRIB_PRESSURE_UNITS, "heightAboveGround": "m"}.get(group)
            dimension = "isobaric" if group in GRIB_PRESSURE_UNITS else group
            coords[dimension] = (dimension, sorted(entry["levels"]), {"units": units})
        datasets.append(xr.Dataset(entry["fields"], coords=coords, attrs={
            "_frameit_vertical_group": "isobaric" if group in GRIB_PRESSURE_UNITS else group,
            "_frameit_forecast_reference_times": sorted(entry["references"])}))
    return datasets


def infer_format(files, declared=None):
    if declared == "fa":
        # Native FA is structurally verified by the isolated metadata reader;
        # no extension guess or attempt to send unknown bytes to NetCDF.
        for path in files:
            with Path(path).open("rb") as handle:
                magic = handle.read(8)
            if magic.startswith((b"GRIB", b"CDF")) or magic == b"\x89HDF\r\n\x1a\n":
                detected = "grib" if magic.startswith(b"GRIB") else "netcdf"
                raise tag_error(ValueError(
                    f"Declared source format fa conflicts with detected {detected}: {path}"
                ), "E1203")
        return "fa"
    formats = set()
    for path in files:
        with Path(path).open("rb") as handle:
            magic = handle.read(8)
        if magic.startswith(b"GRIB"):
            formats.add("grib")
        elif magic.startswith(b"CDF") or magic == b"\x89HDF\r\n\x1a\n":
            formats.add("netcdf")
        else:
            raise PreflightError([Diagnostic(
                "input.format", "Unsupported input file format",
                {"formats": ["netcdf", "grib", "declared fa"]}, {"magic_hex": magic.hex()},
                ["Select readable NetCDF/GRIB inputs, or declare an admitted FA profile for FA."],
                code="E1202")])
    if len(formats) != 1:
        raise tag_error(ValueError("Mixed GRIB/NetCDF inputs are not supported"), "E1203")
    detected = formats.pop()
    if declared and declared not in {detected, "nc" if detected == "netcdf" else "grib2"}:
        raise tag_error(ValueError(
            f"Declared source format {declared} conflicts with detected {detected}"
        ), "E1203")
    return detected


def _check_requests(datasets, requests, path, *, tolerance=.5):
    errors = []
    for group, spec in requests.items():
        for name in spec.get("variables", []):
            if name == "wind_speed":
                continue
            candidates = [ds for ds in datasets if name in ds.data_vars
                          and _belongs_to_group(ds, name, group)]
            if not candidates:
                errors.append(f"{path}: missing {group}.{name}")
        if spec.get("level_selection") in {"indices", "values"}:
            coords = [np.atleast_1d(ds[group].values) for ds in datasets if group in ds.coords]
            if not coords:
                errors.append(f"{path}: missing vertical coordinate {group}")
                continue
            available = np.unique(np.concatenate(coords))
            if spec["level_selection"] == "indices":
                if any(i >= len(available) for i in spec["level_indices"]):
                    errors.append(f"{path}: out-of-range {group} level indices")
            else:
                if any(np.min(np.abs(available.astype(float) - v)) > tolerance
                       for v in spec["level_values"]):
                    errors.append(f"{path}: unavailable {group} level values")
    if errors:
        raise ValueError("\n".join(errors))


def _belongs_to_group(ds, name, group):
    metadata_group = ds.attrs.get("_frameit_vertical_group")
    if metadata_group is not None:
        return metadata_group == group
    if group != "surface":
        return group in ds[name].dims or group in ds[name].coords
    vertical = {"level", "level_w", "heightAboveGround", "isobaric",
                "deptht", "depthu", "depthv", "depthw", "s_rho", "s_w"}
    return not (set(ds[name].dims) & vertical)


def wind_dependencies(conf, requests, *, native=False):
    """Expand explicit calculation inputs; native copies need no wind interpretation."""
    from frameit.processing.derived.wind import wind_names

    expanded = deepcopy(requests)
    if getattr(conf, "atm_model", None) in {"NEMO", "CROCO"}:
        return expanded, []
    pairs = []
    for group, spec in expanded.items():
        variables = spec.setdefault("variables", [])
        if native and "wind_speed" not in variables:
            continue
        definitions = wind_pairs(conf, group)
        if "wind_speed" in variables:
            names = wind_names(conf, group)
            variables.extend(n for n in names if n not in variables)
        aliases = getattr(conf, "tracking_var_aliases" if group == "surface"
                          else "velocity_aliases", {})
        keys = ("u10m", "v10m") if group == "surface" else ("u_velocity", "v_velocity")
        alias_names = tuple(aliases.get(k) for k in keys)
        if (all(alias_names) and set(alias_names) & set(variables)
                and not any((p["u"], p["v"]) == alias_names for p in definitions)):
            definitions.append(pair_definition(conf, group, alias_names))
        if not definitions:
            names = wind_names(conf, group)
            if set(names) & set(variables) or "wind_speed" in variables:
                definitions = [pair_definition(conf, group, names)]
        for declaration in definitions:
            names = declaration["u"], declaration["v"]
            if not set(names) & set(variables):
                continue
            pair = pair_definition(conf, group, names)
            pairs.append(pair)
            variables.extend(n for n in names if n not in variables)
    return expanded, pairs


def inspect_wind_pairs(datasets, conf, pairs, path):
    """Check headers and declared geometry only; never evaluate velocity arrays."""
    records = []
    for pair in pairs:
        group = pair["group"]
        candidates = [ds for ds in datasets if any(
            n in ds and _belongs_to_group(ds, n, group) for n in (pair["u"], pair["v"]))]
        for ds in candidates:
            frame = validate_pair_frame(ds, pair, conf)
            details = {}
            override = wind_frame_override(ds, pair, conf)
            if override:
                details["wind_reference_frame_override"] = override
            if frame == "grid":
                geometry = ds.copy(deep=False)
                for other in datasets:
                    for name in (conf.name_latitude, conf.name_longitude):
                        if name not in geometry and name in other:
                            geometry = geometry.assign_coords({name: other[name]})
                angle = rotation_angle(geometry, conf, pair)
                details["rotation_parameters"] = {
                    key: value for key, value in angle.attrs.items() if key.startswith("rotation_")
                }
                # Native MNH winds are checked on their eventual mass grid.
                dims = set(ds[pair["u"]].dims)
                if conf.atm_model == "MNH":
                    dims = {d.removesuffix("_u").removesuffix("_v") for d in dims}
                if ds[pair["u"]].ndim and not set(angle.dims) <= dims:
                    raise ValueError(f"{path}: wind rotation must use the collocated wind grid")
            records.append({"file": str(path), **deepcopy(pair),
                            "rotation_method": (pair["rotation"]["method"]
                                                if frame == "grid" else "none"), **details})
    return records


def selected_level_records(datasets, requests, path):
    """Record selected labels and original zero-based native positions."""
    records = []
    for group, req in normalize_requests(requests).items():
        for ds in datasets:
            if group == "surface" or group not in ds.dims:
                continue
            positions = selected_native_indices(ds, req, group)
            native = next((ds[n].values for n in (f"{group}_source_native_index",
                                                 "source_native_index")
                           if n in ds.coords and ds[n].dims == (group,)),
                          np.arange(ds.sizes[group]))
            records.append({"file": str(path), "group": group,
                            "level_domain": req["level_domain"],
                            "source_native_indices": np.asarray(native)[positions].tolist(),
                            "values": ds[group].values[positions].tolist()})
    return records


def polar_sampling_plan(conf, time_count):
    """Validate only the effective target, including the full time allocation."""
    from frameit.processing.polar.sampling import sampling_axes

    radii, angles, metadata = sampling_axes(conf)
    if time_count * len(radii) * len(angles) > conf.polar_max_points:
        raise ValueError(
            "Polar geometry across all times exceeds "
            "products.polar.processing.max_target_points")
    return {**metadata, "radial_count": len(radii),
            "estimated_points_per_time": len(radii) * len(angles),
            "estimated_time_count": time_count}


def preflight_result(conf, facts, *, command="validate"):
    """Wrap already-produced facts, including execution's owning prepare/bind result."""
    result = PreflightResult(command, conf=conf, facts=facts)
    for name, source in facts.get("sources", {}).items():
        messages = list(source.get("selection_pending", []))
        if source.get("field_binding") is None:
            messages.append("Field, level, unit and method binding remains pending; "
                            "metadata discovery is not executable clearance.")
        if (not conf.source_requests[name]["exports"]
                and not source.get("tracker_support")
                and not source.get("tracker_support_pending")):
            messages.append(
                f"Select fields in sources.{name}.variables using available_selectors.")
        if source.get("tracker_support_pending"):
            messages.append(source["tracker_support_pending"])
        result.deferred_checks.extend({
            "path": f"sources.{name}", "status": "unfinished-selection", "message": message,
        } for message in messages)
    result.deferred_checks.append({
        "path": "execution", "status": "execution-dependent",
        "message": "Selected payload decoding, value/mask checks, calculation, "
                   "publication and cleanup require execution.",
    })
    if command != "inspect" and not conf.simulation_parameter["request_plan"]["products"]:
        result.errors.append(Diagnostic(
            "products", "No fields or trajectory selected for a product",
            "at least one selected product", conf.yaml_config["products"],
            ["Select fields in sources.<name>.variables, "
              "or explicitly request a trajectory."], code="E1301"))
        result.deferred_checks.append(blocked_check(
            "plan", ["products"], "Product planning requires an explicit selection."))
    return result


def collect_preflight(request, *, command="validate", schema_only=False, check_output=True,
                      execution_options=None, resources=None):
    """Collect existing preflight facts once; failures never grant execution clearance."""
    from frameit.core.configuration import resolved_configuration, resolved_sources
    from frameit.core.settings_class import SimulationConfig

    result = PreflightResult(command)
    try:
        conf = request if isinstance(request, SimulationConfig) else (
            SimulationConfig.from_mapping_with_model_preset(request) if isinstance(request, dict)
            else SimulationConfig.from_yaml_with_model_preset(request))
        result.conf = conf
        if schema_only:
            result.facts = {"configuration": resolved_configuration(conf),
                            "setting_sources": resolved_sources(conf)}
            result.deferred_checks = [{
                "path": "inputs", "status": "schema-only",
                "message": "Offline schema-only: inputs, dependencies "
                           "and execution were not checked.",
            }]
        else:
            if command == "inspect":
                from frameit.core.coupled import prepare_sources

                result.facts = prepare_sources(
                    conf, check_output=False, execution_options=execution_options,
                    resources=resources)[0]
            else:
                from frameit.core.coupled import bind_sources

                result.facts = bind_sources(
                    conf, check_output=check_output, execution_options=execution_options,
                    resources=resources)[0]
            return preflight_result(conf, result.facts, command=command)
    except (OSError, ValueError, ImportError) as exc:
        result.errors = exception_diagnostics(
            exc, path="configuration" if result.conf is None else "plan",
            expected="valid v3 configuration" if result.conf is None else "valid selected metadata",
            observed={"cause": str(exc)}, repairs=[f"Correct the reported prerequisite: {exc}"])
        if isinstance(exc, PreflightError):
            result.facts = exc.facts
            result.deferred_checks = exc.deferred_checks
        if not result.deferred_checks:
            result.deferred_checks = [blocked_check(
                "plan", [error.path for error in result.errors],
                "Dependent planning and execution are blocked until these errors are repaired.")]
    return result


def preflight(conf, *, input_files=None, check_output=True, execution_options=None, resources=None,
              include_variable_metadata=False):
    """Validate metadata/geometry, optionally retaining lazy inputs in a run's owner."""
    if getattr(conf, "schema_version", None) == 3:
        from frameit.core.coupled import bind_sources, prepare_sources

        if input_files is not None:
            if conf.source_name is None:
                raise ValueError("v3 inventories are declared per sources.<name>.files")
            # This internal caller must not replace or widen the authored inventory.
            selected = conf.simulation_parameter["request_plan"]["sources"][conf.source_name]
            if selected["records"] is None or list(map(str, input_files)) != selected["files"]:
                raise ValueError("v3 input_files must be the bound selected source inventory")
        if "polar" in conf.yaml_config["products"]:
            return bind_sources(
                conf, check_output=check_output, execution_options=execution_options,
                resources=resources)[0]
        resource_plan = _describe_v3_unbound_resources(conf, execution_options)
        report = prepare_sources(
            conf, check_output=check_output, execution_options=execution_options,
            resources=resources)[0]
        report.update(resource_plan)
        return report
    if conf.input_sources:
        if input_files is not None:
            raise ValueError("Coupled inventories are specified per input.sources entry")
        from frameit.core.coupled import prepare_sources

        return prepare_sources(conf, check_output=check_output,
                               execution_options=execution_options)[0]
    files = (discover_input_files(conf) if input_files is None
             else resolve_input_files(input_files, strict=True))
    conf.file_type = infer_format(files, conf.file_type or None)
    if conf.atm_model in {"NEMO", "CROCO"} and conf.file_type != "netcdf":
        raise ValueError(f"{conf.atm_model} supports only native NetCDF inputs")
    if conf.file_type == "fa":
        if conf.tracking_method not in {"fixed_box", "prescribed_track"}:
            raise ValueError("FA atmospheric trackers remain gated; use fixed_box/prescribed_track "
                             "or a qualified GRIB/NetCDF tracking source")
        conf.simulation_parameter["fa_inventory"] = []
    inventory = []
    unit_records = []
    wind_records, selected_levels = [], []
    from frameit.tracking.pressure_centroid_inputs import (
        inspect_mnh_sequence,
        is_mnh_centroid,
        mnh_wind_frames,
        resolve_mnh_fields,
    )

    mnh_centroid = is_mnh_centroid(conf)
    multifield = conf.tracking_method == "multifield_vortex"
    vortex_inputs = []
    mnh_records = []
    if (mnh_centroid or multifield and conf.atm_model == "MNH") and conf.file_type != "netcdf":
        raise ValueError(f"Meso-NH {conf.tracking_method} requires native-level NetCDF inputs")

    chunks = conf.netcdf_chunks if resources is not None else None
    with (DatasetResources() if resources is None else nullcontext(resources)) as resources:
        grids = []
        for path, datasets in open_metadata(files, conf, resources, chunks=chunks):
            grids.extend(datasets)
            tracker = conf.requests_tracker().get(conf.tracking_method, {})
            layout = None
            if multifield:
                from frameit.tracking.multifield_inputs import inspect_inputs, resolve_mnh

                report = inspect_inputs(datasets, conf, str(path))
                if conf.atm_model == "MNH" and vortex_inputs and any(
                    report[key] != vortex_inputs[0][key] for key in ("pressure", "height", "winds")
                ):
                    raise ValueError(f"multifield_vortex: inconsistent source fields in {path}")
                vortex_inputs.append({"file": Path(path).name, **report})
                if conf.atm_model == "MNH":
                    layout = resolve_mnh(datasets[0], conf, str(path))
                    tracker = layout.requests()
            if mnh_centroid:
                header = datasets[0]
                stamps = (", ".join(str(t) for t in header.time.values)
                          if "time" in header else "unknown")
                layout = resolve_mnh_fields(header, f"{path}; time={stamps}")
                tracker = layout.requests()
                mnh_records.append((path, header))
            user_dependencies, user_pairs = wind_dependencies(
                conf, conf.requests_user(), native=conf.cartesian_horizontal_winds == "native")
            tracker_dependencies, tracker_pairs = wind_dependencies(conf, tracker)
            if conf.file_type == "netcdf":
                tolerance = 0. if conf.atm_model in {"NEMO", "CROCO"} else .5
                _check_requests(datasets, user_dependencies, path, tolerance=tolerance)
                _check_requests(datasets, tracker_dependencies, path, tolerance=tolerance)
            pairs = []
            for pair in user_pairs + tracker_pairs:
                if pair not in pairs:
                    pairs.append(pair)
            wind_records.extend(inspect_wind_pairs(datasets, conf, pairs, path))
            selected_levels.extend(selected_level_records(datasets, user_dependencies, path))
            tracker_level_requests = deepcopy(tracker_dependencies)
            if (layout is not None
                    and datasets[0].level.attrs.get("c_grid_dynamic_range") is not None):
                tracker_level_requests["level"]["level_selection"] = "physical"
            selected_levels.extend(
                {**r, "purpose": "tracking"}
                for r in selected_level_records(datasets, tracker_level_requests, path)
            )
            variables = {}
            levels = {}
            times = []
            velocity_names = {p[k] for p in pairs for k in ("u", "v")}
            velocity_names.add(conf.velocity_aliases.get("w_velocity"))
            if layout is not None:
                velocity_names.update((layout.u, layout.v))
            requested_names = {
                v for s in (*user_dependencies.values(), *tracker_dependencies.values())
                for v in s.get("variables", [])
            }
            if layout is not None:
                requested_names.update(layout.variables)
            for ds in datasets:
                variables.update({name: da.attrs.get("units") for name, da in ds.data_vars.items()})
                for name in ds.coords:
                    spatial_time = {
                        conf.name_latitude, conf.name_longitude, "time", "valid_time", "step",
                        "forecast_reference_time",
                    }
                    if conf.file_type == "fa":
                        spatial_time.update({"x", "y", "source_i", "source_j", "crs",
                                             "forecast_reference_time", "forecast_period"})
                    if name not in spatial_time and ds[name].ndim <= 1:
                        levels[name] = {"values": np.atleast_1d(ds[name].values).tolist(),
                                        "units": ds[name].attrs.get("units")}
                    if name in {"time", "valid_time"}:
                        times.extend(str(v) for v in np.atleast_1d(ds[name].values))
                for name in requested_names | {conf.name_latitude, conf.name_longitude}:
                    if name not in ds:
                        continue
                    quantity = None
                    if conf.atm_model == "AROME" and name == "w":
                        if unit_key(ds[name].attrs.get("units")) not in {
                            "pa/s", "pas-1", "pas**-1", "pas^-1",
                        }:
                            raise ValueError(f"{path}: w requires pressure velocity units Pa s-1")
                        unit_records.append({"file": str(path), "variable": name,
                                             "source_units": ds[name].attrs["units"],
                                             "calculation_units": "Pa s-1", "assumed": False})
                        continue
                    if name in velocity_names:
                        quantity = "velocity"
                    elif name in {conf.name_latitude, conf.name_longitude}:
                        quantity = "angle"
                    elif (name == conf.tracking_var_aliases.get("geopot")
                          and conf.tracking_method in {"pressure_centroid", "multifield_vortex"}):
                        quantity = "geopotential"
                    elif (name == conf.tracking_var_aliases.get("mslp")
                           and conf.tracking_method in {"pressure_centroid", "multifield_vortex"}):
                        quantity = "pressure"
                    elif layout is not None and name == layout.pressure:
                        quantity = "pressure"
                    elif layout is not None and name in layout.height:
                        quantity = "distance"
                    assumed = "m s-1" if quantity == "velocity" else "degree"
                    if quantity:
                        from frameit.utils.units import unit_metadata

                        normalized = unit_metadata(
                            ds[name], quantity,
                            assumed=assumed if quantity in {"velocity", "angle"} else None,
                            target=("degrees_north" if name == conf.name_latitude
                                    else "degrees_east") if quantity == "angle" else None,
                        )
                        unit_records.append({"file": str(path), "variable": name,
                                             "source_units": ds[name].attrs.get("units"),
                                             "calculation_units": normalized["units"],
                                             "assumed": not bool(ds[name].attrs.get("units"))})
                if "isobaric" in ds.coords and ds.isobaric.attrs.get("units"):
                    convert_units(ds.isobaric, "pressure")
            calendars = {str(ds[name].encoding.get("calendar", ds[name].attrs.get(
                "calendar", "standard"))) for ds in datasets
                for name in ("time", "valid_time") if name in ds.coords}
            inventory.append({"path": str(path), "variables": variables, "levels": levels,
                                "times": sorted(set(times)), "calendars": sorted(calendars)})
            if include_variable_metadata:
                inventory[-1]["variable_metadata"] = [
                    {"name": name,
                     **({"group": ds.attrs["_frameit_vertical_group"]}
                        if "_frameit_vertical_group" in ds.attrs else {}),
                     **inspect_wind_metadata(da.attrs, ds.attrs)}
                    for ds in datasets for name, da in ds.data_vars.items()
                ]
            references = sorted({str(value) for ds in datasets if "forecast_reference_time" in ds
                                 for value in np.atleast_1d(ds.forecast_reference_time.values)})
            if references:
                inventory[-1]["reference_times"] = references
            if datasets[0].attrs.get("_frameit_variable_providers"):
                inventory[-1]["variable_providers"] = datasets[0].attrs["_frameit_variable_providers"]
            unmapped = [entry for ds in datasets for entry in ds.attrs.get(
                "_frameit_unmapped_grib_records", [])]
            if unmapped:
                inventory[-1]["unmapped_grib_records"] = unmapped
        # Some AROME diagnostics legitimately begin after the initial record.
        # Validate availability across the inventory; per-file gaps remain
        # visible and the loader retains its established NaN/time alignment.
        if conf.atm_model in {"NEMO", "CROCO"}:
            from frameit.io.netcdf_utils import validate_native_metadata

            metadata_names = set(requested_names)
            if conf.atm_model == "CROCO":
                from frameit.io.croco_utils import current_pairs, polar_fields

                pairs = current_pairs(conf)
                if pairs:
                    metadata_names.update(name for pair in pairs for name in pair)
                    metadata_names.update(("angle", "mask_rho", "mask_u", "mask_v"))
                if polar_fields(conf):
                    metadata_names.add("mask_rho")
            validate_native_metadata(grids, metadata_names, model=conf.atm_model)
        if getattr(conf, "netcdf_surfex_fields", []):
            from frameit.io.surfex_utils import validate_surfex_metadata

            validate_surfex_metadata(grids, set(conf.netcdf_surfex_fields) & requested_names)
        tolerance = 0. if conf.atm_model in {"NEMO", "CROCO"} else (.51 if conf.file_type == "grib" else .5)
        _check_requests(grids, user_dependencies, Path("selected-inputs"), tolerance=tolerance)
        if mnh_centroid:
            layout = inspect_mnh_sequence(mnh_records)
            conf.requested_variables_tracker["pressure_centroid"] = layout.requests()
            conf.add_parameter("pressure_centroid_inputs", {
                "pressure": layout.pressure, "winds": [layout.u, layout.v],
                "height": list(layout.height), "height_reference": "above_mean_sea_level",
                "wind_reference_frames": mnh_wind_frames(mnh_records[0][1], layout, conf),
            })
        elif multifield and conf.atm_model == "MNH":
            conf.requested_variables_tracker["multifield_vortex"] = layout.requests()
        else:
            _check_requests(
                grids, tracker_dependencies,
                Path("selected-inputs"), tolerance=tolerance,
            )
        geometry = resolve_geometry(conf, grids)
        if multifield:
            from frameit.tracking.multifield_vortex import VortexGrid, VortexOptions

            settings = conf.multifield_vortex
            options = VortexOptions(**settings["numerics"], **settings["quality"])
            seed = settings["seed"]
            # Header/coordinate inspection only: no pressure or wind field is evaluated.
            spatial = next(ds for ds in grids if conf.name_latitude in ds and
                           conf.name_longitude in ds)
            from frameit.utils.units import normalize_geography

            spatial = normalize_geography(spatial, conf)
            lon, lat = xr.broadcast(spatial[conf.name_longitude], spatial[conf.name_latitude])
            if "time" in lon.dims:
                lon, lat = lon.isel(time=0), lat.isel(time=0)
            grid = VortexGrid(np.asarray(lon), np.asarray(lat), conf.resolution, options)
            if not np.isfinite(grid.footprint(seed["longitude"], seed["latitude"])):
                raise ValueError("multifield_vortex seed is outside the input grid")
            conf.add_parameter("multifield_inputs", {
                "files": vortex_inputs, "profile": settings["profile"], "seed": seed,
                "required_pressure_levels_hpa": [850, 700, 500],
                "barnes_efolding_km": grid.efolding_km,
                "barnes_influence_km": grid.influence_km,
                "search_radius_km": grid.search_km,
                "steering_efolding_km": 500., "steering_influence_km": 1000.,
                "seed_has_full_steering_footprint": grid.disk_supported(
                    (seed["longitude"], seed["latitude"]), 1000.),
                "qualification": "experimental_native_grid_adaptation",
            })
    for name in ("prescribed_track_file", "utrack_weights_file"):
        value = getattr(conf, name)
        if value and not Path(value).is_file():
            raise FileNotFoundError(f"Missing {name}: {value}")
    if conf.tracking_method == "utrack" and importlib.util.find_spec("torch") is None:
        raise ValueError("tracking.method utrack requires torch")
    if conf.tracking_method == "utrack" and importlib.util.find_spec("utrack") is None:
        raise ValueError("tracking.method utrack requires the utrack package")
    model_times = {np.datetime64(t, "ns") for item in inventory for t in item["times"]}
    nt = len(model_times)
    if multifield:
        seed_time = conf.multifield_vortex["seed"]["time"]
        if not nt or any(np.isnat(t) for t in model_times):
            raise ValueError("multifield_vortex requires valid model timestamps")
        if seed_time is not None:
            try:
                stamp = np.datetime64(seed_time, "ns")
            except ValueError as exc:
                raise ValueError(
                    "multifield_vortex seed.time must be a valid ISO timestamp") from exc
            if np.isnat(stamp) or stamp != min(model_times):
                raise ValueError("multifield_vortex seed.time must equal the first model timestamp")
    if conf.tracking_method == "prescribed_track":
        from frameit.io.track_file import load_track_coordinates

        track = load_track_coordinates(
            conf.prescribed_track_file, time_name=conf.prescribed_track_time_name,
            latitude_name=conf.prescribed_track_lat_name,
            longitude_name=conf.prescribed_track_lon_name,
        )
        common = sorted(model_times & set(np.asarray(track.time, dtype="datetime64[ns]")))
        nt = len(common)
        if not nt:
            raise ValueError("Prescribed track has no exact timestamp intersection with inputs")
        matched = track.sel(time=common)
        if (not np.isfinite(matched.latitude).all() or not np.isfinite(matched.longitude).all()
                or np.any(np.abs(matched.latitude) > 90)):
            raise ValueError("Prescribed track has invalid common-time geographic coordinates")
        for name in ("latitude", "longitude"):
            coordinate = track[name]
            source_units = coordinate.attrs.get(
                "source_units", coordinate.attrs.get("unit_assumption", coordinate.attrs["units"])
            )
            unit_records.append({"file": conf.prescribed_track_file, "variable": name,
                                 "source_units": source_units,
                                 "calculation_units": coordinate.attrs["units"],
                                 "assumed": "unit_assumption" in coordinate.attrs})
    if conf.tracking_method == "pressure_centroid" and nt < 2:
        raise ValueError("pressure_centroid requires at least two distinct model times")
    if check_output:
        destination = conf.output_dir
        while not destination.exists():
            destination = destination.parent
        if not destination.is_dir() or not os.access(destination, os.W_OK):
            raise tag_error(ValueError(f"Unwritable output destination: {conf.output_dir}"),
                            "E1803")
    from frameit.core.execution import ExecutionOptions
    from frameit.io.netcdf_export import _sanitize_filename_token

    options = execution_options or ExecutionOptions.from_config(conf)
    from frameit.core.runtime import resolve_execution_resources

    options, resources = resolve_execution_resources(options)
    from frameit.core.configuration import resolved_configuration, resolved_sources

    resolved = resolved_configuration(conf, options)
    excluded = []
    if input_files is None:
        candidates = ([Path(p) for p in conf.input_files] if conf.input_files is not None else
                      sorted(p for p in conf.data_dir.glob(conf.build_pattern()) if p.is_file()))
        excluded = [str(p) for p in candidates if input_path_excluded(p, conf)]
    products = []
    prefix = conf.output_dir / "products" / conf.simulation_name
    suffix = ".zarr" if options.engine == "zarr" else ".nc"
    if options.export_netcdf:
        products.append(str(prefix) + f".track{suffix}")
        if options.export_cart:
            products.extend(
                str(prefix) + f".cart.{_sanitize_filename_token(g)}{suffix}"
                for g in conf.requests_user()
            )
        if options.export_polar and conf.compute_polar_proj:
            groups = {conf.name_vertical_dim if g == "level_w" and conf.atm_model == "MNH" else g
                      for g in conf.polar_variables}
            products.extend(
                str(prefix) + f".polar.{_sanitize_filename_token(g)}{suffix}" for g in sorted(groups)
            )
    plan = {"configuration": resolved, "grid_geometry": geometry,
            "inputs": inventory, "unit_provenance": unit_records,
            "wind_provenance": wind_records, "selected_levels": selected_levels,
            "excluded_inputs": excluded, "planned_products": products,
            "setting_sources": resolved_sources(conf, options),
            "tracking_method": conf.tracking_method, "track_time_count": nt,
            "output_directory": str(conf.output_dir), "execution_resources": resources}
    if mnh_centroid:
        plan["tracking_inputs"] = conf.simulation_parameter["pressure_centroid_inputs"]
    if multifield:
        plan["tracking_inputs"] = conf.simulation_parameter["multifield_inputs"]
    if (conf.compute_polar_proj
            and not conf.simulation_parameter.get("_defer_polar_sampling", False)):
        plan["polar_sampling"] = polar_sampling_plan(conf, nt)
    if conf.x_boxsize_km and conf.y_boxsize_km:
        plan["box_points"] = [int(2 * np.rint(v * 1000 / (2 * conf.resolution)) + 1)
                              for v in (conf.x_boxsize_km, conf.y_boxsize_km)]
    conf.add_parameter("input_inventory", [str(p) for p in files])
    conf.add_parameter("unit_provenance", unit_records)
    conf.add_parameter("wind_provenance", wind_records)
    conf.add_parameter("selected_levels", selected_levels)
    if conf.file_type == "fa":
        plan["fa_inputs"] = conf.simulation_parameter["fa_inventory"]
    conf.add_parameter("resolved_config", conf.yaml_config)
    return plan
