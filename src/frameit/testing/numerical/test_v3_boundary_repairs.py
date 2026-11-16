"""Explicit boundary choices; compact fixtures are not producer qualification."""

from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from frameit.core.configuration import resolve_schema
from frameit.core.execution import execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig

from .test_configuration_v2_1 import dataset, document


def test_polar_units_are_explicit_and_do_not_change_native_output(tmp_path):
    dataset(tmp_path, units="km/h", speed=36.)
    path = tmp_path / "native.nc"
    before = path.read_bytes(), path.stat().st_mtime_ns
    raw = document(tmp_path, resources={"synchronous_export": True, "cpus": 1})
    raw["products"] = {
        "model_grid": True,
        "polar": {"radius_km": 10, "azimuth_count": 16,
                  "fields": {"atmosphere": ["UM10"]}}}
    outputs = []
    for converted in (False, True):
        selected = deepcopy(raw)
        selected["output"]["directory"] = str(tmp_path / str(converted))
        if converted:
            selected["products"]["polar"]["field_options"] = {
                "atmosphere": {"UM10": {"units": "m s-1"}}}
        result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(selected))
        products = {p["role"]: p["path"] for p in result.products}
        with xr.open_dataset(products["model_grid"]) as saved:
            np.testing.assert_allclose(saved.UM10, 36.)
            assert saved.UM10.attrs["units"] == "km/h"
        with xr.open_dataset(products["polar"]) as saved:
            saved.load()
            np.testing.assert_allclose(saved.UM10, 10. if converted else 36.)
            assert saved.UM10.attrs["units"] == ("m s-1" if converted else "km/h")
            outputs.append(saved)
    for suffix in ("valid", "support_fraction", "interpolation_status", "geometry_mapped"):
        xr.testing.assert_identical(outputs[0][f"UM10_{suffix}"], outputs[1][f"UM10_{suffix}"])
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_incompatible_polar_units_fail_before_output(tmp_path):
    dataset(tmp_path)
    raw = document(tmp_path)
    raw["products"]["polar"] = {
        "radius_km": 10, "field_options": {"atmosphere": {"UM10": {"units": "K"}}}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="units"):
        preflight(conf)
    assert not conf.output_dir.exists()


def test_derived_polar_result_cannot_override_method_units(tmp_path):
    raw = document(tmp_path)
    raw["sources"]["atmosphere"]["derived"] = {
        "speed": {"method": "wind_speed", "inputs": {"u": "UM10", "v": "VM10"}}}
    raw["products"]["polar"] = {
        "radius_km": 10, "fields": {"atmosphere": ["speed"]},
        "field_options": {"atmosphere": {"speed": {"units": "km/h"}}}}
    with pytest.raises(ValueError, match="derived|base"):
        resolve_schema(raw)


def gap_case(tmp_path, missing=(0,), *, layered=False):
    times = np.array(["2024-01-01", "2024-01-01T01", "2024-01-01T02"],
                     dtype="datetime64[ns]")
    coordinates = {
        "time": times,
        "latitude": ("latitude", [-20.01, -20., -19.99], {"units": "degrees_north"}),
        "longitude": ("longitude", [59.99, 60., 60.01], {"units": "degrees_east"})}
    xr.Dataset({"prmsl": (("time", "latitude", "longitude"),
                         np.full((3, 3, 3), 100000.), {"units": "Pa"})},
               coords=coordinates).to_netcdf(tmp_path / "reference.nc")
    if layered:
        xr.Dataset({"tracer": (("time", "level", "latitude", "longitude"),
                               np.ones((3, 2, 3, 3)), {"units": "1"})},
                   coords={**coordinates, "level": (
                       "level", [10., 30.], {"units": "m", "positive": "up"})}
                   ).to_netcdf(tmp_path / "reference.nc")
    kept = [index for index in range(3) if index not in missing]
    dimensions = ("time", "level", "latitude", "longitude") if layered else (
        "time", "latitude", "longitude")
    shape = (len(kept), 2, 3, 3) if layered else (len(kept), 3, 3)
    values = np.broadcast_to(
        (280. + np.array(kept)).reshape((-1,) + (1,) * (len(shape) - 1)), shape).copy()
    selected = dict(coordinates, time=times[kept])
    if layered:
        selected["level"] = ("level", [10., 30.], {"units": "m", "positive": "up"})
    xr.Dataset({"temperature": (dimensions, values, {"units": "K"})},
               coords=selected).to_netcdf(tmp_path / "temperature.nc")
    return {
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "arome", "files": [str(tmp_path / name) for name in (
                "reference.nc", "temperature.nc")],
            "variables": ({"3d": ["tracer", "temperature"]} if layered else
                          {"2d": ["prmsl", "temperature"]}),
            "field_metadata": {"temperature": {"kind": "continuous"}},
            "allow_initial_gaps": ["temperature"]}},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"synchronous_export": True, "cpus": 1}}


@pytest.mark.parametrize("layered", [False, True])
@pytest.mark.parametrize("product", ["model_grid", "polar"])
def test_declared_initial_absence_preserves_clock_and_later_values(tmp_path, layered, product):
    raw = gap_case(tmp_path, layered=layered)
    if product == "polar":
        raw["products"]["polar"] = {
            "radius_km": .5, "azimuth_count": 8,
            "fields": {"atmosphere": ["temperature"]}}
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.glob("*.nc")}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    report = preflight(conf)
    source = report["sources"]["atmosphere"]
    assert len(source["selected_times"]) == 3
    assert source["allowed_gaps"] == [{
        "field": "temperature", "time": np.datetime64("2024-01-01", "ns"),
        "reason": "declared_initial_absence"}]
    assert all(record["locator"].get("path") for record in source["records"])
    result = execute_simulation(conf)
    path = next(p["path"] for p in result.products if p["role"] == product)
    with xr.open_dataset(path) as saved:
        assert saved.sizes["time"] == 3
        assert np.isnan(saved.temperature.isel(time=0)).all()
        for index, want in ((1, 281.), (2, 282.)):
            values = saved.temperature.isel(time=index).values
            assert np.isfinite(values).any()
            np.testing.assert_allclose(values[np.isfinite(values)], want)
        if product == "polar":
            assert (saved.temperature_valid.isel(time=0) == 0).all()
            assert (saved.temperature_support_fraction.isel(time=0) == 0).all()
            assert (saved.temperature_interpolation_status.isel(time=0) == 2).all()
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before


@pytest.mark.parametrize("missing,declared", [((0,), False), ((1,), True), ((0, 1), True)])
def test_initial_gap_opt_in_does_not_allow_other_absences(tmp_path, missing, declared):
    raw = gap_case(tmp_path, missing)
    if not declared:
        del raw["sources"]["atmosphere"]["allow_initial_gaps"]
    with pytest.raises(ValueError, match="unavailable|missing"):
        preflight(SimulationConfig.from_mapping_with_model_preset(raw))
