# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0
"""Collocated earth-relative winds and geodesic polar diagnostics."""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr


def wind_names(conf: Any, group: str) -> tuple[str, str]:
    """Resolve surface aliases independently of the model-level pair."""
    if group == "surface":
        aliases = getattr(conf, "tracking_var_aliases", {})
        return aliases.get("u10m", "u10"), aliases.get("v10m", "v10")
    aliases = getattr(conf, "velocity_aliases", {})
    return aliases.get("u_velocity", "u"), aliases.get("v_velocity", "v")


def normalize_velocity_units(da: xr.DataArray, conf: Any) -> xr.DataArray:
    """Normalize units; missing units follow the AROME/MNH m/s model contract."""
    units = str(da.attrs.get("units") or "").lower().replace(" ", "").replace("−", "-")
    factors = {
        "": 1.0, "m/s": 1.0, "ms-1": 1.0, "ms^-1": 1.0, "ms**-1": 1.0,
        "km/h": 1.0 / 3.6, "kmh-1": 1.0 / 3.6, "knots": 0.5144444444444445,
        "knot": 0.5144444444444445, "kt": 0.5144444444444445,
        "cm/s": 0.01, "cms-1": 0.01, "cms**-1": 0.01,
    }
    if units not in factors:
        raise ValueError(f"Unsupported wind units {da.attrs.get('units')!r} on {da.name}")
    if not units and str(getattr(conf, "atm_model", "")).upper() not in {"AROME", "MNH"}:
        raise ValueError(f"Wind units required for {da.name}")
    result = da * factors[units]
    result.attrs = dict(da.attrs)
    result.attrs["units"] = "m s-1"
    return result


def align_wind_pair(u: xr.DataArray, v: xr.DataArray) -> tuple[xr.DataArray, xr.DataArray]:
    """Reject staggered/differently labelled pairs instead of broadcasting them."""
    if set(u.dims) != set(v.dims):
        raise ValueError("Wind components must be collocated on identical dimensions")
    return xr.align(u, v, join="exact")


def normalize_winds(ds: xr.Dataset, conf: Any, group: str) -> xr.Dataset:
    """Normalize collocated components before interpolation.

    Explicit grid-relative vectors require a ``grid_rotation`` coordinate:
    radians counterclockwise from geographic east to the grid x direction.
    Missing frame metadata uses the supported models' earth-relative input
    contract; set wind_reference_frame='grid' when that contract is not met.
    """
    names = wind_names(conf, group)
    out = ds.copy(deep=False)
    present = [name for name in names if name in ds]
    frames = set()
    for name in present:
        da = ds[name]
        flag = da.attrs.get("GRIB_uvRelativeToGrid")
        frame = da.attrs.get("wind_reference_frame", ds.attrs.get("wind_reference_frame"))
        if flag is not None:
            if int(flag) not in {0, 1}:
                raise ValueError(f"Invalid GRIB_uvRelativeToGrid on {name}: {flag!r}")
            flag_frame = "grid" if int(flag) else "earth"
            if frame is not None and frame != flag_frame:
                raise ValueError(f"Conflicting wind reference metadata on {name}")
            frame = flag_frame
        if frame is None:
            frame = getattr(conf, "wind_reference_frame", "earth")
            frame_source = f"{conf.atm_model}_input_contract"
        else:
            frame_source = "source_metadata"
        if frame not in {"earth", "grid"}:
            raise ValueError(f"Unknown wind reference frame {frame!r} on {name}")
        frames.add(frame)
        out[name] = normalize_velocity_units(da, conf)
        out[name].attrs.setdefault("wind_reference_frame_source", frame_source)
        out[name].attrs.setdefault("source_wind_reference_frame", frame)
    if len(frames) > 1:
        raise ValueError("Wind components have incompatible reference frames")
    if frames == {"grid"}:
        if len(present) != 2 or "grid_rotation" not in ds:
            raise ValueError("Grid-relative winds require both components and grid_rotation")
        angle = ds["grid_rotation"]
        if angle.attrs.get("units") != "rad":
            raise ValueError("grid_rotation must be in radians counterclockwise from east")
        u, v = align_wind_pair(out[names[0]], out[names[1]])
        if not set(angle.dims) <= set(u.dims):
            raise ValueError("grid_rotation must be defined on the collocated wind grid")
        u, v, angle = xr.align(u, v, angle, join="exact")
        attrs_u, attrs_v = dict(u.attrs), dict(v.attrs)
        out[names[0]] = u * np.cos(angle) - v * np.sin(angle)
        out[names[1]] = u * np.sin(angle) + v * np.cos(angle)
        out[names[0]].attrs, out[names[1]].attrs = attrs_u, attrs_v
    for name in present:
        out[name].attrs.update(wind_reference_frame="earth", units="m s-1")
        if "GRIB_uvRelativeToGrid" in out[name].attrs:
            out[name].attrs["GRIB_uvRelativeToGrid"] = 0
    if present:
        out.attrs.setdefault("source_wind_reference_frame", next(iter(frames)))
    return out


def polar_wind_components(
    u: xr.DataArray, v: xr.DataArray, bearing: xr.DataArray
) -> tuple[xr.DataArray, xr.DataArray]:
    """Rotate collocated east/north winds in m/s using a local bearing in radians."""
    if bearing.attrs.get("units", "rad") != "rad":
        raise ValueError("radial_bearing must be expressed in radians")
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
        u, v = wind_names(conf, group)
        if u not in ds or v not in ds:
            continue
        if "radial_bearing" not in ds:
            raise ValueError("Polar winds require terminal-forward radial_bearing")
        ds = normalize_winds(ds, conf, group)
        radial, tangential = polar_wind_components(ds[u], ds[v], ds["radial_bearing"])
        out[group] = ds.assign(vrad=radial, vtan=tangential)
        out[group].attrs["wind_reference_frame"] = "earth"
    return out


def add_speed_from_uv_dict(
    dict_user: dict[str, xr.Dataset], conf: Any, *, speed_name: str = "wind_speed"
) -> dict[str, xr.Dataset]:
    out = dict_user
    for group, ds in out.items():
        u, v = wind_names(conf, group)
        if u not in ds or v not in ds:
            continue
        ds = normalize_winds(ds, conf, group)
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
