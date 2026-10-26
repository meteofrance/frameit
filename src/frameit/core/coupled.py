"""One geographic track, independently sampled named sources, exact time policy."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import xarray as xr

from frameit.core.configuration import resolved_configuration, source_document
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources, discover_input_files

log = logging.getLogger(__name__)


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


def _inventory(conf):
    from frameit.core.preflight import infer_format, open_metadata

    files = discover_input_files(conf)
    conf.file_type = infer_format(files, conf.file_type or None)
    records = []
    probe = conf.copy()
    probe.requested_variables_user = {}
    for path in files:
        times, references = set(), set()
        if conf.file_type == "fa":
            from frameit.io.fa_backend import inspect_fa

            info = inspect_fa(path, conf.fa_options["profile"],
                              expected_source=conf.fa_options["expected_source"],
                              timeout_seconds=conf.fa_options["timeout_seconds"])
            times = _stamps([np.datetime64(info["valid_time"])], str(path))
            references = {info["reference_time"]}
        else:
            with DatasetResources() as resources:
                for _, datasets in open_metadata([path], probe, resources):
                    for ds in datasets:
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
    return records


def align_source_times(inventories, policy="common", track_times=None):
    """No nearest-time matching, interpolation, filling or silent truncation."""
    sets = {name: {time for entry in entries for time in entry["times"]}
            for name, entries in inventories.items()}
    if policy not in {"common", "strict"}:
        raise ValueError("time alignment must be common or strict")
    union = set.union(*sets.values())
    common = set.intersection(*sets.values())
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
        }
        if skipped:
            log.warning("Source %s: exact-common-time alignment skips %d timestamp(s): %s%s; "
                        "full list recorded in time_alignment provenance", name, len(skipped),
                        ", ".join(skipped[:10]), " ..." if len(skipped) > 10 else "")
    return report


def prepare_sources(conf, *, check_output=True, execution_options=None):
    """Discover times first; scientifically validate only the selected records."""
    from frameit.core.preflight import preflight

    children = {name: SimulationConfig.from_mapping_with_model_preset(
        source_document(conf.yaml_config, name)) for name in conf.input_sources}
    inventories = {name: _inventory(child) for name, child in children.items()}
    track_times = None
    if conf.tracking_method == "prescribed_track":
        from frameit.io.track_file import load_track_coordinates

        track = load_track_coordinates(conf.prescribed_track_file,
                                       time_name=conf.prescribed_track_time_name,
                                       latitude_name=conf.prescribed_track_lat_name,
                                       longitude_name=conf.prescribed_track_lon_name)
        track_times = _stamps(track.time.values, "prescribed track")
    alignment = align_source_times(inventories, conf.time_alignment, track_times)
    selected = set(alignment["selected_times"])
    plans = {}
    known_cycles = []
    for name, child in children.items():
        entries = [item for item in inventories[name] if set(item["times"]) & selected]
        references = {time for entry in entries for time in entry["reference_times"]}
        if len(references) > 1:
            raise ValueError(f"Source {name}: select one forecast cycle explicitly")
        if references:
            known_cycles.append((name, references))
        child.input_files = [entry["path"] for entry in entries]
        plans[name] = preflight(child, input_files=child.input_files, check_output=False,
                                execution_options=execution_options)
        resolved = resolved_configuration(child)
        conf.yaml_config["input"]["sources"][name] = {
            key: resolved[key] for key in ("model", "input", "variables", "polar")}
    if known_cycles and any(cycle != known_cycles[0][1] for _, cycle in known_cycles):
        raise ValueError(f"Coupled forecast cycles disagree: {known_cycles}")
    if conf.tracking_method == "pressure_centroid" and len(selected) < 2:
        raise ValueError("pressure_centroid requires at least two exact common times")
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
    products = []
    if options.export_netcdf:
        products.append(str(prefix) + ".track.nc")
        for name, child in children.items():
            if options.export_cart:
                for group in child.requests_user():
                    products.append(str(prefix) +
                                    f".cart.{name}.{_sanitize_filename_token(group)}.nc")
            if options.export_polar and child.compute_polar_proj:
                for group in child.polar_variables:
                    products.append(str(prefix) +
                                    f".polar.{name}.{_sanitize_filename_token(group)}.nc")
    plan = {"configuration": resolved_configuration(conf, execution_options),
            "grid_geometry": conf.grid_geometry, "time_alignment": alignment,
            "tracking_source": conf.tracking_source, "tracking_method": conf.tracking_method,
            "track_time_count": len(selected), "output_directory": str(conf.output_dir),
            "inputs": [{"source": name, **item}
                       for name, items in inventories.items() for item in items],
            "sources": {name: {key: value for key, value in plans[name].items()
                                if key not in {"configuration", "setting_sources"}}
                        for name in children}, "planned_products": products}
    return plan, children, plans


def _select_times(tree, times):
    if isinstance(tree, xr.Dataset):
        return tree.sel(time=times) if "time" in tree.dims else tree
    return {key: _select_times(value, times) for key, value in tree.items()}


def _mapped_track(track, source, conf):
    from frameit.tracking.geographic import nearest_grid_point

    lat, lon = source[conf.name_latitude], source[conf.name_longitude]
    for dim in ("time", conf.name_time_dim):
        if dim in lat.dims:
            lat = lat.isel({dim: 0}, drop=True)
        if dim in lon.dims:
            lon = lon.isel({dim: 0}, drop=True)
    if lat.ndim == lon.ndim == 2:
        axes = conf.name_lat_dim, conf.name_lon_dim
        lat, lon = lat.transpose(*axes), lon.transpose(*axes)
    result = track.copy(deep=False)
    cy, cx = [], []
    for latitude, longitude in zip(track.lat.values, track.lon.values, strict=True):
        if not _inside_grid(lat, lon, float(latitude), float(longitude), source, conf):
            raise ValueError("A coupled geographic centre is outside a selected source grid; "
                             "no edge-point substitution or spatial time skipping is permitted")
        j, i = nearest_grid_point(lat, lon, float(latitude), float(longitude),
                                  axes=(conf.name_lat_dim, conf.name_lon_dim))
        cy.append(j)
        cx.append(i)
    result["cy"] = ("time", cy)
    result["cx"] = ("time", cx)
    return result


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
    for name, consumer in consumers.items():
        geometry = make_tracking_dataset(consumer.ds_tracker, consumer.conf.tracking_method)
        source_track = (track if name == conf.tracking_source else
                        _mapped_track(track, geometry, consumer.conf))
        consumer.process_loaded(files=[], track=source_track, benchmark=benchmark)
        for section in ("extraction", "polar_projection"):
            runner.timer.sections[section] = (runner.timer.sections.get(section, 0.)
                                              + consumer.timer.sections.get(section, 0.))
        for axis in ("cx", "cy", "valid_box", "ix_min", "ix_max", "iy_min", "iy_max"):
            if axis not in consumer.track:
                continue
            variable = f"{name}_{axis}"
            if variable in runner.track:
                raise ValueError(f"Source index name conflicts with track variable {variable}")
            runner.track[variable] = consumer.track[axis].assign_attrs(
                source_id=name,
                long_name=f"{axis} in {name}'s selected source grid (indices zero-based)")
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
        source_provenance["wind_transformations"] = consumer.conf.simulation_parameter.get(
            "wind_transformations", [])
        source_provenance["fa_inputs"] = consumer.conf.simulation_parameter.get(
            "fa_inputs", source_provenance["fa_inputs"])
    return RunResult(ok=True, n_files=len(files), output_dir=runner.output_dir, files=files)
