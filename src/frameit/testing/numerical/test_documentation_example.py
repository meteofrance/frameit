"""Small instructional input and the documented first run, with independent readers."""

import subprocess
import sys

import numpy as np
import pytest
import xarray as xr
import yaml


@pytest.mark.parametrize("translating", [False, True])
def test_analytical_inputs_follow_declared_formulas_and_independent_clocks(tmp_path, translating):
    from pyproj import Geod

    from frameit.testing.documentation_example import create_tutorial_inputs

    paths = create_tutorial_inputs(tmp_path / "first", translating=translating)
    repeated = create_tutorial_inputs(tmp_path / "second", translating=translating)
    for name in paths:
        with xr.open_dataset(paths[name]) as first, xr.open_dataset(repeated[name]) as second:
            xr.testing.assert_identical(first, second)
    with xr.open_dataset(paths["track"]) as track, xr.open_dataset(paths["atmosphere"]) as air:
        assert air.sizes["time"] == 3
        np.testing.assert_allclose(track.longitude, [60., 60.1, 60.2] if translating else [60.] * 3)
        np.testing.assert_allclose(track.latitude, -20.)
        np.testing.assert_allclose(air.temperature.isel(time=0, latitude=12, longitude=12),
                                   [299.94, 294., 282.])
        np.testing.assert_allclose(air.interface_w.isel(time=0, latitude=12, longitude=12),
                                   [0., .5, 2., 4.])
        lon, lat = np.meshgrid(air.longitude, air.latitude)
        for index in range(3):
            _, back, distance = Geod(ellps="WGS84").inv(
                np.full(lon.shape, track.longitude[index].item()),
                np.full(lat.shape, -20.), lon, lat)
            bearing = np.deg2rad((back + 180.) % 360.)
            speed = 40. * (distance / 40000.) * np.exp((1. - (distance / 40000.)**2) / 2.)
            np.testing.assert_allclose(air.u[index], speed * np.cos(bearing), rtol=0, atol=1e-12)
            np.testing.assert_allclose(air.v[index], -speed * np.sin(bearing), rtol=0, atol=1e-12)
            np.testing.assert_allclose(air.pressure[index],
                                       101000. - 5000. * np.exp(-(distance / 40000.)**2),
                                       rtol=0, atol=1e-12)
        np.testing.assert_allclose(air.u.isel(time=0, latitude=12, longitude=12), 0.)
    with xr.open_dataset(paths["ocean"]) as water, xr.open_dataset(paths["track"]) as track:
        assert water.sizes["time"] == 2
        np.testing.assert_array_equal(water.time, track.time.isel(time=[0, 2]))
        np.testing.assert_allclose(water.depth, [-30., -10., 0.])
        for index, track_index in enumerate((0, 2)):
            lon, lat = water.lon_rho.values, water.lat_rho.values
            _, _, distance = Geod(ellps="WGS84").inv(
                np.full(lon.shape, track.longitude[track_index].item()),
                np.full(lat.shape, -20.), lon, lat)
            z = np.array([-30., -10., 0.])[:, None, None]
            expected = 300. + .01 * z - 2. * np.exp(-(distance / 40000.)**2) * np.exp(z / 20.)
            np.testing.assert_allclose(water.temp[index], expected, rtol=0, atol=1e-12)
        assert np.isfinite(water.temp).all()
        assert water.temp.attrs["units"] == "K"
        assert water.attrs["source"].startswith("Synthetic")
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths.values()}
    with pytest.raises(FileExistsError):
        create_tutorial_inputs(tmp_path / "first", translating=translating)
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before} == before


