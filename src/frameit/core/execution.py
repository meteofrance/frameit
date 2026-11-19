from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from frameit.core.reports import error_record, primary_error_code
from frameit.core.settings_class import SimulationConfig
from frameit.utils.diagnostics import format_message, tag_error
from frameit.utils.logging import frameit_logging_scope

DEFAULT_INSTITUTION = ""


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
    overwrite: bool = False
    compress_coords: bool = False
    unlimited_time: bool = True
    max_workers: int | None = None
    dask_scheduler: str = "threads"
    dask_workers: int | None = None
    native_threads: int = 1
    require_complete_tracking: bool = False
    zarr_chunk_size: dict[str, int] = field(default_factory=dict)
    zarr_shard_size: dict[str, int] = field(default_factory=dict)
    netcdf_chunk_size: dict[str, int] = field(default_factory=dict)
    cpus: int | None = None
    setting_sources: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config, **overrides):
        if config.schema_version == 3:
            document = config.yaml_config
            output, resources = document["output"], document["resources"]
            writer, products = output["writer"], document["products"]
            values = {
                "export_netcdf": bool(products),
                "export_cart": "model_grid" in products, "export_polar": "polar" in products,
                "compress_level": writer["compression"]["level"],
                "compress_coords": writer["compression"]["coordinates"],
                "institution": document["metadata"].get("institution", ""),
                "engine": "zarr" if output["format"] == "zarr" else writer["engine"],
                "overwrite": output["overwrite"], "unlimited_time": writer.get("unlimited_time", True),
                "max_workers": resources.get("export_workers"), "log_level": config.log_level,
                "synchronous_export": resources["synchronous_export"],
                "dask_scheduler": resources["scheduler"], "dask_workers": resources.get("compute_workers"),
                "native_threads": resources["native_threads"], "cpus": resources.get("cpus"),
                "require_complete_tracking": document["region"].get("tracker", {}).get(
                    "on_incomplete", "error") == "error",
                "zarr_chunk_size": writer.get("chunks", {}) if output["format"] == "zarr" else {},
                "zarr_shard_size": writer.get("shards", {}),
                "netcdf_chunk_size": writer.get("chunks", {})
                if output["format"] == "netcdf" else {},
                "setting_sources": {key: value for key, value in config.schema_sources.items()
                                    if key.startswith("resources.")},
            }
            for attr, key in (
                ("cpus", "cpus"), ("max_workers", "export_workers"),
                ("dask_workers", "compute_workers"), ("dask_scheduler", "scheduler"),
                ("native_threads", "native_threads"), ("synchronous_export", "synchronous_export"),
            ):
                if overrides.get(attr) is not None:
                    values["setting_sources"][f"resources.{key}"] = "cli"
            values.update({key: value for key, value in overrides.items() if value is not None})
            return cls(**values)
        output = config.yaml_config.get("output", {})
        execution = config.yaml_config.get("execution", {})
        values = {
            "export_netcdf": output.get("export", {}).get("enabled", True),
            "export_cart": output.get("export", {}).get("cartesian", True),
            "export_polar": output.get("export", {}).get("polar", True),
            "compress_level": output.get("compression", {}).get("level", 1),
            "compress_coords": output.get("compression", {}).get("coordinates", False),
            "institution": output.get("institution", DEFAULT_INSTITUTION),
            "engine": output.get("backend", "netcdf4"), "fmt": output.get("netcdf_format", "NETCDF4"),
            "overwrite": output.get("overwrite", False),
            "unlimited_time": output.get("unlimited_time", True),
            "max_workers": output.get("max_workers"), "log_level": config.log_level,
            "synchronous_export": output.get("synchronous_export", False),
            "dask_scheduler": execution.get("dask_scheduler", "threads"),
            "dask_workers": execution.get("dask_workers"),
            "native_threads": execution.get("native_threads", 1),
            "require_complete_tracking": execution.get("require_complete_tracking", False),
            "zarr_chunk_size": output.get("zarr_chunk_size", {}),
            "zarr_shard_size": output.get("zarr_shard_size", {}),
        }
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)

    def __post_init__(self):
        from frameit.io.zarr_export import validate_zarr_sizes

        validate_zarr_sizes(self.zarr_chunk_size, self.zarr_shard_size)
        validate_zarr_sizes(self.netcdf_chunk_size, {})
        object.__setattr__(self, "netcdf_chunk_size", self.netcdf_chunk_size.copy())
        object.__setattr__(self, "zarr_chunk_size", self.zarr_chunk_size.copy())
        object.__setattr__(self, "zarr_shard_size", self.zarr_shard_size.copy())
        if self.engine not in {"netcdf4", "h5netcdf", "zarr"}:
            raise tag_error(ValueError("output.backend must be netcdf4, h5netcdf or zarr"),
                            "E1805")
        if not 0 <= int(self.compress_level) <= 9:
            raise tag_error(ValueError("compress_level must be in [0, 9]"), "E1805")
        for name in ("max_workers", "dask_workers", "native_threads", "cpus"):
            value = getattr(self, name)
            if (value is not None or name == "native_threads") and (
                type(value) is not int or value < 1
            ):
                raise tag_error(ValueError(f"{name} must be a positive integer"), "E1701")
        for name in ("synchronous_export", "require_complete_tracking"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if self.dask_scheduler not in {"threads", "synchronous"}:
            raise tag_error(ValueError("dask_scheduler must be threads or synchronous"), "E1701")


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
    if getattr(runner.conf, "schema_version", None) == 3:
        published = {str(Path(path).resolve()) for paths in exports.values() for path in paths}
        return [item for item in getattr(runner, "published_products", [])
                if item["path"] in published]
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

        suffix = Path(paths[0]).suffix if paths else ".nc"
        filenames = {
            f"{runner.conf.simulation_name}.{role}.{_sanitize_filename_token(str(group))}{suffix}": str(
                group
            )
            for group in groups
        }
        for path in paths:
            path = Path(path)
            product = {"role": role, "group": filenames.get(path.name),
                       "path": str(path.resolve())}
            dataset = groups.get(filenames.get(path.name))
            if dataset is not None and "source_id" in dataset.attrs:
                product.update(source=dataset.attrs["source_id"],
                               source_group=dataset.attrs["source_group"])
            products.append(product)
    return products


def _loaded_backend_versions():
    """Record native versions without initializing otherwise unused backends."""
    versions = {}
    for name in ("eccodes", "ESMF", "esmpy", "xesmf", "netCDF4", "h5netcdf", "h5py", "pyproj",
                 "zarr"):
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


def _input_path_locations(paths):
    """Retain physical targets and all symlink entries needed to reach inputs."""
    locations, checked = set(), set()
    pending = list(paths)
    while pending:
        path = pending.pop().absolute()
        if path in checked:
            continue
        checked.add(path)
        locations.update((path, path.resolve()))
        # resolve() hides intermediate links, including those in parent directories.
        for entry in (path, *path.parents):
            if entry.is_symlink():
                locations.add(entry.parent.resolve() / entry.name)
                pending.append(entry.parent / entry.readlink())
    return locations


def _run_provenance(config, options, status, runtime):
    from frameit.core.configuration import resolved_sources

    plan = config.simulation_parameter.get("request_plan", {})
    sources = plan.get("sources", {})
    warnings = list(plan.get("warnings", ()))
    for source in sources.values():
        binding = source.get("requests", {}).get("binding") or {}
        warnings.extend(binding.get("warnings", ()))
    return {
        "runtime": runtime, "execution_resources": status["resources"],
        **({"warnings": list(dict.fromkeys(warnings))} if warnings else {}),
        "time_alignment": config.simulation_parameter.get("time_alignment", {}),
        "sources": config.simulation_parameter.get("source_provenance", {}),
        "binding": {name: {
            "status": source.get("requests", {}).get("binding", {}).get("status"),
            "model": source.get("model"), "format": source.get("format"),
            "files": source.get("files"),
            "selected_times": [str(value) for value in source.get("selected_times", [])],
            "excluded_files": source.get("excluded_files", []),
        } for name, source in sources.items()},
        "common_polar_target": config.simulation_parameter.get("common_polar_target"),
        "fa_inputs": config.simulation_parameter.get("fa_inputs", []),
        "grid_geometry": config.grid_geometry,
        "input_inventory": list(dict.fromkeys(
            str(path) for source in sources.values() for path in source.get("files") or [])),
        **{key: config.simulation_parameter.get(key, []) for key in (
            "unit_provenance", "surfex_provenance", "current_provenance", "wind_provenance",
            "wind_transformations", "selected_levels")},
        "tracking_inputs": config.simulation_parameter.get(
            "multifield_inputs", config.simulation_parameter.get("pressure_centroid_inputs", {})),
        "execution_options": asdict(options),
        "setting_sources": resolved_sources(config, options),
        "preset_provenance": {key: value for key, value in config.simulation_parameter.items()
                              if key.startswith("preset_")},
    }


def _recorded_product(product, root):
    path = Path(product["path"])
    return {
        **product, "path": str(path.relative_to(root.resolve())),
        "size_bytes": (sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file())
                       if path.is_dir() else path.stat().st_size),
    }


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
    from contextlib import ExitStack

    from frameit.utils.logging import _QuietProgress

    options = options or ExecutionOptions.from_config(config)
    level = options.log_level or ("DEBUG" if config.DEBUG else "INFO")
    with ExitStack() as logs:
        logs.enter_context(frameit_logging_scope(None, level=level))
        progress = _QuietProgress(logging.getLogger("frameit"))
        logs.callback(progress.stop)
        progress.start()
        try:
            result = _execute_owned_simulation(config, options, input_files, progress, logs, level)
        except BaseException as exc:
            progress.finish("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit))
                            else "failed", code=primary_error_code(exc))
            raise
        progress.finish("complete" if result.tracking_complete else "incomplete",
                        code=None if result.tracking_complete else "W1501")
        return result


