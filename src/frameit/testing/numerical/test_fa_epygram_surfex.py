"""C1 production SURFEX admission; independent words/values, never a reader oracle."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from frameit.core.configuration import resolved_configuration
from frameit.core.settings_class import SimulationConfig
from frameit.io.fa_backend import inspect_fa, request_fa
from frameit.io.fa_epygram import read_values, structure_value
from frameit.testing.numerical.test_fa_cubes import EPYTHON, NATIVE
from frameit.testing.numerical.test_fa_pipeline import single_fa_document

OPTIONS = {"backend": "epygram", "python_executable": EPYTHON}


def surface_fixture(directory, **options):
    path = directory / "surface.fa"
    j, i = np.indices((7, 9))
    truth = (280. + 10*j + i).astype(float)
    truth[1, 1], truth[2, 2] = np.nan, 0.
    written = subprocess.run([EPYTHON, "-m", "frameit.testing.fa_fixture"], input=json.dumps([{
        "path": str(path), "profile": "surfex_history", "hours": 1,
        "extra_metadata": True, "surface_fields": [
            {"name": "SST", "mask": "SEA", "values": (truth + 1).tolist()},
            {"name": "T2M", "mask": "FULL", "values": truth.tolist()}], **options,
    }]), capture_output=True, text=True, timeout=30)
    assert written.returncode == 0, written.stdout + written.stderr
    path.chmod(0o444)
    return path, truth


def test_surfex_schema_replay_and_actual_library_type_guards(tmp_path):
    raw = single_fa_document(tmp_path, [tmp_path / "unopened.fa"])
    raw["input"]["grid_spacing_m"] = 1100.
    raw["input"]["fa"].update(OPTIONS)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    restored = SimulationConfig.from_mapping_with_model_preset(resolved_configuration(conf))
    assert restored.fa_options == conf.fa_options
    assert restored.fa_options["profile"] == "surfex_history"
    assert not (tmp_path / "unopened.fa").exists()
    data = np.ma.array([[0., 5.], [7., 8.]], mask=[[False, True], [False, False]])
    field = SimpleNamespace(structure="H2D", spectral=False, getdata=lambda: data)
    resource = SimpleNamespace(_readH2DField=lambda *args, **kwargs: field)
    actual, undefined = read_values(resource, "SFX.T2M", (2, 2))
    np.testing.assert_array_equal(actual, [[0., np.nan], [7., 8.]])
    assert undefined
    with pytest.raises(ValueError, match="decoded shape contradicts"):
        read_values(resource, "SFX.T2M", (1, 4))
    field.spectral = True
    with pytest.raises(ValueError, match="coefficients/metadata"):
        read_values(resource, "SFX.T2M", (2, 2))
    # Reject casts/shape guesses when an API/table disagrees with actual bytes.
    for wrong in (np.array(8., dtype="float64"), np.array([8, 9], dtype="int64")):
        misc = SimpleNamespace(getdata=lambda wrong=wrong: wrong)
        resource._readMiscField = lambda *args, misc=misc, **kwargs: misc
        with pytest.raises(ValueError, match="actual library type/shape"):
            structure_value(resource, "SFX.VERSION", {"SFX.VERSION": 1}, "integer", 1)


def test_unqualified_dependency_versions_fail_before_native_import(tmp_path, monkeypatch):
    from frameit.io import fa_epygram

    versions = {"epygram": "2.1.0", "falfilfa4py": "1.3.0", "ctypesForFortran": "1.3.0",
                "ectrans4py": "1.6.0", "netCDF4": "1.7.2"}
    monkeypatch.setattr(fa_epygram, "version", versions.__getitem__)
    with pytest.raises(ValueError, match="falfilfa4py==1.2.1"):
        fa_epygram.initialize(tmp_path, None)
    versions.update(falfilfa4py="1.2.1", ctypesForFortran="2.2.1")
    with pytest.raises(ValueError, match="ctypesForFortran==1.3.0"):
        fa_epygram.initialize(tmp_path, None)
    assert "epygram" not in sys.modules and not (tmp_path / ".epygram").exists()


@pytest.mark.skipif(importlib.util.find_spec("epygram") is not None,
                    reason="requires an interpreter without the optional EPyGrAM stack")
def test_absent_epygram_dependency_is_actionable_for_surfex(tmp_path):
    # Runs in reference and core-only CI. Do not select an available helper: this
    # explicitly tests the current interpreter's genuinely missing dependency.
    with pytest.raises(ValueError, match=r"install FrameIt\[fa-epygram\]"):
        inspect_fa(tmp_path / "unopened.fa", "surfex_history", backend="epygram")


# Instrument the *production* worker in a disposable FA-only interpreter. This
# fails if the old raw prepass, a physical raw-word fallback or any unselected
# physical read is used, and counts one native open/close even on selected errors.
WORKER_CHECK = """
import json, sys
from collections import Counter
from pathlib import Path
from falfilfa4py import FA, LFI
from frameit.io import fa_epygram, fa_worker
request, destination, injected_error = json.loads(sys.argv[1])
destination = Path(destination)
epygram = fa_epygram.initialize(destination, request.get('earth_radius_m'))
fa_epygram.initialize = lambda *args: epygram
calls, decoded, structural, epygram_payloads = Counter(), [], [], []
h2d = epygram.formats.FA.FA._readH2DField
def library_field(self, name, getdata=True, **kwargs):
    if getdata:
        epygram_payloads.append(name)
    return h2d(self, name, getdata=getdata, **kwargs)
