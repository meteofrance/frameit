"""Stream ordinary-reader results into a private diagnostic attempt."""

import csv
import json
from collections import Counter
from contextlib import ExitStack
from itertools import chain

import numpy as np
from netCDF4 import Dataset

from frameit.core.run_context import file_sha256
from frameit.core.run_state import write_run_record
from frameit.diagnostics import rsmc
from frameit.diagnostics.best_track import QUADRANTS, THRESHOLD_M_S, THRESHOLDS, reduce_time
from frameit.diagnostics.catalog import AGENCY_PROFILE, AGENCY_PROFILE_VERSION, BEST_TRACK
from frameit.diagnostics.contracts import diagnostic_error
from frameit.diagnostics.geometry import METHOD
from frameit.diagnostics.runner import _preserve_scope
from frameit.diagnostics.sources import open_source
from frameit.utils.atomic import atomic_output
from frameit.utils.diagnostics import format_message, tag_error

METRICS = {
    "maximum_wind": ("m s-1", "maximum physical 10 m wind in the declared core disc"),
    "central_pressure": ("Pa", "minimum mean sea-level pressure in the central search disc"),
    "gust": ("m s-1", "maximum qualified producer gust in the maximum-wind disc"),
    "rmw": ("m", "midpoint of the peak physical-area-weighted mean-speed annulus"),
    "wind_radius": ("m", "maximum radial extent meeting the wind threshold in the quadrant"),
}
SUPPORT = (
    "not_evaluated",
    "complete",
    "crop_truncated",
    "model_domain_truncated",
    "missing_field_support",
    "unknown_geometry",
    "search_limit_reached",
)
COMPARABILITY = (
    "unavailable",
    "qualified",
    "model_native_proxy",
    "temporal_semantics_unverified",
    "physical_definition_unverified",
)
REASONS = (
    "missing_input_sample",
    "gust_not_selected",
    "temporal_semantics_unverified",
    "unknown_geometry",
    "crop_truncated",
    "model_domain_truncated",
    "missing_field_support",
    "search_limit_reached",
    "no_valid_data",
    "stronger_wind_outside_core",
    "threshold_not_reached",
    "cell_area_unverified",
    "empty_annulus",
    "ambiguous_peak",
    "peak_at_radial_boundary",
    "insufficient_azimuthal_sampling",
    "multiple_local_peaks",
    "below_export_resolution",
    "physical_definition_unverified",
)
BOUNDS = ("none", "lower", "upper")
AVAILABILITY = ("unavailable", "available", "ambiguous")
UNSUPPORTED = {
    "typa": "agency_classification_not_implemented",
    "precision": "position_uncertainty_not_implemented",
    "t": "dvorak_not_implemented",
    "ci": "dvorak_not_implemented",
}


def _time_ticks(centres):
    times = np.asarray([c.time for c in centres], dtype="datetime64[ns]")
    for fmt, name in (
        ("s", "seconds"),
        ("ms", "milliseconds"),
        ("us", "microseconds"),
        ("ns", "nanoseconds"),
    ):
        ticks = times.astype(f"datetime64[{fmt}]")
        if np.array_equal(ticks, times):
            return ticks.astype(np.int64), f"{name} since 1970-01-01 00:00:00"


