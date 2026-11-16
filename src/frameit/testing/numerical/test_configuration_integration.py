"""Current-schema integration requiring the native stack and frozen fixture."""

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.settings_class import SimulationConfig

from .test_configuration_v2_1 import dataset, document


def test_new_yaml_real_pipeline_exports_and_replay(tmp_path):
    dataset(tmp_path, units="km/h", speed=36.)
    raw = document(tmp_path)
    source = raw["sources"]["atmosphere"]
    fields = ["UM10", "VM10", "MSLP", "temperature", "wind_speed"]
    source["variables"]["2d"] = fields[:-1]
    source["transforms"] = [
        {"fields": ["UM10", "VM10"], "sampling": "mass", "basis": "earth", "units": "m s-1"}]
    source["derived"] = {
        name: {"method": method, "inputs": {"u": "UM10", "v": "VM10"}}
        for name, method in (
            ("wind_speed", "wind_speed"), ("vrad", "radial_wind"), ("vtan", "tangential_wind"))}
    raw["region"]["width_km"] = {"x": 20, "y": 20}
    raw["products"] = {
        "model_grid": {"fields": {"atmosphere": fields}}, "track": True,
        "polar": {"radius_km": 10, "azimuth_count": 16,
                  "field_options": {"atmosphere": {
                      "UM10": {"units": "m s-1"}, "VM10": {"units": "m s-1"}}},
                  "fields": {"atmosphere": [*fields, "vrad", "vtan"]}}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf, ExecutionOptions.from_config(conf, synchronous_export=True))
    assert result.ok and len(result.products) == 3
    replay = SimulationConfig.from_yaml(conf.output_dir / "resolved-config.yaml")
    from frameit.core.preflight import preflight

    replay_source = preflight(replay, check_output=False)["sources"]["atmosphere"]
    geometry, = replay_source["region"]["grids"].values()
    assert geometry["geometry"]["effective_spacing_m"] == 2500
    assert replay_source["requests"]["binding"]["polar_plan"]["radial_step_km"] == 2.5
    assert (conf.output_dir / "run-provenance.yaml").exists()
    cart = next(p["path"] for p in result.products if p["role"] == "model_grid")
    polar = next(p["path"] for p in result.products if p["role"] == "polar")
    with xr.open_dataset(cart) as ds:
        np.testing.assert_allclose(ds.wind_speed, 10.)
        assert ds.temperature.attrs["units"] == "K"
        assert ds.x_box_km.attrs["units"] == "km"
    with xr.open_dataset(polar) as ds:
        assert ds.UM10.attrs["units"] == "m s-1"
        np.testing.assert_allclose(ds.wind_speed.where(ds.wind_speed.notnull(), 10), 10.)
        assert np.isnan(ds.vrad.isel(radius=0)).all()
        assert np.isnan(ds.vtan.isel(radius=0)).all()
        np.testing.assert_allclose(
            ds.vrad.isel(radius=slice(1, None)),
            10 * np.sin(ds.radial_bearing.isel(radius=slice(1, None))), atol=1e-12)
        np.testing.assert_allclose(
            ds.vtan.isel(radius=slice(1, None)),
            10 * np.cos(ds.radial_bearing.isel(radius=slice(1, None))), atol=1e-12)


@pytest.mark.parametrize("model", ["AROME", "MNH"])
def test_frozen_matrix_yaml_and_mapping_requests_match(tmp_path, model):
    """Exercise both real adapters through strict YAML and mapping boundaries."""
    from frameit.testing.catalog import load_cases, resolve_case
    from frameit.testing.datasets import ci_dataset_root

    root = ci_dataset_root()
    case = next(
        c for c in load_cases() if c["dataset_id"].startswith(f"{model}/") and c["polar"]
        and c["tracker"] == ("fixed_box" if model == "AROME" else "wind_pressure")
    )
    case = resolve_case(case, root, tmp_path / "mapping")
    assert case["preflight"] == "READY", case["reason"]
    # Both replay paths use the same explicit source conventions. This is a
    # configuration-equivalence regression, not scientific validation of them.
    source = case["config"]["sources"]["atmosphere"]
    source["wind_pairs"] = (
        [{"u": f"{group}.u", "v": f"{group}.v", "basis": "earth"}
         for group in ("heightAboveGround", "isobaricInhPa")]
        + [{"u": "u10", "v": "v10", "basis": "earth"}]
        if model == "AROME" else
        [{"u": "level.UT", "v": "level.VT", "basis": "grid",
          "rotation": {"method": "geolocation"}},
         {"u": "UM10", "v": "VM10", "basis": "earth"}]
    )
    case["config"]["resources"] = {
        "cpus": 1, "scheduler": "synchronous", "synchronous_export": True}
    mapping = SimulationConfig.from_mapping_with_model_preset(case["config"])
    raw = {**case["config"], "output": {**case["config"]["output"], "directory": str(tmp_path / "yaml")}}
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(raw))
    conf = SimulationConfig.from_yaml(path)
    a = execute_simulation(mapping, input_files=tuple(case["input_files"]))
    b = execute_simulation(conf, input_files=tuple(case["input_files"]))
    products_a = {(item["role"], item["source"]): item["path"] for item in a.products}
    products_b = {(item["role"], item["source"]): item["path"] for item in b.products}
    assert products_a.keys() == products_b.keys() == {
        ("track", None), ("model_grid", "atmosphere"), ("polar", "atmosphere")}
    for key in products_a:
        with xr.open_dataset(products_a[key]) as actual, xr.open_dataset(products_b[key]) as replay:
            xr.testing.assert_allclose(actual, replay, rtol=1e-10, atol=1e-10)
