"""P4 independent candidate evaluation and fail-closed production boundaries."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from frameit.io.fa_backend import request_fa
from frameit.io.fa_contracts import native_descriptor, resolve_descriptor
from frameit.io.fa_worker import _inspect
from frameit.testing import fa_spectral_probe


def spectral_descriptor():
    return native_descriptor("S001TEMPERATURE", 17,
                             {"exists": True, "spectral": True, "packing": 103, "bits": 18,
                              "truncation": 0, "laplacian": 0}, {},
                             {"KTYPTR": -7, "KTRONC": 3, "KNXLON": 12, "KNLATI": 12}, {}, {})


def test_spectral_facts_preserve_native_words_without_inventing_dimensions_or_meaning():
    raw = spectral_descriptor()
    native = raw["native"]
    assert native["representation"] == "spectral" and native["shape"] is None
    assert native["word_count"] == 17  # not the 144 gridpoints or a coefficient count
    contract = native["spectral_contract"]
    assert contract["native_header"] == {"KTYPTR": -7, "KTRONC": 3}
    for key in ("coefficient_count", "coefficient_order", "space", "normalization",
                "transform_truncation"):
        assert contract[key] is None
    assert native["encoding"]["truncation"] == 0  # FANION under-truncation, not KTRONC
    assert json.loads(json.dumps(raw, allow_nan=False)) == raw
    with pytest.raises(ValueError, match="spectral-to-grid execution is gated"):
        resolve_descriptor(raw, {"units": "K", "kind": "continuous",
                                 "temporal_kind": "instantaneous", "allow_unscaled": True})
    for operation in ("decode", "dataset", "extract", "polar", "diagnostic"):
        assert raw["eligibility"][operation] == "blocked"


def test_selected_spectral_rejected_before_payload_or_library_discovery():
    calls = []

    def flags(unit, prefix, level, suffix):
        calls.append(prefix + suffix)
        return True, prefix == "S001", 103 if prefix == "S001" else 0, 18, 0, 0

    fa = SimpleNamespace(
        get_facst=lambda: (),
        wfacies=lambda header: (
            -7, 0., 0., 0., 0., 3, 12, 12, np.zeros(8), np.zeros(8),
            np.zeros(16), 1, 101325., np.zeros(2), np.zeros(2), False),
        wfadiex=lambda unit: [2026, 1, 1, 0, 0] + [0] * 17,
        wfalsif=lambda unit: "ALD", wfanion=flags,
    )  # No physical reader or transform module provided.
    entries = iter([("S001TEMPERATURE", 17, 1), ("CLSTEMPERATURE", 145, 2)])
    lfi = SimpleNamespace(wlfipos=lambda unit: None, wlfinaf=lambda unit: (2,),
                          wlficas=lambda unit, advance: next(entries))
    request = {"profile": "arome_history", "fields": ["S001TEMPERATURE"]}
    with pytest.raises(ValueError, match="gated.*packing=103, bits=18"):
        _inspect(fa, lfi, 1, "header", request)
    entries = iter([("S001TEMPERATURE", 17, 1), ("CLSTEMPERATURE", 145, 2)])
    info = _inspect(fa, lfi, 1, "header", {**request, "validate_selection": False})
    assert info["field_descriptors"]["S001TEMPERATURE"]["native"]["shape"] is None
    assert info["fields"]["S001TEMPERATURE"]["spectral"] is True
    calls.clear()
    entries = iter([("S001TEMPERATURE", 17, 1), ("CLSTEMPERATURE", 145, 2)])
    info = _inspect(fa, lfi, 1, "header", {**request, "fields": ["CLSTEMPERATURE"]})
    assert calls == ["CLSTEMPERATURE"]  # Unselected spectral records are not even probed.
    assert info["field_descriptors"]["CLSTEMPERATURE"]["native"]["shape"] == [12, 12]


@pytest.mark.parametrize("representation", ["spectral", "unknown", "blocked_gridpoint"])
def test_coefficients_cannot_masquerade_as_gridpoint_values(tmp_path, monkeypatch, representation):
    descriptor = spectral_descriptor()
    if representation != "spectral":
        descriptor["native"]["representation"] = (
            "gridpoint" if representation == "blocked_gridpoint" else representation)

    def child(argv, **kwargs):
        # Even grid-shaped bytes and the right dtype must not bypass representation admission.
        (Path(argv[-1]) / "response.json").write_text(json.dumps({
            "ok": True, "result": {"protocol_version": 1, "dtype": "float64", "shape": [12, 12],
                                    "field_descriptors": {"S001TEMPERATURE": descriptor}}}))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def forbidden(*args, **kwargs):
        raise AssertionError("unqualified transfer must be rejected before loading any array")

    monkeypatch.setattr(subprocess, "run", child)
    monkeypatch.setattr(np, "load", forbidden)
    with pytest.raises(ValueError, match="coefficients cannot be returned as values"):
        request_fa({"operation": "read", "path": "unopened.fa", "fields": ["S001TEMPERATURE"],
                    "allow_unscaled": True})


def test_missing_or_different_candidate_dependency_is_actionable(monkeypatch):
    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(fa_spectral_probe, "version", missing)
    with pytest.raises(ValueError, match="Missing optional spectral test dependency"):
        fa_spectral_probe._probe()
    monkeypatch.setattr(fa_spectral_probe, "version", lambda name: "2.0.0")
    with pytest.raises(ValueError, match="requires ectrans4py==1.6.0"):
        fa_spectral_probe._probe()


@pytest.mark.parametrize("failure", ["crash", "timeout"])
def test_native_probe_failure_cleanup_and_atomic_report(tmp_path, monkeypatch, failure):
    original = subprocess.run
    monkeypatch.setenv("ECCODES_DEFINITION_PATH", "/parent-only/definitions")

    def child(argv, **kwargs):
        assert kwargs["timeout"] == 30
        assert kwargs["env"]["OMP_NUM_THREADS"] == "1"
        assert "ECCODES_DEFINITION_PATH" not in kwargs["env"]
        # Exercise real process death/timeout without crashing a particular native package.
        if failure == "crash":
            script = ("import os, resource, signal; "
                      "resource.setrlimit(resource.RLIMIT_CORE, (0,0)); "
                      "os.kill(os.getpid(), signal.SIGSEGV)")
        else:
            script = "import time; time.sleep(10)"
            kwargs["timeout"] = .1
        return original([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr(subprocess, "run", child)
    output = tmp_path / failure
    result = fa_spectral_probe.run_probe(output)
    assert result["status"] == "failed" and result["production_spectral_fa"] == "blocked"
    assert ("(-11)" if failure == "crash" else "timed out") in result["error"]
    assert list(output.iterdir()) == [output / "report.json"]
    assert json.loads((output / "report.json").read_text()) == result
    before = (output / "report.json").read_bytes()
    with pytest.raises(FileExistsError):
        fa_spectral_probe.run_probe(output)
    assert (output / "report.json").read_bytes() == before


def test_spectral_module_discovery_never_loads_optional_packages():
    result = subprocess.run([sys.executable, "-c", """
import importlib.abc
import sys
class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'ectrans4py', 'falfilfa4py', 'eccodes', 'cfgrib', 'epygram'}:
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, NoNative())
import frameit.io.fa_worker
import frameit.io.fa_utils
import frameit.testing.fa_spectral_probe
assert not {'ectrans4py', 'falfilfa4py', 'eccodes', 'cfgrib', 'epygram'} & sys.modules.keys()
"""], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(importlib.util.find_spec("ectrans4py") is None,
                    reason="optional pinned fa-spectral-test candidate not installed")
def test_native_candidate_against_independent_fourier_modes(tmp_path):
    result = fa_spectral_probe.run_probe(tmp_path / "candidate")
    assert result["status"] == "passed_limited", result
    assert result["production_spectral_fa"] == "blocked" and result["blockers"]
    assert result["versions"]["ectrans4py"] == "1.6.0"
    assert [case["coefficient_count"] for case in result["cases"]] == [44, 64, 24]
    assert sum(len(case["maximum_errors"]) for case in result["cases"]) == 36
    errors = [error for case in result["cases"] for error in case["maximum_errors"].values()]
    assert max(errors) < 5.e-13
    assert "ectrans4py" not in sys.modules and "falfilfa4py" not in sys.modules
