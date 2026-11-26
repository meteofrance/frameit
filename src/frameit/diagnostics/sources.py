"""Read-only binding and bounded tiled views of one recorded source."""

from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from math import isfinite, isqrt, prod
from pathlib import Path
from re import findall, sub

import numpy as np
import xarray as xr

from frameit.core.run_context import content_digest, product_identity
from frameit.diagnostics.catalog import AGENCY_PROFILE_VERSION
from frameit.diagnostics.contracts import DiagnosticPlan, diagnostic_error
from frameit.diagnostics.geometry import PERIMETER_BYTES
from frameit.io.loader import DatasetResources
from frameit.utils.output_paths import OutputPaths
from frameit.utils.units import UNITS, unit_key

UTC_CALENDARS = {"standard", "gregorian", "proleptic_gregorian"}
_ORIGINAL_NETCDF_SPHERES = {"mesonh": (6371229.0, "Meso-NH default (INI_CST.XRADIUS)")}
_EARTH_MODEL_KEYS = {
    "earth_radius", "fa_earth_radius_m", "semi_major_axis", "semi_minor_axis",
    "inverse_flattening", "crs_wkt", "spatial_ref", "reference_ellipsoid_name",
    "horizontal_datum_name", "geographic_crs_name",
}
AREA_UNITS = {"m2": 1, "m^2": 1, "m**2": 1, "km2": 10**6, "km^2": 10**6, "km**2": 10**6}
WIND_NAMES = {
    "speed": {"wind_speed"},
    "u": {"eastward_wind", "grid_eastward_wind", "x_wind"},
    "v": {"northward_wind", "grid_northward_wind", "y_wind"},
    "gust": {"wind_speed_of_gust"},
    "pressure": {"air_pressure_at_mean_sea_level", "air_pressure_at_sea_level"},
    "area": {"cell_area"},
}
CELLS_BYTES = 320  # fields, coordinates, float64 temporaries, masks, neighbour halo


@dataclass(frozen=True)
class File:
    path: Path
    engine: str | None
    representation: str
    identity: dict
    attempt: str | None = None
    decode_units: dict | None = None
    packed_validity: tuple[str, ...] = ()


@dataclass(frozen=True)
class Grid:
    dims: tuple[str, str]
    shape: tuple[int, int]
    latitude: str
    longitude: str
    clock_indices: tuple[tuple[str, int], ...]
    latitude_factor: float
    longitude_factor: float
    earth: tuple[float, float]
    earth_origin: str


@dataclass(frozen=True)
class FieldSample:
    role: str
    name: str
    file: File
    grid: Grid
    indexers: tuple[tuple[str, int], ...]
    time: str
    cycle: str | None
    calendar: str
    reference_calendar: str | None
    time_bounds: tuple[str, str] | None
    centre_time: str | None
    height_m: float | None
    statistic: str
    averaging_seconds: float | None
    qualified: bool
    frame: str | None
    units: str
    factor: float
    decode_bytes: int
    dtype: str
    metadata_evidence: dict
    scalar_coordinates: tuple
    native: dict | None = None
    validity_limits: tuple[float | None, float | None] = (None, None)


@dataclass(frozen=True)
class Group:
    role: str
    fields: tuple[FieldSample, ...]
    tile_side: int
    truncated: str

    @property
    def grid(self):
        return self.fields[0].grid

    @property
    def qualified(self):
        return all(field.qualified for field in self.fields if field.role != "area")


@dataclass(frozen=True)
class Block:
    latitude: np.ndarray
    longitude: np.ndarray
    values: dict[str, np.ndarray]


def _error(message, *, role=None, observed=None):
    path = "diagnostics.best_track"
    return diagnostic_error(
        "E2003",
        path if role is None else f"{path}.fields.{role}",
        message,
        observed=observed,
        expected="bounded input with compatible recorded physical metadata",
        repair="Check the selected field, its metadata and the diagnostic working-buffer budget.",
    )


def _timestamp(value):
    if value is None:
        return None
    if isinstance(value, np.datetime64):
        result = value.astype("datetime64[ns]")
        if np.isnat(result) or result.astype(value.dtype) != value:
            raise _error(f"Unrepresentable or missing exact sample time: {value}")
        return str(result)
    try:
        # Frozen metadata contains ISO strings, never guessed calendar conversions.
        return _timestamp(np.datetime64(value))
    except (TypeError, ValueError) as exc:
        raise _error(f"Invalid exact sample timestamp: {value}") from exc


def _verify_file(file):
    try:
        if file.representation.startswith("original"):
            info = file.path.stat()
            observed = {"size_bytes": info.st_size, "mtime_ns": info.st_mtime_ns}
            if file.identity.get("strategy") == "device_inode":
                observed.update(device=info.st_dev, inode=info.st_ino)
            if any(file.identity.get(key) != value for key, value in observed.items()):
                raise _error(
                    f"Original input identity changed: {file.path.name}", observed=observed
                )
        else:
            current = product_identity(
                file.path, representation=file.representation, engine=file.engine
            )
            if file.identity != current:
                raise _error(
                    f"Published product identity changed: {file.path.name}", observed=current
                )
    except OSError as exc:
        raise _error(f"Cannot verify recorded input identity: {file.path.name}: {exc}") from exc


