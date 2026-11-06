"""Exact synthetic atmosphere/ocean coupling does not authorise real time pairing."""

import json
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.coupled import prepare_sources
from frameit.core.execution import execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_nemo_netcdf import component_scene, nemo_scene


def coupled_document(directory, *, moving=False, exact=True, scalar_polar=False):
    sources = {}
    times = nemo_scene().time_counter.values[:2]
    atmospheric_times = times if exact else times - np.timedelta64(30, "m")
    atmosphere = []
    for name, value in (("prmsl", 100000.), ("u10", 0.), ("v10", 3.)):
        ds = xr.Dataset({name: (("valid_time", "latitude", "longitude"),
                                np.full((2, 9, 9), value), {
                                    "units": "Pa" if name == "prmsl" else "m s-1"})},
                        coords={"valid_time": atmospheric_times,
                                "time": xr.DataArray(np.datetime64("2024-12-11", "ns"),
                                                     attrs={"standard_name": "forecast_reference_time"}),
                                "latitude": ("latitude", -20. + np.arange(-4, 5)*.008, {"units": "degrees_north"}),
                                "longitude": ("longitude", 60. + np.arange(-4, 5)*.008/np.cos(np.deg2rad(20.)),
                                              {"units": "degrees_east"})})
        path = directory / f"{name}.nc"
        ds.to_netcdf(path)
        atmosphere.append(str(path))
    sources["arome"] = {"model": "arome", "input": {"format": "netcdf", "files": atmosphere,
        "netcdf": {"file_layout": "variables"}, "wind_pairs": [
            {"group": "fields_2d", "u": "u10", "v": "v10", "reference_frame": "earth"}]},
        "variables": {"fields_2d": {"names": ["prmsl", "u10", "v10"]}}}
    for source, depth, field, dx, dy in (("nemo_t", "deptht", "votemper", 0., 0.),
                                       ("nemo_u", "depthu", "vozocrtx", .006, 0.),
                                       ("nemo_v", "depthv", "vomecrty", 0., .006),
                                       ("nemo_w", "depthw", "vovecrtz", 0., 0.)):
        ds = nemo_scene() if source == "nemo_t" else component_scene(depth, field, shift_x=dx, shift_y=dy)
        ds = ds.isel(time_counter=slice(0, 2))
        if scalar_polar and source == "nemo_t":
            ds.votemper.values[0, :, 3, 3] = np.nan
        path = directory / f"{source}.nc"
        ds.to_netcdf(path)
        sources[source] = {"model": "nemo", "input": {"format": "netcdf", "files": [str(path)]},
                           "variables": {depth: {"names": [field], "levels": "stored"}}}
    raw = {"schema_version": "2.1", "model": "arome", "run": {"name": "coupled-ocean"},
           "input": {"sources": sources}, "domain": {"width_km": {"x": 2., "y": 2.}},
           "tracking": {"source": "arome", "method": "fixed_box", "fixed_box": {
               "center": {"latitude": -20., "longitude": 60.}}},
           "execution": {"native_threads": 1, "dask_workers": 1},
           "output": {"directory": str(directory / "out"), "overwrite": False,
                      "synchronous_export": True, "max_workers": 1,
                       "cartesian": {"horizontal_vectors": "native"}}}
    if moving:
        track = directory / "track.nc"
        xr.Dataset({"latitude": ("time", [-20., -19.99]),
                    "longitude": ("time", [60., 60. + .01/np.cos(np.deg2rad(20.))])},
                   coords={"time": times}).to_netcdf(track)
        raw["tracking"] = {"source": "arome", "method": "prescribed_track", "prescribed_track": {"file": str(track)}}
    if scalar_polar:
        raw["domain"]["width_km"] = {"x": 4., "y": 4.}
        raw["polar"] = {"enabled": True, "shared_target": True, "azimuth_count": 8}
        for source in sources:
            sources[source]["polar"] = {"enabled": source in {"arome", "nemo_t"}}
        sources["arome"]["polar"]["variables"] = {"fields_2d": {"names": ["prmsl"]}}
        sources["nemo_t"]["polar"]["variables"] = {"deptht": {"names": ["votemper"]}}
    return raw


