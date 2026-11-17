"""C7 output-only contracts; compact fixtures are not real-producer qualification."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.configuration import to_runtime
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_croco_vectors import vector_scene


def configuration(tmp_path, model, fields, *, output=None, **extra):
    return SimulationConfig(**to_runtime({
        "schema_version": 3, "run": {"name": "My run-7"},
        "sources": {"sample": {"model": model, "files": str(tmp_path / "input.nc"),
                               "variables": fields}},
        "output": {"directory": str(tmp_path / "out"), **(output or {})},
        "resources": {"scheduler": "synchronous", "synchronous_export": True, "cpus": 1},
        **extra,
    }))


def mnh_scene():
    clock = np.array(["2026-01-01T00", "2026-01-01T01"], dtype="datetime64[ns]")
    coords = {"time": clock,
              "level": ("level", [10., 30.], {"axis": "Z", "units": "m"}),
              "level_w": ("level_w", [0., 20., 40.], {"axis": "Z", "units": "m"})}
    fields = {}
    for name, z, yd, xd, suffix, ys, xs in (
        ("T", "level", "nj", "ni", "", [10., 11.], [20., 21., 22.]),
        ("U", "level", "nj_u", "ni_u", "_u", [10., 11.], [19.5, 20.5, 21.5, 22.5]),
        ("V", "level", "nj_v", "ni_v", "_v", [9.5, 10.5, 11.5], [20., 21., 22.]),
        ("W", "level_w", "nj", "ni", "", [10., 11.], [20., 21., 22.]),
    ):
        coords[yd] = (yd, ys, {"units": "km"})
        coords[xd] = (xd, xs, {"units": "km"})
        lat = np.broadcast_to(np.array(ys)[:, None], (len(ys), len(xs))) - 30
        lon = np.broadcast_to(np.array(xs), lat.shape) + 40
        coords[f"latitude{suffix}"] = ((yd, xd), lat, {"units": "degrees_north",
                                                     "standard_name": "latitude"})
        coords[f"longitude{suffix}"] = ((yd, xd), lon, {"units": "degrees_east",
                                                      "standard_name": "longitude"})
        shape = (2, len(coords[z][1]), len(ys), len(xs))
        values = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
        values[0, 0, 0, 0] = np.nan
        fields[name] = (("time", z, yd, xd), values,
                        {"units": "K" if name == "T" else "cm s-1",
                         "coordinates": f"latitude{suffix} longitude{suffix}"})
    return xr.Dataset(fields, coords=coords)


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_mixed_mnh_grids_keep_native_samples_and_c7_axes(tmp_path, fmt):
    source = mnh_scene()
    source.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, "mesonh", {
        "3d": ["T", "U", "V", "W"], "levels": {"indices": [0]}},
        output={"format": fmt})
    result = execute_simulation(conf)
    assert len(result.products) == 1
    product = result.products[0]
    suffix = "nc" if fmt == "netcdf" else "zarr"
    assert Path(product["path"]).name == f"My run-7.sample.model_grid.{suffix}"
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
opener = xr.open_dataset if sys.argv[3] == 'netcdf' else xr.open_zarr
with opener(sys.argv[1],**({'consolidated':False} if sys.argv[3] == 'zarr' else {})) as out, \
     xr.open_dataset(sys.argv[2]) as src:
    assert set(out.data_vars) == {'T','U','V','W'}
    for name, dims, ys, xs, suffix in (
        ('T',('time','level','y','x'),'nj','ni',''),
        ('U',('time','level','y','x_u'),'nj_u','ni_u','_u'),
        ('V',('time','level','y_v','x'),'nj_v','ni_v','_v'),
        ('W',('time','level_w','y','x'),'nj','ni','')):
        axis = dims[1]
        assert out[name].dims == dims, (name, out[name].dims)
        assert out[name].dtype == np.float32
        np.testing.assert_array_equal(out[name], src[name].isel({axis:[0]}))
        np.testing.assert_array_equal(out[f'latitude{suffix}'],src[f'latitude{suffix}'])
        np.testing.assert_array_equal(out[f'longitude{suffix}'],src[f'longitude{suffix}'])
        for dim, native in ((dims[-2],ys),(dims[-1],xs)):
            np.testing.assert_array_equal(out[dim],np.arange(src.sizes[native]))
            np.testing.assert_array_equal(out[f'{native}_source_coordinate'],src[native])
            np.testing.assert_array_equal(out[f'{native}_source_native_index'],
                                          np.arange(src.sizes[native]))
            assert out[f'{native}_source_coordinate'].attrs['units'] == 'km'
        assert out[name].attrs['units'] == src[name].attrs['units']
        links = out[name].encoding['coordinates'].split()
        assert f'latitude{suffix}' in links and f'longitude{suffix}' in links
    np.testing.assert_array_equal(out.level_source_native_index,[0])
    np.testing.assert_array_equal(out.level_w_source_native_index,[0])
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], str(tmp_path / "input.nc"), fmt], check=True, capture_output=True,
        text=True)
    assert product["fields"]["U"]["dimensions"] == ["time", "level", "y", "x_u"]
    assert product["fields"]["U"]["units"] == "cm s-1"
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["products"][0]["fields"] == product["fields"]
    assert product["encoding"]["compression"] == {"level": 1, "coordinates": False}


def test_mixed_croco_axes_and_formula_dependencies(tmp_path):
    source = vector_scene()
    source.to_netcdf(tmp_path / "input.nc")
    result = execute_simulation(configuration(tmp_path, "croco", {
        "3d": ["temp", "u", "v", "tracer_w"], "levels": {"indices": [0]}}))
    with xr.open_dataset(result.products[0]["path"]) as out:
        for name, dims in (
            ("temp", ("time", "s_rho", "y_rho", "x_rho")),
            ("u", ("time", "s_rho", "y_rho", "x_u")),
            ("v", ("time", "s_rho", "y_v", "x_rho")),
            ("tracer_w", ("time", "s_w", "y_rho", "x_rho")),
        ):
            assert out[name].dims == dims
            np.testing.assert_array_equal(out[name], source[name].isel({dims[1]: [0]}))
        for axis in ("s_rho", "s_w"):
            assert all(n in out for n in out[axis].attrs["formula_terms"].split()[1::2])
            np.testing.assert_array_equal(out[f"{axis}_source_native_index"], [0])
        for suffix, native in (("rho", "rho"), ("u", "u"), ("v", "v")):
            np.testing.assert_array_equal(out[f"latitude_{suffix}"], source[f"lat_{native}"])
            assert (out[f"latitude_{suffix}"].attrs["units"]
                    == source[f"lat_{native}"].attrs["units"])


def test_writer_chunks_use_exported_dimensions(tmp_path):
    mnh_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, "mesonh", {"3d": ["T"]},
                         output={"writer": {"chunks": {"time": 1, "level": 1, "x": 2, "y": 1},
                                            "unlimited_time": False}},
                         metadata={"extra": {"frameit_version": "not-a-version",
                                             "product_type": "not-a-product"}})
    result = execute_simulation(conf)
    import netCDF4

    with netCDF4.Dataset(result.products[0]["path"]) as saved:
        assert saved["T"].chunking() == [1, 1, 1, 2]
        assert saved["T"].filters()["complevel"] == 1
        assert not saved["time"].filters()["zlib"]
        assert not saved.dimensions["time"].isunlimited()
    assert result.products[0]["encoding"]["chunks"]["T"] == [1, 1, 1, 2]
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert saved.attrs["frameit_version"] != "not-a-version"
        assert saved.attrs["product_type"] == "model_grid"
        annotations = json.loads(saved.attrs["frameit_user_metadata_json"])
        assert annotations["product_type"] == "not-a-product"


@pytest.mark.parametrize("fields", [["A"], ["B", "A"], ["A", "B"]])
def test_inventory_axis_identity_precedes_output_filtering(tmp_path, fields):
    scene = xr.Dataset({
        "A": (("time", "p1", "y", "x"), [[[[0., np.nan]], [[2., 3.]]]], {"units": "K"}),
        "B": (("time", "p2", "y", "x"), [[[[4., 5.]], [[6., 7.]]]], {"units": "K"}),
    }, coords={
        "time": [np.datetime64("2026-01-01", "ns")],
        "p1": ("p1", [850., 500.], {"axis": "Z", "standard_name": "air_pressure",
                                    "units": "hPa", "bounds": "p1_bounds"}),
        "p2": ("p2", [85000., 50000.], {"axis": "Z", "standard_name": "air_pressure",
                                        "units": "Pa"}),
        "p1_bounds": (("p1", "nv"), [[900., 800.], [600., 400.]], {"units": "hPa"}),
        "latitude": ("y", [-20.], {"units": "degrees_north"}),
        "longitude": ("x", [60., 61.], {"units": "degrees_east"}),
    })
    scene.to_netcdf(tmp_path / "input.nc")
    result = execute_simulation(configuration(
        tmp_path, "arome", {"3d": ["A", "B"], "levels": {"indices": [1]}},
        products={"model_grid": {"fields": {"sample": fields}}}))
    with xr.open_dataset(result.products[0]["path"]) as out:
        axis = out.A.dims[1]
        assert axis.startswith("pressure_") and axis != "pressure"
        assert out[axis].attrs["units"] == "hPa"
        np.testing.assert_array_equal(out[axis], [500.])
        np.testing.assert_array_equal(out[f"{axis}_source_native_index"], [1])
        np.testing.assert_array_equal(out[out[axis].attrs["bounds"]], [[600., 400.]])
        np.testing.assert_array_equal(out.A, scene.A.isel(p1=[1]))
        # A second run with a different field selection must use the same inventoried axis.
        conf = configuration(
            tmp_path, "arome", {"3d": ["B", "A"], "levels": {"indices": [1]}},
            output={"directory": str(tmp_path / "second")},
            products={"model_grid": {"fields": {"sample": ["A"]}}})
        second = execute_simulation(conf)
        with xr.open_dataset(second.products[0]["path"]) as other:
            assert other.A.dims == out.A.dims
            np.testing.assert_array_equal(other.A, out.A)
        if "B" in fields:
            assert out.B.dims[1] != axis
            assert out[out.B.dims[1]].attrs["units"] == "Pa"
            np.testing.assert_array_equal(out.B, scene.B.isel(p2=[1]))


@pytest.mark.parametrize("option", [{"engine": "netcdf4"}, {"unlimited_time": True},
                                   {"shards": {"x": 2}}, {"unknown": True}])
def test_inapplicable_writer_options_fail_even_with_a_track(tmp_path, option):
    fmt = "netcdf" if "shards" in option else "zarr"
    with pytest.raises(ValueError, match="NetCDF-only|Zarr-only|Unknown"):
        configuration(tmp_path, "mesonh", {"3d": ["T"]},
                      output={"format": fmt, "writer": option},
                      region={"center": {"latitude": -20, "longitude": 60}},
                      products={"model_grid": True, "track": True})


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_unknown_output_dimension_fails_before_any_publication(tmp_path, fmt):
    mnh_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, "mesonh", {"3d": ["T"]},
                         output={"format": fmt, "writer": {"chunks": {"ni": 2}}})
    with pytest.raises(ValueError, match="Unknown.*dimension"):
        execute_simulation(conf)
    assert not list((conf.output_dir / "products").glob("*"))


@pytest.mark.parametrize("collision", ["auxiliary", "json_annotation"])
def test_output_annotation_collisions_are_not_overwritten(tmp_path, collision):
    source = mnh_scene()
    if collision == "auxiliary":
        source["ni_source_coordinate"] = ("ni", [1., 2., 3.], {"units": "1"})
        fields = {"3d": ["T"], "2d": ["ni_source_coordinate"]}
    else:
        source.attrs = {"custom": {"value": 1}, "custom_json": "original"}
        # NetCDF cannot hold dictionaries; the generated-output boundary is exercised directly.
        from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf

        with pytest.raises(ValueError, match="collision"):
            write_dataset_netcdf(source, tmp_path / "result.nc",
                                 metadata=ExportMetadata("run", "", "", "", ""),
                                 product_type="model_grid")
        assert not (tmp_path / "result.nc").exists()
        return
    source.to_netcdf(tmp_path / "input.nc")
    with pytest.raises(ValueError, match="collision"):
        execute_simulation(configuration(tmp_path, "mesonh", fields))


def test_planned_product_paths_reject_collisions_and_symlinks(tmp_path):
    from frameit.utils.output_paths import OutputPaths

    products = OutputPaths(tmp_path)
    outside = tmp_path / "unrelated"
    outside.mkdir()
    (tmp_path / "products").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        products.planned_products([{"path": "products/run.sample.model_grid.nc"}])
    (tmp_path / "products").unlink()
    with pytest.raises(ValueError, match="collide"):
        products.planned_products([{"path": "products/field.nc"}, {"path": "products/field.nc"}])
    for unsafe in ("../field.nc", "/field.nc", "products/../../field.nc", "products/..\\field"):
        with pytest.raises(ValueError, match="Unsafe"):
            products.planned_products([{"path": unsafe}])


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_unrelated_existing_destination_is_not_a_replaceable_product(tmp_path, fmt):
    mnh_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, "mesonh", {"3d": ["T"]},
                         output={"format": fmt, "overwrite": True})
    suffix = "nc" if fmt == "netcdf" else "zarr"
    target = conf.output_dir / f"products/My run-7.sample.model_grid.{suffix}"
    target.parent.mkdir(parents=True)
    if fmt == "netcdf":
        xr.Dataset({"unrelated": ("x", [123.])}).to_netcdf(target)
        original = target.read_bytes()
    else:
        xr.Dataset({"unrelated": ("x", [123.])}).to_zarr(
            target, zarr_format=3, consolidated=False)
        (target / "private.txt").write_text("unrelated")
        original = (target / "private.txt").read_bytes()
    with pytest.raises(ValueError, match="unrelated|non-Zarr"):
        execute_simulation(conf)
    assert (target.read_bytes() if fmt == "netcdf"
            else (target / "private.txt").read_bytes()) == original


@pytest.mark.parametrize("native_labels", [False, True])
def test_moving_sample_geography_keeps_each_native_clock_and_position(tmp_path, native_labels):
    paths = []
    for hour in (0, 1):
        scene = mnh_scene()[["T"]].isel(time=[hour])
        scene = scene.assign_coords({
            name: scene[name].expand_dims(time=scene.time) + hour * .01
            for name in ("latitude", "longitude")})
        for name in ("latitude", "longitude"):
            scene[name].attrs = {"units": f"degrees_{'north' if name == 'latitude' else 'east'}",
                                 "standard_name": name}
        if not native_labels:
            scene = scene.drop_vars(["ni", "nj"])
        path = tmp_path / f"sample-{hour}.nc"
        scene.to_netcdf(path)
        paths.append(str(path))
    conf = configuration(tmp_path, "mesonh", {"3d": ["T"]}, sources={
        "sample": {"model": "mesonh", "files": paths, "variables": {"3d": ["T"]}}})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        assert out.T.dims == ("time", "level", "y", "x")
        assert out.latitude.dims == ("time", "y", "x")
        np.testing.assert_array_equal(out.time, np.array(
            ["2026-01-01T00", "2026-01-01T01"], dtype="datetime64[ns]"))
        np.testing.assert_array_equal(out.latitude[:, 0, 0], [-20., -19.99])
        for hour, path in enumerate(paths):
            with xr.open_dataset(path) as original:
                np.testing.assert_array_equal(out.T[hour:hour+1], original.T)
                np.testing.assert_array_equal(out.latitude[hour:hour+1], original.latitude)
                np.testing.assert_array_equal(out.longitude[hour:hour+1], original.longitude)


def test_sharded_zarr_fields_and_netcdf_track_have_separate_encoding(tmp_path):
    from frameit.testing.numerical.test_v3_regions import scalar_scene

    scalar_scene(tmp_path / "input.nc", angle=0)
    conf = configuration(tmp_path, "mesonh", {"2d": ["scalar"]},
                         output={"format": "zarr", "writer": {
                             "chunks": {"time": 1, "y": 2, "x": 2},
                             "shards": {"time": 2, "y": 4, "x": 4}}},
                         region={"center": {"latitude": -20, "longitude": 60},
                                 "width_km": {"x": 2, "y": 2}},
                         products={"model_grid": True, "track": True})
    result = execute_simulation(conf)
    assert {p["role"] for p in result.products} == {"model_grid", "track"}
    paths = {p["role"]: p["path"] for p in result.products}
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr, zarr
with xr.open_zarr(sys.argv[1],consolidated=False) as out, xr.open_dataset(sys.argv[2]) as track:
    assert out.scalar.dims == ('time','y','x')
    np.testing.assert_array_equal(out.x,[0,1,2])
    np.testing.assert_array_equal(out.ni_source_native_index,[[2,3,4]]*3)
    assert out.latitude.dims == ('time','y','x')
    assert out.scalar.values[0,1,1] == 0
    assert np.isnan(out.scalar.values[:,0,1]).all()
    np.testing.assert_array_equal(track.latitude,[-20.]*3)
    np.testing.assert_array_equal(track.longitude,[60.]*3)
    assert track.latitude.attrs['units'] == 'degrees_north'
    assert track.time.encoding['calendar'] == 'proleptic_gregorian'
array = zarr.open_group(sys.argv[1],mode='r')['scalar']
assert array.chunks == (1,2,2) and array.shards == (2,4,4)
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", paths["model_grid"], paths["track"]], check=True, capture_output=True, text=True)
    metadata = json.loads((Path(paths["model_grid"]) / "scalar/zarr.json").read_text())
    assert metadata["codecs"][0]["name"] == "sharding_indexed"
    assert metadata["codecs"][0]["configuration"]["codecs"][-1]["configuration"]["level"] == 1


def test_polar_colliding_vertical_axes_keep_each_field_support(tmp_path):
    files = []
    for name, levels in (("A", [10., 30.]), ("B", [20., 40.])):
        scene = mnh_scene()[["T"]].rename(T=name).assign_coords(
            level=("level", levels, {"units": "m", "axis": "Z"}))
        path = tmp_path / f"{name}.nc"
        scene.to_netcdf(path)
        files.append(str(path))
    conf = configuration(tmp_path, "mesonh", {}, sources={"sample": {
        "model": "mesonh", "files": files,
        "variables": {"3d": ["A", "B"], "levels": {"indices": [1]}},
        "field_metadata": {"A": {"kind": "continuous"}, "B": {"kind": "continuous"}},
    }}, region={"center": {"latitude": -19.5, "longitude": 61.}},
        products={"polar": {"radius_km": 1., "azimuth_count": 4}})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        axes = [out[name].dims[1] for name in ("A", "B")]
        assert axes[0] != axes[1] and all(axis.startswith("level_") for axis in axes)
        for name, axis, label in zip(("A", "B"), axes, (30., 40.), strict=True):
            assert out[name].dims == ("time", axis, "radius", "azimuth")
            np.testing.assert_array_equal(out[axis], [label])
            np.testing.assert_array_equal(out[f"{axis}_source_native_index"], [1])
            assert out[f"{name}_support_fraction"].dims == out[name].dims
            assert out[name].attrs["polar_numeric_types"]
        assert out.radius.attrs["units"] == "km"
        assert out.azimuth.attrs["units"] == "rad"
        assert out.azimuth_degrees.attrs["units"] == "degrees"
        assert out.latitude.dims == ("time", "radius", "azimuth")
        np.testing.assert_array_equal(out.center_latitude, [-19.5, -19.5])


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_polar_qualification_keeps_values_masks_and_inventory_names(tmp_path, fmt):
    import hashlib

    files = []
    for name, labels in (("A", [10., 30.]), ("B", [20., 40.])):
        scene = mnh_scene()[["T"]].rename(T=name).assign_coords(
            level=("level", labels, {"units": "m", "axis": "Z"}))
        scene.level.attrs["bounds"] = "level_bounds"
        scene = scene.assign_coords(level_bounds=(
            ("level", "nv"), [[v - 10., v + 10.] for v in labels], {"units": "m"}))
        scene[name].values[:, 1] = 0. if name == "A" else 7.
        if name == "B":
            scene[name].values[1, 1] = np.nan
        path = tmp_path / f"{name}.nc"
        scene.to_netcdf(path)
        files.append(str(path))
    hashes = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}
    axes = {}
    for index, selected in enumerate((["A"], ["B", "A"], ["A", "B"], ["B"])):
        conf = configuration(tmp_path, "mesonh", {}, sources={"sample": {
            "model": "mesonh", "files": files,
            "variables": {"3d": ["A", "B"], "levels": {"indices": [1]}},
            "field_metadata": {"A": {"kind": "continuous"}, "B": {"kind": "continuous"}},
        }}, region={"center": {"latitude": -19.5, "longitude": 61.}},
            products={"polar": {"radius_km": 1., "azimuth_count": 4,
                                "fields": {"sample": selected}}},
            output={"format": fmt, "directory": str(tmp_path / f"out-{index}")})
        result = execute_simulation(conf)
        assert len(result.products) == 1
        product = result.products[0]
        opener = xr.open_dataset if fmt == "netcdf" else xr.open_zarr
        with opener(product["path"], **({"consolidated": False} if fmt == "zarr" else {})) as out:
            for name in selected:
                axis = out[name].dims[1]
                assert axis.startswith("level_")
                assert axes.setdefault(name, axis) == axis
                assert product["fields"][name]["dimensions"] == list(out[name].dims)
                planned = conf.simulation_parameter["request_plan"]["products"][0]
                assert planned["dimensions"][name] == list(out[name].dims)
        subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
opener = xr.open_dataset if sys.argv[2] == 'netcdf' else xr.open_zarr
selected = json.loads(sys.argv[3])
with opener(sys.argv[1],**({'consolidated':False} if sys.argv[2] == 'zarr' else {})) as ds:
    assert {n for n in ds.data_vars if ds[n].attrs.get('frameit_role')
            != 'interpolation_quality'} == set(selected)
    expected_time = np.array(['2026-01-01T00','2026-01-01T01'],dtype='datetime64[ns]')
    np.testing.assert_array_equal(ds.time,expected_time)
    np.testing.assert_array_equal(ds.center_time,expected_time)
    np.testing.assert_array_equal(ds.center_latitude,[-19.5,-19.5])
    np.testing.assert_array_equal(ds.center_longitude,[61.,61.])
    assert ds.time.encoding['calendar'] == 'proleptic_gregorian'
    np.testing.assert_array_equal(ds.radius,[0.,1.])
    np.testing.assert_array_equal(ds.azimuth_degrees,[0.,90.,180.,270.])
    assert ds.radius.attrs['units'] == 'km' and ds.azimuth.attrs['units'] == 'rad'
    assert ds.azimuth_degrees.attrs['units'] == 'degrees'
    assert ds.latitude.dims == ds.longitude.dims == ('time','radius','azimuth')
    registry = json.loads(ds.attrs['frameit_output_coordinates_json'])
    for name in selected:
        value = ds[name]; axis = value.dims[1]
        assert value.dims == ('time',axis,'radius','azimuth')
        assert value.dtype == np.float32 and value.attrs['units'] == 'K'
        np.testing.assert_array_equal(ds[axis],[30.] if name == 'A' else [40.])
        assert ds[axis].attrs['units'] == 'm'
        np.testing.assert_array_equal(ds[f'{axis}_source_native_index'],[1])
        bounds = ds[axis].attrs['bounds']
        assert bounds.startswith('level_bounds_') and ds[bounds].dims == (axis,'nv')
        np.testing.assert_array_equal(ds[bounds],[[20.,40.]] if name == 'A' else [[30.,50.]])
        # CF bounds inherit their coordinate's units when NetCDF elides a duplicate.
        assert ds[bounds].attrs.get('units',ds[axis].attrs['units']) == 'm'
        assert any(item['dimensions'].get('level') == axis for item in registry.values())
        expected = np.zeros((2,1,2,4),dtype=np.float32)
        status = np.zeros(expected.shape,dtype=np.uint8)
        support = np.ones(expected.shape)
        if name == 'B':
            expected[0] = 7.; expected[1] = np.nan
            status[1] = 2; support[1] = 0.
        np.testing.assert_allclose(value,expected,rtol=0,atol=1e-6,equal_nan=True)
        np.testing.assert_array_equal(ds[f'{name}_support_fraction'],support)
        np.testing.assert_array_equal(ds[f'{name}_interpolation_status'],status)
        np.testing.assert_array_equal(ds[f'{name}_valid'],status == 0)
        np.testing.assert_array_equal(ds[f'{name}_full_ring_valid'],(status == 0).all(-1))
        np.testing.assert_array_equal(ds[f'{name}_geometry_mapped'],1)
        flags = ds[f'{name}_interpolation_status']
        np.testing.assert_array_equal(flags.attrs['flag_values'],[0,1,2,3,4])
        assert 'missing_source_data' in flags.attrs['flag_meanings']
        assert flags.dims == value.dims
        assert all(n in ds for n in value.attrs['ancillary_variables'].split())
        numeric = json.loads(value.attrs['polar_numeric_types'])[name]
        assert numeric == {'prepared_dtype':'float32','evaluation_dtype':'float32',
                           'conversion':'none'}
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], fmt, json.dumps(selected)], check=True, capture_output=True, text=True)
        provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
        records = provenance["sources"]["sample"]["polar"]["records"]
        assert {r["field"] for r in records} == set(selected)
        assert all(r["levels"]["source_native_indices"] == [1] for r in records)
        assert all(r["levels"]["values"] == ([30.] if r["field"] == "A" else [40.])
                   for r in records)
        assert {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files} == hashes
    assert axes["A"] != axes["B"]


@pytest.mark.parametrize("engine", ["netcdf4", "h5netcdf"])
def test_lossless_writer_discards_source_packing_not_float_precision(tmp_path, engine):
    from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf

    source = xr.Dataset({"precise": ("x", np.array([0., 1.123456789012345, np.nan],
                                                  dtype=np.float64), {"units": "1"})},
                        coords={"precise_coordinate": ("x", [0., 1.123456789012345, 2.])})
    source.precise.encoding.update(dtype="int16", scale_factor=.01, add_offset=1.)
    source.precise_coordinate.encoding.update(dtype="int16", scale_factor=.01, add_offset=1.)
    target = write_dataset_netcdf(
        source, tmp_path / "precise.nc", metadata=ExportMetadata("run", "", "", "", ""),
        product_type="model_grid", engine=engine, unlimited_time=False)
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    assert out.precise.dtype == np.float64
    np.testing.assert_array_equal(out.precise,[0.,1.123456789012345,np.nan])
    np.testing.assert_array_equal(out.precise_coordinate,[0.,1.123456789012345,2.])
    assert 'scale_factor' not in out.precise.encoding
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", str(target)], check=True, capture_output=True, text=True)
    assert source.precise.encoding["dtype"] == "int16"


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_no_clobber_keeps_source_and_all_existing_outputs(tmp_path, fmt):
    import hashlib

    source = tmp_path / "input.nc"
    mnh_scene().to_netcdf(source)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    conf = configuration(tmp_path, "mesonh", {"3d": ["T"]}, output={"format": fmt})
    execute_simulation(conf)
    before = {str(p.relative_to(conf.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in conf.output_dir.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError, match="overwrite=False"):
        execute_simulation(conf)
    after = {str(p.relative_to(conf.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in conf.output_dir.rglob("*") if p.is_file()}
    assert before == after
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original


@pytest.mark.parametrize("engine", ["netcdf4", "h5netcdf", "zarr"])
def test_decoded_packed_fill_does_not_mask_physical_zero(tmp_path, engine):
    import hashlib
    from copy import deepcopy

    from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf
    from frameit.io.zarr_export import write_dataset_zarr

    path = tmp_path / "packed.nc"
    seed = xr.Dataset({
        "sample": ("point", [0., 1., np.nan], {"units": "m s-1"}),
        "integer": ("point", np.array([0, 1, 2], dtype=np.int16), {"units": "1"}),
    }, coords={
        "physical": ("point", [0., 1., np.nan], {"units": "m"}),
        "physical_source_coordinate": ("point", [0., 1., np.nan], {"units": "m"}),
        "time": np.array(["2000-01-01T00", "2000-01-01T01", "2000-01-01T02"],
                         dtype="datetime64[ns]"),
    })
    for name in ("sample", "physical", "physical_source_coordinate"):
        seed[name].encoding.update(dtype="int16", scale_factor=1., add_offset=-5., _FillValue=0)
    seed.time.encoding.update(dtype="int64", units="hours since 2000-01-01",
                              calendar="proleptic_gregorian")
    seed.to_netcdf(path)
    path.chmod(0o444)
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    with xr.open_dataset(path) as source:
        source.load()
        before = source.copy(deep=True)
        encodings = {name: deepcopy(value.encoding) for name, value in source.variables.items()}
        for name in ("sample", "physical", "physical_source_coordinate"):
            np.testing.assert_array_equal(source[name], [0., 1., np.nan])
            assert source[name].encoding["_FillValue"] == 0
            assert source[name].encoding["dtype"] == np.dtype("int16")
        options = {"metadata": ExportMetadata("run", "", "", "", ""),
                   "product_type": "model_grid", "compress_coords": False}
        if engine == "zarr":
            target = write_dataset_zarr(source, tmp_path / "output.zarr", **options)
        else:
            target = write_dataset_netcdf(source, tmp_path / "output.nc",
                                          engine=engine, **options)
        xr.testing.assert_identical(source, before)
        assert all(source[name].encoding == encoding for name, encoding in encodings.items())
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
engine = sys.argv[3]
out = (xr.open_zarr(sys.argv[1],consolidated=False) if engine == 'zarr'
       else xr.open_dataset(sys.argv[1],engine=engine))
with out, xr.open_dataset(sys.argv[2]) as src:
    for name in ('sample','physical','physical_source_coordinate'):
        np.testing.assert_array_equal(out[name],[0.,1.,np.nan])
        assert out[name].dtype == np.float64 and out[name].attrs == src[name].attrs
        assert np.isnan(out[name].encoding.get('_FillValue',np.nan))
        assert not {'scale_factor','add_offset'} & out[name].encoding.keys()
    np.testing.assert_array_equal(out.integer,[0,1,2])
    assert out.integer.dtype == np.int16 and out.integer.attrs['units'] == '1'
    np.testing.assert_array_equal(out.time,src.time)
    assert out.time.dtype == src.time.dtype == np.dtype('datetime64[ns]')
    assert out.time.encoding['calendar'] == src.time.encoding['calendar']
    assert out.time.encoding['units'] in {
        'hours since 2000-01-01','hours since 2000-01-01 00:00:00'}
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", str(target), str(path), engine], check=True, capture_output=True, text=True)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original


def test_distinct_native_grids_with_equal_shape_never_align_by_position(tmp_path):
    files = []
    for name, shift in (("A", 0.), ("B", .1)):
        scene = mnh_scene()[["T"]].rename(T=name).assign_coords(
            latitude=mnh_scene().latitude + shift)
        scene.latitude.attrs = {"units": "degrees_north", "standard_name": "latitude"}
        path = tmp_path / f"{name}.nc"
        scene.to_netcdf(path)
        files.append(str(path))
    conf = configuration(tmp_path, "mesonh", {}, sources={"sample": {
        "model": "mesonh", "files": files, "variables": {"3d": ["A", "B"]}}})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        assert set(out.A.dims[-2:]).isdisjoint(out.B.dims[-2:])
        assert all(dim.startswith(("y_", "x_")) for dim in out.A.dims[-2:])
        for name, path in zip(("A", "B"), files, strict=True):
            with xr.open_dataset(path) as src:
                np.testing.assert_array_equal(out[name], src[name])
                latitude = next(n for n in out[name].encoding["coordinates"].split()
                                if n.startswith("latitude"))
                np.testing.assert_array_equal(out[latitude], src.latitude)
                for dim in out[name].dims[-2:]:
                    np.testing.assert_array_equal(out[dim], np.arange(out.sizes[dim]))


def test_colliding_hybrid_coefficients_keep_their_own_formula_links(tmp_path):
    paths = []
    for name, labels, coefficients in (("A", [1, 2], [.1, .2]), ("B", [3, 4], [.3, .4])):
        ds = xr.Dataset({name: (("time", "hybrid", "y", "x"), np.ones((1, 2, 1, 2)),
                                {"units": "K"})}, coords={
            "time": [np.datetime64("2026-01-01", "ns")],
            "hybrid": ("hybrid", labels, {"axis": "Z", "units": "1",
                "standard_name": "atmosphere_hybrid_sigma_pressure_coordinate",
                "formula_terms": "a: a b: b ps: ps p0: p0"}),
            "a": ("hybrid", coefficients, {"units": "1"}),
            "b": ("hybrid", [0., 0.], {"units": "1"}),
            "p0": ((), 100000., {"units": "Pa"}),
            "latitude": ("y", [-20.], {"units": "degrees_north"}),
            "longitude": ("x", [60., 61.], {"units": "degrees_east"}),
        })
        if name == "A":
            ds["ps"] = (("time", "y", "x"), np.full((1, 1, 2), 100000.), {"units": "Pa"})
        path = tmp_path / f"{name}.nc"
        ds.to_netcdf(path)
        paths.append(str(path))
    for fmt in ("netcdf", "zarr"):
        conf = configuration(tmp_path, "arome", {}, sources={"sample": {
            "model": "arome", "files": paths, "variables": {"3d": ["A", "B"],
                                                           "levels": {"indices": [1]}}}},
            output={"format": fmt, "directory": str(tmp_path / fmt)})
        result = execute_simulation(conf)
        opener = xr.open_dataset if fmt == "netcdf" else xr.open_zarr
        with opener(result.products[0]["path"], **(
                {"consolidated": False} if fmt == "zarr" else {})) as out:
            for name, label, coefficient in (("A", 2, .2), ("B", 4, .4)):
                axis = out[name].dims[1]
                assert axis.startswith("hybrid_")
                np.testing.assert_array_equal(out[axis], [label])
                terms = out[axis].attrs["formula_terms"].split()
                assert all(n in out for n in terms[1::2])
                assert terms[::2] == ["a:", "b:", "ps:", "p0:"]
                a_name, b_name = terms[1], terms[3]
                assert a_name.startswith("a_") and b_name.startswith("b_")
                np.testing.assert_array_equal(out[a_name], [coefficient])
                assert out[a_name].dims == (axis,)
                assert out[b_name].dims == (axis,)
                assert out[axis].attrs["formula_terms"] == (
                    f"a: {a_name} b: {b_name} ps: ps p0: p0")
                np.testing.assert_array_equal(out[b_name], [0.])
                assert out[a_name].attrs["units"] == out[b_name].attrs["units"] == "1"
                assert out.ps.attrs["units"] == out.p0.attrs["units"] == "Pa"
                np.testing.assert_allclose(
                    out[a_name] * out.p0 + out[b_name] * out.ps,
                    20000. if name == "A" else 40000., rtol=0, atol=1e-10)
        subprocess.run([sys.executable, "-c", """
