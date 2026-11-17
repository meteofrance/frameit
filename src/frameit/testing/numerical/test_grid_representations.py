"""Export-level analytical contracts for independent MNH grid choices.

The small rotated grid has grid-x northward and grid-y westward. Truth is
evaluated from labelled sampling locations, not FrameIt's collocation helpers.
These synthetic checks verify representation, not general model validity.
"""

import numpy as np
import pytest
import xarray as xr

from frameit.core.coupled import bind_sources
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.runner import FrameitRunner
from frameit.core.settings_class import SimulationConfig
from frameit.testing.datasets import ci_dataset_root


def test_real_mnh_native_faces_match_source_file(tmp_path):
    path = ci_dataset_root() / "MNH/CHIDO/3CH09.1.MXX30.011diag.nc"
    with xr.open_dataset(path, engine="netcdf4") as source:
        latitude = float(source.latitude[35, 37])
        longitude = float(source.longitude[35, 37])
        expected_u = source.UT.isel(time=0, level=[1, 3, 5],
                                    nj_u=slice(34, 37), ni_u=slice(36, 40)).values
        expected_v = source.VT.isel(time=0, level=[1, 3, 5],
                                    nj_v=slice(34, 38), ni_v=slice(36, 39)).values
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "mesonh", "files": [str(path)],
            "wind_pairs": [{"u": "UT", "v": "VT", "basis": "grid",
                            "rotation": {"method": "geolocation"}}],
            "variables": {"3d": ["UT", "VT"], "levels": {"indices": [1, 3, 5]}},
        }},
        "region": {"center": {"latitude": latitude, "longitude": longitude},
                   "width_km": {"x": 6, "y": 6}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "real-native")},
    })
    result = execute_simulation(
        conf, ExecutionOptions.from_config(conf, synchronous_export=True))
    product = next(p for p in result.products
                   if p["role"] == "model_grid" and p["source"] == "atmosphere")
    with xr.open_dataset(product["path"], engine="netcdf4") as saved:
        np.testing.assert_array_equal(saved.UT[0], expected_u)
        np.testing.assert_array_equal(saved.VT[0], expected_v)
        assert saved.UT.attrs["wind_reference_frame"] == "grid"
        assert "latitude_u" in saved.coords and "latitude_v" in saved.coords


def native_scene(hour=0, units="m/s"):
    mass = np.arange(-4, 5, dtype=float) * 1000
    faces = np.arange(-4.5, 5, dtype=float) * 1000
    ds = xr.Dataset(coords={
        "time": [np.datetime64("2024-01-01T00", "ns") + np.timedelta64(hour, "h")],
        "level": ("level", [-5., 5., 15., 25.],
                  {"units": "m", "c_grid_dynamic_range": "2:3"}),
        "level_w": ("level_w", [-10., 0., 10., 20.],
                    {"units": "m", "c_grid_dynamic_range": "2:4"}),
    })
    for name, values in (("ni", mass), ("nj", mass), ("ni_u", faces),
                         ("nj_u", mass), ("ni_v", mass), ("nj_v", faces)):
        ds = ds.assign_coords({name: (name, values, {"units": "m"})})
    # Approximately 1-km cells on a sufficiently small regional geographic grid.
    # Latitude independently encodes native x, including the U-face locations.
    for suffix, yd, xd in (("", "nj", "ni"), ("_u", "nj_u", "ni_u"),
                           ("_v", "nj_v", "ni_v")):
        x, y = np.meshgrid(ds[xd].values, ds[yd].values)
        ds = ds.assign_coords({
            "latitude" + suffix: ((yd, xd), -20 + x / 111000,
                                  {"units": "degrees_north"}),
            "longitude" + suffix: ((yd, xd), 60 - y / (111000 * np.cos(np.deg2rad(20))),
                                   {"units": "degrees_east"}),
        })
    ds = ds.assign_coords(angle=xr.DataArray(np.pi / 2, attrs={"units": "rad"}))
    # Real MNH formula dependencies must not reintroduce the other full vertical
    # axis after selection (especially when the only request is interface W).
    ds["ZTOP"] = xr.DataArray(20., attrs={"units": "m"})
    ds["ZS"] = xr.DataArray(np.zeros((9, 9)), dims=("nj", "ni"), attrs={"units": "m"})
    for coordinate in ("level", "level_w"):
        ds[coordinate].attrs["formula_terms"] = f"s: {coordinate} height: ZTOP orog: ZS"
    scale = 3.6 if units == "km/h" else 1.
    ds["UT"] = (("time", "level", "nj_u", "ni_u"),
                np.broadcast_to((10 + faces / 1000) * scale, (1, 4, 9, 10)).copy(),
                {"units": units, "standard_name": "x_wind", "grid": 2})
    ds["VT"] = (("time", "level", "nj_v", "ni_v"), np.zeros((1, 4, 10, 9)),
                {"units": units, "standard_name": "y_wind", "grid": 3})
    for name, values, attrs in (
        ("WT", (70 + 3 * ds.level_w.values) * scale,
         {"units": units, "standard_name": "upward_air_velocity", "grid": 4}),
        ("Q", 1000 + 2 * ds.level_w.values, {"units": "1", "grid": 4}),
    ):
        ds[name] = (("time", "level_w", "nj", "ni"),
                    np.broadcast_to(values[None, :, None, None], (1, 4, 9, 9)).copy(), attrs)
    ds["THT"] = (("time", "level", "nj", "ni"), np.full((1, 4, 9, 9), 300.),
                 {"units": "K", "standard_name": "air_potential_temperature", "grid": 1})
    for name, value, attrs in (
        ("UM10", 3 * scale, {"units": units, "standard_name": "eastward_wind"}),
        ("VM10", 4 * scale, {"units": units, "standard_name": "northward_wind"}),
        ("MSLP", 100000., {"units": "Pa"}),
    ):
        ds[name] = (("time", "nj", "ni"), np.full((1, 9, 9), value), attrs)
    return ds


