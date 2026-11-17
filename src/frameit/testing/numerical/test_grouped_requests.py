"""Explicit native identities and independent selectors, not new scientific methods."""

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.configuration import resolve_schema, source_document
from frameit.core.execution import execute_simulation
from frameit.core.preflight import bind_source, inventory_source
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_v3_grib_reads import write_messages


def grouped_document(tmp_path):
    return {
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "arome", "files": str(tmp_path / "input.grib"),
            "variables": {"2d": ["prmsl"], "3d": {
                "heightAboveGround": {"names": ["u", "v"],
                                      "levels": {"indices": [0, 2, 5]}},
                "isobaric": {"names": ["u", "v"],
                                 "levels": {"values": [1000, 850, 400], "units": "hPa"}},
            }},
            "wind_pairs": [
                {"u": "heightAboveGround.u", "v": "heightAboveGround.v", "basis": "earth"},
                {"u": "isobaric.u", "v": "isobaric.v", "basis": "earth"},
            ],
            "derived": {"speed": {"method": "wind_speed", "inputs": {
                "u": "heightAboveGround.u", "v": "heightAboveGround.v"}}},
        }},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"cpus": 1, "synchronous_export": True},
    }


def test_grouped_schema_preserves_separate_levels_and_reference_consumers(tmp_path):
    raw = grouped_document(tmp_path)
    raw["sources"]["atmosphere"]["transforms"] = [
        {"fields": ["isobaric.u"], "units": "m s-1"}]
    raw["products"] = {"model_grid": {"fields": {"atmosphere": [
        "prmsl", "heightAboveGround.u", "isobaric.u", "speed"]}}}
    original = deepcopy(raw)
    effective, requests, polar = resolve_schema(raw)
    assert raw == original
    request = requests["atmosphere"]
    assert request["fields"] == {"2d": ["prmsl"], "3d": [
        "heightAboveGround.u", "heightAboveGround.v", "isobaric.u", "isobaric.v"]}
    assert request["groups"] == original["sources"]["atmosphere"]["variables"]["3d"]
    assert request["levels"] == {}
    assert request["exports"] == {"model_grid": [
        "prmsl", "heightAboveGround.u", "isobaric.u", "speed"]}
    assert request["internal_inputs"] == ["heightAboveGround.u", "heightAboveGround.v"]
    assert request["transforms"] == [{"fields": ["isobaric.u"], "units": "m s-1"}]
    assert polar == {}
    assert resolve_schema(effective)[0] == effective
    child = source_document(effective, "atmosphere")
    child["sources"]["atmosphere"]["variables"]["3d"]["heightAboveGround"]["names"].append("t")
    request["groups"]["heightAboveGround"]["levels"]["indices"].append(7)
    assert (effective["sources"]["atmosphere"]["variables"]
            == original["sources"]["atmosphere"]["variables"])
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    assert conf.expected_variables_user() == [
        "heightAboveGround.u", "heightAboveGround.v", "isobaric.u",
        "isobaric.v", "prmsl", "speed"]
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("groups,source_levels,error", [
    ({}, None, "3d.*nonempty"),
    ({"isobaric": []}, None, "isobaric.*mapping"),
    ({"isobaric": {}}, None, "isobaric.*names"),
    ({"isobaric": {"names": []}}, None, "names.*nonempty"),
    ({"isobaric": {"names": ["u", "u"]}}, None, "names.*duplicate"),
    ({"isobaric": {"names": ["u"], "indices": [0]}}, None, "indices"),
    ({"isobaric": {"names": ["u"], "levels": {"indices": [-1]}}}, None, "indices"),
    ({"bad.group": {"names": ["u"]}}, None, "group.*identifier"),
    ({"isobaric": {"names": ["u"]}}, {}, "levels.*group"),
    ({"isobaric": {"names": ["u"]}}, {"indices": [0]}, "levels.*group"),
])
def test_grouped_schema_rejects_invalid_or_overlapping_controls(
        tmp_path, groups, source_levels, error):
    raw = grouped_document(tmp_path)
    variables = raw["sources"]["atmosphere"]["variables"]
    variables["3d"] = groups
    if source_levels is not None:
        variables["levels"] = source_levels
    with pytest.raises(ValueError, match=error):
        resolve_schema(raw)
    assert not (tmp_path / "out").exists()


def test_grouped_reference_collisions_fail_before_input_access(tmp_path):
    raw = grouped_document(tmp_path)
    raw["sources"]["atmosphere"]["derived"]["heightAboveGround.u"] = {
        "method": "wind_speed", "inputs": {"u": "heightAboveGround.u", "v": "heightAboveGround.v"}}
    with pytest.raises(ValueError, match="collid"):
        resolve_schema(raw)


