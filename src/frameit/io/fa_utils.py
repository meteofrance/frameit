"""Selected, lazy FA fields on FrameIt's normal grouped dataset interface."""

from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import dask.array as da
import numpy as np
import xarray as xr

from frameit.check.check_functions import drop_time_dupes
from frameit.io.fa_backend import inspect_fa, request_fa
from frameit.io.fa_contracts import resolve_descriptor, validate_descriptor
from frameit.io.fa_cubes import (
    HYBRID_AUXILIARIES,
    add_cube_coordinates,
    cube_layouts,
    record_selection,
    validate_cube_requests,
    vertical_signature,
)
from frameit.io.fa_geometry import fa_geometry, geometry_signature
from frameit.io.loader import managed_loading, resolve_input_files
from frameit.processing.requests import build_group_ds, normalize_requests

log = logging.getLogger(__name__)


def fa_field_names(requests):
    return list(dict.fromkeys(name for spec in requests.values()
                              for name in spec.get("variables", []) if name != "wind_speed"))


def inspect_fa_inputs(path, conf, fields):
    """Read metadata in a clean native process and validate selected meaning."""
    options = conf.fa_options
    records, owners = record_selection(options, fields)
    info = inspect_fa(path, options["profile"], records, timeout_seconds=options["timeout_seconds"],
                      expected_source=options["expected_source"], backend=options["backend"],
                      python_executable=options["python_executable"],
                      earth_radius_m=options["earth_radius_m"],
                      geometry_options={key: options[key] for key in (
                          "subdomain", "earth_radius_m", "max_points")})
    for name in fields:
        metadata = options["field_metadata"].get(name)
        if metadata is None:
            raise ValueError(f"{path}: declare input.fa.field_metadata.{name} "
                             "(units, kind, temporal_kind); native identity is not inferred")
        polar_names = {value for spec in conf.polar_variables.values()
                       for value in spec.get("variables", [])}
        if (name in polar_names and metadata["kind"] == "categorical" and conf.compute_polar_proj
                and conf.polar_interpolation_method != "nearest_s2d"):
            raise ValueError(f"{name}: categorical FA fields require explicit nearest_s2d sampling")
    info["field_definitions"] = {name: dict(options["field_metadata"][name]) for name in fields}
    info["field_descriptors"] = {
        record: resolve_descriptor(info["field_descriptors"][record],
                                   info["field_definitions"][owners[record]])
        for record in records}
    info["native_cubes"] = cube_layouts(info, options, fields)
    if info["native_cubes"]:
        validate_cube_requests(info, normalize_requests(conf.requests_user()), conf)
    return info


def fa_metadata_dataset(info, options, geometry=None):
    """Label geometry/field shapes with lazy NaNs, without physical payload reads."""
    ds = (fa_geometry(info["geometry"], options) if geometry is None else geometry).copy(deep=False)
    stamp = np.datetime64(info["valid_time"], "ns")
    ds = ds.assign_coords(time=("time", [stamp]),
                          forecast_reference_time=np.datetime64(info["reference_time"], "ns"),
                           forecast_period=("time", [np.timedelta64(info["lead_seconds"], "s")]))
    ds = add_cube_coordinates(ds, info)
    for name, definition in info.get("field_definitions", {}).items():
        layout = info.get("native_cubes", {}).get(name)
        record = layout["records"][0] if layout else name
        shape = (ds.sizes["y"], ds.sizes["x"])
        ds[name] = xr.DataArray(da.full(shape, np.nan, chunks=shape), dims=("y", "x"),
                               attrs={**definition, "source_variable_name": name,
                                      "grid_mapping": "crs",
                                      "fa_field_descriptor_scope": (
                                          "representative input record; per-file descriptors "
                                          "and decode observations in run provenance"),
                                      "fa_field_descriptor": json.dumps(
                                          info["field_descriptors"][record], sort_keys=True)})
        if layout:
            attrs = dict(ds[name].attrs,
                         ancillary_variables=" ".join((*HYBRID_AUXILIARIES,
                                                        f"{name}_native_record")),
                         fa_vertical_position=layout["vertical_position"],
                         fa_sampling_origin="explicit input.fa.native_cubes",
                         fa_physical_coordinates="not computed")
            if layout.get("vector_basis"):
                attrs.update(wind_reference_frame=layout["vector_basis"],
                             fa_component_scaling=layout.get("component_scaling"))
            shape = (len(layout["levels"]), ds.sizes["y"], ds.sizes["x"])
            ds[name] = xr.DataArray(da.full(shape, np.nan, chunks=(1, *shape[1:])),
                                    dims=(layout["group"], "y", "x"), attrs=attrs)
    ds.attrs.update(_frameit_vertical_group="surface", source_format="fa",
                    fa_profile=options["profile"], fa_identifier=info["identifier"])
    if info.get("native_cubes"):
        ds.attrs.pop("_frameit_vertical_group")
    if info["surfex_metadata"]:
        ds.attrs.update(surfex_program=info["surfex_metadata"]["PROGRAM"],
                        surfex_version=info["surfex_metadata"]["VERSION"],
                        surfex_bug=info["surfex_metadata"]["BUG"])
    return ds


