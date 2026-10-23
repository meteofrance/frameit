"""Independent transport, spectral and strict-support oracles plus the CI study."""

import json
from importlib import resources

import numpy as np
import pytest

from frameit.testing.analytic_vortices import AnalyticVortex, analytic_source
from frameit.testing.polar_wind_comparison import (
    _fixtures,
    independent_truth,
    read_ci_winds,
    run_comparison,
)
from frameit.testing.wind_point_methods import (
    METHODS,
    profile_peak,
    sample_methods,
    structural_metrics,
    target_grid,
    transport_angles,
)


def _basis(lon, lat):
    longitude, latitude = np.deg2rad([lon, lat])
    normal = np.array([np.cos(latitude)*np.cos(longitude),
                       np.cos(latitude)*np.sin(longitude), np.sin(latitude)])
    east = np.array([-np.sin(longitude), np.cos(longitude), 0.])
    north = np.cross(normal, east)
    return normal, east, north


@pytest.mark.parametrize("start,end", [((0., 0.), (10., 0.)), ((20., 60.), (23., 61.)),
                                      ((179.8, -20.), (-179.7, -19.8))])
def test_transport_against_independent_spherical_rodrigues_rotation(start, end):
    normal0, east0, north0 = _basis(*start)
    normal1, east1, north1 = _basis(*end)
    axis = np.cross(normal0, normal1)
    sine = np.linalg.norm(axis)
    cosine = np.dot(normal0, normal1)
    axis /= sine
    vector = 7*east0 + 11*north0
    # Rigid rotation in the great-circle plane is independent of the azimuth
    # difference formula and parallel-transports tangent vectors on a sphere.
    rotated = vector*cosine + np.cross(axis, vector)*sine + axis*np.dot(axis, vector)*(1-cosine)
    delta = transport_angles(*start, *end, ellps="sphere")
    actual = [7*np.cos(delta)+11*np.sin(delta), 11*np.cos(delta)-7*np.sin(delta)]
    np.testing.assert_allclose(actual, [np.dot(rotated, east1), np.dot(rotated, north1)],
                               atol=1e-12)
    np.testing.assert_allclose(np.hypot(*actual), np.hypot(7, 11), atol=1e-12)


def test_coincident_transport_has_no_arbitrary_direction():
    assert transport_angles(60., -20., 60., -20.) == 0


def test_methods_preserve_named_heights_joint_masks_origin_and_vector_norm():
    pytest.importorskip("xesmf")
    source = analytic_source(AnalyticVortex(), 2000., extent_m=20000., alignment=(.17, -.23))
    source = source.isel(time=0, heightAboveGround=0, drop=True).expand_dims(height=[100, 750])
    source = source.copy(deep=True)
    source.u.values[1] *= 2
    source.v.values[1] *= 2
    target = target_grid((60., -20.), rmax_m=10000., radial_step_m=2000., n_theta=16)
    result, diagnostics = sample_methods(source, target)
    assert list(result.wind_method.values) == list(METHODS)
    assert result.u.dims == ("wind_method", "height", "rr", "theta")
    np.testing.assert_allclose(result.u.isel(height=1), 2*result.u.isel(height=0))
    np.testing.assert_allclose(result.v.isel(height=1), 2*result.v.isel(height=0))
    np.testing.assert_allclose(np.hypot(result.vrad.isel(rr=slice(1, None)),
                                       result.vtan.isel(rr=slice(1, None))),
                               result.wind_speed.isel(rr=slice(1, None)), atol=1e-12)
    assert np.isnan(result.vrad.sel(rr=0)).all() and np.isfinite(result.wind_speed.sel(rr=0)).all()
    assert any(item["negative_weights"] > 0 for item in diagnostics if "patch" in item["method"])
    source.v.values[:, :, 10] = np.nan
    masked, _ = sample_methods(source, target)
    assert int(masked.vector_valid.sum()) < int(result.vector_valid.sum())
    np.testing.assert_array_equal(np.isfinite(masked.u), masked.vector_valid.astype(bool))
    np.testing.assert_array_equal(np.isfinite(masked.v), masked.vector_valid.astype(bool))
    for method in METHODS:
        assert profile_peak(masked.vtan.sel(wind_method=method).isel(height=0).values,
                             masked.rr.values)["rmw_km"] is None
    source.u.attrs["wind_reference_frame"] = "grid"
    with pytest.raises(ValueError, match="Earth-relative"):
        sample_methods(source, target)


def test_losing_a_required_target_invalidates_scores_and_full_search_rmw():
    spec = _fixtures()[0]
    target = target_grid((60., -20.), rmax_m=10000., radial_step_m=2000., n_theta=16)
    reference = independent_truth(spec, target, (60., -20.))
    actual = reference.copy(deep=True)
    actual.vtan.values[1, 0] = np.nan
    score = structural_metrics(actual, reference)
    assert score["fields"]["vtan"]["missing_required_points"] == 1
    assert score["fields"]["vtan"]["rms"] is None
    assert score["actual_peak"]["rmw_km"] is None
    assert all(item["complex_rms_difference_ms"] is None
               for item in score["spectra"] if item["field"] == "vtan")