def test_analytical_missing_and_category_variant_keeps_valid_zeroes(tmp_path):
    from frameit.testing.documentation_example import create_tutorial_inputs

    paths = create_tutorial_inputs(tmp_path, missing=True)
    with xr.open_dataset(paths["atmosphere"]) as source:
        assert np.isnan(source.u.isel(latitude=10, longitude=11)).all()
        assert (source.surface_type.isel(longitude=0) == 0).all()
        assert source.surface_type.attrs["flag_meanings"] == "water land"
    with xr.open_dataset(paths["ocean"]) as source:
        assert (source.mask_rho.isel(eta_rho=0) == 0).all()
        assert np.isnan(source.temp.isel(eta_rho=0)).all()
        assert np.isfinite(source.temp.isel(eta_rho=6, xi_rho=6)).all()


@pytest.mark.parametrize("polar", [False, True])
def test_analytical_tutorial_commands_keep_sparse_times_levels_and_source_bytes(tmp_path, polar):
    from pathlib import Path

    def run(*args):
        result = subprocess.run([sys.executable, *args], cwd=tmp_path,
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    run("-m", "frameit.testing.documentation_example", "--tutorial", "translating",
        "--output", "data")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (tmp_path / "data").glob("*.nc")}
    template = Path(__file__).parents[4] / "example/tutorials/analytic-moving.yaml"
    raw = yaml.safe_load(template.read_text())
    if not polar:
        raw["products"].pop("polar")
        raw["products"].pop("track")
    (tmp_path / "frameit.yaml").write_text(yaml.safe_dump(raw))
    run("-m", "frameit", "validate", "frameit.yaml", "--schema-only")
    run("-m", "frameit", "validate", "frameit.yaml")
    assert not (tmp_path / "results").exists()
    run("-m", "frameit", "run", "frameit.yaml")
    run("-m", "frameit", "status", "results/analytic-moving")
    run("-c", """
import sys, numpy as np, xarray as xr, yaml
status = yaml.safe_load(open('results/analytic-moving/run-status.yaml'))
assert status['state'] == 'completed'
products = status['products']
with xr.open_dataset(
    'results/analytic-moving/products/analytic-moving.atmosphere.model_grid.nc'
) as air:
    np.testing.assert_array_equal(air.time, np.array(
        ['2000-01-01T01', '2000-01-01T02'], dtype='datetime64[ns]'))
    values = air['height.temperature']
    assert values.sizes['height'] == 1
    np.testing.assert_allclose(values, 294.)
    assert 'speed' not in air
with xr.open_dataset(
    'results/analytic-moving/products/analytic-moving.ocean.model_grid.nc'
) as water:
    np.testing.assert_array_equal(water.time, np.array(
        ['2000-01-01T00', '2000-01-01T02'], dtype='datetime64[ns]'))
    np.testing.assert_allclose(water.s_rho, [0., -.25, -.75])
    assert water.temp.attrs['units'] == 'K'
assert 'frameit' not in sys.modules
""")
    status = yaml.safe_load((tmp_path / "results/analytic-moving/run-status.yaml").read_text())
    roles = {p["role"] for p in status["products"]}
    assert roles == ({"model_grid", "polar", "track"} if polar else {"model_grid"})
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before


def test_missing_tutorial_consumes_category_and_explicit_renormalization(tmp_path):
    from pathlib import Path

    from frameit.testing.documentation_example import create_tutorial_inputs

    paths = create_tutorial_inputs(tmp_path / "missing-data", missing=True)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths.values()}
    example = Path(__file__).parents[4] / "example/tutorials/analytic-missing.yaml"
    raw = yaml.safe_load(example.read_text())
    outputs = {}
    for policy in ("strict", "renormalize"):
        raw["output"]["directory"] = f"./{policy}-results"
        raw["products"]["polar"]["field_options"]["atmosphere"]["u"] = {
            "missing_data_policy": policy,
            **({"min_valid_weight_fraction": .5} if policy == "renormalize" else {})}
        request = tmp_path / f"{policy}.yaml"
        request.write_text(yaml.safe_dump(raw))
        run = subprocess.run(
            [sys.executable, "-m", "frameit", "run", str(request)], cwd=tmp_path,
            capture_output=True, text=True, timeout=60)
        assert run.returncode == 0, run.stdout + run.stderr
        with xr.open_dataset(
                tmp_path / f"{policy}-results/products/analytic-missing.atmosphere.polar.nc") as ds:
            outputs[policy] = ds.load()
    strict, partial = outputs["strict"], outputs["renormalize"]
    recovered = np.isnan(strict.u) & np.isfinite(partial.u)
    assert recovered.any()
    assert (partial.u_interpolation_status.where(recovered, 0) == 0).all()
    assert (partial.u_support_fraction.where(recovered, .5) >= .5).all()
    assert (partial.u_support_fraction.where(recovered, .5) < 1).all()
    assert set(np.unique(partial.surface_type)) == {0., 1.}
    xr.testing.assert_identical(strict.surface_type, partial.surface_type)
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before


