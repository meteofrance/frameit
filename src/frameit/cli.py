# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0


from __future__ import annotations

import os
import site
import sys
from pathlib import Path


def _sanitize_sys_path_user_site() -> None:
    """Exclude user site-packages without removing unrelated checkouts or environments."""
    # PYTHONPATH and .pth files can add user packages even with PYTHONNOUSERSITE.
    user_site = Path(site.getusersitepackages()).resolve()

    new_path: list[str] = []
    for p in sys.path:
        try:
            rp = Path(p).resolve()
        except Exception:
            new_path.append(p)
            continue

        if user_site in rp.parents or rp == user_site:
            continue

        new_path.append(p)

    sys.path[:] = new_path


_sanitize_sys_path_user_site()

# Imports only after sys.path is sanitized
import argparse  # noqa: E402
import logging  # noqa: E402
import platform  # noqa: E402
from functools import partial  # noqa: E402
from typing import Any  # noqa: E402

from frameit.utils.diagnostics import (  # noqa: E402
    FrameItArgumentParser as _FrameItArgumentParser,
)
from frameit.utils.diagnostics import (  # noqa: E402
    diagnostic_path,
    exception_code,
    format_help,
    tag_error,
)


def _failure_message(exc: Exception) -> str:
    from frameit.core.reports import preflight_diagnostics

    if diagnostics := preflight_diagnostics(exc):
        paths = dict.fromkeys(diagnostic_path(error.code) for error in diagnostics)
        return str(exc) + "\nTroubleshooting: " + ", ".join(paths)
    return format_help(exception_code(exc), str(exc))


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


def _operational_arguments(parser):
    parser.add_argument("--output-directory", type=Path,
                        help="Override output.directory; relative paths use the launch directory")
    parser.add_argument("--cpus", type=int, help="Override the total CPU budget (positive integer)")
    overwrite = parser.add_mutually_exclusive_group()
    overwrite.add_argument("--overwrite", dest="overwrite", action="store_true", default=None,
                           help="Allow replacement of recognized run artifacts")
    overwrite.add_argument("--no-overwrite", dest="overwrite", action="store_false",
                           help="Refuse existing run artifacts (the default)")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"),
                        help="Override logging.level")


def _operational_overrides(args):
    keys = ("output_directory", "cpus", "overwrite", "log_level")
    return {key: getattr(args, key) for key in keys
            if getattr(args, key, None) is not None}


