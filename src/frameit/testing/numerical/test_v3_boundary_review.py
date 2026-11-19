"""Regressions from the independent boundary review, not scientific sign-off."""

from copy import deepcopy

import netCDF4
import numpy as np
import pytest
import xarray as xr

from frameit.core.execution import execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.processing.requests import align_initial_gap
from frameit.utils.units import convert_units

from .test_configuration_v2_1 import dataset, document
from .test_v3_boundary_repairs import gap_case


def test_initial_gap_refuses_unknown_reference_clock_without_inventing_a_cycle():
    times = np.array(["2024-01-01T00", "2024-01-01T01"], dtype="datetime64[ns]")
    source = {
        "selected_times": list(times),
        "allowed_gaps": [{"field": "u", "time": times[0]}],
        "records": [{"time": time, "cycle": None} for time in times]}
    value = xr.Dataset({"u": ("time", [1.])}, coords={
        "time": times[1:],
        "forecast_reference_time": ("time", np.array(["NaT"], dtype="datetime64[ns]"))})
    with pytest.raises(ValueError, match="ambiguous source reference clocks"):
        align_initial_gap(value, "u", source)


def test_initial_gap_and_complete_polar_field_share_only_real_read_records(tmp_path):
    raw = gap_case(tmp_path)
    raw["sources"]["atmosphere"]["field_metadata"]["prmsl"] = {"kind": "continuous"}
    raw["products"]["polar"] = {
        "radius_km": .5, "azimuth_count": 8,
        "fields": {"atmosphere": ["temperature", "prmsl"]}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    source = preflight(conf)["sources"]["atmosphere"]
    records = deepcopy(source["record_inventory"])
    result = execute_simulation(conf)
    path = next(p["path"] for p in result.products if p["role"] == "polar")
    with xr.open_dataset(path) as saved:
        assert saved.time.size == 3
        assert np.isnan(saved.temperature.isel(time=0)).all()
        np.testing.assert_allclose(saved.prmsl.isel(radius=0), 100000.)
    assert source["record_inventory"] == records


def test_timeless_field_initial_gap_has_missing_output_not_broadcast_values(tmp_path):
    from frameit.core.preflight import collect_preflight

    raw = gap_case(tmp_path)
    path = tmp_path / "temperature.nc"
    with xr.open_dataset(path) as original:
        scene = original.load()
    scene["temperature"] = scene.temperature.isel(time=0, drop=True)
    scene.to_netcdf(path)
    before = path.read_bytes(), path.stat().st_mtime_ns
    preview = collect_preflight(raw)
    assert not preview.errors
    source = preview.facts["sources"]["atmosphere"]
    records = deepcopy(source["record_inventory"])
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert saved.temperature.dims == ("time", "y", "x")
        assert preview.facts["products"][0]["dimensions"]["temperature"] == [
            "time", "y", "x"]
        np.testing.assert_array_equal(saved.time, np.array([
            "2024-01-01T00", "2024-01-01T01", "2024-01-01T02"], dtype="datetime64[ns]"))
        assert np.isnan(saved.temperature.isel(time=0)).all()
        np.testing.assert_array_equal(saved.temperature.isel(time=slice(1, None)), 281.)
    assert source["record_inventory"] == records
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_absent_polar_interval_keeps_unknown_bounds_missing(tmp_path):
    raw = gap_case(tmp_path)
    path = tmp_path / "temperature.nc"
    with xr.open_dataset(path) as original:
        scene = original.load()
    times = scene.time.values
    scene = scene.assign_coords(time_bounds=(
        ("time", "nv"), np.column_stack([times - np.timedelta64(1, "h"), times])))
    scene.time.attrs["bounds"] = "time_bounds"
    scene.temperature.attrs["cell_methods"] = "time: sum"
    scene.to_netcdf(path)
    raw["products"] = {
        "model_grid": {"fields": {"atmosphere": ["prmsl"]}},
        "polar": {"radius_km": .5, "azimuth_count": 8,
                  "fields": {"atmosphere": ["temperature"]}}}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    product = next(p for p in result.products if p["role"] == "polar")
    with xr.open_dataset(product["path"]) as saved:
        assert saved.time.attrs["bounds"] == "time_bounds"
        assert np.isnat(saved.time_bounds.isel(time=0)).all()
        np.testing.assert_array_equal(saved.time_bounds.isel(time=slice(1, None)),
                                      scene.time_bounds)


@pytest.mark.parametrize("layered,moved", [(False, False), (False, True), (True, False)])
def test_grib_gap_geometry_distinguishes_horizontal_and_vertical_support(tmp_path, layered, moved):
    from .test_v3_grib_reads import write_messages

    path = write_messages(tmp_path / "input.grib", [
        *[{"param": 151, "group": "meanSea", "level": 0, "hour": hour, "missing": False}
          for hour in (0, 1, 2)],
        *[{"param": 131 if layered else 147, "group": "isobaricInhPa" if layered else "surface",
           "level": 850 if layered else 0, "hour": hour, "missing": False,
           "latitude": -21. if moved else -20.} for hour in (1, 2)]])
    field = "u" if layered else "slhf"
    raw = {
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "arome", "files": str(path), "format": "grib",
            "variables": {"2d": ["prmsl", *([] if layered else [field])],
                          **({"3d": [field]} if layered else {})},
            "allow_initial_gaps": [field]}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"synchronous_export": True, "cpus": 1}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if layered or moved:
        with pytest.raises(ValueError, match="proven unchanged native grid"):
            preflight(conf)
        assert not conf.output_dir.exists()
    else:
        result = execute_simulation(conf)
        with xr.open_dataset(result.products[0]["path"]) as saved:
            assert saved.time.size == 3
            assert np.isnan(saved.slhf.isel(time=0)).all()
            assert np.isfinite(saved.slhf.isel(time=slice(1, None))).all()


