"""Inspect exposes source evidence without selecting a basis or reading fields."""

from copy import deepcopy
from pathlib import Path

import dask.array as da
import numpy as np
import pytest
import xarray as xr
import yaml
from dask import delayed

from frameit.cli import _build_parser, _cmd_inspect
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources
from frameit.testing.numerical.test_configuration_v2_1 import dataset


@pytest.mark.parametrize("attrs,dataset_attrs,basis", [
    ({}, {}, "unknown"),
    ({"standard_name": "air_temperature"}, {}, "unknown"),
    ({"standard_name": "eastward_wind"}, {}, "eastward/northward components"),
    ({"standard_name": "northward_wind"}, {}, "eastward/northward components"),
    ({"standard_name": "x_wind"}, {}, "grid-aligned components"),
    ({"standard_name": "grid_northward_wind"}, {}, "grid-aligned components"),
    ({"GRIB_uvRelativeToGrid": np.int32(0)}, {}, "eastward/northward components"),
    ({"uvRelativeToGrid": "1"}, {}, "grid-aligned components"),
    ({}, {"wind_reference_frame": "earth"}, "eastward/northward components"),
    ({"standard_name": "x_wind"}, {"wind_reference_frame": "grid"},
     "grid-aligned components"),
    ({"standard_name": "eastward_wind", "GRIB_uvRelativeToGrid": 1}, {},
     "conflicting metadata"),
    ({"uvRelativeToGrid": 1, "GRIB_uvRelativeToGrid": 0}, {}, "conflicting metadata"),
    ({"standard_name": "x_wind"}, {"wind_reference_frame": "earth"},
     "conflicting metadata"),
    ({"GRIB_uvRelativeToGrid": 2}, {}, "invalid metadata"),
    ({"wind_reference_frame": "auto"}, {}, "invalid metadata"),
    ({"standard_name": ["eastward_wind"]}, {}, "invalid metadata"),
])
def test_wind_metadata_interpretation_retains_evidence_without_mutating(
    attrs, dataset_attrs, basis,
):
    from frameit.processing.wind_reference import inspect_wind_metadata

    before = deepcopy((attrs, dataset_attrs))
    result = inspect_wind_metadata(attrs, dataset_attrs)
    assert result["wind_basis"] == basis
    assert result["attributes"] == attrs
    assert result.get("dataset_attributes", {}) == dataset_attrs
    assert (attrs, dataset_attrs) == before
    assert yaml.safe_load(yaml.safe_dump(result)) == result
    if basis == "invalid metadata":
        assert result["wind_metadata_error"]


def test_metadata_report_keeps_numpy_values_portable_without_dumping_other_attributes():
    from frameit.processing.wind_reference import inspect_wind_metadata

    result = inspect_wind_metadata({
        "units": "m s-1", "GRIB_uvRelativeToGrid": np.array([0, 1]),
        "unrelated_private_note": "not part of the public report",
    }, {})
    assert result["attributes"] == {"units": "m s-1", "GRIB_uvRelativeToGrid": [0, 1]}
    assert result["wind_basis"] == "invalid metadata"
    assert yaml.safe_load(yaml.safe_dump(result)) == result


def test_netcdf_inspect_keeps_file_context_and_reads_no_field_payloads(
    tmp_path, monkeypatch, capsys,
):
    source = dataset(tmp_path, name="first.nc")
    source.UM10.attrs.update(standard_name="eastward_wind", GRIB_uvRelativeToGrid=np.int32(0))
    source.VM10.attrs.update(standard_name="northward_wind")
    source["u"] = source.UM10.copy().assign_attrs(units="m s-1")
    source.u.attrs = {"units": "m s-1"}
    source.to_netcdf(tmp_path / "first.nc", engine="h5netcdf")
    source.attrs["wind_reference_frame"] = "grid"
    source.to_netcdf(tmp_path / "second.nc", engine="h5netcdf")
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in tmp_path.glob("*.nc")}
    for path in before:
        path.chmod(0o444)

    original_open = DatasetResources.open_netcdf

    def forbidden():
        raise AssertionError("Inspection evaluated a field payload")

    def guarded_open(self, *args, **kwargs):
        opened = original_open(self, *args, **kwargs)
        for name in opened.data_vars:
            opened[name].data = da.from_delayed(delayed(forbidden)(),
                                              shape=opened[name].shape, dtype=opened[name].dtype)
        return opened

    monkeypatch.setattr(DatasetResources, "open_netcdf", guarded_open)
    args = _build_parser().parse_args([
        "inspect", str(tmp_path), "--model", "mesonh", "--format", "netcdf", "--pattern", "*.nc",
    ])
    assert _cmd_inspect(args) == 0
    report = yaml.safe_load(capsys.readouterr().out)
    assert report["configuration"]["input"]["wind_pairs"] == []
    assert report["wind_provenance"] == []
    first, second = report["inputs"]
    assert first["path"].endswith("first.nc") and second["path"].endswith("second.nc")
    assert first["variables"]["UM10"] == "m s-1"
    fields = {record["name"]: record for record in first["variable_metadata"]}
    assert set(fields) == set(source.data_vars)
    assert fields["UM10"]["attributes"] == {
        "units": "m s-1", "standard_name": "eastward_wind", "GRIB_uvRelativeToGrid": 0,
    }
    assert fields["UM10"]["wind_basis"] == "eastward/northward components"
    assert fields["u"]["wind_basis"] == "unknown"
    fields = {record["name"]: record for record in second["variable_metadata"]}
    assert fields["UM10"]["wind_basis"] == "conflicting metadata"
    assert fields["UM10"]["dataset_attributes"] == {"wind_reference_frame": "grid"}
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before} == before
    assert set(tmp_path.iterdir()) == set(before)


def test_ordinary_preflight_does_not_add_inspection_metadata(tmp_path):
    dataset(tmp_path)
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": "2.1", "model": "mesonh",
        "input": {"directory": str(tmp_path), "pattern": "native.nc", "format": "netcdf"},
        "tracking": {"method": "fixed_box", "fixed_box": {
            "center": {"latitude": -20., "longitude": 60.}}},
    })
    report = preflight(conf, check_output=False)
    assert all("variable_metadata" not in item for item in report["inputs"])


