"""Coupled sources retain their own grids and report every exact-time skip."""

from __future__ import annotations

import copy
import json
import logging
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.configuration import resolve_schema, resolved_configuration
from frameit.core.coupled import align_source_times
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_fa_io import NATIVE, fa_files


def atmospheric_file(directory):
    x, y = np.arange(-3, 4) * 2000., np.arange(-2, 3) * 2000.
    lon, lat = np.meshgrid(60 + np.rad2deg(x / (6371229 * np.cos(np.deg2rad(20)))),
                          -20 + np.rad2deg(y / 6371229))
    time = np.array(["2026-01-01", "2026-01-01T01:00"], dtype="datetime64[ns]")
    j, i = np.indices((5, 7))
    values = 273. + 2 * j[None, ...] + i[None, ...] + np.arange(2)[:, None, None]
    ds = xr.Dataset({"temperature": (("time", "nj", "ni"), values, {"units": "K"})},
                    coords={"time": time, "ni": ("ni", x, {"units": "m"}),
                            "nj": ("nj", y, {"units": "m"}),
                            "longitude": (("nj", "ni"), lon, {"units": "degrees_east"}),
                            "latitude": (("nj", "ni"), lat, {"units": "degrees_north"})})
    path = directory / "atmosphere.nc"
    ds.to_netcdf(path, engine="netcdf4")
    return path


def document(directory, atmosphere, surface_files, *, synchronous=True):
    return {
        "schema_version": 2, "model": "mesonh", "run": {"name": "coupled"},
        "input": {"sources": {
            "atmosphere": {"model": "mesonh", "input": {"files": [str(atmosphere)],
                            "format": "netcdf", "netcdf": {"engine": "netcdf4"}},
                           "variables": {"surface": {"names": ["temperature"]}}},
            "surfex": {"model": "arome", "input": {
                "files": [str(path) for path in surface_files], "format": "fa",
                "fa": {"profile": "surfex_history", "field_metadata": {
                    "SFX.T2M": {"units": "K", "kind": "continuous",
                                "temporal_kind": "instantaneous", "allow_unscaled": True}}}},
                "variables": {"surface": {"names": ["SFX.T2M"]}}},
        }},
        "tracking": {"source": "atmosphere", "method": "fixed_box", "fixed_box": {
            "center": {"latitude": -20., "longitude": 60.}}},
        "domain": {"size_km": {"x": 4., "y": 4.}},
        "output": {"directory": str(directory / "run"), "synchronous_export": synchronous,
                   "max_workers": 1},
    }


def single_fa_document(directory, files):
    coupled = document(directory, directory / "unused.nc", files)
    source = coupled["input"]["sources"]["surfex"]
    return {"schema_version": 2, "model": "arome", "input": source["input"],
            "variables": source["variables"], "domain": coupled["domain"],
            "tracking": {"method": "fixed_box", "fixed_box": {
                "center": {"latitude": -20., "longitude": 60.}}},
            "output": coupled["output"]}


def test_common_and_strict_policy_complete_skip_report(caplog):
    inventories = {"atm": [{"path": "atm", "times": ["a", "b"]}],
                   "sfx": [{"path": "sfx-1", "times": ["b"]},
                           {"path": "sfx-2", "times": ["c"]}]}
    with caplog.at_level(logging.WARNING):
        report = align_source_times(inventories)
    assert report["selected_times"] == ["b"]
    assert report["sources"]["atm"]["skipped_times"] == ["a"]
    assert report["sources"]["sfx"]["skipped_times"] == ["c"]
    assert report["sources"]["sfx"]["skipped_files"] == ["sfx-2"]
    assert "Source atm" in caplog.text and "Source sfx" in caplog.text
    with pytest.raises(ValueError, match="Strict source time alignment"):
        align_source_times(inventories, "strict")
    with pytest.raises(ValueError, match="no exact common"):
        align_source_times(inventories, track_times={"unmatched"})


def test_coupled_schema_defaults_paths_and_bad_options(tmp_path):
    raw = document(tmp_path, tmp_path / "atmosphere.nc", [tmp_path / "surface.fa"])
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    assert conf.time_alignment == "common" and conf.tracking_source == "atmosphere"
    assert conf.file_type == "coupled"
    SimulationConfig.from_mapping_with_model_preset(resolved_configuration(conf))
    for section, key, value in (("input", "time_alignment", "nearest"),
                                ("tracking", "source", "missing")):
        bad = copy.deepcopy(raw)
        bad[section][key] = value
        with pytest.raises(ValueError):
            resolve_schema(bad)
    bad = copy.deepcopy(raw)
    bad["input"]["pattern"] = "*.nc"
    with pytest.raises(ValueError, match="inside each source.input"):
        resolve_schema(bad)
    bad = copy.deepcopy(raw)
    bad["variables"] = {"surface": {"names": ["ambiguous"]}}
    with pytest.raises(ValueError, match="belong to each source"):
        resolve_schema(bad)
    bad = copy.deepcopy(raw)
    definition = bad["input"]["sources"]["surfex"]["input"]["fa"]["field_metadata"]["SFX.T2M"]
    definition["temporal_kind"] = "accumulated"
    with pytest.raises(ValueError, match="no accumulation interval is inferred"):
        resolve_schema(bad)


