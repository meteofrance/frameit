"""Strict public configuration and core metadata regressions."""

from __future__ import annotations

from copy import deepcopy
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
from frameit.io.loader import inventory_source_files
from frameit.processing.derived.wind import polar_wind_components
from frameit.processing.polar.polar_utils import ensure_theta_rad_dim
from frameit.utils.units import convert_units


def minimal_document():
    return {"schema_version": 3,
            "sources": {"atmosphere": {
                "model": "arome", "format": "netcdf", "files": "*.nc",
                "variables": {"2d": ["instructional_scalar"]}}},
            "region": {"center": {"latitude": -20., "longitude": 60.}},
            "products": {"model_grid": True},
            "output": {"directory": "./products", "overwrite": False}}


def test_fields_2d_translates_without_renaming_scientific_products(tmp_path):
    raw = minimal_document()
    assert raw["schema_version"] == 3
    raw["products"] = {"model_grid": True, "polar": {"radius_km": 2}}
    raw["sources"]["atmosphere"]["wind_pairs"] = [
        {"u": "u10", "v": "v10", "basis": "earth"}]
    runtime = to_runtime(raw, base_dir=tmp_path)
    request = runtime["source_requests"]["atmosphere"]
    assert request["fields"] == {"2d": ["instructional_scalar"], "3d": []}
    assert request["exports"] == {
        "model_grid": ["instructional_scalar"], "polar": ["instructional_scalar"]}
    assert not request["derived"] and not request["internal_inputs"]
    assert runtime["yaml_config"]["sources"]["atmosphere"]["variables"] == {
        "2d": ["instructional_scalar"]}
    assert runtime["yaml_config"]["sources"]["atmosphere"]["wind_pairs"] == [
        {"u": "u10", "v": "v10", "basis": "earth"}]
    replay = to_runtime(runtime["yaml_config"], base_dir=tmp_path)
    assert replay["source_requests"] == runtime["source_requests"]


def test_document_helper_emits_native_v3_without_implicit_diagnostics(tmp_path):
    raw = document(tmp_path)
    assert raw["schema_version"] == 3
    source = raw["sources"]["atmosphere"]
    assert source["files"] == str(tmp_path / "*.nc")
    assert source["variables"] == {"2d": ["UM10", "VM10", "MSLP"]}
    assert source["wind_pairs"] == [{"u": "UM10", "v": "VM10", "basis": "earth"}]
    runtime = to_runtime(raw, base_dir=tmp_path)
    request = runtime["source_requests"]["atmosphere"]
    assert request["exports"] == {"model_grid": ["UM10", "VM10", "MSLP"]}
    assert not request["derived"] and not request["internal_inputs"]
    assert runtime["yaml_config"]["products"]["track"] is True
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("location", ["variables", "polar", "wind_pairs", "source"])
def test_public_surface_group_is_rejected_actionably(tmp_path, location):
    raw = minimal_document()
    source = raw["sources"]["atmosphere"]
    if location == "variables":
        source["variables"] = {"surface": {"names": ["instructional_scalar"]}}
        error = "sources.atmosphere.variables.surface"
    elif location == "polar":
        raw["products"]["polar"] = {
            "radius_km": 2, "fields": {"atmosphere": {"surface": ["instructional_scalar"]}}}
        error = "products.polar.fields.atmosphere"
    elif location == "wind_pairs":
        source["wind_pairs"] = [
            {"group": "surface", "u": "u10", "v": "v10", "basis": "earth"}]
        error = r"sources.atmosphere.wind_pairs\[0\].group"
    else:
        raw["sources"] = {"surface": {
            **source, "variables": {"surface": {"names": ["instructional_scalar"]}}}}
        error = "sources.surface.variables.surface"
    with pytest.raises(ValueError, match=error):
        resolve_schema(raw, base_dir=tmp_path)
    assert not (tmp_path / "products").exists()


