"""Explicit preceding-hour association of native means, never time interpolation."""

import logging
import re
from pathlib import Path

import numpy as np
import xarray as xr

log = logging.getLogger(__name__)


def align_preceding_hour(inventories, reference, models, track_times=None):
    """Use the reference clock; require the unique mean over (T-1 hour, T]."""
    if (reference not in inventories or models.get(reference) != "AROME"
            or not any(model == "NEMO" for model in models.values())
            or any(model not in {"AROME", "NEMO"} for model in models.values())):
        raise ValueError("preceding_hour requires an AROME reference and NEMO secondary sources")
    available, intervals = {}, {}
    for name, entries in inventories.items():
        available[name] = {time for entry in entries for time in entry["times"]}
        by_end, by_sample, providers = {}, {}, set()
        for entry in entries:
            for field, attrs in entry.get("temporal_fields", {}).items():
                keys = {(field, sample) for sample in entry["times"]}
                if providers & keys:
                    raise ValueError(f"{name}.{field}: overlapping physical-field providers; "
                                     "preceding_hour requires unique native records")
                providers.update(keys)
                methods = re.findall(r"\btime:\s*([a-z_]+)", attrs.get("cell_methods", ""))
                step = attrs.get("GRIB_stepType")
                operation = attrs.get("online_operation")
                if models[name] == "NEMO":
                    if methods != ["mean"] or operation not in {None, "average"} or step not in {None, "avg"}:
                        raise ValueError(f"{name}.{field}: preceding_hour requires an explicit time mean")
                elif (methods not in ([], ["point"]) or step not in {None, "instant"}
                      or operation not in {None, "instant", "once"}
                      or not (methods == ["point"] or step == "instant")):
                    raise ValueError(f"{name}.{field}: reference fields must be explicitly instantaneous")
            if models[name] != "NEMO":
                continue
            if entry.get("source_time_conflict"):
                raise ValueError(f"{name}: source_time is reserved for original sampling coordinates")
            cells = entry.get("time_cells", [])
            if {cell["source_time"] for cell in cells} != set(entry["times"]):
                raise ValueError(f"{name}: preceding_hour requires bounds for every native sample")
            for cell in cells:
                sample, start, end = (cell[key] for key in ("source_time", "start", "end"))
                s, lo, hi = (np.datetime64(value, "ns") for value in (sample, start, end))
                if (np.isnat([s, lo, hi]).any() or hi - lo != np.timedelta64(1, "h")
                        or not lo <= s <= hi):
                    raise ValueError(f"{name}: invalid hourly interval bounds for {sample}")
                if sample in by_sample and by_sample[sample] != (start, end):
                    raise ValueError(f"{name}: conflicting interval bounds for native sample {sample}")
                by_sample[sample] = start, end
                by_end.setdefault(end, set()).add(sample)
        intervals[name] = by_end
    reference_times = available[reference]
    candidates = reference_times if track_times is None else reference_times & track_times
    mappings = {name: [] for name in inventories}
    omitted, selected = [], []
    for target in sorted(candidates):
        pairing, missing = {}, []
        for name in inventories:
            if models[name] == "NEMO":
                samples = intervals[name].get(target, set())
                if len(samples) > 1:
                    raise ValueError(f"{name}: ambiguous preceding-hour interval ending {target}")
                sample = next(iter(samples)) if samples else None
            else:
                sample = target if target in available[name] else None
            if sample is None:
                missing.append(name)
                continue
            record = {"coupling_time": target, "source_time": sample,
                      "offset_seconds": float((np.datetime64(sample) - np.datetime64(target))
                                              / np.timedelta64(1, "s"))}
            if models[name] == "NEMO":
                record.update(interval_start=str(np.datetime64(target, "ns") - np.timedelta64(1, "h")),
                              interval_end=target)
            pairing[name] = record
        if missing:
            omitted.append({"coupling_time": target, "missing_sources": missing})
        else:
            selected.append(target)
            for name, record in pairing.items():
                mappings[name].append(record)
    if omitted:
        log.warning("preceding_hour omits %d pairing(s): %s%s; missing sources and complete "
                    "mapping recorded in time_alignment provenance", len(omitted),
                    ", ".join(item["coupling_time"] for item in omitted[:10]),
                    " ..." if len(omitted) > 10 else "")
    if not selected:
        raise ValueError("No preceding_hour pairings remain; supply matching preceding intervals/track coverage")
    sources = {}
    for name, entries in inventories.items():
        used = {record["source_time"] for record in mappings[name]}
        sources[name] = {"available_count": len(available[name]), "selected_count": len(selected),
                         "skipped_times": sorted(available[name] - used),
                         "missing_times": [item["coupling_time"] for item in omitted
                                           if name in item["missing_sources"]],
                         "skipped_files": [Path(entry["path"]).name for entry in entries
                                           if not set(entry["times"]) & used],
                         "associations": mappings[name]}
    return {"policy": "preceding_hour", "selected_times": selected, "sources": sources,
            "omitted_pairings": omitted, "missing_pairing_policy": "omit_warn",
            "reference_source": reference,
            "track_excluded_times": sorted(reference_times - candidates)}


def associate_preceding_times(tree, associations):
    """Select native samples exactly, preserving their clock beside coupling time."""
    if not isinstance(tree, xr.Dataset):
        return {key: associate_preceding_times(value, associations) for key, value in tree.items()}
    if "source_time" in tree:
        raise ValueError("source_time is reserved for original sampling coordinates")
    native = np.asarray([record["source_time"] for record in associations], dtype="datetime64[ns]")
    target = np.asarray([record["coupling_time"] for record in associations], dtype="datetime64[ns]")
    result = tree.sel(time=native)
    original = result.time.copy(deep=False)
    source_attrs = dict(original.attrs)
    if "axis" in source_attrs:
        source_attrs["source_axis"] = source_attrs.pop("axis")
    target_attrs = dict(original.attrs, long_name=(
        "coupling time: reference valid time and end of preceding source mean"))
    result = result.assign_coords(source_time=xr.Variable("time", original.data, attrs=source_attrs),
                                  time=xr.Variable("time", target, attrs=target_attrs))
    result.source_time.encoding = dict(original.encoding)
    result.time.encoding = dict(original.encoding)
    result.attrs = dict(result.attrs, temporal_association="preceding_hour",
                        temporal_association_description=(
                            "native mean unchanged; time labels interval end on reference clock; "
                            "source_time retains original sampling label; no temporal interpolation"))
    return result