@contextmanager
def _open(file, *, zarr_objects=None, object_limit=0, decode_coords="all"):
    with ExitStack() as scope, DatasetResources() as resources:
        options = {"chunks": None, "create_default_indexes": False, "decode_coords": decode_coords}
        if file.representation == "zarr3":
            from frameit.diagnostics.zarr_source import open_store

            store = scope.enter_context(
                open_store(file.path, evidence=zarr_objects, max_objects=object_limit)
            )
            ds = resources.add(xr.open_zarr(store, zarr_format=3, consolidated=False, **options))
        else:
            ds = resources.add(
                xr.open_dataset(file.path, engine=file.engine, cache=False, **options)
            )
        if file.attempt is not None and ds.attrs.get("run_attempt_id") != file.attempt:
            raise _error(f"Product attempt identity does not match: {file.path.name}")
        yield ds


def _source_files(parent, request):
    kind, name = request["input"]["kind"], request["input"]["source"]
    evidence = parent.sources[name]
    inventory = evidence.get("frozen_inventory", {})
    cfg = parent.effective["sources"][name]
    if inventory.get("physical_type") != "atmosphere" and (
        inventory or evidence.get("model") not in {"arome", "mesonh"}
    ):
        raise _error(f"Source {name!r} is not an admitted atmospheric source")
    if kind == "original":
        if inventory.get("version") != 1 or inventory.get("format") not in {"netcdf", "grib"}:
            raise _error(f"Original {inventory.get('format')!r} is not an admitted bounded backend")
        representation = "original_grib" if inventory["format"] == "grib" else "original"
        files = tuple(
            File(
                Path(entry["path"]),
                cfg.get("reader", {}).get("engine"),
                representation,
                entry["identity"],
            )
            for entry in inventory["files"]
        )
        if not files:
            raise _error("The parent did not select any original files for this source")
        return files, inventory, cfg, evidence
    matches = [
        item
        for item in parent.products
        if item.get("role", item.get("product")) == "model_grid" and item.get("source") == name
    ]
    if len(matches) != 1:
        raise _error(
            f"Expected one actual model_grid publication for {name!r}; found {len(matches)}"
        )
    (item,) = matches
    (path,) = OutputPaths(parent.root).planned_products(matches)
    encoding = item.get("encoding", {})
    representation = encoding.get("format")
    if representation not in {"netcdf4", "zarr3"}:
        raise _error(f"Published {representation!r} is not an admitted bounded backend")
    if parent.identity_scheme.startswith("legacy_"):
        try:
            identity = product_identity(
                path, representation=representation, engine=encoding.get("engine")
            )
        except (OSError, ValueError) as exc:
            raise _error(f"Cannot read recorded legacy model_grid: {path.name}") from exc
        attempt = None
    else:
        identity, attempt = item.get("identity"), parent.attempt_id
        if not isinstance(identity, dict) or identity.get("version") != 1:
            raise _error("Recorded model_grid lacks a recognized product identity")
    units = None
    if representation == "zarr3":
        from frameit.diagnostics.zarr_source import check_layout
        from frameit.io.zarr_export import check_zarr_dependencies

        check_zarr_dependencies()
        units = check_layout(path)
    packed_validity = tuple(item.get("packed_validity_unresolved", ()))
    file = File(
        path, encoding.get("engine"), representation, identity, attempt, units, packed_validity
    )
    return (file,), {}, cfg, evidence


def _clock_samples(ds, file, *, inventory, file_index, model):
    from frameit.core.preflight import _decoded_clock

    centres = ds.get("center_time")
    clock_view = ds.drop_vars("center_time", errors="ignore")
    for variable in clock_view.variables.values():
        if variable.dtype.kind in "MO" and "bounds" in variable.encoding:
            variable.attrs = dict(variable.attrs, bounds=variable.encoding["bounds"])
    samples, _ = _decoded_clock(clock_view, file.path, model=model)
    frozen = set()
    if inventory:
        frozen = {
            (
                _timestamp(sample["time"]),
                _timestamp(sample["cycle"]),
                tuple(sorted(sample["indexers"].items())),
                sample["calendar"],
                sample.get("reference_calendar"),
            )
            for sample in inventory["samples"]
            if sample["file_index"] == file_index
        }
    for sample in samples:
        if sample["calendar"] not in UTC_CALENDARS or (
            sample.get("reference_calendar") not in UTC_CALENDARS | {None}
        ):
            raise _error(f"Unsupported native/reference calendar in {file.path.name}")
        sample["time"], sample["cycle"] = _timestamp(sample["time"]), _timestamp(sample["cycle"])
        sample["indices"] = tuple(sorted(sample.pop("indexers").items()))
        if (
            inventory
            and (
                sample["time"],
                sample["cycle"],
                sample["indices"],
                sample["calendar"],
                sample.get("reference_calendar"),
            )
            not in frozen
        ):
            continue
        if bounds := sample["time_bounds"]:
            sample["time_bounds"] = tuple(map(_timestamp, bounds))
        if centres is not None and set(centres.dims) <= dict(sample["indices"]).keys():
            sample["centre_time"] = _timestamp(
                centres.isel({dim: dict(sample["indices"])[dim] for dim in centres.dims}).values[()]
            )
        yield sample


