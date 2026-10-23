"""Experimental rain-mass pilot on the matrix's read-only AROME/BATSIRAI fixture.

This declares midpoint analysis cells on the stored GRIB regular_ll grid. It
does not assert that postprocessed GRIB values are native-model cell means.
"""

from __future__ import annotations

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


def _midpoint_edges(values):
    values = np.asarray(values, dtype=float)
    differences = np.diff(values)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all() or not (
        np.all(differences > 0) or np.all(differences < 0)
    ) or not np.allclose(differences, differences[0], rtol=0, atol=1e-9):
        raise ValueError("CI rainfall requires finite, monotone, uniform regular_ll axes")
    return np.concatenate(([values[0] - differences[0]/2],
                           (values[:-1]+values[1:])/2, [values[-1] + differences[-1]/2]))


def _analysis_grid(longitude, latitude):
    if longitude.shape != latitude.shape or longitude.ndim != 2:
        raise ValueError("GRIB geography must have matching (Nj, Ni) shapes")
    longitude = np.rad2deg(np.unwrap(np.deg2rad(longitude), axis=1))
    if not np.allclose(longitude, longitude[:1, :], rtol=0, atol=1e-10) or not np.allclose(
        latitude, latitude[:, :1], rtol=0, atol=1e-10
    ):
        raise ValueError("CI rainfall supports only rectilinear regular_ll geography")
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


def _accumulation_times(metadata):
    if metadata["paramId"] != PARAM_ID or metadata["shortName"] != "tirf" or (
        metadata["typeOfLevel"] != "surface" or metadata["stepType"] != "accum"
        or metadata["typeOfStatisticalProcessing"] != 1
        or metadata["units"] not in {"kg m**-2", "kg m-2"}
        or metadata["stepUnits"] != 1 or metadata["startStep"] != 0
        or metadata["endStep"] <= 0
    ):
        raise ValueError(
            "Expected surface tirf (235015), kg/m2, accumulated from hour zero in hours")
    reference = datetime.strptime(f"{metadata['dataDate']:08d}{metadata['dataTime']:04d}",
                                  "%Y%m%d%H%M")
    end = reference + timedelta(hours=metadata["endStep"])
    return np.datetime64(reference, "ns"), np.datetime64(end, "ns")


def read_rainfall(path, expected_time):
    """Read only parameter 235015, failing on ambiguity or incompatible metadata.

    No cfgrib index or other cache is written alongside source files. A missing
    field is returned explicitly; only the preset's time-zero absence is allowed.
    """
    import eccodes as ec

    keys = ("paramId", "shortName", "units", "typeOfLevel", "stepType", "stepUnits",
            "startStep", "endStep", "typeOfStatisticalProcessing", "dataDate", "dataTime",
            "gridType", "Ni", "Nj", "shapeOfTheEarth", "radius", "jPointsAreConsecutive",
            "alternativeRowScanning", "numberOfMissing")
    selected = None
    with Path(path).open("rb") as stream:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                if ec.codes_get(handle, "paramId") != PARAM_ID:
                    continue
                if selected is not None:
                    raise ValueError(f"Ambiguous tirf records in {Path(path).name}")
                metadata = {key: ec.codes_get(handle, key) for key in keys}
                start, end = _accumulation_times(metadata)
                if end != np.datetime64(expected_time, "ns"):
                    raise ValueError("Rainfall accumulation end does not match the CI recipe time")
                if metadata["gridType"] != "regular_ll" or metadata["shapeOfTheEarth"] != 6:
                    raise ValueError("CI rainfall requires regular_ll on the declared GRIB sphere")
                if metadata["jPointsAreConsecutive"] or metadata["alternativeRowScanning"]:
                    raise ValueError("Unsupported GRIB scanning order for CI rainfall")
                shape = (int(metadata["Nj"]), int(metadata["Ni"]))
                longitude = ec.codes_get_array(handle, "longitudes").reshape(shape)
                latitude = ec.codes_get_array(handle, "latitudes").reshape(shape)
                values = ec.codes_get_values(handle).reshape(shape)
                bitmap = (ec.codes_get_array(handle, "bitmap").reshape(shape).astype(bool)
                          if ec.codes_get(handle, "bitmapPresent") else np.ones(shape, dtype=bool))
                if int((~bitmap).sum()) != metadata["numberOfMissing"]:
                    raise ValueError("GRIB bitmap and missing-value count disagree")
                values = np.where(bitmap, values, np.nan)
                if not np.isfinite(values[bitmap]).all() or np.any(values[bitmap] < 0):
                    raise ValueError(
                        "Accumulated rain must be finite/nonnegative where the bitmap is valid")
                grid = _analysis_grid(longitude, latitude)
                field = xr.DataArray(values, dims=("y", "x"), coords={"y": grid.y, "x": grid.x},
                                     name="tirf", attrs={"units": "kg m-2",
                                     "long_name": "time integral of rain flux",
                                     "cell_methods": "time: sum", "GRIB_paramId": PARAM_ID})
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


