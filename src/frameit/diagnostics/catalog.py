"""Lightweight declarations for the v3 request, editor and capabilities."""

from dataclasses import dataclass
from math import isfinite

from frameit.core.reports import PreflightError
from frameit.utils.diagnostics import format_message

AGENCY_PROFILE = "rsmc_la_reunion"
AGENCY_PROFILE_VERSION = "2026-10-07"
INPUT_KINDS = ("original", "model_grid")
WIND_POLICIES = ("require_10min", "native_proxy")
AVAILABILITY_POLICIES = ("report", "error")
RADII = ("pressure_radius_km", "maximum_wind_radius_km", "wind_radii_radius_km")
RMW_METHOD = "annular_mean_speed"
SECTORS = 12
PROCESSING = {"working_memory_mib": 256, "max_open_files": 4}


@dataclass(frozen=True)
class DiagnosticSpec:
    key: str
    version: int
    maturity: str
    providers: tuple[str, ...]
    quantities: tuple[str, ...]
    requirements: tuple[str, ...]
    method: str


BEST_TRACK = DiagnosticSpec(
    "best_track",
    1,
    "experimental",
    INPUT_KINDS,
    (
        "position",
        "maximum 10 m wind",
        "central sea-level pressure",
        "radius of maximum wind",
        "quadrant wind radii",
        "optional gust",
    ),
    (
        "saved centres and exact sample times",
        "source grid Earth model (declared or documented default)",
        "physical height, units, frame and temporal statistic",
        "physical cell area for RMW",
    ),
    "diagnostics/best_track.html",
)


def diagnostic_capabilities():
    return {
        BEST_TRACK.key: {
            "version": BEST_TRACK.version,
            "maturity": BEST_TRACK.maturity,
            "input_kinds": list(BEST_TRACK.providers),
            "admitted_backends": [
                {"kind": "original", "format": "NetCDF", "preparation": "native collocated"},
                {
                    "kind": "original",
                    "format": "GRIB",
                    "preparation": "spherical regular_ll; selected 10 m wind and MSLP parameters",
                    "dependencies": ["eccodes"],
                },
                {"kind": "model_grid", "format": "NetCDF", "preparation": "native collocated"},
                {
                    "kind": "model_grid",
                    "format": "sharded Zarr v3",
                    "preparation": "native collocated",
                },
            ],
            "quantities": list(BEST_TRACK.quantities),
            "requirements": list(BEST_TRACK.requirements),
            "agency_templates": {
                "RSMC": {"profile": AGENCY_PROFILE, "version": AGENCY_PROFILE_VERSION}
            },
            "dependencies": {"core": ["numpy", "pyproj", "xarray", "netCDF4"]},
            "method": BEST_TRACK.method,
        }
    }


def diagnostics_schema():
    def obj(properties, required=(), **extra):
        return {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
            **({"required": list(required)} if required else {}),
            **extra,
        }

    text = {"$ref": "#/$defs/text"}
    positive = {"type": "number", "exclusiveMinimum": 0}
    selector_properties = {
        "field": text,
        "level": obj({"value": {"type": "number"}, "units": text}, ("value", "units")),
    }

    def fields(*, original):
        properties = {**selector_properties, **({"group": text} if original else {})}
        selector = {"anyOf": [text, obj(properties, ("field",))]}
        return obj(
            {
                "wind": {
                    "oneOf": [
                        obj(dict.fromkeys(keys, selector), keys)
                        for keys in (("speed",), ("u", "v"))
                    ]
                },
                **dict.fromkeys(("sea_level_pressure", "gust", "cell_area"), selector),
            },
            ("wind", "sea_level_pressure"),
        )

    return obj(
        {
            BEST_TRACK.key: obj(
                {
                    "agency_template": {"const": "RSMC"},
                    "input": obj(
                        {"kind": {"enum": list(INPUT_KINDS)}, "source": text}, ("kind", "source")
                    ),
                    # The conditional crop schema below excludes the original-only group key.
                    "fields": fields(original=True),
                    "search": obj(dict.fromkeys(RADII, positive), RADII),
                    "rmw": obj(
                        {
                            "method": {"const": RMW_METHOD},
                            "radius_km": positive,
                            "bin_width_km": positive,
                            "azimuth_sectors": {
                                "type": "integer",
                                "minimum": 4,
                                "default": SECTORS,
                            },
                        },
                        ("method", "radius_km", "bin_width_km"),
                    ),
                    "wind_time_policy": {"enum": list(WIND_POLICIES), "default": WIND_POLICIES[0]},
                    "on_unavailable": {
                        "enum": list(AVAILABILITY_POLICIES),
                        "default": AVAILABILITY_POLICIES[0],
                    },
                    "processing": obj(
                        {
                            key: {"type": "integer", "minimum": 1, "default": value}
                            for key, value in PROCESSING.items()
                        },
                        default=PROCESSING,
                    ),
                    "reference": obj({"file": text, "idswi": text}, ("file", "idswi")),
                },
                ("agency_template", "input", "fields", "search", "rmw"),
                **{
                    "if": {
                        "properties": {"input": {"properties": {"kind": {"const": "model_grid"}}}}
                    },
                    "then": {"properties": {"fields": fields(original=False)}},
                },
            )
        },
        default={},
    )


