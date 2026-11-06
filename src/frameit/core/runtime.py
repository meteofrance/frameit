"""Local execution budgets and portable runtime provenance; no scientific policy."""

from __future__ import annotations

import os
import platform
import signal
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

NATIVE_THREAD_VARIABLES = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS",
)
SLURM_VARIABLES = (
    "SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID", "SLURM_RESTART_COUNT",
    "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_NODE", "SLURM_MEM_PER_CPU", "SLURM_TIMELIMIT",
    "SLURM_JOB_PARTITION",
)


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
            raise ValueError("SLURM_CPUS_PER_TASK must be a positive integer") from exc
        if count < 1:
            raise ValueError("SLURM_CPUS_PER_TASK must be a positive integer")
        limits["slurm_cpus_per_task"] = count
    return max(1, min(limits.values())), limits


def resolve_execution_resources(options):
    """Resolve auto settings; reject explicit process/thread oversubscription.

    Processing and group export occur in successive phases. During export each
    process may have Dask threads, each of which may enter a native thread pool.
    The budget bounds their product; it is not a memory or file-handle budget.
    """
    cpus, limits = cpu_budget()
    dask_workers = 1 if options.dask_scheduler == "synchronous" else (options.dask_workers or 1)
    per_process = dask_workers * options.native_threads
    if per_process > cpus:
        raise ValueError(
            f"Dask workers × native threads ({per_process}) exceeds CPU budget ({cpus})"
        )
    export_workers = (1 if options.synchronous_export
                      else (options.max_workers or cpus // per_process))
    if export_workers * per_process > cpus:
        raise ValueError(
            f"Export workers × Dask workers × native threads ({export_workers * per_process}) "
            f"exceeds CPU budget ({cpus}); reduce output.max_workers or execution thread counts"
        )
    effective = replace(options, max_workers=export_workers, dask_workers=dask_workers)
    return effective, {
        "cpu_budget": cpus, "cpu_limits": limits, "export_workers": export_workers,
        "dask_scheduler": options.dask_scheduler, "dask_workers": dask_workers,
        "native_threads": options.native_threads,
        "export_start_method": None if options.synchronous_export else "spawn",
    }


@contextmanager
def execution_scope(options):
    """Bound both loaded native pools and libraries imported later; restore state."""
    previous = {key: os.environ.get(key) for key in NATIVE_THREAD_VARIABLES}
    try:
        for key in NATIVE_THREAD_VARIABLES:
            os.environ[key] = str(options.native_threads)
        import dask
        from threadpoolctl import threadpool_limits

        with dask.config.set(scheduler=options.dask_scheduler, num_workers=options.dask_workers), \
                threadpool_limits(limits=options.native_threads):
            yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def initialize_export_worker(scheduler, workers, native_threads):
    # Spawned workers must not fall back to Dask's machine-wide thread count.
    import dask
    from threadpoolctl import threadpool_limits

    dask.config.set(scheduler=scheduler, num_workers=workers)
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
        raise SystemExit(128 + signum)

    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def runtime_provenance():
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
