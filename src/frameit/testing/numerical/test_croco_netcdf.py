"""Native CROCO history scalars retain sigma axes and valid formula dependencies."""

import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources
from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord


def croco_scene():
    times = np.array(["2024-12-10T01", "2024-12-10T02"], dtype="datetime64[ns]")
    lat = -20. + (np.arange(7)-3)[:, None]*.01 + np.zeros((7, 7))
    lon = 60. + (np.arange(7)-3)[None, :]*.01/np.cos(np.deg2rad(20.)) + np.zeros((7, 7))
    values = np.arange(2*3*7*7, dtype=float).reshape(2, 3, 7, 7)
    values[0, 0, 3, 3] = 0.
    values[0, 1, 2, 2] = np.nan
    ds = xr.Dataset({
        "temp": (("time", "s_rho", "eta_rho", "xi_rho"), values,
                 {"units": "Celsius", "standard_name": "sea_water_potential_temperature"}),
        "salt": (("time", "s_rho", "eta_rho", "xi_rho"), values+30., {"units": "PSU"}),
        "tracer_w": (("time", "s_w", "eta_rho", "xi_rho"), np.ones((2, 4, 7, 7)), {"units": "1"}),
        "h": (("eta_rho", "xi_rho"), np.full((7, 7), 20.), {"units": "meter"}),
        "zeta": (("time", "eta_rho", "xi_rho"), np.broadcast_to([[[1.]], [[2.]]], (2, 7, 7)), {"units": "meter"}),
        "Cs_rho": ("s_rho", [-.8, -.25, -.1]), "Cs_w": ("s_w", [-1., -.5, -.2, 0.]),
        "hc": xr.DataArray(5., attrs={"units": "meter"}), "Vtransform": xr.DataArray(2.),
        "scrum_time": ("time", times, {"time_origin": "1900-01-01"}),
    }, coords={"time": times, "s_rho": ("s_rho", [-.9, -.5, -.1]),
               "s_w": ("s_w", [-1., -.6, -.2, 0.]),
               "eta_rho": ("eta_rho", np.arange(7), {"c_grid_dynamic_range": "2:6"}),
               "xi_rho": ("xi_rho", np.arange(7), {"c_grid_dynamic_range": "2:6"}),
               "lat_rho": (("eta_rho", "xi_rho"), lat, {"units": "degree_north", "standard_name": "latitude"}),
               "lon_rho": (("eta_rho", "xi_rho"), lon, {"units": "degree_east", "standard_name": "longitude"})},
                    attrs={"type": "CROCO history file", "Vtransform": "2"})
    for axis, curve in (("s_rho", "Cs_rho"), ("s_w", "Cs_w")):
        ds[axis].attrs = {"axis": "Z", "positive": "up", "Vtransform": "2",
                          "standard_name": "ocean_s_coordinate_g2" if axis == "s_rho" else "ocean_s_coordinate_g2_at_w_location",
                          "formula_terms": f"s: {axis} C: {curve} eta: zeta depth: h depth_c: hc"}
    for name in ("time", "scrum_time"):
        ds[name].encoding.update(units="seconds since 2000-01-01", calendar="gregorian")
    return ds


def croco_document(directory, paths, *, variables=None):
    return {"schema_version": 2, "model": "croco", "run": {"name": "native-sigma"},
            "input": {"format": "netcdf", "files": list(map(str, paths))},
            "variables": variables or {"s_rho": {"names": ["temp", "salt"], "levels": {"indices": [1, 0]}},
                                       "s_w": {"names": ["tracer_w"], "levels": {"indices": [2, 0]}},
                                       "surface": {"names": ["zeta"]}},
            "tracking": {"method": "fixed_box", "fixed_box": {"center": {"latitude": -20., "longitude": 60.}}},
            "domain": {"size_km": {"x": 2., "y": 2.}},
            "execution": {"native_threads": 1, "dask_workers": 1},
            "output": {"directory": str(directory/"out"), "overwrite": False,
                       "synchronous_export": True, "max_workers": 1,
                       "cartesian": {"horizontal_winds": "native"}}}