@pytest.mark.parametrize("role,ensemble,isolated", [
    ("model_grid", False, False), ("polar", False, False),
    ("polar", True, False), ("polar", True, True)])
def test_grib_initial_gap_preserves_each_member_and_temporal_evidence(
        tmp_path, role, ensemble, isolated):
    from .test_v3_grib_reads import write_messages

    path = write_messages(tmp_path / "input.grib", [
        {"hour": hour, "param": param, "level": 850, "missing": False,
         **({"member": member} if ensemble else {})}
        for param in (131, 132) for hour in (0, 1, 2)
        if param == 132 or hour != 0
        for member in ((0, 1) if ensemble else (None,))])
    before = path.read_bytes(), path.stat().st_mtime_ns
    raw = {
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "arome", "format": "grib", "files": str(path),
            "variables": {"3d": ["u", "v"]},
            "field_metadata": {name: {"kind": "continuous"} for name in ("u", "v")},
            "allow_initial_gaps": ["u"]}},
        "region": {"center": {"latitude": -19.5, "longitude": 61.}},
        "products": {role: True if role == "model_grid" else {
            "radius_km": .5, "azimuth_count": 8}},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"synchronous_export": True, "scheduler": "synchronous", "cpus": 1}}
    if isolated:
        raw["products"] = {
            "model_grid": {"fields": {"atmosphere": ["v"]}},
            "polar": {"radius_km": .5, "azimuth_count": 8,
                      "fields": {"atmosphere": ["u"]}}}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    product = next(p for p in result.products if p["role"] == role)
    with xr.open_dataset(product["path"]) as saved:
        np.testing.assert_array_equal(saved.time, np.array([
            "2026-01-01T00", "2026-01-01T01", "2026-01-01T02"], dtype="datetime64[ns]"))
        assert np.isnan(saved.u.isel(time=0)).all()
        assert np.isfinite(saved.u.isel(time=slice(1, None))).all()
        if ensemble:
            np.testing.assert_array_equal(saved.number, [0, 1])
        if role == "polar":
            assert (saved.u_interpolation_status.isel(time=0) == 2).all()
        else:
            assert saved.u_GRIB_stepType.isel(time=0).item() == ""
            assert saved.u_GRIB_stepType.isel(time=1).item() == "instant"
            assert np.isnan(saved.u_GRIB_startStep.isel(time=0))
            np.testing.assert_array_equal(saved.u_GRIB_endStep.isel(time=slice(1, None)), [1, 2])
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize("limits", [
    {"valid_min": 30., "valid_max": 40.},
    {"valid_range": np.array([30., 40.])}])
def test_unit_conversion_preserves_ordinary_reader_validity(tmp_path, limits):
    source = xr.DataArray([36.], dims="time", name="u",
                          attrs={"units": "km/h", "actual_range": [36., 36.], **limits})
    result = convert_units(source, "velocity")
    for name, values in limits.items():
        np.testing.assert_allclose(result.attrs[name], np.asarray(values) / 3.6)
    np.testing.assert_allclose(result.attrs["actual_range"], [10., 10.])
    assert source.attrs["units"] == "km/h"
    path = tmp_path / "converted.nc"
    result.to_dataset().to_netcdf(path)
    with netCDF4.Dataset(path) as ordinary:
        assert not np.ma.getmaskarray(ordinary["u"][:]).any()
        np.testing.assert_allclose(ordinary["u"][:], [10.])


