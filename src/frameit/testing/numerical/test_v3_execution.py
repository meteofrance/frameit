"""V3 native execution: selected samples, independent clocks and ordinary readers."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.configuration import load_runtime
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.testing.documentation_example import create_first_run_input


def _configuration(tmp_path, sources, *, output=None):
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump({
        "schema_version": 3,
        "run": {"name": "native"},
        "sources": sources,
        "output": {"directory": "./out", **(output or {})},
        "resources": {"synchronous_export": True, "scheduler": "synchronous"},
    }))
    return SimulationConfig(**load_runtime(path))


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _ordinary_reader(product, source, field, clock):
    subprocess.run([sys.executable, "-c", """
import sys
import numpy as np
import xarray as xr
assert not any(name == 'frameit' or name.startswith('frameit.') for name in sys.modules)
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source:
    field, clock = sys.argv[3:]
    assert set(out.data_vars) == {field}
    np.testing.assert_array_equal(out[field].values, source[field].values)
    assert out[field].dtype == source[field].dtype
    assert out[field].attrs == source[field].attrs
    np.testing.assert_array_equal(out.time.values, source[clock].values)
    assert out.time.encoding['calendar'] == source[clock].encoding['calendar']
    for name in ('latitude', 'longitude', 'nav_lat', 'nav_lon'):
        if name in source:
            stored = {'nav_lat': 'latitude_t', 'nav_lon': 'longitude_t'}.get(name, name)
            np.testing.assert_array_equal(out[stored].values, source[name].values)
            assert out[stored].attrs == source[name].attrs
    for native, dim in (('latitude','y'),('longitude','x'),('y','y_t'),('x','x_t')):
        if native in source.dims and dim in out.dims:
            np.testing.assert_array_equal(out[dim], np.arange(source.sizes[native]))
            np.testing.assert_array_equal(out[f'{native}_source_native_index'],
                                          np.arange(source.sizes[native]))
            if native in source.coords:
                np.testing.assert_array_equal(out[f'{native}_source_coordinate'],source[native])
    assert not any(name in out for name in ('wind_speed', 'vrad', 'vtan', 'center_latitude'))
    assert 'track_filename' not in out.attrs
    assert out.attrs['frameit_version']
