"""Explicit source declarations and native-axis selection contracts."""

import copy

import numpy as np
import pytest
import xarray as xr

from frameit.core.configuration import resolve_schema, to_runtime
from frameit.processing.requests import build_group_ds, normalize_requests, selected_native_indices


def schema():
    return {"schema_version": "2.1", "model": "mesonh", "input": {"pattern": "*.nc"},
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


@pytest.mark.parametrize("levels,domain", [("stored", "stored"),
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
    pair = {"group": "fields_2d", "u": "U", "v": "V", "reference_frame": "earth"}
    raw["input"]["wind_pairs"] = [pair, copy.deepcopy(pair)]
    with pytest.raises(ValueError, match="duplicate"):
        resolve_schema(raw)
    raw["input"]["wind_pairs"][1]["group"] = "level"
    assert to_runtime(raw)["wind_pairs"] == [
        {**pair, "group": "surface"}, {**pair, "group": "level"}]


@pytest.mark.parametrize("method", ["coordinate", "geolocation", "mesonh_projection"])
def test_explicit_grid_rotation_roundtrip(method):
    raw = schema()
    rotation = {"method": method}
    if method == "coordinate":
        rotation["coordinate"] = "grid_angle"
    raw["input"]["wind_pairs"] = [{"group": "level", "u": "UT", "v": "VT",
                                    "reference_frame": "grid", "rotation": rotation}]
    assert to_runtime(raw)["wind_pairs"] == raw["input"]["wind_pairs"]


def test_mesonh_projection_yaml_parameters_roundtrip():
    raw = schema()
    raw["input"]["wind_pairs"] = [{
        "group": "level", "u": "UT", "v": "VT", "reference_frame": "grid",
        "rotation": {"method": "mesonh_projection", "BETA": 0, "RPK": 0, "LON0": 54.2},
    }]
    assert to_runtime(raw)["wind_pairs"] == raw["input"]["wind_pairs"]


@pytest.mark.parametrize("parameter,value", [
    ("BETA", True), ("BETA", "0"), ("BETA", float("inf")),
    ("RPK", None), ("RPK", [0]), ("RPK", 1.1), ("RPK", -1.1),
    ("LON0", float("nan")),
])
def test_invalid_mesonh_projection_yaml_parameters(parameter, value):
    raw = schema()
    raw["input"]["wind_pairs"] = [{
        "group": "level", "u": "UT", "v": "VT", "reference_frame": "grid",
        "rotation": {"method": "mesonh_projection", parameter: value},
    }]
    with pytest.raises(ValueError, match=parameter):
        resolve_schema(raw)


@pytest.mark.parametrize("method", ["coordinate", "geolocation"])
def test_projection_parameters_require_projection_method(method):
    raw = schema()
    raw["input"]["wind_pairs"] = [{
        "group": "level", "u": "UT", "v": "VT", "reference_frame": "grid",
        "rotation": {"method": method, "coordinate": "angle", "BETA": 0},
    }]
    with pytest.raises(ValueError, match="BETA"):
        resolve_schema(raw)


@pytest.mark.parametrize("section,key,value", [
    ("cartesian", "horizontal_vectors", "auto"), ("cartesian", "horizontal_vectors", []),
    ("cartesian", "vertical_velocity", "native"), ("polar", "vertical_velocity", False),
])
def test_invalid_output_selectors(section, key, value):
    raw = schema()
    raw["output"] = {section: {key: value}}
    with pytest.raises(ValueError, match=f"output.{section}.{key}"):
        resolve_schema(raw)


def test_output_selections_are_preserved():
    raw = schema()
    raw["output"] = {"cartesian": {"horizontal_vectors": "native", "vertical_velocity": "mass"},
                     "polar": {"vertical_velocity": "interfaces"}}
    runtime = to_runtime(raw)
    assert runtime["cartesian_horizontal_winds"] == "native"
    assert runtime["cartesian_vertical_velocity"] == "mass"
    assert runtime["polar_vertical_velocity"] == "interfaces"


def test_no_auto_global_frame():
    raw = schema()
    raw["input"]["wind_reference_frame"] = "auto"
    with pytest.raises(ValueError, match="wind_reference_frame"):
        resolve_schema(raw)


def binding_scene():
    """Distinct labelled axes; no scientific equivalence of the U/V/W samples."""
    ds = xr.Dataset(coords={
        "time": np.array(["2026-01-01", "2026-01-01T01"], dtype="datetime64[ns]"),
        "y": [0., 1.], "x": [0., 1., 2.],
        "level": ("level", [0., 10., 20., 30., 40., 50.],
                  {"axis": "Z", "units": "m", "c_grid_dynamic_range": "2:5",
                   "bounds": "level_bounds"}),
        "level_u": ("level_u", [50., 0., 40., 10., 30., 20.],
                    {"axis": "Z", "units": "m", "c_grid_dynamic_range": "1:4"}),
        "level_v": ("level_v", [0., 20., 40., 60., 80.],
                    {"axis": "Z", "units": "m", "c_grid_dynamic_range": "2:4"}),
        "level_w": ("level_w", [-5., 5., 15., 25., 35., 45., 55.],
                    {"axis": "Z", "units": "m", "c_grid_dynamic_range": "2:6"}),
        "single": ("single", [5.], {"axis": "Z", "units": "m"}),
    }, attrs={"model": "Meso-NH"})
    ds["level_bounds"] = (("level", "nv"),
                          [[-5., 5.], [5., 15.], [15., 25.],
                           [25., 35.], [35., 45.], [45., 55.]])
    for name, axis in (("T", "level"), ("U", "level_u"), ("V", "level_v"),
                       ("W", "level_w"), ("one", "single")):
        shape = (2, ds.sizes[axis], 2, 3)
        ds[name] = (("time", axis, "y", "x"),
                    np.arange(np.prod(shape), dtype=float).reshape(shape),
                    {"units": "K" if name in {"T", "one"} else "m s-1"})
    ds["S"] = (("time", "y", "x"), np.arange(12.).reshape(2, 2, 3), {"units": "Pa"})
    return ds


def binding_inventory(tmp_path, monkeypatch, ds=None, *, variables=None, extra=None):
    from frameit.core.preflight import inventory_source
    from frameit.core.settings_class import SimulationConfig
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads

    ds = binding_scene() if ds is None else ds
    path = tmp_path / "source.nc"
    ds.to_netcdf(path, engine="h5netcdf")
    raw = {"schema_version": 3, "sources": {"weather": {
        "files": str(path), "variables": variables or {"3d": ["T"]}}},
        "output": {"directory": str(tmp_path / "out")}}
    if extra:
        raw.update(extra)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    scientific = set(ds.data_vars) - {"level_bounds"}
    scientific.update(name for variable in ds.variables.values()
                      for name in str(variable.attrs.get("ancillary_variables", "")).split())
    reads = guard_netcdf_payloads(monkeypatch, scientific)
    source = inventory_source(conf, "weather")
    return conf, source, reads


def bind_inventory(conf, **options):
    from frameit.core.preflight import bind_source

    return bind_source(conf, "weather", **options)


@pytest.mark.parametrize("case", [
    "all_unequal", "ordered_indices", "inclusive_indices", "inclusive_values",
    "ordered_values", "physical", "singleton", "wrong_2d", "wrong_3d",
    "missing_index", "missing_value", "unknown_physical", "invalid_physical", "empty_interval",
    "duplicate_field_identity", "duplicate_indices", "duplicate_values",
    "duplicate_resolved_level", "original_positions", "physical_original_positions",
    "promoted_duplicate_provider",
    "promoted_ambiguous_name", "promoted_missing_time", "promoted_wrong_category",
    "coordinate_support", "empty_coordinate_samples", "wrong_coordinate_context",
    "scientific_coordinate_dependency", "missing_native_member",
])
def test_v3_field_and_level_binding(tmp_path, monkeypatch, case):
    ds = binding_scene()
    variables, error = {"3d": ["T", "U", "V", "W"]}, None
    if case == "ordered_indices":
        variables.update({"3d": ["T", "U", "W"], "levels": {"indices": [5, 0]}})
    elif case == "inclusive_indices":
        variables["levels"] = {"indices": {"start": 0, "end": 4, "step": 2}}
    elif case == "inclusive_values":
        variables.update({"3d": ["T", "U", "V"],
                          "levels": {"values": {"min": 9, "max": 41}}})
    elif case == "ordered_values":
        variables.update({"3d": ["T", "U", "V"], "levels": {"values": [40, 0]}})
    elif case == "physical":
        variables["levels"] = {"domain": "physical"}
    elif case == "singleton":
        variables = {"3d": ["one"], "levels": {"indices": [0]}}
    elif case in {"wrong_2d", "wrong_3d"}:
        variables = {"2d": ["T"]} if case == "wrong_2d" else {"3d": ["S"]}
        error = r"atmosphere.*variables.*3d.*T" if case == "wrong_2d" else (
            r"atmosphere.*variables.*2d.*S")
    elif case == "missing_index":
        variables["levels"] = {"indices": [5, 0]}
        error = r"V.*unavailable.*5"
    elif case == "missing_value":
        variables.update({"3d": ["T", "U", "V"], "levels": {"values": [30]}})
        error = r"V.*unavailable.*30"
    elif case == "unknown_physical":
        ds.level_v.attrs.pop("c_grid_dynamic_range")
        variables["levels"] = {"domain": "physical"}
        error = r"(?i)level_v.*physical|physical.*level_v"
    elif case == "invalid_physical":
        ds.level_v.attrs["c_grid_dynamic_range"] = "2:99"
        variables["levels"] = {"domain": "physical"}
        error = "c_grid_dynamic_range.*exceeds"
    elif case == "empty_interval":
        variables["levels"] = {"values": {"min": 100, "max": 110}}
        error = "empty.*level|no.*level"
    elif case in {"coordinate_support", "empty_coordinate_samples", "wrong_coordinate_context"}:
        ds = ds[["T", "level_bounds"]].assign_coords(pressure=(
            "level", [100000., 90000., 80000., 70000., 60000., 50000.],
            {"axis": "Z", "standard_name": "air_pressure", "units": "Pa"}))
        ds.level.attrs.pop("axis")
        ds.T.attrs["coordinates"] = "pressure"
        variables = {"3d": ["T"], "levels": {"values": [800], "units": "hPa"}}
        if case != "coordinate_support":
            error = "pressure.*coordinate.*support|coordinate.*pressure.*support"
    elif case == "scientific_coordinate_dependency":
        ds = ds.assign_coords(quality=(("time", "level", "y", "x"),
                                       np.ones((2, 6, 2, 3)), {"flag_values": [0, 1]}))
        ds.T.attrs["ancillary_variables"] = "quality"
        variables = {"3d": ["T"], "levels": {"indices": [5, 0]}}
    elif case.startswith("promoted_"):
        variables = {"2d": ["S"]}
    elif case == "missing_native_member":
        variables = {"3d": ["T"]}
        error = "native axes|native.*support"
    else:
        variables = {"3d": ["T"]} if case != "all_unequal" else variables

    conf, source, reads = binding_inventory(
        tmp_path, monkeypatch, ds, variables=variables)
    request = conf.source_requests["weather"]
    if case == "duplicate_field_identity":
        request["fields"]["3d"].append("T")
        error = "duplicate.*identity|duplicate.*field"
    elif case in {"duplicate_indices", "duplicate_values", "duplicate_resolved_level"}:
        request["levels"] = ({"indices": [1, 1]} if case == "duplicate_indices" else
                             {"values": [10., 10.]} if case == "duplicate_values" else
                             {"values": [10., np.nextafter(10., 11.)]})
        error = "duplicate.*level"
    elif case in {"original_positions", "physical_original_positions"}:
        grid = source["native_grids"][next(
            r["grid_id"] for r in source["records"] if r["name"] == "T")]
        grid["coordinates"]["level_source_native_index"] = {
            "dimensions": ["level"], "values": np.array([0, 2, 4, 6, 8, 10]),
            "attributes": {}, "dtype": "int64", "role": "coordinate_metadata"}
        grid["coordinate_providers"]["level_source_native_index"] = copy.deepcopy(
            grid["coordinate_providers"]["level"])
        for provider in grid["coordinate_providers"]["level_source_native_index"]:
            provider["variable"] = "level_source_native_index"
        if case == "physical_original_positions":
            grid["coordinates"]["level"]["attributes"]["c_grid_dynamic_range"] = "2:9"
            request["levels"] = {"domain": "physical"}
        else:
            request["levels"] = {"indices": [8, 0]}
    elif case in {"empty_coordinate_samples", "wrong_coordinate_context"}:
        for grid in source["native_grids"].values():
            for provider in grid.get("coordinate_providers", {}).get("pressure", []):
                if case == "empty_coordinate_samples":
                    provider["samples"] = []
                else:
                    provider["path"] = str(tmp_path / "not-the-owning-provider.nc")
    elif case.startswith("promoted_"):
        candidates = [r for r in source["record_inventory"] if r["name"] == "T"]
        assert source["provider_conflicts"] == []
        if case == "promoted_duplicate_provider":
            duplicate = copy.deepcopy(candidates[0])
            duplicate["locator"]["path"] = str(tmp_path / "separate-copy.nc")
            source["record_inventory"].append(duplicate)
            grid = source["native_grids"][duplicate["grid_id"]]
            for providers in grid["coordinate_providers"].values():
                provider = copy.deepcopy(providers[0])
                provider["path"] = duplicate["locator"]["path"]
                providers.append(provider)
            error = "competing.*providers"
        elif case == "promoted_ambiguous_name":
            duplicate = copy.deepcopy(candidates[0])
            duplicate["field_id"] = "distinct-field"
            source["fields"]["distinct-field"] = copy.deepcopy(
                source["fields"][candidates[0]["field_id"]])
            source["record_inventory"].append(duplicate)
            error = "distinct fields.*T.*qualified selectors are unsupported"
        elif case == "promoted_missing_time":
            source["record_inventory"] = [
                r for r in source["record_inventory"] if r["name"] != "T"
                or r["time"] == source["selected_times"][0]]
            error = "T.*unavailable.*selected"
        else:
            request["fields"]["2d"].append("T")
            error = r"atmosphere.*variables.*3d.*T"
    elif case == "missing_native_member":
        candidates = [r for r in source["record_inventory"] if r["name"] == "T"]
        for record in candidates:
            record["native_axes"] = {"number": 0}
        duplicate = copy.deepcopy(candidates[0])
        duplicate["native_axes"] = {"number": 1}
        source["record_inventory"].append(duplicate)

    if error:
        with pytest.raises(ValueError, match=error):
            bind_inventory(conf, required_inputs=["T"] if case.startswith("promoted_") else [])
        assert request["binding"] is None
        assert not (tmp_path / "out").exists()
        return

    binding = bind_inventory(conf)
    assert binding["status"] == "bound"
    assert request["binding"] == binding
    fields = binding["products"]["model_grid"]
    expected = {
        "all_unequal": {"T": list(range(6)), "U": list(range(6)),
                        "V": list(range(5)), "W": list(range(7))},
        "ordered_indices": {"T": [5, 0], "U": [5, 0], "W": [5, 0]},
        "inclusive_indices": {n: [0, 2, 4] for n in ("T", "U", "V", "W")},
        "inclusive_values": {"T": [1, 2, 3, 4], "U": [2, 3, 4, 5], "V": [1, 2]},
        "ordered_values": {"T": [4, 0], "U": [2, 1], "V": [2, 0]},
        "physical": {"T": [1, 2, 3, 4], "U": [0, 1, 2, 3],
                     "V": [1, 2, 3], "W": [1, 2, 3, 4, 5]},
        "singleton": {"one": [0]}, "original_positions": {"T": [4, 0]},
        "physical_original_positions": {"T": [1, 2, 3, 4]},
        "coordinate_support": {"T": [2]},
        "scientific_coordinate_dependency": {"T": [5, 0]},
    }[case]
    for name, positions in expected.items():
        assert fields[name]["category"] == "3d"
        for record in fields[name]["records"]:
            assert record["vertical"]["positions"] == positions
            assert len(record["vertical"]["values"]) == len(positions)
            assert record["locator"]["indexers"] == record["locator"]["coordinate_indexers"]
    if case == "original_positions":
        assert fields["T"]["records"][0]["vertical"]["source_native_indices"] == [8, 0]
    if case == "physical_original_positions":
        assert fields["T"]["records"][0]["vertical"]["source_native_indices"] == [2, 4, 6, 8]
    if case == "coordinate_support":
        vertical = fields["T"]["records"][0]["vertical"]
        assert vertical["coordinate"] == "pressure"
        assert vertical["units"] == "hPa"
        assert vertical["values"] == [800.]
    if case == "scientific_coordinate_dependency":
        assert "quality" in binding["dependencies"]
        quality = binding["dependencies"]["quality"]
        assert quality["records"][0]["vertical"]["positions"] == [5, 0]
        assert any(r["name"] == "quality" for r in source["records"])
        assert not any(name == "quality" for name, _ in reads)
    assert not any(name in set(ds.data_vars) - {"level_bounds"} for name, _ in reads)
    assert source["files"] == [str(tmp_path / "source.nc")]


@pytest.mark.parametrize("case", [
    "pressure", "units_only", "indices_and_units", "incompatible",
    "missing_source", "missing_both", "blank_source", "mixed_no_units", "mixed_with_units",
    "mixed_index_only", "float32_roundoff", "converted_roundoff", "nearby_rejected",
    "float64_nearby_rejected", "ambiguous", "bounds", "bounds_units",
    "range_conversion", "range_subsetting", "range_units_only", "range_nonfinite_bounds",
])
def test_v3_vertical_units(tmp_path, monkeypatch, caplog, case):
    ds = binding_scene()[["T", "level_bounds"]]
    ds = ds.assign_coords(level=("level", [100000., 85000., 70000., 50000., 30000., 10000.],
                                          {"axis": "Z", "units": "Pa", "bounds": "level_bounds"}))
    ds["level_bounds"] = (("level", "nv"), [[101000, 99000], [86000, 84000],
                                           [71000, 69000], [51000, 49000],
                                           [31000, 29000], [11000, 9000]])
    levels, error = {"values": [850], "units": "hPa"}, None
    expected_positions, expected_values = [1], [850.]
    if case.startswith("range_"):
        ds.level.attrs.update(valid_min=5000., valid_max=110000.,
                              valid_range=[5000., 110000.], actual_range=[10000., 100000.])
        ds.level_bounds.attrs.update(valid_min=9000., valid_max=111000.,
                                     valid_range=[9000., 111000.],
                                     actual_range=[9000., 101000.])
        if case == "range_conversion":
            levels = {"indices": [0, 1], "units": "hPa"}
            expected_positions, expected_values = [0, 1], [1000., 850.]
        elif case == "range_subsetting":
            levels = {"indices": [1], "units": "Pa"}
            expected_values = [85000.]
        elif case == "range_units_only":
            levels = {"units": "hPa"}
            expected_positions = list(range(6))
            expected_values = [1000., 850., 700., 500., 300., 100.]
        else:
            ds["level_bounds"] = ds.level_bounds.astype(float)
            ds.level_bounds.values[1, 1] = np.nan
    elif case in {"units_only", "bounds", "bounds_units"}:
        levels = {"units": "hPa"}
        expected_positions = list(range(6))
        expected_values = [1000., 850., 700., 500., 300., 100.]
        if case == "bounds_units":
            ds["level_bounds"] = ds.level_bounds / 100
            ds.level_bounds.attrs["units"] = "hPa"
    elif case == "indices_and_units":
        levels = {"indices": [1], "units": "hPa"}
    elif case == "incompatible":
        levels["units"] = "m"
        error = "(?i)incompatible.*units|units.*incompatible"
    elif case in {"missing_source", "missing_both", "blank_source"}:
        ds.level.attrs.pop("units")
        if case == "blank_source":
            ds.level.attrs["units"] = " "
        levels = {"values": [85000]}
        if case in {"missing_source", "blank_source"}:
            levels["units"] = "hPa"
        expected_values = [85000.]
    elif case.startswith("mixed_"):
        ds["U"] = (("time", "other_z", "y", "x"), np.ones((2, 2, 2, 3)), {"units": "m s-1"})
        ds = ds.assign_coords(other_z=("other_z", [850., 700.], {"axis": "Z", "units": "hPa"}))
        if case == "mixed_no_units":
            levels = {"values": [850]}
            error = "different.*units.*explicit|explicit.*units"
        elif case == "mixed_index_only":
            levels = {"indices": [1]}
            expected_values = [85000.]
    elif case in {"float32_roundoff", "converted_roundoff", "nearby_rejected",
                  "float64_nearby_rejected", "ambiguous"}:
        labels = np.array([.1, .2, .3, .4, .5, .6], dtype="float32")
        units, value = "hPa", .1
        if case == "converted_roundoff":
            units, value = "Pa", .001
        elif case == "nearby_rejected":
            value = .100001
            error = "unavailable"
        elif case == "float64_nearby_rejected":
            labels = labels.astype("float64")
            labels[0], value = .1, .10000000001
            error = "unavailable"
        elif case == "ambiguous":
            labels = np.array([.1, np.nextafter(.1, 1.), .3, .4, .5, .6])
            error = "ambiguous.*level"
        ds = ds.assign_coords(level=("level", labels, {"axis": "Z", "units": units}))
        levels = {"values": [value], "units": "hPa"}
        expected_positions = [0]
        expected_values = [float(labels[0]) / (100 if units == "Pa" else 1)]
    variables = {"3d": ["T", "U"] if case.startswith("mixed_") else ["T"], "levels": levels}
    original = ds.copy(deep=True)
    conf, source, reads = binding_inventory(tmp_path, monkeypatch, ds, variables=variables)
    original_grids = copy.deepcopy(source["native_grids"]) if case.startswith("range_") else None
    if error:
        with pytest.raises(ValueError, match=error):
            bind_inventory(conf)
        assert conf.source_requests["weather"]["binding"] is None
        return
    binding = bind_inventory(conf)
    field = binding["products"]["model_grid"]["T"]
    vertical = field["records"][0]["vertical"]
    assert vertical["positions"] == expected_positions
    np.testing.assert_array_equal(vertical["values"], expected_values)
    if case in {"missing_source", "missing_both", "blank_source"}:
        assert binding["warnings"]
        assert any(message in caplog.text for message in binding["warnings"])
        assert vertical["units_origin"] == ("user_assumption" if case != "missing_both"
                                             else "unknown")
        assert vertical["source_units"] is None
        assert vertical["units"] == ("hPa" if case != "missing_both" else None)
    elif case.startswith("mixed_"):
        other = binding["products"]["model_grid"]["U"]["records"][0]["vertical"]
        assert other["values"] == ([700.] if case == "mixed_index_only" else [850.])
        assert other["units"] == "hPa"
    elif case == "range_subsetting":
        assert vertical["units"] == "Pa"
    else:
        assert vertical["units"] == "hPa"
    if case in {"bounds", "bounds_units"}:
        bounds = vertical["coordinates"]["level_bounds"]
        np.testing.assert_array_equal(bounds["values"],
                                      [[1010, 990], [860, 840], [710, 690],
                                       [510, 490], [310, 290], [110, 90]])
        assert bounds["attributes"]["units"] == "hPa"
        assert vertical["coordinates"]["level"]["attributes"]["bounds"] == "level_bounds"
        assert bounds["dtype"] == str(np.asarray(bounds["values"]).dtype)
        assert vertical["coordinates"]["level"]["dtype"] == str(
            np.asarray(vertical["coordinates"]["level"]["values"]).dtype)
    if case.startswith("range_"):
        scale = 1. if case == "range_subsetting" else .01
        for name, limits in (("level", [5000., 110000.]),
                             ("level_bounds", [9000., 111000.])):
            coord = vertical["coordinates"][name]
            attrs = coord["attributes"]
            assert attrs["valid_min"] == limits[0] * scale
            assert attrs["valid_max"] == limits[1] * scale
            np.testing.assert_array_equal(attrs["valid_range"], np.asarray(limits) * scale)
            if case == "range_nonfinite_bounds" and name == "level_bounds":
                assert "actual_range" not in attrs
                assert np.isnan(coord["values"]).any()
            else:
                np.testing.assert_array_equal(
                    attrs["actual_range"], [np.min(coord["values"]), np.max(coord["values"])])
        for grid_id, grid in source["native_grids"].items():
            for name, coord in grid["coordinates"].items():
                before = original_grids[grid_id]["coordinates"][name]
                xr.testing.assert_identical(
                    xr.DataArray(coord["values"], dims=coord["dimensions"],
                                 attrs=coord["attributes"]),
                    xr.DataArray(before["values"], dims=before["dimensions"],
                                 attrs=before["attributes"]))
    xr.testing.assert_identical(ds, original)
    assert source["fields"][field["field_id"]]["attributes"]["units"] == "K"
    assert not any(name in {"T", "U"} for name, _ in reads)


@pytest.mark.parametrize("case", [
    "promoted_file", "dependency_native_axes", "coordinate_payload_indexers",
    "empty_request", "failed_rebind", "non_numeric_labels",
    "standard_name_axis", "levels_leave_2d", "dependency_vertical_grid",
    "dependency_unused_level_difference",
])
def test_v3_binding_final_support(tmp_path, monkeypatch, case):
    from frameit.core.preflight import inventory_source

    ds = binding_scene()
    if case == "dependency_native_axes":
        ds.T.attrs["ancillary_variables"] = "U"
    if case == "non_numeric_labels":
        ds = ds.assign_coords(level=("level", ["a", "b", "c", "d", "e", "f"],
                                     {"axis": "Z", "units": "1"}))
    if case == "standard_name_axis":
        ds = ds.rename(single="plev")
        ds.plev.attrs = {"standard_name": "air_pressure", "units": "hPa"}
    if case in {"dependency_vertical_grid", "dependency_unused_level_difference"}:
        ds["quality"] = (("time", "level", "y", "x"), np.ones((2, 6, 2, 3)))
        ds.T.attrs["ancillary_variables"] = "quality"
    conf, source, _ = binding_inventory(
        tmp_path, monkeypatch, ds,
        variables={"2d": ["S"]} if case in {"promoted_file", "levels_leave_2d"} else
        {"3d": ["one"]} if case == "standard_name_axis" else {"3d": ["T"]})
    request = conf.source_requests["weather"]
    if case == "standard_name_axis":
        selected = bind_inventory(conf)["products"]["model_grid"]["one"]["records"]
        assert selected[0]["vertical"]["dimension"] == "plev"
        assert selected[0]["vertical"]["values"] == [5.]
        return
    if case == "levels_leave_2d":
        request["levels"] = {"values": [99999], "units": "km"}
        selected = bind_inventory(conf)["products"]["model_grid"]["S"]["records"]
        assert selected[0]["vertical"] is None
        assert selected[0]["source_positions"] is None
        assert source["fields"][selected[0]["field_id"]]["attributes"]["units"] == "Pa"
        return
    if case in {"dependency_vertical_grid", "dependency_unused_level_difference"}:
        request["levels"] = {"indices": [0]}
        for record in source["record_inventory"]:
            if record["name"] == "quality":
                original = source["native_grids"][record["grid_id"]]
                record["grid_id"] = "quality-owning-grid"
                if record["grid_id"] not in source["native_grids"]:
                    grid = copy.deepcopy(original)
                    grid["coordinates"]["level"]["values"][
                        0 if case == "dependency_vertical_grid" else 1] += 100
                    source["native_grids"][record["grid_id"]] = grid
        if case == "dependency_unused_level_difference":
            assert bind_inventory(conf)["status"] == "bound"
            return
        with pytest.raises(ValueError, match=(
                "quality.*vertical.*support|vertical.*support.*quality")):
            bind_inventory(conf)
        return
    if case == "promoted_file":
        later = tmp_path / "support.nc"
        ds[["U"]].to_netcdf(later, engine="h5netcdf")
        # Remove U from the original array pool, as in a real field-split source.
        conf.sources["weather"]["files"] = [str(tmp_path / "source.nc"), str(later)]
        source = inventory_source(conf, "weather")
        source["record_inventory"] = [
            r for r in source["record_inventory"] if r["name"] != "U"
            or r["locator"]["path"] == str(later)]
        assert str(later) not in source["files"]
        binding = bind_inventory(conf, required_inputs=["U"])
        assert binding["status"] == "bound"
        assert source["files"] == [str(tmp_path / "source.nc"), str(later)]
        assert conf.input_files == source["files"]
        assert any(entry["path"] == str(later) and entry["status"] == "selected"
                   for entry in source["file_inventory"])
        assert {r["name"] for r in source["records"]} == {"S", "U"}
        return
    if case == "dependency_native_axes":
        for record in source["record_inventory"]:
            if record["name"] in {"T", "U"}:
                record["native_axes"] = {"number": 0 if record["name"] == "T" else 1}
        error = "U.*native.*support|native.*support.*U"
    elif case == "coordinate_payload_indexers":
        for grid in source["native_grids"].values():
            for provider in grid.get("coordinate_providers", {}).get("level", []):
                for sample in provider["samples"]:
                    sample["indexers"] = {"time": 99}
        error = "coordinate.*level.*support|level.*coordinate.*support"
    elif case == "empty_request":
        request["fields"] = {"2d": [], "3d": []}
        request["exports"] = {}
        binding = bind_inventory(conf)
        assert binding["status"] == "pending_method_binding"
        assert request["binding"] is None
        assert binding["deferred_checks"]
        return
    elif case == "failed_rebind":
        assert bind_inventory(conf)["status"] == "bound"
        request["levels"] = {"indices": [99]}
        error = "unavailable"
    else:
        request["levels"] = {"values": [1.]}
        error = "numeric.*labels|labels.*numeric"
    with pytest.raises(ValueError, match=error):
        bind_inventory(conf)
    assert request["binding"] is None
    assert source.get("field_binding") is None


def grib_binding_inventory():
    """Frozen message metadata only; no decoder or native-stack qualification."""
    times = np.array(["2026-01-01", "2026-01-01T01"], dtype="datetime64[ns]")
    field = {"name": "u", "dimensions": ["y", "x"], "dtype": "float64", "grid_id": "g",
             "grid_ids": ["g"], "attributes": {"units": "m s-1", "GRIB_paramId": 131},
             "group": "isobaricInhPa", "levels": [700, 850], "dependencies": {},
             "coordinate_names": ["latitude", "longitude"], "time_varying": True}
    records = [
        {"field_id": "u", "name": "u", "grid_id": "g", "level": level,
         "time": time, "calendar": "proleptic_gregorian", "cycle": times[0],
         "time_bounds": None, "clock": "GRIB_reference_plus_endStep",
         "temporal_metadata": {}, "locator": {
             "format": "grib", "path": f"hour{hour}.grib", "message_index": i,
             "offset": 100 * i, "length": 100}}
        for hour, time in enumerate(times) for i, level in enumerate((700, 850))]
    source = {"name": "weather", "physical_type": "atmosphere",
              "fields": {"u": field}, "native_grids": {
                  "g": {"dimensions": {"y": 2, "x": 3}, "coordinates": {}}},
              "records": records, "record_inventory": list(records), "selected_times": list(times),
              "dependency_resolution": "declared", "provider_conflicts": []}
    request = {"fields": {"2d": [], "3d": ["u"]}, "levels": {"values": [700]},
               "derived": {}, "exports": {"model_grid": ["u"]}, "internal_inputs": [],
               "transforms": [], "polar_options": {}, "binding": None}
    return source, request


@pytest.mark.parametrize("case", [
    "excluded_conflict", "selected_conflict", "missing_level_at_time",
    "native_pressure_order", "selected_pool_only", "own_axis_not_geometry",
])
def test_v3_grib_binding_metadata(case):
    from frameit.processing.requests import bind_requests

    source, request = grib_binding_inventory()
    if case in {"excluded_conflict", "selected_conflict"}:
        position = 1 if case == "excluded_conflict" else 0
        duplicate = copy.deepcopy(source["record_inventory"][position])
        duplicate["locator"]["path"] = "separate-copy.grib"
        source["record_inventory"].append(duplicate)
    elif case == "missing_level_at_time":
        source["record_inventory"] = [r for r in source["record_inventory"]
                                      if not (r["level"] == 700
                                              and r["time"] == source["selected_times"][1])]
    elif case == "native_pressure_order":
        request["levels"] = {"indices": [0, 1]}
    elif case == "selected_pool_only":
        source["fields"]["u"]["levels"] = [500, 700, 850]
        request["levels"] = {}
    else:
        source["native_grids"]["g"]["coordinates"]["isobaricInhPa"] = {
            "dimensions": ["isobaricInhPa"], "values": [1000., 925., 850., 700., 500.],
            "dtype": "float64", "attributes": {"units": "hPa"}}
    if case in {"selected_conflict", "missing_level_at_time"}:
        with pytest.raises(ValueError, match="competing.*providers" if case == "selected_conflict"
                           else "unavailable.*700.*selected"):
            bind_requests(source, request)
        return
    binding = bind_requests(source, request)
    records = binding["products"]["model_grid"]["u"]["records"]
    expected = [850, 700] if case in {"native_pressure_order", "selected_pool_only"} else [700]
    assert records[0]["vertical"]["values"] == expected
    assert {r["level"] for r in binding["records"]} == set(expected)
    assert not any(r["locator"]["path"] == "separate-copy.grib" for r in binding["records"])


@pytest.mark.parametrize("dtype", ["float32", "float64"])
def test_v3_storage_roundoff_boundary(tmp_path, monkeypatch, dtype):
    # The largest finite stored value must not produce an infinite acceptance band.
    labels = np.array([np.finfo(dtype).max], dtype=dtype)
    ds = binding_scene()[["one"]].assign_coords(
        single=("single", labels, {"axis": "Z", "units": "Pa"}))
    conf, _, _ = binding_inventory(tmp_path, monkeypatch, ds, variables={"3d": ["one"]})
    conf.source_requests["weather"]["levels"] = {"values": [1.], "units": "Pa"}
    with pytest.raises(ValueError, match="unavailable"):
        bind_inventory(conf)


@pytest.mark.parametrize("case", [
    "cube_indices", "cube_values", "wrong_cube_category", "missing_label_evidence",
    "blocked_gridpoint", "unknown_shape", "cube_record_overlap",
    "cube_selected_provider_conflict", "cube_unselected_provider_conflict",
    "sample_specific_evidence",
])
def test_v3_fa_binding_metadata(case):
    from frameit.io.fa_contracts import native_descriptor
    from frameit.processing.requests import bind_requests

    source, request = grib_binding_inventory()
    cube = {"records": ["S001T", "S003T"], "vertical_position": "mass", "sampling": "mass"}
    grid = source["native_grids"]["g"]
    grid["native_vertical_header"] = {"KNIVER": 3}
    source["fields"] = {"temperature": {
        "name": "temperature", "dimensions": ["native_level", "y", "x"],
        "grid_id": "g", "grid_ids": ["g"], "attributes": {}, "dependencies": {},
        "native_cube": cube, "time_varying": False}}
    records = []
    for i, time in enumerate(source["selected_times"]):
        record = {
            "field_id": "temperature", "name": "temperature", "grid_id": "g", "level": None,
            "time": time, "calendar": "proleptic_gregorian", "cycle": source["selected_times"][0],
            "time_bounds": None, "clock": "FA_validity", "temporal_metadata": {},
            "locator": {"format": "fa", "path": f"hour{i}.fa", "records": cube["records"],
                        "zone": [0, 3, 0, 2], "identity": [1000, 1234]}}
        records.append(record)
        for label, name in zip([1, 3], cube["records"], strict=True):
            descriptor = native_descriptor(
                name, 6, {"exists": True, "spectral": False}, {},
                {"KTYPTR": -1, "KNLATI": 2, "KNXLON": 3}, {}, {})
            descriptor["sampling"]["epygram"] = {
                "type_of_first_fixed_surface": 119, "levels": [label]}
            source["fields"][name] = {
                "name": name, "dimensions": ["y", "x"], "grid_id": "g", "grid_ids": ["g"],
                "attributes": {}, "dependencies": {}, "time_varying": False,
                "native_descriptor": descriptor}
            records.append({**record, "field_id": name, "name": name,
                            "native_descriptor": copy.deepcopy(descriptor),
                            "locator": {**record["locator"], "records": [name]}})
    source["records"] = [r for r in records if r["name"] == "temperature"]
    source["record_inventory"] = records
    source["file_inventory"] = [
        {"path": f"hour{i}.fa", "fields": ["temperature", *cube["records"]]}
        for i in range(len(source["selected_times"]))]
    request["fields"]["3d"] = ["temperature"]
    request["exports"] = {"model_grid": ["temperature"]}
    request["levels"] = {"indices": [2, 0]} if case == "cube_indices" else {"values": [3, 1]}
    error = None
    if case == "wrong_cube_category":
        request["fields"] = {"2d": ["temperature"], "3d": []}
        error = "atmosphere.*3d.*temperature"
    elif case == "missing_label_evidence":
        source["fields"]["S003T"]["native_descriptor"]["sampling"]["epygram"]["levels"] = []
        for record in records:
            if record["name"] == "S003T":
                record["native_descriptor"]["sampling"]["epygram"]["levels"] = []
        error = "evidenced.*level|level.*evidence"
    elif case in {"blocked_gridpoint", "unknown_shape"}:
        request["fields"] = {"2d": ["S001T"], "3d": []}
        request["exports"] = {"model_grid": ["S001T"]}
        descriptor = source["fields"]["S001T"]["native_descriptor"]
        if case == "unknown_shape":
            descriptor["native"]["shape"] = None
        else:
            descriptor["eligibility"]["decode"] = "blocked"
        for record in records:
            if record["name"] == "S001T":
                record["native_descriptor"] = copy.deepcopy(descriptor)
        error = "eligibility.*unresolved|eligibility.*blocked"
    elif case == "cube_record_overlap":
        request["fields"]["2d"] = ["S001T"]
        request["exports"]["model_grid"].append("S001T")
        error = "repeated.*S001T|S001T.*repeated|duplicate.*record"
    elif case in {"cube_selected_provider_conflict", "cube_unselected_provider_conflict"}:
        duplicate = copy.deepcopy(records[1])
        duplicate["locator"]["path"] = "separate-copy.fa"
        source["record_inventory"].append(duplicate)
        if case == "cube_selected_provider_conflict":
            error = "competing.*providers"
        else:
            request["levels"] = {"values": [3]}
    if error:
        with pytest.raises(ValueError, match=error):
            bind_requests(source, request)
        return
    binding = bind_requests(source, request)
    assert binding["status"] == "pending_method_binding"
    assert binding["deferred_checks"]
    selected = binding["products"]["model_grid"]["temperature"]["records"]
    assert len(selected) == 2
    for record in selected:
        assert record["vertical"]["dimension"] == "level"
        subset = case == "cube_unselected_provider_conflict"
        assert record["vertical"]["positions"] == ([1] if subset else [1, 0])
        assert record["vertical"]["source_native_indices"] == ([2] if subset else [2, 0])
        assert record["vertical"]["values"] == ([3] if subset else [3, 1])
        assert record["vertical"]["units"] == "1"
        assert record["locator"]["records"] == (["S003T"] if subset else ["S003T", "S001T"])


def test_v3_binding_requires_inventory(tmp_path):
    from frameit.core.settings_class import SimulationConfig

    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3,
        "sources": {"weather": {"files": str(tmp_path / "not-opened.nc"),
                                  "variables": {"2d": ["S"]}}},
    })
    with pytest.raises(ValueError, match="inventory"):
        bind_inventory(conf)
    assert conf.source_requests["weather"]["binding"] is None


def fa_record_inventory(tmp_path, monkeypatch, infos, *, raw=False, time=None):
    """Exercise the actual FA inventory producer with isolated metadata responses."""
    from pathlib import Path

    from frameit.core.preflight import inventory_source
    from frameit.core.settings_class import SimulationConfig
    from frameit.io import fa_backend

    paths = []
    for name in infos:
        path = tmp_path / name
        path.write_bytes(b"mock FA metadata provider; no scientific payload")
        infos[name]["identity"] = [path.stat().st_size, path.stat().st_mtime_ns]
        paths.append(str(path))
    calls = []

    def inspect(path, *, fields=(), validate_selection=True, **options):
        info = infos[Path(path).name]
        calls.append((str(path), tuple(fields)))
        assert options["profile"] == "arome_history"
        if fields:
            assert set(fields) == info["records"].keys() and not validate_selection
        return copy.deepcopy(info)

    def forbidden(*args, **kwargs):
        pytest.fail("FA binding/inventory must not request scientific payloads")

    monkeypatch.setattr(fa_backend, "inspect_fa", inspect)
    monkeypatch.setattr(fa_backend, "request_fa", forbidden)
    variables = {"2d": ["S001T"]} if raw else {"3d": ["temperature"]}
    source = {"files": paths, "profile": "arome_history", "variables": variables,
              "field_metadata": {"S001T" if raw else "temperature": {
                  "units": "K", "kind": "continuous", "temporal_kind": "instantaneous"}}}
    if not raw:
        source["native_cubes"] = {"temperature": {
            "records": ["S001T", "S003T"], "vertical_position": "mass", "sampling": "center"}}
    if time:
        source["time"] = time
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3, "sources": {"weather": source},
        "output": {"directory": str(tmp_path / "not-written")},
    })
    inventory = inventory_source(conf, "weather")
    assert len(calls) == 2 * len(infos)
    return conf, inventory


