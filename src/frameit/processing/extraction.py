# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
from collections.abc import Hashable, Iterable
from copy import deepcopy

import numpy as np
import xarray as xr

from .derived.wind import add_speed_from_uv_dict
from .dims_utils import horizontal_axes, normalize_dims_for_extraction
from .polar.metadata import preserve_coordinate_dependencies

logger = logging.getLogger(__name__)


def polar_support_settings(conf, track_box):
    """Expand actual extraction index half-widths by the requested native halo.

    Using already rounded widths avoids losing a halo point to half-integer
    round-to-even behaviour when translating kilometres back to indices.
    """
    support = deepcopy(conf)
    halo = getattr(conf, "polar_source_halo_points", 1)
    scale = float(conf.resolution) / 1000
    support.x_boxsize_km = 2 * (track_box.attrs["box_half_width_x_points"] + halo) * scale
    support.y_boxsize_km = 2 * (track_box.attrs["box_half_width_y_points"] + halo) * scale
    return support


def _iter_datasets(tree) -> Iterable[xr.Dataset]:
    """Yield all xarray.Dataset objects found recursively in a nested dict."""
    if isinstance(tree, xr.Dataset):
        yield tree
    elif isinstance(tree, dict):
        for v in tree.values():
            yield from _iter_datasets(v)


def infer_domain_shape_from_tracker(
    ds_tracker: dict | xr.Dataset,
    conf,
) -> tuple[int, int]:
    """
    Infer the horizontal domain size (nx, ny) from tracker coordinate arrays.

    Searches recursively through ``ds_tracker`` for a dataset that contains
    the lat/lon coordinates named in ``conf``.

    Parameters
    ----------
    ds_tracker : dict or xr.Dataset
        Hierarchical or flat tracker dataset structure.
    conf : object
        Configuration object.  Reads ``name_latitude`` and ``name_longitude``
        (defaults: "latitude", "longitude").

    Returns
    -------
    nx : int
        Number of grid points along the x (longitude) axis.
    ny : int
        Number of grid points along the y (latitude) axis.

    Raises
    ------
    RuntimeError
        If no dataset containing the expected lat/lon coordinates is found.
    """
    lat_name = getattr(conf, "name_latitude", "latitude")
    lon_name = getattr(conf, "name_longitude", "longitude")

    for ds in _iter_datasets(ds_tracker):
        if not isinstance(ds, xr.Dataset):
            continue
        if lat_name in ds.coords and lon_name in ds.coords:
            lat = ds[lat_name]
            lon = ds[lon_name]
            (y, x), _ = horizontal_axes(conf)
            if {y, x} <= set(lat.dims) and {y, x} <= set(lon.dims):
                if any(lat.sizes[d] != lon.sizes[d] for d in (y, x)):
                    raise ValueError("Latitude and longitude horizontal sizes must match")
                return lat.sizes[x], lat.sizes[y]

            # 1D case (AROME-type)
            if lat.ndim == 1 and lon.ndim == 1:
                ny = lat.size
                nx = lon.size
                logger.debug("Domain size inferred from 1D lat/lon: nx=%d, ny=%d", nx, ny)
                return nx, ny

            # 2D case (MNH-type)
            if lat.ndim == 2 and lon.ndim == 2:
                if lat.shape != lon.shape:
                    raise ValueError("Latitude and longitude must have identical shapes")
                ny, nx = lat.shape
                logger.debug("Domain size inferred from 2D lat/lon: nx=%d, ny=%d", nx, ny)
                return nx, ny

    raise RuntimeError(
        f"Could not infer nx, ny: no dataset with coordinates {lat_name!r}, {lon_name!r}"
    )


