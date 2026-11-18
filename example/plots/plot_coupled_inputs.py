"""Plot three prescribed atmospheric/ocean snapshots in the same fixed box."""
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.ticker import FormatStrFormatter

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("atmosphere", type=Path)
parser.add_argument("ocean", type=Path)
parser.add_argument("figure", type=Path)
args = parser.parse_args()
if not args.figure.suffix:
    parser.error("figure needs an explicit extension, for example .svg")
if args.figure.exists():
    raise FileExistsError(args.figure)
with xr.open_dataset(args.atmosphere) as air, xr.open_dataset(args.ocean) as ocean:
    if air.sizes["time"] != 3 or not np.array_equal(air.time, ocean.time):
        raise ValueError("This illustration needs the same three times in both products")
    if any(field.attrs.get("units") != units for field, units in (
        (air["height.temperature"], "K"), (air.height, "m"), (air.u, "m s-1"),
        (air.v, "m s-1"), (ocean.temp, "K"),
    )):
        raise ValueError("Expected air/SST in K, height in m and winds in m s-1")
    fig, axes = plt.subplots(2, 3, figsize=(9.6, 5.6), sharex=True, sharey=True,
                             layout="constrained")
    for column in range(3):
        a, s = air.isel(time=column), ocean.isel(time=column)
        temperature = axes[0, column].pcolormesh(
            a.longitude, a.latitude, a["height.temperature"].sel(height=10),
            shading="nearest", cmap="inferno", vmin=299.9, vmax=302)
        wind = a.isel(x=slice(None, None, 3), y=slice(None, None, 3))
        arrows = axes[0, column].quiver(
            wind.longitude, wind.latitude, wind.u, wind.v, scale=240)
        sst = axes[1, column].pcolormesh(
            s.longitude_rho, s.latitude_rho, s.temp.squeeze(drop=True),
            shading="nearest", cmap="viridis", vmin=298, vmax=300)
        axes[0, column].set_title(a.time.dt.strftime("%H:%M").item())
        for row in range(2):
            ax = axes[row, column]
            ax.set(xlim=(59.6, 60.4), ylim=(-20.4, -19.6),
                   xticks=[59.6, 60., 60.4], yticks=[-20.4, -20., -19.6],
                   aspect=1 / np.cos(np.deg2rad(20.)))
            ax.xaxis.set_major_formatter(FormatStrFormatter("%.1f"))
            ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
        axes[1, column].set_xlabel("Longitude (°E)")
    axes[0, 0].set_ylabel("Latitude (°N)")
    axes[1, 0].set_ylabel("Latitude (°N)")
    axes[0, 2].quiverkey(arrows, .92, .95, 20, "20 m s$^{-1}$", coordinates="figure")
    fig.colorbar(temperature, ax=axes[0], label="10 m air temperature (K)", shrink=.85)
    fig.colorbar(sst, ax=axes[1], label="SST (K)", shrink=.85)
    fig.savefig(args.figure)
