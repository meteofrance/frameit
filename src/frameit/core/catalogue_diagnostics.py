"""Resolve selected missing fields from verified, release-scoped catalogue evidence."""

import logging
import re
from collections import defaultdict
from functools import partial

import numpy as np
import xarray as xr

from frameit.core import metadata_catalogue as catalogue
from frameit.core.configuration import field_selection
from frameit.io.surfex_utils import SURFEX_FIELDS, _unit_identity
from frameit.processing.requests import _operation_units, native_field_group, source_field_metadata
from frameit.processing.wind_reference import _metadata_frames
from frameit.utils.diagnostics import format_message
from frameit.utils.units import UNITS, unit_metadata

_NATIVE_TRACKERS = {"pressure_centroid", "multifield_vortex"}


def _present(value):
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _equal(key, left, right):
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    if key != "units":
        return left == right
    left, right = _unit_identity(left), _unit_identity(right)
    return left == right or any(left in factors and right in factors
                                and factors[left] == factors[right]
                                for _, factors in UNITS.values())


def _binding_matches(required, observed):
    # A path template is reference evidence, never an actual runtime binding.
    return not isinstance(required, dict) and type(required) is type(observed) and (
        required == observed)


def _contradicted(key, required, observed):
    if key == "netcdf_group" and isinstance(required, dict) and isinstance(observed, str):
        template = required.get("path_template", "")
        prefix = template.split("{", 1)[0].rpartition("/")[0]
        return bool(prefix) and observed != prefix and not observed.startswith(prefix + "/")
    # An untyped assertion is unknown, not proof to discard an alternative.
    return type(required) is type(observed) and required != observed


def propose(rows, context, observed, missing, *, reject_unit=None, reject_standard_name=None):
    """Evaluate already exact-name candidates with verified context and joint attributes."""
    outcome = {
        "status": "unmatched", "proposed_values": {}, "unresolved_requirements": [],
        "supporting_record_ids": {},
        "record_ids": [row["id"] for row in rows],
        "withheld": [{"record_id": row["id"], "attribute": key, "reason": reason}
                     for row in rows for key, reason in row["completion"]["withheld"].items()],
        "evidence": [{"record_id": row["id"], "locators": row["source"]["evidence"]}
                     for row in rows if row["source"].get("evidence")],
    }
    if not rows:
        return outcome
    candidates = [row for row in rows if row["completion"]["candidate"]]
    if not candidates:
        outcome["status"] = "reference_only"
        return outcome
    if "namespace" not in context:
        outcome["status"] = "context_required"
        outcome["unresolved_requirements"] = [
            {"key": "namespace", "record_id": row["id"], "required": row["namespace"]}
            for row in candidates]
        return outcome
    candidates = [
        row for row in candidates if row["namespace"] == context["namespace"] and not any(
            key in context and _contradicted(key, need, context[key])
            for key, need in row["completion"]["identity"].items())
    ]
    if not candidates:
        outcome["status"] = "conflict"
        return outcome
    for row in candidates:
        for key, need in row["completion"]["requires"].items():
            if key not in context or not _binding_matches(need, context[key]):
                outcome["unresolved_requirements"].append({
                    "key": key, "record_id": row["id"], "required": need,
                    **({"observed": context[key]} if key in context else {}),
                })
    if outcome["unresolved_requirements"]:
        outcome["status"] = "context_required"
        return outcome

    known = {key: value for key, value in observed.items() if _present(value)}
    compatible = []
    for row in candidates:
        source = row["source"].get("metadata") or {}
        if any(_present(source.get(key)) and not _equal(key, value, source[key])
               for key, value in known.items()):
            outcome["withheld"].append({
                "record_id": row["id"], "attribute": "record", "reason": "observed_conflict"})
            continue
        corroborated = all(_present(source.get(key)) for key in known)
        if not corroborated:
            outcome["withheld"].append({
                "record_id": row["id"], "attribute": "record", "reason": "observed_unconfirmed"})
        # Lack of evidence is not a reason to remove a competing definition.
        compatible.append((row["id"], row["completion"]["values"] if corroborated else {}))
    if not compatible:
        outcome["status"] = "conflict"
        return outcome

    ambiguous, rejected = False, False
    ids = [record_id for record_id, _ in compatible]
    for key in missing:
        if key not in catalogue.COMPLETION_KEYS:
            continue
        values = [eligible.get(key) for _, eligible in compatible]
        if not any(values):
            continue
        value = values[0]
        if value is None or not all(_equal(key, value, other) for other in values):
            ambiguous = True
            outcome["withheld"].append({
                "record_ids": ids, "attribute": key, "reason": "candidate_disagreement"})
        elif key == "units" and reject_unit and (reason := reject_unit(value)):
            rejected = True
            outcome["withheld"].append({
                "record_ids": ids, "attribute": key, "reason": "unit_admission", "detail": reason})
        elif key == "standard_name" and reject_standard_name and (
            reason := reject_standard_name(value)
        ):
            rejected = True
            outcome["withheld"].append({
                "record_ids": ids, "attribute": key, "reason": "wind_basis_conflict",
                "detail": reason})
        else:
            outcome["proposed_values"][key] = value
            outcome["supporting_record_ids"][key] = ids
    values = outcome["proposed_values"]
    outcome["status"] = (
        ("partial" if len(values) < len(missing) else "proposed") if values else
        "conflict" if rejected else "ambiguous" if ambiguous else "reference_only"
    )
    return outcome