def test_sparse_w_only_keeps_selected_mass_targets(tmp_path):
    path = tmp_path / "native.nc"
    native_scene().to_netcdf(path, engine="netcdf4")
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "mesonh", "files": [str(path)],
            "variables": {"3d": ["WT"], "levels": {"indices": [1, 2]}},
            "transforms": [{"fields": ["WT"], "sampling": "mass", "units": "m s-1"}],
        }},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "output"), "writer": {"engine": "netcdf4"}},
    })
    result = execute_simulation(
        conf, ExecutionOptions.from_config(conf, synchronous_export=True))
    with xr.open_dataset(result.products[0]["path"], engine="netcdf4") as mass:
        np.testing.assert_array_equal(mass.level, [5., 15.])
        np.testing.assert_allclose(mass.WT[:, :, 0, 0], [[85., 115.]])


@pytest.fixture
def native_files(tmp_path):
    native_scene().to_netcdf(tmp_path / "native0.nc", engine="netcdf4")
    return tmp_path


def run_export(directory, horizontal="native", vertical="interfaces", *,
               polar=False, polar_vertical="mass", label="run"):
    transforms = [
        {"fields": ["UT", "VT"], "units": "m s-1",
         **({"sampling": "mass", "basis": "earth"} if horizontal == "mass_earth" else {})},
        {"fields": ["WT"], "units": "m s-1",
         **({"sampling": "mass"} if vertical == "mass" else {})},
        {"fields": ["UM10", "VM10"], "basis": "earth", "units": "m s-1"},
    ]
    products = {"model_grid": True, "track": True}
    if polar:
        products["polar"] = {
            # The original 2-km full box implied a 1-km polar radius.
            "radius_km": 1, "radial_step_km": 1, "azimuth_count": 8,
            "field_options": {"atmosphere": {
                "UT": {"sampling": "mass", "basis": "earth", "units": "m s-1"},
                "VT": {"sampling": "mass", "basis": "earth", "units": "m s-1"},
                "WT": {"sampling": "mass" if polar_vertical == "mass" else "native",
                       "units": "m s-1"},
                "UM10": {"basis": "earth", "units": "m s-1"},
                "VM10": {"basis": "earth", "units": "m s-1"},
            }},
        }
    config = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3, "run": {"name": label},
        "sources": {"atmosphere": {
            "model": "mesonh", "files": str(directory / "native*.nc"), "wind_pairs": [
                {"u": "UT", "v": "VT", "basis": "grid",
                 "rotation": {"method": "coordinate", "coordinate": "angle"}},
                {"u": "UM10", "v": "VM10", "basis": "earth"},
            ],
            "variables": {"3d": ["UT", "VT", "THT", "WT", "Q"],
                          "2d": ["UM10", "VM10", "MSLP"], "levels": {"domain": "physical"}},
            "transforms": transforms,
            **({"field_metadata": {name: {"kind": "continuous"} for name in (
                "UT", "VT", "THT", "WT", "Q", "UM10", "VM10", "MSLP")}} if polar else {}),
        }},
        "region": {"center": {"latitude": -20., "longitude": 60.},
                   "width_km": {"x": 2, "y": 2}},
        "products": products,
        "output": {"directory": str(directory / label), "writer": {"engine": "netcdf4"}},
    })
    result = execute_simulation(
        config, ExecutionOptions.from_config(config, synchronous_export=True))
    assert result.ok
    assert result.n_files == len(list(directory.glob("native*.nc")))
    snapshots = {}
    for product in result.products:
        key = product["role"], product["source"]
        assert key not in snapshots, f"Duplicate exported descriptor: {key}"
        # Ordinary CF decoding, after execute_simulation has closed its resources.
        with xr.open_dataset(product["path"], engine="netcdf4") as reopened:
            snapshots[key] = reopened.load()
        assert not any(name.startswith("_frameit") for name in snapshots[key].variables)
    assert ("track", None) in snapshots
    fields = {"UT", "VT", "THT", "WT", "Q", "UM10", "VM10", "MSLP"}
    assert ("model_grid", "atmosphere") in snapshots
    assert fields <= set(snapshots["model_grid", "atmosphere"].data_vars)
    if polar:
        assert ("polar", "atmosphere") in snapshots
        assert fields <= set(snapshots["polar", "atmosphere"].data_vars)
    return snapshots


