# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import xarray as xr

from frameit.core.settings_class import SimulationConfig

from .tracker_core import TcTracker, register_tracker


@register_tracker
class FixedBoxTracker(TcTracker):
    """
    Fixed-position tracker: returns the grid point closest to a prescribed centre.

    The returned ``cy`` and ``cx`` arrays are constant over time.
    Static 1-D axes and 2-D geography are supported independently of model/format.
    """

    name = "fixed_box"
    logical_fields = ()  # no required physical fields

    def __init__(
        self,
        var_aliases: Mapping[str, str],
        fix_subdomain_center: Sequence[float],
        atm_model: str | None = None,
        lat_name: str = "latitude",
        lon_name: str = "longitude",
        horizontal_dims: tuple[str, str] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        var_aliases : Mapping[str, str]
            Variable alias mapping (unused, kept for base-class compatibility).
        fix_subdomain_center : Sequence[float]
            Two-element sequence ``[lat0, lon0]`` giving the imposed centre
            geographic coordinates.
        atm_model : str or None, optional
            Atmospheric model identifier, either ``"AROME"`` or ``"MNH"``.
        lat_name : str, optional
            Name of the latitude coordinate in the tracking dataset.
            Default ``"latitude"``.
        lon_name : str, optional
            Name of the longitude coordinate in the tracking dataset.
            Default ``"longitude"``.

        Raises
        ------
        ValueError
            If ``fix_subdomain_center`` does not contain exactly two elements.
        """
        # Still call parent to set var_aliases / effective_fields.
        super().__init__()

        if not fix_subdomain_center or len(fix_subdomain_center) != 2:
            raise ValueError(
                "FixedBoxTracker: 'fix_subdomain_center' must be a sequence [lat0, lon0]"
            )

        self.lat0 = float(fix_subdomain_center[0])
        self.lon0 = float(fix_subdomain_center[1])

        self.lat_name = lat_name
        self.lon_name = lon_name
        self.horizontal_dims = horizontal_dims
        self.atm_model = atm_model.upper() if atm_model is not None else ""

    # ------------- configuration-specific construction -------------

    @classmethod
    def from_config(cls, conf: SimulationConfig) -> FixedBoxTracker:
        """
        Build a :class:`FixedBoxTracker` from a simulation configuration.

        Parameters
        ----------
        conf : SimulationConfig
            Configuration object.  Required: ``fix_subdomain_center``
            (``[lat0, lon0]``).  Optional: ``tracking_var_aliases``,
            ``name_latitude``, ``name_longitude``, ``atm_model``.

        Returns
        -------
        FixedBoxTracker

        Raises
        ------
        ValueError
            If ``fix_subdomain_center`` is not set in ``conf``.
        """
        var_aliases = getattr(conf, "tracking_var_aliases", {}) or {}

        center = getattr(conf, "fix_subdomain_center", None)
        if center is None:
            raise ValueError(
                "tracking_method='fixed_box' but 'fix_subdomain_center' "
                "is not defined in the configuration."
            )

        lat_name = getattr(conf, "name_latitude", "latitude")
        lon_name = getattr(conf, "name_longitude", "longitude")
        atm_model = getattr(conf, "atm_model", None)

        return cls(
            var_aliases=var_aliases,
            fix_subdomain_center=center,
            atm_model=atm_model,
            lat_name=lat_name,
            lon_name=lon_name,
            horizontal_dims=(conf.name_lat_dim, conf.name_lon_dim) if
            getattr(conf, "name_lat_dim", None) and getattr(conf, "name_lon_dim", None) else None,
        )

    def _track_method(self, ds: xr.Dataset) -> xr.Dataset:
        """
        Compute constant ``(cy, cx)`` indices closest to ``(lat0, lon0)``.

        Parameters
        ----------
        ds : xr.Dataset
            Flat tracking dataset.  Must contain the latitude and longitude
            coordinates named by ``self.lat_name`` and ``self.lon_name``,
            and a ``"time"`` dimension.

        Returns
        -------
        xr.Dataset
            Dataset with variables ``cy(time)`` and ``cx(time)``, both
            constant over time, and the declared ``lon(time)``/``lat(time)``
            geographical centre.

        Raises
        ------
        ValueError
            If required coordinates/time are missing or geography is unsupported.
        """
        if self.lat_name not in ds.coords or self.lon_name not in ds.coords:
            raise ValueError(
                f"FixedBoxTracker: coordinates {self.lat_name!r} or "
                f"{self.lon_name!r} not found in Dataset"
            )

        if "time" not in ds.dims:
            raise ValueError(
                "FixedBoxTracker: 'time' dimension not found in Dataset, "
                "required to produce a time-dependent output."
            )

        time_coord = ds["time"]
        nt = time_coord.size

        lat = ds[self.lat_name]
        lon = ds[self.lon_name]
        from .geographic import nearest_grid_point

        cy_scalar, cx_scalar = nearest_grid_point(lat, lon, self.lat0, self.lon0,
                                                 axes=self.horizontal_dims)

        # Replicate over the time dimension
        cy = xr.DataArray(
            np.full(nt, cy_scalar, dtype=int),
            dims=("time",),
            coords={"time": time_coord},
            name="cy",
        )
        cx = xr.DataArray(
            np.full(nt, cx_scalar, dtype=int),
            dims=("time",),
            coords={"time": time_coord},
            name="cx",
        )

        out = xr.Dataset({"cy": cy, "cx": cx})
        out["lon"] = xr.DataArray(
            np.full(nt, self.lon0), dims=("time",), coords={"time": time_coord},
            attrs={"units": "degrees_east", "long_name": "declared fixed centre longitude"},
        )
        out["lat"] = xr.DataArray(
            np.full(nt, self.lat0), dims=("time",), coords={"time": time_coord},
            attrs={"units": "degrees_north", "long_name": "declared fixed centre latitude"},
        )
        return out