def test_croco_scalar_sigma_roundtrip(tmp_path, monkeypatch):
    import builtins
    from frameit.core.execution import execute_simulation

    path = tmp_path/"ocean.nc"
    croco_scene().to_netcdf(path)
    conf = SimulationConfig.from_mapping_with_model_preset(croco_document(tmp_path, [path]))
    original = builtins.__import__

    def core_only(name, *args, **kwargs):
        if name.split(".")[0] in {"xesmf", "ESMF", "esmpy", "epygram", "eccodes", "cfgrib", "zarr"}:
            raise AssertionError(f"Native scalar extraction attempted optional dependency {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", core_only)
    result = execute_simulation(conf)
    assert result.ok, result
    products = {p["group"]: p["path"] for p in result.products if p["role"] == "cart"}
    assert set(products) == {"s_rho", "s_w", "surface"}
    subprocess.run([sys.executable, "-c", """
import sys, xarray as xr, numpy as np
with xr.open_dataset(sys.argv[1]) as out,xr.open_dataset(sys.argv[4]) as src:
    np.testing.assert_array_equal(out.s_rho,[-.5,-.9])
    np.testing.assert_array_equal(out.s_rho_source_native_index,[1,0])
    np.testing.assert_array_equal(out.Cs_rho,[-.25,-.8])
    assert out.s_rho.attrs['standard_name']=='ocean_s_coordinate_g2'
    assert 'units' not in out.s_rho.attrs
    assert 's_w' not in out.dims
    for t in (0,1):
        window=src.isel(time=t,s_rho=[1,0],eta_rho=out.eta_rho[t].values.astype(int),xi_rho=out.xi_rho[t].values.astype(int))
        for name in ['temp','salt','h','zeta','lat_rho','lon_rho']:
            np.testing.assert_array_equal(out[name][t],window[name])
    np.testing.assert_array_equal(out.time,src.time)
    np.testing.assert_array_equal(out.scrum_time,src.scrum_time)
    assert out.time.encoding['calendar']=='gregorian'
    for term in out.s_rho.attrs['formula_terms'].split()[1::2]: assert term in out
    # Independent CF g2 anchor: h20,hc5,s=-.5,C=-.25,zeta1 -> z=-5.3m.
    s=(out.hc*out.s_rho+out.h*out.Cs_rho)/(out.hc+out.h)
    z=out.zeta+(out.zeta+out.h)*s
    np.testing.assert_allclose(z.isel(time=0,s_rho=0),-5.3,rtol=0,atol=1e-12)
with xr.open_dataset(sys.argv[2]) as out:
    np.testing.assert_array_equal(out.s_w,[-.2,-1.])
    np.testing.assert_array_equal(out.Cs_w,[-.2,-1.])
    np.testing.assert_array_equal(out.s_w_source_native_index,[2,0])
    assert 's_rho' not in out.dims
    for term in out.s_w.attrs['formula_terms'].split()[1::2]: assert term in out
with xr.open_dataset(sys.argv[3]) as out:
    assert 's_rho' not in out.dims and 's_w' not in out.dims
    np.testing.assert_array_equal(out.zeta[:,0,0],[1.,2.])
assert 'frameit' not in sys.modules
""", products["s_rho"], products["s_w"], products["surface"], str(path)], check=True)


@pytest.mark.parametrize("problem", ["transform", "conflicting_transform", "formula", "missing_dependency", "clock", "calendar", "family", "curve_range", "positive", "critical_depth"])
def test_croco_rejects_unresolved_native_definitions(problem):
    from frameit.io.croco_utils import prepare_croco

    ds = croco_scene()
    if problem == "transform":
        ds["Vtransform"] = xr.DataArray(1.)
        ds.attrs["Vtransform"] = "1"
    elif problem == "conflicting_transform":
        ds.s_rho.attrs["Vtransform"] = "1"
    elif problem == "formula":
        ds.s_rho.attrs["formula_terms"] = "s: s_rho C: Cs_rho eta: zeta depth: h"
    elif problem == "missing_dependency":
        ds = ds.drop_vars("hc")
    elif problem == "clock":
        ds["scrum_time"] = ds.scrum_time + np.array([1, 0], dtype="timedelta64[h]")
    elif problem == "calendar":
        ds.time.encoding["calendar"] = "360_day"
    elif problem == "curve_range":
        ds.Cs_rho.values[0] = -2.
    elif problem == "positive":
        ds.s_rho.attrs["positive"] = "down"
    elif problem == "critical_depth":
        ds.hc.values[...] = 0.
    else:
        ds.attrs["type"] = "CROCO averages file"
    with pytest.raises(ValueError, match="CROCO|Vtransform|formula|clock|calendar|history"):
        prepare_croco(ds, SimpleNamespace())


@pytest.mark.parametrize("selection", [{"s_rho": {"names": ["temp"], "levels": {"values": [-.50001]}}},
                                       {"s_rho": {"names": ["missing"], "levels": "all"}},
                                       {"surface": {"names": ["temp"]}}])
