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
        raise ValueError("FA requires EPyGrAM: install FrameIt[fa] in the "
                         "helper environment; input.fa.python_executable can select it") from exc
    for name, expected in (("falfilfa4py", "1.2.1"), ("ctypesForFortran", "1.3.0"),
                           ("ectrans4py", "1.6.0"), ("netCDF4", "1.7.2")):
        try:
            actual = version(name)
        except PackageNotFoundError:
            actual = None
        if actual != expected:
            raise ValueError(f"EPyGrAM 2.1.0 helper requires {name}=={expected}; "
                             "install the coherent fa extra in the helper environment")
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
                raise ValueError(f"{name}: Invalid ASCII/length in FA character metadata")
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
    from falfilfa4py import FA

    from frameit.io.fa_worker import _active_header, _describe

    # Narrow original-header evidence: the library geometry omits admission flags,
    # independently encoded CI corners and original normalized A. Never reconstruct
    # geometry from these words on the EPyGrAM path.
    header = _active_header(dict(resource._raw_header_get()))
    info = _describe(FA, resource._unit, header, _clocks(resource), resource.cdiden.strip(),
                     _inventory(resource), request, source=resource)
    geometry_options = request.get("geometry_options")
    if geometry_options is not None:
        header["epygram"] = geometry_contract(resource.geometry, header, geometry_options)
    selected = {name: descriptor for name, descriptor in info["field_descriptors"].items()
                if descriptor["native"]["representation"] == "gridpoint"
                and descriptor["eligibility"]["decode"] != "blocked"}
    if selected and (resource.geometry.dimensions.get("Y"),
                     resource.geometry.dimensions.get("X")) != (header["KNLATI"], header["KNXLON"]):
        raise ValueError("EPyGrAM sampling/storage contradicts the native FA contract")
    for name, descriptor in selected.items():
        facts = field_metadata(resource, name)
        descriptor["sampling"]["epygram"] = facts
        if facts["type_of_first_fixed_surface"] == 119 and "hybrid_contract" not in info:
            from frameit.io.fa_cubes import hybrid_contract

            info["hybrid_contract"] = hybrid_contract(header, resource.geometry.vcoordinate)
    return info


