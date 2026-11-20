"""Small real v3 regional inputs; numerical preservation is not scientific sign-off."""

import subprocess
import sys

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.configuration import to_runtime
from frameit.core.coupled import bind_sources
from frameit.core.execution import execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.io.track_file import load_track_coordinates


def configuration(tmp_path, sources, *, region=None, products=None, output=None):
    raw = {
        "schema_version": 3, "run": {"name": "regional"}, "sources": sources,
        "output": {"directory": str(tmp_path / "out"), **(output or {})},
        "resources": {"synchronous_export": True, "scheduler": "synchronous", "cpus": 1},
    }
    if region is not None:
        raw["region"] = region
    if products is not None:
        raw["products"] = products
    return SimulationConfig(**to_runtime(raw, base_dir=tmp_path))


def trajectory(path, *, times=None):
    times = np.array(times or ["2000-01-01T02", "2000-01-01T00", "2000-01-01T01"],
                     dtype="datetime64[ns]")
    ds = xr.Dataset({
        "north": ("observation", np.full(len(times), -20.),
                  {"standard_name": "latitude", "units": "degrees_north"}),
        "east": ("observation", np.full(len(times), 60.),
                 {"standard_name": "longitude", "units": "degrees_east"}),
    }, coords={"stamp": ("observation", times, {"standard_name": "time"})})
    ds.to_netcdf(path)
    return ds


def test_trajectory_discovers_cf_names_and_sorts(tmp_path):
    path = tmp_path / "track.nc"
    trajectory(path)
    track = load_track_coordinates(path)
    np.testing.assert_array_equal(track.time, np.array(
        ["2000-01-01T00", "2000-01-01T01", "2000-01-01T02"], dtype="datetime64[ns]"))
    np.testing.assert_array_equal(track.latitude, [-20., -20., -20.])
    assert track.latitude.attrs["units"] == "degrees_north"


@pytest.mark.parametrize("units", ["radians", "singular_degrees"])
def test_trajectory_converts_explicit_compatible_angular_units(tmp_path, units):
    ds = trajectory(tmp_path / "unused.nc")
    if units == "radians":
        ds.north.values[:] = -np.pi / 9
        ds.east.values[:] = np.pi / 3
        ds.north.attrs["units"] = ds.east.attrs["units"] = "radians"
    else:
        ds.north.attrs["units"] = "degree_north"
        ds.east.attrs["units"] = "degree_east"
    ds.to_netcdf(tmp_path / "track.nc")
    result = load_track_coordinates(tmp_path / "track.nc")
    np.testing.assert_allclose(result.latitude, [-20.] * 3, atol=1e-14)
    np.testing.assert_allclose(result.longitude, [60.] * 3, atol=1e-14)


@pytest.mark.parametrize("problem,match", [
    ("duplicate", "duplicate"), ("missing_units", "units"),
    ("wrong_units", "units"), ("conflicting_name", "conflict"),
    ("ambiguous", "ambiguous"), ("dimension", "dimension"),
    ("nonfinite", "finite"),
])
def test_trajectory_rejects_ambiguous_or_invalid_evidence(tmp_path, problem, match):
    ds = trajectory(tmp_path / "unused.nc").rename(
        {"north": "latitude", "east": "longitude", "stamp": "time", "observation": "time"})
    if problem == "duplicate":
        ds = ds.assign_coords(time=("time", [ds.time.values[0]] * 3, ds.time.attrs))
    elif problem == "missing_units":
        ds.latitude.attrs.pop("units")
    elif problem == "wrong_units":
        ds.latitude.attrs["units"] = "degrees_east"
    elif problem == "conflicting_name":
        ds = ds.rename(latitude="lon").drop_vars("longitude")
    elif problem == "ambiguous":
        ds["other"] = ds.latitude
    elif problem == "dimension":
        ds["longitude"] = ("another", [60.] * 3, ds.longitude.attrs)
    else:
        ds.latitude.values[1] = np.nan
    path = tmp_path / "broken.nc"
    ds.to_netcdf(path)
    with pytest.raises(ValueError, match=match):
        load_track_coordinates(path)


def scalar_scene(path, *, model="mesonh", hours=(0, 1, 2), shift=0., angle=120.):
    y, x = np.meshgrid(np.arange(7.) * 1000, np.arange(7.) * 1000, indexing="ij")
    theta = np.deg2rad(angle)
    east = (x - 3000) * np.cos(theta) - (y - 3000) * np.sin(theta)
    north = (x - 3000) * np.sin(theta) + (y - 3000) * np.cos(theta)
    clock, yd, xd, lat, lon = (
        ("time", "nj", "ni", "latitude", "longitude") if model == "mesonh" else
        ("time_counter", "y", "x", "nav_lat", "nav_lon"))
    values = np.arange(len(hours) * 49, dtype="float64").reshape(len(hours), 7, 7)
    values[0, 3, 3] = 0.
    values[:, 2, 3] = np.nan
    ds = xr.Dataset({"scalar": ((clock, yd, xd), values, {"units": "1"})}, coords={
        clock: np.datetime64("2000-01-01T00", "ns") + np.array(hours, dtype="timedelta64[h]"),
        yd: (yd, np.arange(7.) * 1000 + shift, {"units": "m"}),
        xd: (xd, np.arange(7.) * 1000 + shift, {"units": "m"}),
        lat: ((yd, xd), -20 + north / 111000 + shift / 111000,
              {"standard_name": "latitude", "units": "degrees_north"}),
        lon: ((yd, xd), 60 + east / (111000 * np.cos(np.deg2rad(20))),
              {"standard_name": "longitude", "units": "degrees_east"}),
    })
    ds.to_netcdf(path)
    return {"model": model, "files": str(path), "variables": {"2d": ["scalar"]}}


@pytest.mark.parametrize("model", ["mesonh", "croco", "nemo"])
def test_full_native_copy_ignores_unused_fixed_centre(tmp_path, model):
    from frameit.testing.numerical.test_croco_netcdf import croco_scene
    from frameit.testing.numerical.test_nemo_netcdf import nemo_scene

    path = tmp_path / "input.nc"
    if model == "mesonh":
        source = scalar_scene(path)
    else:
        fixture, field = (croco_scene, "temp") if model == "croco" else (nemo_scene, "votemper")
        fixture().to_netcdf(path)
        source = {"model": model, "files": str(path), "variables": {
            "3d": [field], "levels": {"indices": [0]}}}
    outputs = []
    for region in (None, {"center": {"latitude": -20., "longitude": 160.}}):
        conf = configuration(tmp_path, {"data": source}, region=region, output={
            "directory": str(tmp_path / ("fixed" if region else "no-region"))})
        report, _, _ = bind_sources(conf)
        assert not conf.output_dir.exists()
        result = execute_simulation(conf)
        assert result.ok and len(result.products) == 1
        with xr.open_dataset(result.products[0]["path"]) as saved:
            outputs.append(saved.load())
        if region:
            facts = report["sources"]["data"]["region"]
            assert facts["status"] == "unused"
            assert facts["unused_settings"] == [
                "region.center", "region.sources_coupling_time_association"]
            assert report["products"][0]["time_association"] is None
            provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
            assert provenance["sources"]["data"]["region"] == facts
            resolved = yaml.safe_load((conf.output_dir / "resolved-config.yaml").read_text())
            assert resolved["region"]["center"] == region["center"]
    for out in outputs:
        out.attrs.pop("history")
    xr.testing.assert_identical(*outputs)


