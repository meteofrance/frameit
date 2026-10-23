"""Instantaneous semantics, independent means, weighting and ordinary-reader checks."""

import json
from importlib import resources

import numpy as np
import pytest
import xarray as xr

from frameit.testing.polar_thermodynamics_ci import (
    HEIGHTS_M,
    MASS_WEIGHTING_STATUS,
    _instant_time,
    _weighted_means,
    read_thermodynamic_snapshot,
    run_ci_thermodynamics,
)


def fixture_root():
    pytest.importorskip("eccodes")
    root = resources.files("frameit.testing").joinpath("ci_dataset")
    if not root.joinpath("manifest.json").is_file():
        pytest.skip("Bundled CI fixture is not installed")
    return root


def test_area_and_equal_cell_weighting_have_distinct_known_answers():
    area_mean, equal_mean, area, count = _weighted_means(
        np.array([10., 20., np.nan]), np.array([1., 3., 2.]))
    assert area_mean == 17.5 and equal_mean == 15.
    assert area == 4 and count == 2
    empty = _weighted_means(np.array([np.nan, 100.5]), np.array([1., 0.]))
    assert np.isnan(empty[0]) and np.isnan(empty[1]) and empty[2] == 0 and empty[3] == 0
    with pytest.raises(ValueError, match="finite and nonnegative"):
        _weighted_means(np.array([10., 20.]), np.array([1., -1.]))


@pytest.mark.parametrize("change", [{"stepType": "accum"}, {"units": "degC"},
                                    {"level": 20}, {"typeOfLevel": "isobaricInhPa"},
                                    {"paramId": 133}, {"startStep": 0}])
def test_incompatible_time_variable_units_or_height_fail(change):
    metadata = dict(paramId=130, shortName="t", units="K", typeOfLevel="heightAboveGround",
                    level=100, stepType="instant", stepUnits=1, startStep=6, endStep=6,
                    dataDate=20220201, dataTime=0)
    with pytest.raises(ValueError, match="Expected instantaneous"):
        _instant_time({**metadata, **change}, "t", "2022-02-01T06:00:00")


def test_real_snapshot_preserves_levels_time_zero_and_relative_humidity_above_100():
    root = fixture_root().joinpath("AROME", "BATSIRAI")
    initial = read_thermodynamic_snapshot(root / "arome_BATSIRAI_20220201+0000P.grib",
                                         "2022-02-01T00:00:00")
    assert set(initial["fields"]) == {"t", "r"}
    assert len(initial["excluded"]) == 1 and initial["excluded"][0]["quantity"] == "tke"
    assert initial["time"] == np.datetime64("2022-02-01T00:00:00", "ns")
    positive = read_thermodynamic_snapshot(root / "arome_BATSIRAI_20220201+0600P.grib",
                                          "2022-02-01T06:00:00")
    assert set(positive["fields"]) == {"t", "r", "tke"}
    assert positive["fields"]["tke"].attrs["units"] == "J kg-1"
    assert positive["fields"]["r"].attrs["units"] == "%"
    assert float(positive["fields"]["r"].sel(height=750).max()) > 100
    np.testing.assert_array_equal(positive["fields"]["t"].height, HEIGHTS_M)
    with pytest.raises(ValueError, match="valid time differs"):
        read_thermodynamic_snapshot(root / "arome_BATSIRAI_20220201+0600P.grib",
                                    "2022-02-01T12:00:00")


def test_bilinear_cell_quadrature_preserves_leading_axes_and_does_not_clip():
    pytest.importorskip("xesmf")
    from frameit.processing.polar.conservative import ConservativePolarPlan
    from frameit.testing.polar_cell_comparison import bilinear_cell_average, source_fixture

    source = source_fixture(40000.)
    plan = ConservativePolarPlan.build(source, radial_edges_m=[0, 20000.], azimuth_count=12,
        center_lon=0, center_lat=0, earth_radius_m=6371000., max_arc_step_deg=5.)
    values = np.broadcast_to(np.array([100.5, 120.])[:, None, None], (2, *source.lon.shape)).copy()
    field = xr.DataArray(values, dims=("height", "y", "x"),
                         coords={"height": list(HEIGHTS_M), "y": source.y, "x": source.x},
                         attrs={"units": "%"})
    actual = bilinear_cell_average(source, field.transpose("y", "height", "x"), plan.geometry)
    assert actual.shape == (2, 1, 12)
    np.testing.assert_allclose(actual[:, 0, :], np.broadcast_to([[100.5], [120.]], (2, 12)),
                               rtol=0, atol=5e-9)