import re, sys, numpy as np, xarray as xr
out = (xr.open_dataset(sys.argv[1]) if sys.argv[2] == 'netcdf'
       else xr.open_zarr(sys.argv[1],consolidated=False))
with out:
    for name, expected in (('A',20000.),('B',40000.)):
        axis = out[name].dims[1]
        text = out[axis].attrs['formula_terms']
        terms = dict(re.findall(r'([^\\s:]+)\\s*:\\s*([^\\s:]+)',text))
        assert set(terms) == {'a','b','ps','p0'} and len(text.split()) == 8
        a,b,ps,p0 = (out[terms[key]] for key in ('a','b','ps','p0'))
        assert a.dims == b.dims == (axis,)
        assert a.attrs['units'] == b.attrs['units'] == '1'
        assert ps.attrs['units'] == p0.attrs['units'] == 'Pa'
        np.testing.assert_allclose(a*p0+b*ps,expected,rtol=0,atol=1e-10)
        np.testing.assert_array_equal(out[name],1.)
        np.testing.assert_array_equal(out[axis+'_source_native_index'],[1])
        assert out[name].attrs['units'] == 'K'
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], fmt], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("location", ["attrs", "encoding"])
def test_cf_reference_grammars_preserve_labels_methods_and_comments(location):
    from frameit.io.netcdf_export import _rename_coordinate_links

    names = {name: f"{name}_gridA" for name in (
        "a", "b", "ps", "p0", "area", "volume", "latitude", "longitude", "bounds",
        "quality", "crs", "mean", "comment")}
    ds = xr.Dataset({"q": ("x", [0., 1.])}, coords={stored: 0 for stored in names.values()})
    references = {
        "coordinates": "latitude longitude", "bounds": "bounds",
        "formula_terms": "a: a b: b ps: ps p0: p0",
        "cell_measures": "area: area volume: volume",
        "ancillary_variables": "quality", "grid_mapping": "crs: latitude longitude",
        "cell_methods": "latitude: mean (interval: 1 degree comment: area a mean) area: mean",
    }
    getattr(ds.q, location).update(references)
    ds.q.attrs["long_name"] = "a mean area comment"
    _rename_coordinate_links(ds, names)
    assert {key: getattr(ds.q, location)[key] for key in references} == {
        "coordinates": "latitude_gridA longitude_gridA", "bounds": "bounds_gridA",
        "formula_terms": "a: a_gridA b: b_gridA ps: ps_gridA p0: p0_gridA",
        "cell_measures": "area: area_gridA volume: volume_gridA",
        "ancillary_variables": "quality_gridA",
        "grid_mapping": "crs_gridA: latitude_gridA longitude_gridA",
        "cell_methods": "latitude_gridA: mean (interval: 1 degree comment: area a mean) area: mean",
    }
    assert ds.q.attrs["long_name"] == "a mean area comment"


