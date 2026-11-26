"""Qualified catalogue fallback without editing inputs or reading payloads in validation."""

import json
from pathlib import Path

import pytest
import xarray as xr
import yaml

from frameit.cli import _cmd_validate
from frameit.core.catalogue_diagnostics import propose
from frameit.core.execution import execute_simulation
from frameit.core.metadata_catalogue import open_catalogue
from frameit.core.preflight import collect_preflight
from frameit.core.reports import project_report, render_projection
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads
from frameit.testing.numerical.test_v3_operations import scene


@pytest.fixture(scope="module")
def cache_home(tmp_path_factory):
    return tmp_path_factory.mktemp("catalogue")


@pytest.fixture(autouse=True)
def offline_cache(cache_home, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))


def _scene(*, name="THT", units=None, version="6.0.0"):
    ds = scene().rename(U=name)
    ds[name].attrs = {"long_name": "THT", "standard_name": "air_potential_temperature"}
    if version is not None:
        # IO_Header_write_nc4 stores NMNHVERSION(1:3) in the root attribute.
        ds.attrs["MNH_VERSION"] = [int(part) for part in version.split(".")]
    if units is not None:
        ds[name].attrs["units"] = units
    ds.V.attrs = {}
    return ds


def _request(tmp_path, *, name="THT", target="K", paths=None):
    return {
        "schema_version": 3, "run": {"name": "lookup"},
        "sources": {"atmosphere": {
            "model": "mesonh", "files": paths or str(tmp_path / "input.nc"),
            "variables": {"3d": [name]},
            **({"transforms": [{"fields": [name], "units": target}]} if target else {}),
        }},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"scheduler": "synchronous", "synchronous_export": True},
    }


def _suggestions(report):
    table = report["data"]["plan"].get("metadata_catalogue")
    assert table is not None, "Full validation did not report catalogue advice"
    assert table["catalogue_version"] == "0.2.1"
    return table["fields"]


def test_validated_lookup_resolves_required_units_without_a_yaml_declaration(
    tmp_path, monkeypatch, capsys,
):
    path, request = tmp_path / "input.nc", tmp_path / "frameit.yaml"
    _scene().to_netcdf(path, engine="h5netcdf")
    doc = _request(tmp_path)
    request.write_text(yaml.safe_dump(doc))
    before = path.read_bytes(), request.read_bytes()
    with monkeypatch.context() as guard:
        guard_netcdf_payloads(guard, {"THT", "V"})
        assert _cmd_validate(request, json_output=True) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert set(report) == {
        "report_version", "command", "status", "data", "warnings", "errors", "deferred_checks",
    }
    assert report["status"] == "ok" and not report["errors"]
    assert not report["data"]["configuration"]["sources"]["atmosphere"]["field_metadata"]
    field, = _suggestions(report)
    assert field["source_id"] == "atmosphere" and field["selector"] == "THT"
    assert field["native_identity"]["netcdf_group"] == ""
    assert field["status"] == "applied" and field["applied_values"] == {"units": "K"}
    assert 10546 in field["record_ids"] and field["evidence"]
    assert "repair" not in field
    assert any("[W1306]" in warning and "units=K" in warning for warning in report["warnings"])
    assert report["data"]["origins"]["inputs.sources.atmosphere.field_metadata"]["THT"][
        "units"] == "catalogue"
    text = render_projection(report)
    assert "Metadata catalogue 0.2.1" in text and "units=K" in text
    assert (path.read_bytes(), request.read_bytes()) == before
    assert not (tmp_path / "out").exists()

    # Execution independently resolves the same request without a validate-generated file.
    run = execute_simulation(SimulationConfig.from_yaml_with_model_preset(request))
    assert run.ok
    assert "[W1306]" in capsys.readouterr().err
    with xr.open_dataset(run.products[0]["path"]) as output:
        assert output.THT.attrs["units"] == "K"
    provenance = yaml.safe_load((tmp_path / "out" / "run-provenance.yaml").read_text())
    entry, = provenance["sources"]["atmosphere"]["metadata_catalogue"]
    assert entry["applied_values"] == {"units": "K"}
    assert entry["record_ids"] == {"units": [10546]}
    native, = entry["records"]
    assert native["file_index"] == 0
    assert provenance["binding"]["atmosphere"]["files"][native["file_index"]] == str(path)
    assert native["native_identity"]["version"] == "6.0.0"
    assert native["record_ids"] == {"units": [10546]}
    assert (path.read_bytes(), request.read_bytes()) == before


