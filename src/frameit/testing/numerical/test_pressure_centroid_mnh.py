"""Independent native-level/geometry checks and MNH input failure contracts."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
from pyproj import CRS, Transformer

from frameit.cli import main
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources
from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord
from frameit.tracking.pressure_centroid import GEOD, interpolate_to_height
from frameit.tracking.pressure_centroid_grid import StructuredGrid
from frameit.tracking.pressure_centroid_inputs import (
    HEIGHT_FORMULA,
    inspect_mnh_sequence,
    prepare_mnh_inputs,
    resolve_mnh_fields,
)
from frameit.tracking.PressureCentroid_Tracker import PressureCentroidTracker


def native_vortex(*, moving=False, n=141):
    """A translating analytic vortex sampled on an azimuthal-equidistant grid."""
    xy = np.linspace(-700_000, 700_000, n)
    x, y = np.meshgrid(xy, xy)
    projection = CRS.from_proj4("+proj=aeqd +lat_0=-20 +lon_0=60 +datum=WGS84")
    lon, lat = Transformer.from_crs(projection, 4326, always_xy=True).transform(x, y)
    time = np.array(["2024-01-01", "2024-01-01T01:00"], dtype="datetime64[ns]")
    ds = xr.Dataset(coords={
        "time": time, "ni": ("ni", xy, {"units": "m"}),
        "nj": ("nj", xy, {"units": "m"}), "level": ("level", [1000., 3000.], {"units": "m"}),
        "longitude": (("nj", "ni"), lon, {"units": "degrees_east"}),
        "latitude": (("nj", "ni"), lat, {"units": "degrees_north"}),
    })
    terrain = 200 * np.exp(-(x / 200_000)**2 - (y / 200_000)**2)
    height = np.array([1000., 3000.])[:, None, None] + terrain
    ds["ALT"] = (("level", "nj", "ni"), height,
                 {"units": "m", "standard_name": "altitude", "positive": "up"})
    centers, pressure, u, v = [], [], [], []
    for k in range(2):
        center = GEOD.fwd(60, -20, 90, k * 3000)[:2] if moving else (60, -20)
        centers.append(center)
        _, back, distance = GEOD.inv(np.full(lon.shape, center[0]),
                                     np.full(lat.shape, center[1]), lon, lat)
        theta = np.deg2rad((back + 180) % 360)
        radius = distance / 1000
        speed = 40 * radius / 50 * np.exp(1 - radius / 50)
        pressure.append(80_000 - 4000 * np.exp(-(radius / 50)**2))
        u.append(speed * np.cos(theta) + (3000 / 3600 if moving else 0))
        v.append(-speed * np.sin(theta))
    horizontal, vertical = ("time", "nj", "ni"), ("time", "level", "nj", "ni")
    pressure = np.asarray(pressure)
    ds["PABST"] = (vertical, pressure[:, None] * np.exp(-(height[None] - 2000) / 8000),
                   {"units": "Pa"})
    ds["MSLP"] = (horizontal, pressure / 100 + 200, {"units": "hPa"})
    for name, value in (("UT_ZM", u), ("VT_ZM", v)):
        ds[name] = (vertical, np.broadcast_to(np.asarray(value)[:, None], (2, 2, n, n)),
                    {"units": "m s-1"})
    for name, value in (("UM10", u), ("VM10", v)):
        ds[name] = (horizontal, np.asarray(value), {"units": "m s-1"})
    return ds, centers


def wind_settings(*, grid_native=False):
    """Analytic ZM vectors are east/north; raw rotated native vectors are grid-based."""
    return SimpleNamespace(wind_reference_frame=None, wind_pairs=[
        dict(group="level", u="UT" if grid_native else "UT_ZM",
             v="VT" if grid_native else "VT_ZM",
             reference_frame="grid" if grid_native else "earth",
             **({"rotation": {"method": "geolocation"}} if grid_native else {})),
        dict(group="surface", u="UM10", v="VM10", reference_frame="earth"),
    ])


def config(tmp_path):
    return SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 2, "model": "mesonh",
        "input": {"directory": str(tmp_path), "pattern": "native*.nc",
                  "wind_pairs": wind_settings().wind_pairs},
        "tracking": {"method": "pressure_centroid"},
        "domain": {"size_km": {"x": 100, "y": 100}},
        "variables": {"surface": {"names": ["MSLP"]}},
        "polar": {"enabled": False}, "output": {"directory": str(tmp_path / "output")},
    })


def test_native_log_pressure_and_affine_wind_interpolation():
    height = np.array([[[1000., 1500.]], [[3000., 3500.]]])
    pressure = 100_000 * np.exp(-height / 8000)
    record = {"z": height, "pressure_field_pa": pressure, "u": height * .01,
              "v": height * -.02}
    result = interpolate_to_height(record)
    np.testing.assert_allclose(result["p"], 100_000 * np.exp(-2000 / 8000), rtol=1e-14)
    np.testing.assert_allclose(result["u"], 20)
    np.testing.assert_allclose(result["v"], -40)
    reverse = {key: value[::-1] for key, value in record.items()}
    for key, value in interpolate_to_height(reverse).items():
        np.testing.assert_allclose(value, result[key])
    np.testing.assert_allclose(interpolate_to_height(record, 1000)["p"][0, 0], pressure[0, 0, 0])
    assert np.isnan(interpolate_to_height(record, 4000)["p"]).all()
    invalid = {**record, "pressure_field_pa": -pressure}
    with pytest.raises(ValueError, match="positive"):
        interpolate_to_height(invalid)
    with pytest.raises(ValueError, match="monotone"):
        interpolate_to_height({**record, "z": np.zeros_like(height)})


def test_bilinear_native_cells_area_wrap_and_strict_support():
    x, y = np.meshgrid(np.arange(4.), np.arange(4.))
    lon, lat = 179 + x * .4 + y * .1 + x * y * .02, -20 + y * .4 + x * .05
    grid = StructuredGrid(lon, lat)
    field = 3 + 2 * x + 4 * y + x * y
    s, t = .3, .7
    query_lon = 179 + s * .4 + t * .1 + s * t * .02
    query_lat = -20 + t * .4 + s * .05
    assert grid.interpolator(field)(query_lon, query_lat) == pytest.approx(3 + 2*s + 4*t + s*t)
    assert grid.interpolator(field)(query_lon - 360, query_lat) == pytest.approx(
        3 + 2*s + 4*t + s*t)
    assert np.isnan(grid.interpolator(field)(170, -20))
    total = sum(abs(GEOD.polygon_area_perimeter(
        [lon[j, i], lon[j, i+1], lon[j+1, i+1], lon[j+1, i]],
        [lat[j, i], lat[j, i+1], lat[j+1, i+1], lat[j+1, i]])[0])
                for j in range(3) for i in range(3))
    assert grid.area.sum() == pytest.approx(total, rel=1e-14)
    missing = field.copy()
    missing[1, 1] = np.nan
    sample = grid.interpolator(missing)
    assert np.isnan(sample(query_lon, query_lat))
    assert sample(lon[0, 0], lat[0, 0]) == pytest.approx(field[0, 0])
    reversed_grid = StructuredGrid(lon[::-1, ::-1], lat[::-1, ::-1])
    assert reversed_grid.interpolator(field[::-1, ::-1])(query_lon, query_lat) == pytest.approx(
        3 + 2*s + 4*t + s*t)
    with pytest.raises(ValueError, match="folded|degenerate"):
        StructuredGrid(lon[:, [0, 2, 1, 3]], lat[:, [0, 2, 1, 3]])


def test_missing_inputs_give_mnh_recipe_and_file_time(tmp_path):
    source, _ = native_vortex(n=9)
    broken = source.drop_vars(["ALT", "PABST", "UT_ZM"])
    with pytest.raises(ValueError) as error:
        inspect_mnh_sequence([("native012.nc", broken)])
    message = str(error.value)
    for text in ("native012.nc", "2024-01-01", "PABST or PRES", "ALT", "wind pair",
                 "LTPZH=.TRUE.", "LWIND_ZM=.TRUE.", "frameit validate"):
        assert text in message
    broken.to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    with pytest.raises(ValueError, match="LTPZH"):
        preflight(config(tmp_path))
    assert not (tmp_path / "output").exists()


def test_formula_height_pressure_units_and_level_halos():
    source, _ = native_vortex(n=9)
    baseline = prepare_mnh_inputs(source, wind_settings())
    alternative = source.drop_vars("ALT").rename(PABST="PRES")
    alternative["PRES"] = (source.PABST / 100).assign_attrs(units="hPa")
    # Build the exact documented terrain-following formula, not an inference
    # from numeric model-level labels.
    alternative["ZTOP"] = xr.DataArray(10_000., attrs={"units": "m"})
    alternative["ZS"] = xr.zeros_like(source.MSLP.isel(time=0)).assign_attrs(units="m")
    alternative.level.attrs.update(formula_definition=HEIGHT_FORMULA,
                                   computed_standard_name="altitude",
                                   formula_terms="s: level height: ZTOP orog: ZS")
    result = prepare_mnh_inputs(alternative, wind_settings())
    np.testing.assert_allclose(result.height.isel(nj=0, ni=0), [1000, 3000])
    xr.testing.assert_allclose(result.pressure, baseline.pressure)
    for key in ("u", "v", "u10m", "v10m"):
        np.testing.assert_allclose(result[key], baseline[key])
    assert result.attrs["pressure_centroid_pressure_source"] == "PRES"
    unsupported = alternative.copy()
    unsupported.level.attrs = {"units": "m", "formula_definition": "SLEVE"}
    with pytest.raises(ValueError, match="physical model-level altitude"):
        resolve_mnh_fields(unsupported)
    halo = source.isel(level=[0, 0, 1, 1]).assign_coords(level=[-100., 1000., 3000., 5000.])
    halo.level.attrs.update(units="m", c_grid_dynamic_range="2:3")
    assert prepare_mnh_inputs(halo, wind_settings()).sizes["level"] == 2
    with pytest.raises(ValueError, match="AGL"):
        prepare_mnh_inputs(source.assign(ALT=source.ALT.assign_attrs(standard_name="height")),
                           wind_settings())


def test_raw_staggered_wind_rotation_and_surface_basis():
    # A locally rotated, orthogonal grid; +x points north and +y west.
    source, _ = native_vortex(n=9)
    x, y = np.meshgrid(np.arange(3.), np.arange(3.))
    ds = source.isel(ni=slice(0, 3), nj=slice(0, 3)).drop_vars(["UT_ZM", "VT_ZM"])
    ds = ds.assign_coords(ni=[0., 1000., 2000.], nj=[0., 1000., 2000.],
                          longitude=(("nj", "ni"), 60 - y * .01),
                          latitude=(("nj", "ni"), -20 + x * .01),
                          ni_u=[-500., 500., 1500., 2500.], nj_u=ds.nj.values,
                          nj_v=[-500., 500., 1500., 2500.], ni_v=ds.ni.values)
    # Replace the auxiliary unchanged coordinates on unstaggered axes explicitly.
    ds = ds.assign_coords(nj_u=ds.nj.values, ni_v=ds.ni.values)
    ds["UT"] = (("time", "level", "nj_u", "ni_u"), np.full((2, 2, 3, 4), 3.),
                {"units": "m s-1", "standard_name": "x_wind"})
    ds["VT"] = (("time", "level", "nj_v", "ni_v"), np.full((2, 2, 4, 3), 4.),
                {"units": "m s-1", "standard_name": "y_wind"})
    ds["UM10"] = xr.full_like(ds.MSLP, 7.).assign_attrs(units="m/s")
    ds["VM10"] = xr.full_like(ds.MSLP, 8.).assign_attrs(units="m/s")
    prepared = prepare_mnh_inputs(ds, wind_settings(grid_native=True))
    np.testing.assert_allclose(prepared.u, -4, atol=1e-7)
    np.testing.assert_allclose(prepared.v, 3, atol=1e-7)
    np.testing.assert_allclose(prepared.u10m, 7)
    np.testing.assert_allclose(prepared.v10m, 8)
    assert prepared.u.dims == ("time", "level", "nj", "ni")
    assert prepared.attrs["pressure_centroid_wind_rotation"] == "geolocation"
    # Mass and staggered coordinates may declare different compatible units.
    mixed = ds.assign_coords(ni_u=(ds.ni_u / 1000).assign_attrs(units="km"))
    xr.testing.assert_allclose(prepare_mnh_inputs(mixed, wind_settings(grid_native=True)).u,
                               prepared.u)


def test_loader_preserves_tracker_levels_and_checks_later_files(tmp_path):
    source, _ = native_vortex(n=9)
    for k in range(2):
        source.isel(time=[k]).to_netcdf(tmp_path / f"native{k}.nc", engine="h5netcdf")
    conf = config(tmp_path)
    with DatasetResources() as resources:
        user, tracker = concat_nc2ds_by_vert_coord(
            sorted(tmp_path.glob("native*.nc")),
            {"level": {"variables": ["UT_ZM"], "level_selection": "indices", "level_indices": [0]}},
            conf.requests_tracker(), method="pressure_centroid", wind_conf=conf,
            resources=resources,
        )
        assert user["level"].sizes["level"] == 1
        assert tracker["pressure_centroid"]["native"].sizes["level"] == 2
        assert "ALT" in tracker["pressure_centroid"]["native"]
    source.isel(time=[1]).drop_vars("PABST").to_netcdf(tmp_path / "native1.nc", engine="h5netcdf")
    with pytest.raises(ValueError, match="native1.nc.*time=2024-01-01T01"):
        preflight(conf)


@pytest.mark.parametrize("moving", [False, True])
def test_projected_native_vortex_centres_and_motion(moving):
    source, centers = native_vortex(moving=moving)
    tracker = PressureCentroidTracker({}, 10_000, model="MNH", conf=wind_settings())
    result = tracker({"pressure_centroid": {"native": source.chunk({"time": 1})}})
    _, _, error = GEOD.inv(result.lon.values, result.lat.values,
                           np.array(centers)[:, 0], np.array(centers)[:, 1])
    # This is a 10-km sampled analytic vortex: a 1-km bound is one tenth of
    # a source spacing, not a real-case scientific qualification claim.
    assert max(error) < 1000
    assert max(result.motion_residual_m) < 250
    np.testing.assert_allclose(result.environment_hpa, 800, atol=.01)
    np.testing.assert_allclose(result.radius_km, 2 * result.r80_km)
    assert result.cx.dtype.kind == "i"
    assert result.attrs["pressure_centroid_pressure_source"] == "PABST"


def test_mnh_end_to_end_output_reopens_without_frameit(tmp_path):
    source, _ = native_vortex()
    source.to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    conf = config(tmp_path)
    plan = preflight(conf)
    assert plan["tracking_inputs"]["pressure"] == "PABST"
    assert plan["tracking_inputs"]["winds"] == ["UT_ZM", "VT_ZM"]
    assert not conf.output_dir.exists()
    result = execute_simulation(conf, ExecutionOptions(synchronous_export=True))
    assert result.ok
    track = next(Path(product["path"]) for product in result.products if product["role"] == "track")
    # Ordinary xarray reader; no Frameit decoder or schema reconstruction.
    with xr.open_dataset(track, engine="h5netcdf") as reopened:
        assert reopened.sizes["time"] == 2
        assert reopened.environment_hpa.attrs["units"] == "hPa"
        assert reopened.attrs["pressure_centroid_height_reference"] == (
            "altitude_above_mean_sea_level")
        assert reopened.attrs["pressure_centroid_area_weighting"] == "WGS84_quadrilateral_nodal"
        np.testing.assert_allclose(reopened.lon, 60, atol=.01)
    assert "PABST" in (conf.output_dir / "run-provenance.yaml").read_text()
    subprocess.run([
        sys.executable, "-B", "-c",
        "import sys; import xarray as xr; "
        "ds = xr.open_dataset(sys.argv[1], engine='h5netcdf'); "
        "assert ds.sizes['time'] == 2; "
        "assert ds.environment_hpa.attrs['units'] == 'hPa'; "
        "assert abs(float(ds.lon.mean()) - 60) < .01; "
        "assert 'frameit' not in sys.modules; ds.close()", str(track),
    ], check=True, capture_output=True, text=True)


def test_cli_schema_and_mnh_diagnostic_failure(tmp_path, caplog):
    from frameit.core.configuration import write_template

    path = write_template("mesonh", tmp_path / "frameit.yaml", tracking="pressure_centroid")
    source, _ = native_vortex(n=9)
    source.drop_vars(["PABST", "ALT"]).to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    import yaml

    document = yaml.safe_load(path.read_text())
    document["input"] = {"directory": ".", "pattern": "native*.nc"}
    path.write_text(yaml.safe_dump(document))
    for args in (["validate", str(path)], ["run", str(path), "--dry-run"]):
        with pytest.raises(SystemExit) as exit_code:
            main(args)
        assert exit_code.value.code == 1
        assert "LTPZH=.TRUE." in caplog.text
    assert not (tmp_path / "output").exists()


def test_missing_vertical_brackets_and_reference_ring_fail_explicitly():
    source, _ = native_vortex()
    tracker = PressureCentroidTracker({}, 10_000, model="MNH", conf=wind_settings())
    too_high = source.assign(ALT=source.ALT + 3000)
    too_high.ALT.attrs["units"] = "m"
    with pytest.raises(ValueError, match="bracket 2,000 m"):
        tracker({"pressure_centroid": {"native": too_high}})
    cropped = source.isel(ni=slice(55, 86), nj=slice(55, 86))
    with pytest.raises(ValueError, match="500-km.*reference ring"):
        tracker({"pressure_centroid": {"native": cropped}})


def test_inconsistent_sequence_units_and_frames_are_not_silently_combined():
    source, _ = native_vortex(n=9)
    invalid = source.assign(PABST=source.PABST.assign_attrs(units="K"))
    with pytest.raises(ValueError, match="unsupported pressure units"):
        resolve_mnh_fields(invalid)
    changed = source.assign(PABST=(source.PABST / 100).assign_attrs(units="hPa"))
    with pytest.raises(ValueError, match="inconsistent.*units"):
        inspect_mnh_sequence([("first.nc", source), ("second.nc", changed)])
    contradictory = source.assign(UT_ZM=source.UT_ZM.assign_attrs(wind_reference_frame="grid"))
    with pytest.raises(ValueError, match="incompatible reference frames"):
        prepare_mnh_inputs(contradictory, wind_settings())


def test_formula_dependencies_survive_loading(tmp_path):
    source, _ = native_vortex(n=9)
    source = source.drop_vars("ALT")
    source["ZTOP"] = xr.DataArray(10_000., attrs={"units": "m"})
    source["ZS"] = xr.zeros_like(source.MSLP.isel(time=0)).assign_attrs(units="m")
    source.level.attrs.update(formula_definition=HEIGHT_FORMULA,
                              computed_standard_name="altitude",
                              formula_terms="s: level height: ZTOP orog: ZS")
    path = tmp_path / "native.nc"
    source.to_netcdf(path, engine="h5netcdf")
    conf = config(tmp_path)
    assert preflight(conf)["tracking_inputs"]["height"] == ["level", "ZTOP", "ZS"]
    with DatasetResources() as resources:
        _, tree = concat_nc2ds_by_vert_coord(
            [path], {}, conf.requests_tracker(), method="pressure_centroid", wind_conf=conf,
            resources=resources,
        )
        prepared = prepare_mnh_inputs(tree["pressure_centroid"]["native"], wind_settings())
        assert hasattr(prepared.u.data, "dask")
        np.testing.assert_allclose(
            prepared.height.broadcast_like(prepared.pressure).isel(time=0, nj=0, ni=0),
            [1000, 3000])


def test_bundled_mnh_header_identifies_pressure_as_missing():
    path = Path(__file__).parents[1] / "ci_dataset/MNH/CHIDO/3CH09.1.MXX30.011diag.nc"
    with xr.open_dataset(path, engine="h5netcdf") as header:
        with pytest.raises(ValueError) as error:
            resolve_mnh_fields(header, path.name)
    assert "Missing absolute pressure" in str(error.value)
    assert "Missing physical model-level altitude" not in str(error.value)
    assert "LTPZH=.TRUE." in str(error.value)
