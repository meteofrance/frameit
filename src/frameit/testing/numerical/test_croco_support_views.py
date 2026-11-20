"""Owned CROCO support copies; these synthetic cases do not qualify real producers."""

import json
import subprocess
import sys
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from frameit.core.coupled import bind_sources
from frameit.core.execution import execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources
from frameit.io.netcdf_export import output_grid_layout
from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord
from frameit.processing.derived.wind import execute_source_operations
from frameit.testing.numerical.test_croco_vectors import vector_scene
from frameit.testing.numerical.test_v3_regions import configuration

INDEX_ATTRS = {"units": "1", "long_name": "authored native index", "note": "retained"}


def role_case(tmp_path, indices, fmt="netcdf", *, supplied_index=False, coexport_zeta=True,
              region=None):
    ds = vector_scene()
    ds.mask_rho.values[3, 2] = 0
    ds["w"] = xr.zeros_like(ds.temp).assign_attrs(
        units="meter second-1", standard_name="upward_sea_water_velocity")
    if supplied_index:
        ds = ds.assign_coords(s_rho_source_native_index=("s_rho", [0, 1, 2], INDEX_ATTRS))
    path = tmp_path / "ocean.nc"
    ds.to_netcdf(path, engine="h5netcdf")
    variables = {"3d": ["temp", "salt", "w", "u", "v"], "levels": {"indices": indices}}
    if coexport_zeta:
        variables["2d"] = ["zeta"]
    return configuration(tmp_path, {"ocean": {
        "model": "croco", "files": str(path), "variables": variables,
        "wind_pairs": [{"u": "u", "v": "v", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "transforms": [{"fields": ["u", "v"], "sampling": "mass",
                        "basis": "earth", "units": "m s-1"}],
    }}, output={"format": fmt}, region=region)


def assert_role_round_trip(tmp_path, conf, indices, fmt, index_attrs):
    source = tmp_path / "ocean.nc"
    before = source.read_bytes()
    result = execute_simulation(conf)
    assert result.ok and len(result.products) == 1
    subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
path, source, fmt, indices, attrs = sys.argv[1:]
indices, attrs = json.loads(indices), json.loads(attrs)
opener = xr.open_dataset if fmt == 'netcdf' else xr.open_zarr
options = {} if fmt == 'netcdf' else {'consolidated': False}
with opener(path, **options) as out, xr.open_dataset(source) as native:
    assert set(out.data_vars) == {'temp','salt','w','zeta','u','v'}
    assert 'zeta' in out.data_vars and 's_rho_source_native_index' in out.coords
    np.testing.assert_array_equal(out.s_rho_source_native_index, indices)
    assert out.s_rho_source_native_index.attrs == attrs
    np.testing.assert_array_equal(out.s_rho, native.s_rho[indices])
    np.testing.assert_array_equal(out.Cs_rho, native.Cs_rho[indices])
    for name in ('temp', 'salt', 'w'):
        np.testing.assert_array_equal(out[name], native[name].isel(s_rho=indices))
        assert out[name].attrs['units'] == native[name].attrs['units']
    np.testing.assert_array_equal(out.zeta, native.zeta)
    np.testing.assert_array_equal(out.time, native.time)
    assert out.latitude_rho.attrs == native.lat_rho.attrs
    assert out.longitude_rho.attrs == native.lon_rho.attrs
    np.testing.assert_array_equal(out.w, 0.)
    assert 's_rho' in out.w.dims and 's_w' not in out.w.dims
    for name, expected in (('u', -4.), ('v', 2.)):
        values = out[name].values
        assert np.isfinite(values).any()
        np.testing.assert_allclose(values[np.isfinite(values)], expected, atol=1e-12, rtol=0)
        assert np.isnan(out[name].isel(y_rho=0)).all()
        assert np.isnan(out[name].isel(y_rho=3, x_rho=3)).all()
        assert out[name].attrs['units'] == 'm s-1'
        assert out[name].attrs['current_reference_frame'] == 'earth'
    assert all(n in out for n in out.s_rho.attrs['formula_terms'].split()[1::2])
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(source), fmt, json.dumps(indices), json.dumps(index_attrs)],
        check=True, capture_output=True, text=True)
    assert source.read_bytes() == before


@pytest.mark.parametrize("indices", [[0, 2], [2, 0]])
@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_croco_supplied_index_round_trip(tmp_path, indices, fmt):
    conf = role_case(tmp_path, indices, fmt, supplied_index=True)
    assert_role_round_trip(tmp_path, conf, indices, fmt, INDEX_ATTRS)


@pytest.mark.parametrize("indices", [[0, 2], [2, 0]])
@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_croco_zeta_coexport_and_transform_roles(tmp_path, indices, fmt):
    conf = role_case(tmp_path, indices, fmt)
    assert_role_round_trip(tmp_path, conf, indices, fmt, {
        "units": "1", "long_name": "zero-based native source s_rho index"})