def test_fields_2d_fa_selection_retains_internal_record_group(tmp_path):
    raw = minimal_document()
    raw["sources"]["atmosphere"].update(
        format="fa", files="*.fa", profile="arome_history",
        variables={"2d": ["CLSTEMPERATURE"]})
    runtime = to_runtime(raw, base_dir=tmp_path)
    request = runtime["source_requests"]["atmosphere"]
    assert request["fields"] == {"2d": ["CLSTEMPERATURE"], "3d": []}
    assert request["exports"] == {"model_grid": ["CLSTEMPERATURE"]}
    assert runtime["yaml_config"]["sources"]["atmosphere"]["profile"] == "arome_history"
    assert runtime["fa_options"]["profile"] == "arome_history"


def test_current_schema_preserves_explicit_numerical_requests(tmp_path):
    raw = minimal_document()
    raw["region"] = {"tracker": {
        "method": "pressure_wind", "search_width_km": 150., "refine_width_km": 50.},
        "width_km": {"x": 4., "y": 6.}}
    raw["products"]["polar"] = {"radius_km": 2}
    raw["output"]["format"] = "zarr"
    raw["sources"]["atmosphere"]["transforms"] = [
        {"fields": ["u10", "v10"], "sampling": "mass", "basis": "earth"}]
    runtime = to_runtime(raw, base_dir=tmp_path)
    assert runtime["schema_version"] == 3
    assert runtime["tracking_method"] == "wind_pressure"
    assert runtime["wind_pressure_search_half_width_km"] == 75.
    assert runtime["wind_pressure_refine_half_width_km"] == 25.
    assert (runtime["x_boxsize_km"], runtime["y_boxsize_km"]) == (4., 6.)
    request = runtime["source_requests"]["atmosphere"]
    assert request["fields"] == {"2d": ["instructional_scalar"], "3d": []}
    assert request["exports"] == {
        "model_grid": ["instructional_scalar"], "polar": ["instructional_scalar"]}
    assert request["transforms"] == raw["sources"]["atmosphere"]["transforms"]
    assert not request["derived"] and not request["internal_inputs"]
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    options = ExecutionOptions.from_config(conf, export_netcdf=False)
    assert options.engine == "zarr" and not options.export_netcdf
    assert conf.wind_pairs == [] and conf.wind_reference_frame is None


@pytest.mark.parametrize("version", [
    None, 1, 2, "1", "2", "2.0", 2.1, True, False, "9", "2.1.0", "2.1", "3", 3.])
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
    assert "schema_version: 3" in str(error.value)
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
    (("region", "tracker", "method"), "wind_pressure"),
    (("region", "tracker", "wind_pressure"), {}),
    (("sources", "atmosphere", "wind_reference_frame"), "earth"),
    (("sources", "atmosphere", "fa", "backend"), "native"),
    (("polar", "variables"), "all"),
    (("sources", "atmosphere", "variables", "fields_2d"), {"names": ["T"], "levels": "all"}),
    (("output", "engine"), "zarr"),
    (("output", "format"), "NETCDF4"),
    (("output", "export", "netcdf"), False),
    (("output", "cartesian", "horizontal_winds"), "native"),
    (("output", "cartesian", "horizontal_vectors"), "mass_earth"),
])
def test_retired_keys_and_values_fail_in_current_document(path, value):
    raw = minimal_document()
    if path[:2] == ("region", "tracker"):
        raw["region"] = {"tracker": {"method": "pressure_wind"}}
    if path[:3] == ("sources", "atmosphere", "fa"):
        raw["sources"]["atmosphere"].update(format="fa", profile="arome_history")
    target = raw
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value
    rejected = path[0] if path[0] in {"domain", "polar"} else ".".join(path)
    if path[:2] == ("output", "export"):
        rejected = "output.export"
    elif path[:2] == ("output", "cartesian"):
        rejected = "output.cartesian"
    with pytest.raises(ValueError, match=rejected):
        resolve_schema(raw)


