# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Window an already-bound NetCDF payload before turning it into Dask blocks."""

import xarray as xr


def contiguous_positions(positions):
    """Keep order and dimensionality; never widen a sparse selection."""
    if len(positions) and positions[0] >= 0 and all(
            b == a + 1 for a, b in zip(positions, positions[1:])):
        return slice(int(positions[0]), int(positions[-1]) + 1)
    return positions


class RegionalReads:
    """Attempt-local, lazy views; keys distinguish product selections from dependencies."""

    def __init__(self):
        self.samples = {}
        self.preparations = {}

    def remember(self, role, name, record, variable):
        key = role, record["grid_id"], name, record["time"]
        if record.get("native_axes") or key in self.samples:
            self.samples[key] = None
            return
        vertical = record["vertical"]
        self.samples[key] = variable, vertical and (
            vertical["dimension"], vertical["source_native_indices"])

    def raw(self, key, bounds, *, levels=None):
        sample = self.samples.get(key)
        if sample is None:
            return None
        variable, vertical = sample
        if not bounds.keys() <= variable.sizes.keys():
            return None
        indexers = dict(bounds)
        if levels is not None and vertical:
            dim, native = vertical
            if not set(levels) <= set(native):
                return None
            indexers[dim] = contiguous_positions([native.index(i) for i in levels])
        # isel must precede chunk AND transpose: both can materialize a backend view.
        return variable.isel(indexers).chunk({})

    def window(self, key, bounds, like, *, rename=None, levels=None):
        prepare = self.preparations.get(key)
        variable = prepare(bounds, reads=self) if prepare else self.raw(key, bounds, levels=levels)
        if variable is None:
            return None
        part = xr.DataArray(variable).rename(rename or {})
        if "time" in like.dims and "time" not in part.dims:
            part = part.expand_dims(time=1)
        if part.sizes != like.sizes or part.dtype != like.dtype:
            return None
        return like.copy(data=part.transpose(*like.dims).data)

    def polar_reader(self, job, stamp):
        """Translate finite-footprint and stencil offsets into original file indices."""
        name = job["inputs"]["field"]
        record, = job["input_binding"]["dependencies"][name]["records"]
        key = "polar", job["grid_id"], name, stamp
        if not self.preparations.get(key):
            if job["preparation"] != "native_samples" or job["pair"] or "units" in job:
                return None
            key = "native", record["grid_id"], name, stamp
        dims = job["polar_geometry"]["horizontal_dimensions"]
        vertical = record["vertical"]

        def read(field, footprint, y, x):
            bounds = {}
            for axis, selection in (("y", y), ("x", x)):
                start = footprint[f"{axis}_slice"][0]
                bounds[dims[axis]] = slice(start + selection.start, start + selection.stop)
            result = self.window(key, bounds, field, rename={d: f"{a}_box" for a, d in dims.items()},
                                 levels=vertical and vertical["source_native_indices"])
            return field if result is None else result

        return read

    def box(self, grid, value, indices, template):
        """Read each time's clipped rectangle, then gather any repeated edge indices."""
        if value.chunks is None or not value.sizes.get("time") or "time" not in template.dims:
            return template
        pieces = []
        for i, stamp in enumerate(value.time.values):
            key = "model_grid", grid, value.name, stamp
            if self.samples.get(key) is None and not self.preparations.get(key):
                return template
            offsets = {d: idx.isel(time=slice(i, i + 1)) for d, idx in indices.items()}
            bounds = {d: slice(int(idx.min()), int(idx.max()) + 1) for d, idx in offsets.items()}
            like = value.isel(time=slice(i, i + 1), **bounds)
            block = self.window(key, bounds, like)
            if block is None:
                return template
            part = block.isel({d: idx - bounds[d].start for d, idx in offsets.items()})
            pieces.append(part.variable.transpose(*template.dims))
        data = xr.Variable.concat(pieces, dim="time").transpose(*template.dims)
        return template.copy(data=data.data)
