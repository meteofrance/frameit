# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import json
import logging
import re
from collections import ChainMap
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import xarray as xr

from frameit.check.check_functions import drop_time_dupes
from frameit.io.loader import managed_loading, resolve_input_files
from frameit.processing.requests import (
    build_group_ds,
    normalize_requests,
    selected_native_indices,
)
from frameit.processing.wind_reference import MESONH_PROJECTION_METADATA

logger = logging.getLogger(__name__)


def validate_native_metadata(datasets, variables=None, *, model):
    """Reject changing native scientific definitions without loading physical fields."""
    from frameit.processing.polar.metadata import coordinate_dependency_names

    keys = ("units", "standard_name", "long_name", "cell_methods", "positive", "axis",
            "bounds", "formula_terms", "grid_mapping", "online_operation",
            "interval_operation", "interval_write")
    reference = {}
    for ds in datasets:
        selected = ds[[name for name in ds.data_vars if variables is None or name in variables]]
        names = set(selected.variables) | coordinate_dependency_names(
            ds, selected.data_vars, coordinates=selected.coords)
        for name in names:
            attrs = {key: ds[name].attrs.get(key) for key in keys}
            if name in reference:
                changed = [key for key in keys if not np.array_equal(attrs[key], reference[name][key])]
                if changed:
                    raise ValueError(f"{model} {name}: conflicting scientific metadata {changed} "
                                     "across time-series files; no automatic conversion is applied")
            else:
                reference[name] = attrs
    if model == "CROCO":
        from frameit.io.croco_utils import validate_croco_coefficients

        validate_croco_coefficients(datasets, variables)


def normalize_netcdf_time(ds: xr.Dataset, conf) -> xr.Dataset:
    """Use sample time without discarding an evidenced AROME forecast clock."""
    from frameit.io.grib_utils import normalize_isobaric_coordinates

    ds = normalize_isobaric_coordinates(ds)
    if getattr(conf, "atm_model", None) == "NEMO":
        from frameit.io.nemo_utils import prepare_nemo

        ds = prepare_nemo(ds, conf)
    elif getattr(conf, "atm_model", None) == "CROCO":
        from frameit.io.croco_utils import prepare_croco

        ds = prepare_croco(ds, conf)
    elif getattr(conf, "netcdf_surfex_fields", []):
        from frameit.io.surfex_utils import prepare_surfex

        ds = prepare_surfex(ds, conf)
    source = getattr(conf, "name_time_dim", None) or "time"
    if source in ds and ds[source].ndim == 1 and ds[source].dims != (source,):
        ds = ds.swap_dims({ds[source].dims[0]: source})
    renames = {}
    if source != "time" and source in ds:
        if "time" in ds:
            reference = ds["time"]
            if (str(getattr(conf, "atm_model", "")).upper() != "AROME"
                    or reference.ndim != 0
                    or reference.attrs.get("standard_name") != "forecast_reference_time"):
                raise ValueError(f"NetCDF time coordinate 'time' conflicts with configured "
                                 f"dimension {source!r}; provide an unambiguous source schema")
            if "forecast_reference_time" in ds:
                other = ds["forecast_reference_time"]
                if other.ndim != 0 or not reference.variable.equals(other.variable):
                    raise ValueError("Conflicting forecast reference clocks")
                ds = ds.drop_vars("forecast_reference_time")
            renames["time"] = "forecast_reference_time"
        renames[source] = "time"
    result = ds.rename(renames).copy(deep=False)
    if "time" in result and result.time.ndim == 0:
        result = result.assign_coords(time=("time", np.atleast_1d(result.time.values),
                                             dict(result.time.attrs)))
    if renames:
        pattern = re.compile(r"\b(" + "|".join(map(re.escape, renames)) + r")\b")
        for name in result.variables:
            for mapping in ("attrs", "encoding"):
                metadata = dict(getattr(result[name], mapping))
                for key in ("coordinates", "bounds", "cell_methods", "formula_terms",
                            "cell_measures", "ancillary_variables"):
                    if isinstance(metadata.get(key), str):
                        metadata[key] = pattern.sub(lambda m: renames[m[0]], metadata[key])
                setattr(result[name], mapping, metadata)
    return result


def _merge_variable_shards(datasets, variables, *, metadata=()):
    """Merge selected disjoint fields only after exact coordinate/auxiliary checks."""
    from frameit.processing.polar.metadata import coordinate_dependency_names

    requested = set(variables)
    geography = {name for ds in datasets for name in ds.variables
                 if name in {"latitude", "longitude", "nav_lat", "nav_lon"}
                 or ds[name].attrs.get("standard_name") in {"latitude", "longitude"}}
    for ds in datasets:
        if geography - set(ds.variables):
            raise ValueError("NetCDF variable shards require the same geography coordinates")
    datasets = [ds.set_coords(sorted(geography | (set(metadata) & set(ds)))) for ds in datasets]
    logical = ChainMap(*({name: ds[name] for name in ds.variables} for ds in datasets))
    dependencies = coordinate_dependency_names(
        logical, requested, coordinates={name for ds in datasets for name in ds.coords})
    missing = requested - {name for ds in datasets for name in ds.variables}
    if missing:
        raise ValueError(f"NetCDF variable shards missing providers: {sorted(missing)}")
    selected, seen = [], {}
    for ds in datasets:
        names = requested & set(ds.variables)
        keep = names | dependencies | set(ds.coords)
        part = ds.drop_vars([name for name in ds.data_vars if name not in keep])
        for name in set(part.variables) | set(ds.coords):
            value = ds[name]
            if name in seen:
                if name in requested and name not in part.coords:
                    raise ValueError(f"Duplicate selected physical-field provider: {name}")
                if value.ndim > 2:
                    raise ValueError(f"Repeated auxiliary {name} requires unsupported physical-cube equality")
                if not value.variable.identical(seen[name].variable):
                    raise ValueError(f"NetCDF variable shards disagree on coordinate/auxiliary {name}")
            else:
                seen[name] = value
        if selected and ("time" not in part.coords or "time" not in selected[0].coords
                         or not part.time.variable.equals(selected[0].time.variable)):
            raise ValueError("Variable shards require identical sample time coordinates")
        if selected and (set(part.coords) ^ set(selected[0].coords)) & {"forecast_reference_time"}:
            raise ValueError("Variable shards require the same forecast reference clock")
        selected.append(part)
    return xr.merge(selected, join="exact", compat="identical", combine_attrs="override")

