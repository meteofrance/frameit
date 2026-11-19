# FA Projection Radius Default Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admit supported projected FA without a radius declaration when the documented model default agrees with the input.

**Architecture:** Pass the explicit or standard radius to the isolated EPyGrAM worker. Resolve the effective Earth model at the geometry boundary; use its existing facts for warnings, CF geometry and provenance.

**Tech Stack:** Python 3.13, EPyGrAM 2.1.0, pyproj, xarray, pytest, Sphinx.

**Spec:** [FA projection radius default](../specs/2026-11-19-fa-radius-default-design.md)

## Global Constraints

- Use `frameit_env`. Preserve FA header, projection, layout and decoder checks.
- No fitted radius, undeclared field meanings or changes to other formats.
- Preserve historic runs and unrelated work. Do not advance `develop` unless full verification is green.

## Review Focus

- Both native FA profiles must give the same coordinates and values as an explicit standard radius.
- A nonstandard file must reject the default and work with a matching explicit override.
- Wrong explicit declarations, native point limits and angular-only grids remain unchanged.
- Warn once per affected source and record the radius and origin in the ordinary run manifest.
- File eligibility and field declarations remain independent of the radius decision.

## Task 1: Resolve and report the FA model radius

**Files:** `src/frameit/io/{fa_contracts,fa_geometry,fa_worker,fa_epygram,fa_utils}.py`,
`src/frameit/core/{coupled,preflight}.py`, `src/frameit/testing/fa_fixture.py`,
`src/frameit/testing/numerical/{test_fa_geometry,test_fa_epygram_geometry}.py`.

- [ ] Add `test_projected_radius_default_matches_explicit` for both profiles.
  Compare reopened NetCDF coordinates, values and CF `earth_radius` exactly;
  check the warning and per-input provenance (`earth_radius_m == 6371229.0`).
  Use an alternate radius fixture to verify rejection and explicit override.
- [ ] Run `conda run --no-capture-output -n frameit_env python -B -m pytest -q src/frameit/testing/numerical/test_fa_epygram_geometry.py -k 'radius_default'`.
  Expect rejection of defaulted projected geometry before the change.
- [ ] Resolve `earth_model(radius, *, projected)` in `fa_geometry.py`: return
  the request radius and origin, conditional standard radius, or unresolved
  angular model. Use it in the worker geometry contract and parent check.
  Keep the worker and subsequent reads on the same radius; retain original
  corner checks. Surface default use through the preflight warning list and
  export actual model facts, not the authored null.
- [ ] Run the geometry tests and nearby FA pipeline tests. Expect all green.

## Task 2: Document, verify, and integrate

- [ ] Cover integrated-branch review regressions: track exact stationary AROME
  NetCDF shards without losing their leads; reject support with a different
  reference calendar; report current FA warnings once and archive binding
  warnings in run provenance. Keep angular corner diagnostics radius-independent.
- [ ] Update README and the canonical FA input/configuration guidance with
  scope, precedence, attribution and failure behavior. Run a strict Sphinx
  build and publication check; inspect the live desktop and narrow preview.
- [ ] Run unfiltered `python -B -m pytest -q`, documentation checks and
  `python -B -m frameit.testing.polar_qualification` in `frameit_env`. Use fresh
  evidence locations and the supported CI fixture; keep archived runs intact.
- [ ] Review the diff against the approved scope. If all checks pass, commit
  only the task changes. Fast-forward `develop` to the tested revision if local
  and remote ancestry still allow it; preserve its existing unstaged edit.
  Push only `develop` and check the resulting remote revision.
