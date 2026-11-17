"""Small checks for standalone downstream illustration scripts, not diagnostics."""

from pathlib import Path
import subprocess
import sys

import netCDF4
import numpy as np
import xarray as xr


def test_batsirai_plot_cli_reads_time_dependent_cartesian_coordinates(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    times = np.array(["2022-02-01T00:10", "2022-02-01T00:20"], dtype="datetime64[ns]")
    lon, lat = np.meshgrid(np.linspace(59.9, 60.1, 5), np.linspace(-20.1, -19.9, 5))
    wind = np.stack([np.tile(np.linspace(-20., 20., 5), (5, 1)) + t for t in (0., 2.)])
    wind[:, [0, -1], :] = 1e20
    wind[:, :, [0, -1]] = 1e20
    source = xr.Dataset({"UM10": (("time", "y", "x"), wind, {"units": "m s-1"})},
                        coords={"time": times, "latitude": (("y", "x"), lat),
                                "longitude": (("y", "x"), lon),
                                "y": ("y", np.arange(5), {"c_grid_dynamic_range": "2:4"}),
                                "x": ("x", np.arange(5), {"c_grid_dynamic_range": "2:4"})})
    for i in range(2):
        source.isel(time=[i]).to_netcdf(data / f"{i}dg.nc", engine="netcdf4")
    before = {p: p.read_bytes() for p in data.iterdir()}
    for name in ("batsirai-fixed", "batsirai-moving"):
        products = tmp_path / name / "products"
        products.mkdir(parents=True)
        track = xr.Dataset({key: ("time", values, {"units": units}) for key, values, units in (
            ("latitude", [-20., -20.], "degrees_north"),
            ("longitude", [60., 60.], "degrees_east"))},
                           coords={"time": times})
        track.to_netcdf(products / f"{name}.track.nc", engine="netcdf4")
    cart = source.isel(y=slice(1, 4), x=slice(1, 4)).assign_coords(
        latitude=(("time", "y", "x"), np.broadcast_to(lat[1:4, 1:4], (2, 3, 3))),
        longitude=(("time", "y", "x"), np.broadcast_to(lon[1:4, 1:4], (2, 3, 3))))
    products = tmp_path / "batsirai-fixed/products"
    cart = cart.assign_coords(y=np.arange(3), x=np.arange(3))
    for name in ("batsirai-fixed", "batsirai-moving"):
        cart.to_netcdf(tmp_path / name / "products" / f"{name}.atmosphere.model_grid.nc",
                       engine="netcdf4")
    polar = xr.Dataset({"UM10": (("time", "radius", "azimuth"),
                               np.broadcast_to(wind[:, 2:3, 2:3], (2, 3, 8)), {"units": "m s-1"})},
                       coords={"time": times, "radius": [0., 2., 4.],
                               "azimuth": np.arange(8) * np.pi / 4})
    polar.to_netcdf(products / "batsirai-fixed.atmosphere.polar.nc", engine="netcdf4")
    script = Path(__file__).parents[1] / "example/plots/batsirai_wind.py"
    args = [sys.executable, str(script), str(data), str(tmp_path / "batsirai-fixed"),
            str(tmp_path / "batsirai-moving"), str(tmp_path / "figures")]
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    figures = list((tmp_path / "figures").glob("*.png"))
    assert len(figures) == 4 and all(p.read_bytes().startswith(b"\x89PNG") for p in figures)
    assert {p: p.read_bytes() for p in data.iterdir()} == before
    existing = {p: p.read_bytes() for p in figures}
    assert subprocess.run(args, capture_output=True, timeout=60).returncode != 0
    assert {p: p.read_bytes() for p in figures} == existing
    args[-1] = str(data / "figures")
    assert subprocess.run(args, capture_output=True, timeout=60).returncode != 0
    assert not (data / "figures").exists()
    with netCDF4.Dataset(data / '1dg.nc', 'r+') as ds:
        ds['x'].c_grid_dynamic_range = '1:5'
    args[-1] = str(tmp_path / 'unverified-halo')
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0 and 'halo' in result.stderr
    assert not (tmp_path / 'unverified-halo').exists()


def test_first_run_plot_cli_reads_only_the_selected_time(tmp_path):
    from frameit.testing.documentation_example import create_first_run_input

    source = create_first_run_input(tmp_path / "input.nc")
    product = tmp_path / "product.nc"
    with xr.open_dataset(source, engine="netcdf4") as ds:
        crop = ds.isel(latitude=slice(6, 11), longitude=slice(6, 11)).rename(
            {"valid_time": "time"})
        lat, lon = np.meshgrid(crop.latitude, crop.longitude, indexing="ij")
        crop = crop.rename({"latitude": "y", "longitude": "x"}).assign_coords(
            y=np.arange(5), x=np.arange(5),
            latitude=(("time", "y", "x"), np.broadcast_to(lat, (2, 5, 5))),
            longitude=(("time", "y", "x"), np.broadcast_to(lon, (2, 5, 5))))
        crop.to_netcdf(product, engine="netcdf4")
    before = source.read_bytes(), product.read_bytes()
    script = Path(__file__).parents[1] / "example/plots/first_run.py"
    figure = tmp_path / "first-run.png"
    args = [sys.executable, str(script), str(source), str(product), str(figure)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert figure.read_bytes().startswith(b"\x89PNG")
    assert (source.read_bytes(), product.read_bytes()) == before
    assert subprocess.run(args, capture_output=True, timeout=60).returncode != 0
    figure_before = figure.read_bytes()
    args[-1] = str(figure.with_suffix(""))
    assert subprocess.run(args, capture_output=True, timeout=60).returncode != 0
    assert figure.read_bytes() == figure_before
    args[-1] = str(source)
    assert subprocess.run(args, capture_output=True, timeout=60).returncode != 0
    assert (source.read_bytes(), product.read_bytes()) == before