def _units_factor(unit, quantity, *, target=None):
    canonical, factors = UNITS[quantity] if quantity != "area" else ("m2", AREA_UNITS)
    if (key := unit_key(unit)) not in factors:
        raise _error(f"Unrecognized {quantity} units {unit!r}; no implicit conversion")
    return factors[key] / factors[unit_key(target or canonical)]


def _earth_model(ds, field, *, original_model=None):
    from pyproj import CRS
    from pyproj.exceptions import CRSError

    default = _ORIGINAL_NETCDF_SPHERES.get(original_model)
    mapping = field.encoding.get("grid_mapping", field.attrs.get("grid_mapping"))
    grid = ds[mapping].attrs if mapping in ds.variables else {}
    if default is not None and mapping is not None and not grid:
        raise _error(f"{field.name!r} has an unresolved Earth model grid_mapping", observed=mapping)

    candidates = []
    if wkt := grid.get("crs_wkt") or grid.get("spatial_ref"):
        model = CRS.from_wkt(wkt).ellipsoid
        declared = (float(model.semi_major_metre), float(model.semi_minor_metre)), str(mapping)
        if default is None:
            return declared
        candidates.append(declared)

    for attrs, origin in ((grid, f"grid_mapping:{mapping}"), (ds.attrs, "dataset Earth model")):
        if "earth_radius" in attrs:
            a = b = float(attrs["earth_radius"])
        elif "fa_earth_radius_m" in attrs:
            a = b = float(attrs["fa_earth_radius_m"])
            origin = attrs.get("fa_earth_model_origin", origin)
        elif "semi_major_axis" in attrs and (
            "semi_minor_axis" in attrs or "inverse_flattening" in attrs
        ):
            a = float(attrs["semi_major_axis"])
            inv = float(attrs.get("inverse_flattening", 0))
            b = float(attrs.get("semi_minor_axis", a if inv == 0 else a * (1 - 1 / inv)))
        else:
            continue
        if not (isfinite(a) and isfinite(b) and a > 0 and b > 0):
            raise _error(f"Invalid Earth model on {field.name!r}", observed=(a, b))
        candidates.append(((a, b), origin))
    if (
        not candidates
        and default is not None
        and _EARTH_MODEL_KEYS.isdisjoint(grid.keys() | ds.attrs.keys())
    ):
        radius, origin = default
        if mapping is not None:
            try:
                CRS.from_cf({**grid, "earth_radius": radius})
            except (CRSError, KeyError, TypeError, ValueError) as exc:
                raise _error(
                    f"{field.name!r} has an invalid Earth model grid_mapping: {exc}",
                    observed=mapping,
                ) from exc
        return (radius, radius), origin
    if not candidates or len({model for model, _ in candidates}) != 1:
        raise _error(f"{field.name!r} requires one declared Earth model for geodesic distances")
    return candidates[0]


def _coord_names(ds, field, indexers):
    linked = set(str(field.attrs.get("coordinates", field.encoding.get("coordinates", ""))).split())
    names = set(field.coords) | linked
    candidates = {"latitude": [], "longitude": []}
    for name in sorted(names & ds.variables.keys()):
        coord = ds[name]
        raw = str(coord.attrs.get("standard_name", ""))
        role = raw.split("_at_", 1)[0]
        dims = set(coord.dims) - indexers.keys()
        if role in candidates and dims and dims <= set(field.dims) and len(dims) <= 2:
            candidates[role].append(name)
    for role, values in candidates.items():
        candidates[role] = [name for name in values if name in linked] or values
    if any(len(values) != 1 for values in candidates.values()):
        raise _error(
            f"{field.name!r} does not have unique field-specific geographic coordinates",
            observed=candidates,
        )
    return candidates["latitude"][0], candidates["longitude"][0]


