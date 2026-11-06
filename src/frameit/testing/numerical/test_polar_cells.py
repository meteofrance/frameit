"""Independent spherical overlap, coverage and interoperability checks for cells."""

import numpy as np
import pytest
import xarray as xr
from pyproj import Geod

from frameit.processing.polar.conservative import ConservativePolarPlan
from frameit.testing.polar_cell_comparison import (
    EARTH_RADIUS_M,
    independent_overlap,
    source_fixture,
)


def build(source=None, **changes):
    pytest.importorskip("esmpy")
    options = dict(radial_edges_m=[0, 20000, 60000], azimuth_count=12,
                   center_lon=0, center_lat=0, earth_radius_m=EARTH_RADIUS_M,
                   max_arc_step_deg=5)
    options.update(changes)
    return ConservativePolarPlan.build(source if source is not None else source_fixture(20000),
                                       **options)


def field(source, values):
    return xr.DataArray(values, dims=("y", "x"), coords={"y": source.y, "x": source.x},
                        attrs={"units": "m"}, name="depth")


@pytest.mark.parametrize("longitude,latitude", [(0., 0.), (179.8, -20.), (45., 60.)])
def test_overlap_conservation_and_full_disk_against_independent_geometry(longitude, latitude):
    source = source_fixture(40000, longitude=longitude, latitude=latitude)
    plan = build(source, center_lon=longitude, center_lat=latitude)
    oracle = independent_overlap(source, plan.geometry)
    actual = plan.weights.toarray() * plan.geometry.cell_area.values.ravel()[:, None]
    np.testing.assert_allclose(actual, oracle, rtol=2e-7, atol=.05)
    np.testing.assert_allclose(plan.source_overlap_area, oracle.sum(axis=0), rtol=2e-7, atol=.1)
    np.testing.assert_allclose(plan.geometry.geometry_coverage, 1, atol=1e-8)
    # The polygon disk approaches, but is not exactly, the spherical cap.
    cap_area = 4*np.pi*EARTH_RADIUS_M**2 * np.sin(60000/(2*EARTH_RADIUS_M))**2
    assert 0 < 1 - float(plan.geometry.cell_area.sum()) / cap_area < .002
    values = np.arange(source.lon.size).reshape(source.lon.shape) + 1.
    result = plan.apply(field(source, values), source_representation="scalar_cell_mean")
    expected = oracle @ values.ravel()
    np.testing.assert_allclose(result.covered_area_integral.values.ravel(), expected,
                               rtol=2e-7, atol=1)
    np.testing.assert_allclose(result.cell_mean * result.cell_area, result.covered_area_integral)


def test_boundary_and_changing_masks_never_fabricate_full_cell_means():
    source = source_fixture(20000).isel(x=slice(0, 5), x_b=slice(0, 6))
    plan = build(source)
    values = np.ones(source.lon.shape) * 3
    first = plan.apply(field(source, values), source_representation="scalar_cell_mean")
    assert bool(((first.geometry_coverage > 0) & (first.geometry_coverage < .99)).any())
    assert bool(first.cell_mean.isnull().any())
    np.testing.assert_allclose(first.covered_area_mean.where(first.valid_area > 0).values[
        first.valid_area.values > 0], 3)
    values[2:4, 2:4] = np.nan
    second = plan.apply(field(source, values), source_representation="scalar_cell_mean")
    assert bool((second.valid_area_fraction < first.valid_area_fraction - 1e-5).any())
    oracle = independent_overlap(source, plan.geometry)
    np.testing.assert_allclose(second.covered_area_integral.fillna(0).values.ravel(),
                               oracle @ np.nan_to_num(values.ravel()), rtol=2e-7, atol=.5)
    empty = plan.apply(field(source, np.full_like(values, np.nan)),
                       source_representation="scalar_cell_mean")
    assert bool(empty.cell_mean.isnull().all())
    assert bool(empty.covered_area_mean.isnull().all())
    assert bool(empty.covered_area_integral.isnull().all())
    assert float(empty.valid_area.sum()) == 0