@pytest.mark.parametrize("path,value", [
    (("sources", "atmosphere", "exclude"), None),
    (("sources", "atmosphere", "files"), []),
    (("sources", "atmosphere", "variables", "2d"), [""]),
    (("sources", "atmosphere", "variables", "2d"), [" "]),
    (("sources", "atmosphere", "variables"), {1: {"names": ["scalar"]}}),
    (("output",), {"format": "zarr", "writer": {"engine": "netcdf4"}}),
    (("sources", "atmosphere", "reader", "chunks"), {1: 2}),
    (("sources", "atmosphere", 1), "invalid"),
    (("products", "polar"), {
        "radius_km": 2, "fields": {"atmosphere": ["instructional_scalar"]}, "levels": "stored"}),
    (("sources", "atmosphere", "polar"), {"azimuth_count": 8}),
    (("products", "polar"), {"radius_km": 2, "enabled": False}),
    (("region", "sources_coupling_time_association"), "strict"),
])
def test_current_schema_rejects_invalid_dynamic_declarations(path, value):
    raw = minimal_document()
    target = raw
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value
    with pytest.raises(ValueError):
        resolve_schema(raw)


def test_named_sources_project_requested_products_and_replay(tmp_path):
    from frameit.core.configuration import resolved_configuration, source_document

    raw = minimal_document()
    raw["sources"] = {
        "atmosphere": {"model": "arome", "files": ["atmosphere.nc"], "format": "netcdf",
                       "variables": {"2d": ["scalar"]}},
        "ocean": {"model": "nemo", "files": ["ocean.nc"], "format": "netcdf",
                  "variables": {"3d": {
                      "deptht": {"names": ["votemper"], "levels": {"indices": [1, 0]}}}}}}
    raw["region"]["sources_coupling_time_association"] = "common"
    raw["products"]["polar"] = {
        "radius_km": 5., "radial_step_km": 3., "azimuth_count": 8,
        "fields": {"ocean": ["deptht.votemper"]}}
    resolved, _, _ = resolve_schema(raw, base_dir=tmp_path)
    for name in ("atmosphere", "ocean"):
        source = resolved["sources"][name]
        assert source["files"] == [str(tmp_path / f"{name}.nc")]
        child = source_document(resolved, name)
        assert child["schema_version"] == 3
        assert child["sources"][name]["variables"] == source["variables"]
        if name == "ocean":
            assert child["products"]["polar"]["radial_step_km"] == 3.
            assert child["products"]["polar"]["azimuth_count"] == 8
        else:
            assert "polar" not in child["products"]
        resolve_schema(child, base_dir=tmp_path)
    config = SimulationConfig.from_mapping_with_model_preset(resolved)
    replay = resolved_configuration(config)
    assert resolve_schema(replay)[0] == replay
    declared = SimulationConfig.from_mapping_with_model_preset(raw)
    assert declared.schema_sources["products.polar.radial_step_km"] == "yaml"
    assert declared.schema_sources["products.polar.azimuth_count"] == "yaml"
    for key, value in (("time_alignment", "common"), ("sources", {})):
        bad = deepcopy(raw)
        bad["sources"]["ocean"][key] = value
        with pytest.raises(ValueError, match=key):
            resolve_schema(bad)


def test_effective_record_preserves_unresolved_automatic_spacing(tmp_path):
    from frameit.core.configuration import resolved_configuration

    conf = SimulationConfig.from_mapping_with_model_preset(minimal_document())
    effective = resolved_configuration(conf)
    assert "grid_spacing_m" not in effective["sources"]["atmosphere"]
    assert conf.resolution == 0 and conf.infer_grid_geometry
    assert resolve_schema(effective)[0] == effective


