"""Experimental native-grid adaptation of Marchok (2021), ALL_NO_THICK.

Reference: doi:10.1175/JAMC-D-20-0175.1. Source inspected at NOAA-EMC/TC_tracker
2aadeb97bef5bc1885631ff83ebb305ddcaca9eb (TC_tracker.v1.3.0), gettrk_main_gfs.f
(find_maxmin, get_wind_circulation, fixcenter), and gettrk_modules.f.
Native ellipsoidal derivatives, geodesic search grids and strict support rules
are explicit departures; full reference-executable/real-case qualification is open.
"""

from dataclasses import dataclass

import numpy as np

from .pressure_centroid import GEOD, LocalGridIndex, geodesic_circle
from .pressure_centroid_grid import StructuredGrid

REFERENCE_REVISION = "2aadeb97bef5bc1885631ff83ebb305ddcaca9eb"
PARAMETERS = ("mslp", "rv850", "rv700", "gph850", "gph700",
              "circulation850", "circulation700", "circulation_surface", "rv_surface")
PARAMETER_FLAGS = ("accepted insufficient_support flat_objective search_boundary "
                   "distance_rejected nonconverged")
QUALITY_FLAGS = ("accepted insufficient_parameters required_fix_missing pressure_gradient_failed "
                 "circulation_failed separation_failed translation_failed sampling_support_failed "
                 "steering_support_failed hemisphere_changed")


@dataclass(frozen=True)
class VortexOptions:
    analysis_step_km: float = 25.
    refinement_km: float = 2.5
    max_iterations: int = 20
    minimum_support: float = .8
    minimum_samples: int = 16
    minimum_parameters: int = 2
    pressure_rise_pa: float = 50.
    vt850_min_m_s: float = 1.5
    max_separation_km: float = 425.
    max_speed_m_s: float = 60 * .5144444444444445
    speed_check_interval_hours: float = 6.

    def __post_init__(self):
        for name, value in vars(self).items():
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not np.isfinite(value) or value <= 0):
                raise ValueError(f"multifield_vortex.{name} must be finite and positive")
        for name in ("max_iterations", "minimum_samples", "minimum_parameters"):
            if not isinstance(getattr(self, name), int):
                raise ValueError(f"multifield_vortex.{name} must be an integer")
        if self.minimum_support > 1 or self.minimum_parameters > len(PARAMETERS):
            raise ValueError("Invalid multifield_vortex support/parameter count")
        if self.refinement_km > self.analysis_step_km:
            raise ValueError("multifield_vortex.refinement_km must not exceed analysis_step_km")


def pressure_interpolate(pressure_pa, values, targets_pa=(85000., 70000., 50000.)):
    """Interpolate adjacent physical levels linearly in log(p), never extrapolate.

    An incomplete pressure coordinate invalidates that column, rather than
    sorting across a missing intermediate level. Missing bracket values remain
    missing; exact endpoints need only the nonzero-weight value.
    """
    p = np.asarray(pressure_pa, float)
    if p.ndim != 3 or p.shape[0] < 2:
        raise ValueError("multifield_vortex requires at least two native pressure levels")
    if np.any(np.isfinite(p) & (p <= 0)):
        raise ValueError("multifield_vortex absolute pressure must be positive")
    finite = np.isfinite(p).all(axis=0)
    dp = np.diff(p, axis=0)
    if np.any(finite & ~(np.all(dp > 0, axis=0) | np.all(dp < 0, axis=0))):
        raise ValueError("multifield_vortex native pressure columns must be strictly monotone")
    order = np.argsort(p, axis=0)
    ps = np.take_along_axis(p, order, axis=0)
    output = {name: [] for name in values}

    def get(a, indices):
        return np.take_along_axis(a, indices[None], axis=0)[0]

    for target in targets_pa:
        upper = np.clip(np.sum(ps < target, axis=0), 1, p.shape[0] - 1)
        lower = upper - 1
        a, b = get(ps, lower), get(ps, upper)
        valid = finite & (target >= ps[0]) & (target <= ps[-1])
        fraction = np.log(target / a) / np.log(np.where(b > a, b / a, np.nan))
        for name, data in values.items():
            if np.shape(data) != p.shape:
                raise ValueError(f"{name}: native pressure/value dimensions do not match")
            sorted_data = np.take_along_axis(data, order, axis=0)
            lo, hi = get(sorted_data, lower), get(sorted_data, upper)
            value = np.where(fraction == 0, lo, np.where(fraction == 1, hi,
                             lo * (1 - fraction) + hi * fraction))
            output[name].append(np.where(valid, value, np.nan))
    return {name: np.asarray(data) for name, data in output.items()}


