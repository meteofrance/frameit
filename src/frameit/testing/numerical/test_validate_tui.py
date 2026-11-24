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


@pytest.mark.parametrize("mode", [
    "full", "schema", "incomplete", "unconfirmed", "malformed", "unused-centre",
])
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
    text = "schema_version: 3\nsources: [\n" if mode == "malformed" else yaml.safe_dump(raw)
    path.write_text(text)
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
            assert all(label in summary for label in ("Inputs", "Selection", "Region", "Outputs"))
            if mode in {"full", "unused-centre"}:
                assert "1 input file" in summary and "2 selected times" in summary
                assert "1 model-grid output field" in summary and "1 planned" in summary
                assert "instructional_scalar" not in summary and ".model_grid.nc" not in summary
                assert "frameit run " in summary and "--cpus=1" in summary
                assert "--no-overwrite" in summary
                assert "does not assess scientific validity" in summary
                if mode == "unused-centre":
                    assert "Full domain; configured centre unused" in summary
                else:
                    assert "Fixed centre" in summary and "km requested" in summary
            elif mode == "schema":
                assert "input-aware validation" in summary and "frameit run " not in summary
                assert "not checked" in summary and ".model_grid.nc" not in summary
            else:
                assert "First repair" in summary and "frameit run " not in summary
                assert summary.index("First repair") < summary.index("Inputs")
                if mode == "unconfirmed":
                    assert "Unconfirmed output paths" in summary and ".model_grid.nc" not in summary
                elif mode == "malformed":
                    assert "E1102" in summary
                else:
                    assert "E1301" in summary

            overview = app.query_one("#overview-scroll")
            overview.scroll_end(animate=False)
            await pilot.pause()
            overview_y = overview.scroll_y
            await pilot.press("2")
            assert app.query_one("#report-tabs").active == "findings"
            if mode == "incomplete":
                assert "[E1301]" in _text(app, "#finding")
                await pilot.press("down")
                detail = _text(app, "#finding")
                assert "Blocked" in detail and "Prerequisites" in detail
            await pilot.press("3")
            assert app.query_one("#report-tabs").active == "details"
            configuration, origins, plan = (
                app.query_one(f"#detail-{key}") for key in ("configuration", "origins", "plan")
            )
            assert configuration.title == "Effective configuration"
            assert origins.title == "Setting origins"
            assert all(section.collapsed for section in (configuration, origins, plan))
            plan_text = _text(app, "#detail-plan-text")
            if mode in {"incomplete", "unconfirmed", "malformed"}:
                assert "Partial preflight facts" in plan.title
                if mode == "unconfirmed":
                    assert "unconfirmed" in plan.title and ".model_grid.nc" in plan_text
                else:
                    assert "unconfirmed" not in plan.title
            else:
                assert plan.title == "Processing plan"
                if mode in {"full", "unused-centre"}:
                    assert "instructional_scalar" in plan_text and ".model_grid.nc" in plan_text

            details = app.query_one("#details-scroll")
            await pilot.press("tab", "enter")
            assert not configuration.collapsed and origins.collapsed and plan.collapsed
            config_text = _text(app, "#detail-configuration-text")
            if mode == "malformed":
                assert config_text == "Unavailable"
            else:
                assert "\n  atmosphere:\n" in config_text
                assert details.max_scroll_y > 0
                await pilot.press("end")
                await pilot.wait_for_scheduled_animations()
                assert details.scroll_y > 0
            await pilot.press("1")
            assert overview.scroll_y == overview_y
            await pilot.press("q")
        assert app.return_value == int(mode in {"incomplete", "unconfirmed", "malformed"})

    asyncio.run(exercise())
    assert path.read_bytes() == original and not (tmp_path / "output").exists()


def test_console_keeps_source_calendars_separate(tmp_path):
    from frameit.validate_tui import _overview

    report = {"status": "ok", "errors": [], "data": {
        "configuration": {"sources": {"air": {"model": "arome"}, "sea": {"model": "nemo"}},
                          "region": {}},
        "inputs": [{"source": "air", "path": "air.nc"}, {"source": "sea", "path": "sea.nc"}],
        "plan": {"sources": {
            "air": {"selected_times": [{"label": day, "calendar": "360_day"}
                                       for day in ("2001-02-01", "2001-02-30")]},
            "sea": {"selected_times": [{"label": day, "calendar": "noleap"}
                                       for day in ("2001-03-01", "2001-03-15", "2001-03-30")]},
        }},
    }}

    lines = _overview(report, tmp_path / "case.yaml", False, {}, has_warnings=False).splitlines()
    air, sea = (next(line for line in lines if name in line and "selected times" in line)
                for name in ("air", "sea"))
    assert "2 selected times" in air and "2001-02-30 (360_day)" in air and "noleap" not in air
    assert "3 selected times" in sea and "2001-03-30 (noleap)" in sea and "360_day" not in sea


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
        async with app.run_test(size=(52, 16)) as pilot:
            try:
                for index, expected in enumerate(("0 of 6", "2 of 6", "0 of 1", "planned outputs")):
                    assert await asyncio.to_thread(ready[index].wait, 5)
                    await pilot.pause()
                    assert not app.query_one("Footer").display
                    assert "Ctrl+C" in _text(app, "#interrupt-hint")
                    assert app.query_one("#interrupt-hint").display
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
                assert app.query_one("Footer").display
                assert not app.query_one("#interrupt-hint").display
                keys = app.query("FooterKey")
                assert {key.key for key in keys} == {"1", "2", "3", "r", "q"}
                assert all(0 < key.region.right <= app.size.width for key in keys)

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


@pytest.mark.parametrize("while_busy", [True, False])
def test_interruption_returns_130(tmp_path, while_busy):
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
                if not while_busy:
                    release.set()
                    await app.workers.wait_for_complete()
                    await pilot.pause()
                    assert app.result_code == 0
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
        note = {
            "path": "sources.atmosphere",
            "status": "unfinished-selection",
            "message": "t: native vertical group is ambiguous without an explicit selector.",
        }
        result.deferred_checks[0:0] = [note, note.copy()]
        return result

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert _text(app, "#status") == "Input-aware checks passed · 2 field discovery notes"
            await pilot.press("2")
            listing = app.query_one("#finding-list")
            first, second = (str(listing.get_option_at_index(i).prompt) for i in range(2))
            assert first != second and all(" · t" in title for title in (first, second))
            assert "Field discovery · sources.atmosphere" in _text(app, "#finding")
            assert "native vertical group is ambiguous" in _text(app, "#finding")
            await pilot.press("down", "down")
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
