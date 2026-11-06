"""Declared wind bases shared by input inspection and numerical preparation.

Rotation angle is counterclockwise from east to positive native x. Components
are physical velocities, not map-factor-scaled coordinate rates:
``east = u*cos(a)-v*sin(a); north = u*sin(a)+v*cos(a)``.

``coordinate`` requires an explicitly named angle with units. ``geolocation``
uses local WGS84 geodesic directions of both signed native axes; it rejects
reflected/nonorthogonal grids (absolute cosine tolerance .02) and degenerate
neighbours. This is a local finite-neighbour approximation, not a regridding
or conservation method; large/strongly curved cells require separate review.

Meso-NH's conformal-projection angle is BETA-RPK*wrap(longitude-LON0), in
degrees. Sign verified against the authoritative EPyGrAM sources (2026-10-16):
https://github.com/UMR-CNRM/EPyGrAM/blob/master/src/epygram/formats/netCDFMNH.py
(``_read_geometry`` maps BETA directly to projection rotation), and
https://github.com/UMR-CNRM/EPyGrAM/blob/master/src/epygram/geometries/ProjectedGeometry.py
(``compass_grid`` and ``reproject_wind_on_lonlat``, without map-factor correction).
This implements the mathematical convention, not a claim of validation for all
MNH configurations. Cartesian geometry is excluded. Synthetic verification is
in testing/numerical/test_wind_reference.py; real-data qualification remains open.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr

from frameit.utils.units import convert_units


def wind_pairs(conf: Any, group: str) -> list[dict]:
    """Return explicit definitions for one group, without inspecting other groups."""
    return [dict(pair) for pair in (getattr(conf, "wind_pairs", None) or [])
            if pair["group"] == group]


def declared_pair(conf: Any, group: str, names=None) -> dict | None:
    """Resolve a declaration by ordered (u,v) names, or the unique group pair.

    No match returns None; an ambiguous group raises. This helper never infers a
    scientific frame from variable names or source metadata.
    """
    pairs = wind_pairs(conf, group)
    if names is not None:
        pairs = [p for p in pairs if (p["u"], p["v"]) == tuple(names)]
    if len(pairs) > 1:
        raise ValueError(f"Ambiguous wind pairs in group {group!r}; configure diagnostic aliases")
    return pairs[0] if pairs else None


def validate_frame(frame, context="wind") -> str:
    if frame not in {"earth", "grid"}:
        raise ValueError(
            f"{context}: reference_frame must explicitly be earth or grid, got {frame!r}"
        )
    return frame


def pair_definition(conf: Any, group: str, names) -> dict:
    """Effective declaration, including the explicit scalar compatibility path."""
    pair = declared_pair(conf, group, names)
    if pair is not None:
        validate_frame(pair.get("reference_frame"), f"Wind pair {names}")
        if pair["reference_frame"] == "grid":
            rotation = pair.get("rotation") or {}
            if rotation.get("method") not in {"coordinate", "geolocation", "mesonh_projection"}:
                raise ValueError(f"Grid wind pair {names} requires an explicit rotation method")
            if rotation["method"] == "coordinate" and not rotation.get("coordinate"):
                raise ValueError(
                    f"Grid wind pair {names}: coordinate method requires coordinate name"
                )
        return pair
    # Only lightweight historical numerical calls have a canonical earth API.
    direct = not hasattr(conf, "wind_pairs") and not hasattr(conf, "wind_reference_frame")
    frame = "earth" if direct else getattr(conf, "wind_reference_frame", None)
    if frame is None:
        raise ValueError(f"Wind pair {names} in {group!r} needs a wind_pairs declaration "
                         "or explicit legacy wind_reference_frame")
    validate_frame(frame, f"Wind pair {names}")
    return dict(group=group, u=names[0], v=names[1], reference_frame=frame,
                rotation={"method": "coordinate", "coordinate": "grid_rotation"}
                if frame == "grid" else None,
                declaration="canonical_numerical_api" if direct else "legacy_scalar")


def _metadata_frames(attrs, context):
    frames = []
    if attrs.get("wind_reference_frame") is not None:
        frames.append(validate_frame(attrs["wind_reference_frame"], context))
    for key in ("GRIB_uvRelativeToGrid", "uvRelativeToGrid"):
        if key in attrs:
            flag = attrs[key]
            if flag not in (0, 1, "0", "1"):
                raise ValueError(f"{context}: invalid {key}={flag!r}")
            frames.append("grid" if int(flag) else "earth")
    standard = attrs.get("standard_name")
    if standard in {"eastward_wind", "northward_wind"}:
        frames.append("earth")
    elif standard in {"x_wind", "y_wind", "grid_eastward_wind", "grid_northward_wind"}:
        frames.append("grid")
    return frames


def validate_pair_frame(ds: xr.Dataset, pair: dict) -> str:
    """Header-only source-frame check, also safe on previously prepared fields.

    Preparation is identified per component, never from a dataset-wide marker
    (a dataset may contain both grid- and Earth-relative source pairs). A lone
    prepared component is valid after output selection; raw pairs must be complete.
    """
    source = validate_frame(pair["reference_frame"])
    prepared = []
    present = [name for name in (pair["u"], pair["v"]) if name in ds]
    if len(present) != 2 and (not present or not all(is_prepared(ds[n]) for n in present)):
        missing = next(n for n in (pair["u"], pair["v"]) if n not in ds)
        raise ValueError(
            f"Wind pair {pair['u']}/{pair['v']} requires both components; missing {missing}"
        )
    for name, expected in ((pair["u"], {"eastward_wind", "x_wind", "grid_eastward_wind"}),
                           (pair["v"], {"northward_wind", "y_wind", "grid_northward_wind"})):
        if name not in ds:
            continue
        attrs = ds[name].attrs
        done = is_prepared(ds[name])
        prepared.append(done)
        frames = _metadata_frames(attrs, name)
        if not done:
            frames += _metadata_frames(ds.attrs, "Dataset")
        target = "earth" if done else source
        if any(frame != target for frame in frames):
            raise ValueError(f"Conflicting wind reference metadata on {name}: "
                             f"declared {target}, metadata {frames}")
        if done and attrs.get("source_wind_reference_frame") != source:
            raise ValueError(f"Prepared {name}: source frame conflicts with declaration {source}")
        if done:
            names = f"{pair['u']},{pair['v']}"
            if attrs.get("wind_pair", names) != names:
                raise ValueError(f"Prepared {name}: wind_pair conflicts with declaration {names}")
            if source == "grid":
                rotation = pair.get("rotation") or {}
                method = rotation.get("method")
                recorded = attrs.get("wind_rotation_method", method)
                compatible = {method}
                if method == "coordinate":
                    compatible.add("legacy_grid_rotation_coordinate")
                if recorded not in compatible:
                    raise ValueError(f"Prepared {name}: rotation method conflicts with declaration")
                coordinate = rotation.get("coordinate")
                if method == "coordinate" and attrs.get(
                    "wind_rotation_coordinate", coordinate
                ) != coordinate:
                    raise ValueError(
                        f"Prepared {name}: rotation coordinate conflicts with declaration"
                    )
        if attrs.get("standard_name") in {
            "eastward_wind", "northward_wind", "x_wind", "y_wind",
            "grid_eastward_wind", "grid_northward_wind",
        } and attrs["standard_name"] not in expected:
            raise ValueError(f"{name}: standard_name identifies the wrong wind component")
    if any(prepared) and not all(prepared):
        raise ValueError("Wind pair contains only one prepared component")
    return "earth" if all(prepared) else source


def is_prepared(da: xr.DataArray) -> bool:
    """Recognize portable prepared metadata even if private markers were dropped."""
    return da.attrs.get("frameit_wind_prepared") == "earth" or (
        da.attrs.get("wind_reference_frame") == "earth"
        and da.attrs.get("source_wind_reference_frame") in {"earth", "grid"}
    )


def geolocation_rotation(ds: xr.Dataset, conf: Any) -> xr.DataArray:
    """Direction of positive native x, with signed monotone coordinate changes."""
    from pyproj import Geod

    x = getattr(conf, "name_lon_dim", "ni")
    y = getattr(conf, "name_lat_dim", "nj")
    lon_name = getattr(conf, "name_longitude", "longitude")
    lat_name = getattr(conf, "name_latitude", "latitude")
    if any(name not in ds for name in (x, y, lon_name, lat_name)):
        raise ValueError(
            "geolocation rotation requires labelled native axes and longitude/latitude"
        )
    lon, lat = xr.broadcast(
        convert_units(ds[lon_name], "angle", target="degrees"),
        convert_units(ds[lat_name], "angle", target="degrees"),
    )
    if not {x, y} <= set(lon.dims):
        raise ValueError("geolocation must span both native horizontal axes")
    dims = (*[d for d in lon.dims if d not in {x, y}], y, x)
    lon, lat = (a.transpose(*dims) for a in (lon, lat))
    lv, av = np.asarray(lon, float), np.asarray(lat, float)
    if not np.isfinite(lv).all() or not np.isfinite(av).all() or np.any(np.abs(av) >= 90):
        raise ValueError("geolocation rotation requires finite nonpolar geography")
    geod = Geod(ellps="WGS84")
    angles = []
    for dim, axis in ((x, lv.ndim - 1), (y, lv.ndim - 2)):
        c = ds[dim]
        delta = np.diff(np.asarray(c, float))
        if c.dims != (dim,) or len(delta) < 1 or not np.isfinite(c).all() or not (
            np.all(delta > 0) or np.all(delta < 0)
        ):
            raise ValueError("geolocation rotation requires strictly monotone native coordinates")
        index = np.arange(c.size)
        forward, backward = np.minimum(index + 1, c.size - 1), np.maximum(index - 1, 0)
        af, _, df = geod.inv(lv, av, np.take(lv, forward, axis), np.take(av, forward, axis))
        ab, _, db = geod.inv(lv, av, np.take(lv, backward, axis), np.take(av, backward, axis))
        shape = [1] * lv.ndim
        shape[axis] = c.size
        first, last = (index == 0).reshape(shape), (index == c.size - 1).reshape(shape)
        if np.any((df <= 0) & ~last) or np.any((db <= 0) & ~first):
            raise ValueError("geolocation rotation has degenerate native neighbours")
        ab += 180
        af = np.where(last, ab, af)
        ab = np.where(first, af, ab)
        if delta[0] < 0:
            af, ab = af + 180, ab + 180
        a, b = np.deg2rad(af), np.deg2rad(ab)
        if np.any(np.cos(a - b) < .99):
            raise ValueError("geolocation native axis direction changes too sharply")
        angles.append(np.arctan2(np.sin(a) + np.sin(b), np.cos(a) + np.cos(b)))
    if not np.isfinite(angles).all() or np.any(np.abs(np.cos(angles[0] - angles[1])) > .02):
        raise ValueError("geolocation rotation requires an approximately orthogonal grid")
    if np.any(np.sin(angles[0] - angles[1]) <= 0):
        raise ValueError("geolocation rotation rejects reflected native vector orientation")
    return xr.DataArray(np.pi / 2 - angles[0], dims=dims, coords=lon.coords,
                        attrs={"units": "rad", "rotation_geodesic": "WGS84"})


def mesonh_projection_rotation(ds: xr.Dataset, conf: Any) -> xr.DataArray:
    """EPyGrAM/MNH conformal physical-vector convention; no map scaling."""
    def parameter(name, angle=False):
        if name in ds:
            value = ds[name]
        elif name in ds.attrs:
            value = xr.DataArray(ds.attrs[name])
        else:
            raise ValueError(f"mesonh_projection rotation requires {name} metadata")
        if angle:
            # Official MNH BETA/LON0 metadata contract uses degrees.
            value = convert_units(value, "angle", target="degrees", assumed="degrees")
        if value.size != 1 or not np.isfinite(value).all():
            raise ValueError(f"mesonh_projection {name} must be a finite scalar")
        return float(value.item())

    if ("CARTESIAN" in ds and bool(ds.CARTESIAN.item())) or ds.attrs.get("CARTESIAN", False):
        raise ValueError("mesonh_projection does not support CARTESIAN geometry")
    beta, rpk, lon0 = parameter("BETA", True), parameter("RPK"), parameter("LON0", True)
    if abs(rpk) > 1:
        raise ValueError("mesonh_projection RPK must be in [-1, 1]")
    name = getattr(conf, "name_longitude", "longitude")
    if name not in ds:
        raise ValueError("mesonh_projection rotation requires longitude")
    lon = convert_units(ds[name], "angle", target="degrees")
    if not np.isfinite(lon).all():
        raise ValueError("mesonh_projection longitude must be finite")
    angle = np.deg2rad(beta - rpk * ((lon - lon0 + 180) % 360 - 180))
    angle.attrs = dict(units="rad", rotation_formula="BETA-RPK*wrap(longitude-LON0)",
                       rotation_BETA_degrees=beta, rotation_RPK=rpk, rotation_LON0_degrees=lon0)
    return angle


def rotation_angle(ds: xr.Dataset, conf: Any, pair: dict) -> xr.DataArray:
    """Execute exactly the declared method; never select a fallback."""
    rotation = pair.get("rotation") or {}
    method = rotation.get("method")
    if method == "coordinate":
        name = rotation.get("coordinate")
        if not name or name not in ds:
            raise ValueError(f"coordinate rotation requires named coordinate {name!r}")
        angle = convert_units(ds[name], "angle")
    elif method == "geolocation":
        angle = geolocation_rotation(ds, conf)
    elif method == "mesonh_projection":
        angle = mesonh_projection_rotation(ds, conf)
    else:
        raise ValueError(f"Grid wind requires explicit rotation method, got {method!r}")
    if not np.isfinite(angle).all():
        raise ValueError(f"{method} wind rotation angle must be finite")
    return angle
