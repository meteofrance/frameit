"""Lossless NetCDF and metadata-preserving regular-grid GRIB subsetting.

The operations here do not know about test cases or a fixture layout. Native
dependencies are imported only when their respective operation is requested.
GRIB repacking preserves the source packing method, not bitwise encoding.
"""

from __future__ import annotations

import itertools
import math
import re
from pathlib import Path


def _check_crop(crop, shape):
    x0, x1, y0, y1 = (int(v) for v in crop)
    ny, nx = shape
    if not (0 <= x0 < x1 <= nx and 0 <= y0 < y1 <= ny):
        raise ValueError(f"Crop {crop} is outside source shape {shape}")
    return x0, x1, y0, y1


def _grib_matrix(values, nx, ny, consecutive):
    return values.reshape(nx, ny).T if consecutive else values.reshape(ny, nx)


def validate_grib_subset(path, shape, *, message_count=None):
    """Decode every serialized message and reject stale geometry/payload counts."""
    import eccodes as ec

    ny, nx = shape
    count = 0
    with Path(path).open("rb") as stream:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            count += 1
            try:
                actual_shape = (ec.codes_get_long(handle, "Nj"), ec.codes_get_long(handle, "Ni"))
                point_count = ec.codes_get_long(handle, "numberOfDataPoints")
                values_count = len(ec.codes_get_values(handle))
                if actual_shape != shape or point_count != nx * ny or values_count != nx * ny:
                    raise ValueError(
                        f"{path}: GRIB message {count}: shape={actual_shape}, "
                        f"numberOfDataPoints={point_count}, decoded values={values_count}; "
                        f"expected shape={shape}, points={nx * ny}"
                    )
            finally:
                ec.codes_release(handle)
    if not count or (message_count is not None and count != message_count):
        raise ValueError(f"{path}: GRIB message count={count}, expected={message_count}")
    return count


def crop_grib(source, target, crop, *, expected_shape=None, reference_center=None):
    """Crop all messages of one regular_ll file, preserving scan ordering."""
    import eccodes as ec
    import numpy as np

    count = 0
    times = set()
    levels = {}
    common_geometry = None
    with Path(source).open("rb") as incoming, Path(target).open("wb") as outgoing:
        while (handle := ec.codes_grib_new_from_file(incoming)) is not None:
            count += 1
            try:
                if ec.codes_get(handle, "gridType") != "regular_ll":
                    raise ValueError(f"{source}: unsupported GRIB gridType")
                if ec.codes_get_long(handle, "alternativeRowScanning"):
                    raise ValueError(f"{source}: alternating GRIB row scanning is unsupported")
                if ec.codes_get_long(handle, "bitmapPresent"):
                    raise ValueError(f"{source}: GRIB bitmaps are unsupported")
                nx, ny = ec.codes_get_long(handle, "Ni"), ec.codes_get_long(handle, "Nj")
                shape = (ny, nx)
                if expected_shape is not None and shape != tuple(expected_shape):
                    raise ValueError(f"{source}: source shape={shape}, expected={expected_shape}")
                x0, x1, y0, y1 = _check_crop(crop, shape)
                geometry_keys = (
                    "scanningMode",
                    "latitudeOfFirstGridPointInDegrees",
                    "longitudeOfFirstGridPointInDegrees",
                    "latitudeOfLastGridPointInDegrees",
                    "longitudeOfLastGridPointInDegrees",
                    "iDirectionIncrementInDegrees",
                    "jDirectionIncrementInDegrees",
                )
                geometry = (nx, ny) + tuple(ec.codes_get(handle, k) for k in geometry_keys)
                if common_geometry is None:
                    common_geometry = geometry
                    if reference_center is not None:
                        latitude, longitude, expected_x, expected_y = reference_center
                        consecutive = ec.codes_get_long(handle, "jPointsAreConsecutive")
                        lats = _grib_matrix(
                            ec.codes_get_array(handle, "latitudes"), nx, ny, consecutive
                        )
                        lons = _grib_matrix(
                            ec.codes_get_array(handle, "longitudes"), nx, ny, consecutive
                        )
                        distance = (lats - latitude) ** 2 + (
                            ((lons - longitude + 180) % 360) - 180
                        ) ** 2
                        cy, cx = np.unravel_index(np.nanargmin(distance), distance.shape)
                        if (cx, cy) != (expected_x, expected_y):
                            raise ValueError(
                                f"Source reference centre maps to {(cx, cy)}, "
                                f"expected {(expected_x, expected_y)}"
                            )
                elif geometry != common_geometry:
                    raise ValueError(f"{source}: GRIB grids differ between messages")
                consecutive = ec.codes_get_long(handle, "jPointsAreConsecutive")
                values = ec.codes_get_values(handle)
                if values.size != nx * ny:
                    raise ValueError(f"{source}: message {count} has inconsistent payload")
                field = _grib_matrix(values, nx, ny, consecutive)[y0:y1, x0:x1]
                lat0 = ec.codes_get_double(handle, "latitudeOfFirstGridPointInDegrees")
                lon0 = ec.codes_get_double(handle, "longitudeOfFirstGridPointInDegrees")
                dx = ec.codes_get_double(handle, "iDirectionIncrementInDegrees")
                dy = ec.codes_get_double(handle, "jDirectionIncrementInDegrees")
                dx *= -1 if ec.codes_get_long(handle, "iScansNegatively") else 1
                dy *= 1 if ec.codes_get_long(handle, "jScansPositively") else -1
                for key, value in {
                    "Ni": x1 - x0,
                    "Nj": y1 - y0,
                    "latitudeOfFirstGridPointInDegrees": lat0 + y0 * dy,
                    "longitudeOfFirstGridPointInDegrees": (lon0 + x0 * dx) % 360,
                    "latitudeOfLastGridPointInDegrees": lat0 + (y1 - 1) * dy,
                    "longitudeOfLastGridPointInDegrees": (lon0 + (x1 - 1) * dx) % 360,
                }.items():
                    ec.codes_set(handle, key, value)
                # GRIB2 stores this key independently of Ni/Nj. GRIB1 derives it.
                if ec.codes_get_long(handle, "edition") == 2:
                    ec.codes_set_long(handle, "numberOfDataPoints", field.size)
                payload = field.T.ravel() if consecutive else field.ravel()
                ec.codes_set_values(handle, np.ascontiguousarray(payload))
                ec.codes_write(handle, outgoing)
                date = ec.codes_get_long(handle, "validityDate")
                time = ec.codes_get_long(handle, "validityTime")
                times.add(
                    f"{date:08d}"[:4]
                    + "-"
                    + f"{date:08d}"[4:6]
                    + "-"
                    + f"{date:08d}"[6:]
                    + f"T{time // 100:02d}:{time % 100:02d}:00"
                )
                # Satellite products need not have a vertical surface descriptor.
                if ec.codes_is_defined(handle, "typeOfLevel") and ec.codes_is_defined(
                    handle, "level"
                ):
                    group = str(ec.codes_get(handle, "typeOfLevel"))
                    levels.setdefault(group, set()).add(float(ec.codes_get(handle, "level")))
            except Exception as exc:
                raise ValueError(f"{source}: GRIB message {count}: {exc}") from exc
            finally:
                ec.codes_release(handle)
    output_shape = (crop[3] - crop[2], crop[1] - crop[0])
    validate_grib_subset(target, output_shape, message_count=count)
    return {
        "message_count": count,
        "times": sorted(times),
        "levels": {key: sorted(value) for key, value in sorted(levels.items())},
    }


