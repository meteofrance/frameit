"""C9 reports on compact metadata, not scientific or native qualification."""

import importlib.util
import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import yaml

from frameit.core import preflight
from frameit.testing.numerical.test_inspect_metadata import (
    guard_netcdf_payloads,
    v3_scene,
)


def collect(request, **kwargs):
    assert callable(getattr(preflight, "collect_preflight", None)), "shared collector is missing"
    return preflight.collect_preflight(request, **kwargs)


def project(result):
    from frameit.core.reports import project_report

    report = project_report(result)
    assert set(report) == {
        "report_version", "command", "status", "data", "warnings", "errors", "deferred_checks",
    }
    assert report["report_version"] == 1
    assert set(report["data"]) == {"configuration", "origins", "inputs", "plan", "pending"}
    json.dumps(report, allow_nan=False)
    return report


def request(tmp_path, sources):
    return {
        "schema_version": 3, "sources": sources,
        "output": {"directory": str(tmp_path / "output")},
        "resources": {"cpus": 1},
    }


def test_independent_file_causes_keep_locations_and_valid_source_metadata(tmp_path, monkeypatch):
    (tmp_path / "bad.bin").write_bytes(b"not data")
    v3_scene().assign_coords(time=[0., 1., 2., 3.]).to_netcdf(
        tmp_path / "clock.nc", engine="h5netcdf")
    v3_scene().to_netcdf(tmp_path / "good.nc", engine="h5netcdf")
    document = tmp_path / "request.yaml"
    document.write_text(
        "schema_version: 3\nsources:\n"
        "  broken:\n    files: bad.bin\n    variables: {2d: [temperature]}\n"
        "  clock:\n    files: clock.nc\n    variables: {2d: [temperature]}\n"
        "  good:\n    files: good.nc\n    variables: {2d: [temperature]}\n"
        "resources: {cpus: 1}\n",
    )
    guard_netcdf_payloads(monkeypatch, {"temperature"})
    result = collect(document, check_output=False)
    report = project(result)
    assert report["status"] == "error"
    assert len(report["errors"]) == 2
    errors = {error["path"]: error for error in report["errors"]}
    broken = errors["sources.broken.files"]
    assert broken["observed"] == {"magic_hex": b"not data".hex()}
    assert "netcdf" in broken["expected"]["formats"]
    assert broken["locations"] == [
        {"file": str(document), "line": 4, "column": 5},
    ]
    clock = errors["sources.clock.files"]
    assert clock["expected"] == {"clock": "decoded timestamps"}
    assert clock["observed"] == {"clock": "time", "dtype": "float64"}
    assert clock["locations"][0]["line"] == 7
    for error in errors.values():
        assert error["message"] and error["repairs"]
        assert all(isinstance(repair, str) for repair in error["repairs"])
        assert error["contexts"][0]["source"] in {"broken", "clock"}
        assert Path(error["contexts"][0]["file"]).is_file()
    assert set(report["data"]["plan"]["sources"]) == {"good"}
    assert result.facts["sources"]["good"]["requests"]["binding"] is None
    assert report["data"]["plan"].get("planned_products") in (None, [])
    blocked = [check for check in report["deferred_checks"] if check["status"] == "blocked"]
    assert blocked and any(
        set(check["prerequisites"]) == {"sources.broken.files", "sources.clock.files"}
        for check in blocked
    )
    assert not (tmp_path / "output").exists()


def test_genuine_repeats_group_without_losing_files_or_distinct_observations(tmp_path):
    for name, contents in (("one", b"badbytes"), ("two", b"badbytes"), ("three", b"different")):
        (tmp_path / name).write_bytes(contents)
    result = collect(request(tmp_path, {"weather": {
        "files": [str(tmp_path / name) for name in ("one", "two", "three")],
    }}), check_output=False)
    report = project(result)
    assert report["status"] == "error"
    assert len(report["errors"]) == 2
    repeated = next(error for error in report["errors"] if len(error["contexts"]) == 2)
    assert {Path(context["file"]).name for context in repeated["contexts"]} == {"one", "two"}
    assert repeated["locations"] == []
    assert repeated["repairs"] and len(set(repeated["repairs"])) == len(repeated["repairs"])
    assert {error["observed"]["magic_hex"] for error in report["errors"]} == {
        b"badbytes".hex(), b"differen".hex(),
    }


def test_independent_source_schema_failures_are_not_executable_partial_controls(tmp_path):
    result = collect(request(tmp_path, {
        "weather": {"files": "absent.nc", "model": "guess"},
        "ocean": {"files": "absent.nc", "format": "guess"},
    }), schema_only=True)
    report = project(result)
    assert report["status"] == "error"
    assert {error["path"] for error in report["errors"]} == {
        "sources.weather.model", "sources.ocean.format",
    }
    for error in report["errors"]:
        assert error["observed"] == "guess"
        assert isinstance(error["expected"], list) and "guess" not in error["expected"]
        assert error["repairs"] and error["locations"] == []
    assert report["data"]["configuration"] is None
    assert report["data"]["inputs"] == []
    assert report["data"]["plan"] == {}
    assert result.conf is None


def test_yaml_marks_are_captured_from_the_loaded_text_once(tmp_path, monkeypatch):
    document = tmp_path / "request.yaml"
    document.write_text("schema_version: 3\nsources:\n  a:\n    files: missing.nc\n")
    original = Path.read_text
    reads = []

    def changing_text(path, *args, **kwargs):
        if path == document:
            reads.append(path)
            if len(reads) > 1:
                return "schema_version: 4\n"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", changing_text)
    report = project(collect(document, check_output=False))
    assert len(reads) == 1
    error, = report["errors"]
    assert error["path"] == "sources.a.files"
    assert error["locations"] == [{"file": str(document), "line": 4, "column": 5}]
    assert "missing.nc" in yaml.safe_dump(error)


def test_unfinished_inspection_lists_copyable_selectors_without_binding(tmp_path, monkeypatch):
    scene = v3_scene(names=("temperature", "u"))
    scene["profile"] = (
        ("time", "level", "y", "x"), np.ones((4, 2, 2, 3)), {"units": "K"})
    scene = scene.assign_coords(level=("level", [1000., 900.], {"units": "hPa", "axis": "Z"}))
    scene.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = request(tmp_path, {"weather": {"files": str(tmp_path / "input.nc")}})
    guard_netcdf_payloads(monkeypatch, {"temperature", "u", "profile"})
    result = collect(raw, command="inspect")
    report = project(result)
    assert report["status"] == "ok"
    source = report["data"]["plan"]["sources"]["weather"]
    assert source["requests"]["binding"] is None
    selectors = {item["field"]: item["variables"] for item in source["available_selectors"]}
    assert selectors == {
        "temperature": {"2d": ["temperature"]}, "u": {"2d": ["u"]},
        "profile": {"3d": ["profile"]},
    }
    assert any(check["status"] == "unfinished-selection" for check in report["deferred_checks"])
    from frameit.core.configuration import to_runtime
    from frameit.core.coupled import bind_sources
    from frameit.core.settings_class import SimulationConfig

    for name, variables in selectors.items():
        chosen = deepcopy(raw)
        chosen["sources"]["weather"]["variables"] = variables
        conf = SimulationConfig(**to_runtime(chosen))
        _, children, _ = bind_sources(conf)
        binding = children["weather"].source_requests["weather"]["binding"]
        assert set(binding["products"]["model_grid"]) == {name}
    validation = project(collect(raw))
    assert validation["status"] == "error"
    assert "select" in validation["errors"][0]["repairs"][0].lower()


