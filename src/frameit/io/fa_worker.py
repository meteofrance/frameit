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

import numpy as np

from frameit.io.fa_contracts import (
    CUBE_VERTICAL_INTERPRETATION,
    PROTOCOL_VERSION,
    SPECTRAL_GATE,
    SURFEX_METADATA,
    check_expected_source,
    layout_definition,
    native_descriptor,
    resolve_descriptor,
)


def _text(words):
    if np.any((words < 0) | (words > 127)):
        raise ValueError("Invalid ASCII in FA character metadata")
    return "".join(chr(int(value)) for value in words).rstrip(" \x00")


def _typed_spec(records, name, metadata, directory):
    """Release/type/length evidence gate before selected library metadata reads."""
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
    if count is not None and records[name] != count:
        raise ValueError(f"{name}: inconsistent typed metadata length; expected {count}")
    return kind, count


def _active_header(geometry):
    """Bound original admission/corner/normalization evidence from the library."""
    geometry = dict(geometry)
    # Work buffers contain inactive/uninitialized entries, including NaNs.
    geometry.pop("KNOZPA")
    geometry["KNLOPA"] = geometry["KNLOPA"][:8].tolist()
    geometry["PSINLA"] = geometry["PSINLA"][:16].tolist()
    for key in ("PAHYBR", "PBHYBR"):
        geometry[key] = geometry[key][:int(geometry["KNIVER"]) + 1].tolist()
    return geometry


def _describe(fa, unit, geometry, clocks, identifier, records, request, *, source):
    """Scientific/failure adapter over one EPyGrAM resource, not another reader."""
    from frameit.io.fa_epygram import check_surface_layout, structure_value, typed_metadata

    def structure(name, kind, count=None, budget=100_000):
        return structure_value(source, name, records, kind, count, budget=budget)

    profile = request["profile"]
    # A surviving SFX namespace is not evidence of an atmospheric history when
    # directory/source records are missing. Raw inventory must retain that gap.
    surface = any(name.startswith("SFX.") for name in records)
    descriptors, metadata = {}, {}
    required = {"SFX._FBUF_" + key for key in ("SIZE", "NAME", "TYPE", "MASK", "DIM1", "DIM2")}
    required.update("SFX." + key for key in (
        "PROGRAM", "GRID_TYPE", "VERSION", "BUG", "PACK", "DIM_FULL", "IMAX", "JMAX"))
    required.add("SFX.DTCUR")
    missing = sorted(required - records.keys()) if surface else []
    if surface:
        for key in ("PROGRAM", "GRID_TYPE"):
            if "SFX." + key in records:
                metadata[key] = structure("SFX." + key, "character")
        for key in ("VERSION", "BUG", "PACK", "DIM_FULL", "IMAX", "JMAX", "MASDEV", "BUGFIX"):
            if "SFX." + key in records:
                # The library's L0 accessor discards non-0/1 logical words.
                kind = "logical" if key == "PACK" else "integer"
                metadata[key] = structure("SFX." + key, kind, 1)
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
        current = structure("SFX.DTCUR", "date_time", 4, budget=4096)
        if current.size != 4:
            raise ValueError("Unsupported mixed-word SURFEX state timestamp")
        if not np.isfinite(current.view(np.float64)[3]):
            raise ValueError("SURFEX SFX.DTCUR has a nonfinite state timestamp")
        state_time = datetime(*(int(v) for v in current[:3])) + timedelta(
            seconds=float(current.view(np.float64)[3]))
        metadata["STATE_TIME"] = state_time.isoformat()
        matches = state_time.isoformat() == clocks["valid_time"]
        metadata["STATE_TIME_MATCHES_HEADER"] = matches
        if request.get("validate_selection", True) and not matches:
            raise ValueError("SURFEX SFX.DTCUR conflicts with FA header validity; "
                             "no implicit timestamp substitution")
        if request.get("validate_selection", True) and request.get("fields") and (
            metadata["PROGRAM"] != "AROME" or metadata["PACK"] != 0
        ):
            raise ValueError("Only AROME SURFEX histories with SFX.PACK=0 are supported")
        count = structure("SFX._FBUF_SIZE", "integer", 1)
        if not 0 < count <= 3125:
            raise ValueError("SURFEX field directory exceeds 100000-word metadata budget")
        columns = {}
        for key, width in (("NAME", 32), ("TYPE", 2), ("MASK", 16)):
            words = structure("SFX._FBUF_" + key, "integer_array", count * width)
            if words.size != count * width:
                raise ValueError(f"Inconsistent SURFEX field directory {key}")
            columns[key] = [_text(row) for row in words.reshape(count, width)]
        for key in ("DIM1", "DIM2"):
            values = structure("SFX._FBUF_" + key, "integer_array", count)
            if values.size != count:
                raise ValueError(f"Inconsistent SURFEX field directory {key}")
            columns[key] = values.tolist()
        for i, name in enumerate(columns["NAME"]):
            if not name or "SFX." + name in descriptors:
                raise ValueError("Empty or duplicate SURFEX directory name")
            descriptors["SFX." + name] = {key: columns[key][i] for key in columns if key != "NAME"}
        check_surface_layout(source, metadata, descriptors, records, request)
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
            # EPyGrAM's broad -91/-93/-94 Misc fallback conceals physical failures.
            # Observe selected encoding on its unit; never retry another decoder.
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
    typed = {name: typed_metadata(source, name, records, metadata, descriptors)
              for name in request.get("metadata_fields", [])}
    contracts = {name: native_descriptor(name, records[name], fields.get(name, {}),
                                         descriptors.get(name, {}), geometry, metadata, clocks)
                 for name in dict.fromkeys([*fields, *typed])}
    for contract in contracts.values():
        contract["source"].update(profile=profile,
                                 expected_source=request.get("expected_source", {}))
        if contract["native_id"] in typed:
            contract["eligibility"]["metadata_decode"] = "available"
    return {"geometry": geometry, **clocks,
            "identifier": identifier, "record_count": len(records),
            "records": records, "fields": fields, "surfex_metadata": metadata,
            "field_directory": descriptors, "field_descriptors": contracts,
            "typed_metadata": typed}


