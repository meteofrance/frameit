# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Nonnegative-weight interpolation with explicit source support and quality flags."""

from __future__ import annotations

from copy import copy

import numpy as np
import xarray as xr

STATUS_MEANINGS = (
    "valid unmapped_geometry missing_source_data insufficient_valid_weight undefined_vector_origin"
)


def validate_mask_options(policy, minimum_support, zero_tolerance):
    if policy not in {"strict", "renormalize"}:
        raise ValueError("polar_missing_data_policy must be 'strict' or 'renormalize'")
    if not np.isfinite(minimum_support) or not 0 <= minimum_support <= 1:
        raise ValueError("polar_min_valid_weight_fraction must lie within [0, 1]")
    if not np.isfinite(zero_tolerance) or not 0 <= zero_tolerance < 1e-6:
        raise ValueError("polar_weight_zero_tolerance must lie within [0, 1e-6)")


def quality_arrays(support, status):
    """Return portable fraction/status/validity arrays with CF flag metadata."""
    support.attrs = {"units": "1", "long_name": "valid interpolation-weight support fraction"}
    status = status.astype(np.uint8)
    status.attrs = {
        "units": "1", "long_name": "interpolation validity reason",
        "flag_values": np.arange(5, dtype=np.uint8), "flag_meanings": STATUS_MEANINGS,
    }
    valid = (status == 0).astype(np.uint8)
    valid.attrs = {"units": "1", "long_name": "valid sampled value indicator"}
    for array in (support, status, valid):
        array.attrs["frameit_role"] = "interpolation_quality"
    return support, status, valid


def attach_quality(ds, name, support, status):
    support = support.transpose(*ds[name].dims)
    status = status.transpose(*ds[name].dims)
    support, status, valid = quality_arrays(support, status)
    names = [f"{name}_support_fraction", f"{name}_interpolation_status", f"{name}_valid"]
    for variable, value in zip(names, (support, status, valid), strict=True):
        ds[variable] = value
    coverage = valid.mean("theta")
    coverage.attrs = {
        "units": "1", "long_name": f"fraction of valid launch-angle samples for {name}",
        "frameit_role": "interpolation_quality",
    }
    ds[f"{name}_ring_coverage"] = coverage
    eligible = (valid == 1).all("theta").astype(np.uint8)
    eligible.attrs = {
        "units": "1", "long_name": "complete-ring mean/Fourier eligibility",
        "frameit_role": "interpolation_quality",
    }
    ds[f"{name}_full_ring_valid"] = eligible
    ds[name].attrs["ancillary_variables"] = " ".join(
        names + [f"{name}_ring_coverage", f"{name}_full_ring_valid"]
    )


class SupportedRegridder:
    """Apply actual xESMF weights, retaining joint vector masks and strict stencils."""

    def __init__(self, regridder, *, policy="strict", minimum_support=0.5, zero_tolerance=1e-14):
        import sparse

        validate_mask_options(policy, minimum_support, zero_tolerance)
        self.policy, self.minimum_support = policy, minimum_support
        weights = regridder.weights.data.to_scipy_sparse().tocsr(copy=True)
        weights.sum_duplicates()
        if not np.isfinite(weights.data).all():
            raise ValueError(
                "Nonfinite interpolation weights; construct with unmapped_to_nan=False"
            )
        if np.any(weights.data < -zero_tolerance):
            raise ValueError("Valid-weight fractions require nonnegative interpolation weights")
        weights.data[np.abs(weights.data) <= zero_tolerance] = 0
        weights.eliminate_zeros()
        row_sums = np.asarray(weights.sum(axis=1)).ravel()
        self.mapped = row_sums > 0
        if not np.allclose(row_sums[self.mapped], 1, rtol=1e-10, atol=1e-12):
            raise ValueError("Point interpolation weights must preserve constant fields")
        # Normalize only numerical row-sum error after removing declared zero weights.
        rows = np.repeat(np.arange(weights.shape[0]), np.diff(weights.indptr))
        weights.data /= row_sums[rows]
        self.operator = copy(regridder)
        self.operator.weights = xr.DataArray(
            sparse.COO.from_scipy_sparse(weights), dims=("out_dim", "in_dim")
        )
        presence = weights.copy()
        presence.data[:] = 1
        self.presence = copy(regridder)
        self.presence.weights = xr.DataArray(
            sparse.COO.from_scipy_sparse(presence), dims=("out_dim", "in_dim")
        )
        self.geometry_mapped = xr.DataArray(self.mapped, dims="locations")

    def apply(self, field: xr.DataArray, mask: xr.DataArray | None = None):
        if mask is None:
            mask = np.isfinite(field)
        else:
            field, mask = xr.align(field, mask, join="exact")
            mask = mask & np.isfinite(field)
        # No source NaN/Inf ever enters a sparse matrix multiply, including
        # contributors whose mathematically zero coefficient was discarded.
        numerator = self.operator(field.where(mask, 0), keep_attrs=True, skipna=False)
        support = self.operator(mask.astype(float), skipna=False).clip(0, 1)
        absent = self.presence((~mask).astype(float), skipna=False)
        mapped = self.geometry_mapped.broadcast_like(numerator)
        # Complete stencils have exactly unit support; floating sparse sums
        # must not turn a threshold of one into an accidental rejection.
        support = xr.where(mapped & (absent == 0), 1.0, support)
        if self.policy == "strict":
            valid = mapped & (absent == 0)
            result = numerator.where(valid)
            status = xr.where(absent > 0, 2, 0)
        else:
            valid = mapped & (support > 0) & (support >= self.minimum_support)
            if self.minimum_support == 1:
                valid = valid & (absent == 0)
            result = (numerator / support.where(support > 0)).where(valid)
            status = xr.where(support <= 0, 2, xr.where(valid, 0, 3))
        status = xr.where(mapped, status, 1).astype(np.uint8)
        support = support.where(mapped, 0)
        result.attrs = dict(field.attrs)
        return result, support, status
