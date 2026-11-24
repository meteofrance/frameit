"""Product-driven polar execution on compact, independently prescribed inputs."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.configuration import to_runtime
from frameit.core.coupled import bind_sources
from frameit.core.execution import execute_simulation
from frameit.core.settings_class import SimulationConfig


def scene(*, hours=(0, 1, 2), spacing=1000.):
    x = np.arange(-4, 5) * spacing
    lon, lat = np.meshgrid(60. + x / (111000 * np.cos(np.deg2rad(20))),
                           -20. + x / 111000)
    return xr.Dataset({
        "q": (("time", "nj", "ni"), np.full((len(hours), 9, 9), 7.),
              {"units": "K", "kind": "continuous"}),
    }, coords={
        "time": np.datetime64("2024-01-01T00", "ns") + np.array(hours, dtype="timedelta64[h]"),
        "ni": ("ni", x, {"units": "m"}), "nj": ("nj", x, {"units": "m"}),
        "latitude": (("nj", "ni"), lat, {"units": "degrees_north"}),
        "longitude": (("nj", "ni"), lon, {"units": "degrees_east"}),
    })


def configuration(tmp_path, *, source=None, products=None, region=None, sources=None,
                  output_name="output", output_format="netcdf"):
    return SimulationConfig(**to_runtime({
        "schema_version": 3, "run": {"name": "polar"},
        "sources": sources or {"atmosphere": {
            "model": "mesonh", "files": str(tmp_path / "input.nc"),
            "variables": {"2d": ["q"]}, **(source or {})}},
        "region": region or {"center": {"latitude": -20., "longitude": 60.}},
        "products": products or {"polar": {"radius_km": 2.5, "azimuth_count": 8}},
        "output": {"directory": str(tmp_path / output_name), "format": output_format},
        "resources": {"synchronous_export": True, "scheduler": "synchronous", "cpus": 1},
    }))


def test_polar_binding_reuses_identical_geometry_within_each_snapshot(tmp_path):
    ds = scene(hours=(0, 1))
    ds["other"] = ds.q.copy()
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, source={"variables": {"2d": ["q", "other"]}})
    _, children, _ = bind_sources(conf)

    def coordinates(config):
        jobs = config.source_requests["atmosphere"]["binding"]["operation_plans"]
        return [job["polar_geometry"]["longitude"] for job in jobs]

    child = coordinates(children["atmosphere"])
    parent = coordinates(conf)
    assert len(child) == len(parent) == 4
    for group in (child, parent):
        assert all(np.shares_memory(group[0], values) for values in group)
    assert not np.shares_memory(child[0], parent[0])


def test_polar_binding_checks_changed_geometry_even_with_the_same_inventory_id(tmp_path):
    from frameit.processing.polar.sampling import bind_polar_plan

    scene(hours=(0, 1)).to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path)
    _, children, sources = bind_sources(conf)
    child = children["atmosphere"]
    request = child.source_requests["atmosphere"]
    binding = request["binding"]
    first, second = binding["operation_plans"]
    assert first["grid_id"] == second["grid_id"]

    second["grid"] = deepcopy(second["grid"])
    coords = second["grid"]["coordinates"]
    coords["longitude"]["values"] += .25
    coords["ni"]["attributes"]["units"] = "cm"
    bind_polar_plan(sources["atmosphere"], request, binding, child)
    original, changed = (job["polar_geometry"] for job in (first, second))
    np.testing.assert_allclose(changed["longitude"] - original["longitude"], .25)
    assert changed["spacing"]["x"]["spacing_m"] == 10.

    second["grid"] = deepcopy(first["grid"])
    coords = second["grid"]["coordinates"]
    for name in ("longitude", "latitude"):
        # Same shape and physical byte order; different values on each named axis.
        values = np.ascontiguousarray(first["grid"]["coordinates"][name]["values"])
        first["grid"]["coordinates"][name]["values"] = values
        coords[name]["values"] = np.asfortranarray(values.T)
    bind_polar_plan(sources["atmosphere"], request, binding, child)
    original, changed = (job["polar_geometry"] for job in (first, second))
    np.testing.assert_allclose(changed["longitude"], original["longitude"].T)
    coords["longitude"]["attributes"]["units"] = "m"
    with pytest.raises(ValueError, match="unsupported angle units"):
        bind_polar_plan(sources["atmosphere"], request, binding, child)


def ordinary_reader(path, *, fields, values=None, origin_values=None, variable_attributes=None):
    subprocess.run([sys.executable, "-c", """
import json, sys
import numpy as np
import xarray as xr
assert not any(n == "frameit" or n.startswith("frameit.") for n in sys.modules)
with xr.open_dataset(sys.argv[1]) as ds:
    fields, values = json.loads(sys.argv[2]), json.loads(sys.argv[3])
    scientific = {n for n in ds.data_vars
                  if ds[n].attrs.get("frameit_role") != "interpolation_quality"}
    assert scientific == set(fields), scientific
    assert ds.attrs["product_type"] == "polar" and ds.attrs["frameit_version"]
    assert ds.radius.attrs["units"] == "km"
    assert ds.azimuth.attrs["units"] == "rad"
    assert ds.azimuth_degrees.attrs["units"] == "degrees"
    assert ds.azimuth.size == 8
    np.testing.assert_array_equal(ds.radius, [0., 1., 2., 2.5])
    np.testing.assert_array_equal(ds.azimuth_degrees, [0.,45.,90.,135.,180.,225.,270.,315.])
    assert ds.latitude.isel(radius=-1, azimuth=0).min() > -20.
    assert ds.longitude.isel(radius=-1, azimuth=2).min() > 60.
    assert not {"vrad", "vtan", "wind_speed", "U", "V"} & set(ds.data_vars) - set(fields)
    for n, v in values.items():
        np.testing.assert_allclose(ds[n], v, rtol=0, atol=1e-10)
        np.testing.assert_array_equal(ds[n + "_interpolation_status"], 0)
        np.testing.assert_array_equal(ds[n + "_support_fraction"], 1.)
        np.testing.assert_array_equal(ds[n + "_full_ring_valid"], 1)
    for n, v in json.loads(sys.argv[4]).items():
        np.testing.assert_allclose(ds[n].isel(radius=0, azimuth=0), v, rtol=0, atol=1e-8)
    for n, attrs in json.loads(sys.argv[5]).items():
        for key, value in attrs.items():
            assert ds[n].attrs[key] == value
    assert "center_time" in ds and "center_latitude" in ds and "center_longitude" in ds
