"""Serial post-run admission and publication, independent of extraction."""

from contextlib import ExitStack, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from uuid import uuid4

import yaml

from frameit.core.configuration import _read_yaml, read_yaml, resolve_schema
from frameit.core.reports import PreflightResult, error_record, exception_diagnostics, primary_error_code
from frameit.core.run_context import (
    CONTEXT_VERSION,
    PROJECTION_VERSION,
    content_digest,
    file_sha256,
    project_base_request,
)
from frameit.core.run_state import (
    directory_lock,
    finalize_after,
    read_run_status,
    utc_now,
    write_run_record,
)
from frameit.diagnostics.contracts import Centre, ParentSnapshot, diagnostic_error
from frameit.utils.diagnostics import tag_error
from frameit.utils.output_paths import TRAJECTORY_RECORD, OutputPaths

STATUS_FILE = "diagnostics-status.yaml"
UTC_CALENDARS = {"standard", "gregorian", "proleptic_gregorian"}


def _parent_error(message, *, observed=None):
    return diagnostic_error(
        "E2002", "parent", message, expected="matching completed extraction with a saved trajectory",
        observed=observed, repair="Select the matching completed parent with --run-directory. "
        "If its essential records are absent, run extraction to a fresh output directory.",
    )


def _record(root, name):
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise _parent_error(f"Missing or unsafe parent record: {path.name}")
    return path


def _differences(saved, current, prefix=""):
    if isinstance(saved, dict) and isinstance(current, dict):
        for key in sorted(saved.keys() | current.keys()):
            path = f"{prefix}.{key}" if prefix else key
            if key not in saved or key not in current:
                yield path
            else:
                yield from _differences(saved[key], current[key], path)
    elif content_digest(saved) != content_digest(current):
        yield prefix


def _read_centres(path, *, attempt=None, origin=None):
    import numpy as np
    import xarray as xr

    with xr.open_dataset(path, chunks=None, cache=False, create_default_indexes=False) as ds:
        if attempt is not None and (
            ds.attrs.get("run_attempt_id") != attempt
            or ds.attrs.get("record_type") != "frameit_trajectory"
            or ds.attrs.get("record_version") != 1
            or ds.attrs.get("tracking_complete") != 1
        ):
            raise _parent_error("Saved trajectory does not belong to this complete run attempt")
        origin = ds.attrs.get("centre_origin", origin)
        if origin not in {"fixed", "prescribed", "calculated"}:
            raise _parent_error("Saved trajectory centre origin is unavailable")
        names = ("time", "latitude", "longitude")
        if not set(names) <= ds.variables.keys() or any(ds[name].dims != ("time",) for name in names):
            raise _parent_error("Saved trajectory requires one time, latitude, and longitude axis")
        if (ds.latitude.attrs.get("units") != "degrees_north"
                or ds.longitude.attrs.get("units") != "degrees_east"):
            raise _parent_error("Saved trajectory does not establish geographic degrees")
        calendar = ds.time.encoding.get("calendar", "standard")
        clock = ds.time.values
        if calendar not in UTC_CALENDARS or clock.dtype.kind != "M" or not len(clock):
            raise _parent_error("RSMC requires a supported Gregorian trajectory clock",
                                observed=calendar)
        ticks = clock.astype("datetime64[ns]")
        if (np.isnat(ticks).any() or not np.array_equal(ticks.astype(clock.dtype), clock)
                or np.any(ticks[1:] <= ticks[:-1])):
            raise _parent_error("Saved trajectory times must be exact, unique and increasing")
        lat, lon = ds.latitude.values, ds.longitude.values
        if not (np.all(np.isfinite(lat) & (np.abs(lat) <= 90)) and np.isfinite(lon).all()):
            raise _parent_error("Saved trajectory positions must be finite and geographic")
        return tuple(Centre(str(t), float(y), float(x))
                     for t, y, x in zip(ticks, lat, lon, strict=True)), calendar, origin


