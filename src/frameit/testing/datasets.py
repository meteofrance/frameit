"""Preparation and read-only verification of the frozen scientific CI fixture."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
import uuid
from importlib import resources
from pathlib import Path

from frameit.io.subset import crop_grib, crop_netcdf, validate_grib_subset

MANIFEST_FORMAT = "frameit-ci-dataset-v2"


def load_ci_recipe():
    import yaml

    resource = resources.files("frameit.testing").joinpath("recipes", "ci.yaml")
    return yaml.safe_load(resource.read_text(encoding="utf-8"))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _times(variable):
    import numpy as np
    from netCDF4 import num2date

    if variable.dimensions != ("time",) or "units" not in variable.ncattrs():
        raise ValueError("NetCDF time must be a one-dimensional CF coordinate")
    values = variable[:]
    if np.ma.getmaskarray(values).any() or not np.isfinite(values).all():
        raise ValueError("NetCDF time coordinate contains missing/nonfinite values")
    try:
        decoded = num2date(
            values, variable.units, calendar=getattr(variable, "calendar", "standard")
        )
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"NetCDF time coordinate cannot be decoded: {exc}") from exc
    # Preserve CF microseconds. Truncating to whole seconds would incorrectly
    # accept a shifted fixture time and merge distinct external track times.
    return [value.isoformat() for value in decoded]


def _track_schema(path, *, model_times=None):
    import numpy as np
    from netCDF4 import Dataset

    with Dataset(path) as dataset:
        lat = "latitude" if "latitude" in dataset.variables else "lat"
        lon = "longitude" if "longitude" in dataset.variables else "lon"
        if (
            "time" not in dataset.variables
            or lat not in dataset.variables
            or lon not in dataset.variables
        ):
            raise ValueError(
                f"{path}: prescribed track needs time and latitude/longitude or lat/lon"
            )
        times = _times(dataset.variables["time"])
        if not times or len(times) != len(set(times)):
            raise ValueError(f"{path}: prescribed track times must be nonempty and unique")
        overlap = times if model_times is None else [time for time in times if time in model_times]
        if not overlap:
            raise ValueError(
                f"{path}: prescribed track has no exact overlap with the CI model times"
            )
        selected = np.array([time in overlap for time in times])
        for name in (lat, lon):
            variable = dataset.variables[name]
            if variable.dimensions != ("time",) or variable.shape != (len(times),):
                raise ValueError(f"{path}: {name} must have one value per track time")
            positions = np.ma.filled(np.ma.asarray(variable[:], dtype=np.float64), np.nan)
            common_positions = positions[selected]
            if not np.isfinite(common_positions).all():
                raise ValueError(
                    f"{path}: prescribed track contains missing/nonfinite {name} at common times"
                )
            minimum, maximum = (-90, 90) if name == lat else (-180, 360)
            if ((common_positions < minimum) | (common_positions > maximum)).any():
                raise ValueError(
                    f"{path}: prescribed track {name} is outside geographic bounds at common times"
                )
        return {
            "latitude": lat,
            "longitude": lon,
            "time": "time",
            "times": times,
            "overlap_times": overlap,
            "dimensions": {name: len(dim) for name, dim in dataset.dimensions.items()},
        }


def _netcdf_inventory(path, spec, *, cropped=True):
    from netCDF4 import Dataset

    with Dataset(path) as dataset:
        expected = dict(spec["expected_dimensions"])
        if cropped:
            expected["nj"], expected["ni"] = spec["output_shape"]
        for name, size in expected.items():
            if name not in dataset.dimensions or len(dataset.dimensions[name]) != size:
                raise ValueError(f"{path}: incorrect {name} dimension; expected {size}")
        for name in ("ni_u", "ni_v", "nj_u", "nj_v"):
            reference = "ni" if name.startswith("ni") else "nj"
            if name in dataset.dimensions and len(dataset.dimensions[name]) != expected[reference]:
                raise ValueError(f"{path}: incompatible staggered dimension {name}")
        missing = set(spec["variables"]).difference(dataset.variables)
        if missing:
            raise ValueError(f"{path}: missing variables {sorted(missing)}")
        if "time" not in dataset.variables:
            raise ValueError(f"{path}: missing time coordinate")
        levels = {}
        for name in ("level", "level_w"):
            if name in dataset.variables:
                levels[name] = dataset.variables[name][:].tolist()
        return {
            "variables": sorted(dataset.variables),
            "times": _times(dataset.variables["time"]),
            "levels": levels,
            "dimensions": {name: len(dim) for name, dim in dataset.dimensions.items()},
        }


def _grib_inventory(path, spec):
    import eccodes as ec

    count = validate_grib_subset(path, tuple(spec["output_shape"]))
    times = set()
    with Path(path).open("rb") as stream:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                date = f"{ec.codes_get_long(handle, 'validityDate'):08d}"
                time = ec.codes_get_long(handle, "validityTime")
                times.add(
                    f"{date[:4]}-{date[4:6]}-{date[6:]}T{time // 100:02d}:{time % 100:02d}:00"
                )
            finally:
                ec.codes_release(handle)
    return {"message_count": count, "times": sorted(times)}


def _record(path, relative, dataset_id, **metadata):
    before = path.stat()
    digest = sha256_file(path)
    after = path.stat()
    if _stat_identity(before) != _stat_identity(after):
        raise ValueError(f"Fixture input changed during content verification: {path}")
    return {
        "path": relative,
        "dataset_id": dataset_id,
        "bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "sha256": digest,
        **metadata,
    }


def _stat_identity(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _safe_manifest_path(root, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe fixture manifest path: {relative}")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Fixture manifest path escapes its root: {relative}")
    return resolved


def verify_ci_dataset(root: Path, *, dataset_ids=None) -> dict:
    """Verify selected recipe families without modifying an existing manifest.

    Legacy manifests cover only simulation files. The external NetCDF, when
    present, receives a separate fingerprint; its absence remains an optional
    prescribed-case prerequisite rather than invalidating a legacy fixture.
    """
    root = Path(root).resolve()
    recipe = load_ci_recipe()
    selected = set(recipe["datasets"] if dataset_ids is None else dataset_ids)
    unknown = selected.difference(recipe["datasets"])
    if unknown:
        raise ValueError(f"Datasets are not in the CI recipe: {sorted(unknown)}")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"CI fixture manifest is absent: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read CI fixture manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("CI fixture manifest must be a JSON object")
    if not isinstance(manifest.get("format"), str):
        raise ValueError("CI fixture manifest format must be a string")
    version = {"frameit-ci-dataset-v1": 1, MANIFEST_FORMAT: 2}.get(manifest.get("format"))
    if version is None:
        raise ValueError("Unsupported CI fixture manifest format")
    if version == 2 or "schema_version" in manifest:
        if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != version:
            raise ValueError("Unsupported or inconsistent CI fixture manifest schema_version")
    if not isinstance(manifest.get("files"), list):
        raise ValueError("CI fixture manifest files must be a list")
    if version == 2 and not isinstance(manifest.get("datasets"), dict):
        raise ValueError("Native CI fixture manifest datasets must be an object")
    if version == 2 and (
        manifest.get("recipe_id") != recipe["recipe_id"]
        or manifest.get("recipe_version") != recipe["recipe_version"]
    ):
        raise ValueError("CI fixture recipe identity does not match the installed recipe")
    records = {}
    for record in manifest.get("files", []):
        if not isinstance(record, dict):
            raise ValueError("CI fixture file records must be objects")
        relative = record.get("path")
        if not isinstance(relative, str) or relative in records:
            raise ValueError("Invalid or duplicate fixture file record")
        _safe_manifest_path(root, relative)
        if type(record.get("bytes")) is not int or record["bytes"] < 0:
            raise ValueError(
                f"CI fixture file record bytes must be a nonnegative integer: {relative}"
            )
        digest = record.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"CI fixture file record needs a SHA-256 hex digest: {relative}")
        records[relative] = record
    checked = []
    for dataset_id in sorted(selected):
        spec = recipe["datasets"][dataset_id]
        metadata = (
            manifest.get("datasets", {}).get(dataset_id)
            if version == 2
            else manifest.get("arome" if spec["format"] == "grib" else "mnh")
        )
        if not isinstance(metadata, dict):
            raise ValueError(f"Manifest lacks CI recipe metadata for {dataset_id}")
        if (
            metadata.get("crop_xy_python") != spec["crop_xy_python"]
            or metadata.get("crop_grid", metadata.get("output_shape")) != spec["output_shape"]
            or metadata.get("full_grid", metadata.get("source_shape")) != spec["source_shape"]
            or metadata.get("files") != spec["files"]
        ):
            raise ValueError(
                f"Manifest geometry or selected files do not match the CI recipe for {dataset_id}"
            )
        expected_paths = {f"{dataset_id}/{name}" for name in spec["files"]}
        family_paths = {name for name in records if name.startswith(dataset_id + "/")}
        if family_paths != expected_paths:
            raise ValueError(f"Manifest input set does not match the CI recipe for {dataset_id}")
        for name, expected_time in zip(spec["files"], spec["times"], strict=True):
            relative = f"{dataset_id}/{name}"
            path = _safe_manifest_path(root, relative)
            record = records[relative]
            if not path.is_file():
                raise ValueError(f"Missing CI fixture file: {path}")
            verified_record = _record(path, relative, dataset_id)
            if verified_record["bytes"] != record.get("bytes") or verified_record[
                "sha256"
            ] != record.get("sha256"):
                raise ValueError(f"CI fixture hash/size mismatch: {relative}")
            inventory = (
                _grib_inventory(path, spec)
                if spec["format"] == "grib"
                else _netcdf_inventory(path, spec)
            )
            if inventory["times"] != [expected_time]:
                raise ValueError(f"{relative}: decoded time does not match the fixed CI recipe")
            after_inventory = path.stat()
            if (after_inventory.st_size, after_inventory.st_mtime_ns) != (
                verified_record["bytes"],
                verified_record["mtime_ns"],
            ):
                raise ValueError(f"Fixture input changed during header verification: {relative}")
            checked.append({**record, **verified_record})
    track = None
    if "MNH/CHIDO" in selected:
        relative = recipe["external_track"]
        path = _safe_manifest_path(root, relative)
        if version == 2 and relative not in records:
            raise ValueError("Native CI manifest does not fingerprint its external track")
        if path.exists():
            # A legacy manifest does not claim anything about this supplemental
            # file. Its schema is an optional prescribed-case prerequisite,
            # resolved by the catalog only when that case is selected.
            schema = (
                _track_schema(path, model_times=recipe["datasets"]["MNH/CHIDO"]["times"])
                if version == 2
                else None
            )
            track = _record(path, relative, "MNH/CHIDO", schema=schema)
            if version == 2:
                stored = records[relative]
                if stored.get("bytes") != track["bytes"] or stored.get("sha256") != track["sha256"]:
                    raise ValueError("CI external track hash/size mismatch")
            checked.append(track)
        elif version == 2:
            raise ValueError("Native CI fixture external track is absent")
    identity_records = [
        {key: record[key] for key in ("path", "bytes", "sha256")} for record in checked
    ]
    return {
        "ok": True,
        "identity": _canonical_hash(
            {
                "recipe_id": recipe["recipe_id"],
                "files": sorted(identity_records, key=lambda record: record["path"]),
            }
        ),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "schema_version": version,
        "recipe_id": recipe["recipe_id"],
        "files": checked,
        "external_track": track,
    }


def _publish(staging, output, force):
    backup = None
    if output.exists():
        if not force:
            raise ValueError(f"Output already exists: {output}; use --force to replace it")
        backup = output.with_name(f".{output.name}.backup-{uuid.uuid4().hex}")
        output.rename(backup)
    try:
        staging.rename(output)
    except BaseException:
        if backup is not None:
            backup.rename(output)
        raise
    if backup is not None:
        try:
            shutil.rmtree(backup)
        except OSError as exc:
            # The replacement has committed. A cleanup failure must not report
            # the completed installation as a failed transaction.
            return [f"Installation completed; backup retained at {backup}: {exc}"]
    return []


def prepare_ci_dataset(
    source: Path, output: Path, *, max_size_mb=100, force=False, plan_only=False, track_file=None
) -> dict:
    """Prepare and verify the frozen recipe in a staging tree before publishing."""
    source, requested_output = Path(source).resolve(), Path(output)
    if requested_output.is_symlink():
        raise ValueError("The CI output must not be a symbolic link")
    output = requested_output.resolve()
    if source == output or source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError("Source and output must be separate trees; neither may contain the other")
    if not math.isfinite(max_size_mb) or max_size_mb <= 0:
        raise ValueError("--max-size-mb must be finite and positive")
    if output.exists() and not output.is_dir():
        raise ValueError(f"Output is not a directory: {output}")
    if output.exists() and not force and not plan_only:
        raise ValueError(f"Output already exists: {output}; use --force to replace it")
    recipe = load_ci_recipe()
    external = Path(track_file).resolve() if track_file else source / recipe["external_track"]
    if external.is_relative_to(output):
        raise ValueError("The prescribed source track must not be inside the output tree")
    sources = []
    for dataset_id, spec in recipe["datasets"].items():
        for name in spec["files"]:
            path = source / dataset_id / name
            if not path.is_file():
                raise ValueError(f"Required CI source file is absent: {path}")
            if path.resolve().is_relative_to(output):
                raise ValueError(f"Source symlink target is inside the output tree: {path}")
            sources.append(
                {
                    "source": str(path),
                    "output": f"{dataset_id}/{name}",
                    "dataset_id": dataset_id,
                    "crop_xy_python": spec["crop_xy_python"],
                }
            )
    if not external.is_file():
        raise ValueError(f"Required external CHIDO NetCDF track is absent: {external}")
    schema = _track_schema(external, model_times=recipe["datasets"]["MNH/CHIDO"]["times"])
    plan = {
        "recipe_id": recipe["recipe_id"],
        "recipe_version": recipe["recipe_version"],
        "source": str(source),
        "output": str(output),
        "files": sources,
        "external_track": {
            "source": str(external),
            "output": recipe["external_track"],
            "schema": schema,
        },
        "max_size_mb": max_size_mb,
        "checks": [
            "source geometry and times",
            "serialized GRIB point counts",
            "raw NetCDF data and metadata",
            "file SHA-256",
            "actual installed size",
        ],
        "compressed_size_known": False,
    }
    if plan_only:
        return {**plan, "status": "PLANNED"}
    identities = {
        Path(item["source"]): (
            Path(item["source"]).stat().st_size,
            Path(item["source"]).stat().st_mtime_ns,
        )
        for item in sources
    }
    identities[external] = (external.stat().st_size, external.stat().st_mtime_ns)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        manifest = {
            "format": MANIFEST_FORMAT,
            "schema_version": 2,
            "recipe_id": recipe["recipe_id"],
            "recipe_version": recipe["recipe_version"],
            "datasets": {},
            "files": [],
            "source_root": str(source),
        }
        for dataset_id, spec in recipe["datasets"].items():
            manifest["datasets"][dataset_id] = {
                "source_shape": spec["source_shape"],
                "output_shape": spec["output_shape"],
                "crop_xy_python": spec["crop_xy_python"],
                "files": spec["files"],
                "selected_variables": "all_messages"
                if spec["format"] == "grib"
                else spec["variables"],
                "selected_levels": "all",
                "times": spec["times"],
            }
            (staging / dataset_id).mkdir(parents=True)
            for name, expected_time in zip(spec["files"], spec["times"], strict=True):
                original = source / dataset_id / name
                relative = f"{dataset_id}/{name}"
                target = staging / relative
                if spec["format"] == "grib":
                    info = crop_grib(
                        original,
                        target,
                        spec["crop_xy_python"],
                        expected_shape=spec["source_shape"],
                        reference_center=(
                            *spec["fixed_center_lat_lon"],
                            *spec["fixed_center_source_xy"],
                        ),
                    )
                else:
                    crop_netcdf(
                        original,
                        target,
                        spec["crop_xy_python"],
                        expected_dimensions=spec["expected_dimensions"],
                        required_variables=spec["variables"],
                        optional_variables=spec.get("optional_variables", ()),
                    )
                    info = _netcdf_inventory(target, spec)
                if info["times"] != [expected_time]:
                    raise ValueError(f"{original}: decoded time does not match the fixed CI recipe")
                manifest["files"].append(
                    _record(
                        target,
                        relative,
                        dataset_id,
                        source_name=original.name,
                        source_path=str(original),
                        **info,
                    )
                )
        track_target = staging / recipe["external_track"]
        shutil.copyfile(external, track_target)
        track_record = _record(
            track_target,
            recipe["external_track"],
            "MNH/CHIDO",
            schema=schema,
            source_name=external.name,
            source_path=str(external),
        )
        if track_record["sha256"] != sha256_file(external):
            raise ValueError("External track copy differs from its source")
        manifest["files"].append(track_record)
        manifest["external_track"] = track_record
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        verified = verify_ci_dataset(staging)
        total = sum(path.stat().st_size for path in staging.rglob("*") if path.is_file())
        if total > max_size_mb * 1_000_000:
            raise ValueError(
                f"CI fixture size {total / 1_000_000:.3f} MB is above the requested "
                f"{max_size_mb:g} MB ceiling"
            )
        for path, original in identities.items():
            if (path.stat().st_size, path.stat().st_mtime_ns) != original:
                raise ValueError(f"Source changed while preparing the CI fixture: {path}")
        warnings = _publish(staging, output, force)
        return {
            "status": "PREPARED",
            "output": str(output),
            "bytes": total,
            "identity": verified["identity"],
            "manifest_path": str(output / "manifest.json"),
            "recipe_id": recipe["recipe_id"],
            "files": len(manifest["files"]),
            "warnings": warnings,
        }
    finally:
        if staging.exists():
            shutil.rmtree(staging)
