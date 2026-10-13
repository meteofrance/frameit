# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Geometry-owned interpolation plans and bounded in-memory LRU reuse."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import OrderedDict
from dataclasses import dataclass
from time import perf_counter

import numpy as np
import xarray as xr

from frameit.processing.polar.contracts import _validate_cells, target_locstream
from frameit.processing.polar.coverage import SupportedRegridder, validate_mask_options
from frameit.processing.polar.sampling import validate_axes

DEFAULT_CACHE_SIZE = 8
DEFAULT_CACHE_BYTES = 128 * 1024**2


def validate_execution_options(cache_size, max_bytes, output_chunks, profile):
    for name, value in (("polar_regrid_cache_size", cache_size),
                        ("polar_regrid_cache_max_bytes", max_bytes)):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if not isinstance(output_chunks, dict):
        raise ValueError("polar_output_chunks must be a dimension-to-integer mapping")
    for dimension, value in output_chunks.items():
        if not isinstance(dimension, str) or dimension in {
            "x_box", "y_box", "locations", "dummy", "theta_deg",
        } or isinstance(value, bool) or not isinstance(value, (int, np.integer)) or (
            value != -1 and value < 1
        ):
            raise ValueError(
                "polar_output_chunks requires output dimension names and positive sizes/-1"
            )
    if not isinstance(profile, bool):
        raise ValueError("polar_profile must be boolean")


def backend_identity():
    import xesmf

    identity = {"xesmf": str(xesmf.__version__)}
    for name in ("ESMF", "esmpy", "sparse", "numpy"):
        module = sys.modules.get(name)
        if module is not None:
            identity[name] = str(getattr(module, "__version__", "unknown"))
    return identity


def _canonical_array(values):
    array = np.array(values, dtype="<f8", order="C", copy=True)
    array[array == 0] = 0  # canonicalize signed zero without rounding coordinates
    return array


def _hash_array(digest, name, values):
    array = np.ascontiguousarray(values)
    digest.update(json.dumps((name, array.shape, array.dtype.str)).encode())
    digest.update(memoryview(array).cast("B"))


@dataclass(frozen=True)
class RegridGeometry:
    """Validated immutable snapshots; no field data or dynamic masks are retained."""

    source_lon: np.ndarray
    source_lat: np.ndarray
    target_lon: np.ndarray
    target_lat: np.ndarray
    radius_km: np.ndarray
    theta_deg: np.ndarray
    source_mask: np.ndarray | None
    provenance_json: str
    signature: str

    @property
    def provenance(self):
        return json.loads(self.provenance_json)

    @classmethod
    def capture(
        cls, source, target, *, method="bilinear", zero_tolerance=1e-14,
        source_mask=None, periodic=False, extrap_method=None, backend=None,
    ):
        if method not in {"bilinear", "nearest_s2d"}:
            raise ValueError("Regrid plans support bilinear and nearest_s2d point interpolation")
        validate_mask_options("strict", .5, zero_tolerance)
        if source.lon.dims != ("y_box", "x_box") or source.lat.dims != source.lon.dims:
            raise ValueError("Plan source geography must be normalized to y_box/x_box")
        if target.lon.dims != ("rr", "theta_deg") or target.lat.dims != target.lon.dims:
            raise ValueError("Plan target geography must use rr/theta_deg dimensions")
        arrays = [_canonical_array(value.values) for value in (
            source.lon, source.lat, target.lon, target.lat, target.rr, target.theta_deg,
        )]
        lon, lat, target_lon, target_lat, radius, angles = arrays
        if lon.shape != lat.shape or min(lon.shape) < 2 or not np.isfinite(lon).all() or (
            not np.isfinite(lat).all() or np.any(np.abs(lat) > 90)
        ):
            raise ValueError("Invalid finite source geometry")
        _validate_cells(lon, lat)
        target_locstream(target_lon, target_lat)
        validate_axes(radius, angles)
        if target_lon.shape != (radius.size, angles.size):
            raise ValueError("Target geometry does not match its polar axes")
        mask = None
        if source_mask is not None:
            mask = np.asarray(source_mask)
            if mask.shape != lon.shape or not np.isin(mask, [0, 1]).all():
                raise ValueError("Static source mask must be binary and match source geometry")
            mask = np.array(mask, dtype=np.uint8, order="C", copy=True)
        provenance = {
            "source_dimensions": ["y_box", "x_box"], "source_topology": "regional_quadrilateral",
            "target_dimensions": ["rr", "theta_deg"], "location_order": "C",
            "method": method, "zero_weight_tolerance": float(zero_tolerance),
            "periodic": bool(periodic), "extrap_method": extrap_method,
            "backend": backend_identity() if backend is None else dict(backend),
            "interpolation_geometry": "ESMF spherical longitude/latitude degrees",
            "target_earth_model": {key: target.attrs.get(key) for key in (
                "ellps", "semi_major_axis_m", "inverse_flattening",
            )},
            "static_mask_policy": (
                "exclude_entire_contributing_stencil" if mask is not None else "none"
            ),
        }
        provenance_json = json.dumps(provenance, sort_keys=True)
        digest = hashlib.sha256(provenance_json.encode())
        for name, array in zip(("source_lon", "source_lat", "target_lon", "target_lat",
                                "radius_km", "theta_deg"), arrays, strict=True):
            _hash_array(digest, name, array)
            array.setflags(write=False)
        if mask is not None:
            _hash_array(digest, "source_mask", mask)
            mask.setflags(write=False)
        return cls(*arrays, mask, provenance_json, digest.hexdigest())


