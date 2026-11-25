"""Portable identity of an extraction attempt, without claiming payload equality."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date
from math import isfinite
from pathlib import Path

PROJECTION_VERSION = 1
CONTEXT_VERSION = 1


def _portable(value):
    if isinstance(value, dict):
        return {str(key): _portable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if type(value) in (str, int, bool) or value is None:
        return value
    if isinstance(value, float):
        return float(value) if isfinite(value) else str(value)
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "tolist") and getattr(value, "dtype", None) is not None:
        # Avoid datetime64[ns].tolist() returning integer epoch ticks.
        if value.ndim == 0 and value.dtype.kind in "Mm":
            return str(value)
        return _portable(value.tolist())
    return str(value)


def content_digest(value):
    return hashlib.sha256(json.dumps(_portable(value), sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("ascii")).hexdigest()


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def project_base_request(authored, *, base_dir, version=PROJECTION_VERSION):
    """Do not run current defaults, source discovery or symlink resolution."""
    if type(version) is not int or version != PROJECTION_VERSION:
        raise ValueError(f"Unsupported scientific request projection version: {version!r}")
    base_dir = Path(base_dir).absolute()
    result = deepcopy({key: value for key, value in authored.items()
                       if key not in {"diagnostics", "logging", "resources", "metadata"}})

    def absolute(value):
        return str(base_dir / value)

    for source in result.get("sources", {}).values():
        for key in ("files", "exclude"):
            if key in source:
                paths = source[key]
                source[key] = (absolute(paths) if isinstance(paths, str)
                               else [absolute(path) for path in paths])
        reader = source.get("reader", {})
        if "python_executable" in reader:
            reader["python_executable"] = absolute(reader["python_executable"])
    region = result.get("region", {})
    if "file" in region.get("track", {}):
        region["track"]["file"] = absolute(region["track"]["file"])
    if "weights_file" in region.get("tracker", {}):
        region["tracker"]["weights_file"] = absolute(region["tracker"]["weights_file"])
    for section, operational in (
        ("run", {"description"}), ("output", {"directory", "overwrite", "writer"}),
    ):
        if section in result:
            kept = {key: value for key, value in result[section].items() if key not in operational}
            if kept:
                result[section] = kept
            else:
                del result[section]
    return _portable(result)


def build_context(request, effective):
    base = request["path_bases"].get("configuration_directory") or Path.cwd()
    authored = request.get("authored_configuration")
    projections = {
        "authored": project_base_request(authored, base_dir=base) if authored is not None else None,
        "effective": project_base_request(effective, base_dir=base),
    }
    summary = {"context_version": CONTEXT_VERSION, "projection_version": PROJECTION_VERSION,
               **{f"{key}_sha256": content_digest(value) for key, value in projections.items()}}
    return summary, {**summary, **projections}


def freeze_source_inventory(source):
    """Capture the selected providers and clocks, not their archive-wide grid graphs."""
    from frameit.processing.requests import native_field_group, source_field_metadata

    by_path = {entry["path"]: entry for entry in source["file_inventory"]}
    files = [{key: by_path[path][key] for key in ("path", "aliases", "identity")}
             for path in source["files"]]
    indexes = {entry["path"]: index for index, entry in enumerate(files)}
    samples, definitions = {}, {}
    for record in source["records"]:
        locator = record["locator"]
        index = indexes.get(locator["path"])
        if index is None:
            continue
        sample = {key: record.get(key) for key in (
            "time", "calendar", "cycle", "reference_calendar", "cycle_calendar",
            "clock", "time_bounds", "native_axes")}
        sample.update(file_index=index, indexers=locator.get("coordinate_indexers", {}))
        sample = _portable(sample)
        samples.setdefault(content_digest(sample), sample)
        field = source["fields"][record["field_id"]]
        if not field["name"]:
            continue
        metadata = record.get("field_metadata")
        if metadata is None and source["format"] != "fa":
            metadata = source_field_metadata(source, field, record=record)
        metadata = metadata or {"attributes": field["attributes"], "origins": {}}
        definition = _portable({
            "name": field["name"], "file_index": index, "native_id": record["field_id"],
            "group": native_field_group(source, field, record), "metadata": metadata,
        })
        key = content_digest(definition)
        entry = definitions.setdefault(key, {**definition, "samples": []})
        sample_index = {"time": sample["time"], "cycle": sample["cycle"],
                        "indexers": sample["indexers"], "native_axes": sample["native_axes"]}
        if not entry["samples"] or entry["samples"][-1] != sample_index:
            entry["samples"].append(sample_index)
    return {"version": 1, "format": source["format"], "physical_type": source["physical_type"],
            "model": source["model"], "profile": source.get("profile"),
            "files": files, "samples": list(samples.values()),
            "fields": list(definitions.values())}


def _netcdf_structure(ds):
    return content_digest({
        "dimensions": dict(ds.sizes), "attributes": ds.attrs,
        "variables": {name: {"dimensions": value.dims, "dtype": str(value.dtype),
                             "attributes": value.attrs}
                      for name, value in ds.variables.items()},
    })


def product_identity(path, *, representation, header=None, engine=None):
    """Metadata fingerprints; no payload reads or claims of content verification."""
    path = Path(path)
    if representation == "zarr3":
        root = path / "zarr.json"
        documents = [root, *(item / "zarr.json" for item in path.iterdir() if item.is_dir())]
        if any(doc.is_symlink() or doc.parent.is_symlink() for doc in documents):
            raise ValueError(f"Unsafe Zarr metadata in {path}")
        return {"version": 1, "strategy": "zarr_v3_metadata_documents",
                "structure_sha256": content_digest({
                    str(doc.relative_to(path)): file_sha256(doc) for doc in documents})}
    if representation != "netcdf4":
        raise ValueError(f"Unsupported product identity representation: {representation!r}")
    stat = path.stat()
    if header is None:
        import xarray as xr

        with xr.open_dataset(path, engine=engine, decode_cf=False, create_default_indexes=False,
                             cache=False) as saved:
            signature = _netcdf_structure(saved)
    else:
        signature = _netcdf_structure(header)
    return {"version": 1, "strategy": "netcdf_stat_and_header",
            "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "structure_sha256": signature}