@pytest.mark.parametrize("moving", [False, True])
@pytest.mark.parametrize("synchronous", [True, False])
def test_nemo_arome_exact_track_maps_each_grid_independently(tmp_path, moving, synchronous, monkeypatch):
    import builtins

    raw = coupled_document(tmp_path, moving=moving)
    raw["output"]["synchronous_export"] = synchronous
    original = builtins.__import__

    def base_only(name, *args, **kwargs):
        if name.split(".")[0] in {"xesmf", "ESMF", "esmpy", "epygram", "cfgrib", "eccodes", "zarr"}:
            raise AssertionError(f"Base coupled path attempted {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", base_only)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    products = {p["source"]: p["path"] for p in result.products if p["role"] == "cart"}
    assert set(products) == {"arome", "nemo_t", "nemo_u", "nemo_v", "nemo_w"}
    subprocess.run([sys.executable, "-c", """
import json, sys, xarray as xr, numpy as np
from pathlib import Path
paths, moving = json.loads(sys.argv[1]), sys.argv[2] == 'True'
datasets = {name: xr.open_dataset(path) for name,path in paths.items()}
try:
    a = datasets['arome']
    assert a.forecast_reference_time.values == np.datetime64('2024-12-11')
    for name, data in datasets.items():
        np.testing.assert_array_equal(data.time, a.time)
        assert data.attrs['source_id'] == name
    for name, x0, y0 in [('nemo_t',2,2),('nemo_u',1,2),('nemo_v',2,1),('nemo_w',2,2)]:
        data = datasets[name]
        np.testing.assert_array_equal(data.x[0], np.arange(x0,x0+3))
        np.testing.assert_array_equal(data.y[0], np.arange(y0,y0+3))
        np.testing.assert_array_equal(data.x[1], np.arange(x0,x0+3) + int(moving))
        np.testing.assert_array_equal(data.y[1], np.arange(y0,y0+3) + int(moving))
        assert data.time.attrs['bounds'] in data
        assert 'time_centered_bounds' in data
        assert 'horizontal_wind_representation' not in data.attrs
        field = {'nemo_t':'votemper','nemo_u':'vozocrtx','nemo_v':'vomecrty','nemo_w':'vovecrtz'}[name]
        with xr.open_dataset(Path(sys.argv[3])/f'{name}.nc') as source:
            for t in (0,1):
                expected = source[field].isel(time_counter=t,y=data.y[t].values.astype(int),
                                               x=data.x[t].values.astype(int))
                np.testing.assert_array_equal(data[field][t],expected)
finally:
    for data in datasets.values(): data.close()
assert 'frameit' not in sys.modules
""", json.dumps(products), str(moving), str(tmp_path)], check=True)
    provenance = yaml.safe_load((tmp_path / "out/run-provenance.yaml").read_text())
    assert provenance["time_alignment"]["policy"] == "common"
    assert provenance["sources"]["nemo_u"]["model"] == "NEMO"


def test_real_layout_half_hour_means_have_no_exact_overlap(tmp_path):
    raw = coupled_document(tmp_path, exact=False)
    with pytest.raises(ValueError, match="no exact common timestamps"):
        prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("strict", [False, True])
def test_nemo_arome_common_exclusions_and_strict_mismatch(tmp_path, strict):
    raw = coupled_document(tmp_path)
    path = tmp_path / "nemo_t.nc"
    with xr.open_dataset(path) as source:
        subset = source.isel(time_counter=[0]).load()
    short = tmp_path / "short.nc"
    subset.to_netcdf(short)
    raw["input"]["sources"]["nemo_t"]["input"]["files"] = [str(short)]
    if strict:
        raw["input"]["time_alignment"] = "strict"
        with pytest.raises(ValueError, match="Strict source time alignment"):
            prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    else:
        plan, _, _ = prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))
        assert len(plan["time_alignment"]["selected_times"]) == 1
        assert len(plan["time_alignment"]["sources"]["arome"]["skipped_times"]) == 1


