"""Public v3 commands on small instructional inputs; no producer qualification."""

import errno
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from frameit.cli import main
from frameit.testing.documentation_example import create_first_run_input
from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads


def invoke(capsys, *args):
    with pytest.raises(SystemExit) as result:
        main(list(map(str, args)))
    captured = capsys.readouterr()
    return result.value.code, captured.out, captured.err


def envelope(text, command, status="ok"):
    report = json.loads(text)
    assert set(report) == {
        "report_version", "command", "status", "data", "warnings", "errors", "deferred_checks",
    }
    assert report["report_version"] == 1
    assert report["command"] == command and report["status"] == status
    assert set(report["data"]) == {"configuration", "origins", "inputs", "plan", "pending"}
    return report


def case(tmp_path, *, selected=True):
    raw = {
        "schema_version": 3, "run": {"name": "cli"},
        "sources": {"weather": {"model": "arome", "files": "./input.nc"}},
        "output": {"directory": "./out"},
        "resources": {"cpus": 1, "scheduler": "synchronous", "synchronous_export": True},
        "metadata": {"extra": {"note": None}},
    }
    if selected:
        raw["sources"]["weather"]["variables"] = {"2d": ["instructional_scalar"]}
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path, raw


def test_same_yaml_inspection_validation_and_authored_effective_views(
        tmp_path, monkeypatch, capsys):
    create_first_run_input(tmp_path / "input.nc")
    path, raw = case(tmp_path)
    original = path.read_bytes()
    guard_netcdf_payloads(monkeypatch, {"instructional_scalar"})
    for command in ("inspect", "validate"):
        code, out, _ = invoke(capsys, command, path, "--json")
        assert code == 0
        report = envelope(out, command)
        source = report["data"]["plan"]["sources"]["weather"]
        assert "instructional_scalar" in str(source["fields"])
        assert len(source["selected_times"]) == 2
    for json_output in (False, True):
        code, out, _ = invoke(capsys, "config", "show", path, *(["--json"] if json_output else []))
        assert code == 0
        assert (json.loads(out) if json_output else yaml.safe_load(out)) == raw
    code, out, _ = invoke(capsys, "config", "show", path, "--effective", "--json")
    assert code == 0
    effective = envelope(out, "config show --effective")["data"]
    assert effective["configuration"]["output"]["writer"]["engine"] == "netcdf4"
    assert effective["origins"]["output.writer.engine"] == "default"
    assert path.read_bytes() == original and not (tmp_path / "out").exists()


def test_unfinished_inspection_uses_shared_selector_and_never_binds(tmp_path, monkeypatch, capsys):
    create_first_run_input(tmp_path / "input.nc")
    path, _ = case(tmp_path, selected=False)
    guard_netcdf_payloads(monkeypatch, {"instructional_scalar"})

    def forbidden(*args, **kwargs):
        pytest.fail("Discovery performed a scientific bind")

    monkeypatch.setattr("frameit.core.coupled.bind_sources", forbidden)
    code, out, _ = invoke(capsys, "inspect", path, "--json")
    assert code == 0
    report = envelope(out, "inspect")
    source = report["data"]["plan"]["sources"]["weather"]
    assert source["requests"]["binding"] is None
    assert source["available_selectors"][0]["variables"] == {"2d": ["instructional_scalar"]}
    assert any(item["status"] == "unfinished-selection" for item in report["deferred_checks"])


@pytest.mark.parametrize("command", [("validate",), ("config", "show")])
def test_operational_flags_use_original_path_bases_and_origins(
        tmp_path, monkeypatch, capsys, command):
    base, launch = tmp_path / "base", tmp_path / "launch"
    base.mkdir()
    launch.mkdir()
    create_first_run_input(base / "input.nc")
    path, _ = case(base)
    monkeypatch.chdir(launch)
    flags = ["--effective"] if command[0] == "config" else []
    code, out, _ = invoke(capsys, *command, path, *flags, "--json", "--cpus", 1,
                          "--output-directory", "./attempt", "--overwrite", "--log-level", "ERROR")
    assert code == 0
    data = envelope(out, "config show --effective" if flags else "validate")["data"]
    conf = data["configuration"]
    assert conf["sources"]["weather"]["files"] == str(base / "input.nc")
    assert conf["output"]["directory"] == str(launch / "attempt")
    assert conf["output"]["overwrite"] is True and conf["logging"]["level"] == "ERROR"
    for key in ("output.directory", "output.overwrite", "resources.cpus", "logging.level"):
        assert data["origins"][key] == "cli"
    assert not (launch / "attempt").exists()
    code, out, _ = invoke(capsys, *command, path, *flags, "--json", "--no-overwrite")
    assert code == 0
    data = envelope(out, "config show --effective" if flags else "validate")["data"]
    assert data["configuration"]["output"]["directory"] == str(base / "out")
    assert data["origins"]["output.directory"] == "yaml"
    assert data["origins"]["output.overwrite"] == "cli"


