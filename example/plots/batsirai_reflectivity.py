"""Standalone real-data illustrations; imports no FrameIt code.

Usage: python batsirai_reflectivity.py DATA_DIR FIXED_RUN MOVING_RUN NEW_OUTPUT_DIR
The two ACPRR records define a mean rain rate, not instantaneous reflectivity.
Illustrative rain-only relation: Z = 200 R**1.6, R in mm/h, Z in mm6/m3.
No calibration to this simulation, ice scattering or native radar diagnostic is claimed.
"""

from pathlib import Path
import sys

import numpy as np
import xarray as xr


def rain_only_dbz(first_mm, second_mm, interval_hours):
    """Preserve missing values and physical no-rain; reject accumulation resets."""
    if not np.isfinite(interval_hours) or interval_hours <= 0:
        raise ValueError("Rainfall interval must be finite and positive")
    rate = (np.asarray(second_mm) - np.asarray(first_mm)) / interval_hours
    if np.any(np.isfinite(rate) & (rate < 0)):
        raise ValueError("Accumulated rainfall decreased: check for an accumulation reset")
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(200 * rate**1.6)


def main(data, fixed, moving, output):
    import matplotlib.pyplot as plt

    data, fixed, moving, output = (Path(p).resolve() for p in (data, fixed, moving, output))
    if output.is_relative_to(data):
        raise ValueError("Write figures outside the read-only source-data directory")
    files = sorted(data.glob("*dg.nc"))
    if len(files) != 2:
        raise ValueError("This bounded example requires exactly two diagnostic files")
    with xr.open_dataset(files[0], engine="netcdf4") as a, xr.open_dataset(files[1], engine="netcdf4") as b:
        if any(d.ACPRR.attrs.get("units") != "mm" for d in (a, b)):
            raise ValueError("ACPRR must declare accumulated rainfall in mm")
        xr.testing.assert_equal(a.latitude, b.latitude)
        xr.testing.assert_equal(a.longitude, b.longitude)
        times = np.array([a.time.values[0], b.time.values[0]], dtype="datetime64[ns]")
        hours = float((times[1] - times[0]) / np.timedelta64(1, "h"))
        full = rain_only_dbz(a.ACPRR.isel(time=0).values, b.ACPRR.isel(time=0).values, hours)
        latitude, longitude = a.latitude.values.squeeze(), a.longitude.values.squeeze()
    output.mkdir(parents=True, exist_ok=False)
    cmap = plt.colormaps["viridis"].with_extremes(under="white", bad="#9ba6b0")
    interval = " – ".join(np.datetime_as_string(t, unit="m") for t in times)

    def draw(name, x, y, values, title, *, polar=False):
        fig, ax = plt.subplots(figsize=(7, 4.8), subplot_kw={"projection": "polar"} if polar else {},
                               layout="constrained")
        # Display no-rain as under-range white, distinct from missing-data grey.
        shown = np.where(np.isneginf(values), -11., values)
        image = ax.pcolormesh(x, y, shown, shading="nearest", cmap=cmap, vmin=-10, vmax=55,
                              rasterized=True)
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
        fig.colorbar(image, ax=ax, label="Rain-only reflectivity estimate (dBZ)", extend="min", shrink=.85)
        fig.supxlabel(interval + "\nWhite: below −10 dBZ / no rain · grey: missing", fontsize=9)
        return fig, ax, output / name

    for run, name, title in ((fixed, "batsirai-fixed.png", "Fixed native crop"),
                              (moving, "batsirai-tracking.png", "Pressure–wind track and final crop")):
        prefix = "batsirai-fixed" if run == fixed else "batsirai-moving"
        with xr.open_dataset(run / "products" / f"{prefix}.track.nc", engine="netcdf4") as track:
            fig, ax, path = draw(name, longitude, latitude, full, title)
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
    for role, name, title in (("cart", "batsirai-cartesian.png", "Extracted rainfall — native points"),
                               ("polar", "batsirai-polar.png", "Extracted rainfall — polar points")):
        with xr.open_dataset(fixed / "products" / f"batsirai-fixed.{role}.surface.nc", engine="netcdf4") as ds:
            if ds.ACPRR.attrs.get("units") != "mm":
                raise ValueError("Exported ACPRR must retain mm")
            np.testing.assert_array_equal(ds.time.values, times)
            values = rain_only_dbz(ds.ACPRR.isel(time=0).values, ds.ACPRR.isel(time=1).values, hours)
            first = ds.isel(time=0)
            x, y = (ds.theta.values, ds.rr.values) if role == "polar" else (first.longitude, first.latitude)
            fig, _, path = draw(name, x, y, values, title, polar=role == "polar")
            fig.savefig(path, dpi=180)
            plt.close(fig)


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