def test_nemo_arome_outside_grid_fails_without_edge_substitution(tmp_path):
    raw = coupled_document(tmp_path)
    raw["tracking"]["fixed_box"]["center"] = {"latitude": -20.031, "longitude": 60.}
    with pytest.raises(ValueError, match="outside a selected source grid"):
        execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    status = yaml.safe_load((tmp_path / "out/run-status.yaml").read_text())
    assert status["state"] == "failed"
    assert status["products"] == []


def test_nemo_arome_shared_scalar_targets_preserve_source_times_and_masks(tmp_path, monkeypatch):
    pytest.importorskip("xesmf")
    from frameit.processing.polar import polar_proj

    for name in ("wind_names", "normalize_winds", "add_speed_from_uv_dict", "add_vrad_vtan_from_polar_dict"):
        original = getattr(polar_proj, name)
        conf_index = 0 if name == "wind_names" else 1

        def atmosphere_only(*args, _original=original, _index=conf_index, **kwargs):
            if args[_index].atm_model == "NEMO":
                raise AssertionError("NEMO scalar polar sampling called an atmospheric wind helper")
            return _original(*args, **kwargs)

        monkeypatch.setattr(polar_proj, name, atmosphere_only)
    raw = coupled_document(tmp_path, scalar_polar=True)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    products = {p["source"]: p["path"] for p in result.products if p["role"] == "polar"}
    assert set(products) == {"arome", "nemo_t"}
    subprocess.run([sys.executable, "-c", """
import json, sys, xarray as xr, numpy as np
paths = json.loads(sys.argv[1])
with xr.open_dataset(paths['arome']) as a, xr.open_dataset(paths['nemo_t']) as n:
    for name in ['time','rr','theta','center_lon','center_lat']:
        np.testing.assert_array_equal(a[name],n[name])
    np.testing.assert_array_equal(a.longitude,n.nav_lon)
    np.testing.assert_array_equal(a.latitude,n.nav_lat)
    assert a.attrs['common_polar_target_id'] == n.attrs['common_polar_target_id']
    assert n.time.attrs['bounds'] in n and 'time_centered_bounds' in n
    assert n.votemper.attrs['cell_methods'] == 'time: mean (interval: 240 s)'
    assert np.isfinite(a.prmsl).all()
    assert np.isnan(n.votemper.isel(time=0,rr=0)).all()
assert 'frameit' not in sys.modules
""", json.dumps(products)], check=True)


def test_nemo_arome_shared_target_budget_fails_before_outputs(tmp_path):
    raw = coupled_document(tmp_path, scalar_polar=True)
    raw["polar"]["max_points"] = 1
    with pytest.raises(ValueError, match="polar.max_points"):
        preflight(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not (tmp_path / "out").exists()


def test_nemo_arome_forecast_cycle_identity_is_not_the_sample_clock(tmp_path):
    raw = coupled_document(tmp_path)
    with xr.open_dataset(tmp_path / "u10.nc") as source:
        changed = source.load().assign_coords(time=np.datetime64("2024-12-11T06", "ns"))
    changed.time.attrs["standard_name"] = "forecast_reference_time"
    path = tmp_path / "different-cycle.nc"
    changed.to_netcdf(path)
    raw["input"]["sources"]["arome"]["input"]["files"][1] = str(path)
    with pytest.raises(ValueError, match="forecast cycle"):
        prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))


@pytest.mark.parametrize("strict", [False, True])
def test_nemo_arome_prescribed_track_coverage_remains_exact(tmp_path, strict):
    raw = coupled_document(tmp_path, moving=True)
    with xr.open_dataset(tmp_path / "track.nc") as source:
        short = source.isel(time=[0]).load()
    path = tmp_path / "short-track.nc"
    short.to_netcdf(path)
    raw["tracking"]["prescribed_track"]["file"] = str(path)
    raw["input"]["time_alignment"] = "strict" if strict else "common"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if strict:
        with pytest.raises(ValueError, match="track lacks strict source times"):
            prepare_sources(conf)
    else:
        plan, _, _ = prepare_sources(conf)
        assert len(plan["time_alignment"]["selected_times"]) == 1