def test_unit_conversion_rejects_ambiguous_packed_validity_limits():
    source = xr.DataArray([36.], dims="time", name="u", attrs={
        "units": "km/h", "valid_range": np.array([0, 400], dtype="int16")})
    source.encoding["scale_factor"] = .1
    with pytest.raises(ValueError, match="packed.*valid"):
        convert_units(source, "velocity")


def test_bound_model_grid_contract_uses_converted_and_derived_units(tmp_path):
    dataset(tmp_path, units="km/h", speed=36.)
    raw = document(tmp_path)
    source = raw["sources"]["atmosphere"]
    source["transforms"] = [{"fields": ["UM10"], "units": "m s-1"}]
    source["derived"] = {
        "speed": {"method": "wind_speed", "inputs": {"u": "UM10", "v": "VM10"}}}
    raw["products"]["polar"] = {
        "radius_km": 10, "fields": {"atmosphere": ["UM10"]}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    report = preflight(conf)
    product = next(p for p in report["products"] if p["product"] == "model_grid")
    assert product["units"]["UM10"] == product["units"]["speed"] == "m s-1"
    assert product["units"]["VM10"] == "km/h"


@pytest.mark.parametrize("earth", [False, True])
def test_explicit_polar_base_basis_is_separate_from_model_grid(tmp_path, earth):
    scene = dataset(tmp_path, speed=3.)
    scene["VM10"][:] = 4.
    for name in ("UM10", "VM10"):
        scene[name].attrs["wind_reference_frame"] = "grid"
    scene = scene.assign_coords(grid_rotation=xr.DataArray(90., attrs={"units": "degrees"}))
    scene.to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    raw = document(tmp_path, resources={"cpus": 1, "synchronous_export": True})
    source = raw["sources"]["atmosphere"]
    source["wind_pairs"] = [{
        "u": "UM10", "v": "VM10", "basis": "grid",
        "rotation": {"method": "coordinate", "coordinate": "grid_rotation"}}]
    source["transforms"] = [
        {"fields": ["UM10", "VM10"], "sampling": "mass", "basis": "earth"}]
    raw["products"]["polar"] = {
        "radius_km": 10, "azimuth_count": 16,
        "fields": {"atmosphere": ["UM10", "VM10"]}}
    if earth:
        raw["products"]["polar"]["field_options"] = {"atmosphere": {
            name: {"sampling": "mass", "basis": "earth"} for name in ("UM10", "VM10")}}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    for product in result.products:
        if product["role"] == "track":
            continue
        rotated = product["role"] == "model_grid" or earth
        with xr.open_dataset(product["path"]) as saved:
            np.testing.assert_allclose(saved.UM10, -4. if rotated else 3., atol=1e-12)
            np.testing.assert_allclose(saved.VM10, 3. if rotated else 4., atol=1e-12)
            assert saved.UM10.attrs["wind_reference_frame"] == ("earth" if rotated else "grid")


@pytest.mark.parametrize("companion", [True, False])
def test_polar_earth_base_reads_companion_without_exporting_or_changing_native_units(
        tmp_path, companion):
    scene = dataset(tmp_path, units="km/h", speed=10.8)
    scene["VM10"][:] = 14.4
    for name in ("UM10", "VM10"):
        scene[name].attrs["wind_reference_frame"] = "grid"
    scene = scene.assign_coords(grid_rotation=xr.DataArray(90., attrs={"units": "degrees"}))
    if not companion:
        scene = scene.drop_vars("VM10")
    scene.to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    raw = document(tmp_path, resources={"cpus": 1, "synchronous_export": True})
    source = raw["sources"]["atmosphere"]
    source["variables"] = {"2d": ["UM10"]}
    source["wind_pairs"] = [{
        "u": "UM10", "v": "VM10", "basis": "grid",
        "rotation": {"method": "coordinate", "coordinate": "grid_rotation"}}]
    raw["products"] = {"polar": {
        "radius_km": 10, "azimuth_count": 16, "fields": {"atmosphere": ["UM10"]},
        "field_options": {"atmosphere": {"UM10": {"basis": "earth"}}}}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if not companion:
        with pytest.raises(ValueError, match="VM10.*missing"):
            preflight(conf)
        assert not conf.output_dir.exists()
    else:
        result = execute_simulation(conf)
        with xr.open_dataset(result.products[0]["path"]) as saved:
            assert "VM10" not in saved
            assert saved.UM10.attrs["units"] == "km/h"
            np.testing.assert_allclose(saved.UM10, -14.4, atol=1e-12)


@pytest.mark.parametrize("command", ["validate", "config show --effective"])
@pytest.mark.parametrize("problem", ["category", "units", "writer_axis", "tracker_inputs"])
def test_public_native_validation_binds_known_scientific_and_output_constraints(
        tmp_path, monkeypatch, command, problem):
    from frameit.core.preflight import collect_preflight
    from frameit.testing.documentation_example import create_first_run_input

    from .test_inspect_metadata import guard_netcdf_payloads

    path = create_first_run_input(tmp_path / "scalar.nc")
    raw = {
        "schema_version": 3,
        "sources": {"atmosphere": {"model": "arome", "files": str(path),
                                  "variables": {"2d": ["instructional_scalar"]}}},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "out")}}
    source = raw["sources"]["atmosphere"]
    if problem == "category":
        source["variables"] = {"3d": ["instructional_scalar"]}
    elif problem == "units":
        source["transforms"] = [{"fields": ["instructional_scalar"], "units": "m s-1"}]
    elif problem == "writer_axis":
        raw["output"]["writer"] = {"chunks": {"not_an_axis": 1}}
    else:
        from .test_pressure_centroid_mnh import native_vortex

        scene, _ = native_vortex(n=9)
        path = tmp_path / "native.nc"
        scene.drop_vars("ALT").to_netcdf(path)
        source["model"] = "mesonh"
        source["files"] = str(path)
        source["variables"] = {"2d": ["MSLP"]}
        source["wind_pairs"] = [
            {"u": "UT_ZM", "v": "VT_ZM", "basis": "earth"},
            {"u": "UM10", "v": "VM10", "basis": "earth"}]
        raw["region"] = {"tracker": {"method": "pressure_centroid"}}
    guard_netcdf_payloads(monkeypatch, {
        "instructional_scalar", "MSLP", "PABST", "PRES", "UT_ZM", "VT_ZM", "UM10", "VM10"})
    result = collect_preflight(raw, command=command)
    assert result.errors, f"{command} accepted known-invalid {problem}"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("file_count", [1, 2])
