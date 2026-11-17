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

from frameit.core.reports import Diagnostic, PreflightError, exception_diagnostics

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

# Structural keys and choices are shared by validation, capabilities and the editor asset.
V3_KEYS = {
    "source": ("model", "format", "profile", "files", "exclude", "time", "variables",
               "field_metadata", "interpretation", "native_cubes", "fa", "reader",
                "wind_pairs", "transforms", "derived", "allow_initial_gaps"),
    "time": ("cycle", "start", "end", "values", "stride"),
    "variables": ("2d", "3d", "levels"),
    "vertical_group": ("names", "levels"),
    "levels": ("indices", "values", "domain", "units"),
    "field_metadata": ("units", "kind", "temporal_kind", "allow_unscaled",
                       "long_name", "standard_name"),
    "reader": ("engine", "chunks", "python_executable", "timeout_seconds", "max_points"),
    "fa": ("subdomain", "earth_radius_m", "expected_source"),
    "rotation": ("method", "coordinate", "BETA", "RPK", "LON0"),
    "wind_pair": ("u", "v", "basis", "rotation"),
    "transform": ("fields", "sampling", "basis", "units"),
    "derived": ("method", "inputs"),
    "region": ("center", "track", "tracker", "width_km", "sources_coupling_time_association"),
    "model_grid": ("fields", "processing"),
    "polar": ("fields", "processing", "radius_km", "radial_step_km", "azimuth_count",
              "shared_grid", "missing_data_policy", "min_valid_weight_fraction", "field_options"),
    "polar_processing": ("chunks", "max_target_points", "plan_cache", "source_halo_points",
                         "weight_zero_tolerance", "profile"),
    "field_options": ("interpolation", "missing_data_policy",
                       "min_valid_weight_fraction", "sampling", "units", "basis"),
    "writer": ("engine", "unlimited_time", "compression", "chunks", "shards"),
    "compression": ("level", "coordinates"),
    "resources": ("cpus", "scheduler", "compute_workers", "export_workers", "native_threads",
                  "synchronous_export"),
    "metadata": ("institution", "extra"),
}
V3_CHOICES = {
    "model": ("arome", "mesonh", "nemo", "croco"),
    "format": ("netcdf", "grib", "fa"),
    "profile": ("arome_history", "surfex_history"),
    "kind": ("continuous", "categorical"),
    "temporal_kind": ("instantaneous", "mean", "accumulated"),
    "interpretation": ("mesonh_surfex_sea",),
    "reader_engine": ("h5netcdf", "netcdf4", "scipy"),
    "subdomain": ("CI", "C"),
    "rotation": ("coordinate", "geolocation", "mesonh_projection"),
    "wind_basis": ("earth", "grid"),
    "sampling": ("native", "mass"),
    "transform_basis": ("native", "earth"),
    "derived": ("wind_speed", "radial_wind", "tangential_wind"),
    "association": ("exact", "common", "preceding_hour"),
    "tracker": tuple(TRACKER_DEFAULTS),
    "on_incomplete": ("error", "keep_prefix"),
    "solver": ("aitken", "fixed"),
    "interpolation": ("bilinear", "nearest"),
    "missing_data_policy": ("strict", "renormalize"),
    "output_format": ("netcdf", "zarr"),
    "writer_engine": ("netcdf4", "h5netcdf"),
    "scheduler": ("threads", "synchronous"),
    "log_level": ("DEBUG", "INFO", "WARNING", "ERROR"),
}
V3_LIMITS = {
    "latitude": 90, "longitude": 180, "compression_level": 9,
    "azimuth_count": 3, "weight_zero_tolerance": 1e-6,
}
COMPRESSION_DEFAULTS = {"level": 1, "coordinates": False}


def configuration_schema():
    """Build the v3 editor structure; input-dependent eligibility stays in preflight."""
    def ref(name):
        return {"$ref": f"#/$defs/{name}"}

    def choice(name):
        return ref("choices_" + name)

    def obj(properties, required=(), **extra):
        return {"type": "object", "properties": properties, "additionalProperties": False,
                **({"required": list(required)} if required else {}), **extra}

    def array(items, **extra):
        return {"type": "array", "items": items, "minItems": 1, "uniqueItems": True, **extra}

    def mapping(values, **extra):
        return {"type": "object", "additionalProperties": values, **extra}

    positive = {"type": "number", "exclusiveMinimum": 0}
    integer = {"type": "integer", "minimum": 1}
    nonnegative = {"type": "integer", "minimum": 0}
    boolean = {"type": "boolean"}
    number = {"type": "number"}
    text = ref("text")
    names = array(text)
    paths = {"anyOf": [text, array(text, uniqueItems=False)]}
    chunks = mapping(integer)
    processing_chunks = mapping({"anyOf": [integer, {"const": -1}]})
    center = obj({key: {"type": "number", "minimum": -V3_LIMITS[key], "maximum": V3_LIMITS[key]}
                  for key in ("latitude", "longitude")},
                 ("latitude", "longitude"))
    defs = {"text": {"type": "string", "pattern": r"\S"},
            **{"choices_" + name: {"enum": list(values)}
               for name, values in V3_CHOICES.items()}}
    defs["time"] = obj({
        **{key: text for key in ("cycle", "start", "end")},
        "values": names, "stride": integer})
    defs["levels"] = obj({
        "indices": {"anyOf": [array(nonnegative), obj({
            "start": nonnegative, "end": nonnegative, "step": integer}, ("start", "end"))]},
        "values": {"anyOf": [array(number), obj({
            "min": number, "max": number}, ("min", "max"))]},
        "domain": {"const": "physical"}, "units": text})
    defs["vertical_group"] = obj({"names": names, "levels": ref("levels")}, ("names",))
    groups = mapping(ref("vertical_group"), minProperties=1,
                     propertyNames={"pattern": "^[A-Za-z][A-Za-z0-9_-]*$"})
    defs["variables"] = obj({
        "2d": names, "3d": {"anyOf": [names, groups]}, "levels": ref("levels")},
        **{"not": {"required": ["3d", "levels"],
                   "properties": {"3d": {"type": "object"}}}})
    defs["field_metadata"] = obj({
        **{key: text for key in ("units", "long_name", "standard_name")},
        "kind": choice("kind"), "temporal_kind": choice("temporal_kind"),
        "allow_unscaled": boolean})
    defs["reader"] = obj({
        "engine": choice("reader_engine"), "chunks": processing_chunks,
        "python_executable": text, "timeout_seconds": positive, "max_points": integer})
    defs["fa"] = obj({
        "subdomain": choice("subdomain"), "earth_radius_m": positive,
        "expected_source": obj({
            "PROGRAM": text,
            **{key: nonnegative for key in ("VERSION", "BUG", "MASDEV", "BUGFIX")}})})
    defs["rotation"] = obj({
        "method": choice("rotation"), "coordinate": text,
        "BETA": number, "RPK": {"type": "number", "minimum": -1, "maximum": 1}, "LON0": number},
        ("method",))
    defs["wind_pair"] = obj({
        "u": text, "v": text, "basis": choice("wind_basis"), "rotation": ref("rotation")},
        ("u", "v", "basis"))
    defs["transform"] = obj({
        "fields": names, "sampling": choice("sampling"), "basis": choice("transform_basis"),
        "units": text}, ("fields",))
    defs["derived"] = obj({
        "method": choice("derived"), "inputs": obj({"u": text, "v": text}, ("u", "v"))},
        ("method", "inputs"))
    defs["source"] = obj({
        "model": choice("model"), "format": choice("format"), "profile": choice("profile"),
        "files": paths, "exclude": array(text, minItems=0, uniqueItems=False), "time": ref("time"),
        "variables": ref("variables"), "field_metadata": mapping(ref("field_metadata")),
        "interpretation": choice("interpretation"), "reader": ref("reader"), "fa": ref("fa"),
        "native_cubes": mapping(obj({
            "records": names, "vertical_position": {"enum": ["mass", "interface"]},
            "sampling": {"const": "center"}, "vector_basis": choice("wind_basis"),
            "component_scaling": {"const": "physical_velocity"}},
            ("records", "vertical_position", "sampling"))),
        "wind_pairs": array(ref("wind_pair"), minItems=0),
        "transforms": array(ref("transform"), minItems=0, uniqueItems=False),
        "derived": mapping(ref("derived")), "allow_initial_gaps": names},
        ("files",))
    trackers = []
    for method, defaults in TRACKER_DEFAULTS.items():
        properties = {"method": {"const": method}, "on_incomplete": choice("on_incomplete")}
        for key, value in defaults.items():
            if isinstance(value, dict):
                properties[key] = obj({
                    name: {**(choice("solver") if name == "solver" else
                              integer if isinstance(item, int) else
                              positive if isinstance(item, float) else text), "default": item}
                    for name, item in value.items()})
            else:
                properties[key] = {
                    **(boolean if isinstance(value, bool) else
                       integer if isinstance(value, int) else
                       positive if isinstance(value, float) else text), "default": value}
                if key == "profile":
                    properties[key]["const"] = value
        required = ["method"]
        if method != "multifield_vortex":
            properties["on_incomplete"] = {"const": "error"}
        if method == "pressure_wind":
            properties["initial_guess"] = obj({
                **center["properties"], "search_radius_km": positive},
                ("latitude", "longitude", "search_radius_km"))
        elif method == "utrack":
            properties["weights_file"] = text
            required.append("weights_file")
        elif method == "multifield_vortex":
            properties.update(
                seed=obj({**center["properties"], "time": text,
                          "motion_u_m_s": number, "motion_v_m_s": number},
                         ("latitude", "longitude", "motion_u_m_s", "motion_v_m_s")),
                mnh_gravity_m_s2=positive)
            required.append("seed")
        trackers.append(obj(properties, required))
    defs["region"] = obj({
        "center": center, "track": obj({"file": text}, ("file",)),
        "tracker": {"oneOf": trackers}, "width_km": obj({"x": positive, "y": positive}, ("x", "y")),
        "sources_coupling_time_association": choice("association")})
    fields = mapping(names, minProperties=1)
    defs["model_grid"] = obj({
        "fields": fields, "processing": obj({"chunks": processing_chunks})})
    defs["polar_processing"] = obj({
        "chunks": processing_chunks, "max_target_points": integer, "source_halo_points": integer,
        "weight_zero_tolerance": {
            "type": "number", "minimum": 0, "exclusiveMaximum": V3_LIMITS["weight_zero_tolerance"]},
        "plan_cache": obj({"entries": nonnegative, "max_bytes": nonnegative}), "profile": boolean})
    mask = {"missing_data_policy": choice("missing_data_policy"),
            "min_valid_weight_fraction": {**positive, "maximum": 1}}
    defs["field_options"] = obj({
        **mask, "interpolation": choice("interpolation"), "sampling": choice("sampling"),
        "units": text, "basis": choice("transform_basis")})
    defs["polar"] = obj({
        "fields": fields, "processing": ref("polar_processing"), **mask,
        "radius_km": positive, "radial_step_km": positive,
        "azimuth_count": {"type": "integer", "minimum": V3_LIMITS["azimuth_count"]},
        "shared_grid": {**boolean, "default": False},
        "field_options": mapping(mapping(ref("field_options")))}, ("radius_km",))
    defs["compression"] = obj({
        "level": {"type": "integer", "minimum": 0, "maximum": V3_LIMITS["compression_level"],
                  "default": COMPRESSION_DEFAULTS["level"]},
        "coordinates": {**boolean, "default": COMPRESSION_DEFAULTS["coordinates"]}})
    defs["writer"] = obj({
        "engine": choice("writer_engine"), "unlimited_time": boolean,
        "compression": ref("compression"), "chunks": chunks, "shards": chunks})
    defs["resources"] = obj({
        **{key: integer for key in ("cpus", "compute_workers", "export_workers", "native_threads")},
        "scheduler": choice("scheduler"), "synchronous_export": boolean})
    defs["metadata"] = obj({
        "institution": {"type": "string"},
        "extra": {"type": "object", "additionalProperties": True, "default": {}}})
    for name, keys in V3_KEYS.items():
        assert set(defs[name]["properties"]) == set(keys), name
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://meteofrance.github.io/frameit/schemas/config-v3.schema.json",
        "title": "FrameIt configuration v3",
        "description": (
            "Editor structure only. Use frameit inspect/validate for input-dependent selection, "
            "scientific applicability, dependencies and resource checks. "
            "Omit optional controls for defaults; null is allowed only in metadata.extra."),
        **obj({
            "schema_version": {"type": "integer", "const": DEFAULTS["schema_version"]},
            "run": obj({"name": text, "description": {"type": "string"}}),
            "sources": mapping(ref("source"), minProperties=1,
                               propertyNames={"pattern": "^[A-Za-z][A-Za-z0-9_-]*$"}),
            "region": ref("region"),
            "products": obj({
                "model_grid": {"anyOf": [{"const": True}, ref("model_grid")]},
                "polar": ref("polar"), "track": {"anyOf": [{"const": True}, obj({})]}},
                minProperties=1),
            "output": obj({
                "directory": text, "format": choice("output_format"), "overwrite": boolean,
                "writer": ref("writer")}),
            "resources": ref("resources"), "logging": obj({"level": choice("log_level")}),
            "metadata": ref("metadata")}, ("schema_version", "sources")),
        "$defs": defs,
    }


