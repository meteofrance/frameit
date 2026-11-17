"""Explicit SURFEX interpretation never changes unrelated Meso-NH quantities."""

import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.coupled import bind_sources
from frameit.core.preflight import bind_source, inventory_source
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources
from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord


def surfex_scene(index=0):
    fraction = np.ones((7, 7))
    fraction[[0, -1], :] = 999.
    fraction[:, [0, -1]] = 999.
    fraction[2, 2], fraction[3, 3] = 0., .25
    sst = np.full((7, 7), 300.+index)
    sst[3, 4], sst[4, 3] = 999., 0.
    salinity = np.full((7, 7), 35.+index)
    salinity[3, 3] = 0.
    return xr.Dataset({
        "SST": (("nj", "ni"), sst, {"comment": "SST (K)"}),
        "SSS": (("nj", "ni"), salinity, {"comment": "Sea Surface Salinity (psu)"}),
        "H_SEA": (("nj", "ni"), np.full((7, 7), 40.+index), {"comment": "X_Y_H_SEA (W/m2)"}),
        "FRAC_SEA": (("nj", "ni"), fraction, {"comment": "(fraction)"}),
        "PRES": (("nj", "ni"), np.full((7, 7), 999.), {"units": "hPa"}),
    }, coords={"time": [np.datetime64("2024-12-10T01", "ns")+np.timedelta64(index, "h")],
               "ni": ("ni", np.arange(7)*1000., {"units": "m", "c_grid_dynamic_range": "2:6"}),
               "nj": ("nj", np.arange(7)*1000., {"units": "m", "c_grid_dynamic_range": "2:6"}),
               "latitude": (("nj", "ni"), -20.+(np.arange(7)-3)[:, None]*.009+np.zeros((7, 7)), {"units": "degrees_north"}),
               "longitude": (("nj", "ni"), 60.+(np.arange(7)-3)[None, :]*.009/np.cos(np.deg2rad(20.))+np.zeros((7, 7)), {"units": "degrees_east"})})


def surfex_conf():
    return SimpleNamespace(atm_model="MNH", netcdf_surfex_fields=["SST", "SSS", "H_SEA"],
                           requested_variables_user={"surface": {"variables": ["SST", "SSS", "H_SEA", "PRES"]}},
                           simulation_parameter={})


def surfex_document(directory, paths):
    return {"schema_version": 3, "run": {"name": "sea-support"},
            "sources": {"atmosphere": {
                "model": "mesonh", "format": "netcdf", "files": list(map(str, paths)),
                "interpretation": "mesonh_surfex_sea",
                "variables": {"2d": ["SST", "SSS", "H_SEA", "PRES", "FRAC_SEA"]}}},
            "region": {"center": {"latitude": -20., "longitude": 60.},
                       "width_km": {"x": 4., "y": 4.}},
            "resources": {"native_threads": 1, "compute_workers": 1,
                          "synchronous_export": True, "export_workers": 1},
            "output": {"directory": str(directory/"out"), "overwrite": False}}


def test_surfex_sea_support_preserves_fraction_and_valid_zero():
    from frameit.io.surfex_utils import prepare_surfex

    original = surfex_scene().chunk({"nj": 3})
    result = prepare_surfex(original, surfex_conf())
    assert hasattr(result.SST.data, "dask")
    assert result.SST[3, 3] == 300.
    assert result.SSS[3, 3] == 0.
    assert result.H_SEA[3, 3] == 40.  # Never scale the tile value by its .25 fraction.
    assert result.SST[4, 3] == 0.
    assert np.isnan(result.SST[3, 4]) and result.SSS[3, 4] == 35.
    assert np.isnan(result.SST[2, 2]) and np.isnan(result.SST[0]).all()
    np.testing.assert_array_equal(result.PRES, np.full((7, 7), 999.))
    np.testing.assert_array_equal(result.FRAC_SEA[1:-1, 1:-1], original.FRAC_SEA[1:-1, 1:-1])
    assert np.isnan(result.FRAC_SEA[0]).all()
    for name, units in (("SST", "K"), ("SSS", "psu"), ("H_SEA", "W/m2"), ("FRAC_SEA", "1")):
        assert result[name].attrs["units"] == units
        assert result[name].attrs["comment"] == original[name].attrs["comment"]
    assert "FRAC_SEA" in result.SST.attrs["ancillary_variables"].split()
    assert "cell_methods" not in result.H_SEA.attrs and "standard_name" not in result.H_SEA.attrs
    assert original.SST[3, 4] == 999. and "units" not in original.SST.attrs