def test_grib_inspect_preserves_same_name_in_different_groups_without_payload_reads(
    tmp_path, monkeypatch, capsys,
):
    ec = pytest.importorskip("eccodes")
    path = tmp_path / "wind.grib"
    with path.open("wb") as stream:
        for group, level, flag in (("isobaricInhPa", 850, 1), ("hybrid", 1, 0)):
            message = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
            try:
                for key, value in {
                    "Ni": 3, "Nj": 3, "latitudeOfFirstGridPointInDegrees": -20.02,
                    "latitudeOfLastGridPointInDegrees": -20.,
                    "longitudeOfFirstGridPointInDegrees": 60.,
                    "longitudeOfLastGridPointInDegrees": 60.02, "iDirectionIncrementInDegrees": .01,
                    "jDirectionIncrementInDegrees": .01, "jScansPositively": 1,
                    "dataDate": 20240101, "dataTime": 0, "paramId": 131,
                    "typeOfLevel": group, "level": level, "uvRelativeToGrid": flag,
                }.items():
                    ec.codes_set(message, key, value)
                ec.codes_set_values(message, np.ones(9))
                ec.codes_write(message, stream)
            finally:
                ec.codes_release(message)
    path.chmod(0o444)
    original_array = ec.codes_get_array

    def forbidden(*args, **kwargs):
        raise AssertionError("Inspection decoded GRIB field values")

    def guarded_array(handle, key, *args, **kwargs):
        if key in {"values", "codedValues"}:
            forbidden()
        return original_array(handle, key, *args, **kwargs)

    monkeypatch.setattr(ec, "codes_get_values", forbidden)
    monkeypatch.setattr(ec, "codes_get_array", guarded_array)
    args = _build_parser().parse_args([
        "inspect", str(tmp_path), "--model", "arome", "--format", "grib", "--pattern", "*.grib",
    ])
    assert _cmd_inspect(args) == 0
    report = yaml.safe_load(capsys.readouterr().out)
    assert report["inputs"][0]["variables"] == {"u": "m s**-1"}
    records = report["inputs"][0]["variable_metadata"]
    assert [(r["name"], r["group"], r["attributes"]["GRIB_uvRelativeToGrid"], r["wind_basis"])
            for r in records] == [
        ("u", "isobaricInhPa", 1, "grid-aligned components"),
        ("u", "hybrid", 0, "eastward/northward components"),
    ]
    assert list(tmp_path.iterdir()) == [path]


def v3_scene(*, names=("temperature",), hours=(0, 1, 2, 3), model="Meso-NH"):
    """Compact instructional metadata, not producer/scientific qualification."""
    times = np.datetime64("2026-01-01", "ns") + np.array(hours, dtype="timedelta64[h]")
    return xr.Dataset({
        name: (("time", "y", "x"), np.full((len(times), 2, 3), i + 1.),
               {"units": "K"}) for i, name in enumerate(names)
    }, coords={
        "time": ("time", times, {"standard_name": "time"}),
        "y": ("y", [0., 1.], {"units": "km"}),
        "x": ("x", [0., 1., 2.], {"units": "km"}),
        "latitude": ("y", [-20., -19.99], {"units": "degrees_north"}),
        "longitude": ("x", [60., 60.01, 60.02], {"units": "degrees_east"}),
    }, attrs={"model": model} if model else {})


def v3_config(tmp_path, files, *, names=("temperature",), time=None, **source):
    declaration = {"files": [str(p) for p in files],
                   "variables": {"2d": list(names)}, **source}
    if time is not None:
        declaration["time"] = time
    return SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3, "sources": {"weather": declaration},
        "output": {"directory": str(tmp_path / "out")},
    })


def guard_netcdf_payloads(monkeypatch, forbidden_names):
    """Observe the actual backend requests, not replacement lazy arrays."""
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper
    from xarray.backends.netCDF4_ import NetCDF4ArrayWrapper
    from xarray.backends.scipy_ import ScipyArrayWrapper

    reads = []
    for wrapper in (H5NetCDFArrayWrapper, NetCDF4ArrayWrapper, ScipyArrayWrapper):
        original = wrapper.__getitem__

        def guarded(array, key, original=original):
            reads.append((array.variable_name, key))
            assert array.variable_name not in forbidden_names, (
                f"Metadata inspection read scientific payload {array.variable_name}: {key}")
            return original(array, key)

        monkeypatch.setattr(wrapper, "__getitem__", guarded)
    return reads