def test_croco_polar_masks_finite_land_without_changing_native_values_or_depth_meaning(
        tmp_path, file_count):
    from frameit.testing.documentation_example import create_tutorial_inputs

    paths = create_tutorial_inputs(tmp_path / "data")
    with xr.open_dataset(paths["ocean"]) as original:
        water = original.load()
    water["temp"][:] = 280.
    water.mask_rho[6, 6] = 0
    files = [tmp_path / f"water{index}.nc" for index in range(file_count)]
    for index, path in enumerate(files):
        (water if file_count == 1 else water.isel(time=[index])).to_netcdf(path)
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}
    raw = {
        "schema_version": 3,
        "sources": {"ocean": {"model": "croco", "files": [str(path) for path in files],
                             "variables": {"3d": ["temp"]}}},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"model_grid": True, "polar": {"radius_km": 20, "azimuth_count": 8}},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"cpus": 1, "synchronous_export": True}}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    for product in result.products:
        with xr.open_dataset(product["path"]) as saved:
            if product["role"] == "model_grid":
                np.testing.assert_allclose(saved.temp, 280.)
                assert "formula_terms" in saved.s_rho.attrs
            else:
                assert np.isnan(saved.temp.isel(radius=0)).all()
                assert (saved.temp_interpolation_status.isel(radius=0) == 2).all()
                assert "formula_terms" not in saved.s_rho.attrs
                assert saved.s_rho.attrs["source_standard_name"] == "ocean_s_coordinate_g2"
                assert saved.attrs["vertical_sampling"] == (
                    "native_sigma_indices_not_constant_physical_depth")
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files} == before


@pytest.mark.parametrize("problem", ["time_dimension", "changed_between_files"])
def test_croco_polar_static_mask_admission_survives_sample_axis_repair(tmp_path, problem):
    from frameit.testing.documentation_example import create_tutorial_inputs

    paths = create_tutorial_inputs(tmp_path / "data")
    with xr.open_dataset(paths["ocean"]) as original:
        water = original.load()
    files = []
    for index in range(2):
        part = water.isel(time=[index]).copy(deep=True)
        if problem == "time_dimension":
            part["mask_rho"] = part.mask_rho.expand_dims(time=part.time)
        elif index == 1:
            part.mask_rho[6, 6] = 0
        path = tmp_path / f"water{index}.nc"
        part.to_netcdf(path)
        files.append(str(path))
    raw = {
        "schema_version": 3,
        "sources": {"ocean": {"model": "croco", "files": files,
                             "variables": {"3d": ["temp"]}}},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"polar": {"radius_km": 20, "azimuth_count": 8}},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"cpus": 1, "synchronous_export": True}}
    with pytest.raises(ValueError, match="mask_rho"):
        execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not list((tmp_path / "out/products").glob("*.nc"))