def _build_parser() -> argparse.ArgumentParser:
    p = _FrameItArgumentParser(prog="frameit", description="FrameIt CLI", allow_abbrev=False)
    sub = p.add_subparsers(dest="command", required=True)

    # run
    pr = sub.add_parser("run", help="Run FrameIt from a YAML configuration file.", allow_abbrev=False)
    pr.add_argument(
        "config", nargs="?", default=Path("frameit.yaml"), type=Path,
        help="YAML file (default: frameit.yaml)",
    )
    _operational_arguments(pr)
    pr.add_argument(
        "--no-hdf5-debug-pop",
        action="store_true",
        help="Do not remove HDF5_DEBUG from the environment.",
    )

    # Exports enabled by default, disable with --no-*
    pr.add_argument(
        "--no-export",
        dest="export_netcdf",
        action="store_false",
        default=None,
        help="Suppress publication of all declared products; keep processing and records.",
    )
    pr.add_argument(
        "--no-export-polar",
        dest="export_polar",
        action="store_false",
        default=None,
        help="Suppress publication of declared polar products.",
    )
    pr.add_argument(
        "--no-export-cartesian",
        dest="export_cart",
        action="store_false",
        default=None,
        help="Suppress publication of declared model-grid products.",
    )
    pr.add_argument(
        "--compress-level",
        type=int,
        default=None,
        help="Override output.writer.compression.level for NetCDF/Zarr (0-9).",
    )
    pr.add_argument(
        "--institution",
        type=str,
        default=None,
        help="Institution string stored in exported files.",
    )
    pr.add_argument("--synchronous-export", action="store_true", default=None,
                    help="Write groups in the controlling process without an export pool")
    pr.add_argument("--max-workers", type=int, default=None,
                    help="Maximum export processes (must fit the CPU allocation)")
    pr.add_argument("--require-complete-tracking", action="store_true", default=None,
                    help="Fail if the selected tracker returns an incomplete trajectory")

    # validate
    pv = sub.add_parser("validate", allow_abbrev=False,
                        help="Check YAML, selected metadata, dependencies and the processing plan.")
    pv.add_argument(
        "config", nargs="?", type=Path,
        help="YAML file (default: frameit.yaml)",
    )
    pv.add_argument(
        "--schema-only", action="store_true", help="Validate YAML without opening datasets"
    )
    pv.add_argument("--json", action="store_true", help="Emit one structured validation report")
    pv.add_argument("--cli", action="store_true", help="Use the text report instead of the TUI")
    pv.add_argument("--saved-report", type=Path,
                    help="Open an existing validation JSON report without rechecking inputs")
    _operational_arguments(pv)

    from frameit.core.configuration import TEMPLATES

    pin = sub.add_parser(
        "init", help="Create a minimal commented v3 starter", allow_abbrev=False,
        epilog="Named workflows reject composition flags. Coupling: arome+nemo or mesonh+croco; "
               "both support fixed_box (default), prescribed_track, pressure_wind and pressure_centroid.")
    pin.add_argument("name", choices=("arome", "mesonh", "nemo", "croco", *TEMPLATES))
    pin.add_argument("--output", type=Path, default=Path("frameit.yaml"))
    pin.add_argument(
        "--tracking", default=None,
        choices=("pressure_wind", "fixed_box", "prescribed_track", "pressure_centroid"),
    )
    pin.add_argument("--coupling", choices=("nemo", "croco"), default=None)
    pin.add_argument("--force", action="store_true", help="Replace only the selected configuration file")

    pc = sub.add_parser("config", help="Display the authored or effective configuration",
                        allow_abbrev=False)
    pcs = pc.add_subparsers(dest="config_command", required=True)
    pcs_show = pcs.add_parser("show", help="Show the authored request; use --effective for a plan",
                              allow_abbrev=False)
    pcs_show.add_argument("config", nargs="?", type=Path, default=Path("frameit.yaml"))
    pcs_show.add_argument(
        "--effective", action="store_true",
        help="Check metadata and show effective settings and origins"
    )
    pcs_show.add_argument("--json", action="store_true", help="Emit one JSON document")
    _operational_arguments(pcs_show)

    pins = sub.add_parser("inspect", allow_abbrev=False,
                          help="Inspect sources in a YAML request, including unfinished selections")
    pins.add_argument(
        "config", nargs="?", type=Path,
        help="YAML file (default: frameit.yaml)",
    )
    pins.add_argument("--json", action="store_true", help="Emit one structured metadata report")
    pins.add_argument("--cli", action="store_true",
                      help="Use the full text report instead of the TUI")
    pins.add_argument("--saved-report", type=Path,
                      help="Open an existing inspection JSON report without checking inputs")

    capabilities_parser = sub.add_parser(
        "capabilities", allow_abbrev=False,
        help="Show implemented support, dependencies, maturity and limits")
    capabilities_parser.add_argument("--json", action="store_true",
                                     help="Emit one structured support report")

    status_parser = sub.add_parser(
        "status", allow_abbrev=False,
        help="Show last-recorded run facts without the original inputs")
    status_parser.add_argument("run_directory", type=Path,
                               help="Directory containing run-status.yaml")

    fixtures = sub.add_parser(
        "generate-tests-fixtures", allow_abbrev=False,
        help="Generate analytical task-tutorial inputs only; no supplied data needed.")
    fixtures.add_argument("--output", type=Path, default=Path("tutorial-data"),
                          help="New tutorial directory; existing directories are refused")

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
        help="Override the recipe's prescribed track file",
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
        help="UTrack checkpoint; v3 execution binding is unavailable, including with weights.",
    )
    pm.add_argument("--log-level", default=None, choices=("DEBUG", "INFO", "WARNING", "ERROR"))

    pa = sub.add_parser(
        "run-all-tests", help="Run numerical tests and the simulation matrix with benchmarks."
    )
    pa.add_argument("--output", type=Path, required=True, help="Fresh results directory")
    pa.add_argument("--data-root", type=Path, default=None,
                    help="Full-domain matrix inputs; omit for CI mode. Reduced tests use "
                         "FRAMEIT_CI_DATA_ROOT or the package fixture location.")
    pa.add_argument(
        "--utrack-weights", type=Path, default=None,
        help="UTrack checkpoint; v3 execution binding is unavailable, including with weights.")
    pa.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"))

    return p