@pytest.mark.parametrize("case", [
    "aliases", "copies", "field_split", "irrelevant", "unreadable", "shuffled",
    "excluded", "model_conflict", "unknown_model", "embedded_surfex", "two_atmospheres",
    "distinct_domains_members", "ambiguous_name", "derived_dependency", "dependency_excluded",
    "dependency_time_excluded", "independent_sources", "independent_calendars",
    "dependency_only_atmosphere", "unselected_competition", "unreadable_many",
    "wrong_nemo_clock", "wrong_croco_profile", "wrong_reader", "nested_derived",
    "irrelevant_no_clock",
    "scalar_path", "scalar_glob",
    "dynamic_tracker_candidates",
    "recursive_glob",
    "dependency_pool",
    "profile_conflict",
])
def test_v3_source_inventory(tmp_path, monkeypatch, case):
    import os
    import shutil

    from frameit.core.coupled import prepare_sources

    scene = v3_scene()
    first, second = tmp_path / "z-first.nc", tmp_path / "a-second.nc"
    scene.to_netcdf(first, engine="h5netcdf")
    files, names, kwargs = [first], ("temperature",), {}
    error = None
    if case == "aliases":
        alias, hard = tmp_path / "alias.nc", tmp_path / "hard.nc"
        alias.symlink_to(first)
        os.link(first, hard)
        files = [first, first, alias, hard, tmp_path / "*.nc"]
    elif case == "copies":
        shutil.copyfile(first, second)
        files.append(second)
        error = "competing.*provider|provider.*temperature"
    elif case in {"field_split", "irrelevant", "derived_dependency", "dependency_excluded",
                  "nested_derived", "irrelevant_no_clock"}:
        other = v3_scene(names=("salinity",))
        if case == "irrelevant_no_clock":
            other = other.isel(time=0, drop=True)
        other.to_netcdf(second, engine="h5netcdf")
        files.append(second)
        if case == "field_split":
            names = ("temperature", "salinity")
        elif case.startswith("dependency") or case in {"derived_dependency", "nested_derived"}:
            kwargs["derived"] = {"speed": {"method": "wind_speed",
                                           "inputs": {"u": "temperature", "v": "salinity"}}}
            names = ("temperature",)
            if case == "dependency_excluded":
                kwargs["exclude"] = [str(second)]
                error = "salinity.*selected|selected.*salinity"
            if case == "nested_derived":
                kwargs["derived"]["nested"] = {"method": "wind_speed",
                                               "inputs": {"u": "speed", "v": "temperature"}}
    elif case in {"unreadable", "unreadable_many"}:
        second.write_bytes(b"not a supported container")
        files.append(second)
        error = "a-second.nc"
        if case == "unreadable_many":
            third = tmp_path / "third.nc"
            third.write_bytes(b"also unreadable")
            files.append(third)
            error = "(?s)a-second.nc.*third.nc"
    elif case in {"shuffled", "excluded"}:
        v3_scene(hours=(4, 5)).to_netcdf(second, engine="h5netcdf")
        files = [second, first]
        if case == "excluded":
            kwargs["exclude"] = [str(second)]
    elif case == "model_conflict":
        kwargs["model"] = "nemo"
        error = "model.*conflict|conflict.*model"
    elif case == "unknown_model":
        v3_scene(model=None).to_netcdf(first, engine="h5netcdf")
        error = "model.*evidence|model.*declare"
    elif case == "embedded_surfex":
        scene = v3_scene(names=("SST",))
        scene.attrs["MNH_cleanly_closed"] = "yes"
        scene.to_netcdf(first, engine="h5netcdf")
        names = ("SST",)
    elif case == "distinct_domains_members":
        scene["other"] = (("time", "y", "x_other", "member"),
                          np.ones((4, 2, 4, 2)), {"units": "K"})
        scene = scene.assign_coords(x_other=[0, 1, 2, 3], member=[0, 1])
        scene.to_netcdf(first, engine="h5netcdf")
        names = ("temperature", "other")
    elif case == "ambiguous_name":
        other = v3_scene().rename(x="x_other").assign_coords(x_other=[1., 2., 3.])
        other.to_netcdf(second, engine="h5netcdf")
        files.append(second)
        error = "distinct fields.*temperature|temperature.*ambiguous"
    elif case == "dependency_time_excluded":
        scene.temperature.attrs["ancillary_variables"] = "quality"
        scene.to_netcdf(first, engine="h5netcdf")
        v3_scene(names=("quality",), hours=(4,)).to_netcdf(second, engine="h5netcdf")
        files.append(second)
        kwargs["time"] = {"values": ["2026-01-01T01:00:00"]}
        error = "quality.*selected|selected.*quality"
    elif case == "unselected_competition":
        v3_scene(hours=(3, 4)).to_netcdf(second, engine="h5netcdf")
        files.append(second)
        kwargs["time"] = {"values": ["2026-01-01T04:00:00"]}
    elif case in {"wrong_nemo_clock", "wrong_croco_profile"}:
        v3_scene(model="NEMO" if case == "wrong_nemo_clock" else "CROCO").to_netcdf(
            first, engine="h5netcdf")
        error = "NEMO.*time_counter" if case == "wrong_nemo_clock" else "CROCO.*history"
    elif case == "wrong_reader":
        ec = pytest.importorskip("eccodes")
        message = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
        try:
            with first.open("wb") as stream:
                ec.codes_write(message, stream)
        finally:
            ec.codes_release(message)
        kwargs.update(reader={"engine": "h5netcdf"}, model="arome")
        error = "reader.*NetCDF-only"
    elif case == "dynamic_tracker_candidates":
        v3_scene(names=("salinity",), hours=(1,)).to_netcdf(second, engine="h5netcdf")
        files.append(second)
        third = tmp_path / "candidate-copy.nc"
        v3_scene(names=("salinity",), hours=(1,)).to_netcdf(third, engine="h5netcdf")
        files.append(third)
    elif case == "recursive_glob":
        second = tmp_path / "nested" / "deeper" / "part.nc"
        second.parent.mkdir(parents=True)
        v3_scene(hours=(4, 5)).to_netcdf(second, engine="h5netcdf")
        files = [tmp_path / "**" / "*.nc"]
    elif case == "dependency_pool":
        scene = v3_scene(names=("u",))
        scene.u.attrs["units"] = "m s-1"
        scene.to_netcdf(first, engine="h5netcdf")
        other = v3_scene(names=("v", "angle"), hours=(1, 4))
        other.v.attrs["units"] = "m s-1"
        other.angle.attrs["units"] = "rad"
        other.to_netcdf(second, engine="h5netcdf")
        files.append(second)
        names = ("u",)
        kwargs["wind_pairs"] = [{
            "u": "u", "v": "v", "basis": "grid",
            "rotation": {"method": "coordinate", "coordinate": "angle"},
        }]
        kwargs["transforms"] = [{"fields": ["u"], "basis": "earth"}]
    elif case == "profile_conflict":
        kwargs["profile"] = "arome_history"
        error = "format.*conflict|profile.*conflict"

    conf = v3_config(tmp_path, files, names=names, **kwargs)
    if case in {"scalar_path", "scalar_glob"}:
        raw = deepcopy(conf.yaml_config)
        raw["sources"]["weather"]["files"] = str(
            first if case == "scalar_path" else tmp_path / "*.nc")
        conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if case == "dynamic_tracker_candidates":
        raw = deepcopy(conf.yaml_config)
        raw["region"] = {"tracker": {"method": "pressure_centroid"}}
        conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if case in {"two_atmospheres", "independent_sources", "independent_calendars",
                "dependency_only_atmosphere"}:
        raw = deepcopy(conf.yaml_config)
        if case == "two_atmospheres":
            raw["sources"]["not_an_ocean"] = deepcopy(raw["sources"]["weather"])
            error = "one source.*atmosphere|atmosphere.*weather.*not_an_ocean"
        else:
            ocean = v3_scene(hours=(7, 9), names=("salt",), model="NEMO").rename(
                time="time_counter")
            ocean = ocean.drop_vars(["latitude", "longitude"]).assign_coords(
                nav_lat=(("y", "x"), np.broadcast_to([[-20.], [-19.99]], (2, 3)),
                         {"units": "degrees_north", "standard_name": "latitude"}),
                nav_lon=(("y", "x"), np.broadcast_to([[60., 60.01, 60.02]], (2, 3)),
                         {"units": "degrees_east", "standard_name": "longitude"}))
            ocean = ocean.assign_coords(forecast_reference_time=np.datetime64("2025-12-31"))
            if case == "independent_calendars":
                import cftime
                ocean = ocean.assign_coords(
                    time_counter=[cftime.Datetime360Day(2001, 2, 30),
                                  cftime.Datetime360Day(2001, 3, 1)],
                    forecast_reference_time=cftime.Datetime360Day(2001, 2, 1))
            ocean.to_netcdf(second, engine="h5netcdf")
            raw["sources"]["not_atmosphere"] = {
                "files": [str(second)], "variables": {"2d": ["salt"]},
            }
            if case == "dependency_only_atmosphere":
                # No public child document can express this unexported source.
                v3_scene(names=("MSLP", "UM10", "VM10")).to_netcdf(first, engine="h5netcdf")
                raw["sources"]["weather"]["variables"] = {}
                raw["products"] = {"model_grid": {"fields": {"not_atmosphere": ["salt"]}}}
                raw["region"] = {"tracker": {"method": "pressure_wind"}}
        conf = SimulationConfig.from_mapping_with_model_preset(raw)
    origins = deepcopy(conf.schema_sources)
    authored = deepcopy(conf.yaml_config)
    guard_netcdf_payloads(monkeypatch, {
        "temperature", "salinity", "other", "SST", "quality", "salt", "MSLP", "UM10", "VM10",
        "u", "v", "angle",
    })
    if error:
        with pytest.raises(ValueError, match=error):
            preflight(conf, check_output=False)
        assert not conf.output_dir.exists()
        return
    if case in {"independent_sources", "independent_calendars", "dependency_only_atmosphere"}:
        report, children, _ = prepare_sources(conf, check_output=False)
        assert children["weather"].schema_sources["output.directory"] == origins["output.directory"]
        assert (children["not_atmosphere"].schema_sources["output.directory"]
                == origins["output.directory"])
        assert "time_alignment" not in report and conf.tracking_source is None
        ocean = report["sources"]["not_atmosphere"]
        assert ocean["physical_type"] == "ocean"
        if case == "independent_calendars":
            assert [t.day for t in ocean["selected_times"]] == [30, 1]
            assert {r["calendar"] for r in ocean["records"]} == {"360_day"}
        else:
            assert [str(t)[:13] for t in ocean["selected_times"]] == [
                "2026-01-01T07", "2026-01-01T09"]
        if case == "dependency_only_atmosphere":
            child = children["weather"]
            assert child.yaml_config["products"] == {}
            assert child.simulation_parameter["request_plan"]["products"] == []
            assert {r["name"] for r in report["sources"]["weather"]["records"]} == {
                "MSLP", "UM10", "VM10"}
    else:
        report = preflight(conf, check_output=False)
    source = conf.simulation_parameter["request_plan"]["sources"]["weather"]
    assert source["model"] == "mesonh" and source["physical_type"] == "atmosphere"
    assert source["format"] == "netcdf" and source["metadata_origins"]["model"]["evidence"]
    assert source["records"] and source["native_grids"]
    stamps = [r["time"] for r in source["records"]]
    assert stamps == sorted(stamps)
    for record in source["records"]:
        assert record["grid_id"] in source["native_grids"]
        assert record["field_id"] in source["fields"]
        locator = record["locator"]
        assert locator["format"] == "netcdf"
        assert Path(locator["path"]).is_file() and locator["variable"] == record["name"]
        assert locator["indexers"]["time"] in range(2 if case == "unselected_competition" else 4)
    if case == "aliases":
        assert len(source["files"]) == 1
        assert set(source["file_inventory"][0]["aliases"]) == {str(alias), str(hard)}
        assert source["overlapping_patterns"]
    if case == "field_split":
        assert {r["name"] for r in source["records"]} == {"temperature", "salinity"}
        assert len(source["native_grids"]) == 1
    if case in {"irrelevant", "irrelevant_no_clock"}:
        skipped = next(f for f in source["file_inventory"] if f["path"] == str(second))
        assert skipped["status"] == "irrelevant" and "no requested field" in skipped["reason"]
        assert source["files"] == [str(first)]
    if case in {"shuffled", "recursive_glob"}:
        assert source["files"] == [str(first), str(second)]
    if case == "excluded":
        assert source["excluded_files"] == [str(second)]
    if case in {"derived_dependency", "nested_derived"}:
        assert {r["name"] for r in source["records"]} == {"temperature", "salinity"}
        assert source["dependency_resolution"] == "pending_method_binding"
    if case == "embedded_surfex":
        interpreted = v3_config(tmp_path, files, names=("SST",),
                                interpretation="mesonh_surfex_sea")
        interpreted_source = preflight(interpreted, check_output=False)["sources"]["weather"]
        assert interpreted_source["dependency_resolution"] == "pending_method_binding"
    if case == "unselected_competition":
        assert source["files"] == [str(second)]
        assert source["selected_times"] == [np.datetime64("2026-01-01T04", "ns")]
    if case == "dynamic_tracker_candidates":
        assert source["dependency_resolution"] == "pending_method_binding"
        assert {r["name"] for r in source["records"]} == {"temperature", "salinity"}
        assert source["provider_conflicts"][0]["status"] == "pending_method_binding"
    if case == "dependency_pool":
        assert {r["name"] for r in source["records"]} == {"u"}
        candidates = source["record_inventory"]
        assert {r["name"] for r in candidates} == {"u", "v", "angle"}
        assert {r["time"] for r in candidates} <= set(source["selected_times"])
        assert all(r["time"] != np.datetime64("2026-01-01T04", "ns") for r in candidates)
        assert source["dependency_resolution"] == "pending_method_binding"
        pending = next(f for f in source["file_inventory"] if f["path"] == str(second))
        assert pending["status"] == "dependency_pending"
    assert conf.yaml_config == authored and conf.schema_sources == origins
    assert report["sources"]["weather"]["records"] == source["records"]
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("case,selection,hours,error", [
    ("all", {}, [0, 1, 2, 3], None),
    ("inclusive", {"start": "2026-01-01T01:00:00", "end": "2026-01-01T02:00:00"}, [1, 2], None),
    ("between_labels", {"start": "2026-01-01T00:30:00", "end": "2026-01-01T02:30:00"},
     [1, 2], None),
    ("values", {"values": ["2026-01-01T03:00:00", "2026-01-01T01:00:00"]}, [1, 3], None),
    ("stride", {"start": "2026-01-01T01:00:00", "stride": 2}, [1, 3], None),
    ("empty", {"start": "2026-01-02"}, [], "empty|no selected"),
    ("missing", {"values": ["2026-01-02"]}, [], "unavailable|not found"),
    ("calendar", {"values": ["2001-02-30"]}, [1], None),
    ("cycle_required", {}, [], "time.cycle"),
    ("cycle", {"cycle": "2025-12-31T00:00:00"}, [0, 1, 2, 3], None),
    ("missing_cycle", {"cycle": "2025-12-29T00:00:00"}, [], "cycle.*unavailable|cycle.*not found"),
    ("bounds", {"values": ["2026-01-01T01:00:00"]}, [1], None),
    ("unidentified_clocks", {}, [], "clock|forecast"),
    ("shuffled_labels", {}, [1, 3, 0, 2], None),
    ("duplicate_labels", {}, [], "competing.*provider"),
    ("fraction", {"values": ["2026-01-01T01:00:00.123456789"]}, [1], None),
    ("timezone", {"values": ["2026-01-01T02:00:00+01:00"]}, [1], None),
    ("multi_cycle_file", {"cycle": "2025-12-31"}, [0, 1, 2, 3], None),
    ("calendar_fraction", {"values": ["2001-02-30T00:00:00.0000001"]}, [], "unavailable|precision"),
    ("missing_reference", {}, [], "missing.*reference|missing.*forecast"),
    ("conflicting_bounds", {}, [], "bounds.*conflict|conflicting.*bounds"),
])
def test_v3_time_record_selection(tmp_path, monkeypatch, case, selection, hours, error):
    scene = v3_scene()
    if case in {"calendar", "calendar_fraction"}:
        import cftime
        scene = scene.assign_coords(time=[
            cftime.Datetime360Day(2001, 2, 29), cftime.Datetime360Day(2001, 2, 30),
            cftime.Datetime360Day(2001, 3, 1), cftime.Datetime360Day(2001, 3, 2),
        ])
    if "cycle" in case and case != "multi_cycle_file":
        scene = scene.assign_coords(forecast_reference_time=np.datetime64("2025-12-31"))
    if case == "multi_cycle_file":
        scene = scene.rename(time="step").drop_vars("step").expand_dims(cycle=2)
        scene = scene.assign_coords(
            valid_time=(("cycle", "step"), np.broadcast_to(v3_scene().time.values, (2, 4))),
            cycle=("cycle", np.array(["2025-12-30", "2025-12-31"], dtype="datetime64[ns]"),
                   {"standard_name": "forecast_reference_time"}))
    if case == "shuffled_labels":
        scene = scene.isel(time=[2, 0, 3, 1])
    if case == "duplicate_labels":
        scene = scene.assign_coords(time=scene.time.values[[0, 1, 1, 3]])
    if case == "fraction":
        scene = scene.assign_coords(time=scene.time.values + np.timedelta64(123456789, "ns"))
    if case == "missing_reference":
        scene = scene.assign_coords(forecast_reference_time=np.datetime64("NaT", "ns"))
    if case in {"bounds", "conflicting_bounds"}:
        scene["time_bounds"] = (("time", "nv"), scene.time.values[:, None] +
                                np.array([-1, 0], dtype="timedelta64[h]"))
        scene.time.attrs["bounds"] = "time_bounds"
        scene.temperature.attrs["cell_methods"] = "time: mean"
        scene.time.encoding["units"] = "hours since 2026-01-01"
        scene.time_bounds.encoding["units"] = "hours since 2026-01-01"
        if case == "conflicting_bounds":
            scene = scene.assign_coords(
                other_clock=("time", scene.time.values, {
                    "standard_name": "time", "bounds": "other_bounds"}))
            scene["other_bounds"] = scene.time_bounds + np.timedelta64(15, "m")
            scene.other_clock.encoding["units"] = "hours since 2026-01-01"
            scene.other_bounds.encoding["units"] = "minutes since 2026-01-01"
    if case == "unidentified_clocks":
        scene = scene.rename(time="valid_time")
        scene["time"] = np.datetime64("2025-12-31")
    path = tmp_path / "multi.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    files = [path]
    if "cycle" in case and case != "multi_cycle_file":
        second = tmp_path / "second-cycle.nc"
        scene.assign_coords(forecast_reference_time=np.datetime64("2025-12-30")).to_netcdf(
            second, engine="h5netcdf")
        files.append(second)
    reads = guard_netcdf_payloads(monkeypatch, {"temperature"})
    conf = v3_config(tmp_path, files, time=selection)
    if error:
        with pytest.raises(ValueError, match=error):
            preflight(conf, check_output=False)
        return
    report = preflight(conf, check_output=False)
    source = report["sources"]["weather"]
    records = source["records"]
    if case == "multi_cycle_file":
        assert [r["locator"]["indexers"] for r in records] == [
            {"cycle": 1, "step": i} for i in range(4)]
        np.testing.assert_array_equal([r["time"] for r in records], v3_scene().time.values)
        assert all(r["cycle"] == np.datetime64("2025-12-31") for r in records)
        return
    assert [r["locator"]["indexers"]["time"] for r in records] == hours
    np.testing.assert_array_equal([r["time"] for r in records], scene.time.values[hours])
    assert source["selected_times"] == [r["time"] for r in records]
    assert source["files"] == [str(path)]
    assert reads and all(name != "temperature" for name, _ in reads)
    if case == "calendar":
        assert all(r["calendar"] == "360_day" for r in records)
        assert records[0]["time"].day == 30
    if case == "cycle":
        assert all(r["cycle"] == np.datetime64("2025-12-31") for r in records)
    if case == "bounds":
        np.testing.assert_array_equal(records[0]["time_bounds"], np.array(
            ["2026-01-01T00", "2026-01-01T01"], dtype="datetime64[ns]"))
        assert records[0]["temporal_metadata"]["cell_methods"] == "time: mean"


