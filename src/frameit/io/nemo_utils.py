"""Native regional NEMO NetCDF coordinates; no inferred ocean physics."""

import numpy as np
import xarray as xr


def prepare_nemo(ds: xr.Dataset, conf) -> xr.Dataset:
    """Validate stored sampling and retain source-local axes/support unchanged."""
    requested = {name for spec in getattr(conf, "requested_variables_user", {}).values()
                 for name in spec.get("variables", [])}
    native_components = {"vozocrtx", "vomecrty", "vovecrtz", "sozobrtx", "somebrty",
                         "sozotaux", "sometauy"}
    native_components.update(name for name in ds.data_vars if ds[name].attrs.get("standard_name") in {
        "sea_water_x_velocity", "sea_water_y_velocity", "eastward_sea_water_velocity",
        "northward_sea_water_velocity", "upward_sea_water_velocity", "surface_downward_x_stress",
        "surface_downward_y_stress"})
    if requested & {"wind_speed", "vrad", "vtan"}:
        raise ValueError("NEMO wind diagnostics are unsupported; request native ocean quantities")
    if requested & native_components:
        if getattr(conf, "cartesian_horizontal_winds", "mass_earth") != "native":
            raise ValueError("NEMO components require output.cartesian.horizontal_winds: native; "
                             "analysed vectors lack a qualified angle/mesh/support contract")
        polar = getattr(conf, "polar_variables", {})
        polar_names = {name for spec in polar.values() for name in spec.get("variables", [])} if isinstance(
            polar, dict) else requested
        if getattr(conf, "compute_polar_proj", False) and polar_names & native_components:
            raise ValueError("NEMO polar component analysis is unqualified; native extraction remains available")
    vertical = {name for name in ds.data_vars
                if ds[name].attrs.get("standard_name") == "upward_sea_water_velocity"}
    if (requested & (vertical | {"vovecrtz"})
            and getattr(conf, "cartesian_vertical_velocity", "interfaces") != "interfaces"):
        raise ValueError("NEMO W retains native depthw samples; mass-level analysis is unqualified")
    if "time_counter" not in ds:
        raise ValueError("NEMO requires the native time_counter sample clock")
    clock = ds.time_counter
    if clock.dims != ("time_counter",) or not np.issubdtype(clock.dtype, np.datetime64):
        raise ValueError("NEMO requires a decoded Gregorian time_counter clock")
    for name in ("time_counter", "time_centered"):
        if name not in ds:
            continue
        calendar = ds[name].encoding.get("calendar", ds[name].attrs.get("calendar", "standard"))
        if calendar not in {"standard", "gregorian", "proleptic_gregorian"}:
            raise ValueError(f"NEMO unsupported calendar {calendar!r}")
        if not ds[name].variable.equals(clock.variable):
            raise ValueError("NEMO time_counter/time_centered sample clocks disagree")
    bound_names = []
    for name in ("time_counter", "time_centered"):
        if name in ds and ds[name].attrs.get("bounds"):
            bounds = ds[name].attrs["bounds"]
            if bounds not in ds or ds[bounds].shape != (clock.size, 2):
                raise ValueError(f"NEMO missing or invalid time bounds: {bounds}")
            bound_names.append(bounds)
    if len(bound_names) == 2 and not ds[bound_names[0]].variable.equals(ds[bound_names[1]].variable):
        raise ValueError("NEMO time_counter/time_centered bounds disagree")
    for name in ("nav_lat", "nav_lon"):
        if name not in ds or ds[name].dims != ("y", "x"):
            raise ValueError(f"NEMO requires source-local (y, x) geography {name}")
        if not ds[name].attrs.get("units"):
            raise ValueError(f"NEMO geography {name} requires explicit angular units")
    result = ds.set_coords(["nav_lat", "nav_lon", *bound_names,
                           *(["time_centered"] if "time_centered" in ds else [])])
    for dim in ("x", "y"):
        if dim not in result.coords:
            result = result.assign_coords({dim: (dim, np.arange(result.sizes[dim]), {
                "units": "1", "long_name": f"zero-based native source {dim} index"})})
    for dim in ("deptht", "depthu", "depthv", "depthw"):
        if dim not in result.dims:
            continue
        if dim not in result.coords or result[dim].dims != (dim,):
            raise ValueError(f"NEMO {dim} requires its native coordinate")
        bounds = result[dim].attrs.get("bounds")
        if bounds and bounds not in result:
            raise ValueError(f"NEMO missing {dim} bounds {bounds}")
        index = f"{dim}_source_native_index"
        if index not in result:
            result = result.assign_coords({index: (dim, np.arange(result.sizes[dim]), {
                "units": "1", "long_name": f"zero-based native source {dim} index"})})
    return result
