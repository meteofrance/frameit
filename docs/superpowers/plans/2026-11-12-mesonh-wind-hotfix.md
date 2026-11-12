# Meso-NH Wind Metadata Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make incomplete Meso-NH projection headers actionable and support the approved explicit Earth-basis exception.

**Architecture:** Extend the shared wind declaration validator and projection resolver. Reuse the same narrow override policy in preflight, preparation, native export and tracking, preserving source attributes and recording the decision.

**Tech Stack:** Python 3.13, xarray, NumPy, pytest, Sphinx, existing GitHub CLI.

**Spec:** `docs/superpowers/specs/2026-11-12-mesonh-wind-hotfix-design.md`

## Global Constraints

- Use only Conda `frameit_env`, Python 3.13, compact synthetic fixtures and existing dependencies.
- Keep schema `2.1`, the existing numerical formula, defaults and output locations.
- No automatic fallback, inferred projection values or new scientific validation claims.
- Release tag `v2.0.0rc2-hotfix1`; package version `2.0.0rc2+hotfix1`.
- Preserve unrelated work and source datasets; do not merge or push `main`.

## Review Focus

- Partial YAML parameters: merge with source values; explicit zero must win.
- Invalid numbers/booleans/foreign rotation-method keys: fail, not bypass.
- Complete metadata, GRIB sources, wrong components and mixed basis evidence: remain fatal.
- Prepared and native outputs: consistent labels, original evidence, no repeated rotation.
- Header-only validation: never evaluate winds; retain override warnings in provenance.

---

### Task 1: Resolve parameters and the explicit missing-header exception

**Files:**
- Modify: `src/frameit/core/configuration.py`
- Modify: `src/frameit/processing/wind_reference.py`
- Modify: `src/frameit/processing/derived/wind.py`
- Modify: `src/frameit/core/preflight.py`
- Modify: `src/frameit/tracking/pressure_centroid_inputs.py`
- Test: `src/frameit/testing/numerical/test_request_selection.py`
- Test: `src/frameit/testing/numerical/test_wind_reference.py`
- Test: `src/frameit/testing/numerical/test_wind_preflight.py`

**Interfaces:**
- Consumes: existing explicit wind-pair dictionaries, source datasets, runtime configuration.
- Produces: `validate_pair_frame(ds, pair, conf=None) -> str` (compatible optional context), `rotation_angle(ds, conf, pair) -> xr.DataArray`, normalized wind fields and preflight records with inspectable decisions.

- [ ] Add tests for YAML roundtrip and rejection of invalid scalars, RPK outside [-1, 1], and projection parameters on other methods.
- [ ] Add numerical tests for all-missing actionable errors, partial YAML/source parameters, explicit-zero precedence and nonzero independently checked rotation.
- [ ] Add exception tests for coherent grid metadata with missing parameters, no rotation, source preservation, native metadata, prepared idempotence, strict complete/invalid/mixed/legacy/non-MNH cases.
- [ ] Add lazy preflight and tiny exported-NetCDF tests checking values, source evidence and recorded warnings without importing FrameIt to reopen outputs.
- [ ] Run the new focused tests in `frameit_env`; confirm they fail for the intended missing behavior.
- [ ] Implement parameter validation/resolution and the shared context-gated override. Update all callers and preserve existing prepared-field checks.
- [ ] Run focused tests and inspect the diff; all new and existing focused tests must pass.

### Task 2: Document, verify and publish the candidate

**Files:**
- Modify: `docs/source/troubleshooting.rst`
- Modify: `docs/source/task_guides/scalars_and_vectors.rst`
- Modify: `docs/source/user_guide/configuration_file.rst`
- Modify: `docs/source/polar_projection/scientific_qualification.rst`
- Modify: `docs/source/_static/configuration-reference.yaml`
- Modify: `pyproject.toml`, `src/frameit/_version.py`, `CITATION.cff`, `CHANGELOG.md`, `docs/test_release.py`

**Interfaces:**
- Consumes: tested behavior from Task 1.
- Produces: checked documentation, coherent release metadata, focused local commits, hotfix branch PR and GitHub prerelease.

- [ ] Update the release test to version `2.0.0rc2+hotfix1` and date `2026-11-12`; observe failure, then update metadata/changelog.
- [ ] Document parameter units/precedence, missing-data error, explicit Earth declaration, warning provenance and fatal boundaries beside each affected choice.
- [ ] Run focused and broader pytest regressions, package/dependency checks and review all task changes.
- [ ] Run `conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/mesonh-hotfix-01`.
- [ ] Run `conda run --no-capture-output -n frameit_env python docs/check_publication.py build/docs-preview/mesonh-hotfix-01` and publication-check unit tests.
- [ ] Start a loopback server through the background shell; inspect affected pages at desktop and 320px in the live GUI; retain server/tab details for handover.
- [ ] Review, stage only task files and commit verified changes. Push the hotfix branch and open a PR against `main`.
- [ ] Publish the requested GitHub prerelease/tag from the verified commit, reporting hosted-CI/review limitations and leaving `main` unchanged.

## Execution

Proceed inline as requested by the maintainer. The existing isolated worktree was
clean; focused baseline: 231 passed, 2 subtests passed. No extra workspace,
dependencies, speculative options or unrelated refactors are needed.
