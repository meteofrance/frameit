# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Coordinate-based MNH wind preparation before cropping and level selection."""

from __future__ import annotations

import numpy as np
import xarray as xr

from frameit.processing.derived.wind import (
    add_speed_from_uv_dict,
    normalize_velocity_units,
    normalize_winds,
)
from frameit.processing.wind_reference import wind_pairs
from frameit.utils.units import convert_units


def interpolate_staggered(
    da: xr.DataArray, source_dim: str, target: xr.DataArray
) -> xr.DataArray:
    """Interpolate native brackets without extrapolation or lone-edge substitution.

    MNH level coordinates are computational coordinates, not an assumption of
    equally spaced physical altitude. The model's mass coordinates specify the
    actual interpolation targets.
    """
    if source_dim not in da.coords or target.ndim != 1:
        raise ValueError(f"Native coordinates required to collocate {da.name} on {source_dim}")
    source_coordinate, target_coordinate = da[source_dim], target
    if source_coordinate.attrs.get("units") != target.attrs.get("units"):
        source_coordinate = convert_units(source_coordinate, "distance", assumed="m")
        target_coordinate = convert_units(target_coordinate, "distance", assumed="m")
    values = np.asarray(source_coordinate.values, dtype=float)
    if values.size < 2 or not np.isfinite(values).all():
        raise ValueError(f"Invalid native coordinate {source_dim}")
    differences = np.diff(values)
    if not (np.all(differences > 0) or np.all(differences < 0)):
        raise ValueError(f"Native coordinate {source_dim} must be strictly monotone")
    if not np.isfinite(target.values).all():
        raise ValueError("Mass-point coordinates must be finite")
    # Gather the two native brackets instead of xarray.interp's whole-axis
    # rechunking. Subsequent spatial cropping can then cull unrelated lazy
    # source chunks rather than computing full-domain wind arrays.
    order = np.arange(values.size)
    if differences[0] < 0:
        order = order[::-1]
    sorted_values = values[order]
    points = np.asarray(target_coordinate.values, dtype=float)
    upper = np.searchsorted(sorted_values, points, side="right")
    lower = np.clip(upper - 1, 0, values.size - 1)
    upper = np.clip(upper, 0, values.size - 1)
    denominator = sorted_values[upper] - sorted_values[lower]
    weights = np.divide(
        points - sorted_values[lower], denominator,
        out=np.zeros_like(points), where=denominator != 0,
    )
    index_coords = {target.dims[0]: target.values}
    # Same-name indexers must not carry target labels until after gathering:
    # xarray otherwise compares them with the original source labels in isel.
    gather_coords = {} if source_dim == target.dims[0] else index_coords
    low = da.isel({source_dim: xr.DataArray(order[lower], dims=target.dims, coords=gather_coords)})
    high = da.isel({source_dim: xr.DataArray(order[upper], dims=target.dims, coords=gather_coords)})
    # Their auxiliary native-coordinate labels differ; only the mass labels
    # participate in arithmetic alignment.
    if source_dim != target.dims[0]:
        low, high = low.drop_vars(source_dim), high.drop_vars(source_dim)
    else:
        low = low.assign_coords({source_dim: target})
        high = high.assign_coords({source_dim: target})
    weight = xr.DataArray(weights, dims=target.dims, coords=index_coords)
    result = xr.where(weight == 0, low, xr.where(weight == 1, high,
                                              low * (1 - weight) + high * weight))
    mapped = xr.DataArray(
        (points >= sorted_values[0]) & (points <= sorted_values[-1]),
        dims=target.dims, coords=index_coords,
    )
    result = result.where(mapped).assign_coords({target.dims[0]: target})
    result = result.transpose(*(target.dims[0] if d == source_dim else d for d in da.dims))
    if source_dim != target.dims[0] and source_dim in result.coords:
        result = result.drop_vars(source_dim)
    result.attrs = dict(da.attrs)
    if "grid" in result.attrs:
        result.attrs.setdefault("source_grid", result.attrs["grid"])
        result.attrs["grid"] = 1
    result.attrs["wind_collocation"] = "native_coordinate_linear_strict"
    return result


