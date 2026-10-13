"""Independent full-ring means, complex mode amplitudes/phases and sampling aliases."""

import numpy as np
import pytest
import xarray as xr

from frameit.processing.polar import azimuthal_mean, periodic_fourier_coefficients
from frameit.processing.polar.polar_utils import close_theta_for_plot


def field(size, values, start=0):
    theta = start + np.arange(size) * 2 * np.pi / size
    da = xr.DataArray(values(theta), dims="theta", coords={"theta": theta}, name="signal")
    da.theta.attrs["units"] = "rad"
    return da


@pytest.mark.parametrize("size", [36, 64, 360])
def test_full_ring_means_do_not_double_count_north(size):
    constant = field(size, lambda t: np.ones_like(t))
    cosine = field(size, np.cos)
    sine = field(size, np.sin)
    assert float(azimuthal_mean(constant)) == 1
    assert float(azimuthal_mean(cosine)) == pytest.approx(0, abs=1e-12)
    assert float(azimuthal_mean(sine)) == pytest.approx(0, abs=1e-12)
    closed = close_theta_for_plot(cosine.to_dataset())
    assert float(closed.signal.mean("theta")) == pytest.approx(1 / (size + 1), abs=1e-12)
    with pytest.raises(ValueError, match="endpoint-exclusive"):
        azimuthal_mean(closed.signal)


@pytest.mark.parametrize("mode", [1, 2, 3])
@pytest.mark.parametrize("start", [0, 0.01])
def test_complex_coefficients_and_compass_phase(mode, start):
    amplitude, phase, offset = 2.5, 0.37, 4.0
    da = field(64, lambda t: offset + amplitude * np.cos(mode * (t - phase)), start)
    coefficients = periodic_fourier_coefficients(da)
    assert coefficients.sel(azimuthal_wavenumber=0).item() == pytest.approx(offset, abs=1e-12)
    expected = amplitude / 2 * np.exp(-1j * mode * phase)
    assert coefficients.sel(azimuthal_wavenumber=mode).item() == pytest.approx(expected, abs=1e-12)
    assert coefficients.sel(azimuthal_wavenumber=-mode).item() == pytest.approx(
        expected.conjugate(), abs=1e-12
    )
    leakage = coefficients.drop_sel(azimuthal_wavenumber=[0, mode, -mode])
    np.testing.assert_allclose(leakage, 0, atol=1e-12)


def test_shifted_wave_direction_transforms_complex_phase():
    mode, shift = 3, 0.24
    original = periodic_fourier_coefficients(field(64, lambda t: np.cos(mode * (t - 0.31))))
    shifted = periodic_fourier_coefficients(field(64, lambda t: np.cos(mode * (t - 0.31 - shift))))
    expected = original.sel(azimuthal_wavenumber=mode) * np.exp(-1j * mode * shift)
    np.testing.assert_allclose(shifted.sel(azimuthal_wavenumber=mode), expected, atol=1e-12)


def test_above_nyquist_mode_aliases_on_coarse_samples():
    mode = 11
    coarse = periodic_fourier_coefficients(field(16, lambda t: np.cos(mode * t)))
    fine = periodic_fourier_coefficients(field(64, lambda t: np.cos(mode * t)))
    assert coarse.sel(azimuthal_wavenumber=5).item() == pytest.approx(0.5, abs=1e-12)
    assert fine.sel(azimuthal_wavenumber=11).item() == pytest.approx(0.5, abs=1e-12)
    assert fine.sel(azimuthal_wavenumber=5).item() == pytest.approx(0, abs=1e-12)


def test_dc_and_nyquist_coefficients_are_not_doubled():
    da = field(16, lambda t: 3 + 2 * np.cos(8 * t))
    coeff = periodic_fourier_coefficients(da)
    assert coeff.sel(azimuthal_wavenumber=0).item() == pytest.approx(3)
    assert coeff.sel(azimuthal_wavenumber=-8).item() == pytest.approx(2)


@pytest.mark.parametrize("invalid", [np.nan, np.inf])
def test_incomplete_rings_are_not_zero_filled_or_partially_averaged(invalid):
    da = field(64, np.cos)
    da[10] = invalid
    assert np.isnan(azimuthal_mean(da))
    assert np.isnan(periodic_fourier_coefficients(da)).all()


def test_nonuniform_directional_samples_reject_full_ring_diagnostics():
    da = xr.DataArray([1., 2., 3.], dims="theta", coords={"theta": [0., 1., 2.]})
    for helper in (azimuthal_mean, periodic_fourier_coefficients):
        with pytest.raises(ValueError, match="uniform"):
            helper(da)


def test_fourier_coefficients_broadcast_vertical_axes_and_remain_lazy():
    source = field(64, lambda t: np.cos(2 * (t - 0.37))).expand_dims(level=[1000, 2000])
    source.attrs["units"] = "m s-1"
    eager = periodic_fourier_coefficients(source)
    lazy = periodic_fourier_coefficients(source.chunk({"level": 1, "theta": -1}))
    assert hasattr(lazy.data, "dask")
    xr.testing.assert_allclose(lazy.compute(), eager)
    assert lazy.attrs["units"] == "m s-1"
    assert lazy.dims == ("level", "azimuthal_wavenumber")
