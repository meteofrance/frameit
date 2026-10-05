# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

# --- Imports ---
import logging
from collections.abc import Sequence
from typing import ClassVar

import numpy as np
import xarray as xr

from frameit.core.settings_class import SimulationConfig

from .tracker_core import TcTracker, nearest_grid_point, register_tracker

logger = logging.getLogger(__name__)


def _window(center: int, half: int, size: int) -> slice:
    """
    Index slice of half-width ``half`` around ``center``, clipped to ``[0, size)``.

    Parameters
    ----------
    center : int
        Central index.
    half : int
        Half-width in grid points.
    size : int
        Axis length.

    Returns
    -------
    slice
        Clipped slice ``[max(0, center - half), min(size - 1, center + half)]``.
    """
    return slice(max(0, center - half), min(size - 1, center + half) + 1)


def _argmin_around(
    field: xr.DataArray,
    center: tuple[int, int] | None,
    half: int,
    ydim: str,
    xdim: str,
) -> tuple[int, int]:
    """
    Grid indices of the minimum of a 2-D field, searched around a centre.

    Parameters
    ----------
    field : xr.DataArray
        Field at one time step, with dimensions ``ydim`` and ``xdim``.
    center : tuple of int or None
        ``(j, i)`` centre of the search window. ``None`` searches the
        full domain.
    half : int
        Half-width of the search window in grid points.
    ydim, xdim : str
        Names of the y and x dimensions.

    Returns
    -------
    tuple of int
        ``(j, i)`` indices of the minimum in the full-domain frame. The full
        domain is searched if the window holds only missing values.
    """
    if center is not None:
        ys = _window(center[0], half, field.sizes[ydim])
        xs = _window(center[1], half, field.sizes[xdim])
        sub = field.isel({ydim: ys, xdim: xs})
        if not bool(sub.isnull().all()):
            idx = sub.argmin(dim=[ydim, xdim])
            return ys.start + int(idx[ydim]), xs.start + int(idx[xdim])

    idx = field.argmin(dim=[ydim, xdim])
    return int(idx[ydim]), int(idx[xdim])


def _locate_center(
    mslp_t: xr.DataArray,
    wind_t: xr.DataArray,
    guess: tuple[int, int] | None,
    half_search: int,
    half_refine: int,
    ydim: str,
    xdim: str,
) -> tuple[int, int]:
    """
    Locate the cyclone centre at one time step.

    The MSLP minimum is searched within ``half_search`` of ``guess`` (full
    domain if ``guess`` is ``None``). The 10 m wind-speed minimum is then
    searched within ``half_refine`` of that MSLP minimum.

    Parameters
    ----------
    mslp_t : xr.DataArray
        Mean sea-level pressure at one time step.
    wind_t : xr.DataArray
        10 m wind speed at the same time step.
    guess : tuple of int or None
        ``(j, i)`` first guess, typically the previous centre.
    half_search, half_refine : int
        Half-widths of the MSLP search and wind refinement windows, in grid
        points.
    ydim, xdim : str
        Names of the y and x dimensions.

    Returns
    -------
    tuple of int
        ``(j, i)`` indices of the cyclone centre.
    """
    mslp_min = _argmin_around(mslp_t, guess, half_search, ydim, xdim)
    return _argmin_around(wind_t, mslp_min, half_refine, ydim, xdim)


