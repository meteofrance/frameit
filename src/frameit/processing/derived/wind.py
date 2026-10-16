# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0
"""Collocated earth-relative winds and geodesic polar diagnostics."""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr

from frameit.processing.wind_reference import (
    declared_pair,
    is_prepared,
    pair_definition,
    rotation_angle,
    validate_pair_frame,
    wind_pairs,
)
from frameit.utils.units import convert_units


def wind_names(conf: Any, group: str) -> tuple[str, str]:
    """Use a unique declaration; multiple pairs require diagnostic aliases."""
    pairs = wind_pairs(conf, group)
    if len(pairs) == 1:
        return pairs[0]["u"], pairs[0]["v"]
    if group == "surface":
        aliases = getattr(conf, "tracking_var_aliases", {})
        keys = ("u10m", "v10m")
        names = aliases.get("u10m", "u10"), aliases.get("v10m", "v10")
    else:
        aliases = getattr(conf, "velocity_aliases", {})
        keys = ("u_velocity", "v_velocity")
        names = aliases.get("u_velocity", "u"), aliases.get("v_velocity", "v")
    if pairs and (not all(key in aliases for key in keys)
                  or declared_pair(conf, group, names) is None):
        raise ValueError(f"Ambiguous diagnostic wind pair in group {group!r}; "
                         f"configured aliases {names} must identify a declared pair")
    return names


def normalize_velocity_units(da: xr.DataArray, conf: Any) -> xr.DataArray:
    """Normalize units; missing units follow the AROME/MNH m/s model contract."""
    model = str(getattr(conf, "atm_model", "")).upper()
    result = convert_units(da, "velocity", assumed="m s-1" if model in {"AROME", "MNH"} else None)
    if not da.attrs.get("units"):
        result.attrs["unit_assumption_source"] = f"{model}_input_contract"
    return result


def align_wind_pair(u: xr.DataArray, v: xr.DataArray) -> tuple[xr.DataArray, xr.DataArray]:
    """Reject staggered/differently labelled pairs instead of broadcasting them."""
    if set(u.dims) != set(v.dims):
        raise ValueError("Wind components must be collocated on identical dimensions")
    for dim in u.dims:
        if u.sizes[dim] != v.sizes[dim] or (dim in u.coords) != (dim in v.coords):
            raise ValueError("Wind components require identical dimension coordinates")
    for name in set(u.coords) | set(v.coords):
        coordinate = u.coords[name] if name in u.coords else v.coords[name]
        relevant = coordinate.ndim > 0 or name in {
            "latitude", "longitude", "time", "level", "heightAboveGround",
        } or coordinate.attrs.get("standard_name") in {
            "latitude", "longitude", "time", "altitude", "height",
        }
        if not relevant:
            continue
        if (name not in u.coords or name not in v.coords
                or not u[name].variable.equals(v[name].variable)):
            raise ValueError(f"Wind components require identical coordinate {name!r}")
    for da in (u, v):
        prepared = bool(da.attrs.get("wind_collocation"))
        if not prepared and (
            any(dim.endswith(("_u", "_v")) for dim in da.dims)
            or da.attrs.get("grid") in {2, 3, 5, 6, 7, 8}
            or da.attrs.get("location") in {"u", "v", "face", "edge"}
            or da.attrs.get("stagger") not in {None, "", "mass", "center"}
            or any(c.attrs.get("c_grid_axis_shift", 0) != 0 for c in da.coords.values())
        ):
            raise ValueError(
                "Wind components have unresolved native point location; collocate first"
            )
    return xr.align(u, v.transpose(*u.dims), join="exact")


def normalize_native_wind_units(ds: xr.Dataset, conf: Any, group: str) -> xr.Dataset:
    """Normalize source units only, preserving native locations and vector basis.

    For native export: no rotation, collocation, component renaming, or frame
    relabelling. Wind values change only by the declared velocity unit scale.
    """
    out = ds.copy(deep=False)
    pairs = wind_pairs(conf, group)
    names_list = [(p["u"], p["v"]) for p in pairs] if pairs else [wind_names(conf, group)]
    for names in names_list:
        if not any(name in ds for name in names):
            continue
        pair = pair_definition(conf, group, names)
        validate_pair_frame(ds, pair)
        for name in names:
            if name in ds:
                out[name] = normalize_velocity_units(ds[name], conf)
                if not is_prepared(ds[name]):
                    out[name].attrs["wind_reference_frame"] = pair["reference_frame"]
                    out[name].attrs["wind_reference_frame_source"] = "explicit_input_declaration"
    return out