assert not any(n == "frameit" or n.startswith("frameit.") for n in sys.modules)
""", str(path), json.dumps(fields), json.dumps(values or {}),
                    json.dumps(origin_values or {}), json.dumps(variable_attributes or {})],
        check=True, capture_output=True, text=True)


def test_polar_only_without_width_reads_selected_payload_and_real_sampler(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.processing.polar.regrid_plan import PolarRegridPlan

    path = tmp_path / "input.nc"
    scene().to_netcdf(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    conf = configuration(tmp_path, source={
        "time": {"values": ["2024-01-01T01:00:00"]},
        "reader": {"chunks": {"time": 3}},
    })
    reads, applications = [], []
    original_read, original_apply = H5NetCDFArrayWrapper.__getitem__, PolarRegridPlan.apply

    def read(array, key):
        if array.variable_name == "q":
            indices = np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist()
            reads.append(indices)
            assert indices == [1]
        return original_read(array, key)

    def apply(plan, field, *args, **kwargs):
        applications.append((field.name, plan.geometry.provenance["method"]))
        return original_apply(plan, field, *args, **kwargs)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", read)
    monkeypatch.setattr(PolarRegridPlan, "apply", apply)
    result = execute_simulation(conf)
    assert result.ok and len(result.products) == 1
    assert result.products[0]["role"] == "polar"
    assert result.products[0]["path"].endswith("products/polar.atmosphere.polar.nc")
    ordinary_reader(result.products[0]["path"], fields=["q"], values={"q": 7.})
    assert reads and ("q", "bilinear") in applications
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    binding = conf.source_requests["atmosphere"]["binding"]
    assert binding["status"] == "bound" and binding["polar_plan"]["status"] == "bound"
    assert set(binding["products"]) == {"polar"}
    assert set(binding["dependencies"]) == {"q"}
    assert not binding["operations"]
    with xr.open_dataset(result.products[0]["path"]) as ds:
        np.testing.assert_array_equal(ds.time, scene().time.isel(time=[1]))
        assert ds.attrs["last_radial_interval_km"] == .5
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    assert provenance["sources"]["atmosphere"]["polar"]["status"] == "executed"


@pytest.mark.parametrize("kind", [None, "continuous", "categorical"])
def test_polar_methods_use_optional_kind_and_preview_without_payload(
        tmp_path, monkeypatch, kind):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    ds = scene(hours=(0,))
    ds.q.attrs = {"units": "1"}
    if kind == "categorical":
        ds.q.attrs.update(flag_values=np.array([0., 7.]), flag_meanings="zero seven")
    ds.to_netcdf(tmp_path / "input.nc")
    original = H5NetCDFArrayWrapper.__getitem__

    def no_payload(array, key):
        assert array.variable_name != "q"
        return original(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", no_payload)
    conf = configuration(tmp_path, source={
        "field_metadata": {"q": {"kind": kind}} if kind == "continuous" else {},
    })
    _, children, _ = bind_sources(conf)
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    assert binding["polar_plan"]["status"] == "bound"
    job, = binding["operation_plans"]
    options = job["polar_options"]["q"]
    assert options["interpolation"] == ("nearest_s2d" if kind == "categorical" else "bilinear")
    if kind is None:
        assert "kind" not in options and "kind_origin" not in options
    else:
        assert options["kind"] == kind
        assert options["kind_origin"] == ("input" if kind == "categorical" else "declaration")
    assert not conf.output_dir.exists()


def test_polar_rejects_present_malformed_categorical_kind(tmp_path):
    ds = scene(hours=(0,))
    ds.q.attrs["kind"] = "categorical "
    ds.q.values[0, 4, 4:6] = [0., 2.]
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path)
    with pytest.raises(ValueError, match=r"polar\.q: invalid kind.*categorical"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("model", ["mesonh", "arome"])
def test_explicit_nearest_without_kind_preserves_native_samples(tmp_path, model):
    ds = scene(hours=(0,))
    ds.q.attrs.pop("kind")
    ds.q.values[0, 4, 5] = 42.
    ds.q.values[0, 4, 3] = np.nan
    center = {"latitude": -20., "longitude": float(
        ds.longitude[4, 4] + .2 * (ds.longitude[4, 5] - ds.longitude[4, 4]))}
    if model == "arome":
        ds = ds.rename(ni="x", nj="y").assign_attrs(model="AROME")
    ds.to_netcdf(tmp_path / "input.nc")
    products = {"polar": {
        "radius_km": 2.5, "azimuth_count": 8,
        "field_options": {"atmosphere": {"q": {"interpolation": "nearest"}}},
    }}
    outputs = []
    for kind in ("continuous", None):
        conf = configuration(
            tmp_path, source={"model": model, "field_metadata": (
                {"q": {"kind": kind}} if kind else {})}, products=products,
            region={"center": center}, output_name=f"nearest-{kind}")
        _, children, _ = bind_sources(conf)
        assert not conf.output_dir.exists()
        job, = children["atmosphere"].source_requests["atmosphere"]["binding"]["operation_plans"]
        assert job["polar_options"]["q"]["interpolation"] == "nearest_s2d"
        if kind is None:
            assert "kind" not in job["polar_options"]["q"]
            assert "kind" not in job["polar_input_metadata"]["q"]["origins"]
        result = execute_simulation(conf)
        assert result.ok and len(result.products) == 1
        with xr.open_dataset(result.products[0]["path"]) as saved:
            outputs.append(saved.load())
            assert saved.q.attrs["units"] == "K"
            assert saved.longitude.isel(radius=0, azimuth=0).item() > 60.
            assert saved.q.isel(radius=0, azimuth=0).item() == 7.
            assert saved.q.isel(radius=1, azimuth=2).item() == 42.
            assert np.isnan(saved.q.isel(radius=1, azimuth=6).item())
            assert saved.q_geometry_mapped.isel(radius=1, azimuth=6).item() == 1
            assert saved.q_interpolation_status.isel(radius=1, azimuth=6).item() == 2
            assert saved.q_support_fraction.isel(radius=1, azimuth=6).item() == 0
    assert "kind" not in outputs[1].q.attrs
    outputs[0].q.attrs.pop("kind")
    outputs[0].q.attrs.pop("frameit_metadata_origins")
    for out in outputs:
        out.attrs.pop("history")
    xr.testing.assert_identical(*outputs)


@pytest.mark.parametrize("options", [
    {"interpolation": "bilinear"},
    {"interpolation": "nearest", "sampling": "mass"},
    {"interpolation": "nearest", "units": "hPa"},
])
def test_polar_optional_kind_for_bilinear_or_preparation(tmp_path, options):
    ds = scene(hours=(0,))
    ds.q.attrs = {"units": "Pa"}
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, products={"polar": {
        "radius_km": 2.5, "azimuth_count": 8,
        "field_options": {"atmosphere": {"q": options}},
    }})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert "kind" not in saved.q.attrs
        assert saved.q.attrs["units"] == options.get("units", "Pa")
        assert saved.q.attrs["polar_interpolation"] == (
            "bilinear" if options["interpolation"] == "bilinear" else "nearest_s2d")
        np.testing.assert_allclose(saved.q, .07 if "units" in options else 7.)


@pytest.mark.parametrize("kind", [None, "continuous"])
def test_polar_rejects_a_later_wide_integer_record(tmp_path, kind):
    paths = []
    for hour, dtype, value in ((0, "float64", 7.), (1, "int64", 2**53 + 1)):
        ds = scene(hours=(hour,))
        ds.q.attrs.pop("kind")
        ds["q"] = ds.q.copy(data=np.full(ds.q.shape, value, dtype=dtype))
        paths.append(str(tmp_path / f"{hour}.nc"))
        ds.to_netcdf(paths[-1])
    source = {"files": paths, "field_metadata": {"q": {"kind": kind}} if kind else {}}
    conf = configuration(tmp_path, source=source, products={"polar": {
        "radius_km": 2.5, "azimuth_count": 8,
        "field_options": {"atmosphere": {"q": {"interpolation": "nearest"}}},
    }})
    with pytest.raises(ValueError, match=r"\[E1602\].*q.*int64"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def test_polar_rejects_nonnumeric_decoded_samples(tmp_path):
    ds = scene(hours=(0,))
    ds.q.attrs = {"units": "seconds since 2024-01-01"}
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, products={"polar": {
        "radius_km": 2.5, "azimuth_count": 8,
        "field_options": {"atmosphere": {"q": {"interpolation": "nearest"}}},
    }})
    with pytest.raises(ValueError, match=r"\[E1602\].*q.*datetime64"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


@pytest.mark.parametrize(("product", "field"), [
    ("model_grid", "q"), ("polar", "q"), ("model_grid", "instrument.q"),
])
def test_explicit_product_fields_need_no_source_list(tmp_path, monkeypatch, product, field):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    ds = scene()
    ds["other"] = ds.q.copy()
    ds.rename(q=field).to_netcdf(tmp_path / "input.nc")
    spec = {"fields": {"atmosphere": [field]}}
    if product == "polar":
        spec.update(radius_km=2.5, azimuth_count=8)
    original, reads, outputs, locators = H5NetCDFArrayWrapper.__getitem__, [], [], []

    def read(array, key):
        assert array.variable_name != "other"
        if array.variable_name == field:
            indices = np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist()
            assert indices == [1]
            reads.append(array.variable_name)
        return original(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", read)
    for listed in (True, False):
        conf = configuration(tmp_path, source={
            "variables": {"2d": [field]} if listed else {},
            "time": {"values": ["2024-01-01T01:00:00"]},
        }, products={product: spec}, output_name=f"selection-{listed}")
        reads.clear()
        _, children, _ = bind_sources(conf)
        assert not reads and not conf.output_dir.exists()
        request = children["atmosphere"].source_requests["atmosphere"]
        assert request["fields"]["2d"] == ([field] if listed else [])
        locators.append([r["locator"] for r in request["binding"]["records"]])
        result = execute_simulation(conf)
        assert reads and result.ok and [p["role"] for p in result.products] == [product]
        with xr.open_dataset(result.products[0]["path"]) as saved:
            assert {n for n in saved.data_vars if saved[n].attrs.get("frameit_role")
                    != "interpolation_quality"} == {field}
            np.testing.assert_allclose(saved[field], 7., atol=1e-10)
            outputs.append(saved.load())
    assert locators[0] == locators[1]
    for out in outputs:
        out.attrs.pop("history")
    xr.testing.assert_identical(*outputs)


def test_product_selection_requires_a_declared_source_and_unique_native_field(tmp_path):
    sources = {"variables": {}}
    with pytest.raises(ValueError, match="unknown source"):
        configuration(tmp_path, source=sources, products={
            "model_grid": {"fields": {"typo": ["q"]}}})
    ds = scene()
    ds.to_netcdf(tmp_path / "input.nc")
    with pytest.raises(ValueError, match="absent.*unavailable"):
        bind_sources(configuration(tmp_path, source=sources, products={
            "model_grid": {"fields": {"atmosphere": ["absent"]}}}))
    ds.q.attrs["units"] = "Pa"
    ds.to_netcdf(tmp_path / "other.nc")
    with pytest.raises(ValueError, match="distinct fields.*q"):
        bind_sources(configuration(tmp_path, source={
            **sources, "files": [str(tmp_path / name) for name in ("input.nc", "other.nc")],
        }, products={"model_grid": {"fields": {"atmosphere": ["q"]}}}))
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("case", ["literal", "collision", "duplicate"])
def test_product_only_dotted_references_resolve_one_native_field(tmp_path, case):
    ds = scene(hours=(0,)).assign_coords(level=("level", [42.], {"axis": "Z", "units": "m"}))
    ds["anchor"] = ds.q.expand_dims(level=ds.level, axis=1)
    if case != "duplicate":
        ds["level.Q"] = ds.q.copy(data=np.full(ds.q.shape, 1030.))
    if case != "literal":
        ds["Q"] = ds.anchor.copy(data=np.full(ds.anchor.shape, 130.))
    ds.drop_vars("q").to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, source={"variables": {"3d": {"level": {"names": ["anchor"]}}}},
                         products={"polar": {"radius_km": 2.5, "azimuth_count": 8,
                             "fields": {"atmosphere": (
                                 ["Q", "level.Q"] if case == "duplicate" else ["level.Q"])}}})
    if case != "literal":
        message = "distinct fields.*level.Q" if case == "collision" else "duplicate field request"
        with pytest.raises(ValueError, match=message):
            bind_sources(conf)
        assert not conf.output_dir.exists()
        return
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert "level" not in saved["level.Q"].dims
        np.testing.assert_allclose(saved["level.Q"], 1030., atol=1e-10)


def test_product_only_grib_wind10m_does_not_use_3d_height_selector(tmp_path):
    from frameit.testing.numerical.test_v3_grib_reads import write_messages

    surface = _write_arome_wind10m(tmp_path / "surface.grib2", headers=({},))
    upper = write_messages(tmp_path / "height.grib2", [{"group": "heightAboveGround", "level": 20}])
    conf = configuration(tmp_path, source={"model": "arome", "files": list(map(str, [surface, upper])),
        "variables": {"3d": {"heightAboveGround": {"names": ["u"], "levels": {"values": [20]}}}}},
        products={"model_grid": {"fields": {"atmosphere": ["u10"]}}})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert saved.u10.dims[0] == "time" and saved.u10.shape == (1, 7, 7)
        assert saved.u10.values[0, 3, 3] == 3.
    record, = conf.source_requests["atmosphere"]["binding"]["records"]
    assert record["level"] == 10
    assert conf.input_files == [str(surface)]


def _compare_optional_kind(tmp_path, source, field, center, *, guard):
    outputs = {}
    products = {"model_grid": True, "polar": {"radius_km": 2.5, "azimuth_count": 8}}
    for origin in ("declaration", None):
        conf = configuration(tmp_path, source={
            **source, "field_metadata": (
            {field: {"kind": "continuous"}} if origin else {}),
        }, region={"center": center}, products=products, output_name=origin or "unlabeled")
        with guard():
            report, children, _ = bind_sources(conf)
        assert not conf.output_dir.exists()
        assert not any(w.startswith("[W1603]") for w in report["warnings"])
        binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
        jobs = [job for job in binding["operation_plans"] if job["product"] == "polar"]
        assert jobs and all(job["polar_options"][field].get("kind_origin") == origin for job in jobs)
        result = execute_simulation(conf)
        assert result.ok and {p["role"] for p in result.products} == {"model_grid", "polar"}
        for product in result.products:
            with xr.open_dataset(product["path"]) as saved:
                assert saved[field].attrs.get("kind") == ("continuous" if origin else None)
                origins = saved[field].attrs.pop("frameit_metadata_origins", "{}")
                assert json.loads(origins).get("kind") == origin
                saved[field].attrs.pop("kind", None)
                saved.attrs.pop("history")
                outputs.setdefault(product["role"], []).append(saved.load())
        provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
        assert not any(w.startswith("[W1603]") for w in provenance.get("warnings", []))
        records = provenance["sources"]["atmosphere"]["polar"]["records"]
        assert records and all(r["options"][field]["interpolation"] == "bilinear" for r in records)
        assert all(r["input_metadata"][field]["origins"].get("kind") == origin for r in records)
    for pair in outputs.values():
        xr.testing.assert_identical(*pair)
    return {product: pair[1] for product, pair in outputs.items()}


@pytest.mark.parametrize("field", ["UM10", "VM10"])
def test_mesonh_wind10m_polar_optional_kind(tmp_path, monkeypatch, field):
    from contextlib import contextmanager

    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads

    ds = scene(hours=(0, 1)).rename(q=field)
    ds[field].attrs = {"units": "m s-1"}
    ds[field].values[:, 4, 4:6] = [3., 7.]
    ds[field].values[:, 4, 2] = np.nan
    ds.to_netcdf(tmp_path / "input.nc")
    center = {"latitude": -20., "longitude": float(
        ds.longitude[4, 4] + .25 * (ds.longitude[4, 5] - ds.longitude[4, 4]))}

    @contextmanager
    def guard():
        with monkeypatch.context() as patch:
            guard_netcdf_payloads(patch, {field})
            yield

    products = _compare_optional_kind(
        tmp_path, {"variables": {"2d": [field]}}, field, center, guard=guard)
    np.testing.assert_allclose(products["polar"][field].isel(radius=0, azimuth=0),
                               [4., 4.], atol=2e-3, rtol=0)
    np.testing.assert_array_equal(products["model_grid"][field], ds[field])
    np.testing.assert_array_equal(products["polar"].time, ds.time)

    native_only = configuration(tmp_path, source={"variables": {"2d": [field]}},
                                products={"model_grid": True})
    _, children, _ = bind_sources(native_only)
    record = children["atmosphere"].source_requests["atmosphere"]["binding"][
        "products"]["model_grid"][field]["records"][0]
    assert "field_metadata" not in record


@pytest.mark.parametrize("problem", ["later_text", "label", "declared_label", "other_model"])
def test_mesonh_polar_checks_later_dtype_not_field_label(tmp_path, problem):
    ds = scene(hours=(0,)).rename(q="UM10")
    ds.UM10.attrs = {"units": "m s-1"}
    source = {"variables": {"2d": ["UM10"]}}
    if problem == "label":
        ds.UM10.attrs["standard_name"] = "air_temperature"
    elif problem == "declared_label":
        source["field_metadata"] = {"UM10": {"standard_name": "air_temperature"}}
    elif problem == "other_model":
        source["model"] = "arome"
        ds = ds.rename(ni="x", nj="y").assign_attrs(model="AROME")
    path = tmp_path / "input.nc"
    ds.to_netcdf(path)
    if problem == "later_text":
        later = ds.assign_coords(time=ds.time + np.timedelta64(1, "h"))
        later["UM10"] = later.UM10.copy(data=np.full(later.UM10.shape, "text"))
        later.to_netcdf(tmp_path / "later.nc")
        source["files"] = [str(path), str(tmp_path / "later.nc")]
    conf = configuration(tmp_path, source=source)
    if problem == "later_text":
        with pytest.raises(ValueError, match=r"\[E1602\].*UM10.*numeric"):
            bind_sources(conf)
    else:
        bind_sources(conf)
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("observed", [False, True])
def test_mesonh_polar_respects_flags_or_declared_kind(tmp_path, observed):
    ds = scene(hours=(0,)).rename(q="UM10")
    ds.UM10.attrs = {"units": "m s-1"}
    source = {"variables": {"2d": ["UM10"]}}
    if observed:
        ds.UM10.attrs.update(flag_values=np.array([0., 7.]), flag_meanings="zero seven")
    else:
        source["field_metadata"] = {"UM10": {"kind": "categorical"}}
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, source=source)
    _, children, _ = bind_sources(conf)
    job, = children["atmosphere"].source_requests["atmosphere"]["binding"]["operation_plans"]
    options = job["polar_options"]["UM10"]
    assert options["kind_origin"] == ("input" if observed else "declaration")
    assert options["kind"] == "categorical" and options["interpolation"] == "nearest_s2d"
    assert not conf.output_dir.exists()


def test_polar_keeps_known_kind_and_clock_resolution(tmp_path):
    ds = scene(hours=(0,)).rename(time="valid_time")
    ds.q.attrs.update(GRIB_stepType="max", cell_methods="time: maximum")
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path)
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert saved.q.attrs["kind"] == "continuous"
        assert saved.q.attrs["cell_methods"] == "time: maximum"
        np.testing.assert_array_equal(saved.time, ds.valid_time)


@pytest.mark.parametrize("kept_hour", [0, 1])
def test_polar_does_not_label_coexported_records(tmp_path, kept_hour):
    ds = scene(hours=(0, 1)).rename(q="UM10")
    ds.UM10.attrs = {"units": "m s-1"}
    ds.to_netcdf(tmp_path / "input.nc")
    ocean = scene(hours=(kept_hour,)).rename(
        time="time_counter", nj="y", ni="x", latitude="nav_lat", longitude="nav_lon")
    ocean.to_netcdf(tmp_path / "ocean.nc")
    conf = configuration(tmp_path, sources={
        "atmosphere": {"model": "mesonh", "files": str(tmp_path / "input.nc"),
                       "variables": {"2d": ["UM10"]}},
        "ocean": {"model": "nemo", "files": str(tmp_path / "ocean.nc"),
                  "variables": {"2d": ["q"]}},
    }, products={"model_grid": True, "polar": {"radius_km": 2.5, "azimuth_count": 8,
        "fields": {"atmosphere": ["UM10"]}}}, region={
            "center": {"latitude": -20., "longitude": 60.},
            "sources_coupling_time_association": "common"})
    _, children, _ = bind_sources(conf)
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    records = binding["products"]["model_grid"]["UM10"]["records"]
    assert all("field_metadata" not in r for r in records)
    result = execute_simulation(conf)
    for product in (p for p in result.products if p["source"] == "atmosphere"):
        with xr.open_dataset(product["path"]) as saved:
            assert "kind" not in saved.UM10.attrs
            if product["role"] == "model_grid":
                np.testing.assert_array_equal(saved.time, ds.time)
            else:
                np.testing.assert_array_equal(saved.time, ds.time.isel(time=[kept_hour]))


def test_initial_gaps_stay_missing_when_polar_kind_is_unlabeled(tmp_path):
    ds = scene(hours=(0, 1))
    ds.to_netcdf(tmp_path / "input.nc")
    late = ds.isel(time=[1]).rename(q="UM10")
    late.UM10.attrs = {"units": "m s-1"}
    late.to_netcdf(tmp_path / "later.nc")
    conf = configuration(tmp_path, source={
        "files": [str(tmp_path / name) for name in ("input.nc", "later.nc")],
        "variables": {"2d": ["q", "UM10"]}, "allow_initial_gaps": ["UM10"],
    })
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert saved.UM10.isel(time=0).isnull().all()
        np.testing.assert_array_equal(saved.UM10_interpolation_status.isel(time=0), 2)
        assert "kind" not in saved.UM10.attrs
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    absent, observed = [r for r in provenance["sources"]["atmosphere"]["polar"]["records"]
                        if r["field"] == "UM10"]
    assert absent["source_record_absent"]
    assert not observed.get("source_record_absent")
    for record in (absent, observed):
        assert record["options"]["UM10"]["interpolation"] == "bilinear"
        assert "kind" not in record["options"]["UM10"]


def _write_arome_wind10m(path, *, component=2, headers=({}, {})):
    ec = pytest.importorskip("eccodes")
    with path.open("wb") as stream:
        for hour, override in enumerate(headers):
            handle = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
            try:
                for key, value in {
                    "centre": 85, "subCentre": 0, "tablesVersion": 15, "localTablesVersion": 0,
                    "discipline": 0, "parameterCategory": 2, "parameterNumber": component,
                    "productDefinitionTemplateNumber": 0, "typeOfFirstFixedSurface": 103,
                    "scaleFactorOfFirstFixedSurface": 0, "scaledValueOfFirstFixedSurface": 10,
                    "typeOfSecondFixedSurface": 255, "generatingProcessIdentifier": 204,
                    "Ni": 7, "Nj": 7, "latitudeOfFirstGridPoint": -20_030_000,
                    "latitudeOfLastGridPoint": -19_970_000, "longitudeOfFirstGridPoint": 59_970_000,
                    "longitudeOfLastGridPoint": 60_030_000, "iDirectionIncrement": 10_000,
                    "jDirectionIncrement": 10_000, "jScansPositively": 1,
                    "dataDate": 20260101, "dataTime": 0, "forecastTime": hour,
                    "bitmapPresent": 1, **override,
                }.items():
                    ec.codes_set_long(handle, key, value)
                ec.codes_set_double(handle, "missingValue", 9999.)
                values = np.tile([1., 9999., 2., 3., 7., 8., 9.], (7, 1))
                ec.codes_set_values(handle, values.ravel())
                ec.codes_write(handle, stream)
            finally:
                ec.codes_release(handle)
    return path


@pytest.mark.parametrize(("component", "field"), [(2, "u10"), (3, "v10")])
def test_arome_grib2_wind10m_polar_optional_kind(tmp_path, monkeypatch, component, field):
    from contextlib import contextmanager

    ec = pytest.importorskip("eccodes")
    path = _write_arome_wind10m(tmp_path / "wind.grib2", component=component)
    before = path.read_bytes()

    @contextmanager
    def guard():
        with monkeypatch.context() as patch:
            patch.setattr(ec, "codes_get_values", lambda *_: pytest.fail("scientific payload"))
            yield

    products = _compare_optional_kind(tmp_path, {
        "model": "arome", "files": str(path), "variables": {"2d": [field]},
    }, field, {"latitude": -20., "longitude": 60.0025}, guard=guard)
    polar = products["polar"]
    np.testing.assert_allclose(polar[field].isel(radius=0, azimuth=0), [4., 4.], atol=2e-3, rtol=0)
    assert (polar[f"{field}_interpolation_status"] == 2).any()
    np.testing.assert_array_equal(polar.time, products["model_grid"].time)
    assert path.read_bytes() == before


@pytest.mark.parametrize("header", [
    {"tablesVersion": 16}, {"localTablesVersion": 1}, {"generatingProcessIdentifier": 254},
])
def test_arome_polar_does_not_require_kind_matching_wire_codes(tmp_path, header):
    path = _write_arome_wind10m(tmp_path / "wind.grib2", headers=({}, header))
    source = {"model": "arome", "files": str(path), "variables": {"2d": ["u10"]}}
    conf = configuration(tmp_path, source=source)
    _, children, plans = bind_sources(conf)
    assert len(plans["atmosphere"]["records"]) == 2
    jobs = children["atmosphere"].source_requests["atmosphere"]["binding"]["operation_plans"]
    assert all("kind" not in job["polar_options"]["u10"] for job in jobs)
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("stage", ["reader", "payload"])
def test_arome_polar_rechecks_selected_field_before_payload(tmp_path, monkeypatch, stage):
    from contextlib import contextmanager

    from frameit.io import grib_utils
    from frameit.io.loader import DatasetResources

    ec = pytest.importorskip("eccodes")
    path = _write_arome_wind10m(tmp_path / "wind.grib2", headers=({"uvRelativeToGrid": 0},))
    conf = configuration(tmp_path, source={
        "model": "arome", "files": str(path), "variables": {"2d": ["u10"]}})
    _, children, plans = bind_sources(conf)
    source = plans["atmosphere"]
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    original = grib_utils._grib_message

    @contextmanager
    def different_header(locator):
        with original(locator) as handle:
            ec.codes_set_long(handle, "uvRelativeToGrid", 1)
            yield handle

    monkeypatch.setattr(ec, "codes_get_values", lambda *_: pytest.fail("scientific payload"))
    with DatasetResources() as resources:
        if stage == "reader":
            monkeypatch.setattr(grib_utils, "_grib_message", different_header)
            with pytest.raises(ValueError, match="header changed after inventory"):
                grib_utils._selected_grib([path], binding, source, resources)
        else:
            _, views = grib_utils._selected_grib([path], binding, source, resources)
            monkeypatch.setattr(grib_utils, "_grib_message", different_header)
            with pytest.raises(ValueError, match="message changed after binding"):
                next(iter(views["internal"].values())).load(scheduler="synchronous")


def _croco_surface_scene():
    from frameit.testing.numerical.test_croco_vectors import vector_scene

    ds = vector_scene()[["zeta", "mask_rho", "scrum_time"]]
    ds["zeta"] = ds.zeta.copy(deep=True)
    ds.zeta.values[:, 3, 3] = [0., 2.]
    ds.zeta.values[:, 3, 4] = [4., 6.]
    ds.zeta.values[:, 3, 1] = 41.
    ds.mask_rho.values[3, 1] = 0.
    ds.zeta.values[:, 3, 5] = np.nan
    return ds


def test_croco_history_zeta_polar_optional_kind(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads

    ds = _croco_surface_scene()
    path = tmp_path / "history.nc"
    ds.to_netcdf(path)
    center = {"latitude": -20., "longitude": float(
        ds.lon_rho[3, 3] + .25 * (ds.lon_rho[3, 4] - ds.lon_rho[3, 3]))}

    @contextmanager
    def guard():
        with monkeypatch.context() as patch:
            guard_netcdf_payloads(patch, {"zeta"})
            yield

    source = {"model": "croco", "files": str(path), "variables": {"2d": ["zeta"]}}
    products = _compare_optional_kind(tmp_path, source, "zeta", center, guard=guard)
    polar, native = products["polar"], products["model_grid"]
    np.testing.assert_allclose(polar.zeta.isel(radius=0, azimuth=0), [1., 3.], atol=2e-3, rtol=0)
    assert (polar.zeta_interpolation_status == 2).any()
    np.testing.assert_array_equal(native.zeta, ds.zeta)
    np.testing.assert_array_equal(native.time, ds.time)
    np.testing.assert_array_equal(native.scrum_time, ds.scrum_time)
    assert native.zeta.attrs["units"] == "meter"

    native_only = configuration(tmp_path, source=source, products={"model_grid": True})
    _, children, _ = bind_sources(native_only)
    record = children["atmosphere"].source_requests["atmosphere"]["binding"][
        "products"]["model_grid"]["zeta"]["records"][0]
    assert "field_metadata" not in record


@pytest.mark.parametrize("declared", [False, True])
@pytest.mark.parametrize("wet_dry", [False, True])
def test_croco_polar_checks_science_file_with_separate_mask(tmp_path, declared, wet_dry):
    ds = _croco_surface_scene()
    first, later, mask = (tmp_path / f"{name}.nc" for name in ("first", "later", "mask"))
    ds.isel(time=[0]).to_netcdf(first)
    second = ds.isel(time=[1])
    second[["mask_rho", "scrum_time"]].to_netcdf(mask)
    second.drop_vars("mask_rho").assign_attrs(
        {"CPP-options": "MASKING WET_DRY" if wet_dry else "MASKING"}).to_netcdf(later)
    conf = configuration(tmp_path, source={
        "model": "croco", "files": list(map(str, (first, later, mask))),
        "variables": {"2d": ["zeta"]},
        "field_metadata": {"zeta": {"kind": "continuous"}} if declared else {},
    })
    if wet_dry:
        with pytest.raises(ValueError, match=r"later\.nc.*WET_DRY"):
            bind_sources(conf)
        assert not conf.output_dir.exists()
    else:
        bind_sources(conf)
        result = execute_simulation(conf)
        with xr.open_dataset(result.products[0]["path"]) as saved:
            np.testing.assert_allclose(saved.zeta.isel(radius=0, azimuth=0), [0., 2.])


@pytest.mark.parametrize("problem", ["label", "later_layout"])
def test_croco_zeta_polar_does_not_require_kind_matching_labels_or_layout(tmp_path, problem):
    ds = _croco_surface_scene()
    path = tmp_path / "history.nc"
    source = {"model": "croco", "files": [str(path)], "variables": {"2d": ["zeta"]}}
    if problem == "label":
        ds.zeta.attrs["standard_name"] = "sea_surface_height_above_geoid"
    else:
        later = ds.isel(time=[1])
        later["zeta"] = later.zeta.transpose("eta_rho", "xi_rho", "time")
        later.to_netcdf(tmp_path / "later.nc")
        source["files"].append(str(tmp_path / "later.nc"))
        ds = ds.isel(time=[0])
    ds.to_netcdf(path)
    conf = configuration(tmp_path, source=source)
    _, children, _ = bind_sources(conf)
    jobs = children["atmosphere"].source_requests["atmosphere"]["binding"]["operation_plans"]
    assert jobs and all("kind" not in job["polar_options"]["zeta"] for job in jobs)
    assert not conf.output_dir.exists()


def _nemo_cf_sea_height(field="zos"):
    ds = scene(hours=(0, 1)).rename(
        q=field, time="time_counter", nj="y", ni="x", latitude="nav_lat", longitude="nav_lon")
    ds[field].attrs = {"standard_name": "sea_surface_height_above_geoid", "units": "cm"}
    return ds


@pytest.mark.parametrize("field", ["zos", "ssh_export"])
def test_nemo_cf_sea_height_polar_optional_kind(tmp_path, monkeypatch, field):
    from contextlib import contextmanager

    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads

    ds = _nemo_cf_sea_height(field)
    ds[field].values[:, 4, 4:6] = [[0., 4.], [2., 6.]]
    ds[field].values[:, 4, 2] = np.nan
    ds.to_netcdf(tmp_path / "input.nc")
    center = {"latitude": -20., "longitude": float(
        ds.nav_lon[4, 4] + .25 * (ds.nav_lon[4, 5] - ds.nav_lon[4, 4]))}

    @contextmanager
    def guard():
        with monkeypatch.context() as patch:
            guard_netcdf_payloads(patch, {field})
            yield

    source = {"model": "nemo", "variables": {"2d": [field]}}
    products = _compare_optional_kind(tmp_path, source, field, center, guard=guard)
    polar, native = products["polar"], products["model_grid"]
    np.testing.assert_allclose(polar[field].isel(radius=0, azimuth=0), [1., 3.], atol=2e-3, rtol=0)
    assert (polar[field + "_interpolation_status"] == 2).any()
    np.testing.assert_array_equal(native[field], ds[field])
    for saved in (polar, native):
        np.testing.assert_array_equal(saved.time, ds.time_counter)
        assert saved[field].attrs["units"] == "cm"
        assert saved[field].attrs["standard_name"] == "sea_surface_height_above_geoid"

    native_only = configuration(tmp_path, source=source, products={"model_grid": True})
    report, children, _ = bind_sources(native_only)
    records = children["atmosphere"].source_requests["atmosphere"]["binding"][
        "products"]["model_grid"][field]["records"]
    assert all("field_metadata" not in record for record in records)
    assert not any(w.startswith("[W1603]") for w in report["warnings"])


@pytest.mark.parametrize("problem", [
    "name_only", "other_quantity", "wrong_units", "yaml_label", "later_wide_integer", "depth",
])
def test_nemo_polar_checks_dtype_not_scalar_kind_evidence(tmp_path, problem):
    ds = _nemo_cf_sea_height()
    path = tmp_path / "input.nc"
    source = {"model": "nemo", "files": [str(path)], "variables": {"2d": ["zos"]}}
    if problem in {"name_only", "yaml_label"}:
        label = ds.zos.attrs.pop("standard_name")
        if problem == "yaml_label":
            source["field_metadata"] = {"zos": {"standard_name": label}}
    elif problem == "other_quantity":
        ds.zos.attrs["standard_name"] = "sea_binary_mask"
    elif problem == "wrong_units":
        ds.zos.attrs["units"] = "1"
    elif problem == "depth":
        ds["zos"] = ds.zos.expand_dims({"deptht": [5.]}, axis=1)
        ds.deptht.attrs.update(units="m", positive="down")
        source["variables"] = {"3d": ["zos"]}
    else:
        later = ds.isel(time_counter=[1])
        later["zos"] = later.zos.copy(data=np.full(later.zos.shape, 2**53 + 1, dtype="int64"))
        later.to_netcdf(tmp_path / "later.nc")
        source["files"].append(str(tmp_path / "later.nc"))
        ds = ds.isel(time_counter=[0])
    ds.to_netcdf(path)

    conf = configuration(tmp_path, source=source)
    if problem == "later_wide_integer":
        with pytest.raises(ValueError, match=r"\[E1602\].*zos.*int64"):
            bind_sources(conf)
    else:
        bind_sources(conf)
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("case", ["observed", "flags", "declared", "conflict"])
def test_nemo_polar_respects_known_kind(tmp_path, case):
    ds = _nemo_cf_sea_height()
    source = {"model": "nemo", "variables": {"2d": ["zos"]}}
    if case == "observed":
        ds.zos.attrs["kind"] = "continuous"
    if case in {"flags", "conflict"}:
        ds.zos.attrs.update(flag_values=np.array([0., 7.]), flag_meanings="zero seven")
    if case in {"declared", "conflict"}:
        source["field_metadata"] = {"zos": {"kind": (
            "continuous" if case == "conflict" else "categorical")}}
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, source=source)
    if case == "conflict":
        with pytest.raises(ValueError, match="contradicts input 'categorical'"):
            bind_sources(conf)
    else:
        report, children, _ = bind_sources(conf)
        assert not any(w.startswith("[W1603]") for w in report["warnings"])
        jobs = children["atmosphere"].source_requests["atmosphere"]["binding"]["operation_plans"]
        for job in jobs:
            options = job["polar_options"]["zos"]
            assert options["kind_origin"] == ("declaration" if case == "declared" else "input")
            assert options["interpolation"] == ("bilinear" if case == "observed" else "nearest_s2d")
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("unsampled", [2**53 + 1, "text"])
def test_common_polar_dtype_check_ignores_an_unassociated_record(tmp_path, unsampled):
    ds = _nemo_cf_sea_height()
    ds.isel(time_counter=[0]).to_netcdf(tmp_path / "first.nc")
    later = ds.isel(time_counter=[1])
    later["zos"] = later.zos.copy(data=np.full(later.zos.shape, unsampled))
    later.to_netcdf(tmp_path / "later.nc")
    scene(hours=(0,)).to_netcdf(tmp_path / "weather.nc")
    request = {
        "schema_version": 3, "run": {"name": "common-height"},
        "sources": {
            "water": {"model": "nemo", "files": ["first.nc", "later.nc"],
                      "variables": {"2d": ["zos"]}},
            "weather": {"model": "mesonh", "files": "weather.nc", "variables": {"2d": ["q"]}},
        },
        "region": {"center": {"latitude": -20., "longitude": 60.},
                   "sources_coupling_time_association": "common"},
        "products": {"polar": {"radius_km": 2.5, "azimuth_count": 8}},
        "output": {"directory": "output"},
        "resources": {"synchronous_export": True, "cpus": 1},
    }
    document = tmp_path / "request.yaml"
    document.write_text(yaml.safe_dump(request))
    completed = subprocess.run(
        [sys.executable, "-B", "-m", "frameit", "validate", str(document), "--json"],
        capture_output=True, text=True)
    report = json.loads(completed.stdout)
    assert completed.returncode == 0, report["errors"]
    conf = SimulationConfig.from_yaml_with_model_preset(document)
    assert not conf.output_dir.exists()
    result = execute_simulation(conf)
    product = next(p for p in result.products if p["source"] == "water")
    with xr.open_dataset(product["path"]) as saved:
        np.testing.assert_array_equal(saved.time, ds.time_counter[:1])
        np.testing.assert_allclose(saved.zos, 7.)
        assert "kind" not in saved.zos.attrs


def test_incomplete_track_keeps_an_unlabeled_polar_gap(tmp_path):
    from .test_multifield_vortex import vortex

    weather, _ = vortex(n=81)
    weather["MSLP"][1] = 101000.
    weather.to_netcdf(tmp_path / "weather.nc")
    ocean = _nemo_cf_sea_height().assign_coords(time_counter=weather.time.values)
    reference = ocean.rename(zos="q")
    reference.q.attrs = {"units": "1", "kind": "continuous"}
    reference.to_netcdf(tmp_path / "ocean.nc")
    ocean.isel(time_counter=[1]).to_netcdf(tmp_path / "later.nc")
    conf = configuration(tmp_path, sources={
        "weather": {"model": "mesonh", "files": str(tmp_path / "weather.nc"),
                    "variables": {"2d": ["MSLP"]},
                    "wind_pairs": [{"u": "UT_ZM", "v": "VT_ZM", "basis": "earth"},
                                   {"u": "UM10", "v": "VM10", "basis": "earth"}]},
        "water": {"model": "nemo", "files": [str(tmp_path / name) for name in ("ocean.nc", "later.nc")],
                  "variables": {"2d": ["q", "zos"]}, "allow_initial_gaps": ["zos"]},
    }, region={"tracker": {
        "method": "multifield_vortex", "on_incomplete": "keep_prefix", "mnh_gravity_m_s2": 9.80665,
        "seed": {"latitude": -20., "longitude": 60., "motion_u_m_s": 0, "motion_v_m_s": 0},
    }}, products={"track": True, "polar": {"radius_km": 2.5, "azimuth_count": 8,
                                         "fields": {"water": ["q", "zos"]}}})
    bind_sources(conf)
    assert not conf.output_dir.exists()
    result = execute_simulation(conf)
    assert not result.tracking_complete
    product = next(p for p in result.products if p["role"] == "polar")
    with xr.open_dataset(product["path"]) as saved:
        np.testing.assert_array_equal(saved.time, weather.time[:1])
        assert saved.zos.isnull().all()
        np.testing.assert_array_equal(saved.zos_interpolation_status, 2)
        assert saved.q.attrs["kind"] == "continuous"
        assert "kind" not in saved.zos.attrs
        assert "kind" not in json.loads(saved.zos.attrs.get("frameit_metadata_origins", "{}"))
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    absent, = [record for record in provenance["sources"]["water"]["polar"]["records"]
               if record["field"] == "zos"]
    assert absent["source_record_absent"]
    assert "kind" not in absent["input_metadata"]["zos"]["attributes"]


@pytest.mark.parametrize("guard", ["netcdf", "grib", "fa"])
@pytest.mark.parametrize("damage", [
    "missing", "pending", "invalid", "unknown", "unbound", "geometry", "method",
    "policy", "spacing", "jobs", "descriptor", "support", "owning_source",
])
def test_selected_readers_reject_unproven_polar_before_any_payload(tmp_path, guard, damage):
    from frameit.io.fa_utils import _selected_fa
    from frameit.io.grib_utils import _selected_grib
    from frameit.io.netcdf_utils import _selected_netcdf

    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path)
    _, children, plans = bind_sources(conf)
    source = deepcopy(plans["atmosphere"])
    binding = deepcopy(children["atmosphere"].source_requests["atmosphere"]["binding"])
    if damage == "missing":
        binding.pop("polar_plan")
    elif damage == "pending":
        binding["polar_plan"]["status"] = "pending"
    elif damage == "invalid":
        binding["polar_plan"]["radius_km"] = [0., -1.]
    elif damage == "unknown":
        binding["products"]["unknown"] = {}
    elif damage == "unbound":
        binding["status"] = "pending_method_binding"
    elif damage == "geometry":
        binding["operation_plans"][0]["polar_geometry"] = {"invented": True}
    elif damage == "method":
        binding["operation_plans"][0]["polar_options"]["q"]["interpolation"] = "invented"
    elif damage == "policy":
        binding["operation_plans"][0]["polar_options"]["q"]["missing_data_policy"] = "invented"
    elif damage == "spacing":
        binding["polar_plan"]["native_spacing_m"] = [-1.]
    elif damage == "jobs":
        binding["operation_plans"] = []
    elif damage == "descriptor":
        binding["products"]["polar"]["q"]["execution"] = "pending_polar_sampling"
    elif damage == "support":
        binding["operation_plans"][0]["input_binding"]["dependencies"]["q"]["records"] = []
    else:
        source["requests"]["binding"] = None
    with pytest.raises(ValueError, match="bound|polar|Polar|product"):
        if guard == "netcdf":
            _selected_netcdf([], binding, source, None, engine="h5netcdf", chunks={})
        elif guard == "grib":
            _selected_grib([], binding, source, None)
        else:
            _selected_fa([], binding, source, conf, None)


def test_polar_support_and_coordinates_do_not_follow_export_crop(tmp_path):
    ds = scene()
    ds.q.values[:] = 7 + 2 * (ds.longitude.values - 60) + 3 * (ds.latitude.values + 20)
    ds.to_netcdf(tmp_path / "input.nc")
    outputs = []
    for width in (2., 4.):
        conf = configuration(tmp_path, region={
            "center": {"latitude": -20., "longitude": 60.},
            "width_km": {"x": width, "y": width},
        }, products={"model_grid": True, "polar": {"radius_km": 2.5, "azimuth_count": 8}},
            output_name=f"width-{width}")
        result = execute_simulation(conf)
        polar = next(item for item in result.products if item["role"] == "polar")
        native = next(item for item in result.products if item["role"] == "model_grid")
        with xr.open_dataset(polar["path"]) as saved:
            outputs.append(saved.load())
            assert np.isfinite(saved.q).all()
        with xr.open_dataset(native["path"]) as saved:
            assert saved.q.shape[-2:] == ((3, 3) if width == 2 else (5, 5))
    for out in outputs:
        out.attrs.pop("history")
    xr.testing.assert_identical(outputs[0], outputs[1])


def test_speed_samples_components_before_magnitude_and_keeps_inputs_internal(tmp_path, monkeypatch):
    from frameit.processing.polar.regrid_plan import PolarRegridPlan

    ds = scene()
    u = np.full(ds.q.shape, 3.)
    u[:, :, 5:] = -3.
    ds["U"] = ds.q.copy(data=u).assign_attrs(
        units="m s-1", kind="continuous", standard_name="eastward_wind")
    ds["V"] = ds.q.copy(data=np.full(ds.q.shape, 4.)).assign_attrs(
        units="m s-1", kind="continuous", standard_name="northward_wind")
    ds.to_netcdf(tmp_path / "input.nc")
    original_bytes = (tmp_path / "input.nc").read_bytes()
    conf = configuration(tmp_path, source={
        "variables": {},
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "U", "v": "V"}}},
        "time": {"values": ["2024-01-01T01:00:00"]},
    }, region={"center": {"latitude": -20., "longitude": float(
        (ds.longitude[4, 4] + ds.longitude[4, 5]) / 2)}},
        products={"model_grid": True, "polar": {"radius_km": 2.5, "azimuth_count": 8}})
    original_apply, sampled = PolarRegridPlan.apply, []

    def apply(plan, field, *args, **kwargs):
        sampled.append(field.name)
        return original_apply(plan, field, *args, **kwargs)

    monkeypatch.setattr(PolarRegridPlan, "apply", apply)
    result = execute_simulation(conf)
    assert {"U", "V"} <= set(sampled) and "speed" not in sampled
    for item in result.products:
        with xr.open_dataset(item["path"]) as saved:
            scientific = {n for n in saved.data_vars
                          if saved[n].attrs.get("frameit_role") != "interpolation_quality"}
            assert scientific == {"speed"}
            if item["role"] == "polar":
                np.testing.assert_allclose(saved.speed.isel(radius=0), 4., atol=1e-8)
                assert saved.speed.attrs["derivation"] == "magnitude_of_sampled_components"
                ordinary_reader(item["path"], fields=["speed"], origin_values={"speed": [4.]})
            else:
                np.testing.assert_allclose(saved.speed, 5., atol=1e-12)
    assert set(conf.source_requests["atmosphere"]["binding"]["dependencies"]) == {"U", "V"}
    assert (tmp_path / "input.nc").read_bytes() == original_bytes


@pytest.mark.parametrize("names", [["U"], ["U", "V"]])
def test_polar_native_components_need_no_pair_or_implicit_diagnostic(tmp_path, names):
    ds = scene()
    for name, value in (("U", 3.), ("V", 4.)):
        if name in names:
            ds[name] = xr.full_like(ds.q, value).assign_attrs(
                kind="continuous", units="stored_component_units")
    ds.to_netcdf(tmp_path / "input.nc")
    original_bytes = (tmp_path / "input.nc").read_bytes()
    result = execute_simulation(configuration(tmp_path, source={"variables": {"2d": names}}))
    ordinary_reader(result.products[0]["path"], fields=names,
                    values={name: 3. if name == "U" else 4. for name in names})
    assert (tmp_path / "input.nc").read_bytes() == original_bytes


@pytest.mark.parametrize("mass_polar", [False, True])
@pytest.mark.parametrize("mass_export", [False, True])
def test_independent_pressure_w_and_mixed_vertical_grids(tmp_path, mass_polar, mass_export):
    from frameit.testing.numerical.test_grid_representations import native_scene

    ds = native_scene().drop_vars(["UT", "VT"])
    ds.WT.attrs.update(units="Pa s-1", standard_name="lagrangian_tendency_of_air_pressure")
    ds.to_netcdf(tmp_path / "input.nc")
    original_bytes = (tmp_path / "input.nc").read_bytes()
    conf = configuration(tmp_path, source={
        "variables": {"3d": ["WT", "THT"], "levels": {"indices": [2, 0]}},
        "field_metadata": {name: {"kind": "continuous"} for name in ("WT", "THT")},
        "transforms": [{"fields": ["WT"], "sampling": "mass"}] if mass_export else [],
    }, products={"model_grid": True, "polar": {
        "radius_km": 2.5, "azimuth_count": 8,
        "field_options": {"atmosphere": {"WT": {"sampling": "mass"}}} if mass_polar else {},
    }})
    result = execute_simulation(conf)
    for item in result.products:
        with xr.open_dataset(item["path"]) as saved:
            mass = mass_polar if item["role"] == "polar" else mass_export
            dim = "level" if mass else "level_w"
            np.testing.assert_array_equal(saved[dim], [15., -5.] if mass else [10., -10.])
            selection = ({"radius": 0, "azimuth": 0} if item["role"] == "polar"
                         else {"y": 4, "x": 4})
            if item["role"] == "model_grid":
                np.testing.assert_array_equal(saved.ni_source_coordinate, ds.ni)
                np.testing.assert_array_equal(saved.nj_source_coordinate, ds.nj)
            np.testing.assert_allclose(saved.WT.isel(selection),
                                       [[115., 55.]] if mass else [[100., 40.]])
            assert saved.WT.attrs["units"] == "Pa s-1"
            assert saved.WT.attrs["standard_name"] == "lagrangian_tendency_of_air_pressure"
            np.testing.assert_allclose(saved.THT, 300.)
            assert "level" in saved.THT.dims
        if item["role"] == "polar":
            ordinary_reader(
                item["path"], fields=["WT", "THT"],
                origin_values={"WT": [[115., 55.]] if mass_polar else [[100., 40.]]},
                variable_attributes={"WT": {
                    "units": "Pa s-1", "standard_name": "lagrangian_tendency_of_air_pressure"}})
    assert (tmp_path / "input.nc").read_bytes() == original_bytes


def test_shared_grid_uses_coarsest_spacing_without_intersecting_source_clocks_or_masks(tmp_path):
    sources = {}
    for name, model, spacing, hours in (
            ("weather", "mesonh", 1000., (0, 2)), ("water", "nemo", 2000., (1, 3))):
        ds = scene(hours=hours, spacing=spacing)
        ds.q.values[0, 4, 4] = 0 if name == "weather" else np.nan
        if model == "nemo":
            ds = ds.rename(time="time_counter", nj="y", ni="x",
                           latitude="nav_lat", longitude="nav_lon")
        path = tmp_path / f"{name}.nc"
        ds.to_netcdf(path)
        sources[name] = {"model": model, "files": str(path), "variables": {"2d": ["q"]}}
    conf = configuration(tmp_path, sources=sources, products={
        "polar": {"radius_km": 2.5, "shared_grid": True, "azimuth_count": 8}})
    result = execute_simulation(conf)
    for item in result.products:
        with xr.open_dataset(item["path"]) as saved:
            np.testing.assert_array_equal(saved.radius, [0., 2., 2.5])
            hours = (0, 2) if item["source"] == "weather" else (1, 3)
            np.testing.assert_array_equal(saved.time, np.datetime64("2024-01-01T00", "ns")
                                          + np.array(hours, dtype="timedelta64[h]"))
            np.testing.assert_array_equal(saved.center_time, saved.time)
            origin = saved.q.isel(time=0, radius=0)
            if item["source"] == "weather":
                np.testing.assert_array_equal(origin, 0.)
            else:
                assert np.isnan(origin).all()
    contract = conf.simulation_parameter["common_polar_target"]
    assert contract["radial_step_km"] == 2.
    assert contract["verification"] == "exact_coordinates_at_associated_centres"


@pytest.mark.parametrize("step", [None, .5, 1.5])
def test_native_spacing_automatic_angles_and_finer_rejection(tmp_path, step):
    scene().to_netcdf(tmp_path / "input.nc")
    options = {"radius_km": 2.5}
    if step is not None:
        options["radial_step_km"] = step
    conf = configuration(tmp_path, products={"polar": options})
    if step == .5:
        with pytest.raises(ValueError, match="finer.*native"):
            bind_sources(conf)
    else:
        _, children, _ = bind_sources(conf)
        plan = children["atmosphere"].source_requests["atmosphere"]["binding"]["polar_plan"]
        assert plan["radius_km"] == ([0., 1., 2., 2.5] if step is None else [0., 1.5, 2.5])
        assert len(plan["azimuth_degrees"]) == (16 if step is None else 11)


@pytest.mark.parametrize("policy,minimum,missing,status,expected", [
    ("strict", None, "half", 2, np.nan),
    ("renormalize", .49, "half", 0, 0.),
    ("renormalize", .75, "half", 3, np.nan),
    ("renormalize", .49, "all", 2, np.nan),
])
def test_coverage_preserves_zero_missing_and_explicit_threshold(
        tmp_path, policy, minimum, missing, status, expected):
    ds = scene()
    ds.q.values[:] = 0.
    ds.q.values[:, :, 5:] = np.nan
    if missing == "all":
        ds.q.values[:] = np.nan
    ds.to_netcdf(tmp_path / "input.nc")
    options = {"radius_km": 2.5, "azimuth_count": 8, "missing_data_policy": policy}
    if minimum is not None:
        options["min_valid_weight_fraction"] = minimum
    conf = configuration(tmp_path, products={"polar": options}, region={
        "center": {"latitude": -20., "longitude": float(
            (ds.longitude[4, 4] + ds.longitude[4, 5]) / 2)}})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        np.testing.assert_allclose(saved.q.isel(radius=0), expected, atol=1e-10)
        np.testing.assert_array_equal(saved.q_interpolation_status.isel(radius=0), status)
        np.testing.assert_allclose(saved.q_support_fraction.isel(radius=0),
                                   0. if missing == "all" else .5, atol=1e-8)


def test_categorical_nearest_does_not_extrapolate_outside_source_footprint(tmp_path):
    ds = scene()
    ds.q.attrs.update(kind="categorical", flag_values=np.array([0., 7.]),
                      flag_meanings="zero seven")
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, products={"polar": {"radius_km": 10., "azimuth_count": 8}})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert np.isnan(saved.q.isel(radius=-1)).all()
        np.testing.assert_array_equal(saved.q_interpolation_status.isel(radius=-1), 1)
        np.testing.assert_array_equal(saved.q.isel(radius=0), 7.)


@pytest.mark.parametrize("product", ["model_grid", "track", "polar"])
def test_optional_backend_and_point_guard_precede_payload_and_output(
        tmp_path, monkeypatch, product):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.processing.polar import polar_proj

    scene().to_netcdf(tmp_path / "input.nc")
    original = H5NetCDFArrayWrapper.__getitem__

    def no_payload(array, key):
        assert array.variable_name != "q"
        return original(array, key)

    monkeypatch.setattr(polar_proj, "xe", None)
    conf = configuration(tmp_path, products={
        product: {"radius_km": 2.5, "azimuth_count": 8} if product == "polar" else True})
    if product == "polar":
        monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", no_payload)
        with pytest.raises(ImportError, match="xESMF.*omit products.polar"):
            execute_simulation(conf)
        assert not conf.output_dir.exists()
    else:
        if product == "track":
            monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", no_payload)
        result = execute_simulation(conf)
        assert result.ok and [item["role"] for item in result.products] == [product]


def test_full_time_target_budget_fails_without_payload_or_output(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    scene().to_netcdf(tmp_path / "input.nc")
    original = H5NetCDFArrayWrapper.__getitem__

    def no_payload(array, key):
        assert array.variable_name != "q"
        return original(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", no_payload)
    conf = configuration(tmp_path, products={"polar": {
        "radius_km": 2.5, "azimuth_count": 8, "processing": {"max_target_points": 95}}})
    with pytest.raises(ValueError, match="requires 96 points"):
        execute_simulation(conf)
    assert not conf.output_dir.exists()


def test_metadata_preflight_reports_executable_polar_and_product_descriptors(tmp_path):
    from frameit.core.preflight import preflight

    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path)
    report = preflight(conf)
    binding = report["sources"]["atmosphere"]["requests"]["binding"]
    assert binding["status"] == "bound"
    assert binding["polar_plan"]["target_points"] == 96
    product = conf.simulation_parameter["request_plan"]["products"][0]
    assert product["stored_names"] == {"q": "q"}
    assert product["dimensions"] == {"q": ["time", "radius", "azimuth"]}
    assert product["units"] == {"q": "K"}
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("problem", ["category", "unused_override", "category_bilinear",
                                   "nearest_renormalize", "halo", "chunks"])
def test_invalid_polar_contracts_fail_before_payload_or_output(tmp_path, problem):
    ds = scene()
    if problem == "category_bilinear":
        ds.q.attrs["kind"] = "categorical"
    ds.to_netcdf(tmp_path / "input.nc")
    source, options = {}, {"radius_km": 2.5, "azimuth_count": 8}
    if problem == "category":
        source["variables"] = {"3d": ["q"]}
    elif problem == "unused_override":
        options["field_options"] = {"atmosphere": {"unused": {"interpolation": "nearest"}}}
    elif problem == "category_bilinear":
        options["field_options"] = {"atmosphere": {"q": {"interpolation": "bilinear"}}}
    elif problem == "nearest_renormalize":
        options["field_options"] = {"atmosphere": {"q": {
            "interpolation": "nearest", "missing_data_policy": "renormalize",
            "min_valid_weight_fraction": .75}}}
    elif problem == "chunks":
        options["processing"] = {"chunks": {"missing_dimension": 1}}
    with pytest.raises(ValueError, match="category|unused|categorical|nearest|halo|chunks"):
        conf = configuration(tmp_path, source=source, products={"polar": options})
        if problem == "halo":
            from frameit.core.coupled import prepare_sources
            from frameit.core.preflight import bind_source

            _, children, _ = prepare_sources(conf)
            children["atmosphere"].polar_source_halo_points = 0
            bind_source(children["atmosphere"], "atmosphere")
        else:
            bind_sources(conf)
    assert not (tmp_path / "output").exists()


def test_native_stencil_window_is_derived_from_real_weights_and_honours_halo(tmp_path):
    from frameit.processing.polar.regrid_plan import PolarRegridPlan
    from frameit.testing.numerical.test_polar_regrid_plan import plan_inputs

    _, source, target = plan_inputs()
    from frameit.processing.polar.regrid_plan import RegridGeometry

    plan = PolarRegridPlan.build(RegridGeometry.capture(source, target))
    a = plan.source_support(1)
    b = plan.source_support(2)
    assert a["nonzero_source_points"] > 0
    assert b["y_slice"][0] <= a["y_slice"][0] < a["y_slice"][1] <= b["y_slice"][1]
    assert b["x_slice"][0] <= a["x_slice"][0] < a["x_slice"][1] <= b["x_slice"][1]
    field = xr.DataArray(np.arange(source.lon.size).reshape(source.lon.shape).astype(float),
                         dims=("y_box", "x_box"))
    whole = plan.apply(field)
    cropped = plan.apply(field, source_halo_points=1)
    for actual, expected in zip(cropped, whole, strict=True):
        xr.testing.assert_identical(actual, expected)
    with pytest.raises(ValueError, match="halo"):
        plan.apply(field, source_halo_points=0)


def test_exact_source_and_field_filter_avoids_unused_payload_and_centre_requirements(
        tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    ds = scene(hours=(1,))
    ds["unused"] = ds.q + 100.
    ds.to_netcdf(tmp_path / "input.nc")
    ocean = scene(hours=(3,)).rename(
        time="time_counter", nj="y", ni="x", latitude="nav_lat", longitude="nav_lon")
    ocean.q.attrs.pop("kind")
    ocean.to_netcdf(tmp_path / "ocean.nc")
    track = xr.Dataset({
        "latitude": ("time", [-20.], {"units": "degrees_north"}),
        "longitude": ("time", [60.], {"units": "degrees_east"}),
    }, coords={"time": ds.time})
    track.to_netcdf(tmp_path / "track.nc")
    conf = configuration(tmp_path, sources={
        "weather": {"model": "mesonh", "files": str(tmp_path / "input.nc"),
                    "variables": {"2d": ["q", "unused"]}},
        "water": {"model": "nemo", "files": str(tmp_path / "ocean.nc"),
                  "variables": {"2d": ["q"]}},
    }, region={"track": {"file": str(tmp_path / "track.nc")}},
        products={"polar": {"radius_km": 2.5, "azimuth_count": 8,
                            "fields": {"weather": ["q"]}}})
    original, reads = H5NetCDFArrayWrapper.__getitem__, []

    def read(array, key):
        if array.variable_name in {"q", "unused"}:
            assert array.variable_name == "q" and array.shape[0] == 1
            reads.append(array.shape)
        return original(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", read)
    result = execute_simulation(conf)
    assert result.ok and len(result.products) == 1
    assert result.products[0]["source"] == "weather" and reads
    assert not conf.source_requests["water"]["binding"]["records"]
    ordinary_reader(result.products[0]["path"], fields=["q"], values={"q": 7.})


@pytest.mark.parametrize("sampling", ["native", "mixed"])
def test_derived_input_sampling_is_honoured_or_incompatible_preparation_rejected(
        tmp_path, sampling):
    ds = scene()
    ds["U"] = xr.full_like(ds.q, 3.).assign_attrs(
        units="m s-1", kind="continuous", standard_name="eastward_wind")
    ds["V"] = xr.full_like(ds.q, 4.).assign_attrs(
        units="m s-1", kind="continuous", standard_name="northward_wind")
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, source={
        "variables": {},
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "U", "v": "V"}}},
    }, products={"polar": {"radius_km": 2.5, "azimuth_count": 8, "field_options": {
        "atmosphere": {"U": {"sampling": "native"},
                       "V": {"sampling": "mass" if sampling == "mixed" else "native"}}}}})
    _, children, _ = bind_sources(conf)
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    if sampling == "native":
        assert all(job["sampling"] == "native" for job in binding["operation_plans"])
    else:
        assert all(job["input_sampling"] == {"U": "native", "V": "mass"}
                   for job in binding["operation_plans"])
    result = execute_simulation(conf)
    ordinary_reader(result.products[0]["path"], fields=["speed"], values={"speed": 5.})


def test_polar_w_mass_payload_reads_only_actual_native_neighbours(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.testing.numerical.test_grid_representations import native_scene

    ds = xr.concat([native_scene(hour) for hour in (0, 1, 2)], dim="time", data_vars="all")
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, source={
        "variables": {"3d": ["WT", "THT"], "levels": {"indices": [2]}},
        "field_metadata": {name: {"kind": "continuous"} for name in ("WT", "THT")},
        "time": {"values": ["2024-01-01T01:00:00"]},
        "reader": {"chunks": {"time": 3, "level_w": 4}},
    }, products={"polar": {"radius_km": 2.5, "azimuth_count": 8,
                          "field_options": {"atmosphere": {"WT": {"sampling": "mass"}}}}})
    original, reads = H5NetCDFArrayWrapper.__getitem__, []

    def read(array, key):
        if array.variable_name in {"WT", "THT"}:
            times = np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist()
            levels = np.atleast_1d(np.arange(array.shape[1])[key.tuple[1]]).tolist()
            assert times == [1]
            assert levels == ([2, 3] if array.variable_name == "WT" else [2])
            reads.append(array.variable_name)
        return original(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", read)
    result = execute_simulation(conf)
    assert set(reads) == {"WT", "THT"}
    ordinary_reader(result.products[0]["path"], fields=["WT", "THT"],
                    origin_values={"WT": [[115.]], "THT": [[300.]]})


def test_admitted_grib_polar_uses_selected_cycle_level_and_actual_decoder(tmp_path, monkeypatch):
    from frameit.io import grib_utils
    from frameit.processing.polar.regrid_plan import PolarRegridPlan
    from frameit.testing.numerical.test_v3_grib_reads import write_messages

    path = write_messages(tmp_path / "input.grib", [
        {"hour": hour, "level": level, "cycle": cycle, "missing": False}
        for hour in (0, 1, 2) for level in (700, 850) for cycle in (0, 600)])
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    conf = configuration(tmp_path, source={
        "model": "arome", "files": str(path),
        "variables": {"3d": ["u"], "levels": {"values": [700], "units": "hPa"}},
        "field_metadata": {"u": {"kind": "continuous"}},
        "time": {"cycle": "2026-01-01T00:00:00", "values": ["2026-01-01T01:00:00"]},
    }, products={"polar": {"radius_km": 2.5, "azimuth_count": 8}})
    original, reads = grib_utils._grib_payload, []
    original_apply, applications = PolarRegridPlan.apply, []

    def read(locator, shape, header):
        reads.append((header["level"], header["endStep"], str(header["cycle"])))
        return original(locator, shape, header)

    def apply(plan, field, *args, **kwargs):
        applications.append(field.name)
        return original_apply(plan, field, *args, **kwargs)

    monkeypatch.setattr(grib_utils, "_grib_payload", read)
    monkeypatch.setattr(PolarRegridPlan, "apply", apply)
    bind_sources(conf)
    assert not reads
    result = execute_simulation(conf)
    assert reads and set(reads) == {(700, 1, "2026-01-01T00:00:00.000000000")}
    assert "u" in applications
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as ds:
    assert ds.u.dims == ('time','pressure','radius','azimuth')
    np.testing.assert_array_equal(ds.pressure, [700.])
    assert ds.pressure.attrs['units'] == 'hPa'
    np.testing.assert_array_equal(ds.pressure_source_native_index, [1])
    np.testing.assert_array_equal(ds.radius, [0.,2.5])
    np.testing.assert_allclose(ds.u.isel(radius=0), 0., atol=1e-10)
    np.testing.assert_array_equal(ds.u_interpolation_status.isel(radius=0), 0)
    assert 'v' not in ds and 'wind_speed' not in ds and 'vrad' not in ds
assert 'frameit' not in sys.modules
""", result.products[0]["path"]], check=True, capture_output=True, text=True)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_admitted_fa_polar_uses_selected_native_leaf_and_keeps_hybrid_metadata(
        tmp_path, monkeypatch):
    from frameit.processing.polar.regrid_plan import PolarRegridPlan
    from frameit.testing.numerical.test_fa_cubes import DECLARATION, fixtures
    from frameit.testing.numerical.test_v3_interpretation import _fa_requests

    paths = fixtures(tmp_path, hours=(0, 1, 2))
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    conf = configuration(tmp_path, source={
        "model": "arome", "files": list(map(str, paths)), "profile": "arome_history",
        "variables": {"3d": ["temperature"], "levels": {"indices": [2, 0]}},
        "time": {"values": ["2026-01-01T02:00:00"]},
        "field_metadata": {"temperature": DECLARATION},
        "native_cubes": {"temperature": {
            "records": [f"S{k:03d}TEMPERATURE" for k in (1, 2, 3)],
            "vertical_position": "mass", "sampling": "center"}},
        "fa": {"earth_radius_m": 6371229.},
        "reader": {"python_executable": sys.executable, "max_points": 1000, "timeout_seconds": 30},
    }, region={"center": {"latitude": -20., "longitude": 50.}})
    calls = _fa_requests(monkeypatch)
    original, applications = PolarRegridPlan.apply, []

    def apply(plan, field, *args, **kwargs):
        applications.append(field.name)
        return original(plan, field, *args, **kwargs)

    monkeypatch.setattr(PolarRegridPlan, "apply", apply)
    bind_sources(conf)
    assert not any(call["operation"] == "read" for call in calls)
    result = execute_simulation(conf)
    reads = [call for call in calls if call["operation"] == "read"]
    assert {call["path"] for call in reads} == {str(paths[2])}
    assert {tuple(call["fields"]) for call in reads} == {
        ("S001TEMPERATURE",), ("S003TEMPERATURE",)}
    assert all(call["max_points"] == 1000 and call["timeout_seconds"] == 30 for call in reads)
    assert "temperature" in applications
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as ds:
    np.testing.assert_array_equal(ds.level, [3,1])
    np.testing.assert_array_equal(ds.level_source_native_index, [2,0])
    np.testing.assert_allclose(ds.temperature.isel(radius=0,azimuth=0), [[345.,325.]], atol=1e-8)
    np.testing.assert_array_equal(ds.fa_hybrid_a, [0.,10000.,20000.,0.])
    np.testing.assert_array_equal(ds.fa_hybrid_b, [0.,.2,.6,1.])
    np.testing.assert_array_equal(ds.temperature_native_record,
                                   ['S003TEMPERATURE','S001TEMPERATURE'])
    assert ds.temperature.attrs['units'] == 'K'
