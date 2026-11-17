"""Coupled sources retain their own grids and report every exact-time skip."""

from __future__ import annotations

import copy
import json
import logging
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.configuration import resolve_schema, resolved_configuration
from frameit.core.coupled import align_source_times, bind_sources
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.preflight import collect_preflight
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_fa_cubes import EPYTHON
from frameit.testing.numerical.test_fa_cubes import NATIVE as EPYGRAM
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
        "schema_version": 3, "run": {"name": "coupled"},
        "sources": {
            "atmosphere": {"model": "mesonh", "files": [str(atmosphere)],
                           "format": "netcdf", "reader": {"engine": "netcdf4"},
                           "field_metadata": {"temperature": {"kind": "continuous"}},
                           "variables": {"2d": ["temperature"]}},
            "surface": {"model": "arome",
                "files": [str(path) for path in surface_files], "format": "fa",
                "profile": "surfex_history", "field_metadata": {
                    "SFX.T2M": {"units": "K", "kind": "continuous",
                                 "temporal_kind": "instantaneous", "allow_unscaled": True}},
                "variables": {"2d": ["SFX.T2M"]}},
        },
        "region": {"center": {"latitude": -20., "longitude": 60.},
                   "width_km": {"x": 4., "y": 4.},
                   "sources_coupling_time_association": "common"},
        "products": {"model_grid": True, "track": True},
        "resources": {"synchronous_export": synchronous, "export_workers": 1},
        "output": {"directory": str(directory / "run")},
    }


