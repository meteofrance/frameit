"""Export-level analytical contracts for independent MNH grid choices.

The small rotated grid has grid-x northward and grid-y westward. Truth is
evaluated from labelled sampling locations, not FrameIt's collocation helpers.
These synthetic checks verify representation, not general model validity.
"""

from importlib.resources import files

import numpy as np
import pytest
import xarray as xr

from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.settings_class import SimulationConfig


def test_real_mnh_native_faces_match_source_file(tmp_path):
    path = files("frameit.testing").joinpath(
        "ci_dataset/MNH/CHIDO/3CH09.1.MXX30.011diag.nc")
    with xr.open_dataset(path, engine="netcdf4") as source:
        latitude = float(source.latitude[35, 37])
        longitude = float(source.longitude[35, 37])
        expected_u = source.UT.isel(time=0, level=[1, 3, 5],
                                    nj_u=slice(34, 37), ni_u=slice(36, 40)).values
        expected_v = source.VT.isel(time=0, level=[1, 3, 5],
                                    nj_v=slice(34, 38), ni_v=slice(36, 39)).values
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 2, "model": "mesonh",
        "input": {"files": [str(path)], "wind_pairs": [
            {"group": "level", "u": "UT", "v": "VT", "reference_frame": "grid",
             "rotation": {"method": "geolocation"}}]},
        "tracking": {"method": "fixed_box", "fixed_box": {
            "center": {"latitude": latitude, "longitude": longitude}}},
        "domain": {"size_km": {"x": 6, "y": 6}},
        "variables": {"level": {"names": ["UT", "VT"], "levels": {"indices": [1, 3, 5]}}},
        "output": {"directory": str(tmp_path / "real-native"),
                   "cartesian": {"horizontal_winds": "native"}},
    })
    result = execute_simulation(
        conf, ExecutionOptions.from_config(conf, synchronous_export=True))
    product = next(p for p in result.products if p["role"] == "cart")
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
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord
    from frameit.processing.wind_collocation import select_vertical_velocity

    path = tmp_path / "native.nc"
    native_scene().to_netcdf(path, engine="netcdf4")
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 2, "model": "mesonh",
        "input": {"files": [str(path)]},
        "tracking": {"method": "fixed_box", "fixed_box": {
            "center": {"latitude": -20., "longitude": 60.}}},
        "variables": {"level_w": {"names": ["WT"], "levels": {"indices": [1, 2]}}},
    })
    with DatasetResources() as resources:
        groups, _ = concat_nc2ds_by_vert_coord(
            [path], conf.requests_user(), {}, wind_conf=conf, resources=resources,
            engine="netcdf4")
        mass = select_vertical_velocity(groups, conf, "mass")["level"]
        np.testing.assert_array_equal(mass.level, [5., 15.])
        np.testing.assert_allclose(mass.WT[:, :, 0, 0], [[85., 115.]])


@pytest.fixture
def native_files(tmp_path):
    native_scene().to_netcdf(tmp_path / "native0.nc", engine="netcdf4")
    return tmp_path


