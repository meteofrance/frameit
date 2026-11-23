"""Explicit polar wind requests: independent values, joint support and optionality."""

import hashlib
import json
import subprocess
import sys
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.configuration import capabilities, configuration_schema, resolve_schema
from frameit.core.coupled import bind_sources
from frameit.core.execution import execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_grouped_requests import grouped_document
from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads
from frameit.testing.numerical.test_v3_grib_reads import write_messages
from frameit.testing.numerical.test_v3_polar import configuration, scene

METHODS = {"outward": "radial_wind", "clockwise": "tangential_wind"}


def component_source(aliases=("outward", "clockwise")):
    return {
        "variables": {},
        "derived": {name: {"method": METHODS[name], "inputs": {"u": "U", "v": "V"}}
                    for name in aliases},
    }


def component_document(tmp_path, *, aliases=("outward", "clockwise"), source_name="atmosphere"):
    return {
        "schema_version": 3,
        "sources": {source_name: {
            "model": "mesonh", "files": str(tmp_path / "input.nc"),
            **component_source(aliases)}},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"polar": {"radius_km": 2.5, "azimuth_count": 8,
                               "fields": {source_name: list(aliases)}}},
        "output": {"directory": str(tmp_path / "output")},
        "resources": {"cpus": 1, "scheduler": "synchronous", "synchronous_export": True},
    }


def wind_scene(**kwargs):
    ds = scene(**kwargs)
    for name, value, standard in (("U", 3., "eastward_wind"), ("V", 4., "northward_wind")):
        ds[name] = xr.full_like(ds.q, value).assign_attrs(
            units="m s-1", kind="continuous", standard_name=standard)
    return ds


@pytest.mark.parametrize("aliases", [("outward",), ("clockwise",), ("outward", "clockwise")])
@pytest.mark.parametrize("source_name", ["atmosphere", "research"])
def test_explicit_components_schema_and_capabilities(tmp_path, aliases, source_name):
    raw = component_document(tmp_path, aliases=aliases, source_name=source_name)
    original = deepcopy(raw)
    effective, requests, polar = resolve_schema(raw)
    assert raw == original
    assert resolve_schema(effective)[0] == effective
    request = requests[source_name]
    assert request["exports"] == {"polar": list(aliases)}
    assert request["internal_inputs"] == ["U", "V"]
    assert request["fields"] == {"2d": [], "3d": []}
    assert request["derived"] == original["sources"][source_name]["derived"]
    assert polar == {source_name: list(aliases)}
    schema = configuration_schema()
    assert set(METHODS.values()) <= set(schema["$defs"]["choices_derived"]["enum"])
    support = capabilities()
    assert set(METHODS.values()) <= set(support["derived"])
    limits = " ".join(support["products"]["polar"]["limits"]).lower()
    assert all(word in limits for word in ("experimental", "strict", "atmospheric", "fa", "polar"))
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("alias", METHODS)
@pytest.mark.parametrize("problem,error", [
    ("model_grid", r"products.model_grid.*products.polar.fields"),
    ("implicit_model_grid", r"products.model_grid.*products.polar.fields"),
    ("fa", r"sources.atmosphere.derived.*FA"),
    ("ocean", r"sources.atmosphere.derived.*atmospher"),
    ("same", r"derived.*inputs.*distinct"),
    ("missing_key", r"derived.*inputs"),
    ("missing_field", r"sources.atmosphere.variables.*V.*unavailable"),
    ("collision", r"derived.*collid"),
])
def test_active_component_product_and_source_admission(
        tmp_path, monkeypatch, alias, problem, error):
    raw = component_document(tmp_path, aliases=(alias,))
    source = raw["sources"]["atmosphere"]
    inputs = source["derived"][alias]["inputs"]
    if problem in {"model_grid", "implicit_model_grid"}:
        raw["products"]["model_grid"] = (
            {"fields": {"atmosphere": [alias]}} if problem == "model_grid" else True)
    elif problem == "fa":
        source.update(model="arome", format="fa", profile="arome_history")
    elif problem == "ocean":
        source["model"] = "nemo"
    elif problem == "same":
        inputs["v"] = "U"
    elif problem == "missing_key":
        inputs.pop("v")
    elif problem == "missing_field":
        wind_scene().drop_vars("V").to_netcdf(tmp_path / "input.nc")
    elif problem == "collision":
        ds = wind_scene()
        ds[alias] = ds.q
        ds.to_netcdf(tmp_path / "input.nc")
    guard_netcdf_payloads(monkeypatch, {"q", "U", "V", alias})
    with pytest.raises(ValueError, match=error):
        conf = SimulationConfig.from_mapping_with_model_preset(raw)
        bind_sources(conf)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("alias,method", [
    *METHODS.items(), ("geometry_mapped", "radial_wind"), ("radial_bearing", "tangential_wind")])
