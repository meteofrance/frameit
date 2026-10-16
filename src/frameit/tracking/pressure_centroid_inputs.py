"""Meso-NH pressure-centroid input contract, shared by inspection and execution.

MNH 6.0 DIAG recipes are documented at:
https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/
executables_namelists/namelists/nam_diag_general.html
"""

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import xarray as xr

from frameit.processing.wind_collocation import prepare_native_mnh
from frameit.utils.units import convert_units, normalize_geography

from .pressure_centroid import GEOD

HEIGHT_FORMULA = "z(n,k,j,i)=s(k)*(height-orog(j,i))/height+orog(j,i)"


def is_mnh_centroid(conf):
    return conf.atm_model == "MNH" and conf.tracking_method == "pressure_centroid"


def input_error(context, problems):
    """Keep actionable scientific failures consistent across CLI and Python APIs."""
    return ValueError(
        f"pressure_centroid: incomplete or incompatible Meso-NH inputs ({context}).\n"
        + "\n".join(f"  - {problem}" for problem in problems)
        + "\nMeso-NH 6.0 DIAG preparation (DIAG1.nam, &NAM_DIAG):\n"
        "  LTPZH=.TRUE. writes ALT and PRES; pressure may also be supplied as PABST.\n"
        "  LVAR_RS=.TRUE., LWIND_ZM=.TRUE. write UT_ZM and VT_ZM.\n"
        "  LMSLP=.TRUE. writes MSLP.\n"
        "  Include UM10 and VM10 from the surface diagnostics for your MNH/SURFEX setup.\n"
        "Regenerate missing diagnostics for all selected times, keeping native levels\n"
        "bracketing 2,000 m above mean sea level and the full 500-km reference ring.\n"
        "For other MNH versions check the corresponding DIAG documentation.\n"
        "Then run: frameit validate frameit.yaml"
    )


def _height_terms(ds):
    if "level" not in ds:
        return None
    coordinate = ds.level
    definition = "".join(str(coordinate.attrs.get("formula_definition", "")).split())
    if definition != HEIGHT_FORMULA or coordinate.attrs.get("computed_standard_name") != "altitude":
        return None
    tokens = str(coordinate.attrs.get("formula_terms", "")).split()
    if len(tokens) != 6:
        return None
    terms = dict(zip(tokens[::2], tokens[1::2], strict=True))
    if set(terms) != {"s:", "height:", "orog:"} or terms["s:"] != "level":
        return None
    return tuple(terms[k] for k in ("s:", "height:", "orog:"))


@dataclass(frozen=True)
class MNHFields:
    pressure: str
    u: str
    v: str
    height: tuple[str, ...]

    @property
    def variables(self):
        return tuple(dict.fromkeys((self.pressure, self.u, self.v, *self.height,
                                    "MSLP", "UM10", "VM10")))

    def requests(self):
        return {
            "surface": {"variables": ["MSLP", "UM10", "VM10"]},
            "level": {"variables": [self.pressure, self.u, self.v,
                                    *(["ALT"] if self.height == ("ALT",) else [])],
                      "level_selection": "all"},
        }


def _horizontal_coordinates(ds, fields):
    return sorted({"ni", "nj"} | {
        dim for name in (fields.u, fields.v) for dim in ds[name].dims
        if dim not in {"time", "level"}
    })


