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
    assert len(list(root.rglob("*.nc"))) == 22
    with xr.open_dataset(root / "staggered-winds/mesonh.nc") as data:
        np.testing.assert_array_equal(data.ni_u.values[[4, 5]], [-500., 500.])
        np.testing.assert_array_equal(data.UT.values[0, 1, 4, [4, 5]], [9.5, 10.5])
        assert data.angle.attrs["units"] == "rad"
    with xr.open_dataset(root / "coupled-clocks/nemo-t.nc") as data:
        np.testing.assert_array_equal(data.time_bounds, np.array(
            [["2000-01-01T05", "2000-01-01T06"], ["2000-01-01T07", "2000-01-01T08"]],
            dtype="datetime64[ns]"))
        assert data.votemper.attrs["cell_methods"] == "time: mean"
    with xr.open_dataset(root / "forecast-archive/b-other-cycle.nc") as data:
        assert data.time.values == np.datetime64("2000-01-01T01")
        assert data.valid_time.values[0] == np.datetime64("2000-01-01T02")
        assert data.prmsl.values[0, 0, 0] == 101200.
    with xr.open_dataset(root / "calculated-track/atmosphere.nc") as data:
        assert set(data.data_vars) == {"prmsl", "u10", "v10"}
        assert data.u10.attrs["sampling_height_m"] == 10.
        assert data.v10.attrs["standard_name"] == "northward_wind"
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
    assert "[E1901]" in refused.stderr
    assert {path: path.read_bytes() for path in root.rglob("*.nc")} == before


def test_fixture_api_refuses_existing_directories_before_writing(tmp_path):
    from frameit.testing.documentation_example import create_task_fixtures

    target = tmp_path / "research"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("research data")
    with pytest.raises(FileExistsError) as exc:
        create_task_fixtures(target)
    assert exc.value.frameit_code == "E1901"
    assert list(target.iterdir()) == [sentinel]
    assert sentinel.read_text() == "research data"


def test_coupled_fixtures_prescribe_three_times_moving_air_and_a_persistent_cold_trail(tmp_path):
    from frameit.testing.documentation_example import create_task_fixtures

    paths = create_task_fixtures(tmp_path / "data")
    with (xr.open_dataset(paths["coupled.atmosphere"]) as air,
          xr.open_dataset(paths["coupled.ocean"]) as ocean,
          xr.open_dataset(paths["moving.atmosphere"]) as original_air,
          xr.open_dataset(paths["moving.ocean"]) as original_ocean):
        np.testing.assert_array_equal(air.time, ocean.time)
        assert air.sizes["time"] == 3 and original_ocean.sizes["time"] == 2
        np.testing.assert_array_equal(air.u, original_air.u)
        np.testing.assert_array_equal(air.v, original_air.v)
        assert air.u.attrs["sampling_height_m"] == air.v.attrs["sampling_height_m"] == 10.
        near_surface = air.temperature.sel(height=10)
        np.testing.assert_array_equal(near_surface.argmax("longitude").isel(latitude=12),
                                      [12, 14, 16])
        np.testing.assert_allclose(near_surface.isel(time=0, latitude=12, longitude=12),
                                   301.9200996674983, rtol=0, atol=1e-12)
        np.testing.assert_allclose(original_air.temperature.sel(height=10), 299.94,
                                   rtol=0, atol=1e-12)
        sst = ocean.temp.isel(s_rho=2)
        np.testing.assert_allclose(sst.isel(eta_rho=6, xi_rho=6), [298., 298., 298.],
                                   rtol=0, atol=1e-12)
        assert sst.isel(time=0, eta_rho=6, xi_rho=8) > 299.
        np.testing.assert_allclose(sst.isel(time=2, eta_rho=6, xi_rho=8), 298.,
                                   rtol=0, atol=1e-12)
        assert ocean.temp.attrs["units"] == air.temperature.attrs["units"] == "K"
        assert "prescribed" in ocean.attrs["event"].lower()
        assert "max" in ocean.temp.attrs["formula"]
