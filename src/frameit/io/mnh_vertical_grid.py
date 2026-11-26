"""Resolve Meso-NH model-top metadata without reading atmospheric fields."""

import numpy as np
import xarray as xr

from frameit.utils.units import convert_units


ZTOP_ATTRS = {
    "units": "m", "long_name": "ZTOP", "standard_name": "altitude_at_top_of_atmosphere_model",
    "comment": "Height of top level", "grid": 4,
}


def _epsilon(dtype):
    return float(np.finfo(dtype).eps) if dtype.kind == "f" else np.finfo(float).eps


def equal_metres(left, right, epsilon=np.finfo(float).eps):
    """Allow only the precision of stored values and a few arithmetic operations."""
    return np.isclose(left, right, rtol=4 * epsilon, atol=0.)


def _length(value):
    if value.dtype.kind not in "fiu" or value.attrs.get("positive", "up") != "up":
        raise ValueError(f"{value.name} is not a numeric positive-up length")
    native = np.asarray(value)
    if (not np.isfinite(native).all()
            or any(np.isin(native, value.attrs[key]).any()
                   for key in ("_FillValue", "missing_value") if key in value.attrs)
            or ("valid_min" in value.attrs and np.any(native < value.attrs["valid_min"]))
            or ("valid_max" in value.attrs and np.any(native > value.attrs["valid_max"]))
            or ("valid_range" in value.attrs and (
                np.size(value.attrs["valid_range"]) != 2
                or np.any(native < value.attrs["valid_range"][0])
                or np.any(native > value.attrs["valid_range"][1])))):
        raise ValueError(f"{value.name} has missing or invalid lengths")
    metres = np.asarray(convert_units(value.astype("float64"), "distance"))
    if not np.isfinite(metres).all():
        raise ValueError(f"{value.name} does not convert to finite metres")
    return metres


def _count(ds, keys, expected):
    for name in keys:
        declared = [ds.attrs[name]] if name in ds.attrs else []
        if name in ds:
            if ds[name].ndim:
                raise ValueError(f"{name} must be a scalar")
            declared.append(ds[name].item())
        if any(np.asarray(value).ndim or np.asarray(value).dtype.kind not in "iu"
               or value != expected for value in declared):
            raise ValueError(f"{name} contradicts the complete vertical grid")


def _mass_labels(interfaces):
    return np.r_[.5 * interfaces[:-1] + .5 * interfaces[1:],
                 1.5 * interfaces[-1] - .5 * interfaces[-2]]


def _complete_interfaces(ds):
    """Check the documented one-external-level writer, not merely the last label."""
    mass, flux = "level", "level_w"
    n = ds.sizes.get(flux, 0)
    if n < 3 or ds.sizes.get(mass) != n:
        raise ValueError("Complete Meso-NH mass and interface axes are not available")
    _count(ds, ("KMAX", "NKMAX"), n - 2)
    _count(ds, ("JPVEXT",), 1)
    for name, shift, edge, quantity in (
        (mass, 0., n - 1, "altitude"), (flux, -.5, n, "altitude_at_w_location"),
    ):
        if name not in ds.coords or ds[name].dims != (name,):
            raise ValueError(f"{name} is not a native one-dimensional coordinate")
        attrs = ds[name].attrs
        if (attrs.get("axis") != "Z" or attrs.get("positive") != "up"
                or attrs.get("computed_standard_name") != quantity
                or attrs.get("c_grid_axis_shift") != shift
                or attrs.get("c_grid_dynamic_range") != f"2:{edge}"):
            raise ValueError(f"{name} does not establish the complete native physical range")
        index = f"{name}_source_native_index"
        if index in ds and (ds[index].dims != (name,) or
                            not np.array_equal(ds[index], np.arange(n))):
            raise ValueError(f"{name} has non-native or incomplete indices")
    m, w = _length(ds[mass]), _length(ds[flux])
    epsilon = max(_epsilon(ds[mass].dtype), _epsilon(ds[flux].dtype))
    if (not np.all(np.diff(w) > 0.) or not np.all(np.diff(m) > 0.)
            or w[1] != 0. or not equal_metres(w[0], -w[2], epsilon)
            or not equal_metres(m, _mass_labels(w), epsilon).all()):
        raise ValueError("Meso-NH levels do not match the native staggered geometry")
    if "ZHAT" in ds:
        zhat = ds.ZHAT
        if (zhat.dims != (flux,) or not equal_metres(
                _length(zhat), w, max(epsilon, _epsilon(zhat.dtype))).all()):
            raise ValueError("ZHAT contradicts the complete level_w axis")
    # The inclusive upper interface range is Fortran 1-based.
    upper_index = int(ds[flux].attrs["c_grid_dynamic_range"].split(":")[1]) - 1
    return float(w[upper_index]), {
        "coordinate": flux, "physical_range": ds[flux].attrs["c_grid_dynamic_range"],
        "upper_index": upper_index, "length_epsilon": _epsilon(ds[flux].dtype),
    }


