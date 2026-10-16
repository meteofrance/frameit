"""Explicit source declarations and native-axis selection contracts."""

import copy

import numpy as np
import pytest
import xarray as xr

from frameit.core.configuration import migrate_mapping, resolve_schema, to_runtime
from frameit.processing.requests import build_group_ds, normalize_requests, selected_native_indices


def schema():
    return {"schema_version": 2, "model": "mesonh", "input": {"pattern": "*.nc"},
            "tracking": {"method": "fixed_box", "fixed_box": {
                "center": {"latitude": 0, "longitude": 0}}},
            "variables": {"level": {"names": ["T"], "levels": "physical"}}}


def native_dataset():
    return xr.Dataset({"T": ("level", [100., 200., 300., 400.]),
                       "W": ("level_w", [1., 2., 3., 4., 5.]),
                       "surface": xr.DataArray(7.)},
                      coords={"level": ("level", [-10., 10., 30., 50.], {
                          "units": "m", "c_grid_dynamic_range": "2:3", "bounds": "bounds"}),
                              "level_w": ("level_w", [-20., 0., 20., 40., 60.], {
                                  "units": "m", "c_grid_dynamic_range": "2:4"}),
                              "bounds": (("level", "nv"), [[-20, 0], [0, 20], [20, 40], [40, 60]])},
                      attrs={"title": "native fixture", "wind_reference_frame": "earth"})


@pytest.mark.parametrize("selection,domain,positions", [
    ("all", "stored", [0, 1, 2, 3]), ("stored", "stored", [0, 1, 2, 3]),
    ("physical", "physical", [1, 2]),
])
def test_selection_preserves_native_values_and_metadata(selection, domain, positions):
    ds = native_dataset()
    req = normalize_requests({"level": {"variables": ["T"], "level_selection": selection}})["level"]
    assert req["level_domain"] == domain
    assert selected_native_indices(ds, req, "level") == positions
    result = build_group_ds(ds, req, "level", "time", None)
    xr.testing.assert_identical(result.T, ds.T.isel(level=positions))
    xr.testing.assert_identical(result.bounds, ds.bounds.isel(level=positions))
    assert result.attrs == ds.attrs
    assert result.attrs is not ds.attrs
    assert result.level.attrs == ds.level.attrs


def test_physical_domains_are_axis_specific():
    ds = native_dataset()
    req = {"level_domain": "physical", "all_levels": True}
    assert selected_native_indices(ds, req, "level") == [1, 2]
    assert selected_native_indices(ds, req, "level_w") == [1, 2, 3]


@pytest.mark.parametrize("bad", ["0:3", "3:2", "2:5", "2", "2.0:3", [2], [True, 3], [2.5, 3]])
def test_invalid_comodo_domain_fails(bad):
    ds = native_dataset()
    ds.level.attrs["c_grid_dynamic_range"] = bad
    with pytest.raises(ValueError, match="c_grid_dynamic_range"):
        selected_native_indices(ds, {"level_domain": "physical"}, "level")


def test_positive_mnh_heights_do_not_establish_physical_domain():
    ds = native_dataset().assign_coords(level=[10., 20., 30., 40.])
    with pytest.raises(ValueError, match="requires.*c_grid_dynamic_range"):
        selected_native_indices(ds, {"level_domain": "physical"}, "level")
    assert selected_native_indices(ds, {"level_domain": "stored"}, "level") == [0, 1, 2, 3]


@pytest.mark.parametrize("axis", ["isobaricInhPa", "isobaricInPa", "heightAboveGround"])
def test_ordinary_grib_axes_have_no_vertical_halo(axis):
    ds = xr.Dataset(coords={axis: [1000., 850., 700.]})
    assert selected_native_indices(ds, {"level_domain": "physical"}, axis) == [0, 1, 2]


def test_source_native_index_retains_original_positions_after_subset():
    ds = native_dataset().assign_coords(source_native_index=("level", [0, 1, 2, 3]))
    subset = ds.isel(level=[0, 2, 3])
    assert selected_native_indices(subset, {"level_domain": "physical"}, "level") == [1]
    req = normalize_requests({
        "level": {"variables": ["T"], "level_selection": "physical"}
    })["level"]
    result = build_group_ds(subset, req, "level", "time", None)
    np.testing.assert_array_equal(result.source_native_index, [2])
    np.testing.assert_array_equal(result.level, [30.])


def test_surface_group_copies_global_metadata():
    ds = native_dataset()
    result = build_group_ds(ds, {"variables": ["surface"]}, "surface", "time", None)
    assert result.attrs == ds.attrs
    assert result.attrs is not ds.attrs


