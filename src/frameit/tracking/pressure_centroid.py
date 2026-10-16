"""Nguyen et al. pressure centroid, following compare_batsirai_centers v1.4.1.

Independent numerical implementation choices follow the supplied comparison
script; DOI: 10.1175/MWR-D-14-00044.1. All distances use WGS84. The spherical
index is only a conservative prefilter, never the integration geometry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields

import numpy as np
from pyproj import Geod
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)
GEOD = Geod(ellps="WGS84")
G0 = 9.80665
HEIGHT_M = 2000.0
REFERENCE_RADIUS_M = 500_000.0
REFERENCE_ANGLES = 180
INITIAL_RADIUS_KM = 100.0
INNER_MAX_STEPS = 40
INNER_TOLERANCE_M = 100.0


@dataclass(frozen=True)
class CentroidOptions:
    max_iterations: int = 15
    tolerance_m: float = 250.0
    max_motion_iterations: int = 50
    motion_solver: str = "aitken"
    motion_relaxation: float = 0.25
    motion_tolerance_m: float = 250.0
    r80_max_km: float = 250.0
    dr_km: float = 2.5
    dtheta: float = 5.0

    def __post_init__(self):
        for name in ("max_iterations", "max_motion_iterations"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"pressure_centroid_{name} must be an integer >= 1")
        for name in ("tolerance_m", "motion_tolerance_m", "motion_relaxation",
                     "r80_max_km", "dr_km", "dtheta"):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"pressure_centroid_{name} must be finite and positive")
        if self.motion_solver not in ("aitken", "fixed"):
            raise ValueError("pressure_centroid_motion_solver must be aitken or fixed")
        if self.motion_relaxation > 1:
            raise ValueError("pressure_centroid_motion_relaxation must be <= 1")
        if self.r80_max_km < 2 * self.dr_km or self.dtheta > 90:
            raise ValueError("R80 requires at least two radii and four azimuths")

    @classmethod
    def from_config(cls, conf):
        return cls(**{f.name: getattr(conf, "pressure_centroid_" + f.name)
                      for f in fields(cls)})


def interpolate_to_height(rec, height=HEIGHT_M):
    """Linear wind and log-pressure interpolation; no vertical extrapolation."""
    z = np.asarray(rec["z"], float)
    if z.ndim != 3 or z.shape[0] < 2:
        raise ValueError("At least two vertical levels are required")
    # Legacy numerical records explicitly use hPa; adapters supply Pa records.
    native = "pressure_field_pa" in rec
    in_pa = native or "pressure_levels_pa" in rec
    if native:
        pressure = np.asarray(rec["pressure_field_pa"], float)
        if pressure.shape != z.shape:
            raise ValueError("Native pressure and physical height must have identical shapes")
        if np.any(np.isfinite(pressure) & (pressure <= 0)):
            raise ValueError("Absolute pressure must be positive")
        differences = np.diff(z, axis=0)
        finite_columns = np.isfinite(z).all(axis=0)
        monotone = np.all(differences > 0, axis=0) | np.all(differences < 0, axis=0)
        if np.any(finite_columns & ~monotone):
            raise ValueError("Physical height must be strictly monotone in every native column")
    else:
        levels = np.asarray(rec["pressure_levels_pa"] if in_pa else rec["pressure_levels"], float)
        if not np.isfinite(levels).all() or np.any(levels <= 0):
            raise ValueError("Pressure levels must be finite and positive")
        pressure = np.broadcast_to(levels[:, None, None] * (1 if in_pa else 100), z.shape)
    ordering = np.argsort(z, axis=0)
    zs = np.take_along_axis(z, ordering, axis=0)
    above = np.sum(zs < height, axis=0)
    hi = np.clip(above, 1, zs.shape[0] - 1)
    lo = hi - 1

    def get(a, idx):
        return np.take_along_axis(a, idx[None], axis=0)[0]

    za, zb = get(zs, lo), get(zs, hi)
    ok = (height >= zs[0]) & (height <= zs[-1]) & np.isfinite(za) & np.isfinite(zb)
    if native:
        ok &= finite_columns
    frac = (height - za) / np.where(zb > za, zb - za, np.nan)
    result = []
    for data in (rec["u"], rec["v"], np.log(pressure)):
        sorted_data = np.take_along_axis(data, ordering, axis=0)
        lower, upper = get(sorted_data, lo), get(sorted_data, hi)
        out = np.where(frac == 0, lower, np.where(frac == 1, upper,
                       lower * (1 - frac) + upper * frac))
        out[~ok] = np.nan
        result.append(out)
    return dict(u=result[0], v=result[1], p=np.exp(result[2]) / (1 if in_pa else 100))


def make_interpolator(lon, lat, data):
    """Bilinear sampling on a stationary regular lat/lon grid, wrap aware."""
    if not (np.allclose(lon, lon[0][None, :], rtol=0, atol=1e-6)
            and np.allclose(lat, lat[:, 0][:, None], rtol=0, atol=1e-6)):
        raise ValueError("pressure_centroid requires a regular latitude/longitude grid")
    xs = np.rad2deg(np.unwrap(np.deg2rad(lon[0])))
    ys = lat[:, 0].copy()
    a = np.asarray(data)
    if xs.size < 2 or ys.size < 2:
        raise ValueError("At least two grid points per horizontal axis are required")
    if np.diff(xs).mean() < 0:
        xs, a = xs[::-1], a[:, ::-1]
    if np.diff(ys).mean() < 0:
        ys, a = ys[::-1], a[::-1]
    for axis in (xs, ys):
        delta = np.diff(axis)
        if not np.all(delta > 0) or not np.allclose(delta, delta[0], rtol=1e-5, atol=1e-6):
            raise ValueError("Nonmonotone or nonuniform latitude/longitude axis")
    fn = RegularGridInterpolator((ys, xs), a, bounds_error=False, fill_value=np.nan)
    mid = 0.5 * (xs[0] + xs[-1])

    def sample(lons, lats):
        ll, lats = np.broadcast_arrays(np.asarray(lons, float), np.asarray(lats, float))
        ll = mid + (ll - mid + 180) % 360 - 180
        return fn(np.column_stack((lats.ravel(), ll.ravel()))).reshape(lats.shape)

    return sample


def geodesic_circle(center, radius_m, bearings):
    bearings, radii = np.broadcast_arrays(np.asarray(bearings, float), radius_m)
    lon, lat, _ = GEOD.fwd(np.full(bearings.shape, center[0]),
                           np.full(bearings.shape, center[1]), bearings, radii)
    return lon, lat


def reference_pressure(center, sample_p):
    x, y = geodesic_circle(center, REFERENCE_RADIUS_M,
                           np.linspace(0, 360, REFERENCE_ANGLES, endpoint=False))
    sampled = sample_p(x, y)
    if not np.isfinite(sampled).all():
        raise ValueError("500-km pressure reference ring leaves valid data")
    return float(sampled.mean())


class LocalGridIndex:
    def __init__(self, lon, lat, area=None):
        self.lon = np.asarray(lon, float).ravel()
        self.lat = np.asarray(lat, float).ravel()
        lr, br = np.deg2rad(self.lon), np.deg2rad(self.lat)
        cb = np.cos(br)
        self.area = np.maximum(cb, 0) if area is None else np.asarray(area, float).ravel()
        if (self.area.shape != self.lon.shape or not np.isfinite(self.area).all()
                or np.any(self.area <= 0)):
            raise ValueError("Invalid native integration areas")
        xyz = np.column_stack((cb * np.cos(lr), cb * np.sin(lr), np.sin(br)))
        if not np.isfinite(xyz).all() or np.any(np.abs(self.lat) > 90):
            raise ValueError("Invalid grid coordinates")
        self.tree = cKDTree(xyz)

    def disk(self, center, radius_m):
        lr, br = np.deg2rad(center)
        q = (np.cos(br) * np.cos(lr), np.cos(br) * np.sin(lr), np.sin(br))
        cap = 2 * np.sin(min(np.pi, radius_m * 1.03 / 6_300_000) / 2)
        ids = np.asarray(self.tree.query_ball_point(q, cap, return_sorted=True), dtype=int)
        if not len(ids):
            return ids, np.empty(0), np.empty(0)
        az, _, dist = GEOD.inv(np.full(len(ids), center[0]),
                               np.full(len(ids), center[1]), self.lon[ids], self.lat[ids])
        inside = dist <= radius_m
        return ids[inside], az[inside], dist[inside]

    def nearest(self, center):
        # Exact ellipsoidal nearest cell; the first spherical candidate bounds
        # a conservative disk containing every potentially closer grid cell.
        lr, br = np.deg2rad(center)
        q = (np.cos(br) * np.cos(lr), np.cos(br) * np.sin(lr), np.sin(br))
        _, first = self.tree.query(q)
        distance = GEOD.inv(*center, self.lon[first], self.lat[first])[2]
        if distance == 0:
            return int(first), 0.0
        ids, _, distances = self.disk(center, distance + 1e-6)
        j = int(np.argmin(distances))
        return int(ids[j]), float(distances[j])


def centroid_iteration(center, radius_km, p, sample_p, grid_index):
    center = tuple(center)
    pflat = np.asarray(p).ravel()
    for _ in range(INNER_MAX_STEPS):
        env = reference_pressure(center, sample_p)
        ids, az, dist = grid_index.disk(center, radius_km * 1000)
        good = np.isfinite(pflat[ids])
        if np.count_nonzero(good) < 16:
            raise ValueError("Too few finite cells inside integration circle")
        ids, az, dist = ids[good], az[good], dist[good]
        weights = np.maximum(env - pflat[ids], 0) * grid_index.area[ids]
        total = weights.sum()
        if not np.isfinite(total) or total <= 0:
            raise ValueError("No positive pressure deficit inside integration region")
        angle = np.deg2rad(az)
        east = (weights * dist * np.sin(angle)).sum() / total
        north = (weights * dist * np.cos(angle)).sum() / total
        step_m = float(np.hypot(east, north))
        if step_m > 200_000:
            raise ValueError("Centroid iteration jumped >200 km")
        if step_m == 0:
            return center, env
        lon, lat, _ = GEOD.fwd(*center, np.degrees(np.arctan2(east, north)), step_m)
        center = (float(lon), float(lat))
        if step_m < INNER_TOLERANCE_M:
            return center, env
    raise ValueError("Centroid iteration failed to converge")


def calculate_r80(center, sample_u, sample_v, translation,
                  max_r_km=250, dr_km=2.5, dtheta=5):
    bearings = np.arange(0.0, 360.0, dtheta)
    radii = np.arange(dr_km, max_r_km + dr_km / 2, dr_km)
    rr, aa = np.meshgrid(radii, bearings, indexing="ij")
    xx, yy = geodesic_circle(center, rr.ravel() * 1000, aa.ravel())
    xx, yy = xx.reshape(rr.shape), yy.reshape(rr.shape)
    u, v = sample_u(xx, yy) - translation[0], sample_v(xx, yy) - translation[1]
    if not (np.isfinite(u).all() and np.isfinite(v).all()):
        raise ValueError("R80 wind sampling has missing data or leaves domain")
    _, backaz, _ = GEOD.inv(np.full(xx.shape, center[0]),
                            np.full(yy.shape, center[1]), xx, yy)
    theta = np.deg2rad((backaz + 180) % 360)
    clockwise = u * np.cos(theta) - v * np.sin(theta)
    profile = (clockwise if center[1] < 0 else -clockwise).mean(axis=1)
    if profile.max() <= 0:
        raise ValueError("No positive cyclonic tangential wind maximum")
    peak = int(np.argmax(profile))
    if peak == 0:
        raise ValueError("Tangential wind maximum at innermost sampled radius")
    threshold = 0.8 * profile[peak]
    rising = np.flatnonzero((profile[:peak] < threshold)
                            & (profile[1:peak + 1] >= threshold))
    if not len(rising):
        raise ValueError("No inward R80 crossing resolved; reduce dr or inspect vortex")
    j = int(rising[0])
    f = (threshold - profile[j]) / (profile[j + 1] - profile[j])
    return float(radii[j] + f * (radii[j + 1] - radii[j])), radii, profile


def adaptive_centroid(rec, initial, translation, options):
    p = rec["h2000"]["p"]
    if "_interpolators" not in rec:
        factory = rec.get("_sampler_factory")
        rec["_interpolators"] = tuple(
            factory(rec["h2000"][name]) if factory is not None else
            make_interpolator(rec["lon"], rec["lat"], rec["h2000"][name])
            for name in ("p", "u", "v"))
    sp, su, sv = rec["_interpolators"]
    index = rec["_grid_index"]
    center, env = centroid_iteration(initial, INITIAL_RADIUS_KM, p, sp, index)
    history = []
    for _ in range(options.max_iterations):
        r80, _, _ = calculate_r80(center, su, sv, translation, options.r80_max_km,
                                  options.dr_km, options.dtheta)
        radius = 2 * r80
        nxt, env = centroid_iteration(center, radius, p, sp, index)
        displacement = GEOD.inv(*center, *nxt)[2]
        history.append((r80, radius, displacement))
        center = nxt
        if displacement < options.tolerance_m:
            return center, r80, radius, env, history
    raise ValueError("Adaptive centroid failed to converge")


def min_index(field, center=None, half_width=40):
    if center is None:
        sub, yi, xi = field, 0, 0
    else:
        j, i = center
        yi, xi = max(j - half_width, 0), max(i - half_width, 0)
        sub = field[yi:j + half_width + 1, xi:i + half_width + 1]
    if not np.isfinite(sub).any():
        raise ValueError("No valid field within local tracking window")
    jj, ii = np.unravel_index(np.argmin(np.where(np.isfinite(sub), sub, np.inf)), sub.shape)
    return int(yi + jj), int(xi + ii)


def motion_vectors(records, centers):
    times = np.asarray([r["time"] for r in records], dtype="datetime64[ns]")
    if len(times) < 2 or np.isnat(times).any() or np.any(np.diff(times) <= np.timedelta64(0, "ns")):
        raise ValueError("pressure_centroid requires at least two strictly increasing valid times")
    out = []
    for k in range(len(records)):
        i, j = ((0, 1) if k == 0 else (len(records) - 2, len(records) - 1)
                if k == len(records) - 1 else (k - 1, k + 1))
        dt = float((times[j] - times[i]) / np.timedelta64(1, "s"))
        az, _, distance = GEOD.inv(*centers[i], *centers[j])
        out.append((distance * np.sin(np.deg2rad(az)) / dt,
                    distance * np.cos(np.deg2rad(az)) / dt))
    return out


def move_toward(a, b, fraction):
    azimuth, _, distance = GEOD.inv(*a, *b)
    lon, lat, _ = GEOD.fwd(*a, azimuth, fraction * distance)
    return float(lon), float(lat)


def solve_motion_centroids(records, options):
    """Coupled fixed point; convergence ALWAYS uses the unrelaxed residual."""
    centers = [r["guess"] for r in records]
    motion_vectors(records, centers)  # Validate outside accelerated-step recovery.
    residual_history = []
    previous_vector = previous_alpha = previous_max = None
    fallback_steps = backtracks = 0
    last_update = None
    residuals = None
    for cycle in range(1, options.max_motion_iterations + 1):
        try:
            velocities = motion_vectors(records, centers)
            targets, diagnostics = [], []
            for rec, center, velocity in zip(records, centers, velocities, strict=True):
                try:
                    target, r80, radius, env, history = adaptive_centroid(
                        rec, center, velocity, options)
                except ValueError as exc:
                    raise ValueError(f"pressure_centroid at {rec['time']}: {exc}") from exc
                targets.append(target)
                diagnostics.append((r80, radius, env, len(history)))
        except ValueError:
            if options.motion_solver != "aitken" or last_update is None or backtracks >= 3:
                raise
            backtracks += 1
            old_centers, old_targets, old_alpha = last_update
            retry_alpha = min(options.motion_relaxation, old_alpha / (2 ** backtracks))
            centers = [move_toward(a, b, retry_alpha)
                       for a, b in zip(old_centers, old_targets, strict=True)]
            previous_vector = previous_alpha = previous_max = None
            residual_history.clear()
            fallback_steps = 5
            logger.debug("Centroid accelerated-step backtrack: relaxation=%.3f", retry_alpha)
            continue
        backtracks = 0
        geodesics = [GEOD.inv(*a, *b) for a, b in zip(centers, targets, strict=True)]
        residuals = [float(d) for _, _, d in geodesics]
        vector = np.array([value for az, _, distance in geodesics
                           for value in (distance * np.sin(np.deg2rad(az)),
                                         distance * np.cos(np.deg2rad(az)))])
        maximum = max(residuals)
        residual_history.append(maximum)
        if maximum < options.motion_tolerance_m:
            logger.debug("Centroid outer iteration %d: unrelaxed residual %.1f m (converged)",
                        cycle, maximum)
            for rec, residual, velocity, diagnostic in zip(
                    records, residuals, velocities, diagnostics, strict=True):
                r80, radius, env, count = diagnostic
                environment_hpa = env / 100 if rec.get("pressure_units") == "Pa" else env
                rec.update(r80_km=r80, radius_km=radius, environment_hpa=environment_hpa,
                           iterations=count, motion_residual_m=residual,
                           motion_outer_iterations=cycle,
                           translation_u=velocity[0], translation_v=velocity[1])
            return centers
        if len(residual_history) >= 5:
            recent = residual_history[-5:]
            if (min(recent) > options.motion_tolerance_m
                    and max(recent) - min(recent) < .01 * min(recent)):
                logger.info("Centroid coupled solution is stagnating above tolerance")
        alpha = options.motion_relaxation
        if options.motion_solver == "aitken" and fallback_steps == 0:
            if previous_vector is None:
                alpha = 1.0
            else:
                difference = vector - previous_vector
                denom = float(difference @ difference)
                if denom > 1e-12:
                    proposal = -previous_alpha * float(previous_vector @ difference) / denom
                    if np.isfinite(proposal) and proposal > 0:
                        alpha = float(np.clip(proposal, .15, 1.5))
                if maximum > 1.2 * previous_max:
                    alpha = min(alpha, options.motion_relaxation)
            if (len(residual_history) >= 5
                    and min(residual_history[-4:]) >= residual_history[-5] * .98):
                fallback_steps = 5
                alpha = options.motion_relaxation
                logger.debug("Aitken stalled: temporarily using fixed relaxation")
        elif fallback_steps:
            fallback_steps -= 1
        logger.debug("Centroid outer iteration %d: unrelaxed residual %.1f m; relaxation=%.3f",
                    cycle, maximum, alpha)
        previous_vector, previous_alpha, previous_max = vector, alpha, maximum
        last_update = centers, targets, alpha
        centers = [move_toward(a, b, alpha) for a, b in zip(centers, targets, strict=True)]
    details = ", ".join(f"{r['time']}: {d:.0f} m"
                        for r, d in zip(records, residuals, strict=True))
    raise ValueError(f"Coupled storm-motion/centroid iteration did not converge after "
                     f"{options.max_motion_iterations} iterations: maximum unrelaxed residual "
                     f"{max(residuals):.1f} m (requested < {options.motion_tolerance_m:g} m). "
                     f"Per-time residuals: {details}")
