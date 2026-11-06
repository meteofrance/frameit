"""Strict public configuration and core metadata regressions."""

from __future__ import annotations

from pathlib import Path

import dask.array as da
import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.cli import _build_parser, main
from frameit.core.configuration import resolve_schema, to_runtime, write_template
from frameit.core.execution import ExecutionOptions
from frameit.core.grid_geometry import inspect_grid
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import discover_input_files
from frameit.processing.derived.wind import polar_wind_components
from frameit.processing.polar.polar_utils import ensure_theta_rad_dim
from frameit.utils.units import convert_units


def minimal_document():
    return {"schema_version": "2.1", "model": "arome",
            "input": {"pattern": "*.nc", "format": "netcdf"},
            "tracking": {"method": "fixed_box", "fixed_box": {
                "center": {"latitude": -20., "longitude": 60.}}},
            "variables": {"fields_2d": {"names": ["instructional_scalar"]}},
             "output": {"directory": "./products", "overwrite": False}}


def test_fields_2d_translates_without_renaming_scientific_products(tmp_path):
    raw = minimal_document()
    raw["variables"] = {"fields_2d": {"names": ["instructional_scalar"]}}
    raw["polar"] = {"variables": {"fields_2d": {"names": ["instructional_scalar"]}}}
    raw["input"]["wind_pairs"] = [
        {"group": "fields_2d", "u": "u10", "v": "v10", "reference_frame": "earth"}]
    runtime = to_runtime(raw, base_dir=tmp_path)
    assert runtime["requested_variables_user"] == {
        "surface": {"variables": ["instructional_scalar"],
                    "level_selection": "stored", "level_domain": "stored"}}
    assert runtime["polar_variables"] == {"surface": {"variables": ["instructional_scalar"]}}
    assert runtime["wind_pairs"][0]["group"] == "surface"
    assert set(runtime["yaml_config"]["variables"]) == {"fields_2d"}
    assert runtime["yaml_config"]["input"]["wind_pairs"][0]["group"] == "fields_2d"
    replay = to_runtime(runtime["yaml_config"], base_dir=tmp_path)
    assert replay["requested_variables_user"] == runtime["requested_variables_user"]


@pytest.mark.parametrize("location", ["variables", "polar", "wind_pairs", "source"])
def test_public_surface_group_is_rejected_actionably(tmp_path, location):
    raw = minimal_document()
    raw["variables"] = {"fields_2d": {"names": ["instructional_scalar"]}}
    if location == "variables":
        raw["variables"] = {"surface": {"names": ["instructional_scalar"]}}
    elif location == "polar":
        raw["polar"] = {"variables": {"surface": {"names": ["instructional_scalar"]}}}
    elif location == "wind_pairs":
        raw["input"]["wind_pairs"] = [
            {"group": "surface", "u": "u10", "v": "v10", "reference_frame": "earth"}]
    else:
        raw["input"] = {"sources": {"atmosphere": {
            "model": "arome", "input": {"format": "netcdf", "pattern": "*.nc"},
            "variables": {"surface": {"names": ["instructional_scalar"]}}}}}
        raw["variables"] = {}
        raw["tracking"]["source"] = "atmosphere"
    with pytest.raises(ValueError, match="fields_2d"):
        resolve_schema(raw, base_dir=tmp_path)
    assert not (tmp_path / "products").exists()


def test_fields_2d_fa_selection_retains_internal_record_group(tmp_path):
    raw = minimal_document()
    raw["input"].update(format="fa", pattern="*.fa", fa={"profile": "arome_history"})
    raw["variables"] = {"fields_2d": {"names": ["CLSTEMPERATURE"]}}
    runtime = to_runtime(raw, base_dir=tmp_path)
    assert set(runtime["requested_variables_user"]) == {"surface"}
    assert set(runtime["yaml_config"]["variables"]) == {"fields_2d"}