def capabilities():
    """Describe the current public structure and implemented paths, without native imports."""
    import importlib.util

    sources = {
        model: {
            "formats": list(V3_CHOICES["format"]) if model == "arome" else ["netcdf"],
            "inputs": ["declared paths", "unambiguous model/format metadata", "native coordinates",
                       "selected variables and source units"],
            "maturity": "implemented; input-profile and scientific applicability checks required",
            "limits": [],
        } for model in V3_CHOICES["model"]
    }
    sources["arome"]["limits"] = [
        "FA: explicit instantaneous gridpoint declarations/native cubes and producer evidence; "
        "spectral decoding and packed SURFEX reconstruction are gated.",
        "FA tracker support is not executable in v3; arbitrary GRIB/FA profiles are not promised."]
    sources["mesonh"]["limits"] = [
        "NetCDF only; mesonh_surfex_sea interpretation is explicit and requires FRAC_SEA; "
        "no inferred units, flux sign or temperature equivalence."]
    sources["nemo"]["limits"] = [
        "Regional native scalars/components; separate grids, depths, masks and sample clocks."]
    sources["croco"]["limits"] = [
        "History/Vtransform=2; native sigma axes and masks; no arbitrary restart support."]
    tracking = {
        method: {
            "maturity": ("experimental_native_grid_adaptation" if method == "multifield_vortex"
                         else "implemented; no new scientific validation claim"),
            "v3_execution": method != "utrack",
            "models": ["arome", "mesonh"], "dependencies": [],
            "inputs": ["selected pressure/wind metadata and Earth-relative wind evidence"],
            "limits": ["Selected metadata, values and geometry must pass preflight and execution; "
                       "FA tracking is gated."],
        } for method in V3_CHOICES["tracker"]
    }
    tracking["pressure_wind"]["inputs"] += ["MSLP and 10-m U/V"]
    tracking["pressure_centroid"]["inputs"] += [
        "at least two selected times", "MSLP, 10-m U/V and vertical U/V/height",
        "AROME isobaric support or Meso-NH native pressure/ASL brackets"]
    tracking["multifield_vortex"]["inputs"] += [
        "explicit seed/motion", "pressure-level or Meso-NH native multi-field support"]
    tracking["utrack"].update(
        models=["arome"],
        dependencies=["torch", "utrack"],
        inputs=["weights_file", "UTrack-compatible input fields"],
        limits=["Configuration and optional adapter exist, but v3 selected tracker binding "
                "is not yet executable. Dependency presence does not enable it."])
    for method, inputs in (
        ("fixed_box", ["geographic center"]),
        ("prescribed_track", ["track file with exact selected timestamps and geographic degrees"]),
    ):
        tracking[method] = {
            "maturity": "implemented", "v3_execution": True,
            "models": list(V3_CHOICES["model"]), "dependencies": [], "inputs": inputs,
            "limits": ["No nearest-time matching or inferred track."]}
    dependencies = {
        "netcdf": ["xarray", "netCDF4", "h5netcdf"],
        "grib": ["cfgrib", "eccodes"],
        "fa": ["epygram", "ctypesForFortran"],
        "zarr": ["zarr", "xarray"],
        "polar": ["xesmf", "ESMF"],
        "utrack": tracking["utrack"]["dependencies"],
    }
    return {
        "configuration_version": DEFAULTS["schema_version"],
        "sources": sources, "tracking": tracking,
        "products": {
            "model_grid": {"dependencies": [], "limits": [
                "Native fields by default; transformations and derived results are explicit."]},
            "polar": {"dependencies": dependencies["polar"],
                      "interpolation": list(V3_CHOICES["interpolation"]),
                      "maturity": "implemented point sampling",
                       "limits": ["No area-budget conservation guarantee; missing-data policy "
                                  "is explicit. "
                                  "Experimental comparison methods are not public v3 selectors.",
                                  "radial_wind/tangential_wind: experimental polar-only "
                                  "atmospheric "
                                  "binding, strict shared stencils; AROME GRIB/NetCDF and Meso-NH "
                                  "NetCDF only, no FA or ocean variants."]},
            "track": {"dependencies": [], "limits": ["Requires a declared center/track/tracker."]},
        },
        "derived": list(V3_CHOICES["derived"]), "dependencies": dependencies,
        "installed_modules": {name: importlib.util.find_spec(name) is not None
                              for name in sorted({name for names in dependencies.values()
                                                  for name in names})},
        "dependency_check": (
            "Module presence only in this interpreter; not scientific qualification "
            "or proof of backend initialization/helper-interpreter availability."),
        "editor_schema": "schemas/config-v3.schema.json",
    }


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate keys, including duplicates hidden in nested sections."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            location = {
                "file": getattr(self, "source_path", None),
                "line": key_node.start_mark.line + 1,
                "column": key_node.start_mark.column + 1,
            }
            if not isinstance(key, str):
                raise PreflightError([Diagnostic(
                    getattr(self, "node_paths", {}).get(id(key_node), "configuration"),
                    f"YAML keys must be strings (line {location['line']})", "string keys", key,
                    ["Use string keys from the configuration schema."], locations=[location])])
            if key in result:
                raise PreflightError([Diagnostic(
                    getattr(self, "node_paths", {}).get(id(key_node), "configuration"),
                    f"Duplicate key {key!r} at line {location['line']}",
                    "unique mapping keys", {"key": key},
                    [f"Keep one {key} entry in this mapping."], locations=[location])])
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def read_yaml(path):
    return _read_yaml(path)[0]


