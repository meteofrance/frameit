"""Native regional NEMO copies: independent clocks, axes, missingness and grids."""

import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources
from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord


def nemo_scene(*, depth="deptht", field="votemper", shift_x=0., shift_y=0.):
    times = np.array(["2024-12-11T00:30", "2024-12-11T01:30", "2024-12-11T02:30"],
                     dtype="datetime64[ns]")
    lat = -20. + (np.arange(7) - 3)[:, None] * .01 + np.zeros((7, 7)) + shift_y
    lon = 60. + (np.arange(7) - 3)[None, :] * .01 / np.cos(np.deg2rad(20.)) + np.zeros((7, 7)) + shift_x
    values = np.arange(3 * 2 * 7 * 7, dtype=float).reshape(3, 2, 7, 7)
    values[0, 0, 3, 3] = 0.
    values[0, 0, 2, 2] = np.nan
    levels = [0., 2.] if depth == "depthw" else [1., 3.]
    ds = xr.Dataset({field: (("time_counter", depth, "y", "x"), values,
                            {"units": "degC", "long_name": "potential temperature",
                             "cell_methods": "time: mean (interval: 240 s)"})},
                    coords={"time_counter": ("time_counter", times, {"bounds": "time_counter_bounds"}),
                            "time_centered": ("time_counter", times, {"bounds": "time_centered_bounds"}),
                            depth: (depth, levels, {"positive": "down", "units": "m",
                                                   "bounds": f"{depth}_bounds"}),
                            "nav_lat": (("y", "x"), lat, {"units": "degrees_north", "standard_name": "latitude"}),
                            "nav_lon": (("y", "x"), lon, {"units": "degrees_east", "standard_name": "longitude"})})
    bounds = times[:, None] + np.array([-30, 30], dtype="timedelta64[m]")[None, :]
    for name in ("time_counter_bounds", "time_centered_bounds"):
        ds[name] = (("time_counter", "axis_nbounds"), bounds.copy())
        ds[name].encoding["units"] = "seconds since 2024-12-11"
    for name in ("time_counter", "time_centered"):
        ds[name].encoding["units"] = "seconds since 2024-12-11"
    ds[f"{depth}_bounds"] = ((depth, "axis_nbounds"), [[0., 2.], [2., 4.]])
    return ds


def nemo_document(tmp_path, paths, *, variables=None):
    return {"schema_version": "2.1", "model": "nemo", "run": {"name": "native-ocean"},
            "input": {"format": "netcdf", "files": list(map(str, paths)),
                      "netcdf": {"file_layout": "variables"}},
            "variables": variables or {"deptht": {"names": ["votemper"], "levels": {"indices": [0, 1]}}},
            "tracking": {"method": "fixed_box", "fixed_box": {"center": {"latitude": -20., "longitude": 60.}}},
            "domain": {"width_km": {"x": 2., "y": 2.}},
            "execution": {"dask_workers": 1, "native_threads": 1},
            "output": {"directory": str(tmp_path / "out"), "overwrite": False,
                       "synchronous_export": True, "max_workers": 1}}