def test_inspection_without_a_clock_retains_observed_fields_not_phantom_times(tmp_path):
    v3_scene().isel(time=0, drop=True).to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    result = collect(request(tmp_path, {"weather": {"files": str(tmp_path / "input.nc")}}),
                     command="inspect")
    report = project(result)
    assert report["status"] == "ok"
    source = report["data"]["plan"]["sources"]["weather"]
    assert source["selected_times"] == [] and source["records"] == []
    assert {field["name"] for field in source["fields"].values()} == {"temperature"}
    assert any("clock" in check["message"] for check in report["deferred_checks"])


def test_ambiguous_inspection_never_offers_unsupported_qualified_selectors(tmp_path):
    v3_scene().to_netcdf(tmp_path / "one.nc", engine="h5netcdf")
    v3_scene().assign_coords(x=[4., 5., 6.]).to_netcdf(
        tmp_path / "two.nc", engine="h5netcdf")
    report = project(collect(request(tmp_path, {"weather": {
        "files": str(tmp_path / "*.nc"),
    }}), command="inspect"))
    assert report["status"] == "ok"
    source = report["data"]["plan"]["sources"]["weather"]
    assert source["available_selectors"] == []
    pending = report["deferred_checks"]
    assert any("temperature" in check["message"] and "files" in check["message"]
               for check in pending)
    assert all("::" not in yaml.safe_dump(item) for item in source["available_selectors"])


def test_decoded_calendar_and_numpy_metadata_are_projected_without_mutating_axes(
        tmp_path, monkeypatch):
    import cftime

    scene = v3_scene(hours=(0, 1)).assign_coords(
        time=[cftime.Datetime360Day(2001, 2, 30), cftime.Datetime360Day(2001, 3, 1)])
    scene.temperature.attrs["valid_range"] = np.array([0., 400.], dtype="float32")
    scene.temperature.attrs["missing_value"] = np.float32(np.nan)
    scene.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    guard_netcdf_payloads(monkeypatch, {"temperature"})
    result = collect(request(tmp_path, {"weather": {
        "files": str(tmp_path / "input.nc"), "variables": {"2d": ["temperature"]},
    }}))
    before = result.facts["sources"]["weather"]["selected_times"]
    assert isinstance(before[0], cftime.Datetime360Day)
    report = project(result)
    assert report["status"] == "ok"
    public = report["data"]["plan"]["sources"]["weather"]
    assert public["selected_times"][0] == {"label": "2001-02-30 00:00:00", "calendar": "360_day"}
    assert public["records"][0]["calendar"] == "360_day"
    field, = public["fields"].values()
    assert field["attributes"]["valid_range"] == [0., 400.]
    assert result.facts["sources"]["weather"]["selected_times"] is before
    assert before[0].day == 30
    assert result.conf.schema_sources["sources.weather.variables.2d"] == "yaml"


