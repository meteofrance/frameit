"""Plot the actual instructional input and exported crop; imports no FrameIt.

Usage: python first_run.py INPUT.nc PRODUCT.nc NEW_FIGURE.png
"""
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

source, product, output = map(Path, sys.argv[1:])
if output.exists():
    raise FileExistsError(output)
with xr.open_dataset(source, engine="netcdf4") as a, xr.open_dataset(product, engine="netcdf4") as b:
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.1), layout="constrained")
    cmap = plt.colormaps["RdBu_r"].with_extremes(bad="#666666")
    for ax, ds, clock, title in zip(axes, (a, b), ("valid_time", "time"), ("Input", "Exported crop")):
        ds = ds.isel({clock: 0})
        q = ds.instructional_scalar
        if q.attrs.get("units") != "1":
            raise ValueError("This example expects the dimensionless instructional scalar")
        image = ax.pcolormesh(ds.longitude, ds.latitude, q, shading="nearest", cmap=cmap, vmin=-88, vmax=88)
        ax.set(title=title, xlabel="Longitude (degrees east)", ylabel="Latitude (degrees north)")
        ax.set_aspect(1 / np.cos(np.deg2rad(-20)))
        ax.grid(False)
    fig.colorbar(image, ax=axes, label="Instructional scalar (1)", shrink=.85)
    fig.supxlabel("Instructional data, not a simulation · grey marks the missing sample", fontsize=9)
    fig.savefig(output, dpi=180)