def run_export(directory, horizontal="native", vertical="interfaces", *,
               polar=False, polar_vertical="mass", label="run"):
    config = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 2, "model": "mesonh", "run": {"name": label},
        "input": {"directory": str(directory), "pattern": "native*.nc", "wind_pairs": [
            {"group": "level", "u": "UT", "v": "VT", "reference_frame": "grid",
             "rotation": {"method": "coordinate", "coordinate": "angle"}},
            {"group": "surface", "u": "UM10", "v": "VM10", "reference_frame": "earth"},
        ]},
        "tracking": {"method": "fixed_box", "fixed_box": {
            "center": {"latitude": -20., "longitude": 60.}}},
        "domain": {"size_km": {"x": 2, "y": 2}},
        "variables": {
            "level": {"names": ["UT", "VT", "THT"], "levels": "physical"},
            "level_w": {"names": ["WT", "Q"], "levels": "physical"},
            "surface": {"names": ["UM10", "VM10", "MSLP"]},
        },
        "polar": {"enabled": polar, "variables": "all", "radial_step_m": 1000,
                  "azimuth_count": 8},
        "output": {"directory": str(directory / label), "engine": "netcdf4",
                   "cartesian": {"horizontal_winds": horizontal, "vertical_velocity": vertical},
                   "polar": {"vertical_velocity": polar_vertical}},
    })
    result = execute_simulation(
        config, ExecutionOptions.from_config(config, synchronous_export=True))
    assert result.ok
    assert result.n_files == len(list(directory.glob("native*.nc")))
    snapshots = {}
    for product in result.products:
        key = product["role"], product["group"]
        assert key not in snapshots, f"Duplicate exported descriptor: {key}"
        # Ordinary CF decoding, after execute_simulation has closed its resources.
        with xr.open_dataset(product["path"], engine="netcdf4") as reopened:
            snapshots[key] = reopened.load()
        assert not any(name.startswith("_frameit") for name in snapshots[key].variables)
    assert ("track", None) in snapshots
    for group in ("level", "level_w", "surface"):
        assert ("cart", group) in snapshots
        if polar:
            assert ("polar", group) in snapshots
    return snapshots


def assert_vertical(products, role, location):
    mass = products[role, "level"]
    interfaces = products[role, "level_w"]
    np.testing.assert_array_equal(mass.level, [5., 15.])
    np.testing.assert_array_equal(interfaces.level_w, [0., 10., 20.])
    # Q is not W: selecting mass W must never move/drop unrelated interface data.
    assert "level_w" in interfaces.Q.dims
    expected_q = xr.broadcast(1000 + 2 * interfaces.level_w, interfaces.Q)[0]
    np.testing.assert_allclose(interfaces.Q, expected_q.transpose(*interfaces.Q.dims))
    if location == "mass":
        assert "WT" not in interfaces
        assert "level" in mass.WT.dims and "level_w" not in mass.WT.dims
        # Interpolation at z=5 and z=15 gives 85 and 115, respectively.
        w = mass.WT
        expected = 70 + 3 * mass.level
    else:
        assert "WT" not in mass
        assert "level_w" in interfaces.WT.dims and "level" not in interfaces.WT.dims
        w = interfaces.WT
        expected = 70 + 3 * interfaces.level_w
    truth = xr.broadcast(expected, w)[0].transpose(*w.dims)
    np.testing.assert_allclose(w, truth, atol=1e-10)
    assert w.attrs["standard_name"] == "upward_air_velocity"
    assert w.attrs["units"] == "m s-1"