def test_flat_requests_keep_their_existing_names_and_shared_selector(tmp_path):
    raw = grouped_document(tmp_path)
    source = raw["sources"]["atmosphere"]
    source["variables"] = {"3d": ["u", "v"], "levels": {"values": [850], "units": "hPa"}}
    source.pop("wind_pairs")
    source.pop("derived")
    effective, requests, _ = resolve_schema(raw)
    assert requests["atmosphere"]["fields"] == {"2d": [], "3d": ["u", "v"]}
    assert requests["atmosphere"]["exports"] == {"model_grid": ["u", "v"]}
    assert requests["atmosphere"]["levels"] == {"values": [850], "units": "hPa"}
    assert "groups" not in requests["atmosphere"]
    assert effective["sources"]["atmosphere"]["variables"] == source["variables"]


def grib_document(tmp_path, *, extra=()):
    declarations = [
        {"hour": hour, "param": param, "group": group, "level": level}
        for hour in (0, 1, 2) for param in (131, 132, 130)
        for group, levels in (("heightAboveGround", (20, 30, 40, 50, 60, 70)),
                              ("isobaric", (1000, 850, 700, 400)))
        for level in levels
    ]
    path = write_messages(tmp_path / "input.grib", [*declarations, *extra])
    raw = grouped_document(tmp_path)
    source = raw["sources"]["atmosphere"]
    source["variables"].pop("2d")
    source.pop("derived")
    source.pop("wind_pairs")
    source["time"] = {"values": ["2026-01-01T01:00:00", "2026-01-01T02:00:00"]}
    return path, raw


def test_grouped_grib_binds_exact_fields_and_independent_levels_without_payloads(
        tmp_path, monkeypatch):
    import eccodes as ec

    _, raw = grib_document(tmp_path)
    monkeypatch.setattr(ec, "codes_get_values", lambda *a, **kw: pytest.fail("scientific read"))
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    source = inventory_source(conf, "atmosphere")
    binding = bind_source(conf, "atmosphere")
    assert binding["status"] == "bound"
    fields = binding["products"]["model_grid"]
    assert set(fields) == {
        "heightAboveGround.u", "heightAboveGround.v", "isobaric.u", "isobaric.v"}
    assert len({field["field_id"] for field in fields.values()}) == 4
    for reference, field in fields.items():
        height = reference.startswith("heightAboveGround.")
        for record in field["records"]:
            assert record["name"] in {"u", "v"}
            assert source["fields"][record["field_id"]]["group"] == reference.partition(".")[0]
            assert record["vertical"]["positions"] == ([0, 2, 5] if height else [0, 1, 3])
            assert record["vertical"]["values"] == ([20, 40, 70] if height else [1000, 850, 400])
            assert record["vertical"]["units"] == ("m" if height else "hPa")
    assert {r["time"] for r in binding["records"]} == {
        np.datetime64("2026-01-01T01", "ns"), np.datetime64("2026-01-01T02", "ns")}
    assert all(r["name"] in {"u", "v"} for r in binding["records"])
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("case", ["unqualified", "wrong_group", "within_group", "provider"])
def test_grouped_identity_guards_reject_before_payloads(tmp_path, monkeypatch, case):
    import eccodes as ec

    extra = []
    if case in {"within_group", "provider"}:
        extra = [{"hour": 1, "group": "heightAboveGround", "level": 20,
                  **({"latitude": -21.} if case == "within_group" else {})}]
    _, raw = grib_document(tmp_path, extra=extra)
    source = raw["sources"]["atmosphere"]
    error = "distinct fields.*u" if case == "unqualified" else (
        "pressure.u.*unavailable|unavailable.*pressure.u" if case == "wrong_group" else
        "distinct fields.*heightAboveGround.u" if case == "within_group"
        else "competing.*providers")
    if case == "unqualified":
        source["variables"] = {"3d": ["u"]}
    elif case == "wrong_group":
        source["variables"] = {"3d": {"pressure": {"names": ["u"]}}}
    monkeypatch.setattr(ec, "codes_get_values", lambda *a, **kw: pytest.fail("scientific read"))
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match=error):
        inventory_source(conf, "atmosphere")
        bind_source(conf, "atmosphere")
    assert conf.source_requests["atmosphere"]["binding"] is None
    assert not (tmp_path / "out").exists()


