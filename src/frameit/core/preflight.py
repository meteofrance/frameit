"""Dataset metadata/coordinate inspection shared by validation and execution."""

from __future__ import annotations

import importlib.util
import os
from copy import deepcopy
from pathlib import Path

import numpy as np
import xarray as xr

from frameit.core.grid_geometry import resolve_geometry
from frameit.io.loader import (
    DatasetResources,
    discover_input_files,
    input_path_excluded,
    resolve_input_files,
)
from frameit.processing.requests import normalize_requests, selected_native_indices
from frameit.processing.wind_reference import (
    pair_definition,
    rotation_angle,
    validate_pair_frame,
    wind_pairs,
)
from frameit.utils.units import convert_units, unit_key


def open_metadata(files, conf, resources):
    """Open lazily with no disk indexes, closing originals on all error paths."""
    fa_geometries = {}
    for path in files:
        if conf.file_type == "fa":
            from frameit.io.fa_geometry import fa_geometry, geometry_signature
            from frameit.io.fa_utils import (
                fa_field_names,
                fa_metadata_dataset,
                inspect_fa_inputs,
            )

            dependencies, _ = wind_dependencies(conf, conf.requests_user())
            info = inspect_fa_inputs(path, conf, fa_field_names(dependencies))
            signature = geometry_signature(info["geometry"], conf.fa_options)
            if signature not in fa_geometries:
                fa_geometries[signature] = fa_geometry(info["geometry"], conf.fa_options)
            datasets = [fa_metadata_dataset(info, conf.fa_options, fa_geometries[signature])]
            records = conf.simulation_parameter.setdefault("fa_inventory", [])
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
                            "earth_radius_m": conf.fa_options["earth_radius_m"]})
            records[-1]["horizontal_header_signature"] = signature
            records[-1]["grid_lookup"] = fa_geometries[signature].attrs["fa_grid_lookup"]
        elif conf.file_type == "grib":
            datasets = _grib_metadata(path)
        else:
            datasets = [xr.open_dataset(path, engine=conf.netcdf_engine)]
        for ds in datasets:
            resources.add(ds)
        yield path, datasets


def _grib_metadata(path):
    """One header scan, no field decoding or repeated cfgrib index builds."""
    from datetime import datetime

    import eccodes as ec

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
            units = {"isobaricInhPa": "hPa", "isobaricInPa": "Pa",
                     "heightAboveGround": "m"}.get(group)
            coords[group] = (group, sorted(entry["levels"]), {"units": units})
        datasets.append(xr.Dataset(entry["fields"], coords=coords, attrs={
            "_frameit_vertical_group": group,
            "_frameit_forecast_reference_times": sorted(entry["references"])}))
    return datasets


def infer_format(files, declared=None):
    if declared == "fa":
        # Native FA is structurally verified by the isolated metadata reader;
        # no extension guess or attempt to send unknown bytes to NetCDF.
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
            raise ValueError(f"Unsupported input file format: {path}")
    if len(formats) != 1:
        raise ValueError("Mixed GRIB/NetCDF inputs are not supported")
    detected = formats.pop()
    if declared and declared not in {detected, "nc" if detected == "netcdf" else "grib2"}:
        raise ValueError(f"input.format={declared} conflicts with detected {detected}")
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
    vertical = {"level", "level_w", "heightAboveGround", "isobaricInhPa", "isobaricInPa"}
    return not (set(ds[name].dims) & vertical)


def wind_dependencies(conf, requests):
    """Expand identified horizontal pairs, including single-component requests."""
    from frameit.processing.derived.wind import wind_names

    expanded = deepcopy(requests)
    pairs = []
    for group, spec in expanded.items():
        variables = spec.setdefault("variables", [])
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
            frame = validate_pair_frame(ds, pair)
            if frame == "grid":
                geometry = ds.copy(deep=False)
                for other in datasets:
                    for name in (conf.name_latitude, conf.name_longitude):
                        if name not in geometry and name in other:
                            geometry = geometry.assign_coords({name: other[name]})
                angle = rotation_angle(geometry, conf, pair)
                # Native MNH winds are checked on their eventual mass grid.
                dims = set(ds[pair["u"]].dims)
                if conf.atm_model == "MNH":
                    dims = {d.removesuffix("_u").removesuffix("_v") for d in dims}
                if ds[pair["u"]].ndim and not set(angle.dims) <= dims:
                    raise ValueError(f"{path}: wind rotation must use the collocated wind grid")
            records.append({"file": str(path), **deepcopy(pair),
                            "rotation_method": (pair["rotation"]["method"]
                                                if frame == "grid" else "none")})
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
        raise ValueError("Polar geometry across all times exceeds polar.max_points")
    return {**metadata, "radial_count": len(radii),
            "estimated_points_per_time": len(radii) * len(angles),
            "estimated_time_count": time_count}


def preflight(conf, *, input_files=None, check_output=True, execution_options=None):
    if conf.input_sources:
        if input_files is not None:
            raise ValueError("Coupled inventories are specified per input.sources entry")
        from frameit.core.coupled import prepare_sources

        return prepare_sources(conf, check_output=check_output,
                               execution_options=execution_options)[0]
    files = (discover_input_files(conf) if input_files is None
             else resolve_input_files(input_files, strict=True))
    conf.file_type = infer_format(files, conf.file_type or None)
    if conf.file_type == "fa":
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

    with DatasetResources() as resources:
        grids = []
        for path, datasets in open_metadata(files, conf, resources):
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
            user_dependencies, user_pairs = wind_dependencies(conf, conf.requests_user())
            tracker_dependencies, tracker_pairs = wind_dependencies(conf, tracker)
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
                        conf.name_latitude, conf.name_longitude, "time", "valid_time", "step"
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
                for group, expected in (("isobaricInhPa", "hPa"), ("isobaricInPa", "Pa")):
                    if group in ds.coords:
                        da = ds[group]
                        converted = convert_units(da, "pressure", target=expected, assumed=expected)
                        if not np.allclose(da, converted):
                            raise ValueError(
                                f"{path}: {group} contradicts declared coordinate units"
                            )
            calendars = {str(ds[name].encoding.get("calendar", ds[name].attrs.get(
                "calendar", "standard"))) for ds in datasets
                for name in ("time", "valid_time") if name in ds.coords}
            inventory.append({"path": str(path), "variables": variables, "levels": levels,
                               "times": sorted(set(times)), "calendars": sorted(calendars)})
            unmapped = [entry for ds in datasets for entry in ds.attrs.get(
                "_frameit_unmapped_grib_records", [])]
            if unmapped:
                inventory[-1]["unmapped_grib_records"] = unmapped
        # Some AROME diagnostics legitimately begin after the initial record.
        # Validate availability across the inventory; per-file gaps remain
        # visible and the loader retains its established NaN/time alignment.
        tolerance = .51 if conf.file_type == "grib" else .5
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
            raise ValueError(f"Unwritable output destination: {conf.output_dir}")
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
    if options.export_netcdf:
        products.append(str(prefix) + ".track.nc")
        if options.export_cart:
            products.extend(
                str(prefix) + f".cart.{_sanitize_filename_token(g)}.nc"
                for g in conf.requests_user()
            )
        if options.export_polar and conf.compute_polar_proj:
            groups = {conf.name_vertical_dim if g == "level_w" else g for g in conf.polar_variables}
            products.extend(
                str(prefix) + f".polar.{_sanitize_filename_token(g)}.nc" for g in sorted(groups)
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