def test_nemo_arome_interrupted_export_and_overwrite_protection(tmp_path, monkeypatch):
    from frameit.io import netcdf_export

    raw = coupled_document(tmp_path)
    original = netcdf_export.write_dataset_netcdf

    def interrupted(ds, path, **kwargs):
        if ".cart.nemo_u." in str(path):
            raise OSError("synthetic interrupted ocean export")
        return original(ds, path, **kwargs)

    monkeypatch.setattr(netcdf_export, "write_dataset_netcdf", interrupted)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(OSError, match="interrupted ocean export"):
        execute_simulation(conf)
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["state"] == "failed"
    complete = conf.output_dir / "products/coupled-ocean.cart.nemo_t.deptht.nc"
    assert complete.exists()
    with xr.open_dataset(complete) as out:
        assert out.sizes["time"] == 2
    assert not list(conf.output_dir.rglob("*.tmp"))
    assert not (conf.output_dir / "products/coupled-ocean.cart.nemo_u.depthu.nc").exists()
    before = complete.read_bytes()
    monkeypatch.setattr(netcdf_export, "write_dataset_netcdf", original)
    with pytest.raises(FileExistsError):
        execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert complete.read_bytes() == before


def test_nemo_products_zarr_roundtrip(tmp_path):
    pytest.importorskip("zarr")
    raw = coupled_document(tmp_path, moving=True)
    raw["output"].update(backend="zarr",
        zarr_chunk_size={"time": 1, "deptht": 1, "depthu": 1, "depthv": 1, "depthw": 1, "x_box": 2, "y_box": 2},
        zarr_shard_size={"time": 2, "deptht": 2, "depthu": 2, "depthv": 2, "depthw": 2, "x_box": 4, "y_box": 4})
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    products = {p["source"]: p["path"] for p in result.products if p["role"] == "cart"}
    subprocess.run([sys.executable, "-c", """
import json,sys,xarray as xr,numpy as np,zarr
from pathlib import Path
paths=json.loads(sys.argv[1]); root=Path(sys.argv[2])
for source,field,depth in [('nemo_t','votemper','deptht'),('nemo_u','vozocrtx','depthu'),('nemo_v','vomecrty','depthv'),('nemo_w','vovecrtz','depthw')]:
    with xr.open_zarr(paths[source],consolidated=False) as out,xr.open_dataset(root/f'{source}.nc') as src:
        for t in (0,1):
            expected=src[field].isel(time_counter=t,y=out.y[t].values.astype(int),x=out.x[t].values.astype(int))
            np.testing.assert_array_equal(out[field][t],expected)
        np.testing.assert_array_equal(out.time,src.time_counter)
        np.testing.assert_array_equal(out[depth],src[depth])
        np.testing.assert_array_equal(out[f'{depth}_source_native_index'],[0,1])
        for bounds in [f'{depth}_bounds','time_counter_bounds','time_centered_bounds']:
            np.testing.assert_array_equal(out[bounds],src[bounds])
        for attr in ['units','standard_name','long_name','cell_methods']:
            assert out[field].attrs.get(attr)==src[field].attrs.get(attr)
        assert out.attrs['source_id']==source
        assert 'horizontal_wind_representation' not in out.attrs
        array=zarr.open_group(paths[source],mode='r')[field]
        assert array.chunks==(1,1,2,2) and array.shards==(2,2,4,4)
with xr.open_zarr(paths['arome'],consolidated=False) as a:
    assert a.forecast_reference_time.values==np.datetime64('2024-12-11')
assert 'frameit' not in sys.modules
""", json.dumps(products), str(tmp_path)], check=True)


def preceding_inventory():
    target = [f"2024-12-11T0{h}:00:00.000000000" for h in (0, 1, 2)]
    source = ["2024-12-11T00:30:00.000000000", "2024-12-11T01:30:00.000000000"]
    return {"atmosphere": [{"path": "atmosphere.nc", "times": target, "reference_times": [target[0]],
                            "temporal_fields": {"pressure": {"GRIB_stepType": "instant"}}}],
            "ocean": [{"path": "ocean.nc", "times": source, "reference_times": [],
                        "temporal_fields": {"temperature": {"cell_methods": "time: mean (interval: 240 s)",
                                                              "online_operation": "average"}},
                        "time_cells": [{"source_time": source[i], "start": target[i], "end": target[i+1]}
                                       for i in (0, 1)]}]}


