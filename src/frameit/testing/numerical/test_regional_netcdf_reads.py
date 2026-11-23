"""Exercise the native backend boundary, not just a cropped Dask result."""

import numpy as np
import pytest
import xarray as xr
from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

from frameit.core.execution import execute_simulation
from frameit.testing.numerical.test_v3_polar import configuration


@pytest.mark.parametrize("product", ["model_grid", "polar"])
def test_moving_layered_field_reads_only_its_native_window(tmp_path, monkeypatch, product):
    x = np.arange(25) * 1000.
    lon, lat = np.meshgrid(60 + x / 104300., -20 + x / 111000.)
    time = np.array(["2024-01-01", "2024-01-02"], dtype="datetime64[ns]")
    values = np.arange(2 * 4 * 25**2, dtype="f8").reshape(2, 4, 25, 25)
    values[1, 2, 14, 17] = np.nan
    ds = xr.Dataset({"q": (("time", "level", "nj", "ni"), values, {"units": "K"})}, coords={
        "time": time, "level": ("level", [10., 20., 30., 40.], {"units": "m"}),
        "nj": ("nj", x, {"units": "m"}), "ni": ("ni", x, {"units": "m"}),
        "latitude": (("nj", "ni"), lat, {"units": "degrees_north"}),
        "longitude": (("nj", "ni"), lon, {"units": "degrees_east"}),
    })
    ds.to_netcdf(tmp_path / "input.nc", encoding={
        "q": {"dtype": "int16", "scale_factor": .5, "_FillValue": -32768}})
    centres = [(1, 2), (14, 17)]
    xr.Dataset(coords={
        "time": time,
        "latitude": ("time", [lat[j, i] for j, i in centres], {"units": "degrees_north"}),
        "longitude": ("time", [lon[j, i] for j, i in centres], {"units": "degrees_east"}),
    }).to_netcdf(tmp_path / "track.nc")
    cfg = configuration(tmp_path, source={"variables": {"3d": {"level": {
        "names": ["q"], "levels": {"indices": [2, 0]}}}}},
        region={"track": {"file": str(tmp_path / "track.nc")}, "width_km": {"x": 6, "y": 6}},
        products={product: True if product == "model_grid" else {
            "radius_km": 2.5, "radial_step_km": 2., "azimuth_count": 8}})
    original, reads = H5NetCDFArrayWrapper._getitem, []

    def trace(array, key):
        result = original(array, key)
        if array.variable_name == "q":
            reads.append((key, result.shape))
        return result

    monkeypatch.setattr(H5NetCDFArrayWrapper, "_getitem", trace)
    result = execute_simulation(cfg)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        field = saved["level.q"]
        np.testing.assert_array_equal(field.level, [30., 10.])
        if product == "model_grid":
            padded = np.full((2, 7, 7), np.nan)
            padded[:, 2:, 1:] = values[0, [2, 0], :5, :6]
            np.testing.assert_array_equal(field[0], padded)
            np.testing.assert_array_equal(field[1], values[1, [2, 0], 11:18, 14:21])
        else:
            np.testing.assert_allclose(field.isel(time=0, radius=0, azimuth=0),
                                       values[0, [2, 0], 1, 2], atol=1e-8, rtol=0)
    assert reads and all(s[-2] < 25 and s[-1] < 25 for _, s in reads), reads


def test_rotated_mass_winds_read_both_native_face_stencils(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_grid_representations import native_scene

    ds = native_scene(units="km/h")
    ds.UT.values[:, :, 4, 5] = np.nan
    ds.to_netcdf(tmp_path / "input.nc")
    source = {"variables": {"3d": ["UT", "VT"]},
              "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid",
                              "rotation": {"method": "geolocation"}}],
              "transforms": [{"fields": ["UT", "VT"], "sampling": "mass", "basis": "earth"}]}
    region = {"center": {"latitude": -20., "longitude": 60.}, "width_km": {"x": 2, "y": 2}}
    products = {"model_grid": True, "polar": {
        "radius_km": 1.5, "radial_step_km": 1.5, "azimuth_count": 8,
        "field_options": {"atmosphere": {n: {"sampling": "mass", "basis": "earth"}
                                        for n in ("UT", "VT")}}}}
    control = execute_simulation(configuration(
        tmp_path, source={**source, "reader": {"chunks": {"time": 1}}}, region=region,
        products=products, output_name="control"))
    reads = []
    original = H5NetCDFArrayWrapper._getitem

    def trace(array, key):
        result = original(array, key)
        if array.variable_name in {"UT", "VT"}:
            reads.append((array.variable_name, result.shape[-2:]))
        return result

    monkeypatch.setattr(H5NetCDFArrayWrapper, "_getitem", trace)
    trial = execute_simulation(configuration(tmp_path, source=source, region=region,
                                             products=products))
    for a, b in zip(control.products, trial.products, strict=True):
        with xr.open_dataset(a["path"]) as expected, xr.open_dataset(b["path"]) as actual:
            expected.attrs.clear()
            actual.attrs.clear()
            xr.testing.assert_identical(actual, expected)
    assert {name for name, _ in reads} == {"UT", "VT"}
    assert all(max(shape) < 9 for _, shape in reads), reads
