"""Independent vector truth and strict declared-source wind contracts."""

from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
from pyproj import Geod, Proj

from frameit.processing.derived.wind import (
    add_speed_from_uv_dict,
    add_vrad_vtan_from_polar_dict,
    align_wind_pair,
    normalize_native_wind_units,
    normalize_winds,
    polar_wind_components,
    wind_names,
)
from frameit.processing.wind_reference import (
    declared_pair,
    geolocation_rotation,
    pair_definition,
    validate_pair_frame,
)


def settings(*pairs, **kwargs):
    return SimpleNamespace(atm_model="MNH", wind_pairs=list(pairs),
                           wind_reference_frame=None, **kwargs)


def definition(u="u", v="v", frame="grid", method="coordinate", **kwargs):
    return dict(group="level", u=u, v=v, reference_frame=frame,
                rotation=(dict(method=method, coordinate="angle", **kwargs)
                          if frame == "grid" else None))


def field():
    ds = xr.Dataset({"u": ("x", [36., 0.]), "v": ("x", [0., 36.])},
                    coords={"x": [0, 1], "angle": ("x", [90., 90.])})
    ds.angle.attrs["units"] = "degrees"
    for name in ("u", "v"):
        ds[name].attrs.update(units="km/h", wind_reference_frame="grid", GRIB_uvRelativeToGrid=1)
    ds.u.attrs["standard_name"] = "x_wind"
    ds.v.attrs["standard_name"] = "y_wind"
    return ds


def test_quarter_turn_truth_source_preservation_and_idempotence():
    ds = field()
    original = ds.copy(deep=True)
    conf = settings(definition())
    out = normalize_winds(ds, conf, "level")
    np.testing.assert_allclose(out.u, [0, -10], atol=1e-14)
    np.testing.assert_allclose(out.v, [10, 0], atol=1e-14)
    assert out.u.attrs["standard_name"] == "eastward_wind"
    assert out.v.attrs["standard_name"] == "northward_wind"
    assert out.u.attrs["source_standard_name"] == "x_wind"
    assert out.u.attrs["source_GRIB_uvRelativeToGrid"] == 1
    xr.testing.assert_identical(normalize_winds(out, conf, "level"), out)
    for name in ("u", "v"):
        del out[name].attrs["frameit_wind_prepared"]
    out.attrs.update(wind_reference_frame="earth", source_wind_reference_frame="grid")
    xr.testing.assert_identical(normalize_winds(out, conf, "level"), out)
    xr.testing.assert_identical(ds, original)


def test_mixed_pairs_and_native_export_have_independent_bases():
    ds = field().assign(ue=("x", [3., 4.]), vn=("x", [4., 3.]))
    for name, standard in (("ue", "eastward_wind"), ("vn", "northward_wind")):
        ds[name].attrs.update(units="m s-1", standard_name=standard)
    conf = settings(definition(), definition("ue", "vn", "earth"))
    native = normalize_native_wind_units(ds, conf, "level")
    np.testing.assert_allclose(native.u, [10, 0])
    assert native.u.attrs["wind_reference_frame"] == "grid"
    assert native.u.attrs["standard_name"] == "x_wind"
    out = normalize_winds(ds, conf, "level")
    np.testing.assert_allclose(out.u, [0, -10], atol=1e-14)
    xr.testing.assert_identical(out.ue, normalize_winds(out, conf, "level").ue)
    np.testing.assert_allclose(out.ue, ds.ue)
    with pytest.raises(ValueError, match="Ambiguous"):
        wind_names(conf, "level")
    conf.velocity_aliases = {"u_velocity": "ue", "v_velocity": "vn"}
    assert wind_names(conf, "level") == ("ue", "vn")


def test_declarations_are_required_and_methods_never_fall_back():
    ds = field()
    with pytest.raises(ValueError, match="declaration"):
        normalize_winds(ds, settings(), "level")
    conf = settings(definition())
    with pytest.raises(ValueError, match="both components"):
        normalize_winds(ds.drop_vars("v"), conf, "level")
    with pytest.raises(ValueError, match="named coordinate"):
        normalize_winds(ds.drop_vars("angle"), conf, "level")
    conf.wind_pairs[0]["rotation"] = None
    with pytest.raises(ValueError, match="explicit rotation method"):
        normalize_winds(ds, conf, "level")
    conf.wind_pairs[0]["rotation"] = {"method": "mesonh_projection"}
    with pytest.raises(ValueError, match="BETA"):
        normalize_winds(ds, conf, "level")
    conf.wind_pairs[0]["reference_frame"] = "auto"
    with pytest.raises(ValueError, match="earth or grid"):
        normalize_winds(ds, conf, "level")