assert not {'frameit','epygram','falfilfa4py'} & sys.modules.keys()
""", result.products[0]["path"]], check=True, capture_output=True, text=True)
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == before


def test_moving_targets_reuse_matching_weights_with_one_entry_cache(tmp_path):
    ds = scene(hours=(0, 2))
    ds["r"] = ds.q + 1
    ds.r.attrs = dict(ds.q.attrs)
    ds.to_netcdf(tmp_path / "input.nc")
    xr.Dataset({
        "latitude": ("time", [-20., -19.999], {"units": "degrees_north"}),
        "longitude": ("time", [60., 60.001], {"units": "degrees_east"}),
    }, coords={"time": ds.time}).to_netcdf(tmp_path / "track.nc")
    conf = configuration(tmp_path, source={"variables": {"2d": ["q", "r"]}},
                         region={"track": {"file": str(tmp_path / "track.nc")}},
                         products={"polar": {"radius_km": 2.5, "azimuth_count": 8,
                                              "processing": {"plan_cache": {"entries": 1}}}})
    execute_simulation(conf)
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    performance = provenance["sources"]["atmosphere"]["polar"]["regrid_performance"]
    assert performance["builds"] == 2 and performance["hits"] == 2
    assert performance["retained_entries"] == performance["peak_retained_entries"] == 1


@pytest.mark.parametrize("coordinate", ["longitude", "time", "azimuth", "center_time"])
def test_actual_shared_target_mismatch_fails_before_publication(tmp_path, monkeypatch, coordinate):
    from frameit.processing.polar import polar_proj

    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, products={"polar": {
        "radius_km": 2.5, "azimuth_count": 8, "shared_grid": True}})
    original = polar_proj.execute_source_polar

    def altered(*args, **kwargs):
        ds, report = original(*args, **kwargs)
        offset = np.timedelta64(1, "h") if coordinate in {"time", "center_time"} else .001
        return ds.assign_coords({coordinate: ds[coordinate] + offset}), report

    monkeypatch.setattr(polar_proj, "execute_source_polar", altered)
    with pytest.raises(ValueError, match="Shared polar target mismatch"):
        execute_simulation(conf)
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["state"] == "failed" and not status["products"]
    assert not list((conf.output_dir / "products").glob("*.nc"))


@pytest.mark.parametrize("damage", ["missing", "pending", "invalid", "unknown", "unbound"])
def test_execution_guard_rejects_damaged_actual_plan_before_ownership(
        tmp_path, monkeypatch, damage):
    from frameit.core import coupled

    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path)
    original = coupled.bind_sources

    def damaged(*args, **kwargs):
        result = original(*args, **kwargs)
        binding = result[2]["atmosphere"]["requests"]["binding"]
        if damage == "missing":
            binding.pop("polar_plan")
        elif damage == "pending":
            binding["polar_plan"]["status"] = "pending"
        elif damage == "invalid":
            binding["polar_plan"]["radius_km"] = [-1., 2.]
        elif damage == "unknown":
            binding["products"]["unknown"] = {}
        else:
            binding["status"] = "pending"
        return result

    monkeypatch.setattr(coupled, "bind_sources", damaged)
    with pytest.raises(ValueError, match="bound|Polar|product"):
        execute_simulation(conf)
    assert not conf.output_dir.exists()


def test_polar_preparation_uses_each_records_rotation_and_typed_provenance(tmp_path, monkeypatch):
    from frameit.processing.polar.regrid_plan import PolarRegridPlan
    from frameit.testing.numerical.test_grid_representations import native_scene

    ds = xr.concat([native_scene(hour) for hour in (0, 1, 2)], dim="time", data_vars="all")
    ds.UT.values[:] = 3.
    ds.VT.values[:] = 4.
    ds = ds.assign_coords(angle=("time", [0., .25, np.pi / 2], {
        "units": "rad", "valid_range": np.array([0., np.pi]),
        "calibration_revision": np.int32(7)}))
    ds.to_netcdf(tmp_path / "input.nc")
    before = hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest()
    conf = configuration(tmp_path, source={
        "variables": {"levels": {"indices": [2]}},
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "UT", "v": "VT"}}},
        "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "field_metadata": {name: {"kind": "continuous"} for name in ("UT", "VT")},
        "time": {"values": ["2024-01-01T00:00:00", "2024-01-01T02:00:00"]},
    })
    original, sampled = PolarRegridPlan.apply, []

    def apply(plan, field, *args, **kwargs):
        if field.name in {"UT", "VT"}:
            sampled.append((str(field.time.values[0]), field.name, float(
                field.isel(time=0, level=0, y_box=4, x_box=4).compute())))
        return original(plan, field, *args, **kwargs)

    monkeypatch.setattr(PolarRegridPlan, "apply", apply)
    result = execute_simulation(conf)
    expected = [
        ("2024-01-01T00:00:00.000000000", "UT", 3.),
        ("2024-01-01T00:00:00.000000000", "VT", 4.),
        ("2024-01-01T02:00:00.000000000", "UT", -4.),
        ("2024-01-01T02:00:00.000000000", "VT", 3.),
    ]
    assert [(stamp, name) for stamp, name, _ in sampled] == [(s, n) for s, n, _ in expected]
    np.testing.assert_allclose([v for _, _, v in sampled], [v for _, _, v in expected], atol=1e-12)
    ordinary_reader(result.products[0]["path"], fields=["speed"], values={"speed": 5.})
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    records = provenance["sources"]["atmosphere"]["polar"]["records"]
    assert [r["rotation_coordinate"]["values"] for r in records] == [0., np.pi / 2]
    for record in records:
        attrs = record["rotation_coordinate"]["attributes"]
        assert attrs["valid_range"] == [0., np.pi]
        assert type(attrs["calibration_revision"]) is int
        assert record["method"] == "wind_speed"
        assert record["inputs"] == {"u": "UT", "v": "VT"}
        assert record["levels"]["source_native_indices"] == [2]
        assert record["levels"]["values"] == [15.]
        assert record["input_metadata"]["UT"]["attributes"]["units"] == "m/s"
        assert record["input_metadata"]["UT"]["origins"]["kind"] == "declaration"
        assert record["geometry"]["x"]["spacing_m"] == 1000.
    assert hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest() == before


@pytest.mark.parametrize("value", [2**53 + 1, "text"])
def test_polar_rejects_unsupported_dtype_in_unexported_wind_companion(tmp_path, value):
    from frameit.testing.numerical.test_grid_representations import native_scene

    paths = []
    for hour in (0, 1):
        ds = native_scene(hour).assign_coords(angle=xr.DataArray(.25, attrs={"units": "rad"}))
        if hour:
            ds["VT"] = ds.VT.copy(data=np.full(ds.VT.shape, value))
        path = tmp_path / f"{hour}.nc"
        ds.to_netcdf(path)
        paths.append(str(path))
    conf = configuration(tmp_path, source={
        "files": paths, "variables": {"3d": ["UT"], "levels": {"indices": [2]}},
        "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
    }, products={"polar": {
        "radius_km": 2.5, "azimuth_count": 8,
        "field_options": {"atmosphere": {"UT": {"sampling": "mass", "basis": "earth"}}},
    }})
    with pytest.raises(ValueError, match=r"polar\.VT: unsupported numeric dtype"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("mass", [False, True])
def test_shared_level_coordinate_conversion_keeps_polar_samples_and_native_indices(tmp_path, mass):
    from frameit.testing.numerical.test_grid_representations import native_scene

    native_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, source={
        "variables": {"3d": ["WT", "THT"], "levels": {"indices": [2, 0], "units": "km"}},
        "field_metadata": {name: {"kind": "continuous"} for name in ("WT", "THT")},
    }, products={"polar": {
        "radius_km": 2.5, "azimuth_count": 8,
        "field_options": {"atmosphere": {"WT": {"sampling": "mass"}}} if mass else {}}})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        np.testing.assert_array_equal(saved.level, [.015, -.005])
        assert saved.level.attrs["units"] == "km"
        np.testing.assert_array_equal(saved.level_source_native_index, [2, 0])
        if not mass:
            np.testing.assert_array_equal(saved.level_w, [.01, -.01])
            assert saved.level_w.attrs["units"] == "km"
            np.testing.assert_array_equal(saved.level_w_source_native_index, [2, 0])
        np.testing.assert_allclose(saved.WT.isel(radius=0, azimuth=0),
                                   [[115., 55.]] if mass else [[100., 40.]])
        np.testing.assert_array_equal(saved.WT_interpolation_status, 0)


@pytest.mark.parametrize("clock", ["time", "valid_time"])
def test_each_moving_source_geometry_drives_polar_weights_without_stale_coordinates(
        tmp_path, clock):
    ds = scene(hours=(0, 2))
    longitude = np.stack([ds.longitude.values, ds.longitude.values + .002])
    ds = ds.assign_coords(longitude=(("time", "nj", "ni"), longitude,
                                     {"units": "degrees_east"}))
    ds.q.values[:] = longitude
    if clock != "time":
        ds = ds.rename(time=clock)
    ds.to_netcdf(tmp_path / "input.nc")
    result = execute_simulation(configuration(tmp_path))
    with xr.open_dataset(result.products[0]["path"]) as saved:
        # ESMF spherical bilinear longitude error is <1e-8 degree on this grid.
        # A stale second-time grid would instead return 60.002 at the origin.
        np.testing.assert_allclose(saved.q.isel(radius=0), 60., atol=1e-8)
        np.testing.assert_array_equal(saved.center_longitude, [60., 60.])


def test_polar_retains_source_calendar_and_records_field_override_and_profile(tmp_path):
    ds = scene()
    ds.time.encoding.update(calendar="standard", units="hours since 2024-01-01")
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, products={"polar": {
        "radius_km": 2.5, "azimuth_count": 8,
        "field_options": {"atmosphere": {"q": {
            "missing_data_policy": "renormalize", "min_valid_weight_fraction": .75}}},
        "processing": {"profile": True, "chunks": {"radius": 2, "azimuth": 4}},
    }})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert saved.time.encoding["calendar"] == "standard"
        assert saved.q.attrs["polar_missing_data_policy"] == "renormalize"
        assert saved.q.attrs["polar_min_valid_weight_fraction"] == .75
        assert saved.q.attrs["polar_interpolation"] == "bilinear"
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    profile = provenance["sources"]["atmosphere"]["polar"]["profile"]
    assert profile["graph_tasks"] > 0 and profile["process_peak_rss_bytes"] > 0


def test_actual_consumers_bind_once_and_readers_receive_complete_binding_and_owner(
        tmp_path, monkeypatch):
    from frameit.core import preflight
    from frameit.io import netcdf_utils

    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path)
    original_bind, original_read = preflight.bind_source, netcdf_utils._selected_netcdf
    bound, consumed = [], []

    def bind(child, name, **kwargs):
        binding = original_bind(child, name, **kwargs)
        bound.append((id(child), binding))
        return binding

    def read(files, binding, source, *args, **kwargs):
        assert binding is bound[0][1] and source["requests"]["binding"] is binding
        assert set(binding["products"]) == {"polar"}
        assert binding["polar_plan"]["status"] == "bound"
        consumed.append(binding)
        return original_read(files, binding, source, *args, **kwargs)

    monkeypatch.setattr(preflight, "bind_source", bind)
    monkeypatch.setattr(netcdf_utils, "_selected_netcdf", read)
    result = execute_simulation(conf)
    assert len(bound) == len(consumed) == 1
    ordinary_reader(result.products[0]["path"], fields=["q"], values={"q": 7.})


def test_polar_preceding_hour_preserves_ocean_sample_clock_interval_and_centre_time(tmp_path):
    from frameit.testing.numerical.test_v3_regions import preceding_sources

    sources = preceding_sources(tmp_path)
    for source in sources.values():
        source["field_metadata"] = {"scalar": {"kind": "continuous"}}
    conf = configuration(tmp_path, sources=sources, region={
        "center": {"latitude": -20., "longitude": 60.},
        "sources_coupling_time_association": "preceding_hour",
    }, products={"polar": {"radius_km": 1., "azimuth_count": 8, "shared_grid": True}})
    before = {name: hashlib.sha256(Path(source["files"]).read_bytes()).hexdigest()
              for name, source in sources.items()}
    result = execute_simulation(conf)
    path = next(item["path"] for item in result.products if item["source"] == "water")
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as ds, xr.open_dataset(sys.argv[2]) as source:
    np.testing.assert_array_equal(ds.time, source.time_counter)
    np.testing.assert_array_equal(ds.time_bounds, source.time_bounds)
    np.testing.assert_array_equal(ds.center_time, source.time_bounds[:,1])
    np.testing.assert_allclose(ds.scalar.isel(radius=0,azimuth=0), [0.,73.], atol=1e-9)
    assert ds.scalar.attrs['cell_methods'] == 'time: mean'
    assert ds.time.attrs['bounds'] == 'time_bounds'
    np.testing.assert_array_equal(ds.scalar_interpolation_status.isel(radius=0), 0)
assert 'frameit' not in sys.modules
""", path, str(tmp_path / "water.nc")], check=True, capture_output=True, text=True)
    assert {name: hashlib.sha256(Path(source["files"]).read_bytes()).hexdigest()
            for name, source in sources.items()} == before


