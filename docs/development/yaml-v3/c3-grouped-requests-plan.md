# Optional C3 Groups Implementation Plan

> **For agentic workers:** Use `executing-plans` for the lead's tightly coupled
> implementation below. A fresh independent reviewer must approve the whole
> increment before commit; the existing main plan's review-before-commit rule
> overrides intermediate commits.

**Goal:** Select actual fields and independent native-axis levels within one
source, while preserving all existing flat requests and scientific safeguards.

**Architecture:** Extend the current source request handoff with optional local
groups; retain canonical field references as binding keys and native evidence
unchanged. Reuse the existing inventory, operation planner, selected-record
readers, product descriptors and writers.

**Tech Stack:** Python3.13 in `frameit_env`, pytest, existing xarray/ecCodes/
NetCDF/Zarr/polar dependencies, Sphinx. No installation/environment work.

**Spec:** `c3-grouped-requests-design.md` and the main plan's C1–C9 safeguards.

## Global constraints

- Flat `variables.3d` lists/source-wide levels remain unchanged.
- Grouped mode uses `names`/local `levels` and forbids source-wide levels.
- Group identity comes from native metadata; `group.field` is the explicit
  reference and stable grouped stored name.
- Keep raw source IDs/names/locators, clocks, masks, units, C7 coordinates,
  native W and magnitude-after-component-sampling.
- Preserve all partial Task16 work and evidence; no unrelated core fixes.
- No standalone plots/images, production runs, downloads, packages or full
  benchmark. Task16's one post-freeze full diagnostic remains separate.
- Commit locally after review; never push or merge.

## Review focus

- A requested name is ambiguous even when only one of its fields was declared:
  qualify it or fail, never infer identity from product filtering.
- Several identities share the same qualified group: fail before scientific
  reads; time repetition is not ambiguity.
- Different field groups have different local levels/units: select each
  representation independently without changing C7 coordinate identity.
- A qualified derived input is internal only: read only its actual selected
  support and compute polar speed after sampling, not before.
- A qualified name collides with another field/result/coordinate: fail, never
  overwrite or choose a filtering-dependent output name.

## A. Syntax and reference handoff

Files: `src/frameit/core/configuration.py`,
`src/frameit/core/settings_class.py`, shipped
`src/frameit/schemas/config-v3.schema.json`; new
`src/frameit/testing/numerical/test_grouped_requests.py`.

Interfaces: keep `resolve_schema`'s three-item return and all public signatures.
Grouped requests expose `fields["3d"]` as canonical references and a `groups`
mapping containing the declared local specs; flat requests need no new key.
Add `field_selection(request, reference)` in configuration, returning
`(raw_name, group_or_None, levels_mapping)` for internal shared consumers.
Add `_variable_fields(variables)` returning the two canonical field lists for
configuration, expected-variable reporting and runtime projections.

- [x] Write schema tests for both shapes, original height/pressure selections,
  qualified references across products/operations, deep-copy/idempotent
  projections, empty/malformed groups, duplicates and source-level exclusion.
- [x] Run `test_grouped_requests.py` and observe intended syntax failures.
- [x] Implement checked groups/reference handoff using existing `_names` and
  `_levels`; keep all flat behavior and source-name rules.
- [x] Extend authoritative editor definitions for the new shape and exclusion;
  regenerate the shipped JSON asset without installing a validator.
- [x] Run the new tests and `test_configuration_v3.py` plus the editor-schema
  generator-equality test in `test_v3_cli.py`.

## B. Metadata identity and representation binding

Files: `src/frameit/processing/requests.py`, `src/frameit/core/preflight.py`;
new grouped test module. No reader values are used to disambiguate.

Interfaces: add `field_candidates(source, request, reference, records_by_name)`
returning original `(inventory_index, record)` candidates. Reuse `_field_axis`/
`_vertical_axis` evidence, selecting native groups before transforms.
All bind/operation public signatures stay unchanged.