@pytest.mark.parametrize(("version", "name", "target", "status"), [
    (None, "THT", "K", "version_required"),
    ("9.0.0", "THT", "K", "unmatched"),
    ("6.0.0", "tht", "K", "unmatched"),
    ("6.0.0", "THT", "Pa", "conflict"),
])
def test_no_repair_without_exact_identity_and_operation_unit_admission(
    tmp_path, version, name, target, status,
):
    _scene(name=name, version=version).to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    report = project_report(collect_preflight(_request(tmp_path, name=name, target=target)))
    field, = _suggestions(report)
    assert report["errors"] and field["status"] == status
    assert "repair" not in field and not field["proposed_values"]
    assert not any("[W1306]" in warning for warning in report["warnings"])


def test_source_conflict_retains_distinct_file_evidence_and_withholds_selector(tmp_path):
    first, second = tmp_path / "first.nc", tmp_path / "second.nc"
    _scene().isel(time=[0]).to_netcdf(first, engine="h5netcdf")
    _scene(units="degC", version="6.0.1").isel(time=[1]).to_netcdf(second, engine="h5netcdf")
    report = project_report(collect_preflight(_request(tmp_path, paths=[str(first), str(second)])))
    field, = _suggestions(report)
    assert report["errors"][0]["code"] == "E1302"
    assert {Path(record["file"]).name for record in field["records"]} == {"first.nc", "second.nc"}
    assert {r["native_identity"]["version"] for r in field["records"]} == {"6.0.0", "6.0.1"}
    assert field["status"] == "conflict" and field["selector"] is None and "repair" not in field


def test_equal_catalogue_values_do_not_override_mixed_producer_releases(tmp_path):
    first, second = tmp_path / "first.nc", tmp_path / "second.nc"
    _scene().isel(time=[0]).to_netcdf(first, engine="h5netcdf")
    _scene(version="6.0.1").isel(time=[1]).to_netcdf(second, engine="h5netcdf")
    report = project_report(collect_preflight(_request(tmp_path, paths=[str(first), str(second)])))
    field, = _suggestions(report)
    assert {r["native_identity"]["version"] for r in field["records"]} == {"6.0.0", "6.0.1"}
    assert all(r["proposed_values"] == {"units": "K"} for r in field["records"])
    assert report["errors"] and field["status"] == "conflict" and "applied_values" not in field
    assert not any("[W1306]" in warning for warning in report["warnings"])


def test_optional_labels_do_not_fail_validation_or_consult_unselected_fields(tmp_path):
    ds = _scene(units="K")
    ds.THT.attrs = {"units": "K"}
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    result = collect_preflight(_request(tmp_path, target=None))
    assert not result.errors
    field, = _suggestions(project_report(result))
    assert field["selector"] == "THT"
    assert field["applied_values"] == {
        "long_name": "THT", "standard_name": "air_potential_temperature",
    }


@pytest.mark.parametrize("explicit_basis", ["field", "dataset", "wind_pairs"])
def test_catalogue_cf_name_cannot_label_earth_wind_as_grid_wind(tmp_path, explicit_basis):
    ds = _scene(name="UT").rename(V="VT")
    ds.UT.attrs = {"units": "m s-1", "long_name": "UT"}
    doc = _request(tmp_path, name="UT", target=None)
    if explicit_basis == "wind_pairs":
        doc["sources"]["atmosphere"]["wind_pairs"] = [{"u": "UT", "v": "VT", "basis": "earth"}]
    else:
        (ds.UT if explicit_basis == "field" else ds).attrs["wind_reference_frame"] = "earth"
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")

    result = collect_preflight(doc)
    assert not result.errors
    field, = _suggestions(project_report(result))
    assert "standard_name" not in field.get("applied_values", {})
    assert any(reason["reason"] == "wind_basis_conflict" for reason in field["withheld"])
    assert not any("[W1306]" in warning for warning in result.facts["warnings"])