def _read_yaml(path):
    """Use one strict parse tree for values and authored marks."""
    path = Path(path)
    locations = {}
    loader = UniqueLoader(path.read_text(encoding="utf-8"))
    loader.node_paths = {}
    loader.source_path = str(path.absolute())
    try:
        node = loader.get_single_node()

        def visit(node, prefix="", ancestors=()):
            if node is None or id(node) in ancestors:
                return
            if isinstance(node, yaml.MappingNode):
                for key, value in node.value:
                    name = f"{prefix}.{key.value}" if prefix else key.value
                    loader.node_paths[id(key)] = name
                    locations[name] = {
                        "file": str(path.absolute()), "line": key.start_mark.line + 1,
                        "column": key.start_mark.column + 1,
                    }
                    visit(value, name, (*ancestors, id(node)))
            elif isinstance(node, yaml.SequenceNode):
                for index, value in enumerate(node.value):
                    name = f"{prefix}[{index}]"
                    locations[name] = {
                        "file": str(path.absolute()), "line": value.start_mark.line + 1,
                        "column": value.start_mark.column + 1,
                    }
                    visit(value, name, (*ancestors, id(node)))

        visit(node)
        data = loader.construct_document(node) if node is not None else None
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise PreflightError([Diagnostic(
            "configuration", f"Invalid YAML in {path}: {exc}", "valid YAML mapping syntax",
            {"problem": str(exc)}, ["Correct the YAML syntax at the reported location."],
            locations=[{"file": str(path.absolute()), "line": mark.line + 1,
                        "column": mark.column + 1}] if mark else [],
        )]) from exc
    finally:
        loader.dispose()
    if not isinstance(data, dict):
        raise PreflightError([Diagnostic(
            "configuration", f"{path}: expected a YAML mapping", "YAML mapping", data,
            ["Provide a mapping with schema_version: 3 and sources."],
            locations=[{"file": str(path.absolute()), "line": node.start_mark.line + 1,
                        "column": node.start_mark.column + 1}] if node else [],
        )])
    return data, locations


def _merge_checked(raw, defaults, prefix=""):
    """Merge fixed-key controls; dynamic mappings are checked by their owner."""
    if not isinstance(raw, dict):
        raise PreflightError([Diagnostic(
            prefix or "configuration", f"{prefix or 'configuration'} must be a mapping",
            "mapping", raw, [f"Provide a mapping for {prefix or 'configuration'}."])])
    result = copy.deepcopy(defaults)
    errors = []
    for key, value in raw.items():
        if not isinstance(key, str):
            errors.append(Diagnostic(
                prefix or "configuration", f"{prefix or 'configuration'} keys must be strings",
                "string keys", key, [f"Use string keys in {prefix or 'configuration'}."]))
            continue
        location = f"{prefix}.{key}" if prefix else key
        if key not in defaults:
            suggestion = difflib.get_close_matches(key, defaults, n=1)
            errors.append(Diagnostic(
                location, f"Unknown key {location}" +
                (f"; did you mean {suggestion[0]}?" if suggestion else ""),
                {"keys": sorted(defaults)}, key,
                [f"Remove {location} or use an accepted key: {', '.join(sorted(defaults))}."]))
        elif isinstance(defaults[key], dict) and defaults[key]:
            try:
                result[key] = _merge_checked(value, defaults[key], location)
            except ValueError as exc:
                errors.extend(exception_diagnostics(
                    exc, path=location, expected="mapping", observed=value,
                    repairs=[f"Provide a valid mapping for {location}."]))
        else:
            result[key] = copy.deepcopy(value)
    if errors:
        raise PreflightError(errors)
    return result


def _keys(raw, allowed, path, *, required=()):
    if not isinstance(raw, dict):
        raise PreflightError([Diagnostic(
            path, f"{path} must be a mapping", "mapping", raw,
            [f"Provide a mapping for {path}."])])
    for key in raw:
        if not isinstance(key, str) or key not in allowed:
            raise PreflightError([Diagnostic(
                str(key) if path == "configuration" else f"{path}.{key}",
                f"Unknown key {path}.{key}", sorted(allowed), key,
                [f"Remove {path}.{key}; accepted keys: {', '.join(sorted(allowed))}."])])
    missing = set(required) - raw.keys()
    if missing:
        prefix = "" if path == "configuration" else f"{path}."
        raise PreflightError([Diagnostic(
            f"{prefix}{key}", f"{path} requires {', '.join(sorted(missing))}",
            {"present": True}, {"present": False}, [f"Provide {prefix}{key}."])
            for key in sorted(missing)])
    return copy.deepcopy(raw)


def _reject_nulls(value, path=""):
    if path == "metadata.extra":
        if not isinstance(value, dict):
            raise PreflightError([Diagnostic(
                path, "metadata.extra must be a mapping", "mapping", value,
                ["Provide a mapping for metadata.extra."])])
        return
    if value is None:
        raise PreflightError([Diagnostic(
            path or "configuration", "cannot be null; omit the key for its default",
            "omit the key, or provide its declared value type", None,
            [f"Omit {path or 'configuration'} for its default, or provide a valid value."])])
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
        raise PreflightError([Diagnostic(
            path, "must be a nonempty string", "nonempty string", value,
            [f"Set {path} to a nonempty string."])])


def _choice(value, choices, path):
    if not isinstance(value, str) or value not in choices:
        raise PreflightError([Diagnostic(
            path, f"must be one of {', '.join(sorted(choices))}", sorted(choices), value,
            [f"Set {path} to one of: {', '.join(sorted(choices))}."])])


def _boolean(value, path):
    if type(value) is not bool:
        raise PreflightError([Diagnostic(
            path, "must be a YAML boolean", "YAML boolean", value,
            [f"Use true or false for {path}, without quotes."])])


