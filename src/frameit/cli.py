# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0


from __future__ import annotations

import os
import sys
from pathlib import Path


def _sanitize_sys_path_user_site() -> None:
    """
    Ensure FrameIt CLI does not import packages from the user site-packages (e.g. ~/.local),
    which can shadow the conda environment and break version consistency.
    """
    # Fast path: if PYTHONNOUSERSITE is set, user site is usually not injected.
    # Still sanitize defensively because PYTHONPATH or .pth files may add ~/.local manually.
    user_base = Path(os.path.expanduser("~/.local")).resolve()

    new_path: list[str] = []
    for p in sys.path:
        try:
            rp = Path(p).resolve()
        except Exception:
            new_path.append(p)
            continue

        # Drop typical user installs, including ~/.local and user site-packages.
        if user_base in rp.parents or rp == user_base:
            continue

        new_path.append(p)

    sys.path[:] = new_path


_sanitize_sys_path_user_site()

# Imports only after sys.path is sanitized
import argparse  # noqa: E402
import logging  # noqa: E402
import platform  # noqa: E402
from typing import Any  # noqa: E402

_DEFAULT_INSTITUTION = "LACy, Université de La Réunion, CNRS, Météo-France"


def _package_version(pkg_name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(pkg_name)
    except Exception:
        return None


def _probe_module(mod_name: str) -> dict[str, Any]:
    out = {"ok": False, "version": None, "path": None, "error": None}
    try:
        mod = __import__(mod_name)
        out["ok"] = True
        out["version"] = getattr(mod, "__version__", None) or _package_version(mod_name)
        out["path"] = getattr(mod, "__file__", None)
        return out
    except Exception as exc:
        out["error"] = str(exc)
        return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="frameit", description="FrameIt CLI")
    sub = p.add_subparsers(dest="command", required=True)

    # run
    pr = sub.add_parser("run", help="Run FrameIt from a YAML configuration file.")
    pr.add_argument(
        "config", nargs="?", default=Path("frameit.yaml"), type=Path,
        help="YAML file (default: frameit.yaml)",
    )
    pr.add_argument(
        "--dry-run", action="store_true",
        help="Inspect inputs and preview the scientific plan without writing products",
    )
    pr.add_argument(
        "--log-level",
        default=None,
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Override log level. If not set, uses conf.DEBUG to choose DEBUG/INFO.",
    )
    pr.add_argument(
        "--no-hdf5-debug-pop",
        action="store_true",
        help="Do not remove HDF5_DEBUG from the environment.",
    )

    # Exports enabled by default, disable with --no-*
    pr.add_argument(
        "--no-export-netcdf",
        dest="export_netcdf",
        action="store_false",
        default=None,
        help="Disable NetCDF export (enabled by default).",
    )
    pr.add_argument(
        "--no-export-polar",
        dest="export_polar",
        action="store_false",
        default=None,
        help="Disable polar export (enabled by default).",
    )
    pr.add_argument(
        "--no-export-cart",
        dest="export_cart",
        action="store_false",
        default=None,
        help="Disable cartesian export (enabled by default).",
    )
    pr.add_argument(
        "--compress-level",
        type=int,
        default=None,
        help="NetCDF compression level (0-9). Default: 1.",
    )
    pr.add_argument(
        "--institution",
        type=str,
        default=None,
        help="Institution string stored in exported files.",
    )
    pr.add_argument("--output-directory", type=Path, default=None,
                    help="Override output.directory (relative to the launch directory)")
    pr.add_argument("--no-overwrite", dest="overwrite", action="store_false", default=None,
                    help="Refuse an output directory containing previous run artifacts")
    pr.add_argument("--synchronous-export", action="store_true", default=None,
                    help="Write groups in the controlling process without an export pool")
    pr.add_argument("--max-workers", type=int, default=None,
                    help="Maximum export processes (must fit the CPU allocation)")
    pr.add_argument("--require-complete-tracking", action="store_true", default=None,
                    help="Fail if the selected tracker returns an incomplete trajectory")

    # validate
    pv = sub.add_parser("validate", help="Load and validate the YAML configuration (lightweight).")
    pv.add_argument(
        "config", nargs="?", default=Path("frameit.yaml"), type=Path,
        help="YAML file (default: frameit.yaml)",
    )
    pv.add_argument(
        "--schema-only", action="store_true", help="Validate YAML without opening datasets"
    )

    pin = sub.add_parser("init", help="Create an annotated schema-v2 configuration")
    pin.add_argument("model", choices=("arome", "mesonh"))
    pin.add_argument("--output", type=Path, default=Path("frameit.yaml"))
    pin.add_argument(
        "--tracking", default="wind_pressure",
        choices=("wind_pressure", "fixed_box", "prescribed_track", "pressure_centroid",
                 "multifield_vortex", "utrack"),
    )
    pin.add_argument("--full", action="store_true")
    pin.add_argument("--force", action="store_true")

    pc = sub.add_parser("config", help="Migrate or display configuration")
    pcs = pc.add_subparsers(dest="config_command", required=True)
    pcm = pcs.add_parser("migrate", help="Explicitly translate legacy flat YAML")
    pcm.add_argument("config", type=Path)
    pcm.add_argument("--output", type=Path, default=Path("frameit.yaml"))
    pcm.add_argument(
        "--launch-directory", type=Path, default=None,
        help="Original launch directory for legacy relative paths (default: current directory)",
    )
    pcm.add_argument("--force", action="store_true")
    pcs_show = pcs.add_parser("show", help="Show effective settings")
    pcs_show.add_argument("config", nargs="?", type=Path, default=Path("frameit.yaml"))
    pcs_show.add_argument(
        "--resolved", action="store_true", help="Inspect datasets and geometry-dependent defaults"
    )

    pins = sub.add_parser("inspect", help="Inspect dataset metadata, units, and grid geometry")
    pins.add_argument("directory", type=Path)
    pins.add_argument("--model", required=True, choices=("arome", "mesonh"))
    pins.add_argument("--format", choices=("grib", "netcdf", "fa"), default=None)
    pins.add_argument("--pattern", default="*", help="Explicit input glob (default: *)")
    pins.add_argument("--fa-profile", choices=("arome_history", "surfex_history"), default=None)
    pins.add_argument("--fa-fields", nargs="+", default=[],
                      help="Probe native FA encoding flags without decoding values")
    pins.add_argument("--fa-backend", choices=("native", "epygram"), default="native")
    pins.add_argument("--fa-python", default=None,
                      help="Optional path to the FA helper's Python interpreter")

    # info (fusion of version and doctor, verbose by default)
    pi = sub.add_parser(
        "info", help="Print FrameIt and environment information (verbose by default)."
    )
    pi.add_argument("--short", action="store_true", help="Print only 'FrameIt <version>'")

    pd = sub.add_parser(
        "prepare-ci-dataset", help="Prepare and verify the frozen scientific CI fixture."
    )
    pd.add_argument("--source", type=Path, required=True, help="Full simulation dataset root")
    pd.add_argument("--output", type=Path, required=True, help="Fixture destination")
    pd.add_argument(
        "--max-size-mb",
        type=float,
        default=100.0,
        help="Maximum installed fixture size in decimal MB (default: 100)",
    )
    pd.add_argument(
        "--force", action="store_true", help="Transactionally replace an existing fixture"
    )
    pd.add_argument(
        "--plan-only", action="store_true", help="Inspect the recipe without writing data"
    )
    pd.add_argument(
        "--track-file",
        type=Path,
        default=None,
        help="Override source/MNH/IBTracks_reunion_CHIDO.nc",
    )

    pm = sub.add_parser(
        "run-matrix-test", help="Run scientific simulation cases and check their product contracts."
    )
    pm.add_argument("--ci", action="store_true", help="Use the frozen small fixture and CI cases")
    pm.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Input root; overrides the bundled fixture with --ci, required otherwise",
    )
    pm.add_argument("--output", type=Path, required=True, help="Fresh matrix run directory")
    pm.add_argument("--profile", choices=("core", "full"), default="full")
    pm.add_argument(
        "--case",
        action="append",
        default=[],
        dest="cases",
        metavar="ID_OR_GLOB",
        help="Select case IDs or glob patterns (repeatable)",
    )
    pm.add_argument(
        "--plan-only", action="store_true", help="Resolve the plan without running cases"
    )
    pm.add_argument("--input-policy", choices=("strict", "available"), default="strict")
    scheduling = pm.add_mutually_exclusive_group()
    scheduling.add_argument("--keep-going", action="store_true", dest="keep_going", default=True)
    scheduling.add_argument("--fail-fast", action="store_false", dest="keep_going")
    pm.add_argument(
        "--utrack-weights",
        type=Path,
        default=None,
        help="UTrack checkpoint for full-domain runs; UTrack is excluded in CI",
    )
    pm.add_argument("--log-level", default=None, choices=("DEBUG", "INFO", "WARNING", "ERROR"))

    pa = sub.add_parser(
        "run-all-tests", help="Run numerical tests and the simulation matrix with benchmarks."
    )
    pa.add_argument("--output", type=Path, required=True, help="Fresh results directory")
    pa.add_argument("--data-root", type=Path, default=None,
                    help="Full simulation root; defaults to the bundled CI fixture")
    pa.add_argument("--utrack-weights", type=Path, default=None)
    pa.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"))

    return p


