"""C5 disposable-process, transfer and failed-publication contracts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

from frameit.core.execution import execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.io.fa_backend import request_fa
from frameit.io.fa_contracts import native_descriptor
from frameit.testing.numerical.test_fa_cubes import NATIVE
from frameit.testing.numerical.test_fa_pipeline import primary_pair_document


def transfer_response(shape):
    descriptor = native_descriptor(
        "SFX.T2M", 63, {"exists": True, "spectral": False}, {},
        {"KTYPTR": -11, "KNLATI": 7, "KNXLON": 9}, {}, {})
    return {"ok": True, "result": {
        "protocol_version": 1, "shape": shape, "dtype": "float64", "backend_versions": {},
        "field_descriptors": {"SFX.T2M": descriptor}}}


FAILING_HELPER = """
import json, os, resource, signal, sys, time
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
mode, destination, pidfile, response = json.loads(sys.argv[1])
request = json.load(sys.stdin)
assert all(os.environ[n] == '1' for n in
           ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'))
assert not any(n in os.environ for n in
               ('ECCODES_DEFINITION_PATH', 'ECCODES_SAMPLES_PATH',
                'GRIB_DEFINITION_PATH', 'GRIB_SAMPLES_PATH'))
Path(pidfile).write_text(str(os.getpid()))
destination = Path(destination)
(destination / 'values.npy').write_bytes(b'\\x93NUMPY')
if mode == 'crash':
    os.kill(os.getpid(), signal.SIGSEGV)
elif mode == 'timeout':
    time.sleep(60)
elif mode == 'invalid_json':
    (destination / 'response.json').write_text('{')
else:
    if mode == 'success':
        import numpy as np
        np.save(destination / 'values.npy', np.array([[float('nan'), 0.]]))
    (destination / 'response.json').write_text(json.dumps(response))
"""


@pytest.mark.parametrize("failure, message", [
    ("crash", r"process failed \(-11\)"),
    ("timeout", "timed out"),
    ("invalid_json", "Invalid FA decoder response.*surface.fa"),
    ("truncated_npy", "Invalid native array transfer.*surface.fa"),
])
def test_failed_helper_is_reaped_transfer_removed_and_next_request_succeeds(
    tmp_path, monkeypatch, failure, message,
):
    original = subprocess.run
    destinations = []
    mode = failure
    pidfile = tmp_path / "child.pid"
    for name in ("ECCODES_DEFINITION_PATH", "ECCODES_SAMPLES_PATH",
                 "GRIB_DEFINITION_PATH", "GRIB_SAMPLES_PATH"):
        monkeypatch.setenv(name, "parent-only")

    def injected(argv, **kwargs):
        destinations.append(Path(argv[-1]))
        return original([sys.executable, "-c", FAILING_HELPER, json.dumps([
            mode, argv[-1], str(pidfile), transfer_response([1, 2])])], **kwargs)

    monkeypatch.setattr(subprocess, "run", injected)
    request = {"operation": "read", "path": "surface.fa", "fields": ["SFX.T2M"],
               "timeout_seconds": 1 if failure == "timeout" else 30}
    with pytest.raises(ValueError, match=message):
        request_fa(request)
    assert pidfile.is_file(), "Injected helper never reached its failure point"
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)
    assert all(not path.exists() for path in destinations)
    mode = "success"
    actual = request_fa({**request, "timeout_seconds": 30})["values"]
    np.testing.assert_array_equal(actual, [[np.nan, 0.]])
    assert type(actual) is np.ndarray  # No mapping into the deleted transfer directory.
    assert all(not path.exists() for path in destinations)
    assert os.environ["ECCODES_DEFINITION_PATH"] == "parent-only"


@pytest.mark.parametrize("shape", [[1001, 1001], [-1, 2], [True, 2], [1, 1, 1]])
def test_invalid_transfer_shape_fails_before_opening_array(tmp_path, monkeypatch, shape):
    destinations = []

    def response(argv, **kwargs):
        path = Path(argv[-1])
        destinations.append(path)
        (path / "response.json").write_text(json.dumps(transfer_response(shape)))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid/over-budget transfer reached array loading")

    monkeypatch.setattr(subprocess, "run", response)
    monkeypatch.setattr(np, "load", forbidden)
    with pytest.raises(ValueError, match="Invalid native array transfer"):
        request_fa({"operation": "read", "path": "surface.fa", "fields": ["SFX.T2M"],
                    "max_points": 63})
    assert all(not path.exists() for path in destinations)


@pytest.mark.parametrize("data", [np.zeros((2, 1)), np.zeros((1, 2), dtype="int64")])
def test_npy_header_is_checked_without_eager_array_allocation(monkeypatch, data):
    original = np.load

    def response(argv, **kwargs):
        path = Path(argv[-1])
        np.save(path / "values.npy", data, allow_pickle=False)
        (path / "response.json").write_text(json.dumps(transfer_response([1, 2])))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def mapped(*args, **kwargs):
        assert kwargs["mmap_mode"] == "r" and kwargs["allow_pickle"] is False
        return original(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", response)
    monkeypatch.setattr(np, "load", mapped)
    with pytest.raises(ValueError, match="Invalid native array transfer.*dtype/shape"):
        request_fa({"operation": "read", "path": "surface.fa", "fields": ["SFX.T2M"]})


@NATIVE
@pytest.mark.parametrize("synchronous", [True, False])
def test_primary_pair_failed_transfer_never_publishes_surface_product(
    tmp_path, synchronous,
):
    raw = primary_pair_document(tmp_path, synchronous=synchronous)
    sources = raw["input"]["sources"]
    originals = {Path(path): Path(path).read_bytes() for source in sources.values()
                 for path in source["input"]["files"]}
    # A selected executable also reaches spawned exporters; monkeypatches do not.
    shim = tmp_path / "failing-helper"
    shim.write_text(f"#!{sys.executable}\n" + """
import json, subprocess, sys
from pathlib import Path
request = json.load(sys.stdin)
if request['operation'] == 'read':
    destination = Path(sys.argv[-1])
    with Path(DESTINATIONS).open('a') as log:
        log.write(str(destination) + '\\n')
    (destination / 'values.npy').write_bytes(b'\\x93NUMPY')
    response = RESPONSE
    descriptor = response['result']['field_descriptors'].pop('SFX.T2M')
    descriptor['native_id'] = request['fields'][0]
    response['result']['field_descriptors'] = {request['fields'][0]: descriptor}
    (destination / 'response.json').write_text(json.dumps(response))
else:
    result = subprocess.run([REAL_HELPER, *sys.argv[1:]], input=json.dumps(request),
                            text=True, timeout=30)
    sys.exit(result.returncode)
""".replace("RESPONSE", repr(transfer_response([1, 2]))).replace(
        "REAL_HELPER", repr(sources["surfex"]["input"]["fa"]["python_executable"])).replace(
        "DESTINATIONS", repr(str(tmp_path / "transfers.txt"))))
    shim.chmod(0o755)
    sources["surfex"]["input"]["fa"]["python_executable"] = str(shim)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises((ValueError, RuntimeError), match="Invalid native array transfer"):
        execute_simulation(conf)
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["state"] == "failed" and not status.get("products")
    assert not (conf.output_dir / "products/primary-pair.cart.surfex.surface.nc").exists()
    assert not (conf.output_dir / ".frameit-run.lock").exists()
    assert not list(conf.output_dir.rglob("*.partial"))
    destinations = (tmp_path / "transfers.txt").read_text().splitlines()
    assert destinations and all(not Path(path).exists() for path in destinations)
    assert all(path.read_bytes() == before for path, before in originals.items())
