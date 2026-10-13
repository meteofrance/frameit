# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Label-aligned geodesic point sampling with explicit interpolation support."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

import numpy as np
import xarray as xr

from frameit.processing.derived.wind import (
    add_speed_from_uv_dict,
    add_vrad_vtan_from_polar_dict,
    align_wind_pair,
    normalize_winds,
    wind_names,
)
from frameit.processing.polar.contracts import (
    SourceGeometryCache,
    align_times,
    geographic_degrees,
    same_source_geometry,
    time_index,
)
from frameit.processing.polar.coverage import (
    attach_quality,
    validate_mask_options,
)
from frameit.processing.polar.metadata import (
    point_attributes,
    restore_auxiliaries,
    source_auxiliaries,
)
from frameit.processing.polar.performance import dask_graph_tasks, process_peak_rss_bytes
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.processing.polar.polar_utils import finalize_polar_output
from frameit.processing.polar.regrid_plan import (
    DEFAULT_CACHE_BYTES,
    DEFAULT_CACHE_SIZE,
    PolarRegridPlanCache,
    validate_execution_options,
)

try:
    import xesmf as xe
except Exception as exc:  # pragma: no cover
    xe, _XESMF_IMPORT_ERROR = None, exc
else:
    _XESMF_IMPORT_ERROR = None

logger = logging.getLogger(__name__)
_IGNORED_VERTICAL_KEYS = {
    "level_selection", "level_values", "level_indices", "levels", "all_levels", "level",
}


def _get_polar_requests_variables_only(conf):
    raw = getattr(conf, "polar_variables", None)
    if raw is None:
        return {}
    if isinstance(raw, str) and raw.strip().lower() == "all":
        raw = getattr(conf, "requested_variables_user", {})
    if not isinstance(raw, dict):
        raise TypeError("polar_variables must be a dict or 'all'")
    requests = {}
    for group, spec in raw.items():
        if spec is None:
            continue
        if isinstance(spec, (list, tuple)):
            variables = list(spec)
        elif isinstance(spec, dict):
            ignored = set(spec) & _IGNORED_VERTICAL_KEYS
            if ignored:
                logger.warning("Polar vertical selections %s are ignored for %s", ignored, group)
            variables = spec.get("variables", []) or []
        else:
            raise TypeError(f"polar_variables[{group!r}] must be a dict or variable list")
        if variables:
            requests[str(group)] = {"variables": list(dict.fromkeys(map(str, variables)))}
    return requests


def _reshape_locstream_dataset(ds_loc, *, r_km, theta_deg, loc_dim="locations", output_chunks=None):
    expected = len(r_km) * len(theta_deg)
    if ds_loc.sizes.get(loc_dim) != expected:
        raise ValueError("LocStream output size does not match the target polar grid")
    fields = {}
    for name, value in ds_loc.data_vars.items():
        if loc_dim not in value.dims:
            fields[name] = value
            continue
        leading = [dim for dim in value.dims if dim != loc_dim]
        value = value.transpose(*leading, loc_dim)
        shape = tuple(value.sizes[dim] for dim in leading) + (len(r_km), len(theta_deg))
        coords = {dim: value[dim].variable for dim in leading if dim in value.coords}
        coords.update(rr=("rr", r_km), theta_deg=("theta_deg", theta_deg))
        fields[name] = xr.DataArray(
            value.data.reshape(shape), dims=(*leading, "rr", "theta_deg"),
            coords=coords, attrs=dict(value.attrs),
        )
        if output_chunks and hasattr(fields[name].data, "__dask_graph__"):
            fields[name] = fields[name].chunk({
                ("theta_deg" if dim == "theta" else dim): size
                for dim, size in output_chunks.items()
                if ("theta_deg" if dim == "theta" else dim) in fields[name].dims
            })
    return xr.Dataset(fields)


