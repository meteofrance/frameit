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
from frameit.utils.units import convert_units


def open_metadata(files, conf, resources):
    """Open lazily with no disk indexes, closing originals on all error paths."""
    for path in files:
        if conf.file_type == "grib":
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
                if name in {"u10", "v10", "prmsl"} or group in {"surface", "meanSea"}:
                    group = "surface"
                entry = groups.setdefault(group, {"fields": {}, "levels": set(), "times": set()})
                attrs = {"units": str(get("units"))}
                if ec.codes_is_defined(handle, "uvRelativeToGrid"):
                    attrs["GRIB_uvRelativeToGrid"] = int(get("uvRelativeToGrid"))
                entry["fields"][name] = xr.DataArray(0., attrs=attrs)
                entry["levels"].add(float(get("level")))
                date = f"{int(get('validityDate')):08d}{int(get('validityTime')):04d}"
                entry["times"].add(np.datetime64(datetime.strptime(date, "%Y%m%d%H%M"), "ns"))
            finally:
                ec.codes_release(handle)
    if geometry is None:
        raise ValueError(f"{path}: no GRIB messages")
    datasets = [geometry]
    for group, entry in groups.items():
        coords = {"valid_time": sorted(entry["times"])}
        if group != "surface":
            units = {"isobaricInhPa": "hPa", "isobaricInPa": "Pa",
                     "heightAboveGround": "m"}.get(group)
            coords[group] = (group, sorted(entry["levels"]), {"units": units})
        datasets.append(xr.Dataset(entry["fields"], coords=coords,
                                   attrs={"_frameit_vertical_group": group}))
    return datasets


def infer_format(files, declared=None):
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