epygram.formats.FA.FA._readH2DField = library_field
for name in ('wfaitou', 'wfairme', 'wfacies', 'wfadiex', 'wfanion'):
    original = getattr(FA, name)
    def counted(*args, name=name, original=original):
        calls[name] += 1
        if injected_error == 'geometry' and name == 'wfacies':
            raise RuntimeError('injected geometry failure')
        result = original(*args)
        if injected_error == 'storage' and name == 'wfacies' and calls[name] == 2:
            result = list(result)
            result[6], result[7] = result[7], result[6]  # same point count, different storage axes
        if injected_error == 'clock' and name == 'wfadiex':
            result[13] = 3600  # inconsistent raw reference hour/seconds
        return result
    setattr(FA, name, counted)
physical = FA.wfacilo
def selected(*args):
    assert request['operation'] == 'read', 'metadata inspection decoded physical data'
    name = args[2] + args[4]
    assert name == 'SFX.T2M', 'unselected physical decode'
    decoded.append(name)
    return physical(*args)
FA.wfacilo = selected
misc = FA.wfalais
def structural_only(unit, name, length):
    assert name not in ('SFX.T2M', 'SFX.SST'), 'physical failure hidden as metadata'
    structural.append(name)
    return misc(unit, name, length)
FA.wfalais = structural_only
raw = LFI.wlfilec
def narrow_words(unit, name, length, abort):
    assert name in ('SFX.PACK', 'SFX.DTCUR', 'SFX.L1D', 'SFX.L2D'), name
    return raw(unit, name, length, abort)
LFI.wlfilec = narrow_words
def forbidden(*args, **kwargs):
    raise AssertionError('legacy raw-reader prepass/alternate physical decoder used')
FA.wfacile = fa_worker._inspect = forbidden
if injected_error and injected_error not in ('geometry', 'clock', 'storage'):
    fanion = FA.wfanion
    def failure(unit, prefix, level, suffix):
        if prefix + suffix == 'SFX.T2M':
            raise RuntimeError('Error code %s was raised.' % (
                -91 if injected_error == 'late' else injected_error))
        return fanion(unit, prefix, level, suffix)
    if injected_error == 'late':
        read_values = fa_epygram.read_values
        def late_failure(*args):
            FA.wfanion = failure
            return read_values(*args)
        fa_epygram.read_values = late_failure
    else:
        FA.wfanion = failure
