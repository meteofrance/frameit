# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import xarray as xr

from frameit.processing.derived.wind import add_speed_from_uv_dict, add_vrad_vtan_from_polar_dict
from frameit.processing.polar.polar_grid import PolarLonLatGrid
from frameit.processing.polar.polar_utils import finalize_polar_output

try:
    import xesmf as xe
except Exception as exc:  # pragma: no cover
    xe = None
    _XESMF_IMPORT_ERROR = exc
else:
    _XESMF_IMPORT_ERROR = None

logger = logging.getLogger(__name__)


# ----------------------------
# small helpers
# ----------------------------
def _as_lower_str(x: Any) -> str:
    return str(x).strip().lower()


def _get_required(conf: Any, name: str) -> Any:
    v = getattr(conf, name, None)
    if v is None:
        raise ValueError(f"Missing required conf attribute: {name!r}")
    return v


def _polar_lonlat_from_grid(ds_polar: xr.Dataset) -> tuple[xr.DataArray, xr.DataArray]:
    if "lon" in ds_polar:
        lon = ds_polar["lon"]
    elif "longitude" in ds_polar:
        lon = ds_polar["longitude"]
    else:
        raise ValueError(
            "Polar grid dataset missing longitude field (expected 'lon' or 'longitude')."
        )

    if "lat" in ds_polar:
        lat = ds_polar["lat"]
    elif "latitude" in ds_polar:
        lat = ds_polar["latitude"]
    else:
        raise ValueError(
            "Polar grid dataset missing latitude field (expected 'lat' or 'latitude')."
        )

    return lon, lat


def _reshape_locstream_dataset(
    ds_loc: xr.Dataset,
    *,
    r_km: np.ndarray,
    theta_deg: np.ndarray,
    loc_dim: str = "locations",
) -> xr.Dataset:
    if loc_dim not in ds_loc.dims:
        raise ValueError(f"Expected locstream dimension {loc_dim!r} in xESMF output.")

    nr = int(len(r_km))
    ntheta = int(len(theta_deg))
    nloc = int(ds_loc.sizes[loc_dim])
    if nloc != nr * ntheta:
        raise ValueError(f"LocStream size mismatch: {nloc} != {nr}*{ntheta}")

    out_vars: dict[str, xr.DataArray] = {}
    for v in ds_loc.data_vars:
        da = ds_loc[v]
        if loc_dim not in da.dims:
            out_vars[v] = da
            continue

        if da.dims[-1] != loc_dim:
            other = [d for d in da.dims if d != loc_dim]
            da = da.transpose(*other, loc_dim)

        other_dims = list(da.dims[:-1])
        other_shape = [da.sizes[d] for d in other_dims]
        new_shape = tuple(other_shape + [nr, ntheta])

        data = da.data.reshape(new_shape)
        new_dims = tuple(other_dims + ["rr", "theta_deg"])

        # only keep 1D "index-like" coords from xesmf output
        coords: dict[str, Any] = {"rr": ("rr", r_km), "theta_deg": ("theta_deg", theta_deg)}
        for d in other_dims:
            if d in da.coords and da.coords[d].ndim == 1 and da.coords[d].dims == (d,):
                coords[d] = da.coords[d]

        out_vars[v] = xr.DataArray(
            data=data,
            dims=new_dims,
            coords=coords,
            attrs=da.attrs,
            name=da.name,
        )
        
    return xr.Dataset(out_vars)




# ----------------------------
# request parsing for polar (variables only)
# ----------------------------
_IGNORED_VERTICAL_KEYS = {
    "level_selection",
    "level_values",
    "level_indices",
    "levels",
    "all_levels",
    "level",  # defensive (some users might write "level:" by mistake inside group)
}