@pytest.mark.parametrize("profile,physical,field", [
    ("arome_history", "atmosphere", "CLSTEMPERATURE"),
    ("surfex_history", "surface", "SFX.T2M"),
])
def test_v3_fa_inventory_uses_verified_profile_without_physical_reads(
    tmp_path, monkeypatch, profile, physical, field,
):
    import sys

    from frameit.testing.numerical.test_fa_io import NATIVE, fa_files

    if not NATIVE:
        pytest.skip("optional EPyGrAM FA stack not installed")
    paths = fa_files(tmp_path, hours=(2, 0, 1), profile=profile)
    helper = tmp_path / "metadata-python"
    helper.write_text(f"""#!{sys.executable}
import runpy, sys
from frameit.io import fa_epygram
def forbidden(*args, **kwargs):
    raise AssertionError("Metadata inspection requested a scientific FA payload")
fa_epygram.read_values = forbidden
sys.argv = [sys.argv[2], *sys.argv[3:]]
runpy.run_module("frameit.io.fa_worker", run_name="__main__")
""")
    helper.chmod(0o755)
    from frameit.io import fa_backend
    native = fa_backend.request_fa
    operations = []

    def guarded(request):
        operations.append(request["operation"])
        assert request["operation"] == "inspect"
        return native(request)

    monkeypatch.setattr(fa_backend, "request_fa", guarded)
    conf = v3_config(tmp_path, paths, names=(field,), profile=profile,
                     reader={"python_executable": str(helper)},
                     field_metadata={field: {"units": "K", "kind": "continuous",
                                             "temporal_kind": "instantaneous"}},
                     time={"values": ["2026-01-01T01:00:00"]})
    source = preflight(conf, check_output=False)["sources"]["weather"]
    assert source["physical_type"] == physical and source["profile"] == profile
    assert conf.fa_options["profile"] == profile
    assert (conf.name_time_dim, conf.name_lat_dim, conf.name_lon_dim) == ("time", "y", "x")
    assert source["metadata_origins"]["model"]["origin"] == (
        "yaml" if profile == "arome_history" else "input")
    assert len(source["records"]) == 1 and operations
    record = source["records"][0]
    assert record["name"] == field and record["locator"]["records"] == [field]
    assert record["locator"]["zone"] == [0, 9, 0, 7]
    assert record["locator"]["identity"][0] == Path(record["locator"]["path"]).stat().st_size
    assert record["time"] == np.datetime64("2026-01-01T01:00:00")
    assert record["cycle"] == np.datetime64("2026-01-01T00:00:00")
    assert record["grid_id"] in source["native_grids"]
    grid = source["native_grids"][record["grid_id"]]
    assert grid["dimensions"] == {"y": 7, "x": 9}
    assert {"x", "y", "latitude", "longitude", "source_i", "source_j", "crs"} <= (
        grid["coordinates"].keys())
    for axis, coordinate, size in (("x", "longitude", 9), ("y", "latitude", 7)):
        assert grid["coordinates"][coordinate]["dimensions"] == [axis]
        assert grid["coordinates"][coordinate]["values"].shape == (size,)
        np.testing.assert_array_equal(grid["coordinates"][coordinate]["values"],
                                      grid["coordinates"][axis]["values"])