@pytest.mark.parametrize("operation", ["crop", "polar"])
def test_outside_fixed_centre_remains_invalid_for_active_sampling(tmp_path, operation):
    source = scalar_scene(tmp_path / "weather.nc")
    source["field_metadata"] = {"scalar": {"kind": "continuous"}}
    region = {"center": {"latitude": -20., "longitude": 160.}}
    if operation == "crop":
        region["width_km"] = {"x": 2, "y": 2}
    conf = configuration(tmp_path, {"weather": source}, region=region, products=(
        {"polar": {"radius_km": 2.5, "azimuth_count": 8}} if operation == "polar" else None))
    with pytest.raises(ValueError, match="outside"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def test_disjoint_clocks_need_no_common_association_for_native_copies(tmp_path):
    sources = {
        "weather": scalar_scene(tmp_path / "weather.nc", hours=(0, 2)),
        "water": scalar_scene(tmp_path / "water.nc", model="nemo", hours=(1, 3)),
    }
    region = {"center": {"latitude": -20., "longitude": 60.},
              "sources_coupling_time_association": "common"}
    tracked = configuration(tmp_path, sources, region=region,
                            products={"model_grid": True, "track": True})
    with pytest.raises(ValueError, match="no exact common timestamps"):
        bind_sources(tracked)
    assert not tracked.output_dir.exists()
    conf = configuration(tmp_path, sources, region=region)
    bind_sources(conf)
    assert not conf.output_dir.exists()
    result = execute_simulation(conf)
    assert len(result.products) == 2
    for product in result.products:
        hours = [0, 2] if product["source"] == "weather" else [1, 3]
        with xr.open_dataset(product["path"]) as saved:
            np.testing.assert_array_equal(saved.time, np.datetime64("2000-01-01", "ns")
                                          + np.array(hours, dtype="timedelta64[h]"))
            assert "center_time" not in saved


@pytest.mark.parametrize("partial", [False, True])
def test_fixed_region_preserves_native_orientation_padding_and_geometry(tmp_path, partial):
    source = tmp_path / "weather.nc"
    declaration = scalar_scene(source)
    with xr.open_dataset(source) as ds:
        j, i = (0, 0) if partial else (3, 3)
        lat, lon = float(ds.latitude[j, i]), float(ds.longitude[j, i])
    conf = configuration(tmp_path, {"weather": declaration}, region={
        "center": {"latitude": lat + .0001, "longitude": lon + (-.0001 if partial else .0001)},
        "width_km": {"x": 2, "y": 2},
    })
    result = execute_simulation(conf)
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source:
    partial = sys.argv[3] == 'True'
    expected = np.full((3, 3, 3), np.nan)
    if partial:
        expected[:, 1:, 1:] = source.scalar.values[:, :2, :2]
    else:
        expected = source.scalar.values[:, 2:5, 2:5]
    np.testing.assert_array_equal(out.scalar, expected)
    assert out.scalar.attrs == source.scalar.attrs
    assert out.attrs['region_orientation'] == 'native source x/y; no basis rotation'
    assert out.attrs['region_requested_width_x_km'] == 2
    assert out.attrs['region_realised_span_x_km'] == 2
    np.testing.assert_allclose(out.center_latitude - out.grid_selected_latitude, .0001)
    assert bool((out.region_coverage_fraction < 1).all()) == partial
assert 'frameit' not in sys.modules
""", result.products[0]["path"], str(source), str(partial)],
        check=True, capture_output=True, text=True)
    assert len(result.products) == 1
    assert not list((conf.output_dir / "products").glob("*track*"))
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    facts = next(iter(provenance["sources"]["weather"]["region"]["grids"].values()))
    assert facts["requested_width_km"] == {"x": 2, "y": 2}
    assert facts["realised_span_km"] == {"x": 2., "y": 2.}
    assert facts["coverage_fraction"] == ([4 / 9] * 3 if partial else [1.] * 3)


def test_fixed_crop_uses_native_axes_when_geography_is_transposed(tmp_path):
    path = tmp_path / "weather.nc"
    source = scalar_scene(path, angle=0)
    with xr.open_dataset(path) as original:
        native = original.load()
    native = native.assign_coords({
        name: native[name].transpose("ni", "nj") for name in ("latitude", "longitude")})
    native.to_netcdf(path, mode="w")
    conf = configuration(tmp_path, {"weather": source}, region={
        "center": {"latitude": -20, "longitude": 60}, "width_km": {"x": 2, "y": 4}})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_array_equal(out.scalar.isel(time=0), [
            [9., 10., 11.], [16., np.nan, 18.], [23., 0., 25.],
            [30., 31., 32.], [37., 38., 39.]])
        np.testing.assert_array_equal(out.scalar, native.scalar.isel(
            nj=slice(1, 6), ni=slice(2, 5)))
        for name in ("latitude", "longitude"):
            expected = native[name].transpose("nj", "ni").isel(nj=slice(1, 6), ni=slice(2, 5))
            np.testing.assert_array_equal(out[name].transpose("time", "y", "x"),
                                          np.broadcast_to(expected, (3, 5, 3)))
            assert out[name].attrs == native[name].attrs
        np.testing.assert_array_equal(out.x, [0, 1, 2])
        np.testing.assert_array_equal(out.ni_source_native_index, [[2, 3, 4]] * 3)
        np.testing.assert_array_equal(out.grid_selected_latitude, [-20.] * 3)
        np.testing.assert_array_equal(out.grid_selected_longitude, [60.] * 3)


def test_equivalent_geography_units_keep_native_products_and_degree_grid_facts(tmp_path):
    fields = []
    for units in ("degrees", "radians"):
        directory = tmp_path / units
        directory.mkdir()
        path = directory / "weather.nc"
        source = scalar_scene(path)
        with xr.open_dataset(path) as original:
            degrees = original.load()
        native = degrees.copy(deep=True)
        if units == "radians":
            for name in ("latitude", "longitude"):
                native[name] = np.deg2rad(native[name]).assign_attrs(
                    dict(native[name].attrs, units="radians"))
        native.to_netcdf(path, mode="w")
        before = path.read_bytes()
        latitude, longitude = float(degrees.latitude[2, 4]), float(degrees.longitude[2, 4])
        conf = configuration(directory, {"weather": source}, region={
            "center": {"latitude": latitude, "longitude": longitude},
            "width_km": {"x": 2, "y": 4}})
        result = execute_simulation(conf)
        with xr.open_dataset(result.products[0]["path"]) as out:
            fields.append(out.scalar.values.copy())
            np.testing.assert_array_equal(out.scalar, native.scalar.isel(
                nj=slice(0, 5), ni=slice(3, 6)))
            for name in ("latitude", "longitude"):
                expected = native[name].isel(nj=slice(0, 5), ni=slice(3, 6))
                np.testing.assert_array_equal(out[name].transpose("time", "y", "x"),
                                              np.broadcast_to(expected, (3, 5, 3)))
                assert out[name].attrs == native[name].attrs
            np.testing.assert_array_equal(out.ni_source_native_index, [[3, 4, 5]] * 3)
            for name, value, unit in (("latitude", latitude, "degrees_north"),
                                      ("longitude", longitude, "degrees_east")):
                for prefix in ("center_", "grid_selected_"):
                    np.testing.assert_allclose(out[prefix + name], value, rtol=0, atol=1e-12)
                    assert out[prefix + name].attrs["units"] == unit
        provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
        facts = next(iter(provenance["sources"]["weather"]["region"]["grids"].values()))
        assert facts["native_x_indices"] == [4] * 3
        assert facts["native_y_indices"] == [2] * 3
        for name, key in (("latitude", "sample_lat"), ("longitude", "sample_lon")):
            np.testing.assert_allclose(facts["geometry"][key], degrees[name], rtol=0, atol=1e-12)
        assert path.read_bytes() == before
    np.testing.assert_array_equal(*fields)


def test_exact_region_uses_union_centres_without_intersecting_native_clocks(tmp_path):
    sources = {
        "weather": scalar_scene(tmp_path / "weather.nc", hours=(0, 2)),
        "water": scalar_scene(tmp_path / "water.nc", model="nemo", hours=(1,), shift=250.),
    }
    trajectory(tmp_path / "track.nc")
    conf = configuration(tmp_path, sources, region={
        "track": {"file": "./track.nc"}, "width_km": {"x": 2, "y": 2},
    }, products={"model_grid": True, "track": True})
    result = execute_simulation(conf)
    assert len(result.products) == 3
    for source, hours in (("weather", [0, 2]), ("water", [1])):
        path = next(p["path"] for p in result.products if p["source"] == source)
        with xr.open_dataset(path) as out:
            np.testing.assert_array_equal(out.time, np.datetime64("2000-01-01", "ns")
                                          + np.array(hours, dtype="timedelta64[h]"))
            np.testing.assert_array_equal(out.center_time, out.time)
    track = next(p["path"] for p in result.products if p["role"] == "track")
    subprocess.run([sys.executable, "-c", """
import sys, xarray as xr, numpy as np
with xr.open_dataset(sys.argv[1]) as out:
    assert out.latitude.dims == out.longitude.dims == out.time.dims == ('time',)
    assert out.latitude.attrs['standard_name'] == 'latitude'
    assert out.latitude.attrs['units'] == 'degrees_north'
    assert out.longitude.attrs['standard_name'] == 'longitude'
    assert out.longitude.attrs['units'] == 'degrees_east'
    assert 'since' in out.time.encoding['units'] and out.time.encoding['calendar']
    assert out.sizes['time'] == 3
    np.testing.assert_array_equal(out.latitude, [-20.] * 3)
assert 'frameit' not in sys.modules
""", track], check=True, capture_output=True, text=True)


def test_missing_exact_centres_and_outside_footprint_fail_before_ownership(tmp_path):
    sources = {"weather": scalar_scene(tmp_path / "weather.nc")}
    trajectory(tmp_path / "track.nc", times=["2000-01-01T00"])
    conf = configuration(tmp_path, sources, region={"track": {"file": "./track.nc"}})
    with pytest.raises(ValueError, match="centre|center"):
        execute_simulation(conf)
    assert not conf.output_dir.exists()
    conf = configuration(tmp_path, sources, region={
        "center": {"latitude": 0, "longitude": 0}, "width_km": {"x": 2, "y": 2}})
    with pytest.raises(ValueError, match="outside"):
        execute_simulation(conf)
    assert not conf.output_dir.exists()


def pressure_wind_scene(path):
    declaration = scalar_scene(path)
    with xr.open_dataset(path) as original:
        ds = original.load()
    for name, unit in (("MSLP", "hPa"), ("UM10", "km h-1"), ("VM10", "m s-1")):
        values = np.full(ds.scalar.shape, 1000. if name == "MSLP" else 10.)
        values[:, 3, 3] = 950. if name == "MSLP" else 0.
        attrs = {"units": unit}
        if name != "MSLP":
            attrs["standard_name"] = "eastward_wind" if name == "UM10" else "northward_wind"
        ds[name] = (ds.scalar.dims, values, attrs)
    ds.to_netcdf(path, mode="w")
    declaration["time"] = {"stride": 2}
    return declaration


@pytest.mark.parametrize("dependency_only", [False, True])
def test_calculated_tracker_uses_atmosphere_and_actual_sparse_payload_reads(
        tmp_path, monkeypatch, dependency_only):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    import frameit.tracking.PressureWind_Tracker as pressure_module

    atmosphere = pressure_wind_scene(tmp_path / "weather.nc")
    atmosphere["variables"]["2d"] = ["UM10"]
    ocean = scalar_scene(tmp_path / "water.nc", model="nemo", hours=(0, 2))
    conf = configuration(tmp_path, {"water_first": ocean, "renamed_weather": atmosphere},
        region={"tracker": {"method": "pressure_wind"}},
        products={"model_grid": {"fields": (
            {"water_first": ["scalar"]} if dependency_only else
            {"water_first": ["scalar"], "renamed_weather": ["UM10"]})}, "track": True})
    reads, windows = [], []
    original = H5NetCDFArrayWrapper.__getitem__
    algorithm = pressure_module.pressure_wind_tracker

    def read(array, key):
        if array.variable_name in {"MSLP", "UM10", "VM10"}:
            selected = np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist()
            assert set(selected) <= {0, 2}
            reads.extend((array.variable_name, i) for i in selected)
        return original(array, key)

    def track(*args, **kwargs):
        windows.append((kwargs["half_search"], kwargs["half_refine"]))
        return algorithm(*args, **kwargs)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", read)
    monkeypatch.setattr(pressure_module, "pressure_wind_tracker", track)
    result = execute_simulation(conf)
    assert set(reads) == {(name, i) for name in ("MSLP", "UM10", "VM10") for i in (0, 2)}
    assert windows == [(100, 50)]  # 200/100 full km widths on the 1-km fixture.
    binding = conf.source_requests["renamed_weather"]["binding"]
    assert binding["status"] == "bound"
    assert {"MSLP", "UM10", "VM10"} <= binding["dependencies"].keys()
    if not dependency_only:
        product = next(p["path"] for p in result.products if p["source"] == "renamed_weather")
        with xr.open_dataset(product) as out, xr.open_dataset(tmp_path / "weather.nc") as source:
            np.testing.assert_array_equal(out.UM10, source.UM10.isel(time=[0, 2]))
            assert out.UM10.attrs == source.UM10.attrs
            assert set(out.data_vars) == {"UM10"}
    with xr.open_dataset(next(p["path"] for p in result.products if p["role"] == "track")) as out:
        np.testing.assert_allclose(out.latitude, [-20., -20.])
        np.testing.assert_allclose(out.longitude, [60., 60.])
        assert out.sizes["time"] == 2


@pytest.mark.parametrize("lead_layout", ["scalar", "time", "shifted_grid"])
def test_arome_tracker_joins_stationary_forecast_shards(tmp_path, lead_layout):
    cycle = np.datetime64("2026-01-01")
    leads = np.array([6, 12], dtype="timedelta64[h]")
    dims = ("valid_time", "latitude", "longitude")
    pressure = np.full((1, 7, 7), 100000.)
    wind = np.full_like(pressure, 10.)
    pressure[0, 3, 3], wind[0, 3, 3] = 95000., 0.
    paths = []
    for index, lead in enumerate(leads):
        lead_attrs = {"standard_name": "forecast_period"}
        shift = .02 if lead_layout == "shifted_grid" and index else 0.
        scene = xr.Dataset({
            "prmsl": (dims, pressure, {"units": "Pa"}),
            "u10": (dims, wind, {"units": "m s-1", "standard_name": "eastward_wind"}),
            "v10": (dims, wind, {"units": "m s-1", "standard_name": "northward_wind"}),
        }, coords={
            "valid_time": [cycle + lead],
            "time": ((), cycle, {"standard_name": "forecast_reference_time"}),
            "step": (((), lead, lead_attrs) if lead_layout == "scalar" else
                     ("valid_time", [lead], lead_attrs)),
            "latitude": ("latitude", -20. + (np.arange(7) - 3)*.01, {"units": "degrees_north"}),
            "longitude": ("longitude", 60. + shift + (np.arange(7) - 3)*.01,
                          {"units": "degrees_east"}),
        })
        path = tmp_path / f"lead-{index}.nc"
        scene.to_netcdf(path, engine="h5netcdf")
        paths.append(str(path))
    conf = configuration(tmp_path, {"weather": {
        "model": "arome", "files": paths, "variables": {"2d": ["prmsl"]}}},
        region={"tracker": {"method": "pressure_wind"}},
        products={"model_grid": True, "track": True})
    if lead_layout == "shifted_grid":
        with pytest.raises(ValueError, match="distinct fields share requested name"):
            execute_simulation(conf)
        return
    result = execute_simulation(conf)
    assert result.tracking_complete
    with xr.open_dataset(next(p["path"] for p in result.products if p["role"] == "track")) as track:
        np.testing.assert_array_equal(track.time, cycle + leads)
        np.testing.assert_array_equal(track.latitude, [-20., -20.])
        np.testing.assert_array_equal(track.longitude, [60., 60.])
    with xr.open_dataset(next(p["path"] for p in result.products
                              if p["role"] == "model_grid")) as native:
        np.testing.assert_array_equal(native.time, cycle + leads)
        np.testing.assert_array_equal(native.step, leads)
        assert native.step.dims == ("time",)


@pytest.mark.parametrize("crop", [False, True])
def test_common_association_excludes_only_the_regional_operation(tmp_path, crop):
    sources = {
        "weather": scalar_scene(tmp_path / "weather.nc"),
        "water": scalar_scene(tmp_path / "water.nc", model="nemo", hours=(1, 2)),
    }
    conf = configuration(tmp_path, sources, region={
        "center": {"latitude": -20, "longitude": 60},
        "sources_coupling_time_association": "common",
        **({"width_km": {"x": 2, "y": 2}} if crop else {}),
    }, products={"model_grid": True, "track": True})
    result = execute_simulation(conf)
    path = next(p["path"] for p in result.products if p["source"] == "weather")
    with xr.open_dataset(path) as out:
        assert out.sizes["time"] == (2 if crop else 3)
        assert out.scalar.shape[-2:] == ((3, 3) if crop else (7, 7))
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    assert provenance["time_alignment"]["sources"]["weather"]["skipped_times"] == [
        "2000-01-01T00:00:00.000000000"]


@pytest.mark.parametrize("policy", ["exact", "preceding_hour"])
@pytest.mark.parametrize("count", [12, 24])
def test_regional_inventory_groups_records_once_without_changing_clocks(
        tmp_path, monkeypatch, policy, count):
    from types import SimpleNamespace

    from frameit.core import coupled, time_association

    conf = configuration(tmp_path, {
        "weather": {"model": "arome", "files": "./weather.nc"},
        "water": {"model": "nemo", "files": "./water.nc"}},
        region={"center": {"latitude": -20, "longitude": 60},
                "sources_coupling_time_association": policy})
    reads = {"visits": 0, "times": 0}

    class Record(dict):
        def __getitem__(self, key):
            reads["times"] += key == "time"
            return super().__getitem__(key)

    class Records(list):
        def __iter__(self):
            for record in super().__iter__():
                reads["visits"] += 1
                yield record

    plans, children = {}, {}
    ends = np.datetime64("2000-01-01", "ns") + np.arange(1, count + 1) * np.timedelta64(1, "h")
    for name, model, physical in (("weather", "AROME", "atmosphere"), ("water", "NEMO", "ocean")):
        paths = [f"{name}-{i}.nc" for i in range(count // 2)]
        times = ends if name == "weather" else ends - np.timedelta64(30, "m")
        records = Records(Record(
            name="scalar", field_id="scalar", time=stamp, cycle=None, calendar="standard",
            time_bounds=None if name == "weather" else (end - np.timedelta64(1, "h"), end),
            temporal_metadata={
                "cell_methods": "time: point" if name == "weather" else "time: mean"},
            locator={"path": paths[i // 2]})
            for i, (stamp, end) in enumerate(zip(times, ends, strict=True)))
        plans[name] = {
            "format": "netcdf", "physical_type": physical, "records": records,
            "selected_times": list(times[::-1]), "fields": {"scalar": {"time_varying": True}},
            "file_inventory": [{"path": path} for path in paths + [
                f"{name}-unselected.nc", f"{name}-empty.nc"]]}
        children[name] = SimpleNamespace(atm_model=model, source_requests={name: {"exports": {}}})
    owner, method = ((coupled, "align_source_times") if policy == "exact"
                     else (time_association, "align_preceding_hour"))
    original, observed = getattr(owner, method), {}

    def inspect(inventories, *args, **kwargs):
        observed.update(inventories)
        return original(inventories, *args, **kwargs)

    monkeypatch.setattr(owner, method, inspect)
    coupled._prepare_v3_regions(conf, children, plans)
    for name, source in plans.items():
        first_times = list(reversed(source["selected_times"][-2:]))
        if policy == "exact":
            assert [entry["path"] for entry in observed[name]] == [
                entry["path"] for entry in source["file_inventory"]]
            assert observed[name][0]["times"] == source["selected_times"][-2:]
            assert observed[name][-2]["times"] == observed[name][-1]["times"] == []
        else:
            assert len(observed[name]) == count // 2
            assert observed[name][0]["times"] == [str(time) for time in first_times]
        assert len(source["region"]["associations"]) == count
    print(f"I4 policy={policy} records={count * 2} "
          f"visits={reads['visits']} time_reads={reads['times']}")
    assert reads["visits"] <= 5 * count * 2
    assert reads["times"] <= 6 * count * 2


def preceding_sources(tmp_path):
    sources = {
        "weather": scalar_scene(tmp_path / "weather.nc", hours=(1, 2), model="mesonh", angle=0),
        "water": scalar_scene(tmp_path / "water.nc", hours=(0, 1), model="nemo", angle=0),
    }
    sources["weather"]["model"] = "arome"
    with xr.open_dataset(tmp_path / "weather.nc") as ds:
        ds = ds.load().rename(nj="y", ni="x")
    ds.scalar.attrs["cell_methods"] = "time: point"
    ds.to_netcdf(tmp_path / "weather.nc", mode="w")
    with xr.open_dataset(tmp_path / "water.nc") as ds:
        ds = ds.load()
    ds = ds.assign_coords(time_counter=ds.time_counter + np.timedelta64(30, "m"))
    start = ds.time_counter.values - np.timedelta64(30, "m")
    ds["time_bounds"] = (("time_counter", "bounds"), np.stack(
        [start, start + np.timedelta64(1, "h")], axis=1))
    ds.time_counter.attrs["bounds"] = "time_bounds"
    ds.scalar.attrs["cell_methods"] = "time: mean"
    ds.to_netcdf(tmp_path / "water.nc", mode="w")
    return sources


def test_preceding_hour_keeps_native_sample_time_and_bounds(tmp_path):
    sources = preceding_sources(tmp_path)
    conf = configuration(tmp_path, sources, region={
        "center": {"latitude": -20, "longitude": 60}, "width_km": {"x": 2, "y": 2},
        "sources_coupling_time_association": "preceding_hour"})
    result = execute_simulation(conf)
    path = next(p["path"] for p in result.products if p["source"] == "water")
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source:
    np.testing.assert_array_equal(out.time, source.time_counter)
    np.testing.assert_array_equal(out.time_bounds, source.time_bounds)
    np.testing.assert_array_equal(out.center_time, source.time_bounds[:, 1])
    np.testing.assert_array_equal(out.scalar, source.scalar.values[:, 2:5, 2:5])
    assert out.scalar.attrs == source.scalar.attrs
    assert out.time.attrs['bounds'] == 'time_bounds'
assert 'frameit' not in sys.modules
""", path, str(tmp_path / "water.nc")], check=True, capture_output=True, text=True)


