# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Analytical polar coordinates and explicitly plotting-only cyclic closure."""

from __future__ import annotations

import numpy as np
import xarray as xr

from frameit.processing.polar.sampling import angular_tolerance, uniform_periodic_angles
from frameit.utils.units import convert_units


def ensure_theta_rad_dim(ds: xr.Dataset, *, theta_deg: str = "theta_deg") -> xr.Dataset:
    """Normalize angle/radius metadata without changing the number of samples."""
    ds = ds.copy(deep=False)
    if theta_deg in ds.dims:
        degrees = convert_units(
            ds[theta_deg], "angle", target="degree", assumed="degree"
        ).values.astype(float)
        if "theta" in ds.coords:
            existing = convert_units(ds.theta, "angle", assumed="rad")
            if not np.allclose(existing, np.deg2rad(degrees), rtol=1e-12, atol=1e-12):
                raise ValueError("theta and theta_deg disagree physically")
        ds = ds.assign_coords(theta=(theta_deg, np.deg2rad(degrees)))
        ds = ds.swap_dims({theta_deg: "theta"})
        ds = ds.assign_coords(theta_deg=("theta", degrees))
    if "theta" in ds.coords:
        ds = ds.assign_coords(theta=convert_units(ds.theta, "angle", assumed="rad"))
        ds.theta.attrs.update(units="rad", long_name="launch azimuth clockwise from north")
    if "theta_deg" in ds.coords:
        ds = ds.assign_coords(theta_deg=convert_units(
            ds.theta_deg, "angle", target="degree", assumed="degree"))
        if "theta" in ds.coords and not np.allclose(
            ds.theta_deg, np.rad2deg(ds.theta), rtol=1e-12, atol=1e-10
        ):
            raise ValueError("theta and theta_deg disagree physically")
        ds.theta_deg.attrs.update(units="degree", long_name="launch azimuth clockwise from north")
    for radius in ("rr", "rr_km"):
        if radius in ds.coords:
            ds = ds.assign_coords({radius: convert_units(
                ds[radius], "distance", target="km", assumed="km")})
            ds[radius].attrs.update(units="km", long_name="radial distance from center")
    if "rr" in ds.coords and "rr_km" in ds.coords and not np.allclose(
        ds.rr, ds.rr_km, rtol=1e-12, atol=1e-12
    ):
        raise ValueError("rr and rr_km disagree physically")
    return ds


def _inspect_theta(ds, theta_dim):
    """Validate one open/closed cycle and recognize closure from coordinates."""
    if theta_dim not in ds.coords or ds[theta_dim].dims != (theta_dim,):
        raise ValueError(f"A one-dimensional {theta_dim} coordinate is required")
    angle = ds[theta_dim]
    if angle.attrs.get("units", "rad") != "rad":
        raise ValueError(f"{theta_dim} must be in radians")
    values = np.asarray(angle.values)
    if not values.size or not np.isfinite(values).all() or np.any(np.diff(values) <= 0):
        raise ValueError("Polar angles must be non-empty, finite, strictly increasing and unique")
    cycle = 2 * np.pi
    tolerance = angular_tolerance(values, cycle)
    span = float(values[-1]) - float(values[0])
    closed = values.size > 1 and abs(span - cycle) <= tolerance
    base = values[:-1] if closed else values
    if np.any(base < 0) or np.any(base >= cycle) or span > cycle + tolerance:
        raise ValueError(
            "Polar angles must lie in one [0, 2*pi) cycle, optionally with one endpoint"
        )
    if "theta_deg" in ds.coords and ds.theta_deg.dims == (theta_dim,):
        if not np.allclose(ds.theta_deg.values, np.rad2deg(values), rtol=0,
                           atol=np.rad2deg(tolerance)):
            raise ValueError("theta_deg is inconsistent with the radian angle coordinate")
    if closed:
        _validate_closure_values(ds, theta_dim)
    return base, closed


def _validate_closure_values(ds, theta_dim):
    """Check all angular fields/auxiliaries on bounded first/last slices."""
    for name, variable in ds.variables.items():
        if theta_dim not in variable.dims or name in {theta_dim, "theta_deg"}:
            continue
        first = variable.isel({theta_dim: 0}).values
        last = variable.isel({theta_dim: -1}).values
        if np.issubdtype(variable.dtype, np.inexact):
            matches = np.allclose(first, last, rtol=1e-12, atol=1e-12, equal_nan=True)
        else:
            matches = np.array_equal(first, last)
        if not matches:
            raise ValueError(f"Closed polar endpoint does not duplicate the first slice of {name}")


def close_theta_for_plot(ds: xr.Dataset, *, theta_dim: str = "theta") -> xr.Dataset:
    """Append exactly one verified cyclic endpoint on a separate plotting view.

    Actual coordinates and all angular values determine whether closure already
    exists. ``theta_closed`` alone is never trusted. Scientific means/FFTs must
    use the endpoint-exclusive dataset, not this plotting view.
    """
    if theta_dim not in ds.dims:
        return ds.copy(deep=False)
    values, closed = _inspect_theta(ds, theta_dim)
    if closed:
        result = ds.copy(deep=False)
    else:
        tail = ds.isel({theta_dim: slice(0, 1)}).assign_coords(
            {theta_dim: [float(values[0]) + 2 * np.pi]}
        )
        if "theta_deg" in ds.coords and ds.theta_deg.dims == (theta_dim,):
            tail = tail.assign_coords(theta_deg=(theta_dim, [float(ds.theta_deg[0]) + 360]))
        result = xr.concat([ds, tail], dim=theta_dim, data_vars="minimal", coords="minimal")
    result.attrs["theta_closed"] = True
    return result


def close_theta(ds: xr.Dataset, *, theta_dim: str = "theta") -> xr.Dataset:
    """Compatibility alias for the explicit plotting-closure helper."""
    return close_theta_for_plot(ds, theta_dim=theta_dim)


def finalize_polar_output(ds: xr.Dataset) -> xr.Dataset:
    """Produce an endpoint-exclusive analytical grid with truthful topology.

    A pre-existing endpoint is removed only after its coordinates, fields and
    angular auxiliary values are verified. Irregular directions remain labelled
    directional samples and are unsuitable for ordinary full-ring means/FFTs.
    """
    ds = ensure_theta_rad_dim(ds)
    values, closed = _inspect_theta(ds, "theta")
    if closed:
        ds = ds.isel(theta=slice(None, -1))
    uniform = uniform_periodic_angles(values, 2 * np.pi)
    ds.attrs.update(
        theta_reference="geodesic", theta_zero_location="north", theta_direction="clockwise",
        theta_closed=False, n_theta=int(values.size),
        theta_topology="uniform_periodic" if uniform else "directional_samples",
    )
    if uniform:
        ds.attrs["effective_azimuthal_resolution_deg"] = 360 / values.size
    else:
        ds.attrs.pop("effective_azimuthal_resolution_deg", None)
    return ds


def add_vrad_vtan_from_polar_dict(dict_polar_user: dict[str, xr.Dataset], conf):
    """Compatibility wrapper for canonical terminal-bearing wind diagnostics."""
    from frameit.processing.derived.wind import add_vrad_vtan_from_polar_dict as canonical

    return canonical(dict_polar_user, conf)