@pytest.mark.parametrize("attrs", [
    {"standard_name": "eastward_wind"}, {"wind_reference_frame": "earth"},
    {"GRIB_uvRelativeToGrid": 0}, {"GRIB_uvRelativeToGrid": 2},
    {"standard_name": "y_wind"},
])
def test_metadata_cannot_override_declaration(attrs):
    ds = field()
    ds.u.attrs.update(attrs)
    with pytest.raises(ValueError):
        validate_pair_frame(ds, definition())
    with pytest.raises(ValueError):
        normalize_winds(ds, settings(definition()), "level")


def test_unique_pair_alias_resolution_and_unrequested_pair_no_dependencies():
    conf = settings(definition("first", "second"))
    assert wind_names(conf, "level") == ("first", "second")
    assert declared_pair(conf, "level")["u"] == "first"
    assert declared_pair(conf, "surface") is None
    xr.testing.assert_identical(normalize_winds(field(), conf, "level"), field())


def test_explicit_legacy_scalar_and_canonical_low_level_api():
    conf = SimpleNamespace(atm_model="MNH", wind_reference_frame="grid")
    ds = field().rename(angle="grid_rotation")
    out = normalize_winds(ds, conf, "level")
    assert out.u.attrs["wind_rotation_method"] == "legacy_grid_rotation_coordinate"
    assert pair_definition(SimpleNamespace(), "level", ("u", "v"))["reference_frame"] == "earth"
    radial, tangential = polar_wind_components(xr.DataArray(3.), xr.DataArray(4.), xr.DataArray(0.))
    assert radial == 4
    assert tangential == 3


@pytest.mark.parametrize("descending_x,descending_y", [
    (False, False), (True, False), (False, True), (True, True),
])
@pytest.mark.parametrize("latitude", [-40., 40.])
def test_geolocation_signed_axes_independent_projection_truth(descending_x, descending_y, latitude):
    # A conformal LCC grid: physical true east has grid components (cos(a),-sin(a)).
    proj = Proj(proj="lcc", lat_1=latitude, lat_2=latitude, lat_0=latitude,
                lon_0=10, ellps="WGS84")
    x = np.arange(5) * 100.
    y = np.arange(4) * 100.
    if descending_x:
        x = x[::-1]
    if descending_y:
        y = y[::-1]
    xx, yy = np.meshgrid(x, y)
    beta = np.deg2rad(30.)
    lon, lat = proj(xx*np.cos(beta) - yy*np.sin(beta),
                    xx*np.sin(beta) + yy*np.cos(beta), inverse=True)
    angle = beta - np.deg2rad(proj.get_factors(lon, lat).meridian_convergence)
    ds = xr.Dataset({"u": (("nj", "ni"), 7 * np.cos(angle)),
                     "v": (("nj", "ni"), -7 * np.sin(angle))},
                    coords={"ni": x, "nj": y,
                            "longitude": (("nj", "ni"), lon),
                            "latitude": (("nj", "ni"), lat)})
    for name in ("u", "v"):
        ds[name].attrs["units"] = "m s-1"
    ds.longitude.attrs["units"] = "degrees_east"
    ds.latitude.attrs["units"] = "degrees_north"
    conf = settings(definition(method="geolocation"))
    out = normalize_winds(ds, conf, "level")
    np.testing.assert_allclose(out.u, 7, atol=2e-9)
    # One-sided boundary directions approximate local tangent over a 100-m cell.
    np.testing.assert_allclose(out.v, 0, atol=5e-5)
    reflected = ds.isel(nj=slice(None, None, -1)).assign_coords(nj=y)
    with pytest.raises(ValueError, match="orientation"):
        geolocation_rotation(reflected, conf)


@pytest.mark.parametrize("rpk,beta", [(0., 30.), (.6, 15.), (-.6, -25.), (1., 10.), (-1., 10.)])
def test_mesonh_projection_sign_from_independent_projected_axis(rpk, beta):
    # Obtain local grid-x direction by perturbing projected coordinates, independently
    # of the implemented longitude formula (sphere matches MNH conformal convention).
    lat0 = 30. if rpk >= 0 else -30.
    if rpk == 0:
        proj = Proj(proj="merc", lon_0=10, R=6371229)
    elif abs(rpk) == 1:
        proj = Proj(proj="stere", lat_0=90*rpk, lon_0=10, R=6371229)
    else:
        lat0 = np.rad2deg(np.arcsin(rpk))
        proj = Proj(proj="lcc", lat_1=lat0, lat_2=lat0, lon_0=10, R=6371229)
    lon = np.array([7., 10., 13.])
    lat = np.full(3, lat0)
    x, y = proj(lon, lat)
    b = np.deg2rad(beta)
    lf, af = proj(x + .1*np.cos(b), y + .1*np.sin(b), inverse=True)
    az = Geod(a=6371229, b=6371229).inv(lon, lat, lf, af)[0]
    truth = np.deg2rad(90 - az)
    ds = xr.Dataset({"u": ("x", 8*np.cos(truth)), "v": ("x", -8*np.sin(truth)),
                     "BETA": beta, "RPK": rpk, "LON0": 10.},
                    coords={"longitude": ("x", lon)})
    ds.longitude.attrs["units"] = "degrees_east"
    for name in ("u", "v"):
        ds[name].attrs["units"] = "m s-1"
    out = normalize_winds(ds, settings(definition(method="mesonh_projection")), "level")
    np.testing.assert_allclose(out.u, 8, atol=1e-12)
    np.testing.assert_allclose(out.v, 0, atol=2e-7)
    assert out.u.attrs["rotation_RPK"] == rpk


