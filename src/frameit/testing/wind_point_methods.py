"""Experimental point-vector operators and structural metrics, not stable methods.

Scalar ESMF weights and source-to-target vector transport are varied separately.
Scientific velocities remain Earth-relative; no storm translation is subtracted.
"""

from __future__ import annotations

from time import perf_counter

import numpy as np
import xarray as xr
from pyproj import Geod

from frameit.processing.polar.contracts import finite_source_footprint, target_locstream
from frameit.processing.polar.coverage import SupportedRegridder
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.testing.polar_qualification import error_metrics

METHODS = ("bilinear_components", "bilinear_transport", "patch_components", "patch_transport")
ZERO_WEIGHT_TOLERANCE = 1e-14


def target_grid(centre, *, rmax_m=80000., radial_step_m=1000., n_theta=96):
    if not 0 < radial_step_m <= rmax_m <= 500000:
        raise ValueError("Declare 0 < radial_step_m <= rmax_m <= 500000")
    if isinstance(n_theta, bool) or not isinstance(n_theta, int) or n_theta < 3:
        raise ValueError("n_theta must be an integer >= 3")
    count = int(np.ceil(rmax_m/radial_step_m)) + 1
    if count*n_theta > 50000:
        raise ValueError("Wind experiment target exceeds 50000 points")
    radii = np.r_[np.arange(0, rmax_m, radial_step_m), rmax_m]/1000
    reference = xr.Dataset(coords={"time": [0], "y_box": [0], "x_box": [0],
        "longitude": (("y_box", "x_box"), [[centre[0]]]),
        "latitude": (("y_box", "x_box"), [[centre[1]]])})
    track = xr.Dataset({"lon": ("time", [centre[0]]), "lat": ("time", [centre[1]])},
                       coords={"time": [0]})
    grid = PolarLonLatGrid(r_km=radii, theta_deg=np.arange(n_theta)*360/n_theta,
        tracking_method="prescribed_track", time_dim="time", lon_name="longitude",
        lat_name="latitude", max_target_points=50000)
    target = grid.build(reference, track=track).isel(time=0, drop=True)
    return target.assign_coords(center_lon=centre[0], center_lat=centre[1])


def transport_angles(source_lon, source_lat, target_lon, target_lat, *, ellps="WGS84"):
    """Parallel-transport rotation along shortest geodesics (default WGS84).

    A geodesic's tangent is parallel along itself. Keeping along/cross-geodesic
    components fixed gives delta = terminal_forward_azimuth - initial_azimuth.
    Coincident endpoints use the identity, where the path azimuth is undefined.
    """
    first, back, distance = Geod(ellps=ellps).inv(
        source_lon, source_lat, target_lon, target_lat)
    delta = np.deg2rad((back + 180 - first + 180) % 360 - 180)
    return np.where(distance == 0, 0., delta)


def _weights(grid, target, method):
    import xesmf as xe

    started = perf_counter()
    backend = xe.Regridder(grid, target_locstream(target.lon.values, target.lat.values),
                            method, locstream_out=True, unmapped_to_nan=False,
                            input_dims=("y_box", "x_box"))
    if method == "bilinear":
        # Exactly the production zero-weight/row-normalization contract.
        weights = SupportedRegridder(backend).operator.weights.data.to_scipy_sparse().tocsr()
    else:
        weights = backend.weights.data.to_scipy_sparse().tocsr(copy=True)
        weights.sum_duplicates()
        if not np.isfinite(weights.data).all():
            raise ValueError("Nonfinite patch weights")
        weights.data[abs(weights.data) <= ZERO_WEIGHT_TOLERANCE] = 0
        weights.eliminate_zeros()
        sums = np.asarray(weights.sum(axis=1)).ravel()
        mapped = np.diff(weights.indptr) > 0
        if not np.allclose(sums[mapped], 1., rtol=1e-10, atol=1e-12):
            raise ValueError("Patch weights do not preserve scalar constants")
        rows = np.repeat(np.arange(weights.shape[0]), np.diff(weights.indptr))
        weights.data /= sums[rows]
    return weights, perf_counter()-started


