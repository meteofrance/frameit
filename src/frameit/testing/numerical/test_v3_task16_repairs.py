"""Regressions for the maintainer's bounded Task16 repairs, not qualification."""

import re

import numpy as np
import pytest
import xarray as xr

from frameit.core.coupled import bind_sources
from frameit.core.execution import execute_simulation
from frameit.core.preflight import collect_preflight
from frameit.core.settings_class import SimulationConfig

from .test_croco_netcdf import croco_document
from .test_croco_vectors import vector_scene
from .test_v3_polar import configuration, ordinary_reader, scene


@pytest.mark.parametrize("shared,minimum", [(False, 1.), (True, 2.)])
def test_validate_reports_a_copyable_input_dependent_radial_minimum(
        tmp_path, monkeypatch, shared, minimum):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    sources = {}
    for name, model, spacing in (
            [("atmosphere", "mesonh", 1000.), ("ocean", "nemo", 2000.)]
            if shared else [("atmosphere", "mesonh", 1000.)]):
        value = scene(spacing=spacing)
        if model == "nemo":
            value = value.rename(time="time_counter", nj="y", ni="x",
                                 latitude="nav_lat", longitude="nav_lon")
        path = tmp_path / f"{name}.nc"
        value.to_netcdf(path)
        sources[name] = {"model": model, "files": str(path), "variables": {"2d": ["q"]}}
    original = H5NetCDFArrayWrapper.__getitem__

    def metadata_only(self, key):
        if self.variable_name == "q":
            raise AssertionError("Validation must not read q payloads")
        return original(self, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", metadata_only)
    options = {"radius_km": 5., "azimuth_count": 8, "radial_step_km": .5,
               "shared_grid": shared}
    conf = configuration(tmp_path, sources=sources, products={"polar": options})
    with monkeypatch.context() as guard:
        from frameit.io.loader import DatasetResources

        def no_files(*args, **kwargs):
            raise AssertionError("Schema-only validation must not open input files")

        guard.setattr(DatasetResources, "open_netcdf", no_files)
        assert not collect_preflight(conf, schema_only=True).errors
    report = collect_preflight(conf)
    assert report.errors
    message = "\n".join(error.message for error in report.errors)
    assert "not supported yet" in message
    found = re.search(r"minimum supported radial_step_km=([0-9.e+-]+)", message)
    assert found, message
    assert float(found[1]) == minimum
    assert not conf.output_dir.exists()
    options["radial_step_km"] = float(found[1])
    corrected = collect_preflight(configuration(
        tmp_path, sources=sources, products={"polar": options}))
    assert not corrected.errors, corrected.errors


@pytest.mark.parametrize("w_only", [False, True])
@pytest.mark.parametrize("units,interface_values,mass_values", [
    ("m", [10., 0.], [15., 5.]), ("km", [.01, 0.], [.015, .005]),
])
def test_grouped_interface_indices_keep_native_w_and_corresponding_mass_targets(
        tmp_path, w_only, units, interface_values, mass_values):
    from .test_grid_representations import native_scene

    path = tmp_path / "input.nc"
    native_scene().to_netcdf(path)
    before = path.read_bytes(), path.stat().st_mtime_ns
    groups = {"level_w": {
        "names": ["WT"], "levels": {"indices": [2, 1], "units": units}}}
    if not w_only:
        groups["level"] = {
            "names": ["UT", "VT"], "levels": {"values": mass_values, "units": units}}
    source = {"variables": {"3d": groups},
              "field_metadata": {f"{group}.{name}": {"kind": "continuous"}
                                 for group, spec in groups.items() for name in spec["names"]}}
    if not w_only:
        source["transforms"] = [{"fields": ["level.UT", "level.VT"], "sampling": "mass"}]
    polar = {"radius_km": 2.5, "azimuth_count": 8,
             "field_options": {"atmosphere": {
                 f"{group}.{name}": {"sampling": "mass"}
                 for group, spec in groups.items() for name in spec["names"]}}}
    conf = configuration(tmp_path, source=source,
                         products={"model_grid": True, "polar": polar})
    result = execute_simulation(conf)
    for product in result.products:
        with xr.open_dataset(product["path"]) as saved:
            if product["role"] == "model_grid":
                np.testing.assert_array_equal(saved.level_w, interface_values)
                assert saved.level_w.attrs["units"] == units
                np.testing.assert_allclose(saved["level_w.WT"].isel(level_w=0), 100.)
                np.testing.assert_allclose(saved["level_w.WT"].isel(level_w=1), 70.)
            else:
                np.testing.assert_array_equal(saved.level, mass_values)
                assert saved.level.attrs["units"] == units
                np.testing.assert_allclose(
                    saved["level_w.WT"].isel(radius=0, azimuth=0), [[115., 85.]], atol=1e-12)
        if product["role"] == "polar":
            ordinary_reader(
                product["path"], fields=[f"{group}.{name}" for group, spec in groups.items()
                                         for name in spec["names"]],
                origin_values={"level_w.WT": [[115., 85.]]})
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize("file_count", [1, 2])
def test_croco_current_analysis_keeps_proven_static_mask_across_time_split_files(
        tmp_path, file_count):
    paths = []
    for index in range(file_count):
        path = tmp_path / f"ocean-{index}.nc"
        value = vector_scene()
        (value if file_count == 1 else value.isel(time=[index])).to_netcdf(path)
        paths.append(path)
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    raw = croco_document(tmp_path, paths, variables={"3d": ["u"]})
    raw["sources"]["ocean"]["wind_pairs"] = [
        {"u": "u", "v": "v", "basis": "grid",
         "rotation": {"method": "coordinate", "coordinate": "angle"}}]
    raw["sources"]["ocean"]["transforms"] = [
        {"fields": ["u"], "sampling": "mass", "basis": "earth"}]
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert saved.time.size == 2
        np.testing.assert_allclose(saved.u, -4., atol=1e-12)
        assert saved.u.attrs["current_reference_frame"] == "earth"
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths} == before