def test_cell_measure_labels_survive_qualified_variables_in_both_containers(tmp_path):
    from frameit.io.netcdf_export import (
        ExportMetadata,
        _rename_coordinate_links,
        write_dataset_netcdf,
    )
    from frameit.io.zarr_export import write_dataset_zarr

    source = xr.Dataset({"q": ("x", [0., 1.], {
        "units": "K", "cell_measures": "area: area volume: volume"})}, coords={
            "area": ("x", [2., 3.], {"units": "m2"}),
            "volume": ("x", [4., 5.], {"units": "m3"})})
    names = {"area": "area_gridA", "volume": "volume_gridA"}
    dataset = source.rename(names)
    _rename_coordinate_links(dataset, names)
    assert dataset.q.attrs["cell_measures"] == "area: area_gridA volume: volume_gridA"
    assert source.q.attrs["cell_measures"] == "area: area volume: volume"
    for fmt in ("netcdf", "zarr"):
        writer = write_dataset_netcdf if fmt == "netcdf" else write_dataset_zarr
        target = writer(dataset, tmp_path / f"cells.{fmt}", product_type="model_grid",
                        metadata=ExportMetadata("run", "", "", "", ""))
        subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
out = (xr.open_dataset(sys.argv[1]) if sys.argv[2] == 'netcdf'
       else xr.open_zarr(sys.argv[1],consolidated=False))
