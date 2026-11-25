import json
import subprocess
import sys

import pytest
import yaml

from frameit.core.configuration import read_yaml, resolve_schema
from frameit.core.reports import PreflightError, error_record


def request(*, kind="model_grid"):
    return {
        "schema_version": 3,
        "sources": {"weather": {"model": "arome", "files": "input.nc",
                                "variables": {"2d": ["instructional_scalar"]}}},
        "diagnostics": {"best_track": {
            "agency_template": "RSMC",
            "input": {"kind": kind, "source": "weather"},
            "fields": {"wind": {"speed": "wind10"}, "sea_level_pressure": "mslp"},
            "search": {"pressure_radius_km": 20, "maximum_wind_radius_km": 40,
                       "wind_radii_radius_km": 80},
            "rmw": {"method": "annular_mean_speed", "radius_km": 30, "bin_width_km": 10},
        }},
    }


def test_empty_and_catalog_are_lightweight(tmp_path):
    raw = request(kind="original")
    configured, bound, _ = resolve_schema(raw, base_dir=tmp_path)
    del raw["diagnostics"]
    omitted, unconfigured, _ = resolve_schema(raw, base_dir=tmp_path)
    explicit, _, _ = resolve_schema({**raw, "diagnostics": {}}, base_dir=tmp_path)
    assert omitted["diagnostics"] == explicit["diagnostics"] == {}
    assert configured["diagnostics"]["best_track"]["fields"]["wind"] == {"speed": "wind10"}
    assert bound == unconfigured

    path = tmp_path / "request.yaml"
    path.write_text(yaml.safe_dump(request()), encoding="utf-8")
    program = """
import contextlib, io, json, sys
from frameit.cli import main

def run(*args):
    with contextlib.redirect_stdout(io.StringIO()) as stream:
        try:
            main(list(args))
        except SystemExit as exc:
            assert exc.code == 0
    return json.loads(stream.getvalue())

print(json.dumps(run("capabilities", "--json")["data"]["plan"]["capabilities"]["diagnostics"]))
report = run("validate", sys.argv[1], "--schema-only", "--cli", "--json")
assert not report["errors"]
assert any(item["path"] == "diagnostics.best_track" for item in report["deferred_checks"])
assert not {"frameit.diagnostics.sources", "frameit.diagnostics.best_track",
            "frameit.core.metadata_catalogue", "zarr", "epygram", "eccodes"} & sys.modules.keys()
"""
    proc = subprocess.run(
        [sys.executable, "-c", program, str(path)], capture_output=True, text=True, check=True,
    )
    catalog = json.loads(proc.stdout)
    assert list(catalog) == ["best_track"]
    assert catalog["best_track"]["maturity"] == "experimental"


@pytest.mark.parametrize(("parts", "value", "suffix"), [
    ((), None, ""),
    (("best_track",), "on", ".best_track"),
    (("best_track", "enabled"), True, ".best_track.enabled"),
    (("best_track", "input", "kind"), "auto", ".best_track.input.kind"),
    (("best_track", "agency_template"), "JTWC", ".best_track.agency_template"),
    (("best_track", "fields", "wind"), {"speed": "x", "u": "u", "v": "v"}, ".best_track.fields.wind"),
    (("best_track", "fields", "sea_level_pressure"), {"field": "p", "group": "s"},
     ".best_track.fields.sea_level_pressure.group"),
    (("best_track", "fields", "sea_level_pressure"), {"field": "p", "level": {"value": True}},
     ".best_track.fields.sea_level_pressure.level.units"),
    (("best_track", "search", "pressure_radius_km"), 80, ".best_track.search"),
    (("best_track", "rmw", "bin_width_km"), 11, ".best_track.rmw.bin_width_km"),
    (("best_track", "processing"), {"max_open_files": True}, ".best_track.processing.max_open_files"),
])
def test_invalid_diagnostic_path(parts, value, suffix):
    raw = request()
    parent = raw
    chain = ("diagnostics", *parts)
    for key in chain[:-1]:
        parent = parent[key]
    parent[chain[-1]] = value
    with pytest.raises(PreflightError) as error:
        resolve_schema(raw)
    issue = error_record(error.value)["diagnostics"][0]
    assert issue["path"] == f"diagnostics{suffix}"
    assert issue["code"] == "E2001"
    assert issue["help"] == "troubleshooting/diagnostics.html#e2001"


def test_duplicate_yaml_still_reports_authored_path(tmp_path):
    path = tmp_path / "request.yaml"
    path.write_text("diagnostics:\n  best_track:\n    fields: {}\n    fields: {}\n")
    with pytest.raises(PreflightError) as error:
        read_yaml(path)
    issue = error_record(error.value)["diagnostics"][0]
    assert (issue["code"], issue["path"]) == ("E1103", "diagnostics.best_track.fields")
    assert issue["locations"][0]["line"] == 4


def test_defaults_and_advisory(tmp_path):
    from frameit.cli import _collect_report
    from frameit.core.reports import project_report
    from frameit.testing.documentation_example import create_first_run_input

    create_first_run_input(tmp_path / "input.nc")
    path = tmp_path / "request.yaml"
    path.write_text(yaml.safe_dump(request()), encoding="utf-8")
    report = project_report(_collect_report(path, command="validate"))
    assert report["status"] == "ok", report["errors"]
    assert any("W2001" in item and "wind10" in item for item in report["warnings"])
    assert report["data"]["plan"]["products"][0]["fields"] == ["instructional_scalar"]
    best = report["data"]["configuration"]["diagnostics"]["best_track"]
    assert best["rmw"]["azimuth_sectors"] == 12
    assert (best["wind_time_policy"], best["on_unavailable"]) == ("require_10min", "report")
    assert best["processing"] == {"working_memory_mib": 256, "max_open_files": 4}
