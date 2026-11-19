"""Owned scalar progress, not scientific task scanning or a status heartbeat."""

from __future__ import annotations

import hashlib
import logging
import multiprocessing
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue

import pytest

from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.testing.numerical.test_v3_run_state import (
    _exercise_parent_retention_boundary,
    gate_second_product,
    ordinary_reader,
    record,
    two_sources,
)
from frameit.utils import logging as logging_utils


def progress_type():
    assert hasattr(logging_utils, "_QuietProgress"), "quiet execution progress is missing"
    return logging_utils._QuietProgress


def observe(monkeypatch, *, interval=.02):
    """Capture real emitted records; shorten only the private test reporter interval."""
    reporters, messages = [], Queue()
    real_type, handle = progress_type(), logging.Logger.handle

    def create(*args, **kwargs):
        reporter = real_type(*args, interval=interval, **kwargs)
        reporters.append(reporter)
        return reporter

    def handling(logger, entry):
        result = handle(logger, entry)
        if entry.name == "frameit" and entry.getMessage().startswith("Progress |"):
            messages.put(entry.getMessage())
        return result

    monkeypatch.setattr(logging_utils, "_QuietProgress", create)
    monkeypatch.setattr(logging.Logger, "handle", handling)
    return reporters, messages


def notice(messages, operation):
    deadline = time.monotonic() + 10
    while True:
        text = messages.get(timeout=max(.001, deadline - time.monotonic()))
        if operation in text:
            return text


def stopped(reporters):
    assert reporters and all(reporter._thread is None for reporter in reporters)
    assert not any(thread.name == "frameit-progress" for thread in threading.enumerate())


def test_clock_bounds_busy_and_quiet_messages_without_resetting_real_activity():
    """Notices must neither count scheduled work nor make quiet work look active."""
    clock, messages = [0.], []
    logger = logging.Logger("local-progress", logging.INFO)

    class Capture(logging.Handler):
        def emit(self, entry):
            messages.append(entry.getMessage())

    logger.addHandler(Capture())
    reporter = progress_type()(logger, clock=lambda: clock[0])
    reporter.update("preparing lazy source views/calculations", source="weather")
    reporter._report()
    for second in range(1, 3601):
        clock[0] = float(second)
        if second <= 30:
            reporter.update("preparing lazy source views/calculations", source="weather")
        reporter._report()
    assert len(messages) == 121
    assert "elapsed=3600.0s" in messages[-1]
    assert "last activity=3570.0s ago" in messages[-1]
    assert "prepared sources=0" in messages[-1] and "published products=0" in messages[-1]
    reporter.update("computing/writing exports", prepared_sources=1)
    reporter.update("computing/writing exports", published_products=1)
    reporter.finish("complete")
    assert len(messages) == 122
    assert "prepared sources=1" in messages[-1] and "published products=1" in messages[-1]
    assert "Run complete" in messages[-1] and "last activity=0.0s ago" in messages[-1]
    assert all("%" not in text and "ETA" not in text for text in messages)
    print("progress deterministic: 3600 ticks +30 boundaries ->122 records including terminals")
    started = time.perf_counter()
    for _ in range(10000):
        reporter.update("preparing lazy source views/calculations", source="weather")
        reporter._report()
    duration = time.perf_counter() - started
    assert len(messages) == 122 and duration < 5
    print(f"10000 same-clock updates/checks: {duration:.4f}s, 0 extra records")


