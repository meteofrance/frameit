"""Independent operator invariants, geometry-key invalidation and bounded weight reuse."""

import numpy as np
import pytest
import xarray as xr

from frameit.processing.polar import PolarRegridPlanCache
from frameit.processing.polar.contracts import finite_source_footprint
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.processing.polar.polar_proj import polar_project
from frameit.testing.numerical.test_polar_contracts import polar_settings, source_scene


def plan_inputs():
    source = source_scene()
    _, grid, _ = finite_source_footprint(source.isel(time=0, drop=True), "longitude", "latitude")
    target = PolarLonLatGrid.from_conf(polar_settings()).build(source).isel(time=0, drop=True)
    return source, grid, target


def test_sparse_operator_constant_preservation_nonnegative_weights_and_linearity():
    source, grid, target = plan_inputs()
    cache = PolarRegridPlanCache()
    plan = cache.get(grid, target)
    weights = plan.supported.operator.weights.data.to_scipy_sparse()
    mapped = plan.supported.mapped
    np.testing.assert_allclose(np.asarray(weights.sum(axis=1)).ravel()[mapped], 1,
                               rtol=1e-12, atol=1e-12)
    assert (weights.data >= 0).all()
    one = xr.ones_like(source.q.isel(time=0))
    np.testing.assert_allclose(plan.apply(one)[0], 1, rtol=1e-12, atol=1e-12)
    f = source.q.isel(time=0)
    g = f**2 / 100
    a, b = .3, -1.2
    actual = plan.apply(a * f + b * g)[0]
    expected = a * plan.apply(f)[0] + b * plan.apply(g)[0]
    xr.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
    assert plan.diagnostics()["estimated_retained_bytes"] > 0
    with pytest.raises(ValueError):
        plan.geometry.source_lon[0, 0] = 999
    provenance = plan.geometry.provenance
    provenance["method"] = "invalid"
    assert plan.geometry.provenance["method"] == "bilinear"