def single_fa_document(directory, files):
    coupled = document(directory, directory / "unused.nc", files)
    return {"schema_version": 3, "sources": {"surface": coupled["sources"]["surface"]},
            "region": coupled["region"], "products": coupled["products"],
            "resources": coupled["resources"], "output": coupled["output"]}


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
    assert conf.time_alignment == "common" and conf.tracking_source is None
    assert set(conf.sources) == {"atmosphere", "surface"}
    SimulationConfig.from_mapping_with_model_preset(resolved_configuration(conf))
    for section, key, value in (("region", "sources_coupling_time_association", "nearest"),
                                ("region", "source", "missing")):
        bad = copy.deepcopy(raw)
        bad[section][key] = value
        with pytest.raises(ValueError):
            resolve_schema(bad)
    bad = copy.deepcopy(raw)
    bad["pattern"] = "*.nc"
    with pytest.raises(ValueError, match="Unknown key configuration.pattern"):
        resolve_schema(bad)
    bad = copy.deepcopy(raw)
    bad["variables"] = {"2d": ["ambiguous"]}
    with pytest.raises(ValueError, match="Unknown key configuration.variables"):
        resolve_schema(bad)
    bad = copy.deepcopy(raw)
    definition = bad["sources"]["surface"]["field_metadata"]["SFX.T2M"]
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
    raw["sources"]["surface"] = {
        "model": "mesonh", "files": [str(surface)], "format": "netcdf",
        "variables": {"2d": ["surface_temp"]}}

    def forbidden(*args, **kwargs):
        raise AssertionError("NetCDF coupling must not initialize native FA")

    monkeypatch.setattr("frameit.io.fa_backend.request_fa", forbidden)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    checked = collect_preflight(conf, execution_options=ExecutionOptions.from_config(
        conf, export_netcdf=False))
    assert not checked.errors, checked.errors
    preview = checked.facts
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
    raw["region"].pop("center")
    raw["region"]["track"] = {"file": str(track)}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    from frameit.io import fa_utils

    original = fa_utils.request_fa
    read_keys = []

    def counted(request):
        read_keys.append((request["path"], request["key"]))
        return original(request)

    monkeypatch.setattr(fa_utils, "request_fa", counted)
    checked = collect_preflight(conf)
    assert not checked.errors, checked.errors
    assert not read_keys
    result = execute_simulation(conf)
    assert result.ok and read_keys
    assert all("001.fa" in path for path, _ in read_keys)  # No unused time decoded.
    product = next(p["path"] for p in result.products if p["role"] == "model_grid")
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
    raw["sources"]["atmosphere"] = {
        "model": "arome", "files": [str(path)], "format": "grib",
        "variables": {"3d": ["t2m"], "levels": {"values": [2]}}}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok
    products = {p.get("source"): p["path"] for p in result.products if p["role"] == "model_grid"}
    with xr.open_dataset(products["atmosphere"], engine="netcdf4") as data:
        np.testing.assert_array_equal(data.t2m[0, 0],
                                      [[278., 279., 280.], [280., 281., 282.], [282., 283., 284.]])
    with xr.open_dataset(products["surface"], engine="netcdf4") as data:
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
    raw["products"]["polar"] = {
        "radius_km": 2., "radial_step_km": 2., "azimuth_count": 8, "shared_grid": True}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    products = {p.get("source"): p["path"] for p in result.products if p["role"] == "polar"}
    with xr.open_dataset(products["atmosphere"], engine="netcdf4") as a, xr.open_dataset(
        products["surface"], engine="netcdf4"
    ) as s:
        np.testing.assert_array_equal(a.radius, s.radius)
        np.testing.assert_array_equal(a.azimuth, s.azimuth)
        np.testing.assert_allclose(a.longitude, s.longitude, rtol=0, atol=1.e-12)
        np.testing.assert_allclose(a.latitude, s.latitude, rtol=0, atol=1.e-12)
        np.testing.assert_allclose(a.temperature.isel(radius=0), 281., atol=1.e-8)
        np.testing.assert_allclose(s["SFX.T2M"].isel(radius=0), 314.5, atol=1.e-8)


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
@pytest.mark.parametrize("synchronous", [True, False])
def test_netcdf_fa_two_grids_time_intersection_independent_reopening(tmp_path, synchronous):
    atmosphere = atmospheric_file(tmp_path)
    surface = fa_files(tmp_path, (1, 2), profile="surfex_history")
    raw = document(tmp_path, atmosphere, surface, synchronous=synchronous)
    raw["sources"]["surface"]["fa"] = {"expected_source": {
        "PROGRAM": "AROME", "MASDEV": 47, "VERSION": 8, "BUG": 1, "BUGFIX": 0}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    checked = collect_preflight(conf)
    assert not checked.errors, checked.errors
    assert len(conf.simulation_parameter["region_alignment"]["selected_times"]) == 1
    assert not conf.output_dir.exists()
    result = execute_simulation(conf)
    assert result.ok
    products = {p.get("source"): p["path"] for p in result.products if p["role"] == "model_grid"}
    assert set(products) == {"atmosphere", "surface"}
    # Use a fresh ordinary-reader process with no FrameIt or FA imports.
    check = subprocess.run([sys.executable, "-c", """
import json, sys, xarray as xr, numpy as np
products = json.loads(sys.argv[1])
with xr.open_dataset(products['atmosphere'], engine='netcdf4') as a:
    assert a.temperature.shape == (1, 3, 3)
    expected = [[278.,279.,280.],[280.,281.,282.],[282.,283.,284.]]
    np.testing.assert_array_equal(a.temperature[0], expected)
    np.testing.assert_array_equal(a.ni_source_native_index[:, a.sizes['x']//2], [3])
with xr.open_dataset(products['surface'], engine='netcdf4') as s:
    assert s['SFX.T2M'].shape == (1,5,5)
    np.testing.assert_array_equal(s['SFX.T2M'][0],280.5+10*np.arange(1,6)[:,None]+np.arange(2,7))
    assert s['SFX.T2M'].attrs['units'] == 'K'
    assert s.attrs['source_id'] == 'surface'
    assert s['SFX.T2M'].attrs['source_variable_name'] == 'SFX.T2M'
    descriptor = json.loads(s['SFX.T2M'].attrs['fa_field_descriptor'])
    assert descriptor['schema_version'] == 1
    assert descriptor['native']['shape'] == [7,9]
    assert descriptor['units'] == {'value':'K','origin':'explicit_source.field_metadata'}
    assert descriptor['mask']['undefined'] == 'not_read'  # decode facts are in the run manifest
assert 'frameit' not in sys.modules and 'falfilfa4py' not in sys.modules
""", json.dumps(products)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
    # Native centre indices now belong to each source's regional provenance.
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    atmosphere_grid, = provenance["sources"]["atmosphere"]["region"]["grids"].values()
    surface_grid, = provenance["sources"]["surface"]["region"]["grids"].values()
    np.testing.assert_array_equal(atmosphere_grid["native_x_indices"], [3])
    np.testing.assert_array_equal(surface_grid["native_x_indices"], [4])
    np.testing.assert_array_equal(surface_grid["native_y_indices"], [3])
    assert sum(len(s["skipped_times"])
               for s in provenance["time_alignment"]["sources"].values()) == 2
    assert status["state"] == "completed"
    assert provenance["time_alignment"] == status["time_alignment"]
    assert provenance["time_alignment"]["sources"]["atmosphere"]["skipped_times"] == [
        "2026-01-01T00:00:00.000000000"]
    assert provenance["time_alignment"]["sources"]["surface"]["skipped_times"] == [
        "2026-01-01T02:00:00.000000000"]
    assert provenance["sources"]["surface"]["fa_decoder"]["decode_requests"] > 0
    versions = provenance["sources"]["surface"]["fa_decoder"]["backend_versions"]
    # Provenance must identify the installed distribution actually used.
    assert versions["falfilfa4py"] == version("falfilfa4py")
    source = provenance["sources"]["surface"]
    assert source["fa_inputs"][0]["field_descriptors"]["SFX.T2M"]["schema_version"] == 1
    observed = next(iter(source["fa_decoder"]["field_observations"].values()))["SFX.T2M"]
    assert observed["mask"]["undefined"]["present"] is False
    # Packing-0 native fixtures do not exercise the missing GRIB-scaling warning.
    assert observed["scaling"]["status"] == "not_exposed"
    assert observed["scaling"]["fallback"] is None
    assert observed["units"]["origin"] == "explicit_source.field_metadata"
    restored = SimulationConfig.from_yaml(conf.output_dir / "resolved-config.yaml")
    assert resolved_configuration(restored)["sources"]["surface"]["fa"][
        "expected_source"]["MASDEV"] == 47
    assert result.ok and result.n_files == 2  # The non-common FA file was not processed.
    strict = copy.deepcopy(raw)
    strict["region"]["sources_coupling_time_association"] = "strict"
    with pytest.raises(ValueError, match="sources_coupling_time_association"):
        bind_sources(SimulationConfig.from_mapping_with_model_preset(strict))


def primary_pair_document(directory, *, synchronous=True, cycles=None, surface_overrides=None):
    """C3 engineering containers, not a producer preset or a same-reader oracle.

    GRIB uses AROME's public quantity/level conventions on a 13x15 angular grid;
    independently prescribed FA words store dense SURFEX on a 9x11 Lambert grid.
    Neither fixture is written by EPyGrAM. All source files are made read-only.
    """
    ec = pytest.importorskip("eccodes")
    atmosphere, surface, requests = [], [], []
    j, i = np.indices((13, 15))
    for hour in (2, 0, 1):  # Unordered inputs must not choose the track's time order.
        path = directory / f"atmosphere-{hour}.grib"
        atmosphere.append(str(path))
        cycle = (cycles or {}).get(hour, 0)
        with path.open("wb") as stream:
            fields = [(151, None, 100000. + 100*hour + 10*j + i),
                      (165, None, np.zeros_like(j)), (166, None, np.full_like(j, 4 + hour))]
            for level in (700, 850):
                for param, base in ((131, 3.), (132, 4.), (130, 260.), (157, 60.), (129, 50000.)):
                    values = base + level/100. + hour + 2*j + i
                    if param == 157:
                        values[4, 5] = np.nan
                    fields.append((param, level, values))
            for param, level, values in fields:
                sample = "regular_ll_sfc_grib2" if level is None else "regular_ll_pl_grib2"
                handle = ec.codes_grib_new_from_samples(sample)
                try:
                    settings = {
                        "centre": 85, "Ni": 15, "Nj": 13, "jScansPositively": 1,
                        "latitudeOfFirstGridPointInDegrees": -20.054,
                        "latitudeOfLastGridPointInDegrees": -19.946,
                        "longitudeOfFirstGridPointInDegrees": 49.932968,
                        "longitudeOfLastGridPointInDegrees": 50.067032,
                        "iDirectionIncrementInDegrees": .009576,
                        "jDirectionIncrementInDegrees": .009,
                        "shapeOfTheEarth": 6, "dataDate": 20260101,
                        "dataTime": cycle*100, "step": hour - cycle,
                        "paramId": param, "bitsPerValue": 24, "uvRelativeToGrid": 0,
                    }
                    if level is not None:
                        settings["level"] = level
                    for key, value in settings.items():
                        ec.codes_set(handle, key, value)
                    ec.codes_set(handle, "bitmapPresent", int(np.isnan(values).any()))
                    encoded = np.where(np.isfinite(values), values,
                                       ec.codes_get(handle, "missingValue"))
                    ec.codes_set_values(handle, encoded.ravel())
                    ec.codes_write(handle, stream)
                finally:
                    ec.codes_release(handle)
        path.chmod(0o444)
    for hour in (3, 2, 1):
        path = directory / f"surface-{hour}.fa"
        surface.append(str(path))
        temperature = np.full((9, 11), 280. + hour)
        temperature[3, 4] = 0.  # A valid stored zero, independent of SST's missing sample.
        sst = np.full((9, 11), 300. + hour)
        if hour == 1:
            sst[4, 5] = np.nan
        requests.append({
            "path": str(path), "hours": hour, "profile": "surfex_history",
            "nx": 11, "ny": 9, "projection_latitude": -20., "projected_spacing_m": 3000.,
            "surface_fields": [{"name": "SST", "mask": "SEA", "values": sst.tolist()},
                               {"name": "T2M", "mask": "FULL", "values": temperature.tolist()}],
            # Unselected typed/unsupported directory entries cannot trigger a payload read.
            "surface_directory": [{"name": "SST", "mask": "SEA"},
                                  {"name": "T2M", "mask": "FULL"},
                                  {"name": "L2D", "mask": "FULL", "type": "L0", "dim1": 1}],
            "extra_metadata": True, **(surface_overrides or {}).get(hour, {}),
        })
    written = subprocess.run([EPYTHON, "-m", "frameit.testing.fa_fixture"],
                             input=json.dumps(requests), capture_output=True, text=True, timeout=30)
    assert written.returncode == 0, written.stdout + written.stderr
    for path in surface:
        Path(path).chmod(0o444)
    track = directory / "continuous-track.nc"
    xr.Dataset({"longitude": ("time", [50., 50.015], {"units": "degrees_east"}),
                "latitude": ("time", [-20., -19.988], {"units": "degrees_north"})}, coords={
                    "time": np.array(["2026-01-01T01:00", "2026-01-01T02:00"],
                                     dtype="datetime64[ns]")}).to_netcdf(track)
    track.chmod(0o444)
    return {
        "schema_version": 3, "run": {"name": "primary-pair"},
        "sources": {
            "atmosphere": {"model": "arome",
                "files": atmosphere, "format": "grib", "wind_pairs": [
                    {"u": "u10", "v": "v10", "basis": "earth"},
                    {"u": "u", "v": "v", "basis": "earth"}],
                "field_metadata": {name: {"kind": "continuous"} for name in ("prmsl", "t", "r", "z")},
                "variables": {"2d": ["prmsl", "u10", "v10"],
                              "3d": ["u", "v", "t", "r", "z"],
                              "levels": {"values": [850]}}},
            "surface": {"model": "arome", "files": surface, "format": "fa",
                "profile": "surfex_history",
                "reader": {"python_executable": EPYTHON, "max_points": 99},
                "fa": {"earth_radius_m": 6371229.,
                "expected_source": {"PROGRAM": "AROME", "MASDEV": 47, "VERSION": 8,
                                    "BUG": 1, "BUGFIX": 0}},
                "field_metadata": {name: {"units": "K", "kind": "continuous",
                                           "temporal_kind": "instantaneous", "allow_unscaled": False}
                                   for name in ("SFX.T2M", "SFX.SST")},
                "variables": {"2d": ["SFX.T2M", "SFX.SST"]}},
        },
        "region": {"track": {"file": str(track)}, "width_km": {"x": 8., "y": 8.},
                   "sources_coupling_time_association": "common"},
        "products": {"model_grid": True, "track": True},
        "resources": {"synchronous_export": synchronous, "export_workers": 1},
        "output": {"directory": str(directory / "run"), "overwrite": False},
    }


def assert_primary_pair_provenance(conf):
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    alignment = provenance["time_alignment"]
    assert status["state"] == "completed" and alignment == status["time_alignment"]
    assert alignment["policy"] == "common"
    assert alignment["selected_times"] == [f"2026-01-01T0{hour}:00:00.000000000" for hour in (1, 2)]
    for name, skipped, missing, filename in (("atmosphere", 0, 3, "atmosphere-0.grib"),
                                              ("surface", 3, 0, "surface-3.fa")):
        assert alignment["sources"][name] == {
            "available_count": 3, "selected_count": 2,
            "skipped_times": [f"2026-01-01T0{skipped}:00:00.000000000"],
            "missing_times": [f"2026-01-01T0{missing}:00:00.000000000"],
            "skipped_files": [filename],
            "associations": [{
                "source_time": f"2026-01-01T0{hour}:00:00.000000000",
                "coupling_time": f"2026-01-01T0{hour}:00:00.000000000",
                "offset_seconds": 0.} for hour in (1, 2)]}
    source = provenance["sources"]["surface"]
    decoder = source["fa_decoder"]
    assert decoder["decode_requests"] > 0
    assert decoder["backend_versions"]["FA_backend"] == "epygram"
    assert decoder["backend_versions"]["EPyGrAM"] == "2.1.0"
    assert decoder["backend_versions"]["falfilfa4py"] == "1.2.1"
    assert set(decoder["payload_reads"]) == {"surface-1.fa", "surface-2.fa"}
    for fields in decoder["payload_reads"].values():
        assert set(fields) == {"SFX.T2M", "SFX.SST"}
        assert all(evidence == {"library": "EPyGrAM", "resource_class": "epygram.formats.FA.FA",
                                "accessor": "_readH2DField(getdata=True)", "openmode": "r"}
                   for evidence in fields.values())
    for fields in decoder["field_observations"].values():
        for descriptor in fields.values():
            assert descriptor["scaling"]["fallback"] is None
            assert descriptor["scaling"]["status"] == "not_exposed"
            assert descriptor["mask"]["undefined"]["origin"] == "EPyGrAM_returned_mask"
    assert decoder["field_observations"]["surface-1.fa"]["SFX.SST"]["mask"]["nonfinite_count"] == 1
    assert decoder["field_observations"]["surface-2.fa"]["SFX.SST"]["mask"]["nonfinite_count"] == 0
    assert len({record["source_id"] for record in source["fa_inputs"]}) == 2
    restored = SimulationConfig.from_yaml(conf.output_dir / "resolved-config.yaml")
    settings = restored.sources["surface"]
    assert decoder["backend_versions"]["FA_backend"] == "epygram" and (
        settings["reader"]["python_executable"] == EPYTHON)
    assert all(not declaration["allow_unscaled"]
               for declaration in settings["field_metadata"].values())
    assert {tuple(grid["geometry"]["shape"]) for grid in
            provenance["sources"]["atmosphere"]["region"]["grids"].values()} == {(13, 15)}
    assert {tuple(grid["geometry"]["shape"])
            for grid in source["region"]["grids"].values()} == {(9, 11)}
    assert not {"epygram", "falfilfa4py", "ectrans4py"} & sys.modules.keys()
    return provenance, status


# This program deliberately imports only ordinary readers and independent equations.
PRIMARY_NATIVE_CHECK = """
import sys, json, numpy as np, xarray as xr, yaml
p = json.loads(sys.argv[1])
times = np.array(['2026-01-01T01:00','2026-01-01T02:00'], dtype='datetime64[ns]')
with xr.open_dataset(p['track'], engine='netcdf4') as track:
    np.testing.assert_array_equal(track.time, times)
    np.testing.assert_array_equal(track.longitude, [50., 50.015])
    np.testing.assert_array_equal(track.latitude, [-20., -19.988])
    provenance = yaml.safe_load(open(p['provenance']))
    atmosphere_grids = list(provenance['sources']['atmosphere']['region']['grids'].values())
    surface_grids = list(provenance['sources']['surface']['region']['grids'].values())
    assert atmosphere_grids and surface_grids
    for grid in atmosphere_grids:
        np.testing.assert_array_equal(grid['native_x_indices'], [7,9])
        np.testing.assert_array_equal(grid['native_y_indices'], [6,7])
    for grid in surface_grids:
        np.testing.assert_array_equal(grid['native_x_indices'], [5,6])
        np.testing.assert_array_equal(grid['native_y_indices'], [4,4])
    assert sum(len(s['skipped_times']) for s in
               provenance['time_alignment']['sources'].values()) == 2
    for name in ('atmosphere.surface','atmosphere.isobaricInhPa','surface.surface'):
        with xr.open_dataset(p[name.split('.')[0]], engine='netcdf4') as data:
            np.testing.assert_array_equal(data.time, times)
            assert data.attrs['source_id'] == name.split('.')[0]
            assert data.attrs['product_type'] == 'model_grid'
            for t,hour in enumerate((1,2)):
                j, i = np.meshgrid(
                    data.y_source_native_index[t],
                    data.x_source_native_index[t],
                    indexing='ij')
                if name == 'atmosphere.surface':
                    assert set(data.data_vars) == {'prmsl','u10','v10','u','v','t','r','z'}
                    np.testing.assert_array_equal(data.prmsl[t],100000.+100*hour+10*j+i)
                    np.testing.assert_array_equal(data.u10[t],np.zeros_like(j))
                    np.testing.assert_array_equal(data.v10[t],np.full_like(j,4+hour))
                    assert data.prmsl.attrs['units'] == 'Pa'
                elif name == 'atmosphere.isobaricInhPa':
                    assert set(data.data_vars) == {'prmsl','u10','v10','u','v','t','r','z'}
                    np.testing.assert_array_equal(data.pressure,[850.])
                    for var,base in (('u',3.),('v',4.),('t',260.),('r',60.),('z',50000.)):
                        expected = base+8.5+hour+2*j+i
                        if var == 'r': expected[(j==4)&(i==5)] = np.nan
                        np.testing.assert_array_equal(data[var][t,0],expected)
                    assert data.z.attrs['units'] == 'm**2 s**-2'
                    assert data.r.attrs['units'] == '%'
                else:
                    assert set(data.data_vars) == {'SFX.T2M','SFX.SST'}
                    expected = np.full(j.shape,280.+hour)
                    expected[(j==3)&(i==4)] = 0.
                    np.testing.assert_array_equal(data['SFX.T2M'][t], expected)
                    expected = np.full(j.shape,300.+hour)
                    if hour == 1: expected[(j==4)&(i==5)] = np.nan
                    np.testing.assert_array_equal(data['SFX.SST'][t], expected)
                    for var,mask in (('SFX.SST','SEA'),('SFX.T2M','FULL')):
                        assert data[var].attrs['source_variable_name'] == var
                        assert data[var].attrs['surfex_support_mask'] == mask
                        descriptor = json.loads(data[var].attrs['fa_field_descriptor'])
                        assert descriptor['native_id'] == var
                    assert 'level' not in data.dims
assert not {'frameit','epygram','falfilfa4py','eccodes','cfgrib'} & sys.modules.keys()
"""


@EPYGRAM
@pytest.mark.parametrize("synchronous", [True, False])
def test_primary_grib_epygram_surfex_native_exports(tmp_path, synchronous, monkeypatch, caplog):
    from frameit.processing.polar.polar_grid import PolarLonLatGrid

    raw = primary_pair_document(tmp_path, synchronous=synchronous)
    originals = {Path(path): Path(path).read_bytes() for source in raw["sources"].values()
                 for path in source["files"]}

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled polar processing must not build a target")

    monkeypatch.setattr(PolarLonLatGrid, "build", forbidden)
    reads = []
    from frameit.io import fa_utils

    original = fa_utils.request_fa

    def counted(request):
        reads.append((Path(request["path"]).name, request["fields"]))
        return original(request)

    monkeypatch.setattr(fa_utils, "request_fa", counted)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with caplog.at_level(logging.WARNING):
        checked = collect_preflight(conf)
    assert not checked.errors, checked.errors
    plan = checked.facts
    assert not reads and not conf.output_dir.exists()
    assert len(conf.simulation_parameter["region_alignment"]["selected_times"]) == 2 and (
        plan.get("common_polar_target") is None)
    assert "Source atmosphere" in caplog.text and "Source surface" in caplog.text
    result = execute_simulation(conf)
    assert result.ok
    # Spawned exports are observed in the decoder log, not a parent-process mock.
    paths = {p["source"]: p["path"] for p in result.products if p["role"] == "model_grid"}
    paths["track"] = str(conf.output_dir / "products/primary-pair.track.nc")
    paths["provenance"] = str(conf.output_dir / "run-provenance.yaml")
    check = subprocess.run([sys.executable, "-c", PRIMARY_NATIVE_CHECK, json.dumps(paths)],
                           capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    assert_primary_pair_provenance(conf)
    assert result.ok and result.n_files == 4
    assert all(path.read_bytes() == before for path, before in originals.items())
    assert not list(conf.output_dir.rglob("*.partial"))


@EPYGRAM
@pytest.mark.parametrize("failure", ["cycle", "mixed_cycles", "clock", "source"])
def test_primary_pair_rejects_time_cycle_clock_and_source_conflicts(tmp_path, failure):
    raw = primary_pair_document(
        tmp_path, cycles={1: 1, 2: 1} if failure == "cycle" else (
            {2: 1} if failure == "mixed_cycles" else None),
        surface_overrides={2: {"state_hours": 9}} if failure == "clock" else None)
    if failure == "cycle":
        message = r"sources\.atmosphere:.*several forecast cycles.*time\.cycle"
    elif failure == "mixed_cycles":
        message = "Source atmosphere: select one forecast cycle|time.cycle"
    elif failure == "clock":
        message = "DTCUR conflicts"
    else:
        raw["sources"]["surface"]["fa"]["expected_source"]["BUG"] = 2
        message = "expected_source.BUG"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match=message):
        bind_sources(conf)
    assert not conf.output_dir.exists()


@EPYGRAM
@pytest.mark.parametrize("nt", [1, 2])
@pytest.mark.parametrize("packing", [0, 120])
def test_automatic_coupling_preserves_centres_and_scaling_guard(tmp_path, packing, nt):
    raw = primary_pair_document(tmp_path, surface_overrides={1: {"packing": packing}})
    suffixes = tuple(f"-{hour}" for hour in range(1, nt + 1))
    for source in raw["sources"].values():
        source["files"] = [path for path in source["files"] if Path(path).stem.endswith(suffixes)]
    raw["region"].pop("track")
    raw["region"]["tracker"] = {"method": "pressure_wind", "on_incomplete": "error"}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    checked = collect_preflight(conf)
    assert not checked.errors, checked.errors
    assert len(conf.simulation_parameter["region_alignment"]["selected_times"]) == nt
    result = execute_simulation(conf)
    assert result.ok
    with xr.open_dataset(conf.output_dir / "products/primary-pair.track.nc") as track:
        np.testing.assert_allclose(track.longitude, np.full(nt, 49.932968), rtol=0, atol=1.e-6)
        np.testing.assert_allclose(track.latitude, np.full(nt, -20.054), rtol=0, atol=1.e-6)
        np.testing.assert_array_equal(track.cx, np.zeros(nt))
        np.testing.assert_array_equal(track.cy, np.zeros(nt))
        provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
        grids = provenance["sources"]["surface"]["region"]["grids"]
        assert grids and all("native_x_indices" in grid and "native_y_indices" in grid
                             for grid in grids.values())
        for name in ("heading_deg", "dist", "speed"):
            if nt == 1:
                assert np.isnan(track[name]).all()
            else:
                assert np.isfinite(track[name]).all()
    product = next(p["path"] for p in result.products if p.get("source") == "surface")
    with xr.open_dataset(product) as data:
        assert data.sizes["time"] == nt
        np.testing.assert_allclose(data["SFX.T2M"].isel(
            x=data.sizes["x"] // 2, y=data.sizes["y"] // 2), np.arange(nt) + 281.)
    if packing == 120:
        provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
        fields = provenance["sources"]["surface"]["fa_decoder"]["field_observations"]["surface-1.fa"]
        for field in fields.values():
            assert field["scaling"]["status"] == "encoded"
            assert field["scaling"]["divisor"] == 1.
            assert field["scaling"]["fallback"] is None
            assert field["scaling"]["allow_unscaled"] is False


@EPYGRAM
def test_primary_pair_cannot_bypass_missing_surface_scaling(tmp_path):
    raw = primary_pair_document(tmp_path, surface_overrides={
        1: {"packing": 120, "omit_scaling_section": True}})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    checked = collect_preflight(conf)
    assert not checked.errors, checked.errors
    assert len(conf.simulation_parameter["region_alignment"]["selected_times"]) == 2
    with pytest.raises(ValueError, match="unresolved native scaling metadata"):
        execute_simulation(conf)
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    assert status["state"] == "failed"
    observations = provenance["sources"]["surface"]["fa_decoder"]["field_observations"]
    missing = [d["scaling"] for d in observations["surface-1.fa"].values()]
    assert any(s["status"] == "missing" for s in missing)
    assert all(s["fallback"] is None for s in missing)
    assert not (conf.output_dir / "products/primary-pair.surface.model_grid.nc").exists()


def test_exact_common_exclusions_remain_complete_beyond_warning_preview(caplog):
    times = [f"2026-01-01T{hour:02d}:00:00.000000000" for hour in range(14)]
    inventories = {"atmosphere": [{"path": "all.grib", "times": times}],
                   "surfex": [{"path": "common.fa", "times": times[-2:]}]}
    with caplog.at_level(logging.WARNING):
        report = align_source_times(inventories)
    assert report["sources"]["atmosphere"]["skipped_times"] == times[:-2]
    assert report["sources"]["surfex"]["missing_times"] == times[:-2]
    assert "12 timestamp(s)" in caplog.text and "..." in caplog.text
