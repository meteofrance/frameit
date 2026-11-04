"""CROCO Vtransform=2 native history and explicitly selected current analysis."""

from pathlib import Path

import numpy as np
import xarray as xr


def polar_fields(conf):
    return {name for spec in getattr(conf, "polar_variables", {}).values()
            for name in spec.get("variables", [])} if getattr(conf, "compute_polar_proj", False) else set()


def current_pairs(conf):
    """Only declared current names use the existing mass/Earth selector."""
    requested = {name for spec in getattr(conf, "requested_variables_user", {}).values()
                 for name in spec.get("variables", [])}
    analysis = getattr(conf, "cartesian_horizontal_winds", "native") == "mass_earth"
    return [pair for pair in (("u", "v"), ("ubar", "vbar"))
            if (requested if analysis else polar_fields(conf)).intersection(pair)]


def _validate_faces(ds, names):
    for face, mass, suffix in (("xi_u", "xi_rho", "u"), ("eta_v", "eta_rho", "v")):
        if not any(name in ds and face in ds[name].dims for name in names):
            continue
        if mass not in ds.coords or face not in ds.coords:
            raise ValueError(f"CROCO requires labelled {face}/{mass} axes")
        rho, native = ds[mass].values, ds[face].values
        if (rho.ndim != 1 or native.ndim != 1 or len(rho) < 3 or len(native) != len(rho)-1
                or not np.isfinite(rho).all() or not np.isfinite(native).all()
                or not np.allclose(np.diff(rho), np.diff(rho)[0], rtol=0, atol=1e-10)
                or np.diff(rho)[0] == 0
                or not (np.all(np.diff(native) > 0) or np.all(np.diff(native) < 0))
                or not np.allclose(np.sort(native), np.sort((rho[1:]+rho[:-1])/2), rtol=0, atol=1e-10)
                or ds[face].attrs.get("units") != ds[mass].attrs.get("units")):
            raise ValueError(f"CROCO {face}: requires regular N-1 midpoint face coordinates")
        dims = {"eta_rho", "xi_u"} if suffix == "u" else {"eta_v", "xi_rho"}
        for geo in (f"lat_{suffix}", f"lon_{suffix}"):
            if geo not in ds or set(ds[geo].dims) != dims or not ds[geo].attrs.get("units"):
                raise ValueError(f"CROCO requires explicit native face geography {geo}")


def _velocity(da):
    from frameit.utils.units import convert_units

    value = da.copy(deep=False)
    if da.attrs.get("units") in {"meter second-1", "metre second-1"}:
        value.attrs = dict(da.attrs, units="m s-1", source_units=da.attrs["units"])
    return convert_units(value, "velocity")


def _static_wet_mask(ds):
    options = str(ds.attrs.get("CPP-options", "")).split()
    if "MASKING" not in options or "WET_DRY" in options:
        raise ValueError("CROCO analysis requires explicit static MASKING without WET_DRY")
    if "mask_rho" not in ds or ds.mask_rho.dims != ("eta_rho", "xi_rho"):
        raise ValueError("CROCO analysis requires static mask_rho")
    mask = ds.mask_rho
    if (str(mask.attrs.get("option_0", "")).lower() != "land"
            or str(mask.attrs.get("option_1", "")).lower() != "water"
            or not np.isin(mask.values, [0, 1]).all()):
        raise ValueError("CROCO mask_rho requires explicit option_0=land, option_1=water and binary values")
    return mask == 1