def _parameter(attrs, name):
    value = np.asarray(attrs.get(name))
    if value.ndim or value.dtype.kind not in "fiu" or not np.isfinite(value):
        raise ValueError(f"Missing or invalid original grid setting {name}")
    return value.item()


def _replay_interfaces(attrs, count, dtype):
    """Replay the inspected READ_VER_GRID arithmetic in its declared real kind."""
    kind = attrs["YZGRID_TYPE"]
    if kind == "MANUAL":
        physical = np.asarray(attrs.get("ZHAT"))
        if physical.shape != (count + 1,) or physical.dtype.kind not in "fiu":
            raise ValueError("MANUAL requires the full original physical ZHAT list")
        physical = physical.astype(dtype)
        return np.r_[2 * physical[0] - physical[1], physical]
    if kind != "FUNCTN":
        raise ValueError("Original grid type is not a verified FUNCTN or MANUAL recipe")
    ground, cap = (dtype(_parameter(attrs, name)) for name in ("ZDZGRD", "ZDZTOP"))
    if not 0 < ground <= cap:
        raise ValueError("Require 0 < ZDZGRD <= ZDZTOP")
    if abs(cap - ground) < dtype(1e-10):
        return np.arange(-1, count + 1, dtype=dtype) * ground
    threshold, lower, upper = (dtype(_parameter(attrs, name)) for name in (
        "ZZMAX_STRGRD", "ZSTRGRD", "ZSTRTOP"))
    interfaces = np.empty(count + 2, dtype=dtype)
    interfaces[:3] = [-ground, 0., ground]
    for i in range(3, len(interfaces)):
        previous = interfaces[i - 1]
        stretch = lower if previous < threshold - dtype(1e-10) else upper
        interfaces[i] = previous + (previous - interfaces[i - 2]) * (dtype(1) + stretch / dtype(100))
        if interfaces[i] - previous > cap:
            interfaces[i] = previous + cap
    return interfaces


def _matches_stored_axis(ds, name, expected, *, dimension=None):
    if name not in ds:
        return True
    dimension = dimension or name
    if ds[name].dims != (dimension,):
        return False
    stored = _length(ds[name])
    if not stored.size or not np.all(np.diff(stored) > 0):
        return False
    epsilon = max(_epsilon(ds[name].dtype), _epsilon(expected.dtype))
    index = f"{dimension}_source_native_index"
    if index in ds:
        indices = np.asarray(ds[index])
        return (ds[index].dims == (dimension,) and indices.dtype.kind in "iu"
                and np.all((indices >= 0) & (indices < expected.size))
                and equal_metres(stored, expected[indices], epsilon).all())
    if len(stored) == len(expected):
        return equal_metres(stored, expected, epsilon).all()
    positions = np.searchsorted(expected, stored)
    return (len(stored) < len(expected) and (
        equal_metres(stored, expected[np.clip(positions, 0, expected.size - 1)], epsilon)
        | equal_metres(stored, expected[np.clip(positions - 1, 0, expected.size - 1)], epsilon)
    ).all())