def _projection_jobs(requests, inputs, report):
    """Combine requests sharing an output so wind pairs share source stencils."""
    jobs = {}
    for requested, spec in requests.items():
        output = "level" if requested == "level_w" else requested
        source = "level" if requested == "level_w" and "level" in inputs else requested
        if source not in inputs:
            report["skipped"].append({"group": requested, "reason": "missing source group"})
            continue
        if requested == "level_w":
            report["redirects"].append({"from": requested, "to": source})
        job = jobs.setdefault((output, source), {"groups": [], "variables": []})
        job["groups"].append(requested)
        job["variables"] = list(dict.fromkeys(job["variables"] + spec["variables"]))
    return jobs


def _broadcast_auxiliary(value, grid):
    return xr.broadcast(value.reset_coords(drop=True), grid.lon)[0]


def _sample_piece(source, names, pair, geometry, conf, method, plan_cache, source_geometry_cache):
    geography = source.isel(time=0, drop=True) if "time" in source.dims else source
    _, grid, footprint = source_geometry_cache.get(
        geography, conf.name_longitude, conf.name_latitude
    )
    cropped = source.isel(
        y_box=slice(*footprint["y_slice"]), x_box=slice(*footprint["x_slice"])
    )
    plan = plan_cache.get(
        grid, geometry, method=method,
        zero_tolerance=getattr(conf, "polar_weight_zero_tolerance", 1e-14),
        regridder_factory=xe.Regridder,
    )
    application_options = dict(
        policy=getattr(conf, "polar_missing_data_policy", "strict"),
        minimum_support=getattr(conf, "polar_min_valid_weight_fraction", .5),
        output_chunks=getattr(conf, "polar_output_chunks", {}),
    )
    leading, auxiliaries, mapping = source_auxiliaries(
        cropped, conf.name_longitude, conf.name_latitude, field_names=names
    )
    joint = None
    if all(name in names for name in pair):
        u, v = align_wind_pair(cropped[pair[0]], cropped[pair[1]])
        joint = np.isfinite(u) & np.isfinite(v)
        joint = joint.reset_coords(drop=True)
    sampled, support, status = {}, {}, {}
    for name in names:
        field = cropped[name].reset_coords(drop=True)
        if not {"y_box", "x_box"} <= set(field.dims):
            raise ValueError(f"Polar field {name} must contain named y_box/x_box dimensions")
        if not np.issubdtype(field.dtype, np.number):
            raise ValueError(f"Polar field {name} must be numerical")
        sampled[name], support[name], status[name] = plan_cache.apply(
            plan, field, joint if joint is not None and name in pair else None,
            **application_options,
        )
    transformed = {}
    for name, value in auxiliaries.items():
        transformed[name] = plan_cache.apply(
            plan, _broadcast_auxiliary(value, grid), **application_options
        )[0]
    all_values = dict(sampled)
    for name in names:
        all_values[f"{name}_support_fraction"] = support[name]
        all_values[f"{name}_interpolation_status"] = status[name]
    for name, value in transformed.items():
        all_values[name] = value
    template = next(iter(sampled.values()))
    mapped = plan.supported.geometry_mapped
    if "time" in template.dims:
        mapped = mapped.expand_dims(time=template.time)
    all_values["geometry_mapped"] = mapped.astype(np.uint8)
    result = _reshape_locstream_dataset(
        xr.Dataset(all_values), r_km=plan.geometry.radius_km, theta_deg=plan.geometry.theta_deg,
        output_chunks=getattr(conf, "polar_output_chunks", {}),
    )
    transformed = {name: result[name] for name in transformed}
    result = result.drop_vars(list(transformed))
    result = restore_auxiliaries(result, leading, transformed)
    result.attrs["source_grid_mapping"] = mapping
    result.attrs["source_finite_footprint"] = footprint
    return result, plan, footprint