def test_current_string_schema_preserves_numerical_requests(tmp_path):
    raw = minimal_document()
    raw["tracking"] = {"method": "pressure_wind", "pressure_wind": {
        "search_half_width_km": 75., "refine_half_width_km": 25.}}
    raw["domain"] = {"width_km": {"x": 4., "y": 6.}}
    raw["polar"] = {"variables": "extracted"}
    raw["output"].update(backend="zarr", export={"enabled": False},
                         cartesian={"horizontal_vectors": "earth_centered"})
    runtime = to_runtime(raw, base_dir=tmp_path)
    assert runtime["schema_version"] == "2.1"
    assert runtime["tracking_method"] == "wind_pressure"
    assert runtime["wind_pressure_search_half_width_km"] == 75.
    assert runtime["wind_pressure_refine_half_width_km"] == 25.
    assert (runtime["x_boxsize_km"], runtime["y_boxsize_km"]) == (4., 6.)
    assert runtime["cartesian_horizontal_winds"] == "mass_earth"
    assert runtime["requested_variables_user"]["surface"]["variables"] == ["instructional_scalar"]
    assert runtime["requested_variables_user"]["surface"]["level_domain"] == "stored"
    assert runtime["polar_variables"] == {"surface": {"variables": ["instructional_scalar"]}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    options = ExecutionOptions.from_config(conf)
    assert options.engine == "zarr" and not options.export_netcdf
    assert conf.wind_pairs == [] and conf.wind_reference_frame is None


@pytest.mark.parametrize("version", [None, 1, 2, "1", "2", "2.0", 2.1, True, False, "9", "2.1.0"])
@pytest.mark.parametrize("route", ["resolve", "runtime", "mapping", "presets", "yaml", "yaml_preset"])
def test_every_public_loader_rejects_retired_versions_before_access(tmp_path, monkeypatch, version, route):
    import subprocess

    from frameit.io import loader

    def forbidden(*args, **kwargs):
        pytest.fail("Retired public configuration reached dataset access")

    monkeypatch.setattr(xr, "open_dataset", forbidden)
    monkeypatch.setattr(loader, "discover_input_files", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    raw = minimal_document()
    if version is None:
        raw.pop("schema_version")
    else:
        raw["schema_version"] = version
    path = tmp_path / "retired.yaml"
    path.write_text(yaml.safe_dump(raw))
    calls = {"resolve": lambda: resolve_schema(raw), "runtime": lambda: to_runtime(raw),
             "mapping": lambda: SimulationConfig.from_mapping_with_model_preset(raw),
             "presets": lambda: loader.resolve_config_with_model_presets(raw),
             "yaml": lambda: SimulationConfig.from_yaml(path),
             "yaml_preset": lambda: SimulationConfig.from_yaml_with_model_preset(path)}
    with pytest.raises(ValueError, match="schema_version") as error:
        calls[route]()
    assert '"2.1"' in str(error.value)
    assert 'upgrade' not in str(error.value).lower()
    assert not (tmp_path / "products").exists()


@pytest.mark.parametrize("route", ["mapping", "presets", "yaml"])
def test_flat_public_documents_cannot_use_runtime_dispatch(tmp_path, route):
    from frameit.io.loader import resolve_config_with_model_presets

    raw = {"atm_model": "AROME", "simulation_output_dir": str(tmp_path),
           "frameit_output_dir": str(tmp_path / "out"), "tracking_method": "fixed_box"}
    path = tmp_path / "flat.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="schema_version"):
        if route == "mapping":
            SimulationConfig.from_mapping_with_model_preset(raw)
        elif route == "presets":
            resolve_config_with_model_presets(raw)
        else:
            SimulationConfig.from_yaml(path)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("path,value", [
    (("domain", "size_km"), {"x": 4, "y": 4}),
    (("tracking", "method"), "wind_pressure"),
    (("tracking", "wind_pressure"), {}),
    (("input", "wind_reference_frame"), "earth"),
    (("input", "fa", "backend"), "native"),
    (("polar", "variables"), "all"),
    (("variables", "fields_2d", "levels"), "all"),
    (("output", "engine"), "zarr"),
    (("output", "format"), "NETCDF4"),
    (("output", "export", "netcdf"), False),
    (("output", "cartesian", "horizontal_winds"), "native"),
    (("output", "cartesian", "horizontal_vectors"), "mass_earth"),
])
def test_retired_keys_and_values_fail_in_current_document(path, value):
    raw = minimal_document()
    target = raw
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value
    with pytest.raises(ValueError, match=path[-1]):
        resolve_schema(raw)


@pytest.mark.parametrize("change", [
    {"input": {"pattern": "*.nc", "exclude": None}},
    {"input": {"pattern": "*.nc", "files": []}},
    {"variables": {"fields_2d": {"names": [""]}}},
    {"variables": {"fields_2d": {"names": [" "]}}},
    {"variables": {1: {"names": ["scalar"]}}},
    {"output": {"backend": "zarr", "netcdf_format": "unused"}},
    {"input": {"pattern": "*.nc", "netcdf": {"chunks": {1: 2}}}},
    {"input": {"pattern": "*.nc", 1: "invalid"}},
    {"polar": {"variables": {"fields_2d": {"names": ["instructional_scalar"], "levels": "stored"}}}},
])
def test_current_schema_rejects_invalid_dynamic_declarations(change):
    raw = minimal_document()
    raw.update(change)
    with pytest.raises(ValueError):
        resolve_schema(raw)


def test_named_sources_inherit_only_declared_polar_settings_and_replay(tmp_path):
    from frameit.core.configuration import resolved_configuration, source_document

    raw = minimal_document()
    raw.pop("variables")
    raw["tracking"]["source"] = "atmosphere"
    raw["input"] = {"time_alignment": "common", "sources": {
        "atmosphere": {"model": "arome", "input": {"files": ["atmosphere.nc"], "format": "netcdf"},
                       "variables": {"fields_2d": {"names": ["scalar"]}}},
        "ocean": {"model": "nemo", "input": {"files": ["ocean.nc"], "format": "netcdf"},
                  "variables": {"deptht": {"names": ["votemper"], "levels": {"indices": [1, 0]}}},
                  "polar": {"azimuth_count": 8}}}}
    raw["polar"] = {"enabled": False, "radial_step_m": 3000.}
    resolved, _, _ = resolve_schema(raw, base_dir=tmp_path)
    for name in ("atmosphere", "ocean"):
        source = resolved["input"]["sources"][name]
        assert source["input"]["files"] == [str(tmp_path / f"{name}.nc")]
        assert source["polar"]["radial_step_m"] == 3000.
        child = source_document(resolved, name)
        assert child["schema_version"] == "2.1"
        resolve_schema(child, base_dir=tmp_path)
    assert resolved["input"]["sources"]["ocean"]["polar"]["azimuth_count"] == 8
    assert resolved["input"]["sources"]["atmosphere"]["polar"]["azimuth_count"] is None
    config = SimulationConfig.from_mapping_with_model_preset(resolved)
    replay = resolved_configuration(config)
    assert resolve_schema(replay)[0] == replay
    declared = SimulationConfig.from_mapping_with_model_preset(raw)
    assert declared.schema_sources["input.sources.ocean.polar.radial_step_m"] == "yaml"
    assert declared.schema_sources["input.sources.ocean.polar.azimuth_count"] == "yaml"
    assert declared.schema_sources["input.sources.atmosphere.polar.azimuth_count"] == "default"
    for key, value in (("time_alignment", "common"), ("sources", {})):
        bad = yaml.safe_load(yaml.safe_dump(raw))
        bad["input"]["sources"]["ocean"]["input"][key] = value
        with pytest.raises(ValueError, match=key):
            resolve_schema(bad)


def test_effective_record_preserves_unresolved_automatic_spacing(tmp_path):
    from frameit.core.configuration import resolved_configuration

    conf = SimulationConfig.from_mapping_with_model_preset(minimal_document())
    effective = resolved_configuration(conf)
    assert effective["input"]["grid_spacing_m"] is None
    assert resolve_schema(effective)[0] == effective


def test_current_cli_exposes_unambiguous_export_controls_and_no_converter():
    parser = _build_parser()
    args = parser.parse_args(["run", "--no-export", "--no-export-cartesian"])
    assert not args.export_netcdf and not args.export_cart
    for retired in (["run", "--no-export-netcdf"], ["run", "--no-export-cart"],
                    ["config", "migrate", "old.yaml"]):
        with pytest.raises(SystemExit) as result:
            parser.parse_args(retired)
        assert result.value.code == 2


def test_catalog_emits_current_requests_without_legacy_conversion():
    from frameit.testing.catalog import load_cases

    cases = load_cases()
    assert all(case["config"].get("schema_version") == "2.1" for case in cases)
    case = next(case for case in cases if case["id"] == "arome_batsirai_fixed_polar")
    conf = SimulationConfig.from_mapping_with_model_preset(case["config"])
    assert conf.requests_user()["isobaricInhPa"]["level_values"] == [1000, 850, 400]
    assert conf.requests_user()["heightAboveGround"]["level_indices"] == [0, 2, 5]
    assert conf.requests_user()["surface"]["variables"] == ["u10", "v10", "prmsl", "sshf", "slhf"]
    assert conf.resolution == 2500 and conf.radial_resolution == 2500
    assert conf.polar_n_theta is None and conf.azimuthal_resolution == 10


def document(tmp_path, **sections):
    # This synthetic fixture defines UM10/VM10 as Earth-relative components.
    wind_pairs = [{"group": "fields_2d", "u": "UM10", "v": "VM10", "reference_frame": "earth"}]
    value = {"schema_version": "2.1", "model": "mesonh",
             "input": {"directory": str(tmp_path), "pattern": "*.nc", "wind_pairs": wind_pairs},
             "output": {"directory": str(tmp_path / "output")},
             "tracking": {"method": "fixed_box", "fixed_box": {
                 "center": {"latitude": -20., "longitude": 60.}}},
             "variables": {"fields_2d": {"names": ["UM10", "VM10", "MSLP"]}}}
    value.update(sections)
    value["input"].setdefault("wind_pairs", wind_pairs)
    return value


def dataset(tmp_path, name="native.nc", *, dx=2500, dy=2500, units="m s-1", speed=10.):
    n = 17
    # Geographic regional square grid plus reliable projected native coordinates.
    lon, lat = np.meshgrid(60 + (np.arange(n) - n // 2) * .024,
                          -20 + (np.arange(n) - n // 2) * .0225)
    shape = (2, n, n)
    ds = xr.Dataset({
        "UM10": (("time", "nj", "ni"), np.full(shape, speed), {"units": units}),
        "VM10": (("time", "nj", "ni"), np.zeros(shape), {"units": units}),
        "MSLP": (("time", "nj", "ni"), np.full(shape, 100000.), {"units": "Pa"}),
        "temperature": (("time", "nj", "ni"), np.full(shape, 300.), {"units": "K"}),
    }, coords={"time": np.array(["2022-02-01", "2022-02-01T01:00"], dtype="datetime64[ns]"),
               "ni": ("ni", np.arange(n) * dx, {"units": "m"}),
               "nj": ("nj", np.arange(n) * dy, {"units": "m"}),
               "longitude": (("nj", "ni"), lon, {"units": "degrees_east"}),
               "latitude": (("nj", "ni"), lat, {"units": "degrees_north"})})
    ds.to_netcdf(tmp_path / name, engine="h5netcdf")
    return ds


@pytest.mark.parametrize("model", ["arome", "mesonh"])
def test_model_starter_loads_runtime_defaults(tmp_path, model):
    path = tmp_path / "frameit.yaml"
    write_template(model, path)
    conf = SimulationConfig.from_yaml(path)
    assert conf.schema_version == "2.1" and conf.infer_grid_geometry
    assert conf.resolution == 0
    assert conf.tracking_method == "wind_pressure"
    assert conf.data_dir == tmp_path / "data"
    assert conf.wind_pairs == [{"group": "surface", "u": "u10" if model == "arome" else "UM10",
                                "v": "v10" if model == "arome" else "VM10",
                                "reference_frame": "earth"}]
    assert conf.cartesian_horizontal_winds == "mass_earth"
    assert conf.cartesian_vertical_velocity == "interfaces"
    assert conf.polar_vertical_velocity == "mass"
    with pytest.raises(FileExistsError):
        write_template(model, path)


@pytest.mark.parametrize("section", [
    {"polar": {"radial_step_m": "2500"}}, {"polar": {"enabled": "false"}},
    {"polar": {"azimuth_count": 64, "azimuth_step_deg": 10}},
    {"domain": {"width_km": {"x": 500}}}, {"domain": {"width_km": {"x": -1, "y": 50}}},
    {"output": {"compression": {"level": 10}}}, {"logging": {"levle": "INFO"}},
    {"input": {"pattern": "*.nc", "files": ["native.nc"]}},
    {"variables": {"level": {"names": ["UT"], "levels": {"indices": [-1]}}}},
    {"variables": {"level": {"names": ["UT"], "levels": {"indices": [0], "values": [1]}}}},
    {"polar": {"enabled": True}}, {"tracking": None},
])
def test_schema_rejects_ambiguous_or_invalid_values(tmp_path, section):
    with pytest.raises(ValueError):
        resolve_schema(document(tmp_path, **section))


def test_yaml_duplicates_unknown_locations_and_legacy_rejection(tmp_path):
    path = tmp_path / "frameit.yaml"
    path.write_text('schema_version: "2.1"\nmodel: arome\nmodel: mesonh\n')
    with pytest.raises(ValueError, match="Duplicate.*line 3"):
        SimulationConfig.from_yaml(path)
    path.write_text('schema_version: "2.1"\nmodel: arome\ninput:\n  patten: \'*.nc\'\n')
    with pytest.raises(ValueError, match="input.patten") as error:
        SimulationConfig.from_yaml(path)
    assert "line 4" in str(error.value)
    path.write_text("atm_model: AROME\nresolution: 2500\n")
    with pytest.raises(ValueError, match="schema_version"):
        SimulationConfig.from_yaml(path)


def test_inventory_order_exclusion_and_config_relative_paths(tmp_path, monkeypatch):
    for name in ("a.nc", "b.nc", "000.nc"):
        dataset(tmp_path, name)
    path = tmp_path / "frameit.yaml"
    raw = document(tmp_path, input={"files": ["b.nc", "a.nc", "000.nc"], "exclude": ["000.nc"]})
    path.write_text(yaml.safe_dump(raw))
    monkeypatch.chdir(tmp_path.parent)
    conf = SimulationConfig.from_yaml(path)
    assert [p.name for p in discover_input_files(conf)] == ["b.nc", "a.nc"]
    assert conf.data_dir == tmp_path / "data"  # Default directory need not contain explicit files.


def test_preflight_inference_units_defaults_and_no_outputs(tmp_path):
    dataset(tmp_path)
    raw = document(tmp_path, domain={"width_km": {"x": 20, "y": 20}},
                   polar={"enabled": True, "azimuth_count": 16})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan = preflight(conf)
    assert conf.resolution == 2500 and conf.radial_resolution == 2500
    assert plan["grid_geometry"]["sources"] == [
        "projected_coordinate:ni", "projected_coordinate:nj"
    ]
    assert plan["polar_sampling"]["estimated_points_per_time"] == 5 * 16
    assert plan["box_points"] == [9, 9]
    assert not conf.output_dir.exists()
    assert len(plan["unit_provenance"]) > 0


def test_geometry_rejects_anisotropy_and_conflicting_inputs(tmp_path):
    dataset(tmp_path, dx=4000)
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path))
    with pytest.raises(ValueError, match="Anisotropic"):
        preflight(conf)
    dataset(tmp_path)
    ds = dataset(tmp_path, "second.nc")
    ds = ds.assign_coords(longitude=ds.longitude + .1)
    ds.to_netcdf(tmp_path / "second.nc", engine="h5netcdf")
    with pytest.raises(ValueError, match="incompatible"):
        preflight(conf)


def test_geodesic_and_projected_unit_equivalence(tmp_path):
    ds = dataset(tmp_path)
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path))
    baseline = inspect_grid(ds, conf)
    converted = ds.assign_coords(
        ni=ds.ni / 1000, nj=ds.nj / 1000,
        latitude=np.deg2rad(ds.latitude), longitude=np.deg2rad(ds.longitude),
    )
    for name in ("ni", "nj"):
        converted[name].attrs["units"] = "km"
    for name in ("latitude", "longitude"):
        converted[name].attrs["units"] = "rad"
    result = inspect_grid(converted, conf)
    assert result["x"]["spacing_m"] == baseline["x"]["spacing_m"]
    np.testing.assert_allclose(result["sample_lat"], baseline["sample_lat"])
    geographic = ds.copy()
    geographic.ni.attrs = geographic.nj.attrs = {}
    result = inspect_grid(geographic, conf)
    assert result["sources"] == ["geodesic:WGS84"] * 2
    assert 2400 < result["x"]["spacing_m"] < 2600


@pytest.mark.parametrize(
    "units,factor", [("m s-1", 1), ("km/h", 3.6), ("knots", 1 / .5144444444444445)]
)
def test_lazy_wind_and_angle_equivalence(units, factor):
    u = xr.DataArray(
        da.from_array([10. * factor, 20. * factor], chunks=1), dims="theta", attrs={"units": units}
    )
    v = xr.zeros_like(u)
    bearing = xr.DataArray([0., 90.], dims="theta", attrs={"units": "degree"})
    radial, tangential = polar_wind_components(u, v, bearing)
    assert isinstance(radial.data, da.Array)
    np.testing.assert_allclose(radial.compute(), [0, 20], atol=1e-12)
    np.testing.assert_allclose(tangential.compute(), [10, 0], atol=1e-12)
    normalized = convert_units(u, "velocity")
    xr.testing.assert_identical(normalized, convert_units(normalized, "velocity"))


def test_radius_metadata_converts_values_and_detects_disagreement():
    ds = xr.Dataset(coords={"rr": ("rr", [0., 1000.], {"units": "m"}),
                            "rr_km": ("rr", [0., 1.], {"units": "km"}),
                            "theta": ("theta", [0., 90.], {"units": "degree"})})
    normalized = ensure_theta_rad_dim(ds)
    np.testing.assert_allclose(normalized.rr, [0, 1])
    np.testing.assert_allclose(normalized.theta, [0, np.pi / 2])
    with pytest.raises(ValueError, match="disagree"):
        ensure_theta_rad_dim(ds.assign_coords(rr_km=("rr", [0., 2.])))
    with pytest.raises(ValueError, match="unsupported"):
        convert_units(xr.DataArray([1], attrs={"units": "K"}), "velocity")


def test_pressure_height_canonical_equivalence():
    from frameit.tracking.pressure_centroid import interpolate_to_height

    legacy = {"pressure_levels": [900., 700.], "z": np.array([[[1000.]], [[3000.]]]),
              "u": np.array([[[10.]], [[20.]]]), "v": np.zeros((2, 1, 1))}
    canonical = {**legacy, "pressure_levels_pa": [90000., 70000.]}
    a, b = interpolate_to_height(legacy), interpolate_to_height(canonical)
    np.testing.assert_allclose(a["p"] * 100, b["p"])
    np.testing.assert_allclose(a["u"], b["u"])


def test_unit_boundary_angle_consistency_and_grid_rotation(tmp_path):
    from frameit.processing.derived.wind import normalize_winds

    ds = xr.Dataset(coords={
        "theta_deg": ("theta_deg", [0., np.pi / 2], {"units": "rad"}),
        "theta": ("theta_deg", [0., np.pi / 2], {"units": "rad"}),
    })
    result = ensure_theta_rad_dim(ds)
    np.testing.assert_allclose(result.theta_deg, [0, 90])
    with pytest.raises(ValueError, match="disagree"):
        ensure_theta_rad_dim(ds.assign_coords(theta=("theta_deg", [0., .1])))
    winds = xr.Dataset({"UM10": xr.DataArray(10., attrs={"units": "m/s"}),
                        "VM10": xr.DataArray(0., attrs={"units": "m/s"})},
                       coords={"grid_rotation": xr.DataArray(90., attrs={"units": "degree"})},
                       attrs={"wind_reference_frame": "grid"})
    raw = document(tmp_path)
    raw["input"]["wind_pairs"] = [{"group": "fields_2d", "u": "UM10", "v": "VM10",
                                    "reference_frame": "grid", "rotation": {
                                        "method": "coordinate", "coordinate": "grid_rotation"}}]
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = normalize_winds(winds, conf, "surface")
    np.testing.assert_allclose(result.UM10, 0, atol=1e-12)
    np.testing.assert_allclose(result.VM10, 10, atol=1e-12)


def test_time_dependent_geometry_and_override_contract(tmp_path):
    ds = dataset(tmp_path)
    changing = ds.assign_coords(longitude=ds.longitude.expand_dims(time=ds.time).copy())
    changing["longitude"][1] = changing.longitude[1] + .01
    changing.to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path))
    with pytest.raises(ValueError, match="incompatible"):
        preflight(conf)
    dataset(tmp_path)
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, input={
        "directory": str(tmp_path), "pattern": "*.nc", "grid_spacing_m": 2600}))
    assert preflight(conf)["grid_geometry"]["effective_source"] == "input.grid_spacing_m"
    assert conf.resolution == 2600


