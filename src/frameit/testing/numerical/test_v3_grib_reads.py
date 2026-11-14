"""Bound GRIB locators, observed at the real ecCodes payload boundary."""

from copy import deepcopy
from threading import Event

import numpy as np
import pytest
import xarray as xr

from frameit.core.preflight import bind_source, inventory_source
from frameit.io.grib_utils import concat_grib2ds_by_vert_coord
from frameit.io.loader import DatasetResources
from frameit.processing.requests import bind_requests
from frameit.testing.numerical.test_inspect_metadata import v3_config


def write_messages(path, declarations, *, jfast=False):
    ec = pytest.importorskip("eccodes")
    with path.open("wb") as stream:
        for declaration in declarations:
            handle = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
            try:
                hour = declaration.get("hour", 1)
                level = declaration.get("level", 850)
                latitude = declaration.get("latitude", -20.)
                for key, value in {
                    "Ni": 3, "Nj": 2, "latitudeOfFirstGridPointInDegrees": latitude,
                    "latitudeOfLastGridPointInDegrees": latitude + 1.,
                    "longitudeOfFirstGridPointInDegrees": 60.,
                    "longitudeOfLastGridPointInDegrees": 62.,
                    "iDirectionIncrementInDegrees": 1., "jDirectionIncrementInDegrees": 1.,
                    "jScansPositively": 1, "jPointsAreConsecutive": int(jfast),
                    "dataDate": 20260101, "dataTime": declaration.get("cycle", 0),
                    "paramId": declaration.get("param", 131),
                    "typeOfLevel": declaration.get("group", "isobaricInhPa"),
                    "level": level, "forecastTime": hour, "uvRelativeToGrid": 1,
                }.items():
                    ec.codes_set(handle, key, value)
                if "member" in declaration:
                    ec.codes_set(handle, "productDefinitionTemplateNumber", 1)
                    ec.codes_set(handle, "perturbationNumber", declaration["member"])
                    ec.codes_set(handle, "numberOfForecastsInEnsemble",
                                 declaration.get("ensemble_count", 2))
                    ec.codes_set(handle, "typeOfEnsembleForecast", declaration.get(
                        "ensemble_type", declaration["member"]))
                if declaration.get("interval"):
                    ec.codes_set(handle, "stepType", "avg")
                    ec.codes_set(handle, "startStep", declaration.get("start", hour - 1))
                    ec.codes_set(handle, "endStep", hour)
                if declaration.get("subminute"):
                    ec.codes_set(handle, "second", 30)
                    ec.codes_set(handle, "stepUnits", "s")
                    ec.codes_set(handle, "forecastTime", 45)
                base = hour * 1000 + level
                values = np.array([0., base + 1., -1.e30, 9999., base + 4., base + 5.])
                if declaration.get("missing", True):
                    ec.codes_set(handle, "missingValue", -1.e30)
                    ec.codes_set(handle, "bitmapPresent", 1)
                else:
                    values[2] = base + 2.
                ec.codes_set_values(handle, values)
                ec.codes_write(handle, stream)
            finally:
                ec.codes_release(handle)
    path.chmod(0o444)
    return path


def bound_source(tmp_path, declarations, *, variables=None, time=None, jfast=False):
    path = write_messages(tmp_path / "multi.grib", declarations, jfast=jfast)
    conf = v3_config(
        tmp_path, [path], model="arome",
        variables=variables or {"3d": ["u"], "levels": {"values": [700, 1000]}},
        time=time or {"values": ["2026-01-01T01:00:00", "2026-01-01T02:00:00"]},
    )
    source = inventory_source(conf, "weather")
    binding = bind_source(conf, "weather")
    assert binding["status"] == "bound"
    return path, source, binding


