"""Opt-in interpretation of user-confirmed embedded SURFEX sea-field metadata."""

import re
from pathlib import Path

import numpy as np

from frameit.processing.requests import selected_native_indices

SURFEX_FIELDS = {"SST", "SSS", "H_SEA", "LE_SEA", "FMU_SEA", "FMV_SEA", "FRAC_SEA"}


def validate_surfex_fields(fields, model, file_type, layout):
    if (not isinstance(fields, list) or any(not isinstance(name, str) or name not in SURFEX_FIELDS
                                            for name in fields) or len(set(fields)) != len(fields)):
        raise ValueError("input.netcdf.surfex_fields must list unique supported SURFEX sea fields: "
                         + ", ".join(sorted(SURFEX_FIELDS)))
    if fields and (model not in {"mesonh", "MNH"} or file_type not in {None, "", "netcdf"}
                   or layout != "time_series"):
        raise ValueError("input.netcdf.surfex_fields requires Meso-NH NetCDF time_series inputs")


def _unit_identity(value):
    """Only evidenced spelling aliases; unknown SI symbols retain their case."""
    value = str(value or "").strip()
    return {
        "kelvin": "K", "Kelvin": "K",
        "W m-2": "W/m2", "W m^-2": "W/m2", "W m**-2": "W/m2",
        "Wm-2": "W/m2", "Wm^-2": "W/m2", "Wm**-2": "W/m2",
        "Pa": "pa", "hPa": "hpa", "N/m2": "pa", "Nm-2": "pa",
        "N m-2": "pa", "N m^-2": "pa", "N m**-2": "pa",
        "kg/ms2": "pa", "kgm-1s-2": "pa", "kgm**-1s**-2": "pa",
        "kg m-1 s-2": "pa", "kg m**-1 s**-2": "pa", "fraction": "1",
        "m s-1": "ms-1", "m s^-1": "ms^-1", "m s**-1": "ms**-1",
        "km h-1": "kmh-1", "cm s-1": "cms-1", "cm s**-1": "cms**-1",
        "m2 s-2": "m2s-2", "m**2 s**-2": "m**2s**-2", "m^2 s^-2": "m^2s^-2",
    }.get(value, value)


def _units(attrs, field):
    comment = str(attrs.get("comment", ""))
    matches = re.findall(r"\(([^()]*)\)", comment)
    match = re.search(r"\(([^()]*)\)\s*$", comment)
    if len(matches) > 1:
        raise ValueError(f"SURFEX {field}: ambiguous units comment {comment!r}")
    stated = match[1].strip() if match else None
    if stated == "fraction":
        stated = "1"
    declared = attrs.get("units")
    if isinstance(declared, str) and not declared.strip():
        declared = None
    if declared is not None and not isinstance(declared, str):
        raise ValueError(f"SURFEX {field}: invalid explicit units {declared!r}")
    if not declared and not stated:
        raise ValueError(f"SURFEX {field}: missing explicit units or unambiguous unit comment")

    if declared and stated and _unit_identity(declared) != _unit_identity(stated):
        raise ValueError(f"SURFEX {field}: units {declared!r} contradict comment units {stated!r}")
    return declared or stated, "units_attribute" if declared else "source_comment"


def validate_surfex_metadata(datasets, fields):
    """Compare only interpreted quantities/support, allowing unit spelling aliases."""
    if not fields:
        return
    from frameit.io.netcdf_utils import validate_native_metadata

    metadata = []
    for ds in datasets:
        part = ds[[name for name in {*fields, "FRAC_SEA"} if name in ds]].copy(deep=False)
        for name in part.variables:
            if name in fields or name == "FRAC_SEA":
                part[name].attrs = dict(part[name].attrs, units=_unit_identity(part[name].attrs.get("units")))
        metadata.append(part)
    validate_native_metadata(metadata, model="SURFEX")


