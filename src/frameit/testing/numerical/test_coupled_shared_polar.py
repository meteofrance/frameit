"""Shared target coordinates are independent of source grids, masks and containers."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import dask.array as da
import numpy as np
import pytest
import xarray as xr
import yaml
from dask import delayed

from frameit.core.configuration import resolve_schema
from frameit.core.coupled import _polar_target_signature, _shared_polar_target
from frameit.core.execution import execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.testing.numerical.test_fa_io import NATIVE, fa_files
from frameit.testing.numerical.test_fa_pipeline import (
    EPYGRAM,
    PRIMARY_NATIVE_CHECK,
    assert_primary_pair_provenance,
    primary_pair_document,
)


def requests(radial=None, count=None, step=None, ellipsoid="WGS84"):
    return dict(radial_step_m=radial, azimuth_count=count, azimuth_step_deg=step,
                ellipsoid=ellipsoid)


def target_inputs():
    parent = SimpleNamespace(polar_shared_target=True, tracking_source="atmosphere")
    requested = {name: requests() for name in ("atmosphere", "surface", "auxiliary")}
    children = {name: SimpleNamespace(
        compute_polar_proj=True, polar_variables={"surface": {"variables": ["value"]}},
        resolution=resolution, radial_resolution=resolution, polar_n_theta=None,
        azimuthal_resolution=None, polar_ellipsoid="WGS84", polar_max_points=1000,
        x_boxsize_km=8., y_boxsize_km=8., yaml_config={"polar": dict(requested[name])},
    ) for name, resolution in zip(requested, (1000., 2000., 3000.), strict=True)}
    return parent, children, {name: {} for name in children}, requested


def test_common_sampling_resolution_and_disabled_optionality():
    parent, children, plans, requested = target_inputs()
    contract = _shared_polar_target(parent, children, plans, requested, 2)
    assert contract["radial_step_m"] == 3000.
    assert contract["radial_step_origin"] == "coarsest_participating_native_grid"
    assert contract["azimuth_count"] == 9
    assert {child.radial_resolution for child in children.values()} == {3000.}
    assert all(child.yaml_config["polar"]["azimuth_count"] == 9 for child in children.values())
    parent.polar_shared_target = False
    children["surface"].polar_ellipsoid = "different"
    assert _shared_polar_target(parent, children, plans, requested, 2) is None
    parent.polar_shared_target = True
    for child in children.values():
        child.compute_polar_proj = False
    assert _shared_polar_target(parent, children, plans, requested, 2) is None
    parent, children, plans, requested = target_inputs()
    children["auxiliary"].polar_variables = {"surface": {"variables": []}}
    contract = _shared_polar_target(parent, children, plans, requested, 2)
    assert contract["participants"] == ["atmosphere", "surface"]
    assert contract["radial_step_m"] == 2000.


@pytest.mark.parametrize("conflict", [
    "radial", "finer", "angles", "ellipsoid", "budget", "reference"])
def test_common_sampling_conflicts_fail_without_payload_or_native_dependencies(conflict):
    parent, children, plans, requested = target_inputs()
    if conflict == "radial":
        requested["atmosphere"]["radial_step_m"] = 3000.
        requested["surface"]["radial_step_m"] = 4000.
    elif conflict == "finer":
        requested["atmosphere"]["radial_step_m"] = 1000.
    elif conflict == "angles":
        requested["surface"]["azimuth_count"] = 16
    elif conflict == "ellipsoid":
        children["surface"].polar_ellipsoid = "GRS80"
    elif conflict == "reference":
        children["atmosphere"].compute_polar_proj = False
    else:
        children["surface"].polar_max_points = 50  # 27 per frame, but 54 over two frames
    with pytest.raises(ValueError, match="shared_target|Polar target grid"):
        _shared_polar_target(parent, children, plans, requested, 2)


def moving_track():
    return xr.Dataset({"lon": ("time", [60., 60.003], {"units": "degrees_east"}),
                       "lat": ("time", [-20., -19.997], {"units": "degrees_north"})},
                      coords={"time": np.array(["2026-01-01", "2026-01-01T01:00"],
                                               dtype="datetime64[ns]")})


def test_secondary_fixed_box_honors_every_supplied_continuous_centre():
    track = moving_track()
    grid = PolarLonLatGrid(r_km=np.array([0., 1.]), theta_deg=np.array([0., 90., 180., 270.]),
                          tracking_method="fixed_box", time_dim="time", lon_name="longitude",
                          lat_name="latitude")
    geometry = grid.build(xr.Dataset(coords={"time": track.time}), track=track,
                           track_centres_authoritative=True)
    np.testing.assert_array_equal(geometry.center_lon, track.lon)
    np.testing.assert_array_equal(geometry.center_lat, track.lat)
    np.testing.assert_array_equal(geometry.lon.isel(rr=0, theta_deg=0), track.lon)
    assert not np.array_equal(geometry.lon[0], geometry.lon[1])


def test_target_identity_reads_coordinates_not_physical_payloads():
    track = moving_track()
    lon = np.broadcast_to(track.lon.values[:, None, None], (2, 2, 3)).copy()
    lat = np.broadcast_to(track.lat.values[:, None, None], (2, 2, 3)).copy()

    @delayed
    def forbidden():
        raise AssertionError("target compatibility must not decode an unrelated physical field")

    data = xr.Dataset({"field": (("time", "rr", "theta"),
                                 da.from_delayed(forbidden(), shape=(2, 2, 3), dtype=float))},
                      coords={"time": track.time, "rr": [0., 1.], "theta": [0., 2., 4.],
                              "longitude": (("time", "rr", "theta"), lon),
                              "latitude": (("time", "rr", "theta"), lat),
                              "center_lon": track.lon, "center_lat": track.lat})
    child = SimpleNamespace(name_longitude="longitude", name_latitude="latitude",
                            polar_ellipsoid="WGS84")
    signature = _polar_target_signature(data, child, track)
    altered = data.assign_coords(longitude=data.longitude + .001)
    assert _polar_target_signature(altered, child, track) != signature
    with pytest.raises(ValueError, match="continuous reference track"):
        _polar_target_signature(data.assign_coords(center_lon=data.center_lon + .001), child, track)


def netcdf_source(directory, name, spacing, value, *, masked=False):
    x, y = np.arange(-7, 8) * spacing, np.arange(-6, 7) * spacing
    lon, lat = np.meshgrid(60. + np.rad2deg(x / (6371229. * np.cos(np.deg2rad(20.)))),
                           -20. + np.rad2deg(y / 6371229.))
    values = np.broadcast_to(np.array([value, value + 1.])[:, None, None], (2, 13, 15)).copy()
    if masked:
        values[0, 6, 7] = np.nan
    ds = xr.Dataset({"temperature": (("time", "nj", "ni"), values, {"units": "K"})},
                    coords={"time": moving_track().time, "ni": ("ni", x, {"units": "m"}),
                            "nj": ("nj", y, {"units": "m"}),
                             "longitude": (("nj", "ni"), lon, {"units": "degrees_east"}),
                             "latitude": (("nj", "ni"), lat, {"units": "degrees_north"})})
    if name == "surface":
        ds = ds.rename(time="time_counter", nj="y", ni="x",
                       latitude="nav_lat", longitude="nav_lon")
    path = directory / f"{name}.nc"
    ds.to_netcdf(path, engine="netcdf4")
    return path


def coupled_document(directory, *, synchronous=True):
    sources = {}
    for name, spacing, value in (("atmosphere", 1000., 280.), ("surface", 3000., 300.)):
        path = netcdf_source(directory, name, spacing, value, masked=name == "surface")
        sources[name] = {"model": "mesonh" if name == "atmosphere" else "nemo",
                         "files": [str(path)], "format": "netcdf",
                         "variables": {"2d": ["temperature"]},
                         "field_metadata": {"temperature": {"kind": "continuous"}}}
    track = directory / "track.nc"
    moving_track().rename(lon="longitude", lat="latitude").to_netcdf(track)
    return {"schema_version": 3, "run": {"name": "shared"}, "sources": sources,
            "region": {"track": {"file": str(track)}, "width_km": {"x": 8, "y": 8},
                       "sources_coupling_time_association": "common"},
            "products": {"model_grid": True, "track": True,
                         "polar": {"radius_km": 4., "shared_grid": True}},
            "resources": {"synchronous_export": synchronous, "export_workers": 1},
            "output": {"directory": str(directory / "run"), "overwrite": False}}


def test_shared_target_schema_is_additive_and_global(tmp_path):
    document = coupled_document(tmp_path)
    document["products"]["polar"]["shared_grid"] = "true"
    with pytest.raises(ValueError, match="shared_grid: must be a YAML boolean"):
        resolve_schema(document)
    document["products"]["polar"]["shared_grid"] = True
    document["sources"]["surface"]["polar"] = {"shared_grid": False}
    with pytest.raises(ValueError, match="sources.surface.polar.*[Uu]nknown|[Uu]nknown.*polar"):
        resolve_schema(document)


@pytest.mark.parametrize("synchronous", [True, False])
def test_two_physical_sources_share_moving_target_but_not_masks(tmp_path, synchronous, monkeypatch):
    pytest.importorskip("xesmf")
    document = coupled_document(tmp_path, synchronous=synchronous)

    def no_fa(*args, **kwargs):
        raise AssertionError("NetCDF sources must remain independent of native FA")

    monkeypatch.setattr("frameit.io.fa_backend.request_fa", no_fa)
    conf = SimulationConfig.from_mapping_with_model_preset(document)
    plan = preflight(conf)
    assert plan["common_polar_target"]["radial_step_km"] == 3.
    assert plan["common_polar_target"]["radial_step_origin"] == "coarsest_native_grid"
    assert not conf.output_dir.exists()
    result = execute_simulation(conf)
    assert result.ok
    products = {p["source"]: p["path"] for p in result.products if p["role"] == "polar"}
    assert set(products) == {"atmosphere", "surface"}
    assert all(f".{name}.polar.nc" in str(path) for name, path in products.items())
    check = subprocess.run([sys.executable, "-c", """
