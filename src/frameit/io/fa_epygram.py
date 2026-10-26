"""Optional EPyGrAM FA calls inside the disposable native worker only.

Uses the unmodified EPyGrAM API (Météo-France, CeCILL-C). No EPyGrAM code or
definition tables are vendored. Source files are opened explicitly read-only.
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version

import numpy as np


def initialize(destination, radius):
    try:
        if version("epygram") != "2.1.0":
            raise ValueError("This FA backend requires EPyGrAM 2.1.0")
    except PackageNotFoundError as exc:
        raise ValueError("EPyGrAM backend requested: install FrameIt[fa-epygram] in the "
                         "helper environment; input.fa.python_executable can select it") from exc
    for name, expected in (("falfilfa4py", "1.2.1"), ("ctypesForFortran", "1.3.0")):
        if version(name) != expected:
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


def field_metadata(resource, name, header):
    field = resource.readfield(name, getdata=False)
    if field.structure != "H2D" or field.spectral:
        raise ValueError(f"{name}: only decoded gridpoint H2D records are admitted for P5")
    if field.validity.cumulativeduration() is not None:
        raise ValueError(f"{name}: EPyGrAM reports an interval; P5 selection is instantaneous only")
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
            "position_policy": "cube mass/interface sampling is an explicit user declaration",
            "evidence": "EPyGrAM-2.1.0 FA field definitions and header reader"}


def read_values(resource, name, shape):
    field = resource.readfield(name, getdata=True)
    if field.structure != "H2D" or field.spectral:
        raise ValueError(f"{name}: coefficients/metadata cannot be returned as gridpoint values")
    values = np.ma.asarray(field.getdata(), dtype="float64")
    if values.shape != tuple(shape):
        raise ValueError(f"{name}: EPyGrAM decoded shape contradicts the native grid")
    return np.asarray(values.filled(np.nan)), bool(np.ma.getmaskarray(values).any())
