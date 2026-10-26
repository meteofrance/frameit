"""P3 dense SURFEX selection preserves supports, undefined values and native IDs."""

from __future__ import annotations

import numpy as np
import pytest

from frameit.core.settings_class import SimulationConfig
from frameit.io.fa_backend import inspect_fa
from frameit.io.fa_utils import concat_fa2ds_by_vert_coord
from frameit.testing.numerical.test_fa_io import NATIVE, fa_files
from frameit.testing.numerical.test_fa_pipeline import single_fa_document

pytestmark = pytest.mark.skipif(not NATIVE, reason="optional falfilfa4py wheel not installed")


def test_dense_directory_order_single_native_layer_masks_and_zero(tmp_path, monkeypatch):
    y, x = np.indices((7, 9))
    moisture = (.01 * (x + y)).astype(float)
    moisture[2, 3] = np.nan
    fields = [
        {"name": "TG2P1", "mask": "NATURE", "values": (290. + y + x).tolist()},
        {"name": "WG1P1", "mask": "NATURE", "values": moisture.tolist()},
        {"name": "SST", "mask": "SEA", "values": (300. + x * .01 + 0*y).tolist()},
    ]
    path = fa_files(tmp_path, profile="surfex_history", surface_fields=fields)[0]
    path.chmod(0o444)
    before = path.read_bytes()
    info = inspect_fa(path, None)
    assert list(info["field_directory"]) == ["SFX.TG2P1", "SFX.WG1P1", "SFX.SST"]
    raw = single_fa_document(tmp_path, [path])
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
    assert path.read_bytes() == before


@pytest.mark.parametrize("options", [{"surface_pack": 1}, {"program": "MESONH"}])
def test_unqualified_packing_or_producer_does_not_bypass_dense_gate(tmp_path, options):
    path = fa_files(tmp_path, profile="surfex_history", **options)[0]
    assert inspect_fa(path, None, validate_selection=False)["field_directory"]
    with pytest.raises(ValueError, match="Only AROME SURFEX histories.*PACK=0"):
        inspect_fa(path, "surfex_history", ["SFX.T2M"])


def test_unqualified_array_layout_remains_inventory_only(tmp_path):
    path = fa_files(tmp_path, profile="surfex_history", surface_fields=[{
        "name": "TESTLAYOUT", "type": "X2", "mask": "NATURE",
        "values": np.ones((7, 9)).tolist()}])[0]
    assert inspect_fa(path, None)["field_directory"]["SFX.TESTLAYOUT"]["TYPE"] == "X2"
    with pytest.raises(ValueError, match="unsupported SURFEX field type/dimensions"):
        inspect_fa(path, "surfex_history", ["SFX.TESTLAYOUT"])