with out:
    assert out.q.attrs['cell_measures'] == 'area: area_gridA volume: volume_gridA'
    np.testing.assert_array_equal(out.q,[0.,1.])
    np.testing.assert_array_equal(out.area_gridA,[2.,3.])
    np.testing.assert_array_equal(out.volume_gridA,[4.,5.])
    assert out.area_gridA.dims == out.volume_gridA.dims == out.q.dims == ('x',)
    assert out.area_gridA.attrs['units'] == 'm2'
    assert out.volume_gridA.attrs['units'] == 'm3'
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", str(target), fmt], check=True, capture_output=True, text=True)


def test_failed_later_publication_records_only_the_complete_product(tmp_path, monkeypatch):
    from frameit.io import netcdf_export
    from frameit.testing.numerical.test_v3_regions import scalar_scene

    sources = {
        "weather": scalar_scene(tmp_path / "weather.nc", angle=0),
        "water": scalar_scene(tmp_path / "water.nc", model="nemo", angle=0),
    }
    conf = configuration(tmp_path, "mesonh", {}, sources=sources)
    original = netcdf_export.write_dataset_netcdf
    count = 0

    def disk_full(ds, path, **options):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("disk full")
        return original(ds, path, **options)

    monkeypatch.setattr(netcdf_export, "write_dataset_netcdf", disk_full)
    with pytest.raises(OSError, match="disk full"):
        execute_simulation(conf)
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["state"] == "failed"
    assert len(status["products"]) == 1
    product = status["products"][0]
    assert product["source"] == "weather"
    assert product["path"] == "products/My run-7.weather.model_grid.nc"
    with xr.open_dataset(conf.output_dir / product["path"]) as out:
        assert product["fields"]["scalar"]["dimensions"] == list(out.scalar.dims)
    assert len(list((conf.output_dir / "products").iterdir())) == 1


