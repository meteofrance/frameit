"""CROCO native N-1 faces and static-mask rho/Earth current analysis."""

from types import SimpleNamespace
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr

from frameit.testing.numerical.test_croco_netcdf import croco_document, croco_scene


def vector_scene():
    ds = croco_scene().assign_coords(xi_u=np.arange(6)+.5, eta_v=np.arange(6)+.5)
    for suffix, dims, shape in (("u", ("eta_rho", "xi_u"), (7, 6)),
                                 ("v", ("eta_v", "xi_rho"), (6, 7))):
        j, i = np.indices(shape)
        ds = ds.assign_coords({
            f"lat_{suffix}": (dims, -20.+(j-3)*.01, {"units": "degree_north"}),
            f"lon_{suffix}": (dims, 60.+(i-3)*.01, {"units": "degree_east"})})
        data = np.broadcast_to(2. if suffix == "u" else 4., (2, 3, *shape)).copy()
        ds[suffix] = (("time", "s_rho", *dims), data,
                      {"units": "meter second-1", "coordinates": f"lat_{suffix} lon_{suffix}"})
        ds[f"{suffix}bar"] = (("time", *dims), data[:, 0], dict(ds[suffix].attrs))
    ds["angle"] = (("eta_rho", "xi_rho"), np.full((7, 7), np.pi/2), {"units": "radians"})
    ds["mask_rho"] = (("eta_rho", "xi_rho"), np.ones((7, 7)),
                      {"option_0": "land", "option_1": "water", "standard_name": "land_binary_mask"})
    ds.attrs["CPP-options"] = "CURVGRID SPHERICAL MASKING SOLVE3D"
    return ds


def vector_conf(*, representation="mass_earth", names=("u", "v")):
    return SimpleNamespace(atm_model="CROCO", cartesian_horizontal_winds=representation,
                           compute_polar_proj=False, requested_variables_user={
                               "s_rho": {"variables": list(names)}}, simulation_parameter={})


@pytest.mark.parametrize("names", [("u", "v"), ("u",), ("v",), ("ubar", "vbar")])
def test_croco_current_rotation_uses_both_brackets_and_nonzero_angle(names):
    from frameit.io.croco_utils import prepare_croco_currents

    ds = vector_scene().chunk({"time": 1, "s_rho": 1})
    out = prepare_croco_currents(ds, vector_conf(names=names))
    u, v = ("ubar", "vbar") if "ubar" in names else ("u", "v")
    np.testing.assert_allclose(out[u].isel(eta_rho=slice(1, -1), xi_rho=slice(1, -1)), -4., atol=1e-12)
    np.testing.assert_allclose(out[v].isel(eta_rho=slice(1, -1), xi_rho=slice(1, -1)), 2., atol=1e-12)
    for name, standard in ((u, "eastward_sea_water_velocity"), (v, "northward_sea_water_velocity")):
        assert out[name].attrs["standard_name"] == ("barotropic_"+standard if "bar" in name else standard)
        assert out[name].attrs["units"] == "m s-1"
        assert not any("wind" in key for key in out[name].attrs)
        assert not any(face in out[name].coords for face in ("lat_u", "lon_u", "lat_v", "lon_v"))
        assert hasattr(out[name].data, "dask")
        assert bool(out[name].isel(eta_rho=0).isnull().all())
        assert bool(out[name].isel(xi_rho=-1).isnull().all())
    assert "wind_speed" not in out and "vrad" not in out
    assert "standard_name" not in out.mask_rho.attrs
    assert out.mask_rho.attrs["source_standard_name"] == "land_binary_mask"
    xr.testing.assert_identical(ds.u, vector_scene().u.chunk({"time": 1, "s_rho": 1}))
    repeated = prepare_croco_currents(out, vector_conf(names=names))
    xr.testing.assert_identical(repeated, out)


