"""Standalone real-data illustrations; imports no FrameIt code.

Usage: python batsirai_wind.py DATA_DIR FIXED_RUN MOVING_RUN NEW_OUTPUT_DIR
Plot the stored UM10 (Earth-relative 10-m zonal wind, m s-1) at the later time.
The source explicitly declares a one-cell nonphysical outer halo, omitted here.
"""

from pathlib import Path
import sys

import numpy as np
import xarray as xr


def main(data, fixed, moving, output):
    import matplotlib.pyplot as plt

    data, fixed, moving, output = (Path(p).resolve() for p in (data, fixed, moving, output))
    if output.is_relative_to(data):
        raise ValueError("Write figures outside the read-only source-data directory")
    files = sorted(data.glob("*dg.nc"))
    if len(files) != 2:
        raise ValueError("This bounded example requires exactly two diagnostic files")
    with xr.open_dataset(files[0], engine="netcdf4") as a, xr.open_dataset(files[1], engine="netcdf4") as b:
        if any(d.UM10.attrs.get("units") != "m s-1" for d in (a, b)):
            raise ValueError("UM10 must declare wind velocity in m s-1")
        xr.testing.assert_equal(a.latitude, b.latitude)
        xr.testing.assert_equal(a.longitude, b.longitude)
        times = np.array([a.time.values[0], b.time.values[0]], dtype="datetime64[ns]")
        for dimension in b.UM10.dims[-2:]:
            if b[dimension].attrs.get("c_grid_dynamic_range") != f"2:{b.sizes[dimension] - 1}":
                raise ValueError("This example requires the declared one-cell nonphysical halo")
        full = b.UM10.isel(time=0).values[1:-1, 1:-1]
        latitude, longitude = a.latitude.values.squeeze(), a.longitude.values.squeeze()
    output.mkdir(parents=True, exist_ok=False)
    cmap = plt.colormaps["RdBu_r"].with_extremes(bad="#9ba6b0")
    limit = np.ceil(np.nanmax(np.abs(full)) / 5) * 5
    timestamp = np.datetime_as_string(times[-1], unit="m")

    def draw(name, x, y, values, title, *, polar=False):
        fig, ax = plt.subplots(figsize=(7, 4.8), subplot_kw={"projection": "polar"} if polar else {},
                               layout="constrained")
        image = ax.pcolormesh(x, y, values, shading="nearest", cmap=cmap,
                              vmin=-limit, vmax=limit, rasterized=True)
        if polar:
            ax.set_theta_zero_location("N")
            ax.set_theta_direction(-1)
            ax.set_yticks([tick for tick in ax.get_yticks() if 0 < tick <= np.max(y)])
            ax.set_ylim(0, np.max(y))
            ax.set_ylabel("Radius (km)", labelpad=25)
        else:
            ax.set(xlabel="Longitude (degrees east)", ylabel="Latitude (degrees north)")
            ax.set_aspect(1 / np.cos(np.deg2rad(np.nanmean(latitude))))
        ax.grid(False)
        ax.set_title(title, fontsize=13, pad=15)
        fig.colorbar(image, ax=ax, label="10-m zonal wind (m/s)", shrink=.85)
        fig.supxlabel(timestamp + "\nPositive: eastward · negative: westward · grey: missing", fontsize=9)
        return fig, ax, output / name

    for run, name, title in ((fixed, "batsirai-fixed.png", "Fixed native crop"),
                              (moving, "batsirai-tracking.png", "Pressure–wind track and final crop")):
        prefix = "batsirai-fixed" if run == fixed else "batsirai-moving"
        with xr.open_dataset(run / "products" / f"{prefix}.track.nc", engine="netcdf4") as track:
            fig, ax, path = draw(name, longitude[1:-1, 1:-1], latitude[1:-1, 1:-1], full, title)
            if run == moving:
                ax.plot(track.lon, track.lat, "o-", color="#021633", markerfacecolor="white",
                        linewidth=1.5, markersize=5, label="Tracking centres")
            else:
                ax.plot(track.lon[0], track.lat[0], "o", color="#021633", label="Fixed centre")
            j0, j1 = (int(track[n].isel(time=-1)) for n in ("iy_min", "iy_max"))
            i0, i1 = (int(track[n].isel(time=-1)) for n in ("ix_min", "ix_max"))
            corners = [(j0, i0), (j0, i1), (j1, i1), (j1, i0), (j0, i0)]
            ax.plot([longitude[j, i] for j, i in corners], [latitude[j, i] for j, i in corners],
                    color="#ad3200", linewidth=1.7, label="Native crop")
            for limits, coordinates in ((ax.set_xlim, longitude), (ax.set_ylim, latitude)):
                edges = [coordinates[j, i] for j, i in corners]
                padding = (max(edges) - min(edges)) / 4
                limits(min(edges) - padding, max(edges) + padding)
            ax.legend(loc="upper left", fontsize=9)
            fig.savefig(path, dpi=180)
            plt.close(fig)
    for role, name, title in (("cart", "batsirai-cartesian.png", "Zonal wind — native points"),
                               ("polar", "batsirai-polar.png", "Zonal wind — polar points")):
        with xr.open_dataset(fixed / "products" / f"batsirai-fixed.{role}.surface.nc", engine="netcdf4") as ds:
            if ds.UM10.attrs.get("units") != "m s-1":
                raise ValueError("Exported UM10 must retain m s-1")
            np.testing.assert_array_equal(ds.time.values, times)
            snapshot = ds.isel(time=-1)
            values = snapshot.UM10.values
            x, y = (ds.theta.values, ds.rr.values) if role == "polar" else (snapshot.longitude, snapshot.latitude)
            fig, _, path = draw(name, x, y, values, title, polar=role == "polar")
            fig.savefig(path, dpi=180)
            plt.close(fig)


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
