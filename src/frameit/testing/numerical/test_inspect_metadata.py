"""Inspect exposes source evidence without selecting a basis or reading fields."""

from copy import deepcopy

import dask.array as da
import numpy as np
import pytest
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
