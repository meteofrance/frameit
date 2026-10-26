"""Active FA scope: AROME atmosphere and AROME-produced SURFEX, separate products."""

from __future__ import annotations

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
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.testing.numerical.test_fa_geometry import spherical_lambert
from frameit.testing.numerical.test_fa_io import NATIVE, fa_files


def arome_netcdf_document(directory, *, surface_spacing_m=3000.):
    """Compact AROME-schema NetCDF sources for the no-native planning regression."""
    times = np.array(["2026-01-01", "2026-01-01T01:00"], dtype="datetime64[ns]")
    sources = {}
    for name, spacing in (("atmosphere", 1000.), ("surface", surface_spacing_m)):
        latitude = -20. + np.rad2deg(np.arange(-6, 7) * spacing / 6371229.)
        longitude = 60. + np.rad2deg(np.arange(-7, 8) * spacing /
                                     (6371229. * np.cos(np.deg2rad(20.))))
        source = xr.Dataset({"temperature": (("valid_time", "latitude", "longitude"),
                                             np.broadcast_to(280. + np.arange(2)[:, None, None],
                                                             (2, 13, 15)), {"units": "K"})},
                            coords={"valid_time": times,
                                    "latitude": ("latitude", latitude, {"units": "degrees_north"}),
                                    "longitude": ("longitude", longitude,
                                                  {"units": "degrees_east"})})
        path = directory / f"{name}.nc"
        source.to_netcdf(path)
        sources[name] = {"model": "arome", "input": {"format": "netcdf", "files": [str(path)],
                                                     "grid_spacing_m": spacing},
                         "variables": {"surface": {"names": ["temperature"]}}}
    return {"schema_version": 2, "model": "arome", "run": {"name": "arome-budget"},
            "input": {"sources": sources}, "domain": {"size_km": {"x": 8., "y": 8.}},
            "tracking": {"source": "atmosphere", "method": "fixed_box", "fixed_box": {
                "center": {"latitude": -20., "longitude": 60.}}},
            "polar": {"enabled": True, "shared_target": True, "max_points": 60},
            "output": {"directory": str(directory / "out"), "overwrite": False,
                       "synchronous_export": True, "max_workers": 1}}


def test_effective_target_budget_precedes_unused_native_targets_and_replays(tmp_path):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan, children, _ = prepare_sources(conf)
    assert plan["common_polar_target"]["radial_step_m"] == 3000.
    assert plan["common_polar_target"]["azimuth_count"] == 9
    for name, child in children.items():
        assert "_defer_polar_sampling" not in child.simulation_parameter
        sampling = plan["sources"][name]["polar_sampling"]
        assert sampling["estimated_points_per_time"] * sampling["estimated_time_count"] == 54
    assert not conf.output_dir.exists()
    result = execute_simulation(conf)
    assert result.ok
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    contract = provenance["common_polar_target"]
    resolved = yaml.safe_load((conf.output_dir / "resolved-config.yaml").read_text())
    assert "_defer_polar_sampling" not in json.dumps(resolved)
    resolved["output"]["directory"] = str(tmp_path / "replay")
    replay = SimulationConfig.from_mapping_with_model_preset(resolved)
    assert execute_simulation(replay).ok
    replay_contract = yaml.safe_load((replay.output_dir / "run-status.yaml").read_text())[
        "common_polar_target"]
    assert replay_contract["target_signature"] == contract["target_signature"]


def test_arome_base_processing_needs_neither_fa_nor_polar_dependencies(tmp_path, monkeypatch):
    raw = arome_netcdf_document(tmp_path)
    raw["polar"]["enabled"] = False

    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled AROME base processing must not initialize "
                             "FA or polar targets")

    monkeypatch.setattr("frameit.io.fa_backend.request_fa", forbidden)
    monkeypatch.setattr(PolarLonLatGrid, "build", forbidden)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok and not any(item["role"] == "polar" for item in result.products)
    cartesian = {item["source"]: item["path"] for item in result.products if item["role"] == "cart"}
    assert set(cartesian) == {"atmosphere", "surface"}
    for path in cartesian.values():
        with xr.open_dataset(path) as data:
            np.testing.assert_allclose(data.temperature.sel(x_box=0, y_box=0), [280., 281.])
    assert "falfilfa4py" not in sys.modules