def test_nemo_scalar_native_roundtrip(tmp_path, monkeypatch):
    import builtins

    from frameit.core.execution import execute_simulation

    source = nemo_scene()
    source["vodensity"] = source.votemper + 22.
    source.vodensity.attrs = {"units": "kg/m3", "long_name": "sigma-theta density anomaly"}
    path = tmp_path / "ocean.nc"
    source.to_netcdf(path)
    raw = nemo_document(tmp_path, [path], variables={"deptht": {"names": ["votemper", "vodensity"],
                                                             "levels": {"indices": [1, 0]}}})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    original_import = builtins.__import__

    def core_only(name, *args, **kwargs):
        if name.split(".")[0] in {"zarr", "xesmf", "ESMF", "esmpy", "epygram", "eccodes", "cfgrib"}:
            raise AssertionError(f"Native NEMO extraction tried optional import {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", core_only)
    result = execute_simulation(conf)
    assert result.ok, result
    product = next(p["path"] for p in result.products if p["role"] == "cart")
    # Ordinary reader in a fresh process: no FrameIt import or fixture helpers.
    subprocess.run([sys.executable, "-c", """
import netCDF4 as nc
import numpy as np
import sys
with nc.Dataset(sys.argv[1]) as out, nc.Dataset(sys.argv[2]) as source:
    np.testing.assert_array_equal(out['deptht'][:], [3., 1.])
    np.testing.assert_array_equal(out['deptht_source_native_index'][:], [1, 0])
    np.testing.assert_array_equal(out['deptht_bounds'][:], [[2., 4.], [0., 2.]])
    assert out['deptht'].positive == 'down' and out['deptht'].units == 'm'
    assert out['vodensity'].long_name == 'sigma-theta density anomaly'
    assert out['vodensity'].units == 'kg/m3'
    assert out['votemper'].cell_methods == 'time: mean (interval: 240 s)'
    for t in range(3):
        for z, original_z in enumerate([1, 0]):
            np.testing.assert_array_equal(out['votemper'][t,z], source['votemper'][t,original_z,2:5,2:5])
    assert 'time_counter_bounds' in out.variables and 'time_centered_bounds' in out.variables
    assert not any(n in out.variables for n in ('wind_speed','vrad','vtan'))
""", str(product), str(path)], check=True)


@pytest.mark.parametrize("problem", ["clock", "bounds", "calendar", "geography"])
def test_nemo_rejects_conflicting_native_definitions(problem):
    from frameit.io.nemo_utils import prepare_nemo

    ds = nemo_scene()
    if problem == "clock":
        ds["time_centered"] = ds.time_centered + np.timedelta64(1, "m")
    elif problem == "bounds":
        ds["time_centered_bounds"] = ds.time_centered_bounds + np.timedelta64(1, "m")
    elif problem == "calendar":
        ds.time_counter.encoding["calendar"] = "360_day"
    else:
        ds = ds.drop_vars("nav_lon")
    with pytest.raises(ValueError, match="clock|time|bounds|calendar|nav_lon|geography"):
        prepare_nemo(ds, SimpleNamespace())


@pytest.mark.parametrize("selection", ["surface", "close_value"])
def test_nemo_native_requests_fail_in_preflight_and_loader(tmp_path, selection):
    from frameit.core.preflight import preflight

    path = tmp_path / "ocean.nc"
    nemo_scene().to_netcdf(path)
    variables = {"surface": {"names": ["votemper"]}} if selection == "surface" else {
        "deptht": {"names": ["votemper"], "levels": {"values": [1.001]}}}
    conf = SimulationConfig.from_mapping_with_model_preset(nemo_document(tmp_path, [path], variables=variables))
    with pytest.raises(ValueError, match="surface|deptht|level|unavailable"):
        preflight(conf)
    with pytest.raises(ValueError, match="surface|deptht|level|unavailable"):
        concat_nc2ds_by_vert_coord([path], conf.requested_variables_user, {},
                                  concat_dimension="time_counter", wind_conf=conf, float_tol=.5)


def test_nemo_missingness_is_per_field_and_zero_is_valid(tmp_path):
    path = tmp_path / "ocean.nc"
    ds = nemo_scene()
    ds["vosaline"] = xr.full_like(ds.votemper, 0.)
    ds.vosaline.attrs = {"units": "1e-3", "long_name": "practical salinity"}
    ds["unrequested"] = ds.votemper * 100
    ds.to_netcdf(path, encoding={"votemper": {"_FillValue": 1e20}})
    conf = SimulationConfig.from_mapping_with_model_preset(nemo_document(tmp_path, [path], variables={
        "deptht": {"names": ["votemper", "vosaline"], "levels": "stored"}}))
    with DatasetResources() as resources:
        groups, _ = concat_nc2ds_by_vert_coord([path], conf.requested_variables_user, {},
            concat_dimension="time_counter", wind_conf=conf, resources=resources)
        result = groups["deptht"]
        assert "unrequested" not in result
        assert hasattr(result.votemper.data, "dask")
        assert np.isnan(result.votemper[0, 0, 2, 2])
        assert result.vosaline[0, 0, 2, 2] == 0.
        assert result.votemper[0, 0, 3, 3] == 0.


