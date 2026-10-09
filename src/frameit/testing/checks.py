"""Execution/product contracts, deliberately separate from reference validation."""

from __future__ import annotations

from pathlib import Path

from .catalog import time_strings


def check_products(case, products):
    """Check descriptors returned by this execution, never a directory glob.

    A PASS establishes contract compliance, not numerical equivalence. No
    universal finite-everywhere or wind-sign threshold is applied to fields.
    Only small coordinates and track variables are read into memory.
    """
    import numpy as np
    from netCDF4 import Dataset, num2date

    expected = case["expected"]
    checks, actual = [], []

    def record(name, ok, reason="", **detail):
        checks.append({"name": name, "ok": bool(ok), "reason": reason if not ok else "", **detail})

    by_key = {}
    for product in products:
        role, group = product.get("role"), product.get("group")
        key = role, group
        if role not in {"track", "cart", "polar"}:
            record("descriptor-role", False, f"Unknown product role: {role}")
            continue
        if key in by_key:
            record("descriptor-uniqueness", False, f"Duplicate product descriptor: {key}")
        by_key[key] = product
    if not case["config"].get("compute_polar_proj", False):
        record(
            "polar-disabled",
            not any(k[0] == "polar" for k in by_key),
            "Cartesian-only case returned polar products",
        )
    contracts = expected.get("products", [])
    if not contracts:
        record("expected-contract", False, "Resolved case lacks expected product contracts")
    for contract in contracts:
        key = contract["role"], contract.get("group")
        if key not in by_key:
            record("product-present", False, f"Missing product: {key}", role=key[0], group=key[1])
            continue
        descriptor = by_key[key]
        path = Path(descriptor["path"])
        try:
            with Dataset(path) as dataset:
                detail = dict(role=key[0], group=key[1], path=str(path))
                record("product-readable", True, **detail)
                metadata = dict(
                    detail,
                    dimensions={k: len(v) for k, v in dataset.dimensions.items()},
                    variables=list(dataset.variables),
                    coordinates={},
                )
                actual.append(metadata)
                if "time" not in dataset.variables or dataset["time"].dimensions != ("time",):
                    record("time-coordinate", False, "Expected time(time) coordinate", **detail)
                else:
                    time = dataset["time"]
                    calendar = getattr(time, "calendar", "standard")
                    dates = time_strings(num2date(time[:], time.units, calendar))
                    metadata["times"] = dates
                    metadata["coordinates"]["time"] = {
                        "units": time.units,
                        "calendar": calendar,
                        "dtype": str(time.dtype),
                    }
                    record(
                        "exact-times",
                        dates == expected["times"],
                        f"Actual times {dates} differ from expected {expected['times']}",
                        **detail,
                    )
                missing = set(contract["variables"]) - set(dataset.variables)
                record("variables", not missing, f"Missing variables: {sorted(missing)}", **detail)
                for coordinate, values in contract.get("levels", {}).items():
                    if coordinate not in dataset.variables:
                        record(
                            "physical-levels", False, f"Missing coordinate {coordinate}", **detail
                        )
                        continue
                    variable = dataset[coordinate]
                    observed = np.ma.asarray(variable[:]).reshape(-1)
                    metadata["coordinates"][coordinate] = {
                        "values": [
                            float(v) if not np.ma.is_masked(v) and np.isfinite(v) else None
                            for v in observed
                        ],
                        "units": getattr(variable, "units", ""),
                        "dtype": str(variable.dtype),
                        "missing_value_convention": "null",
                    }
                    ok = not np.ma.getmaskarray(observed).any() and np.array_equal(observed, values)
                    record(
                        "physical-levels",
                        ok,
                        f"{coordinate}: actual {observed.tolist()} differs from {values}",
                        **detail,
                    )
                if key[0] == "track":
                    _check_track(dataset, expected, metadata, record, detail)
                else:
                    _check_field_samples(dataset, contract, expected, metadata, record, detail)
                if key[0] == "polar":
                    ok = (
                        {"rr", "theta"} <= set(dataset.dimensions)
                        and "theta_deg" in dataset.variables
                        and dataset["theta_deg"].dimensions == ("theta",)
                    )
                    record(
                        "polar-grid",
                        ok,
                        "Polar product lacks rr/theta dimensions or theta_deg(theta)",
                        **detail,
                    )
        except Exception as exc:
            record(
                "product-readable", False, f"Cannot check {path}: {exc}", role=key[0], group=key[1]
            )
    required_keys = {(c["role"], c.get("group")) for c in contracts}
    extras = set(by_key) - required_keys
    record(
        "product-contract",
        not extras,
        f"Unexpected product descriptors: {sorted(map(str, extras))}",
    )
    failures = [c["reason"] for c in checks if not c["ok"]]
    return {
        "ok": not failures,
        "checks": checks,
        "reason": "; ".join(failures),
        "products": actual,
        "reference_validation": "not_performed",
    }


