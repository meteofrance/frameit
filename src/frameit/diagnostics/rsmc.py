"""Pinned La Réunion archive profile and exact-time local comparison."""

import csv
import hashlib
import os
from dataclasses import dataclass, replace
from datetime import datetime
from math import floor, isfinite
from pathlib import Path

from frameit.diagnostics.best_track import KNOT_M_S, QUADRANTS, THRESHOLDS
from frameit.diagnostics.catalog import AGENCY_PROFILE, AGENCY_PROFILE_VERSION
from frameit.diagnostics.contracts import diagnostic_error

NM_M = 1852
RADIUS_COLUMNS = tuple(
    f"extension_{threshold}kt_{quadrant}" for threshold in THRESHOLDS for quadrant in QUADRANTS
)
COLUMNS = (
    "idswi",
    "nom_cyc",
    "dat",
    "typa",
    "lat",
    "lon",
    "precision",
    "t",
    "ci",
    "ventmax",
    "rafale",
    "pression",
    "rayon_ventmax",
    *RADIUS_COLUMNS,
)
INTENSITY = ("ventmax", "rafale", "pression", "rayon_ventmax", *RADIUS_COLUMNS)
OBSERVED_ONLY = ("nom_cyc", "typa", "precision", "t", "ci")
COMPARISON_COLUMNS = (
    "idswi",
    "dat",
    "match_status",
    "model_lat",
    "model_lon",
    "observed_lat",
    "observed_lon",
    "track_separation_km",
    "position_independence",
    "rmw_methods",
    *(f"observed_{key}" for key in OBSERVED_ONLY),
    *(
        f"{part}_{key}"
        for key in INTENSITY
        for part in ("model", "observed", "difference", "eligible", "reason")
    ),
)
SYNOPTIC = {"00", "06", "12", "18"}


@dataclass(frozen=True)
class Reference:
    idswi: str
    name: str | None
    rows: dict
    facts: dict


def synoptic_date(time):
    date, clock = time.split("T")
    seconds, _, fraction = clock.partition(".")
    if seconds[:2] in SYNOPTIC and seconds[2:] == ":00:00" and not fraction.strip("0"):
        return f"{date} {seconds}"
    return None


def _iso_date(value):
    date = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    if (
        date.strftime("%Y-%m-%d %H:%M:%S") != value
        or f"{date.hour:02}" not in SYNOPTIC
        or (date.minute or date.second)
    ):
        raise ValueError(f"Not an exact synoptic UTC archive timestamp: {value!r}")
    return date.isoformat() + ".000000000"


def _observed_number(row, key):
    raw = row[key].strip()
    if raw in {"", "NA", "NaN"}:
        return None
    number = float(raw)
    if not isfinite(number) or key not in {"lat", "lon"} and number < 0:
        raise ValueError(f"Invalid observed {key}: {raw!r}")
    if key == "lat" and abs(number) > 90:
        raise ValueError(f"Invalid observed latitude: {raw!r}")
    return number


def read_reference(path, *, idswi, times):
    """Retain only relevant selected rows from the exact input bytes hashed."""
    lo, hi = min(times), max(times)
    path = Path(path)
    digest = hashlib.sha256()
    dates, labels, rows = set(), set(), {}
    try:
        with path.open("rb") as source:
            before = os.fstat(source.fileno())

            def lines():
                for n, line in enumerate(source):
                    digest.update(line)
                    yield line.decode("utf-8-sig" if n == 0 else "utf-8")

            reader = csv.DictReader(lines(), delimiter=";", strict=True)
            header = reader.fieldnames
            if header is None or len(header) != len(set(header)) or not set(COLUMNS) <= set(header):
                raise ValueError("Reference CSV must contain the 29 pinned RSMC columns")
            for row in reader:
                if row.get("idswi") != idswi:
                    continue
                if None in row or any(row[key] is None for key in COLUMNS):
                    raise ValueError(f"Malformed selected reference row at line {reader.line_num}")
                date = _iso_date(row["dat"])
                if date in dates:
                    raise ValueError(f"Duplicate selected reference time: {row['dat']}")
                dates.add(date)
                if name := row["nom_cyc"].strip():
                    labels.add(name)
                if lo <= date <= hi:
                    for key in ("lat", "lon", "precision", "t", "ci", *INTENSITY):
                        row[key] = _observed_number(row, key)
                    rows[date] = {key: row[key] for key in COLUMNS}
            after = path.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("Reference file changed while it was read")
        if not dates:
            raise ValueError(f"Selected reference idswi {idswi!r} has no records")
    except (OSError, ValueError, csv.Error) as exc:
        raise diagnostic_error(
            "E2005",
            "diagnostics.best_track.reference",
            str(exc),
            observed={"file": str(path), "idswi": idswi},
            repair="Use a local RSMC La Réunion archive CSV and its exact storm identifier.",
        ) from exc
    return Reference(
        idswi,
        next(iter(labels)) if len(labels) == 1 else None,
        rows,
        {
            "file": str(path),
            "sha256": digest.hexdigest(),
            "size_bytes": before.st_size,
            "idswi": idswi,
            "declared_profile": AGENCY_PROFILE,
            "profile_version": AGENCY_PROFILE_VERSION,
            "matched_time_policy": "exact UTC",
            "track_distance_earth_model": "WGS84",
            "selected_rows_in_range": len(rows),
        },
    )


