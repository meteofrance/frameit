"""Combined numerical validation and isolated simulation computation benchmark."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from importlib import resources
from pathlib import Path

from frameit.testing.artifacts import atomic_json, environment_metadata, utc_now


def run_all_tests(
    output: Path, *, data_root: Path | None = None,
    utrack_weights: Path | None = None, log_level: str | None = None,
) -> dict:
    """Run both suites even after failures, retaining separate timings and artifacts."""
    output = Path(output).expanduser().resolve()
    ci = data_root is None
    root = (
        Path(str(resources.files("frameit.testing").joinpath("ci_dataset")))
        if ci else Path(data_root)
    ).expanduser().resolve()
    if output == root or root in output.parents or output in root.parents:
        raise ValueError("Data and test output trees must not overlap")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Test output must be a fresh directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    from frameit.testing.matrix import run_matrix
    started = time.perf_counter()
    report = {
        "artifact_type": "all_tests", "started_at": utc_now(),
        "environment": environment_metadata(),
    }
    numerical_start = time.perf_counter()
    env = dict(os.environ, PYTHONNOUSERSITE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    # Explicit paths/configuration make installed-wheel runs independent of the CWD.
    tests = Path(str(resources.files("frameit.testing.numerical")))
    if not tests.is_dir():
        raise FileNotFoundError(f"Packaged numerical tests are missing: {tests}")
    command = [
        sys.executable, "-m", "pytest", str(tests), "-c", os.devnull,
        "-ra", f"--junitxml={output / 'numerical.xml'}",
    ]
    with (output / "numerical.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env)
    report["numerical"] = {
        "exit_code": result.returncode, "duration_s": time.perf_counter() - numerical_start,
        "log": "numerical.log", "junit": "numerical.xml",
    }
    qualification_start = time.perf_counter()
    with (output / "qualification.log").open("w", encoding="utf-8") as log:
        qualification = subprocess.run(
            [sys.executable, "-m", "frameit.testing.polar_qualification", "--output",
             str(output / "qualification")], stdout=log, stderr=subprocess.STDOUT, env=env,
        )
    report["scientific_qualification"] = {
        "exit_code": qualification.returncode,
        "duration_s": time.perf_counter() - qualification_start,
        "log": "qualification.log", "report": "qualification/qualification.json",
        "summary": "qualification/summary.json",
    }
    matrix_start = time.perf_counter()
    try:
        matrix = run_matrix(
            root, output / "matrix", ci=ci, profile="full", keep_going=True,
            utrack_weights=utrack_weights, log_level=log_level,
            benchmark=True,
        )
    except (ValueError, OSError, ImportError) as exc:
        matrix = {"exit_code": 2, "results": [], "reason": str(exc)}
    report["matrix"] = {
        "exit_code": matrix["exit_code"], "duration_s": time.perf_counter() - matrix_start,
        "report": "matrix/run.json", "reason": matrix.get("reason", ""),
    }
    cases = [
        {"id": case["id"], "computation_s": case["computation_s"],
         "sections_s": case.get("timing_sections_s", {})}
        for case in matrix["results"]
        if case["status"] == "PASS" and "computation_s" in case
    ]
    report["benchmark"] = {
        "metric": "wall-clock seconds in tracking + extraction + polar_projection",
        "excluded": ["imports", "worker startup", "loading_data", "Netcdf export",
                     "product checks", "numerical tests", "scientific qualification"],
        "cases": cases, "computation_s": sum(case["computation_s"] for case in cases),
        "scope": "successful matrix cases only; single run, no cache flushing",
    }
    codes = (result.returncode, qualification.returncode, matrix["exit_code"])
    report["exit_code"] = 130 if 130 in codes or -2 in codes else (
        2 if any(code not in (0, 1) for code in codes) else int(any(codes))
    )
    report["duration_s"] = time.perf_counter() - started
    report["finished_at"] = utc_now()
    atomic_json(output / "all-tests.json", report)
    return report
