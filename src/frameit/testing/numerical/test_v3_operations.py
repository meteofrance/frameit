"""Explicit C3/C4 operations, independently prescribed samples and read support."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from frameit.core.configuration import to_runtime
from frameit.core.coupled import bind_sources
from frameit.core.execution import execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources
from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord


def scene():
    times = np.array(["2024-01-01T00", "2024-01-01T01", "2024-01-01T02"],
                     dtype="datetime64[ns]")
    return xr.Dataset({
        "U": (("time", "level", "nj", "ni"), np.full((3, 3, 3, 3), 10.8),
              {"units": "km/h", "standard_name": "eastward_wind"}),
        "V": (("time", "level", "nj", "ni"), np.full((3, 3, 3, 3), 14.4),
              {"units": "km/h", "standard_name": "northward_wind"}),
    }, coords={
        "time": times,
        "level": ("level", [10., 20., 30.], {"units": "m", "axis": "Z"}),
        "ni": ("ni", [0., 1000., 2000.], {"units": "m"}),
        "nj": ("nj", [0., 1000., 2000.], {"units": "m"}),
        "latitude": (("nj", "ni"), np.broadcast_to(
            np.array([-20., -19.99, -19.98])[:, None], (3, 3)), {"units": "degrees_north"}),
        "longitude": (("nj", "ni"), np.broadcast_to(
            np.array([60., 60.01, 60.02]), (3, 3)), {"units": "degrees_east"}),
    })


def configuration(tmp_path, source, **document):
    return SimulationConfig(**to_runtime({
        "schema_version": 3, "run": {"name": "operations"},
        "sources": {"atmosphere": {
            "model": "mesonh", "files": str(tmp_path / "input.nc"), **source}},
        "output": {"directory": str(tmp_path / "output")},
        "resources": {"synchronous_export": True, "scheduler": "synchronous"},
        **document,
    }))


def ordinary_reader(path, checks):
    subprocess.run([sys.executable, "-c", """
import json, sys
import numpy as np
import xarray as xr
assert not any(n == "frameit" or n.startswith("frameit.") for n in sys.modules)
with xr.open_dataset(sys.argv[1]) as out:
    checks = json.loads(sys.argv[2])
    assert set(out.data_vars) == set(checks)
    assert out.attrs["frameit_version"] and out.attrs["product_type"] == "model_grid"
    for name, check in checks.items():
        values = out[name].values
        if "values" in check:
            if check.get("exact"):
                np.testing.assert_array_equal(values, check["values"])
            else:
                np.testing.assert_allclose(values, check["values"], rtol=1e-14, atol=1e-12)
        for key, value in check.get("attrs", {}).items():
            assert out[name].attrs[key] == value, (name, key, out[name].attrs)
        for coordinate, values in check.get("coordinates", {}).items():
            np.testing.assert_array_equal(out[coordinate].values, values)
