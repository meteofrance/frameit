# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Validated polar sampling axes and explicit target-grid allocation budgets."""

from __future__ import annotations

import math
from copy import copy

import numpy as np

DEFAULT_MAX_POLAR_POINTS = 2_000_000


def validate_sampling_options(count, step_deg, max_points):
    if isinstance(max_points, (bool, np.bool_)) or not isinstance(max_points, (int, np.integer)):
        raise ValueError("polar_max_points must be a positive integer")
    if max_points <= 0:
        raise ValueError("polar_max_points must be a positive integer")
    if count is not None:
        if isinstance(count, (bool, np.bool_)) or not isinstance(count, (int, np.integer)):
            raise ValueError("polar_n_theta must be an integer of at least 3")
        if count < 3:
            raise ValueError("polar_n_theta must be an integer of at least 3")
    if step_deg is not None:
        if isinstance(step_deg, (bool, np.bool_)) or not np.isfinite(float(step_deg)):
            raise ValueError("azimuthal_resolution must be finite and positive")
        if not 0 < float(step_deg) <= 120:
            raise ValueError("azimuthal_resolution must be positive and at most 120 degrees")
        if float(step_deg) < 360.0 / max_points:
            raise ValueError("Angular sampling exceeds polar_max_points")
        required = math.ceil(360.0 / float(step_deg))
        if count is not None and count != required:
            raise ValueError("polar_n_theta conflicts with the requested azimuthal_resolution")
    if count is not None:
        check_point_budget(count, max_points)


def check_point_budget(points: int, limit: int) -> None:
    if points > limit:
        raise ValueError(
            f"Polar target grid requires {points} points, exceeding polar_max_points={limit}. "
            "Choose coarser sampling or explicitly increase polar_max_points."
        )


def angular_tolerance(values, cycle):
    dtype = np.asarray(values).dtype
    epsilon = np.finfo(dtype).eps if np.issubdtype(dtype, np.floating) else np.finfo(float).eps
    return max(1e-12, 2 * epsilon * cycle)


def uniform_periodic_angles(values, cycle=360.0):
    values = np.asarray(values)
    if values.ndim != 1 or values.size < 3 or not np.isfinite(values).all():
        return False
    gaps = np.diff(np.r_[values.astype(float), float(values[0]) + cycle])
    return bool(np.all(gaps > 0) and np.allclose(gaps, cycle / values.size, rtol=0,
                            atol=angular_tolerance(values, cycle)))


def validate_axes(radius_km, theta_deg):
    if radius_km.ndim != 1 or radius_km.size == 0:
        raise ValueError("r_km must be a non-empty 1D array")
    if not np.isfinite(radius_km).all() or np.any(radius_km < 0):
        raise ValueError("r_km must be finite and nonnegative")
    if np.any(radius_km > np.finfo(float).max / 1000):
        raise ValueError("r_km cannot be represented as finite geodesic distances in metres")
    if np.any(np.diff(radius_km) <= 0):
        raise ValueError("r_km must be strictly increasing")
    if theta_deg.ndim != 1 or theta_deg.size == 0:
        raise ValueError("theta_deg must be a non-empty 1D array")
    if not np.isfinite(theta_deg).all() or np.any((theta_deg < 0) | (theta_deg >= 360)):
        raise ValueError("theta_deg must be finite and in [0, 360), without a duplicate endpoint")
    if np.any(np.diff(theta_deg) <= 0):
        raise ValueError("theta_deg must be strictly increasing and unique")