def _netcdf_identity(model, attrs):
    context = {"format": "netcdf", "netcdf_group": ""}
    if model == "mesonh":
        numbers = attrs.get("MNH_VERSION")
        if isinstance(numbers, np.ndarray):
            numbers = numbers.tolist()
        if isinstance(numbers, (list, tuple)) and len(numbers) == 3 and all(
            isinstance(value, (int, np.integer)) and type(value) is not bool and value >= 0
            for value in numbers
        ):
            context.update(producer=model, version=".".join(map(str, numbers)),
                           namespace="mesonh_netcdf_variable", version_evidence="MNH_VERSION")
        text = attrs.get("MNH_VERSION_STR")
        if isinstance(text, str) and (match := re.fullmatch(
            r"(?:Meso-NH\s+|MASDEV)?(\d+\.\d+\.\d+)", text.strip()
        )):
            if numbers is None:
                context.update(producer=model, version=match[1], namespace="mesonh_netcdf_variable",
                               version_evidence="MNH_VERSION_STR")
            elif "version" in context and match[1] != context["version"]:
                del context["version"], context["version_evidence"]
    elif model in {"croco", "nemo"}:
        versions = {
            match[1]: key for key in ("source", "producer")
            if isinstance(attrs.get(key), str) and (match := re.fullmatch(
                rf"{model}\s+(?:version\s+)?(\d+\.\d+(?:\.\d+)?)", attrs[key].strip(), re.I))
        }
        if len(versions) == 1:
            version, key = next(iter(versions.items()))
            context.update(producer=model, version=version, version_evidence=key)
        if model == "croco" and attrs.get("type") == "CROCO history file":
            context.update(producer=model, namespace="netcdf_variable_name",
                           output_backend="native_netcdf")
    return context


def _matches_field(request, reference, name, group):
    native, qualified, _ = field_selection(request, reference)
    return native == name and (qualified is None or qualified == group)


def _wind_name_rejection(source, field, group, attrs, standard_name):
    name = field["name"]
    claimed = _metadata_frames({"standard_name": standard_name}, name)
    if not claimed:
        return None
    try:
        recorded = _metadata_frames(attrs, name) + _metadata_frames(
            field.get("dataset_attributes", {}), "Dataset")
    except (ValueError, TypeError) as exc:
        return str(exc)
    recorded.extend(pair["basis"] for pair in source["declaration"].get("wind_pairs", ())
                    if any(_matches_field(source["requests"], pair[key], name, group)
                           for key in ("u", "v")))
    if any(frame != claimed[0] for frame in recorded):
        return f"{standard_name} implies {claimed[0]} winds; observed basis {sorted(set(recorded))}"
    return None


