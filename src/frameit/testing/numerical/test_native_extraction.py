"""Independent labelled source-sample checks for bounded native extraction."""

from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from frameit.processing.dims_utils import normalize_dims_for_extraction
from frameit.processing.extraction import extract_data
from frameit.processing.polar.metadata import (
    coordinate_dependency_names,
    point_attributes,
    preserve_coordinate_dependencies,
)
from frameit.tracking.tracker_core import make_tracking_dataset
from frameit.tracking.Utrack_Tracker import _common_input_grid


def settings(**changes):
    args = dict(name_lon_dim="ni", name_lat_dim="nj", name_latitude="latitude",
                name_longitude="longitude", name_time="time", resolution=1000,
                x_boxsize_km=2, y_boxsize_km=2, tracking_method="fixed_box",
                velocity_aliases={"u_velocity": "UT", "v_velocity": "VT"},
                atm_model="MNH")
    args.update(changes)
    return SimpleNamespace(**args)


def scene(storage="n+1", descending=False, permuted=False):
    # Five mass cells with independently evaluated, nonconstant native fields.
    mass = np.arange(5.) * 1000 + 10000
    faces = np.arange(6.) * 1000 + 9500
    if storage == "left":
        faces = faces[:-1]
    elif storage == "right":
        faces = faces[1:]
    if descending:
        mass, faces = mass[::-1], faces[::-1]
    coords = {"time": [0, 1], "level": [1, 2], "ni": mass, "nj": mass,
              "ni_u": faces, "nj_u": mass.copy(), "ni_v": mass.copy(), "nj_v": faces}
    ds = xr.Dataset(coords=coords)
    for suffix, yd, xd in (("", "nj", "ni"), ("_u", "nj_u", "ni_u"),
                           ("_v", "nj_v", "ni_v")):
        xx, yy = np.meshgrid(ds[xd], ds[yd])
        ds = ds.assign_coords({f"latitude{suffix}": ((yd, xd), 10 + yy / 1e5),
                               f"longitude{suffix}": ((yd, xd), 30 + xx / 1e5)})
    ds["UT"] = (("time", "level", "nj_u", "ni_u"),
                np.array([[[x + 2*y + 7*t + 11*z for x in faces] for y in mass]
                          for t in (0, 1) for z in (0, 1)]).reshape(2, 2, 5, len(faces)))
    ds["VT"] = (("time", "level", "nj_v", "ni_v"),
                np.array([[[3*x - y + 7*t + 11*z for x in mass] for y in faces]
                          for t in (0, 1) for z in (0, 1)]).reshape(2, 2, len(faces), 5))
    ds["q"] = ("nj", "ni"), np.add.outer(mass, mass)
    ds["independent"] = ("time", "level"), [[1, 2], [3, 4]]
    ds["level_bounds"] = ("level", "bnds"), [[.5, 1.5], [1.5, 2.5]]
    ds.level.attrs["bounds"] = "level_bounds"
    ds["latitude_u_bounds"] = ("nj_u", "ni_u", "bnds"), np.zeros((5, len(faces), 2))
    ds.latitude_u.attrs["bounds"] = "latitude_u_bounds"
    ds.ni_u.attrs.update(c_grid_dynamic_range="1:5", c_grid_axis_shift=-.5)
    ds.UT.attrs.update(units="m s-1", wind_reference_frame="grid", custom="keep")
    if permuted:
        for name in ("UT", "VT", "q", "latitude", "latitude_u", "longitude_v", "level_bounds"):
            ds[name] = ds[name].transpose(*reversed(ds[name].dims))
    return ds


def run(ds, center=2, native=True, **changes):
    track = xr.Dataset({"cx": ("time", [center, center]), "cy": ("time", [center, center])},
                       coords={"time": [0, 1]})
    return extract_data(settings(**changes), {"level": ds}, ds, track,
                        native_winds=native)[1]["level"]


