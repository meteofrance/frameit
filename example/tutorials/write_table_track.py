"""Write the three known positions and a copy with the middle time missing."""
import numpy as np
import xarray as xr

rows = [
    ("2000-01-01T00:00", -20., 60.),
    ("2000-01-01T01:00", -20., 60.1),
    ("2000-01-01T02:00", -20., 60.2),
]
times, latitudes, longitudes = zip(*rows, strict=True)
track = xr.Dataset(coords={
    "time": ("time", np.array(times, dtype="datetime64[ns]"), {"standard_name": "time"}),
    "latitude": ("time", list(latitudes), {"units": "degrees_north"}),
    "longitude": ("time", list(longitudes), {"units": "degrees_east"}),
})

for name, data in (
    ("table-track.nc", track),
    ("table-track-gap.nc", track.isel(time=[0, 2])),
):
    with open(name, "xb") as output:  # Refuse to replace an existing file.
        output.write(data.to_netcdf(engine="scipy"))