assert not any(n == "frameit" or n.startswith("frameit.") for n in sys.modules)
""", str(path), json.dumps(checks)], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("names", [["U"], ["U", "V"]])
def test_native_components_do_not_request_wind_work(tmp_path, names):
    ds = scene()
    if names == ["U"]:
        ds = ds.drop_vars("V")
        ds.U.attrs = {"units": "stored_velocity_symbol", "custom": "unchanged"}
    ds.U.values[1, 1, 0, 0] = np.nan
    ds.to_netcdf(tmp_path / "input.nc")
    before = hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest()
    conf = configuration(tmp_path, {
        "variables": {"3d": names, "levels": {"indices": [1]}},
        "time": {"values": ["2024-01-01T01:00:00"]},
    })
    result = execute_simulation(conf)
    ordinary_reader(result.products[0]["path"], {
        name: {"values": ds[name].isel(time=[1], level=[1]).values.tolist(),
               "exact": True, "attrs": ds[name].attrs} for name in names})
    assert hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest() == before


def test_numerical_loader_native_singleton_needs_no_companion_or_basis(tmp_path):
    ds = scene().drop_vars("V")
    ds.U.attrs = {"units": "knots", "custom": "native"}
    path = tmp_path / "input.nc"
    ds.to_netcdf(path)
    conf = configuration(tmp_path, {"variables": {"3d": ["U"]}})
    conf.velocity_aliases = {"u_velocity": "U", "v_velocity": "V", "w_velocity": "W"}
    with DatasetResources() as resources:
        user, _ = concat_nc2ds_by_vert_coord(
            [path], {"level": {"variables": ["U"], "all_levels": True}}, {},
            wind_conf=conf, resources=resources)
        xr.testing.assert_identical(user["level"].U.compute(), ds.U)


def test_explicit_units_transform_changes_only_requested_export(tmp_path):
    ds = scene()
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["U", "V"], "levels": {"indices": [2, 0]}},
        "transforms": [{"fields": ["U"], "units": "m s-1"}],
    })
    result = execute_simulation(conf)
    ordinary_reader(result.products[0]["path"], {
        "U": {"values": np.full((3, 2, 3, 3), 3.).tolist(),
              "attrs": {"units": "m s-1", "source_units": "km/h"}},
        "V": {"values": np.full((3, 2, 3, 3), 14.4).tolist(), "attrs": ds.V.attrs},
    })
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_array_equal(out.level, [30., 10.])


def test_derived_inputs_stay_internal_and_selected_reads_are_closed(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    ds = scene()
    ds.U.values[1, 2, 0, 0] = 0
    ds.V.values[1, 2, 0, 0] = 0
    ds.V.values[1, 2, 0, 1] = np.nan
    path = tmp_path / "input.nc"
    ds.to_netcdf(path)
    original = path.read_bytes()
    conf = configuration(tmp_path, {
        "variables": {"levels": {"indices": [2]}},
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "U", "v": "V"}}},
        "time": {"values": ["2024-01-01T01:00:00"]},
        "reader": {"chunks": {"time": 3}},
    })
    reads = []
    original_get = H5NetCDFArrayWrapper.__getitem__

    def selected(array, key):
        if array.variable_name in {"U", "V"}:
            time = np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist()
            levels = np.atleast_1d(np.arange(array.shape[1])[key.tuple[1]]).tolist()
            reads.append((array.variable_name, time, levels))
            assert time == [1] and levels == [2]
        return original_get(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", selected)
    result = execute_simulation(conf)
    expected = np.full((1, 1, 3, 3), 5.)
    expected[0, 0, 0, :2] = [0., np.nan]
    ordinary_reader(result.products[0]["path"], {
        "speed": {"values": expected.tolist(),
                  "attrs": {"units": "m s-1", "frameit_method": "wind_speed"}}})
    assert {name for name, _, _ in reads} == {"U", "V"}
    assert path.read_bytes() == original
    binding = conf.source_requests["atmosphere"]["binding"]
    assert set(binding["dependencies"]) == {"U", "V"}
    assert set(binding["products"]["model_grid"]) == {"speed"}


def test_unused_derived_and_transform_definitions_read_nothing(tmp_path):
    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["U"]},
        "derived": {"unused": {"method": "wind_speed",
                               "inputs": {"u": "absent_u", "v": "absent_v"}}},
        "transforms": [{"fields": ["V"], "basis": "earth"}],
    }, products={"model_grid": {"fields": {"atmosphere": ["U"]}}})
    _, children, _ = bind_sources(conf)
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    assert not binding["dependencies"]
    assert {r["name"] for r in binding["records"]} == {"U"}
    assert not binding.get("operations")


@pytest.mark.parametrize("units", ["K", "MW", "mW"])
def test_incompatible_transform_units_fail_before_payload(tmp_path, units):
    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["U"]},
        "transforms": [{"fields": ["U"], "units": units}],
    })
    with pytest.raises(ValueError, match="units"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def test_derived_result_cannot_shadow_an_unexported_source_field(tmp_path):
    ds = scene()
    ds["speed"] = xr.zeros_like(ds.U)
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "U", "v": "V"}}},
    })
    with pytest.raises(ValueError, match="colli"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def staggered_scene():
    from frameit.testing.numerical.test_grid_representations import native_scene

    ds = xr.concat([native_scene(hour, units="km/h") for hour in range(3)],
                   dim="time", data_vars="all")
    ds["UT"][:] = 10.8
    ds["VT"][:] = 14.4
    return ds


@pytest.mark.parametrize("method", ["coordinate", "geolocation", "mesonh_projection"])
def test_explicit_mass_earth_rotation_uses_known_vectors(tmp_path, method):
    ds = staggered_scene()
    ds.VT.values[1, 2, 3, 3] = np.nan
    ds.to_netcdf(tmp_path / "input.nc")
    rotation = {"method": method}
    if method == "coordinate":
        rotation["coordinate"] = "angle"
    if method == "mesonh_projection":
        rotation.update(BETA=90., RPK=0., LON0=60.)
    conf = configuration(tmp_path, {
        "variables": {"3d": ["UT", "VT", "THT"], "levels": {"indices": [2, 0]}},
        "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid", "rotation": rotation}],
        "transforms": [{"fields": ["UT", "VT"], "sampling": "mass",
                        "basis": "earth", "units": "m s-1"}],
        "time": {"values": ["2024-01-01T01:00:00"]},
    })
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        assert set(out.data_vars) == {"UT", "VT", "THT"}
        assert out.UT.dims == out.VT.dims == ("time", "level", "nj", "ni")
        np.testing.assert_array_equal(out.level, [15., -5.])
        # Grid x points north and grid y west. The finite-neighbour geolocation
        # approximation has <0.001-radian curvature error on this 8-km grid.
        tolerance = .005 if method == "geolocation" else 1e-12
        np.testing.assert_allclose(out.UT[0, :, 4, 4], -4., atol=tolerance)
        np.testing.assert_allclose(out.VT[0, :, 4, 4], 3., atol=tolerance)
        assert np.isnan(out.UT[0, 0, 2:4, 3]).all()
        assert np.isnan(out.VT[0, 0, 2:4, 3]).all()
        assert out.UT.attrs["wind_rotation_method"] == method
        assert out.UT.attrs["frameit_sampling"] == "mass"
        np.testing.assert_array_equal(out.THT, 300.)
    ordinary_reader(result.products[0]["path"], {
        "UT": {"attrs": {"units": "m s-1", "wind_reference_frame": "earth"}},
        "VT": {"attrs": {"units": "m s-1", "wind_reference_frame": "earth"}},
        "THT": {"attrs": {"units": "K"}},
    })


def test_mass_only_single_component_does_not_normalize_units_or_require_pair(tmp_path):
    ds = staggered_scene().drop_vars("VT")
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["UT"], "levels": {"indices": [2]}},
        "transforms": [{"fields": ["UT"], "sampling": "mass"}],
    })
    result = execute_simulation(conf)
    ordinary_reader(result.products[0]["path"], {
        "UT": {"values": np.full((3, 1, 9, 9), 10.8).tolist(),
               "attrs": {"units": "km/h", "standard_name": "x_wind"}}})


def test_w_remap_binds_destination_indices_and_reads_only_required_support(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    ds = staggered_scene()
    ds.WT.attrs.update(units="Pa s-1", standard_name="lagrangian_tendency_of_air_pressure")
    ds.to_netcdf(tmp_path / "input.nc")
    original = (tmp_path / "input.nc").read_bytes()
    conf = configuration(tmp_path, {
        "variables": {"3d": ["WT", "Q"], "levels": {"indices": [2, 0]}},
        "transforms": [{"fields": ["WT"], "sampling": "mass"}],
        "time": {"values": ["2024-01-01T01:00:00"]},
    })
    reads = []
    original_get = H5NetCDFArrayWrapper.__getitem__

    def selected(array, key):
        if array.variable_name in {"WT", "Q", "UT", "VT"}:
            time = np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist()
            levels = np.atleast_1d(np.arange(array.shape[1])[key.tuple[1]]).tolist()
            reads.append((array.variable_name, time, levels))
            assert time == [1]
            assert array.variable_name in {"WT", "Q"}
            assert set(levels) == (set(range(4)) if array.variable_name == "WT" else {2, 0})
        return original_get(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", selected)
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_array_equal(out.level, [15., -5.])
        np.testing.assert_array_equal(out.level_w, [10., -10.])
        np.testing.assert_allclose(out.WT[0, :, 0, 0], [414., 198.])
        np.testing.assert_array_equal(out.Q[0, :, 0, 0], [1020., 980.])
        assert out.WT.attrs["units"] == "Pa s-1"
        assert out.WT.attrs["standard_name"] == "lagrangian_tendency_of_air_pressure"
        assert "source_units" not in out.WT.attrs
    ordinary_reader(result.products[0]["path"], {
        "WT": {"values": np.broadcast_to(
            np.array([414., 198.])[None, :, None, None], (1, 2, 9, 9)).tolist(),
            "attrs": {"units": "Pa s-1", "frameit_sampling": "mass"},
            "coordinates": {"level": [15., -5.], "level_source_native_index": [2, 0]}},
        "Q": {"attrs": {"units": "1"}, "coordinates": {"level_w": [10., -10.]}},
    })
    assert {name for name, _, _ in reads} == {"WT", "Q"}
    assert (tmp_path / "input.nc").read_bytes() == original


def test_derived_preparation_is_independent_of_export_units_and_basis(tmp_path):
    ds = staggered_scene()
    ds.to_netcdf(tmp_path / "input.nc")
    source = {
        "variables": {"3d": ["UT"], "levels": {"indices": [1]}},
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "UT", "v": "VT"}}},
        "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "transforms": [{"fields": ["UT"], "units": "knots"}],
    }
    conf = configuration(tmp_path, source)
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        assert set(out.data_vars) == {"UT", "speed"}
        assert "ni_u" in out.UT.dims and "ni" in out.speed.dims
        np.testing.assert_allclose(out.UT, 3 / .5144444444444445, atol=1e-12)
        np.testing.assert_allclose(out.speed, 5., atol=1e-12)
        assert out.UT.attrs["standard_name"] == "x_wind"
        assert out.UT.attrs["units"] == "knots"
        assert out.speed.attrs["units"] == "m s-1"


@pytest.mark.parametrize("problem", [
    "missing_mass", "missing_angle", "bad_units", "native_rotation",
])
def test_invalid_preparation_fails_without_reading_vectors(tmp_path, monkeypatch, problem):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    ds = staggered_scene()
    if problem == "missing_mass":
        ds = ds.drop_dims("ni")
        ds.level.attrs.pop("formula_terms")
    if problem == "missing_angle":
        ds = ds.drop_vars("angle")
    if problem == "bad_units":
        ds.VT.attrs["units"] = "Pa s-1"
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["UT"]},
        "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "transforms": [{"fields": ["UT"], "sampling": (
            "native" if problem == "native_rotation" else "mass"), "basis": "earth"}],
    })
    original_get = H5NetCDFArrayWrapper.__getitem__

    def forbidden(array, key):
        assert array.variable_name not in {"UT", "VT"}
        return original_get(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", forbidden)
    with pytest.raises(ValueError, match="mass|coordinate|units|collocat|stagger"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def test_polar_level_facts_do_not_clear_polar_execution_or_inherit_export_transform(tmp_path):
    from frameit.core.coupled import prepare_sources
    from frameit.core.preflight import bind_source

    staggered_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["WT"], "levels": {"indices": [2, 0]}},
        "transforms": [{"fields": ["WT"], "sampling": "mass"}],
    }, region={"center": {"latitude": -20., "longitude": 60.}},
        products={"model_grid": True, "polar": {"radius_km": 1.}})
    _, children, plans = prepare_sources(conf)
    binding = bind_source(children["atmosphere"], "atmosphere")
    assert binding["status"] == "pending_method_binding"
    assert children["atmosphere"].source_requests["atmosphere"]["binding"] is None
    model = binding["products"]["model_grid"]["WT"]["records"][0]
    polar = binding["products"]["polar"]["WT"]["records"][0]
    assert model["vertical"]["values"] == [15., -5.]
    assert polar["vertical"]["values"] == [10., -10.]
    assert model["selection_grid_id"] != polar["selection_grid_id"]
    assert polar["selection_grid_id"] == polar["grid_id"]
    assert plans["atmosphere"]["field_binding"]["status"] == "pending_method_binding"


def test_polar_derived_shared_levels_are_bound_but_magnitude_is_not_calculated(tmp_path):
    from frameit.core.coupled import prepare_sources
    from frameit.core.preflight import bind_source

    staggered_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"levels": {"indices": [2, 0]}},
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "UT", "v": "VT"}}},
        "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
    }, region={"center": {"latitude": -20., "longitude": 60.}},
        products={"polar": {"radius_km": 1.}})
    _, children, _ = prepare_sources(conf)
    binding = bind_source(children["atmosphere"], "atmosphere")
    assert binding["status"] == "pending_method_binding"
    descriptor = binding["products"]["polar"]["speed"]
    assert descriptor["method"] == "wind_speed"
    assert descriptor["execution"] == "pending_polar_sampling"
    assert descriptor["records"][0]["vertical"]["values"] == [15., -5.]
    assert descriptor["magnitude_order"] == "after_sampling_components"
    assert not binding["operations"]


def test_croco_explicit_transform_reuses_joint_masks_and_rho_rotation(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.testing.numerical.test_croco_vectors import vector_scene

    ds = vector_scene()
    ds.mask_rho.values[3, 2] = 0
    ds.u.values[1, 1, 4, 3] = 0.
    ds.v.values[1, 1, 4, 4] = 0.
    ds.to_netcdf(tmp_path / "input.nc")
    before = (tmp_path / "input.nc").read_bytes()
    conf = configuration(tmp_path, {
        "model": "croco", "variables": {"3d": ["u"], "levels": {"indices": [1]}},
        "wind_pairs": [{"u": "u", "v": "v", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "transforms": [{"fields": ["u"], "sampling": "mass",
                        "basis": "earth", "units": "m s-1"}],
        "time": {"values": [str(ds.time.values[1])]},
    })
    reads = []
    original_get = H5NetCDFArrayWrapper.__getitem__

    def selected(array, key):
        if array.variable_name in {"u", "v", "zeta"}:
            assert np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist() == [1]
            reads.append(array.variable_name)
        if array.variable_name in {"temp", "salt"}:
            pytest.fail("Unrequested scientific field was read")
        return original_get(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", selected)
    _, children, _ = bind_sources(conf)
    assert not reads
    assert children["atmosphere"].source_requests["atmosphere"]["binding"]["status"] == "bound"
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        assert set(out.data_vars) == {"u"}
        assert out.u.dims == ("time", "s_rho", "eta_rho", "xi_rho")
        assert not {"v", "wind_speed", "vrad", "vtan"} & set(out)
        np.testing.assert_allclose(out.u[0, 0, 2, 4], -4., atol=1e-12)
        assert np.isnan(out.u[0, 0, 3, 3])
        assert out.u.attrs["current_reference_frame"] == "earth"
        assert np.isnan(out.u[0, 0, 0]).all()
        assert all(n in out for n in out.s_rho.attrs["formula_terms"].split()[1::2])
    ordinary_reader(result.products[0]["path"], {
        "u": {"attrs": {"units": "m s-1", "current_reference_frame": "earth"}}})
    assert set(reads) == {"u", "v", "zeta"}
    assert (tmp_path / "input.nc").read_bytes() == before


def test_numerical_mass_extraction_does_not_add_speed(tmp_path):
    from frameit.processing.extraction import extract_data
    from frameit.testing.numerical.test_native_extraction import settings

    ds = scene().rename({"U": "UT", "V": "VT"})
    track = xr.Dataset({"cx": ("time", [1, 1, 1]), "cy": ("time", [1, 1, 1])},
                       coords={"time": ds.time})
    _, out = extract_data(settings(), {"level": ds}, ds, track)
    assert set(out["level"].data_vars) == {"UT", "VT"}


@pytest.mark.parametrize("names", [["U"], ["U", "V"]])
def test_numerical_runner_native_components_keep_samples_without_calculations(tmp_path, names):
    from frameit.core.runner import FrameitRunner

    ds = scene()
    if len(names) == 1:
        ds = ds.drop_vars("V")
    ds.U.attrs = {"units": "knots"}
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {"variables": {"3d": names}})
    conf.schema_version = 1  # Exercise the retained direct numerical route.
    conf.tracking_method = "fixed_box"
    conf.fix_subdomain_center = [60., -20.]
    conf.resolution = 1000
    conf.name_lat_dim, conf.name_lon_dim = "nj", "ni"
    conf.name_latitude, conf.name_longitude = "latitude", "longitude"
    conf.name_vertical_dim, conf.name_time_dim = "level", "time"
    conf.velocity_aliases = {"u_velocity": "U", "v_velocity": "V", "w_velocity": "W"}
    conf.requested_variables_user = {"level": {"variables": names, "all_levels": True}}
    conf.input_files = [str(tmp_path / "input.nc")]
    with FrameitRunner(conf) as runner:
        user, _, _ = runner.load_dataset()
        assert set(user["level"].data_vars) == set(names)
        for name in names:
            xr.testing.assert_identical(user["level"][name].compute(), ds[name])


def test_rotation_geometry_and_declared_origins_are_resolved_per_selected_snapshot(tmp_path):
    paths = []
    for hour, angle in ((0, 0.), (1, np.nan), (2, np.pi / 2)):
        ds = scene().isel(time=[hour])
        ds.U.attrs = {"standard_name": "x_wind"}
        ds.V.attrs = {"standard_name": "y_wind"}
        ds = ds.assign_coords(angle=xr.DataArray(angle, attrs={"units": "rad"}))
        path = tmp_path / f"sample-{hour}.nc"
        ds.to_netcdf(path)
        paths.append(path)
    before = [p.read_bytes() for p in paths]
    conf = configuration(tmp_path, {
        "files": list(map(str, paths)),
        "variables": {"3d": ["U"], "levels": {"indices": [1]}},
        "field_metadata": {"U": {"units": "km/h"}, "V": {"units": "km/h"}},
        "wind_pairs": [{"u": "U", "v": "V", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "transforms": [{"fields": ["U"], "basis": "earth", "units": "m s-1"}],
        "time": {"values": ["2024-01-01T00:00:00", "2024-01-01T02:00:00"]},
    })
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_allclose(out.U[:, 0, 0, 0], [3., -4.], atol=1e-12)
        assert json.loads(out.U.attrs["frameit_metadata_origins"])["units"] == "declaration"
    jobs = conf.source_requests["atmosphere"]["binding"]["operations"]
    assert [float(job["geometry"]["coordinates"]["angle"]["values"]) for job in jobs] == [
        0., np.pi / 2]
    assert [p.read_bytes() for p in paths] == before


def test_remap_uses_destination_original_indices_not_a_renumbered_axis(tmp_path):
    ds = staggered_scene().isel(level=[1, 2])
    ds = ds.assign_coords(level_source_native_index=("level", [1, 2], {"units": "1"}))
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["WT"], "levels": {"indices": [2]}},
        "transforms": [{"fields": ["WT"], "sampling": "mass"}],
    })
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_array_equal(out.level, [15.])
        np.testing.assert_array_equal(out.level_source_native_index, [2])
        np.testing.assert_allclose(out.WT[:, :, 0, 0], 414., atol=1e-12)


def test_grib_derived_uses_selected_cycles_levels_and_real_payloads(tmp_path, monkeypatch):
    from frameit.io import grib_utils
    from frameit.testing.numerical.test_v3_grib_reads import write_messages

    path = write_messages(tmp_path / "input.grib", [
        {"hour": hour, "level": level, "param": param, "cycle": cycle}
        for hour in (0, 1, 2) for level in (700, 850) for param in (131, 132)
        for cycle in (0, 600)])
    before = path.read_bytes()
    conf = configuration(tmp_path, {
        "model": "arome", "files": str(path),
        "variables": {"levels": {"values": [700], "units": "hPa"}},
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "u", "v": "v"}}},
        "wind_pairs": [{"u": "u", "v": "v", "basis": "grid",
                        "rotation": {"method": "geolocation"}}],
        "time": {"cycle": "2026-01-01T00:00:00", "values": ["2026-01-01T01:00:00"]},
    })
    original_payload, reads = grib_utils._grib_payload, []

    def payload(locator, shape, header):
        reads.append((header["paramId"], header["level"], header["cycle"], header["endStep"]))
        return original_payload(locator, shape, header)

    monkeypatch.setattr(grib_utils, "_grib_payload", payload)
    bind_sources(conf)
    assert reads == []
    result = execute_simulation(conf)
    expected = np.array([[[[0., 1701., np.nan], [9999., 1704., 1705.]]]]) * np.sqrt(2)
    ordinary_reader(result.products[0]["path"], {
        "speed": {"values": expected.tolist(), "attrs": {"units": "m s-1"}}})
    assert reads and {entry[:2] for entry in reads} == {(131, 700), (132, 700)}
    assert {str(entry[2]) for entry in reads} == {"2026-01-01T00:00:00.000000000"}
    assert {entry[3] for entry in reads} == {1}
    assert path.read_bytes() == before


def test_fa_explicit_identity_units_keeps_selected_leaf_and_native_support(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_fa_cubes import DECLARATION, fixtures
    from frameit.testing.numerical.test_v3_interpretation import _fa_requests

    paths = fixtures(tmp_path, hours=(0, 1, 2))
    before = [p.read_bytes() for p in paths]
    conf = configuration(tmp_path, {
        "model": "arome", "files": list(map(str, paths)), "profile": "arome_history",
        "variables": {"3d": ["temperature"], "levels": {"indices": [2, 0]}},
        "time": {"values": ["2026-01-01T02:00:00"]},
        "field_metadata": {"temperature": DECLARATION},
        "native_cubes": {"temperature": {
            "records": [f"S{k:03d}TEMPERATURE" for k in (1, 2, 3)],
            "vertical_position": "mass", "sampling": "center"}},
        "transforms": [{"fields": ["temperature"], "units": "K"}],
        "fa": {"earth_radius_m": 6371229.},
        "reader": {"python_executable": sys.executable, "max_points": 1000,
                   "timeout_seconds": 30},
    })
    calls = _fa_requests(monkeypatch)
    bind_sources(conf)
    assert calls and all(c["operation"] == "inspect" for c in calls)
    calls.clear()
    result = execute_simulation(conf)
    reads = [c for c in calls if c["operation"] == "read"]
    assert {c["path"] for c in reads} == {str(paths[2])}
    assert {tuple(c["fields"]) for c in reads} == {
        ("S001TEMPERATURE",), ("S003TEMPERATURE",)}
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_array_equal(out.level, [3, 1])
        np.testing.assert_array_equal(out.level_source_native_index, [2, 0])
        assert out.temperature.attrs["units"] == "K"
        assert set(out.data_vars) == {"temperature"}
        assert "fa_hybrid_a" in out and "fa_hybrid_b" in out
        assert out.fa_hybrid_interface.size == 4
    j, i = np.indices((7, 9))
    expected = np.stack([311. + 10 * j + i, 291. + 10 * j + i])
    expected[:, 1, 1], expected[:, 2, 2] = np.nan, 0.
    ordinary_reader(result.products[0]["path"], {
        "temperature": {"values": expected[None].tolist(), "exact": True,
                        "attrs": {"units": "K", "frameit_method": "transform"},
                        "coordinates": {"level": [3, 1], "level_source_native_index": [2, 0]}}})
    assert [p.read_bytes() for p in paths] == before


def test_noop_sea_transform_retains_each_snapshot_evidence_and_masks(tmp_path):
    from frameit.testing.numerical.test_v3_interpretation import _sea_case

    path, initial = _sea_case(tmp_path, fields=("SST",))
    raw = deepcopy(initial.yaml_config)
    raw["sources"]["surface"]["transforms"] = [{"fields": ["SST"], "sampling": "native"}]
    conf = SimulationConfig(**to_runtime(raw))
    before = path.read_bytes()
    result = execute_simulation(conf)
    interpretation = conf.simulation_parameter["request_plan"]["sources"]["surface"][
        "interpretation"]
    assert len(interpretation["metadata_records"]) == 2
    with xr.open_dataset(result.products[0]["path"]) as out:
        assert out.SST.attrs["surfex_support"] == (
            "FRAC_SEA > 0; no additional fraction weighting applied")
        assert out.SST.attrs["surfex_units_source"] == "source_comment"
        assert np.isnan(out.SST[0, 0, 0])
    ordinary_reader(result.products[0]["path"], {
        "SST": {"attrs": {"units": "K", "frameit_method": "transform"}}})
    assert path.read_bytes() == before


def test_regional_transform_reads_only_required_spatial_neighbours(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    staggered_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["UT"], "levels": {"indices": [2]}},
        "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "transforms": [{"fields": ["UT"], "sampling": "mass",
                        "basis": "earth", "units": "m s-1"}],
        "time": {"values": ["2024-01-01T01:00:00"]},
        "reader": {"chunks": {dim: 1 for dim in ("time", "level", "nj_u", "ni_u", "nj_v", "ni_v")}},
    }, region={"center": {"latitude": -20., "longitude": 60.},
               "width_km": {"x": 2., "y": 2.}})
    footprint = {"UT": set(), "VT": set()}
    original_get = H5NetCDFArrayWrapper.__getitem__

    def selected(array, key):
        if array.variable_name in footprint:
            positions = [np.atleast_1d(np.arange(size)[index]).tolist()
                         for size, index in zip(array.shape, key.tuple, strict=True)]
            assert positions[0] == [1] and positions[1] == [2]
            footprint[array.variable_name].update(
                (y, x) for y in positions[2] for x in positions[3])
        return original_get(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", selected)
    result = execute_simulation(conf)
    assert footprint["UT"] == {(y, x) for y in range(3, 6) for x in range(3, 7)}
    assert footprint["VT"] == {(y, x) for y in range(3, 7) for x in range(3, 6)}
    ordinary_reader(result.products[0]["path"], {
        "UT": {"values": np.full((1, 1, 3, 3), -4.).tolist(),
               "attrs": {"units": "m s-1", "frameit_sampling": "mass"}}})


def test_operation_vertical_conversion_keeps_real_bounds_and_original_indices(tmp_path):
    ds = scene().assign_coords(level_bounds=(
        ("level", "bnds"), [[5., 15.], [15., 25.], [25., 35.]], {"units": "m"}))
    ds.level.attrs.update(bounds="level_bounds", valid_range=[5., 35.])
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["U"], "levels": {"indices": [2, 0], "units": "km"}},
        "transforms": [{"fields": ["U"], "units": "m s-1"}],
    })
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_array_equal(out.level, [.03, .01])
        np.testing.assert_array_equal(out.level_bounds, [[.025, .035], [.005, .015]])
        np.testing.assert_array_equal(out.level_source_native_index, [2, 0])
        np.testing.assert_array_equal(out.level.attrs["valid_range"], [.005, .035])
        assert out.level.attrs["units"] == "km"
        assert out.level_bounds.attrs.get("units", out.level.attrs["units"]) == "km"
    ordinary_reader(result.products[0]["path"], {
        "U": {"values": np.full((3, 2, 3, 3), 3.).tolist(),
              "attrs": {"units": "m s-1"},
              "coordinates": {"level": [.03, .01], "level_source_native_index": [2, 0],
                              "level_bounds": [[.025, .035], [.005, .015]]}}})


def test_missing_selected_vertical_bracket_fails_before_w_values(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    staggered_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["WT"], "levels": {"indices": [3]}},
        "transforms": [{"fields": ["WT"], "sampling": "mass"}],
    })
    original_get = H5NetCDFArrayWrapper.__getitem__

    def forbidden(array, key):
        assert array.variable_name != "WT"
        return original_get(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", forbidden)
    with pytest.raises(ValueError, match="source support unavailable"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def test_projection_declaration_cannot_replace_conflicting_actual_geometry(tmp_path):
    ds = staggered_scene().assign(BETA=0., RPK=0., LON0=60.)
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["UT"]},
        "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid", "rotation": {
            "method": "mesonh_projection", "BETA": 90., "RPK": 0., "LON0": 60.}}],
        "transforms": [{"fields": ["UT"], "sampling": "mass", "basis": "earth"}],
    })
    with pytest.raises(ValueError, match="BETA.*conflict"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def test_numerical_native_grib_cannot_hide_mixed_stored_units(tmp_path, monkeypatch):
    import cfgrib

    from frameit.io.grib_utils import concat_grib2ds_by_vert_coord
    from frameit.testing.numerical.test_wind_preflight import grib_blocks, grib_settings

    paths = [tmp_path / f"sample-{i}.grib" for i in (0, 1)]
    for path in paths:
        path.touch()
    blocks = {
        str(paths[0]): grib_blocks("2024-01-01"),
        str(paths[1]): grib_blocks("2024-01-01T01", units="km h-1"),
    }
    monkeypatch.setattr(cfgrib, "open_datasets", lambda path, **kwargs: blocks[path])
    settings = grib_settings()
    settings.cartesian_horizontal_winds = "native"
    with pytest.raises(ValueError, match="conflicting scientific metadata.*units"):
        concat_grib2ds_by_vert_coord(
            paths, {"isobaricInhPa": {"variables": ["u"], "all_levels": True}}, {},
            index_dir=tmp_path / "cache", wind_conf=settings)


def test_metadata_binding_never_materializes_field_sized_preparation_probes(tmp_path, monkeypatch):
    from frameit.processing import wind_collocation

    staggered_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": ["UT"]},
        "transforms": [{"fields": ["UT"], "sampling": "mass"}],
    })
    interpolate = wind_collocation.interpolate_staggered
    calls = []

    def metadata_only(value, dimension, target):
        if value.ndim > 1:
            calls.append(value.shape)
            assert hasattr(value.data, "dask"), "Metadata binding allocated a field-sized probe"
        return interpolate(value, dimension, target)

    monkeypatch.setattr(wind_collocation, "interpolate_staggered", metadata_only)
    bind_sources(conf)
    assert calls and not conf.output_dir.exists()


@pytest.mark.parametrize("problem", [
    "basis", "rotation", "units", "quantity", "statistics", "angle",
])
def test_croco_known_metadata_conflicts_fail_before_any_scientific_support(
        tmp_path, monkeypatch, problem):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.testing.numerical.test_croco_vectors import vector_scene

    ds = vector_scene()
    pair = {"u": "u", "v": "v", "basis": "grid",
            "rotation": {"method": "coordinate", "coordinate": "angle"}}
    if problem == "basis":
        pair = {"u": "u", "v": "v", "basis": "earth"}
    elif problem == "rotation":
        pair["rotation"] = {"method": "geolocation"}
    elif problem == "units":
        ds.v.attrs["units"] = "Pa"
    elif problem == "quantity":
        ds.v.attrs["standard_name"] = "northward_sea_water_velocity"
    elif problem == "angle":
        ds.angle.values[2, 2] = np.nan
    else:
        ds.v.attrs["cell_methods"] = "time: mean"
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "model": "croco", "variables": {"3d": ["u"]}, "wind_pairs": [pair],
        "transforms": [{"fields": ["u"], "sampling": "mass", "basis": "earth"}],
    })
    original_get = H5NetCDFArrayWrapper.__getitem__

    def metadata_only(array, key):
        assert array.variable_name not in {"u", "v", "mask_rho", "zeta", "h"}
        return original_get(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", metadata_only)
    with pytest.raises(ValueError, match="CROCO"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def test_numerical_native_netcdf_cannot_hide_mixed_stored_units(tmp_path):
    paths = []
    for i, units in enumerate(("knots", "m s-1")):
        ds = scene().isel(time=[i]).drop_vars("V")
        ds.U.attrs = {"units": units}
        path = tmp_path / f"sample-{i}.nc"
        ds.to_netcdf(path)
        paths.append(path)
    conf = configuration(tmp_path, {"variables": {"3d": ["U"]}})
    conf.velocity_aliases = {"u_velocity": "U", "v_velocity": "V", "w_velocity": "W"}
    with pytest.raises(ValueError, match="conflicting scientific metadata.*units"):
        concat_nc2ds_by_vert_coord(
            paths, {"level": {"variables": ["U"], "all_levels": True}}, {}, wind_conf=conf)


@pytest.mark.parametrize("role", ["u", "v"])
@pytest.mark.parametrize("operation", ["derived", "transform"])
def test_vertical_quantity_cannot_be_declared_a_horizontal_component(
        tmp_path, monkeypatch, role, operation):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    ds = scene().rename({"U" if role == "u" else "V": "W"})
    ds.W[:] = 3. if role == "u" else 4.
    ds.W.values[1, 1, 0, :2] = [np.nan, 0.]
    ds.W.attrs = {"units": "m s-1", "standard_name": "upward_air_velocity"}
    ds.to_netcdf(tmp_path / "input.nc")
    before = (tmp_path / "input.nc").read_bytes()
    inputs = {"u": "W" if role == "u" else "U", "v": "V" if role == "u" else "W"}
    source = {"wind_pairs": [{**inputs, "basis": "earth"}]}
    if operation == "derived":
        source["derived"] = {"speed": {"method": "wind_speed", "inputs": inputs}}
    else:
        source["variables"] = {"3d": ["W"]}
        source["transforms"] = [{"fields": ["W"], "basis": "earth"}]
    conf = configuration(tmp_path, source)
    original_get = H5NetCDFArrayWrapper.__getitem__

    def metadata_only(array, key):
        assert array.variable_name not in {"U", "V", "W"}
        return original_get(array, key)

    with monkeypatch.context() as guard:
        guard.setattr(H5NetCDFArrayWrapper, "__getitem__", metadata_only)
        with pytest.raises(ValueError, match="W: standard_name.*wrong wind component"):
            bind_sources(conf)
        with pytest.raises(ValueError, match="W: standard_name.*wrong wind component"):
            execute_simulation(conf)
    assert not conf.output_dir.exists()
    native = configuration(tmp_path, {"variables": {"3d": ["W"]}})
    result = execute_simulation(native)
    ordinary_reader(result.products[0]["path"], {
        "W": {"values": ds.W.values.tolist(), "exact": True, "attrs": ds.W.attrs}})
    assert (tmp_path / "input.nc").read_bytes() == before


@pytest.mark.parametrize("standards", [
    ("eastward_wind", "northward_wind"), (None, None), ("x_wind", "y_wind"),
])
def test_horizontal_quantity_validation_keeps_metadata_gaps_and_narrow_basis_exception(
        tmp_path, standards):
    ds = scene()
    for name, standard in zip(("U", "V"), standards, strict=True):
        ds[name].attrs.pop("standard_name")
        if standard:
            ds[name].attrs["standard_name"] = standard
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "wind_pairs": [{"u": "U", "v": "V", "basis": "earth"}],
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "U", "v": "V"}}},
    })
    result = execute_simulation(conf)
    ordinary_reader(result.products[0]["path"], {
        "speed": {"values": np.full((3, 3, 3, 3), 5.).tolist(),
                  "attrs": {"units": "m s-1", "wind_reference_frame": "earth"}}})


def test_mass_transform_keeps_one_sampling_grid_with_per_record_rotation(tmp_path):
    paths = []
    for hour, angle in ((0, 0.), (2, np.pi / 2)):
        ds = staggered_scene().isel(time=[hour]).assign_coords(
            angle=xr.DataArray(angle, attrs={"units": "rad"}))
        path = tmp_path / f"sample-{hour}.nc"
        ds.to_netcdf(path)
        paths.append(path)
    before = [path.read_bytes() for path in paths]
    conf = configuration(tmp_path, {
        "files": list(map(str, reversed(paths))),
        "variables": {"3d": ["UT"], "levels": {"indices": [2]}},
        "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "transforms": [{"fields": ["UT"], "sampling": "mass",
                        "basis": "earth", "units": "m s-1"}],
        "time": {"values": ["2024-01-01T00:00:00", "2024-01-01T02:00:00"]},
    })
    _, children, plans = bind_sources(conf)
    jobs = children["atmosphere"].source_requests["atmosphere"]["binding"]["operations"]
    assert len(jobs) == 2 and len({job["grid_id"] for job in jobs}) == 1
    assert [float(job["geometry"]["coordinates"]["angle"]["values"]) for job in jobs] == [
        0., np.pi / 2]
    grid = plans["atmosphere"]["representation_grids"][jobs[0]["grid_id"]]
    assert {"latitude", "longitude", "ni", "nj"} <= set(grid["coordinates"])
    assert "angle" not in grid["coordinates"]
    result = execute_simulation(conf)
    expected = np.broadcast_to(np.array([3., -4.])[:, None, None, None], (2, 1, 9, 9))
    ordinary_reader(result.products[0]["path"], {
        "UT": {"values": expected.tolist(),
               "attrs": {"units": "m s-1", "wind_reference_frame": "earth"},
               "coordinates": {"angle": [0., np.pi / 2], "level": [15.],
                               "level_source_native_index": [2]}}})
    subprocess.run([sys.executable, "-c", """
