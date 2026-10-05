# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np
import xarray as xr
from pyproj import Geod

from frameit.core.settings_class import SimulationConfig

_GEOD = Geod(ellps="WGS84")


@dataclass
class TcTracker(ABC):
    """
    Abstract base class for all tropical cyclone trackers.

    Subclasses must define:

    - ``name`` : method name (key in ``ds_tree`` and the YAML config),
    - ``logical_fields`` : canonical variable names expected in the dataset,
    - ``_track_method`` : concrete tracking implementation.

    The tracker receives, via :meth:`__call__`, a hierarchical dict
    ``ds_tree[method][vertical_group] -> xr.Dataset``.
    """

    # mapping "logical name" -> "native name in model files"
    var_aliases: Mapping[str, str] = field(default_factory=dict)

    # Method name (key in ds_tree and in the YAML config)
    name: ClassVar[str] = "method"

    # LOGICAL names expected (u10, v10, mslp, etc.)
    logical_fields: ClassVar[Sequence[str]] = ()

    # Effective names in the Dataset (derived from logical_fields + var_aliases)
    effective_fields: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        # For each logical name, retrieve the native name; if absent, assume the same name
        self.effective_fields = tuple(self.var_aliases.get(f, f) for f in self.logical_fields)

    @classmethod
    def from_config(cls, conf: SimulationConfig) -> TcTracker:
        """
        Construct a tracker instance from a simulation configuration.

        Parameters
        ----------
        conf : SimulationConfig
            Configuration object.  Reads ``tracking_var_aliases`` (optional).

        Returns
        -------
        TcTracker
            Tracker instance with variable aliases from ``conf``.

        Notes
        -----
        Subclasses may override this method to read additional parameters
        from the configuration.
        """
        var_aliases = getattr(conf, "tracking_var_aliases", {}) or {}
        return cls(var_aliases=var_aliases)

    def __call__(
        self,
        ds_tree: Mapping[str, Mapping[str, xr.Dataset]],
    ) -> xr.Dataset:
        """
        Run the tracker on a hierarchical dataset tree.

        Parameters
        ----------
        ds_tree : Mapping[str, Mapping[str, xr.Dataset]]
            Nested mapping ``ds_tree[method][vertical_group] -> xr.Dataset``.

        Returns
        -------
        xr.Dataset
            Tracking result as returned by :meth:`_track_method`, containing
            at minimum ``cx(time)`` and ``cy(time)`` grid-point index arrays.

        Raises
        ------
        ValueError
            If required effective fields are missing from the flat dataset.
        """

        ds_flat = make_tracking_dataset(ds_tree, self.name)
        self._validate_inputs(ds_flat)
        return self._track_method(ds_flat)

    # ------------------ generic helpers ------------------

    def _validate_inputs(self, ds: xr.Dataset) -> None:
        """Check that all effective variables are present."""
        missing = [v for v in self.effective_fields if v not in ds]
        if missing:
            raise ValueError(f"{self.name}: missing required fields in Dataset: {missing}")

    def _field(self, ds: xr.Dataset, logical_name: str) -> xr.DataArray:
        """
        Retrieve a field by its logical name, applying ``var_aliases``.

        Parameters
        ----------
        ds : xr.Dataset
            Flat tracking dataset.
        logical_name : str
            Canonical field name (e.g. ``"mslp"``, ``"u10m"``).

        Returns
        -------
        xr.DataArray
            The resolved field from ``ds``.

        Raises
        ------
        KeyError
            If the native name resolved via ``var_aliases`` is absent from ``ds``.
        """
        native = self.var_aliases.get(logical_name, logical_name)
        try:
            return ds[native]
        except KeyError as exc:
            raise KeyError(
                f"{self.name}: logical field {logical_name!r} is mapped to "
                f"{native!r}, but this variable is not present in Dataset"
            ) from exc

    @abstractmethod
    def _track_method(self, ds: xr.Dataset) -> xr.Dataset:
        """
        Core tracking algorithm — must be implemented by every subclass.

        Parameters
        ----------
        ds : xr.Dataset
            Flat dataset produced by :func:`make_tracking_dataset`.

        Returns
        -------
        xr.Dataset
            Dataset containing at least ``cx(time)`` and ``cy(time)``
            (grid-point index arrays of the cyclone centre).
        """

    # -------------------------
    # High-level API: hierarchical dict -> flat Dataset
    # -------------------------
    def track_from_tree(
        self,
        ds_tree: Mapping[str, Mapping[str, xr.Dataset]],
    ) -> xr.Dataset:
        """
        Convenience wrapper: flatten ``ds_tree`` then apply the tracker.

        Parameters
        ----------
        ds_tree : Mapping[str, Mapping[str, xr.Dataset]]
            Nested mapping ``ds_tree[method][vertical_group] -> xr.Dataset``.

        Returns
        -------
        xr.Dataset
            Tracking result (see :meth:`_track_method`).
        """
        ds_flat = make_tracking_dataset(ds_tree, self.name)
        return self(ds_flat)


