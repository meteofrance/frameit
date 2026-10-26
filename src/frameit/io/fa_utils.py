"""Selected, lazy FA fields on FrameIt's normal grouped dataset interface."""

from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from uuid import uuid4

import dask.array as da
import numpy as np
import xarray as xr

from frameit.check.check_functions import drop_time_dupes
from frameit.io.fa_backend import inspect_fa, request_fa
from frameit.io.fa_contracts import resolve_descriptor, validate_descriptor
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
    info = inspect_fa(path, options["profile"], fields, timeout_seconds=options["timeout_seconds"],
                      expected_source=options["expected_source"])
    if set(conf.requests_user()) - {"surface"}:
        raise ValueError("FA currently supports explicit 2-D records in variables.surface only; "
                         "native layer/patch record identities are retained")
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
        name: resolve_descriptor(info["field_descriptors"][name], info["field_definitions"][name])
        for name in fields}
    return info


def fa_metadata_dataset(info, options, geometry=None):
    ds = (fa_geometry(info["geometry"], options) if geometry is None else geometry).copy(deep=False)
    stamp = np.datetime64(info["valid_time"], "ns")
    ds = ds.assign_coords(time=("time", [stamp]),
                          forecast_reference_time=np.datetime64(info["reference_time"], "ns"),
                          forecast_period=("time", [np.timedelta64(info["lead_seconds"], "s")]))
    for name, definition in info.get("field_definitions", {}).items():
        ds[name] = xr.DataArray(0., attrs={**definition, "source_variable_name": name,
                                          "grid_mapping": "crs",
                                          "fa_field_descriptor_scope": (
                                              "representative input record; per-file descriptors "
                                              "and decode observations in run provenance"),
                                          "fa_field_descriptor": json.dumps(
                                              info["field_descriptors"][name], sort_keys=True)})
    ds.attrs.update(_frameit_vertical_group="surface", source_format="fa",
                    fa_profile=options["profile"], fa_identifier=info["identifier"])
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
        return request_fa({
            "operation": "read", "path": self.path, "identity": self.identity,
            "profile": self.options["profile"], "fields": [self.field],
            "expected_source": self.options["expected_source"],
            "field_declaration": self.descriptor["declaration"],
            "zone": self.zone, "key": encoded,
            "allow_unscaled": self.options["field_metadata"][self.field].get(
                "allow_unscaled", False),
            "diagnostics_path": self.diagnostics_path,
            "timeout_seconds": self.options["timeout_seconds"],
            "max_points": self.options["max_points"],
        })["values"]


@managed_loading
def concat_fa2ds_by_vert_coord(
    files, user_requested_variables_yaml, tracker_requested_variables_by_method_yaml,
    method=None, *, wind_conf, resources=None, strict=False,
    duplicate_time_policy="first", native_output_groups=None,
):
    """Gridpoint instantaneous records only; spectral transforms are not implicit."""
    requests = normalize_requests(user_requested_variables_yaml)
    if set(requests) - {"surface"} or any(
        req["level_indices"] or req["levels"] or req["level_domain"] != "stored"
        for req in requests.values()
    ):
        raise ValueError("FA selection uses 2-D native record names in the surface group, "
                         "not an inferred vertical axis")
    methods = ([method] if method is not None else
               list(tracker_requested_variables_by_method_yaml or {}))
    if any(m not in {"fixed_box", "prescribed_track"} for m in methods):
        raise ValueError("FA tracking currently supports fixed_box or prescribed_track; "
                         "use a GRIB/NetCDF tracking source for coupled atmospheric tracking")
    names = fa_field_names(requests)
    parts, geometries, provenance = [], {}, []
    log_directory = wind_conf.output_dir / "logs"
    decoder_log = (log_directory / f"fa-decoder-{uuid4().hex}.jsonl"
                   if log_directory.is_dir() else None)
    for path in resolve_input_files(files, strict=strict):
        info = inspect_fa_inputs(path, wind_conf, names)
        # Only the active horizontal header entries define source sampling.
        signature = geometry_signature(info["geometry"], wind_conf.fa_options)
        if signature not in geometries:
            geometries[signature] = fa_geometry(info["geometry"], wind_conf.fa_options)
        geometry = geometries[signature]
        ds = fa_metadata_dataset(info, wind_conf.fa_options, geometry)
        for name in names:
            array = FaArray(path, name, info, wind_conf.fa_options, ds.attrs["fa_zone_indices"],
                            str(decoder_log) if decoder_log is not None else None)
            token = hashlib.sha256(json.dumps({
                "path": str(path.resolve()), "identity": array.identity, "field": name,
                "options": array.options, "zone": array.zone,
            }, sort_keys=True).encode()).hexdigest()
            values = da.from_array(array, chunks=array.shape, asarray=False, fancy=False,
                                   name="fa-" + token, meta=np.empty((0, 0), dtype="float64"))
            attrs = {**ds[name].attrs, "source_units": ds[name].attrs["units"],
                     "fa_packing": info["fields"][name]["packing"],
                     "fa_bits": info["fields"][name]["bits"],
                     "field_definition_source": "explicit_input.fa.field_metadata",
                     "cell_methods": "time: point"}
            if "surfex_descriptor" in info["fields"][name]:
                descriptor = info["fields"][name]["surfex_descriptor"]
                attrs.update(surfex_support_mask=descriptor["MASK"],
                             surfex_native_type=descriptor["TYPE"])
            ds[name] = xr.DataArray(values[None, ...], dims=("time", "y", "x"), attrs=attrs)
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
                           "backend_versions": info["backend_versions"],
                           "decoder_log": (str(decoder_log.relative_to(wind_conf.output_dir))
                                           if decoder_log is not None else None),
                           "fields": info["field_definitions"], "encoding": info["fields"],
                           "protocol_version": info["protocol_version"],
                           "field_descriptors": info["field_descriptors"],
                           "expected_source": wind_conf.fa_options["expected_source"]})
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
        from frameit.processing.derived.wind import normalize_native_wind_units

        native_output_groups.update({g: normalize_native_wind_units(ds, wind_conf, g)
                                     for g, ds in native.items()})
    geometry = combined.drop_vars(list(combined.data_vars))
    return native, {name: {"surface": geometry} for name in methods}
