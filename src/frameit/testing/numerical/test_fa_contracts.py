"""P1 typed facts, scientific declarations and private protocol admission gates."""

from __future__ import annotations

import copy
import json
import pickle
import subprocess
import sys

import numpy as np
import pytest

from frameit.core.configuration import resolve_schema, resolved_configuration
from frameit.core.settings_class import SimulationConfig
from frameit.io.fa_backend import inspect_fa, request_fa
from frameit.io.fa_contracts import (
    SURFEX_LAYOUT,
    check_expected_source,
    layout_definition,
    native_descriptor,
    resolve_descriptor,
    validate_descriptor,
)
from frameit.io.fa_epygram import typed_metadata
from frameit.io.fa_utils import FaArray, inspect_fa_inputs
from frameit.testing.numerical.test_fa_io import NATIVE, fa_files
from frameit.testing.numerical.test_fa_pipeline import single_fa_document

SOURCE = {"PROGRAM": "AROME", "VERSION": 8, "BUG": 1, "MASDEV": 47, "BUGFIX": 0, "PACK": 0}
DECLARATION = {"units": "K", "kind": "continuous", "temporal_kind": "instantaneous"}


def descriptor(**encoding):
    return native_descriptor(
        "RESEARCH", 63, {"exists": True, "spectral": False, "packing": 0, **encoding}, {},
        {"KTYPTR": -11, "KNLATI": 7, "KNXLON": 9}, {},
        {"reference_time": "2026-01-01T00:00:00", "valid_time": "2026-01-01T01:00:00"})


def test_descriptor_json_unknown_meaning_and_native_fact_precedence():
    raw = descriptor()
    assert json.loads(json.dumps(raw, allow_nan=False)) == raw
    assert raw["units"]["value"] is None
    assert raw["sampling"]["physical_location"] is None
    assert raw["native"]["shape"] == [7, 9]
    assert raw["mask"]["undefined"] == "not_read"
    with pytest.raises(ValueError, match="declare input.fa.field_metadata.RESEARCH"):
        resolve_descriptor(raw, None)
    resolved = resolve_descriptor(raw, DECLARATION)
    assert resolved["units"]["origin"] == "explicit_input.fa.field_metadata"
    assert raw["units"]["value"] is None  # resolution must not mutate native facts
    native = copy.deepcopy(raw)
    native["units"] = {"value": "K", "origin": "native"}
    assert resolve_descriptor(native, DECLARATION)["units"]["origin"] == "native"
    with pytest.raises(ValueError, match="contradicts native/profile"):
        resolve_descriptor(native, {**DECLARATION, "units": "degC"})
    native["temporal_support"].update(kind="accumulated", origin="native")
    with pytest.raises(ValueError, match="contradicts native/profile"):
        resolve_descriptor(native, DECLARATION)
    with pytest.raises(ValueError, match="spectral"):
        resolve_descriptor(descriptor(spectral=True), DECLARATION)
    with pytest.raises(ValueError, match="instantaneous"):
        resolve_descriptor(raw, {**DECLARATION, "temporal_kind": "averaged"})
    with pytest.raises(ValueError, match="schema_version"):
        validate_descriptor({**raw, "schema_version": 2})
    with pytest.raises(ValueError, match="schema_version"):
        validate_descriptor({**raw, "schema_version": True})
    with pytest.raises(ValueError, match="finite JSON"):
        validate_descriptor({**raw, "unexpected_native_handle": object()})
    packed = native_descriptor("RESEARCH", 2, {"exists": True, "spectral": False}, {},
                               {"KTYPTR": -11, "KNLATI": 7, "KNXLON": 9},
                               {**SOURCE, "PACK": 1}, {})
    with pytest.raises(ValueError, match="PACK=0"):
        resolve_descriptor(packed, DECLARATION)