def preceding_document(directory, *, moving=False, scalar_polar=False):
    raw = coupled_document(directory, scalar_polar=scalar_polar)
    raw["input"]["time_alignment"] = "preceding_hour"
    times = np.array(["2024-12-11T00", "2024-12-11T01", "2024-12-11T02"], dtype="datetime64[ns]")
    for name in ("prmsl", "u10", "v10"):
        path = directory / f"{name}.nc"
        with xr.open_dataset(path) as source:
            ds = source.isel(valid_time=[0, 0, 1]).load().assign_coords(valid_time=times)
        ds[name].attrs["GRIB_stepType"] = "instant"
        ds.to_netcdf(path)
    if moving:
        track = directory / "track.nc"
        xr.Dataset({"latitude": ("time", [-20., -20., -19.99]),
                    "longitude": ("time", [60., 60., 60. + .01/np.cos(np.deg2rad(20.))])},
                   coords={"time": times}).to_netcdf(track)
        raw["tracking"] = {"source": "arome", "method": "prescribed_track",
                           "prescribed_track": {"file": str(track)}}
    return raw


@pytest.mark.parametrize("moving,synchronous,engine", [
    (False, True, "h5netcdf"), (True, True, "h5netcdf"),
    (False, False, "h5netcdf"), (True, False, "h5netcdf"), (True, True, "zarr")])
def test_preceding_hour_coupled_native_copies_and_replay(tmp_path, moving, synchronous, engine):
    if engine == "zarr":
        pytest.importorskip("zarr")
    raw = preceding_document(tmp_path, moving=moving)
    raw["output"].update(synchronous_export=synchronous, backend=engine)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf)
    assert result.ok, result
    assert any("WARNING | preceding_hour omits" in path.read_text()
               for path in (conf.output_dir / "logs").glob("*.log"))
    alignment = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())["time_alignment"]
    assert alignment["omitted_pairings"] == [{"coupling_time": "2024-12-11T00:00:00.000000000",
                                            "missing_sources": ["nemo_t", "nemo_u", "nemo_v", "nemo_w"]}]
    products = {p["source"]: p["path"] for p in result.products if p["role"] == "cart"}
    subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
from pathlib import Path
products = json.loads(sys.argv[1]); root = Path(sys.argv[2]); engine = sys.argv[3]
target = np.array(['2024-12-11T01','2024-12-11T02'],dtype='datetime64[ns]')
native = np.array(['2024-12-11T00:30','2024-12-11T01:30'],dtype='datetime64[ns]')
for name,path in products.items():
    with (xr.open_zarr(path,consolidated=False) if engine == 'zarr' else xr.open_dataset(path)) as out:
        np.testing.assert_array_equal(out.time,target)
        if name == 'arome':
            assert out.forecast_reference_time.values == np.datetime64('2024-12-11')
            continue
        np.testing.assert_array_equal(out.source_time,native)
        np.testing.assert_array_equal(out.time_centered,native)
        assert 'coupling' in out.time.attrs['long_name']
        assert out.source_time.attrs['bounds'] == out.time.attrs['bounds']
        field = {'nemo_t':'votemper','nemo_u':'vozocrtx','nemo_v':'vomecrty','nemo_w':'vovecrtz'}[name]
        with xr.open_dataset(root/f'{name}.nc') as src:
            for t in (0,1):
                expected = src[field].isel(time_counter=t,y=out.y[t].values.astype(int),x=out.x[t].values.astype(int))
                np.testing.assert_array_equal(out[field][t],expected)
            for bound in ['time_counter_bounds','time_centered_bounds']:
                np.testing.assert_array_equal(out[bound],src[bound])
            assert out[field].attrs['cell_methods'] == src[field].attrs['cell_methods']
        assert 'no temporal interpolation' in out.attrs['temporal_association_description']