@pytest.mark.parametrize("reverse", [False, True])
def test_croco_linear_currents_varying_angle_and_permuted_axes(reverse):
    from frameit.io.croco_utils import prepare_croco_currents

    ds = vector_scene()
    ds.u[:] = 2*ds.xi_u + 1
    ds.v[:] = 3*ds.eta_v - 2
    ds.angle[:] = (ds.xi_rho + ds.eta_rho)*.03
    if reverse:
        ds = ds.isel(xi_rho=slice(None, None, -1), xi_u=slice(None, None, -1),
                     eta_rho=slice(None, None, -1), eta_v=slice(None, None, -1))
    ds["u"] = ds.u.transpose("xi_u", "s_rho", "time", "eta_rho")
    out = prepare_croco_currents(ds, vector_conf())
    for j, i in ((2, 3), (4, 2)):
        # Independent scalar reference at native rho coordinates.
        angle = .03*(j+i)
        expected = complex(2*i+1, 3*j-2)*complex(np.cos(angle), np.sin(angle))
        np.testing.assert_allclose(out.u.sel(eta_rho=j, xi_rho=i), expected.real, atol=1e-12, rtol=1e-12)
        np.testing.assert_allclose(out.v.sel(eta_rho=j, xi_rho=i), expected.imag, atol=1e-12, rtol=1e-12)


@pytest.mark.parametrize("problem", ["missing", "dry", "explicit_dry", "zero"])
def test_croco_current_joint_support_never_fills_missing_or_erases_zero(problem):
    from frameit.io.croco_utils import prepare_croco_currents

    ds = vector_scene()
    if problem == "missing":
        ds.u.values[0, 0, 3, 2] = np.nan
    elif problem == "dry":
        ds.mask_rho.values[3, 2] = 0
    elif problem == "explicit_dry":
        ds["mask_u"] = (("eta_rho", "xi_u"), np.ones((7, 6)))
        ds.mask_u.values[3, 2] = 0
    else:
        ds.u[:] = 0
        ds.v[:] = 0
    out = prepare_croco_currents(ds, vector_conf())
    for name in ("u", "v"):
        value = out[name].isel(time=0, s_rho=0, eta_rho=3, xi_rho=3).item()
        assert value == 0 if problem == "zero" else np.isnan(value)


@pytest.mark.parametrize("problem", ["angle_units", "angle_missing", "mask_polarity", "mask_range",
                                    "wet_dry", "missing_companion", "units", "quantity", "face_shift"])
def test_croco_analysis_rejects_unresolved_inputs(problem):
    from frameit.io.croco_utils import prepare_croco

    ds = vector_scene()
    if problem == "angle_units": ds.angle.attrs["units"] = "unknown"
    elif problem == "angle_missing": ds = ds.drop_vars("angle")
    elif problem == "mask_polarity": ds.mask_rho.attrs.pop("option_1")
    elif problem == "mask_range": ds.mask_rho.values[2, 2] = 999
    elif problem == "wet_dry": ds.attrs["CPP-options"] += " WET_DRY"
    elif problem == "missing_companion": ds = ds.drop_vars("v")
    elif problem == "units": ds.u.attrs["units"] = "Pa"
    elif problem == "quantity": ds.u.attrs["standard_name"] = "eastward_sea_water_velocity"
    else: ds = ds.assign_coords(xi_u=ds.xi_u+.1)
    with pytest.raises(ValueError, match="CROCO"):
        prepare_croco(ds, vector_conf())


@pytest.mark.parametrize("representation", ["native", "mass_earth"])
def test_croco_native_nminus1_faces_keep_locations(tmp_path, representation):
    from frameit.core.execution import execute_simulation
    from frameit.core.settings_class import SimulationConfig

    source = tmp_path/"ocean.nc"
    vector_scene().to_netcdf(source)
    raw = croco_document(tmp_path, [source], variables={"s_rho": {
        "names": ["u", "v"], "levels": {"indices": [1, 0]}}})
    raw["output"]["cartesian"]["horizontal_vectors"] = "earth_centered" if representation == "mass_earth" else representation
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    path = next(p["path"] for p in result.products if p["role"] == "cart")
    with xr.open_dataset(path) as out:
        np.testing.assert_array_equal(out.s_rho_source_native_index, [1, 0])
        assert all(name in out for name in ("h", "hc", "Cs_rho", "zeta"))
        if representation == "native":
            assert "x_u_box" in out.u.dims and "y_v_box" in out.v.dims
            np.testing.assert_allclose(out.xi_u.isel(time=0), [1.5, 2.5, 3.5, 4.5])
            np.testing.assert_allclose(out.u, 2.)
            np.testing.assert_allclose(out.v, 4.)
            assert "lat_u" in out and "lon_v" in out
            assert out.u.attrs["units"] == "meter second-1"
        else:
            assert "x_box" in out.u.dims and "y_box" in out.v.dims
            np.testing.assert_allclose(out.u, -4., atol=1e-12)
            np.testing.assert_allclose(out.v, 2., atol=1e-12)
            assert out.u.attrs["standard_name"] == "eastward_sea_water_velocity"
            assert not set(out.dims).intersection({"xi_u", "eta_v", "x_u_box", "y_v_box"})
        provenance = __import__("yaml").safe_load((tmp_path/"out"/"run-provenance.yaml").read_text())
        if representation == "mass_earth":
            assert provenance["current_provenance"]
        assert "wind_speed" not in out
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1]) as out:
    native=sys.argv[2]=='native'
    np.testing.assert_allclose(out.u,2. if native else -4.,atol=1e-12)
    np.testing.assert_allclose(out.v,4. if native else 2.,atol=1e-12)
    np.testing.assert_array_equal(out.s_rho_source_native_index,[1,0])
    for name in out.s_rho.attrs['formula_terms'].split()[1::2]: assert name in out
    assert 'wind_speed' not in out and 'vrad' not in out and 'vtan' not in out