def assert_vertical(products, role, location):
    dataset = products[role, "atmosphere"]
    np.testing.assert_array_equal(dataset.level, [5., 15.])
    np.testing.assert_array_equal(dataset.level_w, [0., 10., 20.])
    # Q is not W: selecting mass W must never move/drop unrelated interface data.
    assert "level_w" in dataset.Q.dims
    expected_q = xr.broadcast(1000 + 2 * dataset.level_w, dataset.Q)[0]
    np.testing.assert_allclose(dataset.Q, expected_q.transpose(*dataset.Q.dims))
    if location == "mass":
        assert "WT" not in {name for name, value in dataset.data_vars.items()
                            if "level_w" in value.dims}
        assert "level" in dataset.WT.dims and "level_w" not in dataset.WT.dims
        # Interpolation at z=5 and z=15 gives 85 and 115, respectively.
        w = dataset.WT
        expected = 70 + 3 * dataset.level
    else:
        assert "WT" not in {name for name, value in dataset.data_vars.items()
                            if "level" in value.dims}
        assert "level_w" in dataset.WT.dims and "level" not in dataset.WT.dims
        w = dataset.WT
        expected = 70 + 3 * dataset.level_w
    truth = xr.broadcast(expected, w)[0].transpose(*w.dims)
    np.testing.assert_allclose(w, truth, atol=1e-10)
    assert w.attrs["standard_name"] == "upward_air_velocity"
    assert w.attrs["units"] == "m s-1"


@pytest.mark.parametrize("horizontal", ["native", "mass_earth"])
@pytest.mark.parametrize("vertical", ["interfaces", "mass"])
def test_cartesian_grid_choices_reopen_with_physical_samples(native_files, horizontal, vertical):
    products = run_export(native_files, horizontal, vertical)
    ds = products["model_grid", "atmosphere"]
    assert_vertical(products, "model_grid", vertical)
    np.testing.assert_allclose(ds.THT, 300)
    if horizontal == "native":
        assert ds.UT.dims == ("time", "level", "y", "x_u")
        assert ds.VT.dims == ("time", "level", "y_v", "x")
        assert ds.sizes["x_u"] == ds.sizes["x"] + 1
        assert ds.sizes["y_v"] == ds.sizes["y"] + 1
        assert {"latitude_u", "longitude_u"} <= set(ds.UT.coords)
        assert {"latitude_v", "longitude_v"} <= set(ds.VT.coords)
        # The exported geography locates the actual unrotated native samples.
        truth = 10 + (ds.latitude_u + 20) * 111000 / 1000
        truth = xr.broadcast(truth, ds.UT)[0].transpose(*ds.UT.dims)
        np.testing.assert_allclose(ds.UT, truth, atol=1e-9)
        np.testing.assert_allclose(ds.VT, 0)
        for name, standard, position in (("UT", "x_wind", "x_face"),
                                          ("VT", "y_wind", "y_face")):
            assert ds[name].attrs["standard_name"] == standard
            assert ds[name].attrs["grid_position"] == position
    else:
        assert ds.UT.dims == ds.VT.dims == ("time", "level", "y", "x")
        np.testing.assert_allclose(ds.UT, 0, atol=1e-12)
        latitude = next(ds[name] for name in ds.VT.encoding["coordinates"].split()
                        if name.startswith("latitude"))
        truth = 10 + (latitude + 20) * 111000 / 1000
        truth = xr.broadcast(truth, ds.VT)[0].transpose(*ds.VT.dims)
        np.testing.assert_allclose(ds.VT, truth, atol=1e-9)
        for name, standard in (("UT", "eastward_wind"), ("VT", "northward_wind")):
            assert ds[name].attrs["standard_name"] == standard
            assert ds[name].attrs["wind_reference_frame"] == "earth"
            assert ds[name].attrs["grid"] == 1
    surface = products["model_grid", "atmosphere"]
    np.testing.assert_allclose(surface.UM10, 3)
    np.testing.assert_allclose(surface.VM10, 4)
    np.testing.assert_allclose(surface.MSLP, 100000)
    metadata = {
        name: (field.attrs.get("units"), field.attrs.get("wind_reference_frame"))
        for name, field in (("UT", ds.UT), ("VT", ds.VT),
                            ("UM10", surface.UM10), ("VM10", surface.VM10))
    }
    frame = "grid" if horizontal == "native" else "earth"
    assert metadata == {"UT": ("m s-1", frame), "VT": ("m s-1", frame),
                        "UM10": ("m s-1", "earth"), "VM10": ("m s-1", "earth")}, metadata


