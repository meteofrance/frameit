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
    ("forecast-archive", "forecast_archive", "model_grid"),
    ("field-selection", "field_selection", "model_grid"),
    ("moving-region", "moving_region", "track"),
    ("calculate-track", "calculate_track", "track"),
    ("scalars-and-vectors", "scalars_and_vectors", "model_grid"),
    ("polar-sampling", "polar_sampling", "polar"),
    ("coupled-inputs", "coupled_inputs", "model_grid"),
    ("coupled-clocks", "coupled_clocks", "model_grid"),
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
        elif name == "forecast-archive":
            np.testing.assert_array_equal(data.time, np.array(
                ["2000-01-01T01", "2000-01-01T02"], dtype="datetime64[ns]"))
            assert data.forecast_reference_time.values == np.datetime64("2000-01-01T00")
            np.testing.assert_array_equal(data.step, np.array([1, 2], dtype="timedelta64[h]"))
            np.testing.assert_array_equal(data.prmsl[:, 0, 0], [100100., 100200.])
            assert data.prmsl.attrs["cell_methods"] == "time: point"
            assert data.prmsl.attrs["units"] == "Pa"
        elif name == "field-selection":
            np.testing.assert_array_equal(data.pressure, [850., 700.])
            assert data.pressure.attrs["units"] == "hPa"
        elif name == "moving-region":
            np.testing.assert_allclose(data.longitude, [60., 60.1, 60.2])
        elif name == "calculate-track":
            np.testing.assert_array_equal(data.time, np.array(
                ["2000-01-01T00", "2000-01-01T01", "2000-01-01T02"], dtype="datetime64[ns]"))
            np.testing.assert_allclose(data.longitude, [60., 60.1, 60.2], rtol=0, atol=1e-8)
            np.testing.assert_allclose(data.latitude, [-20.] * 3, rtol=0, atol=1e-8)
            np.testing.assert_array_equal(data.cx, [12, 14, 16])
            np.testing.assert_array_equal(data.cy, [12, 12, 12])
        elif name == "scalars-and-vectors":
            np.testing.assert_allclose(data.speed, np.hypot(data.u, data.v), rtol=0, atol=1e-12)
        elif name == "polar-sampling":
            assert data.u.sizes["azimuth"] == 16
            assert data.u.attrs["units"] == "m s-1"
        elif name == "coupled-inputs":
            assert data.sizes["time"] == 3
            np.testing.assert_array_equal(data.height, [10.])
            assert {"height.temperature", "u", "v"} <= data.data_vars.keys()
        elif name == "coupled-clocks":
            np.testing.assert_array_equal(data.time, np.array(
                ["2000-01-01T06", "2000-01-01T08"], dtype="datetime64[ns]"))
            assert data.prmsl.attrs["cell_methods"] == "time: point"
        elif name == "storage-and-resources":
            with xr.open_dataset(work / "first-run.nc") as original:
                np.testing.assert_array_equal(
                    data.instructional_scalar, original.instructional_scalar)
        elif name == "analytic-moving":
            assert data.sizes["time"] == 2
            assert data.speed.attrs["units"] == "m s-1"
    plot_inputs = [path]
    if name == "forecast-archive":
        provenance = yaml.safe_load((directory / "run-provenance.yaml").read_text())
        selected = provenance["binding"]["atmosphere"]["files"]
        assert {Path(file).name for file in selected} == {"z-earlier.nc", "a-later.nc"}
    if name == "calculate-track":
        assert {p["role"] for p in status["products"]} == {"track", "model_grid"}
        crop = next(p["path"] for p in status["products"] if p["role"] == "model_grid")
        with xr.open_dataset(directory / crop) as air:
            assert set(air.data_vars) == {"prmsl"}
            pressure = air.prmsl
            np.testing.assert_array_equal(
                pressure.isel({d: pressure.sizes[d] // 2 for d in pressure.dims[-2:]}),
                [96000.] * 3)
            assert pressure.attrs["units"] == "Pa"
        plot_inputs.append(work / "data/track.nc")
    if name == "coupled-inputs":
        water = next(item for item in status["products"] if item.get("source") == "ocean")
        water_path = directory / water["path"]
        with xr.open_dataset(water_path) as ocean:
            assert ocean.sizes["time"] == 3
            assert ocean.temp.attrs["units"] == "K"
        plot_inputs.append(water_path)
    if name == "coupled-clocks":
        omitted, = status["time_alignment"]["omitted_pairings"]
        assert np.datetime64(omitted["coupling_time"]) == np.datetime64("2000-01-01T07")
        assert omitted["missing_sources"] == ["ocean"]
        water = next(item for item in status["products"] if item.get("source") == "ocean")
        water_path = directory / water["path"]
        with (xr.open_dataset(water_path) as ocean,
              xr.open_dataset(work / "coupled-clocks/nemo-t.nc") as original):
            np.testing.assert_array_equal(ocean.time, np.array(
                ["2000-01-01T05:30", "2000-01-01T07:30"], dtype="datetime64[ns]"))
            np.testing.assert_array_equal(ocean.center_time, np.array(
                ["2000-01-01T06", "2000-01-01T08"], dtype="datetime64[ns]"))
            np.testing.assert_array_equal(ocean[ocean.time.attrs["bounds"]], original.time_bounds)
            np.testing.assert_array_equal(ocean.deptht, [5.])
            assert ocean.deptht.attrs["positive"] == "down"
            field = ocean.votemper
            assert field.attrs["cell_methods"] == "time: mean"
            assert field.attrs["units"] == "K"
            yd, xd = field.dims[-2:]
            y, x = (next(coord.values for key, coord in field.coords.items()
                         if key.endswith("_source_native_index") and coord.dims == ("time", dim))
                    for dim in (yd, xd))
            for t in range(2):
                np.testing.assert_array_equal(
                    field.isel(time=t), original.votemper.isel(time_counter=t, y=y[t], x=x[t]))
        plot_inputs.extend([water_path, directory / "run-status.yaml"])
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


def test_polar_coverage_checks_missing_wind_and_valid_category_zero(tmp_path):
    from frameit.testing.documentation_example import create_task_fixtures

    pytest.importorskip("xesmf")
    work = tmp_path / "tutorial-data"
    create_task_fixtures(work)
    script = work / "check_polar_coverage.py"
    shutil.copyfile(ROOT / "example/tutorials" / script.name, script)
    shutil.copyfile(ROOT / "example/tutorials/analytic-missing.yaml", work / "analytic-missing.yaml")
    run = subprocess.run(
        [sys.executable, "-m", "frameit", "run", "analytic-missing.yaml"], cwd=work,
        capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    check = subprocess.run([sys.executable, str(script)], cwd=work,
                           capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    assert "Wind at a mapped point is missing: True" in check.stdout
    assert "Interpolation status: 2" in check.stdout
    assert "Full ring is valid: False" in check.stdout
    assert "Valid water code 0 is present: True" in check.stdout


def test_forecast_archive_inventory_shows_cycle_lead_and_valid_time(tmp_path):
    from frameit.testing.documentation_example import create_task_fixtures

    work = tmp_path / "tutorial-data"
    create_task_fixtures(work)
    script = ROOT / "example/tutorials/inspect_forecast_archive.py"
    result = subprocess.run([sys.executable, str(script)], cwd=work,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert set(result.stdout.splitlines()[1:]) == {
        "z-earlier.nc | 2000-01-01T00:00 | 1 | 2000-01-01T01:00",
        "a-later.nc | 2000-01-01T00:00 | 2 | 2000-01-01T02:00",
        "b-other-cycle.nc | 2000-01-01T01:00 | 1 | 2000-01-01T02:00",
    }


def test_forecast_archive_requires_explicit_cycle(tmp_path):
    import yaml

    from frameit.testing.documentation_example import create_task_fixtures

    work = tmp_path / "tutorial-data"
    create_task_fixtures(work)
    raw = yaml.safe_load((ROOT / "example/tutorials/forecast-archive.yaml").read_text())
    del raw["sources"]["atmosphere"]["time"]["cycle"]
    config = work / "no-cycle.yaml"
    config.write_text(yaml.safe_dump(raw))
    run = subprocess.run(
        [sys.executable, "-m", "frameit", "validate", str(config)], cwd=work,
        capture_output=True, text=True, timeout=60)
    assert run.returncode != 0
    report = run.stdout + run.stderr
    assert "E1403" in report and "time.cycle" in report
    assert not (work / raw["output"]["directory"]).exists()


def test_coupled_clocks_reject_exact_policy_for_half_hour_samples(tmp_path):
    import yaml

    from frameit.testing.documentation_example import create_task_fixtures

    work = tmp_path / "tutorial-data"
    create_task_fixtures(work)
    raw = yaml.safe_load((ROOT / "example/tutorials/coupled-clocks.yaml").read_text())
    del raw["region"]["sources_coupling_time_association"]
    config = work / "exact-clocks.yaml"
    config.write_text(yaml.safe_dump(raw))
    run = subprocess.run(
        [sys.executable, "-m", "frameit", "validate", str(config)], cwd=work,
        capture_output=True, text=True, timeout=60)
    assert run.returncode != 0
    report = run.stdout + run.stderr
    assert "E1404" in report and "05:30" in report
    assert not (work / raw["output"]["directory"]).exists()


def test_table_track_file_works_and_missing_middle_position_fails(tmp_path):
    import yaml

    from frameit.testing.documentation_example import create_task_fixtures

    work = tmp_path / "tutorial-data"
    paths = create_task_fixtures(work)
    script = work / "write_table_track.py"
    shutil.copyfile(ROOT / "example/tutorials" / script.name, script)
    reference = paths["moving.track"]
    before = reference.read_bytes()
    run = subprocess.run([sys.executable, str(script)], cwd=work,
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    assert reference.read_bytes() == before
    raw = yaml.safe_load((ROOT / "example/tutorials/moving-region.yaml").read_text())
    raw["run"]["name"] = "table-region"
    raw["region"]["track"]["file"] = "./table-track.nc"
    raw["output"]["directory"] = "./results/table-region"
    config = work / "table-region.yaml"
    config.write_text(yaml.safe_dump(raw))
    run = subprocess.run(
        [sys.executable, "-m", "frameit", "run", str(config)], cwd=work,
        capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    with (xr.open_dataset(reference) as expected,
          xr.open_dataset(work / "results/table-region/products/table-region.track.nc") as track):
        for name in ("time", "latitude", "longitude"):
            np.testing.assert_array_equal(track[name], expected[name])
    raw["region"]["track"]["file"] = "./table-track-gap.nc"
    raw["output"]["directory"] = "./results/gap-region"
    gap = work / "gap-region.yaml"
    gap.write_text(yaml.safe_dump(raw))
    validate = subprocess.run(
        [sys.executable, "-m", "frameit", "validate", str(gap)], cwd=work,
        capture_output=True, text=True, timeout=60)
    assert validate.returncode != 0
    report = validate.stdout + validate.stderr
    assert "E1404" in report and "01:00" in report


def test_staggered_winds_export_uses_requested_locations_and_directions(tmp_path):
    from frameit.core.execution import execute_simulation
    from frameit.core.settings_class import SimulationConfig
    from frameit.testing.documentation_example import create_task_fixtures

    work = tmp_path / "tutorial-data"
    paths = create_task_fixtures(work)
    source = paths["staggered-winds.mesonh"]
    before = source.read_bytes()
    products = {}
    for representation in ("native", "earth"):
        name = f"staggered-winds-{representation}"
        config = work / f"{name}.yaml"
        shutil.copyfile(ROOT / "example/tutorials" / config.name, config)
        result = execute_simulation(SimulationConfig.from_yaml_with_model_preset(config))
        assert result.ok
        product, = result.products
        assert product["role"] == "model_grid"
        products[representation] = product["path"]
    with (xr.open_dataset(products["native"]) as native,
          xr.open_dataset(products["earth"]) as earth,
          xr.open_dataset(source) as original):
        for data in (native, earth):
            np.testing.assert_array_equal(data.level, [5.])
            assert data.UT.attrs["units"] == data.VT.attrs["units"] == "m s-1"
        assert native.UT.dims == ("time", "level", "y", "x_u")
        assert native.VT.dims == ("time", "level", "y_v", "x")
        assert native.UT.attrs["standard_name"] == "x_wind"
        assert native.VT.attrs["standard_name"] == "y_wind"
        u = 10 + (native.latitude_u + 20) * 111
        expected = xr.broadcast(u, native.UT)[0].transpose(*native.UT.dims)
        np.testing.assert_allclose(native.UT, expected, rtol=0, atol=1e-9)
        np.testing.assert_array_equal(native.VT, 0.)
        indices = {dim: native[f"{dim}_source_native_index"].isel(time=0).values
                   for dim in ("nj_v", "ni_v")}
        for coord in ("latitude_v", "longitude_v"):
            np.testing.assert_array_equal(native[coord].isel(time=0),
                                          original[coord].isel(indices))
        assert earth.UT.dims == earth.VT.dims == ("time", "level", "y", "x")
        assert earth.UT.attrs["standard_name"] == "eastward_wind"
        assert earth.VT.attrs["standard_name"] == "northward_wind"
        assert earth.VT.attrs["wind_reference_frame"] == "earth"
        np.testing.assert_allclose(earth.UT, 0., rtol=0, atol=1e-9)
        np.testing.assert_allclose(earth.VT.isel(time=0, level=0, y=1),
                                   [9., 10., 11.], rtol=0, atol=1e-9)
    assert source.read_bytes() == before
    script = ROOT / "example/tutorials/check_staggered_winds.py"
    check = subprocess.run([sys.executable, str(script)], cwd=work,
                           capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    assert "Native UT x (m): [-1500.0, -500.0, 500.0]" in check.stdout
    assert "Native VT y (m): [-1500.0, -500.0, 500.0]" in check.stdout
    assert "Mass x (m): [-1000.0, 0.0, 1000.0]" in check.stdout
    assert "Mass y (m): [-1000.0, 0.0, 1000.0]" in check.stdout
    assert "Eastward (m/s): [0.0, 0.0]" in check.stdout
    assert "Northward (m/s): [10.0, 11.0]" in check.stdout


def test_calculate_track_reports_seed_with_no_pressure_candidate(tmp_path):
    import yaml

    from frameit.testing.documentation_example import create_task_fixtures

    work = tmp_path / "tutorial-data"
    create_task_fixtures(work)
    raw = yaml.safe_load((ROOT / "example/tutorials/calculate-track.yaml").read_text())
    raw["region"]["tracker"]["initial_guess"]["longitude"] = 50
    config = work / "bad-seed.yaml"
    config.write_text(yaml.safe_dump(raw))
    run = subprocess.run(
        [sys.executable, "-m", "frameit", "run", str(config)], cwd=work,
        capture_output=True, text=True, timeout=60)
    assert run.returncode != 0
    assert "initial guess search circle contains no finite MSLP" in run.stderr
    assert not list((work / raw["output"]["directory"] / "products").glob("*.nc"))


def test_calculate_track_plot_keeps_both_latitudes_visible(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt

    known = tmp_path / "known.nc"
    calculated = tmp_path / "calculated.nc"
    for path, latitude in ((known, -20.), (calculated, -19.85)):
        xr.Dataset({
            "longitude": ("time", [60., 60.1]),
            "latitude": ("time", [latitude] * 2),
        }, coords={"time": np.arange(2)}).to_netcdf(path)
    script = ROOT / "example/plots/plot_calculate_track.py"
    figure = tmp_path / "comparison.svg"
    monkeypatch.setattr(sys, "argv", [str(script), str(calculated), str(known), str(figure)])
    try:
        runpy.run_path(str(script), run_name="__main__")
        bottom, top = plt.gcf().axes[0].get_ylim()
        assert bottom <= -20. < -19.85 <= top
    finally:
        plt.close("all")


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
