"""Explicit, lazy unit conversions at scientific input boundaries."""

from __future__ import annotations

import numpy as np


def unit_key(value):
    return str(value or "").lower().replace(" ", "").replace("−", "-")


UNITS = {
    "velocity": ("m s-1", {
        "m/s": 1, "ms-1": 1, "ms^-1": 1, "ms**-1": 1,
        "km/h": 1 / 3.6, "kmh-1": 1 / 3.6,
        "knots": 0.5144444444444445, "knot": 0.5144444444444445,
        "kt": 0.5144444444444445, "cm/s": .01, "cms-1": .01, "cms**-1": .01,
    }),
    "distance": ("m", {"m": 1, "meter": 1, "metre": 1, "meters": 1,
                         "metres": 1, "km": 1000, "kilometres": 1000,
                         "kilometers": 1000, "cm": .01}),
    "angle": ("rad", {"rad": 1, "radian": 1, "radians": 1,
                      "degree": np.pi / 180, "degrees": np.pi / 180,
                      "degrees_east": np.pi / 180, "degrees_north": np.pi / 180}),
    "pressure": ("Pa", {"pa": 1, "hpa": 100, "mbar": 100}),
    "geopotential": ("m2 s-2", {"m**2s**-2": 1, "m2s-2": 1,
                                "m2s**-2": 1, "m^2s^-2": 1, "m2/s2": 1}),
}


def convert_units(da, quantity, *, target=None, assumed=None):
    """Convert values and metadata together, without computing field arrays.

    ``assumed`` is reserved for documented adapter/constructor contracts.
    """
    canonical, factors = UNITS[quantity]
    declared = da.attrs.get("units")
    source = declared or assumed
    key = unit_key(source)
    destination = target or canonical
    if key not in factors or unit_key(destination) not in factors:
        raise ValueError(f"{da.name}: unsupported {quantity} units {declared!r}")
    factor = factors[key] / factors[unit_key(destination)]
    result = da.copy(deep=False) if factor == 1 else da * factor
    result.attrs = dict(da.attrs)
    result.attrs["units"] = destination
    if not declared:
        result.attrs["unit_assumption"] = str(assumed)
    if factor != 1:
        result.attrs.setdefault("source_units", str(source))
    return result


def unit_metadata(da, quantity, **options):
    """Validate a unit declaration without evaluating a backend field array."""
    import xarray as xr

    probe = xr.DataArray(0., name=da.name, attrs=dict(da.attrs))
    return convert_units(probe, quantity, **options).attrs


def normalize_geography(ds, conf):
    """Supported model adapters use degrees when geographic units are absent."""
    out = ds.copy(deep=False)
    geography = {getattr(conf, "name_latitude", "latitude"): "degrees_north",
                 getattr(conf, "name_longitude", "longitude"): "degrees_east"}
    # Native exports retain each face's geography. Normalize these before files
    # are combined too, rather than labelling later radian values as degrees.
    for name, value in ds.variables.items():
        standard = str(value.attrs.get("standard_name", ""))
        if name in {"latitude_u", "latitude_v", "lat_u", "lat_v"} or standard in {
            "latitude", "latitude_at_u_location", "latitude_at_v_location"
        }:
            geography[name] = "degrees_north"
        elif name in {"longitude_u", "longitude_v", "lon_u", "lon_v"} or standard in {
            "longitude", "longitude_at_u_location", "longitude_at_v_location"
        }:
            geography[name] = "degrees_east"
    for name, units in geography.items():
        if name in out:
            converted = convert_units(out[name], "angle", target=units, assumed=units)
            if not ds[name].attrs.get("units"):
                converted.attrs["unit_assumption_source"] = f"{conf.atm_model}_input_contract"
            out = out.assign_coords({name: converted})
    return out
