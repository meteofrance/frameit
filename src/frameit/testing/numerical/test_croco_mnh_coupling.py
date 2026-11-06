"""Independent source lookup and shared CROCO/MNH point-target contracts."""

import builtins
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.execution import execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_croco_vectors import vector_scene
from frameit.testing.numerical.test_mnh_surfex_support import surfex_scene


def coupled_document(directory, *, moving=False, polar=False, currents=False):
    ocean = vector_scene()
    for name in ("lat_rho", "lat_u", "lat_v"):
        ocean[name] = ocean[name]+.0065
        ocean[name].attrs["units"] = "degree_north"
    for name in ("lon_rho", "lon_u", "lon_v"):
        ocean[name] = ocean[name]+.007
        ocean[name].attrs["units"] = "degree_east"
    ocean.temp[:] = 20.
    ocean.mask_rho.values[1, 1] = 0.
    path = directory/"croco.nc"
    ocean.to_netcdf(path)
    paths = []
    for index in (0, 1):
        path_mnh = directory/f"mnh-{index}.nc"
        surfex_scene(index).to_netcdf(path_mnh)
        paths.append(str(path_mnh))
    raw = {"schema_version": "2.1", "model": "mesonh", "run": {"name": "paired-native"},
           "input": {"sources": {
               "ocean": {"model": "croco", "input": {"format": "netcdf", "files": [str(path)]},
                         "variables": {"s_rho": {"names": ["temp", "u", "v"], "levels": {"indices": [1, 0]}}}},
               "atmosphere": {"model": "mesonh", "input": {"format": "netcdf", "files": paths,
                               "netcdf": {"surfex_fields": ["SST", "SSS"]}},
                              "variables": {"fields_2d": {"names": ["SST", "SSS", "FRAC_SEA"]}}}}},
           "tracking": {"source": "atmosphere", "method": "fixed_box", "fixed_box": {
               "center": {"latitude": -20., "longitude": 60.}}},
           "domain": {"width_km": {"x": 2., "y": 2.}},
           "execution": {"native_threads": 1, "dask_workers": 1},
           "output": {"directory": str(directory/"out"), "overwrite": False,
                      "synchronous_export": True, "max_workers": 1,
                       "cartesian": {"horizontal_vectors": "native"}}}
    if moving:
        track = directory/"track.nc"
        xr.Dataset({"latitude": ("time", [-20., -19.9905]), "longitude": ("time", [60., 60.0095])},
                   coords={"time": ocean.time}).to_netcdf(track)
        raw["tracking"] = {"source": "atmosphere", "method": "prescribed_track",
                           "prescribed_track": {"file": str(track)}}
    if polar:
        raw["polar"] = {"enabled": True, "shared_target": True, "azimuth_count": 8}
        raw["input"]["sources"]["ocean"]["polar"] = {"enabled": True, "variables": {
            "s_rho": {"names": ["temp", "u", "v"] if currents else ["temp"]}}}
        raw["input"]["sources"]["atmosphere"]["polar"] = {"enabled": True, "variables": {
            "fields_2d": {"names": ["SST", "SSS"]}}}
    return raw


@pytest.mark.parametrize("moving", [False, True])
@pytest.mark.parametrize("synchronous", [False, True])
def test_croco_mnh_shifted_grids_share_continuous_track_not_indices(tmp_path, moving, synchronous, monkeypatch, request):
    # A blocked optional plugin discovery must not poison later GRIB tests.
    request.addfinalizer(xr.backends.plugins.refresh_engines)
    raw = coupled_document(tmp_path, moving=moving)
    raw["output"]["synchronous_export"] = synchronous
    original = builtins.__import__

    def base_only(name, *args, **kwargs):
        if name.split(".")[0] in {"xesmf", "ESMF", "esmpy", "epygram", "cfgrib", "eccodes", "zarr"}:
            raise AssertionError(f"Base path attempted {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", base_only)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    track = next(p["path"] for p in result.products if p["role"] == "track")
    with xr.open_dataset(track) as out:
        assert not np.array_equal(out.ocean_cx, out.atmosphere_cx)
        assert not np.array_equal(out.ocean_cy, out.atmosphere_cy)
        np.testing.assert_array_equal(out.lon, [60., 60.0095] if moving else [60., 60.])
        np.testing.assert_array_equal(out.lat, [-20., -19.9905] if moving else [-20., -20.])
    assert yaml.safe_load((tmp_path/"out"/"resolved-config.yaml").read_text())["input"]["time_alignment"] == "common"


