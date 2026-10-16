"""Cached native-quadrilateral sampling and nodal integration areas for MNH."""

import numpy as np
from scipy.spatial import cKDTree

from frameit.processing.polar.contracts import _validate_cells

from .pressure_centroid import GEOD


class StructuredGrid:
    """Inverse bilinear cell mapping, without triangulating across grid boundaries.

    Search uses unwrapped, locally scaled lon/lat only as a conservative locator.
    Native connectivity defines interpolation support; all integration distances
    and polygon areas use WGS84. Only the last target stencil is retained.
    """

    def __init__(self, lon, lat):
        lon, lat = np.asarray(lon, float), np.asarray(lat, float)
        if lon.ndim != 2 or lon.shape != lat.shape or min(lon.shape) < 2:
            raise ValueError("MNH pressure_centroid requires a two-dimensional structured grid")
        if not np.isfinite(lon).all() or not np.isfinite(lat).all() or np.any(np.abs(lat) >= 90):
            raise ValueError("Invalid finite regional MNH geographic coordinates")
        lon = np.rad2deg(np.unwrap(np.unwrap(np.deg2rad(lon), axis=1), axis=0))
        if np.ptp(lon) >= 180:
            raise ValueError(
                "MNH pressure_centroid supports regional grids spanning less than 180 degrees")
        _validate_cells(lon, lat)
        self.shape = lon.shape
        self.mid = float(np.mean(lon))
        self.scale = np.cos(np.deg2rad(np.mean(lat)))
        nodes = np.stack((lon * self.scale, lat), axis=-1)
        corners = np.stack((nodes[:-1, :-1], nodes[:-1, 1:],
                            nodes[1:, 1:], nodes[1:, :-1]), axis=-2).reshape(-1, 4, 2)
        self.origin = corners[:, 0]
        self.b = corners[:, 1] - self.origin
        self.c = corners[:, 3] - self.origin
        self.d = corners[:, 2] - corners[:, 1] - corners[:, 3] + self.origin
        determinants = []
        for s, t in ((0, 0), (1, 0), (1, 1), (0, 1)):
            js, jt = self.b + self.d * t, self.c + self.d * s
            determinants.append(js[:, 0] * jt[:, 1] - js[:, 1] * jt[:, 0])
        determinants = np.asarray(determinants)
        orientation = np.sign(determinants[0])
        if np.any(determinants * orientation <= 1e-12 * np.sum(self.b**2 + self.c**2, axis=1)):
            raise ValueError("MNH source grid contains concave or degenerate bilinear cells")
        centers = corners.mean(axis=1)
        self.radius = np.max(np.linalg.norm(corners - centers[:, None], axis=-1)) * (1 + 1e-10)
        self.tree = cKDTree(centers)
        self._last = None
        # Nodal quadrature: each native quadrilateral distributes a quarter of
        # its ellipsoidal area to each mass point. Boundary nodes get half/quarter
        # support; no latitude-only metric is imposed on a projected mesh.
        cells = np.stack((lon[:-1, :-1], lon[:-1, 1:], lon[1:, 1:], lon[1:, :-1]), axis=-1)
        lats = np.stack((lat[:-1, :-1], lat[:-1, 1:], lat[1:, 1:], lat[1:, :-1]), axis=-1)
        areas = np.array([abs(GEOD.polygon_area_perimeter(x, y)[0])
                          for x, y in zip(cells.reshape(-1, 4), lats.reshape(-1, 4), strict=True)])
        areas = areas.reshape(lon.shape[0] - 1, lon.shape[1] - 1) / 4
        self.area = np.zeros(lon.shape)
        for rows, cols in ((slice(None, -1), slice(None, -1)), (slice(None, -1), slice(1, None)),
                           (slice(1, None), slice(1, None)), (slice(1, None), slice(None, -1))):
            self.area[rows, cols] += areas
        if not np.all(self.area > 0):
            raise ValueError("Invalid native MNH integration-cell areas")

    def _stencil(self, lons, lats):
        ll, lat = np.broadcast_arrays(np.asarray(lons, float), np.asarray(lats, float))
        lon = self.mid + (ll - self.mid + 180) % 360 - 180
        points = np.column_stack((lon.ravel() * self.scale, lat.ravel()))
        if not np.isfinite(points).all():
            raise ValueError("MNH sampling targets must be finite")
        if self._last is not None and np.array_equal(points, self._last[0]):
            return ll.shape, *self._last[1:]
        candidates = self.tree.query_ball_point(points, self.radius, return_sorted=True)
        counts = np.array([len(ids) for ids in candidates])
        targets = np.repeat(np.arange(len(points)), counts)
        ids = np.concatenate(candidates).astype(int) if counts.sum() else np.empty(0, int)
        q = points[targets] - self.origin[ids]
        b, c, d = self.b[ids], self.c[ids], self.d[ids]
        s, t = np.full(len(ids), .5), np.full(len(ids), .5)
        for _ in range(12):
            residual = b * s[:, None] + c * t[:, None] + d * (s * t)[:, None] - q
            js, jt = b + d * t[:, None], c + d * s[:, None]
            det = js[:, 0] * jt[:, 1] - js[:, 1] * jt[:, 0]
            good = np.abs(det) > 1e-20
            denominator = np.where(good, det, np.nan)
            s -= (residual[:, 0] * jt[:, 1] - residual[:, 1] * jt[:, 0]) / denominator
            t -= (js[:, 0] * residual[:, 1] - js[:, 1] * residual[:, 0]) / denominator
        residual = b * s[:, None] + c * t[:, None] + d * (s * t)[:, None] - q
        valid = (np.isfinite(s) & np.isfinite(t) & (s >= -1e-10) & (s <= 1 + 1e-10)
                 & (t >= -1e-10) & (t <= 1 + 1e-10)
                 & (np.linalg.norm(residual, axis=1) <= 1e-8 * np.linalg.norm(b + c, axis=1)))
        chosen = np.flatnonzero(valid)
        _, first = np.unique(targets[chosen], return_index=True)
        chosen = chosen[first]
        target, cell = targets[chosen], ids[chosen]
        s, t = np.clip(s[chosen], 0, 1), np.clip(t[chosen], 0, 1)
        row, col = np.divmod(cell, self.shape[1] - 1)
        base = row * self.shape[1] + col
        nodes = np.column_stack((base, base + 1, base + self.shape[1] + 1, base + self.shape[1]))
        weights = np.column_stack(((1 - s) * (1 - t), s * (1 - t), s * t, (1 - s) * t))
        self._last = points.copy(), target, nodes, weights
        return ll.shape, target, nodes, weights

    def interpolator(self, data):
        data = np.asarray(data)
        if data.shape != self.shape:
            raise ValueError("MNH sample field does not match native geometry")

        def sample(lons, lats):
            shape, target, nodes, weights = self._stencil(lons, lats)
            values = data.ravel()[nodes]
            # Zero-weight neighbours do not invalidate exact-node/edge samples.
            active = weights > 1e-14
            valid = np.all(np.isfinite(values) | ~active, axis=1)
            result = np.full(int(np.prod(shape)), np.nan)
            result[target[valid]] = np.sum(np.where(active, values, 0) * weights, axis=1)[valid]
            return result.reshape(shape)

        return sample
