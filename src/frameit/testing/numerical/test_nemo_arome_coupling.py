"""Exact synthetic atmosphere/ocean coupling does not authorise real time pairing."""

import json
from pathlib import Path
import shutil
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
        "netcdf": {"file_layout": "variables"}, "wind_reference_frame": "earth"},
        "variables": {"surface": {"names": ["prmsl", "u10", "v10"]}}}
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
                           "variables": {depth: {"names": [field], "levels": "all"}}}
    raw = {"schema_version": 2, "model": "arome", "run": {"name": "coupled-ocean"},
           "input": {"sources": sources}, "domain": {"size_km": {"x": 2., "y": 2.}},
           "tracking": {"source": "arome", "method": "fixed_box", "fixed_box": {
               "center": {"latitude": -20., "longitude": 60.}}},
           "execution": {"native_threads": 1, "dask_workers": 1},
           "output": {"directory": str(directory / "out"), "overwrite": False,
                      "synchronous_export": True, "max_workers": 1,
                      "cartesian": {"horizontal_winds": "native"}}}
    if moving:
        track = directory / "track.nc"
        xr.Dataset({"latitude": ("time", [-20., -19.99]),
                    "longitude": ("time", [60., 60. + .01/np.cos(np.deg2rad(20.))])},
                   coords={"time": times}).to_netcdf(track)
        raw["tracking"] = {"source": "arome", "method": "prescribed_track", "prescribed_track": {"file": str(track)}}
    if scalar_polar:
        raw["domain"]["size_km"] = {"x": 4., "y": 4.}
        raw["polar"] = {"enabled": True, "shared_target": True, "azimuth_count": 8}
        for source in sources:
            sources[source]["polar"] = {"enabled": source in {"arome", "nemo_t"}}
        sources["arome"]["polar"]["variables"] = {"surface": {"names": ["prmsl"]}}
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


def test_portable_nemo_arome_example_with_exact_synthetic_inputs(tmp_path):
    example = Path(__file__).resolve().parents[4] / "example/config_file/nemo_arome.yaml"
    if not example.exists():
        pytest.skip("Repository example is not installed with the package")
    data = tmp_path / "data"
    data.mkdir()
    coupled_document(data)
    config = tmp_path / "nemo_arome.yaml"
    shutil.copyfile(example, config)
    conf = SimulationConfig.from_yaml_with_model_preset(config)
    result = execute_simulation(conf)
    assert result.ok, result
    assert len([p for p in result.products if p["role"] == "cart"]) == 5
    replay = SimulationConfig.from_yaml_with_model_preset(conf.output_dir / "resolved-config.yaml")
    assert replay.time_alignment == "common"
    assert replay.input_sources["nemo_u"]["input"]["files"] == [str(data / "nemo_u.nc")]


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
