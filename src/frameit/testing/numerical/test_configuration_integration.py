"""Current-schema integration requiring the native stack and frozen fixture."""

from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.settings_class import SimulationConfig

from .test_configuration_v2_1 import dataset, document


def test_new_yaml_real_pipeline_exports_and_replay(tmp_path):
    dataset(tmp_path, units="km/h", speed=36.)
    raw = document(tmp_path, domain={"width_km": {"x": 20, "y": 20}},
                   polar={"enabled": True, "azimuth_count": 16},
                   variables={"surface": {"names": ["UM10", "VM10", "MSLP", "temperature"]}})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf, ExecutionOptions.from_config(conf, synchronous_export=True))
    assert result.ok and len(result.products) == 3
    replay = SimulationConfig.from_yaml(conf.output_dir / "resolved-config.yaml")
    assert replay.resolution == 2500 and replay.radial_resolution == 2500
    assert (conf.output_dir / "run-provenance.yaml").exists()
    cart = next(p["path"] for p in result.products if p["role"] == "cart")
    polar = next(p["path"] for p in result.products if p["role"] == "polar")
    with xr.open_dataset(cart) as ds:
        np.testing.assert_allclose(ds.wind_speed, 10.)
        assert ds.temperature.attrs["units"] == "K"
        assert ds.x_box_km.attrs["units"] == "km"
    with xr.open_dataset(polar) as ds:
        assert ds.UM10.attrs["units"] == "m s-1"
        np.testing.assert_allclose(ds.wind_speed.where(ds.wind_speed.notnull(), 10), 10.)


@pytest.mark.parametrize("model", ["AROME", "MNH"])
def test_frozen_matrix_yaml_and_mapping_requests_match(tmp_path, model):
    """Exercise both real adapters through strict YAML and mapping boundaries."""
    from importlib import resources

    from frameit.core.runner import FrameitRunner
    from frameit.testing.catalog import load_cases, resolve_case

    root = Path(str(resources.files("frameit.testing").joinpath("ci_dataset")))
    case = next(
        c for c in load_cases() if c["config"]["model"] == {"AROME": "arome", "MNH": "mesonh"}[model] and c["polar"]
        and c["tracker"] == ("fixed_box" if model == "AROME" else "wind_pressure")
    )
    case = resolve_case(case, root, tmp_path / "mapping")
    assert case["preflight"] == "READY", case["reason"]
    # Both replay paths use the same explicit source conventions. This is a
    # configuration-equivalence regression, not scientific validation of them.
    case["config"]["input"]["wind_pairs"] = (
        [{"group": group, "u": "u", "v": "v", "reference_frame": "earth"}
         for group in ("heightAboveGround", "isobaricInhPa")]
        + [{"group": "surface", "u": "u10", "v": "v10", "reference_frame": "earth"}]
        if model == "AROME" else
        [{"group": "level", "u": "UT", "v": "VT", "reference_frame": "grid",
          "rotation": {"method": "geolocation"}},
         {"group": "surface", "u": "UM10", "v": "VM10", "reference_frame": "earth"}]
    )
    mapping = SimulationConfig.from_mapping_with_model_preset(case["config"])
    raw = {**case["config"], "output": {**case["config"]["output"], "directory": str(tmp_path / "yaml")}}
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(raw))
    conf = SimulationConfig.from_yaml(path)
    with FrameitRunner(mapping, input_files=case["input_files"]) as a, FrameitRunner(
        conf, input_files=case["input_files"]
    ) as b:
        a.run()
        b.run()
        xr.testing.assert_allclose(a.track, b.track, rtol=1e-10, atol=1e-10)
        assert set(a.dict_crop_user) == set(b.dict_crop_user)
        for group in a.dict_crop_user:
            xr.testing.assert_allclose(
                a.dict_crop_user[group], b.dict_crop_user[group], rtol=1e-10, atol=1e-10
            )
        for group in a.dict_polar_user:
            xr.testing.assert_allclose(
                a.dict_polar_user[group], b.dict_polar_user[group], rtol=1e-10, atol=1e-10
            )
