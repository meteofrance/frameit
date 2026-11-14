"""One geographic track, independently sampled named sources, exact time policy."""

from __future__ import annotations

import logging
import os
from copy import copy, deepcopy
from pathlib import Path

import numpy as np
import xarray as xr

from frameit.core.configuration import resolved_configuration, source_document
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources, discover_input_files

log = logging.getLogger(__name__)


def _association_report(value):
    """Portable time/geometry facts without changing the executable source clocks."""
    import cftime

    if isinstance(value, dict):
        return {key: _association_report(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_association_report(item) for item in value]
    if isinstance(value, (np.datetime64, cftime.datetime)):
        return str(value)
    return value


def _shared_polar_target(conf, children, plans, requested, time_count):
    """Resolve one explicitly selected target; native grids and masks stay separate."""
    from frameit.processing.polar.sampling import check_point_budget, sampling_axes

    participants = {name: child for name, child in children.items()
                    if child.compute_polar_proj and any(
                        spec.get("variables") for spec in child.polar_variables.values())}
    if not conf.polar_shared_target or not participants:
        return None
    if conf.tracking_source not in participants:
        raise ValueError("polar.shared_target requires polar fields on tracking.source")
    reference = participants[conf.tracking_source]
    explicit = {float(requested[name]["radial_step_m"]) for name in participants
                if requested[name]["radial_step_m"] is not None}
    if len(explicit) > 1:
        raise ValueError("polar.shared_target: conflicting source radial_step_m declarations")
    radial = next(iter(explicit)) if explicit else max(c.resolution for c in participants.values())
    if any(radial < c.resolution for c in participants.values()):
        raise ValueError("polar.shared_target radial_step_m is finer than "
                         "a participating native grid")
    reference_sampling = copy(reference)
    reference_sampling.radial_resolution = radial
    reference_sampling.polar_n_theta = requested[conf.tracking_source]["azimuth_count"]
    reference_sampling.azimuthal_resolution = requested[conf.tracking_source]["azimuth_step_deg"]
    radii, angles, metadata = sampling_axes(reference_sampling)
    for name, child in participants.items():
        candidate = copy(child)
        candidate.radial_resolution = radial
        candidate.polar_n_theta = requested[name]["azimuth_count"]
        candidate.azimuthal_resolution = requested[name]["azimuth_step_deg"]
        if candidate.polar_n_theta is None and candidate.azimuthal_resolution is None:
            candidate.polar_n_theta = len(angles)
        other_radii, other_angles, _ = sampling_axes(candidate)
        if (not np.array_equal(other_radii, radii) or not np.array_equal(other_angles, angles)
                or child.polar_ellipsoid != reference.polar_ellipsoid):
            raise ValueError(f"polar.shared_target: source {name} conflicts with tracking-source "
                             "radius/azimuth/ellipsoid; declare common target settings")
        check_point_budget(time_count * len(radii) * len(angles), child.polar_max_points)
    for name, child in participants.items():
        child.radial_resolution = radial
        child.polar_n_theta, child.azimuthal_resolution = len(angles), None
        child.yaml_config["polar"].update(radial_step_m=radial, azimuth_count=len(angles),
                                         azimuth_step_deg=None)
        plans[name]["polar_sampling"] = {
            **metadata, "shared_target": True, "reference_source": conf.tracking_source,
            "radial_count": len(radii), "estimated_points_per_time": len(radii) * len(angles),
            "estimated_time_count": time_count,
        }
    return {
        "schema_version": 1, "reference_source": conf.tracking_source,
        "participants": list(participants), "radial_step_m": float(radial),
        "radial_step_origin": "explicit" if explicit else "coarsest_participating_native_grid",
        "maximum_radius_km": float(radii[-1]), "radial_count": len(radii),
        "azimuth_count": len(angles), "ellipsoid": reference.polar_ellipsoid,
        "native_spacing_m": {name: child.resolution for name, child in participants.items()},
        "requested_sampling": {name: requested[name] for name in participants},
        "centre_definition": "continuous_tracking_source_centres",
        "verification": "pending_exact_output_coordinates",
    }


def _polar_target_signature(dataset, child, track):
    """Hash only target coordinates; do not materialize fields or equate source masks."""
    import hashlib

    centres = (("time", track.time), ("center_lon", track.lon), ("center_lat", track.lat))
    for name, expected in centres:
        if name not in dataset or not np.array_equal(dataset[name].values, expected.values):
            raise ValueError(f"Shared polar target {name} disagrees with "
                             "continuous reference track")
    digest = hashlib.sha256()
    for canonical, name in (("time", "time"), ("radius", "rr"), ("azimuth", "theta"),
                            ("longitude", child.name_longitude), ("latitude", child.name_latitude)):
        if name not in dataset.coords:
            raise ValueError(f"Shared polar target missing coordinate {name}")
        coordinate = dataset[name]
        if canonical in {"longitude", "latitude"}:
            coordinate = coordinate.transpose("time", "rr", "theta")
        values = (np.asarray(coordinate, dtype="datetime64[ns]").view("int64")
                  if canonical == "time" else np.asarray(coordinate, dtype="float64"))
        if canonical != "time" and not np.isfinite(values).all():
            raise ValueError(f"Shared polar target contains nonfinite {name}")
        digest.update(canonical.encode())
        digest.update(str(values.shape).encode())
        digest.update(np.ascontiguousarray(values).tobytes())
    digest.update(child.polar_ellipsoid.encode())
    return digest.hexdigest()


def _stamps(values, context):
    array = np.asarray(values)
    if not np.issubdtype(array.dtype, np.datetime64):
        raise ValueError(f"{context}: coupled inputs require decoded Gregorian "
                         "datetime coordinates")
    if np.isnat(array).any():
        raise ValueError(f"{context}: missing timestamp")
    years = array.astype("datetime64[Y]").astype("int64") + 1970
    if np.any((years < 1678) | (years > 2261)):
        raise ValueError(f"{context}: time is outside the supported nanosecond range")
    return {str(value.astype('datetime64[ns]')) for value in array.reshape(-1)}


def _inventory(conf, *, temporal=False):
    from frameit.core.preflight import infer_format, open_metadata

    files = discover_input_files(conf)
    conf.file_type = infer_format(files, conf.file_type or None)
    records = []
    probe = conf.copy()
    probe.requested_variables_user = {}
    requested = set()
    if temporal:
        from frameit.core.preflight import wind_dependencies

        if conf.file_type != "netcdf":
            raise ValueError("preceding_hour requires named NetCDF sources")
        for request in (conf.requests_user(), conf.requests_tracker().get(conf.tracking_method, {})):
            expanded, _ = wind_dependencies(conf, request)
            requested.update(name for spec in expanded.values() for name in spec.get("variables", [])
                             if name != "wind_speed")
    for path in files:
        times, references = set(), set()
        temporal_fields, cells, collision = {}, [], False
        if conf.file_type == "fa":
            from frameit.io.fa_backend import inspect_fa

            info = inspect_fa(path, conf.fa_options["profile"],
                              expected_source=conf.fa_options["expected_source"],
                              backend=conf.fa_options["backend"],
                              python_executable=conf.fa_options["python_executable"],
                              earth_radius_m=conf.fa_options["earth_radius_m"],
                              timeout_seconds=conf.fa_options["timeout_seconds"])
            times = _stamps([np.datetime64(info["valid_time"])], str(path))
            references = {info["reference_time"]}
        else:
            with DatasetResources() as resources:
                if temporal:
                    from frameit.io.netcdf_utils import normalize_netcdf_time

                    original = resources.add(xr.open_dataset(path, engine=conf.netcdf_engine))
                    metadata = [(path, [normalize_netcdf_time(original, probe)])]
                else:
                    metadata = open_metadata([path], probe, resources)
                for _, datasets in metadata:
                    for ds in datasets:
                        if temporal:
                            native_times = _stamps(ds.time.values, str(path))
                            if len(native_times) != ds.time.size:
                                raise ValueError(f"{path}: duplicate native sample timestamps; "
                                                 "preceding_hour requires unique physical records")
                            temporal_fields.update({name: {key: ds[name].attrs[key] for key in (
                                "cell_methods", "online_operation", "GRIB_stepType") if key in ds[name].attrs}
                                for name in requested & set(ds.data_vars)})
                            collision |= "source_time" in ds
                            if conf.atm_model == "NEMO":
                                bounds = ds.time.attrs.get("bounds")
                                if not bounds or bounds not in ds:
                                    raise ValueError(f"{path}: preceding_hour requires native time bounds")
                                _stamps(ds[bounds].values, str(path))
                                cells = [{"source_time": str(np.datetime64(sample, "ns")),
                                          "start": str(np.datetime64(lo, "ns")),
                                          "end": str(np.datetime64(hi, "ns"))}
                                         for sample, (lo, hi) in zip(ds.time.values, ds[bounds].values, strict=True)]
                        for name in ("time", "valid_time"):
                            if name in ds.coords:
                                calendar = ds[name].encoding.get("calendar", ds[name].attrs.get(
                                    "calendar", "standard"))
                                if calendar not in {"standard", "gregorian", "proleptic_gregorian"}:
                                    raise ValueError(
                                        f"{path}: unsupported coupled calendar {calendar}")
                                times.update(_stamps(ds[name].values, str(path)))
                        if "forecast_reference_time" in ds.coords:
                            references.update(_stamps(ds.forecast_reference_time.values, str(path)))
                        references.update(ds.attrs.get("_frameit_forecast_reference_times", []))
        if not times:
            raise ValueError(f"{path}: no valid source timestamps")
        records.append({"path": str(path), "times": sorted(times),
                        "reference_times": sorted(str(np.datetime64(t, 'ns')) for t in references)})
        if temporal:
            records[-1].update(temporal_fields=temporal_fields, time_cells=cells,
                               source_time_conflict=collision)
    return records


def align_source_times(inventories, policy="common", track_times=None):
    """No nearest-time matching, interpolation, filling or silent truncation."""
    sets = {name: {time for entry in entries for time in entry["times"]}
            for name, entries in inventories.items()}
    if policy not in {"exact", "common", "strict"}:
        raise ValueError("time alignment must be exact, common or strict")
    union = set.union(*sets.values())
    common = set.intersection(*sets.values())
    if policy == "exact":
        if track_times is not None and union - track_times:
            raise ValueError("Missing centres at selected source times: "
                             f"{sorted(union - track_times)}")
        return {"policy": policy, "selected_times": sorted(union), "sources": {
            name: {"available_count": len(values), "selected_count": len(values),
                   "skipped_times": [], "missing_times": [], "skipped_files": [],
                   "associations": [{"source_time": time, "coupling_time": time,
                                     "offset_seconds": 0.} for time in sorted(values)]}
            for name, values in sets.items()}}
    if policy == "strict" and any(values != union for values in sets.values()):
        details = {name: sorted(union - values) for name, values in sets.items()}
        raise ValueError(f"Strict source time alignment failed; missing timestamps: {details}")
    if track_times is not None:
        if policy == "strict" and common - track_times:
            raise ValueError("Prescribed track lacks strict source times: "
                             f"{sorted(common - track_times)}")
        common &= track_times
    if not common:
        raise ValueError("Sources/prescribed track have no exact common timestamps")
    report = {"policy": policy, "selected_times": sorted(common), "sources": {}}
    for name, values in sets.items():
        skipped = sorted(values - common)
        report["sources"][name] = {
            "available_count": len(values), "selected_count": len(common),
            "skipped_times": skipped, "missing_times": sorted(union - values),
            "skipped_files": [Path(entry["path"]).name for entry in inventories[name]
                              if not set(entry["times"]) & common],
            "associations": [{"source_time": time, "coupling_time": time,
                              "offset_seconds": 0.} for time in sorted(common)],
        }
        if skipped:
            log.warning("Source %s: exact-common-time alignment skips %d timestamp(s): %s%s; "
                        "full list recorded in time_alignment provenance", name, len(skipped),
                        ", ".join(map(str, skipped[:10])), " ..." if len(skipped) > 10 else "")
    return report


def _region_grid(conf, source, grid_id):
    """Use each inventoried native grid, never the atmosphere's indices for another source."""
    from frameit.core.grid_geometry import resolve_geometry
    from frameit.processing.dims_utils import horizontal_axes
    from frameit.utils.units import normalize_geography

    grid = (source["native_grids"][grid_id] if grid_id in source["native_grids"]
            else source["representation_grids"][grid_id])
    geometry = xr.Dataset(coords={
        name: xr.Variable(item["dimensions"], item["values"], attrs=item["attributes"])
        for name, item in grid["coordinates"].items()}, attrs=deepcopy(grid.get("fa_geometry", {})))
    temporal = {}
    for record in source["records"]:
        if record["grid_id"] == grid_id:
            for dim, position in record["locator"].get("coordinate_indexers", {}).items():
                if dim in geometry.dims:
                    temporal.setdefault(dim, set()).add(position)
    geometry = geometry.isel({dim: sorted(indices) for dim, indices in temporal.items()})
    settings = copy(conf)
    for kind, conventional in (
            ("latitude", {"latitude", "nav_lat", "lat_rho", "lat_u", "lat_v"}),
            ("longitude", {"longitude", "nav_lon", "lon_rho", "lon_u", "lon_v"})):
        candidates = [name for name in geometry.coords if
                      geometry[name].attrs.get("standard_name") == kind or name in conventional]
        if len(candidates) != 1:
            raise ValueError(f"Regional {kind} is missing or ambiguous on native grid {grid_id}")
        setattr(settings, f"name_{kind}", candidates[0])
    lat, lon = geometry[settings.name_latitude], geometry[settings.name_longitude]
    spatial = (set(lat.dims) | set(lon.dims)) - {"time", settings.name_time_dim}
    axes = horizontal_axes(settings)[1]
    if settings.atm_model == "AROME":
        axes.update(y="y", x="x")  # Selected AROME adapters also use named y/x axes.
    for axis, attribute in (("y", "name_lat_dim"), ("x", "name_lon_dim")):
        candidates = [dim for dim in spatial if axes.get(dim) == axis or (
            dim in geometry.coords and geometry[dim].attrs.get("axis") == axis.upper())]
        if len(spatial) != 2 or len(candidates) != 1:
            raise ValueError("Regional extraction requires unambiguous native horizontal axes")
        setattr(settings, attribute, candidates[0])
    if settings.name_lat_dim == settings.name_lon_dim:
        raise ValueError("Regional extraction requires distinct native horizontal axes")
    geometry = normalize_geography(geometry, settings)
    settings.grid_geometry = {}
    # Native geometry inspection does not plan or execute a polar target.
    settings.compute_polar_proj = False
    resolve_geometry(settings, [geometry])
    return geometry, settings


def _region_facts(track, geometry, settings):
    """Requested/realised native geometry, using the same box rounding as extraction."""
    from frameit.processing.extraction import center2box

    facts = {
        "requested_latitude": track.lat.values.tolist(),
        "requested_longitude": track.lon.values.tolist(),
        "native_x_indices": track.cx.values.tolist(), "native_y_indices": track.cy.values.tolist(),
        "orientation": "native source x/y; no basis rotation"}
    if settings.x_boxsize_km and settings.y_boxsize_km:
        box = center2box(track, settings.x_boxsize_km, settings.y_boxsize_km,
                         settings.resolution, geometry.sizes[settings.name_lon_dim],
                         geometry.sizes[settings.name_lat_dim], inplace=False)
        facts.update(
            requested_width_km={"x": settings.x_boxsize_km, "y": settings.y_boxsize_km},
            realised_span_km={axis: 2 * box.attrs[f"box_half_width_{axis}_points"]
                             * settings.resolution / 1000 for axis in ("x", "y")},
            coverage_fraction=((box.ix_max_domain - box.ix_min_domain + 1)
                               * (box.iy_max_domain - box.iy_min_domain + 1)
                               / (box.attrs["box_nx_points"]
                                  * box.attrs["box_ny_points"])).values.tolist())
    return facts


def _prepare_v3_regions(conf, children, plans):
    """Metadata-only coverage/geometry; calculated positions remain value-dependent."""
    region = conf.yaml_config["region"]
    if not region:
        return
    if conf.time_alignment == "preceding_hour" and any(
            source["format"] != "netcdf" for source in plans.values()):
        raise ValueError("preceding_hour requires named NetCDF sources")
    unresolved = [source["tracker_support_pending"] for source in plans.values()
                  if source.get("tracker_support_pending")]
    if unresolved:
        # Inspection retains unfinished candidates; the execution binder still fails closed.
        conf.tracking_source = None
        for source in plans.values():
            source["region"] = {"centre_provider": "tracker", "grids": {},
                                "pending": unresolved}
        return
    inventories, records_by_path = {}, {}
    for name, source in plans.items():
        grouped = {}
        for record in source["records"]:
            grouped.setdefault(record["locator"]["path"], []).append(record)
        records_by_path[name] = grouped
        order = {time: index for index, time in enumerate(source["selected_times"])}
        inventories[name] = [{
            "path": entry["path"], "times": sorted(
                {record["time"] for record in grouped.get(entry["path"], [])} & order.keys(),
                key=order.__getitem__)}
            for entry in source["file_inventory"]]
    provider = None
    if "track" in region:
        from frameit.io.track_file import load_track_coordinates

        provider = load_track_coordinates(region["track"]["file"]).rename(
            latitude="lat", longitude="lon")
    atmosphere = next((name for name, plan in plans.items()
                       if plan["physical_type"] == "atmosphere"), None)
    conf.tracking_source = atmosphere if "tracker" in region else None
    track_times = (set(provider.time.values) if provider is not None else
                   set(plans[atmosphere]["selected_times"]) if "tracker" in region else None)
    if conf.time_alignment == "preceding_hour":
        from frameit.core.time_association import align_preceding_hour

        temporal, cycles = {}, []
        for name, source in plans.items():
            entries = []
            known_cycles = {r["cycle"] for r in source["records"] if r["cycle"] is not None}
            if known_cycles:
                cycles.append(known_cycles)
            for entry in source["file_inventory"]:
                records = records_by_path[name].get(entry["path"], [])
                if not records:
                    continue
                fields = {r["name"]: r["temporal_metadata"] for r in records
                          if source["fields"][r["field_id"]]["time_varying"]}
                cells = {(r["time"], *r["time_bounds"]) for r in records
                         if r["time_bounds"] is not None}
                entries.append({"path": entry["path"],
                    "times": sorted(_stamps([r["time"] for r in records], name)),
                    "temporal_fields": fields,
                    "source_time_conflict": any(r["name"] == "source_time" for r in records),
                    "time_cells": [{"source_time": str(np.datetime64(sample, "ns")),
                                    "start": str(np.datetime64(lo, "ns")),
                                    "end": str(np.datetime64(hi, "ns"))}
                                   for sample, lo, hi in sorted(cells)]})
            temporal[name] = entries
        if cycles and any(cycle != cycles[0] for cycle in cycles):
            raise ValueError("preceding_hour: selected forecast cycles disagree")
        track_stamps = None if track_times is None else _stamps(list(track_times), "track")
        alignment = align_preceding_hour(
            temporal, atmosphere, {name: child.atm_model for name, child in children.items()},
            track_stamps)
        alignment["selected_times"] = np.asarray(
            alignment["selected_times"], dtype="datetime64[ns]")
        alignment["selected_times"] = list(alignment["selected_times"])
        for report in alignment["sources"].values():
            for record in report["associations"]:
                for key in ("source_time", "coupling_time"):
                    record[key] = np.datetime64(record[key], "ns")
    else:
        alignment = align_source_times(inventories, conf.time_alignment, track_times)
    conf.add_parameter("time_alignment", _association_report(alignment))
    conf.add_parameter("region_alignment", alignment)
    if "center" in region:
        times = alignment["selected_times"]
        provider = xr.Dataset({
            "lat": ("time", [region["center"]["latitude"]] * len(times)),
            "lon": ("time", [region["center"]["longitude"]] * len(times)),
        }, coords={"time": times})
        calendars = {r["calendar"] for source in plans.values() for r in source["records"]}
        if provider.time.dtype.kind == "O":
            if len(calendars) != 1:
                raise ValueError("Fixed trajectory export requires an unambiguous source calendar")
            provider.time.encoding["calendar"] = next(iter(calendars))
    conf.add_parameter("region_centres", provider)
    for name, source in plans.items():
        source["region"] = {"centre_provider": next(iter(
            region.keys() & {"center", "track", "tracker"}), None),
            "associations": alignment["sources"][name]["associations"], "grids": {}}
        # A dependency-only source is not an extraction footprint requirement.
        requests = children[name].source_requests[name]
        tracker_fields = set(source.get("tracker_support", {}).get("inputs", {}))
        if source.get("field_binding") is not None:
            grids = {r["selection_grid_id"]
                     for descriptors in source["field_binding"]["products"].values()
                     for descriptor in descriptors.values() for r in descriptor["records"]}
        else:
            mass_transforms = {field for transform in requests.get("transforms", [])
                               if transform.get("sampling") == "mass"
                               for field in transform["fields"]}
            fields = {field for product, names in requests["exports"].items() for field in names
                      if product != "model_grid" or field not in mass_transforms}
            grids = {r["grid_id"] for r in source["records"] if r["name"] in fields}
        grids.update(r["grid_id"] for r in source["records"] if r["name"] in tracker_fields)
        for grid_id in grids:
            geometry, settings = _region_grid(children[name], source, grid_id)
            facts = {"geometry": settings.grid_geometry,
                     "centres": "pending_calculation" if provider is None else "checked"}
            if provider is not None:
                times = [r["coupling_time"] for r in source["region"]["associations"]]
                mapped = _mapped_track(provider.sel(time=times), geometry, settings)
                facts.update(_region_facts(mapped, geometry, settings))
            source["region"]["grids"][grid_id] = facts


def prepare_sources(conf, *, check_output=True, execution_options=None, resources=None):
    """Discover times first; scientifically validate only the selected records."""
    if getattr(conf, "schema_version", None) == 3:
        return _prepare_v3_sources(conf, check_output=check_output,
                                   execution_options=execution_options, resources=resources)
    from frameit.core.preflight import polar_sampling_plan, preflight

    preceding = conf.time_alignment == "preceding_hour"
    children = {name: SimulationConfig.from_mapping_with_model_preset(
        source_document(conf.yaml_config, name),
        _defer_polar_sampling=conf.polar_shared_target or preceding) for name in conf.input_sources}
    requested_polar = conf.simulation_parameter.setdefault("coupled_polar_requests", {
        name: {key: child.yaml_config["polar"][key] for key in (
            "radial_step_m", "azimuth_count", "azimuth_step_deg", "ellipsoid")}
        for name, child in children.items()})
    inventories = {name: _inventory(child, temporal=preceding) for name, child in children.items()}
    track_times = None
    if conf.tracking_method == "prescribed_track":
        from frameit.io.track_file import load_track_coordinates

        track = load_track_coordinates(conf.prescribed_track_file,
                                       time_name=conf.prescribed_track_time_name,
                                       latitude_name=conf.prescribed_track_lat_name,
                                       longitude_name=conf.prescribed_track_lon_name)
        track_times = _stamps(track.time.values, "prescribed track")
    if preceding:
        from frameit.core.time_association import align_preceding_hour

        alignment = align_preceding_hour(inventories, conf.tracking_source,
                                         {name: child.atm_model for name, child in children.items()}, track_times)
    else:
        alignment = align_source_times(inventories, conf.time_alignment, track_times)
    selected = set(alignment["selected_times"])
    plans = {}
    known_cycles = []
    for name, child in children.items():
        native_times = ({item["source_time"] for item in alignment["sources"][name]["associations"]}
                        if preceding else selected)
        entries = [item for item in inventories[name] if set(item["times"]) & native_times]
        references = {time for entry in entries for time in entry["reference_times"]}
        if len(references) > 1:
            raise ValueError(f"Source {name}: select one forecast cycle explicitly")
        if references:
            known_cycles.append((name, references))
        child.input_files = [entry["path"] for entry in entries]
        plans[name] = preflight(child, input_files=child.input_files, check_output=False,
                                execution_options=execution_options)
    if known_cycles and any(cycle != known_cycles[0][1] for _, cycle in known_cycles):
        raise ValueError(f"Coupled forecast cycles disagree: {known_cycles}")
    if conf.tracking_method == "pressure_centroid" and len(selected) < 2:
        raise ValueError("pressure_centroid requires at least two exact common times")
    shared = _shared_polar_target(conf, children, plans, requested_polar, len(selected))
    conf.add_parameter("common_polar_target", shared)
    for name, child in children.items():
        if child.simulation_parameter.pop("_defer_polar_sampling", False):
            # All native-input, units, frame and grid checks have run. Validate
            # the resolved target now, never an unused fine-grid intermediate.
            child.__post_init__()
            if child.compute_polar_proj:
                count = len(selected) if preceding or (shared is not None and name in shared[
                    "participants"]) else plans[name]["track_time_count"]
                sampling = polar_sampling_plan(child, count)
                plans[name]["polar_sampling"] = {
                    **plans[name].get("polar_sampling", {}), **sampling}
        resolved = resolved_configuration(child)
        resolved["input"] = {key: value for key, value in resolved["input"].items()
                             if key not in {"sources", "time_alignment"}}
        conf.yaml_config["input"]["sources"][name] = {
            key: resolved[key] for key in ("model", "input", "variables", "polar")}
    if check_output:
        parent = conf.output_dir
        while not parent.exists():
            parent = parent.parent
        if not parent.is_dir() or not os.access(parent, os.W_OK):
            raise ValueError(f"Unwritable output destination: {conf.output_dir}")
    reference = children[conf.tracking_source]
    conf.resolution = reference.resolution
    conf.grid_geometry = {
        "tracking_source": conf.tracking_source,
        "sources": {name: child.grid_geometry for name, child in children.items()}}
    conf.add_parameter("time_alignment", alignment)
    conf.add_parameter("source_provenance", {
        name: {"model": child.atm_model, "format": child.file_type,
               "grid_geometry": child.grid_geometry, "inventory": inventories[name],
                "unit_provenance": child.simulation_parameter.get("unit_provenance", []),
                "surfex_provenance": child.simulation_parameter.get("surfex_provenance", []),
                "current_provenance": child.simulation_parameter.get("current_provenance", []),
               "wind_provenance": child.simulation_parameter.get("wind_provenance", []),
               "fa_inputs": child.simulation_parameter.get("fa_inventory", [])}
        for name, child in children.items()})
    for name in children:
        conf.simulation_parameter["source_provenance"][name]["unmapped_grib_records"] = [
            item for entry in plans[name]["inputs"]
            for item in entry.get("unmapped_grib_records", [])]
    from frameit.core.execution import ExecutionOptions
    from frameit.io.netcdf_export import _sanitize_filename_token

    prefix = conf.output_dir / "products" / conf.simulation_name
    options = execution_options or ExecutionOptions.from_config(conf)
    suffix = ".zarr" if options.engine == "zarr" else ".nc"
    products = []
    if options.export_netcdf:
        products.append(str(prefix) + f".track{suffix}")
        for name, child in children.items():
            if options.export_cart:
                for group in child.requests_user():
                    products.append(str(prefix) +
                                     f".cart.{name}.{_sanitize_filename_token(group)}{suffix}")
            if options.export_polar and child.compute_polar_proj:
                for group in child.polar_variables:
                    products.append(str(prefix) +
                                     f".polar.{name}.{_sanitize_filename_token(group)}{suffix}")
    plan = {"configuration": resolved_configuration(conf, execution_options),
            "grid_geometry": conf.grid_geometry, "time_alignment": alignment,
            "tracking_source": conf.tracking_source, "tracking_method": conf.tracking_method,
            "track_time_count": len(selected), "output_directory": str(conf.output_dir),
            "inputs": [{"source": name, **item}
                       for name, items in inventories.items() for item in items],
            "sources": {name: {key: value for key, value in plans[name].items()
                                if key not in {"configuration", "setting_sources"}}
                        for name in children}, "planned_products": products}
    if shared is not None:
        plan["common_polar_target"] = shared
    return plan, children, plans


def _prepare_v3_sources(conf, *, check_output=True, execution_options=None, resources=None):
    """Independent metadata inventories; associations and payloads belong to later tasks."""
    from frameit.core.configuration import _fa_runtime_options, _source_runtime, resolved_sources
    from frameit.core.preflight import inventory_source
    from frameit.io.loader import _apply_model_presets

    children, plans, errors, types = {}, {}, [], {}
    for name in conf.sources:
        runtime = _source_runtime(conf, name)
        if not runtime["file_type"] and "profile" in conf.sources[name]:
            runtime["file_type"] = "fa"
            runtime["fa_options"] = _fa_runtime_options(conf.sources[name])
        child = SimulationConfig(**_apply_model_presets(runtime))
        children[name] = child
        try:
            source = inventory_source(child, name, resources=resources)
            physical = source["physical_type"]
            if physical in types:
                errors.append(f"Allow only one source per physical type {physical}: "
                              f"{types[physical]}, {name}")
            types[physical] = name
            plans[name] = source
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError("\n".join(errors))
    if conf.yaml_config["region"].get("tracker") and "atmosphere" not in types:
        raise ValueError("region.tracker requires an atmospheric source in the selected inventory")
    if conf.yaml_config["region"].get("tracker"):
        from frameit.tracking.tracker_core import resolve_tracker_support

        name = types["atmosphere"]
        try:
            plans[name]["tracker_support"] = resolve_tracker_support(children[name], plans[name])
        except ValueError as exc:
            plans[name]["tracker_support_pending"] = str(exc)
    _prepare_v3_regions(conf, children, plans)
    if check_output:
        destination = conf.output_dir
        while not destination.exists():
            destination = destination.parent
        if not destination.is_dir() or not os.access(destination, os.W_OK):
            raise ValueError(f"Unwritable output destination: {conf.output_dir}")
    request_plan = conf.simulation_parameter["request_plan"]
    request_plan["sources"] = deepcopy(plans)
    request_plan["deferred_checks"] = [
        "Bind fields, levels, units and method dependencies against selected metadata.",
        "Check time associations, geometry, resources and decode-time eligibility.",
        "Read scientific payloads only through selected record locators.",
    ]
    conf.add_parameter("input_inventory", {
        name: list(source["files"]) for name, source in plans.items()})
    if conf.source_name:
        child = children[conf.source_name]
        conf.input_files = child.input_files
        conf.file_type, conf.atm_model = child.file_type, child.atm_model
        if child.file_type == "fa":
            conf.fa_options = deepcopy(child.fa_options)
            for key in ("name_time_dim", "name_lat_dim", "name_lon_dim",
                        "name_latitude", "name_longitude"):
                setattr(conf, key, getattr(child, key))
    report = {
        "configuration": resolved_configuration(conf, execution_options),
        "setting_sources": resolved_sources(conf, execution_options),
        "sources": request_plan["sources"],
        "inputs": [{"source": name, **deepcopy(entry)}
                   for name, source in plans.items() for entry in source["file_inventory"]],
        "planned_products": [str(conf.output_dir / item["path"])
                             for item in request_plan["products"]],
        "warnings": request_plan["warnings"], "deferred_checks": request_plan["deferred_checks"],
        "output_directory": str(conf.output_dir),
    }
    return report, children, plans


def _select_times(tree, times):
    if isinstance(tree, xr.Dataset):
        return tree.sel(time=times) if "time" in tree.dims else tree
    return {key: _select_times(value, times) for key, value in tree.items()}


def bind_sources(conf):
    """Prepare actual consumers once, then copy their bound snapshots to the parent."""
    from frameit.core.preflight import bind_source

    report, children, plans = prepare_sources(conf)
    for name, child in children.items():
        binding = bind_source(child, name)
        if binding["status"] != "bound":
            raise ValueError(f"sources.{name}: cannot execute until requests bind to metadata "
                             f"and methods: {binding['deferred_checks']}")
    _prepare_v3_regions(conf, children, plans)
    for name, child in children.items():
        conf.source_requests[name] = deepcopy(child.source_requests[name])
        conf.simulation_parameter["request_plan"]["sources"][name] = deepcopy(plans[name])
    conf.add_parameter("input_inventory", {
        name: list(source["files"]) for name, source in plans.items()})
    return report, children, plans


def run_native_sources(runner, *, benchmark=False):
    """Native samples, with optional explicit regional centre associations."""
    from frameit.core.runner import FrameitRunner, RunResult

    report, children, plans = runner.prepared_sources
    runner.preflight_report = report
    runner.timer.start()
    runner.ensure_dirs()
    runner.field_products = {}
    centres = runner.conf.simulation_parameter.get("region_centres")
    files = []
    consumers = {}
    with runner.timer.section("loading_data"):
        for name, child in children.items():
            consumer = FrameitRunner(child)
            runner.resources.add(consumer)
            consumer.ds_user, consumer.ds_tracker, source_files = consumer.load_dataset()
            consumers[name] = consumer
            files.extend(source_files)
            if benchmark:
                for dataset in consumer.ds_user.values():
                    dataset.load()
    if runner.conf.yaml_config["region"].get("tracker"):
        from frameit.core.grid_geometry import resolve_geometry
        from frameit.processing.derived.wind import normalize_winds

        name = runner.conf.tracking_source
        consumer = consumers[name]
        internal = consumer.ds_tracker["internal"]
        geometry, settings = _region_grid(consumer.conf, plans[name], next(iter(internal)))
        for attr in ("name_lat_dim", "name_lon_dim", "name_latitude", "name_longitude"):
            setattr(consumer.conf, attr, getattr(settings, attr))
        consumer.conf.resolution = settings.resolution
        resolve_geometry(consumer.conf, [geometry])
        prepared = ({grid: normalize_winds(ds, consumer.conf,
                         "isobaricInhPa" if "isobaricInhPa" in ds.dims else "surface")
                     for grid, ds in internal.items()}
                    if consumer.conf.tracking_method == "wind_pressure"
                    or consumer.conf.atm_model == "AROME" else internal)
        with runner.timer.section("tracking"):
            from frameit.tracking.tracker_core import make_tracking_dataset

            operation_times = [
                r["source_time"] for r in plans[name]["region"]["associations"]]
            selected = make_tracking_dataset(
                {consumer.conf.tracking_method: prepared}, consumer.conf.tracking_method,
                selected_times=operation_times)
            centres = consumer.run_tracking({consumer.conf.tracking_method: {"selected": selected}})
    if centres is not None:
        selected = runner.conf.simulation_parameter["region_alignment"]["selected_times"]
        accepted = set(centres.time.values)
        if not bool(centres.attrs.get("tracking_complete", True)):
            selected = [time for time in selected if time in accepted]
            for source in plans.values():
                source["region"]["incomplete_excluded_times"] = [
                    str(r["source_time"]) for r in source["region"]["associations"]
                    if r["coupling_time"] not in accepted]
                source["region"]["associations"] = [
                    r for r in source["region"]["associations"] if r["coupling_time"] in accepted]
        runner.track = centres.sel(time=selected)
    with runner.timer.section("extraction"):
        for name, consumer in consumers.items():
            child = consumer.conf
            if "model_grid" in child.source_requests[name]["exports"]:
                fields = child.source_requests[name]["exports"]["model_grid"]
                datasets = [ds.reset_coords([field for field in fields if field in ds.coords])
                            for ds in consumer.ds_user.values()]
                if runner.conf.yaml_config["region"]:
                    datasets = [
                        _regional_dataset(ds, grid_id, child, plans[name], centres)
                        for grid_id, ds in consumer.ds_user.items()]
                dataset = xr.merge(datasets, join="exact",
                                   compat="identical", combine_attrs="override")
                runner.field_products[(name, "model_grid")] = dataset.assign_attrs(
                    source_id=name, source_model=plans[name]["model"],
                    source_format=plans[name]["format"])
    runner.conf.add_parameter("source_provenance", {
        name: {"model": source["model"], "format": source["format"],
               "fa_inputs": children[name].simulation_parameter.get("fa_inputs", []),
               "field_metadata": source["metadata_origins"].get("field_metadata", {}),
               "interpretation": source.get("interpretation"),
               "region": _association_report(source.get("region")),
                "tracker_support": source.get("tracker_support"),
                "operations": [
                    {**{key: operation[key] for key in (
                        "name", "product", "method", "inputs", "sampling", "basis",
                        "grid_id", "preparation", "result_units", "rotation_coordinate")},
                     "source_time": str(operation["context"][0]),
                     "cycle": (str(operation["context"][1])
                               if operation["context"][1] is not None else None),
                     "levels": {key: operation["vertical"][key] for key in (
                         "dimension", "source_native_indices", "values", "units", "units_origin")}
                     if operation["vertical"] else None}
                    for operation in source["requests"]["binding"].get("operations", [])],
                "selected_times": [str(time) for time in source["selected_times"]]}
        for name, source in plans.items()})
    if runner.conf.yaml_config["region"]:
        runner.conf.grid_geometry = {
            name: source["region"]["grids"] for name, source in plans.items()}
    return RunResult(ok=True, n_files=len(files), output_dir=runner.output_dir, files=files)


def _regional_dataset(dataset, grid_id, conf, source, centres):
    from frameit.processing.extraction import extract_data

    if not (conf.x_boxsize_km and conf.y_boxsize_km):
        return dataset
    geometry, settings = _region_grid(conf, source, grid_id)
    associations = source["region"]["associations"]
    native = [record["source_time"] for record in associations]
    target = [record["coupling_time"] for record in associations]
    track = centres.sel(time=target).assign_coords(time=native)
    track = _mapped_track(track, geometry, settings)
    source["region"]["grids"].setdefault(grid_id, {}).update(
        _region_facts(track, geometry, settings), centres="checked")
    dataset = dataset.sel(time=native)
    sample_clock = dataset.time
    if conf.x_boxsize_km and conf.y_boxsize_km:
        field_attrs = {name: dict(value.attrs) for name, value in dataset.data_vars.items()}
        time_encoding = {name: {key: value.encoding[key] for key in ("units", "calendar", "dtype")
                               if key in value.encoding}
                         for name, value in dataset.coords.items() if value.dtype.kind == "M"}
        track, cropped = extract_data(
            settings, {grid_id: dataset}, geometry, track, native_winds=True)
        dataset = cropped[grid_id]
        for name, attrs in field_attrs.items():
            dataset[name].attrs = attrs
        for name, encoding in time_encoding.items():
            dataset[name].encoding = encoding
        nx, ny = geometry.sizes[settings.name_lon_dim], geometry.sizes[settings.name_lat_dim]
        covered_x = track.ix_max_domain - track.ix_min_domain + 1
        covered_y = track.iy_max_domain - track.iy_min_domain + 1
        dataset = dataset.assign_coords(region_coverage_fraction=(
            covered_x * covered_y / (track.attrs["box_nx_points"] * track.attrs["box_ny_points"])))
        dataset.attrs.update(
            region_requested_width_x_km=conf.x_boxsize_km,
            region_requested_width_y_km=conf.y_boxsize_km,
            region_realised_span_x_km=2 * track.attrs["box_half_width_x_points"]
                * settings.resolution / 1000,
            region_realised_span_y_km=2 * track.attrs["box_half_width_y_points"]
                * settings.resolution / 1000,
            region_native_shape=f"{ny},{nx}")
    lat, lon = xr.broadcast(geometry[settings.name_latitude], geometry[settings.name_longitude])
    indexers = {settings.name_lat_dim: xr.DataArray(track.cy.values, dims="time"),
                settings.name_lon_dim: xr.DataArray(track.cx.values, dims="time")}
    selected_lat, selected_lon = lat.isel(indexers), lon.isel(indexers)
    dataset = dataset.assign_coords(
        center_latitude=("time", track.lat.values, {"units": "degrees_north"}),
        center_longitude=("time", track.lon.values, {"units": "degrees_east"}),
        center_time=("time", target, {"long_name": "time of the associated geographical centre"}),
        grid_selected_latitude=("time", selected_lat.values, {"units": "degrees_north"}),
        grid_selected_longitude=("time", selected_lon.values, {"units": "degrees_east"}))
    dataset.attrs.update(region_orientation="native source x/y; no basis rotation",
                         time_association=conf.time_alignment)
    return dataset.assign_coords(time=sample_clock)


def _mapped_track(track, source, conf):
    from frameit.tracking.geographic import (
        locate_track,
        uses_native_fa_lookup,
    )

    if uses_native_fa_lookup(source):
        return locate_track(track, source, axes=(conf.name_lat_dim, conf.name_lon_dim),
                            lat_name=conf.name_latitude, lon_name=conf.name_longitude,
                            require_inside=True)

    lat, lon = source[conf.name_latitude], source[conf.name_longitude]
    for dim in ("time", conf.name_time_dim):
        if dim in lat.dims:
            lat = lat.isel({dim: 0}, drop=True)
        if dim in lon.dims:
            lon = lon.isel({dim: 0}, drop=True)
    if lat.ndim == lon.ndim == 2:
        axes = conf.name_lat_dim, conf.name_lon_dim
        lat, lon = lat.transpose(*axes), lon.transpose(*axes)
    for latitude, longitude in zip(track.lat.values, track.lon.values, strict=True):
        if not _inside_grid(lat, lon, float(latitude), float(longitude), source, conf):
            raise ValueError("A coupled geographic centre is outside a selected source grid; "
                             "no edge-point substitution or spatial time skipping is permitted")
    geography = xr.Dataset({conf.name_latitude: lat, conf.name_longitude: lon})
    return locate_track(track, geography, axes=(conf.name_lat_dim, conf.name_lon_dim),
                        lat_name=conf.name_latitude, lon_name=conf.name_longitude)


def _inside_grid(lat, lon, latitude, longitude, source, conf):
    if ("crs" in source.coords
            and source.crs.attrs.get("grid_mapping_name") == "lambert_conformal_conic"):
        from pyproj import CRS, Transformer

        crs = CRS.from_cf(source.crs.attrs)
        x, y = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True).transform(
            longitude, latitude)
        xc, yc = source[conf.name_lon_dim], source[conf.name_lat_dim]
        return float(xc.min()) <= x <= float(xc.max()) and float(yc.min()) <= y <= float(yc.max())
    lat, lon = np.asarray(lat), np.asarray(lon)
    if lat.ndim == lon.ndim == 1:
        axis = np.rad2deg(np.unwrap(np.deg2rad(lon)))
        centre = (axis.min() + axis.max()) / 2
        query = centre + (longitude - centre + 180) % 360 - 180
        return lat.min() <= latitude <= lat.max() and axis.min() <= query <= axis.max()
    # Regional nonfolded structured-grid perimeter, in geographic degrees.
    # This tests containment only; nearest-point selection retains its existing
    # squared-degree convention and is not a geodesic interpolation method.
    def boundary(array):
        return np.concatenate((array[0], array[1:, -1], array[-1, -2::-1], array[-2:0:-1, 0]))

    longitude_axis = np.rad2deg(np.unwrap(np.deg2rad(boundary(lon))))
    centre = (longitude_axis.min() + longitude_axis.max()) / 2
    query = centre + (longitude - centre + 180) % 360 - 180
    x, y = longitude_axis - query, boundary(lat) - latitude
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Coupled extraction needs a finite regional source perimeter")
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cross = x * y1 - x1 * y
    if np.any((np.abs(cross) <= 1.e-12) & (x * x1 + y * y1 <= 0)):
        return True
    crossings = (y > 0) != (y1 > 0)
    return bool(np.count_nonzero((x[crossings] + (x1[crossings] - x[crossings]) *
                                 (-y[crossings]) / (y1[crossings] - y[crossings])) > 0) % 2)


