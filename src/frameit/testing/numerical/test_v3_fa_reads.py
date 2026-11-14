"""Selected FA leaf reads retain record-local admission and decode-time checks."""

from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path

import dask
import dask.array as da
import numpy as np
import pytest

from frameit.core.preflight import bind_source, inventory_source
from frameit.io import fa_backend, fa_utils
from frameit.io.fa_contracts import resolve_descriptor
from frameit.io.loader import DatasetResources
from frameit.processing.requests import bind_requests
from frameit.testing.numerical.test_fa_cubes import DECLARATION, fixtures
from frameit.testing.numerical.test_fa_epygram_surfex import surface_fixture
from frameit.testing.numerical.test_fa_io import NATIVE, fa_files
from frameit.testing.numerical.test_inspect_metadata import v3_config

pytestmark = pytest.mark.skipif(not NATIVE, reason="optional EPyGrAM FA stack not installed")


@pytest.fixture(scope="module")
def surface_case(tmp_path_factory):
    directory = tmp_path_factory.mktemp("selected-fa-surface")
    y, x = np.indices((7, 9))
    values = (10 * y + x).astype(float)
    values[2, 3] = np.nan
    paths = fa_files(directory, hours=(0, 1, 2), profile="surfex_history", surface_fields=[
        {"name": "WG1P1", "mask": "NATURE", "values": values.tolist()},
        {"name": "SST", "mask": "SEA", "values": (300. + x + 0 * y).tolist()},
    ])
    for path in paths:
        path.chmod(0o444)
    conf = v3_config(directory, paths, names=("SFX.WG1P1",), profile="surfex_history",
                     time={"values": ["2026-01-01T00:00:00", "2026-01-01T02:00:00"]},
                     field_metadata={"SFX.WG1P1": {**DECLARATION, "units": "m3 m-3"}})
    source = inventory_source(conf, "weather")
    binding = bind_source(conf, "weather")
    assert binding["status"] == "bound"
    return conf, source, binding, paths


@pytest.fixture(scope="module")
def cube_case(tmp_path_factory):
    directory = tmp_path_factory.mktemp("selected-fa-cube")
    paths = fixtures(directory, hours=(0, 1, 2))
    cube = {"records": [f"S{k:03d}TEMPERATURE" for k in (1, 2, 3)],
            "vertical_position": "mass", "sampling": "center"}
    conf = v3_config(directory, paths, names=(), profile="arome_history", model="arome",
                     fa={"earth_radius_m": 6371229.},
                     variables={"3d": ["temperature"], "levels": {"indices": [2, 0]}},
                     time={"values": ["2026-01-01T00:00:00", "2026-01-01T02:00:00"]},
                     native_cubes={"temperature": cube},
                     field_metadata={"temperature": DECLARATION})
    source = inventory_source(conf, "weather")
    binding = bind_source(conf, "weather")
    assert binding["status"] == "bound"
    return conf, source, binding, paths


def payload_requests(monkeypatch):
    """Observe and forward actual helper transactions, never replacement values."""
    native = fa_backend.subprocess.run
    calls = []

    def counted(*args, **kwargs):
        request = json.loads(kwargs["input"])
        calls.append(copy.deepcopy(request))
        return native(*args, **kwargs)

    monkeypatch.setattr(fa_backend.subprocess, "run", counted)
    return calls


