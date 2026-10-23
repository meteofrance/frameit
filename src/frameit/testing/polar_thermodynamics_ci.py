"""Instantaneous CI scalar representations and geometric weighting, not budgets.

Temperature, relative humidity and specific TKE retain their physical distinctions.
No density, layer mass, heat capacity or humidity conversion is inferred.
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
from frameit.testing.polar_rainfall_ci import (
    _GRID_KEYS,
    BOUNDS_POLICY,
    DATASET_ID,
    SPATIAL_INTERPRETATION,
    _combine_snapshots,
    _decode_regular_ll,
    _presets,
)

HEIGHTS_M = (100, 750)
_FIELDS = {
    "t": (130, "K", "temperature"),
    "r": (157, "%", "relative humidity"),
    "tke": (260155, "J kg-1", "specific turbulent kinetic energy"),
}
MASS_WEIGHTING_STATUS = "unavailable: no layer air masses or volumes supplied by this slice pilot"


def _instant_time(metadata, quantity, expected_time):
    parameter, units, _ = _FIELDS[quantity]
    if (metadata["paramId"] != parameter or metadata["shortName"] != quantity
            or metadata["units"].replace("**", "") != units
            or metadata["typeOfLevel"] != "heightAboveGround"
            or metadata["level"] not in HEIGHTS_M or metadata["stepType"] != "instant"
            or metadata["stepUnits"] != 1 or metadata["startStep"] != metadata["endStep"]):
        raise ValueError(
            f"Expected instantaneous {quantity} in {units} at {HEIGHTS_M} m above ground")
    reference = datetime.strptime(f"{metadata['dataDate']:08d}{metadata['dataTime']:04d}",
                                  "%Y%m%d%H%M")
    stamp = np.datetime64(reference + timedelta(hours=metadata["endStep"]), "ns")
    if stamp != np.datetime64(expected_time, "ns"):
        raise ValueError("Instantaneous scalar valid time differs from the CI recipe")
    return np.datetime64(reference, "ns"), stamp


def read_thermodynamic_snapshot(path, expected_time):
    """Read the six selected records once, with explicit field/level/time contracts."""
    import eccodes as ec

    by_parameter = {spec[0]: name for name, spec in _FIELDS.items()}
    selected = {name: {} for name in _FIELDS}
    metadata = {name: [] for name in _FIELDS}
    grid, radius, reference = None, None, None
    keys = ("paramId", "shortName", "units", "typeOfLevel", "level", "stepType", "stepUnits",
            "startStep", "endStep", "dataDate", "dataTime", *_GRID_KEYS)
    with Path(path).open("rb") as stream:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                parameter = ec.codes_get(handle, "paramId")
                if (parameter not in by_parameter
                        or ec.codes_get(handle, "typeOfLevel") != "heightAboveGround"
                        or ec.codes_get(handle, "level") not in HEIGHTS_M):
                    continue
                quantity = by_parameter[parameter]
                info = {key: ec.codes_get(handle, key) for key in keys}
                height = info["level"]
                if height in selected[quantity]:
                    raise ValueError(f"Ambiguous {quantity} at {height} m in {Path(path).name}")
                current_reference, stamp = _instant_time(info, quantity, expected_time)
                current_grid, values = _decode_regular_ll(ec, handle, info)
                if grid is None:
                    grid, radius, reference = current_grid, float(info["radius"]), current_reference
                elif (radius != info["radius"] or reference != current_reference
                      or not grid.equals(current_grid)):
                    raise ValueError("Selected scalar grids, spheres or reference cycles differ")
                if not np.isfinite(values).any() or np.any(values[np.isfinite(values)] < 0):
                    raise ValueError(
                        f"{quantity} requires valid nonnegative source values; no clipping")
                selected[quantity][height] = values
                metadata[quantity].append(info)
            finally:
                ec.codes_release(handle)
    if grid is None:
        raise ValueError("Required instantaneous CI thermodynamic fields are absent")
    fields, excluded = {}, []
    for name, (_, units, description) in _FIELDS.items():
        if not selected[name] and name == "tke" and np.datetime64(expected_time, "ns") == reference:
            excluded.append({"quantity": name, "time": expected_time,
                             "reason": "TKE absent at time zero; no value fabricated"})
            continue
        if set(selected[name]) != set(HEIGHTS_M):
            raise ValueError(f"Required {name} levels are missing in {Path(path).name}")
        fields[name] = xr.DataArray(np.stack([selected[name][height] for height in HEIGHTS_M]),
            dims=("height", "y", "x"), coords={"height": list(HEIGHTS_M), "y": grid.y, "x": grid.x},
            name=name, attrs={"units": units, "long_name": description,
                              "GRIB_paramId": _FIELDS[name][0], "temporal_kind": "instantaneous"})
        fields[name].height.attrs.update(units="m", positive="up", axis="Z",
                                         long_name="height above ground", height_reference="ground")
    return {"grid": grid, "radius": radius, "reference": reference, "time": stamp,
            "source_file": Path(path).name, "fields": fields, "metadata": metadata,
            "excluded": excluded}


def _weighted_means(values, areas):
    """Valid-area and equal-observed-cell means along the last axis; empty stays NaN."""
    values, areas = np.broadcast_arrays(values, areas)
    if not np.isfinite(areas).all() or np.any(areas < 0):
        raise ValueError("Area weights must be finite and nonnegative")
    valid = np.isfinite(values) & (areas > 0)
    weights = np.where(valid, areas, 0)
    total = weights.sum(axis=-1)
    count = valid.sum(axis=-1)
    area_mean = np.divide((np.where(valid, values, 0)*weights).sum(axis=-1), total,
                          out=np.full(total.shape, np.nan), where=total > 0)
    equal_mean = np.divide(np.where(valid, values, 0).sum(axis=-1), count,
                           out=np.full(total.shape, np.nan), where=count > 0)
    return area_mean, equal_mean, total, count


def _verify_means_and_weighting(field, cells, overlap):
    flat = field.values.reshape(len(HEIGHTS_M), -1)
    finite = np.isfinite(flat)
    numerator = np.asarray(overlap @ np.where(finite, flat, 0).T).T
    areas = np.asarray(overlap @ finite.astype(float).T).T
    truth = np.divide(numerator, areas, out=np.full_like(numerator, np.nan), where=areas > 0)
    actual = cells.covered_area_mean.values.reshape(truth.shape)
    actual_areas = cells.valid_area.values.reshape(areas.shape)
    np.testing.assert_allclose(actual_areas, areas, rtol=2e-7, atol=.05)
    source_min, source_max = np.nanmin(flat, axis=1), np.nanmax(flat, axis=1)
    tolerance = 1e-7*np.maximum(source_max-source_min, 1.)
    for index in range(len(HEIGHTS_M)):
        np.testing.assert_allclose(actual[index], truth[index], rtol=0, atol=tolerance[index],
                                   equal_nan=True)
    area_mean, equal_mean, observed_area, count = _weighted_means(actual, actual_areas)
    expected_mean = numerator.sum(axis=1)/areas.sum(axis=1)
    for index in range(len(HEIGHTS_M)):
        np.testing.assert_allclose(area_mean[index], expected_mean[index], rtol=0,
                                   atol=tolerance[index])
    units = field.attrs["units"]
    for name, values, basis in (
        ("area_weighted_mean", area_mean, "valid geographic area"),
        ("equal_observed_cell_mean", equal_mean, "equal weight per observed polar cell"),
    ):
        cells[name] = ("height", values, {"units": units, "weighting_basis": basis})
    cells["observed_area"] = ("height", observed_area, {"units": "m2"})
    cells["observed_cell_count"] = ("height", count, {"units": "1"})
    return [{"height_m": height, "source_min": float(source_min[i]),
             "source_max": float(source_max[i]), "mean_tolerance": float(tolerance[i]),
             "max_overlap_mean_difference": float(np.nanmax(abs(actual[i]-truth[i]))),
             "input_overlap_area_mean": float(expected_mean[i]),
             "conservative_area_mean": float(area_mean[i]),
             "equal_observed_cell_mean": float(equal_mean[i]),
             "equal_cell_minus_area_mean": float(equal_mean[i]-area_mean[i]),
             "observed_area_m2": float(observed_area[i]), "observed_cell_count": int(count[i])}
            for i, height in enumerate(HEIGHTS_M)]


def _compare_representations(source, field, cells, rows):
    import xesmf as xe

    from frameit.testing.polar_cell_comparison import bilinear_cell_average

    shape = cells.cell_mean.shape
    target = xr.Dataset({"lon": ("locations", cells.lon.values.ravel()),
                         "lat": ("locations", cells.lat.values.ravel())})
    point = xe.Regridder(source, target, "bilinear", locstream_out=True,
                         unmapped_to_nan=True)(field).values.reshape(shape)
    average = bilinear_cell_average(source, field, cells)
    finer = bilinear_cell_average(source, field, cells, order=8)
    if not (cells.full_cell_valid.values.all() and np.isfinite(point).all()
            and np.isfinite(average).all() and np.isfinite(finer).all()):
        raise ValueError("Representation comparison requires full common support")
    units = field.attrs["units"]
    cells["bilinear_point_sample"] = (cells.cell_mean.dims, point, {"units": units,
        "long_name": "point reconstruction at polar-cell midpoint, not a cell mean"})
    cells["bilinear_area_average"] = (cells.cell_mean.dims, average, {"units": units,
        "cell_methods": "area: mean", "cell_measures": "area: cell_area"})
    area = cells.cell_area.values.ravel()
    point_mean, point_equal, _, _ = _weighted_means(point.reshape(len(HEIGHTS_M), -1), area)
    average_mean, _, _, _ = _weighted_means(average.reshape(len(HEIGHTS_M), -1), area)
    for name, values, basis in (
        ("bilinear_point_area_weighted_mean", point_mean, "cell-area midpoint quadrature"),
        ("bilinear_point_equal_sample_mean", point_equal, "equal polar midpoint samples"),
        ("bilinear_area_weighted_mean", average_mean, "integrated bilinear with geographic area"),
    ):
        cells[name] = ("height", values, {"units": units, "weighting_basis": basis})
    for i, row in enumerate(rows):
        row.update(
            point_area_mean_difference=float(point_mean[i]-row["input_overlap_area_mean"]),
            point_equal_mean_difference=float(point_equal[i]-row["input_overlap_area_mean"]),
            bilinear_area_mean_difference=float(average_mean[i]-row["input_overlap_area_mean"]),
            point_vs_cell_rms=float(np.sqrt(np.mean((point[i]-cells.cell_mean.values[i])**2))),
            bilinear_vs_cell_rms=float(np.sqrt(np.mean((average[i]-cells.cell_mean.values[i])**2))),
            bilinear_quadrature_max_difference=float(np.max(abs(average[i]-finer[i]))),
            bilinear_quadrature_area_mean_difference=float(abs(
                np.sum((average[i]-finer[i])*cells.cell_area.values)/cells.cell_area.values.sum())),
        )


def _check_ranges(cells, rows):
    for name in ("cell_mean", "covered_area_mean", "bilinear_point_sample",
                 "bilinear_area_average"):
        if name not in cells:
            continue
        for i, row in enumerate(rows):
            finite = cells[name].values[i][np.isfinite(cells[name].values[i])]
            tolerance = 1e-9*max(1., abs(row["source_min"]), abs(row["source_max"]))
            if finite.size and (finite.min() < row["source_min"]-tolerance
                                or finite.max() > row["source_max"]+tolerance):
                raise ValueError(f"{name} introduced values outside the source range")


def _instant_product(pieces, records, quantity):
    product = _combine_snapshots(pieces, [r["time"] for r in records],
                                 [r["source_file"] for r in records])
    product.time.attrs.update(standard_name="time", long_name="instantaneous valid time")
    product.time.encoding.update(calendar="proleptic_gregorian", units="hours since " +
        np.datetime_as_string(records[0]["reference"], unit="s").replace("T", " "))
    product.attrs.update(temporal_kind="instantaneous", GRIB_paramId=_FIELDS[quantity][0],
        bounds_policy=BOUNDS_POLICY, source_spatial_interpretation=SPATIAL_INTERPRETATION,
        mass_weighting_status=MASS_WEIGHTING_STATUS,
        physical_budget_status="not computed: area statistics are not heat/water/TKE budgets",
        footprint_meaning="instantaneous fields within each snapshot footprint",
        interpretation="representation/weighting differences, not physical-truth errors")
    return product


def run_ci_thermodynamics(output, *, data_root=None):
    """Run the explicitly selected instantaneous 100/750-m comparison preset."""
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
        raise ValueError("Thermodynamics output must be fresh or empty")
    fixture = verify_ci_dataset(root, dataset_ids=[DATASET_ID])
    recipe = load_ci_recipe()["datasets"][DATASET_ID]
    output.mkdir(parents=True, exist_ok=True)
    report = {"artifact_type": "polar_thermodynamics_ci", "maturity": "experimental",
        "status": "RUNNING", "passed": False, "environment": environment_metadata(),
        "fixture_identity": fixture["identity"],
        "fixture_manifest_sha256": fixture["manifest_sha256"],
        "source_files": [{k: r[k] for k in ("path", "bytes", "sha256")} for r in fixture["files"]],
        "source_spatial_interpretation": SPATIAL_INTERPRETATION, "bounds_policy": BOUNDS_POLICY,
        "mass_weighting_status": MASS_WEIGHTING_STATUS, "products": [], "checks": [],
        "settings": {"heights_above_ground_m": list(HEIGHTS_M), "rmax_m": 60000.,
                     "max_arc_step_deg": 2.5, "presets": list(_presets()),
                     "fixed_center_lat_lon": recipe["fixed_center_lat_lon"],
                     "moving_offsets_deg": [-.15, -.075, 0., .075, .15],
                     "clipped_longitude_offset_deg": .85,
                     "synthetic_missing_x_strip": "30+time_index:35+time_index, both heights",
                     "mean_absolute_tolerance": "1e-7 * max(source range, one source-unit)",
                     "local_difference_norm": "unweighted RMS over polar cells"},
        "quantities": {name: {"units": spec[1], "difference_units": (
            "percentage points" if name == "r" else spec[1]), "cases": [], "excluded": [],
            "source_metadata": []} for name, spec in _FIELDS.items()}}
    atomic_json(output / "comparison.json", report)
    started = perf_counter()
    try:
        records = [read_thermodynamic_snapshot(root / DATASET_ID / name, stamp)
                   for name, stamp in zip(recipe["files"], recipe["times"], strict=True)]
        for record in records:
            for name in _FIELDS:
                report["quantities"][name]["source_metadata"].extend(record["metadata"][name])
            for excluded in record["excluded"]:
                report["quantities"][excluded["quantity"]]["excluded"].append(excluded)
        lat0, lon0 = recipe["fixed_center_lat_lon"]
        for preset in _presets():
            pieces = {name: [] for name in _FIELDS}
            rows = {name: [] for name in _FIELDS}
            selected_records = {name: [] for name in _FIELDS}
            for index, record in enumerate(records):
                longitude = lon0 + (float(np.linspace(-.15, .15, len(records))[index])
                                    if preset["id"] == "moving" else .85
                                    if preset["id"] == "clipped" else 0.)
                plan = ConservativePolarPlan.build(record["grid"],
                    radial_edges_m=np.arange(0, 60000.1, preset["radial_step_m"]),
                    azimuth_count=preset["azimuth_count"], center_lon=longitude, center_lat=lat0,
                    earth_radius_m=record["radius"], max_arc_step_deg=2.5)
                oracle_started = perf_counter()
                overlap = independent_overlap_sparse(record["grid"], plan.geometry)
                oracle_s = perf_counter()-oracle_started
                for name, original in record["fields"].items():
                    field = original.copy(deep=True)
                    if preset["id"] == "masked":
                        field.values[:, :, 30+index:35+index] = np.nan
                    apply_started = perf_counter()
                    cells = plan.apply(field, source_representation="scalar_cell_mean").compute()
                    apply_s = perf_counter()-apply_started
                    statistics = _verify_means_and_weighting(field, cells, overlap)
                    comparison_started = perf_counter()
                    if preset["id"] in {"fixed", "coarse"}:
                        _compare_representations(record["grid"], field, cells, statistics)
                    _check_ranges(cells, statistics)
                    # A geometric numerator is useful for reproducing area means,
                    # but must not masquerade as heat, water mass or total TKE.
                    cells = cells.rename(covered_area_integral="area_weighted_numerator")
                    cells.area_weighted_numerator.attrs.update(
                        long_name="geometric area-mean numerator; not a physical budget")
                    cells.attrs.update(case_id=preset["id"],
                        source_mask_policy=("synthetic shifted five-column gap"
                                            if preset["id"] == "masked" else "stored GRIB bitmap"),
                        centre_policy=("prescribed sensitivity trajectory"
                                       if preset["id"] == "moving" else "declared fixed footprint"))
                    rows[name].append({"time": str(record["time"]), "heights": statistics,
                        "build_s": plan.geometry.attrs["construction_s"], "apply_s": apply_s,
                        "shared_oracle_s": oracle_s,
                        "comparison_s": perf_counter()-comparison_started})
                    pieces[name].append(cells)
                    selected_records[name].append(record)
            for name in _FIELDS:
                product = _instant_product(pieces[name], selected_records[name], name)
                path = output / f"batsirai-{name}-{preset['id']}.nc"
                report["pending_product"] = path.name
                write_dataset_netcdf(product, path, product_type="polar", metadata=ExportMetadata(
                    f"batsirai-{name}-instant-ci", "Experimental instantaneous scalar cells",
                    "Geometric area statistics, not physical budgets", "FrameIt",
                    "Frozen BATSIRAI GRIB"),
                    overwrite=False)
                with xr.open_dataset(path) as saved:
                    for variable in product.variables:
                        xr.testing.assert_allclose(saved[variable], product[variable])
                    if "time_bounds" in saved or "bounds" in saved.time.attrs:
                        raise ValueError("Instantaneous output acquired accumulation bounds")
                    if saved.attrs.get("mass_weighting_status") != MASS_WEIGHTING_STATUS:
                        raise ValueError("Reload lost the mass-weighting limitation")
                report.pop("pending_product")
                report["products"].append(path.name)
                report["quantities"][name]["cases"].append({"id": preset["id"], "times": rows[name],
                    "independent_reader_checked": True})
                report["checks"].append({"name": f"{name}_{preset['id']}_overlap_range_and_reload",
                                         "ok": True})
            atomic_json(output / "comparison.json", report)
        for item in report["source_files"]:
            if sha256_file(root / item["path"]) != item["sha256"]:
                raise ValueError("CI source content changed during the experiment")
        report["checks"].append({"name": "source_content_unchanged", "ok": True})
        report["comparison_summary"] = {}
        for name, result in report["quantities"].items():
            heights = [row for case in result["cases"] if case["id"] in {"fixed", "coarse"}
                       for stamp in case["times"] for row in stamp["heights"]]
            report["comparison_summary"][name] = {
                "difference_units": result["difference_units"],
                "scope": "maximum absolute differences across fixed/coarse times and both heights",
                **{key: max(abs(row[key]) for row in heights) for key in (
                    "equal_cell_minus_area_mean", "point_area_mean_difference",
                    "point_equal_mean_difference", "bilinear_area_mean_difference",
                    "point_vs_cell_rms", "bilinear_vs_cell_rms",
                    "bilinear_quadrature_max_difference",
                    "bilinear_quadrature_area_mean_difference")},
                "max_overlap_mean_difference": max(row["max_overlap_mean_difference"]
                    for case in result["cases"] for stamp in case["times"]
                    for row in stamp["heights"]),
            }
        report.update(status="PASS", passed=True, duration_s=perf_counter()-started,
                      process_lifetime_peak_rss_bytes=process_peak_rss_bytes())
        atomic_json(output / "comparison.json", report)
        return report
    except Exception as exc:
        report.update(status="FAILED", passed=False, reason=f"{type(exc).__name__}: {exc}")
        atomic_json(output / "comparison.json", report)
        raise
