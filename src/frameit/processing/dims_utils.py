# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
from collections.abc import Iterable

import xarray as xr

logger = logging.getLogger(__name__)


def horizontal_axes(conf):
    """Named mass and Meso-NH alias axes; never infer geometry from array order."""
    x = getattr(conf, "name_lon_dim", None) or "ni"
    y = getattr(conf, "name_lat_dim", None) or "nj"
    return (y, x), {y: "y", x: "x", "nj_u": "y", "ni_u": "x",
                    "nj_v": "y", "ni_v": "x"}


def _normalize_dataset_dims(
    ds: xr.Dataset,
    time_dim: str,
    vertical_dims: Iterable[str],
    conf=None,
) -> xr.Dataset:
    """
    Reorder data variable dimensions to ``(time, vertical..., horizontal...)``.

    Parameters
    ----------
    ds : xr.Dataset
        Source dataset (may contain lazy Dask arrays).
    time_dim : str
        Name of the time dimension to place first.
    vertical_dims : Iterable[str]
        Names of known vertical dimensions to place second.

    Returns
    -------
    xr.Dataset
        Shallow copy of ``ds`` with each data variable transposed to the
        canonical order.  Coordinates are not reordered.  The underlying data
        remain lazy if the input was lazy.
    """
    vertical_dims = set(vertical_dims)

    # Shallow copy to avoid modifying `ds` in place while keeping lazy data
    ds_out = ds.copy(deep=False)

    for var_name, da in ds.data_vars.items():
        dims = list(da.dims)
        if not dims:
            continue

        # 1) Time dimension first (if present)
        time_part = [time_dim] if time_dim in dims else []

        # 2) Vertical dimensions next (excluding time if it is in vertical_dims)
        vert_part = [d for d in dims if d in vertical_dims and d != time_dim]

        # 3) Remaining dimensions (typically horizontal and possibly others)
        other_part = [d for d in dims if d not in time_part and d not in vert_part]

        axes = horizontal_axes(conf)[1]
        horizontal = [d for axis in ("y", "x") for d in other_part
                      if axes.get(d) == axis]
        independent = [d for d in other_part if d not in horizontal]
        new_order = time_part + vert_part + independent + horizontal

        if new_order != dims:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Reordering dims for variable %s: %s -> %s",
                    var_name,
                    dims,
                    new_order,
                )
            ds_out[var_name] = da.transpose(*new_order)

    return ds_out


def normalize_dims_for_extraction(
    ds_user: dict[str, xr.Dataset],
    conf,
) -> dict[str, xr.Dataset]:
    """
    Normalize dimension order in all datasets of `ds_user` for cyclone-centred
    extraction.

    Convention enforced for each data variable:
        - time dimension first (if present),
        - known vertical dimensions next,
        - all remaining dimensions last (typically horizontal).

    Parameters
    ----------
    ds_user : dict[str, xr.Dataset]
        Dictionary of user fields (e.g. {"level": ds_level, "surface": ds_sfc}).
    conf : object
        Configuration object. Optionally provides:
          - `name_time` : str, name of the time dimension (default "time"),
          - `vertical_dims_for_extraction` : Iterable[str], names of vertical
            dimensions relevant for extraction (default set below).
    logger : logging.Logger, optional
        Logger for debug information.

    Returns
    -------
    dict[str, xr.Dataset]
        New dictionary with the same keys as `ds_user`, where each dataset
        has its data variables reordered according to the convention.
    """

    # Time dimension name, with a reasonable default
    time_dim = getattr(conf, "name_time", "time")

    # Default list of vertical dimension names, can be overridden in the config
    default_vertical_dims = (
        "level",  # MNH
        "level_w",  # MNH W grid
        "isobaricInhPa",  # AROME, GRIB pressure levels
        "heightAboveGround",
        "hybrid",
        "hybrid1",
        "hybrid2",  # possible model level names
    )
    vertical_dims = getattr(
        conf,
        "vertical_dims_for_extraction",
        default_vertical_dims,
    )

    out: dict[str, xr.Dataset] = {}

    for key, ds in ds_user.items():
        if not isinstance(ds, xr.Dataset):
            raise TypeError(
                f"normalize_dims_for_extraction expects xr.Dataset values, "
                f"got {type(ds)!r} for key {key!r}"
            )
        logger.debug("Normalizing dimension order for ds_user[%s]", key)
        out[key] = _normalize_dataset_dims(
            ds,
            time_dim=time_dim,
            vertical_dims=vertical_dims,
            conf=conf,
        )

    return out