def _finite(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PreflightError([Diagnostic(
            path, "must be a finite number", "finite number", value,
            [f"Set {path} to a finite number; missing data are not zero."])])


def _positive(value, path, *, integer=False, allow_zero=False):
    _finite(value, path)
    if (integer and not isinstance(value, int)) or value < 0 or (value == 0 and not allow_zero):
        expected = ("nonnegative" if allow_zero else "positive") + (
            " integer" if integer else " number")
        raise PreflightError([Diagnostic(
            path, f"must be {expected}", expected, value,
            [f"Set {path} to a {expected}."])])


def _names(value, path, *, empty=False):
    if not isinstance(value, list) or (not empty and not value):
        expected = f"{'nonempty ' if not empty else ''}list of names"
        raise PreflightError([Diagnostic(
            path, f"{path} must be a {expected}", expected, value,
            [f"Provide a {expected} for {path}."])])
    for name in value:
        _text(name, path)
    if len(set(value)) != len(value):
        raise ValueError(f"{path} contains duplicate names")
    return value


def _sizes(value, path, *, whole_axis=False):
    if not isinstance(value, dict):
        raise PreflightError([Diagnostic(
            path, f"{path} must be a dimension-size mapping", "dimension-size mapping", value,
            [f"Provide a dimension-size mapping for {path}."])])
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
        expected = f"path/glob or a {'nonempty ' if not empty else ''}list"
        raise PreflightError([Diagnostic(
            path, f"must be a {expected}", expected, value,
            [f"Set {path} to a path/glob string or a list of path/glob strings."])])
    return [_path(item, base, path, preserve_symlink=True) for item in value]


def _center(value, path):
    result = _keys(value, {"latitude", "longitude"}, path, required={"latitude", "longitude"})
    for name in ("latitude", "longitude"):
        limit = V3_LIMITS[name]
        _finite(result[name], f"{path}.{name}")
        if abs(result[name]) > limit:
            raise PreflightError([Diagnostic(
                f"{path}.{name}", f"{path}.{name} must be in [-{limit}, {limit}] degrees",
                {"min": -limit, "max": limit, "units": "degrees"}, result[name],
                [f"Set {path}.{name} within [-{limit}, {limit}] degrees."])])
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
    checked = _keys(rotation, V3_KEYS["rotation"],
                    path, required={"method"})
    method = checked["method"]
    _choice(method, V3_CHOICES["rotation"], f"{path}.method")
    if method == "coordinate" and "coordinate" not in checked:
        raise PreflightError([Diagnostic(
            f"{path}.coordinate", f"{path}.coordinate is required for method coordinate",
            {"present": True}, {"present": False}, [f"Provide {path}.coordinate."])])
    if "coordinate" in checked:
        _text(checked["coordinate"], f"{path}.coordinate")
        if strict and method != "coordinate":
            raise PreflightError([Diagnostic(
                f"{path}.coordinate", f"{path}.coordinate requires method coordinate",
                {"method": "coordinate"}, {"method": method, "value": checked["coordinate"]},
                [f"Omit {path}.coordinate unless method is coordinate."])])
    for name in ("BETA", "RPK", "LON0"):
        if name in checked:
            if method != "mesonh_projection":
                raise PreflightError([Diagnostic(
                    f"{path}.{name}", f"{path}.{name} requires method mesonh_projection",
                    {"method": "mesonh_projection"}, {"method": method, "value": checked[name]},
                    [f"Omit {path}.{name} unless method is mesonh_projection."])])
            _finite(checked[name], f"{path}.{name}")
            if name == "RPK" and abs(checked[name]) > 1:
                raise PreflightError([Diagnostic(
                    f"{path}.RPK", f"{path}.RPK must be in [-1, 1]",
                    {"min": -1, "max": 1}, checked[name], [f"Set {path}.RPK within [-1, 1]."])])


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
        _choice(options["profile"], V3_CHOICES["profile"], "input.fa.profile")
    if selected and options["profile"] is None:
        raise ValueError("input.format fa requires input.fa.profile")
    _choice(options["subdomain"], V3_CHOICES["subdomain"], "input.fa.subdomain")
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
        _choice(definition.get("kind"), V3_CHOICES["kind"], f"{name}.kind")
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
        raise PreflightError([Diagnostic(
            path, f"{path} must be an ISO timestamp with valid month/day/time ranges",
            "ISO timestamp with valid month/day/time ranges", value,
            [f"Use an ISO timestamp with valid month/day/time ranges for {path}."])])
    if zone and zone != "Z" and (int(zone[1:3]) > 23 or int(zone[4:]) > 59):
        raise PreflightError([Diagnostic(
            path, f"{path} has an invalid ISO timezone offset",
            "ISO timezone offset with hours <= 23 and minutes <= 59", value,
            [f"Use a valid ISO timezone offset in {path}."])])
    return (*numbers, Decimal(f"0.{fraction or '0'}")), zone


def _time(raw, path):
    time = _keys(raw, V3_KEYS["time"], path)
    if "values" in time and time.keys() & {"start", "end", "stride"}:
        raise PreflightError([Diagnostic(
            f"{path}.values", f"{path}.values is exclusive with start, end and stride",
            {"exclusive_with": ["start", "end", "stride"]}, time,
            [f"Use {path}.values alone, or use start/end/stride without values."])])
    for key in ("start", "end", "cycle"):
        if key in time:
            _timestamp(time[key], f"{path}.{key}")
    if "start" in time and "end" in time:
        start, start_zone = _timestamp(time["start"], f"{path}.start")
        end, end_zone = _timestamp(time["end"], f"{path}.end")
        if start_zone == end_zone and start > end:
            raise PreflightError([Diagnostic(
                f"{path}.start", f"{path}.start must not follow end",
                {"not_after": time["end"]}, time["start"],
                [f"Set {path}.start no later than {path}.end."])])
    if "values" in time:
        _names(time["values"], f"{path}.values")
        for value in time["values"]:
            _timestamp(value, f"{path}.values")
    if "stride" in time:
        _positive(time["stride"], f"{path}.stride", integer=True)
    return time


def _levels(raw, path):
    levels = _keys(raw, V3_KEYS["levels"], path)
    strategies = levels.keys() & {"indices", "values", "domain"}
    if len(strategies) > 1:
        raise PreflightError([Diagnostic(
            path, f"{path} requires exactly one of indices, values or domain",
            {"at_most_one": ["domain", "indices", "values"]}, levels,
            [f"Keep only one of {path}.indices, values or domain."])])
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
                raise PreflightError([Diagnostic(
                    f"{path}.{key}", f"{path}.{key} must be a nonempty list", "nonempty list",
                    value, [f"Provide a nonempty list for {path}.{key}."])])
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
                raise PreflightError([Diagnostic(
                    f"{path}.{key}.{low}", f"{path}.{key}.{low} must not exceed {high}",
                    {"max": interval[high]}, interval[low],
                    [f"Set {path}.{key}.{low} no greater than {path}.{key}.{high}."])])
    return levels


def _source(raw, name, base):
    path = f"sources.{name}"
    source = _keys(raw, V3_KEYS["source"], path, required={"files"})
    if "model" in source:
        _choice(source["model"], V3_CHOICES["model"], f"{path}.model")
    if "format" in source:
        _choice(source["format"], V3_CHOICES["format"], f"{path}.format")
    model, fmt = source.get("model"), source.get("format")
    fa_declared = (fmt == "fa" or bool(source.keys() & {"profile", "native_cubes", "fa"})
                   or (isinstance(source.get("reader"), dict) and bool(
                       source["reader"].keys() & {"python_executable", "timeout_seconds", "max_points"})))
    if model in {"nemo", "croco"} and fmt not in {None, "netcdf"}:
        raise PreflightError([Diagnostic(
            f"{path}.format", f"{path}.format: {model} supports only NetCDF",
            {"format": "netcdf"}, {"model": model, "format": fmt},
            [f"Select {path}.format: netcdf for {model}."])])
    source["files"] = _paths(source["files"], base, f"{path}.files")
    exclude = source.get("exclude", [])
    if not isinstance(exclude, list):
        raise ValueError(f"{path}.exclude must be a list of paths/globs")
    source["exclude"] = _paths(exclude, base, f"{path}.exclude", empty=True)
    if "time" in source:
        source["time"] = _time(source["time"], f"{path}.time")
    variables = _keys(source.get("variables", {}), V3_KEYS["variables"], f"{path}.variables")
    for category in ("2d", "3d"):
        if category in variables:
            value = variables[category]
            loc = f"{path}.variables.{category}"
            if category == "3d" and isinstance(value, dict):
                if not value:
                    raise ValueError(f"{loc} must be a nonempty group mapping")
                if "levels" in variables:
                    raise ValueError(f"{path}.variables.levels cannot accompany grouped 3d; "
                                     "put levels inside each group")
                for group, spec in value.items():
                    if not isinstance(group, str) or not re.fullmatch(
                            r"[A-Za-z][A-Za-z0-9_-]*", group):
                        raise ValueError(f"{loc}: vertical group must be a native axis identifier "
                                         "containing letters/digits/_/- and starting with a letter")
                    checked = _keys(spec, V3_KEYS["vertical_group"], f"{loc}.{group}",
                                    required={"names"})
                    _names(checked["names"], f"{loc}.{group}.names")
                    if "levels" in checked:
                        checked["levels"] = _levels(checked["levels"], f"{loc}.{group}.levels")
            else:
                _names(value, loc)
    names = [field for fields in _variable_fields(variables).values() for field in fields]
    if len(set(names)) != len(names):
        raise ValueError(f"{path}.variables contains duplicate field requests")
    if "levels" in variables:
        variables["levels"] = _levels(variables["levels"], f"{path}.variables.levels")
    source["variables"] = variables
    if "allow_initial_gaps" in source:
        _names(source["allow_initial_gaps"], f"{path}.allow_initial_gaps")
        if not set(source["allow_initial_gaps"]) <= set(names):
            raise ValueError(f"{path}.allow_initial_gaps must name selected source fields")
        if fa_declared:
            raise ValueError(f"{path}.allow_initial_gaps does not admit FA inputs")
    metadata = source.setdefault("field_metadata", {})
    if not isinstance(metadata, dict):
        raise PreflightError([Diagnostic(
            f"{path}.field_metadata", f"{path}.field_metadata must be a mapping",
            "mapping", metadata, [f"Provide a mapping for {path}.field_metadata."])])
    for field, declaration in metadata.items():
        _text(field, f"{path}.field_metadata")
        checked = _keys(declaration, V3_KEYS["field_metadata"], f"{path}.field_metadata.{field}")
        for key in ("units", "long_name", "standard_name"):
            if key in checked:
                _text(checked[key], f"{path}.field_metadata.{field}.{key}")
        if "kind" in checked:
            _choice(checked["kind"], V3_CHOICES["kind"],
                    f"{path}.field_metadata.{field}.kind")
        if "temporal_kind" in checked:
            _choice(checked["temporal_kind"], V3_CHOICES["temporal_kind"],
                    f"{path}.field_metadata.{field}.temporal_kind")
        if "allow_unscaled" in checked:
            if not fa_declared:
                loc = f"{path}.field_metadata.{field}.allow_unscaled"
                raise PreflightError([Diagnostic(
                    loc, f"{loc} is FA-only", {"format": "fa"},
                    {"format": fmt, "value": checked["allow_unscaled"]},
                    [f"Omit {loc} for non-FA inputs."])])
            _boolean(checked["allow_unscaled"], f"{path}.field_metadata.{field}.allow_unscaled")
    if "interpretation" in source:
        _choice(source["interpretation"], V3_CHOICES["interpretation"], f"{path}.interpretation")
        if model not in {None, "mesonh"} or fmt not in {None, "netcdf"}:
            raise PreflightError([Diagnostic(
                f"{path}.interpretation", f"{path}.interpretation requires Meso-NH NetCDF",
                {"model": "mesonh", "format": "netcdf"},
                {"model": model, "format": fmt, "interpretation": source["interpretation"]},
                [f"Omit {path}.interpretation unless the source is Meso-NH NetCDF."])])
    reader = _keys(source.get("reader", {}), V3_KEYS["reader"], f"{path}.reader")
    if "engine" in reader:
        if fmt not in {None, "netcdf"} or fa_declared:
            raise PreflightError([Diagnostic(
                f"{path}.reader.engine", f"{path}.reader.engine is NetCDF-only",
                {"format": "netcdf"}, {"format": fmt, "value": reader["engine"]},
                [f"Omit {path}.reader.engine for non-NetCDF inputs."])])
        _choice(reader["engine"], V3_CHOICES["reader_engine"], f"{path}.reader.engine")
    if "chunks" in reader:
        if fa_declared:
            raise PreflightError([Diagnostic(
                f"{path}.reader.chunks", f"{path}.reader.chunks is not supported by the FA decoder",
                "no FA reader chunks", {"format": fmt, "value": reader["chunks"]},
                [f"Omit {path}.reader.chunks for the FA decoder."])])
        _sizes(reader["chunks"], f"{path}.reader.chunks", whole_axis=True)
    for key in ("python_executable", "timeout_seconds", "max_points"):
        if key not in reader:
            continue
        if fmt not in {None, "fa"}:
            raise PreflightError([Diagnostic(
                f"{path}.reader.{key}", f"{path}.reader.{key} is FA-only",
                {"format": "fa"}, {"format": fmt, "value": reader[key]},
                [f"Omit {path}.reader.{key} for non-FA inputs."])])
        if key == "python_executable":
            reader[key] = _path(reader[key], base, f"{path}.reader.{key}", preserve_symlink=True)
        else:
            _positive(reader[key], f"{path}.reader.{key}", integer=key == "max_points")
    source["reader"] = reader
    if fa_declared and fmt in {None, "fa"}:
        if model not in {None, "arome"}:
            raise PreflightError([Diagnostic(
                f"{path}.model", f"{path}.model: current FA profiles require model: arome",
                "arome", model, [f"Use {path}.model: arome only for the admitted FA profiles."])])
        _keys(source.get("fa", {}), V3_KEYS["fa"], f"{path}.fa")
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
        selectors = (
            [(f"{path}.variables.3d.{group}.levels", spec.get("levels", {}))
             for group, spec in variables["3d"].items()]
            if isinstance(variables.get("3d"), dict)
            else [(f"{path}.variables.levels", variables.get("levels", {}))])
        for location, levels in selectors:
            if levels.get("domain") == "physical":
                raise PreflightError([Diagnostic(
                    location, f"{location}: FA physical-domain selection is gated",
                    {"selection": ["indices", "values"]}, levels,
                    [f"Do not use physical-domain selection in {location} for FA."])])
        cube_names = ([field for spec in variables["3d"].values() for field in spec["names"]]
                      if isinstance(variables.get("3d"), dict) else variables.get("3d", []))
        for field in cube_names:
            if field not in options["native_cubes"]:
                raise PreflightError([Diagnostic(
                    f"{path}.variables.3d.{field}",
                    f"{path}.variables.3d.{field} requires an explicit FA native cube",
                    {"native_cubes": [field]},
                    {"field": field, "native_cubes": sorted(options["native_cubes"])},
                    [f"Declare a native cube for {path}.variables.3d.{field}."])])
        if set(variables.get("2d", [])) & options["native_cubes"].keys():
            raise ValueError(f"{path}.variables: select FA native cubes under 3d")
        source["fa"] = {key: options[key] for key in ("subdomain", "expected_source")}
        if options["earth_radius_m"] is not None:
            source["fa"]["earth_radius_m"] = options["earth_radius_m"]
        for key in ("timeout_seconds", "max_points"):
            reader.setdefault(key, options[key])
    elif source.keys() & {"profile", "native_cubes", "fa"}:
        key = sorted(source.keys() & {"profile", "native_cubes", "fa"})[0]
        raise PreflightError([Diagnostic(
            f"{path}.{key}", f"{path}.{key} is FA-only; declare format: fa",
            {"format": "fa"}, {"format": fmt, "value": source[key]},
            [f"Omit {path}.{key} for non-FA inputs."])])
    pairs = source.setdefault("wind_pairs", [])
    if not isinstance(pairs, list):
        raise ValueError(f"{path}.wind_pairs must be a list")
    seen = set()
    for index, pair in enumerate(pairs):
        loc = f"{path}.wind_pairs[{index}]"
        _keys(pair, V3_KEYS["wind_pair"], loc, required={"u", "v", "basis"})
        for component in ("u", "v"):
            _text(pair[component], f"{loc}.{component}")
            if pair[component] in seen:
                raise ValueError(f"{loc}: duplicate wind component {pair[component]}")
            seen.add(pair[component])
        _choice(pair["basis"], V3_CHOICES["wind_basis"], f"{loc}.basis")
        if "rotation" in pair:
            if pair["basis"] != "grid":
                raise PreflightError([Diagnostic(
                    f"{loc}.rotation", f"{loc}.rotation requires basis: grid",
                    {"basis": "grid"}, {"basis": pair["basis"], "value": pair["rotation"]},
                    [f"Omit {loc}.rotation unless basis is grid."])])
            _rotation(pair["rotation"], f"{loc}.rotation")
    transforms = source.setdefault("transforms", [])
    if not isinstance(transforms, list):
        raise ValueError(f"{path}.transforms must be a list")
    for index, transform in enumerate(transforms):
        loc = f"{path}.transforms[{index}]"
        _keys(transform, V3_KEYS["transform"], loc, required={"fields"})
        _names(transform["fields"], f"{loc}.fields")
        if not transform.keys() & {"sampling", "basis", "units"}:
            raise PreflightError([Diagnostic(
                loc, f"{loc} needs sampling, basis or units",
                {"one_of": ["basis", "sampling", "units"]}, transform,
                [f"Declare sampling, basis or units in {loc}."])])
        for key, choices in (("sampling", V3_CHOICES["sampling"]),
                             ("basis", V3_CHOICES["transform_basis"])):
            if key in transform:
                _choice(transform[key], choices, f"{loc}.{key}")
        if "units" in transform:
            _text(transform["units"], f"{loc}.units")
    derived = source.setdefault("derived", {})
    if not isinstance(derived, dict):
        raise PreflightError([Diagnostic(
            f"{path}.derived", f"{path}.derived must be a mapping", "mapping", derived,
            [f"Provide a mapping for {path}.derived."])])
    for field, definition in derived.items():
        loc = f"{path}.derived.{field}"
        _text(field, f"{path}.derived")
        if field in names:
            raise ValueError(f"{loc} collides with an exported source field")
        _keys(definition, V3_KEYS["derived"], loc, required={"method", "inputs"})
        _choice(definition["method"], V3_CHOICES["derived"], f"{loc}.method")
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
    groups = source.get("variables", {}).get("3d", {})
    if isinstance(groups, dict):
        metadata = {}
        for reference, declaration in options["field_metadata"].items():
            name, group, _ = field_selection({"groups": groups}, reference)
            if group is not None:
                cube = options["native_cubes"].get(name, {})
                native_group = ("level_w" if cube.get("vertical_position") == "interface"
                                else "level" if cube.get("vertical_position") == "mass" else None)
                if group != native_group:
                    raise ValueError(f"field_metadata.{reference}: group does not match "
                                     "the explicit native cube")
            if name in metadata and metadata[name] != declaration:
                raise ValueError(f"field_metadata.{reference}: conflicting native declarations")
            metadata[name] = declaration
        options["field_metadata"] = metadata
    options.update({key: value for key, value in source.get("reader", {}).items()
                    if key in {"python_executable", "timeout_seconds", "max_points"}})
    return options


def _region(raw, base):
    path = "region"
    region = _keys(raw, V3_KEYS["region"], path)
    providers = region.keys() & {"center", "track", "tracker"}
    if len(providers) > 1:
        raise PreflightError([Diagnostic(
            path, "region.center, region.track and region.tracker are mutually exclusive",
            {"at_most_one": ["center", "track", "tracker"]}, region,
            ["Keep only one region.center, region.track or region.tracker."])])
    if "width_km" in region:
        if not providers:
            raise PreflightError([Diagnostic(
                "region.width_km", "region.width_km requires a center, track or tracker",
                {"requires_one_of": ["center", "track", "tracker"]}, region["width_km"],
                ["Declare a center, track or tracker for region.width_km."])])
        size = _keys(region["width_km"], {"x", "y"}, "region.width_km", required={"x", "y"})
        for key, value in size.items():
            _positive(value, f"region.width_km.{key}")
    if "center" in region:
        region["center"] = _center(region["center"], "region.center")
    if "track" in region:
        track = _keys(region["track"], {"file"}, "region.track", required={"file"})
        track["file"] = _path(track["file"], base, "region.track.file", preserve_symlink=True)
        region["track"] = track
    if region:
        region.setdefault("sources_coupling_time_association", "exact")
        _choice(region["sources_coupling_time_association"],
                V3_CHOICES["association"], "region.sources_coupling_time_association")
    if "tracker" not in region:
        return region
    tracker = region["tracker"]
    if not isinstance(tracker, dict) or "method" not in tracker:
        raise PreflightError([Diagnostic(
            "region.tracker.method" if isinstance(tracker, dict) else "region.tracker",
            "region.tracker.method is required",
            {"present": True} if isinstance(tracker, dict) else "mapping with method",
            {"present": False} if isinstance(tracker, dict) else tracker,
            ["Provide region.tracker.method in a tracker mapping."])])
    method = tracker["method"]
    _choice(method, V3_CHOICES["tracker"], "region.tracker.method")
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
    _choice(tracker["on_incomplete"], V3_CHOICES["on_incomplete"], "region.tracker.on_incomplete")
    if tracker["on_incomplete"] == "keep_prefix" and method != "multifield_vortex":
        raise PreflightError([Diagnostic(
            "region.tracker.on_incomplete",
            f"region.tracker.on_incomplete: {method} does not support keep_prefix",
            {"method": "multifield_vortex"},
            {"method": method, "on_incomplete": tracker["on_incomplete"]},
            ["Use region.tracker.on_incomplete: error for this method."])])
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
        _choice(tracker["motion"]["solver"], V3_CHOICES["solver"], "region.tracker.motion.solver")
        if tracker["motion"]["relaxation"] > 1:
            raise PreflightError([Diagnostic(
                "region.tracker.motion.relaxation",
                "region.tracker.motion.relaxation must not exceed 1", {"max": 1},
                tracker["motion"]["relaxation"],
                ["Set region.tracker.motion.relaxation no greater than 1."])])
        if tracker["sampling"]["azimuth_step_deg"] >= 180:
            raise PreflightError([Diagnostic(
                "region.tracker.sampling.azimuth_step_deg",
                "region.tracker.sampling.azimuth_step_deg must be below 180",
                {"exclusive_max": 180}, tracker["sampling"]["azimuth_step_deg"],
                ["Set region.tracker.sampling.azimuth_step_deg below 180."])])
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
            raise PreflightError([Diagnostic(
                "region.tracker.seed.latitude",
                "region.tracker.seed.latitude must be non-equatorial and nonpolar",
                {"absolute_min_exclusive": 0, "absolute_max_exclusive": 90}, seed["latitude"],
                ["Provide a non-equatorial, nonpolar region.tracker.seed.latitude."])])
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
        _choice(options["interpolation"], V3_CHOICES["interpolation"], f"{path}.interpolation")
    policy = options.get("missing_data_policy", "strict")
    _choice(policy, V3_CHOICES["missing_data_policy"], f"{path}.missing_data_policy")
    if policy == "renormalize":
        if "min_valid_weight_fraction" not in options:
            raise PreflightError([Diagnostic(
                f"{path}.min_valid_weight_fraction",
                f"{path}.min_valid_weight_fraction is required for renormalize",
                {"present": True}, {"present": False},
                [f"Declare {path}.min_valid_weight_fraction for renormalize."])])
        if options.get("interpolation") == "nearest":
            raise PreflightError([Diagnostic(
                f"{path}.interpolation",
                f"{path}: nearest interpolation cannot renormalize a partial stencil",
                {"interpolation_not": "nearest"},
                {"missing_data_policy": policy, "interpolation": options["interpolation"]},
                [f"Do not combine {path}.interpolation: nearest with renormalize."])])
    elif "min_valid_weight_fraction" in options:
        raise PreflightError([Diagnostic(
            f"{path}.min_valid_weight_fraction",
            f"{path}.min_valid_weight_fraction requires renormalize",
            {"missing_data_policy": "renormalize"},
            {"missing_data_policy": policy, "value": options["min_valid_weight_fraction"]},
            [f"Omit {path}.min_valid_weight_fraction for strict missing-data policy."])])
    if "min_valid_weight_fraction" in options:
        value = options["min_valid_weight_fraction"]
        _positive(value, f"{path}.min_valid_weight_fraction")
        if value > 1:
            raise PreflightError([Diagnostic(
                f"{path}.min_valid_weight_fraction",
                f"{path}.min_valid_weight_fraction must not exceed 1", {"max": 1}, value,
                [f"Set {path}.min_valid_weight_fraction no greater than 1."])])


def _products(raw, sources, region):
    products = _keys(raw, {"model_grid", "polar", "track"}, "products")
    if not products:
        raise PreflightError([Diagnostic(
            "products", "products must request at least one product; omit it for model_grid",
            "at least one product", products,
            ["Request at least one products entry, or omit products for model_grid."])])
    for product, spec in list(products.items()):
        path = f"products.{product}"
        if product in {"model_grid", "track"} and spec is True:
            spec = {}
        if product == "track":
            _keys(spec, set(), path)
            if not region.keys() & {"center", "track", "tracker"}:
                raise PreflightError([Diagnostic(
                    path, "products.track requires a region center, track or tracker",
                    {"requires_one_of": ["center", "track", "tracker"]}, raw[product],
                    ["Declare a region center, track or tracker for products.track."])])
            continue
        allowed = V3_KEYS[product]
        spec = _keys(spec, allowed, path, required={"radius_km"} if product == "polar" else ())
        if "fields" in spec:
            fields = spec["fields"]
            if not isinstance(fields, dict) or not fields:
                raise PreflightError([Diagnostic(
                    f"{path}.fields", f"{path}.fields must be a nonempty source-name mapping",
                    "nonempty source-name mapping", fields,
                    [f"Provide a nonempty source-name mapping for {path}.fields."])])
            for name, names in fields.items():
                if name not in sources:
                    raise PreflightError([Diagnostic(
                        f"{path}.fields.{name}", f"{path}.fields.{name}: unknown source",
                        {"sources": sorted(sources)}, name,
                        [f"Use a declared source name for {path}.fields.{name}."])])
                _names(names, f"{path}.fields.{name}")
                available = _declared_fields(sources[name])
                if not set(names) <= set(available):
                    raise PreflightError([Diagnostic(
                        f"{path}.fields.{name}",
                        f"{path}.fields.{name}: unknown field/result; declare it in sources",
                        {"declared_fields": available}, names,
                        [f"Select declared fields/results in {path}.fields.{name}."])])
        for name, source in sources.items():
            for field in _product_fields(spec, sources, name):
                method = source["derived"].get(field, {}).get("method")
                if method not in {"radial_wind", "tangential_wind"}:
                    continue
                loc = f"sources.{name}.derived.{field}"
                if product != "polar":
                    raise ValueError(
                        f"{path}.fields.{name}: {field} ({method}) is polar-only; "
                        "select it only in products.polar.fields and filter model_grid fields")
                if source.get("model") in {"nemo", "croco"}:
                    raise ValueError(f"{loc}: {method} admits atmospheric winds only")
                if source.get("format") == "fa":
                    raise ValueError(f"{loc}: {method} does not admit FA inputs")
        processing = spec.get("processing", {})
        processing_keys = V3_KEYS["polar_processing"] if product == "polar" else {"chunks"}
        _keys(processing, processing_keys, f"{path}.processing")
        if "chunks" in processing:
            _sizes(processing["chunks"], f"{path}.processing.chunks", whole_axis=True)
        if product == "polar":
            if not region.keys() & {"center", "track", "tracker"}:
                raise PreflightError([Diagnostic(
                    path, f"{path} requires a region center, track or tracker",
                    {"requires_one_of": ["center", "track", "tracker"]}, spec,
                    [f"Declare a region center, track or tracker for {path}."])])
            _positive(spec["radius_km"], f"{path}.radius_km")
            if "radial_step_km" in spec:
                _positive(spec["radial_step_km"], f"{path}.radial_step_km")
            if "azimuth_count" in spec:
                _positive(spec["azimuth_count"], f"{path}.azimuth_count", integer=True)
                if spec["azimuth_count"] < V3_LIMITS["azimuth_count"]:
                    raise PreflightError([Diagnostic(
                        f"{path}.azimuth_count", f"{path}.azimuth_count must be at least 3",
                        {"min": 3}, spec["azimuth_count"],
                        [f"Set {path}.azimuth_count to at least 3."])])
            spec.setdefault("shared_grid", False)
            _boolean(spec["shared_grid"], f"{path}.shared_grid")
            _mask_options(spec, path, defaults=True)
            for key in ("max_target_points", "source_halo_points"):
                if key in processing:
                    _positive(processing[key], f"{path}.processing.{key}", integer=True)
            if "weight_zero_tolerance" in processing:
                value = processing["weight_zero_tolerance"]
                _positive(value, f"{path}.processing.weight_zero_tolerance", allow_zero=True)
                if value >= V3_LIMITS["weight_zero_tolerance"]:
                    raise PreflightError([Diagnostic(
                        f"{path}.processing.weight_zero_tolerance",
                        f"{path}.processing.weight_zero_tolerance must be below 1e-6",
                        {"min": 0, "exclusive_max": 1e-6}, value,
                        [f"Set {path}.processing.weight_zero_tolerance below 1e-6."])])
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
                raise PreflightError([Diagnostic(
                    f"{path}.field_options", f"{path}.field_options must be a source-name mapping",
                    "source-name mapping", options,
                    [f"Provide a source-name mapping for {path}.field_options."])])
            for name, fields in options.items():
                if name not in sources or not isinstance(fields, dict):
                    raise PreflightError([Diagnostic(
                        f"{path}.field_options.{name}",
                        f"{path}.field_options.{name}: unknown source or invalid mapping",
                        {"sources": sorted(sources)} if name not in sources else "mapping",
                        name if name not in sources else fields,
                        [f"Use a declared source and a mapping in {path}.field_options.{name}."])])
                exports = _product_fields(spec, sources, name)
                needed = set(exports) | set(_derived_inputs(sources[name], exports))
                for field, values in fields.items():
                    loc = f"{path}.field_options.{name}.{field}"
                    if field not in needed:
                        raise PreflightError([Diagnostic(
                            loc, f"{loc}: field is unused by this product",
                            {"selected_fields": sorted(needed)}, field,
                            [f"Remove {loc}, or explicitly select this field for the product."])])
                    _keys(values, V3_KEYS["field_options"], loc)
                    if "units" in values:
                        _text(values["units"], f"{loc}.units")
                        if field not in exports or field in sources[name]["derived"]:
                            raise ValueError(f"{loc}.units requires a selected base field; "
                                             "derived methods retain their specified units")
                    if "basis" in values:
                        _choice(values["basis"], V3_CHOICES["transform_basis"], f"{loc}.basis")
                        if field not in exports or field in sources[name]["derived"]:
                            raise ValueError(f"{loc}.basis requires a selected base field")
                    effective = {key: spec[key] for key in
                                 ("missing_data_policy", "min_valid_weight_fraction") if key in spec}
                    if values.get("missing_data_policy") == "strict":
                        effective.pop("min_valid_weight_fraction", None)
                    effective.update(values)
                    _mask_options(effective, loc)
                    if "sampling" in values:
                        _choice(values["sampling"], V3_CHOICES["sampling"], f"{loc}.sampling")
                    if field in sources[name]["derived"] and values.keys() & {
                        "interpolation", "sampling", "missing_data_policy", "min_valid_weight_fraction",
                    }:
                        raise PreflightError([Diagnostic(
                            loc, f"{loc}: set polar preparation on the derived result's inputs",
                            {"configure_inputs": list(
                                sources[name]["derived"][field]["inputs"].values())},
                            values, [f"Set preparation on the inputs of {loc}, not the result."])])
        products[product] = (True if product == "model_grid" and not spec else spec)
    return products


def _variable_fields(variables):
    fields = {key: list(variables.get(key, [])) for key in ("2d", "3d")}
    if isinstance(variables.get("3d"), dict):
        fields["3d"] = [f"{group}.{name}" for group, spec in variables["3d"].items()
                        for name in spec["names"]]
    return fields


def field_selection(request, reference):
    """Keep a request key separate from its native field name and local selector."""
    group, separator, name = reference.partition(".")
    if separator and group in request.get("groups", {}):
        return name, group, request["groups"][group].get("levels", {})
    return reference, None, request.get("levels", {})


def _declared_fields(source):
    fields = _variable_fields(source["variables"])
    return [*fields["2d"], *fields["3d"], *source["derived"]]


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
    _choice(output["format"], V3_CHOICES["output_format"], "output.format")
    _boolean(output["overwrite"], "output.overwrite")
    writer = _keys(output["writer"], V3_KEYS["writer"], "output.writer")
    if output["format"] == "zarr":
        for key in ("engine", "unlimited_time"):
            if key in writer:
                raise PreflightError([Diagnostic(
                    f"output.writer.{key}",
                    f"output.writer.{key} is NetCDF-only, even with products.track",
                    {"format": "netcdf"}, {"format": output["format"], "value": writer[key]},
                    [f"Omit output.writer.{key} for Zarr, or select output.format: netcdf."])])
    else:
        if "shards" in writer:
            raise PreflightError([Diagnostic(
                "output.writer.shards", "output.writer.shards is Zarr-only",
                {"format": "zarr"}, {"format": output["format"], "value": writer["shards"]},
                ["Omit output.writer.shards for NetCDF, or select output.format: zarr."])])
        writer.setdefault("engine", "netcdf4")
        writer.setdefault("unlimited_time", True)
        _choice(writer["engine"], V3_CHOICES["writer_engine"], "output.writer.engine")
        _boolean(writer["unlimited_time"], "output.writer.unlimited_time")
    compression = _merge_checked(writer.get("compression", {}),
                                 COMPRESSION_DEFAULTS, "output.writer.compression")
    _positive(compression["level"], "output.writer.compression.level", integer=True, allow_zero=True)
    if compression["level"] > V3_LIMITS["compression_level"]:
        raise PreflightError([Diagnostic(
            "output.writer.compression.level", "output.writer.compression.level must be in [0, 9]",
            {"min": 0, "max": 9}, compression["level"],
            ["Set output.writer.compression.level to an integer in [0, 9]."])])
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
        raise PreflightError([Diagnostic(
            "schema_version",
            "Expected schema_version: 3 (a YAML integer, not a boolean or string)",
            {"type": "integer", "value": 3},
            raw.get("schema_version") if isinstance(raw, dict) else raw,
            ["Use schema_version: 3 with an unquoted YAML integer."])])
    _reject_nulls({key: value for key, value in raw.items() if key != "sources"})
    _keys(raw, set(DEFAULTS), "configuration", required={"sources"})
    base = Path(base_dir or Path.cwd()).resolve()
    conf = copy.deepcopy(DEFAULTS)
    conf["run"] = _merge_checked(raw.get("run", {}), DEFAULTS["run"], "run")
    _text(conf["run"]["name"], "run.name")
    if "/" in conf["run"]["name"] or "\\" in conf["run"]["name"] or conf["run"]["name"] in {".", ".."}:
        raise PreflightError([Diagnostic(
            "run.name", "run.name must be an identifier without path separators",
            "identifier without path separators", conf["run"]["name"],
            ["Set run.name to an identifier without path separators."])])
    if not isinstance(conf["run"]["description"], str):
        raise PreflightError([Diagnostic(
            "run.description", "run.description must be a string", "string",
            conf["run"]["description"], ["Use a string for run.description."])])
    sources = raw["sources"]
    if sources is None:
        _reject_nulls(sources, "sources")
    if not isinstance(sources, dict) or not sources:
        raise PreflightError([Diagnostic(
            "sources", "sources must be a nonempty mapping of source names",
            "nonempty mapping of source names", sources,
            ["Provide a nonempty source-name mapping for sources."])])
    errors = []
    for name, spec in sources.items():
        try:
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
                raise PreflightError([Diagnostic(
                    f"sources.{name}",
                    "sources names must start with a letter and contain letters/digits/_/-",
                    {"pattern": "[A-Za-z][A-Za-z0-9_-]*"}, name,
                    [f"Rename sources.{name} to start with a letter "
                     "and contain letters/digits/_/-."])])
            _reject_nulls(spec, f"sources.{name}")
            conf["sources"][name] = _source(spec, name, base)
        except ValueError as exc:
            errors.extend(exception_diagnostics(
                exc, path=f"sources.{name}", expected="valid source declaration", observed=spec,
                repairs=[f"Correct sources.{name}: {exc}"]))
    if errors:
        raise PreflightError(errors)
    conf["region"] = _region(raw.get("region", {}), base)
    conf["products"] = _products(raw.get("products", DEFAULTS["products"]),
                                conf["sources"], conf["region"])
    conf["output"] = _output(raw.get("output", {}), base)
    resources = _keys(raw.get("resources", {}), V3_KEYS["resources"], "resources")
    resources = {**DEFAULTS["resources"], **resources}
    _choice(resources["scheduler"], V3_CHOICES["scheduler"], "resources.scheduler")
    _boolean(resources["synchronous_export"], "resources.synchronous_export")
    for key in ("cpus", "compute_workers", "export_workers", "native_threads"):
        if key in resources:
            _positive(resources[key], f"resources.{key}", integer=True)
    conf["resources"] = resources
    conf["logging"] = _merge_checked(raw.get("logging", {}), DEFAULTS["logging"], "logging")
    _choice(conf["logging"]["level"], V3_CHOICES["log_level"], "logging.level")
    conf["metadata"] = _keys(raw.get("metadata", {}), V3_KEYS["metadata"], "metadata")
    conf["metadata"].setdefault("extra", {})
    if "institution" in conf["metadata"] and not isinstance(conf["metadata"]["institution"], str):
        raise PreflightError([Diagnostic(
            "metadata.institution", "metadata.institution must be a string", "string",
            conf["metadata"]["institution"], ["Use a string for metadata.institution."])])
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
            "fields": copy.deepcopy(_variable_fields(source["variables"])),
            **({"groups": copy.deepcopy(source["variables"]["3d"])}
               if isinstance(source["variables"].get("3d"), dict) else {}),
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


def to_runtime(raw, *, base_dir=None, launch_dir=None, overrides=None):
    """Return SimulationConfig arguments; source requests remain unbound."""
    context = {
        "request_kind": "mapping", "authored_configuration": copy.deepcopy(raw),
        "request_path": None,
        "path_bases": {
            "configuration_directory": str(Path(base_dir or Path.cwd()).resolve()),
            "launch_directory": str(Path(launch_dir or Path.cwd()).resolve()),
        },
        "overrides": copy.deepcopy(overrides) if overrides is not None else {},
    }
    if overrides is not None:
        conf, origins = resolve_operational_overrides(
            raw, base_dir=base_dir, launch_dir=launch_dir, overrides=overrides)
        if isinstance(context["overrides"].get("output_directory"), os.PathLike):
            context["overrides"]["output_directory"] = os.fspath(overrides["output_directory"])
        _, requests, _ = resolve_schema(conf, base_dir=base_dir)
    else:
        conf, requests, _ = resolve_schema(raw, base_dir=base_dir)
        origins = setting_sources(raw, conf)
    runtime = _runtime_from_resolved(conf, requests, origins, base_dir=base_dir)
    runtime["request_context"] = context
    return runtime


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
        writer["chunks"] = dict(options.zarr_chunk_size)
        writer["shards"] = dict(options.zarr_shard_size)
    else:
        writer.pop("shards", None)
        writer["engine"], writer["unlimited_time"] = options.engine, options.unlimited_time
        writer["chunks"] = dict(options.netcdf_chunk_size)
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
        origins = {path: origin for path, origin in origins.items() if path in baseline}

        def mark(before, after, prefix=""):
            for key, value in after.items():
                path = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict) and value:
                    mark(before.get(key, {}), value, path)
                elif key not in before or before[key] != value:
                    origins[path] = "cli"

        mark(conf.yaml_config, effective)
        for path in baseline:
            origins.setdefault(path, "default")
        origins.update(options.setting_sources)
    return origins


