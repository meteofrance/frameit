"""Run the downloadable tutorials and plotting scripts on generated inputs only."""

import os
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

ROOT = Path(__file__).resolve().parent.parent
CASES = [
    ("fixed-region", "fixed_region", "model_grid"),
    ("field-selection", "field_selection", "model_grid"),
    ("moving-region", "moving_region", "track"),
    ("scalars-and-vectors", "scalars_and_vectors", "model_grid"),
    ("polar-sampling", "polar_sampling", "polar"),
    ("coupled-inputs", "coupled_inputs", "model_grid"),
    ("storage-and-resources", "storage_and_resources", "model_grid"),
    ("analytic-moving", "analytical_event", "polar"),
]


def test_generated_fixture_plot_uses_only_the_local_analytical_dataset(tmp_path):
    from frameit.testing.documentation_example import create_task_fixtures

    paths = create_task_fixtures(tmp_path / "tutorial-data")
    product = paths["stationary.atmosphere"]
    before = product.read_bytes()
    figure = tmp_path / "fixtures.svg"
    run = subprocess.run(
        [sys.executable, str(ROOT / "example/plots/plot_generate_fixtures.py"),
         str(product), str(figure)], capture_output=True, text=True, timeout=30,
        env={**os.environ, "MPLBACKEND": "Agg"})
    assert run.returncode == 0, run.stdout + run.stderr
    assert figure.stat().st_size > 1000
    assert product.read_bytes() == before
    existing = tmp_path / "existing.png"
    existing.write_bytes(b"unrelated figure")
    refused = subprocess.run(
        [sys.executable, str(ROOT / "example/plots/plot_generate_fixtures.py"),
         str(product), str(existing.with_suffix(""))], capture_output=True, text=True, timeout=30,
        env={**os.environ, "MPLBACKEND": "Agg"})
    assert refused.returncode != 0
    assert existing.read_bytes() == b"unrelated figure"