def test_polar_retains_admitted_native_member_axis_without_duplicate_times(tmp_path):
    from frameit.testing.numerical.test_v3_grib_reads import write_messages

    path = write_messages(tmp_path / "input.grib", [
        {"hour": hour, "level": 700, "member": member, "missing": False}
        for hour in (1, 2) for member in (1, 2)])
    conf = configuration(tmp_path, source={
        "model": "arome", "files": str(path),
        "variables": {"3d": ["u"]}, "field_metadata": {"u": {"kind": "continuous"}},
    }, products={"polar": {"radius_km": 2.5, "azimuth_count": 8,
                          "processing": {"chunks": {"number": 1}}}})
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert saved.sizes["number"] == 2 and saved.sizes["time"] == 2
        assert saved.time.to_index().is_unique
        np.testing.assert_array_equal(saved.number, [1, 2])
        np.testing.assert_array_equal(saved.u.isel(radius=0), 0.)
        descriptor = conf.simulation_parameter["request_plan"]["products"][0]
        assert descriptor["dimensions"]["u"] == list(saved.u.dims)


def test_nearest_uses_esmf_spherical_cell_footprint_not_a_planar_latitude_edge():
    from frameit.processing.polar.regrid_plan import PolarRegridPlanCache

    # The great-circle edge joining (-5,80) and (5,80) reaches 80.0373 N.
    # Thus (0,80.02) is inside this spherical cell, although outside a flat
    # lon/lat rectangle. No scalar interpolation truth comes from FrameIt here.
    source = xr.Dataset({
        "lon": (("y_box", "x_box"), [[-5., 5.], [-5., 5.]]),
        "lat": (("y_box", "x_box"), [[79., 79.], [80., 80.]]),
    })
    target = xr.Dataset({
        "lon": (("rr", "theta_deg"), [[0., 0., 0.]]),
        "lat": (("rr", "theta_deg"), [[80.02, 80.02, 80.02]]),
    }, coords={"rr": [0.], "theta_deg": [0., 120., 240.]})
    cache = PolarRegridPlanCache()
    bilinear = cache.get(source, target)
    nearest = cache.get(source, target, method="nearest_s2d")
    np.testing.assert_array_equal(bilinear.supported.geometry_mapped, True)
    np.testing.assert_array_equal(nearest.supported.geometry_mapped, True)


