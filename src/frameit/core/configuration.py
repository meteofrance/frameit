"""Strict v2.1 public configuration and lightweight inspection tools.

The nested public schema resolves to SimulationConfig's internal numerical
interface. Public documents are not internal dataclass/preset dictionaries.
"""

from __future__ import annotations

import copy
import difflib
import math
import os
import re
from pathlib import Path

import yaml

DEFAULTS = {
    "schema_version": "2.1",
    "model": "arome",
    "run": {"name": "analysis", "description": ""},
    "input": {
        "directory": "./data", "pattern": None, "files": None, "exclude": [],
        "format": None, "grid_spacing_m": None, "duplicate_time_policy": "first",
        "wind_pairs": [],
        "netcdf": {"engine": "h5netcdf", "chunks": {}, "file_layout": "time_series", "surfex_fields": []},
        "fa": {"profile": None, "subdomain": "CI", "earth_radius_m": None,
               "field_metadata": {}, "expected_source": {},
               "backend": "epygram", "python_executable": None, "native_cubes": {},
               "max_points": 20_000_000, "timeout_seconds": 120.},
        "sources": {}, "time_alignment": "common",
    },
    "tracking": {
        "source": None,
        "method": "pressure_wind",
        "pressure_wind": {"search_half_width_km": 100., "refine_half_width_km": 50.,
                          "initial_guess": None},
        "fixed_box": {"center": {"latitude": None, "longitude": None}},
        "prescribed_track": {"file": None, "time_name": "time",
                             "latitude_name": "latitude", "longitude_name": "longitude"},
        "utrack": {"weights_file": None, "use_gpu": False, "batch_size": 16},
        "pressure_centroid": {
            "convergence": {"max_iterations": 15, "tolerance_m": 250.},
            "motion": {"max_iterations": 50, "solver": "aitken", "relaxation": .25,
                       "tolerance_m": 250.},
            "sampling": {"r80_max_distance_km": 250., "radial_step_km": 2.5,
                         "azimuth_step_deg": 5.},
        },
        "multifield_vortex": {
            "profile": "all_no_thick", "on_track_loss": "stop",
            "seed": {"latitude": None, "longitude": None, "time": None,
                     "motion_u_m_s": None, "motion_v_m_s": None},
            "mnh_gravity_m_s2": None,
            "numerics": {"analysis_step_km": 25., "refinement_km": 2.5,
                         "max_iterations": 20, "minimum_support": .8,
                         "minimum_samples": 16},
            "quality": {"minimum_parameters": 2, "pressure_rise_pa": 50.,
                        "vt850_min_m_s": 1.5, "max_separation_km": 425.,
                        "max_speed_m_s": 30.866666666666667,
                        "speed_check_interval_hours": 6.},
        },
    },
    "domain": {"width_km": None, "edge_policy": "pad_nan"},
    "variables": {},
    "polar": {
        "enabled": False, "shared_target": False, "variables": "extracted", "radial_step_m": None,
        "azimuth_step_deg": None, "azimuth_count": None, "interpolation_method": "bilinear",
        "missing_data_policy": "strict", "min_valid_weight_fraction": .5,
        "weight_zero_tolerance": 1e-14, "source_halo_points": 1, "ellipsoid": "WGS84",
        "max_points": 2_000_000, "plan_cache": {"entries": 8, "max_bytes": 128 * 1024**2},
        "chunks": {}, "profile": False,
    },
    "output": {
        "cartesian": {"horizontal_vectors": "earth_centered", "vertical_velocity": "interfaces"},
        "polar": {"vertical_velocity": "mass"},
        "directory": "./output", "export": {"enabled": True, "cartesian": True, "polar": True},
        "compression": {"level": 1, "coordinates": False}, "backend": "netcdf4",
        "netcdf_format": "NETCDF4", "unlimited_time": True, "overwrite": True, "max_workers": None,
        "synchronous_export": False,
        "zarr_chunk_size": {}, "zarr_shard_size": {},
        "institution": "LACy, Université de La Réunion, CNRS, Météo-France",
    },
    "execution": {"dask_scheduler": "threads", "dask_workers": None, "native_threads": 1,
                  "require_complete_tracking": False},
    "logging": {"level": "INFO"},
    "metadata": {"ocean_model": "", "wave_model": "", "extra": {}},
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
        text = path.read_text(encoding="utf-8")
        data = yaml.load(text, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return data


def _merge_checked(raw, defaults, prefix=""):
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
            continue
        if isinstance(defaults[key], dict) and defaults[key]:
            try:
                result[key] = _merge_checked(value, defaults[key], location)
            except ValueError as exc:
                errors.append(str(exc))
        else:
            result[key] = copy.deepcopy(value)
    if errors:
        raise ValueError("\n".join(errors))
    return result


def validate_wind_pressure_initial_guess(value):
    """Validate an optional geographic first-time pressure search."""
    if value is None:
        return None
    path = "tracking.pressure_wind.initial_guess"
    guess = _merge_checked(value, {"latitude": None, "longitude": None,
                                   "search_radius_km": None}, path)
    for name, limit in (("latitude", 90), ("longitude", 180)):
        coordinate = guess[name]
        if (isinstance(coordinate, bool) or not isinstance(coordinate, (int, float))
                or not math.isfinite(coordinate) or abs(coordinate) > limit):
            raise ValueError(f"{path}.{name} must be finite and in [-{limit}, {limit}]")
    _positive(guess["search_radius_km"], f"{path}.search_radius_km")
    return guess


def _positive(value, path, *, integer=False, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{path} must be a finite {'integer' if integer else 'number'}")
    if (integer and not isinstance(value, int)) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{path} must be {'nonnegative' if allow_zero else 'positive'}" +
                         (" integer" if integer else ""))


def _runtime_group(group):
    if group == "surface":
        raise ValueError("Use fields_2d for fields without a selectable vertical axis, not surface")
    return "surface" if group == "fields_2d" else group


def _requests(raw, path="variables", *, polar=False):
    if polar and raw == "extracted":
        return "extracted"
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a mapping" + (" or 'extracted'" if polar else ""))
    result = {}
    for group, spec in raw.items():
        if not isinstance(group, str) or not group.strip():
            raise ValueError(f"{path} requires nonempty group names")
        native_group = _runtime_group(group)
        spec = _merge_checked(spec, {"names": [], **({} if polar else {"levels": "stored"})},
                              f"{path}.{group}")
        names = spec["names"]
        if not isinstance(names, list) or not names or any(
            not isinstance(n, str) or not n.strip() for n in names
        ):
            raise ValueError(f"{path}.{group}.names must be a nonempty list of variable names")
        result[native_group] = {"variables": names}
        if polar:
            continue
        levels = spec["levels"]
        if isinstance(levels, str) and levels in {"stored", "physical"}:
            domain = "physical" if levels == "physical" else "stored"
            result[native_group].update(level_selection=domain, level_domain=domain)
        elif isinstance(levels, dict) and len(levels) == 1 and set(levels) <= {"indices", "values"}:
            strategy, values = next(iter(levels.items()))
            if not isinstance(values, list) or not values:
                raise ValueError(f"{path}.{group}.levels.{strategy} must be a nonempty list")
            for value in values:
                if strategy == "indices":
                    _positive(
                        value, f"{path}.{group}.levels.indices", integer=True, allow_zero=True
                    )
                else:
                    _finite_level(value, group)
            result[native_group].update(level_selection=strategy, **{f"level_{strategy}": values})
        else:
            raise ValueError(
                f"{path}.{group}.levels requires indices or values, or stored/physical"
            )
    return result


def _finite_level(value, group):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"variables.{group}.levels.values must contain finite numbers")


def validate_wind_pairs(pairs):
    """Validate explicit source-component declarations without discovering winds."""
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
            if not isinstance(pair[key], str) or not pair[key].strip():
                raise ValueError(f"{path}.{key} must be a nonempty string")
        if pair["reference_frame"] not in {"earth", "grid"}:
            raise ValueError(f"{path}.reference_frame must be earth or grid")
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
        if (not isinstance(rotation, dict) or "method" not in rotation
                or set(rotation) - {"method", "coordinate"}):
            raise ValueError(f"{path}.rotation requires method and optional coordinate")
        method = rotation["method"]
        if not isinstance(method, str) or method not in {
            "coordinate", "geolocation", "mesonh_projection"
        }:
            raise ValueError(
                f"{path}.rotation.method must be coordinate/geolocation/mesonh_projection"
            )
        if "coordinate" in rotation and (
            not isinstance(rotation["coordinate"], str) or not rotation["coordinate"].strip()
        ):
            raise ValueError(f"{path}.rotation.coordinate must be a nonempty string")
        if method == "coordinate" and "coordinate" not in rotation:
            raise ValueError(f"{path}.rotation.coordinate is required for method coordinate")


def validate_output_selections(horizontal, cartesian_vertical, polar_vertical):
    for path, value, choices in (
        ("output.cartesian.horizontal_winds", horizontal, {"native", "mass_earth"}),
        ("output.cartesian.vertical_velocity", cartesian_vertical, {"interfaces", "mass"}),
        ("output.polar.vertical_velocity", polar_vertical, {"interfaces", "mass"}),
    ):
        if not isinstance(value, str) or value not in choices:
            raise ValueError(f"{path} must be one of {sorted(choices)}")


def validate_fa_options(options, selected=False):
    """No field identity, unit or temporal meaning is guessed from a record name."""
    if options["backend"] != "epygram":
        raise ValueError("input.fa.backend must be epygram")
    executable = options["python_executable"]
    if executable is not None and (not isinstance(executable, str) or not executable.strip()):
        raise ValueError("input.fa.python_executable must be a nonempty interpreter path")
    if ((options["profile"] is not None and not isinstance(options["profile"], str))
            or options["profile"] not in {None, "arome_history", "surfex_history"}):
        raise ValueError("input.fa.profile must be arome_history or surfex_history")
    if selected and options["profile"] is None:
        raise ValueError("input.format fa requires input.fa.profile")
    if not isinstance(options["subdomain"], str) or options["subdomain"] not in {"CI", "C"}:
        raise ValueError("input.fa.subdomain must be CI or C (extension zones are excluded)")
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
        if (not isinstance(name, str) or not name.isascii() or not 1 <= len(name) <= 16):
            raise ValueError("FA identifiers must contain 1–16 ASCII characters")
        if not isinstance(definition, dict) or set(definition) - {
            "units", "kind", "temporal_kind", "allow_unscaled", "long_name", "standard_name"
        }:
            raise ValueError(f"input.fa.field_metadata.{name}: invalid metadata keys")
        if not isinstance(definition.get("units"), str) or not definition["units"].strip():
            raise ValueError(f"{name}: explicit source units are required")
        if (not isinstance(definition.get("kind"), str)
                or definition["kind"] not in {"continuous", "categorical"}):
            raise ValueError(f"{name}: kind must be continuous or categorical")
        if definition.get("temporal_kind") != "instantaneous":
            raise ValueError(f"{name}: only explicit instantaneous FA fields are supported; "
                             "no accumulation interval is inferred from the file header")
        if type(definition.get("allow_unscaled", False)) is not bool:
            raise ValueError(f"{name}: allow_unscaled must be a boolean")
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
        if (not isinstance(cube["vertical_position"], str)
                or cube["vertical_position"] not in {"mass", "interface"}):
            raise ValueError(f"native_cubes.{name}.vertical_position must be mass or interface")
        if cube["sampling"] != "center":
            raise ValueError(f"native_cubes.{name}: only collocated center sampling is admitted")
        if (cube.get("vector_basis") is not None and (
            not isinstance(cube["vector_basis"], str)
            or cube["vector_basis"] not in {"earth", "grid"}
        )):
            raise ValueError(f"native_cubes.{name}.vector_basis must be earth or grid")
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


def source_document(parent, name):
    """Resolve one source using ordinary schema/presets, without nesting runs.

    Secondary sources receive a coordinate-only loader request. Its internal
    fixed-box placeholder is never executed: the coupled runner supplies the
    geographical track from tracking.source explicitly.
    """
    source = parent["input"]["sources"][name]
    document = {key: copy.deepcopy(value) for key, value in parent.items()
                if key not in {"model", "input", "variables", "polar"}}
    document.update(model=source["model"], input=copy.deepcopy(source["input"]),
                    variables=copy.deepcopy(source["variables"]),
                    polar=copy.deepcopy(source["polar"]))
    if name != parent["tracking"]["source"]:
        document["tracking"] = {"method": "fixed_box", "fixed_box": {
            "center": {"latitude": 0., "longitude": 0.}}}
    else:
        document["tracking"]["source"] = None
    return document


def _resolve_sources(raw, conf, base):
    sources = conf["input"]["sources"]
    if not isinstance(sources, dict):
        raise ValueError("input.sources must be a mapping of named sources")
    if not sources:
        if conf["tracking"]["source"] is not None:
            raise ValueError("tracking.source requires input.sources")
        return
    if set(raw.get("input", {})) - {"sources", "time_alignment"}:
        raise ValueError("With input.sources, input settings belong inside each source.input")
    if conf["variables"] or conf["polar"]["variables"] != "extracted":
        raise ValueError("Coupled variables and polar variable selection belong to each source")
    if not isinstance(conf["tracking"]["source"], str) or conf["tracking"]["source"] not in sources:
        raise ValueError("tracking.source must name one of input.sources")
    for name, spec in list(sources.items()):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
            raise ValueError("Source IDs must start with a letter and contain letters/digits/_/-")
        checked = _merge_checked(spec, {"model": conf["model"], "input": {}, "variables": {},
                                        "polar": {}}, f"input.sources.{name}")
        if not isinstance(checked["input"], dict):
            raise ValueError(f"input.sources.{name}.input must be a mapping")
        misplaced = set(checked["input"]) & {"sources", "time_alignment"}
        if misplaced:
            raise ValueError(f"input.sources.{name}.input: {sorted(misplaced)} belong to the parent")
        checked["polar"] = _merge_checked(checked["polar"], conf["polar"],
                                           f"input.sources.{name}.polar")
        if checked["polar"]["shared_target"] != conf["polar"]["shared_target"]:
            raise ValueError("polar.shared_target is a coupled-run setting; "
                             "source declarations must agree with the top-level value")
        sources[name] = checked
    for name in sources:
        child, _, _ = resolve_schema(source_document(conf, name), base_dir=base)
        sources[name] = {key: child[key] for key in ("model", "input", "variables", "polar")}
        sources[name]["input"] = {key: value for key, value in child["input"].items()
                                  if key not in {"sources", "time_alignment"}}
    if sources[conf["tracking"]["source"]]["model"] != conf["model"]:
        raise ValueError("model must match input.sources[tracking.source].model")


def resolve_schema(raw, *, base_dir=None):
    if not isinstance(raw, dict) or type(raw.get("schema_version")) is not str or raw["schema_version"] != "2.1":
        raise ValueError(
            'Expected schema_version: "2.1" (a quoted YAML string).'
        )
    conf = _merge_checked(raw, DEFAULTS)
    enum_paths = (
        "model", "tracking.method", "input.format", "input.duplicate_time_policy",
        "input.time_alignment",
        "input.netcdf.engine", "input.netcdf.file_layout", "domain.edge_policy",
        "polar.interpolation_method", "polar.missing_data_policy", "polar.ellipsoid",
        "output.backend", "output.netcdf_format", "logging.level",
        "tracking.pressure_centroid.motion.solver",
        "tracking.multifield_vortex.profile", "tracking.multifield_vortex.on_track_loss",
    )
    for path in enum_paths:
        value = conf
        for part in path.split("."):
            value = value[part]
        if not isinstance(value, str) and not (
            path == "input.format" and value is None
        ):
            raise ValueError(f"{path} must be a string")
    if "model" not in raw or conf["model"] not in {"arome", "mesonh", "nemo", "croco"}:
        raise ValueError("model must be 'arome', 'mesonh', 'nemo' or 'croco'")
    base = Path(base_dir or Path.cwd()).resolve()
    inp, trk, pol, out = (conf[n] for n in ("input", "tracking", "polar", "output"))
    if conf["model"] in {"nemo", "croco"}:
        if trk["method"] not in {"fixed_box", "prescribed_track"}:
            raise ValueError(f"{conf['model'].upper()} reference sources require fixed_box or prescribed_track")
        if inp["format"] not in {None, "netcdf"}:
            raise ValueError(f"{conf['model'].upper()} supports only native NetCDF inputs")
    if not inp["sources"] and bool(inp["pattern"]) == bool(inp["files"]):
        raise ValueError("input requires exactly one of pattern or files")
    for key in ("directory",):
        if not isinstance(inp[key], str) or not inp[key]:
            raise ValueError(f"input.{key} must be a nonempty path")
    if inp["pattern"] is not None and (not isinstance(inp["pattern"], str) or
                                      Path(inp["pattern"]).is_absolute()):
        raise ValueError("input.pattern must be a relative glob or filename")
    for key in ("exclude", "files"):
        value = inp[key]
        if key == "files" and value is None:
            continue
        if (not isinstance(value, list) or (key == "files" and not value)
                or any(not isinstance(v, str) or not v.strip() for v in value)):
            raise ValueError(f"input.{key} must be a list of paths/patterns")
    if inp["format"] not in {None, "grib", "netcdf", "fa"}:
        raise ValueError("input.format must be grib, netcdf or fa")
    if inp["time_alignment"] not in {"common", "strict", "preceding_hour"}:
        raise ValueError("input.time_alignment must be common, strict or preceding_hour")
    if inp["time_alignment"] == "preceding_hour" and not inp["sources"]:
        raise ValueError("input.time_alignment: preceding_hour requires named NetCDF sources")
    validate_fa_options(inp["fa"], inp["format"] == "fa")
    if inp["format"] == "fa" and conf["model"] != "arome":
        raise ValueError("Current FA profiles require model: arome; declare the actual "
                         "AROME producer explicitly for each FA source")
    if inp["format"] == "fa" and trk["method"] not in {"fixed_box", "prescribed_track"}:
        raise ValueError("FA tracking requires fixed_box/prescribed_track, or a separate "
                         "GRIB/NetCDF tracking source")
    if inp["duplicate_time_policy"] not in {"first", "last"}:
        raise ValueError("input.duplicate_time_policy must be first or last")
    validate_wind_pairs(inp["wind_pairs"])
    for pair in inp["wind_pairs"]:
        _runtime_group(pair["group"])
    horizontal = out["cartesian"]["horizontal_vectors"]
    if not isinstance(horizontal, str) or horizontal not in {"native", "earth_centered"}:
        raise ValueError("output.cartesian.horizontal_vectors must be native or earth_centered")
    validate_output_selections("native" if horizontal == "native" else "mass_earth",
                               out["cartesian"]["vertical_velocity"],
                               out["polar"]["vertical_velocity"])
    if inp["grid_spacing_m"] is not None:
        _positive(inp["grid_spacing_m"], "input.grid_spacing_m")
    methods = {"pressure_wind", "pressure_centroid", "multifield_vortex", "fixed_box",
               "prescribed_track", "utrack"}
    if trk["method"] not in methods:
        raise ValueError(f"tracking.method must be one of {sorted(methods)}")
    for key, value in trk["pressure_wind"].items():
        if key == "initial_guess":
            trk["pressure_wind"][key] = validate_wind_pressure_initial_guess(value)
        else:
            _positive(value, f"tracking.pressure_wind.{key}")
    if trk["method"] == "fixed_box":
        center = trk["fixed_box"]["center"]
        for name, limit in (("latitude", 90), ("longitude", 180)):
            value = center[name]
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or abs(value) > limit):
                raise ValueError(
                    f"tracking.fixed_box.center.{name} must be in [-{limit}, {limit}] degrees"
                )
    if trk["method"] == "prescribed_track" and not trk["prescribed_track"]["file"]:
        raise ValueError("tracking.prescribed_track.file is required")
    if trk["method"] == "utrack" and not trk["utrack"]["weights_file"]:
        raise ValueError("tracking.utrack.weights_file is required")
    if trk["method"] == "multifield_vortex":
        mf = trk["multifield_vortex"]
        if mf["profile"] != "all_no_thick" or mf["on_track_loss"] not in {"stop", "error"}:
            raise ValueError(
                "multifield_vortex requires profile all_no_thick and on_track_loss stop/error")
        for name in ("latitude", "longitude", "motion_u_m_s", "motion_v_m_s"):
            value = mf["seed"][name]
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)):
                raise ValueError(
                    f"tracking.multifield_vortex.seed.{name} must be explicitly supplied")
        if not 0 < abs(mf["seed"]["latitude"]) < 90 or abs(mf["seed"]["longitude"]) > 180:
            raise ValueError("multifield_vortex seed needs a non-equatorial/nonpolar latitude "
                             "and longitude in [-180,180]")
        if mf["seed"]["time"] is not None and not isinstance(mf["seed"]["time"], str):
            raise ValueError("multifield_vortex.seed.time must be an ISO timestamp string or null")
        if mf["mnh_gravity_m_s2"] is not None:
            _positive(mf["mnh_gravity_m_s2"], "tracking.multifield_vortex.mnh_gravity_m_s2")
        if conf["model"] == "mesonh" and mf["mnh_gravity_m_s2"] is None:
            raise ValueError("multifield_vortex with MNH requires an explicit mnh_gravity_m_s2 "
                             "for the model's geometric-to-geopotential height convention")
        from frameit.tracking.multifield_vortex import VortexOptions

        VortexOptions(**mf["numerics"], **mf["quality"])
    _positive(trk["utrack"]["batch_size"], "tracking.utrack.batch_size", integer=True)
    pc = trk["pressure_centroid"]
    for section in ("convergence", "motion", "sampling"):
        for name, value in pc[section].items():
            if name != "solver":
                _positive(value, f"tracking.pressure_centroid.{section}.{name}",
                          integer=name == "max_iterations")
    if pc["motion"]["solver"] not in {"aitken", "fixed"} or pc["motion"]["relaxation"] > 1:
        raise ValueError("Invalid tracking.pressure_centroid.motion solver or relaxation")
    if pc["sampling"]["azimuth_step_deg"] >= 180:
        raise ValueError("tracking.pressure_centroid.sampling.azimuth_step_deg must be below 180")
    size = conf["domain"]["width_km"]
    if size is not None:
        if not isinstance(size, dict) or set(size) != {"x", "y"}:
            raise ValueError("domain.width_km requires x and y full widths")
        for name, value in size.items():
            _positive(value, f"domain.width_km.{name}")
    if conf["domain"]["edge_policy"] != "pad_nan":
        raise ValueError("domain.edge_policy currently supports pad_nan only")
    if pol["enabled"] and size is None:
        raise ValueError("polar.enabled requires domain.width_km")
    if pol["azimuth_count"] is not None and pol["azimuth_step_deg"] is not None:
        raise ValueError("polar.azimuth_count and polar.azimuth_step_deg are mutually exclusive")
    for name in ("radial_step_m", "azimuth_step_deg", "azimuth_count", "max_points"):
        if pol[name] is not None:
            _positive(pol[name], f"polar.{name}", integer=name in {"azimuth_count", "max_points"})
    if pol["azimuth_count"] is not None and pol["azimuth_count"] < 3:
        raise ValueError("polar.azimuth_count must be at least 3")
    if pol["azimuth_step_deg"] is not None and pol["azimuth_step_deg"] > 120:
        raise ValueError("polar.azimuth_step_deg must be at most 120")
    if pol["interpolation_method"] not in {"bilinear", "nearest_s2d"}:
        raise ValueError("polar.interpolation_method must be bilinear or nearest_s2d")
    if pol["missing_data_policy"] not in {"strict", "renormalize"}:
        raise ValueError("polar.missing_data_policy must be strict or renormalize")
    for key in ("min_valid_weight_fraction", "weight_zero_tolerance"):
        _positive(pol[key], f"polar.{key}", allow_zero=True)
        if pol[key] > 1:
            raise ValueError(f"polar.{key} must not exceed 1")
    if pol["weight_zero_tolerance"] >= 1e-6:
        raise ValueError("polar.weight_zero_tolerance must be less than 1e-6")
    _positive(pol["source_halo_points"], "polar.source_halo_points", integer=True)
    for name, value in pol["plan_cache"].items():
        _positive(value, f"polar.plan_cache.{name}", integer=True, allow_zero=True)
    for path, chunks in (
        ("input.netcdf.chunks", inp["netcdf"]["chunks"]), ("polar.chunks", pol["chunks"])
    ):
        if not isinstance(chunks, dict):
            raise ValueError(f"{path} must be a mapping")
        for name, value in chunks.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"{path} requires nonempty dimension names")
            if value != -1:
                _positive(value, f"{path}.{name}", integer=True)
    for path, value in (("polar.enabled", pol["enabled"]),
                        ("polar.shared_target", pol["shared_target"]),
                        ("polar.profile", pol["profile"]),
                        ("tracking.utrack.use_gpu", trk["utrack"]["use_gpu"]),
                        ("output.unlimited_time", out["unlimited_time"]),
                        ("output.overwrite", out["overwrite"]),
                        ("output.synchronous_export", out["synchronous_export"]),
                        ("execution.require_complete_tracking",
                         conf["execution"]["require_complete_tracking"]),
                        ("output.compression.coordinates", out["compression"]["coordinates"]),
                        *((f"output.export.{k}", v) for k, v in out["export"].items())):
        if not isinstance(value, bool):
            raise ValueError(f"{path} must be a YAML boolean")
    _positive(
        out["compression"]["level"], "output.compression.level", integer=True, allow_zero=True
    )
    if out["compression"]["level"] > 9:
        raise ValueError("output.compression.level must be in [0, 9]")
    if out["max_workers"] is not None:
        _positive(out["max_workers"], "output.max_workers", integer=True)
    execution = conf["execution"]
    if execution["dask_scheduler"] not in {"threads", "synchronous"}:
        raise ValueError("execution.dask_scheduler must be threads or synchronous")
    if execution["dask_workers"] is not None:
        _positive(execution["dask_workers"], "execution.dask_workers", integer=True)
    _positive(execution["native_threads"], "execution.native_threads", integer=True)
    if out["backend"] not in {"netcdf4", "h5netcdf", "zarr"}:
        raise ValueError("output.backend must be netcdf4, h5netcdf or zarr")
    if out["netcdf_format"] != "NETCDF4":
        raise ValueError("output.netcdf_format supports only NETCDF4")
    from frameit.io.zarr_export import validate_zarr_sizes

    validate_zarr_sizes(out["zarr_chunk_size"], out["zarr_shard_size"])
    if inp["netcdf"]["engine"] not in {"h5netcdf", "netcdf4", "scipy"}:
        raise ValueError("Unsupported input.netcdf.engine")
    if inp["netcdf"]["file_layout"] not in {"time_series", "variables"}:
        raise ValueError("input.netcdf.file_layout must be time_series or variables")
    from frameit.io.surfex_utils import validate_surfex_fields

    validate_surfex_fields(inp["netcdf"]["surfex_fields"], conf["model"], inp["format"],
                           inp["netcdf"]["file_layout"])
    if conf["logging"]["level"] not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ValueError("logging.level must be DEBUG, INFO, WARNING, or ERROR")
    if not isinstance(conf["metadata"]["extra"], dict):
        raise ValueError("metadata.extra must be a mapping")
    for path, value in (
        ("run.description", conf["run"]["description"]),
        ("output.institution", out["institution"]),
        ("metadata.ocean_model", conf["metadata"]["ocean_model"]),
        ("metadata.wave_model", conf["metadata"]["wave_model"]),
        *((f"tracking.prescribed_track.{key}", trk["prescribed_track"][key])
          for key in ("time_name", "latitude_name", "longitude_name")),
    ):
        if not isinstance(value, str):
            raise ValueError(f"{path} must be a string")
    for section, key in (("prescribed_track", "file"), ("utrack", "weights_file")):
        if trk[section][key] is not None and not isinstance(trk[section][key], str):
            raise ValueError(f"tracking.{section}.{key} must be a path string")
    for section, key in (("run", "name"), ("output", "directory")):
        if not isinstance(conf[section][key], str) or not conf[section][key]:
            raise ValueError(f"{section}.{key} must be a nonempty string")
    name = conf["run"]["name"]
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError("run.name must be an analysis identifier without path separators")
    user = _requests(conf["variables"])
    if inp["format"] == "fa":
        cubes = inp["fa"]["native_cubes"]
        if not cubes and set(user) - {"surface"}:
            raise ValueError("FA 2-D records must be selected in variables.fields_2d")
        levels = conf["variables"].get("fields_2d", {}).get("levels", "stored")
        if levels != "stored":
            raise ValueError("FA layer/patch selection uses explicit native record names; "
                             "variables.fields_2d.levels cannot select a vertical axis")
        for group, spec in user.items():
            if group not in {"surface", "level", "level_w"}:
                raise ValueError("FA native groups are fields_2d, level and level_w")
            if spec.get("level_domain") == "physical":
                raise ValueError("FA physical-coordinate selection is gated; select stored indices")
            for variable in spec["variables"]:
                if variable == "wind_speed":
                    continue
                cube = cubes.get(variable)
                expected = ("surface" if cube is None else
                            "level" if cube["vertical_position"] == "mass" else "level_w")
                if expected != group:
                    public = "fields_2d" if expected == "surface" else expected
                    raise ValueError(f"FA variable {variable}: select in variables.{public}")
    polar = _requests(pol["variables"], "polar.variables", polar=True)
    if polar == "extracted":
        polar = {g: {"variables": list(s["variables"])} for g, s in user.items()}
    for group, spec in polar.items():
        if group not in user or not set(spec["variables"]) <= set(user[group]["variables"]):
            raise ValueError(f"polar.variables.{group} must be a subset of extracted variables")
    if pol["enabled"] and not polar and not inp["sources"]:
        raise ValueError("polar.enabled requires selected polar variables")
    for section, key in (("input", "directory"), ("output", "directory")):
        conf[section][key] = str((base / conf[section][key]).resolve())
    if inp["fa"]["python_executable"] is not None:
        # Resolving a venv's python symlink would silently select the base
        # interpreter and lose that environment's optional native dependencies.
        inp["fa"]["python_executable"] = os.path.abspath(base / inp["fa"]["python_executable"])
    if inp["files"]:
        inp["files"] = [str((base / p).resolve()) for p in inp["files"]]
    for section, key in (("prescribed_track", "file"), ("utrack", "weights_file")):
        if trk[section][key]:
            trk[section][key] = str((base / trk[section][key]).resolve())
    _resolve_sources(raw, conf, base)
    if inp["sources"]:
        conf["input"] = {key: inp[key] for key in ("sources", "time_alignment")}
    return conf, user, polar