@dataclass(frozen=True)
class PolarRegridPlan:
    """Reusable weights and polar layout; validity policy is supplied per application."""

    geometry: RegridGeometry
    supported: SupportedRegridder
    construction_s: float

    @classmethod
    def build(cls, geometry: RegridGeometry, *, regridder_factory=None):
        if regridder_factory is None:
            import xesmf

            regridder_factory = xesmf.Regridder
        started = perf_counter()
        source = xr.Dataset({"lon": (("y_box", "x_box"), geometry.source_lon),
                             "lat": (("y_box", "x_box"), geometry.source_lat)})
        targets = target_locstream(geometry.target_lon, geometry.target_lat)
        options = geometry.provenance
        backend = regridder_factory(
            source, targets, options["method"], locstream_out=True, unmapped_to_nan=False,
            input_dims=("y_box", "x_box"), periodic=options["periodic"],
            extrap_method=options["extrap_method"],
        )
        supported = SupportedRegridder(
            backend, zero_tolerance=options["zero_weight_tolerance"],
            source_mask=geometry.source_mask,
        )
        return cls(geometry, supported, perf_counter() - started)

    @property
    def signature(self):
        return self.geometry.signature

    @property
    def estimated_bytes(self):
        arrays = (self.geometry.source_lon, self.geometry.source_lat, self.geometry.target_lon,
                  self.geometry.target_lat, self.geometry.radius_km, self.geometry.theta_deg,
                  self.supported.mapped, self.supported.row_sums)
        total = sum(array.nbytes for array in arrays)
        if self.geometry.source_mask is not None:
            total += self.geometry.source_mask.nbytes
        for operator in (self.supported.operator, self.supported.presence):
            weights = operator.weights.data
            total += weights.data.nbytes + weights.coords.nbytes
        return total

    def apply(self, field, mask=None, *, policy="strict", minimum_support=.5, output_chunks=None):
        shape = tuple(field.sizes.get(dim) for dim in ("y_box", "x_box"))
        if shape != self.geometry.source_lon.shape:
            raise ValueError("Field shape does not match the plan's source geometry")
        chunks = output_chunks or {}
        validate_execution_options(0, 0, chunks, False)
        nr, ntheta = self.geometry.target_lon.shape
        rings = chunks.get("rr", min(32, nr))
        rings = nr if rings == -1 else min(rings, nr)
        return self.supported.apply(
            field, mask, policy=policy, minimum_support=minimum_support,
            output_chunks=(rings * ntheta,),
        )

    def diagnostics(self):
        sums = self.supported.row_sums[self.supported.mapped]
        return {
            "signature": self.signature, "source_shape": list(self.geometry.source_lon.shape),
            "target_shape": list(self.geometry.target_lon.shape),
            "mapped_targets": int(self.supported.mapped.sum()),
            "mapped_row_sum_min": float(sums.min()) if sums.size else None,
            "mapped_row_sum_max": float(sums.max()) if sums.size else None,
            "estimated_retained_bytes": self.estimated_bytes,
            "construction_s": self.construction_s, "provenance": self.geometry.provenance,
        }


class PolarRegridPlanCache:
    """LRU bounded by entries and estimated array bytes; zero capacity disables reuse."""

    def __init__(self, maxsize=DEFAULT_CACHE_SIZE, max_bytes=DEFAULT_CACHE_BYTES):
        validate_execution_options(maxsize, max_bytes, {}, False)
        self.maxsize, self.max_bytes = int(maxsize), int(max_bytes)
        self._plans = OrderedDict()
        self._bytes = 0
        self.counters = dict(hits=0, misses=0, builds=0, evictions=0, oversized_plans=0,
                             signature_s=0., construction_s=0., application_s=0., applications=0)
        self.peak_entries, self.peak_bytes = 0, 0

    def get(self, source, target, **options):
        factory = options.pop("regridder_factory", None)
        started = perf_counter()
        geometry = RegridGeometry.capture(source, target, **options)
        self.counters["signature_s"] += perf_counter() - started
        if geometry.signature in self._plans:
            self.counters["hits"] += 1
            self._plans.move_to_end(geometry.signature)
            return self._plans[geometry.signature]
        self.counters["misses"] += 1
        plan = PolarRegridPlan.build(geometry, regridder_factory=factory)
        self.counters["builds"] += 1
        self.counters["construction_s"] += plan.construction_s
        if self.maxsize and self.max_bytes:
            if plan.estimated_bytes > self.max_bytes:
                self.counters["oversized_plans"] += 1
            else:
                while self._plans and (len(self._plans) >= self.maxsize or
                                      self._bytes + plan.estimated_bytes > self.max_bytes):
                    _, removed = self._plans.popitem(last=False)
                    self._bytes -= removed.estimated_bytes
                    self.counters["evictions"] += 1
                self._plans[plan.signature] = plan
                self._bytes += plan.estimated_bytes
                self.peak_entries = max(self.peak_entries, len(self._plans))
                self.peak_bytes = max(self.peak_bytes, self._bytes)
        return plan

    def apply(self, plan, field, mask=None, **options):
        started = perf_counter()
        result = plan.apply(field, mask, **options)
        self.counters["applications"] += 1
        self.counters["application_s"] += perf_counter() - started
        return result

    def statistics(self):
        return {**self.counters, "retained_entries": len(self._plans),
                "retained_bytes": self._bytes,
                "peak_retained_entries": self.peak_entries, "peak_retained_bytes": self.peak_bytes,
                "max_entries": self.maxsize, "max_estimated_bytes": self.max_bytes}

    def clear(self):
        self._plans.clear()
        self._bytes = 0