def test_grouped_netcdf_axes_keep_different_native_positions(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads
    from frameit.testing.numerical.test_request_selection import binding_scene

    ds = binding_scene()
    path = tmp_path / "axes.nc"
    ds.to_netcdf(path, engine="h5netcdf")
    raw = {"schema_version": 3, "sources": {"atmosphere": {
        "model": "mesonh", "files": str(path), "variables": {"3d": {
            "level": {"names": ["T"], "levels": {"indices": [5, 0]}},
            "level_w": {"names": ["W"], "levels": {"indices": [6]}},
        }}}}, "output": {"directory": str(tmp_path / "out")}}
    reads = guard_netcdf_payloads(monkeypatch, set(ds.data_vars) - {"level_bounds"})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    inventory_source(conf, "atmosphere")
    binding = bind_source(conf, "atmosphere")
    fields = binding["products"]["model_grid"]
    assert fields["level.T"]["records"][0]["vertical"]["positions"] == [5, 0]
    assert fields["level_w.W"]["records"][0]["vertical"]["positions"] == [6]
    assert not any(name in {"T", "W"} for name, _ in reads)


@pytest.mark.parametrize("qualified", [False, True])
def test_grouped_metadata_never_applies_a_bare_ambiguous_declaration(
        tmp_path, monkeypatch, qualified):
    import eccodes as ec

    _, raw = grib_document(tmp_path)
    source = raw["sources"]["atmosphere"]
    source["field_metadata"] = {
        "heightAboveGround.u" if qualified else "u": {"kind": "continuous"}}
    monkeypatch.setattr(ec, "codes_get_values", lambda *a, **kw: pytest.fail("scientific read"))
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if not qualified:
        with pytest.raises(ValueError, match="field_metadata.*u.*ambiguous"):
            inventory_source(conf, "atmosphere")
        return
    inventory_source(conf, "atmosphere")
    binding = bind_source(conf, "atmosphere")
    fields = binding["products"]["model_grid"]
    assert fields["heightAboveGround.u"]["field_metadata"]["attributes"]["kind"] == "continuous"
    assert "field_metadata" not in fields["isobaric.u"]


def test_grouped_inspection_offers_only_evidenced_copyable_groups(tmp_path, monkeypatch):
    import eccodes as ec

    _, raw = grib_document(tmp_path)
    raw["sources"]["atmosphere"].pop("variables")
    monkeypatch.setattr(ec, "codes_get_values", lambda *a, **kw: pytest.fail("scientific read"))
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    source = inventory_source(conf, "atmosphere")
    selectors = {item["field"]: item["variables"] for item in source["available_selectors"]}
    assert selectors["heightAboveGround.u"] == {
        "3d": {"heightAboveGround": {"names": ["u"]}}}
    assert selectors["isobaric.u"] == {
        "3d": {"isobaric": {"names": ["u"]}}}
    assert "u" not in selectors
    for reference in ("heightAboveGround.u", "isobaric.u"):
        selected = deepcopy(raw)
        selected["sources"]["atmosphere"]["variables"] = selectors[reference]
        child = SimulationConfig.from_mapping_with_model_preset(selected)
        inventory_source(child, "atmosphere")
        binding = bind_source(child, "atmosphere")
        assert set(binding["products"]["model_grid"]) == {reference}


@pytest.mark.parametrize("different", [False, True])
def test_grouped_derived_inputs_bind_their_own_native_identity(tmp_path, monkeypatch, different):
    import eccodes as ec

    _, raw = grib_document(tmp_path)
    source = raw["sources"]["atmosphere"]
    source["wind_pairs"] = [{"u": "heightAboveGround.u", "v": "heightAboveGround.v",
                             "basis": "grid", "rotation": {"method": "geolocation"}}]
    source["derived"] = {"speed": {"method": "wind_speed", "inputs": {
        "u": "heightAboveGround.u",
        "v": "isobaric.v" if different else "heightAboveGround.v"}}}
    raw["products"] = {"model_grid": {"fields": {"atmosphere": ["speed"]}}}
    monkeypatch.setattr(ec, "codes_get_values", lambda *a, **kw: pytest.fail("scientific read"))
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    inventory_source(conf, "atmosphere")
    if different:
        with pytest.raises(ValueError, match="different.*level selectors"):
            bind_source(conf, "atmosphere")
        return
    binding = bind_source(conf, "atmosphere")
    assert binding["status"] == "bound"
    assert set(binding["products"]["model_grid"]) == {"speed"}
    assert set(binding["dependencies"]) == {"heightAboveGround.u", "heightAboveGround.v"}
    assert len(binding["operation_plans"]) == 2
    for operation in binding["operation_plans"]:
        assert operation["vertical"]["values"] == [20, 40, 70]
        assert operation["inputs"] == {"u": "heightAboveGround.u", "v": "heightAboveGround.v"}
        assert all(record["name"] in {"u", "v"} for record in operation["input_binding"]["records"])


@pytest.mark.parametrize("format", ["netcdf", "zarr"])
@pytest.mark.parametrize("filtered", [False, True])
def test_grouped_grib_execution_preserves_values_names_and_plain_reader(
        tmp_path, monkeypatch, format, filtered):
    import eccodes as ec

    path, raw = grib_document(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    pressure = raw["sources"]["atmosphere"]["variables"]["3d"]["isobaric"]["levels"]
    pressure.update(values=[100000, 85000, 40000], units="Pa")
    raw["output"]["format"] = format
    names = ["heightAboveGround.u"] if filtered else [
        "isobaric.v", "heightAboveGround.u", "isobaric.u", "heightAboveGround.v"]
    raw["products"] = {"model_grid": {"fields": {"atmosphere": names}}}
    calls = []
    original = ec.codes_get_values

    def observed(handle):
        calls.append(tuple(ec.codes_get(handle, key) for key in (
            "typeOfLevel", "shortName", "level", "forecastTime")))
        return original(handle)

    monkeypatch.setattr(ec, "codes_get_values", observed)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf)
    assert result.ok and len(result.products) == 1
    product, = result.products
    assert set(product["fields"]) == set(names)
    assert product["stored_names"] == {name: name for name in names}
    expected = {(group, component, level, hour) for group, components, levels in (
        ("heightAboveGround", ("u",) if filtered else ("u", "v"), (20, 40, 70)),
        *([] if filtered else [("isobaricInhPa", ("u", "v"), (1000, 850, 400))]),
    ) for component in components for level in levels for hour in (1, 2)}
    assert set(calls) == expected
    assert len(calls) == len(expected)
    subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np, xarray as xr
path, fmt, names = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
with (xr.open_zarr(path, consolidated=False) if fmt == 'zarr' else xr.open_dataset(path)) as ds:
    assert set(ds.data_vars) == set(names)
    np.testing.assert_array_equal(ds.time, np.array(
        ['2026-01-01T01', '2026-01-01T02'], dtype='datetime64[ns]'))
    np.testing.assert_array_equal(ds.height_above_ground, [20, 40, 70])
    assert ds.height_above_ground.attrs['units'] == 'm'
    if 'isobaric.u' in names:
        np.testing.assert_array_equal(ds.pressure, [100000, 85000, 40000])
        assert ds.pressure.attrs['units'] == 'Pa'
    for name in names:
        group, raw = name.split('.')
        axis = 'pressure' if group == 'isobaric' else 'height_above_ground'
        assert ds[name].dims == ('time', axis, 'y', 'x')
        assert ds[name].attrs['source_variable_name'] == raw
        assert ds[name].attrs['units'] == 'm s**-1'
        levels = [1000, 850, 400] if axis == 'pressure' else [20, 40, 70]
        for t, hour in enumerate((1, 2)):
            for z, level in enumerate(levels):
                base = 1000 * hour + level
                np.testing.assert_array_equal(ds[name][t, z], [
                    [0., base + 1., np.nan], [9999., base + 4., base + 5.]])
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], format, json.dumps(names)], check=True, capture_output=True, text=True)
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    assert status["state"] == "completed"
    assert status["products"][0]["stored_names"] == {name: name for name in names}
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("forged", [False, True])
def test_grouped_fa_cube_keeps_native_admission_and_qualified_output(tmp_path, forged):
    from frameit.io.fa_utils import concat_fa2ds_by_vert_coord
    from frameit.io.loader import DatasetResources
    from frameit.testing.numerical.test_fa_cubes import DECLARATION, fixtures
    from frameit.testing.numerical.test_fa_io import NATIVE
    from frameit.testing.numerical.test_inspect_metadata import v3_config

    if not NATIVE:
        pytest.skip("optional EPyGrAM FA stack not installed")
    paths = fixtures(tmp_path, hours=(0, 1, 2))
    cube = {"records": [f"S{k:03d}TEMPERATURE" for k in (1, 2, 3)],
            "vertical_position": "mass", "sampling": "center"}
    conf = v3_config(
        tmp_path, paths, names=(), profile="arome_history", model="arome",
        fa={"earth_radius_m": 6371229.},
        variables={"3d": {"level": {"names": ["temperature"], "levels": {"indices": [2, 0]}}}},
        time={"values": ["2026-01-01T00:00:00", "2026-01-01T02:00:00"]},
        native_cubes={"temperature": cube}, field_metadata={"level.temperature": DECLARATION})
    source = inventory_source(conf, "weather")
    binding = bind_source(conf, "weather")
    if forged:
        binding = deepcopy(binding)
        binding["products"]["model_grid"]["wrong.temperature"] = (
            binding["products"]["model_grid"].pop("level.temperature"))
        with DatasetResources() as resources, pytest.raises(ValueError, match="native identity"):
            concat_fa2ds_by_vert_coord(
                paths, {}, {}, wind_conf=conf, resources=resources,
                selected_records=binding, source_plan=source)
        return
    with DatasetResources() as resources:
        user, _ = concat_fa2ds_by_vert_coord(
            paths, {}, {}, wind_conf=conf, resources=resources,
            selected_records=binding, source_plan=source)
        out, = user.values()
        assert set(out.data_vars) == {"level.temperature"}
        np.testing.assert_array_equal(out.level, [3, 1])
        assert out["level.temperature"].attrs["source_variable_name"] == "temperature"
        assert "temperature_native_record" in out.coords
        y, x = np.indices((7, 9))
        expected = np.stack([280. + 10 * k + 10 * y + x for k in (3, 1)])
        expected[:, 1, 1] = np.nan
        expected[:, 2, 2] = 0.
        np.testing.assert_array_equal(out["level.temperature"][0].compute(scheduler="synchronous"),
                                      expected)