@pytest.mark.parametrize("polar", [False, True])
def test_nemo_native_component_copy_does_not_bypass_existing_polar_admission(tmp_path, polar):
    from .test_nemo_netcdf import nemo_scene

    scene = nemo_scene(depth="depthu", field="vozocrtx")
    scene.vozocrtx.attrs.update(units="m s-1", standard_name="sea_water_x_velocity",
                                kind="continuous")
    path = tmp_path / "water.nc"
    scene.to_netcdf(path)
    raw = {
        "schema_version": 3,
        "sources": {"ocean": {"model": "nemo", "files": str(path),
                             "variables": {"3d": ["vozocrtx"]}}},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"polar": {"radius_km": 1, "azimuth_count": 8}} if polar else {
            "model_grid": True},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"cpus": 1, "synchronous_export": True}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if polar:
        with pytest.raises(ValueError, match="NEMO polar component.*unqualified"):
            preflight(conf)
        assert not conf.output_dir.exists()
    else:
        result = execute_simulation(conf)
        with xr.open_dataset(result.products[0]["path"]) as saved:
            np.testing.assert_array_equal(saved.vozocrtx, scene.vozocrtx)


@pytest.mark.parametrize("filename", ["conf_pressure_centroid.yml", "conf_multifield_arome.yml"])
def test_arome_tracker_binds_its_pressure_group_without_filtering_archive(
        tmp_path, monkeypatch, filename):
    from pathlib import Path

    import eccodes as ec
    import yaml

    from frameit.core.preflight import collect_preflight
    from frameit.testing.datasets import ci_dataset_root

    files = sorted((ci_dataset_root() / "AROME/BATSIRAI").glob("*.grib"))
    assert len(files) == 5, "The approved unfiltered local fixture is required"
    raw = yaml.safe_load((Path(__file__).parents[4] / "example/config_file" / filename).read_text())
    raw["sources"]["atmosphere"]["files"] = [str(path) for path in files]
    raw["output"]["directory"] = str(tmp_path / "out")
    arrays = ec.codes_get_array

    def no_values(*args, **kwargs):
        pytest.fail("Tracker binding decoded scientific payload")

    def guarded(handle, key, *args, **kwargs):
        if key in {"values", "codedValues"}:
            no_values()
        return arrays(handle, key, *args, **kwargs)

    monkeypatch.setattr(ec, "codes_get_values", no_values)
    monkeypatch.setattr(ec, "codes_get_array", guarded)
    result = collect_preflight(raw)
    assert not result.errors, [error.message for error in result.errors]
    source = result.conf.simulation_parameter["request_plan"]["sources"]["atmosphere"]
    support = source["field_binding"]["dependencies"]
    for name in ("u", "v", "z"):
        assert source["fields"][support[name]["field_id"]]["group"] == "isobaric"
    assert {source["fields"][r["field_id"]]["group"] for r in source["record_inventory"]
            if r["name"] == "u"} >= {"isobaric", "heightAboveGround", "potentialVorticity"}
    assert not (tmp_path / "out").exists()


def test_transformed_and_native_fields_share_unchanged_scalar_support_across_files(tmp_path):
    from .test_v3_operations import scene

    original = scene()
    original["ZTOP"] = xr.DataArray(21660., attrs={"units": "m", "long_name": "model top"})
    original["ZS"] = xr.DataArray(np.zeros((3, 3)), dims=("nj", "ni"), attrs={"units": "m"})
    original.level.attrs.update(
        formula_terms="s: level height: ZTOP orog: ZS",
        formula_definition="z(n,k,j,i)=s(k)*(height-orog(j,i))/height+orog(j,i)",
        computed_standard_name="altitude")
    files = [tmp_path / "part0.nc", tmp_path / "part1.nc"]
    for index, path in enumerate(files):
        original.isel(time=[index]).to_netcdf(path)
    raw = {
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "mesonh", "files": [str(path) for path in files],
            "variables": {"3d": ["U", "V"]},
            "transforms": [{"fields": ["U"], "units": "m s-1"}]}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"cpus": 1, "synchronous_export": True}}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    with xr.open_dataset(result.products[0]["path"]) as saved:
        np.testing.assert_allclose(saved.U, 3., rtol=0, atol=1e-12)
        np.testing.assert_allclose(saved.V, 14.4, rtol=0, atol=1e-12)
        assert saved.ZTOP.dims == () and saved.ZTOP.item() == 21660.
        assert saved.ZTOP.attrs["units"] == "m"


