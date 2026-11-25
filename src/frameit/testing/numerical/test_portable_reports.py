"""Export the recorded result and reopen it without the original request."""

import asyncio
import json

import pytest
from textual.widgets import Input

from frameit.cli import _collect_report, main
from frameit.core.reports import load_saved_report, project_report
from frameit.testing.numerical.test_validate_tui import _case, _text


@pytest.mark.parametrize("command", ["inspect", "validate"])
def test_save_canonical_report_exclusively_and_browse_it_offline(tmp_path, command):
    from frameit.inspect_tui import InspectionApp
    from frameit.validate_tui import ValidationApp

    app_type = InspectionApp if command == "inspect" else ValidationApp
    config = _case(tmp_path)
    data = tmp_path / "data/first-run.nc"
    original, payload = config.read_bytes(), data.read_bytes()
    archive = tmp_path / "recorded report.json"
    collected = []

    def collect(*, progress):
        result = _collect_report(config, command=command, progress=progress,
                                 sample_only=command == "inspect")
        collected.append(project_report(result))
        return result

    async def exercise():
        app = app_type(config, collect)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("w")
            for path in (config, data):
                app.screen.query_one("#export-path", Input).value = str(path)
                await pilot.press("enter")
                assert _text(app.screen, "#export-error")
            app.screen.query_one("#export-path", Input).value = str(archive)
            await pilot.press("enter")
            saved = archive.read_bytes()
            assert json.loads(saved) == collected[0] and len(collected) == 1
            await pilot.press("w")
            app.screen.query_one("#export-path", Input).value = str(archive)
            await pilot.press("enter")
            assert "already exists" in _text(app.screen, "#export-error").lower()
            await pilot.press("escape")
        assert config.read_bytes() == original and data.read_bytes() == payload
        assert archive.read_bytes() == saved

        # Leave the archive as the only available source of facts.
        config.unlink()
        data.unlink()
        recorded = load_saved_report(archive, command)

        def forbidden(**_):
            pytest.fail("A saved report invoked the live collector")

        viewer = app_type(archive, forbidden, saved_report=recorded)
        async with viewer.run_test(size=(80, 24)) as pilot:
            await pilot.press("r", "e")
            assert "Saved report" in _text(viewer, "#status")
            assert viewer.result_code == 0 and not list(viewer.workers)
            if command == "inspect":
                assert viewer.query_one("#fields").row_count == 1
            else:
                assert "frameit run" not in _text(viewer, "#summary")
                assert viewer.query_one("#plan-products").row_count == 1
            await pilot.press("q")

    asyncio.run(exercise())


def test_saved_report_cli_checks_version_shape_and_literal_data(tmp_path, monkeypatch, capsys):
    from frameit import cli

    config = _case(tmp_path)
    report = project_report(_collect_report(config, command="validate", schema_only=True))
    archive = tmp_path / "report.json"

    def forbidden(*args, **kwargs):
        pytest.fail("Reopening JSON loaded a request")

    monkeypatch.setattr(cli, "_load_config", forbidden)
    for invalid, message in (
            ({**report, "report_version": 9}, "Unsupported report version"),
            ({**report, "data": {}}, "Incomplete report data"),
            ({**report, "deferred_checks": []}, "Inconsistent recorded checks"),
            ({**report, "deferred_checks": [], "data": {**report["data"], "pending": []}},
             "Missing recorded validation scope"),
            ({**report, "warnings": ["\x1b]52;bad"]}, "control characters")):
        archive.write_text(json.dumps(invalid))
        with pytest.raises(SystemExit) as outcome:
            main(["validate", "--saved-report", str(archive), "--json"])
        assert outcome.value.code == 1
        assert message in capsys.readouterr().err
    report["warnings"].append("[bold reverse]not markup\r\nordinary CRLF")
    archive.write_text(json.dumps(report))
    with pytest.raises(SystemExit) as outcome:
        main(["validate", "--saved-report", str(archive), "--json"])
    assert outcome.value.code == 0
    assert json.loads(capsys.readouterr().out) == report


def test_saved_report_rejects_malformed_context_before_navigation(tmp_path):
    config = _case(tmp_path)
    config.write_text(config.read_text().replace("data/first-run.nc", "absent.nc"))
    report = project_report(_collect_report(config, command="validate"))
    invalid = {**report["errors"][0], "contexts": [{"source": ["atmosphere"]}]}
    report["errors"].append(invalid)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Invalid diagnostic context"):
        load_saved_report(path, "validate")


def test_saved_report_rejects_incomplete_binding_before_navigation(tmp_path):
    config = _case(tmp_path)
    report = project_report(_collect_report(config, command="validate"))
    source = report["data"]["plan"]["sources"]["atmosphere"]
    source["field_binding"]["products"]["model_grid"]["instructional_scalar"]["records"] = [{}]
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Invalid bound-field record"):
        load_saved_report(path, "validate")


def test_archive_rejects_incomplete_native_metadata_before_field_is_opened(tmp_path):
    config = _case(tmp_path)
    report = project_report(_collect_report(config, command="inspect", sample_only=True))
    fields = report["data"]["plan"]["sources"]["atmosphere"]["fields"]
    next(iter(fields.values()))["native_descriptor"] = {"native": ["not metadata"]}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Invalid field metadata"):
        load_saved_report(path, "inspect")


def test_inspect_view_reopens_full_cli_inventory(tmp_path, capsys):
    from frameit.inspect_tui import InspectionApp

    config = _case(tmp_path)
    archive = tmp_path / "inventory.json"
    with pytest.raises(SystemExit) as outcome:
        main(["inspect", str(config), "--json"])
    assert outcome.value.code == 0
    archive.write_text(capsys.readouterr().out)
    report = load_saved_report(archive, "inspect")

    async def exercise():
        app = InspectionApp(archive, None, saved_report=report)
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.result_code == 0 and app.query_one("#fields").row_count == 1
            await pilot.press("4")
            app.query_one("#source-tabs").active = "files"
            await pilot.pause()
            assert "Selected · first-run.nc" in _text(app, "#source-files")
            assert "Inspected sample" not in _text(app, "#source-files")

    asyncio.run(exercise())


@pytest.mark.parametrize("command", ["inspect", "validate"])
def test_saved_report_refuses_an_explicit_frameit_yaml(command, tmp_path, capsys):
    config = _case(tmp_path)
    archive = tmp_path / "archive.json"
    report = project_report(_collect_report(config, command=command, sample_only=True))
    archive.write_text(json.dumps(report))
    with pytest.raises(SystemExit) as outcome:
        main([command, "frameit.yaml", "--saved-report", str(archive), "--json"])
    captured = capsys.readouterr()
    assert outcome.value.code != 0
    assert "without a YAML request" in captured.err