def to_runtime(raw, *, base_dir=None):
    c, user, polar = resolve_schema(raw, base_dir=base_dir)
    inp = {**DEFAULTS["input"], **c["input"]}
    trk, pol = c["tracking"], c["polar"]
    pc = trk["pressure_centroid"]
    size = c["domain"]["width_km"] or {"x": 0, "y": 0}
    origins = setting_sources(raw, c)
    for name, source in inp["sources"].items():
        for path, origin in setting_sources(raw.get("polar", {}), source["polar"]).items():
            key = f"input.sources.{name}.polar.{path}"
            if origins[key] == "default":
                origins[key] = origin
    return {
        "schema_version": "2.1", "yaml_config": c, "schema_sources": origins,
        "simulation_name": c["run"]["name"],
        "comment": c["run"]["description"],
        "atm_model": {"arome": "AROME", "mesonh": "MNH", "nemo": "NEMO", "croco": "CROCO"}[c["model"]],
        "ocean_model": c["metadata"]["ocean_model"], "wave_model": c["metadata"]["wave_model"],
        "resolution": inp["grid_spacing_m"] or 0, "infer_grid_geometry": True,
        "file_name_prefix": "", "file_name": "", "file_name_suffix": "",
        "file_type": "coupled" if inp["sources"] else inp["format"] or "",
        "input_pattern": inp["pattern"],
        "input_sources": inp["sources"], "time_alignment": inp["time_alignment"],
        "tracking_source": trk["source"], "fa_options": inp["fa"],
        "input_files": inp["files"], "input_exclude": inp["exclude"],
        "simulation_output_dir": inp["directory"], "frameit_output_dir": c["output"]["directory"],
        "duplicate_time_policy": inp["duplicate_time_policy"],
        "netcdf_engine": inp["netcdf"]["engine"],
        "netcdf_chunks": inp["netcdf"]["chunks"],
        "netcdf_file_layout": inp["netcdf"]["file_layout"],
        "netcdf_surfex_fields": inp["netcdf"]["surfex_fields"],
        "wind_reference_frame": None,
        "wind_pairs": [{**pair, "group": _runtime_group(pair["group"])}
                       for pair in inp["wind_pairs"]],
        "cartesian_horizontal_winds": {"native": "native", "earth_centered": "mass_earth"}[
            c["output"]["cartesian"]["horizontal_vectors"]],
        "cartesian_vertical_velocity": c["output"]["cartesian"]["vertical_velocity"],
        "polar_vertical_velocity": c["output"]["polar"]["vertical_velocity"],
        "tracking_method": "wind_pressure" if trk["method"] == "pressure_wind" else trk["method"], "fix_subdomain_center": [
            trk["fixed_box"]["center"]["latitude"], trk["fixed_box"]["center"]["longitude"]]
            if trk["method"] == "fixed_box" else None,
        "wind_pressure_search_half_width_km": trk["pressure_wind"]["search_half_width_km"],
        "wind_pressure_refine_half_width_km": trk["pressure_wind"]["refine_half_width_km"],
        "wind_pressure_initial_guess": trk["pressure_wind"]["initial_guess"],
        "prescribed_track_file": trk["prescribed_track"]["file"] or "",
        "prescribed_track_time_name": trk["prescribed_track"]["time_name"],
        "prescribed_track_lat_name": trk["prescribed_track"]["latitude_name"],
        "prescribed_track_lon_name": trk["prescribed_track"]["longitude_name"],
        "utrack_weights_file": trk["utrack"]["weights_file"],
        "utrack_use_gpu": trk["utrack"]["use_gpu"],
        "utrack_batch_size": trk["utrack"]["batch_size"],
        "pressure_centroid_max_iterations": pc["convergence"]["max_iterations"],
        "pressure_centroid_tolerance_m": pc["convergence"]["tolerance_m"],
        "pressure_centroid_max_motion_iterations": pc["motion"]["max_iterations"],
        "pressure_centroid_motion_solver": pc["motion"]["solver"],
        "pressure_centroid_motion_relaxation": pc["motion"]["relaxation"],
        "pressure_centroid_motion_tolerance_m": pc["motion"]["tolerance_m"],
        "pressure_centroid_r80_max_km": pc["sampling"]["r80_max_distance_km"],
        "pressure_centroid_dr_km": pc["sampling"]["radial_step_km"],
        "pressure_centroid_dtheta": pc["sampling"]["azimuth_step_deg"],
        "multifield_vortex": trk["multifield_vortex"],
        "requested_variables_user": user, "polar_variables": polar,
        "x_boxsize_km": size["x"], "y_boxsize_km": size["y"], "compute_polar_proj": pol["enabled"],
        "polar_shared_target": pol["shared_target"],
        "radial_resolution": pol["radial_step_m"] or 0,
        "azimuthal_resolution": pol["azimuth_step_deg"],
        "polar_n_theta": pol["azimuth_count"], "polar_max_points": pol["max_points"],
        "polar_missing_data_policy": pol["missing_data_policy"],
        "polar_min_valid_weight_fraction": pol["min_valid_weight_fraction"],
        "polar_weight_zero_tolerance": pol["weight_zero_tolerance"],
        "polar_source_halo_points": pol["source_halo_points"], "polar_ellipsoid": pol["ellipsoid"],
        "polar_regrid_cache_size": pol["plan_cache"]["entries"],
        "polar_regrid_cache_max_bytes": pol["plan_cache"]["max_bytes"],
        "polar_output_chunks": pol["chunks"], "polar_profile": pol["profile"],
        "polar_interpolation_method": pol["interpolation_method"],
        "log_level": c["logging"]["level"],
        "DEBUG": c["logging"]["level"] == "DEBUG",
    }


