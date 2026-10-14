"""Shared, unit-aware grid inspection before scientific tracker construction."""

from __future__ import annotations

import numpy as np
import xarray as xr
from pyproj import Geod

from frameit.utils.units import convert_units, normalize_geography


def inspect_grid(ds, conf):
    """Estimate both axes robustly; retain variability instead of hiding it.

    Up to 33 locations per axis sample the regional grid. Projected Cartesian
    coordinates with explicit length units take precedence over geodesics.
    """
    ds = normalize_geography(ds, conf)
    lat, lon = ds[conf.name_latitude], ds[conf.name_longitude]
    if "time" in lat.dims:
        lat = lat.isel(time=0)
    if "time" in lon.dims:
        lon = lon.isel(time=0)
    lat, lon = xr.broadcast(lat, lon)
    ydim, xdim = conf.name_lat_dim, conf.name_lon_dim
    if ydim not in lat.dims or xdim not in lat.dims:
        # Normalized AROME coordinates are themselves the dimension names.
        if lat.ndim != 2:
            raise ValueError("Grid inspection requires two horizontal dimensions")
        ydim, xdim = lat.dims
    if ds.sizes[ydim] < 2 or ds.sizes[xdim] < 2:
        raise ValueError("Grid inference needs at least two points on each horizontal axis")
    ys = np.unique(np.linspace(0, ds.sizes[ydim] - 1, min(33, ds.sizes[ydim])).astype(int))
    xs = np.unique(np.linspace(0, ds.sizes[xdim] - 1, min(33, ds.sizes[xdim])).astype(int))
    sample = dict(zip((ydim, xdim), (ys, xs), strict=True))
    latitude = lat.transpose(ydim, xdim)
    longitude = lon.transpose(ydim, xdim)
    lat = np.asarray(latitude.isel(sample), float)
    lon = np.asarray(longitude.isel(sample), float)
    if not np.isfinite(lat).all() or not np.isfinite(lon).all() or np.any(np.abs(lat) > 90):
        raise ValueError("Grid coordinates must be finite geographic degrees")
    distances = []
    sources = []
    geod = Geod(ellps="WGS84")
    for dim, indices in ((xdim, xs), (ydim, ys)):
        coord = ds.coords.get(dim)
        length_units = coord is not None and coord.attrs.get("units")
        try:
            projected = convert_units(coord, "distance") if length_units else None
        except ValueError:
            projected = None
        if projected is not None and projected.ndim == 1:
            differences = np.diff(np.asarray(projected, float))
            if not (np.all(differences > 0) or np.all(differences < 0)):
                raise ValueError(f"Projected coordinate {dim} must be strictly monotone")
            values = np.abs(differences)
            source = f"projected_coordinate:{dim}"
        else:
            # Sample actual adjacent cells, not long chords divided by skipped
            # grid points (which can hide curvature or local spacing changes).
            start = dict(sample)
            start[dim] = np.unique(np.minimum(indices, ds.sizes[dim] - 2))
            end = {**start, dim: start[dim] + 1}
            _, _, values = geod.inv(
                np.asarray(longitude.isel(start)), np.asarray(latitude.isel(start)),
                np.asarray(longitude.isel(end)), np.asarray(latitude.isel(end)),
            )
            source = "geodesic:WGS84"
        values = np.asarray(values).ravel()
        if not np.isfinite(values).all() or np.any(values <= 0):
            raise ValueError(f"Unusable spacing along {dim}")
        median = float(np.median(values))
        distances.append({"spacing_m": median,
                          "relative_variability": float(np.max(np.abs(values / median - 1))),
                          "min_m": float(np.min(values)), "max_m": float(np.max(values))})
        sources.append(source)
    return {"x": distances[0], "y": distances[1], "sources": sources,
            "shape": [ds.sizes[ydim], ds.sizes[xdim]],
            "coordinate_names": [conf.name_latitude, conf.name_longitude],
            "sample_lon": lon.tolist(), "sample_lat": lat.tolist()}


def resolve_geometry(conf, datasets):
    """Reject geometry unsupported by current scalar-spacing algorithms.

    Qualification limits: <=10% X/Y difference and <=20% within-axis variation.
    An override supplies nominal spacing but never bypasses geometry validation.
    """
    def spatial_records():
        for dataset in datasets:
            if conf.name_latitude not in dataset or conf.name_longitude not in dataset:
                continue
            for dim in ("time", conf.name_time_dim):
                if (dim in dataset[conf.name_latitude].dims
                        or dim in dataset[conf.name_longitude].dims):
                    for index in range(dataset.sizes[dim]):
                        yield dataset.isel({dim: index})
                    break
            else:
                yield dataset

    reference = None
    for ds in spatial_records():
        if conf.name_latitude not in ds or conf.name_longitude not in ds:
            continue
        info = inspect_grid(ds, conf)
        if reference is not None:
            if info["shape"] != reference["shape"] or not all(
                np.allclose(info[k], reference[k], rtol=0, atol=1e-8)
                for k in ("sample_lon", "sample_lat")
            ):
                raise ValueError("Selected inputs have incompatible native grid geometry")
        else:
            reference = info
    if reference is None:
        raise ValueError("Cannot infer grid geometry: missing usable geographic coordinates")
    dx, dy = (reference[a]["spacing_m"] for a in ("x", "y"))
    if max(dx, dy) / min(dx, dy) - 1 > .10:
        raise ValueError(
            "Anisotropic grid (>10% X/Y difference) is unsupported by current trackers/extraction"
        )
    if max(reference[a]["relative_variability"] for a in ("x", "y")) > .20:
        raise ValueError("Nonuniform grid (>20% spacing variability) is unsupported")
    override = conf.yaml_config.get("input", {}).get("grid_spacing_m")
    conf.resolution = float(override) if override is not None else (dx + dy) / 2
    reference["effective_spacing_m"] = conf.resolution
    reference["effective_source"] = "input.grid_spacing_m" if override is not None else "inferred"
    conf.grid_geometry = reference
    if conf.compute_polar_proj and not conf.radial_resolution:
        conf.radial_resolution = conf.resolution
    conf.__post_init__()
    conf.add_parameter("grid_geometry", reference)
    return reference
