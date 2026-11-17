"""Active FA scope: AROME atmosphere and AROME-produced SURFEX, separate products."""

from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.coupled import bind_sources
from frameit.core.execution import execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.testing.numerical.test_fa_geometry import spherical_lambert
from frameit.testing.numerical.test_fa_io import NATIVE, fa_files


def arome_netcdf_document(directory, *, surface_spacing_m=3000.):
    """Synthetic AROME/NEMO scalars for backend-free two-physical-source planning."""
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
        if name == "surface":
            lon, lat = np.meshgrid(longitude, latitude)
            source = source.rename(valid_time="time_counter", latitude="y", longitude="x")
            source = source.assign_coords(
                y=np.arange(13), x=np.arange(15),
                nav_lat=(("y", "x"), lat, {"units": "degrees_north"}),
                nav_lon=(("y", "x"), lon, {"units": "degrees_east"}))
        path = directory / f"{name}.nc"
        source.to_netcdf(path)
        sources[name] = {"model": "arome" if name == "atmosphere" else "nemo",
                         "format": "netcdf", "files": [str(path)],
                         "field_metadata": {"temperature": {"kind": "continuous"}},
                         "variables": {"2d": ["temperature"]}}
    return {"schema_version": 3, "run": {"name": "arome-budget"},
            "sources": sources,
            "region": {"center": {"latitude": -20., "longitude": 60.},
                       "width_km": {"x": 8., "y": 8.},
                       "sources_coupling_time_association": "common"},
            "products": {"model_grid": True, "track": True, "polar": {
                "radius_km": 4., "shared_grid": True, "processing": {"max_target_points": 60}}},
            "resources": {"synchronous_export": True, "export_workers": 1},
            "output": {"directory": str(directory / "out"), "overwrite": False}}


def test_effective_target_budget_precedes_unused_native_targets_and_replays(tmp_path):
    pytest.importorskip("xesmf")
    from pyproj import Geod

    raw = arome_netcdf_document(tmp_path)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan, children, _ = bind_sources(conf)
    # NEMO's angular grid uses WGS84 geography, not the AROME nominal metre step.
    lon_step = np.rad2deg(3000. / (6371229. * np.cos(np.deg2rad(20.))))
    expected_km = Geod(ellps="WGS84").inv(60., -20., 60. + lon_step, -20.)[2] / 1000
    np.testing.assert_allclose(plan["common_polar_target"]["radial_step_km"], expected_km,
                               rtol=1e-12, atol=0)
    assert len(plan["common_polar_target"]["azimuth_degrees"]) == 9
    for name, child in children.items():
        assert "_defer_polar_sampling" not in child.simulation_parameter
        sampling = plan["sources"][name]["requests"]["binding"]["polar_plan"]
        assert len(sampling["radius_km"]) * len(sampling["azimuth_degrees"]) * len(
            sampling["source_times"]) == 54
    assert not conf.output_dir.exists()
    result = execute_simulation(conf)
    assert result.ok
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    contract = provenance["common_polar_target"]
    resolved = yaml.safe_load((conf.output_dir / "resolved-config.yaml").read_text())
    assert "_defer_polar_sampling" not in json.dumps(resolved)
    resolved["output"]["directory"] = str(tmp_path / "replay")
    replay = SimulationConfig.from_mapping_with_model_preset(resolved)
    replay_result = execute_simulation(replay)
    assert replay_result.ok
    replay_contract = yaml.safe_load((replay.output_dir / "run-provenance.yaml").read_text())[
        "common_polar_target"]
    assert (replay_contract["radius_km"], replay_contract["azimuth_degrees"]) == (
        contract["radius_km"], contract["azimuth_degrees"])
    original = {item["source"]: item["path"] for item in result.products
                if item["role"] == "polar"}
    for item in replay_result.products:
        if item["role"] == "polar":
            with xr.open_dataset(original[item["source"]]) as before, xr.open_dataset(
                    item["path"]) as after:
                for name in ("time", "radius", "azimuth", "latitude", "longitude",
                             "center_time", "center_latitude", "center_longitude"):
                    np.testing.assert_array_equal(before[name], after[name])