def observe_decoder(monkeypatch):
    """Spy on native payload decoding and release without replacing the decoder."""
    ec = pytest.importorskip("eccodes")
    reads, active, opened = [], set(), []
    original_new = ec.codes_new_from_message
    original_release = ec.codes_release
    original_values = ec.codes_get_values
    original_array = ec.codes_get_array
    original_get = ec.codes_get

    def new(raw):
        handle = original_new(raw)
        active.add(handle)
        opened.append(bytes(raw))
        return handle

    def release(handle):
        try:
            return original_release(handle)
        finally:
            active.remove(handle)

    def payload(handle):
        reads.append((
            original_get(handle, "paramId"), original_get(handle, "dataTime"),
            original_get(handle, "endStep"), original_get(handle, "level"),
            original_get(handle, "number") if ec.codes_is_defined(handle, "number") else None,
        ))

    def values(handle, *args, **kwargs):
        payload(handle)
        return original_values(handle, *args, **kwargs)

    def array(handle, key, *args, **kwargs):
        if key in {"values", "codedValues", "packedValues"}:
            payload(handle)
        return original_array(handle, key, *args, **kwargs)

    def get(handle, key, *args, **kwargs):
        if key in {"values", "codedValues", "packedValues"}:
            payload(handle)
        return original_get(handle, key, *args, **kwargs)

    def no_scan(*args, **kwargs):
        raise AssertionError("Selected GRIB loading rediscovered the message inventory")

    monkeypatch.setattr(ec, "codes_new_from_message", new)
    monkeypatch.setattr(ec, "codes_release", release)
    monkeypatch.setattr(ec, "codes_get_values", values)
    monkeypatch.setattr(ec, "codes_get_array", array)
    monkeypatch.setattr(ec, "codes_get", get)
    monkeypatch.setattr(ec, "codes_grib_new_from_file", no_scan)
    return reads, active, opened


@pytest.mark.parametrize("jfast", [False, True])
def test_selected_messages_are_lazy_and_exclude_times_levels_and_providers(
    tmp_path, monkeypatch, jfast,
):
    declarations = [
        {"hour": hour, "level": level, "param": param}
        for hour in (0, 1, 2, 3) for level in (700, 1000, 850) for param in (131, 132)
    ]
    # Competing providers at an excluded level cannot be resolved by "first".
    declarations.append({"hour": 1, "level": 850})
    path, source, binding = bound_source(
        tmp_path, declarations, jfast=jfast,
        variables={"3d": ["u"], "levels": {"values": [70000, 100000], "units": "Pa"}},
    )
    before = path.read_bytes()
    reads, active, opened = observe_decoder(monkeypatch)
    with DatasetResources() as resources:
        user, internal = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
        )
        assert not reads and not active
        assert not internal and len(user) == 1
        grid_id, dataset = next(iter(user.items()))
        assert grid_id == binding["records"][0]["grid_id"]
        assert set(dataset.data_vars) == {"u"}
        assert dataset.u.dims == ("time", "isobaricInhPa", "y", "x")
        assert dataset.u.chunks is not None
        np.testing.assert_array_equal(dataset.isobaricInhPa, [70000., 100000.])
        assert dataset.isobaricInhPa.attrs["units"] == "Pa"
        np.testing.assert_array_equal(dataset.isobaricInhPa_source_native_index, [2, 0])
        np.testing.assert_array_equal(dataset.time, np.array(
            ["2026-01-01T01", "2026-01-01T02"], dtype="datetime64[ns]"))
        np.testing.assert_array_equal(dataset.forecast_reference_time, np.array(
            ["2026-01-01", "2026-01-01"], dtype="datetime64[ns]"))
        assert dataset.time.encoding["calendar"] == "proleptic_gregorian"
        assert dataset.u.attrs["units"] == "m s**-1"
        assert dataset.u.attrs["GRIB_uvRelativeToGrid"] == 1
        assert dataset.u.attrs["source_variable_name"] == "u"
        assert dataset.u.attrs["GRIB_paramId"] == 131
        result = dataset.u.compute(scheduler="synchronous")
        expected = np.array([0., 1701., np.nan, 9999., 1704., 1705.])
        expected = expected.reshape(3, 2).T if jfast else expected.reshape(2, 3)
        np.testing.assert_array_equal(result.isel(time=0, isobaricInhPa=0), expected)
        assert set(reads) == {
            (131, 0, 1, 700, None), (131, 0, 1, 1000, None),
            (131, 0, 2, 700, None), (131, 0, 2, 1000, None),
        }
        assert len(reads) == 4 and not active
    assert resources._datasets == [] and not active
    admitted_bytes = set()
    for record in binding["records"]:
        locator = record["locator"]
        admitted_bytes.add(before[locator["offset"]:locator["offset"] + locator["length"]])
    assert opened and set(opened) <= admitted_bytes
    assert path.read_bytes() == before