assert not any(name == 'frameit' or name.startswith('frameit.') for name in sys.modules)
""", str(product), str(source), field, clock], check=True, capture_output=True, text=True)


def test_native_scalar_roundtrip(tmp_path, monkeypatch):
    """A native request must not crop, change zero/NaN, invent a track or clobber."""
    source = create_first_run_input(tmp_path / "scalar.nc")
    original = _digest(source)
    conf = _configuration(tmp_path, {
        "weather": {"model": "arome", "files": "./scalar.nc",
                    "variables": {"2d": ["instructional_scalar"]}},
    })
    import builtins

    original_import = builtins.__import__

    def native_only(name, *args, **kwargs):
        if name.split(".")[0] in {"zarr", "xesmf", "ESMF", "esmpy", "epygram",
                                 "eccodes", "cfgrib"}:
            raise AssertionError(f"Native extraction imported unrelated backend {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", native_only)

    result = execute_simulation(conf)

    assert result.ok and result.n_files == 1
    assert result.files == [str(source)]
    assert len(result.products) == 1
    product = result.products[0]
    expected = conf.output_dir / "products/native.weather.model_grid.nc"
    assert Path(product["path"]) == expected
    assert product["source"] == "weather" and product["role"] == "model_grid"
    assert list((conf.output_dir / "products").iterdir()) == [expected]
    _ordinary_reader(expected, source, "instructional_scalar", "valid_time")
    with xr.open_dataset(expected) as out:
        assert out.instructional_scalar.shape == (2, 17, 17)
        assert out.instructional_scalar.values[0, 8, 8] == 0
        assert np.isnan(out.instructional_scalar.values[:, 7, 9]).all()
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["state"] == "completed"
    assert [item["path"] for item in status["products"]] == [
        "products/native.weather.model_grid.nc"]
    assert _digest(source) == original
    before = {path: _digest(path) for path in conf.output_dir.rglob("*") if path.is_file()}
    with pytest.raises(FileExistsError, match="overwrite=False"):
        execute_simulation(conf)
    assert {path: _digest(path) for path in conf.output_dir.rglob("*") if path.is_file()} == before
    assert _digest(source) == original


def test_sources_keep_independent_clocks(tmp_path):
    """Independent atmosphere/ocean extraction must not intersect or relabel times."""
    atmosphere = create_first_run_input(tmp_path / "scalar.nc")
    ocean = tmp_path / "ocean.nc"
    xr.Dataset({
        "sea_scalar": (("time_counter", "y", "x"), [
            [[0., np.nan], [2., 3.]], [[10., 11.], [12., 13.]]], {"units": "1"}),
    }, coords={
        "time_counter": ("time_counter", np.array(
            ["2000-01-01T00:30", "2000-01-01T01:30"], dtype="datetime64[ns]"),
            {"standard_name": "time", "axis": "T"}),
        "nav_lat": (("y", "x"), [[-20., -20.], [-19.99, -19.99]],
                    {"standard_name": "latitude", "units": "degrees_north"}),
        "nav_lon": (("y", "x"), [[60., 60.01], [60., 60.01]],
                    {"standard_name": "longitude", "units": "degrees_east"}),
    }).to_netcdf(ocean)
    originals = {path: _digest(path) for path in (atmosphere, ocean)}
    conf = _configuration(tmp_path, {
        "weather": {"model": "arome", "files": "./scalar.nc",
                    "variables": {"2d": ["instructional_scalar"]}},
        "water": {"model": "nemo", "files": "./ocean.nc",
                  "variables": {"2d": ["sea_scalar"]}},
    })

    result = execute_simulation(conf)

    assert result.ok and result.n_files == 2
    assert set(result.files) == {str(atmosphere), str(ocean)}
    assert {item["source"] for item in result.products} == {"weather", "water"}
    assert {item["role"] for item in result.products} == {"model_grid"}
    for name, path, field, clock in (
        ("weather", atmosphere, "instructional_scalar", "valid_time"),
        ("water", ocean, "sea_scalar", "time_counter"),
    ):
        product = next(item for item in result.products if item["source"] == name)
        assert Path(product["path"]).name == f"native.{name}.model_grid.nc"
        _ordinary_reader(product["path"], path, field, clock)
        assert _digest(path) == originals[path]
        binding = conf.source_requests[name]["binding"]
        assert binding is not None and binding["status"] == "bound"
        source = conf.simulation_parameter["request_plan"]["sources"][name]
        assert source["requests"]["binding"]["status"] == "bound"
    assert len(list((conf.output_dir / "products").iterdir())) == 2


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4", "scipy"])
def test_readers_obey_selected_records(tmp_path, monkeypatch, engine):
    """Even an oversized requested time chunk cannot read an excluded sample."""
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper
    from xarray.backends.netCDF4_ import NetCDF4ArrayWrapper
    from xarray.backends.scipy_ import ScipyArrayWrapper

    source = create_first_run_input(tmp_path / "scalar.nc")
    if engine == "scipy":
        with xr.open_dataset(source, engine="netcdf4") as original:
            source = tmp_path / "scalar-classic.nc"
            original.to_netcdf(source, engine="scipy")
    conf = _configuration(tmp_path, {
        "weather": {"model": "arome", "files": f"./{source.name}",
                    "variables": {"2d": ["instructional_scalar"]},
                    "time": {"values": ["2000-01-01T01:00:00"]},
                    "reader": {"engine": engine, "chunks": {"valid_time": 2}}},
    })
    reads = []
    with monkeypatch.context() as guard:
        for wrapper in (H5NetCDFArrayWrapper, NetCDF4ArrayWrapper, ScipyArrayWrapper):
            original = wrapper.__getitem__

            def selected_only(array, key, original=original):
                if array.variable_name == "instructional_scalar":
                    positions = np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]])
                    reads.extend(positions.tolist())
                    np.testing.assert_array_equal(positions, [1])
                return original(array, key)

            guard.setattr(wrapper, "__getitem__", selected_only)
        result = execute_simulation(conf)
    assert reads == [1]
    with xr.open_dataset(result.products[0]["path"]) as out, xr.open_dataset(source) as original:
        np.testing.assert_array_equal(out.instructional_scalar, original.instructional_scalar[1:2])
        np.testing.assert_array_equal(out.time, original.valid_time[1:2])


def test_native_cannot_replace_a_source_even_with_overwrite(tmp_path):
    source = create_first_run_input(tmp_path / "out/products/native.weather.model_grid.nc")
    original = _digest(source)
    conf = _configuration(tmp_path, {
        "weather": {"model": "arome", "files": str(source),
                    "variables": {"2d": ["instructional_scalar"]}},
    })
    with pytest.raises(ValueError, match="input"):
        execute_simulation(conf, ExecutionOptions.from_config(conf, overwrite=True))
    assert _digest(source) == original
    assert not (conf.output_dir / "run-status.yaml").exists()


def test_native_cannot_ignore_an_explicit_external_inventory(tmp_path):
    create_first_run_input(tmp_path / "scalar.nc")
    external = create_first_run_input(tmp_path / "external.nc")
    conf = _configuration(tmp_path, {
        "weather": {"model": "arome", "files": "./scalar.nc",
                    "variables": {"2d": ["instructional_scalar"]}},
    })
    with pytest.raises(ValueError, match="inventory"):
        execute_simulation(conf, input_files=(external,))
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("alias_kind", ["symlink", "hardlink"])
def test_native_log_alias_cannot_modify_a_source(tmp_path, monkeypatch, alias_kind):
    import frameit.utils.logging as frameit_logging

    source = create_first_run_input(tmp_path / "scalar.nc")
    original = _digest(source)
    conf = _configuration(tmp_path, {
        "weather": {"model": "arome", "files": "./scalar.nc",
                    "variables": {"2d": ["instructional_scalar"]}},
    })
    alias = conf.output_dir / "logs/native_0102T0304.log"
    alias.parent.mkdir(parents=True)
    if alias_kind == "symlink":
        alias.symlink_to(source)
    else:
        alias.hardlink_to(source)
    occupied = alias.with_name("native_0102T0304.1.log")
    occupied.write_text("An existing unrelated log.\n")
    monkeypatch.setattr(frameit_logging, "datetime", SimpleNamespace(
        now=lambda: datetime(2000, 1, 2, 3, 4)))

    result = execute_simulation(conf)

    assert _digest(source) == original
    assert result.ok and not Path(result.log_path).samefile(source)
    assert alias.samefile(source) and _digest(alias) == original
    assert occupied.read_text() == "An existing unrelated log.\n"
    assert "Run complete" in Path(result.log_path).read_text()
    _ordinary_reader(result.products[0]["path"], source, "instructional_scalar", "valid_time")


def test_native_auxiliary_clock_keeps_samples_and_native_indices(tmp_path):
    fixture = create_first_run_input(tmp_path / "fixture.nc")
    source = tmp_path / "scalar.nc"
    with xr.open_dataset(fixture, engine="netcdf4") as original:
        original.rename_dims({"valid_time": "sample"}).assign_coords(
            sample=("sample", [41, 42], {"long_name": "original sample identifier"})
        ).to_netcdf(source)
    conf = _configuration(tmp_path, {
        "weather": {"model": "arome", "files": "./scalar.nc",
                    "variables": {"2d": ["instructional_scalar"]}},
    })

    result = execute_simulation(conf)

    _ordinary_reader(result.products[0]["path"], source, "instructional_scalar", "valid_time")
    with xr.open_dataset(result.products[0]["path"], engine="netcdf4") as out:
        assert out.instructional_scalar.dims == ("time", "y", "x")
        assert out["sample"].dims == ("time",)
        np.testing.assert_array_equal(out["sample"], [41, 42])
        assert out["sample"].attrs == {"long_name": "original sample identifier"}


def test_native_grib_component_roundtrip(tmp_path):
    """A bound native GRIB component needs neither a companion nor excluded times."""
    import eccodes as ec

    source = tmp_path / "wind.grib"
    with source.open("wb") as stream:
        for hour in (0, 1, 2):
            message = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
            try:
                for key, value in {
                    "Ni": 3, "Nj": 2, "latitudeOfFirstGridPointInDegrees": -20.,
                    "latitudeOfLastGridPointInDegrees": -19.,
                    "longitudeOfFirstGridPointInDegrees": 60.,
                    "longitudeOfLastGridPointInDegrees": 62.,
                    "iDirectionIncrementInDegrees": 1., "jDirectionIncrementInDegrees": 1.,
                    "jScansPositively": 1, "dataDate": 20260101, "dataTime": 0,
                    "paramId": 131, "typeOfLevel": "isobaricInhPa", "level": 850,
                    "forecastTime": hour,
                }.items():
                    ec.codes_set(message, key, value)
                units = ec.codes_get(message, "units")
                ec.codes_set_values(message, np.arange(6, dtype=float) + 10 * hour)
                ec.codes_write(message, stream)
            finally:
                ec.codes_release(message)
    original = _digest(source)
    conf = _configuration(tmp_path, {
        "weather": {"model": "arome", "format": "grib", "files": "./wind.grib",
                    "variables": {"3d": ["u"]},
                    "time": {"values": ["2026-01-01T00:00:00", "2026-01-01T02:00:00"]}},
    })

    result = execute_simulation(conf)

    assert result.ok and result.n_files == 1
    assert len(result.products) == 1
    assert Path(result.products[0]["path"]).name == "native.weather.model_grid.nc"
    subprocess.run([sys.executable, "-c", """
