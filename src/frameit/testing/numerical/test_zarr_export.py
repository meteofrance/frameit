"""Storage-only regressions: ordinary readers, real sharding and safe publication."""

import json
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr

from frameit.io.netcdf_export import ExportMetadata


def scene():
    values = np.arange(3 * 5 * 7, dtype=np.float32).reshape(3, 5, 7)
    values[1, 2, 3] = np.nan
    ds = xr.Dataset(
        {"temperature": (("time", "y", "x"), values, {"units": "K"}),
         "flag": ("time", np.array([0, 1, -9], dtype=np.int16), {"_FillValue": -9}),
         "crs": ((), 0, {"grid_mapping_name": "latitude_longitude"})},
        coords={"time": np.array(["2026-01-01", "2026-01-02", "2026-01-03"],
                                 dtype="datetime64[ns]"),
                "x": np.arange(7), "y": np.arange(5),
                "label": ("time", ["first", "second", "third"]),
                "valid": ("time", [True, False, True])},
        attrs={"selection": {"explicit": True}, "enabled": True})
    ds.temperature.encoding = {"zlib": True, "complevel": 1, "chunksizes": (1, 5, 7)}
    return ds.chunk({"time": 1, "y": 3, "x": 3})


def write(ds, path, **kwargs):
    from frameit.io.zarr_export import write_dataset_zarr

    return write_dataset_zarr(
        ds, path, metadata=ExportMetadata("TEST", "Title", "Summary", "Institute", "test"),
        product_type="cart", group="surface", track_filename="TEST.track.zarr", **kwargs)


def test_sharded_round_trip_independent_reader(tmp_path):
    pytest.importorskip("zarr")
    source = scene()
    target = write(source, tmp_path / "field.zarr",
                   chunk_size={"time": 1, "y": 2, "x": 2},
                   shard_size={"time": 2, "y": 4, "x": 4})
    metadata = json.loads((target / "temperature" / "zarr.json").read_text())
    assert metadata["zarr_format"] == 3
    assert metadata["chunk_grid"]["configuration"]["chunk_shape"] == [2, 4, 4]
    assert metadata["codecs"][0]["name"] == "sharding_indexed"
    assert metadata["codecs"][0]["configuration"]["chunk_shape"] == [1, 2, 2]
    with xr.open_zarr(target, consolidated=False) as saved:
        xr.testing.assert_equal(saved.temperature, source.temperature)
        np.testing.assert_equal(saved.flag.values, [0., 1., np.nan])
        assert saved.crs.item() == 0
        assert saved.attrs["track_filename"] == "TEST.track.zarr"
        assert json.loads(saved.attrs["selection_json"]) == {"explicit": True}
        assert saved.temperature.dtype == np.float32
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_zarr(sys.argv[1], consolidated=False) as ds:
    assert ds.temperature.shape == (3, 5, 7)
    assert ds.temperature[0, 0, 0].values.item() == 0
    assert np.isnan(ds.temperature[1, 2, 3].values.item())
    assert ds.time.values[0] == np.datetime64('2026-01-01')
    assert ds.label.values.tolist() == ['first', 'second', 'third']
    assert ds.valid.values.tolist() == [True, False, True]
