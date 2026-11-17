"""Show the single retained atmospheric layer from the prescribed-event run."""
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
    print(data.time.values, data["height.temperature"].dims)
    fig, ax = plt.subplots(figsize=(4.8, 3.6), layout="constrained")
    data["height.temperature"].isel(time=0).squeeze(drop=True).plot(ax=ax, cmap="viridis")
    ax.set_title("Retained 1000 m layer: 294 K")
    fig.savefig(args.figure)