def sampling_axes(conf):
    """Return physical radii, uniform open angles, and requested/effective metadata."""
    max_points = getattr(conf, "polar_max_points", DEFAULT_MAX_POLAR_POINTS)
    count = getattr(conf, "polar_n_theta", None)
    step = getattr(conf, "azimuthal_resolution", None)
    validate_sampling_options(count, step, max_points)
    if getattr(conf, "schema_version", None) == 3:
        radius = float(conf.yaml_config["products"]["polar"]["radius_km"])
    else:
        sizes = [float(conf.x_boxsize_km), float(conf.y_boxsize_km)]
        if any(not math.isfinite(value) or value <= 0 for value in sizes):
            raise ValueError("x_boxsize_km and y_boxsize_km must be finite and positive")
        radius = 0.5 * min(sizes)
    radial_m = getattr(conf, "radial_resolution", None)
    if radial_m is None or radial_m == 0:
        radial_m = getattr(conf, "resolution", None)
    if radial_m is None or not math.isfinite(float(radial_m)) or float(radial_m) <= 0:
        raise ValueError("radial_resolution must be finite and positive (metres)")
    radial_km = float(radial_m) / 1000
    if radial_km == 0:
        raise ValueError("radial_resolution is too small to represent in kilometres")
    radial_ratio = radius / radial_km
    if not math.isfinite(radial_ratio) or radial_ratio > max_points:
        raise ValueError("Radial sampling exceeds polar_max_points")
    intervals = math.floor(radial_ratio)
    last = intervals * radial_km
    include_endpoint = not math.isclose(last, radius, rel_tol=1e-12, abs_tol=0)
    nr = intervals + 1 + int(include_endpoint)
    if count is not None:
        source = "requested_point_count"
    elif step is not None:
        count = math.ceil(360 / float(step))
        source = "requested_angular_step"
    else:
        ratio = 2 * math.pi * radial_ratio
        if not math.isfinite(ratio) or ratio > max_points:
            raise ValueError("Automatic angular sampling exceeds polar_max_points")
        count = max(3, math.ceil(ratio))
        source = "automatic_outer_ring_spacing"
    check_point_budget(nr * int(count), max_points)
    radii = np.arange(intervals + 1, dtype=float) * radial_km
    if include_endpoint:
        radii = np.append(radii, radius)
    else:
        radii[-1] = radius
    angles = np.arange(count, dtype=float) * (360.0 / count)
    metadata = {
        "angular_sampling_source": source,
        "requested_radial_resolution_m": float(radial_m),
        "effective_azimuthal_resolution_deg": 360.0 / count,
        "n_theta": int(count),
        "polar_max_points": int(max_points),
        "last_radial_interval_km": float(radii[-1] - radii[-2]) if len(radii) > 1 else 0.,
    }
    if step is not None:
        metadata["requested_azimuthal_resolution_deg"] = float(step)
    if getattr(conf, "polar_n_theta", None) is not None:
        metadata["requested_polar_n_theta"] = int(conf.polar_n_theta)
    return radii, angles, metadata