# -------------------------------------------------------------
# Minimal, reusable NetCDF opener
# -------------------------------------------------------------


@managed_loading
def concat_nc2ds(
    files_list: Iterable[str | Path],
    variables: Iterable[str],
    concat_dimension: str | None = None,
    parallel: bool = False,
    strict: bool = False,
    resources=None,
    engine="h5netcdf",
    chunks=None,
    *,
    file_layout="time_series",
    time_conf=None,
) -> xr.Dataset:
    """
    Open selected NetCDF variables lazily, concatenating times or merging shards.

    Uses ``xr.open_dataset`` for each original input, then combines the
    lazy arrays. Loading is lazy (Dask): data is read only on
    explicit ``.compute()`` calls.

    Parameters
    ----------
    files_list : Iterable[str or Path]
        Ordered list of NetCDF file paths. With ``strict=True`` the order is
        preserved and missing entries fail; otherwise paths are sorted and
        non-existent entries are skipped for compatibility.
    variables : Iterable[str]
        Variable names to keep.  All other data variables are dropped before
        loading to reduce memory usage.
    concat_dimension : str or None, optional
        Dimension along which to concatenate (e.g. "time").  When None,
        use ``combine_by_coords`` for the default time-series layout.
    parallel : bool, optional
        Retained for API compatibility. Original handles are opened serially;
        array computation remains lazy and can use Dask scheduling.
    strict : bool, optional
        Consume an explicit inventory without sorting or omitting missing
        paths. Default False preserves ordinary discovery behaviour.
    file_layout : {"time_series", "variables"}
        Default time series require selected fields in every file. Variable
        shards require unique selected providers and exact shared coordinates.

    Returns
    -------
    xr.Dataset
        Lazily-loaded concatenated dataset containing the requested variables
        plus any coordinates present in the files.

    Raises
    ------
    FileNotFoundError
        If no existing files are found after filtering.
    """
    files = resolve_input_files(files_list, strict=strict)
    variables = list(variables)

    if file_layout not in {"time_series", "variables"}:
        raise ValueError("NetCDF file_layout must be time_series or variables")
    conf = time_conf or SimpleNamespace(name_time_dim=concat_dimension or "time", atm_model="AROME")
    if file_layout == "variables":
        opened = [normalize_netcdf_time(resources.open_netcdf(
            path, engine=engine, chunks={} if chunks is None else chunks), conf) for path in files]
        metadata = (set(MESONH_PROJECTION_METADATA) & set(variables)
                    if conf.atm_model == "MNH" else ())
        return _merge_variable_shards(opened, variables, metadata=metadata)

    from frameit.processing.polar.metadata import coordinate_dependency_names

    opened = []
    for path in files:
        original = resources.open_netcdf(
            path, engine=engine, chunks={} if chunks is None else chunks)
        missing = set(variables) - set(original.variables)
        if missing:
            raise ValueError(f"{path}: NetCDF input missing requested fields: {sorted(missing)}")
        prepared = normalize_netcdf_time(original, conf)
        keep = set(variables) | coordinate_dependency_names(prepared, variables)
        opened.append(prepared.drop_vars([name for name in prepared.data_vars if name not in keep]))
    if getattr(conf, "atm_model", None) in {"NEMO", "CROCO"}:
        validate_native_metadata(opened, model=conf.atm_model)
    if getattr(conf, "netcdf_surfex_fields", []):
        from frameit.io.surfex_utils import validate_surfex_metadata

        validate_surfex_metadata(opened, set(conf.netcdf_surfex_fields) & set(variables))
    if len(opened) == 1:
        ds = opened[0]
    elif concat_dimension:
        ds = xr.concat(opened, dim="time" if "time" in opened[0].dims else concat_dimension,
                       data_vars="all", coords="different", compat="no_conflicts", join="outer")
    else:
        ds = xr.combine_by_coords(opened)

    if logger:
        present = ", ".join(sorted(ds.data_vars))
        logger.debug("Variables in dataset: %s", present)
    return ds


# -------------------------------------------------------------
# Main API: 2 requests (user + tracker)
# -------------------------------------------------------------


def input_chunk_plan(source, chunks):
    """Match native keys against the complete owning read binding, never a wider read."""
    targets = {}
    binding = source["requests"]["binding"]
    for record in binding["records"]:
        field = source["fields"][record["field_id"]]
        targets.setdefault(field["name"], set()).update(field["dimensions"])
    unknown = set(chunks or {}) - {dim for dims in targets.values() for dim in dims}
    if unknown:
        raise ValueError(f"Unknown source reader chunks dimensions: {sorted(unknown)}")
    return {
        "requested": dict(chunks or {}),
        "targets": {name: {dim: size for dim, size in (chunks or {}).items() if dim in dims}
                    for name, dims in targets.items()},
        "automatic": (
            "Dask resolves chunks on selected backend views; applications record actual sizes"),
        "applications": [],
    }


