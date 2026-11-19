"""Batch lifecycle and real spawned-export regressions on compact synthetic data."""

from __future__ import annotations

import json
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

from .test_configuration_v2_1 import dataset, document

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


@pytest.mark.parametrize("path,value", [
    (("resources", "native_threads"), 0), (("resources", "compute_workers"), True),
    (("resources", "scheduler"), "processes"),
    (("region", "tracker", "on_incomplete"), "false"),
    (("resources", "synchronous_export"), "false"),
])
def test_invalid_execution_schema(tmp_path, path, value):
    raw = document(tmp_path)
    if path[:2] == ("region", "tracker"):
        raw["region"] = {"tracker": {"method": "pressure_wind"}}
    target = raw
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value
    with pytest.raises(ValueError, match=".".join(path)):
        resolve_schema(raw)


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
        with pytest.raises(FileExistsError, match="locked") as exc:
            with owned_run(root, overwrite=True, initial={}):
                pytest.fail("A second owner entered the directory")
        assert exc.value.frameit_code == "E1801"
        status["state"] = "completed"
    original = (root / "run-status.yaml").read_bytes()
    dataset(tmp_path)
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, output={
        "directory": str(root), "overwrite": False,
    }))
    monkeypatch.setattr("frameit.core.execution._execute_simulation", lambda *a, **k: pytest.fail(
        "No-clobber must fail before processing"
    ))
    with pytest.raises(FileExistsError, match="Existing run artifacts") as exc:
        execute_simulation(conf)
    assert exc.value.frameit_code == "E1802"
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


@pytest.mark.parametrize("mode", ["spawn", "sync", "empty", "failure"])
def test_group_phases_share_one_bounded_pool_and_close_it(tmp_path, monkeypatch, mode):
    from frameit.io import netcdf_export

    original = netcdf_export.ProcessPoolExecutor
    pools = []

    def create_pool(**kwargs):
        pool = original(**kwargs)
        pools.append((pool, kwargs))
        return pool

    monkeypatch.setattr(netcdf_export, "ProcessPoolExecutor", create_pool)
    monkeypatch.setattr("frameit.core.runtime.cpu_budget", lambda: (2, "test allocation"))
    ds = xr.Dataset({"q": (("time", "y", "x"), [[[1., np.nan], [3., 4.]]], {"units": "K"})},
                    coords={"time": [0]}).chunk({"time": 1})
    runner = SimpleNamespace(
        conf=SimpleNamespace(simulation_name="TEST"), output_dir=tmp_path,
        track=xr.Dataset({"cy": ("time", [0])}, coords={"time": [0]}),
        dict_polar_user={"one": ds, "two": ds}, dict_crop_user={"surface": ds},
    )
    if mode == "empty":
        runner.dict_polar_user = runner.dict_crop_user = {}
    if mode == "failure":
        products = tmp_path / "products"
        products.mkdir()
        (products / "TEST.cart.surface.nc").write_bytes(b"previous complete product")
        with pytest.raises(FileExistsError):
            netcdf_export.export_outputs(runner, institution="test", overwrite=False, max_workers=9)
        assert (products / "TEST.cart.surface.nc").read_bytes() == b"previous complete product"
        assert not list(products.glob("*.partial"))
    else:
        result = netcdf_export.export_outputs(
            runner, institution="test", synchronous=mode == "sync", max_workers=9)
        assert set(result) == ({"track"} if mode == "empty" else {"track", "polar", "cart"})
        for role in ("polar", "cart") if mode != "empty" else ():
            for path in result[role]:
                with xr.open_dataset(path) as saved:
                    xr.testing.assert_identical(saved.q, ds.q)
                    assert saved.attrs["track_filename"] == "TEST.track.nc"
    assert len(pools) == (0 if mode in {"sync", "empty"} else 1)
    for pool, options in pools:
        assert options["max_workers"] == 2
        assert options["mp_context"].get_start_method() == "spawn"
        assert options["initargs"] == ("threads", 1, 1)
        assert pool._shutdown_thread and pool._processes is None


