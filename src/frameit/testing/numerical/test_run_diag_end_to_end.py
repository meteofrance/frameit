import csv
import json
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr

from frameit.testing.numerical.test_run_diag_lifecycle import run_diag, snapshot, write_request
from frameit.testing.numerical.test_run_diag_sources import vortex_parent
from frameit.testing.numerical.test_v3_run_state import record


def diag(cfg, *args):
    process = subprocess.run(
        [sys.executable, "-m", "frameit", "run-diag", str(cfg), "--json", *args],
        capture_output=True,
        text=True,
    )
    assert process.stdout.startswith("{"), process.stderr
    report = json.loads(process.stdout)
    return process.returncode, report


def test_original_and_crop_equivalent(tmp_path):
    cfg, raw, path, root = vortex_parent(tmp_path)
    before = snapshot(root)
    code, check = diag(cfg, "--check")
    assert code == 0 and check["report_version"] == 1, check
    assert not (root / "diagnostics").exists()
    code, original = diag(cfg)
    assert code == 0 and original["data"]["plan"]["committed"], original
    raw["diagnostics"]["best_track"]["input"]["kind"] = "model_grid"
    write_request(cfg, raw)
    path.unlink()
    code, cropped = diag(cfg)
    assert code == 0 and cropped["data"]["plan"]["committed"], cropped
    assert snapshot(root) == before

    results = []
    for report in (original, cropped):
        from pathlib import Path

        attempt = Path(report["data"]["plan"]["attempt_directory"])
        with xr.open_dataset(attempt / "best_track/model_best_track.nc") as ds:
            assert ds.sizes["time"] == 2
            assert ds.wind_radius.dims == ("time", "threshold", "quadrant")
            assert ds.wind_radius.attrs["units"] == "m"
            assert ds.maximum_wind.attrs["units"] == "m s-1"
            assert ds.central_pressure.values.tolist() == [98000.0, 98000.0]
            assert "threshold_not_reached" in ds.wind_radius_reasons.attrs["flag_meanings"]
            np.testing.assert_array_equal(ds.latitude.values, [-20, -20])
            results.append(ds[["maximum_wind", "central_pressure", "wind_radius", "rmw"]].load())
        with (attempt / "best_track/rsmc_comparison.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        assert len(rows) == 1 and len(rows[0]) == 29
        assert rows[0]["ventmax"] and rows[0]["pression"] == "980"
        assert rows[0]["ci"] == rows[0]["typa"] == ""
        status = subprocess.run(
            [sys.executable, "-m", "frameit", "status", str(attempt)],
            capture_output=True,
            text=True,
        )
        assert status.returncode == 0 and "completed" in status.stdout.lower()
    xr.testing.assert_allclose(*results, atol=1e-6, rtol=0)


@pytest.mark.parametrize(
    ("policy", "availability", "code"),
    [
        ("require_10min", "report", 0),
        ("require_10min", "error", 1),
        ("native_proxy", "report", 0),
        ("native_proxy", "error", 0),
    ],
)
def test_wind_time_and_unavailability_policy(tmp_path, policy, availability, code):
    cfg, raw, _, root = vortex_parent(tmp_path, kind="model_grid", temporal="instantaneous")
    raw["diagnostics"]["best_track"].update(wind_time_policy=policy, on_unavailable=availability)
    write_request(cfg, raw)
    status, report = diag(cfg)
    assert status == code, report
    if status:
        assert report["errors"][0]["code"] == "E2004"
    else:
        (attempt,) = (root / "diagnostics").iterdir()
        with xr.open_dataset(attempt / "best_track/model_best_track.nc") as ds:
            assert ds.maximum_wind.isnull().all()
            assert bool(ds.maximum_wind_native_proxy.notnull().all()) == (policy == "native_proxy")


def test_missing_wind_height_does_not_hide_available_pressure(tmp_path):
    cfg, _, _, root = vortex_parent(tmp_path, kind="original", declared_height=None)
    code, report = diag(cfg)
    assert code == 0, report
    (attempt,) = (root / "diagnostics").iterdir()
    with xr.open_dataset(attempt / "best_track/model_best_track.nc") as ds:
        assert bool(ds.maximum_wind.isnull().all())
        assert ds.central_pressure.values.tolist() == [98000.0, 98000.0]
        reasons = ds.maximum_wind_reasons.attrs["flag_meanings"].split()
        mask = 1 << reasons.index("physical_definition_unverified")
        assert np.all(ds.maximum_wind_reasons.values & mask)


@pytest.mark.parametrize("outside", ["high_core", "zero_wedge"])
def test_declared_invalid_wind_is_missing_support(tmp_path, outside):
    def invalid_wind(ds):
        values = ds.wind10.values.copy()
        if outside == "high_core":
            values[:, 22, 22] = 200.0
            ds.wind10.attrs["valid_range"] = [0.0, 60.0]
        else:
            values[:, 22:, 22:] = 0.0
            ds.wind10.attrs.update(valid_min=1.0, valid_max=60.0)
        ds.wind10.data = values

    key = "ventmax" if outside == "high_core" else "extension_28kt_ne"
    cfg, _, _, root = vortex_parent(tmp_path, kind="model_grid", edit_input=invalid_wind)
    report = run_diag(cfg)
    assert report["status"] == "ok", report["errors"]
    (attempt,) = (root / "diagnostics").iterdir()
    with (attempt / "best_track/rsmc_comparison.csv").open(newline="") as stream:
        (row,) = csv.DictReader(stream, delimiter=";")
    assert row[key] == ""
    assert row["pression"] == "980"
    assert row["extension_28kt_so"]


def test_scalar_magnitude_of_mean_components_remains_a_proxy(tmp_path):
    def mark_derived(ds):
        ds.wind10.attrs["derivation"] = "magnitude_of_mean_components"

    cfg, raw, _, root = vortex_parent(tmp_path, kind="model_grid", edit_input=mark_derived)
    raw["diagnostics"]["best_track"]["wind_time_policy"] = "native_proxy"
    write_request(cfg, raw)
    report = run_diag(cfg)
    assert report["status"] == "ok", report["errors"]
    (attempt,) = (root / "diagnostics").iterdir()
    with xr.open_dataset(attempt / "best_track/model_best_track.nc") as ds:
        assert bool(ds.maximum_wind.isnull().all())
        assert bool(ds.maximum_wind_native_proxy.notnull().all())


def test_legacy_uses_only_a_recorded_public_track(tmp_path):
    cfg, raw, source, root = vortex_parent(tmp_path, kind="model_grid", export_track=True)
    request_record = record(root, "run-request.yaml")
    for key in ("run_context", "run_attempt_id"):
        del request_record[key]
    write_request(root / "run-request.yaml", request_record)
    for name in ("run-status.yaml", "run-provenance.yaml"):
        value = record(root, name)
        for key in ("run_context", "run_attempt_id", "records"):
            del value[key]
        for item in value["products"]:
            del item["identity"]
        if name == "run-provenance.yaml":
            del value["sources"]["weather"]["frozen_inventory"]
        write_request(root / name, value)
    source.unlink()
    code, report = diag(cfg, "--check")
    assert code == 0, report
    assert report["data"]["plan"]["identity_scheme"] == "legacy_records_and_track_sha256"
    raw["diagnostics"]["best_track"]["input"]["kind"] = "original"
    write_request(cfg, raw)
    code, report = diag(cfg, "--check")
    assert code == 1 and "frozen original file identities" in report["errors"][0]["message"]
    raw["diagnostics"]["best_track"]["input"]["kind"] = "model_grid"
    write_request(cfg, raw)
    for name in ("run-status.yaml", "run-provenance.yaml"):
        value = record(root, name)
        value["products"] = [item for item in value["products"] if item["role"] != "track"]
        write_request(root / name, value)
    code, report = diag(cfg, "--check")
    assert code == 1 and "recorded public track" in report["errors"][0]["message"]