def coordinate_dependencies(dataset, required):
    """Resolve dimension coordinates and recursive CF variable references."""
    keep = set(required)
    absent = keep.difference(dataset.variables)
    if absent:
        raise ValueError(f"Missing required NetCDF variables: {sorted(absent)}")
    pending = list(keep)
    while pending:
        name = pending.pop()
        var = dataset.variables[name]
        references = {d for d in var.dimensions if d in dataset.variables}
        for attr in (
            "coordinates",
            "ancillary_variables",
            "grid_mapping",
            "bounds",
            "climatology",
            "cell_measures",
            "formula_terms",
        ):
            if attr in var.ncattrs():
                text = str(var.getncattr(attr))
                if attr in ("cell_measures", "formula_terms"):
                    references.update(re.findall(r"\w+\s*:\s*([^\s]+)", text))
                else:
                    references.update(text.split())
        missing = references.difference(dataset.variables)
        if missing:
            raise ValueError(f"{name}: missing CF dependencies {sorted(missing)}")
        additions = references.difference(keep)
        keep.update(additions)
        pending.extend(sorted(additions))
    return sorted(keep)


def _slabs(shape, itemsize, limit):
    """N-dimensional tiles whose dense payload never exceeds the byte budget."""
    if not shape:
        yield ()
        return
    chunks = list(shape)
    while math.prod(chunks) * itemsize > limit:
        axis = max(range(len(chunks)), key=lambda i: chunks[i])
        chunks[axis] = max(1, (chunks[axis] + 1) // 2)
        if all(v == 1 for v in chunks) and itemsize > limit:
            raise ValueError("Slab limit is smaller than a single element")
    for starts in itertools.product(
        *(range(0, n, step) for n, step in zip(shape, chunks, strict=True))
    ):
        yield tuple(
            slice(start, min(start + step, n))
            for start, step, n in zip(starts, chunks, shape, strict=True)
        )


def crop_netcdf(
    source,
    target,
    crop,
    *,
    expected_dimensions,
    required_variables,
    x_dimensions=("ni", "ni_u", "ni_v"),
    y_dimensions=("nj", "nj_u", "nj_v"),
    optional_variables=(),
    slab_bytes=32 * 1024 * 1024,
):
    """Copy raw packed data, attributes and CF dependencies using bounded tiles."""
    import numpy as np
    from netCDF4 import Dataset

    with Dataset(source) as incoming:
        if incoming.groups:
            raise ValueError(f"{source}: NetCDF groups are unsupported by the subset operation")
        for name, expected in expected_dimensions.items():
            if name not in incoming.dimensions or len(incoming.dimensions[name]) != expected:
                actual = len(incoming.dimensions[name]) if name in incoming.dimensions else None
                raise ValueError(f"{source}: dimension {name}={actual}, expected={expected}")
        x0, x1, y0, y1 = _check_crop(
            crop, (len(incoming.dimensions["nj"]), len(incoming.dimensions["ni"]))
        )
        for name in x_dimensions:
            if name in incoming.dimensions and len(incoming.dimensions[name]) != len(
                incoming.dimensions["ni"]
            ):
                raise ValueError(f"{source}: unsupported staggered dimension {name}")
        for name in y_dimensions:
            if name in incoming.dimensions and len(incoming.dimensions[name]) != len(
                incoming.dimensions["nj"]
            ):
                raise ValueError(f"{source}: unsupported staggered dimension {name}")
        keep = coordinate_dependencies(
            incoming,
            set(required_variables) | set(optional_variables).intersection(incoming.variables),
        )
        dimensions = {d for name in keep for d in incoming.variables[name].dimensions}
        with Dataset(target, "w", format="NETCDF4") as outgoing:
            outgoing.setncatts(
                {a: incoming.getncattr(a) for a in incoming.ncattrs() if a != "_NCProperties"}
            )
            for name in sorted(dimensions):
                original = incoming.dimensions[name]
                size = (
                    x1 - x0
                    if name in x_dimensions
                    else y1 - y0
                    if name in y_dimensions
                    else len(original)
                )
                outgoing.createDimension(name, None if original.isunlimited() else size)
            for name in keep:
                vin = incoming.variables[name]
                if vin.dtype.kind not in "biufcSU":
                    raise ValueError(f"{source}: unsupported NetCDF dtype for {name}: {vin.dtype}")
                attrs = {a: vin.getncattr(a) for a in vin.ncattrs()}
                kwargs = {"zlib": True, "complevel": 4} if vin.dimensions else {}
                if "_FillValue" in attrs:
                    kwargs["fill_value"] = attrs.pop("_FillValue")
                vout = outgoing.createVariable(name, vin.datatype, vin.dimensions, **kwargs)
                vout.setncatts(attrs)
                vin.set_auto_maskandscale(False)
                vout.set_auto_maskandscale(False)
                vin.set_auto_chartostring(False)
                vout.set_auto_chartostring(False)
                shape = tuple(
                    x1 - x0
                    if d in x_dimensions
                    else y1 - y0
                    if d in y_dimensions
                    else len(incoming.dimensions[d])
                    for d in vin.dimensions
                )
                origins = tuple(
                    x0 if d in x_dimensions else y0 if d in y_dimensions else 0
                    for d in vin.dimensions
                )
                for output_slice in _slabs(shape, max(1, vin.dtype.itemsize), slab_bytes):
                    source_slice = tuple(
                        slice(s.start + origin, s.stop + origin)
                        for s, origin in zip(output_slice, origins, strict=True)
                    )
                    values = vin[source_slice] if shape else vin[...]
                    if shape:
                        vout[output_slice] = values
                    else:
                        vout.assignValue(values)
            outgoing.sync()
        # Read back raw values and compare to the same source tiles, not decoded
        # scaled floats. This catches a second accidental scale/offset application.
        with Dataset(target) as output_check:
            for name in keep:
                vin, vout = incoming.variables[name], output_check.variables[name]
                vin.set_auto_maskandscale(False)
                vout.set_auto_maskandscale(False)
                vin.set_auto_chartostring(False)
                vout.set_auto_chartostring(False)
                if vin.dtype != vout.dtype or vin.ncattrs() != vout.ncattrs():
                    # Attribute order is not semantic; compare names as sets below.
                    if vin.dtype != vout.dtype or set(vin.ncattrs()) != set(vout.ncattrs()):
                        raise ValueError(f"{target}: dtype/attributes changed for {name}")
                for attr in vin.ncattrs():
                    np.testing.assert_equal(vin.getncattr(attr), vout.getncattr(attr))
                origins = tuple(
                    x0 if d in x_dimensions else y0 if d in y_dimensions else 0
                    for d in vin.dimensions
                )
                for output_slice in _slabs(vout.shape, max(1, vin.dtype.itemsize), slab_bytes):
                    source_slice = tuple(
                        slice(s.start + origin, s.stop + origin)
                        for s, origin in zip(output_slice, origins, strict=True)
                    )
                    np.testing.assert_array_equal(
                        vout[output_slice] if vout.shape else vout[...],
                        vin[source_slice] if vin.shape else vin[...],
                    )
    return {"variables": keep}
