"""Experimental scalar cell remapping; deliberately separate from point products.

Inputs are declared cell means with supplied corners, not inferred point values.
All edges and areas use one explicit sphere. No velocity/flux conservation is
implied. See docs/source/polar_projection/conservative_experiment.rst.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from time import perf_counter

import numpy as np
import xarray as xr
from pyproj import Geod
from scipy.sparse import coo_matrix, csr_matrix

from frameit.processing.polar.contracts import _validate_cells
from frameit.processing.polar.metadata import point_attributes

CELL_DIMS = ("radius_cell", "azimuth_cell")


def _esmf():
    try:
        import esmpy
    except ImportError:
        try:
            import ESMF as esmpy
        except ImportError as exc:
            raise ImportError("Conservative polar experiment requires ESMPy/ESMF") from exc
    return esmpy


def _mesh(esmf, polygons, geod):
    """Float64 ESMPy mesh, with explicit CCW orientation and no dropped cells."""
    rings = []
    for polygon in polygons:
        area = geod.polygon_area_perimeter(polygon[:, 0], polygon[:, 1])[0]
        if not np.isfinite(area) or abs(area) < 1e-4:
            raise ValueError("Degenerate spherical cell")
        rings.append(polygon if area > 0 else polygon[::-1])
    nodes = np.concatenate(rings).astype(np.float64)
    # ESMPy fields query element locations even for area-only remapping. Supply
    # spherical representative positions so dateline cells have sensible centres.
    centres = []
    for ring in rings:
        lon, lat = np.deg2rad(ring).T
        x, y, z = np.mean(np.column_stack((np.cos(lat)*np.cos(lon),
                                          np.cos(lat)*np.sin(lon), np.sin(lat))), axis=0)
        centres.append(np.rad2deg([np.arctan2(y, x), np.arctan2(z, np.hypot(x, y))]))
    mesh = esmf.Mesh(parametric_dim=2, spatial_dim=2, coord_sys=esmf.CoordSys.SPH_DEG)
    try:
        mesh.add_nodes(len(nodes), np.arange(len(nodes), dtype=np.int32) + 1,
                       nodes.ravel(), np.zeros(len(nodes), dtype=np.int32))
        mesh.add_elements(len(rings), np.arange(len(rings), dtype=np.int32) + 1,
                          np.array([len(ring) for ring in rings], dtype=np.int32),
                          np.arange(len(nodes), dtype=np.int32),
                          element_coords=np.asarray(centres, dtype=np.float64).ravel())
    except Exception:
        mesh.destroy()
        raise
    return mesh


def _source_polygons(source, max_cells):
    if not {"lon", "lat", "lon_b", "lat_b"} <= set(source.variables):
        raise ValueError("Supply lon, lat and explicit lon_b/lat_b corners in degrees")
    dims = source.lon.dims
    if len(dims) != 2 or source.lat.dims != dims:
        raise ValueError("Source lon/lat must share two named horizontal dimensions")
    shape = source.lon.shape
    if min(shape) < 1:
        raise ValueError("Source must contain at least one cell on each horizontal axis")
    if np.prod(shape) > max_cells:
        raise ValueError("Source exceeds experimental max_cells budget")
    if any(dim not in source.coords or source[dim].dims != (dim,) for dim in dims):
        raise ValueError("Source horizontal dimensions require explicit index coordinates")
    if any(not source.get_index(dim).is_unique for dim in dims):
        raise ValueError("Source horizontal index coordinates must be unique")
    corner_dims = tuple(f"{dim}_b" for dim in dims)
    if source.lon_b.dims != corner_dims or source.lat_b.dims != corner_dims:
        raise ValueError(f"Source corner dimensions must be {corner_dims}, in that order")
    for name in ("lon", "lat", "lon_b", "lat_b"):
        if source[name].attrs.get("units", "degree") not in {
            "degree", "degrees", "degrees_east", "degrees_north",
        } or source[name].attrs.get("standard_name") in {"grid_latitude", "grid_longitude"}:
            raise ValueError("Supply geographic coordinates in degrees, not rotated axes or radians")
        values = source[name].values
        if not np.isfinite(values).all():
            raise ValueError("Source geography and corners must be finite")
        if name.startswith("lat") and np.any(np.abs(values) >= 85):
            raise ValueError("Prototype excludes polar source cells (abs(latitude) >= 85)")
    lon, lat = source.lon_b.values, source.lat_b.values
    if lon.shape != tuple(size + 1 for size in shape) or lat.shape != lon.shape:
        raise ValueError("Corners must have shape (ny+1, nx+1), ordered as source lon/lat")
    # Regional unwrap preserves connectivity across the antimeridian.
    lon = np.rad2deg(np.unwrap(np.unwrap(np.deg2rad(lon), axis=1), axis=0))
    if np.ptp(lon) > 20 or np.ptp(lat) > 20:
        raise ValueError("Prototype supports regional source extents of at most 20 degrees")
    _validate_cells(lon, lat)
    polygons = [np.array([[lon[j, i], lat[j, i]], [lon[j, i+1], lat[j, i+1]],
                          [lon[j+1, i+1], lat[j+1, i+1]], [lon[j+1, i], lat[j+1, i]]])
                for j in range(shape[0]) for i in range(shape[1])]
    return dims, polygons


def _target_polygons(edges, count, centre, geod, arc_step):
    segments = int(np.ceil(360 / count / arc_step))
    angles = np.arange(count * segments + 1) * (360 / (count * segments))
    azimuth, radius = np.meshgrid(angles, edges)
    lon, lat, _ = geod.fwd(np.full(radius.shape, centre[0]),
                          np.full(radius.shape, centre[1]), azimuth, radius)
    # Force bit-identical seam vertices, including at dateline-crossing origins.
    lon[:, -1], lat[:, -1] = lon[:, 0], lat[:, 0]
    polygons, owners = [], []
    for j in range(len(edges) - 1):
        for k in range(count * segments):
            vertices = [(lon[j+1, k], lat[j+1, k]), (lon[j+1, k+1], lat[j+1, k+1])]
            vertices += ([(lon[j, k], lat[j, k])] if edges[j] == 0 else
                         [(lon[j, k+1], lat[j, k+1]), (lon[j, k], lat[j, k])])
            polygons.append(np.array(vertices))
            owners.append(j * count + k // segments)
    return polygons, np.array(owners), segments


@dataclass
class ConservativePolarPlan:
    """Experimental fixed-geometry scalar plan; build a new plan for each centre.

    The source Dataset supplies 2-D lon/lat centres and (ny+1,nx+1) lon_b/lat_b
    corners. Geographic arrays use degrees. No source bounds are guessed.
    """

    source: xr.Dataset
    geometry: xr.Dataset
    weights: csr_matrix
    source_area: np.ndarray
    source_overlap_area: np.ndarray
    horizontal_dims: tuple

    @classmethod
    def build(cls, source, *, radial_edges_m, azimuth_count, center_lon, center_lat,
              earth_radius_m, max_arc_step_deg=1., max_cells=100000):
        started = perf_counter()
        edges = np.asarray(radial_edges_m, dtype=float)
        if (edges.ndim != 1 or edges.size < 2 or not np.isfinite(edges).all()
                or edges[0] != 0 or np.any(np.diff(edges) <= 0) or edges[-1] > 500000):
            raise ValueError("Radial edges must increase from zero to at most 500000 metres")
        for name, value, minimum in (("azimuth_count", azimuth_count, 3),
                                     ("max_cells", max_cells, 1)):
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if not np.isfinite(max_arc_step_deg) or not 0 < max_arc_step_deg <= 5:
            raise ValueError("max_arc_step_deg must lie in (0, 5]")
        if not np.isfinite(earth_radius_m) or earth_radius_m <= 0:
            raise ValueError("Declare a finite positive earth_radius_m")
        if not np.isfinite([center_lon, center_lat]).all() or abs(center_lat) >= 80:
            raise ValueError("Declare a finite centre with abs(latitude) < 80")
        n_parts = (len(edges) - 1) * azimuth_count * int(
            np.ceil(360 / azimuth_count / max_arc_step_deg))
        if n_parts > max_cells:
            raise ValueError("Target subcells exceed experimental max_cells budget")
        dims, source_polygons = _source_polygons(source, max_cells)
        geod = Geod(a=earth_radius_m, b=earth_radius_m)
        polygons, owners, segments = _target_polygons(
            edges, azimuth_count, (center_lon, center_lat), geod, max_arc_step_deg)
        esmf = _esmf()
        resources = []
        try:
            src = _mesh(esmf, source_polygons, geod)
            resources.append(src)
            dst = _mesh(esmf, polygons, geod)
            resources.append(dst)
            srcfield = esmf.Field(src, meshloc=esmf.MeshLoc.ELEMENT)
            resources.append(srcfield)
            dstfield = esmf.Field(dst, meshloc=esmf.MeshLoc.ELEMENT)
            resources.append(dstfield)
            remap = esmf.Regrid(
                srcfield, dstfield, regrid_method=esmf.RegridMethod.CONSERVE,
                norm_type=esmf.NormType.DSTAREA, unmapped_action=esmf.UnmappedAction.IGNORE,
                ignore_degenerate=False, factors=True)
            resources.append(remap)
            raw = remap.get_weights_dict(deep_copy=True)
            srcfield.get_area()
            dstfield.get_area()
            source_area = srcfield.data.copy() * earth_radius_m**2
            part_area = dstfield.data.copy() * earth_radius_m**2
        finally:
            for resource in reversed(resources):
                resource.destroy()
        n_cells = (len(edges) - 1) * azimuth_count
        area = np.bincount(owners, weights=part_area, minlength=n_cells)
        rows = raw["row_dst"] - 1
        weights = coo_matrix((raw["weights"] * part_area[rows] / area[owners[rows]],
                              (owners[rows], raw["col_src"] - 1)),
                             shape=(n_cells, len(source_polygons))).tocsr()
        weights.sum_duplicates()
        if not np.isfinite(weights.data).all() or np.any(weights.data < 0):
            raise ValueError("ESMF returned invalid conservative overlap weights")
        coverage = np.asarray(weights.sum(axis=1)).ravel()
        if np.any(coverage > 1 + 1e-8):
            raise ValueError("Overlapping geometry: destination coverage exceeds one")
        source_overlap_area = np.asarray(weights.T @ area).ravel()
        if np.any(source_overlap_area > source_area * (1 + 1e-8)):
            raise ValueError("Overlapping target geometry: source coverage exceeds one")
        shape = (len(edges) - 1, azimuth_count)
        geometry = xr.Dataset(coords={
            CELL_DIMS[0]: (edges[:-1] + edges[1:]) / 2000,
            CELL_DIMS[1]: (np.arange(azimuth_count) + .5) * 2 * np.pi / azimuth_count,
        })
        geometry["radius_bounds"] = ((CELL_DIMS[0], "bounds"),
                                     np.column_stack((edges[:-1], edges[1:])) / 1000)
        angular_edges = np.arange(azimuth_count + 1) * 2 * np.pi / azimuth_count
        geometry["azimuth_bounds"] = ((CELL_DIMS[1], "bounds"),
                                      np.column_stack((angular_edges[:-1], angular_edges[1:])))
        geometry[CELL_DIMS[0]].attrs.update(units="km", bounds="radius_bounds",
                                           long_name="radial interval midpoint, not area centroid")
        geometry[CELL_DIMS[1]].attrs.update(units="rad", bounds="azimuth_bounds",
                                           long_name="launch azimuth clockwise from north")
        geometry.radius_bounds.attrs["units"] = "km"
        geometry.azimuth_bounds.attrs["units"] = "rad"
        geometry["cell_area"] = (CELL_DIMS, area.reshape(shape), {"units": "m2"})
        geometry["geometry_coverage"] = (CELL_DIMS, coverage.reshape(shape), {"units": "1"})
        # Export the actual mesh pieces, not only idealized annular boundaries.
        vertices = np.full((len(polygons), 4, 2), np.nan)
        for index, polygon in enumerate(polygons):
            vertices[index, :len(polygon)] = polygon
        geometry["subcell_lon_bounds"] = (("subcell", "vertex"), vertices[:, :, 0],
                                          {"units": "degrees_east"})
        geometry["subcell_lat_bounds"] = (("subcell", "vertex"), vertices[:, :, 1],
                                          {"units": "degrees_north"})
        geometry["subcell_owner"] = ("subcell", owners, {"start_index": 0,
            "long_name": "C-order flattened radius_cell/azimuth_cell index"})
        geometry["subcell_area"] = ("subcell", part_area, {"units": "m2"})
        azimuth, radius = np.meshgrid(np.rad2deg(geometry.azimuth_cell),
                                     geometry.radius_cell.values * 1000)
        lon, lat, _ = geod.fwd(np.full(shape, center_lon), np.full(shape, center_lat),
                              azimuth, radius)
        geometry = geometry.assign_coords(lon=(CELL_DIMS, lon), lat=(CELL_DIMS, lat))
        for name, units in (("lon", "degrees_east"), ("lat", "degrees_north")):
            geometry[name].attrs.update(units=units,
                long_name="representative interval-midpoint location, not an area centroid")
        digest = hashlib.sha256()
        digest.update(str(float(earth_radius_m)).encode())
        for values in (source.lon, source.lat, source.lon_b, source.lat_b, vertices):
            digest.update(np.asarray(values, dtype="<f8").tobytes())
        geometry.attrs.update(
            maturity="experimental", representation="polar_cell_mean", backend="ESMPy",
            esmpy_version=str(esmf.__version__), earth_model="sphere",
            earth_radius_m=float(earth_radius_m), center_lon=float(center_lon),
            center_lat=float(center_lat), arc_segments_per_cell=segments,
            effective_arc_step_deg=360 / (azimuth_count * segments),
            area_geometry="spherical great-circle polygon subcells",
            geometry_sha256=digest.hexdigest(), construction_s=perf_counter() - started,
            method="first_order_conservative_DSTAREA", source_bounds_policy="supplied_only",
            reference="10.1175/MWR-D-14-00343.1", full_coverage_tolerance=1e-8,
        )
        snapshot = source[["lon", "lat", "lon_b", "lat_b"]].copy(deep=True)
        return cls(snapshot, geometry, weights, source_area, source_overlap_area, dims)

    def apply(self, field, *, source_representation):
        """Remap declared scalar cell means; dynamic NaN/Inf masks are per call.

        Full-cell means require full valid coverage. Covered means/integrals
        describe only observed overlap; no zero-valued full-cell fill is exposed.
        Dask horizontal axes must each be a single chunk; leading axes may stream.
        """
        if source_representation != "scalar_cell_mean":
            raise ValueError("Prototype requires source_representation='scalar_cell_mean'")
        if not np.issubdtype(field.dtype, np.number) or np.iscomplexobj(field):
            raise ValueError("Scalar field must be real numerical data")
        if not isinstance(field.attrs.get("units"), str) or not field.attrs["units"].strip():
            raise ValueError("Scalar field requires declared units")
        if set(CELL_DIMS) & set(field.dims):
            raise ValueError("Input must not already contain polar cell dimensions")
        for dim in self.horizontal_dims:
            if dim not in field.coords or not field[dim].equals(self.source[dim]):
                raise ValueError(f"Field {dim} coordinates differ from plan source")
            if field.chunks and len(field.chunksizes[dim]) > 1:
                raise ValueError("Rechunk each horizontal dimension to one chunk before remapping")
        for name in ("lon", "lat"):
            if name in field.coords and not field[name].equals(self.source[name]):
                raise ValueError(f"Field {name} geography differs from plan source")
        shape = tuple(self.geometry.sizes[dim] for dim in CELL_DIMS)

        def multiply(values):
            leading = values.shape[:-2]
            flat = values.reshape((-1, self.weights.shape[1]))
            finite = np.isfinite(flat)
            numerator = (self.weights @ np.where(finite, flat, 0).T).T
            support = (self.weights @ finite.astype(float).T).T
            return (numerator.reshape((*leading, *shape)), support.reshape((*leading, *shape)))

        numerator, support = xr.apply_ufunc(
            multiply, field.reset_coords(drop=True), input_core_dims=[list(self.horizontal_dims)],
            output_core_dims=[list(CELL_DIMS), list(CELL_DIMS)], dask="parallelized",
            output_dtypes=[np.float64, np.float64],
            dask_gufunc_kwargs={"output_sizes": dict(zip(CELL_DIMS, shape))})
        result = self.geometry.copy(deep=True)
        numerator = numerator.assign_coords({dim: result[dim] for dim in CELL_DIMS})
        support = support.assign_coords({dim: result[dim] for dim in CELL_DIMS})
        full = abs(support - 1) <= result.attrs["full_coverage_tolerance"]
        observed = support > 0
        result["valid_area_fraction"] = support
        result["valid_area"] = support * result.cell_area
        result["cell_mean"] = (numerator / support.where(observed)).where(full)
        result["covered_area_mean"] = numerator / support.where(observed)
        result["covered_area_integral"] = (numerator * result.cell_area).where(observed)
        result["full_cell_valid"] = full.astype(np.uint8)
        attrs = point_attributes(field.attrs)
        attrs.pop("cell_methods", None)
        for name in ("cell_mean", "covered_area_mean"):
            result[name].attrs = dict(attrs, cell_methods="area: mean",
                                       cell_measures="area: cell_area" if name == "cell_mean"
                                       else "area: valid_area")
        result.covered_area_integral.attrs.update(
            units=f"{field.attrs['units']} m2", long_name="integral over valid source overlap only")
        result.valid_area_fraction.attrs.update(units="1", long_name="valid area / full cell area")
        result.valid_area.attrs["units"] = "m2"
        result.full_cell_valid.attrs.update(
            units="1", flag_values=np.array([0, 1], dtype=np.uint8), flag_meanings="incomplete complete")
        result.attrs.update(source_field=str(field.name or "unnamed"),
                            source_representation=source_representation,
                            missing_data_policy="full_cell_mean_requires_complete_valid_area")
        return result