def _vertical_selection(ds, field, selector, spatial, clock_indices):
    from frameit.processing.requests import _match_levels

    indices = {dim: i for dim, i in clock_indices.items() if dim in field.dims}
    remaining = set(field.dims) - indices.keys() - set(spatial)
    level = selector.get("level")
    selected = None
    axes = [
        dim
        for dim in sorted(remaining)
        if dim in ds.coords
        and (
            ds[dim].attrs.get("axis") == "Z"
            or ds[dim].attrs.get("positive") in {"up", "down"}
            or ds[dim].attrs.get("standard_name")
            in {"height", "air_pressure", "altitude", "geopotential_height"}
        )
    ]
    if level is not None:
        if len(axes) != 1:
            raise _error(
                f"{field.name!r}: exact level selector requires one physical vertical axis"
            )
        (axis,) = axes
        coordinate = ds[axis]
        if coordinate.ndim != 1 or coordinate.dims != (axis,):
            raise _error(f"{field.name!r}: unsupported compound vertical selection")
        target = coordinate.attrs.get("units")
        quantity = next(
            (kind for kind in ("distance", "pressure") if unit_key(target) in UNITS[kind][1]), None
        )
        if quantity is None:
            raise _error(f"{field.name!r}: level units are not physical distance or pressure units")
        value = float(level["value"]) * _units_factor(level["units"], quantity, target=target)
        labels = coordinate.values
        matched = _match_levels(labels, [value], tol=None)
        positions = np.flatnonzero(labels == matched[0]) if matched else []
        if len(positions) != 1:
            raise _error(f"{field.name!r}: field lacks the unique exact physical level {level!r}")
        indices[axis] = int(positions[0])
        selected = axis
        remaining.remove(axis)
    if selector.get("group") not in {None, selected, *(axes if len(axes) == 1 else ())}:
        raise _error(f"{field.name!r}: selector group does not identify the native vertical axis")
    for dim in sorted(remaining):
        if ds.sizes[dim] != 1 or dim not in ds.coords or ds[dim].dims != (dim,):
            raise _error(
                f"{field.name!r}: unresolved native axis {dim!r}; select one physical sample"
            )
        indices[dim] = 0
    return indices


def _height_and_scalar_coords(ds, field, indices, attrs):
    heights = []
    if "height_above_ground_m" in attrs:
        heights.append(float(attrs["height_above_ground_m"]))
    scalar = []
    for coord in field.coords.values():
        standard = coord.attrs.get("standard_name")
        if standard not in {
            "height",
            "altitude",
            "air_pressure",
            "forecast_period",
            "realization",
            "geopotential_height",
        }:
            continue
        if set(coord.dims) <= indices.keys():
            value = coord.isel({dim: indices[dim] for dim in coord.dims}).values[()]
            units = coord.attrs.get("units", coord.encoding.get("units"))
            if standard == "height":
                heights.append(float(value) * _units_factor(units, "distance"))
            scalar.append((standard, str(value), str(units)))
    if heights and (not all(isfinite(h) for h in heights) or len(set(heights)) != 1):
        raise _error(f"Contradictory height evidence on {field.name!r}", observed=heights)
    return heights[0] if heights else None, tuple(sorted(scalar))


def _semantics(role, field, attrs, height, sample, wind_pairs):
    standard = attrs.get("standard_name")
    unresolved = "physical_definition_unverified", None, False, None
    if standard and standard not in WIND_NAMES[role]:
        raise _error(
            f"{field.name!r} does not establish the physical quantity {role}",
            role=role,
            observed=standard,
        )
    if attrs.get("kind") == "categorical":
        raise _error(f"{field.name!r} is categorical, not physical continuous data", role=role)
    if role not in {"pressure", "area"} and height is not None and height != 10:
        raise _error(
            f"{field.name!r} has a height other than 10 m above ground", role=role, observed=height
        )
    if not standard or not attrs.get("units"):
        return unresolved
    if role in {"pressure", "area"}:
        return "native", None, True, None
    reference = attrs.get("physical_reference_frame", attrs.get("reference_frame"))
    basis = attrs.get("wind_reference_frame")
    if reference not in {None, "earth", "ground"} or basis not in {None, "earth", "grid"}:
        raise _error(
            f"{field.name!r}: unsupported physical wind frame",
            role=role,
            observed=(reference, basis),
        )
    declared = {pair["basis"] for pair in wind_pairs if pair.get(role) == field.name}
    implied = (
        "earth"
        if standard in {"eastward_wind", "northward_wind"}
        else "grid"
        if role in {"u", "v"}
        else None
    )
    frames = declared | {value for value in (basis, implied) if value is not None}
    if len(frames) > 1:
        raise _error(
            f"{field.name!r}: contradictory wind basis", role=role, observed=sorted(frames)
        )
    if height is None or not frames and reference not in {"earth", "ground"}:
        return unresolved
    frame = next(iter(frames), "earth")
    if frame == "grid" and role in {"speed", "gust"}:
        raise _error(f"{field.name!r}: scalar magnitude requires an Earth-relative definition")
    method_text = sub(r"\([^)]*\)", "", str(attrs.get("cell_methods", "")))
    methods = [
        method
        for axis, method in findall(r"(\w+)\s*:\s*(\w+)", method_text)
        if axis in {*sample["temporal_names"], "time"}
    ]
    if len(methods) > 1 or methods and findall(r"\b(?:within|over)\s+\w+", method_text):
        return "unverified", None, False, frame
    duration = None
    if bounds := sample["time_bounds"]:
        a, b = map(np.datetime64, bounds)
        if b <= a or not a <= np.datetime64(sample["time"]) <= b:
            raise _error(f"{field.name!r}: invalid or mismatched temporal support interval")
        duration = float((b - a) / np.timedelta64(1, "s"))
    # CF cell_methods interval describes sample spacing, not the length of a mean.
    temporal = attrs.get("temporal_kind")
    if (temporal, methods) in (("instantaneous", ["mean"]), ("mean", ["point"])):
        raise _error(f"{field.name!r}: contradictory temporal operator metadata")
    if role == "gust":
        return (
            "producer_gust",
            duration,
            "maximum" in methods
            and duration is not None
            and attrs.get("gust_duration_seconds") == 3
            and attrs.get("gust_reference_profile") == AGENCY_PROFILE_VERSION,
            frame,
        )
    derivation = attrs.get("derivation")
    component_magnitude = role in {"u", "v"} or derivation in (
        "magnitude_of_mean_components",
        "magnitude_of_collocated_components",
        "magnitude_of_sampled_components",
        "magnitude_of_interpolated_collocated_components",
    )
    if (
        role == "speed"
        and not component_magnitude
        and derivation
        not in (
            None,
            "mean_scalar_speed",
        )
    ):
        return "unverified", None, False, frame
    if "mean" in methods or temporal == "mean" and not methods:
        statistic = "magnitude_of_mean_components" if component_magnitude else "mean_scalar_speed"
        qualified = (
            "mean" in methods
            and duration == 600
            and (
                not component_magnitude
                or attrs.get("sustained_wind_convention")
                == "magnitude_of_mean_components_compatible_10min"
            )
        )
        return statistic, duration, qualified, frame
    if "point" in methods or temporal == "instantaneous":
        return "instantaneous", 0.0, False, frame
    return "unverified", None, False, frame