def _execute_owned_simulation(config, options, input_files, progress, logs, level):
    """Keep logging alive through ownership finalization, not just export."""
    from copy import deepcopy

    from frameit.core.run_state import owned_run
    from frameit.core.runtime import (
        execution_scope,
        resolve_execution_resources,
        runtime_provenance,
    )

    requested = options or ExecutionOptions.from_config(config)
    effective, resources = resolve_execution_resources(requested)
    prepared_sources = None
    selected_plan = None
    if config.schema_version == 3:
        from frameit.utils.output_paths import OutputPaths

        planned_paths = OutputPaths(config.output_dir).planned_products(
            config.simulation_parameter["request_plan"]["products"])
        requested_format = "zarr" if requested.engine == "zarr" else "netcdf"
        if requested_format != config.yaml_config["output"]["format"]:
            raise tag_error(ValueError(
                "Execution engine conflicts with output.format; select the format "
                "in the configuration before execution"
            ), "E1805")
        from frameit.core.coupled import bind_sources
        from frameit.core.preflight import preflight_result
        from frameit.core.reports import PreflightError

        progress.update("preparing metadata/selected source plans",
                        source=next(iter(config.sources)) if len(config.sources) == 1 else None)
        try:
            prepared_sources = bind_sources(config, execution_options=effective)
        except ValueError as exc:
            raise ValueError(f"Cannot bind source requests to metadata: {exc}") from exc

        selected_plan = preflight_result(config, prepared_sources[0], command="run")
        if selected_plan.errors:
            raise PreflightError(selected_plan.errors, facts=selected_plan.facts,
                                 deferred_checks=selected_plan.deferred_checks)
        if set(config.yaml_config["products"]) - {"model_grid", "polar", "track"}:
            raise ValueError("Non-native product execution requires its method binding")
        from frameit.processing.polar.contracts import require_executable_products

        for source in prepared_sources[2].values():
            require_executable_products(source["requests"]["binding"], source)
        sources = prepared_sources[2].values()
        selected = {Path(path).resolve() for source in sources for path in source["files"]}
        if input_files is not None and {Path(path).resolve() for path in input_files} != selected:
            raise ValueError("Explicit input inventory differs from the bound source inventory")
        inputs = []
        for source in sources:
            inputs.extend(Path(path) for entry in source["file_inventory"]
                          for path in (entry["path"], *entry["aliases"]))
            inputs.extend(Path(path) for path in source["excluded_files"])
        if "track" in config.yaml_config["region"]:
            inputs.append(Path(config.yaml_config["region"]["track"]["file"]))
        input_locations = _input_path_locations(inputs)
        targets = planned_paths
        targets += [config.output_dir / name for name in (
            "run-request.yaml", "resolved-config.yaml", "run-provenance.yaml",
            "run-status.yaml", ".frameit-run.lock")]
        for target in targets:
            if target.exists() and any(path.exists() and target.samefile(path) for path in inputs):
                raise tag_error(ValueError(f"Output would replace a source input: {target}"),
                                "E1804")
            if target.is_dir() and any(path.is_relative_to(target.resolve())
                                       for path in input_locations):
                raise tag_error(ValueError(
                    f"Output would replace a directory containing a source input: {target}"
                ), "E1804")
    if requested.export_netcdf and requested.engine == "zarr":
        from frameit.io.zarr_export import check_zarr_dependencies

        check_zarr_dependencies()
    runtime = runtime_provenance(resources)
    initial = {
        "runtime": runtime, "resources": resources,
        "requested_execution_options": asdict(requested),
        "effective_execution_options": asdict(effective),
        "planned_products": deepcopy(config.simulation_parameter.get(
            "request_plan", {}).get("products", [])),
        "pending": ["processing", "publication", "cleanup"],
    }
    request = {"record_version": 1, **deepcopy(config.request_context),
               "requested_execution_options": asdict(requested), "runtime": deepcopy(runtime)}
    provenance = (_run_provenance(config, effective, initial, runtime)
                  if config.schema_version == 3 else None)
    if provenance is not None:
        provenance["layouts"] = prepared_sources[0].get("layouts")
    owned_status = None
    try:
        with owned_run(config.output_dir, overwrite=effective.overwrite, initial=initial,
                       request=request, provenance=provenance) as status:
            owned_status = status
            progress.stop()
            log_path = logs.enter_context(frameit_logging_scope(
                config.output_dir, level=level, simu_name=config.simulation_name))
            logs.callback(progress.stop)
            progress.start()
            log = logging.getLogger("frameit")
            log.info("Log file: %s", log_path)
            log.info("Execution resources: %s", status["resources"])
            if config.schema_version == 3:
                from frameit.core.configuration import resolved_configuration
                from frameit.utils.atomic import write_yaml_atomic

                try:
                    write_yaml_atomic(config.output_dir / "resolved-config.yaml",
                                      resolved_configuration(config, effective),
                                      overwrite=effective.overwrite)
                except Exception as exc:
                    raise tag_error(exc, "E1808")
            with execution_scope(effective):
                result = _execute_simulation(
                    config, effective, status, runtime, input_files=input_files,
                    prepared_sources=prepared_sources, provenance=provenance,
                    selected_plan=selected_plan, progress=progress, log_path=log_path,
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
                pending=[],
                products=[_recorded_product(product, config.output_dir)
                          for product in result.products],
            )
            progress.update("finalizing run records/ownership")
            return result
    except BaseException as exc:
        if owned_status is not None:
            try:
                facts = {key: deepcopy(owned_status[key]) for key in (
                    "products", "pending", "tracking_complete", "tracking_termination_reason",
                    "started_at", "finished_at") if key in owned_status}
                plan = config.simulation_parameter.get("request_plan", {})
                facts.update(
                    state=("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit))
                           else "failed"),
                    observed_owner_state=owned_status["state"],
                    error=error_record(exc),
                    warnings=deepcopy(plan.get("warnings", [])),
                    exclusions={name: deepcopy(source.get("excluded_files", []))
                                for name, source in plan.get("sources", {}).items()},
                    current_attempt="Owner-attested in-memory facts after ownership unwind; "
                                    "final record persistence is not verified.",
                )
                exc._frameit_failure = {"root": str(config.output_dir), "facts": facts}
            except BaseException:
                # Optional presentation metadata must not replace the execution failure.
                pass
        raise


