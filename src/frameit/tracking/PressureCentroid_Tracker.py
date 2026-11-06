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
                 lon_name="longitude", lat_name="latitude", *, model="AROME", conf=None):
        if model not in {"AROME", "MNH"}:
            raise ValueError("pressure_centroid supports AROME and MNH inputs")
        self.model, self.conf = model, conf
        super().__init__(var_aliases=var_aliases)
        if not np.isfinite(resolution_m) or resolution_m <= 0:
            raise ValueError("pressure_centroid requires positive resolution in metres")
        self.half_search = int(np.ceil(100_000 / resolution_m))
        self.half_refine = int(np.ceil(50_000 / resolution_m))
        self.options = options or CentroidOptions()
        self.lon_name, self.lat_name = lon_name, lat_name

    @classmethod
    def from_config(cls, conf):
        return cls(conf.tracking_var_aliases, conf.resolution, CentroidOptions.from_config(conf),
                   conf.name_longitude, conf.name_latitude, model=conf.atm_model, conf=conf)

    def _validate_inputs(self, ds):
        if self.model == "MNH":
            from .pressure_centroid_inputs import resolve_mnh_fields

            resolve_mnh_fields(ds)
        else:
            super()._validate_inputs(ds)

    def _track_method(self, ds):
        from frameit.processing.derived.wind import normalize_velocity_units
        from frameit.utils.units import convert_units

        native = self.model == "MNH"
        provenance = {}
        if native:
            from .pressure_centroid_inputs import prepare_mnh_inputs

            ds = prepare_mnh_inputs(ds, self.conf)
            provenance = dict(ds.attrs)
        level_dim = "level" if native else "isobaricInhPa"
        field = (lambda name: ds[name]) if native else (lambda name: self._field(ds, name))
        mslp = field("mslp")
        if "time" not in mslp.dims or mslp.ndim != 3:
            raise ValueError("pressure_centroid requires MSLP(time, y, x)")
        spatial = ("nj", "ni") if native else tuple(d for d in mslp.dims if d != "time")
        horizontal_dims = ("time", *spatial)
        vertical_dims = ("time", level_dim, *spatial)
        data = {}
        names = (("mslp", "u10m", "v10m", "u", "v", "height", "pressure")
                 if native else self.logical_fields)
        for name in names:
            da = field(name)
            if native and name == "height" and "time" not in da.dims:
                da = da.expand_dims(time=ds.time)
            expected = (vertical_dims if name in ("u", "v", "geopot", "height", "pressure")
                        else horizontal_dims)
            if set(da.dims) != set(expected):
                raise ValueError(f"pressure_centroid: {name} must have dimensions {expected}")
            data[name] = da.transpose(*expected)
        # Reject invalid chronology before loading the large vertical fields.
        motion_vectors([{"time": stamp} for stamp in ds.time.values],
                       [(0.0, 0.0)] * ds.sizes["time"])
        if not native:
            data["geopot"] = convert_units(data["geopot"], "geopotential")
        for name in ("u", "v", "u10m", "v10m"):
            da = data[name]
            data[name] = normalize_velocity_units(
                da, type("Model", (), {"atm_model": self.model})())
            if (da.attrs.get("wind_reference_frame") != "earth" if native else
                    da.attrs.get("GRIB_uvRelativeToGrid") != 0):
                raise ValueError("pressure_centroid requires earth-relative winds")
        data["mslp"] = convert_units(data["mslp"], "pressure")
        if not native:
            levels = np.asarray(convert_units(ds[level_dim], "pressure", assumed="hPa"), float)
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
                if native:
                    from .pressure_centroid_grid import StructuredGrid

                    geometry = StructuredGrid(lon, lat)
                    index = LocalGridIndex(lon, lat, area=geometry.area)
                else:
                    make_interpolator(lon, lat, np.zeros(lon.shape))
                    index = LocalGridIndex(lon, lat)
            elif not (np.array_equal(lon, reference_grid[0])
                      and np.array_equal(lat, reference_grid[1])):
                raise ValueError("pressure_centroid requires the same native grid at all times")
            rec = dict(time=stamp, lon=reference_grid[0], lat=reference_grid[1],
                       pressure_units="Pa", _grid_index=index)
            pairs = (("u", "u"), ("v", "v"), ("height", "z")) if native else (
                ("u", "u"), ("v", "v"), ("geopot", "z"))
            for logical, key in pairs:
                rec[key] = np.asarray(data[logical].isel(time=k), float)
            if native:
                rec["pressure_field_pa"] = np.asarray(data["pressure"].isel(time=k), float)
                rec["_sampler_factory"] = geometry.interpolator
            else:
                rec["pressure_levels_pa"] = levels
                rec["z"] = rec["z"] / G0
            try:
                rec["h2000"] = interpolate_to_height(rec)
                if native and not np.isfinite(rec["h2000"]["p"]).any():
                    raise ValueError(
                        "No valid pressure columns bracket 2,000 m above mean sea level")
            except ValueError as exc:
                raise ValueError(f"pressure_centroid at {stamp}: {exc}") from exc
            for key in ("u", "v", "z", "pressure_levels_pa", "pressure_field_pa"):
                rec.pop(key, None)
            pressure_index = min_index(np.asarray(data["mslp"].isel(time=k)),
                                       previous, self.half_search)
            wind = np.hypot(data["u10m"].isel(time=k), data["v10m"].isel(time=k))
            previous = min_index(np.asarray(wind), pressure_index, self.half_refine)
            guess = min_index(rec["h2000"]["p"], pressure_index, self.half_search)
            rec["guess"] = float(lon[guess]), float(lat[guess])
            records.append(rec)
        motion_vectors(records, [r["guess"] for r in records])
        try:
            centers = solve_motion_centroids(records, self.options)
        except ValueError as exc:
            if native:
                raise ValueError(
                    f"{exc}\nMNH inputs need valid pressure/wind brackets at 2,000 m ASL "
                    "over the integration region, the R80 samples and the full 500-km "
                    "reference ring. Check native-level coverage, masks and domain size."
                ) from exc
            raise
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
                         pressure_centroid_height_reference="geopotential_height",
                         pressure_centroid_reference_radius_km=500.0,
                         pressure_centroid_reference_angles=180,
                         pressure_centroid_initial_radius_km=100.0,
                         pressure_centroid_inner_tolerance_m=100.0,
                         pressure_centroid_inner_max_steps=40)
        out.attrs.update({"pressure_centroid_" + k: v for k, v in asdict(self.options).items()})
        out.attrs.update(provenance)
        if native:
            out.attrs.update(
                pressure_centroid_implementation="frameit_mnh_native_v1",
                pressure_centroid_grid="native_structured_quadrilateral",
                pressure_centroid_area_weighting="WGS84_quadrilateral_nodal",
                pressure_centroid_horizontal_interpolation="inverse_bilinear_geographic_cells",
                pressure_centroid_vertical_interpolation="linear_wind_log_pressure",
            )
        return out