def test_key_includes_coordinates_order_axes_method_earth_backend_and_static_mask():
    _, grid, target = plan_inputs()
    cache = PolarRegridPlanCache(maxsize=16)
    original = cache.get(grid, target)
    assert cache.get(grid.copy(deep=True), target.copy(deep=True)) is original
    # Values/dynamic masks/policy/chunks are application inputs, not key material.
    shifted = grid.assign(lon=grid.lon + .001)
    altered = [
        cache.get(shifted, target),
        cache.get(grid.isel(x_box=slice(None, None, -1)), target),
        cache.get(grid, target.assign(lon=target.lon + .001)),
        cache.get(grid, target, method="nearest_s2d"),
        cache.get(grid, target.assign_attrs(ellps="sphere")),
        cache.get(grid, target, backend={"xesmf": "test-backend-identity"}),
        cache.get(grid, target, zero_tolerance=0),
    ]
    assert all(plan.signature != original.signature for plan in altered)
    mask = np.ones(grid.lon.shape, dtype=np.uint8)
    unmasked = cache.get(grid, target, source_mask=mask)
    mask[mask.shape[0] // 2, mask.shape[1] // 2] = 0
    excluded = cache.get(grid, target, source_mask=mask)
    assert excluded.signature != unmasked.signature
    assert excluded.supported.mapped.sum() < unmasked.supported.mapped.sum()
    assert not excluded.supported.mapped[:target.sizes["theta_deg"]].any()
    # Mutating the supplied geometry must be detected on the next lookup.
    mutable = grid.copy(deep=True)
    assert cache.get(mutable, target) is original
    mutable.lon.data[:] += .002
    assert cache.get(mutable, target).signature != original.signature


def test_lru_eviction_disabled_cache_and_byte_budget():
    _, grid, target = plan_inputs()
    cache = PolarRegridPlanCache(maxsize=2)
    first = cache.get(grid, target)
    second_target = target.assign(lon=target.lon + .001)
    second = cache.get(grid, second_target)
    assert cache.get(grid, target) is first  # first becomes most recently used
    cache.get(grid, target.assign(lon=target.lon + .002))
    assert cache.statistics()["evictions"] == 1
    assert cache.get(grid, second_target) is not second
    assert cache.statistics()["retained_entries"] == 2
    small = PolarRegridPlanCache(max_bytes=1)
    small.get(grid, target)
    small.get(grid, target)
    assert small.statistics()["builds"] == 2
    assert small.statistics()["oversized_plans"] == 2
    assert small.statistics()["retained_bytes"] == 0
    disabled = PolarRegridPlanCache(maxsize=0)
    disabled.get(grid, target)
    disabled.get(grid, target)
    assert disabled.statistics()["builds"] == 2
    assert disabled.statistics()["hits"] == 0
    cache.clear()
    assert cache.statistics()["retained_entries"] == 0
    assert cache.statistics()["retained_bytes"] == 0


def three_groups(times=(0, 1)):
    source = source_scene(times=times)
    return {name: source.copy(deep=True).assign(q=source.q + offset).expand_dims(level=[1, 2])
            for name, offset in (("surface", 0), ("heightAboveGround", 10), ("isobaricInhPa", 20))}


def group_config(**options):
    return polar_settings(polar_variables={name: {"variables": ["q"]} for name in
                                          ("surface", "heightAboveGround", "isobaricInhPa")},
                          **options)


def test_fixed_groups_share_one_plan_with_uncached_numerical_equivalence():
    inputs = three_groups()
    cached, report = polar_project(inputs, conf=group_config(polar_profile=True))
    uncached, baseline = polar_project(inputs, conf=group_config(polar_regrid_cache_size=0))
    assert report["regrid_performance"]["builds"] == 1
    assert report["regrid_performance"]["hits"] == 2
    assert baseline["regrid_performance"]["builds"] == 3
    for name in cached:
        xr.testing.assert_allclose(cached[name], uncached[name], rtol=1e-12, atol=1e-12)
    assert report["regrid_performance"]["source_geometry_cache"]["hits"] > 0
    assert report["regrid_performance"]["graph_tasks"] == 0


def test_time_outer_scheduling_reuses_moving_weights_with_a_single_entry():
    count = 12
    inputs = three_groups(tuple(range(count)))
    track = xr.Dataset({"lon": ("time", np.arange(count) * .001),
                        "lat": ("time", np.full(count, -20.))}, coords={"time": np.arange(count)})
    config = group_config(tracking_method="prescribed_track", polar_regrid_cache_size=1)
    cached, report = polar_project(inputs, conf=config, track=track)
    assert report["regrid_performance"]["builds"] == count
    assert report["regrid_performance"]["hits"] == count * 2
    assert report["regrid_performance"]["cache"]["peak_retained_entries"] == 1
    uncached, baseline = polar_project(inputs, conf=group_config(
        tracking_method="prescribed_track", polar_regrid_cache_size=0
    ), track=track)
    assert baseline["regrid_performance"]["builds"] == count * 3
    for name in cached:
        xr.testing.assert_allclose(cached[name], uncached[name], rtol=1e-12, atol=1e-12)


def test_revisited_centres_reuse_only_identical_geometry():
    source = source_scene(times=(0, 1, 2))
    track = xr.Dataset({"lon": ("time", [0., .01, 0.]), "lat": ("time", [-20., -20., -20.])},
                       coords={"time": [0, 1, 2]})
    _, report = polar_project({"surface": source}, conf=polar_settings(
        tracking_method="prescribed_track", polar_regrid_cache_size=2
    ), track=track)
    assert report["regrid_performance"]["builds"] == 2
    assert report["regrid_performance"]["hits"] == 1
    signatures = report["projected"][0]["regrid_plan_signatures"]
    assert signatures[0] == signatures[2] != signatures[1]


def test_reuse_does_not_cache_dynamic_masks_or_normalization_policy():
    source, grid, target = plan_inputs()
    cache = PolarRegridPlanCache()
    plan = cache.get(grid, target)
    field = source.q.isel(time=0).copy(deep=True)
    field[2, 3] = np.nan
    strict = cache.apply(plan, field)
    renormalized = cache.apply(plan, field, policy="renormalize", minimum_support=.1)
    changed = cache.apply(plan, xr.ones_like(field))
    assert np.isnan(strict[0]).any()
    assert np.isfinite(renormalized[0]).sum() > np.isfinite(strict[0]).sum()
    np.testing.assert_allclose(changed[0], 1)
    np.testing.assert_allclose(changed[1], 1)
    assert cache.get(grid, target) is plan
    assert cache.statistics()["builds"] == 1


@pytest.mark.parametrize("options", [
    {"polar_regrid_cache_size": -1}, {"polar_regrid_cache_size": True},
    {"polar_regrid_cache_max_bytes": -1}, {"polar_output_chunks": []},
    {"polar_output_chunks": {"theta": 0}}, {"polar_output_chunks": {"x_box": 4}},
    {"polar_output_chunks": {"theta": True}}, {"polar_profile": "yes"},
])
def test_invalid_execution_controls_fail_early(options):
    with pytest.raises(ValueError):
        polar_project({"surface": source_scene()}, conf=polar_settings(**options))


def test_source_field_changes_do_not_change_external_cache_geometry_keys():
    source = source_scene()
    cache = PolarRegridPlanCache()
    _, first = polar_project({"surface": source}, conf=polar_settings(), plan_cache=cache)
    modified = source.assign(q=source.q + 5)
    _, second = polar_project({"surface": modified}, conf=polar_settings(), plan_cache=cache)
    assert first["regrid_performance"]["builds"] == 1
    assert second["regrid_performance"]["builds"] == 0
    assert second["regrid_performance"]["hits"] == 1
