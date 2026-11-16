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
from frameit.core.configuration import write_template
from frameit.core.coupled import bind_sources
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_croco_vectors import vector_scene
from frameit.testing.numerical.test_mnh_surfex_support import surfex_scene
from frameit.testing.numerical.test_pressure_centroid_mnh import native_vortex


def generated_centroid_document(directory):
    """Keep generated SEA/ocean selections; request the track read by this test."""
    path = write_template("mesonh", directory / "frameit.yaml", coupling="croco",
                          tracking="pressure_centroid")
    raw = yaml.safe_load(path.read_text())
    ocean = vector_scene()
    ocean.to_netcdf(directory / "ocean.nc", engine="h5netcdf")
    atmosphere, _ = native_vortex()
    atmosphere = atmosphere.assign_coords(time=ocean.time.values)
    for axis in ("ni", "nj"):
        atmosphere[axis].attrs["c_grid_dynamic_range"] = f"1:{atmosphere.sizes[axis]}"
    for name, value, comment in (("SST", 300., "SST (K)"),
                                  ("SSS", 35., "Sea Surface Salinity (psu)"),
                                  ("FRAC_SEA", 1., "(fraction)")):
        atmosphere[name] = xr.full_like(atmosphere.MSLP, value).assign_attrs(comment=comment)
        atmosphere[name].attrs.pop("units", None)
    atmosphere.to_netcdf(directory / "atmosphere.nc", engine="h5netcdf")
    for name, source in raw["sources"].items():
        source["files"] = str(directory / f"{name}.nc")
    raw["region"]["width_km"] = {"x": 2., "y": 2.}
    raw["resources"] = {"native_threads": 1, "compute_workers": 1,
                        "synchronous_export": True, "export_workers": 1}
    raw["output"]["directory"] = str(directory / "out")
    raw["products"]["track"] = True
    return raw


def test_generated_mesonh_croco_centroid_runs(tmp_path):
    raw = generated_centroid_document(tmp_path)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    track = next(p["path"] for p in result.products if p["role"] == "track")
    ocean = next(p["path"] for p in result.products if p["role"] == "model_grid" and p["source"] == "ocean")
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr, yaml
with xr.open_dataset(sys.argv[1]) as track:
    np.testing.assert_allclose(track.longitude, 60., atol=.01)
    np.testing.assert_allclose(track.latitude, -20., atol=.01)
    assert track.sizes['time'] == 2
    sources = yaml.safe_load(open(sys.argv[4]))['sources']
    atmosphere = next(grid for grid in sources['atmosphere']['region']['grids'].values()
                      if 'native_x_indices' in grid)
    ocean = next(grid for grid in sources['ocean']['region']['grids'].values()
                 if grid['geometry']['coordinate_names'] == ['lat_rho', 'lon_rho'])
    assert not np.array_equal(atmosphere['native_x_indices'], ocean['native_x_indices'])
with xr.open_dataset(sys.argv[2]) as out, xr.open_dataset(sys.argv[3]) as source:
    for t in (0, 1):
        expected = source.isel(time=t, s_rho=[0],
            eta_rho=out.eta_rho_source_native_index[t].values.astype(int), xi_rho=out.xi_rho_source_native_index[t].values.astype(int))
        for name in ('temp', 'salt'):
            np.testing.assert_array_equal(out[name][t], expected[name])
    np.testing.assert_array_equal(out.s_rho_source_native_index, [0])
    assert out.temp.attrs['units'] == source.temp.attrs['units']
    assert not any(name in out for name in ('u', 'v', 'wind_speed'))
