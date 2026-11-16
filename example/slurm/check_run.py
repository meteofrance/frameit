"""Independently reopen compact qualification outputs; never imports FrameIt.

This checks compact NetCDF runs against recorded source/product clocks.
It checks completion, readability and an optional numerical regression reference,
not scientific validity or source fingerprints.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import xarray as xr
import yaml


def recorded_times(values, clock):
    """Interpret recorded labels in the product's decoded CF calendar."""
    if clock.dtype.kind == "M":
        return np.array(values, dtype="datetime64[ns]")
    import cftime

    calendar = clock.encoding.get("calendar") or clock.values.flat[0].calendar
    return np.array([
        cftime.datetime.strptime(
            str(value).replace("T", " "),
            "%Y-%m-%d %H:%M:%S.%f" if "." in str(value) else "%Y-%m-%d %H:%M:%S",
            calendar=calendar) for value in values], dtype=object)


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
        key = (product["role"], product["source"])
        if key in products:
            raise ValueError(f"Duplicate product role/source: {key}")
        products[key] = path
    if not products:
        raise ValueError("No products in the completed inventory")
    return status, products


def check(root, *, expected_times=None, reference=None):
    status, products = inventory(root)
    reference_products = inventory(reference)[1] if reference is not None else None
    if reference_products is not None and products.keys() != reference_products.keys():
        raise ValueError("Reference product roles/sources differ")
    provenance = yaml.safe_load((root / "run-provenance.yaml").read_text(encoding="utf-8"))
    alignment = provenance.get("time_alignment", {})
    descriptors = {(p["role"], p["source"]): p for p in status["products"]}
    track = None
    if ("track", None) in products:
        with xr.open_dataset(products[("track", None)], engine="netcdf4") as source:
            track = source.load()
        if expected_times is not None and track.time.size != expected_times:
            raise ValueError(f"Expected {expected_times} track times, found {track.time.size}")
    summaries, counts = [], {}
    for key, path in products.items():
        with xr.open_dataset(path, engine="netcdf4") as ds:
            ds.load()  # Deliberately full reads: use compact qualification cases.
            associations = alignment.get("sources", {}).get(key[1], {}).get("associations", [])
            times = (alignment.get("selected_times") if key[0] == "track" else
                     [record["source_time"] for record in associations] if associations else
                     provenance.get("binding", {}).get(key[1], {}).get("selected_times"))
            if not times or not np.array_equal(
                    ds.time.values, recorded_times(times, ds.time)):
                raise ValueError(f"Product clock differs from recorded contract: {path.name}")
            if track is None and expected_times is not None and ds.time.size != expected_times:
                raise ValueError(
                    f"Expected {expected_times} times in {path.name}, found {ds.time.size}")
            if ds.attrs["product_type"] != key[0]:
                raise ValueError(f"Product type differs from manifest: {path.name}")
            descriptor = descriptors[key]
            for name, dimensions in descriptor["dimensions"].items():
                stored = descriptor["stored_names"][name]
                if list(ds[stored].dims) != dimensions or (
                        ds[stored].attrs.get("units") != descriptor["units"][name]):
                    raise ValueError(
                        f"Field contract differs from manifest: {path.name} {name}")
            if key[0] != "track":
                if ds.attrs.get("source_id") != key[1]:
                    raise ValueError(f"Source differs from manifest: {path.name}")
                counts[key[1]] = ds.time.size
                if any(record.get("interval_start") is not None for record in associations):
                    starts = recorded_times([r["interval_start"] for r in associations], ds.time)
                    ends = recorded_times([r["interval_end"] for r in associations], ds.time)
                    intervals = np.column_stack([starts, ends])
                    bounds = {c.attrs["bounds"] for c in ds.coords.values()
                              if c.dims == ("time",) and c.attrs.get("bounds")
                              and c.dtype.kind in {"M", "O"}}
                    if not bounds or any(
                            name not in ds or not np.array_equal(ds[name].values, intervals)
                            for name in bounds):
                        raise ValueError(f"Recorded interval differs from output: {path.name}")
                if "center_time" in ds:
                    centres = recorded_times(
                        [record["coupling_time"] for record in associations], ds.center_time)
                    if not np.array_equal(ds.center_time.values, centres):
                        raise ValueError(f"Broken centre-time linkage: {path.name}")
                if track is not None and (key[0] == "polar" or "center_time" in ds):
                    if "center_time" not in ds:
                        raise ValueError(f"Broken track linkage: {path.name} center_time")
                    linked = track.sel(time=ds.center_time)
                    for name, coordinate in (
                            ("center_time", "time"), ("center_latitude", "latitude"),
                            ("center_longitude", "longitude")):
                        if (name not in ds
                                or not np.array_equal(ds[name].values, linked[coordinate])):
                            raise ValueError(f"Broken track linkage: {path.name} {name}")
            if reference_products is not None:
                with xr.open_dataset(reference_products[key], engine="netcdf4") as baseline:
                    baseline.load()
                    xr.testing.assert_equal(ds, baseline)
                    # Histories and run metadata differ, but variable definitions must agree.
                    for name in ds.variables:
                        xr.testing.assert_identical(ds[name], baseline[name])
            summaries.append({
                "file": path.name, "dimensions": dict(ds.sizes),
                "time_count": ds.time.size,
                "variables": list(ds.data_vars),
                "units": {name: ds[name].attrs.get("units") for name in ds.variables},
            })
    return {
        "ok": True, "time_count": track.time.size if track is not None else None,
        "time_counts": counts, "expected_times": expected_times,
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
