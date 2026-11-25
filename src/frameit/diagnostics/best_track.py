"""Native-cell best-track estimators; no interpolation or synthetic qualification."""

from dataclasses import replace

import numpy as np
from pyproj import Geod

from frameit.diagnostics.contracts import DiagnosticResult, Metric
from frameit.diagnostics.geometry import (
    PERIMETER_BYTES,
    certify_disc,
    disc_and_rim,
    orientation,
    tile_geometry,
    view_perimeter,
)

THRESHOLDS = (28, 34, 48, 64)
QUADRANTS = ("ne", "se", "so", "no")
KNOT_M_S = 1852 / 3600
THRESHOLD_M_S = tuple(threshold * 1852 / 3600 for threshold in THRESHOLDS)
SUPPORT_REASONS = ("unknown_geometry", "crop_truncated", "model_domain_truncated",
                   "missing_field_support", "search_limit_reached")


def unavailable(reason, *, comparability="unavailable"):
    return Metric(reasons=(reason,), comparability=comparability)


def _intervals(indices):
    sequences = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
    return [(int(s[0]), int(s[-1])) for s in sequences if s.size]


def annular_peak(means, sectors, width):
    if not np.isfinite(means).all():
        return unavailable("empty_annulus")
    highest = float(np.max(means))
    epsilon = max(1e-10, 1e-12 * float(np.max(np.abs(means))))
    candidates = np.flatnonzero(highest - means <= epsilon)
    peak = int(candidates[0])
    midpoint = (peak + .5) * width
    if len(candidates) > 1:
        return Metric(
            observed=midpoint, support="complete", reasons=("ambiguous_peak",),
            candidates=tuple((a * width, (b + 1) * width) for a, b in _intervals(candidates)),
        )
    if peak in {0, len(means) - 1}:
        return Metric(observed=midpoint, support="complete", reasons=("peak_at_radial_boundary",))
    if np.any(sectors[peak - 1:peak + 2] == 0):
        return Metric(observed=midpoint, support="complete",
                      reasons=("insufficient_azimuthal_sampling",))
    local_peaks = 0
    lo = 0
    while lo < len(means):
        hi = lo
        while hi + 1 < len(means) and abs(means[hi + 1] - means[lo]) <= epsilon:
            hi += 1
        if (lo > 0 and hi < len(means) - 1 and means[lo] - means[lo - 1] > epsilon
                and means[hi] - means[hi + 1] > epsilon):
            local_peaks += 1
        lo = hi + 1
    return Metric(value=midpoint, observed=midpoint, support="complete",
                  reasons=("multiple_local_peaks",) if local_peaks > 1 else ())


class _Extremum:
    def __init__(self, *, minimum=False):
        self.minimum = minimum
        self.value = None
        self.location = self.offset = self.index = None
        self.good = self.gaps = self.ties = 0
        self.rim = False

    def add(self, values, valid, disc, rim, latitude, longitude, radius, start):
        mask = valid & disc
        count = int(np.count_nonzero(mask))
        self.good += count
        self.gaps += int(np.count_nonzero(disc)) - count
        if not count:
            return
        available = values[mask]
        value = float(np.min(available) if self.minimum else np.max(available))
        better = self.value is None or (value < self.value if self.minimum else value > self.value)
        if not better and value != self.value:
            return
        same = mask & (values == value)
        n = int(np.count_nonzero(same))
        rim_tie = bool(np.any(same & rim))
        a, b = map(int, np.unravel_index(np.argmax(same), same.shape))
        index = (a + start[0], b + start[1])
        if better or index < self.index:
            self.location = (float(latitude[a, b]), float(longitude[a, b]))
            self.offset, self.index = float(radius[a, b]), index
        self.value = value
        self.ties = n if better else self.ties + n
        self.rim = rim_tie if better else self.rim or rim_tie

    def result(self, geometry, comparability, *, stronger_outside=False):
        reasons = _reasons(geometry, self.gaps, self.rim, self.good)
        if stronger_outside:
            reasons.append("stronger_wind_outside_core")
        is_bound = self.value is not None and any(reason in SUPPORT_REASONS for reason in reasons)
        return Metric(
            value=self.value if not reasons else None, observed=self.value,
            bound=self.value if is_bound else None,
            bound_kind=("upper" if self.minimum else "lower") if is_bound else "none",
            support=_support(reasons), comparability=comparability, reasons=tuple(reasons),
            location=self.location, offset_m=self.offset, ties=self.ties, valid_samples=self.good,
        )