def test_real_quiet_wait_stops_promptly_and_restores_scoped_handlers(tmp_path):
    """The quiet notice must come from the owned thread, not another boundary."""
    kind = progress_type()
    logger = logging.getLogger("frameit")
    saved = logger.handlers[:], logger.level, logger.propagate
    quiet, messages = threading.Event(), []
    with logging_utils.frameit_logging_scope(tmp_path, level="INFO") as path:
        class Capture(logging.Handler):
            def emit(self, entry):
                if entry.getMessage().startswith("Progress |"):
                    messages.append(entry.getMessage())
                    if len(messages) >= 2:
                        quiet.set()

        logger.addHandler(Capture())
        reporter = kind(logger, interval=.02)
        started = time.monotonic()
        reporter.start()
        try:
            assert quiet.wait(5)
        finally:
            reporter.stop()
        duration = time.monotonic() - started
        assert duration < 5
        assert 2 <= len(messages) <= 10
        assert reporter._thread is None
        reporter.stop()
    assert (logger.handlers, logger.level, logger.propagate) == saved
    assert "preparing metadata/selected source plans" in Path(path).read_text()
    print(f"real quiet notice and joined stop: {duration:.4f}s, {len(messages)} records")


def test_logging_transition_keeps_the_existing_quiet_deadline():
    """Adding the owned logfile must not restart a nearly elapsed quiet interval."""
    clock, waits = [0.], []
    logger = logging.Logger("local-progress", logging.INFO)
    logger.addHandler(logging.NullHandler())
    reporter = progress_type()(logger, clock=lambda: clock[0])
    reporter._report()

    class Wait:
        def clear(self):
            pass

        def set(self):
            pass

        def wait(self, timeout):
            waits.append(timeout)
            return True

    reporter._stop = Wait()
    clock[0] = 29.
    reporter.start()
    reporter.stop()
    assert waits == [1.]


@pytest.mark.parametrize("failure", [None, ValueError, KeyboardInterrupt, SystemExit])
def test_quiet_preparation_has_stderr_without_creating_an_attempt(
        tmp_path, monkeypatch, capsys, failure):
    """Slow metadata binding must be visible before any run root or payload exists."""
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.core import coupled

    conf = two_sources(tmp_path, "netcdf", True)
    reporters, messages = observe(monkeypatch)
    ready, release = threading.Event(), threading.Event()
    bind, read = coupled.bind_sources, H5NetCDFArrayWrapper.__getitem__
    reads = []

    def binding(*args, **kwargs):
        ready.set()
        assert release.wait(10)
        if failure:
            raise failure("preparation stopped")
        return bind(*args, **kwargs)

    def reading(array, key):
        if array.variable_name in {"instructional_scalar", "sea_scalar"}:
            reads.append(array.variable_name)
        return read(array, key)

    monkeypatch.setattr(coupled, "bind_sources", binding)
    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", reading)
    with ThreadPoolExecutor(max_workers=1) as pool:
        attempt = pool.submit(execute_simulation, conf)
        try:
            assert ready.wait(10)
            notice(messages, "preparing metadata/selected source plans")
            text = notice(messages, "preparing metadata/selected source plans")
            assert "prepared sources=0" in text and "published products=0" in text
            assert float(re.search(r"last activity=([\d.]+)s", text)[1]) >= 0
            assert not conf.output_dir.exists() and not reads
        finally:
            release.set()
        if failure:
            with pytest.raises(failure, match="preparation stopped"):
                attempt.result(timeout=20)
            assert not conf.output_dir.exists()
        else:
            result = attempt.result(timeout=20)
            assert result.ok and reads
    stopped(reporters)
    captured = capsys.readouterr()
    assert not captured.out and "Progress |" in captured.err
    assert ("Run complete" in captured.err) == (failure is None)


