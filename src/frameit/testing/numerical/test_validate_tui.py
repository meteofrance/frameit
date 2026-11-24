"""Exercise the experimental terminal UI on instructional configurations."""

import asyncio
import os
import pty
import select
import subprocess
import sys
import termios
from functools import partial
from threading import Event

import pytest
import yaml

from frameit.cli import _collect_report
from frameit.core.configuration import write_template
from frameit.testing.documentation_example import create_first_run_input

pytest.importorskip("textual")


def _case(root):
    create_first_run_input(root / "data/first-run.nc")
    return write_template("arome-fixed-scalar", root / "config.yaml")


def _text(app, selector):
    return str(app.query_one(selector).content)


@pytest.mark.parametrize("mode", ["full", "schema", "incomplete", "unconfirmed", "unused-centre"])
def test_validation_tabs_show_only_supported_conclusions(tmp_path, mode):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    raw = yaml.safe_load(path.read_text())
    if mode == "incomplete":
        del raw["sources"]["atmosphere"]["variables"]
    if mode == "unconfirmed":
        raw["sources"]["atmosphere"]["transforms"] = [
            {"fields": ["instructional_scalar"], "units": "K"}
        ]
    if mode == "unused-centre":
        del raw["region"]["width_km"]
    path.write_text(yaml.safe_dump(raw))
    original = path.read_bytes()
    overrides = {"cpus": 1, "overwrite": False}
    schema_only = mode == "schema"
    collect = partial(
        _collect_report, path, command="validate", schema_only=schema_only, overrides=overrides)

    async def exercise():
        app = ValidationApp(path, collect, schema_only=schema_only, overrides=overrides)
        async with app.run_test(size=(52, 16)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.query_one("#report-tabs").active == "overview"
            summary = _text(app, "#summary")
            if mode in {"full", "unused-centre"}:
                assert "instructional_scalar" in summary and "2 selected times" in summary
                assert "Planned outputs" in summary and ".model_grid.nc" in summary
                assert "frameit run " in summary and "--cpus=1" in summary
                assert "--no-overwrite" in summary
                assert "does not assess scientific validity" in summary
                if mode == "unused-centre":
                    assert "Full domain; configured centre unused" in summary
            elif mode == "schema":
                assert "input-aware validation" in summary and "frameit run " not in summary
                assert "Planned outputs: unavailable" in summary
            else:
                assert "First repair" in summary and "frameit run " not in summary
                if mode == "unconfirmed":
                    assert "Unconfirmed output paths" in summary and ".model_grid.nc" in summary
                else:
                    assert "E1301" in summary

            overview = app.query_one("#overview-scroll")
            assert overview.max_scroll_y > 0
            overview.scroll_end(animate=False)
            await pilot.press("2")
            assert app.query_one("#report-tabs").active == "findings"
            if mode == "incomplete":
                assert "[E1301]" in _text(app, "#finding")
                await pilot.press("down")
                detail = _text(app, "#finding")
                assert "Blocked" in detail and "Prerequisites" in detail
            await pilot.press("3")
            assert app.query_one("#report-tabs").active == "details"
            assert "Effective configuration" in _text(app, "#report-details")
            assert "Setting origins" in _text(app, "#report-details")
            details_text = _text(app, "#report-details")
            if mode in {"incomplete", "unconfirmed"}:
                assert "Partial preflight facts" in details_text
                if mode == "unconfirmed":
                    assert "unconfirmed" in details_text and ".model_grid.nc" in details_text
            else:
                assert "Processing plan" in details_text
            details = app.query_one("#details-scroll")
            assert details.max_scroll_y > 0 and details.scroll_y == 0
            await pilot.press("end")
            await pilot.pause(0.3)
            assert details.scroll_y > 0
            await pilot.press("1")
            assert overview.scroll_y > 0
            await pilot.press("q")
        assert app.return_value == (1 if mode in {"incomplete", "unconfirmed"} else 0)

    asyncio.run(exercise())
    assert path.read_bytes() == original and not (tmp_path / "output").exists()


def test_live_scan_and_reload(tmp_path, monkeypatch):
    from frameit import validate_tui

    path = _case(tmp_path)
    clock = [100.0]
    monkeypatch.setattr(validate_tui, "monotonic", lambda: clock[0])
    collect = partial(_collect_report, path, command="validate", overrides={"cpus": 1})
    stages = [
        ("metadata", "atmosphere", 0, 6),
        ("metadata", "atmosphere", 2, 6),
        ("metadata", "ocean", 0, 1),
        ("plan", None, None, None),
        ("configuration", None, None, None),
    ]
    ready, resume = [Event() for _ in stages], [Event() for _ in stages]
    calls = 0

    def gated(*, progress):
        nonlocal calls
        calls += 1
        for index in (range(4) if calls == 1 else (4,)):
            progress(*stages[index])
            ready[index].set()
            assert resume[index].wait(10), "test did not release the validation worker"
        return collect(progress=progress)

    async def exercise():
        app = validate_tui.ValidationApp(path, gated)
        async with app.run_test() as pilot:
            try:
                for index, expected in enumerate(("0 of 6", "2 of 6", "0 of 1", "planned outputs")):
                    assert await asyncio.to_thread(ready[index].wait, 5)
                    await pilot.pause()
                    status = _text(app, "#status")
                    assert expected in status
                    assert ("ETA ~00:08" in status) if index == 1 else ("ETA" not in status)
                    if index == 1:
                        clock[0] += 120
                        async with asyncio.timeout(3):
                            while "ETA" in _text(app, "#status"):
                                await pilot.pause(0.05)
                        assert "2 of 6 files checked" in _text(app, "#status")
                    clock[0] += 4
                    resume[index].set()

                await app.workers.wait_for_complete()
                await pilot.pause()
                assert "passed" in _text(app, "#status")

                path.write_text("schema_version: 3\nsources: [\n")
                await pilot.press("r")
                assert await asyncio.to_thread(ready[4].wait, 5)
                await pilot.press("r")
                assert calls == 2
                assert "passed" not in _text(app, "#status")
                assert not app.query_one("#report-tabs").display
                resume[4].set()
                await app.workers.wait_for_complete()
                await pilot.press("2")
                assert "[E1102]" in _text(app, "#finding")
                assert f"{path}:" in _text(app, "#finding")
                await pilot.press("q")
            finally:
                for release in resume:
                    release.set()
        assert app.return_value == 1

    asyncio.run(exercise())


def test_interruption_does_not_return_a_pass(tmp_path):
    from frameit.validate_tui import ValidationApp

    release, started = Event(), Event()
    path = _case(tmp_path)

    def collect(*, progress):
        started.set()
        assert release.wait(10)
        progress("metadata", "atmosphere", 0, 1)
        return _collect_report(path, command="validate", schema_only=True)

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test() as pilot:
            try:
                assert await asyncio.to_thread(started.wait, 5)
                await pilot.press("ctrl+c")
            finally:
                release.set()
        assert app.return_value == 130

    asyncio.run(exercise())


def test_decoder_warning_is_visible_without_changing_report(tmp_path):
    import h5netcdf

    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    with h5netcdf.File(tmp_path / "data/first-run.nc", "r+") as fixture:
        fixture.variables["instructional_scalar"].attrs.update(
            _FillValue=-999.0, missing_value=-888.0)
    collect = partial(_collect_report, path, command="validate", overrides={"cpus": 1})

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "warning" in _text(app, "#status")
            await pilot.press("2")
            assert "multiple fill values" in _text(app, "#finding")
            await pilot.press("q")
        assert app.return_value == 0

    assert collect().facts["warnings"] == []
    asyncio.run(exercise())


def test_findings_distinguish_discovery_notes_from_run_only_work(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)

    def collect(*, progress):
        result = _collect_report(path, command="validate", overrides={"cpus": 1}, progress=progress)
        result.deferred_checks.insert(0, {
            "path": "sources.atmosphere",
            "status": "unfinished-selection",
            "message": "t: native vertical group is ambiguous without an explicit selector.",
        })
        return result

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert _text(app, "#status") == "Input-aware checks passed · 1 field discovery note"
            await pilot.press("2")
            assert "Field discovery · sources.atmosphere" in _text(app, "#finding")
            assert "native vertical group is ambiguous" in _text(app, "#finding")
            await pilot.press("down")
            detail = _text(app, "#finding")
            assert "During run" in detail and "value/mask checks" in detail
            await pilot.press("q")
        assert app.return_value == 0

    asyncio.run(exercise())


@pytest.mark.skipif(sys.platform != "linux", reason="tests the Linux driver's PTY restoration")
def test_sigterm_restores_tty_during_validation(tmp_path):
    path = _case(tmp_path)
    master, terminal = pty.openpty()
    ready_read, ready_write = os.pipe()
    resume_read, resume_write = os.pipe()
    original = termios.tcgetattr(terminal)
    script = """
import os, sys
from frameit import cli
load = cli._load_config
def gated(*args, **kwargs):
    os.write(int(sys.argv[2]), b'1')
    os.read(int(sys.argv[3]), 1)
    return load(*args, **kwargs)
cli._load_config = gated
cli.main(['validate', sys.argv[1], '--cpus', '1'])
"""
    try:
        with subprocess.Popen(
            [sys.executable, "-c", script, str(path), str(ready_write), str(resume_read)],
            stdin=terminal, stdout=terminal, stderr=terminal,
            pass_fds=(ready_write, resume_read), env={**os.environ, "TERM": "xterm-256color"},
        ) as process:
            try:
                assert select.select([ready_read], [], [], 15)[0]
                assert os.read(ready_read, 1) == b"1"
                assert not termios.tcgetattr(terminal)[3] & (termios.ICANON | termios.ECHO)
                process.terminate()
                os.write(resume_write, b"1")
                assert process.wait(timeout=10) == 143
                assert termios.tcgetattr(terminal) == original
                chunks = []
                while select.select([master], [], [], 0)[0]:
                    chunks.append(os.read(master, 65536))
                assert b"\x1b[?1049l" in b"".join(chunks)
            finally:
                if process.poll() is None:
                    process.kill()
    finally:
        for fd in (master, terminal, ready_read, ready_write, resume_read, resume_write):
            os.close(fd)
