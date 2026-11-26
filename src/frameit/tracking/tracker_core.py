# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar

import xarray as xr

from frameit.core.settings_class import SimulationConfig
from frameit.utils.diagnostics import tag_error


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
    *,
    selected_times=None,
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
        if selected_times is not None:
            if "time" not in ds.coords or any(
                    time not in ds.time.values for time in selected_times):
                raise ValueError(
                    f"Tracker {method!r}: missing selected source times in {vert_group}")
            ds = ds.sel(time=selected_times)
        datasets.append(ds)

    if not datasets:
        raise ValueError(f"No Dataset found for method {method!r} in ds_tree")

    # Outer joins are appropriate for independent vertical groups/time labels,
    # but must never silently align different horizontal sampling locations.
    horizontal_names = {"ni", "nj", "ni_u", "nj_u", "ni_v", "nj_v", "x", "y",
                        "latitude", "longitude", "lat", "lon"}
    for dataset in datasets:
        for name, coord in dataset.coords.items():
            if name in {"latitude", "longitude", "lat", "lon"} or coord.attrs.get(
                    "standard_name") in {"latitude", "longitude"}:
                horizontal_names.update(d for d in coord.dims if d not in {
                    "time", "level", "level_w", "isobaric", "heightAboveGround"}
                    and dataset[d].attrs.get("axis") != "Z")
    for i, left in enumerate(datasets):
        for right in datasets[i + 1:]:
            for dim in set(left.dims) & set(right.dims) & horizontal_names:
                if left.sizes[dim] != right.sizes[dim] or (
                        (dim in left.coords) != (dim in right.coords)):
                    raise ValueError(
                        f"Tracker {method!r}: shared horizontal coordinate {dim!r} "
                        "must match exactly before merging")
            shared = set(left.coords) & set(right.coords)
            for name in shared:
                a, b = left[name], right[name]
                horizontal = (name in horizontal_names
                              or a.attrs.get("axis") in {"X", "Y"}
                              or a.attrs.get("standard_name") in {"latitude", "longitude"})
                if not horizontal:
                    continue
                # Geography can legitimately carry different time/vertical
                # selections. Compare overlapping labels only on those axes.
                nonhorizontal = set(a.dims) | set(b.dims)
                nonhorizontal -= horizontal_names
                try:
                    aa, bb = xr.align(a, b, join="inner", exclude=horizontal_names)
                    # Static geography may accompany time/level-dependent
                    # geography if every shared location agrees.
                    if set(a.dims) ^ set(b.dims) <= nonhorizontal:
                        aa, bb = xr.broadcast(aa, bb)
                    if set(aa.dims) == set(bb.dims):
                        bb = bb.transpose(*aa.dims)
                    xr.testing.assert_equal(aa.variable, bb.variable)
                except (AssertionError, ValueError) as exc:
                    raise ValueError(
                        f"Tracker {method!r}: shared horizontal coordinate {name!r} "
                        "must match exactly before merging"
                    ) from exc

    ds_flat = xr.merge(datasets, compat="no_conflicts", join="outer")
    return ds_flat