def test_internal_stencil_of_exported_name_is_not_exported_or_trimmed(tmp_path, monkeypatch):
    path, source, binding = bound_source(tmp_path, [
        {"hour": hour, "level": level} for hour in (0, 1, 2, 3) for level in (1000, 850, 700)
    ])
    support_request = deepcopy(source["requests"])
    support_request["levels"] = {"indices": [2, 1, 0]}
    support = bind_requests(source, support_request)
    binding["dependencies"]["u"] = support["products"]["model_grid"]["u"]
    binding["records"] = support["records"]
    reads, active, _ = observe_decoder(monkeypatch)
    with DatasetResources() as resources:
        user, internal = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
        )
        exported = next(iter(user.values()))
        ancillary = next(iter(internal["internal"].values()))
        assert not reads
        np.testing.assert_array_equal(exported.isobaricInhPa, [700., 1000.])
        np.testing.assert_array_equal(ancillary.isobaricInhPa, [700., 850., 1000.])
        exported.load(scheduler="synchronous")
        assert len(reads) == 4 and {r[3] for r in reads} == {700, 1000}
        reads.clear()
        ancillary.load(scheduler="synchronous")
        assert len(reads) == 6 and {r[3] for r in reads} == {700, 850, 1000}
        assert not active


@pytest.mark.parametrize("case", [
    "cycle", "subminute", "interval", "members", "alias", "alias_u10", "alias_v10",
])
def test_selected_native_clocks_members_single_levels_and_aliases(
    tmp_path, monkeypatch, case,
):
    declarations = [{"hour": 1}, {"hour": 2}]
    field, category = "u", "3d"
    time = {"values": ["2026-01-01T02:00:00"]}
    if case == "cycle":
        declarations.append({"cycle": 100, "hour": 1})
        time["cycle"] = "2026-01-01T00:00:00"
    if case == "subminute":
        declarations = [{"hour": 0, "subminute": True}]
        time = {"values": ["2026-01-01T00:01:15"]}
    if case == "interval":
        declarations = [{"hour": hour, "interval": True} for hour in (1, 2)]
        field = "avg_u"
    if case == "members":
        declarations = [{"hour": hour, "member": member} for hour in (1, 2) for member in (0, 1)]
    if case.startswith("alias"):
        declarations = [{"hour": 2, "param": 151, "group": "meanSea", "level": 0},
                        {"hour": 2, "param": 165, "group": "heightAboveGround", "level": 10},
                        {"hour": 2, "param": 166, "group": "heightAboveGround", "level": 10}]
        field = {"alias": "prmsl", "alias_u10": "u10", "alias_v10": "v10"}[case]
        category = "2d"
    variables = {category: [field]}
    if category == "3d":
        variables["levels"] = {"indices": [0]}
    path, source, binding = bound_source(
        tmp_path, declarations, variables=variables, time=time,
    )
    reads, active, _ = observe_decoder(monkeypatch)
    # Direct callers also receive the managed close hook.
    user, internal = concat_grib2ds_by_vert_coord(
        [path], {}, {}, selected_records=binding, source_plan=source, wind_conf=object(),
    )
    try:
        dataset = next(iter(user.values()))
        assert not reads and not active and not internal
        assert set(dataset.data_vars) == {field}
        if category == "3d":
            assert dataset.sizes["isobaricInhPa"] == 1
            np.testing.assert_array_equal(dataset.isobaricInhPa, [850.])
        if case == "members":
            np.testing.assert_array_equal(dataset.number, [0, 1])
            assert dataset.number.attrs["standard_name"] == "realization"
            assert dataset.number.attrs["GRIB_numberOfForecastsInEnsemble"] == 2
            np.testing.assert_array_equal(dataset.GRIB_typeOfEnsembleForecast, [0, 1])
            np.testing.assert_array_equal(dataset.GRIB_perturbationNumber, [0, 1])
        if case == "subminute":
            np.testing.assert_array_equal(dataset.forecast_reference_time, np.array(
                ["2026-01-01T00:00:30"], dtype="datetime64[ns]"))
        else:
            np.testing.assert_array_equal(dataset.forecast_reference_time, np.array(
                ["2026-01-01"], dtype="datetime64[ns]"))
        if case == "interval":
            assert dataset.time.attrs["bounds"] == "time_bounds"
            np.testing.assert_array_equal(dataset.time_bounds, np.array(
                [["2026-01-01T01", "2026-01-01T02"]], dtype="datetime64[ns]"))
            assert dataset[field].attrs["GRIB_stepType"] == "avg"
            np.testing.assert_array_equal(dataset.GRIB_startStep, [1])
            np.testing.assert_array_equal(dataset.GRIB_endStep, [2])
        if case.startswith("alias"):
            native, units, param = {
                "alias": ("msl", "Pa", 151),
                "alias_u10": ("10u", "m s**-1", 165),
                "alias_v10": ("10v", "m s**-1", 166),
            }[case]
            assert dataset[field].attrs["source_variable_name"] == native
            assert dataset[field].attrs["units"] == units
            assert dataset[field].attrs["GRIB_paramId"] == param
        dataset.load(scheduler="synchronous")
        assert len(reads) == (2 if case == "members" else 1)
        assert {r[1] for r in reads} == {0} and not active
        if case.startswith("alias"):
            assert {r[0] for r in reads} == {param}
    finally:
        for dataset in user.values():
            dataset.close()
    assert not active