class FaArray:
    """Serializable array descriptor; no native handles/locks cross processes."""

    dtype = np.dtype("float64")
    ndim = 2

    def __init__(self, path, field, info, options, zone, diagnostics_path=None):
        self.path, self.field = str(path), field
        self.identity, self.options = list(info["identity"]), deepcopy(options)
        self.zone = list(zone)
        self.diagnostics_path = diagnostics_path
        self.descriptor = deepcopy(info["field_descriptors"][field])
        validate_descriptor(self.descriptor)
        self.shape = zone[3] - zone[2], zone[1] - zone[0]

    def __getitem__(self, key):
        key = key if isinstance(key, tuple) else (key,)
        key = key + (slice(None),) * (2 - len(key))
        encoded = []
        for value, _size in zip(key, self.shape, strict=True):
            if isinstance(value, slice):
                # Preserve Python's negative-stop semantics for reversed slices.
                encoded.append([value.start, value.stop, value.step])
            else:
                encoded.append(int(value))
        if any(isinstance(v, slice) and len(range(*v.indices(n))) == 0
               for v, n in zip(key, self.shape, strict=True)):
            shape = tuple(len(range(*v.indices(n))) for v, n in zip(key, self.shape, strict=True)
                          if isinstance(v, slice))
            return np.empty(shape, dtype=self.dtype)
        result = request_fa({
            "operation": "read", "path": self.path, "identity": self.identity,
            "profile": self.options["profile"], "fields": [self.field],
            "backend": self.options["backend"],
            "python_executable": self.options["python_executable"],
            "earth_radius_m": self.options["earth_radius_m"],
            "expected_source": self.options["expected_source"],
            "field_declaration": self.descriptor["declaration"],
            "field_declaration_origin": self.descriptor["declaration_origin"],
            "cube_association": self.descriptor["sampling"].get("native_cube"),
            "zone": self.zone, "key": encoded,
            "allow_unscaled": self.descriptor["declaration"].get("allow_unscaled", False),
            "diagnostics_path": self.diagnostics_path,
            "timeout_seconds": self.options["timeout_seconds"],
            "max_points": self.options["max_points"],
        })
        observed = result["field_descriptors"][self.field]
        if any(observed.get(name) != self.descriptor.get(name) for name in (
            "native_id", "source", "native", "sampling", "units", "temporal_support",
            "eligibility", "declaration",
        )):
            raise ValueError(f"FA decoded descriptor contradicts selection for {self.field}")
        shape = tuple(len(range(*v.indices(n))) for v, n in zip(key, self.shape, strict=True)
                      if isinstance(v, slice))
        if result["values"].shape != shape:
            raise ValueError(f"FA decoded shape contradicts selection for {self.field}")
        return result["values"]


