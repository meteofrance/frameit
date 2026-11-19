"""Read the forecast clocks from the three tutorial files."""
from pathlib import Path

import numpy as np
import xarray as xr

files = sorted(Path("forecast-archive").glob("*.nc"))
if not files:
    raise FileNotFoundError("No NetCDF files in forecast-archive/")
print("File | Cycle | Lead (h) | Valid time")
for path in files:
    with xr.open_dataset(path) as data:
        cycle = np.datetime_as_string(data.time.values, unit="m")
        lead = data.step.values[0] / np.timedelta64(1, "h")
        valid = np.datetime_as_string(data.valid_time.values[0], unit="m")
        print(f"{path.name} | {cycle} | {lead:g} | {valid}")
