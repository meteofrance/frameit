"""Geographical point lookup independent of a model's storage format.

The regional squared-degree nearest-point convention is retained from the
geometric trackers. Equivalent longitude representations are matched modulo 360;
differences already within [-180,180] retain their original arithmetic/ties.
This is index lookup, not interpolation or a geodesic metric.
"""

from __future__ import annotations

import numpy as np


def longitude_difference(longitude, reference):
    difference = np.asarray(longitude) - reference
    return np.where(np.abs(difference) > 180, (difference + 180) % 360 - 180, difference)


def nearest_grid_point(latitude, longitude, lat0, lon0, *, axes=None):
    if latitude.ndim == longitude.ndim == 2:
        if axes is not None:
            latitude, longitude = latitude.transpose(*axes), longitude.transpose(*axes)
        elif hasattr(longitude, "transpose") and hasattr(latitude, "dims"):
            longitude = longitude.transpose(*latitude.dims)
        lat, lon = np.asarray(latitude), np.asarray(longitude)
        if lat.shape != lon.shape:
            raise ValueError("Geographic coordinate grids must have identical shapes")
        distance = (lat - lat0)**2 + longitude_difference(lon, lon0)**2
        if not np.isfinite(distance).any():
            raise ValueError("Source geography contains no finite candidate")
        return tuple(int(i) for i in np.unravel_index(np.nanargmin(distance), distance.shape))
    if latitude.ndim == longitude.ndim == 1:
        return (int(np.nanargmin((np.asarray(latitude) - lat0)**2)),
                int(np.nanargmin(longitude_difference(longitude, lon0)**2)))
    raise ValueError("Geographic lookup requires static 1-D axes or matching 2-D grids")