def center2box(
    track_ds: xr.Dataset,
    x_size_km: float,
    y_size_km: float,
    resolution_m: float,
    nx: int,
    ny: int,
    center_x_var: Hashable = "cx",
    center_y_var: Hashable = "cy",
    inplace: bool = True,
) -> xr.Dataset:
    """
    Compute, for each time, the indices of a fixed-size box around the cyclone
    center, together with a flag indicating whether the box is fully inside
    the model domain.

    The ideal box:
      - is always centered on the tracked point,
      - has a constant size in grid points for all times,
      - may extend outside the domain.

    Parameters
    ----------
    track_ds : xr.Dataset
        Dataset containing at least:
        - a 1D coordinate (typically "time"),
        - a variable `center_x_var` (e.g. "cx") with the cyclone center index along x,
        - a variable `center_y_var` (e.g. "cy") with the cyclone center index along y.
        The center indices are expected to follow Python conventions (0 based).
    x_size_km : float
        Full width of the box along the x axis, in kilometers.
    y_size_km : float
        Full height of the box along the y axis, in kilometers.
    resolution_m : float
        Isotropic horizontal grid spacing, in meters (dx = dy = resolution).
    nx : int
        Number of grid points along the x axis of the model domain.
    ny : int
        Number of grid points along the y axis of the model domain.
    center_x_var : Hashable, optional
        Name of the variable holding the center index along x. Default "cx".
    center_y_var : Hashable, optional
        Name of the variable holding the center index along y. Default "cy".
    inplace : bool, optional
        If True, the input dataset is modified in place.
        If False, a shallow copy is created and returned.

    Returns
    -------
    xr.Dataset
        Same dataset, enriched with the following 1D variables
        (dimension identical to the center variables, typically "time"):

        Ideal bounds (always centered, can lie outside the domain):
          - ix_min(time), ix_max(time)
          - iy_min(time), iy_max(time)

        Bounds intersected with the domain:
          - ix_min_domain(time), ix_max_domain(time)
          - iy_min_domain(time), iy_max_domain(time)

        Validity flag:
          - valid_box(time): True if the ideal box is fully inside the domain,
            False otherwise.

        The dataset attributes are also updated with:

          - box_resolution_m : float
          - box_x_size_km : float
          - box_y_size_km : float
          - box_half_width_x_points : int
          - box_half_width_y_points : int
          - box_nx_points : int  (full width in points)
          - box_ny_points : int  (full height in points)
    """
    if resolution_m <= 0:
        raise ValueError("resolution_m must be positive")

    if nx <= 0 or ny <= 0:
        raise ValueError("nx and ny must be positive")

    # Retrieve center coordinates (indices)
    if center_x_var not in track_ds or center_y_var not in track_ds:
        raise KeyError(
            f"center_x_var='{center_x_var}' or center_y_var='{center_y_var}' not found in track_ds"
        )

    cx = track_ds[center_x_var]
    cy = track_ds[center_y_var]

    if cx.dims != cy.dims:
        raise ValueError("center_x_var and center_y_var must have identical dimensions")

    if cx.ndim != 1:
        raise ValueError("center coordinates must be one dimensional")

    time_dim = cx.dims[0]
    time_coord = cx.coords[time_dim].variable

    # Convert box sizes to half widths in grid points
    res_km = resolution_m / 1000.0
    half_x_km = x_size_km / 2.0
    half_y_km = y_size_km / 2.0

    nx_half = int(np.round(half_x_km / res_km))
    ny_half = int(np.round(half_y_km / res_km))

    if nx_half < 0 or ny_half < 0:
        raise ValueError(
            "Computed half widths in grid points are negative, "
            "check x_size_km, y_size_km and resolution_m"
        )

    # Center indices as integers (rounded, in case cx/cy are floats)
    cx_vals = np.asarray(cx.values, dtype=float)
    cy_vals = np.asarray(cy.values, dtype=float)

    if np.isnan(cx_vals).any() or np.isnan(cy_vals).any():
        raise ValueError("Center indices contain NaN, center2box expects finite centers")

    ix_center = np.rint(cx_vals).astype(np.int64)
    iy_center = np.rint(cy_vals).astype(np.int64)

    # Ideal box bounds (always centered, constant size, may be outside domain)
    ix_min = ix_center - nx_half
    ix_max = ix_center + nx_half
    iy_min = iy_center - ny_half
    iy_max = iy_center + ny_half

    # Bounds intersected with the domain [0, nx-1] Ã— [0, ny-1]
    ix_min_domain = np.clip(ix_min, 0, nx - 1)
    ix_max_domain = np.clip(ix_max, 0, nx - 1)
    iy_min_domain = np.clip(iy_min, 0, ny - 1)
    iy_max_domain = np.clip(iy_max, 0, ny - 1)

    # Box is valid if the ideal bounds are fully inside the domain
    valid_x = (ix_min >= 0) & (ix_max < nx)
    valid_y = (iy_min >= 0) & (iy_max < ny)
    valid_box = valid_x & valid_y

    # Prepare output dataset
    ds_out = track_ds if inplace else track_ds.copy()

    # Ideal bounds
    ds_out["ix_min"] = xr.DataArray(
        ix_min,
        dims=(time_dim,),
        coords={time_dim: time_coord},
        name="ix_min",
    )
    ds_out["ix_max"] = xr.DataArray(
        ix_max,
        dims=(time_dim,),
        coords={time_dim: time_coord},
        name="ix_max",
    )
    ds_out["iy_min"] = xr.DataArray(
        iy_min,
        dims=(time_dim,),
        coords={time_dim: time_coord},
        name="iy_min",
    )
    ds_out["iy_max"] = xr.DataArray(
        iy_max,
        dims=(time_dim,),
        coords={time_dim: time_coord},
        name="iy_max",
    )

    # Bounds intersected with the domain
    ds_out["ix_min_domain"] = xr.DataArray(
        ix_min_domain,
        dims=(time_dim,),
        coords={time_dim: time_coord},
        name="ix_min_domain",
    )
    ds_out["ix_max_domain"] = xr.DataArray(
        ix_max_domain,
        dims=(time_dim,),
        coords={time_dim: time_coord},
        name="ix_max_domain",
    )
    ds_out["iy_min_domain"] = xr.DataArray(
        iy_min_domain,
        dims=(time_dim,),
        coords={time_dim: time_coord},
        name="iy_min_domain",
    )
    ds_out["iy_max_domain"] = xr.DataArray(
        iy_max_domain,
        dims=(time_dim,),
        coords={time_dim: time_coord},
        name="iy_max_domain",
    )

    ds_out["valid_box"] = xr.DataArray(
        valid_box.astype(bool),
        dims=(time_dim,),
        coords={time_dim: time_coord},
        name="valid_box",
    )

    # Record configuration in attributes
    box_nx = 2 * nx_half + 1
    box_ny = 2 * ny_half + 1

    attrs = dict(ds_out.attrs)
    attrs["box_resolution_m"] = float(resolution_m)
    attrs["box_x_size_km"] = float(x_size_km)
    attrs["box_y_size_km"] = float(y_size_km)
    attrs["box_half_width_x_points"] = int(nx_half)
    attrs["box_half_width_y_points"] = int(ny_half)
    attrs["box_nx_points"] = int(box_nx)
    attrs["box_ny_points"] = int(box_ny)
    ds_out.attrs = attrs

    return ds_out