assert 'frameit' not in sys.modules
""", track, ocean, str(tmp_path / "ocean.nc"), str(tmp_path / "out/run-provenance.yaml")], check=True)


@pytest.mark.parametrize("problem,message", [
    ("missing_height", "ALT|LTPZH"), ("wind_basis", "Conflicting"),
    ("one_common_time", "at least two"),
])
def test_generated_mesonh_croco_centroid_rejects_invalid_inputs(tmp_path, problem, message):
    raw = generated_centroid_document(tmp_path)
    name = "ocean" if problem == "one_common_time" else "atmosphere"
    path = tmp_path / f"{name}.nc"
    with xr.open_dataset(path, engine="h5netcdf") as source:
        source = source.load()
    if problem == "missing_height":
        source = source.drop_vars("ALT")
    elif problem == "wind_basis":
        source.UT_ZM.attrs["wind_reference_frame"] = "grid"
        source = source.assign(BETA=0., RPK=0., LON0=54.2)
    else:
        source = source.isel(time=[0])
    source.to_netcdf(path, engine="h5netcdf", mode="w")
    with pytest.raises(ValueError, match=message):
        bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))
    assert not (tmp_path / "out").exists()


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
    raw = {"schema_version": 3, "run": {"name": "paired-native"},
           "sources": {
               "ocean": {"model": "croco", "format": "netcdf", "files": [str(path)],
                         "variables": {"3d": ["temp", "u", "v"], "levels": {"indices": [1, 0]}}},
               "atmosphere": {"model": "mesonh", "format": "netcdf", "files": paths,
                              "interpretation": "mesonh_surfex_sea",
                              "variables": {"2d": ["SST", "SSS", "FRAC_SEA"]}}},
           "region": {"center": {"latitude": -20., "longitude": 60.},
                      "width_km": {"x": 2., "y": 2.},
                      "sources_coupling_time_association": "common"},
           "products": {"model_grid": True, "track": True},
           "resources": {"native_threads": 1, "compute_workers": 1,
                         "synchronous_export": True, "export_workers": 1},
           "output": {"directory": str(directory/"out"), "overwrite": False}}
    if moving:
        track = directory/"track.nc"
        xr.Dataset({"latitude": ("time", [-20., -19.9905]), "longitude": ("time", [60., 60.0095])},
                   coords={"time": ocean.time}).to_netcdf(track)
        raw["region"].pop("center")
        raw["region"]["track"] = {"file": str(track)}
    if polar:
        fields = ["temp", "u", "v"] if currents else ["temp"]
        raw["products"]["polar"] = {"radius_km": 1., "shared_grid": True, "azimuth_count": 8,
            "fields": {"ocean": fields, "atmosphere": ["SST", "SSS"]}}
        raw["sources"]["ocean"]["field_metadata"] = {
            name: {"kind": "continuous"} for name in fields}
        raw["sources"]["atmosphere"]["field_metadata"] = {
            name: {"kind": "continuous"} for name in ("SST", "SSS")}
        if currents:
            raw["sources"]["ocean"]["wind_pairs"] = [
                {"u": "u", "v": "v", "basis": "grid",
                 "rotation": {"method": "coordinate", "coordinate": "angle"}}]
            raw["products"]["polar"]["field_options"] = {"ocean": {
                name: {"sampling": "mass", "basis": "earth"} for name in ("u", "v")}}
    return raw


@pytest.mark.parametrize("moving", [False, True])
@pytest.mark.parametrize("synchronous", [False, True])
def test_croco_mnh_shifted_grids_share_continuous_track_not_indices(tmp_path, moving, synchronous, monkeypatch, request):
    # A blocked optional plugin discovery must not poison later GRIB tests.
    request.addfinalizer(xr.backends.plugins.refresh_engines)
    raw = coupled_document(tmp_path, moving=moving)
    raw["resources"]["synchronous_export"] = synchronous
    original = builtins.__import__

    def base_only(name, *args, **kwargs):
        if name.split(".")[0] in {"xesmf", "ESMF", "esmpy", "epygram", "cfgrib", "eccodes", "zarr"}:
            raise AssertionError(f"Base path attempted {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", base_only)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    track = next(p["path"] for p in result.products if p["role"] == "track")
    sources = yaml.safe_load((tmp_path/"out"/"run-provenance.yaml").read_text())["sources"]
    ocean = next(grid for grid in sources["ocean"]["region"]["grids"].values()
                 if grid["geometry"]["coordinate_names"] == ["lat_rho", "lon_rho"])
    atmosphere = next(iter(sources["atmosphere"]["region"]["grids"].values()))
    with xr.open_dataset(track) as out:
        assert not np.array_equal(ocean["native_x_indices"], atmosphere["native_x_indices"])
        assert not np.array_equal(ocean["native_y_indices"], atmosphere["native_y_indices"])
        np.testing.assert_array_equal(out.longitude, [60., 60.0095] if moving else [60., 60.])
        np.testing.assert_array_equal(out.latitude, [-20., -19.9905] if moving else [-20., -20.])
    assert yaml.safe_load((tmp_path/"out"/"resolved-config.yaml").read_text())["region"]["sources_coupling_time_association"] == "common"


@pytest.mark.parametrize("moving", [False, True])
@pytest.mark.parametrize("currents", [False, True])
def test_croco_mnh_shared_polar_keeps_sigma_support_and_current_identity(tmp_path, moving, currents):
    pytest.importorskip("xesmf")
    raw = coupled_document(tmp_path, moving=moving, polar=True, currents=currents)
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    paths = {p["source"]: p["path"] for p in result.products if p["role"] == "polar"}
    with xr.open_dataset(paths["ocean"]) as ocean, xr.open_dataset(paths["atmosphere"]) as mnh:
        for name in ("time", "radius", "azimuth", "center_longitude", "center_latitude"):
            np.testing.assert_array_equal(ocean[name], mnh[name])
        np.testing.assert_array_equal(ocean.longitude, mnh.longitude)
        np.testing.assert_array_equal(ocean.latitude, mnh.latitude)
        assert ocean.attrs["common_polar_target_id"] == mnh.attrs["common_polar_target_id"]
        np.testing.assert_array_equal(ocean.s_rho_source_native_index, [1, 0])
        assert "formula_terms" not in ocean.s_rho.attrs
        assert "standard_name" not in ocean.s_rho.attrs
        assert "source_formula_terms" in ocean.s_rho.attrs
        assert ocean.attrs["vertical_sampling"] == "native_sigma_indices_not_constant_physical_depth"
        np.testing.assert_allclose(ocean.temp.isel(radius=0), 20., atol=1e-10)
        assert not any(name in ocean for name in ("wind_speed", "vrad", "vtan"))
        if currents:
            np.testing.assert_allclose(ocean.u.isel(radius=0), -4., atol=1e-10)
            np.testing.assert_allclose(ocean.v.isel(radius=0), 2., atol=1e-10)
            assert ocean.u.attrs["standard_name"] == "eastward_sea_water_velocity"
        else:
            assert "u" not in ocean and "v" not in ocean
    cart = next(p["path"] for p in result.products if p["role"] == "model_grid" and p["source"] == "ocean")
    with xr.open_dataset(cart) as native:
        np.testing.assert_allclose(native.u, 2.)
        np.testing.assert_allclose(native.v, 4.)
        assert "x_u" in native.u.dims and "y_v" in native.v.dims
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
    source = raw["sources"]["ocean"]
    source["variables"]["3d"] = ["temp"]
    path = source["files"][0]
    with xr.open_dataset(path) as header:
        ds = header.drop_vars(["u", "v", "angle"]).load()
    ds.to_netcdf(path, mode="w")
    from types import SimpleNamespace

    conf = SimpleNamespace(atm_model="CROCO", compute_polar_proj=True,
        cartesian_horizontal_winds="native", simulation_parameter={},
        requested_variables_user={"s_rho": {"variables": ["temp"], "level_indices": [1, 0]}},
        polar_variables={"s_rho": {"variables": ["temp"]}})
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
    path = raw["sources"]["ocean"]["files"][0]
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
    path = next(p["path"] for p in result.products if p["role"] == "model_grid" and p["source"] == "ocean")
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
    raw["sources"]["atmosphere"]["files"] = raw["sources"]["atmosphere"]["files"][:1]
    raw["region"]["sources_coupling_time_association"] = alignment
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    if alignment == "strict":
        with pytest.raises(ValueError, match="strict|timestamp|time"):
            bind_sources(conf, check_output=False)
    else:
        preflight(conf, check_output=False)
        assert len(conf.simulation_parameter["region_alignment"]["selected_times"]) == 1


@pytest.mark.parametrize("problem", ["outside", "budget"])
def test_croco_mnh_invalid_geometry_fails_before_export(tmp_path, problem):
    raw = coupled_document(tmp_path, polar=problem == "budget")
    if problem == "outside":
        raw["region"]["center"]["latitude"] = -30.
    else:
        raw["products"]["polar"]["processing"] = {"max_target_points": 1}
    if problem == "outside":
        with pytest.raises(ValueError, match="outside"):
            execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
        assert not list((tmp_path/"out"/"products").glob("*.model_grid.*"))
    else:
        with pytest.raises(ValueError):
            preflight(SimulationConfig.from_mapping_with_model_preset(raw), check_output=False)
        assert not (tmp_path/"out").exists()


def test_croco_mnh_existing_two_dimensional_pressure_wind_tracking(tmp_path):
    raw = coupled_document(tmp_path)
    source = raw["sources"]["atmosphere"]
    source["wind_pairs"] = [{"u": "UM10", "v": "VM10", "basis": "earth"}]
    for path in source["files"]:
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
    raw["region"].pop("center")
    raw["region"]["tracker"] = {"method": "pressure_wind"}
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    path = next(p["path"] for p in result.products if p["role"] == "track")
    sources = yaml.safe_load((tmp_path/"out"/"run-provenance.yaml").read_text())["sources"]
    atmosphere = next(iter(sources["atmosphere"]["region"]["grids"].values()))
    ocean = next(grid for grid in sources["ocean"]["region"]["grids"].values()
                 if grid["geometry"]["coordinate_names"] == ["lat_rho", "lon_rho"])
    with xr.open_dataset(path) as track:
        np.testing.assert_array_equal(atmosphere["native_x_indices"], [3, 3])
        np.testing.assert_array_equal(atmosphere["native_y_indices"], [3, 3])
        assert not np.array_equal(ocean["native_x_indices"], atmosphere["native_x_indices"])


def test_croco_mnh_products_zarr_roundtrip(tmp_path):
    pytest.importorskip("zarr")
    raw = coupled_document(tmp_path)
    raw["output"]["format"] = "zarr"
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    paths = {p["source"]: p["path"] for p in result.products if p["role"] == "model_grid"}
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
    raw["output"]["format"] = "zarr" if engine == "zarr" else "netcdf"
    if engine != "zarr":
        raw["output"]["writer"] = {"engine": engine}
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
    assert not list((output/"products").glob("*.ocean.model_grid.*"))
    assert not any(".partial" in path.name for path in output.rglob("*"))
    status = yaml.safe_load((output/"run-status.yaml").read_text())
    assert status["state"] == "failed"


def test_croco_mnh_existing_native_products_are_not_overwritten(tmp_path):
    raw = coupled_document(tmp_path)
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    result = execute_simulation(conf)
    paths = [p["path"] for p in result.products if p["role"] == "model_grid"]
    before = {path: Path(path).read_bytes() for path in paths}
    with pytest.raises(FileExistsError):
        execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert before == {path: Path(path).read_bytes() for path in paths}
