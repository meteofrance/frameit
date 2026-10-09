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
    pr.add_argument("config", type=Path, help="Path to the YAML configuration file")
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
        default=True,
        help="Disable NetCDF export (enabled by default).",
    )
    pr.add_argument(
        "--no-export-polar",
        dest="export_polar",
        action="store_false",
        default=True,
        help="Disable polar export (enabled by default).",
    )
    pr.add_argument(
        "--no-export-cart",
        dest="export_cart",
        action="store_false",
        default=True,
        help="Disable cartesian export (enabled by default).",
    )
    pr.add_argument(
        "--compress-level",
        type=int,
        default=1,
        help="NetCDF compression level (0-9). Default: 1.",
    )
    pr.add_argument(
        "--institution",
        type=str,
        default=_DEFAULT_INSTITUTION,
        help="Institution string stored in exported files.",
    )

    # validate
    pv = sub.add_parser("validate", help="Load and validate the YAML configuration (lightweight).")
    pv.add_argument("config", type=Path, help="Path to the YAML configuration file")

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

    return p


def _cmd_validate(cfg_path: Path) -> int:
    from frameit.core.settings_class import SimulationConfig

    conf = SimulationConfig.from_yaml_with_model_preset(cfg_path)

    out_dir = Path(conf.frameit_output_dir)
    if not out_dir.exists():
        print(f"WARNING: output directory does not exist: {out_dir}")
    elif not os.access(out_dir, os.W_OK):
        print(f"WARNING: no write permission on output directory: {out_dir}")

    print("OK: configuration loaded successfully")
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
    execute_simulation(
        conf,
        ExecutionOptions(
            export_netcdf=args.export_netcdf,
            export_polar=args.export_polar,
            export_cart=args.export_cart,
            compress_level=args.compress_level,
            institution=args.institution,
            log_level=args.log_level,
            no_hdf5_debug_pop=args.no_hdf5_debug_pop,
        ),
    )
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
            code = _cmd_validate(args.config)
        elif args.command == "info":
            code = _cmd_info(short=bool(args.short))
        elif args.command == "prepare-ci-dataset":
            code = _cmd_prepare_ci_dataset(args)
        elif args.command == "run-matrix-test":
            code = _cmd_run_matrix(args)
        else:
            code = 2
    except KeyboardInterrupt:
        code = 130
    except (ValueError, FileNotFoundError) as exc:
        logging.getLogger("frameit").error("%s", exc)
        code = 2 if args.command in ("prepare-ci-dataset", "run-matrix-test") else 1
    except Exception:
        logging.getLogger("frameit").exception("FrameIt CLI failed")
        code = 1

    raise SystemExit(code)