def test_preceding_hour_rejects_grib_atmosphere_before_binding_or_payloads(tmp_path, monkeypatch):
    import eccodes as ec

    from frameit.core.coupled import bind_sources
    from frameit.testing.numerical.test_v3_grib_reads import write_messages

    sources = preceding_sources(tmp_path)
    path = tmp_path / "atmosphere.grib"
    write_messages(path, [
        {"hour": hour, "param": 151, "group": "meanSea", "level": 0} for hour in (1, 2)])
    sources["weather"] = {"model": "arome", "files": str(path), "variables": {"2d": ["prmsl"]}}
    with xr.open_dataset(tmp_path / "water.nc") as original:
        ocean = original.load()
    delta = np.datetime64("2026-01-01", "ns") - np.datetime64("2000-01-01", "ns")
    ocean = ocean.assign_coords(time_counter=ocean.time_counter + delta)
    ocean["time_bounds"] = ocean.time_bounds + delta
    ocean.time_counter.attrs["bounds"] = "time_bounds"
    ocean.to_netcdf(tmp_path / "water.nc", mode="w")
    conf = configuration(tmp_path, sources, region={
        "center": {"latitude": -20, "longitude": 60},
        "sources_coupling_time_association": "preceding_hour"})
    reads = []
    original = ec.codes_get_values

    def payload(handle, *args, **kwargs):
        reads.append(ec.codes_get(handle, "paramId"))
        return original(handle, *args, **kwargs)

    monkeypatch.setattr(ec, "codes_get_values", payload)
    with pytest.raises(ValueError, match="preceding_hour.*NetCDF"):
        bind_sources(conf)
    assert not reads and not conf.output_dir.exists()


