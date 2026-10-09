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

    def __post_init__(self):
        if not 0 <= int(self.compress_level) <= 9:
            raise ValueError("compress_level must be in [0, 9]")


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
    """Execute, export and release one simulation through the shared pipeline.

    An explicit inventory is consumed verbatim; ordinary runs discover files
    through the runner. Errors propagate after input and logging cleanup.
    """
    options = options or ExecutionOptions()
    if not options.no_hdf5_debug_pop:
        os.environ.pop("HDF5_DEBUG", None)
    level = options.log_level or ("DEBUG" if config.DEBUG else "INFO")
    started = time.monotonic()
    runner = None
    with frameit_logging_scope(
        config.output_dir, level=level, simu_name=config.simulation_name
    ) as log_path:
        log = logging.getLogger("frameit")
        log.info("Logging initialized: %s", log_path)
        try:
            # No ESMF/cfgrib/NetCDF backend import during CLI help or planning.
            from frameit.core.runner import FrameitRunner

            runner = FrameitRunner(config, input_files=input_files)
            result = runner.run()
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
                    )
                log.info("NetCDF export done.")
            else:
                log.info("NetCDF export skipped (--no-export-netcdf).")
            runner.timer.log_summary(log, title="FrameIt runtime summary")
            log.info("FrameIt ends correctly")
            return SimulationExecutionResult(
                ok=result.ok,
                n_files=result.n_files,
                output_dir=str(result.output_dir.resolve()),
                files=[str(path) for path in result.files],
                products=_product_descriptors(exports, runner),
                duration_s=time.monotonic() - started,
                log_path=str(log_path.resolve()),
                backend_versions=_loaded_backend_versions(),
            )
        except BaseException:
            log.exception("Simulation execution failed")
            raise
        finally:
            if runner is not None:
                runner.close()
