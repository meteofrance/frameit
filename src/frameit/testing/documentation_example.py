"""Deterministic instructional NetCDF, not producer data or a physical simulation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from frameit.utils.atomic import atomic_output
from frameit.utils.diagnostics import FrameItArgumentParser, tag_error


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
    try:
        with atomic_output(path, overwrite=False) as temporary:
            data.to_netcdf(temporary, engine="netcdf4", encoding={
                "valid_time": {"units": "hours since 2000-01-01 00:00:00",
                               "calendar": "proleptic_gregorian"}})
    except OSError as exc:
        raise tag_error(exc, "E1901")
    return path


def create_tutorial_inputs(directory: Path, *, translating=False, missing=False) -> dict[str, Path]:
    """Write a small declared event, not a balanced simulation or producer fixture."""
    from pyproj import Geod

    from frameit.testing.analytic_vortices import AnalyticVortex

    directory = Path(directory)
    paths = {name: directory / f"{name}.nc" for name in ("atmosphere", "ocean", "track")}
    for path in paths.values():
        if path.exists():
            raise tag_error(FileExistsError(path), "E1901")
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


def _create_forecast_archive(directory: Path) -> dict[str, Path]:
    day = np.datetime64("2000-01-01", "ns")
    distance = .01 * np.arange(-3, 4)
    paths = {}
    for name, hour, lead_hours, pressure in (
        ("z-earlier", 0, 1, 100100.),
        ("a-later", 0, 2, 100200.),
        ("b-other-cycle", 1, 1, 101200.),
    ):
        cycle = day + np.timedelta64(hour, "h")
        lead = np.timedelta64(lead_hours, "h")
        data = xr.Dataset({
            "prmsl": (("valid_time", "latitude", "longitude"), np.full((1, 7, 7), pressure),
                      {"units": "Pa", "cell_methods": "valid_time: point",
                       "standard_name": "air_pressure_at_mean_sea_level"}),
        }, coords={
            "valid_time": ("valid_time", [cycle + lead], {"standard_name": "time"}),
            "time": ((), cycle, {"standard_name": "forecast_reference_time"}),
            "step": ("valid_time", [lead], {"standard_name": "forecast_period"}),
            "latitude": ("latitude", -20. + distance, {"units": "degrees_north"}),
            "longitude": ("longitude", 60. + distance, {"units": "degrees_east"}),
        }, attrs={"source": "Synthetic instructional forecast archive; not producer data"})
        paths[f"forecast-archive.{name}"] = directory / f"{name}.nc"
        clock = {"units": "hours since 2000-01-01", "calendar": "proleptic_gregorian"}
        with atomic_output(paths[f"forecast-archive.{name}"], overwrite=False) as temporary:
            data.to_netcdf(temporary, engine="netcdf4", encoding={"time": clock, "valid_time": clock})
    return paths


def _create_coupled_clocks(directory: Path) -> dict[str, Path]:
    times = np.array(["2000-01-01T06", "2000-01-01T07", "2000-01-01T08"], dtype="datetime64[ns]")
    attrs = {"source": "Synthetic instructional clocks; not a coupled simulation"}
    t, j, i = np.indices((3, 9, 9))
    air = xr.Dataset({
        "prmsl": (("time", "latitude", "longitude"), 100000. + 100*t + 10*j + i,
                  {"units": "Pa", "cell_methods": "time: point",
                   "standard_name": "air_pressure_at_mean_sea_level"}),
    }, coords={
        "time": ("time", times, {"standard_name": "time"}),
        "latitude": ("latitude", -20. + .05*np.arange(-4, 5), {"units": "degrees_north"}),
        "longitude": ("longitude", 60. + .05*np.arange(-4, 5), {"units": "degrees_east"}),
    }, attrs=attrs)
    ends = times[[0, 2]]
    bounds = ends[:, None] + np.array([-1, 0], dtype="timedelta64[h]")
    offset = .08*np.arange(-3, 4)
    lon, lat = np.meshgrid(60. + offset, -20. + offset)
    t, j, i = np.indices((2, 7, 7))
    ocean = xr.Dataset({
        "votemper": (("time_counter", "deptht", "y", "x"), (290. + t + .1*j + .01*i)[:, None],
                     {"units": "K", "cell_methods": "time: mean",
                      "standard_name": "sea_water_potential_temperature"}),
        "time_bounds": (("time_counter", "bounds"), bounds),
    }, coords={
        "time_counter": ("time_counter", ends - np.timedelta64(30, "m"),
                         {"standard_name": "time", "bounds": "time_bounds"}),
        "deptht": ("deptht", [5.], {"units": "m", "positive": "down"}),
        "nav_lat": (("y", "x"), lat, {"units": "degrees_north"}),
        "nav_lon": (("y", "x"), lon, {"units": "degrees_east"}),
        "y": np.arange(7),
        "x": np.arange(7),
    }, attrs=attrs)
    track = xr.Dataset(coords={
        "time": ("time", times, {"standard_name": "time"}),
        "latitude": ("time", [-20.] * 3, {"units": "degrees_north"}),
        "longitude": ("time", [60., 60.05, 60.1], {"units": "degrees_east"}),
    }, attrs=attrs)
    clock = {"units": "minutes since 2000-01-01", "calendar": "proleptic_gregorian"}
    paths = {}
    for name, scene, times_to_encode in (
        ("atmosphere", air, ("time",)),
        ("nemo-t", ocean, ("time_counter", "time_bounds")),
        ("track", track, ("time",)),
    ):
        path = directory / f"{name}.nc"
        paths[f"coupled-clocks.{name}"] = path
        with atomic_output(path, overwrite=False) as temporary:
            scene.to_netcdf(temporary, engine="netcdf4",
                            encoding={coord: clock for coord in times_to_encode})
    return paths


def _create_staggered_winds(path: Path) -> Path:
    mass = 1000.*np.arange(-4., 5.)
    faces = 1000.*np.arange(-4.5, 5.)
    data = xr.Dataset({
        "UT": (("time", "level", "nj_u", "ni_u"),
               np.broadcast_to(10. + faces/1000., (1, 3, 9, 10)),
               {"units": "m s-1", "standard_name": "x_wind", "grid": 2}),
        "VT": (("time", "level", "nj_v", "ni_v"), np.zeros((1, 3, 10, 9)),
               {"units": "m s-1", "standard_name": "y_wind", "grid": 3}),
    }, coords={
        "time": [np.datetime64("2000-01-01T00", "ns")],
        "level": ("level", [-5., 5., 15.], {"units": "m", "c_grid_dynamic_range": "2:3"}),
        "angle": ((), np.pi/2, {"units": "rad"}),
    }, attrs={"source": "Synthetic instructional wind pair; not producer data"})
    for suffix, x, y in (("", mass, mass), ("_u", faces, mass), ("_v", mass, faces)):
        xi, yj = f"ni{suffix}", f"nj{suffix}"
        xx, yy = np.meshgrid(x, y)
        # The synthetic grid's x direction is north; its y direction is west.
        data = data.assign_coords({
            xi: (xi, x, {"units": "m"}),
            yj: (yj, y, {"units": "m"}),
            f"latitude{suffix}": ((yj, xi), -20. + xx/111000., {"units": "degrees_north"}),
            f"longitude{suffix}": ((yj, xi), 60. - yy/(111000.*np.cos(np.deg2rad(20))),
                                  {"units": "degrees_east"}),
        })
    with atomic_output(path, overwrite=False) as temporary:
        data.to_netcdf(temporary, engine="netcdf4")
    return path


def create_task_fixtures(directory: Path) -> dict[str, Path]:
    """Generate every task-guide input locally, in a new directory only."""
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise tag_error(exc, "E1901")
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
    calculated_air = coupled_air[["pressure", "u", "v"]].rename(
        {"pressure": "prmsl", "u": "u10", "v": "v10"})
    paths["calculated-track.atmosphere"] = directory / "calculated-track/atmosphere.nc"
    with atomic_output(paths["calculated-track.atmosphere"], overwrite=False) as temporary:
        calculated_air.to_netcdf(temporary, engine="netcdf4")
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
    paths.update(_create_forecast_archive(directory / "forecast-archive"))
    paths.update(_create_coupled_clocks(directory / "coupled-clocks"))
    paths["staggered-winds.mesonh"] = _create_staggered_winds(directory / "staggered-winds/mesonh.nc")
    return paths


def main() -> None:
    parser = FrameItArgumentParser(description=__doc__)
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
