# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import hashlib
import json
import logging
import re
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import xarray as xr

from frameit.check.check_functions import drop_time_dupes
from frameit.core.configuration import field_selection
from frameit.io.loader import managed_loading, resolve_input_files
from frameit.processing.derived.wind import normalize_winds
from frameit.processing.polar.metadata import preserve_coordinate_dependencies
from frameit.processing.wind_reference import wind_pairs

logger = logging.getLogger(__name__)
logging.getLogger("cfgrib").setLevel(logging.WARNING)

GRIB_PRESSURE_UNITS = {"isobaricInhPa": "hPa", "isobaricInPa": "Pa"}


def normalize_isobaric_coordinates(ds):
    """Keep producer pressure units while removing them from FrameIt axis names."""
    renames = {name: "isobaric" for name in GRIB_PRESSURE_UNITS if name in ds}
    if not renames:
        return ds
    if len(renames) > 1 or "isobaric" in ds:
        raise ValueError("Competing pressure coordinates cannot share the isobaric axis")
    result = ds.rename(renames)
    pattern = re.compile(r"\b(" + "|".join(renames) + r")\b")
    for name in result.variables:
        for mapping in ("attrs", "encoding"):
            metadata = dict(getattr(result[name], mapping))
            for key in ("coordinates", "bounds", "cell_methods", "formula_terms",
                        "cell_measures", "ancillary_variables"):
                if isinstance(metadata.get(key), str):
                    metadata[key] = pattern.sub(lambda match: renames[match[0]], metadata[key])
            setattr(result[name], mapping, metadata)
    return result


@contextmanager
def _grib_message(locator):
    """Own and release one exact message in this scope, without scanning a stream."""
    import eccodes as ec
    from cfgrib.xarray_plugin import ECCODES_LOCK

    with ECCODES_LOCK:
        with Path(locator["path"]).open("rb") as stream:
            stream.seek(locator["offset"])
            raw = stream.read(locator["length"])
        if len(raw) != locator["length"] or raw[:4] != b"GRIB" or raw[-4:] != b"7777":
            raise ValueError(
                f"{locator['path']}: invalid selected GRIB message {locator['message_index']}")
        handle = ec.codes_new_from_message(raw)
        try:
            if ec.codes_get_message_size(handle) != locator["length"]:
                raise ValueError(f"{locator['path']}: selected GRIB message length changed")
            yield handle
        finally:
            ec.codes_release(handle)


def _grib_header(handle):
    """Retain selected-message identity for the later lazy read."""
    from datetime import datetime

    import eccodes as ec

    keys = (
        "shortName", "units", "paramId", "typeOfLevel", "level", "md5GridSection",
        "uvRelativeToGrid", "number", "stepType", "startStep", "endStep", "stepUnits",
        "typeOfStatisticalProcessing", "perturbationNumber", "typeOfEnsembleForecast",
        "numberOfForecastsInEnsemble",
    )
    header = {key: ec.codes_get(handle, key) if ec.codes_is_defined(handle, key) else None
              for key in keys}
    header["cycle"] = np.datetime64(datetime(*(
        int(ec.codes_get(handle, key)) for key in (
            "year", "month", "day", "hour", "minute", "second"))), "ns")
    return header


def _grib_payload(locator, shape, header):
    """Decode only this message; its scan order also owns the inventoried geography."""
    import eccodes as ec

    with _grib_message(locator) as handle:
        if _grib_header(handle) != header:
            raise ValueError(f"{locator['path']}: selected GRIB message changed after binding")
        values = ec.codes_get_values(handle)
        if ec.codes_get(handle, "bitmapPresent"):
            values = np.where(ec.codes_get_array(handle, "bitmap"), values, np.nan)
        elif ec.codes_get(handle, "numberOfMissing"):
            values = np.where(values == ec.codes_get(handle, "missingValue"), np.nan, values)
        if ec.codes_get(handle, "jPointsAreConsecutive"):
            return values.reshape(shape[::-1]).T
        return values.reshape(shape)