@pytest.mark.parametrize("polar_vertical", ["interfaces", "mass"])
def test_cartesian_choice_does_not_change_real_polar_or_tracking(native_files, polar_vertical):
    pytest.importorskip("xesmf")
    native = run_export(native_files, "native", "interfaces", polar=True,
                        polar_vertical=polar_vertical, label="native")
    earth = run_export(native_files, "mass_earth", "mass", polar=True,
                       polar_vertical=polar_vertical, label="earth")
    xr.testing.assert_allclose(native["track", None], earth["track", None])
    xr.testing.assert_allclose(native["polar", "atmosphere"], earth["polar", "atmosphere"])
    for products in (native, earth):
        assert_vertical(products, "polar", polar_vertical)
        ds = products["polar", "atmosphere"]
        np.testing.assert_allclose(ds.UT, 0, atol=1e-12)
        # At the repeated polar origin the mass-grid wind is exactly (0, 10).
        np.testing.assert_allclose(ds.VT.isel(radius=0), 10, atol=1e-9)
        latitude = next(ds[name] for name in ds.VT.encoding["coordinates"].split()
                        if name.startswith("latitude"))
        truth = 10 + (latitude + 20) * 111000 / 1000
        truth = xr.broadcast(truth, ds.VT)[0].transpose(*ds.VT.dims)
        # ESMF bilinear weights use spherical cells, not an affine latitude
        # plane. Allow the cell-curvature scale: (1000 m / Earth radius) times
        # the 1 m/s cell-to-cell increment, rounded up to 2e-4 m/s.
        np.testing.assert_allclose(ds.VT, truth, rtol=0, atol=2e-4)
        assert np.isfinite(ds.VT).all()
        assert ds.UT.attrs["standard_name"] == "eastward_wind"
        assert ds.VT.attrs["standard_name"] == "northward_wind"
        assert ds.VT.attrs["wind_reference_frame"] == "earth"
        np.testing.assert_allclose(products["polar", "atmosphere"].UM10, 3, atol=1e-10)
        np.testing.assert_allclose(products["polar", "atmosphere"].VM10, 4, atol=1e-10)


@pytest.mark.parametrize("horizontal", ["native", "mass_earth"])
def test_inconsistent_velocity_units_fail_before_concatenation(native_files, horizontal):
    native_scene(hour=1, units="km/h").to_netcdf(
        native_files / "native1.nc", engine="netcdf4")
    originals = {path: path.read_bytes() for path in native_files.glob("native*.nc")}
    with pytest.raises(ValueError, match="distinct fields share requested name") as caught:
        run_export(native_files, horizontal, "mass")
    assert all(name in str(caught.value) for name in ("native0.nc", "native1.nc", "km/h", "m/s"))
    assert not (native_files / "run").exists()
    assert all(path.read_bytes() == before for path, before in originals.items())