@pytest.mark.parametrize("model,subdirectory,pattern,field,count", [
    ("mesonh", "MNH/CHIDO", "*.nc", "MSLP", 3),
    ("arome", "AROME/BATSIRAI", "*.grib", "prmsl", 5),
])
def test_v3_frozen_inventory_without_payload_reads(
    tmp_path, monkeypatch, model, subdirectory, pattern, field, count,
):
    from frameit.testing.datasets import ci_dataset_root

    paths = sorted((ci_dataset_root() / subdirectory).glob(pattern))
    if not paths:
        pytest.skip("frozen local CI fixture not configured")
    assert len(paths) == count
    if model == "mesonh":
        with xr.open_dataset(paths[0], engine="h5netcdf") as sample:
            geography = {n for n, value in sample.variables.items()
                         if value.attrs.get("standard_name") in {"latitude", "longitude"}}
            forbidden = set(sample.data_vars) - geography
        guard_netcdf_payloads(monkeypatch, forbidden)
    else:
        ec = pytest.importorskip("eccodes")
        original = ec.codes_get_array

        def no_values(*args, **kwargs):
            raise AssertionError("Frozen-fixture inspection decoded GRIB values")

        def guarded_array(handle, key, *args, **kwargs):
            if key in {"values", "codedValues"}:
                no_values()
            return original(handle, key, *args, **kwargs)

        monkeypatch.setattr(ec, "codes_get_values", no_values)
        monkeypatch.setattr(ec, "codes_get_array", guarded_array)
    conf = v3_config(tmp_path, paths[::-1], names=(field,), model=model, time={"stride": 2})
    source = preflight(conf, check_output=False)["sources"]["weather"]
    assert len(source["records"]) == (count + 1) // 2
    assert source["selected_times"] == sorted(source["selected_times"])
    assert source["physical_type"] == "atmosphere"
    assert source["records"][0]["name"] == field


