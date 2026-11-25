"""Compare reported preflight facts, never infer changes in the underlying data."""

import json
from pathlib import Path


def product_key(product):
    name, source = product["product"], product.get("source")
    return f"{source}.{name}" if source else name


def product_path(plan, product):
    path = product.get("path")
    if path and plan.get("output_directory"):
        return str(Path(plan["output_directory"]) / path)
    return path


def _findings(report):
    items = [("Error", item) for item in report["errors"]]
    items.extend(("Warning", item) for item in report["warnings"])
    items.extend(("Blocked", item) for item in report["deferred_checks"]
                 if item["status"] == "blocked")
    # Authored line marks and contextual ordering are not diagnostic identity.
    return {
        (level, json.dumps(item if level == "Warning" else {
            key: item[key] for key in ("code", "path", "message", "expected", "observed",
                                      "prerequisites") if key in item
        }, sort_keys=True)): (level, item)
        for level, item in items
    }


def _finding_label(finding):
    level, item = finding
    if level == "Warning":
        return f"Warning · {item}"
    message = item["message"].split("\n", 1)[0]
    observed = item.get("observed")
    if item.get("code") == "E1201" and isinstance(observed, dict) and observed.get("files"):
        names = observed["files"]
        message = ", ".join(Path(path).name for path in names[:3])
        if len(names) > 3:
            message += f" (+{len(names) - 3} more)"
    if len(message) > 120:
        message = message[:117] + "…"
    identity = f"[{item['code']}]" if "code" in item else level
    return f"{identity} {item['path']} · {message}"


def _schema_only(report):
    return any(check["status"] == "schema-only" for check in report["deferred_checks"])


def _usable_plan(report):
    return report["status"] == "ok" and not _schema_only(report) and not any(
        item["status"] == "blocked" for item in report["deferred_checks"])


def _time_extent(times):
    first, last = times[0], times[-1]
    if isinstance(first, dict) and isinstance(last, dict):
        calendar = (first["calendar"], last["calendar"])
        return calendar, f"{first['label']} → {last['label']} ({first['calendar']})"
    return (None, None), f"{first} → {last}"


def report_changes(before, after):
    """Return concise labels and, only when present in the new report, jump targets."""
    rows = []

    def add(label, target=None):
        rows.append((label, target))

    for key in ("command", "report_version"):
        if before[key] != after[key]:
            add(f"Not comparable: different report {key.replace('_', ' ')}.")
            return rows

    if _schema_only(before) == _schema_only(after):
        old, new = _findings(before), _findings(after)
        for token, finding in new.items():
            if token not in old:
                add(f"Newly reported: {_finding_label(finding)}", ("finding", finding))
        for token, finding in old.items():
            if token not in new:
                add(f"No longer reported: {_finding_label(finding)}")
        if retained := len(old.keys() & new.keys()):
            add(f"Still reported: {retained} finding(s)")
    else:
        add("Findings not compared: different check scopes.")

    left, right = (report["data"]["configuration"] for report in (before, after))
    if left is None or right is None:
        add("Effective settings not comparable: one report did not establish a configuration.")
    else:
        for key in ("output", "products", "region", "resources"):
            if left.get(key) != right.get(key):
                add(f"Effective setting changed: {key}", ("setting", key))
        old_sources, new_sources = left.get("sources", {}), right.get("sources", {})
        for name in sorted(old_sources.keys() | new_sources.keys()):
            prefix = f"sources.{name}"
            if name not in old_sources or name not in new_sources:
                present = name in new_sources
                verb = "Newly declared" if present else "No longer declared"
                add(f"{verb}: {prefix}", ("setting", prefix) if present else None)
                continue
            for key in ("model", "format", "variables", "time", "files", "exclude"):
                if old_sources[name].get(key) != new_sources[name].get(key):
                    add(f"Effective setting changed: {prefix}.{key}",
                        ("setting", f"{prefix}.{key}"))

    old_plan, new_plan = (report["data"]["plan"] for report in (before, after))
    old_sources, new_sources = (plan.get("sources", {}) for plan in (old_plan, new_plan))
    for name in sorted(old_sources.keys() | new_sources.keys()):
        left, right = old_sources.get(name, {}), new_sources.get(name, {})
        times = left.get("selected_times"), right.get("selected_times")
        identity = ("model", "format", "physical_type")
        if (not all(times) or not left.get("model") or not left.get("format")
                or any(left.get(key) != right.get(key) for key in identity)
                or "files" not in left or "files" not in right):
            add(f"Selected coverage not comparable: {name}")
            continue
        target = ("source", name)
        if len(left["files"]) != len(right["files"]):
            add(f"{name} · selected files: {len(left['files'])} → {len(right['files'])}", target)
        old_time, new_time = map(_time_extent, times)
        if len(times[0]) != len(times[1]):
            add(f"{name} · selected times: {len(times[0])} → {len(times[1])}", target)
        if old_time[0] != new_time[0]:
            add(f"Time bounds not compared: {name} calendars differ.")
        elif old_time != new_time:
            add(f"{name} · reported time bounds: {old_time[1]} / now {new_time[1]}", target)

    if _usable_plan(before) and _usable_plan(after):
        old_products, new_products = (
            {product_key(item): (item.get("fields"), product_path(plan, item))
             for item in plan.get("products", ())} for plan in (old_plan, new_plan))
        for key in sorted(old_products.keys() | new_products.keys()):
            if key not in old_products:
                add(f"New planned product: {key}", ("product", key))
            elif key not in new_products:
                add(f"No longer planned: {key}")
            elif old_products[key] != new_products[key]:
                add(f"Product fields or destination changed: {key}", ("product", key))
    elif old_plan.get("products") or new_plan.get("products"):
        add("Products not comparable: one report did not establish a complete plan.")
    return rows or [("No changes in the compared report facts.", None)]
