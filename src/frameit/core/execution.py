from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from frameit.core.settings_class import SimulationConfig
from frameit.utils.logging import frameit_logging_scope

DEFAULT_INSTITUTION = "LACy, Université de La Réunion, CNRS, Météo-France"


@dataclass(frozen=True)
class ExecutionOptions:
    export_netcdf: bool = True
    export_polar: bool = True
    export_cart: bool = True
    compress_level: int = 1
    institution: str = DEFAULT_INSTITUTION
    log_level: str | None = None
    no_hdf5_debug_pop: bool = False
    synchronous_export: bool = False
    benchmark: bool = False
    engine: str = "netcdf4"
    fmt: str = "NETCDF4"
    overwrite: bool = True
    compress_coords: bool = False
    unlimited_time: bool = True
    max_workers: int | None = None
    dask_scheduler: str = "threads"
    dask_workers: int | None = None
    native_threads: int = 1
    require_complete_tracking: bool = False

    @classmethod
    def from_config(cls, config, **overrides):
        output = config.yaml_config.get("output", {})
        execution = config.yaml_config.get("execution", {})
        values = {
            "export_netcdf": output.get("export", {}).get("netcdf", True),
            "export_cart": output.get("export", {}).get("cartesian", True),
            "export_polar": output.get("export", {}).get("polar", True),
            "compress_level": output.get("compression", {}).get("level", 1),
            "compress_coords": output.get("compression", {}).get("coordinates", False),
            "institution": output.get("institution", DEFAULT_INSTITUTION),
            "engine": output.get("engine", "netcdf4"), "fmt": output.get("format", "NETCDF4"),
            "overwrite": output.get("overwrite", True),
            "unlimited_time": output.get("unlimited_time", True),
            "max_workers": output.get("max_workers"), "log_level": config.log_level,
            "synchronous_export": output.get("synchronous_export", False),
            "dask_scheduler": execution.get("dask_scheduler", "threads"),
            "dask_workers": execution.get("dask_workers"),
            "native_threads": execution.get("native_threads", 1),
            "require_complete_tracking": execution.get("require_complete_tracking", False),
        }
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)

    def __post_init__(self):
        if not 0 <= int(self.compress_level) <= 9:
            raise ValueError("compress_level must be in [0, 9]")
        for name in ("max_workers", "dask_workers", "native_threads"):
            value = getattr(self, name)
            if (value is not None or name == "native_threads") and (
                type(value) is not int or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")
        for name in ("synchronous_export", "require_complete_tracking"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if self.dask_scheduler not in {"threads", "synchronous"}:
            raise ValueError("dask_scheduler must be threads or synchronous")


@dataclass
class SimulationExecutionResult:
    ok: bool
    n_files: int
    output_dir: str
    files: list[str]
    products: list[dict] = field(default_factory=list)
    duration_s: float = 0.0
    log_path: str | None = None
    backend_versions: dict[str, str] = field(default_factory=dict)
    timing_sections_s: dict[str, float] = field(default_factory=dict)
    computation_s: float = 0.0
    regrid_performance: dict = field(default_factory=dict)
    tracking_complete: bool = True
    tracking_termination_reason: str = ""
    execution_resources: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _product_descriptors(exports, runner):
    products = []
    for role, paths in exports.items():
        if role == "track":
            products.append({"role": role, "group": None, "path": str(Path(paths).resolve())})
            continue
        groups = (
            getattr(runner, "dict_polar_user" if role == "polar" else "dict_crop_user", {}) or {}
        )
        # Group names can contain punctuation sanitized in the physical name.
        from frameit.io.netcdf_export import _sanitize_filename_token

        filenames = {
            f"{runner.conf.simulation_name}.{role}.{_sanitize_filename_token(str(group))}.nc": str(
                group
            )
            for group in groups
        }
        for path in paths:
            path = Path(path)
            products.append(
                {"role": role, "group": filenames.get(path.name), "path": str(path.resolve())}
            )
    return products


def _loaded_backend_versions():
    """Record native versions without initializing otherwise unused backends."""
    versions = {}
    for name in ("eccodes", "ESMF", "esmpy", "xesmf", "netCDF4", "h5netcdf", "h5py", "pyproj"):
        module = sys.modules.get(name)
        if module is None:
            continue
        version = getattr(module, "__version__", None)
        if version is not None:
            versions[name] = str(version)
        if name == "eccodes":
            try:
                versions["ecCodes_C"] = str(module.codes_get_api_version())
            except Exception:
                pass
        if name == "netCDF4":
            for attribute in ("__netcdf4libversion__", "__hdf5libversion__"):
                value = getattr(module, attribute, None)
                if value is not None:
                    versions[attribute.strip("_")] = str(value)
    return versions


def execute_simulation(
    config: SimulationConfig,
    options: ExecutionOptions | None = None,
    *,
    input_files: tuple[Path, ...] | None = None,
) -> SimulationExecutionResult:
    """Execute one exclusively owned attempt with bounded local concurrency.

    ``run-status.yaml`` is authoritative only after all requested exports and
    input cleanup complete. A permitted shortened track is marked incomplete;
    strict batch callers may require full tracking explicitly.
    """
    from frameit.core.run_state import owned_run
    from frameit.core.runtime import (
        execution_scope,
        resolve_execution_resources,
        runtime_provenance,
    )

    requested = options or ExecutionOptions.from_config(config)
    effective, resources = resolve_execution_resources(requested)
    runtime = runtime_provenance()
    with owned_run(config.output_dir, overwrite=effective.overwrite, initial={
        "runtime": runtime, "resources": resources,
        "requested_execution_options": asdict(requested),
        "effective_execution_options": asdict(effective),
    }) as status:
        with execution_scope(effective):
            result = _execute_simulation(
                config, effective, status, runtime, input_files=input_files
            )
        if not result.ok:
            raise RuntimeError("Processing returned an unsuccessful result")
        result.execution_resources = resources
        status.update(
            state="completed" if result.tracking_complete else "incomplete",
            tracking_complete=result.tracking_complete,
            tracking_termination_reason=result.tracking_termination_reason,
            n_files=result.n_files, duration_s=result.duration_s,
            timing_sections_s=result.timing_sections_s,
            products=[{
                **product,
                "path": str(Path(product["path"]).relative_to(config.output_dir.resolve())),
                "size_bytes": Path(product["path"]).stat().st_size,
            } for product in result.products],
        )
        return result


def _execute_simulation(config, options, status, runtime, *, input_files=None):
    """Execute, export and release one simulation through the shared pipeline.

    An explicit inventory is consumed verbatim; ordinary runs discover files
    through the runner. Errors propagate after input and logging cleanup.
    """
    options = options or ExecutionOptions.from_config(config)
    if not options.no_hdf5_debug_pop:
        os.environ.pop("HDF5_DEBUG", None)
    level = options.log_level or ("DEBUG" if config.DEBUG else "INFO")
    started = time.monotonic()
    runner = None
    provenance = None
    with frameit_logging_scope(
        config.output_dir, level=level, simu_name=config.simulation_name
    ) as log_path:
        log = logging.getLogger("frameit")
        log.info("Log file: %s", log_path)
        log.info("Execution resources: %s", status["resources"])
        if options.benchmark:
            log.info("Benchmark: eager inputs; computation timed separately from I/O")
        try:
            # No ESMF/cfgrib/NetCDF backend import during CLI help or planning.
            from frameit.core.runner import FrameitRunner

            runner = FrameitRunner(config, input_files=input_files)
            result = runner.run(benchmark=True) if options.benchmark else runner.run()
            status["tracking_complete"] = bool(runner.track.attrs.get("tracking_complete", True))
            status["tracking_termination_reason"] = runner.track.attrs.get(
                "tracking_termination_reason", ""
            )
            if config.schema_version == 2:
                from frameit.utils.atomic import write_yaml_atomic

                resolved_path = config.output_dir / "resolved-config.yaml"
                from frameit.core.configuration import resolved_configuration, resolved_sources

                resolved = resolved_configuration(config, options)
                write_yaml_atomic(resolved_path, resolved, overwrite=options.overwrite)
                provenance = {
                        "runtime": runtime, "execution_resources": status["resources"],
                        "grid_geometry": config.grid_geometry,
                        "input_inventory": [str(p) for p in result.files],
                        "unit_provenance": config.simulation_parameter.get("unit_provenance", []),
                        "wind_provenance": config.simulation_parameter.get("wind_provenance", []),
                        "wind_transformations": config.simulation_parameter.get(
                            "wind_transformations", []),
                        "selected_levels": config.simulation_parameter.get("selected_levels", []),
                        "tracking_inputs": config.simulation_parameter.get(
                            "multifield_inputs", config.simulation_parameter.get(
                                "pressure_centroid_inputs", {})),
                        "tracking_summary": {
                            k: v for k, v in runner.track.attrs.items()
                            if k.startswith("tracking_")
                        },
                        "execution_options": asdict(options),
                        "setting_sources": resolved_sources(config, options),
                        "preset_provenance": {
                            k: v for k, v in config.simulation_parameter.items()
                            if k.startswith("preset_")
                        },
                    }
                write_yaml_atomic(config.output_dir / "run-provenance.yaml", provenance)
            if options.require_complete_tracking and not status["tracking_complete"]:
                raise ValueError(
                    "Tracking is incomplete and execution.require_complete_tracking is true: "
                    + status["tracking_termination_reason"]
                )
            exports = {}
            if options.export_netcdf:
                from frameit.io.netcdf_export import export_outputs

                with runner.timer.section("Netcdf export"):
                    exports = export_outputs(
                        runner,
                        institution=options.institution,
                        out_dir=config.output_dir.resolve(),
                        export_polar=options.export_polar,
                        export_cart=options.export_cart,
                        compress_level=options.compress_level,
                        synchronous=options.synchronous_export,
                        engine=options.engine, fmt=options.fmt, overwrite=options.overwrite,
                        compress_coords=options.compress_coords,
                        unlimited_time=options.unlimited_time,
                        max_workers=options.max_workers,
                        dask_scheduler=options.dask_scheduler, dask_workers=options.dask_workers,
                        native_threads=options.native_threads,
                    )
                log.debug("NetCDF export finished")
            else:
                log.info("NetCDF export skipped (--no-export-netcdf).")
            runner.timer.log_summary(log, title="FrameIt runtime summary")
            products = _product_descriptors(exports, runner)
            log.info("Run complete: %d input file(s) · %d product(s)",
                     result.n_files, len(products))
            return SimulationExecutionResult(
                ok=result.ok,
                n_files=result.n_files,
                output_dir=str(result.output_dir.resolve()),
                files=[str(path) for path in result.files],
                products=products,
                duration_s=time.monotonic() - started,
                log_path=str(log_path.resolve()),
                backend_versions=_loaded_backend_versions(),
                timing_sections_s=dict(runner.timer.sections),
                computation_s=sum(
                    runner.timer.sections.get(name, 0.0)
                    for name in ("tracking", "extraction", "polar_projection")
                ),
                regrid_performance=getattr(runner, "polar_report", {}).get(
                    "regrid_performance", {}
                ),
                tracking_complete=bool(runner.track.attrs.get("tracking_complete", True)),
                tracking_termination_reason=runner.track.attrs.get(
                    "tracking_termination_reason", ""),
            )
        except BaseException:
            log.exception("Simulation execution failed")
            raise
        finally:
            try:
                if runner is not None:
                    runner.close()
            finally:
                runtime["loaded_backends"] = _loaded_backend_versions()
                if provenance is not None:
                    write_yaml_atomic(config.output_dir / "run-provenance.yaml", provenance)
