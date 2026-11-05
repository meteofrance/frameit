"""Scientific gates and independent derivative/origin/serialization oracles."""

import json
import subprocess
import sys

import numpy as np
import pytest

from frameit.testing.analytic_vortices import AnalyticVortex, displaced_centre
from frameit.testing.polar_qualification import (
    error_metrics,
    project_fixture,
    refinement_case,
    refinement_gates,
    serialization_and_diagnostics,
)


def test_gaussian_vorticity_regular_limit_and_derived_profile():
    vortex = AnalyticVortex(kind="gaussian_vorticity")
    centre = vortex.evaluate(np.array([vortex.longitude]), np.array([vortex.latitude]))
    assert centre["u"][0] == 0 and centre["v"][0] == 0
    radii = np.array([.01, 1000., 45000., 90000.])
    from pyproj import Geod

    longitude, latitude, _ = Geod(ellps="WGS84").fwd(
        np.full(radii.shape, vortex.longitude), np.full(radii.shape, vortex.latitude),
        np.full(radii.shape, 90.), radii,
    )
    sampled = vortex.evaluate(longitude, latitude)
    exact = vortex.gaussian_vorticity_s * vortex.gaussian_width_m**2 / (2 * radii) * (
        -np.expm1(-(radii / vortex.gaussian_width_m)**2)
    )
    np.testing.assert_allclose(sampled["v"], exact, atol=1e-9, rtol=1e-8)
    np.testing.assert_allclose(sampled["u"], 0, atol=1e-9)
    np.testing.assert_allclose(exact[0] / radii[0], vortex.gaussian_vorticity_s / 2, rtol=1e-10)


def test_regularized_streamfunction_analytical_derivative():
    vortex = AnalyticVortex(kind="streamfunction")
    radii = np.array([0., 2000., 7000., 11000., 19000., 40000., 60000.])
    envelope, derivative = vortex.streamfunction_envelope(radii)
    delta = .01
    above, _ = vortex.streamfunction_envelope(radii + delta)
    below, _ = vortex.streamfunction_envelope(radii - delta)
    np.testing.assert_allclose(derivative, (above - below) / (2 * delta), atol=1e-8, rtol=1e-7)
    assert np.all(envelope[:2] == 0) and np.all(derivative[:2] == 0)
    assert envelope[-2] == vortex.streamfunction_amplitude_m2s


def test_required_set_cannot_improve_error_by_losing_difficult_points():
    truth = np.zeros(3)
    complete = error_metrics(np.array([1., 2., 10.]), truth, np.ones(3, dtype=bool))
    missing = error_metrics(np.array([1., 2., np.nan]), truth, np.ones(3, dtype=bool))
    assert complete["rms"] > 5
    assert missing["missing_required_points"] == 1 and missing["rms"] is None


@pytest.mark.parametrize("kind,grid_kind", [("geodesic", "rectilinear"),
                                          ("streamfunction", "curvilinear")])
def test_integrated_source_refinement_against_independent_truth(kind, grid_kind):
    pytest.importorskip("xesmf")
    vortex = AnalyticVortex(kind=kind)
    case = refinement_case(vortex, grid_kind=grid_kind, spacings=(4000., 2000., 1000.),
                           minimum_radius_m=20000 if kind == "streamfunction" else 0)
    checks = refinement_gates(case, order_fields=["smooth_scalar", "vtan"],
                              rms_limits={"vrad": .05, "vtan": .05})
    assert all(check["ok"] for check in checks), [check for check in checks if not check["ok"]]


def test_displaced_tangential_vortex_has_physical_radial_wind():
    pytest.importorskip("xesmf")
    vortex = AnalyticVortex()
    centre = displaced_centre(vortex, 10000., 90.)
    result, truth, _, _ = project_fixture(vortex, 1000., analysis_centre=centre)
    selected = result.rr.values >= 20.
    actual = result.vrad.isel(time=0, heightAboveGround=0).values[selected]
    expected = truth["vrad"][0, selected]
    assert np.max(np.abs(expected)) > 5.
    np.testing.assert_allclose(actual, expected, atol=.08, rtol=0)


def test_netcdf_reload_diagnostics_keep_scientific_contract(tmp_path):
    pytest.importorskip("xesmf")
    report = serialization_and_diagnostics(AnalyticVortex(longitude=179.6), tmp_path)
    assert report["mean_fft_checked"]


def test_analytical_cli_writes_numerical_evidence_without_plotting_dependencies(tmp_path):
    pytest.importorskip("xesmf")
    output = tmp_path / "example"
    result = subprocess.run([sys.executable, "-c", """
import importlib.abc, runpy, sys
class NoPlotting(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'matplotlib', 'cartopy', 'cmocean'}:
            raise ModuleNotFoundError(f'Plotting dependency requested: {fullname}')
sys.meta_path.insert(0, NoPlotting())
sys.argv = ['polar_qualification', '--example', '--output', sys.argv[1]]
runpy.run_module('frameit.testing.polar_qualification', run_name='__main__')
""", str(output)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert sorted(path.name for path in output.iterdir()) == ["analytical-vortex.nc", "example.json"]
    report = json.loads((output / "example.json").read_text())
    assert report["passed"] and all(check["ok"] for check in report["checks"])
    assert report["serialization"]["mean_fft_checked"]
    assert len(report["spectra"]) == 5
    assert len(report["profiles"]["radius_km"]) == 51
    reader = subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1], engine='netcdf4') as data:
    assert data.sizes['rr'] == 51 and data.sizes['theta'] == 128
    assert data.rr.attrs['units'] == 'km' and data.theta.attrs['units'] == 'rad'
    assert not data.attrs['theta_closed']
    np.testing.assert_allclose(data.constant, 1, atol=1e-12)
    assert np.isnan(data.vtan.isel(rr=0)).all()
    np.testing.assert_allclose(data.vtan.sel(rr=40), 50, atol=.05, rtol=0)
    np.testing.assert_allclose(data.vrad.sel(rr=40), -5, atol=.05, rtol=0)
assert 'frameit' not in sys.modules
""", str(output / "analytical-vortex.nc")], capture_output=True, text=True, timeout=60)
    assert reader.returncode == 0, reader.stdout + reader.stderr