def test_fields_keep_actual_owning_grids(tmp_path, monkeypatch):
    path, source, binding = bound_source(
        tmp_path, [{"hour": 1}, {"hour": 1, "param": 130, "latitude": -10.}],
        variables={"3d": ["u", "t"], "levels": {"indices": [0]}},
        time={"values": ["2026-01-01T01:00:00"]},
    )
    reads, active, _ = observe_decoder(monkeypatch)
    with DatasetResources() as resources:
        user, _ = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
        )
        assert len(user) == 2 and not reads
        for grid_id, dataset in user.items():
            field, = dataset.data_vars
            assert grid_id in source["fields"][binding["products"]["model_grid"][field][
                "field_id"]]["grid_ids"]
            np.testing.assert_array_equal(dataset.latitude[:, 0],
                                          [-20., -19.] if field == "u" else [-10., -9.])
            dataset.load(scheduler="synchronous")
        assert {r[0] for r in reads} == {130, 131} and not active


@pytest.mark.parametrize("case", [
    "pending", "no_source", "outside_files", "outside_inventory", "destination", "polar",
    "duplicate",
])
def test_invalid_or_unbound_selections_fail_without_payloads(tmp_path, monkeypatch, case):
    path, source, binding = bound_source(
        tmp_path, [{"hour": 1}], variables={"3d": ["u"], "levels": {"indices": [0]}},
        time={"values": ["2026-01-01T01:00:00"]},
    )
    binding = deepcopy(binding)
    record = binding["products"]["model_grid"]["u"]["records"][0]
    files = [path]
    if case == "pending":
        binding["status"] = "pending_method_binding"
    if case == "no_source":
        source = None
    if case == "outside_files":
        files = [tmp_path / "unrelated.grib"]
    if case == "outside_inventory":
        record["locator"]["message_index"] += 1
    if case == "destination":
        record["selection_grid_id"] = "not-native"
    if case == "polar":
        binding["products"]["polar"] = binding["products"].pop("model_grid")
    if case == "duplicate":
        binding["products"]["model_grid"]["u"]["records"].append(deepcopy(record))
    reads, active, _ = observe_decoder(monkeypatch)
    with pytest.raises((ValueError, FileNotFoundError)):
        concat_grib2ds_by_vert_coord(
            files, {}, {}, selected_records=binding, source_plan=source,
        )
    assert not reads and not active