def resolve_mnh_fields(ds, context="Dataset"):
    """Resolve alternatives using headers only; never interpret level labels as altitude."""
    problems = []
    pressure = next((name for name in ("PABST", "PRES") if name in ds), None)
    if pressure is None:
        problems.append("Missing absolute pressure on model levels: PABST or PRES")
    pair = next((pair for pair in (("UT_ZM", "VT_ZM"), ("UT", "VT"))
                 if all(name in ds for name in pair)), None)
    if pair is None:
        problems.append("Missing complete horizontal wind pair: UT_ZM/VT_ZM or UT/VT")
    height = ("ALT",) if "ALT" in ds else _height_terms(ds)
    if height is None or any(name not in ds for name in height):
        problems.append("Missing physical model-level altitude: ALT or its explicit level formula")
    for name in ("MSLP", "UM10", "VM10", "time", "latitude", "longitude", "level", "ni", "nj"):
        if name not in ds:
            problems.append(f"Missing {name}")
    if problems:
        raise input_error(context, problems)
    fields = MNHFields(pressure, *pair, height)
    vertical = {"time", "level", "nj", "ni"}
    for name in (pressure, "MSLP", "UM10", "VM10", *height):
        expected = vertical if name == pressure else {"time", "nj", "ni"}
        if name == "ALT":
            allowed = (vertical, vertical - {"time"})
        elif name in height:
            allowed = ({"level"},) if name == "level" else (
                set(), {"time"}, {"nj", "ni"}, {"time", "nj", "ni"})
        else:
            allowed = (expected,)
        if set(ds[name].dims) not in allowed:
            problems.append(f"{name} has incompatible dimensions {ds[name].dims}")
    for name, suffix in zip(pair, ("_u", "_v"), strict=True):
        dims = set(ds[name].dims)
        spatial = {dim for dim in dims if dim not in {"time", "level"}}
        if not {"time", "level"} <= dims or len(spatial) != 2 or not all(
            len(spatial & {mass, mass + suffix}) == 1 for mass in ("ni", "nj")
        ):
            problems.append(f"{name} has unrecognized native wind dimensions {ds[name].dims}")
        for dimension in dims:
            if dimension not in ds.coords:
                problems.append(f"{name} requires labelled native coordinate {dimension}")
    if ds.level.size < 2:
        problems.append("At least two native vertical levels are required")
    if ds.time.dims != ("time",) or not ds.time.size:
        problems.append("A nonempty labelled time(time) coordinate is required")
    if height == ("ALT",) and (
        ds.ALT.attrs.get("positive", "up") != "up"
        or ds.ALT.attrs.get("standard_name") in {"height", "height_above_ground"}
        or ds.ALT.attrs.get("height_reference") in {"above_ground", "AGL"}
    ):
        problems.append("ALT must be positive-up altitude above mean sea level, not height AGL")
    if problems:
        raise input_error(context, problems)
    try:
        for name in (pressure, "MSLP"):
            convert_units(ds[name], "pressure")
        for name in (*pair, "UM10", "VM10"):
            convert_units(ds[name], "velocity", assumed="m s-1")
        for name in height:
            convert_units(ds[name], "distance")
        for name in _horizontal_coordinates(ds, fields):
            convert_units(ds[name], "distance", assumed="m")
    except ValueError as exc:
        raise input_error(context, [str(exc)]) from exc
    return fields


def inspect_mnh_sequence(records):
    """Require a consistent complete layout and units in every selected file.

    A per-file check prevents xarray's outer concatenation from disguising a
    missing field at a later timestamp as an ordinary partially missing array.
    """
    reference = None
    problems = []
    for path, ds in records:
        times = (", ".join(str(t) for t in np.atleast_1d(ds.time.values))
                 if "time" in ds else "unknown")
        context = f"{path}; time={times}"
        try:
            fields = resolve_mnh_fields(ds, context)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        names = tuple(dict.fromkeys((*fields.variables, "latitude", "longitude",
                                    *_horizontal_coordinates(ds, fields),
                                    *(["grid_rotation"] if "grid_rotation" in ds else []))))
        signature = (fields, tuple((name, ds[name].dims, ds[name].attrs.get("units"),
                                   ds[name].attrs.get("wind_reference_frame"),
                                   ds[name].attrs.get("GRIB_uvRelativeToGrid"),
                                   ds[name].attrs.get("standard_name")) for name in names),
                     ds.attrs.get("wind_reference_frame"))
        coordinates = {dim: np.asarray(ds[dim]) for name in fields.variables
                       for dim in ds[name].dims if dim != "time"}
        if reference is None:
            reference = fields, signature, coordinates
        elif signature != reference[1] or coordinates.keys() != reference[2].keys() or any(
            not np.array_equal(coordinates[name], reference[2][name]) for name in coordinates
        ):
            problems.append(str(input_error(context, [
                "Selected files have inconsistent fields, units or native coordinates; "
                "regenerate a consistent "
                "diagnostic sequence before concatenation"])))
    if problems:
        raise ValueError("\n\n".join(problems))
    return reference[0]


