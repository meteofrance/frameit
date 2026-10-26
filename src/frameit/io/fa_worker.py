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

from frameit.io.fa_contracts import (
    PROTOCOL_VERSION,
    SPECTRAL_GATE,
    SURFEX_METADATA,
    check_expected_source,
    layout_definition,
    native_descriptor,
    resolve_descriptor,
)


def _words(lfi, unit, records, name):
    if name not in records or not 0 < records[name] <= 100_000:
        raise ValueError(f"{name}: missing or oversized required FA metadata record")
    return lfi.wlfilec(unit, name, records[name], False)


def _text(words):
    if np.any((words < 0) | (words > 127)):
        raise ValueError("Invalid ASCII in FA character metadata")
    return "".join(chr(int(value)) for value in words).rstrip(" \x00")


def _integer(lfi, unit, records, name):
    words = _words(lfi, unit, records, name)
    if words.size != 1:
        raise ValueError(f"{name}: expected one native integer word")
    return int(words[0])


def _typed_metadata(lfi, unit, records, name, metadata, directory):
    """Explicit small structural reads only; never interpret physical raw words."""
    spec = SURFEX_METADATA.get(name.removeprefix("SFX.")) if name.startswith("SFX.") else None
    if layout_definition(metadata) is None or spec is None:
        raise ValueError(f"{name}: no evidenced release-specific typed metadata definition")
    kind, count = spec
    native_type = directory.get(name, {}).get("TYPE")
    expected_type = {"character": "C0", "integer": "N0", "logical": "L0", "real": "X0",
                     "date_time": "T0", "integer_array": "N1"}[kind]
    if native_type is not None and native_type != expected_type:
        raise ValueError(f"{name}: native directory type {native_type} contradicts "
                         f"{layout_definition(metadata)} definition {expected_type}")
    if name not in records or records[name] > 4096:
        raise ValueError(f"{name}: typed metadata missing or exceeds 4096-word budget")
    words = _words(lfi, unit, records, name)
    if count is not None and words.size != count:
        raise ValueError(f"{name}: inconsistent typed metadata length; expected {count}")
    if kind == "character":
        value = _text(words)
    elif kind == "integer":
        value = int(words[0])
    elif kind == "integer_array":
        value = words.tolist()
    elif kind == "logical":
        if int(words[0]) not in (0, 1):
            raise ValueError(f"{name}: unsupported logical word (only evidenced 0/1 admitted)")
        value = bool(words[0])
    elif kind == "real":
        real = float(words.view(np.float64)[0])
        value = real if np.isfinite(real) else {"nonfinite": str(real)}
    else:  # DTCUR: three integer date words and one IEEE floating seconds word.
        seconds = float(words.view(np.float64)[3])
        if not np.isfinite(seconds):
            raise ValueError(f"{name}: nonfinite state timestamp")
        value = {"date": words[:3].tolist(), "seconds": seconds}
    return {"type": kind, "value": value, "evidence": layout_definition(metadata)}


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
    # A surviving SFX namespace is not evidence of an atmospheric history when
    # directory/source records are missing. Raw inventory must retain that gap.
    surface = any(name.startswith("SFX.") for name in records)
    descriptors, metadata = {}, {}
    required = {"SFX._FBUF_" + key for key in ("SIZE", "NAME", "TYPE", "MASK", "DIM1", "DIM2")}
    required.update("SFX." + key for key in (
        "PROGRAM", "GRID_TYPE", "VERSION", "BUG", "PACK", "DIM_FULL", "IMAX", "JMAX"))
    missing = sorted(required - records.keys()) if surface else []
    if surface:
        for key in ("PROGRAM", "GRID_TYPE"):
            if "SFX." + key in records:
                metadata[key] = _text(_words(lfi, unit, records, "SFX." + key))
        for key in ("VERSION", "BUG", "PACK", "DIM_FULL", "IMAX", "JMAX", "MASDEV", "BUGFIX"):
            if "SFX." + key in records:
                metadata[key] = _integer(lfi, unit, records, "SFX." + key)
    if missing:
        metadata["layout_status"] = "incomplete_surfex_directory"
        metadata["missing_records"] = missing
        if request.get("validate_selection", True) and (
            profile is not None or request.get("fields")
        ):
            raise ValueError(f"Incomplete SURFEX source: missing required records {missing}; "
                             "it cannot be selected as an atmospheric or SURFEX history")
    if profile is not None and surface != (profile == "surfex_history"):
        raise ValueError(f"FA record layout conflicts with profile {profile!r}")
    if surface and not missing:
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
        count = _integer(lfi, unit, records, "SFX._FBUF_SIZE")
        if not 0 < count <= 3125:
            raise ValueError("SURFEX field directory exceeds 100000-word metadata budget")
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
            if not name or "SFX." + name in descriptors:
                raise ValueError("Empty or duplicate SURFEX directory name")
            descriptors["SFX." + name] = {key: columns[key][i] for key in columns if key != "NAME"}
    check_expected_source(metadata, request.get("expected_source", {}))
    fields = {}
    for name in request.get("fields", []):
        if name not in records:
            raise ValueError(f"Missing requested FA record {name!r}")
        if surface and request.get("validate_selection", True):
            descriptor = descriptors.get(name, {})
            if (descriptor.get("TYPE") != "X1" or descriptor.get("DIM2") != -1
                    or descriptor.get("DIM1") != geometry["KNXLON"] * geometry["KNLATI"]):
                raise ValueError(f"{name}: unsupported SURFEX field type/dimensions {descriptor}")
        if (layout_definition(metadata) and name.startswith("SFX.")
                and name[4:] in SURFEX_METADATA):
            fields[name] = {"record_kind": "typed_metadata"}
            continue
        try:
            flags = fa.wfanion(unit, name[:4], 0, name[4:])
        except RuntimeError as exc:
            if not request.get("validate_selection", True):
                fields[name] = {"native_error": str(exc)}
                continue
            raise ValueError(f"{name}: unsupported native encoding ({exc}); "
                             "not metadata fallback") from exc
        if request.get("validate_selection", True):
            if flags[1]:
                raise ValueError(f"{name}: {SPECTRAL_GATE}; native packing={flags[2]}, "
                                 f"bits={flags[3]}. Installing a transform does not "
                                 "qualify decoding")
            if not flags[0]:
                raise ValueError(f"{name}: unknown FA record representation")
        names = "exists", "spectral", "packing", "bits", "truncation", "laplacian"
        fields[name] = dict(zip(names, flags, strict=True))
        if surface:
            fields[name]["surfex_descriptor"] = descriptors.get(name, {})
    typed = {name: _typed_metadata(lfi, unit, records, name, metadata, descriptors)
             for name in request.get("metadata_fields", [])}
    clocks = {"reference_time": basis.isoformat(), "valid_time": valid.isoformat(),
              "lead_seconds": int(stamp[14]),
              "header_interval_start_seconds": int(stamp[15])}
    contracts = {name: native_descriptor(name, records[name], fields.get(name, {}),
                                         descriptors.get(name, {}), geometry, metadata, clocks)
                 for name in dict.fromkeys([*fields, *typed])}
    for contract in contracts.values():
        contract["source"].update(profile=profile,
                                 expected_source=request.get("expected_source", {}))
        if contract["native_id"] in typed:
            contract["eligibility"]["metadata_decode"] = "available"
    return {"geometry": geometry, "reference_time": basis.isoformat(),
            "valid_time": valid.isoformat(), "lead_seconds": int(stamp[14]),
            "header_interval_start_seconds": int(stamp[15]),
            "identifier": fa.wfalsif(unit).strip(), "record_count": len(records),
            "records": records, "fields": fields, "surfex_metadata": metadata,
            "field_directory": descriptors, "field_descriptors": contracts,
            "typed_metadata": typed}


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
            descriptor = info["field_descriptors"][name]
            if descriptor["eligibility"]["decode"] == "blocked":
                raise ValueError(f"{name}: " + "; ".join(descriptor["eligibility"]["reasons"]))
            if request.get("field_declaration") is not None:
                descriptor = resolve_descriptor(descriptor, request["field_declaration"])
            values, undefined, sentinel = FA.wfacilo(
                grid["KNXLON"] * grid["KNLATI"], unit, name[:4], 0, name[4:], False)
            descriptor["mask"]["undefined"] = {
                "present": bool(undefined),
                "sentinel": (float(sentinel) if np.isfinite(sentinel) else str(float(sentinel)))
                if undefined else None,
                "normalization": "native undefined values to NaN; valid zeros retained",
            }
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
            info = {"shape": list(values.shape), "dtype": str(values.dtype),
                    "field_descriptors": {name: descriptor}}
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
        info["protocol_version"] = PROTOCOL_VERSION
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
        if (type(request.get("protocol_version")) is not int
                or request.get("protocol_version") != PROTOCOL_VERSION):
            raise ValueError("Unsupported FA worker protocol_version")
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
