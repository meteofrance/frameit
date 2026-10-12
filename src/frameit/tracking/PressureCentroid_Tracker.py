"""Frameit adapter for the adaptive, storm-motion-coupled pressure centroid."""

from dataclasses import asdict

import numpy as np
import xarray as xr

from .pressure_centroid import (
    G0,
    CentroidOptions,
    LocalGridIndex,
    interpolate_to_height,
    make_interpolator,
    min_index,
    motion_vectors,
    solve_motion_centroids,
)
from .tracker_core import TcTracker, register_tracker


@register_tracker
class PressureCentroidTracker(TcTracker):
    name = "pressure_centroid"
    logical_fields = ("mslp", "u10m", "v10m", "u", "v", "geopot")

    def __init__(self, var_aliases, resolution_m, options=None,
                 lon_name="longitude", lat_name="latitude"):
        super().__init__(var_aliases=var_aliases)
        if not np.isfinite(resolution_m) or resolution_m <= 0:
            raise ValueError("pressure_centroid requires positive resolution in metres")
        self.half_search = int(np.ceil(100_000 / resolution_m))
        self.half_refine = int(np.ceil(50_000 / resolution_m))
        self.options = options or CentroidOptions()
        self.lon_name, self.lat_name = lon_name, lat_name

    @classmethod
    def from_config(cls, conf):
        if conf.atm_model != "AROME":
            raise ValueError("pressure_centroid currently supports AROME isobaric inputs only")
        return cls(conf.tracking_var_aliases, conf.resolution, CentroidOptions.from_config(conf),
                   conf.name_longitude, conf.name_latitude)

    def _track_method(self, ds):
        level_dim = "isobaricInhPa"
        mslp = self._field(ds, "mslp")
        if "time" not in mslp.dims or mslp.ndim != 3:
            raise ValueError("pressure_centroid requires MSLP(time, y, x)")
        spatial = tuple(d for d in mslp.dims if d != "time")
        horizontal_dims = ("time", *spatial)
        vertical_dims = ("time", level_dim, *spatial)
        data = {}
        for name in self.logical_fields:
            da = self._field(ds, name)
            expected = vertical_dims if name in ("u", "v", "geopot") else horizontal_dims
            if set(da.dims) != set(expected):
                raise ValueError(f"pressure_centroid: {name} must have dimensions {expected}")
            data[name] = da.transpose(*expected)
        # Reject invalid chronology before loading the large vertical fields.
        motion_vectors([{"time": stamp} for stamp in ds.time.values],
                       [(0.0, 0.0)] * ds.sizes["time"])
        units = str(data["geopot"].attrs.get("units", "")).replace(" ", "")
        if units not in ("m**2s**-2", "m2s-2", "m2s**-2", "m^2s^-2", "m2/s2"):
            raise ValueError(f"Unrecognized geopotential units: {units!r}")
        for name in ("u", "v", "u10m", "v10m"):
            da = data[name]
            if str(da.attrs.get("units", "")).replace(" ", "") not in (
                    "ms**-1", "ms-1", "m/s", "ms^-1"):
                raise ValueError(f"{name}: expected wind units m s-1")
            if da.attrs.get("GRIB_uvRelativeToGrid") != 0:
                raise ValueError("pressure_centroid requires earth-relative winds")
        if str(mslp.attrs.get("units", "")).lower() not in ("pa", "hpa", "mbar"):
            raise ValueError("Unrecognized MSLP units")
        levels = np.asarray(ds[level_dim], float)
        if levels.size < 2 or len(np.unique(levels)) != len(levels):
            raise ValueError("At least two distinct isobaric levels are required")
        records = []
        previous = None
        reference_grid = None
        for k, stamp in enumerate(ds.time.values):
            coords = []
            for name in (self.lon_name, self.lat_name):
                da = ds[name]
                if "time" in da.dims:
                    da = da.isel(time=k)
                coords.append(da)
            lon_da, lat_da = xr.broadcast(*coords)
            lon = np.asarray(lon_da.transpose(*spatial), float)
            lat = np.asarray(lat_da.transpose(*spatial), float)
            if reference_grid is None:
                reference_grid = lon, lat
                # Validate interpolation geometry before the expensive preparation.
                make_interpolator(lon, lat, np.zeros(lon.shape))
                index = LocalGridIndex(lon, lat)
            elif not (np.array_equal(lon, reference_grid[0])
                      and np.array_equal(lat, reference_grid[1])):
                raise ValueError("pressure_centroid requires the same native grid at all times")
            rec = dict(time=stamp, lon=reference_grid[0], lat=reference_grid[1],
                       pressure_levels=levels, _grid_index=index)
            for logical, key in (("u", "u"), ("v", "v"), ("geopot", "z")):
                rec[key] = np.asarray(data[logical].isel(time=k), float)
            rec["z"] = rec["z"] / G0
            rec["h2000"] = interpolate_to_height(rec)
            for key in ("u", "v", "z", "pressure_levels"):
                del rec[key]
            pressure_index = min_index(np.asarray(data["mslp"].isel(time=k)),
                                       previous, self.half_search)
            wind = np.hypot(data["u10m"].isel(time=k), data["v10m"].isel(time=k))
            previous = min_index(np.asarray(wind), pressure_index, self.half_refine)
            guess = min_index(rec["h2000"]["p"], pressure_index, self.half_search)
            rec["guess"] = float(lon[guess]), float(lat[guess])
            records.append(rec)
        motion_vectors(records, [r["guess"] for r in records])
        centers = solve_motion_centroids(records, self.options)
        nearest = [index.nearest(c) for c in centers]
        cy, cx = np.unravel_index([n[0] for n in nearest], reference_grid[0].shape)
        out = xr.Dataset(coords={"time": ds.time.values})
        variables = {
            "cx": (cx, "1", "nearest native grid column index"),
            "cy": (cy, "1", "nearest native grid row index"),
            "lon": ([c[0] for c in centers], "degrees_east", "continuous centroid longitude"),
            "lat": ([c[1] for c in centers], "degrees_north", "continuous centroid latitude"),
            "grid_center_offset_m": (
                [n[1] for n in nearest], "m", "centroid to extraction cell distance"
            ),
        }
        for name, unit, description in (
                ("r80_km", "km", "inward 80 percent tangential wind radius"),
                ("radius_km", "km", "pressure integration radius, twice R80"),
                ("environment_hpa", "hPa", "500 km ring environmental pressure"),
                ("iterations", "1", "adaptive centroid iterations"),
                ("motion_residual_m", "m", "full unrelaxed fixed point residual"),
                ("motion_outer_iterations", "1", "motion centroid outer iterations"),
                ("translation_u", "m s-1", "solver eastward storm translation"),
                ("translation_v", "m s-1", "solver northward storm translation")):
            variables[name] = ([r[name] for r in records], unit, description)
        for name, (values, unit, description) in variables.items():
            out[name] = xr.DataArray(values, dims="time",
                                     attrs={"units": unit, "long_name": description})
        out.attrs.update(tracking_method=self.name,
                         references="Nguyen et al. (2014), doi:10.1175/MWR-D-14-00044.1",
                         pressure_centroid_implementation="compare_batsirai_centers v1.4.1",
                         pressure_centroid_height_m=2000.0,
                         pressure_centroid_reference_radius_km=500.0,
                         pressure_centroid_reference_angles=180,
                         pressure_centroid_initial_radius_km=100.0,
                         pressure_centroid_inner_tolerance_m=100.0,
                         pressure_centroid_inner_max_steps=40)
        out.attrs.update({"pressure_centroid_" + k: v for k, v in asdict(self.options).items()})
        return out