def test_arome_base_processing_needs_neither_fa_nor_polar_dependencies(tmp_path, monkeypatch):
    raw = arome_netcdf_document(tmp_path)
    raw["products"].pop("polar")

    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled AROME base processing must not initialize "
                             "FA or polar targets")

    monkeypatch.setattr("frameit.io.fa_backend.request_fa", forbidden)
    monkeypatch.setattr(PolarLonLatGrid, "build", forbidden)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok and not any(item["role"] == "polar" for item in result.products)
    cartesian = {item["source"]: item["path"] for item in result.products
                 if item["role"] == "model_grid"}
    assert set(cartesian) == {"atmosphere", "surface"}
    for path in cartesian.values():
        with xr.open_dataset(path) as data:
            field = data.temperature
            np.testing.assert_allclose(field.isel({
                dim: field.sizes[dim] // 2 for dim in field.dims[-2:]}), [280., 281.])
    assert "falfilfa4py" not in sys.modules


@pytest.mark.parametrize("failure", ["time_budget", "finer", "grid"])
def test_target_deferral_preserves_real_budgets_and_grid_guards(tmp_path, failure):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    if failure == "time_budget":
        raw["products"]["polar"]["processing"]["max_target_points"] = 53
        message = "requires 54 points"
    elif failure == "finer":
        raw["products"]["polar"]["radial_step_km"] = 1.
        message = "finer than a participating native grid"
    else:
        original = raw["sources"]["surface"]["files"][0]
        with xr.open_dataset(original) as source:
            data = source.load()
        latitude = (-20. + 2 * (data.nav_lat + 20.)).assign_attrs(data.nav_lat.attrs)
        path = tmp_path / "anisotropic.nc"
        data.assign_coords(nav_lat=latitude).to_netcdf(path)
        raw["sources"]["surface"]["files"] = [str(path)]
        message = "Anisotropic grid"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match=message):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def test_independent_targets_keep_their_original_budget_validation(tmp_path):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    raw["products"]["polar"]["shared_grid"] = False
    with pytest.raises(ValueError, match="requires 130 points"):
        bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))


def test_common_target_time_budget_uses_selected_labels_not_unused_file_times(tmp_path):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    entry = raw["sources"]["surface"]
    with xr.open_dataset(entry["files"][0]) as source:
        one_time = source.isel(time_counter=[0]).load()
    path = tmp_path / "one-surface-time.nc"
    one_time.to_netcdf(path)
    entry["files"] = [str(path)]
    raw["products"]["polar"]["processing"]["max_target_points"] = 30
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan, _, _ = bind_sources(conf)
    sampling = plan["sources"]["atmosphere"]["requests"]["binding"]["polar_plan"]
    assert len(sampling["source_times"]) == 1
    assert len(sampling["radius_km"]) * len(sampling["azimuth_degrees"]) == 27
    assert conf.simulation_parameter["time_alignment"]["sources"]["atmosphere"]["skipped_times"] == [
        "2026-01-01T01:00:00.000000000"]


def test_disabled_source_never_allocates_an_unused_target(tmp_path):
    pytest.importorskip("xesmf")
    from pyproj import Geod

    raw = arome_netcdf_document(tmp_path, surface_spacing_m=500.)
    raw["products"]["model_grid"] = {"fields": {"atmosphere": ["temperature"]}}
    raw["products"]["polar"]["fields"] = {"atmosphere": ["temperature"]}
    raw["region"]["width_km"] = {"x": 4., "y": 4.}
    raw["products"]["polar"]["radius_km"] = 2.
    raw["products"]["polar"]["processing"]["max_target_points"] = 100
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan, _, _ = bind_sources(conf)
    assert plan["common_polar_target"]["participants"] == ["atmosphere"]
    lon_step = np.rad2deg(1000. / (6371229. * np.cos(np.deg2rad(20.))))
    expected_km = Geod(ellps="WGS84").inv(60., -20., 60. + lon_step, -20.)[2] / 1000
    np.testing.assert_allclose(plan["common_polar_target"]["radial_step_km"], expected_km,
                               rtol=1e-12, atol=0)
    assert "polar_plan" not in plan["sources"]["surface"]["requests"]["binding"]
    assert execute_simulation(conf).ok


def test_arome_netcdf_source_time_is_canonical_across_multiple_files(tmp_path):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    entry = raw["sources"]["atmosphere"]
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
        np.testing.assert_allclose(output.temperature.isel(radius=0, azimuth=0),
                                   [280., 281.], atol=1.e-9)


