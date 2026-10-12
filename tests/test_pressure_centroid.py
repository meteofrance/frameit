from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from frameit.core.settings_class import SimulationConfig
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.processing.tracking.postprocess import enrich_track_with_kinematics
from frameit.tracking import pressure_centroid as pc
from frameit.tracking.PressureCentroid_Tracker import PressureCentroidTracker
from frameit.tracking.tracker_core import build_tracker_from_config


def vortex(center=(60.0, -20.0)):
    lon, lat = np.meshgrid(np.linspace(54, 66, 241), np.linspace(-26, -14, 241))
    _, back, distance = pc.GEOD.inv(np.full(lon.shape, center[0]),
                                   np.full(lat.shape, center[1]), lon, lat)
    theta = np.deg2rad((back + 180) % 360)
    r = distance / 1000
    speed = 40 * (r / 50) * np.exp(1 - r / 50)
    return (lon, lat, 800 - 40 * np.exp(-(r / 50) ** 2),
            speed * np.cos(theta), -speed * np.sin(theta))


def test_vertical_interpolation_and_missing_brackets():
    rec = dict(z=np.array([3000, 1000])[:, None, None],
               u=np.array([30, 10])[:, None, None],
               v=np.array([6, 2])[:, None, None], pressure_levels=np.array([700, 900]))
    result = pc.interpolate_to_height(rec)
    assert result["u"].item() == 20
    assert result["v"].item() == 4
    assert result["p"].item() == pytest.approx(np.sqrt(700 * 900))
    assert np.isnan(pc.interpolate_to_height(rec, height=4000)["p"]).all()


@pytest.mark.parametrize("latitude", [-20, 20])
def test_r80_hemisphere_and_translation(latitude):
    center = (60, latitude)
    translation = (7, -3)

    def component(lon, lat, which):
        _, back, distance = pc.GEOD.inv(np.full(lon.shape, center[0]),
                                       np.full(lat.shape, center[1]), lon, lat)
        theta = np.deg2rad((back + 180) % 360)
        r = distance / 1000
        speed = 40 * r / 50 * np.exp(1 - r / 50)
        sign = 1 if latitude < 0 else -1
        return (sign * speed * np.cos(theta) + translation[0] if which == 0
                else -sign * speed * np.sin(theta) + translation[1])

    r80, radii, profile = pc.calculate_r80(
        center, lambda x, y: component(x, y, 0), lambda x, y: component(x, y, 1), translation)
    assert radii[np.argmax(profile)] == 50
    assert r80 == pytest.approx(23.6, abs=.2)
    with pytest.raises(ValueError, match="No positive"):
        pc.calculate_r80(center, lambda x, y: np.zeros_like(x),
                         lambda x, y: np.zeros_like(x), (0, 0))


def test_wrapped_descending_interpolator_and_ring_failure():
    lon, lat = np.meshgrid([181., 180., 179.], [1., 0., -1.])
    sample = pc.make_interpolator(lon, lat, lon + lat)
    assert sample(np.array([-179.5]), np.array([.5]))[0] == pytest.approx(181)
    with pytest.raises(ValueError, match="500-km"):
        pc.reference_pressure((180, 0), sample)


@pytest.mark.parametrize("kwargs", [dict(motion_solver="unknown"), dict(dr_km=0),
                                    dict(tolerance_m=np.nan), dict(motion_relaxation=1.1),
                                    dict(max_iterations=1.5), dict(dtheta=180)])
def test_invalid_options(kwargs):
    with pytest.raises(ValueError):
        pc.CentroidOptions(**kwargs)


def test_factory_and_preset():
    conf = SimulationConfig.from_yaml_with_model_preset(
        "example/config_file/conf_pressure_centroid.yml")
    tracker = build_tracker_from_config(conf)
    assert isinstance(tracker, PressureCentroidTracker)
    assert tracker.half_search == 40
    assert conf.requested_variables_tracker["pressure_centroid"]["isobaricInhPa"][
        "level_selection"] == "all"
    conf.atm_model = "MNH"
    with pytest.raises(ValueError, match="AROME"):
        build_tracker_from_config(conf)


def test_centroid_invalid_integrals():
    lon, lat, p, _, _ = vortex()
    index = pc.LocalGridIndex(lon, lat)
    constant = np.full_like(p, 800.)
    with pytest.raises(ValueError, match="No positive pressure deficit"):
        pc.centroid_iteration((60, -20), 100, constant,
                              pc.make_interpolator(lon, lat, constant), index)
    with pytest.raises(ValueError, match="Too few finite"):
        pc.centroid_iteration((60, -20), .1, p, pc.make_interpolator(lon, lat, p), index)


def test_symmetric_centroid():
    lon, lat, p, _, _ = vortex()
    center, _ = pc.centroid_iteration((60.02, -20.01), 100, p,
                                      pc.make_interpolator(lon, lat, p),
                                      pc.LocalGridIndex(lon, lat))
    assert pc.GEOD.inv(*center, 60, -20)[2] < 100


