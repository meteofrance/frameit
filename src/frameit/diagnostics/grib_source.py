"""One admitted regular-latitude/longitude GRIB message per field and time."""

from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np

from frameit.diagnostics.sources import (
    FieldSample,
    Grid,
    _error,
    _semantics,
    _timestamp,
    _units_factor,
)
from frameit.io.grib_utils import _grib_header, _grib_message, _grib_payload
from frameit.processing.requests import resolve_field_metadata

# Exact registered parameters and surfaces, not aliases derived from file names.
PARAMETERS = {
    "u": (165, "heightAboveGround", "eastward_wind", 10),
    "v": (166, "heightAboveGround", "northward_wind", 10),
    "speed": (207, "heightAboveGround", "wind_speed", 10),
    "pressure": (151, "meanSea", "air_pressure_at_mean_sea_level", None),
}


def _shape(handle, ec, message):
    shape = tuple(ec.codes_get_long(handle, key) for key in ("Nj", "Ni"))
    if (
        list(shape) != message["shape"]
        or min(shape) < 2
        or (shape[0] * shape[1] != ec.codes_get_long(handle, "numberOfPoints"))
    ):
        raise _error("GRIB message failed the recorded structured-grid shape check")
    return shape


def bind_messages(file, file_index, inventory, config, selectors, *, budget):
    try:
        import eccodes as ec
    except ImportError as exc:
        from frameit.utils.diagnostics import tag_error

        raise tag_error(exc, "E1002") from exc

    messages = inventory.get("messages")
    if not messages:
        raise _error("The parent did not freeze exact GRIB message locators")
    by_name = {
        role: [
            m for m in messages if m["file_index"] == file_index and m["name"] == selector["field"]
        ]
        for role, selector in selectors.items()
    }
    for role, sequence in by_name.items():
        selector = selectors[role]
        for message in sequence:
            attrs = message["attributes"]
            group = attrs.get("GRIB_typeOfLevel")
            if selector.get("group") not in {None, group}:
                continue
            if level := selector.get("level"):
                if group != "heightAboveGround":
                    raise _error(
                        "GRIB diagnostic levels require admitted heightAboveGround support"
                    )
                if level["value"] * _units_factor(level["units"], "distance") != message["level"]:
                    continue
            shape = message["shape"]
            decode_bytes = 48 * shape[0] * shape[1] + 3 * message["locator"]["length"]
            if decode_bytes > budget:
                raise _error(
                    "A complete GRIB message decode exceeds the working-buffer budget",
                    observed={"minimum_decode_bytes": decode_bytes, "budget_bytes": budget},
                )
            locator = {"path": str(file.path), **message["locator"]}
            with _grib_message(locator) as handle:
                header = _grib_header(handle)
                if (
                    _timestamp(header["cycle"]) != _timestamp(message["cycle"])
                    or header["md5GridSection"] != message["grid_section"]
                    or header["level"] != message["level"]
                    or header["paramId"] != attrs.get("GRIB_paramId")
                    or header["typeOfLevel"] != group
                    or header["number"] != (message["axes"] or {}).get("number")
                ):
                    raise _error("GRIB message contradicts its frozen physical/sample identity")
                shape = _shape(handle, ec, message)
                if ec.codes_get_string(handle, "gridType") != "regular_ll" or (
                    ec.codes_get_long(handle, "alternativeRowScanning")
                ):
                    raise _error("The diagnostic admits only nonalternating regular_ll GRIB grids")
                radius = ec.codes_get_double(handle, "radius")
                if not 6e6 < radius < 7e6 or ec.codes_get_long(handle, "earthIsOblate"):
                    raise _error("This GRIB diagnostic path requires a declared spherical Earth")
            parameter = PARAMETERS.get(role)
            if parameter is None or parameter[:2] != (header["paramId"], group):
                raise _error(f"GRIB parameter {header['paramId']}/{group} not admitted for {role}")
            _, _, standard, height = parameter
            if height is not None and message["level"] != height:
                raise _error("GRIB wind surface does not establish 10 m height")
            attrs = {**attrs, "standard_name": standard}
            # regular_ll geographic-axis components are collocated and orthonormal.
            if role in {"u", "v", "speed"}:
                if header["uvRelativeToGrid"] not in {0, 1}:
                    raise _error("GRIB wind reference frame is not established")
                attrs = {**attrs, "wind_reference_frame": "earth"}
            inherited = next(
                (
                    entry["metadata"]
                    for entry in inventory["fields"]
                    if entry["file_index"] == file_index
                    and entry["native_id"] == message["native_id"]
                ),
                None,
            )
            declarations = config.get("field_metadata", {})
            declaration = declarations.get(
                f"{group}.{message['name']}", declarations.get(message["name"], {})
            )
            if inherited is not None:
                declaration = {
                    k: v
                    for k, v in inherited["attributes"].items()
                    if k in {"units", "long_name", "standard_name", "temporal_kind"}
                }
            metadata = resolve_field_metadata(attrs, declaration, message["name"])
            attrs = metadata["attributes"]
            if (
                header["stepType"] == "avg"
                and role == "speed"
                and (header["typeOfStatisticalProcessing"] == 0)
            ):
                attrs["cell_methods"] = "time: mean"
            time = _timestamp(message["time"])
            bounds = (
                tuple(map(_timestamp, message["time_bounds"])) if message["time_bounds"] else None
            )
            sample = {"time": time, "time_bounds": bounds, "temporal_names": ("time",)}
            statistic, duration, qualified, frame = _semantics(
                role, SimpleNamespace(name=message["name"]), attrs, height, sample, ()
            )
            quantity = role if role in {"pressure", "area"} else "velocity"
            units = attrs["units"]
            grid = Grid(
                ("y", "x"),
                shape,
                message["grid_section"],
                "regular_ll",
                (),
                1.0,
                1.0,
                (radius, radius),
                "GRIB Earth shape/radius",
            )
            header["cycle"] = _timestamp(header["cycle"])
            evidence = {
                "origin": "frozen_GRIB_message",
                "paramId": header["paramId"],
                "native_surface": group,
                "relative_to_grid": header["uvRelativeToGrid"],
                "member": message["axes"],
                "metadata_origins": metadata["origins"],
            }
            yield FieldSample(
                role,
                message["name"],
                file,
                grid,
                (),
                time,
                _timestamp(message["cycle"]),
                "proleptic_gregorian",
                "proleptic_gregorian",
                bounds,
                None,
                height,
                statistic,
                duration,
                qualified,
                frame,
                units,
                _units_factor(units, quantity),
                decode_bytes,
                "float64",
                evidence,
                tuple(sorted((message["axes"] or {}).items())),
                {"locator": locator, "header": header},
            )


@contextmanager
def open_grib_group(group):
    import eccodes as ec

    first = group.fields[0]
    shape = group.grid.shape
    with _grib_message(first.native["locator"]) as handle:
        fast = ec.codes_get_long(handle, "jPointsAreConsecutive")

        def coordinates(name):
            flat = ec.codes_get_array(handle, name)
            return flat.reshape(shape[::-1]).T if fast else flat.reshape(shape)

        latitude, longitude = coordinates("latitudes"), coordinates("longitudes")
    values = {}
    for field in group.fields:
        header = {**field.native["header"], "cycle": np.datetime64(field.cycle, "ns")}
        values[field.role] = _grib_payload(field.native["locator"], shape, header) * field.factor

    class View:
        def geography(self, window):
            return latitude[window], longitude[window]

        def read_values(self, window):
            return {role: data[window] for role, data in values.items()}

    yield View()