def run_coupled(runner, *, benchmark=False):
    from frameit.core.runner import FrameitRunner, RunResult
    from frameit.tracking.geographic import SNAP_VARIABLES
    from frameit.tracking.tracker_core import make_tracking_dataset

    conf = runner.conf
    runner.timer.start()
    runner.ensure_dirs()
    with runner.timer.section("loading_data"):
        plan, children, plans = prepare_sources(conf)
        runner.preflight_report = plan
        times = np.asarray(plan["time_alignment"]["selected_times"], dtype="datetime64[ns]")
        consumers, files = {}, []
        for name, child in children.items():
            log.info("Loading named source %s (%s)", name, child.file_type)
            child.add_parameter("coupled_source_id", name)
            consumer = FrameitRunner(child)
            runner.resources.add(consumer)
            consumer.timer.start()
            consumer.preflight_report = plans[name]
            consumer.ds_user, consumer.ds_tracker, source_files = consumer.load_dataset()
            if conf.time_alignment == "preceding_hour" and child.atm_model == "NEMO":
                from frameit.core.time_association import associate_preceding_times

                associations = plan["time_alignment"]["sources"][name]["associations"]
                consumer.ds_user = associate_preceding_times(consumer.ds_user, associations)
                consumer.ds_tracker = associate_preceding_times(consumer.ds_tracker, associations)
                consumer._native_cartesian_groups = associate_preceding_times(
                    consumer._native_cartesian_groups, associations)
            else:
                consumer.ds_user = _select_times(consumer.ds_user, times)
                consumer.ds_tracker = _select_times(consumer.ds_tracker, times)
                consumer._native_cartesian_groups = _select_times(
                    consumer._native_cartesian_groups, times)
            consumers[name] = consumer
            files.extend(source_files)
            if benchmark:
                from frameit.processing.extraction import _iter_datasets

                trees = consumer.ds_user, consumer.ds_tracker, consumer._native_cartesian_groups
                for tree in trees:
                    for dataset in _iter_datasets(tree):
                        dataset.load()
    reference = consumers[conf.tracking_source]
    with runner.timer.section("tracking"):
        track = reference.run_tracking(reference.ds_tracker)
    if not np.array_equal(track.time.values, times):
        # Existing permitted shortened tracks remain explicit and share the same
        # selected source times; no secondary source may silently choose others.
        if not set(track.time.values) <= set(times):
            raise ValueError("Tracking produced times outside the aligned source inventory")
    runner.track = track.copy(deep=False)
    runner.track.attrs.update(
        tracking_source=conf.tracking_source, time_alignment_policy=conf.time_alignment,
        time_alignment_skipped_count_convention="per-source timestamp exclusions",
        time_alignment_skipped_count=sum(len(v["skipped_times"])
                                         for v in plan["time_alignment"]["sources"].values()))
    runner.dict_crop_user, runner.dict_polar_user, runner.polar_report = {}, {}, {}
    shared = conf.simulation_parameter.get("common_polar_target")
    for name, consumer in consumers.items():
        geometry = make_tracking_dataset(consumer.ds_tracker, consumer.conf.tracking_method)
        source_track = (track if name == conf.tracking_source else
                        _mapped_track(track, geometry, consumer.conf))
        consumer.process_loaded(files=[], track=source_track, benchmark=benchmark)
        if shared is not None and name in shared["participants"]:
            if not consumer.dict_polar_user:
                raise ValueError(f"Shared polar target source {name} produced "
                                 "no requested polar fields")
            for group, dataset in consumer.dict_polar_user.items():
                signature = _polar_target_signature(dataset, consumer.conf, track)
                if shared.get("target_signature", signature) != signature:
                    raise ValueError(f"Shared polar target mismatch for source {name}, "
                                     f"group {group}")
                shared["target_signature"] = signature
                dataset.attrs.update(common_polar_target_id=signature,
                                     common_polar_reference_source=conf.tracking_source,
                                     common_polar_tracking_method=conf.tracking_method)
        for section in ("extraction", "polar_projection"):
            runner.timer.sections[section] = (runner.timer.sections.get(section, 0.)
                                              + consumer.timer.sections.get(section, 0.))
        snapping = SNAP_VARIABLES
        for axis in ("cx", "cy", "valid_box", "ix_min", "ix_max", "iy_min", "iy_max", *snapping):
            if axis not in consumer.track:
                continue
            variable = f"{name}_{axis}"
            if variable in runner.track:
                raise ValueError(f"Source index name conflicts with track variable {variable}")
            attributes = {"source_id": name}
            if axis not in snapping:
                attributes["long_name"] = (
                    f"{axis} in {name}'s selected source grid (indices zero-based)")
            runner.track[variable] = consumer.track[axis].assign_attrs(**attributes)
        for attribute in ("dict_crop_user", "dict_polar_user"):
            for group, dataset in getattr(consumer, attribute).items():
                dataset = dataset.assign_attrs(source_id=name, source_group=group,
                                               source_model=consumer.conf.atm_model,
                                               source_format=consumer.conf.file_type,
                                               tracking_source=conf.tracking_source,
                                               time_alignment_policy=conf.time_alignment)
                getattr(runner, attribute)[f"{name}.{group}"] = dataset
        runner.polar_report[name] = consumer.polar_report
        source_provenance = conf.simulation_parameter["source_provenance"][name]
        if "tracking_grid_lookup" in source_track.attrs:
            source_provenance["grid_lookup"] = {
                "method": source_track.attrs["tracking_grid_lookup"],
                "offset_convention": source_track.attrs["tracking_snap_convention"],
                "requested_centres": "track.lat / track.lon",
                "selected_centres": f"track.{name}_grid_selected_latitude / "
                                    f"track.{name}_grid_selected_longitude",
                "offsets": [f"track.{name}_{key}" for key in snapping[2:]],
            }
        source_provenance["wind_transformations"] = consumer.conf.simulation_parameter.get(
            "wind_transformations", [])
        source_provenance["fa_inputs"] = consumer.conf.simulation_parameter.get(
            "fa_inputs", source_provenance["fa_inputs"])
    if shared is not None:
        shared["verification"] = "exact_time_radius_azimuth_longitude_latitude"
    return RunResult(ok=True, n_files=len(files), output_dir=runner.output_dir, files=files)