def _new_table(ds, plan, attempt):
    ds.setncatts(
        {
            "Conventions": "CF-1.8",
            "title": "Model diagnostics for comparison with RSMC data; not an official track",
            "diagnostic": BEST_TRACK.key,
            "method_version": BEST_TRACK.version,
            "method_maturity": BEST_TRACK.maturity,
            "coverage_method": METHOD,
            "rmw_method": "annular_mean_speed_v1 (model estimate, not agency analysis)",
            "parent_attempt_id": plan.parent.attempt_id,
            "diagnostic_attempt_id": attempt.name,
            "agency_profile": AGENCY_PROFILE,
            "agency_profile_version": AGENCY_PROFILE_VERSION,
            "centre_origin": plan.parent.centre_origin,
            "time_interpretation": "UTC",
            "search_settings": json.dumps(plan.request["search"], sort_keys=True),
            "rmw_settings": json.dumps(plan.request["rmw"], sort_keys=True),
            "quality_record": "../diagnostics-provenance.yaml",
            "agency_only_fields": json.dumps(UNSUPPORTED, sort_keys=True),
            "comparison_identity": (
                "explicit local reference" if plan.reference else "reference_not_selected"
            ),
        }
    )
    ds.createDimension("time", None)
    ds.createDimension("threshold", 4)
    ds.createDimension("quadrant", 4)
    time = ds.createVariable("time", "i8", ("time",))
    ticks, units = _time_ticks(plan.parent.centres)
    time.setncatts({"units": units, "calendar": plan.parent.calendar, "standard_name": "time"})
    threshold = ds.createVariable("threshold", "f8", ("threshold",))
    threshold.setncatts({"units": "m s-1", "long_name": "wind speed threshold, inclusive"})
    threshold[:] = THRESHOLD_M_S
    knots = ds.createVariable("threshold_knots", "i2", ("threshold",))
    knots.units = "knot"
    knots[:] = THRESHOLDS
    quadrants = ds.createVariable("quadrant", "u1", ("quadrant",))
    quadrants.setncatts(
        {
            "flag_values": np.arange(4, dtype=np.uint8),
            "flag_meanings": " ".join(QUADRANTS),
            "long_name": "clockwise bearing sectors from geographic north",
        }
    )
    quadrants[:] = range(4)
    for name, unit in (("latitude", "degrees_north"), ("longitude", "degrees_east")):
        var = ds.createVariable(name, "f8", ("time",))
        var.setncatts({"units": unit, "standard_name": name})
    intervals = ds.createVariable("rmw_peak_candidate_intervals", str, ("time",))
    intervals.long_name = "JSON pairs of lower and upper bin edges in metres"
    for name, (units, label) in METRICS.items():
        dims = ("time", "threshold", "quadrant") if name == "wind_radius" else ("time",)
        for suffix, detail in (
            ("", label),
            ("_native_proxy", "model native statistic: " + label),
            ("_observed", "restricted-domain estimate before qualification: " + label),
            ("_bound", "observed bound under insufficient support: " + label),
        ):
            if suffix == "_native_proxy" and name not in {"maximum_wind", "rmw", "wind_radius"}:
                continue
            var = ds.createVariable(name + suffix, "f8", dims, fill_value=np.nan)
            var.setncatts({"units": units, "long_name": detail})
        for suffix, meanings in (
            ("_support", SUPPORT),
            ("_comparability", COMPARABILITY),
            ("_bound_kind", BOUNDS),
            ("_availability", AVAILABILITY),
        ):
            var = ds.createVariable(name + suffix, "u1", dims)
            var.setncatts(
                {
                    "flag_values": np.arange(len(meanings), dtype=np.uint8),
                    "flag_meanings": " ".join(meanings),
                }
            )
        flags = ds.createVariable(name + "_reasons", "i4", dims)
        flags.setncatts(
            {
                "flag_masks": np.asarray([1 << i for i in range(len(REASONS))], dtype="i4"),
                "flag_meanings": " ".join(REASONS),
            }
        )
        ds.createVariable(name + "_valid_samples", "i8", dims)
        if name in {"maximum_wind", "central_pressure", "gust"}:
            ds.createVariable(name + "_ties", "i8", dims)
            for suffix, unit in (
                ("_latitude", "degrees_north"),
                ("_longitude", "degrees_east"),
                ("_offset", "m"),
            ):
                ds.createVariable(name + suffix, "f8", dims, fill_value=np.nan).units = unit
    return ticks


def _metric_values(metric):
    return {
        "": metric.qualified_value,
        "_native_proxy": metric.value if metric.comparability == "model_native_proxy" else None,
        "_observed": metric.observed,
        "_bound": metric.bound,
        "_valid_samples": metric.valid_samples,
        "_ties": metric.ties,
        "_latitude": metric.location[0] if metric.location is not None else None,
        "_longitude": metric.location[1] if metric.location is not None else None,
        "_offset": metric.offset_m,
        "_availability": (
            1 if metric.value is not None else 2 if "ambiguous_peak" in metric.reasons else 0
        ),
        "_support": SUPPORT.index(metric.support),
        "_comparability": COMPARABILITY.index(metric.comparability),
        "_bound_kind": BOUNDS.index(metric.bound_kind),
        "_reasons": sum(1 << REASONS.index(reason) for reason in set(metric.reasons)),
    }


def _row_metrics(row):
    return {
        "wind_radius": row.wind_radii,
        **{name: (getattr(row, name),) for name in METRICS if name != "wind_radius"},
    }


def _write_row(ds, index, tick, row):
    ds["time"][index] = tick
    ds["latitude"][index] = row.centre.latitude
    ds["longitude"][index] = row.centre.longitude
    ds["rmw_peak_candidate_intervals"][index] = json.dumps(row.rmw.candidates)
    for name, entries in _row_metrics(row).items():
        values = list(map(_metric_values, entries))
        for prop in values[0]:
            if (target := name + prop) not in ds.variables:
                continue
            data = [m[prop] if m[prop] is not None else np.nan for m in values]
            ds[target][index] = np.asarray(data).reshape(4, 4) if name == "wind_radius" else data[0]


def _check_availability(row, plan):
    if plan.request["on_unavailable"] != "error":
        return
    missing = [
        (name, i, metric.reasons)
        for name, entries in _row_metrics(row).items()
        if name != "gust" or "gust" in plan.request["fields"]
        for i, metric in enumerate(entries)
        if metric.value is None
    ]
    if missing:
        raise diagnostic_error(
            "E2004",
            "diagnostics.best_track.on_unavailable",
            f"Requested quantities unavailable at {row.centre.time}",
            observed=missing,
            expected="all requested metric families available",
            repair="Check the spatial and temporal evidence, or use on_unavailable: report.",
        )


