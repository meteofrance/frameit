"""Batch lifecycle and real spawned-export regressions on compact synthetic data."""

from __future__ import annotations

import os
import signal
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import dask
import netCDF4
import numpy as np
import pytest
import xarray as xr
import yaml
from threadpoolctl import threadpool_info

from frameit.core.configuration import resolve_schema
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.run_state import owned_run
from frameit.core.runtime import execution_scope, resolve_execution_resources
from frameit.core.settings_class import SimulationConfig
from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf, write_group_dict
from frameit.utils.atomic import atomic_output

from .test_configuration_v2 import dataset, document

SLURM_EXAMPLES = Path(__file__).parents[4] / "example" / "slurm"


def test_resource_limits_use_strictest_allocation_and_affinity(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: {0, 1, 2, 3})
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "2")
    effective, resources = resolve_execution_resources(ExecutionOptions())
    assert resources["cpu_budget"] == 2
    assert effective.max_workers == 2 and effective.dask_workers == 1
    with pytest.raises(ValueError, match="exceeds CPU budget"):
        resolve_execution_resources(ExecutionOptions(max_workers=3))
    with pytest.raises(ValueError, match="exceeds CPU budget"):
        resolve_execution_resources(ExecutionOptions(dask_workers=2, native_threads=2))
    effective, _ = resolve_execution_resources(ExecutionOptions(
        synchronous_export=True, max_workers=20, dask_workers=2,
    ))
    assert effective.max_workers == 1 and effective.dask_workers == 2
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "broken")
    with pytest.raises(ValueError, match="SLURM_CPUS_PER_TASK"):
        resolve_execution_resources(ExecutionOptions())
    monkeypatch.delenv("SLURM_CPUS_PER_TASK")
    monkeypatch.setenv("SLURM_JOB_ID", "unbound-task")
    assert resolve_execution_resources(ExecutionOptions())[1]["cpu_budget"] == 1


@pytest.mark.parametrize("section", [
    {"execution": {"native_threads": 0}}, {"execution": {"dask_workers": True}},
    {"execution": {"dask_scheduler": "processes"}},
    {"execution": {"require_complete_tracking": "false"}},
    {"output": {"synchronous_export": "false"}},
])
def test_invalid_execution_schema(tmp_path, section):
    with pytest.raises(ValueError):
        resolve_schema(document(tmp_path, **section))


def test_thread_scope_restores_environment_and_dask(monkeypatch):
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "29")
    before = dask.config.get("scheduler", None)
    with execution_scope(ExecutionOptions(dask_workers=1)):
        assert os.environ["OPENBLAS_NUM_THREADS"] == "1"
        assert dask.config.get("num_workers") == 1
        assert all(pool["num_threads"] == 1 for pool in threadpool_info())
    assert os.environ["OPENBLAS_NUM_THREADS"] == "29"
    assert dask.config.get("scheduler", None) == before


def test_exclusive_run_ownership_and_early_no_clobber(tmp_path, monkeypatch):
    root = tmp_path / "out"
    with owned_run(root, overwrite=False, initial={}) as status:
        with pytest.raises(FileExistsError, match="locked"):
            with owned_run(root, overwrite=True, initial={}):
                pytest.fail("A second owner entered the directory")
        status["state"] = "completed"
    original = (root / "run-status.yaml").read_bytes()
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, output={
        "directory": str(root), "overwrite": False,
    }))
    monkeypatch.setattr("frameit.core.execution._execute_simulation", lambda *a, **k: pytest.fail(
        "No-clobber must fail before processing"
    ))
    with pytest.raises(FileExistsError, match="Existing run artifacts"):
        execute_simulation(conf)
    assert (root / "run-status.yaml").read_bytes() == original
    assert not (root / ".frameit-run.lock").exists()


def test_atomic_no_clobber_publication_race(tmp_path):
    final = tmp_path / "output"
    with pytest.raises(FileExistsError):
        with atomic_output(final, overwrite=False) as temporary:
            temporary.write_bytes(b"new")
            final.write_bytes(b"other writer")
    assert final.read_bytes() == b"other writer"
    assert list(tmp_path.iterdir()) == [final]


