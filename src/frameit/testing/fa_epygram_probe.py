"""C0 library-API evidence, not a production reader or scientific admission gate.

Run once per fresh format-specific interpreter. Reads are explicitly selected;
JSON contains metadata and array counts, never physical values or source paths.
Native diagnostics must still be reviewed before sharing. No upload occurs.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import resource
import sys
import tempfile
from collections import Counter
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np


def _attempt(call):
    try:
        return call()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _array_facts(data):
    if data is None:
        return {"data_present": False}
    values = np.ma.asarray(data)
    result = {"data_present": True, "shape": list(values.shape), "dtype": str(values.dtype)}
    if values.dtype.kind in "fiu":
        result.update(masked=int(np.ma.getmaskarray(values).sum()),
                      nonfinite=int((~np.isfinite(values.filled(0))).sum()),
                      valid_zero=int(np.ma.filled(values == 0, False).sum()))
    return result


def _field_facts(field, *, has_data=True):
    structure = getattr(field, "structure", "Misc")
    # D3Field.getdata() squeezes None in EPyGrAM 2.1.0; d4=True is safe here.
    data = field.getdata() if has_data or structure == "Misc" else field.getdata(d4=True)
    if not has_data and data is not None:
        raise ValueError("Metadata-only request unexpectedly contains data")
    result = {"structure": structure,
              **_array_facts(data)}
    if structure != "Misc":
        result.update(spectral=field.spectral, basis=str(field.validity.getbasis()),
                      valid=str(field.validity.get()),
                      duration=str(field.validity.cumulativeduration()),
                      fixed_surface=field.geometry.vcoordinate.typeoffirstfixedsurface,
                      levels=field.geometry.vcoordinate.levels,
                      horizontal_position=field.geometry.position_on_horizontal_grid)
    return result


def _json_native(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Not a JSON metadata value: {type(value).__name__}")


def _fa_probe(epygram, args):
    import falfilfa4py
    from falfilfa4py import FA, LFI

    from frameit.io.fa_contracts import SURFEX_METADATA

    allowed = {"SFX." + name for name in SURFEX_METADATA} | {
        "SFX._FBUF_" + key for key in ("NAME", "TYPE", "MASK")}
    if not set(args.metadata_fields) <= allowed:
        raise ValueError("Typed reads require a named, evidenced structural metadata layout")
    calls = Counter()
    decoded = []
    originals = {name: getattr(FA, name) for name in (
        "wfaitou", "wfairme", "wfacies", "wfanion", "wfacilo", "wfacile", "wfalais")}

    def counted(name):
        def invoke(*positional, **keywords):
            calls[name] += 1
            if name in {"wfacilo", "wfacile"}:
                decoded.append(positional[2] + positional[4])
            return originals[name](*positional, **keywords)
        return invoke

    # In-memory instrumentation of this disposable probe only, never package edits.
    for name in originals:
        setattr(FA, name, counted(name))
    try:
        with epygram.formats.resource(str(args.path), openmode="r", fmt="FA") as source:
            count = int(LFI.wlfinaf(source._unit)[0])
            if count > args.max_records:
                raise ValueError("FA index exceeds max_records")
            names = source.listfields()
            geometry = source.geometry
            shape = (geometry.dimensions["Y"], geometry.dimensions["X"])
            result = {"record_count_including_header": count, "listfields_count": len(names),
                      "geometry": {"name": geometry.name, "dimensions": geometry.dimensions,
                                   "geoid": geometry.geoid,
                                   "geoid_origin": "EPyGrAM configuration, not producer proof"},
                      "reference_pressure": source.reference_pressure,
                      "basis": str(source.validity.getbasis()), "valid": str(source.validity.get()),
                      "fields": {}, "metadata": {}}
            for name in args.fields:
                if name not in names:
                    raise ValueError(f"Missing exact selected record: {name}")
                item = {"native_flags": _attempt(lambda name=name: list(FA.wfanion(
                    source._unit, name[:4], 0, name[4:]))),
                        "library_type": _attempt(lambda name=name: source.field_type(name)),
                        "encoding": _attempt(lambda name=name: source.fieldencoding(name))}
                # Even getdata=False can inquire spectral dimensions/load ecTrans.
                flags = item["native_flags"]
                if isinstance(flags, list) and flags[0] and not flags[1]:
                    payloads = sum(calls[key] for key in ("wfacilo", "wfacile", "wfalais"))
                    item["metadata_only"] = _attempt(lambda name=name: _field_facts(
                        source.readfield(name, getdata=False), has_data=False))
                    item["metadata_payload_calls"] = sum(calls[key] for key in (
                        "wfacilo", "wfacile", "wfalais")) - payloads
                    if name in args.read_fields:
                        if np.prod(shape) > args.max_points:
                            raise ValueError("Selected full native decode exceeds max_points")
                        item["read"] = _attempt(lambda name=name: _field_facts(
                            source.readfield(name)))
                else:
                    item["read_gate"] = "unresolved native flags or spectral; no payload read"
                result["fields"][name] = item
            result["calls_before_typed_reads"] = dict(calls)
            for name in args.metadata_fields:
                length = int(LFI.wlfinfo(source._unit, name)[0])
                if not 0 < length <= 4096:
                    raise ValueError(f"{name}: metadata exceeds 4096-word budget or is absent")
                item = {"word_count": length,
                        "table": source.sfxflddesc.get(name),
                        "library_type": _attempt(lambda name=name: source.field_type(name))}

                def typed(name=name):
                    field = source.readfield(name)
                    if not isinstance(field, epygram.fields.MiscField):
                        raise ValueError("Selected typed metadata is not a Misc field")
                    data = field.getdata()
                    return {**_field_facts(field), "value": np.asarray(data).tolist()}

                # Do not send a known H2D record through the typed-data route.
                if item["library_type"] != "H2D":
                    item["read"] = _attempt(typed)
                result["metadata"][name] = item
    finally:
        for name, original in originals.items():
            setattr(FA, name, original)
    result["native_calls"] = dict(calls)
    result["decoded_fields"] = decoded
    library = ctypes.CDLL(falfilfa4py.shared_objects_library)
    api = library.codes_get_api_version
    api.restype = ctypes.c_int
    result["FA_ecCodes_C_api"] = api()
    return result


def _grib_probe(epygram, args):
    import eccodes

    keys = ["shortName", "cfVarName", "name", "units", "typeOfLevel", "level", "stepType",
            "startStep", "endStep", "stepUnits", "uvRelativeToGrid", "dataDate", "dataTime",
            "validityDate", "validityTime", "Ni", "Nj", "gridType", "scanningMode"]
    with epygram.formats.resource(str(args.path), openmode="r", fmt="GRIB") as source:
        if source.messages_number > args.max_records:
            raise ValueError("GRIB index exceeds max_records")
        inventory = source.listfields(additional_keys=keys)
        result = {"message_count": source.messages_number,
                  "eccodes_C": eccodes.codes_get_api_version(), "selected": []}
        for selector in args.selectors:
            matches = source.listfields(select=selector, additional_keys=keys)
            if len(matches) != 1:
                raise ValueError(f"Selector must match exactly one message: {selector}")
            item = {"selector": selector, "metadata": matches[0]}
            field = source.readfield(selector, getdata=False, read_misc_metadata=keys)
            item["metadata_only"] = _field_facts(field, has_data=False)
            item["misc_metadata"] = dict(field.misc_metadata)
            result["selected"].append(item)
        result["inventory_count"] = len(inventory)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("format", choices=("FA", "GRIB"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--fields", nargs="*", default=[])
    parser.add_argument("--read-fields", nargs="*", default=[])
    parser.add_argument("--metadata-fields", nargs="*", default=[])
    parser.add_argument("--selectors", type=json.loads, default=[])
    parser.add_argument("--max-points", type=int, default=100_000)
    parser.add_argument("--max-records", type=int, default=2048)
    parser.add_argument("--earth-radius-m", type=float)
    args = parser.parse_args()
    if not set(args.read_fields) <= set(args.fields):
        parser.error("read-fields must be a subset of fields")
    if min(args.max_points, args.max_records) <= 0:
        parser.error("budgets must be positive")
    if any(name in sys.modules for name in ("epygram", "falfilfa4py", "eccodes", "cfgrib")):
        raise RuntimeError("Use a fresh format-specific interpreter")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    for name in ("ECCODES_DEFINITION_PATH", "ECCODES_SAMPLES_PATH",
                 "GRIB_DEFINITION_PATH", "GRIB_SAMPLES_PATH"):
        os.environ.pop(name, None)
    before = args.path.stat()
    with tempfile.TemporaryDirectory(prefix="frameit-c0-") as directory:
        destination = Path(directory)
        if args.format == "FA":
            from frameit.io.fa_epygram import initialize

            epygram = initialize(destination, args.earth_radius_m)
            result = _fa_probe(epygram, args)
            assert not {"eccodes", "cfgrib", "ectrans4py"} & sys.modules.keys()
        else:
            os.environ["HOME"] = directory
            settings = destination / ".epygram"
            settings.mkdir()
            (settings / "userconfig.py").write_text(
                "implemented_formats = ['GRIB']\nactivate_plugins = []\n"
                "init_at_import = False\n" + f"GRIB_safe_indexes = {directory!r}\n",
                encoding="utf-8")
            import epygram

            assert epygram.formats.runtime_available_formats == ["GRIB"]
            result = _grib_probe(epygram, args)
            assert "falfilfa4py" not in sys.modules
    after = args.path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source size/mtime changed")
    result.update(identity_strategy="size/mtime freshness only; no checksum/corruption proof",
                  source_stat_unchanged=True, python=sys.version.split()[0],
                  versions={name: version(name) for name in (
                      ("epygram", "falfilfa4py", "ctypesForFortran") if args.format == "FA"
                      else ("epygram", "eccodes"))})
    if args.format == "GRIB":
        # Conda supplies the native library without the pip-only eccodeslib distribution.
        try:
            result["versions"]["eccodeslib"] = version("eccodeslib")
        except PackageNotFoundError:
            result["versions"]["eccodeslib"] = None
    print(json.dumps(result, indent=2, allow_nan=False, default=_json_native))


if __name__ == "__main__":
    main()