def test_dask_time_masks_and_netcdf_reopen(tmp_path):
    source = source_fixture(20000)
    plan = build(source)
    values = np.ones(source.lon.shape)
    eager = field(source, values).expand_dims(time=[0, 1]).copy(deep=True)
    eager.values[1, 1:4, 2:5] = np.nan
    lazy = plan.apply(eager.chunk({"time": 1, "y": -1, "x": -1}),
                      source_representation="scalar_cell_mean")
    assert hasattr(lazy.cell_mean.data, "__dask_graph__")
    result = lazy.compute()
    xr.testing.assert_allclose(result, plan.apply(eager, source_representation="scalar_cell_mean"))
    result.to_netcdf(tmp_path / "cells.nc")
    with xr.open_dataset(tmp_path / "cells.nc") as saved:
        xr.testing.assert_allclose(saved, result)
        assert saved.cell_mean.attrs["cell_measures"] == "area: cell_area"
        assert saved.covered_area_mean.attrs["cell_measures"] == "area: valid_area"
        assert saved.radius_cell.attrs["bounds"] == "radius_bounds"
        assert saved.attrs["earth_model"] == "sphere"


def test_centre_shift_requires_new_plan_and_geometry_snapshot_is_owned():
    source = source_fixture(20000)
    plan = build(source)
    shifted = build(source, center_lon=.1)
    assert plan.geometry.attrs["geometry_sha256"] != shifted.geometry.attrs["geometry_sha256"]
    assert not np.allclose(plan.weights.toarray(), shifted.weights.toarray())
    original = plan.source.lon.copy(deep=True)
    source.lon.values[:] += 1
    xr.testing.assert_identical(plan.source.lon, original)


def test_source_areas_agree_with_independent_spherical_polygons():
    from frameit.testing.polar_cell_comparison import source_rings

    source = source_fixture(20000)
    plan = build(source)
    geod = Geod(a=EARTH_RADIUS_M, b=EARTH_RADIUS_M)
    areas = [abs(geod.polygon_area_perimeter(*ring.T)[0]) for ring in source_rings(source)]
    np.testing.assert_allclose(plan.source_area, areas, rtol=1e-9, atol=.05)


@pytest.mark.parametrize("changes,match", [
    ({"radial_edges_m": [-1, 20000]}, "Radial edges"),
    ({"azimuth_count": True}, "azimuth_count"),
    ({"max_arc_step_deg": 0}, "max_arc_step_deg"),
    ({"max_cells": 10}, "budget"),
    ({"earth_radius_m": np.nan}, "earth_radius_m"),
])
def test_invalid_geometry_options(changes, match):
    with pytest.raises(ValueError, match=match):
        build(**changes)


def test_explicit_bounds_semantics_alignment_and_units_are_required():
    source = source_fixture(20000)
    with pytest.raises(ValueError, match="explicit lon_b"):
        build(source.drop_vars("lon_b"))
    invalid = source.copy(deep=True)
    invalid.lon_b.values[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        build(invalid)
    invalid = source.copy(deep=True)
    invalid.lon.attrs["units"] = "radians"
    with pytest.raises(ValueError, match="geographic coordinates in degrees"):
        build(invalid)
    with pytest.raises(ValueError, match="corner dimensions"):
        build(source.transpose("x_b", "y_b", "y", "x"))
    plan = build(source)
    value = field(source, np.ones(source.lon.shape))
    with pytest.raises(ValueError, match="scalar_cell_mean"):
        plan.apply(value, source_representation="point_value")
    with pytest.raises(ValueError, match="coordinates differ"):
        plan.apply(value.isel(x=slice(None, None, -1)), source_representation="scalar_cell_mean")
    value.attrs.clear()
    with pytest.raises(ValueError, match="units"):
        plan.apply(value, source_representation="scalar_cell_mean")


def test_arc_refinement_reduces_polygonal_area_error():
    coarse = build(max_arc_step_deg=5)
    fine = build(max_arc_step_deg=1)
    cap_area = 4*np.pi*EARTH_RADIUS_M**2 * np.sin(60000/(2*EARTH_RADIUS_M))**2
    old = abs(float(coarse.geometry.cell_area.sum()) - cap_area)
    new = abs(float(fine.geometry.cell_area.sum()) - cap_area)
    assert new < old / 20
