"""Repeated lookup retains the legacy squared-degree and storage-order contract."""

import numpy as np
import pytest
import xarray as xr

from frameit.tracking import geographic


def track(positions):
    return xr.Dataset({"lat": ("time", np.asarray(positions)[:, 0]),
                       "lon": ("time", np.asarray(positions)[:, 1])},
                      coords={"time": np.arange(len(positions))})


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("offset", [0., 180., 360.])
def test_repeated_lookup_matches_scan_without_full_grid_rescans(monkeypatch, dtype, offset):
    rng = np.random.default_rng(41)
    lat = (-20 + rng.normal(size=(31, 43))).astype(dtype)
    lon = (offset + rng.normal(size=lat.shape)).astype(dtype)
    lat[0, 0], lon[1, 0] = np.nan, np.inf
    lat[4, 5], lon[4, 5] = lat[8, 9], lon[8, 9]
    positions = np.column_stack((-20 + rng.normal(size=80), offset + rng.normal(size=80)))
    positions[:3] = [[lat[8, 9], lon[8, 9]], [-20., offset + 180.], [-20., offset - 359.9]]
    source = xr.Dataset({"latitude": (("y", "x"), lat),
                         "longitude": (("x", "y"), lon.T)})
    with np.errstate(invalid="ignore"):
        expected = [geographic.nearest_grid_point(source.latitude, source.longitude, *map(float, p),
                                                  axes=("y", "x")) for p in positions]

    def forbidden(*args, **kwargs):
        pytest.fail("Repeated ordinary queries must not rescan the entire source grid")

    monkeypatch.setattr(geographic, "nearest_grid_point", forbidden)
    result = geographic.locate_track(track(positions), source, axes=("y", "x"))
    np.testing.assert_array_equal(np.column_stack((result.cy, result.cx)), expected)
    xr.testing.assert_identical(result.lat, track(positions).lat)


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_repeated_lookup_exact_ties_use_first_storage_index(dtype):
    source = xr.Dataset({"latitude": (("y", "x"), np.array([[0., 0.], [0., 0.]], dtype)),
                         "longitude": (("y", "x"), np.array([[179., -179.], [179., -179.]], dtype))})
    result = geographic.locate_track(track([[0., 180.], [0., -180.], [0., 540.]]), source)
    np.testing.assert_array_equal(result.cy, [0, 0, 0])
    np.testing.assert_array_equal(result.cx, [0, 0, 0])


def test_indexed_lookup_retains_reference_failures_and_extreme_query_behavior():
    source = xr.Dataset({"latitude": (("y", "x"), [[0., 0.], [1., 1.]]),
                         "longitude": (("y", "x"), [[10., 11.], [10., 11.]])})
    for query in ([0., np.nan], [np.inf, 0.]):
        with pytest.raises(ValueError, match="no finite candidate"):
            geographic.locate_track(track([[0., 10.], query]), source)
    empty = source.assign(latitude=xr.full_like(source.latitude, np.nan))
    with pytest.raises(ValueError, match="no finite candidate"):
        geographic.locate_track(track([[0., 10.], [1., 11.]]), empty)
    positions = [[0., 1e20], [0., -1e20]]
    expected = [geographic.nearest_grid_point(source.latitude, source.longitude, *p) for p in positions]
    actual = geographic.locate_track(track(positions), source)
    np.testing.assert_array_equal(np.column_stack((actual.cy, actual.cx)), expected)


def test_coupled_lookup_reuses_index_after_containment_check(monkeypatch):
    from types import SimpleNamespace

    from frameit.core.coupled import _mapped_track

    source = xr.Dataset({"latitude": (("y", "x"), [[0., 0.], [1., 1.]]),
                         "longitude": (("y", "x"), [[10., 11.], [10., 11.]])})
    conf = SimpleNamespace(name_latitude="latitude", name_longitude="longitude", name_time_dim="time",
                           name_lat_dim="y", name_lon_dim="x")

    def forbidden(*args, **kwargs):
        pytest.fail("Coupled repeated lookup must share the indexed path")

    monkeypatch.setattr(geographic, "nearest_grid_point", forbidden)
    result = _mapped_track(track([[.2, 10.1], [.9, 10.8]]), source, conf)
    np.testing.assert_array_equal(result.cy, [0, 1])
    np.testing.assert_array_equal(result.cx, [0, 1])
    with pytest.raises(ValueError, match="outside"):
        _mapped_track(track([[.2, 10.1], [20., 10.8]]), source, conf)