def test_croco_cropped_rho_geography_retains_coordinate_metadata(tmp_path):
    conf = role_case(tmp_path, [0, 2], region={
        "center": {"latitude": -20., "longitude": 60.},
        "width_km": {"x": 2., "y": 2.}})
    source = tmp_path / "ocean.nc"
    before = source.read_bytes()
    result = execute_simulation(conf)
    assert result.ok
    subprocess.run([sys.executable, "-c", """
import sys, xarray as xr
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source:
    assert out.latitude_rho.attrs == source.lat_rho.attrs
    assert out.longitude_rho.attrs == source.lon_rho.attrs
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(source)], check=True, capture_output=True, text=True)
    assert source.read_bytes() == before


def test_croco_coexported_mask_has_same_definition_with_or_without_analysis(tmp_path):
    conf = role_case(tmp_path, [0, 2], region={
        "center": {"latitude": -20., "longitude": 60.}, "width_km": {"x": 2., "y": 2.}})
    raw = deepcopy(conf.yaml_config)
    raw["sources"]["ocean"]["variables"]["2d"] = ["zeta", "mask_rho"]
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    raw["sources"]["ocean"].pop("transforms")
    raw["output"]["directory"] = str(tmp_path / "native")
    ordinary = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert ordinary.ok, ordinary
    with xr.open_dataset(result.products[0]["path"]) as currents, xr.open_dataset(
            ordinary.products[0]["path"]) as native, xr.open_dataset(tmp_path / "ocean.nc") as source:
        xr.testing.assert_identical(currents.mask_rho.variable, native.mask_rho.variable)
        assert currents.mask_rho.attrs["source_standard_name"] == "land_binary_mask"
        assert "standard_name" not in currents.mask_rho.attrs
        assert currents.mask_rho.attrs["option_0"] == "land"
        assert currents.mask_rho.attrs["option_1"] == "water"
        assert source.mask_rho.attrs["standard_name"] == "land_binary_mask"
        for name in ("zeta", "temp", "salt", "w"):
            xr.testing.assert_identical(currents[name].variable, native[name].variable)
        for name, expected in (("u", -4.), ("v", 2.)):
            values = currents[name].values
            assert np.isfinite(values).any()
            np.testing.assert_allclose(values[np.isfinite(values)], expected, atol=1e-12, rtol=0.)
            assert np.isnan(currents[name].where(currents.mask_rho == 0)).all()


@pytest.mark.parametrize("problem", ["indices", "labels", "attributes"])
def test_croco_role_normalization_preserves_conflict_rejection(tmp_path, problem):
    conf = role_case(tmp_path, [0, 2], coexport_zeta=False)
    _, children, sources = bind_sources(conf)
    child, source = children["ocean"], sources["ocean"]
    binding = child.source_requests["ocean"]["binding"]
    with DatasetResources() as resources:
        user, support = concat_nc2ds_by_vert_coord(
            [tmp_path / "ocean.nc"], {}, {}, resources=resources,
            selected_records=binding, source_plan=source)
        grid = binding["operations"][0]["grid_id"]
        ds = user[grid]
        index = "s_rho_source_native_index"
        if problem == "indices":
            ds = ds.assign_coords({index: ("s_rho", [0, 1], ds[index].attrs)})
        elif problem == "labels":
            ds = ds.assign_coords(s_rho=[-.9, -.2])
        else:
            ds = ds.assign_coords({index: ds[index].assign_attrs(definition="incompatible")})
        user[grid] = ds
        with pytest.raises(ValueError, match="conflicting|align"):
            execute_source_operations(user, support["internal"], source, binding, child)
    assert not conf.output_dir.exists()


def native_case(tmp_path, *, fields=None, products=None, fmt="netcdf", region=None):
    tmp_path.mkdir(exist_ok=True)
    ds = vector_scene()
    for name in ("lat_rho", "lat_u", "lat_v"):
        ds[name] = (ds[name] + .0065).assign_attrs(units="degree_north")
    for name in ("lon_rho", "lon_u", "lon_v"):
        ds[name] = (ds[name] + .007).assign_attrs(units="degree_east")
    ds["w"] = xr.zeros_like(ds.temp).assign_attrs(
        units="meter second-1", standard_name="upward_sea_water_velocity")
    for name, base in (("u", 0.), ("v", 2000.)):
        t, k, j, i = np.indices(ds[name].shape)
        ds[name].data = base + 1000*t + 100*k + 10*j + i
    j, i = np.indices(ds.h.shape)
    ds.h.data = 20. + j + i
    t, j, i = np.indices(ds.zeta.shape)
    ds.zeta.data = t + .01*j + .001*i
    ds.u.values[1, 0, 3, 3] = 0.
    ds.v.values[0, 2, 2, 3] = np.nan
    path = tmp_path / "input.nc"
    ds.to_netcdf(path, engine="h5netcdf")
    return configuration(tmp_path, {"ocean": {
        "model": "croco", "files": str(path), "variables": fields or {
            "2d": ["zeta"], "3d": ["temp", "u", "v", "w", "tracer_w"],
            "levels": {"indices": [0, 2]}},
    }}, region=region or {
        "center": {"latitude": -20., "longitude": 60.},
        "width_km": {"x": 2., "y": 2.}},
        products=products, output={"format": fmt})


@pytest.mark.parametrize("explicit_zeta_kind", [True, False])
def test_croco_coexported_zeta_retains_own_metadata_with_polar(tmp_path, explicit_zeta_kind):
    conf = native_case(
        tmp_path, fields={"2d": ["zeta"], "3d": ["temp", "salt"], "levels": {"indices": [0, 2]}},
        products={"model_grid": True, "track": True,
                  "polar": {"radius_km": 2, "radial_step_km": 2, "azimuth_count": 8}},
        region={"center": {"latitude": -20., "longitude": 60.},
                "width_km": {"x": 4., "y": 4.}})
    raw = deepcopy(conf.yaml_config)
    raw["sources"]["ocean"]["field_metadata"] = {
        name: {"kind": "continuous"}
        for name in (("temp", "salt", "zeta") if explicit_zeta_kind else ("temp", "salt"))}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    products = {p["role"]: p["path"] for p in result.products}
    with xr.open_dataset(products["model_grid"]) as grid, xr.open_dataset(products["polar"]) as polar:
        assert grid.zeta.attrs["kind"] == "continuous"
        assert grid.zeta.attrs["units"] == "meter"
        assert json.loads(grid.zeta.attrs["frameit_metadata_origins"]) == {
            "kind": "declaration" if explicit_zeta_kind else "documented_fallback", "units": "input"}
        assert "eta: zeta" in grid.s_rho.attrs["formula_terms"]
        t = xr.DataArray([0., 1.], dims="time")
        zeta = t + .01 * grid.eta_rho_source_native_index + .001 * grid.xi_rho_source_native_index
        np.testing.assert_array_equal(grid.zeta, zeta.transpose(*grid.zeta.dims))
        np.testing.assert_array_equal(grid.s_rho_source_native_index, [0, 2])
        assert np.isfinite(polar.temp).any() and np.isfinite(polar.salt).any()
        np.testing.assert_array_equal(polar.time, grid.time)


def model_grid_id(source, name):
    return source["requests"]["binding"]["products"]["model_grid"][name][
        "records"][0]["selection_grid_id"]


def test_croco_regional_layout_is_inventory_stable(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads

    conf = native_case(tmp_path / "all")
    guard_netcdf_payloads(monkeypatch, {
        "temp", "u", "v", "w", "tracer_w", "zeta", "h", "hc", "Cs_rho", "Cs_w"})
    _, _, sources = bind_sources(conf)
    source = sources["ocean"]
    layout = output_grid_layout(source, regional=True)
    primary = layout[model_grid_id(source, "temp")]
    assert primary["dimensions"]["eta_rho"] == "y_rho"
    assert primary["dimensions"]["xi_rho"] == "x_rho"
    assert primary["dimensions"]["s_rho"] == "s_rho"
    for name, inherited, base in (("u", "eta_rho", "y_rho"), ("v", "xi_rho", "x_rho")):
        facts = layout[model_grid_id(source, name)]
        owner = facts["horizontal_identity"]
        assert facts["dimensions"][inherited] == f"{base}_{owner}"
        assert facts["dimensions"]["s_rho"] == f"s_rho_support_{owner}"
        assert facts["support_views"]["h"]["stored_name"] == f"h_support_{owner}"
        for native, public in (("eta_rho", "y_rho"), ("xi_rho", "x_rho")):
            assert facts["support_views"]["h"]["dimensions"][native] == (
                f"{public}_support_{owner}")
        for dependency in ("s_rho", "Cs_rho", "zeta", "h", "hc"):
            assert facts["support_views"][dependency]["owner"] == owner
    other = native_case(tmp_path / "filtered", fields={
        "3d": ["v", "u", "temp"], "levels": {"indices": [0, 2]}},
        products={"model_grid": {"fields": {"ocean": ["u"]}}})
    _, _, filtered = bind_sources(other)
    second = output_grid_layout(filtered["ocean"], regional=True)
    retained = second[model_grid_id(filtered["ocean"], "u")]
    original = layout[model_grid_id(source, "u")]
    for key in ("dimensions", "support_views", "geography", "original_coordinates"):
        assert retained[key] == original[key]
    assert not conf.output_dir.exists() and not other.output_dir.exists()


def test_croco_face_aliases_preserve_c3_selection_guard(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads

    conf = native_case(tmp_path, fields={"3d": {
        "s_rho": {"names": ["temp", "u", "v"], "levels": {"indices": [2, 0]}},
        "s_w": {"names": ["tracer_w"], "levels": {"indices": [1]}},
    }})
    guard_netcdf_payloads(monkeypatch, {"temp", "u", "v", "tracer_w", "zeta", "h"})
    _, _, sources = bind_sources(conf)
    source = sources["ocean"]
    compatibility = output_grid_layout(source)
    regional = output_grid_layout(source, regional=True)
    for name in ("s_rho.temp", "s_rho.u", "s_rho.v"):
        grid = model_grid_id(source, name)
        assert compatibility[grid]["dimensions"]["s_rho"] == "s_rho"
        descriptor = source["requests"]["binding"]["products"]["model_grid"][name]
        assert descriptor["records"][0]["vertical"]["source_native_indices"] == [2, 0]
    u = regional[model_grid_id(source, "s_rho.u")]
    assert u["dimensions"]["s_rho"] != compatibility[model_grid_id(source, "s_rho.u")][
        "dimensions"]["s_rho"]
    assert regional[model_grid_id(source, "s_rho.temp")]["dimensions"]["s_rho"] == "s_rho"


def test_croco_default_layout_does_not_inherit_model_grid_aliases(tmp_path):
    conf = native_case(tmp_path)
    _, _, sources = bind_sources(conf)
    source = sources["ocean"]
    before = output_grid_layout(source)
    output_grid_layout(source, regional=True)
    after = output_grid_layout(source)
    assert after == before
    for name in ("temp", "u", "v"):
        assert after[model_grid_id(source, name)]["dimensions"]["s_rho"] == "s_rho"
        assert "support_views" not in after[model_grid_id(source, name)]


NATIVE_READER = """
import json, sys, numpy as np, xarray as xr
path, source, fmt, levels, mode = sys.argv[1:]
levels = json.loads(levels)
opener = xr.open_dataset if fmt == 'netcdf' else xr.open_zarr
options = {} if fmt == 'netcdf' else {'consolidated': False}
with opener(path, **options) as out, xr.open_dataset(source) as native:
    assert set(out.data_vars) == {'temp', 'u', 'v', 'w', 'tracer_w', 'zeta'}
    registry = json.loads(out.attrs['frameit_output_coordinates_json'])
    np.testing.assert_array_equal(out.time, native.time)
    np.testing.assert_array_equal(out.s_rho, native.s_rho[levels])
    np.testing.assert_array_equal(out.s_w, native.s_w[levels])
    assert out.w.dims[1] == 's_rho' and out.tracer_w.dims[1] == 's_w'
    for name in ('s_rho', 's_w'):
        np.testing.assert_array_equal(out[name + '_source_native_index'], levels)
        assert all(n in out for n in out[name].attrs['formula_terms'].split()[1::2])
    owners = {}
    for face, inherited in (('u', 'y_rho'), ('v', 'x_rho')):
        axis = out[face].dims[1]
        assert axis.startswith('s_rho_support_')
        owner = axis.removeprefix('s_rho_support_')
        owners[face] = owner
        assert inherited + '_' + owner in out[face].dims
        terms = dict(zip(out[axis].attrs['formula_terms'].split()[::2],
                         out[axis].attrs['formula_terms'].split()[1::2]))
        assert terms == {
            's:': axis, 'C:': 'Cs_rho_support_' + owner,
            'eta:': 'zeta_support_' + owner, 'depth:': 'h_support_' + owner,
            'depth_c:': 'hc_support_' + owner}
        np.testing.assert_array_equal(out[axis], native.s_rho[levels])
        np.testing.assert_array_equal(out[axis + '_source_native_index'], levels)
        np.testing.assert_array_equal(out['Cs_rho_support_' + owner], native.Cs_rho[levels])
        np.testing.assert_array_equal(out['hc_support_' + owner], native.hc)
        records = [r['support_views'] for r in registry.values() if 'support_views' in r
                   and r['support_views'].get('h', {}).get('owner') == owner]
        assert records and all(r['h']['native_name'] == 'h' for r in records)
        assert all(r['h']['stored_name'] == 'h_support_' + owner for r in records)
        assert all(r['h']['native_grid_ids'] for r in records)
        assert all(r['s_rho']['formula_terms'] == out[axis].attrs['formula_terms'] for r in records)

    def index_at(name, t):
        value = out[name]
        return value.isel(time=t).values if 'time' in value.dims else value.values

    def reference(name, t, ys, xs, vertical):
        value = native[name].isel(time=t) if 'time' in native[name].dims else native[name]
        data = value.values
        if vertical:
            data = data[levels]
        shape = (len(levels), len(ys), len(xs)) if vertical else (len(ys), len(xs))
        expected = np.full(shape, np.nan)
        for j, y in enumerate(ys):
            for i, x in enumerate(xs):
                if np.isfinite(y) and np.isfinite(x):
                    if vertical:
                        expected[:, j, i] = data[:, int(y), int(x)]
                    else:
                        expected[j, i] = data[int(y), int(x)]
        return expected

    for name, yindex, xindex, geo in (
        ('temp', 'eta_rho_source_native_index', 'xi_rho_source_native_index', 'rho'),
        ('w', 'eta_rho_source_native_index', 'xi_rho_source_native_index', 'rho'),
        ('tracer_w', 'eta_rho_source_native_index', 'xi_rho_source_native_index', 'rho'),
        ('u', 'y_rho_' + owners['u'] + '_source_native_index', 'xi_u_source_native_index', 'u'),
        ('v', 'eta_v_source_native_index', 'x_rho_' + owners['v'] + '_source_native_index', 'v'),
    ):
        assert out[name].dtype == native[name].dtype
        assert out[name].attrs['units'] == native[name].attrs['units']
        for t in range(native.sizes['time']):
            ys, xs = index_at(yindex, t), index_at(xindex, t)
            np.testing.assert_array_equal(out[name].isel(time=t),
                                          reference(name, t, ys, xs, True))
            for kind, raw in (('latitude', 'lat'), ('longitude', 'lon')):
                geo_values = out[kind + '_' + geo]
                if 'time' in geo_values.dims:
                    geo_values = geo_values.isel(time=t)
                np.testing.assert_array_equal(geo_values,
                    reference(raw + '_' + geo, t, ys, xs, False))
    for face, owner in owners.items():
        ydim, xdim = 'y_rho_support_' + owner, 'x_rho_support_' + owner
        assert ydim in out['h_support_' + owner].dims
        assert xdim in out['h_support_' + owner].dims
        if mode == 'fixed':
            assert (out.sizes[ydim], out.sizes[xdim]) == ((3, 7) if face == 'u' else (7, 3))
        for t in range(native.sizes['time']):
            ys = index_at(ydim + '_source_native_index', t)
            xs = index_at(xdim + '_source_native_index', t)
            for name, base in (('h', 'h'), ('zeta', 'zeta'),
                               ('lat_rho', 'latitude_rho'), ('lon_rho', 'longitude_rho')):
                value = out[base + '_support_' + owner]
                if 'time' in value.dims:
                    value = value.isel(time=t)
                np.testing.assert_array_equal(value.transpose(ydim, xdim),
                                              reference(name, t, ys, xs, False))
    if mode == 'fixed':
        assert (out.sizes['y_rho'], out.sizes['x_rho']) == (3, 3)
    if mode == 'edge':
        assert np.isnan(out.eta_rho_source_native_index).any()
        assert np.isnan(out.xi_rho_source_native_index).any()
    np.testing.assert_array_equal(out.w.values[np.isfinite(out.w.values)], 0.)
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
"""


def assert_native_round_trip(tmp_path, conf, levels, fmt, mode):
    source = tmp_path / "input.nc"
    before = source.read_bytes()
    result = execute_simulation(conf)
    assert result.ok and len(result.products) == 1
    checked = subprocess.run([sys.executable, "-c", NATIVE_READER, result.products[0]["path"],
                              str(source), fmt, json.dumps(levels), mode],
                             capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert source.read_bytes() == before
    return result


@pytest.mark.parametrize("levels", [[0, 2], [2, 0], [1]])
@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_croco_owned_support_round_trip(tmp_path, levels, fmt):
    conf = native_case(tmp_path, fields={
        "2d": ["zeta"], "3d": ["temp", "u", "v", "w", "tracer_w"],
        "levels": {"indices": levels}}, fmt=fmt)
    assert_native_round_trip(tmp_path, conf, levels, fmt, "fixed")


@pytest.mark.parametrize("mode", ["moving", "edge"])
@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_croco_moving_edge_support_preserves_native_samples(tmp_path, mode, fmt):
    if mode == "moving":
        path = tmp_path / "track.nc"
        xr.Dataset({
            "latitude": ("time", [-20., -19.9905], {"units": "degrees_north"}),
            "longitude": ("time", [60., 60.0095], {"units": "degrees_east"}),
        }, coords={"time": vector_scene().time}).to_netcdf(path, engine="h5netcdf")
        region = {"track": {"file": str(path)}, "width_km": {"x": 2., "y": 2.}}
    else:
        ds = vector_scene()
        latitude = float(ds.lat_rho[0, 0] + .25*(ds.lat_rho[1, 0] - ds.lat_rho[0, 0])) + .0065
        longitude = float(ds.lon_rho[0, 0] + .25*(ds.lon_rho[0, 1] - ds.lon_rho[0, 0])) + .007
        region = {"center": {"latitude": latitude, "longitude": longitude},
                  "width_km": {"x": 2., "y": 2.}}
    conf = native_case(tmp_path, fields={
        "2d": ["zeta"], "3d": ["temp", "u", "v", "w", "tracer_w"],
        "levels": {"indices": [2, 0]}}, fmt=fmt, region=region)
    assert_native_round_trip(tmp_path, conf, [2, 0], fmt, mode)


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_croco_owned_support_preview_and_chunk_dimensions(tmp_path, fmt):
    import yaml

    conf = native_case(tmp_path, fmt=fmt)
    _, _, sources = bind_sources(conf)
    source = sources["ocean"]
    facts = output_grid_layout(source, regional=True)[model_grid_id(source, "u")]
    target = facts["support_views"]["h"]["dimensions"]["xi_rho"]
    stored = facts["support_views"]["h"]["stored_name"]
    raw = deepcopy(conf.yaml_config)
    raw["products"]["model_grid"] = {"processing": {"chunks": {target: 2}}}
    raw["output"]["writer"]["chunks"] = {target: 2}
    if fmt == "zarr":
        raw["output"]["writer"]["shards"] = {target: 4}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    report, _, _ = bind_sources(conf)
    resources = report["layouts"]["products"]["ocean.model_grid"]
    assert target in resources["applicable_dimensions"]
    assert resources["applied_settings"] == {target: 2}
    preview = next(p for p in report["products"] if p["product"] == "model_grid")
    result = assert_native_round_trip(tmp_path, conf, [0, 2], fmt, "fixed")
    product = result.products[0]
    assert preview["dimensions"] == product["dimensions"]
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["products"][0]["fields"] == product["fields"]
    checked = subprocess.run([sys.executable, "-c", """
import sys, xarray as xr
path, fmt, stored, target = sys.argv[1:]
if fmt == 'netcdf':
    import netCDF4
    with netCDF4.Dataset(path) as source:
        axis = source[stored].dimensions.index(target)
        assert source[stored].chunking()[axis] == 2
else:
    import zarr
    source = zarr.open_group(path, mode='r')[stored]
    axis = source.metadata.dimension_names.index(target)
    assert source.chunks[axis] == 2 and source.shards[axis] == 4
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], fmt, stored, target], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr


@pytest.mark.parametrize("problem", [
    "axis", "owner", "collision", "formula_link", "bounds_link", "ancillary_link",
])
def test_croco_owned_support_rejects_unknown_axes_and_links(tmp_path, monkeypatch, problem):
    from frameit.core.coupled import _regional_dataset
    from frameit.io.netcdf_export import format_model_grid
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads

    conf = native_case(tmp_path)
    if problem == "axis":
        raw = deepcopy(conf.yaml_config)
        raw["output"]["writer"]["chunks"] = {"not_a_native_axis": 1}
        with pytest.raises(ValueError, match="Unknown.*dimensions"):
            bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))
        return
    _, children, sources = bind_sources(conf)
    child, source = children["ocean"], sources["ocean"]
    binding = child.source_requests["ocean"]["binding"]
    grid = model_grid_id(source, "u")
    with DatasetResources() as resources:
        user, _ = concat_nc2ds_by_vert_coord(
            [tmp_path / "input.nc"], {}, {}, resources=resources,
            selected_records=binding, source_plan=source)
        cropped = _regional_dataset(
            user[grid], grid, child, source, conf.simulation_parameter["region_centres"])
        layout = output_grid_layout(source, regional=True)
        views = layout[grid]["support_views"]
        if problem == "owner":
            views["h"]["owner"] = "another_view"
        elif problem == "collision":
            views["h"]["stored_name"] = views["zeta"]["stored_name"]
        elif problem == "formula_link":
            cropped = cropped.drop_vars("h")
        elif problem == "bounds_link":
            cropped.s_rho.attrs["bounds"] = "missing_sigma_bounds"
        else:
            cropped.u.attrs["ancillary_variables"] = "missing_support"
        guard_netcdf_payloads(monkeypatch, {
            "temp", "u", "v", "w", "tracer_w", "h", "zeta", "Cs_rho", "hc"})
        with pytest.raises(ValueError, match="owner|collision|missing|unresolved"):
            format_model_grid(cropped, grid, source, layout)
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("grouped", [False, True])
def test_croco_filtered_and_grouped_fields_keep_owned_views(tmp_path, grouped):
    complete = native_case(tmp_path / "all")
    all_result = execute_simulation(complete)
    if grouped:
        fields = {"3d": {
            "s_rho": {"names": ["v", "u"], "levels": {"indices": [0, 2]}},
        }}
        stored = "s_rho.u"
    else:
        fields = {"3d": ["v", "u"], "levels": {"indices": [0, 2]}}
        stored = "u"
    selected = native_case(tmp_path / "selected", fields=fields, products={
        "model_grid": {"fields": {"ocean": [stored]}}})
    selected_result = execute_simulation(selected)
    checked = subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as complete, xr.open_dataset(sys.argv[2]) as selected:
    field = sys.argv[3]
    assert set(selected.data_vars) == {field}
    assert selected[field].dims == complete.u.dims
    np.testing.assert_array_equal(selected[field], complete.u)
    owner = selected[field].dims[1].removeprefix('s_rho_support_')
    for name in complete.coords:
        if '_support_' + owner in name:
            assert name in selected.coords
            xr.testing.assert_identical(selected[name].variable, complete[name].variable)
    assert selected[selected[field].dims[1]].attrs == complete[complete.u.dims[1]].attrs
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", all_result.products[0]["path"], selected_result.products[0]["path"], stored],
        capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr


@pytest.mark.parametrize("cropped", [False, True])
def test_croco_mixed_polar_plan_keeps_unqualified_sigma(tmp_path, monkeypatch, cropped):
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads

    conf = native_case(tmp_path, fields={
        "3d": ["u", "temp"], "levels": {"indices": [0, 2]}},
        region=({"center": {"latitude": -20., "longitude": 60.}} if not cropped else None),
        products={
            "model_grid": {"fields": {"ocean": ["u"]}},
            "polar": {"radius_km": 1., "azimuth_count": 4, "fields": {"ocean": ["temp"]}},
        })
    path = tmp_path / "input.nc"
    with xr.open_dataset(path) as opened:
        fixture = opened.load()
    for name in ("lat_rho", "lat_u", "lat_v"):
        fixture[name].attrs["units"] = "degrees_north"
    for name in ("lon_rho", "lon_u", "lon_v"):
        fixture[name].attrs["units"] = "degrees_east"
    fixture.to_netcdf(path, mode="w", engine="h5netcdf")
    raw = deepcopy(conf.yaml_config)
    raw["sources"]["ocean"]["field_metadata"] = {"temp": {"kind": "continuous"}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    guard_netcdf_payloads(monkeypatch, {"temp", "u", "v", "h", "zeta", "Cs_rho", "hc"})
    report, _, _ = bind_sources(conf)
    polar = next(p for p in report["products"] if p["product"] == "polar")
    model = next(p for p in report["products"] if p["product"] == "model_grid")
    assert polar["dimensions"]["temp"] == ["time", "s_rho", "radius", "azimuth"]
    assert (model["dimensions"]["u"][1].startswith("s_rho_support_") if cropped
            else model["dimensions"]["u"] == ["time", "s_rho", "y_rho", "x_u"])
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("axis", ["xi_u", "eta_v"])
def test_croco_unrequested_horizontal_index_does_not_break_scalar_planning(
        tmp_path, monkeypatch, axis):
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads

    conf = native_case(tmp_path, fields={"3d": ["temp"], "levels": {"indices": [0, 2]}})
    path = tmp_path / "input.nc"
    with xr.open_dataset(path) as opened:
        ds = opened.load()
    ds = ds.assign_coords({
        f"{axis}_source_native_index": (axis, np.arange(6), INDEX_ATTRS)})
    ds.to_netcdf(path, mode="w", engine="h5netcdf")
    before = path.read_bytes()
    guard_netcdf_payloads(monkeypatch, {"temp", "u", "v", "h", "zeta"})
    report, _, _ = bind_sources(conf)
    assert report["products"][0]["dimensions"]["temp"] == ["time", "s_rho", "y_rho", "x_rho"]
    assert path.read_bytes() == before
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_croco_centre_only_region_keeps_uncropped_schema(tmp_path, fmt):
    conf = native_case(tmp_path, fields={"3d": ["u"], "levels": {"indices": [0, 2]}},
                       region={"center": {"latitude": -20., "longitude": 60.}}, fmt=fmt)
    path = tmp_path / "input.nc"
    before = path.read_bytes()
    report, _, _ = bind_sources(conf)
    assert report["products"][0]["dimensions"]["u"] == ["time", "s_rho", "y_rho", "x_u"]
    assert not any("_support_" in name for name in
                   report["layouts"]["products"]["ocean.model_grid"]["applicable_dimensions"])
    result = execute_simulation(conf)
    checked = subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
path, source, fmt = sys.argv[1:]
with (xr.open_dataset(path) if fmt == 'netcdf' else xr.open_zarr(path, consolidated=False)) as out:
    with xr.open_dataset(source) as native:
        assert out.u.dims == ('time', 's_rho', 'y_rho', 'x_u')
        np.testing.assert_array_equal(out.u, native.u.isel(s_rho=[0, 2]))
        assert not any('_support_' in name for name in out.variables)
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(path), fmt], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_croco_owned_support_retains_distinct_sigma_definitions(tmp_path, fmt):
    conf = native_case(tmp_path, fmt=fmt)
    with xr.open_dataset(tmp_path / "input.nc") as opened:
        native = opened.load()
    paths = []
    for field, suffix, labels in (
            ("u", "first", [-.9, -.5, -.1]), ("other_u", "second", [-.8, -.4, -.05])):
        ds = native[["u", "Cs_rho", "h", "zeta", "hc", "Vtransform"]].copy(deep=True)
        ds = ds.rename({name: f"{name}_{suffix}" for name in ("Cs_rho", "h", "zeta", "hc")})
        ds = ds.assign_coords(s_rho=("s_rho", labels, native.s_rho.attrs))
        ds.s_rho.attrs["formula_terms"] = (
            f"s: s_rho C: Cs_rho_{suffix} eta: zeta_{suffix} "
            f"depth: h_{suffix} depth_c: hc_{suffix}")
        if field != "u":
            ds = ds.rename(u=field)
        path = tmp_path / f"{suffix}.nc"
        ds.to_netcdf(path, engine="h5netcdf")
        paths.append(path)
    raw = deepcopy(conf.yaml_config)
    raw["sources"]["ocean"].update(
        files=[str(path) for path in paths],
        variables={"3d": ["u", "other_u"], "levels": {"indices": [0, 2]}})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    before = [path.read_bytes() for path in paths]
    report, _, _ = bind_sources(conf)
    assert report["products"][0]["dimensions"]["u"][1] != (
        report["products"][0]["dimensions"]["other_u"][1])
    result = execute_simulation(conf)
    checked = subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
