"""Stored rainfall semantics, failure reporting and the real CI cell pilot."""

import json
from importlib import resources

import numpy as np
import pytest

from frameit.testing.polar_rainfall_ci import (
    BOUNDS_POLICY,
    SPATIAL_INTERPRETATION,
    _accumulation_times,
    _analysis_grid,
    _midpoint_edges,
    read_rainfall,
    run_ci_rainfall,
)


def fixture_root():
    pytest.importorskip("eccodes")
    root = resources.files("frameit.testing").joinpath("ci_dataset")
    if not root.joinpath("manifest.json").is_file():
        pytest.skip("Bundled CI data are not installed")
    return root


def metadata():
    return dict(paramId=235015, shortName="tirf", typeOfLevel="surface", stepType="accum",
                typeOfStatisticalProcessing=1, units="kg m**-2", stepUnits=1, startStep=0,
                endStep=6, dataDate=20220201, dataTime=0)


@pytest.mark.parametrize("change", [{"stepType": "instant"}, {"startStep": 6}, {"endStep": 0},
                                    {"units": "m"}, {"stepUnits": 2}, {"paramId": 260015}])
def test_incompatible_quantity_or_accumulation_is_rejected(change):
    with pytest.raises(ValueError, match="accumulated from hour zero"):
        _accumulation_times({**metadata(), **change})


def test_midpoint_bounds_preserve_descending_storage_and_fail_on_irregular_axes():
    np.testing.assert_allclose(_midpoint_edges([-16.5, -16.525, -16.55]),
                               [-16.4875, -16.5125, -16.5375, -16.5625])
    lon, lat = np.meshgrid([59., 59.025, 59.05], [-16.5, -16.525, -16.55])
    grid = _analysis_grid(lon, lat)
    np.testing.assert_array_equal(grid.lat, lat)
    assert grid.lon_b.dims == ("y_b", "x_b")
    assert grid.attrs["bounds_policy"] == BOUNDS_POLICY
    with pytest.raises(ValueError, match="uniform regular_ll"):
        _midpoint_edges([0, 1, 3])
    lon[1, 1] += .01
    with pytest.raises(ValueError, match="rectilinear"):
        _analysis_grid(lon, lat)


def test_real_record_retains_mass_units_and_cumulative_time():
    root = fixture_root().joinpath("AROME", "BATSIRAI")
    assert read_rainfall(root / "arome_BATSIRAI_20220201+0000P.grib", "2022-02-01T00:00:00") is None
    record = read_rainfall(root / "arome_BATSIRAI_20220201+0600P.grib", "2022-02-01T06:00:00")
    assert record["start"] == np.datetime64("2022-02-01T00:00:00", "ns")
    assert record["end"] == np.datetime64("2022-02-01T06:00:00", "ns")
    assert record["metadata"]["radius"] == 6371229
    assert record["field"].attrs["units"] == "kg m-2"
    assert record["field"].shape == (81, 81)
    assert float(record["field"].max()) > 0
    with pytest.raises(ValueError, match="does not match"):
        read_rainfall(root / "arome_BATSIRAI_20220201+0600P.grib", "2022-02-01T12:00:00")


def test_ci_pilot_independent_mass_coverage_time_and_plain_netcdf(tmp_path):
    root = fixture_root()
    pytest.importorskip("esmpy")
    pytest.importorskip("shapely")
    pytest.importorskip("xesmf")
    from netCDF4 import Dataset, num2date

    output = tmp_path / "pilot"
    report = run_ci_rainfall(output, data_root=root)
    assert report["passed"] and report["status"] == "PASS"
    assert report == json.loads((output / "comparison.json").read_text())
    assert len(report["excluded"]) == 1
    assert "no zero value fabricated" in report["excluded"][0]["reason"]
    assert len(report["products"]) == 5
    assert {case["id"] for case in report["cases"]} == {
        "fixed", "moving", "coarse", "clipped", "masked"}
    assert all(row["mass_relative_error"] < 2e-7
               for case in report["cases"] for row in case["times"])
    fixed = next(case for case in report["cases"] if case["id"] == "fixed")
    assert all(row["reconstruction_comparison"] is not None for row in fixed["times"])
    with Dataset(output / "batsirai-rain-moving.nc") as dataset:
        assert dataset.source_spatial_interpretation == SPATIAL_INTERPRETATION
        assert dataset.earth_radius_m == 6371229.
        assert "center_lon" not in dataset.ncattrs()
        np.testing.assert_allclose(dataset["center_lon"][:], [59.85, 59.95, 60.05, 60.15])
        assert dataset["covered_area_integral"].units == "kg"
        assert dataset["cell_mean"].units == "kg m-2"
        assert dataset["time"].bounds == "time_bounds"
        times = num2date(dataset["time"][:], dataset["time"].units)
        # CF bounds inherit their coordinate's units/calendar when not repeated.
        bounds = num2date(dataset["time_bounds"][:],
                         getattr(dataset["time_bounds"], "units", dataset["time"].units))
        assert [stamp.hour for stamp in times] == [6, 12, 18, 0]
        assert all(stamp.isoformat() == "2022-02-01T00:00:00" for stamp in bounds[:, 0])
        assert list(bounds[:, 1]) == list(times)
        assert len(set(dataset["geometry_signature"][:])) == 4
    with Dataset(output / "batsirai-rain-fixed.nc") as dataset:
        assert "bilinear_point_sample" in dataset.variables
        assert dataset["bilinear_area_average"].cell_measures == "area: cell_area"
    with Dataset(output / "batsirai-rain-clipped.nc") as dataset:
        coverage = dataset["geometry_coverage"][:]
        assert np.any((coverage > 0) & (coverage < .99))
        assert np.any(np.ma.getmaskarray(dataset["cell_mean"][:]))
        integral = dataset["covered_area_integral"][:]
        valid = dataset["valid_area"][:]
        mean = dataset["covered_area_mean"][:]
        np.testing.assert_allclose(np.ma.filled(integral, 0), np.ma.filled(mean*valid, 0))
    with Dataset(output / "batsirai-rain-masked.nc") as dataset:
        assert "synthetic" in dataset.source_mask_policy
        assert np.any(dataset["valid_area_fraction"][:] < dataset["geometry_coverage"][:] - 1e-5)
    with pytest.raises(ValueError, match="fresh or empty"):
        run_ci_rainfall(output, data_root=root)
    with pytest.raises(ValueError, match="must not overlap"):
        run_ci_rainfall(root / "pilot", data_root=root)


def test_missing_required_rainfall_leaves_a_failed_report(tmp_path, monkeypatch):
    root = fixture_root()
    import frameit.testing.polar_rainfall_ci as pilot

    original = pilot.read_rainfall

    def missing(path, stamp):
        return None if "+1200P" in path.name else original(path, stamp)

    monkeypatch.setattr(pilot, "read_rainfall", missing)
    output = tmp_path / "failed"
    with pytest.raises(ValueError, match="Required accumulated rainfall is absent"):
        run_ci_rainfall(output, data_root=root)
    report = json.loads((output / "comparison.json").read_text())
    assert not report["passed"] and report["status"] == "FAILED"
    assert report["products"] == []
