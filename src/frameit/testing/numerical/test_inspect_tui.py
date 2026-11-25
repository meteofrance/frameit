"""Keyboard and read-only report behavior in the dataset explorer."""

import asyncio
from functools import partial
from threading import Event

import cftime
import numpy as np
import pytest
import yaml

from frameit.cli import _collect_report
from frameit.testing.numerical.test_inspect_metadata import _write_grib_vectors, v3_scene


def _case(root, sources):
    path = root / "config.yaml"
    path.write_text(yaml.safe_dump({
        "schema_version": 3, "sources": sources, "resources": {"cpus": 1},
        "output": {"directory": "not-created"},
    }, sort_keys=False))
    return path


def _text(app, selector):
    return str(app.query_one(selector).content)


def _app(path, collect=None):
    from frameit.inspect_tui import InspectionApp

    return InspectionApp(path, collect or partial(
        _collect_report, path, command="inspect", sample_only=True))


async def _ready(app, pilot):
    await app.workers.wait_for_complete()
    await pilot.pause()


def test_explorer_browses_and_copies_at_both_sizes(tmp_path):
    x = np.arange(21, dtype=float)
    data = v3_scene(names=("alpha", "middle", "zeta"), hours=(0,)).reindex(x=x).assign_coords(
        longitude=("x", 60. + x / 100, {"units": "degrees_east"}),
        time=[cftime.Datetime360Day(2001, 2, 30)])
    data["alpha"].attrs["units"] = "m s-1 " * 12
    data["zeta"].attrs["units"] = "Pa"
    data.to_netcdf(tmp_path / "sample.nc", engine="h5netcdf")
    (tmp_path / "later.nc").touch()
    v3_scene(names=("different",), hours=(0,)).to_netcdf(
        tmp_path / "other.nc", engine="h5netcdf")
    path = _case(tmp_path, {
        "atmosphere": {"files": ["sample.nc", "later.nc"], "variables": {"2d": ["zeta"]},
                       "time": {"values": ["2001-03-01T00:00:00"]}},
        "other": {"files": "other.nc"},
    })

    async def exercise():
        app = _app(path)
        async with app.run_test(size=(120, 30)) as pilot:
            await _ready(app, pilot)
            table = app.query_one("#fields")
            assert all(app.query_one(selector).is_on_screen for selector in (
                "#fields", "#field-details"))
            assert not app.query_one("#sources").is_on_screen
            assert not app.query_one("#source-tabs").display
            assert [str(col.label) for col in table.ordered_columns] == [
                "Name", "Group", "Units", "Request"]
            assert table.max_scroll_x == 0
            viewport = table.scrollable_size
            assert "1 of 2 files inspected" in _text(app, "#source-scope")
            assert app.result_code == 0
            await pilot.resize_terminal(150, 40)
            assert app.query_one("#sources").is_on_screen
            await pilot.resize_terminal(120, 30)
            await pilot.press("1", "down")
            assert app.focused.id == "sources"
            assert "other" in _text(app, "#source-scope")
            assert str(table.get_row_at(0)[0]) == "different"
            await pilot.press("up", "2", "s")
            assert app.focused.id == "fields"
            assert [str(table.get_row_at(i)[0]) for i in range(table.row_count)] == [
                "middle", "alpha", "zeta"]
            await pilot.press("tab")
            assert app.focused.id == "field-scroll"
            await pilot.press("f", "3", "c")
            assert table.row_count == 1
            assert table.max_scroll_x == 0
            assert table.scrollable_size == viewport
            assert yaml.safe_load(app.clipboard) == {"2d": ["zeta"]}
            assert "sources.atmosphere.variables" in _text(app, "#field-details")
            await pilot.resize_terminal(52, 16)
            await pilot.pause()
            assert app.query_one("#field-scroll").region.width > 0
            assert not app.query_one("#sources-pane").display
            assert not app.query_one("#variables-pane").display
            assert not app.query_one("#source-tabs").display
            keys = {key.key: key.region for key in app.query("FooterKey")}
            assert all(0 < keys[key].right <= 52 for key in ("r", "q"))
            assert "1 of 2 files inspected" in _text(app, "#source-scope")

            await pilot.press("escape", "enter")
            assert app.query_one("#field-scroll").has_focus
            assert table.max_scroll_x == 0
            assert _text(app, "#field-controls").startswith("1 of 3 fields")
            assert app.query_one("#field-evidence").collapsed
            assert "Identity:" not in _text(app, "#field-details")
            await pilot.press("4", "right", "right")
            tabs = app.query_one("#source-tabs")
            assert [pane.id for pane in tabs.query("TabPane")] == [
                "overview", "coordinates", "time", "grids", "files", "origins", "diagnostics"]
            assert tabs.active == "time"
            times = _text(app, "#source-time")
            assert "2001-02-30" in times and "360_day" in times
            assert "Not seen in sample" in times and "Requested time" in times
            await pilot.press("left")
            assert tabs.active == "coordinates"
            assert "omitted coordinate metadata" in _text(app, "#source-coordinates")
            tabs.active = "files"
            await pilot.pause()
            assert "Not inspected" in _text(app, "#source-files")
            assert "later.nc" in _text(app, "#source-files")

            await pilot.press("2")
            assert table.row_count == 1 and str(table.get_row_at(0)[0]) == "zeta"
            request_value = str(table.get_row_at(0)[3])
            await pilot.press("slash", "q", "f", "s", "r", "3", "4")
            assert app.query_one("#field-search").value == "qfsr34"
            assert table.row_count == 0 and app.result_code == 0
            assert any(key.key == "escape" and key.is_on_screen for key in app.query("FooterKey"))
            assert str(table.ordered_columns[3].label) == "Request"
            assert request_value == "Requested"
            await pilot.press("escape", "3")
            assert "No field selected" in _text(app, "#field-details")
            app.copy_to_clipboard("unchanged")
            await pilot.press("c")
            assert app.clipboard == "unchanged"
            await pilot.press("q")
        assert app.return_value == 0

    asyncio.run(exercise())
    assert not (tmp_path / "not-created").exists()


