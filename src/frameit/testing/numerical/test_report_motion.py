"""Exercise shared report feedback against controlled worker boundaries."""

import asyncio
from contextlib import suppress
from functools import partial
from threading import Event

import pytest
from textual.content import Content
from textual.widgets import ProgressBar
from textual.worker import WorkerFailed

from frameit.cli import _collect_report
from frameit.inspect_tui import InspectionApp
from frameit.testing.numerical.test_validate_tui import _case, _text
from frameit.validate_tui import ValidationApp


def test_logo_jumps_to_elapsed_phase_without_repainting_the_same_frame(tmp_path, monkeypatch):
    from frameit import report_motion
    from frameit.core.reports import PreflightResult

    now = [100.0]
    monkeypatch.setattr(report_motion, "monotonic", lambda: now[0], raising=False)
    finish = Event()

    def collect(*, progress):
        assert finish.wait(10)
        return PreflightResult("validate")

    async def exercise():
        app = ValidationApp(tmp_path / "config.yaml", collect)
        async with app.run_test(size=(80, 24)) as pilot:
            try:
                await pilot.pause()
                logo = app.query_one(report_motion.BrandActivity)
                assert logo.timer is not None
                first = logo.content
                logo._advance()
                assert logo.content is first
                now[0] += .5  # Simulate a late timer, without waiting in the test.
                logo._advance()
                frame = logo.content
                assert isinstance(frame, Content) and frame.spans != first.spans
                assert str(frame) == str(first)
                now[0] += 2
                logo._advance()
                assert logo.content is frame
            finally:
                finish.set()

    asyncio.run(exercise())


@pytest.mark.parametrize(("app_type", "command"), [
    (InspectionApp, "inspect"), (ValidationApp, "validate"),
])
def test_busy_feedback_resizes_and_stops(tmp_path, app_type, command):
    path = _case(tmp_path)
    ready, scanning, proceed, finish = (Event() for _ in range(4))

    def collect(*, progress):
        progress("metadata", "atmosphere", None, None)
        ready.set()
        assert proceed.wait(10)
        progress("metadata", "atmosphere", 1, 4)
        scanning.set()
        assert finish.wait(10)
        return _collect_report(path, command=command, sample_only=command == "inspect",
                               schema_only=command == "validate")

    async def exercise():
        app = app_type(path, collect)
        async with app.run_test(size=(120, 40)) as pilot:
            try:
                assert await asyncio.to_thread(ready.wait, 5)
                await pilot.pause()
                assert app.query("#brand-activity")
                logo = app.query_one("#brand-activity")
                bar = app.query_one("#work-progress", ProgressBar)
                assert logo.display and logo.timer is not None
                assert bar.display and bar.total is None
                await pilot.resize_terminal(52, 16)
                assert not logo.display and logo.timer is None
                assert app.query_one("#local-activity").loading
                proceed.set()
                assert await asyncio.to_thread(scanning.wait, 5)
                await pilot.pause()
                assert bar.display and (bar.progress, bar.total) == (1, 4)
                assert "atmosphere · 1 of 4 files checked" in _text(app, "#operation-context")
                finish.set()
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert app.result_code == 0
                assert not bar.display and bar.total == 1
                assert not logo.display and logo.timer is None
                assert not app.query_one("#local-activity").loading
                assert app._elapsed_timer is None
                await pilot.press("q")
            finally:
                proceed.set()
                finish.set()
        assert app.return_value == 0

    asyncio.run(exercise())


def test_selector_copy_toasts_are_literal_and_do_not_pile_up(tmp_path, monkeypatch):
    path = _case(tmp_path)
    collect = partial(_collect_report, path, command="inspect", sample_only=True)

    def unavailable(_):
        raise OSError("Clipboard unavailable [device]")

    async def exercise():
        app = InspectionApp(path, collect)
        async with app.run_test(size=(80, 24), notifications=True) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("2", "c", "c")
            await pilot.pause()
            assert "instructional_scalar" in app.clipboard
            assert len(app.query("Toast")) == 1
            assert "Sent to terminal" in str(app.query_one("Toast").render())
            await pilot.press("p")
            await pilot.pause()
            assert app.clipboard == str(path.absolute())
            assert "Configuration path" in str(app.query_one("Toast").render())
            monkeypatch.setattr(app, "copy_to_clipboard", unavailable)
            await pilot.press("c")
            await pilot.pause()
            toast = app.query_one("Toast")
            assert toast.has_class("-warning")
            assert "Clipboard unavailable" in str(toast.render())
            assert "YAML selector" in _text(app, "#field-details")
            await pilot.press("q")
        assert app.return_value == 0

    asyncio.run(exercise())


