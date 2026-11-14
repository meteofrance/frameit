# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0
"""Collocated earth-relative winds and geodesic polar diagnostics."""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr

from frameit.processing.wind_reference import (
    declared_pair,
    is_prepared,
    pair_definition,
    qualify_overridden_wind_metadata,
    rotation_angle,
    validate_pair_frame,
    wind_frame_override,
    wind_pairs,
)
from frameit.utils.units import convert_units


def wind_names(conf: Any, group: str) -> tuple[str, str]:
    """Use a unique declaration; multiple pairs require diagnostic aliases."""
    pairs = wind_pairs(conf, group)
    if len(pairs) == 1:
        return pairs[0]["u"], pairs[0]["v"]
    if group == "surface":
        aliases = getattr(conf, "tracking_var_aliases", {})
        keys = ("u10m", "v10m")
        names = aliases.get("u10m", "u10"), aliases.get("v10m", "v10")
    else:
        aliases = getattr(conf, "velocity_aliases", {})
        keys = ("u_velocity", "v_velocity")
        names = aliases.get("u_velocity", "u"), aliases.get("v_velocity", "v")
    if pairs and (not all(key in aliases for key in keys)
                  or declared_pair(conf, group, names) is None):
        raise ValueError(f"Ambiguous diagnostic wind pair in group {group!r}; "
                         f"configured aliases {names} must identify a declared pair")
    return names


def normalize_velocity_units(da: xr.DataArray, conf: Any) -> xr.DataArray:
    """Normalize units; missing units follow the AROME/MNH m/s model contract."""
    model = str(getattr(conf, "atm_model", "")).upper()
    result = convert_units(da, "velocity", assumed="m s-1" if model in {"AROME", "MNH"} else None)
    if not da.attrs.get("units"):
        result.attrs["unit_assumption_source"] = f"{model}_input_contract"
    return result


def align_wind_pair(u: xr.DataArray, v: xr.DataArray) -> tuple[xr.DataArray, xr.DataArray]:
    """Reject staggered/differently labelled pairs instead of broadcasting them."""
    if set(u.dims) != set(v.dims):
        raise ValueError("Wind components must be collocated on identical dimensions")
    for dim in u.dims:
        if u.sizes[dim] != v.sizes[dim] or (dim in u.coords) != (dim in v.coords):
            raise ValueError("Wind components require identical dimension coordinates")
    for name in set(u.coords) | set(v.coords):
        coordinate = u.coords[name] if name in u.coords else v.coords[name]
        relevant = coordinate.ndim > 0 or name in {
            "latitude", "longitude", "time", "level", "heightAboveGround",
        } or coordinate.attrs.get("standard_name") in {
            "latitude", "longitude", "time", "altitude", "height",
        }
        if not relevant:
            continue
        if (name not in u.coords or name not in v.coords
                or not u[name].variable.equals(v[name].variable)):
            raise ValueError(f"Wind components require identical coordinate {name!r}")
    for da in (u, v):
        prepared = bool(da.attrs.get("wind_collocation"))
        if not prepared and (
            any(dim.endswith(("_u", "_v")) for dim in da.dims)
            or da.attrs.get("grid") in {2, 3, 5, 6, 7, 8}
            or da.attrs.get("location") in {"u", "v", "face", "edge"}
            or da.attrs.get("stagger") not in {None, "", "mass", "center"}
            or any(c.attrs.get("c_grid_axis_shift", 0) != 0 for c in da.coords.values())
        ):
            raise ValueError(
                "Wind components have unresolved native point location; collocate first"
            )
    return xr.align(u, v.transpose(*u.dims), join="exact")


def normalize_native_wind_units(ds: xr.Dataset, conf: Any, group: str) -> xr.Dataset:
    """Normalize source units only, preserving native locations and vector basis.

    No rotation, collocation or component renaming. Wind values change only by
    the declared velocity unit scale. The explicit MNH missing-header override
    corrects basis labels while retaining the original metadata.
    """
    out = ds.copy(deep=False)
    pairs = wind_pairs(conf, group)
    names_list = [(p["u"], p["v"]) for p in pairs] if pairs else [wind_names(conf, group)]
    for names in names_list:
        if not any(name in ds for name in names):
            continue
        pair = pair_definition(conf, group, names)
        validate_pair_frame(ds, pair, conf)
        override = wind_frame_override(ds, pair, conf)
        for name in names:
            if name in ds:
                out[name] = normalize_velocity_units(ds[name], conf)
                if not is_prepared(ds[name]):
                    out[name].attrs["wind_reference_frame"] = pair["reference_frame"]
                    out[name].attrs["wind_reference_frame_source"] = "explicit_input_declaration"
                    if override:
                        attrs = out[name].attrs
                        for key in ("standard_name", "GRIB_uvRelativeToGrid", "uvRelativeToGrid"):
                            if key in attrs:
                                attrs.setdefault("source_" + key, attrs[key])
                        attrs.update(
                            standard_name="eastward_wind" if name == names[0] else "northward_wind",
                            source_wind_reference_frame="earth",
                            source_wind_reference_frame_metadata="grid",
                            wind_reference_frame_override=override,
                        )
                        for key in ("GRIB_uvRelativeToGrid", "uvRelativeToGrid"):
                            if key in attrs:
                                attrs[key] = 0
    return qualify_overridden_wind_metadata(out, conf)