def _metadata(ds, field, sample, *, inventory, source_cfg, evidence, file_index, scope, cache):
    native = field.attrs
    if not inventory:
        return native, {"origin": "saved_effective_product"}
    name = field.name
    matches = [
        entry
        for entry in inventory.get("fields", [])
        if entry["file_index"] == file_index
        and entry["name"] == name
        and any(
            item["time"] == sample["time"] or _timestamp(item["time"]) == sample["time"]
            for item in entry["samples"]
        )
    ]
    if matches:
        keys = {content_digest(m["metadata"]) for m in matches}
        if len(keys) != 1:
            raise _error(f"Ambiguous frozen metadata for {name!r}")
        old = matches[0]["metadata"]
        return old["attributes"], {"origin": "parent", "origins": old["origins"]}

    from frameit.processing.requests import resolve_field_metadata

    declarations = source_cfg.get("field_metadata", {})
    native_groups = [
        dim
        for dim in field.dims
        if dim in ds.coords
        and (ds[dim].attrs.get("axis") == "Z" or ds[dim].attrs.get("positive") in {"up", "down"})
    ]
    qualified = [
        declarations[f"{dim}.{name}"] for dim in native_groups if f"{dim}.{name}" in declarations
    ]
    declared = declarations.get(name, {})
    choices = [value for value in [declared, *qualified] if value]
    if len({content_digest(item) for item in choices}) > 1:
        raise _error(f"Conflicting inherited source declarations for {name!r}")
    resolved = resolve_field_metadata(
        native, choices[0] if choices else {}, name, temporal_names=sample["temporal_names"]
    )
    attrs, origins = resolved["attributes"], resolved["origins"]
    keys = ("units", "long_name", "standard_name")
    missing = [key for key in keys if not attrs.get(key)]
    details = {"origin": "diagnostic_native", "origins": origins}
    if not missing:
        return attrs, details
    from frameit.core.catalogue_diagnostics import _netcdf_identity, propose

    identity = dict(_netcdf_identity(evidence["model"], ds.attrs), name=name)
    if identity.keys() >= {"producer", "version", "namespace"}:
        from frameit.core import metadata_catalogue

        key = content_digest(identity)
        if key not in cache:
            try:
                if "catalogue" not in cache:
                    cache["catalogue"] = scope.enter_context(metadata_catalogue.open_catalogue())
                cache[key] = cache["catalogue"].lookup(
                    identity["producer"], identity["version"], name, identity["namespace"]
                )
            except metadata_catalogue.CatalogueError:
                cache[key] = []
        result = propose(
            cache[key], identity, {key: attrs[key] for key in keys if key in attrs}, missing
        )
        if values := result["proposed_values"]:
            attrs.update(values)
            origins.update({key: "catalogue" for key in values})
            details.update(
                origin="diagnostic_catalogue",
                catalogue_version=metadata_catalogue.VERSION,
                content_sha256=metadata_catalogue.CONTENT_SHA256,
                native_identity=identity,
                applied_values=values,
                record_ids=result["supporting_record_ids"],
            )
    return attrs, details


def _decode_unit(da):
    shape = da.encoding.get("chunksizes")
    if shape is None:
        return 0  # contiguous storage can select a hyperslab
    stored = np.dtype(da.encoding.get("dtype", da.dtype))
    return prod(shape) * (stored.itemsize + da.dtype.itemsize)