def test_consistent_velocity_units_convert_without_changing_physical_samples(native_files):
    for hour in (0, 1):
        native_scene(hour=hour, units="km/h").to_netcdf(
            native_files / f"native{hour}.nc", engine="netcdf4")
    products = run_export(native_files, "mass_earth", "mass")
    assert_vertical(products, "model_grid", "mass")
    for names in (("UT", "VT", "WT"), ("UM10", "VM10")):
        ds = products["model_grid", "atmosphere"]
        assert ds.sizes["time"] == 2
        for name in names:
            assert ds[name].attrs["units"] == "m s-1"
            xr.testing.assert_allclose(ds[name].isel(time=0, drop=True),
                                       ds[name].isel(time=1, drop=True))
    ds = products["model_grid", "atmosphere"]
    np.testing.assert_allclose(ds.UT, 0, atol=1e-12)
    np.testing.assert_allclose(ds.VT.isel(x=1), 10, atol=1e-10)
    np.testing.assert_allclose(products["model_grid", "atmosphere"].UM10, 3)
    np.testing.assert_allclose(products["model_grid", "atmosphere"].VM10, 4)


def test_inconsistent_native_face_geography_units_fail_before_concat(native_files):
    second = native_scene(hour=1)
    face_geography = ("latitude_u", "longitude_u", "latitude_v", "longitude_v")
    for name in face_geography:
        second = second.assign_coords({
            name: np.deg2rad(second[name]).assign_attrs(units="rad"),
        })
    second.to_netcdf(native_files / "native1.nc", engine="netcdf4")
    originals = {path: path.read_bytes() for path in native_files.glob("native*.nc")}
    with pytest.raises(ValueError, match="distinct fields share requested name") as caught:
        run_export(native_files, "native", "interfaces")
    assert all(name in str(caught.value) for name in (
        *face_geography, "native0.nc", "native1.nc", "degrees_north", "rad"))
    assert not (native_files / "run").exists()
    assert all(path.read_bytes() == before for path, before in originals.items())


def loader_config(path, variables, pairs):
    return SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "mesonh", "files": [str(path)], "wind_pairs": pairs,
            "variables": variables,
        }},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"model_grid": True},
        "output": {"directory": str(path.parent / "output"), "writer": {"engine": "netcdf4"}},
    })


def test_secondary_declared_pair_normalizes_without_primary_alias_fields(tmp_path):
    path = tmp_path / "secondary.nc"
    source = native_scene(units="km/h").rename({"UT": "U2", "VT": "V2"})
    source.to_netcdf(path, engine="netcdf4")
    pairs = [
        {"u": u, "v": v, "basis": "grid",
         "rotation": {"method": "coordinate", "coordinate": "angle"}}
        for u, v in (("UT", "VT"), ("U2", "V2"))
    ]
    conf = loader_config(path, {"3d": ["U2", "V2"], "levels": {"domain": "physical"}},
                         pairs)
    conf.velocity_aliases.update(u_velocity="UT", v_velocity="VT")
    raw, snapshots = conf.yaml_config, {}
    for representation in ("native", "mass_earth"):
        raw["sources"]["atmosphere"]["transforms"] = [
            {"fields": ["U2", "V2"], "units": "m s-1",
             **({"sampling": "mass", "basis": "earth"}
                if representation == "mass_earth" else {})}]
        _, children, _ = bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))
        with FrameitRunner(children["atmosphere"]) as runner:
            groups, _, _ = runner.load_dataset()
            snapshots[representation] = {grid: ds.load() for grid, ds in groups.items()}
    analysis, faces = snapshots["mass_earth"], snapshots["native"]
    assert all("UT" not in ds and "VT" not in ds for ds in analysis.values())
    assert all("UT" not in ds and "VT" not in ds for ds in faces.values())
    face_u = next(ds.U2 for ds in faces.values() if "U2" in ds)
    face_v = next(ds.V2 for ds in faces.values() if "V2" in ds)
    mass_u = next(ds.U2 for ds in analysis.values() if "U2" in ds)
    mass_v = next(ds.V2 for ds in analysis.values() if "V2" in ds)
    np.testing.assert_array_equal(face_u.level, [5., 15.])
    np.testing.assert_allclose(face_u.isel(time=0, level=0, nj_u=4),
                               10 + np.arange(-4.5, 5), rtol=0, atol=1e-12)
    np.testing.assert_allclose(face_v, 0, rtol=0, atol=1e-12)
    np.testing.assert_allclose(mass_u, 0, rtol=0, atol=1e-12)
    np.testing.assert_allclose(mass_v.isel(time=0, level=0, nj=4),
                               10 + np.arange(-4., 5), rtol=0, atol=1e-12)
    for name, standard in (("U2", "x_wind"), ("V2", "y_wind")):
        native_field = next(ds[name] for ds in faces.values() if name in ds)
        mass_field = next(ds[name] for ds in analysis.values() if name in ds)
        assert native_field.attrs["units"] == "m s-1"
        assert native_field.attrs["wind_reference_frame"] == "grid"
        assert native_field.attrs["standard_name"] == standard
        assert mass_field.attrs["units"] == "m s-1"
        assert mass_field.attrs["wind_reference_frame"] == "earth"
    assert mass_u.attrs["standard_name"] == "eastward_wind"
    assert mass_v.attrs["standard_name"] == "northward_wind"


