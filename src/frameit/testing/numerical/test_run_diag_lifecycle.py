"""Exercise parent and child ownership with real extraction records."""

from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

from frameit.core.configuration import to_runtime
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.reports import project_report
from frameit.core.settings_class import SimulationConfig
from frameit.testing.documentation_example import create_first_run_input
from frameit.testing.numerical.test_run_diag_configuration import request
from frameit.testing.numerical.test_v3_run_state import fixed_document, record


def run_diag(*args, **kwargs):
    import importlib.util

    assert importlib.util.find_spec("frameit.diagnostics.runner") is not None
    from frameit.diagnostics.runner import run_diagnostics

    return project_report(run_diagnostics(*args, **kwargs))


def write_request(path, raw):
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


@pytest.fixture
def completed(tmp_path):
    create_first_run_input(tmp_path / "input.nc")
    raw = fixed_document()
    conf = SimulationConfig(**to_runtime(raw, base_dir=tmp_path))
    execute_simulation(conf, ExecutionOptions.from_config(conf, export_netcdf=False))
    raw["diagnostics"] = request()["diagnostics"]
    path = write_request(tmp_path / "config.yaml", raw)
    return conf.output_dir, path, raw


@pytest.fixture
def lifecycle_doubles(monkeypatch):
    from types import SimpleNamespace

    from frameit.diagnostics import runner

    def plan(parent, request, *, scratch):
        from frameit.core.runtime import current_execution_resources

        assert current_execution_resources()["dask_scheduler"] == "synchronous"
        assert current_execution_resources()["native_threads"] == 1
        assert (parent.root / ".frameit-run.lock").exists()
        (scratch / "decoder-index").touch()
        return SimpleNamespace(facts={"test": "planned"})

    def execute(attempt, plan, *, scratch):
        file = attempt / "test-result.nc"
        file.write_bytes(b"test result")
        return ([{"path": file.name}], {"rows": 1}, [])

    monkeypatch.setattr(runner, "_plan_source", plan)
    monkeypatch.setattr(runner, "_execute_plan", execute)
    return runner


def snapshot(root):
    return {
        p.relative_to(root): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and "diagnostics" not in p.relative_to(root).parts
    }


def test_noop_without_a_parent(tmp_path):
    raw = fixed_document()
    for diagnostics in [None, {}]:
        if diagnostics is not None:
            raw["diagnostics"] = diagnostics
        path = write_request(tmp_path / "cfg.yaml", raw)
        report = run_diag(path, check=True)
        assert report["status"] == "ok"
        assert report["data"]["plan"]["message"] == "No diagnostics requested"
        assert not (tmp_path / "out").exists()


def test_noop_and_check_leave_parent_unchanged(completed, lifecycle_doubles):
    root, path, _ = completed
    before = snapshot(root)
    report = run_diag(path, check=True)
    assert report["status"] == "ok" and report["report_version"] == 1
    assert report["data"]["plan"]["test"] == "planned"
    assert not (root / "diagnostics").exists()
    assert snapshot(root) == before


@pytest.mark.parametrize("state", ["running", "failed", "interrupted", "incomplete", "pending"])
def test_parent_gate(completed, state):
    root, path, _ = completed
    file = root / "run-status.yaml"
    status = record(root, file.name)
    if state == "pending":
        status["pending"] = ["cleanup"]
    else:
        status.update(state=state, tracking_termination_reason="test termination")
    write_request(file, status)
    report = run_diag(path, check=True)
    assert report["status"] == "error"
    assert report["errors"][0]["code"] == "E2002"
    assert not (root / "diagnostics").exists()
    if state != "pending":
        assert "test termination" in report["errors"][0]["message"]


def test_locked_parent_and_diagnostic_lease_exclude_overwrite(
    completed, lifecycle_doubles, monkeypatch
):
    root, path, _ = completed
    lock = root / ".frameit-run.lock"
    lock.write_text("other owner")
    report = run_diag(path, check=True)
    assert report["errors"][0]["code"] == "E1801"
    assert lock.read_text() == "other owner"
    lock.unlink()

    expected = lifecycle_doubles._plan_source

    def competing(parent, request, *, scratch):
        conf = SimulationConfig(**to_runtime(fixed_document(), base_dir=path.parent))
        with pytest.raises(FileExistsError, match="locked"):
            execute_simulation(conf, ExecutionOptions.from_config(conf, overwrite=True))
        return expected(parent, request, scratch=scratch)

    monkeypatch.setattr(lifecycle_doubles, "_plan_source", competing)
    assert run_diag(path, check=True)["status"] == "ok"


def test_relocated_parent_matches_the_authored_request(completed, lifecycle_doubles):
    root, path, raw = completed
    destination = root.rename(root.with_name("moved"))
    before = snapshot(destination)
    assert run_diag(path, run_directory=destination, check=True)["status"] == "ok"
    raw["region"]["width_km"]["x"] += 1
    write_request(path, raw)
    report = run_diag(path, run_directory=destination, check=True)
    (issue,) = report["errors"]
    assert issue["code"] == "E2002"
    assert "region.width_km.x" in str(issue)
    assert snapshot(destination) == before


@pytest.mark.parametrize("stage", ["runtime_cleanup", "lock_release"])
def test_cleanup_before_and_release_after_commit(completed, lifecycle_doubles, monkeypatch, stage):
    from frameit.core.runtime import execution_scope

    root, path, _ = completed
    before = snapshot(root)
    if stage == "runtime_cleanup":

        @contextmanager
        def fail(options):
            with execution_scope(options):
                yield
            raise OSError("scope restoration failed")

        monkeypatch.setattr(lifecycle_doubles, "_serial_scope", fail)
    else:
        actual = Path.unlink

        def unlink(path, *args, **kwargs):
            if path.name == ".frameit-diagnostics.lock":
                raise OSError("child lock release failed")
            actual(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", unlink)
    report = run_diag(path)
    assert report["status"] == "error"
    (attempt,) = (root / "diagnostics").iterdir()
    status = record(attempt, "diagnostics-status.yaml")
    expected = "failed" if stage == "runtime_cleanup" else "completed"
    assert status["state"] == expected
    assert bool(status["products"]) == (expected == "completed")
    assert bool(report["data"]["plan"].get("committed")) == (expected == "completed")
    assert snapshot(root) == before
