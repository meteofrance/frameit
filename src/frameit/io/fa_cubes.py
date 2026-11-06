"""Explicit native FA cube associations; no pressure, height or vector diagnosis."""

from __future__ import annotations

import json
from copy import deepcopy

import numpy as np
import xarray as xr

from frameit.io.fa_contracts import CUBE_VERTICAL_INTERPRETATION

HYBRID_AUXILIARIES = (
    "fa_hybrid_a", "fa_hybrid_a_normalized", "fa_hybrid_b", "fa_reference_pressure")


def record_selection(options, names):
    """Expand only requested logical variables into exact declared records."""
    records, owners = [], {}
    for name in names:
        cube = options["native_cubes"].get(name)
        for record in cube["records"] if cube else [name]:
            if record in owners:
                raise ValueError(f"{record}: repeated selection via {owners[record]}/{name}")
            owners[record] = name
            records.append(record)
    return records, owners


def cube_layouts(info, options, names):
    """Check EPyGrAM field levels against native header bounds and declarations."""
    layouts, axes = {}, {}
    nlevels = len(info.get("hybrid_contract", {}).get("interface_indices", [])) - 1
    for name in names:
        declaration = options["native_cubes"].get(name)
        if declaration is None:
            continue
        interface = declaration["vertical_position"] == "interface"
        group = "level_w" if interface else "level"
        levels = []
        for record in declaration["records"]:
            facts = info["field_descriptors"][record]["sampling"].get("epygram", {})
            labels = facts.get("levels", [])
            if (facts.get("type_of_first_fixed_surface") != 119 or len(labels) != 1
                    or int(labels[0]) != labels[0]
                    or not 1 <= labels[0] <= nlevels + int(interface)):
                raise ValueError(f"{record}: cube requires an evidenced native hybrid level "
                                 "within the declared mass/interface header range")
            levels.append(int(labels[0]))
            info["field_descriptors"][record]["sampling"]["native_cube"] = {
                "variable": name, "vertical_position": declaration["vertical_position"],
                "origin": "explicit input.fa.native_cubes", "independent_validation": False,
                "sampling": declaration["sampling"],
                "vector_basis": declaration.get("vector_basis"),
                "component_scaling": declaration.get("component_scaling"),
            }
            info["field_descriptors"][record]["sampling"][
                "vertical_interpretation"] = CUBE_VERTICAL_INTERPRETATION
        if levels != sorted(set(levels)):
            raise ValueError(f"{name}: cube levels must be unique and increasing; no reordering")
        if group in axes and levels != axes[group]:
            raise ValueError(f"{name}: {group} variables require identical native sampling levels")
        axes[group] = levels
        layouts[name] = {"group": group, "levels": levels,
                         "source_native_indices": [k - 1 for k in levels],
                         **deepcopy(declaration)}
    return layouts


def hybrid_contract(header, vertical):
    """FA PREFER scales dimensionless A; A/B define interfaces, not mass means.

    The unmodified EPyGrAM 2.1.0 FA reader separately exposes the same arrays
    in Pa and is checked in the child. Keeping all N+1 interfaces permits sparse
    extraction without inventing full-level coefficients or pressure fields.
    """
    count = header["KNIVER"] + 1
    reference = header["PREFER"]
    a, b = (np.asarray(header[name], dtype=float) for name in ("PAHYBR", "PBHYBR"))
    if (count < 2 or a.shape != (count,) or b.shape != (count,)
            or not np.isfinite(a).all() or not np.isfinite(b).all()
            or not np.isfinite(reference) or reference <= 0):
        raise ValueError("Invalid FA native hybrid header: require finite N+1 A/B, positive PREFER")
    with np.errstate(over="ignore", invalid="ignore"):
        a_pa = a * reference
    if not np.isfinite(a_pa).all():
        raise ValueError("Invalid FA native hybrid header: PAHYBR * PREFER is not finite")
    grid = vertical.grid
    if grid.get("ABgrid_position") != "flux":
        raise ValueError("Unqualified EPyGrAM hybrid coefficient grid")
    entries = grid["gridlevels"]
    if (not np.array_equal([entry[0] for entry in entries], np.arange(1, count + 1))
            or not np.array_equal([entry[1]["Ai"] for entry in entries], a_pa)
            or not np.array_equal([entry[1]["Bi"] for entry in entries], b)):
        raise ValueError("EPyGrAM hybrid coefficients contradict native PREFER/A/B")
    # Use the qualified library's pressure-valued coefficients; original
    # normalized A and PREFER remain native observations, not inferred inverses.
    a_pa = np.asarray([entry[1]["Ai"] for entry in entries])
    return {"interface_indices": list(range(1, count + 1)),
            "coefficient_storage_indices": list(range(count)), "a_normalized": a.tolist(),
            "a_pa": a_pa.tolist(), "b": b.tolist(), "reference_pressure_pa": reference,
            "coefficient_position": "interface", "normalization": "a_pa = PAHYBR * PREFER",
            "evidence": "native header and EPyGrAM-2.1.0 FA._read_geometry",
            "mass_coefficient_policy": "not inferred", "physical_coordinates": "not computed"}