def cli_environment():
    return {
        **os.environ, "SLURM_CPUS_PER_TASK": "1", "SLURM_JOB_ID": "local-qualification",
        "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        "PYTHONNOUSERSITE": "1",
    }


@pytest.mark.parametrize("layout", ["editable", "installed"])
@pytest.mark.parametrize("custom_user_base", [False, True], ids=["default-site", "custom-site"])
def test_cli_keeps_checkout_under_local_in_parent_and_spawn(tmp_path, layout, custom_user_base):
    home = tmp_path / "home"
    selected = home / ".local" / "share" / "checkout" / "src"
    if layout == "installed":
        selected = home / ".local" / "share" / "environment" / "lib" / (
            f"python{sys.version_info.major}.{sys.version_info.minor}"
        ) / "site-packages"
    competitor = tmp_path / "competing-install"
    source = Path(__file__).parents[2]
    for root in (selected, competitor):
        package = root / "frameit"
        package.mkdir(parents=True)
        (package / "utils").mkdir()
        (package / "utils/__init__.py").write_text("")
        for name in ("__init__.py", "_version.py", "cli.py", "utils/diagnostics.py"):
            (package / name).write_bytes((source / name).read_bytes())

    import_directory = selected
    if layout == "editable":
        import_directory = tmp_path / "environment" / "site-packages"
        import_directory.mkdir(parents=True)
        (import_directory / "frameit.pth").write_text(f"{selected}\n")

    script = tmp_path / "probe.py"
    script.write_text("""
import importlib.util
import json
import multiprocessing
import site
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

if __name__ == "__main__":
    user_site = Path(site.getusersitepackages())
    nested = user_site / "injected"
    nested.mkdir(parents=True)
    (nested / "frameit_unwanted_user_site.py").write_text("unwanted = True\\n")
    sibling = user_site.with_name("site-packages-other")
    sibling.mkdir()
    inherited_path = sys.path[:]
    sys.path[:] = []
    site.addsitedir(sys.argv[1])
    sys.path.extend([sys.argv[2], str(user_site), str(nested), str(sibling), *inherited_path])
    assert importlib.util.find_spec("frameit_unwanted_user_site") is not None
    import frameit
    from frameit import cli
    with ProcessPoolExecutor(max_workers=1,
                             mp_context=multiprocessing.get_context("spawn")) as pool:
        worker = pool.submit(cli._probe_module, "frameit").result(timeout=15)
    print(json.dumps({
        "parent": frameit.__file__, "worker": worker["path"], "sys_path": sys.path,
        "user_site": str(user_site), "nested": str(nested), "sibling": str(sibling),
        "unwanted_importable": importlib.util.find_spec("frameit_unwanted_user_site") is not None,
    }))
""")
    env = {**cli_environment(), "HOME": str(home)}
    env.pop("PYTHONUSERBASE", None)
    if custom_user_base:
        env["PYTHONUSERBASE"] = str(tmp_path / "custom-user-base")
    run = subprocess.run(
        [sys.executable, str(script), str(import_directory), str(competitor)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)
    expected = str(selected / "frameit" / "__init__.py")
    assert result["parent"] == expected
    assert result["worker"] == expected
    assert str(selected) in result["sys_path"]
    assert result["user_site"] not in result["sys_path"]
    assert result["nested"] not in result["sys_path"]
    assert result["sibling"] in result["sys_path"]
    assert not result["unwanted_importable"]


def test_cli_info_reports_selected_installation():
    from importlib.metadata import PackageNotFoundError, version

    import frameit

    try:
        selected_version = version("frameit")
    except PackageNotFoundError:
        selected_version = frameit.__version__
    for short in (False, True):
        run = subprocess.run(
            [sys.executable, "-m", "frameit", "info", *(["--short"] if short else [])],
            env=cli_environment(), capture_output=True, text=True, timeout=30,
        )
        assert run.returncode == 0, run.stdout + run.stderr
        if short:
            assert run.stdout == f"FrameIt {selected_version}\n"
        else:
            assert f"FrameIt location: {frameit.__file__}" in run.stdout.splitlines()
            assert "Overall: OK" in run.stdout.splitlines()


@pytest.fixture(scope="module")
def cli_attempts(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("hpc-concurrent")
    dataset(tmp_path)
    config = tmp_path / "case.yaml"
    raw = document(tmp_path)
    raw["region"]["width_km"] = {"x": 20, "y": 20}
    raw["sources"]["atmosphere"]["derived"] = {
        "wind_speed": {"method": "wind_speed", "inputs": {"u": "UM10", "v": "VM10"}}}
    raw["sources"]["atmosphere"]["reader"] = {"engine": "netcdf4"}
    config.write_text(yaml.safe_dump(raw))

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
        assert replay.yaml_config["resources"]["synchronous_export"] == (mode == "sync")
        cart = next(p for p in status["products"] if p["role"] == "model_grid")
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


def test_batch_overrides_validation_does_not_claim_output(tmp_path):
    dataset(tmp_path)
    config = tmp_path / "case.yaml"
    raw = document(tmp_path, resources={"synchronous_export": True})
    config.write_text(yaml.safe_dump(raw))
    destination = tmp_path / "planned-only"
    run = subprocess.run([
        sys.executable, "-m", "frameit", "validate", str(config), "--json",
        "--output-directory", str(destination), "--no-overwrite",
    ], capture_output=True, text=True, env=cli_environment(), timeout=30)
    assert run.returncode == 0, run.stderr
    plan = yaml.safe_load(run.stdout)["data"]
    assert plan["configuration"]["output"]["directory"] == str(destination)
    assert plan["configuration"]["resources"]["synchronous_export"] is True
    assert plan["configuration"]["output"]["overwrite"] is False
    assert plan["plan"]["execution_resources"]["export_start_method"] is None
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
    assert not root.exists()
    dataset(tmp_path)
    script = """
import sys
from frameit.core.runner import FrameitRunner
from frameit.cli import main
def fail(self, **kwargs):
    raise OSError("simulated processing failure")
FrameitRunner.run = fail
main(['run', sys.argv[1], '--output-directory', sys.argv[2], '--no-overwrite'])
"""
    run = subprocess.run(
        [sys.executable, "-c", script, str(config), str(root)],
        capture_output=True, text=True, env=cli_environment(), timeout=30)
    assert run.returncode == 1 and "simulated processing failure" in run.stderr
    status = yaml.safe_load((root / "run-status.yaml").read_text())
    assert status["state"] == "failed" and status["products"] == []
    assert not (root / ".frameit-run.lock").exists()


def test_incomplete_tracking_is_explicit_and_strict_policy_fails(tmp_path, monkeypatch, capsys):
    from frameit.core.runner import FrameitRunner

    dataset(tmp_path)
    original = FrameitRunner.run

    def shortened(runner, **kwargs):
        result = original(runner, **kwargs)
        runner.track.attrs.update(
            tracking_complete=False, tracking_termination_reason="lost test vortex")
        return result

    monkeypatch.setattr("frameit.core.runner.FrameitRunner.run", shortened)
    for strict in (False, True):
        root = tmp_path / str(strict)
        conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, output={
            "directory": str(root)}))
        options = ExecutionOptions.from_config(
            conf, export_netcdf=False, require_complete_tracking=strict)
        if strict:
            with pytest.raises(ValueError, match="Tracking is incomplete"):
                execute_simulation(conf, options)
        else:
            assert not execute_simulation(conf, options).tracking_complete
        status = yaml.safe_load((root / "run-status.yaml").read_text())
        assert status["state"] == ("failed" if strict else "incomplete")
        assert status["tracking_complete"] is False
        if strict:
            assert status["error"]["code"] == "E1504"
        else:
            assert "[W1501]" in capsys.readouterr().err


@pytest.mark.parametrize("kill", [False, True], ids=["sigterm", "sigkill"])
def test_cancellation_and_same_root_exclusion(tmp_path, kill):
    dataset(tmp_path)
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
        if kill:
            assert "error" not in status
        else:
            assert status["error"]["code"] == "E0002"
        assert (root / ".frameit-run.lock").exists() == kill
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=15)