def _native_altitude_scene():
    from .test_wind_collocation import native

    scene = native()
    scene["THT"] = (("time", "level", "nj", "ni"), np.arange(27.).reshape(1, 3, 3, 3),
                    {"units": "K"})
    scene["ZS"] = xr.zeros_like(scene.latitude).assign_attrs(units="m")
    scene["ALT"] = xr.broadcast(scene.level_w, scene.latitude)[0].assign_attrs(
        units="m", standard_name="altitude", positive="up")
    scene.WT.values[0, 2, 1, 1] = np.nan
    for dim, quantity in (("level", "altitude"), ("level_w", "altitude_at_w_location")):
        scene[dim].attrs.update(
            units="m", computed_standard_name=quantity,
            formula_definition="z(n,k,j,i)=s(k)*(height-orog(j,i))/height+orog(j,i)",
            formula_terms=f"s: {dim} height: ZTOP orog: ZS")
    scene.level.attrs["standard_name"] = "altitude"
    return scene


def _native_altitude_request(tmp_path, paths, *, fmt="netcdf"):
    return {
        "schema_version": 3,
        "sources": {"atmosphere": {"model": "mesonh", "files": [str(path) for path in paths],
                     "variables": {"3d": ["THT", "WT", "ALT"], "levels": {"indices": [0, 2]}}}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "out"), "format": fmt},
        "resources": {"cpus": 1, "synchronous_export": True},
    }


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_altitude_formula_native_export_keeps_labels_and_interface_alt(tmp_path, fmt):
    import yaml

    from frameit.core.preflight import collect_preflight

    scene = _native_altitude_scene()
    path = tmp_path / "native.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    raw = _native_altitude_request(tmp_path, [path], fmt=fmt)
    report = collect_preflight(raw)
    assert not report.errors, report.errors
    warnings = report.facts["sources"]["atmosphere"]["field_binding"]["warnings"]
    assert all(any(f"{dim} native labels" in warning and "ZTOP" in warning for warning in warnings)
               for dim in ("level", "level_w"))
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf)
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    assert set(warnings) <= set(provenance["warnings"])
    product, = result.products
    opened = (xr.open_zarr(product["path"], decode_coords=False, consolidated=False)
              if fmt == "zarr" else xr.open_dataset(product["path"], decode_coords=False))
    with opened as saved:
        for dim, labels in (("level", [.5, 6.]), ("level_w", [0., 4.])):
            np.testing.assert_array_equal(saved[dim], labels)
            np.testing.assert_array_equal(saved[f"{dim}_source_native_index"], [0, 2])
            assert saved[dim].attrs["source_formula_terms"] == scene[dim].attrs["formula_terms"]
            assert "formula_terms" not in saved[dim].attrs
            assert "computed_standard_name" not in saved[dim].attrs
        assert saved.level.attrs["source_standard_name"] == "altitude"
        assert "standard_name" not in saved.level.attrs
        np.testing.assert_array_equal(saved.THT, scene.THT.isel(level=[0, 2]))
        np.testing.assert_array_equal(saved.WT, scene.WT.isel(level_w=[0, 2]))
        assert "level_w" in saved.ALT.dims and "level" not in saved.ALT.dims
        alt = saved.ALT.isel(time=0) if "time" in saved.ALT.dims else saved.ALT
        np.testing.assert_array_equal(alt, scene.ALT.isel(level_w=[0, 2]))
        assert "ZTOP" not in saved.variables