def fa_selected_array(record, source_plan, *, options, diagnostics_path=None):
    """Construct a lazy exact-locator read, retaining execution-time codec checks."""
    from frameit.processing.requests import _fa_gridpoint

    locator = record["locator"]
    context = f"{locator['path']}: {record['name']}"
    if (source_plan.get("format") != "fa" or locator.get("format") != "fa"
            or options["profile"] != source_plan["profile"]):
        raise ValueError(f"{context}: selected FA profile/format contradicts its owning source")
    if record.get("selection_grid_id", record["grid_id"]) != record["grid_id"]:
        raise ValueError(f"{context}: FA destination sampling requires method binding")
    # Bound cubes narrow locator.records; every other original fact stays intact.
    original = [candidate for candidate in source_plan["record_inventory"]
                if {k: v for k, v in candidate.items() if k != "locator"} == {
                    k: record.get(k) for k in candidate if k != "locator"}
                and {k: v for k, v in candidate["locator"].items() if k != "records"} == {
                    k: v for k, v in locator.items() if k != "records"}]
    if len(original) != 1:
        raise ValueError(f"{context}: selected FA record is outside the closed inventory "
                         "or contradicts original record metadata")
    stat = Path(locator["path"]).stat()
    if locator["identity"] != [stat.st_size, stat.st_mtime_ns]:
        raise ValueError(f"{context}: FA input changed since inventory "
                         "(size/mtime freshness check)")
    grid = source_plan["native_grids"][record["grid_id"]]
    geometry = fa_geometry(grid["fa_header"], options)
    if locator["zone"] != geometry.attrs["fa_zone_indices"]:
        raise ValueError(f"{context}: selected FA zone contradicts its owning grid")
    field = source_plan["fields"][record["field_id"]]
    cube = field.get("native_cube")
    declaration = options["field_metadata"].get(record["name"])
    original_declaration = source_plan.get("declaration", {}).get(
        "field_metadata", {}).get(record["name"])
    if original_declaration is not None and declaration != original_declaration:
        raise ValueError(f"{context}: FA field requires its original source field_metadata")
    if cube:
        if cube != options["native_cubes"].get(record["name"]):
            raise ValueError(f"{context}: native cube requires its original explicit declaration")
        positions = record.get("source_positions")
        if (not positions or any(type(i) is not int or not 0 <= i < len(cube["records"])
                                 for i in positions) or len(set(positions)) != len(positions)):
            raise ValueError(f"{context}: invalid selected FA cube source positions")
        names = [cube["records"][i] for i in positions]
    else:
        if record.get("source_positions") is not None or record.get("vertical") is not None:
            raise ValueError(f"{context}: a 2-D FA record has no selectable vertical axis")
        names = [record["name"]]
    if locator["records"] != names:
        raise ValueError(f"{context}: selected FA records contradict source positions/declaration")
    descriptors = {}
    for name in names:
        candidates = [part for part in source_plan["record_inventory"]
                      if part["name"] == name
                      and all(part.get(k) == record.get(k) for k in (
                          "time", "cycle", "calendar", "clock", "time_bounds", "temporal_metadata"))
                      and part["locator"] == {**locator, "records": [name]}]
        if len(candidates) != 1:
            raise ValueError(f"{context}: FA cube/raw record {name} needs one original "
                             "provider/sample descriptor in its selected file")
        part = candidates[0]
        descriptor = _fa_gridpoint(source_plan, part)
        if geometry_signature(source_plan["native_grids"][part["grid_id"]]["fa_header"],
                              options) != geometry_signature(grid["fa_header"], options):
            raise ValueError(f"{context}: FA cube part {name} contradicts its owning geometry")
        for key, value in descriptor["sampling"].get("native_vertical_header", {}).items():
            if key in grid["fa_header"] and not np.array_equal(value, grid["fa_header"][key]):
                raise ValueError(f"{context}: FA cube part {name} contradicts its owning header")
        descriptors[name] = resolve_descriptor(
            descriptor, declaration, declaration_origin="explicit_source.field_metadata")
    vertical = record.get("vertical")
    coords = dict(geometry.coords)
    dims = ("time", "y", "x")
    if cube:
        count = grid["fa_header"].get("KNIVER")
        if type(count) is not int or count < 1:
            raise ValueError(f"{context}: FA cube has no evidenced native vertical header")
        # Validate native order, then retain the independent product/support read order.
        ordered = [cube["records"][i] for i in sorted(positions)]
        layout = cube_layouts(
            {"field_descriptors": descriptors,
             "hybrid_contract": {"interface_indices": list(range(count + 1))}},
            {"native_cubes": {record["name"]: {**cube, "records": ordered}}},
            [record["name"]],
            declaration_origin="explicit source.native_cubes")[record["name"]]
        group = layout["group"]
        labels = [descriptors[name]["sampling"]["epygram"]["levels"][0] for name in names]
        native_indices = [int(label) - 1 for label in labels]
        if vertical is not None and (
            vertical["dimension"] != group or vertical["positions"] != positions
            or vertical["values"] != labels or vertical["source_native_indices"] != native_indices
            or vertical["units"] != "1"
        ):
            raise ValueError(f"{context}: selected FA vertical metadata contradicts native records")
        coords.update({
            group: (group, labels, {"axis": "Z", "units": "1", "positive": "down"}),
            f"{group}_source_native_index": (group, native_indices, {"units": "1"}),
            f"{record['name']}_native_record": (group, names),
        })
        if vertical is not None:
            for coordinate, expected in (
                (group, labels), (f"{group}_source_native_index", native_indices),
            ):
                spec = vertical["coordinates"].get(coordinate)
                if spec is not None and (
                    spec["dimensions"] != [group] or not np.array_equal(spec["values"], expected)
                ):
                    raise ValueError(f"{context}: FA coordinate {coordinate} "
                                     "contradicts selected native records")
            coords.update({name: (spec["dimensions"], spec["values"], spec["attributes"])
                           for name, spec in vertical["coordinates"].items()})
        dims = ("time", group, "y", "x")
    arrays = []
    for name in names:
        array = FaArray(locator["path"], name, {
            "identity": locator["identity"], "field_descriptors": descriptors,
        }, options, locator["zone"], diagnostics_path)
        token = hashlib.sha256(json.dumps({
            "path": str(Path(array.path).resolve()), "identity": array.identity,
            "field": name, "descriptor": array.descriptor, "options": array.options,
            "zone": array.zone, "diagnostics_path": diagnostics_path,
        }, sort_keys=True).encode()).hexdigest()
        arrays.append(da.from_array(
            array, chunks=array.shape, asarray=False, fancy=False, name="fa-selected-" + token,
            meta=np.empty((0, 0), dtype="float64")))
    values = da.stack(arrays, axis=0) if cube else arrays[0]
    coords.update(time=("time", [record["time"]]),
                  forecast_reference_time=record["cycle"],
                  forecast_period=("time", [record["time"] - record["cycle"]]))
    descriptor = descriptors[names[0]]
    attrs = {**declaration, "source_variable_name": record["name"], "grid_mapping": "crs",
             "source_units": declaration["units"],
             "field_definition_source": "explicit_source.field_metadata",
             "cell_methods": "time: point",
             "fa_field_descriptor_scope": (
                 "representative input record; per-file descriptors "
                 "and decode observations in run provenance"),
             "fa_field_descriptor": json.dumps(descriptor, sort_keys=True),
             "fa_native_record_descriptors": json.dumps(descriptors, sort_keys=True)}
    if descriptor["native"]["directory"]:
        attrs.update(surfex_support_mask=descriptor["native"]["directory"]["MASK"],
                     surfex_native_type=descriptor["native"]["type"])
    return xr.DataArray(values[None, ...], name=record["name"], dims=dims,
                         coords=coords, attrs=attrs)