# --------------------------------------------------------------------
# Flatten function shared by all trackers
# --------------------------------------------------------------------


def make_tracking_dataset(
    ds_tree: Mapping[str, Mapping[str, xr.Dataset]],
    method: str,
) -> xr.Dataset:
    """
    Merge all vertical-group datasets for a given tracking method into one.

    Parameters
    ----------
    ds_tree : Mapping[str, Mapping[str, xr.Dataset]]
        Nested mapping ``ds_tree[method][vertical_group] -> xr.Dataset``.
    method : str
        Tracking method key to look up in ``ds_tree``.

    Returns
    -------
    xr.Dataset
        Flat dataset produced by merging all vertical groups for ``method``.

    Raises
    ------
    ValueError
        If ``method`` is not a key of ``ds_tree`` or if its sub-dict is empty.
    TypeError
        If a value in the sub-dict is not an :class:`xr.Dataset`.
    """
    try:
        method_group = ds_tree[method]
    except KeyError as exc:
        raise ValueError(f"Tracking method {method!r} not found in ds_tree") from exc

    datasets = []
    for vert_group, ds in method_group.items():
        if not isinstance(ds, xr.Dataset):
            raise TypeError(
                f"For method {method!r}, vertical group {vert_group!r} "
                f"should be an xarray.Dataset, got {type(ds)}"
            )
        datasets.append(ds)

    if not datasets:
        raise ValueError(f"No Dataset found for method {method!r} in ds_tree")

    ds_flat = xr.merge(datasets, compat="no_conflicts")
    return ds_flat


# --------------------------------------------------------------------
# Geographic position -> grid indices, shared by all trackers
# --------------------------------------------------------------------


def _wrap_longitude(lon0: float, lon_grid: np.ndarray) -> float:
    """
    Express a longitude in the convention of the model grid.

    Parameters
    ----------
    lon0 : float
        Longitude in degrees, in any convention.
    lon_grid : np.ndarray
        Grid longitudes in degrees. A maximum above 180 means [0, 360),
        otherwise [-180, 180) is assumed.

    Returns
    -------
    float
        ``lon0`` wrapped into the grid convention.
    """
    if np.nanmax(lon_grid) > 180.0:
        return lon0 % 360.0
    return (lon0 + 180.0) % 360.0 - 180.0


