"""Public diagnostic identifiers are independent of message text."""

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