def _invalid(path, expected, observed):
    from frameit.core.reports import Diagnostic

    raise PreflightError(
        [
            Diagnostic(
                path,
                f"{path} requires {expected}",
                expected,
                observed,
                [f"Set {path} to {expected}."],
                code="E2001",
            )
        ]
    )


def resolve_diagnostics(raw, *, base_dir):
    from frameit.core import configuration as c

    p = f"diagnostics.{BEST_TRACK.key}"
    try:
        root = c._keys(raw, {BEST_TRACK.key}, "diagnostics")
        if BEST_TRACK.key not in root:
            return {}
        required = {"agency_template", "input", "fields", "search", "rmw"}
        best = c._keys(
            root[BEST_TRACK.key],
            required | {"wind_time_policy", "on_unavailable", "processing", "reference"},
            p,
            required=required,
        )
        c._choice(best["agency_template"], ("RSMC",), f"{p}.agency_template")
        source = c._keys(
            best["input"], {"kind", "source"}, f"{p}.input", required={"kind", "source"}
        )
        c._choice(source["kind"], INPUT_KINDS, f"{p}.input.kind")
        c._text(source["source"], f"{p}.input.source")

        fields = c._keys(
            best["fields"],
            {"wind", "sea_level_pressure", "gust", "cell_area"},
            f"{p}.fields",
            required={"wind", "sea_level_pressure"},
        )
        wind = c._keys(fields.pop("wind"), {"speed", "u", "v"}, f"{p}.fields.wind")
        if set(wind) not in ({"speed"}, {"u", "v"}):
            _invalid(
                f"{p}.fields.wind",
                "one speed selector or a pair of u and v selectors",
                sorted(wind),
            )
        selectors = {f"{p}.fields.{key}": value for key, value in fields.items()}
        selectors.update({f"{p}.fields.wind.{key}": value for key, value in wind.items()})
        for path, selector in selectors.items():
            if isinstance(selector, str):
                c._text(selector, path)
                continue
            allowed = {"field", "level"}
            if source["kind"] == "original":
                allowed.add("group")
            selector = c._keys(selector, allowed, path, required={"field"})
            c._text(selector["field"], f"{path}.field")
            if "group" in selector:
                c._text(selector["group"], f"{path}.group")
            if "level" in selector:
                level = c._keys(
                    selector["level"],
                    {"value", "units"},
                    f"{path}.level",
                    required={"value", "units"},
                )
                _check_finite(level["value"], f"{path}.level.value")
                c._text(level["units"], f"{path}.level.units")

        search = c._keys(best["search"], set(RADII), f"{p}.search", required=set(RADII))
        for key, value in search.items():
            _check_distance(value, f"{p}.search.{key}")
        distances = [search[key] for key in RADII]
        if distances != sorted(distances):
            _invalid(
                f"{p}.search", "pressure radius ≤ maximum-wind radius ≤ wind-radii radius", search
            )
        rmw = c._keys(
            best["rmw"],
            {"method", "radius_km", "bin_width_km", "azimuth_sectors"},
            f"{p}.rmw",
            required={"method", "radius_km", "bin_width_km"},
        )
        c._choice(rmw["method"], (RMW_METHOD,), f"{p}.rmw.method")
        for key in ("radius_km", "bin_width_km"):
            _check_distance(rmw[key], f"{p}.rmw.{key}")
        if rmw["radius_km"] > search["maximum_wind_radius_km"]:
            _invalid(
                f"{p}.rmw.radius_km",
                "a radius no larger than maximum_wind_radius_km",
                rmw["radius_km"],
            )
        ratio = rmw["radius_km"] / rmw["bin_width_km"]
        if not isfinite(ratio) or ratio < 3 - 1e-9 or abs(ratio - round(ratio)) > 1e-9:
            _invalid(f"{p}.rmw.bin_width_km", "a width giving at least three whole bins", ratio)
        sectors = rmw.setdefault("azimuth_sectors", SECTORS)
        if type(sectors) is not int or sectors < 4:
            _invalid(f"{p}.rmw.azimuth_sectors", "an integer of at least four", sectors)
        best["rmw"] = rmw

        for key, choices in (
            ("wind_time_policy", WIND_POLICIES),
            ("on_unavailable", AVAILABILITY_POLICIES),
        ):
            c._choice(best.setdefault(key, choices[0]), choices, f"{p}.{key}")
        processing = c._keys(best.get("processing", {}), set(PROCESSING), f"{p}.processing")
        best["processing"] = {**PROCESSING, **processing}
        for key, value in best["processing"].items():
            if type(value) is not int or value <= 0:
                _invalid(f"{p}.processing.{key}", "a positive integer", value)
        if "reference" in best:
            reference = c._keys(
                best["reference"], {"file", "idswi"}, f"{p}.reference", required={"file", "idswi"}
            )
            c._text(reference["idswi"], f"{p}.reference.idswi")
            reference["file"] = c._path(
                reference["file"], base_dir, f"{p}.reference.file", preserve_symlink=True
            )
            best["reference"] = reference
        return {BEST_TRACK.key: best}
    except PreflightError as exc:
        for error in exc.diagnostics:
            error.code = "E2001"
        raise