def test_no_export_does_not_claim_planned_products(tmp_path):
    mnh_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, "mesonh", {"3d": ["T"]})
    result = execute_simulation(conf, ExecutionOptions.from_config(conf, export_netcdf=False))
    assert result.products == []
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["products"] == []
    assert not list(conf.output_dir.glob("products/*"))


@pytest.mark.parametrize("native_axis,exported_axis,label,units", [
    ("isobaric", "pressure", 850, "hPa"),
    ("heightAboveGround", "height_above_ground", 10, "m"),
])
def test_grib_preview_and_publication_use_c7_axes(
        tmp_path, native_axis, exported_axis, label, units):
    from frameit.core.coupled import bind_sources
    from frameit.testing.numerical.test_v3_grib_reads import write_messages

    path = write_messages(tmp_path / "input.grib", [
        {"level": label, "group": native_axis, "member": member,
         "param": 130 if native_axis == "heightAboveGround" else 131} for member in (0, 1)])
    field = "t" if native_axis == "heightAboveGround" else "u"
    conf = configuration(tmp_path, "arome", {}, sources={"sample": {
        "model": "arome", "files": str(path), "variables": {
            "3d": [field], "levels": {"indices": [0]}}}})
    bind_sources(conf)
    planned = conf.simulation_parameter["request_plan"]["products"][0]
    assert planned["dimensions"][field] == ["time", "number", exported_axis, "y", "x"]
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        assert out[field].dims == ("time", "number", exported_axis, "y", "x")
        np.testing.assert_array_equal(out[exported_axis], [label])
        assert out[exported_axis].attrs["units"] == units
        np.testing.assert_array_equal(out[f"{exported_axis}_source_native_index"], [0])
        np.testing.assert_array_equal(out.number, [0, 1])
        expected = [[0., 1000 + label + 1, np.nan], [9999., 1000 + label + 4, 1000 + label + 5]]
        np.testing.assert_array_equal(out[field][0, 0, 0], expected)
        np.testing.assert_array_equal(out[field][0, 1, 0], expected)