def geometry_contract(geometry, header, options):
    """Qualified library axes/CRS/zones, serialized without native objects.

    EPyGrAM recentres projected x/y on CI. Translate its CRS origin to the
    established CF tangent-latitude origin, without changing sampling or fitting
    the independently encoded corners. Only O(nx+ny) coordinates cross the worker.
    """
    from pyproj import CRS, Transformer

    from frameit.io.fa_geometry import admitted_geometry

    p, k, selected = admitted_geometry(header, options)
    ny, nx = header["KNLATI"], header["KNXLON"]
    if (geometry.position_on_horizontal_grid != "center"
            or (geometry.dimensions.get("Y"), geometry.dimensions.get("X")) != (ny, nx)):
        raise ValueError("EPyGrAM geometry contradicts native FA storage dimensions/position")
    regular = p[1] == -9
    if geometry.name != ("regular_lonlat" if regular else "lambert"):
        raise ValueError("EPyGrAM geometry is outside the qualified regional family")

    def zone(name):
        corners = geometry.gimme_corners_ij(subzone=name)
        x0, y0 = corners["ll"]
        x1, y1 = corners["ur"]
        bounds = np.asarray([x0, x1 + 1, y0, y1 + 1])
        if (not np.isfinite(bounds).all() or not np.equal(bounds, np.floor(bounds)).all()
                or not (0 <= x0 <= x1 < nx and 0 <= y0 <= y1 < ny)):
            raise ValueError("Invalid EPyGrAM native FA zone bounds")
        return bounds.astype(int).tolist()

    zones = {"CI": zone("CI")}
    if not regular:
        zones["C"] = zone("C")
        zones["CIE"] = zone(None)
    if (zones["CI"] != [int(k[2]) - 1, int(k[3]), int(k[4]) - 1, int(k[5])]
            or zones[options["subdomain"]] != list(selected)):
        raise ValueError("EPyGrAM native zones contradict original FA domain indices")
    x, _ = geometry.ij2xy(np.arange(nx), 0)
    _, y = geometry.ij2xy(0, np.arange(ny))
    if np.ma.is_masked(x) or np.ma.is_masked(y):
        raise ValueError("Masked EPyGrAM native FA axes are not qualified")
    shift = (0., 0.)
    if regular:
        mapping = {"grid_mapping_name": "latitude_longitude"}
    else:
        radius = options["earth_radius_m"]
        if geometry.geoid != {"a": radius, "b": radius}:
            raise ValueError("EPyGrAM geoid contradicts explicit input.fa.earth_radius_m")
        projection = geometry.projection
        if geometry.secant_projection or projection["rotation"].get("degrees") != 0:
            raise ValueError("Only unrotated spherical tangent Lambert FA is qualified")
        # No public CRS accessor in 2.1.0. The version-matched _proj owns the
        # projection, including its CI-centred false origin; do not rebuild from FA.
        library_crs = geometry._proj.crs
        cf = library_crs.to_cf()
        parallels = np.atleast_1d(cf["standard_parallel"])
        latitude = projection["reference_lat"].get("degrees")
        if not np.equal(parallels, parallels[0]).all():
            raise ValueError("EPyGrAM CRS does not describe the qualified tangent cone")
        mapping = {"grid_mapping_name": cf["grid_mapping_name"],
                   "standard_parallel": float(latitude),
                   "latitude_of_projection_origin": float(latitude),
                   "longitude_of_central_meridian": float(cf["longitude_of_central_meridian"]),
                   "earth_radius": float(radius)}
        canonical = CRS.from_cf(mapping)
        shift = Transformer.from_crs(library_crs, canonical, always_xy=True).transform(0., 0.)
        x, y = np.asarray(x) + shift[0], np.asarray(y) + shift[1]
    if not (np.isfinite(x).all() and np.isfinite(y).all() and np.isfinite(shift).all()):
        raise ValueError("Nonfinite EPyGrAM native FA axes")
    x0, x1, y0, y1 = zones["CI"]
    lon, lat = geometry.ij2ll(np.array([x0, x1 - 1]), np.array([y0, y1 - 1]))
    if np.ma.is_masked(lon) or np.ma.is_masked(lat):
        raise ValueError("Masked EPyGrAM FA geography is not qualified")
    difference = np.array([lon[0], lat[0], lon[1], lat[1]]) - np.rad2deg(p[12:16])
    difference[[0, 2]] = (difference[[0, 2]] + 180) % 360 - 180
    # Same original-header precision bound as the independently checked baseline.
    if not np.isfinite(difference).all() or np.max(np.abs(difference)) > 2.e-5:
        raise ValueError("EPyGrAM geometry/declared Earth model contradicts encoded CI corners")
    return {"schema_version": 1, "origin": "EPyGrAM-2.1.0 geometry/CRS/native zones",
            "native_shape": [ny, nx], "zones": zones,
            "x": np.asarray(x).tolist(), "y": np.asarray(y).tolist(), "crs": mapping,
            "axis_origin_translation": list(shift),
            "axis_origin_policy": "library CI centre translated to existing CF origin; no fitting",
            "earth_model": {"radius_m": options.get("earth_radius_m"),
                            "origin": ("explicit input.fa.earth_radius_m"
                                       if options.get("earth_radius_m") is not None else
                                       "unresolved; angular grid only, no library geoid adopted")},
            "corner_check": "original encoded CI corners; 2e-5 degree header-precision bound"}


def field_metadata(resource, name):
    # The selected raw encoding guard already ran. Avoid the extra field_type
    # inquiry and broad Misc dispatch; this accessor fails closed at every inquiry.
    field = resource._readH2DField(name, getdata=False)
    if getattr(field, "structure", None) != "H2D" or field.spectral:
        raise ValueError(f"{name}: only decoded gridpoint H2D records are admitted")
    if field.validity.cumulativeduration() is not None:
        raise ValueError(f"{name}: EPyGrAM reports an interval; selection is instantaneous only")
    geometry = field.geometry
    if (geometry.position_on_horizontal_grid != "center"
            or geometry.dimensions != resource.geometry.dimensions):
        raise ValueError(f"{name}: EPyGrAM sampling/storage contradicts the native FA contract")
    vertical = geometry.vcoordinate
    levels = np.asarray(vertical.levels)
    if levels.shape != (1,) or not np.isfinite(levels).all():
        raise ValueError(f"{name}: one finite native level per selected record is required")
    if vertical.typeoffirstfixedsurface == 119:
        if vertical.grid != resource.geometry.vcoordinate.grid:
            raise ValueError(f"{name}: field hybrid grid contradicts the library resource")
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
