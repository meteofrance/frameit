"""Analytic native-grid verification; not real-landfall or full NOAA qualification."""

import copy
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr
from pyproj import CRS, Transformer

from frameit.core.configuration import resolve_schema, write_template
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources
from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord
from frameit.tracking.multifield_inputs import canonical_inputs, inspect_inputs, iter_fields
from frameit.tracking.multifield_vortex import (
    PARAMETERS,
    VortexGrid,
    VortexOptions,
    combine_fixes,
    pressure_interpolate,
    quality_check,
    relative_vorticity,
    translation_speed,
)
from frameit.tracking.MultifieldVortex_Tracker import MultifieldVortexTracker
from frameit.tracking.pressure_centroid import G0, GEOD


def document(tmp_path, model="mesonh", latitude=-20.):
    pairs = ([dict(group="surface", u="UM10", v="VM10", reference_frame="earth"),
              dict(group="level", u="UT_ZM", v="VT_ZM", reference_frame="earth")]
             if model == "mesonh" else [
                 dict(group="surface", u="u10", v="v10", reference_frame="earth"),
                 dict(group="isobaricInhPa", u="u", v="v", reference_frame="earth")])
    return {
        "schema_version": 2, "model": model,
        "input": {"directory": str(tmp_path), "pattern": "native*.nc", "wind_pairs": pairs},
        "tracking": {"method": "multifield_vortex", "multifield_vortex": {
            "seed": {"latitude": latitude, "longitude": 60.,
                     "motion_u_m_s": 0., "motion_v_m_s": 0.},
            "mnh_gravity_m_s2": G0 if model == "mesonh" else None,
        }},
        "variables": {"surface": {"names": ["MSLP" if model == "mesonh" else "prmsl"]}},
        "domain": {"size_km": {"x": 150, "y": 150}},
        "output": {"directory": str(tmp_path / "output")},
    }


def vortex(*, model="mesonh", latitude=-20., moving=False, n=81):
    times = np.array(["2024-01-01", "2024-01-01T06:00"], dtype="datetime64[ns]")
    if model == "mesonh":
        axis = np.linspace(-1_300_000., 1_300_000., n)
        x, y = np.meshgrid(axis, axis)
        projection = CRS.from_proj4(f"+proj=aeqd +lat_0={latitude} +lon_0=60 +datum=WGS84")
        lon, lat = Transformer.from_crs(projection, 4326, always_xy=True).transform(x, y)
        spatial = ("nj", "ni")
        coords = {"ni": ("ni", axis, {"units": "m"}), "nj": ("nj", axis, {"units": "m"})}
    else:
        lon, lat = np.meshgrid(np.linspace(47.25, 72.75, n),
                               np.linspace(latitude - 12, latitude + 12, n))
        spatial = ("latitude", "longitude")
        coords = {"longitude": lon[0], "latitude": lat[:, 0]}
    ds = xr.Dataset(coords={"time": times, **coords})
    if model == "mesonh":
        ds = ds.assign_coords(longitude=(spatial, lon), latitude=(spatial, lat))
    for name, units in (("latitude", "degrees_north"), ("longitude", "degrees_east")):
        ds[name].attrs["units"] = units
    pressures, us, vs, amplitudes, centers = [], [], [], [], []
    for k in range(2):
        center = GEOD.fwd(60, latitude, 90, 15_000 * k)[:2] if moving else (60, latitude)
        centers.append(center)
        _, back, distance = GEOD.inv(np.full(lon.shape, center[0]),
                                     np.full(lat.shape, center[1]), lon, lat)
        theta = np.deg2rad((back + 180) % 360)
        radius = distance / 1000
        speed = 35 * radius / 90 * np.exp(1 - radius / 90)
        sign = 1 if latitude < 0 else -1
        us.append(sign * speed * np.cos(theta))
        vs.append(-sign * speed * np.sin(theta))
        amplitudes.append(120 * np.exp(-(radius / 120)**2))
        pressures.append(101000 - 5000 * np.exp(-(radius / 120)**2))
    horizontal = ("time", *spatial)
    wind_attrs = {"units": "m s-1", "GRIB_uvRelativeToGrid": 0}
    names = ("MSLP", "UM10", "VM10") if model == "mesonh" else ("prmsl", "u10", "v10")
    ds[names[0]] = (horizontal, np.asarray(pressures), {"units": "Pa"})
    ds[names[1]] = (horizontal, np.asarray(us), wind_attrs)
    ds[names[2]] = (horizontal, np.asarray(vs), wind_attrs)
    if model == "mesonh":
        ds = ds.assign_coords(level=("level", [0., 2000., 4500., 8500.], {"units": "m"}))
        h = np.broadcast_to(ds.level.values[:, None, None], (4, n, n))
        ds["ALT"] = (("level", *spatial), h, {"units": "m", "standard_name": "altitude"})
        p = 100000 * np.exp(-(h[None] + np.asarray(amplitudes)[:, None]) / 8000)
        ds["PABST"] = (("time", "level", *spatial), p, {"units": "Pa"})
        ds["UT_ZM"] = (("time", "level", *spatial),
                       np.repeat(np.asarray(us)[:, None], 4, axis=1), wind_attrs)
        ds["VT_ZM"] = (("time", "level", *spatial),
                       np.repeat(np.asarray(vs)[:, None], 4, axis=1), wind_attrs)
    else:
        ds = ds.assign_coords(isobaricInhPa=("isobaricInhPa", [850., 700., 500.], {"units": "hPa"}))
        vertical = ("time", "isobaricInhPa", *spatial)
        ds["u"] = (vertical, np.repeat(np.asarray(us)[:, None], 3, axis=1), wind_attrs)
        ds["v"] = (vertical, np.repeat(np.asarray(vs)[:, None], 3, axis=1), wind_attrs)
        h = 8000 * np.log(1000 / np.array([850, 700, 500]))[None, :, None, None]
        ds["z"] = (vertical, (h - np.asarray(amplitudes)[:, None]) * G0, {"units": "m2 s-2"})
    return ds, centers