@pytest.mark.parametrize("moving", [False, True])
@pytest.mark.parametrize("currents", [False, True])
def test_croco_mnh_shared_polar_keeps_sigma_support_and_current_identity(tmp_path, moving, currents):
    pytest.importorskip("xesmf")
    raw = coupled_document(tmp_path, moving=moving, polar=True, currents=currents)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    paths = {p["source"]: p["path"] for p in result.products if p["role"] == "polar"}
    with xr.open_dataset(paths["ocean"]) as ocean, xr.open_dataset(paths["atmosphere"]) as mnh:
        for name in ("time", "rr", "theta", "center_lon", "center_lat"):
            np.testing.assert_array_equal(ocean[name], mnh[name])
        np.testing.assert_array_equal(ocean.lon_rho, mnh.longitude)
        np.testing.assert_array_equal(ocean.lat_rho, mnh.latitude)
        assert ocean.attrs["common_polar_target_id"] == mnh.attrs["common_polar_target_id"]
        np.testing.assert_array_equal(ocean.s_rho_source_native_index, [1, 0])
        assert "formula_terms" not in ocean.s_rho.attrs
        assert "standard_name" not in ocean.s_rho.attrs
        assert "source_formula_terms" in ocean.s_rho.attrs
        assert ocean.attrs["vertical_sampling"] == "native_sigma_indices_not_constant_physical_depth"
        np.testing.assert_allclose(ocean.temp.isel(rr=0), 20., atol=1e-10)
        assert not any(name in ocean for name in ("wind_speed", "vrad", "vtan"))
        if currents:
            np.testing.assert_allclose(ocean.u.isel(rr=0), -4., atol=1e-10)
            np.testing.assert_allclose(ocean.v.isel(rr=0), 2., atol=1e-10)
            assert ocean.u.attrs["standard_name"] == "eastward_sea_water_velocity"
        else:
            assert "u" not in ocean and "v" not in ocean
    cart = next(p["path"] for p in result.products if p["role"] == "cart" and p["source"] == "ocean")
    with xr.open_dataset(cart) as native:
        np.testing.assert_allclose(native.u, 2.)
        np.testing.assert_allclose(native.v, 4.)
        assert "x_u_box" in native.u.dims and "y_v_box" in native.v.dims
        assert "formula_terms" in native.s_rho.attrs
        assert native.u.attrs["units"] == "meter second-1"
    provenance = yaml.safe_load((tmp_path/"out"/"run-provenance.yaml").read_text())
    assert provenance["common_polar_target"]
    if currents:
        assert provenance["sources"]["ocean"]["current_provenance"]


@pytest.mark.parametrize("integration", [False, True])
def test_croco_scalar_polar_masks_water_support_without_current_dependencies(tmp_path, integration):
    from frameit.io.croco_utils import prepare_croco_currents

    raw = coupled_document(tmp_path, polar=True)
    source = raw["input"]["sources"]["ocean"]
    source["variables"]["s_rho"]["names"] = ["temp"]
    path = source["input"]["files"][0]
    with xr.open_dataset(path) as header:
        ds = header.drop_vars(["u", "v", "angle"]).load()
    ds.to_netcdf(path, mode="w")
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": "2.1", "model": "croco", "input": source["input"],
        "variables": source["variables"], "polar": source["polar"],
        "domain": {"width_km": {"x": 2., "y": 2.}},
        "tracking": {"method": "fixed_box", "fixed_box": {"center": {"latitude": -20., "longitude": 60.}}},
        "output": {"cartesian": {"horizontal_vectors": "native"}}})
    sampled = prepare_croco_currents(ds, conf)
    assert bool(sampled.temp.isel(eta_rho=1, xi_rho=1).isnull().all())
    assert bool((ds.temp.isel(eta_rho=1, xi_rho=1) == 20.).all())
    if integration:
        pytest.importorskip("xesmf")
        result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
        assert result.ok, result


@pytest.mark.parametrize("standard", ["sea_binary_mask", "land_binary_mask"])
def test_croco_polar_does_not_publish_interpolated_binary_mask_auxiliary(tmp_path, standard):
    pytest.importorskip("xesmf")
    raw = coupled_document(tmp_path, polar=True, currents=True)
    path = raw["input"]["sources"]["ocean"]["input"]["files"][0]
    with xr.open_dataset(path) as header:
        ds = header.load()
    ds.mask_rho.attrs["standard_name"] = standard
    ds.to_netcdf(path, mode="w")
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    path = next(p["path"] for p in result.products if p["role"] == "polar" and p["source"] == "ocean")
    with xr.open_dataset(path) as out:
        assert "mask_rho" not in out
        assert not any(value.attrs.get("standard_name") == "sea_binary_mask" for value in out.variables.values())
    path = next(p["path"] for p in result.products if p["role"] == "cart" and p["source"] == "ocean")
    with xr.open_dataset(path) as out:
        assert set(np.unique(out.mask_rho)) <= {0., 1.}


