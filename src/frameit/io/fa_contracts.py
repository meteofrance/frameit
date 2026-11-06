"""Versioned private FA facts and declarations, with no native-library imports.

Descriptors are ordinary JSON values, not native handles or scientific approval.
The 8.1 layout below records the P0 corpus, not a catalogue of physical fields.
No physical field catalogue is applied automatically.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy

PROTOCOL_VERSION = 1
DESCRIPTOR_VERSION = 1
SURFEX_LAYOUT = "arome-47-surfex-8.1-observed-v1"
SPECTRAL_GATE = (
    "spectral-to-grid execution is gated: an encoding-qualified coefficient contract "
    "and independent native-grid reference are required "
    "(see Spectral FA support and limitations in the user guide)"
)
CUBE_VERTICAL_INTERPRETATION = (
    "native labels and interface A/B/reference checked against EPyGrAM; "
    "mass/interface and vector sampling explicitly declared by user; "
    "no physical-coordinate diagnosis or independent producer qualification"
)

# Only small structural metadata whose raw-word layout is evidenced by P0 and
# the existing fixture recipe. Physical values are never decoded from raw words.
SURFEX_METADATA = {
    **{name: ("character", None) for name in ("PROGRAM", "GRID_TYPE", "SURF",
                                            "STORAGE_TYPE", "STORAGETYPE")},
    **{name: ("integer", 1) for name in ("VERSION", "BUG", "DIM_FULL", "IMAX", "JMAX",
                                        "MASDEV", "BUGFIX", "SPLIT_PATCH", "_FBUF_SIZE")},
    **{name: ("logical", 1) for name in ("PACK", "L1D", "L2D", "CARTESIAN")},
    **{name: ("real", 1) for name in ("LAT0", "LON0", "RPK", "BETA", "LATORI", "LONORI")},
    "DTCUR": ("date_time", 4),
    "_FBUF_DIM1": ("integer_array", None),
    "_FBUF_DIM2": ("integer_array", None),
}


def layout_definition(metadata):
    if tuple(metadata.get(key) for key in ("PROGRAM", "VERSION", "BUG", "MASDEV", "BUGFIX")) == (
        "AROME", 8, 1, 47, 0):
        return SURFEX_LAYOUT
    return None


def check_expected_source(metadata, expected):
    for key, value in expected.items():
        if key not in metadata or metadata[key] != value:
            raise ValueError(f"input.fa.expected_source.{key}={value!r} conflicts with "
                             f"native source value {metadata.get(key)!r}")


def native_descriptor(name, length, encoding, directory, geometry, metadata, clocks):
    """Describe facts only; unknown shapes, units, bases and masks stay unknown."""
    layout = layout_definition(metadata)
    spec = SURFEX_METADATA.get(name.removeprefix("SFX.")) if layout and name.startswith(
        "SFX.") else None
    representation, dtype, shape = "unknown", None, None
    reasons = []
    if spec is not None:
        representation, dtype = "typed_metadata", spec[0]
        shape = [] if spec[1] == 1 or dtype == "character" else [length]
        reasons.append("structural metadata is not a horizontal physical field")
    elif encoding.get("native_error"):
        reasons.append(encoding["native_error"])
    elif encoding.get("exists"):
        representation = "spectral" if encoding["spectral"] else "gridpoint"
        dtype = "float64"  # native wrapper's decoded dtype, not on-disk precision
        if representation == "spectral":
            reasons.append(SPECTRAL_GATE)
        elif geometry["KTYPTR"] < 0:
            shape = [geometry["KNLATI"], geometry["KNXLON"]]
        else:
            reasons.append("nonregional grid representation is not qualified")
    else:
        reasons.append("native encoding not probed or unknown")
    if metadata.get("layout_status") == "incomplete_surfex_directory":
        reasons.append("incomplete SURFEX directory/source metadata; physical execution is blocked")
    reasons.extend(metadata.get("capability_reasons", []))
    if metadata and (metadata.get("PROGRAM") != "AROME" or metadata.get("PACK") != 0):
        reasons.append("only AROME SURFEX PACK=0 execution is admitted")
    if directory and (directory.get("TYPE") != "X1" or directory.get("DIM2") != -1
                      or shape is None or len(shape) != 2
                      or directory.get("DIM1") != shape[0] * shape[1]):
        reasons.append("SURFEX physical execution requires dense horizontal X1 dimensions")
    status = "blocked" if reasons else "conditional"
    native = {"word_count": length, "type": directory.get("TYPE"),
              "directory": deepcopy(directory), "representation": representation,
              "shape": shape, "decoded_dtype": dtype, "encoding": deepcopy(encoding)}
    if representation == "spectral":
        native["spectral_contract"] = {
            "native_header": {key: deepcopy(geometry[key]) for key in (
                "KTYPTR", "KTRONC") if key in geometry},
            "coefficient_count": None, "coefficient_order": None,
            "space": None, "normalization": None, "transform_truncation": None,
            "dimension_evidence": "unresolved; indexed word count and grid shape "
                                  "are not coefficient dimensions",
            "status": "blocked_unqualified_fa_contract",
        }
    return {
        "schema_version": DESCRIPTOR_VERSION, "native_id": name,
        "source": {"container": "FA", "producer_metadata": deepcopy(metadata),
                   "layout_definition": layout},
        "native": native,
        "sampling": {"layout": "native_storage_y_x" if shape and len(shape) == 2 else None,
                     "physical_location": None, "vector_basis": None,
                     "native_vertical_header": {
                         key: deepcopy(geometry[key]) for key in (
                             "KNIVER", "PREFER", "PAHYBR", "PBHYBR") if key in geometry},
                     "vertical_interpretation": "unqualified; no field-level association or "
                                                "full/interface/physical-coordinate definition"},
        "units": {"value": None, "origin": "unresolved"},
        "scaling": {"status": "inapplicable_raw_metadata" if spec else "not_exposed",
                    "multiplier": None, "offset": None,
                    "policy": ("raw structural words; no physical codec" if spec else
                               "native decoder; encoded factors or unresolved-warning guard")},
        "mask": {"support_label": directory.get("MASK"), "undefined": "not_read",
                 "support_map": None},
        "temporal_support": {**clocks, "kind": None, "bounds": None, "origin": "unresolved"},
        "semantic_evidence": [{"origin": "native_index", "encoding_probe": (
            "native_error" if "native_error" in encoding else
            "native_flags" if "exists" in encoding else "not_requested")},
                              {"origin": "observed_layout", "definition": layout}],
        "eligibility": {"inspect": "available",
                        "metadata_decode": "conditional" if spec else "blocked",
                        "decode": status, "dataset": "blocked",
                        "extract": "blocked", "polar": "blocked", "diagnostic": "blocked",
                        "reasons": reasons, "conditions": [
                            "explicit field meaning", "admitted geometry", "native scaling check"]},
    }


def resolve_descriptor(descriptor, declaration):
    """Native facts > matched conventions > user completion; never relabel facts.

    Currently no release-qualified physical convention fills missing semantics.
    Keeping this distinction explicit prevents a future table from overriding
    an existing native fact or silently converting an existing user declaration.
    """
    validate_descriptor(descriptor)
    result = deepcopy(descriptor)
    if declaration is None:
        raise ValueError(f"declare input.fa.field_metadata.{result['native_id']} "
                         "(units, kind, temporal_kind); native identity is not inferred")
    if result["eligibility"]["decode"] == "blocked":
        raise ValueError(f"{result['native_id']}: " + "; ".join(result["eligibility"]["reasons"]))
    for key, fact in (("units", result["units"]["value"]),
                      ("temporal_kind", result["temporal_support"]["kind"])):
        if fact is not None and declaration.get(key) != fact:
            raise ValueError(f"{result['native_id']}: declared {key} contradicts native/profile "
                             f"value {fact!r}; no relabelling or implicit conversion")
    if declaration.get("temporal_kind") != "instantaneous":
        raise ValueError("Only explicit instantaneous FA fields are supported")
    if not isinstance(declaration.get("units"), str) or not declaration["units"].strip():
        raise ValueError("Explicit source units are required")
    if declaration.get("kind") not in {"continuous", "categorical"}:
        raise ValueError("Explicit continuous/categorical kind is required")
    if result["units"]["value"] is None:
        result["units"] = {"value": declaration["units"],
                           "origin": "explicit_input.fa.field_metadata"}
    if result["temporal_support"]["kind"] is None:
        result["temporal_support"].update(kind="instantaneous",
                                        origin="explicit_input.fa.field_metadata")
    result["declaration"] = deepcopy(declaration)
    result["scaling"]["allow_unscaled"] = declaration.get("allow_unscaled", False)
    result["semantic_evidence"].append({"origin": "explicit_input.fa.field_metadata",
                                       "independent_validation": False})
    # These are conditional capabilities, not proof that downstream geometry,
    # categorical sampling or native scaling requirements have passed.
    result["eligibility"].update(dataset="conditional", extract="conditional", polar="conditional")
    result["eligibility"]["conditions"] = ["admitted geometry", "native scaling check",
                                            "explicit eligible polar selection/method"]
    return result


def validate_descriptor(descriptor):
    if (not isinstance(descriptor, dict)
            or type(descriptor.get("schema_version")) is not int
            or descriptor.get("schema_version") != DESCRIPTOR_VERSION):
        raise ValueError("Unsupported FA field descriptor schema_version")
    for key in ("native_id", "source", "native", "sampling", "units", "scaling", "mask",
                "temporal_support", "semantic_evidence", "eligibility"):
        if key not in descriptor:
            raise ValueError(f"Incomplete FA field descriptor: missing {key}")
    if not isinstance(descriptor["native_id"], str) or not descriptor["native_id"]:
        raise ValueError("Invalid FA field descriptor native_id")
    for key in ("source", "native", "sampling", "units", "scaling", "mask", "temporal_support",
                "eligibility"):
        if not isinstance(descriptor[key], dict):
            raise ValueError(f"Invalid FA field descriptor {key}")
    scaling = descriptor["scaling"]
    if scaling.get("status") == "encoded":
        try:
            mantissa, exponent = scaling["mantissa"], scaling["exponent"]
            if (type(mantissa) is not int or type(exponent) is not int
                    or not all(-(1 << 63) < value < (1 << 63)
                               for value in (mantissa, exponent))):
                raise ValueError("invalid encoded factors")
            divisor = mantissa * 10.**exponent
            multiplier = 1. / divisor
            if (not math.isfinite(divisor) or not math.isfinite(multiplier) or multiplier == 0
                    or scaling["evidence"] != "same_unit_GRIB2_local_85_1"
                    or descriptor["native"]["encoding"]["packing"] != 120
                    or not all(type(scaling[key]) in (int, float)
                               for key in ("divisor", "multiplier", "offset"))
                    or scaling["divisor"] != divisor or scaling["multiplier"] != multiplier
                    or scaling["offset"] != 0 or scaling["fallback"] is not None):
                raise ValueError("inconsistent encoded scaling evidence")
        except (ValueError, KeyError, TypeError, OverflowError, ZeroDivisionError) as exc:
            raise ValueError("Invalid encoded FA scaling descriptor") from exc
    try:
        json.dumps(descriptor, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("FA field descriptor must contain finite JSON values only") from exc