import sys, json, numpy as np, xarray as xr
paths = json.loads(sys.argv[1])
datasets = {name: xr.open_dataset(path) for name, path in paths.items()}
try:
    a = datasets['atmosphere']
    for name, data in datasets.items():
        coordinates = ('time', 'radius', 'azimuth', 'longitude', 'latitude', 'center_longitude', 'center_latitude')
        for coordinate in coordinates:
            np.testing.assert_array_equal(data[coordinate], a[coordinate])
        assert data.attrs['source_id'] == name
    np.testing.assert_array_equal(a.center_longitude, [60.,60.003])
    np.testing.assert_array_equal(a.center_latitude, [-20.,-19.997])
    np.testing.assert_allclose(a.temperature.isel(radius=0), [[280.]*9,[281.]*9], atol=1.e-9)
    np.testing.assert_allclose(datasets['surface'].temperature.isel(time=1,radius=0),
                               [301.]*9, atol=1.e-9)
    assert np.isnan(datasets['surface'].temperature.isel(time=0,radius=0)).all()
    assert np.isfinite(a.temperature.isel(time=0,radius=0)).all()
finally:
    for d in datasets.values(): d.close()
assert 'frameit' not in sys.modules and 'falfilfa4py' not in sys.modules
""", json.dumps(products)], capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    contract = provenance["common_polar_target"]
    assert contract["verification"] == "exact_coordinates_at_associated_centres"
    assert contract["radial_step_origin"] == "coarsest_native_grid"
    assert status["state"] == provenance["state"] == "completed"
    restored = SimulationConfig.from_yaml(conf.output_dir / "resolved-config.yaml")
    assert restored.polar_shared_target is True
    replayed = preflight(restored, check_output=False)["common_polar_target"]
    assert replayed["radial_step_km"] == contract["radial_step_km"] == 3.
    assert replayed["azimuth_degrees"] == contract["azimuth_degrees"]


def test_disabled_shared_target_keeps_base_processing_optional(tmp_path, monkeypatch):
    document = coupled_document(tmp_path)
    document["products"].pop("polar")

    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled polar processing must not create target arrays")

    monkeypatch.setattr(PolarLonLatGrid, "build", forbidden)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(document))
    assert result.ok and all(p["role"] != "polar" for p in result.products)


def test_mismatched_actual_targets_fail_before_product_publication(tmp_path, monkeypatch):
    pytest.importorskip("xesmf")
    from frameit.processing.polar import polar_proj

    original = polar_proj.execute_source_polar

    def inconsistent(internal, source, binding, conf, centres, **kwargs):
        data, report = original(internal, source, binding, conf, centres, **kwargs)
        if conf.source_name == "surface":
            data = data.assign_coords(longitude=data.longitude + .001)
        return data, report

    monkeypatch.setattr(polar_proj, "execute_source_polar", inconsistent)
    conf = SimulationConfig.from_mapping_with_model_preset(coupled_document(tmp_path))
    with pytest.raises(ValueError, match="Shared polar target mismatch for surface: longitude"):
        execute_simulation(conf)
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["state"] == "failed" and status["products"] == []
    assert not list((conf.output_dir / "products").glob("*.nc"))


def test_shared_target_keeps_atmospheric_vertical_groups_separate(tmp_path):
    pytest.importorskip("xesmf")
    document = coupled_document(tmp_path)
    atmosphere = document["sources"]["atmosphere"]
    with xr.open_dataset(atmosphere["files"][0]) as original:
        source = original.load()
    source = source.assign_coords(level=("level", [1, 2], {"units": "1",
                                      "long_name": "synthetic stored level index"}))
    source["column_temperature"] = xr.concat(
        [source.temperature, source.temperature + 10.], dim=source.level).transpose(
            "time", "level", "nj", "ni").assign_attrs(units="K")
    path = tmp_path / "atmosphere-levels.nc"
    source.to_netcdf(path)
    atmosphere["files"] = [str(path)]
    atmosphere["variables"].update({"3d": ["column_temperature"],
                                    "levels": {"indices": [0, 1]}})
    atmosphere["field_metadata"]["column_temperature"] = {"kind": "continuous"}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(document))
    assert result.ok
    paths = [p["path"] for p in result.products if p["role"] == "polar"]
    assert len(paths) == 2 and any(".atmosphere.polar.nc" in str(p) for p in paths)
    with xr.open_dataset(next(p for p in paths if ".atmosphere.polar.nc" in str(p))) as column:
        np.testing.assert_array_equal(column.level, [1, 2])
        assert column.level.attrs["units"] == "1"
        np.testing.assert_allclose(column.column_temperature.isel(radius=0, azimuth=0),
                                   [[280., 290.], [281., 291.]], atol=1.e-9)
        with xr.open_dataset(next(p for p in paths if ".surface.polar.nc" in str(p))) as surface:
            np.testing.assert_array_equal(column.longitude, surface.longitude)
            np.testing.assert_array_equal(column.latitude, surface.latitude)


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
@pytest.mark.parametrize("shared", [True, False])
def test_dense_fa_surface_moving_polar_values_masks_and_readonly_inputs(tmp_path, shared):
    pytest.importorskip("xesmf")
    document = coupled_document(tmp_path)
    document["products"]["polar"].update(shared_grid=shared, radial_step_km=2., azimuth_count=8)
    temperature = np.full((13, 15), 300.)
    temperature[6, 7] = np.nan
    files = fa_files(tmp_path, (0, 1), profile="surfex_history", nx=15, ny=13, surface_fields=[
        {"name": "SST", "mask": "SEA", "values": temperature.tolist()},
        {"name": "WG1P1", "mask": "NATURE", "values": np.zeros((13, 15)).tolist()},
    ])
    before = [path.read_bytes() for path in files]
    for path in files:
        path.chmod(0o444)
    document["sources"]["surface"] = {
        "model": "arome", "files": [str(p) for p in files], "format": "fa",
        "profile": "surfex_history", "field_metadata": {
            "SFX.SST": {"units": "K", "kind": "continuous", "temporal_kind": "instantaneous"},
            "SFX.WG1P1": {"units": "m3 m-3", "kind": "continuous",
                          "temporal_kind": "instantaneous"}},
        "variables": {"2d": ["SFX.SST", "SFX.WG1P1"]}}
    conf = SimulationConfig.from_mapping_with_model_preset(document)
    result = execute_simulation(conf)
    assert result.ok and [p.read_bytes() for p in files] == before
    products = {p["source"]: p["path"] for p in result.products if p["role"] == "polar"}
    check = subprocess.run([sys.executable, "-c", """