def _cmd_validate(cfg_path: Path, *, schema_only=False) -> int:
    from frameit.core.settings_class import SimulationConfig

    conf = SimulationConfig.from_yaml_with_model_preset(cfg_path)

    if not schema_only:
        from frameit.core.preflight import preflight

        plan = preflight(conf)
        print(f"OK: {len(plan['inputs'])} input file(s); grid spacing {conf.resolution:.3f} m")
    else:
        print("OK: schema validated")
    return 0


def _cmd_info(short: bool) -> int:
    from frameit import __version__

    frameit_ver = _package_version("frameit") or __version__
    if short:
        print(f"FrameIt {frameit_ver}")
        return 0

    print(f"FrameIt: {frameit_ver}")
    print(f"Python: {platform.python_version()} ({sys.executable})")
    print(f"Platform: {platform.system()} {platform.release()} ({platform.machine()})")

    env_keys = ("HDF5_DEBUG", "ECCODES_DEFINITION_PATH", "ECCODES_SAMPLES_PATH")
    print("Environment:")
    for k in env_keys:
        print(f"  {k}={os.environ.get(k, '')}")

    modules = {
        "numpy": _probe_module("numpy"),
        "xarray": _probe_module("xarray"),
        "dask": _probe_module("dask"),
        "cfgrib": _probe_module("cfgrib"),
        "eccodes": _probe_module("eccodes"),
        "xesmf": _probe_module("xesmf"),
        "netCDF4": _probe_module("netCDF4"),
        "h5py": _probe_module("h5py"),
    }

    print("Modules:")
    for name in sorted(modules):
        m = modules[name]
        if m["ok"]:
            ver = m["version"] or ""
            print(f"  {name}: OK {ver}".rstrip())
        else:
            print(f"  {name}: MISSING")
            if m["error"]:
                print(f"    error: {m['error']}")

    fa_version = _package_version("falfilfa4py")
    print("  falfilfa4py: " + (f"installed {fa_version}; isolated native reader (not probed)"
                                    if fa_version else "optional, not installed"))

    critical_missing = [k for k in ("numpy", "xarray") if not modules[k]["ok"]]
    if critical_missing:
        print(f"Overall: FAIL (missing critical modules: {', '.join(critical_missing)})")
        return 1

    print("Overall: OK")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from frameit.core.execution import ExecutionOptions, execute_simulation
    from frameit.core.settings_class import SimulationConfig

    conf = SimulationConfig.from_yaml_with_model_preset(args.config)
    if args.output_directory is not None:
        destination = str(args.output_directory.resolve())
        conf.frameit_output_dir = destination
        conf.yaml_config["output"]["directory"] = destination
        conf.schema_sources["output.directory"] = "execution_override"
    options = ExecutionOptions.from_config(
        conf, export_netcdf=args.export_netcdf, export_polar=args.export_polar,
        export_cart=args.export_cart, compress_level=args.compress_level,
        institution=args.institution, log_level=args.log_level,
        no_hdf5_debug_pop=args.no_hdf5_debug_pop,
        overwrite=args.overwrite, synchronous_export=args.synchronous_export,
        max_workers=args.max_workers, require_complete_tracking=args.require_complete_tracking,
    )
    if args.dry_run:
        from frameit.core.preflight import preflight

        _print_yaml(preflight(conf, execution_options=options))
        return 0
    from frameit.core.runtime import termination_scope

    with termination_scope():
        result = execute_simulation(conf, options)
    return 0 if result.ok else 1