def test_observed_layout_does_not_match_another_or_unidentified_release():
    assert layout_definition(SOURCE) == SURFEX_LAYOUT
    for key in ("PROGRAM", "VERSION", "BUG", "MASDEV", "BUGFIX"):
        altered = dict(SOURCE)
        altered.pop(key)
        assert layout_definition(altered) is None
        with pytest.raises(ValueError, match="conflicts with native"):
            check_expected_source(altered, {key: SOURCE[key]})
    assert layout_definition({**SOURCE, "MASDEV": 49}) is None


def test_raw_vertical_header_survives_without_coordinate_or_field_assumptions():
    header = {"KTYPTR": -11, "KNLATI": 7, "KNXLON": 9, "KNIVER": 2, "PREFER": 100000.,
              "PAHYBR": [0., 100., 200.], "PBHYBR": [0., .4, 1.]}
    raw = native_descriptor("S002RESEARCH", 63, {"exists": True, "spectral": False},
                            {}, header, {}, {})
    resolved = resolve_descriptor(raw, DECLARATION)
    sampling = resolved["sampling"]
    assert sampling["native_vertical_header"] == {
        "KNIVER": 2, "PREFER": 100000., "PAHYBR": [0., 100., 200.], "PBHYBR": [0., .4, 1.]}
    assert sampling["physical_location"] is None and sampling["vector_basis"] is None
    assert sampling["vertical_interpretation"].startswith("unqualified;")
    assert resolved["native"]["shape"] == [7, 9]  # the selected record remains 2-D
    assert resolved["eligibility"]["diagnostic"] == "blocked"
    header["PAHYBR"][1] = -999.
    assert raw["sampling"]["native_vertical_header"]["PAHYBR"][1] == 100.
    assert json.loads(json.dumps(resolved, allow_nan=False)) == resolved


@pytest.mark.parametrize("group, levels", [
    ("level", "all"), ("surface", "physical"), ("surface", {"indices": [0]}),
    ("surface", {"values": [850]}),
])
def test_native_atmospheric_cubes_and_vertical_selectors_remain_gated(tmp_path, group, levels):
    path = tmp_path / "unopened.fa"
    raw = single_fa_document(tmp_path, [path])
    raw["input"]["fa"].update(profile="arome_history",
                             field_metadata={"CLSTEMPERATURE": DECLARATION})
    raw["variables"] = {group: {"names": ["CLSTEMPERATURE"], "levels": levels}}
    message = ("FA 2-D records must be selected in variables.surface" if group == "level"
               else "variables.surface.levels cannot select a vertical axis")
    with pytest.raises(ValueError, match=message):
        SimulationConfig.from_mapping_with_model_preset(raw)
    assert not path.exists() and not (tmp_path / "run").exists()