def setting_sources(raw, resolved, prefix=""):
    sources = {}
    for key, value in resolved.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and value:
            child = raw.get(key, {})
            sources.update(setting_sources(child if isinstance(child, dict) else {}, value, path))
        else:
            sources[path] = "yaml" if key in raw else "default"
    return sources


def resolved_configuration(conf, options=None):
    """Reloadable public schema with inferred defaults and effective overrides."""
    result = copy.deepcopy(conf.yaml_config)
    if conf.input_sources:
        result["input"] = {key: result["input"][key] for key in ("sources", "time_alignment")}
    else:
        result["input"]["grid_spacing_m"] = conf.resolution or None
        result["input"]["format"] = conf.file_type or result["input"]["format"]
    if conf.compute_polar_proj and not conf.input_sources:
        result["polar"]["radial_step_m"] = conf.radial_resolution or None
    if options is not None:
        out = result["output"]
        out["export"] = {"enabled": options.export_netcdf, "cartesian": options.export_cart,
                         "polar": options.export_polar}
        out["compression"] = {"level": options.compress_level,
                              "coordinates": options.compress_coords}
        for key in ("overwrite", "unlimited_time", "max_workers", "institution",
                     "synchronous_export", "zarr_chunk_size", "zarr_shard_size"):
            out[key] = getattr(options, key)
        out["backend"] = options.engine
        out["netcdf_format"] = options.fmt
        result["execution"] = {
            key: getattr(options, key) for key in DEFAULTS["execution"]
        }
        result["logging"]["level"] = options.log_level or conf.log_level or "INFO"
    return result