def test_altitude_formula_mass_transform_uses_native_labels_without_active_formula(tmp_path):
    scene = _native_altitude_scene()
    path = tmp_path / "native.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    raw = _native_altitude_request(tmp_path, [path])
    source = raw["sources"]["atmosphere"]
    source["variables"]["3d"] = ["THT", "WT"]
    source["transforms"] = [{"fields": ["WT"], "sampling": "mass"}]
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    product, = result.products
    with xr.open_dataset(product["path"], decode_coords=False) as saved:
        np.testing.assert_array_equal(saved.level, [.5, 6.])
        expected = np.broadcast_to(np.array([.5, 6.])[None, :, None, None], (1, 2, 3, 3)).copy()
        expected[0, 1, 1, 1] = np.nan
        np.testing.assert_allclose(saved.WT, expected, atol=1e-12, rtol=0)
        assert saved.level.attrs["source_formula_terms"] == scene.level.attrs["formula_terms"]
        assert "formula_terms" not in saved.level.attrs


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("case", ["missing_top", "complete", "missing_terrain", "different_grid"])
def test_w_only_mass_transform_binds_destination_altitude_formula(tmp_path, fmt, case):
    from frameit.core.preflight import collect_preflight

    scene = _native_altitude_scene().drop_vars(["UT", "VT", "THT", "ALT"])
    scene.level_w.attrs = {"units": "m"}
    if case != "missing_top":
        scene["ZTOP"] = xr.DataArray(20., attrs={"units": "m"})
    if case == "missing_terrain":
        scene = scene.drop_vars("ZS")
    if case == "different_grid":
        scene["ZS"] = scene.ZS.rename({"ni": "ni_u", "nj": "nj_u"})
    path = tmp_path / "native.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    raw = _native_altitude_request(tmp_path, [path], fmt=fmt)
    source = raw["sources"]["atmosphere"]
    source["variables"]["3d"] = ["WT"]
    source["transforms"] = [{"fields": ["WT"], "sampling": "mass"}]
    report = collect_preflight(raw)
    if case in {"missing_terrain", "different_grid"}:
        assert any("ZS" in e.message for e in report.errors), report.errors
        return
    assert not report.errors, report.errors
    warnings = report.facts["sources"]["atmosphere"]["field_binding"]["warnings"]
    if case == "missing_top":
        assert any("level" in warning and "ZTOP" in warning for warning in warnings)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    product, = result.products
    opened = (xr.open_zarr(product["path"], decode_coords=False, consolidated=False)
              if fmt == "zarr" else xr.open_dataset(product["path"], decode_coords=False))
    with opened as saved:
        np.testing.assert_array_equal(saved.level, [.5, 6.])
        if case == "complete":
            assert saved.level.attrs["formula_terms"] == scene.level.attrs["formula_terms"]
            assert saved.ZTOP.item() == 20.
            np.testing.assert_array_equal(saved.ZS, scene.ZS)
        else:
            assert saved.level.attrs["source_formula_terms"] == scene.level.attrs["formula_terms"]
            assert "formula_terms" not in saved.level.attrs


@pytest.mark.parametrize("case", [
    "partial", "complete", "requested", "ancillary", "conflict", "linked_first", "linked_last",
])
def test_altitude_formula_distinguishes_partial_complete_and_required_support(tmp_path, case):
    from frameit.core.preflight import collect_preflight

    scene = _native_altitude_scene()
    first, second = tmp_path / "first.nc", tmp_path / "second.nc"
    complete = scene.assign(ZTOP=xr.DataArray(20., attrs={"units": "m"}))
    if case.startswith("linked"):
        complete.THT.encoding = {"coordinates": "ZTOP latitude longitude"}
    complete.to_netcdf(first, engine="h5netcdf")
    missing = scene.assign_coords(time=scene.time.values + np.timedelta64(1, "h"))
    if case == "ancillary":
        missing.WT.attrs["ancillary_variables"] = "ZTOP"
    missing.to_netcdf(second, engine="h5netcdf")
    paths = [first, second]
    if case == "linked_last":
        paths.reverse()
    if case == "conflict":
        third = tmp_path / "third.nc"
        scene.assign_coords(time=scene.time.values + np.timedelta64(2, "h")).assign(
            ZTOP=xr.DataArray(.02, attrs={"units": "km"})).to_netcdf(third, engine="h5netcdf")
        paths.append(third)
    raw = _native_altitude_request(tmp_path, paths)
    atmosphere = raw["sources"]["atmosphere"]
    if case == "complete":
        atmosphere["time"] = {"values": ["2024-01-01T00:00:00"]}
    if case == "requested":
        atmosphere["variables"]["2d"] = ["ZTOP"]
    report = collect_preflight(raw)
    if case in {"requested", "ancillary", "conflict", "linked_first", "linked_last"}:
        assert any("ZTOP" in error.message for error in report.errors), report.errors
        assert not (tmp_path / "out").exists()
        return
    assert not report.errors, report.errors
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    product, = result.products
    with xr.open_dataset(product["path"], decode_coords=False) as saved:
        for dim in ("level", "level_w"):
            label = "formula_terms" if case == "complete" else "source_formula_terms"
            assert saved[dim].attrs[label] == scene[dim].attrs["formula_terms"]
        if case == "complete":
            assert saved.ZTOP.item() == 20.
        else:
            assert saved.sizes["time"] == 2 and "ZTOP" not in saved.variables
            assert "formula_terms" not in saved.level.attrs
            assert "formula_terms" not in saved.level_w.attrs


