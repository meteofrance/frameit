"""Real-backend labelled alignment, finite geometry and scientific metadata contracts."""

from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from frameit.io.loader import DatasetResources
from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf
from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord
from frameit.processing.extraction import center2box, extract_data, polar_support_settings
from frameit.processing.polar.polar_proj import polar_project


def polar_settings(**changes):
    values = dict(
        atm_model="AROME", velocity_aliases={"u_velocity": "u", "v_velocity": "v"},
        compute_polar_proj=True, tracking_method="fixed_box", name_longitude="longitude",
        name_latitude="latitude", x_boxsize_km=8, y_boxsize_km=8,
        radial_resolution=2000, polar_n_theta=16,
        polar_variables={"surface": {"variables": ["q"]}},
    )
    values.update(changes)
    return SimpleNamespace(**values)


def source_scene(nx=7, ny=5, times=(0, 1), longitude=0):
    x, y = np.arange(nx) - nx // 2, np.arange(ny) - ny // 2
    lon, lat = np.meshgrid(longitude + x * .04, -20 + y * .04)
    signal = np.arange(len(times))[:, None, None] + 2 * (lon - longitude) + 3 * (lat + 20) + 100
    return xr.Dataset(
        {"q": (("time", "y_box", "x_box"), signal)},
        coords={"time": list(times), "y_box": y, "x_box": x,
                "longitude": (("y_box", "x_box"), lon),
                "latitude": (("y_box", "x_box"), lat)},
    )


@pytest.mark.parametrize("mode", ["fixed_box", "prescribed_track"])
def test_groups_align_time_labels_before_sampling(mode):
    reference = source_scene()
    reference["q"] = xr.ones_like(reference.q)
    other = source_scene(times=(1, 0))
    other["q"] = xr.DataArray(np.broadcast_to(np.array([101., 100.])[:, None, None],
                                              other.q.shape), dims=other.q.dims,
                             coords={"time": [1, 0]})
    config = polar_settings(tracking_method=mode,
                            polar_variables={"heightAboveGround": {"variables": ["q"]}})
    result, _ = polar_project({"surface": reference, "heightAboveGround": other}, conf=config)
    sample = result["heightAboveGround"].q
    np.testing.assert_allclose(sample.isel(time=0), 100, atol=1e-12)
    np.testing.assert_allclose(sample.isel(time=1), 101, atol=1e-12)
    np.testing.assert_array_equal(sample.time, [0, 1])


@pytest.mark.parametrize("times", [(0,), (0, 0), (0, 2), (0, 1, 2), ("0", "1")])
def test_missing_duplicate_extra_or_incompatible_group_times_fail(times):
    with pytest.raises(ValueError, match="time"):
        polar_project({"surface": source_scene(), "other": source_scene(times=times)},
                      conf=polar_settings())


def test_track_times_align_and_extra_positions_are_reported():
    track = xr.Dataset({"lon": ("time", [.01, .02, .03]),
                        "lat": ("time", [-20.01, -20.02, -20.03])}, coords={"time": [1, 0, 2]})
    result, report = polar_project(
        {"surface": source_scene()},
        conf=polar_settings(tracking_method="prescribed_track"), track=track,
    )
    np.testing.assert_allclose(result["surface"].center_lon, [.02, .01])
    assert report["unused_track_times"] == 1
    with pytest.raises(ValueError, match="time"):
        polar_project({"surface": source_scene()}, conf=polar_settings(),
                      track=track.isel(time=[0, 0]))


@pytest.mark.parametrize("nx,ny", [(5, 5), (7, 5)])
def test_named_geographic_and_field_dimension_orders_are_equivalent(nx, ny):
    source = source_scene(nx, ny)
    original, _ = polar_project({"surface": source}, conf=polar_settings())
    transposed = source.copy(deep=False)
    for name in ("longitude", "latitude", "q"):
        dims = transposed[name].dims
        transposed[name] = transposed[name].transpose(*dims[:-2], "x_box", "y_box")
    result, _ = polar_project({"surface": transposed}, conf=polar_settings())
    xr.testing.assert_allclose(result["surface"].q, original["surface"].q)


