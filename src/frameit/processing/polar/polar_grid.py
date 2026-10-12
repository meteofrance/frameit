# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging

import numpy as np
import xarray as xr
from pyproj import Geod

logger = logging.getLogger(__name__)


class PolarLonLatGrid:
    """
    Step 2, build a polar target grid in lon, lat using geodesic forward mapping.

    This class has two responsibilities:
      1) Define the polar sampling axes (r_km, theta_deg) from the configuration,
         including fallbacks when dtheta is not provided.
      2) Convert (r_km, theta_deg) into (lon, lat) around the box center (x_box=0, y_box=0),
         for each time step (or broadcast in fixed_box mode).

    Conventions
    -----------
    - theta_deg is a geodesic azimuth in degrees, clockwise from North:
        0: North, 90: East, 180: South, 270: West
    - center is always (x_box=0, y_box=0)
    """

    def __init__(
        self,
        *,
        r_km: np.ndarray,
        theta_deg: np.ndarray,
        tracking_method: str,
        time_dim: str,
        lon_name: str,
        lat_name: str,
        ellps: str = "WGS84",
        center_x: int = 0,
        center_y: int = 0,
    ) -> None:
        """
        Parameters
        ----------
        r_km : array-like
            Radial distances in kilometres.  Must be 1D and non-empty.
        theta_deg : array-like
            Azimuths in degrees, clockwise from North, spanning [0, 360).
            Must be 1D and non-empty.
        tracking_method : str
            Tracking method name (e.g. "wind_pressure", "fixed_box").
            "fixed_box" uses the first time step's center for all times.
        time_dim : str
            Name of the time dimension in the source datasets.
        lon_name : str
            Name of the longitude coordinate in the source datasets.
        lat_name : str
            Name of the latitude coordinate in the source datasets.
        ellps : str, optional
            Ellipsoid identifier passed to :class:`pyproj.Geod`. Default "WGS84".
        center_x : int, optional
            x_box index of the cyclone centre (usually 0). Default 0.
        center_y : int, optional
            y_box index of the cyclone centre (usually 0). Default 0.
        """
        self.r_km = np.asarray(r_km, dtype=float)
        self.theta_deg = np.asarray(theta_deg, dtype=float)

        self.tracking_method = str(tracking_method)
        self.time_dim = str(time_dim)
        self.lon_name = str(lon_name)
        self.lat_name = str(lat_name)

        self.center_x = int(center_x)
        self.center_y = int(center_y)

        if self.r_km.ndim != 1 or self.r_km.size == 0:
            raise ValueError("r_km must be a non-empty 1D array.")
        if self.theta_deg.ndim != 1 or self.theta_deg.size == 0:
            raise ValueError("theta_deg must be a non-empty 1D array.")

        self._geod = Geod(ellps=ellps)

        # Invariant polar mesh (nr, ntheta)
        AZ, RR = np.meshgrid(self.theta_deg, self.r_km, indexing="xy")
        self._AZ_deg = AZ
        self._dist_m = RR * 1000.0

        # Local cartesian diagnostics (East, North), useful later for radial/tangential transforms
        az_rad = np.deg2rad(AZ)
        self._x_km = RR * np.sin(az_rad)
        self._y_km = RR * np.cos(az_rad)

        logger.debug(
            "PolarLonLatGrid initialized: tracking_method=%s, time_dim=%s,"
            " lon_name=%s, lat_name=%s, center=(%d,%d),"
            " nr=%d, ntheta=%d, rmax_km=%.3f, dtheta_deg=%.3f.",
            self.tracking_method,
            self.time_dim,
            self.lon_name,
            self.lat_name,
            self.center_x,
            self.center_y,
            int(self.r_km.size),
            int(self.theta_deg.size),
            float(np.nanmax(self.r_km)),
            float(self.theta_deg[1] - self.theta_deg[0])
            if self.theta_deg.size > 1
            else float("nan"),
        )

    @staticmethod
    def _require(conf, name: str):
        if not hasattr(conf, name):
            raise AttributeError(f"Missing conf attribute: {name!r}")
        return getattr(conf, name)

    @staticmethod
    def _build_axes_from_conf(conf) -> tuple[np.ndarray, np.ndarray]:
        """
        Build r_km and theta_deg from conf.

        Required:
          - x_boxsize_km, y_boxsize_km
          - radial_resolution (m) or resolution (m)

        Optional:
          - azimuthal_resolution (deg), if absent use:
                dtheta_rad ≈ dr_km / rmax_km
            with safeguards and rounding.

        Notes
        -----
        - rmax_km = 0.5 * min(x_boxsize_km, y_boxsize_km)
        - r_km includes rmax_km (last point forced if needed)
        - theta_deg spans [0, 360) with step dtheta_deg
        """
        xsz = float(PolarLonLatGrid._require(conf, "x_boxsize_km"))
        ysz = float(PolarLonLatGrid._require(conf, "y_boxsize_km"))
        if xsz <= 0.0 or ysz <= 0.0:
            raise ValueError("x_boxsize_km and y_boxsize_km must be positive.")
        rmax_km = 0.5 * min(xsz, ysz)

        dr_m = getattr(conf, "radial_resolution", None)
        if dr_m is None:
            dr_m = getattr(conf, "resolution", None)
        if dr_m is None:
            raise ValueError("Need conf.radial_resolution (m) or conf.resolution (m).")

        dr_km = float(dr_m) / 1000.0
        if dr_km <= 0.0:
            raise ValueError("radial_resolution (or resolution) must be positive.")

        dtheta_deg = getattr(conf, "azimuthal_resolution", None)
        inferred = False
        if dtheta_deg is None:
            dtheta_rad = dr_km / max(rmax_km, 1e-12)
            dtheta_deg = float(np.rad2deg(dtheta_rad))
            dtheta_deg = max(dtheta_deg, 1.0)
            dtheta_deg = round(dtheta_deg, 1)
            inferred = True

        dtheta_deg = float(dtheta_deg)
        if dtheta_deg <= 0.0:
            raise ValueError("azimuthal_resolution must be positive.")

        # r axis, enforce inclusion of rmax_km
        n = int(np.floor(rmax_km / dr_km))
        r_km = np.arange(n + 1, dtype=float) * dr_km
        if r_km.size == 0:
            r_km = np.array([0.0, rmax_km], dtype=float)
        elif abs(r_km[-1] - rmax_km) > 1e-9:
            if r_km[-1] < rmax_km:
                r_km = np.append(r_km, rmax_km)

        # theta axis
        theta_deg = np.arange(0.0, 360.0, dtheta_deg, dtype=float)
        if theta_deg.size == 0:
            theta_deg = np.array([0.0], dtype=float)

        logger.debug(
            "Built polar axes from conf: x_boxsize_km=%.3f, y_boxsize_km=%.3f,"
            " rmax_km=%.3f, dr_km=%.6f, dtheta_deg=%.3f (inferred=%s), nr=%d, ntheta=%d.",
            xsz,
            ysz,
            rmax_km,
            dr_km,
            dtheta_deg,
            bool(inferred),
            int(r_km.size),
            int(theta_deg.size),
        )

        return r_km, theta_deg

    @classmethod
    def from_conf(cls, conf, *, ellps: str = "WGS84") -> PolarLonLatGrid:
        """
        Construct a :class:`PolarLonLatGrid` from a simulation configuration.

        Parameters
        ----------
        conf : object
            Configuration object.  Required attributes: ``tracking_method``,
            ``name_longitude``, ``name_latitude``, ``x_boxsize_km``,
            ``y_boxsize_km``.  Either ``radial_resolution`` (m) or
            ``resolution`` (m) must be set.  ``azimuthal_resolution`` (deg)
            is optional.
        ellps : str, optional
            Ellipsoid identifier. Default "WGS84".

        Returns
        -------
        PolarLonLatGrid
            Initialized grid with center fixed at ``(x_box=0, y_box=0)``.
        """
        tracking_method = str(cls._require(conf, "tracking_method"))
        time_dim = "time"
        lon_name = str(cls._require(conf, "name_longitude"))
        lat_name = str(cls._require(conf, "name_latitude"))

        r_km, theta_deg = cls._build_axes_from_conf(conf)

        logger.debug(
            "Creating PolarLonLatGrid from conf: tracking_method=%s, time_dim=%s,"
            " lon_name=%s, lat_name=%s, ellps=%s.",
            tracking_method,
            time_dim,
            lon_name,
            lat_name,
            ellps,
        )

        return cls(
            r_km=r_km,
            theta_deg=theta_deg,
            tracking_method=tracking_method,
            time_dim=time_dim,
            lon_name=lon_name,
            lat_name=lat_name,
            ellps=ellps,
            center_x=0,
            center_y=0,
        )

    def _get_center_lonlat(self, ds_surface: xr.Dataset) -> tuple[xr.DataArray, xr.DataArray]:
        """
        Extract center lon/lat at ``(x_box=center_x, y_box=center_y)``.

        Parameters
        ----------
        ds_surface : xr.Dataset
            Surface-level extracted dataset containing longitude and latitude
            coordinates on the ``(x_box, y_box)`` grid.

        Returns
        -------
        lon0 : xr.DataArray
            Longitude of the cyclone center, shape ``(time,)`` or scalar.
        lat0 : xr.DataArray
            Latitude of the cyclone center, shape ``(time,)`` or scalar.
        """
        lon0 = ds_surface[self.lon_name].sel(x_box=self.center_x, y_box=self.center_y)
        lat0 = ds_surface[self.lat_name].sel(x_box=self.center_x, y_box=self.center_y)

        if logger.isEnabledFor(logging.DEBUG):
            lon_vals = np.asarray(lon0.values)
            lat_vals = np.asarray(lat0.values)
            logger.debug(
                "Center lon/lat extracted at (x_box=%d, y_box=%d). lon dims=%s, lat dims=%s, "
                "lon finite=%s, lat finite=%s.",
                self.center_x,
                self.center_y,
                lon0.dims,
                lat0.dims,
                bool(np.isfinite(lon_vals).all()),
                bool(np.isfinite(lat_vals).all()),
            )

        return lon0, lat0

    def build(self, ds_surface: xr.Dataset, *, track: xr.Dataset | None = None) -> xr.Dataset:
        """
        Compute the polar lon/lat grid for all time steps in ``ds_surface``.

        Parameters
        ----------
        ds_surface : xr.Dataset
            Surface-level dataset used to retrieve the time axis and the
            cyclone center coordinates.
        track : xr.Dataset or None, optional
            Continuous lon(time)/lat(time) centres, overriding the box centre.

        Returns
        -------
        xr.Dataset
            Dataset with variables:

            - ``lon(time, rr, theta_deg)``: polar grid longitude, degrees east.
            - ``lat(time, rr, theta_deg)``: polar grid latitude, degrees north.
            - ``x_km(rr, theta_deg)``: local Easting offset, km.
            - ``y_km(rr, theta_deg)``: local Northing offset, km.

            And coordinates ``rr_km`` (on dim "rr") and ``theta_deg``.

        Notes
        -----
        When ``tracking_method == "fixed_box"``, the center is taken at ``t=0``
        and broadcast to all time steps, producing a static polar grid.
        """
        if track is not None and "lon" in track and "lat" in track:
            selected = track.sel({self.time_dim: ds_surface[self.time_dim]})
            lon0, lat0 = selected["lon"], selected["lat"]
            if lon0.dims != (self.time_dim,) or lat0.dims != (self.time_dim,):
                raise ValueError("Polar track centres must have dimensions (time,)")
            if not (np.isfinite(lon0.values).all() and np.isfinite(lat0.values).all()):
                raise ValueError("Polar track centres must be finite")
        else:
            lon0, lat0 = self._get_center_lonlat(ds_surface)

        # Determine time axis
        if self.time_dim in ds_surface.dims or self.time_dim in ds_surface.coords:
            time = ds_surface[self.time_dim]
            nt = int(time.size)
            logger.debug("Time axis found in ds_surface: time_dim=%s, nt=%d.", self.time_dim, nt)
        else:
            time = xr.DataArray(
                [np.datetime64("1970-01-01")], dims=(self.time_dim,), name=self.time_dim
            )
            nt = 1
            logger.debug("Time axis missing in ds_surface. Using synthetic time with nt=1.")

        nr = int(self.r_km.size)
        ntheta = int(self.theta_deg.size)

        AZ = self._AZ_deg
        dist_m = self._dist_m

        logger.debug(
            "Building polar lon/lat: tracking_method=%s, nt=%d, nr=%d, ntheta=%d.",
            self.tracking_method,
            nt,
            nr,
            ntheta,
        )

        def _center_as_float(it: int) -> tuple[float, float]:
            if self.time_dim in lon0.dims:
                return float(lon0.isel({self.time_dim: it}).values), float(
                    lat0.isel({self.time_dim: it}).values
                )
            return float(lon0.values), float(lat0.values)

        if self.tracking_method == "fixed_box":
            lon_c, lat_c = _center_as_float(0)
            logger.debug(
                "fixed_box mode: using center from it=0: lon=%.6f, lat=%.6f.", lon_c, lat_c
            )

            lon2, lat2, _ = self._geod.fwd(
                np.full((nr, ntheta), lon_c),
                np.full((nr, ntheta), lat_c),
                AZ,
                dist_m,
            )
            lon_out = np.broadcast_to(lon2[None, :, :], (nt, nr, ntheta))
            lat_out = np.broadcast_to(lat2[None, :, :], (nt, nr, ntheta))
        else:
            lon_out = np.empty((nt, nr, ntheta), dtype=float)
            lat_out = np.empty((nt, nr, ntheta), dtype=float)

            for it in range(nt):
                lon_c, lat_c = _center_as_float(it)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "time step %d/%d: center lon=%.6f, lat=%.6f.", it + 1, nt, lon_c, lat_c
                    )

                lon2, lat2, _ = self._geod.fwd(
                    np.full((nr, ntheta), lon_c),
                    np.full((nr, ntheta), lat_c),
                    AZ,
                    dist_m,
                )
                lon_out[it, :, :] = lon2
                lat_out[it, :, :] = lat2

        ds_polar = xr.Dataset(
            data_vars=dict(
                lon=((self.time_dim, "rr", "theta_deg"), lon_out),
                lat=((self.time_dim, "rr", "theta_deg"), lat_out),
                x_km=(("rr", "theta_deg"), self._x_km),
                y_km=(("rr", "theta_deg"), self._y_km),
            ),
            coords=dict(
                **{self.time_dim: time},
                rr_km=("rr", self.r_km),
                theta_deg=("theta_deg", self.theta_deg),
            ),
            attrs=dict(
                tracking_method=self.tracking_method,
                theta_convention="azimuth_clockwise_from_north",
                center_definition=f"(x_box={self.center_x}, y_box={self.center_y})",
                ellps="WGS84",
            ),
        )

        logger.debug(
            "Polar grid built: lon shape=%s, lat shape=%s, x_km shape=%s, y_km shape=%s.",
            ds_polar["lon"].shape,
            ds_polar["lat"].shape,
            ds_polar["x_km"].shape,
            ds_polar["y_km"].shape,
        )

        return ds_polar