@pytest.mark.parametrize("boundary", ["cleanup", "final_record", "processing_and_cleanup"])
def test_terminal_success_waits_for_cleanup_and_records(tmp_path, monkeypatch, capsys, boundary):
    """Earlier publications are real, but do not establish successful finalization."""
    from frameit.core import run_state
    from frameit.core.runner import FrameitRunner

    conf = two_sources(tmp_path, "netcdf", True)
    reporters, _ = observe(monkeypatch)
    close, write = FrameitRunner.close, run_state.write_yaml_atomic

    def closing(runner):
        close(runner)
        if runner.conf is conf:
            raise OSError("cleanup stopped")

    def writing(path, value, **kwargs):
        if Path(path).name == "run-provenance.yaml" and value["state"] == "completed":
            raise OSError("final record stopped")
        return write(path, value, **kwargs)

    def running(runner, **kwargs):
        raise RuntimeError("primary processing stopped")

    if boundary == "final_record":
        monkeypatch.setattr(run_state, "write_yaml_atomic", writing)
    else:
        monkeypatch.setattr(FrameitRunner, "close", closing)
    if boundary == "processing_and_cleanup":
        monkeypatch.setattr(FrameitRunner, "run", running)
    with pytest.raises(RuntimeError if boundary == "processing_and_cleanup" else OSError,
                       match="primary processing|cleanup stopped|final record stopped"):
        execute_simulation(conf)
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == "failed" and "cleanup" in status["pending"]
    assert len(status["products"]) == (0 if boundary == "processing_and_cleanup" else 2)
    captured = capsys.readouterr()
    assert not captured.out and "Run complete" not in captured.err
    assert "Run complete" not in next((conf.output_dir / "logs").iterdir()).read_text()
    assert "Run failed" in captured.err
    assert not (conf.output_dir / ".frameit-run.lock").exists()
    stopped(reporters)