@pytest.mark.parametrize("units", ["degree_north", "degree_east"])
def test_polar_accepts_registry_geographic_degree_spellings_without_rounding(units):
    from frameit.processing.polar.contracts import geographic_degrees

    coordinate = xr.DataArray([-20., -19.9], attrs={"units": units})
    xr.testing.assert_identical(geographic_degrees(coordinate), coordinate)


def test_original_mnh_physical_value_catalogue_rejects_incompatible_destination_values(tmp_path):
    from frameit.testing.catalog import load_cases, resolve_case
    from frameit.testing.datasets import ci_dataset_root

    case, = load_cases(patterns=("mnh_chido_fixed_values_polar",))
    resolved = resolve_case(case, ci_dataset_root(), tmp_path / "out")
    assert resolved["preflight"] == "INVALID_INPUT", resolved["reason"]
    assert "unavailable level value 0" in resolved["reason"]
    groups = resolved["config"]["sources"]["atmosphere"]["variables"]["3d"]
    assert groups["level"]["levels"]["values"] == [5., 25., 65.]
    assert groups["level_w"]["levels"]["values"] == [0., 20., 50.]
    assert resolved["expected"]["levels"]["level"] == [5., 25., 65.]
    assert resolved["expected"]["levels"]["level_w"] == [0., 20., 50.]
    assert "products" not in resolved["expected"]
    assert not (tmp_path / "out").exists()


def test_model_grid_preview_uses_destination_axes_after_mass_collocation(tmp_path):
    from .test_grid_representations import native_scene

    native_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, source={
        "variables": {"3d": ["UT", "VT"], "levels": {"indices": [1]}},
        "transforms": [{"fields": ["UT", "VT"], "sampling": "mass"}],
    }, products={"model_grid": True})
    report = collect_preflight(conf)
    assert not report.errors, report.errors
    product, = report.facts["products"]
    assert product["dimensions"] == {
        "UT": ["time", "level", "y", "x"], "VT": ["time", "level", "y", "x"]}


