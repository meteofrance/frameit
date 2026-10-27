"""C4 old YAML replay, effective implementation and independent output compatibility."""

from __future__ import annotations

import copy
import os
import subprocess
import sys

import numpy as np
import pytest
import yaml

from frameit.core.configuration import resolved_configuration, write_template
from frameit.core.execution import execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_fa_cubes import EPYTHON, NATIVE
from frameit.testing.numerical.test_fa_pipeline import (
    atmospheric_file,
    document,
    single_fa_document,
)


@pytest.mark.parametrize("coupled", [False, True])
@pytest.mark.parametrize("backend", [None, "native", "epygram"])
def test_old_yaml_acceptance_all_settings_and_resolved_replay(tmp_path, caplog, coupled, backend):
    raw = (document(tmp_path, tmp_path / "atmosphere.nc", [tmp_path / "surface.fa"])
           if coupled else single_fa_document(tmp_path, [tmp_path / "surface.fa"]))
    inp = raw["input"]["sources"]["surfex"]["input"] if coupled else raw["input"]
    inp["grid_spacing_m"] = 1100.
    inp["fa"].update(expected_source={"PROGRAM": "AROME", "VERSION": 8, "BUG": 1,
                                       "MASDEV": 47, "BUGFIX": 0},
                     subdomain="C", earth_radius_m=6371229., max_points=6300,
                     timeout_seconds=17., python_executable="./helper/bin/python")
    if backend is not None:
        inp["fa"]["backend"] = backend
    original = copy.deepcopy(raw)
    path = tmp_path / "old.yaml"
    path.write_text(yaml.safe_dump(raw))
    conf = SimulationConfig.from_yaml(path)
    resolved = resolved_configuration(conf)
    replay_path = tmp_path / "resolved.yaml"
    replay_path.write_text(yaml.safe_dump(resolved))
    replay = SimulationConfig.from_yaml(replay_path)
    fa = (replay.input_sources["surfex"]["input"]["fa"] if coupled else replay.fa_options)
    expected = {**inp["fa"], "backend": backend or "epygram", "native_cubes": {},
                "python_executable": str(tmp_path / "helper/bin/python")}
    assert fa == expected
    assert resolved_configuration(replay) == resolved
    assert raw == original and not (tmp_path / "surface.fa").exists()
    assert ("native is deprecated" in caplog.text) == (backend == "native")


def test_init_and_inspect_use_maintained_default_and_report_legacy_alias(
    tmp_path, monkeypatch, capsys,
):
    from frameit.cli import _build_parser, _cmd_inspect

    path = write_template("arome", tmp_path / "init.yaml", full=True)
    assert yaml.safe_load(path.read_text())["input"]["fa"]["backend"] == "epygram"
    source = tmp_path / "unopened.fa"
    source.touch()
    calls = []

    def inspect(path, profile, fields, **options):
        calls.append(options)
        return {"backend_versions": {"FA_backend": "epygram",
                                     "FA_backend_requested": options["backend"]}}

    monkeypatch.setattr("frameit.io.fa_backend.inspect_fa", inspect)
    for backend in (None, "native"):
        args = _build_parser().parse_args([
            "inspect", str(tmp_path), "--model", "arome", "--format", "fa", "--pattern", "*.fa",
            *(["--fa-backend", backend] if backend else [])])
        assert _cmd_inspect(args) == 0
        report = yaml.safe_load(capsys.readouterr().out)["inputs"][0]
        assert report["backend_versions"]["FA_backend"] == "epygram"
        assert calls[-1]["backend"] == (backend or "epygram")
        assert not calls[-1]["validate_selection"]
    args = _build_parser().parse_args([
        "inspect", str(tmp_path), "--model", "arome", "--fa-backend", "epygram"])
    with pytest.raises(ValueError, match="require --format fa"):
        _cmd_inspect(args)


@NATIVE
@pytest.mark.parametrize("coupled", [False, True])
@pytest.mark.parametrize("backend", [None, "native"])
def test_replayed_legacy_or_implicit_backend_exports_independent_values(
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
    inp = raw["input"]["sources"]["surfex"]["input"] if coupled else raw["input"]
    inp["files"] = [p.name for p in paths]
    inp["fa"].update(python_executable=os.path.relpath(EPYTHON, tmp_path), max_points=63,
                     timeout_seconds=30., expected_source={"PROGRAM": "AROME", "MASDEV": 47})
    inp["fa"]["field_metadata"]["SFX.T2M"]["allow_unscaled"] = False
    if backend is not None:
        inp["fa"]["backend"] = backend
    path = tmp_path / "old.yaml"
    path.write_text(yaml.safe_dump(raw))
    original = SimulationConfig.from_yaml(path)
    preflight(original)
    replay = tmp_path / "replay.yaml"
    replay.write_text(yaml.safe_dump(resolved_configuration(original)))
    conf = SimulationConfig.from_yaml(replay)
    result = execute_simulation(conf)
    assert result.ok, result.error
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    source = provenance["sources"]["surfex"] if coupled else provenance
    facts = source["fa_inputs"][0]
    assert facts["backend"] == facts["backend_versions"]["FA_backend"] == "epygram"
    assert facts["requested_backend"] == (backend or "epygram")
    assert facts["backend_versions"]["FA_backend_requested"] == (backend or "epygram")
    assert bool(facts["backend_versions"]["FA_backend_migration"]) == (backend == "native")
    assert all(observation["library"] == "EPyGrAM" for fields in
               source["fa_decoder"]["payload_reads"].values() for observation in fields.values())
    product = next(p["path"] for p in result.products if p["role"] == "cart"
                   and (not coupled or p["group"] == "surfex.surface"))
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
    saved_input = saved["input"]["sources"]["surfex"]["input"] if coupled else saved["input"]
    assert saved_input["fa"]["backend"] == (backend or "epygram")
    assert saved_input["fa"]["field_metadata"] == inp["fa"]["field_metadata"]