def load_runtime(path, *, launch_dir=None, overrides=None):
    """Load strict YAML and add authored line locations to dotted-key errors."""
    path = Path(path)
    raw, locations = _read_yaml(path)
    try:
        runtime = to_runtime(raw, base_dir=path.resolve().parent,
                             launch_dir=launch_dir, overrides=overrides)
        runtime["request_context"].update(request_kind="yaml", request_path=str(path.absolute()))
        runtime["simulation_parameter"]["_yaml_locations"] = locations
        return runtime
    except ValueError as exc:
        if isinstance(exc, PreflightError):
            from frameit.core.reports import _locations

            for error in exc.diagnostics:
                error.locations = error.locations or _locations(locations, error.path)
            raise
        message = str(exc)
        matches = [(name, mark["line"]) for name, mark in locations.items() if name in message]
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
    starter_method = starter["region"].get("tracker", {}).get("method", "fixed_box")
    method = tracking or starter_method
    if method != starter_method:
        block = "region:\n"
        if coupling:
            block += "  sources_coupling_time_association: common\n"
        if method == "prescribed_track":
            block += ("  # Exact timestamps and geographic degrees; no nearest-time matching.\n"
                      "  # Replace both instructional data and track when using real inputs.\n"
                      "  track:\n    file: ./track.nc\n")
        else:
            block += f"  tracker:\n    method: {method}\n"
        text = re.sub(r"(?ms)^region:\n.*?(?=^  # Illustrative|^  # Full widths)",
                      lambda _: block, text, count=1)
        text = text.replace(f"  name: {starter['run']['name']}\n",
                            f"  name: {name}{'-' + coupling if coupling else ''}-{method.replace('_', '-')}\n")
    if method == "pressure_centroid":
        pair = ("{u: u, v: v, basis: earth}" if name == "arome"
                else "{u: UT_ZM, v: VT_ZM, basis: earth}")
        if not coupling:
            text = text.replace("    # Preserve the selected", f"      - {pair}\n"
                                "    # Preserve the selected", 1)
        guidance = ("# Verify wind declarations and source ASL/pressure/native brackets.\n"
                    "# Keep full 500-km reference-ring support; Meso-NH must bracket 2000 m ASL.\n")
        if coupling:
            guidance += "# Requires at least two exact common times across sources.\n"
        text = text.replace("region:\n", guidance + "region:\n", 1)
    if coupling and method in {"pressure_wind", "pressure_centroid"}:
        u, v = ("u10", "v10") if name == "arome" else ("UM10", "VM10")
        declarations = ("    # Atmospheric tracker winds, independent of ocean sampling.\n"
                        "    # Verify the actual source wind basis and velocity/pressure units.\n"
                        "    # earth: u positive eastward, v positive northward.\n"
                        "    wind_pairs:\n"
                        f"      - {{u: {u}, v: {v}, basis: earth}}\n")
        if method == "pressure_centroid":
            declarations += f"      - {pair}\n"
        # Both coupled resources put the atmosphere first; leave ocean inputs untouched.
        text = text.replace("    format: netcdf\n", "    format: netcdf\n" + declarations, 1)
        text = text.replace("target, winds, currents", "target, currents")
    if coupling and name == "mesonh" and method == "pressure_wind":
        text = text.replace("      2d: [SST, SSS]", "      2d: [SST, SSS, UM10, VM10, MSLP]")
        text = text.replace("  ocean:\n", "    transforms:\n"
                            "      - {fields: [UM10, VM10], sampling: mass, basis: earth}\n"
                            "  ocean:\n", 1)
    path = Path(path)
    resolve_schema(yaml.safe_load(text), base_dir=path.absolute().parent)
    with atomic_output(path, overwrite=force) as temporary:
        temporary.write_text(text, encoding="utf-8")
    return path