def _wind_frame(da, ds, default):
    flag = da.attrs.get("GRIB_uvRelativeToGrid")
    intrinsic = da.name in {"UT_ZM", "VT_ZM", "UM10", "VM10"}
    frame = da.attrs.get("wind_reference_frame")
    if frame is None and not intrinsic:
        frame = ds.attrs.get("wind_reference_frame")
    if flag is not None:
        if flag not in (0, 1) or (frame is not None and frame != ("grid" if flag else "earth")):
            raise ValueError(f"Conflicting/invalid wind reference metadata on {da.name}")
        frame = "grid" if flag else "earth"
    if frame is None and da.attrs.get("standard_name") in {"eastward_wind", "northward_wind"}:
        frame = "earth"
    frame = frame or default
    if frame not in {"grid", "earth"}:
        raise ValueError(f"Unknown wind reference frame {frame!r} on {da.name}")
    return frame


def mnh_wind_frames(ds, fields, conf=None):
    """Resolve the native and surface vector bases independently."""
    default_native = "earth" if fields.u.endswith("_ZM") else "grid"
    if not fields.u.endswith("_ZM") and conf is not None and getattr(
        conf, "schema_sources", {}).get("input.wind_reference_frame") == "yaml":
        default_native = conf.wind_reference_frame
    result = {}
    for pair, default in (((fields.u, fields.v), default_native), (("UM10", "VM10"), "earth")):
        frames = {_wind_frame(ds[name], ds, default) for name in pair}
        if len(frames) != 1:
            raise input_error("Dataset", [
                f"Wind components {pair} have incompatible reference frames"])
        frame = frames.pop()
        if pair[0].endswith("_ZM") and frame != "earth":
            raise input_error("Dataset", ["UT_ZM/VT_ZM contradict their earth-relative definition"])
        result.update(dict.fromkeys(pair, frame))
    return result


def _grid_rotation(ds):
    """Local geographic direction of increasing native x, at native mass points."""
    lon, lat = xr.broadcast(ds.longitude, ds.latitude)
    if "time" in lon.dims:
        lon, lat = lon.isel(time=0), lat.isel(time=0)
    lon, lat = (np.asarray(a.transpose("nj", "ni"), float) for a in (lon, lat))
    if min(lon.shape) < 2:
        raise ValueError("Wind rotation requires at least two horizontal mass points per axis")
    angles = []
    for axis in (1, 0):
        forward = np.minimum(np.arange(lon.shape[axis]) + 1, lon.shape[axis] - 1)
        backward = np.maximum(np.arange(lon.shape[axis]) - 1, 0)
        azf = GEOD.inv(lon, lat, np.take(lon, forward, axis=axis),
                      np.take(lat, forward, axis=axis))[0]
        azb = GEOD.inv(lon, lat, np.take(lon, backward, axis=axis),
                      np.take(lat, backward, axis=axis))[0] + 180
        indices = np.arange(lon.shape[axis])
        shape = [1, 1]
        shape[axis] = len(indices)
        azf = np.where((indices == len(indices) - 1).reshape(shape), azb, azf)
        azb = np.where((indices == 0).reshape(shape), azf, azb)
        # Negative native coordinates reverse both vector axes.
        coordinate = np.asarray(ds["ni" if axis == 1 else "nj"], float)
        if np.all(np.diff(coordinate) < 0):
            azf, azb = azf + 180, azb + 180
        elif not np.all(np.diff(coordinate) > 0):
            raise ValueError("Native coordinates must be strictly monotone for wind rotation")
        a, b = np.deg2rad(azf), np.deg2rad(azb)
        angles.append(np.arctan2(np.sin(a) + np.sin(b), np.cos(a) + np.cos(b)))
    if not np.isfinite(angles).all() or np.max(np.abs(np.cos(angles[0] - angles[1]))) > .02:
        raise ValueError("Native wind rotation requires an approximately orthogonal grid")
    # Grid y must be to the left of grid x, not a reflected vector basis.
    if np.any(np.sin(angles[0] - angles[1]) <= 0):
        raise ValueError("Native wind grid has an inconsistent vector orientation")
    return xr.DataArray(np.pi / 2 - angles[0], dims=("nj", "ni"),
                        coords={d: ds[d] for d in ("nj", "ni")}, attrs={"units": "rad"})


