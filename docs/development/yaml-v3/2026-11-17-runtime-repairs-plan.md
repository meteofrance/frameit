# Retained runtime failures implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement
> this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Repair the 26 regressions retained by the full-suite audit without
weakening numerical, mask, clock, optionality or source-read-only checks.

**Architecture:** Repair the existing inventory, association, sampling and
provenance boundaries. Keep exact xarray merges; never resolve conflicting
scientific coordinates with overrides or by deleting their provenance.

**Tech stack:** Existing Python 3.13 / `frameit_env`, pytest, xarray, native
FA/GRIB readers and installed polar backend. No dependency changes.

**Spec:** `CHECKLIST_FOR_AGENTS.md`, C2/C5/C6/C7/C9;
`2026-11-17-full-suite-audit.md`; maintainer's “Proceed” and explicit
17 November choice of geographic trajectories with per-grid provenance, followed
by authorization to commit and merge locally into `develop` after a green suite.

## Design and approaches

Use shared runtime repairs, not looser tests, skips or expected failures.
The maintainer chose geographic trajectories over restoring legacy track index
fields: preserve exact native-index/snapping expectations in per-grid provenance
and correct conflicting output guidance. This is not a change to lookup methods.
For other repairs, retain existing numerical methods, units, masks, sample clocks,
defaults and rejection policies.

## Global constraints

- Use `frameit_env` with Python 3.13 for all Python checks/builds.
- No installations/environment repairs, production/HPC runs, benchmark campaigns,
  or push. The reserved full-diagnostic campaign remains unused.
- PNG smokes run only in unfiltered suites; never view their generated images.
- Preserve the approved nine-payload fixture and existing documentation preview.
- Commit only task-related, verified changes locally.
- The maintainer authorized autonomous completion until 18 November 2026,
  06:00 UTC+4 (02:00 UTC), and explicitly confirmed screenshots are unavailable.
- Merge into local `develop` only after a green full suite and local commit.
  Preserve other worktrees/branches; rerun the full suite on the merged result.

## Review focus

1. Face geography without CF standard names must retain its own samples/units.
2. Sampled horizontal auxiliaries must follow moving-target times, not merge as
   invariant coordinates; untouched leading auxiliaries must stay untouched.
3. CROCO current records must describe actually validated/executed preparation;
   scalar-only extraction must not invent current processing.
4. Common association must not admit a centroid operation with one actual time,
   nor shorten independent source inventories silently.
5. FA snapping facts must remain source/grid-qualified, with physical units and
   the original continuous centres; ordinary readers need no FrameIt import.

## Execution

The unchanged 26-node reproduction is red: 26 failures, no errors/skips,
`/tmp/opencode/frameit-runtime-red-20261117.{log,xml}`.
Focused commands below use the audit's environment prefix (absolute source
`PYTHONPATH`, approved fixture, one native thread, Agg, `/tmp/opencode`).

### Task 1: Native geography admission

Files: `src/frameit/core/preflight.py`, `src/frameit/core/coupled.py`;
tests: `src/frameit/testing/numerical/test_grid_representations.py`.
Interface: preserve `_native_grid`, `_netcdf_inventory`, `_region_grid` signatures.

- [x] Retain the eight existing red native-face regressions.
- [x] Admit conventional `latitude_u/v` and `longitude_u/v` consistently in
  inventory/metadata classification and regional coordinate selection.
- [x] Run the complete grid-representations and native-extraction modules;
  compare actual native field values, coordinates, units, masks and basis.

### Task 2: Moving polar auxiliary clocks

Files: `src/frameit/processing/polar/metadata.py`;
tests: `test_native_extraction.py`, `test_coupled_shared_polar.py` and connected
polar/FA modules under `src/frameit/testing/numerical/`.
Interface: preserve `restore_auxiliaries(result, leading, transformed)`.