def test_log_pressure_native_interpolation_known_profiles():
    z = np.array([0., 2000., 5000., 8000.])[:, None, None] + np.array([[[0., 100.]]])
    p = 100000 * np.exp(-z / 8000)
    actual = pressure_interpolate(p, {"z": z, "u": 2 + .003*z})
    expected = 8000 * np.log(100000 / np.array([85000, 70000, 50000]))
    np.testing.assert_allclose(actual["z"],
                               np.broadcast_to(expected[:, None, None], (3, 1, 2)), atol=1e-11)
    np.testing.assert_allclose(actual["u"], 2 + .003*actual["z"], atol=1e-12)
    reverse = pressure_interpolate(p[::-1], {"z": z[::-1]})
    np.testing.assert_allclose(reverse["z"], actual["z"])
    assert np.isnan(pressure_interpolate(p, {"z": z}, (110000.,))["z"]).all()
    with pytest.raises(ValueError, match="positive"):
        pressure_interpolate(-p, {"z": z})
    with pytest.raises(ValueError, match="monotone"):
        pressure_interpolate(np.repeat(p[:1], 4, axis=0), {"z": z})


def test_ellipsoidal_vorticity_analytic_solid_rotation_and_warped_grid():
    lon, lat = np.meshgrid(np.linspace(56, 64, 81), np.linspace(-25, -15, 101))
    phi = np.deg2rad(lat)
    n = 6378137. / np.sqrt(1 - 6.6943799901413165e-3 * np.sin(phi)**2)
    omega = 1e-4
    actual = relative_vorticity(omega * n * np.cos(phi), np.zeros_like(phi), lon, lat)
    np.testing.assert_allclose(actual[1:-1, 1:-1], (2 * omega * np.sin(phi))[1:-1, 1:-1], rtol=3e-6)
    # A second solution: v=k*lambda*N*cos(phi), u=0 gives constant curl k.
    j, i = np.meshgrid(np.arange(21.), np.arange(23.), indexing="ij")
    lon, lat = 60 + i*.01 + j*.003, -20 + j*.01 + i*.002
    n = 6378137. / np.sqrt(1 - 6.6943799901413165e-3 * np.sin(np.deg2rad(lat))**2)
    v = 2e-5 * np.deg2rad(lon - 60) * n * np.cos(np.deg2rad(lat))
    actual = relative_vorticity(np.zeros_like(v), v, lon, lat)
    np.testing.assert_allclose(actual[1:-1, 1:-1], 2e-5, atol=1e-11)