def test_quiet_lazy_preparation_has_source_but_no_completed_values(
        tmp_path, monkeypatch, capsys):
    """Loading a selected lazy view must not start its field reads to report status."""
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.core.runner import FrameitRunner

    conf = two_sources(tmp_path, "netcdf", True)
    reporters, messages = observe(monkeypatch)
    ready, release = threading.Event(), threading.Event()
    load, read = FrameitRunner.load_dataset, H5NetCDFArrayWrapper.__getitem__
    reads = []

    def loading(runner):
        result = load(runner)
        if runner.conf.source_name == "weather":
            ready.set()
            assert release.wait(10)
        return result

    def reading(array, key):
        if array.variable_name in {"instructional_scalar", "sea_scalar"}:
            reads.append(array.variable_name)
        return read(array, key)

    monkeypatch.setattr(FrameitRunner, "load_dataset", loading)
    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", reading)
    with ThreadPoolExecutor(max_workers=1) as pool:
        attempt = pool.submit(execute_simulation, conf)
        try:
            assert ready.wait(10)
            text = notice(messages, "preparing lazy source views/calculations")
            assert "source=weather" in text
            assert "prepared sources=0" in text and "published products=0" in text
            assert not reads
            before = (conf.output_dir / "run-status.yaml").read_bytes()
            notice(messages, "preparing lazy source views/calculations")
            assert (conf.output_dir / "run-status.yaml").read_bytes() == before
        finally:
            release.set()
        result = attempt.result(timeout=20)
    assert result.ok and sorted(reads) == ["instructional_scalar"] * 2 + ["sea_scalar"] * 2
    stopped(reporters)
    assert not capsys.readouterr().out


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("synchronous", [True, False], ids=["sync", "spawn"])
@pytest.mark.parametrize("outcome", ["completed", "failed", "interrupted"])
def test_lazy_compute_write_counts_only_parent_retained_publications(
        tmp_path, monkeypatch, capsys, fmt, synchronous, outcome):
    """Quiet export is not completion; notices cannot cause another compute or checkpoint."""
    conf = two_sources(tmp_path, fmt, synchronous)
    originals = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (tmp_path / "input.nc", tmp_path / "ocean.nc")}
    reporters, messages = observe(monkeypatch)
    closed, close = [], logging.FileHandler.close

    def closing(handler):
        if Path(handler.baseFilename).is_relative_to(conf.output_dir):
            assert all(reporter._thread is None for reporter in reporters)
            closed.append(handler.baseFilename)
        close(handler)

    monkeypatch.setattr(logging.FileHandler, "close", closing)
    with multiprocessing.get_context("spawn").Manager() as manager:
        ready, release = manager.Event(), manager.Event()
        gate_second_product(monkeypatch, ready, release, outcome)
        with ThreadPoolExecutor(max_workers=1) as pool:
            attempt = pool.submit(execute_simulation, conf)
            try:
                assert ready.wait(20)
                text = notice(messages, "published products=1")
                assert "computing/writing exports" in text
                assert "prepared sources=2" in text
                status = record(conf.output_dir, "run-status.yaml")
                assert status["state"] == "running" and len(status["products"]) == 1
                assert status["pending"] == ["publication", "cleanup"]
                before = {name: (conf.output_dir / name).read_bytes()
                          for name in ("run-status.yaml", "run-provenance.yaml")}
                for _ in range(2):
                    text = notice(messages, "computing/writing exports")
                    assert "published products=1" in text
                    assert "completed tracking operations=0" in text
                assert {name: (conf.output_dir / name).read_bytes() for name in before} == before
                assert len(list((conf.output_dir / "products").glob("records.water.*"))) == 0
            finally:
                release.set()
            if outcome == "completed":
                result = attempt.result(timeout=30)
                assert result.ok
            else:
                with pytest.raises(OSError if outcome == "failed" else KeyboardInterrupt,
                                   match=f"second product {outcome}"):
                    attempt.result(timeout=30)
    stopped(reporters)
    assert len(closed) == 1
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == outcome
    assert len(status["products"]) == (2 if outcome == "completed" else 1)
    assert status["products"] == record(conf.output_dir, "run-provenance.yaml")["products"]
    for product in status["products"]:
        weather = product["source"] == "weather"
        ordinary_reader(conf.output_dir, product,
                        tmp_path / ("input.nc" if weather else "ocean.nc"),
                        "instructional_scalar" if weather else "sea_scalar",
                        "valid_time" if weather else "time_counter", fmt)
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in originals} == originals
    captured = capsys.readouterr()
    assert not captured.out
    terminal = "Run complete" if outcome == "completed" else f"Run {outcome}"
    assert terminal in captured.err
    assert ("Run complete" in captured.err) == (outcome == "completed")
    text = next((conf.output_dir / "logs").iterdir()).read_text()
    assert terminal in text


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_repeated_runs_honor_levels_and_leave_no_reporter(tmp_path, monkeypatch, capsys, level):
    """A repeated call must not retain a reporter or replace the caller's handlers."""
    conf = two_sources(tmp_path, "netcdf", True)
    reporters, _ = observe(monkeypatch)
    logger = logging.getLogger("frameit")
    previous = logger.handlers[:], logger.level, logger.propagate
    for _ in range(2):
        result = execute_simulation(
            conf, ExecutionOptions.from_config(conf, log_level=level, overwrite=True))
        stopped(reporters)
        assert (logger.handlers, logger.level, logger.propagate) == previous
        text = Path(result.log_path).read_text()
        assert ("Progress |" in text) == (level in {"DEBUG", "INFO"})
        assert ("Run complete" in text) == (level in {"DEBUG", "INFO"})
        assert record(conf.output_dir, "run-status.yaml")["state"] == "completed"
    assert len(reporters) == 2
    assert not capsys.readouterr().out


def test_broken_progress_handler_does_not_replace_processing_error(tmp_path, monkeypatch):
    from frameit.core.runner import FrameitRunner

    conf = two_sources(tmp_path, "netcdf", True)
    reporters, _ = observe(monkeypatch)
    handle = logging.Logger.handle

    def handling(logger, entry):
        if entry.getMessage().startswith("Progress |"):
            raise OSError("progress logging stopped")
        return handle(logger, entry)

    def running(runner, **kwargs):
        raise RuntimeError("primary scientific operation stopped")

    monkeypatch.setattr(logging.Logger, "handle", handling)
    monkeypatch.setattr(FrameitRunner, "run", running)
    with pytest.raises(RuntimeError, match="primary scientific operation stopped"):
        execute_simulation(conf)
    stopped(reporters)
    status = record(conf.output_dir, "run-status.yaml")
    assert status["error"]["message"] == "primary scientific operation stopped"
    assert status["state"] == "failed" and status["products"] == []