def test_current_cli_exposes_unambiguous_export_controls_and_no_converter():
    parser = _build_parser()
    args = parser.parse_args(["run", "--no-export", "--no-export-cartesian"])
    assert not args.export_netcdf and not args.export_cart
    for retired in (["run", "--no-export-netcdf"], ["run", "--no-export-cart"],
                     ["run", "--dry-run"], ["config", "migrate", "old.yaml"]):
        with pytest.raises(SystemExit) as result:
            parser.parse_args(retired)
        assert result.value.code == 2


def test_catalog_emits_current_requests_without_legacy_conversion():
    from frameit.testing.catalog import load_cases

    cases = load_cases()
    assert all(case["config"].get("schema_version") == 3 for case in cases)
    case = next(case for case in cases if case["id"] == "arome_batsirai_fixed_polar")
    conf = SimulationConfig.from_mapping_with_model_preset(case["config"])
    variables = conf.yaml_config["sources"]["atmosphere"]["variables"]
    assert variables["3d"]["isobaricInhPa"]["levels"] == {
        "values": [1000, 850, 400], "units": "hPa"}
    assert variables["3d"]["heightAboveGround"]["levels"] == {"indices": [0, 2, 5]}
    assert variables["2d"] == ["u10", "v10", "prmsl", "sshf", "slhf"]
    assert conf.infer_grid_geometry and conf.resolution == 0 and conf.radial_resolution == 2500
    assert conf.polar_n_theta == 36 and conf.azimuthal_resolution is None


def document(tmp_path, **sections):
    # This synthetic fixture defines UM10/VM10 as Earth-relative components.
    value = {"schema_version": 3,
             "sources": {"atmosphere": {
                 "model": "mesonh", "format": "netcdf", "files": str(tmp_path / "*.nc"),
                 "variables": {"2d": ["UM10", "VM10", "MSLP"]},
                 "wind_pairs": [{"u": "UM10", "v": "VM10", "basis": "earth"}],
                 "field_metadata": {name: {"kind": "continuous"} for name in (
                     "UM10", "VM10", "MSLP", "temperature")}}},
             "output": {"directory": str(tmp_path / "output")},
             "region": {"center": {"latitude": -20., "longitude": 60.}},
             "products": {"model_grid": True, "track": True}}
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
def test_model_starter_loads_runtime_defaults(tmp_path, model):
    path = tmp_path / "frameit.yaml"
    write_template(model, path)
    conf = SimulationConfig.from_yaml(path)
    assert conf.schema_version == 3 and conf.infer_grid_geometry
    assert conf.resolution == 0
    assert conf.tracking_method == "wind_pressure"
    source = conf.yaml_config["sources"]["atmosphere"]
    assert Path(source["files"]).parent == tmp_path / "data"
    assert source["wind_pairs"] == [{"u": "u10" if model == "arome" else "UM10",
                                     "v": "v10" if model == "arome" else "VM10",
                                     "basis": "earth"}]
    assert conf.cartesian_horizontal_winds == "native"
    assert conf.cartesian_vertical_velocity == "interfaces"
    assert conf.polar_vertical_velocity == "interfaces"
    with pytest.raises(FileExistsError):
        write_template(model, path)


@pytest.mark.parametrize("path,value", [
    (("products", "polar"), {"radius_km": 10, "radial_step_km": "2.5"}),
    (("products", "polar"), {"radius_km": 10, "shared_grid": "false"}),
    (("products", "polar"), {"radius_km": 10, "azimuth_count": 64, "azimuth_step_deg": 10}),
    (("region", "width_km"), {"x": 500}),
    (("region", "width_km"), {"x": -1, "y": 50}),
    (("output", "writer", "compression", "level"), 10),
    (("logging", "levle"), "INFO"),
    (("sources", "atmosphere", "files"), {"pattern": "*.nc", "files": ["native.nc"]}),
    (("sources", "atmosphere", "variables"), {
        "3d": {"level": {"names": ["UT"], "levels": {"indices": [-1]}}}}),
    (("sources", "atmosphere", "variables"), {
        "3d": {"level": {"names": ["UT"], "levels": {"indices": [0], "values": [1]}}}}),
    (("products", "polar"), {}),
    (("region",), None),
])
def test_schema_rejects_ambiguous_or_invalid_values(tmp_path, path, value):
    raw = document(tmp_path)
    target = raw
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value
    with pytest.raises(ValueError):
        resolve_schema(raw)


