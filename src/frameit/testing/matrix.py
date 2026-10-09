"""Plan and execute simulation matrices through FrameIt's native run service."""

from __future__ import annotations

import copy
import multiprocessing
import os
import signal
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from frameit.testing.artifacts import (
    FAILURE_STATUSES,
    SCHEMA_VERSION,
    atomic_json,
    case_identity,
    coverage,
    describe_products,
    environment_metadata,
    fingerprint,
    json_value,
    read_json,
    relative_path,
    utc_now,
    write_summary,
)


@dataclass(frozen=True)
class ResolvedMatrixPlan:
    """Serializable resolved input/configuration snapshot; never mutated by execution."""

    mode: str
    profile: str
    input_policy: str
    plan_only: bool
    case_patterns: tuple[str, ...]
    data_root: str
    output: str
    cases: tuple[dict, ...]
    fixture: dict | None
    environment: dict
    created_at: str

    def to_dict(self) -> dict:
        return json_value(
            {
                "schema_version": SCHEMA_VERSION,
                "artifact_type": "matrix_plan",
                "mode": self.mode,
                "profile": self.profile,
                "input_policy": self.input_policy,
                "plan_only": self.plan_only,
                "case_patterns": self.case_patterns,
                "data_root": self.data_root,
                "output": self.output,
                "cases": self.cases,
                "catalog_versions": sorted(
                    {str(case.get("catalog_version", "unknown")) for case in self.cases}
                ),
                "fixture": self.fixture,
                "environment": self.environment,
                "created_at": self.created_at,
            }
        )


def _inventory_changes(records: list[dict]) -> list[dict]:
    changes = []
    for record in records:
        path = Path(record["path"])
        try:
            actual = path.stat()
            if actual.st_size != record["bytes"] or actual.st_mtime_ns != record["mtime_ns"]:
                changes.append({"path": str(path), "reason": "size or modification time changed"})
        except OSError as exc:
            changes.append({"path": str(path), "reason": str(exc)})
    return changes


def _terminate_worker(process: Any) -> None:
    if not process.is_alive():
        return
    # The worker owns a fresh process group where available. This also catches
    # any child work started by an optional native/ML backend.
    try:
        if hasattr(os, "killpg") and os.getpgid(process.pid) == process.pid:
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        pass
    process.join(timeout=5)
    if process.is_alive():
        try:
            if hasattr(os, "killpg") and os.getpgid(process.pid) == process.pid:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.join(timeout=5)


def _worker_entry(case: dict, log_path: str, completion_path: str, log_level: str | None) -> None:
    """Spawn target: import native backends only after redirecting native stderr."""
    import sys

    if hasattr(os, "setsid"):
        os.setsid()
    log = Path(log_path)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8", buffering=1) as stream:
        os.dup2(stream.fileno(), 1)
        os.dup2(stream.fileno(), 2)
        # Python streams can be replaced by test/notebook capture objects; force
        # a real line-buffered stream while native libraries use the same fds.
        sys.stdout = stream
        sys.stderr = stream
        started = time.monotonic()
        try:
            from frameit.core.execution import ExecutionOptions, execute_simulation
            from frameit.core.settings_class import SimulationConfig

            changes = _inventory_changes(case["input_records"])
            if changes:
                atomic_json(
                    Path(completion_path),
                    {
                        "ok": False,
                        "status": "INPUT_CHANGED",
                        "input_changes": changes,
                        "reason": "Planned inputs changed before opening",
                        "products": [],
                    },
                )
                return
            config = SimulationConfig.from_mapping_with_model_preset(case["config"])
            result = execute_simulation(
                config,
                ExecutionOptions(synchronous_export=True, log_level=log_level),
                input_files=tuple(Path(path) for path in case["input_files"]),
            )
            metadata = result.to_dict()
            metadata["duration_s"] = round(time.monotonic() - started, 6)
            changes = _inventory_changes(case["input_records"])
            if changes:
                metadata.update(
                    ok=False,
                    status="INPUT_CHANGED",
                    input_changes=changes,
                    reason="Planned inputs changed during execution",
                )
            atomic_json(Path(completion_path), metadata)
        except BaseException as exc:
            traceback.print_exc()
            atomic_json(
                Path(completion_path),
                {
                    "ok": False,
                    "status": "RUN_FAILED",
                    "products": [],
                    "duration_s": round(time.monotonic() - started, 6),
                    "reason": f"{type(exc).__name__}: {exc}",
                    "exception": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                },
            )
        finally:
            stream.flush()