@pytest.mark.parametrize("refresh", [False, True])
def test_buffered_notices_do_not_stack_or_outlive_refresh(tmp_path, refresh):
    path = _case(tmp_path)
    started, release = Event(), Event()
    calls = 0

    def collect(*, progress):
        nonlocal calls
        calls += 1
        if calls == 2:
            started.set()
            assert release.wait(10)
        return _collect_report(path, command="inspect", sample_only=True, progress=progress)

    async def exercise():
        app = InspectionApp(path, collect)
        async with app.run_test(size=(52, 16), notifications=True) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("2")
            app.action_copy_config_path()
            app.action_copy_selector()
            app.action_copy_config_path()
            try:
                if refresh:
                    app.action_refresh()
                    assert await asyncio.to_thread(started.wait, 5)
                await pilot.pause()
                toasts = list(app.query("Toast"))
                if refresh:
                    assert not toasts
                else:
                    assert len(toasts) == 1
                    assert toasts[0].is_on_screen
                    assert toasts[0].region.y > app.query_one("#identity-bar").region.bottom
                    assert "Configuration path" in str(toasts[0].render())
            finally:
                release.set()
            if refresh:
                await app.workers.wait_for_complete()

    asyncio.run(exercise())


def test_blocked_validation_keeps_one_incomplete_indicator_and_has_help(tmp_path):
    path = _case(tmp_path)

    def collect(*, progress):
        report = _collect_report(path, command="validate", progress=progress)
        report.deferred_checks.insert(0, {
            "status": "blocked", "path": "outputs", "message": "Prerequisite pending.",
        })
        return report

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(80, 24), notifications=True) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "Validation incomplete" in _text(app, "#status")
            assert "unconfirmed" in _text(app, "#summary").lower()
            assert "frameit run" not in _text(app, "#summary")
            assert not app.query("Toast")
            await pilot.press("question_mark")
            assert "Copy evidence" in _text(app.screen, "#report-help")
            await pilot.press("escape")
            await pilot.press("2")
            assert "Prerequisite pending." in _text(app, "#finding")
            await pilot.press("q")
        # The TUI does not change the report collector's exit-code contract.
        assert app.return_value == 0

    asyncio.run(exercise())