import sys, yaml, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    assert out.angle.dims == ('time',)
    np.testing.assert_array_equal(out.time.values, np.array(
        ['2024-01-01T00', '2024-01-01T02'], dtype='datetime64[ns]'))
with open(sys.argv[2]) as stream:
    jobs = yaml.safe_load(stream)['sources']['atmosphere']['operations']
assert len(jobs) == 2 and len({job['grid_id'] for job in jobs}) == 1
assert [job['rotation_coordinate']['values'] for job in jobs] == [0., np.pi/2]
assert all(job['rotation_coordinate']['name'] == 'angle'
           and job['rotation_coordinate']['attributes']['units'] == 'rad' for job in jobs)
assert [job['source_time'] for job in jobs] == [
    '2024-01-01T00:00:00.000000000', '2024-01-01T02:00:00.000000000']
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(conf.output_dir / "run-provenance.yaml")],
                   check=True, capture_output=True, text=True)
    assert [path.read_bytes() for path in paths] == before


def test_numeric_angle_metadata_survives_required_portable_provenance(tmp_path):
    import yaml

    source = tmp_path / "input.nc"
    ds = staggered_scene().assign_coords(angle=xr.DataArray(np.pi / 2, attrs={
        "units": "rad", "valid_range": np.array([0., np.pi]),
        "valid_min": np.float32(0.), "valid_max": np.float64(np.pi),
        "calibration_revision": np.int32(7)}))
    ds.VT.values[2, 2, 3, 3] = np.nan
    ds.to_netcdf(source)
    source.chmod(0o444)
    before = source.read_bytes()
    conf = configuration(tmp_path, {
        "variables": {"3d": ["UT"], "levels": {"indices": [2]}},
        "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "transforms": [{"fields": ["UT"], "sampling": "mass",
                        "basis": "earth", "units": "m s-1"}],
        "time": {"values": ["2024-01-01T00:00:00", "2024-01-01T02:00:00"]},
    })
    try:
        result = execute_simulation(conf)
    finally:
        assert source.read_bytes() == before
    jobs = conf.source_requests["atmosphere"]["binding"]["operations"]
    assert len(jobs) == 2 and len({job["grid_id"] for job in jobs}) == 1
    for job in jobs:
        descriptor = job["rotation_coordinate"]
        assert descriptor["name"] == "angle" and descriptor["dimensions"] == []
        assert descriptor["values"] == np.pi / 2
        attrs = descriptor["attributes"]
        assert attrs["valid_range"] == [0., np.pi]
        assert all(type(value) is float for value in attrs["valid_range"])
        assert type(attrs["valid_min"]) is type(attrs["valid_max"]) is float
        assert type(attrs["calibration_revision"]) is int
        assert yaml.safe_load(yaml.safe_dump(descriptor)) == descriptor
    subprocess.run([sys.executable, "-c", """
import sys, yaml, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    assert set(out.data_vars) == {'UT'}
    expected = np.full((2, 1, 9, 9), -4.)
    expected[1, 0, 2:4, 3] = np.nan
    np.testing.assert_allclose(out.UT.values, expected, rtol=1e-14, atol=1e-12)
    np.testing.assert_array_equal(out.time.values, np.array(
        ['2024-01-01T00', '2024-01-01T02'], dtype='datetime64[ns]'))
    np.testing.assert_array_equal(out.level, [15.])
    np.testing.assert_array_equal(out.level_source_native_index, [2])
    assert out.UT.attrs['units'] == 'm s-1'
    assert out.UT.attrs['wind_reference_frame'] == 'earth'
    np.testing.assert_array_equal(out.angle.attrs['valid_range'], [0., np.pi])
    assert out.angle.attrs['valid_min'] == 0. and out.angle.attrs['valid_max'] == np.pi
    assert out.angle.attrs['calibration_revision'] == 7
with open(sys.argv[2]) as stream:
    jobs = yaml.safe_load(stream)['sources']['atmosphere']['operations']
assert len(jobs) == 2 and len({job['grid_id'] for job in jobs}) == 1
assert [job['source_time'] for job in jobs] == [
    '2024-01-01T00:00:00.000000000', '2024-01-01T02:00:00.000000000']
for job in jobs:
    angle = job['rotation_coordinate']
    assert angle['name'] == 'angle' and angle['dimensions'] == []
    assert angle['values'] == np.pi/2
    attrs = angle['attributes']
    assert attrs['units'] == 'rad' and attrs['valid_range'] == [0., np.pi]
    assert all(type(value) is float for value in attrs['valid_range'])
    assert attrs['valid_min'] == 0. and attrs['valid_max'] == np.pi
    assert type(attrs['valid_min']) is type(attrs['valid_max']) is float
    assert attrs['calibration_revision'] == 7 and type(attrs['calibration_revision']) is int
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(conf.output_dir / "run-provenance.yaml")],
                   check=True, capture_output=True, text=True)
    assert source.read_bytes() == before