def pressure_wind_tracker(
    mslp: xr.DataArray,
    zonal_10m: xr.DataArray,
    merid_10m: xr.DataArray,
    *,
    time_dim: str = "time",
    half_search: int,
    half_refine: int,
    first_guess: tuple[int, int] | None = None,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Sequential cyclone-centre tracker using MSLP and 10 m wind.

    At each time step, the MSLP minimum is searched within ``±half_search``
    grid points of a guess, then refined by the 10 m wind-speed minimum
    within ``±half_refine`` grid points. The guess is the previous centre for
    ``t ≥ 1``. At ``t = 0``, it is ``first_guess`` if given; otherwise the
    MSLP minimum is searched over the full domain.

    Parameters
    ----------
    mslp : xr.DataArray
        Mean sea-level pressure, shape ``(time, ..., y, x)``.
    zonal_10m : xr.DataArray
        10 m zonal wind component, same shape and dimensions as ``mslp``.
    merid_10m : xr.DataArray
        10 m meridional wind component, same shape and dimensions as ``mslp``.
    time_dim : str, optional
        Name of the time dimension. Default ``"time"``.
    half_search : int
        Half-width of the MSLP search box in grid points (≥ 1).
    half_refine : int
        Half-width of the wind refinement box in grid points (≥ 1).
    first_guess : tuple of int, optional
        ``(j, i)`` grid indices of the first guess at ``t = 0``. Default
        ``None`` (global MSLP minimum).

    Returns
    -------
    cy : xr.DataArray
        Latitudinal (y) grid-point index of the cyclone centre, shape ``(time,)``.
    cx : xr.DataArray
        Longitudinal (x) grid-point index of the cyclone centre, shape ``(time,)``.

    Raises
    ------
    ValueError
        If ``mslp``, ``zonal_10m``, and ``merid_10m`` do not share the same
        dimensions, if ``time_dim`` is absent, if ``half_search`` or
        ``half_refine`` is less than 1, or if ``first_guess`` lies outside
        the grid.
    """
    xdim, ydim = mslp.dims[-1], mslp.dims[-2]

    if mslp.dims != zonal_10m.dims or mslp.dims != merid_10m.dims:
        raise ValueError("mslp, zonal_10m and merid_10m must have the same dimensions")

    if time_dim not in mslp.dims:
        raise ValueError(f"Time dimension '{time_dim}' not found in mslp")

    half_search = int(half_search)
    half_refine = int(half_refine)
    if half_search < 1 or half_refine < 1:
        raise ValueError("half_search and half_refine must be >= 1")

    if first_guess is not None:
        j0, i0 = (int(k) for k in first_guess)
        if not (0 <= j0 < mslp.sizes[ydim] and 0 <= i0 < mslp.sizes[xdim]):
            raise ValueError(f"first_guess {first_guess} lies outside the grid")
        first_guess = (j0, i0)

    nt = mslp.sizes[time_dim]
    wind_10m = np.hypot(zonal_10m, merid_10m)

    cy = np.empty(nt, dtype=np.int64)
    cx = np.empty(nt, dtype=np.int64)

    # Sequential tracking: each centre is the guess for the next time step
    center = first_guess
    for it in range(nt):
        center = _locate_center(
            mslp.isel({time_dim: it}),
            wind_10m.isel({time_dim: it}),
            center,
            half_search,
            half_refine,
            ydim,
            xdim,
        )
        cy[it], cx[it] = center

    coords = {time_dim: mslp[time_dim]}
    return (
        xr.DataArray(cy, dims=(time_dim,), coords=coords),
        xr.DataArray(cx, dims=(time_dim,), coords=coords),
    )


@register_tracker
class PressureWindTracker(TcTracker):
    name = "wind_pressure"
    logical_fields = ("mslp", "u10m", "v10m")

    SEARCH_RADIUS_KM: ClassVar[float] = 100.0
    REFINE_RADIUS_KM: ClassVar[float] = 50.0
    # Maximum distance between the first guess and the nearest grid point,
    # in grid spacings. Beyond it, the first guess lies outside the domain.
    FIRST_GUESS_TOLERANCE: ClassVar[float] = 1.0

    def __init__(
        self,
        var_aliases,
        resolution_km: float,
        *,
        first_guess: Sequence[float] | None = None,
        lat_name: str = "latitude",
        lon_name: str = "longitude",
    ):
        """
        Parameters
        ----------
        var_aliases : Mapping[str, str]
            Variable alias mapping (logical name → native name in dataset).
        resolution_km : float
            Model grid spacing in **metres** (converted internally to km).
            Used to derive ``half_search`` and ``half_refine`` in grid points.
        first_guess : Sequence[float], optional
            ``[lat0, lon0]`` first guess of the centre at the first output
            time, in degrees. Default ``None`` (global MSLP minimum).
        lat_name : str, optional
            Name of the latitude coordinate in the tracking dataset.
            Default ``"latitude"``.
        lon_name : str, optional
            Name of the longitude coordinate in the tracking dataset.
            Default ``"longitude"``.
        """
        super().__init__(var_aliases=var_aliases)

        self.resolution_m = float(resolution_km)
        self.resolution_km = self.resolution_m / 1000.0

        half_search = int(np.ceil(self.SEARCH_RADIUS_KM / self.resolution_km))
        half_refine = int(np.ceil(self.REFINE_RADIUS_KM / self.resolution_km))

        self.half_search_indices = max(1, half_search)
        self.half_refine_indices = max(1, half_refine)

        self.first_guess = None if first_guess is None else tuple(map(float, first_guess))
        self.lat_name = lat_name
        self.lon_name = lon_name

    @classmethod
    def from_config(cls, conf: SimulationConfig) -> "PressureWindTracker":
        """
        Build a :class:`PressureWindTracker` from a simulation configuration.

        Parameters
        ----------
        conf : SimulationConfig
            Configuration object.  Reads ``tracking_var_aliases``,
            ``resolution`` (grid spacing in metres), and optionally
            ``tracking_first_guess``, ``name_latitude`` and ``name_longitude``.

        Returns
        -------
        PressureWindTracker
        """
        var_aliases = getattr(conf, "tracking_var_aliases", {}) or {}
        resolution_km = conf.resolution  # in metres; converted to km below
        return cls(
            var_aliases=var_aliases,
            resolution_km=resolution_km,
            first_guess=getattr(conf, "tracking_first_guess", None),
            lat_name=getattr(conf, "name_latitude", None) or "latitude",
            lon_name=getattr(conf, "name_longitude", None) or "longitude",
        )

    def _first_guess_indices(self, ds: xr.Dataset) -> tuple[int, int]:
        """
        Convert the geographic first guess into grid indices.

        Parameters
        ----------
        ds : xr.Dataset
            Flat tracking dataset holding the latitude and longitude
            coordinates.

        Returns
        -------
        tuple of int
            ``(j, i)`` indices of the grid point closest to the first guess.

        Raises
        ------
        ValueError
            If the coordinates are missing, or if the first guess is farther
            than ``FIRST_GUESS_TOLERANCE`` grid spacings from the nearest grid
            point, i.e. outside the model domain.
        """
        if self.lat_name not in ds.coords or self.lon_name not in ds.coords:
            raise ValueError(
                f"{self.name}: coordinates {self.lat_name!r} or {self.lon_name!r} "
                "not found in Dataset, required to use tracking_first_guess"
            )

        lat0, lon0 = self.first_guess
        j, i, dist_m = nearest_grid_point(ds[self.lat_name], ds[self.lon_name], lat0, lon0)

        if dist_m > self.FIRST_GUESS_TOLERANCE * self.resolution_m:
            raise ValueError(
                f"{self.name}: tracking_first_guess [{lat0}, {lon0}] lies outside the "
                f"model domain (nearest grid point at {dist_m / 1000.0:.1f} km)"
            )

        logger.info(
            "%s: first guess [%.2f, %.2f] mapped to grid point (j=%d, i=%d)",
            self.name,
            lat0,
            lon0,
            j,
            i,
        )
        return j, i

    def _track_method(self, ds: xr.Dataset) -> xr.Dataset:
        """
        Apply :func:`pressure_wind_tracker` to the flat dataset.

        Parameters
        ----------
        ds : xr.Dataset
            Flat tracking dataset.  Must contain the fields aliased to
            ``"mslp"``, ``"u10m"``, and ``"v10m"``, and the latitude and
            longitude coordinates if a first guess is set.

        Returns
        -------
        xr.Dataset
            Dataset with variables ``cy(time)`` and ``cx(time)``.
        """
        mslp = self._field(ds, "mslp")
        u10 = self._field(ds, "u10m")
        v10 = self._field(ds, "v10m")

        first_guess = None if self.first_guess is None else self._first_guess_indices(ds)

        cy, cx = pressure_wind_tracker(
            mslp=mslp,
            zonal_10m=u10,
            merid_10m=v10,
            time_dim="time",
            half_search=self.half_search_indices,
            half_refine=self.half_refine_indices,
            first_guess=first_guess,
        )

        return xr.Dataset({"cy": cy, "cx": cx})