assert 'frameit' not in sys.modules
""", json.dumps(products), str(tmp_path), engine], check=True)
    replay = SimulationConfig.from_yaml_with_model_preset(conf.output_dir / "resolved-config.yaml")
    assert replay.time_alignment == "preceding_hour"
    replay_plan, _, _ = prepare_sources(replay, check_output=False)
    assert replay_plan["time_alignment"] == alignment


@pytest.mark.parametrize("problem", ["mean", "instant", "bounds", "format"])
def test_preceding_hour_inventory_validates_raw_selected_field_metadata(tmp_path, problem):
    raw = preceding_document(tmp_path)
    if problem == "format":
        raw["input"]["sources"]["arome"]["input"]["format"] = "grib"
    else:
        path = tmp_path / ("u10.nc" if problem == "instant" else "nemo_t.nc")
        with xr.open_dataset(path) as source:
            ds = source.load()
        if problem == "instant":
            ds.u10.attrs.pop("GRIB_stepType")
        elif problem == "mean":
            ds.votemper.attrs["cell_methods"] = "time: point"
        else:
            ds = ds.drop_vars(["time_counter_bounds", "time_centered_bounds"])
        ds.to_netcdf(path)
    with pytest.raises(ValueError, match="instant|mean|bounds|NetCDF|input.format"):
        prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("shared", [False, True])
def test_preceding_hour_polar_budget_counts_selected_pairs(tmp_path, shared):
    raw = preceding_document(tmp_path, scalar_polar=True)
    raw["polar"].update(shared_target=shared, max_points=48, radial_step_m=1200.)
    plan, _, _ = prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert plan["track_time_count"] == 2
    for name in ("arome", "nemo_t"):
        assert plan["sources"][name]["polar_sampling"]["estimated_time_count"] == 2
    raw["polar"]["max_points"] = 47
    with pytest.raises(ValueError, match="polar.max_points"):
        prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not (tmp_path / "out").exists()


def test_preceding_hour_scalar_polar_keeps_native_clock_and_bounds(tmp_path):
    pytest.importorskip("xesmf")
    raw = preceding_document(tmp_path, moving=True, scalar_polar=True)
    path = tmp_path / "nemo_t.nc"
    with xr.open_dataset(path) as source:
        ds = source.load()
    for name in ("time_counter", "time_centered", "time_counter_bounds", "time_centered_bounds"):
        ds[name].encoding.update(calendar="gregorian", units="seconds since 1800-01-01")
    ds.to_netcdf(path)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    products = {p["source"]: p["path"] for p in result.products if p["role"] == "polar"}
    with xr.open_dataset(products["arome"]) as a, xr.open_dataset(products["nemo_t"]) as n:
        for name in ("time", "rr", "theta", "center_lon", "center_lat"):
            np.testing.assert_array_equal(a[name], n[name])
        np.testing.assert_array_equal(n.source_time, np.array([
            "2024-12-11T00:30", "2024-12-11T01:30"], dtype="datetime64[ns]"))
        np.testing.assert_array_equal(n.time_centered, n.source_time)
        assert n.source_time.attrs["bounds"] in n
        assert n.time.attrs["bounds"] in n
        assert n.votemper.attrs["cell_methods"] == "time: mean (interval: 240 s)"
        assert n.source_time.encoding["calendar"] == "gregorian"
        assert n.time_centered.encoding["calendar"] == "gregorian"
        assert n.time.encoding["calendar"] == "gregorian"
        assert np.isnan(n.votemper.isel(time=0, rr=0)).all()


def test_preceding_hour_file_selection_uses_native_not_reference_times(tmp_path):
    raw = preceding_document(tmp_path)
    paths = []
    with xr.open_dataset(tmp_path / "nemo_t.nc") as source:
        for index in (0, 1):
            path = tmp_path / f"part-{index}.nc"
            source.isel(time_counter=[index]).to_netcdf(path)
            paths.append(str(path))
    raw["input"]["sources"]["nemo_t"]["input"]["files"] = paths
    plan, children, _ = prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert children["nemo_t"].input_files == paths
    assert len(plan["time_alignment"]["selected_times"]) == 2


def test_preceding_hour_polar_fractional_packed_depths_are_not_rounded(tmp_path):
    pytest.importorskip("xesmf")
    raw = preceding_document(tmp_path, scalar_polar=True)
    path = tmp_path / "nemo_t.nc"
    with xr.open_dataset(path) as source:
        ds = source.load()
    attrs = dict(ds.deptht.attrs)
    ds = ds.assign_coords(deptht=("deptht", [1.25, 3.75], attrs))
    ds.deptht.encoding.update(dtype="int16", scale_factor=.25, _FillValue=-32768)
    ds.to_netcdf(path)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    product = next(p["path"] for p in result.products if p["role"] == "polar" and p["source"] == "nemo_t")
    subprocess.run([sys.executable, "-c", """
