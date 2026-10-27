"""Labelled FA grids: EPyGrAM geometry facts and the legacy native baseline.

    FA modern-header PSINLA angular parameters are radians. CI bounds in KNLOPA
    are one-based inclusive. The geographic anchor is at the centre of CI, not
    the centre of CIE. Earth radius is an explicit user declaration, never inferred
    from a filename. See the FA input method note for scope and verification.
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from pyproj import CRS, Transformer

NATIVE_LOOKUP = "fa_source_crs_native_axes_v1"


def _regional_header(header):
    """Validate the evidenced modern header; ignore inactive work-buffer tails."""
    p = np.asarray(header["PSINLA"][:16], dtype=float)
    k = np.asarray(header["KNLOPA"][:8], dtype=float)
    if p.size != 16 or k.size != 8 or not np.isfinite(p).all() or not np.isfinite(k).all():
        raise ValueError("FA requires finite active modern rectangular header entries")
    if p[0] != -1 or header["KTYPTR"] >= 0:
        raise ValueError("FA requires a supported modern rectangular header")
    if (header["PCODIL"] != 0 or any(header.get(key, 0) != 0
                                     for key in ("PSLAPO", "PCLOPO", "PSLOPO"))):
        raise ValueError("Rotated/stretched/academic FA header conventions are not qualified")
    if not np.equal(k, np.floor(k)).all() or np.any(k[6:8] < 0):
        raise ValueError("FA domain indices and I-zone widths must be nonnegative integers")
    for key in ("KNXLON", "KNLATI"):
        if not np.isfinite(header[key]) or int(header[key]) != header[key] or header[key] < 2:
            raise ValueError("FA requires integer rectangular dimensions of at least two points")
    if p[1] < -1 and p[1] != -9:
        raise ValueError("Unsupported FA regular-grid header discriminator")
    return p, k.astype(int)


def geometry_signature(header, options):
    import json

    if "epygram" in header:
        return json.dumps({"subdomain": options["subdomain"], "geometry": header["epygram"]},
                          sort_keys=True, allow_nan=False)
    if options.get("backend") == "epygram":
        raise ValueError("Missing qualified EPyGrAM geometry; inspect with geometry_options")
    p, k = _regional_header(header)
    return json.dumps({"options": {k: options[k] for k in ("subdomain", "earth_radius_m")},
                       "header": {"KTYPTR": header["KTYPTR"], "PCODIL": header["PCODIL"],
                                  "KNXLON": header["KNXLON"], "KNLATI": header["KNLATI"],
                                  "KNLOPA": k.tolist(), "PSINLA": p.tolist()}},
                       sort_keys=True, allow_nan=False)


def admitted_geometry(header, options):
    """Qualification/resource checks only; EPyGrAM owns geometry interpretation.

    Original discriminants and encoded corners are not all exposed by its geometry
    object. Keep these finite admission checks, without reconstructing a projection.
    """
    p, k = _regional_header(header)
    nx, ny = int(header["KNXLON"]), int(header["KNLATI"])
    if nx * ny > options.get("max_points", 20_000_000):
        raise ValueError("Native FA storage grid exceeds input.fa.max_points; "
                         "raise the declared resource budget explicitly if appropriate")
    if options["subdomain"] not in {"CI", "C"}:
        raise ValueError("FA subdomain must be CI or C")
    regular = p[1] == -9
    if regular:
        if options["subdomain"] != "CI":
            raise ValueError("Regular lon/lat FA supports the complete CI grid only")
        if list(k[2:6]) != [1, nx, 1, ny] or p[6] == 0 or p[7] == 0:
            raise ValueError("Regular FA requires complete CI bounds and nonzero angular steps")
        x0, x1, y0, y1 = 0, nx, 0, ny
        anchor_i, anchor_j = (nx - 1) / 2, (ny - 1) / 2
    else:
        radius = options.get("earth_radius_m")
        if radius is None:
            raise ValueError("Projected FA requires an explicit input.fa.earth_radius_m")
        if not np.isfinite(radius) or radius <= 0:
            raise ValueError("FA earth_radius_m must be finite and positive")
        if not 0 < abs(p[1]) < 1 or int(header["PCODIL"]) == -1:
            raise ValueError("Only spherical tangent Lambert projected FA is supported")
        if k[1] not in (0, 1, -1):
            raise ValueError("Unsupported FA domain-zone flag")
        x0, x1, y0, y1 = int(k[2]) - 1, int(k[3]), int(k[4]) - 1, int(k[5])
        if not (0 <= x0 < x1 <= nx and 0 <= y0 < y1 <= ny):
            raise ValueError("FA CI bounds conflict with stored dimensions")
        anchor_i, anchor_j = (x0 + x1 - 1) / 2, (y0 + y1 - 1) / 2
        if options["subdomain"] == "C":
            x0, x1, y0, y1 = x0 + int(k[6]), x1 - int(k[6]), y0 + int(k[7]), y1 - int(k[7])
        if x0 >= x1 or y0 >= y1 or p[6] <= 0 or p[7] <= 0:
            raise ValueError("Invalid FA domain extent or spacing")
        lat0 = np.rad2deg(p[3])
        if not 0 < abs(lat0) < 90:
            raise ValueError("Degenerate tangent Lambert reference latitude")
        if abs(abs(p[1]) - abs(np.sin(p[3]))) > 5.e-7:
            raise ValueError("FA projection does not match the supported tangent-cone convention")
    return p, k, (x0, x1, y0, y1), (anchor_i, anchor_j)


def _label_grid(x, y, mapping, longitude, latitude, shape, zone, subdomain, *, regular):
    units = ("degrees_east", "degrees_north") if regular else ("m", "m")
    ds = xr.Dataset(coords={
        "x": ("x", x, {"units": units[0], "axis": "X"}),
        "y": ("y", y, {"units": units[1], "axis": "Y"}),
        "longitude": ("x" if regular else ("y", "x"), longitude,
                      {"units": "degrees_east", "standard_name": "longitude"}),
        "latitude": ("y" if regular else ("y", "x"), latitude,
                     {"units": "degrees_north", "standard_name": "latitude"}),
    })
    if not regular:
        ds.x.attrs["standard_name"] = "projection_x_coordinate"
        ds.y.attrs["standard_name"] = "projection_y_coordinate"
    if not (np.isfinite(ds.latitude).all() and np.isfinite(ds.longitude).all()):
        raise ValueError("Nonfinite reconstructed FA geography")
    if (float(ds.longitude.max()) - float(ds.longitude.min()) > 180
            or np.any(np.abs(ds.latitude) >= 90)):
        raise ValueError("FA geographical index lookup supports nonpolar, "
                         "non-dateline regional grids")
    x0, x1, y0, y1 = zone
    ds = ds.assign_coords(crs=xr.DataArray(0, attrs=mapping),
                          source_i=("x", np.arange(x0, x1)), source_j=("y", np.arange(y0, y1)))
    ds.attrs.update(fa_subdomain=subdomain, fa_native_shape=list(shape),
                    fa_zone_indices=list(zone),
                    fa_grid_lookup="legacy_squared_degrees" if regular else NATIVE_LOOKUP)
    return ds


def _library_grid(facts, options):
    """Expand serializable library axes/CRS; no FA header interpretation here."""
    if facts.get("schema_version") != 1:
        raise ValueError("Unsupported FA library geometry schema_version")
    shape = facts["native_shape"]
    if shape[0] * shape[1] > options.get("max_points", 20_000_000):
        raise ValueError("Native FA storage grid exceeds input.fa.max_points")
    if facts["earth_model"]["radius_m"] != options.get("earth_radius_m"):
        raise ValueError("FA library geometry conflicts with the declared Earth model")
    try:
        zone = facts["zones"][options["subdomain"]]
    except KeyError as exc:
        raise ValueError("FA subdomain is not qualified for this library geometry") from exc
    x0, x1, y0, y1 = zone
    x, y = np.asarray(facts["x"])[x0:x1], np.asarray(facts["y"])[y0:y1]
    mapping = facts["crs"]
    regular = mapping["grid_mapping_name"] == "latitude_longitude"
    if regular:
        longitude, latitude = x, y
    else:
        crs = CRS.from_cf(mapping)
        inverse = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
        longitude, latitude = inverse.transform(*np.meshgrid(x, y))
    ds = _label_grid(x, y, mapping, longitude, latitude, shape, zone, options["subdomain"],
                     regular=regular)
    ds.attrs["fa_geometry_origin"] = facts["origin"]
    ds.attrs["fa_earth_model_origin"] = facts["earth_model"]["origin"]
    return ds


def fa_geometry(header, options):
    if "epygram" in header:
        return _library_grid(header["epygram"], options)
    if options.get("backend") == "epygram":
        raise ValueError("Missing qualified EPyGrAM geometry; inspect with geometry_options")
    p, k, (x0, x1, y0, y1), (anchor_i, anchor_j) = admitted_geometry(header, options)
    nx, ny = int(header["KNXLON"]), int(header["KNLATI"])
    regular = p[1] == -9
    if regular:
        longitude = np.rad2deg(p[4] + (np.arange(nx) - anchor_i) * p[6])
        latitude = np.rad2deg(p[5] + (np.arange(ny) - anchor_j) * p[7])
        difference = np.array([longitude[0], latitude[0], longitude[-1], latitude[-1]])
        difference -= np.rad2deg(p[12:16])
        difference[[0, 2]] = (difference[[0, 2]] + 180) % 360 - 180
        if np.max(np.abs(difference)) > 2.e-5:
            raise ValueError("FA regular geometry contradicts encoded CI corners")
        x, y = longitude, latitude
        mapping = {"grid_mapping_name": "latitude_longitude"}
    else:
        radius = options["earth_radius_m"]
        ci_bounds = int(k[2]) - 1, int(k[3]), int(k[4]) - 1, int(k[5])
        lat0, lon0, anchor_lon, anchor_lat = np.rad2deg([p[3], p[2], p[4], p[5]])
        mapping = dict(grid_mapping_name="lambert_conformal_conic", standard_parallel=float(lat0),
                       latitude_of_projection_origin=float(lat0),
                       longitude_of_central_meridian=float(lon0), earth_radius=float(radius))
        crs = CRS.from_cf(mapping)
        forward = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
        inverse = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
        ax, ay = forward.transform(anchor_lon, anchor_lat)
        ci_x = ax + (np.array([ci_bounds[0], ci_bounds[1] - 1]) - anchor_i) * p[6]
        ci_y = ay + (np.array([ci_bounds[2], ci_bounds[3] - 1]) - anchor_j) * p[7]
        corner_lon, corner_lat = inverse.transform(ci_x, ci_y)
        encoded = np.rad2deg(p[12:16])
        difference = np.array([corner_lon[0], corner_lat[0],
                               corner_lon[1], corner_lat[1]]) - encoded
        difference[[0, 2]] = (difference[[0, 2]] + 180) % 360 - 180
        # Native modern headers store angles as rounded reals. This tolerance
        # covers their precision, not a license to silently fit a different CRS.
        if not np.isfinite(difference).all() or np.max(np.abs(difference)) > 2.e-5:
            raise ValueError("Declared FA Earth shape/projection contradicts encoded CI corners "
                             f"(maximum disagreement {np.max(np.abs(difference)):.6g} degrees)")
        x = ax + (np.arange(x0, x1) - anchor_i) * p[6]
        y = ay + (np.arange(y0, y1) - anchor_j) * p[7]
        longitude, latitude = inverse.transform(*np.meshgrid(x, y))
    return _label_grid(x, y, mapping, longitude, latitude, (ny, nx), (x0, x1, y0, y1),
                       options["subdomain"], regular=regular)