def _print_yaml(value):
    import yaml

    print(yaml.safe_dump(value, sort_keys=False, allow_unicode=True))


def _cmd_config(args):
    from frameit.core.configuration import migrate_mapping, read_yaml

    if args.config_command == "migrate":
        if args.output.exists() and not args.force:
            raise FileExistsError(f"Configuration exists: {args.output}; use --force")
        config, reports = migrate_mapping(read_yaml(args.config), launch_dir=args.launch_directory)
        import yaml

        args.output.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        print(f"Migrated configuration: {args.output}")
        for report in reports:
            print(report)
    else:
        from frameit.core.settings_class import SimulationConfig

        conf = SimulationConfig.from_yaml(args.config)
        if args.resolved:
            from frameit.core.preflight import preflight

            _print_yaml(preflight(conf))
        else:
            _print_yaml(conf.yaml_config)
    return 0


def _cmd_inspect(args):
    if args.format == "fa":
        from frameit.io.fa_backend import inspect_fa

        paths = sorted(path for path in args.directory.glob(args.pattern) if path.is_file())
        if not paths:
            raise FileNotFoundError("No FA inspection inputs match the selected pattern")
        _print_yaml({"format": "fa", "inputs": [{"path": str(path), **inspect_fa(
            path, args.fa_profile, args.fa_fields, validate_selection=False,
            backend=args.fa_backend, python_executable=args.fa_python)} for path in paths],
            "interpretation": "Raw native metadata; scientific field definitions and "
                              "projected Earth shape must be declared before execution"})
        return 0
    if (args.fa_profile is not None or args.fa_fields
            or args.fa_backend != "native" or args.fa_python):
        raise ValueError("--fa-profile/--fa-fields/--fa-backend/--fa-python require --format fa")
    from frameit.core.preflight import preflight
    from frameit.core.settings_class import SimulationConfig

    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 2, "model": args.model,
        "input": {"directory": str(args.directory.resolve()), "pattern": args.pattern,
                  "format": args.format},
        "tracking": {"method": "fixed_box", "fixed_box": {
            "center": {"latitude": 0., "longitude": 0.}}},
    })
    _print_yaml(preflight(conf, check_output=False))
    return 0