def test_spacing_argument_deprecation_preserves_metres():
    from frameit.tracking.PressureWind_Tracker import PressureWindTracker

    with pytest.warns(DeprecationWarning, match="metres"):
        old = PressureWindTracker({}, resolution_km=2500)
    new = PressureWindTracker({}, grid_spacing_m=2500)
    assert old.half_search_indices == new.half_search_indices == 40
    tuned = PressureWindTracker({}, 2500, search_half_width_km=75, refine_half_width_km=25)
    assert tuned.half_search_indices == 30 and tuned.half_refine_indices == 10
    with pytest.raises(ValueError, match="both"):
        PressureWindTracker({}, grid_spacing_m=2500, resolution_km=2500)


def test_pressure_wind_direct_call_normalizes_components_before_minimum():
    from frameit.tracking.PressureWind_Tracker import pressure_wind_tracker

    mslp = xr.DataArray(np.full((1, 3, 3), 100000.), dims=("time", "y", "x"),
                        coords={"time": [0]})
    mslp[0, 1, 1] = 99000
    u = xr.full_like(mslp, 30.)
    v = xr.zeros_like(mslp)
    u[0, 1, 1], u[0, 1, 2] = 10., 0.
    v[0, 1, 2] = 20.
    u.attrs["units"], v.attrs["units"] = "m/s", "km/h"
    cy, cx = pressure_wind_tracker(mslp, u, v, half_search=1, half_refine=1)
    # 20 km/h is 5.56 m/s, physically calmer than the 10 m/s candidate.
    assert cy.item() == 1 and cx.item() == 2