def test_native_payload_error_releases_handle_and_loading_error_rolls_back(tmp_path, monkeypatch):
    path, source, binding = bound_source(
        tmp_path, [{"hour": 1}], variables={"3d": ["u"], "levels": {"indices": [0]}},
        time={"values": ["2026-01-01T01:00:00"]},
    )
    reads, active, _ = observe_decoder(monkeypatch)
    resources = DatasetResources()
    prior = resources.add(xr.Dataset())
    user, _ = concat_grib2ds_by_vert_coord(
        [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
    )

    def fail(*args, **kwargs):
        raise RuntimeError("injected native payload failure")

    ec = pytest.importorskip("eccodes")
    monkeypatch.setattr(ec, "codes_get_values", fail)
    with pytest.raises(RuntimeError, match="injected native payload failure"):
        next(iter(user.values())).load(scheduler="synchronous")
    assert not active
    resources.close()
    resources = DatasetResources()
    resources.add(prior)
    closed = []
    original_add = resources.add

    def track(dataset):
        dataset.set_close(lambda: closed.append(dataset))
        return original_add(dataset)

    monkeypatch.setattr(resources, "add", track)
    broken = deepcopy(binding)
    broken["dependencies"]["missing"] = {
        "field_id": "missing", "category": "2d", "records": [
            {**deepcopy(binding["products"]["model_grid"]["u"]["records"][0]),
             "field_id": "missing", "name": "missing"}],
    }
    with pytest.raises(ValueError):
        concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=broken, source_plan=source, resources=resources,
        )
    assert resources._datasets == [prior]
    assert not active and not reads
    assert closed
    resources.close()


def test_changed_native_header_is_rejected_before_payload_decode(tmp_path, monkeypatch):
    path, source, binding = bound_source(
        tmp_path, [{"hour": 1}], variables={"3d": ["u"], "levels": {"indices": [0]}},
        time={"values": ["2026-01-01T01:00:00"]},
    )
    reads, active, _ = observe_decoder(monkeypatch)
    ec = pytest.importorskip("eccodes")
    with DatasetResources() as resources:
        user, _ = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
        )
        original_new = ec.codes_new_from_message

        def changed(raw):
            handle = original_new(raw)
            ec.codes_set(handle, "forecastTime", 3)
            return handle

        monkeypatch.setattr(ec, "codes_new_from_message", changed)
        with pytest.raises(ValueError, match="changed"):
            next(iter(user.values())).load(scheduler="synchronous")
    assert not reads and not active


def test_inconsistent_intervals_are_not_resolved_by_last_message(tmp_path, monkeypatch):
    path, source, binding = bound_source(
        tmp_path, [{"hour": 2, "level": 850, "interval": True, "start": 0},
                   {"hour": 2, "level": 700, "interval": True, "start": 1}],
        variables={"3d": ["avg_u"], "levels": {"indices": [0, 1]}},
        time={"values": ["2026-01-01T02:00:00"]},
    )
    reads, active, _ = observe_decoder(monkeypatch)
    with pytest.raises(ValueError, match="interval"):
        concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source,
        )
    assert not reads and not active