@pytest.mark.parametrize("problem", ["missing_fraction", "invalid_fraction", "missing_support", "missing_comment", "unit_conflict", "physical_range"])
def test_surfex_invalid_required_support_and_metadata_fail(problem):
    from frameit.io.surfex_utils import prepare_surfex

    ds = surfex_scene()
    if problem == "missing_fraction":
        ds = ds.drop_vars("FRAC_SEA")
    elif problem == "invalid_fraction":
        ds.FRAC_SEA.values[3, 3] = 1.1
    elif problem == "missing_support":
        ds.FRAC_SEA.values[3, 3] = 999.
    elif problem == "missing_comment":
        ds.SST.attrs.pop("comment")
    elif problem == "unit_conflict":
        ds.SST.attrs["units"] = "degC"
    else:
        ds.ni.attrs.pop("c_grid_dynamic_range")
    with pytest.raises(ValueError, match="SURFEX|FRAC_SEA|units|physical"):
        prepare_surfex(ds, surfex_conf())


def test_surfex_explicit_unit_spelling_equivalence_and_opt_out():
    from frameit.io.surfex_utils import prepare_surfex

    ds = surfex_scene()
    ds.SST.attrs["units"] = "kelvin"
    ds.H_SEA.attrs["units"] = "W m-2"
    result = prepare_surfex(ds, surfex_conf())
    assert result.SST.attrs["units"] == "kelvin"
    assert result.H_SEA.attrs["units"] == "W m-2"
    conf = surfex_conf()
    conf.netcdf_surfex_fields = []
    xr.testing.assert_identical(prepare_surfex(ds, conf), ds)


def test_surfex_empty_units_attribute_is_completed_from_comment():
    from frameit.io.surfex_utils import prepare_surfex

    ds = surfex_scene()
    ds.SST.attrs["units"] = " "
    result = prepare_surfex(ds, surfex_conf())
    assert result.SST.attrs["units"] == "K"
    assert result.SST.attrs["surfex_units_source"] == "source_comment"


def test_surfex_stress_comment_units_are_not_interpreted_as_velocity():
    from frameit.io.surfex_utils import prepare_surfex

    ds = surfex_scene()
    ds["FMU_SEA"] = (("nj", "ni"), np.full((7, 7), 2.), {"comment": "X_Y_FMU_SEA (kg/ms2)", "units": "Pa"})
    conf = surfex_conf()
    conf.netcdf_surfex_fields = ["FMU_SEA"]
    conf.requested_variables_user = {"surface": {"variables": ["FMU_SEA"]}}
    out = prepare_surfex(ds, conf)
    assert out.FMU_SEA[3, 3] == 2.
    assert out.FMU_SEA.attrs["units"] == "Pa"
    assert "wind_speed" not in out and "standard_name" not in out.FMU_SEA.attrs


def test_surfex_marker_rule_never_reinterprets_croco_water_mask():
    from frameit.io.netcdf_utils import normalize_netcdf_time
    from frameit.testing.numerical.test_croco_netcdf import croco_scene

    ds = croco_scene()
    ds["mask_rho"] = (("eta_rho", "xi_rho"), np.ones((7, 7)), {"option_0": "land", "option_1": "water"})
    ds.mask_rho.values[2, 2] = 0.
    ds.temp.values[0, 0, 3, 3] = 999.
    out = normalize_netcdf_time(ds, SimpleNamespace(atm_model="CROCO", name_time_dim="time"))
    np.testing.assert_array_equal(out.mask_rho, ds.mask_rho)
    assert out.temp[0, 0, 3, 3] == 999.


