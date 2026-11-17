"""Header-only wind contracts and explicit catalog/centroid conventions."""

from copy import deepcopy
from types import SimpleNamespace

import dask.array as da
import numpy as np
import pytest
import xarray as xr
from dask import delayed

from frameit.core.configuration import to_runtime
from frameit.core.preflight import (
    collect_preflight,
    inspect_wind_pairs,
    selected_level_records,
    wind_dependencies,
)
from frameit.core.settings_class import SimulationConfig
from frameit.testing.catalog import load_cases
from frameit.testing.numerical.test_pressure_centroid_mnh import native_vortex
from frameit.tracking.pressure_centroid_inputs import prepare_mnh_inputs
from frameit.tracking.tracker_core import resolve_tracker_support


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
                         "VT": ("level", [0.]), "BETA": 0., "RPK": 0., "LON0": 54.2})
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


@pytest.mark.parametrize("frame", ["grid", "earth"])
def test_missing_mnh_projection_headers_preflight_never_reads_winds(frame):
    @delayed
    def forbidden():
        raise AssertionError("Preflight evaluated a velocity field")

    rotation = {"method": "mesonh_projection", "BETA": 0, "RPK": 0, "LON0": 54.2}
    conf = settings(frame, rotation if frame == "grid" else None)
    source = xr.Dataset(coords={
        "level": [1000.],
        "longitude": ("level", [54.2], {"units": "degrees_east"}),
    })
    for name, standard in (("UT", "x_wind"), ("VT", "y_wind")):
        source[name] = ("level", da.from_delayed(forbidden(), (1,), float),
                        {"standard_name": standard})
    _, pairs = wind_dependencies(conf, {"level": {"variables": ["UT"]}})
    if frame == "earth":
        with pytest.warns(UserWarning, match="grid.*missing"):
            records = inspect_wind_pairs([source], conf, pairs, "fixture.nc")
        assert "missing" in records[0]["wind_reference_frame_override"]
    else:
        records = inspect_wind_pairs([source], conf, pairs, "fixture.nc")
        assert records[0]["rotation_method"] == "mesonh_projection"
        assert records[0]["rotation_parameters"]["rotation_LON0_degrees"] == 54.2


@pytest.mark.parametrize("frame", ["grid", "earth"])
@pytest.mark.parametrize("representation", ["native", "earth_centered"])
def test_missing_mnh_projection_headers_export_and_provenance(tmp_path, frame, representation):
    from frameit.core.execution import ExecutionOptions, execute_simulation

    source, _ = native_vortex(n=9)
    source = source.drop_vars([n for n in ("BETA", "RPK", "LON0") if n in source])
    for name in ("BETA", "RPK", "LON0"):
        source.attrs.pop(name, None)
    for name, standard in (("UT_ZM", "x_wind"), ("VT_ZM", "y_wind")):
        source[name].attrs.update(standard_name=standard, wind_reference_frame="grid")
    source.to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    pair = {"u": "UT_ZM", "v": "VT_ZM", "basis": frame}
    if frame == "grid":
        pair["rotation"] = {"method": "mesonh_projection", "BETA": 0, "RPK": 0, "LON0": 54.2}
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "mesonh", "files": str(tmp_path / "native.nc"), "wind_pairs": [pair],
            "variables": {"3d": ["UT_ZM", "VT_ZM"]},
            **({"transforms": [{"fields": ["UT_ZM", "VT_ZM"],
                                "sampling": "mass", "basis": "earth"}]}
               if representation == "earth_centered" else {}),
        }},
        "region": {"center": {"latitude": -20., "longitude": 60.},
                   "width_km": {"x": 2000, "y": 2000}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "output")},
    })
    result = execute_simulation(conf, ExecutionOptions(synchronous_export=True))
    assert result.ok
    path = next(p["path"] for p in result.products
                if p["role"] == "model_grid" and p["source"] == "atmosphere")
    with xr.open_dataset(path, engine="h5netcdf") as reopened:
        for name in ("UT_ZM", "VT_ZM"):
            # C7 uses zero-based crop positions: old offsets -4:4 are positions 2:10.
            np.testing.assert_allclose(
                reopened[name].isel(x=slice(2, 11), y=slice(2, 11)), source[name]
            )
            assert reopened[name].isel(x=0).isnull().all()
            if frame == "earth":
                assert "missing" in reopened[name].attrs["wind_reference_frame_override"]
                assert reopened[name].attrs["source_standard_name"] == source[name].attrs["standard_name"]
            elif representation == "earth_centered":
                assert reopened[name].attrs["rotation_LON0_degrees"] == 54.2
    if frame == "earth":
        from pathlib import Path

        import yaml

        assert "metadata says grid-aligned" in Path(result.log_path).read_text()
        provenance = yaml.safe_load((tmp_path / "output" / "run-provenance.yaml").read_text())
        assert "wind_reference_frame_override" in str(provenance)


