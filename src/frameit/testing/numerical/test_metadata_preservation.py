"""Retain evidenced time support and native indices without weakening strict checks."""

import hashlib
import json
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr

from frameit.core.coupled import bind_sources
from frameit.core.execution import execute_simulation
from frameit.core.preflight import inventory_source
from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads, v3_scene
from frameit.testing.numerical.test_v3_regions import configuration, preceding_sources


@pytest.mark.parametrize("metadata", [
    {}, {"GRIB_stepType": "instant"}, {"GRIB_stepType": "avg"},
    {"GRIB_stepType": "avg", "cell_methods": "time: point"},
    {"GRIB_stepType": "instant", "cell_methods": "time: mean"},
])
def test_netcdf_inventory_keeps_observed_time_metadata_without_payloads(
        tmp_path, monkeypatch, metadata):
    names = ("prmsl", "u10", "v10")
    ds = v3_scene(names=names, hours=(1, 2), model="AROME")
    for name in names:
        ds[name].attrs = {"units": "Pa" if name == "prmsl" else "m s-1", **metadata}
    path = tmp_path / "atmosphere.nc"
    ds.to_netcdf(path, engine="h5netcdf")
    before = path.read_bytes()
    conf = configuration(tmp_path, {"atmosphere": {
        "model": "arome", "files": str(path), "variables": {"2d": list(names)}}})
    guard_netcdf_payloads(monkeypatch, set(names))
    source = inventory_source(conf, "atmosphere")
    assert len(source["records"]) == 6
    for record in source["records"]:
        assert record["temporal_metadata"] == metadata
        assert source["fields"][record["field_id"]]["attributes"] == ds[record["name"]].attrs
    assert not conf.output_dir.exists()
    assert path.read_bytes() == before


@pytest.mark.parametrize("metadata,accepted", [
    ({"GRIB_stepType": "instant"}, True),
    ({}, False),
    ({"GRIB_stepType": "avg", "cell_methods": "time: point"}, False),
    ({"GRIB_stepType": "instant", "cell_methods": "time: mean"}, False),
])
def test_preceding_hour_checks_retained_evidence_and_keeps_native_clocks(
        tmp_path, monkeypatch, metadata, accepted):
    original = preceding_sources(tmp_path)
    sources = {"atmosphere": original["weather"], "ocean": original["water"]}
    path = tmp_path / "weather.nc"
    with xr.open_dataset(path) as opened:
        ds = opened.load()
    ds.scalar.attrs.pop("cell_methods")
    ds.scalar.attrs.update(metadata)
    ds.to_netcdf(path, mode="w")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.glob("*.nc")}
    conf = configuration(tmp_path, sources, region={
        "center": {"latitude": -20., "longitude": 60.},
        "width_km": {"x": 2., "y": 2.},
        "sources_coupling_time_association": "preceding_hour"})
    with monkeypatch.context() as guard:
        guard_netcdf_payloads(guard, {"scalar"})
        if not accepted:
            with pytest.raises(ValueError, match="explicitly instantaneous"):
                bind_sources(conf)
        else:
            bind_sources(conf)
    assert not conf.output_dir.exists()
    if accepted:
        result = execute_simulation(conf)
        assert result.ok
        ocean = next(p["path"] for p in result.products if p["source"] == "ocean")
        subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source:
    np.testing.assert_array_equal(out.time, source.time_counter)
    np.testing.assert_array_equal(out.time_bounds, source.time_bounds)
    np.testing.assert_array_equal(out.center_time, source.time_bounds[:, 1])
    np.testing.assert_array_equal(out.scalar, source.scalar.values[:, 2:5, 2:5])
    assert out.scalar.attrs == source.scalar.attrs
    assert out.time.attrs['bounds'] == 'time_bounds'
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", ocean, str(tmp_path / "water.nc")], check=True, capture_output=True, text=True)
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in tmp_path.glob("*.nc")} == before