def nearest_grid_point(
    lat: xr.DataArray | np.ndarray,
    lon: xr.DataArray | np.ndarray,
    lat0: float,
    lon0: float,
) -> tuple[int, int, float]:
    """
    Find the grid point closest to a geographic position.

    The grid type is inferred from the coordinate dimensionality:

    - 1-D ``lat(y)`` and ``lon(x)`` (rectilinear grid, e.g. AROME): the
      closest latitude and longitude are searched independently;
    - 2-D ``lat(y, x)`` and ``lon(y, x)`` (curvilinear grid, e.g. Meso-NH):
      the minimum of the squared distance in degrees is searched.

    Parameters
    ----------
    lat : xr.DataArray or np.ndarray
        Grid latitudes in degrees, 1-D or 2-D.
    lon : xr.DataArray or np.ndarray
        Grid longitudes in degrees, same dimensionality as ``lat``.
    lat0 : float
        Target latitude in degrees.
    lon0 : float
        Target longitude in degrees, in any convention. It is wrapped into
        the grid convention before the search.

    Returns
    -------
    j : int
        Index of the closest point along the y (latitude) axis.
    i : int
        Index of the closest point along the x (longitude) axis.
    distance_m : float
        Geodesic distance on the WGS84 ellipsoid between the target and the
        selected grid point, in metres.

    Raises
    ------
    ValueError
        If ``lat`` and ``lon`` are neither both 1-D nor both 2-D with the
        same shape.
    """
    lat_vals = np.asarray(lat, dtype=np.float64)
    lon_vals = np.asarray(lon, dtype=np.float64)
    lon0 = _wrap_longitude(float(lon0), lon_vals)
    lat0 = float(lat0)

    if lat_vals.ndim == 1 and lon_vals.ndim == 1:
        # Rectilinear grid: independent search along each axis
        j = int(np.nanargmin((lat_vals - lat0) ** 2))
        i = int(np.nanargmin((lon_vals - lon0) ** 2))
        lat_sel, lon_sel = lat_vals[j], lon_vals[i]
    elif lat_vals.ndim == 2 and lat_vals.shape == lon_vals.shape:
        # Curvilinear grid: search over the full 2-D field
        dist2 = (lat_vals - lat0) ** 2 + (lon_vals - lon0) ** 2
        j, i = (int(k) for k in np.unravel_index(np.nanargmin(dist2), dist2.shape))
        lat_sel, lon_sel = lat_vals[j, i], lon_vals[j, i]
    else:
        raise ValueError(
            "nearest_grid_point: expected 1-D lat/lon or 2-D lat/lon of the same "
            f"shape, got lat.shape={lat_vals.shape}, lon.shape={lon_vals.shape}"
        )

    _, _, distance_m = _GEOD.inv(lon0, lat0, lon_sel, lat_sel)
    return j, i, float(distance_m)


# --------------------------------------------------------------------
# Registre de trackers
# --------------------------------------------------------------------

TRACKER_REGISTRY: dict[str, type[TcTracker]] = {}


def register_tracker(cls: type[TcTracker]) -> type[TcTracker]:
    """
    Class decorator to register a tracker in :data:`TRACKER_REGISTRY`.

    Parameters
    ----------
    cls : type[TcTracker]
        Tracker class whose ``name`` attribute is used as the registry key.

    Returns
    -------
    type[TcTracker]
        The same class, unchanged.

    Raises
    ------
    ValueError
        If ``cls.name`` is already present in the registry.
    """
    if cls.name in TRACKER_REGISTRY:
        raise ValueError(f"Tracker name already registered: {cls.name}")
    TRACKER_REGISTRY[cls.name] = cls
    return cls


# --------------------------------------------------------------------
# Factory from config
# --------------------------------------------------------------------


def build_tracker_from_config(conf: SimulationConfig) -> TcTracker:
    """
    Instantiate the tracker selected by ``conf.tracking_method``.

    Parameters
    ----------
    conf : SimulationConfig
        Configuration object.  Reads ``tracking_method`` to look up the
        registered tracker class.

    Returns
    -------
    TcTracker
        Tracker instance built via the class's :meth:`TcTracker.from_config`.

    Raises
    ------
    ValueError
        If ``conf.tracking_method`` is not in :data:`TRACKER_REGISTRY`.
    """
    method = conf.tracking_method
    try:
        tracker_cls = TRACKER_REGISTRY[method]
    except KeyError:
        raise ValueError(f"Unknown tracking method: {method!r}") from None

    return tracker_cls.from_config(conf)