def test_explorer_shows_a_fitting_field_row_in_a_nine_row_terminal(tmp_path):
    data = v3_scene(names=("a",), hours=(0,)).isel(time=0, drop=True)
    data["a"].attrs["units"] = "K"
    data.to_netcdf(tmp_path / "sample.nc", engine="h5netcdf")
    path = _case(tmp_path, {"air": {"files": "sample.nc", "variables": {"2d": ["a"]}}})

    async def exercise():
        app = _app(path)
        async with app.run_test(size=(52, 9)) as pilot:
            await _ready(app, pilot)
            await pilot.press("2")
            table = app.query_one("#fields")
            assert table.row_count == 1 and table.max_scroll_x == 0
            assert table.scrollable_size.height > table.header_height
            assert app.query_one("#field-controls").display

    asyncio.run(exercise())


def test_search_reuses_unchanged_rows_and_only_builds_the_latest_query(tmp_path, monkeypatch):
    sample = tmp_path / "sample.nc"
    data = v3_scene(names=("pressure", "temperature"), hours=(0,))
    data.to_netcdf(sample, engine="h5netcdf")
    path = _case(tmp_path, {"air": {"files": "sample.nc"}})

    async def exercise():
        app = _app(path)
        async with app.run_test(size=(120, 36)) as pilot:
            await _ready(app, pilot)
            table = app.query_one("#fields")
            search = app.query_one("#field-search")
            cleared = []
            clear = table.clear

            def track_clear(*args, **kwargs):
                cleared.append(search.value)
                return clear(*args, **kwargs)

            monkeypatch.setattr(table, "clear", track_clear)
            assert table.row_count == 2
            for prefix in ("t", "te", "tem", "temp"):
                search.value = prefix
            await pilot.pause()
            assert cleared == ["temp"] and table.row_count == 1
            assert str(table.get_row_at(0)[0]) == "temperature"
            search.value = "temperature"
            await pilot.pause()
            assert cleared == ["temp"] and "1 of 2 fields" in _text(app, "#field-controls")
            assert "temperature" in _text(app, "#field-details")
            data["temperature"].attrs["units"] = "degC"
            data.to_netcdf(sample, engine="h5netcdf")
            await pilot.press("r")
            await _ready(app, pilot)
            assert str(table.get_row_at(0)[2]) == "degC"
            assert cleared == ["temp", "temperature"]

    asyncio.run(exercise())