def test_pair_alignment_rejects_labels_auxiliary_coordinates_and_unresolved_locations():
    u = xr.DataArray([1., 2.], dims="x", coords={"x": [0, 1], "longitude": ("x", [3., 4.])})
    with pytest.raises(ValueError, match="coordinate"):
        align_wind_pair(u, u.assign_coords(longitude=("x", [3., 5.])))
    with pytest.raises(ValueError, match="coordinate"):
        align_wind_pair(u, u.assign_coords(x=[1, 2]))
    with pytest.raises(ValueError, match="point location"):
        align_wind_pair(u.assign_attrs(grid=2), u.assign_attrs(grid=3))


def test_selected_method_checks_units_and_grid_geometry():
    ds = field()
    ds.angle.attrs.clear()
    with pytest.raises(ValueError, match="units"):
        normalize_winds(ds, settings(definition()), "level")
    x, y = np.meshgrid(np.arange(3) * .001, np.arange(3) * .001)
    ds = xr.Dataset(coords={"ni": [0, 1, 2], "nj": [0, 1, 2],
                            "longitude": (("nj", "ni"), x + y),
                            "latitude": (("nj", "ni"), y)})
    ds.longitude.attrs["units"] = "degrees_east"
    ds.latitude.attrs["units"] = "degrees_north"
    conf = settings(definition(method="geolocation"))
    with pytest.raises(ValueError, match="orthogonal"):
        geolocation_rotation(ds, conf)
    with pytest.raises(ValueError, match="monotone"):
        geolocation_rotation(ds.assign_coords(ni=[0, 2, 1]), conf)


def test_prepared_pair_requires_consistent_source_and_complete_preparation():
    conf = settings(definition())
    ds = normalize_winds(field(), conf, "level")
    ds.u.attrs["source_wind_reference_frame"] = "earth"
    with pytest.raises(ValueError, match="source frame"):
        normalize_winds(ds, conf, "level")
    ds = normalize_winds(field(), conf, "level")
    ds.v.attrs = field().v.attrs
    with pytest.raises(ValueError, match="one prepared"):
        normalize_winds(ds, conf, "level")


@pytest.mark.parametrize("component", ["u", "v"])
def test_selected_prepared_singleton_is_idempotent_and_has_no_pair_diagnostics(component):
    conf = settings(definition())
    prepared = normalize_winds(field(), conf, "level")
    singleton = prepared[[component]].drop_vars("angle")
    # Portable metadata is sufficient even when an intermediate reader drops
    # FrameIt's private preparation marker and the original rotation coordinate.
    del singleton[component].attrs["frameit_wind_prepared"]
    xr.testing.assert_identical(normalize_winds(singleton, conf, "level"), singleton)
    for operation in (add_speed_from_uv_dict, add_vrad_vtan_from_polar_dict):
        result = operation({"level": singleton}, conf)["level"]
        xr.testing.assert_identical(result, singleton)
        with pytest.raises(ValueError, match="both components"):
            operation({"level": field()[[component]]}, conf)
    singleton[component].attrs["source_wind_reference_frame"] = "earth"
    with pytest.raises(ValueError, match="source frame"):
        normalize_winds(singleton, conf, "level")


@pytest.mark.parametrize("attrs,match", [
    ({"wind_pair": "another,pair"}, "wind_pair"),
    ({"wind_rotation_method": "geolocation"}, "rotation method"),
    ({"wind_rotation_coordinate": "another_angle"}, "rotation coordinate"),
])
def test_prepared_singleton_validates_declaration_provenance(attrs, match):
    conf = settings(definition())
    selected = normalize_winds(field(), conf, "level")[["u"]]
    selected.u.attrs.update(attrs)
    with pytest.raises(ValueError, match=match):
        normalize_winds(selected, conf, "level")


def test_alignment_ignores_unrelated_scalar_auxiliaries_but_checks_geography():
    u = xr.DataArray([1., 2.], dims="x", coords={"x": [0, 1], "source_component": "u"})
    v = u.assign_coords(source_component="v", unused_scalar=42)
    align_wind_pair(u, v)
    with pytest.raises(ValueError, match="longitude"):
        align_wind_pair(u.assign_coords(longitude=10), v.assign_coords(longitude=11))