def relative_vorticity(u, v, lon, lat):
    """Normal curl of physical east/north winds on the WGS84 ellipsoid.

    zeta = [M dv/dlambda - d(N cos(phi) u)/dphi] / (M N cos(phi)).
    Computational-index derivatives are transformed through the geographic
    Jacobian; numpy's centred/one-sided second-order differences are used.
    The outermost nodes are excluded from centre fixing. Masks propagate.
    """
    longitude = np.unwrap(np.unwrap(np.deg2rad(lon), axis=1), axis=0)
    phi = np.deg2rad(lat)
    if min(phi.shape) < 3:
        raise ValueError("Relative vorticity requires at least three points per axis")
    lj, li = np.gradient(longitude, edge_order=2)
    pj, pi = np.gradient(phi, edge_order=2)
    determinant = li * pj - lj * pi
    if np.any(np.abs(determinant) < 1e-16):
        raise ValueError("Degenerate geographic Jacobian for relative vorticity")
    a, eccentricity2 = 6378137., 6.6943799901413165e-3
    denominator = 1 - eccentricity2 * np.sin(phi)**2
    n = a / np.sqrt(denominator)
    m = a * (1 - eccentricity2) / denominator**1.5
    vj, vi = np.gradient(np.asarray(v, float), edge_order=2)
    qj, qi = np.gradient(n * np.cos(phi) * np.asarray(u, float), edge_order=2)
    result = (m * (vi * pj - vj * pi) - (li * qj - lj * qi)) / (
        determinant * m * n * np.cos(phi))
    result[[0, -1], :] = np.nan
    result[:, [0, -1]] = np.nan
    return result


def offset(center, east_m, north_m):
    east, north = np.broadcast_arrays(east_m, north_m)
    lon, lat, _ = GEOD.fwd(np.full(east.shape, center[0]), np.full(east.shape, center[1]),
                           np.degrees(np.arctan2(east, north)), np.hypot(east, north))
    return np.column_stack((np.ravel(lon), np.ravel(lat)))