def test_rectilinear_axes_and_dateline_wrapping_preserve_connectivity():
    source = source_scene(longitude=179.98)
    expected, _ = polar_project({"surface": source}, conf=polar_settings())
    wrapped = source.assign_coords(longitude=(source.longitude + 180) % 360 - 180)
    result, _ = polar_project({"surface": wrapped}, conf=polar_settings())
    xr.testing.assert_allclose(result["surface"].q, expected["surface"].q)
    one_dimensional = source.drop_vars(["longitude", "latitude"]).assign_coords(
        longitude=("x_box", source.longitude.isel(y_box=0).values),
        latitude=("y_box", source.latitude.isel(x_box=0).values),
    )
    result, _ = polar_project({"surface": one_dimensional}, conf=polar_settings())
    xr.testing.assert_allclose(result["surface"].q, expected["surface"].q)


@pytest.mark.parametrize("issue", ["hole", "latitude", "degenerate", "folded"])
def test_invalid_source_geometry_is_rejected_before_backend(issue):
    source = source_scene().copy(deep=True)
    if issue == "hole":
        source.longitude[1, 1] = np.nan
    elif issue == "latitude":
        source.latitude[1, 1] = 91
    elif issue == "degenerate":
        source.longitude[:, 1] = source.longitude[:, 0]
    else:
        source.longitude[:, 2] = source.longitude[:, 4]
    with pytest.raises(ValueError):
        polar_project({"surface": source}, conf=polar_settings())


def test_fixed_origin_does_not_reuse_weights_for_a_moving_source_grid():
    source = source_scene()
    longitude = np.stack([source.longitude.values, source.longitude.values + .01])
    source = source.assign_coords(longitude=(("time", "y_box", "x_box"), longitude))
    source["q"] = ("time", "y_box", "x_box"), longitude
    config = polar_settings()
    result, _ = polar_project({"surface": source}, conf=config)
    centre = result["surface"].q.isel(rr=0, theta=0)
    # Spherical bilinear weights need not reproduce longitude itself exactly;
    # this sub-millimetre angular tolerance still detects a stale 0.01-degree map.
    np.testing.assert_allclose(centre, 0, atol=1e-8)


def test_vertical_auxiliaries_bounds_and_units_survive_export(tmp_path):
    source = source_scene()
    source["q"] = source.q.expand_dims(level=[1000., 2000.])
    source = source.assign_coords(
        altitude=("level", [1200., 2500.]), bnds=["lower", "upper"],
        geometric_height=source.q * 0 + xr.DataArray([1200., 2500.], dims="level",
                                                   coords={"level": [1000., 2000.]}),
    )
    source["level_bounds"] = ("level", "bnds"), [[900., 1100.], [1900., 2100.]]
    source.level.attrs.update(units="hPa", bounds="level_bounds")
    source.altitude.attrs.update(units="m", standard_name="altitude")
    source.geometric_height.attrs.update(units="m", standard_name="height")
    source.q.attrs.update(units="K", standard_name="air_temperature", grid_mapping="crs",
                          coordinates="old_x old_y", cell_measures="area: native_area")
    source = source.assign_coords(crs=0)
    source.crs.attrs["grid_mapping_name"] = "lambert_conformal_conic"
    source.q.encoding.update(dtype="int16", scale_factor=.001, _FillValue=-999)
    result, _ = polar_project({"surface": source}, conf=polar_settings(polar_ellipsoid="sphere"))
    ds = result["surface"]
    assert ds.q.attrs["units"] == "K"
    assert ds.level.attrs == source.level.attrs
    np.testing.assert_array_equal(ds.level_bounds, source.level_bounds)
    np.testing.assert_array_equal(ds.altitude, source.altitude)
    assert {"rr", "theta", "level"} <= set(ds.geometric_height.dims)
    np.testing.assert_allclose(ds.geometric_height.isel(time=0, rr=0, theta=0), [1200, 2500])
    assert "crs" not in ds and "grid_mapping" not in ds.q.attrs
    assert "coordinates" not in ds.q.attrs and "cell_measures" not in ds.q.attrs
    assert ds.q.encoding == {}
    assert ds.attrs["ellps"] == "sphere"
    assert "spherical" in ds.attrs["interpolation_geometry"]
    path = tmp_path / "sampled.nc"
    write_dataset_netcdf(
        ds, path, product_type="polar",
        metadata=ExportMetadata("synthetic", "scalar", "contracts", "test", "analytic"),
    )
    with xr.open_dataset(path) as saved:
        assert saved.q.attrs["units"] == "K"
        assert saved.level.attrs["bounds"] == "level_bounds"
        assert "flag_values" in saved.q_interpolation_status.attrs
        assert saved.rr.attrs["units"] == "km"
        assert saved.theta.attrs["units"] == "rad"