def _validate_current_inputs(ds, pairs):
    if not pairs:
        return
    from frameit.utils.units import convert_units

    _static_wet_mask(ds)
    if "angle" not in ds or ds.angle.dims != ("eta_rho", "xi_rho"):
        raise ValueError("CROCO current analysis requires rho-point angle")
    try:
        convert_units(xr.DataArray(0., attrs=ds.angle.attrs), "angle")
        for pair in pairs:
            for name in pair:
                if name not in ds:
                    raise ValueError(f"missing current companion {name}")
                _velocity(xr.DataArray(0., attrs=ds[name].attrs))
    except ValueError as error:
        raise ValueError(f"CROCO current analysis: {error}") from error
    if not np.isfinite(ds.angle.values).all():
        raise ValueError("CROCO angle must be finite")
    for pair in pairs:
        statistics = ("cell_methods", "online_operation", "interval_operation", "interval_write")
        if any(ds[pair[0]].attrs.get(key) != ds[pair[1]].attrs.get(key) for key in statistics):
            raise ValueError("CROCO current companions have incompatible statistical definitions")
        for name, horizontal in zip(pair, ({"eta_rho", "xi_u"}, {"eta_v", "xi_rho"})):
            required = {"time", *horizontal} | ({"s_rho"} if name in {"u", "v"} else set())
            if set(ds[name].dims) != required:
                raise ValueError(f"CROCO {name}: incompatible native current dimensions")
            axis = "x" if name in {"u", "ubar"} else "y"
            prefix = "barotropic_" if "bar" in name else ""
            standard = f"{prefix}sea_water_{axis}_velocity"
            location = "u" if axis == "x" else "v"
            if ds[name].attrs.get("standard_name") not in {None, standard, f"{standard}_at_{location}_location"}:
                raise ValueError(f"CROCO {name}: quantity metadata contradicts native grid-relative current identity")
    for suffix, dims in (("u", {"eta_rho", "xi_u"}), ("v", {"eta_v", "xi_rho"})):
        name = f"mask_{suffix}"
        if name in ds and (set(ds[name].dims) != dims or not np.isin(ds[name].values, [0, 1]).all()):
            raise ValueError(f"CROCO {name}: requires binary native face support")


def prepare_croco_currents(ds, conf):
    """Both-valid midpoint collocation, then joint-mask rho/Earth rotation."""
    from frameit.processing.wind_collocation import interpolate_staggered
    from frameit.utils.units import convert_units

    pairs = current_pairs(conf)
    polar = polar_fields(conf)
    if not pairs and not polar:
        return ds
    if not polar and all(name in ds and ds[name].attrs.get("current_reference_frame") == "earth"
           for pair in pairs for name in pair):
        return ds
    _validate_faces(ds, [name for pair in pairs for name in pair])
    _validate_current_inputs(ds, pairs)
    result = ds.copy(deep=False)
    if result.mask_rho.attrs.get("standard_name") == "land_binary_mask":
        attrs = dict(result.mask_rho.attrs)
        attrs["source_standard_name"] = attrs.pop("standard_name")
        result["mask_rho"].attrs = attrs
    wet = _static_wet_mask(ds)
    angle = convert_units(ds.angle, "angle") if pairs else None
    for pair in pairs:
        components = []
        for name, face, mass in zip(pair, ("xi_u", "eta_v"), ("xi_rho", "eta_rho")):
            support = interpolate_staggered(wet.astype(float), mass, ds[face]) == 1
            mask_name = "mask_u" if face == "xi_u" else "mask_v"
            if mask_name in ds:
                support = support & (ds[mask_name] == 1)
            value = _velocity(ds[name]).where(support)
            components.append(interpolate_staggered(value, face, ds[mass]))
        u, v = components
        valid = wet & np.isfinite(u) & np.isfinite(v)
        for name, value, standard in zip(pair,
                (u*np.cos(angle)-v*np.sin(angle), u*np.sin(angle)+v*np.cos(angle)),
                ("eastward_sea_water_velocity", "northward_sea_water_velocity")):
            value = value.where(valid)
            if "bar" in name:
                standard = "barotropic_" + standard
            value.attrs = {key: val for key, val in ds[name].attrs.items()
                           if key not in {"standard_name", "coordinates", "grid", "long_name"}}
            value.attrs.update(units="m s-1", standard_name=standard,
                               long_name=standard.replace("_", " "), current_reference_frame="earth",
                               current_collocation="native_midpoint_both_valid_then_angle_rotation",
                               current_support="static mask_rho option_0=land option_1=water; joint finite vector",
                               source_units=ds[name].attrs["units"],
                               coordinates="lat_rho lon_rho", ancillary_variables="angle mask_rho")
            for key in ("long_name", "standard_name"):
                if key in ds[name].attrs:
                    value.attrs[f"source_{key}"] = ds[name].attrs[key]
            result[name] = value
    for name in polar - {name for pair in pairs for name in pair} - {"mask_rho"}:
        if name in result and {"eta_rho", "xi_rho"} <= set(result[name].dims):
            value = result[name].where(wet)
            value.attrs = dict(result[name].attrs, croco_support="static mask_rho option_0=land option_1=water")
            result[name] = value
    if pairs:
        result.attrs = dict(result.attrs, current_analysis_method="CROCO 2.1 midpoint collocation then rho angle rotation; no extrapolation or motion subtraction")
    return result