def test_ci_thermodynamic_representations_weighting_and_netcdf(tmp_path):
    root = fixture_root()
    pytest.importorskip("xesmf")
    pytest.importorskip("shapely", minversion="2")
    from netCDF4 import Dataset, num2date

    output = tmp_path / "thermodynamics"
    report = run_ci_thermodynamics(output, data_root=root)
    assert report["passed"] and report["status"] == "PASS"
    assert len(report["products"]) == 15 and all(check["ok"] for check in report["checks"])
    assert report["mass_weighting_status"] == MASS_WEIGHTING_STATUS
    assert report["quantities"]["r"]["difference_units"] == "percentage points"
    for name, count, units in (("t", 5, "K"), ("r", 5, "%"), ("tke", 4, "J kg-1")):
        result = report["quantities"][name]
        assert len(result["cases"]) == 5
        assert all(len(case["times"]) == count for case in result["cases"])
        assert len(result["excluded"]) == (1 if name == "tke" else 0)
        assert all(height["max_overlap_mean_difference"] <= height["mean_tolerance"]
                   for case in result["cases"] for stamp in case["times"]
                   for height in stamp["heights"])
        with Dataset(output / f"batsirai-{name}-fixed.nc") as saved:
            assert len(saved.dimensions["time"]) == count
            np.testing.assert_array_equal(saved["height"][:], HEIGHTS_M)
            assert saved["height"].height_reference == "ground"
            assert saved["cell_mean"].units == units
            assert "time_bounds" not in saved.variables and "bounds" not in saved["time"].ncattrs()
            assert "time: sum" not in saved["cell_mean"].cell_methods
            assert "covered_area_integral" not in saved.variables
            assert "not a physical budget" in saved["area_weighted_numerator"].long_name
            times = num2date(saved["time"][:], saved["time"].units)
            assert times[0].hour == (6 if name == "tke" else 0)
            numerator = saved["area_weighted_numerator"][:].sum(axis=(-2, -1))
            denominator = saved["valid_area"][:].sum(axis=(-2, -1))
            np.testing.assert_allclose(saved["area_weighted_mean"][:], numerator/denominator)
            assert saved.mass_weighting_status == MASS_WEIGHTING_STATUS
            assert saved["bilinear_area_average"].units == units
        with Dataset(output / f"batsirai-{name}-clipped.nc") as saved:
            assert np.any(np.ma.getmaskarray(saved["cell_mean"][:]))
            assert np.any(saved["geometry_coverage"][:] == 0)
        with Dataset(output / f"batsirai-{name}-masked.nc") as saved:
            assert "synthetic" in saved.source_mask_policy
            geometry = saved["geometry_coverage"][:][:, None, :, :]
            assert np.any(saved["valid_area_fraction"][:] < geometry - 1e-5)
    with pytest.raises(ValueError, match="fresh or empty"):
        run_ci_thermodynamics(output, data_root=root)
    with pytest.raises(ValueError, match="must not overlap"):
        run_ci_thermodynamics(root / "thermodynamics", data_root=root)


def test_missing_positive_lead_tke_fails_instead_of_dropping_times(tmp_path, monkeypatch):
    root = fixture_root()
    import frameit.testing.polar_thermodynamics_ci as pilot

    original = pilot.read_thermodynamic_snapshot

    def missing(path, stamp):
        if "+1200P" in path.name:
            raise ValueError("Required tke levels are missing")
        return original(path, stamp)

    monkeypatch.setattr(pilot, "read_thermodynamic_snapshot", missing)
    output = tmp_path / "failed"
    with pytest.raises(ValueError, match="Required tke levels are missing"):
        run_ci_thermodynamics(output, data_root=root)
    report = json.loads((output / "comparison.json").read_text())
    assert report["status"] == "FAILED" and not report["passed"] and not report["products"]