import sys, json, xarray as xr, numpy as np
p = json.loads(sys.argv[1])
with xr.open_dataset(p['atmosphere']) as a, xr.open_dataset(p['surface']) as s:
    for name in ('time','radius','azimuth','longitude','latitude'):
        np.testing.assert_array_equal(a[name], s[name])
    np.testing.assert_array_equal(s.center_longitude, [60.,60.003])
    assert np.isnan(s['SFX.SST'].isel(time=0,radius=0)).all()
    np.testing.assert_array_equal(s['SFX.WG1P1'].isel(radius=0), np.zeros((2,8)))
    assert s['SFX.SST'].attrs['surfex_support_mask'] == 'SEA'
    assert s['SFX.WG1P1'].attrs['surfex_support_mask'] == 'NATURE'
    assert 'level' not in s.dims
assert 'frameit' not in sys.modules and 'falfilfa4py' not in sys.modules
""", json.dumps(products)], capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    assert "falfilfa4py" not in sys.modules


@EPYGRAM
@pytest.mark.parametrize("synchronous", [True, False])
def test_primary_pair_shared_target_geometry_budgets_and_fresh_exports(
    tmp_path, synchronous, monkeypatch,
):
    pytest.importorskip("xesmf")
    from frameit.core import grid_geometry
    from frameit.io import fa_utils
    from frameit.processing.polar import sampling

    raw = primary_pair_document(tmp_path, synchronous=synchronous)
    raw["products"]["polar"] = {"radius_km": 4., "shared_grid": True,
        "fields": {"atmosphere": ["prmsl", "t", "r", "z"], "surface": ["SFX.T2M", "SFX.SST"]},
        "processing": {"max_target_points": 60}}
    originals = {Path(path): Path(path).read_bytes() for source in raw["sources"].values()
                 for path in source["files"]}
    events, reads = [], []
    original_geometry = grid_geometry.resolve_geometry
    original_target = sampling.resolve_polar_sampling
    original_budget = sampling.check_point_budget
    original_read = fa_utils.request_fa

    def geometry(*args, **kwargs):
        result = original_geometry(*args, **kwargs)
        event = ("geometry", result["shape"])
        if event not in events:
            events.append(event)
        return result

    def target(source, binding, conf, *, radial_step_km=None):
        assert {tuple(shape) for operation, shape in events if operation == "geometry"} == {
            (13, 15), (9, 11)}
        if ("shared", None) not in events:
            events.append(("shared", None))
        return original_target(source, binding, conf, radial_step_km=radial_step_km)

    def budget(points, maximum):
        events.append(("budget", points))
        return original_budget(points, maximum)

    def read(request):
        reads.append(request["fields"])
        return original_read(request)

    # V3 resolves source geometry before final shared sampling; config also checks point guards.
    monkeypatch.setattr(grid_geometry, "resolve_geometry", geometry)
    monkeypatch.setattr(sampling, "resolve_polar_sampling", target)
    monkeypatch.setattr(sampling, "check_point_budget", budget)
    monkeypatch.setattr(fa_utils, "request_fa", read)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan = preflight(conf)
    assert [event for event in events if event[0] != "budget"][:3] == [
        ("geometry", [13, 15]), ("geometry", [9, 11]), ("shared", None)]
    # Option/one-frame guards also check 9/27 points; the full allocation is 54.
    budgets = [points for operation, points in events if operation == "budget"]
    assert max(budgets) == 54 and budgets.count(54) == 2
    assert all(len(p["requests"]["binding"]["polar_plan"]["source_times"]) *
               len(p["requests"]["binding"]["polar_plan"]["radius_km"]) *
               len(p["requests"]["binding"]["polar_plan"]["azimuth_degrees"]) == 54
               for p in plan["sources"].values())
    assert not reads and not conf.output_dir.exists()
    contract = plan["common_polar_target"]
    assert contract["radial_step_km"] == 3. and len(contract["azimuth_degrees"]) == 9
    assert contract["radial_step_origin"] == "coarsest_native_grid"
    result = execute_simulation(conf)
    assert result.ok
    carts = {p["source"]: p["path"] for p in result.products if p["role"] == "model_grid"}
    carts["track"] = next(p["path"] for p in result.products if p["role"] == "track")
    carts["provenance"] = str(conf.output_dir / "run-provenance.yaml")
    polars = {p["source"]: p["path"] for p in result.products if p["role"] == "polar"}
    assert set(polars) == {"atmosphere", "surface"}
    check = subprocess.run([sys.executable, "-c", PRIMARY_NATIVE_CHECK + """