@pytest.mark.parametrize("conflicting", [False, True])
@pytest.mark.parametrize("companion", ["THT", "UT"])
def test_grouped_w_transform_selects_destination_without_changing_other_group(
        tmp_path, monkeypatch, conflicting, companion):
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads
    from frameit.testing.numerical.test_v3_operations import configuration, staggered_scene

    ds = staggered_scene()
    ds.WT.attrs.pop("standard_name")
    ds.WT.attrs["units"] = "Pa s-1"
    ds.to_netcdf(tmp_path / "input.nc")
    original = (tmp_path / "input.nc").read_bytes()
    conf = configuration(tmp_path, {
        "variables": {"3d": {
            "level_w": {"names": ["WT"], "levels": {"indices": [2, 0]}},
            "level": {"names": [companion],
                      "levels": {"indices": [1] if conflicting else [2, 0]}},
        }},
        "transforms": [{"fields": ["level_w.WT"], "sampling": "mass"}],
        "time": {"values": ["2024-01-01T01:00:00"]},
    })
    if conflicting:
        from frameit.core.coupled import bind_sources

        guard_netcdf_payloads(monkeypatch, {"WT", companion})
        with pytest.raises(ValueError, match="different group.*same output axis"):
            bind_sources(conf)
        assert conf.source_requests["atmosphere"]["binding"] is None
        assert not conf.output_dir.exists()
        return
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        w, other = out["level_w.WT"], out[f"level.{companion}"]
        np.testing.assert_array_equal(w[w.dims[1]], [15., -5.])
        assert w.dims[1] == other.dims[1]
        np.testing.assert_array_equal(other[other.dims[1]], [15., -5.])
        np.testing.assert_array_equal(w[0, :, 0, 0], [414., 198.])
        np.testing.assert_array_equal(other, 300. if companion == "THT" else 10.8)
        assert w.attrs["units"] == "Pa s-1"
        assert other.attrs["source_variable_name"] == companion
    assert (tmp_path / "input.nc").read_bytes() == original


