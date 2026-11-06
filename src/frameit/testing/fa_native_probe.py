"""FA-only upstream encoding reproducer; no FrameIt decoder or physical reads.

Run in a fresh interpreter, never import this native probe into a GRIB process.
Only explicitly named records are probed. JSON omits paths, values and full indexes;
native diagnostic output must still be reviewed before sharing. No upload occurs.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import resource
import sys
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4


def probe(path, names):
    """Inventory and query encoding only, opening OLD and closing KEEP."""
    if "eccodes" in sys.modules or "cfgrib" in sys.modules:
        raise RuntimeError("Use a fresh FA-only interpreter")
    # Match the production child policy before loading native libraries.
    for key in ("ECCODES_DEFINITION_PATH", "ECCODES_SAMPLES_PATH"):
        os.environ.pop(key, None)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[key] = "1"
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    import falfilfa4py
    from falfilfa4py import FA, LFI

    before = path.stat()
    unit = FA.wfaitou(str(path), "OLD", uuid4().hex[:16])
    try:
        LFI.wlfipos(unit)
        records = {}
        for _ in range(LFI.wlfinaf(unit)[0]):
            name, length, _ = LFI.wlficas(unit, True)
            records[name.strip()] = int(length)
        result = {"record_count": len(records), "probes": {}}
        for name in names:
            if not 4 <= len(name) <= 16 or not name.isascii():
                raise ValueError("Native names must contain 4–16 ASCII characters")
            item = {"length_words": records.get(name), "calls": []}
            calls = [(name[:4], 0, name[4:])]
            if name[0] == "S" and name[1:4].isdigit():
                calls.append(("S", int(name[1:4]), name[4:]))
            for prefix, level, suffix in calls:
                call = {"arguments": [prefix, level, suffix]}
                try:
                    call["flags"] = list(FA.wfanion(unit, prefix, level, suffix))
                except RuntimeError as exc:
                    call["error"] = str(exc)
                item["calls"].append(call)
            result["probes"][name] = item
        library = ctypes.CDLL(falfilfa4py.shared_objects_library)
        api = library.codes_get_api_version
        api.restype = ctypes.c_int
        result["versions"] = {
            "python": sys.version.split()[0],
            "falfilfa4py": version("falfilfa4py"),
            "ctypesForFortran": version("ctypesForFortran"),
            "native_eccodes_api": api(),
            "native_build_revision": "not exposed by this probe",
            "definitions": "wheel MEMFS; parent overrides excluded",
        }
    finally:
        FA.wfairme(unit, "KEEP")
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source size/mtime changed during probe")
    result["size_mtime_unchanged"] = True
    result["identity_strategy"] = "stat freshness only; no content checksum"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("records", nargs="+")
    args = parser.parse_args()
    print(json.dumps(probe(args.path, args.records), indent=2))


if __name__ == "__main__":
    main()