@pytest.fixture
def mixed_horizontal_file(tmp_path):
    source = native_scene()
    for name in ("ni_u", "nj_v"):
        source = source.assign_coords({name: (source[name] / 1000).assign_attrs(units="km")})
    path = tmp_path / "native0.nc"
    source.to_netcdf(path, engine="netcdf4")
    return path


def test_mixed_horizontal_coordinate_units_preserve_physical_faces(mixed_horizontal_file):
    path = mixed_horizontal_file
    conf = loader_config(path, {"3d": ["UT", "VT"], "levels": {"domain": "physical"}},
                         [{"u": "UT", "v": "VT", "basis": "grid",
                            "rotation": {"method": "coordinate", "coordinate": "angle"}}])
    raw, snapshots = conf.yaml_config, {}
    for representation in ("native", "mass_earth"):
        raw["sources"]["atmosphere"]["transforms"] = [
            {"fields": ["UT", "VT"], "units": "m s-1",
             **({"sampling": "mass", "basis": "earth"}
                if representation == "mass_earth" else {})}]
        _, children, _ = bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))
        with FrameitRunner(children["atmosphere"]) as runner:
            groups, _, _ = runner.load_dataset()
            snapshots[representation] = {grid: ds.load() for grid, ds in groups.items()}
    analysis, faces = snapshots["mass_earth"], snapshots["native"]
    face_u = next(ds.UT for ds in faces.values() if "UT" in ds)
    face_v = next(ds.VT for ds in faces.values() if "VT" in ds)
    mass_u = next(ds.UT for ds in analysis.values() if "UT" in ds)
    mass_v = next(ds.VT for ds in analysis.values() if "VT" in ds)
    expected_faces = np.arange(-4.5, 5) * 1000
    for name in ("ni", "nj"):
        np.testing.assert_array_equal(mass_u[name], np.arange(-4., 5) * 1000)
    np.testing.assert_allclose(face_u.isel(time=0, level=0, nj_u=4),
                               10 + expected_faces / 1000, rtol=0, atol=1e-12)
    np.testing.assert_allclose(mass_u, 0, rtol=0, atol=1e-12)
    np.testing.assert_allclose(mass_v.isel(time=0, level=0, nj=4),
                               10 + np.arange(-4., 5), rtol=0, atol=1e-12)
    coordinates = {"ni_u": face_u.ni_u, "nj_v": face_v.nj_v}
    units = {name: coordinate.attrs.get("units") for name, coordinate in coordinates.items()}
    assert units == {"ni_u": "m", "nj_v": "m"}, units
    for name in ("ni_u", "nj_v"):
        np.testing.assert_allclose(coordinates[name], expected_faces, rtol=0, atol=1e-12)


def test_native_crop_preserves_faces_with_mixed_horizontal_units(mixed_horizontal_file):
    # Exercise native cropping/export as well as the pre-crop loader arrays.
    ds = run_export(mixed_horizontal_file.parent, "native", "interfaces")[
        "model_grid", "atmosphere"]
    np.testing.assert_allclose(ds.UT.isel(time=0, level=0, y=1),
                               [8.5, 9.5, 10.5, 11.5], rtol=0, atol=1e-12)
    np.testing.assert_allclose(ds.latitude_u.isel(time=0, y=1),
                               -20 + np.array([-1500., -500., 500., 1500.]) / 111000,
                               rtol=0, atol=1e-12)
    np.testing.assert_allclose(ds.longitude_v.isel(time=0, x=1),
                               60 - np.array([-1500., -500., 500., 1500.]) /
                               (111000 * np.cos(np.deg2rad(20))), rtol=0, atol=1e-12)