def test_complete_ring_harmonic_phase_and_normalization_have_known_answer():
    import xarray as xr

    angles = np.arange(32)*2*np.pi/32

    def field(phase):
        radial = np.broadcast_to(np.cos(2*(angles-phase)), (3, 32)).copy()
        tangential = 10 + 3*np.broadcast_to(np.cos(2*(angles-phase)), (3, 32))
        radial[0], tangential[0] = np.nan, np.nan
        return xr.Dataset({"u": (("rr", "theta"), radial*np.sin(angles)+tangential*np.cos(angles)),
            "v": (("rr", "theta"), radial*np.cos(angles)-tangential*np.sin(angles)),
            "vrad": (("rr", "theta"), radial), "vtan": (("rr", "theta"), tangential),
            "wind_speed": (("rr", "theta"), np.hypot(radial, tangential))},
            coords={"rr": [0., 1., 2.], "theta": angles})

    score = structural_metrics(field(.3), field(.1))
    mode = next(row for row in score["spectra"] if row["field"] == "vtan" and row["mode"] == 2)
    assert mode["complete_rings"] == 2 and mode["strong_phase_eligible_rings"] == 2
    np.testing.assert_allclose(mode["complex_rms_difference_ms"], 3*np.sin(.2), atol=1e-12)
    np.testing.assert_allclose(mode["peak_direction_max_difference_deg"], np.rad2deg(.2),
                               atol=1e-12)
    incomplete = field(.3)
    incomplete.vtan.values[1, 0] = np.nan
    incomplete_score = structural_metrics(incomplete, field(.1))
    missing_mode = next(row for row in incomplete_score["spectra"]
                        if row["field"] == "vtan" and row["mode"] == 2)
    assert missing_mode["strong_phase_required_rings"] == 2
    assert missing_mode["strong_phase_eligible_rings"] == 1
    assert missing_mode["lost_resolved_phase_rings"] == 1


def test_full_analytical_and_native_comparison_exports_with_plain_readers(tmp_path):
    pytest.importorskip("xesmf")
    pytest.importorskip("eccodes")
    from netCDF4 import Dataset

    root = resources.files("frameit.testing").joinpath("ci_dataset")
    if not root.joinpath("manifest.json").is_file():
        pytest.skip("Bundled CI fixture is not installed")
    record = read_ci_winds(root / "AROME/BATSIRAI/arome_BATSIRAI_20220201+0000P.grib",
                           "2022-02-01T00:00:00")
    assert record["source"].u.shape == (2, 81, 81)
    assert all(item["uvRelativeToGrid"] == 0 for item in record["metadata"])
    with pytest.raises(ValueError, match="valid time"):
        read_ci_winds(root / "AROME/BATSIRAI/arome_BATSIRAI_20220201+0000P.grib",
                       "2022-02-01T06:00:00")
    output = tmp_path / "study"
    report = run_comparison(output, ci=True)
    assert report["passed"] and report["status"] == "PASS"
    assert report["analytical"]["fixtures"] == 6 and report["ci"]["cases"] == 4
    detailed = json.loads((output / "analytical/analytical.json").read_text())
    assert all(row["ok"] for row in detailed["checks"])
    assert len(detailed["centre_sensitivity"]) == 14
    assert len(detailed["angular_sampling"]) == 2
    assert max(row["truth_radial_rms_ms"] for row in detailed["centre_sensitivity"]) > 3
    native = json.loads((output / "ci/ci.json").read_text())
    assert native["source_content_unchanged"] and native["production_bilinear_parity_checked"]
    with Dataset(output / "ci/batsirai-wind-fixed.nc") as saved:
        assert list(saved["wind_method"][:]) == list(METHODS)
        assert saved.wind_reference_frame == "earth" and saved.maturity == "experimental"
        assert saved["u"].units == "m s-1" and "time_bounds" not in saved.variables
        assert len(saved.dimensions["time"]) == 5 and len(saved.dimensions["height"]) == 2
        assert np.ma.getmaskarray(saved["vrad"][:, :, :, 0, :]).all()
        assert np.isfinite(saved["wind_speed"][:, :, :, 0, :]).all()
        assert "vtan_fourier_real" in saved.variables and "vtan_fourier_imag" in saved.variables
        assert not any(name.endswith("support_fraction") for name in saved.variables)
    with Dataset(output / "ci/batsirai-wind-masked.nc") as saved:
        geometry = saved["geometry_mapped"][:][:, :, None, :, :]
        assert np.any(saved["vector_valid"][:] < geometry)
        assert np.ma.getmaskarray(saved["vtan_azimuthal_mean"][:]).any()
    with pytest.raises(ValueError, match="fresh or empty"):
        run_comparison(output)


def test_failed_experiment_retains_failed_parent_status(tmp_path, monkeypatch):
    import frameit.testing.polar_wind_comparison as experiment

    def fail(_):
        raise ValueError("deliberate candidate-backend failure")

    monkeypatch.setattr(experiment, "run_analytical", fail)
    with pytest.raises(ValueError, match="candidate-backend failure"):
        run_comparison(tmp_path / "failed")
    report = json.loads((tmp_path / "failed/comparison.json").read_text())
    assert not report["passed"] and report["status"] == "FAILED"
    assert report["analytical"]["status"] == "FAILED"
    assert report["analytical"]["report"] == "analytical/analytical.json"
