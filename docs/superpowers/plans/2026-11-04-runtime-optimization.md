# Runtime optimization and GRIB investigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the qualified performance-audit improvements, then diagnose the native GRIB shutdown failure and assess EPyGrAM on measured speed and compatibility.

**Architecture:** Retain the existing input adapters, ESMF interpolation weights, scientific policies and output contracts. Remove redundant work at shared boundaries; retain spawned export and disposable native-reader isolation. Backend replacement is conditional, not a goal in itself.

**Tech Stack:** Python 3.13 in `frameit_env`; NumPy, SciPy CSR/cKDTree, xarray, Dask, existing NetCDF/Zarr writers, cfgrib/ecCodes and installed EPyGrAM.

**Spec:** User's request following the read-only performance audit; measurements/prototypes retained under `/tmp/opencode/frameit-performance-audit/`. The user previously requested direct execution ("dive in"); implementation choices below are agent choices, not scientific approvals.

## Global Constraints

- Use Conda `frameit_env` with Python 3.13; no dependency/environment upgrade.
- Preserve scientific equations, interpolation weights, masks, first-storage-index ties, metadata, output schemas and configuration defaults.
- Keep diagnostics optional, source files read-only, concurrency capped and native libraries isolated.
- No persistent native service, global input cache, automatic backend fallback or hidden approximation.
- Preserve unrelated `opencode.json`; commit only task-related files locally; never push.
- Use compact regressions and the existing bounded BATSIRAI selection; distinguish warm-cache engineering measurements from general scientific validation.

## Review Focus

- Dask spatial chunks and multiple leading dimensions must remain lazy and retain coordinates without unbounded leading-axis rechunking (task 1).
- Empty/failed exports must close a shared pool and preserve atomic per-product publication (task 2).
- Wrapped longitudes, nonfinite geography and exact distance ties must retain legacy selections (task 3).
- Mixed ascending/descending native columns, exact vertical endpoints and local all-NaN tracking windows must preserve failure/fallback rules (task 4).
- Native cleanup, corrupted transfers and selection culling must not be weakened to amortize startup (tasks 5–6).

## Task 1: Batched polar weight application

**Files:** `src/frameit/processing/polar/coverage.py`, `regrid_plan.py` in the same directory; `src/frameit/testing/numerical/test_polar_coverage.py` and existing plan tests.

**Interfaces:** Preserve `SupportedRegridder.apply(field, mask=None, *, policy=None, minimum_support=None, output_chunks=None)` and its value/support/status tuple. Retain compatibility attributes used by current tests/callers; account for retained CSR storage in `PolarRegridPlan.estimated_bytes`.

- [ ] Add a regression prohibiting the three xESMF application calls while comparing batched, labelled, transposed, masked and spatially chunked inputs against independent weighted sums; cover strict/renormalized thresholds and unmapped rows.
- [ ] Run that regression and observe failure on the current implementation.
- [ ] Apply the normalized ESMF weights through batched CSR in `xr.apply_ufunc`; preserve leading chunks and requested output chunks, no eager payload reads during graph construction.
- [ ] Run `conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_polar_coverage.py src/frameit/testing/numerical/test_polar_regrid_plan.py` (discover actual plan-test filename before running).
- [ ] Review the diff and commit the polar optimization after passing targeted checks.

## Task 2: Reuse the isolated export pool

**Files:** `src/frameit/io/netcdf_export.py`; existing export/HPC execution tests.

**Interfaces:** Preserve `write_group_dict` and `export_outputs` outputs/defaults; an internal optional executor may be passed between the two. Keep the existing synchronous option unchanged.

- [ ] Add a regression asserting one spawned executor for combined Cartesian/polar export, resource-budget initialization, no executor for synchronous/empty export, and propagated writer failure with cleanup.
- [ ] Run the new test and observe the current two-pool failure.
- [ ] Share one context-managed, resource-capped spawn pool across the two phases without concurrent scientific transformations or altered output paths.
- [ ] Run export, Zarr and HPC regression tests, including ordinary-reader output reopening.
- [ ] Review the diff and commit the export optimization.

