"""Plot retained source times, averaging intervals, and the omitted pair."""
import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
import yaml

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("atmosphere", type=Path)
parser.add_argument("ocean", type=Path)
parser.add_argument("status", type=Path)
parser.add_argument("figure", type=Path)
args = parser.parse_args()
if not args.figure.suffix:
    parser.error("figure needs an explicit extension, for example .svg")
if args.figure.exists():
    raise FileExistsError(args.figure)

status = yaml.safe_load(args.status.read_text())
omitted = np.array(
    [pair["coupling_time"] for pair in status["time_alignment"]["omitted_pairings"]],
    dtype="datetime64[ns]")
with xr.open_dataset(args.atmosphere) as air, xr.open_dataset(args.ocean) as ocean:
    fig, ax = plt.subplots(figsize=(6.4, 3.2), layout="constrained")
    for start, end in ocean[ocean.time.attrs["bounds"]].values:
        ax.plot([start, end], [0, 0], color="0.35", linewidth=2)
    ax.plot(ocean.time, np.zeros(ocean.sizes["time"]), "o", label="Mean label")
    ax.vlines(ocean.center_time, 0, 1, color="0.35", linestyles="dotted")
    ax.plot(air.time, np.ones(air.sizes["time"]), "s", label="Retained snapshot")
    ax.plot(omitted, np.ones(omitted.size), "x", label="Omitted pair")
    ax.set(yticks=[0, 1], yticklabels=["NEMO mean", "AROME snapshot"],
           xlabel="Time (UTC)", ylim=(-.35, 1.65))
    ax.xaxis.set_major_locator(mdates.HourLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.legend(loc="upper center", ncols=3)
    fig.savefig(args.figure)