def normalize_winds(ds: xr.Dataset, conf: Any, group: str) -> xr.Dataset:
    """Convert every present declared mass-point pair to physical east/north m/s.

    Unknown fields and absent pairs do not create dependencies. A lone member
    of an unprepared pair is an error. Prepared singletons may survive variable
    selection. Repeated preparation is idempotent, including when original
    metadata and dataset source markers are retained.
    """
    pairs = wind_pairs(conf, group)
    names_list = [(p["u"], p["v"]) for p in pairs] if pairs else [wind_names(conf, group)]
    out = ds.copy(deep=False)
    for names in names_list:
        if not any(name in ds for name in names):
            continue
        pair = pair_definition(conf, group, names)
        frame = validate_pair_frame(ds, pair, conf)
        override = wind_frame_override(ds, pair, conf)
        present = [name for name in names if name in ds]
        if len(present) == 1:
            name = present[0]
            out[name] = normalize_velocity_units(ds[name], conf)
            continue
        u, v = align_wind_pair(*(normalize_velocity_units(ds[name], conf) for name in names))
        if all(is_prepared(ds[name]) for name in names):
            out[names[0]], out[names[1]] = u, v
            continue
        method = "none"
        angle = None
        if frame == "grid":
            angle = rotation_angle(ds, conf, pair)
            method = pair["rotation"]["method"]
            if pair.get("declaration") == "legacy_scalar":
                method = "legacy_grid_rotation_coordinate"
        if angle is not None:
            if not set(angle.dims) <= set(u.dims):
                raise ValueError("Wind rotation must be defined on the collocated wind grid")
            u, v, angle = xr.align(u, v, angle, join="exact")
            east = u * np.cos(angle) - v * np.sin(angle)
            north = u * np.sin(angle) + v * np.cos(angle)
        else:
            east, north = u, v
        for name, value, standard in zip(names, (east, north),
                                          ("eastward_wind", "northward_wind"), strict=True):
            attrs = dict(ds[name].attrs)
            attrs.update((u if name == names[0] else v).attrs)
            for key in ("standard_name", "grid", "GRIB_uvRelativeToGrid", "uvRelativeToGrid"):
                if key in attrs:
                    attrs.setdefault("source_" + key, attrs[key])
            attrs.update(units="m s-1", wind_reference_frame="earth",
                         source_wind_reference_frame=pair["reference_frame"],
                         wind_reference_frame_source=pair.get("declaration", "wind_pairs"),
                         standard_name=standard, frameit_wind_prepared="earth",
                          wind_rotation_method=method, wind_pair=",".join(names))
            if override:
                attrs.update(wind_reference_frame_override=override,
                             source_wind_reference_frame_metadata="grid")
            for key in ("GRIB_uvRelativeToGrid", "uvRelativeToGrid"):
                if key in attrs:
                    attrs[key] = 0
            if "grid" in attrs:
                # MNH mass-point grid indicator; original indicator remains source_grid.
                attrs["grid"] = 1
            if angle is not None:
                attrs["wind_rotation_convention"] = "counterclockwise_from_east_to_grid_x"
                if pair["rotation"].get("coordinate"):
                    attrs["wind_rotation_coordinate"] = pair["rotation"]["coordinate"]
                for key, item in angle.attrs.items():
                    if key.startswith("rotation_"):
                        attrs[key] = item
            out[name] = value.assign_attrs(attrs)
    return qualify_overridden_wind_metadata(out, conf)


def polar_wind_components(
    u: xr.DataArray, v: xr.DataArray, bearing: xr.DataArray
) -> tuple[xr.DataArray, xr.DataArray]:
    """Rotate collocated east/north winds in m/s using a local bearing in radians."""
    # This low-level numerical API historically accepts unitless canonical
    # arrays (m/s and radians); explicitly declared alternative units convert.
    u = convert_units(u, "velocity", assumed="m s-1")
    v = convert_units(v, "velocity", assumed="m s-1")
    bearing = convert_units(bearing, "angle", assumed="rad")
    u, v = align_wind_pair(u, v)
    u, v, bearing = xr.align(u, v, bearing, join="exact")
    if "rr" in bearing.coords:
        bearing = bearing.where(bearing["rr"] != 0)
    radial = u * np.sin(bearing) + v * np.cos(bearing)
    tangential = u * np.cos(bearing) - v * np.sin(bearing)
    for da, description in (
        (radial, "radial wind component (positive outward from storm center)"),
        (tangential, "tangential wind component (positive clockwise)"),
    ):
        da.attrs.update(
            units="m s-1", long_name=description, wind_reference_frame="earth",
            vector_basis="terminal_forward_geodesic", origin_policy="undefined_at_zero_radius",
        )
    return radial, tangential


