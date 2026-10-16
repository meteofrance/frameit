"""Meso-NH pressure-centroid input contract, shared by inspection and execution.

MNH 6.0 DIAG recipes are documented at:
https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/
executables_namelists/namelists/nam_diag_general.html
"""

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import xarray as xr

from frameit.processing.requests import selected_native_indices
from frameit.processing.wind_collocation import prepare_native_mnh
from frameit.processing.wind_reference import pair_definition, rotation_angle, validate_pair_frame
from frameit.utils.units import convert_units, normalize_geography

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


def mnh_wind_frames(ds, fields, conf=None):
    """Validate declared native/surface bases, never infer them from field names.

    The lightweight ``conf=None`` numerical API takes canonical Earth-relative
    physical vectors for *both* pairs. Grid-relative fixtures must pass explicit
    pair declarations and rotation settings, just as production callers do.
    """
    if conf is None:
        conf = SimpleNamespace(wind_reference_frame="earth")
    result = {}
    for group, names in (("level", (fields.u, fields.v)), ("surface", ("UM10", "VM10"))):
        pair = pair_definition(conf, group, names)
        try:
            frame = validate_pair_frame(ds, pair)
        except ValueError as exc:
            raise ValueError(
                f"Wind components {names} have incompatible reference frames: {exc}"
            ) from exc
        if frame == "grid":
            rotation_angle(ds, conf, pair)
        result.update(dict.fromkeys(names, pair["reference_frame"]))
    return result


def prepare_mnh_inputs(ds, conf=None):
    """Return lazy, canonical mass-point fields; physical-height evaluation is explicit."""
    fields = resolve_mnh_fields(ds)
    settings = SimpleNamespace(
        atm_model="MNH", name_lon_dim="ni", name_lat_dim="nj", name_vertical_dim="level",
        name_latitude="latitude", name_longitude="longitude",
        velocity_aliases={"u_velocity": fields.u, "v_velocity": fields.v},
        tracking_var_aliases={"u10m": "UM10", "v10m": "VM10"},
        wind_pairs=[pair_definition(
            conf if conf is not None else SimpleNamespace(wind_reference_frame="earth"),
            group, names,
        ) for group, names in (("level", (fields.u, fields.v)),
                               ("surface", ("UM10", "VM10")))],
        wind_reference_frame=None,
    )
    source = normalize_geography(ds, settings)
    source = source.assign_coords({
        name: convert_units(source[name], "distance", assumed="m")
        for name in _horizontal_coordinates(source, fields)
    })
    try:
        frames = mnh_wind_frames(source, fields, settings)
        rotation = ",".join(dict.fromkeys(
            p["rotation"]["method"] for p in settings.wind_pairs
            if p["reference_frame"] == "grid")) or "none"
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
        if physical is not None:
            positions = selected_native_indices(
                source, {"level_domain": "physical", "all_levels": True}, "level")
            result = result.isel(level=positions)
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
