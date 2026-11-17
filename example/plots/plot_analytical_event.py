"""Plot the requested polar wind speed without subtracting centre motion."""
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("product", type=Path)
parser.add_argument("figure", type=Path)
args = parser.parse_args()
if not args.figure.suffix:
    parser.error("figure needs an explicit extension, for example .svg")
if args.figure.exists():
    raise FileExistsError(args.figure)
with xr.open_dataset(args.product) as data:
    fig, ax = plt.subplots(figsize=(5, 4), subplot_kw={"projection": "polar"}, layout="constrained")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    field = data.speed.isel(time=0).transpose("radius", "azimuth")
    r, theta = data.radius.values, data.azimuth.values
    radial_edges = np.r_[0, (r[:-1] + r[1:]) / 2, r[-1]]
    azimuth_edges = np.r_[(theta[-1] + theta[0] - 2*np.pi) / 2,
                         (theta[:-1] + theta[1:]) / 2, (theta[-1] + theta[0] + 2*np.pi) / 2]
    mesh = ax.pcolormesh(azimuth_edges, radial_edges, field, shading="flat",
                         cmap="viridis", vmin=0)
    radius = float(data.radius[-1])
    ax.set_ylim(0, radius)
    ax.set_thetagrids([0, 90, 180, 270], ["N", "E", "S", "W"])
    ax.set_yticks([radius / 2, radius], [f"{radius / 2:g} km", f"{radius:g} km"])
    ax.set_rlabel_position(225)
    ax.set_title(f"Polar wind speed, {data.time.dt.strftime('%H:%M').values[0]}", pad=18)
    fig.colorbar(mesh, ax=ax, label="Wind speed (m s$^{-1}$)", shrink=.8, pad=.12)
    fig.savefig(args.figure)