@pytest.mark.parametrize("horizontal", ["native", "mass_earth"])
@pytest.mark.parametrize("vertical", ["interfaces", "mass"])
def test_cartesian_grid_choices_reopen_with_physical_samples(native_files, horizontal, vertical):
    products = run_export(native_files, horizontal, vertical)
    ds = products["cart", "level"]
    assert_vertical(products, "cart", vertical)
    np.testing.assert_allclose(ds.THT, 300)
    if horizontal == "native":
        assert ds.UT.dims == ("time", "level", "y_u_box", "x_u_box")
        assert ds.VT.dims == ("time", "level", "y_v_box", "x_v_box")
        assert ds.sizes["x_u_box"] == ds.sizes["x_box"] + 1
        assert ds.sizes["y_v_box"] == ds.sizes["y_box"] + 1
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
        assert ds.UT.dims == ds.VT.dims == ("time", "level", "y_box", "x_box")
        np.testing.assert_allclose(ds.UT, 0, atol=1e-12)
        truth = 10 + (ds.latitude + 20) * 111000 / 1000
        truth = xr.broadcast(truth, ds.VT)[0].transpose(*ds.VT.dims)
        np.testing.assert_allclose(ds.VT, truth, atol=1e-9)
        for name, standard in (("UT", "eastward_wind"), ("VT", "northward_wind")):
            assert ds[name].attrs["standard_name"] == standard
            assert ds[name].attrs["wind_reference_frame"] == "earth"
            assert ds[name].attrs["grid"] == 1
    surface = products["cart", "surface"]
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
    for group in ("level", "level_w", "surface"):
        xr.testing.assert_allclose(native["polar", group], earth["polar", group])
    for products in (native, earth):
        assert_vertical(products, "polar", polar_vertical)
        ds = products["polar", "level"]
        np.testing.assert_allclose(ds.UT, 0, atol=1e-12)
        # At the repeated polar origin the mass-grid wind is exactly (0, 10).
        np.testing.assert_allclose(ds.VT.isel(rr=0), 10, atol=1e-9)
        truth = 10 + (ds.latitude + 20) * 111000 / 1000
        truth = xr.broadcast(truth, ds.VT)[0].transpose(*ds.VT.dims)
        # ESMF bilinear weights use spherical cells, not an affine latitude
        # plane. Allow the cell-curvature scale: (1000 m / Earth radius) times
        # the 1 m/s cell-to-cell increment, rounded up to 2e-4 m/s.
        np.testing.assert_allclose(ds.VT, truth, rtol=0, atol=2e-4)
        assert np.isfinite(ds.VT).all()
        assert ds.UT.attrs["standard_name"] == "eastward_wind"
        assert ds.VT.attrs["standard_name"] == "northward_wind"
        assert ds.VT.attrs["wind_reference_frame"] == "earth"
        np.testing.assert_allclose(products["polar", "surface"].UM10, 3, atol=1e-10)
        np.testing.assert_allclose(products["polar", "surface"].VM10, 4, atol=1e-10)


@pytest.mark.parametrize("horizontal", ["native", "mass_earth"])
def test_each_file_normalizes_velocity_units_before_concatenation(native_files, horizontal):
    native_scene(hour=1, units="km/h").to_netcdf(
        native_files / "native1.nc", engine="netcdf4")
    products = run_export(native_files, horizontal, "mass")
    assert_vertical(products, "cart", "mass")
    for group, names in (("level", ("UT", "VT", "WT")),
                         ("surface", ("UM10", "VM10"))):
        ds = products["cart", group]
        assert ds.sizes["time"] == 2
        for name in names:
            assert ds[name].attrs["units"] == "m s-1"
            xr.testing.assert_allclose(ds[name].isel(time=0, drop=True),
                                       ds[name].isel(time=1, drop=True))
    ds = products["cart", "level"]
    if horizontal == "native":
        np.testing.assert_allclose(ds.UT.isel(x_u_box=0), 8.5, atol=1e-10)
    else:
        np.testing.assert_allclose(ds.VT.isel(x_box=1), 10, atol=1e-10)
    np.testing.assert_allclose(products["cart", "surface"].UM10, 3)
    np.testing.assert_allclose(products["cart", "surface"].VM10, 4)


def test_native_face_geography_normalizes_each_file_before_concat(native_files):
    second = native_scene(hour=1)
    face_geography = ("latitude_u", "longitude_u", "latitude_v", "longitude_v")
    for name in face_geography:
        second = second.assign_coords({
            name: np.deg2rad(second[name]).assign_attrs(units="rad"),
        })
    second.to_netcdf(native_files / "native1.nc", engine="netcdf4")
    products = run_export(native_files, "native", "interfaces")
    ds = products["cart", "level"]
    for name in face_geography:
        assert ds[name].sizes["time"] == 2
        assert ds[name].attrs["units"] == (
            "degrees_north" if name.startswith("latitude") else "degrees_east")
        xr.testing.assert_allclose(ds[name].isel(time=0, drop=True),
                                   ds[name].isel(time=1, drop=True))
    # Check the actual crop locations, not only agreement of the two files.
    x_faces = np.array([-1500., -500., 500., 1500.])
    y_mass = np.array([-1000., 0., 1000.])
    for time in (0, 1):
        np.testing.assert_allclose(ds.latitude_u.isel(time=time, y_u_box=1),
                                   -20 + x_faces / 111000, rtol=0, atol=1e-12)
        np.testing.assert_allclose(ds.longitude_u.isel(time=time, x_u_box=1),
                                   60 - y_mass / (111000 * np.cos(np.deg2rad(20))),
                                   rtol=0, atol=1e-12)
        np.testing.assert_allclose(ds.UT.isel(time=time, level=0, y_u_box=1),
                                   10 + x_faces / 1000, rtol=0, atol=1e-12)


