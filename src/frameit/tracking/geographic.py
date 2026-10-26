"""Geographical point lookup independent of a model's storage format.

The regional squared-degree nearest-point convention is retained from the
geometric trackers. Equivalent longitude representations are matched modulo 360;
differences already within [-180,180] retain their original arithmetic/ties.
This is index lookup, not interpolation or a geodesic metric.
Admitted FA Lambert datasets instead use their explicit source CRS/native axes
through locate_track; an ordinary CF mapping alone never switches legacy inputs.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

SNAP_VARIABLES = ("grid_selected_latitude", "grid_selected_longitude", "grid_snap_dx_m",
                  "grid_snap_dy_m", "grid_snap_distance_m")
SNAP_ATTRIBUTES = {"tracking_grid_lookup", "tracking_snap_convention", "tracking_grid_ties"}


def clear_grid_observations(track):
    """A different source must never inherit another grid's snapping facts."""
    result = track.drop_vars(list(SNAP_VARIABLES), errors="ignore")
    result.attrs = {key: value for key, value in track.attrs.items() if key not in SNAP_ATTRIBUTES}
    return result


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


def uses_native_fa_lookup(source):
    from frameit.io.fa_geometry import NATIVE_LOOKUP

    return source.attrs.get("fa_grid_lookup") == NATIVE_LOOKUP


def _projected_fa_axes(source, axes, lat_name, lon_name):
    """Prove geography/axes/CRS association over every cell, in bounded row blocks."""
    from pyproj import CRS, Transformer

    axes = axes or ("y", "x")
    ydim, xdim = axes
    if ("crs" not in source.coords
            or source.crs.attrs.get("grid_mapping_name") != "lambert_conformal_conic"
            or "earth_radius" not in source.crs.attrs):
        raise ValueError("Native FA lookup requires its explicit spherical Lambert CRS")
    lat, lon = source[lat_name], source[lon_name]
    if (set(lat.dims) != set(axes) or set(lon.dims) != set(axes)
            or lat.attrs.get("units") != "degrees_north"
            or lon.attrs.get("units") != "degrees_east"):
        raise ValueError("Native FA lookup requires static named geography in explicit degrees")
    coordinates = []
    for dim in (ydim, xdim):
        axis = source[dim]
        values = np.asarray(axis, float)
        if (axis.dims != (dim,) or axis.attrs.get("units") != "m"
                or values.size < 2 or not np.isfinite(values).all()):
            raise ValueError("Native FA lookup requires finite 1-D metre axes")
        delta = np.diff(values)
        tolerance = max(1.e-5, 64 * np.finfo(float).eps * np.max(np.abs(values)))
        if (not (np.all(delta > 0) or np.all(delta < 0))
                or not np.allclose(delta, delta[0], rtol=0, atol=tolerance)):
            raise ValueError("Native FA lookup requires monotone regular projected axes")
        coordinates.append(values)
    y, x = coordinates
    crs = CRS.from_cf(source.crs.attrs)
    forward = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
    lat, lon = lat.transpose(*axes), lon.transpose(*axes)
    for row in range(0, y.size, 32):
        stop = min(row + 32, y.size)
        px, py = forward.transform(np.asarray(lon.isel({ydim: slice(row, stop)})),
                                   np.asarray(lat.isel({ydim: slice(row, stop)})))
        # Internal double-precision CRS round trip, NOT the native-header corner
        # tolerance or permission to fit an unverified source Earth model.
        if (not np.allclose(px, x[None, :], rtol=0, atol=1.e-5)
                or not np.allclose(py, y[row:stop, None], rtol=0, atol=1.e-5)):
            raise ValueError("Native FA geography contradicts projected axes/CRS sample locations")
    return y, x, lat, lon, forward


def locate_track(track, source, *, axes=None, lat_name="latitude", lon_name="longitude",
                 require_inside=False):
    """Keep continuous centres; select native points without interpolating fields.

    Only the admitted FA marker changes the historical lookup convention. Other
    source formats retain nearest_grid_point, including its original tie choices.
    """
    result = clear_grid_observations(track)
    cy, cx = [], []
    native = uses_native_fa_lookup(source)
    if native:
        y, x, lat, lon, forward = _projected_fa_axes(source, axes, lat_name, lon_name)
        projected_x, projected_y = forward.transform(
            (np.asarray(track.lon) + 180) % 360 - 180, np.asarray(track.lat))
        observations = []
    else:
        lat, lon = source[lat_name], source[lon_name]
    centres = zip(track.lat.values, track.lon.values, strict=True)
    for index, (latitude, longitude) in enumerate(centres):
        if native and (not np.isfinite([latitude, longitude]).all() or abs(latitude) >= 90):
            raise ValueError("Geographic centres must be finite nonpolar coordinates")
        if native:
            qx, qy = projected_x[index], projected_y[index]
            if not np.isfinite([qx, qy]).all():
                raise ValueError("Geographic centre cannot be mapped to the source CRS")

            def select(axis, query):
                scale = max(np.max(abs(axis)), abs(query))
                tolerance = max(1.e-5, 64 * np.finfo(float).eps * scale)
                if require_inside and not axis.min() - tolerance <= query <= axis.max() + tolerance:
                    raise ValueError(
                        "A coupled geographic centre is outside a selected source grid; "
                        "no edge substitution or spatial time skipping is permitted")
                distance = abs(axis - query)
                return int(np.flatnonzero(distance <= distance.min() + tolerance)[0])

            j, i = select(y, qy), select(x, qx)
            observations.append([float(lat[j, i]), float(lon[j, i]), x[i] - qx, y[j] - qy])
        else:
            j, i = nearest_grid_point(lat, lon, float(latitude), float(longitude), axes=axes)
        cy.append(j)
        cx.append(i)
    result["cy"], result["cx"] = ("time", cy), ("time", cx)
    if native:
        for col, name, units in ((0, "grid_selected_latitude", "degrees_north"),
                                  (1, "grid_selected_longitude", "degrees_east"),
                                  (2, "grid_snap_dx_m", "m"), (3, "grid_snap_dy_m", "m")):
            result[name] = xr.DataArray([row[col] for row in observations], dims="time",
                                       attrs={"units": units})
        result.grid_selected_latitude.attrs["long_name"] = "selected source grid point latitude"
        result.grid_selected_longitude.attrs["long_name"] = "selected source grid point longitude"
        result.grid_snap_dx_m.attrs["long_name"] = (
            "selected minus requested source-CRS x coordinate")
        result.grid_snap_dy_m.attrs["long_name"] = (
            "selected minus requested source-CRS y coordinate")
        result["grid_snap_distance_m"] = np.hypot(result.grid_snap_dx_m, result.grid_snap_dy_m)
        result.grid_snap_distance_m.attrs.update(units="m", long_name="projected snapping distance")
        result.attrs.update(tracking_grid_lookup=source.attrs["fa_grid_lookup"],
                            tracking_snap_convention="selected minus requested; source CRS metres",
                            tracking_grid_ties="first storage index within roundoff tolerance")
    return result