@pytest.mark.parametrize("name,script,role", CASES)
@pytest.mark.parametrize("interface", ["api", "cli"])
def test_downloadable_task_executes_and_plots_without_supplied_data(
    tmp_path, name, script, role, interface,
):
    from frameit.core.execution import execute_simulation
    from frameit.core.settings_class import SimulationConfig
    from frameit.testing.documentation_example import create_task_fixtures

    work = tmp_path / "tutorial-data"
    create_task_fixtures(work)
    config = work / f"{name}.yaml"
    shutil.copyfile(ROOT / "example/tutorials" / config.name, config)
    if interface == "api":
        result = execute_simulation(SimulationConfig.from_yaml_with_model_preset(config))
        assert result.ok
    else:
        completed = subprocess.run(
            [sys.executable, "-m", "frameit", "run", str(config)], cwd=work,
            capture_output=True, text=True, timeout=60)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    import yaml

    directory = work / "results" / name
    status = yaml.safe_load((directory / "run-status.yaml").read_text())
    assert status["state"] == "completed"
    product = next(p for p in status["products"]
                   if p["role"] == role and (role == "track" or p["source"] == "atmosphere"))
    path = directory / product["path"]
    with (xr.open_zarr(path, consolidated=False) if path.suffix == ".zarr"
          else xr.open_dataset(path)) as data:
        if name == "fixed-region":
            assert data.instructional_scalar.shape == (2, 5, 5)
            assert data.instructional_scalar.isel(time=0, y=2, x=2) == 0
        elif name == "field-selection":
            np.testing.assert_array_equal(data.pressure, [850., 700.])
            assert data.pressure.attrs["units"] == "hPa"
        elif name == "moving-region":
            np.testing.assert_allclose(data.longitude, [60., 60.1, 60.2])
        elif name == "scalars-and-vectors":
            np.testing.assert_allclose(data.speed, np.hypot(data.u, data.v), rtol=0, atol=1e-12)
        elif name == "polar-sampling":
            assert data.u.sizes["azimuth"] == 16
            assert data.u.attrs["units"] == "m s-1"
        elif name == "coupled-inputs":
            assert data.sizes["time"] == 3
            np.testing.assert_array_equal(data.height, [10.])
            assert {"height.temperature", "u", "v"} <= data.data_vars.keys()
        elif name == "storage-and-resources":
            with xr.open_dataset(work / "first-run.nc") as original:
                np.testing.assert_array_equal(
                    data.instructional_scalar, original.instructional_scalar)
        elif name == "analytic-moving":
            assert data.sizes["time"] == 2
            assert data.speed.attrs["units"] == "m s-1"
    plot_inputs = [path]
    if name == "coupled-inputs":
        water = next(item for item in status["products"] if item.get("source") == "ocean")
        water_path = directory / water["path"]
        with xr.open_dataset(water_path) as ocean:
            assert ocean.sizes["time"] == 3
            assert ocean.temp.attrs["units"] == "K"
        plot_inputs.append(water_path)
    if interface != "cli":
        return  # The scripts consume the products, not the interface that created them.

    plot = work / f"plot_{script}.py"
    shutil.copyfile(ROOT / "example/plots" / plot.name, plot)
    figure = work / f"{name}.svg"
    args = [sys.executable, str(plot), *map(str, plot_inputs), str(figure)]
    run = subprocess.run(args, cwd=work, capture_output=True, text=True, timeout=30,
                         env={**os.environ, "MPLBACKEND": "Agg"})
    assert run.returncode == 0, run.stdout + run.stderr
    assert figure.stat().st_size > 1000
    before = figure.read_bytes()
    refused = subprocess.run(args, cwd=work, capture_output=True, text=True, timeout=30,
                             env={**os.environ, "MPLBACKEND": "Agg"})
    assert refused.returncode != 0
    assert figure.read_bytes() == before
    existing = work / "existing.png"
    existing.write_bytes(b"unrelated figure")
    args[-1] = str(existing.with_suffix(""))
    refused = subprocess.run(args, cwd=work, capture_output=True, text=True, timeout=30,
                             env={**os.environ, "MPLBACKEND": "Agg"})
    assert refused.returncode != 0
    assert existing.read_bytes() == b"unrelated figure"


@pytest.mark.parametrize("script,field", [
    ("polar_sampling", "u"), ("analytical_event", "speed"),
])
def test_polar_plots_keep_samples_on_north_zero_clockwise_axes(
    tmp_path, monkeypatch, script, field,
):
    import matplotlib.pyplot as plt

    values = np.arange(12., dtype=float).reshape(3, 4)
    path = tmp_path / "polar.nc"
    xr.Dataset({field: (("time", "radius", "azimuth"), values[None], {"units": "m s-1"})},
               coords={"time": [np.datetime64("2000-01-01T01")],
                       "radius": ("radius", [0., 10., 20.], {"units": "km"}),
                       "azimuth": ("azimuth", [0., np.pi/2, np.pi, 3*np.pi/2],
                                   {"units": "rad"})}).to_netcdf(path)
    source = ROOT / f"example/plots/plot_{script}.py"
    monkeypatch.setattr(sys, "argv", [str(source), str(path), str(tmp_path / "polar.svg")])
    try:
        runpy.run_path(str(source), run_name="__main__")
        axes = plt.gcf().axes[0]
        assert axes.name == "polar"
        assert axes.get_theta_direction() == -1
        assert axes.get_theta_offset() == np.pi / 2
        np.testing.assert_array_equal(axes.collections[0].get_array().reshape(3, 4), values)
        coordinates = axes.collections[0].get_coordinates()
        np.testing.assert_array_equal(coordinates[0, :, 1], 0.)
        np.testing.assert_array_equal(coordinates[-1, :, 1], 20.)
        np.testing.assert_allclose(coordinates[0, -1, 0] - coordinates[0, 0, 0], 2 * np.pi)
        np.testing.assert_allclose(axes.get_rmax(), 20.)
    finally:
        plt.close("all")