@pytest.mark.parametrize("problem,match", [
    ("duration", "hourly"), ("mean", "time mean"), ("cycle", "cycle"),
    ("unselected", "No preceding_hour"), ("excluded", "No preceding_hour"),
])
def test_preceding_hour_uses_only_selected_evidenced_intervals(tmp_path, problem, match):
    sources = preceding_sources(tmp_path)
    with xr.open_dataset(tmp_path / "water.nc") as ds:
        ds = ds.load()
    if problem == "duration":
        ds.time_bounds.values[:, 0] -= np.timedelta64(1, "h")
    elif problem == "mean":
        ds.scalar.attrs["cell_methods"] = "time: point"
    elif problem == "cycle":
        ds = ds.assign_coords(forecast_reference_time=np.datetime64("1999-12-31"))
        with xr.open_dataset(tmp_path / "weather.nc") as atmosphere:
            atmosphere = atmosphere.load().assign_coords(
                forecast_reference_time=np.datetime64("1999-12-30"))
        atmosphere.to_netcdf(tmp_path / "weather.nc", mode="w")
    elif problem == "unselected":
        sources["water"]["time"] = {"values": ["2000-01-01T00:30:00"]}
        sources["weather"]["time"] = {"values": ["2000-01-01T02:00:00"]}
    else:
        sources["water"]["files"] = [str(tmp_path / "water.nc"), str(tmp_path / "extra.nc")]
        ds.isel(time_counter=[0]).to_netcdf(tmp_path / "extra.nc")
        sources["water"]["exclude"] = [str(tmp_path / "water.nc")]
        sources["weather"]["time"] = {"values": ["2000-01-01T02:00:00"]}
    ds.to_netcdf(tmp_path / "water.nc", mode="w")
    conf = configuration(tmp_path, sources, region={
        "center": {"latitude": -20, "longitude": 60}, "width_km": {"x": 2, "y": 2},
        "sources_coupling_time_association": "preceding_hour"})
    with pytest.raises(ValueError, match=match):
        execute_simulation(conf)
    assert not conf.output_dir.exists()