@pytest.mark.parametrize("phase,operation,published", [
    ("tracking", "tracking/calculating centres", 0),
    ("cleanup", "cleanup", 2),
    ("final_record", "finalizing run records/ownership", 2),
])
def test_quiet_actual_operation_keeps_its_phase_until_the_boundary_returns(
        tmp_path, monkeypatch, phase, operation, published):
    """A blocked tracker, cleanup or final checkpoint is not terminal success."""
    from frameit.core import run_state
    from frameit.core.runner import FrameitRunner
    from frameit.testing.numerical.test_v3_regions import configuration, pressure_wind_scene

    conf = configuration(tmp_path, {"weather": pressure_wind_scene(tmp_path / "input.nc")},
                         region={"tracker": {"method": "pressure_wind"}},
                         products={"model_grid": True, "track": True})
    reporters, messages = observe(monkeypatch)
    ready, release = threading.Event(), threading.Event()
    track, close, write = (
        FrameitRunner.run_tracking, FrameitRunner.close, run_state.write_yaml_atomic)

    def gate():
        ready.set()
        assert release.wait(10)

    def tracking(runner, *args, **kwargs):
        gate()
        return track(runner, *args, **kwargs)

    def closing(runner):
        if runner.conf is conf:
            gate()
        close(runner)

    def writing(path, value, **kwargs):
        if Path(path).name == "run-provenance.yaml" and value["state"] == "completed":
            gate()
        return write(path, value, **kwargs)

    if phase == "tracking":
        monkeypatch.setattr(FrameitRunner, "run_tracking", tracking)
    elif phase == "cleanup":
        monkeypatch.setattr(FrameitRunner, "close", closing)
    else:
        monkeypatch.setattr(run_state, "write_yaml_atomic", writing)
    with ThreadPoolExecutor(max_workers=1) as pool:
        attempt = pool.submit(execute_simulation, conf)
        try:
            assert ready.wait(10)
            text = notice(messages, operation)
            assert f"published products={published}" in text and "prepared sources=1" in text
            if phase == "tracking":
                assert "source=weather" in text and "completed tracking operations=0" in text
            assert "Run complete" not in next((conf.output_dir / "logs").iterdir()).read_text()
            before = (conf.output_dir / "run-status.yaml").read_bytes()
            notice(messages, operation)
            assert (conf.output_dir / "run-status.yaml").read_bytes() == before
        finally:
            release.set()
        assert attempt.result(timeout=20).ok
    stopped(reporters)
    assert record(conf.output_dir, "run-status.yaml")["state"] == "completed"


