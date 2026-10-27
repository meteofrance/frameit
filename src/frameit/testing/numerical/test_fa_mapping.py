"""P2 native-axis association against independent spherical Lambert equations."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.coupled import _mapped_track
from frameit.core.execution import execute_simulation
from frameit.core.grid_geometry import resolve_geometry
from frameit.core.settings_class import SimulationConfig
from frameit.io.fa_epygram import geometry_contract
from frameit.io.fa_geometry import NATIVE_LOOKUP, admitted_geometry, fa_geometry, geometry_signature
from frameit.testing.numerical.test_fa_geometry import header, spherical_lambert
from frameit.testing.numerical.test_fa_io import NATIVE, fa_files
from frameit.testing.numerical.test_fa_pipeline import (
    atmospheric_file,
    document,
    single_fa_document,
)
from frameit.tracking.FixedBox_Tracker import FixedBoxTracker
from frameit.tracking.geographic import SNAP_VARIABLES, locate_track, nearest_grid_point
from frameit.tracking.PrescribedTrack_Tracker import PrescribedTrack

OPTIONS = {"subdomain": "CI", "earth_radius_m": 6371229.}
CONF = SimpleNamespace(name_lat_dim="y", name_lon_dim="x", name_time_dim="time",
                       name_latitude="latitude", name_longitude="longitude")


def track_at(x, y, latitude=-30.):
    lon, lat = spherical_lambert(np.atleast_1d(x), np.atleast_1d(y), 6371229., latitude)
    return xr.Dataset({"lat": ("time", lat), "lon": ("time", lon)}, coords={
        "time": np.datetime64("2026-01-01", "ns") + np.arange(lat.size) * np.timedelta64(1, "h")})


@pytest.mark.parametrize("latitude", [-30., 30.])
@pytest.mark.parametrize("reverse", [False, True])
def test_source_crs_selection_asymmetric_offset_and_descending_axes(latitude, reverse):
    source = fa_geometry(header(latitude), OPTIONS)
    if reverse:
        source = source.isel(x=slice(None, None, -1), y=slice(None, None, -1))
    track = track_at([-4499.99, 1250., 5000.], [-2100., 2700., 3000.], latitude)
    actual = locate_track(track, source, require_inside=True)
    expected_i = [int(np.argmin(abs(source.x.values - x))) for x in [-4499.99, 1250., 5000.]]
    expected_j = [int(np.argmin(abs(source.y.values - y))) for y in [-2100., 2700., 3000.]]
    np.testing.assert_array_equal(actual.cx, expected_i)
    np.testing.assert_array_equal(actual.cy, expected_j)
    np.testing.assert_array_equal(actual.lat, track.lat)
    np.testing.assert_array_equal(actual.lon, track.lon)
    np.testing.assert_allclose(actual.grid_snap_dx_m,
                               source.x.values[expected_i] - [-4499.99, 1250., 5000.], atol=1.e-7)
    np.testing.assert_allclose(actual.grid_snap_dy_m,
                               source.y.values[expected_j] - [-2100., 2700., 3000.], atol=1.e-7)
    np.testing.assert_allclose(actual.grid_snap_distance_m,
                               np.hypot(actual.grid_snap_dx_m, actual.grid_snap_dy_m))
    assert actual.attrs["tracking_grid_lookup"] == NATIVE_LOOKUP
    wrapped = track.assign(lon=track.lon + 360.)
    np.testing.assert_array_equal(locate_track(wrapped, source).cx, actual.cx)
    np.testing.assert_array_equal(locate_track(wrapped, source).cy, actual.cy)


def test_reproduced_squared_degree_error_and_legacy_decision_are_explicit():
    source = fa_geometry(header(), OPTIONS)
    track = track_at(-4499.99, -2100.)
    assert nearest_grid_point(source.latitude, source.longitude,
                              float(track.lat[0]), float(track.lon[0])) == (1, 0)
    native = locate_track(track, source)
    assert (int(native.cy[0]), int(native.cx[0])) == (1, 1)
    legacy = source.copy(deep=False)
    legacy.attrs = {}  # a CRS alone must not change other source formats' conventions
    old = locate_track(track, legacy)
    assert (int(old.cy[0]), int(old.cx[0])) == (1, 0)
    assert "grid_snap_dx_m" not in old


def test_secondary_legacy_source_never_inherits_reference_grid_observations():
    source = fa_geometry(header(), OPTIONS)
    reference = locate_track(track_at(500.01, -100.), source)
    legacy_source = source.copy(deep=False)
    legacy_source.attrs = {}
    mapped = _mapped_track(reference, legacy_source, CONF)
    assert not set(SNAP_VARIABLES) & set(mapped.variables)
    assert "tracking_grid_lookup" not in mapped.attrs
    assert set(SNAP_VARIABLES) <= set(reference.variables)
    assert reference.attrs["tracking_grid_lookup"] == NATIVE_LOOKUP


def test_coverage_zone_boundaries_ties_and_independent_source_indices():
    source = fa_geometry(header(), OPTIONS)
    outside = track_at(5001., 0.)
    with pytest.raises(ValueError, match="outside a selected source grid"):
        _mapped_track(outside, source, CONF)
    # Existing single-source edge-nearest policy is retained and reported.
    assert int(locate_track(outside, source).cx[0]) == 10
    for subdomain in ("CI", "C"):
        zone = fa_geometry(header(), {**OPTIONS, "subdomain": subdomain})
        edge = _mapped_track(track_at(float(zone.x[0]), float(zone.y[-1])), zone, CONF)
        assert (int(edge.cy[0]), int(edge.cx[0])) == (zone.sizes["y"] - 1, 0)
    tie = locate_track(track_at(-4500., -2500.), source)
    assert (int(tie.cy[0]), int(tie.cx[0])) == (0, 0)
    # Same shape, different grid: each source is located independently.
    shifted = source.assign_coords(x=source.x + 1000.)
    shifted.x.attrs = dict(source.x.attrs)
    lon, lat = spherical_lambert(*np.meshgrid(shifted.x, shifted.y), 6371229.)
    shifted = shifted.assign_coords(longitude=(("y", "x"), lon, source.longitude.attrs),
                                     latitude=(("y", "x"), lat, source.latitude.attrs))
    original = _mapped_track(track_at(0., 0.), source, CONF)
    different = _mapped_track(track_at(0., 0.), shifted, CONF)
    assert int(original.cx[0]) == 5 and int(different.cx[0]) == 4


@pytest.mark.parametrize("corruption", ["geography", "axis", "units", "time", "crs"])
def test_full_sample_association_rejects_contradictions(corruption):
    source = fa_geometry(header(), OPTIONS).copy(deep=True)
    if corruption == "geography":
        source.latitude.values[2, 3] += .001  # not a corner; full association must be checked
    elif corruption == "axis":
        values = source.x.values.copy()
        values[3] += 10.
        source = source.assign_coords(x=("x", values, source.x.attrs))
    elif corruption == "units":
        source.x.attrs["units"] = "km"
    elif corruption == "time":
        source = source.assign_coords(latitude=source.latitude.expand_dims(time=[0, 1]))
    else:
        source.crs.attrs["earth_radius"] = 5000000.
    with pytest.raises(ValueError, match="Native FA"):
        locate_track(track_at(0., 0.), source)


def test_active_signature_and_unqualified_header_guards():
    h = header()
    noisy = {**h, "PSINLA": [*h["PSINLA"], np.nan, 1.e99],
             "KNLOPA": [*h["KNLOPA"], 9999], "KNOZPA": [np.nan], "LDGARD": True,
             "PAHYBR": [np.nan], "KNIVER": 90}
    assert geometry_signature(h, OPTIONS) == geometry_signature(noisy, OPTIONS)
    changed = copy.deepcopy(h)
    changed["epygram"]["x"][0] += 1.
    assert geometry_signature(h, OPTIONS) != geometry_signature(changed, OPTIONS)
    for key, index, value in (("KNLOPA", 6, -1), ("KNLOPA", 2, 1.5),
                               ("PSINLA", 0, -2), ("PSINLA", 1, -9.1),
                               ("PSINLA", 4, np.nan)):
        bad = copy.deepcopy(h)
        bad[key][index] = value
        with pytest.raises(ValueError):
            admitted_geometry(bad, OPTIONS)
    for key, value in (("KTYPTR", 1), ("PCODIL", .5), ("PSLAPO", .1)):
        with pytest.raises(ValueError):
            admitted_geometry({**h, key: value}, OPTIONS)


def test_regular_descending_axes_and_encoded_corner_contradiction():
    h = header()
    h["KTYPTR"] = -11
    h["KNLOPA"][2:6] = [1, 13, 1, 9]
    p = h["PSINLA"]
    p[1], p[6], p[7] = -9, np.deg2rad(.01), np.deg2rad(-.01)
    p[12:16] = [p[4] - 6*p[6], p[5] - 4*p[7], p[4] + 6*p[6], p[5] + 4*p[7]]
    longitude = 50. + (np.arange(13) - 6)*.01
    latitude = -30. - (np.arange(9) - 4)*.01
    library = SimpleNamespace(
        name="regular_lonlat", position_on_horizontal_grid="center", dimensions={"X": 13, "Y": 9},
        gimme_corners_ij=lambda subzone: {"ll": (0, 0), "ur": (12, 8)},
        ij2xy=lambda i, j: (longitude[i], latitude[j]),
        ij2ll=lambda i, j: (longitude[i], latitude[j]))
    h["epygram"] = geometry_contract(library, h, OPTIONS)
    source = fa_geometry(h, OPTIONS)
    np.testing.assert_allclose(source.longitude, 50. + (np.arange(13) - 6) * .01)
    np.testing.assert_allclose(source.latitude, -30. - (np.arange(9) - 4) * .01)
    p[12] += .001
    with pytest.raises(ValueError, match="contradicts encoded CI corners"):
        geometry_contract(library, h, OPTIONS)


def test_anisotropic_lookup_does_not_bypass_scalar_extraction_guards():
    source = fa_geometry(header(), OPTIONS)
    source = source.assign_coords(y=source.y * 2)
    source.y.attrs = {"units": "m"}
    lon, lat = spherical_lambert(*np.meshgrid(source.x, source.y), 6371229.)
    source = source.assign_coords(longitude=(("y", "x"), lon, {"units": "degrees_east"}),
                                   latitude=(("y", "x"), lat, {"units": "degrees_north"}))
    assert int(locate_track(track_at(0., 0.), source).cx[0]) == 5
    conf = SimpleNamespace(**vars(CONF), yaml_config={"input": {"grid_spacing_m": 1000.}})
    with pytest.raises(ValueError, match="Anisotropic grid"):
        resolve_geometry(conf, [source])


def test_fixed_and_prescribed_tracking_keep_requested_centres(tmp_path):
    source = fa_geometry(header(), OPTIONS).assign_coords(time=[np.datetime64("2026-01-01", "ns")])
    track = track_at(-4499.99, -2100.)
    fixed = FixedBoxTracker({}, [float(track.lat[0]), float(track.lon[0])])._track_method(source)
    assert int(fixed.cx[0]) == 1
    path = tmp_path / "prescribed.nc"
    track.rename(lat="latitude", lon="longitude").to_netcdf(path)
    prescribed = PrescribedTrack({}, path)._track_method(source)
    np.testing.assert_array_equal(fixed.cx, prescribed.cx)
    np.testing.assert_allclose(fixed.grid_snap_dx_m, prescribed.grid_snap_dx_m)


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_native_projected_extraction_and_ordinary_reader_provenance(tmp_path):
    import subprocess
    import sys

    path = fa_files(tmp_path, projection_latitude=-30.)[0]
    before = path.read_bytes()
    raw = single_fa_document(tmp_path, [path])
    raw["input"]["fa"]["profile"] = "arome_history"
    raw["input"]["fa"]["earth_radius_m"] = 6371229.
    raw["input"]["fa"]["field_metadata"] = {
        "CLSTEMPERATURE": {"units": "K", "kind": "continuous", "temporal_kind": "instantaneous"}}
    raw["variables"] = {"surface": {"names": ["CLSTEMPERATURE"]}}
    centre = track_at(500.01, -100.)
    raw["tracking"]["fixed_box"]["center"] = {
        "latitude": float(centre.lat[0]), "longitude": float(centre.lon[0])}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf)
    assert result.ok and path.read_bytes() == before
    products = {p["role"]: p["path"] for p in result.products}
    check = subprocess.run([sys.executable, "-c", """