def _metrics(result):
    return dict(
        zip(
            INTENSITY,
            (
                (result.maximum_wind, KNOT_M_S),
                (result.gust, KNOT_M_S),
                (result.central_pressure, 100),
                (result.rmw, NM_M),
                *((metric, NM_M) for metric in result.wind_radii),
            ),
            strict=True,
        )
    )


def _radius_rounded(metric):
    value = metric.qualified_value
    if value == 0 and "threshold_not_reached" in metric.reasons:
        return 0
    if value is None or value < NM_M / 2:
        return None
    return floor(value / NM_M + 0.5)


def flag_projection_resolution(result):
    def flag(metric):
        value = metric.qualified_value
        return (
            replace(metric, reasons=(*metric.reasons, "below_export_resolution"))
            if (value is not None and 0 < value < NM_M / 2)
            else metric
        )

    return replace(result, rmw=flag(result.rmw), wind_radii=tuple(map(flag, result.wind_radii)))


def _longitude(value):
    return value if -180 <= value < 180 else (value + 180) % 360 - 180


def project_row(result, *, reference):
    date = synoptic_date(result.centre.time)
    if date is None:
        return None
    row = dict.fromkeys(COLUMNS)
    observed = reference.rows.get(result.centre.time, {}) if reference is not None else {}
    row.update(dat=date, lat=result.centre.latitude, lon=_longitude(result.centre.longitude))
    if reference is not None:
        row.update(idswi=reference.idswi, nom_cyc=observed.get("nom_cyc") or reference.name)
    for key, (metric, scale) in _metrics(result).items():
        value = metric.qualified_value
        if key == "rayon_ventmax" or key in RADIUS_COLUMNS:
            row[key] = _radius_rounded(metric)
        elif value is not None and isfinite(value) and value >= 0:
            row[key] = floor(value / scale + 0.5)
    return row


def comparison_row(result, *, reference, time=None, position_independence="not_assessed"):
    from pyproj import Geod

    stamp = result.centre.time if result is not None else time
    observed = reference.rows.get(stamp)
    observed_fields = observed or {}
    model_lat, model_lon = (
        (result.centre.latitude, _longitude(result.centre.longitude))
        if result is not None
        else (None, None)
    )
    lat, lon = (observed_fields.get(k) for k in ("lat", "lon"))
    distance = None
    if None not in (lat, lon, model_lat, model_lon):
        _, _, metres = Geod(ellps="WGS84").inv(model_lon, model_lat, lon, lat)
        distance = metres / 1000
    row = {
        "idswi": reference.idswi,
        "dat": synoptic_date(stamp),
        "match_status": (
            "matched"
            if result is not None and observed is not None
            else "model_only"
            if result is not None
            else "observation_only"
        ),
        "model_lat": model_lat,
        "model_lon": model_lon,
        "observed_lat": lat,
        "observed_lon": lon,
        "track_separation_km": distance,
        "position_independence": position_independence,
        "rmw_methods": "model annular mean; observed agency analysis",
        **{f"observed_{key}": observed_fields.get(key) for key in OBSERVED_ONLY},
    }
    metrics = _metrics(result) if result is not None else {}
    for key in INTENSITY:
        observed_value = observed_fields.get(key)
        metric, scale = metrics.get(key, (None, 1))
        value = metric.qualified_value if metric is not None else None
        model = value / scale if value is not None else None
        eligible = model is not None and observed_value is not None
        reasons = list(metric.reasons) if metric is not None else ["no_model_sample"]
        if metric is not None and metric.comparability != "qualified":
            reasons.append(metric.comparability)
        if observed_value is None:
            reasons.append("no_observed_value")
        row.update(
            {
                f"model_{key}": model,
                f"observed_{key}": observed_value,
                f"difference_{key}": model - observed_value if eligible else None,
                f"eligible_{key}": int(eligible),
                f"reason_{key}": "|".join(dict.fromkeys(reasons)),
            }
        )
    return row
