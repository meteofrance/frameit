# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Labelled time alignment and finite structured geometry for polar sampling."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from copy import copy, deepcopy
from time import perf_counter

import numpy as np
import xarray as xr


def require_executable_products(binding, source):
    """Admit polar only with its complete, source-owned preparation and target plan."""
    if not isinstance(binding, dict) or binding.get("status") != "bound" or source is None:
        raise ValueError("Selected products require bound requests and owning source metadata")
    products = binding.get("products", {})
    if set(products) - {"model_grid", "polar"}:
        raise ValueError("Unknown selected field product")
    if "polar" not in products:
        return
    if (source.get("requests", {}).get("binding") or {}).get("status") != "bound":
        raise ValueError("Polar products require the bound owning source snapshot")
    plan = binding.get("polar_plan") or {}
    if plan.get("status") != "bound":
        raise ValueError("Polar product requires a bound executable polar plan")
    from frameit.processing.polar.sampling import uniform_periodic_angles, validate_axes

    try:
        validate_axes(np.asarray(plan["radius_km"]), np.asarray(plan["azimuth_degrees"]))
        if not uniform_periodic_angles(plan["azimuth_degrees"]):
            raise ValueError("Polar azimuths must form a full open clockwise ring")
        jobs = [job for job in binding["operation_plans"] if job["product"] == "polar"]
        if not jobs or {job["name"] for job in jobs} != set(products["polar"]):
            raise ValueError("Polar jobs do not match requested product descriptors")
        spacing = np.asarray(plan["native_spacing_m"])
        if (not spacing.size or not np.isfinite(spacing).all() or np.any(spacing <= 0)
                or not np.isfinite(plan["radial_step_km"]) or plan["radial_step_km"] <= 0
                or plan["radial_step_km"] * 1000 < spacing.max() * (1 - 1e-12)):
            raise ValueError("Polar native-spacing evidence is missing")
        for job in jobs:
            sampled = ({job["inputs"]["field"]} if job["method"] == "polar_input"
                       else set(job["inputs"].values()))
            if (job["input_binding"]["status"] != "bound"
                    or set(job["polar_options"]) != sampled
                    or not job["polar_geometry"]
                    or products["polar"][job["name"]].get("execution") != "bound_polar_sampling"):
                raise ValueError("Polar preparation or interpolation evidence is incomplete")
            geometry = job["polar_geometry"]
            lon, lat = np.asarray(geometry["longitude"]), np.asarray(geometry["latitude"])
            if (lon.shape != lat.shape or lon.ndim != 2 or min(lon.shape) < 2
                    or not np.isfinite(lon).all() or not np.isfinite(lat).all()):
                raise ValueError("Polar prepared geometry is invalid")
            _validate_cells(lon, lat)
            for name, descriptor in job["input_binding"]["dependencies"].items():
                if not descriptor["records"]:
                    raise ValueError(f"Polar input {name} has no bound native support")
                for record in descriptor["records"]:
                    matches = []
                    for native in source["record_inventory"]:
                        if (record["field_id"] != native["field_id"]
                                or record["time"] != native["time"]
                                or record["cycle"] != native["cycle"]
                                or record.get("native_axes") != native.get("native_axes")):
                            continue
                        locator = dict(native["locator"])
                        if "records" in locator:
                            if source["fields"][record["field_id"]].get("native_cube"):
                                locator["records"] = [
                                    locator["records"][i] for i in record["source_positions"]]
                            elif (record["source_positions"] is not None
                                  or record["vertical"] is not None):
                                raise ValueError("A 2-D FA record has no selectable vertical axis")
                        matches.append(record["locator"] == locator)
                    if not any(matches):
                        raise ValueError("Polar input is outside the owning selected inventory")
            for options in job["polar_options"].values():
                if options["interpolation"] not in {"bilinear", "nearest_s2d"}:
                    raise ValueError("Polar interpolation method is not executable")
                from frameit.processing.polar.coverage import validate_mask_options

                validate_mask_options(options["missing_data_policy"],
                                      options["min_valid_weight_fraction"], 0)
    except (KeyError, TypeError, AttributeError, IndexError, ValueError) as exc:
        raise ValueError(f"Polar plan evidence is missing or invalid: {exc}") from exc


