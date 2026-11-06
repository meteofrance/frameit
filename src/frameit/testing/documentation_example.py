"""Deterministic instructional NetCDF, not producer data or a physical simulation."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr

from frameit.utils.atomic import atomic_output


def create_first_run_input(path: Path) -> Path:
    """Create the two-time scalar example without replacing an existing input."""
    path = Path(path)
    t, j, i = np.indices((2, 17, 17))
    values = (1000*t + 10*(j-8) + (i-8)).astype(float)
    values[:, 7, 9] = np.nan
    data = xr.Dataset({
        "instructional_scalar": (("valid_time", "latitude", "longitude"), values, {
            "units": "1", "long_name": "dimensionless instructional scalar",
            "comment": "1000*t + 10*(j-8) + (i-8); zero-based indices; missing at j=7,i=9",
        }),
    }, coords={
        "valid_time": ("valid_time", np.array(
            ["2000-01-01T00:00", "2000-01-01T01:00"], dtype="datetime64[ns]"),
            {"standard_name": "time", "axis": "T"}),
        "latitude": ("latitude", -20. + .01 * np.arange(-8, 9),
                     {"units": "degrees_north", "standard_name": "latitude"}),
        "longitude": ("longitude", 60. + .01 * np.arange(-8, 9),
                      {"units": "degrees_east", "standard_name": "longitude"}),
    }, attrs={
        "title": "FrameIt instructional scalar example",
        "source": "Synthetic structured-adapter input; not an AROME producer file",
        "comment": "No physical interpretation or real-producer qualification; zero is valid, NaN is missing.",
    })
    with atomic_output(path, overwrite=False) as temporary:
        data.to_netcdf(temporary, engine="netcdf4", encoding={
            "valid_time": {"units": "hours since 2000-01-01 00:00:00", "calendar": "proleptic_gregorian"}})
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New instructional NetCDF path (no overwrite)")
    args = parser.parse_args()
    print(f"Created instructional input: {create_first_run_input(args.output)}")


if __name__ == "__main__":
    main()