def _execute_case(case: dict, output: Path, log_level: str | None) -> dict:
    """Run one non-daemon isolated worker and require a successful completion."""
    case_root = output / "cases" / case["id"]
    log_path = case_root / "logs" / "frameit.log"
    completion_path = case_root / "worker_result.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # A log exists even if process creation or backend import fails immediately.
    log_path.touch()
    started = time.monotonic()
    changes = _inventory_changes(case["input_records"])
    if changes:
        return {
            "status": "INPUT_CHANGED",
            "exit_code": 1,
            "products": [],
            "duration_s": 0.0,
            "reason": "Planned inputs changed before scheduling",
            "input_changes": changes,
        }
    process = multiprocessing.get_context("spawn").Process(
        target=_worker_entry,
        args=(case, str(log_path), str(completion_path), log_level),
        name=f"frameit-{case['id']}",
        daemon=False,
    )
    try:
        process.start()
        while process.is_alive():
            process.join(timeout=0.2)
    except KeyboardInterrupt:
        _terminate_worker(process)
        raise
    except Exception as exc:
        _terminate_worker(process)
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(f"Worker launch failed: {exc}\n")
        return {
            "status": "WORKER_FAILED",
            "exit_code": 1,
            "products": [],
            "duration_s": round(time.monotonic() - started, 6),
            "reason": str(exc),
        }
    worker_exit = process.exitcode
    if worker_exit != 0 or not completion_path.is_file():
        return {
            "status": "WORKER_FAILED",
            "exit_code": 1,
            "worker_exit_code": worker_exit,
            "products": [],
            "duration_s": round(time.monotonic() - started, 6),
            "reason": f"Worker exit={worker_exit}; a clean completion record is required",
        }
    try:
        result = read_json(completion_path)
    except (OSError, ValueError) as exc:
        return {
            "status": "WORKER_FAILED",
            "exit_code": 1,
            "worker_exit_code": worker_exit,
            "products": [],
            "duration_s": round(time.monotonic() - started, 6),
            "reason": f"Invalid worker completion record: {exc}",
        }
    result["worker_exit_code"] = worker_exit
    result["exit_code"] = 0 if result.get("ok") else 1
    result.setdefault("duration_s", round(time.monotonic() - started, 6))
    result.setdefault("status", "EXECUTED" if result.get("ok") else "RUN_FAILED")
    changes = _inventory_changes(case["input_records"])
    if changes:
        result.update(
            ok=False,
            status="INPUT_CHANGED",
            exit_code=1,
            input_changes=changes,
            reason="Planned inputs changed during execution",
        )
    return result


def _preflight_result(case: dict, output: Path, *, plan_only: bool) -> dict:
    status = case["preflight"]
    if status == "READY":
        status = "PLANNED" if plan_only else "NOT_RUN"
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "matrix_case_result",
        "id": case["id"],
        "requirement": case["requirement"],
        "status": status,
        "exit_code": 2
        if status == "INVALID_INPUT"
        else (1 if status == "MISSING_REQUIRED_INPUT" else 0),
        "duration_s": 0.0,
        "reason": case.get("reason", ""),
        "config": f"configs/{case['id']}.yaml",
        "output_dir": f"cases/{case['id']}/products",
        "log": f"cases/{case['id']}/logs/frameit.log",
        "expected": case.get("expected", {}),
        "identity": case.get("identity"),
        "products": [],
        "product_checks": {"state": "not_evaluated", "checks": []},
    }


def _exit_code(plan: dict, results: list[dict], *, interrupted: bool = False) -> int:
    statuses = [result["status"] for result in results]
    if interrupted or "INTERRUPTED" in statuses:
        return 130
    if "INVALID_INPUT" in statuses:
        return 2
    if any(status in FAILURE_STATUSES for status in statuses):
        return 1
    if plan["input_policy"] == "strict" and "MISSING_REQUIRED_INPUT" in statuses:
        return 1
    if plan["plan_only"]:
        return 0 if "PLANNED" in statuses else 2
    return 0 if "PASS" in statuses else 2


def _publish_run(
    plan: dict,
    results: list[dict],
    output: Path,
    started_at: str,
    *,
    complete: bool,
    interrupted: bool = False,
) -> dict:
    # Read case checkpoints back; aggregation and TSV derive from those records.
    checkpoints = [
        read_json(output / "cases" / result["id"] / "result.json", require_schema=True)
        for result in results
    ]
    report = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "matrix_run",
        "plan": "plan.json",
        "plan_sha256": fingerprint(plan),
        "plan_hash_format": "sha256-canonical-json",
        "mode": plan["mode"],
        "profile": plan["profile"],
        "catalog_versions": plan["catalog_versions"],
        "input_policy": plan["input_policy"],
        "plan_only": plan["plan_only"],
        "environment": plan["environment"],
        "fixture": plan.get("fixture"),
        "started_at": started_at,
        "finished_at": utc_now() if complete else None,
        "completion_state": "interrupted"
        if interrupted
        else ("complete" if complete else "running"),
        "results": checkpoints,
        "coverage": coverage(plan, checkpoints),
        "exit_code": _exit_code(plan, checkpoints, interrupted=interrupted) if complete else None,
        "reference_validation": "not_performed",
        "execution_outcome": "not_performed"
        if plan["plan_only"]
        else (
            "failed"
            if any(
                result["status"]
                in {
                    "INPUT_CHANGED",
                    "RUN_FAILED",
                    "WORKER_FAILED",
                    "OUTPUT_CHECK_FAILED",
                    "INTERRUPTED",
                }
                for result in checkpoints
            )
            else (
                "passed"
                if any(result["status"] == "PASS" for result in checkpoints)
                else "not_performed"
            )
        ),
    }
    atomic_json(output / "run.json", report)
    write_summary(output / "summary.tsv", checkpoints)
    return report