import sys, xarray as xr, numpy as np
with xr.open_dataset(sys.argv[1]) as out:
    np.testing.assert_array_equal(out.deptht,[1.25,3.75])
assert 'frameit' not in sys.modules
""", product], check=True)


@pytest.mark.parametrize("across_files", [False, True])
def test_preceding_hour_duplicate_physical_records_fail_instead_of_deduplicating(tmp_path, across_files):
    raw = preceding_document(tmp_path)
    path = tmp_path / "nemo_t.nc"
    with xr.open_dataset(path) as source:
        ds = source.load()
    if across_files:
        other = tmp_path / "duplicate.nc"
        ds["votemper"] = ds.votemper + 100.
        ds.votemper.attrs["cell_methods"] = "time: mean (interval: 240 s)"
        ds.votemper.attrs["units"] = "degC"
        ds.to_netcdf(other)
        raw["input"]["sources"]["nemo_t"]["input"]["files"].append(str(other))
    else:
        duplicate = ds.isel(time_counter=[0, 0, 1])
        duplicate.votemper.values[1] += 100.
        duplicate.to_netcdf(path)
    with pytest.raises(ValueError, match="[Dd]uplicate|[Oo]verlapping"):
        prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not (tmp_path / "out").exists()


def test_preceding_hour_complementary_providers_can_repeat_clock_metadata(tmp_path):
    raw = preceding_document(tmp_path)
    path = tmp_path / "nemo_t.nc"
    with xr.open_dataset(path) as source:
        extra = source.load().rename({"votemper": "other_temperature"})
    other = tmp_path / "complement.nc"
    extra.to_netcdf(other)
    spec = raw["input"]["sources"]["nemo_t"]
    spec["input"]["files"].append(str(other))
    spec["input"]["netcdf"] = {"file_layout": "variables"}
    spec["variables"]["deptht"]["names"].append("other_temperature")
    plan, _, _ = prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert len(plan["time_alignment"]["selected_times"]) == 2


def test_preceding_hour_selects_bounds_not_nearest_and_warns(caplog):
    from frameit.core.time_association import align_preceding_hour

    inventory = preceding_inventory()
    result = align_preceding_hour(inventory, "atmosphere", {"atmosphere": "AROME", "ocean": "NEMO"})
    target = inventory["atmosphere"][0]["times"]
    assert result["selected_times"] == target[1:]
    assert result["omitted_pairings"] == [{"coupling_time": target[0], "missing_sources": ["ocean"]}]
    assert "omit" in caplog.text.lower() and target[0] in caplog.text
    mappings = result["sources"]["ocean"]["associations"]
    assert [m["source_time"] for m in mappings] == inventory["ocean"][0]["times"]
    assert [m["interval_end"] for m in mappings] == target[1:]
    assert [m["interval_start"] for m in mappings] == target[:2]
    assert [m["offset_seconds"] for m in mappings] == [-1800., -1800.]


@pytest.mark.parametrize("problem", ["no_bounds", "duration", "outside", "ambiguous", "mean", "instant", "profile", "collision"])
def test_preceding_hour_rejects_unresolved_inputs(problem):
    from frameit.core.time_association import align_preceding_hour

    inventory = preceding_inventory()
    ocean = inventory["ocean"][0]
    models = {"atmosphere": "AROME", "ocean": "NEMO"}
    if problem == "no_bounds":
        ocean.pop("time_cells")
    elif problem == "duration":
        ocean["time_cells"][0]["start"] = "2024-12-11T00:15:00.000000000"
    elif problem == "outside":
        ocean["time_cells"][0]["source_time"] = "2024-12-10T23:30:00.000000000"
    elif problem == "ambiguous":
        other = dict(ocean["time_cells"][0], source_time="2024-12-11T00:45:00.000000000")
        ocean["time_cells"].append(other)
        ocean["times"].append(other["source_time"])
    elif problem == "mean":
        ocean["temporal_fields"]["temperature"]["cell_methods"] = "time: point"
    elif problem == "instant":
        inventory["atmosphere"][0]["temporal_fields"]["pressure"]["GRIB_stepType"] = "avg"
    elif problem == "profile":
        models["atmosphere"] = "NEMO"
    else:
        ocean["source_time_conflict"] = True
    with pytest.raises(ValueError, match="bounds|hour|interval|mean|instant|AROME|source_time"):
        align_preceding_hour(inventory, "atmosphere", models)


def test_preceding_hour_exact_participants_track_subset_and_empty_failure():
    from frameit.core.time_association import align_preceding_hour

    inventory = preceding_inventory()
    target = inventory["atmosphere"][0]["times"]
    inventory["other"] = [dict(inventory["atmosphere"][0], path="other.nc", times=target[::2])]
    models = {"atmosphere": "AROME", "ocean": "NEMO", "other": "AROME"}
    result = align_preceding_hour(inventory, "atmosphere", models, track_times=set(target[1:]))
    assert result["selected_times"] == [target[2]]
    assert result["track_excluded_times"] == [target[0]]
    assert result["omitted_pairings"] == [{"coupling_time": target[1], "missing_sources": ["other"]}]
    with pytest.raises(ValueError, match="No.*preceding.hour.*pair"):
        align_preceding_hour(inventory, "atmosphere", models, track_times={target[0]})


def test_preceding_hour_relabels_coordinates_without_recomputing_values():
    from frameit.core.time_association import align_preceding_hour, associate_preceding_times

    inventory = preceding_inventory()
    mappings = align_preceding_hour(inventory, "atmosphere", {
        "atmosphere": "AROME", "ocean": "NEMO"})["sources"]["ocean"]["associations"]
    native = np.array(inventory["ocean"][0]["times"], dtype="datetime64[ns]")
    ds = xr.Dataset({"temperature": ("time", [10., 20.], {"cell_methods": "time: mean", "units": "degC"}),
                     "missing": ("time", [0., np.nan])},
                    coords={"time": ("time", native, {"bounds": "time_bounds", "axis": "T"}),
                            "time_centered": ("time", native),
                            "time_bounds": (("time", "nv"), np.array([
                                [m["interval_start"], m["interval_end"]] for m in mappings], dtype="datetime64[ns]"))}).chunk({"time": 1})
    ds.time.encoding.update(units="seconds since 1800-01-01", calendar="gregorian")
    result = associate_preceding_times({"deptht": ds}, mappings)["deptht"]
    assert hasattr(result.temperature.data, "dask")
    np.testing.assert_array_equal(result.temperature, [10., 20.])
    np.testing.assert_array_equal(result.missing, [0., np.nan])
    np.testing.assert_array_equal(result.time, np.array([m["coupling_time"] for m in mappings], dtype="datetime64[ns]"))
    np.testing.assert_array_equal(result.source_time, native)
    np.testing.assert_array_equal(result.time_centered, native)
    np.testing.assert_array_equal(result.time_bounds, ds.time_bounds)
    assert result.time.attrs["bounds"] == result.source_time.attrs["bounds"] == "time_bounds"
    assert "coupling" in result.time.attrs["long_name"]
    assert "axis" not in result.source_time.attrs
    assert result.source_time.encoding["calendar"] == "gregorian"
    assert result.temperature.attrs["cell_methods"] == "time: mean"
    assert "source_time" not in ds
    with pytest.raises(ValueError, match="source_time"):
        associate_preceding_times(ds.assign_coords(source_time=("time", native)), mappings)
