"""Experimental accumulated-scalar pilots on the read-only AROME/BATSIRAI fixture.

This declares midpoint analysis cells on the stored GRIB regular_ll grid. It
does not assert that postprocessed GRIB values are native-model cell means.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path
from time import perf_counter

import numpy as np
import xarray as xr

from frameit.testing.artifacts import atomic_json, environment_metadata
from frameit.testing.datasets import load_ci_recipe, sha256_file, verify_ci_dataset

DATASET_ID = "AROME/BATSIRAI"
PARAM_ID = 235015
BOUNDS_POLICY = "regular_ll_midpoint_analysis_cells_great_circle_edges"
SPATIAL_INTERPRETATION = "declared_piecewise_constant_analysis_cell_means_not_native_model_verified"
FOOTPRINT_MEANING = (
    "cumulative rain within each snapshot footprint, not a storm-following accumulation")


@dataclass(frozen=True)
class _Quantity:
    parameter_id: int
    short_name: str
    field_units: str
    integral_units: str
    integral_name: str
    metric_suffix: str
    description: str
    nonnegative: bool = False

    @property
    def footprint_meaning(self):
        if self.short_name == "tirf":
            return FOOTPRINT_MEANING
        return ("source-signed cumulative surface heat exchange within each snapshot footprint; "
                "not heat content or a storm-following accumulation")


_QUANTITIES = {
    "tirf": _Quantity(PARAM_ID, "tirf", "kg m-2", "kg", "mass", "kg_m2",
                      "time integral of rain flux", nonnegative=True),
    "sshf": _Quantity(146, "sshf", "J m-2", "J", "energy", "J_m2",
                      "time-integrated surface sensible heat net flux"),
    "slhf": _Quantity(147, "slhf", "J m-2", "J", "energy", "J_m2",
                      "time-integrated surface latent heat net flux"),
}

_GRID_KEYS = ("gridType", "Ni", "Nj", "shapeOfTheEarth", "radius", "jPointsAreConsecutive",
              "alternativeRowScanning", "numberOfMissing")


def _midpoint_edges(values):
    values = np.asarray(values, dtype=float)
    differences = np.diff(values)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all() or not (
        np.all(differences > 0) or np.all(differences < 0)
    ) or not np.allclose(differences, differences[0], rtol=0, atol=1e-9):
        raise ValueError("CI scalar pilot requires finite, monotone, uniform regular_ll axes")
    return np.concatenate(([values[0] - differences[0]/2],
                           (values[:-1]+values[1:])/2, [values[-1] + differences[-1]/2]))


def _analysis_grid(longitude, latitude):
    if longitude.shape != latitude.shape or longitude.ndim != 2:
        raise ValueError("GRIB geography must have matching (Nj, Ni) shapes")
    longitude = np.rad2deg(np.unwrap(np.deg2rad(longitude), axis=1))
    if not np.allclose(longitude, longitude[:1, :], rtol=0, atol=1e-10) or not np.allclose(
        latitude, latitude[:, :1], rtol=0, atol=1e-10
    ):
        raise ValueError("CI scalar pilot supports only rectilinear regular_ll geography")
    lon_b, lat_b = np.meshgrid(_midpoint_edges(longitude[0]), _midpoint_edges(latitude[:, 0]))
    result = xr.Dataset({"lon": (("y", "x"), longitude), "lat": (("y", "x"), latitude),
                         "lon_b": (("y_b", "x_b"), lon_b),
                         "lat_b": (("y_b", "x_b"), lat_b)},
                        coords={"y": np.arange(latitude.shape[0]),
                                "x": np.arange(latitude.shape[1])})
    for name in ("lon", "lon_b"):
        result[name].attrs["units"] = "degrees_east"
    for name in ("lat", "lat_b"):
        result[name].attrs["units"] = "degrees_north"
    result.attrs["bounds_policy"] = BOUNDS_POLICY
    return result


def _accumulation_times(metadata, *, quantity="tirf"):
    spec = _QUANTITIES[quantity]
    accepted_units = {spec.field_units, spec.field_units.replace("m-2", "m**-2")}
    if metadata["paramId"] != spec.parameter_id or metadata["shortName"] != spec.short_name or (
        metadata["typeOfLevel"] != "surface" or metadata["stepType"] != "accum"
        or metadata["typeOfStatisticalProcessing"] != 1
        or metadata["units"] not in accepted_units
        or metadata["stepUnits"] != 1 or metadata["startStep"] != 0
        or metadata["endStep"] <= 0
    ):
        raise ValueError(
            f"Expected surface {quantity} ({spec.parameter_id}), {spec.field_units}, "
            "accumulated from hour zero in hours")
    reference = datetime.strptime(f"{metadata['dataDate']:08d}{metadata['dataTime']:04d}",
                                  "%Y%m%d%H%M")
    end = reference + timedelta(hours=metadata["endStep"])
    return np.datetime64(reference, "ns"), np.datetime64(end, "ns")


def _decode_regular_ll(ec, handle, metadata):
    """Read-only common geometry/bitmap decoding for the explicit CI scalar pilots."""
    if metadata["gridType"] != "regular_ll" or metadata["shapeOfTheEarth"] != 6:
        raise ValueError("CI scalar pilot requires regular_ll on the declared GRIB sphere")
    if metadata["jPointsAreConsecutive"] or metadata["alternativeRowScanning"]:
        raise ValueError("Unsupported GRIB scanning order for CI scalar pilot")
    shape = (int(metadata["Nj"]), int(metadata["Ni"]))
    longitude = ec.codes_get_array(handle, "longitudes").reshape(shape)
    latitude = ec.codes_get_array(handle, "latitudes").reshape(shape)
    values = ec.codes_get_values(handle).reshape(shape)
    bitmap = (ec.codes_get_array(handle, "bitmap").reshape(shape).astype(bool)
              if ec.codes_get(handle, "bitmapPresent") else np.ones(shape, dtype=bool))
    if int((~bitmap).sum()) != metadata["numberOfMissing"]:
        raise ValueError("GRIB bitmap and missing-value count disagree")
    if not np.isfinite(values[bitmap]).all():
        raise ValueError("Scalar must be finite where the bitmap is valid")
    return _analysis_grid(longitude, latitude), np.where(bitmap, values, np.nan)


def read_rainfall(path, expected_time):
    """Compatibility entry point for the original rainfall-only experiment."""
    return read_accumulated_scalar(path, expected_time, quantity="tirf")


def read_accumulated_scalar(path, expected_time, *, quantity):
    """Read one explicitly selected scalar with its source sign and time bounds.

    No cfgrib index or other cache is written alongside source files. A missing
    field is returned explicitly; only the preset's time-zero absence is allowed.
    """
    import eccodes as ec

    spec = _QUANTITIES[quantity]
    keys = ("paramId", "shortName", "units", "typeOfLevel", "stepType", "stepUnits",
            "startStep", "endStep", "typeOfStatisticalProcessing", "dataDate", "dataTime",
            *_GRID_KEYS)
    selected = None
    with Path(path).open("rb") as stream:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                if ec.codes_get(handle, "paramId") != spec.parameter_id:
                    continue
                if selected is not None:
                    raise ValueError(f"Ambiguous {quantity} records in {Path(path).name}")
                metadata = {key: ec.codes_get(handle, key) for key in keys}
                start, end = _accumulation_times(metadata, quantity=quantity)
                if end != np.datetime64(expected_time, "ns"):
                    raise ValueError("Scalar accumulation end does not match the CI recipe time")
                grid, values = _decode_regular_ll(ec, handle, metadata)
                if spec.nonnegative and np.any(values[np.isfinite(values)] < 0):
                    raise ValueError(
                        "Accumulated rain must be nonnegative where the bitmap is valid")
                field = xr.DataArray(values, dims=("y", "x"), coords={"y": grid.y, "x": grid.x},
                                     name=quantity, attrs={"units": spec.field_units,
                                     "long_name": spec.description,
                                     "cell_methods": "time: sum",
                                     "GRIB_paramId": spec.parameter_id})
                selected = {"grid": grid, "field": field, "metadata": metadata,
                            "start": start, "end": end, "source_file": Path(path).name}
            finally:
                ec.codes_release(handle)
    return selected


def _presets():
    return (
        {"id": "fixed", "radial_step_m": 10000., "azimuth_count": 24},
        {"id": "moving", "radial_step_m": 10000., "azimuth_count": 24},
        {"id": "coarse", "radial_step_m": 20000., "azimuth_count": 12},
        {"id": "clipped", "radial_step_m": 10000., "azimuth_count": 24},
        {"id": "masked", "radial_step_m": 10000., "azimuth_count": 24},
    )


def _combine_snapshots(pieces, times, source_files):
    """Join fixed-axis polar geometry while retaining time-varying coordinates."""
    static_names = ("radius_bounds", "azimuth_bounds", "subcell_owner")
    static = pieces[0][list(static_names)].reset_coords(drop=True)
    dynamic = []
    for piece, stamp in zip(pieces, times, strict=True):
        item = piece.drop_vars(list(static_names)).expand_dims(time=[stamp])
        item = item.assign_coords(lon=piece.lon.expand_dims(time=[stamp]),
                                  lat=piece.lat.expand_dims(time=[stamp]))
        item["center_lon"] = ("time", [piece.attrs["center_lon"]], {"units": "degrees_east"})
        item["center_lat"] = ("time", [piece.attrs["center_lat"]], {"units": "degrees_north"})
        item["geometry_signature"] = ("time", [piece.attrs["geometry_sha256"]])
        dynamic.append(item)
    product = xr.concat(dynamic, dim="time", data_vars="all", coords="minimal", compat="equals",
                        join="exact", combine_attrs="drop_conflicts")
    product = xr.merge([product, static], compat="equals")
    product["source_file"] = ("time", source_files)
    for name in ("center_lon", "center_lat", "geometry_sha256", "construction_s"):
        product.attrs.pop(name, None)
    return product


def _combine_products(pieces, records, *, quantity="tirf"):
    spec = _QUANTITIES[quantity]
    product = _combine_snapshots(pieces, [r["end"] for r in records],
                                 [r["source_file"] for r in records])
    product["time_bounds"] = (("time", "bounds"),
                               np.array([[r["start"], r["end"]] for r in records]))
    product.time.attrs.update(bounds="time_bounds", standard_name="time",
                              long_name="end of source cumulative rain interval")
    units = "hours since " + np.datetime_as_string(records[0]["start"], unit="s").replace("T", " ")
    for name in ("time", "time_bounds"):
        product[name].encoding.update(units=units, calendar="proleptic_gregorian")
    product["accumulation_end_hour"] = ("time", [r["metadata"]["endStep"] for r in records],
                                         {"units": "h"})
    for name in ("cell_mean", "covered_area_mean"):
        product[name].attrs.update(units=spec.field_units, cell_methods="time: sum area: mean")
    product.covered_area_integral.attrs.update(
        units=spec.integral_units, cell_methods="time: sum area: sum",
        long_name=f"accumulated {spec.integral_name} over valid input-grid overlap")
    product.attrs.update(
        bounds_policy=BOUNDS_POLICY, source_spatial_interpretation=SPATIAL_INTERPRETATION,
        footprint_meaning=spec.footprint_meaning, GRIB_paramId=spec.parameter_id,
        temporal_processing="source cumulative intervals retained; no deaccumulation",
        source_sign_policy="stored GRIB signs preserved; no direction conversion or clipping")
    return product


def _check_reopened(path, expected, *, quantity="tirf"):
    """Use an ordinary reader, including values, time bounds and area metadata."""
    with xr.open_dataset(path) as saved:
        for name in expected.variables:
            xr.testing.assert_allclose(saved[name], expected[name])
        if saved.time.attrs.get("bounds") != "time_bounds":
            raise ValueError("Reload lost accumulation bounds")
        if saved.covered_area_integral.attrs.get("units") != _QUANTITIES[quantity].integral_units:
            raise ValueError("Reload lost accumulated-integral units")
        if saved.attrs.get("source_spatial_interpretation") != SPATIAL_INTERPRETATION:
            raise ValueError("Reload lost the declared spatial interpretation")


def _compare_reconstructions(source, field, cells, reference_integral, *, quantity="tirf"):
    """Same stored input, different reconstructions; no physical accuracy oracle."""
    import xesmf as xe

    from frameit.testing.polar_cell_comparison import bilinear_cell_average

    spec = _QUANTITIES[quantity]
    target = xr.Dataset({"lon": ("locations", cells.lon.values.ravel()),
                         "lat": ("locations", cells.lat.values.ravel())})
    point = xe.Regridder(source, target, "bilinear", locstream_out=True,
                         unmapped_to_nan=True)(field).values.reshape(cells.cell_area.shape)
    average = bilinear_cell_average(source, field, cells)
    finer_average = bilinear_cell_average(source, field, cells, order=8)
    common = cells.full_cell_valid.values.astype(bool) & np.isfinite(average) & np.isfinite(point)
    if not common.all():
        raise ValueError("Fixed/coarse comparison requires complete common interpolation support")
    cells["bilinear_point_sample"] = (cells.cell_mean.dims, point, {"units": spec.field_units,
        "cell_methods": "time: sum",
        "long_name": "point reconstruction at the interval midpoint, not a cell mean"})
    cells["bilinear_area_average"] = (cells.cell_mean.dims, average, {"units": spec.field_units,
        "cell_methods": "time: sum area: mean", "cell_measures": "area: cell_area"})
    reference = float(reference_integral.sum())
    area_integral = float(np.sum(average*cells.cell_area.values))
    midpoint_integral = float(np.sum(point*cells.cell_area.values))
    return {"interpretation": "input-cell reconstruction differences, not physical truth errors",
            "local_difference_norm": "unweighted RMS over full polar cells",
            f"bilinear_cell_mean_difference_rms_{spec.metric_suffix}": float(np.sqrt(np.mean(
                (average - cells.cell_mean.values)**2))),
            "bilinear_area_budget_relative_difference": (
                area_integral/reference - 1 if reference else None),
            "bilinear_midpoint_budget_relative_difference": (
                midpoint_integral/reference - 1 if reference else None),
            f"bilinear_quadrature_max_difference_{spec.metric_suffix}": float(
                np.max(abs(average-finer_average)))}


def _integral_errors(actual, expected, absolute_contributions):
    """Check each signed cell against absolute source contributions, not its net."""
    error = abs(actual - expected)
    np.testing.assert_array_less(error, 1. + 2e-7*absolute_contributions)
    return error


def run_ci_rainfall(output, *, data_root=None):
    """Execute the original, opt-in rain-mass CI preset."""
    return run_ci_scalar(output, quantity="tirf", data_root=data_root)


def run_ci_scalar(output, *, quantity, data_root=None):
    """Execute one of the three declared accumulated-scalar CI presets."""
    from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf
    from frameit.processing.polar.conservative import ConservativePolarPlan
    from frameit.processing.polar.performance import process_peak_rss_bytes
    from frameit.testing.polar_cell_comparison import independent_overlap_sparse

    spec = _QUANTITIES[quantity]
    rain = quantity == "tirf"
    root = (Path(str(resources.files("frameit.testing").joinpath("ci_dataset")))
            if data_root is None else Path(data_root)).resolve()
    output = Path(output).expanduser().resolve()
    if output == root or root in output.parents or output in root.parents:
        raise ValueError("CI inputs and pilot outputs must not overlap")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("CI scalar output must be fresh or empty")
    fixture = verify_ci_dataset(root, dataset_ids=[DATASET_ID])
    recipe = load_ci_recipe()["datasets"][DATASET_ID]
    output.mkdir(parents=True, exist_ok=True)
    report = {"artifact_type": "polar_rainfall_ci" if rain else "polar_accumulated_scalar_ci",
              "quantity": quantity, "maturity": "experimental",
              "status": "RUNNING", "passed": False, "environment": environment_metadata(),
              "fixture_identity": fixture["identity"],
              "fixture_manifest_sha256": fixture["manifest_sha256"],
              "source_files": [{key: r[key] for key in ("path", "bytes", "sha256")}
                               for r in fixture["files"]],
              "bounds_policy": BOUNDS_POLICY,
              "source_spatial_interpretation": SPATIAL_INTERPRETATION,
              "footprint_meaning": spec.footprint_meaning,
              "source_sign_policy": (
                  "stored GRIB signs preserved; no direction conversion or clipping"),
              "excluded": [], "cases": [], "products": [],
              "settings": {"parameter_id": spec.parameter_id, "rmax_m": 60000.,
                           "max_arc_step_deg": 2.5, "presets": list(_presets()),
                           "integral_relative_tolerance": 2e-7,
                           "integral_absolute_tolerance": 1., "integral_units": spec.integral_units,
                           "tolerance_scale": "per-cell overlap integral of absolute source values",
                           "fixed_center_lat_lon": recipe["fixed_center_lat_lon"],
                           "moving_longitude_offsets_deg": [-.15, -.05, .05, .15],
                           "clipped_longitude_offset_deg": .85,
                           "synthetic_mask": {"axis": "x", "initial_start": 30,
                                              "width": 5, "shift_per_time": 1}},
              "checks": []}
    if rain:
        report["settings"].update(mass_relative_tolerance=2e-7, mass_absolute_tolerance_kg=1.)
    atomic_json(output / "comparison.json", report)
    started = perf_counter()
    try:
        records = []
        for index, (name, stamp) in enumerate(zip(recipe["files"], recipe["times"], strict=True)):
            record = (read_rainfall(root / DATASET_ID / name, stamp) if rain else
                      read_accumulated_scalar(root / DATASET_ID / name, stamp, quantity=quantity))
            if record is None:
                if index != 0:
                    label = "rainfall" if rain else quantity
                    raise ValueError(f"Required accumulated {label} is absent: {name}")
                report["excluded"].append({"source_file": name, "time": stamp,
                    "reason": f"parameter {spec.parameter_id} absent at time zero; "
                    "no zero value fabricated"})
            else:
                records.append(record)
        if len(records) != 4:
            raise ValueError(
                "CI preset requires the four positive-lead cumulative scalar records")
        report["source_metadata"] = [r["metadata"] for r in records]
        lat0, lon0 = recipe["fixed_center_lat_lon"]
        for preset in _presets():
            pieces, rows = [], []
            for index, record in enumerate(records):
                field = record["field"].copy(deep=True)
                longitude = lon0
                if preset["id"] == "moving":
                    longitude += float(np.linspace(-.15, .15, len(records))[index])
                elif preset["id"] == "clipped":
                    longitude += .85
                elif preset["id"] == "masked":
                    field.values[:, 30+index:35+index] = np.nan
                plan = ConservativePolarPlan.build(record["grid"],
                    radial_edges_m=np.arange(0, 60000.1, preset["radial_step_m"]),
                    azimuth_count=preset["azimuth_count"], center_lon=longitude, center_lat=lat0,
                    earth_radius_m=float(record["metadata"]["radius"]), max_arc_step_deg=2.5)
                apply_started = perf_counter()
                cells = plan.apply(field, source_representation="scalar_cell_mean").compute()
                apply_s = perf_counter() - apply_started
                oracle_started = perf_counter()
                overlap = independent_overlap_sparse(record["grid"], plan.geometry)
                finite = np.isfinite(field.values.ravel())
                observed = np.where(finite, field.values.ravel(), 0)
                expected_integral = np.asarray(overlap @ observed)
                absolute_integral = np.asarray(overlap @ abs(observed))
                expected_valid_area = np.asarray(overlap @ finite.astype(float))
                actual_integral = cells.covered_area_integral.fillna(0).values.ravel()
                # Per-cell agreement prevents cancellation hiding remapping errors.
                error_by_cell = _integral_errors(actual_integral, expected_integral,
                                                 absolute_integral)
                np.testing.assert_allclose(cells.valid_area.values.ravel(), expected_valid_area,
                                           rtol=2e-7, atol=.05)
                oracle_s = perf_counter() - oracle_started
                alternative = None
                comparison_started = perf_counter()
                if preset["id"] in {"fixed", "coarse"}:
                    alternative = _compare_reconstructions(record["grid"], field, cells,
                                                            expected_integral, quantity=quantity)
                total = float(expected_integral.sum())
                actual_total = float(actual_integral.sum())
                error = abs(actual_total - total)
                rows.append({"source_file": record["source_file"],
                    "accumulation_start": str(record["start"]),
                    "accumulation_end": str(record["end"]),
                    "center_lon": longitude, "center_lat": lat0,
                    f"independent_input_overlap_{spec.integral_name}_{spec.integral_units}": total,
                    f"polar_valid_overlap_{spec.integral_name}_{spec.integral_units}": actual_total,
                    f"{spec.integral_name}_relative_error": error/max(abs(total), 1.),
                    "absolute_source_overlap_integral": float(absolute_integral.sum()),
                    "integral_l1_normalized_error": float(error_by_cell.sum()) / max(
                        float(absolute_integral.sum()), 1.),
                    "net_to_absolute_integral_ratio": abs(total) / float(absolute_integral.sum())
                    if absolute_integral.sum() else None,
                    "geometry_coverage_min": float(cells.geometry_coverage.min()),
                    "valid_area_fraction_min": float(cells.valid_area_fraction.min()),
                    "build_s": plan.geometry.attrs["construction_s"], "apply_s": apply_s,
                    "independent_oracle_s": oracle_s,
                    "reconstruction_comparison": alternative,
                    "reconstruction_comparison_s": perf_counter()-comparison_started,
                    "plan_array_bytes": int(plan.geometry.nbytes + plan.source.nbytes
                        + plan.source_area.nbytes + plan.source_overlap_area.nbytes
                        + plan.weights.data.nbytes + plan.weights.indices.nbytes
                        + plan.weights.indptr.nbytes)})
                pieces.append(cells)
            product = _combine_products(pieces, records, quantity=quantity)
            product.attrs.update(case_id=preset["id"], fixture_identity=fixture["identity"],
                source_mask_policy=("synthetic missing column strip shifted by one cell per time"
                                    if preset["id"] == "masked" else "stored GRIB bitmap"),
                centre_policy=("prescribed +/-0.15 degree longitude trajectory; not a tracker"
                               if preset["id"] == "moving" else "declared fixed footprint"))
            prefix = "rain" if rain else quantity
            path = output / f"batsirai-{prefix}-{preset['id']}.nc"
            report["pending_product"] = path.name
            write_dataset_netcdf(product, path, product_type="polar", metadata=ExportMetadata(
                f"batsirai-{prefix}-ci", f"Experimental accumulated {quantity} analysis cells",
                spec.footprint_meaning, "FrameIt", "Frozen AROME/BATSIRAI GRIB fixture"),
                overwrite=False)
            _check_reopened(path, product, quantity=quantity)
            report.pop("pending_product")
            report["products"].append(path.name)
            report["cases"].append({"id": preset["id"], "times": rows,
                "independent_reader_checked": True,
                "process_lifetime_peak_rss_bytes": process_peak_rss_bytes()})
            report["checks"].append({"name": preset["id"] + "_per_cell_overlap_and_reload",
                                     "ok": True})
            atomic_json(output / "comparison.json", report)
        for item in report["source_files"]:
            if sha256_file(root / item["path"]) != item["sha256"]:
                raise ValueError(f"Source fixture changed during pilot: {item['path']}")
        report["checks"].append({"name": "source_content_unchanged", "ok": True})
        report.update(status="PASS", passed=True, duration_s=perf_counter()-started,
                      promotion_status=(
                          "experimental reconstruction; native cell semantics unverified"))
        atomic_json(output / "comparison.json", report)
        return report
    except Exception as exc:
        report.update(status="FAILED", passed=False, reason=f"{type(exc).__name__}: {exc}",
                      duration_s=perf_counter()-started)
        atomic_json(output / "comparison.json", report)
        raise


def run_ci_heat_fluxes(output, *, data_root=None):
    """Explicitly select the two source-signed accumulated surface-energy presets."""
    root = (Path(str(resources.files("frameit.testing").joinpath("ci_dataset")))
            if data_root is None else Path(data_root)).resolve()
    output = Path(output).expanduser().resolve()
    if output == root or root in output.parents or output in root.parents:
        raise ValueError("CI inputs and pilot outputs must not overlap")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("CI heat-flux output must be fresh or empty")
    output.mkdir(parents=True, exist_ok=True)
    report = {"artifact_type": "polar_heat_flux_ci", "maturity": "experimental",
              "status": "RUNNING", "passed": False, "environment": environment_metadata(),
              "source_spatial_interpretation": SPATIAL_INTERPRETATION,
              "quantities": {}}
    atomic_json(output / "comparison.json", report)
    try:
        for quantity in ("sshf", "slhf"):
            report["pending_quantity"] = quantity
            atomic_json(output / "comparison.json", report)
            result = run_ci_scalar(output / quantity, quantity=quantity, data_root=root)
            if not result["passed"]:
                raise ValueError(f"Accumulated {quantity} pilot did not pass")
            report["quantities"][quantity] = {
                "report": f"{quantity}/comparison.json", "passed": True,
                "fixture_identity": result["fixture_identity"],
                "products": [f"{quantity}/{path}" for path in result["products"]],
                "max_integral_l1_normalized_error": max(
                    row["integral_l1_normalized_error"]
                    for case in result["cases"] for row in case["times"]),
            }
        report.pop("pending_quantity")
        report.update(status="PASS", passed=True)
        atomic_json(output / "comparison.json", report)
        return report
    except Exception as exc:
        report.update(status="FAILED", passed=False, reason=f"{type(exc).__name__}: {exc}")
        atomic_json(output / "comparison.json", report)
        raise