@pytest.mark.parametrize("method", ["pressure_centroid", "multifield_vortex"])
def test_partial_projection_yaml_retains_source_parameters_for_native_trackers(tmp_path, method):
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

    source, _ = native_vortex(n=9)
    source = source.assign(RPK=0., LON0=54.2)
    for name, standard in (("UT_ZM", "x_wind"), ("VT_ZM", "y_wind")):
        source[name].attrs["standard_name"] = standard
    path = tmp_path / "native.nc"
    source.to_netcdf(path, engine="h5netcdf")
    tracking = {"method": method}
    if method == "multifield_vortex":
        tracking.update(seed={"latitude": -20., "longitude": 60.,
                              "motion_u_m_s": 0., "motion_v_m_s": 0.},
                        mnh_gravity_m_s2=9.80665)
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "mesonh", "files": [str(path)], "wind_pairs": [
                {"u": "UT_ZM", "v": "VT_ZM", "basis": "grid",
                 "rotation": {"method": "mesonh_projection", "BETA": 90}},
                {"u": "UM10", "v": "VM10", "basis": "earth"},
            ], "variables": {"2d": ["MSLP"]},
        }},
        "region": {"tracker": tracking},
        "products": {"model_grid": True, "track": True},
        "output": {"directory": str(tmp_path / "out")},
    })
    report = collect_preflight(conf)
    assert not report.errors, report.errors
    resolve_tracker_support(conf, report.facts["sources"]["atmosphere"])
    with DatasetResources() as resources:
        _, trackers = concat_nc2ds_by_vert_coord(
            [path], {"surface": {"variables": ["MSLP"]}}, {method: {}}, method,
            wind_conf=conf, resources=resources,
        )
        prepared = trackers[method]["native"]
        if method == "pressure_centroid":
            prepared = prepare_mnh_inputs(prepared, conf)
        np.testing.assert_allclose(prepared.u, -source.VT_ZM, atol=1e-12)
        np.testing.assert_allclose(prepared.v, source.UT_ZM, atol=1e-12)


def projection_shards(tmp_path, *, frame="earth", repeated=True, source_frame="earth"):
    source, _ = native_vortex(n=9)
    source = source.assign(BETA=0., RPK=0., LON0=54.2)
    for name, standard in (("UT_ZM", "eastward_wind"), ("VT_ZM", "northward_wind")):
        source[name].attrs["standard_name"] = (
            standard if source_frame == "earth" else "x_wind" if name == "UT_ZM" else "y_wind"
        )
    paths = []
    for index, name in enumerate(("UT_ZM", "VT_ZM")):
        names = [name] + (["BETA", "RPK", "LON0"] if repeated or index == 0 else [])
        path = tmp_path / f"part{index}.nc"
        source[names].to_netcdf(path, engine="h5netcdf")
        paths.append(path)
    pair = {"u": "UT_ZM", "v": "VT_ZM", "basis": frame}
    if frame == "grid":
        pair["rotation"] = {"method": "mesonh_projection", "BETA": 0}
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "mesonh", "files": list(map(str, paths)), "wind_pairs": [pair],
            "variables": {"3d": ["UT_ZM", "VT_ZM"]},
            "transforms": [{"fields": ["UT_ZM", "VT_ZM"], "sampling": "mass", "basis": "earth"}],
        }},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "out")},
    })
    return source, paths, conf