def _quality_for_outputs(ds, sampled_names, pair, internal):
    for name in sampled_names:
        attach_quality(ds, name, ds[f"{name}_support_fraction"], ds[f"{name}_interpolation_status"])
    if all(name in sampled_names for name in pair):
        for name in ("vrad", "vtan", "wind_speed"):
            if name not in ds:
                continue
            support = ds[f"{pair[0]}_support_fraction"]
            status = ds[f"{pair[0]}_interpolation_status"]
            if name in {"vrad", "vtan"}:
                status = xr.where(ds.rr == 0, 4, status)
            attach_quality(ds, name, support, status)
    for name in internal:
        ds = ds.drop_vars([name] + [
            f"{name}_{suffix}" for suffix in (
                "support_fraction", "interpolation_status", "valid", "ring_coverage",
                "full_ring_valid",
            )
        ], errors="ignore")
    if internal:
        for name in ("vrad", "vtan"):
            ds = ds.drop_vars([name] + [
                f"{name}_{suffix}" for suffix in (
                    "support_fraction", "interpolation_status", "valid", "ring_coverage",
                    "full_ring_valid",
                )
            ], errors="ignore")
    ds.geometry_mapped.attrs.update(
        units="1", long_name="target mapped by finite source geometry",
        frameit_role="interpolation_quality",
    )
    return ds