def _admit_parent(root, raw, *, base_dir, source_name, source_kind):
    status_path = _record(root, "run-status.yaml")
    status = read_run_status(root)
    if status["state"] != "completed" or status.get("pending") != []:
        reason = status.get("tracking_termination_reason") or (status.get("error") or {}).get(
            "message", "")
        raise _parent_error(
            f"Parent state is {status['state']} with pending {status.get('pending')}: {reason}",
            observed={"state": status["state"], "pending": status.get("pending"), "reason": reason},
        )
    if not isinstance(status.get("recorded_processing"), dict):
        raise _parent_error("Parent provenance is missing or does not match authoritative status")
    paths = [status_path, _record(root, "run-provenance.yaml"),
             _record(root, "run-request.yaml")]
    fingerprints = [(path, file_sha256(path)) for path in paths]
    provenance = read_yaml(paths[1], error_code="E2002")
    request = read_yaml(paths[2], error_code="E2002")
    authored = request.get("authored_configuration")
    saved_base = request.get("path_bases", {}).get("configuration_directory")
    if (request.get("record_version") != 1 or not isinstance(authored, dict)
            or not isinstance(saved_base, str) or not Path(saved_base).is_absolute()):
        raise _parent_error("Parent lacks the frozen authored request and configuration base")
    products = tuple(status["products"])
    attempt = status.get("run_attempt_id")
    if attempt is None and "run_context" not in status:
        if "run_context" in request or request.get("run_attempt_id") is not None:
            raise _parent_error("Mixed legacy and current parent records")
        version = PROJECTION_VERSION
        old = project_base_request(authored, base_dir=saved_base, version=version)
        resolved = _record(root, "resolved-config.yaml")
        fingerprints.append((resolved, file_sha256(resolved)))
        effective = project_base_request(read_yaml(resolved), base_dir=saved_base, version=version)
        inventory = [item for item in products if item.get("role", item.get("product")) == "track"]
        if len(inventory) != 1:
            raise _parent_error("Legacy parent requires exactly one recorded public track product")
        track, = OutputPaths(root).planned_products(inventory)
        if not track.is_file() or track.suffix != ".nc":
            raise _parent_error("The recorded legacy track is not a readable NetCDF file")
        origin = next((label for key, label in (
            ("center", "fixed"), ("track", "prescribed"), ("tracker", "calculated"))
            if key in old.get("region", {})), None)
        centres, calendar, origin = _read_centres(track, origin=origin)
        fingerprints.append((track, file_sha256(track)))
        attempt = content_digest([(path.relative_to(root).as_posix(), digest)
                                  for path, digest in fingerprints])
        scheme = "legacy_records_and_track_sha256"
    else:
        context = request.get("run_context", {})
        version = context.get("projection_version")
        if (context.get("context_version") != CONTEXT_VERSION
                or type(version) is not int or version != PROJECTION_VERSION):
            raise _parent_error("Unsupported parent context or projection version; use a "
                                "compatible FrameIt version", observed=version)
        old, effective = context.get("authored"), context.get("effective")
        summary = {key: value for key, value in context.items()
                   if key not in {"authored", "effective"}}
        if (not isinstance(attempt, str) or not attempt or request.get("run_attempt_id") != attempt
                or summary != status.get("run_context") or not isinstance(effective, dict)
                or not isinstance(old, dict)
                or any(summary.get(f"{key}_sha256") != content_digest(value)
                       for key, value in (("effective", effective), ("authored", old)))
                or content_digest(old) != content_digest(project_base_request(
                    authored, base_dir=saved_base, version=version))):
            raise _parent_error("Parent request and authoritative run context disagree")
        inventory = [item for item in status.get("records", []) if item.get("role") == "trajectory"]
        if len(inventory) != 1:
            raise _parent_error("Parent has no saved trajectory; a full-domain run can complete "
                                "without cyclone centres")
        entry, = inventory
        track = OutputPaths(root).trajectory_record()
        if (entry.get("path") != TRAJECTORY_RECORD or entry.get("run_attempt_id") != attempt
                or not track.is_file() or file_sha256(track) != entry.get("sha256")):
            raise _parent_error("Saved trajectory does not match the recorded path, attempt or hash")
        centres, calendar, origin = _read_centres(track, attempt=attempt)
        fingerprints.append((track, entry["sha256"]))
        scheme = "run_attempt_id_and_record_fingerprints"
    current = project_base_request(raw, base_dir=base_dir, version=version)
    if content_digest(current) != content_digest(old):
        changed = list(_differences(old, current))
        raise _parent_error("Scientific request differs from the parent at " + ", ".join(changed[:10]),
                            observed={"different_settings": changed[:10]})
    sources = provenance.get("sources", {})
    evidence = sources.get(source_name)
    if not isinstance(evidence, dict) or source_name not in effective.get("sources", {}):
        raise _parent_error(f"Parent lacks frozen provenance for source {source_name!r}")
    if source_kind == "original" and not evidence.get("frozen_inventory"):
        raise _parent_error("Parent lacks frozen original file identities; select an eligible "
                            "model_grid product or create a new parent")
    parent = ParentSnapshot(root, attempt, scheme, centres, calendar, origin, effective, sources,
                            products, tuple(fingerprints))
    _recheck_parent(parent)
    return parent


