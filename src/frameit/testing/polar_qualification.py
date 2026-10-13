"""Integrated numerical qualification of geodesic cyclone point diagnostics.

Run ``python -m frameit.testing.polar_qualification --output <fresh-directory>``.
JSON evidence and optional figures record independent truth, common valid sets,
source refinement, spectra, centre sensitivity and deliberate coverage loss.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import xarray as xr

from frameit.testing.analytic_vortices import (
    AnalyticVortex,
    analytic_source,
    displaced_centre,
    sampled_truth,
)
from frameit.testing.artifacts import atomic_json, environment_metadata, utc_now

REFERENCES = {
    "geodesic_geometry": "10.1007/s00190-012-0578-z",
    "controlled_centre_experiments": "10.1175/JAMC-D-15-0125.1",
    "gaussian_vorticity_and_streamfunction": "10.3390/atmos10060300",
    "coverage_screening": "10.1175/MWR-D-21-0223.1",
}


def qualification_settings(**changes):
    values = dict(
        atm_model="AROME", velocity_aliases={"u_velocity": "u", "v_velocity": "v"},
        compute_polar_proj=True, tracking_method="prescribed_track",
        name_longitude="longitude", name_latitude="latitude", x_boxsize_km=200,
        y_boxsize_km=200, radial_resolution=2000, polar_n_theta=128,
        polar_variables={"heightAboveGround": {"variables": [
            "u", "v", "constant", "smooth_scalar", "harmonic_1", "harmonic_2", "harmonic_3",
        ]}}, polar_missing_data_policy="strict", polar_profile=True,
    )
    values.update(changes)
    return SimpleNamespace(**values)


def project_fixture(vortex, spacing_m, *, grid_kind="rectilinear", analysis_centre=None,
                    grid_centre=None, alignment=(0., 0.), source=None, **settings):
    from frameit.processing.polar.polar_proj import polar_project

    centre = analysis_centre or (vortex.longitude, vortex.latitude)
    source = source if source is not None else analytic_source(
        vortex, spacing_m, grid_kind=grid_kind, grid_centre=grid_centre, alignment=alignment
    )
    config = qualification_settings(**settings)
    track = xr.Dataset({"lon": ("time", np.full(source.sizes["time"], centre[0])),
                        "lat": ("time", np.full(source.sizes["time"], centre[1]))},
                       coords={"time": source.time.values})
    started = perf_counter()
    output, report = polar_project({"heightAboveGround": source}, conf=config, track=track)
    result = output["heightAboveGround"].compute()
    elapsed = perf_counter() - started
    truth = sampled_truth(vortex, result, centre)
    return result, truth, report, elapsed


def error_metrics(actual, truth, required):
    """Do not let a method improve its score by dropping difficult target points."""
    actual, truth, required = np.broadcast_arrays(actual, truth, required)
    required = required & np.isfinite(truth)
    count = int(required.sum())
    valid = required & np.isfinite(actual)
    missing = count - int(valid.sum())
    error = actual[required] - truth[required]
    return {
        "required_points": count, "valid_required_points": int(valid.sum()),
        "missing_required_points": missing,
        "rms": float(np.sqrt(np.mean(error**2))) if count and not missing else None,
        "maximum": float(np.max(np.abs(error))) if count and not missing else None,
    }


def compare_fields(result, truth, *, minimum_radius_m=0):
    required = np.broadcast_to(result.rr.values[:, None] * 1000 >= minimum_radius_m,
                               (result.sizes["rr"], result.sizes["theta"]))
    metrics = {}
    for name in ("constant", "smooth_scalar", "vrad", "vtan", "wind_speed"):
        actual = result[name].isel(time=0, heightAboveGround=0).values
        metrics[name] = error_metrics(actual, truth[name][0], required)
        scale = 1. if name in ("constant", "smooth_scalar") else max(
            float(np.nanmax(truth["wind_speed"])), 1e-12
        )
        metrics[name]["normalization_scale"] = scale
        metrics[name]["units"] = "1" if name in ("constant", "smooth_scalar") else "m s-1"
        metrics[name]["normalized_rms"] = (
            metrics[name]["rms"] / scale if metrics[name]["rms"] is not None else None
        )
        metrics[name]["normalized_maximum"] = (
            metrics[name]["maximum"] / scale if metrics[name]["maximum"] is not None else None
        )
    return metrics


def direct_coefficients(values, angles, mode):
    return np.mean(values * np.exp(-1j * mode * angles), axis=-1)


def spectral_metrics(result, truth, *, minimum_radius_m=20000):
    """Compare complex coefficients first; measure phase only above an amplitude floor."""
    angles = result.theta.values
    selected = result.rr.values * 1000 >= minimum_radius_m
    records = []
    for name, mode in (("vrad", 1), ("vtan", 1),
                       ("harmonic_1", 1), ("harmonic_2", 2), ("harmonic_3", 3)):
        actual = direct_coefficients(result[name].isel(time=0, heightAboveGround=0).values,
                                     angles, mode)[selected]
        exact = direct_coefficients(truth[name][0], angles, mode)[selected]
        delta = actual - exact
        phase_floor = .1 if name in ("vrad", "vtan") else 1e-3
        strong = np.abs(exact) >= phase_floor
        phase_error = np.angle(actual[strong] * np.conj(exact[strong])) / mode
        records.append({
            "field": name, "mode": mode,
            "complex_rms_error": float(np.sqrt(np.mean(np.abs(delta)**2))),
            "amplitude_max_error": float(np.max(np.abs(np.abs(actual) - np.abs(exact)))),
            "phase_peak_direction_max_error_rad": float(np.max(np.abs(phase_error)))
            if strong.any() else None,
            "phase_amplitude_floor": phase_floor,
            "actual_coefficients": [[float(z.real), float(z.imag)] for z in actual],
            "truth_coefficients": [[float(z.real), float(z.imag)] for z in exact],
        })
    return records


def radial_profiles(result, truth):
    records = {"radius_km": result.rr.values.tolist()}
    for name in ("vrad", "vtan", "wind_speed"):
        actual = result[name].isel(time=0, heightAboveGround=0).values
        exact = truth[name][0]
        records[name] = {
            "actual": [float(x) if np.isfinite(x) else None for x in np.mean(actual, axis=-1)],
            "truth": [float(x) if np.isfinite(x) else None for x in np.mean(exact, axis=-1)],
        }
    actual = np.abs(np.mean(result.vtan.isel(time=0, heightAboveGround=0).values[1:], axis=-1))
    exact = np.abs(np.mean(truth["vtan"][0, 1:], axis=-1))
    radii = result.rr.values[1:]
    records["rmw"] = {"actual_km": float(radii[np.argmax(actual)]),
                      "truth_on_target_grid_km": float(radii[np.argmax(exact)]),
                      "error_km": float(abs(radii[np.argmax(actual)] - radii[np.argmax(exact)]))}
    return records


def refinement_case(vortex, *, grid_kind="rectilinear", spacings=(8000., 4000., 2000., 1000.),
                    minimum_radius_m=0, alignment=(.17, -.23)):
    records = []
    for spacing in spacings:
        result, truth, report, elapsed = project_fixture(
            vortex, spacing, grid_kind=grid_kind, alignment=alignment
        )
        records.append({
            "source_spacing_m": spacing, "metrics": compare_fields(
                result, truth, minimum_radius_m=minimum_radius_m
            ), "spectra": spectral_metrics(result, truth),
            "profiles": radial_profiles(result, truth),
            "geometry_mapped_points": int(result.geometry_mapped.sum()),
            "target_points": int(result.geometry_mapped.size),
            "source_shape": report["projected"][0]["source_finite_footprints"][0]["finite_shape"],
            "complete_execution_s": elapsed, "regrid_performance": report["regrid_performance"],
        })
        if vortex.kind == "streamfunction":
            records[-1]["profiles"]["rmw"] = None
    for index in range(1, len(records)):
        ratio = records[index - 1]["source_spacing_m"] / records[index]["source_spacing_m"]
        orders = {}
        for field, metric in records[index]["metrics"].items():
            earlier = records[index - 1]["metrics"][field]["rms"]
            error = metric["rms"]
            orders[field] = float(np.log(earlier / error) / np.log(ratio)) if (
                earlier is not None and error is not None and earlier > 1e-13 and error > 1e-13
            ) else None
        records[index]["observed_orders"] = orders
    return {"fixture": vortex.parameters(), "grid_kind": grid_kind,
            "alignment_in_source_cells": list(alignment), "minimum_radius_m": minimum_radius_m,
            "target_radial_spacing_m": 2000., "target_n_theta": 128, "refinement": records}


def refinement_gates(case, *, order_fields, rms_limits):
    """Predeclared physical error/coverage gates; thresholds are engineering criteria."""
    checks = []
    for row in case["refinement"]:
        for name, metric in row["metrics"].items():
            checks.append({"name": f"{name}_common_valid_set_{row['source_spacing_m']}",
                           "ok": metric["missing_required_points"] == 0
                           and metric["required_points"] > 0})
        constant_error = row["metrics"]["constant"]["maximum"]
        checks.append({"name": f"constant_preservation_{row['source_spacing_m']}",
                       "ok": constant_error is not None and constant_error <= 1e-12})
    for row in case["refinement"][-2:]:
        for name in order_fields:
            order = row.get("observed_orders", {}).get(name)
            checks.append({"name": f"{name}_interior_order_{row['source_spacing_m']}",
                           "value": order, "minimum": 1.7,
                           "ok": order is not None and order >= 1.7})
    fine = case["refinement"][-1]
    for name, limit in rms_limits.items():
        value = fine["metrics"][name]["rms"]
        checks.append({"name": f"{name}_finest_rms", "value": value, "maximum": limit,
                       "ok": value is not None and value <= limit})
    if case["fixture"]["kind"] == "geodesic":
        error = fine["profiles"]["rmw"]["error_km"]
        checks.append({"name": "radius_of_maximum_wind_on_target_grid", "value": error,
                       "maximum_km": 2., "ok": error <= 2.})
    return checks


def centre_sensitivity(vortex, *, spacings=(4000., 1000.)):
    rows = []
    reference_radius = (1.120906422778534 * vortex.gaussian_width_m
                        if vortex.kind == "gaussian_vorticity" else vortex.radius_m)
    reference_name = ("derived_gaussian_rmw" if vortex.kind == "gaussian_vorticity"
                      else "streamfunction_envelope_radius")
    for fraction in (0., .05, .1, .25):
        for direction in ((0.,) if fraction == 0 else (0., 90., 225.)):
            centre = displaced_centre(vortex, fraction * reference_radius, direction)
            for spacing in spacings:
                result, truth, _, _ = project_fixture(vortex, spacing, analysis_centre=centre)
                rows.append({"source_spacing_m": spacing,
                             "centre_offset_rmw_fraction": fraction
                             if vortex.kind == "gaussian_vorticity" else None,
                             "centre_offset_reference_fraction": fraction,
                             "centre_offset_reference_radius_m": reference_radius,
                             "centre_offset_reference": reference_name,
                             "fixture_kind": vortex.kind,
                             "centre_offset_m": fraction * reference_radius,
                             "offset_bearing_deg": direction, "analysis_centre": list(centre),
                             "metrics": compare_fields(result, truth, minimum_radius_m=20000),
                             "spectra": spectral_metrics(result, truth)})
    return rows


def angular_sweep(vortex):
    rows = []
    for count in (16, 32, 64, 128):
        result, truth, _, _ = project_fixture(vortex, 1000, polar_n_theta=count)
        errors = []
        for mode in (1, 2, 3):
            radius = result.rr.values * 1000
            envelope = (radius / vortex.radius_m)**mode * np.exp(
                (1 - (radius / vortex.radius_m)**2) / 2
            )
            expected = envelope / 2 * np.exp(-1j * mode * .37)
            actual = direct_coefficients(truth[f"harmonic_{mode}"][0], result.theta.values, mode)
            errors.append(float(np.max(np.abs(actual - expected))))
        rows.append({"n_theta": count, "source_spacing_m": 1000,
                     "analytical_harmonic_coefficient_errors": errors,
                     "sampled_spectra": spectral_metrics(result, truth)})
    return rows


def subgrid_translations(vortex):
    rows = []
    for spacing in (4000., 1000.):
        for east, north in ((0., 0.), (.23, .37), (-.41, .19)):
            distance = spacing * np.hypot(east, north)
            bearing = np.rad2deg(np.arctan2(east, north))
            centre = displaced_centre(vortex, distance, bearing)
            from dataclasses import replace

            translated = replace(vortex, longitude=centre[0], latitude=centre[1])
            result, truth, _, _ = project_fixture(
                translated, spacing, grid_centre=(vortex.longitude, vortex.latitude)
            )
            rows.append({"source_spacing_m": spacing, "translation_source_cells": [east, north],
                         "centre_grid_offset_m": float(result.center_grid_offset_m[0]),
                         "metrics": compare_fields(result, truth)})
    return rows


def backend_equivalence(vortex):
    source = analytic_source(vortex, 2000)
    eager, _, _, _ = project_fixture(vortex, 2000, source=source)
    uncached, _, _, _ = project_fixture(vortex, 2000, source=source, polar_regrid_cache_size=0)
    lazy, _, _, _ = project_fixture(vortex, 2000, source=source.chunk(
        {"time": 1, "heightAboveGround": 1, "y_box": 31, "x_box": 29}
    ), polar_output_chunks={"rr": 17, "theta": 32})
    xr.testing.assert_allclose(eager, uncached, rtol=1e-12, atol=1e-12)
    xr.testing.assert_allclose(eager, lazy, rtol=1e-12, atol=1e-12)
    return {"cached_uncached_equivalent": True, "eager_lazy_equivalent": True}


def clipped_boundary_errors(vortex):
    """Fixed oracle-defined interior/boundary sets on a clipped geographic source."""
    from pyproj import Geod

    geod = Geod(ellps=vortex.earth_model)
    _, _, east_m = geod.inv(vortex.longitude, vortex.latitude,
                           vortex.longitude + 1, vortex.latitude)
    _, _, north_m = geod.inv(vortex.longitude, vortex.latitude,
                            vortex.longitude, vortex.latitude + 1)
    rows = []
    for spacing in (4000., 2000., 1000.):
        source = analytic_source(vortex, spacing, extent_m=80000.)
        result, truth, _, _ = project_fixture(vortex, spacing, source=source)
        x = ((result.longitude.values[0] - vortex.longitude + 180) % 360 - 180) * east_m
        y = (result.latitude.values[0] - vortex.latitude) * north_m
        common = (abs(x) <= 79000) & (abs(y) <= 79000)
        boundary = common & ((abs(x) >= 72000) | (abs(y) >= 72000))
        row = {"source_spacing_m": spacing, "source_extent_m": 80000,
               "mapped_points": int(result.geometry_mapped.sum()), "regions": {}}
        for region, required in (("interior", common & ~boundary), ("boundary", boundary)):
            row["regions"][region] = {}
            for name in ("smooth_scalar", "vrad", "vtan"):
                actual = result[name].isel(time=0, heightAboveGround=0).values
                row["regions"][region][name] = error_metrics(actual, truth[name][0], required)
        rows.append(row)
    return rows


def coverage_experiment(vortex, output=None):
    source = analytic_source(vortex, 2000, times=(0, 1, 2))
    _, angles, _ = vortex.polar_geometry(source.longitude.values, source.latitude.values)
    for index in range(3):
        wrapped = angles % (2 * np.pi)
        masked = (wrapped >= index * .4) & (wrapped < index * .4 + np.pi / 2)
        for name in source.data_vars:
            source[name][index] = source[name].isel(time=index).where(~masked)
    # Deliberate true model boundary: keep only the eastern half of the grid.
    keep = source.x_box >= 0
    source = source.assign_coords(longitude=source.longitude.where(keep),
                                  latitude=source.latitude.where(keep))
    for name in source.data_vars:
        source[name] = source[name].where(keep)
    centres = [(vortex.longitude + index * .005, vortex.latitude) for index in range(3)]
    from frameit.processing.polar.polar_proj import polar_project

    track = xr.Dataset({"lon": ("time", [c[0] for c in centres]),
                        "lat": ("time", [c[1] for c in centres])}, coords={"time": [0, 1, 2]})
    projected, _ = polar_project({"heightAboveGround": source}, conf=qualification_settings(),
                                 track=track)
    result = projected["heightAboveGround"].compute()
    expected = result.constant_valid.mean("theta")
    np.testing.assert_allclose(result.constant_ring_coverage, expected)
    assert bool((result.geometry_mapped == 0).any())
    assert bool((result.constant_interpolation_status == 2).any())
    assert bool((result.constant_full_ring_valid == 0).any())
    if output is not None:
        from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf

        path = Path(output) / "moving-masked-vortex.nc"
        write_dataset_netcdf(result, path, product_type="polar", metadata=ExportMetadata(
            "moving-mask", "Moving masked analytical field", "Clipping and changing sectors",
            "FrameIt", "Independent analytical source samples",
        ))
        with xr.open_dataset(path) as saved:
            for name in ("constant_valid", "constant_ring_coverage",
                         "constant_interpolation_status", "geometry_mapped"):
                np.testing.assert_array_equal(saved[name], result[name])
    return {"status_counts": {str(status): int(
        (result.constant_interpolation_status == status).sum())
                              for status in (0, 1, 2, 3)},
            "ring_coverage": result.constant_ring_coverage.values.tolist(),
            "coverage_matches_valid_sample_counts": True,
            "accuracy_scoring": "incomplete rings are not scored as improved interpolation"}


def serialization_and_diagnostics(vortex, output):
    from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf
    from frameit.processing.polar.diagnostics import azimuthal_mean, periodic_fourier_coefficients
    from frameit.processing.polar.polar_utils import close_theta_for_plot

    result, truth, _, _ = project_fixture(vortex, 1000)
    result.attrs["analytical_parameters"] = vortex.parameters()
    path = Path(output) / "analytical-vortex.nc"
    write_dataset_netcdf(result, path, product_type="polar", metadata=ExportMetadata(
        "analytical-vortex", "Geodesic vortex qualification", "Independent manufactured truth",
        "FrameIt", "Analytical east/north source samples",
    ))
    with xr.open_dataset(path) as dataset:
        saved = dataset.load()
    for name in result.variables:
        np.testing.assert_allclose(saved[name], result[name], atol=1e-12, rtol=1e-12,
                                   equal_nan=True)
    assert saved.rr.attrs["units"] == "km" and saved.theta.attrs["units"] == "rad"
    assert saved.radial_bearing.attrs["units"] == "rad"
    assert saved.theta_deg.attrs["units"] == "degree"
    assert not saved.attrs["theta_closed"]
    assert saved.attrs["polar_vector_origin_policy"] == "undefined_radial_tangential_components"
    assert "analytical_parameters_json" in saved.attrs
    np.testing.assert_allclose(azimuthal_mean(saved.vtan), saved.vtan.mean("theta", skipna=False))
    coefficient = periodic_fourier_coefficients(saved.harmonic_2).sel(azimuthal_wavenumber=2)
    expected = direct_coefficients(truth["harmonic_2"], saved.theta.values, 2)
    np.testing.assert_allclose(coefficient.isel(heightAboveGround=0), expected, atol=.01, rtol=0)
    plot = close_theta_for_plot(saved)
    assert plot.sizes["theta"] == saved.sizes["theta"] + 1
    np.testing.assert_allclose(plot.harmonic_2.isel(theta=0), plot.harmonic_2.isel(theta=-1))
    return {"product": path.name, "variables_preserved": len(result.variables),
            "origin_units_topology_preserved": True, "mean_fft_plotting_checked": True}


def run_analytic_example(output, *, figures=True):
    """Generate a small analytical vortex, exported samples and truth/error/mode plots."""
    output = Path(output).expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Example output must be fresh or empty")
    output.mkdir(parents=True, exist_ok=True)
    vortex = AnalyticVortex(inflow_max_ms=5.)
    result, truth, _, _ = project_fixture(vortex, 1000.)
    metrics = compare_fields(result, truth)
    checks = [{"name": f"{name}_rms", "ok": metrics[name]["rms"] < .05}
              for name in ("vrad", "vtan", "wind_speed")]
    report = {"fixture": vortex.parameters(), "metrics": metrics,
              "spectra": spectral_metrics(result, truth),
              "profiles": radial_profiles(result, truth),
              "serialization": serialization_and_diagnostics(vortex, output),
              "checks": checks, "passed": all(c["ok"] for c in checks)}
    atomic_json(output / "example.json", report)
    if figures:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(10, 8))
        radius = result.rr.values
        profile = report["profiles"]
        axes[0, 0].plot(radius, profile["vtan"]["truth"], label="direct truth")
        axes[0, 0].plot(radius, profile["vtan"]["actual"], "--", label="sampled")
        axes[0, 0].set(xlabel="radius (km)", ylabel="clockwise tangential wind (m/s)")
        for name in ("vrad", "vtan"):
            error = result[name].isel(time=0, heightAboveGround=0).values - truth[name][0]
            axes[0, 1].plot(radius[1:], np.sqrt(np.mean(error[1:]**2, axis=-1)), label=name)
        axes[0, 1].set(xlabel="radius (km)", ylabel="point-sampling RMS error (m/s)")
        ring = int(np.argmin(abs(radius * 1000 - vortex.radius_m)))
        for exact, label, style in ((False, "sampled", "o-"), (True, "direct truth", "x--")):
            coefficients = []
            for mode in (1, 2, 3):
                field = truth[f"harmonic_{mode}"][0] if exact else result[
                    f"harmonic_{mode}"].isel(time=0, heightAboveGround=0).values
                coefficients.append(direct_coefficients(field, result.theta.values, mode)[ring])
            coefficients = np.asarray(coefficients)
            axes[1, 0].plot([1, 2, 3], abs(coefficients), style, label=label)
            axes[1, 1].plot([1, 2, 3], -np.angle(coefficients) / [1, 2, 3], style, label=label)
        axes[1, 0].set(xlabel="azimuthal mode", ylabel="complex coefficient amplitude")
        axes[1, 1].set(xlabel="azimuthal mode", ylabel="peak direction clockwise from north (rad)")
        for axis in axes.flat:
            axis.legend()
        fig.tight_layout()
        fig.savefig(output / "vortex-diagnostics.png", dpi=150)
        plt.close(fig)
    return report


def run_polar_qualification(output, *, figures=True):
    output = Path(output).expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Qualification output must be fresh or empty")
    output.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    report = {"artifact_type": "polar_scientific_qualification", "started_at": utc_now(),
              "environment": environment_metadata(), "references": REFERENCES, "cases": [],
              "checks": [], "error_norm": "pointwise RMS/max on oracle-defined common target sets",
              "convergence_criterion": "p>=1.7 over the finest two useful intervals",
              "gate_source": "predeclared engineering criteria, not cyclone-paper thresholds"}
    scenarios = [
        (AnalyticVortex(), "rectilinear"),
        (AnalyticVortex(latitude=20., tangential_max_ms=-50.), "curvilinear"),
        (AnalyticVortex(inflow_max_ms=5.), "curvilinear"),
        (AnalyticVortex(latitude=60., tangential_max_ms=-50., inflow_max_ms=5.), "rectilinear"),
        (AnalyticVortex(longitude=179.6), "rectilinear"),
        (AnalyticVortex(kind="gaussian_vorticity"), "rectilinear"),
        (AnalyticVortex(kind="streamfunction"), "curvilinear"),
    ]
    for vortex, grid_kind in scenarios:
        minimum = 20000 if vortex.kind == "streamfunction" else 0
        case = refinement_case(vortex, grid_kind=grid_kind, minimum_radius_m=minimum)
        report["cases"].append(case)
        fields = ["smooth_scalar", "vtan"]
        if vortex.inflow_max_ms:
            fields.append("vrad")
        limits = {"smooth_scalar": 1e-6, "vtan": .05, "vrad": .05, "wind_speed": .05}
        checks = refinement_gates(case, order_fields=fields, rms_limits=limits)
        for check in checks:
            check["case_index"] = len(report["cases"]) - 1
        report["checks"].extend(checks)
        atomic_json(output / "qualification.json", report)
    report["centre_sensitivity"] = centre_sensitivity(
        AnalyticVortex(kind="gaussian_vorticity")
    ) + centre_sensitivity(AnalyticVortex(kind="streamfunction"))
    report["angular_sampling"] = angular_sweep(AnalyticVortex())
    report["subgrid_translations"] = subgrid_translations(AnalyticVortex())
    report["backend_equivalence"] = backend_equivalence(AnalyticVortex())
    report["clipped_boundary_errors"] = clipped_boundary_errors(AnalyticVortex())
    report["coverage"] = coverage_experiment(AnalyticVortex(), output)
    report["serialization"] = serialization_and_diagnostics(AnalyticVortex(), output)
    for row in report["centre_sensitivity"]:
        report["checks"].append({"name": "displaced_centre_independent_oracle",
                                 "ok": all(m["missing_required_points"] == 0
                                           for m in row["metrics"].values())})
        if row["source_spacing_m"] == 1000:
            for name in ("vrad", "vtan"):
                error = row["metrics"][name]["rms"]
                report["checks"].append({"name": f"displaced_{name}_finest_error",
                                         "value": error, "maximum_ms": .05,
                                         "ok": error is not None and error <= .05})
            for spectral in row["spectra"]:
                phase = spectral["phase_peak_direction_max_error_rad"]
                if phase is not None:
                    report["checks"].append({"name": "displaced_resolved_mode_phase",
                                             "value": phase, "maximum_rad": .02,
                                             "ok": phase <= .02})
    for row in report["angular_sampling"]:
        report["checks"].append({"name": "analytical_complex_harmonic_truth",
                                 "ok": max(row["analytical_harmonic_coefficient_errors"]) < 1e-10})
        for spectral in row["sampled_spectra"]:
            if spectral["field"].startswith("harmonic_"):
                report["checks"].append({"name": "sampled_complex_harmonic_error",
                                         "value": spectral["complex_rms_error"], "maximum": .01,
                                         "ok": spectral["complex_rms_error"] <= .01})
                phase = spectral["phase_peak_direction_max_error_rad"]
                report["checks"].append({"name": "sampled_harmonic_peak_direction",
                                         "value": phase, "maximum_rad": .01,
                                         "ok": phase is not None and phase <= .01})
    for index in range(3):
        coarse = report["subgrid_translations"][index]
        fine = report["subgrid_translations"][index + 3]
        for name in ("vrad", "vtan"):
            old, new = coarse["metrics"][name]["rms"], fine["metrics"][name]["rms"]
            report["checks"].append({"name": f"translated_{name}_refinement",
                                     "coarse_rms": old, "fine_rms": new,
                                     "ok": old is not None and new is not None and new < old})
    for region in ("interior", "boundary"):
        for row in report["clipped_boundary_errors"]:
            for name, metrics in row["regions"][region].items():
                report["checks"].append({"name": f"clipped_{region}_{name}_common_valid_set",
                                         "ok": metrics["missing_required_points"] == 0})
        coarse = report["clipped_boundary_errors"][0]["regions"][region]["vtan"]["rms"]
        fine = report["clipped_boundary_errors"][-1]["regions"][region]["vtan"]["rms"]
        report["checks"].append({"name": f"clipped_{region}_wind_refinement",
                                 "coarse_rms": coarse, "fine_rms": fine,
                                 "ok": fine is not None and coarse is not None and fine < coarse})
    report["passed"] = all(check["ok"] for check in report["checks"])
    report["duration_s"], report["finished_at"] = perf_counter() - started, utc_now()
    atomic_json(output / "qualification.json", report)
    atomic_json(output / "summary.json", qualification_summary(report))
    if figures:
        _qualification_figures(report, output)
    return report


def qualification_summary(report):
    """Compact numerical evidence; detailed profiles/complex coefficients remain separate."""
    rows = []
    for case in report["cases"]:
        fine = case["refinement"][-1]
        rows.append({"fixture": case["fixture"], "grid_kind": case["grid_kind"],
                     "finest_spacing_m": fine["source_spacing_m"],
                     "finest_metrics": fine["metrics"],
                     "finest_orders": fine.get("observed_orders", {}),
                     "rmw": fine["profiles"]["rmw"]})
    return {"passed": report["passed"], "check_count": len(report["checks"]),
            "failures": [c for c in report["checks"] if not c["ok"]],
            "references": report["references"], "cases": rows,
            "duration_s": report["duration_s"]}


def _qualification_figures(report, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for index, case in enumerate(report["cases"]):
        h = [row["source_spacing_m"] for row in case["refinement"]]
        errors = [row["metrics"]["vtan"]["rms"] for row in case["refinement"]]
        axes[0].loglog(h, errors, "o-", label=f"{index}: {case['fixture']['kind']}")
    axes[0].set(xlabel="source spacing (m)", ylabel="tangential RMS error (m/s)")
    axes[0].legend(fontsize=7)
    fine = report["cases"][0]["refinement"][-1]["profiles"]
    axes[1].plot(fine["radius_km"], fine["vtan"]["truth"], label="direct truth")
    axes[1].plot(fine["radius_km"], fine["vtan"]["actual"], "--", label="sampled")
    axes[1].set(xlabel="geodesic radius (km)", ylabel="clockwise tangential wind (m/s)")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(output / "convergence-and-profiles.png", dpi=150)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--example", action="store_true", help="Run the analytical vortex example")
    args = parser.parse_args(argv)
    runner = run_analytic_example if args.example else run_polar_qualification
    report = runner(args.output, figures=not args.no_figures)
    failures = [c for c in report["checks"] if not c["ok"]]
    print(f"Polar scientific qualification: {'PASS' if report['passed'] else 'FAIL'}; "
          f"{len(report['checks'])} checks, {len(failures)} failures")
    for failure in failures:
        print(failure)
    print(f"Report: {args.output / ('example.json' if args.example else 'qualification.json')}")
    return int(not report["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