polars = json.loads(sys.argv[2])
def selected_with_quality(data, names):
    suffixes = ('','_support_fraction','_interpolation_status','_valid',
                '_ring_coverage','_full_ring_valid')
    assert set(data.data_vars) == {n+s for n in names for s in suffixes} | {'geometry_mapped'}
    for name in names:
        assert data[name+'_interpolation_status'].dtype == np.uint8
        assert 'flag_meanings' in data[name+'_interpolation_status'].attrs
with xr.open_dataset(polars['atmosphere'], engine='netcdf4') as a:
    for group, path in polars.items():
        with xr.open_dataset(path, engine='netcdf4') as data:
            for name in ('time','radius','azimuth','longitude','latitude','center_longitude','center_latitude'):
                np.testing.assert_array_equal(data[name], a[name])
    np.testing.assert_array_equal(a.center_longitude, [50.,50.015])
    np.testing.assert_array_equal(a.center_latitude, [-20.,-19.988])
    # Independent affine GRIB truth at both continuous (not snapped) centres.
    j = (np.array([-20.,-19.988])+20.054)/.009
    i = (np.array([50.,50.015])-49.932968)/.009576
    expected = 100000.+100*np.array([1,2])+10*j+i
    # Ordinary exports retain the established float32 field encoding.
    np.testing.assert_array_equal(a.prmsl.isel(radius=0),
                                  np.broadcast_to(expected.astype('float32')[:,None],(2,9)))
    selected_with_quality(a, ['prmsl', 't', 'r', 'z'])
