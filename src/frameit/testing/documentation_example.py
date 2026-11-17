"""Deterministic instructional NetCDF, not producer data or a physical simulation."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr

from frameit.utils.atomic import atomic_output


def create_first_run_input(path: Path) -> Path:
    """Create the two-time scalar example without replacing an existing input."""
    path = Path(path)
    t, j, i = np.indices((2, 17, 17))
    values = (1000*t + 10*(j-8) + (i-8)).astype(float)
    values[:, 7, 9] = np.nan
    data = xr.Dataset({
        "instructional_scalar": (("valid_time", "latitude", "longitude"), values, {
            "units": "1", "long_name": "dimensionless instructional scalar",
            "comment": "1000*t + 10*(j-8) + (i-8); zero-based indices; missing at j=7,i=9",
        }),
    }, coords={
        "valid_time": ("valid_time", np.array(
            ["2000-01-01T00:00", "2000-01-01T01:00"], dtype="datetime64[ns]"),
            {"standard_name": "time", "axis": "T"}),
        "latitude": ("latitude", -20. + .01 * np.arange(-8, 9),
                     {"units": "degrees_north", "standard_name": "latitude"}),
        "longitude": ("longitude", 60. + .01 * np.arange(-8, 9),
                      {"units": "degrees_east", "standard_name": "longitude"}),
    }, attrs={
        "title": "FrameIt instructional scalar example",
        "source": "Synthetic structured-adapter input; not an AROME producer file",
        "comment": "No physical interpretation or real-producer qualification; zero is valid, NaN is missing.",
    })
    with atomic_output(path, overwrite=False) as temporary:
        data.to_netcdf(temporary, engine="netcdf4", encoding={
            "valid_time": {"units": "hours since 2000-01-01 00:00:00", "calendar": "proleptic_gregorian"}})
    return path


def create_tutorial_inputs(directory: Path, *, translating=False, missing=False) -> dict[str, Path]:
    """Write a small declared event, not a balanced simulation or producer fixture."""
    from pyproj import Geod

    from frameit.testing.analytic_vortices import AnalyticVortex

    directory = Path(directory)
    paths = {name: directory / f"{name}.nc" for name in ("atmosphere", "ocean", "track")}
    for path in paths.values():
        if path.exists():
            raise FileExistsError(path)
    times = np.array(["2000-01-01T00", "2000-01-01T01", "2000-01-01T02"],
                     dtype="datetime64[ns]")
    centres = 60. + (.1 * np.arange(3) if translating else np.zeros(3))
    provenance = {
        "source": "Synthetic instructional inputs; not producer data or a physical simulation",
        "event": "prescribed Gaussian vortex; no dynamical balance or motion subtraction",
        "V_max_m_s": 40., "R_m": 40000., "p_infinity_Pa": 101000., "delta_p_Pa": 5000.,
        "centre_longitude_step_degrees": .1 if translating else 0.,
    }
    longitude, latitude = 60. + .05 * np.arange(-12, 13), -20. + .05 * np.arange(-12, 13)
    lon, lat = np.meshgrid(longitude, latitude)
    u, v, pressure = [], [], []
    geod = Geod(ellps="WGS84")
    for centre in centres:
        model = AnalyticVortex(longitude=float(centre), latitude=-20., tangential_max_ms=40.)
        fields = model.evaluate(lon, lat)
        _, _, radius = geod.inv(np.full(lon.shape, centre), np.full(lat.shape, -20.), lon, lat)
        u.append(fields["u"])
        v.append(fields["v"])
        pressure.append(101000. - 5000. * np.exp(-(radius / 40000.)**2))
    dims = ("time", "latitude", "longitude")
    wind = {"units": "m s-1", "wind_reference_frame": "earth", "kind": "continuous"}
    air = xr.Dataset({
        "u": (dims, np.asarray(u), {**wind, "standard_name": "eastward_wind"}),
        "v": (dims, np.asarray(v), {**wind, "standard_name": "northward_wind"}),
        "pressure": (dims, np.asarray(pressure), {
            "units": "Pa", "standard_name": "air_pressure_at_mean_sea_level",
            "kind": "continuous"}),
        "temperature": (("time", "height", "latitude", "longitude"),
                        np.broadcast_to((300. - .006 * np.array([10., 1000., 3000.]))[
                            None, :, None, None], (3, 3, 25, 25)),
                        {"units": "K", "kind": "continuous", "formula": "300 K - (0.006 K/m) z"}),
        "interface_w": (("time", "interface_height", "latitude", "longitude"),
                        np.broadcast_to(np.array([0., .5, 2., 4.])[None, :, None, None],
                                        (3, 4, 25, 25)),
                        {"units": "m s-1", "kind": "continuous", "formula": "(0.001 s-1) z"}),
    }, coords={
        "time": times,
        "latitude": ("latitude", latitude, {"units": "degrees_north", "standard_name": "latitude"}),
        "longitude": ("longitude", longitude, {
            "units": "degrees_east", "standard_name": "longitude"}),
        "height": ("height", [10., 1000., 3000.], {"units": "m", "axis": "Z", "positive": "up"}),
        "interface_height": ("interface_height", [0., 500., 2000., 4000.],
                             {"units": "m", "axis": "Z", "positive": "up"}),
    }, attrs=provenance)
    ocean_lon, ocean_lat = np.meshgrid(60. + .1 * np.arange(-6, 7), -20. + .1 * np.arange(-6, 7))
    depths = np.array([-30., -10., 0.])
    temperatures = []
    for centre in centres[[0, 2]]:
        _, _, radius = geod.inv(
            np.full(ocean_lon.shape, centre), np.full(ocean_lat.shape, -20.), ocean_lon, ocean_lat)
        z = depths[:, None, None]
        temperatures.append(300. + .01 * z - 2. * np.exp(-(radius / 40000.)**2) * np.exp(z / 20.))
    water = xr.Dataset({
        "temp": (("time", "s_rho", "eta_rho", "xi_rho"), np.asarray(temperatures), {
            "units": "K", "kind": "continuous", "temporal_kind": "instantaneous",
            "long_name": "instructional ocean temperature response",
            "formula": "300 K + (0.01 K/m) z - (2 K) exp(-(r/40 km)^2) exp(z/20 m)",
            "ancillary_variables": "mask_rho"}),
        "h": (("eta_rho", "xi_rho"), np.full((13, 13), 40.), {"units": "m"}),
        "zeta": (("time", "eta_rho", "xi_rho"), np.zeros((2, 13, 13)), {"units": "m"}),
        "Cs_rho": ("s_rho", depths / 40., {"units": "1"}),
        "hc": xr.DataArray(5., attrs={"units": "m"}),
        "Vtransform": xr.DataArray(2),
        "mask_rho": (("eta_rho", "xi_rho"), np.ones((13, 13), dtype="uint8"), {
            "units": "1", "option_0": "land", "option_1": "water"}),
    }, coords={
        "time": times[[0, 2]], "eta_rho": np.arange(13), "xi_rho": np.arange(13),
        "s_rho": ("s_rho", depths / 40., {
            "units": "1", "axis": "Z", "positive": "up", "Vtransform": "2",
            "standard_name": "ocean_s_coordinate_g2",
            "formula_terms": "s: s_rho C: Cs_rho eta: zeta depth: h depth_c: hc"}),
        "depth": ("s_rho", depths, {"units": "m", "long_name": "height relative to sea surface"}),
        "lat_rho": (("eta_rho", "xi_rho"), ocean_lat, {
            "units": "degrees_north", "standard_name": "latitude"}),
        "lon_rho": (("eta_rho", "xi_rho"), ocean_lon, {
            "units": "degrees_east", "standard_name": "longitude"}),
    }, attrs={**provenance, "type": "CROCO history file",
              "Vtransform": "2", "CPP-options": "MASKING"})
    if missing:
        for name in ("u", "v"):
            air[name][:, 10, 11] = np.nan
        air["surface_type"] = (("latitude", "longitude"),
                               np.broadcast_to((np.arange(25) >= 12).astype("uint8"), (25, 25)),
                               {"units": "1", "kind": "categorical", "flag_values": [0, 1],
                                "flag_meanings": "water land"})
        water.mask_rho[0, :] = 0
        water["temp"] = water.temp.where(water.mask_rho == 1)
    track = xr.Dataset(coords={
        "time": times,
        "latitude": ("time", [-20.] * 3, {"units": "degrees_north", "standard_name": "latitude"}),
        "longitude": ("time", centres, {"units": "degrees_east", "standard_name": "longitude"}),
    }, attrs=provenance)
    for name, scene in (("atmosphere", air), ("ocean", water), ("track", track)):
        scene.time.attrs.update(standard_name="time", axis="T")
        with atomic_output(paths[name], overwrite=False) as temporary:
            scene.to_netcdf(temporary, engine="netcdf4")
    return paths


def create_task_fixtures(directory: Path) -> dict[str, Path]:
    """Generate every task-guide input locally, in a new directory only."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    paths = {"scalar": create_first_run_input(directory / "first-run.nc")}
    for name, folder, options in (
        ("stationary", "stationary", {}),
        ("moving", "data", {"translating": True}),
        ("missing", "missing-data", {"missing": True}),
    ):
        paths.update({f"{name}.{field}": path for field, path in
                      create_tutorial_inputs(directory / folder, **options).items()})
    with xr.open_dataset(paths["stationary.atmosphere"]) as source:
        air = source.load()
    interfaces = air[["temperature", "interface_w"]].rename({
        "height": "level", "interface_height": "level_w",
        "temperature": "THT", "interface_w": "WT",
    }).rename_dims({"latitude": "nj", "longitude": "ni"})
    interfaces = interfaces.assign_coords(
        ni=("ni", 5000. * np.arange(25), {"units": "m"}),
        nj=("nj", 5000. * np.arange(25), {"units": "m"}),
    )
    interfaces.WT.attrs["standard_name"] = "upward_air_velocity"
    paths["interfaces"] = directory / "interfaces.nc"
    with atomic_output(paths["interfaces"], overwrite=False) as temporary:
        interfaces.to_netcdf(temporary, engine="netcdf4")
    pressure = air[["pressure", "temperature"]].rename({
        "pressure": "prmsl", "temperature": "height_temperature"})
    levels = np.array([85000., 70000., 50000.])
    t, _, j, i = np.indices((3, 3, 25, 25))
    pressure["temperature"] = (
        ("time", "isobaric", "latitude", "longitude"),
        270. + .0002 * levels[None, :, None, None] + t + .1 * (j - 12) + .1 * (i - 12),
        {"units": "K", "kind": "continuous",
         "formula": "270 K + (0.0002 K/Pa) p + (1 K) t + (0.1 K) (j-12+i-12)"},
    )
    pressure = pressure.assign_coords(
        isobaric=("isobaric", levels, {"units": "Pa", "axis": "Z", "positive": "down",
                                      "standard_name": "air_pressure"}))
    paths["pressure"] = directory / "pressure.nc"
    with atomic_output(paths["pressure"], overwrite=False) as temporary:
        pressure.to_netcdf(temporary, engine="netcdf4")
    from pyproj import Geod

    with xr.open_dataset(paths["moving.atmosphere"]) as source:
        coupled_air = source.load()
    anomaly = (101000. - coupled_air.pressure) / 5000.
    coupled_air["temperature"] = (
        coupled_air.temperature + 2. * anomaly * np.exp(-coupled_air.height / 1000.)
    ).assign_attrs(
        units="K", kind="continuous",
        formula="300 K - (0.006 K/m) z + (2 K) exp(-(r/40 km)^2) exp(-z/1000 m)")
    for name in ("u", "v"):
        coupled_air[name].attrs["sampling_height_m"] = 10.
    with xr.open_dataset(paths["moving.ocean"]) as source:
        coupled_ocean = source.load().drop_dims("time")
    coupled_ocean = coupled_ocean.assign_coords(time=coupled_air.time)
    lon, lat = coupled_ocean.lon_rho.values, coupled_ocean.lat_rho.values
    radii = []
    geod = Geod(ellps="WGS84")
    with xr.open_dataset(paths["moving.track"]) as track:
        for x, y in zip(track.longitude.values, track.latitude.values, strict=True):
            radii.append(geod.inv(np.full(lon.shape, x), np.full(lat.shape, y), lon, lat)[2])
    wake = np.maximum.accumulate(np.exp(-(np.asarray(radii) / 15000.)**2), axis=0)
    z = coupled_ocean.depth.values[None, :, None, None]
    coupled_ocean["temp"] = (
        ("time", "s_rho", "eta_rho", "xi_rho"),
        300. + .01 * z - 2. * wake[:, None] * np.exp(z / 20.),
        {"units": "K", "kind": "continuous", "temporal_kind": "instantaneous",
         "long_name": "prescribed ocean temperature with a persistent cold trail",
         "formula": "300 K + (0.01 K/m) z - (2 K) max[k<=t](exp(-(r_k/15 km)^2)) exp(z/20 m)",
         "ancillary_variables": "mask_rho"})
    coupled_ocean["zeta"] = (
        ("time", "eta_rho", "xi_rho"), np.zeros((3, *lon.shape)), {"units": "m"})
    for name, scene in (("atmosphere", coupled_air), ("ocean", coupled_ocean)):
        scene.attrs["event"] = (
            "prescribed translating temperature/winds and persistent cold trail; "
            "no coupled dynamics")
        paths[f"coupled.{name}"] = directory / f"coupled-{name}.nc"
        with atomic_output(paths[f"coupled.{name}"], overwrite=False) as temporary:
            scene.to_netcdf(temporary, engine="netcdf4")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New instructional NetCDF path or tutorial directory (no overwrite)")
    parser.add_argument("--tutorial", choices=("stationary", "translating", "missing"),
                        help="Create a labelled atmospheric/ocean tutorial directory instead")
    args = parser.parse_args()
    if args.tutorial:
        for path in create_tutorial_inputs(
                args.output, translating=args.tutorial == "translating",
                missing=args.tutorial == "missing").values():
            print(f"Created instructional input: {path}")
    else:
        print(f"Created instructional input: {create_first_run_input(args.output)}")


if __name__ == "__main__":
    main()