def _bind_fixture_hashes(case: dict, fixture: dict | None, root: Path) -> None:
    if not fixture:
        return
    verified = list(fixture.get("files", []))
    if fixture.get("external_track"):
        verified.append(fixture["external_track"])
    verified_by_path = {str((root / item["path"]).resolve()): item for item in verified}
    for record in case.get("input_records", []):
        verified_record = verified_by_path.get(str(Path(record["path"]).resolve()))
        if verified_record is None:
            continue
        if record["bytes"] != verified_record["bytes"] or (
            "mtime_ns" in verified_record and record["mtime_ns"] != verified_record["mtime_ns"]
        ):
            case.update(
                preflight="INVALID_INPUT",
                reason=(f"CI input changed after fixture verification: {record['path']}"),
            )
        elif verified_record.get("sha256"):
            record["sha256"] = verified_record["sha256"]


def run_matrix(
    data_root: Path,
    output: Path,
    *,
    ci: bool = False,
    profile: str = "full",
    cases: tuple[str, ...] = (),
    plan_only: bool = False,
    input_policy: str = "strict",
    keep_going: bool = True,
    utrack_weights: Path | None = None,
    log_level: str | None = None,
) -> dict:
    """Resolve, execute and report selected native matrix cases.

    ``PASS`` means execution and output contracts passed. Reference comparison is
    deliberately a later service. Invalid call arguments raise ``ValueError``;
    resolved input/prerequisite failures are persisted and return an exit code.
    """
    from frameit.core.settings_class import SimulationConfig
    from frameit.testing.catalog import load_cases, resolve_case
    from frameit.testing.checks import check_products

    mode = "ci" if ci else "full"
    if profile not in {"core", "full"}:
        raise ValueError("profile must be 'core' or 'full'")
    if input_policy not in {"strict", "available"}:
        raise ValueError("input_policy must be 'strict' or 'available'")
    data_root = Path(data_root).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if output == data_root or data_root in output.parents or output in data_root.parents:
        raise ValueError("Data and matrix output trees must not overlap")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Matrix output must be a fresh directory: {output}")
    definitions = load_cases(mode=mode, profile=profile, patterns=tuple(cases))
    if not definitions:
        raise ValueError("No matrix cases match the requested mode/profile/selection")
    output.mkdir(parents=True, exist_ok=True)
    (output / "configs").mkdir()
    started_at = utc_now()
    fixture = None
    fixture_error = None
    if ci:
        from frameit.testing.datasets import verify_ci_dataset

        dataset_ids = sorted(
            {case["dataset_id"] for case in definitions if not case.get("excluded_reason")}
        )
        if dataset_ids:
            try:
                fixture = verify_ci_dataset(data_root, dataset_ids=dataset_ids)
            except (ValueError, OSError) as exc:
                fixture_error = f"CI fixture verification failed: {exc}"
    context = {"utrack_weights": str(utrack_weights) if utrack_weights is not None else None}
    planned = []
    for definition in definitions:
        case_output = output / "cases" / definition["id"] / "products"
        try:
            case = resolve_case(
                definition,
                data_root,
                case_output,
                input_policy=input_policy,
                mode=mode,
                context=context,
            )
            case = copy.deepcopy(case)
        except (ValueError, OSError, ImportError) as exc:
            case = copy.deepcopy(definition)
            case.update(
                preflight="INVALID_INPUT",
                reason=f"Case resolution failed: {exc}",
                input_files=[],
                input_records=[],
                expected={},
            )
        case["mode"] = mode
        case.setdefault("input_files", [])
        case.setdefault("input_records", [])
        case.setdefault("expected", {})
        if fixture_error and case["preflight"] != "EXCLUDED":
            case.update(preflight="INVALID_INPUT", reason=fixture_error)
        _bind_fixture_hashes(case, fixture, data_root)
        try:
            config = SimulationConfig.from_mapping_with_model_preset(case["config"])
            case["effective_config"] = config.to_dict(include_runtime=False)
            case["identity"] = case_identity(case, data_root)
        except (ValueError, TypeError, KeyError) as exc:
            case["effective_config"] = {}
            case["identity"] = None
            if case["preflight"] == "READY":
                case.update(preflight="INVALID_INPUT", reason=f"Configuration is invalid: {exc}")
        # Save user mapping separately from the effective preset/default view.
        config_path = output / "configs" / f"{case['id']}.yaml"
        config_path.write_text(
            yaml.safe_dump(json_value(case["config"]), sort_keys=False), encoding="utf-8"
        )
        atomic_json(output / "configs" / f"{case['id']}.resolved.json", case["effective_config"])
        planned.append(case)
    plan = ResolvedMatrixPlan(
        mode=mode,
        profile=profile,
        input_policy=input_policy,
        plan_only=plan_only,
        case_patterns=tuple(cases),
        data_root=str(data_root),
        output=str(output),
        cases=tuple(planned),
        fixture=fixture,
        environment=environment_metadata(),
        created_at=started_at,
    ).to_dict()
    atomic_json(output / "plan.json", plan)
    results = [_preflight_result(case, output, plan_only=plan_only) for case in planned]
    for result in results:
        atomic_json(output / "cases" / result["id"] / "result.json", result)
    _publish_run(plan, results, output, started_at, complete=False)
    if plan_only:
        return _publish_run(plan, results, output, started_at, complete=True)
    stopped = False
    interrupted = False
    for index, case in enumerate(planned):
        if case["preflight"] != "READY":
            if not keep_going and (
                case["preflight"] == "INVALID_INPUT"
                or (case["preflight"] == "MISSING_REQUIRED_INPUT" and input_policy == "strict")
            ):
                stopped = True
            continue
        if stopped:
            results[index]["reason"] = "Not scheduled after fail-fast"
            atomic_json(output / "cases" / case["id"] / "result.json", results[index])
            continue
        print(f"[RUN ] {case['id']}", flush=True)
        result = results[index]
        result["started_at"] = utc_now()
        try:
            executed = _execute_case(case, output, log_level)
            result.update(executed)
            if result["status"] == "EXECUTED":
                try:
                    checks = check_products(case, executed.get("products", []))
                    result["product_checks"] = {
                        **checks,
                        "state": ("passed" if checks["ok"] else "failed"),
                    }
                    result["status"] = "PASS" if checks["ok"] else "OUTPUT_CHECK_FAILED"
                    result["exit_code"] = 0 if checks["ok"] else 1
                    result["reason"] = checks.get("reason", "")
                    result["products"] = describe_products(executed.get("products", []), output)
                except Exception as exc:
                    result.update(
                        status="OUTPUT_CHECK_FAILED",
                        exit_code=1,
                        reason=f"Product inspection failed: {type(exc).__name__}: {exc}",
                        product_checks={"state": "failed", "checks": []},
                    )
            # Worker metadata paths are provenance; the public artifact paths
            # are relocatable and never inferred by globbing the directory.
            if result.get("log_path"):
                result["simulation_log"] = relative_path(result.pop("log_path"), output)
            for product in result.get("products", []):
                if product.get("path"):
                    product["path"] = relative_path(product["path"], output)
            for detail in result.get("product_checks", {}).get("products", []):
                if detail.get("path"):
                    detail["path"] = relative_path(detail["path"], output)
            for check in result.get("product_checks", {}).get("checks", []):
                if check.get("path"):
                    check["path"] = relative_path(check["path"], output)
            result["output_dir"] = f"cases/{case['id']}/products"
            result["finished_at"] = utc_now()
        except KeyboardInterrupt:
            result.update(
                status="INTERRUPTED",
                exit_code=130,
                reason="User interruption",
                finished_at=utc_now(),
            )
            interrupted = True
            stopped = True
        except Exception as exc:
            # A scheduler/IPC failure must still leave a durable case record.
            result.update(
                status="WORKER_FAILED",
                exit_code=1,
                reason=f"Worker orchestration failed: {type(exc).__name__}: {exc}",
                finished_at=utc_now(),
                exception={
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
        results[index] = result
        atomic_json(output / "cases" / case["id"] / "result.json", result)
        print(f"[{result['status']}] {case['id']} {result.get('reason', '')}", flush=True)
        _publish_run(plan, results, output, started_at, complete=False)
        if result["status"] in FAILURE_STATUSES and not keep_going:
            stopped = True
        if interrupted:
            for remaining in results[index + 1 :]:
                if remaining["status"] == "NOT_RUN":
                    remaining["reason"] = "Not scheduled after interruption"
                    atomic_json(output / "cases" / remaining["id"] / "result.json", remaining)
            break
    return _publish_run(plan, results, output, started_at, complete=True, interrupted=interrupted)
