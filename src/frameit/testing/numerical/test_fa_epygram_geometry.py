"""C2 library adapter versus independent angular/Snyder geometry and native IDs."""

from __future__ import annotations

import copy
import json
import subprocess

import numpy as np
import pytest

from frameit.core.preflight import preflight
from frameit.core.settings_class import SimulationConfig
from frameit.io.fa_backend import inspect_fa, request_fa
from frameit.io.fa_geometry import fa_geometry, geometry_signature
from frameit.io.fa_utils import concat_fa2ds_by_vert_coord
from frameit.testing.numerical.test_fa_cubes import EPYTHON, NATIVE
from frameit.testing.numerical.test_fa_geometry import spherical_lambert
from frameit.testing.numerical.test_fa_pipeline import single_fa_document
from frameit.tracking.geographic import locate_track

OPTIONS = {"subdomain": "CI", "earth_radius_m": 6371229., "max_points": 117}
BACKEND = {"backend": "epygram", "python_executable": EPYTHON}


def test_epygram_labelled_grid_requires_qualified_library_facts():
    for operation in (fa_geometry, geometry_signature):
        with pytest.raises(ValueError, match="Missing qualified EPyGrAM geometry"):
            operation({}, {**OPTIONS, "backend": "epygram"})


def write_grid(directory, **options):
    path = directory / "grid.fa"
    written = subprocess.run([EPYTHON, "-m", "frameit.testing.fa_fixture"], input=json.dumps([{
        "path": str(path), "nx": 13, "ny": 9, "profile": "surfex_history", **options,
    }]), capture_output=True, text=True, timeout=30)
    assert written.returncode == 0, written.stdout + written.stderr
    path.chmod(0o444)
    return path


def inspect_grid(path, options):
    return inspect_fa(path, "surfex_history", ["SFX.T2M"], **BACKEND,
                      earth_radius_m=options["earth_radius_m"], geometry_options=options)


@NATIVE
@pytest.mark.parametrize("latitude", [-30., 30.])
@pytest.mark.parametrize("subdomain", ["CI", "C"])
def test_library_zones_cf_origin_and_snapping_against_snyder(tmp_path, latitude, subdomain):
    # Nonzero CI offsets, asymmetric CIE, nonzero I and anchor != projection origin.
    centre = (51., latitude + .5)
    path = write_grid(tmp_path, projection_latitude=latitude, projection_center=centre,
                      ci_bounds=[2, 12, 1, 8], i_widths=[1, 1])
    before = path.read_bytes()
    options = {**OPTIONS, "subdomain": subdomain}
    info = inspect_grid(path, options)
    facts = info["geometry"]["epygram"]
    assert facts["zones"] == {"CI": [2, 12, 1, 8], "C": [3, 11, 2, 7], "CIE": [0, 13, 0, 9]}
    assert facts["earth_model"] == {"radius_m": 6371229.,
                                      "origin": "explicit input.fa.earth_radius_m"}
    assert info["field_descriptors"]["SFX.T2M"]["mask"]["undefined"] == "not_read"
    ds = fa_geometry(info["geometry"], options)
    # Independent spherical forward equations for the off-origin anchor.
    phi0, lam0 = np.deg2rad([latitude, 50.])
    lam, phi = np.deg2rad(centre)
    n = np.sin(phi0)
    f = np.cos(phi0) * np.tan(np.pi/4 + phi0/2)**n / n
    rho0 = 6371229. * f / np.tan(np.pi/4 + phi0/2)**n
    rho = 6371229. * f / np.tan(np.pi/4 + phi/2)**n
    ax, ay = rho * np.sin(n*(lam-lam0)), rho0 - rho * np.cos(n*(lam-lam0))
    np.testing.assert_allclose(ds.x, ax + (ds.source_i - 6.5)*1000., rtol=0, atol=1.e-7)
    np.testing.assert_allclose(ds.y, ay + (ds.source_j - 4)*1000., rtol=0, atol=1.e-7)
    lon, lat = spherical_lambert(*np.meshgrid(ds.x, ds.y), 6371229., latitude)
    np.testing.assert_allclose(ds.longitude, lon, rtol=0, atol=2.e-11)
    np.testing.assert_allclose(ds.latitude, lat, rtol=0, atol=2.e-11)
    # Preserve the existing source CRS/CF origin, not the library's CI-centred axes.
    legacy = fa_geometry({k: v for k, v in info["geometry"].items() if k != "epygram"}, options)
    np.testing.assert_allclose(ds.x, legacy.x, rtol=0, atol=1.e-7)
    np.testing.assert_allclose(ds.y, legacy.y, rtol=0, atol=1.e-7)
    assert ds.crs.attrs == legacy.crs.attrs
    import xarray as xr

    track = xr.Dataset({"lon": ("time", [float(ds.longitude[2, 2])]),
                        "lat": ("time", [float(ds.latitude[2, 2])])}, coords={"time": [0]})
    located = locate_track(track, ds, require_inside=True)
    assert (int(located.cx[0]), int(located.cy[0])) == (2, 2)
    np.testing.assert_allclose(located.grid_snap_distance_m, 0., rtol=0, atol=1.e-7)
    result = request_fa({"operation": "read", "path": str(path), "profile": "surfex_history",
                         "fields": ["SFX.T2M"], **BACKEND, "earth_radius_m": 6371229.,
                         "max_points": 117, "zone": ds.attrs["fa_zone_indices"],
                         "key": [[None, None, -2], [None, None, -3]]})
    j, i = np.indices((9, 13))
    x0, x1, y0, y1 = facts["zones"][subdomain]
    np.testing.assert_array_equal(result["values"], (280. + 10*j + i)[y0:y1, x0:x1][::-2, ::-3])
    assert path.read_bytes() == before


