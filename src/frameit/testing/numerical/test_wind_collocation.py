"""Native affine-field and sparse-level regressions for MNH preparation."""

from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from frameit.io.loader import DatasetResources
from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord
from frameit.processing.wind_collocation import (
    _collocate_w_to_zC,
    collocate_winds,
    interpolate_staggered,
    prepare_native_mnh,
)


def conf():
    return SimpleNamespace(
        atm_model="MNH", name_lon_dim="ni", name_lat_dim="nj", name_vertical_dim="level",
        velocity_aliases={"u_velocity": "UT", "v_velocity": "VT", "w_velocity": "WT"},
        wind_reference_frame="earth",
    )


def native(reverse=False):
    x, y = np.array([0., 2., 4.]), np.array([0., 2., 4.])
    xs, ys = np.array([-1., 1., 3., 5.]), np.array([-1., 1., 3., 5.])
    if reverse:
        x, y, xs, ys = x[::-1], y[::-1], xs[::-1], ys[::-1]
    levels, interfaces = [0.5, 2.5, 6.0], [0., 1., 4., 8.]
    ds = xr.Dataset(
        {"UT": (("time", "level", "nj_u", "ni_u"),
                np.broadcast_to(xs, (1, 3, 3, 4)).copy()),
         "VT": (("time", "level", "nj_v", "ni_v"),
                np.broadcast_to(ys[None, None, :, None], (1, 3, 4, 3)).copy()),
         "WT": (("time", "level_w", "nj", "ni"),
                np.broadcast_to(np.array(interfaces)[None, :, None, None], (1, 4, 3, 3)).copy())},
        coords={"time": [np.datetime64("2024-01-01")], "level": levels,
                "level_w": interfaces, "ni": x, "nj": y,
                "ni_u": xs, "nj_u": y, "ni_v": x, "nj_v": ys,
                "latitude": (("nj", "ni"), np.broadcast_to(y[:, None], (3, 3))),
                "longitude": (("nj", "ni"), np.broadcast_to(x[None, :], (3, 3)))},
    )
    for name in ("UT", "VT", "WT"):
        ds[name].attrs["units"] = "m s-1"
    return ds


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("component", ["UT", "VT"])
def test_single_component_affine_native_collocation(component, reverse):
    source = native(reverse)
    paired, _ = prepare_native_mnh(source, conf())
    companion = "VT" if component == "UT" else "UT"
    with pytest.raises(ValueError, match="both components"):
        prepare_native_mnh(source.drop_vars(companion), conf())
    # Dependency loading prepares both components before user selection. The
    # selected singleton must remain usable without deriving a vector magnitude.
    direct = collocate_winds({"level": paired.drop_vars(
        ["WT", "VT" if component == "UT" else "UT"]
    )}, conf=conf())
    xr.testing.assert_allclose(direct["level"][component], paired[component])
    assert "wind_speed" not in direct["level"]
    axis = "ni" if component == "UT" else "nj"
    expected = source[axis].broadcast_like(paired[component])
    np.testing.assert_allclose(paired[component], expected, atol=1e-12)
    assert paired[component].dims == ("time", "level", "nj", "ni")


def test_stretched_vertical_sparse_targets_and_unavailable_bracket():
    source = native()
    _, mass_w = prepare_native_mnh(source, conf())
    np.testing.assert_allclose(mass_w[:, :, 0, 0], [[0.5, 2.5, 6]])
    sparse = _collocate_w_to_zC(
        source.WT, zC_name="level", zC_coord=source.level.isel(level=[0, 2]), policy="strict"
    )
    np.testing.assert_allclose(sparse[:, :, 0, 0], [[0.5, 6]])
    unavailable = interpolate_staggered(
        source.WT, "level_w", xr.DataArray([2.5, 9.], dims="level", coords={"level": [2.5, 9.]})
    )
    assert np.isnan(unavailable.isel(level=1)).all()


@pytest.mark.parametrize("w_only", [False, True])
def test_loader_retains_native_brackets_before_selection(tmp_path, w_only):
    source = native()
    path = tmp_path / "native.nc"
    source.to_netcdf(path, engine="h5netcdf")
    requests = {"level_w": {"variables": ["WT"], "level_selection": "indices",
                            "level_indices": [0, 2]}}
    if not w_only:
        requests["level"] = {"variables": ["UT", "VT"], "level_selection": "indices",
                             "level_indices": [0, 2]}
    with DatasetResources() as resources:
        groups, _ = concat_nc2ds_by_vert_coord(
            [path], requests, {}, wind_conf=conf(), concat_dimension="time", resources=resources
        )
        # Requested Cartesian W remains on native interfaces; its hidden mass
        # counterpart retains correct brackets from the entire lazy source.
        np.testing.assert_allclose(groups["level_w"].WT[:, :, 0, 0], [[0, 4]])
        result = collocate_winds(groups, conf=conf())
        np.testing.assert_allclose(result["level"].WT[:, :, 0, 0], [[0.5, 6]])
        assert "level_w" not in result
        assert "_frameit_mass_w" not in result["level"]
        retained = collocate_winds(groups, conf=conf(), drop_level_w_group=False)
        np.testing.assert_allclose(retained["level"].WT[:, :, 0, 0], [[0.5, 6]])
        np.testing.assert_allclose(retained["level_w"].WT[:, :, 0, 0], [[0, 4]])
        if not w_only:
            np.testing.assert_allclose(result["level"].wind_speed[:, :, 1, 1], np.sqrt(8))
            # Consuming native-prepared arrays must not collocate a second time.
            xr.testing.assert_allclose(result["level"].UT, groups["level"].UT)


