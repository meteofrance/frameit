"""Seeded multi-field adapter with explicit experimental qualification status."""

import logging
from dataclasses import asdict
from functools import partial

import numpy as np
import xarray as xr

from .multifield_inputs import canonical_inputs, iter_fields
from .multifield_vortex import (
    PARAMETER_FLAGS,
    PARAMETERS,
    QUALITY_FLAGS,
    REFERENCE_REVISION,
    VortexGrid,
    VortexOptions,
    combine_fixes,
    offset,
    quality_check,
    relative_vorticity,
    translation_speed,
)
from .pressure_centroid import GEOD
from .tracker_core import TcTracker, register_tracker

logger = logging.getLogger(__name__)


@register_tracker
class MultifieldVortexTracker(TcTracker):
    name = "multifield_vortex"
    logical_fields = ()

    def __init__(self, conf):
        super().__init__()
        self.conf = conf
        self.settings = conf.multifield_vortex
        self.options = VortexOptions(**self.settings["numerics"], **self.settings["quality"])
        self.seed = self.settings["seed"]
        if (self.seed["latitude"] is None or self.seed["longitude"] is None or
                self.seed["motion_u_m_s"] is None or self.seed["motion_v_m_s"] is None):
            raise ValueError("multifield_vortex requires an explicit seed position and motion")
        if self.settings["profile"] != "all_no_thick":
            raise ValueError("multifield_vortex currently supports all_no_thick only")

    @classmethod
    def from_config(cls, conf):
        return cls(conf)

    def _track_method(self, source):
        ds = canonical_inputs(source, self.conf)
        if "time" not in ds.coords or ds.time.dims != ("time",):
            raise ValueError("multifield_vortex requires a labelled time(time) coordinate")
        times = np.asarray(ds.time, dtype="datetime64[ns]")
        if (not len(times) or np.isnat(times).any() or
                np.any(np.diff(times) <= np.timedelta64(0, "ns"))):
            raise ValueError("multifield_vortex requires strictly increasing valid times")
        if self.seed["time"] is not None and np.datetime64(self.seed["time"], "ns") != times[0]:
            raise ValueError("multifield_vortex seed.time must match the first input timestamp")
        guess = (self.seed["longitude"], self.seed["latitude"])
        if not np.isfinite(guess).all() or not 0 < abs(guess[1]) < 90:
            raise ValueError(
                "multifield_vortex seed must have finite, non-equatorial/nonpolar latitude")
        hemisphere = np.sign(guess[1])
        motion = np.array([self.seed["motion_u_m_s"], self.seed["motion_v_m_s"]], float)
        if not np.isfinite(motion).all():
            raise ValueError("multifield_vortex seed motion must be finite, in m/s")
        records, attempts, history = [], [], []
        grid = None
        speed_anchor = None
        reason = ""
        for k, fields in enumerate(iter_fields(ds, self.conf)):
            if grid is None:
                grid = VortexGrid(fields["lon"], fields["lat"], self.conf.resolution, self.options)
                if not np.isfinite(grid.footprint(*guess)):
                    raise ValueError("multifield_vortex seed is outside the native grid")
            elif not (np.array_equal(grid.lon, fields["lon"]) and
                      np.array_equal(grid.lat, fields["lat"])):
                raise ValueError("multifield_vortex requires a stationary native grid")
            positions, statuses = [], []
            for name in PARAMETERS:
                if name.startswith("circulation"):
                    suffix = name.removeprefix("circulation")
                    if suffix == "_surface":
                        u, v = fields["u10m"], fields["v10m"]
                    else:
                        level = 0 if suffix == "850" else 1
                        u, v = fields["u"][level], fields["v"][level]
                    su, sv = grid.geometry.interpolator(u), grid.geometry.interpolator(v)
                    objective = partial(grid.circulation, sample_u=su, sample_v=sv)
                    maximize, radius = True, 250.
                else:
                    if name == "mslp":
                        data = fields["mslp"]
                    elif name.startswith("gph"):
                        data = fields["height"][0 if name == "gph850" else 1]
                    else:
                        if name == "rv_surface":
                            u, v = fields["u10m"], fields["v10m"]
                        else:
                            level = 0 if name == "rv850" else 1
                            u, v = fields["u"][level], fields["v"][level]
                        data = hemisphere * relative_vorticity(u, v, grid.lon, grid.lat)
                    objective = partial(grid.barnes, data=data)
                    maximize, radius = name.startswith("rv"), grid.search_km
                position, status = grid.extremum(guess, objective, maximize, radius)
                positions.append(position if status == 0 else [np.nan, np.nan])
                statuses.append(status)
            positions = np.asarray(positions)
            center, statuses, weights, error_std, spread, limit = combine_fixes(
                positions, statuses, guess, history)
            metrics = dict(pressure_rise_pa=np.nan, vt850_mean_m_s=np.nan, separation_km=np.nan)
            quality = 1
            if center is not None:
                quality, metrics = quality_check(grid, fields, center, positions,
                                                 statuses, self.options)
                if np.sign(center[1]) != hemisphere:
                    quality = 9
            speed = np.nan
            if quality == 0 and speed_anchor is not None:
                speed = translation_speed(*speed_anchor, times[k], center,
                                          self.options.speed_check_interval_hours)
                if np.isfinite(speed):
                    if speed > self.options.max_speed_m_s:
                        quality = 6
                    else:
                        speed_anchor = (times[k], center)
            steering = np.full(2, np.nan)
            if quality == 0 and k + 1 < len(times):
                # Reference weights: 850/700/500 = .25/.50/.25. Missing support
                # is not replaced by zero or by another steering layer.
                steering = np.array([
                    sum(w * grid.barnes(center, fields[name][i], 500., 1000.)
                        for i, w in enumerate((.25, .5, .25))) for name in ("u", "v")])
                if not np.isfinite(steering).all():
                    quality = 8
            attempts.append(dict(time=times[k], positions=positions, statuses=statuses,
                                 weights=weights, quality=quality, guess=guess,
                                 exclusion_km=limit, spread=spread, speed=speed,
                                 steering=steering, **metrics))
            if quality:
                reason = QUALITY_FLAGS.split()[quality]
                if not records or self.settings["on_track_loss"] == "error":
                    hint = ("500/700/850-hPa steering requires a 1000-km influence disk"
                            if quality == 8 else "check native-level masks, pressure/circulation "
                            "structure, domain coverage and QC settings")
                    raise ValueError(f"multifield_vortex at {times[k]}: {reason}; "
                                     f"{hint}")
                logger.warning("multifield_vortex terminated at %s: %s (%d/%d accepted times)",
                               times[k], reason, len(records), len(times))
                break
            if records:
                dt = float((times[k] - records[-1]["time"]) / np.timedelta64(1, "s"))
                az, _, distance = GEOD.inv(*records[-1]["center"], *center)
                motion = distance / dt * np.array([np.sin(np.deg2rad(az)), np.cos(np.deg2rad(az))])
            if speed_anchor is None:
                speed_anchor = (times[k], center)
            records.append(dict(time=times[k], center=center))
            history.append(error_std)
            if k + 1 < len(times):
                dt = float((times[k + 1] - times[k]) / np.timedelta64(1, "s"))
                velocity = (steering + motion) / 2
                guess = tuple(offset(center, velocity[0] * dt, velocity[1] * dt)[0])
        out = xr.Dataset(coords={"time": [r["time"] for r in records],
                                 "attempt_time": [a["time"] for a in attempts],
                                 "parameter": list(PARAMETERS)})
        centers = np.array([r["center"] for r in records])
        for i, name, unit in ((0, "lon", "degrees_east"), (1, "lat", "degrees_north")):
            out[name] = ("time", centers[:, i], {"units": unit})
        nearest = [grid.index.nearest(tuple(p)) for p in centers]
        cy, cx = np.unravel_index([p[0] for p in nearest], grid.lon.shape)
        out["cx"], out["cy"] = ("time", cx), ("time", cy)
        out["grid_center_offset_m"] = ("time", [p[1] for p in nearest], {"units": "m"})
        positions = np.array([a["positions"] for a in attempts])
        dims = ("attempt_time", "parameter")
        out["parameter_lon"] = (dims, positions[:, :, 0], {"units": "degrees_east"})
        out["parameter_lat"] = (dims, positions[:, :, 1], {"units": "degrees_north"})
        out["parameter_status"] = (dims, np.array([a["statuses"] for a in attempts]), {
            "flag_values": np.arange(6, dtype="int8"), "flag_meanings": PARAMETER_FLAGS})
        out["parameter_weight"] = (dims, np.array([a["weights"] for a in attempts]), {"units": "1"})
        out["quality_status"] = ("attempt_time", np.array(
            [a["quality"] for a in attempts], "int8"), {
            "flag_values": np.arange(10, dtype="int8"), "flag_meanings": QUALITY_FLAGS})
        out["accepted_parameter_count"] = (
            "attempt_time", np.sum(out.parameter_status.values == 0, axis=1))
        for component, unit, index in (("lon", "degrees_east", 0), ("lat", "degrees_north", 1)):
            out[f"guess_{component}"] = (
                "attempt_time", [a["guess"][index] for a in attempts], {"units": unit})
        for index, component in enumerate(("u", "v")):
            out[f"steering_{component}"] = (
                "attempt_time", [a["steering"][index] for a in attempts], {"units": "m s-1"})
        for name, key, unit in (("parameter_spread_km", "spread", "km"),
                                ("exclusion_limit_km", "exclusion_km", "km"),
                                ("pressure_rise_333km_pa", "pressure_rise_pa", "Pa"),
                                ("vt850_mean", "vt850_mean_m_s", "m s-1"),
                                ("mslp_rv850_separation_km", "separation_km", "km"),
                                ("checked_translation_speed", "speed", "m s-1")):
            out[name] = ("attempt_time", [a[key] for a in attempts], {"units": unit})
        out.attrs.update(ds.attrs)
        out.attrs.update(
            tracking_method=self.name, method_maturity="experimental_native_grid_adaptation",
            references="Marchok (2021), doi:10.1175/JAMC-D-20-0175.1",
            reference_revision=REFERENCE_REVISION, multifield_profile="all_no_thick",
            tracking_complete=int(not reason), tracking_requested_time_count=len(times),
            tracking_termination_reason=reason,
            tracking_termination_time=str(attempts[-1]["time"]) if reason else "",
            multifield_options=asdict(self.options), multifield_seed=self.seed,
            multifield_barnes_efolding_km=grid.efolding_km,
            multifield_barnes_influence_km=grid.influence_km,
            multifield_search_radius_km=grid.search_km,
            multifield_mnh_gravity_m_s2=self.settings["mnh_gravity_m_s2"] or "not_applicable",
            scientific_qualification=(
                "analytic checks only; full NOAA/real-landfall qualification pending"),
        )
        return out