def test_only_selected_features_require_dependencies(tmp_path, monkeypatch):
    from frameit.core.coupled import prepare_sources
    from frameit.core.settings_class import SimulationConfig

    v3_scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = request(tmp_path, {"weather": {
        "files": str(tmp_path / "input.nc"), "variables": {"2d": ["temperature"]},
    }})
    original = importlib.util.find_spec
    queried = []

    def missing_optional(name, *args, **kwargs):
        queried.append(name)
        return None if name in {"xesmf", "torch", "utrack"} else original(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", missing_optional)
    native = project(collect(raw))
    assert native["status"] == "ok"
    assert not {"xesmf", "torch", "utrack"} & set(queried)
    raw["region"] = {"center": {"latitude": -20., "longitude": 60.}}
    raw["products"] = {"polar": {"radius_km": 2., "radial_step_km": 1.}}
    report = project(collect(raw))
    assert report["status"] == "error"
    error, = report["errors"]
    assert error["path"] == "products.polar"
    assert error["expected"] == {"module": "xesmf", "available": True}
    assert error["observed"] == {"module": "xesmf", "available": False}
    with pytest.raises(ValueError, match="xesmf"):
        prepare_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not (tmp_path / "output").exists()


def test_offline_schema_only_never_opens_inputs_or_probes_optional_backends(tmp_path, monkeypatch):
    from frameit.io.loader import DatasetResources

    def forbidden(*args, **kwargs):
        pytest.fail("offline schema-only inspected a dataset or probed a backend")

    monkeypatch.setattr(DatasetResources, "open_netcdf", forbidden)
    monkeypatch.setattr(importlib.util, "find_spec", forbidden)
    raw = request(tmp_path, {"weather": {
        "model": "arome", "format": "fa", "profile": "arome_history", "files": "absent.fa",
    }})
    report = project(collect(raw, schema_only=True))
    assert report["status"] == "ok" and not report["errors"]
    assert report["data"]["inputs"] == [] and report["data"]["plan"] == {}
    assert report["data"]["configuration"]["sources"]["weather"]["format"] == "fa"
    assert any("dependenc" in item["message"] for item in report["deferred_checks"])


@pytest.mark.parametrize("body,path,observed,line", [
    ("schema_version: true\nsources: {}\n", "schema_version", True, 1),
    ("schema_version: 3\nsources:\n  a:\n    files: null\n",
     "sources.a.files", None, 4),
    ("schema_version: 3\nsources:\n  a:\n    files: one\n    files: two\n",
     "sources.a.files", {"key": "files"}, 5),
    ("schema_version: 3\nsources: {}\nmisspelled: true\n",
     "misspelled", "misspelled", 3),
    ("schema_version: 3\nsources:\n  a:\n    1: input.nc\n",
     "sources.a.1", 1, 4),
    ("[]\n", "configuration", [], 1),
])
def test_schema_failure_diagnostics_retain_actual_facts_and_marks(
        tmp_path, body, path, observed, line):
    document = tmp_path / "request.yaml"
    document.write_text(body)
    report = project(collect(document, schema_only=True))
    assert report["status"] == "error"
    error, = report["errors"]
    assert error["path"] == path
    assert error["observed"] == observed
    assert error["expected"] is not None and error["repairs"]
    assert error["locations"][0]["line"] == line
    assert report["data"]["configuration"] is None


@pytest.mark.parametrize("case", [
    "metadata_ok", "metadata_error", "schema_only", "version_error", "syntax_error", "missing_yaml",
])
def test_actual_validate_cli_emits_one_json_document_and_nonzero_errors(tmp_path, case):
    document = tmp_path / "request.yaml"
    v3_scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = request(tmp_path, {"weather": {
        "model": "mesonh", "files": str(tmp_path / "input.nc"),
        "variables": {"2d": ["temperature"]},
    }})
    if case == "metadata_error":
        (tmp_path / "input.nc").unlink()
        (tmp_path / "input.nc").write_bytes(b"badbytes")
    if case == "version_error":
        raw["schema_version"] = True
    document.write_text(yaml.safe_dump(raw, sort_keys=False))
    if case == "syntax_error":
        document.write_text("schema_version: 3\nsources: [\n")
    if case == "missing_yaml":
        document.unlink()
    options = ["--schema-only"] if case == "schema_only" else []
    process = subprocess.run(
        [sys.executable, "-m", "frameit", "validate", str(document), "--json", *options],
        capture_output=True, text=True, timeout=30, env=os.environ.copy(), check=False,
    )
    assert process.stdout.strip().startswith("{"), process.stderr
    report = json.loads(process.stdout)
    assert set(report) == {
        "report_version", "command", "status", "data", "warnings", "errors", "deferred_checks",
    }
    assert report["command"] == "validate"
    failure = case.endswith("error") or case == "missing_yaml"
    assert (process.returncode != 0) == failure
    assert report["status"] == ("error" if failure else "ok")
    assert bool(report["errors"]) == failure
    assert "INFO:" not in process.stdout and "WARNING:" not in process.stdout
    if case == "metadata_ok":
        assert "INFO:" in process.stderr
        source = report["data"]["plan"]["sources"]["weather"]
        assert {field["name"] for field in source["fields"].values()} == {"temperature"}
        assert source["records"][0]["calendar"]
    if case == "schema_only":
        assert report["data"]["inputs"] == []
        assert report["deferred_checks"]
    if case == "syntax_error":
        assert report["errors"][0]["locations"][0]["file"] == str(document)
        assert report["errors"][0]["locations"][0]["line"] >= 2


def test_readable_human_report_exposes_same_facts_and_repairs(tmp_path):
    from frameit.core import reports

    v3_scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = request(tmp_path, {"weather": {
        "files": str(tmp_path / "input.nc"), "variables": {"2d": ["temperature"]},
    }})
    result = collect(raw)
    assert callable(getattr(reports, "render_report", None)), "shared human renderer is missing"
    text = reports.render_report(result)
    for fact in ("OK", "weather", "temperature", "2026-01-01", "K", "cpu_budget", "input.nc",
                 "products/analysis.weather.model_grid.nc", "default", "Pending"):
        assert fact in text
    (tmp_path / "input.nc").unlink()
    failed = collect(raw)
    report = project(failed)
    text = reports.render_report(failed)
    assert "ERROR" in text and "blocked" in text
    for error in report["errors"]:
        assert error["path"] in text and error["message"] in text
        assert all(repair in text for repair in error["repairs"])
    assert "{'source':" not in text and "{'files':" not in text


def test_bound_polar_projection_remains_metadata_only_and_keeps_typed_plan(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_v3_polar import configuration, scene

    scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    guard_netcdf_payloads(monkeypatch, {"q"})
    conf = configuration(tmp_path)
    result = collect(conf)
    report = project(result)
    assert report["status"] == "ok"
    assert report["data"]["plan"]["sources"]["atmosphere"]["field_binding"]["status"] == "bound"
    product, = report["data"]["plan"]["products"]
    assert product["dimensions"] == {"q": ["time", "radius", "azimuth"]}
    assert product["units"] == {"q": "K"} and product["stored_names"] == {"q": "q"}
    record = result.facts["sources"]["atmosphere"]["records"][0]
    assert isinstance(record["time"], np.datetime64)
    assert result.conf.source_requests["atmosphere"]["binding"]["status"] == "bound"
    assert not conf.output_dir.exists()


def test_projection_bounds_geometry_and_preserves_non_json_annotations(tmp_path):
    from frameit.testing.numerical.test_v3_polar import configuration, scene

    scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    conf = configuration(tmp_path, products={"model_grid": True})
    conf.yaml_config["metadata"]["extra"] = {
        "day": date(2026, 1, 1), "bytes": b"\x00\xff", "unmeasured": None,
    }
    result = collect(conf)
    report = project(result)
    extra = report["data"]["configuration"]["metadata"]["extra"]
    assert extra == {"day": "2026-01-01", "bytes": {"hex": "00ff"}, "unmeasured": None}
    grid, = report["data"]["plan"]["sources"]["atmosphere"]["native_grids"].values()
    assert grid["coordinates"]["latitude"]["values"]["shape"] == [9, 9]
    assert result.facts["sources"]["atmosphere"]["native_grids"][
        next(iter(result.facts["sources"]["atmosphere"]["native_grids"]))
    ]["coordinates"]["latitude"]["values"].shape == (9, 9)
    assert any(key.startswith("inputs.sources.atmosphere.") for key in report["data"]["origins"])


def test_missing_selected_fields_and_model_conflicts_keep_actual_metadata_facts(tmp_path):
    v3_scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = request(tmp_path, {"weather": {
        "files": str(tmp_path / "input.nc"), "variables": {"2d": ["missing"]},
    }})
    report = project(collect(raw))
    error, = report["errors"]
    assert error["path"] == "sources.weather.variables"
    assert error["expected"] == {"required_fields": ["missing"]}
    assert error["observed"]["available_fields"] == ["temperature"]
    raw["sources"]["weather"] = {"files": str(tmp_path / "input.nc"), "model": "nemo"}
    report = project(collect(raw))
    error, = report["errors"]
    assert error["path"] == "sources.weather.model"
    assert error["expected"] == {"model": "nemo"}
    assert error["observed"]["models"] == ["mesonh"]
    assert error["repairs"]


def test_unavailable_reader_reports_selected_dependency_not_an_unrelated_backend(
        tmp_path, monkeypatch):
    v3_scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    original = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **kw: (
        None if name == "h5netcdf" else original(name, *a, **kw)))
    report = project(collect(request(tmp_path, {"weather": {
        "files": str(tmp_path / "input.nc"), "variables": {"2d": ["temperature"]},
    }})))
    assert report["status"] == "error"
    error, = report["errors"]
    assert error["path"] == "sources.weather.reader.engine"
    assert error["observed"] == {"module": "h5netcdf", "available": False}
    assert error["expected"] == {"module": "h5netcdf", "available": True}


def test_independent_binding_errors_are_collected_and_all_clearance_revoked(tmp_path, monkeypatch):
    from frameit.core import coupled
    from frameit.core.reports import PreflightError
    from frameit.core.settings_class import SimulationConfig

    v3_scene().to_netcdf(tmp_path / "weather.nc", engine="h5netcdf")
    ocean = v3_scene(model="NEMO").rename(time="time_counter").drop_vars(["latitude", "longitude"])
    ocean = ocean.assign_coords(
        nav_lat=(("y", "x"), np.broadcast_to([[-20.], [-19.99]], (2, 3)),
                 {"units": "degrees_north", "standard_name": "latitude"}),
        nav_lon=(("y", "x"), np.broadcast_to([[60., 60.01, 60.02]], (2, 3)),
                 {"units": "degrees_east", "standard_name": "longitude"}))
    ocean.to_netcdf(tmp_path / "ocean.nc", engine="h5netcdf")
    sources = {name: {
        "files": str(tmp_path / f"{name}.nc"), "variables": {"2d": ["temperature"]},
        "transforms": [{"fields": ["temperature"], "units": "m s-1"}],
    } for name in ("weather", "ocean")}
    conf = SimulationConfig.from_mapping_with_model_preset(request(tmp_path, sources))
    guard_netcdf_payloads(monkeypatch, {"temperature"})
    original_bind = preflight.bind_source
    children = []

    def observe(child, name, **kwargs):
        children.append(child)
        return original_bind(child, name, **kwargs)

    monkeypatch.setattr(preflight, "bind_source", observe)
    with pytest.raises(PreflightError) as failure:
        coupled.bind_sources(conf)
    assert {error.path for error in failure.value.diagnostics} == {
        "sources.weather", "sources.ocean",
    }
    assert len(children) == 2
    for owner in (conf, *children):
        assert all(req["binding"] is None for req in owner.source_requests.values())
    assert failure.value.deferred_checks[0]["status"] == "blocked"
    assert not conf.output_dir.exists()


def test_existing_planning_handlers_share_one_preflight_and_projection(
        tmp_path, monkeypatch, capsys):
    from frameit import cli
    from frameit.core import reports

    v3_scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    document = tmp_path / "request.yaml"
    document.write_text(yaml.safe_dump(request(tmp_path, {"weather": {
        "files": str(tmp_path / "input.nc"), "variables": {"2d": ["temperature"]},
    }})))
    calls, projections = [], []
    original_preflight, original_project = preflight.preflight, reports.project_report

    def observe_preflight(*args, **kwargs):
        facts = original_preflight(*args, **kwargs)
        calls.append(facts)
        return facts

    def observe_projection(result):
        projections.append(result)
        return original_project(result)

    monkeypatch.setattr(preflight, "preflight", observe_preflight)
    monkeypatch.setattr(reports, "project_report", observe_projection)
    assert cli._cmd_validate(document, json_output=True) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    parser = cli._build_parser()
    assert cli._cmd_run(parser.parse_args(["run", str(document), "--dry-run"])) == 0
    assert "OK: run" in capsys.readouterr().out
    assert cli._cmd_config(parser.parse_args(["config", "show", str(document), "--resolved"])) == 0
    assert "OK: config show --effective" in capsys.readouterr().out
    assert len(calls) == len(projections) == 3
    assert all(result.facts is facts for result, facts in zip(projections, calls, strict=True))
    assert [facts["sources"]["weather"]["selected_times"] for facts in calls] == [
        list(v3_scene().time.values),
    ] * 3


def test_independent_null_source_and_invalid_source_are_both_reported(tmp_path):
    report = project(collect(request(tmp_path, {
        "a": {"files": None}, "b": {"files": "input.nc", "model": "guess"},
    }), schema_only=True))
    assert report["status"] == "error"
    assert {error["path"] for error in report["errors"]} == {
        "sources.a.files", "sources.b.model",
    }


def test_existing_execution_facts_can_be_reported_without_reinspection(tmp_path, monkeypatch):
    v3_scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    result = collect(request(tmp_path, {"weather": {
        "files": str(tmp_path / "input.nc"), "variables": {"2d": ["temperature"]},
    }}))

    def forbidden(*args, **kwargs):
        pytest.fail("reporting existing facts must not inspect inputs again")

    monkeypatch.setattr(preflight, "preflight", forbidden)
    assert callable(getattr(preflight, "preflight_result", None)), "facts wrapper is missing"
    execution = preflight.preflight_result(result.conf, result.facts, command="run")
    assert execution.facts is result.facts and execution.conf is result.conf
    report = project(execution)
    assert report["command"] == "run" and report["status"] == "ok"
    assert any(check["status"] == "unfinished-selection" for check in report["deferred_checks"])
    assert any(check["status"] == "execution-dependent" for check in report["deferred_checks"])


def test_disabled_export_does_not_require_an_unused_writer(tmp_path, monkeypatch):
    from frameit.core.execution import ExecutionOptions
    from frameit.core.settings_class import SimulationConfig

    v3_scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    conf = SimulationConfig.from_mapping_with_model_preset(request(tmp_path, {"weather": {
        "files": str(tmp_path / "input.nc"), "variables": {"2d": ["temperature"]},
    }}))
    original = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **kw: (
        None if name == "netCDF4" else original(name, *a, **kw)))
    options = ExecutionOptions.from_config(conf, export_netcdf=False)
    report = project(collect(conf, execution_options=options))
    assert report["status"] == "ok" and not report["errors"]
    assert not any(item["module"] == "netCDF4" for item in report["data"]["plan"]["dependencies"])