@pytest.mark.parametrize("failure", ["time_budget", "finer", "grid"])
def test_target_deferral_preserves_real_budgets_and_grid_guards(tmp_path, failure):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    if failure == "time_budget":
        raw["polar"]["max_points"] = 53
        message = "requires 54 points"
    elif failure == "finer":
        raw["polar"]["radial_step_m"] = 1000.
        message = "finer than a participating native grid"
    else:
        original = raw["input"]["sources"]["surface"]["input"]["files"][0]
        with xr.open_dataset(original) as source:
            data = source.load()
        latitude = (-20. + 2 * (data.latitude + 20.)).assign_attrs(data.latitude.attrs)
        path = tmp_path / "anisotropic.nc"
        data.assign_coords(latitude=latitude).to_netcdf(path)
        raw["input"]["sources"]["surface"]["input"]["files"] = [str(path)]
        message = "Anisotropic grid"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match=message):
        preflight(conf)
    assert not conf.output_dir.exists()


def test_independent_targets_keep_their_original_budget_validation(tmp_path):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    raw["polar"]["shared_target"] = False
    with pytest.raises(ValueError, match="requires 130 points"):
        preflight(SimulationConfig.from_mapping_with_model_preset(raw))


def test_common_target_time_budget_uses_selected_labels_not_unused_file_times(tmp_path):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    entry = raw["input"]["sources"]["surface"]["input"]
    with xr.open_dataset(entry["files"][0]) as source:
        one_time = source.isel(valid_time=[0]).load()
    path = tmp_path / "one-surface-time.nc"
    one_time.to_netcdf(path)
    entry["files"] = [str(path)]
    raw["polar"]["max_points"] = 30  # one 27-point target fits; two would not
    plan = preflight(SimulationConfig.from_mapping_with_model_preset(raw))
    assert plan["sources"]["atmosphere"]["polar_sampling"]["estimated_time_count"] == 1
    assert plan["sources"]["atmosphere"]["polar_sampling"]["estimated_points_per_time"] == 27
    assert plan["time_alignment"]["sources"]["atmosphere"]["skipped_times"] == [
        "2026-01-01T01:00:00.000000000"]


def test_disabled_source_never_allocates_an_unused_target(tmp_path):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path, surface_spacing_m=500.)
    raw["input"]["sources"]["surface"]["variables"] = {}
    raw["input"]["sources"]["surface"]["polar"] = {"enabled": False}
    raw["domain"]["size_km"] = {"x": 4., "y": 4.}
    raw["polar"]["max_points"] = 100
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan = preflight(conf)
    assert plan["common_polar_target"]["participants"] == ["atmosphere"]
    assert plan["common_polar_target"]["radial_step_m"] == 1000.
    assert "polar_sampling" not in plan["sources"]["surface"]
    assert execute_simulation(conf).ok


def test_arome_netcdf_source_time_is_canonical_across_multiple_files(tmp_path):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    entry = raw["input"]["sources"]["atmosphere"]["input"]
    with xr.open_dataset(entry["files"][0]) as source:
        data = source.load()
    paths = []
    for index in (1, 0):
        path = tmp_path / f"split-{index}.nc"
        data.isel(valid_time=[index]).to_netcdf(path)
        paths.append(str(path))
    entry["files"] = paths
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok
    product = next(item["path"] for item in result.products
                   if item["role"] == "polar" and item["source"] == "atmosphere")
    with xr.open_dataset(product) as output:
        assert "valid_time" not in output.dims
        np.testing.assert_array_equal(output.time, data.valid_time)
        np.testing.assert_allclose(output.temperature.isel(rr=0, theta=0), [280., 281.], atol=1.e-9)