def test_yaml_duplicates_unknown_locations_and_legacy_rejection(tmp_path):
    path = tmp_path / "frameit.yaml"
    path.write_text('schema_version: 3\nsources: {}\nsources: {}\n')
    with pytest.raises(ValueError, match="Duplicate.*line 3"):
        SimulationConfig.from_yaml(path)
    path.write_text(
        "schema_version: 3\nsources:\n  atmosphere:\n    files: '*.nc'\n    patten: '*.nc'\n")
    with pytest.raises(ValueError, match="sources.atmosphere.patten") as error:
        SimulationConfig.from_yaml(path)
    assert "line 5" in str(error.value)
    path.write_text("atm_model: AROME\nresolution: 2500\n")
    with pytest.raises(ValueError, match="schema_version"):
        SimulationConfig.from_yaml(path)


def test_inventory_order_exclusion_and_config_relative_paths(tmp_path, monkeypatch):
    for name in ("a.nc", "b.nc", "000.nc"):
        dataset(tmp_path, name)
    path = tmp_path / "frameit.yaml"
    raw = document(tmp_path)
    raw["sources"]["atmosphere"].update(
        files=["b.nc", "a.nc", "000.nc"], exclude=["000.nc"])
    path.write_text(yaml.safe_dump(raw))
    monkeypatch.chdir(tmp_path.parent)
    conf = SimulationConfig.from_yaml(path)
    entries, excluded, overlaps = inventory_source_files(conf.sources["atmosphere"])
    assert [Path(entry["path"]).name for entry in entries] == ["b.nc", "a.nc"]
    assert excluded == [str(tmp_path / "000.nc")] and not overlaps
    assert all(Path(entry["path"]).parent == tmp_path for entry in entries)


def test_preflight_inference_units_defaults_and_no_outputs(tmp_path):
    dataset(tmp_path)
    raw = document(tmp_path)
    raw["region"]["width_km"] = {"x": 20, "y": 20}
    raw["products"]["polar"] = {"radius_km": 10, "azimuth_count": 16}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan = preflight(conf)
    source = plan["sources"]["atmosphere"]
    grid, = source["region"]["grids"].values()
    assert grid["geometry"]["effective_spacing_m"] == 2500
    assert grid["geometry"]["sources"] == [
        "projected_coordinate:ni", "projected_coordinate:nj"
    ]
    polar = source["requests"]["binding"]["polar_plan"]
    assert polar["radial_step_km"] == 2.5
    assert len(polar["radius_km"]) * len(polar["azimuth_degrees"]) == 5 * 16
    assert grid["realised_span_km"] == {"x": 20., "y": 20.}
    assert [int(grid["realised_span_km"][axis] * 1000 / 2500 + 1)
            for axis in ("x", "y")] == [9, 9]
    assert not conf.output_dir.exists()
    assert {job["name"]: job["result_units"]
            for job in source["requests"]["binding"]["operation_plans"]} == {
                "UM10": "m s-1", "VM10": "m s-1", "MSLP": "Pa"}


def test_geometry_rejects_anisotropy_and_conflicting_inputs(tmp_path):
    dataset(tmp_path, dx=4000)
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path))
    with pytest.raises(ValueError, match="Anisotropic"):
        preflight(conf)
    dataset(tmp_path)
    ds = dataset(tmp_path, "second.nc")
    ds = ds.assign_coords(longitude=ds.longitude + .1)
    ds.to_netcdf(tmp_path / "second.nc", engine="h5netcdf")
    with pytest.raises(ValueError, match="distinct fields.*conflicting fields"):
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
    from types import SimpleNamespace

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
    conf = SimpleNamespace(wind_pairs=[{
        "group": "surface", "u": "UM10", "v": "VM10", "reference_frame": "grid",
        "rotation": {"method": "coordinate", "coordinate": "grid_rotation"}}])
    result = normalize_winds(winds, conf, "surface")
    np.testing.assert_allclose(result.UM10, 0, atol=1e-12)
    np.testing.assert_allclose(result.VM10, 10, atol=1e-12)