def test_polar_zarr_quality_and_separate_netcdf_track_reopen_without_frameit(tmp_path):
    scene().to_netcdf(tmp_path / "input.nc")
    before = hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest()
    conf = configuration(tmp_path, output_format="zarr", products={
        "polar": {"radius_km": 2.5, "azimuth_count": 8}, "track": True})
    result = execute_simulation(conf)
    assert {item["role"] for item in result.products} == {"polar", "track"}
    polar = next(item["path"] for item in result.products if item["role"] == "polar")
    track = next(item["path"] for item in result.products if item["role"] == "track")
    assert polar.endswith("products/polar.atmosphere.polar.zarr")
    assert track.endswith("products/polar.track.nc")
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_zarr(sys.argv[1], consolidated=False) as ds, xr.open_dataset(sys.argv[2]) as track:
    np.testing.assert_allclose(ds.q, 7., atol=1e-10)
    np.testing.assert_array_equal(ds.q_interpolation_status, 0)
    np.testing.assert_array_equal(ds.q_valid, 1)
    assert ds.q_interpolation_status.dtype == np.uint8
    assert 'flag_meanings' in ds.q_interpolation_status.attrs
    np.testing.assert_array_equal(ds.radius, [0.,1.,2.,2.5])
    np.testing.assert_array_equal(ds.time, track.time)
    np.testing.assert_array_equal(ds.center_latitude, track.latitude)
    np.testing.assert_array_equal(ds.center_longitude, track.longitude)
    assert ds.attrs['product_type'] == 'polar'
