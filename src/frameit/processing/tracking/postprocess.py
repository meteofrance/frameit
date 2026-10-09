# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging

import numpy as np
import xarray as xr
from pyproj import Geod

logger = logging.getLogger(__name__)


def _norm_az_deg(az_deg: np.ndarray) -> np.ndarray:
    """Normalize azimuth to [0, 360)."""
    az = np.asarray(az_deg, dtype=float)
    return (az % 360.0 + 360.0) % 360.0


def enrich_track_with_kinematics(
    track_ds: xr.Dataset,
    *,
    ds_flat: xr.Dataset,
    conf,
    ellps: str = "WGS84",
    time_dim: str | None = None,
    lon_name: str | None = None,
    lat_name: str | None = None,
    cx_name: str = "cx",
    cy_name: str = "cy",
    min_step_m: float = 1.0,
) -> xr.Dataset:
    """
    Post-process tracker output to add centre lon/lat and simple kinematics.

    Parameters
    ----------
    track_ds : xr.Dataset
        Tracker output.  Must contain ``cx(time)`` and ``cy(time)``
        (grid-point index arrays).
    ds_flat : xr.Dataset
        Flattened dataset used for tracking.  Must contain longitude and
        latitude fields in one of the accepted layouts:

        - 2-D ``(y, x)`` or 3-D ``(time, y, x)``
        - 1-D ``(x)`` for longitude and ``(y)`` for latitude, or 3-D variants.
    conf : object
        Configuration object.  Reads ``tracking_method``, ``name_longitude``,
        and ``name_latitude``.
    ellps : str, optional
        Ellipsoid identifier passed to :class:`pyproj.Geod`. Default ``"WGS84"``.
    time_dim : str or None, optional
        Override for the time dimension name.  When ``None``, ``"time"`` is used.
    lon_name : str or None, optional
        Override for the longitude variable name.  When ``None``, uses
        ``conf.name_longitude``.
    lat_name : str or None, optional
        Override for the latitude variable name.  When ``None``, uses
        ``conf.name_latitude``.
    cx_name : str, optional
        Name of the x-index variable in ``track_ds``. Default ``"cx"``.
    cy_name : str, optional
        Name of the y-index variable in ``track_ds``. Default ``"cy"``.
    min_step_m : float, optional
        Minimum step distance in metres below which the previous heading is
        reused. Default ``1.0``.

    Returns
    -------
    xr.Dataset
        Copy of ``track_ds`` with added variables:

        - ``lon(time)`` : centre longitude, degrees east.
        - ``lat(time)`` : centre latitude, degrees north.
        - ``heading_deg(time)`` : forward geodesic azimuth in degrees,
          clockwise from North; last value copied from previous step.
        - ``dist(time)`` : step distance in km; last value copied.
        - ``speed(time)`` : step speed in m s⁻¹; last value copied.

    Notes
    -----
    Returns ``track_ds`` unchanged when ``tracking_method == "fixed_box"``,
    when fewer than two time steps are present, or when required fields are
    missing from ``track_ds`` or ``ds_flat``.
    """

    tracking_method = str(getattr(conf, "tracking_method", "")).lower()
    if tracking_method == "fixed_box":
        return track_ds

    tdim = "time"
    lonv_name = lon_name or getattr(conf, "name_longitude", None)
    latv_name = lat_name or getattr(conf, "name_latitude", None)

    if lonv_name is None or latv_name is None:
        logger.warning("[track_kinematics] conf missing name_longitude/name_latitude, skip.")
        return track_ds

    if tdim not in track_ds.dims:
        logger.warning("[track_kinematics] track_ds missing time dim %r, skip.", tdim)
        return track_ds

    if (cx_name not in track_ds) or (cy_name not in track_ds):
        logger.warning("[track_kinematics] track_ds missing %r/%r, skip.", cx_name, cy_name)
        return track_ds

    if (lonv_name not in ds_flat) or (latv_name not in ds_flat):
        logger.warning(
            "[track_kinematics] ds_flat missing lon/lat (%s/%s), skip.", lonv_name, latv_name
        )
        return track_ds

    nt = int(track_ds.sizes.get(tdim, 0))
    if nt < 2:
        return track_ds

    lon_src = ds_flat[lonv_name]
    lat_src = ds_flat[latv_name]

    # Align lon/lat time axis to track time if present
    if tdim in lon_src.dims and tdim in track_ds.coords:
        try:
            lon_src = lon_src.sel({tdim: track_ds[tdim].values})
            lat_src = lat_src.sel({tdim: track_ds[tdim].values})
        except Exception:
            pass

    # Only time labels belong on positional indexers. Auxiliary coordinates
    # sampled by an earlier tracking stage can conflict with the source grid.
    cy = track_ds[cy_name].reset_coords(drop=True)
    cx = track_ds[cx_name].reset_coords(drop=True)

    # Identify spatial dims (excluding time)
    non_time_dims_lon = [d for d in lon_src.dims if d != tdim]
    non_time_dims_lat = [d for d in lat_src.dims if d != tdim]

    is_2d = len(non_time_dims_lon) >= 2 and len(non_time_dims_lat) >= 2
    is_1d = len(non_time_dims_lon) == 1 and len(non_time_dims_lat) == 1

    if is_2d:
        # Standard case: lon(y, x) and lat(y, x)
        ydim, xdim = non_time_dims_lon[-2], non_time_dims_lon[-1]
        try:
            lon_c = lon_src.isel({ydim: cy, xdim: cx})
            lat_c = lat_src.isel({ydim: cy, xdim: cx})
        except Exception as exc:
            logger.warning(
                "[track_kinematics] failed to sample lon/lat at (cy,cx) using (%s,%s): %s",
                ydim,
                xdim,
                exc,
            )
            return track_ds

    elif is_1d:
        # 1D case: lon(x) and lat(y), sampled independently
        xdim_lon = non_time_dims_lon[0]
        ydim_lat = non_time_dims_lat[0]
        try:
            lon_c = lon_src.isel({xdim_lon: cx})
            lat_c = lat_src.isel({ydim_lat: cy})
        except Exception as exc:
            logger.warning(
                "[track_kinematics] failed to sample 1D lon/lat at (cx=%s, cy=%s): %s",
                xdim_lon,
                ydim_lat,
                exc,
            )
            return track_ds

    else:
        logger.warning(
            "[track_kinematics] lon/lat have unexpected dimensions "
            "(lon dims=%s, lat dims=%s), expected 1D or 2D spatial fields, skip.",
            non_time_dims_lon,
            non_time_dims_lat,
        )
        return track_ds

    # Ensure lon_c/lat_c have time dimension (broadcast if lon/lat were time-invariant)
    if tdim not in lon_c.dims:
        lon_c = lon_c.expand_dims({tdim: track_ds[tdim]})
    if tdim not in lat_c.dims:
        lat_c = lat_c.expand_dims({tdim: track_ds[tdim]})

    lon_arr = np.asarray(lon_c.values, dtype=float)
    lat_arr = np.asarray(lat_c.values, dtype=float)

    geod = Geod(ellps=ellps)
    az12, _, dist_m = geod.inv(lon_arr[:-1], lat_arr[:-1], lon_arr[1:], lat_arr[1:])
    az12 = _norm_az_deg(np.asarray(az12, dtype=float))
    dist_m = np.asarray(dist_m, dtype=float)

    # dt in seconds
    tvals = track_ds[tdim].values.astype("datetime64[s]")
    dt_s = np.diff(tvals).astype("timedelta64[s]").astype(float)
    dt_s = np.where(dt_s > 0, dt_s, np.nan)

    speed = dist_m / dt_s

    heading_deg = np.full((nt,), np.nan, dtype=float)
    d_m = np.full((nt,), np.nan, dtype=float)
    speed_ms = np.full((nt,), np.nan, dtype=float)

    heading_deg[:-1] = az12
    d_m[:-1] = dist_m / 1e3
    speed_ms[:-1] = speed

    # Copy last
    heading_deg[-1] = heading_deg[-2]
    d_m[-1] = d_m[-2]
    speed_ms[-1] = speed_ms[-2]

    # Guard against near-stationary steps, keep previous heading when possible
    if min_step_m is not None and float(min_step_m) > 0.0:
        bad = d_m < float(min_step_m)
        if np.any(bad):
            for i in range(1, nt):
                if bad[i]:
                    heading_deg[i] = heading_deg[i - 1]

    out = track_ds.copy()
    # Vectorized sampling attaches source-grid positions as coordinates. Keep
    # the geographic values without leaking ni/nj or latitude/longitude(time)
    # into downstream selection indexers.
    out["lon"] = lon_c.astype(float).reset_coords(drop=True)
    out["lat"] = lat_c.astype(float).reset_coords(drop=True)
    out["heading_deg"] = xr.DataArray(heading_deg, dims=(tdim,))
    out["dist"] = xr.DataArray(d_m, dims=(tdim,))
    out["speed"] = xr.DataArray(speed_ms, dims=(tdim,))

    out["lon"].attrs.update(units="degrees_east", long_name="cyclone center longitude")
    out["lat"].attrs.update(units="degrees_north", long_name="cyclone center latitude")
    out["heading_deg"].attrs.update(
        units="degree", long_name="cyclone heading (azimuth, clockwise from north)"
    )
    out["dist"].attrs.update(units="km", long_name="step distance (forward)")
    out["speed"].attrs.update(units="m s-1", long_name="step speed (forward)")

    return out