def _selected_fa(files, binding, source, conf, resources):
    """Assemble only bound product/internal stencils through the selected leaf."""
    if binding.get("status") != "bound" or source is None:
        raise ValueError("FA selected_records requires bound interpretation "
                         "and owning source metadata")
    from frameit.processing.polar.contracts import require_executable_products

    require_executable_products(binding, source)
    admitted = {Path(path).resolve() for path in files}
    log_directory = conf.output_dir / "logs"
    decoder_log = (log_directory / f"fa-decoder-{uuid4().hex}.jsonl"
                   if log_directory.is_dir() else None)
    provenance = []

    def groups(descriptors, *, internal=False):
        by_grid, vertical_dims = {}, set()
        for name, descriptor in descriptors.items():
            if descriptor.get("operation"):
                continue
            samples = {}
            for record in descriptor["records"]:
                if Path(record["locator"]["path"]).resolve() not in admitted:
                    raise ValueError(f"{name}: selected locator is outside the admitted FA files")
                array = fa_selected_array(
                    record, source, options=conf.fa_options,
                    diagnostics_path=str(decoder_log) if decoder_log is not None else None)
                grid = source["native_grids"][record["grid_id"]]
                dataset = array.to_dataset()
                cube = source["fields"][record["field_id"]].get("native_cube")
                if cube:
                    group = record["vertical"]["dimension"]
                    vertical_dims.add(group)
                    dataset = add_cube_coordinates(dataset, {
                        "hybrid_contract": grid["fa_hybrid_contract"],
                        "native_cubes": {name: {
                            **cube, "group": group,
                            "levels": array[group].values.tolist(),
                            "source_native_indices": record["vertical"]["source_native_indices"],
                            "records": record["locator"]["records"]}}})
                    dataset[name].attrs.update(
                        ancillary_variables=" ".join(
                            (*HYBRID_AUXILIARIES, f"{name}_native_record")),
                        fa_vertical_position=cube["vertical_position"],
                        fa_sampling_origin="explicit source.native_cubes",
                        fa_physical_coordinates="not computed")
                    if cube.get("vector_basis"):
                        dataset[name].attrs.update(wind_reference_frame=cube["vector_basis"],
                                                  fa_component_scaling=cube.get("component_scaling"))
                dataset.attrs = dict(grid["fa_geometry"], source_format="fa",
                                     fa_profile=conf.fa_options["profile"])
                dataset.time.encoding["calendar"] = record["calendar"]
                resources.add(dataset)
                samples.setdefault(record["grid_id"], []).append(dataset)
                provenance.append({
                    "source_id": Path(record["locator"]["path"]).name,
                    "identity_strategy": "size_mtime_freshness",
                    "identity": record["locator"]["identity"],
                    "valid_time": str(record["time"]), "reference_time": str(record["cycle"]),
                    "profile": conf.fa_options["profile"],
                    "subdomain": conf.fa_options["subdomain"],
                    "earth_radius_m": conf.fa_options["earth_radius_m"],
                    "expected_source": conf.fa_options["expected_source"],
                    "grid_lookup": grid["fa_geometry"]["fa_grid_lookup"],
                    "field_descriptors": json.loads(array.attrs["fa_native_record_descriptors"]),
                    "decoder_log": str(decoder_log.relative_to(conf.output_dir))
                    if decoder_log is not None else None,
                    "decode_check_policy": "required on payload evaluation; see decoder_log"})
            for grid_id, sequence in samples.items():
                combined = (sequence[0] if len(sequence) == 1 else xr.concat(
                    sequence, dim="time", data_vars="all", coords="minimal",
                    compat="equals", join="exact", combine_attrs="override"))
                by_grid.setdefault(grid_id, []).append(combined)
        from frameit.tracking.tracker_core import merge_internal_stencils

        return {grid_id: (merge_internal_stencils(datasets, vertical_dims) if internal else
                         xr.merge(datasets, join="exact", compat="identical",
                                  combine_attrs="override"))
                for grid_id, datasets in by_grid.items()}

    user = groups(binding["products"].get("model_grid", {}))
    tracker = {"internal": groups(binding["dependencies"], internal=True)} \
        if binding["dependencies"] else {}
    conf.add_parameter("fa_inputs", provenance)
    return user, tracker