path, fmt = sys.argv[1:3]
with (xr.open_dataset(path) if fmt == 'netcdf' else xr.open_zarr(path, consolidated=False)) as out:
    assert set(out.data_vars) == {'u', 'other_u'}
    assert out.u.dims[1] != out.other_u.dims[1]
    for field, source in zip(('u', 'other_u'), sys.argv[3:]):
        with xr.open_dataset(source) as native:
            axis = out[field].dims[1]
            np.testing.assert_array_equal(out[axis], native.s_rho[[0, 2]])
            np.testing.assert_array_equal(out[axis + '_source_native_index'], [0, 2])
            terms = out[axis].attrs['formula_terms'].split()[1::2]
            assert all(name in out for name in terms)
            np.testing.assert_array_equal(out[terms[1]], native[
                native.s_rho.attrs['formula_terms'].split()[3]][[0, 2]])
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], fmt, *map(str, paths)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert [path.read_bytes() for path in paths] == before


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("support", ["geography_bounds", "nested_ancillary"])
def test_croco_owned_support_carries_present_metadata_closure(tmp_path, fmt, support):
    conf = native_case(tmp_path, fields={"3d": ["u"], "levels": {"indices": [0, 2]}}, fmt=fmt)
    path = tmp_path / "input.nc"
    with xr.open_dataset(path) as opened:
        ds = opened.load()
    if support == "geography_bounds":
        ds.lat_rho.attrs["bounds"] = "lat_rho_bounds"
        ds = ds.assign_coords(lat_rho_bounds=(
            ("eta_rho", "xi_rho", "nv"),
            np.stack([ds.lat_rho.values - .005, ds.lat_rho.values + .005], axis=-1),
            {"units": "degree_north"}))
    else:
        ds.h.attrs["ancillary_variables"] = "h_error"
        ds["h_error"] = (ds.h * .01).assign_attrs(
            units="meter", ancillary_variables="h_quality")
        ds["h_quality"] = xr.zeros_like(ds.h, dtype="int8").assign_attrs(
            flag_values=np.array([0, 1], dtype="int8"), flag_meanings="usable suspect")
    ds.to_netcdf(path, mode="w", engine="h5netcdf")
    raw = deepcopy(conf.yaml_config)
    if support == "geography_bounds":
        raw["products"]["model_grid"] = {"processing": {"chunks": {"nv": 1}}}
        raw["output"]["writer"]["chunks"] = {"nv": 1}
        if fmt == "zarr":
            raw["output"]["writer"]["shards"] = {"nv": 2}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    report, children, sources = bind_sources(conf)
    if support == "geography_bounds":
        assert "nv" in report["layouts"]["products"]["ocean.model_grid"]["applicable_dimensions"]
    else:
        binding = children["ocean"].source_requests["ocean"]["binding"]
        assert {"h_error", "h_quality"} <= binding["dependencies"].keys()
        with DatasetResources() as resources:
            user, _ = concat_nc2ds_by_vert_coord(
                [path], {}, {}, resources=resources, selected_records=binding,
                source_plan=sources["ocean"])
            for name in ("h_error", "h_quality"):
                assert name in user[model_grid_id(sources["ocean"], "u")].coords
                assert hasattr(user[model_grid_id(sources["ocean"], "u")][name].data, "dask")
    before = path.read_bytes()
    result = execute_simulation(conf)
    checked = subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