@NATIVE
@pytest.mark.parametrize("direction", [1, -1])
def test_regular_library_axes_are_angular_and_keep_orientation(tmp_path, direction, monkeypatch):
    path = write_grid(tmp_path, angular_steps_degrees=(.01064, direction*.01))
    options = {**OPTIONS, "earth_radius_m": None}
    info = inspect_grid(path, options)
    # The labelled library path must work without calling the manual header path.
    def forbidden(*args, **kwargs):
        raise AssertionError("manual FA geometry reconstruction used")

    monkeypatch.setattr("frameit.io.fa_geometry._regional_header", forbidden)
    ds = fa_geometry(info["geometry"], options)
    np.testing.assert_allclose(ds.longitude, 60. + (np.arange(13)-6)*.01064, rtol=0, atol=1.e-10)
    np.testing.assert_allclose(ds.latitude, -20. + (np.arange(9)-4)*direction*.01,
                               rtol=0, atol=1.e-10)
    assert ds.crs.attrs == {"grid_mapping_name": "latitude_longitude"}
    assert info["geometry"]["epygram"]["earth_model"]["radius_m"] is None
    assert "no library geoid adopted" in ds.attrs["fa_earth_model_origin"]
    signature = geometry_signature(info["geometry"], options)
    changed = copy.deepcopy(info["geometry"])
    changed["KNIVER"] += 1
    assert geometry_signature(changed, options) == signature


@NATIVE
def test_geometry_earth_model_corners_and_full_native_budget_fail_closed(tmp_path):
    path = write_grid(tmp_path, projection_latitude=-30.)
    with pytest.raises(ValueError, match="explicit input.fa.earth_radius_m"):
        inspect_grid(path, {**OPTIONS, "earth_radius_m": None})
    with pytest.raises(ValueError, match="contradicts encoded CI corners"):
        inspect_grid(path, {**OPTIONS, "earth_radius_m": 5000000.})
    with pytest.raises(ValueError, match="input.fa.max_points"):
        inspect_grid(path, {**OPTIONS, "max_points": 116})


@NATIVE
def test_same_shape_different_library_grids_cannot_share_a_source_sequence(tmp_path):
    directories = [tmp_path / str(i) for i in range(2)]
    for directory in directories:
        directory.mkdir()
    paths = [write_grid(directory, hours=i, projection_latitude=-30.,
                        projection_center=(50. + .01*i, -30.))
             for i, directory in enumerate(directories)]
    infos = [inspect_grid(path, OPTIONS) for path in paths]
    assert geometry_signature(infos[0]["geometry"], OPTIONS) != geometry_signature(
        infos[1]["geometry"], OPTIONS)
    raw = single_fa_document(tmp_path, paths)
    raw["input"]["fa"].update(**BACKEND, earth_radius_m=6371229.)
    raw["tracking"]["fixed_box"]["center"] = {"latitude": -30., "longitude": 50.}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with pytest.raises(ValueError, match="incompatible horizontal geometry"):
        concat_fa2ds_by_vert_coord(paths, conf.requests_user(), {}, wind_conf=conf)
    with pytest.raises(ValueError, match="[Gg]eometr|[Gg]rid"):
        preflight(conf)
    assert not conf.output_dir.exists()
