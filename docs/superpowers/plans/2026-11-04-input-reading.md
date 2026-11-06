# Shared Input Reading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate measured redundant input work without changing scientific results.

**Architecture:** Reuse lazy raw NetCDF datasets through the existing resource
owner, including runtime preflight. Build native Cartesian groups only when
selected. Preserve independent per-file scientific preparation.

**Tech Stack:** Python 3.13, xarray, Dask, h5netcdf/netCDF4, pytest.

**Spec:** `docs/superpowers/specs/2026-11-04-input-reading-design.md`

## Global Constraints

- Use Conda `frameit_env` with Python 3.13; add no dependencies.
- Keep inputs read-only and generated profiles/products outside the repository.
- Retain the current input engine, chunk defaults, public YAML and output schema.
- Preserve all per-file scientific checks and resource cleanup, including failure.
- Work in the current checkout; preserve unrelated `opencode.json`; never push.

## Review Focus

- Different engine/chunk settings must not share an incompatible lazy dataset.
- Failed loading and subsequent retry must not retrieve a closed cache entry.
- Standalone metadata inspection must close handles without reading field cubes.
- Variable shards and model-specific clock/formula checks must remain intact.
- Native winds and the internal mass-W sidecar must remain available when used.

---

### Task 1: Reuse managed NetCDF opens

**Files:** `src/frameit/io/loader.py`, `src/frameit/io/netcdf_utils.py`,
`src/frameit/core/preflight.py`, `src/frameit/core/runner.py`;
tests in `src/frameit/testing/numerical/test_netcdf_assembly.py`.

**Interfaces:** Add `DatasetResources.open_netcdf(path, *, engine, chunks=None)`;
allow `preflight(..., resources=None)` and `open_metadata(..., chunks=None)`.
Existing direct callers retain their ownership and defaults.

- [x] Write parameterized tests using real compact Meso-NH/AROME/NEMO/CROCO files:
  `runner.load_dataset()` opens each path once, selected values/masks remain exact,
  source chunks are retained and unrequested payloads are never evaluated.
- [x] Add lifecycle tests: closing then reopening reads a changed fixture;
  failure rollback closes newly opened handles and allows a clean retry;
  distinct engine/chunk requests remain separate; standalone preflight closes.
- [x] Run the new tests and observe failures from redundant opens/missing reuse.
- [x] Implement the owner-local cache; route NetCDF opens through it, replacing
  discovery context managers that would close shared originals. Share the runner
  resource owner with runtime preflight, using configured chunks for that path.
- [x] Run `conda run -n frameit_env python -m pytest -q` on the changed test file
  and the existing ocean, wind, configuration and metadata-only regressions.

### Task 2: Avoid unused native Cartesian preparation

**Files:** `src/frameit/core/runner.py`;
tests in `src/frameit/testing/numerical/test_netcdf_assembly.py`.

**Interfaces:** Pass `native_output_groups=None` unless native Cartesian output
is selected. Keep the existing dictionary available to coupled consumers.

- [x] Test both representations with real scalar/vector fixtures: the selected
  output values remain correct; unused native groups are not constructed.
- [x] Observe the unused-branch test fail before changing the runner.
- [x] Pass the selected native-group destination consistently to all loaders.
- [x] Run native-grid, wind-collocation, FA/GRIB and coupled regressions.

### Task 3: Measure and hand over

**Files:** `docs/development/input-reading.md`,
`docs/source/user_guide/input_files.rst`, `CHANGELOG.md`, this plan.

- [x] Repeat the same fresh-process BATSIRAI cases with both installed readers;
  keep profiling instrumentation separate from unprofiled timing comparisons.
- [x] Reopen baseline/new products without importing FrameIt; compare exact
  decoded values and scientific metadata, and verify original source windows.
- [x] Report median timing, RSS, logical reads and OS-cache limitations; document
  existing reader/chunk tuning without claiming all-model real-data speedups.
- [x] Run the full `conda run -n frameit_env python -m pytest -q`, relevant docs
  checks, review task-only diffs, and commit locally without pushing.

Final verification: 1006 tests and two subtests passed; 46 assembly tests passed
again after formatting. Both input readers passed exact baseline/source-window
comparisons. The actual CLI smoke run and fresh-context code review passed.
HTML builds with two existing unrelated tracker warnings; strict `-W` therefore
remains nonzero. Implementation commit: `ecc9ada`; no merge or push requested.
