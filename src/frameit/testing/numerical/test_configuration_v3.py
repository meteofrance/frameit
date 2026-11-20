"""Metadata-free public v3 syntax, defaults and runtime handoffs."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from frameit.core import configuration
from frameit.core.configuration import resolve_schema, source_document, to_runtime
from frameit.core.execution import ExecutionOptions
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import resolve_config_with_model_presets


def document():
    return {
        "schema_version": 3,
        "sources": {
            "weather": {
                "model": "mesonh", "files": "./data/*.nc",
                "variables": {"2d": ["MSLP"], "3d": ["UT", "VT", "WT"]},
            },
        },
    }


def put(raw, path, value):
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def test_defaults_keep_full_native_request_without_a_track_or_scientific_guesses(tmp_path):
    raw = document()
    original = copy.deepcopy(raw)
    resolved, requests, polar = resolve_schema(raw, base_dir=tmp_path)
    assert raw == original
    assert resolved["products"] == {"model_grid": True}
    assert resolved["region"] == {}
    assert resolved["output"]["overwrite"] is False
    assert resolved["output"]["format"] == "netcdf"
    assert resolved["output"]["writer"] == {
        "engine": "netcdf4", "unlimited_time": True,
        "compression": {"level": 1, "coordinates": False},
    }
    assert resolved["metadata"] == {"extra": {}}
    assert resolved["resources"] == {
        "scheduler": "threads", "native_threads": 1, "synchronous_export": False,
    }
    source = resolved["sources"]["weather"]
    assert source["files"] == str(tmp_path / "data/*.nc")
    assert "levels" not in source["variables"]
    assert source["field_metadata"] == {}
    assert source["wind_pairs"] == [] and source["transforms"] == [] and source["derived"] == {}
    assert requests["weather"]["exports"] == {"model_grid": ["MSLP", "UT", "VT", "WT"]}
    assert requests["weather"]["internal_inputs"] == []
    assert requests["weather"]["binding"] is None
    assert polar == {}
    assert resolve_schema(resolved)[0] == resolved
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("version", [None, True, False, 1, 2, "2.1", "3", 3.0, 4])
@pytest.mark.parametrize("route", ["resolve", "runtime", "mapping", "presets", "yaml"])
def test_all_public_loaders_require_integer_three_before_input_access(tmp_path, version, route):
    raw = document()
    if version is None:
        raw.pop("schema_version")
    else:
        raw["schema_version"] = version
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump(raw))
    routes = {
        "resolve": lambda: resolve_schema(raw),
        "runtime": lambda: to_runtime(raw),
        "mapping": lambda: SimulationConfig.from_mapping_with_model_preset(raw),
        "presets": lambda: resolve_config_with_model_presets(raw),
        "yaml": lambda: SimulationConfig.from_yaml(path),
    }
    with pytest.raises(ValueError, match="schema_version: 3"):
        routes[route]()
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("path", [
    "model", "input", "tracking", "domain", "variables", "polar", "execution",
    "sources.weather.type", "sources.weather.input", "sources.weather.layout",
    "sources.weather.grid_spacing_m", "sources.weather.duplicate_time_policy",
    "sources.weather.surfex_fields", "sources.weather.reader.file_layout",
    "sources.weather.reader.backend", "sources.weather.variables.fields_2d",
    "sources.weather.variables.levels.per_field", "sources.weather.time.nearest",
    "region.source", "region.track.latitude_name", "region.tracker.source",
    "region.tracker.pressure_wind", "products.model_grid.enabled",
    "products.polar.azimuth_step_deg", "products.polar.levels",
    "output.backend", "output.writer.format", "resources.dask_workers",
    "metadata.ocean_model", "metadata.wave_model", "logging.levle",
])
def test_unknown_and_retired_keys_fail_at_their_yaml_location(path):
    raw = document()
    if path.startswith("region.track."):
        raw["region"] = {"track": {"file": "track.nc"}}
    if path.startswith("region.tracker."):
        raw["region"] = {"tracker": {"method": "pressure_wind"}}
    if path.startswith("products.model_grid."):
        raw["products"] = {"model_grid": {}}
    if path.startswith("products.polar."):
        raw["region"] = {"center": {"latitude": -20, "longitude": 60}}
        raw["products"] = {"polar": {"radius_km": 100}}
    put(raw, path, {})
    with pytest.raises(ValueError, match=path.replace(".", r"\.")):
        resolve_schema(raw)


@pytest.mark.parametrize("path", [
    "sources", "sources.weather", "sources.weather.model", "sources.weather.files",
    "sources.weather.exclude", "sources.weather.variables", "sources.weather.variables.2d",
    "sources.weather.variables.levels", "sources.weather.variables.levels.units",
    "sources.weather.time", "sources.weather.time.start", "sources.weather.reader.chunks.x",
    "sources.weather.field_metadata.UT.units", "sources.weather.wind_pairs",
    "sources.weather.transforms", "sources.weather.derived", "region", "region.center.latitude",
    "region.tracker.initial_guess.latitude", "products", "products.model_grid",
    "products.polar.processing.plan_cache.entries", "output.writer.compression.level",
    "metadata.institution", "logging.level", "resources.cpus", "run.description",
])
def test_explicit_null_is_rejected_recursively_with_omission_guidance(path):
    raw = document()
    put(raw, path, None)
    with pytest.raises(ValueError, match=rf"{path.replace('.', r'\.')}.*omit"):
        resolve_schema(raw)


def test_metadata_extra_alone_allows_arbitrary_nested_null_annotations():
    raw = document()
    raw["metadata"] = {
        "extra": {"unset": None, "nested": [None, {"arbitrary": None}]},
    }
    assert resolve_schema(raw)[0]["metadata"] == raw["metadata"]
    raw["metadata"]["extra"] = None
    with pytest.raises(ValueError, match="metadata.extra.*mapping"):
        resolve_schema(raw)


@pytest.mark.parametrize("tail,line", [
    ("run:\n  name: first\n  name: second\n", 6),
    ("metadata:\n  extra:\n    label: first\n    label: second\n", 7),
])
def test_duplicate_yaml_keys_fail_even_inside_annotations(tmp_path, tail, line):
    path = tmp_path / "duplicate.yaml"
    path.write_text("schema_version: 3\nsources:\n  weather: {files: data.nc}\n" + tail)
    with pytest.raises(ValueError, match=rf"Duplicate key.*line {line}"):
        SimulationConfig.from_yaml(path)


def test_yaml_error_includes_the_authored_line_and_no_output(tmp_path):
    path = tmp_path / "case.yaml"
    path.write_text("schema_version: 3\nsources:\n  weather:\n    files: data.nc\n    reader:\n      engin: scipy\n")
    with pytest.raises(ValueError, match="sources.weather.reader.engin") as error:
        SimulationConfig.from_yaml(path)
    assert "line 6" in str(error.value)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("files", ["data.nc", ["a.nc", "parts/*.nc"]])
def test_paths_and_auxiliaries_are_yaml_relative_without_discovery(tmp_path, files):
    raw = document()
    raw["sources"]["weather"]["files"] = files
    raw["sources"]["weather"]["exclude"] = ["parts/skip*.nc"]
    raw["region"] = {"track": {"file": "tracks/centres.nc"}}
    raw["output"] = {"directory": "runs/output"}
    conf, _, _ = resolve_schema(raw, base_dir=tmp_path)
    expected = (str(tmp_path / files) if isinstance(files, str)
                else [str(tmp_path / item) for item in files])
    assert conf["sources"]["weather"]["files"] == expected
    assert conf["sources"]["weather"]["exclude"] == [str(tmp_path / "parts/skip*.nc")]
    assert conf["region"]["track"]["file"] == str(tmp_path / "tracks/centres.nc")
    assert conf["output"]["directory"] == str(tmp_path / "runs/output")


@pytest.mark.parametrize("source", [
    {}, {"files": []}, {"files": ""}, {"files": [True]}, {"files": "x", "model": "unknown"},
    {"files": "x", "format": "hdf5"}, {"files": "x", "model": "nemo", "format": "grib"},
    {"files": "x", "model": "mesonh", "format": "fa"},
    {"files": "x", "exclude": "skip.nc"},
])
def test_source_required_paths_and_admitted_model_formats(source):
    with pytest.raises(ValueError, match="sources.custom"):
        resolve_schema({"schema_version": 3, "sources": {"custom": source}})


def test_undeclared_model_format_and_multiple_sources_stay_unbound(tmp_path):
    raw = {"schema_version": 3, "sources": {
        "anything": {"files": "a.nc"}, "another": {"files": "b.nc"},
    }}
    runtime = to_runtime(raw, base_dir=tmp_path)
    assert runtime["atm_model"] is None and runtime["file_type"] == ""
    assert runtime["input_sources"] == {} and runtime["tracking_source"] is None
    assert set(runtime["sources"]) == {"anything", "another"}
    plan = runtime["simulation_parameter"]["request_plan"]
    for source in plan["sources"].values():
        assert source["physical_type"] is None and source["records"] is None
        assert source["native_grids"] is None and source["files"] is None
    assert plan["warnings"] == [] and plan["deferred_checks"]
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    assert conf.atm_model is None and conf.requested_variables_tracker == {}
    assert "preset_model_used" not in conf.simulation_parameter


@pytest.mark.parametrize("time", [
    {"start": "2026-01-01T00:00:00", "end": "2026-01-02T00:00:00", "stride": 2},
    {"values": ["2026-01-02T00:00:00", "2026-01-01T00:00:00"]},
    {"cycle": "2026-01-01T00:00:00", "values": ["2026-01-01T01:00:00Z"]},
    {"start": "2001-02-30T00:00:00"},  # Source calendars are not assumed Gregorian.
    {},
])
def test_time_requests_preserve_decoded_calendar_decisions_for_binding(time):
    raw = document()
    raw["sources"]["weather"]["time"] = time
    resolved = resolve_schema(raw)[0]["sources"]["weather"]["time"]
    assert all(resolved[key] == value for key, value in time.items())


@pytest.mark.parametrize("time", [
    {"values": []}, {"values": ["2026-01-01T00:00:00"] * 2},
    {"values": ["2026-01-01T00:00:00"], "start": "2026-01-01T00:00:00"},
    {"values": ["2026-01-01T00:00:00"], "stride": 2},
    {"start": "2026-01-02T00:00:00", "end": "2026-01-01T00:00:00"},
    {"start": "not-a-time"}, {"cycle": 20260101}, {"start": "2026-13-01T00:00:00"},
    {"start": "2026-01-01T24:00:00"}, {"stride": 0}, {"stride": True}, {"stride": 1.5},
])
def test_invalid_or_exclusive_time_syntax(time):
    raw = document()
    raw["sources"]["weather"]["time"] = time
    with pytest.raises(ValueError, match="sources.weather.time"):
        resolve_schema(raw)


@pytest.mark.parametrize("levels", [
    {"indices": [5, 0]}, {"indices": {"start": 0, "end": 20, "step": 2}},
    {"values": [850, 700], "units": "hPa"}, {"values": {"min": 700, "max": 850}},
    {"domain": "physical"}, {"units": "m"}, {},
])
def test_shared_levels_preserve_strategy_order_and_units_without_binding(levels):
    raw = document()
    raw["sources"]["weather"]["variables"]["levels"] = levels
    conf, requests, _ = resolve_schema(raw)
    assert conf["sources"]["weather"]["variables"]["levels"] == levels
    assert requests["weather"]["levels"] == levels


@pytest.mark.parametrize("levels", [
    {"indices": []}, {"indices": [0, 0]}, {"indices": [-1]}, {"indices": [True]},
    {"indices": [1.0]}, {"indices": {"start": 2, "end": 1}},
    {"indices": {"start": 0}}, {"indices": {"start": 0, "end": 3, "step": 0}},
    {"values": []}, {"values": [1, 1.]}, {"values": [float("nan")]},
    {"values": {"min": 850, "max": 700}}, {"values": {"min": 700}},
    {"indices": [0], "values": [850]}, {"domain": "physical", "indices": [0]},
    {"domain": "stored"}, {"units": ""}, {"units": 1}, "physical",
])
def test_invalid_or_multiple_level_strategies(levels):
    raw = document()
    raw["sources"]["weather"]["variables"]["levels"] = levels
    with pytest.raises(ValueError, match="levels"):
        resolve_schema(raw)


@pytest.mark.parametrize("variables", [
    {"2d": ["T", "T"]}, {"2d": ["T"], "3d": ["T"]}, {"2d": "T"},
    {"3d": [""]}, {"3d": [{"name": "T"}]}, {"level": ["T"]},
])
def test_variables_are_exact_unique_source_names_not_groups_or_qualified_selectors(variables):
    raw = document()
    raw["sources"]["weather"]["variables"] = variables
    with pytest.raises(ValueError, match="variables"):
        resolve_schema(raw)


def test_all_source_scientific_declarations_are_preserved_and_not_applied():
    raw = document()
    src = raw["sources"]["weather"]
    src.update(
        interpretation="mesonh_surfex_sea",
        field_metadata={"UT": {"units": "m s-1", "kind": "continuous",
                               "temporal_kind": "instantaneous"}},
        wind_pairs=[{"u": "UT", "v": "VT", "basis": "grid"}],
        transforms=[{"fields": ["UT", "VT"], "sampling": "mass", "basis": "earth"},
                    {"fields": ["WT"], "sampling": "mass", "units": "m s-1"}],
        derived={"speed": {"method": "wind_speed", "inputs": {"u": "UT", "v": "VT"}}},
        reader={"engine": "h5netcdf", "chunks": {"time": 1, "level": -1}},
    )
    resolved, requests, _ = resolve_schema(raw)
    for key in ("interpretation", "field_metadata", "wind_pairs", "transforms", "derived", "reader"):
        assert resolved["sources"]["weather"][key] == src[key]
    assert "speed" in requests["weather"]["exports"]["model_grid"]
    assert requests["weather"]["internal_inputs"] == ["UT", "VT"]
    assert "units" not in resolved["sources"]["weather"]["variables"]


@pytest.mark.parametrize("path,value", [
    ("field_metadata.UT.kind", "auto"), ("field_metadata.UT.units", ""),
    ("field_metadata.UT.temporal_kind", "auto"), ("field_metadata.UT.unknown", 1),
    ("interpretation", "auto"), ("wind_pairs", [{"u": "UT", "v": "UT", "basis": "earth"}]),
    ("wind_pairs", [{"group": "level", "u": "UT", "v": "VT", "basis": "earth"}]),
    ("wind_pairs", [{"u": "UT", "v": "VT", "basis": "auto"}]),
    ("wind_pairs", [{"u": "UT", "v": "VT", "basis": "grid",
                     "rotation": {"method": "coordinate"}}]),
    ("wind_pairs", [{"u": "UT", "v": "VT", "basis": "grid",
                     "rotation": {"method": "geolocation", "BETA": 0}}]),
    ("transforms", [{"fields": ["UT"], "sampling": "auto"}]),
    ("transforms", [{"fields": ["UT"], "units": ""}]),
    ("transforms", [{"fields": ["UT"]}]),
    ("derived", {"MSLP": {"method": "wind_speed", "inputs": {"u": "UT", "v": "VT"}}}),
    ("derived", {"speed": {"method": "invented", "inputs": {"u": "UT", "v": "VT"}}}),
    ("derived", {"speed": {"method": "wind_speed", "inputs": {"u": "UT"}}}),
])
def test_invalid_source_declarations_are_not_accepted_as_arbitrary_mappings(path, value):
    raw = document()
    put(raw, "sources.weather." + path, value)
    with pytest.raises(ValueError, match=path.split(".")[0]):
        resolve_schema(raw)


@pytest.mark.parametrize("method,options", [
    ("coordinate", {"coordinate": "angle"}),
    ("geolocation", {}),
    ("mesonh_projection", {"BETA": 0., "RPK": -0.5, "LON0": 55.}),
])
def test_approved_rotation_declarations_need_no_eager_metadata(method, options):
    raw = document()
    raw["sources"]["weather"]["wind_pairs"] = [{
        "u": "UT", "v": "VT", "basis": "grid", "rotation": {"method": method, **options},
    }]
    assert resolve_schema(raw)[0]["sources"]["weather"]["wind_pairs"] == raw["sources"]["weather"]["wind_pairs"]


def fa_document():
    return {"schema_version": 3, "sources": {"native": {
        "model": "arome", "format": "fa", "profile": "arome_history", "files": "*.fa",
        "native_cubes": {"temperature": {
            "records": ["S001TEMPERATURE", "S002TEMPERATURE"],
            "vertical_position": "mass", "sampling": "center",
        }},
        "field_metadata": {"temperature": {
            "units": "K", "kind": "continuous", "temporal_kind": "instantaneous",
        }},
        "variables": {"3d": ["temperature"], "levels": {"indices": [1, 0]}},
        "fa": {"subdomain": "C", "earth_radius_m": 6371229.,
               "expected_source": {"PROGRAM": "AROME", "VERSION": 1}},
        "reader": {"python_executable": "env/bin/python", "timeout_seconds": 60,
                   "max_points": 10000},
    }}}


def test_fa_keeps_existing_admission_and_preserves_helper_symlink(tmp_path):
    raw = fa_document()
    executable = tmp_path / "env/bin/python"
    executable.parent.mkdir(parents=True)
    executable.symlink_to("/usr/bin/python3")
    conf, _, _ = resolve_schema(raw, base_dir=tmp_path)
    assert conf["sources"]["native"]["reader"]["python_executable"] == str(executable)
    assert conf["sources"]["native"]["native_cubes"] == raw["sources"]["native"]["native_cubes"]
    runtime = SimulationConfig.from_mapping_with_model_preset(conf)
    assert runtime.fa_options["profile"] == "arome_history"
    assert runtime.fa_options["native_cubes"] == raw["sources"]["native"]["native_cubes"]


@pytest.mark.parametrize("path,value", [
    ("profile", "arbitrary"), ("fa.subdomain", "full"), ("fa.backend", "spectral"),
    ("fa.expected_source.VERSION", True), ("fa.expected_source.UNKNOWN", 1),
    ("native_cubes.temperature.sampling", "staggered"),
    ("native_cubes.temperature.component_scaling", "map_scaled"),
    ("native_cubes.temperature.records", ["S001TEMPERATURE"] * 2),
    ("field_metadata.temperature.temporal_kind", "accumulated"),
    ("variables.levels", {"domain": "physical"}),
])
def test_v3_does_not_broaden_fa_admission(path, value):
    raw = fa_document()
    put(raw, "sources.native." + path, value)
    with pytest.raises(ValueError, match="sources.native"):
        resolve_schema(raw)


@pytest.mark.parametrize("format,reader", [
    ("netcdf", {"python_executable": "python"}), ("grib", {"timeout_seconds": 2}),
    ("netcdf", {"max_points": 10}), ("fa", {"engine": "h5netcdf"}),
    ("grib", {"engine": "netcdf4"}), ("netcdf", {"engine": "cfgrib"}),
    ("netcdf", {"chunks": {"x": True}}),
])
def test_reader_options_apply_only_to_admitted_formats(format, reader):
    raw = document() if format != "fa" else fa_document()
    name = "weather" if format != "fa" else "native"
    raw["sources"][name]["format"] = format
    raw["sources"][name]["reader"] = reader
    with pytest.raises(ValueError, match="reader"):
        resolve_schema(raw)


@pytest.mark.parametrize("region", [
    {"center": {"latitude": -20, "longitude": 60}},
    {"track": {"file": "./centres.nc"}},
    {"tracker": {"method": "pressure_wind"}},
    {"tracker": {"method": "pressure_centroid", "motion": {"solver": "fixed"}}},
    {"tracker": {"method": "utrack", "weights_file": "./weights.pt"}},
])
def test_explicit_centre_providers_and_tracker_method_defaults(region):
    raw = document()
    raw["region"] = region
    resolved = resolve_schema(raw)[0]["region"]
    assert resolved["sources_coupling_time_association"] == "exact"
    if region.get("tracker", {}).get("method") == "pressure_wind":
        assert resolved["tracker"]["search_width_km"] == 200
        assert resolved["tracker"]["refine_width_km"] == 100
        assert resolved["tracker"]["on_incomplete"] == "error"
    assert resolve_schema(raw)[0]["products"] == {"model_grid": True}


@pytest.mark.parametrize("region", [
    {"center": {"latitude": 0, "longitude": 0}, "track": {"file": "track.nc"}},
    {"center": {"latitude": 0, "longitude": 0}, "tracker": {"method": "pressure_wind"}},
    {"width_km": {"x": 20, "y": 20}}, {"center": {}},
    {"center": {"latitude": True, "longitude": 0}},
    {"center": {"latitude": 91, "longitude": 0}},
    {"center": {"latitude": 0, "longitude": float("inf")}},
    {"tracker": {}}, {"tracker": {"method": "unknown"}},
    {"tracker": {"method": "pressure_wind", "on_incomplete": "silent"}},
    {"tracker": {"method": "pressure_wind", "search_width_km": 0}},
    {"tracker": {"method": "pressure_centroid", "search_width_km": 100}},
    {"track": {}}, {"sources_coupling_time_association": "nearest"},
])
def test_regions_reject_multiple_providers_missing_geometry_and_wrong_method_settings(region):
    raw = document()
    raw["region"] = region
    with pytest.raises(ValueError, match="region"):
        resolve_schema(raw)


def test_track_and_polar_are_explicit_products_not_tracker_side_effects(tmp_path):
    raw = document()
    raw["region"] = {"center": {"latitude": -20, "longitude": 60}}
    raw["sources"]["weather"]["derived"] = {
        "speed": {"method": "wind_speed", "inputs": {"u": "UT", "v": "VT"}},
    }
    raw["products"] = {
        "polar": {"radius_km": 200, "azimuth_count": 180,
                  "fields": {"weather": ["MSLP", "speed", "WT"]},
                  "field_options": {"weather": {
                      "UT": {"interpolation": "bilinear"},
                      "WT": {"sampling": "mass"},
                  }},
                  "processing": {"chunks": {"time": 1}, "max_target_points": 100000,
                                 "plan_cache": {"entries": 2, "max_bytes": 4096},
                                 "source_halo_points": 2, "weight_zero_tolerance": 1e-14,
                                 "profile": True}},
        "track": True,
    }
    conf, requests, polar = resolve_schema(raw, base_dir=tmp_path)
    assert "model_grid" not in conf["products"]
    assert conf["products"]["polar"]["missing_data_policy"] == "strict"
    assert conf["products"]["polar"]["shared_grid"] is False
    assert "radial_step_km" not in conf["products"]["polar"]
    assert requests["weather"]["exports"] == {"polar": ["MSLP", "speed", "WT"]}
    assert requests["weather"]["internal_inputs"] == ["UT", "VT"]
    assert polar == {"weather": ["MSLP", "speed", "WT"]}
    plan = to_runtime(raw, base_dir=tmp_path)["simulation_parameter"]["request_plan"]
    assert [(item["product"], item["path"]) for item in plan["products"]] == [
        ("polar", "products/analysis.weather.polar.nc"),
        ("track", "products/analysis.track.nc"),
    ]


@pytest.mark.parametrize("products", [
    {}, {"model_grid": False}, {"track": False}, {"track": True},
    {"polar": {"radius_km": 100}}, {"model_grid": {"fields": {"absent": ["MSLP"]}}},
    {"model_grid": {"fields": {}}},
    {"model_grid": {"fields": {"weather": ["MSLP", "MSLP"]}}},
])
def test_schema_rejects_invalid_product_shapes_centres_and_source_names(products):
    raw = document()
    raw["products"] = products
    with pytest.raises(ValueError, match="products"):
        resolve_schema(raw)


@pytest.mark.parametrize("options", [
    {"radius_km": 0}, {"radius_km": 100, "azimuth_count": 2},
    {"radius_km": 100, "azimuth_count": True},
    {"radius_km": 100, "radial_step_km": -1},
    {"radius_km": 100, "missing_data_policy": "renormalize"},
    {"radius_km": 100, "min_valid_weight_fraction": .5},
    {"radius_km": 100, "field_options": {"weather": {"MSLP": {
        "interpolation": "nearest", "missing_data_policy": "renormalize",
        "min_valid_weight_fraction": .5}}}},
    {"radius_km": 100, "field_options": {"weather": {"unused": {"sampling": "mass"}}}},
    {"radius_km": 100, "processing": {"source_halo_points": 0}},
    {"radius_km": 100, "processing": {"weight_zero_tolerance": 1e-3}},
])
def test_invalid_polar_controls_fail_without_reading_fields(options):
    raw = document()
    raw["region"] = {"center": {"latitude": -20, "longitude": 60}}
    raw["products"] = {"polar": options}
    with pytest.raises(ValueError, match="products.polar"):
        resolve_schema(raw)


@pytest.mark.parametrize("output", [
    {"format": "zarr", "writer": {"engine": "netcdf4"}},
    {"format": "zarr", "writer": {"unlimited_time": False}},
    {"format": "netcdf", "writer": {"shards": {"time": 2}}},
    {"format": "netcdf", "writer": {"engine": "scipy"}},
    {"writer": {"compression": {"level": True}}},
    {"writer": {"compression": {"level": 10}}},
    {"writer": {"chunks": {"time": 0}}}, {"overwrite": "false"},
])
def test_writer_cross_format_controls_stay_invalid_even_with_a_netcdf_track(output):
    raw = document()
    raw["region"] = {"center": {"latitude": -20, "longitude": 60}}
    raw["products"] = {"model_grid": True, "track": True}
    raw["output"] = output
    with pytest.raises(ValueError, match="output"):
        resolve_schema(raw)


def test_zarr_and_netcdf_writer_options_map_to_existing_execution_options():
    raw = document()
    raw["output"] = {"format": "zarr", "overwrite": True,
                     "writer": {"chunks": {"time": 2}, "shards": {"time": 4},
                                "compression": {"level": 3, "coordinates": True}}}
    raw["resources"] = {"cpus": 2, "compute_workers": 1, "export_workers": 2,
                        "native_threads": 1, "synchronous_export": True}
    raw["metadata"] = {"institution": "Declared laboratory", "extra": {"note": None}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    options = ExecutionOptions.from_config(conf)
    assert options.engine == "zarr" and options.overwrite
    assert options.zarr_chunk_size == {"time": 2} and options.zarr_shard_size == {"time": 4}
    assert options.compress_level == 3 and options.compress_coords
    assert options.institution == "Declared laboratory"
    assert options.cpus == 2 and options.max_workers == 2 and options.dask_workers == 1
    assert options.synchronous_export and not options.export_polar and options.export_cart


@pytest.mark.parametrize("path,value", [
    ("resources.cpus", True), ("resources.cpus", 0), ("resources.compute_workers", 1.5),
    ("resources.export_workers", -1), ("resources.scheduler", "processes"),
    ("resources.native_threads", 0), ("resources.synchronous_export", "false"),
    ("run.name", "../escape"), ("run.name", ""), ("run.description", False),
    ("logging.level", "TRACE"), ("metadata.institution", 1),
])
def test_run_resources_logging_and_metadata_boundaries(path, value):
    raw = document()
    put(raw, path, value)
    with pytest.raises(ValueError, match=path.replace(".", r"\.")):
        resolve_schema(raw)


def test_source_local_documents_are_independent_without_fabricated_centres(tmp_path):
    raw = document()
    raw["sources"]["sea"] = {"model": "nemo", "files": "ocean.nc", "variables": {"3d": ["temp"]}}
    raw["products"] = {"model_grid": {"fields": {"weather": ["UT"], "sea": ["temp"]}}}
    parent = resolve_schema(raw, base_dir=tmp_path)[0]
    saved = copy.deepcopy(parent)
    child = source_document(parent, "sea")
    assert child["sources"] == {"sea": parent["sources"]["sea"]}
    assert child["region"] == {} and child["products"] == {
        "model_grid": {"fields": {"sea": ["temp"]}},
    }
    assert resolve_schema(child)[0] == child
    child["sources"]["sea"]["variables"]["3d"].append("salt")
    assert parent == saved


def test_single_source_runtime_has_identity_but_never_uses_old_coupled_dispatch(tmp_path):
    conf = SimulationConfig.from_mapping_with_model_preset(document())
    assert conf.schema_version == 3 and conf.source_name == "weather"
    assert conf.atm_model == "MNH" and conf.input_sources == {}
    assert conf.tracking_method is None and conf.requested_variables_tracker == {}
    assert conf.wind_pairs == [] and conf.requested_variables_user == {}
    assert not conf.is_mnh_timeseries_name("000")
    assert conf.sources["weather"]["variables"]["3d"] == ["UT", "VT", "WT"]
    assert conf.expected_variables_user() == ["MSLP", "UT", "VT", "WT"]
    assert conf.expected_variables_tracker() == []
    assert not conf.compute_polar_proj
    assert conf.cartesian_horizontal_winds == "native"
    assert conf.cartesian_vertical_velocity == conf.polar_vertical_velocity == "interfaces"
    options = ExecutionOptions.from_config(conf)
    assert options.overwrite is False and options.institution == ""
    assert options.export_cart and not options.export_polar
    assert configuration.resolved_configuration(conf) == conf.yaml_config
    assert configuration.resolved_sources(conf)["output.overwrite"] == "default"


def test_explicit_pressure_wind_full_widths_map_without_changing_old_tracker_geometry():
    raw = document()
    raw["region"] = {"tracker": {"method": "pressure_wind", "search_width_km": 150,
                                  "refine_width_km": 50,
                                  "initial_guess": {"latitude": -20., "longitude": 60.,
                                                    "search_radius_km": 100}},
                     "width_km": {"x": 400, "y": 300}}
    runtime = to_runtime(raw)
    assert runtime["tracking_method"] == "wind_pressure"
    assert runtime["wind_pressure_search_half_width_km"] == 75
    assert runtime["wind_pressure_refine_half_width_km"] == 25
    assert (runtime["x_boxsize_km"], runtime["y_boxsize_km"]) == (400, 300)


def test_operational_precedence_origins_and_distinct_path_bases(tmp_path):
    yaml_base, launch = tmp_path / "authored", tmp_path / "launch"
    raw = document()
    raw["output"] = {"directory": "yaml-output", "overwrite": True}
    raw["resources"] = {"cpus": 8}
    raw["logging"] = {"level": "WARNING"}
    original = copy.deepcopy(raw)
    effective, origins = configuration.resolve_operational_overrides(
        raw, base_dir=yaml_base, launch_dir=launch,
        overrides={"output_directory": "cli-output", "cpus": 2,
                   "overwrite": False, "log_level": "DEBUG"},
    )
    assert effective["output"]["directory"] == str(launch / "cli-output")
    assert effective["sources"]["weather"]["files"] == str(yaml_base / "data/*.nc")
    assert effective["resources"]["cpus"] == 2
    assert effective["output"]["overwrite"] is False
    assert effective["logging"]["level"] == "DEBUG"
    assert all(origins[key] == "cli" for key in (
        "output.directory", "output.overwrite", "resources.cpus", "logging.level",
    ))
    assert origins["sources.weather.files"] == "yaml"
    assert origins["output.writer.compression.level"] == "default"
    assert raw == original
    effective, origins = configuration.resolve_operational_overrides(raw, base_dir=yaml_base)
    assert effective["output"]["directory"] == str(yaml_base / "yaml-output")
    assert effective["resources"]["cpus"] == 8
    assert origins["resources.cpus"] == origins["output.overwrite"] == "yaml"
    effective, origins = configuration.resolve_operational_overrides(document(), base_dir=yaml_base)
    assert effective["output"]["directory"] == str(yaml_base / "output")
    assert effective["output"]["overwrite"] is False
    assert "cpus" not in effective["resources"]  # Detection belongs to resource resolution.
    assert origins["output.directory"] == origins["output.overwrite"] == "default"


@pytest.mark.parametrize("overrides", [
    {"cpus": True}, {"cpus": 0}, {"overwrite": "false"}, {"log_level": "TRACE"},
    {"output_directory": ""}, {"output_directory": None}, {"scientific_selection": "T"},
])
def test_operational_overrides_validate_values_and_cannot_change_science(overrides):
    with pytest.raises(ValueError):
        configuration.resolve_operational_overrides(document(), overrides=overrides)


def test_effective_configuration_remains_v3_and_only_applies_operational_options():
    raw = document()
    raw["output"] = {"format": "zarr"}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    options = ExecutionOptions.from_config(conf, overwrite=True, compress_level=4, log_level="ERROR")
    effective = configuration.resolved_configuration(conf, options)
    assert effective["output"]["overwrite"] is True
    assert effective["output"]["writer"]["compression"]["level"] == 4
    assert effective["logging"]["level"] == "ERROR"
    assert "engine" not in effective["output"]["writer"]
    assert "unlimited_time" not in effective["output"]["writer"]
    assert resolve_schema(effective)[0] == effective
    assert configuration.resolved_sources(conf, options)["output.overwrite"] == "cli"


def test_operational_output_accepts_the_path_type_used_by_argparse(tmp_path):
    effective, origins = configuration.resolve_operational_overrides(
        document(), base_dir=tmp_path / "yaml", launch_dir=tmp_path / "launch",
        overrides={"output_directory": Path("results")},
    )
    assert effective["output"]["directory"] == str(tmp_path / "launch/results")
    assert origins["output.directory"] == "cli"


def test_time_window_order_includes_fractional_seconds():
    raw = document()
    raw["sources"]["weather"]["time"] = {
        "start": "2026-01-01T00:00:00.2", "end": "2026-01-01T00:00:00.1",
    }
    with pytest.raises(ValueError, match="sources.weather.time.start"):
        resolve_schema(raw)


def test_field_policy_can_override_a_product_renormalization_policy():
    raw = document()
    raw["region"] = {"center": {"latitude": -20, "longitude": 60}}
    raw["products"] = {"polar": {
        "radius_km": 100, "missing_data_policy": "renormalize",
        "min_valid_weight_fraction": .75,
        "field_options": {"weather": {
            "MSLP": {"interpolation": "nearest", "missing_data_policy": "strict"},
        }},
    }}
    options = resolve_schema(raw)[0]["products"]["polar"]["field_options"]["weather"]["MSLP"]
    assert options == {"interpolation": "nearest", "missing_data_policy": "strict"}


def test_unbound_execution_fails_before_claiming_output_or_loading_inputs(tmp_path):
    from frameit.core.execution import execute_simulation
    from frameit.core.reports import PreflightError, error_record

    raw = document()
    raw["sources"]["weather"]["files"] = str(tmp_path / "missing.nc")
    raw["output"] = {"directory": str(tmp_path / "output")}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="Cannot bind source requests to metadata") as exc:
        execute_simulation(conf)
    assert type(exc.value) is ValueError
    assert isinstance(exc.value.__cause__, PreflightError)
    record = error_record(exc.value)
    assert record["code"] == "E1201"
    assert [item["code"] for item in record["diagnostics"]] == ["E1201"]
    assert not conf.output_dir.exists()


def test_unbound_discovery_cannot_fall_back_to_an_invented_file_pattern(tmp_path):
    from frameit.io.loader import discover_input_files

    conf = SimulationConfig(**to_runtime(document(), base_dir=tmp_path))
    with pytest.raises(ValueError, match="bind.*source|source.*bind"):
        discover_input_files(conf)
    assert not conf.output_dir.exists()


def test_direct_numerical_constructor_retains_bound_groups_and_tracker_controls(tmp_path):
    args = {
        "simulation_name": "numerical", "file_name_prefix": "MNH.", "file_name": "",
        "file_name_suffix": ".", "file_type": "nc", "atm_model": "MNH",
        "ocean_model": "", "wave_model": "", "resolution": 2500, "comment": "",
        "simulation_output_dir": str(tmp_path), "frameit_output_dir": str(tmp_path / "out"),
        "tracking_method": "fixed_box", "fix_subdomain_center": [-20., 60.],
        "requested_variables_user": {"level": {"variables": ["UT"], "level_indices": [2, 0]}},
        "wind_pairs": [{"group": "level", "u": "UT", "v": "VT", "reference_frame": "earth"}],
    }
    conf = SimulationConfig(**args)
    assert conf.requests_user() == {"level": {"variables": ["UT"], "level_indices": [2, 0]}}
    assert conf.wind_pairs == args["wind_pairs"]
    assert conf.cartesian_horizontal_winds == "mass_earth"
    assert conf.is_mnh_timeseries_name("MNH.000.nc")


def test_all_v3_loaders_leave_dataset_and_subprocess_access_for_preflight(tmp_path, monkeypatch):
    import subprocess

    import xarray as xr

    def forbidden(*args, **kwargs):
        pytest.fail("Schema-only resolution reached input discovery, a dataset, or a decoder")

    monkeypatch.setattr(xr, "open_dataset", forbidden)
    monkeypatch.setattr("frameit.io.loader.discover_input_files", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    raw = document()
    path = tmp_path / "request.yaml"
    path.write_text(yaml.safe_dump(raw))
    resolve_schema(raw)
    to_runtime(raw)
    resolve_config_with_model_presets(raw)
    assert SimulationConfig.from_mapping_with_model_preset(raw).schema_version == 3
    assert SimulationConfig.from_yaml(path).schema_version == 3


@pytest.mark.parametrize("method,settings", [
    ("pressure_centroid", {"convergence": {"max_iterations": 5},
                          "motion": {"solver": "fixed", "relaxation": .5},
                          "sampling": {"radial_step_km": 5}}),
    ("multifield_vortex", {"seed": {"latitude": -20., "longitude": 60.,
                                   "time": "2026-01-01T00:00:00",
                                   "motion_u_m_s": 1., "motion_v_m_s": 2.},
                          "mnh_gravity_m_s2": 9.81, "on_incomplete": "keep_prefix",
                          "numerics": {"max_iterations": 10},
                          "quality": {"minimum_parameters": 3}}),
])
def test_existing_explicit_tracker_settings_roundtrip_without_executing(method, settings):
    raw = document()
    raw["region"] = {"tracker": {"method": method, **settings}}
    conf = resolve_schema(raw)[0]
    assert resolve_schema(conf)[0] == conf
    runtime = to_runtime(raw)
    assert runtime["tracking_method"] == method
    if method == "multifield_vortex":
        assert runtime["multifield_vortex"]["on_track_loss"] == "stop"
        assert not ExecutionOptions.from_config(SimulationConfig(**runtime)).require_complete_tracking


@pytest.mark.parametrize("tracker", [
    {"method": "utrack"}, {"method": "utrack", "weights_file": "x", "batch_size": True},
    {"method": "pressure_centroid", "motion": {"relaxation": 1.1}},
    {"method": "pressure_centroid", "convergence": {"max_iterations": True}},
    {"method": "pressure_centroid", "sampling": {"azimuth_step_deg": 180}},
    {"method": "multifield_vortex"},
    {"method": "multifield_vortex", "seed": {"latitude": 0., "longitude": 60.,
                                            "motion_u_m_s": 1., "motion_v_m_s": 2.}},
])
def test_method_specific_required_entries_and_numerics_are_checked(tracker):
    raw = document()
    raw["region"] = {"tracker": tracker}
    with pytest.raises(ValueError, match="region.tracker"):
        resolve_schema(raw)


def test_derived_cycles_fail_even_when_the_product_filters_out_the_result():
    raw = document()
    raw["sources"]["weather"]["derived"] = {
        "speed": {"method": "wind_speed", "inputs": {"u": "speed", "v": "VT"}},
    }
    raw["products"] = {"model_grid": {"fields": {"weather": ["MSLP"]}}}
    with pytest.raises(ValueError, match="derived.*cycle"):
        resolve_schema(raw)


@pytest.mark.parametrize("omitted", [("model",), ("format",), ("model", "format")])
def test_fa_declarations_do_not_require_guessing_an_undeclared_model_or_format(omitted):
    raw = fa_document()
    for key in omitted:
        raw["sources"]["native"].pop(key)
    resolved = resolve_schema(raw)[0]
    for key in omitted:
        assert key not in resolved["sources"]["native"]
    assert resolved["sources"]["native"]["profile"] == "arome_history"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    assert conf.sources["native"]["profile"] == "arome_history"
    assert conf.atm_model == (None if "model" in omitted else "AROME")


def test_binding_request_mutation_cannot_rewrite_the_effective_product_controls():
    raw = document()
    raw["products"] = {"model_grid": {"fields": {"weather": ["UT"]}}}
    resolved, requests, _ = resolve_schema(raw)
    requests["weather"]["exports"]["model_grid"].append("VT")
    assert resolved["products"]["model_grid"]["fields"] == {"weather": ["UT"]}
    assert raw["products"]["model_grid"]["fields"] == {"weather": ["UT"]}


def test_unquoted_yaml_timestamp_explains_the_required_string_syntax(tmp_path):
    path = tmp_path / "case.yaml"
    path.write_text(
        "schema_version: 3\nsources:\n  weather:\n    files: data.nc\n"
        "    time:\n      start: 2026-01-01T00:00:00\n"
    )
    with pytest.raises(ValueError, match="sources.weather.time.start.*quoted ISO timestamp"):
        SimulationConfig.from_yaml(path)


@pytest.mark.parametrize("missing_profile", [True, False])
def test_fa_admission_errors_point_to_v3_declarations_not_the_old_adapter_mapping(missing_profile):
    raw = fa_document()
    if missing_profile:
        raw["sources"]["native"].pop("profile")
        location = "sources.native.profile"
    else:
        raw["sources"]["native"]["fa"]["expected_source"]["VERSION"] = True
        location = "sources.native.fa.expected_source.VERSION"
    with pytest.raises(ValueError, match=location.replace(".", r"\.")) as error:
        resolve_schema(raw)
    assert "input.fa" not in str(error.value)


@pytest.mark.parametrize("with_track", [False, True])
def test_tracking_dependency_source_runtime_has_no_exports_and_keeps_origins(tmp_path, with_track):
    raw = document()
    raw["sources"]["sea"] = {
        "model": "nemo", "files": "ocean.nc", "variables": {"3d": ["temp"]},
    }
    raw["region"] = {"tracker": {"method": "pressure_wind"}}
    raw["products"] = {"model_grid": {"fields": {"sea": ["temp"]}}}
    if with_track:
        raw["products"]["track"] = True
    effective, origins = configuration.resolve_operational_overrides(
        raw, base_dir=tmp_path / "yaml", launch_dir=tmp_path / "launch",
        overrides={"output_directory": "result", "overwrite": True},
    )
    parent = SimulationConfig(**to_runtime(effective))
    parent.schema_sources = origins
    saved = parent.to_dict()
    if with_track:
        assert source_document(parent.yaml_config, "weather")["products"] == {"track": True}
    else:
        with pytest.raises(ValueError, match="not requested by any product"):
            source_document(parent.yaml_config, "weather")

    child = SimulationConfig(**configuration._source_runtime(parent, "weather"))
    assert child.source_name == "weather" and set(child.sources) == {"weather"}
    assert child.tracking_method == "wind_pressure"
    assert child.yaml_config["region"]["tracker"]["method"] == "pressure_wind"
    assert child.yaml_config["products"] == {}
    assert child.source_requests["weather"]["exports"] == {}
    assert child.simulation_parameter["request_plan"]["products"] == []
    assert child.sources["weather"]["files"] == str(tmp_path / "yaml/data/*.nc")
    assert child.frameit_output_dir == str(tmp_path / "launch/result")
    assert child.schema_sources["sources.weather.files"] == "yaml"
    assert child.schema_sources["region.tracker.search_width_km"] == "default"
    assert child.schema_sources["output.directory"] == "cli"
    assert child.schema_sources["output.overwrite"] == "cli"
    assert child.schema_sources["products"] == "automatic"
    assert not any(path.startswith("sources.sea.") for path in child.schema_sources)
    assert not any(path.startswith("products.model_grid") for path in child.schema_sources)
    options = ExecutionOptions.from_config(child)
    assert not options.export_netcdf and not options.export_cart and not options.export_polar
    with pytest.raises(ValueError, match="products"):
        resolve_schema(child.yaml_config)
    child.sources["weather"]["variables"]["2d"].append("internal_probe")
    assert parent.to_dict() == saved

    ocean = SimulationConfig(**configuration._source_runtime(parent, "sea"))
    assert ocean.source_name == "sea" and ocean.atm_model == "NEMO"
    assert ocean.source_requests["sea"]["exports"] == {"model_grid": ["temp"]}
    assert ocean.yaml_config["products"] == {"model_grid": {"fields": {"sea": ["temp"]}}}
    assert [item["path"] for item in ocean.simulation_parameter["request_plan"]["products"]] == [
        "products/analysis.sea.model_grid.nc",
    ]
    assert ocean.schema_sources["output.directory"] == "cli"
    assert ocean.schema_sources["output.writer.compression.level"] == "default"
    assert parent.to_dict() == saved


@pytest.mark.parametrize("with_seed_time", [False, True])
def test_omitted_vortex_options_reach_the_existing_numerical_tracker(with_seed_time):
    from frameit.tracking.MultifieldVortex_Tracker import MultifieldVortexTracker

    from .test_multifield_vortex import vortex

    seed = {"latitude": -20., "longitude": 60., "motion_u_m_s": 0., "motion_v_m_s": 0.}
    if with_seed_time:
        seed["time"] = "2024-01-01T00:00:00"
    raw = {
        "schema_version": 3,
        "sources": {"weather": {"model": "arome", "files": "unopened.nc"}},
        "region": {"tracker": {"method": "multifield_vortex", "seed": seed}},
        "products": {"track": True},
    }
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    # The existing in-memory fixture declares physical Earth-relative components.
    conf.wind_pairs = [
        {"group": "surface", "u": "u10", "v": "v10", "reference_frame": "earth"},
        {"group": "isobaric", "u": "u", "v": "v", "reference_frame": "earth"},
    ]
    conf.resolution = 32500
    source = vortex(model="arome")[0].isel(time=[0])
    result = MultifieldVortexTracker.from_config(conf)._track_method(source)
    assert result.sizes["time"] == 1 and result.attrs["tracking_complete"] == 1
    assert result.time.values.tolist() == source.time.values.tolist()
    assert result.attrs["multifield_mnh_gravity_m_s2"] == "not_applicable"
    assert conf.multifield_vortex["seed"]["time"] == seed.get("time")
    assert conf.multifield_vortex["mnh_gravity_m_s2"] is None
    public = conf.yaml_config["region"]["tracker"]
    assert ("time" in public["seed"]) is with_seed_time
    assert "mnh_gravity_m_s2" not in public
    assert resolve_schema(conf.yaml_config)[0] == conf.yaml_config


@pytest.mark.parametrize("route", ["runtime", "presets", "source"])
@pytest.mark.parametrize("attribute", [
    "input_exclude", "netcdf_chunks", "wind_pressure_initial_guess",
    "polar_output_chunks", "multifield_vortex",
])
def test_mutable_runtime_fields_cannot_rewrite_effective_declarations(route, attribute):
    raw = document()
    raw["sources"]["weather"].update(
        format="netcdf", exclude=["skip*.nc"], reader={"chunks": {"time": 1}},
    )
    tracker = {"method": "pressure_wind", "initial_guess": {
        "latitude": -20., "longitude": 60., "search_radius_km": 100,
    }}
    if attribute == "multifield_vortex":
        tracker = {"method": "multifield_vortex", "seed": {
            "latitude": -20., "longitude": 60., "motion_u_m_s": 0., "motion_v_m_s": 0.,
        }}
    raw["region"] = {"tracker": tracker}
    raw["products"] = {
        "model_grid": True, "polar": {"radius_km": 100, "processing": {"chunks": {"time": 1}}},
    }
    parent = None
    if route == "source":
        raw["sources"]["sea"] = {
            "model": "nemo", "files": "ocean.nc", "variables": {"3d": ["temp"]},
        }
        parent = SimulationConfig(**to_runtime(raw))
        parent_saved = parent.to_dict()
        conf = SimulationConfig(**configuration._source_runtime(parent, "weather"))
    elif route == "presets":
        conf = SimulationConfig.from_mapping_with_model_preset(raw)
    else:
        conf = SimulationConfig(**to_runtime(raw))
    saved_yaml = copy.deepcopy(conf.yaml_config)
    saved_sources = copy.deepcopy(conf.sources)
    saved_plan = copy.deepcopy(conf.simulation_parameter["request_plan"])
    saved_origins = copy.deepcopy(conf.schema_sources)

    if attribute == "input_exclude":
        conf.input_exclude.append("runtime-only.nc")
    elif attribute == "wind_pressure_initial_guess":
        conf.wind_pressure_initial_guess["latitude"] = -21.
    elif attribute == "multifield_vortex":
        conf.multifield_vortex["numerics"]["max_iterations"] = 99
        conf.multifield_vortex["quality"]["minimum_parameters"] = 3
        conf.multifield_vortex["seed"]["longitude"] = 61.
    else:
        getattr(conf, attribute)["time"] = 7

    assert conf.yaml_config == saved_yaml
    assert conf.sources == saved_sources
    assert conf.simulation_parameter["request_plan"] == saved_plan
    assert conf.schema_sources == saved_origins
    if parent is not None:
        assert parent.to_dict() == parent_saved


@pytest.mark.parametrize("route", ["config", "overrides", "constructor", "replace"])
def test_execution_options_own_their_mutable_layouts(route):
    from dataclasses import replace

    raw = document()
    raw["output"] = {"format": "zarr", "writer": {
        "chunks": {"time": 2}, "shards": {"time": 4},
    }}
    conf = SimulationConfig(**to_runtime(raw))
    saved_yaml = copy.deepcopy(conf.yaml_config)
    saved_origins = dict(conf.schema_sources)
    chunks, shards = {"time": 2}, {"time": 4}
    original = None
    if route == "config":
        options = ExecutionOptions.from_config(conf)
    elif route == "overrides":
        options = ExecutionOptions.from_config(conf, zarr_chunk_size=chunks, zarr_shard_size=shards)
    elif route == "constructor":
        options = ExecutionOptions(engine="zarr", zarr_chunk_size=chunks, zarr_shard_size=shards)
    else:
        original = ExecutionOptions.from_config(conf)
        options = replace(original)
    peer = ExecutionOptions.from_config(conf)

    options.zarr_chunk_size["time"] = 4
    options.zarr_shard_size["time"] = 8

    assert conf.yaml_config == saved_yaml
    assert conf.schema_sources == saved_origins
    assert peer.zarr_chunk_size == {"time": 2} and peer.zarr_shard_size == {"time": 4}
    assert chunks == {"time": 2} and shards == {"time": 4}
    if original is not None:
        assert original.zarr_chunk_size == {"time": 2} and original.zarr_shard_size == {"time": 4}