def test_time_dependent_geometry_and_retired_override_contract(tmp_path):
    ds = dataset(tmp_path)
    changing = ds.assign_coords(longitude=ds.longitude.expand_dims(time=ds.time).copy())
    changing["longitude"][1] = changing.longitude[1] + .01
    changing.to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path))
    with pytest.raises(ValueError, match="incompatible"):
        preflight(conf)
    dataset(tmp_path)
    raw = document(tmp_path)
    raw["sources"]["atmosphere"]["grid_spacing_m"] = 2600
    with pytest.raises(ValueError, match=r"sources\.atmosphere\.grid_spacing_m"):
        SimulationConfig.from_mapping_with_model_preset(raw)


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
    from frameit.core.execution import execute_simulation

    ds = dataset(tmp_path)
    path = tmp_path / "track.nc"
    xr.Dataset({
        "lat": ("time", np.deg2rad([-20., -20.]), {"units": "rad"}),
        "lon": ("time", np.deg2rad([60., 60.]), {"units": "rad"}),
    }, coords={"time": ds.time}).to_netcdf(path, engine="h5netcdf")
    raw = document(tmp_path, region={
        "track": {"file": str(path)}, "width_km": {"x": 20, "y": 20}})
    raw["sources"]["atmosphere"]["files"] = [str(tmp_path / "native.nc")]
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan = preflight(conf)
    assert len(plan["sources"]["atmosphere"]["selected_times"]) == 2
    centres = conf.simulation_parameter["region_centres"]
    assert centres.lat.attrs["source_units"] == "rad"
    np.testing.assert_allclose(centres.lat, -20.)
    np.testing.assert_allclose(centres.lon, 60.)
    assert not conf.output_dir.exists()
    result = execute_simulation(conf, ExecutionOptions.from_config(conf, synchronous_export=True))
    assert not any(item["role"] == "polar" for item in result.products)
    track = next(item for item in result.products if item["role"] == "track")
    with xr.open_dataset(track["path"]) as saved:
        np.testing.assert_allclose(saved.latitude, -20.)
        np.testing.assert_allclose(saved.longitude, 60.)
    missing = xr.Dataset(coords={"time": ds.time})
    missing.to_netcdf(path, engine="h5netcdf")
    with pytest.raises(ValueError, match="missing or ambiguous"):
        preflight(conf)


def test_cli_validation_options_and_no_products(tmp_path, capsys):
    dataset(tmp_path)
    path = tmp_path / "frameit.yaml"
    raw = document(tmp_path)
    raw["output"]["writer"] = {"compression": {"level": 0}}
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(SystemExit) as result:
        main(["validate", str(path), "--json", "--cpus", "1"])
    assert result.value.code == 0
    report = yaml.safe_load(capsys.readouterr().out)
    plan = report["data"]
    assert {item["product"] for item in plan["plan"]["products"]} == {"model_grid", "track"}
    assert plan["configuration"]["output"]["writer"]["compression"]["level"] == 0
    assert plan["configuration"]["sources"]["atmosphere"]["format"] == "netcdf"
    assert plan["origins"]["output.writer.compression.level"] == "yaml"
    assert plan["origins"]["resources.cpus"] == "cli"
    assert not (tmp_path / "output").exists()


def test_cli_yaml_precedence_and_optional_config(tmp_path):
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, output={
        "directory": str(tmp_path / "out"), "writer": {"compression": {"level": 4}}}))
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