import sys
import numpy as np
import xarray as xr
with xr.open_dataset(sys.argv[1], engine='netcdf4') as out:
    assert set(out.data_vars) == {'u'}
    assert out.u.shape == (2, 1, 2, 3)
    assert out.u.attrs['units'] == sys.argv[2]
    np.testing.assert_array_equal(out.u.values, [
        [[[0., 1., 2.], [3., 4., 5.]]], [[[20., 21., 22.], [23., 24., 25.]]]])
    np.testing.assert_array_equal(out.time.values, np.array(
        ['2026-01-01T00:00', '2026-01-01T02:00'], dtype='datetime64[ns]'))
assert not any(name == 'frameit' or name.startswith('frameit.') for name in sys.modules)
""", result.products[0]["path"], units], check=True, capture_output=True, text=True)
    assert _digest(source) == original
    assert not list(tmp_path.glob("*.idx"))


def test_native_croco_can_export_a_field_also_used_as_formula_support(tmp_path):
    from frameit.testing.numerical.test_croco_netcdf import croco_scene

    source = tmp_path / "ocean.nc"
    croco_scene().to_netcdf(source)
    original = _digest(source)
    conf = _configuration(tmp_path, {
        "water": {"model": "croco", "files": "./ocean.nc",
                  "variables": {"2d": ["zeta"], "3d": ["temp"],
                                "levels": {"indices": [1, 0]}}},
    })

    result = execute_simulation(conf)

    assert result.ok and len(result.products) == 1
    subprocess.run([sys.executable, "-c", """