def test_altitude_optional_top_does_not_hide_required_terrain_of_same_name(tmp_path):
    from frameit.core.preflight import collect_preflight

    scene = _native_altitude_scene().drop_vars("ZS")
    for dim in ("level", "level_w"):
        scene[dim].attrs["formula_terms"] = f"s: {dim} height: ZS orog: ZS"
    path = tmp_path / "native.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    report = collect_preflight(_native_altitude_request(tmp_path, [path]))
    assert any("ZS" in error.message for error in report.errors), report.errors


@pytest.mark.parametrize("clock", ["time", "forecast_reference_time"])
def test_altitude_formula_support_cannot_borrow_a_conflicting_calendar(tmp_path, clock):
    from frameit.core.preflight import collect_preflight

    scene = _native_altitude_scene()
    top = xr.Dataset({"ZTOP": ((), 20., {"units": "m"})}, coords={"time": scene.time.values})
    if clock == "forecast_reference_time":
        reference = scene.time.values[0]
        scene = scene.assign_coords(forecast_reference_time=reference)
        top = top.assign_coords(forecast_reference_time=reference)
    scene.time.encoding["calendar"] = top.time.encoding["calendar"] = "standard"
    scene[clock].encoding["calendar"] = "standard"
    top[clock].encoding["calendar"] = "proleptic_gregorian"
    path, support = tmp_path / "fields.nc", tmp_path / "top.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    top.to_netcdf(support, engine="h5netcdf")
    report = collect_preflight(_native_altitude_request(tmp_path, [path, support]))
    assert any("calendar" in e.message and "ZTOP" in e.message for e in report.errors), report.errors


@pytest.mark.parametrize("file_count", [1, 2])
def test_preview_keeps_per_file_static_samples_separate_but_not_single_file_static(
        tmp_path, file_count):
    from frameit.core.preflight import collect_preflight

    times = np.array(["2000-01-01T00", "2000-01-01T01"], dtype="datetime64[ns]")
    files = []
    for index in range(file_count):
        scene = xr.Dataset(
            {"flux": (("latitude", "longitude"), np.full((3, 3), float(index)),
                      {"units": "W m-2"})},
            coords={"time": times if file_count == 1 else times[index:index + 1],
                    "latitude": ("latitude", [-20.01, -20., -19.99], {"units": "degrees_north"}),
                    "longitude": ("longitude", [59.99, 60., 60.01], {"units": "degrees_east"})})
        path = tmp_path / f"part{index}.nc"
        scene.to_netcdf(path)
        files.append(str(path))
    raw = {
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "arome", "files": files, "variables": {"2d": ["flux"]}}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"cpus": 1, "synchronous_export": True}}
    preview = collect_preflight(raw)
    assert not preview.errors
    planned = preview.facts["products"][0]["dimensions"]["flux"]
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert planned == list(saved.flux.dims)
        if file_count == 2:
            np.testing.assert_array_equal(saved.flux[:, 0, 0], [0., 1.])
        else:
            assert saved.flux.ndim == 2
            np.testing.assert_array_equal(saved.flux, 0.)


def test_missing_utrack_dependencies_do_not_promise_executable_v3_support(tmp_path, monkeypatch):
    import importlib.util

    from frameit.core.preflight import _required_dependencies

    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3,
        "sources": {"atmosphere": {"model": "arome", "files": str(tmp_path / "absent.grib")}},
        "region": {"tracker": {"method": "utrack", "weights_file": str(tmp_path / "weights.pt")}},
        "products": {"track": True},
        "output": {"directory": str(tmp_path / "out")}})
    available = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: (
        None if name in {"torch", "utrack"} else available(name, *a, **k)))
    facts, errors = _required_dependencies(conf)
    missing = [error for error in errors if error.path == "region.tracker"]
    assert len(missing) == 2
    assert {error.code for error in missing} == {"E1502"}
    assert all(error.repairs == ["UTrack v3 execution is unavailable; select another tracker."]
               for error in missing)
    assert {fact["module"] for fact in facts if fact["path"] == "region.tracker"} == {
        "torch", "utrack"}
    assert not conf.output_dir.exists()