def _recheck_parent(parent):
    for path, fingerprint in parent.fingerprints:
        if path.is_symlink() or not path.is_file() or file_sha256(path) != fingerprint:
            raise _parent_error(f"Parent record changed during diagnostic admission or processing: "
                                f"{path.relative_to(parent.root)}")


@contextmanager
def _preserve_scope(scope, message):
    value = scope.__enter__()
    failure = None
    try:
        yield value
    except BaseException as exc:
        failure = exc
        raise
    finally:
        with finalize_after(failure, message):
            scope.__exit__(type(failure) if failure else None, failure,
                           failure.__traceback__ if failure else None)


def _serial_scope(options):
    from frameit.core.runtime import execution_scope

    return execution_scope(options)


def _plan_source(parent, request, *, scratch):
    from frameit.diagnostics.sources import plan_source

    return plan_source(parent, request, scratch=scratch)


def _execute_plan(attempt, plan, *, scratch):
    from frameit.diagnostics.output import execute_plan

    return execute_plan(attempt, plan, scratch=scratch)


def _child_attempt(root, locks):
    directory = root / "diagnostics"
    if directory.is_symlink() or directory.exists() and not directory.is_dir():
        raise tag_error(ValueError(f"Unsafe diagnostic attempt root: {directory}"), "E1805")
    attempt = directory / uuid4().hex
    attempt.mkdir(parents=True, exist_ok=False)
    locks.enter_context(directory_lock(attempt, lock_name=".frameit-diagnostics.lock"))
    return attempt