def test_surface_leaf_reads_only_selected_samples_and_native_records(
    surface_case, monkeypatch, tmp_path,
):
    conf, source, binding, paths = surface_case
    source = copy.deepcopy(source)
    # A merged summary is deliberately unusable; the selected record is evidence.
    field = next(f for f in source["fields"].values() if f["name"] == "SFX.WG1P1")
    field["native_descriptor"]["eligibility"]["decode"] = "blocked"
    original_pool = copy.deepcopy(source["record_inventory"])
    before = [p.read_bytes() for p in paths]
    selected = binding["products"]["model_grid"]["SFX.WG1P1"]["records"]
    original = copy.deepcopy(selected)
    calls = payload_requests(monkeypatch)
    diagnostics = tmp_path / "decoder.jsonl"
    arrays = [fa_utils.fa_selected_array(
        record, source, options=conf.fa_options, diagnostics_path=str(diagnostics),
    ) for record in selected]
    assert all(isinstance(array.data, da.Array) for array in arrays)
    assert calls == []
    result = dask.compute(*arrays, scheduler="synchronous")
    assert {(Path(c["path"]).name, tuple(c["fields"])) for c in calls} == {
        ("native-000.fa", ("SFX.WG1P1",)), ("native-002.fa", ("SFX.WG1P1",)),
    }
    assert len(calls) == 2 and all(c["operation"] == "read" for c in calls)
    y, x = np.indices((7, 9))
    truth = (10 * y + x).astype(float)
    truth[2, 3] = np.nan
    for array, record in zip(result, selected, strict=True):
        np.testing.assert_array_equal(array[0], truth)
        assert array.dims == ("time", "y", "x")
        assert array.time.values[0] == record["time"]
        assert array.forecast_reference_time.values == record["cycle"]
        assert array.forecast_period.values[0] == record["time"] - record["cycle"]
        assert array.attrs["units"] == "m3 m-3"
        assert array.attrs["surfex_support_mask"] == "NATURE"
        assert float(array[0, 0, 0]) == 0. and np.isnan(array[0, 2, 3])
    for call in calls:
        assert call["zone"] == [0, 9, 0, 7] and call["identity"] in (
            record["locator"]["identity"] for record in selected)
        assert call["field_declaration"] == conf.fa_options["field_metadata"]["SFX.WG1P1"]
    observations = [json.loads(line) for line in diagnostics.read_text().splitlines()]
    assert all(o["payload_read"]["accessor"] == "_readH2DField(getdata=True)"
               for o in observations)
    assert selected == original
    assert source["record_inventory"] == original_pool
    assert [p.read_bytes() for p in paths] == before
    # Packing-0 fixtures retain IEEE NaN, not a native encoded undefined flag.
    assert all(o["field_descriptors"]["SFX.WG1P1"]["mask"]["nonfinite_count"] == 1
               for o in observations)


def test_cube_leaf_keeps_selected_order_and_separate_internal_support(cube_case, monkeypatch):
    conf, source, binding, paths = cube_case
    before = [p.read_bytes() for p in paths]
    original_pool = copy.deepcopy(source["record_inventory"])
    selected = binding["products"]["model_grid"]["temperature"]["records"][1]
    support_request = copy.deepcopy(conf.source_requests["weather"])
    support_request["levels"] = {"indices": [2, 1, 0]}
    support_binding = bind_requests(source, support_request)
    assert support_binding["status"] == "bound"
    support = support_binding["products"]["model_grid"]["temperature"]["records"][1]
    calls = payload_requests(monkeypatch)
    output = fa_utils.fa_selected_array(selected, source, options=conf.fa_options)
    internal = fa_utils.fa_selected_array(support, source, options=conf.fa_options)
    assert calls == []
    actual = output.compute(scheduler="synchronous")
    assert len(calls) == 2
    assert {tuple(c["fields"]) for c in calls} == {
        ("S003TEMPERATURE",), ("S001TEMPERATURE",),
    }
    assert {c["path"] for c in calls} == {str(paths[2])}
    assert actual.dims == ("time", "level", "y", "x")
    assert actual.level.values.tolist() == [3, 1]
    assert actual.level_source_native_index.values.tolist() == [2, 0]
    assert actual.temperature_native_record.values.tolist() == [
        "S003TEMPERATURE", "S001TEMPERATURE",
    ]
    y, x = np.indices((7, 9))
    expected = np.stack([280. + 10 * k + 10 * y + x + 1. for k in (3, 1)])
    expected[:, 1, 1] = np.nan
    expected[:, 2, 2] = 0.
    np.testing.assert_array_equal(actual[0], expected)
    calls.clear()
    support_values = internal.compute(scheduler="synchronous")
    assert support_values.level.values.tolist() == [3, 2, 1]
    assert len(calls) == 3
    assert {tuple(c["fields"]) for c in calls} == {
        ("S003TEMPERATURE",), ("S002TEMPERATURE",), ("S001TEMPERATURE",),
    }
    assert {c["path"] for c in calls} == {str(paths[2])}
    assert output.level.values.tolist() == [3, 1]
    assert source["record_inventory"] == original_pool
    assert [p.read_bytes() for p in paths] == before