def _load_config(path, overrides):
    try:
        from frameit.core.configuration import load_runtime
        from frameit.core.settings_class import SimulationConfig
        from frameit.io.loader import _apply_model_presets
    except ImportError as exc:
        raise tag_error(exc, "E1001")
    from frameit.utils.logging import frameit_logging_scope

    runtime = load_runtime(path, launch_dir=Path.cwd(), overrides=overrides)
    with frameit_logging_scope(None, level=runtime["log_level"]):
        for handler in logging.getLogger("frameit").handlers:
            handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        return SimulationConfig(**_apply_model_presets(runtime, strict_locked=True))


def _report_failure(exc, command, *, sample_only=False):
    from frameit.core.reports import (
        PreflightResult,
        blocked_check,
        exception_diagnostics,
    )

    errors = exception_diagnostics(
        exc, path="configuration", expected="valid v3 configuration",
        observed={"cause": str(exc)}, repairs=[f"Correct the reported prerequisite: {exc}"])
    deferred = [] if sample_only else [blocked_check(
        "plan", [error.path for error in errors],
        "Dependent planning and execution are blocked until these errors are repaired.")]
    return PreflightResult(command, errors=errors, deferred_checks=deferred)


def _collect_report(path, *, command, schema_only=False, overrides=None, progress=None,
                    sample_only: bool = False):
    if progress is not None:
        progress("configuration", None, None, None)
    try:
        from yaml import YAMLError

        from frameit.core.preflight import collect_preflight
        from frameit.utils.logging import frameit_logging_scope
    except ImportError as exc:
        return _report_failure(tag_error(exc, "E1001"), command, sample_only=sample_only)

    try:
        request = _load_config(path, overrides or {})
        with frameit_logging_scope(None, level=request.log_level):
            for handler in logging.getLogger("frameit").handlers:
                handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
            return collect_preflight(
                request, command=command, schema_only=schema_only, progress=progress,
                sample_only=sample_only)
    except (OSError, ValueError, ImportError, YAMLError) as exc:
        return _report_failure(exc, command, sample_only=sample_only)


def _run_report_app(build_app, *, cli_output: bool, json_output: bool) -> int | None:
    if (cli_output or json_output or os.environ.get("TERM") in (None, "", "dumb")
            or not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr))):
        return None
    try:
        app = build_app()
    except ModuleNotFoundError as exc:
        if exc.name != "textual":
            raise
        return None

    from signal import SIGTERM, signal

    previous = signal(SIGTERM, lambda *_: app.exit(128 + SIGTERM))
    try:
        code = app.run()
    finally:
        signal(SIGTERM, previous)
    return 1 if code is None else code


def _cmd_validate(cfg_path: Path, *, schema_only=False, json_output=False, cli_output=False,
                  overrides=None) -> int:
    collect = partial(_collect_report, cfg_path, command="validate", schema_only=schema_only,
                      overrides=overrides)

    def build_app():
        from frameit.validate_tui import ValidationApp

        return ValidationApp(cfg_path, collect, schema_only=schema_only, overrides=overrides,
                             isolate=True)

    code = _run_report_app(build_app, cli_output=cli_output, json_output=json_output)
    return _print_preflight(collect(), json_output=json_output) if code is None else code


def _print_preflight(result, *, json_output=False):
    from frameit.core.reports import render_report, serialize_report

    print(serialize_report(result) if json_output else render_report(result))
    return int(bool(result.errors))