with xr.open_dataset(polars['surface'], engine='netcdf4') as s:
    selected_with_quality(s, ['SFX.T2M','SFX.SST'])
    assert np.isnan(s['SFX.SST'].isel(time=0,radius=0)).all()
    np.testing.assert_allclose(s['SFX.SST'].isel(time=1,radius=0),302.,rtol=0,atol=1.e-9)
    np.testing.assert_allclose(s['SFX.T2M'].isel(radius=0),[[281.]*9,[282.]*9],rtol=0,atol=1.e-9)
with xr.open_dataset(polars['atmosphere'], engine='netcdf4') as pressure:
    np.testing.assert_array_equal(pressure.pressure,[850.])
    selected_with_quality(pressure, ['prmsl','t','r','z'])
assert not {'frameit','epygram','falfilfa4py','eccodes','cfgrib'} & sys.modules.keys()
""", json.dumps(carts), json.dumps(polars)], capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    provenance, status = assert_primary_pair_provenance(conf)
    assert provenance["common_polar_target"]["verification"] == (
        "exact_coordinates_at_associated_centres")
    assert all(path.read_bytes() == before for path, before in originals.items())


@EPYGRAM
@pytest.mark.parametrize("failure", ["target_budget", "finer", "native_budget"])
def test_primary_pair_planning_guards_precede_payload_and_target_allocation(
    tmp_path, failure, monkeypatch,
):
    pytest.importorskip("xesmf")
    raw = primary_pair_document(tmp_path)
    raw["products"]["polar"] = {"radius_km": 4., "shared_grid": True,
        "fields": {"atmosphere": ["prmsl", "t", "r", "z"], "surface": ["SFX.T2M", "SFX.SST"]},
        "processing": {"max_target_points": 60}}
    if failure == "target_budget":
        raw["products"]["polar"]["processing"]["max_target_points"] = 53
        message = "requires 54 points"
    elif failure == "finer":
        raw["products"]["polar"]["radial_step_km"] = 1.
        message = "finer than a participating native grid"
    else:
        raw["sources"]["surface"]["reader"]["max_points"] = 98
        message = "resource budget"

    def forbidden(*args, **kwargs):
        raise AssertionError("planning must fail before physical reads or target allocation")

    monkeypatch.setattr("frameit.io.fa_utils.request_fa", forbidden)
    monkeypatch.setattr(PolarLonLatGrid, "build", forbidden)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match=message):
        preflight(conf)
    assert not conf.output_dir.exists()