def test_unused_component_declaration_does_not_activate_polar(tmp_path, monkeypatch, alias, method):
    from frameit.processing.polar import polar_proj

    scene().to_netcdf(tmp_path / "input.nc")  # U/V deliberately absent.
    monkeypatch.setattr(polar_proj, "xe", None)
    source = {"variables": {"2d": ["q"]},
              "derived": {alias: {"method": method, "inputs": {"u": "U", "v": "V"}}}}
    conf = configuration(tmp_path, source=source,
                         products={"model_grid": {"fields": {"atmosphere": ["q"]}}})
    _, children, _ = bind_sources(conf)
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    assert not binding["dependencies"]
    assert set(binding["products"]["model_grid"]) == {"q"}
    assert {record["name"] for record in binding["records"]} == {"q"}
    assert not binding["operation_plans"]
    assert not conf.output_dir.exists()
    result = execute_simulation(conf)
    assert result.ok and [item["role"] for item in result.products] == ["model_grid"]
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert set(saved.data_vars) == {"q"}
        np.testing.assert_array_equal(saved.q, 7.)


@pytest.mark.parametrize("method", METHODS.values())
@pytest.mark.parametrize("alias", [
    "geometry_mapped", "radial_bearing", "time", "rr", "rr_km", "theta", "theta_deg",
    "radius", "azimuth", "azimuth_degrees", "latitude", "longitude",
    "center_lat", "center_lon", "center_time", "center_latitude", "center_longitude",
    "radial_spacing_km", "max_azimuthal_spacing_m",
    "q_geometry_mapped", "q_support_fraction", "q_interpolation_status",
    "q_valid", "q_ring_coverage", "q_full_ring_valid",
])
def test_component_alias_cannot_replace_generated_polar_data(tmp_path, monkeypatch, method, alias):
    wind_scene(hours=(1,)).to_netcdf(tmp_path / "input.nc")
    raw = component_document(tmp_path)
    raw["sources"]["atmosphere"].update(
        variables={"2d": ["q"]},
        derived={alias: {"method": method, "inputs": {"u": "U", "v": "V"}}})
    raw["products"]["polar"]["fields"] = {"atmosphere": ["q", alias]}
    guard_netcdf_payloads(monkeypatch, {"q", "U", "V"})
    with pytest.raises(ValueError, match=f"derived.{alias}.*generated polar"):
        bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("alias,axis", [
    ("level", "level"), ("level_source_native_index", "level"),
    ("isobaric", "isobaric"),
    ("isobaric_source_native_index", "isobaric"),
    ("pressure", "isobaric"), ("pressure_source_native_index", "isobaric"),
])
def test_component_alias_cannot_replace_native_or_public_vertical_coordinates(
        tmp_path, monkeypatch, alias, axis):
    ds = wind_scene(hours=(1,))
    for name in ("U", "V"):
        ds[name] = ds[name].expand_dims({axis: [850., 700.]}, axis=1)
    ds[axis].attrs.update(units="hPa" if axis == "isobaric" else "m", axis="Z")
    ds.to_netcdf(tmp_path / "input.nc")
    raw = component_document(tmp_path)
    raw["sources"]["atmosphere"]["derived"] = {
        alias: {"method": "radial_wind", "inputs": {"u": "U", "v": "V"}}}
    raw["products"]["polar"]["fields"] = {"atmosphere": [alias]}
    guard_netcdf_payloads(monkeypatch, {"q", "U", "V"})
    with pytest.raises(ValueError, match=f"derived.{alias}.*generated polar"):
        bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not (tmp_path / "output").exists()


def test_component_quality_name_does_not_replace_another_selected_field(tmp_path, monkeypatch):
    ds = wind_scene(hours=(1,))
    ds["outward_support_fraction"] = ds.q
    ds.to_netcdf(tmp_path / "input.nc")
    raw = component_document(tmp_path, aliases=("outward",))
    raw["sources"]["atmosphere"]["variables"] = {"2d": ["outward_support_fraction"]}
    raw["products"]["polar"]["fields"]["atmosphere"].append("outward_support_fraction")
    guard_netcdf_payloads(monkeypatch, {"q", "U", "V", "outward_support_fraction"})
    with pytest.raises(ValueError, match="derived.outward.*generated polar"):
        bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not (tmp_path / "output").exists()