def _validity_limits(field, file):
    attrs = field.attrs
    keys = attrs.keys() & {"valid_min", "valid_max", "valid_range"}
    if not keys:
        return None, None
    packing = {"scale_factor", "add_offset", "_Unsigned"}
    if field.name in file.packed_validity or packing & (attrs.keys() | field.encoding.keys()):
        raise _error(f"{field.name!r}: packed validity limits have no admitted interpretation")

    def bounds(key, shape):
        value = np.asarray(attrs[key])
        if value.shape != shape or value.dtype.kind not in "iuf" or not np.isfinite(value).all():
            raise _error(f"{field.name!r}: invalid numeric {key} metadata")
        return value

    if "valid_range" in keys:
        if len(keys) > 1:
            raise _error(f"{field.name!r}: use either valid_range or valid_min/valid_max")
        lower, upper = map(float, bounds("valid_range", (2,)))
    else:
        lower, upper = (
            float(bounds(key, ())) if key in keys else None for key in ("valid_min", "valid_max")
        )
    if lower is not None and upper is not None and lower > upper:
        raise _error(f"{field.name!r}: validity range minimum exceeds its maximum")
    return lower, upper


def _bind_field(ds, file, role, selector, sample, attrs, evidence, wind_pairs, *, original_model):
    field = ds[selector["field"]]
    if role in {"u", "v"}:
        from frameit.processing.derived.wind import require_collocated_location

        require_collocated_location(field)
    clock_indices = dict(sample["indices"])
    if not set(field.dims).intersection(clock_indices) and role != "area":
        raise _error(
            f"{field.name!r}: no field sample axis is linked to the recorded clock", role=role
        )
    lat, lon = _coord_names(ds, field, clock_indices)
    spatial = (set(ds[lat].dims) | set(ds[lon].dims)) - clock_indices.keys()
    dims = tuple(dim for dim in field.dims if dim in spatial)
    if len(dims) != 2 or any(ds.sizes[dim] < 2 for dim in dims):
        raise _error(f"{field.name!r}: requires a structured two-dimensional geographic grid")
    indices = _vertical_selection(ds, field, selector, dims, clock_indices)
    coordinates = [ds[lat], ds[lon]]
    if any(set(coord.dims) - set(dims) - clock_indices.keys() for coord in coordinates):
        raise _error(f"{field.name!r}: unsupported geographic coordinate axes")
    if any(key in attrs for key in ("flag_masks", "flag_values")):
        raise _error(f"{field.name!r}: a categorical field cannot supply physical values")
    height, scalar = _height_and_scalar_coords(ds, field, indices, attrs)
    statistic, seconds, qualified, frame = _semantics(
        role, field, attrs, height, sample, wind_pairs
    )
    units = attrs.get("units")
    quantity = role if role in {"pressure", "area"} else "velocity"
    factor = _units_factor(units, quantity) if units else 1.0
    earth, origin = _earth_model(ds, field, original_model=original_model)
    grid = Grid(
        dims,
        tuple(ds.sizes[d] for d in dims),
        lat,
        lon,
        tuple((d, i) for d, i in sample["indices"] if d in ds[lat].dims or d in ds[lon].dims),
        _units_factor(ds[lat].attrs.get("units"), "angle", target="degrees_north"),
        _units_factor(ds[lon].attrs.get("units"), "angle", target="degrees_east"),
        earth,
        origin,
    )
    return FieldSample(
        role,
        field.name,
        file,
        grid,
        tuple(sorted(indices.items())),
        sample["time"],
        sample["cycle"],
        sample["calendar"],
        sample.get("reference_calendar"),
        sample["time_bounds"],
        sample.get("centre_time"),
        height,
        statistic,
        seconds,
        qualified,
        frame,
        units,
        factor,
        sum(
            (file.decode_units or {}).get(da.name, _decode_unit(da)) for da in (field, *coordinates)
        ),
        str(field.dtype),
        evidence,
        scalar,
        validity_limits=_validity_limits(field, file),
    )


def _selectors(request):
    fields = request["fields"]
    roles = {**fields["wind"], "pressure": fields["sea_level_pressure"]}
    for name, role in (("gust", "gust"), ("cell_area", "area")):
        if name in fields:
            roles[role] = fields[name]
    return {
        role: ({"field": value} if isinstance(value, str) else value)
        for role, value in roles.items()
    }


