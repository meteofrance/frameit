"""Independent sparse-weight oracles and actual ESMF coverage/missing-data tests."""

import numpy as np
import pytest
import xarray as xr
import xesmf as xe
from test_polar_contracts import polar_settings, source_scene

from frameit.processing.polar import (
    azimuthal_mean,
    coverage_aware_azimuthal_mean,
    periodic_fourier_coefficients,
)
from frameit.processing.polar.coverage import SupportedRegridder
from frameit.processing.polar.polar_proj import polar_project


def prescribed_weights(weights, **options):
    grid = xr.Dataset({"lon": (("y_box", "x_box"), [[0., 1.], [0., 1.]]),
                       "lat": (("y_box", "x_box"), [[0., 0.], [1., 1.]])})
    target = xr.Dataset({"lon": ("locations", [.5]), "lat": ("locations", [.5])})
    backend = xe.Regridder(
        grid, target, "bilinear", locstream_out=True, unmapped_to_nan=False,
        weights={"row_dst": np.ones(4, dtype=int), "col_src": np.arange(1, 5),
                 "weights": np.array(weights)},
    )
    return SupportedRegridder(backend, **options)


@pytest.mark.parametrize("policy,threshold,expected,reason", [
    ("strict", .5, np.nan, 2), ("renormalize", .5, 30, 0), ("renormalize", .8, np.nan, 3),
])
def test_actual_backend_application_matches_independent_weighted_oracle(
    policy, threshold, expected, reason
):
    operator = prescribed_weights([.1, .2, .3, .4], policy=policy, minimum_support=threshold)
    field = xr.DataArray([[10., 20.], [np.nan, 40.]], dims=("y_box", "x_box"))
    value, support, status = operator.apply(field)
    np.testing.assert_allclose(support, .7, atol=1e-14)
    np.testing.assert_allclose(value, expected, equal_nan=True, atol=1e-12)
    np.testing.assert_array_equal(status, [reason])
    assert value.item() != 21


def test_zero_weight_nan_and_all_missing_source_values():
    operator = prescribed_weights([.5, 0, 0, .5])
    field = xr.DataArray([[10., np.nan], [np.inf, 40.]], dims=("y_box", "x_box"))
    value, support, status = operator.apply(field)
    np.testing.assert_allclose(value, 25)
    np.testing.assert_allclose(support, 1)
    np.testing.assert_array_equal(status, [0])
    missing = SupportedRegridder(operator.operator, policy="renormalize", minimum_support=0)
    value, support, status = missing.apply(xr.full_like(field, np.nan))
    assert np.isnan(value).all()
    np.testing.assert_allclose(support, 0)
    np.testing.assert_array_equal(status, [2])


def test_unit_support_threshold_uses_complete_stencil_semantics():
    operator = prescribed_weights([.1, .2, .3, .4], policy="renormalize", minimum_support=1)
    field = xr.DataArray([[10., 20.], [30., 40.]], dims=("y_box", "x_box"))
    value, support, status = operator.apply(field)
    np.testing.assert_allclose(value, 30)
    np.testing.assert_array_equal(support, [1])
    np.testing.assert_array_equal(status, [0])
    tiny = prescribed_weights([.3, .3, .4 - 1e-15, 1e-15], policy="renormalize",
                              minimum_support=1, zero_tolerance=0)
    field[-1, -1] = np.nan
    assert np.isnan(tiny.apply(field)[0]).all()


def test_declared_numerical_zero_tolerance_and_negative_weights():
    field = xr.DataArray([[10., 10.], [10., np.nan]], dims=("y_box", "x_box"))
    values = [.3, .3, .4 - 1e-15, 1e-15]
    ignored = prescribed_weights(values, zero_tolerance=1e-14)
    assert np.isfinite(ignored.apply(field)[0]).all()
    contributing = prescribed_weights(values, zero_tolerance=0)
    assert np.isnan(contributing.apply(field)[0]).all()
    with pytest.raises(ValueError, match="nonnegative"):
        prescribed_weights([.3, .3, .5, -.1])


@pytest.mark.parametrize("edge", ["left", "right", "south", "north"])
def test_nan_padded_domain_edges_use_finite_geometry_and_flag_unmapped_targets(edge):
    source = source_scene()
    source["q"] = xr.ones_like(source.q)
    axis = "x_box" if edge in {"left", "right"} else "y_box"
    valid = source[axis] >= 0 if edge in {"left", "south"} else source[axis] <= 0
    source = source.assign_coords(longitude=source.longitude.where(valid),
                                  latitude=source.latitude.where(valid))
    source["q"] = source.q.where(valid)
    result, report = polar_project({"surface": source}, conf=polar_settings())
    ds = result["surface"]
    mapped = ds.geometry_mapped.astype(bool)
    assert bool(mapped.any()) and bool((~mapped).any())
    np.testing.assert_allclose(ds.q.where(mapped, drop=True).values[np.isfinite(
        ds.q.where(mapped, drop=True).values)], 1, atol=1e-12)
    assert bool(ds.q.where(~mapped).isnull().all())
    assert bool((ds.q_interpolation_status.where(~mapped, 1) == 1).all())
    footprint = report["projected"][0]["source_finite_footprints"][0]
    assert footprint["finite_shape"] != footprint["original_shape"]
    np.testing.assert_allclose(ds.q_ring_coverage, mapped.mean("theta"))