def test_missing_bracket_is_not_partial_extrapolation():
    source = native()
    source["UT"][..., 1] = np.nan
    result, _ = prepare_native_mnh(source, conf())
    assert np.isnan(result.UT.isel(ni=0)).all()
    with pytest.raises(ValueError, match="strictly monotone"):
        interpolate_staggered(source.UT.assign_coords(ni_u=[0, 0, 2, 3]), "ni_u", source.ni)


def test_lazy_native_collocation_matches_eager():
    source = native()
    lazy = source.chunk({"ni_u": 2, "nj_v": 2, "level": 1, "level_w": 2})
    eager_result, eager_w = prepare_native_mnh(source, conf())
    lazy_result, lazy_w = prepare_native_mnh(lazy, conf())
    assert hasattr(lazy_result.UT.data, "dask")
    assert hasattr(lazy_w.data, "dask")
    xr.testing.assert_allclose(lazy_result.UT.compute(), eager_result.UT)
    xr.testing.assert_allclose(lazy_result.VT.compute(), eager_result.VT)
    xr.testing.assert_allclose(lazy_w.compute(), eager_w)


def test_native_and_surface_winds_use_source_grid_frame():
    source = native()
    source.attrs["wind_reference_frame"] = "grid"
    source = source.assign_coords(grid_rotation=(("nj", "ni"), np.full((3, 3), np.pi / 2)))
    source.grid_rotation.attrs["units"] = "rad"
    source["UM10"] = xr.full_like(source.longitude, 3.)
    source["VM10"] = xr.full_like(source.longitude, 4.)
    source.UM10.attrs["units"] = source.VM10.attrs["units"] = "m/s"
    settings = conf()
    settings.wind_reference_frame = "grid"
    settings.tracking_var_aliases = {"u10m": "UM10", "v10m": "VM10"}
    result, _ = prepare_native_mnh(source, settings)
    np.testing.assert_allclose(result.UM10, -4, atol=1e-12)
    np.testing.assert_allclose(result.VM10, 3, atol=1e-12)
    np.testing.assert_allclose(result.UT[:, :, 1, 1], -2, atol=1e-12)
    np.testing.assert_allclose(result.VT[:, :, 1, 1], 2, atol=1e-12)


def test_runner_loads_speed_only_native_dependencies(tmp_path, monkeypatch):
    from frameit.core.runner import FrameitRunner

    path = tmp_path / "native.nc"
    native().to_netcdf(path, engine="h5netcdf")
    settings = conf()
    settings.file_type = "nc"
    settings.infer_grid_geometry = False
    settings.netcdf_engine = "h5netcdf"
    settings.netcdf_chunks = {}
    settings.duplicate_time_policy = "first"
    settings.name_time_dim = "time"
    settings.name_latitude = "latitude"
    settings.name_longitude = "longitude"
    settings.tracking_method = "fixed_box"
    settings.requested_variables_tracker = {"fixed_box": {}}
    settings.requested_variables_user = {
        "level": {"variables": ["wind_speed"], "level_selection": "indices",
                  "level_indices": [0, 2]}
    }
    settings.polar_variables = "all"
    runner = object.__new__(FrameitRunner)
    runner.conf, runner.resources, runner.input_files = settings, DatasetResources(), None
    runner.find_files = lambda: [path]
    monkeypatch.setattr("frameit.core.runner.build_tracker_from_config", lambda *args: None)
    # This fixture exercises loading/derivation, not nominal geographic grid
    # resolution (which has independent checks and real matrix fixtures).
    monkeypatch.setattr("frameit.core.runner.check_resolution", lambda *args: None)
    try:
        groups, _, _ = runner.load_dataset()
        np.testing.assert_allclose(groups["level"].wind_speed[:, :, 1, 1], np.sqrt(8))
        assert runner._internal_wind_names == {"level": ["UT", "VT"]}
        assert settings.requested_variables_user["level"]["variables"] == ["wind_speed"]
    finally:
        runner.close()
