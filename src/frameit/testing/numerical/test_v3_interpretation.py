"""Stored-value declarations and opt-in interpretation on real selected readers."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.coupled import bind_sources
from frameit.core.execution import execute_simulation
from frameit.testing.documentation_example import create_first_run_input
from frameit.testing.numerical.test_mnh_surfex_support import surfex_scene
from frameit.testing.numerical.test_v3_execution import _configuration


def _payload_guard(monkeypatch, names):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    original = H5NetCDFArrayWrapper.__getitem__
    reads = []

    def observed(self, key):
        if self.variable_name in names:
            reads.append((self.variable_name, key.tuple))
        return original(self, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", observed)
    return reads


def _fa_requests(monkeypatch):
    original, calls = subprocess.run, []

    def observed(argv, **kwargs):
        if "frameit.io.fa_worker" in argv:
            calls.append(json.loads(kwargs["input"]))
        return original(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", observed)
    return calls


def test_declarations_fill_gaps_without_converting_values(tmp_path, monkeypatch):
    path = create_first_run_input(tmp_path / "scalar.nc")
    with xr.open_dataset(path) as original:
        ds = original.load()
    ds.instructional_scalar.attrs = {"cell_methods": "valid_time: point"}
    ds.to_netcdf(path, mode="w")
    before = path.read_bytes()
    conf = _configuration(tmp_path, {"atmosphere": {
        "files": str(path), "model": "arome",
        "variables": {"2d": ["instructional_scalar"]},
        "time": {"values": ["2000-01-01T01:00:00"]},
        "field_metadata": {"instructional_scalar": {
            "units": "K", "kind": "continuous", "temporal_kind": "instantaneous",
            "long_name": "declared stored scalar"}},
    }})
    reads = _payload_guard(monkeypatch, {"instructional_scalar"})
    _, children, plans = bind_sources(conf)
    assert reads == []
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    assert binding["status"] == "bound"
    metadata = binding["products"]["model_grid"]["instructional_scalar"]["field_metadata"]
    assert metadata["origins"]["units"] == "declaration"
    assert metadata["origins"]["temporal_kind"] == "input"
    assert plans["atmosphere"]["metadata_origins"]["field_metadata"]
    result = execute_simulation(conf)
    assert result.ok, result
    assert reads and all(np.atleast_1d(np.arange(2)[key[0]]).tolist() == [1]
                         for _, key in reads)
    subprocess.run([sys.executable, "-c", """
import sys, json, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as src:
    np.testing.assert_array_equal(out.instructional_scalar, src.instructional_scalar[1:2])
    assert out.instructional_scalar.attrs['units'] == 'K'
    assert out.instructional_scalar.attrs['cell_methods'] == 'time: point'
    origins = json.loads(out.instructional_scalar.attrs['frameit_metadata_origins'])
    assert origins['units'] == 'declaration' and origins['temporal_kind'] == 'input'
    assert out.time.values.tolist() == src.valid_time.values[1:2].tolist()
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(path)], check=True, capture_output=True, text=True)
    assert path.read_bytes() == before


