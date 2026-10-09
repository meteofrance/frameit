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
    Both AROME (1-D lat/lon) and MNH (2-D lat/lon) grids are supported.
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
            and ``cx(time)``.

        Raises
        ------
        ValueError
            If required coordinates are missing from the track file or model
            dataset, if no common dates are found, or if ``atm_model`` is
            not ``"AROME"`` or ``"MNH"``.
        """
        lat = ds.coords[self.lat_name]
        lon = ds.coords[self.lon_name]
        time_model = ds["time"].values

        # 1) Read the external track file
        with xr.open_dataset(self.track_file) as trk:
            if self.track_time_name not in trk.coords:
                raise ValueError(
                    f"PrescribedTrack: time coordinate {self.track_time_name!r} "
                    "not found in the track file."
                )
            names = []
            for requested, long_name, short_name in (
                (self.track_lat_name, "latitude", "lat"),
                (self.track_lon_name, "longitude", "lon"),
            ):
                name = requested
                if name not in trk and name == long_name and short_name in trk:
                    name = short_name
                if name not in trk:
                    raise ValueError(
                        f"PrescribedTrack: variable {requested!r} not found in the track file."
                    )
                if trk[name].dims != (self.track_time_name,):
                    raise ValueError(
                        f"PrescribedTrack: {name!r} must be one-dimensional "
                        f"along {self.track_time_name!r}"
                    )
                names.append(name)

            time_trk = trk[self.track_time_name].values
            if trk[self.track_time_name].dims != (self.track_time_name,):
                raise ValueError("PrescribedTrack: time must be a one-dimensional coordinate")
            if np.unique(time_trk).size != time_trk.size:
                raise ValueError("PrescribedTrack: duplicate track times are ambiguous")
            common_times = np.intersect1d(time_model, time_trk)
            if common_times.size == 0:
                raise ValueError(
                    "PrescribedTrack: no common dates between the model Dataset and the track file."
                )
            trk_sel = trk.sel({self.track_time_name: common_times})
            # Eagerly copy the small coordinate arrays before closing the file.
            lat_trk = trk_sel[names[0]].values.copy()
            lon_trk = trk_sel[names[1]].values.copy()
            if not (np.isfinite(lat_trk).all() and np.isfinite(lon_trk).all()):
                raise ValueError("PrescribedTrack: common-time track positions must be finite")

        ntime = common_times.size
        cy = np.empty(ntime, dtype="int64")
        cx = np.empty(ntime, dtype="int64")

        model = self.atm_model

        # 3) Calcul des indices (cy, cx) pour chaque date

        # AROME case: 1D lat (nj), 1D lon (ni)
        if model == "AROME":
            if not (lat.ndim == 1 and lon.ndim == 1):
                raise ValueError(
                    f"PrescribedTrack (AROME): expected 1D lat/lon, got "
                    f"lat.ndim={lat.ndim}, lon.ndim={lon.ndim}"
                )

            lat_vals = lat.values
            lon_vals = lon.values

            for k in range(ntime):
                lat0 = float(lat_trk[k])
                lon0 = float(lon_trk[k])

                j = int(np.nanargmin((lat_vals - lat0) ** 2))
                i = int(np.nanargmin((lon_vals - lon0) ** 2))

                cy[k] = j
                cx[k] = i

        # MNH case: 2D lat (nj, ni), 2D lon (nj, ni)
        elif model == "MNH":
            if not (lat.ndim == 2 and lon.ndim == 2):
                raise ValueError(
                    f"PrescribedTrack (MNH): expected 2D lat/lon, got "
                    f"lat.ndim={lat.ndim}, lon.ndim={lon.ndim}"
                )
            if lat.shape != lon.shape:
                raise ValueError(
                    "PrescribedTrack (MNH): 2D latitude and longitude must have the same shape"
                )

            for k in range(ntime):
                lat0 = float(lat_trk[k])
                lon0 = float(lon_trk[k])

                dlat = lat - lat0
                dlon = lon - lon0
                dist2 = dlat * dlat + dlon * dlon

                dist_vals = dist2.values
                j_flat, i_flat = np.unravel_index(int(np.nanargmin(dist_vals)), dist_vals.shape)
                cy[k] = int(j_flat)
                cx[k] = int(i_flat)

        else:
            raise ValueError(f"PrescribedTrack: unsupported atmospheric model {model!r}")

        # 4) Construction du Dataset de sortie
        time_da = xr.DataArray(common_times, dims=("time",), name="time")

        out = xr.Dataset(
            data_vars={
                "cy": xr.DataArray(cy, dims=("time",), coords={"time": time_da}),
                "cx": xr.DataArray(cx, dims=("time",), coords={"time": time_da}),
            },
            coords={"time": time_da},
        )
        return out
