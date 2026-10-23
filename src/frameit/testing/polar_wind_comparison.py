"""Controlled wind point-method comparison; add --ci for the frozen BATSIRAI winds.

Independent manufactured truth separates interpolation, basis and centre effects.
Real-data differences are not truth errors. No production defaults are changed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path
from time import perf_counter

import numpy as np
import xarray as xr
from pyproj import Geod

from frameit.testing.analytic_vortices import AnalyticVortex, analytic_source, displaced_centre
from frameit.testing.artifacts import atomic_json, environment_metadata
from frameit.testing.datasets import load_ci_recipe, sha256_file, verify_ci_dataset
from frameit.testing.polar_qualification import project_fixture
from frameit.testing.polar_rainfall_ci import _GRID_KEYS, DATASET_ID, _decode_regular_ll
from frameit.testing.wind_point_methods import (
    METHODS,
    attach_profiles,
    profile_peak,
    sample_methods,
    structural_metrics,
    target_grid,
)


def _fixtures():
    return (
        {"id": "southern_swirl", "vortex": AnalyticVortex(), "grid_kind": "rectilinear"},
        {"id": "compact_northern_inflow", "vortex": AnalyticVortex(
            latitude=20., radius_m=12000., tangential_max_ms=-50., inflow_max_ms=5.),
            "grid_kind": "rectilinear"},
        {"id": "high_latitude_swirl", "vortex": AnalyticVortex(
            latitude=60., tangential_max_ms=-50.), "grid_kind": "rectilinear"},
        {"id": "dateline_curvilinear", "vortex": AnalyticVortex(longitude=179.6),
            "grid_kind": "curvilinear"},
        {"id": "asymmetric", "vortex": AnalyticVortex(), "grid_kind": "curvilinear",
            "perturbation": AnalyticVortex(kind="streamfunction")},
        {"id": "sharp_eyewall", "vortex": AnalyticVortex(radius_m=30000.),
            "grid_kind": "rectilinear", "profile": "lognormal", "log_width": .12},
    )


def evaluate_fixture(spec, lon, lat):
    """Direct kinematic source/target values; no interpolation/transport operators."""
    vortex = spec["vortex"]
    if spec.get("profile") == "lognormal":
        radius, _, bearing = vortex.polar_geometry(lon, lat)
        speed = np.zeros_like(radius)
        positive = radius > 0
        speed[positive] = vortex.tangential_max_ms*np.exp(
            -.5*(np.log(radius[positive]/vortex.radius_m)/spec["log_width"])**2)
        u, v = speed*np.cos(bearing), -speed*np.sin(bearing)
    else:
        fields = vortex.evaluate(lon, lat)
        u, v = fields["u"], fields["v"]
    if "perturbation" in spec:
        fields = spec["perturbation"].evaluate(lon, lat)
        u, v = u+fields["u"], v+fields["v"]
    return u, v


def fixture_source(spec, spacing):
    full = analytic_source(spec["vortex"], spacing, grid_kind=spec["grid_kind"],
                           extent_m=110000., alignment=(.17, -.23))
    u, v = evaluate_fixture(spec, full.longitude.values, full.latitude.values)
    full.u.data = u[None, None]
    full.v.data = v[None, None]
    return full


def independent_truth(spec, target, centre):
    u, v = evaluate_fixture(spec, target.lon.values, target.lat.values)
    _, back, _ = Geod(ellps="WGS84").inv(np.full(u.shape, centre[0]),
        np.full(u.shape, centre[1]), target.lon.values, target.lat.values)
    bearing = np.deg2rad(back+180)
    origin = np.broadcast_to(target.rr.values[:, None] == 0, u.shape)
    fields = {"u": u, "v": v, "wind_speed": np.hypot(u, v),
              "vrad": np.where(origin, np.nan, u*np.sin(bearing)+v*np.cos(bearing)),
              "vtan": np.where(origin, np.nan, u*np.cos(bearing)-v*np.sin(bearing))}
    return xr.Dataset({name: (("rr", "theta"), value, {"units": "m s-1"})
                       for name, value in fields.items()},
                      coords={"rr": target.rr.values, "theta": np.deg2rad(target.theta_deg.values)})


def _scores(result, reference, *, interpretation="independent analytical error", common=None):
    if interpretation == "independent analytical error":
        for name in ("u", "v", "vrad", "vtan", "wind_speed"):
            if not np.isfinite(reference[name].values[1:]).all():
                raise ValueError("Independent truth is invalid on a required analytical target")
    return {method: structural_metrics(result.sel(wind_method=method, drop=True), reference,
                                       interpretation=interpretation, required=common)
            for method in METHODS}


def _vector_rms(score):
    values = [score["fields"][name]["rms"] for name in ("u", "v")]
    return float(np.hypot(*values)) if all(value is not None for value in values) else None


def _compact_score(score):
    complex_values = [row["complex_rms_difference_ms"] for row in score["spectra"]]
    phase_values = [row["strong_peak_direction_max_difference_deg"] for row in score["spectra"]
                    if row["strong_peak_direction_max_difference_deg"] is not None]
    return {"vector_rms_ms": _vector_rms(score), "radial_rms_ms": score["fields"]["vrad"]["rms"],
            "tangential_rms_ms": score["fields"]["vtan"]["rms"],
            "rmw_difference_km": score["rmw_difference_km"],
            "peak_mean_tangential_difference_ms": score["peak_mean_tangential_difference_ms"],
            "point_max_speed_difference_ms": score["point_max_speed_difference_ms"],
            "max_complex_harmonic_rms_ms": max(complex_values)
            if all(value is not None for value in complex_values) else None,
            "max_strong_peak_direction_difference_deg": max(phase_values) if phase_values else None}


def _parity(full_source, spec, spacing, centre, result):
    production, _, _, _ = project_fixture(spec["vortex"], spacing, source=full_source,
        analysis_centre=centre, radial_resolution=1000, polar_n_theta=96,
        x_boxsize_km=160, y_boxsize_km=160,
        polar_variables={"heightAboveGround": {"variables": ["u", "v"]}})
    baseline = result.sel(wind_method="bilinear_components", drop=True)
    for name in ("u", "v", "vrad", "vtan", "wind_speed"):
        expected = production[name].isel(time=0, heightAboveGround=0)
        np.testing.assert_allclose(baseline[name], expected,
                                   rtol=1e-12, atol=1e-10, equal_nan=True)


def _native_parity(source, stamp, centre, result):
    from frameit.processing.polar.polar_proj import polar_project
    from frameit.testing.polar_qualification import qualification_settings

    full = source.rename(height="heightAboveGround").expand_dims(time=[stamp])
    track = xr.Dataset({"lon": ("time", [centre[0]]), "lat": ("time", [centre[1]])},
                       coords={"time": [stamp]})
    conf = qualification_settings(x_boxsize_km=120, y_boxsize_km=120, radial_resolution=1000,
        polar_n_theta=96, polar_variables={"heightAboveGround": {"variables": ["u", "v"]}})
    production, _ = polar_project({"heightAboveGround": full}, conf=conf, track=track)
    for name in ("u", "v", "vrad", "vtan", "wind_speed"):
        actual = result[name].sel(wind_method="bilinear_components", drop=True)
        expected = production["heightAboveGround"][name].isel(time=0).transpose(
            "heightAboveGround", "rr", "theta")
        np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-10, equal_nan=True)


def _export(result, path, *, truth=None, source="Independent manufactured wind"):
    from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf

    result = attach_profiles(result.copy(deep=True))
    if truth is not None:
        for name in ("u", "v", "vrad", "vtan", "wind_speed"):
            result[f"truth_{name}"] = truth[name]
    write_dataset_netcdf(result, path, product_type="polar", overwrite=False,
        metadata=ExportMetadata("wind-method-comparison", "Experimental wind point methods",
            "Strict joint stencils; Earth-relative velocities; no conservation claim",
            "FrameIt", source))
    with xr.open_dataset(path) as saved:
        for name in result.variables:
            xr.testing.assert_allclose(saved[name], result[name])
        assert saved.vrad.attrs["units"] == "m s-1"
        assert saved.attrs["wind_reference_frame"] == "earth"
        assert not saved.attrs["theta_closed"]
    return path.name


def run_analytical(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {"fixtures": [], "centre_sensitivity": [], "angular_sampling": [],
              "coverage_experiments": [], "checks": [], "products": []}
    for spec in _fixtures():
        vortex = spec["vortex"]
        centre = (vortex.longitude, vortex.latitude)
        target = target_grid(centre)
        truth = independent_truth(spec, target, centre)
        records = []
        for spacing in (4000., 2000., 1000.):
            full = fixture_source(spec, spacing)
            source = full.isel(time=0, heightAboveGround=0, drop=True)
            result, timing = sample_methods(source, target)
            scores = _scores(result, truth)
            records.append({"source_spacing_m": spacing, "scores": scores, "operators": timing})
            if spacing == 1000:
                _parity(full, spec, spacing, centre, result)
                report["checks"].append({"name": spec["id"]+"_production_bilinear_parity",
                                         "ok": True})
                result.attrs["fixture_parameters"] = vortex.parameters()
                report["products"].append(_export(
                    result, output / f"{spec['id']}-1000m.nc", truth=truth))
        for method in METHODS:
            coarse, fine = records[0]["scores"][method], records[-1]["scores"][method]
            for name in ("u", "v", "vrad", "vtan", "wind_speed"):
                values = fine["fields"][name]
                report["checks"].append({"name": f"{spec['id']}_{method}_{name}_required_set",
                    "ok": values["missing_required_points"] == 0 and values["required_points"] > 0})
            vector_coarse = _vector_rms(coarse)
            vector_fine = _vector_rms(fine)
            report["checks"].append({"name": f"{spec['id']}_{method}_vector_refinement",
                                     "coarse_ms": vector_coarse, "fine_ms": vector_fine,
                                     "ok": vector_fine is not None and vector_coarse is not None
                                     and vector_fine < vector_coarse})
            report["checks"].append({"name": f"{spec['id']}_{method}_finest_vector_bound",
                                     "value_ms": vector_fine, "maximum_ms": .5,
                                     "ok": vector_fine is not None and vector_fine < .5})
            report["checks"].append({"name": f"{spec['id']}_{method}_sampled_rmw",
                "difference_km": fine["rmw_difference_km"], "maximum_km": 1.,
                "ok": fine["rmw_difference_km"] is not None and fine["rmw_difference_km"] <= 1.})
            for spectral in fine["spectra"]:
                error = spectral["complex_rms_difference_ms"]
                phase = spectral["strong_peak_direction_max_difference_deg"]
                report["checks"].append({"name": f"{spec['id']}_{method}_resolved_spectrum",
                    "field": spectral["field"], "mode": spectral["mode"],
                    "complex_rms_ms": error, "maximum_complex_rms_ms": .25,
                    "strong_peak_direction_difference_deg": phase, "maximum_phase_deg": 5.,
                    "ok": error is not None and error < .25
                    and spectral["strong_phase_required_rings"]
                    == spectral["strong_phase_eligible_rings"]
                    and (phase is None or phase < 5.)})
        report["fixtures"].append({"id": spec["id"], "parameters": vortex.parameters(),
            "grid_kind": spec["grid_kind"], "profile": spec.get("profile", "geodesic"),
            "log_width": spec.get("log_width"),
            "perturbation": spec["perturbation"].parameters() if "perturbation" in spec else None,
            "source_alignment_cells": [.17, -.23], "refinement": records})
        atomic_json(output / "analytical.json", report)
    spec = next(item for item in _fixtures() if item["id"] == "asymmetric")
    centre = (spec["vortex"].longitude, spec["vortex"].latitude)
    centred_truth = independent_truth(spec, target_grid(centre), centre)
    centred_peak = profile_peak(centred_truth.vtan.values, centred_truth.rr.values)
    for spacing in (4000., 1000.):
        source = fixture_source(spec, spacing).isel(time=0, heightAboveGround=0, drop=True)
        for fraction in (0., .05, .1, .25):
            for direction in ((0.,) if fraction == 0 else (0., 90.)):
                displaced = displaced_centre(spec["vortex"],
                                              fraction*spec["vortex"].radius_m, direction)
                target = target_grid(displaced)
                truth = independent_truth(spec, target, displaced)
                result, _ = sample_methods(source, target)
                scores = _scores(result, truth)
                peak = profile_peak(truth.vtan.values, truth.rr.values)
                for method, score in scores.items():
                    report["checks"].append({"name": "centre_sweep_required_targets",
                        "method": method, "spacing_m": spacing, "offset_fraction": fraction,
                        "ok": all(field["missing_required_points"] == 0
                                  and field["required_points"] > 0
                                  for field in score["fields"].values())})
                report["centre_sensitivity"].append({"source_spacing_m": spacing,
                    "offset_reference_radius_fraction": fraction, "offset_bearing_deg": direction,
                    "analysis_centre_lon_lat": list(displaced), "scores": scores,
                    "truth_rmw_response_km": peak["rmw_km"]-centred_peak["rmw_km"],
                    "truth_radial_rms_ms": float(np.sqrt(np.mean(truth.vrad.values[1:]**2)))})
    source = fixture_source(spec, 1000.).isel(time=0, heightAboveGround=0, drop=True)
    for count in (16, 32):
        target = target_grid(centre, n_theta=count)
        truth = independent_truth(spec, target, centre)
        result, _ = sample_methods(source, target)
        for method, score in _scores(result, truth).items():
            report["checks"].append({"name": "angular_sweep_required_targets", "method": method,
                "n_theta": count, "ok": all(field["missing_required_points"] == 0
                    and field["required_points"] > 0 for field in score["fields"].values())})
        report["angular_sampling"].append({"n_theta": count, "source_spacing_m": 1000.,
            "scores": _scores(result, truth), "truth_sampling_difference_from_96_angles_ms": {
                f"{name}_mode_{mode}": float(np.sqrt(np.mean(abs(
                    np.mean(truth[name].values[1:]*np.exp(-1j*mode*truth.theta.values), axis=-1)
                    - np.mean(centred_truth[name].values[1:]*np.exp(
                        -1j*mode*centred_truth.theta.values), axis=-1))**2)))
                for name in ("vrad", "vtan") for mode in (1, 2, 3)}})
    source = fixture_source(spec, 2000.).isel(time=0, heightAboveGround=0, drop=True)
    for epoch in (0, 1):
        masked = source.copy(deep=True)
        masked.u.values[:, 50+epoch:53+epoch] = np.nan
        masked.v.values[48+epoch:51+epoch, :] = np.nan
        # Finite source geometry is clipped, never padded or extrapolated.
        masked = masked.isel(x_box=slice(0, 70))
        result, _ = sample_methods(masked, target_grid(centre))
        np.testing.assert_array_equal(np.isfinite(result.u), result.vector_valid.astype(bool))
        np.testing.assert_array_equal(np.isfinite(result.v), result.vector_valid.astype(bool))
        report["checks"].append({"name": "coverage_strict_joint_mask", "epoch": epoch, "ok": True})
        report["coverage_experiments"].append({"synthetic_mask_epoch": epoch,
            "source_clip": "first 70 x points", "source_mask": "distinct U column and V row gaps",
            "methods": {method: {"valid_vector_points": int(
                result.vector_valid.sel(wind_method=method).sum()),
                "mapped_points": int(result.geometry_mapped.sel(wind_method=method).sum()),
                "profile_peak": profile_peak(result.vtan.sel(wind_method=method).values,
                                              result.rr.values)}
                for method in METHODS}})
    report["passed"] = all(check["ok"] for check in report["checks"])
    atomic_json(output / "analytical.json", report)
    return report


def read_ci_winds(path, expected_time):
    import eccodes as ec

    heights = (100, 750)
    selected = {"u": {}, "v": {}}
    metadata, grid, radius = [], None, None
    keys = ("paramId", "shortName", "units", "uvRelativeToGrid", "typeOfLevel", "level",
            "stepType", "stepUnits", "startStep", "endStep", "dataDate", "dataTime", *_GRID_KEYS)
    with Path(path).open("rb") as stream:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                parameter = ec.codes_get(handle, "paramId")
                if (parameter not in (131, 132)
                        or ec.codes_get(handle, "typeOfLevel") != "heightAboveGround"
                        or ec.codes_get(handle, "level") not in heights):
                    continue
                info = {key: ec.codes_get(handle, key) for key in keys}
                name = "u" if parameter == 131 else "v"
                if (info["shortName"] != name or info["units"].replace("**", "") != "m s-1"
                        or info["uvRelativeToGrid"] != 0 or info["stepType"] != "instant"
                        or info["stepUnits"] != 1 or info["startStep"] != info["endStep"]):
                    raise ValueError(
                        "CI comparison requires declared instantaneous Earth-relative m/s winds")
                reference = datetime.strptime(f"{info['dataDate']:08d}{info['dataTime']:04d}",
                                              "%Y%m%d%H%M")
                stamp = np.datetime64(reference+timedelta(hours=info["endStep"]), "ns")
                if stamp != np.datetime64(expected_time, "ns"):
                    raise ValueError("Wind valid time does not match the CI recipe")
                if info["level"] in selected[name]:
                    raise ValueError("Ambiguous CI wind component/height record")
                current, values = _decode_regular_ll(ec, handle, info)
                if grid is None:
                    grid, radius = current, float(info["radius"])
                elif not grid.equals(current) or radius != info["radius"]:
                    raise ValueError("CI wind component grids or Earth models differ")
                selected[name][info["level"]] = values
                metadata.append(info)
            finally:
                ec.codes_release(handle)
    if any(set(selected[name]) != set(heights) for name in selected):
        raise ValueError("Required CI U/V height pairs are missing")
    source = xr.Dataset({name: (("height", "y_box", "x_box"),
        np.stack([selected[name][height] for height in heights]),
        {"units": "m s-1", "wind_reference_frame": "earth", "GRIB_uvRelativeToGrid": 0})
        for name in selected}, coords={"height": list(heights), "y_box": grid.y.values,
            "x_box": grid.x.values, "longitude": (("y_box", "x_box"), grid.lon.values),
            "latitude": (("y_box", "x_box"), grid.lat.values)})
    source.height.attrs.update(units="m", long_name="height above ground",
                                height_reference="ground")
    return {"source": source, "time": stamp, "metadata": metadata,
            "source_file": Path(path).name, "source_sphere_radius_m": radius}


def run_ci(output, root=None):
    root = (Path(str(resources.files("frameit.testing").joinpath("ci_dataset")))
            if root is None else Path(root)).resolve()
    output = Path(output).resolve()
    if root == output or root in output.parents or output in root.parents:
        raise ValueError("CI wind output and source fixture must not overlap")
    fixture = verify_ci_dataset(root, dataset_ids=[DATASET_ID])
    recipe = load_ci_recipe()["datasets"][DATASET_ID]
    records = [read_ci_winds(root / DATASET_ID / name, stamp)
               for name, stamp in zip(recipe["files"], recipe["times"], strict=True)]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {"fixture_identity": fixture["identity"], "cases": [], "products": [],
        "interpretation": "native differences from component bilinear, not truth errors",
        "source_files": [{key: r[key] for key in ("path", "bytes", "sha256")}
                         for r in fixture["files"]],
        "source_metadata": [r["metadata"] for r in records],
        "settings": {"fixed_center_lat_lon": recipe["fixed_center_lat_lon"],
            "rmax_m": 60000., "radial_step_m": 1000., "n_theta": 96,
            "heights_above_ground_m": [100, 750],
            "moving_longitude_offsets_deg": [-.15, -.075, 0., .075, .15],
            "clipped_longitude_offset_deg": .85,
            "synthetic_masks": "U x columns 30+i:35+i; V y rows 20+i:23+i at recipe index i"}}
    lat0, lon0 = recipe["fixed_center_lat_lon"]
    for case in ("fixed", "moving", "clipped", "masked"):
        pieces, rows = [], []
        for index, record in enumerate(records):
            offset = .85 if case == "clipped" else (
                float(np.linspace(-.15, .15, len(records))[index]) if case == "moving" else 0.)
            centre = (lon0+offset, lat0)
            source = record["source"].copy(deep=True)
            if case == "masked":
                source.u.values[:, :, 30+index:35+index] = np.nan
                source.v.values[:, 20+index:23+index, :] = np.nan
            result, timing = sample_methods(source, target_grid(centre, rmax_m=60000.))
            if case == "fixed" and index == 0:
                _native_parity(source, record["time"], centre, result)
                report["production_bilinear_parity_checked"] = True
            common = result.polar_vector_valid.values.astype(bool).all(axis=0)
            if case in {"fixed", "moving"} and not common[:, 1:, :].all():
                raise ValueError("Full-footprint CI comparison lost required common support")
            heights = []
            for height in result.height.values:
                selected = result.sel(height=height, drop=True)
                baseline = selected.sel(wind_method="bilinear_components", drop=True)
                required = common[list(result.height.values).index(height)]
                heights.append({"height_m": int(height),
                    "common_polar_points": int(required.sum()),
                    "method_valid_points": {method: int(
                        selected.polar_vector_valid.sel(wind_method=method).sum())
                                            for method in METHODS},
                    "differences": _scores(selected, baseline,
                        interpretation="common-support difference from component bilinear",
                        common=required)})
            rows.append({"time": str(record["time"]), "centre_lon_lat": list(centre),
                         "heights": heights, "operators": timing})
            result = result.expand_dims(time=[record["time"]])
            result = result.assign_coords(center_lon=("time", [centre[0]]),
                                           center_lat=("time", [centre[1]]))
            result["source_file"] = ("time", [record["source_file"]])
            result.attrs.update(source_sphere_radius_m=record["source_sphere_radius_m"],
                case_id=case, centre_policy=("prescribed sensitivity trajectory, not tracker"
                    if case == "moving" else "declared fixed footprint"),
                source_mask_policy="distinct synthetic U/V gaps" if case == "masked"
                else "stored GRIB bitmaps", temporal_kind="instantaneous")
            pieces.append(result)
        product = xr.concat(pieces, dim="time", data_vars="all", coords="different",
                            compat="equals", join="exact", combine_attrs="drop_conflicts")
        product.height.attrs.update(units="m", height_reference="ground")
        for key in ("center_definition", "center_lon", "center_lat"):
            product.attrs.pop(key, None)
        report["products"].append(_export(product, output / f"batsirai-wind-{case}.nc",
                                            source="Frozen BATSIRAI Earth-relative GRIB winds"))
        report["cases"].append({"id": case, "times": rows, "independent_reader_checked": True})
        atomic_json(output / "ci.json", report)
    for item in report["source_files"]:
        if sha256_file(root / item["path"]) != item["sha256"]:
            raise ValueError("CI source content changed during wind comparison")
    report["passed"] = True
    report["source_content_unchanged"] = True
    atomic_json(output / "ci.json", report)
    return report


def run_comparison(output, *, ci=False):
    from frameit.processing.polar.performance import process_peak_rss_bytes

    output = Path(output).expanduser().resolve()
    root = Path(str(resources.files("frameit.testing").joinpath("ci_dataset"))).resolve()
    if root == output or root in output.parents or output in root.parents:
        raise ValueError("Wind comparison output and source fixture must not overlap")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Wind comparison output must be fresh or empty")
    output.mkdir(parents=True, exist_ok=True)
    report = {"artifact_type": "polar_wind_method_comparison", "maturity": "experimental",
              "status": "RUNNING", "passed": False, "environment": environment_metadata(),
              "settings": {"methods": list(METHODS), "source_spacings_m": [4000, 2000, 1000],
                  "target_rmax_m": 80000, "target_radial_step_m": 1000, "n_theta": 96,
                  "source_extent_m": 110000, "source_alignment_cells": [.17, -.23],
                  "centre_offset_reference_fractions": [0., .05, .1, .25],
                  "centre_directions_deg": [0., 90.], "centre_spacings_m": [4000, 1000],
                  "angular_counts": [16, 32, 96],
                  "transport": "WGS84 shortest-geodesic parallel transport",
                  "velocity_frame": "Earth-relative, no storm-motion subtraction",
                  "masks": "strict joint finite nonzero-weight stencil, no renormalized gaps"}}
    report["environment"]["execution_backend"] = "in_process_sequential"
    started = perf_counter()
    atomic_json(output / "comparison.json", report)
    try:
        report["analytical"] = {"report": "analytical/analytical.json", "status": "RUNNING"}
        atomic_json(output / "comparison.json", report)
        analytical = run_analytical(output / "analytical")
        report["analytical"] = {"report": "analytical/analytical.json",
            "passed": analytical["passed"],
            "checks": len(analytical["checks"]), "fixtures": len(analytical["fixtures"]),
            "fine_results": {fixture["id"]: {method: _compact_score(score)
                for method, score in fixture["refinement"][-1]["scores"].items()}
                for fixture in analytical["fixtures"]}}
        if ci:
            report["ci"] = {"report": "ci/ci.json", "status": "RUNNING", "passed": False}
            atomic_json(output / "comparison.json", report)
            native = run_ci(output / "ci")
            report["ci"] = {"report": "ci/ci.json", "passed": native["passed"],
                             "cases": len(native["cases"])}
        passed = analytical["passed"] and (not ci or report["ci"]["passed"])
        report.update(passed=passed, status="PASS" if passed else "FAILED",
                      duration_s=perf_counter()-started,
                      process_lifetime_peak_rss_bytes=process_peak_rss_bytes())
        atomic_json(output / "comparison.json", report)
        return report
    except Exception as exc:
        for stage in ("analytical", "ci"):
            if report.get(stage, {}).get("status") == "RUNNING":
                report[stage].update(status="FAILED", passed=False)
        report.update(status="FAILED", passed=False, reason=f"{type(exc).__name__}: {exc}",
                      duration_s=perf_counter()-started)
        atomic_json(output / "comparison.json", report)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ci", action="store_true", help="Also compare bundled BATSIRAI U/V winds")
    args = parser.parse_args()
    report = run_comparison(args.output, ci=args.ci)
    print(f"Wind method comparison: {'PASS' if report['passed'] else 'FAIL'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