def polar_field_options(metadata, options, conf, context):
    """Resolve interpolation without requiring or inferring field kind."""
    attrs, origins = metadata["attributes"], metadata["origins"]
    kind = attrs.get("kind")
    # Missing kind is intentional: bilinear is a method default, not a classification.
    if "kind" in attrs and (not isinstance(kind, str) or kind not in {"continuous", "categorical"}):
        raise ValueError(f"{context}: invalid kind {kind!r}; use continuous or categorical")
    method = options.get("interpolation", "nearest" if kind == "categorical" else "bilinear")
    if kind == "categorical" and method != "nearest":
        raise ValueError(f"{context}: categorical fields require nearest interpolation")
    policy = options.get("missing_data_policy", conf.polar_missing_data_policy)
    minimum = options.get("min_valid_weight_fraction", conf.polar_min_valid_weight_fraction)
    if method == "nearest" and policy != "strict":
        raise ValueError(f"{context}: nearest interpolation cannot renormalize partial stencils")
    from frameit.processing.polar.coverage import validate_mask_options

    validate_mask_options(policy, minimum, conf.polar_weight_zero_tolerance)
    return {
        **({"kind": kind, "kind_origin": origins["kind"]} if kind is not None else {}),
        "interpolation": "nearest_s2d" if method == "nearest" else method,
        "missing_data_policy": policy, "min_valid_weight_fraction": minimum,
        "sampling": options.get("sampling", "native"),
    }


def polar_source_geometry(job, conf):
    """Normalize this actual prepared sample grid, without reading scientific fields."""
    from frameit.core.grid_geometry import inspect_grid
    from frameit.processing.dims_utils import horizontal_axes

    geometry = xr.Dataset(coords={
        name: xr.Variable(item["dimensions"], item["values"], item["attributes"])
        for name, item in job["grid"]["coordinates"].items()})
    axes = horizontal_axes(conf)[1]
    axes.update(y="y", x="x")
    dims = job["grid"]["dimensions"]
    settings = copy(conf)
    names = {}
    for kind, conventional in (
            ("latitude", {"latitude", "nav_lat", "lat_rho", "lat_u", "lat_v",
                          "latitude_u", "latitude_v"}),
            ("longitude", {"longitude", "nav_lon", "lon_rho", "lon_u", "lon_v",
                           "longitude_u", "longitude_v"})):
        candidates = [name for name, value in geometry.coords.items()
                      if (value.attrs.get("standard_name") == kind or name in conventional)
                      and set(value.dims) <= set(dims) and value.ndim > 0]
        if len(candidates) != 1:
            raise ValueError(
                f"{job['name']}: polar {kind} is missing or ambiguous on prepared grid")
        names[kind] = candidates[0]
        setattr(settings, f"name_{kind}", candidates[0])
    spatial = set(geometry[names["latitude"]].dims) | set(geometry[names["longitude"]].dims)
    horizontal = {}
    for axis in ("y", "x"):
        candidates = [dim for dim in spatial if axes.get(dim) == axis or (
            dim in geometry.coords and geometry[dim].attrs.get("axis") == axis.upper())]
        if len(spatial) != 2 or len(candidates) != 1:
            raise ValueError(f"{job['name']}: polar sampling requires evidenced horizontal axes")
        horizontal[axis] = candidates[0]
        setattr(settings, "name_lat_dim" if axis == "y" else "name_lon_dim", candidates[0])
    evidence = inspect_grid(geometry, settings)
    normalized = xr.Dataset(coords={
        kind: geographic_degrees(geometry[name]).rename(
            {dim: f"{axis}_box" for axis, dim in horizontal.items()
             if dim in geometry[name].dims})
        for kind, name in names.items()})
    _, grid, footprint = finite_source_footprint(normalized, "longitude", "latitude")
    return {
        "horizontal_dimensions": horizontal, "coordinate_names": names,
        "longitude": np.asarray(grid.lon), "latitude": np.asarray(grid.lat),
        "footprint": footprint, "spacing": evidence,
    }


def time_index(ds: xr.Dataset, context: str):
    if "time" not in ds.coords or ds.time.dims != ("time",) or not ds.time.size:
        raise ValueError(f"{context} requires a non-empty labelled time(time) coordinate")
    index = ds.time.to_index()
    if not index.is_unique or bool(ds.time.isnull().any()):
        raise ValueError(f"{context} contains duplicate or missing time labels")
    return index


def _time_kind(index):
    if hasattr(index, "calendar"):
        return "calendar", index.calendar
    dtype = np.asarray(index.values).dtype
    if np.issubdtype(dtype, np.datetime64):
        return "datetime", None
    if np.issubdtype(dtype, np.number):
        return "numeric", None
    return str(dtype), None


def align_times(ds: xr.Dataset, reference: xr.DataArray, context: str, *, exact=True):
    source = time_index(ds, context)
    expected = reference.to_index()
    if _time_kind(source) != _time_kind(expected):
        raise ValueError(f"{context} has an incompatible time representation or calendar")
    if (exact and len(source) != len(expected)) or np.any(source.get_indexer(expected) < 0):
        raise ValueError(f"{context} does not contain exactly the required reference times")
    result = ds.sel(time=reference.values)
    # Keep labels/attributes without carrying reference-group scalar coordinates.
    result = result.assign_coords(time=reference.variable)
    return result


