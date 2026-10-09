# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

import logging
from dataclasses import dataclass
from pathlib import Path

import xarray as xr

from frameit.check.check_functions import check_group_var, check_resolution
from frameit.io.loader import DatasetResources, discover_input_files, resolve_input_files
from frameit.processing.extraction import extract_data
from frameit.processing.tracking.postprocess import enrich_track_with_kinematics
from frameit.processing.wind_collocation import collocate_winds
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

        self.tracker = build_tracker_from_config(conf)

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
        logger.info("Data path (YAML): %s", self.conf.data_dir)
        logger.info("Output path  (YAML): %s", self.conf.output_dir)
        logger.info("Log path: %s", self.output_dir)

        created = not self.output_dir.exists()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if created:
            logger.info("Output directory created")

        if not self.conf.data_dir.exists():
            raise FileNotFoundError(f"Data dir not found: {self.conf.data_dir}")
        logger.info("Paths : OK")

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

        logger.info("Found (%d) files:", len(files))
        for f in files:
            logger.info("\t\t\t- %s", f.name, extra={"noprefix": True})

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
        file_type = (self.conf.file_type or "").lower()
        time_dim = getattr(self.conf, "name_time_dim", None)

        requested_vars_user = getattr(self.conf, "requested_variables_user", None) or {}

        tracking_method = getattr(self.conf, "tracking_method", None)
        requested_vars_tracker = getattr(self.conf, "requested_variables_tracker", None) or {}

        if file_type in {"nc", "netcdf", "netcdf4"}:
            from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord

            logger.info("Loading NetCDF files (%d files)...", len(files))

            dict_user, dict_tracker = concat_nc2ds_by_vert_coord(
                files,
                user_requested_variables_yaml=requested_vars_user,
                tracker_requested_variables_by_method_yaml=requested_vars_tracker,
                method=tracking_method,
                concat_dimension=time_dim,
                float_tol=0.5,
                strict=self.input_files is not None,
                resources=self.resources,
            )

        elif file_type in {"grib", "grib2"}:
            from frameit.io.grib_utils import concat_grib2ds_by_vert_coord

            logger.info("Loading GRIB files (%d files)...", len(files))
            index_dir = Path(self.output_dir) / ".cfgrib"

            dict_user, dict_tracker = concat_grib2ds_by_vert_coord(
                files,
                user_requested_variables_yaml=requested_vars_user,
                tracker_requested_variables_by_method_yaml=requested_vars_tracker,
                method=tracking_method,
                index_dir=index_dir,
                float_tol=0.51,
                warn=True,
                strict=self.input_files is not None,
                resources=self.resources,
            )

        else:
            raise ValueError(f"Unsupported file_type: {self.conf.file_type}")

        # Check groups and variables
        logger.info("Datasets asked by user:")
        check_group_var(dict_user, requested_vars_user)
        logger.info("Datasets asked by tracker:")
        req_trk = (requested_vars_tracker or {}).get(tracking_method, {})
        check_group_var(dict_tracker, req_trk)
        check_resolution(dict_user, self.conf)

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

    def run(self):
        """
        Execute the full FrameIt pipeline.

        Steps: directory check → data loading → tracking → extraction →
        optional wind collocation (MNH only) → polar projection.

        Returns
        -------
        RunResult
            ``ok=True`` with the number of processed files and the output directory.
        """
        log = logging.getLogger("frameit")

        log.info("Extraction of simulation: %s", self.conf.simulation_name)

        # Start global timer
        self.timer.start()

        # Check directories
        self.ensure_dirs()

        # Loading data
        with self.timer.section("loading_data"):
            dict_user, dict_tracker, files = self.load_dataset()
            self.ds_user = dict_user
            self.ds_tracker = dict_tracker

        # Tracking step
        with self.timer.section("tracking"):
            self.track = self.run_tracking(self.ds_tracker)

        # Extraction step
        with self.timer.section("extraction"):
            self.track, self.dict_crop_user = extract_data(
                conf=self.conf,
                ds_user=self.ds_user,
                ds_tracker=self.ds_tracker,
                track_ds=self.track,
            )

        # Polar projection (including optional MNH collocation)
        with self.timer.section("polar_projection"):
            atm_model = str(getattr(self.conf, "atm_model", "")).upper()

            if atm_model == "MNH":
                self.dict_collocated_crop_user = collocate_winds(
                    self.dict_crop_user,
                    conf=self.conf,
                    policy="partial",
                )
                src_dict = self.dict_collocated_crop_user
            else:
                src_dict = self.dict_crop_user

            if self.conf.compute_polar_proj:
                from frameit.processing.polar.polar_proj import polar_project

                self.dict_polar_user, self.polar_report = polar_project(
                    src_dict,
                    conf=self.conf,
                    method="bilinear",
                )
            else:
                self.dict_polar_user, self.polar_report = {}, {}

        return RunResult(ok=True, n_files=len(files), output_dir=self.output_dir, files=files)
