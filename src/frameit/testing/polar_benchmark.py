"""Isolated cached/uncached polar workloads with numerical equivalence checks.

Run ``python -m frameit.testing.polar_benchmark --output /path/to/fresh/results``.
Each variant uses a fresh spawned worker so native RSS high-water marks do not
inherit the other variant's allocations. Computation and export are separated.
"""

from __future__ import annotations

import argparse
import copy
import multiprocessing
import os
import traceback
from importlib import resources
from pathlib import Path
from time import perf_counter

from frameit.testing.artifacts import atomic_json, environment_metadata, read_json, utc_now

DEFAULT_CASES = (
    "arome_batsirai_fixed_polar", "arome_batsirai_prescribed_polar",
    "mnh_chido_fixed_polar", "mnh_chido_wind_pressure_polar",
)
DEFAULT_FULL_CASES = (
    "arome_batsirai_fixed_polar", "arome_batsirai_wind_pressure_polar",
    "mnh_chido_fixed_polar", "mnh_chido_wind_pressure_polar",
)


def _benchmark_worker(case, root, output, mode, cache_size, completion):
    output, completion = Path(output), Path(completion)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "worker.log").open("w", encoding="utf-8", buffering=1) as stream:
        os.dup2(stream.fileno(), 1)
        os.dup2(stream.fileno(), 2)
        started = perf_counter()
        try:
            from frameit.core.execution import ExecutionOptions, execute_simulation
            from frameit.core.settings_class import SimulationConfig
            from frameit.processing.polar.performance import process_peak_rss_bytes
            from frameit.testing.catalog import resolve_case
            from frameit.testing.checks import check_products

            resolved = resolve_case(case, Path(root), output / "products", mode=mode)
            if resolved["preflight"] != "READY":
                raise ValueError(f"Benchmark case unavailable: {resolved['reason']}")
            config = copy.deepcopy(resolved["config"])
            config.update(polar_regrid_cache_size=cache_size, polar_profile=True)
            target_motion = "case tracker"
            if mode == "ci" and case["id"] == "arome_batsirai_prescribed_polar":
                import numpy as np
                import xarray as xr

                # Small continuous motion inside the same frozen extraction
                # cell exercises moving target weights without enlarging the CI domain.
                times = np.array(resolved["expected"]["times"], dtype="datetime64[ns]")
                latitude, longitude = config["fix_subdomain_center"]
                track = xr.Dataset(
                    {"lon": ("time", longitude + np.linspace(-.001, .001, len(times))),
                     "lat": ("time", np.full(len(times), latitude))}, coords={"time": times},
                )
                track_path = output / "continuous-origin.nc"
                track.to_netcdf(track_path)
                config["prescribed_track_file"] = str(track_path)
                target_motion = "continuous longitude +/-0.001 degree within the fixed CI cell"
            result = execute_simulation(
                SimulationConfig.from_mapping_with_model_preset(config),
                ExecutionOptions(benchmark=True, synchronous_export=True, log_level="WARNING"),
                input_files=tuple(Path(path) for path in resolved["input_files"]),
            )
            checks = check_products(resolved, result.products)
            if not checks["ok"]:
                raise ValueError(checks["reason"])
            atomic_json(completion, {
                "ok": True, "case": case["id"], "cache_size": cache_size,
                "target_motion": target_motion, "result": result.to_dict(),
                "process_peak_rss_bytes": process_peak_rss_bytes(),
                "worker_wall_s": perf_counter() - started,
            })
        except BaseException as exc:
            traceback.print_exc(file=stream)
            atomic_json(completion, {"ok": False, "case": case["id"],
                                     "reason": f"{type(exc).__name__}: {exc}"})