def test_barnes_matches_independent_direct_gaussian_sum():
    lon, lat = np.meshgrid(np.linspace(56, 64, 61), np.linspace(-24, -16, 61))
    grid = VortexGrid(lon, lat, 15000, VortexOptions())
    field = 10 + (lon - 60)**2 + 3*(lat + 20)**2
    _, _, distance = GEOD.inv(np.full(lon.shape, 60.1), np.full(lon.shape, -19.9), lon, lat)
    inside = distance <= grid.influence_km*1000
    w = np.exp(-(distance[inside] / (grid.efolding_km*1000))**2)
    expected = np.sum(field[inside]*w) / w.sum()
    assert grid.barnes((60.1, -19.9), field) == pytest.approx(expected, rel=1e-14)
    field[inside] = np.nan
    assert np.isnan(grid.barnes((60.1, -19.9), field))


def test_composite_weights_rejection_and_longitude_wrapping():
    positions = np.array([[179.9, -20], [-179.9, -20], [170., -20]])
    center, status, weights, _, spread, cutoff = combine_fixes(
        positions, [0, 0, 0], (180., -20), [])
    assert abs(abs(center[0]) - 180) < 1e-10
    assert status.tolist() == [0, 0, 4]
    np.testing.assert_allclose(weights, [.5, .5, 0.], atol=1e-12)
    assert 0 < spread < 20 and cutoff == 300
    assert combine_fixes(positions[:2], [0, 0], (180., -20), [1., 2.])[-1] == 225
    assert combine_fixes(positions[:2], [0, 0], (180., -20), [200.])[-1] == 485


@pytest.mark.parametrize("latitude", [-20., 20.])
def test_circulation_exact_samples_and_missing_arc(latitude):
    source, _ = vortex(latitude=latitude, n=41)
    lon, lat = source.longitude.values, source.latitude.values
    grid = VortexGrid(lon, lat, 65000, VortexOptions())
    center, omega = (60., latitude), 2e-5

    def component(x, y, which):
        _, back, distance = GEOD.inv(np.full(x.shape, center[0]), np.full(x.shape, center[1]), x, y)
        angle = np.deg2rad((back + 180) % 360)
        sign = 1 if latitude > 0 else -1
        return sign * omega * distance * (-np.cos(angle) if which == 0 else np.sin(angle))

    expected = 2*np.pi*omega*np.sum((np.arange(35, 216, 30)*1000.)**2)
    score = grid.circulation(center, lambda x, y: component(x, y, 0),
                             lambda x, y: component(x, y, 1))
    assert score == pytest.approx(expected, rel=1e-12)
    assert np.isnan(grid.circulation(center, lambda x, y: np.full_like(x, np.nan),
                                     lambda x, y: component(x, y, 1)))


def test_translation_qc_uses_elapsed_interval_not_hourly_noise():
    start = np.datetime64("2024-01-01T00:00", "ns")
    center = (60., -20.)
    relocated = GEOD.fwd(*center, 90., 200000.)[:2]
    assert np.isnan(translation_speed(start, center, start + np.timedelta64(1, "h"), relocated, 6))
    speed = translation_speed(start, center, start + np.timedelta64(7, "h"), relocated, 6)
    assert speed == pytest.approx(200000/25200, rel=1e-12)


def test_unresolved_spacing_is_not_a_silent_smoothing_choice():
    with pytest.raises(ValueError, match="resolved positive grid spacing"):
        VortexGrid(np.zeros((3, 3)), np.zeros((3, 3)), 0, VortexOptions())


def write_grib(path, ds, *, omit=None):
    import eccodes as ec

    with path.open("wb") as handle:
        for k in range(ds.sizes["time"]):
            for name, parameter in (("prmsl", 151), ("u10", 165), ("v10", 166),
                                    ("u", 131), ("v", 132), ("z", 129)):
                levels = ds.isobaricInhPa.values if name in {"u", "v", "z"} else [None]
                for level in levels:
                    if omit is not None and (name, level, k) == omit:
                        continue
                    # 500-hPa geopotential is not a required centre-fixing input.
                    if name == "z" and level == 500:
                        continue
                    message = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
                    try:
                        for key, value in {
                            "Ni": ds.sizes["longitude"], "Nj": ds.sizes["latitude"],
                            "latitudeOfFirstGridPointInDegrees": float(ds.latitude[0]),
                            "latitudeOfLastGridPointInDegrees": float(ds.latitude[-1]),
                            "longitudeOfFirstGridPointInDegrees": float(ds.longitude[0]),
                            "longitudeOfLastGridPointInDegrees": float(ds.longitude[-1]),
                            "iDirectionIncrementInDegrees": float(ds.longitude[1]-ds.longitude[0]),
                            "jDirectionIncrementInDegrees": float(ds.latitude[1]-ds.latitude[0]),
                            "jScansPositively": 1, "dataDate": 20240101, "dataTime": 0,
                            "forecastTime": k*6, "paramId": parameter, "uvRelativeToGrid": 0,
                            "bitsPerValue": 24,
                        }.items():
                            ec.codes_set(message, key, value)
                        if level is not None:
                            ec.codes_set(message, "typeOfLevel", "isobaricInhPa")
                            ec.codes_set(message, "level", int(level))
                        values = ds[name].isel(time=k)
                        if level is not None:
                            values = values.sel(isobaricInhPa=level)
                        ec.codes_set_values(message, values.values.ravel())
                        ec.codes_write(message, handle)
                    finally:
                        ec.codes_release(message)


