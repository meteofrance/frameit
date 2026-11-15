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
def test_polar_methods_require_kind_evidence_and_preview_without_payload(
        tmp_path, monkeypatch, kind):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    ds = scene()
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
    if kind is None:
        with pytest.raises(ValueError, match="kind"):
            bind_sources(conf)
    else:
        _, children, _ = bind_sources(conf)
        binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
        assert binding["polar_plan"]["status"] == "bound"
        job = binding["operation_plans"][0]
        assert job["polar_options"]["q"]["interpolation"] == (
            "nearest_s2d" if kind == "categorical" else "bilinear")
        assert job["polar_options"]["q"]["kind_origin"] == (
            "input" if kind == "categorical" else "declaration")
    assert not conf.output_dir.exists()


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
        if name == "weather" and damage == "kind":
            ds.q.attrs.pop("kind")
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


@pytest.mark.parametrize("damage", ["step", "kind", "geometry", "method", "halo", "pending"])
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
    message = {"step": "finer", "kind": "kind", "geometry": "coordinates",
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


def test_review_integer_continuous_bilinear_preserves_fractions_and_native_exports(
        tmp_path, monkeypatch):
    from frameit.processing.polar.regrid_plan import PolarRegridPlan

    ds = scene(hours=(0,)).isel(nj=slice(2, 7), ni=slice(2, 7))
    ramp = np.broadcast_to(np.arange(5, dtype=np.int32), (1, 5, 5)).copy()
    dims = ("time", "nj", "ni")
    ds["q"] = (dims, ramp, {"kind": "continuous", "units": "K"})
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
        assert facts['conversion'] == ('integer_to_float64_for_continuous_bilinear'
                                       if name in {'q','negative'} else 'none')
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
