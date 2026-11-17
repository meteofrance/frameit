"""Tutorial setup needs no supplied data and cannot replace a research directory."""

import subprocess
import sys

import numpy as np
import pytest
import xarray as xr


def test_fixture_command_creates_all_small_instructional_inputs(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "frameit", "generate-tests-fixtures", "--output", "tutorial-data"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / "tutorial-data"
    assert len(list(root.rglob("*.nc"))) == 12
    with xr.open_dataset(root / "pressure.nc") as data:
        assert data.temperature.dims == ("time", "isobaric", "latitude", "longitude")
        assert data.isobaric.attrs["units"] == "Pa"
        np.testing.assert_array_equal(data.isobaric, [85000., 70000., 50000.])
        np.testing.assert_allclose(data.temperature.isel(time=0, latitude=12, longitude=12),
                                   [287., 284., 280.])
        assert data.attrs["source"].startswith("Synthetic")
    with xr.open_dataset(root / "interfaces.nc") as data:
        np.testing.assert_array_equal(data.level_w, [0., 500., 2000., 4000.])
        np.testing.assert_allclose(data.WT.isel(time=0, nj=12, ni=12), [0., .5, 2., 4.])
    before = {path: path.read_bytes() for path in root.rglob("*.nc")}
    refused = subprocess.run(
        [sys.executable, "-m", "frameit", "generate-tests-fixtures", "--output", "tutorial-data"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert refused.returncode != 0
    assert {path: path.read_bytes() for path in root.rglob("*.nc")} == before


def test_fixture_api_refuses_existing_directories_before_writing(tmp_path):
    from frameit.testing.documentation_example import create_task_fixtures

    target = tmp_path / "research"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("research data")
    with pytest.raises(FileExistsError):
        create_task_fixtures(target)
    assert list(target.iterdir()) == [sentinel]
    assert sentinel.read_text() == "research data"
