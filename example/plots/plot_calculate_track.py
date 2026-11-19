"""Compare an exported track with the known positions in the fixture."""
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import xarray as xr
from matplotlib.ticker import FormatStrFormatter, LinearLocator

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("track", type=Path)
parser.add_argument("reference", type=Path)
parser.add_argument("figure", type=Path)
args = parser.parse_args()
if not args.figure.suffix:
    parser.error("figure needs an explicit extension, for example .svg")
if args.figure.exists():
    raise FileExistsError(args.figure)

with xr.open_dataset(args.track) as track, xr.open_dataset(args.reference) as reference:
    if not track.indexes["time"].equals(reference.indexes["time"]):
        raise ValueError("Calculated and known positions must have the same times")
    fig, ax = plt.subplots(figsize=(5, 3.6), layout="constrained")
    ax.plot(reference.longitude, reference.latitude, "o--", markersize=10,
            markerfacecolor="none", label="Known positions")
    ax.plot(track.longitude, track.latitude, "x", label="Calculated centres")
    ax.set(xlabel="Longitude (°E)", ylabel="Latitude (°N)",
           title="Calculated and known positions")
    ax.set_xticks(reference.longitude.values)
    bottom = min(float(track.latitude.min()), float(reference.latitude.min()))
    top = max(float(track.latitude.max()), float(reference.latitude.max()))
    ax.set_ylim(bottom - .1, top + .1)
    ax.yaxis.set_major_locator(LinearLocator(3))
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.legend(loc="upper left")
    fig.savefig(args.figure)
