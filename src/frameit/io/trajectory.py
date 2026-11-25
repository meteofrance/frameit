"""Small, lossless internal record of the centres actually used by a run."""

from frameit.core.run_context import file_sha256
from frameit.utils.atomic import atomic_output
from frameit.utils.diagnostics import tag_error
from frameit.utils.output_paths import TRAJECTORY_RECORD, OutputPaths


def track_coordinates(track):
    ds = track.rename(lat="latitude", lon="longitude").copy(deep=False)
    for name, units in (("latitude", "degrees_north"), ("longitude", "degrees_east")):
        ds[name].attrs = dict(ds[name].attrs, standard_name=name, units=units)
    return ds


def write_trajectory_record(root, track, *, attempt_id, origin, tracking_facts, overwrite):
    path = OutputPaths(root).trajectory_record()
    ds = track_coordinates(track)[["latitude", "longitude"]]
    for name in ("latitude", "longitude"):
        ds[name] = ds[name].astype("float64")
        ds[name].encoding = {}
    ds.attrs = {
        "record_type": "frameit_trajectory",
        "record_version": 1,
        "run_attempt_id": attempt_id,
        "centre_origin": origin,
        **tracking_facts,
    }
    calendar = track.time.encoding.get("calendar", "proleptic_gregorian")
    ds.time.encoding = {"calendar": calendar, "dtype": "int64"}
    try:
        with atomic_output(path, overwrite=overwrite) as temporary:
            ds.to_netcdf(temporary, engine="netcdf4")
            checksum = file_sha256(temporary)
    except Exception as exc:
        tag_error(exc, "E1808")
        raise
    return {
        "role": "trajectory",
        "path": TRAJECTORY_RECORD,
        "run_attempt_id": attempt_id,
        "calendar": calendar,
        "centre_origin": origin,
        "sha256": checksum,
    }