def source_lonlat(ds: xr.Dataset, lon_name: str, lat_name: str):
    if lon_name not in ds or lat_name not in ds:
        raise ValueError("Source grid requires geographic longitude and latitude")
    lon, lat = xr.broadcast(geographic_degrees(ds[lon_name]), geographic_degrees(ds[lat_name]))
    if set(lon.dims) != {"y_box", "x_box"} or set(lat.dims) != {"y_box", "x_box"}:
        raise ValueError("Source geography must use named y_box/x_box dimensions")
    lon = np.asarray(lon.transpose("y_box", "x_box").values, dtype=float)
    lat = np.asarray(lat.transpose("y_box", "x_box").values, dtype=float)
    if lon.shape != (ds.sizes["y_box"], ds.sizes["x_box"]) or lat.shape != lon.shape:
        raise ValueError("Source geographic coordinates do not match the field grid")
    return lon, lat


def geographic_degrees(coordinate):
    if coordinate.attrs.get("standard_name") in {"grid_latitude", "grid_longitude"}:
        raise ValueError("Rotated-grid coordinates are not geographic longitude/latitude")
    units = coordinate.attrs.get("units", "degree")
    if units in {"rad", "radian", "radians"}:
        result = np.rad2deg(coordinate)
        result.attrs = {**coordinate.attrs, "units": "degree"}
        return result
    if units not in {"degree", "degrees", "degree_east", "degree_north",
                      "degrees_east", "degrees_north"}:
        raise ValueError("Geographic coordinates must be angular degrees or radians")
    return coordinate


def finite_source_footprint(ds: xr.Dataset, lon_name: str, lat_name: str):
    """Trim NaN-padded domain edges; never fabricate coordinates inside a grid."""
    lon, lat = source_lonlat(ds, lon_name, lat_name)
    finite = np.isfinite(lon) & np.isfinite(lat)
    rows, cols = np.where(finite)
    if not rows.size:
        raise ValueError("Source footprint has no finite geographic coordinates")
    y_slice = slice(int(rows.min()), int(rows.max()) + 1)
    x_slice = slice(int(cols.min()), int(cols.max()) + 1)
    lon, lat = lon[y_slice, x_slice], lat[y_slice, x_slice]
    if not np.isfinite(lon).all() or not np.isfinite(lat).all():
        raise ValueError("Missing geographic coordinates inside the source footprint")
    if min(lon.shape) < 2:
        raise ValueError("Source footprint needs at least two points along each horizontal axis")
    if np.any(np.abs(lat) > 90):
        raise ValueError("Source latitude must lie within [-90, 90] degrees")
    # Unwrap coordinates without reordering points or changing cell connectivity.
    lon = np.rad2deg(np.unwrap(np.unwrap(np.deg2rad(lon), axis=1), axis=0))
    _validate_cells(lon, lat)
    grid = xr.Dataset({
        "lon": (("y_box", "x_box"), np.ascontiguousarray(lon)),
        "lat": (("y_box", "x_box"), np.ascontiguousarray(lat)),
    })
    footprint = {
        "original_shape": [ds.sizes["y_box"], ds.sizes["x_box"]],
        "finite_shape": list(lon.shape),
        "y_slice": [y_slice.start, y_slice.stop], "x_slice": [x_slice.start, x_slice.stop],
    }
    return ds.isel(y_box=y_slice, x_box=x_slice), grid, footprint


def _validate_cells(lon, lat):
    """Require a nonfolded regional quadrilateral grid in unwrapped lon/lat."""
    east_x, east_y = lon[:-1, 1:] - lon[:-1, :-1], lat[:-1, 1:] - lat[:-1, :-1]
    diag_x, diag_y = lon[1:, 1:] - lon[:-1, :-1], lat[1:, 1:] - lat[:-1, :-1]
    south_x, south_y = lon[1:, :-1] - lon[:-1, :-1], lat[1:, :-1] - lat[:-1, :-1]
    first = east_x * diag_y - east_y * diag_x
    second = diag_x * south_y - diag_y * south_x
    scale = np.maximum(east_x**2 + east_y**2, south_x**2 + south_y**2)
    tolerance = 1e-12 * scale
    if np.any(np.abs(first) <= tolerance) or np.any(np.abs(second) <= tolerance):
        raise ValueError("Source grid contains degenerate cells")
    signs = np.sign(first)
    if np.any(signs != np.sign(second)) or np.any(signs != signs.flat[0]):
        raise ValueError("Source grid contains folded or inconsistent cell connectivity")