def _unit_rejection(source, name, group, attrs, packing, tracker, units):
    request = source["requests"]
    exports = request["exports"]

    def matches(reference):
        return _matches_field(request, reference, name, group)

    targets = set()
    pairs = source["declaration"].get("wind_pairs", ())
    croco_current = False
    for ref, operation in [
        *((ref, transform) for transform in request["transforms"] for ref in transform["fields"]
          if ref in exports.get("model_grid", ())),
        *((ref, request["polar_options"].get(ref, {})) for ref in exports.get("polar", ())
          if ref not in request["derived"]),
    ]:
        if matches(ref) and "units" in operation:
            targets.add(operation["units"])
        if operation.get("basis") == "earth" and any(
            ref in (pair["u"], pair["v"]) and any(matches(pair[k]) for k in ("u", "v"))
            for pair in pairs
        ):
            if source["model"] == "croco" and operation.get("sampling") == "mass":
                croco_current = True
            else:
                targets.add("m s-1")
    for ref in {ref for items in exports.values() for ref in items} & request["derived"].keys():
        if any(map(matches, request["derived"][ref]["inputs"].values())):
            targets.add("m s-1")

    tracker_quantity = None
    if tracker == "wind_pressure":
        if name in {"MSLP", "prmsl"}:
            tracker_quantity = "pressure"
        elif name in {"UM10", "VM10", "u10", "v10"}:
            tracker_quantity = "velocity"
    elif (tracker in _NATIVE_TRACKERS
          and name in source.get("tracker_support", {}).get("inputs", {})):
        return "The selected tracker checks native units for this field."
    if not targets and not croco_current and not tracker_quantity:
        return None
    probe = xr.DataArray(0., name=name, attrs={**attrs, "units": units})
    probe.encoding = dict(packing)
    try:
        for target in sorted(targets):
            _operation_units(probe, target, model=source["model"])
        if tracker_quantity:
            unit_metadata(probe, tracker_quantity)
        if croco_current:
            from frameit.io.croco_utils import _velocity

            _velocity(probe)
    except (ValueError, TypeError) as exc:
        return str(exc)
    return None


def _selector(name, field_id, groups, records, requests):
    by_name = records[name]
    group = groups[field_id]
    same_group = {identity for identity in by_name if groups[identity] == group}
    qualified = f"{group}.{name}"
    if (group in requests.get("groups", {}) and same_group == {field_id}
            and qualified not in records):
        return qualified
    # A literal dotted name can collide with the declaration for another field's group.
    prefix, separator, suffix = name.partition(".")
    if (by_name != {field_id} or separator and prefix in requests.get("groups", {})
            and any(groups[other] == prefix for other in records.get(suffix, ()))):
        return None
    return name