def bind_polar_plan(source, request, binding, conf, *, radial_step_km=None):
    """Resolve actual preparation, interpolation evidence and a crop-independent target."""
    from frameit.processing.polar.contracts import polar_field_options, polar_source_geometry
    from frameit.processing.polar.polar_proj import require_polar_backend
    from frameit.processing.requests import resolve_field_metadata, source_field_metadata

    if not source.get("region", {}).get("associations"):
        binding["deferred_checks"].append(
            "Polar centre/time associations and regional geometry require method planning.")
        return
    require_polar_backend()
    jobs = [job for job in binding["operation_plans"] if job["product"] == "polar"]
    components = [job for job in jobs if job["method"] in {"radial_wind", "tangential_wind"}]
    if components:
        from frameit.io.netcdf_export import _output_grid_facts, output_grid_layout

        layout = output_grid_layout({
            **source, "representation_grids": binding["representation_grids"],
            "requests": {**request, "binding": binding}})
        selected = set(binding["products"]["polar"])
        suffixes = ("geometry_mapped", "support_fraction", "interpolation_status",
                    "valid", "ring_coverage", "full_ring_valid")
        reserved = {
            "geometry_mapped", "time", "rr", "rr_km", "theta", "theta_deg", "radius",
            "azimuth", "azimuth_degrees", "latitude", "longitude", "radial_bearing",
            "center_lat", "center_lon", "center_time", "center_latitude", "center_longitude",
            "radial_spacing_km", "max_azimuthal_spacing_m",
        } | {f"{name}_{suffix}" for name in selected for suffix in suffixes}
        for job in components:
            facts = _output_grid_facts(layout, job["grid_id"], job["name"])
            spatial = set(facts["horizontal"]) | set(facts["geography"])
            names = {native: target for native, target in {
                **facts["dimensions"], **facts["coordinates"]}.items() if native not in spatial}
            generated = reserved | set(names) | set(names.values()) | {
                f"{name}_source_native_index" for native, target in facts["dimensions"].items()
                if native not in spatial for name in (native, target)}
            if job["name"] in generated or selected.intersection(
                    f"{job['name']}_{suffix}" for suffix in suffixes):
                raise ValueError(
                    f"sources.{source['name']}.derived.{job['name']}: alias collides with "
                    "generated polar coordinates or quality variables; choose another output alias")
    spacing = []
    for job in jobs:
        job["polar_geometry"] = polar_source_geometry(job, conf)
        evidence = job["polar_geometry"]["spacing"]
        spacing.append(max(evidence[axis]["spacing_m"] for axis in ("x", "y")))
        job["polar_options"] = {}
        job["polar_input_metadata"] = {}
        for name in set(job["inputs"].values()):
            descriptor = job["input_binding"]["dependencies"][name]
            record = descriptor["records"][0]
            field = source["fields"][record["field_id"]]
            metadata = record.get("field_metadata") or source_field_metadata(
                source, field, record=record) or resolve_field_metadata(
                    record.get("observed_attributes", field["attributes"]), {},
                    f"polar.{name}", temporal_names=record.get("temporal_names", [record["clock"]]))
            job["polar_options"][name] = polar_field_options(
                metadata, {"sampling": job["sampling"], **request["polar_options"].get(name, {})},
                conf, f"polar.{name}")
            job["polar_input_metadata"][name] = {
                "attributes": {key: metadata["attributes"][key] for key in (
                    "units", "kind", "temporal_kind", "standard_name")
                    if key in metadata["attributes"]},
                "origins": metadata["origins"],
            }
        if job["method"] in {"radial_wind", "tangential_wind"}:
            loc = f"sources.{source['name']}.derived.{job['name']}"
            u, v = (job["polar_options"][job["inputs"][key]] for key in ("u", "v"))
            if any(options["kind"] != "continuous" for options in (u, v)):
                raise ValueError(f"{loc}: polar wind components require continuous inputs")
            if any(options["missing_data_policy"] != "strict" for options in (u, v)):
                raise ValueError(f"{loc}: polar wind components require strict shared stencils")
            different = [key for key in (
                "kind", "interpolation", "missing_data_policy",
                "min_valid_weight_fraction", "sampling")
                if u[key] != v[key]]
            if different:
                raise ValueError(
                    f"{loc}: paired polar inputs require matching effective {', '.join(different)}")
    if conf.polar_source_halo_points < 1:
        raise ValueError(
            "Polar source halo is insufficient: at least one native neighbour is required")
    binding["polar_plan"] = {"status": "prepared", "native_spacing_m": spacing}
    if conf.polar_shared_target and radial_step_km is None:
        return binding["polar_plan"]
    return resolve_polar_sampling(source, binding, conf, radial_step_km=radial_step_km)


def resolve_polar_sampling(source, binding, conf, *, radial_step_km=None):
    """Resolve only the final target; never rebuild preparation/read bindings."""
    spacing = binding["polar_plan"]["native_spacing_m"]
    native = max(spacing)
    requested = conf.yaml_config["products"]["polar"].get("radial_step_km")
    step = radial_step_km if radial_step_km is not None else (
        requested if requested is not None else native / 1000)
    if step * 1000 < native * (1 - 1e-12):
        raise ValueError(
            f"products.polar.radial_step_km={step} is finer than supported native spacing "
            f"{native / 1000} km; evidence: {spacing} metres")
    settings = copy(conf)
    settings.radial_resolution = step * 1000
    radii, angles, metadata = sampling_axes(settings)
    associations = source.get("region", {}).get("associations", [])
    times = [record["source_time"] for record in associations] or source["selected_times"]
    check_point_budget(len(times) * len(radii) * len(angles), conf.polar_max_points)
    binding["polar_plan"] = {
        "status": "bound", "radius_km": radii.tolist(), "azimuth_degrees": angles.tolist(),
        "radial_step_km": step, "native_spacing_m": spacing,
        "radial_step_origin": (
            "shared_coarsest_native_grid" if radial_step_km is not None and requested is None else
            "requested" if requested is not None else "coarsest_prepared_native_grid"),
        "source_times": times, "associations": associations,
        "centre_provider": source["region"]["centre_provider"],
        "support": "actual_nonzero_native_interpolation_stencils_independent_of_export_crop",
        "source_halo_points": conf.polar_source_halo_points,
        "target_points": len(times) * len(radii) * len(angles), **metadata,
    }
    for descriptor in binding["products"]["polar"].values():
        descriptor["execution"] = "bound_polar_sampling"
    return binding["polar_plan"]
