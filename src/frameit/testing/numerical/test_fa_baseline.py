"""P0 failure classification and private-data-free reproducer checks."""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from frameit.io.fa_worker import _inspect
from frameit.testing.numerical.test_fa_io import NATIVE, fa_files


@pytest.mark.parametrize("code", [-91, -93, -94])
def test_selected_native_error_is_never_metadata_fallback(code):
    def failure(*args):
        raise RuntimeError(f"Error code {code} was raised.")

    fa = SimpleNamespace(
        get_facst=lambda: (),
        wfacies=lambda header: (
            0, 0., 0., 0., 0., 0, 7, 9, np.zeros(8), np.zeros(8),
            np.zeros(16), 1, 101325., np.zeros(2), np.zeros(2), False),
        wfadiex=lambda unit: [2026, 1, 1, 0, 0] + [0] * 17,
        wfalsif=lambda unit: "ALD",
        wfanion=failure,
    )
    lfi = SimpleNamespace(wlfipos=lambda unit: None, wlfinaf=lambda unit: (1,),
                          wlficas=lambda unit, advance: ("SURFPRESSION", 1410925, 1))
    request = {"profile": None, "fields": ["SURFPRESSION"]}
    with pytest.raises(ValueError, match=f"unsupported native encoding.*{code}.*"):
        _inspect(fa, lfi, 1, "header", request)
    report = _inspect(fa, lfi, 1, "header", {**request, "validate_selection": False})
    assert report["fields"]["SURFPRESSION"] == {
        "native_error": f"Error code {code} was raised."}
    # Unselected unsupported records do not prevent an index-only operation.
    assert _inspect(fa, lfi, 1, "header", {**request, "fields": []})["fields"] == {}


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_upstream_probe_is_read_only_and_does_not_export_private_paths(tmp_path):
    path = fa_files(tmp_path)[0]
    path.chmod(0o444)
    original = path.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "frameit.testing.fa_native_probe", str(path),
         "CLSTEMPERATURE", "ABSENT"], capture_output=True, text=True, timeout=30,
        check=True)
    report = json.loads(result.stdout)
    assert report["probes"]["CLSTEMPERATURE"]["calls"][0]["flags"][:2] == [True, False]
    absent = report["probes"]["ABSENT"]
    assert absent["length_words"] is None
    assert absent["calls"][0].get("flags", [False])[0] is False
    assert report["size_mtime_unchanged"]
    assert str(tmp_path) not in result.stdout
    assert path.read_bytes() == original
    assert "falfilfa4py" not in sys.modules


def test_probe_module_discovery_does_not_load_optional_native_library():
    result = subprocess.run([sys.executable, "-c", """
import importlib.abc
import sys
class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'falfilfa4py', 'eccodes', 'cfgrib'}:
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, NoNative())
import frameit.testing.fa_native_probe
import frameit.io.fa_worker
assert 'falfilfa4py' not in sys.modules
assert 'eccodes' not in sys.modules
"""], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
