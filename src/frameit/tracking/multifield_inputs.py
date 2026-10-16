"""Header validation and per-timestamp model preparation for multi-field tracking."""

import numpy as np
import xarray as xr

from frameit.processing.derived.wind import normalize_winds
from frameit.processing.wind_reference import wind_pairs
from frameit.utils.units import convert_units, normalize_geography, unit_metadata

from .multifield_vortex import pressure_interpolate
from .pressure_centroid import G0
from .pressure_centroid_inputs import prepare_mnh_inputs, resolve_mnh_fields

LEVELS_HPA = (850., 700., 500.)


def mnh_error(context, detail):
    return ValueError(
        f"multifield_vortex: incompatible MNH inputs ({context}).\n{detail}\n"
        "Supply MSLP, UM10/VM10, native horizontal winds, absolute pressure "
        "(PABST or PRES) and ALT or the explicitly supported height formula.\n"
        "MNH 6.0 DIAG1.nam &NAM_DIAG: LTPZH=.TRUE. writes ALT/PRES; "
        "LVAR_RS=.TRUE., LWIND_ZM=.TRUE. write UT_ZM/VT_ZM; LMSLP=.TRUE. writes MSLP.\n"
        "Include the surface diagnostics for your MNH/SURFEX setup. Retain physical "
        "levels bracketing 850, 700 and 500 hPa. Declare both wind pairs and any rotation "
        "using input.wind_pairs. Declare the model's constant gravity as "
        "tracking.multifield_vortex.mnh_gravity_m_s2 to convert geometric altitude "
        "to geopotential height. Check the DIAG instructions for your MNH version."
    )


def selected_mnh_source(ds, conf):
    """Honour an explicitly selected standard MNH pair before candidate discovery."""
    declarations = wind_pairs(conf, "level") if conf is not None else []
    known = {("UT", "VT"), ("UT_ZM", "VT_ZM")}
    selected = [(p["u"], p["v"]) for p in declarations if (p["u"], p["v"]) in known]
    if len(selected) > 1:
        raise ValueError("multifield_vortex requires one declared MNH model-level wind pair")
    if selected:
        ds = ds.drop_vars([n for pair in known if pair != selected[0] for n in pair if n in ds])
    return ds


def resolve_mnh(ds, conf, context="Dataset"):
    try:
        fields = resolve_mnh_fields(selected_mnh_source(ds, conf), context)
    except ValueError as exc:
        # Reuse the native physical-field checks, with this method's own target
        # levels and preparation guidance rather than the 2-km centroid recipe.
        detail = str(exc).split("\nMeso-NH 6.0 DIAG preparation")[0]
        detail = detail.replace("pressure_centroid:", "native field checks:")
        raise mnh_error(context, detail) from exc
    if getattr(conf, "multifield_vortex", {}).get("mnh_gravity_m_s2") is None:
        raise mnh_error(context,
                        "The MNH geometric-to-geopotential height convention is unresolved.")
    return fields


def inspect_inputs(datasets, conf, context="selected-inputs"):
    """Validate one input file, including all required variable/level combinations."""
    if conf.atm_model == "MNH":
        if len(datasets) != 1:
            raise mnh_error(context, "Native MNH NetCDF input is required")
        fields = resolve_mnh(datasets[0], conf, context)
        from .pressure_centroid_inputs import mnh_wind_frames

        frames = mnh_wind_frames(datasets[0], fields, conf)
        return {"pressure": fields.pressure, "height": list(fields.height),
                "winds": [fields.u, fields.v], "pressure_levels_hpa": list(LEVELS_HPA),
                "wind_reference_frames": frames,
                "mnh_gravity_m_s2": conf.multifield_vortex["mnh_gravity_m_s2"]}
    problems = []
    all_times = {str(np.datetime64(t, "ns")) for ds in datasets
                 for coord in ("time", "valid_time") if coord in ds.coords
                 for t in np.atleast_1d(ds[coord].values)}
    for name in ("prmsl", "u10", "v10"):
        candidates = [ds[name] for ds in datasets if name in ds]
        if not candidates:
            problems.append(f"missing surface {name}")
        else:
            unit_metadata(candidates[0], "pressure" if name == "prmsl" else "velocity")
            coverage = [entry for da in candidates for entry in
                        da.attrs.get("_frameit_level_times", [])]
            if coverage:
                for stamp in sorted(all_times):
                    if not any(t == stamp for _, t in coverage):
                        problems.append(f"missing surface {name}, time={stamp}")
    for name in ("u", "v", "z"):
        required = LEVELS_HPA[:2] if name == "z" else LEVELS_HPA
        available = set()
        coverage = []
        for ds in datasets:
            if name not in ds or "isobaricInhPa" not in ds:
                continue
            unit_metadata(ds[name], "geopotential" if name == "z" else "velocity")
            levels = convert_units(ds.isobaricInhPa, "pressure", target="hPa", assumed="hPa")
            available.update(np.atleast_1d(levels.values).astype(float))
            coverage.extend(ds[name].attrs.get("_frameit_level_times", []))
        for level in required:
            if not any(abs(value - level) < .01 for value in available):
                problems.append(f"missing {name} at {level:g} hPa")
        if coverage:
            for stamp in sorted(all_times):
                for level in required:
                    if not any(abs(p - level) < .01 and t == stamp for p, t in coverage):
                        problems.append(f"missing {name} at {level:g} hPa, time={stamp}")
    if problems:
        raise ValueError(f"multifield_vortex ({context}): " + "; ".join(problems) +
                         ". Supply AROME pressure-level u/v at 850/700/500 hPa, "
                         "z at 850/700 hPa, and prmsl/u10/v10.")
    return {"pressure_levels_hpa": list(LEVELS_HPA), "height": "z/9.80665",
            "winds": ["u", "v"], "surface": ["prmsl", "u10", "v10"]}


