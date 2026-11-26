"""Exercise FrameIt's selected-input path with only the external inference replaced."""

import sys
from importlib.machinery import ModuleSpec
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from frameit.core.execution import execute_simulation
from frameit.core.preflight import collect_preflight
from frameit.core.settings_class import SimulationConfig


def scene():
    ds = xr.Dataset(coords={
        "time": np.datetime64("2024-01-01T00", "ns") + np.arange(5) * np.timedelta64(6, "h"),
        "latitude": ("latitude", [-20.2, -20.1, -20., -19.9, -19.8], {"units": "degrees_north"}),
        "longitude": ("longitude", [60., 60.1, 60.2, 60.3, 60.4, 60.5], {"units": "degrees_east"}),
        "isobaric": ("isobaric", [70000., 85000., 95000.], {"units": "Pa"}),
    })
    horizontal = ("time", "latitude", "longitude")
    ds["u10"] = (horizontal, np.broadcast_to(np.arange(4., 9.)[:, None, None], (5, 5, 6)),
                 {"units": "m s-1", "standard_name": "eastward_wind"})
    ds["v10"] = (horizontal, np.full((5, 5, 6), 3.),
                 {"units": "m s-1", "standard_name": "northward_wind"})
    ds["absv"] = (("time", "isobaric", *horizontal[1:]),
                  np.broadcast_to(np.array([1e-4, -2e-4, 3e-4])[None, :, None, None], (5, 3, 5, 6)),
                  {"units": "s-1", "standard_name": "atmosphere_absolute_vorticity"})
    return ds


def write_grib(path, ds, *, omit_850=False, wind_height=10):
    import eccodes as ec

    with path.open("wb") as stream:
        for i in range(ds.sizes["time"]):
            for name, short, levels in (("u10", "10u", [None]), ("v10", "10v", [None]),
                                        ("absv", "absv", [700, 850, 950])):
                for level in levels:
                    if omit_850 and i == 2 and level == 850:
                        continue
                    message = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
                    try:
                        for key, value in {
                            "Ni": 6, "Nj": 5,
                            "latitudeOfFirstGridPointInDegrees": -20.2,
                            "latitudeOfLastGridPointInDegrees": -19.8,
                            "longitudeOfFirstGridPointInDegrees": 60.,
                            "longitudeOfLastGridPointInDegrees": 60.5,
                            "iDirectionIncrementInDegrees": .1, "jDirectionIncrementInDegrees": .1,
                            "jScansPositively": 1, "dataDate": 20240101, "dataTime": 0,
                            "forecastTime": i * 6, "shortName": short, "uvRelativeToGrid": 0,
                        }.items():
                            ec.codes_set(message, key, value)
                        values = ds[name].isel(time=i)
                        if level is None:
                            ec.codes_set(message, "level", wind_height)
                        else:
                            ec.codes_set(message, "typeOfLevel", "isobaricInhPa")
                            ec.codes_set(message, "level", level)
                            values = values.sel(isobaric=100 * level)
                        ec.codes_set_values(message, values.values.ravel())
                        ec.codes_write(message, stream)
                    finally:
                        ec.codes_release(message)


@pytest.fixture
def backend(monkeypatch):
    """Do not install Torch or open a Lightning checkpoint for this test."""
    calls = SimpleNamespace(loaded=[], batches=[], center=(1.8, 2.7))
    modules = {name: ModuleType(name) for name in ("torch", "utrack", "utrack.prepare")}
    for name, module in modules.items():
        module.__spec__ = ModuleSpec(name, None)
        monkeypatch.setitem(sys.modules, name, module)

    def prepare_input(*, u10, v10, absv, lat):
        np.testing.assert_allclose(v10, 3.)
        np.testing.assert_allclose(absv, -2e-4)
        assert np.all(lat < 0)
        calls.batches.append(u10[:, 0, 0].tolist())
        return np.stack([np.hypot(u10, v10), -absv], axis=1)

    class Utracker:
        def load_checkpoint(self, *, checkpoint_path):
            calls.loaded.append(checkpoint_path)

        def predict_batch(self, inputs, *, use_gpu, match, batch_size):
            assert inputs.shape[1:] == (2, 5, 6) and len(inputs) <= batch_size
            assert not use_gpu and not match
            fix = SimpleNamespace(vmax_center=calls.center)
            cyclone = SimpleNamespace(last_fix=lambda: fix)
            return np.zeros((len(inputs), 5, 6)), [
                [] if calls.center is None else [cyclone] for _ in inputs]

    modules["utrack"].Utracker = Utracker
    modules["utrack.prepare"].get_latitude = lambda ds: ds.latitude
    modules["utrack.prepare"].prepare_input = prepare_input
    return calls