@pytest.mark.parametrize("analysis", [False, True])
def test_croco_support_validation_respects_selection_and_native_copy_optionality(
        tmp_path, monkeypatch, analysis):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    paths = []
    for index in (0, 1):
        value = vector_scene().isel(time=[index]).copy(deep=True)
        if index:
            value.mask_rho[2, 2] = 0
            value.angle[2, 2] += .1
        path = tmp_path / f"ocean-{index}.nc"
        value.to_netcdf(path)
        paths.append(path)
    raw = croco_document(tmp_path, paths, variables={"3d": ["u" if analysis else "temp"]})
    if analysis:
        raw["sources"]["ocean"].update(
            time={"values": ["2024-12-10T01:00:00"]},
            wind_pairs=[{"u": "u", "v": "v", "basis": "grid",
                         "rotation": {"method": "coordinate", "coordinate": "angle"}}],
            transforms=[{"fields": ["u"], "sampling": "mass", "basis": "earth"}])
    original = H5NetCDFArrayWrapper.__getitem__

    def metadata_only(self, key):
        forbidden = {"u", "v", "temp", "salt", "zeta"} | (
            set() if analysis else {"angle", "mask_rho"})
        if self.variable_name in forbidden:
            raise AssertionError(f"Unselected/physical payload read: {self.variable_name}")
        return original(self, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", metadata_only)
    report = collect_preflight(raw, check_output=False)
    assert not report.errors, report.errors


def test_croco_reader_checks_admitted_paths_before_opening_static_support(tmp_path, monkeypatch):
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import _selected_netcdf

    path = tmp_path / "ocean.nc"
    vector_scene().to_netcdf(path)
    conf = SimulationConfig.from_mapping_with_model_preset(croco_document(tmp_path, [path]))
    _, children, plans = bind_sources(conf, check_output=False)
    child = children["ocean"]

    def no_files(*args, **kwargs):
        raise AssertionError("An unadmitted locator must fail before opening its file")

    monkeypatch.setattr(DatasetResources, "open_netcdf", no_files)
    with DatasetResources() as resources, pytest.raises(ValueError, match="outside the admitted"):
        _selected_netcdf(
            [tmp_path / "different.nc"], child.source_requests["ocean"]["binding"],
            plans["ocean"], resources, engine=child.netcdf_engine, chunks=None)


def test_grib_internal_surface_height_remains_scalar_beside_selected_height_axis(tmp_path):
    from frameit.core.preflight import bind_source, inventory_source
    from frameit.io.grib_utils import concat_grib2ds_by_vert_coord
    from frameit.io.loader import DatasetResources

    from .test_inspect_metadata import v3_config
    from .test_v3_grib_reads import write_messages

    path = write_messages(tmp_path / "input.grib", [
        {"param": 165, "group": "heightAboveGround", "level": 10, "missing": False},
        *({"param": 131, "group": "heightAboveGround", "level": level, "missing": False}
          for level in (20, 40, 70)),
    ])
    before = path.read_bytes()
    conf = v3_config(tmp_path, [path], model="arome", variables={
        "2d": ["u10"], "3d": ["u"], "levels": {"values": [70, 20]}},
        transforms=[{"fields": ["u", "u10"], "units": "m s-1"}])
    source = inventory_source(conf, "weather")
    binding = bind_source(conf, "weather")
    with DatasetResources() as resources:
        _, internal = concat_grib2ds_by_vert_coord(
            [path], {}, {}, selected_records=binding, source_plan=source,
            resources=resources)
        surface, = [ds.u10 for ds in internal["internal"].values() if "u10" in ds]
        upper, = [ds.u for ds in internal["internal"].values() if "u" in ds]
        assert surface.dims == ("time", "y", "x")
        assert surface.heightAboveGround.item() == 10.
        np.testing.assert_array_equal(upper.heightAboveGround, [70., 20.])
        assert upper.dims == ("time", "heightAboveGround", "y", "x")
        np.testing.assert_array_equal(surface.isel(time=0, y=0), [0., 1011., 1012.])
        np.testing.assert_array_equal(upper.isel(time=0, y=0, x=1), [1071., 1021.])
    assert path.read_bytes() == before


@pytest.mark.parametrize("file_count", [1, 2])
@pytest.mark.parametrize("change", ["values", "units"])
def test_croco_reader_rejects_angle_changes_from_own_bound_geometry(tmp_path, file_count, change):
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

    paths = []
    for index in range(file_count):
        path = tmp_path / f"ocean-{index}.nc"
        value = vector_scene()
        (value if file_count == 1 else value.isel(time=[index])).to_netcdf(path)
        paths.append(path)
    raw = croco_document(tmp_path, paths, variables={"3d": ["u"]})
    raw["sources"]["ocean"].update(
        wind_pairs=[{"u": "u", "v": "v", "basis": "grid",
                     "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        transforms=[{"fields": ["u"], "sampling": "mass", "basis": "earth"}])
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    _, children, plans = bind_sources(conf, check_output=False)
    child = children["ocean"]
    for path in paths:
        with xr.open_dataset(path) as original:
            changed = original.load()
        if change == "values":
            changed.angle.values[:] = 0.
        else:
            changed.angle.attrs["units"] = "degrees"
        changed.to_netcdf(path)
    with DatasetResources() as resources, pytest.raises(ValueError, match="CROCO.*revalidat"):
        concat_nc2ds_by_vert_coord(
            paths, {}, {}, resources=resources,
            selected_records=child.source_requests["ocean"]["binding"], source_plan=plans["ocean"])


@pytest.mark.parametrize("file_count", [1, 2])
@pytest.mark.parametrize("formula", [None, "s: s_rho C: Cs_rho"])
def test_croco_invalid_sigma_formula_returns_public_diagnostic(tmp_path, file_count, formula):
    paths = []
    for index in range(file_count):
        value = vector_scene().isel(time=[index]).copy(deep=True)
        if formula is None:
            del value.s_rho.attrs["formula_terms"]
        else:
            value.s_rho.attrs["formula_terms"] = formula
        path = tmp_path / f"ocean-{index}.nc"
        value.to_netcdf(path)
        paths.append(path)
    report = collect_preflight(
        croco_document(tmp_path, paths, variables={"3d": ["temp"]}), check_output=False)
    assert report.errors
    assert any("CROCO" in error.message and "formula" in error.message for error in report.errors)


@pytest.mark.parametrize("suffix,dims", [
    ("u", ("time", "eta_rho", "xi_u")), ("v", ("time", "eta_v", "xi_rho")),
])
def test_croco_required_dynamic_face_mask_fails_validation(tmp_path, suffix, dims):
    value = vector_scene()
    value[f"mask_{suffix}"] = (dims, np.ones(tuple(value.sizes[dim] for dim in dims)))
    path = tmp_path / "ocean.nc"
    value.to_netcdf(path)
    raw = croco_document(tmp_path, [path], variables={"3d": ["u"]})
    raw["sources"]["ocean"].update(
        wind_pairs=[{"u": "u", "v": "v", "basis": "grid",
                     "rotation": {"method": "coordinate", "coordinate": "angle"}}],
        transforms=[{"fields": ["u"], "sampling": "mass", "basis": "earth"}])
    report = collect_preflight(raw, check_output=False)
    assert report.errors
    assert any(f"CROCO mask_{suffix}" in error.message for error in report.errors)


def test_initial_gap_polar_keeps_interval_metadata_field_owned(tmp_path):
    import subprocess
    import sys

    from .test_v3_grib_reads import write_messages

    path = write_messages(tmp_path / "input.grib", [
        *({"hour": hour, "missing": False} for hour in (0, 1, 2)),
        *({"hour": hour, "interval": True, "missing": False} for hour in (1, 2)),
    ])
    before = path.read_bytes()
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3, "sources": {"atmosphere": {
            "model": "arome", "files": str(path),
            "variables": {"3d": ["u", "avg_u"], "levels": {"indices": [0]}},
            "allow_initial_gaps": ["avg_u"],
            "field_metadata": {name: {"kind": "continuous"} for name in ("u", "avg_u")},
        }},
        "region": {"center": {"latitude": -19.5, "longitude": 61.}},
        "products": {"model_grid": True, "polar": {"radius_km": 5., "azimuth_count": 4}},
        "output": {"directory": str(tmp_path / "out")},
        "resources": {"cpus": 1, "scheduler": "synchronous", "synchronous_export": True},
    })
    result = execute_simulation(conf)
    assert {product["role"] for product in result.products} == {"model_grid", "polar"}
    for product in result.products:
        checked = subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    times = np.array(['2026-01-01T00', '2026-01-01T01', '2026-01-01T02'], dtype='datetime64[ns]')
    np.testing.assert_array_equal(out.time, times)
    assert 'bounds' not in out.time.attrs
    np.testing.assert_array_equal(out.avg_u_time, times)
    assert out.avg_u_time.attrs['bounds'] == 'avg_u_time_bounds'
    assert np.isnat(out.avg_u_time_bounds[0]).all()
    np.testing.assert_array_equal(out.avg_u_time_bounds[1:], np.array([
        ['2026-01-01T00', '2026-01-01T01'], ['2026-01-01T01', '2026-01-01T02']],
        dtype='datetime64[ns]'))
    np.testing.assert_array_equal(out.avg_u_GRIB_stepType[1:], ['avg', 'avg'])
    np.testing.assert_array_equal(out.avg_u_GRIB_startStep[1:], [0, 1])
    assert np.isnan(out.avg_u.isel(time=0)).all()
    if sys.argv[2] == 'polar':
        u, mean = (out[name].isel(radius=0, azimuth=0) for name in ('u', 'avg_u'))
        assert np.isfinite(u).all()
        np.testing.assert_array_equal(mean[1:], u[1:])
    else:
        np.testing.assert_array_equal(out.u.isel(pressure=0, y=0, x=1), [851,1851,2851])
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], product["role"]], capture_output=True, text=True)
        assert checked.returncode == 0, checked.stderr
    assert path.read_bytes() == before