def test_grouped_polar_speed_keeps_magnitude_after_component_sampling(tmp_path):
    from frameit.testing.numerical.test_v3_polar import configuration, ordinary_reader, scene

    ds = scene()
    u = np.full(ds.q.shape, 3.)
    u[:, :, 5:] = -3.
    for name, data, standard in (
            ("U", u, "eastward_wind"), ("V", np.full(ds.q.shape, 4.), "northward_wind")):
        ds[name] = ds.q.copy(data=data).expand_dims(level=[10.], axis=1).assign_attrs(
            units="m s-1", kind="continuous", standard_name=standard)
    ds.level.attrs.update(axis="Z", units="m")
    ds.to_netcdf(tmp_path / "input.nc")
    original = (tmp_path / "input.nc").read_bytes()
    conf = configuration(tmp_path, source={
        "variables": {"3d": {"level": {"names": ["U", "V"], "levels": {"indices": [0]}}}},
        "derived": {"speed": {"method": "wind_speed", "inputs": {"u": "level.U", "v": "level.V"}}},
        "time": {"values": ["2024-01-01T01:00:00"]},
    }, region={"center": {"latitude": -20., "longitude": float(
        (ds.longitude[4, 4] + ds.longitude[4, 5]) / 2)}},
        products={"model_grid": {"fields": {"atmosphere": ["speed"]}},
                  "polar": {"radius_km": 2.5, "azimuth_count": 8,
                            "fields": {"atmosphere": ["speed", "level.U"]},
                            "field_options": {"atmosphere": {
                                "level.U": {"interpolation": "bilinear"}}}}})
    result = execute_simulation(conf)
    for item in result.products:
        with xr.open_dataset(item["path"]) as out:
            if item["role"] == "model_grid":
                np.testing.assert_allclose(out.speed, 5., atol=1e-12)
            else:
                np.testing.assert_allclose(out.speed.isel(radius=0), 4., atol=1e-8)
                assert out.speed.attrs["derivation"] == "magnitude_of_sampled_components"
                assert "level.U_interpolation_status" in out
                assert out["level.U"].shape[1] == 1
                ordinary_reader(item["path"], fields=["speed", "level.U"],
                                origin_values={"speed": [[4.]], "level.U": [[0.]]})
    dependencies = conf.source_requests["atmosphere"]["binding"]["dependencies"]
    assert set(dependencies) == {"level.U", "level.V"}
    assert (tmp_path / "input.nc").read_bytes() == original


