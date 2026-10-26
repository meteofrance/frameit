"""Native FA requests stay isolated even when cfgrib has already been imported."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import numpy as np
import pytest

from frameit.io.fa_backend import collect_fa_diagnostics, inspect_fa, request_fa
from frameit.io.fa_contracts import native_descriptor

NATIVE = importlib.util.find_spec("falfilfa4py") is not None


def fa_files(directory, hours=(0,), *, profile="arome_history", **options):
    paths = [directory / f"native-{hour:03d}.fa" for hour in hours]
    request = [{"path": str(path), "hours": hour, "offset": hour * .5,
                "profile": profile, **options} for hour, path in zip(hours, paths, strict=True)]
    result = subprocess.run([sys.executable, "-m", "frameit.testing.fa_fixture"],
                            input=json.dumps(request), text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return paths


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_native_index_values_freshness_and_read_only(tmp_path):
    # Deliberately initialize the opposing runtime before any FA transaction.
    ec = pytest.importorskip("eccodes")
    path = fa_files(tmp_path, (1,))[0]
    path.chmod(0o444)
    before = path.read_bytes()
    info = inspect_fa(path, "arome_history", ["CLSTEMPERATURE"])
    assert info["valid_time"] == "2026-01-01T01:00:00"
    request = {"operation": "read", "path": str(path), "profile": "arome_history",
               "fields": ["CLSTEMPERATURE"], "identity": info["identity"],
               "zone": [0, 9, 0, 7], "key": [[2, 5, None], [3, 6, None]]}
    actual = request_fa(request)["values"]
    np.testing.assert_array_equal(actual, 280.5 + 10 * np.arange(2, 5)[:, None] + np.arange(3, 6))
    assert path.read_bytes() == before
    assert "falfilfa4py" not in sys.modules
    message = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        assert ec.codes_get_long(message, "Ni") > 0
    finally:
        ec.codes_release(message)
    request["identity"] = [0, 0]
    with pytest.raises(ValueError, match="changed since inventory"):
        request_fa(request)


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_surfex_typed_directory_and_profile_rejection(tmp_path):
    path = fa_files(tmp_path, profile="surfex_history")[0]
    info = inspect_fa(path, "surfex_history", ["SFX.T2M"])
    assert info["surfex_metadata"]["PROGRAM"] == "AROME"
    assert info["fields"]["SFX.T2M"]["surfex_descriptor"] == {
        "TYPE": "X1", "MASK": "FULL", "DIM1": 63, "DIM2": -1}
    with pytest.raises(ValueError, match="conflicts with profile"):
        inspect_fa(path, "arome_history")
    with pytest.raises(ValueError, match="Missing requested FA record"):
        inspect_fa(path, "surfex_history", ["SFX.UNKNOWN"])


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_surfex_state_clock_conflict_is_not_silently_substituted(tmp_path):
    path = fa_files(tmp_path, profile="surfex_history", state_hours=2)[0]
    with pytest.raises(ValueError, match="SFX.DTCUR conflicts"):
        inspect_fa(path, "surfex_history", ["SFX.T2M"])
    report = inspect_fa(path, None, validate_selection=False)
    assert report["surfex_metadata"]["STATE_TIME_MATCHES_HEADER"] is False


def test_worker_death_and_unscaled_warning_are_actionable(tmp_path, monkeypatch):
    from pathlib import Path

    def fake(argv, **kwargs):
        destination = Path(argv[-1])
        np.save(destination / "values.npy", np.array([[np.nan, 0.]]))
        (destination / "response.json").write_text(json.dumps({
            "ok": True, "result": {"shape": [1, 2], "dtype": "float64", "backend_versions": {},
                                    "protocol_version": 1,
                                    "field_descriptors": {"SFX.T2M": native_descriptor(
                                        "SFX.T2M", 2, {"exists": True, "spectral": False}, {},
                                        {"KTYPTR": -1, "KNLATI": 1, "KNXLON": 2}, {}, {})}}}))
        return subprocess.CompletedProcess(
            argv, 0, stdout="has no encoded FMULTM and FMULTE", stderr="")

    monkeypatch.setattr(subprocess, "run", fake)
    request = {"operation": "read", "path": "native.fa", "fields": ["SFX.T2M"],
               "diagnostics_path": str(tmp_path / "decoder.jsonl")}
    with pytest.raises(ValueError, match="missing native scaling metadata"):
        request_fa(request)
    values = request_fa({**request, "allow_unscaled": True})["values"]
    assert np.isnan(values[0, 0]) and values[0, 1] == 0
    summary = collect_fa_diagnostics(tmp_path, [{"decoder_log": "decoder.jsonl"}])
    scaling = summary["field_observations"]["native.fa"]["SFX.T2M"]["scaling"]
    assert scaling["status"] == "missing" and scaling["multiplier"] is None
    assert scaling["fallback"] == "identity_explicit_opt_in"
    assert summary["decode_requests"] == 2 and summary["warnings"]
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw:
                        subprocess.CompletedProcess(argv, -11, stdout="", stderr="native crash"))
    with pytest.raises(ValueError, match=r"process failed \(-11\).*native crash"):
        request_fa(request)