def test_arome_grib_pipeline_and_variable_specific_time_coverage(tmp_path):
    source, _ = vortex(model="arome")
    path = tmp_path / "native.grib"
    write_grib(path, source)
    raw = document(tmp_path, "arome")
    raw["input"]["pattern"] = "*.grib"
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    preview = preflight(conf)
    assert preview["tracking_inputs"]["required_pressure_levels_hpa"] == [850, 700, 500]
    result = execute_simulation(conf, ExecutionOptions(synchronous_export=True))
    assert result.ok and result.tracking_complete
    # A shared isobaric coordinate must not hide a missing u message at one time.
    write_grib(path, source, omit=("u", 500., 1))
    with pytest.raises(ValueError, match="missing u at 500 hPa, time=2024-01-01T06"):
        preflight(SimulationConfig.from_mapping_with_model_preset(raw))


@pytest.mark.parametrize("model", ["arome", "mesonh"])
@pytest.mark.parametrize("latitude", [-20., 20.])
def test_seeded_analytic_vortex_on_both_models(tmp_path, model, latitude):
    source, centers = vortex(model=model, latitude=latitude, moving=True)
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, model, latitude))
    conf.resolution = 32500
    result = MultifieldVortexTracker(conf)({"multifield_vortex": {"all": source}})
    assert result.sizes["time"] == 2 and result.sizes["parameter"] == len(PARAMETERS)
    assert result.tracking_complete == 1
    _, _, errors = GEOD.inv(result.lon.values, result.lat.values,
                            np.array(centers)[:, 0], np.array(centers)[:, 1])
    # Source spacings are about 30 km; this bounds recovery within half a cell.
    assert max(errors) < 15000
    assert (result.accepted_parameter_count >= 7).all()
    assert result.cx.dtype.kind == "i"
    assert result.attrs["method_maturity"] == "experimental_native_grid_adaptation"


def test_mnh_native_height_convention_and_missing_fields(tmp_path):
    source, _ = vortex()
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path))
    prepared = canonical_inputs(source.chunk({"time": 1}), conf)
    record = next(iter_fields(prepared, conf))
    expected = 8000 * np.log(1000 / 850) - 120
    assert record["height"][0, 40, 40] == pytest.approx(expected, abs=1e-9)
    with pytest.raises(ValueError, match="LTPZH"):
        inspect_inputs([source.drop_vars("PABST")], conf, "native012.nc")
    unresolved = copy.deepcopy(conf)
    unresolved.multifield_vortex["mnh_gravity_m_s2"] = None
    with pytest.raises(ValueError, match="geopotential height convention"):
        inspect_inputs([source], unresolved)