- [x] Add compact actual multi-axis GRIB tests, metadata-only payload guards and
  grouped NetCDF axis fixtures. Assert same-group ambiguity and competing
  providers still fail; unrelated duplicated names and repeated times do not.
- [x] Watch the focused tests fail at the actual missing identity boundary.
- [x] Use the shared candidate resolver during inventory, final binding,
  operation-input resolution, metadata declaration lookup and inspection.
  Apply local selectors per field, and the common vertically varying input
  selector to derived results; reject different derived input selectors.
- [x] Preserve dependency support, selected-time constraints, provider checks,
  failed-rebind clearance and explicit destination-grid behavior.
- [x] Run grouped tests plus `test_request_selection.py`,
  `test_grid_representations.py`, `test_grib_lifecycle.py`,
  `test_inspect_metadata.py`, and relevant operation/polar/report tests.
  Record unrelated existing failures, not blanket exemptions.

## C. Selected-reader execution and output identity

Files: `src/frameit/io/grib_utils.py` closed-inventory name check,
`src/frameit/io/fa_utils.py` post-admission scientific-array naming,
`src/frameit/io/netcdf_utils.py` original-name provenance; output assembly only
if the actual tests demonstrate another reference-vs-native-name assumption.
Review fix1 also adapts canonical/native keys at the existing CROCO preparation
boundary in `src/frameit/processing/derived/wind.py`, without changing result merging.
Tests are in the new grouped module and relevant existing reader/output modules.

Interfaces: binding/product keys are references; each bound record keeps its
actual `name`/`field_id`/native locator. Readers use native locators for reads
and name the constructed result with its binding reference. Output descriptor
and stored-name mappings remain stable.

- [x] Add a real end-to-end multi-axis GRIB test with source hashes, selected
  decoder calls, distinct values/zero/NaN, singleton levels, export filtering
  and ordinary-reader assertions. Add grouped NetCDF/W and qualified derived/
  transform/polar input checks without changing existing fixture assertions.
- [x] Observe the intended downstream failures before changing those callers.
- [x] Fix only demonstrated name-key assumptions; preserve adapter scientific
  checks, native identity provenance, C7 coordinates and existing encodings.
- [x] Run the new end-to-end tests and connected reader/output/operation/polar
  tests, with exact pass/failure/node records.

## D. Documentation, independent review and local commit

Files: canonical `task_guides/field_selection.rst`,
`user_guide/configuration_file.rst`, `user_guide/output_files.rst` and
`reference/all_keys.rst` under `docs/source`; internal C3 contracts/state/evidence.
Do not stage unrelated partial Task16 producer/prose changes.

- [x] Teach both request shapes, qualification, reference spelling, derived
  selector inheritance, collision handling and actual stored names. Keep the
  small examples flat; label grouped fragments supplementary.
- [x] Run focused/connected tests, Ruff no-new comparison and `git diff --check`.
- [x] Run strict Sphinx, `docs/check_publication.py` and the13 publication
  unittests in `frameit_env`; inspect affected live HTML using text-only DOM
  desktop/narrow checks, retaining the preview.
- [ ] Obtain a fresh independent spec/quality review of actual diff, tests,
  evidence and documentation. Fix concrete findings and verify each closure.
- [ ] Review/stage only C3 paths, verify the partial Task16 work remains intact,
  commit locally and record the SHA/effective handoff. Do not claim full
  Task16/native/wheel/schema-standards/HPC/human acceptance.

Command prefix for Python/tests:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env
```

Self-review: all design sections map to A–D; no new planner, method or dependency.
The downstream file list will be narrowed to demonstrated consumers by the
read-only trace before C begins. These are steps of one independently reviewed
deliverable, not permission to commit a partially executable extension.

Review02 found four Important gaps; scoped closure of shared C7-axis identity,
independent generated tracker support, qualified CROCO preparation and FA error
reporting is required before the last two boxes above can be checked. Preserve
authorship of explicit operation inputs when handing their selectors to the
existing input binder; they are not automatically generated tracker support.