def test_component_alias_with_unused_quality_suffix_remains_valid(tmp_path, monkeypatch):
    wind_scene(hours=(1,)).to_netcdf(tmp_path / "input.nc")
    raw = component_document(tmp_path)
    raw["sources"]["atmosphere"].update(
        variables={"2d": ["q"]},
        derived={"q_support_fraction": {
            "method": "radial_wind", "inputs": {"u": "U", "v": "V"}}})
    raw["products"]["polar"]["fields"] = {"atmosphere": ["q_support_fraction"]}
    guard_netcdf_payloads(monkeypatch, {"q", "U", "V"})
    _, children, _ = bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    assert set(binding["products"]["polar"]) == {"q_support_fraction"}
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("alias", METHODS)
@pytest.mark.parametrize("problem,error", [
    ("matching", None), ("origins", None), ("nearest", None), ("missing_kind", None),
    ("renormalize", r"derived.*strict"),
    ("interpolation", r"derived.*interpolation"),
    ("sampling", r"derived.*sampling"),
    ("threshold", r"min_valid_weight_fraction"),
    ("categorical", r"derived.*categorical"),
    ("temporal", r"temporal"),
    ("basis", r"wind.*metadata|basis|reference"),
    ("rotation", r"rotation"),
    ("vertical", r"dimensions|collocat|align|only admitted W"),
    ("units", r"units"),
])
def test_component_pair_options_are_strict_and_compatible(tmp_path, monkeypatch, alias,
                                                         problem, error):
    ds = wind_scene(hours=(1,))
    raw = component_document(tmp_path, aliases=(alias,))
    source, polar = raw["sources"]["atmosphere"], raw["products"]["polar"]
    if problem in {"origins", "missing_kind"}:
        ds.V.attrs.pop("kind")
    if problem == "origins":
        source["field_metadata"] = {"V": {"kind": "continuous"}}
    elif problem == "nearest":
        polar["field_options"] = {"atmosphere": {
            name: {"interpolation": "nearest"} for name in ("U", "V")}}
    elif problem == "renormalize":
        polar.update(missing_data_policy="renormalize", min_valid_weight_fraction=.5)
    elif problem in {"interpolation", "sampling", "threshold"}:
        key, value = {"interpolation": ("interpolation", "nearest"),
                      "sampling": ("sampling", "native"),
                      "threshold": ("min_valid_weight_fraction", .75)}[problem]
        polar["field_options"] = {"atmosphere": {"V": {key: value}}}
    elif problem == "categorical":
        ds.V.attrs["kind"] = "categorical"
    elif problem == "temporal":
        ds.V.attrs["cell_methods"] = "time: mean"
    elif problem == "basis":
        ds.V.attrs["standard_name"] = "y_wind"
    elif problem == "rotation":
        for name in ("U", "V"):
            ds[name].attrs.pop("standard_name")
        source["wind_pairs"] = [{"u": "U", "v": "V", "basis": "grid"}]
    elif problem == "vertical":
        ds["V"] = ds.V.expand_dims(level_w=[10.], axis=1)
        ds.level_w.attrs.update(units="m", axis="Z")
    elif problem == "units":
        ds.V.attrs["units"] = "K"
    ds.to_netcdf(tmp_path / "input.nc")
    guard_netcdf_payloads(monkeypatch, {"q", "U", "V"})
    if error:
        with pytest.raises(ValueError, match=error):
            bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    else:
        conf = SimulationConfig.from_mapping_with_model_preset(raw)
        _, children, _ = bind_sources(conf)
        binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
        assert binding["status"] == "bound"
        assert set(binding["products"]["polar"]) == {alias}
        job, = binding["operation_plans"]
        options = job["polar_options"]
        assert options["U"]["kind"] == "continuous"
        assert options["V"].get("kind") == (None if problem == "missing_kind" else "continuous")
        assert {o["missing_data_policy"] for o in options.values()} == {"strict"}
        assert job["pair"] and set(job["input_binding"]["dependencies"]) == {"U", "V"}
        if problem == "origins":
            assert options["U"]["kind_origin"] == "input"
            assert options["V"]["kind_origin"] == "declaration"
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("problem", ["matching", "ambiguous", "unequal", "collision"])
def test_component_grouped_binding_preserves_identity_and_guards(tmp_path, monkeypatch, problem):
    import eccodes as ec

    write_messages(tmp_path / "input.grib", [
        {"hour": 1, "param": param, "group": group, "level": level, "missing": False}
        for param in (131, 132)
        for group, levels in (("heightAboveGround", (20, 40, 70)),
                              ("isobaric", (850, 700)))
        for level in levels])
    raw = grouped_document(tmp_path)
    source = raw["sources"]["atmosphere"]
    source["variables"].pop("2d")
    source["variables"]["3d"]["heightAboveGround"]["levels"] = {"indices": [2, 0]}
    source["variables"]["3d"]["isobaric"]["levels"] = {"indices": [1]}
    source["wind_pairs"] = [
        {**pair, "basis": "grid", "rotation": {"method": "geolocation"}}
        for pair in source["wind_pairs"]]
    source["derived"] = {
        alias: {"method": method, "inputs": {"u": f"{group}.u", "v": f"{group}.v"}}
        for (alias, method), group in zip(
            METHODS.items(), ("heightAboveGround", "isobaric"), strict=True)}
    source["field_metadata"] = {
        f"{group}.{name}": {"kind": "continuous"}
        for group in ("heightAboveGround", "isobaric") for name in ("u", "v")}
    raw["region"] = {"center": {"latitude": -20., "longitude": 60.}}
    raw["products"] = {"polar": {"radius_km": 2.5, "azimuth_count": 8,
                                 "fields": {"atmosphere": list(METHODS)}}}
    if problem == "ambiguous":
        source["derived"]["outward"]["inputs"]["u"] = "u"
    elif problem == "unequal":
        source["derived"]["outward"]["inputs"]["v"] = "isobaric.v"
    elif problem == "collision":
        source["derived"]["u"] = source["derived"].pop("outward")
        raw["products"]["polar"]["fields"]["atmosphere"] = ["u"]
    monkeypatch.setattr(ec, "codes_get_values", lambda *a, **kw: pytest.fail("scientific read"))
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if problem != "matching":
        error = {"ambiguous": "sources.atmosphere.*distinct fields",
                 "unequal": "different level selectors",
                 "collision": "derived.u.*collid"}[problem]
        with pytest.raises(ValueError, match=error):
            bind_sources(conf)
    else:
        _, children, _ = bind_sources(conf)
        binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
        assert binding["status"] == "bound"
        jobs = {job["name"]: job for job in binding["operation_plans"]}
        assert set(jobs) == set(METHODS)
        assert jobs["outward"]["vertical"]["source_native_indices"] == [2, 0]
        assert jobs["outward"]["vertical"]["values"] == [70, 20]
        assert jobs["clockwise"]["vertical"]["source_native_indices"] == [1]
        assert jobs["clockwise"]["vertical"]["values"] == [700]
        assert len({descriptor["field_id"] for descriptor in binding["dependencies"].values()}) == 4
    assert not (tmp_path / "out").exists()