def test_nemo_init_inspect_replay_and_atmospheric_tracker_rejection(tmp_path):
    from frameit.core.configuration import resolved_configuration, write_template
    from frameit.core.preflight import preflight

    path = tmp_path / "ocean.nc"
    nemo_scene().to_netcdf(path)
    conf = SimulationConfig.from_mapping_with_model_preset(nemo_document(tmp_path, [path]))
    preflight(conf)
    replay = SimulationConfig.from_mapping_with_model_preset(resolved_configuration(conf))
    assert replay.atm_model == "NEMO" and replay.name_latitude == "nav_lat"
    template = tmp_path / "nemo.yaml"
    write_template("nemo", template)
    assert SimulationConfig.from_yaml_with_model_preset(template).tracking_method == "fixed_box"
    result = subprocess.run([sys.executable, "-m", "frameit", "inspect", str(tmp_path),
                             "--model", "nemo", "--format", "netcdf", "--pattern", "ocean.nc"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    raw = nemo_document(tmp_path, [path])
    raw["tracking"] = {"method": "wind_pressure"}
    with pytest.raises(ValueError, match="NEMO|nemo|fixed_box"):
        SimulationConfig.from_mapping_with_model_preset(raw)


def test_nemo_scalar_shards_reject_equal_shape_different_geography(tmp_path):
    from frameit.core.preflight import preflight

    paths = [tmp_path / "temperature.nc", tmp_path / "salinity.nc"]
    nemo_scene().to_netcdf(paths[0])
    nemo_scene(field="vosaline", shift_x=.005).to_netcdf(paths[1])
    raw = nemo_document(tmp_path, paths, variables={"deptht": {"names": ["votemper", "vosaline"],
                                                             "levels": "stored"}})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="coordinate|geography"):
        preflight(conf)


def test_nemo_detected_non_netcdf_fails_before_optional_reader(tmp_path, monkeypatch):
    from frameit.core import preflight as module

    path = tmp_path / "wrong-format.grib"
    path.write_bytes(b"GRIB" + bytes(16))
    raw = nemo_document(tmp_path, [path])
    raw["input"]["format"] = None
    conf = SimulationConfig.from_mapping_with_model_preset(raw)

    def forbidden(*args):
        raise AssertionError("NEMO must reject GRIB before entering its optional decoder")

    monkeypatch.setattr(module, "_grib_metadata", forbidden)
    with pytest.raises(ValueError, match="NEMO.*NetCDF"):
        module.preflight(conf)


def component_scene(depth, field, **shifts):
    ds = nemo_scene(depth=depth, field=field, **shifts)
    ds[field].attrs.update(units="m/s", long_name="native ocean component", standard_name={
        "vozocrtx": "sea_water_x_velocity", "vomecrty": "sea_water_y_velocity",
        "vovecrtz": "upward_sea_water_velocity"}[field])
    return ds


def test_nemo_equal_dimension_names_keep_independent_geography(tmp_path):
    from frameit.core.execution import execute_simulation

    cases = [("deptht", "votemper", 0., 0., 2, 2),
             ("depthu", "vozocrtx", .006, 0., 1, 2),
             ("depthv", "vomecrty", 0., .006, 2, 1),
             ("depthw", "vovecrtz", 0., 0., 2, 2)]
    for depth, field, dx, dy, x0, y0 in cases:
        source = nemo_scene() if depth == "deptht" else component_scene(depth, field, shift_x=dx, shift_y=dy)
        path = tmp_path / f"{depth}.nc"
        source.to_netcdf(path)
        raw = nemo_document(tmp_path, [path], variables={depth: {"names": [field], "levels": {"indices": [1, 0]}}})
        raw["output"].update(directory=str(tmp_path / depth), cartesian={"horizontal_vectors": "native"})
        result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
        assert result.ok, result
        product = next(p["path"] for p in result.products if p["role"] == "cart")
        with xr.open_dataset(product) as out:
            np.testing.assert_array_equal(out.x[0], np.arange(x0, x0+3))
            np.testing.assert_array_equal(out.y[0], np.arange(y0, y0+3))
            np.testing.assert_array_equal(out[field], source[field].values[:, [1, 0], y0:y0+3, x0:x0+3])
            np.testing.assert_array_equal(out.nav_lon[0], source.nav_lon[y0:y0+3, x0:x0+3])
            np.testing.assert_array_equal(out.nav_lat[0], source.nav_lat[y0:y0+3, x0:x0+3])
            np.testing.assert_array_equal(out[f"{depth}_bounds"], [[2., 4.], [0., 2.]])
            np.testing.assert_array_equal(out[depth], [2., 0.] if depth == "depthw" else [3., 1.])
        subprocess.run([sys.executable, "-c", """
import netCDF4 as nc
import numpy as np
import sys
path, source_path, field, depth, x0, y0 = sys.argv[1:]
x0, y0 = int(x0), int(y0)
with nc.Dataset(path) as out, nc.Dataset(source_path) as source:
    actual = out[field][:]
    expected = source[field][:, [1,0], y0:y0+3, x0:x0+3]
    np.testing.assert_array_equal(np.ma.getmaskarray(actual), np.ma.getmaskarray(expected))
    np.testing.assert_array_equal(actual.compressed(), expected.compressed())
    np.testing.assert_array_equal(out['nav_lat'][0], source['nav_lat'][y0:y0+3, x0:x0+3])
    np.testing.assert_array_equal(out['nav_lon'][0], source['nav_lon'][y0:y0+3, x0:x0+3])
    np.testing.assert_array_equal(out[depth][:], source[depth][[1,0]])
    assert np.any(actual == 0.)
    assert out[field].units == source[field].units
    assert 'horizontal_wind_representation' not in out.ncattrs()
""", str(product), str(path), field, depth, str(x0), str(y0)], check=True)
    # A T/U source cannot be assembled as complementary fields on one grid.
    raw = nemo_document(
        tmp_path, [tmp_path / "deptht.nc", tmp_path / "depthu.nc"], variables={
            "deptht": {"names": ["votemper"], "levels": "stored"},
            "depthu": {"names": ["vozocrtx"], "levels": "stored"}})
    raw["output"]["cartesian"] = {"horizontal_vectors": "native"}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="coordinate|geography"):
        concat_nc2ds_by_vert_coord(conf.input_files, conf.requested_variables_user, {},
                                  concat_dimension="time_counter", wind_conf=conf, file_layout="variables")


