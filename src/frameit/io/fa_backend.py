"""Bounded, isolated native FA requests, safe alongside cfgrib in the parent."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

from frameit.io.fa_contracts import PROTOCOL_VERSION, validate_descriptor

log = logging.getLogger(__name__)
_REQUEST_LOCK = threading.Lock()


def _record_diagnostics(request, info):
    path = request.get("diagnostics_path")
    if path is not None:
        record = {"source_file": Path(request["path"]).name,
                  "fields": request.get("fields", []), **info}
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
        try:
            os.write(descriptor, (json.dumps(record) + "\n").encode())
        finally:
            os.close(descriptor)


def collect_fa_diagnostics(output_dir, inputs):
    """Summarize child-native diagnostics after all spawned exporters complete."""
    summary = {"decode_requests": 0, "warnings": [], "backend_versions": {},
               "field_observations": {}}
    warnings = set()
    for relative in sorted({item["decoder_log"] for item in inputs if item.get("decoder_log")}):
        path = Path(output_dir) / relative
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                summary["decode_requests"] += 1
                summary["backend_versions"].update(record.get("backend_versions", {}))
                if record.get("field_descriptors"):
                    summary["field_observations"].setdefault(record["source_file"], {}).update(
                        record["field_descriptors"])
                if record.get("diagnostics"):
                    warnings.add(record["diagnostics"])
    summary["warnings"] = sorted(warnings)
    return summary


def request_fa(request):
    """A fresh interpreter per transaction avoids inherited native-library state.

    At most one transaction runs per consuming process. Only a selected record
    is decoded, and native cropping precedes binary transfer. This deliberately
    favors deterministic cleanup over a persistent service; startup cost is real.
    """
    if (type(request.get("protocol_version", PROTOCOL_VERSION)) is not int
            or request.get("protocol_version", PROTOCOL_VERSION) != PROTOCOL_VERSION):
        raise ValueError("Unsupported FA worker protocol_version")
    request = {**request, "protocol_version": PROTOCOL_VERSION}
    environment = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                       MKL_NUM_THREADS="1", PYTHONNOUSERSITE="1")
    # The wheel's private ecCodes uses its own matching MEMFS definitions.
    # Parent GRIB overrides remain untouched and must not change child decoding.
    for key in ("ECCODES_DEFINITION_PATH", "ECCODES_SAMPLES_PATH",
                "GRIB_DEFINITION_PATH", "GRIB_SAMPLES_PATH"):
        environment.pop(key, None)
    with _REQUEST_LOCK, tempfile.TemporaryDirectory(prefix="frameit-fa-") as directory:
        try:
            result = subprocess.run(
                [request.get("python_executable") or sys.executable,
                 "-m", "frameit.io.fa_worker", directory],
                input=json.dumps(request), capture_output=True, text=True, errors="replace",
                env=environment, check=False, timeout=request.get("timeout_seconds", 120.),
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"FA request timed out for {Path(request['path']).name}; "
                             "review input.fa.timeout_seconds and source availability") from exc
        except OSError as exc:
            raise ValueError("Cannot launch the FA helper; check input.fa.python_executable "
                             "and install FrameIt with the selected FA extra there") from exc
        diagnostics = (result.stdout + result.stderr).strip()
        response = Path(directory) / "response.json"
        context = f"{Path(request['path']).name}: {', '.join(request.get('fields', []))}"
        if result.returncode or not response.is_file():
            _record_diagnostics(request, {"diagnostics": diagnostics,
                                          "returncode": result.returncode})
            raise ValueError(f"FA decoder process failed ({result.returncode}) for {context}: "
                             f"{diagnostics[-4000:]}")
        payload = json.loads(response.read_text(encoding="utf-8"))
        if not payload["ok"]:
            _record_diagnostics(request, {"diagnostics": diagnostics, "error": payload["error"]})
            raise ValueError(f"FA input {context}: {payload['error']}\n{diagnostics[-4000:]}")
        info = payload["result"]
        if (type(info.get("protocol_version")) is not int
                or info.get("protocol_version") != PROTOCOL_VERSION):
            raise ValueError(f"Unsupported FA response protocol_version for {context}")
        for name, descriptor in info.get("field_descriptors", {}).items():
            validate_descriptor(descriptor)
            if descriptor["native_id"] != name:
                raise ValueError(f"FA descriptor native identity mismatch for {context}")
        if diagnostics:
            log.warning("FA decoder %s: %s", context, diagnostics)
        if request["operation"] == "read":
            descriptor = info.get("field_descriptors", {}).get(request["fields"][0])
            if descriptor is None:
                raise ValueError(f"Missing FA decoded field descriptor for {context}")
            if (descriptor["native"]["representation"] != "gridpoint"
                    or descriptor["eligibility"]["decode"] == "blocked"):
                raise ValueError(f"FA transfer is not a qualified gridpoint field: {context}; "
                                 "coefficients cannot be returned as values")
            if descriptor["native"]["decoded_dtype"] != info["dtype"]:
                raise ValueError(f"FA decoded dtype contradicts field descriptor for {context}")
            # Qualified 1.2.1/1.3.0 stacks expose no structured multiplier query. Absence of this
            # warning is NOT independent scaling verification or identity proof.
            missing = "has no encoded FMULTM and FMULTE" in diagnostics
            descriptor["scaling"].update(
                status="missing" if missing else "not_exposed",
                evidence="native_diagnostic_text" if missing else "no_structured_native_query",
                fallback="identity_explicit_opt_in" if missing and request.get(
                    "allow_unscaled") else None,
            )
            _record_diagnostics(request, {"diagnostics": diagnostics,
                                          "backend_versions": info["backend_versions"],
                                          "protocol_version": PROTOCOL_VERSION,
                                          "field_descriptors": info["field_descriptors"]})
            if missing and not request.get("allow_unscaled"):
                raise ValueError(f"{context}: missing native scaling metadata; explicitly declare "
                                 "field_metadata.<record>.allow_unscaled: true only when justified")
            values = np.load(Path(directory) / "values.npy", allow_pickle=False)
            if values.dtype != np.float64 or list(values.shape) != info["shape"]:
                raise ValueError(f"Invalid native array transfer for {context}")
            info["values"] = values
        info["decoder_diagnostics"] = diagnostics
        return info


def inspect_fa(path, profile, fields=(), *, validate_selection=True, timeout_seconds=120.,
              expected_source=None, metadata_fields=(), backend="native", python_executable=None,
              earth_radius_m=None, geometry_options=None):
    return request_fa({"operation": "inspect", "path": str(path), "profile": profile,
                       "fields": list(dict.fromkeys(fields)),
                       "validate_selection": validate_selection,
                       "expected_source": expected_source or {},
                       "metadata_fields": list(dict.fromkeys(metadata_fields)),
                       "backend": backend, "python_executable": python_executable,
                        "earth_radius_m": earth_radius_m,
                        "geometry_options": geometry_options,
                       "timeout_seconds": timeout_seconds})
