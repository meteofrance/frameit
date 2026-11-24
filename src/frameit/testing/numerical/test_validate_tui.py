"""Exercise the experimental terminal UI on instructional configurations."""

import asyncio
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


@pytest.mark.parametrize("mode", ["full", "schema", "incomplete", "unconfirmed"])
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
            if mode == "full":
                assert "instructional_scalar" in summary and "2 selected times" in summary
                assert "Planned outputs" in summary and ".model_grid.nc" in summary
                assert "frameit run " in summary and "--cpus=1" in summary
                assert "--no-overwrite" in summary and "not checked" in summary
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
            assert "Processing plan" in _text(app, "#report-details")
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
