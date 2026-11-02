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