def test_v3_fa_unknown_shape_stays_unknown(tmp_path, monkeypatch):
    from frameit.core.preflight import inventory_source
    from frameit.io import fa_backend
    from frameit.testing.numerical.test_fa_io import NATIVE, fa_files

    if not NATIVE:
        pytest.skip("optional EPyGrAM FA stack not installed")
    path = fa_files(tmp_path)[0]
    native = fa_backend.inspect_fa

    def unknown_shape(*args, **kwargs):
        # A metadata-boundary case, not a spectral decoder qualification fixture.
        info = native(*args, **kwargs)
        for descriptor in info["field_descriptors"].values():
            descriptor["native"].update(shape=None, representation="unknown")
        return info

    monkeypatch.setattr(fa_backend, "inspect_fa", unknown_shape)
    conf = v3_config(tmp_path, [path], names=("CLSTEMPERATURE",), model="arome", format="fa",
                     profile="arome_history")
    source = inventory_source(conf, "weather")
    selected = next(f for f in source["fields"].values() if f["name"] == "CLSTEMPERATURE")
    assert selected["dimensions"] is None
    assert selected["native_descriptor"]["native"]["shape"] is None


@pytest.mark.parametrize("case", ["available", "missing_time", "excluded_time", "duplicate",
                                 "same_file"])
def test_v3_coordinate_dependency_keeps_provider_and_selected_support(tmp_path, monkeypatch, case):
    import shutil

    science = v3_scene()
    science.temperature.attrs["ancillary_variables"] = "quality"
    support = v3_scene(names=("quality",), hours={
        "missing_time": (1,), "excluded_time": (4,),
    }.get(case, (1, 3))).set_coords("quality")
    first, second = tmp_path / "science.nc", tmp_path / "support.nc"
    if case == "same_file":
        science = science.assign_coords(quality=v3_scene(names=("quality",)).quality)
    science.to_netcdf(first, engine="h5netcdf")
    files = [first]
    if case != "same_file":
        support.to_netcdf(second, engine="h5netcdf")
        files.append(second)
    if case == "duplicate":
        copy = tmp_path / "support-copy.nc"
        shutil.copyfile(second, copy)
        files.append(copy)
    guard_netcdf_payloads(monkeypatch, {"temperature", "quality"})
    conf = v3_config(tmp_path, files, time={"values": [
        "2026-01-01T01:00:00", "2026-01-01T03:00:00",
    ]})
    error = ("competing.*provider" if case == "duplicate" else
             "quality.*selected" if case in {"missing_time", "excluded_time"} else None)
    if error:
        with pytest.raises(ValueError, match=error):
            preflight(conf, check_output=False)
        return
    source = preflight(conf, check_output=False)["sources"]["weather"]
    records = [r for r in source["records"] if r["name"] == "quality"]
    assert len(records) == 2
    assert [r["time"] for r in records] == [
        np.datetime64("2026-01-01T01"), np.datetime64("2026-01-01T03")]
    provider = first if case == "same_file" else second
    assert {r["locator"]["path"] for r in records} == {str(provider)}
    assert [r["locator"]["indexers"] for r in records] == [
        {"time": i} for i in ((1, 3) if case == "same_file" else (0, 1))]
    assert all(r in source["record_inventory"] for r in records)
    field = source["fields"][records[0]["field_id"]]
    assert field["role"] == "array" and field["xarray_coordinate"] is True
    assert next(f for f in source["file_inventory"] if f["path"] == str(provider))[
        "status"] == "selected"
    assert all("quality" not in grid["coordinates"] for grid in source["native_grids"].values())