class CatalogueResolution:
    """Resolve selected metadata before its checks; keep original file metadata intact."""

    def __init__(self, resources):
        self.resources = resources
        self.headers = {}
        self.inventories = {}
        self.pending_trackers = {}
        self.index = None
        self.lookups = {}
        self.fields = []
        self.warnings = []
        self.unavailable = False

    def netcdf_header(self, source_id, path, model, attrs):
        self.headers[source_id, str(path)] = _netcdf_identity(model, attrs)

    def capture(self, source_id, source, identities, *, blocked=False, tracker=None):
        selected = [r for r in source["records"] if r["field_id"] in identities]
        seen = {_snapshot_key(r) for r in selected}
        self.inventories[source_id] = source, seen, tracker
        if tracker in _NATIVE_TRACKERS and not blocked:
            self.pending_trackers[source_id] = selected
        else:
            self._resolve(source_id, source, selected, tracker, blocked=blocked)

    def after_tracker(self, source_id, *, blocked=False):
        if selected := self.pending_trackers.pop(source_id, ()):
            source, _, tracker = self.inventories[source_id]
            self._resolve(source_id, source, selected, tracker, blocked=blocked)

    def observe_operation(self, source_id, candidates):
        source, seen, tracker = self.inventories[source_id]
        chosen = [record for sequence in candidates.values() for _, record in sequence]
        new = {_snapshot_key(r) for r in chosen} - seen
        if new:
            # Evaluate all selected records of a new field together, not one time at a time.
            identities = {identity for identity, _ in new}
            self._resolve(source_id, source,
                          [r for r in chosen if r["field_id"] in identities], tracker)
            seen.update(new)

    def _selections(self, source_id, source, chosen):
        by_name, groups, observations = defaultdict(set), {}, defaultdict(list)
        fields = source["fields"]
        chosen_names = {r["name"] for r in chosen if r["name"] is not None}
        group_names = chosen_names | {name.split(".", 1)[1] for name in chosen_names if "." in name}
        for record in source["record_inventory"]:
            name, field_id = record["name"], record["field_id"]
            if name is None:
                continue
            by_name[name].add(field_id)
            if name in group_names and field_id not in groups:
                try:
                    groups[field_id] = native_field_group(source, fields[field_id], record)
                except ValueError:
                    groups[field_id] = None
        seen = set()
        for record in chosen:
            name, field_id = record["name"], record["field_id"]
            path = record["locator"]["path"]
            if name is None or (field_id, path) in seen:
                continue
            seen.add((field_id, path))
            field = fields[field_id]
            selector = _selector(name, field_id, groups, by_name, source["requests"])
            attrs = record.get("observed_attributes", field["attributes"])
            valid = True
            try:
                metadata = source_field_metadata(source, field, record=record, use_catalogue=False,
                                                 check_native=True)
            except ValueError:
                valid = False  # Do not work around a rejected native declaration.
            else:
                if metadata is not None:
                    attrs = metadata["attributes"]
            observed = {key: attrs[key] for key in catalogue.COMPLETION_KEYS if key in attrs}
            identity = dict(self.headers.get(
                (source_id, path), {"format": record["locator"]["format"]}))
            if (source["declaration"].get("interpretation") == "mesonh_surfex_sea"
                    and name in SURFEX_FIELDS):
                # A verified host version says nothing about the embedded writer release.
                identity = {"format": "netcdf", "netcdf_group": ""}
            if native := record["locator"].get("variable"):
                identity["name"] = native
            elif record["locator"]["format"] == "fa" and not field.get("native_cube"):
                identity["name"] = name
            missing = [key for key in catalogue.COMPLETION_KEYS if not _present(observed.get(key))]
            observations[name, selector].append((
                record, identity, observed, missing, valid, attrs, groups[field_id]))
        for (name, selector), items in observations.items():
            if any(valid and ("units" in missing or missing and "version" in identity)
                   for _, identity, _, missing, valid, _, _ in items):
                yield name, selector, items

    def _lookup(self, identity):
        if not self.unavailable:
            try:
                if self.index is None:
                    self.index = self.resources.enter_context(catalogue.open_catalogue())
                key = tuple(identity.get(k) for k in ("producer", "version", "name", "namespace"))
                if key not in self.lookups:
                    self.lookups[key] = self.index.lookup(*key)
                return self.lookups[key]
            except catalogue.CatalogueError as exc:
                self.unavailable = True
                self._warn("W1307", f"Metadata catalogue unavailable: {exc}. "
                           "Use explicit source evidence for unresolved fields.")
        return []

    def _resolve(self, source_id, source, chosen, tracker, *, blocked=False):
        if not chosen:
            return
        resolved = {}
        for name, selector, items in self._selections(source_id, source, chosen):
            results = []
            for record, identity, observed, missing, valid, attrs, group in items:
                result = propose([], {}, {}, [])
                if not valid:
                    result["status"] = "conflict"
                elif not missing:
                    result["status"] = "complete"
                elif "version" not in identity:
                    result["status"] = "version_required"
                    result["unresolved_requirements"] = [{"key": "version"}]
                elif "name" not in identity:
                    result["status"] = "context_required"
                    result["unresolved_requirements"] = [{"key": "name"}]
                else:
                    reject_unit = partial(_unit_rejection, source, name, group, attrs,
                                          record.get("packing", {}), tracker)
                    reject_name = partial(_wind_name_rejection, source,
                                          source["fields"][record["field_id"]], group, attrs)
                    result = propose(self._lookup(identity), identity, observed, missing,
                                     reject_unit=reject_unit, reject_standard_name=reject_name)
                    if self.unavailable:
                        result["status"] = "unavailable"
                results.append({
                    "file": record["locator"]["path"], "native_identity": identity,
                    "observed_metadata": observed, "missing_attributes": missing, **result,
                })
            summary = _combine(source_id, name, selector, results, blocked)
            if values := summary.pop("proposed_values"):
                for record, *_ in items:
                    resolved[_snapshot_key(record)] = values
                summary["applied_values"] = values
                summary["status"] = ("applied" if len(values) == len(summary["missing_attributes"])
                                     else "partially_applied")
                attributes = ", ".join(f"{key}={value}" for key, value in values.items())
                self._warn("W1306", f"Metadata catalogue {catalogue.VERSION} supplied "
                           f"{attributes} for {source_id}.{selector or name}. "
                           "Input files and YAML were not changed.")
            else:
                summary["proposed_values"] = {}
            self.fields.append(summary)
        for record in chosen:
            if values := resolved.get(_snapshot_key(record)):
                record["catalogue_values"] = values

    def _warn(self, code, text):
        message = format_message(code, text)
        if message not in self.warnings:
            self.warnings.append(message)
            logging.getLogger(__name__).warning(message)

    def finish(self, facts):
        if self.fields:
            facts["metadata_catalogue"] = {
                "catalogue_version": catalogue.VERSION, "content_sha256": catalogue.CONTENT_SHA256,
                "fields": self.fields,
            }
        if self.warnings:
            facts["warnings"] = list(dict.fromkeys([*facts.get("warnings", ()), *self.warnings]))


