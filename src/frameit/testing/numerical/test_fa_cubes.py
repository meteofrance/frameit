"""Independent P5 columns, native indices/masks and isolated EPyGrAM admission."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.configuration import resolved_configuration
from frameit.core.execution import execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.io.fa_backend import request_fa
from frameit.io.fa_cubes import cube_layouts, hybrid_contract
from frameit.io.fa_utils import concat_fa2ds_by_vert_coord
from frameit.testing.numerical.test_fa_geometry import spherical_lambert

EPYTHON = os.environ.get("FRAMEIT_TEST_EPYGRAM_PYTHON") or (
    sys.executable if importlib.util.find_spec("epygram") is not None else None)
NATIVE = pytest.mark.skipif(EPYTHON is None, reason="optional EPyGrAM helper not installed")
HYBRID = {"a_normalized": [0., .1, .2, 0.], "b": [0., .2, .6, 1.],
          "reference_pressure_pa": 100000.}
DECLARATION = {"units": "K", "kind": "continuous", "temporal_kind": "instantaneous"}


def document(directory, files, *, latitude=-20., synchronous=True):
    return {
        "schema_version": 2, "model": "arome", "run": {"name": "native-cubes"},
        "input": {"format": "fa", "files": [str(p) for p in files], "fa": {
            "backend": "epygram", "python_executable": EPYTHON, "profile": "arome_history",
            "earth_radius_m": 6371229., "field_metadata": {
                "temperature": DECLARATION,
                "w_if": {**DECLARATION, "units": "m s-1"}},
            "native_cubes": {
                "temperature": {"records": [f"S{k:03d}TEMPERATURE" for k in (1, 2, 3)],
                                "vertical_position": "mass", "sampling": "center"},
                "w_if": {"records": [f"S{k:03d}VERTIC.VELOC" for k in range(1, 5)],
                         "vertical_position": "interface", "sampling": "center"}}}},
        "variables": {"level": {"names": ["temperature"], "levels": {"indices": [2, 0]}},
                      "level_w": {"names": ["w_if"], "levels": {"indices": [3, 0]}}},
        "tracking": {"method": "fixed_box", "fixed_box": {
            "center": {"latitude": latitude, "longitude": 50.}}},
        "domain": {"size_km": {"x": 6., "y": 4.}},
        "output": {"directory": str(directory / "run"), "synchronous_export": synchronous,
                   "max_workers": 1},
    }


def fixtures(directory, *, hours=(0,), latitude=-20., winds=False, second_reference=None,
             zero_cell=True):
    j, i = np.indices((7, 9))
    xx, yy = np.meshgrid(np.arange(-4, 5) * 1000., np.arange(-3, 4) * 1000.)
    lon, _ = spherical_lambert(xx, yy, 6371229., latitude)
    # Independent spherical conformal-grid convergence, not FrameIt's rotation.
    angle = -np.sin(np.deg2rad(latitude)) * np.deg2rad(lon - 50.)
    requests, paths = [], []
    for index, hour in enumerate(hours):
        path = directory / f"cube-{hour}.fa"
        paths.append(path)
        fields = []
        for k in (1, 2, 3):
            values = 280. + 10 * k + 10 * j + i + hour * .5
            values[1, 1] = np.nan
            if zero_cell:
                values[2, 2] = 0.
            fields.append({"name": f"S{k:03d}TEMPERATURE", "values": values.tolist()})
            if winds:
                for component, values in (
                    ("U", 3 * np.cos(angle) + 4 * np.sin(angle)),
                    ("V", -3 * np.sin(angle) + 4 * np.cos(angle)),
                ):
                    values[1, 1] = np.nan
                    fields.append({"name": f"S{k:03d}WIND.{component}.PHYS",
                                   "values": values.tolist()})
        for k in range(1, 5):
            values = k + j * .1 + i * .01 + hour * .5
            values[1, 1] = np.nan
            fields.append({"name": f"S{k:03d}VERTIC.VELOC", "values": values.tolist()})
        hybrid = copy.deepcopy(HYBRID)
        if index and second_reference is not None:
            hybrid["reference_pressure_pa"] = second_reference
        requests.append({"path": str(path), "hours": hour, "projection_latitude": latitude,
                         "atmospheric_fields": fields, "hybrid_header": hybrid})
    result = subprocess.run([EPYTHON, "-m", "frameit.testing.fa_fixture"],
                            input=json.dumps(requests), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    for path in paths:
        path.chmod(0o444)
    return paths


def test_explicit_cube_schema_replay_and_admission_failures(tmp_path):
    raw = document(tmp_path, [tmp_path / "unopened.fa"])
    raw["input"]["grid_spacing_m"] = 1000.
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    restored = SimulationConfig.from_mapping_with_model_preset(resolved_configuration(conf))
    assert restored.fa_options == conf.fa_options
    assert conf.fa_options["python_executable"] == EPYTHON  # Preserve venv symlinks.
    for key, value, message in (
        ("backend", "native", "native_cubes require backend"),
        ("python_executable", "", "interpreter path"),
    ):
        bad = copy.deepcopy(raw)
        bad["input"]["fa"][key] = value
        with pytest.raises(ValueError, match=message):
            SimulationConfig.from_mapping_with_model_preset(bad)
    for key, value, message in (
        ("sampling", "u_face", "center sampling"),
        ("component_scaling", "map_scaled", "scaling is gated"),
        ("vertical_position", "pressure", "mass or interface"),
        ("records", ["S*TEMPERATURE"], "invalid or repeated"),
    ):
        bad = copy.deepcopy(raw)
        bad["input"]["fa"]["native_cubes"]["temperature"][key] = value
        with pytest.raises(ValueError, match=message):
            SimulationConfig.from_mapping_with_model_preset(bad)
    bad = copy.deepcopy(raw)
    bad["variables"]["level"]["levels"] = "physical"
    with pytest.raises(ValueError, match="physical-coordinate selection is gated"):
        SimulationConfig.from_mapping_with_model_preset(bad)
    assert not (tmp_path / "unopened.fa").exists()


def test_hybrid_units_reference_pressure_and_invalid_columns():
    header = {"KNIVER": 3, "PREFER": 100000., "PAHYBR": [0., .1, .2, 0.],
              "PBHYBR": [0., .2, .6, 1.]}
    contract = hybrid_contract(header)
    assert contract["a_pa"] == [0., 10000., 20000., 0.]
    assert contract["reference_pressure_pa"] == 100000.  # not EPyGrAM's 101325 default
    assert contract["interface_indices"] == [1, 2, 3, 4]
    assert contract["coefficient_storage_indices"] == [0, 1, 2, 3]
    assert contract["mass_coefficient_policy"] == "not inferred"
    assert contract["physical_coordinates"] == "not computed"
    for change in ({"PREFER": 0.}, {"PAHYBR": [0., .1]}, {"PBHYBR": [0., np.nan, .6, 1.]}):
        with pytest.raises(ValueError, match="Invalid FA native hybrid header"):
            hybrid_contract({**header, **change})
    info = {"geometry": header, "field_descriptors": {"S001X": {"sampling": {"epygram": {
        "type_of_first_fixed_surface": 100, "levels": [850]}}}}}
    options = {"native_cubes": {"x": {"records": ["S001X"], "vertical_position": "mass",
                                     "sampling": "center"}}}
    with pytest.raises(ValueError, match="evidenced native hybrid level"):
        cube_layouts(info, options, ["x"])


def test_epygram_optionality_and_native_contradictions(tmp_path, monkeypatch):
    from frameit.io import fa_epygram

    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(fa_epygram, "version", missing)
    with pytest.raises(ValueError, match="install FrameIt\\[fa-epygram\\]"):
        fa_epygram.initialize(tmp_path, None)
    with pytest.raises(ValueError, match="Cannot launch the FA helper"):
        request_fa({"operation": "inspect", "path": "unopened.fa",
                    "python_executable": str(tmp_path / "missing-python")})
    vertical = SimpleNamespace(typeoffirstfixedsurface=119, levels=[2], position_on_grid="mass",
                               grid={"ABgrid_position": "flux", "gridlevels": [
                                   (1, {"Ai": 0., "Bi": 0.}), (2, {"Ai": 1., "Bi": 1.})]})
    with pytest.raises(ValueError, match="contradict native PREFER/A/B"):
        hybrid_contract({"KNIVER": 1, "PAHYBR": [0., .1], "PBHYBR": [0., 1.],
                         "PREFER": 100000.}, vertical)
    result = subprocess.run([sys.executable, "-c", """
