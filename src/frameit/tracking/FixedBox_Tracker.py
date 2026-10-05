# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import xarray as xr

from frameit.core.settings_class import SimulationConfig

from .tracker_core import TcTracker, nearest_grid_point, register_tracker


@register_tracker
class FixedBoxTracker(TcTracker):
    """
    Fixed-position tracker: returns the grid point closest to a prescribed centre.

    The returned ``cy`` and ``cx`` arrays are constant over time.
    Both AROME (1-D lat/lon) and MNH (2-D lat/lon) grids are supported.
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
            Kept for backward compatibility: the grid type is now inferred
            from the dimensionality of the latitude and longitude coordinates.
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
            constant over time.

        Raises
        ------
        ValueError
            If required coordinates or the ``"time"`` dimension are missing,
            or if latitude and longitude are neither both 1-D nor both 2-D.
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

        # Closest grid point to the imposed centre (1-D or 2-D lat/lon)
        cy_scalar, cx_scalar, _ = nearest_grid_point(
            ds[self.lat_name], ds[self.lon_name], self.lat0, self.lon0
        )

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
        return out