def validate_croco_coefficients(datasets, variables=None):
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
        for name in ("angle", "mask_rho", "mask_u", "mask_v"):
            if name not in ds or (variables is not None and name not in variables):
                continue
            values = ds[name].values
            if name in reference and not np.array_equal(values, reference[name]):
                raise ValueError(f"CROCO {name}: static current geometry/support changes across files")
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
    if (requested | polar_fields(conf)) & {"wind_speed", "vrad", "vtan"}:
        raise ValueError("CROCO ocean fields do not admit atmospheric wind diagnostics")
    pairs = current_pairs(conf)
    if getattr(conf, "cartesian_horizontal_winds", "native") != "native" and requested & {"sustr", "svstr"}:
        raise ValueError("CROCO stress analysis remains unqualified; request native representation")
    face_names = requested | {name for pair in pairs for name in pair}
    _validate_faces(ds, face_names)
    _validate_current_inputs(ds, pairs)
    polar = polar_fields(conf)
    if polar:
        if polar & {"mask_rho", "mask_u", "mask_v"}:
            raise ValueError("CROCO binary mask polar sampling is not qualified; use native masks")
        _static_wet_mask(ds)
        for name in polar:
            if name in result:
                ancillary = str(result[name].attrs.get("ancillary_variables", "")).split()
                result[name].attrs = dict(result[name].attrs,
                                          ancillary_variables=" ".join(dict.fromkeys([*ancillary, "mask_rho"])))
    for pair in pairs:
        for name in pair:
            ancillary = str(result[name].attrs.get("ancillary_variables", "")).split()
            ancillary.extend(key for key in ("angle", "mask_rho", "mask_u", "mask_v") if key in ds)
            result[name].attrs = dict(result[name].attrs, ancillary_variables=" ".join(dict.fromkeys(ancillary)))
    params = getattr(conf, "simulation_parameter", None)
    if pairs and params is not None:
        records = params.setdefault("current_provenance", [])
        for pair in pairs:
            record = {"source_id": Path(ds.encoding.get("source", "in_memory")).name,
                      "components": list(pair), "method": "both_valid_midpoint_then_rho_angle_rotation",
                      "producer_reference": "CROCO 2.1.0 cpl_prism_put.F/setup_grid1.F",
                      "support": "static MASKING; mask_rho option_0=land option_1=water; joint finite vector",
                      "source_mask_standard_name": ds.mask_rho.attrs.get("standard_name"),
                      "reference_frame": "earth", "units": "m s-1",
                      "source_units": {name: ds[name].attrs["units"] for name in pair},
                      "boundary_policy": "missing bracket remains missing; no extrapolation",
                      "vertical_policy": "same native sigma index; no physical-depth interpolation",
                      "track_motion_subtracted": False}
            if record not in records:
                records.append(record)
    if getattr(conf, "compute_polar_proj", False):
        if any(name in ds and set(ds[name].dims) & {"xi_u", "eta_v"}
               and name not in {"u", "v", "ubar", "vbar"} for name in polar):
            raise ValueError("CROCO polar native-face/stress interpretation is not qualified")
    geography = [name for name in ("lat_rho", "lon_rho", "lat_u", "lon_u", "lat_v", "lon_v", "scrum_time") if name in result]
    return result.set_coords(geography)