def test_catalogue_does_not_introduce_an_unrelated_native_export_failure(tmp_path):
    ds = _scene()
    ds.THT.attrs.update(online_operation="mean", cell_methods="time: point")
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    result = collect_preflight(_request(tmp_path, target=None))
    assert not result.errors, result.errors
    assert not any("[W1306]" in warning for warning in result.facts["warnings"])


def test_conflicting_explicit_declaration_is_not_resolved_by_catalogue(tmp_path):
    _scene(units="K").to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    doc = _request(tmp_path)
    doc["sources"]["atmosphere"]["field_metadata"] = {"THT": {"units": "Pa"}}
    result = collect_preflight(doc)
    assert result.errors and "contradicts input" in result.errors[0].message
    assert "metadata_catalogue" not in result.facts


@pytest.mark.parametrize("where", ["input", "declaration"])
def test_existing_units_take_precedence_without_a_catalogue_warning(tmp_path, where):
    ds = _scene(units="kelvin" if where == "input" else None)
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    doc = _request(tmp_path, target="kelvin")
    if where == "declaration":
        doc["sources"]["atmosphere"]["field_metadata"] = {"THT": {"units": "kelvin"}}
    result = collect_preflight(doc)
    assert not result.errors and "metadata_catalogue" not in result.facts
    source = result.facts["sources"]["atmosphere"]
    assert source["metadata_origins"]["field_metadata"].get("THT", {}).get("units", "input") == (
        where)
    assert result.facts["products"][0]["units"]["THT"] == "kelvin"