def _get_polar_requests_variables_only(conf: Any) -> dict[str, dict[str, Any]]:
    """
    Build variable-only polar requests, ignoring any vertical-level selection.

    Parameters
    ----------
    conf : object
        Configuration object.  Reads ``polar_variables``, which may be:

        - ``"all"`` : use ``conf.requested_variables_user`` as source, keeping
          only the ``"variables"`` key per group.
        - A dict shaped like ``requested_variables_user`` : extract only the
          variable lists.  Vertical-selection keys are ignored and a warning
          is emitted.

    Returns
    -------
    dict[str, dict[str, Any]]
        Mapping from group name to ``{"variables": [...]}``.  Groups with no
        variables are omitted.
    """
    raw = getattr(conf, "polar_variables", None)
    if raw is None:
        return {}

    if isinstance(raw, str) and _as_lower_str(raw) == "all":
        raw = getattr(conf, "requested_variables_user", None)

    if not isinstance(raw, dict):
        raise TypeError("conf.polar_variables must be a dict (or 'all').")

    out: dict[str, dict[str, Any]] = {}
    for g, spec in raw.items():
        g = str(g)

        if spec is None:
            continue

        # allow shorthand: group: ["u","v"]
        if isinstance(spec, (list, tuple)):
            vars_list = [str(v) for v in spec]
            out[g] = {"variables": vars_list}
            continue

        if not isinstance(spec, dict):
            raise TypeError(f"polar_variables[{g!r}] must be a dict or a list of variable names.")

        # ignore vertical-selection related keys
        ignored = sorted([k for k in spec.keys() if k in _IGNORED_VERTICAL_KEYS])
        if ignored:
            logger.warning(
                f"[polar_project] polar_variables[{g}] contains vertical selection keys {ignored}, "
                "ignored. All available levels in extracted datasets will be projected.",
            )

        vars_list = spec.get("variables", []) or []
        vars_list = [str(v) for v in vars_list]
        if vars_list:
            out[g] = {"variables": vars_list}

    return out


def _subset_vars_for_polar(
    ds_src: xr.Dataset,
    variables: list[str],
    *,
    time_dim: str,
    group: str = "",
) -> xr.Dataset | None:
    """
    Subset a dataset to the requested variables, preserving all vertical levels.

    Parameters
    ----------
    ds_src : xr.Dataset
        Source dataset for the group.
    variables : list[str]
        Variable names to keep.
    time_dim : str
        Name of the time dimension.  Variables missing this dimension are
        expanded along it.
    group : str, optional
        Group label used in warning messages. Default ``""``.

    Returns
    -------
    xr.Dataset or None
        Subset dataset with only the requested variables and all GRIB scalar
        auxiliary coordinates dropped.  ``None`` when no requested variable
        is present in ``ds_src``.
    """
    keep = [v for v in variables if v in ds_src.data_vars]
    missing = [v for v in variables if v not in ds_src.data_vars]
    if missing:
        logger.warning(f"[polar_project] group={group}: missing variables (skipped): {missing}")
    if not keep:
        return None

    var_map: dict[str, xr.DataArray] = {}
    for v in keep:
        da = ds_src[v]
        if time_dim in ds_src.dims and time_dim not in da.dims:
            da = da.expand_dims({time_dim: ds_src[time_dim]})
        var_map[v] = da

    ds_sub = xr.Dataset(var_map)

    # Drop AROME GRIB scalar artefacts (step, valid_time, scalar heightAboveGround, …).
    ds_sub = ds_sub.reset_coords(drop=True)

    return ds_sub


# ----------------------------
# main API
# ----------------------------


