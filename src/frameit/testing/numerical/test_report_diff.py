"""Check comparison summaries against independent recorded source facts."""

from frameit.core.reports import Diagnostic, PreflightResult, project_report
from frameit.report_diff import report_changes


def test_comparison_keeps_structured_file_context_in_finding_identity():
    def report(file, *, reverse=False):
        contexts = [{"source": "air", "file": file}, {"source": "air", "field": "temperature"}]
        item = Diagnostic("sources.air.time", "Invalid clock", None, None, [],
                          code="E1401", contexts=contexts[::-1] if reverse else contexts)
        return project_report(PreflightResult("validate", errors=[item]))

    old = report("/owned/run/a.nc")
    reordered = report("/owned/run/a.nc", reverse=True)
    replaced = report("/owned/run/b.nc")
    assert any("Still reported: 1" in label for label, _ in report_changes(old, reordered))
    labels = [label for label, _ in report_changes(old, replaced)]
    assert any(label.startswith("Newly reported") and "b.nc" in label for label in labels)
    assert any(label.startswith("No longer reported") and "a.nc" in label for label in labels)
    assert not any("Still reported" in label for label in labels)


def test_comparison_does_not_treat_unqualified_timestamps_as_the_same_calendar():
    def report(calendar):
        time = "2024-01-01T00:00:00"
        source = {"model": "nemo", "format": "netcdf", "physical_type": "ocean",
                  "files": ["sea.nc"], "selected_times": [time],
                  "records": [{"time": time, "calendar": calendar}]}
        return project_report(PreflightResult("validate", facts={"sources": {"sea": source}}))

    changes = report_changes(report("standard"), report("proleptic_gregorian"))
    assert any("Time bounds not compared" in label and "standard → proleptic_gregorian" in label
               and target == ("source", "sea") for label, target in changes)


def test_comparison_does_not_report_newly_resolved_details_as_setting_edits():
    before = PreflightResult("validate", facts={"configuration": {
        "output": {"directory": "/prior", "writer": {}}, "resources": {"cpus": None},
    }}, errors=[Diagnostic("sources.air.files", "No file", None, None, [], code="E1201")])
    after = PreflightResult("validate", facts={"configuration": {
        "output": {"directory": "/new", "writer": {"engine": "netcdf4"}},
        "resources": {"cpus": 4},
    }})
    labels = {label for label, _ in report_changes(*map(project_report, (before, after)))}
    assert "Effective setting changed: output.directory" in labels
    assert "Effective setting changed: resources" not in labels
    assert "Effective setting changed: output" not in labels