def sample_methods(source, target):
    """Sample collocated m/s Earth-relative U/V with strict shared stencils.

    NumPy-only, bounded regional comparison. Time/height leading axes survive by
    name. Geometry is normalized through production finite-footprint contracts.
    """
    if source.sizes["y_box"]*source.sizes["x_box"] > 100000:
        raise ValueError("Wind experiment source exceeds 100000 points")
    for name in ("u", "v"):
        if source[name].attrs.get("units") != "m s-1" or (
            source[name].attrs.get("wind_reference_frame") != "earth"
            or source[name].attrs.get("GRIB_uvRelativeToGrid", 0) != 0
        ):
            raise ValueError("Supply explicitly collocated Earth-relative u/v in m s-1")
    if source.u.dims != source.v.dims:
        raise ValueError("Wind pair dimensions must match exactly")
    source, grid, footprint = finite_source_footprint(source, "longitude", "latitude")
    if np.ptp(grid.lon.values) > 20 or np.ptp(grid.lat.values) > 20:
        raise ValueError("Wind comparison is limited to regional grids spanning at most 20 degrees")
    leading = [dim for dim in source.u.dims if dim not in {"y_box", "x_box"}]
    u, v = xr.align(source.u, source.v, join="exact")
    u = u.transpose(*leading, "y_box", "x_box")
    v = v.transpose(*u.dims)
    shape = (*[u.sizes[dim] for dim in leading], target.sizes["rr"], target.sizes["theta_deg"])
    flat_u = u.values.reshape(-1, grid.lon.size)
    flat_v = v.values.reshape(flat_u.shape)
    joint = np.isfinite(flat_u) & np.isfinite(flat_v)
    safe_u, safe_v = np.where(joint, flat_u, 0), np.where(joint, flat_v, 0)
    sampled_u, sampled_v, validities, mappings, diagnostics = [], [], [], [], []
    for method in ("bilinear", "patch"):
        weights, build_s = _weights(grid, target, method)
        presence = weights.copy()
        presence.data[:] = 1
        mapped = np.diff(weights.indptr) > 0
        valid = mapped[None, :] & ((presence @ (~joint).astype(float).T).T == 0)
        rows = np.repeat(np.arange(weights.shape[0]), np.diff(weights.indptr))
        transport_started = perf_counter()
        angle = transport_angles(grid.lon.values.ravel()[weights.indices],
            grid.lat.values.ravel()[weights.indices], target.lon.values.ravel()[rows],
            target.lat.values.ravel()[rows])
        cosine, sine = weights.copy(), weights.copy()
        cosine.data *= np.cos(angle)
        sine.data *= np.sin(angle)
        transport_build_s = perf_counter()-transport_started
        for basis in ("components", "transport"):
            started = perf_counter()
            if basis == "components":
                out_u = (weights @ safe_u.T).T
                out_v = (weights @ safe_v.T).T
            else:
                out_u = (cosine @ safe_u.T + sine @ safe_v.T).T
                out_v = (cosine @ safe_v.T - sine @ safe_u.T).T
            sampled_u.append(np.where(valid, out_u, np.nan).reshape(shape))
            sampled_v.append(np.where(valid, out_v, np.nan).reshape(shape))
            validities.append(valid.reshape(shape))
            mappings.append(mapped.reshape(target.lon.shape))
            diagnostics.append({"method": f"{method}_{basis}", "weight_build_s": build_s,
                "transport_build_s": transport_build_s if basis == "transport" else 0.,
                "apply_s": perf_counter()-started, "nonzero_weights": weights.nnz,
                "negative_weights": int(np.sum(weights.data < 0)),
                "shared_base_array_bytes": int(sum(op.data.nbytes+op.indices.nbytes+op.indptr.nbytes
                                                   for op in (weights, presence))),
                "transport_extra_array_bytes": int(sum(
                    op.data.nbytes+op.indices.nbytes+op.indptr.nbytes for op in (cosine, sine))),
                "operator_array_bytes": int(sum(op.data.nbytes+op.indices.nbytes+op.indptr.nbytes
                                                for op in (weights, presence, cosine, sine)))})
    dims = ("wind_method", *leading, "rr", "theta")
    coords = {dim: u[dim] for dim in leading if dim in u.coords}
    coords.update(wind_method=list(METHODS), rr=target.rr.values,
                  theta=np.deg2rad(target.theta_deg.values),
                  theta_deg=("theta", target.theta_deg.values),
                  longitude=(("rr", "theta"), target.lon.values),
                  latitude=(("rr", "theta"), target.lat.values),
                  radial_bearing=(("rr", "theta"), target.radial_bearing.values),
                  center_lon=float(target.center_lon), center_lat=float(target.center_lat))
    result = xr.Dataset({"u": (dims, np.stack(sampled_u)), "v": (dims, np.stack(sampled_v)),
        "vector_valid": (dims, np.stack(validities).astype(np.uint8)),
        "geometry_mapped": (("wind_method", "rr", "theta"), np.stack(mappings).astype(np.uint8))},
        coords=coords, attrs=dict(target.attrs))
    bearing = result.radial_bearing
    result["vrad"] = result.u*np.sin(bearing) + result.v*np.cos(bearing)
    result["vtan"] = result.u*np.cos(bearing) - result.v*np.sin(bearing)
    result["wind_speed"] = np.hypot(result.u, result.v)
    result["polar_vector_valid"] = (
        result.vector_valid.astype(bool) & (result.rr > 0)).astype(np.uint8)
    for name in ("u", "v", "vrad", "vtan", "wind_speed"):
        result[name].attrs.update(units="m s-1", wind_reference_frame="earth",
            ancillary_variables="polar_vector_valid geometry_mapped" if name in {"vrad", "vtan"}
            else "vector_valid geometry_mapped")
    for name in ("vector_valid", "polar_vector_valid", "geometry_mapped"):
        result[name].attrs.update(units="1", flag_values=np.array([0, 1], dtype=np.uint8),
                                  flag_meanings="invalid valid")
    result.rr.attrs.update(units="km", long_name="geodesic distance from analysis centre")
    result.theta.attrs.update(units="rad", long_name="launch azimuth clockwise from north")
    result.theta_deg.attrs["units"] = "degree"
    result.longitude.attrs["units"] = "degrees_east"
    result.latitude.attrs["units"] = "degrees_north"
    result.center_lon.attrs["units"] = "degrees_east"
    result.center_lat.attrs["units"] = "degrees_north"
    result.radial_bearing.attrs.update(units="rad", long_name="terminal-forward geodesic bearing")
    result.attrs.update(maturity="experimental", wind_reference_frame="earth",
        methods=list(METHODS), missing_data_policy="strict joint U/V nonzero-weight stencil",
        zero_weight_tolerance=ZERO_WEIGHT_TOLERANCE, theta_closed=False,
        tangential_sign="clockwise positive", radial_sign="outward positive",
        conservation_claim="none: point velocities, not momentum/energy/flux remapping",
        transport_geometry=(
            "WGS84 shortest-geodesic parallel transport; ESMF scalar weights spherical"),
        source_finite_footprint=footprint)
    return result, diagnostics