## Task 3: Reuse a squared-degree geographical index

**Files:** `src/frameit/tracking/geographic.py`; geographical/fixed/prescribed/coupled lookup regressions.

**Interfaces:** Keep `nearest_grid_point` as the one-point reference and preserve native FA projected lookup. Build a local reusable index only for repeated non-native 2-D lookups in `locate_track`.

- [ ] Add oracle comparisons for random positions, seam/wrapped longitudes, transposed axes, missing coordinates, duplicate/equidistant cells and invalid queries; assert repeated queries do not rescan the whole grid.
- [ ] Run the efficiency regression and observe failure.
- [ ] Use installed SciPy cKDTree as a candidate locator; re-evaluate candidates with the original arithmetic and select the first storage index, using a legacy scan when the index cannot safely represent an input.
- [ ] Run lookup and coupled-grid regression tests and the retained 300-position bounded benchmark.
- [ ] Review the diff and commit the geographical optimization.

## Task 4: Avoid redundant tracker work

**Files:** `src/frameit/tracking/pressure_centroid.py`, `PressureWind_Tracker.py`; native centroid and pressure-wind tests.

**Interfaces:** Preserve `interpolate_to_height(rec, height=HEIGHT_M)` and `pressure_wind_tracker(...)` return values and failure/fallback behavior. Only native columns already validated as monotone bypass sorting.

- [ ] Add native interpolation tests prohibiting `argsort` while comparing mixed orientation, missing columns, endpoint/extrapolation, invalid pressure and legacy unsorted records to known/reference results; run to observe failure.
- [ ] Gather native brackets directly and compute log-pressure at the two selected samples; retain the legacy sorting path.
- [ ] Add a counted-lazy-read test for tracking windows, including local all-NaN/global fallbacks and all-NaN failure; observe redundant reads before changing code.
- [ ] Load only each selected search/refinement window once, and load global fields only when the existing fallback needs them.
- [ ] Run both tracker suites and retained vertical/wind benchmarks; review and commit.

## Task 5: Qualify bounded FA batching

**Files:** Inspect `src/frameit/io/fa_utils.py`, `fa_backend.py`, `fa_worker.py` and native-selection/resource tests before deciding the production boundary.

**Interfaces:** Existing per-record declarations, freshness checks, payload limits, descriptor/NPY validation, diagnostics and disposable-child lifetime are mandatory.

- [ ] Determine whether a small batch can be integrated without decoding lazily unselected records, increasing full-domain residency or weakening per-record checks.
- [ ] If so, add a failing process-count/selection/resource regression, implement the narrow batch transaction, and run all FA lifecycle/selection regressions before committing.
- [ ] If not, record the concrete blocker and retain current safe behavior rather than ship the disposable probe as production code.

## Task 6: Native GRIB root cause and EPyGrAM comparison

**Files:** `src/frameit/io/grib_utils.py`, relevant reader/dependency initialization paths and fresh-process regressions; investigation scripts outside the repository; concise results in `docs/development/runtime-optimization.md`.

**Interfaces:** Current GRIB groups, vertical/time selection, masks, wind metadata and resource ownership remain the compatibility contract. EPyGrAM FA initialization is FA-only and must not be repurposed in the parent.

- [ ] Reproduce the retained unmodified SIGABRT; reduce imports, reads and cleanup independently to locate the corrupting native boundary, recording library identities and versions.
- [ ] Form and test one root-cause hypothesis at a time; add a fresh-process failing regression before a production fix.
- [ ] Benchmark installed EPyGrAM GRIB inventory/selection/decode/cleanup against cfgrib using equal requested fields/levels and fresh processes; compare values, masks, geometry, times and metadata.
- [ ] Replace only if a bounded compatible implementation is measurably faster; otherwise retain cfgrib and document the evidence and remaining limitations.
- [ ] Run relevant regressions, the full `conda run -n frameit_env python -m pytest -q`, bounded polar pipelines and independent-reader comparisons. Run changed-file import lint and `git diff --check`.
- [ ] Review all changes, commit fixes/results locally, and report exact commands/results, commit IDs and unresolved limits without claiming scientific sign-off.