def test_reordered_vertical_wind_coordinates_align_or_fail():
    source = source_scene()
    source["u"] = source.q.expand_dims(level=[1000., 2000.])
    source["v"] = source.u.sel(level=[2000., 1000.]) * 0
    config = polar_settings(polar_variables={"surface": {"variables": ["u", "v"]}},
                            tracking_var_aliases={"u10m": "u", "v10m": "v"})
    result, _ = polar_project({"surface": source}, conf=config)
    assert result["surface"].u.dims == result["surface"].v.dims
    bad = source.drop_vars("v")
    bad["v"] = source.u.rename(level="different_vertical_grid")
    with pytest.raises(ValueError, match="identical dimensions"):
        polar_project({"surface": bad}, conf=config)


def test_vertical_bounds_survive_loading_selection_and_extraction(tmp_path):
    source = source_scene().rename(y_box="nj", x_box="ni")
    source["q"] = source.q.expand_dims(level=[1000., 2000.])
    source["level_bounds"] = ("level", "bnds"), [[900., 1100.], [1900., 2100.]]
    source.level.attrs.update(units="hPa", bounds="level_bounds")
    path = tmp_path / "model.nc"
    source.to_netcdf(path, engine="h5netcdf")
    config = polar_settings(atm_model="MNH", name_lon_dim="ni", name_lat_dim="nj",
                            name_vertical_dim="level", resolution=4000,
                            velocity_aliases={"u_velocity": "UT", "v_velocity": "VT"},
                            polar_variables={"level": {"variables": ["q"]}})
    request = {"level": {"variables": ["q"], "level_selection": "indices", "level_indices": [1]}}
    with DatasetResources() as resources:
        groups, tracking = concat_nc2ds_by_vert_coord(
            [path], request, {"fixed_box": {}}, method="fixed_box", concat_dimension="time",
            wind_conf=config, resources=resources,
        )
        assert "level_bounds" in groups["level"]
        track = xr.Dataset({"cx": ("time", [3, 3]), "cy": ("time", [2, 2]),
                            "lon": ("time", [0., 0.]), "lat": ("time", [-20., -20.])},
                           coords={"time": [0, 1]})
        _, extracted = extract_data(config, groups, tracking["fixed_box"], track)
        assert "level_bounds" in extracted["level"]
        result, _ = polar_project(extracted, conf=config, track=track)
        np.testing.assert_array_equal(result["level"].level_bounds, [[1900., 2100.]])


def test_incompatible_calendars_are_rejected():
    import cftime

    first = source_scene().assign_coords(
        time=[cftime.DatetimeNoLeap(2024, 1, 1), cftime.DatetimeNoLeap(2024, 1, 2)]
    )
    second = source_scene().assign_coords(
        time=[cftime.Datetime360Day(2024, 1, 1), cftime.Datetime360Day(2024, 1, 2)]
    )
    with pytest.raises(ValueError, match="calendar"):
        polar_project({"surface": first, "other": second}, conf=polar_settings())


def test_native_halo_is_not_lost_at_half_integer_box_widths():
    settings = polar_settings(x_boxsize_km=9, y_boxsize_km=9, resolution=3000,
                              polar_source_halo_points=1)
    track = xr.Dataset({"cx": ("time", [10]), "cy": ("time", [10])}, coords={"time": [0]})
    box = center2box(track, 9, 9, 3000, 21, 21, inplace=False)
    expanded = polar_support_settings(settings, box)
    support = center2box(track, expanded.x_boxsize_km, expanded.y_boxsize_km,
                         3000, 21, 21, inplace=False)
    assert support.attrs["box_nx_points"] == box.attrs["box_nx_points"] + 2
    assert support.attrs["box_ny_points"] == box.attrs["box_ny_points"] + 2
    assert settings.x_boxsize_km == 9
