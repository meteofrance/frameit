"""Strict v3 requests and their metadata-free runtime handoff.

Public source names and categories are not numerical loader groups. Binding
them to actual fields, grids and records belongs to metadata preflight.
"""

from __future__ import annotations

import copy
import difflib
import math
import os
import re
from decimal import Decimal
from pathlib import Path

import yaml

DEFAULTS = {
    "schema_version": 3,
    "run": {"name": "analysis", "description": ""},
    "sources": {},
    "region": {},
    "products": {"model_grid": True},
    "output": {"directory": "./output", "format": "netcdf", "overwrite": False, "writer": {}},
    "resources": {"scheduler": "threads", "native_threads": 1, "synchronous_export": False},
    "logging": {"level": "INFO"},
    "metadata": {"extra": {}},
}

# Direct numerical constructors still use the admitted FA adapter contract.
FA_DEFAULTS = {
    "profile": None, "subdomain": "CI", "earth_radius_m": None,
    "field_metadata": {}, "expected_source": {}, "backend": "epygram",
    "python_executable": None, "native_cubes": {},
    "max_points": 20_000_000, "timeout_seconds": 120.,
}

TRACKER_DEFAULTS = {
    "pressure_wind": {"search_width_km": 200., "refine_width_km": 100.},
    "pressure_centroid": {
        "convergence": {"max_iterations": 15, "tolerance_m": 250.},
        "motion": {"max_iterations": 50, "solver": "aitken", "relaxation": .25,
                   "tolerance_m": 250.},
        "sampling": {"r80_max_distance_km": 250., "radial_step_km": 2.5,
                     "azimuth_step_deg": 5.},
    },
    "utrack": {"use_gpu": False, "batch_size": 16},
    "multifield_vortex": {
        "profile": "all_no_thick",
        "numerics": {"analysis_step_km": 25., "refinement_km": 2.5,
                     "max_iterations": 20, "minimum_support": .8, "minimum_samples": 16},
        "quality": {"minimum_parameters": 2, "pressure_rise_pa": 50., "vt850_min_m_s": 1.5,
                    "max_separation_km": 425., "max_speed_m_s": 30.866666666666667,
                    "speed_check_interval_hours": 6.},
    },
}


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate keys, including duplicates hidden in nested sections."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ValueError(f"YAML keys must be strings (line {key_node.start_mark.line + 1})")
            if key in result:
                raise ValueError(f"Duplicate key {key!r} at line {key_node.start_mark.line + 1}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def read_yaml(path):
    path = Path(path)
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return data


def _merge_checked(raw, defaults, prefix=""):
    """Merge fixed-key controls; dynamic mappings are checked by their owner."""
    if not isinstance(raw, dict):
        raise ValueError(f"{prefix or 'configuration'} must be a mapping")
    result = copy.deepcopy(defaults)
    errors = []
    for key, value in raw.items():
        if not isinstance(key, str):
            errors.append(f"{prefix or 'configuration'} keys must be strings")
            continue
        location = f"{prefix}.{key}" if prefix else key
        if key not in defaults:
            suggestion = difflib.get_close_matches(key, defaults, n=1)
            errors.append(f"Unknown key {location}" +
                          (f"; did you mean {suggestion[0]}?" if suggestion else ""))
        elif isinstance(defaults[key], dict) and defaults[key]:
            try:
                result[key] = _merge_checked(value, defaults[key], location)
            except ValueError as exc:
                errors.append(str(exc))
        else:
            result[key] = copy.deepcopy(value)
    if errors:
        raise ValueError("\n".join(errors))
    return result


def _keys(raw, allowed, path, *, required=()):
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a mapping")
    for key in raw:
        if not isinstance(key, str) or key not in allowed:
            raise ValueError(f"Unknown key {path}.{key}")
    missing = set(required) - raw.keys()
    if missing:
        raise ValueError(f"{path} requires {', '.join(sorted(missing))}")
    return copy.deepcopy(raw)


def _reject_nulls(value, path=""):
    if path == "metadata.extra":
        if not isinstance(value, dict):
            raise ValueError("metadata.extra must be a mapping")
        return
    if value is None:
        raise ValueError(f"{path or 'configuration'} cannot be null; omit the key for its default")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path or 'configuration'} keys must be strings")
            _reject_nulls(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_nulls(child, f"{path}[{index}]")


def _text(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a nonempty string")


def _choice(value, choices, path):
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{path} must be one of {', '.join(sorted(choices))}")


def _boolean(value, path):
    if type(value) is not bool:
        raise ValueError(f"{path} must be a YAML boolean")


def _finite(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{path} must be a finite number")


def _positive(value, path, *, integer=False, allow_zero=False):
    _finite(value, path)
    if (integer and not isinstance(value, int)) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{path} must be {'nonnegative' if allow_zero else 'positive'}" +
                         (" integer" if integer else ""))


def _names(value, path, *, empty=False):
    if not isinstance(value, list) or (not empty and not value):
        raise ValueError(f"{path} must be a {'nonempty ' if not empty else ''}list of names")
    for name in value:
        _text(name, path)
    if len(set(value)) != len(value):
        raise ValueError(f"{path} contains duplicate names")
    return value


def _sizes(value, path, *, whole_axis=False):
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a dimension-size mapping")
    for name, count in value.items():
        _text(name, path)
        if not (whole_axis and type(count) is int and count == -1):
            _positive(count, f"{path}.{name}", integer=True)


def _path(value, base, path, *, preserve_symlink=False):
    _text(value, path)
    # Input aliases and virtualenv interpreter symlinks carry their own identity.
    return str((base / value).absolute() if preserve_symlink else (base / value).resolve())


def _paths(value, base, path, *, empty=False):
    if isinstance(value, str):
        return _path(value, base, path, preserve_symlink=True)
    if not isinstance(value, list) or (not value and not empty):
        raise ValueError(f"{path} must be a path/glob or a {'nonempty ' if not empty else ''}list")
    return [_path(item, base, path, preserve_symlink=True) for item in value]


def _center(value, path):
    result = _keys(value, {"latitude", "longitude"}, path, required={"latitude", "longitude"})
    for name, limit in (("latitude", 90), ("longitude", 180)):
        _finite(result[name], f"{path}.{name}")
        if abs(result[name]) > limit:
            raise ValueError(f"{path}.{name} must be in [-{limit}, {limit}] degrees")
    return result


def validate_wind_pressure_initial_guess(value):
    """Validate the direct numerical tracker's optional first-time search."""
    if value is None:
        return None
    path = "tracking.pressure_wind.initial_guess"
    guess = _merge_checked(value, {"latitude": None, "longitude": None,
                                  "search_radius_km": None}, path)
    _center({key: guess[key] for key in ("latitude", "longitude")}, path)
    _positive(guess["search_radius_km"], f"{path}.search_radius_km")
    return guess


def _runtime_group(group):
    if group == "surface":
        raise ValueError("Use fields_2d for fields without a selectable vertical axis, not surface")
    return "surface" if group == "fields_2d" else group


def validate_wind_pairs(pairs):
    """Validate the existing, already-bound numerical component declarations."""
    if not isinstance(pairs, list):
        raise ValueError("input.wind_pairs must be a list")
    seen = set()
    for index, pair in enumerate(pairs):
        path = f"input.wind_pairs[{index}]"
        required = {"group", "u", "v", "reference_frame"}
        if not isinstance(pair, dict) or not required <= set(pair) or set(pair) - (
            required | {"rotation"}
        ):
            raise ValueError(f"{path} requires group, u, v, reference_frame; optional rotation")
        for key in required:
            _text(pair[key], f"{path}.{key}")
        _choice(pair["reference_frame"], {"earth", "grid"}, f"{path}.reference_frame")
        if pair["u"] == pair["v"]:
            raise ValueError(f"{path} u and v must be distinct components")
        for name in (pair["u"], pair["v"]):
            identity = (pair["group"], name)
            if identity in seen:
                raise ValueError(f"{path}: duplicate wind component {identity}")
            seen.add(identity)
        rotation = pair.get("rotation")
        if "rotation" not in pair:
            if pair["reference_frame"] == "grid":
                raise ValueError(f"{path}.rotation is required for grid-relative winds")
            continue
        _rotation(rotation, f"{path}.rotation", strict=False)


def _rotation(rotation, path, *, strict=True):
    checked = _keys(rotation, {"method", "coordinate", "BETA", "RPK", "LON0"},
                    path, required={"method"})
    method = checked["method"]
    _choice(method, {"coordinate", "geolocation", "mesonh_projection"}, f"{path}.method")
    if method == "coordinate" and "coordinate" not in checked:
        raise ValueError(f"{path}.coordinate is required for method coordinate")
    if "coordinate" in checked:
        _text(checked["coordinate"], f"{path}.coordinate")
        if strict and method != "coordinate":
            raise ValueError(f"{path}.coordinate requires method coordinate")
    for name in ("BETA", "RPK", "LON0"):
        if name in checked:
            if method != "mesonh_projection":
                raise ValueError(f"{path}.{name} requires method mesonh_projection")
            _finite(checked[name], f"{path}.{name}")
            if name == "RPK" and abs(checked[name]) > 1:
                raise ValueError(f"{path}.RPK must be in [-1, 1]")


def validate_output_selections(horizontal, cartesian_vertical, polar_vertical):
    for path, value, choices in (
        ("output.cartesian.horizontal_winds", horizontal, {"native", "mass_earth"}),
        ("output.cartesian.vertical_velocity", cartesian_vertical, {"interfaces", "mass"}),
        ("output.polar.vertical_velocity", polar_vertical, {"interfaces", "mass"}),
    ):
        _choice(value, choices, path)


def validate_fa_options(options, selected=False):
    """Keep the admitted numerical FA contract; never infer meaning from names."""
    if options["backend"] != "epygram":
        raise ValueError("input.fa.backend must be epygram")
    if options["python_executable"] is not None:
        _text(options["python_executable"], "input.fa.python_executable")
    if options["profile"] is not None:
        _choice(options["profile"], {"arome_history", "surfex_history"}, "input.fa.profile")
    if selected and options["profile"] is None:
        raise ValueError("input.format fa requires input.fa.profile")
    _choice(options["subdomain"], {"CI", "C"}, "input.fa.subdomain")
    if options["earth_radius_m"] is not None:
        _positive(options["earth_radius_m"], "input.fa.earth_radius_m")
    _positive(options["max_points"], "input.fa.max_points", integer=True)
    _positive(options["timeout_seconds"], "input.fa.timeout_seconds")
    expected = options["expected_source"]
    if not isinstance(expected, dict) or set(expected) - {"PROGRAM", "VERSION", "BUG",
                                                        "MASDEV", "BUGFIX"}:
        raise ValueError("input.fa.expected_source accepts PROGRAM, VERSION, BUG, MASDEV, BUGFIX")
    for key, value in expected.items():
        if ((key == "PROGRAM" and (not isinstance(value, str) or not value.strip()))
                or (key != "PROGRAM" and (type(value) is not int or value < 0))):
            raise ValueError(f"input.fa.expected_source.{key}: invalid native source assertion")
    if not isinstance(options["field_metadata"], dict):
        raise ValueError("input.fa.field_metadata must be a mapping")
    for name, definition in options["field_metadata"].items():
        if not isinstance(name, str) or not name.isascii() or not 1 <= len(name) <= 16:
            raise ValueError("FA identifiers must contain 1–16 ASCII characters")
        if not isinstance(definition, dict) or set(definition) - {
            "units", "kind", "temporal_kind", "allow_unscaled", "long_name", "standard_name"
        }:
            raise ValueError(f"input.fa.field_metadata.{name}: invalid metadata keys")
        if not isinstance(definition.get("units"), str) or not definition["units"].strip():
            raise ValueError(f"{name}: explicit source units are required")
        _choice(definition.get("kind"), {"continuous", "categorical"}, f"{name}.kind")
        if definition.get("temporal_kind") != "instantaneous":
            raise ValueError(f"{name}: only explicit instantaneous FA fields are supported; "
                             "no accumulation interval is inferred from the file header")
        _boolean(definition.get("allow_unscaled", False), f"{name}.allow_unscaled")
        for key in ("long_name", "standard_name"):
            if key in definition and not isinstance(definition[key], str):
                raise ValueError(f"{name}: {key} must be a string")
    cubes = options["native_cubes"]
    if not isinstance(cubes, dict):
        raise ValueError("input.fa.native_cubes must be a mapping")
    if cubes and options["profile"] != "arome_history":
        raise ValueError("FA native_cubes require profile: arome_history")
    records_seen = set()
    for name, cube in cubes.items():
        if (not isinstance(name, str) or not name.isidentifier() or len(name) > 16
                or not name.isascii() or name.startswith("fa_")
                or name in {"time", "x", "y", "level", "level_w", "latitude", "longitude", "crs",
                            "source_i", "source_j", "forecast_period", "wind_speed"}
                or name not in options["field_metadata"]):
            raise ValueError("Each native cube needs a 1-16 character variable identifier "
                             "and explicit field_metadata")
        required = {"records", "vertical_position", "sampling"}
        if (not isinstance(cube, dict) or not required <= cube.keys()
                or cube.keys() - (required | {"vector_basis", "component_scaling"})):
            raise ValueError(f"native_cubes.{name}: requires records, vertical_position, sampling")
        _choice(cube["vertical_position"], {"mass", "interface"},
                f"native_cubes.{name}.vertical_position")
        if cube["sampling"] != "center":
            raise ValueError(f"native_cubes.{name}: only collocated center sampling is admitted")
        if cube.get("vector_basis") is not None:
            _choice(cube["vector_basis"], {"earth", "grid"}, f"native_cubes.{name}.vector_basis")
        if cube.get("component_scaling") not in (None, "physical_velocity"):
            raise ValueError(f"native_cubes.{name}: map-scaled/unknown component scaling is gated")
        records = cube["records"]
        if not isinstance(records, list) or not records:
            raise ValueError(f"native_cubes.{name}.records must be a nonempty exact record list")
        for record in records:
            if (not isinstance(record, str) or not 4 <= len(record) <= 16
                    or not record.isascii() or any(c in record for c in "*?[]")
                    or record in records_seen or record == name):
                raise ValueError(f"native_cubes.{name}: invalid or repeated native record")
            records_seen.add(record)


def _timestamp(value, path):
    """Check ISO syntax only: the source calendar decides which dates exist."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a quoted ISO timestamp")
    match = re.fullmatch(
        r"(\d{4,})-(\d{2})-(\d{2})"
        r"(?:T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?)?", value,
    )
    if not match:
        raise ValueError(f"{path} must be a quoted ISO timestamp")
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    numbers = tuple(int(item or 0) for item in (year, month, day, hour, minute, second))
    if not (1 <= numbers[1] <= 12 and 1 <= numbers[2] <= 31
            and numbers[3] < 24 and numbers[4] < 60 and numbers[5] < 60):
        raise ValueError(f"{path} must be an ISO timestamp with valid month/day/time ranges")
    if zone and zone != "Z" and (int(zone[1:3]) > 23 or int(zone[4:]) > 59):
        raise ValueError(f"{path} has an invalid ISO timezone offset")
    return (*numbers, Decimal(f"0.{fraction or '0'}")), zone


def _time(raw, path):
    time = _keys(raw, {"cycle", "start", "end", "values", "stride"}, path)
    if "values" in time and time.keys() & {"start", "end", "stride"}:
        raise ValueError(f"{path}.values is exclusive with start, end and stride")
    for key in ("start", "end", "cycle"):
        if key in time:
            _timestamp(time[key], f"{path}.{key}")
    if "start" in time and "end" in time:
        start, start_zone = _timestamp(time["start"], f"{path}.start")
        end, end_zone = _timestamp(time["end"], f"{path}.end")
        if start_zone == end_zone and start > end:
            raise ValueError(f"{path}.start must not follow end")
    if "values" in time:
        _names(time["values"], f"{path}.values")
        for value in time["values"]:
            _timestamp(value, f"{path}.values")
    if "stride" in time:
        _positive(time["stride"], f"{path}.stride", integer=True)
    return time


def _levels(raw, path):
    levels = _keys(raw, {"indices", "values", "domain", "units"}, path)
    strategies = levels.keys() & {"indices", "values", "domain"}
    if len(strategies) > 1:
        raise ValueError(f"{path} requires exactly one of indices, values or domain")
    if "units" in levels:
        _text(levels["units"], f"{path}.units")
    if "domain" in levels:
        _choice(levels["domain"], {"physical"}, f"{path}.domain")
    for key in ("indices", "values"):
        if key not in levels:
            continue
        value = levels[key]
        if isinstance(value, list):
            if not value:
                raise ValueError(f"{path}.{key} must be a nonempty list")
            for item in value:
                if key == "indices":
                    _positive(item, f"{path}.indices", integer=True, allow_zero=True)
                else:
                    _finite(item, f"{path}.values")
            if len(set(value)) != len(value):
                raise ValueError(f"{path}.{key} contains duplicate levels")
        else:
            bounds = {"start", "end", "step"} if key == "indices" else {"min", "max"}
            required = bounds - {"step"}
            interval = _keys(value, bounds, f"{path}.{key}", required=required)
            for bound, item in interval.items():
                if key == "indices":
                    _positive(item, f"{path}.{key}.{bound}", integer=True,
                              allow_zero=bound != "step")
                else:
                    _finite(item, f"{path}.{key}.{bound}")
            low, high = ("start", "end") if key == "indices" else ("min", "max")
            if interval[low] > interval[high]:
                raise ValueError(f"{path}.{key}.{low} must not exceed {high}")
    return levels


def _source(raw, name, base):
    path = f"sources.{name}"
    source = _keys(raw, {
        "model", "format", "profile", "files", "exclude", "time", "variables",
        "field_metadata", "interpretation", "native_cubes", "fa", "reader",
        "wind_pairs", "transforms", "derived",
    }, path, required={"files"})
    if "model" in source:
        _choice(source["model"], {"arome", "mesonh", "nemo", "croco"}, f"{path}.model")
    if "format" in source:
        _choice(source["format"], {"netcdf", "grib", "fa"}, f"{path}.format")
    model, fmt = source.get("model"), source.get("format")
    fa_declared = (fmt == "fa" or bool(source.keys() & {"profile", "native_cubes", "fa"})
                   or (isinstance(source.get("reader"), dict) and bool(
                       source["reader"].keys() & {"python_executable", "timeout_seconds", "max_points"})))
    if model in {"nemo", "croco"} and fmt not in {None, "netcdf"}:
        raise ValueError(f"{path}.format: {model} supports only NetCDF")
    source["files"] = _paths(source["files"], base, f"{path}.files")
    exclude = source.get("exclude", [])
    if not isinstance(exclude, list):
        raise ValueError(f"{path}.exclude must be a list of paths/globs")
    source["exclude"] = _paths(exclude, base, f"{path}.exclude", empty=True)
    if "time" in source:
        source["time"] = _time(source["time"], f"{path}.time")
    variables = _keys(source.get("variables", {}), {"2d", "3d", "levels"}, f"{path}.variables")
    names = []
    for category in ("2d", "3d"):
        if category in variables:
            names.extend(_names(variables[category], f"{path}.variables.{category}"))
    if len(set(names)) != len(names):
        raise ValueError(f"{path}.variables contains duplicate field requests")
    if "levels" in variables:
        variables["levels"] = _levels(variables["levels"], f"{path}.variables.levels")
    source["variables"] = variables
    metadata = source.setdefault("field_metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}.field_metadata must be a mapping")
    for field, declaration in metadata.items():
        _text(field, f"{path}.field_metadata")
        checked = _keys(declaration, {
            "units", "kind", "temporal_kind", "allow_unscaled", "long_name", "standard_name",
        }, f"{path}.field_metadata.{field}")
        for key in ("units", "long_name", "standard_name"):
            if key in checked:
                _text(checked[key], f"{path}.field_metadata.{field}.{key}")
        if "kind" in checked:
            _choice(checked["kind"], {"continuous", "categorical"},
                    f"{path}.field_metadata.{field}.kind")
        if "temporal_kind" in checked:
            _choice(checked["temporal_kind"], {"instantaneous", "mean", "accumulated"},
                    f"{path}.field_metadata.{field}.temporal_kind")
        if "allow_unscaled" in checked:
            if not fa_declared:
                raise ValueError(f"{path}.field_metadata.{field}.allow_unscaled is FA-only")
            _boolean(checked["allow_unscaled"], f"{path}.field_metadata.{field}.allow_unscaled")
    if "interpretation" in source:
        _choice(source["interpretation"], {"mesonh_surfex_sea"}, f"{path}.interpretation")
        if model not in {None, "mesonh"} or fmt not in {None, "netcdf"}:
            raise ValueError(f"{path}.interpretation requires Meso-NH NetCDF")
    reader = _keys(source.get("reader", {}), {
        "engine", "chunks", "python_executable", "timeout_seconds", "max_points",
    }, f"{path}.reader")
    if "engine" in reader:
        if fmt not in {None, "netcdf"} or fa_declared:
            raise ValueError(f"{path}.reader.engine is NetCDF-only")
        _choice(reader["engine"], {"h5netcdf", "netcdf4", "scipy"}, f"{path}.reader.engine")
    if "chunks" in reader:
        if fa_declared:
            raise ValueError(f"{path}.reader.chunks is not supported by the FA decoder")
        _sizes(reader["chunks"], f"{path}.reader.chunks", whole_axis=True)
    for key in ("python_executable", "timeout_seconds", "max_points"):
        if key not in reader:
            continue
        if fmt not in {None, "fa"}:
            raise ValueError(f"{path}.reader.{key} is FA-only")
        if key == "python_executable":
            reader[key] = _path(reader[key], base, f"{path}.reader.{key}", preserve_symlink=True)
        else:
            _positive(reader[key], f"{path}.reader.{key}", integer=key == "max_points")
    source["reader"] = reader
    if fa_declared and fmt in {None, "fa"}:
        if model not in {None, "arome"}:
            raise ValueError(f"{path}.model: current FA profiles require model: arome")
        _keys(source.get("fa", {}), {"subdomain", "earth_radius_m", "expected_source"}, f"{path}.fa")
        options = _fa_runtime_options(source)
        try:
            validate_fa_options(options, selected=True)
        except ValueError as exc:
            message = str(exc)
            for key in options:
                section = ("reader." if key in {"python_executable", "timeout_seconds", "max_points"}
                           else "fa." if key in {"subdomain", "earth_radius_m", "expected_source"}
                           else "")
                message = message.replace(f"input.fa.{key}", f"{path}.{section}{key}")
            message = message.replace("input.format fa", f"{path}.format: fa")
            raise ValueError(f"{path}: {message}") from exc
        if variables.get("levels", {}).get("domain") == "physical":
            raise ValueError(f"{path}.variables.levels: FA physical-domain selection is gated")
        for field in variables.get("3d", []):
            if field not in options["native_cubes"]:
                raise ValueError(f"{path}.variables.3d.{field} requires an explicit FA native cube")
        if set(variables.get("2d", [])) & options["native_cubes"].keys():
            raise ValueError(f"{path}.variables: select FA native cubes under 3d")
        source["fa"] = {key: options[key] for key in ("subdomain", "expected_source")}
        if options["earth_radius_m"] is not None:
            source["fa"]["earth_radius_m"] = options["earth_radius_m"]
        for key in ("timeout_seconds", "max_points"):
            reader.setdefault(key, options[key])
    elif source.keys() & {"profile", "native_cubes", "fa"}:
        key = sorted(source.keys() & {"profile", "native_cubes", "fa"})[0]
        raise ValueError(f"{path}.{key} is FA-only; declare format: fa")
    pairs = source.setdefault("wind_pairs", [])
    if not isinstance(pairs, list):
        raise ValueError(f"{path}.wind_pairs must be a list")
    seen = set()
    for index, pair in enumerate(pairs):
        loc = f"{path}.wind_pairs[{index}]"
        _keys(pair, {"u", "v", "basis", "rotation"}, loc, required={"u", "v", "basis"})
        for component in ("u", "v"):
            _text(pair[component], f"{loc}.{component}")
            if pair[component] in seen:
                raise ValueError(f"{loc}: duplicate wind component {pair[component]}")
            seen.add(pair[component])
        _choice(pair["basis"], {"earth", "grid"}, f"{loc}.basis")
        if "rotation" in pair:
            if pair["basis"] != "grid":
                raise ValueError(f"{loc}.rotation requires basis: grid")
            _rotation(pair["rotation"], f"{loc}.rotation")
    transforms = source.setdefault("transforms", [])
    if not isinstance(transforms, list):
        raise ValueError(f"{path}.transforms must be a list")
    for index, transform in enumerate(transforms):
        loc = f"{path}.transforms[{index}]"
        _keys(transform, {"fields", "sampling", "basis", "units"}, loc, required={"fields"})
        _names(transform["fields"], f"{loc}.fields")
        if not transform.keys() & {"sampling", "basis", "units"}:
            raise ValueError(f"{loc} needs sampling, basis or units")
        for key, choices in (("sampling", {"native", "mass"}), ("basis", {"native", "earth"})):
            if key in transform:
                _choice(transform[key], choices, f"{loc}.{key}")
        if "units" in transform:
            _text(transform["units"], f"{loc}.units")
    derived = source.setdefault("derived", {})
    if not isinstance(derived, dict):
        raise ValueError(f"{path}.derived must be a mapping")
    for field, definition in derived.items():
        loc = f"{path}.derived.{field}"
        _text(field, f"{path}.derived")
        if field in names:
            raise ValueError(f"{loc} collides with an exported source field")
        _keys(definition, {"method", "inputs"}, loc, required={"method", "inputs"})
        _choice(definition["method"], {"wind_speed"}, f"{loc}.method")
        inputs = _keys(definition["inputs"], {"u", "v"}, f"{loc}.inputs", required={"u", "v"})
        for key, value in inputs.items():
            _text(value, f"{loc}.inputs.{key}")
        if inputs["u"] == inputs["v"]:
            raise ValueError(f"{loc}.inputs needs distinct u and v")
    return source


def _fa_runtime_options(source):
    options = copy.deepcopy(FA_DEFAULTS)
    options.update(copy.deepcopy(source.get("fa", {})))
    for key in ("profile", "native_cubes", "field_metadata"):
        if key in source:
            options[key] = copy.deepcopy(source[key])
    options.update({key: value for key, value in source.get("reader", {}).items()
                    if key in {"python_executable", "timeout_seconds", "max_points"}})
    return options


def _region(raw, base):
    path = "region"
    region = _keys(raw, {
        "center", "track", "tracker", "width_km", "sources_coupling_time_association",
    }, path)
    providers = region.keys() & {"center", "track", "tracker"}
    if len(providers) > 1:
        raise ValueError("region.center, region.track and region.tracker are mutually exclusive")
    if "width_km" in region:
        if not providers:
            raise ValueError("region.width_km requires a center, track or tracker")
        size = _keys(region["width_km"], {"x", "y"}, "region.width_km", required={"x", "y"})
        for key, value in size.items():
            _positive(value, f"region.width_km.{key}")
    if "center" in region:
        region["center"] = _center(region["center"], "region.center")
    if "track" in region:
        track = _keys(region["track"], {"file"}, "region.track", required={"file"})
        track["file"] = _path(track["file"], base, "region.track.file")
        region["track"] = track
    if region:
        region.setdefault("sources_coupling_time_association", "exact")
        _choice(region["sources_coupling_time_association"],
                {"exact", "common", "preceding_hour"}, "region.sources_coupling_time_association")
    if "tracker" not in region:
        return region
    tracker = region["tracker"]
    if not isinstance(tracker, dict) or "method" not in tracker:
        raise ValueError("region.tracker.method is required")
    method = tracker["method"]
    _choice(method, set(TRACKER_DEFAULTS), "region.tracker.method")
    optional = {
        "pressure_wind": {"initial_guess"},
        "pressure_centroid": set(),
        "utrack": {"weights_file"},
        "multifield_vortex": {"seed", "mnh_gravity_m_s2"},
    }
    _keys(tracker, {"method", "on_incomplete"} | TRACKER_DEFAULTS[method].keys() | optional[method],
          "region.tracker")
    defaults = {"method": method, "on_incomplete": "error", **TRACKER_DEFAULTS[method],
                **{key: None for key in optional[method]}}
    tracker = _merge_checked(tracker, defaults, "region.tracker")
    tracker = {key: value for key, value in tracker.items() if value is not None}
    _choice(tracker["on_incomplete"], {"error", "keep_prefix"}, "region.tracker.on_incomplete")
    if tracker["on_incomplete"] == "keep_prefix" and method != "multifield_vortex":
        raise ValueError(f"region.tracker.on_incomplete: {method} does not support keep_prefix")
    if method == "pressure_wind":
        for key in ("search_width_km", "refine_width_km"):
            _positive(tracker[key], f"region.tracker.{key}")
        if "initial_guess" in tracker:
            guess = _keys(tracker["initial_guess"], {"latitude", "longitude", "search_radius_km"},
                          "region.tracker.initial_guess",
                          required={"latitude", "longitude", "search_radius_km"})
            _center({key: guess[key] for key in ("latitude", "longitude")},
                    "region.tracker.initial_guess")
            _positive(guess["search_radius_km"], "region.tracker.initial_guess.search_radius_km")
    elif method == "pressure_centroid":
        for section in ("convergence", "motion", "sampling"):
            for key, value in tracker[section].items():
                if key != "solver":
                    _positive(value, f"region.tracker.{section}.{key}",
                              integer=key == "max_iterations")
        _choice(tracker["motion"]["solver"], {"aitken", "fixed"}, "region.tracker.motion.solver")
        if tracker["motion"]["relaxation"] > 1:
            raise ValueError("region.tracker.motion.relaxation must not exceed 1")
        if tracker["sampling"]["azimuth_step_deg"] >= 180:
            raise ValueError("region.tracker.sampling.azimuth_step_deg must be below 180")
    elif method == "utrack":
        tracker["weights_file"] = _path(tracker.get("weights_file"), base,
                                       "region.tracker.weights_file")
        _boolean(tracker["use_gpu"], "region.tracker.use_gpu")
        _positive(tracker["batch_size"], "region.tracker.batch_size", integer=True)
    else:
        _choice(tracker["profile"], {"all_no_thick"}, "region.tracker.profile")
        seed = _keys(tracker.get("seed"), {
            "latitude", "longitude", "time", "motion_u_m_s", "motion_v_m_s",
        }, "region.tracker.seed", required={"latitude", "longitude", "motion_u_m_s", "motion_v_m_s"})
        _center({key: seed[key] for key in ("latitude", "longitude")}, "region.tracker.seed")
        if not 0 < abs(seed["latitude"]) < 90:
            raise ValueError("region.tracker.seed.latitude must be non-equatorial and nonpolar")
        for key in ("motion_u_m_s", "motion_v_m_s"):
            _finite(seed[key], f"region.tracker.seed.{key}")
        if "time" in seed:
            _timestamp(seed["time"], "region.tracker.seed.time")
        if "mnh_gravity_m_s2" in tracker:
            _positive(tracker["mnh_gravity_m_s2"], "region.tracker.mnh_gravity_m_s2")
        from frameit.tracking.multifield_vortex import VortexOptions

        try:
            VortexOptions(**tracker["numerics"], **tracker["quality"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"region.tracker: {exc}") from exc
    region["tracker"] = tracker
    return region


def _mask_options(options, path, *, defaults=False):
    if defaults:
        options.setdefault("missing_data_policy", "strict")
    if "interpolation" in options:
        _choice(options["interpolation"], {"bilinear", "nearest"}, f"{path}.interpolation")
    policy = options.get("missing_data_policy", "strict")
    _choice(policy, {"strict", "renormalize"}, f"{path}.missing_data_policy")
    if policy == "renormalize":
        if "min_valid_weight_fraction" not in options:
            raise ValueError(f"{path}.min_valid_weight_fraction is required for renormalize")
        if options.get("interpolation") == "nearest":
            raise ValueError(f"{path}: nearest interpolation cannot renormalize a partial stencil")
    elif "min_valid_weight_fraction" in options:
        raise ValueError(f"{path}.min_valid_weight_fraction requires renormalize")
    if "min_valid_weight_fraction" in options:
        value = options["min_valid_weight_fraction"]
        _positive(value, f"{path}.min_valid_weight_fraction")
        if value > 1:
            raise ValueError(f"{path}.min_valid_weight_fraction must not exceed 1")


def _products(raw, sources, region):
    products = _keys(raw, {"model_grid", "polar", "track"}, "products")
    if not products:
        raise ValueError("products must request at least one product; omit it for model_grid")
    for product, spec in list(products.items()):
        path = f"products.{product}"
        if product in {"model_grid", "track"} and spec is True:
            spec = {}
        if product == "track":
            _keys(spec, set(), path)
            if not region.keys() & {"center", "track", "tracker"}:
                raise ValueError("products.track requires a region center, track or tracker")
            continue
        allowed = {"fields", "processing"}
        if product == "polar":
            allowed |= {"radius_km", "radial_step_km", "azimuth_count", "shared_grid",
                        "missing_data_policy", "min_valid_weight_fraction", "field_options"}
        spec = _keys(spec, allowed, path, required={"radius_km"} if product == "polar" else ())
        if "fields" in spec:
            fields = spec["fields"]
            if not isinstance(fields, dict) or not fields:
                raise ValueError(f"{path}.fields must be a nonempty source-name mapping")
            for name, names in fields.items():
                if name not in sources:
                    raise ValueError(f"{path}.fields.{name}: unknown source")
                _names(names, f"{path}.fields.{name}")
                available = _declared_fields(sources[name])
                if not set(names) <= set(available):
                    raise ValueError(f"{path}.fields.{name}: unknown field/result; declare it in sources")
        processing = spec.get("processing", {})
        processing_keys = {"chunks"}
        if product == "polar":
            processing_keys |= {"max_target_points", "plan_cache", "source_halo_points",
                                "weight_zero_tolerance", "profile"}
        _keys(processing, processing_keys, f"{path}.processing")
        if "chunks" in processing:
            _sizes(processing["chunks"], f"{path}.processing.chunks", whole_axis=True)
        if product == "polar":
            if not region.keys() & {"center", "track", "tracker"}:
                raise ValueError(f"{path} requires a region center, track or tracker")
            _positive(spec["radius_km"], f"{path}.radius_km")
            if "radial_step_km" in spec:
                _positive(spec["radial_step_km"], f"{path}.radial_step_km")
            if "azimuth_count" in spec:
                _positive(spec["azimuth_count"], f"{path}.azimuth_count", integer=True)
                if spec["azimuth_count"] < 3:
                    raise ValueError(f"{path}.azimuth_count must be at least 3")
            spec.setdefault("shared_grid", False)
            _boolean(spec["shared_grid"], f"{path}.shared_grid")
            _mask_options(spec, path, defaults=True)
            for key in ("max_target_points", "source_halo_points"):
                if key in processing:
                    _positive(processing[key], f"{path}.processing.{key}", integer=True)
            if "weight_zero_tolerance" in processing:
                value = processing["weight_zero_tolerance"]
                _positive(value, f"{path}.processing.weight_zero_tolerance", allow_zero=True)
                if value >= 1e-6:
                    raise ValueError(f"{path}.processing.weight_zero_tolerance must be below 1e-6")
            if "profile" in processing:
                _boolean(processing["profile"], f"{path}.processing.profile")
            if "plan_cache" in processing:
                cache = _keys(processing["plan_cache"], {"entries", "max_bytes"},
                              f"{path}.processing.plan_cache")
                for key, value in cache.items():
                    _positive(value, f"{path}.processing.plan_cache.{key}",
                              integer=True, allow_zero=True)
            options = spec.get("field_options", {})
            if not isinstance(options, dict):
                raise ValueError(f"{path}.field_options must be a source-name mapping")
            for name, fields in options.items():
                if name not in sources or not isinstance(fields, dict):
                    raise ValueError(f"{path}.field_options.{name}: unknown source or invalid mapping")
                exports = _product_fields(spec, sources, name)
                needed = set(exports) | set(_derived_inputs(sources[name], exports))
                for field, values in fields.items():
                    loc = f"{path}.field_options.{name}.{field}"
                    if field not in needed:
                        raise ValueError(f"{loc}: field is unused by this product")
                    _keys(values, {"interpolation", "missing_data_policy",
                                   "min_valid_weight_fraction", "sampling"}, loc)
                    effective = {key: spec[key] for key in
                                 ("missing_data_policy", "min_valid_weight_fraction") if key in spec}
                    if values.get("missing_data_policy") == "strict":
                        effective.pop("min_valid_weight_fraction", None)
                    effective.update(values)
                    _mask_options(effective, loc)
                    if "sampling" in values:
                        _choice(values["sampling"], {"native", "mass"}, f"{loc}.sampling")
                    if field in sources[name]["derived"] and values.keys() & {
                        "interpolation", "sampling", "missing_data_policy", "min_valid_weight_fraction",
                    }:
                        raise ValueError(f"{loc}: set polar preparation on the derived result's inputs")
        products[product] = (True if product == "model_grid" and not spec else spec)
    return products


def _declared_fields(source):
    return [*source["variables"].get("2d", []), *source["variables"].get("3d", []),
            *source["derived"]]


def _product_fields(spec, sources, name):
    return (spec["fields"].get(name, []) if isinstance(spec, dict) and "fields" in spec
            else _declared_fields(sources[name]))


def _derived_inputs(source, exports, visiting=()):
    inputs = []
    for field in exports:
        if field not in source["derived"]:
            continue
        if field in visiting:
            raise ValueError(f"sources: derived inputs contain a cycle at {field}")
        dependencies = list(source["derived"][field]["inputs"].values())
        inputs.extend(dependencies)
        inputs.extend(_derived_inputs(source, dependencies, (*visiting, field)))
    return list(dict.fromkeys(inputs))


def _output(raw, base):
    output = _merge_checked(raw, DEFAULTS["output"], "output")
    output["directory"] = _path(output["directory"], base, "output.directory")
    _choice(output["format"], {"netcdf", "zarr"}, "output.format")
    _boolean(output["overwrite"], "output.overwrite")
    writer = _keys(output["writer"], {
        "engine", "unlimited_time", "compression", "chunks", "shards",
    }, "output.writer")
    if output["format"] == "zarr":
        for key in ("engine", "unlimited_time"):
            if key in writer:
                raise ValueError(f"output.writer.{key} is NetCDF-only, even with products.track")
    else:
        if "shards" in writer:
            raise ValueError("output.writer.shards is Zarr-only")
        writer.setdefault("engine", "netcdf4")
        writer.setdefault("unlimited_time", True)
        _choice(writer["engine"], {"netcdf4", "h5netcdf"}, "output.writer.engine")
        _boolean(writer["unlimited_time"], "output.writer.unlimited_time")
    compression = _merge_checked(writer.get("compression", {}),
                                 {"level": 1, "coordinates": False}, "output.writer.compression")
    _positive(compression["level"], "output.writer.compression.level", integer=True, allow_zero=True)
    if compression["level"] > 9:
        raise ValueError("output.writer.compression.level must be in [0, 9]")
    _boolean(compression["coordinates"], "output.writer.compression.coordinates")
    writer["compression"] = compression
    for key in ("chunks", "shards"):
        if key in writer:
            _sizes(writer[key], f"output.writer.{key}")
    if output["format"] == "zarr":
        from frameit.io.zarr_export import validate_zarr_sizes

        validate_zarr_sizes(writer.get("chunks", {}), writer.get("shards", {}))
    output["writer"] = writer
    return output


def resolve_schema(raw, *, base_dir=None):
    """Return ``(document, source_requests, polar_fields)`` without opening inputs."""
    if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int or raw["schema_version"] != 3:
        raise ValueError("Expected schema_version: 3 (a YAML integer, not a boolean or string)")
    _reject_nulls(raw)
    _keys(raw, set(DEFAULTS), "configuration", required={"sources"})
    base = Path(base_dir or Path.cwd()).resolve()
    conf = copy.deepcopy(DEFAULTS)
    conf["run"] = _merge_checked(raw.get("run", {}), DEFAULTS["run"], "run")
    _text(conf["run"]["name"], "run.name")
    if "/" in conf["run"]["name"] or "\\" in conf["run"]["name"] or conf["run"]["name"] in {".", ".."}:
        raise ValueError("run.name must be an identifier without path separators")
    if not isinstance(conf["run"]["description"], str):
        raise ValueError("run.description must be a string")
    sources = raw["sources"]
    if not isinstance(sources, dict) or not sources:
        raise ValueError("sources must be a nonempty mapping of source names")
    for name, spec in sources.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
            raise ValueError("sources names must start with a letter and contain letters/digits/_/-")
        conf["sources"][name] = _source(spec, name, base)
    conf["region"] = _region(raw.get("region", {}), base)
    conf["products"] = _products(raw.get("products", DEFAULTS["products"]),
                                conf["sources"], conf["region"])
    conf["output"] = _output(raw.get("output", {}), base)
    resources = _keys(raw.get("resources", {}), {
        "cpus", "scheduler", "compute_workers", "export_workers", "native_threads", "synchronous_export",
    }, "resources")
    resources = {**DEFAULTS["resources"], **resources}
    _choice(resources["scheduler"], {"threads", "synchronous"}, "resources.scheduler")
    _boolean(resources["synchronous_export"], "resources.synchronous_export")
    for key in ("cpus", "compute_workers", "export_workers", "native_threads"):
        if key in resources:
            _positive(resources[key], f"resources.{key}", integer=True)
    conf["resources"] = resources
    conf["logging"] = _merge_checked(raw.get("logging", {}), DEFAULTS["logging"], "logging")
    _choice(conf["logging"]["level"], {"DEBUG", "INFO", "WARNING", "ERROR"}, "logging.level")
    conf["metadata"] = _keys(raw.get("metadata", {}), {"institution", "extra"}, "metadata")
    conf["metadata"].setdefault("extra", {})
    if "institution" in conf["metadata"] and not isinstance(conf["metadata"]["institution"], str):
        raise ValueError("metadata.institution must be a string")
    requests, polar = {}, {}
    for name, source in conf["sources"].items():
        exports = {product: _product_fields(spec, conf["sources"], name)
                   for product, spec in conf["products"].items() if product != "track"}
        exports = {product: list(fields) for product, fields in exports.items() if fields}
        needed = list(dict.fromkeys(field for fields in exports.values() for field in fields))
        internal = _derived_inputs(source, needed)
        # Cycles are invalid declarations even when a product filters the result out.
        _derived_inputs(source, list(source["derived"]))
        requests[name] = {
            "fields": {key: copy.deepcopy(source["variables"].get(key, [])) for key in ("2d", "3d")},
            "levels": copy.deepcopy(source["variables"].get("levels", {})),
            "derived": copy.deepcopy(source["derived"]),
            "exports": exports, "internal_inputs": internal,
            "transforms": copy.deepcopy(source["transforms"]),
            "polar_options": copy.deepcopy(conf["products"].get("polar", {}).get(
                "field_options", {}).get(name, {})),
            "binding": None,
        }
        if "polar" in exports:
            polar[name] = list(exports["polar"])
    return conf, requests, polar


def source_document(parent, name):
    """Return an independent v3 request for one source, without invented geometry."""
    document = _source_document(parent, name)
    if document.get("products") == {}:
        raise ValueError(f"Source {name!r} is not requested by any product")
    return document


def _source_document(parent, name):
    if name not in parent["sources"]:
        raise ValueError(f"Unknown source {name!r}")
    document = copy.deepcopy(parent)
    document["sources"] = {name: document["sources"][name]}
    for product, spec in list(document.get("products", {}).items()):
        if not isinstance(spec, dict):
            continue
        if "fields" in spec:
            if name not in spec["fields"]:
                del document["products"][product]
                continue
            spec["fields"] = {name: spec["fields"][name]}
        if "field_options" in spec:
            spec["field_options"] = {name: spec["field_options"][name]} if name in spec["field_options"] else {}
    return document


def _source_runtime(parent, name):
    """Project a v3 SimulationConfig into source-local constructor arguments.

    Dependency-only children may have no products internally. Only the parent
    owns a track export; this view is not a standalone public YAML document.
    """
    document = _source_document(parent.yaml_config, name)
    document["products"].pop("track", None)
    origins = {path: parent.schema_sources.get(path, "automatic")
               for path in setting_sources({}, document)}
    requests = {name: copy.deepcopy(parent.source_requests[name])}
    return _runtime_from_resolved(document, requests, origins,
                                  base_dir=parent.simulation_output_dir)


def _request_plan(conf, requests):
    products = []
    suffix = "nc" if conf["output"]["format"] == "netcdf" else "zarr"
    for product in conf["products"]:
        if product == "track":
            products.append({
                "source": None, "product": "track",
                "path": f"products/{conf['run']['name']}.track.nc",
                "fields": ["latitude", "longitude"], "stored_names": None,
                "dimensions": None, "units": None, "representation": "trajectory",
                "time_association": conf["region"].get("sources_coupling_time_association"),
            })
            continue
        for name, req in requests.items():
            if product not in req["exports"]:
                continue
            products.append({
                "source": name, "product": product,
                "path": f"products/{conf['run']['name']}.{name}.{product}.{suffix}",
                "fields": list(req["exports"][product]), "stored_names": None,
                "dimensions": None, "units": None, "representation": product,
                "time_association": conf["region"].get("sources_coupling_time_association"),
            })
    return {
        "sources": {name: {
            "declaration": copy.deepcopy(source), "physical_type": None,
            "model": source.get("model"), "profile": source.get("profile"),
            "files": None, "metadata_origins": {}, "records": None, "native_grids": None,
            "requests": copy.deepcopy(requests[name]),
        } for name, source in conf["sources"].items()},
        "products": products, "warnings": [],
        "deferred_checks": [
            "Bind source models, formats, physical types, files, fields, times and native grids from metadata.",
            "Check method applicability, units, level availability, dependencies, geometry and resources.",
        ],
    }


def to_runtime(raw, *, base_dir=None):
    """Return SimulationConfig arguments; source requests remain unbound."""
    conf, requests, _ = resolve_schema(raw, base_dir=base_dir)
    return _runtime_from_resolved(conf, requests, setting_sources(raw, conf), base_dir=base_dir)


def _runtime_from_resolved(conf, requests, origins, *, base_dir=None):
    name = next(iter(conf["sources"])) if len(conf["sources"]) == 1 else None
    source = conf["sources"][name] if name else {}
    region, products = conf["region"], conf["products"]
    tracker = region.get("tracker", {})
    method = tracker.get("method")
    method = "wind_pressure" if method == "pressure_wind" else method
    if "center" in region:
        method = "fixed_box"
    elif "track" in region:
        method = "prescribed_track"
    polar = products.get("polar", {})
    processing = polar.get("processing", {})
    cache = processing.get("plan_cache", {})
    size = region.get("width_km", {})
    pc = tracker if method == "pressure_centroid" else TRACKER_DEFAULTS["pressure_centroid"]
    runtime = {
        "schema_version": 3, "yaml_config": conf, "schema_sources": origins,
        "sources": copy.deepcopy(conf["sources"]), "source_name": name,
        "source_requests": copy.deepcopy(requests),
        "simulation_parameter": {"request_plan": _request_plan(conf, requests)},
        "simulation_name": conf["run"]["name"], "comment": conf["run"]["description"],
        "atm_model": {"arome": "AROME", "mesonh": "MNH", "nemo": "NEMO", "croco": "CROCO"}.get(
            source.get("model")),
        "ocean_model": "", "wave_model": "", "resolution": 0, "infer_grid_geometry": True,
        "file_name_prefix": "", "file_name": "", "file_name_suffix": "",
        "file_type": source.get("format", ""), "input_sources": {}, "tracking_source": None,
        "simulation_output_dir": str(Path(base_dir or Path.cwd()).resolve()),
        "frameit_output_dir": conf["output"]["directory"], "input_files": None,
        "input_exclude": source.get("exclude", []),
        "time_alignment": region.get("sources_coupling_time_association", "exact"),
        "fa_options": _fa_runtime_options(source) if source.get("format") == "fa" else {},
        "netcdf_engine": source.get("reader", {}).get("engine", "h5netcdf"),
        "netcdf_chunks": source.get("reader", {}).get("chunks", {}),
        "wind_pairs": [], "wind_reference_frame": None,
        "cartesian_horizontal_winds": "native", "cartesian_vertical_velocity": "interfaces",
        "polar_vertical_velocity": "interfaces", "tracking_method": method,
        "fix_subdomain_center": [region["center"][key] for key in ("latitude", "longitude")]
        if "center" in region else None,
        "wind_pressure_search_half_width_km": tracker.get("search_width_km", 200.) / 2,
        "wind_pressure_refine_half_width_km": tracker.get("refine_width_km", 100.) / 2,
        "wind_pressure_initial_guess": tracker.get("initial_guess"),
        "prescribed_track_file": region.get("track", {}).get("file", ""),
        "utrack_weights_file": tracker.get("weights_file"),
        "utrack_use_gpu": tracker.get("use_gpu", False),
        "utrack_batch_size": tracker.get("batch_size", 16),
        "pressure_centroid_max_iterations": pc["convergence"]["max_iterations"],
        "pressure_centroid_tolerance_m": pc["convergence"]["tolerance_m"],
        "pressure_centroid_max_motion_iterations": pc["motion"]["max_iterations"],
        "pressure_centroid_motion_solver": pc["motion"]["solver"],
        "pressure_centroid_motion_relaxation": pc["motion"]["relaxation"],
        "pressure_centroid_motion_tolerance_m": pc["motion"]["tolerance_m"],
        "pressure_centroid_r80_max_km": pc["sampling"]["r80_max_distance_km"],
        "pressure_centroid_dr_km": pc["sampling"]["radial_step_km"],
        "pressure_centroid_dtheta": pc["sampling"]["azimuth_step_deg"],
        "multifield_vortex": ({**tracker, "seed": {"time": None, **tracker["seed"]},
                              "mnh_gravity_m_s2": tracker.get("mnh_gravity_m_s2"),
                              "on_track_loss":
                              "stop" if tracker["on_incomplete"] == "keep_prefix" else "error"}
                             if method == "multifield_vortex" else {}),
        "requested_variables_user": {}, "polar_variables": {},
        "x_boxsize_km": size.get("x", 0), "y_boxsize_km": size.get("y", 0),
        "compute_polar_proj": "polar" in products, "polar_shared_target": polar.get("shared_grid", False),
        "radial_resolution": polar.get("radial_step_km", 0) * 1000,
        "azimuthal_resolution": None, "polar_n_theta": polar.get("azimuth_count"),
        "polar_max_points": processing.get("max_target_points", 2_000_000),
        "polar_missing_data_policy": polar.get("missing_data_policy", "strict"),
        "polar_min_valid_weight_fraction": polar.get("min_valid_weight_fraction", .5),
        "polar_weight_zero_tolerance": processing.get("weight_zero_tolerance", 1e-14),
        "polar_source_halo_points": processing.get("source_halo_points", 1),
        "polar_regrid_cache_size": cache.get("entries", 8),
        "polar_regrid_cache_max_bytes": cache.get("max_bytes", 128 * 1024**2),
        "polar_output_chunks": processing.get("chunks", {}), "polar_profile": processing.get("profile", False),
        "log_level": conf["logging"]["level"], "DEBUG": conf["logging"]["level"] == "DEBUG",
    }
    # Copy fields separately; one deepcopy of runtime would preserve YAML aliases.
    return {key: copy.deepcopy(value) for key, value in runtime.items()}


def setting_sources(raw, resolved, prefix=""):
    origins = {}
    for key, value in resolved.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and value:
            child = raw.get(key, {})
            origins.update(setting_sources(child if isinstance(child, dict) else {}, value, path))
        else:
            origins[path] = "yaml" if key in raw else "default"
    return origins


def resolve_operational_overrides(raw, *, base_dir=None, launch_dir=None, overrides=None):
    """Return ``(effective_document, dotted_origins)`` for CLI > YAML > defaults.

    ``overrides`` accepts output_directory, cpus, overwrite and log_level.
    Absence means no override; explicit null is not an omitted flag.
    """
    conf, _, _ = resolve_schema(raw, base_dir=base_dir)
    origins = setting_sources(raw, conf)
    overrides = _keys(overrides if overrides is not None else {}, {
        "output_directory", "cpus", "overwrite", "log_level",
    }, "overrides")
    _reject_nulls(overrides, "overrides")
    for key, section, setting in (
        ("output_directory", "output", "directory"), ("cpus", "resources", "cpus"),
        ("overwrite", "output", "overwrite"), ("log_level", "logging", "level"),
    ):
        if key not in overrides:
            continue
        value = overrides[key]
        if key == "output_directory":
            if isinstance(value, os.PathLike):
                value = os.fspath(value)
            value = _path(value, Path(launch_dir or Path.cwd()).resolve(), f"overrides.{key}")
        conf[section][setting] = value
        origins[f"{section}.{setting}"] = "cli"
    # Reuse the same value checks for YAML and CLI controls.
    return resolve_schema(conf, base_dir=base_dir)[0], origins


def resolved_configuration(conf, options=None):
    """Return valid effective v3 controls, without inserting pending metadata."""
    result = copy.deepcopy(conf.yaml_config)
    if options is None:
        return result
    writer, resources = result["output"]["writer"], result["resources"]
    result["output"]["overwrite"] = options.overwrite
    result["output"]["format"] = "zarr" if options.engine == "zarr" else "netcdf"
    writer["compression"] = {"level": options.compress_level, "coordinates": options.compress_coords}
    if options.engine == "zarr":
        writer.pop("engine", None)
        writer.pop("unlimited_time", None)
        if options.zarr_chunk_size:
            writer["chunks"] = dict(options.zarr_chunk_size)
        if options.zarr_shard_size:
            writer["shards"] = dict(options.zarr_shard_size)
    else:
        writer.pop("shards", None)
        writer["engine"], writer["unlimited_time"] = options.engine, options.unlimited_time
    for attr, key in (("cpus", "cpus"), ("dask_workers", "compute_workers"), ("max_workers", "export_workers")):
        if getattr(options, attr) is not None:
            resources[key] = getattr(options, attr)
    resources.update(scheduler=options.dask_scheduler, native_threads=options.native_threads,
                     synchronous_export=options.synchronous_export)
    if options.institution or "institution" in result["metadata"]:
        result["metadata"]["institution"] = options.institution
    result["logging"]["level"] = options.log_level or conf.log_level or "INFO"
    return result


def resolved_sources(conf, options=None):
    origins = dict(conf.schema_sources)
    if options is not None:
        effective = resolved_configuration(conf, options)
        baseline = setting_sources(conf.yaml_config, effective)

        def mark(before, after, prefix=""):
            for key, value in after.items():
                path = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    mark(before.get(key, {}), value, path)
                elif key not in before or before[key] != value:
                    origins[path] = "cli"

        mark(conf.yaml_config, effective)
        for path in baseline:
            origins.setdefault(path, "default")
    return origins


def load_runtime(path):
    """Load strict YAML and add authored line locations to dotted-key errors."""
    path = Path(path)
    raw = read_yaml(path)
    try:
        return to_runtime(raw, base_dir=path.resolve().parent)
    except ValueError as exc:
        locations = {}

        def visit(node, prefix=""):
            if isinstance(node, yaml.MappingNode):
                for key, value in node.value:
                    name = f"{prefix}.{key.value}" if prefix else key.value
                    locations[name] = key.start_mark.line + 1
                    visit(value, name)

        visit(yaml.compose(path.read_text(encoding="utf-8")))
        message = str(exc)
        matches = [(name, line) for name, line in locations.items() if name in message]
        if matches:
            message += "\n" + ", ".join(f"{name}: line {line}" for name, line in matches)
        raise ValueError(f"{path}: {message}") from exc


TEMPLATES = {
    "arome-pressure-wind": "arome", "mesonh-pressure-wind": "mesonh",
    "arome-fixed-scalar": "arome-fixed-scalar", "nemo-native": "nemo", "croco-native": "croco",
    "arome-nemo": "arome-nemo", "mesonh-croco": "mesonh-croco",
}


def write_template(name, path, *, tracking=None, coupling=None, force=False):
    """Select a declared starter; preserve its comments, not an exhaustive defaults dump."""
    from importlib import resources

    from frameit.utils.atomic import atomic_output

    if not isinstance(name, str):
        raise ValueError("Template selector must be a model or named workflow")
    if name in TEMPLATES:
        if tracking is not None or coupling is not None:
            raise ValueError("Named workflows reject tracking/coupling flags; select a model to compose")
        resource = TEMPLATES[name]
    elif name in {"arome", "mesonh", "nemo", "croco"}:
        if coupling is not None:
            if (name, coupling) not in {("arome", "nemo"), ("mesonh", "croco")}:
                raise ValueError("Starter coupling supports only arome+nemo or mesonh+croco")
            tracking = tracking or "fixed_box"
            allowed = {"fixed_box", "prescribed_track", "pressure_wind", "pressure_centroid"}
            resource = f"{name}-{coupling}"
        else:
            atmospheric = name in {"arome", "mesonh"}
            tracking = tracking or ("pressure_wind" if atmospheric else "fixed_box")
            allowed = {"fixed_box", "prescribed_track"}
            if atmospheric:
                allowed |= {"pressure_wind", "pressure_centroid"}
            resource = (f"{name}-fixed-scalar" if atmospheric and tracking in {
                "fixed_box", "prescribed_track"} else name)
        if tracking not in allowed:
            raise ValueError(f"Unsupported starter tracking selection: {name}/{coupling}/{tracking}")
    else:
        raise ValueError(f"Unknown template selector: {name}")

    text = resources.files("frameit").joinpath(f"templates/{resource}.yaml").read_text(encoding="utf-8")
    starter = yaml.safe_load(text)
    method = tracking or starter["tracking"]["method"]
    if method != starter["tracking"]["method"]:
        block = "tracking:\n" + ("  source: atmosphere\n" if coupling else "")
        block += f"  method: {method}\n"
        if method == "prescribed_track":
            block += ("  # Exact timestamps and geographic degrees; no nearest-time matching.\n"
                      "  # Replace both instructional data and track when using real inputs.\n"
                      "  prescribed_track:\n    file: ./track.nc\n")
        text = re.sub(r"(?ms)^tracking:\n.*?(?=^domain:)", lambda _: block, text, count=1)
        text = text.replace(f"  name: {starter['run']['name']}\n",
                            f"  name: {name}{'-' + coupling if coupling else ''}-{method.replace('_', '-')}\n")
    if method == "pressure_centroid":
        pair = ("{group: isobaricInhPa, u: u, v: v, reference_frame: earth}" if name == "arome"
                else "{group: level, u: UT_ZM, v: VT_ZM, reference_frame: earth}")
        if not coupling:
            text = text.replace("tracking:\n", f"    - {pair}\ntracking:\n", 1)
        guidance = ("# Verify wind declarations and source ASL/pressure/native brackets.\n"
                    "# Keep full 500-km reference-ring support; Meso-NH must bracket 2000 m ASL.\n")
        if coupling:
            guidance += "# Requires at least two exact common times across sources.\n"
        text = text.replace("tracking:\n", guidance + "tracking:\n", 1)
    if coupling and method in {"pressure_wind", "pressure_centroid"}:
        u, v = ("u10", "v10") if name == "arome" else ("UM10", "VM10")
        declarations = ("        # Atmospheric tracker winds, independent of ocean sampling.\n"
                        "        # Verify the actual source wind basis and velocity/pressure units.\n"
                        "        # earth: u positive eastward, v positive northward.\n"
                        "        wind_pairs:\n"
                        f"          - {{group: fields_2d, u: {u}, v: {v}, reference_frame: earth}}\n")
        if method == "pressure_centroid":
            declarations += f"          - {pair}\n"
        # Both coupled resources put the atmosphere first; leave ocean inputs untouched.
        text = text.replace("        format: netcdf\n", "        format: netcdf\n" + declarations, 1)
        text = text.replace("target, winds, currents", "target, currents")
    if coupling and name == "mesonh" and method == "pressure_wind":
        text = text.replace("          names: [SST, SSS]", "          names: [SST, SSS, UM10, VM10, MSLP]")
        text += "  cartesian:\n    horizontal_vectors: earth_centered\n"
    path = Path(path)
    resolve_schema(yaml.safe_load(text), base_dir=path.absolute().parent)
    with atomic_output(path, overwrite=force) as temporary:
        temporary.write_text(text, encoding="utf-8")
    return path
