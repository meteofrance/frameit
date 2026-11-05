"""Small instructional input and the documented first run, with independent readers."""

import subprocess
import sys

import numpy as np
import pytest
import xarray as xr
import yaml


def test_input_is_deterministic_labelled_and_not_a_physical_field(tmp_path):
    from frameit.testing.documentation_example import create_first_run_input

    first = create_first_run_input(tmp_path / "first.nc")
    second = create_first_run_input(tmp_path / "second.nc")
    # Avoid discovering unrelated optional readers for this known NetCDF input.
    with xr.open_dataset(first, engine="netcdf4") as a, xr.open_dataset(second, engine="netcdf4") as b:
        xr.testing.assert_identical(a, b)
        assert a.sizes == {"valid_time": 2, "latitude": 17, "longitude": 17}
        assert set(a.data_vars) == {"instructional_scalar"}
        np.testing.assert_allclose(a.latitude, np.linspace(-20.08, -19.92, 17))
        np.testing.assert_allclose(a.longitude, np.linspace(59.92, 60.08, 17))
        np.testing.assert_array_equal(a.valid_time, np.array(
            ["2000-01-01T00:00", "2000-01-01T01:00"], dtype="datetime64[ns]"))
        assert a.latitude.attrs["units"] == "degrees_north"
        assert a.longitude.attrs["units"] == "degrees_east"
        field = a.instructional_scalar
        assert field.attrs["units"] == "1"
        assert field[0, 8, 8] == 0 and field[1, 8, 8] == 1000
        assert field[0, 0, 0] == -88 and field[1, 16, 16] == 1088
        assert field[:, 7, 9].isnull().all() and int(field.isnull().sum()) == 2
        assert "instructional" in a.attrs["title"].lower()
        assert "not an AROME producer file" in a.attrs["source"]
        assert "1000*t + 10*(j-8) + (i-8)" in field.attrs["comment"]


def test_input_creation_refuses_overwrite_without_changing_bytes(tmp_path):
    from frameit.testing.documentation_example import create_first_run_input

    path = tmp_path / "existing.nc"
    path.write_bytes(b"existing research input")
    with pytest.raises(FileExistsError):
        create_first_run_input(path)
    assert path.read_bytes() == b"existing research input"
    assert list(tmp_path.iterdir()) == [path]


def test_exact_first_run_commands_and_fresh_ordinary_reader(tmp_path):
    def run(*args):
        result = subprocess.run([sys.executable, *args], cwd=tmp_path,
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    run("-m", "frameit.testing.documentation_example", "--output", "data/first-run.nc")
    source = tmp_path / "data/first-run.nc"
    source.chmod(0o444)
    before = source.read_bytes(), source.stat().st_mtime_ns
    run("-m", "frameit", "init", "arome-fixed-scalar")
    run("-m", "frameit", "validate", "--schema-only")
    run("-m", "frameit", "validate")
    plan = yaml.safe_load(run("-m", "frameit", "run", "--dry-run"))
    assert not (tmp_path / "output").exists()
    assert len(plan["planned_products"]) == 2
    run("-m", "frameit", "run")
    status = yaml.safe_load((tmp_path / "output/run-status.yaml").read_text())
    assert status["state"] == "completed" and status["tracking_complete"]
    assert {(p["role"], p["group"]) for p in status["products"]} == {
        ("track", None), ("cart", "surface")}
    resolved = yaml.safe_load((tmp_path / "output/resolved-config.yaml").read_text())
    assert resolved["schema_version"] == "2.1"
    assert resolved["variables"] == {"surface": {"names": ["instructional_scalar"]}}
    assert resolved["polar"]["enabled"] is False
    assert resolved["domain"]["width_km"] == {"x": 4, "y": 4}
    assert resolved["input"]["wind_pairs"] == []
    assert (tmp_path / "output/run-provenance.yaml").is_file()
    run("-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset('output/products/arome-fixed-scalar.cart.surface.nc', engine='netcdf4') as d:
    assert dict(d.sizes) == {'time': 2, 'y_box': 5, 'x_box': 5}
    assert set(d.data_vars) == {'instructional_scalar'}
    first = np.array([[-22, -21, -20, -19, -18], [-12, -11, -10, np.nan, -8],
                      [-2, -1, 0, 1, 2], [8, 9, 10, 11, 12], [18, 19, 20, 21, 22]])
    np.testing.assert_array_equal(d.instructional_scalar, np.stack([first, first + 1000]))
    assert d.instructional_scalar.attrs['units'] == '1'
    np.testing.assert_allclose(d.latitude[0, :, 0], [-20.02, -20.01, -20, -19.99, -19.98])
    np.testing.assert_allclose(d.longitude[0, 0, :], [59.98, 59.99, 60, 60.01, 60.02])
    np.testing.assert_array_equal(d.time, np.array(['2000-01-01T00', '2000-01-01T01'], dtype='datetime64[ns]'))
with xr.open_dataset('output/products/arome-fixed-scalar.track.nc', engine='netcdf4') as d:
    np.testing.assert_array_equal(d.cx, [8, 8])
    np.testing.assert_array_equal(d.cy, [8, 8])
    np.testing.assert_allclose(d.lat, -20)
    np.testing.assert_allclose(d.lon, 60)
assert 'frameit' not in sys.modules
""")
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_input_creation_and_explicit_reader_need_no_optional_scientific_stack(tmp_path):
    result = subprocess.run([sys.executable, "-c", """
import sys, xarray as xr
from frameit.testing.documentation_example import create_first_run_input
create_first_run_input(sys.argv[1])
with xr.open_dataset(sys.argv[1], engine='netcdf4') as d:
    assert d.sizes['valid_time'] == 2
import pyproj
assert not {'cfgrib', 'epygram', 'xesmf', 'esmpy', 'torch', 'zarr'} & sys.modules.keys()
""", str(tmp_path / "input.nc")], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
