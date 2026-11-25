"""C9 projection of existing preflight facts; never an executable plan."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from frameit.utils.diagnostics import (
    CODE_TOPICS,
    UNEXPECTED_ERROR,
    diagnostic_path,
    exception_code,
    format_message,
)

if TYPE_CHECKING:
    from frameit.core.settings_class import SimulationConfig

REPORT_VERSION = 1
_REPORT_KEYS = {"report_version", "command", "status", "data", "warnings", "errors",
                "deferred_checks"}
_DATA_KEYS = {"configuration", "origins", "inputs", "plan", "pending"}
_TERMINAL_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\ud800-\udfff]")


@dataclass
class Diagnostic:
    path: str
    message: str
    expected: Any
    observed: Any
    repairs: list[str]
    locations: list[dict] = field(default_factory=list)
    contexts: list[dict] = field(default_factory=list)
    code: str = field(kw_only=True)


class PreflightError(ValueError):
    """Carry known causes and partial metadata through existing fail-closed APIs."""

    def __init__(self, diagnostics, *, facts=None, deferred_checks=()):
        self.diagnostics = diagnostics
        self.facts = facts or {}
        self.deferred_checks = list(deferred_checks)
        super().__init__(str(self))

    def __str__(self):
        return "\n".join(
            format_message(error.code, f"{error.path}: {error.message}")
            + "".join(f"; {context}" for context in error.contexts)
            + "".join(f"; {mark['file']}: line {mark['line']}, column {mark['column']}"
                      for mark in error.locations)
            for error in self.diagnostics)


@dataclass
class PreflightResult:
    command: str
    conf: SimulationConfig | None = None
    facts: dict = field(default_factory=dict)
    errors: list[Diagnostic] = field(default_factory=list)
    deferred_checks: list[dict] = field(default_factory=list)


def exception_diagnostics(exc, *, path, expected, observed, repairs):
    """Retain structured boundary facts; opaque adapter failures stay opaque."""
    if isinstance(exc, PreflightError):
        return exc.diagnostics
    return [Diagnostic(path, str(exc), expected, observed, repairs, code=exception_code(exc))]


def blocked_check(path, prerequisites, message):
    return {"path": path, "status": "blocked",
            "prerequisites": list(dict.fromkeys(prerequisites)), "message": message}


def _metadata_view(value):
    """Copy metadata only; large coordinate arrays are described, never computed."""
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float:
        return value if math.isfinite(value) else {"nonfinite": str(value)}
    if isinstance(value, dict):
        return {str(key): _metadata_view(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_metadata_view(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"hex": value.hex()}
    # Plain metadata, including startup failures, requires no scientific imports.
    import cftime
    import numpy as np
    import xarray as xr

    if isinstance(value, (xr.Dataset, xr.DataArray)):
        return {"dimensions": dict(value.sizes), "attributes": _metadata_view(value.attrs)}
    if isinstance(value, np.ndarray):
        if value.ndim <= 1 and value.size <= 16:
            return [_metadata_view(item) for item in value.reshape(-1)]
        return {"shape": list(value.shape), "dtype": str(value.dtype),
                "values": "omitted coordinate metadata"}
    if isinstance(value, cftime.datetime):
        return {"label": str(value), "calendar": value.calendar}
    if isinstance(value, (np.datetime64, np.timedelta64)):
        return str(value)
    if isinstance(value, np.generic):
        return _metadata_view(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    return value


def _diagnostic_item(error, conf=None):
    return _metadata_view({
        "code": error.code, "help": diagnostic_path(error.code),
        "path": error.path, "message": error.message, "expected": error.expected,
        "observed": error.observed, "repairs": error.repairs,
        "locations": diagnostic_locations(error, conf), "contexts": error.contexts,
    })


def preflight_diagnostics(exc: BaseException) -> list[Diagnostic]:
    """Find structured causes beneath wrappers that do not own a diagnosis."""
    seen = set()
    cause = exc
    while cause is not None and id(cause) not in seen:
        code = getattr(cause, "frameit_code", UNEXPECTED_ERROR)
        if isinstance(code, str) and code != UNEXPECTED_ERROR and code in CODE_TOPICS:
            break
        if isinstance(cause, PreflightError) and cause.diagnostics:
            return cause.diagnostics
        seen.add(id(cause))
        cause = cause.__cause__
    return []


def primary_error_code(exc: BaseException) -> str:
    diagnostics = preflight_diagnostics(exc)
    return diagnostics[0].code if diagnostics else exception_code(exc)


def error_record(exc: BaseException) -> dict:
    """Keep the cause codes when reporting or recording a failed run."""
    record = {"type": type(exc).__name__, "message": str(exc), "code": primary_error_code(exc)}
    if diagnostics := preflight_diagnostics(exc):
        record["diagnostics"] = [_diagnostic_item(error) for error in diagnostics]
    return record


def project_report(result):
    """Return the seven-key JSON-safe view without changing internal decoded facts."""
    from frameit.core.configuration import resolved_configuration, resolved_sources

    facts, conf = result.facts, result.conf
    configuration = facts.get("configuration")
    origins = facts.get("setting_sources", {})
    if conf is not None:
        if configuration is None:
            configuration = resolved_configuration(conf)
        if not origins:
            origins = resolved_sources(conf)
    origins = dict(origins)
    for name, source in facts.get("sources", {}).items():
        for key, origin in source.get("metadata_origins", {}).items():
            origins[f"inputs.sources.{name}.{key}"] = origin
    errors = []
    for error in result.errors:
        item = _diagnostic_item(error, conf)
        repeated = next((previous for previous in errors if all(
            previous[key] == item[key] for key in (
                "code", "path", "message", "expected", "observed", "repairs"))), None)
        if repeated is None:
            errors.append(item)
        else:
            for key in ("contexts", "locations"):
                repeated[key].extend(entry for entry in item[key] if entry not in repeated[key])
    plan = {key: value for key, value in facts.items() if key not in {
        "configuration", "setting_sources", "inputs", "warnings", "deferred_checks",
    }}
    return {
        "report_version": REPORT_VERSION, "command": result.command,
        "status": "error" if errors else "ok",
        "data": _metadata_view({
            "configuration": configuration, "origins": origins,
            "inputs": facts.get("inputs", []), "plan": plan,
            "pending": result.deferred_checks,
        }),
        "warnings": _metadata_view(facts.get("warnings", [])), "errors": errors,
        "deferred_checks": _metadata_view(result.deferred_checks),
    }


def serialize_report(result):
    return serialize_projection(project_report(result))


def serialize_projection(report):
    return json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)


def _validate_saved_values(value):
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_saved_values(key)
            _validate_saved_values(child)
    elif isinstance(value, list):
        for child in value:
            _validate_saved_values(child)
    elif isinstance(value, str) and _TERMINAL_CONTROL.search(value):
        raise ValueError("Saved report contains terminal control characters or invalid Unicode.")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Saved report contains nonfinite JSON numbers.")


def load_saved_report(path, command):
    """Read a versioned public projection; none of its referenced files are opened."""
    if not path.is_file():
        raise ValueError("Expected a regular JSON report file.")
    try:
        with path.open(encoding="utf-8") as stream:
            report = json.load(stream)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"Invalid saved report JSON: {exc}") from None
    if not isinstance(report, dict) or set(report) != _REPORT_KEYS:
        raise ValueError("Not a complete FrameIt report envelope.")
    if type(report["report_version"]) is not int or report["report_version"] != REPORT_VERSION:
        raise ValueError(f"Unsupported report version (expected {REPORT_VERSION}).")
    if report["command"] != command:
        raise ValueError(f"Expected a saved {command} report; use its original command.")

    data = report["data"]
    if (not isinstance(data, dict) or set(data) != _DATA_KEYS
            or (data["configuration"] is not None
                and not isinstance(data["configuration"], dict))
            or not all(isinstance(data[key], dict) for key in ("origins", "plan"))
            or not all(isinstance(data[key], list) for key in ("inputs", "pending"))):
        raise ValueError("Incomplete report data.")

    def strings(value):
        return isinstance(value, list) and all(isinstance(item, str) for item in value)

    errors, warnings, checks = (report[key] for key in ("errors", "warnings", "deferred_checks"))
    if (not all(isinstance(value, list) for value in (errors, checks)) or not strings(warnings)
            or report["status"] != ("error" if errors else "ok")):
        raise ValueError("Incomplete diagnostics or inconsistent report outcome.")
    for item in errors:
        if (not isinstance(item, dict) or not {"expected", "observed"} <= item.keys()
                or not all(isinstance(item.get(key), str)
                           for key in ("code", "path", "message", "help"))
                or not strings(item.get("repairs"))
                or not all(isinstance(item.get(key), list) for key in ("locations", "contexts"))):
            raise ValueError("Incomplete diagnostic in saved report.")
        for mark in item["locations"]:
            if (not isinstance(mark, dict) or not isinstance(mark.get("file"), str)
                    or not all(type(mark.get(key)) is int and mark[key] > 0
                               for key in ("line", "column"))):
                raise ValueError("Invalid diagnostic location in saved report.")
        if not all(isinstance(context, dict) for context in item["contexts"]):
            raise ValueError("Invalid diagnostic context in saved report.")
    for item in checks:
        if (not isinstance(item, dict)
                or not all(isinstance(item.get(key), str) for key in ("path", "status", "message"))
                or not strings(item.get("prerequisites", []))):
            raise ValueError("Incomplete check in saved report.")
    try:
        _validate_saved_values(report)
    except RecursionError:
        raise ValueError("Saved report metadata is nested too deeply.") from None
    return report


def render_report(result):
    """Render the same public facts and repairs as readable, labelled text."""
    return render_projection(project_report(result))


def render_projection(report):
    lines = [f"{'OK' if report['status'] == 'ok' else 'ERROR'}: {report['command']} "
             "(checks only; not scientific validity or completed execution)"]

    def describe(value, indent=2):
        padding = " " * indent
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, (dict, list)) and item:
                    lines.append(f"{padding}{key}:")
                    describe(item, indent + 2)
                else:
                    lines.append(f"{padding}{key}: {scalar(item)}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(f"{padding}-")
                    describe(item, indent + 2)
                else:
                    lines.append(f"{padding}- {scalar(item)}")
        else:
            lines.append(f"{padding}{scalar(value)}")

    def scalar(value):
        if value is None:
            return "unavailable"
        if value == [] or value == {}:
            return "none"
        return str(value)

    for error in report["errors"]:
        lines.append(format_message(error["code"], f"Error at {error['path']}: {error['message']}"))
        lines.append(f"  Troubleshooting: {error['help']}")
        for label, key in (("Expected", "expected"), ("Observed", "observed"),
                           ("Affected", "contexts"), ("Locations", "locations"),
                           ("Repairs", "repairs")):
            lines.append(f"  {label}:")
            describe(error[key], 4)
    for section in ("configuration", "origins", "inputs", "plan", "pending"):
        lines.append(section.capitalize() + ":")
        describe(report["data"][section])
    if report["warnings"]:
        lines.append("Warnings:")
        describe(report["warnings"])
    return "\n".join(lines)


def render_run_summary(facts, *, root, recorded=False):
    """Present actual publications without opening a product or source archive."""
    import yaml

    state = facts["state"]
    label = "Last-recorded state" if recorded else "Run state"
    lines = [f"{label}: {state}", f"Run directory: {root}"]
    if state == "incomplete":
        warning = "Accepted incomplete tracking; this is not a complete trajectory."
        lines.append(warning if recorded else format_message("W1501", warning))
    if recorded:
        lines.append("Recorded metadata only; not a liveness or payload integrity check.")
    if state in {"failed", "interrupted", "running"}:
        lines.append("Use a fresh attempt directory for retries. A recorded running state does not "
                     "show whether its process is alive. Confirm the owner has stopped before "
                     "removing a stale lock; no automatic repair is performed.")
    error = facts.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    if isinstance(code, str) and code in CODE_TOPICS:
        lines.append(f"Troubleshooting: {diagnostic_path(code)}")
    lines.append("Products list completed publications; planned_products are not completions.")
    lines.append(yaml.safe_dump(
        _metadata_view(facts), sort_keys=False, allow_unicode=True).rstrip())
    lines.append("Open listed .nc products with xarray.open_dataset; open .zarr products with "
                 "xarray.open_zarr (Zarr v3 reader required). FrameIt is not required.")
    return "\n".join(lines)


def diagnostic_locations(error, conf):
    if error.locations:
        return list(error.locations)
    marks = conf.simulation_parameter.get("_yaml_locations", {}) if conf else {}
    locations = []
    if error.path.endswith(".files") and conf:
        for context in error.contexts:
            source = conf.sources.get(context.get("source"), {})
            patterns = source.get("files", [])
            if isinstance(patterns, list):
                for index, pattern in enumerate(patterns):
                    if pattern in context.get("patterns", []):
                        locations.extend(_locations(marks, f"{error.path}[{index}]"))
    return locations or _locations(marks, error.path)


def _locations(marks, path):
    while path:
        if path in marks:
            return [marks[path]]
        path = path.rsplit(".", 1)[0] if "." in path else ""
    return []
