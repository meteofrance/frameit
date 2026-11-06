# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Full-ring angular means and normalized, compass-referenced Fourier coefficients."""

from __future__ import annotations

import numpy as np
import xarray as xr

from frameit.processing.polar.polar_utils import _inspect_theta
from frameit.processing.polar.sampling import uniform_periodic_angles


def _require_uniform_open_ring(field, theta_dim):
    values, closed = _inspect_theta(field.to_dataset(name="_field"), theta_dim)
    if closed or not uniform_periodic_angles(values, 2 * np.pi):
        raise ValueError("Angular diagnostics require a uniform, endpoint-exclusive full ring")
    if not np.issubdtype(field.dtype, np.number):
        raise ValueError("Angular diagnostics require numerical field values")
    return values


def azimuthal_mean(field: xr.DataArray, *, theta_dim: str = "theta") -> xr.DataArray:
    """Average over launch angle; any missing sample invalidates its ring mean.

    This is not a circumference- or area-weighted mean on the ellipsoid.
    """
    _require_uniform_open_ring(field, theta_dim)
    result = field.mean(theta_dim, skipna=False, keep_attrs=True).where(
        np.isfinite(field).all(theta_dim)
    )
    result.attrs.update(averaging_basis="uniform_launch_azimuth", missing_data_policy="full_ring")
    result.attrs.pop("ancillary_variables", None)
    return result


def coverage_aware_azimuthal_mean(
    field: xr.DataArray, *, minimum_coverage: float = 1.0, theta_dim: str = "theta"
) -> xr.Dataset:
    """Return a declared valid-sector mean with coverage and full-ring eligibility.

    The default requires complete coverage. Lowering the threshold explicitly
    enables partial means, which do not reconstruct the unobserved sectors and
    need not be unbiased estimates of the full-ring mean.
    """
    _require_uniform_open_ring(field, theta_dim)
    if not np.isfinite(minimum_coverage) or not 0 <= minimum_coverage <= 1:
        raise ValueError("minimum_coverage must lie within [0, 1]")
    valid = np.isfinite(field)
    count = valid.sum(theta_dim)
    coverage = count / field.sizes[theta_dim]
    mean = (field.where(valid, 0).sum(theta_dim) / count.where(count > 0)).where(
        coverage >= minimum_coverage
    )
    mean.attrs = dict(field.attrs)
    mean.attrs.update(
        averaging_basis="uniform_launch_azimuth", averaging_coverage="valid_sector",
        minimum_ring_coverage=minimum_coverage, unobserved_sector_reconstruction="none",
    )
    mean.attrs["ancillary_variables"] = "ring_coverage full_ring_valid"
    coverage.attrs.update(units="1", long_name="fraction of finite launch-angle samples")
    return xr.Dataset({"azimuthal_mean": mean, "ring_coverage": coverage,
                       "full_ring_valid": valid.all(theta_dim).astype(np.uint8)})


def periodic_fourier_coefficients(
    field: xr.DataArray, *, theta_dim: str = "theta"
) -> xr.DataArray:
    """Return c_m = mean(q(theta) * exp(-i*m*theta)) for signed integer modes.

    Angles increase clockwise from north. For A*cos(m*(theta-theta0)), positive
    non-Nyquist c_m is A/2*exp(-i*m*theta0). DC/Nyquist are not doubled; phase
    is undefined for a vanishing coefficient. Missing samples propagate, with
    no zero filling. Dask inputs require one chunk along the angular dimension.
    """
    values = _require_uniform_open_ring(field, theta_dim)
    field = field.where(np.isfinite(field))
    size = values.size
    mode_dim = "azimuthal_wavenumber"
    if mode_dim in field.dims or mode_dim in field.coords:
        raise ValueError(f"Input already contains {mode_dim}")
    modes = np.rint(np.fft.fftfreq(size, d=1 / size)).astype(int)
    result = xr.apply_ufunc(
        lambda data: np.fft.fft(data, axis=-1) / size,
        field, input_core_dims=[[theta_dim]], output_core_dims=[[mode_dim]],
        exclude_dims={theta_dim}, dask="parallelized", output_dtypes=[np.complex128],
        dask_gufunc_kwargs={"output_sizes": {mode_dim: size}}, keep_attrs=True,
    ).assign_coords({mode_dim: modes})
    # An offset starting angle must not change the compass phase convention.
    result = result * xr.DataArray(np.exp(-1j * modes * values[0]), dims=mode_dim,
                                  coords={mode_dim: modes})
    result.name = f"{field.name}_fourier_coefficient" if field.name else "fourier_coefficient"
    result.attrs = dict(field.attrs)
    result.attrs.pop("ancillary_variables", None)
    result.attrs.update(
        fourier_normalization="1/n_theta", phase_convention="exp(-i*m*theta), clockwise_from_north",
        missing_data_policy="full_ring",
    )
    result[mode_dim].attrs.update(units="1", long_name="signed azimuthal wavenumber")
    return result