def polar_project(
    dico_collocated: dict[str, xr.Dataset], *, conf: Any, method="bilinear", track=None,
    plan_cache: PolarRegridPlanCache | None = None,
):
    """Sample aligned fields using explicit geometry, missing-data and coverage contracts.

    The reference time axis comes from surface, otherwise the first source
    group. Source groups must contain exactly those labels (order may differ).
    Extra track positions are permitted and reported, but missing/duplicate
    track labels are not. No nearest-neighbour extrapolation is introduced.
    """
    if not bool(getattr(conf, "compute_polar_proj", False)):
        return {}, {"skipped": [], "notes": ["compute_polar_proj is False"]}
    if xe is None:  # pragma: no cover
        raise ImportError("xESMF is required for polar projection") from _XESMF_IMPORT_ERROR
    if method not in {"bilinear", "nearest_s2d"}:
        raise ValueError("Explicit support policies require bilinear or nearest_s2d point sampling")
    policy = getattr(conf, "polar_missing_data_policy", "strict")
    minimum = getattr(conf, "polar_min_valid_weight_fraction", 0.5)
    tolerance = getattr(conf, "polar_weight_zero_tolerance", 1e-14)
    validate_mask_options(policy, minimum, tolerance)
    cache_size = getattr(conf, "polar_regrid_cache_size", DEFAULT_CACHE_SIZE)
    cache_bytes = getattr(conf, "polar_regrid_cache_max_bytes", DEFAULT_CACHE_BYTES)
    chunks = getattr(conf, "polar_output_chunks", {})
    profile = getattr(conf, "polar_profile", False)
    validate_execution_options(cache_size, cache_bytes, chunks, profile)
    cache = plan_cache if plan_cache is not None else PolarRegridPlanCache(cache_size, cache_bytes)
    cache_start = dict(cache.counters)
    source_geometry_cache = SourceGeometryCache()
    projection_started = perf_counter()
    requests = _get_polar_requests_variables_only(conf)
    if not requests:
        return {}, {"skipped": [], "notes": ["No polar_variables request found"]}
    if not dico_collocated:
        raise ValueError("Polar projection requires source groups")
    reference = dico_collocated.get("surface", next(iter(dico_collocated.values())))
    reference_index = time_index(reference, "Reference source")
    if not reference_index.is_monotonic_increasing:
        raise ValueError("Reference time labels must be increasing")
    time = xr.DataArray(reference.time.variable)
    inputs = {name: align_times(ds, time, f"Source group {name}")
              for name, ds in dico_collocated.items()}
    report = {"projected": [], "skipped": [], "redirects": [], "unused_track_times": 0}
    if track is not None:
        report["unused_track_times"] = len(time_index(track, "Polar track")) - len(time)
        track = align_times(track, time, "Polar track", exact=False)
    reference = inputs["surface"] if "surface" in inputs else next(iter(inputs.values()))
    lon, lat = xr.broadcast(geographic_degrees(reference[conf.name_longitude]),
                            geographic_degrees(reference[conf.name_latitude]))
    reference = reference.assign_coords({conf.name_longitude: lon, conf.name_latitude: lat})
    grid = PolarLonLatGrid.from_conf(conf, ellps=getattr(conf, "polar_ellipsoid", "WGS84"))
    geometry = grid.build(reference, track=track)
    target_static = all(
        all(np.array_equal(geometry[name].isel(time=0), geometry[name].isel(time=index))
            for name in ("lon", "lat")) for index in range(1, len(time))
    )
    outputs = {}
    plan_diagnostics = {}
    projection_work = []
    for (output, source_name), job in _projection_jobs(requests, inputs, report).items():
        source = inputs[source_name]
        requested = job["variables"]
        pair = wind_names(conf, output)
        internal = []
        if "wind_speed" in requested:
            if not all(name in source for name in pair):
                raise ValueError(f"wind_speed in {output} requires collocated {pair}")
            internal = [name for name in pair if name not in requested]
        names = list(dict.fromkeys([n for n in requested if n != "wind_speed"] + internal))
        missing = [name for name in names if name not in source.data_vars]
        names = [name for name in names if name in source.data_vars]
        if not names:
            report["skipped"].append({"group": output, "reason": "no matching fields",
                                      "missing_variables": missing})
            continue
        reserved = {"geometry_mapped"} | {
            f"{name}_{suffix}" for name in names for suffix in (
                "support_fraction", "interpolation_status", "valid", "ring_coverage",
                "full_ring_valid",
            )
        }
        if reserved.intersection(names):
            raise ValueError("Requested field names collide with interpolation-quality variables")
        if any(name in names for name in pair):
            source = normalize_winds(source, conf, output)
        # Static quantities still acquire exactly the required time labels.
        for name in names:
            if "time" not in source[name].dims:
                source = source.assign({name: source[name].expand_dims(time=time)})
        static = target_static and same_source_geometry(
            source, conf.name_longitude, conf.name_latitude, geometry_cache=source_geometry_cache,
        )
        projection_work.append(dict(
            output=output, source_name=source_name, source=source, job=job, names=names,
            pair=pair, internal=internal, missing=missing, static=static,
            footprints=[], pieces=[], signatures=[],
        ))
    for work in projection_work:
        if work["static"]:
            # Geometry is proven invariant; apply the same weights to all times.
            result, plan, footprint = _sample_piece(
                work["source"], work["names"], work["pair"],
                geometry.isel(time=0, drop=True), conf, method,
                cache, source_geometry_cache,
            )
            work["result"] = result
            work["footprints"] = [footprint] * len(time)
            work["signatures"] = [plan.signature] * len(time)
            plan_diagnostics[plan.signature] = plan.diagnostics()
    # Apply every compatible group at one instant before advancing time. A
    # small cache can then reuse moving-grid weights even for long sequences.
    for index in range(len(time)):
        for work in projection_work:
            if not work["static"]:
                piece, plan, footprint = _sample_piece(
                    work["source"].isel(time=index, drop=True), work["names"], work["pair"],
                    geometry.isel(time=index, drop=True), conf, method,
                    cache, source_geometry_cache,
                )
                work["pieces"].append(piece.expand_dims(time=[time.values[index]]))
                work["footprints"].append(footprint)
                work["signatures"].append(plan.signature)
                plan_diagnostics[plan.signature] = plan.diagnostics()
    for work in projection_work:
        output, source_name, source, job, names, pair, internal, missing = (
            work[key] for key in (
                "output", "source_name", "source", "job", "names", "pair", "internal", "missing"
            )
        )
        footprints, signatures = work["footprints"], work["signatures"]
        result = work["result"] if work["static"] else xr.concat(
            work["pieces"], dim="time", coords="different", compat="equals"
        )
        result = result.assign_coords(time=time.variable)
        for name in ("lon", "lat"):
            label = conf.name_longitude if name == "lon" else conf.name_latitude
            result = result.assign_coords({label: geometry[name].variable})
            result[label].attrs["units"] = "degrees_east" if name == "lon" else "degrees_north"
        for name in geometry.coords:
            if name not in {"time", "rr", "theta_deg"}:
                result = result.assign_coords({name: geometry[name].variable})
        for name in ("x_km", "y_km"):
            result = result.assign_coords({name: geometry[name].variable})
        mapping = result.attrs.get("source_grid_mapping", {})
        result.attrs = {("source_" + key if key.startswith("box_") else key): value
                        for key, value in point_attributes(source.attrs).items()}
        result.attrs.update(geometry.attrs)
        result.attrs.update(
            polar_proj_backend="xesmf", polar_proj_method=method,
            polar_proj_group_source=source_name, polar_proj_group_output=output,
            polar_proj_group_requested=job["groups"][0],
            polar_proj_groups_requested=job["groups"],
            polar_time_alignment="exact_reference_labels",
            polar_missing_data_policy=policy, polar_min_valid_weight_fraction=minimum,
            polar_weight_zero_tolerance=tolerance,
            polar_source_halo_points=getattr(conf, "polar_source_halo_points", 1),
            interpolation_geometry="ESMF spherical longitude/latitude degrees",
            target_geometry="ellipsoidal geodesic point sampling",
            source_grid_mapping=mapping, source_finite_footprints=footprints,
            requested_output_box_x_size_km=conf.x_boxsize_km,
            requested_output_box_y_size_km=conf.y_boxsize_km,
            polar_maximum_radius_km=float(geometry.rr[-1]),
        )
        result = finalize_polar_output(result)
        coordinate_attributes = {name: dict(coord.attrs) for name, coord in result.coords.items()}
        result = add_vrad_vtan_from_polar_dict({output: result}, conf)[output]
        result = add_speed_from_uv_dict({output: result}, conf)[output]
        result = _quality_for_outputs(result, names, pair, internal)
        # xarray mask arithmetic may discard coordinate attributes when its
        # arrays are assigned back. Restore the authoritative coordinate schema.
        for name, attributes in coordinate_attributes.items():
            if name in result.coords:
                result[name].attrs = attributes
        result = finalize_polar_output(result)
        for name, variable in list(result.data_vars.items()):
            if chunks and hasattr(variable.data, "__dask_graph__"):
                result[name] = variable.chunk({dim: size for dim, size in chunks.items()
                                               if dim in variable.dims})
        outputs[output] = result
        mapped = result.geometry_mapped.mean("theta")
        report["projected"].append({
            "requested_group": job["groups"][0],
            "requested_groups": job["groups"], "source_group": source_name,
            "output_group": output, "nvars": len(names), "missing_variables": missing,
            "geometry_mapped_fraction_by_radius": mapped.values.tolist(),
            "source_finite_footprints": footprints,
            "regrid_plan_signatures": signatures,
        })
    unknown_chunks = set(chunks) - {dim for ds in outputs.values() for dim in ds.dims}
    if outputs and unknown_chunks:
        raise ValueError(f"Unknown polar_output_chunks dimensions: {sorted(unknown_chunks)}")
    report["n_groups_out"], report["n_groups_requested"] = len(outputs), len(requests)
    stats = cache.statistics()
    per_call = {key: cache.counters[key] - value for key, value in cache_start.items()}
    report["regrid_performance"] = {
        **per_call, "cache": stats, "source_geometry_cache": source_geometry_cache.statistics(),
        "plans": list(plan_diagnostics.values()),
        "projection_setup_s": perf_counter() - projection_started,
        "application_timing_scope": (
            "NumPy computation or Dask graph setup; excludes lazy materialization"
        ),
        "output_chunks": chunks, "default_radial_block": 32,
        "graph_tasks": dask_graph_tasks(outputs.values()) if profile else None,
        "process_peak_rss_bytes": process_peak_rss_bytes() if profile else None,
        "rss_scope": "process lifetime high-water mark, including prior imports and loading",
    }
    return outputs, report
