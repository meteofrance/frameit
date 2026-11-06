# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Validated polar sampling axes and explicit target-grid allocation budgets."""

from __future__ import annotations

import math

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
    }
    if step is not None:
        metadata["requested_azimuthal_resolution_deg"] = float(step)
    if getattr(conf, "polar_n_theta", None) is not None:
        metadata["requested_polar_n_theta"] = int(conf.polar_n_theta)
    return radii, angles, metadata