@pytest.mark.parametrize("frame", ["earth", "grid"])
def test_projection_headers_are_checked_metadata_in_variable_shards(tmp_path, frame):
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

    source, paths, conf = projection_shards(tmp_path, frame=frame, source_frame=frame)
    report = collect_preflight(conf)
    assert not report.errors, report.errors
    with DatasetResources() as resources:
        groups, _ = concat_nc2ds_by_vert_coord(
            paths, {"level": {"variables": ["UT_ZM", "VT_ZM"]}}, {}, wind_conf=conf,
            file_layout="variables", resources=resources,
        )
        np.testing.assert_allclose(groups["level"].UT_ZM, source.UT_ZM)


def test_variable_shard_preflight_keeps_complete_projection_conflicts_fatal(tmp_path):
    _, _, conf = projection_shards(tmp_path, repeated=False, source_frame="grid")
    report = collect_preflight(conf)
    assert report.errors
    assert "Conflicting" in str(report.errors)


def test_scalar_shards_do_not_validate_unused_wind_projection(tmp_path):
    from frameit.io.loader import DatasetResources
    from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

    source, _ = native_vortex(n=9)
    paths = []
    for index, name in enumerate(("MSLP", "ALT")):
        path = tmp_path / f"scalar{index}.nc"
        source[[name]].assign_coords(time=source.time).assign(BETA=float(index)).to_netcdf(
            path, engine="h5netcdf"
        )
        paths.append(path)
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "mesonh", "files": list(map(str, paths)), "variables": {"2d": ["MSLP"]},
        }},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "out")},
    })
    report = collect_preflight(conf)
    assert not report.errors, report.errors
    with DatasetResources() as resources:
        groups, _ = concat_nc2ds_by_vert_coord(
            paths, {"surface": {"variables": ["MSLP"]}}, {}, wind_conf=conf,
            file_layout="variables", resources=resources,
        )
        np.testing.assert_allclose(groups["surface"].MSLP, source.MSLP)


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
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "arome", "files": str(tmp_path / "vertical.nc"),
            "variables": {"3d": [name]},
        }},
        "region": {"center": {"latitude": -20.01, "longitude": 60.01}},
        "products": {"model_grid": True},
        "output": {"directory": str(tmp_path / "output")},
    })
    assert conf.velocity_aliases["w_velocity"] == "wz"
    report = collect_preflight(conf)
    assert not report.errors, report.errors
    selected = report.facts["sources"]["atmosphere"]
    binding = selected["field_binding"]
    assert binding["operation_plans"] == []
    field = binding["products"]["model_grid"][name]["field_id"]
    record = selected["fields"][field]["attributes"]
    assert record["units"] == units
    if name == "w":
        source[name].attrs["units"] = "m s-1"
        source.to_netcdf(path, engine="h5netcdf")
        report = collect_preflight(conf)
        assert report.errors
        assert "pressure velocity" in str(report.errors)


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


def test_catalog_preserves_source_and_output_conventions(tmp_path):
    for case in load_cases():
        raw = deepcopy(case["config"])
        # This checks declarations only; source-dependent levels bind at inventory.
        # Normally bound from the frozen fixture's centre_grid/track at resolution.
        if "center" in raw["region"]:
            raw["region"]["center"] = {"latitude": -10.3, "longitude": 55.}
        if case["tracker"] == "prescribed_track":
            raw["region"].pop("center", None)
            raw["region"]["track"] = {"file": "fixture-track.nc"}
        if case["tracker"] == "utrack":
            raw["region"]["tracker"]["weights_file"] = "fixture-weights.pt"
        runtime = to_runtime(raw, base_dir=tmp_path)
        source = raw["sources"]["atmosphere"]
        expected = deepcopy(source["wind_pairs"])
        assert expected[-1]["basis"] == "earth"
        assert runtime["yaml_config"]["sources"]["atmosphere"]["wind_pairs"] == expected
        assert all(transform["basis"] == "earth" and transform["sampling"] == (
            "native" if source["model"] == "arome" else "mass")
            for transform in source.get("transforms", []))
        assert runtime["cartesian_vertical_velocity"] == "interfaces"
        for field, options in runtime["source_requests"]["atmosphere"]["polar_options"].items():
            if field == "level_w.WT":
                assert options["sampling"] == "mass"


