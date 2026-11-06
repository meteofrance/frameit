"""Independently reopen compact qualification outputs; never imports FrameIt.

This checks run completion, readability and an optional numerical regression
reference. It does not establish scientific validity or fingerprint source data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import xarray as xr
import yaml


def inventory(root):
    root = root.resolve()
    status = yaml.safe_load((root / "run-status.yaml").read_text(encoding="utf-8"))
    if status["state"] != "completed" or not status.get("tracking_complete"):
        raise ValueError(f"Run is not complete: {status['state']}")
    if (root / ".frameit-run.lock").exists():
        raise ValueError("Run is still locked")
    products = {}
    for product in status["products"]:
        relative = Path(product["path"])
        path = (root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root) or path.suffix != ".nc":
            raise ValueError(f"Invalid product path: {relative}")
        if path.stat().st_size != product["size_bytes"]:
            raise ValueError(f"Product size changed: {relative}")
        key = (product["role"], product["group"])
        if key in products:
            raise ValueError(f"Duplicate product role/group: {key}")
        products[key] = path
    if ("track", None) not in products:
        raise ValueError("No exported track in the completed inventory")
    return status, products


def check(root, *, expected_times=None, reference=None):
    status, products = inventory(root)
    reference_products = inventory(reference)[1] if reference is not None else None
    if reference_products is not None and products.keys() != reference_products.keys():
        raise ValueError("Reference product roles/groups differ")
    with xr.open_dataset(products[("track", None)], engine="netcdf4") as track:
        times = track.time.values
    if expected_times is not None and len(times) != expected_times:
        raise ValueError(f"Expected {expected_times} track times, found {len(times)}")
    summaries = []
    for key, path in products.items():
        with xr.open_dataset(path, engine="netcdf4") as ds:
            ds.load()  # Deliberately full reads: use compact qualification cases.
            np.testing.assert_array_equal(ds.time.values, times)
            if ds.attrs["product_type"] != key[0]:
                raise ValueError(f"Product type differs from manifest: {path.name}")
            if key[0] != "track" and ds.attrs["track_filename"] != products[("track", None)].name:
                raise ValueError(f"Broken track linkage: {path.name}")
            if reference_products is not None:
                with xr.open_dataset(reference_products[key], engine="netcdf4") as baseline:
                    baseline.load()
                    xr.testing.assert_equal(ds, baseline)
                    # Histories and run metadata differ, but variable definitions must agree.
                    for name in ds.variables:
                        xr.testing.assert_identical(ds[name], baseline[name])
            summaries.append({
                "file": path.name, "dimensions": dict(ds.sizes),
                "variables": list(ds.data_vars),
                "units": {name: ds[name].attrs.get("units") for name in ds.variables},
            })
    return {
        "ok": True, "time_count": len(times), "expected_times": expected_times,
        "comparison": "exact decoded values and variable metadata" if reference else None,
        "runtime": status["runtime"], "resources": status["resources"],
        "duration_s": status["duration_s"], "products": summaries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--expected-times", type=int)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--report", type=Path, help="Fresh JSON report path")
    args = parser.parse_args()
    try:
        result = check(args.run, expected_times=args.expected_times, reference=args.reference)
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    text = json.dumps(result, indent=2, allow_nan=False)
    if args.report:
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
    print(text)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