assert 'frameit' not in sys.modules
""", str(target)], check=True)
    assert source.temperature.encoding["zlib"] is True


@pytest.mark.parametrize("kwargs, chunks, shards", [
    ({}, [1, 5, 7], [8, 20, 28]),
    ({"chunk_size": {"x": 2, "not_in_product": 10}}, [1, 5, 2], [8, 20, 8]),
    ({"shard_size": {"x": 6}}, [1, 5, 1], [8, 20, 6]),
])
def test_shape_defaults_and_overrides(tmp_path, kwargs, chunks, shards):
    zarr = pytest.importorskip("zarr")
    target = write(scene(), tmp_path / "field.zarr", **kwargs)
    array = zarr.open_group(target, mode="r")["temperature"]
    assert list(array.chunks) == chunks
    assert list(array.shards) == shards


def test_default_layout_does_not_multiply_large_vertical_blocks(tmp_path):
    zarr = pytest.importorskip("zarr")
    ds = xr.Dataset({"cube": (("time", "level", "y", "x"),
                              np.zeros((2, 100, 5, 7), dtype=np.float32))})
    array = zarr.open_group(write(ds, tmp_path / "cube.zarr"), mode="r")["cube"]
    assert array.chunks == (1, 1, 5, 7)
    assert array.shards == (8, 1, 20, 28)


def test_store_failure_and_overwrite(tmp_path, monkeypatch):
    pytest.importorskip("zarr")
    target = write(scene(), tmp_path / "field.zarr")
    original = (target / "zarr.json").read_bytes()
    with pytest.raises(FileExistsError):
        write(scene(), target, overwrite=False)

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(xr.Dataset, "to_zarr", fail)
    with pytest.raises(OSError, match="disk full"):
        write(scene(), target)
    assert (target / "zarr.json").read_bytes() == original
    assert list(tmp_path.iterdir()) == [target]


def test_directory_publication_failure_restores_old_store(tmp_path, monkeypatch):
    from frameit.utils import atomic

    target = tmp_path / "field.zarr"
    target.mkdir()
    (target / "zarr.json").write_text('{"zarr_format": 3, "node_type": "group"}')
    original_replace = atomic.os.replace

    def fail_publish(source, destination):
        if str(source).endswith(".partial"):
            raise OSError("publication failed")
        return original_replace(source, destination)

    monkeypatch.setattr(atomic.os, "replace", fail_publish)
    with pytest.raises(OSError, match="publication failed"):
        with atomic.atomic_directory_output(target) as temporary:
            (temporary / "new").write_text("new")
    assert (target / "zarr.json").is_file()
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_refuse_non_store_replacement(tmp_path, kind):
    from frameit.utils.atomic import atomic_directory_output

    target = tmp_path / "field.zarr"
    if kind == "directory":
        target.mkdir()
    elif kind == "symlink":
        target.symlink_to(tmp_path / "missing", target_is_directory=True)
    else:
        target.write_text("unrelated work")
    with pytest.raises(ValueError, match="store|symlink"):
        with atomic_directory_output(target):
            pytest.fail("Must reject before writing")


@pytest.mark.parametrize("kwargs", [
    {"chunk_size": {"x": True}}, {"chunk_size": {"x": 0}},
    {"shard_size": {"x": -1}}, {"shard_size": {"x": 1.5}},
    {"chunk_size": []}, {"chunk_size": {"x": 3}, "shard_size": {"x": 4}},
])
def test_invalid_sizes_fail_before_publication(tmp_path, kwargs):
    pytest.importorskip("zarr")
    with pytest.raises(ValueError, match="chunk|shard"):
        write(scene(), tmp_path / "field.zarr", **kwargs)
    assert not (tmp_path / "field.zarr").exists()


def test_empty_dimension_fails_actionably(tmp_path):
    pytest.importorskip("zarr")
    with pytest.raises(ValueError, match="empty.*dimension|dimension.*empty"):
        write(scene().isel(time=slice(0, 0)), tmp_path / "field.zarr")


def test_zarr_schema_only_needs_no_optional_imports(tmp_path):
    from frameit.testing.numerical.test_configuration_v2 import document

    raw = document(tmp_path, output={"engine": "zarr", "zarr_chunk_size": {"x_box": 2},
                                     "zarr_shard_size": {"x_box": 4}})
    subprocess.run([sys.executable, "-c", """