path, source, fmt, support = sys.argv[1:]
with (xr.open_dataset(path) if fmt == 'netcdf' else xr.open_zarr(path, consolidated=False)) as out:
    with xr.open_dataset(source) as native:
        owner = out.u.dims[1].removeprefix('s_rho_support_')
        ydim, xdim = 'y_rho_support_' + owner, 'x_rho_support_' + owner
        if support == 'geography_bounds':
            geography = out['latitude_rho_support_' + owner]
            name = geography.attrs['bounds']
            assert name == 'lat_rho_bounds_support_' + owner and name in out.coords
            assert out.sizes['nv'] == 2
            values = out[name].transpose('time', ydim, xdim, 'nv')
            for t in range(out.sizes['time']):
                ys = out[ydim + '_source_native_index'].isel(time=t).values.astype(int)
                xs = out[xdim + '_source_native_index'].values.astype(int)
                np.testing.assert_array_equal(values.isel(time=t), native.lat_rho_bounds[
                    {'eta_rho': ys, 'xi_rho': xs}])
            if fmt == 'netcdf':
                import netCDF4
                with netCDF4.Dataset(path) as stored:
                    assert stored[name].chunking()[stored[name].dimensions.index('nv')] == 1
            else:
                import zarr
                stored = zarr.open_group(path, mode='r')[name]
                axis = stored.metadata.dimension_names.index('nv')
                assert stored.chunks[axis] == 1 and stored.shards[axis] == 2
        else:
            error, quality = 'h_error_support_' + owner, 'h_quality_support_' + owner
            assert out['h_support_' + owner].attrs['ancillary_variables'] == error
            assert out[error].attrs['ancillary_variables'] == quality
            assert error in out.coords and quality in out.coords
            np.testing.assert_array_equal(out[error], out['h_support_' + owner] * .01)
            np.testing.assert_array_equal(out[quality], 0)
            np.testing.assert_array_equal(out[quality].attrs['flag_values'], [0, 1])
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(path), fmt, support], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert path.read_bytes() == before
