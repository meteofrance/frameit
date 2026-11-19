"""Show the retained valid times and forecast leads at one grid point."""
import argparse
from pathlib import Path

import matplotlib.dates as mdates
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
    pressure = data.prmsl.isel(y=0, x=0).values
    leads = data.step.values / np.timedelta64(1, "h")
    fig, ax = plt.subplots(figsize=(5, 3.6), layout="constrained")
    ax.plot(data.time, pressure, "o-")
    for time, value, lead in zip(data.time.values, pressure, leads, strict=True):
        ax.annotate(f"+{lead:g} h", (time, value), xytext=(0, 8),
                    textcoords="offset points", ha="center")
    ax.set(xlabel="Valid time (UTC)", ylabel="Mean sea-level pressure (Pa)",
           title="Samples from the selected forecast")
    ax.set_xticks(data.time.values)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.margins(x=.15, y=.2)
    fig.savefig(args.figure)