try:
    info = fa_worker.handle(request, destination)
except Exception as exc:
    if injected_error == 'geometry':
        assert 'injected geometry failure' in str(exc), str(exc)
    elif injected_error == 'clock':
        assert 'inconsistent FA forecast reference date' in str(exc), str(exc)
    elif injected_error == 'storage':
        assert 'sampling/storage contradicts' in str(exc), str(exc)
    elif injected_error == 'late':
        assert 'Field is not H2D' in str(exc), str(exc)
    else:
        assert injected_error and 'unsupported native encoding' in str(exc), str(exc)
        assert str(injected_error) in str(exc) and 'not metadata fallback' in str(exc)
    info = {'selected_error': str(exc)}
assert calls['wfaitou'] == calls['wfairme'] == 1, calls
assert not {'eccodes', 'cfgrib', 'ectrans4py', 'epygram.formats.GRIB'} & sys.modules.keys()
print('C1_RESULT=' + json.dumps({'info': info, 'calls': dict(calls),
                                'decoded': decoded, 'structural': structural,
                                'epygram_payloads': epygram_payloads}, allow_nan=False))
"""


@NATIVE
@pytest.mark.parametrize("operation", ["inspect", "read"])
@pytest.mark.parametrize("projected", [False, True])
def test_one_resource_library_structure_and_selected_payload(tmp_path, operation, projected):
    options = {"projection_latitude": -20.} if projected else {}
    # An unselected unsupported typed record must not be physically probed/read.
    options["surface_directory"] = [
        {"name": "T2M", "mask": "FULL"}, {"name": "SST", "mask": "SEA", "type": "L1"}]
    path, truth = surface_fixture(tmp_path, **options)
    before = path.read_bytes()
    request = {"operation": operation, "path": str(path), "profile": "surfex_history",
               "fields": ["SFX.T2M"], "backend": "epygram", "earth_radius_m": 6371229.,
               "geometry_options": {"subdomain": "CI", "earth_radius_m": 6371229.,
                                    "max_points": 63},
               "metadata_fields": ["SFX.PROGRAM", "SFX.VERSION", "SFX.LAT0", "SFX.PACK",
                                   "SFX.L1D", "SFX.L2D", "SFX.DTCUR", "SFX._FBUF_DIM1"],
               "zone": [1, 8, 1, 6], "key": [[None, None, -2], [None, None, -3]]}
    result = subprocess.run([EPYTHON, "-c", WORKER_CHECK,
                             json.dumps([request, str(tmp_path), None])],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.split("C1_RESULT=")[1])
    info = report["info"]
    assert info["backend_versions"]["FA_backend"] == "epygram"
    assert info["backend_versions"]["falfilfa4py"] == "1.2.1"
    assert "SFX._FBUF_NAME" in report["structural"]  # library, not raw directory decode
    # Original admission/corner/normalization and clock observations remain narrow.
    assert report["calls"]["wfacies"] == report["calls"]["wfadiex"] == 2
    assert report["calls"]["wfanion"] == (2 if operation == "inspect" else 3)
    if operation == "inspect":
        assert info["geometry"]["epygram"]["native_shape"] == [7, 9]
        assert report["decoded"] == []
        assert report["epygram_payloads"] == [] and "payload_read" not in info
        assert info["reference_time"] == "2026-01-01T00:00:00"
        assert info["valid_time"] == info["surfex_metadata"]["STATE_TIME"] == "2026-01-01T01:00:00"
        typed = info["typed_metadata"]
        expected = {"SFX.PROGRAM": "AROME", "SFX.VERSION": 8, "SFX.LAT0": -20.25,
                    "SFX.PACK": False, "SFX.L1D": False, "SFX.L2D": True,
                    "SFX.DTCUR": {"date": [2026, 1, 1], "seconds": 3600.},
                    "SFX._FBUF_DIM1": [63, 63]}
        assert {name: item["value"] for name, item in typed.items()} == expected
        assert list(info["field_directory"]) == ["SFX.T2M", "SFX.SST"]
    else:
        assert report["decoded"] == ["SFX.T2M"]
        assert report["epygram_payloads"] == ["SFX.T2M"]
        assert info["payload_read"] == {
            "library": "EPyGrAM", "resource_class": "epygram.formats.FA.FA",
            "accessor": "_readH2DField(getdata=True)", "openmode": "r"}
        np.testing.assert_array_equal(np.load(tmp_path / "values.npy"), truth[5:0:-2, 7:0:-3])
        mask = info["field_descriptors"]["SFX.T2M"]["mask"]
        assert mask["nonfinite_count"] == 1 and mask["support_map"] is None
    assert path.read_bytes() == before


@NATIVE
@pytest.mark.parametrize("code", [-91, -93, -94])
def test_selected_native_failure_never_reaches_library_metadata_fallback(tmp_path, code):
    path, _truth = surface_fixture(tmp_path)
    request = {"operation": "inspect", "path": str(path), "profile": "surfex_history",
               "fields": ["SFX.T2M"], "backend": "epygram"}
    result = subprocess.run([EPYTHON, "-c", WORKER_CHECK,
                             json.dumps([request, str(tmp_path), code])],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.split("C1_RESULT=")[1])
    assert report["decoded"] == [] and "selected_error" in report["info"]


@NATIVE
def test_later_physical_failure_also_cannot_dispatch_to_misc_reader(tmp_path):
    path, _truth = surface_fixture(tmp_path)
    request = {"operation": "read", "path": str(path), "profile": "surfex_history",
               "fields": ["SFX.T2M"], "backend": "epygram", "zone": [0, 9, 0, 7], "key": [2, 2]}
    result = subprocess.run([EPYTHON, "-c", WORKER_CHECK,
                             json.dumps([request, str(tmp_path), "late"])],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.split("C1_RESULT=")[1])
    assert report["decoded"] == [] and "selected_error" in report["info"]


@NATIVE
@pytest.mark.parametrize("failure", ["geometry", "clock", "storage"])
def test_open_or_header_failure_closes_the_single_owned_resource(tmp_path, failure):
    path, _truth = surface_fixture(tmp_path)
    request = {"operation": "inspect", "path": str(path), "profile": "surfex_history",
               "fields": ["SFX.T2M"], "backend": "epygram"}
    result = subprocess.run([EPYTHON, "-c", WORKER_CHECK,
                             json.dumps([request, str(tmp_path), failure])],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.split("C1_RESULT=")[1])
    assert report["decoded"] == [] and "selected_error" in report["info"]


@NATIVE
@pytest.mark.parametrize("changes, message", [
    ({"SFX.PACK": [-1]}, "unsupported logical word"),
    ({"SFX.VERSION": [8, 1]}, "inconsistent typed metadata length"),
    ({"SFX.DTCUR": [2026, 1, 1]}, "inconsistent typed metadata length"),
    ({"SFX.DTCUR": [2026, 1, 1, 0x7FF8000000000000]}, "nonfinite state timestamp"),
    ({"SFX.DTCUR": None}, "Incomplete SURFEX source"),
    ({"SFX.IMAX": [8]}, "CI dimensions"),
    ({"SFX._FBUF_DIM2": [-1]}, "inconsistent typed metadata length"),
    ({"SFX._FBUF_SIZE": [3126]}, "metadata budget"),
    ({"SFX.PROGRAM": [256]}, "ASCII"),
])
def test_malformed_structure_fails_before_physical_payload(tmp_path, changes, message):
    path, _truth = surface_fixture(tmp_path, structural_overrides=changes)
    with pytest.raises(ValueError, match=message):
        inspect_fa(path, "surfex_history", ["SFX.T2M"], **OPTIONS)


@NATIVE
def test_clock_release_directory_and_full_native_budget_guards(tmp_path):
    path, _truth = surface_fixture(tmp_path, state_hours=2, source_bug=2)
    report = inspect_fa(path, None, ["SFX.T2M"], validate_selection=False, **OPTIONS)
    descriptor = report["field_descriptors"]["SFX.T2M"]
    assert descriptor["eligibility"]["decode"] == "blocked"
    assert report["surfex_metadata"]["STATE_TIME_MATCHES_HEADER"] is False
    with pytest.raises(ValueError, match="DTCUR conflicts"):
        inspect_fa(path, "surfex_history", ["SFX.T2M"], **OPTIONS)
    with pytest.raises(ValueError, match="release-specific"):
        inspect_fa(path, None, validate_selection=False, metadata_fields=["SFX.VERSION"], **OPTIONS)
    with pytest.raises(ValueError, match="expected_source.BUG"):
        inspect_fa(path, None, validate_selection=False, expected_source={"BUG": 1}, **OPTIONS)
    request = {"operation": "read", "path": str(path), "profile": "surfex_history",
               "fields": ["SFX.T2M"], "identity": [0, 0], "zone": [0, 9, 0, 7], "key": [0, 0],
               **OPTIONS}
    with pytest.raises(ValueError, match="changed since inventory"):
        request_fa(request)
    other = tmp_path / "valid"
    other.mkdir()
    path, _truth = surface_fixture(other)
    request.update(path=str(path), identity=None, max_points=62)
    with pytest.raises(ValueError, match="max_points resource budget"):
        request_fa(request)
    # Logical metadata cannot be selected as physical X1, regardless of tables.
    with pytest.raises(ValueError, match="unsupported SURFEX field type/dimensions"):
        inspect_fa(path, "surfex_history", ["SFX.L2D"], **OPTIONS)


@NATIVE
@pytest.mark.parametrize("directory, message", [
    ([{"name": "T2M", "mask": "FULL"}] * 2, "duplicate SURFEX directory"),
    ([{"name": "ABSENT", "mask": "FULL"}], "references absent records"),
])
def test_directory_identity_is_checked_against_library_inventory(tmp_path, directory, message):
    path, _truth = surface_fixture(tmp_path, surface_directory=directory)
    with pytest.raises(ValueError, match=message):
        inspect_fa(path, None, **OPTIONS)


@NATIVE
def test_integer_directory_words_preserve_non_float64_representable_values(tmp_path):
    path, _truth = surface_fixture(tmp_path, structural_overrides={
        "SFX._FBUF_DIM1": [2**60 + 1, 63]})
    info = inspect_fa(path, None, metadata_fields=["SFX._FBUF_DIM1"], **OPTIONS)
    assert info["typed_metadata"]["SFX._FBUF_DIM1"]["value"] == [2**60 + 1, 63]
    assert info["field_directory"]["SFX.SST"]["DIM1"] == 2**60 + 1
    with pytest.raises(ValueError, match="unsupported SURFEX field type/dimensions"):
        inspect_fa(path, "surfex_history", ["SFX.SST"], **OPTIONS)


@NATIVE
def test_ci_dimensions_are_not_mistaken_for_dense_storage_size(tmp_path):
    path, truth = surface_fixture(tmp_path, projection_latitude=-20., ci_bounds=[1, 8, 1, 6])
    info = inspect_fa(path, "surfex_history", ["SFX.T2M"], earth_radius_m=6371229., **OPTIONS)
    assert info["surfex_metadata"]["DIM_FULL"] == 35
    assert info["field_directory"]["SFX.T2M"]["DIM1"] == 63
    assert [info["geometry"][key] for key in ("KNLATI", "KNXLON")] == [7, 9]
    request = {"operation": "read", "path": str(path), "profile": "surfex_history",
               "fields": ["SFX.T2M"], "zone": [1, 8, 1, 6], "key": [[None]*3, [None]*3],
               "earth_radius_m": 6371229., **OPTIONS}
    result = request_fa(request)
    np.testing.assert_array_equal(result["values"], truth[1:6, 1:8])
    with pytest.raises(ValueError, match="max_points resource budget"):
        request_fa({**request, "max_points": 62})


@NATIVE
def test_unmatched_release_is_inventory_only_not_automatic_table_admission(tmp_path):
    path, _truth = surface_fixture(tmp_path, source_bug=2)
    assert inspect_fa(path, None, **OPTIONS)["field_directory"]
    with pytest.raises(ValueError, match="evidenced AROME-47 SURFEX-8.1 layout"):
        inspect_fa(path, "surfex_history", ["SFX.T2M"], **OPTIONS)


@NATIVE
def test_selected_non_fa_physical_words_do_not_become_dense_values(tmp_path):
    # A lying X1 directory cannot turn raw integer metadata into physical data.
    path, _truth = surface_fixture(tmp_path, structural_overrides={"SFX.T2M": [1, 2, 3]})
    assert inspect_fa(path, "surfex_history", ["SFX.SST"], **OPTIONS)["fields"]["SFX.SST"]
    with pytest.raises(ValueError, match="unsupported native encoding"):
        inspect_fa(path, "surfex_history", ["SFX.T2M"], **OPTIONS)


@NATIVE
def test_parent_grib_and_epygram_surface_remain_isolated(tmp_path):
    ec = pytest.importorskip("eccodes")
    message = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    ec.codes_release(message)
    path, truth = surface_fixture(tmp_path)
    request = {"operation": "read", "path": str(path), "profile": "surfex_history",
               "fields": ["SFX.T2M"], "zone": [0, 9, 0, 7], "key": [[None]*3, [None]*3],
               **OPTIONS}
    result = request_fa(request)
    np.testing.assert_array_equal(result["values"], truth)
    assert result["backend_versions"]["FA_backend"] == "epygram"
    assert result["backend_versions"]["EPyGrAM"] == "2.1.0"
    assert not {"epygram", "falfilfa4py"} & sys.modules.keys()
    message = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    ec.codes_release(message)
    invalid = copy.deepcopy(request)
    invalid["python_executable"] = str(tmp_path / "missing-helper")
    with pytest.raises(ValueError, match="Cannot launch the FA helper"):
        request_fa(invalid)


@NATIVE
def test_native_scaling_warning_is_fatal_and_explicit_opt_in_is_recorded(tmp_path):
    path, _truth = surface_fixture(tmp_path, packing=120)
    info = inspect_fa(path, "surfex_history", ["SFX.T2M"], **OPTIONS)
    assert info["surfex_metadata"]["PACK"] == 0 and info["fields"]["SFX.T2M"]["packing"] == 120
    request = {"operation": "read", "path": str(path), "profile": "surfex_history",
               "fields": ["SFX.T2M"], "zone": [0, 9, 0, 7], "key": [[1, 3, None], [1, 3, None]],
               "diagnostics_path": str(tmp_path / "decoder.jsonl"), **OPTIONS}
    with pytest.raises(ValueError, match="missing native scaling metadata"):
        request_fa(request)
    # Engineering fallback semantics only: this is not proof of producer scaling.
    result = request_fa({**request, "allow_unscaled": True})
    assert np.isnan(result["values"][0, 0]) and result["values"][1, 1] == 0.
    scaling = result["field_descriptors"]["SFX.T2M"]["scaling"]
    assert scaling["status"] == "missing" and scaling["fallback"] == "identity_explicit_opt_in"
    assert scaling["multiplier"] is None
    assert result["field_descriptors"]["SFX.T2M"]["mask"]["undefined"]["origin"] == (
        "EPyGrAM_returned_mask")
    assert result["field_descriptors"]["SFX.T2M"]["mask"]["nonfinite_count"] == 1
    logs = [json.loads(line) for line in (tmp_path / "decoder.jsonl").read_text().splitlines()]
    assert len(logs) == 2
    assert logs[0]["field_descriptors"]["SFX.T2M"]["scaling"]["fallback"] is None
    assert all(item["backend_versions"]["FA_backend"] == "epygram" for item in logs)