def test_arome_netcdf_ambiguous_time_names_fail_without_guessing(tmp_path):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    entry = raw["input"]["sources"]["atmosphere"]["input"]
    with xr.open_dataset(entry["files"][0]) as source:
        data = source.load().assign_coords(time=np.datetime64("2025-12-31", "ns"))
    path = tmp_path / "ambiguous-time.nc"
    data.to_netcdf(path)
    entry["files"] = [str(path)]
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="conflicts with configured dimension"):
        execute_simulation(conf)
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["state"] == "failed" and status["products"] == []


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_arome_fa_and_surfex_fa_share_the_effective_target_on_distinct_grids(tmp_path):
    pytest.importorskip("xesmf")
    atmospheric_dir, surface_dir = tmp_path / "atmosphere", tmp_path / "surface"
    atmospheric_dir.mkdir()
    surface_dir.mkdir()
    atmosphere = fa_files(atmospheric_dir, (0, 1), nx=15, ny=13, projection_latitude=-30.,
                          field_values=np.full((13, 15), 280.).tolist())
    surface = fa_files(surface_dir, (0, 1), profile="surfex_history", nx=11, ny=9,
                       projection_latitude=-30., projected_spacing_m=3000.,
                       field_values=np.full((9, 11), 300.).tolist())
    originals = {path: path.read_bytes() for path in [*atmosphere, *surface]}
    for path in originals:
        path.chmod(0o444)
    times = np.array(["2026-01-01", "2026-01-01T01:00"], dtype="datetime64[ns]")
    longitude, latitude = spherical_lambert(np.array([0., 400.]), np.array([0., 300.]), 6371229.)
    track = tmp_path / "track.nc"
    xr.Dataset({"longitude": ("time", longitude), "latitude": ("time", latitude)},
               coords={"time": times}).to_netcdf(track)
    sources = {}
    for name, files, profile, field in (
        ("atmosphere", atmosphere, "arome_history", "CLSTEMPERATURE"),
        ("surface", surface, "surfex_history", "SFX.T2M"),
    ):
        sources[name] = {"model": "arome", "input": {
            "format": "fa", "files": [str(path) for path in files], "fa": {
                "profile": profile, "earth_radius_m": 6371229., "field_metadata": {
                    field: {"units": "K", "kind": "continuous",
                            "temporal_kind": "instantaneous"}}}},
            "variables": {"surface": {"names": [field]}}}
    raw = {"schema_version": 2, "model": "arome", "run": {"name": "arome-sfx"},
           "input": {"sources": sources}, "domain": {"size_km": {"x": 8., "y": 8.}},
           "tracking": {"source": "atmosphere", "method": "prescribed_track",
                        "prescribed_track": {"file": str(track)}},
           "polar": {"enabled": True, "shared_target": True, "max_points": 60},
           "output": {"directory": str(tmp_path / "out"), "overwrite": False,
                      "synchronous_export": True, "max_workers": 1}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan = preflight(conf)
    assert plan["common_polar_target"]["radial_step_m"] == 3000.
    result = execute_simulation(conf)
    assert result.ok
    paths = {item["source"]: item["path"] for item in result.products if item["role"] == "polar"}
    paths["track"] = next(item["path"] for item in result.products if item["role"] == "track")
    check = subprocess.run([sys.executable, "-c", """
import sys, json, xarray as xr, numpy as np
p = json.loads(sys.argv[1])
with xr.open_dataset(p['atmosphere']) as a, xr.open_dataset(p['surface']) as s:
    for name in ('time','rr','theta','longitude','latitude','center_lon','center_lat'):
        np.testing.assert_array_equal(a[name], s[name])
    assert a.attrs['common_polar_target_id'] == s.attrs['common_polar_target_id']
    np.testing.assert_allclose(a.CLSTEMPERATURE.isel(rr=0), [[280.]*9,[280.5]*9], atol=1.e-9)
    np.testing.assert_allclose(s['SFX.T2M'].isel(rr=0), [[300.]*9,[300.5]*9], atol=1.e-9)
with xr.open_dataset(p['track']) as t:
    assert int(t.atmosphere_cx[0]) == 7 and int(t.surface_cx[0]) == 5
    assert int(t.atmosphere_cy[0]) == 6 and int(t.surface_cy[0]) == 4
assert 'frameit' not in sys.modules and 'falfilfa4py' not in sys.modules
""", json.dumps(paths)], capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    assert all(path.read_bytes() == content for path, content in originals.items())
    restored = SimulationConfig.from_yaml(conf.output_dir / "resolved-config.yaml")
    assert restored.input_sources["surface"]["model"] == "arome"
    assert restored.input_sources["surface"]["polar"]["radial_step_m"] == 3000.