def test_explorer_scrolls_source_picker_without_a_bar(tmp_path):
    from textual.events import MouseScrollDown

    v3_scene(hours=(0,)).to_netcdf(tmp_path / "sample.nc", engine="h5netcdf")
    path = _case(tmp_path, {f"source{i}": {"files": "sample.nc"} for i in range(12)})

    async def exercise():
        app = _app(path)
        async with app.run_test(size=(52, 16)) as pilot:
            await _ready(app, pilot)
            await pilot.press("1")
            sources = app.query_one("#sources")
            assert sources.max_scroll_y > 0
            assert sources.scrollbars_space == (0, 0)
            x, y = sources.content_region.offset
            app.post_message(MouseScrollDown(None, x, y, 0, 0, 0, False, False, False))
            await pilot.pause()
            assert sources.scroll_y > 0
            await pilot.press("end")
            assert "source11" in _text(app, "#source-scope")

    asyncio.run(exercise())


def test_explorer_refreshes_without_stale_selection(tmp_path):
    for filename, names in (("a.nc", ("a", "z")), ("b.nc", ("z",)), ("c.nc", ("a",))):
        v3_scene(names=names, hours=(0,)).to_netcdf(tmp_path / filename, engine="h5netcdf")
    path = _case(tmp_path, {"weather": {"files": "a.nc", "variables": {"2d": ["z"]}}})
    opened_second, release_second = Event(), Event()
    calls = 0

    def collect(*, progress):
        nonlocal calls
        calls += 1
        if calls == 2:
            progress("metadata", "weather", 0, 1)
            opened_second.set()
            assert release_second.wait(10)
        return _collect_report(path, command="inspect", progress=progress, sample_only=True)

    def save(filename):
        raw = yaml.safe_load(path.read_text())
        raw["sources"]["weather"]["files"] = filename
        path.write_text(yaml.safe_dump(raw))

    async def exercise():
        app = _app(path, collect)
        async with app.run_test(size=(52, 16)) as pilot:
            try:
                await _ready(app, pilot)
                await pilot.press("2", "f", "3", "c")
                assert yaml.safe_load(app.clipboard) == {"2d": ["z"]}
                save("b.nc")
                await pilot.press("r")
                assert await asyncio.to_thread(opened_second.wait, 5)
                await pilot.pause()
                assert app.query_one("#explorer").display
                assert "previous report" in _text(app, "#status")
                context = _text(app, "#operation-context")
                assert "0 of 1" in context and "ETA" not in context
                await pilot.press("r", "c")
                assert calls == 2
                release_second.set()
                await _ready(app, pilot)
                assert "b.nc" in _text(app, "#source-scope")
                assert "z" in _text(app, "#field-details")
                save("c.nc")
                await pilot.press("r")
                await _ready(app, pilot)
                assert "c.nc" in _text(app, "#source-scope")
                assert "No field selected" in _text(app, "#field-details")
                assert "Not seen in sample" in _text(app, "#source-overview")
                app.copy_to_clipboard("unchanged")
                await pilot.press("c")
                assert app.clipboard == "unchanged"
                await pilot.press("ctrl+c")
            finally:
                release_second.set()
        assert app.return_value == 130 and calls == 3

    asyncio.run(exercise())


def test_explorer_keeps_ambiguous_rows_without_copy(tmp_path):
    ec = pytest.importorskip("eccodes")
    _write_grib_vectors(ec, tmp_path / "winds.grib", [
        ("isobaricInhPa", 850, 1, 0, 131), ("isobaricInhPa", 850, 0, 600, 131),
    ])
    path = _case(tmp_path, {"atmosphere": {
        "model": "arome", "files": "winds.grib", "variables": {"3d": ["u"]},
    }})

    async def exercise():
        app = _app(path)
        async with app.run_test() as pilot:
            await _ready(app, pilot)
            table = app.query_one("#fields")
            assert table.row_count == 2
            rows = [table.get_row_at(row) for row in (0, 1)]
            assert [str(row[0]) for row in rows] == ["u", "u"]
            assert str(rows[0][1]) != str(rows[1][1])
            request_column = next(i for i, col in enumerate(table.ordered_columns)
                                  if str(col.label) == "Request")
            assert all(str(table.get_row_at(row)[request_column]) == "Unresolved"
                       for row in (0, 1))
            await pilot.press("2", "down", "3", "c")
            assert not app.clipboard
            assert "No YAML selector" in _text(app, "#field-details")
            await pilot.press("q")
        assert app.return_value == 0

    asyncio.run(exercise())


