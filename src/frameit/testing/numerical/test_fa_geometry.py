"""Independent spherical tangent-Lambert equations and labelled zone checks."""

import numpy as np
import pytest

from frameit.io.fa_geometry import fa_geometry, geometry_signature


def header(latitude=-30.):
    p = [0.] * 16
    p[0], p[1] = -1., abs(np.sin(np.deg2rad(latitude)))
    p[2:6] = np.deg2rad([50., latitude, 50., latitude])
    p[6:8] = [1000., 1000.]
    longitude, latitude = spherical_lambert(np.array([-5000., 5000.]),
                                           np.array([-3000., 3000.]), 6371229., latitude)
    p[12:16] = np.deg2rad([longitude[0], latitude[0], longitude[1], latitude[1]])
    return dict(KTYPTR=-5, KNLATI=9, KNXLON=13, PCODIL=0,
                KNLOPA=[0, 1, 2, 12, 2, 8, 1, 1], PSINLA=p)


def spherical_lambert(x, y, radius, latitude=-30.):
    # Snyder's spherical tangent-cone equations, evaluated independently from
    # FrameIt's pyproj CRS construction. The reference is 30 degrees south, 50 east.
    phi0, lam0 = np.deg2rad([latitude, 50.])
    n = np.sin(phi0)
    f = np.cos(phi0) * np.tan(np.pi / 4 + phi0 / 2)**n / n
    rho0 = radius * f / np.tan(np.pi / 4 + phi0 / 2)**n
    rho = np.sign(n) * np.hypot(x, rho0 - y)
    theta = np.arctan2(np.sign(n) * x, np.sign(n) * (rho0 - y))
    return np.rad2deg(lam0 + theta / n), np.rad2deg(
        2 * np.arctan((radius * f / rho)**(1 / n)) - np.pi / 2)


@pytest.mark.parametrize("latitude", [-30., 30.])
def test_tangent_lambert_asymmetric_ci_and_c_against_equations(latitude):
    h = header(latitude)
    options = {"subdomain": "CI", "earth_radius_m": 6371229.}
    ds = fa_geometry(h, options)
    assert dict(ds.sizes) == {"x": 11, "y": 7}
    np.testing.assert_array_equal(ds.source_i, np.arange(1, 12))
    np.testing.assert_array_equal(ds.source_j, np.arange(1, 8))
    xx, yy = np.meshgrid(np.arange(-5, 6) * 1000., np.arange(-3, 4) * 1000.)
    longitude, truth_latitude = spherical_lambert(xx, yy, options["earth_radius_m"], latitude)
    np.testing.assert_allclose(ds.longitude, longitude, atol=2.e-11, rtol=0)
    np.testing.assert_allclose(ds.latitude, truth_latitude, atol=2.e-11, rtol=0)
    assert float(ds.longitude[3, 5]) == pytest.approx(50.)
    assert float(ds.latitude[3, 5]) == pytest.approx(latitude)
    central = fa_geometry(h, {**options, "subdomain": "C"})
    np.testing.assert_allclose(central.longitude, ds.longitude[1:-1, 1:-1])
    np.testing.assert_allclose(central.latitude, ds.latitude[1:-1, 1:-1])
    with pytest.raises(ValueError, match="explicit input.fa.earth_radius_m"):
        fa_geometry(h, {"subdomain": "CI"})
    with pytest.raises(ValueError, match="contradicts encoded CI corners"):
        fa_geometry(h, {"subdomain": "CI", "earth_radius_m": 5000000.})


def test_geometry_signature_ignores_inherited_surface_vertical_header():
    options = {"subdomain": "CI", "earth_radius_m": 6371229.}
    h = header()
    assert geometry_signature(h, options) == geometry_signature(
        {**h, "KNIVER": 90, "PAHYBR": [0., 1.], "PBHYBR": [1., 0.], "PREFER": 101325.}, options)
    with pytest.raises(ValueError, match="CI bounds"):
        fa_geometry({**h, "KNXLON": 4}, options)


def test_geographic_lookup_matches_equivalent_longitudes_without_regridding():
    from frameit.tracking.geographic import nearest_grid_point

    latitude = np.array([-20., -19.])
    longitude = np.array([300., 301.])
    assert nearest_grid_point(latitude, longitude, -19., -59.) == (1, 1)
    lon, lat = np.meshgrid(longitude, latitude)
    assert nearest_grid_point(lat, lon, -19., -59.) == (1, 1)
