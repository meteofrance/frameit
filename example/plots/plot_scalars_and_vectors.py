"""Plot the explicitly requested speed from a generated wind field."""
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
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
    fig, ax = plt.subplots(figsize=(4.8, 3.6), layout="constrained")
    data.speed.isel(time=0).plot(ax=ax, cmap="viridis")
    ax.set_title("Requested Earth-relative wind speed")
    fig.savefig(args.figure)