def _snapshot_key(record):
    return record["field_id"], record["locator"]["path"]


def _combine(source_id, name, selector, results, blocked):
    first = results[0]
    summary = {key: value for key, value in first.items() if key != "file"}
    summary.update(source_id=source_id, field=name, selector=selector)
    if len(results) > 1:
        summary["records"] = results
        for key in ("native_identity", "observed_metadata"):
            summary[key] = {k: v for k, v in first[key].items() if all(
                k in record[key] and _same_fact(v, record[key][k]) for record in results)}
        for key in ("record_ids", "missing_attributes", "unresolved_requirements",
                    "withheld", "evidence"):
            summary[key] = []
            for value in (item for record in results for item in record[key]):
                if value not in summary[key]:
                    summary[key].append(value)
        values = {key: value for key, value in first["proposed_values"].items() if all(
            _equal(key, value, record["proposed_values"].get(key)) for record in results)}
        if values and any(
            key not in summary["native_identity"]
            for key in ("producer", "version", "name", "namespace")
        ):
            values = {}
            summary["withheld"].append({
                "attribute": "record", "reason": "per_file_identity_disagreement"})
        summary["supporting_record_ids"] = {
            key: sorted({record_id for record in results
                         for record_id in record["supporting_record_ids"].get(key, ())})
            for key in values}
        statuses = {r["status"] for r in results}
        summary["proposed_values"] = values
        summary["status"] = (("proposed" if len(values) == len(summary["missing_attributes"])
                               else "partial") if values else
                             first["status"] if len(statuses) == 1 and not first["proposed_values"]
                             else "conflict")
    else:
        summary["file"] = first["file"]
    if blocked or selector is None:
        summary.update(status="conflict", selector=None, proposed_values={},
                       supporting_record_ids={})
        summary["withheld"] = [*summary["withheld"], {
            "attribute": "record", "reason": "no_unambiguous_selector"}]
    return summary


def _same_fact(left, right):
    return type(left) is type(right) and bool(np.array_equal(left, right))