def test_coupled_netcdf_sources_do_not_need_fa_backend(tmp_path, monkeypatch):
    atmosphere = atmospheric_file(tmp_path)
    surface = tmp_path / "surface.nc"
    with xr.open_dataset(atmosphere, engine="netcdf4") as original:
        shifted = original.rename(temperature="surface_temp").load().assign_coords(
            time=original.time.values + np.timedelta64(1, "h"))
        shifted.to_netcdf(surface, engine="netcdf4")
    raw = document(tmp_path, atmosphere, [])
    raw["input"]["sources"]["surfex"] = {
        "model": "mesonh", "input": {"files": [str(surface)], "format": "netcdf"},
        "variables": {"surface": {"names": ["surface_temp"]}}}

    def forbidden(*args, **kwargs):
        raise AssertionError("NetCDF coupling must not initialize native FA")

    monkeypatch.setattr("frameit.io.fa_backend.request_fa", forbidden)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    preview = preflight(conf, execution_options=ExecutionOptions.from_config(
        conf, export_netcdf=False))
    assert preview["planned_products"] == []
    result = execute_simulation(conf)
    assert result.ok and len(result.products) == 3


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_fa_only_multi_time_prescribed_track_is_exact_and_lazy(tmp_path, monkeypatch):
    files = fa_files(tmp_path, (2, 0, 1), profile="surfex_history")
    raw = single_fa_document(tmp_path, files)
    track = tmp_path / "track.nc"
    xr.Dataset({"latitude": ("time", [-20.]), "longitude": ("time", [60.])}, coords={
        "time": [np.datetime64("2026-01-01T01:00", "ns")]}).to_netcdf(track, engine="netcdf4")
    raw["tracking"] = {"method": "prescribed_track", "prescribed_track": {"file": str(track)}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    from frameit.io import fa_utils

    original = fa_utils.request_fa
    read_keys = []

    def counted(request):
        read_keys.append((request["path"], request["key"]))
        return original(request)

    monkeypatch.setattr(fa_utils, "request_fa", counted)
    preflight(conf)
    assert not read_keys
    result = execute_simulation(conf)
    assert result.ok and read_keys
    assert all("001.fa" in path for path, _ in read_keys)  # No unused time decoded.
    product = next(p["path"] for p in result.products if p["role"] == "cart")
    with xr.open_dataset(product, engine="netcdf4") as data:
        assert data.time.size == 1
        assert data["SFX.T2M"].shape == (1, 5, 5)
        assert data["SFX.T2M"].attrs["surfex_support_mask"] == "FULL"


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_grib_and_fa_share_one_run_without_native_runtime_collision(tmp_path):
    ec = pytest.importorskip("eccodes")
    path = tmp_path / "atmosphere.grib"
    handle = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        settings = {"Ni": 7, "Nj": 5, "jScansPositively": 1,
                    "latitudeOfFirstGridPointInDegrees": -20.04,
                    "latitudeOfLastGridPointInDegrees": -19.96,
                    "longitudeOfFirstGridPointInDegrees": 59.93616,
                    "longitudeOfLastGridPointInDegrees": 60.06384,
                    "iDirectionIncrementInDegrees": .02128,
                    "jDirectionIncrementInDegrees": .02,
                    "dataDate": 20260101, "dataTime": 0, "step": 1,
                    "paramId": 167, "bitsPerValue": 24}
        for key, value in settings.items():
            ec.codes_set(handle, key, value)
        j, i = np.indices((5, 7))
        ec.codes_set_values(handle, (274. + 2 * j + i).ravel())
        with path.open("wb") as stream:
            ec.codes_write(handle, stream)
            unknown = ec.codes_clone(handle)
            try:
                for key in ("parameterCategory", "parameterNumber", "typeOfFirstFixedSurface"):
                    ec.codes_set(unknown, key, 255)
                assert ec.codes_get(unknown, "shortName") == "unknown"
                ec.codes_write(unknown, stream)
            finally:
                ec.codes_release(unknown)
    finally:
        ec.codes_release(handle)
    files = fa_files(tmp_path, (1,), profile="surfex_history")
    raw = document(tmp_path, path, files)
    raw["model"] = "arome"
    raw["input"]["sources"]["atmosphere"] = {
        "model": "arome", "input": {"files": [str(path)], "format": "grib"},
        "variables": {"heightAboveGround": {"names": ["t2m"], "levels": {"values": [2]}}}}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok
    products = {p.get("source"): p["path"] for p in result.products if p["role"] == "cart"}
    with xr.open_dataset(products["atmosphere"], engine="netcdf4") as data:
        np.testing.assert_array_equal(data.t2m[0, 0],
                                      [[278., 279., 280.], [280., 281., 282.], [282., 283., 284.]])
    with xr.open_dataset(products["surfex"], engine="netcdf4") as data:
        assert data["SFX.T2M"].shape == (1, 5, 5)
    assert "falfilfa4py" not in sys.modules
    provenance = yaml.safe_load((tmp_path / "run" / "run-provenance.yaml").read_text())
    assert provenance["sources"]["atmosphere"]["unmapped_grib_records"]


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_coupled_common_polar_target_and_scalar_truth(tmp_path):
    pytest.importorskip("xesmf")
    atmosphere = atmospheric_file(tmp_path)
    files = fa_files(tmp_path, (1,), profile="surfex_history")
    raw = document(tmp_path, atmosphere, files)
    raw["polar"] = {"enabled": True, "radial_step_m": 2000., "azimuth_count": 8}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    products = {p.get("source"): p["path"] for p in result.products if p["role"] == "polar"}
    with xr.open_dataset(products["atmosphere"], engine="netcdf4") as a, xr.open_dataset(
        products["surfex"], engine="netcdf4"
    ) as s:
        np.testing.assert_array_equal(a.rr, s.rr)
        np.testing.assert_array_equal(a.theta, s.theta)
        np.testing.assert_allclose(a.longitude, s.longitude, rtol=0, atol=1.e-12)
        np.testing.assert_allclose(a.latitude, s.latitude, rtol=0, atol=1.e-12)
        np.testing.assert_allclose(a.temperature.isel(rr=0), 281., atol=1.e-8)
        np.testing.assert_allclose(s["SFX.T2M"].isel(rr=0), 314.5, atol=1.e-8)


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
@pytest.mark.parametrize("synchronous", [True, False])
def test_netcdf_fa_two_grids_time_intersection_independent_reopening(tmp_path, synchronous):
    atmosphere = atmospheric_file(tmp_path)
    surface = fa_files(tmp_path, (1, 2), profile="surfex_history")
    raw = document(tmp_path, atmosphere, surface, synchronous=synchronous)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan = preflight(conf)
    assert plan["track_time_count"] == 1
    assert not conf.output_dir.exists()
    result = execute_simulation(conf)
    assert result.ok and result.n_files == 2  # The non-common FA file was not processed.
    products = {p.get("source"): p["path"] for p in result.products if p["role"] == "cart"}
    assert set(products) == {"atmosphere", "surfex"}
    # Use a fresh ordinary-reader process with no FrameIt or FA imports.
    check = subprocess.run([sys.executable, "-c", """
import json, sys, xarray as xr, numpy as np
products = json.loads(sys.argv[1])
with xr.open_dataset(products['atmosphere'], engine='netcdf4') as a:
    assert a.temperature.shape == (1, 3, 3)
    expected = [[278.,279.,280.],[280.,281.,282.],[282.,283.,284.]]
    np.testing.assert_array_equal(a.temperature[0], expected)
with xr.open_dataset(products['surfex'], engine='netcdf4') as s:
    assert s['SFX.T2M'].shape == (1,5,5)
    np.testing.assert_array_equal(s['SFX.T2M'][0],280.5+10*np.arange(1,6)[:,None]+np.arange(2,7))
    assert s['SFX.T2M'].attrs['units'] == 'K'
    assert s.attrs['source_id'] == 'surfex'
    assert s['SFX.T2M'].attrs['source_variable_name'] == 'SFX.T2M'
assert 'frameit' not in sys.modules and 'falfilfa4py' not in sys.modules
""", json.dumps(products)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
    with xr.open_dataset(next(p["path"] for p in result.products if p["role"] == "track"),
                         engine="netcdf4") as track:
        np.testing.assert_array_equal(track.cx, [3])
        np.testing.assert_array_equal(track.atmosphere_cx, [3])
        np.testing.assert_array_equal(track.surfex_cx, [4])
        np.testing.assert_array_equal(track.surfex_cy, [3])
        assert track.attrs["time_alignment_skipped_count"] == 2
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["state"] == "completed"
    assert provenance["time_alignment"] == status["time_alignment"]
    assert provenance["time_alignment"]["sources"]["atmosphere"]["skipped_times"] == [
        "2026-01-01T00:00:00.000000000"]
    assert provenance["time_alignment"]["sources"]["surfex"]["skipped_times"] == [
        "2026-01-01T02:00:00.000000000"]
    assert provenance["sources"]["surfex"]["fa_decoder"]["decode_requests"] > 0
    versions = provenance["sources"]["surfex"]["fa_decoder"]["backend_versions"]
    assert versions["falfilfa4py"] == "1.3.0"
    SimulationConfig.from_yaml(conf.output_dir / "resolved-config.yaml")
    strict = copy.deepcopy(raw)
    strict["input"]["time_alignment"] = "strict"
    with pytest.raises(ValueError, match="Strict source time alignment"):
        preflight(SimulationConfig.from_mapping_with_model_preset(strict))