def test_missing_path_does_not_hide_an_independent_bad_selected_file(tmp_path):
    (tmp_path / "bad.bin").write_bytes(b"badbytes")
    document = tmp_path / "request.yaml"
    document.write_text(
        "schema_version: 3\nsources:\n  weather:\n    files:\n"
        "      - missing.nc\n      - bad.bin\n"
    )
    report = project(collect(document))
    assert report["status"] == "error"
    assert len(report["errors"]) == 2
    missing = next(error for error in report["errors"] if "missing" in str(error["observed"]))
    assert missing["locations"] == [{"file": str(document), "line": 5, "column": 9}]
    bad = next(error for error in report["errors"] if "magic_hex" in error["observed"])
    assert bad["locations"] == [{"file": str(document), "line": 6, "column": 9}]
    assert bad["observed"]["magic_hex"] == b"badbytes".hex()
    assert all(error["repairs"] for error in report["errors"])


@pytest.mark.parametrize("section,value,expected", [
    ("resources", {"cpus": 0}, "positive integer"),
    ("output", {"overwrite": "yes"}, "YAML boolean"),
    ("sources", {"weather": {"files": 0}}, "path/glob"),
])
def test_schema_value_errors_project_actual_value_not_a_traceback(
        tmp_path, section, value, expected):
    raw = request(tmp_path, {"weather": {"files": "absent.nc"}})
    raw[section] = value
    report = project(collect(raw, schema_only=True))
    error, = report["errors"]
    assert error["observed"] in (0, "yes")
    assert expected in error["expected"]
    assert error["repairs"] and error["locations"] == []


def test_yaml_report_locations_do_not_extend_the_frozen_run_request_record(tmp_path):
    from frameit.core.execution import execute_simulation
    from frameit.core.settings_class import SimulationConfig

    v3_scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = request(tmp_path, {"weather": {
        "files": "input.nc", "variables": {"2d": ["temperature"]},
    }})
    raw["resources"].update(synchronous_export=True, scheduler="synchronous")
    document = tmp_path / "request.yaml"
    document.write_text(yaml.safe_dump(raw))
    conf = SimulationConfig.from_yaml_with_model_preset(document)
    assert set(conf.request_context) == {
        "request_kind", "authored_configuration", "request_path", "path_bases", "overrides",
    }
    result = execute_simulation(conf)
    assert result.ok and len(result.products) == 1
    captured = yaml.safe_load((conf.output_dir / "run-request.yaml").read_text())
    assert set(captured) == {
        "record_version", "request_kind", "authored_configuration", "request_path", "path_bases",
        "overrides", "requested_execution_options", "runtime",
    }
    assert captured["authored_configuration"] == raw


def test_direct_preparation_errors_include_captured_authored_locations(tmp_path):
    from frameit.core.coupled import prepare_sources
    from frameit.core.reports import PreflightError
    from frameit.core.settings_class import SimulationConfig

    (tmp_path / "bad.bin").write_bytes(b"badbytes")
    document = tmp_path / "request.yaml"
    document.write_text("schema_version: 3\nsources:\n  weather:\n    files: bad.bin\n")
    conf = SimulationConfig.from_yaml_with_model_preset(document)
    with pytest.raises(PreflightError) as failure:
        prepare_sources(conf)
    error, = failure.value.diagnostics
    assert error.locations == [{"file": str(document), "line": 4, "column": 5}]
    assert "line 4" in str(failure.value)