def test_internal_only_field_is_not_exported_and_is_read_only_on_demand(tmp_path, monkeypatch):
    path, source, binding = bound_source(tmp_path, [
        {"hour": hour, "level": level, "param": param}
        for hour in (0, 1, 2, 3) for level in (1000, 850, 700) for param in (131, 132)
    ])
    binding = bind_requests(source, source["requests"], required_inputs=("v",))
    assert binding["status"] == "bound"
    reads, active, _ = observe_decoder(monkeypatch)
    with DatasetResources() as resources:
        user, internal = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
        )
        exported = next(iter(user.values()))
        dependency = next(iter(internal["internal"].values()))
        assert set(exported.data_vars) == {"u"} and set(dependency.data_vars) == {"v"}
        assert not reads
        exported.load(scheduler="synchronous")
        assert len(reads) == 4 and {r[0] for r in reads} == {131}
        reads.clear()
        dependency.load(scheduler="synchronous")
        assert len(reads) == 4 and {r[0] for r in reads} == {132}
        assert {r[2] for r in reads} == {1, 2}
        assert {r[3] for r in reads} == {700, 1000}
        assert not active


def test_threaded_payloads_serialize_native_handle_ownership(tmp_path, monkeypatch):
    path, source, binding = bound_source(tmp_path, [
        {"hour": hour, "level": level} for hour in (1, 2) for level in (700, 1000)
    ])
    reads, active, _ = observe_decoder(monkeypatch)
    ec = pytest.importorskip("eccodes")
    overlapping = Event()
    concurrent_counts = []
    original_new, original_values = ec.codes_new_from_message, ec.codes_get_values
    with DatasetResources() as resources:
        user, _ = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
        )

        def counted(raw):
            handle = original_new(raw)
            concurrent_counts.append(len(active))
            if len(active) > 1:
                overlapping.set()
            return handle

        def values(handle, *args, **kwargs):
            overlapping.wait(timeout=.1)
            return original_values(handle, *args, **kwargs)

        monkeypatch.setattr(ec, "codes_new_from_message", counted)
        monkeypatch.setattr(ec, "codes_get_values", values)
        next(iter(user.values())).load(scheduler="threads", num_workers=2)
    assert len(reads) == 4 and max(concurrent_counts) == 1 and not active


def test_nonpressure_axis_uses_native_increasing_order_and_explicit_indices(tmp_path, monkeypatch):
    path, source, binding = bound_source(
        tmp_path, [{"hour": 1, "level": level, "param": 130, "group": "heightAboveSea"}
                   for level in (200, 50, 100)],
        variables={"3d": ["t"], "levels": {"indices": [2, 0]}},
        time={"values": ["2026-01-01T01:00:00"]},
    )
    reads, active, _ = observe_decoder(monkeypatch)
    with DatasetResources() as resources:
        user, _ = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
        )
        dataset = next(iter(user.values()))
        np.testing.assert_array_equal(dataset.heightAboveSea, [200., 50.])
        np.testing.assert_array_equal(dataset.heightAboveSea_source_native_index, [2, 0])
        assert dataset.heightAboveSea.attrs["units"] == "m"
        assert dataset.t.attrs["units"] == "K"
        assert not reads
        dataset.t.isel(heightAboveSea=1).compute(scheduler="synchronous")
        assert reads == [(130, 0, 1, 50, None)] and not active


@pytest.mark.parametrize("missing", [False, True])
def test_native_bitmap_does_not_mask_valid_zero_or_9999(tmp_path, monkeypatch, missing):
    path, source, binding = bound_source(
        tmp_path, [{"hour": 1, "missing": missing}],
        variables={"3d": ["u"], "levels": {"indices": [0]}},
        time={"values": ["2026-01-01T01:00:00"]},
    )
    reads, active, _ = observe_decoder(monkeypatch)
    with DatasetResources() as resources:
        user, _ = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
        )
        result = next(iter(user.values())).u.compute(scheduler="synchronous")
        np.testing.assert_array_equal(result.squeeze(), np.array(
            [[0., 1851., np.nan if missing else 1852.], [9999., 1854., 1855.]]))
        assert len(reads) == 1 and not active