- [x] Add a red compact regression combining two sampled horizontal auxiliary
  coordinates with different values and one time label each; require values
  `[1.5, 2.5]` on the corresponding times, physical metadata and exact merges.
- [x] Retain a sample's time dimension on its transformed horizontal auxiliaries.
  Do not interpolate or modify untouched scalar/vertical metadata.
- [x] Run the seven existing FA merge regressions plus connected polar metadata,
  eager/lazy, support, masks and ordinary-reader checks.

### Task 3: Provenance and status propagation

Files: `src/frameit/io/croco_utils.py`,
`src/frameit/processing/derived/wind.py`, `src/frameit/core/coupled.py`,
`src/frameit/core/execution.py`; tests: existing CROCO/FA pipeline modules.
Interfaces: existing preparation signatures and named-source run manifest.

- [x] Strengthen red current provenance checks for actual mask authority,
  original units, no extrapolation and no motion subtraction; require no current
  record for scalar-only work.
- [x] Reuse the existing current record definition at actual current preparation,
  preserve actual input identifiers, and publish child current records by source.
- [x] Publish retained unmapped native GRIB records with their field attributes
  and record locators; verify the deliberately unknown second message remains
  inspectable and is not exported as a physical field.
- [x] Copy actual time-association/common-target records to status when present,
  rather than guarding on retired configuration structure.
- [x] Run current/vector/support and FA pipeline/run-state regressions.

### Task 4: Centroid operation-time admission

Files: `src/frameit/core/coupled.py`;
tests: `test_croco_mnh_coupling.py`, `test_nemo_arome_coupling.py`.
Interface: preserve `_prepare_v3_regions(conf, children, plans)` and native
selected times; validate the association used by the tracker.

- [x] Retain both red `one_common_time` cases.
- [x] Require at least two distinct associated operation times for the existing
  pressure-centroid method and record the actual operation count.
- [x] Run positive two-time centroid and all invalid-input cases for both models.

### Task 5: FA per-grid mapping facts and guidance

Files: `src/frameit/core/coupled.py`,
`src/frameit/testing/numerical/test_fa_mapping.py`,
`docs/source/user_guide/{fa_geometry,output_files}.rst`.
Interface: extend `_region_facts`' per-grid report with actual lookup convention,
selected geography, offsets and units; no new universal trajectory index fields.

- [x] Move both exact mapping assertions to per-grid provenance, retaining the
  same expected indices (`5,3` and independent atmosphere `3`/surface `5`),
  offsets (`499.99 m`, `100 m`) and tolerances; require geographic track values.
- [x] Observe the missing per-grid snapping record fail before adding it.
- [x] Preserve mapped lookup facts in per-grid provenance and update canonical
  guidance to agree with the maintainer's geographic-trajectory choice.
- [x] Run all mapping/replay/region regressions with ordinary readers.

### Task 6: Verification, review and local handover

- [x] Run connected modules and inspect any assertions newly reached.
- [x] Obtain a fresh bounded read-only review and resolve verified findings.
  The review identified a real C7 defect: polar preparation must not replace a
  native grid description with operation-local metadata under the same grid ID.
  Preserve the existing native reader; add native-only/polar-enabled invariance
  checks, keep native inventory authoritative, and verify unchanged collocation,
  coordinates, indices, values, units and basis before the full suite.
- [x] Run strict Sphinx/publication checks in `frameit_env`; inspect affected
  rendered pages in the live GUI at desktop/narrow widths and retain the preview.
- [x] Verify approved fixture checksums before and after the final unfiltered
  `python -B -m pytest -q --junitxml=...`; inspect all failures/counts/warnings.
- [x] Review diff/status, whitespace and introduced lint diagnostics; record
  exact evidence, compatibility limits and preview ownership in development notes.
- [ ] Make focused local commits after a green full suite.
- [ ] Merge into local `develop` in its existing clean worktree; verify the
  merged result with the unfiltered full suite. Do not push or delete host-owned
  worktrees/branches. Report resulting commits and verification.