@pytest.mark.parametrize("layout", ["transposed", "wrong_clock_dimension", "valid"])
def test_v3_time_bounds_require_clock_dimension_identity(tmp_path, monkeypatch, layout):
    scene = v3_scene(hours=(0, 1))
    values = scene.time.values[:, None] + np.array([-1, 0], dtype="timedelta64[h]")
    dims = {"transposed": ("nv", "time"), "wrong_clock_dimension": ("other_time", "nv"),
            "valid": ("time", "nv")}[layout]
    scene["time_bounds"] = (dims, values.T if layout == "transposed" else values)
    scene.time.attrs["bounds"] = "time_bounds"
    for name in ("time", "time_bounds"):
        scene[name].encoding["units"] = "hours since 2026-01-01"
    path = tmp_path / "bounds.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    guard_netcdf_payloads(monkeypatch, {"temperature"})
    conf = v3_config(tmp_path, [path])
    if layout != "valid":
        with pytest.raises(ValueError, match="bounds.*dimension|invalid.*bounds"):
            preflight(conf, check_output=False)
        return
    source = preflight(conf, check_output=False)["sources"]["weather"]
    np.testing.assert_array_equal([r["time_bounds"] for r in source["records"]], np.array([
        ["2025-12-31T23", "2026-01-01T00"], ["2026-01-01T00", "2026-01-01T01"],
    ], dtype="datetime64[ns]"))


@pytest.mark.parametrize("case,selection,positions", [
    ("window_zeroes", {"start": "2026-01-01T00:30:00.0000000000"}, [1, 2, 3]),
    ("values_zeroes", {"values": ["2026-01-01T01:00:00.123456789000"]}, [1]),
    ("timezone_zeroes", {"values": ["2026-01-01T02:00:00.0000000000+01:00"]}, [1]),
    ("cycle_zeroes", {"cycle": "2025-12-31T00:00:00.000000000000Z"}, [0, 1, 2, 3]),
    ("unsupported_precision", {"start": "2026-01-01T00:30:00.0000000001"}, []),
    ("unsupported_range", {"start": "999999-01-01T00:00:00.000000000"}, []),
    ("timezone_range", {"start": "1677-09-21T00:12:43+00:01"}, []),
])
def test_v3_timestamp_precision_is_checked_before_numpy_selection(
    tmp_path, monkeypatch, case, selection, positions,
):
    scene = v3_scene().assign_coords(forecast_reference_time=np.datetime64("2025-12-31"))
    if case == "values_zeroes":
        scene = scene.assign_coords(time=scene.time.values + np.timedelta64(123456789, "ns"))
    path = tmp_path / "precision.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    guard_netcdf_payloads(monkeypatch, {"temperature"})
    conf = v3_config(tmp_path, [path], time=selection)
    if not positions:
        with pytest.raises(ValueError, match="precision|representable|range"):
            preflight(conf, check_output=False)
        return
    source = preflight(conf, check_output=False)["sources"]["weather"]
    assert [r["locator"]["indexers"]["time"] for r in source["records"]] == positions
    np.testing.assert_array_equal(source["selected_times"], scene.time.values[positions])


@pytest.mark.parametrize("case", ["identical", "coefficient", "reference_pressure", "attributes",
                                 "physical_duplicate", "quality_duplicate", "missing_PS",
                                 "malformed_terms"])