def loader_config(path, variables, pairs):
    return SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 2, "model": "mesonh",
        "input": {"files": [str(path)], "wind_pairs": pairs},
        "tracking": {"method": "fixed_box", "fixed_box": {
            "center": {"latitude": -20., "longitude": 60.}}},
        "variables": variables,
    })


def test_secondary_declared_pair_normalizes_without_primary_alias_fields(tmp_path):
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

    path = tmp_path / "secondary.nc"
    source = native_scene(units="km/h").rename({"UT": "U2", "VT": "V2"})
    source.to_netcdf(path, engine="netcdf4")
    pairs = [
        {"group": "level", "u": u, "v": v, "reference_frame": "grid",
         "rotation": {"method": "coordinate", "coordinate": "angle"}}
        for u, v in (("UT", "VT"), ("U2", "V2"))
    ]
    conf = loader_config(path, {"level": {"names": ["U2", "V2"], "levels": "physical"}},
                         pairs)
    conf.velocity_aliases.update(u_velocity="UT", v_velocity="VT")
    native = {}
    with DatasetResources() as resources:
        groups, _ = concat_nc2ds_by_vert_coord(
            [path], conf.requests_user(), {}, wind_conf=conf, resources=resources,
            native_output_groups=native, engine="netcdf4")
        analysis, faces = groups["level"].load(), native["level"].load()
    assert "UT" not in analysis and "VT" not in analysis
    assert "UT" not in faces and "VT" not in faces
    np.testing.assert_array_equal(faces.level, [5., 15.])
    np.testing.assert_allclose(faces.U2.isel(time=0, level=0, nj_u=4),
                               10 + np.arange(-4.5, 5), rtol=0, atol=1e-12)
    np.testing.assert_allclose(faces.V2, 0, rtol=0, atol=1e-12)
    np.testing.assert_allclose(analysis.U2, 0, rtol=0, atol=1e-12)
    np.testing.assert_allclose(analysis.V2.isel(time=0, level=0, nj=4),
                               10 + np.arange(-4., 5), rtol=0, atol=1e-12)
    for name, standard in (("U2", "x_wind"), ("V2", "y_wind")):
        assert faces[name].attrs["units"] == "m s-1"
        assert faces[name].attrs["wind_reference_frame"] == "grid"
        assert faces[name].attrs["standard_name"] == standard
        assert analysis[name].attrs["units"] == "m s-1"
        assert analysis[name].attrs["wind_reference_frame"] == "earth"
    assert analysis.U2.attrs["standard_name"] == "eastward_wind"
    assert analysis.V2.attrs["standard_name"] == "northward_wind"


@pytest.fixture
def mixed_horizontal_file(tmp_path):
    source = native_scene()
    for name in ("ni_u", "nj_v"):
        source = source.assign_coords({name: (source[name] / 1000).assign_attrs(units="km")})
    path = tmp_path / "native0.nc"
    source.to_netcdf(path, engine="netcdf4")
    return path


