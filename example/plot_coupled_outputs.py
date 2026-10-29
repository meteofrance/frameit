#!/usr/bin/env python3
"""Plot coupled FrameIt NetCDF outputs without importing FrameIt.

Run beside the NetCDF files with::

    conda run -n test python plot_coupled_outputs.py

Dependencies: numpy, xarray, netCDF4, matplotlib, cartopy, cmocean, PyYAML.
Cartopy downloads Natural Earth's finest available (1:10 million) layers once.
Figures are exploratory: neither tracked storm identity nor field accuracy is
established. Missing samples are not filled. See plots/plot_manifest.json for
selection rules, transformations, limitations and dependency versions.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import cartopy
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cmocean
import matplotlib
from cartopy.mpl.gridliner import Gridliner

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import xarray as xr
import yaml
from matplotlib.colors import Normalize, TwoSlopeNorm
from matplotlib.text import Text

INK = "#192e43"
BLUE = "#176b97"
RED = "#bd4d44"
GEO = ccrs.PlateCarree()
PRODUCTS = {
    "track": "track",
    "surface": "cart.atmosphere.surface",
    "temperature": "cart.atmosphere.heightAboveGround",
    "profiles": "cart.atmosphere.isobaricInhPa",
    "surfex": "cart.surfex.surface",
    "polar_pressure": "polar.atmosphere.surface",
    "polar_temperature": "polar.atmosphere.heightAboveGround",
    "polar_profiles": "polar.atmosphere.isobaricInhPa",
    "polar_surfex": "polar.surfex.surface",
}
STEMS = (
    "01_track_and_surface_evolution",
    "02_surface_wind_and_pressure",
    "03_coupled_temperature_comparison",
    "04_vertical_evolution_at_tracked_centres",
    "05_vertical_section_through_peak_ascent",
)


def style():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "axes.labelcolor": INK,
            "axes.edgecolor": "#9ca8b2",
            "axes.linewidth": 0.7,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "xtick.color": "#475968",
            "ytick.color": "#475968",
            "text.color": INK,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.unicode_minus": True,
        }
    )


def stamp(value, year=False):
    dt = np.datetime64(value, "s").astype(datetime)
    return dt.strftime("%d %b %Y · %H UTC" if year else "%d %b · %H UTC")


def heading(fig, title, subtitle, footer):
    fig.text(0.055, 0.973, title, fontsize=20, weight="bold", va="top")
    fig.text(0.055, 0.925, subtitle, fontsize=10.5, color="#526576", va="top")
    fig.text(0.055, 0.022, footer, fontsize=9, color="#526576", va="bottom")


def require_units(data, accepted):
    units = str(data.attrs.get("units", "")).strip()
    if units not in accepted:
        raise ValueError(f"{data.name}: expected units {sorted(accepted)}, found {units!r}.")


def temperature_2m(ds, name):
    data = ds[name]
    require_units(data, {"K"})
    if "heightAboveGround" in data.dims:
        if not np.array_equal(ds.heightAboveGround.values, [2.0]):
            raise ValueError(f"{name}: expected one explicitly identified 2 m level.")
        data = data.squeeze("heightAboveGround", drop=True)
    return data


def wind_speed(ds, u_name, v_name):
    u, v = ds[u_name], ds[v_name]
    for data in (u, v):
        require_units(data, {"m s-1", "m s**-1", "m s^-1"})
        if data.attrs.get("grid_position") != "mass_aligned":
            raise ValueError(f"{data.name}: native staggered winds need explicit collocation.")
        if data.attrs.get("wind_reference_frame") != "earth":
            raise ValueError(f"{data.name}: expected explicitly Earth-relative components.")
    if u.dims != v.dims:
        raise ValueError("Wind components do not occupy the same dimensions.")
    u, v = xr.align(u, v, join="exact")
    return np.hypot(u, v)


def verify_shared_target(reference, other):
    target = reference.attrs.get("common_polar_target_id")
    if not target or target != other.attrs.get("common_polar_target_id"):
        raise ValueError("The polar products do not identify the same shared target.")
    for name in ("time", "rr", "theta", "latitude", "longitude"):
        if not np.array_equal(reference[name].values, other[name].values):
            raise ValueError(f"Shared polar {name} differs; refusing pointwise comparison.")
    if reference.attrs.get("theta_convention") != "azimuth_clockwise_from_north":
        raise ValueError("Expected north-zero, clockwise polar azimuths.")
    theta = reference.theta.values
    if not np.allclose(np.diff(np.r_[theta, theta[0] + 2 * np.pi]), 2 * np.pi / len(theta)):
        raise ValueError("Angular means require the expected uniform periodic azimuth grid.")
    require_units(reference.rr, {"km"})


def valid_polar(ds, name):
    data = ds[name]
    flag = f"{name}_valid"
    if flag not in ds:
        raise ValueError(f"Missing sampling validity flags: {flag}.")
    return data.where((ds[flag] == 1) & np.isfinite(data))


def complete_ring_mean(data):
    """Equal-angle mean; any missing azimuth makes the ring missing."""
    return data.mean("theta", skipna=False)


def cart_geolocation(ds, index):
    lon = ds.longitude.isel(time=index).values
    lat = ds.latitude.isel(time=index).values
    if lon.ndim == lat.ndim == 1:
        lon, lat = np.meshgrid(lon, lat)
    if lon.ndim != 2 or lon.shape != lat.shape:
        raise ValueError("Expected a rectilinear or two-dimensional geographic grid.")
    return lon, lat


def extent_for(ds, index, pad=0.05):
    lon, lat = cart_geolocation(ds, index)
    return [lon.min() - pad, lon.max() + pad, lat.min() - pad, lat.max() + pad]


def map_axes(fig, spec, extent, left=True, bottom=True, backdrop=False):
    ax = fig.add_subplot(spec, projection=ccrs.Mercator(central_longitude=35))
    ax.set_extent(extent, crs=GEO)
    ax.set_facecolor("#edf3f6")
    if backdrop:
        ax.add_feature(cfeature.LAND.with_scale("10m"), facecolor="#e9e6dc", zorder=0)
        ax.add_feature(cfeature.LAKES.with_scale("10m"), facecolor="#d0e4ef", zorder=1)
    ax.coastlines(resolution="10m", color="#354e5d", linewidth=0.75, zorder=6)
    ax.add_feature(
        cfeature.BORDERS.with_scale("10m"),
        edgecolor="#506574",
        linewidth=0.65,
        linestyle=(0, (4, 2)),
        zorder=6,
    )
    ax.add_feature(
        cfeature.LAKES.with_scale("10m"),
        facecolor="none",
        edgecolor="#476d83",
        linewidth=0.55,
        zorder=6,
    )
    grid = ax.gridlines(
        crs=GEO,
        draw_labels=True,
        linewidth=0.45,
        color="#657887",
        alpha=0.35,
        linestyle=":",
        x_inline=False,
        y_inline=False,
    )
    grid.top_labels = False
    grid.right_labels = False
    grid.left_labels = left
    grid.bottom_labels = bottom
    grid.xlocator = mticker.MaxNLocator(4)
    grid.ylocator = mticker.MaxNLocator(4)
    grid.xlabel_style = grid.ylabel_style = {"size": 8.5, "color": "#475968"}
    grid.xpadding = grid.ypadding = 5
    return ax


def centre_marker(ax, track, index):
    (line,) = ax.plot(
        float(track.lon[index]),
        float(track.lat[index]),
        marker="+",
        ms=11,
        mew=1.9,
        color=INK,
        transform=GEO,
        zorder=9,
        path_effects=[pe.Stroke(linewidth=3.5, foreground="white"), pe.Normal()],
    )
    line.set_gid("tracked-centre")


def time_axis(ax, times):
    hours = times.astype("datetime64[h]")
    step = max(1, int(np.ceil(len(hours) / 5)))
    ax.set_xticks(mdates.date2num(hours[::step].astype("datetime64[ms]").astype(object)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H UTC"))
    ax.grid(axis="y", color="#dfe5e9", linewidth=0.7, zorder=0)
    ax.tick_params(axis="x", pad=6)


def colourbar(fig, artist, spec, label, ticks=None):
    cax = fig.add_subplot(spec)
    bar = fig.colorbar(artist, cax=cax, orientation="horizontal", ticks=ticks)
    bar.set_ticks([t for t in bar.get_ticks() if bar.vmin <= t <= bar.vmax])
    bar.set_label(label, labelpad=6)
    bar.outline.set_linewidth(0.5)
    return bar


def symmetric_limit(data, step):
    finite = np.asarray(data)[np.isfinite(data)]
    if not finite.size:
        raise ValueError("No finite values are available for a colour scale.")
    return max(step, np.ceil(np.max(np.abs(finite)) / step) * step)


def tracked_columns(profiles, track):
    """Select native points only when they coincide with the recorded centres."""
    if profiles.latitude.dims != ("time", "y_box"):
        raise ValueError("This example expects the atmospheric regular-latitude grid.")
    iy = np.abs(profiles.latitude.values - track.lat.values[:, None]).argmin(axis=1)
    ix = np.abs(profiles.longitude.values - track.lon.values[:, None]).argmin(axis=1)
    rows = np.arange(len(iy))
    if not np.allclose(profiles.latitude.values[rows, iy], track.lat.values, atol=1e-8, rtol=0):
        raise ValueError("Track centres are off-grid; explicitly choose an interpolation method.")
    if not np.allclose(profiles.longitude.values[rows, ix], track.lon.values, atol=1e-8, rtol=0):
        raise ValueError("Track centres are off-grid; explicitly choose an interpolation method.")
    return profiles.isel(
        y_box=xr.DataArray(iy, dims="time", coords={"time": track.time}),
        x_box=xr.DataArray(ix, dims="time", coords={"time": track.time}),
    )


def figure_track(data):
    track, surface = data["track"], data["surface"]
    times = track.time.values
    speed = wind_speed(surface, "u10", "v10")
    maximum = speed.max(("y_box", "x_box"), skipna=False).values
    peak = int(np.nanargmax(maximum))
    minimum = (surface.prmsl / 100).min(("y_box", "x_box"), skipna=False).values
    central = valid_polar(data["polar_pressure"], "prmsl").isel(rr=0, theta=0).values / 100
    fig = plt.figure(figsize=(14.5, 8.3))
    heading(
        fig,
        "Tracked centres and surface evolution",
        f"AROME / SURFEX · {stamp(times[0], True)} — {stamp(times[-1])} · identity unverified",
        "Extrema refer to each moving native crop, not verified storm intensity. "
        "Dashed box: crop at maximum 10 m wind.",
    )
    grid = fig.add_gridspec(
        2,
        2,
        left=0.065,
        right=0.955,
        bottom=0.18,
        top=0.81,
        width_ratios=[1.05, 1],
        hspace=0.52,
        wspace=0.34,
    )
    extent = [
        float(track.lon.min()) - 2.0,
        float(track.lon.max()) + 2.0,
        float(track.lat.min()) - 1.1,
        float(track.lat.max()) + 1.1,
    ]
    ax = map_axes(fig, grid[:, 0], extent, backdrop=True)
    ax.set_title("Southeast Africa", loc="left", pad=12)
    ax.plot(track.lon, track.lat, color=INK, lw=1.5, transform=GEO, zorder=7)
    elapsed = (times - times[0]) / np.timedelta64(1, "h")
    points = ax.scatter(
        track.lon,
        track.lat,
        c=elapsed,
        cmap=cmocean.cm.thermal,
        s=65,
        edgecolors="white",
        linewidths=0.9,
        transform=GEO,
        zorder=8,
    )
    for i, shift, align in ((0, (-12, -18), "right"), (len(times) - 1, (12, 10), "left")):
        ax.annotate(
            stamp(times[i]),
            xy=(float(track.lon[i]), float(track.lat[i])),
            xycoords=GEO._as_mpl_transform(ax),
            xytext=shift,
            textcoords="offset points",
            fontsize=9,
            ha=align,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 2},
            zorder=10,
        )
    lon, lat = cart_geolocation(surface, peak)
    boundary_lon = np.r_[lon[0, :], lon[1:, -1], lon[-1, -2::-1], lon[-2:0:-1, 0], lon[0, 0]]
    boundary_lat = np.r_[lat[0, :], lat[1:, -1], lat[-1, -2::-1], lat[-2:0:-1, 0], lat[0, 0]]
    ax.plot(boundary_lon, boundary_lat, "--", color=RED, lw=1.3, transform=GEO, zorder=7)
    position = ax.get_position()
    cax = fig.add_axes([position.x0 + 0.03, 0.095, position.width - 0.06, 0.018])
    bar = fig.colorbar(
        points, cax=cax, orientation="horizontal", ticks=np.linspace(0, elapsed[-1], 5)
    )
    bar.set_label("Hours since first valid time", labelpad=4)
    pressure_ax = fig.add_subplot(grid[0, 1])
    pressure_ax.set_title("Sea-level pressure", loc="left", pad=34)
    pressure_ax.plot(times, minimum, "o-", color=BLUE, ms=4, lw=1.8, label="Crop minimum")
    pressure_ax.plot(times, central, "s--", color=RED, ms=4, lw=1.6, label="At tracked centre")
    pressure_ax.legend(
        loc="lower left",
        bbox_to_anchor=(0, 1.015),
        ncols=2,
        frameon=False,
        borderaxespad=0,
        fontsize=9,
        handlelength=2.2,
    )
    pressure_ax.set_ylabel("Pressure (hPa)")
    pressure_ax.margins(y=0.18)
    time_axis(pressure_ax, times)
    wind_ax = fig.add_subplot(grid[1, 1])
    wind_ax.set_title("Maximum 10 m wind in each crop", loc="left", pad=12)
    wind_ax.plot(times, maximum, "o-", color=BLUE, ms=5, lw=1.9)
    wind_ax.scatter(times[peak], maximum[peak], s=85, facecolors="none", edgecolors=RED, lw=1.8)
    wind_ax.set_ylabel("Wind speed (m s$^{-1}$)")
    wind_ax.set_ylim(0, np.ceil(maximum.max() / 2) * 2 + 1)
    time_axis(wind_ax, times)
    return fig, {"maximum_10m_wind_m_s": maximum.tolist(), "minimum_mslp_hpa": minimum.tolist()}


def figure_surface(data):
    surface, track = data["surface"], data["track"]
    times = track.time.values
    speed = wind_speed(surface, "u10", "v10")
    vmax = float(np.ceil(float(speed.max()) / 2) * 2)
    cols = min(3, len(times))
    rows = int(np.ceil(len(times) / cols))
    fig = plt.figure(figsize=(15.0, 3.6 * rows + 2.4))
    heading(
        fig,
        "Surface wind and pressure at every common time",
        f"AROME · {len(times)} native-grid snapshots · "
        f"{stamp(times[0], True)} — {stamp(times[-1])}",
        "Contours: sea-level pressure (hPa) · + tracked centre · arrows: Earth-relative 10 m wind",
    )
    grid = fig.add_gridspec(
        rows,
        cols,
        left=0.075,
        right=0.955,
        bottom=0.165,
        top=0.855,
        hspace=0.23,
        wspace=0.12,
    )
    pressure_levels = np.arange(
        np.floor(float(surface.prmsl.min()) / 200) * 2,
        np.ceil(float(surface.prmsl.max()) / 200) * 2 + 1,
        2,
    )
    quiver = None
    for i in range(len(times)):
        ax = map_axes(
            fig,
            grid[i // cols, i % cols],
            extent_for(surface, i),
        )
        lon, lat = cart_geolocation(surface, i)
        artist = ax.pcolormesh(
            lon,
            lat,
            speed.isel(time=i),
            cmap=cmocean.cm.speed,
            vmin=0,
            vmax=vmax,
            transform=GEO,
            shading="auto",
            rasterized=True,
            zorder=2,
        )
        contours = ax.contour(
            lon,
            lat,
            surface.prmsl.isel(time=i) / 100,
            levels=pressure_levels,
            colors=INK,
            linewidths=0.65,
            alpha=0.8,
            transform=GEO,
            zorder=4,
        )
        labels = ax.clabel(contours, fmt="%d", fontsize=7.5, inline=False)
        for label in labels:
            label.set_gid("contour-label")
            label.set_path_effects([pe.Stroke(linewidth=2, foreground="white"), pe.Normal()])
        sl = np.s_[5::10, 5::10]
        quiver = ax.quiver(
            lon[sl],
            lat[sl],
            surface.u10.isel(time=i).values[sl],
            surface.v10.isel(time=i).values[sl],
            transform=GEO,
            color=INK,
            units="inches",
            scale_units="inches",
            scale=48,
            width=0.011,
            headwidth=3.5,
            alpha=0.8,
            zorder=5,
        )
        centre_marker(ax, track, i)
        ax.set_title(stamp(times[i]), loc="left", pad=10, fontsize=11)
    cax = fig.add_axes([0.23, 0.093, 0.54, 0.015])
    bar = fig.colorbar(artist, cax=cax, orientation="horizontal", ticks=np.arange(0, vmax + 1, 2))
    bar.set_label("10 m wind speed (m s$^{-1}$)", labelpad=5)
    ax.quiverkey(
        quiver,
        0.865,
        0.027,
        10,
        "10 m s$^{-1}$",
        coordinates="figure",
        labelpos="E",
        labelsep=0.08,
        fontproperties={"size": 9},
    )
    return fig, {"wind_colour_limits_m_s": [0, vmax], "pressure_contour_interval_hpa": 2}


def figure_temperature(data):
    polar_a, polar_s = data["polar_temperature"], data["polar_surfex"]
    a = valid_polar(polar_a, "t2m").squeeze("heightAboveGround", drop=True)
    s = valid_polar(polar_s, "SFX.T2M")
    delta = s - a
    positive_r = delta.where(delta.rr > 0, drop=True)
    point_rms = np.sqrt((positive_r**2).mean(("rr", "theta"), skipna=False)).values
    if not np.isfinite(point_rms).any():
        raise ValueError("No complete shared target is available for temperature selection.")
    selected = int(np.nanargmax(point_rms))
    native_a = temperature_2m(data["temperature"], "t2m").isel(time=selected) - 273.15
    native_s = temperature_2m(data["surfex"], "SFX.T2M").isel(time=selected) - 273.15
    lower = np.floor(min(float(native_a.min()), float(native_s.min())) / 2) * 2
    upper = np.ceil(max(float(native_a.max()), float(native_s.max())) / 2) * 2
    dmax = symmetric_limit(delta.isel(time=selected).values, 1)
    times = data["track"].time.values
    ring_rms = np.sqrt(complete_ring_mean(delta**2))
    fig = plt.figure(figsize=(15.5, 10.2))
    heading(
        fig,
        "2 m temperature across the coupled outputs",
        f"{stamp(times[selected], True)} · largest shared-point RMS difference: "
        f"{point_rms[selected]:.2f} K (r > 0)",
        "ΔT = SURFEX − atmospheric GRIB · existing shared WGS84 / bilinear samples; "
        "neither source is observational truth.",
    )
    grid = fig.add_gridspec(
        4,
        3,
        left=0.075,
        right=0.955,
        bottom=0.14,
        top=0.84,
        height_ratios=[1, 0.045, 0.86, 0.045],
        hspace=0.80,
        wspace=0.30,
    )
    extent = extent_for(data["temperature"], selected)
    artists = []
    for j, (key, values, title) in enumerate(
        (
            ("temperature", native_a, "Atmospheric GRIB · native grid"),
            ("surfex", native_s, "SURFEX FA · native grid"),
        )
    ):
        ax = map_axes(fig, grid[0, j], extent)
        lon, lat = cart_geolocation(data[key], selected)
        artist = ax.pcolormesh(
            lon,
            lat,
            values,
            cmap=cmocean.cm.thermal,
            vmin=lower,
            vmax=upper,
            shading="auto",
            transform=GEO,
            rasterized=True,
            zorder=2,
        )
        artists.append(artist)
        centre_marker(ax, data["track"], selected)
        ax.set_title(title, loc="left", pad=12, fontsize=11)
    ax = map_axes(fig, grid[0, 2], extent)
    lon = polar_a.longitude.isel(time=selected).values
    lat = polar_a.latitude.isel(time=selected).values
    d = delta.isel(time=selected).values

    def cyclic(x):
        return np.concatenate((x, x[:, :1]), axis=1)

    artist = ax.contourf(
        cyclic(lon),
        cyclic(lat),
        cyclic(d),
        levels=np.linspace(-dmax, dmax, 41),
        cmap=cmocean.cm.balance,
        norm=TwoSlopeNorm(0, -dmax, dmax),
        transform=GEO,
        zorder=2,
    )
    ax.plot(cyclic(lon)[-1], cyclic(lat)[-1], color=INK, lw=0.7, transform=GEO, zorder=4)
    centre_marker(ax, data["track"], selected)
    ax.set_title("SURFEX − GRIB · shared target", loc="left", pad=12, fontsize=11)
    colourbar(fig, artists[0], grid[1, :2], "2 m air temperature (°C)")
    colourbar(fig, artist, grid[1, 2], "ΔT (K)", ticks=np.linspace(-dmax, dmax, 5))
    ax = fig.add_subplot(grid[2, :])
    artist = ax.pcolormesh(
        times,
        delta.rr,
        ring_rms.transpose("rr", "time"),
        shading="nearest",
        cmap=cmocean.cm.amp,
        vmin=0,
        vmax=np.ceil(float(ring_rms.max()) * 10) / 10,
        rasterized=True,
    )
    ax.axvline(times[selected], color=INK, ls="--", lw=1.0)
    ax.set_title("Cross-source differences by radius and time", loc="left", pad=12)
    ax.set_ylabel("Radius from tracked centre (km)")
    ax.set_ylim(0, float(delta.rr.max()))
    time_axis(ax, times)
    ax.grid(False)
    colourbar(fig, artist, grid[3, :], "Complete-ring RMS ΔT (K) · equal-angle samples")
    return fig, {
        "selected_time_utc": np.datetime_as_string(times[selected], unit="s"),
        "selection": (
            "Maximum RMS SURFEX minus GRIB over shared points with rr > 0; no area weighting"
        ),
        "shared_point_rms_difference_k": point_rms.tolist(),
        "all_times_difference_range_k": [float(delta.min()), float(delta.max())],
    }


def pressure_axis(ax, levels):
    ax.set_yscale("log")
    ax.set_ylim(float(levels.max()), float(levels.min()))
    ax.set_yticks([700, 600, 500, 400, 300, 250, 200, 150])
    ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.yaxis.set_minor_locator(mticker.NullLocator())
    ax.set_ylabel("Pressure (hPa)")


def temperature_contours(ax, x, pressure, values):
    contours = ax.contour(
        x,
        pressure,
        values,
        levels=[-60, -40, -20, 0],
        colors=INK,
        linewidths=0.8,
        alpha=0.8,
    )
    labels = ax.clabel(contours, fmt=lambda t: f"{t:.0f}°C", fontsize=8, inline=False)
    for label in labels:
        label.set_gid("contour-label")
        label.set_path_effects([pe.Stroke(linewidth=2.5, foreground="white"), pe.Normal()])


def figure_vertical(data):
    track = data["track"]
    centre = tracked_columns(data["profiles"], track).sel(isobaricInhPa=slice(700, 150))
    pressure, times = centre.isobaricInhPa.values, track.time.values
    speed = wind_speed(centre, "u", "v")
    fig = plt.figure(figsize=(14.5, 10.2))
    heading(
        fig,
        "Vertical evolution at the tracked centres",
        f"AROME · exact native-grid columns · {stamp(times[0], True)} — {stamp(times[-1])}",
        "Columns follow the moving centres. 700–150 hPa only; lower levels omitted because "
        "no surface-pressure mask is available.",
    )
    grid = fig.add_gridspec(
        4,
        2,
        left=0.075,
        right=0.95,
        bottom=0.13,
        top=0.84,
        height_ratios=[1, 0.055, 1, 0.055],
        hspace=0.80,
        wspace=0.28,
    )
    omega_limit = symmetric_limit(centre.w.values, 0.25)
    wz_limit = symmetric_limit(centre.wz.values, 0.25)
    specs = (
        (
            centre.r,
            "Relative humidity + temperature",
            "Relative humidity (%)",
            cmocean.cm.haline,
            Normalize(0, 100),
        ),
        (
            speed,
            "Earth-relative horizontal wind",
            "Wind speed (m s$^{-1}$)",
            cmocean.cm.speed,
            Normalize(0, np.ceil(float(speed.max()) / 2) * 2),
        ),
        (
            centre.w,
            "Pressure vertical velocity",
            "ω (Pa s$^{-1}$; negative upward)",
            cmocean.cm.balance_r,
            TwoSlopeNorm(0, -omega_limit, omega_limit),
        ),
        (
            centre.wz,
            "Geometric vertical velocity",
            "$w_z$ (m s$^{-1}$; positive upward)",
            cmocean.cm.balance,
            TwoSlopeNorm(0, -wz_limit, wz_limit),
        ),
    )
    for i, (values, title, label, cmap, norm) in enumerate(specs):
        row, col = (i // 2) * 2, i % 2
        ax = fig.add_subplot(grid[row, col])
        artist = ax.pcolormesh(
            times,
            pressure,
            values.transpose("isobaricInhPa", "time"),
            shading="nearest",
            cmap=cmap,
            norm=norm,
            rasterized=True,
        )
        pressure_axis(ax, pressure)
        time_axis(ax, times)
        ax.grid(False)
        ax.set_title(title, loc="left", pad=12)
        if i == 0:
            temperature_contours(
                ax,
                times,
                pressure,
                (centre.t - 273.15).transpose("isobaricInhPa", "time"),
            )
        colourbar(fig, artist, grid[row + 1, col], label)
    return fig, {
        "pressure_range_hpa": [700, 150],
        "sampling": "Exact native column at each track centre",
    }


def figure_section(data):
    ds = data["profiles"]
    if 700.0 not in ds.isobaricInhPa.values:
        raise ValueError("The 700 hPa level is required for the ascent-section selection.")
    peak_field = ds.wz.sel(isobaricInhPa=700).transpose("time", "y_box", "x_box").values
    ti, yi, xi = (int(i) for i in np.unravel_index(np.nanargmax(peak_field), peak_field.shape))
    section = ds.isel(time=ti, y_box=yi).sel(isobaricInhPa=slice(700, 150))
    pressure = section.isobaricInhPa.values
    x = section.x_box_km.values
    lon, lat = cart_geolocation(ds, ti)
    peak_value = float(peak_field[ti, yi, xi])
    fig = plt.figure(figsize=(15.5, 7.7))
    heading(
        fig,
        "Vertical section through the strongest 700 hPa ascent",
        f"{stamp(ds.time.values[ti], True)} · east–west section at {abs(lat[yi, xi]):.2f}°S · "
        f"peak $w_z$ = {peak_value:.2f} m s$^{{-1}}$ at {lon[yi, xi]:.2f}°E",
        "Dashed line: selected 700 hPa maximum. Native pressure levels; no surface-pressure mask. "
        "ω and $w_z$ are distinct source fields.",
    )
    grid = fig.add_gridspec(
        2,
        3,
        left=0.07,
        right=0.96,
        bottom=0.19,
        top=0.81,
        height_ratios=[1, 0.045],
        hspace=0.48,
        wspace=0.30,
    )
    omega_limit = symmetric_limit(section.w.values, 0.25)
    wz_limit = symmetric_limit(section.wz.values, 0.5)
    specs = (
        (
            section.r,
            "Relative humidity + temperature",
            "Relative humidity (%)",
            cmocean.cm.haline,
            Normalize(0, 100),
        ),
        (
            section.w,
            "Pressure vertical velocity",
            "ω (Pa s$^{-1}$; negative upward)",
            cmocean.cm.balance_r,
            TwoSlopeNorm(0, -omega_limit, omega_limit),
        ),
        (
            section.wz,
            "Geometric vertical velocity",
            "$w_z$ (m s$^{-1}$; positive upward)",
            cmocean.cm.balance,
            TwoSlopeNorm(0, -wz_limit, wz_limit),
        ),
    )
    for i, (values, title, label, cmap, norm) in enumerate(specs):
        ax = fig.add_subplot(grid[0, i])
        artist = ax.pcolormesh(
            x,
            pressure,
            values.transpose("isobaricInhPa", "x_box"),
            shading="nearest",
            cmap=cmap,
            norm=norm,
            rasterized=True,
        )
        pressure_axis(ax, pressure)
        ax.set_xlim(x.min(), x.max())
        ax.set_xticks([-100, -50, 0, 50, 100])
        ax.set_xlabel("Native-grid x offset from tracked centre (km)", labelpad=8, fontsize=9)
        ax.axvline(x[xi], color=INK, ls="--", lw=1.0)
        ax.set_title(title, loc="left", pad=12, fontsize=11)
        if i == 0:
            temperature_contours(
                ax,
                x,
                pressure,
                (section.t - 273.15).transpose("isobaricInhPa", "x_box"),
            )
        colourbar(fig, artist, grid[1, i], label)
    return fig, {
        "selected_time_utc": np.datetime_as_string(ds.time.values[ti], unit="s"),
        "selection": (
            "Maximum finite native-grid geometric vertical velocity at 700 hPa over all times"
        ),
        "latitude_deg_north": float(lat[yi, xi]),
        "longitude_deg_east": float(lon[yi, xi]),
        "peak_geometric_vertical_velocity_m_s": peak_value,
        "section_y_box_index": yi,
        "pressure_range_hpa": [700, 150],
    }


def figure_texts(fig):
    texts = fig.findobj(Text)
    for ax in fig.axes:
        for artist in ax.get_children():
            if isinstance(artist, Gridliner):
                texts.extend(artist.label_artists)
    return list({id(text): text for text in texts}.values())


def save_figure(fig, output, stem, dpi):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    occupied = []
    for text in figure_texts(fig):
        if text.get_visible() and text.get_text().strip() and text.get_gid() != "contour-label":
            occupied.append(text.get_window_extent(renderer).expanded(1.08, 1.15))
    for ax in fig.axes:
        for line in ax.lines:
            if line.get_gid() == "tracked-centre":
                occupied.append(line.get_window_extent(renderer).expanded(1.3, 1.3))
    for text in figure_texts(fig):
        if text.get_gid() != "contour-label":
            continue
        box = text.get_window_extent(renderer).expanded(1.15, 1.25)
        frame = text.axes.get_window_extent(renderer)
        inside = frame.contains(box.x0, box.y0) and frame.contains(box.x1, box.y1)
        if not inside or any(box.overlaps(other) for other in occupied):
            text.set_visible(False)
        else:
            occupied.append(box)
    fig.canvas.draw()
    canvas = fig.bbox
    drawn = []
    for text in figure_texts(fig):
        if not text.get_visible() or not text.get_text().strip():
            continue
        box = text.get_window_extent(renderer)
        if box.width == 0 or box.height == 0:
            continue
        if box.x0 < -1 or box.y0 < -1 or box.x1 > canvas.width + 1 or box.y1 > canvas.height + 1:
            raise RuntimeError(f"Text falls outside the figure: {text.get_text()!r}")
        drawn.append((text, box))
    for (first, a), (second, b) in combinations(drawn, 2):
        if a.overlaps(b):
            raise RuntimeError(
                f"Overlapping figure text: {first.get_text()!r} / {second.get_text()!r}"
            )
    for suffix in ("png", "pdf"):
        path = output / f"{stem}.{suffix}"
        temporary = output / f".{stem}.{suffix}.partial"
        fig.savefig(
            temporary,
            format=suffix,
            dpi=dpi,
            metadata={"Creator": "plot_coupled_outputs.py"} if suffix == "pdf" else None,
        )
        os.replace(temporary, path)
        print(f"Saved {path.name}", flush=True)
    plt.close(fig)


def validate_products(data):
    times = data["track"].time.values
    if not 2 <= len(times) <= 12 or not np.all(np.diff(times) > np.timedelta64(0, "s")):
        raise ValueError("This figure layout requires 2–12 distinct, increasing valid times.")
    for key, ds in data.items():
        if not np.array_equal(times, ds.time.values):
            raise ValueError(
                f"{key}: valid times differ; no implicit temporal matching is performed."
            )
    for key in ("surface", "polar_pressure"):
        require_units(data[key].prmsl, {"Pa"})
    for key in ("temperature", "polar_temperature"):
        temperature_2m(data[key], "t2m")
    temperature_2m(data["surfex"], "SFX.T2M")
    temperature_2m(data["polar_surfex"], "SFX.T2M")
    for key in ("profiles", "polar_profiles"):
        ds = data[key]
        require_units(ds.isobaricInhPa, {"hPa"})
        require_units(ds.t, {"K"})
        require_units(ds.r, {"%"})
        require_units(ds.w, {"Pa s**-1", "Pa s-1", "Pa s^-1"})
        require_units(ds.wz, {"m s**-1", "m s-1", "m s^-1"})
        if not np.all(np.diff(ds.isobaricInhPa.values) < 0):
            raise ValueError("Expected strictly descending pressure levels.")
        if not {150, 700}.issubset(ds.isobaricInhPa.values):
            raise ValueError("Both 150 hPa and 700 hPa are needed for these vertical plots.")
    reference = data["polar_temperature"]
    for key in ("polar_pressure", "polar_profiles", "polar_surfex"):
        verify_shared_target(reference, data[key])
    if not np.isclose(reference.rr.values[0], 0):
        raise ValueError("Expected a stored polar origin at rr = 0.")
    wind_speed(data["surface"], "u10", "v10")
    wind_speed(data["profiles"], "u", "v")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--config", type=Path, help="Default: YAML beside the input directory.")
    parser.add_argument("--output-dir", type=Path, help="Default: INPUT_DIR/plots.")
    parser.add_argument(
        "--dpi", type=int, default=240, help="PNG and raster-layer resolution (default: 240)."
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace only this script's named outputs."
    )
    args = parser.parse_args(argv)
    root = args.input_dir.resolve()
    config_path = args.config or root.with_suffix(".yaml")
    if not config_path.is_file():
        parser.error(f"Configuration not found: {config_path}; supply --config.")
    config_bytes = config_path.read_bytes()
    config = yaml.safe_load(config_bytes)
    prefix = config["run"]["name"]
    if not isinstance(prefix, str) or Path(prefix).name != prefix:
        parser.error("run.name must be a simple product-name prefix.")
    if not 72 <= args.dpi <= 600:
        parser.error("Choose --dpi between 72 and 600.")
    output = (args.output_dir or root / "plots").resolve()
    planned = [output / f"{stem}.{suffix}" for stem in STEMS for suffix in ("png", "pdf")]
    planned.append(output / "plot_manifest.json")
    existing = [path.name for path in planned if path.exists()]
    if existing and not args.overwrite:
        parser.error(
            f"Outputs already exist: {', '.join(existing)}. Use --overwrite to replace them."
        )
    output.mkdir(parents=True, exist_ok=True)
    cartopy.config["cache_dir"] = Path(os.environ.get("TMPDIR", "/tmp/opencode")) / "cartopy-cache"
    cartopy.config["cache_dir"].mkdir(parents=True, exist_ok=True)
    style()
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "script": Path(__file__).name,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "configuration": {
            "name": config_path.name,
            "sha256": hashlib.sha256(config_bytes).hexdigest(),
        },
        "python": sys.version.split()[0],
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "xarray", "netCDF4", "matplotlib", "cartopy", "cmocean", "PyYAML")
        },
        "geographic_layers": (
            "Natural Earth 1:10 million coastline, land, lakes and international borders"
        ),
        "conversions": {
            "sea_level_pressure": "Pa / 100 -> hPa",
            "temperature": "K - 273.15 -> degC",
        },
        "methods": {
            "wind_speed": (
                "hypot(u, v); requires collocated, mass-aligned Earth-relative components"
            ),
            "temperature_difference": (
                "SURFEX SFX.T2M minus atmospheric t2m at exactly equal existing polar targets"
            ),
            "ring_rms": (
                "sqrt(equal-angle mean(delta_T**2)); any missing azimuth makes the ring missing"
            ),
            "selection_rms": (
                "Unweighted shared points at rr > 0; "
                "origin excluded to avoid counting it once per azimuth"
            ),
            "vertical_sampling": (
                "Native pressure-level values; no new vertical interpolation "
                "or conversion of omega to wz"
            ),
            "rendering": (
                "Raster cells/contour displays only; "
                "no field smoothing, gap filling or additional regridding"
            ),
        },
        "limitations": [
            "Exploratory comparisons, not independent validation of the data or tracking.",
            "Tracked storm identity is explicitly unverified in the supplied configuration.",
            "Surface-pressure and terrain masks are unavailable; "
            "pressure sections are restricted to 700–150 hPa.",
            "Shared-target temperature differences combine source sampling/resolution effects; "
            "neither source is truth.",
            "Pointwise RMS and equal-angle ring statistics are not area averages "
            "or conservation estimates.",
            "Only the supplied exact-common times are plotted; no excluded time is reconstructed.",
            "Natural Earth 10m is a map scale, not ten-metre positional accuracy.",
        ],
        "figures": {},
        "sources": [],
        "outputs": [path.name for path in planned],
    }
    with ExitStack() as stack:
        data = {}
        for key, token in PRODUCTS.items():
            path = root / f"{prefix}.{token}.nc"
            if not path.is_file():
                parser.error(f"Required product is missing: {path.name}")
            ds = stack.enter_context(xr.open_dataset(path, engine="netcdf4", cache=False))
            data[key] = ds
            manifest["sources"].append(
                {
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "frameit_version": ds.attrs.get("frameit_version"),
                    "history": ds.attrs.get("history"),
                }
            )
        validate_products(data)
        manifest["valid_times_utc"] = np.datetime_as_string(
            data["track"].time.values, unit="s"
        ).tolist()
        manifest["source_time_exclusions_count"] = int(
            data["track"].attrs.get("time_alignment_skipped_count", 0)
        )
        manifest["source_time_exclusions_convention"] = data["track"].attrs.get(
            "time_alignment_skipped_count_convention"
        )
        manifest["common_polar_target_id"] = data["polar_temperature"].attrs[
            "common_polar_target_id"
        ]
        manifest["run_status_present"] = (root / "run-status.yaml").is_file()
        manifest["run_provenance_present"] = (root / "run-provenance.yaml").is_file()
        if not manifest["run_status_present"]:
            manifest["limitations"].append(
                "No run-status.yaml supplied; overall processing completion is not established."
            )
        for stem, make in zip(
            STEMS,
            (figure_track, figure_surface, figure_temperature, figure_vertical, figure_section),
            strict=True,
        ):
            fig, details = make(data)
            save_figure(fig, output, stem, args.dpi)
            manifest["figures"][stem] = details
    temporary = output / ".plot_manifest.json.partial"
    temporary.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, output / "plot_manifest.json")
    print(f"Finished: {len(STEMS)} figures, PNG + PDF, and plot_manifest.json.", flush=True)


if __name__ == "__main__":
    main()
