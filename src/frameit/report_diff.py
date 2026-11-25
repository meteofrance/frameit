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


def source_identity(source):
    return tuple(source.get(key) for key in ("model", "format", "physical_type", "profile"))


def finding_key(level, item):
    if level == "Warning":
        return level, item
    # Authored line marks and the order of context entries are not diagnostic identity.
    detail = {key: item[key] for key in ("code", "path", "message", "expected", "observed")
              if key in item}
    conditions = tuple(sorted(item.get("prerequisites", ())))
    contexts = tuple(sorted(json.dumps(context, sort_keys=True)
                            for context in item.get("contexts", ())))
    return level, json.dumps(detail, sort_keys=True), conditions, contexts


def _findings(report):
    items = [("Error", item) for item in report["errors"]]
    items.extend(("Warning", item) for item in report["warnings"])
    items.extend(("Blocked", item) for item in report["deferred_checks"]
                 if item["status"] == "blocked")
    return {finding_key(level, item): (level, item) for level, item in items}


def _context_label(item):
    labels = {}
    for context in item.get("contexts", ()):
        for key in ("file", "files", "field", "field_id", "source", "group", "grid_id"):
            value = context.get(key)
            values = value if isinstance(value, list) else [value]
            for entry in values:
                if isinstance(entry, str) and entry:
                    labels.setdefault(entry, f"{key}: {entry}")
    if not labels:
        return ""
    parts = list(labels.values())
    return " · " + "; ".join(parts[:4]) + (f" (+{len(parts) - 4} more)" if len(parts) > 4 else "")


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
    return f"{identity} {item['path']} · {message}{_context_label(item)}"


def _schema_only(report):
    return any(check["status"] == "schema-only" for check in report["deferred_checks"])


def _usable_plan(report):
    return report["status"] == "ok" and not _schema_only(report) and not any(
        item["status"] == "blocked" for item in report["deferred_checks"])


def _time_extent(source):
    times = source["selected_times"]
    first, last = times[0], times[-1]
    calendars = {time["calendar"] for time in times if isinstance(time, dict)}
    if not calendars:
        records = source.get("records") or source.get("record_inventory", ())
        calendars = {record["calendar"] for record in records if record.get("calendar")}
    labels = [time["label"] if isinstance(time, dict) else time for time in (first, last)]
    return tuple(sorted(calendars)), " → ".join(labels)


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

    old_plan, new_plan = (report["data"]["plan"] for report in (before, after))
    comparable_plan = _usable_plan(before) and _usable_plan(after)
    left, right = (report["data"]["configuration"] for report in (before, after))
    if left is None or right is None:
        add("Effective settings not comparable: one report did not establish a configuration.")
    else:
        for key in ("products", "region"):
            if left.get(key) != right.get(key):
                add(f"Effective setting changed: {key}", ("setting", key))
        old_output, new_output = (view.get("output", {}) for view in (left, right))
        for key in ("directory", "format", "overwrite"):
            if old_output.get(key) != new_output.get(key):
                path = f"output.{key}"
                add(f"Effective setting changed: {path}", ("setting", path))
        resolved = {"output.writer": (old_output.get("writer"), new_output.get("writer")),
                    "resources": (left.get("resources"), right.get("resources"))}
        if (_usable_plan(before) == _usable_plan(after)
                and ("execution_resources" in old_plan) == ("execution_resources" in new_plan)):
            for key, (old, new) in resolved.items():
                if old != new:
                    add(f"Effective setting changed: {key}", ("setting", key))
        elif any(old != new for old, new in resolved.values()):
            add("Writer and resource details not compared: plan scopes differ.")
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

    old_sources, new_sources = (plan.get("sources", {}) for plan in (old_plan, new_plan))
    for name in sorted(old_sources.keys() | new_sources.keys()):
        left, right = old_sources.get(name, {}), new_sources.get(name, {})
        times = left.get("selected_times"), right.get("selected_times")
        if (not all(times) or not left.get("model") or not left.get("format")
                or source_identity(left) != source_identity(right)
                or left.get("files") is None or right.get("files") is None):
            add(f"Selected coverage not comparable: {name}")
            continue
        target = ("source", name)
        if len(left["files"]) != len(right["files"]):
            add(f"{name} · selected files: {len(left['files'])} → {len(right['files'])}", target)
        (old_calendars, old_time), (new_calendars, new_time) = map(_time_extent, (left, right))
        if len(times[0]) != len(times[1]):
            add(f"{name} · selected times: {len(times[0])} → {len(times[1])}", target)
        if old_calendars != new_calendars:
            recorded = [" / ".join(cals) or "Not reported"
                        for cals in (old_calendars, new_calendars)]
            add(f"Time bounds not compared: {name} calendars ({' → '.join(recorded)}).", target)
        elif len(old_calendars) > 1:
            add(f"Time bounds not compared: {name} reports multiple calendars.", target)
        elif old_time != new_time:
            calendar = f" ({old_calendars[0]})" if old_calendars else ""
            add(f"{name} · reported time bounds{calendar}: {old_time} / now {new_time}", target)

    if comparable_plan:
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
