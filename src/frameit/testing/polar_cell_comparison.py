"""Opt-in comparison of polar point samples and experimental scalar cell means.

Independent references use gnomonic polygon clipping and spherical quadrature,
not ESMF weights. Run with --output pointing at a fresh directory.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

import numpy as np
import xarray as xr
from pyproj import CRS, Geod, Transformer

from frameit.testing.artifacts import atomic_json, environment_metadata

EARTH_RADIUS_M = 6371000.


def chart(longitude=0., latitude=0., radius=EARTH_RADIUS_M):
    geographic = CRS.from_proj4(f"+proj=longlat +R={radius}")
    projected = CRS.from_proj4(
        f"+proj=gnom +lat_0={latitude} +lon_0={longitude} +R={radius} +units=m")
    return (Transformer.from_crs(geographic, projected, always_xy=True),
            Transformer.from_crs(projected, geographic, always_xy=True))


def source_fixture(spacing_m=10000., *, longitude=0., latitude=0.):
    """Explicit cells in a spherical gnomonic chart; no production bounds inference."""
    _, inverse = chart(longitude, latitude)
    count = int(np.ceil(160000 / spacing_m))
    edges = np.linspace(-80000, 80000, count + 1)
    centres = (edges[:-1] + edges[1:]) / 2
    lon_b, lat_b = inverse.transform(*np.meshgrid(edges, edges))
    lon, lat = inverse.transform(*np.meshgrid(centres, centres))
    return xr.Dataset({"lon": (("y", "x"), lon), "lat": (("y", "x"), lat),
                       "lon_b": (("y_b", "x_b"), lon_b), "lat_b": (("y_b", "x_b"), lat_b)},
                      coords={"y": centres, "x": centres})


def source_rings(source):
    lon, lat = source.lon_b.values, source.lat_b.values
    return [np.array([(lon[j, i], lat[j, i]), (lon[j, i+1], lat[j, i+1]),
                      (lon[j+1, i+1], lat[j+1, i+1]), (lon[j+1, i], lat[j+1, i])])
            for j in range(source.sizes["y"]) for i in range(source.sizes["x"])]


def target_rings(geometry):
    return [np.column_stack((lon[np.isfinite(lon)], lat[np.isfinite(lat)]))
            for lon, lat in zip(geometry.subcell_lon_bounds.values,
                                geometry.subcell_lat_bounds.values, strict=True)]


def independent_overlap(source, geometry):
    """Clip great-circle polygons as straight lines in a gnomonic chart.

    Area is evaluated independently with PROJ on the same sphere, after inverse
    projection of each intersection. This is an oracle for small regional cases.
    """
    return independent_overlap_sparse(source, geometry).toarray()


def independent_overlap_sparse(source, geometry):
    """Spatially indexed oracle; bound storage by actual polygon intersections."""
    from scipy.sparse import coo_matrix
    from shapely import STRtree
    from shapely.geometry import Polygon

    radius = geometry.attrs["earth_radius_m"]
    forward, inverse = chart(geometry.attrs["center_lon"], geometry.attrs["center_lat"], radius)
    geod = Geod(a=radius, b=radius)
    sources = [Polygon(np.column_stack(forward.transform(*ring.T)))
               for ring in source_rings(source)]
    tree = STRtree(sources)
    rows, columns, areas = [], [], []
    for ring, owner in zip(target_rings(geometry), geometry.subcell_owner.values, strict=True):
        target = Polygon(np.column_stack(forward.transform(*ring.T)))
        for index in tree.query(target, predicate="intersects"):
            intersection = target.intersection(sources[index])
            if intersection.is_empty or intersection.area == 0:
                continue
            lon, lat = inverse.transform(*np.asarray(intersection.exterior.coords).T)
            rows.append(owner)
            columns.append(index)
            areas.append(abs(geod.polygon_area_perimeter(lon, lat)[0]))
    return coo_matrix((areas, (rows, columns)),
                      shape=(geometry.cell_area.size, len(sources))).tocsr()


def polygon_quadrature(ring, forward, *, radius=EARTH_RADIUS_M, order=10):
    """Independent Gaussian quadrature sites/weights via a Duffy map.

    The gnomonic area Jacobian is (1+(x*x+y*y)/R**2)**(-3/2).
    Our source rectangles and target subcells are convex in this regional chart.
    """
    xy = np.column_stack(forward.transform(*ring.T))
    nodes, weights = np.polynomial.legendre.leggauss(order)
    u, v = np.meshgrid((nodes + 1) / 2, (nodes + 1) / 2)
    quadrature = np.outer(weights, weights) / 4
    sites, areas = [], []
    for index in range(1, len(xy) - 1):
        a, b, c = xy[0], xy[index], xy[index+1]
        cross = abs((b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]))
        points = a + u[..., None] * (b-a) + ((1-u)*v)[..., None] * (c-a)
        x, y = points[..., 0], points[..., 1]
        jacobian = (1 + (x*x + y*y) / radius**2)**(-1.5)
        sites.append(points.reshape(-1, 2))
        areas.append((quadrature * cross * (1-u) * jacobian).ravel())
    return np.concatenate(sites), np.concatenate(areas)


def polygon_integral(ring, function, forward, *, radius=EARTH_RADIUS_M, order=10):
    sites, areas = polygon_quadrature(ring, forward, radius=radius, order=order)
    return float(np.sum(areas * function(*sites.T)))


def target_integrals(geometry, function, *, order=10):
    forward, _ = chart(geometry.attrs["center_lon"], geometry.attrs["center_lat"],
                       geometry.attrs["earth_radius_m"])
    totals = np.zeros(geometry.cell_area.size)
    for ring, owner in zip(target_rings(geometry), geometry.subcell_owner.values, strict=True):
        totals[owner] += polygon_integral(ring, function, forward,
                                          radius=geometry.attrs["earth_radius_m"], order=order)
    return totals.reshape(geometry.cell_area.shape)


def rainfall(x, y):
    """Manufactured localized rainfall depth in metres, not a physical storm model."""
    return .03 * np.exp(-.5 * (((x-13000)/8000)**2 + ((y+7000)/12000)**2))


def bilinear_cell_average(source, point_field, geometry, *, order=4):
    """Integrate the bilinear point reconstruction over exactly the same cells.

    Unlike assigning midpoint values to cells, this explicitly approximates an
    area average. It does not enforce the supplied source cell-mean integrals.
    """
    import xesmf as xe

    forward, inverse = chart(geometry.attrs["center_lon"], geometry.attrs["center_lat"],
                             geometry.attrs["earth_radius_m"])
    sites, areas, owners = [], [], []
    for ring, owner in zip(target_rings(geometry), geometry.subcell_owner.values, strict=True):
        xy, weights = polygon_quadrature(ring, forward, order=order,
                                         radius=geometry.attrs["earth_radius_m"])
        sites.append(xy)
        areas.append(weights)
        owners.append(np.full(len(xy), owner))
    lon, lat = inverse.transform(*np.concatenate(sites).T)
    target = xr.Dataset({"lon": ("locations", lon), "lat": ("locations", lat)})
    samples = xe.Regridder(source, target, "bilinear", locstream_out=True)(point_field).values
    totals = np.bincount(np.concatenate(owners), weights=samples * np.concatenate(areas),
                         minlength=geometry.cell_area.size)
    return totals.reshape(geometry.cell_area.shape) / geometry.cell_area.values


def compact_wind_experiment():
    """Exercise the existing full point-vector path on a compact 12-km core.

    WGS84 vector fixtures are separate from the spherical rainfall experiment.
    No scalar conservative remap is presented as a velocity/flux method.
    """
    from frameit.testing.analytic_vortices import AnalyticVortex
    from frameit.testing.polar_qualification import compare_fields, project_fixture, radial_profiles

    vortex = AnalyticVortex(radius_m=12000., inflow_max_ms=5.)
    rows = []
    for spacing in (4000., 2000., 1000.):
        result, truth, _, elapsed = project_fixture(
            vortex, spacing, radial_resolution=500, x_boxsize_km=100, y_boxsize_km=100)
        metrics = compare_fields(result, truth)
        profiles = radial_profiles(result, truth)
        rows.append({"source_spacing_m": spacing, "prescribed_rmw_km": 12.,
                     "target_radial_step_m": 500., "target_azimuth_count": 128,
                     "earth_model": "WGS84", "metrics": metrics, "rmw": profiles["rmw"],
                     "complete_execution_s": elapsed})
    return rows


def compare(output):
    import xesmf as xe

    from frameit.io.netcdf_export import ExportMetadata, write_dataset_netcdf
    from frameit.processing.polar.conservative import ConservativePolarPlan

    output = Path(output).expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Comparison output must be fresh or empty")
    output.mkdir(parents=True, exist_ok=True)
    report = {"maturity": "experimental", "environment": environment_metadata(),
              "earth_radius_m": EARTH_RADIUS_M, "cases": [],
              "fixture": {"source_extent_gnomonic_m": [-80000, 80000],
                          "rainfall_peak_m": .03, "rainfall_centre_xy_m": [13000, -7000],
                          "rainfall_sigma_xy_m": [8000, 12000],
                          "source_cell_means": "independent spherical quadrature",
                          "source_point_values": "direct analytical centre evaluation"},
              "interpretation": "Point errors and cell-mean errors measure different quantities; "
              "midpoint quadrature is a budget estimate, not conservative remapping."}
    checks = []
    # Deliberately retain one source cell crossing the target boundary so the
    # budget oracle uses shared-domain overlap, not the whole source rectangle.
    for spacing in (20000., 10000., 5000.):
        source = source_fixture(spacing)
        plan = ConservativePolarPlan.build(
            source, radial_edges_m=np.linspace(0, 60000, 7), azimuth_count=24,
            center_lon=0, center_lat=0, earth_radius_m=EARTH_RADIUS_M, max_arc_step_deg=2.5)
        forward, inverse = chart()
        rings = source_rings(source)
        means = np.array([polygon_integral(ring, rainfall, forward) /
                          polygon_integral(ring, lambda x, y: np.ones_like(x), forward)
                          for ring in rings]).reshape(source.lon.shape)
        finer_means = np.array([polygon_integral(ring, rainfall, forward, order=16) /
                                polygon_integral(ring, lambda x, y: np.ones_like(x), forward,
                                                 order=16)
                                for ring in rings]).reshape(source.lon.shape)
        source_quadrature_error = float(np.max(np.abs(means - finer_means)))
        field = xr.DataArray(means, dims=("y", "x"), coords={"y": source.y, "x": source.x},
                             name="rainfall_depth", attrs={"units": "m"})
        started = perf_counter()
        cells = plan.apply(field, source_representation="scalar_cell_mean").compute()
        application_s = perf_counter() - started
        truth_integrals = target_integrals(plan.geometry, rainfall)
        finer_truth = target_integrals(plan.geometry, rainfall, order=16)
        quadrature_error = float(np.max(np.abs(truth_integrals - finer_truth)))
        truth_mean = truth_integrals / cells.cell_area.values
        # A separate centre-evaluated source is necessary for a fair point test.
        x, y = np.meshgrid(source.x.values, source.y.values)
        point_field = field.copy(data=rainfall(x, y))
        azimuth, radius = np.meshgrid(np.rad2deg(cells.azimuth_cell),
                                     cells.radius_cell.values * 1000)
        geod = Geod(a=EARTH_RADIUS_M, b=EARTH_RADIUS_M)
        lon, lat, _ = geod.fwd(np.zeros(radius.shape), np.zeros(radius.shape), azimuth, radius)
        target = xr.Dataset({"lon": ("locations", lon.ravel()),
                             "lat": ("locations", lat.ravel())})
        started = perf_counter()
        sampler = xe.Regridder(source, target, "bilinear", locstream_out=True)
        point_build_s = perf_counter() - started
        started = perf_counter()
        sampled = sampler(point_field).values.reshape(radius.shape)
        point_apply_s = perf_counter() - started
        exact_points = rainfall(*forward.transform(lon, lat))
        averaged_bilinear = bilinear_cell_average(source, point_field, plan.geometry)
        finer_bilinear = bilinear_cell_average(source, point_field, plan.geometry, order=8)
        # Independent overlap validates conservation for the piecewise-constant
        # source reconstruction separately from its approximation to smooth truth.
        overlap = independent_overlap(source, plan.geometry)
        expected_integral = float(np.sum(overlap @ means.ravel()))
        actual_integral = float(cells.covered_area_integral.sum())
        conservation_error = abs(actual_integral - expected_integral) / expected_integral
        cells["analytical_cell_mean"] = (cells.cell_mean.dims, truth_mean, {"units": "m"})
        cells["bilinear_point_sample"] = (cells.cell_mean.dims, sampled, {"units": "m",
            "long_name": "point value at interval midpoint; not a cell mean"})
        cells["analytical_point_value"] = (cells.cell_mean.dims, exact_points, {"units": "m"})
        cells["bilinear_area_average"] = (cells.cell_mean.dims, averaged_bilinear, {"units": "m",
            "cell_methods": "area: mean", "cell_measures": "area: cell_area"})
        cells.attrs["comparison_source_spacing_m"] = spacing
        path = output / f"rainfall-{int(spacing)}m.nc"
        write_dataset_netcdf(cells, path, product_type="polar", metadata=ExportMetadata(
            "polar-cell-experiment", "Experimental rainfall cell/point comparison",
            "Manufactured scalar; spherical geometry", "FrameIt", "Analytical fixture"))
        # Ordinary-reader verification without relying on FrameIt's loader.
        with xr.open_dataset(path) as saved:
            np.testing.assert_allclose(saved.cell_mean, cells.cell_mean)
            np.testing.assert_allclose(saved.cell_area, cells.cell_area)
            assert saved.radius_cell.attrs["bounds"] == "radius_bounds"
            assert saved.attrs["maturity"] == "experimental"
        row = {
            "source_spacing_m": spacing, "source_shape": list(source.lon.shape),
            "cell_mean_rms_m": float(np.sqrt(np.mean((cells.cell_mean.values-truth_mean)**2))),
            "point_rms_m": float(np.sqrt(np.mean((sampled-exact_points)**2))),
            "bilinear_area_average_rms_m": float(np.sqrt(np.mean(
                (averaged_bilinear-truth_mean)**2))),
            "bilinear_area_average_quadrature_difference_m": float(np.max(
                np.abs(averaged_bilinear-finer_bilinear))),
            "bilinear_area_average_budget_relative_error_smooth_truth": float(
                np.sum(averaged_bilinear*cells.cell_area.values) / truth_integrals.sum() - 1),
            "conservation_relative_error_independent_overlap": conservation_error,
            "conservative_budget_relative_error_smooth_truth": float(
                (actual_integral / truth_integrals.sum()) - 1),
            "bilinear_midpoint_budget_relative_error_smooth_truth": float(
                np.sum(sampled*cells.cell_area.values) / truth_integrals.sum() - 1),
            "quadrature_max_integral_difference_m3": quadrature_error,
            "source_mean_quadrature_max_difference_m": source_quadrature_error,
            "cell_build_s": plan.geometry.attrs["construction_s"],
            "cell_apply_s": application_s, "point_build_s": point_build_s,
            "point_apply_s": point_apply_s,
            "cell_plan_array_bytes": int(plan.weights.data.nbytes + plan.weights.indices.nbytes
                                         + plan.weights.indptr.nbytes + plan.geometry.nbytes),
            "product": path.name,
        }
        report["cases"].append(row)
        checks.extend([
            {"name": f"independent_overlap_{int(spacing)}m", "value": conservation_error,
             "maximum": 1e-7, "ok": conservation_error < 1e-7},
            {"name": f"analytical_quadrature_{int(spacing)}m", "value": quadrature_error,
             "maximum_m3": 1e-3, "ok": quadrature_error < 1e-3},
            {"name": f"source_mean_quadrature_{int(spacing)}m", "value": source_quadrature_error,
             "maximum_m": 1e-7, "ok": source_quadrature_error < 1e-7},
        ])
        atomic_json(output / "comparison.json", report)
    for name in ("cell_mean_rms_m", "point_rms_m"):
        checks.append({"name": f"refinement_{name}",
                       "ok": report["cases"][-1][name] < report["cases"][0][name]})
    report["compact_wind_point_baseline"] = compact_wind_experiment()
    wind_rows = report["compact_wind_point_baseline"]
    coarse, fine = wind_rows[0], wind_rows[-1]
    for name in ("vrad", "vtan", "wind_speed"):
        checks.append({"name": f"compact_wind_refinement_{name}",
                       "ok": fine["metrics"][name]["rms"] < coarse["metrics"][name]["rms"]})
    checks.append({"name": "compact_rmw_within_target_interval", "maximum_km": .5,
                   "value": fine["rmw"]["error_km"], "ok": fine["rmw"]["error_km"] <= .5})
    report["checks"] = checks
    report["passed"] = all(check["ok"] for check in checks)
    report["promotion_status"] = (
        "No default change; real-model and vector qualification outstanding")
    atomic_json(output / "comparison.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--ci", action="store_true",
                           help="Run the experimental BATSIRAI rain pilot on bundled CI data.")
    selection.add_argument("--ci-heat-fluxes", action="store_true",
                           help="Run the source-signed sshf/slhf accumulated-energy CI pilots.")
    args = parser.parse_args()
    if args.ci_heat_fluxes:
        from frameit.testing.polar_rainfall_ci import run_ci_heat_fluxes

        report = run_ci_heat_fluxes(args.output)
    elif args.ci:
        from frameit.testing.polar_rainfall_ci import run_ci_rainfall

        report = run_ci_rainfall(args.output)
    else:
        report = compare(args.output)
    print(f"Polar cell experiment: {'PASS' if report['passed'] else 'FAIL'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