def test_mixed_croco_zarr_is_readable_with_native_formula_support(tmp_path):
    import hashlib

    source = tmp_path / "input.nc"
    vector_scene().to_netcdf(source)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    conf = configuration(tmp_path, "croco", {
        "2d": ["zeta"], "3d": ["temp", "u", "v", "tracer_w"], "levels": {"indices": [0]}},
        output={"format": "zarr", "writer": {
            "chunks": {"time": 1, "s_rho": 1, "s_w": 1, "y_rho": 2, "x_rho": 2,
                       "x_u": 2, "y_v": 2},
            "shards": {"time": 2, "y_rho": 4, "x_rho": 4, "x_u": 4, "y_v": 4}}})
    result = execute_simulation(conf)
    assert len(result.products) == 1
    product = result.products[0]
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr, zarr
with xr.open_zarr(sys.argv[1],consolidated=False) as ds, xr.open_dataset(sys.argv[2]) as src:
    assert set(ds.data_vars) == {'zeta','temp','u','v','tracer_w'}
    for name, dims in (
        ('temp',('time','s_rho','y_rho','x_rho')),
        ('u',('time','s_rho','y_rho','x_u')),
        ('v',('time','s_rho','y_v','x_rho')),
        ('tracer_w',('time','s_w','y_rho','x_rho'))):
        assert ds[name].dims == dims
        np.testing.assert_array_equal(ds[name],src[name].isel({dims[1]:[0]}))
        assert ds[name].dtype == src[name].dtype
        assert ds[name].attrs['units'] == src[name].attrs['units']
    np.testing.assert_array_equal(ds.zeta,src.zeta)
    np.testing.assert_array_equal(ds.time,src.time)
    np.testing.assert_array_equal(ds.scrum_time,src.scrum_time)
    for axis in ('s_rho','s_w'):
        np.testing.assert_array_equal(ds[axis],src[axis][:1])
        np.testing.assert_array_equal(ds[f'{axis}_source_native_index'],[0])
        assert all(n in ds for n in ds[axis].attrs['formula_terms'].split()[1::2])
    for native, stored in (('eta_rho','y_rho'),('xi_rho','x_rho'),
                           ('xi_u','x_u'),('eta_v','y_v')):
        np.testing.assert_array_equal(ds[stored],np.arange(src.sizes[native]))
        np.testing.assert_array_equal(ds[f'{native}_source_coordinate'],src[native])
        np.testing.assert_array_equal(ds[f'{native}_source_native_index'],
                                      np.arange(src.sizes[native]))
    for suffix in ('rho','u','v'):
        np.testing.assert_array_equal(ds[f'latitude_{suffix}'],src[f'lat_{suffix}'])
        np.testing.assert_array_equal(ds[f'longitude_{suffix}'],src[f'lon_{suffix}'])
        assert ds[f'latitude_{suffix}'].attrs['units'] == src[f'lat_{suffix}'].attrs['units']
    physical = ds.zeta+(ds.zeta+ds.h)*(ds.hc*ds.s_rho+ds.h*ds.Cs_rho)/(ds.hc+ds.h)
    np.testing.assert_allclose(physical.isel(time=0,s_rho=0),-16.22,rtol=0,atol=1e-12)
array = zarr.open_group(sys.argv[1],mode='r')['temp']
assert array.chunks == (1,1,2,2) and array.shards == (2,1,4,4)
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], str(source)], check=True, capture_output=True, text=True)
    assert product["encoding"]["chunks"]["temp"] == [1, 1, 2, 2]
    assert product["encoding"]["shards"]["temp"] == [2, 1, 4, 4]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("cropped", [False, True], ids=["full-domain", "fixed-crop"])