def test_interface_walkthrough_keeps_native_w_and_explicit_mass_w_distinct(tmp_path):
    from pathlib import Path

    from frameit.testing.documentation_example import create_task_fixtures

    paths = create_task_fixtures(tmp_path / "generated")
    root = Path(__file__).parents[4]
    path = tmp_path / "interfaces.nc"
    path.write_bytes(paths["interfaces"].read_bytes())
    before = path.read_bytes(), path.stat().st_mtime_ns
    request = tmp_path / "interfaces.yaml"
    request.write_text((root / "example/tutorials/analytic-interfaces.yaml").read_text())
    run = subprocess.run([sys.executable, "-m", "frameit", "run", str(request)], cwd=tmp_path,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    reader = subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset('interface-results/products/analytic-interfaces.atmosphere.model_grid.nc') as ds:
    np.testing.assert_allclose(ds.WT, .5, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(ds.level_w, [500.])
with xr.open_dataset('interface-results/products/analytic-interfaces.atmosphere.polar.nc') as ds:
    np.testing.assert_allclose(ds.WT, 1., rtol=0, atol=1e-12)
    np.testing.assert_array_equal(ds.level, [1000.])
    assert ds.WT.attrs['units'] == 'm s-1'
assert 'frameit' not in sys.modules
"""], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert reader.returncode == 0, reader.stderr
    with pytest.raises(FileExistsError):
        create_task_fixtures(tmp_path / "generated")
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


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


@pytest.mark.parametrize("tutorial_edits", [False, True], ids=["starter", "guided-first-run"])
def test_exact_first_run_commands_and_fresh_ordinary_reader(tmp_path, tutorial_edits):
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
    root, name = ("results", "first-run") if tutorial_edits else ("output", "arome-fixed-scalar")
    if tutorial_edits:
        path = tmp_path / "frameit.yaml"
        raw = yaml.safe_load(path.read_text())
        raw["run"]["name"] = name
        raw["output"]["directory"] = f"./{root}"
        path.write_text(yaml.safe_dump(raw))
    run("-m", "frameit", "inspect", "frameit.yaml")
    run("-m", "frameit", "validate", "--schema-only")
    run("-m", "frameit", "validate")
    plan = yaml.safe_load(run("-m", "frameit", "config", "show", "frameit.yaml", "--effective",
                              "--json"))
    assert not (tmp_path / root).exists()
    assert set(plan["data"]["configuration"]["products"]) == {"model_grid"}
    run("-m", "frameit", "run")
    run("-m", "frameit", "status", f"./{root}")
    status = yaml.safe_load((tmp_path / root / "run-status.yaml").read_text())
    assert status["state"] == "completed" and status["tracking_complete"]
    assert {(p["role"], p["source"]) for p in status["products"]} == {
        ("model_grid", "atmosphere")}
    resolved = yaml.safe_load((tmp_path / root / "resolved-config.yaml").read_text())
    assert resolved["schema_version"] == 3
    assert resolved["sources"]["atmosphere"]["variables"] == {"2d": ["instructional_scalar"]}
    assert "polar" not in resolved["products"] and "track" not in resolved["products"]
    assert resolved["region"]["width_km"] == {"x": 4, "y": 4}
    assert resolved["sources"]["atmosphere"]["wind_pairs"] == []
    assert resolved["run"]["name"] == name
    assert (tmp_path / root / "run-provenance.yaml").is_file()
    run("-c", """
import sys, numpy as np, xarray as xr
root, name = sys.argv[1:]
with xr.open_dataset(f'{root}/products/{name}.atmosphere.model_grid.nc', engine='netcdf4') as d:
    assert dict(d.sizes) == {'time': 2, 'y': 5, 'x': 5}
    assert set(d.data_vars) == {'instructional_scalar'}
    first = np.array([[-22, -21, -20, -19, -18], [-12, -11, -10, np.nan, -8],
                      [-2, -1, 0, 1, 2], [8, 9, 10, 11, 12], [18, 19, 20, 21, 22]])
    np.testing.assert_array_equal(d.instructional_scalar, np.stack([first, first + 1000]))
    assert d.instructional_scalar.attrs['units'] == '1'
    np.testing.assert_allclose(d.latitude[0, :, 0], [-20.02, -20.01, -20, -19.99, -19.98])
    np.testing.assert_allclose(d.longitude[0, 0, :], [59.98, 59.99, 60, 60.01, 60.02])
    np.testing.assert_array_equal(d.time, np.array(['2000-01-01T00', '2000-01-01T01'], dtype='datetime64[ns]'))
    np.testing.assert_array_equal(d.longitude_source_native_index[:, 2], [8, 8])
    np.testing.assert_array_equal(d.latitude_source_native_index[:, 2], [8, 8])
    np.testing.assert_allclose(d.center_latitude, -20)
    np.testing.assert_allclose(d.center_longitude, 60)
assert 'frameit' not in sys.modules
""", root, name)
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_quick_start_commands_use_the_selected_mesonh_scalar(tmp_path):
    from frameit.testing.numerical.test_configuration_v2_1 import dataset

    data = tmp_path / 'data'
    data.mkdir()
    dataset(data)
    source = data / "native.nc"
    before = source.read_bytes(), source.stat().st_mtime_ns

    def run(*args):
        result = subprocess.run([sys.executable, '-m', 'frameit', *args], cwd=tmp_path,
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    run('init', 'mesonh', '--tracking', 'fixed_box', '--output', 'region.yaml')
    path = tmp_path / 'region.yaml'
    raw = yaml.safe_load(path.read_text())
    raw['sources']['atmosphere']['files'] = './data/native.nc'
    raw['region']['width_km'] = {'x': 4, 'y': 4}
    path.write_text(yaml.safe_dump(raw))
    run('inspect', 'region.yaml')
    run('validate', 'region.yaml', '--schema-only')
    run('validate', 'region.yaml')
    assert yaml.safe_load(run('config', 'show', 'region.yaml'))['sources']['atmosphere'][
        'variables'] == {'2d': ['MSLP']}
    run('config', 'show', 'region.yaml', '--effective')
    assert not (tmp_path / 'output').exists()
    run('run', 'region.yaml')
    status = yaml.safe_load((tmp_path / 'output/run-status.yaml').read_text())
    assert status['state'] == 'completed' and status['tracking_complete']
    result = subprocess.run([sys.executable, '-c', """
import sys, numpy as np, xarray as xr
path = 'output/products/mesonh-fixed-scalar.atmosphere.model_grid.nc'
with xr.open_dataset(path, engine='netcdf4') as d:
    assert set(d.data_vars) == {'MSLP'}
    assert dict(d.sizes) == {'time': 2, 'y': 3, 'x': 3}
    np.testing.assert_array_equal(d.MSLP, np.full((2, 3, 3), 100000.))
    assert d.MSLP.attrs['units'] == 'Pa'
assert 'frameit' not in sys.modules
"""], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
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