def _build_box_indexers(track_box: xr.Dataset, nx: int, ny: int, resolution_m: float):
    """
    Build time-dependent indexers to extract a box centred on the cyclone,
    using the ideal bounds (ix_min, iy_min) computed by center2box.

    Assumptions
    -----------
    - track_box contains at least ix_min(time), iy_min(time) and the attributes
      box_nx_points, box_ny_points, box_half_width_x_points,
      box_half_width_y_points.
    - ix_min/iy_min are the ideal box bounds [ix_min..ix_max] x [iy_min..iy_max].

    Returns
    -------
    x_idx : xr.DataArray
        Global x indices, shape (time, x_box).
    y_idx : xr.DataArray
        Global y indices, shape (time, y_box).
    mask_box : xr.DataArray (bool)
        Mask (time, y_box, x_box), False only where the box falls outside the domain.
    x_box : xr.DataArray
        Local point offsets, dims ("x_box",), centred on 0.
    y_box : xr.DataArray
        Local point offsets, dims ("y_box",), centred on 0.
    x_box_km, y_box_km : xr.DataArray
        Local offsets in km.
    """

    # Reference time dimension
    time_var = track_box["ix_min"]
    time_dim = time_var.dims[0]
    # A track can carry sampled source-grid coordinates along time. Indexers
    # must carry only the time labels, not those unrelated spatial coordinates.
    time_coord = time_var.coords[time_dim].variable

    # Box geometry
    box_nx = int(track_box.attrs["box_nx_points"])
    box_ny = int(track_box.attrs["box_ny_points"])
    nx_half = int(track_box.attrs.get("box_half_width_x_points", (box_nx - 1) // 2))
    ny_half = int(track_box.attrs.get("box_half_width_y_points", (box_ny - 1) // 2))

    if box_nx != 2 * nx_half + 1 or box_ny != 2 * ny_half + 1:
        logger.warning(
            "Inconsistent box geometry: box_nx=%d, nx_half=%d; box_ny=%d, ny_half=%d",
            box_nx,
            nx_half,
            box_ny,
            ny_half,
        )

    # Local indices 0..N-1
    i = np.arange(box_nx, dtype=np.int64)  # local x index
    j = np.arange(box_ny, dtype=np.int64)  # local y index

    # Ideal minimum indices (can be <0 or >nx-1, ny-1)
    ix_min = np.asarray(track_box["ix_min"].values, dtype=np.int64)  # (ntime,)
    iy_min = np.asarray(track_box["iy_min"].values, dtype=np.int64)  # (ntime,)

    # Ideal global box indices:
    #   [ix_min..ix_max] = ix_min + [0..box_nx-1]
    #   [iy_min..iy_max] = iy_min + [0..box_ny-1]
    x_idx_ideal = ix_min[:, None] + i[None, :]  # (time, x_box)
    y_idx_ideal = iy_min[:, None] + j[None, :]  # (time, y_box)

    # Domain masks
    mask_x = (x_idx_ideal >= 0) & (x_idx_ideal < nx)
    mask_y = (y_idx_ideal >= 0) & (y_idx_ideal < ny)

    # Indices clipped to domain bounds
    x_idx = np.clip(x_idx_ideal, 0, nx - 1)
    y_idx = np.clip(y_idx_ideal, 0, ny - 1)

    # 3D mask in the local box: (time, y_box, x_box)
    mask_box_np = mask_y[:, :, None] & mask_x[:, None, :]

    # Local coordinates centred on the box centre
    x_box = xr.DataArray(i - nx_half, dims=("x_box",), name="x_box")
    y_box = xr.DataArray(j - ny_half, dims=("y_box",), name="y_box")

    # Coordinates in km
    res_km = resolution_m / 1000.0
    x_box_km = x_box * res_km
    y_box_km = y_box * res_km
    x_box.attrs.update(units="1", long_name="x grid-point offset from extraction centre")
    y_box.attrs.update(units="1", long_name="y grid-point offset from extraction centre")
    x_box_km.attrs.update(units="km", long_name="x distance offset from extraction centre")
    y_box_km.attrs.update(units="km", long_name="y distance offset from extraction centre")

    # Wrap as NumPy-backed DataArrays (no Dask in indexers)
    x_idx_da = xr.DataArray(
        x_idx,
        dims=(time_dim, "x_box"),
        coords={time_dim: time_coord, "x_box": x_box},
        name="x_idx",
    )
    y_idx_da = xr.DataArray(
        y_idx,
        dims=(time_dim, "y_box"),
        coords={time_dim: time_coord, "y_box": y_box},
        name="y_idx",
    )
    mask_box_da = xr.DataArray(
        mask_box_np,
        dims=(time_dim, "y_box", "x_box"),
        coords={time_dim: time_coord, "y_box": y_box, "x_box": x_box},
        name="mask_box",
    )

    logger.debug(
        "Built box indexers from ix_min/iy_min (NumPy-backed): box_nx=%d, box_ny=%d, nx=%d, ny=%d",
        box_nx,
        box_ny,
        nx,
        ny,
    )

    return x_idx_da, y_idx_da, mask_box_da, x_box, y_box, x_box_km, y_box_km


def _extract_box_for_dataset(
    ds: xr.Dataset,
    x_idx: xr.DataArray,
    y_idx: xr.DataArray,
    mask_box: xr.DataArray,
    conf,
    x_box: xr.DataArray,
    y_box: xr.DataArray,
    x_box_km: xr.DataArray,
    y_box_km: xr.DataArray,
    track_box: xr.Dataset,
) -> xr.Dataset:
    """
    Extract a time-varying cyclone-centred box from a single Dataset.

    Parameters
    ----------
    ds : xr.Dataset
        Source dataset (after dimension normalization).
    x_idx : xr.DataArray
        Global x indices, shape ``(time, x_box)``, clipped to domain bounds.
    y_idx : xr.DataArray
        Global y indices, shape ``(time, y_box)``, clipped to domain bounds.
    mask_box : xr.DataArray
        Boolean validity mask, shape ``(time, y_box, x_box)``.  False where
        the box extends outside the model domain.
    conf : object
        Configuration object.  Reads coordinate dimension names and
        ``tracking_method``.
    x_box : xr.DataArray
        Local x-offsets in grid points, dims ``("x_box",)``, centred on 0.
    y_box : xr.DataArray
        Local y-offsets in grid points, dims ``("y_box",)``, centred on 0.
    x_box_km : xr.DataArray
        Local x-offsets in kilometres.
    y_box_km : xr.DataArray
        Local y-offsets in kilometres.
    track_box : xr.Dataset
        Track dataset with box geometry attributes (``box_nx_points``, etc.)
        and the ideal box bounds (``ix_min``, ``iy_min``, etc.).

    Returns
    -------
    xr.Dataset
        Dataset restricted to the cyclone-centred box, with local coordinates
        ``x_box``, ``y_box``, ``x_box_km``, ``y_box_km``, and lat/lon arrays
        when available.  Out-of-domain points are NaN-masked.

    Notes
    -----
    Horizontal axes are selected by name, including for bounds and independent
    fields whose last dimensions need not be horizontal.
    """

    time_dim = getattr(conf, "name_time", "time")
    lat_name = getattr(conf, "name_latitude", "latitude")
    lon_name = getattr(conf, "name_longitude", "longitude")
    tracking_method = getattr(conf, "tracking_method", "")

    # ------------------------------------------------------------------
    # 1) Extract data variables
    # ------------------------------------------------------------------
    data_vars_out: dict[str, xr.DataArray] = {}
    (y_dim, x_dim), _ = horizontal_axes(conf)

    for name, da in ds.data_vars.items():
        dims = da.dims

        # Variables with no horizontal structure: copied as-is
        indexers = {d: idx for d, idx in ((y_dim, y_idx), (x_dim, x_idx)) if d in dims}
        if not indexers:
            data_vars_out[name] = da
            continue

        # Extraction with vectorized indexers
        # x_idx: (time, x_box), y_idx: (time, y_box)
        # da:   (..., y_dim, x_dim)
        da_box = da.isel(indexers)

        # Application du masque NaN pour les points hors domaine
        mask = mask_box
        if y_dim not in indexers:
            mask = mask.any("y_box")
        if x_dim not in indexers:
            mask = mask.any("x_box")
        da_box = da_box.where(mask)

        data_vars_out[name] = da_box

    # ------------------------------------------------------------------
    # 2) Base coordinates (time, levels, etc.) kept as-is
    # ------------------------------------------------------------------
    dims_out: set[Hashable] = set()
    for da in data_vars_out.values():
        dims_out.update(da.dims)

    coords_out: dict[Hashable, xr.DataArray] = {}
    for d in dims_out:
        if d in ds.coords:
            coords_out[d] = ds.coords[d]

    # Local box coordinates
    coords_out["x_box"] = x_box
    coords_out["y_box"] = y_box
    coords_out["x_box_km"] = x_box_km
    coords_out["y_box_km"] = y_box_km

    # Dataset extrait (sans lat/lon pour l'instant)
    ds_out = xr.Dataset(data_vars=data_vars_out, coords=coords_out)

    # ------------------------------------------------------------------
    # 3) Latitude / longitude in the box
    # ------------------------------------------------------------------
    if (lat_name in ds) and (lon_name in ds):
        lat_full = ds[lat_name]
        lon_full = ds[lon_name]

        try:
            lat_spatial = [d for d in lat_full.dims if d != time_dim]
            lon_spatial = [d for d in lon_full.dims if d != time_dim]
            if len(lat_spatial) == 2 and len(lon_spatial) == 2:
                # Cas 2D (MNH typiquement)
                y_lat = getattr(conf, "name_lat_dim", None) or lat_spatial[-2]
                x_lat = getattr(conf, "name_lon_dim", None) or lat_spatial[-1]

                lat_box = lat_full.isel({y_lat: y_idx, x_lat: x_idx})
                lon_box = lon_full.isel({y_lat: y_idx, x_lat: x_idx})

                lat_box = lat_box.where(mask_box)
                lon_box = lon_box.where(mask_box)

            elif len(lat_spatial) == 1 and len(lon_spatial) == 1:
                # Cas 1D (AROME typiquement)
                y_lat = lat_spatial[0]
                x_lon = lon_spatial[0]

                lat_1d = lat_full.isel({y_lat: y_idx})  # (time, y_box)
                lon_1d = lon_full.isel({x_lon: x_idx})  # (time, x_box)

                # Broadcast to (time, y_box, x_box)
                lat_box = lat_1d.broadcast_like(mask_box)
                lon_box = lon_1d.broadcast_like(mask_box)

                lat_box = lat_box.where(mask_box)
                lon_box = lon_box.where(mask_box)

            else:
                logger.warning(
                    "Latitude/longitude have unexpected shapes (lat.ndim=%d, lon.ndim=%d); "
                    "skipping lat/lon extraction for this dataset.",
                    lat_full.ndim,
                    lon_full.ndim,
                )
                lat_box = lon_box = None

        except Exception as exc:  # xarray broadcasting / indexing issues
            logger.warning(
                "Failed to extract lat/lon box for dataset: %s",
                exc,
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
            lat_box = lon_box = None

        if lat_box is not None and lon_box is not None:
            ds_out = ds_out.assign_coords({lat_name: lat_box, lon_name: lon_box})
    else:
        logger.debug(
            "No %s/%s coordinates in dataset; skipping lat/lon box.",
            lat_name,
            lon_name,
        )

    # ------------------------------------------------------------------
    # 4) Optional reorientation of y_box so that latitude increases with y_box
    #    (south at bottom, north at top in the centred box)
    # ------------------------------------------------------------------
    if (lat_name in ds_out.coords) and ("y_box" in ds_out.coords[lat_name].dims):
        try:
            # Take a representative latitudinal slice: time 0, x_box at box centre
            x_center = ds_out.sizes["x_box"] // 2

            # If there is no time dimension (rare case), ignore time_dim
            if time_dim in ds_out[lat_name].coords:
                lat_line = ds_out[lat_name].isel({time_dim: 0, "x_box": x_center}).values
            else:
                lat_line = ds_out[lat_name].isel({"x_box": x_center}).values

            # Drop any NaN values
            valid = np.isfinite(lat_line)
            lat_line = lat_line[valid]

            if lat_line.size >= 2:
                # If latitude decreases with y_box, reverse the axis
                if lat_line[-1] < lat_line[0]:
                    # 1) reverse the point order along y_box
                    ds_out = ds_out.isel(y_box=slice(None, None, -1))
                    # 2) flip the sign of y_box to keep [-ny_half..+ny_half]
                    ds_out = ds_out.assign_coords(y_box=-ds_out["y_box"])
                    ds_out = ds_out.assign_coords(y_box_km=-ds_out["y_box_km"])
                    ds_out.y_box.attrs.update(
                        units="1", long_name="y grid-point offset from extraction centre"
                    )
                    ds_out.y_box_km.attrs.update(
                        units="km", long_name="y distance offset from extraction centre"
                    )
        except Exception as exc:
            logger.warning(
                "Failed to reorient y_box according to latitude: %s",
                exc,
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )

    # ------------------------------------------------------------------
    # 5) Attributes: copy from ds and add box geometry attributes
    # ------------------------------------------------------------------
    attrs = dict(ds.attrs)
    # Box geometry attributes, defined by center2box
    for key in (
        "box_resolution_m",
        "box_x_size_km",
        "box_y_size_km",
        "box_half_width_x_points",
        "box_half_width_y_points",
        "box_nx_points",
        "box_ny_points",
    ):
        if key in track_box.attrs:
            attrs[key] = track_box.attrs[key]

    # Summary of extraction parameters
    extraction_params = {
        "tracking_method": tracking_method,
        "time_dim": time_dim,
        "lat_name": getattr(conf, "name_latitude", "latitude"),
        "lon_name": getattr(conf, "name_longitude", "longitude"),
    }
    attrs["extraction_parameters"] = extraction_params

    ds_out.attrs = attrs
    # Extra vertex dimensions prevent vertical bounds from being carried by
    # individual field DataArrays during spatial indexing.
    ds_out = preserve_coordinate_dependencies(ds, ds_out)
    ds_out = _clean_cropped_metadata(ds_out)

    return ds_out


def _clean_cropped_metadata(ds):
    """Remove source-domain validity/bounds claims that no longer describe a box."""
    ds = ds.copy(deep=False)
    for value in [ds, *(ds[name] for name in ds.variables)]:
        attrs = dict(value.attrs)
        if "c_grid_dynamic_range" in attrs:
            attrs["source_c_grid_dynamic_range"] = str(attrs.pop("c_grid_dynamic_range"))
        if attrs.get("bounds") and attrs["bounds"] not in ds:
            attrs["source_bounds"] = attrs.pop("bounds")
        value.attrs = attrs
    return ds


def _native_axis_indexer(ds, dim, mass_dim, axis, track_box, conf):
    """Match labelled regular native positions to requested mass-cell support.

    Face coordinates must lie on half-integer mass indices. Equal-N storage
    can omit either outer face; N+1 storage can supply both. Missing positions
    are masked, never synthesized. Axes may independently ascend or descend.
    Local offsets follow source mass-index orientation, including on reversed
    axes; native extraction does not rotate/reorient the vector basis.
    """
    if dim not in ds.coords or mass_dim not in ds.coords:
        raise ValueError(f"Native extraction requires labelled {dim!r} and {mass_dim!r} axes")
    mass, native = ds[mass_dim], ds[dim]
    if mass.dims != (mass_dim,) or native.dims != (dim,):
        raise ValueError("Native extraction requires one-dimensional labelled horizontal axes")
    if mass.attrs.get("units") != native.attrs.get("units"):
        from frameit.utils.units import convert_units

        mass = convert_units(mass, "distance", assumed="m")
        native = convert_units(native, "distance", assumed="m")
    m, n = np.asarray(mass, dtype=float), np.asarray(native, dtype=float)
    delta = np.diff(m)
    if len(delta) == 0 or not n.size or not np.isfinite(m).all() or not np.isfinite(n).all():
        raise ValueError("Native extraction requires finite horizontal geometry and >=2 mass cells")
    step = delta[0]
    if step == 0 or not np.allclose(delta, step, rtol=1e-7, atol=abs(step) * 1e-9):
        raise ValueError("Native extraction requires regular monotone mass axes")
    p = (n - m[0]) / step
    nd = np.diff(p)
    if len(nd) and not (np.allclose(nd, 1, atol=1e-7) or np.allclose(nd, -1, atol=1e-7)):
        raise ValueError(f"Native axis {dim!r} must have the mass-grid spacing")
    face = not np.allclose(p, np.rint(p), rtol=0, atol=1e-7)
    if face and not np.allclose(p - .5, np.rint(p - .5), rtol=0, atol=1e-7):
        raise ValueError(f"Native axis {dim!r} is neither cell-aligned nor half-cell staggered")
    count = track_box.attrs[f"box_n{axis}_points"]
    half = track_box.attrs[f"box_half_width_{axis}_points"]
    offsets = np.arange(count + int(face), dtype=float) - half - (.5 if face else 0)
    suffix = dim.rsplit("_", 1)[-1] if dim != mass_dim else None
    local = f"{axis}_{suffix}_box" if suffix in {"u", "v"} else f"{axis}_box"
    minimum = track_box[f"i{axis}_min"]
    targets = np.asarray(minimum)[:, None] + offsets[None, :] + half
    direction = nd[0] if len(nd) else 1.
    raw = np.rint((targets - p[0]) / direction).astype(np.int64)
    valid = (raw >= 0) & (raw < len(p))
    clipped = np.clip(raw, 0, len(p) - 1)
    valid &= np.isclose(p[clipped], targets, rtol=0, atol=1e-7)
    coord = xr.DataArray(offsets, dims=local, attrs={
        "units": "1", "long_name": f"native {axis} offset in signed mass-grid index units",
        "grid_position": f"{axis}_face" if face else "mass_aligned",
    })
    coords = {minimum.dims[0]: minimum.coords[minimum.dims[0]].variable, local: coord}
    indexer = xr.DataArray(clipped, dims=(minimum.dims[0], local), coords=coords)
    mask = xr.DataArray(valid, dims=indexer.dims, coords=coords)
    return indexer, mask, face


def _extract_native_box(ds, x_idx, y_idx, mask_box, conf, x_box, y_box,
                        x_box_km, y_box_km, track_box):
    """Crop native values and geography together on each labelled source grid.

    Output uses x_u_box/y_u_box and x_v_box/y_v_box for aliases (even when
    perpendicular positions coincide with mass cells), and x_box/y_box for
    mass fields. Face axes contain N+1 samples. No collocation, basis rotation,
    speed calculation or data extrapolation is performed.
    """
    (y, x), axes = horizontal_axes(conf)
    indexers, masks, faces = {}, {}, {}
    for dim in ds.dims:
        if dim not in axes:
            continue
        axis = axes[dim]
        idx, mask, face = _native_axis_indexer(
            ds, dim, x if axis == "x" else y, axis, track_box, conf)
        indexers[dim], masks[dim], faces[dim] = idx, mask, face
    cropped = ds.isel(indexers)
    out = xr.Dataset(attrs=dict(ds.attrs))
    for name, da in ds.variables.items():
        value = cropped[name]
        relevant = [dim for dim in da.dims if dim in masks]
        # Drop automatically attached source coordinates before constructing the
        # result: each coordinate is independently cropped/masked below.
        clean = xr.DataArray(value.variable)
        for dim in relevant:
            clean = clean.where(masks[dim])
        clean.attrs = dict(da.attrs)
        if relevant:
            position = [f"{axes[d]}_face" for d in relevant if faces[d]]
            clean.attrs["grid_position"] = " ".join(position) or "mass_aligned"
        if name in ds.coords:
            out = out.assign_coords({name: clean})
        else:
            out[name] = clean
    for idx in indexers.values():
        local = idx.dims[-1]
        out = out.assign_coords({local: idx[local]})
        distance = idx[local] * float(conf.resolution) / 1000
        distance.attrs = dict(units="km", long_name=f"{local} signed mass-index distance offset")
        out = out.assign_coords({f"{local}_km": distance})
    out.attrs.update(track_box.attrs)
    out.attrs["native_horizontal_extraction"] = (
        "source mass-index orientation; labelled cell/face support; unavailable faces NaN; "
        "native vector basis unchanged")
    return _clean_cropped_metadata(out)


def extract_data(
    conf,
    ds_user: dict[str, xr.Dataset],
    ds_tracker: dict[str, xr.Dataset] | xr.Dataset,
    track_ds: xr.Dataset,
    *,
    native_winds: bool = False,
):
    """
    High-level extraction: compute box bounds and crop all user datasets.

    Parameters
    ----------
    conf : object
        Configuration object.  Reads ``x_boxsize_km``, ``y_boxsize_km``,
        and ``resolution`` (metres).
    ds_user : dict[str, xr.Dataset]
        User datasets keyed by vertical group (e.g. "level", "surface").
    ds_tracker : dict or xr.Dataset
        Tracker datasets used to infer the domain shape (nx, ny).
    track_ds : xr.Dataset
        Track dataset containing at least ``cx(time)`` and ``cy(time)``.
    native_winds : bool, optional
        Preserve normalized native U/V samples and basis without computing
        speed. Labelled native face axes use N+1 bounding samples (NaN where
        unavailable), on x_u_box/y_u_box and x_v_box/y_v_box dimensions.

    Returns
    -------
    track_box : xr.Dataset
        Track dataset enriched with box bounds (``ix_min``, ``ix_max``,
        ``iy_min``, ``iy_max``, ``valid_box``, …) by :func:`center2box`.
        Equals the original ``track_ds`` when no box is requested.
    extracted : dict[str, xr.Dataset]
        Cyclone-centred extracted fields keyed by group, or ``ds_user`` with
        normalized dimension ordering when no box is requested.

    Raises
    ------
    ValueError
        If a box is requested but ``conf.resolution`` <= 0.
    """

    # Box parameters from config
    x_box = float(getattr(conf, "x_boxsize_km", 0.0) or 0.0)
    y_box = float(getattr(conf, "y_boxsize_km", 0.0) or 0.0)
    resolution_m = float(getattr(conf, "resolution", 0.0) or 0.0)

    # Reject raw staggering before any spatial coordinates can be discarded.
    if not native_winds:
        mass, axes = horizontal_axes(conf)
        for ds in ds_user.values():
            for name, da in ds.data_vars.items():
                if any(d in axes and d not in mass for d in da.dims):
                    raise ValueError(
                        f"{name}: unprepared native staggering; prepare mass/Earth winds "
                        "before extraction or use native_winds=True"
                    )

    # Always normalize dims so the rest of the pipeline can rely on the convention
    ds_user_norm = normalize_dims_for_extraction(ds_user, conf=conf)

    # Prescribed tracks can contain only a subset of model times. Align before
    # time-dependent spatial indexing, also when no spatial box is requested.
    if "time" in track_ds.coords:
        ds_user_norm = {
            key: ds.sel(time=track_ds["time"].values) if "time" in ds.dims else ds
            for key, ds in ds_user_norm.items()
        }

    # If no box requested, return track_ds and normalized datasets
    if x_box <= 0.0 or y_box <= 0.0:
        logger.info(
            "No box requested (x_boxsize_km=%.1f, y_boxsize_km=%.1f); "
            "skipping center2box and spatial extraction.",
            x_box,
            y_box,
        )
        return track_ds, ds_user_norm

    if resolution_m <= 0.0:
        raise ValueError(
            f"Box requested (x_boxsize_km={x_box}, y_boxsize_km={y_box}) "
            f"but configuration 'resolution'={resolution_m} <= 0."
        )

    # Domain size nx, ny from tracker datasets
    nx, ny = infer_domain_shape_from_tracker(ds_tracker, conf)

    logger.debug(
        "Running center2box: x=%.1f km, y=%.1f km, resolution=%.1f m, nx=%d, ny=%d",
        x_box,
        y_box,
        resolution_m,
        nx,
        ny,
    )

    # Boxes around the track
    track_box = center2box(
        track_ds,
        x_size_km=x_box,
        y_size_km=y_box,
        resolution_m=resolution_m,
        nx=nx,
        ny=ny,
        center_x_var="cx",
        center_y_var="cy",
        inplace=False,
    )

    # Build shared indexers/masks for the box
    x_idx, y_idx, mask_box, x_box_coord, y_box_coord, x_box_km, y_box_km = _build_box_indexers(
        track_box=track_box,
        nx=nx,
        ny=ny,
        resolution_m=resolution_m,
    )

    # Extract cyclone-centred box for each user dataset
    extracted: dict[str, xr.Dataset] = {}
    for key, ds in ds_user_norm.items():
        if "time" in ds.dims:
            ds = ds.sel(time=track_box["time"].values)
        logger.debug("Extracting cyclone-centred box for ds_user[%s]", key)
        extractor = _extract_native_box if native_winds else _extract_box_for_dataset
        extracted[key] = extractor(
            ds=ds,
            x_idx=x_idx,
            y_idx=y_idx,
            mask_box=mask_box,
            conf=conf,
            x_box=x_box_coord,
            y_box=y_box_coord,
            x_box_km=x_box_km,
            y_box_km=y_box_km,
            track_box=track_box,
        )
    # Add total wind speed here :
    if not native_winds:
        extracted = add_speed_from_uv_dict(extracted, conf)

    return track_box, extracted