def prepare_native_mnh(ds: xr.Dataset, conf) -> tuple[xr.Dataset, xr.DataArray | None]:
    """Prepare U/V and a separate mass-point W while all native neighbours exist.

    Native W remains unchanged for requested Cartesian interface products. Its
    independently prepared counterpart is consumed by the polar pipeline.
    """
    out = ds.copy(deep=False)
    # Horizontal coordinate units may differ between stored face/mass axes.
    # Their physical positions, rather than their numeric labels, set brackets.
    for dim in (conf.name_lon_dim, conf.name_lat_dim):
        for name in (dim, dim + "_u", dim + "_v"):
            if name in out.coords and out[name].attrs.get("units"):
                out = out.assign_coords({name: convert_units(out[name], "distance")})
    aliases = conf.velocity_aliases
    pairs = wind_pairs(conf, conf.name_vertical_dim)
    components = [(p[c], suffix) for p in pairs for c, suffix in (("u", "_u"), ("v", "_v"))]
    if not pairs:
        components = [(aliases.get("u_velocity", "UT"), "_u"),
                      (aliases.get("v_velocity", "VT"), "_v")]
    for name, suffix in components:
        if name not in out:
            continue
        da = out[name].reset_coords(drop=True)
        for mass in (conf.name_lon_dim, conf.name_lat_dim):
            if mass + suffix in da.dims:
                if mass not in out.coords:
                    raise ValueError(f"Missing native mass coordinate {mass}")
                if np.array_equal(da[mass + suffix].values, out[mass].values):
                    da = da.rename({mass + suffix: mass})
                else:
                    da = interpolate_staggered(da, mass + suffix, out[mass])
            elif mass not in da.dims:
                raise ValueError(f"Unrecognized native horizontal grid for {name}")
        if "grid" in da.attrs:
            da.attrs.setdefault("source_grid", da.attrs["grid"])
            da.attrs["grid"] = 1
        out[name] = da
        out[name].attrs["wind_collocation"] = "native_coordinate_linear_strict"
    out = normalize_winds(out, conf, conf.name_vertical_dim)
    out = normalize_winds(out, conf, "surface")
    w_name = aliases.get("w_velocity", "WT")
    mass_w = None
    if w_name in ds:
        out[w_name] = normalize_velocity_units(out[w_name], conf)
    if w_name in ds and "level_w" in ds[w_name].dims:
        if conf.name_vertical_dim not in ds.coords:
            raise ValueError("W collocation requires the native mass vertical coordinate")
        mass_w = interpolate_staggered(
            out[w_name], "level_w", ds[conf.name_vertical_dim]
        )
    return out, mass_w


def _collocate_w_to_zC(w, *, zC_name, zC_coord, policy="strict"):
    """Direct-call compatibility helper using coordinates, never selected-array lengths."""
    if policy not in {"strict", "partial"}:
        raise ValueError("policy must be 'partial' or 'strict'")
    if zC_name in w.dims:
        return w.sel({zC_name: zC_coord})
    if "level_w" not in w.dims:
        raise ValueError("W requires an identified native level_w dimension")
    return interpolate_staggered(w, "level_w", zC_coord)


def _collocate_box_component(da, ds, mass, staggered, axis):
    """Compatibility for cropped arrays retaining their actual coordinate pairs."""
    if mass not in ds.coords or staggered not in ds.coords:
        raise ValueError(f"Native mass/staggered coordinates required for {da.name}")
    target, source = ds[mass], ds[staggered]
    delta = source.diff(axis).median(axis, skipna=True)
    forward = (target - source) * delta >= 0
    other_source = xr.where(forward, source.shift({axis: -1}), source.shift({axis: 1}))
    other_value = xr.where(forward, da.shift({axis: -1}), da.shift({axis: 1}))
    weight = (target - source) / (other_source - source)
    valid = (weight >= 0) & (weight <= 1) & np.isfinite(da) & np.isfinite(other_value)
    result = xr.where(
        target == source, da, (da * (1 - weight) + other_value * weight).where(valid)
    )
    result.attrs = dict(da.attrs)
    result.attrs["wind_collocation"] = "coordinate_pair_linear_strict"
    return result