@pytest.mark.parametrize("problem", ["unknown", "model", "format", "layout", "duplicates", "not_list"])
def test_surfex_schema_keeps_interpretation_explicit_and_bounded(tmp_path, problem):
    raw = surfex_document(tmp_path, [tmp_path/"snapshot.nc"])
    source = raw["sources"]["atmosphere"]
    if problem == "unknown":
        source["interpretation"] = "unknown"
    elif problem == "model":
        source["model"] = "arome"
    elif problem == "format":
        source["format"] = "grib"
    elif problem == "layout":
        source["reader"] = {"file_layout": "variables"}
    elif problem == "duplicates":
        source["variables"]["2d"] = ["SST", "SST"]
    else:
        source["variables"]["2d"] = "SST"
    with pytest.raises(ValueError, match="interpretation|file_layout|variables"):
        SimulationConfig.from_mapping_with_model_preset(raw)


def test_surfex_python_configuration_cannot_silently_select_other_model(tmp_path):
    conf = SimulationConfig.from_mapping_with_model_preset(surfex_document(tmp_path, [tmp_path/"snapshot.nc"]))
    conf.sources["atmosphere"]["model"] = "croco"
    with pytest.raises(ValueError, match="surfex_fields|interpretation"):
        SimulationConfig.from_mapping_with_model_preset(
            {**conf.yaml_config, "sources": conf.sources})