def _execute_simulation(config, options, status, runtime, *, input_files=None,
                        prepared_sources=None, provenance=None, selected_plan=None,
                        progress, log_path):
    """Execute, export and release one simulation through the shared pipeline.

    An explicit inventory is consumed verbatim; ordinary runs discover files
    through the runner. Errors propagate after input and logging cleanup.
    """
    options = options or ExecutionOptions.from_config(config)
    if not options.no_hdf5_debug_pop:
        os.environ.pop("HDF5_DEBUG", None)
    started = time.monotonic()
    runner = None
    failure = None
    log = logging.getLogger("frameit")
    from frameit.core.run_state import checkpoint_run, finalize_after

    def published(product):
        progress.update("computing/writing exports", published_products=1)
        status["products"].append(_recorded_product(product, config.output_dir))
        checkpoint_run(config.output_dir, status, provenance)

    if options.benchmark:
        log.info("Benchmark: eager inputs; computation timed separately from I/O")
    try:
        # No ESMF/cfgrib/NetCDF backend import during CLI help or planning.
        from frameit.core.runner import FrameitRunner

        runner = FrameitRunner(config, input_files=input_files,
                               prepared_sources=prepared_sources)
        runner.preflight_result = selected_plan
        runner.progress = progress
        progress.update("preparing lazy source views/calculations")
        result = runner.run(benchmark=True) if options.benchmark else runner.run()
        status["pending"].remove("processing")
        layouts = None
        if config.schema_version == 3:
            layouts = runner.preflight_report["layouts"]
            for name, source in runner.prepared_sources[2].items():
                if "reader_layout" in source:
                    layouts["inputs"][name].update(source["reader_layout"])
            for (source, product), dataset in runner.field_products.items():
                spec = config.yaml_config["products"][product]
                chunks = (spec.get("processing", {}).get("chunks", {})
                          if isinstance(spec, dict) else {})
                dataset = dataset.chunk({dim: size for dim, size in chunks.items()
                                         if dim in dataset.dims})
                runner.field_products[(source, product)] = dataset
                layouts["products"][f"{source}.{product}"].update(
                    chunks={name: {dim: list(sizes)
                                   for dim, sizes in value.variable.chunksizes.items()}
                            for name, value in dataset.data_vars.items()},
                    dimensions=dict(dataset.sizes),
                    uncompressed_arrays_bytes=sum(
                        value.nbytes for value in dataset.variables.values()),
                    resolved_chunks="actual lazy product before storage rechunking")
        track_attrs = runner.track.attrs if runner.track is not None else {}
        status["tracking_complete"] = bool(track_attrs.get("tracking_complete", True))
        status["tracking_termination_reason"] = track_attrs.get(
            "tracking_termination_reason", ""
        )
        if "time_alignment" in config.simulation_parameter:
            status["time_alignment"] = config.simulation_parameter["time_alignment"]
            if config.simulation_parameter.get("common_polar_target") is not None:
                status["common_polar_target"] = config.simulation_parameter[
                    "common_polar_target"]
        if config.schema_version == 3:
            provenance.update(_run_provenance(config, options, status, runtime))
            provenance.update(
                input_inventory=[str(path) for path in result.files],
                tracking_summary={key: value for key, value in track_attrs.items()
                                  if key.startswith("tracking_")},
                layouts=layouts)
            checkpoint_run(config.output_dir, status, provenance)
        if options.require_complete_tracking and not status["tracking_complete"]:
            raise tag_error(ValueError(
                "Tracking is incomplete; region.tracker.on_incomplete: error "
                "or --require-complete-tracking requires a complete trajectory: "
                + status["tracking_termination_reason"]
            ), "E1504")
        exports = {}
        if options.export_netcdf:
            from frameit.io.netcdf_export import export_outputs

            progress.update("computing/writing exports")
            try:
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
                        zarr_chunk_size=options.zarr_chunk_size,
                        zarr_shard_size=options.zarr_shard_size,
                        netcdf_chunk_size=options.netcdf_chunk_size,
                        on_published=published,
                    )
            except FileExistsError as exc:
                raise tag_error(exc, "E1802")
            except Exception as exc:
                raise tag_error(exc, "E1806")
            log.debug("Product export finished (engine=%s)", options.engine)
        else:
            log.info("Product export skipped (--no-export).")
        status["pending"].remove("publication")
        runner.timer.log_summary(log, title="FrameIt runtime summary")
        products = _product_descriptors(exports, runner)
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
            tracking_complete=bool(track_attrs.get("tracking_complete", True)),
            tracking_termination_reason=track_attrs.get(
                "tracking_termination_reason", ""),
        )
    except BaseException as exc:
        failure = exc
        if runner is not None and hasattr(runner, "published_products"):
            status["products"] = [
                _recorded_product(item, config.output_dir)
                for item in runner.published_products]
        log.exception(format_message(primary_error_code(exc), "Simulation execution failed"))
        raise
    finally:
        progress.reconcile_published(len(getattr(runner, "published_products", ())))
        progress.update("cleanup")
        try:
            with finalize_after(failure, "Input cleanup also failed"):
                if runner is not None:
                    runner.close()
                status["pending"].remove("cleanup")
        except BaseException as exc:
            failure = exc
            raise
        finally:
            with finalize_after(failure, "Finalizing execution records also failed"):
                progress.update("finalizing execution records")
                runtime["loaded_backends"] = _loaded_backend_versions()
                if provenance is not None:
                    provenance.update(_run_provenance(config, options, status, runtime))
                    status["products"] = [
                        _recorded_product(item, config.output_dir)
                        for item in getattr(runner, "published_products", [])]
                    from frameit.io.fa_backend import collect_fa_diagnostics

                    if provenance["fa_inputs"]:
                        provenance["fa_decoder"] = collect_fa_diagnostics(
                            config.output_dir, provenance["fa_inputs"])
                    for source in provenance["sources"].values():
                        if source["fa_inputs"]:
                            source["fa_decoder"] = collect_fa_diagnostics(
                                config.output_dir, source["fa_inputs"])
                    checkpoint_run(config.output_dir, status, provenance)