def test_nemo_native_components_never_call_wind_preparation(tmp_path, monkeypatch):
    from frameit.core.execution import execute_simulation

    def forbidden(*args, **kwargs):
        raise AssertionError("Ocean components must not execute atmospheric wind preparation")

    for target in ("frameit.processing.derived.wind.normalize_winds",
                   "frameit.processing.derived.wind.normalize_native_wind_units",
                   "frameit.processing.derived.wind.normalize_velocity_units",
                   "frameit.processing.wind_collocation.prepare_native_mnh",
                   "frameit.core.runner.add_speed_from_uv_dict",
                   "frameit.core.runner.select_vertical_velocity",
                   "frameit.processing.extraction.add_speed_from_uv_dict"):
        monkeypatch.setattr(target, forbidden)
    ds = component_scene("depthu", "vozocrtx")
    ds["sozotaux"] = (("time_counter", "y", "x"), np.zeros((3, 7, 7)),
                      {"units": "N/m2", "standard_name": "surface_downward_x_stress"})
    path = tmp_path / "components.nc"
    ds.to_netcdf(path)
    raw = nemo_document(tmp_path, [path], variables={
        "depthu": {"names": ["vozocrtx"], "levels": "stored"}, "surface": {"names": ["sozotaux"]}})
    raw["output"]["cartesian"] = {"horizontal_vectors": "native"}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    for product in result.products:
        if product["role"] != "cart":
            continue
        with xr.open_dataset(product["path"]) as out:
            assert "horizontal_wind_representation" not in out.attrs
            assert "vertical_velocity_representation" not in out.attrs
            assert not {"wind_speed", "vrad", "vtan"} & set(out.variables)
            name = "vozocrtx" if product["group"] == "depthu" else "sozotaux"
            assert out[name].attrs["units"] == ds[name].attrs["units"]
            assert out[name].attrs["standard_name"] == ds[name].attrs["standard_name"]


