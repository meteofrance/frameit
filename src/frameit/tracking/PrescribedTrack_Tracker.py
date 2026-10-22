# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
import xarray as xr

from frameit.core.settings_class import SimulationConfig

from .tracker_core import TcTracker, register_tracker


@register_tracker
class PrescribedTrack(TcTracker):
    """
    Tracker driven by an external prescribed-track NetCDF file.

    At each time step the grid indices ``(cy, cx)`` of the closest grid point
    to the track's ``(lat, lon)`` are returned.  Only dates common to the
    model dataset and the track file are processed.

    The track file must contain at minimum ``time(time)``, a latitude
    variable, and a longitude variable (names configurable via conf).
    Static 1-D axes and 2-D geography are supported independently of model/format.
    """

    name = "prescribed_track"
    logical_fields = ()  # no physical fields required

    def __init__(
        self,
        var_aliases: Mapping[str, str],
        track_file: str | Path,
        atm_model: str | None = None,
        lat_name: str = "latitude",
        lon_name: str = "longitude",
        track_time_name: str = "time",
        track_lat_name: str = "latitude",
        track_lon_name: str = "longitude",
        horizontal_dims: tuple[str, str] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        var_aliases : Mapping[str, str]
            Variable alias mapping (unused, kept for base-class compatibility).
        track_file : str or Path
            Path to the NetCDF file containing the prescribed track.
        atm_model : str or None, optional
            Atmospheric model identifier, either ``"AROME"`` or ``"MNH"``.
        lat_name : str, optional
            Name of the latitude coordinate in the model dataset.
            Default ``"latitude"``.
        lon_name : str, optional
            Name of the longitude coordinate in the model dataset.
            Default ``"longitude"``.
        track_time_name : str, optional
            Name of the time coordinate in the track file. Default ``"time"``.
        track_lat_name : str, optional
            Name of the latitude variable in the track file. Default ``"latitude"``.
        track_lon_name : str, optional
            Name of the longitude variable in the track file. Default ``"longitude"``.
        """
        # var_aliases is unused here, but the parent is called to initialise
        # effective_fields (empty for this tracker).
        super().__init__()

        self.track_file = Path(track_file)
        self.atm_model = atm_model.upper() if atm_model is not None else ""

        self.lat_name = lat_name
        self.lon_name = lon_name
        self.horizontal_dims = horizontal_dims

        self.track_time_name = track_time_name
        self.track_lat_name = track_lat_name
        self.track_lon_name = track_lon_name

    # ------------- construction from config -------------

    @classmethod
    def from_config(cls, conf: SimulationConfig) -> PrescribedTrack:
        """
        Build a :class:`PrescribedTrack` from a simulation configuration.

        Parameters
        ----------
        conf : SimulationConfig
            Configuration object.  Required: ``prescribed_track_file``,
            ``name_latitude``, ``name_longitude``, ``atm_model``.  Optional:
            ``tracking_var_aliases``, ``prescribed_track_time_name``,
            ``prescribed_track_lat_name``, ``prescribed_track_lon_name``.

        Returns
        -------
        PrescribedTrack

        Raises
        ------
        ValueError
            If ``prescribed_track_file`` is not set in ``conf``.
        """
        var_aliases = getattr(conf, "tracking_var_aliases", {}) or {}

        track_file = getattr(conf, "prescribed_track_file", None)
        if not track_file:
            raise ValueError(
                "tracking_method='prescribed_tracker' but "
                "'prescribed_track_file' is not defined in the configuration."
            )

        lat_name = getattr(conf, "name_latitude", "latitude")
        lon_name = getattr(conf, "name_longitude", "longitude")
        atm_model = getattr(conf, "atm_model", None)

        track_time_name = getattr(conf, "prescribed_track_time_name", "time")
        track_lat_name = getattr(conf, "prescribed_track_lat_name", "latitude")
        track_lon_name = getattr(conf, "prescribed_track_lon_name", "longitude")

        return cls(
            var_aliases=var_aliases,
            track_file=track_file,
            atm_model=atm_model,
            lat_name=lat_name,
            lon_name=lon_name,
            track_time_name=track_time_name,
            track_lat_name=track_lat_name,
            track_lon_name=track_lon_name,
            horizontal_dims=(conf.name_lat_dim, conf.name_lon_dim) if
            getattr(conf, "name_lat_dim", None) and getattr(conf, "name_lon_dim", None) else None,
        )

    # ------------- tracking method core -------------

    def _track_method(self, ds: xr.Dataset) -> xr.Dataset:
        """
        Compute ``(cy, cx)`` indices for dates common to the model and track file.

        Parameters
        ----------
        ds : xr.Dataset
            Flat tracking dataset.  Must contain the latitude and longitude
            coordinates named by ``self.lat_name`` and ``self.lon_name``,
            and a ``"time"`` dimension.

        Returns
        -------
        xr.Dataset
            Dataset restricted to common dates, with variables ``cy(time)``
            and ``cx(time)``, plus the supplied continuous ``lon(time)`` and
            ``lat(time)`` used by geographical diagnostics.

        Raises
        ------
        ValueError
            If required coordinates are missing from the track file or model
            dataset, if no common dates are found, or geography is unsupported.
        """
        from frameit.io.track_file import load_track_coordinates
        from frameit.utils.units import convert_units

        lat = convert_units(ds.coords[self.lat_name], "angle",
                            target="degrees_north", assumed="degrees_north")
        lon = convert_units(ds.coords[self.lon_name], "angle",
                            target="degrees_east", assumed="degrees_east")
        time_model = ds["time"].values

        # 1) Read the external track file
        trk = load_track_coordinates(
            self.track_file, time_name=self.track_time_name,
            latitude_name=self.track_lat_name, longitude_name=self.track_lon_name,
        )
        common_times = np.intersect1d(time_model, trk.time.values)
        if common_times.size == 0:
            raise ValueError("PrescribedTrack: no common dates between model and track file")
        trk_sel = trk.sel(time=common_times)
        lat_trk, lon_trk = trk_sel.latitude.values, trk_sel.longitude.values
        if not (np.isfinite(lat_trk).all() and np.isfinite(lon_trk).all()):
            raise ValueError("PrescribedTrack: common-time track positions must be finite")

        ntime = common_times.size
        cy = np.empty(ntime, dtype="int64")
        cx = np.empty(ntime, dtype="int64")

        from .geographic import nearest_grid_point

        for k in range(ntime):
            cy[k], cx[k] = nearest_grid_point(lat, lon, float(lat_trk[k]), float(lon_trk[k]),
                                             axes=self.horizontal_dims)

        # 4) Construction du Dataset de sortie
        time_da = xr.DataArray(common_times, dims=("time",), name="time")

        out = xr.Dataset(
            data_vars={
                "cy": xr.DataArray(cy, dims=("time",), coords={"time": time_da}),
                "cx": xr.DataArray(cx, dims=("time",), coords={"time": time_da}),
                "lon": xr.DataArray(
                    lon_trk, dims=("time",), coords={"time": time_da},
                    attrs={"units": "degrees_east", "long_name": "prescribed cyclone longitude"},
                ),
                "lat": xr.DataArray(
                    lat_trk, dims=("time",), coords={"time": time_da},
                    attrs={"units": "degrees_north", "long_name": "prescribed cyclone latitude"},
                ),
            },
            coords={"time": time_da},
        )
        return out