def test_arome_netcdf_ambiguous_time_names_fail_without_guessing(tmp_path):
    pytest.importorskip("xesmf")
    raw = arome_netcdf_document(tmp_path)
    entry = raw["sources"]["atmosphere"]
    with xr.open_dataset(entry["files"][0]) as source:
        data = source.load().assign_coords(time=np.datetime64("2025-12-31", "ns"))
    path = tmp_path / "ambiguous-time.nc"
    data.to_netcdf(path)
    entry["files"] = [str(path)]
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match=(
            "conflicts with configured dimension|conflicting or unidentified sample/forecast clocks")):
        execute_simulation(conf)
    assert not conf.output_dir.exists()


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
    xr.Dataset({"longitude": ("time", longitude, {"units": "degrees_east"}),
                "latitude": ("time", latitude, {"units": "degrees_north"})},
               coords={"time": times}).to_netcdf(track)
    sources = {}
    for name, files, profile, field in (
        ("atmosphere", atmosphere, "arome_history", "CLSTEMPERATURE"),
        ("surface", surface, "surfex_history", "SFX.T2M"),
    ):
        sources[name] = {"model": "arome",
            "format": "fa", "files": [str(path) for path in files],
            "profile": profile, "fa": {"earth_radius_m": 6371229.},
            "field_metadata": {
                    field: {"units": "K", "kind": "continuous",
                            "temporal_kind": "instantaneous"}},
            "variables": {"2d": [field]}}
    raw = {"schema_version": 3, "run": {"name": "arome-sfx"},
           "sources": sources,
           "region": {"track": {"file": str(track)}, "width_km": {"x": 8., "y": 8.},
                      "sources_coupling_time_association": "common"},
           "products": {"model_grid": True, "track": True, "polar": {
               "radius_km": 4., "shared_grid": True, "processing": {"max_target_points": 60}}},
           "resources": {"synchronous_export": True, "export_workers": 1},
           "output": {"directory": str(tmp_path / "out"), "overwrite": False}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan, _, _ = bind_sources(conf)
    assert plan["common_polar_target"]["radial_step_km"] == 3.
    result = execute_simulation(conf)
    assert result.ok
    paths = {item["source"]: item["path"] for item in result.products if item["role"] == "polar"}
    paths["track"] = next(item["path"] for item in result.products if item["role"] == "track")
    paths["provenance"] = str(conf.output_dir / "run-provenance.yaml")
    check = subprocess.run([sys.executable, "-c", """
import sys, json, xarray as xr, numpy as np, yaml
p = json.loads(sys.argv[1])
provenance = yaml.safe_load(open(p['provenance']))
with xr.open_dataset(p['atmosphere']) as a, xr.open_dataset(p['surface']) as s:
    for name in ('time','radius','azimuth','longitude','latitude',
                 'center_longitude','center_latitude'):
        np.testing.assert_array_equal(a[name], s[name])
    assert provenance['common_polar_target']['verification'] == 'exact_coordinates_at_associated_centres'
    descriptor = json.loads(a.CLSTEMPERATURE.attrs['fa_field_descriptor'])
    sampling = descriptor['sampling']
    assert sampling['native_vertical_header'] == {
        'KNIVER': 1, 'PREFER': 101325., 'PAHYBR': [0.,0.], 'PBHYBR': [0.,1.]}
    assert sampling['physical_location'] is None
    assert sampling['vertical_interpretation'].startswith('unqualified;')
    assert 'level' not in a.dims
    np.testing.assert_allclose(a.CLSTEMPERATURE.isel(radius=0), [[280.]*9,[280.5]*9], atol=1.e-9)
    np.testing.assert_allclose(s['SFX.T2M'].isel(radius=0), [[300.]*9,[300.5]*9], atol=1.e-9)
with xr.open_dataset(p['track']) as t:
    atmosphere, = provenance['sources']['atmosphere']['region']['grids'].values()
    surface, = provenance['sources']['surface']['region']['grids'].values()
    assert int(atmosphere['native_x_indices'][0]) == 7 and int(surface['native_x_indices'][0]) == 5
    assert int(atmosphere['native_y_indices'][0]) == 6 and int(surface['native_y_indices'][0]) == 4
assert 'frameit' not in sys.modules and 'falfilfa4py' not in sys.modules
""", json.dumps(paths)], capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    assert all(path.read_bytes() == content for path, content in originals.items())
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    for entry in provenance["sources"]["atmosphere"]["fa_inputs"]:
        sampling = entry["field_descriptors"]["CLSTEMPERATURE"]["sampling"]
        assert sampling["native_vertical_header"] == {
            "KNIVER": 1, "PREFER": 101325., "PAHYBR": [0., 0.], "PBHYBR": [0., 1.]}
        assert sampling["physical_location"] is None
    restored = SimulationConfig.from_yaml(conf.output_dir / "resolved-config.yaml")
    assert restored.sources["surface"]["model"] == "arome"
    replay_plan, _, _ = bind_sources(restored, check_output=False)
    assert replay_plan["common_polar_target"]["radial_step_km"] == 3.