def test_metadata_failure_releases_native_handle_without_reading_values(tmp_path, monkeypatch):
    path, source, binding = bound_source(
        tmp_path, [{"hour": 1}], variables={"3d": ["u"], "levels": {"indices": [0]}},
        time={"values": ["2026-01-01T01:00:00"]},
    )
    reads, active, _ = observe_decoder(monkeypatch)
    ec = pytest.importorskip("eccodes")
    original_get = ec.codes_get

    def failed(handle, key, *args, **kwargs):
        if key == "shortName":
            raise RuntimeError("injected native metadata failure")
        return original_get(handle, key, *args, **kwargs)

    monkeypatch.setattr(ec, "codes_get", failed)
    with DatasetResources() as resources, pytest.raises(RuntimeError, match="native metadata"):
        concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
        )
    assert not reads and not active and not resources._datasets


@pytest.mark.parametrize("case", ["mixed_members", "surface_levels"])
def test_unrepresentable_native_axes_are_not_silently_dropped(tmp_path, monkeypatch, case):
    declarations = [{"hour": 1}, {"hour": 1, "member": 0}]
    variables = {"3d": ["u"], "levels": {"indices": [0]}}
    if case == "surface_levels":
        declarations = [{"hour": 1, "param": 151, "group": "meanSea", "level": level}
                        for level in (0, 1)]
        variables = {"2d": ["prmsl"]}
    path, source, binding = bound_source(
        tmp_path, declarations, variables=variables,
        time={"values": ["2026-01-01T01:00:00"]},
    )
    reads, active, _ = observe_decoder(monkeypatch)
    with pytest.raises(ValueError, match="native"):
        concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source,
        )
    assert not reads and not active


def test_changing_internal_stencil_is_an_explicit_blocker_not_a_first_record_choice(
    tmp_path, monkeypatch,
):
    path, source, binding = bound_source(tmp_path, [
        {"hour": hour, "level": level} for hour in (1, 2) for level in (700, 850, 1000)
    ])
    support_request = deepcopy(source["requests"])
    support_request["levels"] = {"indices": [2, 1, 0]}
    support = bind_requests(source, support_request)["products"]["model_grid"]["u"]
    exported = binding["products"]["model_grid"]["u"]
    binding["dependencies"]["u"] = {**support, "records": [
        record for record in exported["records"] if record["time"] == np.datetime64("2026-01-01T01")
    ] + [
        record for record in support["records"] if record["time"] == np.datetime64("2026-01-01T02")
    ]}
    reads, active, _ = observe_decoder(monkeypatch)
    with pytest.raises(ValueError, match="stencil"):
        concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source,
        )
    assert not reads and not active


def test_member_metadata_is_not_replaced_by_the_first_members_count(tmp_path, monkeypatch):
    path, source, binding = bound_source(
        tmp_path, [{"hour": 1, "member": 0, "ensemble_count": 2},
                   {"hour": 1, "member": 1, "ensemble_count": 3}],
        variables={"3d": ["u"], "levels": {"indices": [0]}},
        time={"values": ["2026-01-01T01:00:00"]},
    )
    reads, active, _ = observe_decoder(monkeypatch)
    with DatasetResources() as resources:
        user, _ = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source, resources=resources,
        )
        dataset = next(iter(user.values()))
        np.testing.assert_array_equal(dataset.GRIB_numberOfForecastsInEnsemble, [2, 3])
        assert "GRIB_numberOfForecastsInEnsemble" not in dataset.number.attrs
        assert not reads and not active
