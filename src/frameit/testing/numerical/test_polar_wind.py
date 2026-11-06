"""Independent geodesic geometry and polar wind numerical oracles."""

from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
from pyproj import Geod

from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf
from frameit.processing.derived.wind import (
    normalize_winds,
    polar_wind_components,
)
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.processing.polar.polar_proj import polar_project
from frameit.processing.tracking.postprocess import enrich_track_with_kinematics
from frameit.tracking.FixedBox_Tracker import FixedBoxTracker
from frameit.tracking.PrescribedTrack_Tracker import PrescribedTrack


def conf(**overrides):
    values = dict(
        atm_model="AROME", velocity_aliases={"u_velocity": "u", "v_velocity": "v"},
        tracking_method="prescribed_track", name_longitude="longitude",
        name_latitude="latitude", compute_polar_proj=True, x_boxsize_km=80,
        y_boxsize_km=80, radial_resolution=5000, azimuthal_resolution=10,
        polar_variables={"heightAboveGround": {"variables": ["u", "v"]}},
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def reference_box(lat=-20.0, lon=0.0):
    return xr.Dataset(
        coords={"time": [0, 1], "x_box": [0], "y_box": [0],
                "longitude": (("y_box", "x_box"), [[lon]]),
                "latitude": (("y_box", "x_box"), [[lat]])}
    )


def grid(radius, angles, mode="prescribed_track", ellps="WGS84"):
    return PolarLonLatGrid(
        r_km=np.asarray(radius), theta_deg=np.asarray(angles), tracking_method=mode,
        time_dim="time", lon_name="longitude", lat_name="latitude", ellps=ellps,
    )


def test_published_karney_direct_problem():
    # Karney (2013), Table 2: numerical values rounded in the publication.
    result = grid([10000], [30]).build(reference_box(40))
    np.testing.assert_allclose(result.lat, 41.79331020506, atol=1e-8, rtol=0)
    np.testing.assert_allclose(result.lon, 137.84490004377, atol=1e-8, rtol=0)
    np.testing.assert_allclose(
        np.rad2deg(result.radial_bearing), 149.09016931807, atol=1e-8, rtol=0
    )


@pytest.mark.parametrize("latitude", [-60, -20, 0, 20, 60])
def test_geodesic_roundtrip_dateline_and_origin(latitude):
    result = grid([0, 1, 100, 500], [0, 45, 90, 180, 270]).build(
        reference_box(latitude, 179.5)
    )
    geod = Geod(ellps="WGS84")
    lon, lat = result.lon.values[0, 1:], result.lat.values[0, 1:]
    launch, back, distance = geod.inv(
        np.full(lon.shape, 179.5), np.full(lon.shape, latitude), lon, lat
    )
    np.testing.assert_allclose(distance, np.broadcast_to([[1000], [100000], [500000]],
                                                       distance.shape), atol=1e-6, rtol=0)
    difference = (launch - result.theta_deg.values + 180) % 360 - 180
    np.testing.assert_allclose(difference, 0, atol=1e-8)
    np.testing.assert_allclose(
        result.radial_bearing.values[0, 1:], np.deg2rad((back + 180) % 360), atol=1e-12
    )
    assert np.isnan(result.radial_bearing.isel(rr=0)).all()


@pytest.mark.parametrize("latitude,leakage", [(-20, 1.424027906), (60, -6.703955887)])
def test_terminal_rotation_not_launch_rotation(latitude, leakage):
    result = grid([0, 500], [90]).build(reference_box(latitude))
    _, back, _ = Geod(ellps="WGS84").inv(
        0, latitude, float(result.lon[0, 1, 0]), float(result.lat[0, 1, 0])
    )
    angle = np.deg2rad(back + 180)
    u = xr.full_like(result.radial_bearing, 50 * np.cos(angle))
    v = xr.full_like(result.radial_bearing, -50 * np.sin(angle))
    # full_like copies bearing metadata; these fixtures are velocities.
    u.attrs = {"units": "m s-1"}
    v.attrs = {"units": "m s-1"}
    radial, tangential = polar_wind_components(u, v, result.radial_bearing)
    np.testing.assert_allclose(radial.isel(rr=1), 0, atol=1e-10)
    np.testing.assert_allclose(tangential.isel(rr=1), 50, atol=1e-10)
    np.testing.assert_allclose(u.isel(rr=1), leakage, atol=1e-8)
    assert np.isnan(radial.isel(rr=0)).all()


def test_cardinal_components_vertical_broadcast_and_alignment():
    bearing = xr.DataArray(np.deg2rad([0, 90, 180, 270]), dims="theta")
    u = xr.DataArray(np.ones((2, 4)), dims=("level", "theta"), coords={"level": [1, 2]})
    v = u * 0
    radial, tangential = polar_wind_components(u, v, bearing)
    np.testing.assert_allclose(radial[0], [0, 1, 0, -1], atol=1e-10)
    np.testing.assert_allclose(tangential[0], [1, 0, -1, 0], atol=1e-10)
    outward, cross_flow = polar_wind_components(np.sin(bearing), np.cos(bearing), bearing)
    np.testing.assert_allclose(outward, 1, atol=1e-10)
    np.testing.assert_allclose(cross_flow, 0, atol=1e-10)
    with pytest.raises(ValueError):
        polar_wind_components(u, v.assign_coords(level=[2, 3]), bearing)
    with pytest.raises(ValueError, match="identical dimensions"):
        polar_wind_components(u, v.rename(theta="staggered_theta"), bearing)


def test_continuous_origin_fixed_freeze_and_earth_metadata():
    box = reference_box()
    track = xr.Dataset({"lon": ("time", [0.001, 0.002]),
                        "lat": ("time", [-20.001, -20.002])}, coords={"time": [0, 1]})
    moving = grid([0, 10], [0, 90]).build(box, track=track)
    np.testing.assert_allclose(moving.lon[:, 0, 0], track.lon)
    assert np.all(moving.center_grid_offset_m > 0)
    fixed = grid([0, 10], [0, 90], "fixed_box", "sphere").build(box, track=track)
    np.testing.assert_allclose(fixed.center_lon, 0.001)
    np.testing.assert_allclose(fixed.lon[0], fixed.lon[1])
    assert fixed.attrs["ellps"] == "sphere"
    assert fixed.attrs["center_definition"] == "continuous_track"


@pytest.mark.parametrize("nt", [1, 2])
@pytest.mark.parametrize("model", ["AROME", "MNH"])
@pytest.mark.parametrize("method", ["fixed_box", "prescribed_track"])
def test_supplied_centres_survive_tracker_and_postprocessing(tmp_path, model, method, nt):
    times = np.array(["2024-01-01T00", "2024-01-01T06"], dtype="datetime64[ns]")[:nt]
    expected_lat = np.array([-20.01, -20.02])[:nt]
    expected_lon = np.array([0.01, 0.02])[:nt]
    if model == "AROME":
        source = xr.Dataset(coords={"time": times, "latitude": [-21., -20., -19.],
                                    "longitude": [0., 1., 2.]})
    else:
        lon, lat = np.meshgrid([0., 1., 2.], [-21., -20., -19.])
        source = xr.Dataset(coords={"time": times, "ni": [0, 1, 2], "nj": [0, 1, 2],
                                    "longitude": (("nj", "ni"), lon),
                                    "latitude": (("nj", "ni"), lat)})
    if method == "prescribed_track":
        path = tmp_path / "supplied-track.nc"
        xr.Dataset({"latitude": ("time", expected_lat), "longitude": ("time", expected_lon)},
                   coords={"time": times}).to_netcdf(path)
        tracker = PrescribedTrack({}, path, atm_model=model)
    else:
        tracker = FixedBoxTracker({}, [expected_lat[0], expected_lon[0]], atm_model=model)
        expected_lat[:] = expected_lat[0]
        expected_lon[:] = expected_lon[0]
    track = tracker({method: {"surface": source}})
    track = enrich_track_with_kinematics(track, ds_flat=source, conf=conf(tracking_method=method))
    np.testing.assert_allclose(track.lon, expected_lon)
    np.testing.assert_allclose(track.lat, expected_lat)
    np.testing.assert_array_equal(track.cx, np.zeros(nt))
    np.testing.assert_array_equal(track.cy, np.ones(nt))
    geometry = grid([0, 10], [0, 90], method).build(source, track=track)
    np.testing.assert_allclose(geometry.lon[:, 0, 0], expected_lon)
    np.testing.assert_allclose(geometry.lat[:, 0, 0], expected_lat)


@pytest.mark.parametrize("nt", [1, 2])
@pytest.mark.parametrize("layout", ["rectilinear", "curvilinear", "time_curvilinear"])
def test_index_track_coordinates_do_not_require_motion(nt, layout):
    times = np.array(["2024-01-01T00", "2024-01-01T06"], dtype="datetime64[ns]")[:nt]
    source = xr.Dataset(coords={"time": times, "latitude": [-21., -20., -19.],
                                "longitude": [50., 51., 52.]})
    if layout != "rectilinear":
        lon, lat = np.meshgrid(source.longitude.values, source.latitude.values)
        source = xr.Dataset(coords={"time": times, "longitude": (("y", "x"), lon),
                                    "latitude": (("y", "x"), lat)})
        if layout == "time_curvilinear":
            source = source.assign_coords({
                name: source[name].expand_dims(time=times) for name in ("longitude", "latitude")})
    track = xr.Dataset({"cx": ("time", [1, 2][:nt]), "cy": ("time", [1, 2][:nt])},
                       coords={"time": times})
    result = enrich_track_with_kinematics(track, ds_flat=source,
                                         conf=conf(tracking_method="wind_pressure"))
    np.testing.assert_array_equal(result.lon, [51., 52.][:nt])
    np.testing.assert_array_equal(result.lat, [-20., -19.][:nt])
    assert result.lon.dims == result.lat.dims == ("time",)
    assert result.lon.attrs["units"] == "degrees_east"
    assert result.lat.attrs["units"] == "degrees_north"
    assert "lon" not in track and "lat" not in track
    if nt == 1:
        for name in ("heading_deg", "dist", "speed"):
            assert result[name].dims == ("time",) and np.isnan(result[name]).all()
    else:
        azimuth, _, distance = Geod(ellps="WGS84").inv(51., -20., 52., -19.)
        np.testing.assert_allclose(result.heading_deg, azimuth % 360)
        np.testing.assert_allclose(result.dist, distance / 1000)
        np.testing.assert_allclose(result.speed, distance / (6 * 3600))


def test_grid_relative_rotation_units_and_missing_metadata_contract():
    ds = xr.Dataset({"u": ("x", [36.0]), "v": ("x", [0.0])},
                    coords={"grid_rotation": ("x", [np.pi / 2])})
    for name in ("u", "v"):
        ds[name].attrs.update(units="km/h", GRIB_uvRelativeToGrid=1)
    ds.grid_rotation.attrs["units"] = "rad"
    settings = conf(wind_reference_frame="grid")
    rotated = normalize_winds(ds, settings, "heightAboveGround")
    np.testing.assert_allclose(rotated.u, 0, atol=1e-10)
    np.testing.assert_allclose(rotated.v, 10, atol=1e-10)
    assert rotated.u.attrs["GRIB_uvRelativeToGrid"] == 0
    assert rotated.u.attrs["units"] == "m s-1"
    with pytest.raises(ValueError, match="named coordinate"):
        normalize_winds(ds.drop_vars("grid_rotation"), settings, "heightAboveGround")
    with pytest.raises(ValueError, match="Conflicting wind reference"):
        inconsistent = ds.copy(deep=True)
        inconsistent.v.attrs["GRIB_uvRelativeToGrid"] = 0
        normalize_winds(inconsistent, settings, "heightAboveGround")


def vortex_source(n):
    axis = np.linspace(-0.6, 0.6, n)
    lon, lat = np.meshgrid(axis, axis - 20)
    geod = Geod(ellps="WGS84")
    _, back, r = geod.inv(np.zeros_like(lon), np.full_like(lat, -20), lon, lat)
    angle = np.deg2rad(back + 180)
    speed = 50 * r / 40000 * np.exp((1 - (r / 40000) ** 2) / 2)
    u, v = speed * np.cos(angle), -speed * np.sin(angle)
    indices = np.arange(n) - n // 2
    ds = xr.Dataset(
        {"u": (("time", "heightAboveGround", "y_box", "x_box"), u[None, None]),
         "v": (("time", "heightAboveGround", "y_box", "x_box"), v[None, None])},
        coords={"time": [0], "heightAboveGround": [2000], "x_box": indices,
                "y_box": indices, "longitude": (("y_box", "x_box"), lon),
                "latitude": (("y_box", "x_box"), lat)},
    )
    for name in ("u", "v"):
        ds[name].attrs.update(units="m s-1", GRIB_uvRelativeToGrid=0)
    return ds


def test_real_xesmf_geodesic_vortex_and_speed_only(tmp_path):
    pytest.importorskip("xesmf")
    errors = []
    radial_errors = []
    for n in [17, 33]:
        source = vortex_source(n)
        result, _ = polar_project({"heightAboveGround": source}, conf=conf())
        ds = result["heightAboveGround"]
        r = ds.rr.values * 1000
        truth = 50 * r / 40000 * np.exp((1 - (r / 40000) ** 2) / 2)
        errors.append(float(np.sqrt(((ds.vtan.isel(rr=slice(1, None)) -
                                     xr.DataArray(truth[1:], dims="rr",
                                                  coords={"rr": ds.rr[1:]})) ** 2).mean())))
        radial_errors.append(float(np.sqrt((ds.vrad.isel(rr=slice(1, None)) ** 2).mean())))
        assert np.isnan(ds.vrad.isel(rr=0)).all()
        assert np.isfinite(ds.wind_speed.isel(rr=0)).all()
        assert ds.radial_bearing.dims == ("time", "rr", "theta")
        assert ds.u.attrs["units"] == "m s-1"
        speed_conf = conf(polar_variables={"heightAboveGround": {"variables": ["wind_speed"]}})
        speed_only, _ = polar_project({"heightAboveGround": source}, conf=speed_conf)
        np.testing.assert_allclose(speed_only["heightAboveGround"].wind_speed, ds.wind_speed)
        physical_fields = {name for name, value in speed_only["heightAboveGround"].data_vars.items()
                           if value.attrs.get("frameit_role") != "interpolation_quality"}
        assert physical_fields == {"wind_speed"}
        assert not any(name.startswith(("u_", "v_")) for name in
                       speed_only["heightAboveGround"].data_vars)
        path = tmp_path / f"polar-{n}.nc"
        write_dataset_netcdf(
            ds, path, product_type="polar",
            metadata=ExportMetadata(
                "synthetic", "vortex", "geodesic wind test", "test", "analytic"
            ),
        )
        with xr.open_dataset(path) as saved:
            assert saved.radial_bearing.attrs["units"] == "rad"
            np.testing.assert_allclose(saved.center_lat, -20)
    assert errors[1] < 0.4 * errors[0]
    assert radial_errors[1] < 0.5 * radial_errors[0]
