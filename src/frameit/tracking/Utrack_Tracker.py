# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

import logging

import xarray as xr

from frameit.core.settings_class import SimulationConfig

from .tracker_core import TcTracker, register_tracker

try:
    from utrack import Utracker
    from utrack.prepare import prepare_input
except Exception:
    pass

logger = logging.getLogger(__name__)


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
            on isobaric levels; the first level is used).

        Returns
        -------
        xr.Dataset
            Dataset with variables ``cy(time)`` and ``cx(time)``.
        """
        u10 = self._field(ds, "u10m")
        v10 = self._field(ds, "v10m")
        absv = self._field(ds, "absv").isel(isobaricInhPa=0)

        time_da = ds["time"]

        # Applying utrack model

        x = prepare_input(u10=u10, v10=v10, absv=absv)
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