def _selected_netcdf(files, binding, source, resources, *, engine, chunks):
    """Keep bound product selections separate from internal native read stencils."""
    if binding.get("status") != "bound" or source is None:
        raise ValueError(
            "NetCDF selected_records requires bound requests and owning source metadata")
    from frameit.io.grib_utils import normalize_isobaric_coordinates
    from frameit.processing.polar.contracts import require_executable_products

    require_executable_products(binding, source)
    layout = source.setdefault("reader_layout", input_chunk_plan(source, chunks))
    admitted = {Path(path).resolve() for path in files}
    model = {"mesonh": "MNH"}.get(source["model"], source["model"].upper())
    if model == "CROCO":
        from frameit.io.croco_utils import validate_bound_support

        if any(record["locator"]["format"] != "netcdf"
               or Path(record["locator"]["path"]).resolve() not in admitted
               for record in binding["records"]):
            raise ValueError("CROCO selected locator is outside the admitted NetCDF files")
        validate_bound_support(source, binding, engine=engine, resources=resources)
    native_conf = SimpleNamespace(
        atm_model=model, cartesian_horizontal_winds="native",
        cartesian_vertical_velocity="interfaces", compute_polar_proj=False,
    )
    samples_by_record = {}
    records = binding["records"]
    omit_dtcur = (any(record.get("scalar_dtcur_alias") for record in records)
                  and any("DTCUR" not in record["temporal_names"] for record in records))

    def sample(name, record):
        key = name, id(record)
        if key in samples_by_record:
            return samples_by_record[key]
        locator = record["locator"]
        path = Path(locator["path"])
        if locator["format"] != "netcdf" or path.resolve() not in admitted:
            raise ValueError(
                f"{name}: selected locator is outside the admitted NetCDF files")
        if record["selection_grid_id"] != record["grid_id"]:
            raise ValueError(f"{name}: destination-grid transformation is not executable")
        original = normalize_isobaric_coordinates(
            resources.open_netcdf(path, engine=engine, chunks=None))
        variable = locator["variable"]
        grid = source["native_grids"][record["grid_id"]]
        coordinates = set(grid["coordinates"]) | {record["clock"]}
        coordinates.update(dim for dim in locator["coordinate_indexers"]
                           if dim in original.coords)
        coordinates.update(n for n in original.variables if (
            n in {"time", "valid_time", "time_counter", "time_centered",
                  "scrum_time", "forecast_reference_time"}
            or original[n].attrs.get("standard_name") in {"time", "forecast_reference_time"}
            or original[n].attrs.get("axis") == "T"))
        if omit_dtcur:
            coordinates.discard("DTCUR")
        coordinates.update(original[n].attrs["bounds"] for n in list(coordinates)
                           if original[n].attrs.get("bounds"))
        coords = {n: original[n].variable.copy(deep=False) for n in coordinates}
        for n, definition in grid["coordinates"].items():
            if (coords[n].ndim == 0 and coords[n].attrs.get("standard_name") == "forecast_period"
                    and definition["dimensions"]):
                coords[n] = coords[n].set_dims(definition["dimensions"])
        dataset = xr.Dataset(
            {name: original[variable].variable.copy(deep=False)},
            coords=coords,
            attrs=dict(original.attrs),
        )
        if name != variable:
            dataset[name].attrs["source_variable_name"] = variable
        indexers = {dim: [position] for dim, position in
                    locator["coordinate_indexers"].items() if dim in dataset.dims}
        indexers.update({dim: [position] for dim, position in locator["indexers"].items()
                         if dim in original[variable].dims})
        vertical = record["vertical"]
        if vertical is not None:
            dim = vertical["dimension"]
            indexers[dim] = record["source_positions"]
            index = f"{dim}_source_native_index"
            if variable == index and variable in original.coords:
                dataset = dataset.set_coords(name)
            if model in {"NEMO", "CROCO"} and index not in dataset:
                if index in original.coords:
                    dataset = dataset.assign_coords({
                        index: original[index].variable.copy(deep=False)})
                else:
                    dataset = dataset.assign_coords({index: (dim, np.arange(original.sizes[dim]), {
                        "units": "1", "long_name": f"zero-based native source {dim} index"})})
        dataset = dataset.isel(indexers)
        if omit_dtcur:
            dataset.attrs["frameit_omitted_time_alias"] = (
                "DTCUR is absent from some selected native samples; use canonical time")
        elif record.get("scalar_dtcur_alias"):
            # The admitted current-time alias belongs to this sample, not to the file series.
            dataset = dataset.assign_coords(DTCUR=dataset.DTCUR.variable.set_dims(("time",)))
        samples_by_record[key] = dataset
        return dataset

    def effective_attrs(value, record, descriptor):
        metadata = record.get("field_metadata", descriptor.get("field_metadata"))
        attrs = ({**metadata["attributes"],
                  "frameit_metadata_origins": json.dumps(metadata["origins"], sort_keys=True)}
                 if metadata else value.attrs)
        if model == "CROCO" and record["locator"]["variable"] == "mask_rho":
            from frameit.io.croco_utils import mask_rho_attributes

            attrs = mask_rho_attributes(attrs)
        return attrs

    def formula_support(dataset, record):
        """Only already-bound ordinary-reader support can accompany a product."""
        field = source["fields"][record["field_id"]]
        dependencies = dict(field.get("dependencies", {}))
        roles = {"coordinates", "formula_terms", "cell_measures"}
        if model == "CROCO":
            roles.add("ancillary_variables")
            pending, visited = list(dependencies), set()
            while pending:
                name = pending.pop()
                if name in visited:
                    continue
                visited.add(name)
                descriptor = binding["dependencies"].get(name)
                if descriptor is None:
                    continue
                support_field = source["fields"][descriptor["field_id"]]
                for child, role in support_field.get("dependencies", {}).items():
                    if child not in dependencies:
                        dependencies[child] = role
                        pending.append(child)
        for name, role in dependencies.items():
            if role not in roles or name in dataset:
                continue
            descriptor = binding["dependencies"].get(name)
            records = [] if descriptor is None else [
                other for other in descriptor["records"]
                if all(other.get(key) == record.get(key) for key in (
                    "time", "cycle", "native_axes"))]
            if len(records) != 1:
                raise ValueError(f"{name}: ordinary-reader support needs one bound native record")
            other = records[0]
            support = sample(name, other)
            parent, vertical = record["vertical"], other["vertical"]
            if parent is not None and vertical is not None and (
                    parent["dimension"] == vertical["dimension"]):
                native = vertical["source_native_indices"]
                support = support.isel({vertical["dimension"]: [
                    native.index(index) for index in parent["source_native_indices"]]})
            value = support[name].variable.copy(deep=False)
            if model == "CROCO":
                value.attrs = effective_attrs(value, other, descriptor)
            dataset = dataset.assign_coords({
                **{n: value.variable.copy(deep=False) for n, value in support.coords.items()
                   if n not in dataset},
                name: value,
            })
        return dataset

    def prepare(dataset, name, record, descriptor):
        supported = formula_support(dataset, record)
        metadata = record.get("field_metadata", descriptor.get("field_metadata"))
        supported[name].attrs = effective_attrs(supported[name], record, descriptor)
        sea_fields = binding.get("interpretation", {}).get("fields", [])
        if name in sea_fields:
            from frameit.io.surfex_utils import prepare_surfex

            if name != "FRAC_SEA":
                support = binding["dependencies"].get("FRAC_SEA", {})
                records = [other for other in support.get("records", [])
                           if other["time"] == record["time"] and other["cycle"] == record["cycle"]]
                if len(records) != 1:
                    raise ValueError("SURFEX selected SEA field requires one selected FRAC_SEA")
                fraction = sample("FRAC_SEA", records[0]).FRAC_SEA
                meaning = records[0].get(
                    "field_metadata", binding["dependencies"]["FRAC_SEA"]["field_metadata"])
                fraction.attrs = {
                    **meaning["attributes"],
                    "frameit_metadata_origins": json.dumps(meaning["origins"], sort_keys=True)}
                supported = supported.assign_coords(FRAC_SEA=fraction)
            native_conf.netcdf_surfex_fields = [name]
            native_conf.requested_variables_user = {"native": {"variables": [name]}}
            supported = prepare_surfex(supported, native_conf)
            for field_name in {name, "FRAC_SEA"}:
                selected_metadata = metadata if field_name == name else meaning
                supported[field_name].attrs["surfex_units_source"] = selected_metadata[
                    "origins"]["units"]
            source["interpretation"]["value_checks"] = "selected FRAC_SEA physical support checked"
        native_conf.requested_variables_user = {"native": {"variables": [name]}}
        if model == "NEMO":
            from frameit.io.nemo_utils import prepare_nemo

            supported = prepare_nemo(supported, native_conf)
        elif model == "CROCO":
            from frameit.io.croco_utils import prepare_croco

            original = resources.open_netcdf(
                record["locator"]["path"], engine=engine, chunks=None)
            # Admission needs the native rho/face coordinate evidence, not companions.
            metadata = ("lat_rho", "lon_rho", "xi_rho", "eta_rho",
                        "lat_u", "lon_u", "xi_u", "lat_v", "lon_v", "eta_v",
                        "Vtransform")
            validation = supported.assign_coords({
                n: original[n].variable.copy(deep=False) for n in metadata
                if n in original and n not in supported})
            prepared = prepare_croco(validation, native_conf, native_axes=original.coords)
            supported = supported.assign_coords({
                n: prepared[n] for n in supported.coords})
        return supported

    def groups(descriptors, *, export_support=False):
        by_grid, vertical_dims = {}, set()
        for name, descriptor in descriptors.items():
            if descriptor.get("operation"):
                continue
            samples, validation = {}, []
            for record in descriptor["records"]:
                dataset = sample(name, record)
                prepared = prepare(dataset, name, record, descriptor)
                validation.append(prepared)
                if export_support:
                    dataset = prepared.reset_coords(
                        [field for field in descriptors if field in prepared.coords])
                elif name in binding.get("interpretation", {}).get("fields", []):
                    dataset = prepared.reset_coords(
                        [field for field in descriptors if field in prepared.coords])
                vertical = record["vertical"]
                if vertical is not None:
                    vertical_dims.add(vertical["dimension"])
                    for coordinate, metadata in vertical["coordinates"].items():
                        attrs = dict(metadata["attributes"])
                        if (coordinate in prepared
                                and "source_standard_name" in prepared[coordinate].attrs):
                            attrs.update({key: prepared[coordinate].attrs[key]
                                          for key in ("standard_name", "source_standard_name")})
                        value = xr.Variable(
                            metadata["dimensions"], metadata["values"], attrs=attrs)
                        value = value.isel({
                            dim: [position] for dim, position in
                            record["locator"]["coordinate_indexers"].items() if dim in value.dims})
                        dataset = dataset.assign_coords({coordinate: value})
                    if (not export_support
                            and f"{vertical['dimension']}_source_native_index" not in dataset):
                        dataset = dataset.assign_coords({
                            f"{vertical['dimension']}_source_native_index": (
                                vertical["dimension"], vertical["source_native_indices"],
                                {"units": "1"})})
                # Chunk the selected backend view, not a full-file Dask array.
                # Otherwise a retained time chunk can read excluded scientific samples.
                dataset = dataset.chunk({dim: size for dim, size in (chunks or {}).items()
                                          if dim in dataset.dims})
                application = {
                    "field": name, "grid_id": record["grid_id"],
                    "source_time": str(record["time"]),
                    "chunks": {dim: list(sizes)
                               for dim, sizes in dataset[name].variable.chunksizes.items()},
                }
                if application not in layout["applications"]:
                    layout["applications"].append(application)
                dataset = normalize_netcdf_time(
                    dataset, SimpleNamespace(name_time_dim=record["clock"], atm_model="AROME"))
                samples.setdefault(record["grid_id"], []).append(dataset)
            if model in {"NEMO", "CROCO"}:
                validate_native_metadata(validation, [name], model=model)
            for grid_id, sequence in samples.items():
                concat_dim = "time"
                if len(sequence) > 1 and sequence[0].time.ndim > 1:
                    locators = [r["locator"]["coordinate_indexers"]
                                for r in descriptor["records"] if r["grid_id"] == grid_id]
                    varying = [
                        dim for dim in sequence[0].time.dims
                        if len({locator[dim] for locator in locators}) > 1
                        or (dim in sequence[0].coords and any(
                            not sequence[0][dim].variable.equals(ds[dim].variable)
                            for ds in sequence[1:]))]
                    if len(varying) != 1:
                        raise ValueError(
                            f"{name}: multiple native sample axes require an explicit "
                            "assembly contract; no flattening or gap filling is applied")
                    concat_dim = varying[0]
                static = (not source["fields"][descriptor["field_id"]]["time_varying"]
                          and len({r["locator"]["path"] for r in descriptor["records"]}) == 1)
                # Static support in successive files belongs to each sample, not an
                # eager equality check or an arbitrary first-file depth/mask.
                support_coords = [
                    n for n in sequence[0].coords
                    if n in binding["dependencies"] and sequence[0][n].ndim >= 2
                    and len({r["locator"]["path"]
                             for r in binding["dependencies"][n]["records"]}) > 1]
                combined = (sequence[0] if len(sequence) == 1 else xr.concat(
                    sequence, dim=concat_dim, data_vars="minimal" if static else "all",
                    coords=support_coords or "minimal",
                    compat="equals", join="exact", combine_attrs="override"))
                if export_support:
                    from frameit.processing.requests import align_initial_gap

                    combined = align_initial_gap(combined, name, source)
                # Keep absent-field read clocks real; only output preparation pads them.
                key = ((grid_id, name) if not export_support and any(
                    gap["field"] == name for gap in source.get("allowed_gaps", [])) else grid_id)
                by_grid.setdefault(key, []).append(combined)
        from frameit.tracking.tracker_core import merge_internal_stencils

        return {grid_id: (xr.merge(datasets, join="exact", compat="identical",
                                  combine_attrs="override") if export_support else
                         merge_internal_stencils(datasets, vertical_dims))
                for grid_id, datasets in by_grid.items()}

    return (
        groups(binding["products"].get("model_grid", {}), export_support=True),
        {"internal": groups(binding["dependencies"])} if binding["dependencies"] else {},
    )


