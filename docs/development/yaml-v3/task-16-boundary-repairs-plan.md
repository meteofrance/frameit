# Task16 Boundary Repairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans inline.
> The maintainer explicitly requested autonomous continuation without questions.

**Goal:** Express the three preserved Task16 contracts without relaxing defaults.

**Architecture:** Extend existing source/polar field declarations and carry
per-file wind evidence through the existing inventory. Keep real physical
records separate from permitted output missingness and reuse unit conversion.

**Tech Stack:** Existing Python 3.13 frameit_env, xarray, Dask, ecCodes,
NetCDF and current optional polar backend; no installations.

**Spec:** `task-16-boundary-repairs-design.md`, the producer contract and
`CHECKLIST_FOR_AGENTS.md`, particularly C1–C10 and Tasks16–21.

## Global Constraints

- Preserve strict/native defaults, original scientific fixtures and tolerances.
- No compatibility aliases, scientific substitutions or fabricated input records.
- No source mutation, installation/environment repair, production/cluster run,
  benchmark campaign or standalone image/plot/screenshot check.
- Keep current public and shared-helper signatures.
- Use source-selected frameit_env and fresh evidence/output destinations.
- Review before local implementation commits; never push.

## Review Focus

- Initial absence must not hide later/partial-level or dependency failures.
- A selected source clock must not be shortened by field-level absence.
- Units overrides must not leak into unselected products or derived winds.
- Per-file opposing metadata must survive identical-field deduplication privately.
- Failed preparation must not create a successful manifest or mutate inputs.

### Repair 1 — Per-file inspection evidence

**Files:** `core/preflight.py`, existing `test_inspect_metadata.py`.
**Interfaces:** `_netcdf_inventory(path, source, resources)` returns narrow
`dataset_attributes`; `inventory_source(conf, name, resources=...)` publishes
them on their owning file entries.

- [ ] Run the existing guarded missing-context regression and observe RED.
- [ ] Reuse `inspect_wind_metadata({}, ds.attrs)` to retain only its dataset
  allowlist; copy it to the corresponding file entry, not field identity.
- [ ] Run the complete inspection metadata module and relevant v3 report tests.
  Expected: the prior missing-context assertion passes, no payload/privacy
  regressions; unchanged scientific interpretation.

### Repair 2 — Explicit polar base-field units

**Files:** `core/configuration.py`, `schemas/config-v3.schema.json`,
`processing/requests.py`, `processing/polar/polar_proj.py`,
`numerical/test_configuration_integration.py`, a focused boundary test module.
**Interfaces:** existing field-options mapping admits `units`; bound polar base
operations record requested/result units, execution uses `_operation_units`.

- [ ] Add explicit polar `UM10`/`VM10` m/s options to the existing unchanged
  36km/h integration input and observe RED before implementation.
- [ ] Add incompatible-unit/default/inactive-isolation checks on compact inputs.
- [ ] Validate the syntax and metadata, convert only requested base-field values,
  regenerate the existing schema asset with its existing mechanism.
- [ ] Run focused tests and the original integration assertion. Expected:
  36km/h becomes10m/s only where requested; default base units stay native;
  speed/radial/tangential definitions, masks and tolerances stay unchanged.

### Repair 3 — Explicit initial absent records

**Files:** `core/configuration.py`, schema asset, `core/preflight.py`,
`processing/requests.py`, selected GRIB/NetCDF assembly as necessary,
`testing/catalog.py`, current consumers and compact boundary tests.
**Interfaces:** `sources.<name>.allow_initial_gaps` lists selected references;
actual missing contexts are recorded separately and used for output alignment.

- [ ] Build compact selected-record tests for one initial absent scalar and a
  layered field; retain real clocks/records. Observe RED.
- [ ] Pin undeclared/later/partial-level/dependency failures and source immutability.
- [ ] Admit only declared initial complete-field absences at inventory/binding,
  preserve strict required method support and real-record read guards.
- [ ] Align permitted missing output samples lazily, with no invented source
  records, zero fill, interpolation in time or source rewriting.
- [ ] Consume the catalogue's original explicit gap list directly in v3.
  Expected: original fields, times and levels remain unchanged and the ordinary
  reader sees missing first samples plus unchanged later physical values.

### Integration, documentation and continuation

- [ ] Finish remaining direct-v3 producer/caller conversions with original IDs,
  quantities, clocks, missingness, benchmark motion and helper APIs preserved.
- [ ] Document the two opt-ins and descriptive per-file inspection in canonical
  configuration/input guidance and reference comments.
- [ ] Run focused connected lanes and the exact Task16 nine-file command.
- [ ] Strict Sphinx/publication/live text checks; no prohibited image checks.
- [ ] Freeze the actual Task16 tree, run its one full diagnostic, audit causes/
  assertion history, obtain fresh bounded review, resolve findings and commit.
- [ ] Continue Tasks17,18,19,20,21 in the existing approved plan; record restricted
  or human-only evidence as missing instead of asserting acceptance.

Self-review: each scope has a RED/positive/default/failure check; existing
signatures are retained; no new diagnostic or independent scientific approval
is claimed. Implementation proceeds inline under the explicit autonomy request.
