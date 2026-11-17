"""Pressure-group names do not encode units; native decoder identity still does."""

import numpy as np
import pytest
import xarray as xr

from frameit.core.preflight import bind_source, inventory_source
from frameit.io.grib_utils import concat_grib2ds_by_vert_coord
from frameit.io.loader import DatasetResources
from frameit.testing.numerical.test_inspect_metadata import v3_config
from frameit.testing.numerical.test_v3_grib_reads import write_messages


@pytest.mark.parametrize("units,wanted", [
    ("Pa", 85000.),
    ("hPa", 850.),
])
def test_grib_isobaric_group_keeps_native_units_and_selected_payload(
    tmp_path, units, wanted,
):
    native, level = "isobaricInhPa", 850
    path = write_messages(tmp_path / "pressure.grib", [
        {"group": native, "hour": 1, "level": level, "missing": False},
    ])
    before = path.read_bytes()
    conf = v3_config(tmp_path, [path], model="arome", variables={"3d": {
        "isobaric": {"names": ["u"], "levels": {"values": [wanted], "units": units}},
    }})
    source = inventory_source(conf, "weather")
    field = next(value for value in source["fields"].values() if value["name"] == "u")
    assert field["group"] == "isobaric"
    assert field["attributes"]["GRIB_typeOfLevel"] == native
    binding = bind_source(conf, "weather")
    assert binding["status"] == "bound"
    with DatasetResources() as resources:
        groups, _ = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources)
        data = next(iter(groups.values())).load()
    wind = data["isobaric.u"]
    assert "isobaric" in wind.dims
    assert data.isobaric.attrs["units"] == units
    np.testing.assert_allclose(data.isobaric, [wanted], rtol=0, atol=1e-12)
    np.testing.assert_array_equal(
        wind.isel(time=0, isobaric=0),
        np.array([0., 1001. + level, 1002. + level, 9999., 1004. + level, 1005. + level])
        .reshape(2, 3),
    )
    assert path.read_bytes() == before


@pytest.mark.parametrize("source_axis", ["isobaric", "isobaricInhPa", "isobaricInPa"])
def test_netcdf_isobaric_selection_uses_coordinate_units(tmp_path, source_axis):
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

    path = tmp_path / "pressure.nc"
    xr.Dataset({"temperature": (("time", source_axis, "latitude", "longitude"),
                               np.broadcast_to(np.array([280., 270.])[None, :, None, None],
                                               (1, 2, 2, 2)), {"units": "K"})},
               coords={
                   "time": [np.datetime64("2000-01-01")],
                   source_axis: (source_axis, [85000., 70000.], {"units": "Pa", "axis": "Z"}),
                   "latitude": ("latitude", [-20., -19.], {"units": "degrees_north"}),
                   "longitude": ("longitude", [60., 61.], {"units": "degrees_east"}),
               }).to_netcdf(path)
    conf = v3_config(tmp_path, [path], model="arome", variables={"3d": {
        "isobaric": {"names": ["temperature"],
                     "levels": {"values": [700, 850], "units": "hPa"}},
    }})
    before = path.read_bytes()
    source = inventory_source(conf, "weather")
    binding = bind_source(conf, "weather")
    assert binding["status"] == "bound"
    records = binding["products"]["model_grid"]["isobaric.temperature"]["records"]
    assert records[0]["vertical"]["dimension"] == "isobaric"
    np.testing.assert_array_equal(records[0]["vertical"]["values"], [700., 850.])
    with DatasetResources() as resources:
        groups, _ = concat_nc2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources)
        data = next(iter(groups.values())).load()
    np.testing.assert_array_equal(data.isobaric, [700., 850.])
    np.testing.assert_array_equal(
        data["isobaric.temperature"].isel(time=0, latitude=0, longitude=0), [270., 280.])
    assert data.isobaric.attrs["units"] == "hPa"
    assert path.read_bytes() == before


@pytest.mark.parametrize("role", ["user", "tracker"])
def test_direct_grib_rejects_competing_pressure_representations(tmp_path, monkeypatch, role):
    cfgrib = pytest.importorskip("cfgrib")
    path = tmp_path / "input.grib"
    path.write_bytes(b"mocked cfgrib boundary")
    blocks = [
        xr.Dataset({"u": ((axis, "latitude", "longitude"), np.full((1, 2, 2), value),
                          {"units": "m s-1"})}, coords={
            axis: (axis, [level], {"units": units}),
            "latitude": [-20., -19.], "longitude": [60., 61.],
            "valid_time": np.datetime64("2000-01-01"),
        })
        for axis, level, units, value in (
            ("isobaricInhPa", 850., "hPa", 10.), ("isobaricInPa", 85000., "Pa", 20.))
    ]
    monkeypatch.setattr(cfgrib, "open_datasets", lambda *args, **kwargs: blocks)
    request = {"isobaric": {"variables": ["u"], "all_levels": True}}
    with pytest.raises(ValueError, match="isobaric.*conflicting.*units"):
        concat_grib2ds_by_vert_coord(
            [path], request if role == "user" else {},
            {"pressure_centroid": request} if role == "tracker" else {},
            index_dir=tmp_path / "indexes")
