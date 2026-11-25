"""Exercise the terminal UI on instructional configurations."""

import asyncio
import os
import pty
import select
import subprocess
import sys
import termios
from contextlib import suppress
from functools import partial
from threading import Event
from time import monotonic

import pytest
import yaml
from textual import on
from textual.events import MouseScrollDown
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
            assert all(label in summary for label in ("Inputs", "Selection", "Region", "Outputs"))
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
                    assert plan_text.startswith("planned_products:")
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
            details.scroll_to(y=plan.virtual_region.y + 3, animate=False)
            await pilot.pause()
            assert _text(app, "#details-sticky") == "Processing plan"

            await pilot.press("enter")
            assert plan.collapsed
            assert "Processing plan" not in _text(app, "#details-sticky")
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
    from frameit import report_tui, validate_tui

    path = _case(tmp_path)
    clock = [100.0]
    monkeypatch.setattr(report_tui, "monotonic", lambda: clock[0])
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
                assert app.query_one("#local-activity").loading
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
        if mode == "initial" or (refresh and calls == 2):
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
                    await pilot.resize_terminal(120, 40)
                    await pilot.press("enter")
                await pilot.press("ctrl+c")
                if mode != "idle":
                    status = _text(app, "#status").lower()
                    assert "cancellation requested" in status
                    release.set()
                    with pytest.raises(WorkerCancelled):
                        await worker.wait()
                    await pilot.pause()
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
        assert app.return_value == (0 if mode == "retry" else 130)

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
            assert _text(app, "#status") == "Validation passed · 2 field discovery notes"
            await pilot.press("2")
            listing = app.query_one("#finding-list")
            style = "option-list--option-highlighted"
            assert listing.get_component_styles(style).text_style.underline
            await pilot.press("tab")
            assert app.query_one("#finding-scroll").has_focus
            assert not listing.get_component_styles(style).text_style.underline
            await pilot.press("shift+tab")
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
            await pilot.press("2", "tab", "end")
            await pilot.wait_for_scheduled_animations()
            detail = app.query_one("#finding-scroll")
            finding = app.query_one("#finding")
            assert "YAML:" in str(finding.content) and "Troubleshooting:" in str(finding.content)
            assert detail.has_focus and detail.scroll_y > 0
            assert finding.region.bottom <= app.query_one("#findings-layout").region.bottom
            await pilot.press("b")
            await pilot.wait_for_scheduled_animations()
            await pilot.press("end")
            await pilot.wait_for_scheduled_animations()
            assert finding.region.bottom <= app.query_one("#findings-layout").region.bottom

    asyncio.run(exercise())


@pytest.mark.skipif(sys.platform != "linux", reason="tests the Linux driver's PTY restoration")
@pytest.mark.parametrize("command", ["validate", "inspect"])
def test_sigterm_restores_tty_during_terminal_report(tmp_path, command):
    path = _case(tmp_path)
    master, terminal = pty.openpty()
    termios.tcsetwinsize(terminal, (24, 80))
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
args = [sys.argv[4], sys.argv[1]]
cli.main(args + (['--cpus', '1'] if args[0] == 'validate' else []))
"""
    try:
        with subprocess.Popen(
            [sys.executable, "-c", script, str(path), str(ready_write), str(resume_read), command],
            stdin=terminal, stdout=terminal, stderr=terminal,
            pass_fds=(ready_write, resume_read), env={**os.environ, "TERM": "xterm-256color"},
        ) as process:
            try:
                assert select.select([ready_read], [], [], 15)[0]
                assert os.read(ready_read, 1) == b"1"
                assert not termios.tcgetattr(terminal)[3] & (termios.ICANON | termios.ECHO)
                process.terminate()
                os.write(resume_write, b"1")
                # A terminal consumes output while the driver flushes on shutdown.
                chunks = []
                deadline = monotonic() + 10
                while process.poll() is None and monotonic() < deadline:
                    if select.select([master], [], [], 0.1)[0]:
                        chunks.append(os.read(master, 65536))
                assert process.returncode == 143
                assert termios.tcgetattr(terminal) == original
                while select.select([master], [], [], 0)[0]:
                    chunks.append(os.read(master, 65536))
                assert b"\x1b[?1049l" in b"".join(chunks)
            finally:
                if process.poll() is None:
                    process.kill()
    finally:
        for fd in (master, terminal, ready_read, ready_write, resume_read, resume_write):
            os.close(fd)