def _configured_top(ds):
    from frameit.core.catalogue_diagnostics import _netcdf_identity

    attrs = ds.attrs
    if "YZGRID_TYPE" not in attrs:
        raise ValueError("Original NAM_VER_GRID settings are not stored in the input")
    identity = _netcdf_identity("mesonh", attrs)
    if identity.get("version") != "5.6.2":
        raise ValueError("No verified READ_VER_GRID configuration recipe for the recorded producer")
    count = _parameter(attrs, "NKMAX")
    if not isinstance(count, int) or not 1 <= count <= 10_000:
        raise ValueError("Original NKMAX must be a positive integer within the replay limit")
    _count(ds, ("KMAX",), count)
    _count(ds, ("JPVEXT",), 1)
    if "ZHAT" in ds and "level_w" in ds.coords:
        zhat, flux = ds.ZHAT, ds.level_w
        if zhat.dims != ("level_w",) or flux.dims != zhat.dims or not equal_metres(
                _length(zhat), _length(flux), max(_epsilon(zhat.dtype), _epsilon(flux.dtype))).all():
            raise ValueError("ZHAT contradicts the stored level_w positions")
    precision = attrs.get("MNH_REAL")
    if precision not in (None, 4, 8):
        raise ValueError("Original MNH_REAL must denote 4- or 8-byte real arithmetic")
    values = {}
    for size, dtype in ((4, np.float32), (8, np.float64)):
        if precision not in (None, size):
            continue
        interfaces = _replay_interfaces(attrs, count, dtype)
        if (np.isfinite(interfaces).all() and interfaces[1] == 0.
                and np.all(np.diff(interfaces) > 0.)
                and _matches_stored_axis(ds, "level_w", interfaces)
                and _matches_stored_axis(ds, "ZHAT", interfaces, dimension="level_w")
                and _matches_stored_axis(ds, "level", _mass_labels(interfaces))):
            values[size] = float(interfaces[-1])
    if len(set(values.values())) != 1:
        raise ValueError("Original grid reconstruction disagrees with stored levels or real precision")
    parameters = ("NKMAX", "ZDZGRD", "ZDZTOP", "ZZMAX_STRGRD", "ZSTRGRD", "ZSTRTOP")
    return next(iter(values.values())), {
        "producer_version": identity["version"], "version_evidence": identity["version_evidence"],
        "grid_type": str(attrs["YZGRID_TYPE"]), "real_bytes": list(values),
        "parameters": {key: _parameter(attrs, key) for key in parameters if key in attrs},
        **({"physical_interface_count": count + 1} if attrs["YZGRID_TYPE"] == "MANUAL" else {}),
    }


def _decision(status, method=None, value_m=None, **evidence):
    return dict(status=status, method=method, value_m=value_m, evidence=evidence)


def resolve_ztop(ds: xr.Dataset) -> dict:
    """Resolve only instrumented native layouts or complete original grid recipes."""
    native = ds.get("ZTOP")
    top = None
    if native is not None:
        try:
            if native.ndim or (top := _length(native).item()) <= 0.:
                raise ValueError("Native ZTOP must be a positive scalar altitude")
        except (ValueError, TypeError) as exc:
            return _decision("conflicting", reason=str(exc))
    try:
        interface, evidence = _complete_interfaces(ds)
    except (ValueError, TypeError) as exc:
        unproven = str(exc)
    else:
        if top is None:
            return _decision("reconstructed", "level_w", interface, **evidence)
        if not equal_metres(top, interface,
                            max(evidence["length_epsilon"], _epsilon(native.dtype))):
            return _decision("conflicting", native_value_m=top, level_w_value_m=interface,
                             reason="Native ZTOP disagrees with the proven physical upper interface")
    if top is not None:
        return _decision("native", "native", top, variable="ZTOP",
                         units=str(native.attrs["units"]), native_value=native.item(),
                         length_epsilon=_epsilon(native.dtype))
    try:
        value, evidence = _configured_top(ds)
    except (ValueError, TypeError, OverflowError) as exc:
        return _decision("missing", level_w_reason=unproven, configuration_reason=str(exc))
    return _decision("reconstructed", "nam_ver_grid", value, **evidence)


def assign_resolved_ztop(ds: xr.Dataset, decision: dict) -> xr.Dataset:
    """Attach the bound scalar only in memory, never modifying native variables."""
    if "ZTOP" in ds or decision["status"] != "reconstructed":
        return ds
    attrs = decision.get("attributes", ZTOP_ATTRS)
    value = decision.get("native_value", decision["value_m"])
    return ds.assign(ZTOP=xr.DataArray(value, attrs=attrs))