def test_real_incomplete_track_has_incomplete_terminal_and_actual_inventory(
        tmp_path, monkeypatch, capsys):
    """An accepted tracker prefix is not a complete run or a shortened native clock."""
    from frameit.testing.numerical.test_multifield_vortex import vortex
    from frameit.testing.numerical.test_v3_regions import configuration

    dataset, _ = vortex(n=81)
    dataset["MSLP"][1] = 101000.
    source = tmp_path / "native.nc"
    dataset.to_netcdf(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    conf = configuration(tmp_path, {"weather": {
        "model": "mesonh", "files": "./native.nc", "variables": {"2d": ["MSLP"]},
        "wind_pairs": [{"u": "UT_ZM", "v": "VT_ZM", "basis": "earth"},
                       {"u": "UM10", "v": "VM10", "basis": "earth"}]}},
        region={"tracker": {"method": "multifield_vortex", "on_incomplete": "keep_prefix",
            "mnh_gravity_m_s2": 9.80665,
            "seed": {"latitude": -20, "longitude": 60, "motion_u_m_s": 0, "motion_v_m_s": 0}}},
        products={"model_grid": True, "track": True})
    reporters, _ = observe(monkeypatch)
    result = execute_simulation(conf)
    stopped(reporters)
    status = record(conf.output_dir, "run-status.yaml")
    assert not result.tracking_complete and status["state"] == "incomplete"
    assert status["tracking_termination_reason"] == "required_fix_missing"
    assert len(status["products"]) == 2 and status["pending"] == []
    assert status["products"] == record(conf.output_dir, "run-provenance.yaml")["products"]
    for product in result.products:
        subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source:
    if sys.argv[3] == 'track':
        assert out.sizes['time'] == 1 and out.sizes['attempt_time'] == 2
        np.testing.assert_array_equal(out.time, source.time[:1])
        assert out.latitude.attrs['units'] == 'degrees_north'
        assert out.longitude.attrs['units'] == 'degrees_east'
        assert not out.attrs['tracking_complete']
    else:
        np.testing.assert_array_equal(out.MSLP, source.MSLP)
        np.testing.assert_array_equal(out.time, source.time)
        assert out.MSLP.attrs == source.MSLP.attrs
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], str(source), product["role"]],
            check=True, capture_output=True, text=True)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    captured = capsys.readouterr()
    assert not captured.out and "Run incomplete" in captured.err
    text = Path(result.log_path).read_text()
    terminal = [line for line in text.splitlines()
                if "Progress | " in line and "Run incomplete" in line]
    assert len(terminal) == 1 and "published products=2" in terminal[0]
    assert "[W1501]" in terminal[0]
    assert "prepared sources=1" in terminal[0] and "completed tracking operations=1" in terminal[0]
    assert "Run complete" not in text


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("boundary", [
    "before_retention", "callback_entry", "callback_error", "callback_signal",
])
def test_a1_terminal_count_matches_retained_publications(tmp_path, monkeypatch, fmt, boundary):
    """A missed callback cannot remove a retained product from the terminal count."""
    reporters, messages = observe(monkeypatch)
    _exercise_parent_retention_boundary(tmp_path, monkeypatch, fmt, boundary)
    stopped(reporters)
    root = tmp_path / "out"
    status = record(root, "run-status.yaml")
    state = "failed" if boundary == "callback_error" else "interrupted"
    text = notice(messages, f"Run {state}")
    assert status["state"] == state and len(status["products"]) == 2
    assert int(re.search(r"published products=(\d+)", text)[1]) == len(status["products"])
    assert f"Run {state}" in next((root / "logs").iterdir()).read_text()


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_a1_success_reconciles_without_recounting_callbacks(tmp_path, monkeypatch, fmt):
    conf = two_sources(tmp_path, fmt, False)
    originals = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (tmp_path / "input.nc", tmp_path / "ocean.nc")}
    reporters, messages = observe(monkeypatch)
    result = execute_simulation(conf)
    stopped(reporters)
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == "completed"
    assert len(result.products) == len(status["products"]) == 2
    assert status["products"] == record(conf.output_dir, "run-provenance.yaml")["products"]
    assert len({item["path"] for item in status["products"]}) == 2
    text = notice(messages, "Run complete")
    assert int(re.search(r"published products=(\d+)", text)[1]) == 2
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in originals} == originals


def test_a1_reconcile_is_absolute_without_activity_or_increment_semantics_changes():
    clock, messages = [0.], []
    logger = logging.Logger("local-progress", logging.INFO)

    class Capture(logging.Handler):
        def emit(self, entry):
            messages.append(entry.getMessage())

    logger.addHandler(Capture())
    reporter = progress_type()(logger, clock=lambda: clock[0])
    reporter.update("computing/writing exports", source="weather",
                    prepared_sources=1, tracking_operations=1, published_products=1)
    clock[0] = 10.
    assert hasattr(reporter, "reconcile_published"), (
        "absolute retained-count reconciliation missing")
    reporter.reconcile_published(2)
    reporter.reconcile_published(2)
    assert not messages
    reporter._report()
    assert "published products=2" in messages[-1] and "last activity=10.0s ago" in messages[-1]
    assert "computing/writing exports" in messages[-1] and "source=weather" in messages[-1]
    assert ("prepared sources=1" in messages[-1]
            and "completed tracking operations=1" in messages[-1])
    reporter.update("computing/writing exports", published_products=1)
    reporter._report(force=True)
    assert "published products=3" in messages[-1]