def prepare_mnh_inputs(ds, conf=None):
    """Return lazy, canonical mass-point fields; physical-height evaluation is explicit."""
    fields = resolve_mnh_fields(ds)
    settings = SimpleNamespace(
        atm_model="MNH", name_lon_dim="ni", name_lat_dim="nj", name_vertical_dim="level",
        name_latitude="latitude", name_longitude="longitude",
        velocity_aliases={"u_velocity": fields.u, "v_velocity": fields.v},
        tracking_var_aliases={"u10m": "UM10", "v10m": "VM10"}, wind_reference_frame="earth",
    )
    source = normalize_geography(ds, settings)
    source = source.assign_coords({
        name: convert_units(source[name], "distance", assumed="m")
        for name in _horizontal_coordinates(source, fields)
    })
    try:
        frames = mnh_wind_frames(source, fields, conf)
        for name, frame in frames.items():
            source[name] = source[name].assign_attrs(wind_reference_frame=frame)
        rotation = "none"
        if "grid" in frames.values():
            rotation = ("source_grid_rotation" if "grid_rotation" in source
                        else "WGS84_native_axis_direction")
            if "grid_rotation" not in source:
                source = source.assign_coords(grid_rotation=_grid_rotation(source))
        source, _ = prepare_native_mnh(source, settings)
        if fields.height == ("ALT",):
            height = convert_units(source.ALT, "distance")
        else:
            s, top, terrain = (convert_units(source[n], "distance") for n in fields.height)
            if bool((top <= 0).any()) or bool((terrain >= top).any()):
                raise ValueError("Invalid top/orography in the explicit MNH height formula")
            height = s * (top - terrain) / top + terrain
        height = height.assign_attrs(units="m", standard_name="altitude", positive="up")
        result = xr.Dataset({
            "u": source[fields.u], "v": source[fields.v],
            "pressure": convert_units(source[fields.pressure], "pressure"), "height": height,
            "mslp": convert_units(source.MSLP, "pressure"),
            "u10m": source.UM10, "v10m": source.VM10,
        })
        result = result.assign_coords(latitude=source.latitude, longitude=source.longitude)
        # Native backup files can contain nonphysical bottom/top levels. Respect
        # MNH's one-based inclusive dynamic range when it is explicitly supplied.
        physical = source.level.attrs.get("c_grid_dynamic_range")
        if physical:
            first, last = (int(v) for v in physical.split(":"))
            if not 1 <= first <= last <= source.level.size:
                raise ValueError("level.c_grid_dynamic_range is incompatible with the input levels")
            result = result.isel(level=slice(first - 1, last))
        if result.sizes["level"] < 2:
            raise ValueError("At least two physical native levels are required")
    except ValueError as exc:
        raise input_error("Dataset", [str(exc)]) from exc
    result.attrs.update(
        pressure_centroid_pressure_source=fields.pressure,
        pressure_centroid_pressure_source_units=ds[fields.pressure].attrs["units"],
        pressure_centroid_height_source=",".join(fields.height),
        pressure_centroid_height_formula=(
            "source_ALT" if fields.height == ("ALT",) else HEIGHT_FORMULA),
        pressure_centroid_wind_sources=f"{fields.u},{fields.v}",
        pressure_centroid_wind_collocation="native_coordinate_linear_strict",
        pressure_centroid_horizontal_coordinate_units="m",
        pressure_centroid_horizontal_unit_assumptions=",".join(
            name for name in _horizontal_coordinates(ds, fields)
            if not ds[name].attrs.get("units")),
        pressure_centroid_wind_rotation=rotation,
        pressure_centroid_native_wind_reference=frames[fields.u],
        pressure_centroid_surface_wind_reference=frames["UM10"],
        pressure_centroid_height_reference="altitude_above_mean_sea_level",
    )
    return result
