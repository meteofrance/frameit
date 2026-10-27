"""P3 dense SURFEX selection preserves supports, undefined values and native IDs."""

from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest
import yaml

from frameit.core.execution import execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.io.fa_backend import inspect_fa
from frameit.io.fa_utils import concat_fa2ds_by_vert_coord
from frameit.testing.numerical.test_fa_cubes import EPYTHON
from frameit.testing.numerical.test_fa_cubes import NATIVE as EPYGRAM
from frameit.testing.numerical.test_fa_io import NATIVE, fa_files
from frameit.testing.numerical.test_fa_pipeline import single_fa_document

pytestmark = pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")


@pytest.fixture(params=["native", pytest.param("epygram", marks=EPYGRAM)])
def backend_options(request):
    return {"backend": request.param,
            "python_executable": EPYTHON if request.param == "epygram" else None}


def test_dense_directory_order_single_native_layer_masks_and_zero(
    tmp_path, monkeypatch, backend_options,
):
    y, x = np.indices((7, 9))
    moisture = (x + 10 * y).astype(float) / 1000.
    moisture[2, 3] = np.nan
    fields = [
        {"name": "TG2P1", "mask": "NATURE", "values": (290. + y + x).tolist()},
        {"name": "WG1P1", "mask": "NATURE", "values": moisture.tolist()},
        {"name": "SST", "mask": "SEA", "values": (300. + x * .01 + 0*y).tolist()},
    ]
    path = fa_files(tmp_path, profile="surfex_history", surface_fields=fields)[0]
    path.chmod(0o444)
    before = path.read_bytes()
    info = inspect_fa(path, None, **backend_options)
    assert list(info["field_directory"]) == ["SFX.TG2P1", "SFX.WG1P1", "SFX.SST"]
    raw = single_fa_document(tmp_path, [path])
    raw["input"]["fa"].update(backend_options)
    raw["variables"] = {"surface": {"names": ["SFX.WG1P1"]}}
    raw["input"]["fa"]["field_metadata"] = {"SFX.WG1P1": {
        "units": "m3 m-3", "kind": "continuous", "temporal_kind": "instantaneous"}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    from frameit.io import fa_utils

    native = fa_utils.request_fa
    calls = []

    def counted(request):
        calls.append(request["fields"])
        return native(request)

    monkeypatch.setattr(fa_utils, "request_fa", counted)
    user, _ = concat_fa2ds_by_vert_coord([path], conf.requests_user(),
                                        conf.requests_tracker(), method="fixed_box", wind_conf=conf)
    assert calls == []
    data = user["surface"]
    assert set(data.data_vars) == {"SFX.WG1P1"}
    actual = data["SFX.WG1P1"].compute()
    np.testing.assert_array_equal(actual[0], moisture)
    assert float(actual[0, 0, 0]) == 0.  # valid zero is not absent NATURE support
    assert np.isnan(actual[0, 2, 3])
    assert calls == [["SFX.WG1P1"]]
    assert actual.attrs["surfex_support_mask"] == "NATURE"
    assert actual.dims == ("time", "y", "x")  # no invented soil-depth/patch coordinate
    # Independent point/strided truth on the dense layout, not a packed support
    # map or an oracle made by slicing the reader's own full result.
    selected = fa_utils.inspect_fa_inputs(path, conf, ["SFX.WG1P1"])
    array = fa_utils.FaArray(path, "SFX.WG1P1", selected, conf.fa_options, [0, 9, 0, 7])
    np.testing.assert_array_equal(array[1:6:2, 2:8:3],
                                  [[.012, .015], [.032, .035], [.052, .055]])
    np.testing.assert_array_equal(array[::-2, 6:0:-3],
                                  [[.066, .063], [.046, .043], [.026, np.nan], [.006, .003]])
    assert np.isnan(array[2, 3])
    assert array[1:1, :].shape == (0, 9)
    assert calls == [["SFX.WG1P1"]] * 4
    assert path.read_bytes() == before


@pytest.mark.parametrize("options", [{"surface_pack": 1}, {"program": "OTHER"}])
def test_unqualified_packing_or_producer_does_not_bypass_dense_gate(
    tmp_path, options, backend_options,
):
    path = fa_files(tmp_path, profile="surfex_history", **options)[0]
    assert inspect_fa(path, None, validate_selection=False, **backend_options)["field_directory"]
    with pytest.raises(ValueError, match="Only AROME SURFEX histories.*PACK=0"):
        inspect_fa(path, "surfex_history", ["SFX.T2M"], **backend_options)


@pytest.mark.parametrize("layout", [
    {"type": "X0"}, {"type": "X2"}, {"type": "N1"}, {"type": "L1"}, {"type": "C1"},
    {"dim1": 62}, {"dim2": 1},
])
def test_unqualified_array_layout_remains_inventory_only(tmp_path, layout, backend_options):
    path = fa_files(tmp_path, profile="surfex_history", surface_fields=[{
        "name": "TESTLAYOUT", "mask": "NATURE", **layout,
        "values": np.ones((7, 9)).tolist()}])[0]
    info = inspect_fa(path, None, ["SFX.TESTLAYOUT"], validate_selection=False, **backend_options)
    assert info["field_directory"]["SFX.TESTLAYOUT"]["TYPE"] == layout.get("type", "X1")
    assert info["field_descriptors"]["SFX.TESTLAYOUT"]["eligibility"]["decode"] == "blocked"
    with pytest.raises(ValueError, match="unsupported SURFEX field type/dimensions"):
        inspect_fa(path, "surfex_history", ["SFX.TESTLAYOUT"], **backend_options)


@pytest.mark.parametrize("damage", [
    "name", "name_program", "directory_program", "only_field", "type", "pack",
])
def test_incomplete_surface_directory_cannot_bypass_profile_checks(
    tmp_path, damage, backend_options,
):
    path = fa_files(tmp_path, profile="surfex_history", program="OTHER")[0]
    original = inspect_fa(path, None, **backend_options)["records"]
    removed = ["SFX._FBUF_NAME"]
    if damage in {"name_program", "directory_program"}:
        removed.append("SFX.PROGRAM")
    if damage == "directory_program":
        removed.extend(name for name in original if name.startswith("SFX._FBUF_"))
    if damage == "only_field":
        removed = [name for name in original if name.startswith("SFX.") and name != "SFX.T2M"]
    if damage in {"type", "pack"}:
        removed = ["SFX._FBUF_TYPE" if damage == "type" else "SFX.PACK"]
    # Corrupt only our generated negative fixture, in a separate native process.
    script = """
import json, sys
from uuid import uuid4
from falfilfa4py import FA, LFI
unit = FA.wfaitou(sys.argv[1], 'OLD', uuid4().hex[:16])
try:
    for name in json.loads(sys.argv[2]):
        LFI.wlfisup(unit, name)
finally:
    FA.wfairme(unit, 'KEEP')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(path), json.dumps(sorted(set(removed)))],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    info = inspect_fa(path, None, validate_selection=False, **backend_options)
    if damage == "name":
        assert info["surfex_metadata"]["PROGRAM"] == "OTHER"
    assert info["surfex_metadata"]["layout_status"] == "incomplete_surfex_directory"
    assert set(info["surfex_metadata"]["missing_records"]) >= set(removed) & {
        "SFX._FBUF_NAME", "SFX.PROGRAM", "SFX._FBUF_TYPE", "SFX.PACK"}
    assert "SFX.T2M" in info["records"]
    for profile, fields in (("arome_history", []), ("arome_history", ["SFX.T2M"]),
                            ("surfex_history", ["SFX.T2M"])):
        with pytest.raises(ValueError, match="Incomplete SURFEX source"):
            inspect_fa(path, profile, fields, **backend_options)
    descriptor = inspect_fa(path, None, ["SFX.T2M"], validate_selection=False, **backend_options)[
        "field_descriptors"]["SFX.T2M"]
    assert descriptor["eligibility"]["decode"] == "blocked"
    assert any("incomplete SURFEX" in reason for reason in descriptor["eligibility"]["reasons"])
    assert "falfilfa4py" not in sys.modules


def categorical_document(tmp_path):
    classes = np.tile([0., 0., 2., 2., 5., np.nan, 0., 2., 0.], (7, 1))
    path = fa_files(tmp_path, profile="surfex_history", surface_fields=[{
        "name": "COVERCLASS", "mask": "FULL", "values": classes.tolist()}])[0]
    raw = single_fa_document(tmp_path, [path])
    raw["variables"] = {"surface": {"names": ["SFX.COVERCLASS"]}}
    raw["input"]["fa"]["field_metadata"] = {"SFX.COVERCLASS": {
        "units": "1", "kind": "categorical", "temporal_kind": "instantaneous"}}
    return raw


def test_categorical_selection_rejects_bilinear_before_payload_reads(
    tmp_path, monkeypatch, backend_options,
):
    raw = categorical_document(tmp_path)
    raw["input"]["fa"].update(backend_options)
    raw["polar"] = {"enabled": True}

    def forbidden(*args, **kwargs):
        raise AssertionError("categorical method validation must precede physical decoding")

    monkeypatch.setattr("frameit.io.fa_utils.request_fa", forbidden)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="categorical FA fields require explicit nearest_s2d"):
        preflight(conf)
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("polar", [False, True])
def test_dense_x1_categories_keep_codes_and_masks_in_ordinary_outputs(
    tmp_path, polar, backend_options,
):
    if polar:
        pytest.importorskip("xesmf")
    raw = categorical_document(tmp_path)
    raw["input"]["fa"].update(backend_options)
    raw["polar"] = {"enabled": polar, "interpolation_method": "nearest_s2d",
                    "radial_step_m": 2000., "azimuth_count": 8}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf)
    assert result.ok
    paths = {item["role"]: item["path"] for item in result.products}
    check = subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
paths = json.loads(sys.argv[1])
with xr.open_dataset(paths['cart']) as native:
    v = native['SFX.COVERCLASS']
    np.testing.assert_array_equal(v[0], np.tile([2., 2., 5., np.nan, 0.], (5, 1)))
    assert v.attrs['kind'] == 'categorical' and v.attrs['units'] == '1'
    d = json.loads(v.attrs['fa_field_descriptor'])
    assert d['native']['type'] == 'X1' and d['native']['decoded_dtype'] == 'float64'
    assert d['mask']['support_map'] is None
if 'polar' in paths:
    with xr.open_dataset(paths['polar']) as target:
        values = target['SFX.COVERCLASS'].values
        assert set(values[np.isfinite(values)]) <= {0., 2., 5.}
        assert np.any(values == 0.) and np.isnan(values).any()
assert not {'frameit', 'falfilfa4py', 'epygram'} & sys.modules.keys()
""", json.dumps(paths)], capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    assert provenance["fa_inputs"][0]["fields"]["SFX.COVERCLASS"]["kind"] == "categorical"
    versions = provenance["fa_inputs"][0]["backend_versions"]
    assert versions["FA_backend"] == backend_options["backend"]
    if backend_options["backend"] == "epygram":
        assert provenance["fa_decoder"]["backend_versions"]["EPyGrAM"] == "2.1.0"
