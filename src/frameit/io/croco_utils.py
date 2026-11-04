"""Native CROCO Vtransform=2 history metadata; no physical-depth calculation."""

import numpy as np
import xarray as xr


def validate_croco_coefficients(datasets):
    """A history sequence must not inherit one file's different sigma definition."""
    reference = {}
    for ds in datasets:
        if not ds.data_vars:
            continue
        for axis in ("s_rho", "s_w"):
            if axis not in ds:
                continue
            tokens = ds[axis].attrs["formula_terms"].split()
            terms = dict(zip((token.rstrip(":") for token in tokens[::2]), tokens[1::2]))
            for name in (axis, terms["C"], terms["depth_c"]):
                values = ds[name].values
                if name in reference and not np.array_equal(values, reference[name]):
                    raise ValueError(f"CROCO {name}: conflicting native sigma definitions across files")
                reference[name] = values


def prepare_croco(ds: xr.Dataset, conf) -> xr.Dataset:
    """Validate native rho scalars and retain explicit sigma formula dependencies."""
    if ds.attrs.get("type") != "CROCO history file":
        raise ValueError("CROCO currently requires the declared history file family")
    if "time" not in ds or ds.time.dims != ("time",) or not np.issubdtype(ds.time.dtype, np.datetime64):
        raise ValueError("CROCO requires a decoded Gregorian time(time) clock")
    for name in ("time", "scrum_time"):
        if name not in ds:
            continue
        clock = ds[name]
        calendar = clock.encoding.get("calendar", clock.attrs.get("calendar", "standard"))
        if calendar not in {"standard", "gregorian", "proleptic_gregorian"}:
            raise ValueError(f"CROCO unsupported calendar {calendar!r}")
        if not clock.variable.equals(ds.time.variable) or np.isnat(clock.values).any():
            raise ValueError("CROCO time/scrum_time clocks disagree or contain missing times")
    declarations = [ds.attrs["Vtransform"]] if "Vtransform" in ds.attrs else []
    if "Vtransform" in ds:
        if ds.Vtransform.ndim:
            raise ValueError("CROCO Vtransform must be scalar")
        declarations.append(ds.Vtransform.item())
    for axis in ("s_rho", "s_w"):
        if axis in ds and "Vtransform" in ds[axis].attrs:
            declarations.append(ds[axis].attrs["Vtransform"])
    try:
        valid = bool(declarations) and all(float(value) == 2 for value in declarations)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("CROCO requires consistent explicit Vtransform=2 declarations")
    result = ds.copy(deep=False)
    for axis in ("s_rho", "s_w"):
        if axis not in ds.dims:
            continue
        if axis not in ds.coords or ds[axis].dims != (axis,):
            raise ValueError(f"CROCO requires native {axis} coordinates")
        values = ds[axis].values
        if (not np.isfinite(values).all() or np.any(values < -1) or np.any(values > 0)
                or np.any(np.diff(values) <= 0)):
            raise ValueError(f"CROCO {axis} must increase from -1 toward 0")
        standard = ds[axis].attrs.get("standard_name")
        allowed = {"ocean_s_coordinate_g2"}
        if axis == "s_w":
            allowed.add("ocean_s_coordinate_g2_at_w_location")
        if standard not in allowed or ds[axis].attrs.get("positive") != "up":
            raise ValueError(f"CROCO {axis} requires the Vtransform=2 formula definition")
        tokens = str(ds[axis].attrs.get("formula_terms", "")).split()
        terms = dict(zip((token.rstrip(":") for token in tokens[::2]), tokens[1::2]))
        if (len(tokens) != 10 or any(not token.endswith(":") for token in tokens[::2])
                or set(terms) != {"s", "C", "eta", "depth", "depth_c"}
                or terms["s"] != axis or any(name not in ds for name in terms.values())):
            raise ValueError(f"CROCO {axis} has missing or invalid formula dependencies")
        curve, eta, depth, critical = (ds[terms[key]] for key in ("C", "eta", "depth", "depth_c"))
        if (curve.dims != (axis,) or eta.dims != ("time", "eta_rho", "xi_rho")
                or depth.dims != ("eta_rho", "xi_rho") or critical.ndim):
            raise ValueError(f"CROCO {axis} formula dependencies have incompatible native dimensions")
        if (not np.isfinite(curve.values).all() or np.any(curve.values < -1) or np.any(curve.values > 0)
                or curve.attrs.get("units") not in {None, "1"}
                or not np.isfinite(critical.item()) or critical.item() <= 0):
            raise ValueError(f"CROCO {axis} has invalid stretching/critical depth")
        metre_units = {"m", "meter", "metre", "meters", "metres"}
        if any(value.attrs.get("units") not in metre_units for value in (eta, depth, critical)):
            raise ValueError(f"CROCO {axis} formula lengths require explicit metre units")
        if ds[axis].attrs.get("units") not in {None, "1"}:
            raise ValueError(f"CROCO {axis} is dimensionless, not physical depth")
        index = f"{axis}_source_native_index"
        result = result.assign_coords({index: (axis, np.arange(ds.sizes[axis]), {
            "units": "1", "long_name": f"zero-based native source {axis} index"})})
        if standard == "ocean_s_coordinate_g2_at_w_location":
            result[axis].attrs = dict(result[axis].attrs, source_standard_name=standard,
                                      standard_name="ocean_s_coordinate_g2")
    for name in ("lat_rho", "lon_rho"):
        if name not in ds or ds[name].dims != ("eta_rho", "xi_rho") or not ds[name].attrs.get("units"):
            raise ValueError(f"CROCO requires explicit native rho geography {name}")
    requested = {name for spec in getattr(conf, "requested_variables_user", {}).values()
                 for name in spec.get("variables", [])}
    if requested & {"wind_speed", "vrad", "vtan"}:
        raise ValueError("CROCO ocean fields do not admit atmospheric wind diagnostics")
    if any(name in ds and set(ds[name].dims) & {"xi_u", "eta_v"} for name in requested):
        raise ValueError("CROCO native face/current analysis is not yet qualified; rho scalars remain available")
    if getattr(conf, "compute_polar_proj", False):
        raise ValueError("CROCO sigma polar metadata/analysis is not yet qualified; native extraction remains available")
    return result.set_coords(["lat_rho", "lon_rho", *(["scrum_time"] if "scrum_time" in result else [])])