def test_native_centroid_binds_real_support_separately_from_export_levels(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.testing.numerical.test_pressure_centroid_mnh import native_vortex

    ds, _ = native_vortex(n=81)
    ds = xr.concat([ds.isel(time=[0]), ds.isel(time=[0]).assign_coords(
        time=[np.datetime64("2024-01-01T00:30", "ns")]), ds.isel(time=[1])], dim="time")
    ds.to_netcdf(tmp_path / "native.nc")
    conf = configuration(tmp_path, {"weather": {
        "model": "mesonh", "files": "./native.nc",
        "time": {"stride": 2},
        "variables": {"3d": ["PABST"], "levels": {"indices": [1]}},
        "wind_pairs": [{"u": "UT_ZM", "v": "VT_ZM", "basis": "earth"},
                       {"u": "UM10", "v": "VM10", "basis": "earth"}]}},
        region={"tracker": {"method": "pressure_centroid"}},
        products={"model_grid": True, "track": True})
    reads = []
    original = H5NetCDFArrayWrapper.__getitem__

    def selected(array, key):
        if array.variable_name in {"PABST", "UT_ZM", "VT_ZM", "UM10", "VM10", "MSLP"}:
            indices = np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist()
            assert set(indices) <= {0, 2}
            reads.extend((array.variable_name, index) for index in indices)
        return original(array, key)

    with monkeypatch.context() as guard:
        guard.setattr(H5NetCDFArrayWrapper, "__getitem__", selected)
        result = execute_simulation(conf)
    assert set(reads) == {(name, index) for name in (
        "PABST", "UT_ZM", "VT_ZM", "UM10", "VM10", "MSLP") for index in (0, 2)}
    binding = conf.source_requests["weather"]["binding"]
    exported = binding["products"]["model_grid"]["PABST"]["records"][0]
    internal = binding["dependencies"]["PABST"]["records"][0]
    assert exported["source_positions"] == [1]
    assert internal["source_positions"] == [0, 1]
    with xr.open_dataset(next(p["path"] for p in result.products if p["role"] == "track")) as out:
        np.testing.assert_allclose(out.longitude, 60, atol=.01)
        np.testing.assert_allclose(out.latitude, -20, atol=.01)
    product = next(p["path"] for p in result.products if p["role"] == "model_grid")
    with xr.open_dataset(product) as out:
        np.testing.assert_array_equal(out.PABST, ds.PABST.isel(time=[0, 2], level=[1]))
        assert set(out.data_vars) == {"PABST"}


@pytest.mark.parametrize("policy", ["error", "keep_prefix"])
def test_multifield_real_track_loss_status_and_native_exports(tmp_path, policy):
    from frameit.testing.numerical.test_multifield_vortex import vortex

    ds, _ = vortex(n=81)
    ds["MSLP"][1] = 101000.
    ds.to_netcdf(tmp_path / "native.nc")
    conf = configuration(tmp_path, {"weather": {
        "model": "mesonh", "files": "./native.nc",
        "variables": {"2d": ["MSLP"]},
        "wind_pairs": [{"u": "UT_ZM", "v": "VT_ZM", "basis": "earth"},
                       {"u": "UM10", "v": "VM10", "basis": "earth"}]}},
        region={"tracker": {"method": "multifield_vortex", "on_incomplete": policy,
            "mnh_gravity_m_s2": 9.80665,
            "seed": {"latitude": -20, "longitude": 60, "motion_u_m_s": 0, "motion_v_m_s": 0}}},
        products={"model_grid": True, "track": True})
    if policy == "error":
        with pytest.raises(ValueError, match="required_fix_missing"):
            execute_simulation(conf)
        status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
        assert status["state"] == "failed" and status["products"] == []
    else:
        result = execute_simulation(conf)
        assert not result.tracking_complete
        assert result.tracking_termination_reason == "required_fix_missing"
        status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
        assert status["state"] == "incomplete"
        track = next(p["path"] for p in result.products if p["role"] == "track")
        with xr.open_dataset(track) as out:
            assert out.sizes["time"] == 1 and out.sizes["attempt_time"] == 2
        product = next(p["path"] for p in result.products if p["role"] == "model_grid")
        with xr.open_dataset(product) as out:
            np.testing.assert_array_equal(out.MSLP, ds.MSLP)
            assert out.sizes["time"] == 2


@pytest.mark.parametrize("method", ["pressure_centroid", "multifield_vortex"])
def test_arome_existing_methods_bind_selected_metadata_and_export_track_only(tmp_path, method):
    from frameit.testing.numerical.test_multifield_vortex import vortex

    ds, _ = vortex(model="arome", n=81)
    ds.to_netcdf(tmp_path / "atmosphere.nc")
    tracker = {"method": method}
    if method == "multifield_vortex":
        tracker["seed"] = {"latitude": -20, "longitude": 60, "motion_u_m_s": 0, "motion_v_m_s": 0}
    conf = configuration(tmp_path, {"renamed": {
        "model": "arome", "files": "./atmosphere.nc",
        "wind_pairs": [{"u": "u", "v": "v", "basis": "earth"},
                       {"u": "u10", "v": "v10", "basis": "earth"}]}},
        region={"tracker": tracker}, products={"track": True})
    result = execute_simulation(conf)
    assert len(result.products) == 1 and result.products[0]["role"] == "track"
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_allclose(out.latitude, -20, atol=.05)
        np.testing.assert_allclose(out.longitude, 60, atol=.05)
    support = conf.simulation_parameter["request_plan"]["sources"]["renamed"]["tracker_support"]
    assert set(support["inputs"]) == {"u", "v", "z", "u10", "v10", "prmsl"}


def test_arome_multifield_grib_uses_selected_stencils_and_keeps_native_product(
        tmp_path, monkeypatch):
    import eccodes as ec

    from frameit.testing.numerical.test_multifield_vortex import vortex, write_grib

    original, _ = vortex(model="arome", n=81)
    ds = xr.concat([original.isel(time=[0]), original.isel(time=[0]),
                    original.isel(time=[1])], dim="time").assign_coords(time=np.array(
        ["2024-01-01T00", "2024-01-01T06", "2024-01-01T12"], dtype="datetime64[ns]"))
    ds.to_netcdf(tmp_path / "reference.nc")
    write_grib(tmp_path / "atmosphere.grib", ds)
    conf = configuration(tmp_path, {"weather": {
        "model": "arome", "files": "./atmosphere.grib", "time": {"stride": 2},
        "variables": {"3d": ["u"], "levels": {"values": [500], "units": "hPa"}}}},
        region={"tracker": {"method": "multifield_vortex", "seed": {
            "latitude": -20, "longitude": 60, "motion_u_m_s": 0, "motion_v_m_s": 0}}},
        products={"model_grid": True, "track": True})
    reads = []
    values = ec.codes_get_values

    def selected(handle, *args, **kwargs):
        reads.append((ec.codes_get(handle, "paramId"), ec.codes_get(handle, "endStep"),
                      ec.codes_get(handle, "level")))
        return values(handle, *args, **kwargs)

    monkeypatch.setattr(ec, "codes_get_values", selected)
    result = execute_simulation(conf)
    assert set(reads) == {
        (param, hour, level) for hour in (0, 12) for param in (131, 132, 129)
        for level in ((850, 700) if param == 129 else (850, 700, 500))} | {
        (param, hour, level) for hour in (0, 12) for param, level in (
            (151, 0), (165, 10), (166, 10))}
    product = next(p["path"] for p in result.products if p["role"] == "model_grid")
    track = next(p["path"] for p in result.products if p["role"] == "track")
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source, \
     xr.open_dataset(sys.argv[3]) as track:
    assert set(out.data_vars) == {'u'}
    np.testing.assert_array_equal(out.pressure, [500.])
    np.testing.assert_array_equal(out.pressure_source_native_index, [2])
    np.testing.assert_array_equal(out.time, source.time.isel(time=[0, 2]))
    # 24-bit GRIB packing of this <70-m/s range has error below 1e-4 m/s.
    np.testing.assert_allclose(out.u, source.u.isel(time=[0, 2], isobaric=[2]),
                               rtol=0, atol=1e-4)
    np.testing.assert_allclose(track.latitude, -20, atol=.05)
    np.testing.assert_allclose(track.longitude, 60, atol=.05)
assert 'frameit' not in sys.modules
""", product, str(tmp_path / "reference.nc"), track],
        check=True, capture_output=True, text=True)


@pytest.mark.parametrize("location", [
    "track_destination", "store_alias_chain", "store_directory_chain",
])
def test_trajectory_and_required_aliases_are_read_only_before_run_ownership(tmp_path, location):
    sources = {"weather": scalar_scene(tmp_path / "weather.nc")}
    output = {}
    if location == "track_destination":
        track = tmp_path / "out/products/regional.track.nc"
        track.parent.mkdir(parents=True)
    else:
        output["format"] = "zarr"
        store = tmp_path / "out/products/regional.weather.model_grid.zarr"
        store.parent.mkdir(parents=True)
        xr.Dataset({"prior": ("x", [1.])}).to_zarr(store, zarr_format=3, consolidated=False)
        original = tmp_path / "trajectory.nc"
        trajectory(original)
        directory = location == "store_directory_chain"
        intermediate = store / "trajectory-link"
        intermediate.symlink_to(original.parent if directory else original,
                                target_is_directory=directory)
        declaration = tmp_path / "selected-trajectory"
        declaration.symlink_to(intermediate.relative_to(tmp_path), target_is_directory=directory)
        track = declaration / original.name if directory else declaration
    if location == "track_destination":
        trajectory(track)
    original_bytes = track.read_bytes()
    conf = configuration(tmp_path, sources, region={"track": {"file": str(track)}},
                         products={"model_grid": True, "track": True},
                         output={**output, "overwrite": True})
    with pytest.raises(ValueError, match="input"):
        execute_simulation(conf)
    assert track.read_bytes() == original_bytes
    assert not (conf.output_dir / "run-status.yaml").exists()


@pytest.mark.parametrize("directory", [False, True])
def test_prescribed_alias_can_publish_independent_outputs(tmp_path, directory):
    source = tmp_path / "weather.nc"
    sources = {"weather": scalar_scene(source)}
    original = tmp_path / "trajectory.nc"
    trajectory(original)
    intermediate = tmp_path / "trajectory-view"
    intermediate.symlink_to(original.parent if directory else original,
                            target_is_directory=directory)
    declaration = tmp_path / "selected-trajectory"
    declaration.symlink_to(intermediate.name, target_is_directory=directory)
    track = declaration / original.name if directory else declaration
    before = original.read_bytes()
    conf = configuration(tmp_path, sources, region={"track": {"file": str(track)}},
                         products={"model_grid": True, "track": True})
    result = execute_simulation(conf)
    field_path = next(p["path"] for p in result.products if p["role"] == "model_grid")
    track_path = next(p["path"] for p in result.products if p["role"] == "track")
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as fields, xr.open_dataset(sys.argv[2]) as track, \
     xr.open_dataset(sys.argv[3]) as source:
    np.testing.assert_array_equal(fields.scalar, source.scalar)
    np.testing.assert_array_equal(fields.time, source.time)
    np.testing.assert_array_equal(track.latitude, [-20.] * 3)
    np.testing.assert_array_equal(track.longitude, [60.] * 3)
    assert track.latitude.attrs['units'] == 'degrees_north'
    assert track.longitude.attrs['units'] == 'degrees_east'
    assert track.time.encoding['calendar'] and 'since' in track.time.encoding['units']
assert 'frameit' not in sys.modules
""", field_path, track_path, str(source)], check=True, capture_output=True, text=True)
    assert original.read_bytes() == track.read_bytes() == before
    assert declaration.is_symlink() and intermediate.is_symlink()