def test_v3_field_split_coalesces_only_owning_grid_coordinate_metadata(tmp_path, monkeypatch, case):
    scenes = []
    shape = (4, 2, 2, 3)
    for name in ("temperature", "salinity"):
        scene = v3_scene(names=(name,))
        scene[name] = (("time", "lev", "y", "x"), np.ones(shape), {"units": "K"})
        scenes.append(scene.assign_coords(
            lev=("lev", [0, 1], {
                "standard_name": "atmosphere_hybrid_sigma_pressure_coordinate",
                "axis": "Z", "units": "1", "positive": "down",
                "formula_terms": "a: a b: b p0: p0 ps: PS"}),
            a=("lev", [.1, .2], {"units": "1"}),
            b=("lev", [.9, .8], {"units": "1"}),
            p0=((), 100000., {"units": "Pa"})))
    first, second = scenes
    first["PS"] = (("time", "y", "x"), np.full((4, 2, 3), 98000.), {"units": "Pa"})
    first = first.assign_coords(
        quality=(("time", "lev", "y", "x"), np.zeros(shape), {"flag_values": [0, 1]}))
    first.temperature.attrs["ancillary_variables"] = "quality"
    if case == "coefficient":
        second.a.data = np.array([.1, .3])
    elif case == "reference_pressure":
        second.p0.data = np.array(101325.)
    elif case == "attributes":
        second.b.attrs["long_name"] = "distinct producer definition"
    elif case == "physical_duplicate":
        second["temperature"] = (("time", "lev", "y", "x"), np.ones(shape),
                                 dict(first.temperature.attrs))
    elif case == "quality_duplicate":
        second = second.assign_coords(
            quality=(("time", "lev", "y", "x"), np.zeros(shape), {"flag_values": [0, 1]}))
        second.salinity.attrs["ancillary_variables"] = "quality"
    elif case == "missing_PS":
        first = first.drop_vars("PS")
    elif case == "malformed_terms":
        second.lev.attrs["formula_terms"] += " dangling"
    paths = [tmp_path / "temperature.nc", tmp_path / "salinity.nc"]
    for scene, path in zip((first, second), paths, strict=True):
        scene.to_netcdf(path, engine="h5netcdf")
    guard_netcdf_payloads(monkeypatch, {"temperature", "salinity", "PS", "quality"})
    conf = v3_config(tmp_path, paths, variables={"3d": ["temperature", "salinity"]},
                     time={"values": ["2026-01-01T01:00:00", "2026-01-01T03:00:00"]})
    error = {
        "physical_duplicate": "competing physical-field providers for temperature",
        "quality_duplicate": "competing physical-field providers for quality",
        "missing_PS": "PS.*selected",
        "malformed_terms": "lev.*formula_terms",
    }.get(case)
    if error:
        with pytest.raises(ValueError, match=error):
            preflight(conf, check_output=False)
        return
    source = preflight(conf, check_output=False)["sources"]["weather"]
    assert {r["name"] for r in source["records"]} == {
        "temperature", "salinity", "PS", "quality"}
    assert not source["provider_conflicts"]
    grids = {name: next(r["grid_id"] for r in source["records"] if r["name"] == name)
             for name in ("temperature", "salinity")}
    assert (grids["temperature"] == grids["salinity"]) is (case == "identical")
    for name, path, scene in zip(("temperature", "salinity"), paths, (first, second), strict=True):
        grid = source["native_grids"][grids[name]]
        for coefficient in ("a", "b", "p0"):
            metadata = grid["coordinates"][coefficient]
            assert metadata["role"] == "coordinate_metadata"
            np.testing.assert_array_equal(metadata["values"], scene[coefficient].values)
            providers = grid["coordinate_providers"][coefficient]
            assert {p["path"] for p in providers} == (
                set(map(str, paths)) if case == "identical" else {str(path)})
            assert all(p["variable"] == coefficient and p["format"] == "netcdf"
                       for p in providers)
            assert all([s["coordinate_indexers"] for s in p["samples"]] == [
                {"time": 1}, {"time": 3}] for p in providers)
        assert "PS" not in grid["coordinates"] and "quality" not in grid["coordinates"]
        record = next(r for r in source["records"] if r["name"] == name)
        field = source["fields"][record["field_id"]]
        assert field["coordinate_dependencies"] == {
            "a": "formula_terms", "b": "formula_terms", "p0": "formula_terms",
            "latitude": "coordinates", "longitude": "coordinates"}
        assert field["dependencies"]["PS"] == "formula_terms"
    assert source["files"] == list(map(str, paths))
    if case == "identical":
        formula_paths = [tmp_path / "formula-temperature.nc", tmp_path / "formula-salinity.nc"]
        for scene, path in zip((first, second), formula_paths, strict=True):
            scene.reset_coords(["a", "b", "p0"]).to_netcdf(path, engine="h5netcdf")
        formula_source = preflight(v3_config(
            tmp_path, formula_paths, variables={"3d": ["temperature", "salinity"]},
            time={"values": ["2026-01-01T01:00:00", "2026-01-01T03:00:00"]}),
            check_output=False)["sources"]["weather"]
        assert {r["grid_id"] for r in formula_source["records"]
                if r["name"] in grids} == {grids["temperature"]}


@pytest.mark.parametrize("case", [
    "review_reproduction", "wrong_dimensions", "wrong_endpoint_count", "ancillary_only",
    "cell_measure_only", "formula_input_only",
    "flag_values_only", "flag_masks_only", "flag_meanings_only", "missing", "valid",
])
def test_v3_coordinate_bounds_fail_before_scientific_backend_access(tmp_path, monkeypatch, case):
    scene = v3_scene(hours=(0, 1))
    shape = (2, 2, 2, 3)
    scene["temperature"] = (("time", "level", "y", "x"), np.ones(shape), {"units": "K"})
    scene = scene.assign_coords(
        level=[0, 1],
        pressure=("level", [850., 700.], {
            "standard_name": "air_pressure", "axis": "Z", "units": "hPa", "bounds": "quality"}))
    dims, values, attrs = ("level", "nv"), np.array([[900., 800.], [750., 650.]]), {"units": "hPa"}
    if case == "review_reproduction":
        dims, values = ("time", "level", "y", "x"), np.zeros(shape)
        attrs["flag_values"] = [0, 1]
    elif case == "wrong_dimensions":
        dims = ("nv", "level")
    elif case == "wrong_endpoint_count":
        dims, values = ("level", "nv"), np.zeros((2, 3))
    elif case == "flag_values_only":
        attrs["flag_values"] = [0, 1]
    elif case == "flag_masks_only":
        attrs["flag_masks"] = [1, 2]
    elif case == "flag_meanings_only":
        attrs["flag_meanings"] = "clear suspect"
    if case in {"review_reproduction", "ancillary_only"}:
        scene.temperature.attrs["ancillary_variables"] = "quality"
    elif case == "cell_measure_only":
        scene.temperature.attrs["cell_measures"] = "area: quality"
    elif case == "formula_input_only":
        scene.level.attrs.update(
            standard_name="atmosphere_hybrid_sigma_pressure_coordinate", axis="Z", units="1",
            formula_terms="a: a b: b p0: p0 ps: quality")
        scene = scene.assign_coords(a=("level", [.1, .2], {"units": "1"}),
                                    b=("level", [.9, .8], {"units": "1"}),
                                    p0=((), 100000., {"units": "Pa"}))
    if case != "missing":
        scene = scene.assign_coords(quality=(dims, values, attrs))
    path = tmp_path / "contradictory-bounds.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    forbidden = {"temperature", "quality"} if case != "valid" else {"temperature"}
    reads = guard_netcdf_payloads(monkeypatch, forbidden)
    conf = v3_config(tmp_path, [path], variables={"3d": ["temperature"]},
                     time={"values": ["2026-01-01T01:00:00"]})
    if case != "valid":
        reason = ("dimensions|endpoint" if case in {
            "review_reproduction", "wrong_dimensions", "wrong_endpoint_count"} else
            "missing" if case == "missing" else "ancillary|flag|scientific")
        with pytest.raises(ValueError, match=rf"pressure.*bounds.*quality.*({reason})") as caught:
            preflight(conf, check_output=False)
        assert str(path) in str(caught.value)
        assert not any(name == "quality" for name, _ in reads)
        assert not conf.output_dir.exists()
        return
    source = preflight(conf, check_output=False)["sources"]["weather"]
    assert len(source["records"]) == 1
    record = source["records"][0]
    assert record["locator"]["indexers"] == {"time": 1}
    grid = source["native_grids"][record["grid_id"]]
    assert grid["coordinates"]["pressure"]["attributes"]["bounds"] == "quality"
    assert grid["coordinates"]["quality"]["role"] == "coordinate_metadata"
    np.testing.assert_array_equal(grid["coordinates"]["quality"]["values"], values)