def test_track_loss_prefix_error_and_independent_netcdf_reader(tmp_path, monkeypatch):
    source, _ = vortex()
    source["MSLP"][1] = 101000.
    source.to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path))
    preview = preflight(conf)
    assert preview["tracking_inputs"]["seed_has_full_steering_footprint"]
    assert not conf.output_dir.exists()
    import builtins

    original_import = builtins.__import__

    def no_optional_backend(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "utrack", "xesmf", "ESMF"}:
            raise ImportError(f"optional backend deliberately unavailable: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_optional_backend)
    result = execute_simulation(conf, ExecutionOptions(synchronous_export=True))
    assert result.ok and not result.tracking_complete
    assert result.tracking_termination_reason == "required_fix_missing"
    path = next(p["path"] for p in result.products if p["role"] == "track")
    with xr.open_dataset(path, engine="h5netcdf") as ds:
        assert ds.sizes["time"] == 1 and ds.sizes["attempt_time"] == 2
        assert ds.quality_status.values.tolist() == [0, 2]
        assert ds.parameter_lon.attrs["units"] == "degrees_east"
    subprocess.run([sys.executable, "-B", "-c",
                    "import sys; import xarray as xr; "
                    "d=xr.open_dataset(sys.argv[1],engine='h5netcdf'); "
                    "assert d.sizes['time']==1; assert d.sizes['parameter']==9; "
                    "assert d.attrs['tracking_complete']==0; "
                    "assert 'frameit' not in sys.modules; d.close()",
                    str(path)], check=True, capture_output=True)
    conf.multifield_vortex["on_track_loss"] = "error"
    with pytest.raises(ValueError, match="required_fix_missing"):
        MultifieldVortexTracker(conf)({"multifield_vortex": {"all": source}})


def test_structural_quality_checks_and_mask_support(tmp_path):
    source, _ = vortex()
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path))
    prepared = canonical_inputs(source, conf)
    fields = next(iter_fields(prepared, conf))
    center = (60., -20.)
    grid = VortexGrid(fields["lon"], fields["lat"], 32500, VortexOptions())
    positions = np.broadcast_to(center, (9, 2)).copy()
    statuses = np.zeros(9, dtype="int8")
    assert quality_check(grid, fields, center, positions, statuses, VortexOptions())[0] == 0
    no_gradient = {**fields, "mslp": np.full_like(fields["mslp"], 101000.)}
    assert quality_check(grid, no_gradient, center, positions, statuses, VortexOptions())[0] == 3
    no_wind = {**fields, "u": fields["u"]*0, "v": fields["v"]*0}
    assert quality_check(grid, no_wind, center, positions, statuses, VortexOptions())[0] == 4
    missing = {**fields, "mslp": np.full_like(fields["mslp"], np.nan)}
    assert quality_check(grid, missing, center, positions, statuses, VortexOptions())[0] == 7
    positions[0] = GEOD.fwd(*center, 90, 150000)[:2]
    positions[1] = GEOD.fwd(*center, 270, 150000)[:2]
    assert quality_check(grid, fields, center, positions, statuses,
                         VortexOptions(max_separation_km=200))[0] == 5


def test_mnh_per_file_pressure_and_height_units_are_normalized(tmp_path):
    source, _ = vortex(n=41)
    source.isel(time=[0]).to_netcdf(tmp_path / "native0.nc", engine="h5netcdf")
    other = source.isel(time=[1]).copy()
    other["PABST"] = (other.PABST / 100).assign_attrs(units="hPa")
    other["ALT"] = (other.ALT / 1000).assign_attrs(units="km", standard_name="altitude")
    other.to_netcdf(tmp_path / "native1.nc", engine="h5netcdf")
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path))
    preflight(conf)
    with DatasetResources() as resources:
        _, tree = concat_nc2ds_by_vert_coord(
            sorted(tmp_path.glob("native*.nc")), {}, conf.requests_tracker(),
            method="multifield_vortex", wind_conf=conf, resources=resources)
        loaded = tree["multifield_vortex"]["native"]
        np.testing.assert_allclose(loaded.pressure[0], loaded.pressure[1], rtol=1e-14)
        assert loaded.pressure.attrs["units"] == "Pa"
        assert loaded.height.attrs["units"] == "m"
        heights = loaded.height.broadcast_like(loaded.pressure)
        np.testing.assert_allclose(heights[0], heights[1], atol=1e-12)


@pytest.mark.parametrize("model", ["arome", "mesonh"])
@pytest.mark.parametrize("full", [False, True])
def test_template_and_seed_configuration(tmp_path, model, full):
    path = write_template(model, tmp_path / "frameit.yaml", full=full, tracking="multifield_vortex")
    conf = SimulationConfig.from_yaml_with_model_preset(path)
    assert conf.tracking_method == "multifield_vortex"
    raw = document(tmp_path, model)
    raw["tracking"]["multifield_vortex"]["seed"].pop("motion_u_m_s")
    with pytest.raises(ValueError, match="motion_u_m_s"):
        resolve_schema(raw)


@pytest.mark.parametrize("invalid", ["scalar_time", "multiple_realizations"])
def test_ambiguous_time_or_realization_fails_before_tracking(tmp_path, invalid):
    source, _ = vortex(model="arome", n=9)
    if invalid == "scalar_time":
        source = source.isel(time=0, drop=True)
    else:
        source = source.expand_dims(realization=[0, 1])
    conf = SimulationConfig.from_mapping_with_model_preset(document(tmp_path, "arome"))
    with pytest.raises(ValueError, match=r"time\(time\)|one realization"):
        MultifieldVortexTracker(conf)({"multifield_vortex": {"all": source}})