def test_prescribed_track_radians_preflight_and_tracking_without_polar(tmp_path):
    from frameit.core.runner import FrameitRunner

    ds = dataset(tmp_path)
    path = tmp_path / "track.nc"
    xr.Dataset({
        "lat": ("time", np.deg2rad([-20., -20.]), {"units": "rad"}),
        "lon": ("time", np.deg2rad([60., 60.]), {"units": "rad"}),
    }, coords={"time": ds.time}).to_netcdf(path, engine="h5netcdf")
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, input={
        "files": [str(tmp_path / "native.nc")]}, tracking={
        "method": "prescribed_track", "prescribed_track": {"file": str(path)}},
        domain={"width_km": {"x": 20, "y": 20}}))
    plan = preflight(conf)
    assert plan["track_time_count"] == 2
    assert any(r["source_units"] == "rad" for r in plan["unit_provenance"])
    # Explicit inventories do not require the unused default ./data directory.
    with FrameitRunner(conf) as runner:
        runner.run()
        np.testing.assert_allclose(runner.track.lat, -20.)
        np.testing.assert_allclose(runner.track.lon, 60.)
    missing = xr.Dataset(coords={"time": ds.time})
    missing.to_netcdf(path, engine="h5netcdf")
    with pytest.raises(ValueError, match="one-dimensional"):
        preflight(conf)


