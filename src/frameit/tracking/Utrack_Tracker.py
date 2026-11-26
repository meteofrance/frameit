# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

import numpy as np
import xarray as xr

from frameit.core.settings_class import SimulationConfig
from frameit.utils.diagnostics import tag_error
from frameit.utils.units import convert_units

from .tracker_core import TcTracker, register_tracker


def _common_input_grid(u, v, absv, lat, lon):
    """Validate labelled collocation before stripping labels for the ML API."""
    horizontal = set(u.dims) - {"time"}
    if len(horizontal) != 2 or "time" not in u.dims:
        raise ValueError("UTrack winds require time and exactly two horizontal dimensions")
    if set(v.dims) != set(u.dims) or set(absv.dims) != set(u.dims):
        raise ValueError("UTrack winds and absolute vorticity must share common grid locations")
    if any(len({d in a.coords for a in (u, v, absv)}) != 1 for d in horizontal):
        raise ValueError("UTrack requires consistent horizontal labels to verify locations")
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
                      or (d in u.coords and u[d].attrs.get("axis") == "Y")]
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
            on the exact 850 hPa level), and a ``latitude``
            or ``lat`` coordinate for the hemisphere vorticity correction.

        Returns
        -------
        xr.Dataset
            Dataset with variables ``cy(time)`` and ``cx(time)``.
        """
        from utrack.prepare import get_latitude, prepare_input

        u10 = convert_units(self._field(ds, "u10m"), "velocity")
        v10 = convert_units(self._field(ds, "v10m"), "velocity")
        absv = self._field(ds, "absv")
        if "isobaric" not in absv.coords or absv.isobaric.dims != ("isobaric",):
            raise ValueError("UTrack requires a labelled isobaric axis for absolute vorticity")
        indices = np.flatnonzero(convert_units(absv.isobaric, "pressure", target="hPa") == 850.)
        if len(indices) != 1:
            raise ValueError("UTrack requires one exact 850 hPa level for absolute vorticity")
        absv = convert_units(absv.isel(isobaric=int(indices[0]), drop=True), "vorticity")
        lat = get_latitude(ds)
        lon_name = next((n for n in ("longitude", "lon") if n in ds), None)
        if lon_name is None:
            raise ValueError("UTrack requires longitude to verify common geographic locations")
        u10, v10, absv = _common_input_grid(u10, v10, absv, lat, ds[lon_name])
        _, ny, nx = u10.shape
        lat = lat.transpose(*(d for d in u10.dims if d in lat.dims))
        inputs = xr.Dataset({"u10": u10, "v10": v10, "absv": absv},
                            coords={"utrack_latitude": lat})
        if not np.isfinite(ds[lon_name].values).all():
            raise ValueError("UTrack requires finite longitudes on its horizontal grid")
        cx, cy = [], []
        for start in range(0, inputs.sizes["time"], self.batch_size):
            batch = inputs.isel(time=slice(start, start + self.batch_size)).compute()
            values = {name: batch[name].values for name in ("u10", "v10", "absv")}
            latitude = batch.utrack_latitude.values
            if not (np.isfinite(latitude).all() and (np.abs(latitude) <= 90).all()
                    and all(np.isfinite(var).all() for var in values.values())):
                raise tag_error(ValueError(
                    f"UTrack requires finite inputs and valid latitudes at {batch.time.values}"),
                    "E1503")
            _, detections = self.utracker.predict_batch(
                prepare_input(**values, lat=latitude),
                use_gpu=self.use_gpu, match=False, batch_size=self.batch_size)
            if len(detections) != batch.sizes["time"]:
                raise tag_error(ValueError("UTrack did not return one detection list per time"),
                                "E1503")
            for stamp, cyclones in zip(batch.time.values, detections, strict=True):
                if not cyclones:
                    raise tag_error(ValueError(f"UTrack: No cyclone detected at {stamp}"), "E1503")
                y, x = cyclones[0].last_fix().vmax_center
                if not (0 <= y <= ny - 1 and 0 <= x <= nx - 1):
                    raise tag_error(ValueError(
                        f"UTrack centre ({y}, {x}) at {stamp} is outside the input grid"), "E1503")
                # Preserve the adapter's historical conversion of fractional pixel centres.
                cy.append(int(y))
                cx.append(int(x))
        return xr.Dataset({"cy": ("time", cy), "cx": ("time", cx)}, coords={"time": ds.time})