def handle(request, destination):
    # Importing here keeps even worker-module discovery free of native FA state.
    backend = request.get("backend", "epygram")
    if backend not in {"native", "epygram"}:
        raise ValueError("Unknown FA backend")
    from frameit.io.fa_epygram import initialize, inspect_resource, read_values

    epygram = initialize(destination, request.get("earth_radius_m"))
    import falfilfa4py

    path = Path(request["path"])
    before = path.stat()
    identity = [before.st_size, before.st_mtime_ns]
    if request.get("identity") is not None and request["identity"] != identity:
        raise ValueError("FA input changed since inventory (size/mtime freshness check)")
    # Own before opening: failed geometry/validity reads must close this unit too.
    epy_resource = epygram.formats.resource(
        str(path), openmode="r", fmt="FA", fmtdelayedopen=True)
    try:
        epy_resource.open()
        info = inspect_resource(epy_resource, request)
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
            if request.get("cube_association") is not None:
                descriptor["sampling"]["native_cube"] = request["cube_association"]
                descriptor["sampling"]["vertical_interpretation"] = CUBE_VERTICAL_INTERPRETATION
            values, undefined = read_values(
                epy_resource, name, (grid["KNLATI"], grid["KNXLON"]))
            payload_read = {
                "library": "EPyGrAM", "accessor": "_readH2DField(getdata=True)",
                "resource_class": f"{type(epy_resource).__module__}.{type(epy_resource).__name__}",
                "openmode": epy_resource.openmode,
            }
            descriptor["mask"]["undefined"] = {
                "present": bool(undefined),
                "origin": "EPyGrAM_returned_mask",
                "sentinel_origin": "normalized_NaN; original native flag/sentinel not exposed",
                "sentinel": "nan" if undefined else None,
                "normalization": "native undefined values to NaN; valid zeros retained",
            }
            descriptor["mask"]["nonfinite_count"] = int(np.count_nonzero(~np.isfinite(values)))
            x0, x1, y0, y1 = request["zone"]
            if not (0 <= x0 < x1 <= grid["KNXLON"] and 0 <= y0 < y1 <= grid["KNLATI"]):
                raise ValueError("Invalid FA native domain selection")
            values = values[y0:y1, x0:x1]
            key = tuple(slice(*item) if isinstance(item, list) else item for item in request["key"])
            values = np.asarray(values[key])
            if values.ndim:
                values = np.ascontiguousarray(values)
            np.save(destination / "values.npy", values, allow_pickle=False)
            info = {"shape": list(values.shape), "dtype": str(values.dtype),
                    "field_descriptors": {name: descriptor}, "payload_read": payload_read}
        library = ctypes.CDLL(falfilfa4py.shared_objects_library)
        native_version = library.codes_get_api_version
        native_version.restype = ctypes.c_int
        number = native_version()
        info["backend_versions"] = {
            "FA_backend": "epygram",
            "FA_backend_requested": backend,
            "FA_backend_migration": ("deprecated native alias resolved to epygram; "
                                     "install FrameIt[fa] and use backend: epygram"
                                     if backend == "native" else None),
            "falfilfa4py": version("falfilfa4py"),
            "ctypesForFortran": version("ctypesForFortran"),
            "FA_ecCodes_C": f"{number // 10000}.{number // 100 % 100}.{number % 100}",
            "FA_python": sys.version.split()[0],
            "FA_definition_policy": "wheel_MEMFS; parent GRIB definition/sample overrides excluded",
        }
        if any(name in sys.modules for name in ("eccodes", "cfgrib", "epygram.formats.GRIB")):
            raise ValueError("EPyGrAM FA worker unexpectedly initialized a Python GRIB backend")
        if "ectrans4py" in sys.modules:
            raise ValueError("EPyGrAM gridpoint worker unexpectedly loaded spectral transforms")
        info["backend_versions"].update(
            EPyGrAM=version("epygram"),
            EPyGrAM_ecTrans_distribution=version("ectrans4py"),
            EPyGrAM_netCDF4_distribution=version("netCDF4"),
            EPyGrAM_policy="FA-only private child configuration; no personal tables/plugins; "
                           "gridpoint read only, no spectral/vertical/vector derivation")
        info["identity"] = identity
        info["protocol_version"] = PROTOCOL_VERSION
    finally:
        epy_resource.close()
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
