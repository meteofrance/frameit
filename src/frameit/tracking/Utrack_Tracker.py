# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

import logging

import xarray as xr

from frameit.core.settings_class import SimulationConfig

from .tracker_core import TcTracker, register_tracker

logger = logging.getLogger(__name__)


def _common_input_grid(u, v, absv, lat, lon):
    """Validate labelled collocation before stripping labels for the ML API."""
    horizontal = set(u.dims) - {"time"}
    if len(horizontal) != 2 or "time" not in u.dims:
        raise ValueError("UTrack winds require time and exactly two horizontal dimensions")
    if set(v.dims) != set(u.dims) or set(absv.dims) != set(u.dims):
        raise ValueError("UTrack winds and absolute vorticity must share common grid locations")
    if any(d not in a.coords for a in (u, v, absv) for d in horizontal):
        raise ValueError("UTrack requires labelled horizontal coordinates to verify locations")
    for geo in (lat, lon):
        if not set(geo.dims) <= set(u.dims) or not (set(geo.dims) & horizontal):
            raise ValueError("UTrack geography must share the wind grid locations")
    if (set(lat.dims) | set(lon.dims)) - {"time"} != horizontal:
        raise ValueError("UTrack geography must span both wind horizontal axes")
    try:
        xr.align(u, v, absv, lat, lon, join="exact")
    except ValueError as exc:
        raise ValueError("UTrack wind/vorticity/geography coordinates must match exactly") from exc
    # Reject per-field location declarations that disagree even if dimensions
    # happen to have the same lengths/labels.
    positions = {a.attrs.get("grid_position", "mass_aligned") for a in (u, v, absv)}
    if len(positions) != 1 or any("face" in p for p in positions):
        raise ValueError("UTrack requires collocated mass-grid wind/vorticity inputs")
    if lat.ndim == 1:
        y = lat.dims[0]
    else:
        candidates = [d for d in horizontal if d in {"nj", "y", "latitude", "lat"}
                      or u[d].attrs.get("axis") == "Y"]
        if len(candidates) != 1:
            raise ValueError("UTrack requires an identifiable named y axis")
        y = candidates[0]
    x, = horizontal - {y}
    return tuple(a.transpose("time", y, x) for a in (u, v, absv))


@register_tracker
class UtrackTracker(TcTracker):
    """
    Tracker backed by the UTrack deep-learning model.

    Runs UTrack inference on 10 m wind and absolute vorticity fields to
    locate the cyclone centre at each time step.  Requires the optional
    ``utrack`` package.
    """

    name = "utrack"
    logical_fields = ("u10m", "v10m", "absv")

    def __init__(self, var_aliases, checkpoint_path, use_gpu, batch_size):
        """
        Parameters
        ----------
        var_aliases : Mapping[str, str]
            Variable alias mapping (logical name → native name in dataset).
        checkpoint_path : str or Path
            Path to the UTrack model checkpoint file.
        use_gpu : bool
            Whether to run inference on GPU.
        batch_size : int
            Number of time steps processed per batch.
        """
        super().__init__(var_aliases=var_aliases)

        # Optional ML backends are initialized only when this tracker is used.
        # Their import-time diagnostics do not belong in unrelated simulations.
        from utrack import Utracker

        self.utracker = Utracker()
        self.utracker.load_checkpoint(checkpoint_path=checkpoint_path)
        self.use_gpu = use_gpu
        self.batch_size = batch_size

    @classmethod
    def from_config(cls, conf: SimulationConfig) -> "UtrackTracker":
        """
        Build a :class:`UtrackTracker` from a simulation configuration.

        Parameters
        ----------
        conf : SimulationConfig
            Configuration object.  Required: ``utrack_weights_file``.
            Optional: ``tracking_var_aliases``, ``utrack_use_gpu`` (default
            ``False``), ``utrack_batch_size`` (default 16).

        Returns
        -------
        UtrackTracker

        Raises
        ------
        ValueError
            If ``utrack_weights_file`` is not set in ``conf``.
        """
        var_aliases = getattr(conf, "tracking_var_aliases", {}) or {}

        checkpoint_path = getattr(conf, "utrack_weights_file", None)
        if checkpoint_path is None:
            raise ValueError(
                "tracking_method='utrack' but "
                "'utrack_weights_file' is not defined in the configuration."
            )
        use_gpu = getattr(conf, "utrack_use_gpu", False)
        batch_size = getattr(conf, "utrack_batch_size", 16)

        return cls(
            var_aliases=var_aliases,
            checkpoint_path=checkpoint_path,
            use_gpu=use_gpu,
            batch_size=batch_size,
        )

    def _track_method(self, ds: xr.Dataset) -> xr.Dataset:
        """
        Apply UTrack inference to locate the cyclone at each time step.

        Parameters
        ----------
        ds : xr.Dataset
            Flat tracking dataset.  Must contain the fields aliased to
            ``"u10m"``, ``"v10m"``, and ``"absv"`` (absolute vorticity
            on isobaric levels; the first level is used), and a ``latitude``
            or ``lat`` coordinate for the hemisphere vorticity correction.

        Returns
        -------
        xr.Dataset
            Dataset with variables ``cy(time)`` and ``cx(time)``.
        """
        from utrack.prepare import get_latitude, prepare_input

        u10 = self._field(ds, "u10m")
        v10 = self._field(ds, "v10m")
        absv = self._field(ds, "absv").isel(isobaricInhPa=0)
        lat = get_latitude(ds)
        lon_name = next((n for n in ("longitude", "lon") if n in ds), None)
        if lon_name is None:
            raise ValueError("UTrack requires longitude to verify common geographic locations")
        u10, v10, absv = _common_input_grid(u10, v10, absv, lat, ds[lon_name])
        lat = lat.transpose(*(d for d in u10.dims if d in lat.dims))

        time_da = ds["time"]

        # Applying utrack model

        x = prepare_input(
            u10=u10.values,
            v10=v10.values,
            absv=absv.values,
            lat=lat.values,
        )
        y_pred, cyclones = self.utracker.predict_batch(
            x, use_gpu=self.use_gpu, match=False, batch_size=self.batch_size
        )

        # Processing output

        cx = []
        cy = []

        for i, cycs in enumerate(cyclones):
            if len(cycs) > 0:
                y, x = cycs[0].last_fix().vmax_center
            else:
                logger.warning(
                    "No cyclone detected by the tracker at position=%s,"
                    " returning coordinates (x=0, y=0)",
                    i,
                )
                y, x = 0, 0  # np.nan, np.nan

            cx.append(x)
            cy.append(y)

        # Build the output dataset

        out = xr.Dataset(
            {
                "cy": xr.DataArray(cy, dims=("time",), coords={"time": time_da}).astype(int),
                "cx": xr.DataArray(cx, dims=("time",), coords={"time": time_da}).astype(int),
            }
        )

        return out
