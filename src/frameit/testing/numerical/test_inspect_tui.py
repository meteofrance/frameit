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
    data["alpha"].attrs["units"] = "m s-1"
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
            assert all(app.query_one(selector).region.width > 0 for selector in (
                "#sources", "#fields", "#field-details", "#source-tabs"))
            assert table.ordered_columns[-1].content_width >= len("Not requested")
            assert "1 of 2 files inspected" in _text(app, "#source-scope")
            assert app.result_code == 0
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
            await pilot.press("slash", "q", "f", "s", "r", "3", "4")
            assert app.query_one("#field-search").value == "qfsr34"
            assert table.row_count == 0 and app.result_code == 0
            await pilot.press("escape", "3")
            assert "No field selected" in _text(app, "#field-details")
            app.copy_to_clipboard("unchanged")
            await pilot.press("c")
            assert app.clipboard == "unchanged"
            await pilot.press("q")
        assert app.return_value == 0

    asyncio.run(exercise())
    assert not (tmp_path / "not-created").exists()


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
                assert not app.query_one("#explorer").display
                assert "0 of 1" in _text(app, "#status") and "ETA" not in _text(app, "#status")
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
            assert all(str(table.get_row_at(row)[-1]) == "Unresolved" for row in (0, 1))
            await pilot.press("2", "down", "3", "c")
            assert not app.clipboard
            assert "No YAML selector" in _text(app, "#field-details")
            await pilot.press("q")
        assert app.return_value == 0

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
            await pilot.press("q")
        assert app.return_value == 1

    asyncio.run(exercise())
