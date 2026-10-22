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
                  state_hours=None):
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
    header = uuid4().hex[:16]
    FA.wfacade(header, -11, 0., 0., 0., 0., 11, ny, nx,
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
        if profile == "surfex_history":
            field = "SFX.T2M"

            def words(name, values):
                values = np.asarray(values, dtype="int64")
                LFI.wlfiecr(unit, "SFX." + name, values.size, values)

            def text(name, value, width):
                words(name, [ord(c) for c in value.ljust(width)])

            text("PROGRAM", "AROME", 40)
            text("GRID_TYPE", "LONLAT", 40)
            for name, value in (("VERSION", 8), ("BUG", 1), ("PACK", 0),
                                ("DIM_FULL", nx * ny), ("IMAX", nx), ("JMAX", ny),
                                ("_FBUF_SIZE", 1)):
                words(name, [value])
            text("_FBUF_NAME", "T2M", 32)
            text("_FBUF_TYPE", "X1", 2)
            text("_FBUF_MASK", "FULL", 16)
            words("_FBUF_DIM1", [nx * ny])
            words("_FBUF_DIM2", [-1])
            current = np.array([2026, 1, 1, 0], dtype="int64")
            current.view(np.float64)[3] = 3600. * (hours if state_hours is None else state_hours)
            words("DTCUR", current)
        y, x = np.indices((ny, nx))
        values = (280. + offset + 10 * y + x).astype("float64")
        FA.wfaieno(unit, field[:4], 0, field[4:], values.size, values.ravel(), False, False, 1.e20)
    finally:
        FA.wfairme(unit, "KEEP")


def main():
    request = json.load(sys.stdin)
    for item in request:
        write_fixture(Path(item.pop("path")), **item)


if __name__ == "__main__":
    main()
