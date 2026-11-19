"""Local execution budgets and portable runtime provenance; no scientific policy."""

from __future__ import annotations

import os
import platform
import signal
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from frameit.utils.diagnostics import tag_error

NATIVE_THREAD_VARIABLES = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS",
)
SLURM_VARIABLES = (
    "SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID", "SLURM_RESTART_COUNT",
    "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_NODE", "SLURM_MEM_PER_CPU", "SLURM_TIMELIMIT",
    "SLURM_JOB_PARTITION",
)
_EXECUTION_RESOURCES = ContextVar("frameit_execution_resources", default=None)


def cpu_budget():
    """Use the strictest of task allocation, CPU affinity, and machine count."""
    limits = {"machine": os.cpu_count() or 1}
    if hasattr(os, "sched_getaffinity"):
        limits["affinity"] = len(os.sched_getaffinity(0))
    allocated = os.environ.get("SLURM_CPUS_PER_TASK")
    if allocated is None and os.environ.get("SLURM_JOB_ID"):
        # Slurm's default is one CPU per task. Without an explicit task request,
        # an unbound process may see the whole node through sched_getaffinity.
        limits["slurm_default_task"] = 1
    if allocated is not None:
        try:
            count = int(allocated)
        except ValueError as exc:
            raise tag_error(ValueError(
                "SLURM_CPUS_PER_TASK must be a positive integer"
            ), "E1701") from exc
        if count < 1:
            raise tag_error(ValueError("SLURM_CPUS_PER_TASK must be a positive integer"), "E1701")
        limits["slurm_cpus_per_task"] = count
    return max(1, min(limits.values())), limits