def _selected_grib(files, binding, source, resources):
    """Build native lazy arrays from closed bindings, separately for each read role."""
    import dask.array as da
    from dask import delayed

    if binding.get("status") != "bound" or source is None:
        raise ValueError("GRIB selected_records requires bound requests and owning source metadata")
    from frameit.processing.polar.contracts import require_executable_products

    require_executable_products(binding, source)
    admitted = {Path(path).resolve() for path in files}

    def locator_key(locator):
        return (locator["path"], locator["message_index"], locator["offset"], locator["length"])

    pool = {locator_key(record["locator"]): record for record in source["record_inventory"]}
    originals = {}

    def message(record, field, grid):
        locator = record["locator"]
        key = locator_key(locator)
        if key not in originals:
            with _grib_message(locator) as handle:
                header = _grib_header(handle)
                expected = {
                    key.removeprefix("GRIB_"): value for key, value in {
                        **field["attributes"], **record["temporal_metadata"]}.items()}
                expected.update(
                    cycle=record["cycle"], level=record["level"],
                    number=record.get("native_axes", {}).get("number"),
                    md5GridSection=grid["grib_grid_section"],
                    **record.get("ensemble_metadata", {}),
                )
                if any(header.get(key) != value for key, value in expected.items()):
                    raise ValueError(
                        f"{locator['path']}: selected GRIB header changed after inventory")
                attrs = dict(field["attributes"],
                             source_variable_name=header["shortName"])
            shape = tuple(grid["dimensions"][dim] for dim in ("y", "x"))
            data = da.from_delayed(
                delayed(_grib_payload)(locator, shape, header),
                shape=shape, dtype=np.float64,
            )
            # No native/file handle survives either metadata inspection or a payload
            # task. The registry still owns the original lazy dataset and rollback.
            originals[key] = resources.add(xr.Dataset({
                record["name"]: (("y", "x"), data, attrs)}))
        return originals[key][record["name"]]

    def groups(descriptors, *, internal=False):
        by_grid, vertical_dims = {}, set()
        for name, descriptor in descriptors.items():
            if descriptor.get("operation"):
                continue
            native_name, native_group, _ = field_selection(source.get("requests", {}), name)
            records_by_grid = {}
            for record in descriptor["records"]:
                locator = record["locator"]
                if locator["format"] != "grib" or Path(locator["path"]).resolve() not in admitted:
                    raise ValueError(f"{name}: selected locator is outside the admitted GRIB files")
                native = pool.get(locator_key(locator))
                if (native is None or descriptor["field_id"] != record["field_id"]
                        or any(record.get(key) != value for key, value in native.items())
                        or record["field_id"] not in source["fields"]
                        or native_name != record["name"]
                        or native_group is not None and native_group != source["fields"][
                            record["field_id"]]["group"]
                        or source["fields"][descriptor["field_id"]]["name"] != record["name"]):
                    raise ValueError(
                        f"{name}: selected GRIB record is outside the closed inventory")
                if record["selection_grid_id"] != record["grid_id"]:
                    raise ValueError(f"{name}: destination-grid transformation is not executable")
                if set(record.get("native_axes", {})) - {"number"}:
                    raise ValueError(f"{name}: unsupported GRIB native axes")
                records_by_grid.setdefault(record["grid_id"], []).append(record)
            for grid_id, records in records_by_grid.items():
                field = source["fields"][descriptor["field_id"]]
                grid = source["native_grids"][grid_id]
                vertical = records[0]["vertical"]
                if len({tuple(r.get("native_axes", {})) for r in records}) != 1:
                    raise ValueError(f"{name}: mixed native GRIB member axes are not executable")
                if vertical is None and len({r["level"] for r in records}) != 1:
                    raise ValueError(f"{name}: ambiguous native GRIB surface levels")
                if any(r["source_positions"] != records[0]["source_positions"] for r in records):
                    raise ValueError(
                        f"{name}: changing native GRIB read stencils are not executable")
                native_levels = sorted(
                    {r["level"] for r in pool.values() if r["field_id"] == descriptor["field_id"]},
                    reverse=field["group"] == "isobaric",
                )
                levels = ([native_levels[i] for i in records[0]["source_positions"]]
                          if vertical is not None else [records[0]["level"]])
                samples, references = {}, {}
                members = sorted({r["native_axes"]["number"] for r in records
                                  if "number" in r.get("native_axes", {})})
                for record in records:
                    stamp, cycle = record["time"], record["cycle"]
                    if stamp in references and references[stamp] != cycle:
                        raise ValueError(
                            f"{name}: multiple GRIB cycles at one time require selection")
                    references[stamp] = cycle
                    member = record.get("native_axes", {}).get("number")
                    key = stamp, member, record["level"]
                    if key in samples:
                        raise ValueError(f"{name}: competing selected GRIB message providers")
                    samples[key] = message(record, field, grid)
                times = sorted(references)

                time_arrays = []
                for stamp in times:
                    member_arrays = []
                    for member in members or [None]:
                        missing = [level for level in levels
                                   if (stamp, member, level) not in samples]
                        if missing:
                            raise ValueError(
                                f"{name}: missing bound GRIB levels {missing} at {stamp}")
                        arrays = [samples[stamp, member, level].data for level in levels]
                        member_arrays.append(
                            da.stack(arrays) if vertical is not None else arrays[0])
                    time_arrays.append(da.stack(member_arrays) if members else member_arrays[0])
                data = da.stack(time_arrays)
                dims = ["time"] + (["number"] if members else [])
                coords = {coordinate: xr.Variable(
                    metadata["dimensions"], metadata["values"], metadata["attributes"])
                    for coordinate, metadata in grid["coordinates"].items()}
                if vertical is not None:
                    vertical_dims.add(vertical["dimension"])
                    dims.append(vertical["dimension"])
                    coords.update({coordinate: xr.Variable(
                        metadata["dimensions"], metadata["values"], metadata["attributes"])
                        for coordinate, metadata in vertical["coordinates"].items()})
                    coords[f"{vertical['dimension']}_source_native_index"] = (
                        vertical["dimension"], vertical["source_native_indices"], {"units": "1"})
                else:
                    coords[field["group"]] = records[0]["level"]
                dims.extend(("y", "x"))
                coords["time"] = ("time", times, {"standard_name": "time"})
                cycles = [references[stamp] for stamp in times]
                coords["forecast_reference_time"] = (
                    "time", cycles, {"standard_name": "forecast_reference_time"})
                coords["step"] = ("time", np.asarray(times) - np.asarray(cycles),
                                  {"standard_name": "forecast_period"})
                temporal = {}
                for record in records:
                    stamp = record["time"]
                    if stamp in temporal and temporal[stamp] != record["temporal_metadata"]:
                        raise ValueError(f"{name}: inconsistent selected GRIB temporal intervals")
                    temporal[stamp] = record["temporal_metadata"]
                for key in records[0]["temporal_metadata"]:
                    coords[key] = ("time", [temporal[stamp][key] for stamp in times])
                if members:
                    ensemble = records[0].get("ensemble_metadata", {})
                    attrs = {"standard_name": "realization", "units": "1"}
                    counts = {r.get("ensemble_metadata", {}).get("numberOfForecastsInEnsemble")
                              for r in records}
                    if "numberOfForecastsInEnsemble" in ensemble and len(counts) == 1:
                        attrs["GRIB_numberOfForecastsInEnsemble"] = ensemble[
                            "numberOfForecastsInEnsemble"]
                    coords["number"] = ("number", members, attrs)
                    by_member = {}
                    for record in records:
                        member = record["native_axes"]["number"]
                        metadata = record.get("ensemble_metadata", {})
                        if member in by_member and by_member[member] != metadata:
                            raise ValueError(f"{name}: changing GRIB ensemble metadata")
                        by_member[member] = metadata
                    for key in ensemble:
                        coords["GRIB_" + key] = (
                            "number", [by_member[member][key] for member in members])
                bounds = {}
                for record in records:
                    stamp = record["time"]
                    if stamp in bounds and bounds[stamp] != record["time_bounds"]:
                        raise ValueError(f"{name}: inconsistent selected GRIB time intervals")
                    bounds[stamp] = record["time_bounds"]
                bounds = {stamp: values for stamp, values in bounds.items() if values is not None}
                if bounds:
                    if set(bounds) != set(times):
                        raise ValueError(f"{name}: inconsistent selected GRIB time intervals")
                    coords["time_bounds"] = (("time", "nv"), [bounds[stamp] for stamp in times])
                    coords["time"][2]["bounds"] = "time_bounds"
                attrs = dict(next(iter(samples.values())).attrs)
                if metadata := descriptor.get("field_metadata"):
                    attrs.update(metadata["attributes"])
                    attrs["frameit_metadata_origins"] = json.dumps(
                        metadata["origins"], sort_keys=True)
                dataset = xr.Dataset({name: (dims, data, attrs)}, coords=coords)
                dataset.time.encoding["calendar"] = records[0]["calendar"]
                dataset.forecast_reference_time.encoding["calendar"] = records[0]["calendar"]
                if not internal:
                    from frameit.processing.requests import align_initial_gap

                    dataset = align_initial_gap(dataset, name, source)
                # A scalar surface height must not align onto another field's height axis.
                key = ((grid_id, name) if internal and (vertical is None or any(
                    gap["field"] == name for gap in source.get("allowed_gaps", []))) else grid_id)
                by_grid.setdefault(key, []).append(dataset)
        from frameit.tracking.tracker_core import merge_internal_stencils

        return {grid_id: (merge_internal_stencils(
                         datasets, vertical_dims.intersection(datasets[0].dims)) if internal else
                         xr.merge(datasets, join="exact", compat="identical",
                                  combine_attrs="override"))
                for grid_id, datasets in by_grid.items()}

    return (
        groups(binding["products"].get("model_grid", {})),
        {"internal": groups(binding["dependencies"], internal=True)}
        if binding["dependencies"] else {},
    )