def test_motion_irregular_times():
    records = [{"time": np.datetime64("2022-01-01") + np.timedelta64(s, "s")}
               for s in (0, 100, 300)]
    centers = [pc.move_toward((0, 0), (1, 0), s / 300) for s in (0, 100, 300)]
    vectors = pc.motion_vectors(records, centers)
    np.testing.assert_allclose(vectors, np.tile(vectors[0], (3, 1)), atol=1e-8)
    with pytest.raises(ValueError, match="strictly increasing"):
        pc.motion_vectors(records[::-1], centers)


def test_full_residual_not_relaxed_step(monkeypatch):
    records = [dict(time=np.datetime64("2022-01-01") + np.timedelta64(k, "h"), guess=(60, -20))
               for k in range(2)]

    def evaluate(rec, center, velocity, options):
        lon, lat, _ = pc.GEOD.fwd(*center, 90, 1000)
        return (lon, lat), 25, 50, 800, [(25, 50, 1000)]

    monkeypatch.setattr(pc, "adaptive_centroid", evaluate)
    with pytest.raises(ValueError, match="unrelaxed residual 1000"):
        pc.solve_motion_centroids(records, pc.CentroidOptions(
            motion_solver="fixed", motion_relaxation=.01, max_motion_iterations=2))


def test_aitken_backtracks_and_returns_current_centres(monkeypatch):
    records = [dict(time=np.datetime64("2022-01-01") + np.timedelta64(k, "h"), guess=(60, -20))
               for k in range(2)]
    target = pc.move_toward((60, -20), (61, -20), .01)
    calls = []

    def evaluate(rec, center, velocity, options):
        distance = pc.GEOD.inv(60, -20, *center)[2]
        calls.append(distance)
        if distance > 800:
            raise ValueError("outside domain")
        return target, 25, 50, 800, [(25, 50, 0)]

    monkeypatch.setattr(pc, "adaptive_centroid", evaluate)
    result = pc.solve_motion_centroids(records, pc.CentroidOptions(motion_tolerance_m=790))
    assert any(d > 800 for d in calls)
    assert pc.GEOD.inv(60, -20, *result[0])[2] == pytest.approx(
        .25 * pc.GEOD.inv(60, -20, *target)[2], abs=1e-6)
    assert records[0]["motion_residual_m"] < 790


def test_adapter_and_continuous_outputs(tmp_path):
    lon, lat, pressure, u, v = vortex()
    time = np.array(["2022-01-01T00", "2022-01-01T06"], dtype="datetime64[ns]")
    dims = ("time", "isobaricInhPa", "latitude", "longitude")
    ds = xr.Dataset(coords=dict(time=time, isobaricInhPa=[900., 700.],
                                latitude=lat[:, 0], longitude=lon[0]))
    for name, value in (("u", u), ("v", v)):
        ds[name] = xr.DataArray(np.broadcast_to(value, (2, 2, *value.shape)), dims=dims,
                                attrs={"units": "m s**-1", "GRIB_uvRelativeToGrid": 0})
    heights = np.array([1000., 3000.])[None, :, None, None]
    # Pressure deficit is encoded by the pressure-level heights, not MSLP.
    offset = 2000 - (1000 + (np.log(900) - np.log(pressure))
                     / (np.log(900) - np.log(700)) * 2000)
    ds["z"] = xr.DataArray(np.broadcast_to((heights + offset) * pc.G0,
                                           (2, 2, *pressure.shape)), dims=dims,
                              attrs={"units": "m**2 s**-2"})
    for name, value, units in (("prmsl", pressure, "hPa"), ("u10", u, "m s**-1"),
                               ("v10", v, "m s**-1")):
        ds[name] = xr.DataArray(np.broadcast_to(value, (2, *value.shape)),
                                dims=("time", "latitude", "longitude"),
                                attrs={"units": units, "GRIB_uvRelativeToGrid": 0})
    tracker = PressureCentroidTracker(dict(mslp="prmsl", u10m="u10", v10m="v10", geopot="z"), 5000)
    invalid = ds.copy(deep=False)
    invalid["u"] = invalid.u.assign_attrs(GRIB_uvRelativeToGrid=1)
    with pytest.raises(ValueError, match="earth-relative"):
        tracker({"pressure_centroid": {"all": invalid}})
    track = tracker({"pressure_centroid": {"all": ds}})
    assert track.cx.dtype.kind == "i"
    assert np.max(track.motion_residual_m) < 250
    assert np.max(track.radius_km) == pytest.approx(2 * np.max(track.r80_km))
    conf = SimpleNamespace(tracking_method="pressure_centroid", name_longitude="longitude",
                           name_latitude="latitude")
    enriched = enrich_track_with_kinematics(track, ds_flat=ds, conf=conf)
    xr.testing.assert_equal(enriched.lon, track.lon)
    grid = PolarLonLatGrid(r_km=np.array([0., 10.]), theta_deg=np.array([0., 90.]),
                           tracking_method="pressure_centroid", time_dim="time",
                           lon_name="longitude", lat_name="latitude")
    polar = grid.build(ds, track=track)
    np.testing.assert_allclose(polar.lon.isel(rr=0, theta_deg=0), track.lon)
    path = tmp_path / "track.nc"
    enriched.to_netcdf(path)
    with xr.open_dataset(path) as exported:
        np.testing.assert_allclose(exported.lon, track.lon)
        assert exported.attrs["pressure_centroid_motion_solver"] == "aitken"