def test_moving_region_plot_has_three_one_decimal_ticks_per_axis(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt

    path = tmp_path / "track.nc"
    xr.Dataset({"longitude": ("time", [60., 60.1, 60.2]),
                "latitude": ("time", [-20., -20., -20.])},
               coords={"time": np.arange(3)}).to_netcdf(path)
    script = ROOT / "example/plots/plot_moving_region.py"
    monkeypatch.setattr(sys, "argv", [str(script), str(path), str(tmp_path / "track.svg")])
    try:
        runpy.run_path(str(script), run_name="__main__")
        axes = plt.gcf().axes[0]
        plt.gcf().canvas.draw()
        assert len(axes.get_xticks()) == len(axes.get_yticks()) == 3
        assert [label.get_text() for label in axes.get_xticklabels()] == ["60.0", "60.1", "60.2"]
        assert all(re.fullmatch(r"-?\d+\.\d", label.get_text())
                   for label in axes.get_yticklabels())
    finally:
        plt.close("all")


@pytest.mark.parametrize("problem", [None, "time", "units"])
def test_coupled_plot_has_six_fixed_geographical_panels_and_preserves_values(
    tmp_path, monkeypatch, problem,
):
    import matplotlib.pyplot as plt
    from matplotlib.quiver import QuiverKey

    time = np.array(["2000-01-01T00", "2000-01-01T01", "2000-01-01T02"],
                    dtype="datetime64[ns]")
    coords = {"time": time, "latitude": ("y", [-20.4, -20., -19.6]),
              "longitude": ("x", [59.6, 60., 60.4])}
    air_values = 300. + np.arange(27.).reshape(3, 3, 3) / 100
    water_values = 300. - np.arange(27.).reshape(3, 3, 3) / 10
    water_values[:, 0, 0] = np.nan
    air_path, water_path = tmp_path / "air.nc", tmp_path / "water.nc"
    xr.Dataset({
        "height.temperature": (("time", "height", "y", "x"), air_values[:, None],
                               {"units": "K"}),
        "u": (("time", "y", "x"), np.ones((3, 3, 3)),
              {"units": "knots" if problem == "units" else "m s-1"}),
        "v": (("time", "y", "x"), np.zeros((3, 3, 3)), {"units": "m s-1"}),
    }, coords={**coords, "height": ("height", [10.], {"units": "m"})}).to_netcdf(air_path)
    ocean_coords = {{"latitude": "latitude_rho", "longitude": "longitude_rho"}.get(key, key): value
                    for key, value in coords.items()}
    xr.Dataset({"temp": (("time", "depth", "y", "x"), water_values[:, None], {"units": "K"})},
               coords={**ocean_coords,
                       "time": time + np.timedelta64(1, "h") if problem == "time" else time,
                       "depth": [0.]}).to_netcdf(water_path)
    script = ROOT / "example/plots/plot_coupled_inputs.py"
    monkeypatch.setattr(sys, "argv", [
        str(script), str(air_path), str(water_path), str(tmp_path / "coupled.svg")])
    try:
        if problem:
            message = "three times" if problem == "time" else "Expected"
            with pytest.raises(ValueError, match=message):
                runpy.run_path(str(script), run_name="__main__")
            return
        runpy.run_path(str(script), run_name="__main__")
        panels = plt.gcf().axes[:6]
        assert len(plt.gcf().axes) == 8
        for column in range(3):
            np.testing.assert_array_equal(
                panels[column].collections[0].get_array(), air_values[column])
            np.testing.assert_array_equal(
                panels[3 + column].collections[0].get_array().filled(np.nan), water_values[column])
            assert panels[column].collections[1].U[0] == 1.
            assert panels[column].collections[1].V[0] == 0.
        assert all(panel.get_xlim() == (59.6, 60.4) for panel in panels)
        assert all(panel.get_ylim() == (-20.4, -19.6) for panel in panels)
        plt.gcf().canvas.draw()
        key = next(item for item in plt.gcf().findobj() if isinstance(item, QuiverKey))
        assert key.text.get_window_extent().y1 <= plt.gcf().bbox.y1
    finally:
        plt.close("all")