def _parse_and_normalize(yaml_req: dict | None, dims_seen: set[str]) -> dict[str, dict]:
    """
    Normalise the YAML into:
      group_name -> {
        "dimension": str | None,
        "variables": list[str],
        "all_levels": bool,
        "levels": list[float|int],
        "level_indices": list[int],
      }
    - 'dimension' is taken from the YAML if provided, otherwise inferred when
      the group name matches a known coordinate.
    - If no dimension is found, the group is treated as surface-like.
    """
    if not yaml_req:
        return {}
    out: dict[str, dict] = {}
    for group, spec in yaml_req.items():
        spec = spec or {}
        dim = spec.get("dimension", None)
        # "surface" is a logical group spanning GRIB surface/meanSea/10-m
        # blocks, not the scalar "surface" coordinate on some messages.
        if dim is None and group != "surface" and group in dims_seen:
            dim = group
        from frameit.processing.requests import normalize_requests

        normalized = normalize_requests({group: spec})[group]
        out[group] = {
            "dimension": dim,
            "variables": list(spec.get("variables", [])),
            # GRIB pressure/height axes have no native halo levels.
            "all_levels": normalized["all_levels"],
            "levels": normalized["levels"],
            "level_indices": normalized["level_indices"],
        }
    return out


def _match_levels(avail_vals, requested, tol: float) -> list[float]:
    if not requested:
        return []
    vals = np.asarray(avail_vals, dtype=float)
    out = []
    for lv in requested:
        lvf = float(lv)
        j = int(np.argmin(np.abs(vals - lvf)))
        if abs(float(vals[j]) - lvf) <= tol:
            out.append(float(vals[j]))
    seen = set()
    uniq = []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def _collect_parts_for_req(
    dsets: list[xr.Dataset],
    req_map: dict[str, dict],
    float_tol: float,
    tag: str,  # "user variables dict" | "tracker variables dict"
    *,
    select_levels: bool = True,
) -> dict[str, list[xr.Dataset]]:
    """
    Filter GRIB dataset blocks for a single request map.

    Parameters
    ----------
    dsets : list[xr.Dataset]
        All xarray Datasets opened from one GRIB file (one per message type).
    req_map : dict[str, dict]
        Normalized request map ``{group: spec}`` as returned by
        :func:`_parse_and_normalize`.
    float_tol : float
        Tolerance for numeric vertical level matching.
    tag : str
        Label used in log messages (e.g. "user variables dict" or
        "tracker variables dict:<method>").

    Returns
    -------
    dict[str, list[xr.Dataset]]
        ``{group: [filtered datasets]}`` — one list per group, with one
        entry per matching GRIB block.
    """
    file_parts: dict[str, list[xr.Dataset]] = {}

    for ds in dsets:
        for g, req in req_map.items():
            dim = req.get("dimension")
            if dim and dim not in ds.dims and dim not in ds.coords:
                continue
            keep = [v for v in req.get("variables", []) if v in ds.data_vars]
            if not keep:
                continue
            # Expanding an unchunked backend can materialize its variables.
            # Restrict first: unrelated atmospheric fields are not dependencies
            # of a small coupled-source extraction.
            sel = preserve_coordinate_dependencies(ds, ds[keep])
            if dim and dim not in sel.dims:
                if sel[dim].ndim != 0:
                    continue
                sel = sel.expand_dims(dim)
            if "valid_time" in sel.coords:
                valid_dims = sel["valid_time"].dims
                if len(valid_dims) > 1:
                    raise ValueError("GRIB inputs with multiple forecast initializations and "
                                     "lead-time axes require an explicit single-cycle selection")
                sel = sel.assign_coords(time=sel["valid_time"])
                if valid_dims and valid_dims != ("time",):
                    sel = sel.swap_dims({valid_dims[0]: "time"})

            # Vertical selection
            if select_levels and dim and dim in sel.dims and not req.get("all_levels", False):
                if req.get("level_indices"):
                    idx_list = [int(i) for i in req["level_indices"]]
                    n = int(sel.sizes[dim])
                    valid_idx = [i for i in idx_list if -n <= i < n]
                    if not valid_idx:
                        continue
                    sel = sel.isel({dim: valid_idx})
                elif req.get("levels"):
                    matched = _match_levels(sel[dim].values, req["levels"], tol=float_tol)
                    if not matched:
                        continue
                    sel = sel.sel({dim: matched})

            # Variables
            keep = [v for v in req.get("variables", []) if v in sel.data_vars]
            if keep:
                file_parts.setdefault(g, []).append(
                    preserve_coordinate_dependencies(sel, sel[keep]))

    return file_parts