def test_w_interpolation_uses_physical_coordinates_with_km_interfaces(tmp_path):
    source = native_scene()
    # Leave the independently evaluated W values unchanged: W = 70 + 3*z_metres.
    # Only its coordinate representation changes, not the sampled physical field.
    attrs = dict(source.level_w.attrs, units="km")
    source = source.assign_coords(level_w=(source.level_w / 1000).assign_attrs(attrs))
    path = tmp_path / "native.nc"
    source.to_netcdf(path, engine="netcdf4")
    conf = loader_config(path, {"3d": ["THT", "WT"], "levels": {"domain": "physical"}}, [])
    raw, snapshots = conf.yaml_config, {}
    for representation in ("native", "mass"):
        raw["sources"]["atmosphere"]["transforms"] = [
            {"fields": ["WT"], "units": "m s-1",
             **({"sampling": "mass"} if representation == "mass" else {})}]
        _, children, _ = bind_sources(SimulationConfig.from_mapping_with_model_preset(raw))
        with FrameitRunner(children["atmosphere"]) as runner:
            groups, _, _ = runner.load_dataset()
            snapshots[representation] = next(ds.load() for ds in groups.values() if "WT" in ds)
    mass = snapshots["mass"]
    np.testing.assert_array_equal(mass.level, [5., 15.])
    assert mass.level.attrs["units"] == "m"
    assert mass.WT.dims == ("time", "level", "nj", "ni")
    truth = xr.broadcast(xr.DataArray([85., 115.], dims="level",
                                      coords={"level": [5., 15.]}), mass.WT)[0]
    np.testing.assert_allclose(mass.WT, truth.transpose(*mass.WT.dims),
                               rtol=0, atol=1e-12)
    assert mass.WT.attrs["units"] == "m s-1"
    interfaces = snapshots["native"]
    np.testing.assert_allclose(interfaces.WT.isel(time=0, nj=4, ni=4),
                                [70., 100., 130.], rtol=0, atol=1e-12)


