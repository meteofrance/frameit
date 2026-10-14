"""Small prescribed-track coordinates, shared by preflight and tracking."""

import numpy as np
import xarray as xr

from frameit.utils.units import convert_units


def load_track_coordinates(path, *, time_name="time", latitude_name="latitude",
                           longitude_name="longitude"):
    with xr.open_dataset(path) as source:
        if time_name not in source.coords or source[time_name].dims != (time_name,):
            raise ValueError(f"PrescribedTrack: {time_name!r} must be a time coordinate")
        times = source[time_name].values.copy()
        if np.unique(times).size != times.size:
            raise ValueError("PrescribedTrack: duplicate track times are ambiguous")
        variables = {}
        for requested, canonical, short, units in (
            (latitude_name, "latitude", "lat", "degrees_north"),
            (longitude_name, "longitude", "lon", "degrees_east"),
        ):
            name = requested
            if name not in source and name == canonical and short in source:
                name = short
            if name not in source or source[name].dims != (time_name,):
                raise ValueError(
                    f"PrescribedTrack: {requested!r} must be one-dimensional along time"
                )
            coordinate = convert_units(source[name], "angle", target=units, assumed=units)
            if "unit_assumption" in coordinate.attrs:
                coordinate.attrs.setdefault(
                    "unit_assumption_source", "prescribed_track_degree_contract"
                )
            variables[canonical] = ("time", coordinate.values.copy(), coordinate.attrs)
    return xr.Dataset(variables, coords={"time": times})