def merge_internal_stencils(datasets, vertical_dims):
    """Align selected internal levels only; structural holes are never source samples."""
    import numpy as np

    vertical_dims = set(vertical_dims)
    targets = {}
    for dataset in datasets:
        for dim in vertical_dims & dataset.coords.keys():
            labels = dataset[dim]
            if labels.dims != (dim,) or len(np.unique(labels)) != labels.size:
                raise ValueError(f"Internal stencil requires unique labelled vertical axis {dim}")
            values = targets.setdefault(dim, [])
            values.extend(value for value in labels.values.tolist() if value not in values)
    for index, left in enumerate(datasets):
        for right in datasets[index + 1:]:
            nonvertical = set(left.dims) - vertical_dims
            if nonvertical != set(right.dims) - vertical_dims or any(
                    left.sizes[dim] != right.sizes[dim] for dim in nonvertical):
                raise ValueError("Internal stencils have incompatible nonvertical dimensions")
            fixed_left, fixed_right = [
                {name for name, coord in ds.coords.items()
                 if not set(coord.dims) & vertical_dims} for ds in (left, right)]
            if fixed_left != fixed_right:
                raise ValueError("Internal stencils have incompatible nonvertical coordinates")
            for name in left.coords.keys() & right.coords.keys():
                a, b = left[name], right[name]
                try:
                    if a.encoding.get("calendar") != b.encoding.get("calendar"):
                        raise ValueError("incompatible coordinate calendars")
                    a, b = xr.align(a, b, join="inner", exclude=nonvertical)
                    xr.testing.assert_identical(a.variable, b.variable)
                except (AssertionError, ValueError) as exc:
                    raise ValueError(f"Internal stencil coordinate {name!r} conflicts") from exc
    aligned = [dataset.reindex({dim: values for dim, values in targets.items()
                               if dim in dataset.dims}) for dataset in datasets]
    result = xr.merge(aligned, join="exact", compat="no_conflicts", combine_attrs="override")
    for name, coordinate in result.coords.items():
        if name == "source_native_index" or name.endswith("_source_native_index"):
            values = np.asarray(coordinate)
            if (values.ndim == 1 and set(coordinate.dims) & vertical_dims
                    and (not np.isfinite(values).all() or len(np.unique(values)) != values.size)):
                raise ValueError(f"Internal stencil native-index mapping {name!r} conflicts")
    return result


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
    if getattr(conf, "schema_version", None) == 3:
        source = conf.simulation_parameter["request_plan"]["sources"][conf.source_name]
        if source.get("tracker_support", {}).get("method") != method:
            raise ValueError(f"{method}: tracker support is not resolved against selected metadata")
    try:
        tracker_cls = TRACKER_REGISTRY[method]
    except KeyError:
        raise ValueError(f"Unknown tracking method: {method!r}") from None

    return tracker_cls.from_config(conf)


def require_utrack_source(model, fmt):
    if model != "arome" or fmt not in {"netcdf", "grib"}:
        raise tag_error(ValueError("UTrack requires an AROME NetCDF or GRIB source"), "E1502")


def _utrack_checkpoint(conf):
    from os import R_OK, access
    from pathlib import Path

    path = Path(conf.utrack_weights_file)
    if not (path.is_file() and access(path, R_OK) and path.stat().st_size):
        raise tag_error(ValueError(
            "UTrack checkpoint must be a readable, nonempty local file; "
            "check region.tracker.weights_file"), "E1502")


def _utrack_horizontal_identity(source, record):
    from frameit.core.preflight import _metadata_id

    grid = source["native_grids"][record["grid_id"]]
    if source["format"] == "grib":
        return grid["grib_grid_section"]
    dims = set(grid["dimensions"]) - {"isobaric"}
    if len(dims) != 2:
        raise ValueError("UTrack requires a two-dimensional horizontal grid")
    return _metadata_id("utrack_grid_", {
        "dimensions": {dim: grid["dimensions"][dim] for dim in dims},
        "coordinates": {name: coord for name, coord in grid["coordinates"].items()
                        if coord["dimensions"] and set(coord["dimensions"]) <= dims},
        "grid_mapping": grid["grid_mapping"],
    })


def utrack_850_position(pressure):
    """The native label must be 850 hPa after unit conversion, not a nearby level."""
    import numpy as np

    from frameit.utils.units import convert_units

    levels = convert_units(pressure.astype("float64"), "pressure", target="hPa")
    matches = np.flatnonzero(levels.values == 850.)
    if len(matches) != 1:
        raise ValueError("UTrack requires one exact 850 hPa level for absolute vorticity")
    return int(matches[0])


def _utrack_vertical_label(name, attrs):
    return (name in {"height", "heightAboveGround", "heightAboveSea", "meanSea", "isobaric",
                     "level", "hybrid", "altitude", "depth"}
            or attrs.get("axis") == "Z" or attrs.get("positive") in {"up", "down"}
            or attrs.get("standard_name") in {"height", "altitude", "depth", "air_pressure",
                                              "height_above_mean_sea_level", "surface_altitude"})