assert 'frameit' not in sys.modules
""", str(path), representation], check=True)


def test_croco_direct_analysis_rejects_missing_companions():
    from frameit.io.croco_utils import prepare_croco_currents

    with pytest.raises(ValueError, match="CROCO.*companion"):
        prepare_croco_currents(vector_scene().drop_vars(["u", "v"]), vector_conf())


def test_croco_analysis_rejects_different_component_statistics():
    from frameit.io.croco_utils import prepare_croco

    ds = vector_scene()
    ds.v.attrs["cell_methods"] = "time: mean"
    with pytest.raises(ValueError, match="CROCO.*statistic"):
        prepare_croco(ds, vector_conf())


def test_croco_native_faces_do_not_require_analysis_inputs():
    from frameit.io.croco_utils import prepare_croco

    ds = vector_scene().drop_vars(["angle", "mask_rho", "v"])
    out = prepare_croco(ds, vector_conf(representation="native", names=("u",)))
    assert out.u.variable.identical(ds.u.variable)


def test_croco_preflight_current_payload_stays_unread(tmp_path, monkeypatch):
    from frameit.core.preflight import preflight
    from frameit.core.settings_class import SimulationConfig
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    path = tmp_path/"ocean.nc"
    vector_scene().to_netcdf(path)
    raw = croco_document(tmp_path, [path], variables={"s_rho": {"names": ["u"]}})
    raw["output"]["cartesian"]["horizontal_vectors"] = "earth_centered"
    original = H5NetCDFArrayWrapper.__getitem__

    def metadata_only(self, key):
        if self.variable_name in {"u", "v", "temp", "salt", "zeta"}:
            raise AssertionError(f"Physical payload read: {self.variable_name}")
        return original(self, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", metadata_only)
    preflight(SimulationConfig.from_mapping_with_model_preset(raw), check_output=False)


@pytest.mark.parametrize("field", ["angle", "mask_rho", "v"])
def test_croco_analysis_sequence_rejects_changed_support_or_companion_metadata(tmp_path, field):
    from frameit.core.preflight import preflight
    from frameit.core.settings_class import SimulationConfig
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

    paths = []
    for index in (0, 1):
        ds = vector_scene().isel(time=[index])
        if index:
            if field == "angle": ds.angle.values[2, 2] += .1
            elif field == "mask_rho": ds.mask_rho.values[2, 2] = 0
            else: ds.v.attrs["cell_methods"] = "time: mean"
        path = tmp_path/f"ocean-{index}.nc"
        ds.to_netcdf(path)
        paths.append(path)
    raw = croco_document(tmp_path, paths, variables={"s_rho": {"names": ["u"]}})
    raw["output"]["cartesian"]["horizontal_vectors"] = "earth_centered"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="CROCO"):
        preflight(conf, check_output=False)
    with DatasetResources() as resources, pytest.raises(ValueError, match="CROCO"):
        concat_nc2ds_by_vert_coord(paths, conf.requests_user(), conf.requests_tracker(),
                                   method="fixed_box", wind_conf=conf, resources=resources)