def collocate_winds(
    dico_user: dict[str, xr.Dataset], *, conf, policy: str = "strict",
    drop_level_w_group: bool = True,
) -> dict[str, xr.Dataset]:
    """Consume native-prepared winds, or collocate explicitly bracketed inputs.

    ``partial`` is accepted for API compatibility but no longer extrapolates an
    unavailable collocation neighbour. The standard loader prepares winds before
    extraction/subsetting; direct calls must retain coordinates and brackets.
    """
    if policy not in {"partial", "strict"}:
        raise ValueError("policy must be 'partial' or 'strict'")
    if str(conf.atm_model).upper() != "MNH":
        return dict(dico_user)
    out = select_vertical_velocity(
        dico_user, conf, "mass", retain_interfaces=not drop_level_w_group)
    mass_group = conf.name_vertical_dim
    aliases = conf.velocity_aliases
    w_name = aliases.get("w_velocity", "WT")
    if mass_group not in out:
        if any(w_name in ds for ds in out.values()):
            raise ValueError("W-only polar preparation requires native mass-level dependencies")
        return out
    ds = out[mass_group]
    if any(
        name in ds and any(dim.endswith(("_u", "_v")) for dim in ds[name].dims)
        for name in (aliases.get("u_velocity", "UT"), aliases.get("v_velocity", "VT"))
    ):
        ds, native_w = prepare_native_mnh(ds, conf)
        if native_w is not None:
            ds[w_name] = native_w
        out[mass_group] = ds
    for name, mass, suffix, axis in (
        (aliases.get("u_velocity", "UT"), conf.name_lon_dim, "_u", "x_box"),
        (aliases.get("v_velocity", "VT"), conf.name_lat_dim, "_v", "y_box"),
    ):
        if name not in ds or ds[name].attrs.get("wind_collocation"):
            continue
        if all(d in ds[name].dims for d in (conf.name_lon_dim, conf.name_lat_dim)):
            # Already mass-point inputs need no private preparation marker.
            continue
        elif mass + suffix in ds[name].dims and mass in ds.coords:
            ds[name] = interpolate_staggered(ds[name], mass + suffix, ds[mass])
        elif axis in ds[name].dims:
            ds[name] = _collocate_box_component(ds[name], ds, mass, mass + suffix, axis)
        else:
            raise ValueError(f"Native staggered coordinates required for {name}")
    for key, source in list(out.items()):
        if key != mass_group and w_name in source and "level_w" in source[w_name].dims:
            if w_name not in ds or not ds[w_name].attrs.get("wind_collocation"):
                ds[w_name] = _collocate_w_to_zC(
                    source[w_name], zC_name=mass_group, zC_coord=ds[mass_group]
                )
            if drop_level_w_group:
                remaining = source.drop_vars(w_name)
                if remaining.data_vars:
                    out[key] = remaining
                else:
                    out.pop(key)
    return add_speed_from_uv_dict(out, conf)


def select_vertical_velocity(groups, conf, location, *, retain_interfaces=False):
    """Choose W's representation without changing other fields or vector bases.

    The sidecar was interpolated on the complete source before selection. Only
    W moves to the mass group; other interface quantities keep their own levels.
    """
    if location not in {"interfaces", "mass"}:
        raise ValueError("vertical_velocity must be interfaces or mass")
    out = {key: ds.copy(deep=False) for key, ds in groups.items()}
    mass = conf.name_vertical_dim
    w_name = conf.velocity_aliases.get("w_velocity", "WT")
    for group, source in list(out.items()):
        if "_frameit_mass_w" not in source:
            continue
        if location == "mass":
            w = source["_frameit_mass_w"].rename(w_name)
            w.attrs = dict(w.attrs, vertical_location="mass")
            if mass in out:
                w = w.sel({mass: out[mass][mass]})
                out[mass][w_name] = w
            else:
                out[mass] = w.to_dataset()
                out[mass].attrs = dict(source.attrs)
        remove = ["_frameit_mass_w"]
        if location == "mass" and not retain_interfaces:
            remove.append(w_name)
        remaining = source.drop_vars(remove, errors="ignore")
        if mass in remaining.dims and group != mass and not any(
            mass in value.dims for value in remaining.data_vars.values()
        ):
            remaining = remaining.drop_dims(mass)
        if remaining.data_vars:
            out[group] = remaining
        else:
            out.pop(group, None)
    return out