def resolve_execution_resources(options):
    """Resolve auto settings; reject explicit process/thread oversubscription.

    Processing and group export occur in successive phases. During export each
    process may have Dask threads, each of which may enter a native thread pool.
    The budget bounds their product; it is not a memory or file-handle budget.
    """
    available, limits = cpu_budget()
    cpus = options.cpus if options.cpus is not None else available
    if cpus > available:
        raise tag_error(ValueError(
            f"resources.cpus={cpus} exceeds the available CPU limit ({available}); "
            "reduce resources.cpus or request a larger allocation"
        ), "E1701")
    dask_workers = 1 if options.dask_scheduler == "synchronous" else (options.dask_workers or 1)
    per_process = dask_workers * options.native_threads
    if per_process > cpus:
        raise tag_error(ValueError(
            f"Dask workers × native threads ({per_process}) exceeds CPU budget ({cpus})"
        ), "E1701")
    export_workers = (1 if options.synchronous_export
                      else (options.max_workers or cpus // per_process))
    if export_workers * per_process > cpus:
        raise tag_error(ValueError(
            f"Export workers × Dask workers × native threads ({export_workers * per_process}) "
            f"exceeds CPU budget ({cpus}); reduce resources.export_workers, "
            "resources.compute_workers or resources.native_threads"
        ), "E1701")
    origins = dict(options.setting_sources)
    for key, value in (
        ("cpus", options.cpus), ("compute_workers", options.dask_workers),
        ("export_workers", options.max_workers),
    ):
        origins.setdefault(f"resources.{key}", "automatic" if value is None else "explicit")
    for key, attr in (("scheduler", "dask_scheduler"), ("native_threads", "native_threads"),
                      ("synchronous_export", "synchronous_export")):
        origins.setdefault(
            f"resources.{key}",
            "default" if getattr(options, attr) == getattr(type(options), attr) else "explicit")
    effective = replace(options, cpus=cpus, max_workers=export_workers,
                        dask_workers=dask_workers, setting_sources=origins)
    return effective, {
        "cpu_budget": cpus, "cpu_limits": limits, "export_workers": export_workers,
        "available_cpus": available, "reader_workers": 1,
        "dask_scheduler": options.dask_scheduler, "dask_workers": dask_workers,
        "native_threads": options.native_threads,
        "synchronous_export": options.synchronous_export,
        "export_start_method": None if options.synchronous_export else "spawn",
        "setting_sources": origins,
        "concurrency_scope": (
            "serial source readers; compute and export are successive phases; "
            "export_workers × compute_workers × native_threads <= cpu_budget"
        ),
    }


def current_execution_resources():
    """Return the active effective budget for nested local export pools."""
    return _EXECUTION_RESOURCES.get()


def _initialize_compute_thread(native_threads):
    from threadpoolctl import threadpool_limits

    # OpenMP limits are thread-local; a pre-existing Dask thread can retain another limit.
    threadpool_limits(limits=native_threads)


@contextmanager
def execution_scope(options):
    """Bound both loaded native pools and libraries imported later; restore state."""
    options, resources = resolve_execution_resources(options)
    token = _EXECUTION_RESOURCES.set(resources)
    previous = {key: os.environ.get(key) for key in NATIVE_THREAD_VARIABLES}
    try:
        for key in NATIVE_THREAD_VARIABLES:
            os.environ[key] = str(options.native_threads)
        import dask
        from threadpoolctl import threadpool_limits

        pool = (ThreadPoolExecutor(
            max_workers=options.dask_workers, initializer=_initialize_compute_thread,
            initargs=(options.native_threads,))
            if options.dask_scheduler == "threads" else nullcontext(None))
        with threadpool_limits(limits=options.native_threads), pool as workers, \
                dask.config.set(scheduler=options.dask_scheduler, num_workers=options.dask_workers,
                                pool=workers):
            yield
    finally:
        _EXECUTION_RESOURCES.reset(token)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def initialize_export_worker(scheduler, workers, native_threads):
    # Spawned workers must not fall back to Dask's machine-wide thread count.
    import dask
    from threadpoolctl import threadpool_limits

    for key in NATIVE_THREAD_VARIABLES:
        os.environ[key] = str(native_threads)
    pool = (ThreadPoolExecutor(max_workers=workers, initializer=_initialize_compute_thread,
                               initargs=(native_threads,)) if scheduler == "threads" else None)
    dask.config.set(scheduler=scheduler, num_workers=workers, pool=pool)
    threadpool_limits(limits=native_threads)


@contextmanager
def termination_scope():
    """Let the CLI record ordinary SIGTERM cancellation and return status 143.

    SIGKILL, native crashes and node loss cannot run Python cleanup. Their last
    manifest remains running and their lock must not be reclaimed automatically.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def terminate(signum, _frame):
        raise tag_error(SystemExit(128 + signum), "E0002")

    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def runtime_provenance(resources=None):
    from frameit._version import __version__

    packages = {}
    for name in (
        "numpy", "scipy", "xarray", "dask", "PyYAML", "pyproj", "netCDF4", "h5netcdf",
        "h5py", "cfgrib", "eccodes", "xesmf", "esmpy", "threadpoolctl",
        "falfilfa4py", "ctypesForFortran",
    ):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            pass
    result = {
        "frameit_version": __version__, "python": platform.python_version(),
        "installed_packages": packages,
        "slurm": {key: os.environ[key] for key in SLURM_VARIABLES if key in os.environ},
        "code_revision": None, "code_dirty": None,
    }
    effective = resources if resources is not None else current_execution_resources()
    if effective is not None:
        result["execution_resources"] = effective
    root = Path(__file__).resolve().parents[3]
    if (root / ".git").exists():
        try:
            result["code_revision"] = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, timeout=5,
                stderr=subprocess.DEVNULL,
            ).strip()
            result["code_dirty"] = bool(subprocess.check_output(
                ["git", "-C", str(root), "status", "--porcelain"], text=True, timeout=5,
                stderr=subprocess.DEVNULL,
            ).strip())
        except (OSError, subprocess.SubprocessError):
            pass
    # Wheels may not contain a checkout. A supplied revision is explicitly a claim.
    if result["code_revision"] is None and os.environ.get("FRAMEIT_CODE_REVISION"):
        result["code_revision"] = os.environ["FRAMEIT_CODE_REVISION"]
        result["code_revision_source"] = "environment_unverified"
    return result