def component_reader(path, fields, velocities, fmt="netcdf"):
    """Fresh ordinary readers check endpoint dot products, not FrameIt's rotation helper."""
    result = subprocess.run([sys.executable, "-c", """
import json, sys
import numpy as np
import xarray as xr
from pyproj import Geod
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
path, fmt = sys.argv[1], sys.argv[4]
fields, velocities = json.loads(sys.argv[2]), json.loads(sys.argv[3])
with (xr.open_zarr(path, consolidated=False) if fmt == 'zarr' else xr.open_dataset(path)) as ds:
    scientific = {n for n in ds.data_vars
                  if ds[n].attrs.get('frameit_role') != 'interpolation_quality'}
    assert scientific == set(fields), scientific
    assert ds.radius.attrs['units'] == 'km' and ds.azimuth.attrs['units'] == 'rad'
    assert ds.radial_bearing.dims == ('time', 'radius', 'azimuth')
    lon0 = np.broadcast_to(ds.center_longitude.values[:, None, None], ds.longitude.shape)
    lat0 = np.broadcast_to(ds.center_latitude.values[:, None, None], ds.latitude.shape)
    _, back, _ = Geod(ellps='WGS84').inv(lon0, lat0, ds.longitude.values, ds.latitude.values)
    bearing = np.deg2rad((back + 180.) % 360.)
    np.testing.assert_allclose(ds.radial_bearing[:, 1:], bearing[:, 1:], rtol=0, atol=2e-12)
    for name, (u, v) in velocities.items():
        value = ds[name]
        assert value.dims[0] == 'time' and value.dims[-2:] == ('radius', 'azimuth')
        angle = bearing.reshape((bearing.shape[0],) + (1,) * (value.ndim - 3) + bearing.shape[1:])
        u, v = np.asarray(u)[..., None, None], np.asarray(v)[..., None, None]
        method = value.attrs['frameit_method']
        expected = (u*np.sin(angle) + v*np.cos(angle) if method == 'radial_wind'
                    else u*np.cos(angle) - v*np.sin(angle))
        np.testing.assert_allclose(value[..., 1:, :], expected[..., 1:, :], rtol=0, atol=2e-10)
        assert np.isnan(value.isel(radius=0)).all()
        attrs = value.attrs
        assert attrs['units'] == 'm s-1'
        assert attrs['wind_reference_frame'] == 'earth'
        assert attrs['vector_basis'] == 'terminal_forward_geodesic'
        assert attrs['origin_policy'] == 'undefined_at_zero_radius'
        assert attrs['polar_support_definition'] == 'joint_finite_component_stencil'
        assert attrs['frameit_method_maturity'] == 'experimental_public_binding'
        assert 'standard_name' not in attrs
        assert ('outward' if method == 'radial_wind' else 'clockwise') in attrs['long_name']
        assert len(json.loads(attrs['polar_component_options'])) == 2
        assert len(json.loads(attrs['polar_numeric_types'])) == 2
        for linked in attrs['ancillary_variables'].split():
            assert linked in ds and ds[linked].attrs['frameit_role'] == 'interpolation_quality'
        np.testing.assert_array_equal(ds[name+'_interpolation_status'].isel(radius=0), 4)
        np.testing.assert_array_equal(
            ds[name+'_interpolation_status'].isel(radius=slice(1,None)), 0)
        np.testing.assert_array_equal(ds[name+'_support_fraction'], 1.)
        np.testing.assert_array_equal(ds[name+'_geometry_mapped'], 1)
        np.testing.assert_array_equal(ds[name+'_valid'].isel(radius=0), 0)
        np.testing.assert_array_equal(ds[name+'_ring_coverage'].isel(radius=0), 0)
        np.testing.assert_array_equal(ds[name+'_full_ring_valid'].isel(radius=0), 0)
        np.testing.assert_array_equal(ds[name+'_full_ring_valid'].isel(radius=slice(1,None)), 1)
    if fmt == 'zarr':
        import zarr
        group = zarr.open_group(path, mode='r')
        assert group.metadata.zarr_format == 3
        assert all(group[n].shards is not None for n in velocities)
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", str(path), json.dumps(fields), json.dumps(velocities), fmt],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("aliases", [("outward",), ("clockwise",), ("outward", "clockwise")])
@pytest.mark.parametrize("dtype", ["float64", "int16"])
@pytest.mark.parametrize("model", ["mesonh", "arome"])
def test_explicit_component_cardinal_signs_and_origin(tmp_path, aliases, dtype, model):
    from frameit.processing.derived.wind import polar_wind_components

    bearing = xr.DataArray(np.deg2rad([0., 90., 180., 270.]), dims="theta_deg")
    u, v = xr.full_like(bearing, 3.), xr.full_like(bearing, 4.)
    radial, tangential = polar_wind_components(u, v, bearing)
    np.testing.assert_allclose(radial, [4., 3., -4., -3.], rtol=0, atol=1e-12)
    np.testing.assert_allclose(tangential, [3., -4., -3., 4.], rtol=0, atol=1e-12)
    ds = wind_scene(hours=(1,))
    for name in ("U", "V"):
        ds[name] = ds[name].astype(dtype)
    if model == "arome":
        ds = ds.drop_vars(["latitude", "longitude"]).rename(
            time="valid_time", ni="longitude", nj="latitude").assign_coords(
                latitude=("latitude", ds.latitude[:, 0].values, {"units": "degrees_north"}),
                longitude=("longitude", ds.longitude[0, :].values, {"units": "degrees_east"}))
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, source={**component_source(aliases), "model": model})
    result = execute_simulation(conf)
    component_reader(result.products[0]["path"], list(aliases),
                     {name: [3., 4.] for name in aliases})
    with xr.open_dataset(result.products[0]["path"]) as saved:
        for name in aliases:
            types = json.loads(saved[name].attrs["polar_numeric_types"])
            assert all(item["evaluation_dtype"] == "float64" for item in types.values())
        assert not {"U", "V", "speed", "wind_speed", "vrad", "vtan"} & set(saved.data_vars)


@pytest.mark.parametrize("case", ["controlled", "zero_weight", "all_missing", "zero", "native"])
def test_explicit_components_use_joint_source_support(tmp_path, monkeypatch, case):
    import xesmf as xe

    ds = wind_scene(hours=(1,))
    if case in {"controlled", "zero_weight", "native"}:
        ds.U[0, 4, 5], ds.V[0, 5, 4] = np.nan, np.nan
    elif case == "all_missing":
        ds.U[:] = ds.V[:] = np.nan
    else:
        ds.U[:] = ds.V[:] = 0.
    ds.V.attrs.pop("kind")
    ds.to_netcdf(tmp_path / "input.nc")
    original_factory = xe.Regridder
    if case != "native":
        def prescribed(source, targets, method, **options):
            size = targets.lon.size
            nx = source.sizes["x_box"]
            columns = np.array([4*nx+4, 4*nx+5, 5*nx+4, 5*nx+5]) + 1
            weights = [.5, 0., 0., .5] if case == "zero_weight" else [.1, .2, .3, .4]
            return original_factory(source, targets, method, **options, weights={
                "row_dst": np.repeat(np.arange(1, size+1), 4),
                "col_src": np.tile(columns, size), "weights": np.tile(weights, size)})

        monkeypatch.setattr(xe, "Regridder", prescribed)
    source = component_source()
    source["variables"] = {"2d": ["U", "V", "q"]}
    source["derived"]["speed"] = {"method": "wind_speed", "inputs": {"u": "U", "v": "V"}}
    conf = configuration(tmp_path, source=source, products={
        "polar": {"radius_km": 10. if case == "native" else 2.5, "azimuth_count": 8}})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        saved.load()
        if case == "native":
            grid = xr.Dataset({"lon": ds.longitude, "lat": ds.latitude})
            targets = xr.Dataset({
                "lon": ("locations", saved.longitude.values.ravel()),
                "lat": ("locations", saved.latitude.values.ravel())})
            backend = original_factory(
                grid, targets, "bilinear", locstream_out=True, unmapped_to_nan=False)
            weights = backend.weights.data.to_scipy_sparse().tocsr()
            weights.data[np.abs(weights.data) <= 1e-14] = 0.
            weights.eliminate_zeros()
            joint = (np.isfinite(ds.U) & np.isfinite(ds.V)).values[0].ravel()
            sums = np.asarray(weights.sum(axis=1)).ravel()
            support = np.asarray(weights @ joint.astype(float)).ravel()
            support = np.divide(support, sums, out=np.zeros_like(support), where=sums > 0)
            support = support.reshape(saved.longitude.shape)
            assert np.any((support > 0) & (support < .999))
            assert np.any(sums == 0) and np.any(sums > 0)
            expected_status = np.where(sums.reshape(support.shape) == 0, 1,
                                       np.where(support < 1-1e-12, 2, 0))
        else:
            support = {"controlled": .5, "zero_weight": 1., "all_missing": 0., "zero": 1.}[case]
            expected_status = 2 if case in {"controlled", "all_missing"} else 0
        for name in METHODS:
            np.testing.assert_allclose(saved[name+"_support_fraction"], support, rtol=0, atol=1e-12)
            np.testing.assert_array_equal(
                saved[name+"_interpolation_status"].isel(radius=slice(1, None)),
                expected_status[:, 1:] if case == "native" else expected_status)
            np.testing.assert_array_equal(saved[name+"_interpolation_status"].isel(radius=0), 4)
            assert np.isnan(saved[name].isel(radius=0)).all()
            invalid = saved[name+"_interpolation_status"] != 0
            assert np.isnan(saved[name].where(invalid)).all()
            if case == "zero":
                np.testing.assert_array_equal(saved[name].isel(radius=slice(1, None)), 0.)
        if case == "controlled":
            np.testing.assert_allclose(saved.U_support_fraction, .8, atol=1e-12)
            np.testing.assert_allclose(saved.V_support_fraction, .7, atol=1e-12)
            np.testing.assert_allclose(saved.speed_support_fraction, .7, atol=1e-12)
        np.testing.assert_array_equal(saved.q_interpolation_status, 0 if case != "native" else (
            (sums == 0).reshape(saved.longitude.shape).astype(np.uint8)))


@pytest.mark.parametrize("latitude", [-60., 60.])
@pytest.mark.parametrize("moving", [False, True])
def test_explicit_component_terminal_bearing_and_motion(tmp_path, latitude, moving):
    ds = wind_scene(hours=(0, 2), spacing=100000.)
    lon, lat = np.meshgrid(
        179.5 + ds.ni.values / (111000*np.cos(np.deg2rad(latitude))),
        latitude + ds.nj.values / 111000)
    ds = ds.assign_coords(
        longitude=(("nj", "ni"), (lon+180) % 360-180, {"units": "degrees_east"}),
        latitude=(("nj", "ni"), lat, {"units": "degrees_north"}))
    ds.to_netcdf(tmp_path / "input.nc")
    region = {"center": {"latitude": latitude, "longitude": 179.5}}
    if moving:
        xr.Dataset({
            "latitude": ("time", [latitude, latitude+.03], {"units": "degrees_north"}),
            "longitude": ("time", [179.5, 179.55], {"units": "degrees_east"}),
        }, coords={"time": ds.time}).to_netcdf(tmp_path / "track.nc")
        region = {"track": {"file": str(tmp_path / "track.nc")}}
    conf = configuration(tmp_path, source=component_source(), region=region,
                         products={"polar": {"radius_km": 250., "azimuth_count": 8}})
    result = execute_simulation(conf)
    component_reader(result.products[0]["path"], list(METHODS),
                     {name: [3., 4.] for name in METHODS})
    with xr.open_dataset(result.products[0]["path"]) as saved:
        np.testing.assert_array_equal(saved.time, ds.time)
        np.testing.assert_array_equal(saved.center_time, ds.time)
        np.testing.assert_array_equal(saved.center_longitude, [179.5, 179.55 if moving else 179.5])
        assert float(abs(saved.radial_bearing.isel(radius=-1)-saved.azimuth).max()) > .01
        np.testing.assert_allclose(
            np.hypot(saved.outward, saved.clockwise).isel(radius=slice(1, None)),
            5., rtol=0, atol=1e-10)


@pytest.mark.parametrize("indices", [[2, 0], [0, 2], [1]])
def test_explicit_component_selected_reads_and_grouped_levels(tmp_path, monkeypatch, indices):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    ds = wind_scene()
    scale = xr.DataArray([1., 2., 3.], dims="level", coords={"level": [10., 20., 30.]})
    for name, value, standard in (("U", 10.8, "x_wind"), ("V", 14.4, "y_wind")):
        ds[name] = (xr.full_like(ds.q, value)*scale).transpose(
            "time", "level", "nj", "ni").assign_attrs(
                units="km/h", kind="continuous", standard_name=standard)
    ds.level.attrs.update(units="m", axis="Z")
    ds = ds.assign_coords(angle=xr.full_like(ds.latitude, 90.).assign_attrs(units="degree"))
    ds.to_netcdf(tmp_path / "input.nc")
    before = (tmp_path / "input.nc").read_bytes()
    source = component_source()
    source.update(variables={"3d": {"level": {
                      "names": ["U", "V"], "levels": {"indices": indices}}}},
                  wind_pairs=[{"u": "level.U", "v": "level.V", "basis": "grid",
                               "rotation": {"method": "coordinate", "coordinate": "angle"}}],
                  time={"values": ["2024-01-01T01:00:00"]},
                  reader={"chunks": {"time": 3, "level": 3}})
    for definition in source["derived"].values():
        definition["inputs"] = {"u": "level.U", "v": "level.V"}
    original, reads = H5NetCDFArrayWrapper.__getitem__, []

    def selected(array, key):
        if array.variable_name in {"U", "V"}:
            times = np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist()
            levels = np.atleast_1d(np.arange(array.shape[1])[key.tuple[1]]).tolist()
            assert times == [1] and set(levels) == set(indices)
            reads.append(array.variable_name)
        return original(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", selected)
    conf = configuration(tmp_path, source=source, products={
        "polar": {"radius_km": 2.5, "azimuth_count": 8, "fields": {"atmosphere": list(METHODS)}}})
    result = execute_simulation(conf)
    scales = np.array(indices)+1
    component_reader(result.products[0]["path"], list(METHODS), {
        name: [(-4*scales)[None, :].tolist(), (3*scales)[None, :].tolist()] for name in METHODS})
    with xr.open_dataset(result.products[0]["path"]) as saved:
        np.testing.assert_array_equal(saved.level_source_native_index, indices)
        np.testing.assert_array_equal(saved.level, ds.level.isel(level=indices))
    assert set(reads) == {"U", "V"}
    assert (tmp_path / "input.nc").read_bytes() == before


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("aliases", [("outward",), ("clockwise",), ("outward", "clockwise")])
def test_explicit_components_round_trip_and_base_speed_invariance(tmp_path, fmt, aliases):
    ds = wind_scene(hours=(1,))
    ds.to_netcdf(tmp_path / "input.nc")
    before = hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest()
    source = component_source()
    source["variables"] = {"2d": ["U", "V", "q"]}
    source["derived"]["speed"] = {"method": "wind_speed", "inputs": {"u": "U", "v": "V"}}
    outputs = []
    for suffix, extra in (("base", ()), ("components", aliases)):
        fields = ["U", "V", "q", "speed", *extra]
        conf = configuration(tmp_path, source=source, products={"polar": {
            "radius_km": 2.5, "azimuth_count": 8, "fields": {"atmosphere": fields}}},
            output_name=suffix, output_format=fmt)
        result = execute_simulation(conf)
        component_reader(result.products[0]["path"], fields,
                         {name: [3., 4.] for name in extra}, fmt)
        opener = xr.open_zarr if fmt == "zarr" else xr.open_dataset
        with opener(result.products[0]["path"], **(
                {"consolidated": False} if fmt == "zarr" else {})) as saved:
            outputs.append(saved.load())
    base, added = outputs
    for name in base.data_vars:
        xr.testing.assert_identical(base[name], added[name])
    np.testing.assert_allclose(added.speed.isel(radius=0), 5., rtol=0, atol=1e-12)
    for name, value in (("U", 3.), ("V", 4.), ("q", 7.)):
        np.testing.assert_allclose(added[name].isel(radius=0), value, rtol=0, atol=1e-12)
    assert hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest() == before
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    records = provenance["sources"]["atmosphere"]["polar"]["records"]
    assert {record["field"] for record in records} == set(fields)
    assert all(record["method"] == METHODS[record["field"]] for record in records
               if record["field"] in aliases)


@pytest.mark.parametrize("damage", ["missing", "misaligned", "nonfinite"])
def test_component_rejects_unproven_terminal_bearing(tmp_path, monkeypatch, damage):
    from frameit.processing.polar.polar_grid import PolarLonLatGrid

    wind_scene(hours=(1,)).to_netcdf(tmp_path / "input.nc")
    original = PolarLonLatGrid.build

    def broken(grid, *args, **kwargs):
        target = original(grid, *args, **kwargs)
        bearing = target.radial_bearing
        target = target.drop_vars("radial_bearing")
        if damage != "missing":
            target = target.assign_coords(radial_bearing=(
                bearing.rename(theta_deg="wrong_angle") if damage == "misaligned"
                else xr.full_like(bearing, np.nan)))
        return target

    monkeypatch.setattr(PolarLonLatGrid, "build", broken)
    with pytest.raises(ValueError, match="bearing"):
        execute_simulation(configuration(tmp_path, source=component_source()))
    assert not list((tmp_path / "output/products").glob("*.nc"))


def test_component_does_not_inherit_an_eastward_standard_name(tmp_path):
    wind_scene(hours=(1,)).to_netcdf(tmp_path / "input.nc")
    with xr.set_options(keep_attrs=True):
        result = execute_simulation(configuration(tmp_path, source=component_source(("outward",))))
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert "standard_name" not in saved.outward.attrs
        assert saved.outward.attrs["vector_basis"] == "terminal_forward_geodesic"


def test_existing_speed_renormalization_survives_selected_strict_component(tmp_path):
    ds = wind_scene(hours=(1,))
    ds.U[:, :, 5:], ds.V[:, 5:, :] = np.nan, np.nan
    ds["strictU"], ds["strictV"] = ds.U.copy(), ds.V.copy()
    ds.to_netcdf(tmp_path / "input.nc")
    source = component_source()
    source["variables"] = {"2d": ["U", "V", "q"]}
    for definition in source["derived"].values():
        definition["inputs"] = {"u": "strictU", "v": "strictV"}
    source["derived"]["speed"] = {"method": "wind_speed", "inputs": {"u": "U", "v": "V"}}
    outputs = []
    for suffix, extra in (("base", []), ("added", ["outward"])):
        options = {"radius_km": 2.5, "azimuth_count": 8,
                   "fields": {"atmosphere": ["U", "V", "q", "speed", *extra]},
                   "missing_data_policy": "renormalize", "min_valid_weight_fraction": .1}
        if extra:
            options["field_options"] = {"atmosphere": {
                name: {"missing_data_policy": "strict"} for name in ("strictU", "strictV")}}
        conf = configuration(tmp_path, source=source, products={"polar": options},
                             region={"center": {"latitude": -19.999, "longitude": 60.001}},
                             output_name=suffix)
        result = execute_simulation(conf)
        with xr.open_dataset(result.products[0]["path"]) as saved:
            outputs.append(saved.load())
    base, added = outputs
    for name in base.data_vars:
        xr.testing.assert_identical(base[name], added[name])
    assert not {"clockwise", "strictU", "strictV"} & set(added.data_vars)
    assert bool((added.speed_interpolation_status == 0).any())
    assert bool((added.outward_interpolation_status == 2).any())


def test_explicit_components_grib_reads_keep_grouped_clock_and_levels(tmp_path, monkeypatch):
    import eccodes as ec

    from frameit.io import grib_utils

    raw_path = write_messages(tmp_path / "native.grib", [
        {"hour": hour, "param": param, "group": group, "level": level, "missing": False}
        for hour in (0, 1, 2) for param in (131, 132)
        for group, levels in (("heightAboveGround", (20, 40, 70)),
                              ("isobaric", (850, 700))) for level in levels])
    path = tmp_path / "input.grib"
    with raw_path.open("rb") as stream, path.open("wb") as output:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                # Binary-exact constants isolate selection/rotation from GRIB packing error.
                factor = ec.codes_get(handle, "level")/10 * (ec.codes_get(handle, "endStep")+1)
                component = 3. if ec.codes_get(handle, "paramId") == 131 else 4.
                ec.codes_set(handle, "uvRelativeToGrid", 0)
                ec.codes_set_values(handle, np.full(6, component*factor))
                ec.codes_write(handle, output)
            finally:
                ec.codes_release(handle)
    path.chmod(0o444)
    before = path.read_bytes()
    raw = grouped_document(tmp_path)
    source = raw["sources"]["atmosphere"]
    source["variables"].pop("2d")
    source["variables"]["3d"]["heightAboveGround"]["levels"] = {"indices": [2, 0]}
    source["variables"]["3d"]["isobaric"]["levels"] = {"indices": [1]}
    source["time"] = {"values": ["2026-01-01T01:00:00"]}
    source["derived"] = {
        alias: {"method": method, "inputs": {"u": f"{group}.u", "v": f"{group}.v"}}
        for (alias, method), group in zip(
            METHODS.items(), ("heightAboveGround", "isobaric"), strict=True)}
    source["field_metadata"] = {
        f"{group}.{name}": {"kind": "continuous"}
        for group in ("heightAboveGround", "isobaric") for name in ("u", "v")}
    raw["region"] = {"center": {"latitude": -19.5, "longitude": 60.5}}
    raw["products"] = {"polar": {"radius_km": 2.5, "azimuth_count": 8,
                                 "fields": {"atmosphere": list(METHODS)}}}
    original, reads = grib_utils._grib_payload, []

    def selected(locator, shape, header):
        reads.append((header["shortName"], header["typeOfLevel"], header["level"],
                      header["endStep"], str(header["cycle"])))
        return original(locator, shape, header)

    monkeypatch.setattr(grib_utils, "_grib_payload", selected)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    bind_sources(conf)
    assert not reads
    result = execute_simulation(conf)
    assert set(reads) == {
        (name, group, level, 1, "2026-01-01T00:00:00.000000000")
        for name in ("u", "v") for group, levels in (
            ("heightAboveGround", (70, 20)), ("isobaricInhPa", (700,))) for level in levels}
    component_reader(result.products[0]["path"], list(METHODS), {
        "outward": [[[42., 12.]], [[56., 16.]]], "clockwise": [[[420.]], [[560.]]]})
    with xr.open_dataset(result.products[0]["path"]) as saved:
        np.testing.assert_array_equal(saved.height_above_ground, [70, 20])
        np.testing.assert_array_equal(saved.pressure, [700])
        np.testing.assert_array_equal(saved.height_above_ground_source_native_index, [2, 0])
        np.testing.assert_array_equal(saved.pressure_source_native_index, [1])
        np.testing.assert_array_equal(saved.time, [np.datetime64("2026-01-01T01", "ns")])
        np.testing.assert_array_equal(saved.center_time, saved.time)
    assert path.read_bytes() == before