def _cmd_saved_report(args):
    from frameit.core.reports import load_saved_report, render_projection, serialize_projection

    if (args.config is not None or getattr(args, "schema_only", False)
            or (args.command == "validate" and _operational_overrides(args))):
        print("Use --saved-report without a YAML request or live check options.", file=sys.stderr)
        return 1
    path = args.saved_report
    try:
        report = load_saved_report(path, args.command)
    except (OSError, ValueError) as exc:
        print(f"Cannot open saved report: {exc}", file=sys.stderr)
        return 1

    def build_app():
        if args.command == "inspect":
            from frameit.inspect_tui import InspectionApp

            return InspectionApp(path, None, saved_report=report)
        from frameit.validate_tui import ValidationApp

        return ValidationApp(path, None, saved_report=report)

    code = _run_report_app(build_app, cli_output=args.cli, json_output=args.json)
    if code is not None:
        return code
    if args.json:
        print(serialize_projection(report))
    else:
        print("Saved report (recorded checks only)\n" + render_projection(report).replace(
            "\r\n", "\n"))
    return int(bool(report["errors"]))


def _cmd_info(short: bool) -> int:
    import frameit

    frameit_ver = _package_version("frameit") or frameit.__version__
    if short:
        print(f"FrameIt {frameit_ver}")
        return 0

    print(f"FrameIt: {frameit_ver}")
    print(f"FrameIt location: {frameit.__file__}")
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
        print(format_help(
            "E1001", f"Overall: FAIL (missing critical modules: {', '.join(critical_missing)})"
        ))
        return 1

    print("Overall: OK")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        from frameit.core.execution import ExecutionOptions, execute_simulation
    except ImportError as exc:
        raise tag_error(exc, "E1001")

    conf = _load_config(args.config, _operational_overrides(args))
    options = ExecutionOptions.from_config(
        conf, export_netcdf=args.export_netcdf, export_polar=args.export_polar,
        export_cart=args.export_cart, compress_level=args.compress_level,
        institution=args.institution,
        no_hdf5_debug_pop=args.no_hdf5_debug_pop,
        synchronous_export=args.synchronous_export,
        max_workers=args.max_workers, require_complete_tracking=args.require_complete_tracking,
    )
    for attr, path in (("compress_level", "output.writer.compression.level"),
                       ("institution", "metadata.institution")):
        if getattr(args, attr) is not None:
            options.setting_sources[path] = "cli"
    from frameit.core.reports import error_record, render_run_summary
    from frameit.core.runtime import termination_scope

    try:
        with termination_scope():
            result = execute_simulation(conf, options)
    except BaseException as exc:
        try:
            attested = getattr(exc, "_frameit_failure", None)
            if attested is not None:
                print(render_run_summary(attested["facts"], root=attested["root"]))
            else:
                print(render_run_summary({
                    "state": ("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit))
                              else "failed"),
                    "error": error_record(exc),
                    "current_attempt": (
                        "Inventory unavailable; no owning final facts were returned. "
                        "On-disk status may belong to an earlier or concurrent attempt. "
                        "Use frameit status for separate last-recorded information."),
                }, root=conf.output_dir))
        except BaseException:
            # Reporting must preserve the primary failure, including interruptions.
            pass
        raise
    plan = conf.simulation_parameter.get("request_plan", {})
    print(render_run_summary({
        "state": "completed" if result.tracking_complete else "incomplete",
        "products": result.products, "pending": [],
        "tracking_termination_reason": result.tracking_termination_reason,
        "warnings": plan.get("warnings", []),
        "exclusions": {name: source.get("excluded_files", [])
                       for name, source in plan.get("sources", {}).items()},
    }, root=result.output_dir))
    return 0 if result.ok else 1


def _print_yaml(value):
    import yaml

    print(yaml.safe_dump(value, sort_keys=False, allow_unicode=True))


def _cmd_config(args):
    if args.effective:
        return _print_preflight(_collect_report(
            args.config, command="config show --effective", overrides=_operational_overrides(args)),
            json_output=args.json)
    if _operational_overrides(args):
        raise tag_error(ValueError("Operational overrides require config show --effective"), "E0001")
    from frameit.core.configuration import read_yaml

    authored = read_yaml(args.config)
    if args.json:
        import json

        from frameit.core.reports import _metadata_view

        print(json.dumps(_metadata_view(authored), indent=2, ensure_ascii=False, allow_nan=False))
    else:
        _print_yaml(authored)
    return 0