class VortexGrid:
    def __init__(self, lon, lat, resolution_m, options):
        if isinstance(resolution_m, bool) or not np.isfinite(resolution_m) or resolution_m <= 0:
            raise ValueError("multifield_vortex requires resolved positive grid spacing in metres")
        self.lon, self.lat = np.asarray(lon, float), np.asarray(lat, float)
        self.geometry = StructuredGrid(lon, lat, compute_area=False)
        self.index = LocalGridIndex(lon, lat)
        self.options = options
        self.footprint = self.geometry.interpolator(np.ones(self.lon.shape))
        degrees = resolution_m / 111194.9
        self.efolding_km = 60. if degrees < .1 else (75. if degrees < 1.26 else 150.)
        self.influence_km = 150. if degrees < 1.26 else 300.
        self.search_km = (150. if degrees < .1 else 200. if degrees < .4 else
                          300. if degrees < 1.26 else 350.)

    def disk_supported(self, center, radius_km):
        if not np.isfinite(self.footprint(*center)):
            return False
        x, y = geodesic_circle(center, radius_km * 1000, np.arange(0., 360., 7.5))
        return bool(np.isfinite(self.footprint(x, y)).all())

    def barnes(self, center, data, efolding_km=None, influence_km=None):
        re = self.efolding_km if efolding_km is None else efolding_km
        ri = self.influence_km if influence_km is None else influence_km
        if not self.disk_supported(center, ri):
            return np.nan
        ids, _, distance = self.index.disk(center, ri * 1000)
        values = np.asarray(data).ravel()[ids]
        weights = np.exp(-(distance / (re * 1000))**2)
        good = np.isfinite(values)
        if (good.sum() < self.options.minimum_samples or weights[good].sum() <
                self.options.minimum_support * weights.sum()):
            return np.nan
        return float(np.sum(weights[good] * values[good]) / weights[good].sum())

    def tangential(self, center, u, v):
        _, back, distance = GEOD.inv(np.full(self.lon.shape, center[0]),
                                     np.full(self.lat.shape, center[1]), self.lon, self.lat)
        bearing = np.deg2rad((back + 180) % 360)
        sign = 1 if center[1] > 0 else -1
        return sign * (-u * np.cos(bearing) + v * np.sin(bearing)), distance

    def circulation(self, center, sample_u, sample_v):
        if not np.isfinite(self.footprint(*center)):
            return np.nan
        radii = np.arange(35., 216., 30.) * 1000
        bearings = np.arange(7.5, 360., 15.)
        rr, aa = np.meshgrid(radii, bearings, indexing="ij")
        x, y = geodesic_circle(center, rr, aa)
        u, v = sample_u(x, y), sample_v(x, y)
        # Equal support is mandatory here: summing different arcs would favour
        # candidates on the edge of terrain masks or of the regional domain.
        if not (np.isfinite(u).all() and np.isfinite(v).all()):
            return np.nan
        _, back, _ = GEOD.inv(np.full(x.shape, center[0]), np.full(x.shape, center[1]), x, y)
        theta = np.deg2rad((back + 180) % 360)
        sign = 1 if center[1] > 0 else -1
        return float(np.sum(sign * (-u * np.cos(theta) + v * np.sin(theta)) *
                            (2 * np.pi * rr / 24)))

    def extremum(self, guess, objective, maximize, radius_km):
        """Bounded coarse search, then 3x3 geodesic refinement to declared spacing."""
        step = self.options.analysis_step_km
        axis = np.arange(-radius_km, radius_km + step / 2, step)
        axis = np.unique(np.r_[axis, 0.])
        east, north = np.meshgrid(axis, axis)
        use = np.hypot(east, north) <= radius_km + 1e-8
        points = offset(guess, east[use] * 1000, north[use] * 1000)
        current = np.asarray(guess)
        for iteration in range(self.options.max_iterations):
            scores = np.asarray([objective(tuple(p)) for p in points])
            good = np.isfinite(scores)
            if not good.any():
                return current, 1
            finite = scores[good]
            if iteration == 0 and np.ptp(finite) <= 1e-12 * max(1., np.max(np.abs(finite))):
                return current, 2
            best = np.nanmax(scores) if maximize else np.nanmin(scores)
            tied = np.flatnonzero(good & np.isclose(scores, best, rtol=1e-13, atol=0))
            # Resolve equivalent optima by proximity to the current centre.
            distances = GEOD.inv(np.full(len(tied), current[0]), np.full(len(tied), current[1]),
                                  points[tied, 0], points[tied, 1])[2]
            chosen = points[tied[np.argmin(distances)]]
            move = GEOD.inv(*current, *chosen)[2] / 1000
            current = chosen
            if iteration and move < step * .1:
                if step <= self.options.refinement_km:
                    distance = GEOD.inv(*guess, *current)[2] / 1000
                    return current, 3 if distance >= radius_km - step / 2 else 0
                step = max(self.options.refinement_km, step / 2)
            elif iteration == 0:
                step = max(self.options.refinement_km, step / 2)
            e, n = np.meshgrid([-step, 0., step], [-step, 0., step])
            points = offset(current, e.ravel() * 1000, n.ravel() * 1000)
            distance = GEOD.inv(np.full(len(points), guess[0]), np.full(len(points), guess[1]),
                                points[:, 0], points[:, 1])[2]
            points = points[distance <= radius_km * 1000 + 1e-6]
        return current, 5


