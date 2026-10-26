"""
FrameIt, core classes.

This module centralises the dataclasses and small utility classes used
to describe and validate a simulation configuration.

Design principles:
- SimulationConfig describes the user configuration.
- Light validation in __post_init__ catches inconsistencies early.
- Helpers build file patterns and paths.

Author: C. SOUFFLET
"""

# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import copy
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from frameit.io.loader import load_config_with_model_presets, resolve_config_with_model_presets

logger = logging.getLogger(__name__)

# Restricted types for a few key fields
ModelName = Literal["AROME", "MNH"]
TrackingMethod = Literal[
    "wind_pressure", "pressure_centroid", "multifield_vortex", "fixed_box",
    "prescribed_track", "utrack"
]


@dataclass
class SimulationConfig:
    # Identity and file pattern
    simulation_name: str
    file_name_prefix: str
    file_name: str
    file_name_suffix: str
    file_type: str  # grib/netcdf/fa, or internal coupled dispatch

    # Models and metadata
    atm_model: ModelName
    ocean_model: str
    wave_model: str
    resolution: int
    comment: str

    # Debug
    DEBUG: bool = False

    # Coordinate dimension names
    name_time_dim: str | None = None
    name_vertical_dim: str | None = None
    name_lat_dim: str | None = None
    name_lon_dim: str | None = None

    # Latitude/longitude coordinate names
    name_latitude: str | None = None
    name_longitude: str | None = None

    # Velocity variable aliases
    velocity_aliases: dict[str, str] = field(default_factory=dict)

    # Fixed subdomain centre
    fix_subdomain_center: list[float] | None = None

    # Tracking
    # ---------
    # Tracker selection
    tracking_method: TrackingMethod = "method"
    # Variables dedicated to tracking
    requested_variables_tracker: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Variable name aliases for trackers
    tracking_var_aliases: dict[str, str] = field(default_factory=dict)
    # Prescribed track
    prescribed_track_file: str = ""
    prescribed_track_time_name: str = "time"
    prescribed_track_lat_name: str = "latitude"
    prescribed_track_lon_name: str = "longitude"
    # Utrack
    utrack_weights_file: str = None
    utrack_use_gpu: bool = False
    utrack_batch_size: int = 16

    # Adaptive pressure centroid (compare_batsirai_centers v1.4.1)
    pressure_centroid_max_iterations: int = 15
    pressure_centroid_tolerance_m: float = 250.0
    pressure_centroid_max_motion_iterations: int = 50
    pressure_centroid_motion_solver: str = "aitken"
    pressure_centroid_motion_relaxation: float = 0.25
    pressure_centroid_motion_tolerance_m: float = 250.0
    pressure_centroid_r80_max_km: float = 250.0
    pressure_centroid_dr_km: float = 2.5
    pressure_centroid_dtheta: float = 5.0
    multifield_vortex: dict[str, Any] = field(default_factory=dict)

    # Variables requested by the user
    requested_variables_user: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Box size (km)
    x_boxsize_km: float = 0
    y_boxsize_km: float = 0

    # Paths
    simulation_output_dir: str = ""
    frameit_output_dir: str = ""

    # Polar projection
    compute_polar_proj: bool = False
    polar_shared_target: bool = False
    radial_resolution: float = 0
    azimuthal_resolution: float | None = None
    polar_n_theta: int | None = None
    polar_max_points: int = 2_000_000
    polar_missing_data_policy: str = "strict"
    polar_min_valid_weight_fraction: float = 0.5
    polar_weight_zero_tolerance: float = 1e-14
    polar_source_halo_points: int = 1
    polar_ellipsoid: str = "WGS84"
    polar_regrid_cache_size: int = 8
    polar_regrid_cache_max_bytes: int = 128 * 1024**2
    polar_output_chunks: dict[str, int] = field(default_factory=dict)
    polar_profile: bool = False
    polar_variables: dict[str, dict[str, Any]] = field(default_factory=dict)
    field_orientation: str = "geodesic"
    wind_reference_frame: str | None = None
    wind_pairs: list[dict[str, Any]] = field(default_factory=list)
    cartesian_horizontal_winds: str = "mass_earth"
    cartesian_vertical_velocity: str = "interfaces"
    polar_vertical_velocity: str = "mass"

    # Derived and runtime parameters
    simulation_parameter: dict[str, Any] = field(default_factory=dict)

    # Legacy configuration field, retained for compatibility. Runtime indexes
    # always live in output_dir/cache, including when the runner overrides it.
    grib_index_dir: str = "cache"

    # Public nested YAML resolves into this internal numerical interface.
    schema_version: int = 1
    yaml_config: dict[str, Any] = field(default_factory=dict)
    schema_sources: dict[str, str] = field(default_factory=dict)
    infer_grid_geometry: bool = False
    grid_geometry: dict[str, Any] = field(default_factory=dict)
    input_pattern: str | None = None
    input_files: list[str] | None = None
    input_exclude: list[str] = field(default_factory=list)
    duplicate_time_policy: str = "first"
    netcdf_engine: str = "h5netcdf"
    netcdf_chunks: dict[str, int] = field(default_factory=dict)
    input_sources: dict[str, Any] = field(default_factory=dict)
    time_alignment: str = "common"
    tracking_source: str | None = None
    fa_options: dict[str, Any] = field(default_factory=dict)
    wind_pressure_search_half_width_km: float = 100.0
    wind_pressure_refine_half_width_km: float = 50.0
    # Shared default for continuous polar point samples; no area-budget guarantee.
    # Methods are selected explicitly, never inferred per variable.
    polar_interpolation_method: str = "bilinear"
    log_level: str | None = None

    # -----------------------
    # Properties
    # -----------------------
    @property
    def data_dir(self) -> Path:
        """
        Root directory containing model output files.

        Returns
        -------
        Path
            ``simulation_output_dir`` as a :class:`Path` object.
        """
        return Path(self.simulation_output_dir)

    @property
    def output_dir(self) -> Path:
        """
        Root directory for FrameIt output files.

        Returns
        -------
        Path
            ``frameit_output_dir`` as a :class:`Path` object.
        """
        return Path(self.frameit_output_dir)

    @property
    def file_pattern(self) -> str:
        """File pattern as defined in the FrameIt documentation."""
        # file_name_prefix + file_name + '???' + file_name_suffix + file_type
        if self.input_pattern is not None:
            return self.input_pattern
        return f"{self.file_name_prefix}{self.file_name}???{self.file_name_suffix}{self.file_type}"

    # -----------------------
    # Utility methods
    # -----------------------
    def build_pattern(self) -> str:
        """
        Return the glob pattern for model output files.

        Returns
        -------
        str
            Pattern built from ``file_name_prefix``, ``file_name``, "???",
            ``file_name_suffix``, and ``file_type``.
        """
        return self.file_pattern

    def add_parameter(self, name: str, value: Any) -> None:
        """
        Store a named derived parameter in ``simulation_parameter``.

        Parameters
        ----------
        name : str
            Parameter key.
        value : Any
            Parameter value.
        """
        self.simulation_parameter[name] = value

    def to_dict(self, include_runtime: bool = True) -> dict[str, Any]:
        """
        Export the configuration as a flat dictionary.

        Parameters
        ----------
        include_runtime : bool, optional
            When False, the ``simulation_parameter`` key (runtime-derived
            values) is removed from the output. Default True.

        Returns
        -------
        dict[str, Any]
            Shallow copy of all configuration fields.
        """
        d = asdict(self)
        if not include_runtime:
            d.pop("simulation_parameter", None)
        return d

    def copy(self) -> SimulationConfig:
        """
        Return a deep copy of this configuration object.

        Returns
        -------
        SimulationConfig
            Independent copy with no shared mutable state.
        """
        return copy.deepcopy(self)

    def printID(self):
        """
        Print all configuration fields to stdout in YAML-compatible format.

        Excludes the ``comment`` field.  Dict and list values are formatted
        as inline YAML blocks.
        """
        import yaml

        d = self.to_dict()
        print(f"SimulationConfig: {getattr(self, 'simulation_name', 'N/A')}")
        for k in sorted(d):
            if k == "comment":
                continue
            v = d[k]
            s = (
                yaml.safe_dump(v, default_flow_style=False, allow_unicode=True).strip()
                if isinstance(v, (dict, list, tuple, set))
                else str(v)
            )
            if "\n" in s:
                s = s.replace("\n", "\n  ")
                print(f"{k}:\n  {s}")
            else:
                print(f"{k}: {s}")

    # -----------------------
    # Validation
    # -----------------------
    def __post_init__(self):
        if type(self.polar_shared_target) is not bool:
            raise ValueError("polar_shared_target must be a boolean")
        if self.file_type == "fa":
            if self.atm_model != "AROME":
                raise ValueError("Current FA profiles require atm_model='AROME'")
            from frameit.core.configuration import (
                DEFAULTS,
                _merge_checked,
                validate_fa_options,
            )

            self.fa_options = _merge_checked(self.fa_options, DEFAULTS["input"]["fa"], "input.fa")
            validate_fa_options(self.fa_options, selected=True)
            for name, value in (("name_time_dim", "time"), ("name_lat_dim", "y"),
                                ("name_lon_dim", "x"), ("name_latitude", "latitude"),
                                ("name_longitude", "longitude")):
                if getattr(self, name) not in {None, value}:
                    raise ValueError(f"FA adapter requires canonical {name}={value!r}")
                setattr(self, name, value)
        from frameit.processing.polar.coverage import validate_mask_options
        from frameit.processing.polar.regrid_plan import validate_execution_options
        from frameit.processing.polar.sampling import sampling_axes, validate_sampling_options

        validate_execution_options(
            self.polar_regrid_cache_size, self.polar_regrid_cache_max_bytes,
            self.polar_output_chunks, self.polar_profile,
        )
        validate_mask_options(
            self.polar_missing_data_policy, self.polar_min_valid_weight_fraction,
            self.polar_weight_zero_tolerance,
        )
        if isinstance(self.polar_source_halo_points, bool) or not isinstance(
            self.polar_source_halo_points, int
        ) or self.polar_source_halo_points < 1:
            raise ValueError("polar_source_halo_points must be an integer of at least one")
        from pyproj import Geod

        try:
            Geod(ellps=self.polar_ellipsoid)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Unknown polar_ellipsoid {self.polar_ellipsoid!r}") from exc
        validate_sampling_options(
            self.polar_n_theta, self.azimuthal_resolution, self.polar_max_points
        )
        from frameit.core.configuration import validate_output_selections, validate_wind_pairs

        validate_wind_pairs(self.wind_pairs)
        validate_output_selections(self.cartesian_horizontal_winds,
                                   self.cartesian_vertical_velocity,
                                   self.polar_vertical_velocity)
        if self.wind_reference_frame is not None and (
            not isinstance(self.wind_reference_frame, str)
            or self.wind_reference_frame not in {"earth", "grid"}
        ):
            raise ValueError("wind_reference_frame must be 'earth', 'grid', or None")
        if self.atm_model not in ("AROME", "MNH"):
            raise ValueError("atm_model must be 'AROME' or 'MNH'")

        if not self.simulation_output_dir:
            raise ValueError("simulation_output_dir must not be empty")
        if not self.frameit_output_dir:
            raise ValueError("frameit_output_dir must not be empty")

        if not isinstance(self.tracking_method, str):
            raise TypeError("tracking_method should be a string")
        import math

        if (isinstance(self.resolution, bool) or not isinstance(self.resolution, (int, float))
                or not math.isfinite(self.resolution)):
            raise TypeError("resolution must be a finite number (in metres)")
        if self.resolution < 0:
            raise ValueError("resolution must not be negative")

        self.file_name_prefix = self.file_name_prefix or ""
        self.file_name_suffix = self.file_name_suffix or ""
        self.file_type = self.file_type or ""

        if (self.compute_polar_proj
                and not self.simulation_parameter.get("_defer_polar_sampling", False)
                and not (self.infer_grid_geometry and not self.grid_geometry)):
            if self.radial_resolution is not None and self.radial_resolution < 0:
                raise ValueError(f"radial_resolution={self.radial_resolution} m must be positive.")
            if not self.radial_resolution:
                logger.warning(
                    "radial_resolution not set, defaulting to native resolution=%d m.",
                    self.resolution,
                )
                self.radial_resolution = float(self.resolution)
            elif self.radial_resolution < self.resolution:
                raise ValueError(
                    f"radial_resolution={self.radial_resolution:.0f} m is finer than "
                    f"the native grid resolution={self.resolution} m. "
                    "Interpolating to a finer radial grid than the source data is not meaningful."
                )
            sampling_axes(self)

    # -----------------------
    # Constructors
    # -----------------------
    @classmethod
    def from_yaml(cls, path: Path | str) -> SimulationConfig:
        """
        Load a configuration from a plain YAML file.

        Parameters
        ----------
        path : Path or str
            Path to the YAML configuration file.

        Returns
        -------
        SimulationConfig
            Configuration object built from the YAML key-value mapping.

        Raises
        ------
        FileNotFoundError
            If ``path`` does not exist.
        ValueError
            If the YAML content is not a key-value mapping.
        """
        return cls.from_yaml_with_model_preset(path)

    @classmethod
    def from_yaml_with_model_preset(
        cls, path: Path | str, *, strict_locked: bool = True
    ) -> SimulationConfig:
        """
        Load a run YAML and merge it with model-dependent preset files.

        Model-dependent keys (coordinate names, tracker variables) are locked
        by the preset and always override values present in the run YAML.

        Parameters
        ----------
        path : Path or str
            Path to the run YAML configuration file.
        strict_locked : bool, optional
            Reserved for future strict enforcement of preset-locked keys.
            Default True.

        Returns
        -------
        SimulationConfig
            Fully merged and validated configuration.
        """
        merged = load_config_with_model_presets(Path(path), strict_locked=strict_locked)
        return cls(**merged)

    @classmethod
    def from_mapping_with_model_preset(
        cls, mapping: dict[str, Any], *, strict_locked: bool = True,
        _defer_polar_sampling: bool = False,
    ) -> SimulationConfig:
        """Resolve an in-memory run mapping with the ordinary model presets."""
        resolved = resolve_config_with_model_presets(mapping, strict_locked=strict_locked)
        if _defer_polar_sampling:
            # Coupled discovery validates inputs/geometry first. Its target is
            # resolved only after every participating native spacing is known.
            resolved.setdefault("simulation_parameter", {})["_defer_polar_sampling"] = True
        return cls(**resolved)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimulationConfig:
        """
        Build a configuration from a plain dictionary.

        Parameters
        ----------
        data : dict[str, Any]
            Mapping of configuration field names to values.

        Returns
        -------
        SimulationConfig
            Configuration object.
        """
        return cls(**data)

    # -----------------------
    # FrameIt-specific helpers
    # -----------------------
    def is_mnh_timeseries_name(self, filename_or_path) -> bool:
        """
        Test whether a file is the MNH "000" timeseries file to be skipped.

        Parameters
        ----------
        filename_or_path : str or Path
            File name or path to test.

        Returns
        -------
        bool
            True only when ``atm_model == "MNH"`` and the file name matches
            the "000" timeseries entry of the current file pattern.
        """
        if self.schema_version == 2 or self.atm_model != "MNH":
            return False

        try:
            pattern = self.build_pattern()  # si ta classe l’a
        except AttributeError:
            pattern = getattr(self, "file_pattern", "")

        ts_name = pattern.replace("???", "000", 1) if "???" in pattern else "000"
        return Path(filename_or_path).name == ts_name

    def requests_user(self) -> dict[str, dict[str, Any]]:
        """
        Return user variable requests, normalizing None to an empty dict.

        Returns
        -------
        dict[str, dict[str, Any]]
            ``requested_variables_user`` or ``{}`` if not set.
        """
        return self.requested_variables_user or {}

    def requests_tracker(self) -> dict[str, dict[str, Any]]:
        """
        Return tracker variable requests, normalizing None to an empty dict.

        Returns
        -------
        dict[str, dict[str, Any]]
            ``requested_variables_tracker`` or ``{}`` if not set.
        """
        return self.requested_variables_tracker or {}

    def expected_variables_user(self) -> list[str]:
        """
        Return the sorted union of all user-requested variable names.

        Returns
        -------
        list[str]
            Sorted list of variable names from all groups in
            ``requested_variables_user``.
        """
        if self.requested_variables_user:
            s: set[str] = set()
            for req in self.requested_variables_user.values():
                s.update(req.get("variables", []))
            return sorted(s)
        return list(self.variables)

    def expected_variables_tracker(self) -> list[str]:
        """
        Return the sorted union of all tracker-requested variable names.

        Returns
        -------
        list[str]
            Sorted list of variable names from all groups in
            ``requested_variables_tracker``.
        """
        if self.requested_variables_tracker:
            s: set[str] = set()
            for req in self.requested_variables_tracker.values():
                s.update(req.get("variables", []))
            return sorted(s)
        return list(self.variables)

    def expected_polar_variables(self) -> list[str]:
        """
        Return the list of group keys to project in polar coordinates.

        Returns
        -------
        list[str]
            Keys of ``polar_variables``.
        """
        return list(self.polar_variables)