def test_surfex_preflight_reads_support_but_never_thermal_payload(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    path = tmp_path/"snapshot.nc"
    surfex_scene().to_netcdf(path)
    conf = SimulationConfig.from_mapping_with_model_preset(surfex_document(tmp_path, [path]))
    original = H5NetCDFArrayWrapper.__getitem__
    reads = []

    def metadata_only(self, key):
        reads.append(self.variable_name)
        if self.variable_name in {"SST", "SSS", "H_SEA", "PRES"}:
            raise AssertionError(f"Preflight decoded physical payload {self.variable_name}")
        return original(self, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", metadata_only)
    with DatasetResources() as resources:
        _, children, sources = bind_sources(conf, check_output=False, resources=resources)
        assert "FRAC_SEA" not in reads  # Metadata preflight never reads support values.
        child = children["atmosphere"]
        # Selected numerical preparation checks support while thermal arrays stay lazy.
        concat_nc2ds_by_vert_coord(
            [path], {}, {}, wind_conf=child, resources=resources,
            selected_records=child.source_requests["atmosphere"]["binding"],
            source_plan=sources["atmosphere"])
    assert "FRAC_SEA" in reads


@pytest.mark.parametrize("change", ["units", "statistic", "quantity", "support"])
def test_surfex_snapshots_reject_incompatible_scientific_metadata(tmp_path, change):
    paths = []
    for index in (0, 1):
        ds = surfex_scene(index)
        if index:
            if change == "units":
                ds.SST.attrs.update(units="degC", comment="SST (degC)")
            elif change == "statistic":
                ds.H_SEA.attrs["cell_methods"] = "time: mean"
            elif change == "quantity":
                ds.SST.attrs["standard_name"] = "sea_water_potential_temperature"
            else:
                ds.FRAC_SEA.attrs["standard_name"] = "land_area_fraction"
        path = tmp_path/f"snapshot-{index}.nc"
        ds.to_netcdf(path)
        paths.append(path)
    conf = SimulationConfig.from_mapping_with_model_preset(surfex_document(tmp_path, paths))
    with pytest.raises(ValueError, match="SURFEX.*metadata|distinct fields|contradict"):
        bind_sources(conf, check_output=False)
    with DatasetResources() as resources, pytest.raises(
            ValueError, match="SURFEX.*metadata|distinct fields|contradict"):
        inventory_source(conf, "atmosphere", resources=resources)
        bind_source(conf, "atmosphere")


def test_surfex_equivalent_snapshot_unit_spellings_remain_compatible(tmp_path):
    paths = []
    for index in (0, 1):
        ds = surfex_scene(index)
        if index:
            ds.SST.attrs["units"] = "kelvin"
            ds.H_SEA.attrs["units"] = "W m-2"
        path = tmp_path/f"snapshot-{index}.nc"
        ds.to_netcdf(path)
        paths.append(path)
    conf = SimulationConfig.from_mapping_with_model_preset(surfex_document(tmp_path, paths))
    with DatasetResources() as resources:
        _, children, sources = bind_sources(conf, check_output=False, resources=resources)
        child = children["atmosphere"]
        user, _ = concat_nc2ds_by_vert_coord(
            paths, {}, {}, wind_conf=child, resources=resources,
            selected_records=child.source_requests["atmosphere"]["binding"],
            source_plan=sources["atmosphere"])
        native, = user.values()
        np.testing.assert_array_equal(native.SST[:, 3, 3], [300., 301.])
        assert native.SST.attrs["units"] == "K"


@pytest.mark.parametrize("coupled", [False, True])
def test_surfex_snapshots_export_and_replay_preserve_source_values_and_policy(tmp_path, coupled):
    from frameit.core.execution import execute_simulation

    paths = []
    for index in (0, 1):
        path = tmp_path/f"snapshot-{index}.nc"
        surfex_scene(index).to_netcdf(path)
        paths.append(path)
    raw = surfex_document(tmp_path, paths)
    if coupled:
        # V3 uses the same source container with implicit or explicit product fields.
        raw["products"] = {"model_grid": {"fields": {
            "atmosphere": raw["sources"]["atmosphere"]["variables"]["2d"]}}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    standalone = SimulationConfig.from_mapping_with_model_preset(surfex_document(tmp_path, paths))
    with DatasetResources() as resources:
        _, children, sources = bind_sources(standalone, resources=resources)
        child = children["atmosphere"]
        user, _ = concat_nc2ds_by_vert_coord(
            paths, {}, {}, wind_conf=child, resources=resources,
            selected_records=child.source_requests["atmosphere"]["binding"],
            source_plan=sources["atmosphere"])
        native, = user.values()
        assert hasattr(native.SST.data, "dask")
        np.testing.assert_array_equal(native.SST[:, 3, 3], [300., 301.])
    result = execute_simulation(conf)
    assert result.ok, result
    product = next(p["path"] for p in result.products if p["role"] == "model_grid")
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    np.testing.assert_array_equal(out.PRES,np.full(out.PRES.shape,999.))
    for t in (0,1):
        np.testing.assert_array_equal(out.SST[t,2,2],300.+t)
        assert out.SSS[t,2,2]==0. and out.H_SEA[t,2,2]==40.+t
        assert np.isnan(out.SST[t,2,3])
    assert out.SST.attrs['units']=='K' and out.SST.attrs['comment']=='SST (K)'
    assert 'FRAC_SEA' in out.SST.attrs['ancillary_variables'].split()
    assert out.FRAC_SEA[0,2,2]==.25
assert 'frameit' not in sys.modules
""", product], check=True)
    replay = SimulationConfig.from_yaml_with_model_preset(conf.output_dir/"resolved-config.yaml")
    assert replay.sources["atmosphere"]["interpretation"] == "mesonh_surfex_sea"
    assert replay.sources["atmosphere"]["variables"]["2d"] == [
        "SST", "SSS", "H_SEA", "PRES", "FRAC_SEA"]
    provenance = yaml.safe_load((conf.output_dir/"run-provenance.yaml").read_text())
    records = provenance["sources"]["atmosphere"]["interpretation"]["metadata_records"]
    assert {record["field"] for record in records} >= {"SST", "SSS", "H_SEA"}


def test_surfex_optional_polar_preserves_central_valid_zero_and_units(tmp_path):
    pytest.importorskip("xesmf")
    from frameit.core.execution import execute_simulation

    path = tmp_path/"snapshot.nc"
    surfex_scene().to_netcdf(path)
    raw = surfex_document(tmp_path, [path])
    raw["products"] = {"model_grid": True, "polar": {
        "radius_km": 2., "azimuth_count": 8,
        "fields": {"atmosphere": ["SST", "SSS"]}}}
    raw["sources"]["atmosphere"]["field_metadata"] = {
        name: {"kind": "continuous"} for name in ("SST", "SSS")}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    product = next(p["path"] for p in result.products if p["role"] == "polar")
    with xr.open_dataset(product) as out:
        np.testing.assert_allclose(out.SST.isel(radius=0), 300., rtol=0, atol=1e-10)
        np.testing.assert_allclose(out.SSS.isel(radius=0), 0., rtol=0, atol=1e-10)
        assert out.SST.attrs["units"] == "K"
        assert "cell_methods" not in out.SST.attrs