def test_atomic_publication_honors_umask_and_retains_existing_permissions(tmp_path):
    final = tmp_path / "shared-product"
    previous = os.umask(0o027)
    try:
        with atomic_output(final) as temporary:
            temporary.write_bytes(b"first")
    finally:
        os.umask(previous)
    assert stat.S_IMODE(final.stat().st_mode) == 0o640
    final.chmod(0o660)
    with atomic_output(final) as temporary:
        temporary.write_bytes(b"second")
    assert stat.S_IMODE(final.stat().st_mode) == 0o660


@pytest.mark.parametrize("engine", ["netcdf4", "h5netcdf"])
def test_failed_netcdf_write_preserves_previous_complete_product(tmp_path, monkeypatch, engine):
    final = tmp_path / "product.nc"
    meta = ExportMetadata("test", "test", "test", "test", "test", user_metadata={"case": "pilot"})
    ds = xr.Dataset({"value": ("time", [3.0])}, coords={"time": [0]})
    write_dataset_netcdf(ds, final, metadata=meta, product_type="track", engine=engine)
    with netCDF4.Dataset(final) as saved:
        assert saved.frameit_user_metadata_json == '{"case": "pilot"}'
    before = final.read_bytes()

    def fail(_self, path, **kwargs):
        Path(path).write_bytes(b"interrupted bytes")
        raise OSError("simulated full filesystem")

    monkeypatch.setattr(xr.Dataset, "to_netcdf", fail)
    with pytest.raises(OSError, match="full filesystem"):
        write_dataset_netcdf(ds, final, metadata=meta, product_type="track", engine=engine)
    assert final.read_bytes() == before
    assert list(tmp_path.iterdir()) == [final]


def test_group_filename_collisions_fail_before_writing(tmp_path):
    meta = ExportMetadata("test", "test", "test", "test", "test")
    with pytest.raises(ValueError, match="same NetCDF destination"):
        write_group_dict(
            {"a/b": xr.Dataset(), "a_b": xr.Dataset()}, tmp_path,
            simu_name="test", grid="cart", metadata=meta, track_filename="test.track.nc",
        )
    assert not list(tmp_path.iterdir())


def cli_environment():
    return {
        **os.environ, "SLURM_CPUS_PER_TASK": "1", "SLURM_JOB_ID": "local-qualification",
        "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        "PYTHONNOUSERSITE": "1",
    }


