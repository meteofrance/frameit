# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import xarray as xr

from frameit.check.check_functions import check_group_var, check_resolution
from frameit.io.loader import DatasetResources, discover_input_files, resolve_input_files
from frameit.processing.derived.wind import add_speed_from_uv_dict, wind_names
from frameit.processing.extraction import _iter_datasets, extract_data, polar_support_settings
from frameit.processing.tracking.postprocess import enrich_track_with_kinematics
from frameit.processing.wind_collocation import select_vertical_velocity
from frameit.tracking.tracker_core import build_tracker_from_config, make_tracking_dataset
from frameit.utils.logging_helpers import (
    log_global_params_and_presets,
    log_tracker_requested_vars,
    log_user_requested_vars,
)
from frameit.utils.timing import RunTimer

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    ok: bool
    n_files: int
    output_dir: Path
    files: list[Path]


class FrameitRunner:
    def __init__(self, conf, output_dir: Path | None = None, *, input_files=None):
        """
        Parameters
        ----------
        conf : SimulationConfig
            Loaded simulation configuration.
        output_dir : Path or None, optional
            Override for the output directory.  Falls back to ``conf.output_dir``
            when None.
        """
        self.conf = conf
        self.input_files = None if input_files is None else tuple(Path(p) for p in input_files)
        self.resources = DatasetResources()
        self._output_dir_override = output_dir
        self.timer = RunTimer()
        self.ds_user = None  # variables requested by the user
        self.ds_tracker = None  # variables needed by the tracker

        self.track = None  # tracking output

        self.dict_crop_user = None  # user variables cropped to the area of interest

        self.dict_collocated_crop_user = (
            None  # Same as dict_crop_user but winds are collocated at cells mass point
        )

        self.tracker = None
        self.preflight_report = None

    def close(self):
        """Release original lazy input handles after computation/export."""
        self.resources.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def output_dir(self) -> Path:
        return self._output_dir_override or self.conf.output_dir

    def ensure_dirs(self):
        """
        Verify input/output directory paths and create the output directory.

        Raises
        ------
        FileNotFoundError
            If ``conf.data_dir`` does not exist.
        """
        logger.info("Input:  %s", self.conf.data_dir)
        logger.info("Output: %s", self.output_dir)

        created = not self.output_dir.exists()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if created:
            logger.debug("Output directory created")

        if (not self.conf.input_sources and self.input_files is None
                and self.conf.input_files is None
                and not self.conf.data_dir.exists()):
            raise FileNotFoundError(f"Data dir not found: {self.conf.data_dir}")
        logger.debug("Input/output paths verified")

    def find_files(self):
        """
        Resolve the file glob pattern and return the matched input files.

        Skips the MNH timeseries "000" file when ``conf.atm_model == "MNH"``.

        Returns
        -------
        list[Path]
            Sorted list of matched input files.

        Raises
        ------
        FileNotFoundError
            If no files match the glob pattern.
        """
        pattern = self.conf.build_pattern()

        # 1) Log parameters, presets and requested variables
        log_global_params_and_presets(self.conf, pattern)
        log_user_requested_vars(self.conf)
        log_tracker_requested_vars(self.conf)

        # 2) Recherche des fichiers
        if self.input_files is not None:
            files = resolve_input_files(self.input_files, strict=True)
        else:
            files = discover_input_files(self.conf)

        # MNH-specific: skip the '000' timeseries file
        n_before = len(files)
        if self.input_files is None:
            files = [p for p in files if not self.conf.is_mnh_timeseries_name(p)]
        n_skipped = n_before - len(files)
        if n_skipped:
            logger.info("Skipped MNH timeseries '000' file(s): %d", n_skipped)

        if not files:
            raise FileNotFoundError(f"No files correspond to {pattern} within {self.conf.data_dir}")

        logger.info("Input inventory: %d file(s), %s → %s", len(files),
                    files[0].name, files[-1].name)
        for f in files:
            logger.debug("  %s", f.name)

        # Store the file pattern in the config for reference
        self.conf.add_parameter("simu_output_files", pattern)
        return files

    def load_dataset(self):
        """
        Load user and tracker datasets from the matched input files.

        Dispatches to :func:`concat_nc2ds_by_vert_coord` or
        :func:`concat_grib2ds_by_vert_coord` based on ``conf.file_type``.

        Returns
        -------
        tuple[dict, dict, list[Path]]
            ``(dict_user, dict_tracker, files)`` where:

            - ``dict_user``    : ``{group -> xr.Dataset}`` for user variables.
            - ``dict_tracker`` : ``{method -> {group -> xr.Dataset}}`` for tracker variables.
            - ``files``        : list of input file paths.

        Raises
        ------
        ValueError
            If ``conf.file_type`` is not one of "nc", "netcdf", "grib", "grib2".
        """
        files = self.find_files()
        if self.conf.infer_grid_geometry and self.preflight_report is None:
            from frameit.core.preflight import preflight

            self.preflight_report = preflight(self.conf, input_files=files)
        self.tracker = build_tracker_from_config(self.conf)
        file_type = (self.conf.file_type or "").lower()
        time_dim = getattr(self.conf, "name_time_dim", None)

        requested_vars_user = getattr(self.conf, "requested_variables_user", None) or {}
        loading_requests = deepcopy(requested_vars_user)
        self._internal_wind_names = {}
        self._native_cartesian_groups = {}
        polar_requests = getattr(self.conf, "polar_variables", {})
        for group, spec in loading_requests.items():
            variables = list(spec.get("variables", []))
            polar_spec = polar_requests.get(group, {}) if isinstance(polar_requests, dict) else {}
            polar_names = (
                polar_spec.get("variables", []) if isinstance(polar_spec, dict) else polar_spec
            )
            pair = wind_names(self.conf, group)
            from frameit.processing.wind_reference import wind_pairs

            pairs = [(p["u"], p["v"]) for p in wind_pairs(self.conf, group)] or [pair]
            dependencies = []
            for names in pairs:
                if any(name in variables for name in names) or (
                    names == pair and ("wind_speed" in variables or "wind_speed" in polar_names)
                ):
                    dependencies.extend(names)
            if dependencies:
                self._internal_wind_names[group] = [
                    name for name in dict.fromkeys(dependencies) if name not in variables
                ]
                spec["variables"] = list(dict.fromkeys(variables + dependencies))

        tracking_method = getattr(self.conf, "tracking_method", None)
        requested_vars_tracker = getattr(self.conf, "requested_variables_tracker", None) or {}

        if file_type in {"nc", "netcdf", "netcdf4"}:
            from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

            logger.info("Loading NetCDF files (%d files)...", len(files))

            dict_user, dict_tracker = concat_nc2ds_by_vert_coord(
                files,
                user_requested_variables_yaml=loading_requests,
                tracker_requested_variables_by_method_yaml=requested_vars_tracker,
                method=tracking_method,
                concat_dimension=time_dim,
                float_tol=0.5,
                strict=self.input_files is not None,
                resources=self.resources,
                wind_conf=self.conf,
                engine=self.conf.netcdf_engine,
                chunks=self.conf.netcdf_chunks,
                duplicate_time_policy=self.conf.duplicate_time_policy,
                native_output_groups=self._native_cartesian_groups,
            )

        elif file_type == "fa":
            from frameit.io.fa_utils import concat_fa2ds_by_vert_coord

            dict_user, dict_tracker = concat_fa2ds_by_vert_coord(
                files, loading_requests, requested_vars_tracker, method=tracking_method,
                strict=True, resources=self.resources, wind_conf=self.conf,
                duplicate_time_policy=self.conf.duplicate_time_policy,
                native_output_groups=self._native_cartesian_groups,
            )

        elif file_type in {"grib", "grib2"}:
            from frameit.io.grib_utils import concat_grib2ds_by_vert_coord

            logger.info("Loading GRIB files (%d files)...", len(files))
            from frameit.utils.output_paths import OutputPaths

            index_dir = OutputPaths(self.output_dir).cache

            dict_user, dict_tracker = concat_grib2ds_by_vert_coord(
                files,
                user_requested_variables_yaml=loading_requests,
                tracker_requested_variables_by_method_yaml=requested_vars_tracker,
                method=tracking_method,
                index_dir=index_dir,
                float_tol=0.51,
                warn=True,
                strict=self.input_files is not None,
                resources=self.resources,
                duplicate_time_policy=self.conf.duplicate_time_policy,
                wind_conf=self.conf,
                native_output_groups=self._native_cartesian_groups,
                filter_requested=bool(self.conf.simulation_parameter.get("coupled_source_id")),
            )

        else:
            raise ValueError(f"Unsupported file_type: {self.conf.file_type}")

        from frameit.processing.derived.wind import normalize_winds
        from frameit.utils.units import normalize_geography

        dict_user = {g: normalize_geography(ds, self.conf) for g, ds in dict_user.items()}
        from frameit.tracking.pressure_centroid_inputs import is_mnh_centroid

        dict_tracker = {m: {g: (normalize_geography(ds, self.conf) if
                               ((is_mnh_centroid(self.conf) and m == "pressure_centroid") or
                                (self.conf.atm_model == "MNH" and m == "multifield_vortex")) else
                               normalize_winds(normalize_geography(ds, self.conf), self.conf, g))
                            for g, ds in groups.items()}
                        for m, groups in dict_tracker.items()}
        if file_type == "fa" and self.conf.fa_options["native_cubes"]:
            # New FA cubes prepare selected vector components, while magnitude
            # remains an explicitly requested diagnostic. Legacy loaders retain
            # their established output contract.
            dict_user = {g: normalize_winds(ds, self.conf, g) for g, ds in dict_user.items()}
            speed_groups = {g for g, spec in requested_vars_user.items()
                            if "wind_speed" in spec.get("variables", [])}
            requested_speed = {g: ds for g, ds in dict_user.items() if g in speed_groups}
            dict_user.update(add_speed_from_uv_dict(requested_speed, self.conf))
        else:
            dict_user = add_speed_from_uv_dict(dict_user, self.conf)
        # Record the effective per-component transformations, including direct
        # Python API runs which did not call metadata preflight.
        transformations = []
        for group, dataset in dict_user.items():
            for name, value in dataset.data_vars.items():
                keys = ("source_wind_reference_frame", "wind_reference_frame",
                        "wind_rotation_method", "wind_collocation", "w_target_mapping",
                        "w_source_interface_values", "w_mass_target_values")
                record = {key: value.attrs[key] for key in keys if key in value.attrs}
                if record:
                    transformations.append(dict(group=group, variable=name, **record))
        if hasattr(self.conf, "add_parameter"):
            self.conf.add_parameter("wind_transformations", transformations)

        # Check groups and variables
        logger.debug("Checking user datasets")
        check_group_var(dict_user, requested_vars_user)
        logger.debug("Checking tracker datasets")
        req_trk = (requested_vars_tracker or {}).get(tracking_method, {})
        check_group_var(dict_tracker, req_trk)
        if not self.conf.infer_grid_geometry:
            check_resolution(dict_user, self.conf)
        for group, dataset in dict_user.items():
            logger.info("  Loaded %s: %d field(s) · %s", group, len(dataset.data_vars),
                        ", ".join(f"{name}={size}" for name, size in dataset.sizes.items()))

        return dict_user, dict_tracker, files

    def run_tracking(self, ds_tracker) -> xr.Dataset:
        """
        Run the configured tracker and enrich the output with kinematics.

        Parameters
        ----------
        ds_tracker : dict[str, dict[str, xr.Dataset]]
            Hierarchical tracker dataset produced by :meth:`load_dataset`.

        Returns
        -------
        xr.Dataset
            Track dataset containing at least ``cx``, ``cy``, ``lon``, ``lat``,
            ``heading_deg``, ``dist``, and ``speed``.
        """
        if self.tracker is None:
            if self.conf.infer_grid_geometry and not self.conf.grid_geometry:
                from frameit.core.grid_geometry import resolve_geometry

                resolve_geometry(self.conf, _iter_datasets(ds_tracker))
            self.tracker = build_tracker_from_config(self.conf)
        logger.info("Running tracker %s", self.tracker.name)
        track = self.tracker(ds_tracker)

        ds_flat = make_tracking_dataset(ds_tracker, self.tracker.name)
        track = enrich_track_with_kinematics(
            track,
            ds_flat=ds_flat,
            conf=self.conf,
            cx_name="cx",
            cy_name="cy",
        )
        return track

    def run(self, *, benchmark: bool = False):
        """
        Execute the full FrameIt pipeline.

        Steps: directory check → data loading → tracking → extraction →
        optional wind collocation (MNH only) → polar projection.

        Returns
        -------
        RunResult
            ``ok=True`` with the number of processed files and the output directory.
        """
        if self.conf.input_sources:
            from frameit.core.coupled import run_coupled

            return run_coupled(self, benchmark=benchmark)
        log = logging.getLogger("frameit")

        log.info("Simulation: %s", self.conf.simulation_name)

        # Start global timer
        self.timer.start()

        # Check directories
        self.ensure_dirs()

        # Loading data
        with self.timer.section("loading_data"):
            dict_user, dict_tracker, files = self.load_dataset()
            self.ds_user = dict_user
            self.ds_tracker = dict_tracker
            if benchmark:
                for dataset in _iter_datasets((dict_user, dict_tracker)):
                    dataset.load()

        return self.process_loaded(files, benchmark=benchmark)

    def process_loaded(self, files, *, track=None, benchmark=False):
        """Process prepared groups, optionally with centres supplied by a source."""
        log = logging.getLogger("frameit")
        # Tracking step
        with self.timer.section("tracking"):
            self.track = self.run_tracking(self.ds_tracker) if track is None else track
            if benchmark:
                self.track.load()
        log.info("%s: %d time(s)", "Tracking complete" if track is None else
                 "Using supplied geographical centres", self.track.sizes.get("time", 0))

        # Export representation is separate from the prepared analysis branch.
        native_cart = getattr(self.conf, "cartesian_horizontal_winds", "mass_earth") == "native"
        cart_source = self._native_cartesian_groups if native_cart else self.ds_user
        cart_source = select_vertical_velocity(
            cart_source, self.conf, getattr(self.conf, "cartesian_vertical_velocity", "interfaces")
        )
        if native_cart:
            for group, spec in self.conf.requested_variables_user.items():
                if "wind_speed" in spec.get("variables", []) and group in self.ds_user:
                    speed = self.ds_user[group]["wind_speed"]
                    if group not in cart_source:
                        cart_source[group] = speed.to_dataset()
                    else:
                        cart_source[group]["wind_speed"] = speed
        # Extraction step
        log.info("Extracting Cartesian fields: %.1f × %.1f km · %.0f m grid",
                 self.conf.x_boxsize_km, self.conf.y_boxsize_km, self.conf.resolution)
        with self.timer.section("extraction"):
            self.track, self.dict_crop_user = extract_data(
                conf=self.conf,
                ds_user=cart_source,
                ds_tracker=self.ds_tracker,
                track_ds=self.track,
                native_winds=native_cart,
            )
            if benchmark:
                self.track.load()
                for dataset in self.dict_crop_user.values():
                    dataset.load()

        # Polar projection (including optional MNH collocation)
        if self.conf.compute_polar_proj:
            log.info("Projecting polar fields")
        with self.timer.section("polar_projection"):
            self.dict_collocated_crop_user = {}
            if self.conf.compute_polar_proj:
                support_conf = polar_support_settings(self.conf, self.track)
                polar_source = select_vertical_velocity(
                    self.ds_user, self.conf, getattr(self.conf, "polar_vertical_velocity", "mass")
                )
                _, support_fields = extract_data(
                    conf=support_conf, ds_user=polar_source, ds_tracker=self.ds_tracker,
                    track_ds=self.track,
                )
                self.dict_collocated_crop_user = support_fields

            if self.conf.compute_polar_proj:
                from frameit.processing.polar.polar_proj import polar_project

                self.dict_polar_user, self.polar_report = polar_project(
                    support_fields,
                    conf=self.conf,
                    method=self.conf.polar_interpolation_method,
                    track=self.track,
                )
            else:
                self.dict_polar_user, self.polar_report = {}, {}
            if benchmark:
                for dataset in (
                    *self.dict_crop_user.values(), *self.dict_polar_user.values(),
                    *(self.dict_collocated_crop_user or {}).values(),
                ):
                    dataset.load()

        for group, names in getattr(self, "_internal_wind_names", {}).items():
            if group in self.dict_crop_user:
                original = self.conf.requested_variables_user[group].get("variables", [])
                drop = list(names)
                if "wind_speed" not in original and not all(
                    name in original for name in wind_names(self.conf, group)
                ):
                    drop.append("wind_speed")
                self.dict_crop_user[group] = self.dict_crop_user[group].drop_vars(
                    drop, errors="ignore"
                )

        for group, dataset in list(self.dict_crop_user.items()):
            used = {dim for value in dataset.data_vars.values() for dim in value.dims}
            private_axes = {f"{axis}_{suffix}_box" for axis in ("x", "y") for suffix in ("u", "v")}
            private_axes |= {f"{axis}_{suffix}" for axis in (
                self.conf.name_lon_dim, self.conf.name_lat_dim) for suffix in ("u", "v")}
            unused = (set(dataset.dims) & private_axes) - used
            if unused:
                dataset = dataset.drop_dims(unused)
            dataset.attrs.update(
                horizontal_wind_representation=getattr(
                    self.conf, "cartesian_horizontal_winds", "mass_earth"),
                vertical_velocity_representation=getattr(
                    self.conf, "cartesian_vertical_velocity", "interfaces"),
            )
            self.dict_crop_user[group] = dataset

        return RunResult(ok=True, n_files=len(files), output_dir=self.output_dir, files=files)