def _check_finite(value, path):
    from frameit.core.configuration import _finite

    try:
        _finite(value, path)
    except OverflowError:
        _invalid(path, "a finite number representable in float64", value)


def _check_distance(value, path):
    _check_finite(value, path)
    if value <= 0 or not isfinite(float(value) * 1000):
        _invalid(path, "a positive finite distance in kilometres", value)


def preflight_advice(result, *, products=None):
    """A product plan is advice only, never admission of a completed parent."""
    if result.command != "validate":
        return
    best = result.conf.yaml_config.get("diagnostics", {}).get(BEST_TRACK.key)
    if best is None:
        return
    result.facts["diagnostics"] = {
        BEST_TRACK.key: {"input": best["input"], "requirements": list(BEST_TRACK.requirements)}
    }
    result.deferred_checks.append(
        {
            "path": "diagnostics.best_track",
            "status": "deferred",
            "message": "Use frameit run-diag --check to admit the completed parent.",
        }
    )
    if products is None or best["input"]["kind"] != "model_grid":
        return
    source = best["input"]["source"]
    targets = [
        product
        for product in products
        if product["product"] == "model_grid" and product["source"] == source
    ]
    stored = {
        name for product in targets for name in (product.get("stored_names") or product["fields"])
    }
    selectors = {**best["fields"], **best["fields"]["wind"]}
    del selectors["wind"]
    missing = {
        value if isinstance(value, str) else value["field"] for value in selectors.values()
    } - stored
    if missing:
        warnings = result.facts.setdefault("warnings", [])
        warnings.append(
            format_message(
                "W2001",
                f"diagnostics.best_track: planned model_grid for {source!r} does not list "
                f"{', '.join(sorted(missing))}. Select the exact exported fields; "
                "validation does not add them to products.model_grid.fields.",
            )
        )
