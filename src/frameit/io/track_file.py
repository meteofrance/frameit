"""Small prescribed-track coordinates, shared by preflight and tracking."""

import numpy as np
import xarray as xr

from frameit.utils.units import convert_units, unit_key


def load_track_coordinates(path, *, time_name="time", latitude_name="latitude",
                           longitude_name="longitude"):
    """Discover one labelled trajectory; names never override contradictory evidence."""
    with xr.open_dataset(path, engine="netcdf4") as source:
        candidates = {key: [] for key in ("time", "latitude", "longitude")}
        names = {"time": {time_name, "time"}, "latitude": {latitude_name, "latitude", "lat"},
                 "longitude": {longitude_name, "longitude", "lon"}}
        for name, value in source.variables.items():
            evidence = {kind for kind, aliases in names.items() if name in aliases}
            standard = value.attrs.get("standard_name")
            if standard in candidates:
                evidence.add(standard)
            if value.attrs.get("axis") == "T":
                evidence.add("time")
            if len(evidence) > 1 or evidence and standard and standard not in evidence:
                raise ValueError(f"PrescribedTrack: conflicting coordinate evidence for {name!r}")
            for kind in evidence:
                candidates[kind].append(name)
        for kind, found in candidates.items():
            if len(found) != 1:
                raise ValueError(
                    f"PrescribedTrack: missing or ambiguous {kind} coordinate: {found}")
        chosen = {kind: source[found[0]] for kind, found in candidates.items()}
        clock = chosen["time"]
        if clock.ndim != 1 or not clock.size:
            raise ValueError("PrescribedTrack: time must have one nonempty trajectory dimension")
        units = clock.encoding.get("units", clock.attrs.get("units", ""))
        if " since " not in units or not (
                np.issubdtype(clock.dtype, np.datetime64) or clock.dtype.kind == "O"):
            raise ValueError("PrescribedTrack: time requires CF-decodable units and calendar")
        times = clock.values.copy()
        if any(value is None or str(value) == "NaT" for value in times):
            raise ValueError("PrescribedTrack: missing track times")
        if len(set(times)) != times.size:
            raise ValueError("PrescribedTrack: duplicate track times are ambiguous")
        variables = {}
        for kind, units in (("latitude", "degrees_north"), ("longitude", "degrees_east")):
            value = chosen[kind]
            if value.dims != clock.dims:
                raise ValueError(
                    f"PrescribedTrack: {kind} must share the time trajectory dimension")
            observed = unit_key(value.attrs.get("units"))
            direction = "north" if kind == "latitude" else "east"
            admitted = {"rad", "radian", "radians", "degree", "degrees",
                        f"degree_{direction}", f"degrees_{direction}"}
            if observed not in admitted:
                raise ValueError(
                    f"PrescribedTrack: {kind} requires explicit consistent {units} units")
            coordinate = convert_units(value, "angle", target=units)
            if not np.isfinite(coordinate.values).all():
                raise ValueError("PrescribedTrack: positions must be finite")
            variables[kind] = ("time", coordinate.values.copy(),
                               dict(coordinate.attrs, standard_name=kind))
        result = xr.Dataset(variables, coords={"time": ("time", times, dict(clock.attrs))})
        result.time.encoding = {key: clock.encoding[key] for key in ("units", "calendar")
                                if key in clock.encoding}
    return result.sortby("time")