def test_refresh_keeps_the_same_finding_and_reading_position(tmp_path):
    path = _case(tmp_path)
    calls = 0
    selected_text = "v: separate native groups need an explicit selection."

    def collect(*, progress):
        nonlocal calls
        calls += 1
        report = _collect_report(path, command="validate", schema_only=True, progress=progress)
        notes = [
            {"status": "unfinished-selection", "path": "sources.atmosphere",
             "message": "t: select a native group."},
            {"status": "unfinished-selection", "path": "sources.atmosphere",
             "message": "\n".join([selected_text] + [f"Evidence line {i}" for i in range(24)])},
        ]
        if calls > 1:
            notes.insert(0, {**notes[0], "message": "r: new field discovery note."})
        report.deferred_checks[:0] = notes
        return report

    async def exercise():
        app = ValidationApp(path, collect, schema_only=True)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("2", "down", "enter", "pagedown")
            await pilot.wait_for_scheduled_animations()
            detail = app.query_one("#finding-scroll")
            offset = detail.scroll_offset
            assert selected_text in _text(app, "#finding")
            assert offset.y > 0 and detail.has_focus
            await pilot.press("r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert selected_text in _text(app, "#finding")
            assert app.query_one("#finding-list").highlighted == 2
            assert detail.scroll_offset == offset and detail.has_focus

    asyncio.run(exercise())


@pytest.mark.parametrize("motion", [True, False])
def test_report_page_navigation_respects_motion(tmp_path, monkeypatch, motion):
    from textual import constants

    path = _case(tmp_path)
    collect = partial(_collect_report, path, command="validate", schema_only=True)
    monkeypatch.setattr(constants, "SMOOTH_SCROLL", motion)

    async def exercise():
        app = ValidationApp(path, collect, schema_only=True)
        async with app.run_test(size=(52, 16)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("3", "tab", "enter", "3")
            details = app.query_one("#details-scroll")
            seen = []
            scroll = details.scroll_page_down

            def record(**kwargs):
                seen.append(kwargs)
                return scroll(**kwargs)

            monkeypatch.setattr(details, "scroll_page_down", record)
            await pilot.press("pagedown")
            await pilot.wait_for_scheduled_animations()
            assert details.scroll_y > 0
            assert seen and seen[0].get("animate") is motion and seen[0].get("duration") == .12
            await pilot.press("q")

    asyncio.run(exercise())


@pytest.mark.parametrize(("app_type", "command", "pane", "focus", "main", "key"), [
    (InspectionApp, "inspect", "#sources-pane", "sources", "#fields", "1"),
    (ValidationApp, "validate", "#finding-list", "finding-list", "#finding-scroll", "2"),
])
def test_wide_sidebar_keeps_focus_and_recovers_on_resize(
        tmp_path, app_type, command, pane, focus, main, key):
    path = _case(tmp_path)
    collect = partial(_collect_report, path, command=command, sample_only=command == "inspect",
                      schema_only=command == "validate")

    async def exercise():
        app = app_type(path, collect)
        width_for_sidebar = 150 if command == "inspect" else 120
        async with app.run_test(size=(width_for_sidebar, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press(key)
            sidebar = app.query_one(pane)
            content = app.query_one(main)
            assert app.focused.id == focus
            width = content.region.width
            await pilot.press("b")
            await pilot.wait_for_scheduled_animations()
            assert not sidebar.display and content.region.width > width
            assert app.focused is content
            await pilot.press("b")
            await pilot.wait_for_scheduled_animations()
            assert sidebar.display and content.region.width == width
            assert app.focused.id == focus
            await pilot.press("b")
            assert app.focused is content
            app.action_toggle_sidebar()
            await pilot.resize_terminal(width_for_sidebar + 12, 44)
            await pilot.wait_for_scheduled_animations()
            assert sidebar.display and app.focused.id == focus
            await pilot.resize_terminal(width_for_sidebar, 40)
            await pilot.press("b", "b", "b")
            await pilot.resize_terminal(80, 24)
            await pilot.press(key)
            assert sidebar.display and app.focused.id == focus
            await pilot.resize_terminal(width_for_sidebar, 40)
            await pilot.wait_for_scheduled_animations()
            assert not sidebar.display and content.region.width > width
            assert app.focused is content
            await pilot.press("q")
        assert app.return_value == 0

    asyncio.run(exercise())


def test_refresh_worker_error_keeps_previous_report_marked_stale(tmp_path):
    path = _case(tmp_path)
    calls = 0

    def collect(*, progress):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("reader could not finish")
        return _collect_report(path, command="inspect", sample_only=True, progress=progress)

    async def exercise():
        app = InspectionApp(path, collect)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("2", "c")
            assert "instructional_scalar" in app.clipboard
            old = _text(app, "#source-scope")
            await pilot.press("r")
            with suppress(WorkerFailed):
                await app.workers.wait_for_complete()
            await pilot.pause()
            assert "previous report is stale" in _text(app, "#status")
            assert "reader could not finish" in _text(app, "#status")
            assert _text(app, "#source-scope") == old
            assert app.query_one("#explorer").display
            app.copy_to_clipboard("unchanged")
            await pilot.press("c")
            assert app.clipboard == "unchanged"
            await pilot.press("q")
        assert app.return_value == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("no_color,level", [(False, "none"), (True, "full")])
def test_reduced_rendering_keeps_static_progress(tmp_path, no_color, level):
    path = _case(tmp_path)
    entered, leave = Event(), Event()
    collect = partial(_collect_report, path, command="validate", schema_only=True)

    def blocked(*, progress):
        entered.set()
        assert leave.wait(10)
        return collect(progress=progress)

    async def exercise():
        app = ValidationApp(path, blocked, schema_only=True)
        app.animation_level = level
        app.no_color = no_color
        async with app.run_test(size=(80, 24)) as pilot:
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                await pilot.pause()
                assert app.query("#brand-activity")
                logo = app.query_one("#brand-activity")
                assert logo.display == (not no_color)
                assert logo.timer is None
                assert not app.query_one("#local-activity").loading
                assert not app.query_one("#work-progress").display
                assert "Reading configuration" in _text(app, "#status")
                leave.set()
                await app.workers.wait_for_complete()
                await pilot.pause()
                await pilot.press("q")
            finally:
                leave.set()
        assert app.return_value == 0

    asyncio.run(exercise())