def run_diagnostics(config_path, *, run_directory=None, check=False):
    result = PreflightResult("run-diag")
    status_path = None
    committed = False
    try:
        config_path = Path(config_path).absolute()
        raw, locations = _read_yaml(config_path)
        try:
            config, _, _ = resolve_schema(raw, base_dir=config_path.parent)
        except ValueError as exc:
            for error in getattr(exc, "diagnostics", []):
                if error.path in locations:
                    error.locations.append(locations[error.path])
            raise
        if not config["diagnostics"]:
            result.facts["message"] = "No diagnostics requested"
            return result

        from frameit.core.execution import ExecutionOptions
        from frameit.core.runtime import current_execution_resources, runtime_provenance

        best = config["diagnostics"]["best_track"]
        root = Path(run_directory if run_directory is not None else config["output"]["directory"])
        if root.is_symlink() or not root.is_dir():
            raise _parent_error(f"Missing or unsafe parent directory: {root}")
        root = root.resolve()
        options = ExecutionOptions(cpus=1, dask_scheduler="synchronous", dask_workers=1,
                                   native_threads=1, synchronous_export=True, max_workers=1)
        with directory_lock(root), ExitStack() as child_lock:
            status = None
            try:
                with _preserve_scope(_serial_scope(options), "Restoring diagnostic runtime"):
                    start = monotonic()
                    parent = _admit_parent(
                        root, raw, base_dir=config_path.parent, source_name=best["input"]["source"],
                        source_kind=best["input"]["kind"])
                    with _preserve_scope(TemporaryDirectory(prefix="frameit-diag-"),
                                         "Cleaning diagnostic scratch") as tmp:
                        scratch = Path(tmp)
                        plan = _plan_source(parent, best, scratch=scratch)
                        runtime = runtime_provenance(current_execution_resources())
                        result.facts.update(
                            parent_attempt_id=parent.attempt_id, identity_scheme=parent.identity_scheme,
                            centre_origin=parent.centre_origin, execution=runtime,
                            **plan.facts,
                        )
                        if check:
                            result.deferred_checks.append({
                                "path": "diagnostics.best_track", "status": "execution-dependent",
                                "message": "Payload support, numerical reductions and publications "
                                           "were not checked.",
                            })
                            _recheck_parent(parent)
                            return result
                        attempt = _child_attempt(root, child_lock)
                        status_path = attempt / STATUS_FILE
                        status = {"schema_version": 1, "state": "running", "products": [],
                                  "diagnostic_attempt_id": attempt.name,
                                  "parent_attempt_id": parent.attempt_id, "started_at": utc_now(),
                                  "finished_at": None}
                        result.facts.update(attempt_directory=str(attempt), committed=False)
                        write_run_record(status_path, status, overwrite=False)
                        write_run_record(attempt / "diagnostics-request.yaml", {
                            "record_version": 1, "diagnostics": raw["diagnostics"],
                            "configuration_directory": str(config_path.parent),
                        }, overwrite=False)
                        write_run_record(attempt / "diagnostics-resolved.yaml", {
                            "record_version": 1, "best_track": best,
                        }, overwrite=False)
                        products, science, warnings = _execute_plan(attempt, plan, scratch=scratch)
                        _recheck_parent(parent)
                        write_run_record(attempt / "diagnostics-provenance.yaml", {
                            "record_version": 1, "attempt": attempt.name,
                            "parent": parent.attempt_id, "identity_scheme": parent.identity_scheme,
                            "parent_records": {str(p.relative_to(root)): value
                                               for p, value in parent.fingerprints},
                            "plan": plan.facts, "execution": runtime, "scientific_summary": science,
                            "warnings": warnings, "work_duration_s": monotonic() - start,
                        }, overwrite=False)
                status.update(state="completed", products=products, scientific_summary=science,
                              finished_at=utc_now())
                write_run_record(status_path, status)
                committed = True
                result.facts.update(committed=True, products=products, scientific_summary=science,
                                    warnings=warnings)
            except BaseException as exc:
                if status is not None and not committed:
                    with finalize_after(exc, "Writing diagnostic failure status also failed"):
                        status.update(state=("interrupted" if isinstance(
                            exc, (KeyboardInterrupt, SystemExit)) else "failed"),
                            error=error_record(exc), products=[], finished_at=utc_now())
                        write_run_record(status_path, status)
                raise
    except Exception as exc:
        if status_path is not None and committed:
            exc.add_note(f"Diagnostic products were already committed at {status_path.parent}.")
            result.facts["message"] = f"Outputs were already committed at {status_path.parent}"
        if primary_error_code(exc) == "E0999" and isinstance(exc, yaml.YAMLError):
            tag_error(exc, "E1102")
        result.errors = exception_diagnostics(
            exc, path="diagnostics.best_track", expected="admitted diagnostic execution",
            observed={"cause": str(exc), "notes": getattr(exc, "__notes__", [])},
            repairs=["Use the linked troubleshooting entry and run --check again."],
        )
    return result


def read_diagnostics_status(root):
    path = Path(root) / STATUS_FILE
    if path.is_symlink() or not path.is_file():
        raise tag_error(ValueError(f"Missing or unsafe diagnostic status: {path}"), "E1807")
    value = read_yaml(path, error_code="E1807")
    if (type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or value.get("state") not in {"running", "completed", "failed", "interrupted"}
            or not isinstance(value.get("started_at"), str)
            or not isinstance(value.get("products"), list)
            or not all(isinstance(item, dict) and isinstance(item.get("path"), str)
                       for item in value["products"])):
        raise tag_error(ValueError(f"Unrecognized diagnostic status: {path}"), "E1807")
    return value