assert 'frameit' not in sys.modules
""", polar, track], check=True, capture_output=True, text=True)
    assert hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest() == before


def test_mixed_input_preparation_rejects_actual_incompatible_face_and_mass_grids(tmp_path):
    from frameit.testing.numerical.test_grid_representations import native_scene

    native_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, source={
        "variables": {},
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "UT", "v": "VT"}}},
        "field_metadata": {name: {"kind": "continuous"} for name in ("UT", "VT")},
    }, products={"polar": {"radius_km": 2.5, "azimuth_count": 8, "field_options": {
        "atmosphere": {"UT": {"sampling": "native"}, "VT": {"sampling": "mass"}}}}})
    with pytest.raises(ValueError, match="identical dimensions"):
        bind_sources(conf)
    assert not conf.output_dir.exists()


def test_unlisted_fa_source_does_not_join_netcdf_preceding_hour_polar_operation(
        tmp_path, monkeypatch):
    from frameit.testing.numerical.test_fa_io import fa_files
    from frameit.testing.numerical.test_v3_interpretation import _fa_requests
    from frameit.testing.numerical.test_v3_regions import preceding_sources

    sources = preceding_sources(tmp_path)
    for source in sources.values():
        source["field_metadata"] = {"scalar": {"kind": "continuous"}}
    paths = fa_files(tmp_path, profile="surfex_history")
    sources["surface"] = {
        "model": "arome", "files": list(map(str, paths)), "profile": "surfex_history",
        "variables": {"2d": ["SFX.T2M"]},
        "field_metadata": {"SFX.T2M": {
            "kind": "continuous", "units": "K", "temporal_kind": "instantaneous"}},
        "fa": {"earth_radius_m": 6371229.},
    }
    calls = _fa_requests(monkeypatch)
    conf = configuration(tmp_path, sources=sources, region={
        "center": {"latitude": -20., "longitude": 60.},
        "sources_coupling_time_association": "preceding_hour",
    }, products={"polar": {"radius_km": 1., "azimuth_count": 8,
                          "fields": {"weather": ["scalar"], "water": ["scalar"]}}})
    result = execute_simulation(conf)
    assert {item["source"] for item in result.products} == {"weather", "water"}
    assert not any(call["operation"] == "read" for call in calls)
    assert not conf.source_requests["surface"]["binding"]["records"]


@pytest.mark.parametrize("layout", ["dimension_coordinates", "auxiliary_coordinates"])
def test_instructional_rectilinear_geography_survives_horizontal_normalization(
        tmp_path, monkeypatch, layout):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.processing.polar import polar_proj
    from frameit.testing.documentation_example import create_first_run_input

    generated = create_first_run_input(tmp_path / "first-run.nc")
    path = generated
    with xr.open_dataset(generated) as original:
        metadata = {name: dict(original[name].attrs) for name in ("latitude", "longitude")}
        if layout == "auxiliary_coordinates":
            control = original.load().rename_dims(latitude="y", longitude="x").assign_coords(
                y=np.arange(17), x=np.arange(17))
            path = tmp_path / "control.nc"
            control.to_netcdf(path, engine="netcdf4")
    hashes = {item: hashlib.sha256(item.read_bytes()).hexdigest() for item in {generated, path}}
    conf = configuration(tmp_path, source={
        "model": "arome", "files": str(path),
        "variables": {"2d": ["instructional_scalar"]},
        "field_metadata": {"instructional_scalar": {
            "kind": "continuous", "temporal_kind": "instantaneous"}},
    }, products={"polar": {"radius_km": 2., "radial_step_km": 1.5, "azimuth_count": 8}})
    original_read, original_sample = H5NetCDFArrayWrapper.__getitem__, polar_proj._sample_piece
    reads, sampled = [], []

    def read(array, key):
        if array.variable_name == "instructional_scalar":
            reads.extend(np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist())
        return original_read(array, key)

    def sample(source, *args, **kwargs):
        result = original_sample(source, *args, **kwargs)
        for name, axis in (("latitude", "y_box"), ("longitude", "x_box")):
            assert source[name].dims == (axis,)
            assert source[name].attrs == metadata[name]
        sampled.append((source.instructional_scalar.dims, result[1].geometry.provenance["method"]))
        return result

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", read)
    monkeypatch.setattr(polar_proj, "_sample_piece", sample)
    try:
        result = execute_simulation(conf)
        assert result.ok and len(result.products) == 1
        assert result.products[0]["role"] == "polar"
        assert set(reads) == {0, 1}
        assert sampled == [(("time", "y_box", "x_box"), "bilinear")] * 2
        binding = conf.source_requests["atmosphere"]["binding"]
        assert binding["status"] == binding["polar_plan"]["status"] == "bound"
        assert set(binding["products"]) == {"polar"}
        product = conf.simulation_parameter["request_plan"]["products"][0]
        assert product["dimensions"] == {"instructional_scalar": ["time", "radius", "azimuth"]}
        assert product["units"] == {"instructional_scalar": "1"}
        reader = subprocess.run([sys.executable, "-c", """
