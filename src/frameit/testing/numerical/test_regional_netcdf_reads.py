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
            reads.append(tuple(tuple(np.atleast_1d(np.arange(n)[k]))
                               for n, k in zip(array.shape, key, strict=True)))
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
            assert np.isnan(field.isel(time=1, level=0, radius=0)).all()
            np.testing.assert_array_equal(
                saved["level.q_interpolation_status"].isel(time=1, level=0, radius=0), 2)
    rectangles = ([(0, 5, 0, 6), (11, 18, 14, 21)] if product == "model_grid"
                  else [(0, 6, 0, 7), (10, 19, 13, 22)])
    # h5netcdf reads the two native levels in ascending order; output order is [2, 0].
    assert sorted(reads) == [((t,), (0, 2), tuple(range(y0, y1)), tuple(range(x0, x1)))
                             for t, (y0, y1, x0, x1) in enumerate(rectangles)]


@pytest.mark.parametrize("missing_face_units", [False, True])
def test_rotated_mass_winds_read_both_native_face_stencils(tmp_path, monkeypatch, missing_face_units):
    import weakref

    from frameit.io import netcdf_export
    from frameit.processing.derived import wind
    from frameit.testing.numerical.test_grid_representations import native_scene

    ds = native_scene(units="km/h")
    for suffix in ("", "_u", "_v"):
        x, y = np.meshgrid(ds["ni" + suffix], ds["nj" + suffix])
        ds["latitude" + suffix].values[:] = -20 + (x - 4e-6 * x * y) / 111000
        ds["longitude" + suffix].values[:] = 60 - (y + 2e-6 * (x*x - y*y)) / (
            111000 * np.cos(np.deg2rad(20)))
    ds.VT.values[:] = 3.6 * (3 + np.asarray(ds.nj_v)[:, None] / 1000
                             + np.asarray(ds.ni_v)[None, :] / 2500)
    ds.UT.values[:, :, 4, 5] = np.nan
    if missing_face_units:
        del ds.ni_u.attrs["units"]
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
    angles, retained = [], []
    angle, write = wind.rotation_angle, netcdf_export._write_product

    def remember(*args):
        result = angle(*args)
        angles.append(weakref.ref(result))
        return result

    def at_export(*args):
        retained.append(sum(ref() is not None for ref in angles))
        return write(*args)

    monkeypatch.setattr(wind, "rotation_angle", remember)
    monkeypatch.setattr(netcdf_export, "_write_product", at_export)
    trial = execute_simulation(configuration(tmp_path, source=source, region=region,
                                             products=products))
    for a, b in zip(control.products, trial.products, strict=True):
        with xr.open_dataset(a["path"]) as expected, xr.open_dataset(b["path"]) as actual:
            expected.attrs.clear()
            actual.attrs.clear()
            xr.testing.assert_identical(actual, expected)
    assert {name for name, _ in reads} == {"UT", "VT"}
    assert all(max(shape) < 9 for _, shape in reads), reads
    assert angles and not any(retained), "full-domain rotation inputs retained through publication"


@pytest.mark.parametrize("short_axis", ["time", "level"])
def test_reopened_file_cannot_clip_a_bound_native_selection(tmp_path, short_axis):
    from frameit.io.loader import DatasetResources
    from frameit.testing.numerical.test_v3_netcdf_reads import _binding, _load
    from frameit.testing.numerical.test_v3_operations import scene

    ds = scene()
    paths, binding, source = _binding(tmp_path, [ds], "mesonh", {"3d": ["U"]})
    ds.isel({short_axis: slice(0, 2)}).to_netcdf(paths[0], engine="h5netcdf")
    with DatasetResources() as resources, pytest.raises(IndexError):
        groups, _ = _load(paths, binding, source, resources=resources)
        for group in groups.values():
            group.load()


def test_static_native_field_reads_the_requested_box_at_each_time(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_v3_polar import scene

    ds = scene(hours=(0, 1))
    ds["topo"] = (("nj", "ni"), np.arange(81.).reshape(9, 9), {"units": "m"})
    ds.to_netcdf(tmp_path / "input.nc")
    xr.Dataset(coords={
        "time": ds.time,
        "latitude": ("time", [ds.latitude.values[4, 4], ds.latitude.values[5, 6]],
                     {"units": "degrees_north"}),
        "longitude": ("time", [ds.longitude.values[4, 4], ds.longitude.values[5, 6]],
                      {"units": "degrees_east"}),
    }).to_netcdf(tmp_path / "track.nc")
    cfg = configuration(tmp_path, source={"variables": {"2d": ["q", "topo"]}},
                        region={"track": {"file": str(tmp_path / "track.nc")},
                                "width_km": {"x": 2, "y": 2}}, products={"model_grid": True})
    original, reads = H5NetCDFArrayWrapper._getitem, []

    def trace(array, key):
        result = original(array, key)
        if array.variable_name == "topo":
            reads.append(result.shape)
        return result

    monkeypatch.setattr(H5NetCDFArrayWrapper, "_getitem", trace)
    result = execute_simulation(cfg)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        np.testing.assert_array_equal(saved.topo.isel(time=0), ds.topo[3:6, 3:6])
        np.testing.assert_array_equal(saved.topo.isel(time=1), ds.topo[4:7, 5:8])
    assert reads and set(reads) == {(3, 3)}