def croco_metadata_case(tmp_path, indices, format="netcdf"):
    from frameit.testing.numerical.test_croco_vectors import vector_scene

    ds = vector_scene()
    ds.mask_rho.values[3, 2] = 0
    ds["w"] = xr.zeros_like(ds.temp).assign_attrs(
        units="meter second-1", standard_name="upward_sea_water_velocity")
    ds.to_netcdf(tmp_path / "ocean.nc", engine="h5netcdf")
    conf = configuration(tmp_path, {"ocean": {
        "model": "croco", "files": str(tmp_path / "ocean.nc"),
        "variables": {"3d": ["temp", "salt", "w", "u", "v"],
                      "levels": {"indices": indices}},
        "wind_pairs": [{"u": "u", "v": "v", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "transforms": [{"fields": ["u", "v"], "sampling": "mass",
                        "basis": "earth", "units": "m s-1"}],
    }}, output={"format": format})
    return conf


@pytest.mark.parametrize("indices", [[0, 2], [2, 0]])
@pytest.mark.parametrize("format", ["netcdf", "zarr"])
def test_mixed_croco_transform_retains_native_index_metadata(
        tmp_path, indices, format):
    conf = croco_metadata_case(tmp_path, indices, format)
    source = tmp_path / "ocean.nc"
    before = source.read_bytes()
    result = execute_simulation(conf)
    assert result.ok and len(result.products) == 1
    subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
path, source, fmt, indices = sys.argv[1:5]
indices = json.loads(indices)
with (xr.open_zarr(path, consolidated=False) if fmt == 'zarr' else xr.open_dataset(path)) as out:
    with xr.open_dataset(source) as native:
        assert set(out.data_vars) == {'temp', 'salt', 'w', 'u', 'v'}
        np.testing.assert_array_equal(out.s_rho, native.s_rho[indices])
        np.testing.assert_array_equal(out.s_rho_source_native_index, indices)
        expected = {
            'units': '1', 'long_name': 'zero-based native source s_rho index'}
        assert out.s_rho_source_native_index.attrs == expected
        np.testing.assert_array_equal(out.Cs_rho, native.Cs_rho[indices])
        for name in ('temp', 'salt', 'w'):
            np.testing.assert_array_equal(out[name], native[name].isel(s_rho=indices))
            assert out[name].attrs['units'] == native[name].attrs['units']
        np.testing.assert_array_equal(out.zeta, native.zeta)
        np.testing.assert_array_equal(out.time, native.time)
        np.testing.assert_array_equal(out.w, 0.)
        assert 's_rho' in out.w.dims and 's_w' not in out.w.dims
        for name, value in (('u', -4.), ('v', 2.)):
            data = out[name].values
            assert np.isfinite(data).any()
            np.testing.assert_allclose(data[np.isfinite(data)], value, atol=1e-12, rtol=0)
            assert np.isnan(out[name].isel(y_rho=0)).all()
            assert np.isnan(out[name].isel(y_rho=3, x_rho=3)).all()
            assert out[name].attrs['units'] == 'm s-1'
            assert out[name].attrs['current_reference_frame'] == 'earth'
        for name in out.s_rho.attrs['formula_terms'].split()[1::2]:
            assert name in out
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(source), format,
        json.dumps(indices)], check=True, capture_output=True, text=True)
    assert source.read_bytes() == before


@pytest.mark.parametrize("indices", [[0, 2], [2, 0]])
def test_operation_result_preserves_supplied_native_index_attributes(indices):
    from frameit.processing.derived.wind import execute_source_operations

    attrs = {"units": "1", "long_name": "original CROCO index definition",
             "provenance_note": "source coordinate"}
    time = np.datetime64("2024-01-01", "ns")
    labels = [-.9, -.5, -.1]
    native = xr.Dataset({
        "u": (("time", "s_rho"), [[1., 2., 3.]], {"units": "m s-1"}),
        "temperature": (("time", "s_rho"), [[280., 281., 282.]], {"units": "K"}),
    }, coords={"time": [time], "s_rho": labels,
               "s_rho_source_native_index": ("s_rho", [0, 1, 2], attrs)})
    selected = native.isel(s_rho=indices)
    operation = {
        "method": "transform", "name": "u", "model": "croco", "grid_id": "rho",
        "inputs": {"field": "u"}, "sampling": "native", "basis": "native",
        "preparation": "native_samples", "pair": None,
        "vertical": {
            "dimension": "s_rho", "positions": indices, "source_native_indices": indices,
            "values": [-.9, -.1] if indices == [0, 2] else [-.1, -.9], "units": None,
            "coordinates": {"s_rho_source_native_index": {
                "dimensions": ["s_rho"], "values": indices, "attributes": attrs}}},
        "geometry": {"coordinates": {"s_rho": {
            "dimensions": ["s_rho"], "values": labels, "attributes": {}}}, "attributes": {}},
        "input_binding": {"dependencies": {"u": {"records": [{
            "grid_id": "rho", "time": time, "field_id": "u",
            "vertical": {"dimension": "s_rho", "source_native_indices": indices}}]}}},
    }
    source = {"model": "croco", "format": "netcdf", "declaration": {},
              "fields": {"u": {"name": "u", "attributes": {"units": "m s-1"},
                               "time_varying": True}}}
    result = execute_source_operations(
        {"rho": selected.drop_vars("u")}, {"rho": native}, source,
        {"operations": [operation]}, None)
    assert result["rho"].s_rho_source_native_index.identical(selected.s_rho_source_native_index)
    xr.testing.assert_equal(result["rho"].u, selected.u)
    xr.testing.assert_identical(result["rho"].temperature, selected.temperature)


@pytest.mark.parametrize("conflict", ["indices", "labels", "attributes"])
def test_mixed_croco_transform_does_not_hide_genuine_coordinate_conflicts(tmp_path, conflict):
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord
    from frameit.processing.derived.wind import execute_source_operations

    conf = croco_metadata_case(tmp_path, [0, 2])
    _, children, sources = bind_sources(conf)
    child, source = children["ocean"], sources["ocean"]
    binding = child.source_requests["ocean"]["binding"]
    with DatasetResources() as resources:
        user, support = concat_nc2ds_by_vert_coord(
            [tmp_path / "ocean.nc"], {}, {}, resources=resources,
            selected_records=binding, source_plan=source)
        grid = binding["operations"][0]["grid_id"]
        assert grid in user
        ds = user[grid]
        index = "s_rho_source_native_index"
        if conflict == "indices":
            ds = ds.assign_coords({index: ("s_rho", [0, 1], ds[index].attrs)})
        elif conflict == "labels":
            ds = ds.assign_coords(s_rho=[-.9, -.2])
        else:
            ds = ds.assign_coords({index: ds[index].assign_attrs(
                definition="conflicting authored support")})
        user[grid] = ds
        with pytest.raises(ValueError, match="conflicting|align"):
            execute_source_operations(user, support["internal"], source, binding, child)
    assert not conf.output_dir.exists()
