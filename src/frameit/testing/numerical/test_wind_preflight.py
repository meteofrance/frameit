"""Header-only wind contracts and explicit catalog/centroid conventions."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import dask.array as da
import numpy as np
import pytest
import xarray as xr
from dask import delayed

from frameit.core.configuration import migrate_mapping, to_runtime
from frameit.core.preflight import (
    inspect_wind_pairs,
    preflight,
    selected_level_records,
    wind_dependencies,
)
from frameit.core.settings_class import SimulationConfig
from frameit.testing.catalog import load_cases
from frameit.testing.numerical.test_pressure_centroid_mnh import native_vortex
from frameit.tracking.pressure_centroid_inputs import prepare_mnh_inputs


def settings(frame="earth", rotation=None):
    return SimpleNamespace(
        atm_model="MNH", name_lon_dim="ni", name_lat_dim="nj",
        name_longitude="longitude", name_latitude="latitude",
        wind_reference_frame=None,
        velocity_aliases={"u_velocity": "UT", "v_velocity": "VT", "w_velocity": "WT"},
        tracking_var_aliases={"u10m": "UM10", "v10m": "VM10"},
        wind_pairs=[dict(group="level", u="UT", v="VT", reference_frame=frame,
                         rotation=rotation),
                    dict(group="surface", u="UM10", v="VM10", reference_frame="earth")],
    )


@pytest.mark.parametrize("variable", ["UT", "VT", "wind_speed"])
def test_single_component_dependencies_and_missing_companion(variable):
    conf = settings()
    requests = {"level": {"variables": [variable]}}
    expanded, pairs = wind_dependencies(conf, requests)
    assert {"UT", "VT"} <= set(expanded["level"]["variables"])
    assert requests["level"]["variables"] == [variable]
    with pytest.raises(ValueError, match="missing VT"):
        inspect_wind_pairs([xr.Dataset({"UT": ("level", [0.])})], conf, pairs, "fixture.nc")


def test_metadata_does_not_supply_an_undeclared_frame():
    conf = settings()
    conf.wind_pairs = []
    with pytest.raises(ValueError, match="needs a wind_pairs declaration"):
        wind_dependencies(conf, {"level": {"variables": ["UT"]}})


@pytest.mark.parametrize("metadata", [
    {"GRIB_uvRelativeToGrid": 1}, {"uvRelativeToGrid": "1"},
    {"standard_name": "x_wind"}, {"wind_reference_frame": "grid"},
    {"standard_name": "northward_wind"},
])
def test_conflicting_flags_cf_and_frames_fail(metadata):
    conf = settings()
    _, pairs = wind_dependencies(conf, {"level": {"variables": ["UT"]}})
    source = xr.Dataset({"UT": xr.DataArray([0.], dims="level", attrs=metadata),
                         "VT": ("level", [0.])})
    with pytest.raises(ValueError, match="Conflicting|wrong wind component"):
        inspect_wind_pairs([source], conf, pairs, "fixture.nc")


def test_preflight_rotation_reads_geometry_without_reading_winds():
    @delayed
    def forbidden():
        raise AssertionError("Preflight evaluated a velocity field")

    conf = settings("grid", {"method": "geolocation"})
    x, y = np.meshgrid(np.arange(3.), np.arange(3.))
    source = xr.Dataset(coords={
        "ni": [0., 1000., 2000.], "nj": [0., 1000., 2000.],
        "longitude": (("nj", "ni"), 60 + x * .01, {"units": "degrees_east"}),
        "latitude": (("nj", "ni"), -20 + y * .01, {"units": "degrees_north"}),
    })
    for name in ("UT", "VT"):
        source[name] = (("nj", "ni"), da.from_delayed(forbidden(), (3, 3), float))
    _, pairs = wind_dependencies(conf, {"level": {"variables": ["UT"]}})
    # Add the native level axis required by group membership.
    source = source.expand_dims(level=[1000.])
    records = inspect_wind_pairs([source], conf, pairs, "fixture.nc")
    assert records[0]["rotation_method"] == "geolocation"
    pairs[0]["rotation"] = {"method": "coordinate", "coordinate": "missing_angle"}
    with pytest.raises(ValueError, match="missing_angle"):
        inspect_wind_pairs([source], conf, pairs, "fixture.nc")
    pairs[0]["rotation"] = {"method": "mesonh_projection"}
    with pytest.raises(ValueError, match="BETA"):
        inspect_wind_pairs([source], conf, pairs, "fixture.nc")


def test_physical_level_provenance_preserves_original_indices():
    source = xr.Dataset(coords={
        "level": ("level", [-100., 500., 1500., 3000.], {"c_grid_dynamic_range": "2:4"}),
    })
    records = selected_level_records([source], {
        "level": {"variables": ["UT"], "level_selection": "physical"},
    }, "fixture.nc")
    assert records[0]["source_native_indices"] == [1, 2, 3]
    assert records[0]["values"] == [500., 1500., 3000.]
    selected = source.isel(level=[1, 3]).assign_coords(source_native_index=("level", [1, 3]))
    assert selected_level_records([selected], {
        "level": {"level_selection": "physical"},
    }, "fixture.nc")[0]["source_native_indices"] == [1, 3]


@pytest.mark.parametrize("name,units", [("w", "Pa s-1"), ("wz", "m s-1")])
def test_arome_vertical_quantities_have_no_horizontal_frame_requirement(tmp_path, name, units):
    source = xr.Dataset({name: (("time", "heightAboveGround", "latitude", "longitude"),
                               np.ones((1, 1, 3, 3)),
                               {"units": units, "GRIB_uvRelativeToGrid": 1})}, coords={
        "time": np.array(["2024-01-01"], dtype="datetime64[ns]"),
        "heightAboveGround": ("heightAboveGround", [100.], {"units": "m"}),
        "latitude": ("latitude", [-20.02, -20.01, -20.], {"units": "degrees_north"}),
        "longitude": ("longitude", [60., 60.01, 60.02], {"units": "degrees_east"}),
    })
    path = tmp_path / "vertical.nc"
    source.to_netcdf(path, engine="h5netcdf")
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 2, "model": "arome",
        "input": {"directory": str(tmp_path), "pattern": "vertical.nc"},
        "tracking": {"method": "fixed_box", "fixed_box": {
            "center": {"latitude": -20.01, "longitude": 60.01}}},
        "variables": {"heightAboveGround": {"names": [name], "levels": "all"}},
        "polar": {"enabled": False}, "output": {"directory": str(tmp_path / "output")},
    })
    assert conf.velocity_aliases["w_velocity"] == "wz"
    plan = preflight(conf)
    assert plan["wind_provenance"] == []
    record = next(r for r in plan["unit_provenance"] if r["variable"] == name)
    assert record["calculation_units"] == units
    if name == "w":
        source[name].attrs["units"] = "m s-1"
        source.to_netcdf(path, engine="h5netcdf")
        with pytest.raises(ValueError, match="pressure velocity"):
            preflight(conf)


@pytest.mark.parametrize("method", ["coordinate", "geolocation"])
def test_centroid_explicit_native_rotation_and_independent_surface_basis(method):
    source, _ = native_vortex(n=9)
    source = source.isel(ni=slice(0, 3), nj=slice(0, 3)).drop_vars(["UT_ZM", "VT_ZM"])
    x, y = np.meshgrid(np.arange(3.), np.arange(3.))
    source = source.assign_coords(
        ni=[0., 1000., 2000.], nj=[0., 1000., 2000.],
        longitude=(("nj", "ni"), 60 - y * .01, {"units": "degrees_east"}),
        latitude=(("nj", "ni"), -20 + x * .01, {"units": "degrees_north"}),
        ni_u=[-500., 500., 1500., 2500.], nj_v=[-500., 500., 1500., 2500.],
    )
    # Explicit canonical fixture: +grid-x is north, +grid-y is west.
    source["UT"] = (("time", "level", "nj", "ni_u"), np.full((2, 2, 3, 4), 3.),
                     {"units": "m s-1", "standard_name": "x_wind"})
    source["VT"] = (("time", "level", "nj_v", "ni"), np.full((2, 2, 4, 3), 4.),
                     {"units": "m s-1", "standard_name": "y_wind"})
    source["UM10"] = xr.full_like(source.UM10, 7.).assign_attrs(units="m s-1")
    source["VM10"] = xr.full_like(source.VM10, 8.).assign_attrs(units="m s-1")
    source = source.assign_coords(angle=xr.DataArray(90., attrs={"units": "degrees"}))
    rotation = {"method": method}
    if method == "coordinate":
        rotation["coordinate"] = "angle"
    conf = settings("grid", rotation)
    result = prepare_mnh_inputs(source, conf)
    np.testing.assert_allclose(result.u, -4, atol=1e-7)
    np.testing.assert_allclose(result.v, 3, atol=1e-7)
    np.testing.assert_allclose(result.u10m, 7)
    np.testing.assert_allclose(result.v10m, 8)
    assert result.attrs["pressure_centroid_native_wind_reference"] == "grid"
    assert result.attrs["pressure_centroid_surface_wind_reference"] == "earth"
    assert result.attrs["pressure_centroid_wind_rotation"] == method
    missing = source.drop_vars("angle" if method == "coordinate" else "longitude")
    with pytest.raises(ValueError, match="angle|longitude"):
        prepare_mnh_inputs(missing, conf)
    with pytest.raises(ValueError, match="Conflicting"):
        prepare_mnh_inputs(source)  # canonical numerical API explicitly requires Earth vectors
    conf.wind_pairs = []
    with pytest.raises(ValueError, match="needs a wind_pairs declaration"):
        prepare_mnh_inputs(source, conf)


def test_catalog_migration_preserves_source_and_output_conventions(tmp_path):
    for case in load_cases():
        old = deepcopy(case["config"])
        # Normally bound from the frozen fixture's centre_grid/track at resolution.
        old["fix_subdomain_center"] = old["fix_subdomain_center"] or [-10.3, 55.]
        if old["tracking_method"] == "prescribed_track":
            old["prescribed_track_file"] = "fixture-track.nc"
        if old["tracking_method"] == "utrack":
            old["utrack_weights_file"] = "fixture-weights.pt"
        migrated, _ = migrate_mapping(old, launch_dir=tmp_path)
        assert migrated["input"]["wind_pairs"] == old["wind_pairs"]
        runtime = to_runtime(migrated, base_dir=tmp_path)
        for key in ("wind_pairs", "cartesian_horizontal_winds", "cartesian_vertical_velocity",
                    "polar_vertical_velocity"):
            assert runtime[key] == old[key]


def test_source_examples_declare_conventions():
    import yaml

    root = Path(__file__).parents[4]
    for path in (root / "example").rglob("*.yml"):
        source = yaml.safe_load(path.read_text())
        conf = SimulationConfig.from_mapping_with_model_preset(source)
        assert conf.wind_pairs, path
        assert conf.wind_reference_frame is None
        assert conf.cartesian_horizontal_winds == "mass_earth"


def test_explicit_centroid_preflight_and_export(tmp_path):
    from frameit.core.execution import ExecutionOptions, execute_simulation

    source, _ = native_vortex()
    source.to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 2, "model": "mesonh",
        "input": {"directory": str(tmp_path), "pattern": "native.nc", "wind_pairs": [
            {"group": "level", "u": "UT_ZM", "v": "VT_ZM", "reference_frame": "earth"},
            {"group": "surface", "u": "UM10", "v": "VM10", "reference_frame": "earth"},
        ]},
        "tracking": {"method": "pressure_centroid"},
        "domain": {"size_km": {"x": 100, "y": 100}},
        "variables": {"surface": {"names": ["MSLP"]}},
        "polar": {"enabled": False}, "output": {"directory": str(tmp_path / "output")},
    })
    plan = preflight(conf)
    assert len(plan["wind_provenance"]) == 2
    assert plan["tracking_inputs"]["wind_reference_frames"]["UT_ZM"] == "earth"
    result = execute_simulation(conf, ExecutionOptions(synchronous_export=True))
    assert result.ok
    path = next(p["path"] for p in result.products if p["role"] == "track")
    with xr.open_dataset(path, engine="h5netcdf") as reopened:
        assert reopened.sizes["time"] == 2
        np.testing.assert_allclose(reopened.lon, 60., atol=.01)
        assert reopened.attrs["pressure_centroid_native_wind_reference"] == "earth"


def grib_blocks(stamp, *, scalar=True, units="m s-1", flag=1, angle=90.):
    """Synthetic cfgrib blocks with explicitly declared grid-basis vectors."""
    levels = 850. if scalar else [850., 700.]
    dims = ("latitude", "longitude") if scalar else (
        "isobaricInhPa", "latitude", "longitude")
    shape = (2, 2) if scalar else (2, 2, 2)
    scale = 3.6 if units == "km h-1" else 1.
    source = xr.Dataset(coords={
        "time": np.datetime64("2024-01-01", "ns"),
        "valid_time": np.datetime64(stamp, "ns"),
        "isobaricInhPa": xr.DataArray(levels, dims=() if scalar else "isobaricInhPa",
                                      attrs={"units": "hPa"}),
        "latitude": ("latitude", [-20., -19.99], {"units": "degrees_north"}),
        "longitude": ("longitude", [60., 60.01], {"units": "degrees_east"}),
        "crs": xr.DataArray(0, attrs={"grid_mapping_name": "latitude_longitude"}),
    })
    for name, value in (("u", 3.), ("v", 4.)):
        source[name] = (dims, np.full(shape, value * scale), {
            "units": units, "GRIB_uvRelativeToGrid": flag, "grid_mapping": "crs",
        })
    # Rotation geometry need not be a requested field or live in the wind block.
    geometry = xr.Dataset({"rotation": xr.DataArray(angle, attrs={"units": "degrees"})})
    return [source[["u"]], source[["v"]], geometry]


def grib_settings():
    return SimpleNamespace(
        atm_model="AROME", name_latitude="latitude", name_longitude="longitude",
        wind_reference_frame=None,
        wind_pairs=[{
            "group": "isobaricInhPa", "u": "u", "v": "v", "reference_frame": "grid",
            "rotation": {"method": "coordinate", "coordinate": "rotation"},
        }],
    )


def test_grib_per_file_units_rotation_and_native_branch(tmp_path, monkeypatch):
    from frameit.io import grib_utils
    from frameit.io.loader import DatasetResources

    paths = [tmp_path / "first.grib", tmp_path / "second.grib"]
    for path in paths:
        path.touch()
    blocks = {
        str(paths[0]): grib_blocks("2024-01-01", angle=90.),
        str(paths[1]): grib_blocks("2024-01-01T01:00", scalar=False,
                                  units="km h-1", angle=0.),
    }
    monkeypatch.setattr(grib_utils.cfgrib, "open_datasets", lambda path, **kw: blocks[path])
    request = {"isobaricInhPa": {
        "variables": ["u", "v"], "level_selection": "values", "level_values": [850.],
    }}
    native = {}
    with DatasetResources() as resources:
        user, tracker = grib_utils.concat_grib2ds_by_vert_coord(
            paths, request, {"pressure_centroid": request}, method="pressure_centroid",
            index_dir=tmp_path / "indexes", wind_conf=grib_settings(),
            native_output_groups=native, resources=resources,
        )
        prepared = user["isobaricInhPa"]
        assert prepared.sizes["time"] == 2
        assert prepared.sizes["isobaricInhPa"] == 1
        np.testing.assert_allclose(prepared.u.isel(time=0), -4., atol=1e-14)
        np.testing.assert_allclose(prepared.v.isel(time=0), 3., atol=1e-14)
        np.testing.assert_allclose(prepared.u.isel(time=1), 3., atol=1e-14)
        np.testing.assert_allclose(prepared.v.isel(time=1), 4., atol=1e-14)
        xr.testing.assert_identical(tracker["pressure_centroid"]["isobaricInhPa"], prepared)
        raw = native["isobaricInhPa"]
        np.testing.assert_allclose(raw.u, 3.)
        np.testing.assert_allclose(raw.v, 4.)
        assert set(raw.data_vars) == {"u", "v"}
        assert raw.u.attrs["units"] == prepared.u.attrs["units"] == "m s-1"
        assert raw.u.attrs["GRIB_uvRelativeToGrid"] == 1
        assert prepared.u.attrs["GRIB_uvRelativeToGrid"] == 0
        assert "crs" in raw.coords and "rotation" in raw.coords
        np.testing.assert_allclose(raw.rotation, [90., 0.])


def test_grib_later_frame_conflict_is_checked_before_concatenation(tmp_path, monkeypatch):
    from frameit.io import grib_utils

    paths = [tmp_path / "first.grib", tmp_path / "second.grib"]
    for path in paths:
        path.touch()
    blocks = {
        str(paths[0]): grib_blocks("2024-01-01"),
        str(paths[1]): grib_blocks("2024-01-01T01:00", flag=0),
    }
    monkeypatch.setattr(grib_utils.cfgrib, "open_datasets", lambda path, **kw: blocks[path])
    with pytest.raises(ValueError, match="Conflicting wind reference metadata"):
        grib_utils.concat_grib2ds_by_vert_coord(
            paths, {"isobaricInhPa": {"variables": ["u", "v"], "level_selection": "all"}},
            {}, index_dir=tmp_path / "indexes", wind_conf=grib_settings(),
        )


@pytest.mark.parametrize("selection", [
    {"level_selection": "physical"}, {"level_selection": "all"},
    {"level_selection": "indices", "level_indices": [0]},
    {"level_selection": "values", "level_values": [850.]},
])
def test_grib_all_scalar_level_headers_retain_selected_timestamps(tmp_path, monkeypatch, selection):
    from frameit.io import grib_utils

    paths = [tmp_path / "first.grib", tmp_path / "second.grib"]
    for path in paths:
        path.touch()
    blocks = {str(path): grib_blocks(stamp) for path, stamp in zip(
        paths, ["2024-01-01", "2024-01-01T01:00"], strict=True)}
    monkeypatch.setattr(grib_utils.cfgrib, "open_datasets", lambda path, **kw: blocks[path])
    user, _ = grib_utils.concat_grib2ds_by_vert_coord(
        paths, {"isobaricInhPa": {"variables": ["u", "v"], **selection}}, {},
        index_dir=tmp_path / "indexes",
    )
    try:
        assert user["isobaricInhPa"].sizes["time"] == 2
        assert user["isobaricInhPa"].isobaricInhPa.values.tolist() == [850.]
        # Omitting wind_conf retains the historical raw-vector API.
        np.testing.assert_allclose(user["isobaricInhPa"].u, 3.)
        assert user["isobaricInhPa"].u.attrs["GRIB_uvRelativeToGrid"] == 1
    finally:
        for ds in user.values():
            ds.close()