def add_vrad_vtan_from_polar_dict(
    dict_polar_user: dict[str, xr.Dataset], conf: Any
) -> dict[str, xr.Dataset]:
    out = dict_polar_user
    for group, ds in out.items():
        pairs = wind_pairs(conf, group)
        if pairs and not any(p[component] in ds for p in pairs for component in ("u", "v")):
            continue
        ds = normalize_winds(ds, conf, group)
        out[group] = ds
        u, v = wind_names(conf, group)
        if u not in ds or v not in ds:
            continue
        if "radial_bearing" not in ds:
            raise ValueError("Polar winds require terminal-forward radial_bearing")
        radial, tangential = polar_wind_components(ds[u], ds[v], ds["radial_bearing"])
        out[group] = ds.assign(vrad=radial, vtan=tangential)
        out[group].attrs["wind_reference_frame"] = "earth"
    return out


def add_speed_from_uv_dict(
    dict_user: dict[str, xr.Dataset], conf: Any, *, speed_name: str = "wind_speed"
) -> dict[str, xr.Dataset]:
    out = dict_user
    for group, ds in out.items():
        pairs = wind_pairs(conf, group)
        if pairs and not any(p[component] in ds for p in pairs for component in ("u", "v")):
            continue
        ds = normalize_winds(ds, conf, group)
        out[group] = ds
        u, v = wind_names(conf, group)
        if u not in ds or v not in ds:
            continue
        u_da, v_da = align_wind_pair(ds[u], ds[v])
        speed = np.hypot(u_da, v_da)
        speed.attrs.update(
            units="m s-1", long_name="horizontal wind speed", wind_reference_frame="earth",
            derivation=(
                "magnitude_of_interpolated_collocated_components"
                if "radial_bearing" in ds else "magnitude_of_collocated_components"
            ),
        )
        out[group] = ds.assign({speed_name: speed})
        out[group].attrs["wind_reference_frame"] = "earth"
    return out