def _reasons(geometry, missing, rim, samples):
    return ([geometry] if geometry != "complete" else []) + (
        ["missing_field_support"] if missing else []) + (
        ["search_limit_reached"] if rim else []) + (["no_valid_data"] if not samples else [])


def _support(reasons):
    return next((reason for reason in SUPPORT_REASONS if reason in reasons), "complete")


class _WindRadii:
    def __init__(self):
        self.maximum = np.full((4, 4), -np.inf)
        self.touched = np.zeros((4, 4), dtype=bool)
        self.good = np.zeros(4, dtype=np.int64)
        self.gaps = np.zeros(4, dtype=np.int64)

    def add(self, speed, valid, disc, rim, radius, bearing):
        for q in range(4):
            assigned = disc & (radius > 0) & (bearing >= 90 * q) & (bearing < 90 * (q + 1))
            supported = assigned & valid
            self.good[q] += np.count_nonzero(supported)
            self.gaps[q] += np.count_nonzero(assigned & ~valid)
            for i, threshold in enumerate(THRESHOLD_M_S):
                exceed = supported & (speed >= threshold)
                if np.any(exceed):
                    self.maximum[i, q] = max(self.maximum[i, q], np.max(radius[exceed]))
                    self.touched[i, q] |= np.any(exceed & rim)

    def result(self, geometry, comparability):
        entries = []
        for i, q in np.ndindex((4, 4)):
            value = float(self.maximum[i, q])
            observed = value if np.isfinite(value) else None
            reasons = _reasons(geometry, self.gaps[q], self.touched[i, q], self.good[q])
            available = not reasons
            if available and observed is None:
                reasons.append("threshold_not_reached")
            is_bound = not available and observed is not None
            entries.append(Metric(
                value=(0. if observed is None else observed) if available else None,
                observed=observed, bound=observed if is_bound else None,
                bound_kind="lower" if is_bound else "none", support=_support(reasons),
                comparability=comparability, reasons=tuple(reasons), valid_samples=int(self.good[q]),
            ))
        for q in range(4):
            metric = [entries[i * 4 + q].value for i in range(4)]
            if any(a < b for a, b in zip(metric, metric[1:])
                   if a is not None and b is not None):
                raise ArithmeticError("Nested wind-radius thresholds produced out-of-order extents")
        return tuple(entries)


class _Annuli:
    def __init__(self, config):
        self.width = config["bin_width_km"] * 1000
        self.count = round(config["radius_km"] / config["bin_width_km"])
        self.sectors = config["azimuth_sectors"]
        self.sum = np.zeros(self.count, dtype=np.float64)
        self.area = np.zeros_like(self.sum)
        self.occupancy = np.zeros((self.count, self.sectors), dtype=np.int64)
        self.missing = self.good = 0
        self.has_area = False

    def add(self, speed, valid, cell_area, disc, radius, bearing):
        if cell_area is None:
            return
        self.has_area = True
        support = disc & valid & np.isfinite(cell_area) & (cell_area > 0)
        n = int(np.count_nonzero(support))
        self.good += n
        self.missing += int(np.count_nonzero(disc)) - n
        r = radius[support]
        k = np.minimum((r / self.width).astype(np.intp), self.count - 1)
        q = np.minimum((bearing[support] / 360 * self.sectors).astype(np.intp), self.sectors - 1)
        area = cell_area[support]
        np.add.at(self.sum, k, speed[support] * area)
        np.add.at(self.area, k, area)
        directional = r > 0
        np.add.at(self.occupancy, (k[directional], q[directional]), 1)

    def result(self, geometry, comparability):
        reasons = _reasons(geometry, self.missing, False, self.good)
        if not self.has_area:
            reasons.append("cell_area_unverified")
        if reasons:
            return Metric(comparability=comparability, support=_support(reasons),
                          reasons=tuple(reasons), valid_samples=self.good)
        mean = np.divide(self.sum, self.area, where=self.area > 0,
                         out=np.full(self.count, np.nan))
        return replace(annular_peak(mean, self.occupancy, self.width),
                       comparability=comparability, valid_samples=self.good)


def _tiles(shape, side):
    ny, nx = shape
    for y in range(0, ny, side):
        for x in range(0, nx, side):
            ey, ex = min(y + side, ny), min(x + side, nx)
            oy, ox = max(0, y - 1), max(0, x - 1)
            window = (slice(oy, min(ey + 1, ny)), slice(ox, min(ex + 1, nx)))
            interior = (slice(y - oy, ey - oy), slice(x - ox, ex - ox))
            yield (y, x), window, interior


