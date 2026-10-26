"""Compact analytical FA fixtures, written only in an isolated test process.

This is test infrastructure, not a supported FA product writer. Values are
known physical scalars on an asymmetric regular-lon/lat grid. No spectral
transformation, pressure diagnosis, or producer-specific surface mapping occurs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import numpy as np


def write_fixture(path, *, hours=0, nx=9, ny=7, offset=0., profile="arome_history", packing=0,
                  state_hours=None, source_version=8, source_bug=1, program="AROME",
                  extra_metadata=False, projection_latitude=None, surface_fields=None,
                  surface_pack=0):
    from falfilfa4py import FA, LFI

    if path.exists():
        raise FileExistsError(path)
    sizes = FA.get_facst()
    k = np.zeros(sizes[0], dtype="int64")
    z = np.zeros(sizes[1], dtype="int64")
    p = np.zeros(18, dtype="float64")
    k[2:6] = 1, nx, 1, ny
    p[0:2] = -1, -9
    p[4:8] = np.deg2rad([60., -20., .01064, .01])
    p[8:10] = p[6] * (nx - 1), p[7] * (ny - 1)
    p[12:16] = [p[4] - (nx - 1) * p[6] / 2, p[5] - (ny - 1) * p[7] / 2,
                 p[4] + (nx - 1) * p[6] / 2, p[5] + (ny - 1) * p[7] / 2]
    if projection_latitude is not None:
        # Independent spherical equations, not FrameIt's pyproj geometry builder.
        phi0, lam0 = np.deg2rad([projection_latitude, 50.])
        n = np.sin(phi0)
        f = np.cos(phi0) * np.tan(np.pi / 4 + phi0 / 2)**n / n
        rho0 = 6371229. * f / np.tan(np.pi / 4 + phi0 / 2)**n
        xx = np.array([-1., 1.]) * (nx - 1) * 500.
        yy = np.array([-1., 1.]) * (ny - 1) * 500.
        rho = np.sign(n) * np.hypot(xx, rho0 - yy)
        theta = np.arctan2(np.sign(n) * xx, np.sign(n) * (rho0 - yy))
        corners_lon = lam0 + theta / n
        corners_lat = 2 * np.arctan((6371229. * f / rho)**(1 / n)) - np.pi / 2
        p[1] = abs(n)
        p[2:6] = lam0, phi0, lam0, phi0
        p[6:10] = 1000., 1000., nx * 1000., ny * 1000.
        p[12:16] = corners_lon[0], corners_lat[0], corners_lon[1], corners_lat[1]
        k[1] = 1
    header = uuid4().hex[:16]
    FA.wfacade(header, -11 if projection_latitude is None else -5, 0., 0., 0., 0.,
               11 if projection_latitude is None else 3, ny, nx,
               len(k), k, len(z), z, len(p), p, 1, 101325.,
               np.array([0., 0.]), np.array([0., 1.]), False)
    unit = FA.wfaitou(str(path), "NEW", header)
    try:
        FA.wfautif(unit, "ALD")
        date = np.array([2026, 1, 1, 0, 0, 1, hours, 0, 10, 0, 0, 1,
                         0, 0, hours * 3600, 0, 0, 0, 0, 0, 0, 0], dtype="int64")
        FA.wfandax(unit, date)
        FA.wfagote(unit, packing, 24, 24, 0, 0, 0)
        field = "CLSTEMPERATURE"
        y, x = np.indices((ny, nx))
        values = (280. + offset + 10 * y + x).astype("float64")
        fields = [{"name": field, "values": values, "mask": "FULL"}]
        if profile == "surfex_history":
            field = "SFX.T2M"
            fields = [{"name": "T2M", "values": values, "mask": "FULL"}]
            if surface_fields is not None:
                fields = surface_fields

            def words(name, values):
                values = np.asarray(values, dtype="int64")
                LFI.wlfiecr(unit, "SFX." + name, values.size, values)

            def text(name, value, width):
                words(name, [ord(c) for c in value.ljust(width)])

            text("PROGRAM", program, 40)
            text("GRID_TYPE", "LONLAT", 40)
            for name, value in (("VERSION", source_version), ("BUG", source_bug),
                                ("PACK", surface_pack),
                                ("MASDEV", 47), ("BUGFIX", 0),
                                ("DIM_FULL", nx * ny), ("IMAX", nx), ("JMAX", ny),
                                ("_FBUF_SIZE", len(fields))):
                words(name, [value])
            for column, width, entries in (
                ("NAME", 32, [f["name"] for f in fields]),
                ("TYPE", 2, [f.get("type", "X1") for f in fields]),
                ("MASK", 16, [f["mask"] for f in fields]),
            ):
                text("_FBUF_" + column, "".join(value.ljust(width) for value in entries),
                     len(fields) * width)
            words("_FBUF_DIM1", [nx * ny] * len(fields))
            words("_FBUF_DIM2", [-1] * len(fields))
            current = np.array([2026, 1, 1, 0], dtype="int64")
            current.view(np.float64)[3] = 3600. * (hours if state_hours is None else state_hours)
            words("DTCUR", current)
            if extra_metadata:
                words("L1D", [0])
                words("L2D", [1])
                words("LAT0", np.array([-20.25], dtype="float64").view("int64"))
        for item in fields:
            field = ("SFX." + item["name"] if profile == "surfex_history" else item["name"])
            values = np.asarray(item["values"], dtype="float64")
            if values.shape != (ny, nx):
                raise ValueError("Fixture field must match the declared native grid")
            undefined = bool(np.any(~np.isfinite(values)))
            # Raw packing-0 does not encode the undefined flag/sentinel. Preserve
            # IEEE NaNs there, rather than writing an unflagged physical 1e20.
            encoded = values if packing == 0 else np.where(np.isfinite(values), values, 1.e20)
            FA.wfaieno(unit, field[:4], 0, field[4:], encoded.size, encoded.ravel(),
                       False, undefined and packing != 0, 1.e20)
    finally:
        FA.wfairme(unit, "KEEP")


def main():
    request = json.load(sys.stdin)
    for item in request:
        write_fixture(Path(item.pop("path")), **item)


if __name__ == "__main__":
    main()