@managed_loading
def concat_fa2ds_by_vert_coord(
    files, user_requested_variables_yaml, tracker_requested_variables_by_method_yaml,
    method=None, *, wind_conf, resources=None, strict=False,
    duplicate_time_policy="first", native_output_groups=None,
    selected_records=None, source_plan=None,
):
    """Gridpoint instantaneous records only; spectral transforms are not implicit."""
    if selected_records is not None:
        return _selected_fa(files, selected_records, source_plan, wind_conf, resources)
    if getattr(wind_conf, "schema_version", None) == 3:
        raise ValueError("FA source interpretation requires selected bound requests; "
                         "pending metadata does not authorize payload reading")
    requests = normalize_requests(user_requested_variables_yaml)
    if not wind_conf.fa_options["native_cubes"] and (set(requests) - {"surface"} or any(
        req["level_indices"] or req["levels"] or req["level_domain"] != "stored"
        for req in requests.values()
    )):
        raise ValueError("FA selection uses 2-D native record names in the surface group, "
                         "not an inferred vertical axis")
    methods = ([method] if method is not None else
               list(tracker_requested_variables_by_method_yaml or {}))
    if any(m not in {"fixed_box", "prescribed_track"} for m in methods):
        raise ValueError("FA tracking currently supports fixed_box or prescribed_track; "
                         "use a GRIB/NetCDF tracking source for coupled atmospheric tracking")
    names = fa_field_names(requests)
    parts, geometries, provenance, vertical_signatures = [], {}, [], set()
    log_directory = wind_conf.output_dir / "logs"
    decoder_log = (log_directory / f"fa-decoder-{uuid4().hex}.jsonl"
                   if log_directory.is_dir() else None)
    for path in resolve_input_files(files, strict=strict):
        info = inspect_fa_inputs(path, wind_conf, names)
        validate_cube_requests(info, requests, wind_conf)
        if info.get("native_cubes"):
            vertical_signatures.add(vertical_signature(info))
            if len(vertical_signatures) != 1:
                raise ValueError("Selected FA inputs have incompatible native vertical definitions")
        # Library axes/CRS/zones define EPyGrAM sampling; vertical facts are separate.
        signature = geometry_signature(info["geometry"], wind_conf.fa_options)
        if signature not in geometries:
            geometries[signature] = fa_geometry(info["geometry"], wind_conf.fa_options)
        geometry = geometries[signature]
        ds = fa_metadata_dataset(info, wind_conf.fa_options, geometry)
        arrays = {}
        for name in info["field_descriptors"]:
            array = FaArray(path, name, info, wind_conf.fa_options, ds.attrs["fa_zone_indices"],
                            str(decoder_log) if decoder_log is not None else None)
            token = hashlib.sha256(json.dumps({
                "path": str(path.resolve()), "identity": array.identity, "field": name,
                "options": array.options, "zone": array.zone,
            }, sort_keys=True).encode()).hexdigest()
            values = da.from_array(array, chunks=array.shape, asarray=False, fancy=False,
                                   name="fa-" + token, meta=np.empty((0, 0), dtype="float64"))
            arrays[name] = values
        for name in names:
            layout = info["native_cubes"].get(name)
            record = layout["records"][0] if layout else name
            values = (da.stack([arrays[r] for r in layout["records"]], axis=0) if layout
                      else arrays[name])
            attrs = {**ds[name].attrs, "source_units": ds[name].attrs["units"],
                     "fa_packing": info["fields"][record]["packing"],
                     "fa_bits": info["fields"][record]["bits"],
                     "field_definition_source": "explicit_input.fa.field_metadata",
                     "cell_methods": "time: point"}
            if "surfex_descriptor" in info["fields"][record]:
                descriptor = info["fields"][record]["surfex_descriptor"]
                attrs.update(surfex_support_mask=descriptor["MASK"],
                             surfex_native_type=descriptor["TYPE"])
            dims = ("time", layout["group"], "y", "x") if layout else ("time", "y", "x")
            ds[name] = xr.DataArray(values[None, ...], dims=dims, attrs=attrs)
            if attrs.get("allow_unscaled"):
                log.warning("%s: %s permits native identity-scaling fallback "
                            "by explicit declaration", path.name, name)
        parts.append(ds)
        provenance.append({"source_id": path.name, "identity_strategy": "size_mtime_freshness",
                           "size_bytes": info["identity"][0], "mtime_ns": info["identity"][1],
                           "valid_time": info["valid_time"],
                           "reference_time": info["reference_time"],
                           "profile": wind_conf.fa_options["profile"],
                           "subdomain": wind_conf.fa_options["subdomain"],
                           "earth_radius_m": wind_conf.fa_options["earth_radius_m"],
                           "horizontal_header_signature": signature,
                           "grid_lookup": geometry.attrs["fa_grid_lookup"],
                           "backend_versions": info["backend_versions"],
                           "decoder_log": (str(decoder_log.relative_to(wind_conf.output_dir))
                                           if decoder_log is not None else None),
                           "fields": info["field_definitions"], "encoding": info["fields"],
                           "protocol_version": info["protocol_version"],
                           "field_descriptors": info["field_descriptors"],
                            "expected_source": wind_conf.fa_options["expected_source"]})
        provenance[-1].update(native_cubes=info["native_cubes"],
                               hybrid_contract=info.get("hybrid_contract"),
                               backend=info["backend_versions"]["FA_backend"],
                               requested_backend=wind_conf.fa_options["backend"])
        provenance[-1]["geometry_contract"] = info["geometry"].get("epygram")
        provenance[-1]["producer_metadata"] = info["surfex_metadata"]
    if len(geometries) != 1:
        raise ValueError("Selected FA inputs have incompatible horizontal geometry")
    if len({entry["reference_time"] for entry in provenance}) != 1:
        raise ValueError("Select one FA forecast cycle explicitly; "
                         "duplicate policy cannot select cycles")
    combined = drop_time_dupes(xr.concat(parts, dim="time", data_vars="all", coords="minimal",
                                         compat="equals", join="exact"), keep=duplicate_time_policy)
    combined = combined.sortby("time")
    wind_conf.add_parameter("fa_inputs", provenance)
    native = {group: build_group_ds(combined, req, group, "time", None)
              for group, req in requests.items()}
    native = {key: value for key, value in native.items() if value is not None}
    if native_output_groups is not None:
        native_output_groups.update(native)
    geometry = combined.drop_vars(list(combined.data_vars))
    return native, {name: {"surface": geometry} for name in methods}