def test_native_index_and_value_selections_remain_distinct():
    ds = native_dataset()
    requests = normalize_requests({
        "level": {"variables": ["T"], "level_selection": "indices", "level_indices": [0, 2]},
        "level_w": {"variables": ["W"], "level_selection": "values", "level_values": [0., 40.]},
    })
    assert normalize_requests(requests) == requests
    assert selected_native_indices(ds, requests["level"], "level") == [0, 2]
    assert selected_native_indices(ds, requests["level_w"], "level_w") == [1, 3]
    indices = build_group_ds(ds, requests["level"], "level", "time", None)
    values = build_group_ds(ds, requests["level_w"], "level_w", "time", None)
    xr.testing.assert_identical(indices.T, ds.T.isel(level=[0, 2]))
    xr.testing.assert_identical(values.W, ds.W.isel(level_w=[1, 3]))


def test_physical_filter_does_not_renumber_explicit_indices():
    ds = native_dataset()
    req = {"variables": ["T"], "level_domain": "physical", "level_indices": [0, 2, 3]}
    assert selected_native_indices(ds, req, "level") == [2]
    result = build_group_ds(ds, req, "level", "time", None)
    xr.testing.assert_identical(result.T, ds.T.isel(level=[2]))


@pytest.mark.parametrize("levels,domain", [("all", "stored"), ("stored", "stored"),
                                         ("physical", "physical")])
def test_schema_level_domain_and_no_implicit_wind_declaration(levels, domain):
    raw = schema()
    raw["variables"]["level"]["levels"] = levels
    runtime = to_runtime(raw)
    assert runtime["wind_reference_frame"] is None
    assert runtime["wind_pairs"] == []
    normalized = normalize_requests(runtime["requested_variables_user"])
    assert normalized["level"]["level_domain"] == domain


@pytest.mark.parametrize("pair", [
    None, {}, {"group": "surface", "u": "U", "v": "V", "reference_frame": "auto"},
    {"group": "surface", "u": "U", "v": "V", "reference_frame": "earth", "extra": 1},
    {"group": "surface", "u": "U", "v": "U", "reference_frame": "earth"},
    {"group": "surface", "u": 1, "v": "V", "reference_frame": "earth"},
    {"group": "surface", "u": "U", "v": "V", "reference_frame": "grid"},
    {"group": "surface", "u": "U", "v": "V", "reference_frame": "grid",
     "rotation": {"method": "auto"}},
    {"group": "surface", "u": "U", "v": "V", "reference_frame": "grid",
     "rotation": {"method": "coordinate"}},
    {"group": "surface", "u": "U", "v": "V", "reference_frame": "grid",
     "rotation": {"method": "geolocation", "extra": True}},
])
def test_strict_wind_pair_declarations(pair):
    raw = schema()
    raw["input"]["wind_pairs"] = [pair]
    with pytest.raises(ValueError, match="wind_pairs"):
        resolve_schema(raw)


def test_duplicate_pair_components_fail_but_different_groups_are_distinct():
    raw = schema()
    pair = {"group": "surface", "u": "U", "v": "V", "reference_frame": "earth"}
    raw["input"]["wind_pairs"] = [pair, copy.deepcopy(pair)]
    with pytest.raises(ValueError, match="duplicate"):
        resolve_schema(raw)
    raw["input"]["wind_pairs"][1]["group"] = "level"
    assert to_runtime(raw)["wind_pairs"] == raw["input"]["wind_pairs"]


@pytest.mark.parametrize("method", ["coordinate", "geolocation", "mesonh_projection"])
def test_explicit_grid_rotation_roundtrip(method):
    raw = schema()
    rotation = {"method": method}
    if method == "coordinate":
        rotation["coordinate"] = "grid_angle"
    raw["input"]["wind_pairs"] = [{"group": "level", "u": "UT", "v": "VT",
                                    "reference_frame": "grid", "rotation": rotation}]
    assert to_runtime(raw)["wind_pairs"] == raw["input"]["wind_pairs"]


@pytest.mark.parametrize("section,key,value", [
    ("cartesian", "horizontal_winds", "auto"), ("cartesian", "horizontal_winds", []),
    ("cartesian", "vertical_velocity", "native"), ("polar", "vertical_velocity", False),
])
def test_invalid_output_selectors(section, key, value):
    raw = schema()
    raw["output"] = {section: {key: value}}
    with pytest.raises(ValueError, match=f"output.{section}.{key}"):
        resolve_schema(raw)


def test_output_selections_and_legacy_explicit_frame_are_preserved():
    raw = schema()
    raw["output"] = {"cartesian": {"horizontal_winds": "native", "vertical_velocity": "mass"},
                     "polar": {"vertical_velocity": "interfaces"}}
    runtime = to_runtime(raw)
    assert runtime["cartesian_horizontal_winds"] == "native"
    assert runtime["cartesian_vertical_velocity"] == "mass"
    assert runtime["polar_vertical_velocity"] == "interfaces"
    for frame in (None, "earth", "grid"):
        old = {"atm_model": "MNH", "wind_reference_frame": frame}
        migrated, _ = migrate_mapping(old)
        assert migrated["input"]["wind_reference_frame"] == frame


def test_no_auto_global_frame():
    raw = schema()
    raw["input"]["wind_reference_frame"] = "auto"
    with pytest.raises(ValueError, match="wind_reference_frame"):
        resolve_schema(raw)