def test_croco_explicit_binary_mask_polar_request_fails_instead_of_bilinear_sampling():
    from types import SimpleNamespace
    from frameit.io.croco_utils import prepare_croco

    conf = SimpleNamespace(requested_variables_user={"surface": {"variables": ["mask_rho"]}},
                           polar_variables={"surface": {"variables": ["mask_rho"]}},
                           cartesian_horizontal_winds="native", compute_polar_proj=True)
    with pytest.raises(ValueError, match="CROCO.*binary mask"):
        prepare_croco(vector_scene(), conf)


@pytest.mark.parametrize("alignment", ["common", "strict"])
def test_croco_mnh_unequal_times_preserve_exact_alignment_policy(tmp_path, alignment):
    raw = coupled_document(tmp_path)
    raw["input"]["sources"]["atmosphere"]["input"]["files"] = raw["input"]["sources"]["atmosphere"]["input"]["files"][:1]
    raw["input"]["time_alignment"] = alignment
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if alignment == "strict":
        with pytest.raises(ValueError, match="strict|timestamp|time"):
            preflight(conf, check_output=False)
    else:
        report = preflight(conf, check_output=False)
        assert report["track_time_count"] == 1


@pytest.mark.parametrize("problem", ["outside", "budget"])
def test_croco_mnh_invalid_geometry_fails_before_export(tmp_path, problem):
    raw = coupled_document(tmp_path, polar=problem == "budget")
    if problem == "outside":
        raw["tracking"]["fixed_box"]["center"]["latitude"] = -30.
    else:
        raw["polar"]["max_points"] = 1
    if problem == "outside":
        with pytest.raises(ValueError, match="outside"):
            execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
        assert not list((tmp_path/"out").glob("*.cart.*"))
    else:
        with pytest.raises(ValueError):
            preflight(SimulationConfig.from_mapping_with_model_preset(raw), check_output=False)
        assert not (tmp_path/"out").exists()


def test_croco_mnh_existing_two_dimensional_pressure_wind_tracking(tmp_path):
    raw = coupled_document(tmp_path)
    source = raw["input"]["sources"]["atmosphere"]
    source["input"]["wind_pairs"] = [{"group": "fields_2d", "u": "UM10", "v": "VM10",
                                         "reference_frame": "earth"}]
    for path in source["input"]["files"]:
        with xr.open_dataset(path) as header:
            ds = header.load()
        pressure = np.full((7, 7), 100000.)
        pressure[3, 3] = 95000.
        ds["MSLP"] = (("nj", "ni"), pressure, {"units": "Pa"})
        wind = np.full((7, 7), 10.)
        wind[3, 3] = 0.
        ds["UM10"] = (("nj", "ni"), wind, {"units": "m s-1"})
        ds["VM10"] = (("nj", "ni"), np.zeros((7, 7)), {"units": "m s-1"})
        ds.to_netcdf(path, mode="w")
    raw["tracking"] = {"source": "atmosphere", "method": "pressure_wind"}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    path = next(p["path"] for p in result.products if p["role"] == "track")
    with xr.open_dataset(path) as track:
        np.testing.assert_array_equal(track.atmosphere_cx, [3, 3])
        np.testing.assert_array_equal(track.atmosphere_cy, [3, 3])
        assert not np.array_equal(track.ocean_cx, track.atmosphere_cx)


def test_croco_mnh_products_zarr_roundtrip(tmp_path):
    pytest.importorskip("zarr")
    raw = coupled_document(tmp_path)
    raw["output"]["backend"] = "zarr"
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    paths = {p["source"]: p["path"] for p in result.products if p["role"] == "cart"}
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_zarr(sys.argv[1],consolidated=False) as ocean:
    np.testing.assert_allclose(ocean.u,2.)
    np.testing.assert_allclose(ocean.v,4.)
    np.testing.assert_array_equal(ocean.s_rho_source_native_index,[1,0])
    for term in ocean.s_rho.attrs['formula_terms'].split()[1::2]: assert term in ocean
with xr.open_zarr(sys.argv[2],consolidated=False) as mnh:
    assert int((mnh.SSS==0).sum())==2
    assert mnh.SST.attrs['units']=='K'