def polar_project(
    dico_collocated: dict[str, xr.Dataset],
    *,
    conf: Any,
    method: str = "bilinear",
    track: xr.Dataset | None = None,
) -> tuple[dict[str, xr.Dataset], dict[str, Any]]:
    """
    Project cyclone-centred Cartesian fields onto a polar (r, θ) grid.

    Uses xESMF regridding from the rectangular ``(x_box, y_box)`` extracted
    grid to a geodesic polar locstream, then reshapes the result into
    ``(rr, theta_deg)`` dimensions.

    Parameters
    ----------
    dico_collocated : dict[str, xr.Dataset]
        Per-group collocated datasets keyed by vertical group name
        (e.g. ``"surface"``, ``"level"``, ``"heightAboveGround"``).
        Each dataset must have a ``"time"`` dimension.
    conf : object
        Configuration object.  Required attributes: ``compute_polar_proj``
        (bool), ``name_longitude``, ``name_latitude``, ``tracking_method``,
        ``polar_variables``, and polar-grid sizing attributes consumed by
        :class:`~frameit.processing.polar.polar_grid.PolarLonLatGrid`.
    method : str, optional
        xESMF regridding method. Default ``"bilinear"``.
    track : xr.Dataset or None, optional
        Continuous ``lon(time)``/``lat(time)`` centres for the polar origin.
        When absent, use the centre cell of the extracted Cartesian box.

    Returns
    -------
    dico_out : dict[str, xr.Dataset]
        Per-group polar datasets keyed by output group name.  Empty when
        ``conf.compute_polar_proj`` is ``False`` or all requests are skipped.
    report : dict[str, Any]
        Projection summary with keys ``"projected"``, ``"skipped"``,
        ``"redirects"``, ``"n_groups_out"``, ``"n_groups_requested"``,
        and ``"notes"`` (when skipped early).

    Raises
    ------
    ImportError
        If xESMF is not installed.
    ValueError
        If the ``"time"`` dimension is absent from the reference dataset.
    """
    if xe is None:  # pragma: no cover
        raise ImportError("xESMF is required for polar projection.") from _XESMF_IMPORT_ERROR

    if not bool(getattr(conf, "compute_polar_proj", False)):
        return {}, {"skipped": [], "notes": ["compute_polar_proj is False"]}

    time_dim = "time"  # FrameIt convention after extract_data
    lon_name = str(_get_required(conf, "name_longitude"))
    lat_name = str(_get_required(conf, "name_latitude"))
    tracking_method = str(_get_required(conf, "tracking_method"))

    reqs = _get_polar_requests_variables_only(conf)
    if not reqs:
        return {}, {"skipped": [], "notes": ["No polar_variables request found."]}

    ds_ref = (
        dico_collocated["surface"]
        if "surface" in dico_collocated
        else next(iter(dico_collocated.values()))
    )
    if time_dim not in ds_ref.dims:
        raise ValueError(f"[polar_project] Expected {time_dim!r} in extracted datasets.")

    time = ds_ref[time_dim]
    ntimes = int(time.size)

    logger.info(
        f"[polar_project] start: method={method!s}, tracking_method={tracking_method!s}, "
        f"time_dim={time_dim!r}, lon={lon_name!r}, lat={lat_name!r}, ntimes={ntimes}",
    )
    logger.info(f"[polar_project] requested groups: {list(reqs.keys())}")
    if ntimes > 0:
        logger.info(f"[polar_project] time range: {time.values[0]} -> {time.values[-1]}")

    # Step 2: Build polar grid and drop non-dimension coords (AROME GRIB artefacts)
    grid = PolarLonLatGrid.from_conf(conf=conf)
    ds_polar_grid = grid.build(ds_ref, track=track).reset_coords(drop=True)

    lon_polar, lat_polar = _polar_lonlat_from_grid(ds_polar_grid)
    r_km = np.asarray(grid.r_km, dtype=float)
    theta_deg = np.asarray(ds_polar_grid["theta_deg"].values, dtype=float)
    nr = int(r_km.size)
    ntheta = int(theta_deg.size)
    nloc = nr * ntheta

    logger.info(f"[polar_project] target grid: nr={nr}, ntheta={ntheta}, nloc={nloc}")

    # detect polar-grid time dimension if present
    grid_time_dim = None
    for d in lon_polar.dims:
        if d not in ("rr", "theta_deg"):
            grid_time_dim = d
            break

    fixed_box = _as_lower_str(tracking_method) == "fixed_box"
    logger.info(f"[polar_project] fixed_box={fixed_box}, grid_time_dim={grid_time_dim!r}")

    report: dict[str, Any] = {"skipped": [], "redirects": [], "projected": []}
    dico_out: dict[str, xr.Dataset] = {}

    def _make_grid_in(ds_src_t: xr.Dataset) -> xr.Dataset:
        # lon/lat as plain arrays only (avoid scalar coords bleed-through)
        lon2 = np.asarray(ds_src_t[lon_name].values)
        lat2 = np.asarray(ds_src_t[lat_name].values)
        lon2 = np.asfortranarray(lon2)
        lat2 = np.asfortranarray(lat2)
        return xr.Dataset(
            data_vars=dict(lon=(("y_box", "x_box"), lon2), lat=(("y_box", "x_box"), lat2))
        )

    def _make_locstream_out(lon2d: np.ndarray, lat2d: np.ndarray) -> xr.Dataset:
        lon1d = np.asarray(lon2d, dtype=float).reshape(-1)
        lat1d = np.asarray(lat2d, dtype=float).reshape(-1)
        if lon1d.size != nloc:
            raise ValueError(f"Target locstream size mismatch: {lon1d.size} != {nloc}")
        return xr.Dataset(data_vars=dict(lon=(("locations",), lon1d), lat=(("locations",), lat1d)))

    def _get_lonlat_target(it: int) -> tuple[np.ndarray, np.ndarray]:
        if grid_time_dim is None:
            return lon_polar.values, lat_polar.values
        return lon_polar.isel({grid_time_dim: it}).values, lat_polar.isel(
            {grid_time_dim: it}
        ).values

    # constant polar diagnostics as raw arrays
    xkm = ds_polar_grid["x_km"].values if "x_km" in ds_polar_grid else None
    ykm = ds_polar_grid["y_km"].values if "y_km" in ds_polar_grid else None

    for group_key, req in reqs.items():
        group_key = str(group_key)
        out_key = "level" if group_key == "level_w" else group_key

        logger.info(
            "[polar_project] group=%s: start, requested variables=%s",
            group_key,
            req.get("variables", []),
        )

        # redirect rule for level_w
        if group_key == "level_w":
            if "level" in dico_collocated:
                src_key = "level"
                report["redirects"].append({"from": "level_w", "to": "level"})
                logger.info("[polar_project] group=level_w redirected to source group 'level'")
            elif "level_w" in dico_collocated:
                src_key = "level_w"
                report["redirects"].append({"from": "level_w", "to": "level_w"})
                logger.info("[polar_project] group=level_w uses source group 'level_w'")
            else:
                report["skipped"].append(
                    {"group": group_key, "reason": "missing group level and level_w"}
                )
                logger.warning(
                    "[polar_project] group=level_w skipped: missing group level and level_w"
                )
                continue
        else:
            if group_key not in dico_collocated:
                report["skipped"].append({"group": group_key, "reason": "missing group"})
                logger.warning(f"[polar_project] group={group_key} skipped: missing group")
                continue
            src_key = group_key

        ds_src = dico_collocated[src_key]

        variables = req.get("variables", []) or []
        ds_sub = _subset_vars_for_polar(ds_src, variables, time_dim=time_dim, group=group_key)
        if ds_sub is None or len(ds_sub.data_vars) == 0:
            report["skipped"].append({"group": group_key, "reason": "no matching variables"})
            logger.warning(f"[polar_project] group={group_key} skipped: no matching variables")
            continue

        logger.info(
            f"[polar_project] group={group_key}: source={src_key!s} out={out_key!s} "
            f"kept_vars={list(ds_sub.data_vars)} dims={dict(ds_sub.sizes)}",
        )

        pieces = []

        if fixed_box:
            ds_src0 = ds_src.isel({time_dim: 0})
            ds_in0 = _make_grid_in(ds_src0)

            lon0, lat0 = _get_lonlat_target(0)
            ds_out0 = _make_locstream_out(lon0, lat0)

            regridder = xe.Regridder(
                ds_in0,
                ds_out0,
                method,
                locstream_out=True,
                unmapped_to_nan=True,
            )
            try:
                ds_loc = regridder(ds_sub)  # keeps time + vertical dims
                ds_pol = _reshape_locstream_dataset(
                    ds_loc, r_km=r_km, theta_deg=theta_deg, loc_dim="locations"
                )

                lon_full = np.broadcast_to(lon0[None, :, :], (ntimes, nr, ntheta))
                lat_full = np.broadcast_to(lat0[None, :, :], (ntimes, nr, ntheta))

                time_clean = xr.DataArray(time.values, dims=(time_dim,), name=time_dim)
                ds_pol = ds_pol.assign_coords(
                    {
                        time_dim: time_clean,
                        lon_name: ((time_dim, "rr", "theta_deg"), lon_full),
                        lat_name: ((time_dim, "rr", "theta_deg"), lat_full),
                    }
                )

                if xkm is not None:
                    ds_pol = ds_pol.assign_coords({"x_km": (("rr", "theta_deg"), xkm)})
                if ykm is not None:
                    ds_pol = ds_pol.assign_coords({"y_km": (("rr", "theta_deg"), ykm)})

                pieces = [ds_pol]

            finally:
                try:
                    regridder.clean_weight_file()
                except Exception:
                    pass

        else:
            for it in range(ntimes):
                ds_src_t = ds_src.isel({time_dim: it})
                ds_sub_t = ds_sub.isel({time_dim: it}) if time_dim in ds_sub.dims else ds_sub

                ds_in = _make_grid_in(ds_src_t)
                lon_it, lat_it = _get_lonlat_target(it)
                ds_out = _make_locstream_out(lon_it, lat_it)

                regridder = xe.Regridder(
                    ds_in,
                    ds_out,
                    method,
                    locstream_out=True,
                    unmapped_to_nan=True,
                )
                try:
                    ds_loc = regridder(ds_sub_t)
                    ds_pol = _reshape_locstream_dataset(
                        ds_loc, r_km=r_km, theta_deg=theta_deg, loc_dim="locations"
                    )

                    tval = time.isel({time_dim: it}).values
                    ds_pol = ds_pol.expand_dims({time_dim: [tval]})

                    ds_pol = ds_pol.assign_coords(
                        {
                            time_dim: [tval],
                            lon_name: ((time_dim, "rr", "theta_deg"), lon_it[None, :, :]),
                            lat_name: ((time_dim, "rr", "theta_deg"), lat_it[None, :, :]),
                        }
                    )
                    if xkm is not None:
                        ds_pol = ds_pol.assign_coords({"x_km": (("rr", "theta_deg"), xkm)})
                    if ykm is not None:
                        ds_pol = ds_pol.assign_coords({"y_km": (("rr", "theta_deg"), ykm)})

                    pieces.append(ds_pol)

                finally:
                    try:
                        regridder.clean_weight_file()
                    except Exception:
                        pass

        if not pieces:
            report["skipped"].append(
                {"group": group_key, "reason": "projection produced no output"}
            )
            logger.warning(
                f"[polar_project] group={group_key} skipped: projection produced no output"
            )
            continue

        ds_group_out = xr.concat(pieces, dim=time_dim) if len(pieces) > 1 else pieces[0]

        logger.info(
            "[polar_project] group=%s: projected vars=%s dims=%s",
            group_key,
            list(ds_group_out.data_vars),
            dict(ds_group_out.sizes),
        )

        ds_group_out.attrs.update(ds_src.attrs)
        ds_group_out.attrs["polar_proj_backend"] = "xesmf"
        ds_group_out.attrs["polar_proj_method"] = str(method)
        ds_group_out.attrs["polar_proj_group_requested"] = group_key
        ds_group_out.attrs["polar_proj_group_source"] = src_key
        ds_group_out.attrs["polar_proj_group_output"] = out_key

        ds_group_out = finalize_polar_output(ds_group_out)
        
        ds_group_out = ds_group_out.assign_coords({"rr_km": xr.DataArray(r_km, dims=("rr",), 
                                attrs={"units": "km", "long_name": "radial distance from center"})})

        if out_key in dico_out:
            dico_out[out_key] = xr.merge([dico_out[out_key], ds_group_out], compat="no_conflicts")
        else:
            dico_out[out_key] = ds_group_out

        report["projected"].append(
            {
                "requested_group": group_key,
                "source_group": src_key,
                "output_group": out_key,
                "nvars": len(ds_sub.data_vars),
            }
        )

    if not dico_out:
        logger.warning("[polar_project] No variables projected (all requests skipped).")
    else:
        # summary (no per-time logging)
        nreq = len(reqs)
        nproj = len(report.get("projected", []))
        nskip = len(report.get("skipped", []))
        reasons = [x.get("reason", "unknown") for x in report.get("skipped", [])]
        reason_counts: dict[str, int] = {}
        for r in reasons:
            reason_counts[r] = reason_counts.get(r, 0) + 1
        logger.info(
            "[polar_project] summary: requested_groups=%s, projected_groups=%s,"
            " skipped_groups=%s, skip_reasons=%s",
            nreq,
            nproj,
            nskip,
            reason_counts,
        )

        dico_out = add_vrad_vtan_from_polar_dict(dico_out, conf)
        dico_out = add_speed_from_uv_dict(dico_out, conf)

    report["n_groups_out"] = len(dico_out)
    report["n_groups_requested"] = len(reqs)
    return dico_out, report