def mnh_loading_fields(ds, conf):
    fields = resolve_mnh(ds, conf)
    return fields, fields.requests()


def canonical_inputs(ds, conf):
    """Prepare lazy arrays; materialize only one timestamp in iter_fields."""
    if ds.attrs.get("multifield_input_stage") == "native_mass_earth":
        return ds
    if conf.atm_model == "MNH":
        resolve_mnh(ds, conf)
        try:
            prepared = prepare_mnh_inputs(selected_mnh_source(ds, conf), conf)
        except ValueError as exc:
            detail = str(exc).split("\nMeso-NH 6.0 DIAG preparation")[0]
            detail = detail.replace("pressure_centroid:", "native field checks:")
            raise mnh_error("native preparation", detail) from exc
        prepared.attrs = {key.replace("pressure_centroid_", "multifield_"): value
                          for key, value in prepared.attrs.items()}
        prepared.attrs["multifield_input_stage"] = "native_mass_earth"
        prepared.attrs["multifield_source_height_reference"] = prepared.attrs.pop(
            "multifield_height_reference")
        prepared.attrs["multifield_height_reference"] = "geopotential_height"
        prepared.attrs["multifield_height_conversion"] = "H=z_geometric*g_model/9.80665"
        return prepared
    ds = normalize_geography(ds, conf)
    for group in ("surface", "isobaricInhPa"):
        ds = normalize_winds(ds, conf, group)
    inspect_inputs([ds], conf)
    result = xr.Dataset({name: ds[name] for name in ("u", "v", "z")})
    result["mslp"] = convert_units(ds.prmsl, "pressure")
    result["u10m"], result["v10m"] = ds.u10, ds.v10
    result["z"] = (convert_units(ds.z, "geopotential") / G0).assign_attrs(
        units="m", standard_name="geopotential_height")
    result.attrs.update(multifield_height_source="z/9.80665",
                        multifield_height_reference="geopotential_height")
    return result


def iter_fields(ds, conf):
    """Yield canonical 2-D/three-pressure-level records on the original mass grid."""
    spatial = ("nj", "ni") if conf.atm_model == "MNH" else tuple(
        d for d in ds.mslp.dims if d != "time")
    if len(spatial) != 2:
        raise ValueError("multifield_vortex requires one realization and two horizontal dimensions")
    for index, stamp in enumerate(ds.time.values):
        part = ds.isel(time=index)
        lon, lat = xr.broadcast(part.longitude, part.latitude)
        record = {"time": stamp, "lon": np.asarray(lon.transpose(*spatial), float),
                  "lat": np.asarray(lat.transpose(*spatial), float)}
        for name in ("mslp", "u10m", "v10m"):
            record[name] = np.asarray(part[name].transpose(*spatial), float)
        if conf.atm_model == "MNH":
            p = np.asarray(part.pressure.transpose("level", *spatial), float)
            values = {name: np.asarray(part[name].transpose("level", *spatial), float)
                      for name in ("u", "v", "height")}
            record.update(pressure_interpolate(p, values))
            record["height"] *= conf.multifield_vortex["mnh_gravity_m_s2"] / G0
        else:
            for name in ("u", "v", "z"):
                record["height" if name == "z" else name] = np.asarray(
                    part[name].sel(isobaricInhPa=list(LEVELS_HPA)).transpose(
                        "isobaricInhPa", *spatial), float)
        for name in ("u", "v"):
            if not all(np.isfinite(layer).any() for layer in record[name]):
                raise ValueError(f"multifield_vortex at {stamp}: no valid {name} coverage "
                                 "at a required 850/700/500-hPa surface; check native brackets")
        if not all(np.isfinite(layer).any() for layer in record["height"][:2]):
            raise ValueError(f"multifield_vortex at {stamp}: no valid 850/700-hPa heights")
        yield record