def test_explorer_copies_current_row_before_highlight_event_is_handled(tmp_path):
    v3_scene(names=("a", "z"), hours=(0,)).to_netcdf(tmp_path / "sample.nc", engine="h5netcdf")
    path = _case(tmp_path, {"weather": {"files": "sample.nc"}})

    async def exercise():
        app = _app(path)
        async with app.run_test() as pilot:
            await _ready(app, pilot)
            await pilot.press("2", "c")
            assert yaml.safe_load(app.clipboard) == {"2d": ["a"]}
            app.query_one("#fields").action_cursor_down()
            app.action_copy_selector()
            assert yaml.safe_load(app.clipboard) == {"2d": ["z"]}

    asyncio.run(exercise())


def test_draft_copies_qualified_selectors_without_applying_and_marks_stale_entries(tmp_path):
    ec = pytest.importorskip("eccodes")
    _write_grib_vectors(ec, tmp_path / "first.grib", [
        ("isobaricInhPa", 850, 1, 0, 131), ("hybrid", 1, 0, 0, 131),
        ("hybrid", 1, 0, 0, 132),
    ])
    _write_grib_vectors(ec, tmp_path / "later.grib", [("hybrid", 1, 0, 0, 132)])
    path = _case(tmp_path, {"weather": {"model": "arome", "files": "first.grib"}})
    original = path.read_bytes()

    async def exercise():
        app = _app(path)
        async with app.run_test(size=(80, 24)) as pilot:
            await _ready(app, pilot)
            await pilot.press("2", "a", "down", "a", "v")
            preview = _text(app.screen, "#draft-yaml")
            expected = {"sources": {"weather": {"variables": {"3d": {
                "hybrid": {"names": ["u"]}, "isobaric": {"names": ["u"]},
            }}}}}
            assert yaml.safe_load(preview) == expected
            await pilot.press("c", "escape")
            assert yaml.safe_load(app.clipboard) == expected
            assert path.read_bytes() == original
            assert "Not requested" in _text(app, "#field-details")
            await pilot.press("down", "a", "v")
            assert "Cannot combine" in _text(app.screen, "#draft-yaml")
            await pilot.press("c")
            assert yaml.safe_load(app.clipboard) == expected
            await pilot.press("end", "delete", "escape")
            updated = original.replace(b"first.grib", b"later.grib")
            path.write_bytes(updated)
            await pilot.press("r")
            await _ready(app, pilot)
            await pilot.press("v")
            assert "2 need review" in _text(app.screen, "#draft-status")
            assert "No current selectors" in _text(app.screen, "#draft-yaml")
            await pilot.press("c", "escape")
            assert yaml.safe_load(app.clipboard) == expected and path.read_bytes() == updated

    asyncio.run(exercise())


def test_draft_does_not_reuse_an_identical_field_from_a_different_model(tmp_path):
    for name, model in (("arome.nc", "AROME"), ("mnh.nc", "Meso-NH")):
        v3_scene(hours=(0,), model=model).to_netcdf(tmp_path / name, engine="h5netcdf")
    path = _case(tmp_path, {"weather": {"model": "arome", "files": "arome.nc"}})

    async def exercise():
        app = _app(path)
        async with app.run_test(size=(80, 24)) as pilot:
            await _ready(app, pilot)
            await pilot.press("2", "a", "v")
            assert "1 current" in _text(app.screen, "#draft-status")
            await pilot.press("escape")
            config = yaml.safe_load(path.read_text())
            config["sources"]["weather"].update(model="mesonh", files="mnh.nc")
            path.write_text(yaml.safe_dump(config))
            await pilot.press("r")
            await _ready(app, pilot)
            assert app.result_code == 0 and "MESONH" in _text(app, "#source-scope")
            await pilot.press("v")
            assert "1 need review" in _text(app.screen, "#draft-status")
            await pilot.press("c")
            assert app.clipboard == ""
            await pilot.press("escape", "a", "a", "v", "c")
            assert yaml.safe_load(app.clipboard) == {
                "sources": {"weather": {"variables": {"2d": ["temperature"]}}}}

    asyncio.run(exercise())