def normalize_winds(ds: xr.Dataset, conf: Any, group: str) -> xr.Dataset:
    """Convert every present declared mass-point pair to physical east/north m/s.

    Unknown fields and absent pairs do not create dependencies. A lone member
    of an unprepared pair is an error. Prepared singletons may survive variable
    selection. Repeated preparation is idempotent, including when original
    metadata and dataset source markers are retained.
    """
    pairs = wind_pairs(conf, group)
    names_list = [(p["u"], p["v"]) for p in pairs] if pairs else [wind_names(conf, group)]
    out = ds.copy(deep=False)
    for names in names_list:
        if not any(name in ds for name in names):
            continue
        pair = pair_definition(conf, group, names)
        frame = validate_pair_frame(ds, pair)
        present = [name for name in names if name in ds]
        if len(present) == 1:
            name = present[0]
            out[name] = normalize_velocity_units(ds[name], conf)
            continue
        u, v = align_wind_pair(*(normalize_velocity_units(ds[name], conf) for name in names))
        if all(is_prepared(ds[name]) for name in names):
            out[names[0]], out[names[1]] = u, v
            continue
        method = "none"
        angle = None
        if frame == "grid":
            angle = rotation_angle(ds, conf, pair)
            method = pair["rotation"]["method"]
            if pair.get("declaration") == "legacy_scalar":
                method = "legacy_grid_rotation_coordinate"
        if angle is not None:
            if not set(angle.dims) <= set(u.dims):
                raise ValueError("Wind rotation must be defined on the collocated wind grid")
            u, v, angle = xr.align(u, v, angle, join="exact")
            east = u * np.cos(angle) - v * np.sin(angle)
            north = u * np.sin(angle) + v * np.cos(angle)
        else:
            east, north = u, v
        for name, value, standard in zip(names, (east, north),
                                          ("eastward_wind", "northward_wind"), strict=True):
            attrs = dict(ds[name].attrs)
            attrs.update((u if name == names[0] else v).attrs)
            for key in ("standard_name", "grid", "GRIB_uvRelativeToGrid", "uvRelativeToGrid"):
                if key in attrs:
                    attrs.setdefault("source_" + key, attrs[key])
            attrs.update(units="m s-1", wind_reference_frame="earth",
                         source_wind_reference_frame=pair["reference_frame"],
                         wind_reference_frame_source=pair.get("declaration", "wind_pairs"),
                         standard_name=standard, frameit_wind_prepared="earth",
                         wind_rotation_method=method, wind_pair=",".join(names))
            for key in ("GRIB_uvRelativeToGrid", "uvRelativeToGrid"):
                if key in attrs:
                    attrs[key] = 0
            if "grid" in attrs:
                # MNH mass-point grid indicator; original indicator remains source_grid.
                attrs["grid"] = 1
            if angle is not None:
                attrs["wind_rotation_convention"] = "counterclockwise_from_east_to_grid_x"
                if pair["rotation"].get("coordinate"):
                    attrs["wind_rotation_coordinate"] = pair["rotation"]["coordinate"]
                for key, item in angle.attrs.items():
                    if key.startswith("rotation_"):
                        attrs[key] = item
            out[name] = value.assign_attrs(attrs)
    return out


def polar_wind_components(
    u: xr.DataArray, v: xr.DataArray, bearing: xr.DataArray
) -> tuple[xr.DataArray, xr.DataArray]:
    """Rotate collocated east/north winds in m/s using a local bearing in radians."""
    # This low-level numerical API historically accepts unitless canonical
    # arrays (m/s and radians); explicitly declared alternative units convert.
    u = convert_units(u, "velocity", assumed="m s-1")
    v = convert_units(v, "velocity", assumed="m s-1")
    bearing = convert_units(bearing, "angle", assumed="rad")
    u, v = align_wind_pair(u, v)
    u, v, bearing = xr.align(u, v, bearing, join="exact")
    if "rr" in bearing.coords:
        bearing = bearing.where(bearing["rr"] != 0)
    radial = u * np.sin(bearing) + v * np.cos(bearing)
    tangential = u * np.cos(bearing) - v * np.sin(bearing)
    for da, description in (
        (radial, "radial wind component (positive outward from storm center)"),
        (tangential, "tangential wind component (positive clockwise)"),
    ):
        da.attrs.update(
            units="m s-1", long_name=description, wind_reference_frame="earth",
            vector_basis="terminal_forward_geodesic", origin_policy="undefined_at_zero_radius",
        )
    return radial, tangential


def add_vrad_vtan_from_polar_dict(
    dict_polar_user: dict[str, xr.Dataset], conf: Any
) -> dict[str, xr.Dataset]:
    out = dict_polar_user
    for group, ds in out.items():
        pairs = wind_pairs(conf, group)
        if pairs and not any(p[component] in ds for p in pairs for component in ("u", "v")):
            continue
        ds = normalize_winds(ds, conf, group)
        out[group] = ds
        u, v = wind_names(conf, group)
        if u not in ds or v not in ds:
            continue
        if "radial_bearing" not in ds:
            raise ValueError("Polar winds require terminal-forward radial_bearing")
        radial, tangential = polar_wind_components(ds[u], ds[v], ds["radial_bearing"])
        out[group] = ds.assign(vrad=radial, vtan=tangential)
        out[group].attrs["wind_reference_frame"] = "earth"
    return out


def add_speed_from_uv_dict(
    dict_user: dict[str, xr.Dataset], conf: Any, *, speed_name: str = "wind_speed"
) -> dict[str, xr.Dataset]:
    out = dict_user
    for group, ds in out.items():
        pairs = wind_pairs(conf, group)
        if pairs and not any(p[component] in ds for p in pairs for component in ("u", "v")):
            continue
        ds = normalize_winds(ds, conf, group)
        out[group] = ds
        u, v = wind_names(conf, group)
        if u not in ds or v not in ds:
            continue
        u_da, v_da = align_wind_pair(ds[u], ds[v])
        speed = np.hypot(u_da, v_da)
        speed.attrs.update(
            units="m s-1", long_name="horizontal wind speed", wind_reference_frame="earth",
            derivation=(
                "magnitude_of_interpolated_collocated_components"
                if "radial_bearing" in ds else "magnitude_of_collocated_components"
            ),
        )
        out[group] = ds.assign({speed_name: speed})
        out[group].attrs["wind_reference_frame"] = "earth"
    return out
