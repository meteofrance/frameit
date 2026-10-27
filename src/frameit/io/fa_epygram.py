"""Optional EPyGrAM FA calls inside the disposable native worker only.

Uses the unmodified EPyGrAM API (Météo-France, CeCILL-C). No EPyGrAM code or
definition tables are vendored. Source files are opened explicitly read-only.
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version

import numpy as np

from frameit.io.fa_contracts import layout_definition


def initialize(destination, radius):
    try:
        if version("epygram") != "2.1.0":
            raise ValueError("This FA backend requires EPyGrAM 2.1.0")
    except PackageNotFoundError as exc:
        raise ValueError("EPyGrAM backend requested: install FrameIt[fa-epygram] in the "
                         "helper environment; input.fa.python_executable can select it") from exc
    for name, expected in (("falfilfa4py", "1.2.1"), ("ctypesForFortran", "1.3.0"),
                           ("ectrans4py", "1.6.0"), ("netCDF4", "1.7.2")):
        try:
            actual = version(name)
        except PackageNotFoundError:
            actual = None
        if actual != expected:
            raise ValueError(f"EPyGrAM 2.1.0 helper requires {name}=={expected}; "
                             "install the coherent fa-epygram extra in a separate environment")
    # EPyGrAM supports a user configuration read during package import. A private
    # empty HOME prevents personal tables/plugins and disables its GRIB runtime
    # before it can initialize any native format. Installed files stay untouched.
    os.environ["HOME"] = str(destination)
    config = destination / ".epygram"
    config.mkdir()
    settings = ("implemented_formats = ['FA']\nactivate_plugins = []\n"
                "init_at_import = False\nspectral_coeff_order = 'model'\n")
    if radius is not None:
        settings += f"FA_default_geoid = {{'a': {float(radius)!r}, 'b': {float(radius)!r}}}\n"
    (config / "userconfig.py").write_text(settings, encoding="utf-8")
    import epygram

    if epygram.formats.runtime_available_formats != ["FA"]:
        raise ValueError("EPyGrAM FA-only initialization failed")
    epygram.init_env(omp_num_threads=1, no_mpi=True, unlimited_stack=False)
    return epygram


def _inventory(resource):
    """Library inventory plus bounded native length/duplicate observations.

    EPyGrAM omits the first seven cadre records and DATX, and does not expose
    lengths or reject duplicate IDs. Observe only these index facts on its unit;
    do not open a parallel raw reader or classify/decode unselected fields.
    """
    from falfilfa4py import LFI

    count = int(LFI.wlfinaf(resource._unit)[0])
    if not 7 <= count <= 100_000:
        raise ValueError("FA index is invalid or exceeds the 100000-record inventory budget")
    LFI.wlfipos(resource._unit)
    headers = [LFI.wlficas(resource._unit, True)[0].strip() for _ in range(7)]
    names = headers + list(resource.listfields())
    if LFI.wlfinfo(resource._unit, "DATX-DES-DONNEES")[0] > 0:
        names.insert(7, "DATX-DES-DONNEES")
    if len(set(names)) != len(names) or any(not name for name in names):
        raise ValueError("Empty or duplicate FA record in EPyGrAM inventory")
    if count != len(names):
        raise ValueError("EPyGrAM inventory contradicts native FA record count")
    records = {name: int(LFI.wlfinfo(resource._unit, name)[0]) for name in names}
    if any(length <= 0 for length in records.values()):
        raise ValueError("Missing or invalid native FA record length")
    return records


def _clocks(resource):
    """Use library validity, rejecting its permissive raw-clock normalization."""
    from falfilfa4py import FA

    basis, valid = resource.validity.getbasis(), resource.validity.get()
    lead = resource.validity.term().total_seconds()
    if not (1678 <= basis.year <= 2261 and 1678 <= valid.year <= 2261 and lead >= 0):
        raise ValueError("Unsupported FA valid/reference time or negative forecast lead")
    stamp = FA.wfadiex(resource._unit)
    if (list(stamp[:5]) != [basis.year, basis.month, basis.day, basis.hour, basis.minute]
            or int(stamp[13]) != basis.hour * 3600 + basis.minute * 60 + basis.second
            or int(stamp[14]) != lead):
        raise ValueError("Unsupported or inconsistent FA forecast reference date")
    duration = resource.validity.cumulativeduration().total_seconds()
    return {"reference_time": basis.isoformat(), "valid_time": valid.isoformat(),
            "lead_seconds": int(lead), "header_interval_start_seconds": int(lead - duration)}


def structure_value(resource, name, records, kind, count=None, *, budget=4096):
    """Read named small structure, never physical words as an alternate codec.

    T0 is mixed integer/IEEE-seconds; the library returns only its year. L0
    converts every nonzero word to True, concealing invalid logical encodings.
    Those two evidenced structural types alone need a same-unit raw observation.
    FBUF character columns lack library definitions and arrive as int64 words.
    """
    from frameit.io.fa_contracts import SURFEX_METADATA
    from frameit.io.fa_worker import _text

    allowed = {"SFX." + key for key in SURFEX_METADATA} | {
        "SFX._FBUF_" + key for key in ("NAME", "TYPE", "MASK")}
    if name not in allowed:
        raise ValueError(f"{name}: not an evidenced structural metadata record")
    length = records.get(name, 0)
    if not 0 < length <= budget:
        raise ValueError(f"{name}: missing or oversized required FA metadata record")
    if count is not None and length != count:
        raise ValueError(f"{name}: inconsistent typed metadata length; expected {count}")
    if kind in {"logical", "date_time"}:
        from falfilfa4py import LFI

        words = LFI.wlfilec(resource._unit, name, length, False)
        if kind == "date_time":
            return words
        if int(words[0]) not in (0, 1):
            raise ValueError(f"{name}: unsupported logical word (only evidenced 0/1 admitted)")
        return bool(words[0])
    # These allowlisted structural records must not be guessed from FANION's
    # broad -91/-93/-94 fallback. Use the version-matched library Misc accessor
    # directly; it owns typed decoding, while the checks below verify its result.
    field = resource._readMiscField(name, getdata=True)
    if getattr(field, "structure", "Misc") != "Misc":
        raise ValueError(f"{name}: library type contradicts structural metadata")
    data = np.asarray(field.getdata())
    if kind == "character":
        if data.dtype.kind == "U" and data.shape == ():
            text = str(data.item())
            if len(text) != length or any(ord(c) > 127 for c in text):
                raise ValueError(f"{name}: invalid ASCII/length in FA character metadata")
            return text.rstrip(" \x00")
        if data.dtype == np.int64 and data.shape == (length,):
            return _text(data)
    elif kind in {"integer", "integer_array"}:
        if data.dtype == np.int64 and data.size == length:
            if kind == "integer" and data.shape in {(), (1,)}:
                return int(data.item())
            if kind == "integer_array" and data.shape == (length,):
                return data
    elif kind == "real" and data.dtype == np.float64 and data.shape in {(), (1,)}:
        return float(data.item())
    raise ValueError(f"{name}: unexpected actual library type/shape {data.dtype}/{data.shape}")


def typed_metadata(resource, name, records, metadata, directory):
    from frameit.io.fa_worker import _typed_spec

    kind, count = _typed_spec(records, name, metadata, directory)
    value = structure_value(resource, name, records, kind, count)
    if kind == "integer_array":
        value = value.tolist()
    elif kind == "date_time":
        seconds = float(value.view(np.float64)[3])
        if not np.isfinite(seconds):
            raise ValueError(f"{name}: nonfinite state timestamp")
        value = {"date": value[:3].tolist(), "seconds": seconds}
    elif kind == "real" and not np.isfinite(value):
        value = {"nonfinite": str(value)}
    return {"type": kind, "value": value, "evidence": layout_definition(metadata),
            "accessor": ("same_resource_structural_words" if kind in {"logical", "date_time"}
                         else "EPyGrAM._readMiscField")}


def check_surface_layout(resource, metadata, directory, records, request):
    """Finite C1 capability, not admission from a library name/default table."""
    absent = sorted(directory.keys() - records.keys())
    if absent:
        raise ValueError(f"SURFEX directory references absent records {absent}")
    dimensions = resource.geometry.dimensions
    ci_shape = [dimensions.get("Y_CIzone", dimensions.get("Y")),
                dimensions.get("X_CIzone", dimensions.get("X"))]
    reasons = []
    if layout_definition(metadata) is None:
        reasons.append("EPyGrAM SURFEX execution requires the evidenced AROME-47 SURFEX-8.1 layout")
    if (ci_shape != [metadata["JMAX"], metadata["IMAX"]]
            or metadata["DIM_FULL"] != metadata["IMAX"] * metadata["JMAX"]):
        reasons.append("SURFEX IMAX/JMAX/DIM_FULL contradict the native CI dimensions")
    metadata["capability_reasons"] = reasons
    if reasons and request.get("validate_selection", True) and request.get("fields"):
        raise ValueError("; ".join(reasons))


def inspect_resource(resource, request):
    from falfilfa4py import FA, LFI

    from frameit.io.fa_worker import _active_header, _describe

    # Transitional public-contract adapter: original modern header flags, encoded
    # CI corners and normalized A/PREFER remain necessary to the existing grid
    # signature/corner guards. No second geometry reconstruction happens here.
    # C2 transfers that labelled-grid contract; use the library's raw-header API
    # on this resource until then, rather than another raw resource/prepass.
    header = _active_header(dict(resource._raw_header_get()))
    info = _describe(FA, LFI, resource._unit, header, _clocks(resource), resource.cdiden.strip(),
                     _inventory(resource), request, source=resource)
    for name, descriptor in info["field_descriptors"].items():
        if (descriptor["native"]["representation"] == "gridpoint"
                and descriptor["eligibility"]["decode"] != "blocked"):
            descriptor["sampling"]["epygram"] = field_metadata(resource, name, header)
    return info


def field_metadata(resource, name, header):
    field = resource.readfield(name, getdata=False)
    if getattr(field, "structure", None) != "H2D" or field.spectral:
        raise ValueError(f"{name}: only decoded gridpoint H2D records are admitted")
    if field.validity.cumulativeduration() is not None:
        raise ValueError(f"{name}: EPyGrAM reports an interval; selection is instantaneous only")
    geometry = field.geometry
    if (geometry.position_on_horizontal_grid != "center"
            or (geometry.dimensions["Y"], geometry.dimensions["X"]) != (
                header["KNLATI"], header["KNXLON"])):
        raise ValueError(f"{name}: EPyGrAM sampling/storage contradicts the native FA contract")
    vertical = geometry.vcoordinate
    levels = np.asarray(vertical.levels)
    if levels.shape != (1,) or not np.isfinite(levels).all():
        raise ValueError(f"{name}: one finite native level per selected record is required")
    if vertical.typeoffirstfixedsurface == 119:
        grid = vertical.grid
        if grid.get("ABgrid_position") != "flux":
            raise ValueError(f"{name}: unqualified hybrid coefficient grid")
        a = [entry[1]["Ai"] for entry in grid["gridlevels"]]
        b = [entry[1]["Bi"] for entry in grid["gridlevels"]]
        if (not np.array_equal(a, np.asarray(header["PAHYBR"]) * header["PREFER"])
                or not np.array_equal(b, header["PBHYBR"])):
            raise ValueError(f"{name}: EPyGrAM hybrid coefficients contradict native PREFER/A/B")
    return {"type_of_first_fixed_surface": int(vertical.typeoffirstfixedsurface),
            "levels": levels.tolist(), "horizontal_position": "center",
            "header_position_default": vertical.position_on_grid,
            "position_policy": "library defaults/tables are not producer-specific sampling proof; "
                               "cube mass/interface sampling is an explicit user declaration",
            "evidence": "EPyGrAM-2.1.0 FA field definitions and header reader"}


def read_values(resource, name, shape):
    # Selection already checked raw native flags and H2D metadata. Do not let a
    # subsequent FANION failure dispatch through readfield's broad Misc fallback
    # and read physical words with FALAIS. This version-matched library accessor
    # uses fieldencoding and fails closed instead; no alternate decoder is tried.
    field = resource._readH2DField(name, getdata=True)
    if field.structure != "H2D" or field.spectral:
        raise ValueError(f"{name}: coefficients/metadata cannot be returned as gridpoint values")
    values = np.ma.asarray(field.getdata())
    if values.dtype != np.float64:
        raise ValueError(f"{name}: unexpected EPyGrAM decoded dtype {values.dtype}; "
                         "float64 required")
    if values.shape != tuple(shape):
        raise ValueError(f"{name}: EPyGrAM decoded shape contradicts the native grid")
    return np.asarray(values.filled(np.nan)), bool(np.ma.getmaskarray(values).any())