def _groups(bindings, selectors, *, radius_bins, sectors, budget, original):
    roles = [
        ("wind", ("speed",) if "speed" in selectors else ("u", "v")),
        ("pressure", ("pressure",)),
        ("gust", ("gust",)),
    ]
    groups = []
    for role, members in roles:
        if any(name not in bindings for name in members):
            continue
        fields = tuple(bindings[name] for name in members)
        first = fields[0]
        common = (
            first.file.path,
            first.grid,
            first.cycle,
            first.calendar,
            first.reference_calendar,
        )
        if len(fields) > 1:
            other = fields[1]
            physical = all(f.statistic != "physical_definition_unverified" for f in fields)
            if (
                common
                != (
                    other.file.path,
                    other.grid,
                    other.cycle,
                    other.calendar,
                    other.reference_calendar,
                )
                or physical
                and (
                    first.statistic,
                    first.averaging_seconds,
                    first.time_bounds,
                    first.frame,
                    first.qualified,
                    first.scalar_coordinates,
                )
                != (
                    other.statistic,
                    other.averaging_seconds,
                    other.time_bounds,
                    other.frame,
                    other.qualified,
                    other.scalar_coordinates,
                )
            ):
                raise _error(
                    "Wind components do not share an admitted collocated grid, "
                    "physical coordinates, clock, and averaging convention"
                )
            if physical and first.frame == "grid":
                raise _error(
                    "Grid-relative components require verified orthonormal preparation; "
                    "this grid has no admitted native stencil"
                )
        first_grid = first.grid
        if role == "wind" and (area := bindings.get("area")) is not None:
            if common != (
                area.file.path,
                area.grid,
                area.cycle,
                area.calendar,
                area.reference_calendar,
            ):
                raise _error("Physical cell area does not match the final wind grid exactly")
            if area.qualified:
                fields = (*fields, area)
        perimeter_bytes = 4 * sum(first_grid.shape) * PERIMETER_BYTES
        decode_bytes = sum(f.decode_bytes for f in fields)
        accumulators = radius_bins * (64 + sectors * 8) if role == "wind" else 0
        reserved = perimeter_bytes + decode_bytes + accumulators
        if budget < reserved + 9 * CELLS_BYTES:
            raise _error(
                "Minimum decode, perimeter and accumulator working buffers exceed "
                "working_memory_mib",
                observed={"reserved_bytes": reserved, "budget_bytes": budget},
            )
        tile_side = min(256, isqrt((budget - reserved) // CELLS_BYTES) - 2)
        groups.append(
            Group(
                role, fields, tile_side, "model_domain_truncated" if original else "crop_truncated"
            )
        )
    return tuple(groups)


def plan_source(parent, request, *, scratch):
    """Verify concrete files and bind exact fields without reading scientific payloads."""
    del scratch  # NetCDF creates no indexes or decoder logs.
    try:
        return _plan_source(parent, request)
    except (OSError, ValueError, TypeError) as exc:
        from frameit.core.reports import PreflightError

        if isinstance(exc, PreflightError):
            raise
        raise _error(str(exc)) from exc


def _plan_source(parent, request):
    width = request["rmw"]["bin_width_km"]
    bins = round(request["rmw"]["radius_km"] / width)
    sectors = request["rmw"]["azimuth_sectors"]
    budget = request["processing"]["working_memory_mib"] * 2**20
    need = bins * (64 + sectors * 8)
    if (
        bins > np.iinfo(np.intp).max
        or sectors > np.iinfo(np.intp).max
        or (bins * sectors > np.iinfo(np.intp).max or need + 9 * CELLS_BYTES > budget)
    ):
        raise _error(
            "RMW accumulator dimensions exceed the working-buffer budget",
            observed={"accumulator_bytes": need, "budget_bytes": budget},
        )
    files, inventory, cfg, evidence = _source_files(parent, request)
    object_limit = budget // 4096
    zarr_objects = {file.path: {} for file in files if file.representation == "zarr3"}
    if zarr_objects:
        budget -= object_limit * 1024
    selectors = _selectors(request)
    original = bool(inventory)
    original_model = evidence["model"] if original else None
    # Keep dangling grid_mapping references visible before considering a default.
    decode_coords = "coordinates" if original_model in _ORIGINAL_NETCDF_SPHERES else "all"
    times = {centre.time for centre in parent.centres}
    bindings, seen = {}, set()

    def add(field):
        role = field.role
        seen.add(role)
        if field.time not in times:
            return
        matching = bindings.setdefault(field.time, {})
        if role in matching:
            raise _error(f"Ambiguous provider, cycle or member for {role} at {field.time}")
        matching[role] = field

    with ExitStack() as scope:
        cache = {}
        for i, file in enumerate(files):
            _verify_file(file)
            if file.representation == "original_grib":
                from frameit.diagnostics.grib_source import bind_messages

                for field in bind_messages(file, i, inventory, cfg, selectors, budget=budget):
                    add(field)
                continue
            with _open(
                file, zarr_objects=zarr_objects.get(file.path), object_limit=object_limit,
                decode_coords=decode_coords,
            ) as ds:
                if not original and (
                    ds.attrs.get("product_type") != "model_grid"
                    or ds.attrs.get("source_id") != request["input"]["source"]
                ):
                    raise _error("Recorded product does not carry the selected model_grid identity")
                samples = list(
                    _clock_samples(
                        ds, file, inventory=inventory, file_index=i, model=evidence["model"]
                    )
                )
                if not samples:
                    continue
                local = dict(selectors)
                if "area" not in local:
                    wind = local.get("speed", local.get("u"))["field"]
                    if wind in ds:
                        area = ds[wind].attrs.get(
                            "cell_measures", ds[wind].encoding.get("cell_measures", "")
                        )
                        areas = findall(r"\barea:\s*(\S+)", str(area))
                        if len(areas) == 1 and areas[0] in ds:
                            local["area"] = {"field": areas[0]}
                for role, selector in local.items():
                    if selector["field"] not in ds.data_vars and not (
                        role == "area" and selector["field"] in ds.variables
                    ):
                        continue
                    for sample in samples:
                        attrs, metadata = _metadata(
                            ds,
                            ds[selector["field"]],
                            sample,
                            inventory=inventory,
                            source_cfg=cfg,
                            evidence=evidence,
                            file_index=i,
                            scope=scope,
                            cache=cache,
                        )
                        field = _bind_field(
                            ds,
                            file,
                            role,
                            selector,
                            sample,
                            attrs,
                            metadata,
                            cfg.get("wind_pairs", ()) if original else (),
                            original_model=original_model,
                        )
                        add(field)
    if absent := selectors.keys() - seen:
        missing = {role: selectors[role]["field"] for role in sorted(absent)}
        raise _error(
            f"Requested fields not found in the selected provider: {missing}", observed=missing
        )
    groups = tuple(
        (
            c.time,
            _groups(
                bindings.get(c.time, {}),
                selectors,
                radius_bins=bins,
                sectors=sectors,
                budget=budget,
                original=original,
            ),
        )
        for c in parent.centres
    )
    facts = {
        "diagnostic": "best_track",
        "source": request["input"],
        "track_samples": len(parent.centres),
        "files": [{**asdict(file), "path": str(file.path)} for file in files],
        "input_identity_note": (
            "Legacy product: current header/stat evidence only; it does not "
            "establish original publication bytes."
            if parent.identity_scheme.startswith("legacy_")
            else "Metadata fingerprint; not a payload checksum."
        ),
        "inherited_catalogue": evidence.get("metadata_catalogue", []),
        "working_buffers": {
            "budget_bytes": budget,
            "bytes_per_tile_cell_with_halo": CELLS_BYTES,
            "rmw_accumulator_bytes": need,
            "max_open_source_files": 1,
            "unestimated": "Python/backend caches, metadata objects and process RSS",
        },
        "groups": [_group_facts(stamp, group) for stamp, items in groups for group in items],
    }
    if zarr_objects:
        facts["initial_zarr_accesses"] = {p.name: len(keys) for p, keys in zarr_objects.items()}
        facts["working_buffers"]["max_zarr_access_records"] = object_limit
    return DiagnosticPlan(
        parent, request, facts, groups, files,
        zarr_evidence=zarr_objects, decode_coords=decode_coords,
    )


def _group_facts(stamp, group):
    field = group.fields[0]
    return {
        "time": stamp,
        "role": group.role,
        "qualified": group.qualified,
        "tile_side": group.tile_side,
        "temporal_statistic": field.statistic,
        "averaging_seconds": field.averaging_seconds,
        "sources": [{**asdict(f), "file": f.file.path.name} for f in group.fields],
    }


class _GroupView:
    def __init__(self, dataset, group):
        self.dataset, self.group = dataset, group

    def geography(self, window):
        grid = self.group.grid
        indexers = dict(grid.clock_indices) | dict(zip(grid.dims, window, strict=True))
        shape = tuple(
            len(range(*key.indices(n))) for key, n in zip(window, grid.shape, strict=True)
        )
        coordinates = []
        for name, factor in (
            (grid.latitude, grid.latitude_factor),
            (grid.longitude, grid.longitude_factor),
        ):
            da = self.dataset[name]
            values = (
                da.isel({d: indexers[d] for d in da.dims})
                .transpose(*(dim for dim in grid.dims if dim in da.dims))
                .to_numpy()
            )
            shaped = tuple(
                size if dim in da.dims else 1 for dim, size in zip(grid.dims, shape, strict=True)
            )
            coordinates.append(
                np.broadcast_to(
                    (values.astype("float64", copy=False) * factor).reshape(shaped), shape
                )
            )
        return tuple(coordinates)

    def read(self, window):
        lat, lon = self.geography(window)
        return Block(lat, lon, self.read_values(window))

    def read_values(self, window):
        spatial = dict(zip(self.group.grid.dims, window, strict=True))
        values = {}
        for field in self.group.fields:
            data = (
                self.dataset[field.name]
                .isel(dict(field.indexers) | spatial)
                .transpose(*self.group.grid.dims)
                .to_numpy()
            )
            converted = data.astype("float64", copy=False) * field.factor
            lower, upper = field.validity_limits
            if lower is not None:
                converted[data < lower] = np.nan
            if upper is not None:
                converted[data > upper] = np.nan
            values[field.role] = converted
        return values


class _Provider:
    def __init__(self, plan):
        self.plan = plan
        self.groups = dict(plan.samples)
        self.zarr_evidence = {path: dict(keys) for path, keys in (plan.zarr_evidence or {}).items()}

    def samples(self, track_time):
        return self.groups[track_time]

    @contextmanager
    def open_group(self, group):
        file = group.fields[0].file
        if file.representation == "original_grib":
            from frameit.diagnostics.grib_source import open_grib_group

            with open_grib_group(group) as view:
                yield view
            return
        with _open(
            file,
            zarr_objects=self.zarr_evidence.get(file.path),
            object_limit=self.plan.facts["working_buffers"].get("max_zarr_access_records", 0),
            decode_coords=self.plan.decode_coords,
        ) as ds:
            yield _GroupView(ds, group)

    def recheck(self):
        for file in self.plan.files:
            _verify_file(file)
            if file.path in self.zarr_evidence:
                from frameit.diagnostics.zarr_source import verify_accesses

                verify_accesses(file.path, self.zarr_evidence[file.path])


@contextmanager
def open_source(plan, *, scratch):
    del scratch
    yield _Provider(plan)
