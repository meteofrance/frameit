"""Bounded P4 candidate evaluation, not production spectral FA admission.

Run with --output <fresh-directory>. Only the disposable child imports native
libraries. The fixed analytical modes have declared transform parameters;
they do not establish a native FA coefficient decode or header mapping.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from frameit.testing.artifacts import atomic_json

# (nx, ny, tx, ty, expected inquiry coefficient count). These are library test
# parameters, not a mapping from native FA header words to truncations.
CASES = ((12, 12, 3, 3, 44), (18, 12, 5, 3, 64), (12, 12, 2, 2, 24))
BLOCKERS = [
    "Real 103/18 records: P0 verified flags only, not coefficient decoding/scaling/masks",
    "Release-matched FA header-to-transform, coefficient order/space/normalization contract",
    "Independent trusted real native-grid fields, geometry/zone reference and justified tolerances",
    "Production coefficient/workspace/transfer memory qualification",
]


def _probe():
    """Fresh child only; independent closed-form Fourier truth, no forward transform."""
    try:
        versions = {name: version(name) for name in ("ectrans4py", "ctypesForFortran", "numpy")}
    except PackageNotFoundError as exc:
        raise ValueError("Missing optional spectral test dependency; install the "
                         "fa-spectral-test extra in a disposable environment") from exc
    if versions["ectrans4py"] != "1.6.0" or versions["ctypesForFortran"] != "1.3.0":
        raise ValueError("P4 probe requires ectrans4py==1.6.0 and ctypesForFortran==1.3.0; "
                         "install the optional fa-spectral-test extra in a disposable environment")
    if any(name in sys.modules for name in ("eccodes", "cfgrib", "ectrans4py", "falfilfa4py")):
        raise RuntimeError("Use a fresh native-only probe process")
    import ectrans4py as transform
    import numpy as np

    from frameit.core.runtime import runtime_provenance

    transform.init_env(omp_num_threads=1, no_mpi=True, unlimited_stack=False)
    if transform.__version__ != "1.6.0":
        raise ValueError("Unexpected native ecTrans version; evaluation is version-specific")
    report = {"schema_version": 1, "status": "passed_limited", "production_spectral_fa": "blocked",
              "scope": "ecTrans regional double-Fourier scalar modes only; no FA codec qualified",
              "versions": {**versions, "ecTrans_native": transform.__version__,
                           "python": sys.version.split()[0]},
              "runtime": runtime_provenance(), "blockers": BLOCKERS, "cases": [],
              "resources": {"native_threads": 1, "resolutions": len(CASES),
                            "maximum_gridpoints": 216, "unlimited_stack": False},
              "tolerance": {"rtol": 0., "atol": 5.e-13,
                            "basis": "unit coefficients, <=5 waves, <=216 points, float64; "
                                     "roundoff allowance, not a real-encoding tolerance"}}
    for nx, ny, tx, ty, expected_count in CASES:
        # No crop, remap, Legendre/global transform, derivative or physical diagnosis.
        args = (nx, ny, nx, ny, tx, ty, len(CASES))
        points, count = transform.etrans_inq4py(*args, 1000., 1000.)
        if (points, count) != (nx * ny, expected_count):
            raise ValueError("Unexpected native LAM inquiry dimensions")
        x = 2 * np.pi * np.arange(nx)[None, :] / nx
        y = 2 * np.pi * np.arange(ny)[:, None] / ny
        # File order is four reals per (m,n), m varying fastest. These
        # independent basis functions check both imaginary signs and all four
        # slots. Nonzero modes carry a factor two in each active direction.
        y1 = 4 * (tx + 1)
        modes = [
            ("ZERO", None, 0., np.zeros((ny, nx))),
            ("CONSTANT", 0, 1.25, np.full((ny, nx), 1.25)),
            ("COSX", 4, 1., 2 * np.cos(x) + np.zeros_like(y)),
            ("SINX", 6, 1., -2 * np.sin(x) + np.zeros_like(y)),
            ("COSY", y1, 1., 2 * np.cos(y) + np.zeros_like(x)),
            ("SINY", y1 + 1, 1., -2 * np.sin(y) + np.zeros_like(x)),
            ("CC", y1 + 4, 1., 4 * np.cos(x) * np.cos(y)),
            ("CS", y1 + 5, 1., -4 * np.cos(x) * np.sin(y)),
            ("SC", y1 + 6, 1., -4 * np.sin(x) * np.cos(y)),
            ("SS", y1 + 7, 1., 4 * np.sin(x) * np.sin(y)),
            ("EDGEX", 4 * tx, 1., 2 * np.cos(tx * x) + np.zeros_like(y)),
            ("EDGEY", count - 4, 1., 2 * np.cos(ty * y) + np.zeros_like(x)),
        ]
        errors = {}
        for label, index, amplitude, truth in modes:
            coefficients = np.zeros(count)
            if index is not None:
                coefficients[index] = amplitude
            actual = transform.sp2gp_lam4py(
                *args, count, False, True, 1000., 1000., coefficients)[0]
            if actual.shape != (points,) or not np.isfinite(actual).all():
                raise ValueError("Invalid native transform output")
            actual = actual.reshape(ny, nx)
            np.testing.assert_allclose(actual, truth, rtol=0., atol=5.e-13)
            errors[label] = float(np.max(np.abs(actual - truth)))
        report["cases"].append({"grid_y_x": [ny, nx], "physical_y_x": [ny, nx],
                                "spacing_x_y_m": [1000., 1000.],
                                "truncation_x_y": [tx, ty],
                                "coefficient_count": count,
                                "coefficient_count_origin": "ETRANS_INQ",
                                "coefficient_order": "ecTrans FA order; LREORDER=True",
                                "space": "regional double Fourier", "derivatives": False,
                                "maximum_errors": errors})
    return report


def run_probe(output):
    """Publish a bounded attempt, including native death/timeout, to a fresh directory."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                       MKL_NUM_THREADS="1", PYTHONNOUSERSITE="1")
    for key in ("ECCODES_DEFINITION_PATH", "ECCODES_SAMPLES_PATH"):
        environment.pop(key, None)
    report = {"schema_version": 1, "status": "failed", "production_spectral_fa": "blocked"}
    with tempfile.TemporaryDirectory(prefix="native-", dir=output) as scratch:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "frameit.testing.fa_spectral_probe", "--worker", scratch],
                capture_output=True, text=True, errors="replace", env=environment,
                timeout=30, check=False)
            response = Path(scratch) / "response.json"
            if result.returncode or not response.is_file():
                report["error"] = f"Native spectral probe failed ({result.returncode})"
            else:
                report = json.loads(response.read_text(encoding="utf-8"))
            report["native_diagnostics"] = (result.stdout + result.stderr).strip()
        except subprocess.TimeoutExpired:
            report["error"] = "Native spectral probe timed out (30 seconds)"
    report["timeout_seconds"] = 30
    atomic_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker is not None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        try:
            report = _probe()
        except Exception as exc:
            report = {"schema_version": 1, "status": "failed", "production_spectral_fa": "blocked",
                      "error": f"{type(exc).__name__}: {exc}"}
        atomic_json(args.worker / "response.json", report)
    else:
        report = run_probe(args.output)
        print(json.dumps({"status": report["status"], "report": str(args.output / "report.json")}))
        if report["status"] != "passed_limited":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