def test_explicit_centroid_preflight_and_export(tmp_path):
    from frameit.core.execution import ExecutionOptions, execute_simulation

    source, _ = native_vortex()
    source.to_netcdf(tmp_path / "native.nc", engine="h5netcdf")
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3,
        "sources": {"atmosphere": {
            "model": "mesonh", "files": str(tmp_path / "native.nc"), "wind_pairs": [
                {"u": "UT_ZM", "v": "VT_ZM", "basis": "earth"},
                {"u": "UM10", "v": "VM10", "basis": "earth"},
            ], "variables": {"2d": ["MSLP"]},
        }},
        "region": {"tracker": {"method": "pressure_centroid"},
                   "width_km": {"x": 100, "y": 100}},
        "products": {"model_grid": True, "track": True},
        "output": {"directory": str(tmp_path / "output")},
    })
    report = collect_preflight(conf)
    assert not report.errors, report.errors
    resolve_tracker_support(conf, report.facts["sources"]["atmosphere"])
    assert len(conf.wind_pairs) == 2
    assert next(p for p in conf.wind_pairs if p["u"] == "UT_ZM")["reference_frame"] == "earth"
    result = execute_simulation(conf, ExecutionOptions(synchronous_export=True))
    assert result.ok
    path = next(p["path"] for p in result.products if p["role"] == "track")
    with xr.open_dataset(path, engine="h5netcdf") as reopened:
        assert reopened.sizes["time"] == 2
        np.testing.assert_allclose(reopened.longitude, 60., atol=.01)
        assert reopened.attrs["pressure_centroid_native_wind_reference"] == "earth"


def grib_blocks(stamp, *, scalar=True, units="m s-1", flag=1, angle=90.):
    """Synthetic cfgrib blocks with explicitly declared grid-basis vectors."""
    levels = 850. if scalar else [850., 700.]
    dims = ("latitude", "longitude") if scalar else (
        "isobaric", "latitude", "longitude")
    shape = (2, 2) if scalar else (2, 2, 2)
    scale = 3.6 if units == "km h-1" else 1.
    source = xr.Dataset(coords={
        "time": np.datetime64("2024-01-01", "ns"),
        "valid_time": np.datetime64(stamp, "ns"),
        "isobaric": xr.DataArray(levels, dims=() if scalar else "isobaric",
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
            "group": "isobaric", "u": "u", "v": "v", "reference_frame": "grid",
            "rotation": {"method": "coordinate", "coordinate": "rotation"},
        }],
    )


