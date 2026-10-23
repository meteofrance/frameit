"""Source-signed surface-energy integration, cancellation and real CI exports."""

import json
from importlib import resources

import numpy as np
import pytest

from frameit.testing.polar_rainfall_ci import (
    _accumulation_times,
    _integral_errors,
    read_accumulated_scalar,
    run_ci_heat_fluxes,
)


def fixture_root():
    pytest.importorskip("eccodes")
    root = resources.files("frameit.testing").joinpath("ci_dataset")
    if not root.joinpath("manifest.json").is_file():
        pytest.skip("Bundled CI data are not installed")
    return root


@pytest.mark.parametrize("quantity,parameter", [("sshf", 146), ("slhf", 147)])
def test_real_heat_records_preserve_signed_values_and_energy_units(quantity, parameter):
    root = fixture_root().joinpath("AROME", "BATSIRAI")
    assert read_accumulated_scalar(root / "arome_BATSIRAI_20220201+0000P.grib",
        "2022-02-01T00:00:00", quantity=quantity) is None
    record = read_accumulated_scalar(root / "arome_BATSIRAI_20220201+0600P.grib",
                                     "2022-02-01T06:00:00", quantity=quantity)
    assert record["metadata"]["paramId"] == parameter
    assert record["field"].attrs["units"] == "J m-2"
    assert record["start"] == np.datetime64("2022-02-01T00:00:00", "ns")
    assert record["end"] == np.datetime64("2022-02-01T06:00:00", "ns")
    assert record["field"].shape == (81, 81)
    assert float(record["field"].min()) < 0
    if quantity == "sshf":
        assert float(record["field"].max()) > 0
    else:
        assert float(record["field"].max()) < 0
    for change in ({"units": "W m**-2"}, {"stepType": "avg"}, {"startStep": 3},
                   {"paramId": 235015}):
        with pytest.raises(ValueError, match="accumulated from hour zero"):
            _accumulation_times({**record["metadata"], **change}, quantity=quantity)


def test_signed_cell_check_is_stable_at_zero_net_and_cannot_hide_cancelled_errors():
    # Strong opposing source contributions can have an exactly zero cell net.
    # Tolerance scales with those contributions, while cells are checked separately.
    expected = np.array([0., 0.])
    absolute = np.array([1e12, 1e12])
    np.testing.assert_array_equal(_integral_errors(np.array([1., -1.]), expected, absolute),
                                  [1., 1.])
    with pytest.raises(AssertionError):
        _integral_errors(np.array([1e8, -1e8]), expected, absolute)


def test_heat_flux_ci_energy_coverage_bounds_and_ordinary_reader(tmp_path):
    root = fixture_root()
    pytest.importorskip("esmpy")
    pytest.importorskip("xesmf")
    pytest.importorskip("shapely", minversion="2")
    from netCDF4 import Dataset, num2date

    output = tmp_path / "energy"
    summary = run_ci_heat_fluxes(output, data_root=root)
    assert summary["passed"] and summary["status"] == "PASS"
    assert set(summary["quantities"]) == {"sshf", "slhf"}
    for quantity, parameter in (("sshf", 146), ("slhf", 147)):
        entry = summary["quantities"][quantity]
        assert entry["passed"] and len(entry["products"]) == 5
        assert entry["max_integral_l1_normalized_error"] < 2e-7
        report = json.loads((output / entry["report"]).read_text())
        assert report["quantity"] == quantity
        assert report["settings"]["integral_units"] == "J"
        assert report["settings"]["parameter_id"] == parameter
        assert len(report["excluded"]) == 1
        assert all(check["ok"] for check in report["checks"])
        assert len(report["cases"]) == 5
        assert all(len(case["times"]) == 4 for case in report["cases"])
        assert all(row["absolute_source_overlap_integral"] > 0
                   for case in report["cases"] for row in case["times"])
        with Dataset(output / quantity / f"batsirai-{quantity}-fixed.nc") as saved:
            assert saved["cell_mean"].units == "J m-2"
            assert saved["covered_area_integral"].units == "J"
            assert saved.GRIB_paramId == parameter
            assert "stored GRIB signs preserved" in saved.source_sign_policy
            assert np.any(saved["cell_mean"][:] < 0)
            assert np.any(saved["covered_area_integral"][:] < 0)
            assert saved["bilinear_area_average"].units == "J m-2"
            bounds = num2date(saved["time_bounds"][:],
                              getattr(saved["time_bounds"], "units", saved["time"].units))
            times = num2date(saved["time"][:], saved["time"].units)
            assert all(stamp.isoformat() == "2022-02-01T00:00:00" for stamp in bounds[:, 0])
            assert list(bounds[:, 1]) == list(times)
            np.testing.assert_allclose(
                saved["covered_area_integral"][:],
                saved["covered_area_mean"][:]*saved["valid_area"][:])
        with Dataset(output / quantity / f"batsirai-{quantity}-clipped.nc") as saved:
            assert np.any(np.ma.getmaskarray(saved["cell_mean"][:]))
            assert np.any(saved["geometry_coverage"][:] == 0)
        with Dataset(output / quantity / f"batsirai-{quantity}-masked.nc") as saved:
            assert "synthetic" in saved.source_mask_policy
            assert np.any(saved["valid_area_fraction"][:] < saved["geometry_coverage"][:] - 1e-5)
    with pytest.raises(ValueError, match="fresh or empty"):
        run_ci_heat_fluxes(output, data_root=root)


def test_missing_heat_record_retains_completed_quantity_and_failed_child(tmp_path, monkeypatch):
    root = fixture_root()
    pytest.importorskip("esmpy")
    pytest.importorskip("xesmf")
    pytest.importorskip("shapely", minversion="2")
    import frameit.testing.polar_rainfall_ci as pilot

    original = pilot.read_accumulated_scalar

    def missing(path, stamp, *, quantity):
        if quantity == "slhf" and "+1200P" in path.name:
            return None
        return original(path, stamp, quantity=quantity)

    monkeypatch.setattr(pilot, "read_accumulated_scalar", missing)
    monkeypatch.setattr(pilot, "_presets", lambda: (
        {"id": "fixed", "radial_step_m": 10000., "azimuth_count": 24},))
    output = tmp_path / "failed"
    with pytest.raises(ValueError, match="Required accumulated slhf is absent"):
        run_ci_heat_fluxes(output, data_root=root)
    summary = json.loads((output / "comparison.json").read_text())
    assert summary["status"] == "FAILED" and not summary["passed"]
    assert summary["quantities"]["sshf"]["passed"]
    assert summary["pending_quantity"] == "slhf"
    child = json.loads((output / "slhf" / "comparison.json").read_text())
    assert child["status"] == "FAILED" and child["products"] == []
