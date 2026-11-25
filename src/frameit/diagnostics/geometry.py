"""Conservative structured-centre footprint and tile neighbour geometry."""

from dataclasses import dataclass
from math import pi

import numpy as np

METHOD = "structured_center_perimeter_v1"
EPSILON_M = 1.
PERIMETER_BYTES = 256


def _cross(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def _project(centre, latitude, longitude, geod):
    shape = latitude.shape
    azimuth, _, radius = geod.inv(
        np.full(shape, centre.longitude), np.full(shape, centre.latitude), longitude, latitude,
    )
    valid = (np.isfinite(latitude) & np.isfinite(longitude) & (np.abs(latitude) <= 90)
             & np.isfinite(radius) & (radius < min(geod.a, geod.b) * pi / 2))
    angle = np.deg2rad(azimuth)
    xy = np.stack((radius * np.sin(angle), radius * np.cos(angle)), axis=-1)
    return np.where(valid, radius, np.nan), np.mod(azimuth, 360), xy, valid


def _simple_boundary(points):
    """Sweep overlapping edge boxes; nonadjacent touches are not certified."""
    end = np.roll(points, -1, axis=0)
    lower, upper = np.minimum(points, end), np.maximum(points, end)
    if np.any(np.linalg.norm(end - points, axis=1) <= EPSILON_M):
        return False
    active = []
    for i in np.argsort(lower[:, 0], kind="stable"):
        active = [j for j in active if upper[j, 0] >= lower[i, 0] - EPSILON_M]
        for j in active:
            if abs(i - j) in {1, len(points) - 1}:
                continue
            if (upper[j, 1] < lower[i, 1] - EPSILON_M
                    or upper[i, 1] < lower[j, 1] - EPSILON_M):
                continue
            a, b, c, d = points[i], end[i], points[j], end[j]
            # Signed distances to the supporting lines (metres).
            for x, y, u, v in ((a, b, c, d), (c, d, a, b)):
                vector = y - x
                scale = np.linalg.norm(vector)
                dc, dd = _cross(vector, u - x) / scale, _cross(vector, v - x) / scale
                if min(dc, dd) > EPSILON_M or max(dc, dd) < -EPSILON_M:
                    break
            else:
                return False
        active.append(i)
    return True


def certify_disc(centre, perimeter, *, geod, radius_m, budget_bytes):
    """Return complete only with a simple, contained, locally valid perimeter."""
    latitude, longitude = perimeter
    max_vertices = budget_bytes // PERIMETER_BYTES
    if not 4 <= len(latitude) <= max_vertices:
        return "unknown_geometry"
    radii, _, points, valid = _project(centre, latitude, longitude, geod)
    if not np.all(valid) or not _simple_boundary(points):
        return "unknown_geometry"
    guard = radius_m + EPSILON_M
    if np.any(radii <= guard):
        return "truncated"
    winding = np.sum(np.arctan2(
        _cross(points, np.roll(points, -1, axis=0)),
        np.einsum("ij,ij->i", points, np.roll(points, -1, axis=0)),
    ))
    if abs(winding) < 1e-8:
        return "truncated"
    if abs(abs(winding) - 2 * pi) > 1e-8:
        return "unknown_geometry"
    # Triangle inequality: every point on a short edge is within half its
    # length of an endpoint. Refine uncertain edges without retaining a mesh.
    edges_az, _, lengths = geod.inv(longitude, latitude, np.roll(longitude, -1),
                                   np.roll(latitude, -1))
    checks = len(latitude)
    for i in range(len(latitude)):
        j = (i + 1) % len(latitude)
        if min(radii[i], radii[j]) - lengths[i] / 2 > guard:
            continue
        stack = [(longitude[i], latitude[i], radii[i],
                  longitude[j], latitude[j], radii[j], edges_az[i], lengths[i])]
        while stack:
            x, y, ra, x1, y1, rb, bearing, length = stack.pop()
            if min(ra, rb) - length / 2 > guard:
                continue
            if checks >= max_vertices or length <= EPSILON_M:
                return "unknown_geometry"
            checks += 1
            xm, ym, _ = geod.fwd(x, y, bearing, length / 2)
            _, _, rm = geod.inv(centre.longitude, centre.latitude, xm, ym)
            if not np.isfinite(rm):
                return "unknown_geometry"
            if rm <= guard:
                return "truncated"
            bearing_mid, _, right = geod.inv(xm, ym, x1, y1)
            stack.append((xm, ym, rm, x1, y1, rb, bearing_mid, right))
            stack.append((x, y, ra, xm, ym, rm, bearing, length / 2))
    return "complete"


def view_perimeter(view, shape):
    ny, nx = shape
    windows = (
        (slice(0, 1), slice(0, nx)),
        (slice(1, ny - 1), slice(nx - 1, nx)),
        (slice(ny - 1, ny), slice(0, nx)),
        (slice(1, ny - 1), slice(0, 1)),
    )
    parts = [view.geography(window) for window in windows]
    return tuple(np.concatenate([
        part[axis].ravel()[::-1] if i >= 2 else part[axis].ravel()
        for i, part in enumerate(parts)
    ]) for axis in range(2))


@dataclass(frozen=True)
class TileGeometry:
    radius: np.ndarray
    bearing: np.ndarray
    xy: np.ndarray
    valid: np.ndarray


def tile_geometry(centre, haloed_coordinates, *, geod):
    return TileGeometry(*_project(centre, *haloed_coordinates, geod))


def orientation(tile, available_cells):
    """Each native quad must have the same two nondegenerate triangle orientations."""
    xy = tile.xy
    origin = xy[:-1, :-1]
    diagonal = xy[1:, 1:] - origin
    a = _cross(xy[:-1, 1:] - origin, diagonal)[available_cells]
    b = _cross(diagonal, xy[1:, :-1] - origin)[available_cells]
    if not a.size:
        return None
    if np.all(a > EPSILON_M**2) and np.all(b > EPSILON_M**2):
        return 1
    if np.all(a < -EPSILON_M**2) and np.all(b < -EPSILON_M**2):
        return -1
    return 0


def disc_and_rim(radius, distance, interior):
    within = (radius <= distance)
    padded = np.pad(within, 1, constant_values=False)
    inner = padded[1:-1, 1:-1] & padded[:-2, 1:-1] & padded[2:, 1:-1] & (
        padded[1:-1, :-2] & padded[1:-1, 2:])
    return within[interior], (within & ~inner)[interior]