def test_grib_per_file_units_rotation_and_native_branch(tmp_path, monkeypatch):
    from frameit.io import grib_utils
    from frameit.io.loader import DatasetResources

    cfgrib = pytest.importorskip("cfgrib")
    paths = [tmp_path / "first.grib", tmp_path / "second.grib"]
    for path in paths:
        path.touch()
    blocks = {
        str(paths[0]): grib_blocks("2024-01-01", angle=90.),
        str(paths[1]): grib_blocks("2024-01-01T01:00", scalar=False,
                                  units="km h-1", angle=0.),
    }
    monkeypatch.setattr(cfgrib, "open_datasets", lambda path, **kw: blocks[path])
    request = {"isobaric": {
        "variables": ["u", "v"], "level_selection": "values", "level_values": [850.],
    }}
    settings = grib_settings()
    settings.cartesian_horizontal_winds = "mass_earth"
    with DatasetResources() as resources:
        user, tracker = grib_utils.concat_grib2ds_by_vert_coord(
            paths, request, {"pressure_centroid": request}, method="pressure_centroid",
            index_dir=tmp_path / "indexes", wind_conf=settings, resources=resources,
        )
        prepared = user["isobaric"]
        assert prepared.sizes["time"] == 2
        assert prepared.sizes["isobaric"] == 1
        np.testing.assert_allclose(prepared.u.isel(time=0), -4., atol=1e-14)
        np.testing.assert_allclose(prepared.v.isel(time=0), 3., atol=1e-14)
        np.testing.assert_allclose(prepared.u.isel(time=1), 3., atol=1e-14)
        np.testing.assert_allclose(prepared.v.isel(time=1), 4., atol=1e-14)
        xr.testing.assert_identical(tracker["pressure_centroid"]["isobaric"], prepared)
        for index, (unit, u, v, angle) in enumerate((
                ("m s-1", 3., 4., 90.), ("km h-1", 10.8, 14.4, 0.))):
            native = {}
            grib_utils.concat_grib2ds_by_vert_coord(
                [paths[index]], request, {}, index_dir=tmp_path / "indexes",
                wind_conf=settings, native_output_groups=native, resources=resources)
            raw = native["isobaric"]
            np.testing.assert_allclose(raw.u, u)
            np.testing.assert_allclose(raw.v, v)
            assert set(raw.data_vars) == {"u", "v"}
            assert raw.u.attrs["units"] == unit
            assert prepared.u.attrs["units"] == "m s-1"
            assert raw.u.attrs["GRIB_uvRelativeToGrid"] == 1
            assert prepared.u.attrs["GRIB_uvRelativeToGrid"] == 0
            assert "crs" in raw.coords and "rotation" in raw.coords
            np.testing.assert_allclose(raw.rotation, angle)


def test_grib_later_frame_conflict_is_checked_before_concatenation(tmp_path, monkeypatch):
    from frameit.io import grib_utils

    cfgrib = pytest.importorskip("cfgrib")
    paths = [tmp_path / "first.grib", tmp_path / "second.grib"]
    for path in paths:
        path.touch()
    blocks = {
        str(paths[0]): grib_blocks("2024-01-01"),
        str(paths[1]): grib_blocks("2024-01-01T01:00", flag=0),
    }
    monkeypatch.setattr(cfgrib, "open_datasets", lambda path, **kw: blocks[path])
    settings = grib_settings()
    settings.cartesian_horizontal_winds = "mass_earth"
    with pytest.raises(ValueError, match="Conflicting wind reference metadata"):
        grib_utils.concat_grib2ds_by_vert_coord(
            paths, {"isobaric": {"variables": ["u", "v"], "level_selection": "all"}},
            {}, index_dir=tmp_path / "indexes", wind_conf=settings,
        )


@pytest.mark.parametrize("selection", [
    {"level_selection": "physical"}, {"level_selection": "all"},
    {"level_selection": "indices", "level_indices": [0]},
    {"level_selection": "values", "level_values": [850.]},
])
def test_grib_all_scalar_level_headers_retain_selected_timestamps(tmp_path, monkeypatch, selection):
    from frameit.io import grib_utils

    cfgrib = pytest.importorskip("cfgrib")
    paths = [tmp_path / "first.grib", tmp_path / "second.grib"]
    for path in paths:
        path.touch()
    blocks = {str(path): grib_blocks(stamp) for path, stamp in zip(
        paths, ["2024-01-01", "2024-01-01T01:00"], strict=True)}
    monkeypatch.setattr(cfgrib, "open_datasets", lambda path, **kw: blocks[path])
    user, _ = grib_utils.concat_grib2ds_by_vert_coord(
        paths, {"isobaric": {"variables": ["u", "v"], **selection}}, {},
        index_dir=tmp_path / "indexes",
    )
    try:
        assert user["isobaric"].sizes["time"] == 2
        assert user["isobaric"].isobaric.values.tolist() == [850.]
        # Omitting wind_conf retains the historical raw-vector API.
        np.testing.assert_allclose(user["isobaric"].u, 3.)
        assert user["isobaric"].u.attrs["GRIB_uvRelativeToGrid"] == 1
    finally:
        for ds in user.values():
            ds.close()
