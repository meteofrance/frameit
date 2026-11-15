# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import datetime as dt
import json
import logging
import multiprocessing
from collections.abc import Callable, Mapping
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from frameit._version import __version__ as frameit_version
from frameit.utils.atomic import atomic_output

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return (
        dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


class _JSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        if isinstance(obj, (dt.datetime, dt.date)):
            return obj.isoformat()
        return super().default(obj)


def _sanitize_filename_token(token: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return "".join(ch if ch in allowed else "_" for ch in token)


def _jsonify_if_needed(value: Any) -> str | None:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, cls=_JSONEncoder, ensure_ascii=False, sort_keys=True)
    return None


def _sanitize_attrs(attrs: Mapping[str, Any]) -> dict[str, Any]:
    """
    NetCDF attrs must be scalar strings/numbers (or arrays of those).
    Convert dict/list-like attrs into JSON strings with *_json suffix.
    """
    out: dict[str, Any] = {}
    for k, v in (attrs or {}).items():
        if v is None:
            continue

        js = _jsonify_if_needed(v)
        if js is not None:
            if f"{k}_json" in attrs:
                raise ValueError(f"Metadata annotation collision: {k}_json")
            out[f"{k}_json"] = js
            continue

        if isinstance(v, Path):
            out[k] = str(v)

        # IMPORTANT: netCDF4 does not allow boolean attributes
        elif isinstance(v, (bool, np.bool_)):
            out[k] = np.int8(v)

        elif isinstance(v, (np.integer,)):
            out[k] = int(v)
        elif isinstance(v, (np.floating,)):
            out[k] = float(v)
        elif isinstance(v, (dt.datetime, dt.date)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _append_history(ds: xr.Dataset, entry: str) -> xr.Dataset:
    hist = ds.attrs.get("history", "")
    ds.attrs["history"] = f"{hist}\n{entry}" if hist else entry
    return ds


def _output_geography(grid_id, coordinates):
    geography = {}
    for kind, conventional in (
        ("latitude", {"latitude", "latitude_u", "latitude_v", "nav_lat",
                      "lat_rho", "lat_u", "lat_v"}),
        ("longitude", {"longitude", "longitude_u", "longitude_v", "nav_lon",
                       "lon_rho", "lon_u", "lon_v"}),
    ):
        found = [n for n, c in coordinates.items()
                 if c["attributes"].get("standard_name") == kind or n in conventional]
        if len(found) > 1:
            raise ValueError(f"{grid_id}: ambiguous output {kind}: {found}")
        if found:
            geography[kind] = found[0]
    return geography


def _moving_grid_trajectories(source):
    """Identify complete inventoried coordinate trajectories, not individual snapshots."""
    from frameit.core.preflight import _metadata_id

    snapshots = {}
    for grid_id, grid in source["native_grids"].items():
        geography = _output_geography(grid_id, grid["coordinates"])
        if not any(set(grid["coordinates"][n]["dimensions"]) - grid["dimensions"].keys()
                   for n in geography.values()):
            continue
        snapshots[grid_id] = {}
        for name in geography.values():
            coordinate = grid["coordinates"][name]
            frames = set()
            for provider in grid.get("coordinate_providers", {}).get(name, []):
                for sample in provider["samples"]:
                    indexers = sample["indexers"]
                    spatial = [d for d in coordinate["dimensions"] if d not in indexers]
                    frames.add(_metadata_id("", {
                        "time": sample["time"], "calendar": sample["calendar"],
                        "cycle": sample["cycle"], "time_bounds": sample.get("time_bounds"),
                        "dimensions": spatial, "attributes": coordinate["attributes"],
                        "dtype": str(np.asarray(coordinate["values"]).dtype),
                        "axes": {d: grid["coordinates"][d] for d in spatial
                                 if d in grid["coordinates"]},
                        "values": np.asarray(coordinate["values"])[tuple(
                            indexers.get(d, slice(None)) for d in coordinate["dimensions"])],
                    }))
            # Excluded records still contribute known geometry, without inventing their clocks.
            snapshots[grid_id][name] = frames or {_metadata_id("", coordinate)}
    if not snapshots:
        return {}
    owners, signatures, cache = {}, {}, {}
    for field_id, entry in source["fields"].items():
        grid_ids = tuple(sorted(g for g in entry.get("grid_ids", [entry.get("grid_id")])
                                if g in snapshots))
        if not grid_ids:
            continue
        if grid_ids not in cache:
            cache[grid_ids] = _metadata_id("", {
                name: sorted({frame for g in grid_ids for frame in snapshots[g][name]})
                for name in snapshots[grid_ids[0]]})
        signatures[field_id] = cache[grid_ids]
        for grid_id in grid_ids:
            owners.setdefault(grid_id, {}).setdefault(cache[grid_ids], set()).add(entry["name"])
    for descriptors in source.get("requests", {}).get("binding", {}).get("products", {}).values():
        for name, descriptor in descriptors.items():
            signature = signatures.get(descriptor.get("field_id"))
            for record in descriptor["records"]:
                grid_id = record["selection_grid_id"]
                if signature is not None and grid_id in owners:
                    owners[grid_id].setdefault(signature, set()).add(name)
    return owners


def _output_grid_facts(layout, grid_id, field=None):
    if grid_id in layout:
        return layout[grid_id]
    matches = [facts for facts in layout.values()
               if facts["native_grid_id"] == grid_id and field in facts["fields"]]
    if len(matches) != 1:
        raise ValueError(f"{grid_id}: unresolved output trajectory for {field!r}")
    return matches[0]


def output_grid_layout(source):
    """Resolve names from the complete inventory, never the selected field order."""
    from frameit.core.preflight import _metadata_id

    moving = _moving_grid_trajectories(source)
    grids, origins = {}, {}
    for grid_id, grid in {
        **source["native_grids"], **source.get("representation_grids", {})
    }.items():
        variants = moving.get(grid_id, {None: set()})
        for trajectory, fields in variants.items():
            key = grid_id if len(variants) == 1 else f"{grid_id}_{trajectory}"
            grids[key] = grid
            origins[key] = grid_id, trajectory, sorted(fields)
    layouts, axes, horizontal = {}, {}, {}
    for grid_id, grid in grids.items():
        native_id, trajectory, fields = origins[grid_id]
        grid = {**grid, "dimensions": dict(grid["dimensions"]),
                "coordinates": dict(grid["coordinates"])}
        if group := grid.get("vertical_group"):
            levels = sorted({value for field in source["fields"].values()
                             if native_id in field.get("grid_ids", [field.get("grid_id")])
                             for value in field.get("levels", [])})
            if levels:
                grid["dimensions"][group] = len(levels)
                grid["coordinates"][group] = {
                    "dimensions": [group], "values": np.asarray(levels), "attributes": {}}
        if "vertical_position" in grid:
            group = "level_w" if grid["vertical_position"] == "interface" else "level"
            cubes = [field["native_cube"] for field in source["fields"].values()
                     if "native_cube" in field and native_id in field.get(
                         "grid_ids", [field.get("grid_id")])]
            if cubes:
                labels = {field["name"]: field["native_descriptor"]["sampling"].get(
                    "epygram", {}).get("levels", [])
                          for field in source["fields"].values() if "native_descriptor" in field}
                grid["dimensions"][group] = len(cubes[0]["records"])
                grid["coordinates"][group] = {
                    "dimensions": [group],
                    "values": [labels[record][0] for record in cubes[0]["records"]],
                    "attributes": {}}
        model = source["model"]
        names = ({"eta_rho": "y_rho", "xi_rho": "x_rho", "eta_v": "y_v", "xi_u": "x_u"}
                 if model == "croco" else
                 {"y": "y_t", "x": "x_t"} if model == "nemo" else
                 {"nj": "y", "ni": "x", "latitude": "y", "longitude": "x",
                  "y": "y", "x": "x", "nj_u": "y", "ni_u": "x_u",
                  "nj_v": "y_v", "ni_v": "x"})
        dims, identities = {}, {}
        coordinates = grid["coordinates"]
        h_dims = {dim: names[dim] for dim in grid["dimensions"] if dim in names}
        geography = _output_geography(grid_id, coordinates)
        h_facts = ({"trajectory": trajectory} if trajectory is not None else
                   {n: coordinates[n] for n in geography.values()})
        h_identity = _metadata_id("", {"dimensions": h_dims, "geography": h_facts})
        pair = tuple(sorted(h_dims.values()))
        horizontal.setdefault(pair, set()).add(h_identity)
        for dim in grid["dimensions"]:
            coord = coordinates.get(dim, {})
            attrs = coord.get("attributes", {})
            base = names.get(dim, dim)
            if dim in {"isobaricInhPa", "isobaricInPa"} or attrs.get(
                "standard_name") == "air_pressure":
                base = "pressure"
            elif dim == "heightAboveGround":
                base = "height_above_ground"
            elif dim == "native_level":
                base = "level_w" if grid.get("vertical_location") == "interface" else "level"
            dims[dim] = base
            dependencies = {n: c for n, c in coordinates.items()
                            if dim in c["dimensions"] and n not in geography.values()
                            and not n.endswith("_source_native_index")}
            if native_id in source.get("representation_grids", {}) and dim not in h_dims:
                originals = [
                    {n: c for n, c in native["coordinates"].items()
                     if dim in c["dimensions"] and not n.endswith("_source_native_index")}
                    for native in source["native_grids"].values()
                    if dim in native["coordinates"]
                    and coord.get("attributes", {}).get("units")
                    == native["coordinates"][dim]["attributes"].get("units")
                    and np.isin(coord.get("values", []),
                                native["coordinates"][dim]["values"]).all()]
                unique = {_metadata_id("", value): value for value in originals}
                if len(unique) == 1:
                    dependencies = next(iter(unique.values()))
            identity = _metadata_id("", (
                {"coordinate": {k: v for k, v in coord.items() if k != "dimensions"},
                 "size": grid["dimensions"][dim]}
                if dim in h_dims and coord else
                {"native_name": dim, "coordinates": dependencies,
                 "size": len(dependencies[dim]["values"]) if dim in dependencies
                 else grid["dimensions"][dim]}))
            identities[dim] = identity
            axes.setdefault(base, set()).add(identity)
        suffix = ("_u" if "x_u" in h_dims.values() else
                  "_v" if "y_v" in h_dims.values() else
                  "_rho" if model == "croco" else "_t" if model == "nemo" else "")
        layouts[grid_id] = {
            "native_grid_id": native_id, "fields": fields,
            "dimensions": dims, "identities": identities, "horizontal": h_dims,
            "horizontal_identity": h_identity, "pair": pair,
            "geography": {native: kind + suffix for kind, native in geography.items()},
            "suffix": suffix,
        }
    for layout in layouts.values():
        multiple_grids = len(horizontal[layout["pair"]]) > 1
        for dim, base in layout["dimensions"].items():
            identity = layout["identities"][dim]
            if dim in layout["horizontal"] and multiple_grids:
                identity = layout["horizontal_identity"]
            if len(axes[base]) > 1 or (dim in layout["horizontal"] and multiple_grids):
                layout["dimensions"][dim] = f"{base}_{identity}"
        if multiple_grids:
            layout["geography"] = {
                n: f"{target}_{layout['horizontal_identity']}"
                for n, target in layout["geography"].items()}
    coordinates, identities = {}, {}
    for grid_id, layout in layouts.items():
        names, signatures = {}, {}
        for name, coord in grids[grid_id]["coordinates"].items():
            if name in layout["horizontal"]:
                continue
            target = layout["geography"].get(name, layout["dimensions"].get(name, name))
            signature = _metadata_id("", {
                "dimensions": [layout["dimensions"].get(d, d) for d in coord["dimensions"]],
                **{k: v for k, v in coord.items() if k not in {"dimensions", "values"}
                   or k == "values" and set(coord["dimensions"]) <= set(layout["dimensions"])}})
            names[name], signatures[name] = target, signature
            identities.setdefault(target, set()).add(signature)
        coordinates[grid_id] = names, signatures
    for grid_id, (names, signatures) in coordinates.items():
        layout = layouts[grid_id]
        layout["coordinates"] = {
            name: (f"{target}_{signatures[name]}" if len(identities[target]) > 1
                   and name not in layout["dimensions"] and name not in layout["geography"]
                   else target)
            for name, target in names.items()}
        layout["original_coordinates"] = {
            native: {
                "coordinate": f"{target if target != base else native}_source_coordinate"
                if native in grids[grid_id]["coordinates"] else None,
                "index": f"{target if target != base else native}_source_native_index",
            }
            for native, base in layout["horizontal"].items()
            for target in [layout["dimensions"][native]]}
    return layouts


def _rename_coordinate_links(dataset, names):
    """Rename CF variable references, not semantic labels, methods or comments."""
    import re

    if not names:
        return
    for variable in dataset.variables.values():
        for mapping in (variable.attrs, variable.encoding):
            for key in ("coordinates", "bounds", "formula_terms", "cell_measures",
                        "ancillary_variables", "grid_mapping", "cell_methods"):
                if isinstance(mapping.get(key), str):
                    if key in {"formula_terms", "cell_measures"}:
                        mapping[key] = re.sub(
                            r"(:\s*)(\S+)", lambda m: m[1] + names.get(m[2], m[2]), mapping[key])
                    elif key == "cell_methods":
                        mapping[key] = re.sub(
                            r"\([^)]*\)|([^\s:()]+)(?=\s*:)",
                            lambda m: names.get(m[1], m[1])
                            if m[1] and m[1] not in {"area", "volume"} else m[0], mapping[key])
                    else:
                        mapping[key] = re.sub(
                            r"[^\s:]+", lambda m: names.get(m[0], m[0]), mapping[key])


def format_model_grid(dataset, grid_id, source, layout, *, field=None):
    """Qualify an already selected/cropped grid without changing its samples."""
    ds = dataset.copy(deep=False)
    facts = _output_grid_facts(layout, grid_id, field)
    dimensions, horizontal = dict(facts["dimensions"]), dict(facts["horizontal"])
    geography = dict(facts["geography"])
    # Formula support can live on another admitted native grid (e.g. CROCO rho
    # depth supporting a U face). Keep that support's axes, not the field's axes.
    for other in layout.values():
        for dim, target in other["dimensions"].items():
            if dim in ds.dims and dim not in dimensions:
                candidates = {item["dimensions"][dim] for item in layout.values()
                              if dim in item["dimensions"]}
                if len(candidates) != 1:
                    raise ValueError(f"{grid_id}: ambiguous output support axis {dim}")
                dimensions[dim] = target
                if dim in other["horizontal"]:
                    horizontal[dim] = other["horizontal"][dim]
        for native, target in other["geography"].items():
            if native in ds and native not in geography:
                candidates = {item["geography"][native] for item in layout.values()
                              if native in item["geography"]}
                if len(candidates) == 1:
                    geography[native] = target
    rename_dims = {}
    rename_vars = {**facts["coordinates"], **geography}
    auxiliary = {}
    for native, target in dimensions.items():
        if native in horizontal:
            # Cropped geography may be 2-D; its retained index identifies the axis.
            index = f"{native}_source_native_index"
            actual = native if native in ds.dims else None
            if actual is None and index in ds:
                actual, = (dim for dim in ds[index].dims if dim != "time")
            if actual is None or actual not in ds.dims:
                continue
            rename_dims[actual] = target
            qualified = target != horizontal[native]
            source_coord = f"{target if qualified else native}_source_coordinate"
            if native in ds:
                if native in rename_vars:
                    auxiliary[source_coord] = ds[native].variable.copy(deep=False)
                else:
                    rename_vars[native] = source_coord
            stored_index = f"{target if qualified else native}_source_native_index"
            if index not in ds:
                auxiliary[stored_index] = xr.Variable(actual, np.arange(ds.sizes[actual]), {
                    "units": "1", "long_name": f"zero-based native source {native} index"})
            elif index != stored_index:
                rename_vars[index] = stored_index
        else:
            if native in ds.dims:
                rename_dims[native] = target
            if native in ds:
                rename_vars[native] = target
            index = f"{native}_source_native_index"
            if index in ds:
                rename_vars[index] = f"{target}_source_native_index"
            elif native in ds.dims:
                descriptor = next((
                    record["vertical"] for descriptor in
                    source["requests"]["binding"]["products"]["model_grid"].values()
                    for record in descriptor["records"]
                    if record["grid_id"] == grid_id and record.get("vertical")
                    and record["vertical"]["dimension"] == native), None)
                if descriptor:
                    auxiliary[f"{target}_source_native_index"] = xr.Variable(
                        native, descriptor["source_native_indices"], {"units": "1"})
    for name in ("grid_selected_latitude", "grid_selected_longitude",
                 "region_coverage_fraction", "x_box_km", "y_box_km", "x_box", "y_box"):
        if name in ds and name not in rename_vars:
            suffix = facts["suffix"]
            if len({v["horizontal_identity"] for v in layout.values()
                    if v["pair"] == facts["pair"]}) > 1:
                suffix += "_" + facts["horizontal_identity"]
            rename_vars[name] = name + suffix
    rename_vars = {n: target for n, target in rename_vars.items() if n in ds and n != target}
    for name in auxiliary.keys() | set(rename_vars.values()):
        if name in ds and name not in rename_vars:
            raise ValueError(f"Output coordinate collision: {name}")
    ds = ds.assign_coords(auxiliary)
    # Separate dimension renames from variables: geographic dimension-coordinates
    # remain geographic auxiliaries rather than being relabelled as indices.
    variables, coords = {}, {}
    for name, value in ds.variables.items():
        target = rename_vars.get(name, name)
        if target in variables or target in coords:
            raise ValueError(f"Output coordinate collision: {target}")
        variable = xr.Variable(tuple(rename_dims.get(d, d) for d in value.dims),
                               value.data, value.attrs, encoding=value.encoding)
        (coords if name in ds.coords else variables)[target] = variable
    ds = xr.Dataset(variables, coords=coords, attrs=ds.attrs)
    _rename_coordinate_links(ds, rename_vars)
    for dim in horizontal:
        target = dimensions[dim]
        if target in ds.dims:
            ds = ds.assign_coords({target: (target, np.arange(ds.sizes[target]), {
                "units": "1", "long_name": "local zero-based array position"})})
    ds.attrs["frameit_output_coordinates"] = {
        identity: {key: value[key] for key in (
            "native_grid_id", "dimensions", "geography", "original_coordinates")}
        for identity, value in layout.items()}
    for name in ds.data_vars:
        links = str(ds[name].encoding.get(
            "coordinates", ds[name].attrs.pop("coordinates", ""))).split()
        links.extend(n for n in geography.values()
                     if n in ds and set(ds[n].dims) <= set(ds[name].dims))
        ds[name].encoding["coordinates"] = " ".join(dict.fromkeys(links))
    return ds


def format_polar_output(dataset, job, *, layout):
    """Qualify completed vertical samples, never the polar target or calculations."""
    facts = _output_grid_facts(layout, job["grid_id"], job["name"])
    spatial = set(facts["horizontal"]) | set(facts["geography"])
    names = {**facts["dimensions"], **facts["coordinates"]}
    for native, target in facts["dimensions"].items():
        if native not in spatial:
            names[f"{native}_source_native_index"] = f"{target}_source_native_index"
    rename = {native: target for native, target in names.items()
              if native not in spatial and native != target
              and (native in dataset.variables or native in dataset.dims)}
    result = dataset.rename(rename)
    _rename_coordinate_links(result, rename)
    result.attrs["frameit_output_coordinates"] = {
        identity: {
            "native_grid_id": value["native_grid_id"],
            "dimensions": {native: target for native, target in value["dimensions"].items()
                           if native not in value["horizontal"]},
            "coordinates": {native: target for native, target in value["coordinates"].items()
                            if native not in value["geography"]},
        } for identity, value in layout.items()}
    return result


def _make_encoding(
    ds: xr.Dataset,
    compress_level: int = 1,
    compress_coords: bool = False,
    chunk_size: dict[str, int] | None = None,
) -> dict[str, dict[str, Any]]:
    enc: dict[str, dict[str, Any]] = {}
    for v in ds.data_vars:
        enc[v] = {"zlib": compress_level > 0, "complevel": int(compress_level), "shuffle": True}
    if compress_coords:
        for c in ds.coords:
            if ds[c].ndim >= 1:
                enc[c] = {"zlib": True, "complevel": int(compress_level), "shuffle": True}
    if chunk_size:
        for name, var in ds.variables.items():
            if var.ndim:
                enc.setdefault(name, {})["chunksizes"] = tuple(
                    min(ds.sizes[d], chunk_size.get(d, ds.sizes[d])) for d in var.dims)
    return enc


@dataclass
class ExportMetadata:
    simulation_id: str
    title: str
    summary: str
    institution: str
    source: str
    conventions: str = "CF-1.8"
    frameit_version: str = frameit_version
    user_metadata: dict[str, Any] = field(default_factory=dict)

    def base_attrs(self) -> dict[str, Any]:
        """
        Build the base CF global attribute dictionary.

        Returns
        -------
        dict[str, Any]
            Global attribute mapping ready to merge into ``ds.attrs``.
        """
        attrs = {
            "Conventions": self.conventions,
            "title": self.title,
            "summary": self.summary,
            "institution": self.institution,
            "source": self.source,
            "simulation_id": self.simulation_id,
            "frameit_version": self.frameit_version,
        }
        if self.user_metadata:
            attrs["frameit_user_metadata"] = self.user_metadata
        return attrs


def build_metadata_from_conf(
    conf: Any,
    *,
    frameit_version: str = frameit_version,
    institution: str,
) -> ExportMetadata:
    """
    Build an :class:`ExportMetadata` instance from a loaded configuration.

    Parameters
    ----------
    conf : object
        Configuration object (typically a :class:`SimulationConfig`).
        Accessed with ``getattr``; missing attributes fall back to "unknown".
    frameit_version : str, optional
        FrameIt version string to embed in metadata.  Defaults to the
        installed package version.
    institution : str
        Institution string to embed in the NetCDF global attributes.

    Returns
    -------
    ExportMetadata
        Populated metadata object ready to pass to :func:`write_dataset_netcdf`.
    """
    simu = str(getattr(conf, "simulation_name", "UNKNOWN_SIMU"))
    comment = str(getattr(conf, "comment", "")).strip()

    atm = str(getattr(conf, "atm_model", "unknown"))
    oce = str(getattr(conf, "ocean_model", "unknown"))
    wav = str(getattr(conf, "wave_model", "unknown"))
    ftype = str(getattr(conf, "file_type", "unknown"))
    trk = str(getattr(conf, "tracking_method", "unknown"))

    source = (
        f"file_type={ftype}; tracking_method={trk};"
        f" atm_model={atm}; ocean_model={oce}; wave_model={wav}"
    )

    title = f"FrameIt outputs for {simu}"
    summary = (
        comment
        if comment
        else "Cyclone-centric extraction and derived products generated by FrameIt."
    )

    meta = ExportMetadata(
        simulation_id=simu,
        title=title,
        summary=summary,
        institution=institution,
        source=source,
        frameit_version=frameit_version,
        user_metadata=getattr(conf, "yaml_config", {}).get("metadata", {}).get("extra", {}),
    )

    logger.debug(
        "Built metadata from conf: simulation_id=%s, institution=%s,"
        " conventions=%s, frameit_version=%s.",
        meta.simulation_id,
        meta.institution,
        meta.conventions,
        meta.frameit_version,
    )
    logger.debug("Metadata source string: %s", meta.source)
    return meta


def _prepare_dataset(ds, metadata, product_type, group=None, track_filename=None):
    """Keep metadata meaning and JSON attribute conventions identical across writers."""
    ds_out = ds.copy(deep=False)
    ds_out.attrs = _sanitize_attrs(ds_out.attrs)
    for name in ds_out.variables:
        ds_out[name].attrs = _sanitize_attrs(ds_out[name].attrs)
        original = ds_out[name].encoding
        keep = {"_FillValue", "units", "calendar", "coordinates", "grid_mapping"}
        if ds_out[name].dtype.kind in "Mm":
            keep.add("dtype")
        ds_out[name].encoding = {key: value for key, value in original.items() if key in keep}
        # A source fill code may equal a valid decoded floating value.
        if ds_out[name].dtype.kind == "f" and original.get("_FillValue") is not None:
            ds_out[name].encoding["_FillValue"] = np.nan
    ds_out.attrs.update(_sanitize_attrs(metadata.base_attrs()))
    ds_out.attrs["product_type"] = str(product_type)
    if group is not None:
        ds_out.attrs["group"] = str(group)
    if track_filename is not None:
        ds_out.attrs["track_filename"] = str(track_filename)
    return ds_out


def write_dataset_netcdf(
    ds: xr.Dataset,
    path: str | Path,
    *,
    metadata: ExportMetadata,
    product_type: str,
    group: str | None = None,
    track_filename: str | None = None,
    engine: str = "netcdf4",
    fmt: str = "NETCDF4",
    overwrite: bool = True,
    compress_level: int = 1,
    compress_coords: bool = False,
    unlimited_time: bool = True,
    chunk_size: dict[str, int] | None = None,
) -> Path:
    """
    Write a single xarray Dataset to a NetCDF file with CF-compliant metadata.

    Global attributes are taken from ``metadata.base_attrs()`` merged with
    ``product_type`` (and optionally ``group`` and ``track_filename``).
    All variable and coordinate attributes are sanitized to be NetCDF-compatible
    before writing.

    Parameters
    ----------
    ds : xr.Dataset
        Dataset to export.
    path : str or Path
        Destination file path.  Parent directory is created if absent.
    metadata : ExportMetadata
        Global CF-compliant attributes (title, institution, etc.).
    product_type : str
        Product category stored as a global attribute (e.g. "track", "polar").
    group : str or None, optional
        Vertical group name stored as a global attribute. Default None.
    track_filename : str or None, optional
        Name of the associated track file stored as a global attribute.
        Default None.
    engine : str, optional
        NetCDF writing engine passed to ``xr.Dataset.to_netcdf``. Default "netcdf4".
    fmt : str, optional
        NetCDF format string (e.g. "NETCDF4"). Default "NETCDF4".
    overwrite : bool, optional
        If False, raise :exc:`FileExistsError` when the destination exists.
        Default True.
    compress_level : int, optional
        zlib compression level (0–9). Default 1.
    compress_coords : bool, optional
        Apply compression to coordinate variables as well. Default False.
    unlimited_time : bool, optional
        Declare the "time" dimension unlimited. Default True.

    Returns
    -------
    Path
        Path to the written NetCDF file.

    Raises
    ------
    FileExistsError
        If ``path`` already exists and ``overwrite=False``.
    """
    from frameit.io.zarr_export import validate_zarr_sizes

    validate_zarr_sizes(chunk_size or {}, {})
    unknown = set(chunk_size or {}) - set(ds.dims)
    if unknown:
        raise ValueError(f"Unknown output chunk dimensions: {sorted(unknown)}")
    if engine not in {"netcdf4", "h5netcdf"} or fmt != "NETCDF4":
        raise ValueError("NetCDF output requires netcdf4 or h5netcdf and NETCDF4 format")
    if type(compress_level) is not int or not 0 <= compress_level <= 9:
        raise ValueError("compress_level must be an integer in [0, 9]")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not overwrite:
        logger.error("Refusing to overwrite existing file (overwrite=False): %s", str(path))
        raise FileExistsError(f"File exists and overwrite=False: {path}")

    logger.debug(
        "Writing NetCDF: %s (product_type=%s, group=%s, engine=%s, fmt=%s,"
        " compress_level=%s, compress_coords=%s, unlimited_time=%s).",
        str(path),
        str(product_type),
        str(group) if group is not None else None,
        engine,
        fmt,
        int(compress_level),
        bool(compress_coords),
        bool(unlimited_time),
    )

    ds_out = _prepare_dataset(ds, metadata, product_type, group, track_filename)

    ds_out = _append_history(ds_out, f"{_utc_now_iso()}: written by frameit io.netcdf_export")

    encoding = _make_encoding(
        ds_out, compress_level=compress_level, compress_coords=compress_coords,
        chunk_size=chunk_size,
    )
    unlimited_dims = ["time"] if (unlimited_time and ("time" in ds_out.dims)) else None

    logger.debug("NetCDF dims: %s", dict(ds_out.sizes))
    logger.debug(
        "NetCDF vars: n_data_vars=%s, n_coords=%s.", len(ds_out.data_vars), len(ds_out.coords)
    )
    if unlimited_dims is not None:
        logger.debug("Unlimited dims: %s", unlimited_dims)

    with atomic_output(path, overwrite=overwrite) as temporary:
        ds_out.to_netcdf(
            temporary,
            mode="w",
            engine=engine,
            format=fmt,
            encoding=encoding,
            unlimited_dims=unlimited_dims,
        )

    logger.debug("NetCDF written: %s", str(path))
    return path


def _write_dataset(ds, path, *, engine, zarr_chunk_size=None, zarr_shard_size=None, **kwargs):
    if engine == "zarr":
        from frameit.io.zarr_export import write_dataset_zarr

        kwargs.pop("fmt", None)
        kwargs.pop("unlimited_time", None)
        return write_dataset_zarr(ds, path, chunk_size=zarr_chunk_size,
                                  shard_size=zarr_shard_size, **kwargs)
    return write_dataset_netcdf(ds, path, engine=engine, **kwargs)


def _write_single_group(args: tuple) -> Path:
    """
    Worker function for ProcessPoolExecutor — must be a top-level callable.
    Unpacks all arguments and calls the selected dataset writer.
    """
    (
        group,
        ds,
        out_path,
        grid,
        metadata,
        track_filename,
        engine,
        fmt,
        overwrite,
        compress_level,
        compress_coords,
        unlimited_time,
        zarr_chunk_size,
        zarr_shard_size,
    ) = args

    return _write_dataset(
        ds,
        out_path,
        metadata=metadata,
        product_type=grid,
        group=str(group),
        track_filename=track_filename,
        engine=engine,
        fmt=fmt,
        overwrite=overwrite,
        compress_level=compress_level,
        compress_coords=compress_coords,
        unlimited_time=unlimited_time,
        zarr_chunk_size=zarr_chunk_size,
        zarr_shard_size=zarr_shard_size,
    )


def _export_pool(group_count, max_workers, dask_scheduler, dask_workers, native_threads):
    from frameit.core.runtime import (
        cpu_budget,
        current_execution_resources,
        initialize_export_worker,
    )

    cpus, _ = cpu_budget()
    active = current_execution_resources()
    if active is not None:
        cpus = min(cpus, active["cpu_budget"])
    per_process = (1 if dask_scheduler == "synchronous" else dask_workers) * native_threads
    if per_process > cpus:
        raise ValueError("Export thread counts exceed CPU budget")
    workers = min(max_workers or cpus // per_process, group_count, cpus // per_process)
    return ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
        initializer=initialize_export_worker,
        initargs=(dask_scheduler, dask_workers, native_threads),
    )


def _write_product(item, dataset, destination, options):
    """Publish one v3 product and return only its actual reopened field/encoding facts."""
    source, product = item["source"], item["product"]
    engine = options["engine"]
    path = _write_dataset(dataset, destination, **options)
    fields = {name: {
        "source": source, "path": item["path"], "stored_name": name,
        "dimensions": list(dataset[name].dims), "units": dataset[name].attrs.get("units"),
        "representation": item["representation"],
    } for name in item["fields"]}
    encoding = {
        "format": "zarr3" if engine == "zarr" else "netcdf4", "engine": engine,
        "compression": {"level": options["compress_level"],
                        "coordinates": options["compress_coords"]},
        "chunks": {}, "shards": {},
        "publication": ("complete-directory replacement has a visibility gap"
                        if engine == "zarr" else "atomic file publication; no append/resume"),
    }
    if engine == "zarr":
        import zarr

        stored = zarr.open_group(path, mode="r")
        for name in dataset.variables:
            encoding["chunks"][name] = list(stored[name].chunks)
            encoding["shards"][name] = list(stored[name].shards or ())
        encoding["reader_requirements"] = "Zarr v3 with sharding_indexed codec"
    else:
        with xr.open_dataset(path, engine=engine, decode_times=False) as saved:
            encoding["unlimited_time"] = "time" in saved.encoding.get("unlimited_dims", ())
            encoding["chunks"] = {
                name: list(value.encoding.get("chunksizes") or ())
                for name, value in saved.variables.items()}
        encoding["reader_requirements"] = "NetCDF4/HDF5 reader"
    return {
        **item, "role": product, "group": None, "path": str(path.resolve()),
        "fields": fields,
        "dimensions": {name: value["dimensions"] for name, value in fields.items()},
        "units": {name: value["units"] for name, value in fields.items()},
        "stored_names": {name: name for name in fields}, "encoding": encoding,
    }


def write_group_dict(
    ds_dict: Mapping[str, xr.Dataset],
    out_dir: str | Path,
    *,
    simu_name: str,
    grid: str,  # "polar" or "cart"
    metadata: ExportMetadata,
    track_filename: str,
    engine: str = "netcdf4",
    fmt: str = "NETCDF4",
    overwrite: bool = True,
    compress_level: int = 1,
    compress_coords: bool = False,
    unlimited_time: bool = True,
    max_workers: int | None = None,
    synchronous: bool = False,
    dask_scheduler: str = "threads",
    dask_workers: int = 1,
    native_threads: int = 1,
    zarr_chunk_size: dict[str, int] | None = None,
    zarr_shard_size: dict[str, int] | None = None,
    _executor: ProcessPoolExecutor | None = None,
) -> list[Path]:
    """
    Write grouped products as NetCDF files or Zarr stores, optionally in parallel.

    Each group produces ``{simu_name}.{grid}.{group}.nc`` or ``.zarr`` inside ``out_dir``.

    Parameters
    ----------
    ds_dict : Mapping[str, xr.Dataset]
        Group datasets to export, keyed by group name.
    out_dir : str or Path
        Output directory.  Created if absent.
    simu_name : str
        Simulation identifier used as the file name prefix.
    grid : str
        Grid type label used in the file name (e.g. "polar" or "cart").
    metadata : ExportMetadata
        Global CF-compliant attributes forwarded to each file.
    track_filename : str
        Name of the associated track file stored as a global attribute.
    engine : str, optional
        NetCDF writing engine. Default "netcdf4".
    fmt : str, optional
        NetCDF format string. Default "NETCDF4".
    overwrite : bool, optional
        Overwrite existing files. Default True.
    compress_level : int, optional
        zlib compression level (0–9). Default 1.
    compress_coords : bool, optional
        Apply compression to coordinate variables. Default False.
    unlimited_time : bool, optional
        Declare the "time" dimension unlimited. Default True.
    max_workers : int or None, optional
        Maximum parallel worker processes, also capped by group count and CPU
        budget. Default None resolves from the allocation/affinity.

    Returns
    -------
    list[Path]
        Paths to the written NetCDF files (order reflects completion order).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.debug(
        "Writing group dictionary: out_dir=%s, simu_name=%s, grid=%s, n_groups=%s, max_workers=%s.",
        str(out_dir),
        simu_name,
        grid,
        len(ds_dict),
        max_workers,
    )

    # Build the list of argument tuples for each worker
    tasks_args = []
    destinations = set()
    for group, ds in ds_dict.items():
        group_token = _sanitize_filename_token(str(group))
        suffix = ".zarr" if engine == "zarr" else ".nc"
        fn = f"{simu_name}.{grid}.{group_token}{suffix}"
        out_path = out_dir / fn
        if out_path in destinations:
            kind = "Zarr" if engine == "zarr" else "NetCDF"
            raise ValueError(f"Group names map to the same {kind} destination: {out_path}")
        destinations.add(out_path)

        logger.debug(
            "Queuing group=%s -> %s (vars=%s, dims=%s).",
            str(group),
            str(out_path),
            len(ds.data_vars),
            dict(ds.sizes),
        )

        tasks_args.append(
            (
                group,
                ds,
                out_path,
                grid,
                metadata,
                track_filename,
                engine,
                fmt,
                overwrite,
                compress_level,
                compress_coords,
                unlimited_time,
                zarr_chunk_size,
                zarr_shard_size,
            )
        )

    if synchronous:
        # A matrix case already runs in an isolated worker. Do not create a
        # nested process pool, even a one-worker pool, for group serialization.
        return [_write_single_group(args) for args in tasks_args]

    written: list[Path] = []
    if not tasks_args:
        return written
    pool = nullcontext(_executor) if _executor is not None else _export_pool(
        len(tasks_args), max_workers, dask_scheduler, dask_workers, native_threads)
    with pool as executor:
        futures = {
            executor.submit(_write_single_group, args): args[0]  # args[0] = group name
            for args in tasks_args
        }
        for future in as_completed(futures):
            group_name = futures[future]
            try:
                path = future.result()
                written.append(path)
                logger.debug("NetCDF written: %s", path)
            except Exception:
                logger.exception("Failed to write group=%s.", group_name)
                raise

    logger.debug("Group dictionary written: n_files=%s.", len(written))
    return written


def export_outputs(
    runner: Any,
    *,
    frameit_version: str = frameit_version,
    institution: str,
    out_dir: Path | None = None,
    out_subdir: str = "",
    export_polar: bool = True,
    export_cart: bool = True,
    engine: str = "netcdf4",
    fmt: str = "NETCDF4",
    overwrite: bool = True,
    compress_level: int = 1,
    compress_coords: bool = False,
    unlimited_time: bool = True,
    max_workers: int | None = None,
    synchronous: bool = False,
    dask_scheduler: str = "threads",
    dask_workers: int = 1,
    native_threads: int = 1,
    zarr_chunk_size: dict[str, int] | None = None,
    zarr_shard_size: dict[str, int] | None = None,
    netcdf_chunk_size: dict[str, int] | None = None,
    on_published: Callable[[dict], None] | None = None,
) -> dict[str, Path | list[Path]]:
    """
    Export all FrameIt products using the selected NetCDF or Zarr engine.

    The track file is always written.  Polar and Cartesian exports are
    conditional on the corresponding flag and on data being available.

    Parameters
    ----------
    runner : FrameitRunner
        A runner instance on which :meth:`~FrameitRunner.run` has already been
        called.
    frameit_version : str, optional
        Version string embedded in global NetCDF attributes.  Defaults to the
        installed package version.
    institution : str
        Institution string stored in global NetCDF attributes.
    out_dir : Path or None, optional
        Root output directory.  Falls back to ``runner.output_dir`` when None.
    out_subdir : str, optional
        Sub-directory appended inside ``out_dir/products``. Default "".
    export_polar : bool, optional
        Write polar-projection datasets when available. Default True.
    export_cart : bool, optional
        Write Cartesian (box) datasets when available. Default True.
    engine : str, optional
        NetCDF writing engine. Default "netcdf4".
    fmt : str, optional
        NetCDF format string. Default "NETCDF4".
    overwrite : bool, optional
        Overwrite existing output files. Default True.
    compress_level : int, optional
        zlib compression level (0–9). Default 1.
    compress_coords : bool, optional
        Apply compression to coordinate variables. Default False.
    unlimited_time : bool, optional
        Declare the "time" dimension unlimited. Default True.
    max_workers : int or None, optional
        Maximum parallel workers for group export. Default None.
    on_published : callable or None, optional
        Parent-only v3 checkpoint after each complete atomic publication.
        Callback failures propagate; they do not undo published products.

    Returns
    -------
    dict[str, Path or list[Path]]
        Keys present depend on what was exported:

        - ``"track"``: Path to the track file.
        - ``"polar"``: list of Path for polar files (if exported).
        - ``"cart"``:  list of Path for Cartesian files (if exported).
    """
    conf = runner.conf
    simu_name = str(getattr(conf, "simulation_name", "UNKNOWN_SIMU"))

    from frameit.utils.output_paths import OutputPaths

    root = Path(out_dir) if out_dir is not None else Path(runner.output_dir)
    base_out = OutputPaths(root).products
    out_path = base_out / out_subdir if out_subdir else base_out
    out_path.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting products: engine=%s, compression=%d", engine, int(compress_level))
    logger.debug(
        "Export outputs: simu_name=%s, out_path=%s, export_polar=%s, export_cart=%s,"
        " engine=%s, fmt=%s, overwrite=%s, compress_level=%s, max_workers=%s.",
        simu_name,
        str(out_path),
        bool(export_polar),
        bool(export_cart),
        engine,
        fmt,
        bool(overwrite),
        int(compress_level),
        max_workers,
    )

    meta = build_metadata_from_conf(conf, frameit_version=frameit_version, institution=institution)

    if getattr(conf, "schema_version", None) == 3:
        from frameit.io.zarr_export import validate_zarr_sizes

        results = {}
        runner.published_products = []
        planned = [item for item in conf.simulation_parameter["request_plan"]["products"]
                   if (item["product"] != "model_grid" or export_cart)
                   and (item["product"] != "polar" or export_polar)]
        if not planned:
            return results
        destinations = OutputPaths(root).planned_products(planned)
        field_datasets = [runner.field_products[(item["source"], item["product"])]
                          for item in planned if item["product"] != "track"]
        sizes = (zarr_chunk_size or {}) if engine == "zarr" else (netcdf_chunk_size or {})
        validate_zarr_sizes(sizes, zarr_shard_size or {})
        unknown = (set(sizes) | set(zarr_shard_size or {})) - {
            dim for dataset in field_datasets or [runner.track] for dim in dataset.dims}
        if unknown:
            raise ValueError(f"Unknown output writer dimensions: {sorted(unknown)}")
        for item, destination in zip(planned, destinations, strict=True):
            if destination.exists() and not overwrite:
                raise FileExistsError(f"File exists and overwrite=False: {destination}")
            if destination.exists() and overwrite:
                try:
                    if destination.is_dir():
                        header = json.loads((destination / "zarr.json").read_text())
                        attrs = header.get("attributes", {}) if isinstance(header, dict) else {}
                    else:
                        with xr.open_dataset(destination, decode_times=False) as existing:
                            attrs = existing.attrs
                    owned = (isinstance(attrs, Mapping)
                             and attrs.get("simulation_id") == simu_name
                             and attrs.get("product_type") == item["product"]
                             and attrs.get("frameit_version")
                             and (item["source"] is None or
                                  attrs.get("source_id") == item["source"]))
                except (OSError, ValueError):
                    owned = False
                if not owned:
                    raise ValueError(f"Refusing to replace an unrelated product: {destination}")
        tasks = []
        for item, destination in zip(planned, destinations, strict=True):
            source, product = item["source"], item["product"]
            dataset = (runner.track.rename(lat="latitude", lon="longitude")
                       if product == "track" else runner.field_products[(source, product)])
            if product == "track":
                dataset = dataset.copy(deep=False)
                for name, units in (("latitude", "degrees_north"), ("longitude", "degrees_east")):
                    dataset[name].attrs = dict(dataset[name].attrs, standard_name=name, units=units)
                dataset.time.encoding = dict(dataset.time.encoding,
                    units="seconds since 1970-01-01", calendar=dataset.time.encoding.get(
                        "calendar", "proleptic_gregorian"))
            writer = {
                "metadata": meta, "product_type": product,
                "engine": "netcdf4" if product == "track" and engine == "zarr" else engine,
                "fmt": fmt, "overwrite": overwrite, "compress_level": compress_level,
                "compress_coords": compress_coords, "unlimited_time": unlimited_time,
                "zarr_chunk_size": {d: s for d, s in (zarr_chunk_size or {}).items()
                                    if d in dataset.dims},
                "zarr_shard_size": {d: s for d, s in (zarr_shard_size or {}).items()
                                    if d in dataset.dims},
            }
            if engine != "zarr":
                writer["chunk_size"] = {d: s for d, s in (netcdf_chunk_size or {}).items()
                                        if d in dataset.dims}
            tasks.append((item, dataset, destination, writer))

        def published(facts):
            # A signal or callback failure can leave retention complete but handling unfinished.
            if any(item["path"] == facts["path"] for item in runner.published_products):
                return
            runner.published_products.append(facts)
            results.setdefault(facts["role"], []).append(Path(facts["path"]))
            if on_published is not None:
                on_published(facts)

        if synchronous:
            for args in tasks:
                published(_write_product(*args))
        elif tasks:
            with _export_pool(len(tasks), max_workers, dask_scheduler,
                              dask_workers, native_threads) as executor:
                futures = []
                failure = None
                try:
                    for args in tasks:
                        futures.append(executor.submit(_write_product, *args))
                    for future in as_completed(futures):
                        try:
                            published(future.result())
                        except BaseException as exc:
                            if failure is None:
                                failure = exc
                except BaseException as exc:
                    failure = exc
                finally:
                    # Graceful interruption still waits for workers; inventory their actual results.
                    for future in futures:
                        try:
                            published(future.result())
                        except BaseException as exc:
                            if failure is None:
                                failure = exc
                if failure is not None:
                    raise failure
        return results

    # Track
    suffix = ".zarr" if engine == "zarr" else ".nc"
    track_file = out_path / f"{simu_name}.track{suffix}"
    logger.debug("Exporting track to %s", track_file)

    track_written = _write_dataset(
        runner.track,
        track_file,
        metadata=meta,
        product_type="track",
        engine=engine,
        fmt=fmt,
        overwrite=overwrite,
        compress_level=compress_level,
        compress_coords=compress_coords,
        unlimited_time=unlimited_time,
        zarr_chunk_size=zarr_chunk_size,
        zarr_shard_size=zarr_shard_size,
    )

    results: dict[str, Path | list[Path]] = {"track": track_written}

    groups = {}
    for grid, enabled, attribute in (("polar", export_polar, "dict_polar_user"),
                                      ("cart", export_cart, "dict_crop_user")):
        datasets = getattr(runner, attribute, None)
        if enabled and datasets:
            groups[grid] = datasets
        else:
            logger.debug("%s export skipped (enabled=%s, data present=%s).",
                         grid, bool(enabled), bool(datasets))
    pool = (_export_pool(max(map(len, groups.values())), max_workers,
                         dask_scheduler, dask_workers, native_threads)
            if groups and not synchronous else nullcontext(None))
    # Share native-safe workers across phases, retaining serial phase ordering.
    with pool as executor:
        for grid, datasets in groups.items():
            logger.info("  %s: %d group(s)", grid, len(datasets))
            results[grid] = write_group_dict(
                datasets, out_path, simu_name=simu_name, grid=grid, metadata=meta,
                track_filename=track_written.name, engine=engine, fmt=fmt,
                overwrite=overwrite, compress_level=compress_level, compress_coords=compress_coords,
                unlimited_time=unlimited_time, max_workers=max_workers, synchronous=synchronous,
                dask_scheduler=dask_scheduler, dask_workers=dask_workers, native_threads=native_threads,
                zarr_chunk_size=zarr_chunk_size, zarr_shard_size=zarr_shard_size, _executor=executor,
            )

    for role, paths in results.items():
        for path in ([paths] if isinstance(paths, Path) else paths):
            logger.info("  Saved %s: %s", role, path.name)
    return results
