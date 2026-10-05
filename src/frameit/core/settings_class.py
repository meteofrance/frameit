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
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from frameit.io.loader import load_config_with_model_presets

logger = logging.getLogger(__name__)

# Restricted types for a few key fields
ModelName = Literal["AROME", "MNH"]
TrackingMethod = Literal["wind_pressure", "fixed_box", "prescribed_track"]  # extend as needed


@dataclass
class SimulationConfig:
    # Identity and file pattern
    simulation_name: str
    file_name_prefix: str
    file_name: str
    file_name_suffix: str
    file_type: str  # "grib" or "nc"

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
    # Optional first guess [lat0, lon0] (degrees) of the centre at the first output time
    tracking_first_guess: list[float] | None = None
    # Prescribed track
    prescribed_track_file: str = ""
    # Utrack
    utrack_weights_file: str = None
    utrack_use_gpu: bool = False
    utrack_batch_size: int = 16

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
    radial_resolution: float = 0
    azimuthal_resolution: float = 10.0
    polar_variables: dict[str, dict[str, Any]] = field(default_factory=dict)
    field_orientation: str = "geodesic"

    # Derived and runtime parameters
    simulation_parameter: dict[str, Any] = field(default_factory=dict)

    # GRIB index directory
    grib_index_dir: str = ".cfgrib"

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
        if self.atm_model not in ("AROME", "MNH"):
            raise ValueError("atm_model must be 'AROME' or 'MNH'")

        if not self.simulation_output_dir:
            raise ValueError("simulation_output_dir must not be empty")
        if not self.frameit_output_dir:
            raise ValueError("frameit_output_dir must not be empty")

        if not isinstance(self.tracking_method, str):
            raise TypeError("tracking_method should be a string")
        if not isinstance(self.resolution, int):
            raise TypeError("resolution should be an integer (in metres)")

        self.file_name_prefix = self.file_name_prefix or ""
        self.file_name_suffix = self.file_name_suffix or ""
        self.file_type = self.file_type or ""

        if self.tracking_first_guess is not None:
            self.tracking_first_guess = self._validate_first_guess(self.tracking_first_guess)
            if self.tracking_method != "wind_pressure":
                logger.warning(
                    "tracking_first_guess is ignored by tracking_method=%r.",
                    self.tracking_method,
                )

        if self.compute_polar_proj:
            if self.radial_resolution is not None and self.radial_resolution < 0:
                raise ValueError(
                    f"radial_resolution={self.radial_resolution} m must be positive."
                )
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

    @staticmethod
    def _validate_first_guess(value: Any) -> list[float]:
        """
        Validate the ``tracking_first_guess`` setting.

        Parameters
        ----------
        value : Any
            Raw value read from the configuration, expected ``[lat0, lon0]``
            in degrees.

        Returns
        -------
        list of float
            ``[lat0, lon0]`` as floats. The longitude is wrapped into the grid
            convention later, by the tracker.

        Raises
        ------
        ValueError
            If ``value`` is not a pair of finite numbers, or if the latitude
            is outside [-90, 90].
        """
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("tracking_first_guess must be a sequence [lat0, lon0]")
        try:
            lat0, lon0 = (float(v) for v in value)
        except (TypeError, ValueError) as exc:
            raise ValueError("tracking_first_guess values must be numbers") from exc
        if not (math.isfinite(lat0) and math.isfinite(lon0)):
            raise ValueError("tracking_first_guess values must be finite")
        if not -90.0 <= lat0 <= 90.0:
            raise ValueError(f"tracking_first_guess latitude {lat0} is outside [-90, 90]")
        return [lat0, lon0]



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
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"YAML file not found: {p}")
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError("The YAML file must describe a key-value mapping")
        return cls(**data)

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
        if self.atm_model != "MNH":
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
