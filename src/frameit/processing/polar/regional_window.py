# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Conservative source strip bounds for ESMF's regional Cartesian bilinear search."""

from dataclasses import dataclass

import numpy as np

# In the admitted hemisphere (front >= 0.5), this covers the ESMF 8.9.1
# parametric edge tolerance (up to 1e-7) after central projection.
_SEARCH_PADDING = 1e-5


def _project(lon, lat, origin):
    """Map Earth-centred rays to the tangent plane at the fixed source origin."""
    lon = np.deg2rad(lon) - origin[0]
    lat = np.deg2rad(lat)
    c, s = np.cos(origin[1]), np.sin(origin[1])
    clat, slat = np.cos(lat), np.sin(lat)
    meridian = clat * np.cos(lon)
    front = c * meridian + s * slat
    if np.any(front < .5):
        return None
    return clat * np.sin(lon) / front, (c * slat - s * meridian) / front


def _cartesian(lon, lat):
    """Use the colatitude convention of ESMF's SPH_DEG conversion."""
    lon, colat = np.deg2rad(lon), np.deg2rad(90. - lat)
    return np.stack((np.sin(colat) * np.cos(lon), np.sin(colat) * np.sin(lon), np.cos(colat)), axis=-1)


def _has_inside_matches(lon, lat, target_lon, target_lat, rows, y, x):
    """For clipped rows, witness an in-cell match without using its weights."""
    # An exact native node is found before the element search.
    exact = (lon[y, x] == target_lon[rows]) & (lat[y, x] == target_lat[rows])
    matched = rows[exact]
    rows, y, x = rows[~exact], y[~exact], x[~exact]
    required = np.union1d(rows, matched)
    if not rows.size:
        return True

    # Try the real quads incident to each remaining positive contributor.
    # GridToMesh orders corners (00, 10, 11, 01) in x/y. At an edge through
    # corner 00, the Cartesian radial intersection is linear to first order.
    y = y[:, None] + [0, -1, -1, 0]
    x = x[:, None] + [0, 0, -1, -1]
    rows = np.repeat(rows, 4)
    qy = y.reshape(-1, 1) + [0, 0, 1, 1]
    qx = x.reshape(-1, 1) + [0, 1, 1, 0]
    corners = _cartesian(lon[qy, qx], lat[qy, qx])
    a, b, c, d = corners.transpose(1, 0, 2)
    target = _cartesian(target_lon[rows], target_lat[rows])
    edge_x, edge_y = b - a, d - a
    jac = np.stack((edge_x, edge_y, -target), axis=-1)
    lengths = np.linalg.norm(jac[..., :2], axis=1)
    # The cell must also be visible on the first pass through the search tree.
    box = np.all((corners.min(axis=1) - 1e-9 <= target)
                 & (target <= corners.max(axis=1) + 1e-9), axis=1)
    good = box & (np.abs(np.linalg.det(jac)) > .75 * lengths.prod(axis=1))
    u, v, t = np.linalg.solve(jac[good], -a[good, :, None])[..., 0].T
    # One Newton update from (0, 0, 0), as in ESMF 8.9.1's
    # intersect_quad_with_line. Leave ample roundoff room for the double
    # coordinate conversion and cofactor solve, and a decade for the residual.
    rounding = 64 * np.finfo(float).eps / lengths[good].min(axis=1)
    slack = 5e-11 - rounding  # quad is_in tolerance, converted to [0, 1]
    residual = (u * v)[:, None] * (a - b + c - d)[good]
    inside = ((t > .5) & (u >= -slack) & (v >= -slack) & (u <= 1 + slack) & (v <= 1 + slack)
              & (np.linalg.norm(residual, axis=1) < 1e-11))
    return np.union1d(matched, rows[good][inside]).size == required.size


@dataclass(frozen=True)
class RegionalWindow:
    """Only the per-axis strip envelopes are retained, not the projected mesh."""

    origin: tuple[float, float]
    bounds: tuple[np.ndarray, np.ndarray]

    @classmethod
    def capture(cls, lon, lat):
        # shortcut: leave polar source nodes to the full builder until qualified.
        if np.any(np.abs(lat) >= 89):
            return None
        mid = tuple(size // 2 for size in lon.shape)
        origin = tuple(np.deg2rad([lon[mid], lat[mid]]))
        projected = _project(lon, lat, origin)
        if projected is None:
            return None
        x, y = projected
        for axis, major, minor in ((0, y, x), (1, x, y)):
            steps = np.diff(major, axis=axis)
            # Consistently directed edge cones keep quads convex and prevent overlaps.
            if not np.all(steps * np.sign(steps.flat[0])
                          > np.abs(np.diff(minor, axis=axis)) + _SEARCH_PADDING):
                return None
        bounds = tuple(np.stack((a.min(axis=axis), a.max(axis=axis)))
                       for a, axis in ((y, 1), (x, 0)))
        for axis in bounds:
            axis.setflags(write=False)
        return cls(origin, bounds)

    @property
    def nbytes(self):
        return sum(axis.nbytes for axis in self.bounds)

    def find(self, lon, lat):
        projected = _project(lon, lat, self.origin)
        if projected is None:
            return None
        window = []
        # The image of a Cartesian bilinear quad lies in the convex hull of its
        # projected vertices. A strip uses all vertices from both native rows/columns.
        for target, (lo, hi) in zip(projected[::-1], self.bounds, strict=True):
            cells = np.flatnonzero(
                (np.minimum(lo[:-1], lo[1:]) <= target.max() + _SEARCH_PADDING)
                & (np.maximum(hi[:-1], hi[1:]) >= target.min() - _SEARCH_PADDING))
            if not cells.size:
                return None
            start, stop = int(cells[0]) - 1, int(cells[-1]) + 3
            if start <= 0 or stop >= lo.size:
                return None
            window.append(slice(start, stop))
        return tuple(window)