import sys
import numpy as np
import xarray as xr
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source:
    assert set(out.data_vars) == {'temp', 'zeta'}
    np.testing.assert_array_equal(out.temp.values, source.temp.values[:, [1, 0]])
    np.testing.assert_array_equal(out.zeta.values, source.zeta.values)
    np.testing.assert_array_equal(out.s_rho.values, source.s_rho.values[[1, 0]])
    assert out.temp.attrs['units'] == source.temp.attrs['units']
    assert out.zeta.attrs['units'] == source.zeta.attrs['units']
    tokens = out.s_rho.attrs['formula_terms'].split()
    assert all(name in out for name in tokens[1::2])
    assert {'Cs_rho', 'h', 'hc'} <= set(out.variables)
assert not any(name == 'frameit' or name.startswith('frameit.') for name in sys.modules)
""", result.products[0]["path"], str(source)], check=True, capture_output=True, text=True)
    assert _digest(source) == original


@pytest.mark.parametrize("location", [
    "nested", "parent_alias", "parent_alias_traversal", "leaf_alias",
    "deduplicated_alias", "directory_alias", "excluded", "two_hop_alias",
    "two_hop_directory_alias", "excluded_two_hop_alias",
])
def test_native_cannot_replace_a_store_containing_source_paths(tmp_path, location):
    pytest.importorskip("zarr")
    target = tmp_path / "out/products/native.weather.model_grid.zarr"
    target.parent.mkdir(parents=True)
    xr.Dataset({"prior": ("x", [1.])}).to_zarr(
        target, zarr_format=3, consolidated=False)
    declaration = {"model": "arome", "variables": {"2d": ["instructional_scalar"]}}
    if location in {"nested", "parent_alias", "parent_alias_traversal"}:
        source = create_first_run_input(target / "source.nc")
        if location.startswith("parent_alias"):
            parent = target / "child" if location == "parent_alias_traversal" else target
            parent.mkdir(exist_ok=True)
            parent_alias = tmp_path / "source-view"
            parent_alias.symlink_to(parent, target_is_directory=True)
            source = parent_alias / ("../source.nc" if location == "parent_alias_traversal"
                                     else "source.nc")
        declaration["files"] = str(source)
    else:
        source = create_first_run_input(tmp_path / "source.nc")
        alias = target / "source-link.nc"
        if location == "excluded":
            create_first_run_input(alias)
            declaration.update(files=[str(source), str(alias)], exclude=[str(alias)])
        elif location == "directory_alias":
            alias.symlink_to(source.parent, target_is_directory=True)
            source = alias / source.name
            declaration["files"] = str(source)
        elif "two_hop" in location:
            directory = location == "two_hop_directory_alias"
            alias.symlink_to(source.parent if directory else source, target_is_directory=directory)
            declared = tmp_path / "current"
            declared.symlink_to(alias.relative_to(tmp_path), target_is_directory=directory)
            if location == "excluded_two_hop_alias":
                declaration.update(files=[str(source), str(declared)], exclude=[str(declared)])
            else:
                declaration["files"] = str(declared / source.name if directory else declared)
            source = declared / source.name if directory else declared
        else:
            alias.symlink_to(source)
            declaration["files"] = (str(alias) if location == "leaf_alias"
                                    else [str(source), str(alias)])
    original = _digest(source)
    before = {path.relative_to(target): _digest(path)
              for path in target.rglob("*") if path.is_file()}
    conf = _configuration(tmp_path, {"weather": declaration},
                          output={"format": "zarr", "overwrite": True})

    with pytest.raises(ValueError, match="source input"):
        execute_simulation(conf)

    assert source.is_file() and _digest(source) == original
    assert {path.relative_to(target): _digest(path)
            for path in target.rglob("*") if path.is_file()} == before
    assert not (conf.output_dir / "run-status.yaml").exists()
    assert not (conf.output_dir / "logs").exists()


@pytest.mark.parametrize("declared,engine", [
    ("netcdf", "zarr"), ("zarr", "netcdf4"),
])
def test_native_format_override_must_match_the_declared_format(tmp_path, declared, engine):
    source = create_first_run_input(tmp_path / "scalar.nc")
    original = _digest(source)
    conf = _configuration(tmp_path, {
        "weather": {"model": "arome", "files": "./scalar.nc",
                    "variables": {"2d": ["instructional_scalar"]}},
    }, output={"format": declared})

    with pytest.raises(ValueError, match=r"output\.format"):
        execute_simulation(conf, ExecutionOptions.from_config(conf, engine=engine))

    assert _digest(source) == original
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("declared,engine,suffix", [
    ("netcdf", "h5netcdf", ".nc"), ("zarr", "zarr", ".zarr"),
])
def test_native_same_format_options_preserve_product_paths(tmp_path, declared, engine, suffix):
    source = create_first_run_input(tmp_path / "scalar.nc")
    original = _digest(source)
    conf = _configuration(tmp_path, {
        "weather": {"model": "arome", "files": "./scalar.nc",
                    "variables": {"2d": ["instructional_scalar"]}},
    }, output={"format": declared})
    options = ExecutionOptions.from_config(conf, engine=engine, overwrite=True)

    for _ in range(2):
        result = execute_simulation(conf, options)
        product = Path(result.products[0]["path"])
        assert result.ok and product.name == f"native.weather.model_grid{suffix}"
        assert product.is_dir() == (declared == "zarr")
        subprocess.run([sys.executable, "-c", """
import sys
import numpy as np
import xarray as xr
options = {'consolidated': False} if sys.argv[1] == 'zarr' else {}
with xr.open_dataset(sys.argv[2], engine=sys.argv[1], **options) as out:
    with xr.open_dataset(sys.argv[3]) as source:
        assert set(out.data_vars) == {'instructional_scalar'}
        np.testing.assert_array_equal(out.instructional_scalar, source.instructional_scalar)
        assert out.instructional_scalar.attrs == source.instructional_scalar.attrs
assert not any(name == 'frameit' or name.startswith('frameit.') for name in sys.modules)
""", engine, str(product), str(source)], check=True, capture_output=True, text=True)
        status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
        resolved = yaml.safe_load((conf.output_dir / "resolved-config.yaml").read_text())
        assert status["state"] == "completed"
        assert status["products"][0]["path"] == f"products/{product.name}"
        assert resolved["output"]["format"] == declared
        assert _digest(source) == original
