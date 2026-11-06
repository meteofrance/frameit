"""Bounded, isolated native FA requests, safe alongside cfgrib in the parent."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
from math import prod
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
               "field_observations": {}, "payload_reads": {}}
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
                if record.get("payload_read"):
                    summary["payload_reads"].setdefault(record["source_file"], {}).update(
                        {name: record["payload_read"] for name in record["fields"]})
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
    if request.get("backend") == "native":
        log.warning("FA backend: native is a deprecated alias for epygram; "
                    "use backend: epygram and install FrameIt[fa] in the helper")
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
        try:
            payload = json.loads(response.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Invalid FA decoder response for {context}: {exc}") from exc
        if not isinstance(payload, dict) or type(payload.get("ok")) is not bool:
            raise ValueError(f"Invalid FA decoder response for {context}")
        if not payload["ok"]:
            _record_diagnostics(request, {"diagnostics": diagnostics, "error": payload["error"]})
            raise ValueError(f"FA input {context}: {payload['error']}\n{diagnostics[-4000:]}")
        info = payload.get("result")
        if not isinstance(info, dict):
            raise ValueError(f"Invalid FA decoder response for {context}")
        if (type(info.get("protocol_version")) is not int
                or info.get("protocol_version") != PROTOCOL_VERSION):
            raise ValueError(f"Unsupported FA response protocol_version for {context}")
        for name, descriptor in info.get("field_descriptors", {}).items():
            validate_descriptor(descriptor)
            if descriptor["native_id"] != name:
                raise ValueError(f"FA descriptor native identity mismatch for {context}")
        if diagnostics:
            observed = any(d["scaling"].get("status") == "encoded"
                           for d in info.get("field_descriptors", {}).values())
            note = " [encoded FA factors observed]" if observed else ""
            log.warning("FA decoder %s%s: %s", context, note, diagnostics)
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
            # FADGRA's unknown-parameter warning can coexist with encoded factors.
            observed = descriptor["scaling"].get("status") == "encoded"
            missing = "has no encoded FMULTM and FMULTE" in diagnostics and not observed
            if not observed:
                descriptor["scaling"].update(
                    status="missing" if missing else "not_exposed",
                    evidence="native_diagnostic_text" if missing else "no_structured_native_query",
                    fallback="identity_explicit_opt_in" if missing and request.get(
                        "allow_unscaled") else None,
                )
            _record_diagnostics(request, {"diagnostics": diagnostics,
                                          "backend_versions": info["backend_versions"],
                                          "payload_read": info.get("payload_read"),
                                          "protocol_version": PROTOCOL_VERSION,
                                          "field_descriptors": info["field_descriptors"]})
            if missing and not request.get("allow_unscaled"):
                raise ValueError(f"{context}: unresolved native scaling metadata; "
                                 "explicitly declare "
                                 "field_metadata.<record>.allow_unscaled: true only when justified")
            shape = info.get("shape")
            budget = request.get("max_points", 20_000_000)
            if (not isinstance(shape, list) or len(shape) > 2
                    or any(type(n) is not int or not 0 <= n <= budget for n in shape)
                    or prod(shape) > budget):
                raise ValueError(f"Invalid native array transfer for {context}")
            try:
                # Map first: a corrupt NPY header must not allocate before its
                # dtype/shape is checked. Detach before the owned directory closes.
                transfer = np.load(Path(directory) / "values.npy", allow_pickle=False,
                                   mmap_mode="r")
                try:
                    if (not isinstance(transfer, np.ndarray) or transfer.dtype != np.float64
                            or list(transfer.shape) != shape):
                        raise ValueError("dtype/shape contradicts the FA response")
                    info["values"] = np.array(transfer, copy=True)
                finally:
                    del transfer
            except (OSError, ValueError, EOFError) as exc:
                raise ValueError(f"Invalid native array transfer for {context}: {exc}") from exc
        info["decoder_diagnostics"] = diagnostics
        return info


def inspect_fa(path, profile, fields=(), *, validate_selection=True, timeout_seconds=120.,
              expected_source=None, metadata_fields=(), backend="epygram", python_executable=None,
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
