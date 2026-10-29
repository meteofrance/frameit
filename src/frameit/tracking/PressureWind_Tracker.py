# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

# --- Imports ---
from typing import ClassVar

import numpy as np
import xarray as xr

from frameit.core.settings_class import SimulationConfig

from .tracker_core import TcTracker, register_tracker


def pressure_wind_tracker(
    mslp: xr.DataArray,
    zonal_10m: xr.DataArray,
    merid_10m: xr.DataArray,
    *,
    time_dim: str = "time",
    half_search: int,
    half_refine: int,
    initial_mask: xr.DataArray | None = None,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Sequential cyclone-centre tracker using MSLP and 10 m wind.

    At ``t = 0``: global MSLP minimum, refined by the 10 m wind minimum
    within ``±half_refine`` grid points.

    At ``t ≥ 1``: MSLP minimum within ``±half_search`` around the previous
    centre (first guess), refined by the wind minimum within ``±half_refine``.

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
    initial_mask : xr.DataArray, optional
        First-time pressure candidates. No finite candidate is an error; wind
        refinement remains unconstrained by this mask. Omit for a global search.

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
        dimensions, if ``time_dim`` is absent, or if ``half_search`` or
        ``half_refine`` is less than 1.
    """

    from frameit.utils.units import convert_units

    # Unitless direct numerical inputs follow the documented m/s contract.
    zonal_10m = convert_units(zonal_10m, "velocity", assumed="m s-1")
    merid_10m = convert_units(merid_10m, "velocity", assumed="m s-1")
    mslp, zonal_10m, merid_10m = xr.align(mslp, zonal_10m, merid_10m, join="exact")

    nix, njy = mslp.dims[-1], mslp.dims[-2]
    ny = mslp.sizes[njy]
    nx = mslp.sizes[nix]

    if mslp.dims != zonal_10m.dims or mslp.dims != merid_10m.dims:
        raise ValueError("mslp, zonal_10m and merid_10m must have the same dimensions")

    if time_dim not in mslp.dims:
        raise ValueError(f"Time dimension '{time_dim}' not found in mslp")

    half_search = int(half_search)
    half_refine = int(half_refine)
    if half_search < 1 or half_refine < 1:
        raise ValueError("half_search and half_refine must be >= 1")

    nt = mslp.sizes[time_dim]
    time_coord = mslp[time_dim]

    cy = xr.DataArray(
        np.full(nt, np.nan, dtype=np.float64),
        dims=(time_dim,),
        coords={time_dim: time_coord},
    )
    cx = xr.DataArray(
        np.full(nt, np.nan, dtype=np.float64),
        dims=(time_dim,),
        coords={time_dim: time_coord},
    )

    wind_10m = np.hypot(zonal_10m, merid_10m)

    # ------------------------------------------------------------------
    # t = 0: global MSLP minimum then wind refinement over +/-half_refine
    # ------------------------------------------------------------------
    mslp0 = mslp.isel({time_dim: 0})
    wind0 = wind_10m.isel({time_dim: 0})
    if initial_mask is not None:
        if initial_mask.dims != mslp0.dims or initial_mask.shape != mslp0.shape:
            raise ValueError("Initial search mask must match the horizontal pressure grid")
        mslp0 = mslp0.where(initial_mask & np.isfinite(mslp0))
        if not bool(np.isfinite(mslp0).any()):
            raise ValueError("wind_pressure initial guess search circle contains no finite MSLP; "
                             "check seed position, radius and input coverage")

    idx_mslp0 = mslp0.argmin(dim=[njy, nix])
    cy0_fg = int(idx_mslp0[njy])
    cx0_fg = int(idx_mslp0[nix])

    y_min0 = max(0, cy0_fg - half_refine)
    y_max0 = min(ny - 1, cy0_fg + half_refine)
    x_min0 = max(0, cx0_fg - half_refine)
    x_max0 = min(nx - 1, cx0_fg + half_refine)

    wind0_sub = wind0.isel(
        {
            njy: slice(y_min0, y_max0 + 1),
            nix: slice(x_min0, x_max0 + 1),
        }
    )

    if bool(wind0_sub.isnull().all()):
        idx_wind0 = wind0.argmin(dim=[njy, nix])
        cy0 = int(idx_wind0[njy])
        cx0 = int(idx_wind0[nix])
    else:
        idx_wind0 = wind0_sub.argmin(dim=[njy, nix])
        cy0_rel = int(idx_wind0[njy])
        cx0_rel = int(idx_wind0[nix])
        cy0 = y_min0 + cy0_rel
        cx0 = x_min0 + cx0_rel

    cy.loc[{time_dim: time_coord[0]}] = cy0
    cx.loc[{time_dim: time_coord[0]}] = cx0
    cy_prev, cx_prev = cy0, cx0

    # ------------------------------------------------------------------
    # t >= 1: MSLP search over +/-half_search, wind refinement over +/-half_refine
    # ------------------------------------------------------------------
    for it in range(1, nt):
        t_val = time_coord[it]

        mslp_t = mslp.isel({time_dim: it})
        wind_t = wind_10m.isel({time_dim: it})

        # 1) MSLP search box around the previous centre
        y_min = max(0, cy_prev - half_search)
        y_max = min(ny - 1, cy_prev + half_search)
        x_min = max(0, cx_prev - half_search)
        x_max = min(nx - 1, cx_prev + half_search)

        mslp_sub = mslp_t.isel(
            {
                njy: slice(y_min, y_max + 1),
                nix: slice(x_min, x_max + 1),
            }
        )

        # 2) MSLP first guess (local, or global if all NaN)
        if bool(mslp_sub.isnull().all()):
            idx_mslp = mslp_t.argmin(dim=[njy, nix])
            cy_fg = int(idx_mslp[njy])
            cx_fg = int(idx_mslp[nix])
        else:
            idx_mslp = mslp_sub.argmin(dim=[njy, nix])
            cy_rel = int(idx_mslp[njy])
            cx_rel = int(idx_mslp[nix])
            cy_fg = y_min + cy_rel
            cx_fg = x_min + cx_rel

        # 3) wind refinement around the first guess (box +/-half_refine)
        y2_min = max(0, cy_fg - half_refine)
        y2_max = min(ny - 1, cy_fg + half_refine)
        x2_min = max(0, cx_fg - half_refine)
        x2_max = min(nx - 1, cx_fg + half_refine)

        wind_sub = wind_t.isel(
            {
                njy: slice(y2_min, y2_max + 1),
                nix: slice(x2_min, x2_max + 1),
            }
        )

        if bool(wind_sub.isnull().all()):
            idx_wind = wind_t.argmin(dim=[njy, nix])
            cy_new = int(idx_wind[njy])
            cx_new = int(idx_wind[nix])
        else:
            idx_wind = wind_sub.argmin(dim=[njy, nix])
            cy_rel = int(idx_wind[njy])
            cx_rel = int(idx_wind[nix])
            cy_new = y2_min + cy_rel
            cx_new = x2_min + cx_rel

        cy.loc[{time_dim: t_val}] = cy_new
        cx.loc[{time_dim: t_val}] = cx_new
        cy_prev, cx_prev = cy_new, cx_new

    return cy.astype(int), cx.astype(int)


@register_tracker
class PressureWindTracker(TcTracker):
    name = "wind_pressure"
    required_fields = ("prmsl", "u10", "v10")

    SEARCH_RADIUS_KM: ClassVar[float] = 100.0
    REFINE_RADIUS_KM: ClassVar[float] = 50.0

    def __init__(
        self, var_aliases, grid_spacing_m: float | None = None, *,
        search_half_width_km=100., refine_half_width_km=50., resolution_km=None,
        initial_guess=None, lat_name="latitude", lon_name="longitude",
    ):
        """
        Parameters
        ----------
        var_aliases : Mapping[str, str]
            Variable alias mapping (logical name → native name in dataset).
        grid_spacing_m : float
            Model grid spacing in **metres** (converted internally to km).
            Used to derive ``half_search`` and ``half_refine`` in grid points.
        """
        super().__init__(var_aliases=var_aliases)
        from frameit.core.configuration import validate_wind_pressure_initial_guess

        self.initial_guess = validate_wind_pressure_initial_guess(initial_guess)
        self.lat_name, self.lon_name = lat_name, lon_name

        if resolution_km is not None:
            import warnings

            if grid_spacing_m is not None:
                raise ValueError("Supply grid_spacing_m, not both spacing arguments")
            warnings.warn(
                "resolution_km historically means metres; use grid_spacing_m",
                DeprecationWarning, stacklevel=2,
            )
            grid_spacing_m = resolution_km
        if grid_spacing_m is None:
            raise ValueError("grid_spacing_m is required")
        for value in (search_half_width_km, refine_half_width_km):
            if not np.isfinite(value) or value <= 0:
                raise ValueError("Search/refinement half-widths must be positive kilometres")

        self.resolution_km = float(grid_spacing_m) / 1000.0
        if not np.isfinite(self.resolution_km) or self.resolution_km <= 0:
            raise ValueError("grid_spacing_m must be finite and positive")

        half_search = int(np.ceil(search_half_width_km / self.resolution_km))
        half_refine = int(np.ceil(refine_half_width_km / self.resolution_km))

        self.half_search_indices = max(1, half_search)
        self.half_refine_indices = max(1, half_refine)

    @classmethod
    def from_config(cls, conf: SimulationConfig) -> "PressureWindTracker":
        """
        Build a :class:`PressureWindTracker` from a simulation configuration.

        Parameters
        ----------
        conf : SimulationConfig
            Configuration object.  Reads ``tracking_var_aliases`` and
            ``resolution`` (grid spacing in metres).

        Returns
        -------
        PressureWindTracker
        """
        var_aliases = getattr(conf, "tracking_var_aliases", {}) or {}
        return cls(var_aliases=var_aliases, grid_spacing_m=conf.resolution,
                   search_half_width_km=conf.wind_pressure_search_half_width_km,
                   refine_half_width_km=conf.wind_pressure_refine_half_width_km,
                   initial_guess=conf.wind_pressure_initial_guess,
                   lat_name=conf.name_latitude, lon_name=conf.name_longitude)

    def _track_method(self, ds: xr.Dataset) -> xr.Dataset:
        """
        Apply :func:`pressure_wind_tracker` to the flat dataset.

        Parameters
        ----------
        ds : xr.Dataset
            Flat tracking dataset.  Must contain the fields aliased to
            ``"mslp"``, ``"u10m"``, and ``"v10m"``.

        Returns
        -------
        xr.Dataset
            Dataset with variables ``cy(time)`` and ``cx(time)``.
        """
        mslp = self._field(ds, "mslp")
        u10 = self._field(ds, "u10m")
        v10 = self._field(ds, "v10m")
        initial_mask = None
        if self.initial_guess is not None:
            from pyproj import Geod

            seed = self.initial_guess
            coords = []
            for name in (self.lat_name, self.lon_name):
                if name not in ds:
                    raise ValueError(f"wind_pressure initial guess requires coordinate {name}")
                coordinate = ds[name]
                coords.append(coordinate.isel(time=0) if "time" in coordinate.dims else coordinate)
            lat, lon = xr.broadcast(*coords)
            spatial = mslp.isel(time=0)
            if set(lat.dims) != set(spatial.dims):
                raise ValueError("Initial guess geography must match the horizontal pressure grid")
            lat, lon = lat.transpose(*spatial.dims), lon.transpose(*spatial.dims)
            _, _, distance = Geod(ellps="WGS84").inv(
                np.full(lat.shape, seed["longitude"]),
                np.full(lat.shape, seed["latitude"]), np.asarray(lon), np.asarray(lat))
            initial_mask = xr.DataArray(
                np.isfinite(distance) & (distance <= seed["search_radius_km"] * 1000),
                dims=spatial.dims, coords=spatial.coords)

        cy, cx = pressure_wind_tracker(
            mslp=mslp,
            zonal_10m=u10,
            merid_10m=v10,
            time_dim="time",
            half_search=self.half_search_indices,
            half_refine=self.half_refine_indices,
            initial_mask=initial_mask,
        )

        result = xr.Dataset({"cy": cy, "cx": cx})
        if self.initial_guess is not None:
            result.attrs.update(
                wind_pressure_initial_guess_latitude=self.initial_guess["latitude"],
                wind_pressure_initial_guess_longitude=self.initial_guess["longitude"],
                wind_pressure_initial_search_radius_km=self.initial_guess["search_radius_km"],
                wind_pressure_initial_search_geometry="WGS84 geodesic circle; first input time",
            )
        return result
