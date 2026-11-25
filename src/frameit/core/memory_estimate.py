"""Advisory RSS budgets from a validated request, without building data graphs."""

from collections import defaultdict
from math import gcd, prod

import numpy as np

MIB = 1024**2
GIB = 1024**3


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    return (ordered[(n - 1) // 2] + ordered[n // 2]) // 2 if n else 0


def _block(sizes, chunks):
    return prod(min(size, limit) if (limit := chunks.get(dim, -1)) > 0 else size
                for dim, size in sizes.items())


def _sizes(grid):
    sizes = {dim: int(size) for dim, size in grid["dimensions"].items()}
    if any(size < 1 for size in sizes.values()):
        raise ValueError("A bound grid has an empty dimension.")
    return sizes


def _width(source, record):
    if source["format"] in {"grib", "fa"}:
        return 8  # Both native readers expose float64 payloads.
    field = source["fields"][record["field_id"]]
    dtype = record.get("decoded_dtype") or field.get("dtype")
    if not dtype or (decoded := np.dtype(dtype)).hasobject or not decoded.itemsize:
        raise ValueError(f"{field['name']}: decoded element size is not known.")
    return decoded.itemsize


def _record_key(record):
    return (record["field_id"], record["locator"]["path"], record["time"], record["level"],
            tuple(sorted(record.get("native_axes", {}).items())))


def _input_work(source, reader_chunks):
    binding = source["field_binding"]
    native, fmt = source["native_grids"], source["format"]
    selected_depth = defaultdict(dict)
    if fmt == "netcdf":
        for descriptors in (*binding["products"].values(), binding["dependencies"]):
            for descriptor in descriptors.values():
                if descriptor.get("operation"):
                    continue
                for record in descriptor["records"]:
                    if record.get("vertical"):
                        dim = record["vertical"]["dimension"]
                        depths = selected_depth[_record_key(record)]
                        depths[dim] = max(depths.get(dim, 0), len(record["source_positions"]))
    blocks, largest_record, tiles = [], 0, 0
    support = source.get("tracker_support", {})
    tracker_fields = set(support.get("inputs", {}))
    tracker_times = {item["source_time"] for item in source.get(
        "region", {}).get("associations", ())}
    per_time, planes = defaultdict(int), defaultdict(int)
    for record in binding["records"]:
        grid = native[record["grid_id"]]
        sizes = _sizes(grid)
        width = _width(source, record)
        if fmt == "fa":
            # The selected FA zone can be smaller than the record decoded by the helper.
            y, x = grid["fa_geometry"]["fa_native_shape"]
            cells = int(y) * int(x)
        elif fmt == "grib":
            cells = prod(sizes.values())
        else:
            sizes.update(selected_depth.get(_record_key(record), {}))
            cells = _block(sizes, reader_chunks)
        block = cells * width
        blocks.append(block)
        tiles += (prod((size + chunk - 1) // chunk
                       for dim, size in sizes.items()
                       if (chunk := reader_chunks.get(dim, -1)) > 0) if fmt == "netcdf" else 1)
        if fmt != "netcdf":
            largest_record = max(largest_record, block)
        stamp = record["time"]
        if record["name"] in tracker_fields and (not tracker_times or stamp in tracker_times):
            per_time[stamp] += prod(sizes.values()) * max(width, 8)
            # Centroid/vortex methods may retain reduced horizontal planes across times.
            for coord in grid["coordinates"].values():
                if coord["values"].ndim == 2:
                    planes[stamp] = max(planes[stamp], int(coord["values"].size))
    retained_tracker = (sum(planes.values()) * 5 * 8
                        if support.get("method") in {"pressure_centroid", "multifield_vortex"}
                        else 0)
    return {
        "selected_records": len(blocks), "estimated_input_tiles": tiles,
        "largest_input_block_bytes": max(blocks, default=0),
        "typical_input_block_bytes": _median(blocks),
        "largest_eager_native_record_bytes": largest_record,
        "tracker_largest_sample_bytes": max(per_time.values(), default=0),
        "tracker_typical_sample_bytes": _median(per_time.values()),
        "tracker_retained_plane_bytes": retained_tracker,
    }


def _geometry_size(source):
    """Count already-materialized coordinate arrays, not any selected field values."""
    seen, retained, largest = set(), 0, 0
    binding = source["field_binding"]
    jobs = binding.get("operation_plans", ())
    grids = (*source["native_grids"].values(), *source.get("representation_grids", {}).values(),
             *(job["grid"] for job in jobs), *(job["geometry"] for job in jobs))
    for grid in grids:
        values = [coord["values"] for coord in grid["coordinates"].values()]
        largest = max(largest, sum(int(value.nbytes) for value in values))
        for value in values:
            if id(value) not in seen:
                retained += int(value.nbytes)
                seen.add(id(value))
    for job in jobs:
        if geometry := job.get("polar_geometry"):
            for value in (geometry["longitude"], geometry["latitude"]):
                if id(value) not in seen:
                    retained += int(value.nbytes)
                    seen.add(id(value))
    return retained, largest


def _writer_block(sizes, spatial, width, output, chunks, shards):
    if output == "zarr":
        storage = {}
        for dim, size in sizes.items():
            default = min(size, 128) if dim in spatial else 1
            chunk = chunks.get(dim, gcd(default, shards[dim]) if dim in shards else default)
            storage[dim] = shards.get(dim, chunk * (8 if dim == "time" else 4 if dim in spatial
                                                    else 1))
    else:
        # Explicit HDF5 encodings use full extents for dimensions not listed.
        storage = chunks or {"time": 1}
    return width * _block(sizes, storage)


def _axis_sizes(records):
    values = defaultdict(set)
    for record in records:
        for dim, value in record.get("native_axes", {}).items():
            values[dim].add(value)
    return {dim: len(coords) for dim, coords in values.items()}


def _product_work(product, source, facts, layout):
    from frameit.io.netcdf_export import _output_grid_facts

    kind, source_id = product["product"], product["source"]
    output = facts["configuration"]["output"]["format"]
    if kind == "track":
        times = max((len(s["selected_times"]) for s in facts["sources"].values()), default=1)
        return {"largest_writer_block_bytes": 16 * 8, "resident_product_bytes": times * 16 * 8,
                "largest_processing_block_bytes": 0}
    binding = source["field_binding"]
    native_axes = {name: _axis_sizes(item["records"])
                   for name, item in binding["products"][kind].items()}
    key = f"{source_id}.{kind}"
    chunks = facts["layouts"]["writer"]["chunks"].get(key, {})
    shards = facts["layouts"]["writer"]["shards"].get(key, {})
    largest, processing_block, resident = 0, 0, 0
    if kind == "polar":
        polar = binding["polar_plan"]
        radii, angles = len(polar["radius_km"]), len(polar["azimuth_degrees"])
        times = set(polar["source_times"])
        processing_chunks = facts["layouts"]["products"][key]["applied_settings"]
        jobs = [job for job in binding["operation_plans"] if job["product"] == "polar"]
        signatures = {(job["grid_id"], job["context"][0], job["method"])
                      for job in jobs if job["context"][0] in times}
        # Target coordinates and interpolation/coverage weights can stay in the lazy graphs
        # after a method's LRU evicts a plan. Do not use cache size as a graph memory cap.
        resident = radii * angles * (32 * len(times) + 128 * len(signatures))
        for job in jobs:
            shape = _sizes(job["grid"])
            if vertical := job["vertical"]:
                shape[vertical["dimension"]] = len(vertical["positions"])
            # Execution joins the cropped stencil plane into a block. Its exact window needs
            # the interpolation weights, so budget the full prepared source extent per sample.
            stencil = 8 * _block(shape, {"time": 1})
            for dim in job["polar_geometry"]["horizontal_dimensions"].values():
                shape.pop(dim, None)
            axes = _output_grid_facts(layout, job["grid_id"], job["name"])["dimensions"]
            shape = {axes.get(dim, dim): size for dim, size in shape.items()}
            spatial = {"radius", "azimuth"}
            shape.update(time=len(times), radius=radii, azimuth=angles)
            # Sampling builds whole azimuth rings; final write chunks may be smaller.
            rings = processing_chunks.get("radius", min(32, radii))
            rings_block = 24 * _block(shape, {
                **processing_chunks, "time": 1, "radius": rings, "azimuth": -1})
            processing_block = max(processing_block, stencil + rings_block)
            shape.update({axes.get(dim, dim): size
                          for dim, size in native_axes[job["name"]].items()})
            largest = max(largest, _writer_block(shape, spatial, 24, output, chunks, shards))
    else:
        width_km = facts["configuration"].get("region", {}).get("width_km")
        for name in product["fields"]:
            descriptor = binding["products"][kind][name]
            records = descriptor["records"]
            dims = product["dimensions"][name]
            if dims is None or not records:
                raise ValueError(f"{source_id}.{name}: output shape is not bound.")
            times = len({r["time"] for r in records})
            associated = source.get("region", {}).get("associations", ())
            if width_km and associated:
                times = len({item["source_time"] for item in associated})
            if any(gap["field"] == name for gap in source.get("allowed_gaps", ())):
                times = max(times, len(source["selected_times"]))
            for record in records:
                grid_id = record["selection_grid_id"]
                grid = (source["native_grids"].get(grid_id)
                        or source["representation_grids"][grid_id])
                shape = _sizes(grid)
                if vertical := record["vertical"]:
                    shape[vertical["dimension"]] = len(vertical["positions"])
                shape.update(native_axes[name])
                axes = _output_grid_facts(layout, grid_id, name if descriptor.get("operation")
                                          else record["name"])
                shape = {axes["dimensions"].get(dim, dim): size for dim, size in shape.items()}
                shape["time"] = times
                spatial = set(axes["horizontal"].values())
                if width_km and spatial:
                    region = source["region"]["grids"][grid_id]
                    spacing_km = region["geometry"]["effective_spacing_m"] / 1000
                    for axis, dim in zip(("x", "y"), axes["pair"], strict=True):
                        # Crops keep their requested size, even where padded outside the source.
                        shape[dim] = 2 * round(width_km[axis] / 2 / spacing_km) + 1
                if set(dims) - shape.keys():
                    raise ValueError(f"{source_id}.{name}: output dimensions have no known sizes.")
                shape = {dim: shape[dim] for dim in dims}
                width = _width(source, record)
                if descriptor.get("operation") or width_km:
                    width = max(8, width)  # Allow floating-point preparation/padding.
                    processing_block = max(processing_block, width * _block(shape, {"time": 1}))
                largest = max(largest, _writer_block(shape, spatial, width, output, chunks, shards))
    return {"largest_writer_block_bytes": largest, "resident_product_bytes": resident,
            "largest_processing_block_bytes": processing_block}


def _unavailable(reason):
    return {"status": "unavailable", "reason": reason, "estimated_peak_rss_bytes": None,
            "estimated_median_rss_bytes": None, "recommended_allocation_bytes": None}


def estimate_run_memory(facts, *, output_layouts=None):
    """Estimate a process-tree working set, not a measured or guaranteed memory limit."""
    from frameit.io.netcdf_export import output_grid_layout

    products, sources = facts.get("products"), facts.get("sources")
    resources = facts.get("execution_resources")
    if not products or not sources or not resources or any(
        (source.get("field_binding") or {}).get("status") != "bound"
        for source in sources.values()
    ):
        return _unavailable("Complete validation and bind the selected inputs and products first.")
    try:
        inputs = {
            name: _input_work(source, facts["layouts"]["inputs"][name]["requested"])
            for name, source in sources.items()
        }
        geometry = {name: _geometry_size(source) for name, source in sources.items()}
        outputs = {}
        for product in products:
            name, kind = product["source"], product["product"]
            source, layout = sources.get(name), None
            if source is not None:
                if output_layouts is not None:
                    layout = output_layouts[name][kind]
                else:
                    layout = output_grid_layout(source, regional=(kind == "model_grid" and bool(
                        facts["configuration"].get("region", {}).get("width_km"))))
            outputs[name, kind] = _product_work(product, source, facts, layout)
    except (KeyError, ValueError, TypeError, AttributeError, ArithmeticError) as exc:
        return _unavailable(f"Some bound input or output sizes could not be estimated: {exc}")

    has_polar = any(kind == "polar" for _, kind in outputs)
    has_fa = any(source["format"] == "fa" for source in sources.values())
    main_base = (256 + (128 if has_polar else 0)) * MIB
    helper = 160 * MIB if has_fa else 0
    workers = resources["dask_workers"]
    thread_reserve = workers * resources["native_threads"] * MIB
    records = sum(len(s["record_inventory"]) for s in sources.values())
    jobs = sum(len(s["field_binding"].get("operation_plans", ())) for s in sources.values())
    retained = (3 * sum(nbytes for nbytes, _ in geometry.values())
                + 4096 * records + 1024 * sum(i["estimated_input_tiles"] for i in inputs.values())
                + 16384 * jobs)
    geom_peak = max(largest for _, largest in geometry.values())
    input_peak = max(item["largest_input_block_bytes"] for item in inputs.values())
    input_typical = _median(i["typical_input_block_bytes"] for i in inputs.values())
    live = main_base + retained + thread_reserve
    phases = {
        "preflight": (main_base + retained + helper + 8 * geom_peak,
                      main_base + retained + helper + 2 * geom_peak),
        "preparation": (live + helper + workers * 3 * input_peak,
                        live + helper + workers * 2 * input_typical),
    }
    if any(source.get("tracker_support") for source in sources.values()):
        tracker = max(i["tracker_largest_sample_bytes"] for i in inputs.values())
        typical = max(i["tracker_typical_sample_bytes"] for i in inputs.values())
        planes = sum(i["tracker_retained_plane_bytes"] for i in inputs.values())
        phases["tracking"] = (live + planes + 3 * tracker, live + planes + 2 * typical)
    polar_storage = sum(item["resident_product_bytes"] for (name, kind), item in outputs.items()
                        if kind == "polar")
    if has_polar:
        block = max(i["largest_processing_block_bytes"] for i in outputs.values())
        phases["polar"] = (live + polar_storage + workers * (3 * input_peak + 4 * block),
                           live + polar_storage + workers * (2 * input_typical + block))

    spawned = (0 if resources["synchronous_export"]
               else min(resources["export_workers"], len(outputs)))
    writer_work = []
    for (name, _kind), item in outputs.items():
        read, coordinates = inputs.get(name, {}), geometry.get(name, (0, 0))[0]
        transfer = coordinates + item["resident_product_bytes"]
        decode = read.get("largest_input_block_bytes", 0)
        typical = read.get("typical_input_block_bytes", 0)
        writer = item["largest_writer_block_bytes"]
        processing = item["largest_processing_block_bytes"]
        overhead = helper if name is not None and sources[name]["format"] == "fa" else 0
        if spawned:
            overhead += 192 * MIB + thread_reserve + 2 * transfer
        writer_work.append((overhead + workers * (3 * decode + 2 * writer + 3 * processing),
                            overhead + workers * (2 * typical + writer + processing)))
    export_peak = sum(sorted((peak for peak, _ in writer_work), reverse=True)[:spawned or 1])
    export_typical = min(export_peak,
                         _median(typical for _, typical in writer_work) * (spawned or 1))
    phases["export"] = (live + polar_storage + export_peak, live + polar_storage + export_typical)

    peak = max(pair[0] for pair in phases.values())
    typical = _median(pair[1] for pair in phases.values())
    allocation = ((3 * peak + 2 * GIB - 1) // (2 * GIB)) * GIB
    return {
        "status": "estimated", "method": "bound_working_sets_v1",
        "estimated_peak_rss_bytes": peak, "estimated_median_rss_bytes": typical,
        "recommended_allocation_bytes": allocation, "headroom_fraction": 0.5,
        "rss_scope": "sum of simultaneous RSS of the main process and local workers",
        "median_basis": "median of modeled typical phase working sets, not time-weighted",
        "concurrency": {"dask_workers": workers, "native_threads": resources["native_threads"],
                        "spawned_export_workers": spawned},
        "inputs": inputs,
        "products": {f"{name}.{kind}" if name else kind: item
                     for (name, kind), item in outputs.items()},
        "phases": {name: {"peak_rss_bytes": values[0], "typical_rss_bytes": values[1]}
                   for name, values in phases.items()},
        "assumptions": [
            "Fixed process overhead and buffer multipliers; not a measured or guaranteed limit.",
            "Native decode, backend chunk caches, graph reuse and codec workspace vary.",
            "Source reads may cover the full native grid before a crop or regrid.",
            "Polar processing budgets a full prepared source plane when stencil sizes are unknown.",
            "Summed RSS can count shared pages twice and is not scheduler MaxRSS.",
        ],
    }
