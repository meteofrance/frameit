"""Private, disposable FA decoder process; never import the Python GRIB backend.

Control/results use a private JSON file and arrays use NPY. Fortran output is
captured by the caller, separately from the protocol. Source files are only
opened with OLD and closed with KEEP. No native state survives a request.
"""

from __future__ import annotations

import ctypes
import json
import resource
import sys
from datetime import datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import numpy as np


def _words(lfi, unit, records, name):
    return lfi.wlfilec(unit, name, records[name], False)


def _text(words):
    if np.any((words < 0) | (words > 127)):
        raise ValueError("Invalid ASCII in FA character metadata")
    return "".join(chr(int(value)) for value in words).rstrip(" \x00")


def _inspect(fa, lfi, unit, header, request):
    raw = fa.wfacies(*fa.get_facst(), header)
    keys = ("KTYPTR", "PSLAPO", "PCLOPO", "PSLOPO", "PCODIL", "KTRONC",
            "KNLATI", "KNXLON", "KNLOPA", "KNOZPA", "PSINLA", "KNIVER",
            "PREFER", "PAHYBR", "PBHYBR", "LDGARD")
    geometry = dict(zip(keys, raw, strict=True))
    # Work buffers contain inactive/uninitialized entries, including NaNs.
    geometry.pop("KNOZPA")
    geometry["KNLOPA"] = raw[8][:8].tolist()
    geometry["PSINLA"] = raw[10][:16].tolist()
    for key in ("PAHYBR", "PBHYBR"):
        geometry[key] = geometry[key][:int(geometry["KNIVER"]) + 1].tolist()
    stamp = fa.wfadiex(unit)
    year, month, day, hour, minute = (int(v) for v in stamp[:5])
    basis = datetime(year, month, day) + timedelta(seconds=int(stamp[13]))
    if basis.hour != hour or basis.minute != minute or not 1678 <= year <= 2261:
        raise ValueError("Unsupported or inconsistent FA forecast reference date")
    valid = basis + timedelta(seconds=int(stamp[14]))
    if int(stamp[14]) < 0 or not 1678 <= valid.year <= 2261:
        raise ValueError("Unsupported FA valid time or negative forecast lead")
    lfi.wlfipos(unit)
    records = {}
    for _ in range(lfi.wlfinaf(unit)[0]):
        name, length, _position = lfi.wlficas(unit, True)
        name = name.strip()
        if name in records:
            raise ValueError(f"Duplicate FA record {name!r}")
        records[name] = int(length)
    profile = request["profile"]
    surface = "SFX._FBUF_NAME" in records
    if profile is not None and surface != (profile == "surfex_history"):
        raise ValueError(f"FA record layout conflicts with profile {profile!r}")
    descriptors, metadata = {}, {}
    if surface:
        for key in ("PROGRAM", "GRID_TYPE"):
            metadata[key] = _text(_words(lfi, unit, records, "SFX." + key))
        for key in ("VERSION", "BUG", "PACK", "DIM_FULL", "IMAX", "JMAX"):
            metadata[key] = int(_words(lfi, unit, records, "SFX." + key)[0])
        if "SFX.DTCUR" in records:
            current = _words(lfi, unit, records, "SFX.DTCUR")
            if current.size != 4:
                raise ValueError("Unsupported mixed-word SURFEX state timestamp")
            state_time = datetime(*(int(v) for v in current[:3])) + timedelta(
                seconds=float(current.view(np.float64)[3]))
            metadata["STATE_TIME"] = state_time.isoformat()
            metadata["STATE_TIME_MATCHES_HEADER"] = state_time == valid
            if request.get("validate_selection", True) and state_time != valid:
                raise ValueError("SURFEX SFX.DTCUR conflicts with FA header validity; "
                                 "no implicit timestamp substitution")
        if request.get("validate_selection", True) and request.get("fields") and (
            metadata["PROGRAM"] != "AROME" or metadata["PACK"] != 0
        ):
            raise ValueError("Only AROME SURFEX histories with SFX.PACK=0 are supported")
        count = int(_words(lfi, unit, records, "SFX._FBUF_SIZE")[0])
        columns = {}
        for key, width in (("NAME", 32), ("TYPE", 2), ("MASK", 16)):
            words = _words(lfi, unit, records, "SFX._FBUF_" + key)
            if words.size != count * width:
                raise ValueError(f"Inconsistent SURFEX field directory {key}")
            columns[key] = [_text(row) for row in words.reshape(count, width)]
        for key in ("DIM1", "DIM2"):
            values = _words(lfi, unit, records, "SFX._FBUF_" + key)
            if values.size != count:
                raise ValueError(f"Inconsistent SURFEX field directory {key}")
            columns[key] = values.tolist()
        for i, name in enumerate(columns["NAME"]):
            descriptors["SFX." + name] = {key: columns[key][i] for key in columns if key != "NAME"}
    fields = {}
    for name in request.get("fields", []):
        if name not in records:
            raise ValueError(f"Missing requested FA record {name!r}")
        if surface and request.get("validate_selection", True):
            descriptor = descriptors.get(name, {})
            if (descriptor.get("TYPE") != "X1" or descriptor.get("DIM2") != -1
                    or descriptor.get("DIM1") != geometry["KNXLON"] * geometry["KNLATI"]):
                raise ValueError(f"{name}: unsupported SURFEX field type/dimensions {descriptor}")
        try:
            flags = fa.wfanion(unit, name[:4], 0, name[4:])
        except RuntimeError as exc:
            if not request.get("validate_selection", True):
                fields[name] = {"native_error": str(exc)}
                continue
            raise ValueError(f"{name}: unsupported native encoding ({exc}); "
                             "not metadata fallback") from exc
        if request.get("validate_selection", True) and (not flags[0] or flags[1]):
            raise ValueError(f"{name}: spectral or unknown FA records require a separate transform")
        names = "exists", "spectral", "packing", "bits", "truncation", "laplacian"
        fields[name] = dict(zip(names, flags, strict=True))
        if surface:
            fields[name]["surfex_descriptor"] = descriptors[name]
    return {"geometry": geometry, "reference_time": basis.isoformat(),
            "valid_time": valid.isoformat(), "lead_seconds": int(stamp[14]),
            "header_interval_start_seconds": int(stamp[15]),
            "identifier": fa.wfalsif(unit).strip(), "record_count": len(records),
            "records": records, "fields": fields, "surfex_metadata": metadata,
            "field_directory": descriptors}


