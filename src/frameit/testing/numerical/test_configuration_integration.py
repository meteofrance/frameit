"""Current-schema integration requiring the native stack and frozen fixture."""

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.configuration import resolved_configuration
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.settings_class import SimulationConfig

from .test_configuration_v2_1 import dataset, document


def _product_paths(result):
    assert result.ok and len(result.products) == 3
    paths = {(p["role"], p["source"]): p["path"] for p in result.products}
    assert paths.keys() == {("track", None), ("model_grid", "atmosphere"), ("polar", "atmosphere")}
    return paths


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
    raw["output"]["directory"] = "./yaml"
    source["files"] = "./*.nc"
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    yaml_conf = SimulationConfig.from_yaml(path)
    assert yaml_conf.output_dir == tmp_path / "yaml"
    mapping_products, yaml_products = (
        _product_paths(
            execute_simulation(c, ExecutionOptions.from_config(c, synchronous_export=True))
        )
        for c in (conf, yaml_conf)
    )
    replay = SimulationConfig.from_yaml(conf.output_dir / "resolved-config.yaml")
    from frameit.core.preflight import preflight

    replay_source = preflight(replay, check_output=False)["sources"]["atmosphere"]
    geometry, = replay_source["region"]["grids"].values()
    assert geometry["geometry"]["effective_spacing_m"] == 2500
    assert replay_source["requests"]["binding"]["polar_plan"]["radial_step_km"] == 2.5
    assert (conf.output_dir / "run-provenance.yaml").exists()
    for key, product in mapping_products.items():
        with xr.open_dataset(product) as ds, xr.open_dataset(yaml_products[key]) as from_yaml:
            xr.testing.assert_allclose(ds, from_yaml, rtol=1e-10, atol=1e-10)
            if key[0] == "model_grid":
                np.testing.assert_allclose(ds.wind_speed, 10.)
                assert ds.temperature.attrs["units"] == "K"
                assert ds.x_box_km.attrs["units"] == "km"
            elif key[0] == "polar":
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
    """Check both constructors select the same request, then run it once via YAML."""
    from frameit.testing.catalog import load_cases, resolve_case
    from frameit.testing.datasets import ci_dataset_root

    root = ci_dataset_root()
    case = next(
        c for c in load_cases() if c["dataset_id"].startswith(f"{model}/") and c["polar"]
        and c["tracker"] == ("fixed_box" if model == "AROME" else "wind_pressure")
    )
    context = {}
    if model == "AROME":
        rejected = resolve_case(case, root, tmp_path / "unsupported", context=context)
        assert case["config"]["products"]["polar"]["radial_step_km"] == 2.5
        assert rejected["preflight"] == "INVALID_INPUT"
        assert "not supported yet" in rejected["reason"]
        minimum = rejected["reason"].partition("minimum supported radial_step_km=")[2]
        assert minimum and float(minimum.split()[0]) > 2.5, rejected["reason"]
        # Replay a separate supported-native variant; the original 2.5-km request stays rejected.
        case["config"]["products"]["polar"].pop("radial_step_km")
    case = resolve_case(case, root, tmp_path / "mapping", context=context)
    assert case["preflight"] == "READY", case["reason"]
    # Both replay paths use the same explicit source conventions. This is a
    # configuration-equivalence regression, not scientific validation of them.
    source = case["config"]["sources"]["atmosphere"]
    source["wind_pairs"] = (
        [{"u": f"{group}.u", "v": f"{group}.v", "basis": "earth"}
         for group in ("heightAboveGround", "isobaric")]
        + [{"u": "u10", "v": "v10", "basis": "earth"}]
        if model == "AROME" else
        [{"u": "level.UT", "v": "level.VT", "basis": "grid",
          "rotation": {"method": "geolocation"}},
         {"u": "UM10", "v": "VM10", "basis": "earth"}]
    )
    case["config"]["resources"] = {
        "cpus": 1, "scheduler": "synchronous", "synchronous_export": True}
    mapping = SimulationConfig.from_mapping_with_model_preset(case["config"])
    output = str(tmp_path / "yaml")
    raw = {**case["config"], "output": {**case["config"]["output"], "directory": output}}
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    conf = SimulationConfig.from_yaml(path)
    effective = resolved_configuration(mapping)
    effective["output"]["directory"] = output
    assert resolved_configuration(conf) == effective
    assert conf.source_requests == mapping.source_requests

    products = _product_paths(execute_simulation(conf, input_files=tuple(case["input_files"])))
    contracts = {(p["role"], p["source"]): p for p in case["expected"]["products"]}
    assert products.keys() == contracts.keys()
    for key, product in products.items():
        contract = contracts[key]
        with xr.open_dataset(product) as ds:
            times = np.array(contract["times"], dtype="datetime64[ns]")
            np.testing.assert_array_equal(ds.time, times)
            assert set(contract["variables"]) <= ds.data_vars.keys()
            for field, dims in contract.get("dimensions", {}).items():
                assert ds[field].dims == tuple(dims)
            for axis, levels in contract.get("levels", {}).items():
                np.testing.assert_array_equal(ds.coords[axis], levels)