def _cmd_inspect(args):
    config = args.config or Path("frameit.yaml")

    def build_app():
        from frameit.inspect_tui import InspectionApp

        return InspectionApp(config, partial(
            _collect_report, config, command="inspect", sample_only=True), isolate=True)

    code = _run_report_app(build_app, cli_output=args.cli, json_output=args.json)
    if code is None:
        return _print_preflight(
            _collect_report(config, command="inspect"), json_output=args.json)
    return code


def _cmd_prepare_ci_dataset(args: argparse.Namespace) -> int:
    from frameit.testing.datasets import prepare_ci_dataset

    try:
        report = prepare_ci_dataset(
            args.source,
            args.output,
            max_size_mb=args.max_size_mb,
            force=args.force,
            plan_only=args.plan_only,
            track_file=args.track_file,
        )
    except (ValueError, OSError) as exc:
        raise tag_error(exc, "E1901")
    import json

    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


def _cmd_run_matrix(args: argparse.Namespace) -> int:
    from importlib import resources

    from frameit.testing.matrix import run_matrix

    if args.data_root is None and not args.ci:
        raise tag_error(ValueError("--data-root is required without --ci"), "E1902")
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
    if report["exit_code"]:
        print(format_help(report.get("code", "E1903"), "The matrix did not pass. See run.json."))
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
    try:
        parser = _build_parser()
    except ImportError as exc:
        print(format_help("E1001", str(exc)), file=sys.stderr)
        raise SystemExit(1) from None
    args = parser.parse_args(argv)

    # Minimal fallback logging for unexpected errors before FrameIt logging is configured
    logging.basicConfig(level=getattr(logging, getattr(args, "log_level", None) or "INFO"),
                        format="%(levelname)s:%(name)s:%(message)s")

    try:
        if getattr(args, "saved_report", None) is not None:
            code = _cmd_saved_report(args)
        elif args.command == "run":
            code = _cmd_run(args)
        elif args.command == "validate":
            code = _cmd_validate(
                args.config or Path("frameit.yaml"), schema_only=args.schema_only,
                json_output=args.json,
                cli_output=args.cli, overrides=_operational_overrides(args))
        elif args.command == "init":
            from frameit.core.configuration import write_template

            path = write_template(
                args.name, args.output, tracking=args.tracking, coupling=args.coupling, force=args.force
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
        elif args.command == "capabilities":
            from frameit.core.configuration import capabilities
            from frameit.core.reports import PreflightResult

            code = _print_preflight(PreflightResult(
                "capabilities", facts={"capabilities": capabilities()}), json_output=args.json)
        elif args.command == "status":
            from frameit.core.reports import render_run_summary
            from frameit.core.run_state import read_run_status

            facts = read_run_status(args.run_directory)
            print(render_run_summary(facts, root=args.run_directory.resolve(), recorded=True))
            code = 0 if facts["state"] in {"completed", "incomplete"} else 1
        elif args.command == "info":
            code = _cmd_info(short=bool(args.short))
        elif args.command == "generate-tests-fixtures":
            from frameit.testing.documentation_example import create_task_fixtures

            for path in create_task_fixtures(args.output).values():
                print(f"Created instructional fixture: {path}")
            code = 0
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
            if code:
                print(format_help(report.get("code", "E1903"), "See all-tests.json and the logs."))
        else:
            code = 2
    except KeyboardInterrupt:
        logging.getLogger("frameit").error("%s", format_help("E0002", "FrameIt was interrupted"))
        code = 130
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        logging.getLogger("frameit").error("%s", _failure_message(exc))
        code = 2 if args.command in (
            "prepare-ci-dataset", "run-matrix-test", "run-all-tests"
        ) else 1
    except Exception as exc:
        logging.getLogger("frameit").exception("%s", _failure_message(exc))
        code = 1

    raise SystemExit(code)