def _compare_outputs(first, second):
    import numpy as np
    import xarray as xr

    def products(record):
        return {(p["role"], p["group"]): p["path"] for p in record["result"]["products"]
                if p["role"] == "polar"}

    a, b = products(first), products(second)
    if not a or set(a) != set(b):
        raise ValueError("Benchmark variants do not have matching polar products")
    maximum = 0.
    for key in a:
        with xr.open_dataset(a[key]) as cached, xr.open_dataset(b[key]) as uncached:
            xr.testing.assert_allclose(cached, uncached, rtol=1e-12, atol=1e-12)
            for name in cached.data_vars:
                if np.issubdtype(cached[name].dtype, np.number):
                    difference = np.abs(cached[name] - uncached[name])
                    if bool(np.isfinite(difference).any()):
                        maximum = max(maximum, float(difference.max(skipna=True)))
    return maximum


def run_polar_benchmark(output, *, data_root=None, case_ids=DEFAULT_CASES, repeats=1, timeout=600):
    from frameit.testing.catalog import load_cases

    if repeats < 1 or timeout <= 0:
        raise ValueError("Benchmark repeats and timeout must be positive")
    output = Path(output).expanduser().resolve()
    root = (Path(str(resources.files("frameit.testing").joinpath("ci_dataset")))
            if data_root is None else Path(data_root)).expanduser().resolve()
    if root == output or root in output.parents or output in root.parents:
        raise ValueError("Benchmark input and output trees must not overlap")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Benchmark output must be fresh or empty")
    mode = "ci" if data_root is None else "full"
    if mode == "full" and case_ids == DEFAULT_CASES:
        case_ids = DEFAULT_FULL_CASES
    cases = load_cases(mode=mode, profile="full", patterns=case_ids)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "artifact_type": "polar_interpolation_benchmark", "started_at": utc_now(),
        "environment": environment_metadata(), "runs": [], "comparisons": [],
        "timing_scope": (
            "input preloading, computation, projection application/build and export separated"
        ),
        "memory_scope": (
            "fresh worker process lifetime RSS peak, including imports and input preload"
        ),
    }
    context = multiprocessing.get_context("spawn")
    for case in cases:
        for repetition in range(repeats):
            variants = {}
            # Alternate order on repeat runs to reduce systematic filesystem/order bias.
            order = (8, 0) if repetition % 2 == 0 else (0, 8)
            for capacity in order:
                variant = "cached" if capacity else "uncached"
                directory = output / case["id"] / f"repeat-{repetition + 1:02d}" / variant
                completion = directory / "result.json"
                process = context.Process(target=_benchmark_worker,
                                          args=(case, root, directory, mode, capacity, completion))
                process.start()
                process.join(timeout)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                    if process.is_alive():
                        process.kill()
                        process.join(5)
                    raise TimeoutError(f"Benchmark worker timed out: {case['id']} {variant}")
                if process.exitcode != 0 or not completion.is_file():
                    raise RuntimeError(f"Benchmark worker failed: {case['id']} {variant}")
                record = read_json(completion)
                if not record["ok"]:
                    raise RuntimeError(record["reason"])
                record.update(variant=variant, repetition=repetition + 1)
                report["runs"].append(record)
                variants[variant] = record
            error = _compare_outputs(variants["cached"], variants["uncached"])
            cached_time = variants["cached"]["result"]["timing_sections_s"]["polar_projection"]
            baseline_time = variants["uncached"]["result"]["timing_sections_s"]["polar_projection"]
            report["comparisons"].append({
                "case": case["id"], "repetition": repetition + 1,
                "maximum_numerical_difference": error, "cached_polar_s": cached_time,
                "uncached_polar_s": baseline_time,
                "polar_speedup": baseline_time / cached_time if cached_time else None,
            })
            atomic_json(output / "benchmark.json", report)
    report["finished_at"] = utc_now()
    atomic_json(output / "benchmark.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)
    report = run_polar_benchmark(args.output, data_root=args.data_root,
                                 case_ids=args.cases or DEFAULT_CASES,
                                 repeats=args.repeats, timeout=args.timeout)
    for row in report["comparisons"]:
        print(f"{row['case']}: cached={row['cached_polar_s']:.3f}s "
              f"uncached={row['uncached_polar_s']:.3f}s speedup={row['polar_speedup']:.2f}x "
              f"maximum difference={row['maximum_numerical_difference']:.3g}")
    print(f"Benchmark report: {args.output / 'benchmark.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
