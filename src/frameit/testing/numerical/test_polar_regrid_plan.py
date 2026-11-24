"""Independent operator invariants, geometry-key invalidation and bounded weight reuse."""

import numpy as np
import pytest
import xarray as xr

from frameit.processing.polar import PolarRegridPlan, PolarRegridPlanCache
from frameit.processing.polar.contracts import finite_source_footprint
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.processing.polar.polar_proj import polar_project
from frameit.processing.polar.regrid_plan import RegridGeometry
from frameit.testing.numerical.test_polar_contracts import polar_settings, source_scene


def plan_inputs():
    source = source_scene()
    _, grid, _ = finite_source_footprint(source.isel(time=0, drop=True), "longitude", "latitude")
    target = PolarLonLatGrid.from_conf(polar_settings()).build(source).isel(time=0, drop=True)
    return source, grid, target


def regional_inputs(*, dateline=False, skewed=False):
    source = source_scene(nx=111, ny=83, times=(0,), longitude=179.98 if dateline else 60.)
    if dateline:
        lon = source.longitude + .02 * np.sin(source.y_box / 10)
        lat = source.latitude + .02 * np.sin(source.x_box / 12)
        source = source.assign_coords(longitude=(lon + 180) % 360 - 180, latitude=lat)
        source = source.isel(x_box=slice(None, None, -1))
    if skewed:
        source = source.assign_coords(longitude=source.longitude + .06 * source.y_box)
    _, grid, _ = finite_source_footprint(source.isel(time=0, drop=True), "longitude", "latitude")
    target = PolarLonLatGrid.from_conf(polar_settings()).build(source).isel(time=0, drop=True)
    return source, grid, target


def observe_esmf_shapes(monkeypatch):
    import xesmf

    original = xesmf.Regridder.__init__
    shapes = []

    def observed(self, source, *args, **kwargs):
        shapes.append(source.lon.shape)
        return original(self, source, *args, **kwargs)

    monkeypatch.setattr(xesmf.Regridder, "__init__", observed)
    return shapes


@pytest.fixture
def reference_esmf():
    import xesmf
    from xesmf.backend import ESMF

    if (xesmf.__version__, ESMF.__version__) != ("0.9.2", "8.9.1") or ESMF.pet_count() != 1:
        pytest.skip("Regional windows require the reference single-PET xESMF/ESMF stack")
    return xesmf


@pytest.mark.parametrize("dateline", [False, True])
@pytest.mark.filterwarnings("error:Input array is not F_CONTIGUOUS:UserWarning")
def test_windowed_bilinear_keeps_full_grid_weights_and_quality(monkeypatch, dateline, reference_esmf):
    source, grid, target = regional_inputs(dateline=dateline)
    shapes = observe_esmf_shapes(monkeypatch)
    # The custom factory forces the unchanged full-grid path but calls the same ESMF.
    reference = PolarRegridPlan.build(
        RegridGeometry.capture(grid, target),
        regridder_factory=lambda *a, **k: reference_esmf.Regridder(*a, **k))
    plan = PolarRegridPlanCache().get(grid, target)
    assert shapes[0] == grid.lon.shape and len(shapes) == 2
    assert np.prod(shapes[1]) < grid.lon.size / 4, "ESMF still builds on the full domain"
    assert plan.signature == reference.signature
    assert plan.source_support(1) == reference.source_support(1)
    assert plan.supported.operator.filename == reference.supported.operator.filename
    weights, expected = plan.supported.weights, reference.supported.weights
    assert weights.shape == expected.shape
    for attr in ("indptr", "indices", "data"):
        np.testing.assert_array_equal(getattr(weights, attr), getattr(expected, attr))

    field = source.q.isel(time=0, drop=True).where(source.x_box != 0).chunk({"x_box": 12})
    for policy in ("strict", "renormalize"):
        actual = plan.apply(field, policy=policy, source_halo_points=1)
        expected = reference.apply(field, policy=policy, source_halo_points=1)
        assert (expected[2].compute() == 2).any()
        for value, truth in zip(actual, expected, strict=True):
            xr.testing.assert_identical(value.compute(), truth.compute())


def test_window_lookup_reuse_requires_exact_source_geography(monkeypatch, reference_esmf):
    _, grid, target = regional_inputs()
    shapes = observe_esmf_shapes(monkeypatch)
    cache = PolarRegridPlanCache()
    first = cache.get(grid, target)
    moved = target.assign(lon=target.lon + .007)
    second = cache.get(grid.copy(deep=True), moved)
    changed = grid.copy(deep=True)
    changed.lon.values[0, 0] += .0001
    third = cache.get(changed, moved)
    assert cache.get(grid, target) is first
    assert len({plan.signature for plan in (first, second, third)}) == 3
    assert not np.array_equal(first.supported.weights.data, second.supported.weights.data)
    assert len(shapes) == 3 and all(np.prod(shape) < grid.lon.size / 4 for shape in shapes)
    assert first._window_index is not None and second._window_index is first._window_index
    assert third._window_index is not first._window_index


