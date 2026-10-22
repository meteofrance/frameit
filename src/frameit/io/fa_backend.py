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
    summary = {"decode_requests": 0, "warnings": [], "backend_versions": {}}
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
    environment = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                       MKL_NUM_THREADS="1", PYTHONNOUSERSITE="1")
    # The wheel's private ecCodes uses its own matching MEMFS definitions.
    # Parent GRIB overrides remain untouched and must not change child decoding.
    for key in ("ECCODES_DEFINITION_PATH", "ECCODES_SAMPLES_PATH"):
        environment.pop(key, None)
    with _REQUEST_LOCK, tempfile.TemporaryDirectory(prefix="frameit-fa-") as directory:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "frameit.io.fa_worker", directory],
                input=json.dumps(request), capture_output=True, text=True, errors="replace",
                env=environment, check=False, timeout=request.get("timeout_seconds", 120.),
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"FA request timed out for {Path(request['path']).name}; "
                             "review input.fa.timeout_seconds and source availability") from exc
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
        if request["operation"] == "read":
            _record_diagnostics(request, {"diagnostics": diagnostics,
                                          "backend_versions": info["backend_versions"]})
        if diagnostics:
            log.warning("FA decoder %s: %s", context, diagnostics)
        if request["operation"] == "read":
            if ("has no encoded FMULTM and FMULTE" in diagnostics
                    and not request.get("allow_unscaled")):
                raise ValueError(f"{context}: missing native scaling metadata; explicitly declare "
                                 "field_metadata.<record>.allow_unscaled: true only when justified")
            values = np.load(Path(directory) / "values.npy", allow_pickle=False)
            if values.dtype != np.float64 or list(values.shape) != info["shape"]:
                raise ValueError(f"Invalid native array transfer for {context}")
            info["values"] = values
        info["decoder_diagnostics"] = diagnostics
        return info


def inspect_fa(path, profile, fields=(), *, validate_selection=True, timeout_seconds=120.):
    return request_fa({"operation": "inspect", "path": str(path), "profile": profile,
                       "fields": list(dict.fromkeys(fields)),
                       "validate_selection": validate_selection,
                       "timeout_seconds": timeout_seconds})