def test_tracker_consumes_admitted_catalogue_pressure_units(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_v3_polar import scene as surface_scene

    ds = surface_scene().rename(q="MSLP").assign_attrs(MNH_VERSION=[6, 0, 0])
    ds.MSLP.attrs = {"long_name": "MSLP", "standard_name": "air_pressure_at_sea_level"}
    ds["UM10"] = xr.zeros_like(ds.MSLP).assign_attrs(
        long_name="UM10", units="m s-1", standard_name="eastward_wind")
    ds["VM10"] = xr.zeros_like(ds.MSLP).assign_attrs(
        long_name="VM10", units="m s-1", standard_name="northward_wind")
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    doc = _request(tmp_path, name="MSLP", target=None)
    doc["sources"]["atmosphere"]["variables"] = {"2d": ["MSLP"]}
    doc["region"] = {"tracker": {"method": "pressure_wind"}}
    doc["products"] = {"track": True}
    guard_netcdf_payloads(monkeypatch, {"MSLP", "UM10", "VM10"})
    result = collect_preflight(doc)
    assert not result.errors, result.errors
    field = next(row for row in _suggestions(project_report(result)) if row["field"] == "MSLP")
    assert field["applied_values"] == {"units": "hPa"}


def test_pressure_centroid_does_not_block_units_for_an_independent_transform(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_pressure_centroid_mnh import native_vortex

    ds, _ = native_vortex(n=7)
    ds.attrs["MNH_VERSION"] = [6, 0, 0]
    ds["THT"] = xr.full_like(ds.PABST, 300.).assign_attrs(
        units="", long_name="THT", standard_name="air_potential_temperature")
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    doc = _request(tmp_path)
    doc["sources"]["atmosphere"]["wind_pairs"] = [
        {"u": "UT_ZM", "v": "VT_ZM", "basis": "earth"},
        {"u": "UM10", "v": "VM10", "basis": "earth"},
    ]
    doc["region"] = {"tracker": {"method": "pressure_centroid"},
                     "width_km": {"x": 100, "y": 100}}
    doc["products"] = {"track": True, "model_grid": True}
    guard_netcdf_payloads(monkeypatch, set(ds.data_vars) - {"latitude", "longitude"})
    result = collect_preflight(doc)
    assert not result.errors, result.errors
    field = next(row for row in _suggestions(project_report(result)) if row["field"] == "THT")
    assert field["applied_values"] == {"units": "K"}


def test_catalogue_withholds_units_when_packed_range_blocks_conversion(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_v3_polar import scene as surface_scene

    ds = surface_scene().rename(q="MSLP").assign_attrs(MNH_VERSION=[6, 0, 0])
    ds.MSLP.attrs = {"long_name": "MSLP", "standard_name": "air_pressure_at_sea_level",
                     "valid_range": [0, 1100]}
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf", encoding={
        "MSLP": {"dtype": "int16", "scale_factor": 0.1, "_FillValue": -32768},
    })
    doc = _request(tmp_path, name="MSLP", target="Pa")
    doc["sources"]["atmosphere"]["variables"] = {"2d": ["MSLP"]}
    guard_netcdf_payloads(monkeypatch, {"MSLP"})

    report = project_report(collect_preflight(doc))
    field, = _suggestions(report)
    assert report["errors"] and not field.get("applied_values")
    assert any(evidence["reason"] == "unit_admission"
               and "packed validity/range metadata" in evidence["detail"]
               for evidence in field["withheld"])
    assert not any("[W1306]" in warning for warning in report["warnings"])


def test_native_version_string_identifies_the_release(tmp_path):
    ds = _scene(version=None)
    ds.attrs["MNH_VERSION_STR"] = "Meso-NH 6.0.0"
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    result = collect_preflight(_request(tmp_path))
    field, = _suggestions(project_report(result))
    assert field["native_identity"]["version_evidence"] == "MNH_VERSION_STR"
    assert field["applied_values"] == {"units": "K"}


def test_catalogue_advice_does_not_hide_an_independent_source_error(tmp_path):
    _scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    doc = _request(tmp_path)
    doc["sources"]["ocean"] = {"model": "nemo", "files": str(tmp_path / "missing.nc"),
                               "variables": {"2d": ["temp"]}}
    result = collect_preflight(doc)
    assert {e.path for e in result.errors} == {"sources.ocean.files"}
    field, = _suggestions(project_report(result))
    assert field["source_id"] == "atmosphere" and field["applied_values"] == {"units": "K"}


def test_schema_only_and_inspect_do_not_open_catalogue(tmp_path, monkeypatch):
    def unopened(*args, **kwargs):
        pytest.fail("Only full validation can consult the catalogue")

    # An unusable XDG location also makes any unexpected construction visible.
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "offline-cache"))
    monkeypatch.setattr("frameit.core.metadata_catalogue.open_catalogue", unopened)
    doc = _request(tmp_path)
    assert not collect_preflight(doc, schema_only=True).errors
    _scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    assert not collect_preflight(doc, command="inspect").errors
    assert not (tmp_path / "offline-cache").exists()


@pytest.mark.parametrize("target", ["K", None])
def test_missing_catalogue_does_not_replace_validation_verdict(tmp_path, monkeypatch, target):
    _scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    not_directory = tmp_path / "not-a-directory"
    not_directory.write_text("unavailable disposable cache")
    monkeypatch.setenv("XDG_CACHE_HOME", str(not_directory))
    result = collect_preflight(_request(tmp_path, target=target))
    assert bool(result.errors) == bool(target)
    assert any("[W1307]" in warning for warning in result.facts["warnings"])
    if target:
        assert "incompatible or unsupported units" in result.errors[0].message


def _resolve(producer, version, name, namespace, context, observed=None, missing=("units",)):
    with open_catalogue() as index:
        rows = index.lookup(producer, version, name, namespace)
    assert rows
    return propose(rows, {"namespace": namespace, **context}, observed or {}, missing)


@pytest.mark.parametrize(("group", "units"), [
    ("Time_series/TSERIES/GLOB", "kg m-2"),
    ("Time_series/ZTSERIES/GLOB", "kg kg-1"),
])
def test_actual_mesonh_netcdf_group_distinguishes_units(group, units):
    result = _resolve("mesonh", "6.0.0", "RVT_GLOB", "mesonh_netcdf_variable",
                      {"format": "netcdf", "netcdf_group": group})
    assert result["proposed_values"] == {"units": units}