def test_explorer_reports_a_decoded_clock_without_field_rows(tmp_path):
    v3_scene(hours=(0, 1)).drop_vars("temperature").to_netcdf(
        tmp_path / "coordinates.nc", engine="h5netcdf")
    path = _case(tmp_path, {"weather": {"files": "coordinates.nc"}})

    async def exercise():
        app = _app(path)
        async with app.run_test(size=(52, 16)) as pilot:
            await _ready(app, pilot)
            assert app.query_one("#fields").row_count == 0
            await pilot.press("4", "right", "right")
            times = _text(app, "#source-time")
            assert "Timestamps (2)" in times and "2026-01-01T01:00:00" in times
            assert "No decoded sample clock" not in _text(app, "#finding")

    asyncio.run(exercise())


@pytest.mark.parametrize("replace", [False, True])
def test_refresh_resets_scroll_for_changed_fields(tmp_path, replace):
    names = ("b00",) if replace else (*[f"a{i:02d}" for i in range(20)], "z00")
    for filename, fields in (("first.nc", ("z00",)), ("updated.nc", names)):
        scene = v3_scene(names=fields, hours=(0,))
        scene[fields[-1]].attrs["description"] = "\n".join(f"Details {i}" for i in range(20))
        scene.to_netcdf(tmp_path / filename, engine="h5netcdf")
    path = _case(tmp_path, {"weather": {"files": "first.nc"}})

    async def exercise():
        app = _app(path)
        async with app.run_test(size=(52, 16)) as pilot:
            await _ready(app, pilot)
            table = app.query_one("#fields")
            detail = app.query_one("#field-scroll")
            if replace:
                await pilot.press("3", "tab", "enter", "end")
                await pilot.wait_for_scheduled_animations()
                offset = detail.scroll_offset
                assert offset.y > 0
                await pilot.press("r")
                await _ready(app, pilot)
                assert detail.scroll_offset == offset
            else:
                await pilot.press("2")
            path.write_text(path.read_text().replace("first.nc", "updated.nc"))
            await pilot.press("r")
            await _ready(app, pilot)
            if replace:
                assert _text(app, "#field-details").startswith("b00\n")
                assert detail.scroll_offset.y == 0
            else:
                assert str(table.get_row_at(table.cursor_row)[0]) == "z00"
                assert table.scroll_offset.y > 0

    asyncio.run(exercise())


@pytest.mark.parametrize("malformed", [False, True])
def test_explorer_diagnostics_leave_readable_sources(tmp_path, malformed):
    (tmp_path / "broken.nc").touch()
    v3_scene(hours=(0,)).to_netcdf(tmp_path / "good.nc", engine="h5netcdf")
    path = _case(tmp_path, {"bad": {"files": "broken.nc"}, "good": {"files": "good.nc"}})
    if malformed:
        path.write_text("sources: [\n")

    async def exercise():
        app = _app(path)
        async with app.run_test(size=(52, 16)) as pilot:
            await _ready(app, pilot)
            assert "Inspection" in _text(app, "#status")
            if malformed:
                assert app.focused.id == "finding-list"
                assert app.query_one("#finding-list").option_count == 1
                assert "E1102" in _text(app, "#finding")
            else:
                assert "good" in _text(app, "#source-scope")
                await pilot.press("2")
                assert app.query_one("#fields").row_count == 1
                assert "E1202" in _text(app, "#finding")
                await pilot.press("1", "up", "4")
                assert "Sample failed" in _text(app, "#source-files")
                assert "0 of 1 files inspected" in _text(app, "#source-scope")
                await pilot.press("d")
                assert app.query_one("#source-tabs").active == "diagnostics"
                assert app.focused.id == "finding-list"
            await pilot.press("q")
        assert app.return_value == 1

    asyncio.run(exercise())