def test_instructional_rectilinear_model_grid_uses_native_crop_axes(tmp_path, fmt, cropped):
    import hashlib

    from frameit.testing.documentation_example import create_first_run_input

    source = create_first_run_input(tmp_path / "data/first-run.nc")
    source.chmod(0o444)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    document = {
        "schema_version": 3, "run": {"name": "fixed-region"},
        "sources": {"atmosphere": {
            "model": "arome", "files": "./data/first-run.nc",
            "variables": {"2d": ["instructional_scalar"]}}},
        "output": {"directory": "./output", "format": fmt},
        "resources": {"cpus": 1, "scheduler": "synchronous", "native_threads": 1,
                      "synchronous_export": True, "export_workers": 1},
    }
    if cropped:
        document["region"] = {"center": {"latitude": -20, "longitude": 60},
                              "width_km": {"x": 4, "y": 4}}
    request = tmp_path / "frameit.yaml"
    request.write_text(yaml.safe_dump(document))
    conf = SimulationConfig.from_yaml_with_model_preset(request)
    result = execute_simulation(conf)
    assert len(result.products) == 1
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original
    product = result.products[0]
    assert product["source"] == "atmosphere" and product["role"] == "model_grid"
    assert product["fields"]["instructional_scalar"]["dimensions"] == ["time", "y", "x"]
    assert product["dimensions"]["instructional_scalar"] == ["time", "y", "x"]
    planned = conf.simulation_parameter["request_plan"]["products"][0]
    assert planned["dimensions"]["instructional_scalar"] == ["time", "y", "x"]
    for record in ("run-status.yaml", "run-provenance.yaml"):
        published = yaml.safe_load((conf.output_dir / record).read_text())["products"]
        assert published[0]["fields"] == product["fields"]
    subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
opener = xr.open_dataset if sys.argv[3] == 'netcdf' else xr.open_zarr
from pathlib import Path
cropped = sys.argv[4] == 'True'
with opener(sys.argv[1],**({'consolidated':False} if sys.argv[3] == 'zarr' else {})) as out, \
     xr.open_dataset(sys.argv[2]) as src:
    q = out.instructional_scalar
    assert set(out.data_vars) == {'instructional_scalar'}
    assert q.dims == ('time','y','x') and q.dtype == np.float64
    assert q.attrs == src.instructional_scalar.attrs and q.attrs['units'] == '1'
    if cropped:
        first = np.array([[-22.,-21.,-20.,-19.,-18.],
                          [-12.,-11.,-10.,np.nan,-8.],
                          [-2.,-1.,0.,1.,2.],
                          [8.,9.,10.,11.,12.],
                          [18.,19.,20.,21.,22.]])
        expected = np.stack((first,first+1000.))
        native = np.arange(6,11)
        assert q.shape == (2,5,5) and q.values[0,2,2] == 0.
        assert np.isnan(q.values[:,1,3]).all()
    else:
        t,j,i = np.indices((2,17,17))
        expected = (1000*t+10*(j-8)+(i-8)).astype(float)
        expected[:,7,9] = np.nan
        native = np.arange(17)
        assert q.shape == (2,17,17) and q.values[0,8,8] == 0.
        assert np.isnan(q.values[:,7,9]).all()
    np.testing.assert_array_equal(q,expected)
    np.testing.assert_array_equal(out.y,np.arange(len(native)))
    np.testing.assert_array_equal(out.x,np.arange(len(native)))
    assert out.y.attrs['units'] == out.x.attrs['units'] == '1'
    np.testing.assert_array_equal(out.time,src.valid_time)
    assert out.time.encoding['calendar'] == src.valid_time.encoding['calendar']
    for name,dim,indices in (
        ('latitude','y',np.broadcast_to(native[None,:,None],q.shape)),
        ('longitude','x',np.broadcast_to(native[None,None,:],q.shape)),
    ):
        labels = src[name].isel({name:native}).values
        expected_geo = np.broadcast_to(labels[None,:,None] if dim == 'y'
                                      else labels[None,None,:],q.shape)
        geography = out[name]
        assert geography.dims == (('time','y','x') if cropped else (dim,))
        np.testing.assert_array_equal(geography.broadcast_like(q),expected_geo)
        auxiliary = out[name+'_source_coordinate']
        np.testing.assert_array_equal(auxiliary.broadcast_like(q),expected_geo)
        assert auxiliary.attrs['units'] == geography.attrs['units'] == src[name].attrs['units']
        index = out[name+'_source_native_index']
        assert index.dims == (('time',dim) if cropped else (dim,))
        np.testing.assert_array_equal(index.broadcast_like(q),indices)
        assert index.attrs['units'] == '1'
        assert name in q.encoding['coordinates'].split()
    if cropped:
        np.testing.assert_array_equal(out.center_time,out.time)
        np.testing.assert_array_equal(out.center_latitude,[-20.,-20.])
        np.testing.assert_array_equal(out.center_longitude,[60.,60.])
        assert out.attrs['region_orientation'] == 'native source x/y; no basis rotation'
    else:
        assert not {'center_time','center_latitude','center_longitude'} & set(out.variables)
    facts = json.loads(out.attrs['frameit_output_coordinates_json'])
    assert any(item['dimensions'] == {'latitude':'y','longitude':'x'}
               for item in facts.values())
if sys.argv[3] == 'zarr':
    import zarr
    array = zarr.open_group(sys.argv[1],mode='r')['instructional_scalar']
    assert array.shards is not None and len(array.shards) == 3
    metadata = json.loads((Path(sys.argv[1])/'instructional_scalar/zarr.json').read_text())
    assert metadata['zarr_format'] == 3 and metadata['dimension_names'] == ['time','y','x']
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], str(source), fmt, str(cropped)], check=True, capture_output=True, text=True)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("packaging", ["whole", "successive", "shared-snapshot"])
def test_independent_moving_grid_trajectories_keep_stable_own_coordinates(
        tmp_path, fmt, packaging):
    import hashlib

    from frameit.core.coupled import bind_sources

    files, scenes = {}, {}
    for name, shift in (("A", 0.), ("B", 5.)):
        scene = mnh_scene()[["T"]].rename(T=name)
        for coordinate in ("latitude", "longitude"):
            original = scene[coordinate]
            values = np.stack([original.values + hour * .01 for hour in (0, 1)])
            if coordinate == "latitude":
                values += shift
                if name == "B" and packaging == "shared-snapshot":
                    values[0] -= shift
            scene = scene.assign_coords({coordinate: (
                ("time", "nj", "ni"), values, dict(original.attrs))})
        if name == "B":
            scene[name].values[:] += 100.
        scene[name].values[0, 0, 0, 1] = 0.
        scenes[name], files[name] = scene, []
        for index in ([None] if packaging == "whole" else [0, 1]):
            path = tmp_path / f"{name}-{index}.nc"
            (scene if index is None else scene.isel(time=[index])).to_netcdf(path)
            path.chmod(0o444)
            files[name].append(str(path))
    hashes = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
              for paths in files.values() for path in paths}
    names = {}
    for index, fields in enumerate((["A", "B"], ["A"], ["B", "A"], ["B"])):
        conf = configuration(tmp_path, "mesonh", {}, sources={"sample": {
            "model": "mesonh", "files": [path for paths in files.values() for path in paths],
            "variables": {"3d": ["A", "B"]}}},
            products={"model_grid": {"fields": {"sample": fields}}},
            output={"format": fmt, "directory": str(tmp_path / f"out-{index}")})
        result = execute_simulation(conf)
        assert len(result.products) == 1
        product = result.products[0]
        planned = conf.simulation_parameter["request_plan"]["products"][0]
        opener = xr.open_dataset if fmt == "netcdf" else xr.open_zarr
        with opener(product["path"], **({"consolidated": False} if fmt == "zarr" else {})) as out:
            for name in fields:
                dimensions = tuple(out[name].dims)
                assert dimensions[:2] == ("time", "level") and len(dimensions) == 4
                assert dimensions[2].startswith("y_") and dimensions[3].startswith("x_")
                geography = tuple(n for n in out[name].encoding["coordinates"].split()
                                  if n.startswith(("latitude_", "longitude_")))
                identity = dimensions, geography
                assert names.setdefault(name, identity) == identity
                assert product["fields"][name]["dimensions"] == list(dimensions)
                assert planned["dimensions"][name] == list(dimensions)
            if len(fields) == 2:
                assert set(out.A.dims[-2:]).isdisjoint(out.B.dims[-2:])
        subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
from contextlib import ExitStack
files, selected = json.loads(sys.argv[3]), json.loads(sys.argv[4])
out = (xr.open_dataset(sys.argv[1]) if sys.argv[2] == 'netcdf'
       else xr.open_zarr(sys.argv[1],consolidated=False))