def publish_results(attempt, plan, results, *, reference=None, recheck=lambda: None):
    product = attempt / "best_track"
    names = ["model_best_track.nc", "rsmc_comparison.csv"]
    if reference is not None:
        names.append("comparison.csv")
    destinations = [product / name for name in names]
    counts, limitations = Counter(), Counter()
    positions = (
        "prescribed_not_independent"
        if plan.parent.centre_origin == "prescribed"
        else "fixed_not_forecast"
        if plan.parent.centre_origin == "fixed"
        else "independence_not_established"
    )
    matched, model_only = [], []
    with ExitStack() as publication:
        paths = [
            publication.enter_context(
                _preserve_scope(
                    atomic_output(path, overwrite=False),
                    f"Finalizing {path.name}",
                )
            )
            for path in destinations
        ]
        with ExitStack() as writers:
            ds = writers.enter_context(
                _preserve_scope(
                    Dataset(paths[0], "w", format="NETCDF4"),
                    "Closing canonical diagnostic NetCDF",
                )
            )
            ticks = _new_table(ds, plan, attempt)
            projection = csv.DictWriter(
                writers.enter_context(paths[1].open("w", encoding="utf-8", newline="")),
                fieldnames=rsmc.COLUMNS,
                delimiter=";",
            )
            projection.writeheader()
            comparison = None
            if reference is not None:
                comparison = csv.DictWriter(
                    writers.enter_context(paths[2].open("w", encoding="utf-8", newline="")),
                    fieldnames=rsmc.COMPARISON_COLUMNS,
                    delimiter=";",
                )
                comparison.writeheader()
            for i, (row, tick) in enumerate(zip(results, ticks, strict=True)):
                row = rsmc.flag_projection_resolution(row)
                _check_availability(row, plan)
                _write_row(ds, i, tick, row)
                counts["canonical_rows"] += 1
                for metric in chain.from_iterable(_row_metrics(row).values()):
                    counts[
                        (
                            "expected_unavailable"
                            if "gust_not_selected" in metric.reasons
                            else "unavailable"
                        )
                        if metric.value is None
                        else metric.comparability
                    ] += 1
                    limitations.update(metric.reasons)
                if fields := rsmc.project_row(row, reference=reference):
                    projection.writerow(fields)
                    counts["synoptic_rows"] += 1
                    if comparison is not None:
                        diff = rsmc.comparison_row(
                            row, reference=reference, position_independence=positions
                        )
                        comparison.writerow(diff)
                        (matched if diff["match_status"] == "matched" else model_only).append(
                            row.centre.time
                        )
            observation_only = []
            if comparison is not None:
                observation_only = sorted(reference.rows.keys() - set(matched))
                for time in observation_only:
                    comparison.writerow(
                        rsmc.comparison_row(
                            None, reference=reference, time=time, position_independence=positions
                        )
                    )
        recheck()
    summary = {
        "counts": dict(counts),
        "quality_reasons": dict(limitations),
        "agency_only_fields": UNSUPPORTED,
        "csv_quality_note": "See paired NetCDF flags",
    }
    if reference is not None:
        summary["reference"] = {
            **reference.facts,
            "matched": matched,
            "model_only": model_only,
            "observation_only": observation_only,
            "position_independence": positions,
        }
    warnings = (
        []
        if counts["synoptic_rows"]
        else [
            format_message(
                "W2002", "no_synoptic_samples: the RSMC projection contains only its header"
            )
        ]
    )
    return (
        [
            {
                "role": role,
                "path": str(path.relative_to(attempt)),
                "size_bytes": path.stat().st_size,
            }
            for role, path in zip(
                ("canonical_best_track", "rsmc_projection", "local_comparison"),
                destinations,
                strict=False,
            )
        ],
        summary,
        warnings,
    )


def execute_plan(attempt, plan, *, scratch):
    try:
        with open_source(plan, scratch=scratch) as provider:
            rows = (reduce_time(centre, provider, plan) for centre in plan.parent.centres)
            products, summary, warnings = publish_results(
                attempt, plan, rows, reference=plan.reference, recheck=provider.recheck
            )
            if provider.zarr_evidence:
                name = "diagnostics-input-objects.yaml"
                write_run_record(
                    attempt / name,
                    {
                        "strategy": "zarr_v3_accessed_object_size_and_mtime",
                        "version": 1,
                        "stores": {
                            path.name: {
                                key: list(stamp) if stamp is not None else None
                                for key, stamp in keys.items()
                            }
                            for path, keys in provider.zarr_evidence.items()
                        },
                    },
                    overwrite=False,
                )
                summary["accessed_storage_record"] = {
                    "path": name,
                    "sha256": file_sha256(attempt / name),
                }
            return products, summary, warnings
    except OSError as exc:
        tag_error(exc, "E1806")
        raise
