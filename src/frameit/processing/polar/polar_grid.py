# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging

import numpy as np
import xarray as xr
from pyproj import Geod

from frameit.processing.polar.sampling import (
    DEFAULT_MAX_POLAR_POINTS,
    check_point_budget,
    sampling_axes,
    uniform_periodic_angles,
    validate_axes,
    validate_sampling_options,
)

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
    - supplied continuous track centres override the extraction centre cell
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
        max_target_points: int = DEFAULT_MAX_POLAR_POINTS,
    ) -> None:
        """
        Parameters
        ----------
        r_km : array-like
            Finite, nonnegative, strictly increasing radial distances in
            kilometres. Must be 1D and non-empty.
        theta_deg : array-like
            Azimuths in degrees, clockwise from North, spanning [0, 360).
            Must be finite, strictly increasing, unique, 1D and non-empty.
            Nonuniform directions are supported as directional samples, not
            as a uniform ring for ordinary Fourier analysis.
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
        max_target_points : int, optional
            Allocation budget for the complete target grid across all times.
            Default 2,000,000. Checked before mesh/target-coordinate allocation.
        """
        self.r_km = np.asarray(r_km, dtype=float)
        self.theta_deg = np.asarray(theta_deg, dtype=float)

        self.tracking_method = str(tracking_method)
        self.time_dim = str(time_dim)
        self.lon_name = str(lon_name)
        self.lat_name = str(lat_name)

        self.center_x = int(center_x)
        self.center_y = int(center_y)

        validate_axes(self.r_km, self.theta_deg)
        validate_sampling_options(None, None, max_target_points)
        self.max_target_points = int(max_target_points)
        check_point_budget(self.r_km.size * self.theta_deg.size, self.max_target_points)
        self.sampling_metadata = {}

        self._geod = Geod(ellps=ellps)
        self.ellps = ellps

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
        """Build physical radii and an exactly periodic, endpoint-exclusive ring."""
        radius, angles, _ = sampling_axes(conf)
        return radius, angles

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
            is optional. ``polar_n_theta`` selects an explicit integer count;
            otherwise angular sampling targets the radial spacing at the outer
            ring. ``polar_max_points`` bounds geometry points across all times.
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

        r_km, theta_deg, metadata = sampling_axes(conf)

        logger.debug(
            "Creating PolarLonLatGrid from conf: tracking_method=%s, time_dim=%s,"
            " lon_name=%s, lat_name=%s, ellps=%s.",
            tracking_method,
            time_dim,
            lon_name,
            lat_name,
            ellps,
        )

        grid = cls(
            r_km=r_km,
            theta_deg=theta_deg,
            tracking_method=tracking_method,
            time_dim=time_dim,
            lon_name=lon_name,
            lat_name=lat_name,
            ellps=ellps,
            center_x=0,
            center_y=0,
            max_target_points=getattr(conf, "polar_max_points", DEFAULT_MAX_POLAR_POINTS),
        )
        grid.sampling_metadata = metadata
        return grid

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
        if track is not None:
            if "lon" not in track or "lat" not in track:
                raise ValueError("Polar track requires continuous lon(time) and lat(time)")
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
        check_point_budget(nt * nr * ntheta, self.max_target_points)

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

            lon2, lat2, back_azimuth = self._geod.fwd(
                np.full((nr, ntheta), lon_c),
                np.full((nr, ntheta), lat_c),
                AZ,
                dist_m,
            )
            lon2[self.r_km == 0] = lon_c
            lat2[self.r_km == 0] = lat_c
            lon_out = np.broadcast_to(lon2[None, :, :], (nt, nr, ntheta))
            lat_out = np.broadcast_to(lat2[None, :, :], (nt, nr, ntheta))
            bearing = np.deg2rad((back_azimuth + 180.0) % 360.0)
            bearing_out = np.broadcast_to(bearing[None, :, :], (nt, nr, ntheta)).copy()
            center_lon = np.full(nt, lon_c)
            center_lat = np.full(nt, lat_c)
        else:
            lon_out = np.empty((nt, nr, ntheta), dtype=float)
            lat_out = np.empty((nt, nr, ntheta), dtype=float)
            bearing_out = np.empty((nt, nr, ntheta), dtype=float)
            center_lon = np.empty(nt)
            center_lat = np.empty(nt)

            for it in range(nt):
                lon_c, lat_c = _center_as_float(it)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "time step %d/%d: center lon=%.6f, lat=%.6f.", it + 1, nt, lon_c, lat_c
                    )

                lon2, lat2, back_azimuth = self._geod.fwd(
                    np.full((nr, ntheta), lon_c),
                    np.full((nr, ntheta), lat_c),
                    AZ,
                    dist_m,
                )
                lon2[self.r_km == 0] = lon_c
                lat2[self.r_km == 0] = lat_c
                lon_out[it, :, :] = lon2
                lat_out[it, :, :] = lat2
                bearing_out[it] = np.deg2rad((back_azimuth + 180.0) % 360.0)
                center_lon[it], center_lat[it] = lon_c, lat_c

        bearing_out[:, self.r_km == 0, :] = np.nan
        # Do not carry scalar GRIB coordinates attached to the reference time
        # into geometry shared by unrelated vertical groups.
        time = xr.DataArray(time.values, dims=(self.time_dim,), name=self.time_dim)

        ds_polar = xr.Dataset(
            data_vars=dict(
                lon=((self.time_dim, "rr", "theta_deg"), lon_out),
                lat=((self.time_dim, "rr", "theta_deg"), lat_out),
                x_km=(("rr", "theta_deg"), self._x_km),
                y_km=(("rr", "theta_deg"), self._y_km),
            ),
            coords=dict(
                **{self.time_dim: time},
                rr=("rr", self.r_km),
                rr_km=("rr", self.r_km),
                theta_deg=("theta_deg", self.theta_deg),
                radial_bearing=((self.time_dim, "rr", "theta_deg"), bearing_out),
                center_lon=(self.time_dim, center_lon),
                center_lat=(self.time_dim, center_lat),
            ),
            attrs=dict(
                tracking_method=self.tracking_method,
                theta_convention="azimuth_clockwise_from_north",
                center_definition=(
                    "continuous_track" if track is not None
                    else f"(x_box={self.center_x}, y_box={self.center_y})"
                ),
                ellps=self.ellps,
                semi_major_axis_m=self._geod.a,
                inverse_flattening=1.0 / self._geod.f if self._geod.f else 0.0,
                polar_vector_origin_policy="undefined_radial_tangential_components",
            ),
        )
        ds_polar["radial_bearing"].attrs.update(
            units="rad", long_name="terminal-forward geodesic bearing clockwise from local north"
        )
        ds_polar["center_lon"].attrs.update(units="degrees_east")
        ds_polar["center_lat"].attrs.update(units="degrees_north")
        ds_polar.attrs.update(self.sampling_metadata)
        uniform = uniform_periodic_angles(self.theta_deg)
        ds_polar.attrs.update(
            theta_topology="uniform_periodic" if uniform else "directional_samples",
            n_theta=ntheta,
            theta_closed=False,
            radial_spacing_uniform=bool(
                nr < 3 or np.allclose(np.diff(self.r_km), np.diff(self.r_km)[0],
                                     rtol=1e-12, atol=0)
            ),
        )
        for name in ("rr", "rr_km"):
            ds_polar[name].attrs.update(units="km", long_name="radial distance from center")
        if uniform:
            ds_polar.attrs["effective_azimuthal_resolution_deg"] = 360.0 / ntheta
        ds_polar = ds_polar.assign_coords(
            radial_spacing_km=("rr", np.r_[np.diff(self.r_km), np.nan])
        )
        ds_polar["radial_spacing_km"].attrs.update(
            units="km", long_name="distance to the next radial sample (undefined at last radius)"
        )
        _, _, distances = self._geod.inv(
            lon_out, lat_out, np.roll(lon_out, -1, axis=-1), np.roll(lat_out, -1, axis=-1)
        )
        ds_polar = ds_polar.assign_coords(
            max_azimuthal_spacing_m=((self.time_dim, "rr"), distances.max(axis=-1))
        )
        ds_polar["max_azimuthal_spacing_m"].attrs.update(
            units="m", long_name="maximum geodesic distance between cyclic neighbour samples"
        )
        if "x_box" in ds_surface.dims and "y_box" in ds_surface.dims and (
            self.center_x in ds_surface.x_box.values and self.center_y in ds_surface.y_box.values
        ):
            box_lon, box_lat = self._get_center_lonlat(ds_surface)
            _, _, offset = self._geod.inv(
                np.broadcast_to(box_lon.values, (nt,)),
                np.broadcast_to(box_lat.values, (nt,)),
                center_lon, center_lat,
            )
            ds_polar = ds_polar.assign_coords(center_grid_offset_m=(self.time_dim, offset))
            ds_polar["center_grid_offset_m"].attrs.update(
                units="m", long_name="distance between polar origin and extraction centre cell"
            )

        logger.debug(
            "Polar grid built: lon shape=%s, lat shape=%s, x_km shape=%s, y_km shape=%s.",
            ds_polar["lon"].shape,
            ds_polar["lat"].shape,
            ds_polar["x_km"].shape,
            ds_polar["y_km"].shape,
        )

        return ds_polar