with out, ExitStack() as stack:
    assert set(out.data_vars) == set(selected)
    np.testing.assert_array_equal(out.time,np.array(
        ['2026-01-01T00','2026-01-01T01'],dtype='datetime64[ns]'))
    assert not {'center_time','center_latitude','center_longitude'} & set(out.variables)
    registry = json.loads(out.attrs['frameit_output_coordinates_json'])
    for name in selected:
        sources = [stack.enter_context(xr.open_dataset(path)) for path in files[name]]
        src = (sources[0] if len(sources) == 1 else xr.concat(
            sources,dim='time',data_vars='all',coords='minimal',compat='equals',join='exact'))
        field = out[name]; y,x = field.dims[-2:]
        np.testing.assert_array_equal(field,src[name])
        assert field.dtype == np.float32 and field.attrs['units'] == src[name].attrs['units']
        assert field.values[0,0,0,1] == 0. and np.isnan(field.values[0,0,0,0])
        assert out.time.encoding['calendar'] == src.time.encoding['calendar']
        links = field.encoding['coordinates'].split()
        for kind in ('latitude','longitude'):
            coordinate, = [n for n in links if n.startswith(kind+'_')]
            assert out[coordinate].dims == ('time',y,x)
            np.testing.assert_array_equal(out[coordinate],src[kind])
            assert out[coordinate].dtype == src[kind].dtype
            assert out[coordinate].attrs == src[kind].attrs
        for native, axis in (('nj',y),('ni',x)):
            np.testing.assert_array_equal(out[axis],np.arange(src.sizes[native]))
            np.testing.assert_array_equal(out[axis+'_source_coordinate'],src[native])
            np.testing.assert_array_equal(out[axis+'_source_native_index'],
                                          np.arange(src.sizes[native]))
            assert out[axis+'_source_coordinate'].attrs['units'] == src[native].attrs['units']
            assert out[axis+'_source_native_index'].attrs['units'] == '1'
        assert any(item['dimensions'].get('nj') == y and item['dimensions'].get('ni') == x
                   for item in registry.values())
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], fmt, json.dumps(files), json.dumps(fields)],
            check=True, capture_output=True, text=True)
        assert {path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                for path in hashes} == hashes
    if packaging == "successive":
        controls = []
        for name, scene in scenes.items():
            path = tmp_path / f"whole-control-{name}.nc"
            scene.to_netcdf(path)
            path.chmod(0o444)
            controls.append(str(path))
        conf = configuration(tmp_path, "mesonh", {}, sources={"sample": {
            "model": "mesonh", "files": controls, "variables": {"3d": ["A", "B"]}}})
        bind_sources(conf)
        planned = conf.simulation_parameter["request_plan"]["products"][0]
        assert all(planned["dimensions"][name] == list(names[name][0]) for name in ("A", "B"))


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_shared_snapshot_single_time_keeps_extra_dimension_bounds(tmp_path, fmt):
    import hashlib

    files = {}
    for name in ("A", "B"):
        scene = mnh_scene()[["T"]].rename(T=name)
        scene.level.attrs["bounds"] = "level_bounds"
        scene = scene.assign_coords(level_bounds=(
            ("level", "nv"), [[0., 20.], [20., 40.]], {"units": "m"}))
        for kind in ("latitude", "longitude"):
            original = scene[kind]
            geography = np.stack([original.values, original.values + .01])
            if name == "B" and kind == "latitude":
                geography[1] += 5.
            scene = scene.assign_coords({kind: (
                ("time", "nj", "ni"), geography, dict(original.attrs))})
        if name == "B":
            scene[name].values[:] += 100.
        scene[name].values[0, 0, 0, 1] = 0.
        files[name] = []
        for hour in (0, 1):
            path = tmp_path / f"{name}-{hour}.nc"
            scene.isel(time=[hour]).to_netcdf(path)
            path.chmod(0o444)
            files[name].append(str(path))
    hashes = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
              for paths in files.values() for path in paths}
    axes = {}
    for index, selected in enumerate((["A", "B"], ["A"], ["B"])):
        conf = configuration(tmp_path, "mesonh", {}, sources={"sample": {
            "model": "mesonh", "files": [path for paths in files.values() for path in paths],
            "time": {"values": ["2026-01-01T00:00:00"]},
            "variables": {"3d": ["A", "B"], "levels": {"indices": [0]}}}},
            products={"model_grid": {"fields": {"sample": selected}}},
            output={"format": fmt, "directory": str(tmp_path / f"out-{index}")})
        result = execute_simulation(conf)
        assert len(result.products) == 1
        product = result.products[0]
        planned = conf.simulation_parameter["request_plan"]["products"][0]
        assert set(product["fields"]) == set(selected)
        for name in selected:
            dimensions = product["fields"][name]["dimensions"]
            assert planned["dimensions"][name] == dimensions
            assert axes.setdefault(name, dimensions) == dimensions
        for record in ("run-status.yaml", "run-provenance.yaml"):
            saved = yaml.safe_load((conf.output_dir / record).read_text())["products"][0]
            assert saved["fields"] == product["fields"]
        subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
out = (xr.open_dataset(sys.argv[1]) if sys.argv[2] == 'netcdf'
       else xr.open_zarr(sys.argv[1],consolidated=False))
files, selected, dimensions = map(json.loads,sys.argv[3:])
with out:
    assert set(out.data_vars) == set(selected)
    for owner in out.variables:
        if bounds := out[owner].attrs.get('bounds'):
            assert bounds in out, (owner,bounds)
            assert out[bounds].dims[:-1] == out[owner].dims
    np.testing.assert_array_equal(out.time,np.array(
        ['2026-01-01T00'],dtype='datetime64[ns]'))
    np.testing.assert_array_equal(out.level,[10.])
    np.testing.assert_array_equal(out.level_source_native_index,[0])
    bounds = out[out.level.attrs['bounds']]
    assert bounds.dims == ('level','nv') and bounds.shape == (1,2)
    np.testing.assert_array_equal(bounds,[[0.,20.]])
    assert bounds.attrs.get('units',out.level.attrs['units']) == out.level.attrs['units'] == 'm'
    assert not {'center_time','center_latitude','center_longitude'} & set(out.variables)
    expected = {'A': [[[[np.nan,0.,2.],[3.,4.,5.]]]],
                'B': [[[[np.nan,0.,102.],[103.,104.,105.]]]]}
    for name in selected:
        field = out[name]; y,x = field.dims[-2:]
        assert list(field.dims) == dimensions[name] and field.dims[:2] == ('time','level')
        assert y.startswith('y_') and x.startswith('x_')
        np.testing.assert_array_equal(field,np.array(expected[name],dtype=np.float32))
        assert field.dtype == np.float32 and field.attrs['units'] == 'K'
        with xr.open_dataset(files[name][0]) as src:
            np.testing.assert_array_equal(field,src[name].isel(level=[0]))
            assert out.time.encoding['calendar'] == src.time.encoding['calendar']
            for kind in ('latitude','longitude'):
                stored, = [n for n in field.encoding['coordinates'].split()
                            if n.startswith(kind+'_')]
                assert out[stored].dims == ('time',y,x)
                np.testing.assert_array_equal(out[stored],src[kind])
                assert out[stored].attrs == src[kind].attrs
            for native,axis in (('nj',y),('ni',x)):
                np.testing.assert_array_equal(out[axis],np.arange(src.sizes[native]))
                np.testing.assert_array_equal(out[axis+'_source_coordinate'],src[native])
                np.testing.assert_array_equal(out[axis+'_source_native_index'],
                                              np.arange(src.sizes[native]))
                assert out[axis+'_source_coordinate'].attrs['units'] == 'km'
                assert out[axis+'_source_native_index'].attrs['units'] == '1'
    if len(selected) == 2:
        assert set(out.A.dims[-2:]).isdisjoint(out.B.dims[-2:])
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], fmt, json.dumps(files), json.dumps(selected),
            json.dumps(product["dimensions"])], check=True, text=True)
        assert {path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                for path in hashes} == hashes
