# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Nonnegative-weight interpolation with explicit source support and quality flags."""

from __future__ import annotations

from copy import copy
from math import fsum

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


def _apply_weights(data, valid, *, weights, presence, rows, minimum_support):
    """One cropped horizontal block, with a module-level callable for spawned export."""
    weights, presence = weights[rows], presence[rows]
    shape = (*data.shape[:-2], weights.shape[0])
    data = data.reshape(-1, weights.shape[1])
    valid = valid.reshape(data.shape)
    numerator = (weights @ np.where(valid, data, 0).T).T.astype(data.dtype, copy=False)
    support = (weights @ valid.astype(float).T).T
    absent = (presence @ (~valid).astype(float).T).T
    if minimum_support is not None and 0 < minimum_support < 1:
        # Re-sum borderline stencils accurately; never relax the scientific threshold.
        bound = 2 * np.finfo(float).eps * np.diff(weights.indptr)
        uncertain = ((abs(support - minimum_support) <= bound)
                     & (support > 0) & (absent > 0))
        for sample, location in np.argwhere(uncertain):
            start, stop = weights.indptr[location:location + 2]
            support[sample, location] = fsum(
                weight for weight, index in zip(weights.data[start:stop],
                                                  weights.indices[start:stop], strict=True)
                if valid[sample, index])
    return tuple(array.reshape(shape) for array in (numerator, support, absent))


class SupportedRegridder:
    """Apply actual xESMF weights, retaining joint vector masks and strict stencils."""

    def __init__(
        self, regridder, *, policy="strict", minimum_support=0.5, zero_tolerance=1e-14,
        source_mask=None,
    ):
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
        if source_mask is not None:
            mask = np.asarray(source_mask)
            if mask.shape != regridder.shape_in or not np.isin(mask, [0, 1]).all():
                raise ValueError("Static source mask must be binary and match the source grid")
            rows = np.repeat(np.arange(weights.shape[0]), np.diff(weights.indptr))
            excluded_rows = np.unique(rows[~mask.astype(bool).ravel()[weights.indices]])
            weights.data[np.isin(rows, excluded_rows)] = 0
            weights.eliminate_zeros()
        row_sums = np.asarray(weights.sum(axis=1)).ravel()
        self.row_sums = row_sums.copy()
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
        self.weights, self.presence_weights = weights, presence
        self.presence = copy(regridder)
        self.presence.weights = xr.DataArray(
            sparse.COO.from_scipy_sparse(presence), dims=("out_dim", "in_dim")
        )
        self.geometry_mapped = xr.DataArray(self.mapped, dims="locations")

    def apply(
        self, field: xr.DataArray, mask: xr.DataArray | None = None, *, policy=None,
        minimum_support=None, output_chunks=None,
    ):
        policy = self.policy if policy is None else policy
        minimum_support = self.minimum_support if minimum_support is None else minimum_support
        validate_mask_options(policy, minimum_support, 0)
        if not {"y_box", "x_box"} <= set(field.dims):
            raise ValueError("Fields require named y_box/x_box dimensions")
        leading = [dim for dim in field.dims if dim not in {"y_box", "x_box"}]
        field = field.transpose(*leading, "y_box", "x_box")
        if mask is None:
            mask = np.isfinite(field)
        else:
            field, mask = xr.align(field, mask, join="exact")
            mask = mask & np.isfinite(field)
        mask = mask.transpose(*field.dims)
        if tuple(field.sizes[dim] for dim in ("y_box", "x_box")) != self.operator.shape_in:
            raise ValueError("Field shape does not match the interpolation source grid")
        if field.chunks is not None or mask.chunks is not None:
            # A stencil needs the cropped horizontal plane, never all times/levels.
            if field.chunks is None:
                field = field.chunk(mask.chunksizes)
            field = field.chunk({"y_box": -1, "x_box": -1})
            mask = mask.chunk(field.chunksizes)
        weights, presence = self.weights, self.presence_weights

        # No source NaN/Inf ever enters a sparse matrix multiply, including
        # contributors whose mathematically zero coefficient was discarded.
        locations = weights.shape[0]
        chunk_size = output_chunks[0] if output_chunks else locations
        chunk_size = locations if chunk_size == -1 else chunk_size
        blocks = []
        for start in range(0, locations, chunk_size):
            stop = min(start + chunk_size, locations)
            blocks.append(xr.apply_ufunc(
                _apply_weights, field, mask,
                kwargs={"weights": weights, "presence": presence, "rows": slice(start, stop),
                        "minimum_support": minimum_support if policy == "renormalize" else None},
                input_core_dims=[["y_box", "x_box"], ["y_box", "x_box"]],
                output_core_dims=[["locations"], ["locations"], ["locations"]],
                dask="parallelized", output_dtypes=[field.dtype, float, float],
                dask_gufunc_kwargs={"output_sizes": {"locations": stop - start}},
            ))
        arrays = tuple(xr.concat([block[index] for block in blocks], dim="locations")
                       if len(blocks) > 1 else blocks[0][index] for index in range(3))
        numerator, support, absent = arrays
        support = support.clip(0, 1)
        mapped = self.geometry_mapped.broadcast_like(numerator)
        # Complete stencils have exactly unit support; floating sparse sums
        # must not turn a threshold of one into an accidental rejection.
        support = xr.where(mapped & (absent == 0), 1.0, support)
        if policy == "strict":
            valid = mapped & (absent == 0)
            result = numerator.where(valid)
            status = xr.where(absent > 0, 2, 0)
        else:
            valid = mapped & (support > 0) & (support >= minimum_support)
            if minimum_support == 1:
                valid = valid & (absent == 0)
            result = (numerator / support.where(support > 0)).where(valid)
            status = xr.where(support <= 0, 2, xr.where(valid, 0, 3))
        status = xr.where(mapped, status, 1).astype(np.uint8)
        support = support.where(mapped, 0)
        result.attrs = dict(field.attrs)
        return result, support, status
