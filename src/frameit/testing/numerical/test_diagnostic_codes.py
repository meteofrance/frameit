"""Public diagnostic identifiers are independent of message text."""

import pytest

from frameit.core.reports import Diagnostic, PreflightResult, project_report, render_report


def test_code_paths_and_exception_identity():
    from frameit.utils.diagnostics import diagnostic_path, exception_code, tag_error

    error = ValueError("bad input")
    assert diagnostic_path("E0999") == "troubleshooting/start.html#e0999"
    assert tag_error(error, "E0999") is error
    assert tag_error(error, "E0999") is error
    assert type(error) is ValueError
    assert error.args == ("bad input",)
    assert len(error.__notes__) == 1

    root = tag_error(OSError("bad file"), "E0001")
    wrapped = ValueError("binding failed")
    wrapped.__cause__ = root
    assert exception_code(wrapped) == "E0001"


def test_equal_report_facts_with_distinct_codes_do_not_merge():
    def cause(code, file):
        return Diagnostic(
            "configuration", "bad input", "valid input", None, ["Check the file."],
            contexts=[{"file": file}], code=code,
        )

    result = PreflightResult("validate", errors=[
        cause("E0001", "one.yaml"),
        cause("E0999", "two.yaml"),
        cause("E0001", "three.yaml"),
    ])
    first, second = project_report(result)["errors"]
    assert (first["code"], second["code"]) == ("E0001", "E0999")
    assert first["contexts"] == [{"file": "one.yaml"}, {"file": "three.yaml"}]
    assert second["help"] == "troubleshooting/start.html#e0999"
    assert "[E0001]" in render_report(result)


def test_aggregate_error_record_keeps_each_cause():
    from frameit.core.reports import PreflightError, error_record

    original = PreflightError([
        Diagnostic("source.one", "missing file", "file", None, [], code="E0999"),
        Diagnostic("source.two", "bad argument", "argument", 42, [], code="E0001"),
    ])
    record = error_record(original)
    assert record["type"] == "PreflightError" and record["code"] == "E0999"
    assert [(item["path"], item["code"]) for item in record["diagnostics"]] == [
        ("source.one", "E0999"), ("source.two", "E0001"),
    ]
    assert "[E0001]" in str(original)


def test_wrapped_preflight_error_keeps_both_repairs():
    from frameit.cli import _failure_message
    from frameit.core.reports import PreflightError, error_record

    cause = PreflightError([
        Diagnostic("sources.air.files", "no matching file", "file", None, [], code="E1201"),
        Diagnostic("sources.sea", "unused source", "field", None, [], code="E1301"),
    ])
    wrapped = ValueError(f"Cannot bind source requests to metadata: {cause}")
    wrapped.__cause__ = cause

    record = error_record(wrapped)
    assert (record["type"], record["code"]) == ("ValueError", "E1201")
    assert [item["code"] for item in record["diagnostics"]] == ["E1201", "E1301"]
    display = _failure_message(wrapped)
    assert "Cannot bind source requests to metadata" in display
    assert "troubleshooting/inputs.html#e1201" in display
    assert "troubleshooting/fields.html#e1301" in display


def test_invalid_matrix_plan_leaves_no_run_directory(tmp_path, capsys, caplog):
    from frameit.cli import main

    output = tmp_path / "matrix"
    with pytest.raises(SystemExit) as exc:
        main(["run-matrix-test", "--ci", "--output", str(output),
              "--case", "no-such-matrix-case", "--plan-only"])
    assert exc.value.code == 2
    assert "[E1902]" in capsys.readouterr().err + caplog.text
    assert not output.exists()


def test_failed_qualification_keeps_the_check_with_its_summary_code(tmp_path, monkeypatch, capsys):
    from frameit.testing import polar_qualification

    monkeypatch.setattr(polar_qualification, "run_analytic_example", lambda _output: {
        "passed": False, "checks": [{"ok": False, "reason": "analytical limit exceeded"}],
    })
    assert polar_qualification.main(["--example", "--output", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "[E1903]" in output and "analytical limit exceeded" in output


def test_fixture_replacement_reports_retained_backup_without_failing(tmp_path, monkeypatch):
    from frameit.testing import datasets

    output, staging = tmp_path / "fixture", tmp_path / "staging"
    output.mkdir()
    staging.mkdir()
    (output / "previous").write_text("old fixture")
    (staging / "current").write_text("new fixture")

    def fail_to_remove(_path):
        raise PermissionError("test: no permission to remove backup")

    monkeypatch.setattr(datasets.shutil, "rmtree", fail_to_remove)
    warning, = datasets._publish(staging, output, force=True)
    assert (output / "current").read_text() == "new fixture"
    backup, = tmp_path.glob(".fixture.backup-*")
    assert (backup / "previous").read_text() == "old fixture"
    assert warning.startswith("[W1901]") and str(backup) in warning