import importlib.abc, sys
class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'epygram', 'falfilfa4py', 'eccodes', 'ectrans4py'}:
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, NoNative())
import frameit.io.fa_epygram, frameit.io.fa_cubes, frameit.io.fa_worker
assert 'epygram' not in sys.modules
"""], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@NATIVE
@pytest.mark.parametrize("synchronous", [True, False])
def test_native_cube_export_indices_coefficients_masks_and_sparse_decodes(tmp_path, synchronous):
    from netCDF4 import Dataset
    # Parent GRIB remains usable before and after the different FA native stack.
    ec = pytest.importorskip("eccodes")
    message = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    ec.codes_release(message)

    paths = fixtures(tmp_path, hours=(0, 1))
    before = [p.read_bytes() for p in paths]
    raw = document(tmp_path, paths, synchronous=synchronous)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    preview = preflight(conf)
    assert not conf.output_dir.exists()
    assert preview["selected_levels"][0]["source_native_indices"] == [2, 0]
    assert preview["fa_inputs"][0]["hybrid_contract"]["a_pa"] == [0., 10000., 20000., 0.]
    result = execute_simulation(conf)
    assert result.ok, result.error
    products = {p["group"]: p["path"] for p in result.products if p["role"] == "cart"}
    assert set(products) == {"level", "level_w"}
    j, i = np.indices((7, 9))
    with Dataset(products["level"]) as data:
        assert data.variables["level"][:].tolist() == [3, 1]
        assert data.variables["level_source_native_index"][:].tolist() == [2, 0]
        assert data.variables["level"].units == "1"
        assert data.variables["fa_hybrid_a"].units == "Pa"
        np.testing.assert_array_equal(data.variables["fa_hybrid_a"][:], [0, 10000, 20000, 0])
        assert data.variables["fa_reference_pressure"][...] == 100000.
        records = data.variables["temperature_native_record"][:].tolist()
        assert records == ["S003TEMPERATURE", "S001TEMPERATURE"]
        expected = np.stack([280. + 10 * k + 10 * j + i for k in (3, 1)])
        expected[:, 1, 1] = np.nan
        expected[:, 2, 2] = 0.
        np.testing.assert_allclose(data.variables["temperature"][0].filled(np.nan),
                                   expected[:, 1:6, 1:8], rtol=0, atol=0, equal_nan=True)
        assert not {"pressure", "height", "altitude", "surface_pressure"} & data.variables.keys()
    with Dataset(products["level_w"]) as data:
        assert data.variables["level_w"][:].tolist() == [4, 1]
        assert data.variables["level_w_source_native_index"][:].tolist() == [3, 0]
        assert data.dimensions["fa_hybrid_interface"].size == 4
        assert "level" not in data.dimensions
    reader = subprocess.run([sys.executable, "-c", """