def test_joint_vector_support_matches_actual_native_weights():
    source = source_scene(nx=3, ny=3, times=(0,))
    source["u"] = xr.ones_like(source.q) * 2
    source["v"] = xr.ones_like(source.q) * 5
    source["u"][0, 1, 2] = np.nan
    source["v"][0, 2, 1] = np.nan
    source["u"][0, 2, 2] = 14
    source["v"][0, 2, 2] = 21
    track = xr.Dataset({"lon": ("time", [.02]), "lat": ("time", [-19.98])}, coords={"time": [0]})
    config = polar_settings(
        polar_variables={"heightAboveGround": {"variables": ["u", "v"]}},
        polar_missing_data_policy="renormalize", polar_min_valid_weight_fraction=.1,
    )
    result, _ = polar_project({"heightAboveGround": source}, conf=config, track=track)
    ds = result["heightAboveGround"]
    grid = xr.Dataset({"lon": source.longitude, "lat": source.latitude})
    target = xr.Dataset({"lon": ("locations", [.02]), "lat": ("locations", [-19.98])})
    backend = xe.Regridder(grid, target, "bilinear", locstream_out=True, unmapped_to_nan=False)
    weights = backend.weights.data.to_scipy_sparse().toarray()[0]
    mask = (np.isfinite(source.u) & np.isfinite(source.v)).values[0].ravel()
    support = weights[mask].sum()
    for name in ("u", "v"):
        expected = np.sum(weights[mask] * source[name].values[0].ravel()[mask]) / support
        np.testing.assert_allclose(ds[name].isel(time=0, rr=0), expected, atol=1e-12)
        np.testing.assert_allclose(ds[f"{name}_support_fraction"].isel(time=0, rr=0), support)
    np.testing.assert_allclose(ds.u_support_fraction, ds.v_support_fraction)
    assert bool((ds.vrad_interpolation_status.isel(rr=0) == 4).all())
    assert bool((ds.wind_speed_interpolation_status.isel(rr=0) == 0).all())
    assert bool((ds.vrad_full_ring_valid.isel(rr=0) == 0).all())


def test_field_nan_at_an_exact_native_node_does_not_poison_zero_coefficients():
    source = source_scene(times=(0,))
    source["q"] = xr.ones_like(source.q) * 10
    source.q[0, 1, 2] = np.nan
    result, _ = polar_project({"surface": source}, conf=polar_settings())
    ds = result["surface"]
    np.testing.assert_allclose(ds.q.isel(rr=0), 10)
    np.testing.assert_allclose(ds.q_support_fraction.isel(rr=0), 1)


def test_missing_sectors_require_complete_ring_diagnostics():
    theta = np.arange(64) * 2 * np.pi / 64
    data = xr.DataArray(np.cos(theta), dims="theta", coords={"theta": theta})
    missing = data.where(np.cos(data.theta) >= 0)
    assert np.isfinite(missing.mean()).item()
    assert np.isnan(azimuthal_mean(missing)).item()
    assert bool(np.isnan(periodic_fourier_coefficients(missing)).all())
    np.testing.assert_allclose(np.isfinite(missing).mean(), .5, atol=1 / 64)
    strict = coverage_aware_azimuthal_mean(missing)
    assert np.isnan(strict.azimuthal_mean).item()
    partial = coverage_aware_azimuthal_mean(missing, minimum_coverage=.4)
    assert partial.azimuthal_mean.item() > .6
    assert partial.full_ring_valid.item() == 0
    assert partial.azimuthal_mean.attrs["averaging_coverage"] == "valid_sector"
    np.testing.assert_allclose(partial.ring_coverage, np.isfinite(missing).mean())


def test_lazy_and_eager_coverage_results_match():
    source = source_scene()
    source.q[0, 2, 3] = np.nan
    config = polar_settings(polar_missing_data_policy="renormalize")
    eager, _ = polar_project({"surface": source}, conf=config)
    lazy, _ = polar_project({"surface": source.chunk({"time": 1, "x_box": 3})}, conf=config)
    assert hasattr(lazy["surface"].q.data, "dask")
    xr.testing.assert_allclose(lazy["surface"].compute(), eager["surface"])