@pytest.mark.skipif(not NATIVE, reason="optional EPyGrAM FA stack not installed")
def test_typed_words_are_reinterpreted_not_cast_and_unknowns_never_read(tmp_path):
    # Independent raw word truth, including an integer not exactly representable
    # in float64. No native codec round trip is the oracle for these conversions.
    values = {"SFX.LAT0": np.array([0xC034400000000000], dtype="uint64").view("int64"),
              "SFX._FBUF_DIM1": np.array([2**60 + 1, -1], dtype="int64"),
              "SFX.PROGRAM": np.array([65, 82, 79, 77, 69, 32], dtype="int64"),
              "SFX.L1D": np.array([0], dtype="int64"),
              "SFX.L2D": np.array([1], dtype="int64"),
              "SFX.DTCUR": np.array([2026, 1, 1, 0x40AC200000000000], dtype="int64")}
    transactions = 0

    def typed(name, **kwargs):
        nonlocal transactions
        directory = tmp_path / str(transactions)
        directory.mkdir()
        transactions += 1
        entries = [{"name": "T2M", "mask": "FULL"}, {"name": "SST", "mask": "SEA"}]
        path = fa_files(directory, profile="surfex_history", extra_metadata=True,
                        source_bug=kwargs.get("source", SOURCE)["BUG"],
                        surface_fields=[{**entry, "values": np.zeros((7, 9)).tolist()}
                                        for entry in entries],
                        surface_directory=entries,
                        structural_overrides={key: value.tolist() for key, value in values.items()}
                        )[0]
        return inspect_fa(path, None, validate_selection=False, metadata_fields=[name])[
            "typed_metadata"][name]["value"]

    assert typed("SFX.LAT0") == -20.25
    assert typed("SFX._FBUF_DIM1") == [2**60 + 1, -1]
    assert typed("SFX.PROGRAM") == "AROME"
    assert typed("SFX.L1D") is False and typed("SFX.L2D") is True
    assert typed("SFX.DTCUR") == {"date": [2026, 1, 1], "seconds": 3600.}
    class NoRead:
        def __getattr__(self, name):
            raise AssertionError("unqualified typed metadata accessed the library")

    for name in ("SFX.T2M", "SFX.UNKNOWN"):
        with pytest.raises(ValueError, match="release-specific"):
            typed_metadata(NoRead(), name, {name: 1}, SOURCE, {})
    with pytest.raises(ValueError, match="release-specific"):
        typed("SFX.LAT0", source={**SOURCE, "BUG": 2})
    with pytest.raises(ValueError, match="contradicts"):
        typed_metadata(NoRead(), "SFX.LAT0", {"SFX.LAT0": 1}, SOURCE,
                       {"SFX.LAT0": {"TYPE": "N0"}})
    values["SFX.L2D"][0] = -1
    with pytest.raises(ValueError, match="logical word"):
        typed("SFX.L2D")
    values["SFX.PROGRAM"][0] = 256
    with pytest.raises(ValueError, match="Invalid ASCII"):
        typed("SFX.PROGRAM")
    values["SFX.PROGRAM"][0] = 65
    values["SFX.LAT0"][0] = 0x7FF8000000000000
    assert typed("SFX.LAT0") == {"nonfinite": "nan"}
    json.dumps(typed("SFX.LAT0"), allow_nan=False)


def test_expected_source_schema_and_resolved_yaml_compatibility(tmp_path):
    raw = single_fa_document(tmp_path, [tmp_path / "unopened.fa"])
    raw["input"]["grid_spacing_m"] = 1100.
    raw["input"]["fa"]["expected_source"] = {"PROGRAM": "AROME", "MASDEV": 47, "VERSION": 8}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    resolved = resolved_configuration(conf)
    assert resolved["input"]["fa"]["field_metadata"] == raw["input"]["fa"]["field_metadata"]
    restored = SimulationConfig.from_mapping_with_model_preset(resolved)
    assert restored.fa_options == conf.fa_options
    for bad in ({"MASDEV": True}, {"VERSION": "8"}, {"units": "K"}, {"PROGRAM": ""}):
        invalid = copy.deepcopy(raw)
        invalid["input"]["fa"]["expected_source"] = bad
        with pytest.raises(ValueError, match="expected_source"):
            resolve_schema(invalid)


def test_unknown_protocol_rejected_without_opening_source(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unknown protocol must fail before child launch")

    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="protocol_version"):
        request_fa({"protocol_version": 2})
    monkeypatch.setenv("ECCODES_DEFINITION_PATH", "/parent-only/definitions")
    monkeypatch.setenv("ECCODES_SAMPLES_PATH", "/parent-only/samples")

    def mismatched(argv, **kwargs):
        from pathlib import Path

        assert "ECCODES_DEFINITION_PATH" not in kwargs["env"]
        assert "ECCODES_SAMPLES_PATH" not in kwargs["env"]
        assert json.loads(kwargs["input"])["protocol_version"] == 1
        (Path(argv[-1]) / "response.json").write_text(json.dumps({
            "ok": True, "result": {"protocol_version": 2}}))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mismatched)
    with pytest.raises(ValueError, match="response protocol_version"):
        request_fa({"path": "unopened.fa", "operation": "inspect"})


@pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")
def test_native_metadata_only_no_payload_and_serializable_lazy_descriptor(tmp_path):
    path = fa_files(tmp_path, profile="surfex_history", extra_metadata=True)[0]
    before = path.read_bytes()
    # Patch only the disposable child's horizontal reader. Metadata inspection
    # must succeed without invoking it or probing unselected physical fields.
    script = """
import json, sys
from pathlib import Path
from falfilfa4py import FA
def forbidden(*args):
    raise AssertionError('physical payload operation during metadata-only inspection')
FA.wfacilo = forbidden
FA.wfanion = forbidden
from frameit.io.fa_worker import handle
print(json.dumps(handle(json.loads(sys.argv[1]), Path(sys.argv[2])), allow_nan=False))
"""
    result = subprocess.run([sys.executable, "-c", script, json.dumps({
        "operation": "inspect", "path": str(path), "profile": "surfex_history",
        "metadata_fields": ["SFX.LAT0", "SFX.L1D", "SFX.L2D", "SFX.PROGRAM", "SFX._FBUF_DIM1"]
    }), str(tmp_path)], capture_output=True, text=True, timeout=30, check=True)
    info = json.loads(result.stdout)
    assert info["typed_metadata"]["SFX.LAT0"]["value"] == -20.25
    assert info["typed_metadata"]["SFX._FBUF_DIM1"]["value"] == [63]
    assert info["field_descriptors"]["SFX.L2D"]["native"]["decoded_dtype"] == "logical"
    logical = info["field_descriptors"]["SFX.L2D"]
    assert logical["eligibility"]["metadata_decode"] == "available"
    assert logical["eligibility"]["decode"] == "blocked"  # not a physical array
    assert logical["semantic_evidence"][0]["encoding_probe"] == "not_requested"
    assert path.read_bytes() == before
    conf = SimulationConfig.from_mapping_with_model_preset(single_fa_document(tmp_path, [path]))
    info = inspect_fa_inputs(path, conf, ["SFX.T2M"])
    array = FaArray(path, "SFX.T2M", info, conf.fa_options, [0, 9, 0, 7])
    restored = pickle.loads(pickle.dumps(array))
    assert restored.descriptor == json.loads(json.dumps(array.descriptor))
    assert restored.shape == (7, 9)
    conf.fa_options["field_metadata"] = {}
    with pytest.raises(ValueError, match="declare input.fa.field_metadata"):
        inspect_fa_inputs(path, conf, ["SFX.T2M"])
    # The same record remains inspectable with unresolved meaning.
    assert inspect_fa(path, None, ["SFX.T2M"])["field_descriptors"]["SFX.T2M"]["units"][
        "value"] is None
    with pytest.raises(ValueError, match="expected_source.MASDEV"):
        inspect_fa(path, None, expected_source={"MASDEV": 49})
    with pytest.raises(ValueError, match="unsupported SURFEX field"):
        inspect_fa(path, "surfex_history", ["SFX.VERSION"])
    unknown_release = fa_files(tmp_path, (1,), profile="surfex_history", source_bug=2)[0]
    assert inspect_fa(unknown_release, None)["field_directory"]  # inventory is still available
    with pytest.raises(ValueError, match="release-specific typed metadata"):
        inspect_fa(unknown_release, None, metadata_fields=["SFX.VERSION"])
    with pytest.raises(ValueError, match="expected_source.BUG"):
        inspect_fa(unknown_release, None, expected_source={"BUG": 1})


def test_worker_rejects_protocol_before_loading_optional_libraries(tmp_path):
    result = subprocess.run([sys.executable, "-m", "frameit.io.fa_worker", str(tmp_path)],
                            input=json.dumps({"protocol_version": 2}), text=True,
                            capture_output=True, timeout=30)
    assert result.returncode == 0
    assert "Unsupported FA worker protocol_version" in json.loads(
        (tmp_path / "response.json").read_text())["error"]
