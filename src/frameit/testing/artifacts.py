"""Durable, versioned matrix artifacts and path-independent scientific identities.

This module contains no simulation orchestration or numerical comparison. JSON
records are authoritative; the tabular summary is a derived view of those records.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


class CaseStatus(str, Enum):
    PLANNED = "PLANNED"
    PASS = "PASS"
    EXCLUDED = "EXCLUDED"
    SKIPPED_PREREQUISITE = "SKIPPED_PREREQUISITE"
    MISSING_REQUIRED_INPUT = "MISSING_REQUIRED_INPUT"
    INVALID_INPUT = "INVALID_INPUT"
    INPUT_CHANGED = "INPUT_CHANGED"
    RUN_FAILED = "RUN_FAILED"
    WORKER_FAILED = "WORKER_FAILED"
    OUTPUT_CHECK_FAILED = "OUTPUT_CHECK_FAILED"
    INTERRUPTED = "INTERRUPTED"
    NOT_RUN = "NOT_RUN"


FAILURE_STATUSES = frozenset(
    {
        CaseStatus.INVALID_INPUT.value,
        CaseStatus.INPUT_CHANGED.value,
        CaseStatus.RUN_FAILED.value,
        CaseStatus.WORKER_FAILED.value,
        CaseStatus.OUTPUT_CHECK_FAILED.value,
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_value(value: Any) -> Any:
    """Convert bounded metadata to strict JSON, rejecting unsupported values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite metadata is not supported in matrix JSON")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # NumPy scalar metadata can occur in scientific inventory records.
    if hasattr(value, "item"):
        return json_value(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported matrix metadata type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    """Publish one complete JSON record, preserving the previous one on failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(json_value(value), indent=2, sort_keys=True, allow_nan=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path, *, require_schema: bool = False) -> dict:
    with Path(path).open(encoding="utf-8") as stream:
        record = json.load(stream)
    if not isinstance(record, dict):
        raise ValueError("Matrix artifact must contain a JSON object")
    if require_schema:
        version = str(record.get("schema_version", ""))
        if version.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
            raise ValueError(f"Unsupported matrix artifact schema: {version!r}")
    return record


# Explicitly remove location, presentation and execution fields, preserving all
# scientific defaults and preset-resolved coordinate/variable aliases.
_NON_SCIENTIFIC_CONFIG_FIELDS = frozenset(
    {
        "simulation_output_dir",
        "frameit_output_dir",
        "prescribed_track_file",
        "utrack_weights_file",
        "grib_index_dir",
        "simulation_parameter",
        "comment",
        "DEBUG",
        "simulation_name",
    }
)


def scientific_configuration(config: dict) -> dict:
    return {
        key: json_value(value)
        for key, value in config.items()
        if key not in _NON_SCIENTIFIC_CONFIG_FIELDS
    }


def input_identity(records: list[dict], data_root: Path) -> dict:
    """Separate semantic input identity from absolute rerun/provenance paths."""
    items = []
    strong = True
    for record in records:
        path = Path(record["path"])
        try:
            name = path.relative_to(data_root).as_posix()
        except ValueError:
            # Track overrides/checkpoints have a named role instead of a host path.
            name = str(record.get("role", path.name))
        item = {"name": name, "bytes": int(record["bytes"])}
        if record.get("sha256"):
            item["sha256"] = record["sha256"]
        else:
            strong = False
            item["mtime_ns"] = int(record["mtime_ns"])
            if record.get("header_fingerprint"):
                item["header_fingerprint"] = record["header_fingerprint"]
        items.append(item)
    return {"strength": "sha256" if strong else "size_mtime_inventory", "files": items}


def case_identity(case: dict, data_root: Path) -> dict:
    """Identity for a future comparator; FrameIt build versions are provenance."""
    semantic = {
        "case_id": case["id"],
        "case_revision": case.get("revision", 1),
        "mode": case["mode"],
        "dataset_id": case["dataset_id"],
        "configuration": scientific_configuration(case["effective_config"]),
        "inputs": input_identity(case.get("input_records", []), data_root),
        "expected": {
            key: value
            for key, value in case.get("expected", {}).items()
            if key not in {"prescribed_track", "input_coverage"}
        },
    }
    return {"fingerprint": fingerprint(semantic), "semantic": semantic}


def environment_metadata() -> dict:
    """Probe installed distribution versions without initializing native backends."""
    from frameit import __version__

    dependencies = {}
    for package in (
        "numpy",
        "xarray",
        "scipy",
        "netCDF4",
        "h5netcdf",
        "h5py",
        "cfgrib",
        "eccodes",
        "eccodeslib",
        "xesmf",
        "esmpy",
        "dask",
        "pyproj",
        "torch",
        "utrack",
    ):
        try:
            dependencies[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            dependencies[package] = None
    return {
        "frameit_version": __version__,
        "source_revision": os.environ.get("FRAMEIT_BUILD_REVISION"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": dependencies,
        "execution_backend": "sequential_spawn_worker",
        "group_export": "synchronous",
    }


def relative_path(path: str | Path, root: Path) -> str:
    path = Path(path)
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def describe_products(products: list[dict], run_root: Path) -> list[dict]:
    """Collect bounded metadata; physical arrays stay in the NetCDF products."""
    import numpy as np
    import xarray as xr

    result = []
    for product in products:
        descriptor = dict(product)
        path = Path(descriptor["path"])
        descriptor["path"] = relative_path(path, run_root)
        descriptor["bytes"] = path.stat().st_size
        with xr.open_dataset(path) as dataset:
            descriptor["dimensions"] = dict(dataset.sizes)
            descriptor["variables"] = list(dataset.data_vars)
            coordinates = {}
            for name, coordinate in dataset.coords.items():
                values = np.asarray(coordinate.values)
                info = {
                    "dimensions": list(coordinate.dims),
                    "dtype": str(values.dtype),
                    "shape": list(values.shape),
                    "units": coordinate.attrs.get("units", coordinate.encoding.get("units")),
                    "calendar": coordinate.attrs.get(
                        "calendar", coordinate.encoding.get("calendar")
                    ),
                }
                if values.size <= 512:
                    if np.issubdtype(values.dtype, np.datetime64):
                        info["values"] = values.astype("datetime64[ns]").astype(str).tolist()
                    else:
                        info["values"] = [
                            None
                            if isinstance(value, float) and not math.isfinite(value)
                            else str(value)
                            if not isinstance(value, (str, int, float, bool))
                            else value
                            for value in values.reshape(-1).tolist()
                        ]
                else:
                    info["values_sha256"] = hashlib.sha256(values.tobytes()).hexdigest()
                coordinates[name] = info
            descriptor["coordinates"] = coordinates
            if descriptor.get("role") == "track":
                descriptor["centres"] = {
                    name: np.asarray(dataset[name].values).reshape(-1).tolist()
                    for name in ("cx", "cy")
                    if name in dataset
                }
        result.append(descriptor)
    return json_value(result)


def coverage(plan: dict, results: list[dict]) -> dict:
    """One reducer defines coverage denominators for all report views."""
    by_id = {result["id"]: result for result in results}
    cases = plan.get("cases", [])
    excluded = [case["id"] for case in cases if case["preflight"] == "EXCLUDED"]
    required = [
        case["id"]
        for case in cases
        if case["id"] not in excluded and case["requirement"] == "required"
    ]
    optional = [
        case["id"]
        for case in cases
        if case["id"] not in excluded and case["requirement"] == "optional"
    ]
    passed = [result["id"] for result in results if result["status"] == "PASS"]
    missing = [result["id"] for result in results if result["status"] == "MISSING_REQUIRED_INPUT"]
    partial_inventory = any(
        case.get("expected", {}).get("input_coverage", "complete") != "complete"
        for case in cases
        if case["id"] not in excluded
    )
    partial_required_inventory = any(
        case.get("expected", {}).get("input_coverage", "complete") != "complete"
        for case in cases
        if case["id"] in required
    )
    requested_tags = sorted({tag for case in cases for tag in case.get("coverage", [])})
    exercised_tags = sorted(
        {tag for case in cases if case["id"] in passed for tag in case.get("coverage", [])}
    )
    return {
        "selected_ids": [case["id"] for case in cases],
        "eligible_required_ids": required,
        "eligible_optional_ids": optional,
        "excluded_ids": excluded,
        "passed_ids": passed,
        "skipped_ids": [
            result["id"] for result in results if result["status"] == "SKIPPED_PREREQUISITE"
        ],
        "missing_input_ids": missing,
        "failed_ids": [result["id"] for result in results if result["status"] in FAILURE_STATUSES],
        "unexecuted_ids": [
            result["id"]
            for result in results
            if result["status"] in {"NOT_RUN", "PLANNED", "INTERRUPTED"}
        ],
        "input_coverage": "partial" if missing or partial_inventory else "complete",
        "required_coverage": "not_performed"
        if plan.get("plan_only")
        else (
            "complete"
            if all(by_id.get(case_id, {}).get("status") == "PASS" for case_id in required)
            and not partial_required_inventory
            and not missing
            else "incomplete"
        ),
        "scientific_coverage": {
            "requested_tags": requested_tags,
            "exercised_tags": exercised_tags,
            "unexercised_tags": sorted(set(requested_tags) - set(exercised_tags)),
        },
        "reference_validation": "not_performed",
        "scope": {
            "mode": plan.get("mode"),
            "profile": plan.get("profile"),
            "case_patterns": plan.get("case_patterns", []),
        },
    }


def write_summary(path: Path, results: list[dict]) -> None:
    fields = (
        "id",
        "requirement",
        "status",
        "exit_code",
        "duration_s",
        "config",
        "output_dir",
        "log",
        "reason",
    )
    lines = ["\t".join(fields)]
    for result in results:
        lines.append(
            "\t".join(
                str(result.get(field, "")).replace("\t", " ").replace("\n", " ") for field in fields
            )
        )
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