def resolved_sources(conf, options=None):
    sources = dict(conf.schema_sources)
    if not conf.input_sources:
        sources["input.grid_spacing_m"] = conf.grid_geometry.get("effective_source", "unresolved")
        sources["input.format"] = (
            "inferred_from_content" if conf.yaml_config["input"]["format"] is None else "yaml"
        )
    if not conf.input_sources and conf.yaml_config["polar"]["radial_step_m"] is None:
        sources["polar.radial_step_m"] = "resolved_grid_spacing"
    if options is not None:
        from frameit.core.execution import ExecutionOptions

        baseline = ExecutionOptions.from_config(conf)
        for attribute, path in (
            ("export_netcdf", "output.export.enabled"), ("export_cart", "output.export.cartesian"),
            ("export_polar", "output.export.polar"), ("compress_level", "output.compression.level"),
            ("compress_coords", "output.compression.coordinates"),
            ("institution", "output.institution"),
            ("log_level", "logging.level"), ("engine", "output.backend"), ("fmt", "output.netcdf_format"),
            ("overwrite", "output.overwrite"), ("unlimited_time", "output.unlimited_time"),
            ("max_workers", "output.max_workers"),
            ("synchronous_export", "output.synchronous_export"),
            ("zarr_chunk_size", "output.zarr_chunk_size"),
            ("zarr_shard_size", "output.zarr_shard_size"),
            *((key, f"execution.{key}") for key in DEFAULTS["execution"]),
        ):
            if getattr(options, attribute) != getattr(baseline, attribute):
                sources[path] = "execution_override"
    return sources


def load_runtime(path):
    """Load strict YAML and add line locations to dotted-key diagnostics."""
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