@pytest.mark.parametrize("statistic_name,method,declared", [
    ("t", "mean", "instantaneous"),
    ("sample", "mean", "instantaneous"),
    ("t", "maximum", "mean"),
    ("t", "sum", "mean"),
    ("t", "mean", "mean"),
])
def test_cf_temporal_metadata_uses_admitted_clock_and_dimensions(
    tmp_path, monkeypatch, statistic_name, method, declared,
):
    from frameit.core.preflight import preflight

    path = create_first_run_input(tmp_path / "clock.nc")
    with xr.open_dataset(path) as original:
        ds = original.load().rename({"valid_time": "t"})
    ds.t.attrs.update(standard_name="time", axis="T")
    if statistic_name == "sample":
        ds = ds.rename_dims({"t": "sample"})
    ds.instructional_scalar.attrs.update(cell_methods=f"{statistic_name}: {method}")
    ds.to_netcdf(path, mode="w")
    before = path.read_bytes()
    conf = _configuration(tmp_path, {"atmosphere": {
        "model": "arome", "files": str(path),
        "variables": {"2d": ["instructional_scalar"]},
        "field_metadata": {"instructional_scalar": {"temporal_kind": declared}},
    }})
    reads = _payload_guard(monkeypatch, {"instructional_scalar"})
    if declared != method:
        with pytest.raises(ValueError, match="contradict"):
            preflight(conf, check_output=False)
        with pytest.raises(ValueError, match="contradict"):
            execute_simulation(conf)
        assert reads == [] and not conf.output_dir.exists()
    else:
        preflight(conf, check_output=False)
        assert reads == []
        result = execute_simulation(conf)
        assert result.ok, result
        subprocess.run([sys.executable, "-c", """
import sys, json, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as src:
    np.testing.assert_array_equal(out.instructional_scalar, src.instructional_scalar)
    np.testing.assert_array_equal(out.time, src.t)
    attrs = out.instructional_scalar.attrs
    assert attrs['cell_methods'] == 'time: mean' and attrs['temporal_kind'] == 'mean'
    assert json.loads(attrs['frameit_metadata_origins'])['temporal_kind'] == 'input'
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(path)], check=True, capture_output=True, text=True)
    assert path.read_bytes() == before


def test_cf_interval_qualifier_is_not_another_temporal_method(tmp_path, monkeypatch):
    path = create_first_run_input(tmp_path / "clock.nc")
    with xr.open_dataset(path) as original:
        ds = original.load().rename({"valid_time": "t"}).rename_dims({"t": "interval"})
    ds.t.attrs.update(standard_name="time", axis="T")
    ds.instructional_scalar.attrs["cell_methods"] = "t: mean (interval: 1 hour)"
    ds.to_netcdf(path, mode="w")
    conf = _configuration(tmp_path, {"atmosphere": {
        "model": "arome", "files": str(path),
        "variables": {"2d": ["instructional_scalar"]},
        "field_metadata": {"instructional_scalar": {"temporal_kind": "mean"}},
    }})
    reads = _payload_guard(monkeypatch, {"instructional_scalar"})
    _, children, _ = bind_sources(conf)
    metadata = children["atmosphere"].source_requests["atmosphere"]["binding"][
        "products"]["model_grid"]["instructional_scalar"]["field_metadata"]
    assert metadata["attributes"]["temporal_kind"] == "mean"
    assert metadata["origins"]["temporal_kind"] == "input"
    assert reads == [] and not conf.output_dir.exists()


@pytest.mark.parametrize("observed,declared,agrees", [
    ("MW m-2", "mW m-2", False),
    ("UnlistedUnit", "unlistedunit", False),
    ("MW m-2", "MW m-2", True),
    ("kelvin", "K", True),
    ("W/m2", "W m-2", True),
    ("Pa", "N/m2", True),
    ("m s**-1", "m/s", True),
    ("cm/s", "m/s", False),
])
def test_stored_unit_comparison_is_explicit_and_preserves_spelling(observed, declared, agrees):
    from frameit.processing.requests import resolve_field_metadata

    if not agrees:
        with pytest.raises(ValueError, match="contradict"):
            resolve_field_metadata({"units": observed}, {"units": declared}, "field")
    else:
        result = resolve_field_metadata({"units": observed}, {"units": declared}, "field")
        assert result["attributes"]["units"] == observed
        assert result["origins"]["units"] == "input"


def test_distinct_si_prefix_declaration_fails_before_payload(tmp_path, monkeypatch):
    from frameit.core.preflight import preflight

    path = create_first_run_input(tmp_path / "power.nc")
    with xr.open_dataset(path) as original:
        ds = original.load()
    ds.instructional_scalar.attrs["units"] = "MW m-2"
    ds.to_netcdf(path, mode="w")
    before = path.read_bytes()
    conf = _configuration(tmp_path, {"atmosphere": {
        "model": "arome", "files": str(path),
        "variables": {"2d": ["instructional_scalar"]},
        "field_metadata": {"instructional_scalar": {"units": "mW m-2"}},
    }})
    reads = _payload_guard(monkeypatch, {"instructional_scalar"})
    with pytest.raises(ValueError, match="contradict"):
        preflight(conf, check_output=False)
    with pytest.raises(ValueError, match="contradict"):
        execute_simulation(conf)
    assert reads == [] and not conf.output_dir.exists()
    assert path.read_bytes() == before


def test_sea_alias_declaration_keeps_comment_units_and_values(tmp_path, monkeypatch):
    from frameit.core.preflight import preflight
    from frameit.core.settings_class import SimulationConfig

    path, initial = _sea_case(tmp_path, fields=("SST",))
    before = path.read_bytes()
    raw = copy.deepcopy(initial.yaml_config)
    raw["sources"]["surface"]["field_metadata"] = {"SST": {"units": "kelvin"}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    reads = _payload_guard(monkeypatch, {"SST", "FRAC_SEA"})
    preflight(conf, check_output=False)
    assert reads == []
    result = execute_simulation(conf)
    assert result.ok, result
    subprocess.run([sys.executable, "-c", """
import sys, json, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    assert out.SST.attrs['units'] == 'K'
    assert out.SST.attrs['surfex_units_source'] == 'source_comment'
    assert json.loads(out.SST.attrs['frameit_metadata_origins'])['units'] == 'source_comment'
    assert out.SST[0,3,3] == 301. and out.SST[0,4,3] == 0.
    assert np.isnan(out.SST[0,3,4]) and out.FRAC_SEA[0,3,3] == .25
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"]], check=True, capture_output=True, text=True)
    assert path.read_bytes() == before


def test_sea_comment_does_not_case_fold_distinct_si_prefixes(tmp_path, monkeypatch):
    from frameit.core.preflight import preflight

    path, conf = _sea_case(tmp_path, fields=("H_SEA",))
    with xr.open_dataset(path) as original:
        ds = original.load()
    ds.H_SEA.attrs.update(units="MW m-2", comment="stored flux (mW m-2)")
    ds.to_netcdf(path, mode="w")
    reads = _payload_guard(monkeypatch, {"H_SEA", "FRAC_SEA"})
    with pytest.raises(ValueError, match="contradict"):
        preflight(conf, check_output=False)
    assert reads == [] and not conf.output_dir.exists()


@pytest.mark.parametrize("attrs,declaration", [
    ({"units": "K"}, {"units": "degC"}),
    ({"units": "m s-1"}, {"units": "km h-1"}),
    ({"standard_name": "air_temperature"}, {"standard_name": "sea_surface_temperature"}),
    ({"kind": "categorical"}, {"kind": "continuous"}),
    ({"flag_values": [0, 1]}, {"kind": "continuous"}),
    ({"cell_methods": "valid_time: mean"}, {"temporal_kind": "instantaneous"}),
    ({"cell_methods": "valid_time: maximum"}, {"temporal_kind": "mean"}),
    ({"online_operation": "average"}, {"temporal_kind": "instantaneous"}),
    ({"temporal_kind": "accumulated"}, {"temporal_kind": "instantaneous"}),
])
def test_contradictory_declarations_fail_without_payload(tmp_path, monkeypatch, attrs, declaration):
    path = create_first_run_input(tmp_path / "scalar.nc")
    with xr.open_dataset(path) as original:
        ds = original.load()
    ds.instructional_scalar.attrs = attrs
    ds.to_netcdf(path, mode="w")
    conf = _configuration(tmp_path, {"atmosphere": {
        "files": str(path), "model": "arome",
        "variables": {"2d": ["instructional_scalar"]},
        "field_metadata": {"instructional_scalar": declaration},
    }})
    reads = _payload_guard(monkeypatch, {"instructional_scalar"})
    with pytest.raises(ValueError, match="contradict"):
        execute_simulation(conf)
    assert reads == [] and not conf.output_dir.exists()


def _sea_case(tmp_path, *, interpretation=True, fields=("SST", "H_SEA", "PRES"),
              invalid_sample=None):
    parts = [surfex_scene(i) for i in range(3)]
    if invalid_sample is not None:
        parts[invalid_sample].FRAC_SEA.values[3, 3] = 1.1
    path = tmp_path / "sea.nc"
    xr.concat(parts, dim="time", data_vars="all", coords="minimal", compat="equals").to_netcdf(path)
    source = {"model": "mesonh", "files": str(path), "variables": {"2d": list(fields)},
              "time": {"values": ["2024-12-10T02:00:00"]},
              "reader": {"chunks": {"time": 3}}}
    if interpretation:
        source["interpretation"] = "mesonh_surfex_sea"
    return path, _configuration(tmp_path, {"surface": source})


def _sea_snapshots(tmp_path, *, first_units="K", conflict=None):
    paths = []
    for index in (0, 1):
        ds = surfex_scene(index)
        if first_units is not None or index:
            ds.SST.attrs["units"] = "kelvin" if index else first_units
        ds["FMU_SEA"] = (("nj", "ni"), np.full((7, 7), 2.), {
            "units": "N/m2" if index else "Pa", "comment": "stored stress (kg/ms2)"})
        if index:
            ds.H_SEA.attrs["units"] = "W m-2"
            if conflict == "units":
                ds.SST.attrs.update(units="degC", comment="SST (degC)")
            elif conflict == "quantity":
                ds.SST.attrs["standard_name"] = "sea_water_potential_temperature"
            elif conflict == "statistic":
                ds.SST.attrs["cell_methods"] = "time: mean"
            elif conflict == "support":
                ds.FRAC_SEA.attrs["standard_name"] = "land_area_fraction"
            elif conflict == "grid":
                ds = ds.assign_coords(ni=ds.ni + 250.)
            elif conflict == "provider":
                ds = ds.assign_coords(time=[np.datetime64("2024-12-10T01", "ns")])
            elif conflict == "non_sea":
                ds.PRES.attrs["units"] = "mbar"
        path = tmp_path / f"snapshot-{index}.nc"
        ds.to_netcdf(path)
        paths.append(path)
    source = {"model": "mesonh", "files": list(map(str, paths)),
              "interpretation": "mesonh_surfex_sea",
              "variables": {"2d": ["PRES"] if conflict == "non_sea"
                            else ["SST", "H_SEA", "FMU_SEA"]}}
    if conflict == "opt_out":
        source.pop("interpretation")
    return paths, _configuration(tmp_path, {"surface": source})


@pytest.mark.parametrize("first_units", ["K", None])
def test_equivalent_sea_snapshots_keep_values_and_each_observed_origin(
    tmp_path, monkeypatch, first_units,
):
    paths, conf = _sea_snapshots(tmp_path, first_units=first_units)
    before = [path.read_bytes() for path in paths]
    reads = _payload_guard(monkeypatch, {"SST", "H_SEA", "FMU_SEA", "FRAC_SEA", "PRES", "SSS"})
    _, children, plans = bind_sources(conf)
    assert reads == []
    binding = children["surface"].source_requests["surface"]["binding"]
    assert binding["status"] == "bound"
    records = binding["products"]["model_grid"]["SST"]["records"]
    assert [record["observed_attributes"].get("units") for record in records] == [
        first_units, "kelvin"]
    assert [record["field_metadata"]["origins"]["units"] for record in records] == [
        "units_attribute" if first_units else "source_comment", "units_attribute"]
    assert {r["locator"]["path"] for r in plans["surface"]["records"]} == set(map(str, paths))
    result = execute_simulation(conf)
    assert result.ok, result
    assert {name for name, _ in reads} == {"SST", "H_SEA", "FMU_SEA", "FRAC_SEA"}
    subprocess.run([sys.executable, "-c", """
import sys, json, numpy as np, xarray as xr, yaml
with xr.open_dataset(sys.argv[1]) as out:
    assert out.SST.attrs['units'] == 'K'
    assert out.H_SEA.attrs['units'] == 'W/m2' and out.FMU_SEA.attrs['units'] == 'Pa'
    assert out.time.values.tolist() == np.array(
        ['2024-12-10T01','2024-12-10T02'], dtype='datetime64[ns]').tolist()
    for t in (0,1):
        truth = np.full((7,7), 300.+t)
        truth[[0,-1],:] = np.nan
        truth[:,[0,-1]] = np.nan
        truth[2,2] = np.nan
        truth[3,4] = np.nan
        truth[4,3] = 0.
        np.testing.assert_array_equal(out.SST[t], truth)
        assert out.SST[t,3,3] == 300.+t and out.H_SEA[t,3,3] == 40.+t
        assert out.FMU_SEA[t,3,3] == 2. and out.FRAC_SEA[t,3,3] == .25
provenance = yaml.safe_load(open(sys.argv[2]))
records = provenance['sources']['surface']['interpretation']['metadata_records']
assert len(records) == 8
sst = sorted((r for r in records if r['field'] == 'SST'), key=lambda r:r['time'])
assert [r['source_id'] for r in sst] == ['snapshot-0.nc','snapshot-1.nc']
assert [r['observed_attributes'].get('units') for r in sst] == [
    None if sys.argv[3] == 'None' else 'K', 'kelvin']
assert [r['origins']['units'] for r in sst] == [
    'source_comment' if sys.argv[3] == 'None' else 'units_attribute', 'units_attribute']
assert [r['units'] for r in sst] == ['K','kelvin']
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(conf.output_dir / "run-provenance.yaml"),
                    str(first_units)], check=True, capture_output=True, text=True)
    assert [path.read_bytes() for path in paths] == before


@pytest.mark.parametrize("conflict", [
    "units", "quantity", "statistic", "support", "grid", "provider", "non_sea", "opt_out",
])
def test_sea_snapshot_aliases_do_not_clear_real_or_non_sea_conflicts(
    tmp_path, monkeypatch, conflict,
):
    from frameit.core.preflight import preflight

    paths, conf = _sea_snapshots(tmp_path, conflict=conflict)
    before = [path.read_bytes() for path in paths]
    reads = _payload_guard(monkeypatch, {"SST", "H_SEA", "FMU_SEA", "FRAC_SEA", "PRES", "SSS"})
    with pytest.raises(ValueError, match="distinct fields|competing|contradict"):
        preflight(conf, check_output=False)
    assert reads == [] and not conf.output_dir.exists()
    assert [path.read_bytes() for path in paths] == before


@pytest.mark.parametrize("interpretation", [False, True])
def test_sea_opt_in_reads_only_selected_support_and_preserves_values(
    tmp_path, monkeypatch, interpretation,
):
    path, conf = _sea_case(tmp_path, interpretation=interpretation, invalid_sample=0)
    before = path.read_bytes()
    reads = _payload_guard(monkeypatch, {"SST", "SSS", "H_SEA", "PRES", "FRAC_SEA"})
    _, children, _ = bind_sources(conf)
    assert reads == []
    binding = children["surface"].source_requests["surface"]["binding"]
    assert binding["status"] == "bound"
    assert ("FRAC_SEA" in binding["dependencies"]) is interpretation
    result = execute_simulation(conf)
    assert result.ok, result
    assert {name for name, _ in reads} == (
        {"SST", "H_SEA", "PRES", "FRAC_SEA"} if interpretation else {"SST", "H_SEA", "PRES"})
    assert all(np.atleast_1d(np.arange(3)[key[0]]).tolist() == [1] for _, key in reads)
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    interpreted = sys.argv[2] == 'True'
    np.testing.assert_array_equal(out.PRES, np.full((1,7,7),999.))
    assert out.SST[0,4,3] == 0. and out.H_SEA[0,3,3] == 41.
    assert out.time.values[0] == np.datetime64('2024-12-10T02:00:00')
    if interpreted:
        assert out.SST[0,3,3] == 301. and out.FRAC_SEA[0,3,3] == .25
        assert np.isnan(out.SST[0,3,4]) and np.isnan(out.SST[0,2,2])
        assert np.isnan(out.SST[0,0]).all()
        assert out.SST.attrs['units'] == 'K'
        assert out.SST.attrs['surfex_units_source'] == 'source_comment'
        assert out.H_SEA.attrs['units'] == 'W/m2'
        assert 'cell_methods' not in out.H_SEA.attrs
        assert 'FRAC_SEA' in out.SST.attrs['ancillary_variables'].split()
    else:
        assert out.SST[0,3,4] == 999. and out.SST[0,2,2] == 301.
        assert 'units' not in out.SST.attrs and 'FRAC_SEA' not in out
    assert 'SSS' not in out and out.attrs['frameit_version']
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(interpretation)], check=True, capture_output=True, text=True)
    assert path.read_bytes() == before
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    if interpretation:
        assert provenance["sources"]["surface"]["interpretation"]["method"] == "mesonh_surfex_sea"
        origins = provenance["sources"]["surface"]["field_metadata"]
        assert origins["SST"]["units"] == "source_comment"


def test_sea_invalid_selected_support_fails_at_execution_not_metadata(tmp_path, monkeypatch):
    path, conf = _sea_case(tmp_path, invalid_sample=1)
    reads = _payload_guard(monkeypatch, {"SST", "H_SEA", "PRES", "FRAC_SEA"})
    bind_sources(conf)
    assert reads == []
    with pytest.raises(ValueError, match=r"FRAC_SEA.*\[0,1\]"):
        execute_simulation(conf)
    assert reads and {name for name, _ in reads} == {"FRAC_SEA"}
    assert not list(conf.output_dir.glob("products/*.nc"))


def test_sea_opt_in_with_no_eligible_selection_needs_no_support(tmp_path, monkeypatch):
    path, conf = _sea_case(tmp_path, fields=("PRES",))
    reads = _payload_guard(monkeypatch, {"SST", "SSS", "H_SEA", "PRES", "FRAC_SEA"})
    result = execute_simulation(conf)
    assert result.ok, result
    assert {name for name, _ in reads} == {"PRES"}
    assert path.exists()


def test_sea_internal_fraction_keeps_the_same_missing_value_interpretation(tmp_path):
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

    _, conf = _sea_case(tmp_path, fields=("SST", "FRAC_SEA"))
    _, children, plans = bind_sources(conf)
    binding = children["surface"].source_requests["surface"]["binding"]
    with DatasetResources() as resources:
        user, tracker = concat_nc2ds_by_vert_coord(
            plans["surface"]["files"], {}, {}, selected_records=binding,
            source_plan=plans["surface"], resources=resources)
        exported = next(iter(user.values())).FRAC_SEA
        internal = next(iter(tracker["internal"].values())).FRAC_SEA
        assert np.isnan(internal[0, 0]).all()
        assert internal[0, 3, 3] == .25
        xr.testing.assert_equal(internal, exported)


@pytest.mark.parametrize("regional", [False, True])
def test_public_fa_cube_uses_selected_leaf_and_native_geometry(tmp_path, monkeypatch, regional):
    from frameit.core import coupled
    from frameit.core.settings_class import SimulationConfig
    from frameit.testing.numerical.test_fa_cubes import DECLARATION, fixtures

    paths = fixtures(tmp_path, hours=(0, 1, 2))
    before = [p.read_bytes() for p in paths]
    cube = {"records": [f"S{k:03d}TEMPERATURE" for k in (1, 2, 3)],
            "vertical_position": "mass", "sampling": "center"}
    conf = _configuration(tmp_path, {"atmosphere": {
        "files": list(map(str, paths)), "profile": "arome_history",
        "variables": {"3d": ["temperature"], "levels": {"indices": [2, 0]}},
        "time": {"values": ["2026-01-01T00:00:00", "2026-01-01T02:00:00"]},
        "field_metadata": {"temperature": DECLARATION},
        "native_cubes": {"temperature": cube}, "fa": {"earth_radius_m": 6371229.},
        "reader": {"python_executable": sys.executable, "max_points": 1000,
                   "timeout_seconds": 30},
    }})
    if regional:
        raw = copy.deepcopy(conf.yaml_config)
        raw["region"] = {"center": {"latitude": -20., "longitude": 50.},
                         "width_km": {"x": 6., "y": 4.}}
        conf = SimulationConfig.from_mapping_with_model_preset(raw)
    calls = _fa_requests(monkeypatch)
    native_lookup = coupled._mapped_track
    lookup_calls = []

    def projected_lookup(track, geometry, settings):
        assert geometry.attrs["fa_grid_lookup"] == "fa_source_crs_native_axes_v1"
        assert geometry.attrs["fa_zone_indices"] == [0, 9, 0, 7]
        assert "crs" in geometry
        assert geometry.crs.attrs["grid_mapping_name"] == "lambert_conformal_conic"
        lookup_calls.append(True)
        return native_lookup(track, geometry, settings)

    monkeypatch.setattr(coupled, "_mapped_track", projected_lookup)
    _, children, _ = bind_sources(conf)
    assert calls and all(c["operation"] == "inspect" for c in calls)
    binding = children["atmosphere"].source_requests["atmosphere"]["binding"]
    assert binding["status"] == "bound"
    calls.clear()
    result = execute_simulation(conf)
    assert result.ok, result
    reads = [c for c in calls if c["operation"] == "read"]
    assert len(reads) == 4
    assert {(Path(c["path"]).name, c["fields"][0]) for c in reads} == {
        (f"cube-{hour}.fa", f"S{k:03d}TEMPERATURE") for hour in (0, 2) for k in (3, 1)}
    assert all(c["max_points"] == 1000 and c["timeout_seconds"] == 30 for c in reads)
    assert bool(lookup_calls) is regional
    subprocess.run([sys.executable, "-c", """
import sys, json, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    j,i = np.indices((7,9))
    expected = np.array([[280.+10*k+10*j+i+hour*.5 for k in (3,1)] for hour in (0,2)])
    expected[:,:,1,1] = np.nan
    expected[:,:,2,2] = 0.
    if sys.argv[2] == 'True':
        expected = expected[:,:,1:6,1:8]
        assert out.attrs['fa_grid_lookup'] == 'fa_source_crs_native_axes_v1'
        assert out.center_longitude.values.tolist() == [50.,50.]
    np.testing.assert_array_equal(out.temperature, expected)
    assert out.level.values.tolist() == [3,1]
    assert out.level_source_native_index.values.tolist() == [2,0]
    assert out.temperature_native_record.values.tolist() == ['S003TEMPERATURE','S001TEMPERATURE']
    np.testing.assert_array_equal(out.fa_hybrid_a, [0.,10000.,20000.,0.])
    np.testing.assert_array_equal(out.fa_hybrid_b, [0.,.2,.6,1.])
    assert out.fa_reference_pressure == 100000.
    assert out.fa_hybrid_a.attrs['units'] == 'Pa'
    assert out.temperature.attrs['units'] == 'K'
    descriptor = json.loads(out.temperature.attrs['fa_field_descriptor'])
    assert 'representative input record' in out.temperature.attrs['fa_field_descriptor_scope']
    assert descriptor['units']['origin'] == 'explicit_source.field_metadata'
    assert descriptor['eligibility']['diagnostic'] == 'blocked'
    assert out.time.values.tolist() == np.array(
        ['2026-01-01T00:00:00','2026-01-01T02:00:00'],dtype='datetime64[ns]').tolist()
    assert out.forecast_reference_time.values == np.datetime64('2026-01-01')
    np.testing.assert_array_equal(out.forecast_period, np.array([0,2], dtype='timedelta64[h]'))
    assert set(out.data_vars) >= {'temperature'}
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(regional)], check=True, capture_output=True, text=True)
    assert [p.read_bytes() for p in paths] == before
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    assert provenance["sources"]["atmosphere"]["fa_inputs"]


@pytest.mark.parametrize("factors,allow_unscaled,success", [
    ([2, 1], False, True), (None, False, False), (None, True, True),
])
def test_public_fa_scaling_is_checked_at_decode(
    tmp_path, monkeypatch, factors, allow_unscaled, success,
):
    from frameit.testing.numerical.test_fa_cubes import DECLARATION
    from frameit.testing.numerical.test_fa_epygram_surfex import surface_fixture

    path, truth = surface_fixture(
        tmp_path, packing=120, **({"omit_scaling_section": True} if factors is None
                                 else {"encoded_scaling": factors}))
    before = path.read_bytes()
    conf = _configuration(tmp_path, {"surface": {
        "files": str(path), "profile": "surfex_history",
        "variables": {"2d": ["SFX.T2M"]},
        "field_metadata": {"SFX.T2M": {**DECLARATION, "allow_unscaled": allow_unscaled}},
    }})
    calls = _fa_requests(monkeypatch)
    bind_sources(conf)
    assert all(c["operation"] == "inspect" for c in calls)
    if not success:
        with pytest.raises(ValueError, match="unresolved native scaling"):
            execute_simulation(conf)
        assert not list(conf.output_dir.glob("products/*.nc"))
    else:
        result = execute_simulation(conf)
        assert result.ok, result
        with xr.open_dataset(result.products[0]["path"]) as out:
            np.testing.assert_allclose(out["SFX.T2M"][0], truth / (20. if factors else 1.),
                                       rtol=0, atol=(512. / 2**24) / (20. if factors else 1.),
                                       equal_nan=True)
            assert out["SFX.T2M"][0,2,2] == 0.
            assert np.isnan(out["SFX.T2M"][0,1,1])
        subprocess.run([sys.executable, "-c", """
import sys, json, numpy as np, xarray as xr, yaml
with xr.open_dataset(sys.argv[1]) as out:
    j,i = np.indices((7,9))
    truth = 280.+10*j+i
    truth[1,1] = np.nan
    truth[2,2] = 0.
    divisor = float(sys.argv[2])
    np.testing.assert_allclose(out['SFX.T2M'][0], truth/divisor,
                               rtol=0, atol=(512./2**24)/divisor, equal_nan=True)
    assert out['SFX.T2M'].attrs['units'] == 'K'
    assert out.time.values[0] == np.datetime64('2026-01-01T01:00:00')
provenance = yaml.safe_load(open(sys.argv[3]))
facts = provenance['sources']['surface']['fa_decoder']['field_observations']
assert facts
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"], str(20. if factors else 1.),
                        str(conf.output_dir / "run-provenance.yaml")],
                       check=True, capture_output=True, text=True)
        provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
        assert provenance["sources"]["surface"]["fa_inputs"][0]["decoder_log"]
    assert any(c["operation"] == "read" for c in calls)
    assert path.read_bytes() == before


def test_public_fa_native_component_needs_no_pair_or_basis(tmp_path, monkeypatch):
    from frameit.testing.numerical.test_fa_cubes import DECLARATION, fixtures

    paths = fixtures(tmp_path, winds=True)
    before = paths[0].read_bytes()
    conf = _configuration(tmp_path, {"atmosphere": {
        "profile": "arome_history", "files": str(paths[0]),
        "variables": {"3d": ["u_native"], "levels": {"indices": [1]}},
        "native_cubes": {"u_native": {
            "records": [f"S{k:03d}WIND.U.PHYS" for k in (1, 2, 3)],
            "sampling": "center", "vertical_position": "mass"}},
        "field_metadata": {"u_native": {**DECLARATION, "units": "m s-1"}},
        "fa": {"earth_radius_m": 6371229.},
    }})
    calls = _fa_requests(monkeypatch)
    result = execute_simulation(conf)
    assert result.ok, result
    reads = [c for c in calls if c["operation"] == "read"]
    assert len(reads) == 1 and reads[0]["fields"] == ["S002WIND.U.PHYS"]
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    angle = -np.sin(np.deg2rad(-20.))*np.deg2rad(out.longitude.values-50.)
    expected = 3*np.cos(angle)+4*np.sin(angle)
    expected[1,1] = np.nan
    np.testing.assert_allclose(out.u_native[0,0], expected, rtol=0, atol=1e-12, equal_nan=True)
    assert out.u_native.attrs['units'] == 'm s-1'
    assert out.level.values.tolist() == [2] and out.level_source_native_index.values.tolist() == [1]
    assert not any('WIND.V' in n or n in {'v_native','wind_speed'} for n in out)
    assert 'wind_reference_frame' not in out.u_native.attrs
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"]], check=True, capture_output=True, text=True)
    assert paths[0].read_bytes() == before


def test_interpretation_does_not_clear_transform_work(tmp_path, monkeypatch):
    path, original = _sea_case(tmp_path)
    from frameit.core.settings_class import SimulationConfig

    raw = copy.deepcopy(original.yaml_config)
    raw["sources"]["surface"]["transforms"] = [{"fields": ["SST"], "units": "degC"}]
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    reads = _payload_guard(monkeypatch, {"SST", "H_SEA", "FRAC_SEA", "PRES"})
    with pytest.raises(ValueError, match="incompatible or unsupported units"):
        execute_simulation(conf)
    assert reads == [] and not conf.output_dir.exists()
    assert path.exists()


def test_metadata_preflight_reports_declarations_without_mask_values(tmp_path, monkeypatch):
    from frameit.core.preflight import preflight

    _, conf = _sea_case(tmp_path, invalid_sample=1)
    reads = _payload_guard(monkeypatch, {"SST", "H_SEA", "FRAC_SEA", "PRES"})
    report = preflight(conf, check_output=False)
    assert reads == []
    source = report["sources"]["surface"]
    assert source["metadata_origins"]["field_metadata"]["SST"]["units"] == "source_comment"
    assert source["requests"]["binding"] is None
    assert source["interpretation"]["pending_value_checks"]


def test_sea_declaration_can_complete_missing_units_but_not_replace_comment(tmp_path):
    from frameit.core.preflight import preflight
    from frameit.core.settings_class import SimulationConfig

    path, original = _sea_case(tmp_path, fields=("SST",))
    with xr.open_dataset(path) as opened:
        ds = opened.load()
    ds.SST.attrs = {}
    ds.to_netcdf(path, mode="w")
    raw = copy.deepcopy(original.yaml_config)
    raw["sources"]["surface"]["field_metadata"] = {"SST": {"units": "K"}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    report = preflight(conf, check_output=False)
    origins = report["sources"]["surface"]["metadata_origins"]["field_metadata"]
    assert origins["SST"]["units"] == "declaration"
    result = execute_simulation(conf)
    assert result.ok
    with xr.open_dataset(result.products[0]["path"]) as out:
        assert out.SST.attrs["surfex_units_source"] == "declaration"
    ds.SST.attrs["comment"] = "SST (degC)"
    ds.to_netcdf(path, mode="w")
    with pytest.raises(ValueError, match="contradict"):
        preflight(SimulationConfig.from_mapping_with_model_preset(raw), check_output=False)


@pytest.mark.parametrize("contradiction", [False, True])
def test_grib_declarations_do_not_replace_native_header_or_request_companion(
    tmp_path, monkeypatch, contradiction,
):
    import eccodes as ec

    from frameit.testing.numerical.test_v3_grib_reads import write_messages

    path = write_messages(tmp_path / "u.grib", [{"hour": 1}, {"hour": 2}])
    before = path.read_bytes()
    conf = _configuration(tmp_path, {"atmosphere": {
        "model": "arome", "files": str(path),
        "variables": {"3d": ["u"]}, "time": {"values": ["2026-01-01T02:00:00"]},
        "field_metadata": {"u": {"units": "km h-1" if contradiction else "m/s",
                                 "kind": "continuous", "temporal_kind": "instantaneous"}},
    }})
    native, reads = ec.codes_get_values, []

    def observed(handle, *args, **kwargs):
        reads.append(tuple(ec.codes_get(handle, key) for key in (
            "paramId", "dataTime", "endStep", "level")))
        return native(handle, *args, **kwargs)

    monkeypatch.setattr(ec, "codes_get_values", observed)
    if contradiction:
        with pytest.raises(ValueError, match="contradict"):
            execute_simulation(conf)
        assert reads == [] and not conf.output_dir.exists()
    else:
        result = execute_simulation(conf)
        assert result.ok, result
        assert reads == [(131, 0, 2, 850)]
        subprocess.run([sys.executable, "-c", """
import sys,json,numpy as np,xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    assert set(out.data_vars) == {'u'}
    np.testing.assert_array_equal(out.u[0,0], [[0.,2851.,np.nan],[9999.,2854.,2855.]])
    assert out.u.attrs['units'] == 'm s**-1'
    assert out.u.attrs['kind'] == 'continuous'
    assert json.loads(out.u.attrs['frameit_metadata_origins'])['units'] == 'input'
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", result.products[0]["path"]], check=True, capture_output=True, text=True)
    assert path.read_bytes() == before