def test_public_pending_fa_binding_still_rejected_without_helper_calls(
    surface_case, monkeypatch, tmp_path,
):
    original, _, _, paths = surface_case
    conf = v3_config(tmp_path, paths, names=("SFX.WG1P1",), profile="surfex_history",
                     field_metadata=original.fa_options["field_metadata"],
                     transforms=[{"fields": ["SFX.WG1P1"], "units": "1"}])
    source = inventory_source(conf, "weather")
    calls = payload_requests(monkeypatch)
    with pytest.raises(ValueError, match="incompatible or unsupported units"):
        bind_source(conf, "weather")
    assert calls == []
    assert conf.source_requests["weather"]["binding"] is None
    assert source["requests"]["binding"] is None
    raw = copy.deepcopy(conf.yaml_config)
    raw["sources"]["weather"]["transforms"] = []
    raw["region"] = {"center": {"latitude": -20., "longitude": 50.}}
    raw["products"] = {"polar": {"radius_km": 1.}}
    conf = type(conf).from_mapping_with_model_preset(raw)
    source = inventory_source(conf, "weather")
    binding = bind_source(conf, "weather")
    assert binding["status"] == "pending_method_binding"
    assert conf.source_requests["weather"]["binding"] is None
    assert source["requests"]["binding"] is None
    calls.clear()
    with DatasetResources() as resources:
        import xarray as xr

        closed = []
        existing = xr.Dataset()
        existing.set_close(lambda: closed.append("existing"))
        resources.add(existing)
        with pytest.raises(ValueError, match=(
            "FA selected_records requires bound interpretation"
        )):
            fa_utils.concat_fa2ds_by_vert_coord(
                paths, {}, {}, wind_conf=conf, resources=resources,
                selected_records=binding, source_plan=source,
            )
        assert resources._datasets == [existing] and closed == []
    assert closed == ["existing"]
    assert calls == []


@pytest.mark.parametrize("corruption", ["clock", "shape", "eligibility", "transfer_shape"])
def test_selected_leaf_rejects_contradictory_decoded_record_and_removes_transfer(
    surface_case, monkeypatch, corruption,
):
    conf, source, binding, _ = surface_case
    selected = binding["products"]["model_grid"]["SFX.WG1P1"]["records"][0]
    array = fa_utils.fa_selected_array(selected, source, options=conf.fa_options)
    native = fa_backend.subprocess.run
    transfers = []

    def damaged_response(argv, **kwargs):
        result = native(argv, **kwargs)
        destination = Path(argv[-1])
        transfers.append(destination)
        response = json.loads((destination / "response.json").read_text())
        assert response["ok"], result.stdout + result.stderr
        info = response["result"]
        descriptor = info["field_descriptors"]["SFX.WG1P1"]
        if corruption == "clock":
            descriptor["temporal_support"]["valid_time"] = "2026-01-02T00:00:00"
        elif corruption == "shape":
            descriptor["native"]["shape"] = [9, 7]
        elif corruption == "eligibility":
            descriptor["eligibility"]["decode"] = "unqualified"
        else:
            info["shape"] = [1, 63]
            np.save(destination / "values.npy",
                    np.load(destination / "values.npy", allow_pickle=False).reshape(1, 63))
        (destination / "response.json").write_text(json.dumps(response))
        return result

    monkeypatch.setattr(fa_backend.subprocess, "run", damaged_response)
    with pytest.raises(ValueError, match="FA decoded.*(descriptor|shape).*selection"):
        array.data.compute(scheduler="synchronous")
    assert transfers and all(not path.exists() for path in transfers)


