"""Sampling geometry, periodic topology, allocation limits and plotting closure."""

from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.settings_class import SimulationConfig
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.processing.polar.polar_utils import close_theta_for_plot, finalize_polar_output


def settings(**overrides):
    values = dict(
        tracking_method="fixed_box", name_longitude="longitude", name_latitude="latitude",
        x_boxsize_km=200, y_boxsize_km=200, radial_resolution=3000,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def box(times=2):
    return xr.Dataset(coords={
        "time": np.arange(times), "x_box": [0], "y_box": [0],
        "longitude": (("y_box", "x_box"), [[179.5]]),
        "latitude": (("y_box", "x_box"), [[-20.]]),
    })


def configured_grid(**overrides):
    return PolarLonLatGrid.from_conf(settings(**overrides))


@pytest.mark.parametrize("step,count", [(7, 52), (10, 36), (0.5, 720)])
def test_requested_step_has_uniform_wrap_interval(step, count):
    grid = configured_grid(azimuthal_resolution=step)
    ds = finalize_polar_output(grid.build(box()))
    assert ds.sizes["theta"] == count
    gaps = np.diff(np.r_[ds.theta.values, 2 * np.pi])
    np.testing.assert_allclose(gaps, 2 * np.pi / count, atol=1e-12, rtol=0)
    assert ds.theta[-1] < 2 * np.pi
    assert ds.attrs["theta_closed"] is False
    assert ds.attrs["requested_azimuthal_resolution_deg"] == step
    assert ds.attrs["effective_azimuthal_resolution_deg"] == 360 / count
    assert ds.attrs["theta_topology"] == "uniform_periodic"
    assert ds.rr.attrs["units"] == "km"


def test_auto_sampling_matches_outer_ring_distance_without_degree_floor():
    grid = configured_grid(x_boxsize_km=500, y_boxsize_km=500, radial_resolution=1000)
    assert grid.theta_deg.size == int(np.ceil(2 * np.pi * 250))
    ds = grid.build(box())
    assert ds.attrs["effective_azimuthal_resolution_deg"] < 1
    assert ds.attrs["angular_sampling_source"] == "automatic_outer_ring_spacing"
    assert "requested_azimuthal_resolution_deg" not in ds.attrs
    assert np.max(ds.max_azimuthal_spacing_m.values) <= 1000
    np.testing.assert_allclose(ds.max_azimuthal_spacing_m.isel(rr=0), 0)


def test_explicit_count_and_serialized_configuration(tmp_path):
    config = SimulationConfig(
        simulation_name="sampling", file_name_prefix="", file_name="synthetic",
        file_name_suffix="", file_type="grib", ocean_model="", wave_model="", comment="",
        atm_model="AROME", simulation_output_dir=str(tmp_path), frameit_output_dir=str(tmp_path),
        compute_polar_proj=True, resolution=3000, radial_resolution=3000,
        x_boxsize_km=200, y_boxsize_km=200, polar_n_theta=64,
    )
    assert config.azimuthal_resolution is None
    copied = SimulationConfig.from_dict(config.to_dict())
    assert copied.polar_n_theta == 64
    assert copied.polar_max_points == 2_000_000
    path = tmp_path / "sampling.yml"
    path.write_text(yaml.safe_dump(config.to_dict()))
    assert SimulationConfig.from_yaml(path).polar_n_theta == 64
    grid = configured_grid(polar_n_theta=64)
    assert grid.theta_deg.size == 64
    configured_grid(polar_n_theta=52, azimuthal_resolution=7)
    with pytest.raises(ValueError, match="conflicts"):
        configured_grid(polar_n_theta=64, azimuthal_resolution=10)
    with pytest.raises(ValueError, match="conflicts"):
        SimulationConfig.from_dict({**config.to_dict(), "azimuthal_resolution": 10})


@pytest.mark.parametrize("options", [
    {"polar_n_theta": 2}, {"polar_n_theta": True}, {"polar_n_theta": 3.5},
    {"azimuthal_resolution": 0}, {"azimuthal_resolution": -7},
    {"azimuthal_resolution": np.nan}, {"azimuthal_resolution": np.inf},
    {"azimuthal_resolution": True}, {"azimuthal_resolution": 180},
    {"polar_max_points": 0}, {"polar_max_points": True}, {"polar_max_points": 2.5},
    {"radial_resolution": np.nan}, {"radial_resolution": np.inf},
    {"x_boxsize_km": np.inf}, {"y_boxsize_km": -200},
])
def test_invalid_sampling_configuration(options):
    with pytest.raises(ValueError):
        configured_grid(**options)


def test_point_budget_before_mesh_allocation_and_across_times():
    with pytest.raises(ValueError, match="polar_max_points"):
        configured_grid(polar_n_theta=36, polar_max_points=1000)
    grid = configured_grid(polar_n_theta=36, polar_max_points=2000)
    with pytest.raises(ValueError, match="polar_max_points"):
        grid.build(box(times=2))
    with pytest.raises(ValueError, match="polar_max_points"):
        configured_grid(azimuthal_resolution=1e-300)
    with pytest.raises(ValueError, match="polar_max_points"):
        configured_grid(radial_resolution=1e-300)
    with pytest.raises(ValueError, match="polar_max_points"):
        PolarLonLatGrid(r_km=np.arange(100), theta_deg=np.arange(360),
                       tracking_method="fixed_box", time_dim="time", lon_name="longitude",
                       lat_name="latitude", max_target_points=1000)


@pytest.mark.parametrize("radii,angles", [
    ([-1, 0], [0, 90]), ([0, np.nan], [0, 90]), ([0, np.inf], [0, 90]),
    ([0, 1, 1], [0, 90]), ([1, 0], [0, 90]), ([], [0, 90]),
    ([0, 1], [0, 360]), ([0, 1], [90, 0]), ([0, 1], [0, 0]),
    ([0, 1], [0, np.nan]), ([0, 1], [0, np.inf]), ([0, 1], [-1, 90]),
    ([0, 1], []), ([[0, 1]], [0, 90]), ([0, 1], [[0, 90]]), ([0, 1e308], [0, 90]),
])
def test_invalid_direct_axes(radii, angles):
    with pytest.raises(ValueError):
        PolarLonLatGrid(r_km=radii, theta_deg=angles, tracking_method="fixed_box",
                       time_dim="time", lon_name="longitude", lat_name="latitude")


def test_actual_radial_intervals_and_coordinate_aware_derivative():
    ds = finalize_polar_output(configured_grid(polar_n_theta=36).build(box()))
    np.testing.assert_array_equal(ds.rr[-3:], [96, 99, 100])
    np.testing.assert_allclose(ds.radial_spacing_km[:-1], np.diff(ds.rr))
    assert np.isnan(ds.radial_spacing_km[-1])
    assert ds.attrs["radial_spacing_uniform"] is False
    q = ds.rr ** 2
    np.testing.assert_allclose(q.differentiate("rr", edge_order=2), 2 * ds.rr, atol=1e-12)


def test_plotting_closure_idempotence_auxiliaries_and_analysis_reopening():
    ds = finalize_polar_output(configured_grid(polar_n_theta=36).build(box()))
    ds["signal"] = np.cos(ds.theta).broadcast_like(ds.lon)
    ds["time_only"] = ("time", [1., 2.])
    original = ds.copy(deep=True)
    xr.testing.assert_identical(finalize_polar_output(ds), ds)
    closed = close_theta_for_plot(ds)
    assert closed.sizes["theta"] == 37
    assert closed.time_only.dims == ("time",)
    xr.testing.assert_identical(close_theta_for_plot(closed), closed)
    xr.testing.assert_identical(ds, original)
    xr.testing.assert_identical(finalize_polar_output(closed), ds)
    for name in ["radial_bearing", "lon", "lat", "signal"]:
        np.testing.assert_allclose(closed[name].isel(theta=0), closed[name].isel(theta=-1),
                                   equal_nan=True)
    assert closed.theta_deg[-1] == 360
    assert closed.theta[-1] == 2 * np.pi


def test_inconsistent_closed_values_and_repeated_endpoint_are_rejected():
    ds = finalize_polar_output(configured_grid(polar_n_theta=36).build(box()))
    ds["signal"] = np.cos(ds.theta)
    closed = close_theta_for_plot(ds)
    inconsistent = closed.copy(deep=True)
    inconsistent["signal"][-1] = 42
    for helper in (close_theta_for_plot, finalize_polar_output):
        with pytest.raises(ValueError, match="does not duplicate"):
            helper(inconsistent)
    integer_labels = closed.assign(label=("theta", np.full(37, 10**12, dtype=np.int64)))
    integer_labels["label"][-1] += 1
    with pytest.raises(ValueError, match="does not duplicate"):
        close_theta_for_plot(integer_labels)
    repeated = xr.concat([closed, closed.isel(theta=slice(-1, None))], dim="theta")
    with pytest.raises(ValueError, match="unique"):
        close_theta_for_plot(repeated)
    # A stale attribute does not override actual open/closed coordinates.
    stale = ds.assign_attrs(theta_closed=True)
    assert close_theta_for_plot(stale).sizes["theta"] == 37
    closed.attrs["theta_closed"] = False
    assert close_theta_for_plot(closed).sizes["theta"] == 37


def test_directional_samples_are_labelled_truthfully():
    ds = PolarLonLatGrid(r_km=[0, 10], theta_deg=[0, 90, 190], tracking_method="fixed_box",
                        time_dim="time", lon_name="longitude", lat_name="latitude").build(box())
    ds = finalize_polar_output(ds)
    assert ds.attrs["theta_topology"] == "directional_samples"
    assert "effective_azimuthal_resolution_deg" not in ds.attrs