def handle(request, destination):
    # Importing here keeps even worker-module discovery free of native FA state.
    import falfilfa4py
    from falfilfa4py import FA, LFI

    path = Path(request["path"])
    before = path.stat()
    identity = [before.st_size, before.st_mtime_ns]
    if request.get("identity") is not None and request["identity"] != identity:
        raise ValueError("FA input changed since inventory (size/mtime freshness check)")
    unit = None
    try:
        header = uuid4().hex[:16]
        unit = FA.wfaitou(str(path), "OLD", header)
        info = _inspect(FA, LFI, unit, header, request)
        if request["operation"] == "read":
            name = request["fields"][0]
            grid = info["geometry"]
            if grid["KNXLON"] * grid["KNLATI"] > request.get("max_points", 20_000_000):
                raise ValueError("FA decoded record exceeds the declared "
                                 "max_points resource budget")
            values, undefined, sentinel = FA.wfacilo(
                grid["KNXLON"] * grid["KNLATI"], unit, name[:4], 0, name[4:], False)
            if undefined:
                if np.isnan(sentinel):
                    values[np.isnan(values)] = np.nan
                else:
                    values[values == sentinel] = np.nan
            x0, x1, y0, y1 = request["zone"]
            if not (0 <= x0 < x1 <= grid["KNXLON"] and 0 <= y0 < y1 <= grid["KNLATI"]):
                raise ValueError("Invalid FA native domain selection")
            values = values.reshape(grid["KNLATI"], grid["KNXLON"])[y0:y1, x0:x1]
            key = tuple(slice(*item) if isinstance(item, list) else item for item in request["key"])
            values = np.asarray(values[key])
            if values.ndim:
                values = np.ascontiguousarray(values)
            np.save(destination / "values.npy", values, allow_pickle=False)
            info = {"shape": list(values.shape), "dtype": str(values.dtype)}
        library = ctypes.CDLL(falfilfa4py.shared_objects_library)
        native_version = library.codes_get_api_version
        native_version.restype = ctypes.c_int
        number = native_version()
        info["backend_versions"] = {
            "falfilfa4py": version("falfilfa4py"),
            "ctypesForFortran": version("ctypesForFortran"),
            "FA_ecCodes_C": f"{number // 10000}.{number // 100 % 100}.{number % 100}",
            "FA_python": sys.version.split()[0],
            "FA_definition_policy": "wheel_MEMFS; parent GRIB definition/sample overrides excluded",
        }
        info["identity"] = identity
    finally:
        if unit is not None:
            FA.wfairme(unit, "KEEP")
    after = path.stat()
    if identity != [after.st_size, after.st_mtime_ns]:
        raise ValueError("FA input size/mtime changed during reading")
    return info


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    destination = Path(sys.argv[1])
    try:
        request = json.load(sys.stdin)
        if request.get("operation") not in {"inspect", "read"}:
            raise ValueError("Unknown FA worker operation")
        if request["operation"] == "read":
            request["validate_selection"] = True
        result = {"ok": True, "result": handle(request, destination)}
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    (destination / "response.json").write_text(
        json.dumps(result, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