@pytest.mark.parametrize("storage", ["n+1", "left", "right"])
@pytest.mark.parametrize("descending", [False, True])
@pytest.mark.parametrize("permuted", [False, True])
def test_native_samples_are_cell_bounding_and_keep_source_basis(storage, descending, permuted):
    ds = scene(storage, descending, permuted)
    result = run(ds)
    assert result.sizes["x_u_box"] == result.sizes["y_v_box"] == 4
    assert result.sizes["y_u_box"] == result.sizes["x_v_box"] == 3
    for t in (0, 1):
        for z in (0, 1):
            # Geographic coordinates independently encode the source locations.
            ux = (result.longitude_u.isel(time=t) - 30) * 1e5
            uy = (result.latitude_u.isel(time=t) - 10) * 1e5
            vx = (result.longitude_v.isel(time=t) - 30) * 1e5
            vy = (result.latitude_v.isel(time=t) - 10) * 1e5
            np.testing.assert_allclose(result.UT.isel(time=t, level=z),
                                       (ux + 2*uy + 7*t + 11*z).transpose("y_u_box", "x_u_box"),
                                       atol=1e-8)
            np.testing.assert_allclose(result.VT.isel(time=t, level=z),
                                       (3*vx - vy + 7*t + 11*z).transpose("y_v_box", "x_v_box"),
                                       atol=1e-8)
    # The three mass cells at indices 1..3 have four bounding half-index faces.
    np.testing.assert_array_equal(result.x_u_box, [-1.5, -.5, .5, 1.5])
    step = float(ds.ni[1] - ds.ni[0])
    expected = float(ds.ni[2]) + step * np.array([-1.5, -.5, .5, 1.5])
    np.testing.assert_allclose((result.longitude_u.isel(time=0, y_u_box=1)-30)*1e5,
                               expected, atol=1e-8)
    assert result.UT.attrs["wind_reference_frame"] == "grid"
    assert result.UT.attrs["custom"] == "keep"
    assert result.UT.attrs["grid_position"] == "x_face"
    assert result.VT.attrs["grid_position"] == "y_face"
    assert "c_grid_dynamic_range" not in result.ni_u.attrs
    assert "source_c_grid_dynamic_range" in result.ni_u.attrs
    xr.testing.assert_equal(result.independent, ds.independent)
    np.testing.assert_array_equal(result.level_bounds, [[.5, 1.5], [1.5, 2.5]])
    assert result.latitude_u_bounds.sizes["x_u_box"] == 4
    assert "latitude_u_bounds" in result
    assert not any(name in result for name in ("speed", "wind_speed", "horizontal_wind_speed"))


@pytest.mark.parametrize("storage", ["n+1", "left", "right"])
@pytest.mark.parametrize("center", [0, 4])
@pytest.mark.parametrize("descending", [False, True])
def test_boundary_faces_are_nan_without_extrapolation(storage, center, descending):
    source = scene(storage, descending=descending)
    result = run(source, center=center)
    mass_cells = np.arange(center - 1, center + 2)
    step = float(source.ni[1] - source.ni[0])
    targets = float(source.ni[0]) + step * np.arange(center - 1.5, center + 2)
    available = np.isin(targets, source.ni_u)
    values = result.UT.isel(time=0, level=0, y_u_box=1)
    np.testing.assert_array_equal(np.isfinite(values), available)
    np.testing.assert_allclose(values.values[available],
                               targets[available] + 2*float(source.nj[center]))
    np.testing.assert_array_equal(np.isfinite(result.q.isel(time=0, y_box=1)),
                                  (mass_cells >= 0) & (mass_cells < 5))
    np.testing.assert_array_equal(np.isfinite(result.longitude_u.isel(time=0, y_u_box=1)),
                                  available)