@pytest.mark.parametrize("analysis", ["mass_earth", "polar"])
def test_unqualified_nemo_vector_analysis_fails_actionably(tmp_path, analysis):
    from frameit.core.preflight import preflight

    path = tmp_path / "current.nc"
    component_scene("depthu", "vozocrtx").to_netcdf(path)
    raw = nemo_document(tmp_path, [path], variables={"depthu": {"names": ["vozocrtx"], "levels": "stored"}})
    raw["output"]["cartesian"] = {"horizontal_vectors": "native" if analysis == "polar" else "earth_centered"}
    if analysis == "polar":
        raw["polar"] = {"enabled": True}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="NEMO.*native|NEMO.*analysis|NEMO.*polar"):
        preflight(conf)
    with pytest.raises(ValueError, match="NEMO.*native|NEMO.*analysis|NEMO.*polar"):
        concat_nc2ds_by_vert_coord([path], conf.requested_variables_user, {},
                                  concat_dimension="time_counter", wind_conf=conf)


def test_nemo_vertical_mass_analysis_is_not_a_native_copy(tmp_path):
    from frameit.core.preflight import preflight

    path = tmp_path / "vertical.nc"
    component_scene("depthw", "vovecrtz").to_netcdf(path)
    raw = nemo_document(tmp_path, [path], variables={"depthw": {"names": ["vovecrtz"], "levels": "stored"}})
    raw["output"]["cartesian"] = {"horizontal_vectors": "native", "vertical_velocity": "mass"}
    with pytest.raises(ValueError, match="NEMO.*depthw|NEMO.*native"):
        preflight(SimulationConfig.from_mapping_with_model_preset(raw))


@pytest.mark.parametrize("attribute", ["units", "standard_name", "long_name", "cell_methods",
                                       "depth_units", "positive"])
def test_nemo_time_series_rejects_changes_in_scientific_meaning(tmp_path, attribute):
    from frameit.core.preflight import preflight

    first = nemo_scene().isel(time_counter=[0])
    second = nemo_scene().isel(time_counter=[1])
    for ds in (first, second):
        ds.votemper.attrs["standard_name"] = "sea_water_potential_temperature"
    if attribute == "depth_units":
        second.deptht.attrs["units"] = "km"
    elif attribute == "positive":
        second.deptht.attrs["positive"] = "up"
    else:
        second.votemper.attrs[attribute] = {"units": "K", "standard_name": "sea_water_temperature",
            "long_name": "density anomaly", "cell_methods": "time: point"}[attribute]
    paths = [tmp_path / "first.nc", tmp_path / "second.nc"]
    first.to_netcdf(paths[0])
    second.to_netcdf(paths[1])
    raw = nemo_document(tmp_path, paths)
    raw["input"]["netcdf"]["file_layout"] = "time_series"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="NEMO.*metadata|NEMO.*units|NEMO.*meaning"):
        preflight(conf)
    with pytest.raises(ValueError, match="NEMO.*metadata|NEMO.*units|NEMO.*meaning"):
        concat_nc2ds_by_vert_coord(paths, conf.requested_variables_user, {},
                                  concat_dimension="time_counter", wind_conf=conf)


@pytest.mark.parametrize("conflict", [False, True])
def test_nemo_time_series_validates_original_data_variable_clock(tmp_path, conflict):
    ds = nemo_scene().reset_coords("time_centered")
    if conflict:
        ds["time_centered"] = ds.time_centered + np.timedelta64(1, "m")
        ds.time_centered.attrs["bounds"] = "time_centered_bounds"
        ds.time_centered.encoding["units"] = "seconds since 2024-12-11"
    path = tmp_path / "clock.nc"
    ds.to_netcdf(path)
    raw = nemo_document(tmp_path, [path])
    raw["input"]["netcdf"]["file_layout"] = "time_series"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)

    def load():
        return concat_nc2ds_by_vert_coord([path], conf.requested_variables_user, {},
                                          concat_dimension="time_counter", wind_conf=conf)

    if conflict:
        with pytest.raises(ValueError, match="sample clocks disagree"):
            load()
    else:
        groups, _ = load()
        try:
            result = groups["deptht"]
            np.testing.assert_array_equal(result.time_centered, ds.time_centered)
            np.testing.assert_array_equal(result.time_centered_bounds, ds.time_centered_bounds)
        finally:
            groups["deptht"].close()