@pytest.mark.parametrize("lon_step, require_full_grid", [(.04, False), (.002, True)])
def test_windowed_stencils_at_a_native_node_and_shared_edge(
        monkeypatch, reference_esmf, lon_step, require_full_grid):
    _, grid, _ = regional_inputs()
    grid = grid.assign(lon=60. + (grid.lon - 60.) * (lon_step / .04))
    # A native node repeated at the centre, and positions on either side of
    # the meridian through a shared edge, one to a few longitude ulps away.
    lon = np.stack((np.full(8, 60.), 60. + np.spacing(60.) * np.arange(-2, 6)))
    lat = np.broadcast_to(np.array([[-20.], [-19.98]]), lon.shape)
    target = xr.Dataset({
        "lon": (("rr", "theta_deg"), lon),
        "lat": (("rr", "theta_deg"), lat),
    }, coords={"rr": [0., 5.], "theta_deg": np.arange(0., 360., 45.)})
    geometry = RegridGeometry.capture(grid, target)
    shapes = observe_esmf_shapes(monkeypatch)
    plan = PolarRegridPlan.build(geometry)
    assert np.prod(shapes[0]) < grid.lon.size / 4
    assert (grid.lon.shape in shapes) == require_full_grid
    full = PolarRegridPlan.build(
        geometry, regridder_factory=lambda *a, **k: reference_esmf.Regridder(*a, **k))
    for attr in ("indices", "indptr", "data"):
        np.testing.assert_array_equal(getattr(plan.supported.weights, attr),
                                      getattr(full.supported.weights, attr))


@pytest.mark.parametrize("case", [
    "edge", "skewed", "nearest", "static_mask", "backend", "actual_backend", "multi_pet",
])
def test_unqualified_windows_keep_the_full_grid_builder(monkeypatch, case):
    _, grid, target = regional_inputs(skewed=case == "skewed")
    options = {}
    if case == "edge":
        target = target.assign(lon=target.lon - .04 * 55)
    elif case == "nearest":
        options["method"] = "nearest_s2d"
    elif case == "static_mask":
        mask = np.ones(grid.lon.shape, dtype=np.uint8)
        mask[41, 56] = 0
        options["source_mask"] = mask
    elif case == "backend":
        options["backend"] = {"xesmf": "unverified"}
    elif case == "actual_backend":
        from xesmf.backend import ESMF

        monkeypatch.setattr(ESMF, "__version__", "unverified")
        options["backend"] = {"xesmf": "0.9.2", "esmpy": "8.9.1"}
    elif case == "multi_pet":
        from xesmf.backend import ESMF

        monkeypatch.setattr(ESMF, "pet_count", lambda: 2)
    shapes = observe_esmf_shapes(monkeypatch)
    plan = PolarRegridPlanCache().get(grid, target, **options)
    assert shapes == [grid.lon.shape] * (2 if case == "nearest" else 1)
    if case in {"edge", "static_mask"}:
        assert 0 < plan.supported.mapped.sum() < target.lon.size


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


def observe_cropped_operators(monkeypatch):
    from frameit.processing.polar.coverage import SupportedRegridder

    applied = []
    original = SupportedRegridder.apply

    def observe(self, *args, **kwargs):
        applied.append((self.weights, self.presence_weights))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SupportedRegridder, "apply", observe)
    return applied


def test_cache_shares_cropped_weights_between_lazy_fields(monkeypatch):
    source, grid, target = regional_inputs()
    cache = PolarRegridPlanCache()
    plan = cache.get(grid, target)
    applied = observe_cropped_operators(monkeypatch)
    field = xr.full_like(source.q.isel(time=0, drop=True), 7.).chunk()
    missing = cache.apply(plan, field, xr.zeros_like(field, dtype=bool), source_halo_points=1)
    valid = cache.apply(plan, field + 2, source_halo_points=np.int64(1))
    wider = cache.apply(plan, field, source_halo_points=2)

    for first, second, third in zip(*applied, strict=True):
        assert first is second and first is not third
        assert first.shape[1] < third.shape[1]
        assert not any(getattr(first, key).flags.writeable for key in ("data", "indices", "indptr"))
    assert np.isnan(missing[0].compute()).all()
    np.testing.assert_array_equal(missing[1].compute(), 0.)
    np.testing.assert_array_equal(missing[2].compute(), 2)
    np.testing.assert_allclose(valid[0].compute(), 9., rtol=0, atol=1e-12)
    np.testing.assert_array_equal(valid[1].compute(), 1.)
    np.testing.assert_array_equal(valid[2].compute(), 0)
    np.testing.assert_allclose(wider[0].compute(), 7., rtol=0, atol=1e-12)
    for invalid in (True, 1.0, 0):
        with pytest.raises(ValueError, match="halo"):
            cache.apply(plan, field, source_halo_points=invalid)


