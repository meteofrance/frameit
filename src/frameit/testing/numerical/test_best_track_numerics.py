from dataclasses import replace

import numpy as np
import pytest
import xarray as xr
from pyproj import Geod

from frameit.core.configuration import resolve_schema
from frameit.testing.numerical.test_run_diag_sources import vortex_parent


def setup_case(tmp_path):
    import importlib.util

    assert importlib.util.find_spec("frameit.diagnostics.best_track") is not None
    from frameit.diagnostics.runner import _admit_parent
    from frameit.diagnostics.sources import plan_source

    cfg, raw, path, root = vortex_parent(tmp_path)
    request = resolve_schema(raw, base_dir=cfg.parent)[0]["diagnostics"]["best_track"]
    parent = _admit_parent(root, raw, base_dir=cfg.parent, source_name="weather",
                           source_kind="original")
    return plan_source(parent, request, scratch=tmp_path), path


def test_discrete_vortex_and_quadrants(tmp_path):
    plan, path = setup_case(tmp_path)
    from frameit.diagnostics.best_track import reduce_time
    from frameit.diagnostics.sources import open_source

    c = plan.parent.centres[0]
    with open_source(plan, scratch=tmp_path) as provider:
        row = reduce_time(c, provider, plan)
    with xr.open_dataset(path) as ds:
        lon, lat = np.meshgrid(ds.longitude.values, ds.latitude.values)
        az, _, distance = Geod(a=6371000, b=6371000).inv(
            np.full(lon.shape, 60.), np.full(lat.shape, -20.), lon, lat)
        quadrant = np.mod(az, 360) // 90
        speed = ds.wind10.values[0]
        assert row.maximum_wind.observed == pytest.approx(speed[distance <= 40000].max())
        assert row.central_pressure.value == 98000
        for n, threshold in enumerate((28, 34, 48, 64)):
            for q in range(4):
                selected = (distance > 0) & (distance <= 80000) & (
                    quadrant == q) & (speed >= threshold * 1852 / 3600)
                metric = row.wind_radii[n * 4 + q]
                assert (metric.value if metric.value is not None else metric.bound) == pytest.approx(
                    distance[selected].max() if selected.any() else 0., abs=1e-6)


def test_coverage_and_rim_invariant_in_tiles(tmp_path):
    plan, _ = setup_case(tmp_path)
    from frameit.diagnostics.best_track import reduce_time
    from frameit.diagnostics.sources import open_source

    small_tiles = replace(plan, samples=tuple(
        (time, tuple(replace(group, tile_side=4) for group in groups))
        for time, groups in plan.samples
    ))
    c = plan.parent.centres[0]
    with open_source(plan, scratch=tmp_path) as p, open_source(small_tiles, scratch=tmp_path) as s:
        large, small = reduce_time(c, p, plan), reduce_time(c, s, small_tiles)
    assert large == small


def test_annular_peak_rules():
    import importlib.util

    assert importlib.util.find_spec("frameit.diagnostics.best_track") is not None
    from frameit.diagnostics.best_track import annular_peak

    complete = np.full((5, 4), 2)
    result = annular_peak(np.array([1., 3., 2., 2.5, 1.]), complete, 1000.)
    assert result.value == 1500
    assert "multiple_local_peaks" in result.reasons
    tie = annular_peak(np.array([1., 3., 2., 3., 1.]), complete, 1000.)
    assert tie.value is None and tie.observed == 1500
    assert tie.candidates == ((1000., 2000.), (3000., 4000.))
    incomplete_sector = complete.copy()
    incomplete_sector[0, 2] = 0
    assert annular_peak(np.array([1., 3., 2., 2., 1.]), incomplete_sector, 1000.).value is None
    assert annular_peak(np.array([3., 2., 1., 2., 1.]), complete, 1000.).value is None


def test_geodesic_perimeter_handles_dateline_and_rejects_edge():
    import importlib.util

    assert importlib.util.find_spec("frameit.diagnostics.geometry") is not None
    from frameit.diagnostics.contracts import Centre
    from frameit.diagnostics.geometry import certify_disc

    geod = Geod(a=6371000, b=6371000)
    centre = Centre("2000-01-01", -20., 180.)
    lat = np.array([-21., -21., -19., -19.])
    lon = np.array([179., -179., -179., 179.])
    assert certify_disc(centre, (lat, lon), geod=geod, radius_m=50000,
                        budget_bytes=100_000) == "complete"
    assert certify_disc(centre, (lat, lon), geod=geod, radius_m=125000,
                        budget_bytes=100_000) != "complete"
    assert certify_disc(centre, (lat[[0, 2, 1, 3]], lon[[0, 2, 1, 3]]), geod=geod,
                        radius_m=30000, budget_bytes=100_000) == "unknown_geometry"