def test_cli_dry_run_options_and_no_products(tmp_path, capsys):
    dataset(tmp_path)
    path = tmp_path / "frameit.yaml"
    path.write_text(yaml.safe_dump(document(tmp_path)))
    with pytest.raises(SystemExit) as result:
        main(["run", str(path), "--dry-run", "--no-export", "--compress-level", "0"])
    assert result.value.code == 0
    plan = yaml.safe_load(capsys.readouterr().out)
    assert plan["planned_products"] == []
    assert plan["configuration"]["output"]["compression"]["level"] == 0
    assert plan["configuration"]["input"]["format"] == "netcdf"
    assert plan["setting_sources"]["output.compression.level"] == "execution_override"
    assert not (tmp_path / "output").exists()


def test_cli_yaml_precedence_and_optional_config(tmp_path):
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, output={
        "directory": str(tmp_path / "out"), "export": {"polar": False},
        "compression": {"level": 4}}))
    args = _build_parser().parse_args(["run"])
    assert args.config == Path("frameit.yaml")
    assert args.compress_level is None and args.export_polar is None
    options = ExecutionOptions.from_config(
        conf, compress_level=args.compress_level, export_polar=args.export_polar
    )
    assert options.compress_level == 4 and not options.export_polar
    assert ExecutionOptions.from_config(conf, compress_level=0, export_polar=True).export_polar
    path = tmp_path / "frameit.yaml"
    path.write_text(yaml.safe_dump(document(tmp_path)))
    with pytest.raises(SystemExit) as result:
        main(["validate", str(path), "--schema-only"])
    assert result.value.code == 0