def test_unknown_cloud_name_array_and_normalized_les_do_not_inherit_generic_units():
    root = {"format": "netcdf", "netcdf_group": ""}
    cloud = _resolve("mesonh", "6.0.0", "CCLOUD", "mesonh_netcdf_variable",
                     {**root, "name_array": "C2R2NAMES", "name_array_binding_verified": 1})
    assert not cloud["proposed_values"]
    assert any(item["key"] == "name_array_binding_verified"
               for item in cloud["unresolved_requirements"])
    les = _resolve("mesonh", "6.0.0", "ACCU_PREC", "mesonh_netcdf_variable",
                   {"format": "netcdf", "netcdf_group": "LES_budgets/Surface/Cartesian/Mean/X/GLOB",
                    "CLES_NORM_TYPE": "CONV"})
    assert not les["proposed_values"]


@pytest.mark.parametrize(("name", "observed", "missing"), [
    ("u", {"standard_name": "sea_water_temperature"}, ("units", "long_name")),
    ("aice", {"units": "K"}, ("standard_name", "long_name")),
])
def test_native_croco_candidates_require_scientifically_compatible_observations(
    name, observed, missing,
):
    outcome = _resolve("croco", "2.1.0", name, "netcdf_variable_name",
                       {"format": "netcdf", "output_backend": "native_netcdf"}, observed, missing)
    assert outcome["status"] == "conflict" and not outcome["proposed_values"]


@pytest.mark.parametrize(("producer", "version", "name", "reason", "observed"), [
    ("croco", "2.1.0", "vortuw_nbq", "unresolved_unit", {}),
    ("nemo", "4.2.1", "ttrd_totad", "cf_unit_dimension_conflict",
     {"units": "degC/s", "standard_name": "tendency_of_sea_water_salinity_due_to_advection"}),
])
def test_source_placeholders_and_conflicts_do_not_produce_units(
    producer, version, name, reason, observed,
):
    outcome = _resolve(producer, version, name, "xios_field_id",
                       {"format": "netcdf", "output_backend": "xios",
                        "xios_binding_verified": True, "xios_field_id": name}, observed,
                       ("units", "long_name") if not observed else ("long_name",))
    assert "units" not in outcome["proposed_values"]
    assert any(item["reason"] == reason for item in outcome["withheld"])


def test_output_alias_and_product_mnemonic_are_not_native_bindings():
    nemo = _resolve("nemo", "4.2.1", "votemper", "explicit_xios_output_name", {"format": "netcdf"})
    assert nemo["status"] == "context_required" and not nemo["proposed_values"]
    arome = _resolve("arome", "official_product_documentation_snapshot_2026-11-25",
                     "ALBEDO", "meteo_france_product_mnemonic", {"format": "grib"})
    assert arome["status"] == "reference_only" and not arome["proposed_values"]


def test_empty_candidate_counts_instead_of_selecting_an_eligible_first_row():
    identity = {"namespace": "native"}
    usable = {"candidate": True, "identity": {}, "requires": {}, "withheld": {}}
    rows = [
        {"id": 1, "namespace": "native", "source": {"metadata": {"units": "K"}},
         "completion": {**usable, "values": {"units": "K"}}},
        {"id": 2, "namespace": "native", "source": {},
         "completion": {**usable, "values": {}, "withheld": {"units": "source_review_required"}}},
    ]
    result = propose(rows, identity, {}, ("units",))
    assert result["status"] == "ambiguous" and not result["proposed_values"]


def test_observed_units_and_standard_name_do_not_establish_two_different_identities():
    completion = {"candidate": True, "identity": {}, "requires": {}, "withheld": {},
                  "values": {"long_name": "Cannot be proposed"}}
    rows = [
        {"id": 1, "namespace": "native", "completion": completion,
         "source": {"metadata": {"units": "K", "standard_name": "air_temperature"}}},
        {"id": 2, "namespace": "native", "completion": completion,
         "source": {"metadata": {"units": "Pa", "standard_name": "air_pressure"}}},
    ]
    result = propose(rows, {"namespace": "native"}, {"units": "K", "standard_name": "air_pressure"},
                     ("long_name",))
    assert result["status"] == "conflict" and not result["proposed_values"]