@pytest.mark.parametrize("damage", [
    "missing_descriptor", "blocked", "unknown_shape", "wrong_shape", "native_id",
    "clock", "vertical_header", "zone", "identity", "outside_pool", "declaration",
    "profile", "destination", "raw_vertical", "changed_declaration",
])
def test_leaf_preserves_record_local_admission_before_any_payload(
    surface_case, monkeypatch, damage,
):
    conf, source, binding, _ = surface_case
    source, options = copy.deepcopy(source), copy.deepcopy(conf.fa_options)
    selected = copy.deepcopy(binding["products"]["model_grid"]["SFX.WG1P1"]["records"][0])
    raw = next(r for r in source["record_inventory"]
               if r["name"] == selected["name"] and r["time"] == selected["time"])
    if damage == "missing_descriptor":
        raw.pop("native_descriptor")
        selected.pop("native_descriptor")
    elif damage == "blocked":
        raw["native_descriptor"]["eligibility"].update(decode="blocked", reasons=["not admitted"])
    elif damage in {"unknown_shape", "wrong_shape"}:
        raw["native_descriptor"]["native"]["shape"] = (
            None if damage == "unknown_shape" else [9, 7])
    elif damage == "native_id":
        raw["native_descriptor"]["native_id"] = "SFX.SST"
    elif damage == "clock":
        raw["native_descriptor"]["temporal_support"]["valid_time"] = "2026-01-01T01:00:00"
    elif damage == "vertical_header":
        raw["native_descriptor"]["sampling"]["native_vertical_header"]["KNIVER"] = 99
    elif damage == "zone":
        raw["locator"]["zone"] = [1, 8, 1, 6]
    elif damage == "identity":
        raw["locator"]["identity"] = [0, 0]
    elif damage == "outside_pool":
        source["record_inventory"].remove(raw)
    elif damage == "declaration":
        options["field_metadata"] = {}
    elif damage == "changed_declaration":
        options["field_metadata"]["SFX.WG1P1"]["units"] = "K"
    elif damage == "profile":
        options["profile"] = "arome_history"
    elif damage == "destination":
        selected["selection_grid_id"] = "not-a-native-grid"
    elif damage == "raw_vertical":
        selected["source_positions"] = [0]
    if damage not in {"outside_pool", "destination", "raw_vertical"}:
        selected.update(copy.deepcopy(raw))
    calls = payload_requests(monkeypatch)
    with pytest.raises(ValueError):
        fa_utils.fa_selected_array(selected, source, options=options)
    assert calls == []


@pytest.mark.parametrize("damage", [
    "missing_part", "duplicate_part", "other_sample", "no_label",
    "wrong_part_header", "wrong_part_geometry", "positions", "records", "vertical",
    "vertical_coordinate", "native_index_coordinate", "cube_declaration", "unbound_cube",
])
def test_cube_leaf_requires_matching_selected_raw_candidates(cube_case, monkeypatch, damage):
    conf, source, binding, _ = cube_case
    source, options = copy.deepcopy(source), copy.deepcopy(conf.fa_options)
    selected = copy.deepcopy(binding["products"]["model_grid"]["temperature"]["records"][0])
    part = next(r for r in source["record_inventory"]
                if r["name"] == "S003TEMPERATURE" and r["time"] == selected["time"])
    if damage == "missing_part":
        source["record_inventory"].remove(part)
    elif damage == "duplicate_part":
        source["record_inventory"].append(copy.deepcopy(part))
    elif damage == "other_sample":
        part["time"] = np.datetime64("2026-01-01T01:00:00")
    elif damage == "no_label":
        part["native_descriptor"]["sampling"]["epygram"]["levels"] = []
    elif damage == "wrong_part_header":
        part["native_descriptor"]["sampling"]["native_vertical_header"]["PREFER"] = 1.
    elif damage == "wrong_part_geometry":
        grid = copy.deepcopy(source["native_grids"][part["grid_id"]])
        grid["fa_header"]["epygram"]["x"][0] += 1.
        source["native_grids"][part["grid_id"]] = grid
    elif damage == "positions":
        selected["source_positions"] = [3]
    elif damage == "records":
        selected["locator"]["records"] = ["S003TEMPERATURE", "S002TEMPERATURE"]
    elif damage == "vertical":
        selected["vertical"]["values"] = [2, 1]
    elif damage in {"vertical_coordinate", "native_index_coordinate"}:
        coordinate = "level" if damage == "vertical_coordinate" else "level_source_native_index"
        selected["vertical"]["coordinates"][coordinate]["values"] = [99, 98]
    elif damage == "cube_declaration":
        options["native_cubes"]["temperature"]["sampling"] = "u_face"
    elif damage == "unbound_cube":
        selected = copy.deepcopy(next(r for r in source["record_inventory"]
                                      if r["name"] == "temperature"
                                      and r["time"] == selected["time"]))
    calls = payload_requests(monkeypatch)
    with pytest.raises(ValueError):
        fa_utils.fa_selected_array(selected, source, options=options)
    assert calls == []