def test_preflight_explains_tracker_dependencies_without_scientific_reads(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.core.coupled import prepare_sources

    source = pressure_wind_scene(tmp_path / "weather.nc")
    conf = configuration(tmp_path, {"unusual_name": source},
                         region={"tracker": {"method": "pressure_wind"}})
    original = H5NetCDFArrayWrapper.__getitem__

    def metadata_only(array, key):
        if array.variable_name in {"scalar", "MSLP", "UM10", "VM10"}:
            pytest.fail(f"Preflight read scientific payload {array.variable_name}")
        return original(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", metadata_only)
    report, _, plans = prepare_sources(conf)
    assert set(plans["unusual_name"]["tracker_support"]["inputs"]) == {"MSLP", "UM10", "VM10"}
    assert report["sources"]["unusual_name"]["region"]["centre_provider"] == "tracker"
    assert plans["unusual_name"]["region"]["grids"]


@pytest.mark.parametrize("pending", ["transforms", "derived", "polar", "interpretation"])
def test_tracker_binding_does_not_clear_unrelated_pending_operations(tmp_path, pending):
    from frameit.core.coupled import bind_sources

    source = pressure_wind_scene(tmp_path / "weather.nc")
    products = None
    if pending == "transforms":
        source["transforms"] = [{"fields": ["scalar"], "units": "K"}]
    elif pending == "derived":
        source["derived"] = {"speed": {
            "method": "wind_speed", "inputs": {"u": "UM10", "v": "VM10"}}}
        products = {"model_grid": {"fields": {"weather": ["speed"]}}}
    elif pending == "polar":
        source["field_metadata"] = {"scalar": {"kind": "continuous"}}
        products = {"polar": {"radius_km": 1}}
    else:
        source["interpretation"] = "mesonh_surfex_sea"
    conf = configuration(tmp_path, {"weather": source},
                         region={"tracker": {"method": "pressure_wind"},
                                 "width_km": {"x": 2, "y": 2}}, products=products)
    if pending == "derived":
        before = (tmp_path / "weather.nc").read_bytes()
        _, children, plans = bind_sources(conf)
        binding = children["weather"].source_requests["weather"]["binding"]
        assert binding["status"] == "bound"
        assert set(binding["products"]["model_grid"]) == {"speed"}
        assert set(binding["dependencies"]) == {"MSLP", "UM10", "VM10"}
        assert plans["weather"]["tracker_support"]["inputs"] == {
            "MSLP": {}, "UM10": {}, "VM10": {}}
        result = execute_simulation(conf)
        subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    assert set(out.data_vars) == {'speed'}
    assert out.speed.shape == (2, 3, 3)
    expected = np.full((2, 3, 3), np.sqrt(100 + (25/9)**2))
    expected[:, 1, 1] = 0
    np.testing.assert_allclose(out.speed, expected, atol=1e-12)
    assert out.speed.attrs['units'] == 'm s-1'
    assert out.speed.attrs['frameit_method'] == 'wind_speed'
    assert np.diff(out.time.values).tolist() == [7200000000000]
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"]], check=True, capture_output=True, text=True)
        assert (tmp_path / "weather.nc").read_bytes() == before
        return
    if pending == "interpretation":
        _, children, plans = bind_sources(conf)
        binding = children["weather"].source_requests["weather"]["binding"]
        assert binding["status"] == "bound"
        assert conf.source_requests["weather"]["binding"]["status"] == "bound"
        assert plans["weather"]["requests"]["binding"]["status"] == "bound"
        assert binding["interpretation"] == {
            "method": "mesonh_surfex_sea", "fields": [], "pending_value_checks": []}
        assert conf.source_requests["weather"]["exports"] == {"model_grid": ["scalar"]}
        assert set(binding["products"]["model_grid"]) == {"scalar"}
        assert plans["weather"]["tracker_support"]["inputs"] == {
            "MSLP": {}, "UM10": {}, "VM10": {}}
        assert set(binding["dependencies"]) == {"MSLP", "UM10", "VM10"}
        assert {record["name"] for record in binding["records"]} == {
            "scalar", "MSLP", "UM10", "VM10"}
        assert not conf.output_dir.exists()
        return
    if pending == "polar":
        _, children, plans = bind_sources(conf)
        binding = children["weather"].source_requests["weather"]["binding"]
        assert binding["status"] == "bound" and binding["polar_plan"]["target_points"] == 28
        assert set(binding["dependencies"]) == {"scalar", "MSLP", "UM10", "VM10"}
        assert plans["weather"]["tracker_support"]["inputs"] == {
            "MSLP": {}, "UM10": {}, "VM10": {}}
        result = execute_simulation(conf)
        subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    np.testing.assert_allclose(out.scalar.isel(radius=0,azimuth=0), [0.,122.], atol=1e-9)
    np.testing.assert_array_equal(out.scalar_interpolation_status.isel(radius=0), 0)
    np.testing.assert_array_equal(out.time, out.center_time)
    assert not {'MSLP','UM10','VM10','wind_speed','vrad','vtan'} & set(out.data_vars)
assert 'frameit' not in sys.modules
""", result.products[0]["path"]], check=True, capture_output=True, text=True)
        return
    with pytest.raises(ValueError, match="pending|bind|support|method"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def test_fixed_region_retains_non_gregorian_source_calendar(tmp_path):
    import cftime

    declaration = scalar_scene(tmp_path / "weather.nc", hours=(0, 1))
    with xr.open_dataset(tmp_path / "weather.nc") as ds:
        ds = ds.load().assign_coords(time=[
            cftime.Datetime360Day(2000, 2, 29), cftime.Datetime360Day(2000, 2, 30)])
    ds.to_netcdf(tmp_path / "weather.nc", mode="w")
    conf = configuration(tmp_path, {"weather": declaration}, region={
        "center": {"latitude": -20, "longitude": 60}, "width_km": {"x": 2, "y": 2}},
        products={"model_grid": True, "track": True})
    result = execute_simulation(conf)
    for product in result.products:
        with xr.open_dataset(product["path"]) as out:
            assert out.time.encoding["calendar"] == "360_day"
            np.testing.assert_array_equal(out.time, ds.time)


def test_grib_tracker_decodes_only_selected_messages(tmp_path, monkeypatch):
    import eccodes as ec

    from frameit.testing.numerical.test_multifield_vortex import vortex, write_grib

    ds, _ = vortex(model="arome", n=41)
    write_grib(tmp_path / "atmosphere.grib", ds)
    conf = configuration(tmp_path, {"weather": {
        "model": "arome", "files": "./atmosphere.grib",
        "time": {"values": ["2024-01-01T06:00:00"]}}},
        region={"tracker": {"method": "pressure_wind"}}, products={"track": True})
    original = ec.codes_get_values
    reads = []

    def selected(handle, *args, **kwargs):
        reads.append((ec.codes_get(handle, "paramId"), ec.codes_get(handle, "endStep")))
        return original(handle, *args, **kwargs)

    monkeypatch.setattr(ec, "codes_get_values", selected)
    result = execute_simulation(conf)
    assert set(reads) == {(151, 6), (165, 6), (166, 6)}
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_array_equal(out.time, ds.time.isel(time=[1]))
        np.testing.assert_allclose(out.longitude, [60.], atol=.01)


def test_grib_fixed_crop_keeps_native_samples_without_projected_axis_labels(tmp_path):
    import eccodes as ec

    from frameit.testing.numerical.test_multifield_vortex import vortex, write_grib

    ds, _ = vortex(model="arome", n=41)
    write_grib(tmp_path / "atmosphere.grib", ds)
    conf = configuration(tmp_path, {"weather": {
        "model": "arome", "files": "./atmosphere.grib", "variables": {"2d": ["prmsl"]}}},
        region={"center": {"latitude": -20, "longitude": 60},
                "width_km": {"x": 100, "y": 100}})
    native = []
    with (tmp_path / "atmosphere.grib").open("rb") as stream:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                if ec.codes_get(handle, "paramId") == 151:
                    native.append(ec.codes_get_values(handle).reshape(41, 41)[19:22, 19:22])
            finally:
                ec.codes_release(handle)
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_array_equal(out.prmsl, native)
        assert set(out.data_vars) == {"prmsl"}


@pytest.mark.parametrize("problem", ["surface_axis", "partial_wind_basis"])
def test_tracker_rejects_unresolved_metadata_before_ownership(tmp_path, problem):
    declaration = pressure_wind_scene(tmp_path / "weather.nc")
    with xr.open_dataset(tmp_path / "weather.nc") as ds:
        ds = ds.load()
    if problem == "surface_axis":
        ds["MSLP"] = ds.MSLP.expand_dims(level=[0, 1])
    else:
        ds.VM10.attrs.pop("standard_name")
    ds.to_netcdf(tmp_path / "weather.nc", mode="w")
    conf = configuration(tmp_path, {"weather": declaration},
                         region={"tracker": {"method": "pressure_wind"}})
    with pytest.raises(ValueError, match="horizontal|2d|basis"):
        execute_simulation(conf)
    assert not conf.output_dir.exists()