def _select_group_levels(ds, req, float_tol):
    """Select only after the file's components have been merged and prepared."""
    dim = req.get("dimension")
    if not dim or req.get("all_levels", False):
        return ds
    if req.get("level_indices"):
        n = ds.sizes[dim]
        indices = [int(i) for i in req["level_indices"] if -n <= int(i) < n]
        return ds.isel({dim: indices}) if indices else None
    if req.get("levels"):
        levels = _match_levels(ds[dim].values, req["levels"], tol=float_tol)
        return ds.sel({dim: levels}) if levels else None
    return ds


def _retain_wind_geometry(ds, dsets, conf, group):
    """Retain declared rotation inputs even when cfgrib puts them in another block."""
    if conf is None:
        return ds
    names = {conf.name_latitude, conf.name_longitude}
    for pair in wind_pairs(conf, group):
        rotation = pair.get("rotation") or {}
        if rotation.get("coordinate"):
            names.add(rotation["coordinate"])
        if rotation.get("method") == "mesonh_projection":
            names.update(("BETA", "RPK", "LON0", "CARTESIAN"))
    # The explicit scalar compatibility path names grid_rotation.
    if getattr(conf, "wind_reference_frame", None) == "grid":
        names.add("grid_rotation")
    for source in dsets:
        for name in names:
            if name not in ds and name in source:
                ds = ds.assign_coords({name: source[name]})
            elif name not in ds and name not in ds.attrs and name in source.attrs:
                ds = ds.assign_attrs({name: source.attrs[name]})
    return ds