import sys
import numpy as np
import xarray as xr
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source:
    field = out.instructional_scalar
    assert field.dims == ('time', 'radius', 'azimuth') and field.shape == (2, 3, 8)
    assert field.attrs['units'] == '1'
    assert field.attrs['polar_interpolation'] == 'bilinear'
    assert field.attrs['polar_missing_data_policy'] == 'strict'
    scientific = {n for n in out.data_vars
                  if out[n].attrs.get('frameit_role') != 'interpolation_quality'}
    assert scientific == {'instructional_scalar'}
    np.testing.assert_array_equal(out.radius, [0., 1.5, 2.])
    np.testing.assert_allclose(out.azimuth, np.arange(8) * np.pi / 4, rtol=0, atol=1e-14)
    np.testing.assert_array_equal(out.azimuth_degrees, [0., 45., 90., 135., 180., 225., 270., 315.])
    assert out.radius.attrs['units'] == 'km' and out.azimuth.attrs['units'] == 'rad'
    np.testing.assert_array_equal(out.time, source.valid_time)
    np.testing.assert_array_equal(out.time, np.array(
        ['2000-01-01T00:00', '2000-01-01T01:00'], dtype='datetime64[ns]'))
    np.testing.assert_array_equal(out.center_time, out.time)
    assert out.time.encoding['calendar'] == source.valid_time.encoding['calendar']
    np.testing.assert_array_equal(out.center_latitude, [-20., -20.])
    np.testing.assert_array_equal(out.center_longitude, [60., 60.])
    np.testing.assert_allclose(field.isel(radius=0),
                               np.broadcast_to([[0.], [1000.]], (2, 8)), rtol=0, atol=1e-9)
    assert (out.latitude.isel(radius=-1, azimuth=0) > -20.).all()
    assert (out.longitude.isel(radius=-1, azimuth=2) > 60.).all()
    assert (out.latitude.isel(radius=-1, azimuth=4) < -20.).all()
    assert (out.longitude.isel(radius=-1, azimuth=6) < 60.).all()
    # The missing j=7,i=9 contributes to the two south-east stencils, not the origin.
    missing = np.zeros((2, 3, 8), dtype=bool)
    missing[:, 1:, 3] = True
    np.testing.assert_array_equal(np.isnan(field), missing)
    status = out.instructional_scalar_interpolation_status
    assert status.dtype == np.uint8 and 'missing_source_data' in status.attrs['flag_meanings']
    np.testing.assert_array_equal(status, np.where(missing, 2, 0))
    np.testing.assert_array_equal(out.instructional_scalar_valid, ~missing)
    np.testing.assert_array_equal(out.instructional_scalar_geometry_mapped, 1)
    np.testing.assert_array_equal(out.geometry_mapped, 1)
    support = out.instructional_scalar_support_fraction.values
    np.testing.assert_array_equal(support[~missing], 1.)
    assert ((support[missing] > 0) & (support[missing] < 1)).all()
    np.testing.assert_array_equal(out.instructional_scalar_ring_coverage,
                                   [[1., .875, .875], [1., .875, .875]])
    np.testing.assert_array_equal(out.instructional_scalar_full_ring_valid, [[1, 0, 0], [1, 0, 0]])
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(path)], capture_output=True, text=True)
        assert reader.returncode == 0, reader.stdout + reader.stderr
    finally:
        assert {item: hashlib.sha256(item.read_bytes()).hexdigest() for item in hashes} == hashes