def execute_source_operations(user, internal, source, binding, conf):
    """Execute only bound model-grid results, on separate native input views."""
    import json
    from copy import copy

    from frameit.processing.requests import _operation_units, source_field_metadata
    from frameit.processing.wind_collocation import collocate_mnh_component

    out = dict(user)
    results = {}
    rotation_coordinates = {}
    for operation in binding.get("operations", []):
        geometry = xr.Dataset(coords={
            n: xr.Variable(c["dimensions"], c["values"], c["attributes"])
            for n, c in operation["geometry"]["coordinates"].items()},
            attrs=operation["geometry"]["attributes"])
        target_vertical = operation["vertical"]
        if target_vertical is not None:
            dim = target_vertical["dimension"]
            geometry = geometry.isel({dim: target_vertical["positions"]})
        arrays = {}
        native_views = []
        input_names = set(operation["inputs"].values())
        for name in operation["input_binding"]["dependencies"]:
            descriptor = operation["input_binding"]["dependencies"][name]
            record = descriptor["records"][0]
            native = internal[record["grid_id"]]
            value = native[name]
            native_view = native
            if "time" in value.dims:
                value = value.sel(time=[record["time"]])
                native_view = native_view.sel(time=[record["time"]])
            for dim, member in record.get("native_axes", {}).items():
                value = value.sel({dim: [member]})
            vertical = record["vertical"]
            if vertical is not None:
                dim = vertical["dimension"]
                index = f"{dim}_source_native_index"
                original = native[index].values.tolist()
                value = value.isel({dim: [original.index(i) for i in
                                         vertical["source_native_indices"]]})
                native_view = native_view.isel({dim: [original.index(i) for i in
                                                      vertical["source_native_indices"]]})
            field = source["fields"][record["field_id"]]
            metadata = record.get("field_metadata") or source_field_metadata(
                source, field, record=record) or descriptor.get("field_metadata")
            attrs = {**value.attrs, **(
                field["attributes"] if metadata is None else metadata["attributes"])}
            if metadata:
                attrs["frameit_metadata_origins"] = json.dumps(metadata["origins"], sort_keys=True)
            native_views.append(native_view)
            value = value.reset_coords(drop=True).assign_attrs(attrs)
            if (name in input_names and operation["sampling"] == "mass"
                    and operation["model"] == "mesonh"):
                value = collocate_mnh_component(
                    value, geometry, conf, vertical="level_w" in value.dims)
            arrays[name] = value
        prepared = xr.Dataset({n: value for n, value in arrays.items() if n in input_names})
        prepared = prepared.assign_coords({
            n: c for n, c in geometry.coords.items() if set(c.dims) <= set(prepared.dims)})
        prepared.attrs = dict(geometry.attrs)
        if operation["preparation"] == "croco_midpoint_both_valid_then_rho_angle":
            from frameit.io.croco_utils import prepare_croco_currents

            settings = copy(conf)
            settings.cartesian_horizontal_winds = "mass_earth"
            settings.compute_polar_proj = False
            settings.requested_variables_user = {"current": {
                "variables": [operation["inputs"]["u"], operation["inputs"]["v"]]}}
            prepared = prepare_croco_currents(prepared, settings)
        if operation["pair"]:
            settings = copy(conf)
            settings.wind_pairs = [operation["pair"]]
            if source["format"] == "grib":
                settings.name_lat_dim, settings.name_lon_dim = "y", "x"
            settings.velocity_aliases = {
                "u_velocity": operation["inputs"]["u"], "v_velocity": operation["inputs"]["v"]}
            prepared = normalize_winds(prepared, settings, "operation")
        if operation["method"] == "wind_speed":
            u, v = align_wind_pair(*(prepared[operation["inputs"][key]] for key in ("u", "v")))
            value = np.hypot(u, v).assign_attrs(
                units="m s-1", long_name="horizontal wind speed",
                wind_reference_frame="earth", derivation="magnitude_of_collocated_components")
        else:
            input_name = operation["inputs"]["field"]
            value = prepared[input_name]
            if operation["preparation"] == "croco_midpoint_both_valid_then_rho_angle":
                value = value.assign_coords(mask_rho=prepared.mask_rho)
            units = operation.get("units") or arrays[input_name].attrs.get("units")
            if units and (operation["pair"] or "units" in operation):
                value = _operation_units(value, units, model=operation["model"])
        from frameit.processing.polar.metadata import preserve_coordinate_dependencies

        support = xr.Dataset(arrays)
        support = support.assign_coords({
            n: c for n, c in geometry.coords.items() if set(c.dims) <= set(support.dims)})
        dataset = preserve_coordinate_dependencies(
            support, value.to_dataset(name=operation["name"]))
        for native_view in native_views:
            dataset = preserve_coordinate_dependencies(native_view, dataset)
        vertical = operation["vertical"]
        if vertical is not None:
            dataset = dataset.assign_coords({
                n: xr.Variable(c["dimensions"], c["values"], c["attributes"])
                for n, c in vertical["coordinates"].items()})
            dataset = dataset.assign_coords({f"{vertical['dimension']}_source_native_index": (
                vertical["dimension"], vertical["source_native_indices"], {"units": "1"})})
        dataset = dataset.drop_vars(
            [n for n in dataset.coords if n in {"BETA", "RPK", "LON0", "CARTESIAN"}],
            errors="ignore")
        key = operation["grid_id"], operation["name"]
        if operation["pair"]:
            coordinate = (operation["pair"].get("rotation") or {}).get("coordinate")
            if coordinate in dataset.coords:
                rotation_coordinates.setdefault(key, set()).add(coordinate)
        dataset[operation["name"]].attrs.update(
            frameit_method=operation["method"], frameit_preparation=operation["preparation"],
            frameit_sampling=operation["sampling"], frameit_basis=operation["basis"],
            frameit_selection_grid=operation["grid_id"],
            frameit_shared_levels=json.dumps(
                {key: vertical[key] for key in ("source_native_indices", "values", "units")}
                if vertical else None, sort_keys=True),
        )
        results.setdefault(key, []).append(dataset)
    for (grid, name), sequence in results.items():
        for coordinate in rotation_coordinates.get((grid, name), set()):
            if any(not sequence[0][coordinate].variable.equals(ds[coordinate].variable)
                   for ds in sequence[1:]):
                sequence = [ds.assign_coords({
                    coordinate: ds[coordinate].expand_dims(time=ds.time)
                    if "time" not in ds[coordinate].dims else ds[coordinate]}) for ds in sequence]
        result = (sequence[0] if len(sequence) == 1 else xr.concat(
            sequence, dim="time", data_vars="all", coords="minimal",
            compat="equals", join="exact", combine_attrs="override"))
        out[grid] = (xr.merge([out[grid], result], join="exact", compat="identical",
                              combine_attrs="override") if grid in out else result)
    return out