def target_locstream(lon, lat):
    lon, lat = np.asarray(lon), np.asarray(lat)
    if lon.shape != lat.shape or not np.isfinite(lon).all() or not np.isfinite(lat).all():
        raise ValueError("Target geographic coordinates must be finite and consistently shaped")
    if np.any(np.abs(lat) > 90):
        raise ValueError("Target latitude must lie within [-90, 90] degrees")
    return xr.Dataset({"lon": ("locations", lon.ravel()), "lat": ("locations", lat.ravel())})


def same_source_geometry(ds: xr.Dataset, lon_name: str, lat_name: str, *, geometry_cache=None):
    if geometry_cache is not None:
        _, first_grid, first_footprint = geometry_cache.get(
            ds.isel(time=0, drop=True), lon_name, lat_name
        )
        for index in range(1, ds.sizes["time"]):
            _, grid, footprint = geometry_cache.get(
                ds.isel(time=index, drop=True), lon_name, lat_name
            )
            if footprint != first_footprint or not all(np.array_equal(first_grid[name], grid[name])
                                                       for name in ("lon", "lat")):
                return False
        return True
    first = source_lonlat(ds.isel(time=0, drop=True), lon_name, lat_name)
    return all(
        all(np.array_equal(a, b, equal_nan=True) for a, b in zip(
            first, source_lonlat(ds.isel(time=index, drop=True), lon_name, lat_name), strict=True
        )) for index in range(1, ds.sizes["time"])
    )


class SourceGeometryCache:
    """Bounded normalized-coordinate reuse, with no source field data retained.

    NumPy coordinates use content fingerprints (not mutable object identities).
    Dask coordinates use immutable graph tokens, avoiding repeat materialization
    of identical geographical arrays. Input files must remain unchanged, as in
    the ordinary execution inventory contract.
    """

    def __init__(self, maxsize=8, max_bytes=8 * 1024**2):
        self.maxsize, self.max_bytes = maxsize, max_bytes
        self._entries = OrderedDict()
        self._bytes = 0
        self.hits, self.misses, self.evictions = 0, 0, 0
        self.normalization_s, self.fingerprint_s = 0., 0.
        self._timed_calls = dict(normalization_s=0, fingerprint_s=0)

    def get(self, source, lon_name, lat_name, *, profile=True):
        if not isinstance(profile, bool):
            raise ValueError("profile must be boolean")
        started = perf_counter() if profile else None
        digest = hashlib.sha256()
        for name in (lon_name, lat_name):
            coord = source[name]
            metadata = (coord.dims, coord.shape, str(coord.dtype),
                        coord.attrs.get("units"), coord.attrs.get("standard_name"))
            digest.update(json.dumps(metadata).encode())
            if hasattr(coord.data, "__dask_graph__"):
                from dask.base import tokenize

                digest.update(tokenize(coord.data).encode())
            else:
                array = np.ascontiguousarray(coord.data)
                digest.update(memoryview(array).cast("B"))
        key = digest.hexdigest()
        if profile:
            self.fingerprint_s += perf_counter() - started
            self._timed_calls["fingerprint_s"] += 1
        if key in self._entries:
            self.hits += 1
            self._entries.move_to_end(key)
            grid, footprint, _ = self._entries[key]
        else:
            self.misses += 1
            started = perf_counter() if profile else None
            _, grid, footprint = finite_source_footprint(source, lon_name, lat_name)
            grid = grid.copy(deep=True)
            grid.lon.data.setflags(write=False)
            grid.lat.data.setflags(write=False)
            if profile:
                self.normalization_s += perf_counter() - started
                self._timed_calls["normalization_s"] += 1
            size = grid.lon.data.nbytes + grid.lat.data.nbytes
            if self.maxsize and size <= self.max_bytes:
                while self._entries and (len(self._entries) >= self.maxsize or
                                         self._bytes + size > self.max_bytes):
                    _, (_, _, removed_bytes) = self._entries.popitem(last=False)
                    self._bytes -= removed_bytes
                    self.evictions += 1
                self._entries[key] = grid, footprint, size
                self._bytes += size
        cropped = source.isel(y_box=slice(*footprint["y_slice"]),
                              x_box=slice(*footprint["x_slice"]))
        return cropped, grid, deepcopy(footprint)

    def statistics(self, *, profile=True):
        if not isinstance(profile, bool):
            raise ValueError("profile must be boolean")
        return dict(hits=self.hits, misses=self.misses, evictions=self.evictions,
                    normalization_s=(self.normalization_s
                                     if profile and self._timed_calls["normalization_s"] else None),
                    fingerprint_s=(self.fingerprint_s
                                   if profile and self._timed_calls["fingerprint_s"] else None),
                    timing={"enabled": profile, "measured_calls": dict(self._timed_calls),
                            "scope": "cumulative timed cache calls; excludes unmeasured calls"},
                    retained_entries=len(self._entries), retained_bytes=self._bytes,
                    max_entries=self.maxsize, max_bytes=self.max_bytes)