def resolve_tracker_support(conf, source):
    """Resolve existing method inputs from the closed selected metadata pool."""
    from frameit.io.grib_utils import GRIB_PRESSURE_UNITS
    from frameit.processing.requests import _field_axis
    from frameit.processing.wind_reference import (
        _metadata_frames,
        validate_pair_frame,
    )
    from frameit.utils.units import convert_units, unit_metadata

    method = conf.tracking_method
    utrack = method == "utrack"
    if utrack:
        require_utrack_source(source["model"], source["format"])
        _utrack_checkpoint(conf)
    if method in {"pressure_centroid", "multifield_vortex"} and source["model"] == "mesonh":
        from frameit.io.loader import DatasetResources

        from .pressure_centroid_inputs import (
            inspect_mnh_sequence,
            mnh_wind_frames,
            selected_mnh_metadata,
        )

        if source["format"] != "netcdf":
            raise tag_error(ValueError(f"{method}: native Meso-NH NetCDF metadata is required"),
                            "E1502")
        conf.wind_pairs = [
            {**{key: value for key, value in pair.items() if key != "basis"},
             "reference_frame": pair["basis"],
             "group": "surface" if pair["u"] == "UM10" else "level"}
            for pair in conf.sources[conf.source_name]["wind_pairs"]]
        with DatasetResources() as resources:
            sequence = selected_mnh_metadata(source, conf, resources)
            if method == "multifield_vortex":
                from .multifield_inputs import inspect_inputs, selected_mnh_source

                sequence = [(path, selected_mnh_source(ds, conf)) for path, ds in sequence]
                for path, ds in sequence:
                    inspect_inputs([ds], conf, path)
            fields = inspect_mnh_sequence(sequence)
            projections = []
            for _, ds in sequence:
                active = {}
                mnh_wind_frames(ds, fields, conf, active_projection=active)
                projections.append(active)
            coordinates = set.intersection(*(set(ds.coords) for _, ds in sequence))
            inputs = {name: {} for name in fields.variables if name not in coordinates}
            reference = projections[0]
            if any(projection.keys() != reference.keys() for projection in projections[1:]):
                raise ValueError(f"{method}: inconsistent active Meso-NH projection across samples")
            projection = {"CARTESIAN"} if reference else set()
            projection_attributes = {}
            for pair, parameters in reference.items():
                for name, definition in parameters.items():
                    if any(p[pair][name] != definition for p in projections[1:]):
                        raise ValueError(
                            f"{method}: Meso-NH projection scalar {name} differs across "
                            "selected samples; tracking requires one stationary projection.")
                    if definition[1] == "variable":
                        projection.add(name)
                    elif definition[1] == "dataset_attribute":
                        projection_attributes[name] = definition[0]
            geometry = projection | {
                pair["rotation"]["coordinate"] for pair in conf.wind_pairs
                if (pair.get("rotation") or {}).get("coordinate")}
            inputs.update({field["name"]: {} for field in source["fields"].values()
                           if field["name"] in geometry
                           and any(field["name"] in ds for _, ds in sequence)})
            projection_constants = []
            for name in sorted(projection):
                if all(name in ds and ds[name].ndim == 0 for _, ds in sequence):
                    values = [ds[name].variable for _, ds in sequence]
                    if any(not values[0].identical(value) for value in values[1:]):
                        raise ValueError(
                            f"{method}: Meso-NH projection scalar {name} differs across "
                            "selected samples; tracking requires one stationary projection.")
                    projection_constants.append(name)
        if method == "pressure_centroid" and len(source["selected_times"]) < 2:
            raise ValueError("pressure_centroid requires at least two selected source times")
        conf.add_parameter(f"{method}_inputs", {
            "pressure": fields.pressure, "winds": [fields.u, fields.v],
            "height": list(fields.height)})
        return {"method": method, "inputs": inputs,
                **({"projection_constants": projection_constants} if projection_constants else {}),
                **({"projection_attributes": projection_attributes} if projection_attributes else {}),
                "selected_time_count": len(source["selected_times"]),
                "value_checks": (
                    "pending execution: physical brackets, masks, geometry and convergence")}
    if (method not in {"wind_pressure", "pressure_centroid", "multifield_vortex", "utrack"}
            or source["format"] == "fa"):
        raise tag_error(ValueError(f"{method}: selected tracker method support is not yet executable"),
                         "E1502")
    surface = (("UM10", "VM10") if source["model"] == "mesonh" else ("u10", "v10"))
    pressure = "MSLP" if source["model"] == "mesonh" else "prmsl"
    upper = (("absv",) if utrack else ("u", "v", "z") if method != "wind_pressure" else ())
    names = (*surface, *upper) if utrack else (pressure, *surface, *upper)
    pool = source["record_inventory"]
    by_name = {n: [(i, r) for i, r in enumerate(pool) if r["name"] == n] for n in names}
    headers, inputs, axes = {}, {}, {}
    file_frames = {}
    horizontal = set()
    # A conflicting linked level may have been excluded from the admitted grid roles.
    unbound_labels = ({f["name"] for f in source["fields"].values()
                       if _utrack_vertical_label(f["name"], f["attributes"])}
                      if utrack and source["format"] == "netcdf" else set())
    for name in names:
        candidates = [(i, record) for i, record in by_name[name] if (
            name not in upper or source["fields"][record["field_id"]].get("group") == "isobaric"
            or "isobaric" in source["fields"][record["field_id"]]["dimensions"])]
        by_name[name] = candidates
        records = [record for _, record in candidates]
        identities = {record["field_id"] for record in records}
        if len(identities) != 1:
            raise ValueError(
                f"{method}: required input {name} missing or ambiguous in selected metadata")
        field = source["fields"][next(iter(identities))]
        record = records[0]
        attrs = field["attributes"]
        if record.get("catalogue_values"):
            from frameit.processing.requests import source_field_metadata

            attrs = source_field_metadata(source, field, record=record)["attributes"]
        headers[name] = xr.DataArray(0., attrs=attrs, name=name)
        quantity = {"absv": "vorticity", "z": "geopotential", pressure: "pressure"}.get(
            name, "velocity")
        unit_metadata(headers[name], quantity)
        axis = _field_axis(source, field, record, by_name)
        selector = {}
        if name in upper:
            if axis is None or axis["dimension"] != "isobaric" or axis["descriptor"] is None:
                raise ValueError(f"{method}: {name} requires the admitted AROME isobaric axis")
            axes[name] = axis["descriptor"]
            unit_metadata(xr.DataArray(0., attrs=axes[name]["attributes"]), "pressure")
            if method == "multifield_vortex":
                selector = {"values": [850, 700] if name == "z" else [850, 700, 500],
                            "units": "hPa"}
            elif utrack:
                if attrs.get("standard_name") not in {None, "", "atmosphere_absolute_vorticity"}:
                    raise ValueError("UTrack absv metadata must describe absolute vorticity")
                label = axes[name]
                if (attrs.get("GRIB_typeOfLevel") not in {None, "", *GRIB_PRESSURE_UNITS}
                        or label["attributes"].get("standard_name") not in {None, "", "air_pressure"}):
                    raise ValueError("UTrack absv metadata must describe an isobaric level")
                position = utrack_850_position(xr.DataArray(
                    label["values"], attrs=label["attributes"], name=axis["coordinate"]))
                selector = {"indices": [int(axis["native"][position])], "units": "hPa"}
        elif axis is not None:
            raise ValueError(f"{method}: {name} must be a 2d horizontal input")
        if utrack:
            gridded_records = {r["grid_id"]: r for r in records}
            if name in surface:
                file_frames[name] = _metadata_frames(
                    field.get("dataset_attributes", {}), f"{name} in {record['locator']['path']}")
                if source["format"] == "grib":
                    if (attrs.get("GRIB_typeOfLevel") != "heightAboveGround"
                            or any(r["level"] != 10 for r in records)):
                        raise ValueError(f"UTrack {name} requires 10 m above-ground wind")
                elif (attrs.get("GRIB_typeOfLevel") not in {None, "", "heightAboveGround"}
                      or attrs.get("GRIB_level", 10) != 10
                      or any(dep in unbound_labels for dep, role in field["dependencies"].items()
                             if role == "coordinates")):
                    raise ValueError(f"UTrack {name} requires 10 m above-ground wind; "
                                     "the linked vertical metadata do not support it")
                for grid_id in gridded_records:
                    for label, coord in source["native_grids"][grid_id]["coordinates"].items():
                        meta = coord["attributes"]
                        if _utrack_vertical_label(label, meta):
                            if (coord["dimensions"] or meta.get("standard_name") != "height"
                                    or meta.get("positive", "up") != "up"
                                    or convert_units(xr.DataArray(
                                        coord["values"], attrs=meta), "distance").item() != 10.):
                                raise ValueError(f"UTrack {name} requires 10 m above-ground wind")
            horizontal.update(_utrack_horizontal_identity(source, r) for r in gridded_records.values())
        inputs[name] = selector
    if utrack and len(horizontal) != 1:
        raise ValueError("UTrack winds and vorticity must share the same horizontal grid")
    conf.wind_pairs = []
    for group, components in (("surface", surface), *(
            [("isobaric", ("u", "v"))] if "u" in upper else [])):
        from frameit.core.configuration import field_selection

        request = conf.source_requests[conf.source_name]
        declarations = []
        for pair in conf.sources[conf.source_name]["wind_pairs"]:
            selected = [field_selection(request, pair[key])[:2] for key in ("u", "v")]
            if tuple(item[0] for item in selected) == components and all(
                    item[1] in {None, group} for item in selected):
                declarations.append({**pair, "u": components[0], "v": components[1]})
        if len(declarations) > 1:
            raise ValueError(f"{method}: ambiguous wind declarations for {group}")
        if declarations:
            pair = dict(declarations[0], group=group, reference_frame=declarations[0]["basis"])
            pair.pop("basis")
        else:
            evidence = [set(_metadata_frames(headers[name].attrs, name)
                            + file_frames.get(name, [])) for name in components]
            if len(evidence[0]) != 1 or evidence[0] != evidence[1]:
                raise ValueError(f"{method}: wind basis is missing or conflicting; "
                                 "declare sources.*.wind_pairs")
            pair = dict(group=group, u=components[0], v=components[1],
                        reference_frame=next(iter(evidence[0])))
        validate_pair_frame(xr.Dataset(headers), pair, conf)
        for name in components:
            if any(frame != pair["reference_frame"] for frame in file_frames.get(name, ())):
                raise ValueError(f"Conflicting wind reference metadata on {name} in its owning "
                                 f"file: declared {pair['reference_frame']}, metadata "
                                 f"{file_frames[name]}")
        if pair["reference_frame"] != "earth":
            raise ValueError(f"{method}: grid winds require explicit supported preparation")
        conf.wind_pairs.append(pair)
    if method == "pressure_centroid":
        if len(source["selected_times"]) < 2:
            raise ValueError("pressure_centroid requires at least two selected source times")
        levels = [convert_units(xr.DataArray(axis["values"], attrs=axis["attributes"]),
                                "pressure", target="hPa").values for axis in axes.values()]
        if any(len(values) < 2 for values in levels) or any(
                not (levels[0] == values).all() for values in levels[1:]):
            raise ValueError("pressure_centroid requires matching pressure support on u/v/z")
    conf.tracking_var_aliases = dict(zip(("u10m", "v10m"), surface, strict=True))
    if not utrack:
        conf.tracking_var_aliases.update(mslp=pressure)
        if upper:
            conf.tracking_var_aliases.update(u="u", v="v", geopot="z")
    return {"method": method, "inputs": inputs,
            "selected_time_count": len(source["selected_times"]),
            "value_checks": "pending execution; no scientific payload read during binding"}