@managed_loading
def concat_nc2ds_by_vert_coord(
    files: Iterable[str | Path],
    user_requested_variables_yaml: dict[str, dict[str, Any]],
    tracker_requested_variables_by_method_yaml: dict[str, dict[str, Any]] | None,
    method: str | None = None,
    *,
    concat_dimension: str = "time",
    parallel: bool = False,
    strict: bool = False,
    keep_geovars: bool = True,
    geovar_candidates: tuple[str, ...] = ("latitude", "longitude", "grid_rotation"),
    float_tol: float | None = None,
    resources=None,
    wind_conf=None,
    engine="h5netcdf",
    chunks=None,
    duplicate_time_policy="first",
    native_output_groups=None,
    file_layout="time_series",
    selected_records=None,
    source_plan=None,
) -> tuple[dict[str, xr.Dataset], dict[str, dict[str, xr.Dataset]]]:
    """
    Open the NetCDF files once then apply two independent requests.
    Returns (by_group_user, by_group_tracker), where:
      - by_group_user: {group -> xr.Dataset}
      - by_group_tracker: {method -> {group -> xr.Dataset}}

    Supported groups: "level", "level_w", "surface".
    - Vertical selection by indices or values. `float_tol=None` enforces exact equality.
    - The variables actually read are the union of those requested by the user
      and all selected tracker methods, plus geographic variables if present.
    - `method=None` processes all methods present in `tracker_requested_variables_by_method_yaml`.
    - Loading is lazy (Dask): data is only read on explicit .compute() calls
      downstream, avoiding MemoryError on large datasets.
    - With ``wind_conf`` for MNH, U/V are prepared on native mass points before
      selection. Native W is retained and ``_frameit_mass_w`` carries its mass
      counterpart until the runner consumes it; it is not an export variable.
    """

    if selected_records is not None:
        return _selected_netcdf(
            files, selected_records, source_plan, resources,
            engine=engine, chunks=chunks,
        )

    # Normalise the user request
    user_req = normalize_requests(user_requested_variables_yaml)

    # Select and normalise tracker methods
    tracker_yaml = tracker_requested_variables_by_method_yaml or {}
    if method is None:
        methods = list(tracker_yaml.keys())
    else:
        methods = [m for m in tracker_yaml.keys() if m == method]
        if not methods:
            logger.warning(
                "Tracker method '%s' not found. No tracker group will be produced.", method
            )
    tracker_req_by_method: dict[str, dict[str, Any]] = {
        m: normalize_requests(tracker_yaml.get(m, {})) for m in methods
    }

    files = resolve_input_files(files, strict=strict)
    chunks = {} if chunks is None else chunks
    ocean = wind_conf is not None and wind_conf.atm_model in {"NEMO", "CROCO"}
    if ocean:
        float_tol = None
        geovar_candidates = (wind_conf.name_latitude, wind_conf.name_longitude)
    mnh_centroid = wind_conf is not None and wind_conf.atm_model == "MNH" and (
        method == "pressure_centroid" or (method is None and "pressure_centroid" in methods))
    mnh_fields = None
    vortex_fields = None
    if wind_conf is not None and wind_conf.atm_model == "MNH" and (
        method == "multifield_vortex" or (method is None and "multifield_vortex" in methods)
    ):
        from frameit.tracking.multifield_inputs import inspect_inputs, mnh_loading_fields

        for path in files:
            header = resources.open_netcdf(path, engine=engine, chunks=chunks)
            inspect_inputs([header], wind_conf, str(path))
            fields, requests = mnh_loading_fields(header, wind_conf)
            if vortex_fields is not None and fields != vortex_fields:
                raise ValueError(f"multifield_vortex: inconsistent source fields in {path}")
            vortex_fields = fields
        tracker_req_by_method["multifield_vortex"] = normalize_requests(requests)
        wind_conf.requested_variables_tracker["multifield_vortex"] = requests
    if mnh_centroid:
        from frameit.tracking.pressure_centroid_inputs import inspect_mnh_sequence

        def headers():
            for path in files:
                yield path, resources.open_netcdf(path, engine=engine, chunks=chunks)

        mnh_fields = inspect_mnh_sequence(headers())
        logger.info("MNH pressure_centroid inputs: pressure=%s, winds=%s/%s, height=%s",
                    mnh_fields.pressure, mnh_fields.u, mnh_fields.v,
                    ",".join(mnh_fields.height))
        tracker_req_by_method["pressure_centroid"] = normalize_requests(mnh_fields.requests())
        wind_conf.requested_variables_tracker["pressure_centroid"] = mnh_fields.requests()

    if file_layout not in {"time_series", "variables"}:
        raise ValueError("NetCDF file_layout must be time_series or variables")
    if len(files) > 1 and file_layout == "time_series":
        if wind_conf is not None and wind_conf.atm_model == "CROCO":
            from frameit.io.croco_utils import current_pairs, polar_fields

            pairs = current_pairs(wind_conf)
            polar = polar_fields(wind_conf)
            if pairs or polar:
                # Validate native companions before per-file rotation hides their metadata.
                headers = [normalize_netcdf_time(resources.open_netcdf(
                    path, engine=engine, chunks=chunks), wind_conf) for path in files]
                names = {name for pair in pairs for name in pair} | polar | {"mask_rho"}
                if pairs:
                    names.update(("angle", "mask_u", "mask_v"))
                validate_native_metadata(headers, names, model="CROCO")
        # Interpret units, basis and native brackets independently in each file.
        # Concatenating first would retain only one file's interpretation.
        users, trackers, natives = [], [], []
        for path in files:
            native = {} if native_output_groups is not None else None
            user, tracker = concat_nc2ds_by_vert_coord(
                [path], user_requested_variables_yaml, tracker_requested_variables_by_method_yaml,
                method, concat_dimension=concat_dimension, parallel=parallel, strict=True,
                keep_geovars=keep_geovars, geovar_candidates=geovar_candidates,
                float_tol=float_tol, resources=resources, wind_conf=wind_conf, engine=engine,
                chunks=chunks, duplicate_time_policy=duplicate_time_policy,
                native_output_groups=native,
                file_layout=file_layout,
            )
            users.append(user)
            trackers.append(tracker)
            if native is not None:
                natives.append(native)

        def combine(parts):
            result = {}
            for group in dict.fromkeys(g for part in parts for g in part):
                sequence = [part[group] for part in parts if group in part]
                if ocean or (wind_conf is not None and getattr(
                        wind_conf, "cartesian_horizontal_winds", "native") == "native"):
                    validate_native_metadata(sequence, model=wind_conf.atm_model)
                if getattr(wind_conf, "netcdf_surfex_fields", []):
                    from frameit.io.surfex_utils import validate_surfex_metadata

                    fields = set(wind_conf.netcdf_surfex_fields) & set().union(*(ds.data_vars for ds in sequence))
                    validate_surfex_metadata(sequence, fields)
                result[group] = drop_time_dupes(xr.concat(
                    sequence, dim="time", data_vars="minimal", coords="different",
                    compat="equals", join="exact", combine_attrs="override",
                ), keep=duplicate_time_policy)
            return result

        if native_output_groups is not None:
            native_output_groups.update(combine(natives))
        return combine(users), {
            m: combine([tree.get(m, {}) for tree in trackers]) for m in methods
        }

    # Minimal union of variables to read
    requested_vars_all: set[str] = set()
    for _, spec in user_req.items():
        requested_vars_all.update(spec.get("variables", []))
    for _m, blk in tracker_req_by_method.items():
        for _, spec in blk.items():
            requested_vars_all.update(spec.get("variables", []))
    if mnh_fields is not None:
        requested_vars_all.update(mnh_fields.variables)
    if vortex_fields is not None:
        requested_vars_all.update(vortex_fields.variables)

    wind_geometry = set()
    prepare_user_winds = (wind_conf is not None and not ocean
                          and (getattr(wind_conf, "cartesian_horizontal_winds", "native")
                               != "native"
                               or any("wind_speed" in r["variables"] for r in user_req.values())))
    if prepare_user_winds or tracker_req_by_method:
        from frameit.processing.derived.wind import wind_names
        from frameit.processing.wind_reference import wind_pairs

        for group in set(user_req) | {g for blk in tracker_req_by_method.values() for g in blk}:
            pairs = wind_pairs(wind_conf, group)
            names = [(p["u"], p["v"]) for p in pairs] or [wind_names(wind_conf, group)]
            for pair in names:
                if prepare_user_winds and requested_vars_all.intersection(pair):
                    requested_vars_all.update(pair)
        for pair in getattr(wind_conf, "wind_pairs", []):
            if requested_vars_all.intersection((pair["u"], pair["v"])):
                rotation = pair.get("rotation") or {}
                if rotation.get("method") == "coordinate":
                    requested_vars_all.add(rotation["coordinate"])
                if (rotation.get("method") == "mesonh_projection"
                        or wind_conf.atm_model == "MNH"):
                    wind_geometry.update(MESONH_PROJECTION_METADATA)

    if wind_conf is not None and wind_conf.atm_model == "CROCO":
        from frameit.io.croco_utils import current_pairs, polar_fields

        pairs = current_pairs(wind_conf)
        if pairs:
            requested_vars_all.update(name for pair in pairs for name in pair)
            requested_vars_all.update(("angle", "mask_rho"))
        if polar_fields(wind_conf):
            requested_vars_all.add("mask_rho")

    # Automatically add geographic variables
    requested_vars_all.discard("wind_speed")
    auto_geo = []
    if keep_geovars or wind_geometry:
        present = set()
        for path in files:
            header = resources.open_netcdf(path, engine=engine, chunks=chunks)
            present.update(header.variables)
        requested_vars_all.update(wind_geometry & present)
        auto_geo = [name for name in geovar_candidates if name in present] if keep_geovars else []
        if auto_geo:
            logger.info("Auto-adding geographic variables: %s", ", ".join(auto_geo))
        requested_vars_all.update(auto_geo)

    # Single lazy read (Dask via chunks={} in concat_nc2ds)
    ds = concat_nc2ds(
        files_list=files,
        variables=sorted(requested_vars_all),
        concat_dimension=concat_dimension,
        parallel=parallel,
        strict=strict,
        resources=resources,
        engine=engine,
        chunks=chunks,
        file_layout=file_layout,
        time_conf=wind_conf,
    )
    ds = ds.set_coords(sorted(wind_geometry & set(ds)))
    # The opener normalizes source clocks before selection and deduplication.
    if "time" in ds.dims:
        concat_dimension = "time"
    if ocean:
        from frameit.core.preflight import _check_requests

        _check_requests([ds], user_requested_variables_yaml, Path("selected-inputs"), tolerance=0.)

    for req in [user_req, *tracker_req_by_method.values()]:
        for spec in req.values():
            missing = set(spec.get("variables", [])) - set(ds.data_vars) - {"wind_speed"}
            if missing:
                raise ValueError(f"NetCDF input missing requested fields: {sorted(missing)}")

    # Promote geographic variables to coordinates if needed
    if auto_geo:
        keep_as_coords = [v for v in auto_geo if v in ds]
        if keep_as_coords:
            ds = ds.set_coords(keep_as_coords)

    if prepare_user_winds:
        from frameit.processing.derived.wind import normalize_native_wind_units
        from frameit.utils.units import normalize_geography

        ds = normalize_geography(ds, wind_conf)
        if str(wind_conf.atm_model).upper() == "MNH":
            from frameit.utils.units import convert_units

            for dim in (wind_conf.name_lon_dim, wind_conf.name_lat_dim):
                for name in (dim, dim + "_u", dim + "_v"):
                    if name in ds.coords and ds[name].attrs.get("units"):
                        ds = ds.assign_coords({name: convert_units(ds[name], "distance")})
        for group in set(user_req) | {g for blk in tracker_req_by_method.values() for g in blk}:
            # Centroid field discovery is validated by its explicitly declared
            # native adapter too; source units are canonical before concatenation.
            declarations = wind_pairs(wind_conf, group)
            pair_names = [p[c] for p in declarations for c in ("u", "v")]
            if not declarations:
                pair_names = wind_names(wind_conf, group)
            if group == "surface" or any(
                name in ds and group in ds[name].dims for name in pair_names
            ):
                ds = normalize_native_wind_units(ds, wind_conf, group)
        w_name = wind_conf.velocity_aliases.get("w_velocity", "WT")
        if w_name in ds:
            from frameit.processing.derived.wind import normalize_velocity_units

            ds[w_name] = normalize_velocity_units(ds[w_name], wind_conf)

    # Native collocation precedes both horizontal cropping and vertical selection.
    mass_w = None
    if prepare_user_winds and str(wind_conf.atm_model).upper() == "MNH":
        from frameit.processing.wind_collocation import prepare_native_mnh

        ds_user_native, mass_w = prepare_native_mnh(ds, wind_conf)
    elif wind_conf is not None and wind_conf.atm_model == "CROCO":
        from frameit.io.croco_utils import prepare_croco_currents

        ds_user_native = prepare_croco_currents(ds, wind_conf)
    elif prepare_user_winds:
        from frameit.processing.derived.wind import normalize_winds

        ds_user_native = ds
        for group in set(user_req) | {g for blk in tracker_req_by_method.values() for g in blk}:
            ds_user_native = normalize_winds(ds_user_native, wind_conf, group)
    else:
        ds_user_native = ds

    if mass_w is None and wind_conf is not None and wind_conf.atm_model == "MNH":
        w_name = wind_conf.velocity_aliases.get("w_velocity", "WT")
        mass_requested = getattr(wind_conf, "cartesian_vertical_velocity", "interfaces") == "mass"
        mass_requested |= (getattr(wind_conf, "compute_polar_proj", False)
                           and getattr(wind_conf, "polar_vertical_velocity", "mass") == "mass")
        if mass_requested and w_name in ds and "level_w" in ds[w_name].dims:
            from frameit.processing.wind_collocation import collocate_mnh_component

            mass_w = collocate_mnh_component(ds[w_name], ds, wind_conf, vertical=True)

    # Build groups
    out_user: dict[str, xr.Dataset] = {}
    out_trk: dict[str, dict[str, xr.Dataset]] = {}

    for g in user_req:
        if g in user_req:
            ds_u = build_group_ds(ds_user_native, user_req[g], g, concat_dimension, float_tol)
            if ds_u is not None:
                out_user[g] = ds_u

    if native_output_groups is not None:
        for group, req in user_req.items():
            native = build_group_ds(ds, req, group, concat_dimension, float_tol)
            if native is not None:
                # Mass axes and geography define the cell-aligned crop even if
                # every requested variable happens to be on staggered faces.
                for name in ("ni", "nj", "latitude", "longitude"):
                    if name in ds:
                        native = native.assign_coords({name: ds[name]})
                native_output_groups[group] = native

    if mass_w is not None and "level_w" in out_user:
        # Keep the requested native W product, but carry independently prepared
        # mass-point W through extraction for polar use. Trim this internal field
        # from Cartesian outputs in the runner after consuming it.
        if "level" in out_user:
            selected = mass_w.sel(level=out_user["level"]["level"])
            target_policy = "selected_mass_fields"
        elif user_req["level_w"].get("level_domain") == "physical":
            positions = selected_native_indices(
                ds, {"level_domain": "physical", "all_levels": True}, "level"
            )
            selected = mass_w.isel(level=positions)
            target_policy = "physical_mass_range"
        elif user_req["level_w"]["all_levels"]:
            selected = mass_w
            target_policy = "stored_mass_range"
        else:
            native_labels = out_user["level_w"]["level_w"].values
            indices = ds.indexes["level_w"].get_indexer(native_labels)
            if (indices < 0).any() or (indices >= mass_w.sizes["level"]).any():
                raise ValueError("Requested W interfaces lack corresponding native mass levels")
            selected = mass_w.isel(level=indices)
            target_policy = "corresponding_native_mass_indices"
        selected.attrs = dict(selected.attrs, vertical_location="mass",
                              w_target_mapping=target_policy,
                              w_source_interface_values=str(
                                  out_user["level_w"].level_w.values.tolist()),
                              w_mass_target_values=str(selected.level.values.tolist()))
        out_user["level_w"]["_frameit_mass_w"] = selected
        if native_output_groups is not None and "level_w" in native_output_groups:
            native_output_groups["level_w"]["_frameit_mass_w"] = selected

    for m, blk in tracker_req_by_method.items():
        grp_map: dict[str, xr.Dataset] = {}

        if m == "multifield_vortex" and vortex_fields is not None:
            from frameit.tracking.multifield_inputs import canonical_inputs

            # Prepare each file independently before concatenation: pressure,
            # altitude and vector conventions must not inherit the first file's units.
            grp_map["native"] = canonical_inputs(ds[list(vortex_fields.variables)], wind_conf)
        elif m == "pressure_centroid" and mnh_fields is not None:
            # Keep all native neighbours and physical-height dependencies. The
            # model adapter collocates/rotates before any vertical selection;
            # raw tracker vectors must not pass through generic normalization.
            names = list(mnh_fields.variables)
            grp_map["native"] = ds[names]

        # Special cases: fixed_box and prescribed_track
        elif m in {"fixed_box", "prescribed_track"}:
            # Minimal Dataset: no data_vars, coordinates only (time, latitude, longitude, etc.)
            data_vars = list(ds.data_vars)
            if data_vars:
                ds_t = ds.drop_vars(data_vars)
            else:
                ds_t = ds

            # Store under an arbitrary group name, e.g. "surface"
            grp_map["surface"] = ds_t

        else:
            # General case: go through build_group_ds
            for g in blk:
                if g in blk:
                    ds_t = build_group_ds(ds_user_native, blk[g], g, concat_dimension, float_tol)
                    if ds_t is not None:
                        grp_map[g] = ds_t

        if grp_map:
            out_trk[m] = grp_map

    # Final deduplication
    out_user = {g: drop_time_dupes(ds, keep=duplicate_time_policy) for g, ds in out_user.items()}
    out_trk = {
        m: {g: drop_time_dupes(ds, keep=duplicate_time_policy) for g, ds in grp.items()}
        for m, grp in out_trk.items()
    }

    return out_user, out_trk