def vertical_signature(info):
    return json.dumps({"cubes": info.get("native_cubes", {}),
                       "hybrid": info.get("hybrid_contract")}, sort_keys=True, allow_nan=False)


def add_cube_coordinates(ds, info):
    if not info.get("native_cubes"):
        return ds
    contract = info["hybrid_contract"]
    interface = "fa_hybrid_interface"
    ds = ds.assign_coords({
        interface: (interface, contract["interface_indices"], {
            "units": "1", "long_name": "original native hybrid coefficient interface index"}),
        "fa_hybrid_interface_source_native_index": (interface,
            contract["coefficient_storage_indices"], {"units": "1",
            "long_name": "zero-based native hybrid coefficient storage index"}),
        "fa_hybrid_a": (interface, contract["a_pa"], {
            "units": "Pa", "long_name": "pressure-valued hybrid A at native interfaces",
            "conversion": "native PAHYBR multiplied by native PREFER"}),
        "fa_hybrid_a_normalized": (interface, contract["a_normalized"], {
            "units": "1", "long_name": "native normalized PAHYBR interface coefficients"}),
        "fa_hybrid_b": (interface, contract["b"], {
            "units": "1", "long_name": "native PBHYBR interface coefficients"}),
        "fa_reference_pressure": xr.DataArray(contract["reference_pressure_pa"], attrs={
            "units": "Pa", "long_name": "native PREFER used to scale PAHYBR"}),
    })
    for name, layout in info["native_cubes"].items():
        group = layout["group"]
        ds = ds.assign_coords({
            group: (group, layout["levels"], {"axis": "Z", "units": "1", "positive": "down",
                                            "long_name": "native " + layout["vertical_position"]
                                                         + " model level index"}),
            f"{group}_source_native_index": (group, layout["source_native_indices"], {
                "units": "1", "long_name": "original zero-based native vertical index"}),
            f"{name}_native_record": (group, np.asarray(layout["records"], dtype=str)),
        })
    return ds


def validate_cube_requests(info, requests, conf):
    """No implied physical-level selection, wind basis or map-factor correction."""
    from frameit.core.preflight import wind_dependencies

    for group, spec in requests.items():
        for name in spec["variables"]:
            if name != "wind_speed" and info["native_cubes"].get(name, {}).get(
                "group", "surface"
            ) != group:
                raise ValueError(f"{name}: FA variable/cube selected in the wrong group {group}")
        if spec.get("level_domain") == "physical":
            raise ValueError("FA physical coordinates are gated; select stored indices/labels")
        layouts = [info["native_cubes"][name] for name in spec["variables"]
                   if name in info["native_cubes"]]
        if not layouts:
            continue
        levels = layouts[0]["levels"]
        if any(i < 0 or i >= len(levels) for i in spec.get("level_indices", [])):
            raise ValueError(f"{group}: out-of-range native FA cube indices")
        if any(label not in levels for label in spec.get("levels", [])):
            raise ValueError(f"{group}: unavailable native FA cube labels; no pressure matching")
    _, pairs = wind_dependencies(conf, conf.requests_user())
    for pair in pairs:
        for name in (pair["u"], pair["v"]):
            layout = info["native_cubes"].get(name)
            if layout is None:
                continue
            if (layout.get("vector_basis") != pair["reference_frame"]
                    or layout.get("component_scaling") != "physical_velocity"):
                raise ValueError(f"{name}: native cube wind basis/scaling must match wind_pairs "
                                 "and explicitly declare physical_velocity")