@pytest.mark.parametrize("case", [
    "native", "model_mass", "polar_mass", "both_mass", "missing_destination_level",
    "pending_transform", "pending_derived", "unavailable_support", "destination_loses_axis",
    "model_mass_ancillary", "model_mass_ancillary_exported", "model_mass_ancillary_nested",
    "model_mass_ancillary_missing", "pending_transform_ancillary",
])
def test_v3_representation_level_binding(tmp_path, monkeypatch, case):
    from frameit.testing.numerical.test_request_selection import (
        bind_inventory,
        binding_inventory,
        binding_scene,
    )

    # Destination coordinates/support are declared fixtures, not a W-remap test.
    ds = binding_scene()
    ancillary = "ancillary" in case
    if ancillary:
        ds["quality"] = (("time", "level_w", "y", "x"), np.ones((2, 7, 2, 3)),
                         {"units": "1", "flag_values": [0, 1]})
        ds.W.attrs["ancillary_variables"] = "quality"
        if case == "model_mass_ancillary_nested":
            ds["quality2"] = ds.quality.copy()
            ds.quality.attrs["ancillary_variables"] = "quality2"
    variables = {"3d": ["T", "W"], "levels": {"indices": [5, 0]}}
    extra = {"region": {"center": {"latitude": 0, "longitude": 0}},
             "products": {"model_grid": True, "polar": {"radius_km": 1}}}
    if case != "native":
        extra["sources"] = {"weather": {
            "files": str(tmp_path / "source.nc"), "variables": variables}}
        if case in {"model_mass", "both_mass", "missing_destination_level",
                    "pending_transform", "unavailable_support", "destination_loses_axis",
                    "pending_transform_ancillary"} or case.startswith("model_mass_ancillary"):
            extra["sources"]["weather"]["transforms"] = [
                {"fields": ["W"], "sampling": "mass"}]
    if case == "model_mass_ancillary_exported":
        variables["3d"].append("quality")
    if case == "model_mass_ancillary_missing":
        support = tmp_path / "support.nc"
        ds[["quality"]].isel(level_w=slice(0, 6)).to_netcdf(support, engine="h5netcdf")
        ds = ds.drop_vars("quality")
        extra["sources"]["weather"]["files"] = [str(tmp_path / "source.nc"), str(support)]
    if case == "pending_derived":
        extra["sources"]["weather"]["derived"] = {
            "speed": {"method": "wind_speed", "inputs": {"u": "T", "v": "U"}}}
        extra["products"] = {"model_grid": {"fields": {"weather": ["speed"]}}}
    if case == "pending_transform_ancillary":
        extra["products"] = {"model_grid": True}
    conf, source, reads = binding_inventory(
        tmp_path, monkeypatch, ds, variables=variables, extra=extra)
    original_files, original_times = list(source["files"]), list(source["selected_times"])
    request = conf.source_requests["weather"]
    representations = {}
    destination = {
        "dimensions": {"level": 6, "y": 2, "x": 3},
        "coordinates": {"level": {
            "dimensions": ["level"], "values": np.array([0., 10., 20., 30., 40., 50.]),
            "attributes": {"axis": "Z", "units": "m"}, "dtype": "float64",
            "role": "coordinate_metadata"}},
    }
    if case == "missing_destination_level":
        destination["dimensions"]["level"] = 5
        destination["coordinates"]["level"]["values"] = np.arange(5.) * 10
    native_id = next(r["grid_id"] for r in source["record_inventory"] if r["name"] == "W")
    for product in ("model_grid", "polar"):
        mass = (product == "model_grid" and case in {
            "model_mass", "both_mass", "missing_destination_level", "unavailable_support",
            "destination_loses_axis"}
                or product == "model_grid" and case.startswith("model_mass_ancillary")
                or product == "polar" and case in {"polar_mass", "both_mass"})
        if not mass:
            continue
        if product == "polar":
            request["polar_options"]["W"] = {"sampling": "mass"}
        representations[product] = {"W": {native_id: {
            "grid_id": "fixture_mass", "grid": destination, "sampling": "mass",
            "source_positions": {i: [i, i + 1] for i in range(6)}}}}
    if case == "unavailable_support":
        representations["model_grid"]["W"][native_id]["source_positions"][5] = [6, 7]
    if case == "destination_loses_axis":
        destination["dimensions"].pop("level")
        destination["coordinates"] = {}
    if case in {"missing_destination_level", "unavailable_support", "destination_loses_axis",
                "model_mass_ancillary_missing"}:
        error = (r"quality.*vertical index support unavailable for \[6\]"
                 if case == "model_mass_ancillary_missing" else
                 "unavailable.*5|support.*unavailable|vertical.*axis")
        with pytest.raises(ValueError, match=error):
            bind_inventory(conf, representations=representations)
        assert request["binding"] is None
        assert not (tmp_path / "out").exists()
        assert source["files"] == original_files and source["selected_times"] == original_times
        assert not any(name in {"T", "W", "quality", "quality2"} for name, _ in reads)
        return
    binding = bind_inventory(conf, representations=representations)
    assert source["files"] == original_files and source["selected_times"] == original_times
    assert not any(name in {"T", "W", "quality", "quality2"} for name, _ in reads)
    # Polar preparation/derived method support is not implemented by these fixtures.
    assert binding["status"] == "pending_method_binding"
    assert request["binding"] is None
    if case in {"pending_transform", "pending_derived", "pending_transform_ancillary"}:
        assert binding["deferred_checks"]
        if ancillary:
            assert binding["products"]["model_grid"]["W"]["records"] == []
            assert binding["dependencies"]["quality"]["records"] == []
            assert any("quality" in check and "pending method binding" in check
                       for check in binding["deferred_checks"])
        return
    for product in ("model_grid", "polar"):
        record = binding["products"][product]["W"]["records"][0]
        mass = product in representations
        assert record["vertical"]["dimension"] == ("level" if mass else "level_w")
        assert record["vertical"]["positions"] == [5, 0]
        assert record["vertical"]["values"] == ([50., 0.] if mass else [45., -5.])
        assert record["selection_grid_id"] == ("fixture_mass" if mass else native_id)
        assert record["source_positions"] == ([5, 6, 0, 1] if mass else [5, 0])
    assert request["levels"] == {"indices": [5, 0]}
    if ancillary:
        assert len(binding["dependencies"]["quality"]["records"]) == 2
        for record in binding["dependencies"]["quality"]["records"]:
            assert record["selection_grid_id"] == native_id
            assert record["source_positions"] == [5, 6, 0, 1]
            assert record["vertical"]["dimension"] == "level_w"
            assert record["vertical"]["positions"] == [5, 6, 0, 1]
            assert record["vertical"]["values"] == [45., 55., -5., 5.]
        if case == "model_mass_ancillary_exported":
            for product in ("model_grid", "polar"):
                assert len(binding["products"][product]["quality"]["records"]) == 2
                for record in binding["products"][product]["quality"]["records"]:
                    assert record["source_positions"] == [5, 0]
                    assert record["vertical"]["positions"] == [5, 0]
                    assert record["vertical"]["values"] == [45., -5.]
        if case == "model_mass_ancillary_nested":
            assert len(binding["dependencies"]["quality2"]["records"]) == 2
            for record in binding["dependencies"]["quality2"]["records"]:
                assert set(record["source_positions"]) == {5, 6, 0, 1}
        assert source["files"] == [str(tmp_path / "source.nc")]