def test_native_mode_never_calls_speed(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("native output must not derive speed")
    monkeypatch.setattr("frameit.processing.extraction.add_speed_from_uv_dict", forbidden)
    run(scene())


def test_unprepared_mass_extraction_fails_before_losing_grid_coordinates():
    with pytest.raises(ValueError, match="unprepared native staggering"):
        run(scene(), native=False)
    with pytest.raises(ValueError, match="unprepared native staggering"):
        run(scene(), native=False, x_boxsize_km=0)


def test_named_mass_axes_crop_permuted_fields_and_leave_bounds_independent():
    source = scene().drop_vars(["UT", "VT"])
    source = source.drop_dims(["ni_u", "nj_u", "ni_v", "nj_v"])
    source["q"] = source.q.transpose("ni", "nj")
    result = run(source, native=False)
    np.testing.assert_allclose(result.q.isel(time=0),
                               source.q.isel(ni=slice(1, 4), nj=slice(1, 4)).T)
    xr.testing.assert_equal(result.independent, source.independent)
    np.testing.assert_array_equal(result.level_bounds, source.level_bounds)
    normalized = normalize_dims_for_extraction({"level": source}, settings())["level"]
    assert normalized.q.dims == ("nj", "ni")
    assert normalized.level_bounds.dims == ("level", "bnds")


def test_native_non_face_geometry_fails_actionably():
    source = scene().assign_coords(ni_u=scene().ni_u + 100)
    with pytest.raises(ValueError, match="neither cell-aligned nor half-cell staggered"):
        run(source)


def test_independently_reversed_native_axes_match_labelled_source_samples():
    source = scene()
    reversed_source = source.isel(ni_u=slice(None, None, -1), nj_v=slice(None, None, -1))
    original, reversed_result = run(source), run(reversed_source)
    xr.testing.assert_allclose(original.UT, reversed_result.UT)
    xr.testing.assert_allclose(original.VT, reversed_result.VT)


def test_tracker_rejects_horizontal_mismatch_but_allows_time_vertical_alignment():
    left = xr.Dataset({"a": (("time", "nj", "ni"), np.ones((2, 2, 3)))},
                      coords={"time": [0, 1], "ni": [0, 1, 2], "nj": [0, 1]})
    right = left.rename(a="b").assign_coords(ni=[.5, 1.5, 2.5])
    with pytest.raises(ValueError, match="horizontal coordinate.*must match exactly"):
        make_tracking_dataset({"test": {"a": left, "b": right}}, "test")
    right = left.rename(a="b").isel(time=[1]).expand_dims(level=[850])
    merged = make_tracking_dataset({"test": {"a": left, "b": right}}, "test")
    assert merged.sizes["time"] == 2
    lat = xr.DataArray(np.zeros((2, 3)), dims=("nj", "ni"))
    left = left.assign_coords(latitude=lat)
    right = right.assign_coords(latitude=lat.expand_dims(time=[1], level=[850]))
    merged = make_tracking_dataset({"test": {"a": left, "b": right}}, "test")
    assert "latitude" in merged
    bad = right.assign_coords(latitude=right.latitude + .1)
    with pytest.raises(ValueError, match="horizontal coordinate.*must match exactly"):
        make_tracking_dataset({"test": {"a": left, "b": bad}}, "test")


def test_utrack_checks_grid_locations_before_unlabelled_arrays():
    u = xr.DataArray(np.zeros((2, 3, 4)), dims=("time", "nj", "ni"),
                     coords={"time": [0, 1], "nj": [0, 1, 2], "ni": [0, 1, 2, 3]})
    lat, lon = u.nj, u.ni
    fields = _common_input_grid(u.transpose("ni", "time", "nj"), u, u, lat, lon)
    assert all(a.dims == ("time", "nj", "ni") for a in fields)
    with pytest.raises(ValueError, match="common grid locations"):
        _common_input_grid(u, u.rename(ni="ni_u"), u, lat, lon)
    with pytest.raises(ValueError, match="match exactly"):
        _common_input_grid(u, u.assign_coords(ni=u.ni + .5), u, lat, lon)


def test_metadata_dependencies_preserved_without_restoring_horizontal_bounds():
    source = scene()
    source["crs"] = xr.DataArray(0, attrs={"grid_mapping_name": "lambert_conformal_conic"})
    source["quality"] = ("level",), [1, 2]
    source["cell_area"] = ("nj", "ni"), np.ones((5, 5))
    source["latitude_bounds"] = ("nj", "ni", "bnds"), np.ones((5, 5, 2))
    source.latitude.attrs["bounds"] = "latitude_bounds"
    source.q.attrs.update(grid_mapping="crs", ancillary_variables="quality",
                          cell_measures="area: cell_area")
    deps = coordinate_dependency_names(source, ["q"])
    assert {"crs", "quality", "cell_area", "latitude_bounds", "level_bounds"} <= deps
    selected = preserve_coordinate_dependencies(source, source[["q"]])
    assert {"crs", "quality", "cell_area"} <= set(selected.variables)
    sampled = xr.Dataset({"q": (("level", "y_box", "x_box"), np.ones((2, 3, 3)))},
                         coords={"level": source.level,
                                 "latitude": (("y_box", "x_box"), np.ones((3, 3)))})
    sampled.latitude.attrs["bounds"] = "latitude_bounds"
    sampled = preserve_coordinate_dependencies(source, sampled)
    assert "latitude_bounds" not in sampled
    assert "bounds" not in sampled.latitude.attrs
    assert "nj" not in sampled.dims and "ni" not in sampled.dims
    assert "level_bounds" in sampled
    attrs = point_attributes({"c_grid_dynamic_range": "1:5", "c_grid_axis_shift": -.5,
                              "grid_position": "x_face", "grid_mapping": "crs"})
    assert "c_grid_dynamic_range" not in attrs
    assert attrs["source_c_grid_dynamic_range"] == "1:5"
    assert "grid_mapping" not in attrs
