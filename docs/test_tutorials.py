"""Run the downloadable tutorials and plotting scripts on generated inputs only."""

import os
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
    ("analytic-moving", "analytical_event", "model_grid"),
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
        elif name == "storage-and-resources":
            with xr.open_dataset(work / "first-run.nc") as original:
                np.testing.assert_array_equal(
                    data.instructional_scalar, original.instructional_scalar)
        elif name == "analytic-moving":
            np.testing.assert_allclose(data["height.temperature"], 294., rtol=0, atol=1e-12)
            assert data.sizes["time"] == 2
    plot = work / f"plot_{script}.py"
    shutil.copyfile(ROOT / "example/plots" / plot.name, plot)
    figure = work / f"{name}.svg"
    args = [sys.executable, str(plot), str(path), str(figure)]
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