def _combine_products(pieces, records):
    static_names = ("radius_bounds", "azimuth_bounds", "subcell_owner")
    static = pieces[0][list(static_names)].reset_coords(drop=True)
    dynamic = []
    for piece, record in zip(pieces, records, strict=True):
        item = piece.drop_vars(list(static_names)).expand_dims(time=[record["end"]])
        item = item.assign_coords(lon=piece.lon.expand_dims(time=[record["end"]]),
                                  lat=piece.lat.expand_dims(time=[record["end"]]))
        item["center_lon"] = ("time", [piece.attrs["center_lon"]], {"units": "degrees_east"})
        item["center_lat"] = ("time", [piece.attrs["center_lat"]], {"units": "degrees_north"})
        item["geometry_signature"] = ("time", [piece.attrs["geometry_sha256"]])
        dynamic.append(item)
    product = xr.concat(dynamic, dim="time", data_vars="all", coords="minimal", compat="equals",
                        join="exact", combine_attrs="drop_conflicts")
    product = xr.merge([product, static], compat="equals")
    product["time_bounds"] = (("time", "bounds"),
                               np.array([[r["start"], r["end"]] for r in records]))
    product.time.attrs.update(bounds="time_bounds", standard_name="time",
                              long_name="end of source cumulative rain interval")
    units = "hours since " + np.datetime_as_string(records[0]["start"], unit="s").replace("T", " ")
    for name in ("time", "time_bounds"):
        product[name].encoding.update(units=units, calendar="proleptic_gregorian")
    product["source_file"] = ("time", [r["source_file"] for r in records])
    product["accumulation_end_hour"] = ("time", [r["metadata"]["endStep"] for r in records],
                                         {"units": "h"})
    for name in ("cell_mean", "covered_area_mean"):
        product[name].attrs.update(units="kg m-2", cell_methods="time: sum area: mean")
    product.covered_area_integral.attrs.update(units="kg", cell_methods="time: sum area: sum",
        long_name="accumulated rain mass over valid input-grid overlap at this footprint")
    # Geometry varies in time; authoritative centres/signatures are coordinates/
    # variables above, never a misleading first-time global attribute.
    for name in ("center_lon", "center_lat", "geometry_sha256", "construction_s"):
        product.attrs.pop(name, None)
    product.attrs.update(
        bounds_policy=BOUNDS_POLICY, source_spatial_interpretation=SPATIAL_INTERPRETATION,
        footprint_meaning=FOOTPRINT_MEANING, GRIB_paramId=PARAM_ID,
        temporal_processing="source cumulative intervals retained; no deaccumulation")
    return product


def _check_reopened(path, expected):
    """Use an ordinary reader, including values, time bounds and area metadata."""
    with xr.open_dataset(path) as saved:
        for name in expected.variables:
            xr.testing.assert_allclose(saved[name], expected[name])
        if saved.time.attrs.get("bounds") != "time_bounds":
            raise ValueError("Reload lost accumulation bounds")
        if saved.covered_area_integral.attrs.get("units") != "kg":
            raise ValueError("Reload lost accumulated-mass units")
        if saved.attrs.get("source_spatial_interpretation") != SPATIAL_INTERPRETATION:
            raise ValueError("Reload lost the declared spatial interpretation")


def _compare_reconstructions(source, field, cells, reference_mass):
    """Same stored input, different reconstructions; no physical accuracy oracle."""
    import xesmf as xe

    from frameit.testing.polar_cell_comparison import bilinear_cell_average

    target = xr.Dataset({"lon": ("locations", cells.lon.values.ravel()),
                         "lat": ("locations", cells.lat.values.ravel())})
    point = xe.Regridder(source, target, "bilinear", locstream_out=True,
                         unmapped_to_nan=True)(field).values.reshape(cells.cell_area.shape)
    average = bilinear_cell_average(source, field, cells)
    finer_average = bilinear_cell_average(source, field, cells, order=8)
    common = cells.full_cell_valid.values.astype(bool) & np.isfinite(average) & np.isfinite(point)
    if not common.all():
        raise ValueError("Fixed/coarse comparison requires complete common interpolation support")
    cells["bilinear_point_sample"] = (cells.cell_mean.dims, point, {"units": "kg m-2",
        "cell_methods": "time: sum",
        "long_name": "point reconstruction at the interval midpoint, not a cell mean"})
    cells["bilinear_area_average"] = (cells.cell_mean.dims, average, {"units": "kg m-2",
        "cell_methods": "time: sum area: mean", "cell_measures": "area: cell_area"})
    reference = float(reference_mass.sum())
    area_mass = float(np.sum(average*cells.cell_area.values))
    midpoint_mass = float(np.sum(point*cells.cell_area.values))
    return {"interpretation": "input-cell reconstruction differences, not physical truth errors",
            "local_difference_norm": "unweighted RMS over full polar cells",
            "bilinear_cell_mean_difference_rms_kg_m2": float(np.sqrt(np.mean(
                (average - cells.cell_mean.values)**2))),
            "bilinear_area_budget_relative_difference": (
                area_mass/reference - 1 if reference else None),
            "bilinear_midpoint_budget_relative_difference": (
                midpoint_mass/reference - 1 if reference else None),
            "bilinear_quadrature_max_difference_kg_m2": float(np.max(abs(average-finer_average)))}


