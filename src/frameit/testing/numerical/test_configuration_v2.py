"""Schema, migration, scientific unit equivalence, and real pipeline regressions."""

from __future__ import annotations

from pathlib import Path

import dask.array as da
import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.cli import _build_parser, main
from frameit.core.configuration import migrate_mapping, resolve_schema, write_template
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.grid_geometry import inspect_grid
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import discover_input_files
from frameit.processing.derived.wind import polar_wind_components
from frameit.processing.polar.polar_utils import ensure_theta_rad_dim
from frameit.utils.units import convert_units


def document(tmp_path, **sections):
    value = {"schema_version": 2, "model": "mesonh",
             "input": {"directory": str(tmp_path), "pattern": "*.nc"},
             "output": {"directory": str(tmp_path / "output")},
             "tracking": {"method": "fixed_box", "fixed_box": {
                 "center": {"latitude": -20., "longitude": 60.}}},
             "variables": {"surface": {"names": ["UM10", "VM10", "MSLP"]}}}
    value.update(sections)
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
@pytest.mark.parametrize("full", [False, True])
@pytest.mark.parametrize(
    "method", ["wind_pressure", "fixed_box", "prescribed_track", "utrack", "pressure_centroid"]
)
def test_generated_templates(tmp_path, model, full, method):
    path = tmp_path / "frameit.yaml"
    if model == "mesonh" and method == "pressure_centroid":
        with pytest.raises(ValueError, match="arome"):
            write_template(model, path, full=full, tracking=method)
        return
    write_template(model, path, full=full, tracking=method)
    conf = SimulationConfig.from_yaml(path)
    assert conf.schema_version == 2 and conf.infer_grid_geometry
    assert conf.resolution == 0
    assert conf.tracking_method == method
    assert conf.data_dir == tmp_path / "data"
    with pytest.raises(FileExistsError):
        write_template(model, path)


@pytest.mark.parametrize("section", [
    {"polar": {"radial_step_m": "2500"}}, {"polar": {"enabled": "false"}},
    {"polar": {"azimuth_count": 64, "azimuth_step_deg": 10}},
    {"domain": {"size_km": {"x": 500}}}, {"domain": {"size_km": {"x": -1, "y": 50}}},
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
    path.write_text("schema_version: 2\nmodel: arome\nmodel: mesonh\n")
    with pytest.raises(ValueError, match="Duplicate.*line 3"):
        SimulationConfig.from_yaml(path)
    path.write_text("schema_version: 2\nmodel: arome\ninput:\n  patten: '*.nc'\n")
    with pytest.raises(ValueError, match="input.patten") as error:
        SimulationConfig.from_yaml(path)
    assert "line 4" in str(error.value)
    path.write_text("atm_model: AROME\nresolution: 2500\n")
    with pytest.raises(ValueError, match="config migrate"):
        SimulationConfig.from_yaml(path)


def test_migration_preserves_patterns_paths_and_physical_values(tmp_path):
    old = {"atm_model": "MNH", "simulation_name": "test", "file_name_prefix": "3",
           "file_name": "CH09.1.MXX30.", "file_name_suffix": "diag.", "file_type": "nc",
           "resolution": 2500, "simulation_output_dir": "data", "frameit_output_dir": "out",
           "tracking_method": "wind_pressure", "x_boxsize_km": 500, "y_boxsize_km": 400,
           "requested_variables_user": {"level": {
               "variables": ["UT"], "level_selection": "indices", "level_indices": [0, 2]}},
           "radial_resolution": 5000, "azimuthal_resolution": 10,
           "field_orientation": "geodesic",
           "simulation_parameter": {"author": "test", "preset_model_used": "MNH"}}
    c, reports = migrate_mapping(old, launch_dir=tmp_path)
    assert c["input"]["pattern"] == "3CH09.1.MXX30.???diag.nc"
    assert c["input"]["exclude"] == ["3CH09.1.MXX30.000diag.nc"]
    assert c["input"]["directory"] == str(tmp_path / "data")
    assert c["input"]["grid_spacing_m"] == 2500
    assert c["polar"]["radial_step_m"] == 5000
    assert c["variables"]["level"]["levels"] == {"indices": [0, 2]}
    assert c["metadata"]["extra"] == {"author": "test"}
    assert any("field_orientation" in r for r in reports)


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
    raw = document(tmp_path, domain={"size_km": {"x": 20, "y": 20}},
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
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path))
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


def test_all_shipped_example_yaml_uses_new_schema():
    root = Path(__file__).parents[4]
    paths = list((root / "example").rglob("*.yml"))
    assert paths
    for path in paths:
        assert SimulationConfig.from_yaml(path).schema_version == 2


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
        domain={"size_km": {"x": 20, "y": 20}}))
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
        main(["run", str(path), "--dry-run", "--no-export-netcdf", "--compress-level", "0"])
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