def test_native_scalar_fa_polar_reads_only_selected_leaf_without_vertical_positions(
        tmp_path, monkeypatch):
    from frameit.processing.polar.regrid_plan import PolarRegridPlan
    from frameit.testing.numerical.test_fa_io import fa_files
    from frameit.testing.numerical.test_v3_interpretation import _fa_requests

    values = np.full((7, 9), 300.)
    values[3, 4], values[2, 5] = 0., np.nan
    paths = fa_files(tmp_path, hours=(0, 1, 2), profile="surfex_history", surface_fields=[
        {"name": "T2M", "mask": "FULL", "values": values.tolist()},
        {"name": "SST", "mask": "SEA", "values": np.full((7, 9), 999.).tolist()},
    ])
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    conf = configuration(tmp_path, source={
        "model": "arome", "files": list(map(str, paths)), "profile": "surfex_history",
        "variables": {"2d": ["SFX.T2M"]},
        "field_metadata": {"SFX.T2M": {
            "units": "K", "kind": "continuous", "temporal_kind": "instantaneous"}},
        "fa": {"earth_radius_m": 6371229.},
        "time": {"values": ["2026-01-01T00:00:00", "2026-01-01T02:00:00"]},
        "reader": {"python_executable": sys.executable, "max_points": 1000, "timeout_seconds": 30},
    }, products={"polar": {"radius_km": 2.5, "radial_step_km": 1.5, "azimuth_count": 8}})
    calls = _fa_requests(monkeypatch)
    _, children, sources = bind_sources(conf)
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    records = binding["operation_plans"][0]["input_binding"]["dependencies"]["SFX.T2M"]["records"]
    assert all(record["source_positions"] is None and record["vertical"] is None
               for record in records)
    assert not sources["atmosphere"]["fields"][records[0]["field_id"]].get("native_cube")
    assert not any(call["operation"] == "read" for call in calls)
    original, applications = PolarRegridPlan.apply, []

    def apply(plan, field, *args, **kwargs):
        applications.append((field.name, field.dims, plan.geometry.provenance["method"]))
        return original(plan, field, *args, **kwargs)

    monkeypatch.setattr(PolarRegridPlan, "apply", apply)
    try:
        result = execute_simulation(conf)
        assert result.ok and len(result.products) == 1 and result.products[0]["role"] == "polar"
        assert [item for item in applications if item[0] == "SFX.T2M"] == [
            ("SFX.T2M", ("time", "y_box", "x_box"), "bilinear")] * 2
        reads = [call for call in calls if call["operation"] == "read"]
        assert {call["path"] for call in reads} == {str(paths[0]), str(paths[2])}
        assert {tuple(call["fields"]) for call in reads} == {("SFX.T2M",)}
        assert all(call["max_points"] == 1000 and call["timeout_seconds"] == 30 for call in reads)
        reader = subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    field = out['SFX.T2M']
    assert field.dims == ('time','radius','azimuth') and field.shape == (2,3,8)
    scientific = {n for n in out.data_vars
                  if out[n].attrs.get('frameit_role') != 'interpolation_quality'}
    assert scientific == {'SFX.T2M'} and 'SFX.SST' not in out
    assert field.attrs['units'] == 'K' and field.attrs['temporal_kind'] == 'instantaneous'
    assert field.attrs['polar_missing_data_policy'] == 'strict'
    np.testing.assert_array_equal(out.time, np.array(
        ['2026-01-01T00:00','2026-01-01T02:00'], dtype='datetime64[ns]'))
    np.testing.assert_array_equal(out.center_time, out.time)
    np.testing.assert_array_equal(out.radius, [0.,1.5,2.5])
    np.testing.assert_allclose(field.isel(radius=0), 0., rtol=0, atol=1e-8)
    np.testing.assert_allclose(field.isel(radius=-1),
                               [[300.,300.,300.,np.nan,300.,300.,300.,300.]]*2, rtol=0, atol=1e-8)
    missing = np.zeros((2,3,8), dtype=bool)
    missing[:,1:,3] = True
    np.testing.assert_array_equal(np.isnan(field), missing)
    status = out['SFX.T2M_interpolation_status']
    assert status.dtype == np.uint8
    np.testing.assert_array_equal(status, np.where(missing,2,0))
    np.testing.assert_array_equal(out['SFX.T2M_geometry_mapped'], 1)
    np.testing.assert_array_equal(out['SFX.T2M_valid'], ~missing)
    support = out['SFX.T2M_support_fraction'].values
    np.testing.assert_array_equal(support[~missing], 1.)
    assert ((support[missing] > 0) & (support[missing] < 1)).all()
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
assert not {'epygram','falfilfa4py'} & sys.modules.keys()
""", result.products[0]["path"]], capture_output=True, text=True)
        assert reader.returncode == 0, reader.stdout + reader.stderr
    finally:
        assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == before


@pytest.mark.parametrize("shape", ["scalar", "cube"])
@pytest.mark.parametrize("damage", ["locator", "support"])
def test_fa_polar_guard_rejects_corrupted_native_scalar_or_cube_support(
        tmp_path, monkeypatch, shape, damage):
    from frameit.processing.polar.contracts import require_executable_products
    from frameit.testing.numerical.test_fa_cubes import DECLARATION, fixtures
    from frameit.testing.numerical.test_fa_io import fa_files
    from frameit.testing.numerical.test_v3_interpretation import _fa_requests

    if shape == "scalar":
        paths = fa_files(tmp_path, profile="surfex_history")
        name, profile, longitude = "SFX.T2M", "surfex_history", 60.
        selection = {"variables": {"2d": [name]}}
    else:
        paths = fixtures(tmp_path, hours=(0,))
        name, profile, longitude = "temperature", "arome_history", 50.
        selection = {"variables": {"3d": [name], "levels": {"indices": [2, 0]}},
                     "native_cubes": {name: {
                         "records": [f"S{k:03d}TEMPERATURE" for k in (1, 2, 3)],
                         "vertical_position": "mass", "sampling": "center"}}}
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    conf = configuration(tmp_path, source={
        "model": "arome", "files": list(map(str, paths)), "profile": profile,
        "field_metadata": {name: DECLARATION}, "fa": {"earth_radius_m": 6371229.}, **selection,
    }, region={"center": {"latitude": -20., "longitude": longitude}})
    calls = _fa_requests(monkeypatch)
    _, children, sources = bind_sources(conf)
    binding = deepcopy(children["atmosphere"].source_requests["atmosphere"]["binding"])
    record = binding["operation_plans"][0]["input_binding"]["dependencies"][name]["records"][0]
    if damage == "locator":
        record["locator"]["records"] = []
    elif shape == "scalar":
        record["source_positions"] = [0]
    else:
        record["source_positions"] = None
        native = next(item for item in sources["atmosphere"]["record_inventory"]
                      if item["field_id"] == record["field_id"])
        record["locator"] = deepcopy(native["locator"])
    with pytest.raises(ValueError, match="Polar plan evidence"):
        require_executable_products(binding, sources["atmosphere"])
    assert not any(call["operation"] == "read" for call in calls)
    assert not conf.output_dir.exists()
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == before


def review_shared_configuration(tmp_path, polar, *, fine_hours=(0, 1), damage=None):
    sources, paths = {}, []
    for name, model, spacing, hours in (
            ("weather", "mesonh", 1000., fine_hours), ("water", "nemo", 3000., (0, 1))):
        ds = scene(hours=hours, spacing=spacing)
        ds.q.values[:] = 7. if name == "weather" else 11.
        if name == "weather":
            ds.q.attrs.pop("kind")
            if damage == "dtype":
                ds["q"] = ds.q.copy(data=np.full(ds.q.shape, 2**53 + 1, dtype="int64"))
        if name == "weather" and damage == "geometry":
            ds.longitude.values[4, 4] = np.nan
        if model == "nemo":
            ds = ds.rename(time="time_counter", nj="y", ni="x",
                           latitude="nav_lat", longitude="nav_lon")
        path = tmp_path / f"{name}.nc"
        ds.to_netcdf(path)
        paths.append(path)
        sources[name] = {"model": model, "files": str(path), "variables": {"2d": ["q"]}}
    return configuration(tmp_path, sources=sources, products={
        "polar": {"radius_km": 4., "shared_grid": True, **polar}}), paths


@pytest.mark.parametrize("count,limit,fine_hours", [
    (9, 60, (0, 1)), (None, 60, (0, 1)),
    (9, 53, (0, 1)), (None, 53, (0, 1)), (9, 53, (0,)),
])
def test_review_shared_budget_uses_only_final_axes_and_retains_bind_once(
        tmp_path, monkeypatch, count, limit, fine_hours):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.core import preflight
    from frameit.processing.polar import sampling

    options = {"processing": {"max_target_points": limit}}
    if count is not None:
        options["azimuth_count"] = count
    conf, paths = review_shared_configuration(tmp_path, options, fine_hours=fine_hours)
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    original_bind, original_read = preflight.bind_source, H5NetCDFArrayWrapper.__getitem__
    original_axes = sampling.sampling_axes
    bound, reads, steps = [], [], []

    def bind(child, name, **kwargs):
        binding = original_bind(child, name, **kwargs)
        source = child.simulation_parameter["request_plan"]["sources"][name]
        bound.append((child, name, binding, source))
        assert binding["status"] == "pending_polar_target"
        assert binding["polar_plan"]["status"] == "prepared"
        assert not binding["deferred_checks"]
        assert child.source_requests[name]["binding"] is None
        assert source["requests"]["binding"] is None
        assert all(item["execution"] == "pending_polar_sampling"
                   for item in binding["products"]["polar"].values())
        return binding

    def read(array, key):
        if array.variable_name == "q":
            assert limit == 60
            reads.append(np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist())
        return original_read(array, key)

    def axes(settings):
        steps.append(settings.radial_resolution)
        return original_axes(settings)

    monkeypatch.setattr(preflight, "bind_source", bind)
    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", read)
    monkeypatch.setattr(sampling, "sampling_axes", axes)
    try:
        if limit == 53:
            with pytest.raises(ValueError, match="requires 54 points"):
                execute_simulation(conf)
            assert not reads and not conf.output_dir.exists()
            assert all(request["binding"] is None for request in conf.source_requests.values())
            for child, name, binding, source in bound:
                assert binding["status"] != "bound"
                assert binding["polar_plan"]["status"] != "bound"
                assert child.source_requests[name]["binding"] is None
                assert source["requests"]["binding"] is None
                assert all(item["execution"] != "bound_polar_sampling"
                           for item in binding["products"]["polar"].values())
        else:
            result = execute_simulation(conf)
            assert result.ok and reads and len(result.products) == 2
            for child, name, binding, source in bound:
                assert child.source_requests[name]["binding"] is binding
                assert source["requests"]["binding"] is binding
                assert binding["status"] == binding["polar_plan"]["status"] == "bound"
                assert binding["polar_plan"]["target_points"] == 54
                assert binding["polar_plan"]["radial_step_km"] == 3.
                assert binding["polar_plan"]["n_theta"] == 9
                origin = binding["polar_plan"]["angular_sampling_source"]
                assert origin == (
                    "requested_point_count" if count else "automatic_outer_ring_spacing")
            for product in result.products:
                reader = subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    assert out.q.dims == ('time','radius','azimuth') and out.q.shape == (2,3,9)
    np.testing.assert_array_equal(out.radius, [0.,3.,4.])
    np.testing.assert_array_equal(out.azimuth_degrees, np.arange(9)*40.)
    np.testing.assert_allclose(out.azimuth, np.arange(9)*2*np.pi/9, rtol=0, atol=1e-14)
    np.testing.assert_array_equal(out.time, np.array(
        ['2024-01-01T00:00','2024-01-01T01:00'], dtype='datetime64[ns]'))
    np.testing.assert_array_equal(out.center_time, out.time)
    expected = np.full((2,3,9), float(sys.argv[2]))
    # The approximate 9x9 fine-source latitude extent stops just short of 4 km north.
    if sys.argv[2] == '7':
        expected[:,-1,0] = np.nan
    missing = np.isnan(expected)
    np.testing.assert_allclose(out.q, expected, rtol=0, atol=1e-10)
    np.testing.assert_array_equal(out.q_interpolation_status, missing.astype(np.uint8))
    np.testing.assert_array_equal(out.q_support_fraction, ~missing)
    np.testing.assert_array_equal(out.q_geometry_mapped, ~missing)
    assert out.q.attrs['units'] == 'K'
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], "7" if product["source"] == "weather" else "11"],
                    capture_output=True, text=True)
                assert reader.returncode == 0, reader.stdout + reader.stderr
        assert len(bound) == 2 and len({id(item[0]) for item in bound}) == 2
        assert steps == ([3000.] if limit == 53 and len(fine_hours) == 2 else [3000., 3000.])
    finally:
        assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == hashes


@pytest.mark.parametrize("damage", ["step", "dtype", "geometry", "method", "halo", "pending"])
def test_review_shared_preparation_failures_never_gain_clearance(tmp_path, monkeypatch, damage):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.core import preflight

    options = {"azimuth_count": 9, "processing": {"max_target_points": 60}}
    if damage == "step":
        options["radial_step_km"] = 1.
    conf, paths = review_shared_configuration(tmp_path, options, damage=damage)
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    original_bind, original_read = preflight.bind_source, H5NetCDFArrayWrapper.__getitem__
    children = []

    def bind(child, name, **kwargs):
        children.append((child, name))
        if damage == "halo" and name == "weather":
            child.polar_source_halo_points = 0
        if damage == "method" and name == "weather":
            child.source_requests[name]["polar_options"]["q"] = {
                "interpolation": "nearest", "missing_data_policy": "renormalize",
                "min_valid_weight_fraction": .75}
        binding = original_bind(child, name, **kwargs)
        if damage == "pending" and name == "water":
            binding["status"] = "pending_method_binding"
            binding["deferred_checks"].append("Unresolved preparation, not target-only pending")
        return binding

    def no_payload(array, key):
        assert array.variable_name != "q"
        return original_read(array, key)

    monkeypatch.setattr(preflight, "bind_source", bind)
    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", no_payload)
    message = {"step": "finer", "dtype": "int64", "geometry": "coordinates",
               "method": "nearest", "halo": "halo", "pending": "Unresolved"}[damage]
    with pytest.raises(ValueError, match=message):
        execute_simulation(conf)
    assert not conf.output_dir.exists()
    assert all(request["binding"] is None for request in conf.source_requests.values())
    for child, name in children:
        source = child.simulation_parameter["request_plan"]["sources"][name]
        assert child.source_requests[name]["binding"] is None
        assert source["requests"]["binding"] is None
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == hashes


def test_review_shared_failed_rebind_revokes_previous_owner_clearance(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.processing.polar.contracts import require_executable_products

    conf, paths = review_shared_configuration(tmp_path, {
        "azimuth_count": 9, "processing": {"max_target_points": 60}})
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    original_read = H5NetCDFArrayWrapper.__getitem__

    def no_payload(array, key):
        assert array.variable_name != "q"
        return original_read(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", no_payload)
    bind_sources(conf)
    old_sources = conf.simulation_parameter["request_plan"]["sources"]
    old_bindings = {name: source["requests"]["binding"] for name, source in old_sources.items()}
    assert all(binding["status"] == "bound" for binding in old_bindings.values())
    conf.yaml_config["products"]["polar"]["processing"]["max_target_points"] = 53
    conf.polar_max_points = 53
    with pytest.raises(ValueError, match="requires 54 points"):
        bind_sources(conf)
    assert not conf.output_dir.exists()
    assert "common_polar_target" not in conf.simulation_parameter
    assert all(request["binding"] is None for request in conf.source_requests.values())
    for name, source in old_sources.items():
        assert source["requests"]["binding"] is None
        with pytest.raises(ValueError, match="owning source"):
            require_executable_products(old_bindings[name], source)
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == hashes


def test_polar_integers_without_kind_preserve_fractions_and_native_exports(
        tmp_path, monkeypatch):
    from frameit.processing.polar.regrid_plan import PolarRegridPlan

    ds = scene(hours=(0,)).isel(nj=slice(2, 7), ni=slice(2, 7))
    ramp = np.broadcast_to(np.arange(5, dtype=np.int32), (1, 5, 5)).copy()
    dims = ("time", "nj", "ni")
    ds["q"] = (dims, ramp, {"units": "K"})
    ds["negative"] = (dims, -ramp, {"kind": "continuous", "units": "1"})
    ds["floating32"] = (dims, ramp.astype(np.float32), {"kind": "continuous", "units": "K"})
    masked = ramp.astype(np.float64)
    masked[:, 1, 3] = np.nan
    ds["masked"] = (dims, masked, {"kind": "continuous", "units": "K"})
    ds["classes"] = (dims, 10 * ramp, {
        "kind": "categorical", "units": "1", "flag_values": np.arange(5, dtype=np.int32) * 10,
        "flag_meanings": "zero ten twenty thirty forty"})
    path = tmp_path / "input.nc"
    ds.to_netcdf(path, encoding={
        name: {"_FillValue": None} for name in ("q", "negative", "classes")})
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    fields = ["q", "negative", "floating32", "masked", "classes"]
    longitude = float((ds.longitude[2, 2] + ds.longitude[2, 3]) / 2)
    conf = configuration(tmp_path, source={"variables": {"2d": fields}},
                         region={"center": {"latitude": -20., "longitude": longitude}},
                         products={"model_grid": True, "polar": {
                             "radius_km": 1., "azimuth_count": 4}})
    original, evaluations = PolarRegridPlan.apply, {}

    def apply(plan, field, *args, **kwargs):
        evaluations[field.name] = str(field.dtype)
        return original(plan, field, *args, **kwargs)

    monkeypatch.setattr(PolarRegridPlan, "apply", apply)
    try:
        result = execute_simulation(conf)
        assert result.ok and {item["role"] for item in result.products} == {"polar", "model_grid"}
        products = {item["role"]: item["path"] for item in result.products}
        reader = subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as polar, xr.open_dataset(sys.argv[2]) as native, \
xr.open_dataset(sys.argv[3]) as source:
    for name, expected in (('q',2.5),('negative',-2.5),('floating32',2.5),('masked',2.5)):
        np.testing.assert_allclose(polar[name].isel(radius=0), expected, rtol=0, atol=1e-8)
        np.testing.assert_array_equal(polar[name+'_interpolation_status'].isel(radius=0), 0)
        np.testing.assert_array_equal(polar[name+'_support_fraction'].isel(radius=0), 1.)
        assert polar[name].attrs['polar_interpolation'] == 'bilinear'
        assert polar[name].attrs['units'] == source[name].attrs['units']
    for name in ('q','negative','classes'):
        assert native[name].dtype == source[name].dtype == np.dtype('int32')
        np.testing.assert_array_equal(native[name], source[name])
    assert native.floating32.dtype == source.floating32.dtype == np.dtype('float32')
    np.testing.assert_array_equal(native.masked, source.masked)
    np.testing.assert_array_equal(np.isnan(native.masked), np.isnan(source.masked))
    assert polar.q.dtype == polar.negative.dtype == np.dtype('float64')
    assert 'kind' not in polar.q.attrs and 'kind' not in native.q.attrs
    assert polar.floating32.dtype == np.dtype('float32')
    assert polar.masked.dtype == np.dtype('float64')
    missing = np.zeros((1,2,4), dtype=bool)
    missing[:,1,2] = True
    np.testing.assert_array_equal(np.isnan(polar.masked), missing)
    np.testing.assert_array_equal(polar.masked_interpolation_status, np.where(missing,2,0))
    np.testing.assert_array_equal(polar.masked_geometry_mapped, 1)
    assert polar['classes'].attrs['polar_interpolation'] == 'nearest_s2d'
    assert set(np.unique(polar['classes'])) <= {0.,10.,20.,30.,40.}
    assert set(polar['classes'].isel(radius=0).values.ravel()) <= {20.,30.}
    np.testing.assert_array_equal(polar.classes_interpolation_status, 0)
    np.testing.assert_array_equal(polar.time, source.time)
    np.testing.assert_array_equal(polar.center_time, source.time)
    for name, evaluation in (('q','float64'),('negative','float64'),('floating32','float32'),
                             ('masked','float64'),('classes','int32')):
        facts = json.loads(polar[name].attrs['polar_numeric_types'])[name]
        assert facts['evaluation_dtype'] == evaluation
        assert facts['prepared_dtype'] == str(source[name].dtype)
        assert facts['conversion'] == {
            'q':'integer_to_float64_for_bilinear',
            'negative':'integer_to_float64_for_continuous_bilinear',
        }.get(name, 'none')
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", products["polar"], products["model_grid"], str(path)], capture_output=True, text=True)
        assert reader.returncode == 0, reader.stdout + reader.stderr
        assert evaluations == {"q": "float64", "negative": "float64", "floating32": "float32",
                               "masked": "float64", "classes": "int32"}
        provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
        records = provenance["sources"]["atmosphere"]["polar"]["records"]
        for record in records:
            facts = record["numeric_types"][record["field"]]
            assert facts["evaluation_dtype"] == evaluations[record["field"]]
            assert facts["prepared_dtype"] == str(ds[record["field"]].dtype)
    finally:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