def full_ring_profile(values):
    valid = np.isfinite(values).all(axis=-1)
    return np.where(valid, np.mean(values, axis=-1), np.nan)


def profile_peak(values, radius_km):
    """Peak absolute complete-ring mean vtan; incomplete search is not narrowed."""
    profile = full_ring_profile(values)[1:]
    if not np.isfinite(profile).all():
        return {"rmw_km": None, "peak_mean_tangential_ms": None,
                "reason": "incomplete rings in the declared radial search"}
    index = int(np.argmax(abs(profile)))
    return {"rmw_km": float(radius_km[index+1]),
            "peak_mean_tangential_ms": float(abs(profile[index])),
            "peak_at_search_boundary": index in {0, len(profile)-1}}


def structural_metrics(actual, reference, *, required=None, interpretation="analytical error"):
    """Point/peak/Fourier comparisons on declared support, never zero-filled rings.

    Inputs have only rr/theta dimensions. The caller distinguishes independent
    truth from a real-data baseline. Positive-mode phase requires amplitude >=.1 m/s.
    """
    radius, angles = actual.rr.values, actual.theta.values
    if required is None:
        required = np.broadcast_to(radius[:, None] > 0, actual.vtan.shape)
    fields = {name: error_metrics(actual[name].values, reference[name].values, required)
              for name in ("u", "v", "vrad", "vtan", "wind_speed")}
    actual_peak = profile_peak(actual.vtan.values, radius)
    reference_peak = profile_peak(reference.vtan.values, radius)
    peaks_available = actual_peak["rmw_km"] is not None and reference_peak["rmw_km"] is not None
    rmw_error = abs(actual_peak["rmw_km"]-reference_peak["rmw_km"]) if peaks_available else None
    peak_error = (actual_peak["peak_mean_tangential_ms"]-reference_peak["peak_mean_tangential_ms"]
                  if rmw_error is not None else None)
    actual_speed = actual.wind_speed.values[required]
    reference_speed = reference.wind_speed.values[required]
    point_peaks_available = (actual_speed.size > 0 and np.isfinite(actual_speed).all()
                             and np.isfinite(reference_speed).all())
    point_peak = float(actual_speed.max()) if point_peaks_available else None
    reference_point_peak = float(reference_speed.max()) if point_peaks_available else None
    spectra = []
    for name in ("vrad", "vtan"):
        for mode in (1, 2, 3):
            exact = np.mean(reference[name].values[1:]*np.exp(-1j*mode*angles), axis=-1)
            estimate = np.mean(actual[name].values[1:]*np.exp(-1j*mode*angles), axis=-1)
            complete = np.isfinite(exact) & np.isfinite(estimate)
            phase_eligible = complete & (abs(exact) >= .1) & (abs(estimate) >= .1)
            phase = np.angle(estimate[phase_eligible]*np.conj(exact[phase_eligible]))/mode
            strong_required = np.isfinite(exact) & (abs(exact) >= 1.)
            strong_valid = strong_required & complete & (abs(estimate) >= .1)
            strong_phase = np.angle(estimate[strong_valid]*np.conj(exact[strong_valid]))/mode
            spectra.append({"field": name, "mode": mode,
                "required_rings": len(exact), "complete_rings": int(complete.sum()),
                "complex_rms_difference_ms": float(np.sqrt(np.mean(abs(estimate-exact)**2)))
                if complete.all() else None,
                "amplitude_max_difference_ms": float(np.max(abs(abs(estimate)-abs(exact))))
                if complete.all() else None,
                "phase_eligible_rings": int(phase_eligible.sum()), "phase_floor_ms": .1,
                "strong_phase_required_rings": int(strong_required.sum()),
                "strong_phase_eligible_rings": int(strong_valid.sum()),
                "strong_phase_truth_floor_ms": 1.,
                "strong_peak_direction_max_difference_deg": float(
                    np.rad2deg(abs(strong_phase).max())) if strong_phase.size else None,
                "peak_direction_max_difference_deg": float(np.rad2deg(abs(phase).max()))
                if phase.size else None,
                "lost_resolved_phase_rings": int(np.sum(np.isfinite(exact) & (abs(exact) >= .1)
                    & (~np.isfinite(estimate) | (abs(estimate) < .1))))})
    return {"interpretation": interpretation, "fields": fields, "actual_peak": actual_peak,
            "reference_peak": reference_peak, "rmw_difference_km": rmw_error,
            "peak_mean_tangential_difference_ms": peak_error,
            "point_max_speed_ms": point_peak, "reference_point_max_speed_ms": reference_point_peak,
            "point_max_speed_difference_ms": point_peak-reference_point_peak
            if point_peaks_available else None, "spectra": spectra}


def attach_profiles(result):
    """Portable full-ring profiles and split complex coefficients for ordinary readers."""
    mode_dim = "azimuthal_wavenumber"
    for name in ("vrad", "vtan"):
        field = result[name]
        dims = tuple(dim for dim in field.dims if dim != "theta")
        values = field.transpose(*dims, "theta").values
        result[f"{name}_azimuthal_mean"] = (dims, full_ring_profile(values), {"units": "m s-1"})
        coefficients = np.stack([np.mean(values*np.exp(-1j*mode*result.theta.values), axis=-1)
                                 for mode in (1, 2, 3)], axis=-1)
        for component, data in (("real", coefficients.real), ("imag", coefficients.imag)):
            result[f"{name}_fourier_{component}"] = ((*dims, mode_dim), data, {"units": "m s-1",
                "normalization": "1/n_theta", "phase_convention": "exp(-i*m*theta)"})
    return result.assign_coords({mode_dim: [1, 2, 3]})
