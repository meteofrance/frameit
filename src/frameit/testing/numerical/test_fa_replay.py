"""Current YAML replay, effective implementation and independent output compatibility."""

from __future__ import annotations

import copy
import os
import subprocess
import sys

import numpy as np
import pytest
import yaml

from frameit.core.configuration import resolved_configuration, source_document, write_template
from frameit.core.execution import execute_simulation
from frameit.core.preflight import collect_preflight
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_fa_cubes import EPYTHON, NATIVE
from frameit.testing.numerical.test_fa_pipeline import (
    atmospheric_file,
    document,
    single_fa_document,
)


@pytest.mark.parametrize("coupled", [False, True])
@pytest.mark.parametrize("backend", [None, "epygram"])
def test_current_yaml_all_settings_and_resolved_replay(tmp_path, coupled, backend):
    raw = (document(tmp_path, tmp_path / "atmosphere.nc", [tmp_path / "surface.fa"])
           if coupled else single_fa_document(tmp_path, [tmp_path / "surface.fa"]))
    inp = raw["sources"]["surface"]
    inp["fa"] = {"expected_source": {"PROGRAM": "AROME", "VERSION": 8, "BUG": 1,
                                    "MASDEV": 47, "BUGFIX": 0},
                 "subdomain": "C", "earth_radius_m": 6371229.}
    inp["reader"] = {"max_points": 6300, "timeout_seconds": 17.,
                     "python_executable": "./helper/bin/python"}
    original = copy.deepcopy(raw)
    path = tmp_path / "current.yaml"
    path.write_text(yaml.safe_dump(raw))
    conf = SimulationConfig.from_yaml(path)
    resolved = resolved_configuration(conf)
    replay_path = tmp_path / "resolved.yaml"
    replay_path.write_text(yaml.safe_dump(resolved))
    replay = SimulationConfig.from_yaml(replay_path)
    fa = (SimulationConfig.from_mapping_with_model_preset(
        source_document(replay.yaml_config, "surface")).fa_options if coupled else replay.fa_options)
    expected = {**inp["fa"], **inp["reader"], "profile": inp["profile"],
                "field_metadata": inp["field_metadata"],
                "backend": backend or "epygram", "native_cubes": {},
                "python_executable": str(tmp_path / "helper/bin/python")}
    assert fa == expected
    assert resolved_configuration(replay) == resolved
    assert raw == original and not (tmp_path / "surface.fa").exists()


def test_init_is_backend_free_and_explicit_fa_uses_maintained_default(tmp_path):
    path = write_template("arome", tmp_path / "init.yaml")
    assert SimulationConfig.from_yaml(path).fa_options == {}
    source = tmp_path / "unopened.fa"
    request = single_fa_document(tmp_path, [source])
    assert SimulationConfig.from_mapping_with_model_preset(request).fa_options["backend"] == (
        "epygram")
    assert not source.exists()
    request["sources"]["surface"]["format"] = "netcdf"
    request["sources"]["surface"]["reader"] = {"python_executable": sys.executable}
    path.write_text(yaml.safe_dump(request))
    with pytest.raises(ValueError, match="reader.python_executable.*FA-only"):
        SimulationConfig.from_yaml(path)


@NATIVE
@pytest.mark.parametrize("coupled", [False, True])
@pytest.mark.parametrize("backend", [None, "epygram"])
def test_replayed_current_or_implicit_backend_exports_independent_values(
    tmp_path, coupled, backend,
):
    from frameit.testing.numerical.test_fa_io import fa_files

    j, i = np.indices((7, 9))
    truth = (280. + 10*j + i).astype(float)
    truth[2, 3], truth[3, 4] = np.nan, 0.
    paths = fa_files(tmp_path, (0, 1), profile="surfex_history", field_values=truth.tolist())
    for path in paths:
        path.chmod(0o444)
    before = [p.read_bytes() for p in paths]
    raw = (document(tmp_path, atmospheric_file(tmp_path), paths) if coupled
           else single_fa_document(tmp_path, paths))
    inp = raw["sources"]["surface"]
    inp["files"] = [p.name for p in paths]
    inp["reader"] = {"python_executable": os.path.relpath(EPYTHON, tmp_path),
                     "max_points": 63, "timeout_seconds": 30.}
    inp["fa"] = {"expected_source": {"PROGRAM": "AROME", "MASDEV": 47}}
    inp["field_metadata"]["SFX.T2M"]["allow_unscaled"] = False
    path = tmp_path / "current.yaml"
    path.write_text(yaml.safe_dump(raw))
    original = SimulationConfig.from_yaml(path)
    checked = collect_preflight(original)
    assert not checked.errors, checked.errors
    replay = tmp_path / "replay.yaml"
    replay.write_text(yaml.safe_dump(resolved_configuration(original)))
    conf = SimulationConfig.from_yaml(replay)
    result = execute_simulation(conf)
    assert result.ok, result.error
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    source = provenance["sources"]["surface"]
    effective = SimulationConfig.from_mapping_with_model_preset(
        source_document(conf.yaml_config, "surface")).fa_options
    facts = source["fa_decoder"]
    assert effective["backend"] == facts["backend_versions"]["FA_backend"] == "epygram"
    assert effective["backend"] == (backend or "epygram")
    assert facts["backend_versions"]["FA_backend_requested"] == (backend or "epygram")
    assert not facts["backend_versions"]["FA_backend_migration"]
    assert all(observation["library"] == "EPyGrAM" for fields in
               source["fa_decoder"]["payload_reads"].values() for observation in fields.values())
    product = next(p["path"] for p in result.products if p["role"] == "model_grid"
                    and p["source"] == "surface")
    reader = subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1], engine='netcdf4') as d:
    j, i = np.indices((7, 9))
    truth = (280. + 10*j + i).astype(float)
    truth[2, 3], truth[3, 4] = np.nan, 0.
    expected = np.stack([truth, truth + .5])[:, 1:6, 2:7]
    np.testing.assert_array_equal(d['SFX.T2M'], expected)
    assert d['SFX.T2M'].attrs['units'] == 'K'
    assert d['SFX.T2M'].attrs['source_variable_name'] == 'SFX.T2M'
    np.testing.assert_array_equal(d.source_i, [[2, 3, 4, 5, 6]]*2)
    np.testing.assert_array_equal(d.source_j, [[1, 2, 3, 4, 5]]*2)
assert not {'frameit', 'epygram', 'falfilfa4py'} & sys.modules.keys()
""", str(product)], capture_output=True, text=True, timeout=30)
    assert reader.returncode == 0, reader.stdout + reader.stderr
    assert [p.read_bytes() for p in paths] == before
    saved = yaml.safe_load((conf.output_dir / "resolved-config.yaml").read_text())
    saved_input = saved["sources"]["surface"]
    assert SimulationConfig.from_mapping_with_model_preset(source_document(
        saved, "surface")).fa_options["backend"] == (backend or "epygram")
    assert saved_input["field_metadata"] == inp["field_metadata"]