def combine_fixes(positions, statuses, guess, history):
    """Regional reference rejection and distance-to-first-mean exponential weights.

    Three prior radial-error standard deviations, growth factor 1.25, and
    bounds 225/485 km follow pinned fixcenter/gettrk_modules. Initial cutoff
    is 300 km. Longitude averaging is unwrapped about the declared guess.
    """
    positions, statuses = np.asarray(positions, float), np.array(statuses, dtype=np.int8)
    statuses[(statuses == 0) & ~np.isfinite(positions).all(axis=1)] = 1
    valid = statuses == 0
    distances = np.full(len(positions), np.nan)
    distances[valid] = GEOD.inv(np.full(valid.sum(), guess[0]), np.full(valid.sum(), guess[1]),
                                positions[valid, 0], positions[valid, 1])[2] / 1000
    limit = 300. if not history else min(485., max(225., 3.75 * np.mean(history[-3:])))
    statuses[valid & (distances > limit)] = 4
    included = statuses == 0
    weights = np.zeros(len(positions))
    historical = distances[np.isfinite(distances) & (distances <= 485.)]
    error_std = float(np.std(historical, ddof=1)) if len(historical) > 1 else .1
    if not included.any():
        return None, statuses, weights, error_std, np.nan, limit
    xy = positions[included].copy()
    xy[:, 0] = guess[0] + (xy[:, 0] - guess[0] + 180) % 360 - 180
    first = xy.mean(axis=0)
    radial = GEOD.inv(np.full(len(xy), first[0]), np.full(len(xy), first[1]),
                       xy[:, 0], xy[:, 1])[2] / 1000
    sigma = max(5., float(np.std(radial, ddof=1))) if len(xy) > 1 else 5.
    w = np.exp(-radial / (3 * sigma))
    w /= w.sum()
    center = np.sum(xy * w[:, None], axis=0)
    center[0] = (center[0] + 180) % 360 - 180
    weights[included] = w
    spread = float(np.mean(GEOD.inv(np.full(len(xy), center[0]), np.full(len(xy), center[1]),
                                    xy[:, 0], xy[:, 1])[2]) / 1000)
    return center, statuses, weights, error_std, spread, limit


def quality_check(grid, fields, center, positions, statuses, options):
    """Conservative native-grid versions of the published pressure/circulation checks."""
    metrics = dict(pressure_rise_pa=np.nan, vt850_mean_m_s=np.nan, separation_km=np.nan)
    if (statuses == 0).sum() < options.minimum_parameters:
        return 1, metrics
    if statuses[0] != 0 or statuses[1] != 0:
        return 2, metrics
    metrics["separation_km"] = GEOD.inv(*positions[0], *positions[1])[2] / 1000
    if metrics["separation_km"] > options.max_separation_km:
        return 5, metrics
    x, y = geodesic_circle(center, 333_000., np.arange(7.5, 360, 15.))
    sample = grid.geometry.interpolator(fields["mslp"])
    ring, core = sample(x, y), sample(*center)
    if not np.isfinite(ring).all() or not np.isfinite(core):
        return 7, metrics
    # At least one quadrant must meet the pressure-rise threshold.
    metrics["pressure_rise_pa"] = float(np.max(ring.reshape(4, 6).mean(axis=1) - core))
    if metrics["pressure_rise_pa"] < options.pressure_rise_pa:
        return 3, metrics
    if not grid.disk_supported(center, 275.):
        return 7, metrics
    tangential, distance = grid.tangential(center, fields["u"][0], fields["v"][0])
    inside = (distance > 1) & (distance <= 275_000)
    good = inside & np.isfinite(tangential)
    if good.sum() < options.minimum_samples or good.sum() < options.minimum_support * inside.sum():
        return 7, metrics
    metrics["vt850_mean_m_s"] = float(tangential[good].mean())
    if metrics["vt850_mean_m_s"] <= options.vt850_min_m_s:
        return 4, metrics
    return 0, metrics


def translation_speed(anchor_time, anchor_center, time, center, interval_hours):
    """Return NaN until the declared QC interval has elapsed; no hourly proxy."""
    elapsed = float((time - anchor_time) / np.timedelta64(1, "s"))
    if elapsed < interval_hours * 3600:
        return np.nan
    return float(GEOD.inv(*anchor_center, *center)[2] / elapsed)