def test_mixed_horizontal_coordinate_units_preserve_physical_faces(mixed_horizontal_file):
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

    path = mixed_horizontal_file
    conf = loader_config(path, {"level": {"names": ["UT", "VT"], "levels": "physical"}},
                         [{"group": "level", "u": "UT", "v": "VT", "reference_frame": "grid",
                           "rotation": {"method": "coordinate", "coordinate": "angle"}}])
    native = {}
    with DatasetResources() as resources:
        groups, _ = concat_nc2ds_by_vert_coord(
            [path], conf.requests_user(), {}, wind_conf=conf, resources=resources,
            native_output_groups=native, engine="netcdf4")
        analysis, faces = groups["level"].load(), native["level"].load()
    expected_faces = np.arange(-4.5, 5) * 1000
    for name in ("ni", "nj"):
        np.testing.assert_array_equal(analysis[name], np.arange(-4., 5) * 1000)
    np.testing.assert_allclose(faces.UT.isel(time=0, level=0, nj_u=4),
                               10 + expected_faces / 1000, rtol=0, atol=1e-12)
    np.testing.assert_allclose(analysis.UT, 0, rtol=0, atol=1e-12)
    np.testing.assert_allclose(analysis.VT.isel(time=0, level=0, nj=4),
                               10 + np.arange(-4., 5), rtol=0, atol=1e-12)
    units = {name: faces[name].attrs.get("units") for name in ("ni_u", "nj_v")}
    assert units == {"ni_u": "m", "nj_v": "m"}, units
    for name in ("ni_u", "nj_v"):
        np.testing.assert_allclose(faces[name], expected_faces, rtol=0, atol=1e-12)


def test_native_crop_preserves_faces_with_mixed_horizontal_units(mixed_horizontal_file):
    # Exercise native cropping/export as well as the pre-crop loader arrays.
    ds = run_export(mixed_horizontal_file.parent, "native", "interfaces")["cart", "level"]
    np.testing.assert_allclose(ds.UT.isel(time=0, level=0, y_u_box=1),
                               [8.5, 9.5, 10.5, 11.5], rtol=0, atol=1e-12)
    np.testing.assert_allclose(ds.latitude_u.isel(time=0, y_u_box=1),
                               -20 + np.array([-1500., -500., 500., 1500.]) / 111000,
                               rtol=0, atol=1e-12)
    np.testing.assert_allclose(ds.longitude_v.isel(time=0, x_v_box=1),
                               60 - np.array([-1500., -500., 500., 1500.]) /
                               (111000 * np.cos(np.deg2rad(20))), rtol=0, atol=1e-12)


def test_w_interpolation_uses_physical_coordinates_with_km_interfaces(tmp_path):
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord
    from frameit.processing.wind_collocation import select_vertical_velocity

    source = native_scene()
    # Leave the independently evaluated W values unchanged: W = 70 + 3*z_metres.
    # Only its coordinate representation changes, not the sampled physical field.
    attrs = dict(source.level_w.attrs, units="km")
    source = source.assign_coords(level_w=(source.level_w / 1000).assign_attrs(attrs))
    path = tmp_path / "native.nc"
    source.to_netcdf(path, engine="netcdf4")
    conf = loader_config(path, {
        "level": {"names": ["THT"], "levels": "physical"},
        "level_w": {"names": ["WT"], "levels": "physical"},
    }, [])
    native = {}
    with DatasetResources() as resources:
        groups, _ = concat_nc2ds_by_vert_coord(
            [path], conf.requests_user(), {}, wind_conf=conf, resources=resources,
            native_output_groups=native, engine="netcdf4")
        for loaded in (groups, native):
            mass = select_vertical_velocity(loaded, conf, "mass")["level"].load()
            np.testing.assert_array_equal(mass.level, [5., 15.])
            assert mass.level.attrs["units"] == "m"
            assert mass.WT.dims == ("time", "level", "nj", "ni")
            truth = xr.broadcast(xr.DataArray([85., 115.], dims="level",
                                              coords={"level": [5., 15.]}), mass.WT)[0]
            np.testing.assert_allclose(mass.WT, truth.transpose(*mass.WT.dims),
                                       rtol=0, atol=1e-12)
            assert mass.WT.attrs["units"] == "m s-1"
            interfaces = select_vertical_velocity(loaded, conf, "interfaces")["level_w"]
            np.testing.assert_allclose(interfaces.WT.isel(time=0, nj=4, ni=4),
                                       [70., 100., 130.], rtol=0, atol=1e-12)