@pytest.mark.parametrize("tail,path,observed,expected,line,column", [
    ("output:\n  writer:\n    compression:\n      level: 10\n",
     "output.writer.compression.level", 10, {"min": 0, "max": 9}, 8, 7),
    ("output:\n  writer:\n    compression: 17\n",
     "output.writer.compression", 17, "mapping", 7, 5),
    ("    variables: 17\n", "sources.weather.variables", 17, "mapping", 5, 5),
    ("    field_metadata: []\n",
     "sources.weather.field_metadata", [], "mapping", 5, 5),
    ("    derived: []\n", "sources.weather.derived", [], "mapping", 5, 5),
    ("    reader:\n      chunks: []\n",
     "sources.weather.reader.chunks", [], "dimension-size mapping", 6, 7),
    ("metadata:\n  extra: []\n", "metadata.extra", [], "mapping", 6, 3),
    ("region:\n  center: {latitude: 0}\n", "region.center.longitude",
     {"present": False}, {"present": True}, 6, 3),
    ("products:\n  polar: {}\n", "products.polar.radius_km",
     {"present": False}, {"present": True}, 6, 3),
    ("region:\n  tracker: {}\n", "region.tracker.method",
     {"present": False}, {"present": True}, 6, 3),
    ("region:\n  center:\n    latitude: 91\n    longitude: 0\n",
     "region.center.latitude", 91, {"min": -90, "max": 90, "units": "degrees"}, 7, 5),
    ("    time:\n      values: ['2026-01-01']\n      start: '2026-01-01'\n",
     "sources.weather.time.values", {"values": ["2026-01-01"], "start": "2026-01-01"},
     {"exclusive_with": ["start", "end", "stride"]}, 6, 7),
    ("    time:\n      start: '2026-01-02'\n      end: '2026-01-01'\n",
     "sources.weather.time.start", "2026-01-02", {"not_after": "2026-01-01"}, 6, 7),
    ("    variables:\n      levels: {indices: [0], values: [1000]}\n",
     "sources.weather.variables.levels", {"indices": [0], "values": [1000]},
     {"at_most_one": ["domain", "indices", "values"]}, 6, 7),
    ("    variables:\n      levels:\n        values: {min: 1000, max: 900}\n",
     "sources.weather.variables.levels.values.min", 1000, {"max": 900}, 7, 18),
    ("region:\n  center: {latitude: 0, longitude: 0}\n  track: {file: track.nc}\n",
     "region", {"center": {"latitude": 0, "longitude": 0}, "track": {"file": "track.nc"}},
     {"at_most_one": ["center", "track", "tracker"]}, 5, 1),
    ("region:\n  tracker:\n    method: pressure_centroid\n    motion: {relaxation: 2}\n",
     "region.tracker.motion.relaxation", 2, {"max": 1}, 8, 14),
    ("region:\n  tracker:\n    method: pressure_centroid\n    sampling: {azimuth_step_deg: 180}\n",
     "region.tracker.sampling.azimuth_step_deg", 180, {"exclusive_max": 180}, 8, 16),
    ("region:\n  center: {latitude: 0, longitude: 0}\nproducts:\n"
     "  polar: {radius_km: 2, azimuth_count: 2}\n",
     "products.polar.azimuth_count", 2, {"min": 3}, 8, 25),
    ("region:\n  center: {latitude: 0, longitude: 0}\nproducts:\n"
     "  polar:\n    radius_km: 2\n    processing: {weight_zero_tolerance: 0.000001}\n",
     "products.polar.processing.weight_zero_tolerance", 0.000001,
     {"min": 0, "exclusive_max": 0.000001}, 10, 18),
    ("region:\n  center: {latitude: 0, longitude: 0}\nproducts:\n"
     "  polar:\n    radius_km: 2\n    missing_data_policy: renormalize\n"
     "    min_valid_weight_fraction: 2\n",
     "products.polar.min_valid_weight_fraction", 2, {"max": 1}, 11, 5),
    ("output:\n  format: zarr\n  writer:\n    engine: h5netcdf\n",
     "output.writer.engine", {"format": "zarr", "value": "h5netcdf"},
     {"format": "netcdf"}, 8, 5),
])
def test_fix1_owned_schema_facts_and_same_text_marks(
        tmp_path, monkeypatch, tail, path, observed, expected, line, column):
    document = tmp_path / "request.yaml"
    text = "schema_version: 3\nsources:\n  weather:\n    files: absent.nc\n" + tail
    document.write_text(text)
    original = Path.read_text
    reads = []

    def one_read(filename, *args, **kwargs):
        if filename == document:
            reads.append(filename)
        return original(filename, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", one_read)
    report = project(collect(document, schema_only=True))
    assert report["status"] == "error"
    error, = report["errors"]
    assert error["path"] == path
    assert error["observed"] == observed
    assert error["expected"] == expected
    assert error["repairs"] and all(path in repair for repair in error["repairs"])
    assert error["locations"] == [{"file": str(document), "line": line, "column": column}]
    assert reads == [document]
    assert report["data"]["configuration"] is None and report["data"]["plan"] == {}
    memory = project(collect(yaml.safe_load(text), schema_only=True))
    assert memory["errors"][0]["path"] == path
    assert memory["errors"][0]["observed"] == observed
    assert memory["errors"][0]["locations"] == []


@pytest.mark.parametrize("tail,path,observed,expected", [
    ("run: {unknown: 1}\n", "run.unknown", "unknown", {"keys": ["description", "name"]}),
    ("run: {name: ../bad}\n", "run.name", "../bad", "identifier without path separators"),
    ("run: {description: 17}\n", "run.description", 17, "string"),
    ("sources: []\n", "sources", [], "nonempty mapping of source names"),
    ("metadata: {institution: 17}\n", "metadata.institution", 17, "string"),
    ("    variables: {2d: []}\n", "sources.weather.variables.2d", [], "nonempty list of names"),
    ("    variables: {levels: {indices: []}}\n",
     "sources.weather.variables.levels.indices", [], "nonempty list"),
    ("    format: grib\n    model: nemo\n", "sources.weather.format",
     {"model": "nemo", "format": "grib"}, {"format": "netcdf"}),
    ("    reader: {engine: scipy}\n    format: grib\n",
     "sources.weather.reader.engine", {"format": "grib", "value": "scipy"},
     {"format": "netcdf"}),
    ("    format: netcdf\n    reader: {max_points: 10}\n",
     "sources.weather.reader.max_points", {"format": "netcdf", "value": 10}, {"format": "fa"}),
    ("    wind_pairs:\n      - {u: u, v: v, basis: grid, rotation: {method: coordinate}}\n",
     "sources.weather.wind_pairs[0].rotation.coordinate", {"present": False}, {"present": True}),
    ("    wind_pairs:\n      - {u: u, v: v, basis: grid,\n"
     "         rotation: {method: mesonh_projection, RPK: 2}}\n",
     "sources.weather.wind_pairs[0].rotation.RPK", 2, {"min": -1, "max": 1}),
    ("    transforms: [{fields: [temperature]}]\n", "sources.weather.transforms[0]",
     {"fields": ["temperature"]}, {"one_of": ["basis", "sampling", "units"]}),
    ("region: {width_km: {x: 1, y: 1}}\n", "region.width_km",
     {"x": 1, "y": 1}, {"requires_one_of": ["center", "track", "tracker"]}),
    ("region: {tracker: []}\n", "region.tracker", [], "mapping with method"),
    ("region:\n  tracker: {method: pressure_wind, on_incomplete: keep_prefix}\n",
     "region.tracker.on_incomplete", {"method": "pressure_wind", "on_incomplete": "keep_prefix"},
     {"method": "multifield_vortex"}),
    ("region:\n  tracker:\n    method: multifield_vortex\n"
     "    seed: {latitude: 0, longitude: 0, motion_u_m_s: 0, motion_v_m_s: 0}\n",
     "region.tracker.seed.latitude", 0,
     {"absolute_min_exclusive": 0, "absolute_max_exclusive": 90}),
    ("products: {}\n", "products", {}, "at least one product"),
    ("products: {track: true}\n", "products.track", True,
     {"requires_one_of": ["center", "track", "tracker"]}),
    ("products: {model_grid: {fields: []}}\n", "products.model_grid.fields", [],
     "nonempty source-name mapping"),
    ("products: {model_grid: {fields: {missing: [temperature]}}}\n",
     "products.model_grid.fields.missing", "missing", {"sources": ["weather"]}),
    ("products: {model_grid: {fields: {weather: [missing]}}}\n",
     "products.model_grid.fields.weather", ["missing"], {"declared_fields": []}),
    ("products: {polar: {radius_km: 2}}\n", "products.polar", {"radius_km": 2},
     {"requires_one_of": ["center", "track", "tracker"]}),
    ("region: {center: {latitude: 0, longitude: 0}}\nproducts:\n"
     "  polar: {radius_km: 2, field_options: []}\n",
     "products.polar.field_options", [], "source-name mapping"),
    ("region: {center: {latitude: 0, longitude: 0}}\nproducts:\n"
     "  polar: {radius_km: 2, field_options: {weather: []}}\n",
     "products.polar.field_options.weather", [], "mapping"),
    ("region: {center: {latitude: 0, longitude: 0}}\nproducts:\n"
     "  polar: {radius_km: 2, missing_data_policy: renormalize}\n",
     "products.polar.min_valid_weight_fraction", {"present": False}, {"present": True}),
    ("region: {center: {latitude: 0, longitude: 0}}\nproducts:\n"
     "  polar: {radius_km: 2, min_valid_weight_fraction: 0.5}\n",
     "products.polar.min_valid_weight_fraction",
     {"missing_data_policy": "strict", "value": 0.5}, {"missing_data_policy": "renormalize"}),
    ("region: {center: {latitude: 0, longitude: 0}}\nproducts:\n"
     "  polar: {radius_km: 2, missing_data_policy: renormalize, min_valid_weight_fraction: 0.5,\n"
     "          field_options: {weather: {unused: {interpolation: nearest}}}}\n",
     "products.polar.field_options.weather.unused", "unused", {"selected_fields": []}),
    ("output: {writer: {shards: {x: 4}}}\n", "output.writer.shards",
     {"format": "netcdf", "value": {"x": 4}}, {"format": "zarr"}),
])
def test_fix1_other_owned_schema_controls_keep_rule_and_value(
        tmp_path, tail, path, observed, expected):
    document = tmp_path / "request.yaml"
    prefix = "schema_version: 3\nsources:\n  weather:\n    files: absent.nc\n"
    text = "schema_version: 3\n" + tail if tail.startswith("sources:") else prefix + tail
    document.write_text(text)
    report = project(collect(document, schema_only=True))
    assert report["status"] == "error"
    error, = report["errors"]
    assert error["path"] == path
    assert error["observed"] == observed and error["expected"] == expected
    assert error["repairs"] and all(path in repair for repair in error["repairs"])
    assert error["locations"] and all(mark["file"] == str(document) for mark in error["locations"])
    assert report["data"]["configuration"] is None


@pytest.mark.parametrize("tail,path,observed,expected", [
    ("    wind_pairs:\n      - {u: u, v: v, basis: grid,\n"
     "         rotation: {method: geolocation, coordinate: angle}}\n",
     "sources.weather.wind_pairs[0].rotation.coordinate",
     {"method": "geolocation", "value": "angle"}, {"method": "coordinate"}),
    ("    wind_pairs:\n      - {u: u, v: v, basis: grid,\n"
     "         rotation: {method: geolocation, BETA: 0}}\n",
     "sources.weather.wind_pairs[0].rotation.BETA",
     {"method": "geolocation", "value": 0}, {"method": "mesonh_projection"}),
    ("    format: netcdf\n    field_metadata: {temperature: {allow_unscaled: true}}\n",
     "sources.weather.field_metadata.temperature.allow_unscaled",
     {"format": "netcdf", "value": True}, {"format": "fa"}),
    ("    model: arome\n    format: grib\n    interpretation: mesonh_surfex_sea\n",
     "sources.weather.interpretation",
     {"model": "arome", "format": "grib", "interpretation": "mesonh_surfex_sea"},
     {"model": "mesonh", "format": "netcdf"}),
    ("    format: fa\n    profile: arome_history\n    reader: {chunks: {x: 1}}\n",
     "sources.weather.reader.chunks", {"format": "fa", "value": {"x": 1}},
     "no FA reader chunks"),
    ("    format: fa\n    model: mesonh\n    profile: arome_history\n",
     "sources.weather.model", "mesonh", "arome"),
    ("    format: fa\n    profile: arome_history\n"
     "    variables: {levels: {domain: physical}}\n",
     "sources.weather.variables.levels", {"domain": "physical"},
     {"selection": ["indices", "values"]}),
    ("    format: fa\n    profile: arome_history\n    variables: {3d: [q]}\n",
     "sources.weather.variables.3d.q", {"field": "q", "native_cubes": []},
     {"native_cubes": ["q"]}),
    ("    format: grib\n    profile: arome_history\n", "sources.weather.profile",
     {"format": "grib", "value": "arome_history"}, {"format": "fa"}),
    ("    wind_pairs:\n      - {u: u, v: v, basis: earth, rotation: {method: geolocation}}\n",
     "sources.weather.wind_pairs[0].rotation",
     {"basis": "earth", "value": {"method": "geolocation"}}, {"basis": "grid"}),
    ("    variables: {2d: [temperature]}\n"
     "region: {center: {latitude: 0, longitude: 0}}\nproducts:\n"
     "  polar: {radius_km: 2, missing_data_policy: renormalize, min_valid_weight_fraction: 0.5,\n"
     "          field_options: {weather: {temperature: {interpolation: nearest}}}}\n",
     "products.polar.field_options.weather.temperature.interpolation",
     {"missing_data_policy": "renormalize", "interpolation": "nearest"},
     {"interpolation_not": "nearest"}),
    ("    derived: {speed: {method: wind_speed, inputs: {u: u, v: v}}}\n"
     "region: {center: {latitude: 0, longitude: 0}}\nproducts:\n"
     "  polar: {radius_km: 2, field_options: {weather: {speed: {interpolation: nearest}}}}\n",
     "products.polar.field_options.weather.speed", {"interpolation": "nearest"},
     {"configure_inputs": ["u", "v"]}),
    ("    time: {start: '2026-13-01'}\n", "sources.weather.time.start", "2026-13-01",
     "ISO timestamp with valid month/day/time ranges"),
    ("    time: {start: '2026-01-01T00:00:00+99:00'}\n", "sources.weather.time.start",
     "2026-01-01T00:00:00+99:00", "ISO timezone offset with hours <= 23 and minutes <= 59"),
])
def test_fix1_conditional_schema_rules_remain_explicit(
        tmp_path, tail, path, observed, expected):
    document = tmp_path / "request.yaml"
    document.write_text("schema_version: 3\nsources:\n  weather:\n    files: absent.nc\n" + tail)
    report = project(collect(document, schema_only=True))
    error, = report["errors"]
    assert report["status"] == "error"
    assert error["path"] == path and error["expected"] == expected
    assert error["observed"] == observed
    assert error["repairs"] and all(path in repair for repair in error["repairs"])
    assert error["locations"] and error["locations"][0]["file"] == str(document)


@pytest.mark.parametrize("bad_first,bad_line,model_line", [(True, 3, 7), (False, 6, 5)])
def test_fix1_invalid_source_name_does_not_discard_an_independent_model_error(
        tmp_path, bad_first, bad_line, model_line):
    document = tmp_path / "request.yaml"
    invalid = "  bad.name:\n    files: absent.nc\n"
    weather = "  weather:\n    files: absent.nc\n    model: guess\n"
    text = "schema_version: 3\nsources:\n" + (
        invalid + weather if bad_first else weather + invalid)
    document.write_text(text)
    report = project(collect(document, schema_only=True))
    assert report["status"] == "error"
    errors = {error["path"]: error for error in report["errors"]}
    assert len(report["errors"]) == 2 and set(errors) == {
        "sources.bad.name", "sources.weather.model",
    }
    name = errors["sources.bad.name"]
    assert name["observed"] == "bad.name"
    assert name["expected"] == {"pattern": "[A-Za-z][A-Za-z0-9_-]*"}
    assert name["locations"] == [{"file": str(document), "line": bad_line, "column": 3}]
    assert name["repairs"] and "Rename" in name["repairs"][0]
    model = errors["sources.weather.model"]
    assert model["observed"] == "guess"
    assert model["expected"] == ["arome", "croco", "mesonh", "nemo"]
    assert model["locations"] == [{"file": str(document), "line": model_line, "column": 5}]
    assert model["repairs"]
    assert report["data"]["configuration"] is None and report["data"]["plan"] == {}
    memory = project(collect(yaml.safe_load(text), schema_only=True))
    assert {error["path"] for error in memory["errors"]} == set(errors)
    assert all(error["locations"] == [] for error in memory["errors"])


def test_fix1_source_identifiers_keep_the_existing_rule_not_a_vocabulary(tmp_path):
    valid = project(collect(request(tmp_path, {
        "Research_42-output": {"files": "absent.nc"},
    }), schema_only=True))
    assert valid["status"] == "ok"
    assert "Research_42-output" in valid["data"]["configuration"]["sources"]
    invalid = project(collect(request(tmp_path, {
        42: {"files": "absent.nc"}, "Research_42-output": {"files": "absent.nc", "model": "guess"},
    }), schema_only=True))
    assert {error["path"] for error in invalid["errors"]} == {
        "sources.42", "sources.Research_42-output.model",
    }
    assert next(error for error in invalid["errors"] if error["path"] == "sources.42")[
        "observed"] == 42


def fix1_mixed_configuration(tmp_path, *, shared, bad_units, polar):
    import hashlib

    from frameit.core.settings_class import SimulationConfig
    from frameit.testing.numerical.test_v3_polar import scene

    atmosphere, ocean, broken = (
        tmp_path / name for name in ("atmosphere.nc", "ocean.nc", "bad.bin"))
    scene().to_netcdf(atmosphere, engine="h5netcdf")
    water = scene().rename({
        "ni": "x", "nj": "y", "time": "time_counter", "latitude": "nav_lat", "longitude": "nav_lon",
    }).assign_attrs(model="NEMO")
    water.to_netcdf(ocean, engine="h5netcdf")
    broken.write_bytes(b"badbytes")
    raw = request(tmp_path, {
        "broken": {"files": str(broken), "variables": {"2d": ["q"]}},
        "atmosphere": {
            "model": "mesonh", "files": str(atmosphere), "variables": {"2d": ["q"]},
            "transforms": [{"fields": ["q"], "units": "m s-1"}] if bad_units else [],
        },
        "ocean": {"files": str(ocean), "variables": {"2d": ["q"]}},
    })
    if polar:
        raw["region"] = {"center": {"latitude": -20., "longitude": 60.}}
        raw["products"] = {
            "model_grid": True,
            "polar": {"radius_km": 2.5, "azimuth_count": 8, "shared_grid": shared},
        }
    raw["resources"].update(synchronous_export=True, scheduler="synchronous")
    document = tmp_path / "request.yaml"
    document.write_text(yaml.safe_dump(raw, sort_keys=False))
    originals = {}
    for path in (atmosphere, ocean, broken):
        path.chmod(0o444)
        originals[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return SimulationConfig.from_yaml_with_model_preset(document), originals


@pytest.mark.parametrize("polar,shared", [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize("bad_units", [False, True])
def test_fix1_inventory_error_keeps_independent_local_binding_checks(
        tmp_path, monkeypatch, polar, shared, bad_units):
    import hashlib

    from frameit.core import coupled
    from frameit.core.reports import PreflightError

    conf, originals = fix1_mixed_configuration(
        tmp_path, shared=shared, bad_units=bad_units, polar=polar)
    inventory, bindings, results = {}, {}, {}
    original_inventory, original_bind = preflight.inventory_source, preflight.bind_source

    def inventory_once(child, name, **kwargs):
        inventory[name] = inventory.get(name, 0) + 1
        return original_inventory(child, name, **kwargs)

    def bind_once(child, name, **kwargs):
        bindings.setdefault(name, []).append(child)
        binding = original_bind(child, name, **kwargs)
        results[name] = (binding, binding["status"])
        return binding

    def blocked_geometry(*args, **kwargs):
        pytest.fail("cross-source region/product geometry ran with an unavailable inventory")

    guard_netcdf_payloads(monkeypatch, {"q"})
    monkeypatch.setattr(preflight, "inventory_source", inventory_once)
    monkeypatch.setattr(preflight, "bind_source", bind_once)
    monkeypatch.setattr(coupled, "_prepare_v3_regions", blocked_geometry)
    with pytest.raises(PreflightError) as failed:
        coupled.bind_sources(conf)
    error = failed.value
    assert inventory == {"broken": 1, "atmosphere": 1, "ocean": 1}
    assert set(bindings) == {"atmosphere", "ocean"}
    assert all(len(owners) == 1 for owners in bindings.values())
    expected_paths = {"sources.broken.files"} | ({"sources.atmosphere"} if bad_units else set())
    assert {cause.path for cause in error.diagnostics} == expected_paths
    assert len(error.diagnostics) == len(expected_paths)
    if bad_units:
        units = next(cause for cause in error.diagnostics if cause.path == "sources.atmosphere")
        assert "incompatible or unsupported units 'K' -> 'm s-1'" in units.message
        assert units.observed["fields"]["q"]["units"] == "K"
    blocked = {check["path"]: check for check in error.deferred_checks}
    assert blocked["sources.broken.binding"]["prerequisites"] == ["sources.broken.files"]
    assert "sources.ocean.binding" not in blocked
    if bad_units:
        assert blocked["sources.atmosphere.execution"]["prerequisites"] == ["sources.atmosphere"]
    assert set(blocked["plan"]["prerequisites"]) == expected_paths
    assert results["ocean"][1] == ("pending_method_binding" if polar else "bound")
    assert results["ocean"][0]["deferred_checks"] == ([
        "Polar centre/time associations and regional geometry require method planning.",
    ] if polar else [])
    assert blocked["sources.ocean.execution"]["prerequisites"] == ["sources.broken.files"]
    for binding, _ in results.values():
        assert binding["status"] != "bound"
        assert "polar_plan" not in binding
    for owner in (conf, *(owners[0] for owners in bindings.values())):
        assert all(item["binding"] is None for item in owner.source_requests.values())
        assert "common_polar_target" not in owner.simulation_parameter
        for source in owner.simulation_parameter["request_plan"]["sources"].values():
            assert source["requests"]["binding"] is None and source.get("field_binding") is None
    assert set(error.facts["sources"]) == {"atmosphere", "ocean"}
    assert all(source.get("field_binding") is None for source in error.facts["sources"].values())
    assert not error.facts.get("products") and not error.facts.get("common_polar_target")
    assert all(cause.locations for cause in error.diagnostics)
    assert not conf.output_dir.exists()
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in originals} == originals


@pytest.mark.parametrize("frontend", ["prepare", "native"])
def test_fix1_partial_inventory_does_not_bind_ordinary_discovery(tmp_path, monkeypatch, frontend):
    from frameit.core import coupled
    from frameit.core.reports import PreflightError

    conf, _ = fix1_mixed_configuration(tmp_path, shared=False, bad_units=True, polar=False)
    original_inventory, inventory = preflight.inventory_source, []

    def observe_inventory(child, name, **kwargs):
        inventory.append(name)
        return original_inventory(child, name, **kwargs)

    def no_bind(*args, **kwargs):
        pytest.fail("ordinary discovery must not bind even locally available sources")

    guard_netcdf_payloads(monkeypatch, {"q"})
    monkeypatch.setattr(preflight, "inventory_source", observe_inventory)
    monkeypatch.setattr(preflight, "bind_source", no_bind)
    monkeypatch.setattr(coupled, "bind_sources", no_bind)
    operation = coupled.prepare_sources if frontend == "prepare" else preflight.preflight
    with pytest.raises(PreflightError) as failure:
        operation(conf)
    assert inventory == ["broken", "atmosphere", "ocean"]
    assert {error.path for error in failure.value.diagnostics} == {"sources.broken.files"}
    assert all(item["binding"] is None for item in conf.source_requests.values())
    assert all(source.get("field_binding") is None
               for source in failure.value.facts["sources"].values())
    assert any(check["path"] == "sources.broken.binding"
               for check in failure.value.deferred_checks)
    assert not conf.output_dir.exists()


def test_fix1_partial_inventory_still_blocks_missing_local_method_dependencies(
        tmp_path, monkeypatch):
    from frameit.core import coupled
    from frameit.core.reports import PreflightError

    conf, _ = fix1_mixed_configuration(tmp_path, shared=True, bad_units=True, polar=True)
    original_spec = importlib.util.find_spec

    def absent_polar(module, *args, **kwargs):
        return None if module == "xesmf" else original_spec(module, *args, **kwargs)

    def no_bind(*args, **kwargs):
        pytest.fail("a missing selected local method dependency must block its binding")

    guard_netcdf_payloads(monkeypatch, {"q"})
    monkeypatch.setattr(importlib.util, "find_spec", absent_polar)
    monkeypatch.setattr(preflight, "bind_source", no_bind)
    with pytest.raises(PreflightError) as failure:
        coupled.bind_sources(conf)
    assert {error.path for error in failure.value.diagnostics} == {
        "products.polar", "sources.broken.files",
    }
    blocked = {check["path"]: check for check in failure.value.deferred_checks}
    assert blocked["sources.broken.binding"]["prerequisites"] == ["sources.broken.files"]
    for name in ("atmosphere", "ocean"):
        assert blocked[f"sources.{name}.binding"]["prerequisites"] == ["products.polar"]
    assert all(request["binding"] is None for request in conf.source_requests.values())
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("authored,selected,module", [
    ("netcdf4", "h5netcdf", "h5netcdf"), ("h5netcdf", "netcdf4", "netCDF4"),
])
@pytest.mark.parametrize("available", [True, False])
def test_fix1_writer_dependencies_follow_effective_engine_in_both_availability_directions(
        tmp_path, monkeypatch, authored, selected, module, available):
    from frameit.core.configuration import resolved_configuration
    from frameit.core.execution import ExecutionOptions
    from frameit.core.settings_class import SimulationConfig
    from frameit.io import zarr_export

    raw = request(tmp_path, {"weather": {
        "files": "absent.nc", "variables": {"2d": ["temperature"]},
    }})
    raw["output"]["writer"] = {"engine": authored}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    before = deepcopy(conf.yaml_config)
    options = ExecutionOptions.from_config(conf, engine=selected)
    probes = []

    def installed(name):
        probes.append(name)
        assert name in {"netCDF4", "h5netcdf"}
        return object() if (name == module) == available else None

    def no_zarr():
        pytest.fail("NetCDF writer selection must not check Zarr")

    monkeypatch.setattr(importlib.util, "find_spec", installed)
    monkeypatch.setattr(zarr_export, "check_zarr_dependencies", no_zarr)
    facts, errors = preflight._required_dependencies(conf, options)
    assert probes == [module]
    fact, = facts
    assert fact["path"] == "output.writer.engine" and fact["module"] == module
    assert fact["available"] is available
    assert bool(errors) is not available
    if errors:
        error, = errors
        assert error.path == "output.writer.engine"
        assert error.expected == {"module": module, "available": True}
        assert error.observed == {"module": module, "available": False}
        assert error.repairs
    assert resolved_configuration(conf, options)["output"]["writer"]["engine"] == selected
    assert conf.yaml_config == before and not conf.output_dir.exists()


@pytest.mark.parametrize("authored_format,selected", [("netcdf", "zarr"), ("zarr", "h5netcdf")])
@pytest.mark.parametrize("available", [True, False])
def test_fix1_writer_dependencies_follow_effective_format_and_existing_zarr_versions(
        tmp_path, monkeypatch, authored_format, selected, available):
    import importlib.metadata

    from frameit.core.configuration import resolved_configuration
    from frameit.core.execution import ExecutionOptions
    from frameit.core.settings_class import SimulationConfig
    from frameit.io import zarr_export

    raw = request(tmp_path, {"weather": {
        "files": "absent.nc", "variables": {"2d": ["temperature"]},
    }})
    raw["output"]["format"] = authored_format
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    before = deepcopy(conf.yaml_config)
    options = ExecutionOptions.from_config(conf, engine=selected)
    probes = []
    original_zarr = zarr_export.check_zarr_dependencies

    def installed(module):
        probes.append(module)
        return object() if available else None

    def version(package):
        assert selected == "zarr" and package in {"xarray", "zarr"}
        return "2026.9.0" if package == "xarray" else ("3.4.2" if available else "3.4.1")

    def zarr_versions():
        probes.append("zarr")
        return original_zarr()

    monkeypatch.setattr(importlib.util, "find_spec", installed)
    monkeypatch.setattr(importlib.metadata, "version", version)
    monkeypatch.setattr(zarr_export, "check_zarr_dependencies", zarr_versions)
    facts, errors = preflight._required_dependencies(conf, options)
    assert probes == [selected]
    assert bool(errors) is not available
    if errors:
        error, = errors
        assert error.path == ("output.format" if selected == "zarr" else "output.writer.engine")
        assert error.repairs
        if selected == "zarr":
            assert error.expected == "xarray>=2026.9.0 and zarr>=3.4.2,<4"
            assert "zarr>=3.4.2,<4" in error.message
    else:
        fact, = facts
        assert fact["module"] == selected and fact["available"] is True
    effective = resolved_configuration(conf, options)["output"]
    assert effective["format"] == ("zarr" if selected == "zarr" else "netcdf")
    assert conf.yaml_config == before and not conf.output_dir.exists()


@pytest.mark.parametrize("authored_format,selected", [
    ("netcdf", "h5netcdf"), ("netcdf", "zarr"), ("zarr", "netcdf4"),
])
def test_fix1_disabled_export_skips_authored_and_effective_writer_dependencies(
        tmp_path, monkeypatch, authored_format, selected):
    from frameit.core.execution import ExecutionOptions
    from frameit.core.settings_class import SimulationConfig
    from frameit.io import zarr_export

    raw = request(tmp_path, {"weather": {
        "files": "absent.nc", "variables": {"2d": ["temperature"]},
    }})
    raw["output"]["format"] = authored_format
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    options = ExecutionOptions.from_config(conf, engine=selected, export_netcdf=False)

    def no_dependency(*args, **kwargs):
        pytest.fail("disabled export must not probe any writer or unrelated optional dependency")

    monkeypatch.setattr(importlib.util, "find_spec", no_dependency)
    monkeypatch.setattr(zarr_export, "check_zarr_dependencies", no_dependency)
    assert preflight._required_dependencies(conf, options) == ([], [])
    assert not conf.output_dir.exists()


def test_fix2_required_key_repair_uses_real_root_and_preserves_nested_prefix(tmp_path, monkeypatch):
    def offline_only(*args, **kwargs):
        pytest.fail("schema-only required-key repairs must not inspect inputs or dependencies")

    monkeypatch.setattr(preflight, "preflight", offline_only)
    monkeypatch.setattr(importlib.util, "find_spec", offline_only)
    missing = project(collect({"schema_version": 3}, schema_only=True))
    assert missing["status"] == "error" and missing["data"]["configuration"] is None
    error, = missing["errors"]
    assert error["path"] == "sources" and error["repairs"] == ["Provide sources."]
    assert error["message"] == "configuration requires sources"
    assert error["expected"] == {"present": True} and error["observed"] == {"present": False}
    assert error["locations"] == [] and missing["data"]["inputs"] == []
    repaired = {"schema_version": 3, error["path"]: {
        "weather": {"files": str(tmp_path / "absent.nc")},
    }}
    accepted = project(collect(repaired, schema_only=True))
    assert accepted["status"] == "ok" and accepted["errors"] == []
    assert accepted["data"]["inputs"] == [] and not (tmp_path / "absent.nc").exists()
    nested = project(collect({
        **repaired, "region": {"center": {"latitude": 0}},
    }, schema_only=True))
    nested_error, = nested["errors"]
    assert nested["status"] == "error" and nested["data"]["configuration"] is None
    assert nested_error["path"] == "region.center.longitude"
    assert nested_error["repairs"] == ["Provide region.center.longitude."]
    assert nested_error["expected"] == {"present": True}
    assert nested_error["observed"] == {"present": False} and nested_error["locations"] == []