def preflight(conf, *, input_files=None, check_output=True, execution_options=None):
    files = (discover_input_files(conf) if input_files is None
             else resolve_input_files(input_files, strict=True))
    conf.file_type = infer_format(files, conf.file_type or None)
    inventory = []
    unit_records = []
    from frameit.processing.derived.wind import wind_names
    from frameit.tracking.pressure_centroid_inputs import (
        inspect_mnh_sequence,
        is_mnh_centroid,
        mnh_wind_frames,
        resolve_mnh_fields,
    )

    mnh_centroid = is_mnh_centroid(conf)
    mnh_records = []
    if mnh_centroid and conf.file_type != "netcdf":
        raise ValueError("Meso-NH pressure_centroid requires native-level NetCDF inputs")

    user_dependencies = deepcopy(conf.requests_user())
    for group, spec in user_dependencies.items():
        if "wind_speed" in spec.get("variables", []):
            spec["variables"] = list(
                dict.fromkeys(spec["variables"] + list(wind_names(conf, group)))
            )
    with DatasetResources() as resources:
        grids = []
        for path, datasets in open_metadata(files, conf, resources):
            grids.extend(datasets)
            user = conf.requests_user()
            tracker = conf.requests_tracker().get(conf.tracking_method, {})
            layout = None
            if mnh_centroid:
                header = datasets[0]
                stamps = (", ".join(str(t) for t in header.time.values)
                          if "time" in header else "unknown")
                layout = resolve_mnh_fields(header, f"{path}; time={stamps}")
                tracker = layout.requests()
                mnh_records.append((path, header))
            variables = {}
            levels = {}
            times = []
            velocity_names = set(conf.velocity_aliases.values()) | {
                conf.tracking_var_aliases.get(k) for k in ("u", "v", "u10m", "v10m")}
            if layout is not None:
                velocity_names.update((layout.u, layout.v))
            requested_names = {
                v for s in (*user.values(), *tracker.values()) for v in s.get("variables", [])
            }
            if layout is not None:
                requested_names.update(layout.variables)
                frames = mnh_wind_frames(datasets[0], layout, conf)
            if any("wind_speed" in s.get("variables", []) for s in user.values()):
                for group, spec in user.items():
                    if "wind_speed" in spec.get("variables", []):
                        for name in wind_names(conf, group):
                            requested_names.add(name)
            for ds in datasets:
                variables.update({name: da.attrs.get("units") for name, da in ds.data_vars.items()})
                for name in ds.coords:
                    spatial_time = {
                        conf.name_latitude, conf.name_longitude, "time", "valid_time", "step"
                    }
                    if name not in spatial_time and ds[name].ndim <= 1:
                        levels[name] = {"values": np.atleast_1d(ds[name].values).tolist(),
                                        "units": ds[name].attrs.get("units")}
                    if name in {"time", "valid_time"}:
                        times.extend(str(v) for v in np.atleast_1d(ds[name].values))
                for name in requested_names | {conf.name_latitude, conf.name_longitude}:
                    if name not in ds:
                        continue
                    quantity = None
                    if name in velocity_names:
                        quantity = "velocity"
                    elif name in {conf.name_latitude, conf.name_longitude}:
                        quantity = "angle"
                    elif (name == conf.tracking_var_aliases.get("geopot")
                          and conf.tracking_method == "pressure_centroid"):
                        quantity = "geopotential"
                    elif (name == conf.tracking_var_aliases.get("mslp")
                           and conf.tracking_method == "pressure_centroid"):
                        quantity = "pressure"
                    elif layout is not None and name == layout.pressure:
                        quantity = "pressure"
                    elif layout is not None and name in layout.height:
                        quantity = "distance"
                    assumed = "m s-1" if quantity == "velocity" else "degree"
                    if quantity:
                        normalized = convert_units(
                            ds[name], quantity,
                            assumed=assumed if quantity in {"velocity", "angle"} else None,
                            target=("degrees_north" if name == conf.name_latitude
                                    else "degrees_east") if quantity == "angle" else None,
                        )
                        if quantity == "velocity":
                            flag = ds[name].attrs.get("GRIB_uvRelativeToGrid")
                            frame = ds[name].attrs.get(
                                "wind_reference_frame",
                                ds.attrs.get("wind_reference_frame", conf.wind_reference_frame),
                            )
                            if layout is not None and name in frames:
                                frame = frames[name]
                            if flag is not None:
                                if int(flag) not in {0, 1}:
                                    raise ValueError(f"{path}: invalid wind reference on {name}")
                                frame = "grid" if int(flag) else "earth"
                            if frame == "grid" and "grid_rotation" not in ds and not (
                                layout is not None and name in frames
                            ):
                                raise ValueError(
                                    f"{path}: grid-relative {name} requires grid_rotation"
                                )
                        unit_records.append({"file": str(path), "variable": name,
                                             "source_units": ds[name].attrs.get("units"),
                                             "calculation_units": normalized.attrs["units"],
                                             "assumed": not bool(ds[name].attrs.get("units"))})
                for group, expected in (("isobaricInhPa", "hPa"), ("isobaricInPa", "Pa")):
                    if group in ds.coords:
                        da = ds[group]
                        converted = convert_units(da, "pressure", target=expected, assumed=expected)
                        if not np.allclose(da, converted):
                            raise ValueError(
                                f"{path}: {group} contradicts declared coordinate units"
                            )
            inventory.append({"path": str(path), "variables": variables, "levels": levels,
                              "times": sorted(set(times))})
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
        else:
            _check_requests(
                grids, conf.requests_tracker().get(conf.tracking_method, {}),
                Path("selected-inputs"), tolerance=tolerance,
            )
        geometry = resolve_geometry(conf, grids)
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
            "excluded_inputs": excluded, "planned_products": products,
            "setting_sources": resolved_sources(conf, options),
            "tracking_method": conf.tracking_method, "track_time_count": nt,
            "output_directory": str(conf.output_dir)}
    if mnh_centroid:
        plan["tracking_inputs"] = conf.simulation_parameter["pressure_centroid_inputs"]
    if conf.compute_polar_proj:
        from frameit.processing.polar.sampling import sampling_axes

        radii, angles, metadata = sampling_axes(conf)
        plan["polar_sampling"] = {**metadata, "radial_count": len(radii),
                                  "estimated_points_per_time": len(radii) * len(angles),
                                  "estimated_time_count": nt}
        if nt * len(radii) * len(angles) > conf.polar_max_points:
            raise ValueError("Polar geometry across all times exceeds polar.max_points")
    if conf.x_boxsize_km and conf.y_boxsize_km:
        plan["box_points"] = [int(2 * np.rint(v * 1000 / (2 * conf.resolution)) + 1)
                              for v in (conf.x_boxsize_km, conf.y_boxsize_km)]
    conf.add_parameter("input_inventory", [str(p) for p in files])
    conf.add_parameter("unit_provenance", unit_records)
    conf.add_parameter("resolved_config", conf.yaml_config)
    return plan