def test_croco_invalid_selection_fails_preflight_and_direct_loader(tmp_path, selection):
    path = tmp_path/"ocean.nc"
    croco_scene().to_netcdf(path)
    conf = SimulationConfig.from_mapping_with_model_preset(croco_document(tmp_path, [path], variables=selection))
    with pytest.raises(ValueError, match="level|temp|missing|surface"):
        preflight(conf)
    with DatasetResources() as resources, pytest.raises(ValueError, match="level|temp|missing|surface"):
        concat_nc2ds_by_vert_coord([path], conf.requests_user(), conf.requests_tracker(),
                                   method=conf.tracking_method, wind_conf=conf, resources=resources)


def test_croco_init_inspect_replay_and_atmospheric_tracker_rejection(tmp_path):
    from frameit.core.configuration import resolved_configuration, write_template

    path = tmp_path/"ocean.nc"
    croco_scene().to_netcdf(path)
    raw = croco_document(tmp_path, [path])
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    preflight(conf)
    replay = SimulationConfig.from_mapping_with_model_preset(resolved_configuration(conf))
    assert replay.atm_model == "CROCO" and replay.name_latitude == "lat_rho"
    write_template("croco", tmp_path/"croco.yaml")
    subprocess.run([sys.executable, "-m", "frameit", "inspect", str(tmp_path), "--model", "croco",
                    "--format", "netcdf", "--pattern", "ocean.nc"], check=True, capture_output=True, text=True)
    raw["tracking"]["method"] = "wind_pressure"
    with pytest.raises(ValueError, match="CROCO|croco|fixed_box"):
        SimulationConfig.from_mapping_with_model_preset(raw)


def test_croco_selected_loading_stays_lazy_and_snapshots_preserve_state(tmp_path):
    paths = []
    for index in (0, 1):
        path = tmp_path/f"snapshot-{index}.nc"
        croco_scene().isel(time=[index]).to_netcdf(path)
        paths.append(path)
    conf = SimulationConfig.from_mapping_with_model_preset(croco_document(tmp_path, paths))
    with DatasetResources() as resources:
        groups, _ = concat_nc2ds_by_vert_coord(paths, conf.requests_user(), conf.requests_tracker(),
                                              method="fixed_box", wind_conf=conf, resources=resources)
        assert hasattr(groups["s_rho"].temp.data, "dask")
        assert groups["s_rho"].sizes["s_rho"] == 2
        np.testing.assert_array_equal(groups["s_rho"].zeta[:,0,0], [1.,2.])


@pytest.mark.parametrize("change", ["units", "standard_name", "curve", "critical_depth"])
def test_croco_time_series_rejects_changing_scientific_definitions(tmp_path, change):
    paths = []
    for index in (0, 1):
        ds = croco_scene().isel(time=[index])
        if index:
            if change == "units":
                ds.temp.attrs["units"] = "K"
            elif change == "standard_name":
                ds.temp.attrs["standard_name"] = "sea_water_temperature"
            elif change == "curve":
                ds.Cs_rho.values[1] = -.3
            else:
                ds["hc"] = xr.DataArray(6., attrs={"units": "meter"})
        path = tmp_path/f"snapshot-{index}.nc"
        ds.to_netcdf(path)
        paths.append(path)
    conf = SimulationConfig.from_mapping_with_model_preset(croco_document(tmp_path, paths))
    with pytest.raises(ValueError, match="CROCO|metadata|definitions"):
        preflight(conf)
    with DatasetResources() as resources, pytest.raises(ValueError, match="CROCO|metadata|definitions"):
        concat_nc2ds_by_vert_coord(paths, conf.requests_user(), conf.requests_tracker(), method="fixed_box",
                                   wind_conf=conf, resources=resources)


@pytest.mark.parametrize("unsupported", ["faces", "polar"])
def test_croco_unqualified_analysis_does_not_silently_use_scalar_path(tmp_path, unsupported):
    path = tmp_path/"ocean.nc"
    ds = croco_scene()
    raw = croco_document(tmp_path, [path])
    if unsupported == "faces":
        ds["u"] = (("time", "s_rho", "eta_rho", "xi_u"), np.ones((2,3,7,6)), {"units": "meter second-1"})
        raw["variables"] = {"s_rho": {"names": ["u"], "levels": "all"}}
    else:
        raw["polar"] = {"enabled": True}
    ds.to_netcdf(path)
    with pytest.raises(ValueError, match="CROCO.*(?:qualified|labelled)"):
        preflight(SimulationConfig.from_mapping_with_model_preset(raw))