def test_public_execution_keeps_fa_pending_before_payload_or_output(
    surface_case, monkeypatch, tmp_path,
):
    from frameit.core.execution import execute_simulation

    original, _, _, paths = surface_case
    conf = v3_config(tmp_path, paths, names=("SFX.WG1P1",), profile="surfex_history",
                     field_metadata={})
    calls = payload_requests(monkeypatch)
    with pytest.raises(ValueError, match="declare.*field_metadata"):
        execute_simulation(conf)
    assert calls and all(call["operation"] == "inspect" for call in calls)
    assert not conf.output_dir.exists()


def test_singleton_cube_leaf_needs_no_excluded_raw_descriptors(cube_case, monkeypatch):
    conf, source, _, paths = cube_case
    request = copy.deepcopy(conf.source_requests["weather"])
    request["levels"] = {"indices": [2]}
    selected = bind_requests(source, request)["products"]["model_grid"]["temperature"]["records"][0]
    source = copy.deepcopy(source)
    # The leaf needs the selected part, not another level or merged summary.
    for part in source["record_inventory"]:
        if part["name"] in {"S001TEMPERATURE", "S002TEMPERATURE"}:
            part.pop("native_descriptor", None)
    for field in source["fields"].values():
        field.pop("native_descriptor", None)
    calls = payload_requests(monkeypatch)
    array = fa_utils.fa_selected_array(selected, source, options=conf.fa_options)
    assert calls == [] and array.sizes["level"] == 1
    result = array.compute(scheduler="synchronous")
    assert result.level.values.tolist() == [3]
    assert result.level_source_native_index.values.tolist() == [2]
    assert len(calls) == 1 and calls[0]["path"] == str(paths[0])
    assert calls[0]["fields"] == ["S003TEMPERATURE"]


def test_leaf_snapshots_options_and_original_descriptor_and_keeps_scalar_slices(
    surface_case, monkeypatch,
):
    conf, source, binding, _ = surface_case
    record = binding["products"]["model_grid"]["SFX.WG1P1"]["records"][0]
    descriptor = resolve_descriptor(record["native_descriptor"],
                                    conf.fa_options["field_metadata"]["SFX.WG1P1"])
    info = {"identity": record["locator"]["identity"],
            "field_descriptors": {"SFX.WG1P1": descriptor}}
    options = copy.deepcopy(conf.fa_options)
    array = fa_utils.FaArray(record["locator"]["path"], "SFX.WG1P1", info, options,
                             record["locator"]["zone"])
    descriptor["units"]["value"] = "not-original"
    options["backend"] = "not-original"
    calls = payload_requests(monkeypatch)
    assert array[0:0].shape == (0, 9) and calls == []
    assert array[0, 0] == 0.
    assert np.isnan(array[2, 3])
    np.testing.assert_array_equal(array[6:0:-2, 8:1:-3], [[68., 65., 62.],
                                                       [48., 45., 42.],
                                                       [28., 25., 22.]])
    assert len(calls) == 3
    assert all(c["fields"] == ["SFX.WG1P1"] and c["backend"] == "epygram" for c in calls)
    assert all(c["field_declaration"]["units"] == "m3 m-3" for c in calls)


