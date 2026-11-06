"""Small checks for standalone downstream illustration scripts, not diagnostics."""

import importlib.util
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr


@pytest.fixture(scope="module")
def illustration():
    path = Path(__file__).parents[4] / "example/plots/batsirai_reflectivity.py"
    spec = importlib.util.spec_from_file_location("batsirai_illustration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rain_only_estimate_keeps_missing_distinct_from_no_rain(illustration):
    first = np.array([0., 1., np.nan, 0.])
    second = np.array([0., 2., 3., 10.])
    result = illustration.rain_only_dbz(first, second, 1.)
    assert np.isneginf(result[0])
    np.testing.assert_allclose(result[[1, 3]], [23.010299956639813, 39.01029995663981],
                               rtol=0, atol=1e-12)
    assert np.isnan(result[2])
    assert np.isnan(first[2]) and first[1] == 1. and second[1] == 2.


@pytest.mark.parametrize("hours", [0., -1., np.nan, np.inf])
def test_rain_only_estimate_rejects_invalid_time_support(illustration, hours):
    with pytest.raises(ValueError, match="interval"):
        illustration.rain_only_dbz(np.array([0.]), np.array([1.]), hours)


def test_rain_only_estimate_rejects_accumulation_reset(illustration):
    with pytest.raises(ValueError, match="reset|decrease"):
        illustration.rain_only_dbz(np.array([2.]), np.array([1.]), 1 / 6)


def test_batsirai_plot_cli_reads_time_dependent_cartesian_coordinates(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    times = np.array(["2022-02-01T00:10", "2022-02-01T00:20"], dtype="datetime64[ns]")
    lon, lat = np.meshgrid(np.linspace(59.9, 60.1, 5), np.linspace(-20.1, -19.9, 5))
    rain = np.stack([np.zeros((5, 5)), np.ones((5, 5))])
    source = xr.Dataset({"ACPRR": (("time", "y", "x"), rain, {"units": "mm"})},
                        coords={"time": times, "latitude": (("y", "x"), lat),
                                "longitude": (("y", "x"), lon)})
    for i in range(2):
        source.isel(time=[i]).to_netcdf(data / f"{i}dg.nc", engine="netcdf4")
    before = {p: p.read_bytes() for p in data.iterdir()}
    for name in ("batsirai-fixed", "batsirai-moving"):
        products = tmp_path / name / "products"
        products.mkdir(parents=True)
        track = xr.Dataset({key: ("time", values) for key, values in {
            "lat": [-20., -20.], "lon": [60., 60.], "ix_min": [1, 1],
            "ix_max": [3, 3], "iy_min": [1, 1], "iy_max": [3, 3]}.items()},
                           coords={"time": times})
        track.to_netcdf(products / f"{name}.track.nc", engine="netcdf4")
    cart = source.isel(y=slice(1, 4), x=slice(1, 4)).assign_coords(
        latitude=(("time", "y", "x"), np.broadcast_to(lat[1:4, 1:4], (2, 3, 3))),
        longitude=(("time", "y", "x"), np.broadcast_to(lon[1:4, 1:4], (2, 3, 3))))
    products = tmp_path / "batsirai-fixed/products"
    cart.to_netcdf(products / "batsirai-fixed.cart.surface.nc", engine="netcdf4")
    polar = xr.Dataset({"ACPRR": (("time", "rr", "theta"),
                                np.broadcast_to(rain[:, :1, :1], (2, 3, 8)), {"units": "mm"})},
                       coords={"time": times, "rr": [0., 2., 4.],
                               "theta": np.arange(8) * np.pi / 4})
    polar.to_netcdf(products / "batsirai-fixed.polar.surface.nc", engine="netcdf4")
    script = Path(__file__).parents[4] / "example/plots/batsirai_reflectivity.py"
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


def test_first_run_plot_cli_reads_only_the_selected_time(tmp_path):
    from frameit.testing.documentation_example import create_first_run_input

    source = create_first_run_input(tmp_path / "input.nc")
    product = tmp_path / "product.nc"
    with xr.open_dataset(source, engine="netcdf4") as ds:
        crop = ds.isel(latitude=slice(6, 11), longitude=slice(6, 11)).rename(
            {"valid_time": "time"})
        lat, lon = np.meshgrid(crop.latitude, crop.longitude, indexing="ij")
        crop = crop.rename({"latitude": "y_box", "longitude": "x_box"}).assign_coords(
            latitude=(("time", "y_box", "x_box"), np.broadcast_to(lat, (2, 5, 5))),
            longitude=(("time", "y_box", "x_box"), np.broadcast_to(lon, (2, 5, 5))))
        crop.to_netcdf(product, engine="netcdf4")
    before = source.read_bytes(), product.read_bytes()
    script = Path(__file__).parents[4] / "example/plots/first_run.py"
    figure = tmp_path / "first-run.png"
    args = [sys.executable, str(script), str(source), str(product), str(figure)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert figure.read_bytes().startswith(b"\x89PNG")
    assert (source.read_bytes(), product.read_bytes()) == before
    assert subprocess.run(args, capture_output=True, timeout=60).returncode != 0
    args[-1] = str(source)
    assert subprocess.run(args, capture_output=True, timeout=60).returncode != 0
    assert (source.read_bytes(), product.read_bytes()) == before