@managed_loading
def concat_grib2ds_by_vert_coord(
    files,
    user_requested_variables_yaml: dict,
    tracker_requested_variables_by_method_yaml: dict,
    method: str | None = None,
    index_dir: str | Path = "cache",
    float_tol: float = 0.51,
    warn: bool = True,
    *,
    strict: bool = False,
    resources=None,
    duplicate_time_policy="first",
    wind_conf=None,
    native_output_groups: dict[str, xr.Dataset] | None = None,
    filter_requested: bool = False,
    selected_records=None,
    source_plan=None,
) -> tuple[dict[str, xr.Dataset], dict[str, dict[str, xr.Dataset]]]:
    """
    Open a list of GRIB files and build per-group user and tracker Datasets.

    Files are opened once with cfgrib; datasets are then filtered, merged, and
    concatenated along the time axis.

    Parameters
    ----------
    files : list[str or Path]
        Ordered list of GRIB files (one per time step or a time sequence).
    user_requested_variables_yaml : dict
        YAML-like request block for user variables, ``{group: spec}``.
    tracker_requested_variables_by_method_yaml : dict
        YAML-like request block for tracker variables,
        ``{method: {group: spec}}``.
    method : str or None, optional
        Restrict tracker loading to this method only.  ``None`` loads all
        methods present in the tracker YAML.
    index_dir : str or Path, optional
        Directory for cfgrib index files. Created if absent. Default "cache".
    float_tol : float, optional
        Tolerance for numeric vertical level matching. Default 0.51.
    warn : bool, optional
        Emit a warning when the requested tracking method is absent from the
        tracker YAML. Default True.
    wind_conf : optional
        Explicit wind declarations. Normalize each file's merged group to
        Earth-relative m/s before vertical selection and time concatenation.
        None preserves the historical unprepared loader API.
    native_output_groups : mutable dict, optional
        When supplied with wind_conf, populate user groups from the same source
        pieces with m/s units but original names, locations and source vector
        basis. Uses the same vertical/time selection, without derived speed.
    selected_records, source_plan : optional
        Complete executable v3 binding and its inventoried owning source. Decode
        exact selected message locators lazily, without legacy normalization or
        dependency discovery. Return native grid IDs and separate internal groups.

    Returns
    -------
    by_group_user : dict[str, xr.Dataset]
        ``{group -> xr.Dataset}`` for user-requested variables.
    by_group_trk : dict[str, dict[str, xr.Dataset]]
        ``{method -> {group -> xr.Dataset}}`` for tracker-requested variables.
    """

    if selected_records is not None:
        return _selected_grib(files, selected_records, source_plan, resources)

    # Keep optional ecCodes initialization after core geometry imports: some
    # wheels globally preload a conflicting PROJ before pyproj is initialized.
    import cfgrib

    files = resolve_input_files(files, strict=strict)
    idx_dir = Path(index_dir)
    idx_dir.mkdir(parents=True, exist_ok=True)

    # 1) Open files and inventory coordinates
    opened_per_file: dict[Path, list[xr.Dataset]] = {}
    dims_seen: set[str] = set()
    for f in files:
        source_id = hashlib.sha256(str(f.resolve()).encode()).hexdigest()[:16]
        backend_kwargs = {
            "read_keys": ["uvRelativeToGrid"],
            "indexpath": str(idx_dir / (f.name + f".{source_id}.{{short_hash}}.idx")),
        }
        selectors = None
        if filter_requested:
            import eccodes as ec

            blocks = [user_requested_variables_yaml]
            tracker_blocks = tracker_requested_variables_by_method_yaml or {}
            blocks.extend(block for key, block in tracker_blocks.items()
                          if method is None or key == method)
            wanted = {name for block in blocks for spec in block.values()
                      for name in spec.get("variables", []) if name != "wind_speed"}
            if wind_conf is not None:
                if wind_conf.wind_reference_frame == "grid":
                    wanted.add("grid_rotation")
                for pair in wind_conf.wind_pairs:
                    if wanted.intersection((pair["u"], pair["v"])):
                        rotation = pair.get("rotation") or {}
                        if rotation.get("coordinate"):
                            wanted.add(rotation["coordinate"])
            if wanted:
                selectors = set()
                with Path(f).open("rb") as stream:
                    while True:
                        handle = ec.codes_grib_new_from_file(stream, headers_only=True)
                        if handle is None:
                            break
                        try:
                            short = str(ec.codes_get(handle, "shortName"))
                            try:
                                canonical = str(ec.codes_get(handle, "cfVarName"))
                            except ec.CodesInternalError:
                                canonical = short
                            aliases = {"msl": "prmsl", "10u": "u10", "10v": "v10"}
                            if short not in {"unknown", "undef", ""} and wanted.intersection(
                                {short, canonical, aliases.get(short, short)}
                            ):
                                selectors.add(short)
                        finally:
                            ec.codes_release(handle)
            else:
                # Coordinate-only coupled requests need no arbitrary data field.
                from frameit.core.preflight import _grib_metadata

                metadata = _grib_metadata(f)[0]
                lat, lon = metadata.latitude.values, metadata.longitude.values
                if not (np.allclose(lat, lat[:, :1], rtol=0, atol=1.e-12)
                        and np.allclose(lon, lon[:1, :], rtol=0, atol=1.e-12)):
                    raise ValueError("Coordinate-only coupled GRIB requires a regular lon/lat grid")
                dsets = [xr.Dataset(coords={
                    "latitude": ("latitude", lat[:, 0], {"units": "degrees_north"}),
                    "longitude": ("longitude", lon[0], {"units": "degrees_east"}),
                    "valid_time": metadata.valid_time.variable,
                })]
                selectors = set()
        if selectors is None:
            dsets = cfgrib.open_datasets(str(f), backend_kwargs=backend_kwargs)
        elif wanted:
            dsets = []
            for short in sorted(selectors):
                dsets.extend(cfgrib.open_datasets(str(f), backend_kwargs={
                    **backend_kwargs, "filter_by_keys": {"shortName": short}}))
        for ds in dsets:
            resources.add(ds)
        dsets = [normalize_isobaric_coordinates(ds) for ds in dsets]
        # Match the canonical aliases already used by metadata preflight, while
        # retaining original variables for callers that request native names.
        aliases = {"msl": "prmsl", "10u": "u10", "10v": "v10"}
        dsets = [ds.assign({new: ds[old].assign_attrs(source_variable_name=old)
                            for old, new in aliases.items() if old in ds and new not in ds})
                 for ds in dsets]
        opened_per_file[f] = dsets
        for ds in dsets:
            dims_seen.update(ds.sizes.keys())
            dims_seen.update(ds.coords)

    # 2) Normalisation YAML
    user_req = _parse_and_normalize(user_requested_variables_yaml, dims_seen)

    tracker_yaml = tracker_requested_variables_by_method_yaml or {}
    if method is None:
        methods = list(tracker_yaml.keys())
    else:
        methods = [m for m in tracker_yaml.keys() if m == method]
        if not methods and warn:
            logger.warning(
                "Tracker method '%s' not found; no tracker block will be produced.", method
            )
    tracker_req_by_method: dict[str, dict[str, dict]] = {
        m: _parse_and_normalize(tracker_yaml.get(m, {}), dims_seen) for m in methods
    }

    # 3) Union pour inventaire global
    all_groups: dict[str, dict] = dict(user_req)
    for _m, blk in tracker_req_by_method.items():
        for k, v in blk.items():
            if k not in all_groups:
                all_groups[k] = v

    global_levels: dict[str, set] = {g: set() for g, s in all_groups.items() if s.get("dimension")}
    global_depth: dict[str, int] = {g: 0 for g, s in all_groups.items() if s.get("dimension")}

    for _, dsets in opened_per_file.items():
        for ds in dsets:
            for g, spec in all_groups.items():
                dim = spec.get("dimension")
                if dim and dim in ds.coords:
                    global_depth[g] = max(global_depth[g], int(ds[dim].size))
                    try:
                        vals = np.asarray(ds[dim].values, dtype=float).ravel().tolist()
                    except Exception:
                        vals = [float(v) for v in ds[dim].values]
                    global_levels[g].update(vals)

    # 4) Collect per-file pieces into lists.
    # Memory fix: accumulate datasets per file in lists, then do a single
    # xr.concat at the end — avoids O(N²) intermediate copies.
    # Before: xr.concat([accumulated, ds_file], dim="time") at each iteration
    # After: list accumulation + single final concat
    parts_user_all: dict[str, list[xr.Dataset]] = {}
    parts_native_all: dict[str, list[xr.Dataset]] = {}
    parts_trk_all: dict[str, dict[str, list[xr.Dataset]]] = {m: {} for m in methods}

    from frameit.io.netcdf_utils import validate_native_metadata

    for _f, dsets in opened_per_file.items():
        parts_user = _collect_parts_for_req(
            dsets, user_req, float_tol, tag="user variables dict", select_levels=False
        )
        parts_trk_by_m: dict[str, dict[str, list[xr.Dataset]]] = {
            m: _collect_parts_for_req(
                dsets, tracker_req_by_method[m], float_tol, tag=f"tracker variables dict:{m}",
                select_levels=False,
            )
            for m in methods
        }

        for g, parts in parts_user.items():
            validate_native_metadata(parts, model="GRIB")
            ds_file = xr.merge(
                parts, compat="override", join="outer", combine_attrs="drop_conflicts"
            )
            ds_file = _retain_wind_geometry(ds_file, dsets, wind_conf, g)
            if wind_conf is not None:
                if native_output_groups is not None:
                    native = _select_group_levels(ds_file, user_req[g], float_tol)
                    if native is not None:
                        parts_native_all.setdefault(g, []).append(native)
                if (getattr(wind_conf, "cartesian_horizontal_winds", "native") != "native"
                        or "wind_speed" in user_req[g]["variables"]):
                    ds_file = normalize_winds(ds_file, wind_conf, g)
            ds_file = _select_group_levels(ds_file, user_req[g], float_tol)
            if ds_file is not None:
                parts_user_all.setdefault(g, []).append(ds_file)

        for m, parts_trk in parts_trk_by_m.items():
            for g, parts in parts_trk.items():
                validate_native_metadata(parts, model="GRIB")
                ds_file = xr.merge(
                    parts, compat="override", join="outer", combine_attrs="drop_conflicts"
                )
                ds_file = _retain_wind_geometry(ds_file, dsets, wind_conf, g)
                if wind_conf is not None:
                    ds_file = normalize_winds(ds_file, wind_conf, g)
                ds_file = _select_group_levels(ds_file, tracker_req_by_method[m][g], float_tol)
                if ds_file is not None:
                    parts_trk_all[m].setdefault(g, []).append(ds_file)

    if wind_conf is None or getattr(wind_conf, "cartesian_horizontal_winds", "native") == "native":
        for parts in parts_user_all.values():
            validate_native_metadata(parts, model="GRIB")
    for parts in parts_native_all.values():
        validate_native_metadata(parts, model="GRIB")
    for groups in parts_trk_all.values():
        for parts in groups.values():
            validate_native_metadata(parts, model="GRIB")
    # Concat unique en fin de boucle — une seule allocation par groupe
    by_group_user: dict[str, xr.Dataset] = {
        g: xr.concat(
            parts,
            dim="time",
            # compat="equals",
            compat="no_conflicts",
            data_vars="all",
            coords="different",
            join="outer",
            combine_attrs="override",
        ).sortby("time")
        for g, parts in parts_user_all.items()
    }
    by_group_trk: dict[str, dict[str, xr.Dataset]] = {
        m: {
            g: xr.concat(
                parts,
                dim="time",
                # compat="equals",
                compat="no_conflicts",
                data_vars="all",
                coords="different",
                join="outer",
                combine_attrs="override",
            ).sortby("time")
            for g, parts in grp.items()
        }
        for m, grp in parts_trk_all.items()
    }

    # 5) Post-processing: geometric trackers.
    # Bug fix: this block was previously inside the per-file loop, so it ran once
    # per file. Moved here, after the loop, so it runs only once.
    geo_methods = {"fixed_box", "prescribed_track"}

    if by_group_user:
        g_user_ref, ds_user_ref = next(iter(by_group_user.items()))

        data_vars = list(ds_user_ref.data_vars)
        if data_vars:
            ds_geo = ds_user_ref.drop_vars(data_vars)
        else:
            ds_geo = ds_user_ref

        for m in methods:
            if m in geo_methods:
                if m not in by_group_trk:
                    by_group_trk[m] = {}
                by_group_trk[m]["surface"] = ds_geo
    else:
        # Coordinate-only runs must not depend on an arbitrary user field.
        geometry_parts = []
        for dsets in opened_per_file.values():
            reference = next((ds for ds in dsets if all(
                name in ds.coords for name in ("latitude", "longitude", "valid_time")
            )), None)
            if reference is not None:
                geometry_parts.append(xr.Dataset(coords={
                    "time": np.atleast_1d(reference.valid_time.values),
                    "latitude": reference.latitude.reset_coords(drop=True),
                    "longitude": reference.longitude.reset_coords(drop=True),
                }))
        if geometry_parts:
            ds_geo = xr.concat(geometry_parts, dim="time").sortby("time")
            for m in methods:
                if m in geo_methods:
                    by_group_trk.setdefault(m, {})["surface"] = ds_geo

    # 6) Final deduplication
    by_group_user = {
        g: drop_time_dupes(ds, keep=duplicate_time_policy) for g, ds in by_group_user.items()
    }
    by_group_trk = {
        m: {g: drop_time_dupes(ds, keep=duplicate_time_policy) for g, ds in grp.items()}
        for m, grp in by_group_trk.items()
    }
    if native_output_groups is not None and wind_conf is not None:
        native_output_groups.update({
            g: drop_time_dupes(xr.concat(
                parts, dim="time", compat="no_conflicts", data_vars="all", coords="different",
                join="outer", combine_attrs="override",
            ).sortby("time"), keep=duplicate_time_policy)
            for g, parts in parts_native_all.items()
        })
    return by_group_user, by_group_trk