@pytest.fixture(scope="module")
def cli_attempts(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("hpc-concurrent")
    dataset(tmp_path)
    config = tmp_path / "case.yaml"
    config.write_text(yaml.safe_dump(document(
        tmp_path, domain={"size_km": {"x": 20, "y": 20}},
    )))

    def run(mode):
        args = [
            sys.executable, "-m", "frameit", "run", str(config),
            "--output-directory", str(tmp_path / mode), "--no-overwrite",
            "--max-workers", "1", "--require-complete-tracking",
        ]
        if mode == "sync":
            args.append("--synchronous-export")
        return subprocess.run(
            args, env=cli_environment(), capture_output=True, text=True, timeout=60
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        runs = list(executor.map(run, ["spawn", "sync"]))
    for mode, run in zip(["spawn", "sync"], runs, strict=True):
        assert run.returncode == 0, run.stdout + run.stderr
        root = tmp_path / mode
        status = yaml.safe_load((root / "run-status.yaml").read_text())
        assert status["state"] == "completed" and status["tracking_complete"]
        assert len(status["products"]) == 2
        assert status["resources"]["cpu_budget"] == 1
        assert status["runtime"]["slurm"]["SLURM_JOB_ID"] == "local-qualification"
        assert not (root / ".frameit-run.lock").exists()
        assert not list(root.rglob("*.partial"))
        provenance = yaml.safe_load((root / "run-provenance.yaml").read_text())
        assert "netCDF4" in provenance["runtime"]["loaded_backends"]
        replay = SimulationConfig.from_yaml(root / "resolved-config.yaml")
        assert replay.yaml_config["output"]["synchronous_export"] == (mode == "sync")
        cart = next(p for p in status["products"] if p["role"] == "cart")
        with netCDF4.Dataset(root / cart["path"]) as saved:
            np.testing.assert_allclose(saved.variables["wind_speed"][:], 10., rtol=0, atol=0)
            assert saved.variables["UM10"].units == "m s-1"
    return tmp_path


def test_concurrent_cli_attempts_spawn_and_sync_export_exactly(cli_attempts):
    for path in (cli_attempts / "spawn" / "products").glob("*.nc"):
        with xr.open_dataset(path) as actual, xr.open_dataset(
            cli_attempts / "sync" / "products" / path.name
        ) as reference:
            xr.testing.assert_equal(actual, reference)
            for name in actual.variables:
                xr.testing.assert_identical(actual[name], reference[name])


@pytest.mark.skipif(
    not (SLURM_EXAMPLES / "check_run.py").is_file(), reason="Requires checkout examples"
)
def test_independent_checker_accepts_reference_and_rejects_wrong_time_count(cli_attempts):
    tmp_path = cli_attempts
    checker = SLURM_EXAMPLES / "check_run.py"
    checked = subprocess.run([
        sys.executable, str(checker), str(tmp_path / "spawn"), "--expected-times", "2",
        "--reference", str(tmp_path / "sync"), "--report", str(tmp_path / "check.json"),
    ], capture_output=True, text=True, timeout=30, env=cli_environment())
    assert checked.returncode == 0, checked.stdout + checked.stderr

    wrong_count = subprocess.run([
        sys.executable, str(checker), str(tmp_path / "spawn"), "--expected-times", "3",
    ], capture_output=True, text=True, env=cli_environment(), timeout=30)
    assert wrong_count.returncode == 1 and '"ok": false' in wrong_count.stdout


def test_batch_overrides_dry_run_does_not_claim_output(tmp_path):
    dataset(tmp_path)
    config = tmp_path / "case.yaml"
    config.write_text(yaml.safe_dump(document(tmp_path)))
    destination = tmp_path / "planned-only"
    run = subprocess.run([
        sys.executable, "-m", "frameit", "run", str(config), "--dry-run",
        "--output-directory", str(destination), "--synchronous-export", "--no-overwrite",
    ], capture_output=True, text=True, env=cli_environment(), timeout=30)
    assert run.returncode == 0, run.stderr
    plan = yaml.safe_load(run.stdout)
    assert plan["configuration"]["output"]["directory"] == str(destination)
    assert plan["configuration"]["output"]["synchronous_export"] is True
    assert plan["configuration"]["output"]["overwrite"] is False
    assert plan["execution_resources"]["export_start_method"] is None
    assert not destination.exists()


def test_cli_processing_failure_never_marks_completed(tmp_path):
    config = tmp_path / "case.yaml"
    root = tmp_path / "failed"
    config.write_text(yaml.safe_dump(document(tmp_path)))  # No matching inputs.
    run = subprocess.run([
        sys.executable, "-m", "frameit", "run", str(config),
        "--output-directory", str(root), "--no-overwrite",
    ], capture_output=True, text=True, env=cli_environment(), timeout=30)
    assert run.returncode == 1
    status = yaml.safe_load((root / "run-status.yaml").read_text())
    assert status["state"] == "failed" and status["products"] == []
    assert not (root / ".frameit-run.lock").exists()


@pytest.mark.skipif(
    not (SLURM_EXAMPLES / "frameit.sbatch").is_file(), reason="Requires checkout examples"
)
def test_slurm_launcher_isolates_retries_and_propagates_failure(tmp_path):
    """Exercise the shell boundary locally; the srun shim is not a scheduler test."""
    inputs = tmp_path / "input with spaces"
    inputs.mkdir()
    dataset(inputs)
    config = inputs / "case.yaml"
    config.write_text(yaml.safe_dump(document(inputs, input={"files": ["native.nc"]})))
    parent = tmp_path / "attempts with spaces"
    parent.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    srun = bin_dir / "srun"
    srun.write_text("""#!/bin/sh
while [ "$#" -gt 0 ]; do
    case "$1" in --nodes=*|--ntasks=*) shift ;; *) break ;; esac
done
exec "$@"
""")
    srun.chmod(0o755)
    activation = tmp_path / "activate.sh"
    activation.write_text(f'export PATH="{Path(sys.executable).parent}:$PATH"\n')
    env = {
        **cli_environment(), "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        "SLURM_NTASKS": "1", "FRAMEIT_ENV_SCRIPT": str(activation),
    }
    launcher = SLURM_EXAMPLES / "frameit.sbatch"
    for _ in range(2):
        run = subprocess.run(
            ["bash", str(launcher), str(config), str(parent)], cwd=tmp_path,
            env=env, capture_output=True, text=True, timeout=45,
        )
        assert run.returncode == 0, run.stdout + run.stderr
    attempts = list(parent.iterdir())
    assert len(attempts) == 2
    for attempt in attempts:
        assert (attempt / "work").is_dir()
        status = yaml.safe_load((attempt / "run" / "run-status.yaml").read_text())
        assert status["state"] == "completed"
        assert status["effective_execution_options"]["overwrite"] is False
        assert status["effective_execution_options"]["require_complete_tracking"] is True

    # An actual CLI input failure must remain nonzero across exec/srun/the wrapper.
    (inputs / "native.nc").unlink()
    failed = subprocess.run(
        ["bash", str(launcher), str(config), str(parent)], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert failed.returncode == 1


def test_incomplete_tracking_is_explicit_and_strict_policy_fails(tmp_path, monkeypatch):
    def shortened(runner, **kwargs):
        runner.track = xr.Dataset(attrs={
            "tracking_complete": False, "tracking_termination_reason": "lost test vortex",
        })
        return SimpleNamespace(ok=True, n_files=0, output_dir=runner.output_dir, files=[])

    monkeypatch.setattr("frameit.core.runner.FrameitRunner.run", shortened)
    for strict in (False, True):
        root = tmp_path / str(strict)
        conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, output={
            "directory": str(root), "export": {"netcdf": False},
        }, execution={"require_complete_tracking": strict}))
        if strict:
            with pytest.raises(ValueError, match="Tracking is incomplete"):
                execute_simulation(conf)
        else:
            assert not execute_simulation(conf).tracking_complete
        status = yaml.safe_load((root / "run-status.yaml").read_text())
        assert status["state"] == ("failed" if strict else "incomplete")
        assert status["tracking_complete"] is False


@pytest.mark.parametrize("kill", [False, True], ids=["sigterm", "sigkill"])
def test_cancellation_and_same_root_exclusion(tmp_path, kill):
    config = tmp_path / "case.yaml"
    root = tmp_path / "out"
    ready = tmp_path / "ready"
    config.write_text(yaml.safe_dump(document(tmp_path)))
    script = """
import signal, sys
from pathlib import Path
from frameit.core.runner import FrameitRunner
from frameit.cli import main
def block(self, **kwargs):
    Path(sys.argv[3]).touch()
    while True:
        signal.pause()
FrameitRunner.run = block
main(['run', sys.argv[1], '--output-directory', sys.argv[2], '--no-overwrite'])
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(config), str(root), str(ready)],
        env=cli_environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 30
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.exists(), "Blocking run did not start"
        competitor = subprocess.run([
            sys.executable, "-m", "frameit", "run", str(config),
            "--output-directory", str(root),
        ], capture_output=True, text=True, env=cli_environment(), timeout=30)
        assert competitor.returncode != 0 and "locked" in competitor.stderr
        process.send_signal(signal.SIGKILL if kill else signal.SIGTERM)
        _, stderr = process.communicate(timeout=15)
        assert process.returncode == (-signal.SIGKILL if kill else 143), stderr
        status = yaml.safe_load((root / "run-status.yaml").read_text())
        assert status["state"] == ("running" if kill else "interrupted")
        assert (root / ".frameit-run.lock").exists() == kill
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=15)