def test_new_yaml_real_pipeline_exports_and_replay(tmp_path):
    dataset(tmp_path, units="km/h", speed=36.)
    raw = document(tmp_path, domain={"size_km": {"x": 20, "y": 20}},
                   polar={"enabled": True, "azimuth_count": 16},
                   variables={"surface": {"names": ["UM10", "VM10", "MSLP", "temperature"]}})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf, ExecutionOptions.from_config(conf, synchronous_export=True))
    assert result.ok and len(result.products) == 3
    replay = SimulationConfig.from_yaml(conf.output_dir / "resolved-config.yaml")
    assert replay.resolution == 2500 and replay.radial_resolution == 2500
    assert (conf.output_dir / "run-provenance.yaml").exists()
    cart = next(p["path"] for p in result.products if p["role"] == "cart")
    polar = next(p["path"] for p in result.products if p["role"] == "polar")
    with xr.open_dataset(cart) as ds:
        np.testing.assert_allclose(ds.wind_speed, 10.)
        assert ds.temperature.attrs["units"] == "K"
        assert ds.x_box_km.attrs["units"] == "km"
    with xr.open_dataset(polar) as ds:
        assert ds.UM10.attrs["units"] == "m s-1"
        np.testing.assert_allclose(ds.wind_speed.where(ds.wind_speed.notnull(), 10), 10.)


@pytest.mark.parametrize("model", ["AROME", "MNH"])
def test_frozen_matrix_new_schema_matches_legacy_configuration(tmp_path, model):
    """Exercise both real adapters through migrated nested configuration."""
    from importlib import resources

    from frameit.core.runner import FrameitRunner
    from frameit.testing.catalog import load_cases, resolve_case

    root = Path(str(resources.files("frameit.testing").joinpath("ci_dataset")))
    case = next(
        c for c in load_cases() if c["config"]["atm_model"] == model and c["polar"]
        and c["tracker"] == ("fixed_box" if model == "AROME" else "wind_pressure")
    )
    case = resolve_case(case, root, tmp_path / "legacy")
    assert case["preflight"] == "READY", case["reason"]
    legacy = SimulationConfig.from_mapping_with_model_preset(case["config"])
    nested, _ = migrate_mapping(case["config"])
    nested["output"]["directory"] = str(tmp_path / "nested")
    conf = SimulationConfig.from_mapping_with_model_preset(nested)
    with FrameitRunner(legacy, input_files=case["input_files"]) as a, FrameitRunner(
        conf, input_files=case["input_files"]
    ) as b:
        a.run()
        b.run()
        xr.testing.assert_allclose(a.track, b.track, rtol=1e-10, atol=1e-10)
        assert set(a.dict_crop_user) == set(b.dict_crop_user)
        for group in a.dict_crop_user:
            xr.testing.assert_allclose(
                a.dict_crop_user[group], b.dict_crop_user[group], rtol=1e-10, atol=1e-10
            )
        for group in a.dict_polar_user:
            xr.testing.assert_allclose(
                a.dict_polar_user[group], b.dict_polar_user[group], rtol=1e-10, atol=1e-10
            )