assert 'frameit' not in sys.modules
""", paths["ocean"], paths["atmosphere"]], check=True)


@pytest.mark.parametrize("engine", ["netcdf4", "zarr"])
def test_croco_mnh_partial_native_write_is_not_published(tmp_path, monkeypatch, engine):
    if engine == "zarr":
        pytest.importorskip("zarr")
    raw = coupled_document(tmp_path)
    raw["output"]["backend"] = engine
    method = "to_zarr" if engine == "zarr" else "to_netcdf"
    original = getattr(xr.Dataset, method)

    def fail_after_writing(dataset, *args, **kwargs):
        result = original(dataset, *args, **kwargs)
        if dataset.attrs.get("source_id") == "ocean":
            raise OSError("simulated disk full after native payload write")
        return result

    monkeypatch.setattr(xr.Dataset, method, fail_after_writing)
    with pytest.raises((OSError, RuntimeError), match="disk full|export"):
        execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    output = tmp_path/"out"
    assert not list(output.glob("*.cart.ocean.*"))
    assert not any(".partial" in path.name for path in output.rglob("*"))
    status = yaml.safe_load((output/"run-status.yaml").read_text())
    assert status["state"] == "failed"


def test_croco_mnh_existing_native_products_are_not_overwritten(tmp_path):
    raw = coupled_document(tmp_path)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf)
    paths = [p["path"] for p in result.products if p["role"] == "cart"]
    before = {path: Path(path).read_bytes() for path in paths}
    with pytest.raises(FileExistsError):
        execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert before == {path: Path(path).read_bytes() for path in paths}


@pytest.mark.parametrize("representation", ["native", "mass_earth"])
def test_croco_mnh_portable_example_runs_both_current_representations(tmp_path, representation):
    example = Path(__file__).resolve().parents[4]/"example/config_file/croco_mesonh.yaml"
    if not example.exists():
        pytest.skip("Repository example is not installed with the package")
    fixture = coupled_document(tmp_path)
    raw = yaml.safe_load(example.read_text())
    for name in ("ocean", "atmosphere"):
        entry = raw["input"]["sources"][name]["input"]
        entry.pop("directory")
        entry.pop("pattern")
        entry["files"] = fixture["input"]["sources"][name]["input"]["files"]
    for path in raw["input"]["sources"]["atmosphere"]["input"]["files"]:
        with xr.open_dataset(path) as header:
            ds = header.load()
        ds["PRES"] = (("time", "level", "nj", "ni"), np.full((1, 3, 7, 7), 999.), {"units": "hPa"})
        ds = ds.assign_coords(level=[0., 1., 2.])
        ds["MSLP"] = (("nj", "ni"), np.full((7, 7), 1000.), {"units": "hPa"})
        for field, units in (("LE_SEA", "W/m2"), ("FMU_SEA", "kg/ms2"), ("FMV_SEA", "kg/ms2")):
            ds[field] = (("nj", "ni"), np.full((7, 7), 2.), {"comment": f"X_Y_{field} ({units})"})
        ds.to_netcdf(path, mode="w")
    path = raw["input"]["sources"]["ocean"]["input"]["files"][0]
    with xr.open_dataset(path) as header:
        ds = header.load()
    ds["w"] = xr.zeros_like(ds.temp).assign_attrs(units="meter second-1", standard_name="upward_sea_water_velocity")
    ds.to_netcdf(path, mode="w")
    raw["input"]["sources"]["ocean"]["variables"]["s_rho"]["levels"] = {"indices": [0, 2]}
    raw["input"]["sources"]["atmosphere"]["variables"]["level"]["levels"] = {"indices": [1, 2]}
    raw["tracking"]["fixed_box"]["center"] = {"latitude": -20., "longitude": 60.}
    raw["domain"]["width_km"] = {"x": 2., "y": 2.}
    raw["output"]["directory"] = str(tmp_path/"example-output")
    raw["output"]["cartesian"]["horizontal_vectors"] = "earth_centered" if representation == "mass_earth" else representation
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    ocean = next(p["path"] for p in result.products if p["role"] == "cart"
                 and p.get("source_group") == "s_rho")
    with xr.open_dataset(ocean) as out:
        values = out.u.values
        np.testing.assert_allclose(values[np.isfinite(values)], 2. if representation == "native" else -4., atol=1e-12)
        assert np.isfinite(values).any()
        if representation == "mass_earth":
            assert np.isnan(values).any()  # The fixture has a dry native bracket.
        np.testing.assert_allclose(out.w, 0.)
        assert "s_rho" in out.w.dims and "s_w" not in out.w.dims