def _group_result(centre, group, view, request, comparability):
    search = request["search"]
    role = group.role
    wind, pressure = role == "wind", role == "pressure"
    core = (search["pressure_radius_km"] if pressure else search["maximum_wind_radius_km"]) * 1000
    radii = search["wind_radii_radius_km"] * 1000 if wind else core
    rmw = request["rmw"]["radius_km"] * 1000
    distances = (core, radii, rmw) if wind else (core,)
    extrema = _Extremum(minimum=pressure)
    extents, annuli = (_WindRadii(), _Annuli(request["rmw"])) if wind else (None, None)
    outside = -np.inf
    grid = group.grid
    geod = Geod(a=grid.earth[0], b=grid.earth[1])
    perimeter = view_perimeter(view, grid.shape)
    budget = 4 * sum(grid.shape) * PERIMETER_BYTES
    coverage = {r: certify_disc(centre, perimeter, geod=geod, radius_m=r,
                               budget_bytes=budget) for r in set(distances)}
    topology = set()
    for start, window, inner in _tiles(grid.shape, group.tile_side):
        lat, lon = view.geography(window)
        info = tile_geometry(centre, (lat, lon), geod=geod)
        y, x = np.indices((lat.shape[0] - 1, lat.shape[1] - 1))
        norm = ((y >= inner[0].start) & (y < inner[0].stop)
                & (x >= inner[1].start) & (x < inner[1].stop))
        sign = orientation(info, norm)
        if sign is not None:
            topology.add(sign)
        if not np.all(info.valid[inner]):
            topology.add(0)
        r = info.radius[inner]
        if not np.any(r <= radii):
            continue
        vals = {k: v[inner] for k, v in view.read_values(window).items()}
        if wind:
            if "speed" in vals:
                values = vals["speed"]
            else:
                values = np.hypot(vals["u"], vals["v"])
        else:
            values = vals[role]
        valid = np.isfinite(values) & ((values > 0) if pressure else (values >= 0))
        disc, rim = disc_and_rim(info.radius, core, inner)
        extrema.add(values, valid, disc, rim, lat[inner], lon[inner], r, start)
        if wind:
            outer, outer_rim = disc_and_rim(info.radius, radii, inner)
            bearing = info.bearing[inner]
            extents.add(values, valid, outer, outer_rim, r, bearing)
            annuli.add(values, valid, vals.get("area"), r <= rmw, r, bearing)
            if np.any(available := outer & ~disc & valid):
                outside = max(outside, np.max(values[available]))
    if len(topology) != 1 or 0 in topology:
        coverage = dict.fromkeys(distances, "unknown_geometry")
    coverage = {r: group.truncated if state == "truncated" else state
                for r, state in coverage.items()}
    metric = extrema.result(
        coverage[core], comparability,
        stronger_outside=bool(wind and extrema.value is not None and outside > extrema.value),
    )
    if not wind:
        return (metric,)
    return metric, annuli.result(coverage[rmw], comparability), extents.result(
        coverage[radii], comparability)


def reduce_time(centre, provider, plan):
    """Read only one time/group at once; all scientific decisions remain in the row."""
    missing = unavailable("missing_input_sample")
    result = {
        "maximum_wind": missing, "central_pressure": missing, "rmw": missing,
        "gust": missing if "gust" in plan.request["fields"] else unavailable("gust_not_selected"),
        "wind_radii": (missing,) * 16,
    }
    for group in provider.samples(centre.time):
        cmp = "qualified"
        if not group.qualified:
            field = group.fields[0]
            if (group.role != "wind" or plan.request["wind_time_policy"] != "native_proxy"
                    or field.statistic == "unverified" or field.averaging_seconds is None):
                why = unavailable("temporal_semantics_unverified",
                                  comparability="temporal_semantics_unverified")
                if group.role == "wind":
                    result.update(maximum_wind=why, rmw=why, wind_radii=(why,) * 16)
                else:
                    result["gust"] = why
                continue
            cmp = "model_native_proxy"
        with provider.open_group(group) as view:
            metrics = _group_result(centre, group, view, plan.request, cmp)
        if group.role == "wind":
            result["maximum_wind"], result["rmw"], result["wind_radii"] = metrics
        else:
            result["central_pressure" if group.role == "pressure" else "gust"], = metrics
    return DiagnosticResult(centre, **result)
