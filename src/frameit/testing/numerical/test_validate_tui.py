"""Exercise the terminal UI on instructional configurations."""

import asyncio
import os
import pty
import select
import subprocess
import sys
import termios
from contextlib import nullcontext, suppress
from functools import partial
from shlex import join
from threading import Event
from time import monotonic

import pytest
import yaml
from textual import on
from textual.events import Key, MouseScrollDown
from textual.geometry import Region
from textual.worker import Worker, WorkerCancelled, WorkerFailed, WorkerState

from frameit.cli import _collect_report
from frameit.core.configuration import write_template
from frameit.testing.documentation_example import create_first_run_input


def _case(root):
    create_first_run_input(root / "data/first-run.nc")
    return write_template("arome-fixed-scalar", root / "config.yaml")


def _text(app, selector):
    return str(app.query_one(selector).content)


def test_validation_uses_shared_report_shell():
    from frameit.report_tui import ReportApp
    from frameit.validate_tui import ValidationApp

    assert issubclass(ValidationApp, ReportApp)


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
    failed = mode in {"incomplete", "unconfirmed", "malformed"}
    collect = partial(
        _collect_report, path, command="validate", schema_only=schema_only, overrides=overrides)

    async def exercise():
        app = ValidationApp(path, collect, schema_only=schema_only, overrides=overrides)
        async with app.run_test(size=(52, 16)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            verdict = ("Validation failed" if failed else
                       "Schema checks passed" if schema_only else "Validation passed")
            status = app.query_one("#status")
            rendered = status.render_lines(Region(0, 0, status.region.width, 1))[0].text
            assert rendered.lstrip().startswith(verdict)
            assert app.query_one("#report-tabs").active == "overview"
            assert _text(app, "#context") == path.name
            summary = _text(app, "#summary")
            assert "scientific validity" not in summary
            labels = ("Inputs", "Selection", "Time", "Region", "Outputs")
            assert all(label in summary for label in labels)
            if mode in {"full", "unused-centre"}:
                assert "static support" in summary.splitlines()[0]
                assert "value/mask checks" in summary.splitlines()[1]
                assert "1 file scanned" in summary and "2 source times selected" in summary
                assert "1 model-grid output field" in summary and "1 planned" in summary
                assert "instructional_scalar" not in summary and ".model_grid.nc" not in summary
                assert "frameit run " in summary and "--cpus=1" in summary
                assert "--no-overwrite" in summary
                if mode == "unused-centre":
                    assert "Full domain; configured centre unused" in summary
                else:
                    assert "Fixed centre" in summary and "km crop requested" in summary
            elif mode == "schema":
                assert "validate without --schema-only" in summary
                assert "frameit run " not in summary
                assert "Not checked (schema only)" in summary and ".model_grid.nc" not in summary
            else:
                assert "Fix first" in summary and "frameit run " not in summary
                assert summary.index("Fix first") < summary.index("Inputs")
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
                assert "Partial plan" in plan.title
                if mode == "unconfirmed":
                    assert "unconfirmed" in plan.title and ".model_grid.nc" in plan_text
                    assert "unconfirmed" in plan_text.lower()
                else:
                    assert "unconfirmed" not in plan.title
            else:
                assert plan.title == "Processing plan"
                if mode in {"full", "unused-centre"}:
                    assert "instructional_scalar" in plan_text and ".model_grid.nc" in plan_text
                    products = app.query_one("#plan-products")
                    assert products.row_count == 1
                    source, kind, count, destination = map(str, products.get_row_at(0))
                    assert (source, kind, count) == ("atmosphere", "model grid", "1")
                    assert "/" not in destination and destination.endswith(".model_grid.nc")

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
        assert app.return_value == int(failed)

    asyncio.run(exercise())
    assert path.read_bytes() == original and not (tmp_path / "output").exists()


def test_details_render_long_nested_yaml_lines_without_wrapping(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    raw = yaml.safe_load(path.read_text())
    description = "instructional-" * 8
    raw["run"]["description"] = description
    path.write_text(yaml.safe_dump(raw))
    collect = partial(_collect_report, path, command="validate", schema_only=True)

    async def exercise():
        app = ValidationApp(path, collect, schema_only=True)
        async with app.run_test(size=(52, 16)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("3")
            details = app.query_one("#details-scroll")
            viewport = details.scrollable_size
            await pilot.press("tab", "enter")
            config = app.query_one("#detail-configuration-text")
            line = f"  description: {description}"
            row = str(config.content).splitlines().index(line)
            assert config.render_line(row).text.rstrip() == line
            assert details.max_scroll_x > 0
            assert details.scrollable_size == viewport
            assert details.scrollbars_space == (1, 1)
            vertical = details.vertical_scrollbar
            strokes = [vertical.render_line(i).text for i in range(vertical.size.height)]
            assert any("┃" in line for line in strokes)
            corner = (vertical.region.x, details.horizontal_scrollbar.region.y)
            background = app.screen.styles.background.rich_color
            assert background.triplet == (0, 0, 0)
            assert app.screen.get_style_at(*corner).bgcolor == background
            await pilot.press("right")
            await pilot.wait_for_scheduled_animations()
            assert details.scroll_x > 0
            x, y = vertical.region.offset
            grip = next(i for i, line in enumerate(strokes) if "┃" in line)
            await pilot.mouse_down(offset=(x, y + grip))
            await pilot.hover(offset=(x, y + grip + 2))
            await pilot.mouse_up(offset=(x, y + grip + 2))
            await pilot.wait_for_scheduled_animations()
            assert details.scroll_y > 0
            details.scroll_to(y=0, animate=False)
            await pilot.pause()
            assert "┃" not in strokes[-1]
            await pilot.click(offset=(x, vertical.region.bottom - 1))
            await pilot.wait_for_scheduled_animations()
            assert details.scroll_y > 0
            await pilot.press("q")

    asyncio.run(exercise())


def test_details_thumb_is_draggable_with_only_one_clipped_column(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    raw = yaml.safe_load(path.read_text())
    raw["run"]["description"] = "a" * 116 + "END"
    path.write_text(yaml.safe_dump(raw))
    collect = partial(_collect_report, path, command="validate", schema_only=True)

    async def exercise():
        app = ValidationApp(path, collect, schema_only=True)
        async with app.run_test(size=(104, 92)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("3", "tab", "enter")
            details = app.query_one("#details-scroll")
            assert details.max_scroll_x > 1
            await pilot.resize_terminal(app.size.width + details.max_scroll_x - 1, app.size.height)
            assert (details.max_scroll_x, details.max_scroll_y) == (1, 0)
            bar = details.horizontal_scrollbar
            assert "━" in bar.render_line(0).text
            x, y = bar.region.offset
            await pilot.mouse_down(offset=(x, y))
            await pilot.hover(offset=(x + 2, y))
            await pilot.wait_for_scheduled_animations()
            await pilot.mouse_up(offset=(x + 2, y))
            assert details.scroll_x == 1

    asyncio.run(exercise())


def test_details_pins_only_the_section_scrolled_under_the_top_edge(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    collect = partial(_collect_report, path, command="validate")

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("3", "tab", "enter")
            details = app.query_one("#details-scroll")
            viewport = details.scrollable_size
            details.scroll_to(y=3, animate=False)
            await pilot.pause()
            pinned = app.query_one("#details-sticky")
            assert pinned.is_on_screen
            assert _text(app, "#details-sticky") == "Effective configuration"
            x, y = pinned.region.offset
            app.post_message(MouseScrollDown(None, x + 2, y, 0, 0, 0, False, False, False))
            await pilot.pause()
            await pilot.wait_for_scheduled_animations()
            assert details.scroll_offset.y > 3

            details.scroll_end(animate=False)
            await pilot.pause()
            await pilot.click("#detail-plan CollapsibleTitle", offset=(3, 0))
            plan = app.query_one("#detail-plan")
            assert not plan.collapsed
            details.scroll_to(y=plan.virtual_region.y, animate=False)
            await pilot.pause()
            assert not _text(app, "#details-sticky")
            await pilot.press("3")
            assert details.has_focus
            details.scroll_to(y=plan.virtual_region.y + 3, animate=False)
            await pilot.pause()
            assert _text(app, "#details-sticky") == "Processing plan"

            await pilot.click("#details-sticky", offset=(3, 0))
            assert plan.collapsed
            assert not app.query_one("#detail-configuration").collapsed
            assert "Processing plan" not in _text(app, "#details-sticky")
            heading = plan.query_one("CollapsibleTitle")
            assert heading.has_focus
            viewport_region = details.scrollable_content_region
            assert viewport_region.y <= heading.region.y < viewport_region.bottom

            await pilot.press("enter")
            assert not plan.collapsed
            await pilot.press("enter")
            assert plan.collapsed
            details.scroll_home(animate=False)
            await pilot.pause()
            assert not _text(app, "#details-sticky")
            assert details.scrollable_size == viewport
            await pilot.press("q")

    asyncio.run(exercise())


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
    air, sea = (next(line for line in lines if name in line and "times selected" in line)
                for name in ("air", "sea"))
    assert "2 source times selected" in air and "noleap" not in air
    assert "2001-02-01 (360_day)" in air and "2001-02-30 (360_day)" in air
    assert "3 source times selected" in sea and "360_day" not in sea
    assert "2001-03-01 (noleap)" in sea and "2001-03-30 (noleap)" in sea


@pytest.mark.parametrize("product", ["model_grid", "polar"])
def test_console_distinguishes_scanned_files_source_times_and_centre_matches(tmp_path, product):
    from frameit.validate_tui import _overview

    times = ["2022-02-01T00:00:00", "2022-02-01T01:00:00", "2022-02-01T02:00:00"]
    report = {"status": "ok", "errors": [], "data": {
        "configuration": {"sources": {"air": {"model": "arome"}}, "region": {
            "track": {"file": "track.nc"}, "width_km": {"x": 200, "y": 200},
            "sources_coupling_time_association": "common",
        }},
        "inputs": [{"source": "air", "path": f"air{i}.nc", "status": status}
                   for i, status in enumerate(["selected"] * 3 + ["time_excluded"])],
        "plan": {
            "sources": {"air": {"selected_times": times, "region": {"associations": [
                {"source_time": time, "coupling_time": time} for time in times[1:]
            ]}}},
            "products": [{"source": "air", "product": product, "fields": ["t"]}],
            "planned_products": [f"air.{product}.nc"],
        },
    }}

    summary = _overview(report, tmp_path / "case.yaml", False, {}, has_warnings=False)
    assert "4 files scanned" in summary and "3 source times selected" in summary
    assert "2 source times matched to centres" in summary
    assert ("200 × 200 km crop requested" in summary) == (product == "model_grid")


def test_live_scan_and_reload(tmp_path, monkeypatch):
    from frameit import report_check, report_tui, validate_tui

    path = _case(tmp_path)
    clock = [100.0]
    monkeypatch.setattr(report_tui, "monotonic", lambda: clock[0])
    monkeypatch.setattr(report_check, "monotonic", lambda: clock[0])
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
                    context = _text(app, "#operation-context")
                    assert expected in (status if index == 3 else context)
                    assert ("ETA ~00:08" in context) if index == 1 else ("ETA" not in context)
                    if index == 1:
                        clock[0] += 120
                        async with asyncio.timeout(3):
                            while "ETA" in _text(app, "#operation-context"):
                                await pilot.pause(0.05)
                        assert "2 of 6 files checked" in _text(app, "#operation-context")
                    clock[0] += 4
                    resume[index].set()

                await app.workers.wait_for_complete()
                await pilot.pause()
                assert "passed" in _text(app, "#status")
                assert app.query_one("Footer").display
                assert not app.query_one("#interrupt-hint").display
                keys = app.query("FooterKey")
                assert list(dict.fromkeys(key.key for key in keys)) == ["1", "2", "3", "r", "q"]
                assert all(0 < key.region.right <= app.size.width for key in keys)

                path.write_text("schema_version: 3\nsources: [\n")
                await pilot.press("r")
                assert await asyncio.to_thread(ready[4].wait, 5)
                await pilot.press("r")
                assert calls == 2
                assert "passed" not in _text(app, "#status")
                assert not app.query_one("#report-tabs").display
                assert "Refreshing" in _text(app, "#status")
                assert app.query_one("#brand-activity").display
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


@pytest.mark.parametrize("mode", ["initial", "refresh", "retry", "retry-fails", "idle"])
def test_validation_interruption_preserves_the_previous_view(tmp_path, mode):
    from frameit.validate_tui import ValidationApp

    release, started = Event(), Event()
    path = _case(tmp_path)
    calls = 0
    refresh = mode in {"refresh", "retry", "retry-fails"}

    def collect(*, progress):
        nonlocal calls
        calls += 1
        if (mode == "initial" and calls == 1) or (refresh and calls == 2):
            started.set()
            assert release.wait(10)
            progress("metadata", "atmosphere", 0, 1)
        if mode == "retry-fails" and calls == 3:
            raise RuntimeError("reader could not finish")
        return _collect_report(path, command="validate", progress=progress)

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(120, 40)) as pilot:
            try:
                if mode != "initial":
                    await app.workers.wait_for_complete()
                    await pilot.pause()
                    assert app.result_code == 0
                if refresh:
                    await pilot.press("3")
                    await pilot.click("#detail-plan CollapsibleTitle", offset=(3, 0))
                    if mode == "retry":
                        await pilot.press("3")
                    await pilot.press("pagedown")
                    await pilot.wait_for_scheduled_animations()
                    details = app.query_one("#details-scroll")
                    offset = details.scroll_offset
                    focused = details if mode == "retry" else details.query_one(
                        "#detail-plan CollapsibleTitle")
                    assert offset.y > 0 and focused.has_focus
                    previous = _text(app, "#summary")
                    await pilot.press("r", "1")
                if mode != "idle":
                    assert await asyncio.to_thread(started.wait, 5)
                    worker = next(iter(app.workers))
                if refresh:
                    assert not app.query_one("#report-tabs").display
                    assert app.query_one("#brand-activity").display
                    await pilot.resize_terminal(52, 16)
                    assert app.query_one("#brand-activity").display
                    await pilot.resize_terminal(120, 40)
                    await pilot.press("enter")
                await pilot.press("ctrl+c")
                if mode != "idle":
                    status = _text(app, "#status").lower()
                    assert "cancellation requested" in status
                    await pilot.press("r")
                    assert list(app.workers) == [worker]
                    release.set()
                    with pytest.raises(WorkerCancelled):
                        await worker.wait()
                    await pilot.pause()
                    if mode == "initial":
                        assert "cancelled" in _text(app, "#status").lower()
                        assert "previous" not in _text(app, "#status").lower()
                        assert not app.query_one("#report-tabs").display
                        await pilot.press("r")
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        assert app.result_code == 0
                        await pilot.press("q")
                if refresh:
                    tabs = app.query_one("#report-tabs")
                    assert tabs.display and tabs.active == "details"
                    assert not app.query_one("#detail-plan").collapsed
                    assert focused.has_focus and details.scroll_offset == offset
                    assert _text(app, "#summary") == previous
                    assert "previous report" in _text(app, "#status").lower()
                    assert not app.query_one("#brand-activity").display
                    assert {"1", "2", "3", "r", "q"} <= {
                        key.key for key in app.query("FooterKey") if key.is_on_screen
                    }
                    if mode == "retry":
                        await pilot.press("r")
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        assert "passed" in _text(app, "#status")
                    elif mode == "retry-fails":
                        await pilot.press("r")
                        with suppress(WorkerFailed):
                            await app.workers.wait_for_complete()
                        await pilot.pause()
                        assert "previous report is stale" in _text(app, "#status")
                    await pilot.press("q")
            finally:
                release.set()
        assert app.return_value == (0 if mode in {"initial", "retry"} else 130)

    asyncio.run(exercise())


def test_revalidation_before_view_has_redrawn_keeps_cancelled_details_focus(tmp_path):
    from frameit.validate_tui import ValidationApp

    class PromptRetry(ValidationApp):
        retry = True

        @on(Worker.StateChanged)
        def retry_first_cancellation(self, event):
            if self.retry and event.state == WorkerState.CANCELLED:
                self.retry = False
                self.call_next(self.action_refresh)

    path = _case(tmp_path)
    entered, release = [Event(), Event()], [Event(), Event()]
    calls = 0

    def collect(*, progress):
        nonlocal calls
        calls += 1
        if calls > 1:
            index = calls - 2
            entered[index].set()
            assert release[index].wait(10)
            progress("report", None, None, None)
        return _collect_report(path, command="validate", progress=progress)

    async def exercise():
        app = PromptRetry(path, collect)
        app.animation_level = "none"
        async with app.run_test(size=(80, 24)) as pilot:
            try:
                await app.workers.wait_for_complete()
                await pilot.press("3")
                await pilot.click("#detail-plan CollapsibleTitle", offset=(3, 0))
                await pilot.press("pagedown")
                focused = app.query_one("#detail-plan CollapsibleTitle")
                assert focused.has_focus
                details = app.query_one("#details-scroll")
                offset = details.scroll_offset
                assert offset.y > 0
                await pilot.press("r")
                for index in range(2):
                    assert await asyncio.to_thread(entered[index].wait, 5)
                    worker = next(iter(app.workers))
                    await pilot.press("ctrl+c")
                    release[index].set()
                    with pytest.raises(WorkerCancelled):
                        await worker.wait()
                await pilot.pause()
                assert focused.has_focus
                assert details.scroll_offset == offset
                await pilot.press("q")
            finally:
                for event in release:
                    event.set()
        assert app.return_value == 130

    asyncio.run(exercise())


def test_keys_buffered_after_refresh_do_not_change_the_restored_finding(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    path.write_text(path.read_text().replace("data/first-run.nc", "absent.nc"))
    started, release = Event(), Event()
    calls = 0

    def collect(*, progress):
        nonlocal calls
        calls += 1
        if calls == 2:
            started.set()
            assert release.wait(10)
            progress("metadata", None, None, None)
        return _collect_report(path, command="validate", progress=progress)

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(80, 24)) as pilot:
            try:
                await app.workers.wait_for_complete()
                await pilot.press("2", "down")
                listing = app.query_one("#finding-list")
                assert listing.has_focus and listing.highlighted == 1
                finding = _text(app, "#finding")
                app.post_message(Key("r", "r"))
                app.post_message(Key("down", None))
                assert await asyncio.to_thread(started.wait, 5)
                worker = next(iter(app.workers))
                await pilot.press("ctrl+c")
                release.set()
                with pytest.raises(WorkerCancelled):
                    await worker.wait()
                async with asyncio.timeout(3):
                    while not listing.has_focus:
                        await pilot.pause()
                assert listing.highlighted == 1 and _text(app, "#finding") == finding
            finally:
                release.set()

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
            assert _text(app, "#status") == (
                "Validation passed · Metadata preflight · 2 field discovery notes")
            await pilot.press("2")
            listing = app.query_one("#finding-list")
            style = "option-list--option-highlighted"
            assert not listing.get_component_styles(style).text_style.underline
            focus = listing.styles.border_left
            await pilot.press("enter")
            assert app.query_one("#finding-scroll").has_focus
            assert listing.styles.border_left != focus
            await pilot.press("escape")
            first, second = (str(listing.get_option_at_index(i).prompt) for i in range(2))
            assert first != second and all(" · t" in title for title in (first, second))
            assert "Field discovery · sources.atmosphere" in _text(app, "#finding")
            assert "native vertical group is ambiguous" in _text(app, "#finding")
            await pilot.press("n")
            assert listing.option_count == 2
            await pilot.press("n")
            assert listing.option_count == 3
            await pilot.press("down", "down")
            detail = _text(app, "#finding")
            assert "During run" in detail and "value/mask checks" in detail
            await pilot.press("q")
        assert app.return_value == 0

    asyncio.run(exercise())


def test_wide_finding_scrolls_to_yaml_location_and_help(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    request = yaml.safe_load(path.read_text())
    request["sources"]["atmosphere"]["files"] = str(
        tmp_path / ("nonexistent-" * 22) / "*.nc")
    path.write_text(yaml.safe_dump(request))
    collect = partial(_collect_report, path, command="validate")

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(120, 30)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("2", "enter", "tab", "enter", "end")
            await pilot.wait_for_scheduled_animations()
            detail = app.query_one("#finding-scroll")
            finding = app.query_one("#finding-evidence-text")
            assert "YAML:" in str(finding.content) and "Troubleshooting:" in str(finding.content)
            assert detail.has_focus_within and detail.scroll_y > 0
            assert finding.region.bottom <= app.query_one("#findings-layout").region.bottom
            await pilot.press("b")
            await pilot.wait_for_scheduled_animations()
            await pilot.press("end")
            await pilot.wait_for_scheduled_animations()
            assert finding.region.bottom <= app.query_one("#findings-layout").region.bottom

    asyncio.run(exercise())


def test_compact_finding_shows_repair_before_long_evidence_and_returns_to_selection(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    request = yaml.safe_load(path.read_text())
    pattern = str(tmp_path / ("unavailable-" * 25) / "*.nc")
    request["sources"]["atmosphere"]["files"] = pattern
    path.write_text(yaml.safe_dump(request))

    def collect(*, progress):
        result = _collect_report(path, command="validate", progress=progress)
        result.deferred_checks.extend({
            "path": f"check.{i}", "status": "execution-dependent",
            "message": "This check requires execution.",
        } for i in range(25))
        return result

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("2")
            listing = app.query_one("#finding-list")
            reader = app.query_one("#finding-scroll")
            assert listing.has_focus and not reader.display
            await pilot.press("enter")
            assert reader.has_focus and not listing.display
            assert reader.region.width == app.query_one("#findings-layout").region.width
            shown = _text(app, "#finding")
            assert "No input files match" in shown and "Repair: Correct" in shown
            assert "Location: config.yaml:" in shown and pattern not in shown
            assert app.query_one("#finding").region.bottom <= reader.region.bottom
            assert app.query_one("#finding-evidence").collapsed
            await pilot.press("y")
            assert pattern in app.clipboard and str(path) in app.clipboard
            await pilot.press("escape")
            assert listing.has_focus and listing.highlighted == 0
            assert not reader.display
            await pilot.press("end", "up")
            await pilot.wait_for_scheduled_animations()
            selection, offset = listing.highlighted, listing.scroll_offset
            assert offset.y > 0
            await pilot.press("enter", "escape")
            assert listing.has_focus and listing.highlighted == selection
            assert listing.scroll_offset == offset
            await pilot.press("1")
            app.post_message(Key("2", "2"))
            app.post_message(Key("enter", "\r"))
            await pilot.pause()
            assert reader.has_focus

    asyncio.run(exercise())


@pytest.mark.parametrize("terminal_can_suspend", [True, False])
def test_live_editor_repairs_only_the_active_config_and_preserves_context(
        tmp_path, monkeypatch, terminal_can_suspend):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path).rename(tmp_path / "config [with spaces;].yaml")
    good = "data/first-run.nc"
    assert good in path.read_text()
    path.write_text(path.read_text().replace(good, "missing.nc"))
    editor = tmp_path / "editor with spaces.py"
    editor.write_text(
        "import pathlib, sys\n"
        f"assert sys.argv[1:] == [{str(path)!r}]\n"
        "p = pathlib.Path(sys.argv[1])\n"
        f"p.write_text(p.read_text().replace('missing.nc', {good!r}))\n")
    monkeypatch.setenv("VISUAL", join([sys.executable, str(editor)]))
    collect = partial(_collect_report, path, command="validate")

    async def exercise():
        app = ValidationApp(path, collect)
        if terminal_can_suspend:
            # The headless driver has no terminal to hand to the real test editor process.
            monkeypatch.setattr(app, "suspend", nullcontext)
        async with app.run_test(size=(80, 24), notifications=True) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("2", "enter", "l")
            assert app.clipboard.startswith(f"{path}:")
            reader = app.query_one("#finding-scroll")
            assert reader.has_focus and app.result_code == 1
            await pilot.press("e")
            assert reader.has_focus and app.result_code == 1
            if terminal_can_suspend:
                assert good in path.read_text()
                assert "not revalidated" in _text(app, "#status").lower()
                await pilot.press("r")
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert "passed" in _text(app, "#status").lower()
                assert app.query_one("#report-tabs").active == "findings"
                async with asyncio.timeout(3):
                    while not reader.has_focus:
                        await pilot.pause()
                assert app.result_code == 0
            else:
                assert "missing.nc" in path.read_text()
                assert "Editor unavailable" in str(app.query_one("Toast").render())
                assert app.clipboard.startswith(f"{path}:")

    asyncio.run(exercise())


def test_blocked_check_links_to_the_reported_cause_and_setting_origin(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    path.write_text(path.read_text().replace("data/first-run.nc", "not-found.nc"))
    collect = partial(_collect_report, path, command="validate")

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("2", "down", "enter")
            previous = _text(app, "#finding")
            assert "Blocked" in previous and "sources.atmosphere.files" in previous
            await pilot.press("g")
            choices = app.screen.query_one("#related-options")
            assert "E1201" in str(choices.get_option_at_index(0).prompt)
            await pilot.press("enter")
            assert "No input files match" in _text(app, "#finding")
            await pilot.press("g")
            choices = app.screen.query_one("#related-options")
            while "Setting" not in str(choices.highlighted_option.prompt):
                assert choices.highlighted < choices.option_count - 1
                await pilot.press("down")
            await pilot.press("enter")
            assert app.query_one("#report-tabs").active == "details"
            evidence = _text(app, "#detail-why-text")
            assert "sources.atmosphere.files" in evidence and "authored" in evidence.lower()
            await pilot.press("escape", "escape")
            assert _text(app, "#finding") == previous
            assert app.query_one("#finding-scroll").has_focus

    asyncio.run(exercise())


def test_planned_product_links_to_bound_field_and_back_to_its_uses(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    collect = partial(_collect_report, path, command="validate")

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("3")
            await pilot.click("#detail-plan CollapsibleTitle", offset=(3, 0))
            plan_body = app.query_one("#detail-plan-text").region
            body_style = app.screen.get_style_at(plan_body.right - 2, plan_body.y + 1)
            assert body_style.bgcolor.triplet == (0, 0, 0)
            await pilot.press("g", "down", "enter")
            evidence = _text(app, "#detail-why-text")
            assert "Native field: instructional_scalar" in evidence
            assert "Product uses: model_grid" in evidence
            await pilot.press("g")
            choices = app.screen.query_one("#related-options")
            assert "atmosphere.model_grid" in str(choices.get_option_at_index(0).prompt)
            await pilot.press("enter")
            assert "instructional_scalar" in _text(app, "#detail-plan-text")
            await pilot.press("escape")
            assert _text(app, "#detail-why-text") == evidence

    asyncio.run(exercise())


def test_related_evidence_uses_product_cursor_before_highlight_is_delivered(tmp_path):
    from frameit.testing.numerical.test_nemo_netcdf import nemo_document, nemo_scene
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    sea = tmp_path / "ocean.nc"
    nemo_scene().to_netcdf(sea, engine="h5netcdf")
    request = yaml.safe_load(path.read_text())
    request.pop("region")
    request["sources"].update(nemo_document(tmp_path, [sea])["sources"])
    path.write_text(yaml.safe_dump(request, sort_keys=False))
    collect = partial(_collect_report, path, command="validate")

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("3")
            await pilot.click("#detail-plan CollapsibleTitle", offset=(3, 0))
            await pilot.press("tab")
            table = app.query_one("#plan-products")
            assert app.result_code == 0 and table.has_focus and table.row_count == 2
            table.action_cursor_down()
            app.action_related()
            await pilot.pause()
            choices = app.screen.query_one("#related-options")
            assert str(choices.get_option_at_index(0).prompt) == "Source · ocean"
            assert "votemper" in str(choices.get_option_at_index(1).prompt)

    asyncio.run(exercise())


def test_changes_compare_completed_failed_checks_and_skip_cancelled_attempts(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    valid = path.read_text()
    first = valid.replace("data/first-run.nc", "absent-a.nc")
    second = valid.replace("data/first-run.nc", "absent-b.nc")
    path.write_text(first)
    entered, release = Event(), Event()
    calls = 0

    def collect(*, progress):
        nonlocal calls
        calls += 1
        if calls == 3:
            entered.set()
            assert release.wait(10)
            progress("configuration", None, None, None)
        return _collect_report(path, command="validate", progress=progress)

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(80, 24)) as pilot:
            try:
                await app.workers.wait_for_complete()
                assert app.result_code == 1
                path.write_text(second)
                await pilot.press("r")
                await app.workers.wait_for_complete()
                await pilot.press("u")
                assert app.result_code == 1
                summary = _text(app, "#detail-changes-text")
                assert "Newly reported" in summary and "absent-b.nc" in summary
                assert "No longer reported" in summary and "absent-a.nc" in summary
                assert "Resolved" not in summary and "sources.atmosphere.files" in summary
                await pilot.press("g", "enter")
                assert "absent-b.nc" in _text(app, "#finding-evidence-text")
                await pilot.press("escape")
                assert app.query_one("#report-tabs").active == "details"
                path.write_text(valid)
                await pilot.press("r")
                assert await asyncio.to_thread(entered.wait, 5)
                await pilot.press("ctrl+c")
                release.set()
                with suppress(WorkerCancelled):
                    await app.workers.wait_for_complete()
                await pilot.pause()
                assert _text(app, "#detail-changes-text") == summary
                await pilot.press("r")
                await app.workers.wait_for_complete()
                await pilot.pause()
                latest = _text(app, "#detail-changes-text")
                assert "absent-b.nc" in latest and "absent-a.nc" not in latest
                assert app.result_code == 0
            finally:
                release.set()

    asyncio.run(exercise())


def test_refresh_retains_finding_when_only_authored_line_numbers_move(tmp_path):
    from frameit.validate_tui import ValidationApp

    path = _case(tmp_path)
    config = yaml.safe_load(path.read_text())
    config["sources"]["atmosphere"]["files"] = ["absent-a.nc", "absent-b.nc"]
    path.write_text(yaml.safe_dump(config))
    collect = partial(_collect_report, path, command="validate")

    async def exercise():
        app = ValidationApp(path, collect)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("2", "down", "enter")
            evidence = _text(app, "#finding-evidence-text")
            assert "absent-b.nc" in evidence
            path.write_text("# Move the original line marks\n" + path.read_text())
            await pilot.press("r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            updated = _text(app, "#finding-evidence-text")
            assert "absent-b.nc" in updated and updated != evidence

    asyncio.run(exercise())


@pytest.mark.skipif(sys.platform != "linux", reason="tests the Linux driver's PTY restoration")
@pytest.mark.parametrize("command", ["validate", "inspect"])
def test_sigterm_restores_tty_during_terminal_report(tmp_path, command):
    path = _case(tmp_path)
    (tmp_path / "gate-next").touch()
    master, terminal = pty.openpty()
    termios.tcsetwinsize(terminal, (24, 80))
    original = termios.tcgetattr(terminal)
    script = """
import sys
from functools import partial
from pathlib import Path
from frameit import cli
from frameit.testing.numerical.test_report_process import gated_cli_report
cli._collect_report = partial(gated_cli_report, Path(sys.argv[1]).parent)
args = [sys.argv[2], sys.argv[1]]
cli.main(args + (['--cpus', '1'] if args[0] == 'validate' else []))
"""
    chunks = []

    def read_output():
        if select.select([master], [], [], 0.05)[0]:
            chunks.append(os.read(master, 65536))

    try:
        with subprocess.Popen(
            [sys.executable, "-c", script, str(path), command],
            stdin=terminal, stdout=terminal, stderr=terminal,
            env={**os.environ, "TERM": "xterm-256color"},
        ) as process:
            try:
                deadline = monotonic() + 10
                while not (started := list(tmp_path.glob("entered-*"))) and monotonic() < deadline:
                    read_output()
                assert started, b"".join(chunks)[-1500:].decode(errors="replace")
                reader_pid = int(started[0].name.split("-")[-1])
                assert reader_pid != process.pid
                assert not termios.tcgetattr(terminal)[3] & (termios.ICANON | termios.ECHO)
                process.terminate()
                # A terminal consumes output while the driver flushes on shutdown.
                deadline = monotonic() + 10
                while process.poll() is None and monotonic() < deadline:
                    read_output()
                assert process.returncode == 143
                assert termios.tcgetattr(terminal) == original
                with pytest.raises(ProcessLookupError):
                    os.kill(reader_pid, 0)
                while select.select([master], [], [], 0)[0]:
                    chunks.append(os.read(master, 65536))
                assert b"\x1b[?1049l" in b"".join(chunks)
            finally:
                (tmp_path / "release").touch()
                if process.poll() is None:
                    process.kill()
    finally:
        for fd in (master, terminal):
            os.close(fd)