import json, sys, numpy as np
from netCDF4 import Dataset
products = json.loads(sys.argv[1])
with Dataset(products['level']) as ds:
    assert ds.variables['level'][:].tolist() == [3, 1]
    assert ds.variables['fa_hybrid_a'].units == 'Pa'
    np.testing.assert_array_equal(ds.variables['fa_hybrid_a'][:], [0, 10000, 20000, 0])
    values = ds.variables['temperature'][0].filled(np.nan)
    assert np.isnan(values[0, 0, 0]) and values[0, 1, 1] == 0
with Dataset(products['level_w']) as ds:
    assert ds.variables['level_w'][:].tolist() == [4, 1]
    assert ds.dimensions['fa_hybrid_interface'].size == 4
assert not {'frameit', 'epygram', 'falfilfa4py'} & sys.modules.keys()
""", json.dumps(products)], capture_output=True, text=True, timeout=30)
    assert reader.returncode == 0, reader.stdout + reader.stderr
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    assert provenance["fa_inputs"][0]["backend_versions"]["EPyGrAM"] == "2.1.0"
    logs = [json.loads(line) for log in (conf.output_dir / "logs").glob("fa-decoder-*.jsonl")
            for line in log.read_text().splitlines()]
    decoded = {name for record in logs for name in record["fields"]}
    assert decoded == {"S003TEMPERATURE", "S001TEMPERATURE",
                       "S004VERTIC.VELOC", "S001VERTIC.VELOC"}
    assert [p.read_bytes() for p in paths] == before
    assert "epygram" not in sys.modules and "falfilfa4py" not in sys.modules
    message = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    ec.codes_release(message)


@NATIVE
def test_source_vertical_conflicts_and_unavailable_labels_fail(tmp_path):
    paths = fixtures(tmp_path, hours=(0, 1), second_reference=101325.)
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, paths))
    with pytest.raises(ValueError, match="incompatible native vertical"):
        preflight(conf)
    with pytest.raises(ValueError, match="incompatible native vertical"):
        concat_fa2ds_by_vert_coord(paths, conf.requests_user(), {}, wind_conf=conf)
    raw = document(tmp_path, paths[:1])
    raw["variables"]["level"]["levels"] = {"values": [850]}
    with pytest.raises(ValueError, match="no pressure matching"):
        preflight(SimulationConfig.from_mapping_with_model_preset(raw))


@NATIVE
@pytest.mark.parametrize("latitude", [-20., 20.])
def test_native_and_analysis_winds_basis_masks_neighbours_and_idempotence(tmp_path, latitude):
    from frameit.processing.derived.wind import normalize_winds

    paths = fixtures(tmp_path, latitude=latitude, winds=True)
    raw = document(tmp_path, paths, latitude=latitude)
    raw["variables"] = {"level": {"names": ["u"], "levels": {"indices": [2]}}}
    raw["input"]["wind_pairs"] = [{"group": "level", "u": "u", "v": "v",
                                   "reference_frame": "grid",
                                   "rotation": {"method": "geolocation"}}]
    for variable, component in (("u", "U"), ("v", "V")):
        raw["input"]["fa"]["field_metadata"][variable] = {**DECLARATION, "units": "m s-1"}
        raw["input"]["fa"]["native_cubes"][variable] = {
            "records": [f"S{k:03d}WIND.{component}.PHYS" for k in (1, 2, 3)],
            "vertical_position": "mass", "sampling": "center", "vector_basis": "grid",
            "component_scaling": "physical_velocity"}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    from frameit.core.preflight import wind_dependencies

    expanded, _ = wind_dependencies(conf, conf.requests_user())
    native = {}
    groups, _ = concat_fa2ds_by_vert_coord(paths, expanded, {}, wind_conf=conf,
                                         native_output_groups=native)
    assert set(groups["level"].data_vars) == {"u", "v"}  # required companion, selected level only
    assert groups["level"].level.values.tolist() == [3]
    analyzed = normalize_winds(groups["level"], conf, "level").compute()
    # Finite-neighbour WGS84 geolocation differs slightly from exact spherical
    # convergence. At 1-km spacing/8-km extent, 5e-4 m/s bounds one-sided direction
    # and ellipsoid effects for this 5-m/s vector; it is not a production error bound.
    for name, truth in (("u", 3.), ("v", 4.)):
        values = analyzed[name].values
        assert np.isnan(values[0, 0, 1, 1])
        assert np.count_nonzero(np.isfinite(values)) == 62
        np.testing.assert_allclose(values[np.isfinite(values)], truth, rtol=0, atol=5.e-4)
    xr.testing.assert_identical(normalize_winds(analyzed, conf, "level"), analyzed)
    assert native["level"].u.attrs["wind_reference_frame"] == "grid"
    assert "frameit_wind_prepared" not in native["level"].u.attrs
    raw["variables"]["level"]["names"] = ["u", "v"]
    raw["output"]["cartesian"] = {"horizontal_winds": "native"}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    product = next(p["path"] for p in result.products if p["role"] == "cart")
    with xr.open_dataset(product, engine="netcdf4") as data:
        assert "wind_speed" not in data
        assert data.u.attrs["wind_reference_frame"] == "grid"
        assert "frameit_wind_prepared" not in data.u.attrs
        assert data.level.values.tolist() == [3]
    if latitude > 0:
        speed = copy.deepcopy(raw)
        speed["variables"]["level"]["names"] = ["wind_speed"]
        speed["output"]["directory"] = str(tmp_path / "selected-speed")
        result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(speed))
        product = next(p["path"] for p in result.products if p["role"] == "cart")
        with xr.open_dataset(product, engine="netcdf4") as data:
            assert not {"u", "v"} & set(data.data_vars)
            values = data.wind_speed.values
            assert np.isfinite(values).any()
            np.testing.assert_allclose(values[np.isfinite(values)], 5., rtol=0, atol=1.e-12)
    raw["input"]["fa"]["native_cubes"]["u"]["vector_basis"] = "earth"
    with pytest.raises(ValueError, match="wind basis/scaling must match"):
        preflight(SimulationConfig.from_mapping_with_model_preset(raw))
    raw["input"]["fa"]["native_cubes"]["u"]["vector_basis"] = "grid"
    raw["input"]["fa"]["field_metadata"]["u"]["units"] = "K"
    with pytest.raises(ValueError, match="velocity|units"):
        preflight(SimulationConfig.from_mapping_with_model_preset(raw))


@NATIVE
def test_private_epygram_configuration_and_metadata_only_cli(tmp_path, monkeypatch, capsys):
    from frameit.cli import _build_parser, _cmd_inspect

    paths = fixtures(tmp_path)
    home = tmp_path / "private-home"
    (home / ".epygram").mkdir(parents=True)
    (home / ".epygram" / "userconfig.py").write_text("raise RuntimeError('private config used')")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GRIB_DEFINITION_PATH", "/invalid-parent-only")
    args = _build_parser().parse_args([
        "inspect", str(tmp_path), "--model", "arome", "--format", "fa", "--pattern", "cube-*.fa",
        "--fa-profile", "arome_history", "--fa-backend", "epygram", "--fa-python", EPYTHON,
        "--fa-fields", "S003TEMPERATURE"])
    assert _cmd_inspect(args) == 0
    report = yaml.safe_load(capsys.readouterr().out)
    metadata = report["inputs"][0]["field_descriptors"]["S003TEMPERATURE"]
    assert metadata["sampling"]["epygram"]["levels"] == [3]
    assert metadata["mask"]["undefined"] == "not_read"
    assert report["inputs"][0]["backend_versions"]["EPyGrAM"] == "2.1.0"
    assert os.environ["HOME"] == str(home) and paths[0].exists()


@NATIVE
def test_polar_cube_keeps_native_full_and_interface_axes(tmp_path):
    pytest.importorskip("xesmf")
    # This case uses exactly additive vertical offsets for a bilinear linearity
    # oracle. The independent native-export cases above separately retain zeros.
    paths = fixtures(tmp_path, zero_cell=False)
    raw = document(tmp_path, paths)
    raw["polar"] = {"enabled": True, "radial_step_m": 1000., "azimuth_count": 8}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    preview = preflight(conf)
    assert any(path.endswith(".polar.level_w.nc") for path in preview["planned_products"])
    result = execute_simulation(conf)
    products = {p["group"]: p["path"] for p in result.products if p["role"] == "polar"}
    assert set(products) == {"level", "level_w"}
    with xr.open_dataset(products["level"], engine="netcdf4") as data:
        assert data.level.values.tolist() == [3, 1]
        assert data.fa_hybrid_a.attrs["units"] == "Pa"
        difference = (data.temperature.isel(level=0) - data.temperature.isel(level=1)).values
        assert np.isfinite(difference).all()
        np.testing.assert_allclose(difference[np.isfinite(difference)], 20., rtol=0, atol=1.e-12)
    with xr.open_dataset(products["level_w"], engine="netcdf4") as data:
        assert data.level_w.values.tolist() == [4, 1]
        assert data.w_if.attrs["fa_vertical_position"] == "interface"
        assert data.fa_hybrid_interface.values.tolist() == [1, 2, 3, 4]