def test_schema_only_is_offline_with_operational_overrides(tmp_path, monkeypatch, capsys):
    path, _ = case(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Offline validation accessed inputs or checked installed dependencies")

    monkeypatch.setattr("frameit.core.coupled.prepare_sources", forbidden)
    monkeypatch.setattr("frameit.core.preflight.preflight", forbidden)
    code, out, _ = invoke(capsys, "validate", path, "--schema-only", "--cpus", 2, "--json")
    assert code == 0
    report = envelope(out, "validate")
    assert report["data"]["configuration"]["resources"]["cpus"] == 2
    assert "dependencies" in report["deferred_checks"][0]["message"]


@pytest.mark.parametrize("command", [
    ("inspect",), ("validate",), ("config", "show", "--effective")])
@pytest.mark.parametrize("contents,expected", [
    ("schema_version: 3\nsources:\n  weather: {files: missing.nc, model: invented}\n", "E1105"),
    ("schema_version: 3\nsources: {}\nsources: {}\n", "E1103"),
    ("schema_version: 3\nsources: [\n", "E1102"),
    ('schema_version: "3"\nsources: {}\n', "E1104"),
    (None, "E1101"),
])
def test_json_failures_are_one_document_with_repairs_and_nonzero(
        tmp_path, capsys, command, contents, expected):
    path = tmp_path / "bad.yaml"
    if contents is not None:
        path.write_text(contents)
    code, out, _ = invoke(capsys, *command, path, "--json")
    assert code == 1
    report = envelope(out, "config show --effective" if len(command) > 1 else command[0], "error")
    assert report["errors"][0]["repairs"]
    assert report["errors"][0]["code"] == expected
    assert report["errors"][0]["help"] == f"troubleshooting/configuration.html#{expected.lower()}"
    if contents is not None:
        assert report["errors"][0]["locations"]
    assert not (tmp_path / "output").exists()


def test_forbidden_yaml_character_is_reported_as_yaml_in_json(tmp_path, capsys):
    path = tmp_path / "bad.yaml"
    path.write_bytes(b"schema_version: 3\nsources: \x00\n")
    code, out, _ = invoke(capsys, "validate", path, "--schema-only", "--json")
    assert code == 1
    error, = envelope(out, "validate", "error")["errors"]
    assert error["help"] == "troubleshooting/configuration.html#e1102"
    assert "bad.yaml" in error["message"]


@pytest.mark.parametrize("command", ["inspect", "validate"])
def test_competing_file_providers_link_to_field_selection(tmp_path, capsys, command):
    source = create_first_run_input(tmp_path / "input.nc")
    (tmp_path / "copy.nc").write_bytes(source.read_bytes())
    path, raw = case(tmp_path)
    raw["sources"]["weather"]["files"] = ["input.nc", "copy.nc"]
    path.write_text(yaml.safe_dump(raw))
    code, out, _ = invoke(capsys, command, path, "--json")
    assert code == 1
    error, = envelope(out, command, "error")["errors"]
    assert error["help"] == "troubleshooting/fields.html#e1302"
    assert "input.nc" in error["message"] and "copy.nc" in error["message"]
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("command", [("run",), ("validate",), ("config", "show", "--effective")])
def test_overwrite_flags_are_exclusive(tmp_path, capsys, command):
    code, out, err = invoke(capsys, *command, "--overwrite", "--no-overwrite")
    assert code == 2 and not out and "not allowed" in err


@pytest.mark.parametrize("args", [(), ("not-a-command",), ("run", "--bad-option"),
                                  ("validate", "--overwrite", "--no-overwrite")])
def test_argparse_error_is_coded_before_logging(capsys, args):
    code, out, err = invoke(capsys, *args)
    assert code == 2 and not out
    assert "usage:" in err and "[E0001]" in err
    assert "troubleshooting/start.html#e0001" in err
    for command in ((), ("validate",)):
        code, out, err = invoke(capsys, *command, "--help")
        assert code == 0 and "usage:" in out and not err
        assert "[E0001]" not in out


def test_required_startup_import_failure_reports_a_code(monkeypatch, capsys):
    def unavailable():
        raise ModuleNotFoundError("No module named 'yaml'", name="yaml")

    monkeypatch.setattr("frameit.cli._build_parser", unavailable)
    code, out, err = invoke(capsys, "--help")
    assert code == 1 and not out
    assert "[E1001]" in err and "No module named 'yaml'" in err


@pytest.mark.parametrize("command,module", [("run", "pyproj"), ("validate", "numpy")])
def test_required_import_at_command_boundary_reports_e1001(tmp_path, command, module):
    path, _ = case(tmp_path)
    result = subprocess.run([sys.executable, "-c", """
import sys
from frameit.cli import main
command, module, path = sys.argv[1:]
sys.modules[module] = None
main([command, path, *(["--json"] if command == "validate" else [])])
""", command, module, str(path)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 1
    if command == "validate":
        error, = envelope(result.stdout, command, "error")["errors"]
        assert error["help"] == "troubleshooting/start.html#e1001"
    else:
        assert not result.stdout
        assert "[E1001]" in result.stderr and "troubleshooting/start.html#e1001" in result.stderr
    assert not (tmp_path / "out").exists()


def test_starter_failures_explain_the_cause_without_changing_the_file(tmp_path, capsys, caplog):
    path = tmp_path / "starter.yaml"
    path.write_bytes(b"previous file")
    code, _, err = invoke(capsys, "init", "arome", "--output", path)
    assert code == 1 and "[E1106]" in err + caplog.text
    assert path.read_bytes() == b"previous file"
    code, _, err = invoke(capsys, "init", "nemo-native", "--tracking", "fixed_box")
    assert code == 1 and "[E1107]" in err + caplog.text


@pytest.mark.parametrize("args", [("run", "--dry-run"), ("config", "show", "--resolved")])
def test_retired_options_are_rejected_and_not_advertised(capsys, args):
    code, _, err = invoke(capsys, *args)
    assert code == 2 and "unrecognized" in err
    command = args[:-1]
    code, out, _ = invoke(capsys, *command, "--help")
    assert code == 0 and args[-1] not in out


def test_authored_show_does_not_accept_silent_operational_overrides(tmp_path, capsys, caplog):
    path, raw = case(tmp_path)
    code, _, err = invoke(capsys, "config", "show", path, "--cpus", 2)
    assert code != 0 and "--effective" in err + caplog.text
    assert yaml.safe_load(path.read_text()) == raw


def test_run_binds_once_records_all_overrides_and_reopens_without_frameit(
        tmp_path, monkeypatch, capsys):
    source = create_first_run_input(tmp_path / "input.nc")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    path, raw = case(tmp_path)
    from frameit.core import coupled, preflight

    original = coupled.bind_sources
    calls = []

    def bind(*args, **kwargs):
        calls.append(1)
        assert len(calls) == 1, "CLI repeated the owning bind"
        return original(*args, **kwargs)

    monkeypatch.setattr(coupled, "bind_sources", bind)
    monkeypatch.setattr(preflight, "collect_preflight",
                        lambda *a, **k: pytest.fail("extra preflight"))
    code, out, _ = invoke(
        capsys, "run", path, "--output-directory", tmp_path / "attempt", "--cpus", 1,
        "--no-overwrite", "--log-level", "ERROR", "--synchronous-export", "--max-workers", 1,
        "--compress-level", 2, "--institution", "Instructional check")
    assert code == 0 and len(calls) == 1
    root = tmp_path / "attempt"
    request = yaml.safe_load((root / "run-request.yaml").read_text())
    assert request["authored_configuration"] == raw
    assert request["overrides"] == {
        "output_directory": str(root), "cpus": 1, "overwrite": False, "log_level": "ERROR"}
    assert request["requested_execution_options"]["compress_level"] == 2
    assert request["requested_execution_options"]["max_workers"] == 1
    assert request["requested_execution_options"]["setting_sources"][
        "output.writer.compression.level"] == "cli"
    assert request["requested_execution_options"]["setting_sources"][
        "metadata.institution"] == "cli"
    assert request["runtime"]["code_revision"]
    assert "instructional_scalar" in out and "products/cli.weather.model_grid.nc" in out
    assert "xarray" in out and "completed" in out
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    subprocess.run([sys.executable, "-c", """
import sys
import numpy as np
import xarray as xr
assert 'frameit' not in sys.modules
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source:
    np.testing.assert_array_equal(out.instructional_scalar, source.instructional_scalar)
    assert out.instructional_scalar.attrs == source.instructional_scalar.attrs
    np.testing.assert_array_equal(out.time, source.valid_time)
assert 'frameit' not in sys.modules
""", str(root / "products/cli.weather.model_grid.nc"), str(source)], check=True)


def test_cli_logs_go_to_stderr_with_json(tmp_path):
    create_first_run_input(tmp_path / "input.nc")
    path, _ = case(tmp_path)
    result = subprocess.run([sys.executable, "-c", """
import logging,sys
from frameit.cli import main
from frameit.core import preflight
original = preflight.collect_preflight
def collect(*args, **kwargs):
    logging.getLogger('frameit').warning('CLI stderr sentinel')
    return original(*args, **kwargs)
preflight.collect_preflight = collect
main(['validate', sys.argv[1], '--json'])
""", str(path)], capture_output=True, text=True)
    assert result.returncode == 0
    envelope(result.stdout, "validate")
    assert "CLI stderr sentinel" in result.stderr


def test_yaml_log_level_applies_to_report_logging(tmp_path):
    path, raw = case(tmp_path)
    raw["logging"] = {"level": "ERROR"}
    path.write_text(yaml.safe_dump(raw))
    result = subprocess.run([sys.executable, "-c", """
import logging,sys
from frameit.cli import main
from frameit.core import preflight
original = preflight.collect_preflight
def collect(*args, **kwargs):
    logging.getLogger('frameit').warning('SUPPRESSED-WARNING')
    return original(*args, **kwargs)
preflight.collect_preflight = collect
main(['validate', sys.argv[1], '--schema-only', '--json'])
""", str(path)], capture_output=True, text=True)
    assert result.returncode == 0
    envelope(result.stdout, "validate")
    assert "SUPPRESSED-WARNING" not in result.stderr


def test_capabilities_reports_actual_scope_without_importing_optional_backends(tmp_path):
    result = subprocess.run([sys.executable, "-c", """
import sys
from frameit.cli import main
try:
    main(['capabilities', '--json'])
finally:
    optional = {'epygram','cfgrib','eccodes','xesmf','ESMF','esmpy','torch','zarr'}
    assert not optional & sys.modules.keys()
"""], capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    data = envelope(result.stdout, "capabilities")["data"]
    support = data["plan"]["capabilities"]
    assert set(support["sources"]) == {"arome", "mesonh", "nemo", "croco"}
    assert support["sources"]["mesonh"]["formats"] == ["netcdf"]
    assert support["sources"]["nemo"]["formats"] == ["netcdf"]
    assert support["sources"]["arome"]["formats"] == ["netcdf", "grib", "fa"]
    assert support["tracking"]["multifield_vortex"]["maturity"] == (
        "experimental_native_grid_adaptation")
    assert set(support["tracking"]["utrack"]["dependencies"]) == {"torch", "utrack"}
    assert support["tracking"]["utrack"]["models"] == ["arome"]
    assert support["tracking"]["utrack"]["v3_execution"] is False
    assert "weights" in str(support["tracking"]["utrack"]["inputs"])
    assert support["products"]["polar"]["dependencies"] == ["xesmf", "ESMF"]
    assert set(support["products"]) == {"model_grid", "polar", "track"}
    assert "conservative" not in support["products"]["polar"]["interpolation"]
    assert "spectral" in str(support["sources"]["arome"]["limits"])
    assert "not scientific qualification" in support["dependency_check"]
    assert not list(tmp_path.iterdir())


def test_fixture_command_help_has_no_archive_specific_track_name():
    result = subprocess.run(
        [sys.executable, "-m", "frameit", "prepare-ci-dataset", "--help"],
        capture_output=True, text=True, check=True)
    assert "recipe's prescribed track file" in result.stdout
    assert "CHIDO" not in result.stdout


def test_editor_schema_is_generated_from_shared_structural_definitions():
    from importlib import resources

    from frameit.core import configuration as cfg

    assert callable(getattr(cfg, "configuration_schema", None)), "Missing authoritative generator"
    schema = cfg.configuration_schema()
    asset = resources.files("frameit").joinpath("schemas/config-v3.schema.json")
    assert json.loads(asset.read_text()) == schema
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"] == {"type": "integer", "const": 3}
    assert schema["required"] == ["schema_version", "sources"]
    assert set(schema["properties"]) == set(cfg.DEFAULTS)
    for name, keys in cfg.V3_KEYS.items():
        assert set(schema["$defs"][name]["properties"]) == set(keys), name
        assert schema["$defs"][name]["additionalProperties"] is False
    for name, choices in cfg.V3_CHOICES.items():
        assert schema["$defs"]["choices_" + name]["enum"] == list(choices)
    assert schema["$defs"]["metadata"]["properties"]["extra"] == {
        "type": "object", "additionalProperties": True, "default": {}}
    assert schema["$defs"]["source"]["required"] == ["files"]
    assert schema["$defs"]["source"]["properties"]["variables"] == {"$ref": "#/$defs/variables"}
    assert schema["$defs"]["variables"]["properties"]["2d"]["items"] == {"$ref": "#/$defs/text"}
    assert schema["$defs"]["compression"]["properties"]["level"]["maximum"] == 9
    assert schema["$defs"]["compression"]["properties"]["level"]["minimum"] == 0
    assert schema["$defs"]["compression"]["properties"]["level"]["default"] == 1
    assert schema["$defs"]["reader"]["properties"]["chunks"]["additionalProperties"]["anyOf"] == [
        {"type": "integer", "minimum": 1}, {"const": -1}]
    assert schema["$defs"]["writer"]["properties"]["chunks"]["additionalProperties"] == {
        "type": "integer", "minimum": 1}
    assert schema["properties"]["sources"]["propertyNames"]["pattern"] == (
        "^[A-Za-z][A-Za-z0-9_-]*$")
    assert not any("default" in spec and spec["default"] is None
                   for definition in schema["$defs"].values()
                   for spec in definition.get("properties", {}).values())


@pytest.mark.parametrize("value", [None, [], "wrong"])
def test_schema_annotation_exception_does_not_allow_null_scientific_controls(tmp_path, value):
    from frameit.core.configuration import resolve_schema

    _, raw = case(tmp_path)
    raw["metadata"]["extra"] = {"annotation": value, "nested": [None, {}]}
    resolved = resolve_schema(raw, base_dir=tmp_path)[0]
    assert resolved["metadata"]["extra"] == raw["metadata"]["extra"]
    raw["sources"]["weather"]["variables"] = None
    with pytest.raises(ValueError, match="omit"):
        resolve_schema(raw, base_dir=tmp_path)


@pytest.mark.parametrize("state,exit_code", [
    ("completed", 0), ("incomplete", 0), ("running", 1), ("failed", 1), ("interrupted", 1),
])
def test_status_reads_only_portable_records_without_inputs_or_products(
        tmp_path, monkeypatch, capsys, state, exit_code):
    root = tmp_path / "run"
    root.mkdir()
    status = {
        "schema_version": 1, "state": state, "started_at": "2000-01-01T00:00:00+00:00",
        "updated_at": "2000-01-01T01:00:00+00:00", "finished_at": None,
        "products": [{"source": "weather", "role": "model_grid",
                      "path": "products/actual.nc", "fields": ["temperature"],
                      "units": {"temperature": "K"}}],
        "planned_products": [{"path": "products/not-published.nc", "fields": ["planned_field"]}],
        "pending": [] if state in {"completed", "incomplete"} else ["publication", "cleanup"],
        "warnings": ["recorded warning"],
        "error": {"type": "ValueError", "message": "recorded failure"},
        "tracking_termination_reason": "lost support" if state == "incomplete" else "",
    }
    (root / "run-status.yaml").write_text(yaml.safe_dump(status))
    provenance = {
        **status, "runtime": {"frameit_version": "test"}, "execution_options": {},
        "execution_resources": {}, "sources": {},
        "binding": {"weather": {"excluded_files": ["missing-excluded.nc"]}},
    }
    (root / "run-provenance.yaml").write_text(yaml.safe_dump(provenance))
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    original = Path.read_text

    def fixed_records_only(path, *args, **kwargs):
        assert path.parent == root and path.name in {
            "run-status.yaml", "run-provenance.yaml", "run-request.yaml", "resolved-config.yaml"}
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fixed_records_only)
    monkeypatch.setattr(Path, "glob", lambda *a, **k: pytest.fail("status scanned a directory"))
    monkeypatch.setattr(Path, "rglob", lambda *a, **k: pytest.fail("status scanned a payload"))
    code, out, _ = invoke(capsys, "status", root)
    assert code == exit_code
    assert f"Last-recorded state: {state}" in out
    for fact in ("temperature", "products/actual.nc", "Planned", "products/not-published.nc",
                 "recorded warning", "missing-excluded.nc", "xarray", "not a liveness"):
        assert fact.lower() in out.lower()
    if state == "incomplete":
        assert "Accepted incomplete tracking" in out and "lost support" in out
    if state in {"failed", "interrupted"}:
        assert "recorded failure" in out
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


@pytest.mark.parametrize("contents", [None, "not a mapping", "schema_version: 2\n",
                                     "schema_version: 1\nstate: invented\nproducts: []\n"])
def test_missing_or_unrecognized_status_is_actionable_and_never_creates_root(
        tmp_path, capsys, caplog, contents):
    root = tmp_path / "run"
    if contents is not None:
        root.mkdir()
        (root / "run-status.yaml").write_text(contents)
    code, out, err = invoke(capsys, "status", root)
    assert code == 1
    assert "run-status.yaml" in out + err + caplog.text
    assert "[E1807]" in out + err + caplog.text
    assert "troubleshooting/outputs.html#e1807" in out + err + caplog.text
    assert "record" in (out + err + caplog.text).lower()
    if contents is None:
        assert not root.exists()


def test_status_does_not_mix_a_different_provenance_checkpoint(tmp_path, capsys):
    status = {
        "schema_version": 1, "state": "running", "started_at": "2000-01-01T00:00:00",
        "updated_at": "current", "products": [], "pending": ["processing"],
    }
    (tmp_path / "run-status.yaml").write_text(yaml.safe_dump(status))
    (tmp_path / "run-provenance.yaml").write_text(yaml.safe_dump({
        **status, "updated_at": "old", "state": "completed",
        "warnings": ["STALE-PROVENANCE-MUST-NOT-BE-CURRENT"]}))
    code, out, _ = invoke(capsys, "status", tmp_path)
    assert code == 1 and "checkpoint" in out.lower()
    assert "[W1801]" in out
    assert "STALE-PROVENANCE" not in out
    assert "unavailable" in out.lower() and "not a liveness" in out


def test_status_read_that_changes_reports_e1809(tmp_path, capsys, caplog, monkeypatch):
    from frameit.core import configuration

    path = tmp_path / "run-status.yaml"
    path.write_text(yaml.safe_dump({
        "schema_version": 1, "state": "running", "started_at": "first", "products": [],
    }))
    original = configuration.read_yaml
    reads = iter(("first", "second"))

    def advancing(path, **kwargs):
        return {**original(path, **kwargs), "updated_at": next(reads)}

    monkeypatch.setattr(configuration, "read_yaml", advancing)
    code, out, err = invoke(capsys, "status", tmp_path)
    assert code == 1 and not out
    assert "[E1809]" in err + caplog.text


def test_disappearing_status_keeps_file_not_found_type(tmp_path, monkeypatch):
    from frameit.core import configuration, run_state

    path = tmp_path / "run-status.yaml"
    path.write_text(yaml.safe_dump({
        "schema_version": 1, "state": "running", "started_at": "first", "products": [],
    }))
    original = configuration.read_yaml

    def disappear_after_first_snapshot(path, **kwargs):
        initial = original(path, **kwargs)
        path.unlink()
        return initial

    monkeypatch.setattr(configuration, "read_yaml", disappear_after_first_snapshot)
    with pytest.raises(FileNotFoundError) as exc:
        run_state.read_run_status(tmp_path)
    assert exc.value.frameit_code == "E1809"
    assert exc.value.filename == str(path)


@pytest.mark.parametrize("number", [errno.ENOSPC, errno.EDQUOT])
def test_output_filesystem_exhaustion_keeps_its_code(
        tmp_path, capsys, monkeypatch, number):
    from frameit.core import run_state

    create_first_run_input(tmp_path / "input.nc")
    path, _ = case(tmp_path)
    original = run_state.write_yaml_atomic

    def writing(path, value, **kwargs):
        if Path(path).name == "run-request.yaml":
            raise OSError(number, "test filesystem limit")
        return original(path, value, **kwargs)

    monkeypatch.setattr(run_state, "write_yaml_atomic", writing)
    code, out, _ = invoke(capsys, "run", path)
    assert code == 1 and "code: E1810" in out
    status = yaml.safe_load((tmp_path / "out/run-status.yaml").read_text())
    assert status["state"] == "failed" and status["products"] == []
    assert status["error"]["code"] == "E1810"


def test_failed_run_never_presents_an_old_or_concurrent_inventory_as_current(
        tmp_path, monkeypatch, capsys, caplog):
    path, _ = case(tmp_path)
    root = tmp_path / "out"
    root.mkdir()
    (root / "run-status.yaml").write_text(yaml.safe_dump({
        "schema_version": 1, "state": "completed", "started_at": "old",
        "products": [{"path": "products/STALE-SUCCESS.nc"}],
    }))

    def fail(*args, **kwargs):
        raise FileExistsError("Current attempt did not acquire ownership")

    monkeypatch.setattr("frameit.core.execution.execute_simulation", fail)
    code, out, err = invoke(capsys, "run", path)
    assert code == 1
    assert "Current attempt did not acquire ownership" in out + err + caplog.text
    assert "inventory unavailable" in out.lower()
    assert "STALE-SUCCESS" not in out


def test_owned_failure_keeps_operational_request_without_rereading_yaml(
        tmp_path, monkeypatch, capsys):
    create_first_run_input(tmp_path / "input.nc")
    path, raw = case(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fail(runner, **kwargs):
        path.write_text("schema_version: 4\n")
        raise RuntimeError("Instructional failure after ownership")

    monkeypatch.setattr("frameit.core.runner.FrameitRunner.run", fail)
    code, out, _ = invoke(capsys, "run", path, "--output-directory", "./attempt",
                          "--cpus", 1, "--no-export", "--log-level", "ERROR")
    assert code == 1 and "owner-attested" in out.lower()
    assert "inventory unavailable" not in out.lower()
    request = yaml.safe_load((Path.cwd() / "attempt/run-request.yaml").read_text())
    assert request["authored_configuration"] == raw
    assert request["overrides"]["output_directory"] == "attempt"
    assert request["requested_execution_options"]["export_netcdf"] is False


@pytest.mark.parametrize("flag,option,published", [
    ("--no-export", "export_netcdf", False),
    ("--no-export-cartesian", "export_cart", False),
    ("--no-export-polar", "export_polar", True),
])
def test_nonretired_publication_suppression_is_recorded_without_selecting_products(
        tmp_path, capsys, flag, option, published):
    create_first_run_input(tmp_path / "input.nc")
    path, _ = case(tmp_path)
    code, _, _ = invoke(capsys, "run", path, flag, "--no-hdf5-debug-pop", "--log-level", "ERROR")
    assert code == 0
    root = tmp_path / "out"
    request = yaml.safe_load((root / "run-request.yaml").read_text())
    assert request["requested_execution_options"][option] is False
    assert request["requested_execution_options"]["no_hdf5_debug_pop"] is True
    status = yaml.safe_load((root / "run-status.yaml").read_text())
    assert bool(status["products"]) is published
    assert all(item["role"] == "model_grid" for item in status["products"])
    assert {item["product"] for item in status["planned_products"]} == {"model_grid"}


def test_status_syntax_errors_keep_argparse_exit_two(capsys):
    code, out, err = invoke(capsys, "status")
    assert code == 2 and not out and "run_directory" in err


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("cart,polar,track,select_polar,expected", [
    (True, True, True, True, {"model_grid", "polar", "track"}),
    (False, True, True, True, {"polar", "track"}),
    (True, False, True, True, {"model_grid", "track"}),
    (False, False, True, True, {"track"}),
    (False, False, False, True, set()),
    (False, False, False, False, set()),
])
def test_publication_filter_keeps_plan_track_callbacks_and_actual_records(
        tmp_path, monkeypatch, capsys, fmt, cart, polar, track, select_polar, expected):
    from frameit.io import netcdf_export

    source = create_first_run_input(tmp_path / "input.nc")
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    path, raw = case(tmp_path)
    raw["output"]["format"] = fmt
    if track or select_polar:
        raw["region"] = {"center": {"latitude": -20., "longitude": 60.}}
    raw["sources"]["weather"]["field_metadata"] = {
        "instructional_scalar": {"kind": "continuous"}}
    raw["products"] = {"model_grid": True}
    if select_polar:
        raw["products"]["polar"] = {"radius_km": 2, "radial_step_km": 2, "azimuth_count": 4}
    if track:
        raw["products"]["track"] = True
    path.write_text(yaml.safe_dump(raw))
    original_request = path.read_bytes()
    callbacks = []
    export = netcdf_export.export_outputs

    def exporting(runner, **kwargs):
        planned = deepcopy(runner.conf.simulation_parameter["request_plan"]["products"])
        published = kwargs["on_published"]

        def callback(item):
            assert item in runner.published_products
            callbacks.append(deepcopy(item))
            published(item)

        kwargs["on_published"] = callback
        result = export(runner, **kwargs)
        assert runner.conf.simulation_parameter["request_plan"]["products"] == planned
        assert {item["role"] for item in runner.published_products} == expected
        if not track and not select_polar:
            assert runner.track is None
        return result

    monkeypatch.setattr(netcdf_export, "export_outputs", exporting)
    if not expected:
        monkeypatch.setattr(netcdf_export, "_export_pool",
                            lambda *a, **k: pytest.fail("Empty publication started a pool"))
    flags = ([] if cart else ["--no-export-cartesian"]) + (
        [] if polar else ["--no-export-polar"])
    code, out, _ = invoke(capsys, "run", path, "--log-level", "ERROR", *flags)
    assert code == 0
    root = tmp_path / "out"
    status = yaml.safe_load((root / "run-status.yaml").read_text())
    provenance = yaml.safe_load((root / "run-provenance.yaml").read_text())
    assert status["state"] == "completed" and status["pending"] == []
    assert len(callbacks) == len(expected) == len(status["products"])
    assert {item["role"] for item in status["products"]} == expected
    assert status["products"] == provenance["products"]
    assert status["planned_products"] == provenance["planned_products"]
    assert {item["product"] for item in status["planned_products"]} == set(raw["products"])
    assert {item.name for item in (root / "products").iterdir()} == {
        Path(item["path"]).name for item in status["products"]}
    assert "completed" in out
    subprocess.run([sys.executable, "-c", """
import json,sys
import numpy as np
import xarray as xr
assert 'frameit' not in sys.modules
products = json.loads(sys.argv[3])
with xr.open_dataset(sys.argv[2]) as source:
    for product in products:
        path = sys.argv[1] + '/' + product['path']
        opener = xr.open_zarr if path.endswith('.zarr') else xr.open_dataset
        options = {'consolidated':False} if path.endswith('.zarr') else {}
        with opener(path, **options) as out:
            role = product['role']
            assert out.attrs['product_type'] == role
            if role == 'track':
                np.testing.assert_array_equal(out.latitude, [-20., -20.])
                np.testing.assert_array_equal(out.longitude, [60., 60.])
                assert out.latitude.attrs['units'] == 'degrees_north'
            else:
                assert 'instructional_scalar' in out
                assert out.instructional_scalar.attrs['units'] == '1'
                if role == 'model_grid':
                    np.testing.assert_array_equal(out.instructional_scalar,
                                                  source.instructional_scalar)
                else:
                    assert out.instructional_scalar.dims == ('time','radius','azimuth')
                    assert out.radius.attrs['units'] == 'km'
assert 'frameit' not in sys.modules
""", str(root), str(source), json.dumps(status["products"])], check=True,
        capture_output=True, text=True)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original
    assert path.read_bytes() == original_request


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("failure,exit_code,state", [
    (OSError, 1, "failed"), (KeyboardInterrupt, 130, "interrupted"),
])
def test_owned_failure_summary_uses_actual_retained_products_after_unwind(
        tmp_path, monkeypatch, capsys, fmt, failure, exit_code, state):
    from frameit.io import netcdf_export
    from frameit.testing.numerical.test_v3_run_state import ordinary_reader, two_sources

    conf = two_sources(tmp_path, fmt, True)
    path = tmp_path / "request.yaml"
    path.write_text(yaml.safe_dump(conf.request_context["authored_configuration"], sort_keys=False))
    request_bytes = path.read_bytes()
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (tmp_path / "input.nc", tmp_path / "ocean.nc")}
    write = netcdf_export._write_product
    calls = []

    def writing(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise failure("B2 second publication stopped")
        return write(*args, **kwargs)

    monkeypatch.setattr(netcdf_export, "_write_product", writing)
    monkeypatch.setattr("frameit.core.run_state.read_run_status",
                        lambda *a, **k: pytest.fail("Failure summary reread disk records"))
    code, out, _ = invoke(capsys, "run", path, "--log-level", "ERROR")
    assert code == exit_code
    assert out.startswith(f"Run state: {state}")
    assert "owner-attested" in out.lower() and "inventory unavailable" not in out.lower()
    assert "B2 second publication stopped" in out and "publication" in out
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    assert status["state"] == state and len(status["products"]) == 1
    assert status["products"] == provenance["products"]
    product, = status["products"]
    assert product["source"] == "weather" and product["path"] in out
    assert "instructional_scalar" in out and "records.water.model_grid" not in out
    assert not (conf.output_dir / ".frameit-run.lock").exists()
    ordinary_reader(conf.output_dir, product, tmp_path / "input.nc",
                    "instructional_scalar", "valid_time", fmt)
    assert path.read_bytes() == request_bytes
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes} == hashes


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("record_name", ["run-provenance.yaml", "run-status.yaml"])
def test_final_record_failure_is_not_current_success_or_persisted_checkpoint(
        tmp_path, monkeypatch, capsys, fmt, record_name):
    from frameit.core import run_state
    from frameit.testing.numerical.test_v3_run_state import two_sources

    conf = two_sources(tmp_path, fmt, True)
    path = tmp_path / "request.yaml"
    path.write_text(yaml.safe_dump(conf.request_context["authored_configuration"], sort_keys=False))
    original = run_state.write_yaml_atomic

    def writing(path, value, **kwargs):
        if Path(path).name == record_name and value.get("state") == "completed":
            raise OSError("B2 final checkpoint stopped")
        return original(path, value, **kwargs)

    monkeypatch.setattr(run_state, "write_yaml_atomic", writing)
    code, out, _ = invoke(capsys, "run", path, "--log-level", "ERROR")
    assert code == 1 and out.startswith("Run state: failed")
    assert "owner-attested" in out.lower() and "B2 final checkpoint stopped" in out
    assert "code: E1808" in out
    assert "persistence" in out.lower() and "not verified" in out.lower()
    assert "Run state: completed" not in out
    for source in ("weather", "water"):
        assert f"records.{source}.model_grid." in out
    if record_name == "run-status.yaml":
        assert "observed_owner_state: completed" in out
        assert yaml.safe_load((conf.output_dir / record_name).read_text())["state"] == "running"
    else:
        assert "observed_owner_state: failed" in out
    assert not (conf.output_dir / ".frameit-run.lock").exists()


@pytest.mark.parametrize("during", ["execution_checkpoint", "owned_run"])
def test_failed_finalization_does_not_replace_cancellation(tmp_path, monkeypatch, capsys, during):
    from frameit.core import run_state
    from frameit.utils.diagnostics import tag_error

    create_first_run_input(tmp_path / "input.nc")
    path, _ = case(tmp_path)
    original = run_state.write_yaml_atomic
    interrupted = False

    def cancel(*args, **kwargs):
        nonlocal interrupted
        interrupted = True
        raise tag_error(SystemExit(143), "E0002")

    def writing(path, value, **kwargs):
        if (interrupted and Path(path).name == "run-status.yaml"
                and (during == "execution_checkpoint" or value["state"] == "interrupted")):
            raise PermissionError("test: cannot finish writing status")
        return original(path, value, **kwargs)

    monkeypatch.setattr("frameit.core.runner.FrameitRunner.run", cancel)
    monkeypatch.setattr(run_state, "write_yaml_atomic", writing)
    code, out, _ = invoke(capsys, "run", path, "--log-level", "ERROR")
    assert code == 143 and out.startswith("Run state: interrupted")
    assert "code: E0002" in out
    assert "final record persistence is not verified" in " ".join(out.split())
    root = tmp_path / "out"
    assert yaml.safe_load((root / "run-status.yaml").read_text())["state"] == "running"
    assert not (root / ".frameit-run.lock").exists()
    log, = (root / "logs").glob("*.log")
    assert "[E1808]" in log.read_text()


@pytest.mark.parametrize("boundary", ["locked", "initial_record"])
def test_real_unowned_failure_keeps_old_records_out_of_summary(
        tmp_path, monkeypatch, capsys, caplog, boundary):
    from frameit.core import run_state

    create_first_run_input(tmp_path / "input.nc")
    path, _ = case(tmp_path)
    root = tmp_path / "out"
    root.mkdir()
    old = {"schema_version": 1, "state": "completed", "started_at": "old",
           "products": [{"path": "products/STALE-ATTEMPT.nc"}]}
    record = root / "run-status.yaml"
    record.write_text(yaml.safe_dump(old))
    original_bytes = record.read_bytes()
    if boundary == "locked":
        (root / ".frameit-run.lock").write_text("another owner")
    else:
        original = run_state.write_yaml_atomic

        def writing(path, value, **kwargs):
            if Path(path).name == "run-request.yaml":
                raise OSError("initial request record stopped")
            return original(path, value, **kwargs)

        monkeypatch.setattr(run_state, "write_yaml_atomic", writing)
    code, out, _ = invoke(capsys, "run", path, "--overwrite", "--log-level", "ERROR")
    assert code == 1 and "inventory unavailable" in out.lower()
    assert "owner-attested" not in out.lower() and "STALE-ATTEMPT" not in out
    assert f"code: {'E1801' if boundary == 'locked' else 'E1808'}" in out
    if boundary == "locked":
        assert "troubleshooting/outputs.html#e1801" in caplog.text
        assert record.read_bytes() == original_bytes
    else:
        assert yaml.safe_load(record.read_text())["state"] == "failed"


@pytest.mark.parametrize("boundary", ["attachment", "rendering"])
def test_summary_failure_never_replaces_the_primary_owned_exception(
        tmp_path, monkeypatch, capsys, boundary):
    from frameit import cli

    class PrimaryFailure(RuntimeError):
        def __setattr__(self, key, value):
            if boundary == "attachment" and key == "_frameit_failure":
                raise OSError("summary attachment unavailable")
            super().__setattr__(key, value)

    failure = PrimaryFailure("primary owned failure")
    create_first_run_input(tmp_path / "input.nc")
    path, _ = case(tmp_path)

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr("frameit.core.runner.FrameitRunner.run", fail)
    if boundary == "rendering":
        def unavailable(*args, **kwargs):
            raise OSError("summary rendering unavailable")

        monkeypatch.setattr("frameit.core.reports.render_run_summary", unavailable)
    args = cli._build_parser().parse_args(["run", str(path), "--log-level", "ERROR"])
    with pytest.raises(PrimaryFailure) as observed:
        cli._cmd_run(args)
    assert observed.value is failure
    status = yaml.safe_load((tmp_path / "out/run-status.yaml").read_text())
    assert status["state"] == "failed"
    assert status["error"]["code"] == "E0999"
    if boundary == "attachment":
        assert "inventory unavailable" in capsys.readouterr().out.lower()


def test_failed_publication_checkpoint_does_not_turn_memory_facts_into_persistence(
        tmp_path, monkeypatch, capsys):
    from frameit.core import run_state
    from frameit.testing.numerical.test_v3_run_state import ordinary_reader

    source = create_first_run_input(tmp_path / "input.nc")
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    path, _ = case(tmp_path)
    original = run_state.write_yaml_atomic

    def writing(path, value, **kwargs):
        if Path(path).name == "run-status.yaml" and value["products"]:
            raise OSError("publication checkpoint unavailable")
        return original(path, value, **kwargs)

    monkeypatch.setattr(run_state, "write_yaml_atomic", writing)
    code, out, _ = invoke(capsys, "run", path, "--log-level", "ERROR")
    assert code == 1 and out.startswith("Run state: failed")
    assert "owner-attested" in out.lower() and "not verified" in out.lower()
    assert "actual recorded publications" not in out
    assert "products/cli.weather.model_grid.nc" in out
    status = yaml.safe_load((tmp_path / "out/run-status.yaml").read_text())
    assert status["state"] == "running" and status["products"] == []
    ordinary_reader(tmp_path / "out", {"path": "products/cli.weather.model_grid.nc"},
                    source, "instructional_scalar", "valid_time", "netcdf")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash


@pytest.mark.parametrize("key,default", [("search_width_km", 200.), ("refine_width_km", 100.)])
def test_editor_pressure_wind_widths_match_runtime_positive_numbers(tmp_path, key, default):
    from importlib import resources

    from frameit.core.configuration import configuration_schema, resolve_schema

    raw = {
        "schema_version": 3,
        "sources": {"weather": {"model": "arome", "files": "./input.nc"}},
        "region": {"tracker": {"method": "pressure_wind"}},
    }
    original = deepcopy(raw)
    assert resolve_schema(raw, base_dir=tmp_path)[0]["region"]["tracker"][key] == default
    for value in (default, 72, 12.5):
        request = deepcopy(raw)
        request["region"]["tracker"][key] = value
        assert resolve_schema(request, base_dir=tmp_path)[0]["region"]["tracker"][key] == value
        request["region"]["tracker"][key] = str(value)
        with pytest.raises(ValueError, match=key + ": must be a finite number"):
            resolve_schema(request, base_dir=tmp_path)
    asset = resources.files("frameit").joinpath("schemas/config-v3.schema.json")
    for schema in (configuration_schema(), json.loads(asset.read_text())):
        tracker = next(item for item in schema["$defs"]["region"]["properties"]["tracker"]["oneOf"]
                       if item["properties"]["method"]["const"] == "pressure_wind")
        assert tracker["properties"][key] == {
            "type": "number", "exclusiveMinimum": 0, "default": default}
    assert raw == original and not list(tmp_path.iterdir())


@pytest.mark.parametrize("annotation,expected", [
    ("2026-11-15", "2026-11-15"),
    ("2026-11-15T08:30:00Z", "2026-11-15T08:30:00+00:00"),
    ("!!set {survey: null}", ["survey"]),
    ("!!binary SGVsbG8=", {"hex": "48656c6c6f"}),
    (".nan", {"nonfinite": "nan"}),
    (".inf", {"nonfinite": "inf"}),
    ("-.inf", {"nonfinite": "-inf"}),
])
def test_authored_json_projects_yaml_annotations_without_defaults_or_mutation(
        tmp_path, monkeypatch, capsys, annotation, expected):
    from frameit.core import configuration as cfg

    source = tmp_path / "input.nc"
    source.write_bytes(b"Must not open or alter this instructional source.")
    path = tmp_path / "request.yaml"
    path.write_text(
        "schema_version: 3\nsources:\n  weather: {model: arome, files: ./input.nc}\n"
        "metadata:\n  extra:\n    annotation: " + annotation + "\n    nested: [null, {note: μ}]\n")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    authored = cfg.read_yaml(path)
    resolved = cfg.resolve_schema(authored, base_dir=tmp_path)[0]
    assert yaml.safe_dump(resolved["metadata"]["extra"]) == yaml.safe_dump(
        authored["metadata"]["extra"])
    read, loaded = cfg.read_yaml, []

    def reading(request):
        value = read(request)
        loaded.append((value, yaml.safe_dump(value)))
        return value

    def forbidden(*args, **kwargs):
        pytest.fail("Authored show accessed datasets or collected an effective plan")

    monkeypatch.setattr(cfg, "read_yaml", reading)
    monkeypatch.setattr("xarray.open_dataset", forbidden)
    monkeypatch.setattr("xarray.open_mfdataset", forbidden)
    monkeypatch.setattr("frameit.core.preflight.collect_preflight", forbidden)
    monkeypatch.setattr("frameit.core.coupled.prepare_sources", forbidden)
    code, out, _ = invoke(capsys, "config", "show", path, "--json")
    assert code == 0
    value = json.loads(out, parse_constant=lambda item: pytest.fail("Non-strict JSON: " + item))
    assert value == {
        "schema_version": 3,
        "sources": {"weather": {"model": "arome", "files": "./input.nc"}},
        "metadata": {"extra": {"annotation": expected, "nested": [None, {"note": "μ"}]}},
    }
    code, out, _ = invoke(capsys, "config", "show", path)
    assert code == 0 and yaml.safe_dump(yaml.safe_load(out)) == yaml.safe_dump(authored)
    assert all(yaml.safe_dump(value) == original for value, original in loaded)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