def _cmd_prepare_ci_dataset(args: argparse.Namespace) -> int:
    from frameit.testing.datasets import prepare_ci_dataset

    report = prepare_ci_dataset(
        args.source,
        args.output,
        max_size_mb=args.max_size_mb,
        force=args.force,
        plan_only=args.plan_only,
        track_file=args.track_file,
    )
    import json

    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


def _cmd_run_matrix(args: argparse.Namespace) -> int:
    from importlib import resources

    from frameit.testing.matrix import run_matrix

    if args.data_root is None and not args.ci:
        raise ValueError("--data-root is required without --ci")
    data_root = args.data_root
    if data_root is None:
        data_root = Path(str(resources.files("frameit.testing").joinpath("ci_dataset")))
    report = run_matrix(
        data_root,
        args.output,
        ci=args.ci,
        profile=args.profile,
        cases=tuple(args.cases),
        plan_only=args.plan_only,
        input_policy=args.input_policy,
        keep_going=args.keep_going,
        utrack_weights=args.utrack_weights,
        log_level=args.log_level,
    )
    print(f"Matrix results: {args.output.resolve()}")
    print(f"Exit code: {report['exit_code']}")
    return int(report["exit_code"])


def main(argv: list[str] | None = None) -> None:
    """
    Entry point for the ``frameit`` CLI.

    Parameters
    ----------
    argv : list[str] or None, optional
        Argument list to parse.  When ``None``, :attr:`sys.argv` is used.

    Raises
    ------
    SystemExit
        Always raised with exit code ``0`` on success, ``1`` on unhandled
        exception, or ``2`` for an unknown sub-command.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Minimal fallback logging for unexpected errors before FrameIt logging is configured
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    try:
        if args.command == "run":
            code = _cmd_run(args)
        elif args.command == "validate":
            code = _cmd_validate(args.config, schema_only=args.schema_only)
        elif args.command == "init":
            from frameit.core.configuration import write_template

            path = write_template(
                args.model, args.output, full=args.full, tracking=args.tracking, force=args.force
            )
            print(
                f"Created {path}. Edit the examples, then run 'frameit validate {path}' "
                f"and 'frameit run {path}'."
            )
            code = 0
        elif args.command == "config":
            code = _cmd_config(args)
        elif args.command == "inspect":
            code = _cmd_inspect(args)
        elif args.command == "info":
            code = _cmd_info(short=bool(args.short))
        elif args.command == "prepare-ci-dataset":
            code = _cmd_prepare_ci_dataset(args)
        elif args.command == "run-matrix-test":
            code = _cmd_run_matrix(args)
        elif args.command == "run-all-tests":
            from frameit.testing.all_tests import run_all_tests

            report = run_all_tests(
                args.output, data_root=args.data_root,
                utrack_weights=args.utrack_weights, log_level=args.log_level,
            )
            print(f"All-test results: {args.output.resolve()}")
            print(f"Computation benchmark: {report['benchmark']['computation_s']:.6f} s")
            code = report["exit_code"]
        else:
            code = 2
    except KeyboardInterrupt:
        code = 130
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        logging.getLogger("frameit").error("%s", exc)
        code = 2 if args.command in (
            "prepare-ci-dataset", "run-matrix-test", "run-all-tests"
        ) else 1
    except Exception:
        logging.getLogger("frameit").exception("FrameIt CLI failed")
        code = 1

    raise SystemExit(code)