def config(tmp_path, path, *, model="arome", weights=True):
    checkpoint = tmp_path / "test.ckpt"
    if weights:
        checkpoint.write_bytes(b"not used by fake inference")
    return {
        "schema_version": 3,
        "sources": {"atm": {"model": model, "files": str(path), "time": {"stride": 2}}},
        "region": {"tracker": {"method": "utrack", "weights_file": str(checkpoint),
                               "batch_size": 2}},
        "products": {"track": True},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"cpus": 1, "scheduler": "synchronous", "synchronous_export": True},
    }


@pytest.mark.parametrize("fmt", ["netcdf", "grib"])
def test_utrack_selected_850_and_track(tmp_path, monkeypatch, backend, fmt):
    path = tmp_path / ("in.nc" if fmt == "netcdf" else "in.grib")
    ds = scene()
    if fmt == "netcdf":
        from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

        ds.to_netcdf(path, engine="h5netcdf")
        original = H5NetCDFArrayWrapper.__getitem__

        def selected(array, key):
            if array.variable_name in {"u10", "v10", "absv"}:
                assert set(np.atleast_1d(np.arange(5)[key.tuple[0]])) <= {0, 2, 4}
                if array.variable_name == "absv":
                    assert set(np.atleast_1d(np.arange(3)[key.tuple[1]])) == {1}
            return original(array, key)

        monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", selected)
    else:
        import eccodes as ec

        write_grib(path, ds)
        original = ec.codes_get_values

        def selected(handle):
            assert ec.codes_get(handle, "endStep") in {0, 12, 24}
            if ec.codes_get(handle, "shortName") == "absv":
                assert ec.codes_get(handle, "level") == 850
            return original(handle)

        monkeypatch.setattr(ec, "codes_get_values", selected)
    raw = config(tmp_path, path)
    preview = collect_preflight(raw)
    assert not preview.errors, [error.message for error in preview.errors]
    assert backend.loaded == []
    assert not (tmp_path / "out").exists()
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert backend.batches == [[4., 6.], [8.]]
    assert len(backend.loaded) == 1
    track, = result.products
    assert track["role"] == "track"
    with xr.open_dataset(track["path"]) as out:
        np.testing.assert_array_equal(out.time, ds.time.values[[0, 2, 4]])
        np.testing.assert_allclose(out.latitude, -20.1)
        np.testing.assert_allclose(out.longitude, 60.2)


@pytest.mark.parametrize(("case", "message"), [
    ("no_weights", "checkpoint"), ("empty_weights", "checkpoint"),
    ("wrong_units", "vorticity"), ("wrong_quantity", "vorticity"),
    ("other_grid", "grid"), ("missing_850", "850"),
    ("grib_height", "u10"), ("netcdf_height", "10 m"), ("mesonh", "AROME"),
])
def test_utrack_rejects_incompatible_preflight_inputs(tmp_path, backend, case, message):
    ds = scene()
    raw = config(tmp_path, tmp_path / "in.nc",
                 model="mesonh" if case == "mesonh" else "arome",
                 weights=case not in {"no_weights", "empty_weights"})
    source = raw["sources"]["atm"]
    path = tmp_path / "in.nc"
    if case == "empty_weights":
        (tmp_path / "test.ckpt").touch()
    if case == "wrong_units":
        ds.absv.attrs["units"] = "m"
    elif case == "wrong_quantity":
        ds.absv.attrs["standard_name"] = "atmosphere_relative_vorticity"
    elif case == "other_grid":
        ds["absv"] = ds.absv.rename(longitude="lon").assign_coords(lon=ds.longitude.values + 1)
    elif case == "netcdf_height":
        ds = ds.assign_coords(height=xr.DataArray(11., attrs={"units": "m", "standard_name": "height"}))
    if case in {"missing_850", "grib_height"}:
        path = tmp_path / "in.grib"
        source["files"] = str(path)
        write_grib(path, ds, omit_850=case == "missing_850",
                   wind_height=11 if case == "grib_height" else 10)
    else:
        ds.to_netcdf(path, engine="h5netcdf")
    report = collect_preflight(raw)
    assert any(message in error.message for error in report.errors), report.errors
    assert backend.loaded == [] and not (tmp_path / "out").exists()


@pytest.mark.parametrize(("center", "nan", "message"), [
    (None, False, "No cyclone detected"), ((1, 9), False, "outside"),
    ((1, 2), True, "finite"),
])
def test_utrack_invalid_sample_does_not_publish_track(tmp_path, backend, center, nan, message):
    path = tmp_path / "in.nc"
    ds = scene()
    if nan:
        ds["v10"] = ds["v10"].where(ds["v10"].longitude != 60.5)
    ds.to_netcdf(path, engine="h5netcdf")
    backend.center = center
    conf = SimulationConfig.from_mapping_with_model_preset(config(tmp_path, path))
    with pytest.raises(ValueError, match=message):
        execute_simulation(conf)
    assert not list((tmp_path / "out").rglob("*.nc"))