def _check_track(dataset, expected, metadata, record, detail):
    import numpy as np

    axes = {}
    for name in ("cx", "cy"):
        if name not in dataset.variables:
            continue
        values = np.ma.asarray(dataset[name][:]).reshape(-1)
        finite = (
            dataset[name].dimensions == ("time",)
            and len(values) == len(expected["times"])
            and not np.ma.getmaskarray(values).any()
            and np.all(np.isfinite(values))
        )
        record(
            "finite-centres", finite, f"Track {name} contains missing/nonfinite centres", **detail
        )
        if finite:
            axes[name] = np.asarray(values)
            metadata[name] = values.tolist()
        if "centres" in expected:
            reference = [c[name] for c in expected["centres"]]
            record(
                "expected-centres",
                finite and np.array_equal(values, reference),
                f"Track {name} differs from independent expected indices {reference}",
                **detail,
            )
    if "shape" in expected and len(axes) == 2:
        ny, nx = expected["shape"]
        ok = np.all((axes["cx"] >= 0) & (axes["cx"] < nx)) and np.all(
            (axes["cy"] >= 0) & (axes["cy"] < ny)
        )
        record("centre-domain", ok, "Track centre is outside the input domain", **detail)
    if expected.get("complete_boxes", True):
        if "valid_box" not in dataset.variables:
            record("complete-boxes", False, "Track lacks valid_box", **detail)
        else:
            valid = np.ma.asarray(dataset["valid_box"][:])
            ok = (
                dataset["valid_box"].dimensions == ("time",)
                and len(valid.reshape(-1)) == len(expected["times"])
                and not np.ma.getmaskarray(valid).any()
                and np.all(valid == 1)
            )
            record(
                "complete-boxes", ok, "Tracker selected a box outside the input domain", **detail
            )


def _check_field_samples(dataset, contract, expected, metadata, record, detail):
    """Require some finite data per requested field/time, in bounded reads.

    The explicit initial-time gaps are allowed. This is a readability/mask
    contract, not a physical-range or reference-comparison policy.
    """
    import numpy as np

    allowed = {
        (gap["group"], gap["variable"], time)
        for gap in expected.get("allowed_gaps", [])
        for time in gap["times"]
    }
    for name in contract["variables"]:
        if name not in dataset.variables:
            continue
        variable = dataset[name]
        horizontal = {"rr", "theta"} if contract["role"] == "polar" else {"y_box", "x_box"}
        required_dims = horizontal | {"time"} | set(contract.get("levels", {}))
        record(
            "field-dimensions",
            required_dims <= set(variable.dimensions),
            f"{name} dimensions {variable.dimensions} lack required {sorted(required_dims)}",
            **detail,
        )
        if "time" not in variable.dimensions:
            record("field-time-dimension", False, f"{name} lacks a time dimension", **detail)
            continue
        time_axis = variable.dimensions.index("time")
        spatial = [i for i, n in enumerate(variable.shape) if i != time_axis and n]
        split = max(spatial, key=lambda i: variable.shape[i]) if spatial else None
        elements = int(
            np.prod([n for i, n in enumerate(variable.shape) if i not in {time_axis, split}])
        )
        slab = max(1, 262144 // max(1, elements))
        for index, stamp in enumerate(metadata.get("times", [])):
            if (contract.get("group"), name, stamp) in allowed:
                record("field-finite-sample", True, variable=name, time=stamp, **detail)
                continue
            usable = False
            width = variable.shape[split] if split is not None else 1
            for start in range(0, width, slab):
                selection = [slice(None)] * variable.ndim
                selection[time_axis] = index
                if split is not None:
                    selection[split] = slice(start, min(start + slab, width))
                values = np.ma.asarray(variable[tuple(selection)])
                if np.any(np.isfinite(np.ma.filled(values.astype(float), np.nan))):
                    usable = True
                    break
            record(
                "field-finite-sample",
                usable,
                f"{name} has no finite data at {stamp}; no gap is allowed",
                variable=name,
                time=stamp,
                **detail,
            )
