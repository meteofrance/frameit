# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Labelled time alignment and finite structured geometry for polar sampling."""

from __future__ import annotations

import numpy as np
import xarray as xr


def time_index(ds: xr.Dataset, context: str):
    if "time" not in ds.coords or ds.time.dims != ("time",) or not ds.time.size:
        raise ValueError(f"{context} requires a non-empty labelled time(time) coordinate")
    index = ds.time.to_index()
    if not index.is_unique or bool(ds.time.isnull().any()):
        raise ValueError(f"{context} contains duplicate or missing time labels")
    return index


def _time_kind(index):
    if hasattr(index, "calendar"):
        return "calendar", index.calendar
    dtype = np.asarray(index.values).dtype
    if np.issubdtype(dtype, np.datetime64):
        return "datetime", None
    if np.issubdtype(dtype, np.number):
        return "numeric", None
    return str(dtype), None


def align_times(ds: xr.Dataset, reference: xr.DataArray, context: str, *, exact=True):
    source = time_index(ds, context)
    expected = reference.to_index()
    if _time_kind(source) != _time_kind(expected):
        raise ValueError(f"{context} has an incompatible time representation or calendar")
    if (exact and len(source) != len(expected)) or np.any(source.get_indexer(expected) < 0):
        raise ValueError(f"{context} does not contain exactly the required reference times")
    result = ds.sel(time=reference.values)
    # Keep labels/attributes without carrying reference-group scalar coordinates.
    result = result.assign_coords(time=reference.variable)
    return result


def source_lonlat(ds: xr.Dataset, lon_name: str, lat_name: str):
    if lon_name not in ds or lat_name not in ds:
        raise ValueError("Source grid requires geographic longitude and latitude")
    lon, lat = xr.broadcast(geographic_degrees(ds[lon_name]), geographic_degrees(ds[lat_name]))
    if set(lon.dims) != {"y_box", "x_box"} or set(lat.dims) != {"y_box", "x_box"}:
        raise ValueError("Source geography must use named y_box/x_box dimensions")
    lon = np.asarray(lon.transpose("y_box", "x_box").values, dtype=float)
    lat = np.asarray(lat.transpose("y_box", "x_box").values, dtype=float)
    if lon.shape != (ds.sizes["y_box"], ds.sizes["x_box"]) or lat.shape != lon.shape:
        raise ValueError("Source geographic coordinates do not match the field grid")
    return lon, lat


def geographic_degrees(coordinate):
    if coordinate.attrs.get("standard_name") in {"grid_latitude", "grid_longitude"}:
        raise ValueError("Rotated-grid coordinates are not geographic longitude/latitude")
    units = coordinate.attrs.get("units", "degree")
    if units in {"rad", "radian", "radians"}:
        result = np.rad2deg(coordinate)
        result.attrs = {**coordinate.attrs, "units": "degree"}
        return result
    if units not in {"degree", "degrees", "degrees_east", "degrees_north"}:
        raise ValueError("Geographic coordinates must be angular degrees or radians")
    return coordinate


def finite_source_footprint(ds: xr.Dataset, lon_name: str, lat_name: str):
    """Trim NaN-padded domain edges; never fabricate coordinates inside a grid."""
    lon, lat = source_lonlat(ds, lon_name, lat_name)
    finite = np.isfinite(lon) & np.isfinite(lat)
    rows, cols = np.where(finite)
    if not rows.size:
        raise ValueError("Source footprint has no finite geographic coordinates")
    y_slice = slice(int(rows.min()), int(rows.max()) + 1)
    x_slice = slice(int(cols.min()), int(cols.max()) + 1)
    lon, lat = lon[y_slice, x_slice], lat[y_slice, x_slice]
    if not np.isfinite(lon).all() or not np.isfinite(lat).all():
        raise ValueError("Missing geographic coordinates inside the source footprint")
    if min(lon.shape) < 2:
        raise ValueError("Source footprint needs at least two points along each horizontal axis")
    if np.any(np.abs(lat) > 90):
        raise ValueError("Source latitude must lie within [-90, 90] degrees")
    # Unwrap coordinates without reordering points or changing cell connectivity.
    lon = np.rad2deg(np.unwrap(np.unwrap(np.deg2rad(lon), axis=1), axis=0))
    _validate_cells(lon, lat)
    grid = xr.Dataset({
        "lon": (("y_box", "x_box"), np.ascontiguousarray(lon)),
        "lat": (("y_box", "x_box"), np.ascontiguousarray(lat)),
    })
    footprint = {
        "original_shape": [ds.sizes["y_box"], ds.sizes["x_box"]],
        "finite_shape": list(lon.shape),
        "y_slice": [y_slice.start, y_slice.stop], "x_slice": [x_slice.start, x_slice.stop],
    }
    return ds.isel(y_box=y_slice, x_box=x_slice), grid, footprint


def _validate_cells(lon, lat):
    """Require a nonfolded regional quadrilateral grid in unwrapped lon/lat."""
    east_x, east_y = lon[:-1, 1:] - lon[:-1, :-1], lat[:-1, 1:] - lat[:-1, :-1]
    diag_x, diag_y = lon[1:, 1:] - lon[:-1, :-1], lat[1:, 1:] - lat[:-1, :-1]
    south_x, south_y = lon[1:, :-1] - lon[:-1, :-1], lat[1:, :-1] - lat[:-1, :-1]
    first = east_x * diag_y - east_y * diag_x
    second = diag_x * south_y - diag_y * south_x
    scale = np.maximum(east_x**2 + east_y**2, south_x**2 + south_y**2)
    tolerance = 1e-12 * scale
    if np.any(np.abs(first) <= tolerance) or np.any(np.abs(second) <= tolerance):
        raise ValueError("Source grid contains degenerate cells")
    signs = np.sign(first)
    if np.any(signs != np.sign(second)) or np.any(signs != signs.flat[0]):
        raise ValueError("Source grid contains folded or inconsistent cell connectivity")


def target_locstream(lon, lat):
    lon, lat = np.asarray(lon), np.asarray(lat)
    if lon.shape != lat.shape or not np.isfinite(lon).all() or not np.isfinite(lat).all():
        raise ValueError("Target geographic coordinates must be finite and consistently shaped")
    if np.any(np.abs(lat) > 90):
        raise ValueError("Target latitude must lie within [-90, 90] degrees")
    return xr.Dataset({"lon": ("locations", lon.ravel()), "lat": ("locations", lat.ravel())})


def same_source_geometry(ds: xr.Dataset, lon_name: str, lat_name: str):
    first = source_lonlat(ds.isel(time=0, drop=True), lon_name, lat_name)
    return all(
        all(np.array_equal(a, b, equal_nan=True) for a, b in zip(
            first, source_lonlat(ds.isel(time=index, drop=True), lon_name, lat_name), strict=True
        )) for index in range(1, ds.sizes["time"])
    )