import json, sys
from frameit.core.configuration import resolve_schema
resolve_schema(json.loads(sys.argv[1]))
assert 'zarr' not in sys.modules
""", json.dumps(raw)], check=True)


@pytest.mark.parametrize("setting", [
    {"zarr_chunk_size": {"x": True}}, {"zarr_chunk_size": {"x": 0}},
    {"zarr_shard_size": {"x": -1}}, {"zarr_shard_size": {"x": 1.5}},
    {"zarr_chunk_size": []}, {"zarr_chunk_size": {"x": 3}, "zarr_shard_size": {"x": 4}},
])
def test_schema_rejects_invalid_zarr_sizes(tmp_path, setting):
    from frameit.core.configuration import resolve_schema
    from frameit.testing.numerical.test_configuration_v2 import document

    with pytest.raises(ValueError, match="chunk|shard"):
        resolve_schema(document(tmp_path, output={"engine": "zarr", **setting}))


@pytest.mark.parametrize("synchronous", [True, False])
def test_export_all_product_types_and_references(tmp_path, synchronous):
    pytest.importorskip("zarr")
    from types import SimpleNamespace

    from frameit.core.execution import _product_descriptors
    from frameit.io.netcdf_export import export_outputs

    ds = scene()
    ds.attrs.update(source_id="atmosphere", source_group="surface")
    runner = SimpleNamespace(conf=SimpleNamespace(simulation_name="TEST"), output_dir=tmp_path,
                             track=ds[["flag"]], dict_crop_user={"atmosphere.surface": ds},
                             dict_polar_user={"with space": ds})
    exports = export_outputs(runner, institution="test", engine="zarr", synchronous=synchronous,
                             max_workers=1, zarr_chunk_size={"x": 2},
                             zarr_shard_size={"x": 4})
    assert exports["track"].name == "TEST.track.zarr"
    assert exports["cart"][0].name == "TEST.cart.atmosphere.surface.zarr"
    assert exports["polar"][0].name == "TEST.polar.with_space.zarr"
    for role in ("cart", "polar"):
        with xr.open_zarr(exports[role][0], consolidated=False) as saved:
            assert saved.attrs["track_filename"] == "TEST.track.zarr"
            xr.testing.assert_equal(saved.temperature, ds.temperature)
    cart = next(p for p in _product_descriptors(exports, runner) if p["role"] == "cart")
    assert cart["group"] == "atmosphere.surface"
    assert cart["source"] == "atmosphere"
    assert cart["source_group"] == "surface"


def test_pipeline_planning_inventory_and_replay(tmp_path):
    pytest.importorskip("zarr")
    import yaml

    from frameit.core.execution import execute_simulation
    from frameit.core.preflight import preflight
    from frameit.core.settings_class import SimulationConfig
    from frameit.testing.numerical.test_configuration_v2 import dataset, document

    dataset(tmp_path)
    raw = document(tmp_path, output={"directory": str(tmp_path / "run"), "engine": "zarr",
                                     "synchronous_export": True,
                                     "zarr_chunk_size": {"time": 1, "x_box": 2},
                                     "zarr_shard_size": {"time": 2, "x_box": 4}})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan = preflight(conf)
    assert all(p.endswith(".zarr") for p in plan["planned_products"])
    result = execute_simulation(conf)
    assert result.ok
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["state"] == "completed"
    for product in status["products"]:
        path = conf.output_dir / product["path"]
        assert product["size_bytes"] == sum(p.stat().st_size for p in path.rglob("*")
                                            if p.is_file())
        with xr.open_zarr(path, consolidated=False) as saved:
            assert saved.sizes["time"] == 2
            if product["role"] == "cart":
                np.testing.assert_allclose(saved.UM10, 10.)
                assert product["group"] == "surface"
    assert "zarr" in result.backend_versions
    resolved = yaml.safe_load((conf.output_dir / "resolved-config.yaml").read_text())
    assert resolved["output"]["zarr_chunk_size"] == {"time": 1, "x_box": 2}
    assert resolved["output"]["zarr_shard_size"] == {"time": 2, "x_box": 4}
    resolved["output"]["directory"] = str(tmp_path / "replay")
    assert execute_simulation(SimulationConfig.from_mapping_with_model_preset(resolved)).ok


def test_coupled_preview_and_execution(tmp_path):
    pytest.importorskip("zarr")
    from frameit.core.execution import execute_simulation
    from frameit.core.preflight import preflight
    from frameit.core.settings_class import SimulationConfig
    from frameit.testing.numerical.test_arome_fa_coupling import arome_netcdf_document

    raw = arome_netcdf_document(tmp_path)
    raw["polar"]["enabled"] = False
    raw["output"]["engine"] = "zarr"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    plan = preflight(conf)
    assert all(p.endswith(".zarr") for p in plan["planned_products"])
    result = execute_simulation(conf)
    cart = [p for p in result.products if p["role"] == "cart"]
    assert {p["source"] for p in cart} == {"atmosphere", "surface"}
    for product in cart:
        with xr.open_zarr(product["path"], consolidated=False) as saved:
            np.testing.assert_allclose(saved.temperature.sel(x_box=0, y_box=0), [280., 281.])


def test_missing_optional_dependency_fails_before_processing(tmp_path, monkeypatch):
    import importlib.metadata

    from frameit.core.execution import ExecutionOptions, execute_simulation
    from frameit.core.settings_class import SimulationConfig
    from frameit.testing.numerical.test_configuration_v2 import dataset, document

    original = importlib.metadata.version

    def missing_zarr(name):
        if name == "zarr":
            raise importlib.metadata.PackageNotFoundError(name)
        return original(name)

    monkeypatch.setattr(importlib.metadata, "version", missing_zarr)
    raw = document(tmp_path, output={"directory": str(tmp_path / "run"), "engine": "zarr"})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match=r"frameit\[zarr\]"):
        execute_simulation(conf)
    assert not conf.output_dir.exists()
    dataset(tmp_path)
    options = ExecutionOptions.from_config(conf, export_netcdf=False)
    assert execute_simulation(conf, options).products == []


@pytest.mark.parametrize("package, old_version", [("xarray", "2025.10.1"), ("zarr", "3.1.3")])
def test_unsupported_optional_versions_fail_actionably(monkeypatch, package, old_version):
    import importlib.metadata

    from frameit.io.zarr_export import check_zarr_dependencies

    original = importlib.metadata.version
    monkeypatch.setattr(importlib.metadata, "version",
                        lambda name: old_version if name == package else original(name))
    with pytest.raises(ValueError, match=r"frameit\[zarr\]"):
        check_zarr_dependencies()
