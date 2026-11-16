"""Declarative scientific cases and selective, header-only input preflight.

Planning uses the ordinary configuration/discovery contracts, never the CLI or
an execution worker. Physical arrays are not read to inventory fields/levels;
only horizontal coordinates needed for independent centre lookup are loaded.
"""

from __future__ import annotations

import copy
import fnmatch
import hashlib
import importlib
import importlib.util
from importlib.resources import files
from pathlib import Path

import yaml


def _catalog():
    value = yaml.safe_load(files("frameit.testing").joinpath("catalogs/science.yaml").read_text())
    if value.get("schema_version") != 1:
        raise ValueError("Unsupported matrix catalog schema")
    ids = [case["id"] for case in value["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate matrix case IDs")
    for case in value["cases"]:
        if case["dataset"] not in value["datasets"]:
            raise ValueError(f"Unknown dataset for case {case['id']}")
        if case["profile"] not in {"core", "full"}:
            raise ValueError(f"Unknown profile for case {case['id']}")
        if case["tracker"] not in {"fixed_box", "wind_pressure", "prescribed_track", "utrack"}:
            raise ValueError(f"Unknown tracker for case {case['id']}")
        if case.get("requirement", "required") not in {"required", "optional"}:
            raise ValueError(f"Unknown requirement for case {case['id']}")
        if case.get("selection", "indices") not in {"all", "indices", "values"}:
            raise ValueError(f"Unknown level selection for case {case['id']}")
        for mode in case["modes"]:
            dataset = value["datasets"][case["dataset"]]
            if mode not in {"ci", "full"} or mode not in dataset:
                raise ValueError(f"Unknown dataset binding for case {case['id']}")
            fragment = "mnh" if dataset["model"] == "MNH" else f"arome_{mode}"
            if any(g not in value["fragments"][fragment] for g in case.get("groups", [])):
                raise ValueError(f"Unknown request group for case {case['id']}")
    return value


def load_cases(mode="ci", profile="full", patterns=()):
    """Return independent, unbound definitions selected by stable ID/globs."""
    if mode not in {"ci", "full"} or profile not in {"core", "full"}:
        raise ValueError("mode must be ci/full and profile must be core/full")
    catalog = _catalog()
    result = []
    for definition in catalog["cases"]:
        if mode not in definition["modes"] or (
            profile == "core" and definition["profile"] != "core"
        ):
            continue
        if patterns and not any(fnmatch.fnmatchcase(definition["id"], p) for p in patterns):
            continue
        dataset = copy.deepcopy(catalog["datasets"][definition["dataset"]])
        binding = dataset[mode]
        model = dataset["model"]
        fragment = "mnh" if model == "MNH" else f"arome_{mode}"
        requests = copy.deepcopy(catalog["fragments"][fragment])
        if definition.get("groups"):
            requests = {g: requests[g] for g in definition["groups"]}
        for group, variables in definition.get("field_selection", {}).items():
            if group not in requests:
                raise ValueError(f"Field selection refers to an unrequested group: {group}")
            requests[group]["variables"] = list(variables)
            requests[group]["polar_variables"] = list(variables)
        wind_group = "heightAboveGround" if model == "AROME" else "level"
        speed_only = requests.get(wind_group, {}).get("variables") == ["wind_speed"]
        variables, polar_fields, pending_values = {}, [], []
        for group, spec in requests.items():
            if group == "surface":
                variables["2d"] = list(spec["variables"])
                polar_fields.extend(spec.get("polar_variables", spec["variables"]))
                continue
            req = {"names": list(spec["variables"])}
            if speed_only and group == wind_group:
                pair = next(pair for pair in catalog["wind_pairs"][model]
                            if pair["group"] == group)
                req["names"] = [pair["u"], pair["v"]]
            selection = definition.get("selection") or (
                "values" if "values" in spec else "indices")
            if selection == "indices":
                req["levels"] = {"indices": list(spec["indices"])}
            elif selection == "values" and spec.get("values"):
                req["levels"] = {"values": list(spec["values"])}
                if group in {"isobaricInhPa", "isobaricInPa"}:
                    req["levels"]["units"] = "hPa" if group == "isobaricInhPa" else "Pa"
            elif selection == "values":
                pending_values.append(group)
            variables.setdefault("3d", {})[group] = req
            polar_fields.extend(f"{group}.{name}" for name in
                                spec.get("polar_variables", spec["variables"]))
        suffix = "0P.grib" if model == "AROME" else "diag.nc"
        pattern = f"{dataset['stem']}???{suffix}"
        centre = binding.get("centre") or [None, None]
        names = [*variables.get("2d", []), *[
            f"{group}.{name}" for group, spec in variables.get("3d", {}).items()
            for name in spec["names"]]]
        pairs = []
        for pair in catalog["wind_pairs"][model]:
            prefix = "" if pair["group"] == "surface" else f"{pair['group']}."
            pairs.append({
                "u": prefix + pair["u"], "v": prefix + pair["v"],
                "basis": pair["reference_frame"],
                **({"rotation": copy.deepcopy(pair["rotation"])} if "rotation" in pair else {})})
        source = {
            "model": "arome" if model == "AROME" else "mesonh",
            "format": "grib" if model == "AROME" else "netcdf",
            "files": f"{definition['dataset']}/{pattern}",
            "exclude": [] if model == "AROME" else [
                f"{definition['dataset']}/{dataset['stem']}000{suffix}"],
            "variables": variables, "wind_pairs": pairs,
            "field_metadata": {name: {"kind": "continuous"} for name in names}}
        wind_fields = [pair[key] for pair in pairs for key in ("u", "v") if pair[key] in names]
        preparation_fields = (wind_fields if model == "AROME" else [
            name for name in wind_fields if name.startswith("level.")])
        if preparation_fields:
            source["transforms"] = [{"fields": preparation_fields,
                                     "sampling": "native" if model == "AROME" else "mass",
                                     "basis": "earth"}]
        gaps = [name if group == "surface" else f"{group}.{name}"
                for group, fields in catalog["allowed_initial_gaps"].get(model, {}).items()
                for name in fields if (name if group == "surface" else f"{group}.{name}") in names]
        if gaps:
            source["allow_initial_gaps"] = gaps
        wind_pair = next((pair for pair in pairs
                          if pair["u"].startswith(wind_group + ".")
                          and {pair["u"], pair["v"]} <= set(names)), None)
        model_fields = list(names)
        if wind_pair:
            inputs = {key: wind_pair[key] for key in ("u", "v")}
            source["derived"] = {"wind_speed": {"method": "wind_speed", "inputs": inputs}}
            model_fields.append("wind_speed")
            polar_fields.append("wind_speed")
            if speed_only:
                model_fields, polar_fields = ["wind_speed"], ["wind_speed"]
            elif definition.get("polar", True):
                source["derived"].update({
                    alias: {"method": method, "inputs": inputs}
                    for alias, method in (("vrad", "radial_wind"), ("vtan", "tangential_wind"))})
                polar_fields.extend(["vrad", "vtan"])
        width = {"x": definition.get("x_boxsize_km", binding["box_km"]),
                 "y": definition.get("y_boxsize_km", binding["box_km"])}
        region = {"center": dict(zip(("latitude", "longitude"), centre, strict=True)),
                  "width_km": width}
        if definition["tracker"] in {"wind_pressure", "utrack"}:
            region.pop("center")
            region["tracker"] = {"method": (
                "pressure_wind" if definition["tracker"] == "wind_pressure" else "utrack")}
        config = {
            "schema_version": 3,
            "run": {"name": definition["id"].upper(),
                    "description": f"Scientific matrix: {definition['id']}"},
            "sources": {"atmosphere": source}, "region": region,
            "products": {"model_grid": {"fields": {"atmosphere": model_fields}}, "track": True},
            "output": {"directory": "./output"}}
        if definition.get("polar", True):
            options = {name: {"sampling": "mass"} for name in polar_fields
                       if model == "MNH" and name in [*preparation_fields, "level_w.WT"]}
            for name in preparation_fields:
                if name in options:
                    options[name]["basis"] = "earth"
            config["products"]["polar"] = {
                "radius_km": min(width.values()) / 2,
                "radial_step_km": dataset["resolution"] / 1000,
                "azimuth_count": round(360 / definition.get("azimuth", 10)),
                "fields": {"atmosphere": polar_fields},
                **({"field_options": {"atmosphere": options}} if options else {})}
        result.append(
            dict(
                id=definition["id"],
                requirement=definition.get("requirement", "required"),
                profile=definition["profile"],
                dataset_id=definition["dataset"],
                tracker=definition["tracker"],
                polar=definition.get("polar", True),
                coverage=definition["coverage"],
                config=config,
                mode=mode,
                catalog_version=catalog["catalog_version"],
                revision="1",
                expected_file_count=binding["count"],
                filename_glob=pattern,
                excluded_reason=definition.get("ci_exclusion") if mode == "ci" else None,
                binding=binding,
                request_fragments=requests,
                pending_level_values=pending_values,
                allowed_initial_gaps=catalog["allowed_initial_gaps"].get(model, {}),
                prescribed_oracle=catalog["ci_prescribed_oracle"] if mode == "ci" else None,
            )
        )
    if not result:
        raise ValueError("No matrix cases match the selected mode/profile/case patterns")
    for pattern in patterns:
        if not any(fnmatch.fnmatchcase(case["id"], pattern) for case in result):
            raise ValueError(
                f"Case pattern matches no case in the selected mode/profile: {pattern}"
            )
    return result


def time_strings(values):
    """Canonical nanosecond ISO times, with no approximate intersection."""
    from datetime import datetime

    import numpy as np

    result = []
    for value in values:
        calendar = getattr(value, "calendar", "standard")
        if calendar not in {"standard", "gregorian", "proleptic_gregorian"}:
            raise ValueError(f"Unsupported calendar for exact matrix matching: {calendar}")
        if isinstance(value, np.datetime64):
            year = (
                int(np.datetime_as_string(value, unit="D").split("-")[0])
                if not np.isnat(value)
                else 0
            )
            if not 1678 <= year <= 2261:
                raise ValueError("Matrix time is outside supported nanosecond calendar range")
            stamp = value
        else:
            text = value.isoformat() if hasattr(value, "isoformat") else str(value)
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            # Reject out-of-range numpy dates rather than silently wrapping.
            if not 1678 <= parsed.year <= 2261:
                raise ValueError("Matrix time is outside supported nanosecond calendar range")
            if parsed.tzinfo is not None and parsed.utcoffset().total_seconds() != 0:
                raise ValueError("Matrix times must use UTC or unzoned model time")
            stamp = np.datetime64(parsed.replace(tzinfo=None), "ns")
        if np.isnat(stamp):
            raise ValueError("Missing matrix time coordinate")
        result.append(str(stamp.astype("datetime64[ns]")))
    return result


def file_record(path, *, content=False):
    path = Path(path)
    stat = path.stat()
    record = {"path": str(path.absolute()), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    if content:
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                h.update(chunk)
        record["sha256"] = h.hexdigest()
    return record


def _grib_inventory(paths, progress=None):
    from datetime import datetime

    import eccodes as ec
    import numpy as np

    records, coordinates, shape, geometry = [], None, None, None
    aliases = {"10u": "u10", "10v": "v10", "msl": "prmsl"}
    for index, path in enumerate(paths, 1):
        if progress:
            progress(f"Inspecting GRIB file {index}/{len(paths)}: {path}")
        fields, stamps = {}, set()
        message = 0
        with path.open("rb") as stream:
            while (handle := ec.codes_grib_new_from_file(stream)) is not None:
                message += 1

                def get(key, path=path, message=message, handle=handle):
                    try:
                        return ec.codes_get(handle, key)
                    except ec.CodesInternalError as exc:
                        raise ValueError(
                            f"{path.name}: GRIB message {message}, key {key!r}: {exc}"
                        ) from exc

                try:
                    grid = (int(get("Nj")), int(get("Ni")))
                    if int(get("numberOfDataPoints")) != grid[0] * grid[1]:
                        raise ValueError(f"{path.name}: grid/data point count mismatch")
                    if shape is not None and grid != shape:
                        raise ValueError(f"{path.name}: inconsistent GRIB grid")
                    shape = grid
                    signature = tuple(
                        get(key)
                        for key in (
                            "gridType",
                            "latitudeOfFirstGridPointInDegrees",
                            "longitudeOfFirstGridPointInDegrees",
                            "latitudeOfLastGridPointInDegrees",
                            "longitudeOfLastGridPointInDegrees",
                            "iDirectionIncrementInDegrees",
                            "jDirectionIncrementInDegrees",
                            "scanningMode",
                        )
                    )
                    if geometry is not None and signature != geometry:
                        raise ValueError(
                            f"{path.name}: GRIB message {message} uses a different horizontal grid"
                        )
                    geometry = signature
                    if (
                        ec.codes_is_defined(handle, "productDefinitionTemplateNumber")
                        and int(get("productDefinitionTemplateNumber")) == 32
                    ):
                        continue
                    group, level = str(get("typeOfLevel")), float(get("level"))
                    short = str(get("shortName"))
                    try:
                        name = str(ec.codes_get(handle, "cfVarName"))
                    except ec.KeyValueNotFoundError:
                        name = short
                    if name in {"unknown", "undef", ""}:
                        name = short
                    # Stack identities are paramId-based in cfgrib: individual
                    # 100/200m u/v computed names must not split a wind stack.
                    if short in {"u", "v"}:
                        name = short
                    name = aliases.get(name, aliases.get(short, name))
                    if name in {"u10", "v10", "prmsl"} or group in {"surface", "meanSea"}:
                        group = "surface"
                    fields.setdefault(group, {}).setdefault(name, set()).add(level)
                    key = f"{int(get('validityDate')):08d}{int(get('validityTime')):04d}"
                    stamps.add(time_strings([datetime.strptime(key, "%Y%m%d%H%M")])[0])
                    if coordinates is None:
                        lat = np.asarray(ec.codes_get_array(handle, "latitudes"))
                        lon = np.asarray(ec.codes_get_array(handle, "longitudes"))
                        jfast = int(get("jPointsAreConsecutive"))
                        lat = lat.reshape(grid[::-1]).T if jfast else lat.reshape(grid)
                        lon = lon.reshape(grid[::-1]).T if jfast else lon.reshape(grid)
                        coordinates = (lat, lon)
                finally:
                    ec.codes_release(handle)
        if not fields or len(stamps) != 1:
            raise ValueError(f"{path.name}: expected one unambiguous atmospheric validity time")
        records.append({"path": str(path), "times": sorted(stamps), "fields": fields})
    return _finish_inventory(records, shape, coordinates, "AROME")


def _netcdf_inventory(paths, progress=None):
    import numpy as np
    from netCDF4 import Dataset, num2date

    records, shape, coordinates, levels, coordinate_metadata = [], None, None, {}, {}
    field_units = {}
    for index, path in enumerate(paths, 1):
        if progress:
            progress(f"Inspecting NetCDF file {index}/{len(paths)}: {path}")
        with Dataset(path) as dataset:
            if "time" not in dataset.variables or dataset["time"].dimensions != ("time",):
                raise ValueError(f"{path.name}: expected time(time)")
            time = dataset["time"]
            calendar = getattr(time, "calendar", "standard")
            stamps = time_strings(num2date(time[:], time.units, calendar))
            coordinate_metadata["time"] = {
                "units": time.units,
                "calendar": calendar,
                "dtype": str(time.dtype),
            }
            dims = dataset.dimensions
            grid = (len(dims["nj"]), len(dims["ni"]))
            if shape is not None and grid != shape:
                raise ValueError(f"{path.name}: inconsistent NetCDF horizontal grid")
            shape = grid
            fields = {"surface": {}}
            for group in ("level", "level_w"):
                if group not in dataset.variables:
                    raise ValueError(f"{path.name}: missing {group} coordinate")
                coordinate = dataset[group]
                vals = np.asarray(coordinate[:], dtype=float).tolist()
                if not vals or not np.all(np.isfinite(vals)) or len(vals) != len(set(vals)):
                    raise ValueError(f"{path.name}: invalid {group} coordinate")
                if group in levels and vals != levels[group]:
                    raise ValueError(f"{path.name}: inconsistent {group} coordinates")
                levels[group] = vals
                meta = {"units": getattr(coordinate, "units", ""), "dtype": str(coordinate.dtype)}
                if (
                    group in coordinate_metadata
                    and meta["units"] != coordinate_metadata[group]["units"]
                ):
                    raise ValueError(f"{path.name}: inconsistent {group} units")
                coordinate_metadata[group] = meta
                fields[group] = {}
            for name, variable in dataset.variables.items():
                if name in dims or name in {"latitude", "longitude"}:
                    continue
                group = next(
                    (g for g in ("level", "level_w") if g in variable.dimensions), "surface"
                )
                fields[group][name] = set(levels[group]) if group in levels else {0.0}
                field_units[name] = getattr(variable, "units", None)
            for name in ("latitude", "longitude"):
                if name not in dataset.variables:
                    raise ValueError(f"{path.name}: missing {name}")
            lat = np.ma.filled(dataset["latitude"][:], np.nan).squeeze()
            lon = np.ma.filled(dataset["longitude"][:], np.nan).squeeze()
            if lat.shape != shape or lon.shape != shape:
                raise ValueError(f"{path.name}: expected two-dimensional lat/lon")
            if coordinates is None:
                coordinates = lat, lon
            elif not (
                np.array_equal(lat, coordinates[0], equal_nan=True)
                and np.array_equal(lon, coordinates[1], equal_nan=True)
            ):
                raise ValueError(f"{path.name}: different horizontal coordinate grid")
            records.append({"path": str(path), "times": stamps, "fields": fields})
    result = _finish_inventory(records, shape, coordinates, "MNH")
    result.update(levels=levels, coordinate_metadata=coordinate_metadata, field_units=field_units)
    return result


def _finish_inventory(records, shape, coordinates, model):
    records.sort(key=lambda r: r["times"][0])
    times = [time for record in records for time in record["times"]]
    if times != sorted(times) or len(times) != len(set(times)):
        raise ValueError("Model files contain duplicate or unordered decoded times")
    union = {}
    for record in records:
        for group, fields in record["fields"].items():
            for name, values in fields.items():
                union.setdefault(group, {}).setdefault(name, set()).update(values)
    levels = {}
    for group, fields in union.items():
        if group == "surface":
            continue
        # u is the reference stack for GRIB coordinate order; inventories may
        # contain unrelated fields at additional levels.
        values = fields.get("u", next(iter(fields.values())))
        levels[group] = sorted(values, reverse=group == "isobaricInhPa")
    return {
        "records": records,
        "times": times,
        "shape": shape,
        "coordinates": coordinates,
        "levels": levels,
        "fields": union,
        "model": model,
    }


def _selected_levels(case, inventory):
    requests = case["config"]["sources"]["atmosphere"]["variables"].get("3d", {})
    selected = {}
    for group, request in requests.items():
        available = inventory["levels"].get(group, [])
        levels = request.get("levels", {})
        if not available:
            raise ValueError(f"Missing requested vertical group {group}")
        if group in case.get("pending_level_values", []):
            vals = [available[i] for i in case["request_fragments"][group]["indices"]]
            request["levels"] = {"values": list(vals)}
            units = inventory.get("coordinate_metadata", {}).get(group, {}).get("units")
            if units:
                request["levels"]["units"] = units
        elif not levels:
            vals = available
        elif "indices" in levels:
            indices = levels["indices"]
            if any(i < -len(available) or i >= len(available) for i in indices):
                raise ValueError(f"{group}: requested level indices exceed available coordinates")
            vals = [available[i] for i in indices]
        else:
            vals = levels["values"]
            if not all(any(abs(float(v) - float(a)) <= 1e-6 for a in available) for v in vals):
                raise ValueError(f"{group}: requested physical levels {vals} are absent")
        selected[group] = list(vals)
    return selected


def _check_fields(case, inventory, selected):
    source = case["config"]["sources"]["atmosphere"]
    requests = {group: {"variables": list(spec["names"])}
                for group, spec in source["variables"].get("3d", {}).items()}
    requests["surface"] = {"variables": list(source["variables"].get("2d", []))}
    model = inventory["model"]
    tracker = case["tracker"]
    if tracker in {"wind_pressure", "utrack"}:
        names = ["u10", "v10", "prmsl"] if model == "AROME" else ["UM10", "VM10", "MSLP"]
        if tracker == "utrack":
            names = names[:2]
            requests.setdefault("isobaricInhPa", {"variables": []})["variables"].append("absv")
        surface = requests.setdefault("surface", {"variables": []})
        surface["variables"] = list(set(surface["variables"]) | set(names))
    for pair in source["wind_pairs"]:
        group, separator, u = pair["u"].partition(".")
        group, u, v = ((group, u, pair["v"].partition(".")[2]) if separator else
                       ("surface", pair["u"], pair["v"]))
        request = requests.get(group)
        if request and {u, v} & set(request["variables"]):
            request["variables"] = list(dict.fromkeys([*request["variables"], u, v]))
    for request in requests.values():
        request["variables"] = [n for n in request["variables"] if n != "wind_speed"]
    gaps = []
    for index, record in enumerate(inventory["records"]):
        for group, request in requests.items():
            for name in request["variables"]:
                available = record["fields"].get(group, {}).get(name, set())
                if not available:
                    if index == 0 and name in case["allowed_initial_gaps"].get(group, []):
                        gaps.append(
                            {
                                "times": record["times"],
                                "group": group,
                                "variable": name,
                                "expectation": "missing values allowed at initial time",
                            }
                        )
                        continue
                    raise ValueError(
                        f"{Path(record['path']).name}: missing requested {group}/{name}"
                    )
                values = (
                    [850.0] if name == "absv" and tracker == "utrack" else selected.get(group, [])
                )
                if values and not all(
                    any(abs(float(v) - float(a)) <= 1e-6 for a in available) for v in values
                ):
                    raise ValueError(
                        f"{Path(record['path']).name}: {group}/{name} "
                        f"lacks selected levels {values}"
                    )
    return gaps


def _nearest(coordinates, lat, lon):
    import numpy as np

    lats, lons = coordinates
    distance = (lats - lat) ** 2 + (lons - lon) ** 2
    if not np.any(np.isfinite(distance)):
        raise ValueError("Model coordinates contain no usable nearest point")
    y, x = np.unravel_index(np.nanargmin(distance), distance.shape)
    return {"cx": int(x), "cy": int(y)}


def _prescribed(case, root, output, inventory):
    from datetime import datetime

    import numpy as np
    from netCDF4 import Dataset, date2num, num2date

    if inventory["model"] == "AROME":
        point = case["config"]["region"]["center"]
        path = output.parent / "inputs" / "stationary-reference-track.nc"
        path.parent.mkdir(parents=True, exist_ok=True)
        with Dataset(path, "w") as dataset:
            dataset.createDimension("time", len(inventory["times"]))
            time = dataset.createVariable("time", "f8", ("time",))
            time.units = "seconds since 1970-01-01 00:00:00"
            time.calendar = "standard"
            dates = [datetime.fromisoformat(t[:26]) for t in inventory["times"]]
            time[:] = date2num(dates, time.units, time.calendar)
            for name, value, units in zip(
                ("latitude", "longitude"),
                (point["latitude"], point["longitude"]),
                ("degrees_north", "degrees_east"),
                strict=True,
            ):
                variable = dataset.createVariable(name, "f8", ("time",))
                variable[:] = value
                variable.units = units
            dataset.provenance = (
                "Stationary reference centre; model validity times; not an observed best track"
            )
        point = case["config"]["region"]["center"]
        centre = _nearest(inventory["coordinates"], point["latitude"], point["longitude"])
        return path, inventory["times"], [centre.copy() for _ in inventory["times"]]
    path = root / "MNH" / "IBTracks_reunion_CHIDO.nc"
    if not path.exists():
        raise FileNotFoundError(f"External prescribed NetCDF is absent: {path}")
    with Dataset(path) as track:
        lat_name = "latitude" if "latitude" in track.variables else "lat"
        lon_name = "longitude" if "longitude" in track.variables else "lon"
        if not {"time", lat_name, lon_name} <= set(track.variables):
            raise ValueError("Track needs time and latitude/longitude (or lat/lon)")
        for name in ("time", lat_name, lon_name):
            if track[name].dimensions != ("time",):
                raise ValueError(f"Track variable {name} must have dimensions (time,)")
        time = track["time"]
        dates = time_strings(num2date(time[:], time.units, getattr(time, "calendar", "standard")))
        if len(dates) != len(set(dates)):
            raise ValueError("External prescribed track contains duplicate times")
        lat = np.ma.filled(track[lat_name][:], np.nan)
        lon = np.ma.filled(track[lon_name][:], np.nan)
        lookup = {stamp: (float(a), float(b)) for stamp, a, b in zip(dates, lat, lon, strict=True)}
        common = [stamp for stamp in inventory["times"] if stamp in lookup]
        if not common:
            raise ValueError("External prescribed track has no exact overlap with model times")
        centres = []
        for stamp in common:
            a, b = lookup[stamp]
            if not np.isfinite(a) or not np.isfinite(b) or abs(a) > 90:
                raise ValueError(f"Invalid prescribed position at common time {stamp}")
            centre = _nearest(inventory["coordinates"], a, b)
            half = int(
                np.ceil(case["config"]["region"]["width_km"]["x"] * 1000 /
                         _catalog()["datasets"][case["dataset_id"]]["resolution"] / 2)
            )
            ny, nx = inventory["shape"]
            if min(centre["cx"], nx - 1 - centre["cx"], centre["cy"], ny - 1 - centre["cy"]) < half:
                raise ValueError(f"Prescribed extraction box exceeds domain at {stamp}")
            centres.append(centre)
    if case["mode"] == "ci":
        oracle = case["prescribed_oracle"]
        if common != oracle["times"] or centres != oracle["centres"]:
            raise ValueError("External track differs from frozen CHIDO fixture time/centre oracle")
    return path, common, centres


def probe_dependencies(case):
    """Probe only selected scientific branches; missing and broken differ."""
    if case["tracker"] == "utrack":
        if importlib.util.find_spec("utrack") is None:
            raise ModuleNotFoundError("Optional UTrack package is absent")
        try:
            module = importlib.import_module("utrack")
            prepare = importlib.import_module("utrack.prepare")
            if not hasattr(module, "Utracker") or not hasattr(prepare, "prepare_input"):
                raise ImportError("Expected UTrack APIs are unavailable")
        except Exception as exc:
            raise ValueError(f"Installed UTrack package is unusable: {exc}") from exc
    if case["polar"]:
        if importlib.util.find_spec("xesmf") is None:
            raise ValueError("Polar cases require the xESMF/ESMF backend")
        try:
            module = importlib.import_module("xesmf")
            if not hasattr(module, "Regridder"):
                raise ImportError("xesmf.Regridder is unavailable")
        except Exception as exc:
            raise ValueError(f"Installed xESMF/ESMF backend is unusable: {exc}") from exc


def _products_expected(case, selected, inventory=None):
    from frameit.core.coupled import bind_sources
    from frameit.core.settings_class import SimulationConfig
    from frameit.io.netcdf_export import _output_grid_facts, output_grid_layout

    config = case["config"]
    conf = SimulationConfig.from_mapping_with_model_preset(config)
    plan = bind_sources(conf, check_output=False)[0]
    source = plan["sources"]["atmosphere"]
    layout = output_grid_layout(source)
    times = list(case["expected"]["times"])
    contracts = []
    if config["products"].get("track"):
        point = config["region"].get("center")
        contracts.append({
            "role": "track", "source": None, "variables": ["latitude", "longitude"],
            "times": times, "complete_boxes": False,
            **({name: [point[name]] * len(times) for name in ("latitude", "longitude")}
               if point else {})})
    for role in ("model_grid", "polar"):
        if role not in config["products"]:
            continue
        product = next(item for item in plan["products"] if item["product"] == role)
        names = product["fields"]
        contract = {
            "role": role, "source": "atmosphere", "variables": list(names), "times": times,
            "dimensions": product["dimensions"], "units": {}, "levels": {}}
        if role == "model_grid":
            contract["native_index_coordinates"] = {}
        for name in names:
            descriptor = source["requests"]["binding"]["products"][role][name]
            representations = descriptor.get("representations")
            contract["units"][name] = (
                representations[0]["units"] if representations else
                source["fields"][descriptor["field_id"]]["attributes"].get("units"))
            for record in descriptor["records"]:
                facts = _output_grid_facts(layout, record["selection_grid_id"], name)
                if role == "model_grid":
                    contract["native_index_coordinates"].update({
                        original["index"]: (
                            "cx" if facts["horizontal"][native].startswith("x") else "cy")
                        for native, original in facts["original_coordinates"].items()})
                vertical = record.get("vertical")
                if vertical is None:
                    continue
                field = source["fields"][record["field_id"]]
                group = field.get("group") or next(
                    (dim for dim in field["dimensions"] if dim in selected), None)
                values = selected[group]
                if role == "polar" and group == "level_w" and vertical["dimension"] == "level":
                    values = (selected["level"] if "level" in selected else [
                        inventory["levels"]["level"][inventory["levels"]["level_w"].index(value)]
                        for value in values])
                axis = facts["dimensions"].get(vertical["dimension"], vertical["dimension"])
                contract["levels"][axis] = list(values)
        contracts.append(contract)
    return contracts


def resolve_case(case, data_root, case_output, *, input_policy="strict", mode=None, context=None):
    """Resolve exact files, expected coordinates/products and prerequisites.

    Shared ``context`` caches a metadata inventory for each unique dataset. It
    may carry ``utrack_weights``; no environment-specific paths are consulted.
    """
    from frameit.core.settings_class import SimulationConfig
    from frameit.io.loader import inventory_source_files

    if input_policy not in {"strict", "available"}:
        raise ValueError("input_policy must be strict or available")
    value = copy.deepcopy(case)
    context = {} if context is None else context
    root, output = Path(data_root).expanduser().absolute(), Path(case_output).absolute()
    value["mode"] = mode or value["mode"]
    config = value["config"]
    source = config["sources"]["atmosphere"]
    source["files"] = str(root / value["dataset_id"] / value["filename_glob"])
    source["exclude"] = [str(root / path) for path in source.get("exclude", [])]
    config["output"]["directory"] = str(output)
    value.update(input_files=[], input_records=[], expected={}, preflight="READY", reason="")
    if value.get("excluded_reason"):
        value.update(preflight="EXCLUDED", reason=value["excluded_reason"])
        return value
    try:
        # The early checkpoint check keeps disabled optional ML cases cheap.
        if value["tracker"] == "utrack":
            supplied = context.get("utrack_weights")
            if not supplied:
                value.update(
                    preflight="SKIPPED_PREREQUISITE", reason="No UTrack checkpoint supplied"
                )
                return value
            weights = Path(supplied).expanduser().absolute()
            if not weights.is_file():
                raise ValueError(f"Explicit UTrack checkpoint is not a readable file: {weights}")
            with weights.open("rb") as stream:
                if not stream.read(1):
                    raise ValueError("UTrack checkpoint is empty")
            config["region"]["tracker"].update(
                weights_file=str(weights), use_gpu=False, batch_size=16)
            value["input_records"].append(file_record(weights))
        key = (str(root), value["dataset_id"], value["filename_glob"])
        cache = context.setdefault("inventories", {})
        if key not in cache:
            progress = context.get("progress")
            if progress:
                progress(f"Discovering inputs for {value['dataset_id']}")
            # Discovery uses coordinates only; centres/level values bind from this inventory.
            try:
                entries, _, _ = inventory_source_files(source)
                paths = [Path(entry["path"]) for entry in entries]
            except FileNotFoundError:
                status = (
                    "SKIPPED_PREREQUISITE"
                    if value["requirement"] == "optional"
                    else "MISSING_REQUIRED_INPUT"
                )
                value.update(
                    preflight=status, reason=f"No simulation files for {value['dataset_id']}"
                )
                return value
            inventory = (
                _grib_inventory(paths, progress=progress)
                if source["model"] == "arome"
                else _netcdf_inventory(paths, progress=progress)
            )
            inventory["input_records"] = [file_record(r["path"]) for r in inventory["records"]]
            cache[key] = inventory
            if progress:
                progress(f"Inventory complete: {value['dataset_id']} ({len(paths)} files)")
        inventory = cache[key]
        value["input_files"] = [record["path"] for record in inventory["records"]]
        value["input_records"].extend(copy.deepcopy(inventory["input_records"]))
        count = len(value["input_files"])
        if count != value["expected_file_count"] and (
            input_policy == "strict" or value["mode"] == "ci"
        ):
            status = "MISSING_REQUIRED_INPUT"
            if value["requirement"] == "optional":
                status = (
                    "SKIPPED_PREREQUISITE"
                    if count < value["expected_file_count"]
                    else "INVALID_INPUT"
                )
            value.update(
                preflight=status,
                reason=f"Expected {value['expected_file_count']} files, found {count}",
            )
            return value
        if value["mode"] == "ci" and tuple(value["binding"]["shape"]) != inventory["shape"]:
            raise ValueError("Simulation grid differs from frozen CI geometry")
        if "centre_grid" in value["binding"]:
            x, y = value["binding"]["centre_grid"]
            lat, lon = inventory["coordinates"]
            centre = [float(lat[y, x]), float(lon[y, x])]
            import math

            if not all(math.isfinite(position) for position in centre):
                raise ValueError("Frozen fixed centre has invalid source coordinates")
            point = dict(zip(("latitude", "longitude"), centre, strict=True))
            if value["tracker"] in {"fixed_box", "prescribed_track"}:
                config["region"]["center"] = point
        if value["tracker"] == "utrack":
            if any(
                850.0 not in r["fields"].get("isobaricInhPa", {}).get("absv", set())
                for r in inventory["records"]
            ):
                value.update(
                    preflight="SKIPPED_PREREQUISITE",
                    reason="UTrack requires 850-hPa absolute vorticity at every model time",
                )
                return value
        selected = _selected_levels(value, inventory)
        gaps = _check_fields(value, inventory, selected)
        expected = dict(
            times=inventory["times"],
            levels=selected,
            input_coverage="complete" if count == value["expected_file_count"] else "partial",
            source_time_count=len(inventory["times"]),
            source_file_count=count,
            allowed_gaps=gaps,
            shape=list(inventory["shape"]),
            coordinate_metadata=inventory.get("coordinate_metadata", {}),
            complete_boxes=True,
        )
        if value["tracker"] == "fixed_box":
            point = config["region"]["center"]
            centre = _nearest(inventory["coordinates"], point["latitude"], point["longitude"])
            import math

            ny, nx = inventory["shape"]
            size = config["region"]["width_km"]
            spacing = _catalog()["datasets"][value["dataset_id"]]["resolution"]
            half_x = math.ceil(size["x"] * 1000 / spacing / 2)
            half_y = math.ceil(size["y"] * 1000 / spacing / 2)
            if (
                min(centre["cx"], nx - 1 - centre["cx"]) < half_x
                or min(centre["cy"], ny - 1 - centre["cy"]) < half_y
            ):
                raise ValueError("Fixed-centre extraction box exceeds the input domain")
            expected["centres"] = [centre.copy() for _ in inventory["times"]]
            expected["center"] = point
        elif value["tracker"] == "prescribed_track":
            try:
                path, times, centres = _prescribed(value, root, output, inventory)
            except FileNotFoundError as exc:
                value.update(preflight="SKIPPED_PREREQUISITE", reason=str(exc))
                return value
            if source["model"] == "arome":
                expected["center"] = dict(config["region"]["center"])
            config["region"].pop("center", None)
            config["region"]["track"] = {"file": str(path)}
            config["region"]["sources_coupling_time_association"] = "common"
            value["input_records"].append(file_record(path, content=True))
            expected.update(times=times, centres=centres, prescribed_track=str(path))
        value["expected"] = expected
        expected["products"] = _products_expected(value, selected, inventory)
        expected["source_times"] = {"atmosphere": expected["times"]}
        for gap in gaps:
            gap["source"] = "atmosphere"
            gap["field"] = (gap["variable"] if gap["group"] == "surface" else
                            f"{gap['group']}.{gap['variable']}")
        for contract in expected["products"]:
            if contract["role"] == "model_grid" and "centres" in expected:
                contract["native_centres"] = expected["centres"]
        if (
            value["tracker"] in {"wind_pressure", "prescribed_track", "utrack"}
            and len(expected["times"]) > 1
        ):
            expected["products"][0]["variables"].extend(["heading_deg", "dist", "speed"])
        # Check the final physical value bindings with the production resolver.
        SimulationConfig.from_mapping_with_model_preset(config)
        probe_dependencies(value)
    except ModuleNotFoundError as exc:
        if value["tracker"] == "utrack" and exc.name in {None, "utrack"}:
            value.update(preflight="SKIPPED_PREREQUISITE", reason=str(exc))
        else:
            value.update(preflight="INVALID_INPUT", reason=f"Missing input dependency: {exc}")
    except Exception as exc:
        value.update(preflight="INVALID_INPUT", reason=str(exc))
    return value
