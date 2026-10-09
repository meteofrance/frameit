# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping
from functools import wraps
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("frameit.io.loader")

DEFAULT_PRESETS_ROOT = Path(__file__).resolve().parents[1] / "presets"


class DatasetResources:
    """Own the original opened datasets until computation and export finish."""

    def __init__(self):
        self._datasets = []
        self._ids = set()

    def add(self, dataset):
        if id(dataset) not in self._ids:
            self._ids.add(id(dataset))
            self._datasets.append(dataset)
        return dataset

    def close_from(self, start=0):
        datasets = self._datasets[start:]
        del self._datasets[start:]
        for dataset in reversed(datasets):
            self._ids.discard(id(dataset))
            try:
                dataset.close()
            except Exception:
                log.exception("Failed to close a loaded dataset")

    def close(self):
        self.close_from()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def managed_loading(function):
    """Give direct loader callers a close hook; roll back failed opens."""

    @wraps(function)
    def wrapper(*args, resources=None, **kwargs):
        owned = resources is None
        registry = resources if resources is not None else DatasetResources()
        start = len(registry._datasets)
        try:
            result = function(*args, resources=registry, **kwargs)
        except BaseException:
            registry.close_from(start)
            raise
        if owned:

            def attach(value):
                if hasattr(value, "set_close"):
                    # Do not overwrite an original backend's close callback
                    # with a callback that would recursively close itself.
                    if id(value) in registry._ids:
                        value = value.copy(deep=False)
                    value.set_close(registry.close)
                    return value
                elif isinstance(value, Mapping):
                    return {key: attach(item) for key, item in value.items()}
                elif isinstance(value, tuple):
                    return tuple(attach(item) for item in value)
                elif isinstance(value, list):
                    return [attach(item) for item in value]
                return value

            result = attach(result)
        return result

    return wrapper


def resolve_input_files(files, *, strict=False):
    """Validate an explicit inventory without sorting or omitting its entries."""
    paths = [Path(path) for path in files]
    missing = [str(path) for path in paths if not path.is_file()]
    if strict and missing:
        raise FileNotFoundError(
            "Resolved input file is missing or not a file: " + ", ".join(missing)
        )
    if not strict:
        paths = sorted(path for path in paths if path.is_file())
    if not paths:
        raise FileNotFoundError("No valid input file found")
    return paths


def discover_input_files(config):
    """Ordinary run discovery, shared with native matrix planning."""
    files = sorted(config.data_dir.glob(config.build_pattern()))
    files = [path for path in files if not config.is_mnh_timeseries_name(path)]
    return resolve_input_files(files, strict=True)


def _load_yaml(p: Path) -> dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"The YAML must be a key-value mapping in {p}")
    return data


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config_with_model_presets(
    run_yaml_path: Path, *, strict_locked: bool = False
) -> dict[str, Any]:
    """
    Load a run YAML file and merge it with model-dependent preset files.

    Model-dependent keys (coordinate names, tracker variables) are always
    taken from the preset files stored under ``frameit/presets/<model>/``
    and override any values present in the run YAML.

    Parameters
    ----------
    run_yaml_path : Path
        Path to the user run YAML file.  Must contain at least ``atm_model``.
    strict_locked : bool, optional
        Reserved for future enforcement of preset-locked keys. Default False.

    Returns
    -------
    dict[str, Any]
        Merged configuration mapping ready to be passed to
        ``SimulationConfig(**merged)``.

    Raises
    ------
    ValueError
        If ``atm_model`` is missing from the run YAML.
    FileNotFoundError
        If the coordinate or tracker preset file for the model is not found.
    """
    return resolve_config_with_model_presets(
        _load_yaml(Path(run_yaml_path)), strict_locked=strict_locked
    )


def resolve_config_with_model_presets(
    mapping: Mapping[str, Any], *, strict_locked: bool = False
) -> dict[str, Any]:
    """Resolve YAML and in-memory configurations through the same presets."""
    if not isinstance(mapping, Mapping):
        raise ValueError("The configuration must be a key-value mapping")
    run = copy.deepcopy(dict(mapping))

    model = run.get("atm_model")
    if not model:
        raise ValueError("atm_model is missing from the run YAML")
    tracking_method = run.get("tracking_method", "wind_pressure")

    model_dir = DEFAULT_PRESETS_ROOT / model
    coords_p = model_dir / "model_name_map.yaml"
    tracker_p = model_dir / "vars_trackers.yaml"
    if not coords_p.exists():
        raise FileNotFoundError(f"coords_dims not found for {model}: {coords_p}")
    if not tracker_p.exists():
        raise FileNotFoundError(f"tracker preset not found for {model}: {tracker_p}")

    coords = _load_yaml(coords_p)
    tracker_yaml_raw = _load_yaml(tracker_p)

    # Wrap the tracker content under a dedicated key for the dataclass.
    # tracker_yaml_raw typically contains 'requested_variables_by_method'.
    if "requested_variables_by_method" in tracker_yaml_raw:
        tracker_wrapped = {
            "requested_variables_tracker": tracker_yaml_raw["requested_variables_by_method"]
        }
    else:
        # Fallback: treat the whole file as a {method: spec} mapping
        tracker_wrapped = {"requested_variables_tracker": tracker_yaml_raw}

    # Keys locked by the presets
    coords_keys = set(coords.keys())
    tracker_keys = set(tracker_wrapped.keys())  # here {"requested_variables_tracker"}
    locked_keys = coords_keys | tracker_keys

    # Warn if the run YAML contained locked keys
    purged = [k for k in sorted(locked_keys) if k in run]
    if purged:
        log.info(
            "Model/tracker-dependent keys overridden by presets: %s",
            ", ".join(purged),
        )

    # Remove locked keys from the run dict, then merge coords -> tracker_wrapped -> run_pruned
    run_pruned = {k: v for k, v in run.items() if k not in locked_keys}
    merged = _deep_merge(coords, tracker_wrapped)
    merged = _deep_merge(merged, run_pruned)

    # Store tracing information
    merged.setdefault("simulation_parameter", {})
    sp = merged["simulation_parameter"]
    sp["preset_model_used"] = str(model)
    sp["preset_coords_path"] = str(coords_p)
    sp["preset_tracker_path"] = str(tracker_p)
    sp["preset_fields_coords_dims"] = {k: merged[k] for k in sorted(coords_keys)}
    sp["preset_fields_tracker"] = {
        k: merged[k] for k in sorted(tracker_keys)
    }  # -> requested_variables_tracker

    # Ensure tracking_method is present
    merged.setdefault("tracking_method", tracking_method)

    return merged