def run_ci_rainfall(output, *, data_root=None):
    """Execute the documented, opt-in CI analysis-cell reconstruction preset."""
    from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf
    from frameit.processing.polar.conservative import ConservativePolarPlan
    from frameit.processing.polar.performance import process_peak_rss_bytes
    from frameit.testing.polar_cell_comparison import independent_overlap_sparse

    root = (Path(str(resources.files("frameit.testing").joinpath("ci_dataset")))
            if data_root is None else Path(data_root)).resolve()
    output = Path(output).expanduser().resolve()
    if output == root or root in output.parents or output in root.parents:
        raise ValueError("CI inputs and pilot outputs must not overlap")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("CI rainfall output must be fresh or empty")
    fixture = verify_ci_dataset(root, dataset_ids=[DATASET_ID])
    recipe = load_ci_recipe()["datasets"][DATASET_ID]
    output.mkdir(parents=True, exist_ok=True)
    report = {"artifact_type": "polar_rainfall_ci", "maturity": "experimental",
              "status": "RUNNING", "passed": False, "environment": environment_metadata(),
              "fixture_identity": fixture["identity"],
              "fixture_manifest_sha256": fixture["manifest_sha256"],
              "source_files": [{key: r[key] for key in ("path", "bytes", "sha256")}
                               for r in fixture["files"]],
              "bounds_policy": BOUNDS_POLICY,
              "source_spatial_interpretation": SPATIAL_INTERPRETATION,
              "footprint_meaning": FOOTPRINT_MEANING, "excluded": [], "cases": [], "products": [],
              "settings": {"parameter_id": PARAM_ID, "rmax_m": 60000., "max_arc_step_deg": 2.5,
                           "presets": list(_presets()), "mass_relative_tolerance": 2e-7,
                           "mass_absolute_tolerance_kg": 1.,
                           "fixed_center_lat_lon": recipe["fixed_center_lat_lon"],
                           "moving_longitude_offsets_deg": [-.15, -.05, .05, .15],
                           "clipped_longitude_offset_deg": .85,
                           "synthetic_mask": {"axis": "x", "initial_start": 30,
                                              "width": 5, "shift_per_time": 1}},
              "checks": []}
    atomic_json(output / "comparison.json", report)
    started = perf_counter()
    try:
        records = []
        for index, (name, stamp) in enumerate(zip(recipe["files"], recipe["times"], strict=True)):
            record = read_rainfall(root / DATASET_ID / name, stamp)
            if record is None:
                if index != 0:
                    raise ValueError(f"Required accumulated rainfall is absent: {name}")
                report["excluded"].append({"source_file": name, "time": stamp,
                    "reason": "parameter 235015 absent at time zero; no zero value fabricated"})
            else:
                records.append(record)
        if len(records) != 4:
            raise ValueError(
                "CI preset requires the four positive-lead cumulative rainfall records")
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
                expected_mass = np.asarray(overlap @ np.where(finite, field.values.ravel(), 0))
                expected_valid_area = np.asarray(overlap @ finite.astype(float))
                actual_mass = cells.covered_area_integral.fillna(0).values.ravel()
                # Per-cell agreement prevents cancellation hiding remapping errors.
                np.testing.assert_allclose(actual_mass, expected_mass, rtol=2e-7, atol=1.)
                np.testing.assert_allclose(cells.valid_area.values.ravel(), expected_valid_area,
                                           rtol=2e-7, atol=.05)
                oracle_s = perf_counter() - oracle_started
                alternative = None
                comparison_started = perf_counter()
                if preset["id"] in {"fixed", "coarse"}:
                    alternative = _compare_reconstructions(record["grid"], field, cells,
                                                            expected_mass)
                total = float(expected_mass.sum())
                error = abs(float(actual_mass.sum()) - total)
                rows.append({"source_file": record["source_file"],
                    "accumulation_start": str(record["start"]),
                    "accumulation_end": str(record["end"]),
                    "center_lon": longitude, "center_lat": lat0,
                    "independent_input_overlap_mass_kg": total,
                    "polar_valid_overlap_mass_kg": float(actual_mass.sum()),
                    "mass_relative_error": error/max(abs(total), 1.),
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
            product = _combine_products(pieces, records)
            product.attrs.update(case_id=preset["id"], fixture_identity=fixture["identity"],
                source_mask_policy=("synthetic missing column strip shifted by one cell per time"
                                    if preset["id"] == "masked" else "stored GRIB bitmap"),
                centre_policy=("prescribed +/-0.15 degree longitude trajectory; not a tracker"
                               if preset["id"] == "moving" else "declared fixed footprint"))
            path = output / f"batsirai-rain-{preset['id']}.nc"
            report["pending_product"] = path.name
            write_dataset_netcdf(product, path, product_type="polar", metadata=ExportMetadata(
                "batsirai-rainfall-ci", "Experimental accumulated rain analysis cells",
                FOOTPRINT_MEANING, "FrameIt", "Frozen AROME/BATSIRAI GRIB fixture"),
                overwrite=False)
            _check_reopened(path, product)
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
