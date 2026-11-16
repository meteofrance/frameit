"""Catalogue preservation regressions, not real-producer qualification."""

from pathlib import Path

import netCDF4
import numpy as np
import pytest
import xarray as xr

from frameit.testing import catalog
from frameit.testing.datasets import ci_dataset_root


@pytest.mark.parametrize("mode", ["ci", "full"])
@pytest.mark.parametrize("case_id,group,names", [
    ("arome_batsirai_speed_only_polar", "heightAboveGround", ["u", "v"]),
    ("mnh_chido_speed_only_polar", "level", ["UT", "VT"]),
])
def test_speed_only_catalogue_declares_a_method_not_a_stored_field(mode, case_id, group, names):
    case, = catalog.load_cases(mode=mode, patterns=(case_id,))
    source = case["config"]["sources"]["atmosphere"]
    assert source["variables"]["3d"][group]["names"] == names
    assert source["derived"] == {"wind_speed": {
        "method": "wind_speed", "inputs": {
            key: f"{group}.{name}" for key, name in zip(("u", "v"), names, strict=True)}}}
    for role in ("model_grid", "polar"):
        assert case["config"]["products"][role]["fields"] == {"atmosphere": ["wind_speed"]}


@pytest.fixture
def resolved_mnh(tmp_path):
    case, = catalog.load_cases(patterns=("mnh_chido_fixed_polar",))
    context = {}
    resolved = catalog.resolve_case(case, ci_dataset_root(), tmp_path / "out", context=context)
    assert resolved["preflight"] == "READY", resolved["reason"]
    inventory, = context["inventories"].values()
    return resolved, inventory


def test_catalogue_preserves_independent_native_and_mass_target_levels(resolved_mnh):
    resolved, _ = resolved_mnh
    products = {item["role"]: item for item in resolved["expected"]["products"]}
    assert products["model_grid"].get("levels") == {
        "level": [5., 25., 65.], "level_w": [0., 20., 50.]}
    assert products["polar"].get("levels") == {"level": [5., 25., 65.]}


def test_catalogue_static_grid_owners_keep_crop_checks_active(resolved_mnh):
    resolved, _ = resolved_mnh
    native = next(item for item in resolved["expected"]["products"] if item["role"] == "model_grid")
    assert native["native_index_coordinates"]
    assert set(native["native_index_coordinates"].values()) == {"cx", "cy"}
    assert native["native_centres"] == [{"cx": 37, "cy": 35}] * 3


def test_catalogue_expected_clock_does_not_follow_a_truncated_production_plan(
        resolved_mnh, monkeypatch):
    from frameit.core import coupled

    resolved, inventory = resolved_mnh
    independent = []
    for path in resolved["input_files"]:
        with netCDF4.Dataset(path) as source:
            time = source["time"]
            dates = netCDF4.num2date(time[:], time.units, time.calendar)
            independent.extend(str(np.datetime64(date.isoformat(), "ns")) for date in dates)
    original = coupled.bind_sources

    def shortened(*args, **kwargs):
        result = original(*args, **kwargs)
        source = result[0]["sources"]["atmosphere"]
        source["selected_times"] = source["selected_times"][1:]
        return result

    monkeypatch.setattr(coupled, "bind_sources", shortened)
    contracts = catalog._products_expected(resolved, resolved["expected"]["levels"], inventory)
    assert len(independent) == 3
    assert all(item["times"] == independent for item in contracts)


@pytest.mark.parametrize("missing", [False, True])
def test_crop_completeness_is_checked_without_a_known_centre(tmp_path, missing):
    from frameit.testing.checks import _check_field_samples

    path = tmp_path / "indices.nc"
    with netCDF4.Dataset(path, "w") as output:
        output.createDimension("x", 3)
        indices = output.createVariable("native_index", "i4", ("x",), fill_value=-999)
        indices[:] = [10, -999 if missing else 11, 12]
    checks = []
    with netCDF4.Dataset(path) as saved:
        _check_field_samples(saved, {
            "variables": [], "native_index_coordinates": {"native_index": "cx"}},
            {}, {}, lambda name, ok, *args, **kwargs: checks.append((name, bool(ok))), {})
    assert checks == [("complete-boxes", not missing)]


def test_prescribed_arome_reference_centre_handoff_needs_no_benchmark_run(tmp_path, monkeypatch):
    # Isolate the reference handoff; this does not waive the separate AROME spacing guard.
    monkeypatch.setattr(catalog, "_products_expected", lambda *args: [
        {"role": "track", "variables": ["latitude", "longitude"]}])
    case, = catalog.load_cases(patterns=("arome_batsirai_prescribed_polar",))
    resolved = catalog.resolve_case(case, ci_dataset_root(), tmp_path / "out")
    assert resolved["preflight"] == "READY", resolved["reason"]
    assert resolved["expected"]["center"] == {"latitude": -17.5, "longitude": 60.}
    with xr.open_dataset(Path(resolved["expected"]["prescribed_track"])) as track:
        np.testing.assert_array_equal(track.latitude, [-17.5] * 5)
        np.testing.assert_array_equal(track.longitude, [60.] * 5)