def test_frozen_arome_mixed_groups_preserve_original_level_choices(tmp_path, monkeypatch):
    import eccodes as ec

    root = os.environ.get("FRAMEIT_CI_DATA_ROOT")
    if not root:
        pytest.skip("requires the separately supplied frozen CI fixture")
    files = sorted((Path(root) / "AROME" / "BATSIRAI").glob("*.grib"))
    assert len(files) == 5
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    raw = grouped_document(tmp_path)
    source = raw["sources"]["atmosphere"]
    source.update(files=[str(path) for path in files], time={"values": [
        "2022-02-01T06:00:00", "2022-02-01T18:00:00"]})
    source["variables"].pop("2d")
    source.pop("wind_pairs")
    source.pop("derived")
    reads = []
    original_values = ec.codes_get_values

    def observed(handle):
        reads.append(tuple(ec.codes_get(handle, key) for key in (
            "typeOfLevel", "shortName", "validityDate", "validityTime")))
        return original_values(handle)

    monkeypatch.setattr(ec, "codes_get_values", observed)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf)
    assert result.ok and len(result.products) == 1
    assert len(reads) == 24
    assert all(group in {"heightAboveGround", "isobaricInhPa"} and name in {"u", "v"}
               and date == 20220201 and clock in {600, 1800}
               for group, name, date, clock in reads)
    subprocess.run([sys.executable, "-c", """
import datetime, json, sys, eccodes as ec, numpy as np, xarray as xr
selected = {'2022-02-01T06:00:00', '2022-02-01T18:00:00'}
records = {}
for path in json.loads(sys.argv[2]):
    with open(path, 'rb') as stream:
        while (h := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                if not all(ec.codes_is_defined(h, k) for k in ('typeOfLevel', 'shortName')):
                    continue
                group, name = (ec.codes_get(h, k) for k in ('typeOfLevel', 'shortName'))
                if name not in ('u', 'v') or group not in ('heightAboveGround', 'isobaricInhPa'):
                    continue
                date = str(ec.codes_get(h, 'validityDate'))
                clock = str(ec.codes_get(h, 'validityTime')).zfill(4)
                stamp = datetime.datetime.strptime(date+clock, '%Y%m%d%H%M').isoformat()
                if stamp not in selected:
                    continue
                level = ec.codes_get(h, 'level')
                values = ec.codes_get_values(h)
                if ec.codes_get(h, 'bitmapPresent'):
                    values = np.where(ec.codes_get_array(h, 'bitmap'), values, np.nan)
                shape = (ec.codes_get(h, 'Nj'), ec.codes_get(h, 'Ni'))
                values = (values.reshape(shape[::-1]).T if ec.codes_get(h, 'jPointsAreConsecutive')
                          else values.reshape(shape))
                key = stamp, group, name, level
                assert key not in records
                records[key] = values
            finally:
                ec.codes_release(h)
with xr.open_dataset(sys.argv[1]) as ds:
    assert set(ds.data_vars) == {
        'heightAboveGround.u', 'heightAboveGround.v', 'isobaric.u', 'isobaric.v'}
    for group, native_group, axis in (
        ('heightAboveGround', 'heightAboveGround', 'height_above_ground'),
        ('isobaric', 'isobaricInhPa', 'pressure'),
    ):
        for name in ('u', 'v'):
            available = sorted({k[3] for k in records if k[1:3] == (native_group, name)})
            levels = ([available[i] for i in (0, 2, 5)] if axis == 'height_above_ground'
                      else [1000,850,400])
            field = ds[group+'.'+name]
            assert field.dims == ('time', axis, 'y', 'x')
            np.testing.assert_array_equal(field[axis], levels)
            for t, stamp in enumerate(sorted(selected)):
                for z, level in enumerate(levels):
                    np.testing.assert_array_equal(
                        field[t,z], records[stamp,native_group,name,level])
    assert ds.pressure.attrs['units'] == 'hPa'
    assert ds.height_above_ground.attrs['units'] == 'm'
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], json.dumps([str(path) for path in files])],
                   check=True, capture_output=True, text=True)
    assert {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files} == before


def test_grouped_stored_name_cannot_replace_required_native_support(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads
    from frameit.testing.numerical.test_request_selection import binding_scene

    ds = binding_scene().assign_coords({"level.T": 42.})
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = {"schema_version": 3, "sources": {"atmosphere": {
        "model": "mesonh", "files": str(tmp_path / "input.nc"),
        "variables": {"3d": {"level": {"names": ["T"]}}},
    }}, "output": {"directory": str(tmp_path / "out")}}
    guard_netcdf_payloads(monkeypatch, {"T", "level.T"})
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="collid"):
        inventory_source(conf, "atmosphere")
        bind_source(conf, "atmosphere")
    assert conf.source_requests["atmosphere"]["binding"] is None
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("forged", ["invented.u", "isobaric.v", "unrequested_alias"])
def test_grouped_grib_reader_still_checks_reference_against_native_identity(
        tmp_path, monkeypatch, forged):
    import eccodes as ec

    from frameit.io.grib_utils import concat_grib2ds_by_vert_coord
    from frameit.io.loader import DatasetResources

    path, raw = grib_document(tmp_path)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    source = inventory_source(conf, "atmosphere")
    binding = deepcopy(bind_source(conf, "atmosphere"))
    binding["products"] = {"model_grid": {
        forged: binding["products"]["model_grid"]["heightAboveGround.u"]}}
    monkeypatch.setattr(ec, "codes_get_values", lambda *a, **kw: pytest.fail("scientific read"))
    with DatasetResources() as resources, pytest.raises(ValueError, match="closed inventory"):
        concat_grib2ds_by_vert_coord([path], {}, {}, resources=resources,
                                    selected_records=binding, source_plan=source)


def test_grouped_wrong_category_repair_uses_a_valid_native_2d_name(tmp_path):
    _, raw = grib_document(tmp_path, extra=[
        {"hour": hour, "group": "heightAboveGround", "level": 10} for hour in (1, 2)])
    raw["sources"]["atmosphere"]["variables"] = {
        "3d": {"heightAboveGround": {"names": ["u10"]}}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    inventory_source(conf, "atmosphere")
    with pytest.raises(ValueError, match=r"variables: \{2d: \[u10\]\}"):
        bind_source(conf, "atmosphere")


@pytest.mark.parametrize("grouped", [False, True])
def test_fa_physical_selection_rejection_keeps_local_path_and_cli_json(tmp_path, grouped):
    from frameit.core.reports import PreflightError
    from frameit.testing.numerical.test_configuration_v3 import fa_document

    raw = fa_document()
    source = raw["sources"].pop("native")
    raw["sources"]["atmosphere"] = source
    selector = {"domain": "physical"}
    source["variables"] = (
        {"3d": {"level": {"names": ["temperature"], "levels": selector}}} if grouped
        else {"3d": ["temperature"], "levels": selector})
    path = ("sources.atmosphere.variables.3d.level.levels" if grouped
            else "sources.atmosphere.variables.levels")
    with pytest.raises(PreflightError) as caught:
        resolve_schema(raw, base_dir=tmp_path)
    diagnostic, = caught.value.diagnostics
    assert diagnostic.path == path
    assert diagnostic.observed == selector
    assert "gated" in diagnostic.message
    assert all(path in repair for repair in diagnostic.repairs)
    document = tmp_path / "fa.yaml"
    document.write_text(yaml.safe_dump(raw))
    result = subprocess.run([
        sys.executable, "-m", "frameit", "validate", str(document), "--schema-only", "--json",
    ], capture_output=True, text=True)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert set(report) == {
        "report_version", "command", "status", "data", "warnings", "errors", "deferred_checks",
    }
    assert report["report_version"] == 1
    assert report["command"] == "validate" and report["status"] == "error"
    error, = report["errors"]
    assert error["path"] == path and error["observed"] == selector
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("grouped", [False, True])
def test_tracker_support_keeps_native_keys_and_levels_with_grouped_export(
        tmp_path, monkeypatch, grouped):
    from frameit.core.coupled import bind_sources
    from frameit.processing.requests import bind_requests
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads
    from frameit.testing.numerical.test_pressure_centroid_mnh import native_vortex
    from frameit.testing.numerical.test_v3_regions import configuration

    ds, _ = native_vortex(n=81)
    ds.to_netcdf(tmp_path / "native.nc")
    before = (tmp_path / "native.nc").read_bytes()
    conf = configuration(tmp_path, {"atmosphere": {
        "model": "mesonh", "files": "./native.nc",
        "variables": (
            {"3d": {"level": {"names": ["PABST"], "levels": {"indices": [1]}}}} if grouped
            else {"3d": ["PABST"], "levels": {"indices": [1]}}),
        "wind_pairs": [{"u": "UT_ZM", "v": "VT_ZM", "basis": "earth"},
                       {"u": "UM10", "v": "VM10", "basis": "earth"}]}},
        region={"tracker": {"method": "pressure_centroid"}},
        products={"model_grid": True, "track": True})
    with monkeypatch.context() as guard:
        guard_netcdf_payloads(guard, {"PABST", "UT_ZM", "VT_ZM", "UM10", "VM10", "MSLP"})
        _, children, sources = bind_sources(conf)
    request = children["atmosphere"].source_requests["atmosphere"]
    binding = request["binding"]
    assert binding["status"] == "bound"
    reference = "level.PABST" if grouped else "PABST"
    exported = binding["products"]["model_grid"][reference]
    internal = binding["dependencies"]["PABST"]
    assert exported["field_id"] == internal["field_id"]
    assert all(record["source_positions"] == [1] for record in exported["records"])
    assert all(record["source_positions"] == [0, 1] for record in internal["records"])
    assert set(binding["dependencies"]) >= {"PABST", "UT_ZM", "VT_ZM", "UM10", "VM10", "MSLP"}
    if grouped:
        authored = deepcopy(request)
        authored["internal_inputs"].append("PABST")
        with pytest.raises(ValueError, match="duplicate field request by resolved identity"):
            bind_requests(sources["atmosphere"], authored, required_inputs={"PABST": {}})
    assert not conf.output_dir.exists()
    if grouped:
        result = execute_simulation(conf)
        product = next(p["path"] for p in result.products if p["role"] == "model_grid")
        with xr.open_dataset(product) as out:
            assert set(out.data_vars) == {"level.PABST"}
            np.testing.assert_array_equal(out["level.PABST"], ds.PABST.isel(level=[1]))
        track = next(p["path"] for p in result.products if p["role"] == "track")
        with xr.open_dataset(track) as out:
            np.testing.assert_allclose(out.longitude, 60, atol=.01)
            np.testing.assert_allclose(out.latitude, -20, atol=.01)
    assert (tmp_path / "native.nc").read_bytes() == before


def test_grouped_croco_transform_keeps_native_current_preparation(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.core.coupled import bind_sources
    from frameit.testing.numerical.test_croco_vectors import vector_scene
    from frameit.testing.numerical.test_v3_operations import configuration, ordinary_reader

    ds = vector_scene()
    ds.mask_rho.values[3, 2] = 0
    ds.u.values[1, 1, 4, 3] = 0.
    ds.v.values[1, 1, 4, 4] = 0.
    ds.to_netcdf(tmp_path / "input.nc")
    before = (tmp_path / "input.nc").read_bytes()
    conf = configuration(tmp_path, {
        "model": "croco",
        "variables": {"3d": {"s_rho": {"names": ["u"], "levels": {"indices": [1]}}}},
        "wind_pairs": [{"u": "s_rho.u", "v": "s_rho.v", "basis": "grid",
                        "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        "transforms": [{"fields": ["s_rho.u"], "sampling": "mass",
                        "basis": "earth", "units": "m s-1"}],
        "time": {"values": [str(ds.time.values[1])]},
    })
    reads = []
    original_get = H5NetCDFArrayWrapper.__getitem__

    def selected(array, key):
        if array.variable_name in {"u", "v", "zeta"}:
            assert np.atleast_1d(np.arange(array.shape[0])[key.tuple[0]]).tolist() == [1]
            if array.variable_name in {"u", "v"}:
                assert np.atleast_1d(np.arange(array.shape[1])[key.tuple[1]]).tolist() == [1]
            reads.append(array.variable_name)
        if array.variable_name in {"temp", "salt"}:
            pytest.fail("Unrequested scientific field was read")
        return original_get(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", selected)
    _, children, _ = bind_sources(conf)
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    assert not reads and binding["status"] == "bound"
    assert {"s_rho.u", "s_rho.v"} <= binding["dependencies"].keys()
    result = execute_simulation(conf)
    with xr.open_dataset(result.products[0]["path"]) as out:
        assert set(out.data_vars) == {"s_rho.u"}
        u = out["s_rho.u"]
        assert u.dims == ("time", "s_rho", "y_rho", "x_rho")
        np.testing.assert_array_equal(out.xi_rho_source_coordinate, ds.xi_rho)
        np.testing.assert_array_equal(out.eta_rho_source_coordinate, ds.eta_rho)
        np.testing.assert_allclose(u[0, 0, 2, 4], -4., atol=1e-12)
        assert np.isnan(u[0, 0, 3, 3]) and np.isnan(u[0, 0, 0]).all()
        assert u.attrs["current_reference_frame"] == "earth"
        assert u.attrs["source_variable_name"] == "u"
        assert all(n in out for n in out.s_rho.attrs["formula_terms"].split()[1::2])
    ordinary_reader(result.products[0]["path"], {
        "s_rho.u": {"attrs": {"units": "m s-1", "current_reference_frame": "earth"}}})
    assert set(reads) == {"u", "v", "zeta"}
    assert (tmp_path / "input.nc").read_bytes() == before


def test_authored_operation_aliases_cannot_become_generated_support(tmp_path, monkeypatch):
    from frameit.core.coupled import bind_sources
    from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads
    from frameit.testing.numerical.test_v3_operations import configuration, scene

    ds = scene()
    ds.U.attrs.pop("standard_name")
    ds.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, {
        "variables": {"3d": {"level": {"names": ["U"]}}},
        "wind_pairs": [{"u": "level.U", "v": "U", "basis": "earth"}],
        "derived": {"speed": {
            "method": "wind_speed", "inputs": {"u": "level.U", "v": "U"}}},
    }, products={"model_grid": {"fields": {"atmosphere": ["speed"]}}})
    guard_netcdf_payloads(monkeypatch, {"U", "V"})
    with pytest.raises(ValueError, match="duplicate field request by resolved identity"):
        bind_sources(conf)
    assert conf.source_requests["atmosphere"]["binding"] is None
    assert not conf.output_dir.exists()