def test_cropped_weights_normalize_unsigned_halo_on_native_edge():
    source, grid, target = plan_inputs()
    cache = PolarRegridPlanCache()
    plan = cache.get(grid, target.assign(lon=target.lon - .08))
    field = source.q.isel(time=0, drop=True).chunk()
    assert plan.source_support(1)["x_slice"][0] == 0
    expected = plan.apply(field, source_halo_points=1)

    for halo in (np.uint64(1), 1, np.uint64(1)):
        for result, reference in zip(
                cache.apply(plan, field, source_halo_points=halo), expected, strict=True):
            xr.testing.assert_identical(result.compute(), reference.compute())


@pytest.mark.parametrize("warm", [False, True])
def test_cropped_weights_reject_duration_halo(warm):
    source, grid, target = plan_inputs()
    cache = PolarRegridPlanCache()
    plan = cache.get(grid, target)
    field = source.q.isel(time=0, drop=True)
    if warm:
        cache.apply(plan, field, source_halo_points=1)
    with pytest.raises(ValueError, match="halo"):
        cache.apply(plan, field, source_halo_points=np.timedelta64(1, "D"))


def test_cropped_weights_do_not_displace_base_plans(monkeypatch):
    source, grid, target = plan_inputs()
    moved = target.assign(lon=target.lon + .001)
    sizing = PolarRegridPlanCache()
    limit = sizing.get(grid, target).estimated_bytes + sizing.get(grid, moved).estimated_bytes
    cache = PolarRegridPlanCache(maxsize=2, max_bytes=limit)
    plan = cache.get(grid, target)
    field = source.q.isel(time=0, drop=True)
    applied = observe_cropped_operators(monkeypatch)
    cache.apply(plan, field, source_halo_points=1)
    extra = sum(getattr(matrix, key).nbytes for matrix in applied[0]
                for key in ("data", "indices", "indptr"))
    assert cache.statistics()["retained_bytes"] == plan.estimated_bytes + extra

    cache.get(grid, moved)
    assert cache.get(grid, target) is plan
    cache.apply(plan, field, source_halo_points=1)
    cache.apply(plan, field, source_halo_points=1)
    stats = cache.statistics()
    assert stats["retained_bytes"] == stats["peak_retained_bytes"] == limit
    assert stats["evictions"] == 0
    assert applied[0][0] is not applied[1][0] and applied[1][0] is not applied[2][0]
    cache.clear()
    assert cache.statistics()["retained_bytes"] == 0


def test_cropped_weights_leave_with_evicted_plan(monkeypatch):
    source, grid, target = plan_inputs()
    cache = PolarRegridPlanCache(maxsize=1)
    plan = cache.get(grid, target)
    field = xr.ones_like(source.q.isel(time=0, drop=True)).chunk()
    applied = observe_cropped_operators(monkeypatch)
    projected, _, _ = cache.apply(plan, field, source_halo_points=1)
    cache.apply(plan, field, source_halo_points=1)
    assert applied[0][0] is applied[1][0]

    replacement = cache.get(grid, target.assign(lon=target.lon + .001))
    assert cache.statistics()["retained_bytes"] == replacement.estimated_bytes
    rebuilt = cache.get(grid, target)
    cache.apply(rebuilt, field, source_halo_points=1)
    cache.apply(plan, field, source_halo_points=1)
    assert applied[2][0] is not applied[0][0] and applied[3][0] is not applied[2][0]
    cache.clear()
    applied.clear()
    np.testing.assert_allclose(projected.compute(), 1., rtol=0, atol=1e-12)


def three_groups(times=(0, 1)):
    source = source_scene(times=times)
    return {name: source.copy(deep=True).assign(q=source.q + offset).expand_dims(level=[1, 2])
            for name, offset in (("surface", 0), ("heightAboveGround", 10), ("isobaric", 20))}


def group_config(**options):
    return polar_settings(polar_variables={name: {"variables": ["q"]} for name in
                                          ("surface", "heightAboveGround", "isobaric")},
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
