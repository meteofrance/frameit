"""Explicit SURFEX interpretation never changes unrelated Meso-NH quantities."""

import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
import yaml

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
    return {"schema_version": "2.1", "model": "mesonh", "run": {"name": "sea-support"},
            "input": {"format": "netcdf", "files": list(map(str, paths)),
                      "netcdf": {"surfex_fields": ["SST", "SSS", "H_SEA"]}},
            "variables": {"fields_2d": {"names": ["SST", "SSS", "H_SEA", "PRES", "FRAC_SEA"]}},
            "tracking": {"method": "fixed_box", "fixed_box": {"center": {"latitude": -20., "longitude": 60.}}},
            "domain": {"width_km": {"x": 4., "y": 4.}},
            "execution": {"native_threads": 1, "dask_workers": 1},
            "output": {"directory": str(directory/"out"), "overwrite": False,
                       "synchronous_export": True, "max_workers": 1}}


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
    if problem == "unknown":
        raw["input"]["netcdf"]["surfex_fields"] = ["PRES"]
    elif problem == "model":
        raw["model"] = "arome"
    elif problem == "format":
        raw["input"]["format"] = "grib"
    elif problem == "layout":
        raw["input"]["netcdf"]["file_layout"] = "variables"
    elif problem == "duplicates":
        raw["input"]["netcdf"]["surfex_fields"] = ["SST", "SST"]
    else:
        raw["input"]["netcdf"]["surfex_fields"] = "SST"
    with pytest.raises(ValueError, match="surfex_fields|SURFEX"):
        SimulationConfig.from_mapping_with_model_preset(raw)


def test_surfex_python_configuration_cannot_silently_select_other_model(tmp_path):
    conf = SimulationConfig.from_mapping_with_model_preset(surfex_document(tmp_path, [tmp_path/"snapshot.nc"]))
    conf.atm_model = "CROCO"
    with pytest.raises(ValueError, match="surfex_fields"):
        conf.__post_init__()


def test_surfex_preflight_reads_support_but_never_thermal_payload(tmp_path, monkeypatch):
    from frameit.core.preflight import preflight
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
    preflight(conf, check_output=False)
    assert "FRAC_SEA" in reads


@pytest.mark.parametrize("change", ["units", "statistic", "quantity", "support"])
def test_surfex_snapshots_reject_incompatible_scientific_metadata(tmp_path, change):
    from frameit.core.preflight import preflight

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
    with pytest.raises(ValueError, match="SURFEX.*metadata"):
        preflight(conf, check_output=False)
    with DatasetResources() as resources, pytest.raises(ValueError, match="SURFEX.*metadata"):
        concat_nc2ds_by_vert_coord(paths, conf.requests_user(), conf.requests_tracker(),
                                   method="fixed_box", wind_conf=conf, resources=resources)


def test_surfex_equivalent_snapshot_unit_spellings_remain_compatible(tmp_path):
    from frameit.core.preflight import preflight

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
    preflight(conf, check_output=False)
    with DatasetResources() as resources:
        user, _ = concat_nc2ds_by_vert_coord(paths, conf.requests_user(), conf.requests_tracker(),
                                             method="fixed_box", wind_conf=conf, resources=resources)
        np.testing.assert_array_equal(user["surface"].SST[:, 3, 3], [300., 301.])
        assert user["surface"].SST.attrs["units"] == "K"


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
        source = {"model": "mesonh", "input": raw["input"], "variables": raw.pop("variables")}
        raw["input"] = {"sources": {"mnh": source}}
        raw["tracking"]["source"] = "mnh"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    standalone = SimulationConfig.from_mapping_with_model_preset(surfex_document(tmp_path, paths))
    with DatasetResources() as resources:
        user, _ = concat_nc2ds_by_vert_coord(paths, standalone.requests_user(), standalone.requests_tracker(),
                                             method="fixed_box", wind_conf=standalone, resources=resources)
        assert hasattr(user["surface"].SST.data, "dask")
        np.testing.assert_array_equal(user["surface"].SST[:, 3, 3], [300., 301.])
    result = execute_simulation(conf)
    assert result.ok, result
    product = next(p["path"] for p in result.products if p["role"] == "cart")
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
    assert (replay.input_sources["mnh"]["input"]["netcdf"]["surfex_fields"] if coupled
            else replay.netcdf_surfex_fields) == ["SST", "SSS", "H_SEA"]
    provenance = yaml.safe_load((conf.output_dir/"run-provenance.yaml").read_text())
    records = provenance["sources"]["mnh"]["surfex_provenance"] if coupled else provenance["surfex_provenance"]
    assert {record["field"] for record in records} >= {"SST", "SSS", "H_SEA"}


def test_surfex_optional_polar_preserves_central_valid_zero_and_units(tmp_path):
    pytest.importorskip("xesmf")
    from frameit.core.execution import execute_simulation

    path = tmp_path/"snapshot.nc"
    surfex_scene().to_netcdf(path)
    raw = surfex_document(tmp_path, [path])
    raw["polar"] = {"enabled": True, "azimuth_count": 8,
                    "variables": {"fields_2d": {"names": ["SST", "SSS"]}}}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    product = next(p["path"] for p in result.products if p["role"] == "polar")
    with xr.open_dataset(product) as out:
        np.testing.assert_allclose(out.SST.isel(rr=0), 300., rtol=0, atol=1e-10)
        np.testing.assert_allclose(out.SSS.isel(rr=0), 0., rtol=0, atol=1e-10)
        assert out.SST.attrs["units"] == "K"
        assert "cell_methods" not in out.SST.attrs