def surfex_metadata(source, field):
    """Check interpreted surface shape/physical bounds using inventory metadata only."""
    import xarray as xr

    if source["model"] != "mesonh" or source["format"] != "netcdf":
        raise ValueError("SURFEX SEA interpretation requires Meso-NH NetCDF")
    dims = set(field["dimensions"]) - {
        record["clock"] for record in source["record_inventory"]}
    if dims != {"nj", "ni"}:
        raise ValueError(f"SURFEX {field['name']} requires native surface nj/ni dimensions")
    for grid_id in field.get("grid_ids", [field["grid_id"]]):
        grid = source["native_grids"][grid_id]
        ds = xr.Dataset(coords={
            name: xr.Variable(item["dimensions"], item["values"], attrs=item["attributes"])
            for name, item in grid["coordinates"].items() if name in {"nj", "ni"}})
        for axis in ("nj", "ni"):
            if axis not in ds or "c_grid_dynamic_range" not in ds[axis].attrs:
                raise ValueError(f"SURFEX physical support requires {axis}.c_grid_dynamic_range")
            selected_native_indices(ds, {"level_domain": "physical", "all_levels": True}, axis)
    attrs = dict(field["attributes"])
    declared_units = source.get("declaration", {}).get(
        "field_metadata", {}).get(field["name"], {}).get("units")
    completed = not str(attrs.get("units", "")).strip() and not re.search(
        r"\([^()]*\)\s*$", str(attrs.get("comment", ""))) and declared_units
    if completed:
        attrs["units"] = declared_units
    units, origin = _units(attrs, field["name"])
    return dict(attrs, units=units, surfex_units_source="declaration" if completed else origin)


def prepare_surfex(ds, conf):
    """Mask only explicitly selected SEA fields without additional value weighting."""
    declared = getattr(conf, "netcdf_surfex_fields", [])
    validate_surfex_fields(declared, getattr(conf, "atm_model", None),
                           getattr(conf, "file_type", "netcdf"),
                           getattr(conf, "netcdf_file_layout", "time_series"))
    requested = {name for spec in getattr(conf, "requested_variables_user", {}).values()
                 for name in spec.get("variables", [])}
    fields = [name for name in declared if name in requested]
    if not fields:
        return ds
    if "FRAC_SEA" not in ds:
        raise ValueError("SURFEX selected SEA fields require FRAC_SEA support")
    missing = set(fields) - set(ds)
    if missing:
        raise ValueError(f"SURFEX missing selected fields {sorted(missing)}")
    # Backend-only metadata opens must not decode thermal arrays during masking.
    lazy = ds[list(dict.fromkeys(["FRAC_SEA", *fields]))].chunk({})
    fraction = lazy.FRAC_SEA.where(lazy.FRAC_SEA != 999.)
    if set(fraction.dims) not in ({"nj", "ni"}, {"time", "nj", "ni"}):
        raise ValueError("SURFEX FRAC_SEA requires native nj/ni dimensions")
    positions = {}
    for axis in ("nj", "ni"):
        if axis not in ds.coords or "c_grid_dynamic_range" not in ds[axis].attrs:
            raise ValueError(f"SURFEX physical support requires {axis}.c_grid_dynamic_range")
        positions[axis] = selected_native_indices(ds, {"level_domain": "physical", "all_levels": True}, axis)
    physical = fraction.isel(positions)
    if bool((~np.isfinite(physical) | (physical < 0) | (physical > 1)).any()):
        raise ValueError("SURFEX FRAC_SEA physical support must be finite and within [0,1]")
    result, records = ds.copy(deep=False), []
    for name in dict.fromkeys(["FRAC_SEA", *fields]):
        if name not in ds:
            raise ValueError(f"SURFEX missing selected field {name}")
        if set(ds[name].dims) not in ({"nj", "ni"}, {"time", "nj", "ni"}):
            raise ValueError(f"SURFEX {name} requires native surface nj/ni dimensions")
        units, origin = _units(ds[name].attrs, name)
        value = fraction if name == "FRAC_SEA" else lazy[name].where((lazy[name] != 999.) & (fraction > 0))
        value.attrs = dict(ds[name].attrs, units=units, surfex_units_source=origin,
                           surfex_source_invalid_value=999.)
        if name != "FRAC_SEA":
            ancillary = str(value.attrs.get("ancillary_variables", "")).split()
            value.attrs.update(ancillary_variables=" ".join(dict.fromkeys([*ancillary, "FRAC_SEA"])),
                               surfex_support="FRAC_SEA > 0; no additional fraction weighting applied")
        result[name] = value
        records.append({"source_id": Path(ds.encoding.get("source", "in_memory")).name,
                        "field": name, "units": units, "units_source": origin,
                        "invalid_value": 999., "support": "fraction" if name == "FRAC_SEA" else "FRAC_SEA > 0",
                        "value_weighting": "unchanged", "contract_source": "user_confirmed_source_metadata"})
    params = getattr(conf, "simulation_parameter", None)
    if params is not None:
        previous = params.setdefault("surfex_provenance", [])
        for record in records:
            if record not in previous:
                previous.append(record)
    result.attrs = dict(result.attrs, surfex_interpreted_fields=" ".join(fields),
                        surfex_interpretation="source999 invalid; units from attribute/comment; positive sea support; "
                                              "no value weighting or inferred flux timing/sign/basis")
    return result