@pytest.mark.parametrize("case", [
    "cube_different_labels", "cube_missing_requested", "cube_blocked_first",
    "raw_blocked_first", "raw_blocked_second", "raw_excluded_bad", "cube_excluded_labels",
    "missing_raw_descriptor", "missing_cube_part_descriptor", "missing_cube_label",
    "wrong_native_id", "wrong_clock", "wrong_shape", "wrong_vertical_header",
    "selected_conflict", "unselected_conflict", "summary_is_not_evidence",
])
def test_v3_fa_record_evidence_from_inventory(tmp_path, monkeypatch, case):
    from frameit.io.fa_contracts import native_descriptor

    header = {
        "KTYPTR": -1, "KNLATI": 2, "KNXLON": 3, "KNIVER": 4, "PREFER": 100000.,
        "PAHYBR": [0.] * 5, "PBHYBR": [0., .25, .5, .75, 1.],
        "epygram": {
            "schema_version": 1, "native_shape": [2, 3],
            "earth_model": {"radius_m": None, "origin": "fixture"},
            "x": [60., 60.01, 60.02], "y": [-20., -19.99],
            "zones": {"CI": [0, 3, 0, 2]}, "crs": {"grid_mapping_name": "latitude_longitude"},
            "origin": "mock metadata; not native producer qualification",
        },
    }
    infos = {}
    for hour, labels in ((0, [1, 3]), (1, [2, 4])):
        stamp = f"2026-01-01T0{hour}:00:00"
        clocks = {"valid_time": stamp, "reference_time": "2026-01-01T00:00:00"}
        descriptors = {}
        for name, label in zip(["S001T", "S003T"], labels, strict=True):
            descriptor = native_descriptor(
                name, 6, {"exists": True, "spectral": False}, {}, header, {}, clocks)
            descriptor["sampling"]["epygram"] = {
                "type_of_first_fixed_surface": 119, "levels": [label]}
            descriptors[name] = descriptor
        infos[f"hour{hour}.fa"] = {
            **clocks, "geometry": copy.deepcopy(header), "surfex_metadata": {},
            "records": {name: {} for name in descriptors}, "field_descriptors": descriptors,
            "identifier": "metadata fixture", "backend_versions": {"fixture": "metadata only"},
        }
    raw = case in {"raw_blocked_first", "raw_blocked_second", "raw_excluded_bad",
                   "missing_raw_descriptor",
                   "wrong_native_id", "wrong_clock", "wrong_shape"}
    first = infos["hour0.fa"]["field_descriptors"]["S001T"]
    error, bad_path = None, "hour0.fa"
    if case in {"cube_blocked_first", "raw_blocked_first"}:
        first["eligibility"].update(decode="blocked", reasons=["fixture unqualified encoding"])
        error = "eligibility.*blocked"
    elif case == "raw_blocked_second":
        infos["hour1.fa"]["field_descriptors"]["S001T"]["eligibility"].update(
            decode="blocked", reasons=["fixture unqualified encoding"])
        error, bad_path = "eligibility.*blocked", "hour1.fa"
    elif case == "raw_excluded_bad":
        later = infos["hour1.fa"]["field_descriptors"]["S001T"]
        later["native"]["shape"] = None
        later["eligibility"].update(decode="blocked", reasons=["fixture unknown shape"])
    elif case == "cube_missing_requested":
        error, bad_path = "unavailable.*1", "hour1.fa"
    elif case in {"missing_raw_descriptor", "missing_cube_part_descriptor"}:
        error = "record.*descriptor|descriptor.*record"
    elif case == "missing_cube_label":
        first["sampling"]["epygram"]["levels"] = []
        error = "evidenced.*level"
    elif case == "wrong_native_id":
        first["native_id"] = "S999T"
        error = "identity|native_id"
    elif case == "wrong_clock":
        first["temporal_support"]["valid_time"] = "2026-01-01T01:00:00"
        error = "clock|time"
    elif case == "wrong_shape":
        first["native"]["shape"] = [3, 3]
        error = "shape"
    elif case == "wrong_vertical_header":
        first["sampling"]["native_vertical_header"]["KNIVER"] = 3
        error = "header|KNIVER"
    elif case in {"selected_conflict", "unselected_conflict"}:
        duplicate = copy.deepcopy(infos["hour0.fa"])
        duplicate["records"] = {"S001T": {}}
        duplicate["field_descriptors"] = {"S001T": duplicate["field_descriptors"]["S001T"]}
        infos["copy0.fa"] = duplicate
        # Both times retain label 3 while the duplicate only competes at label 1.
        infos["hour1.fa"]["field_descriptors"]["S003T"]["sampling"]["epygram"]["levels"] = [3]
        if case == "selected_conflict":
            error = "competing.*providers"
    time = ({"values": ["2026-01-01T00:00:00"]}
            if case in {"raw_excluded_bad", "cube_excluded_labels"} else None)
    conf, source = fa_record_inventory(tmp_path, monkeypatch, infos, raw=raw, time=time)
    request = conf.source_requests["weather"]
    if case in {"cube_missing_requested", "cube_excluded_labels"}:
        request["levels"] = {"values": [1]}
    elif case == "unselected_conflict":
        request["levels"] = {"values": [3]}
    if case in {"missing_raw_descriptor", "missing_cube_part_descriptor"}:
        for record in source["record_inventory"]:
            if record["name"] == "S001T" and record["time"] == source["selected_times"][0]:
                record.pop("native_descriptor", None)
    if case == "summary_is_not_evidence":
        for field in source["fields"].values():
            if field["name"] == "S001T":
                field["native_descriptor"]["sampling"]["epygram"]["levels"] = [99]
                field["native_descriptor"]["eligibility"]["decode"] = "blocked"
    original_pool = copy.deepcopy(source["record_inventory"])
    if error:
        with pytest.raises(ValueError, match=error) as failure:
            bind_inventory(conf)
        assert bad_path in str(failure.value)
        assert request["binding"] is None and source.get("field_binding") is None
        assert not (tmp_path / "not-written").exists()
        return
    binding = bind_inventory(conf)
    assert binding["status"] == "pending_method_binding" and request["binding"] is None
    assert any("scaling" in check for check in binding["deferred_checks"])
    selected = binding["products"]["model_grid"]["S001T" if raw else "temperature"]["records"]
    assert len(selected) == (1 if time else 2)
    for index, record in enumerate(selected):
        assert record["locator"]["path"] == str(tmp_path / f"hour{index}.fa")
        assert record["time"] == source["selected_times"][index]
        assert record["cycle"] == np.datetime64("2026-01-01T00:00:00")
        assert record["grid_id"] in source["native_grids"]
        assert record["locator"]["zone"] == [0, 3, 0, 2]
        assert record["locator"]["identity"] == infos[f"hour{index}.fa"]["identity"]
        if raw:
            assert record["vertical"] is None
        else:
            expected = ([1] if time else [3] if case == "unselected_conflict"
                        else [1, 3] if index == 0 else [2, 4])
            assert record["vertical"]["values"] == expected
            assert record["vertical"]["source_native_indices"] == [value - 1 for value in expected]
            assert record["locator"]["records"] == (
                ["S003T"] if case == "unselected_conflict" else
                ["S001T"] if time else ["S001T", "S003T"])
            assert "native_descriptor" not in record
    assert source["record_inventory"] == original_pool
    assert all(r["locator"]["path"] in {str(tmp_path / f"hour{i}.fa")
                                      for i in range(1 if time else 2)}
               for r in binding["records"])
    assert not (tmp_path / "not-written").exists()