import sys, json, numpy as np, xarray as xr
p = json.loads(sys.argv[1])
with xr.open_dataset(p['track']) as t:
    assert int(t.cx[0]) == 5 and int(t.cy[0]) == 3
    np.testing.assert_allclose(t.grid_snap_dx_m, 499.99, atol=1.e-5)
    np.testing.assert_allclose(t.grid_snap_dy_m, 100., atol=1.e-5)
    assert t.attrs['tracking_grid_lookup'] == 'fa_source_crs_native_axes_v1'
with xr.open_dataset(p['cart']) as d:
    np.testing.assert_array_equal(d.CLSTEMPERATURE[0],
        280. + 10*np.arange(1,6)[:,None] + np.arange(3,8))
assert 'frameit' not in sys.modules and 'falfilfa4py' not in sys.modules
""", json.dumps(products)], capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    assert provenance["tracking_summary"]["tracking_grid_lookup"] == NATIVE_LOOKUP


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_coupled_projected_source_retains_offsets_and_own_indices(tmp_path):
    import subprocess
    import sys

    atmosphere = atmospheric_file(tmp_path)
    # Prepare a compact independent NetCDF fixture, not a private/source product.
    with xr.open_dataset(atmosphere) as original:
        data = original.load()
    lon, lat = spherical_lambert(*np.meshgrid(data.ni, data.nj), 6371229.)
    data = data.assign_coords(longitude=(("nj", "ni"), lon, {"units": "degrees_east"}),
                               latitude=(("nj", "ni"), lat, {"units": "degrees_north"}))
    atmosphere = tmp_path / "projected-atmosphere.nc"
    data.to_netcdf(atmosphere)
    surface = fa_files(tmp_path, profile="surfex_history", projection_latitude=-30.)
    raw = document(tmp_path, atmosphere, surface)
    raw["input"]["sources"]["surfex"]["input"]["fa"]["earth_radius_m"] = 6371229.
    centre = track_at(500.01, -100.)
    raw["tracking"]["fixed_box"]["center"] = {
        "latitude": float(centre.lat[0]), "longitude": float(centre.lon[0])}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf)
    assert result.ok
    track = next(p["path"] for p in result.products if p["role"] == "track")
    check = subprocess.run([sys.executable, "-c", """
import sys, xarray as xr, numpy as np
with xr.open_dataset(sys.argv[1]) as t:
    assert int(t.atmosphere_cx[0]) == 3 and int(t.surfex_cx[0]) == 5
    assert t.surfex_grid_snap_dx_m.attrs['units'] == 'm'
    np.testing.assert_allclose(t.surfex_grid_snap_dx_m, 499.99, atol=1.e-5)
    assert t.surfex_grid_selected_latitude.attrs['source_id'] == 'surfex'
assert 'frameit' not in sys.modules and 'falfilfa4py' not in sys.modules
""", str(track)], capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    mapping = provenance["sources"]["surfex"]["grid_lookup"]
    assert mapping["method"] == NATIVE_LOOKUP
    assert mapping["offsets"][0] == "track.surfex_grid_snap_dx_m"
