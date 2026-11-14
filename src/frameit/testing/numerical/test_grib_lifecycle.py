"""Fresh-process checks: native import order and interpreter shutdown matter."""

import importlib.util
import json
import subprocess
import sys

import pytest

from frameit.testing.datasets import ci_dataset_root


def test_discovering_grib_loader_does_not_initialize_optional_native_decoder():
    run = subprocess.run([sys.executable, "-c", """
import resource, sys
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
import frameit.io.grib_utils
assert 'cfgrib' not in sys.modules and 'eccodes' not in sys.modules
print('loader discovery completed', flush=True)
"""], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "loader discovery completed" in run.stdout


@pytest.mark.skipif(importlib.util.find_spec("cfgrib") is None, reason="Optional GRIB backend")
def test_direct_grib_loading_and_native_shutdown_in_fresh_interpreter(tmp_path):
    source = ci_dataset_root() / "AROME/BATSIRAI"
    run = subprocess.run([sys.executable, "-c", """
import resource, sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
from frameit.io.grib_utils import concat_grib2ds_by_vert_coord
from frameit.io.loader import DatasetResources
with DatasetResources() as owned:
    user, _ = concat_grib2ds_by_vert_coord(
        sorted(Path(sys.argv[1]).glob('*.grib'))[:1],
        {'isobaricInhPa': {'variables': ['u', 'v'], 'level_selection': 'indices',
                           'level_indices': [0]}}, {}, method='fixed_box',
        index_dir=sys.argv[2], resources=owned, filter_requested=True)
    data = user['isobaricInhPa'].load()
    assert data.u.shape == data.v.shape == (1, 1, 81, 81)
    assert data.u.attrs['units'] == 'm s**-1'
    assert data.u.notnull().all() and data.v.notnull().all()
print('native cleanup completed', flush=True)
""", str(source), str(tmp_path / "index")], capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "native cleanup completed" in run.stdout


@pytest.mark.skipif(importlib.util.find_spec("cfgrib") is None, reason="Optional GRIB backend")
def test_matrix_fixture_planning_and_native_shutdown_in_fresh_interpreter(tmp_path):
    output = tmp_path / "plan"
    run = subprocess.run([sys.executable, "-c", """
import resource, sys
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
from frameit.cli import main
main(['run-matrix-test', '--ci', '--plan-only', '--case',
      'arome_batsirai_fixed_cart_only', '--output', sys.argv[1], '--data-root', sys.argv[2]])
""", str(output), str(ci_dataset_root())], capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads((output / "run.json").read_text())
    assert report["exit_code"] == 0
    assert [case["status"] for case in report["results"]] == ["PLANNED"]
    assert len(json.loads((output / "plan.json").read_text())["fixture"]["files"]) == 5


@pytest.mark.parametrize("case", ["selected_messages", "cycles", "cycle_required", "intervals",
                                 "duplicate", "name_ambiguity", "multiple_grids",
                                 "unknown_parameter", "deferred_level_conflict", "subminute",
                                 "ensemble", "derived_level_conflict", "nested_level_conflict",
                                 "internal_requested_level_conflict"])
def test_v3_grib_metadata_locators_without_value_decoding(tmp_path, monkeypatch, case):
    import numpy as np

    from frameit.core.preflight import preflight

    from .test_inspect_metadata import v3_config

    ec = pytest.importorskip("eccodes")
    path = tmp_path / "multi.grib"
    declarations = [(0, 1, 131, 850, -20.), (0, 2, 131, 850, -20.),
                    (0, 3, 131, 850, -20.), (0, 2, 132, 850, -20.)]
    if case in {"cycles", "cycle_required"}:
        declarations += [(600, 2, 131, 850, -20.)]
    if case == "duplicate":
        declarations += [declarations[1]]
    if case == "deferred_level_conflict":
        declarations += [declarations[1], (0, 2, 131, 700, -20.)]
    if case in {"derived_level_conflict", "nested_level_conflict",
                "internal_requested_level_conflict"}:
        declarations += [declarations[1], (0, 2, 131, 700, -20.),
                         (0, 2, 132, 700, -20.)]
        if case == "internal_requested_level_conflict":
            declarations += [(0, 2, 131, 700, -20.)]
    if case == "name_ambiguity":
        declarations += [(0, 2, 131, 700, -20.)]
    if case == "multiple_grids":
        declarations[-1] = (0, 2, 132, 850, -10.)
    if case == "unknown_parameter":
        declarations += [(0, 2, 0, 850, -20.)]
    if case == "subminute":
        declarations = [(0, 0, 131, 850, -20.)]
    if case == "ensemble":
        declarations = [(0, 2, 131, 850, -20.)] * 2
    with path.open("wb") as stream:
        for message_index, (cycle, hour, param, level, latitude) in enumerate(declarations):
            msg = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
            try:
                for key, value in {
                    "Ni": 3, "Nj": 2, "latitudeOfFirstGridPointInDegrees": latitude,
                    "latitudeOfLastGridPointInDegrees": latitude + 1.,
                    "longitudeOfFirstGridPointInDegrees": 60.,
                    "longitudeOfLastGridPointInDegrees": 62., "iDirectionIncrementInDegrees": 1.,
                    "jDirectionIncrementInDegrees": 1., "jScansPositively": 1,
                    "dataDate": 20260101, "dataTime": cycle, "paramId": param,
                    "typeOfLevel": ("isobaricInhPa"
                                    if case != "name_ambiguity" or level == 850 else "hybrid"),
                    "level": level, "forecastTime": hour,
                }.items():
                    if key == "paramId" and value == 0:
                        continue
                    ec.codes_set(msg, key, value)
                if param == 0:
                    for key in ("discipline", "parameterCategory", "parameterNumber"):
                        ec.codes_set(msg, key, 255)
                if case == "subminute":
                    ec.codes_set(msg, "second", 30)
                    ec.codes_set(msg, "stepUnits", "s")
                    ec.codes_set(msg, "forecastTime", 45)
                if case == "ensemble":
                    ec.codes_set(msg, "productDefinitionTemplateNumber", 1)
                    ec.codes_set(msg, "perturbationNumber", message_index)
                    ec.codes_set(msg, "numberOfForecastsInEnsemble", 2)
                if case == "intervals":
                    ec.codes_set(msg, "stepType", "avg")
                    ec.codes_set(msg, "startStep", hour - 1)
                    ec.codes_set(msg, "endStep", hour)
                ec.codes_set_values(msg, np.ones(6))
                ec.codes_write(msg, stream)
            finally:
                ec.codes_release(msg)
    original_array = ec.codes_get_array
    original_get = ec.codes_get

    def forbidden(*args, **kwargs):
        raise AssertionError("Metadata inspection decoded scientific GRIB values")

    def guarded_array(handle, key, *args, **kwargs):
        if key in {"values", "codedValues", "packedValues"}:
            forbidden()
        return original_array(handle, key, *args, **kwargs)

    def guarded_get(handle, key, *args, **kwargs):
        if key in {"values", "codedValues", "packedValues"}:
            forbidden()
        return original_get(handle, key, *args, **kwargs)

    monkeypatch.setattr(ec, "codes_get_values", forbidden)
    monkeypatch.setattr(ec, "codes_get_array", guarded_array)
    monkeypatch.setattr(ec, "codes_get", guarded_get)
    time = {} if case == "cycle_required" else {"values": ["2026-01-01T02:00:00"]}
    if case == "cycles":
        time["cycle"] = "2026-01-01T00:00:00"
    if case == "subminute":
        time = {"values": ["2026-01-01T00:01:15"]}
    field = "avg_u" if case == "intervals" else "u"
    conf = v3_config(tmp_path, [path], names=(field,), model="arome", time=time,
                     variables={"3d": [field]})
    if case == "deferred_level_conflict":
        from copy import deepcopy

        from frameit.core.settings_class import SimulationConfig

        raw = deepcopy(conf.yaml_config)
        raw["sources"]["weather"]["variables"] = {"3d": ["u"], "levels": {"values": [700]}}
        conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if case in {"derived_level_conflict", "nested_level_conflict",
                "internal_requested_level_conflict"}:
        derived = {"speed": {"method": "wind_speed", "inputs": {"u": "u", "v": "v"}}}
        if case == "nested_level_conflict":
            derived["nested"] = {"method": "wind_speed", "inputs": {"u": "speed", "v": "v"}}
        conf = v3_config(tmp_path, [path], model="arome", time=time,
                         variables={"levels": {"values": [700]}}, derived=derived)
    error = {"cycle_required": "time.cycle", "duplicate": "competing.*provider",
             "name_ambiguity": "distinct fields.*u"}.get(case)
    if error:
        with pytest.raises(ValueError, match=error):
            preflight(conf, check_output=False)
        return
    source = preflight(conf, check_output=False)["sources"]["weather"]
    assert source["format"] == "grib" and source["physical_type"] == "atmosphere"
    if case == "subminute":
        assert source["records"][0]["cycle"] == np.datetime64("2026-01-01T00:00:30")
        assert source["records"][0]["time"] == np.datetime64("2026-01-01T00:01:15")
        return
    if case == "ensemble":
        assert len(source["fields"]) == 1
        assert [r["native_axes"]["number"] for r in source["records"]] == [0, 1]
        assert len({r["grid_id"] for r in source["records"]}) == 1
        return
    if case in {"deferred_level_conflict", "derived_level_conflict", "nested_level_conflict",
                "internal_requested_level_conflict"}:
        assert len(source["records"]) == {
            "deferred_level_conflict": 3, "derived_level_conflict": 5,
            "nested_level_conflict": 5, "internal_requested_level_conflict": 6,
        }[case]
        assert len(source["provider_conflicts"]) == (
            2 if case == "internal_requested_level_conflict" else 1)
        conflict = source["provider_conflicts"][0]
        assert conflict["level"] == 850 and conflict["status"] == "pending_level_binding"
        assert len(conflict["locators"]) == 2
        if case == "internal_requested_level_conflict":
            assert source["provider_conflicts"][1]["level"] == 700
        assert len({r["locator"]["message_index"] for r in source["records"]}) == len(
            source["records"])
        assert source["requests"]["binding"] is None
        return
    assert len(source["records"]) == 1
    record = source["records"][0]
    assert record["name"] == field and record["level"] == 850.
    locator = record["locator"]
    assert locator["format"] == "grib" and locator["message_index"] == 1
    assert locator["offset"] > 0 and locator["length"] > 0
    with path.open("rb") as stream:
        stream.seek(locator["offset"])
        raw = stream.read(locator["length"])
    assert raw[:4] == b"GRIB" and raw[-4:] == b"7777"
    assert len(source["native_grids"]) == (2 if case == "multiple_grids" else 1)
    if case == "intervals":
        np.testing.assert_array_equal(record["time_bounds"], np.array(
            ["2026-01-01T01", "2026-01-01T02"], dtype="datetime64[ns]"))
        assert record["temporal_metadata"]["GRIB_stepType"] == "avg"