def test_lazy_selected_read_rechecks_original_size_mtime_and_cleans_failure(
    surface_case, monkeypatch, tmp_path,
):
    conf, _, _, paths = surface_case
    path = tmp_path / "freshness.fa"
    shutil.copy2(paths[0], path)
    local = v3_config(tmp_path, [path], names=("SFX.WG1P1",), profile="surfex_history",
                      field_metadata=conf.fa_options["field_metadata"])
    source = inventory_source(local, "weather")
    binding = bind_source(local, "weather")
    record = binding["products"]["model_grid"]["SFX.WG1P1"]["records"][0]
    array = fa_utils.fa_selected_array(record, source, options=local.fa_options)
    native = fa_backend.subprocess.run
    transfers = []

    def observed(argv, **kwargs):
        transfers.append(Path(argv[-1]))
        return native(argv, **kwargs)

    monkeypatch.setattr(fa_backend.subprocess, "run", observed)
    stamp = path.stat()
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000))
    with pytest.raises(ValueError, match="changed since inventory"):
        array.compute(scheduler="synchronous")
    assert transfers and all(not directory.exists() for directory in transfers)
    # Only the disposable negative copy changed; source fixtures remain read-only.
    assert path.read_bytes() == paths[0].read_bytes()


@pytest.mark.parametrize("factors,allow_unscaled,message", [
    (None, False, "unresolved native scaling metadata"),
    (None, True, None),
    ([2, 1], False, None),
    ([0, 1], True, "invalid encoded FA scaling"),
])
def test_selected_locator_keeps_decoded_scaling_gate(
    tmp_path, monkeypatch, factors, allow_unscaled, message,
):
    path, truth = surface_fixture(
        tmp_path, packing=120, **({"omit_scaling_section": True} if factors is None
                                 else {"encoded_scaling": factors}))
    original = path.read_bytes()
    conf = v3_config(tmp_path, [path], names=("SFX.T2M",), profile="surfex_history",
                     field_metadata={"SFX.T2M": {**DECLARATION, "allow_unscaled": allow_unscaled}})
    source = inventory_source(conf, "weather")
    binding = bind_source(conf, "weather")
    selected = binding["products"]["model_grid"]["SFX.T2M"]["records"][0]
    diagnostics = tmp_path / "decoder.jsonl"
    calls = payload_requests(monkeypatch)
    array = fa_utils.fa_selected_array(
        selected, source, options=conf.fa_options, diagnostics_path=str(diagnostics))
    assert calls == []
    if message:
        with pytest.raises(ValueError, match=message):
            array.compute(scheduler="synchronous")
    else:
        actual = array.compute(scheduler="synchronous")
        assert np.isnan(actual[0, 1, 1]) and float(actual[0, 2, 2]) == 0.
        if factors is not None:
            np.testing.assert_allclose(actual[0], truth / 20., rtol=0, atol=2.e-6,
                                       equal_nan=True)
        observation = json.loads(diagnostics.read_text().splitlines()[-1])
        mask = observation["field_descriptors"]["SFX.T2M"]["mask"]
        assert mask["nonfinite_count"] == 1
        assert mask["undefined"]["origin"] == "EPyGrAM_returned_mask"
        scaling = observation["field_descriptors"]["SFX.T2M"]["scaling"]
        if factors is None:
            assert scaling["status"] == "missing"
            assert scaling["fallback"] == "identity_explicit_opt_in"
            assert scaling["multiplier"] is None
        else:
            assert scaling["status"] == "encoded" and scaling["fallback"] is None
            assert scaling["divisor"] == 20.
    assert len(calls) == 1 and calls[0]["fields"] == ["SFX.T2M"]
    assert path.read_bytes() == original
