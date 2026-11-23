# Optional Polar Kind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement inline. Steps use checkbox syntax for tracking.

**Goal:** Make polar sampling independent of the presence of `kind`.

**Architecture:** Bind the effective interpolation in the existing polar
planner, with numeric eligibility checked independently. Delete the adapter
backfills and their reporting rather than introducing a replacement classifier.

**Tech Stack:** Python 3.13, xarray/xESMF, pytest, Sphinx.

**Spec:** [Polar sampling does not require field kind](../specs/2026-11-23-optional-polar-kind-design.md)

## Global Constraints

Use `frameit_env`; do not add dependencies or change FA, wind, time, geometry
or mask contracts. Commit on a temporary local branch from `develop`, then
fast-forward `develop` and push only that branch.

## Review Focus

- Unlabeled integer interpolation must retain fractional values.
- Later selected records must not bypass numeric checks; unused times need not pass them.
- A partly unlabeled wind pair must still match interpolation and use joint masks.
- Co-exported native fields and synthetic initial gaps must not acquire kind from polar sampling.
- Categorical flags still select nearest, and known categorical inputs cannot use bilinear.

### Task 1: Remove the polar kind gate and backfill

- [x] In `test_v3_polar.py` and `test_v3_polar_components.py`, make binding of
  unlabeled direct, prepared and paired fields a success case. Reopen a sampled
  integer ramp to check a fractional value. Compare reopened Meso-NH, GRIB,
  CROCO and NEMO results with explicit continuous declarations, allowing only
  the metadata difference. Keep failures for nonnumeric and wide-integer
  records, and check gap and native metadata in `test_croco_support_views.py`
  and `test_v3_polar.py`.
- [x] Run `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q
  src/frameit/testing/numerical/test_v3_polar.py -k 'optional_kind or
  integers_without_kind'`. Expected before implementation: failures on E1603.
- [x] In `contracts.py` and `sampling.py`, remove missing-kind admission,
  nearest waivers and gap markers. Compare actual pair options, not presence
  of kind. Check numeric sample dtypes in the plan, not metadata kind.
  In `polar_proj.py`, evaluate bilinear integers as float64.
- [x] Remove the kind-only adapter rules and `W1603` emission from
  `requests.py`, `preflight.py`, `coupled.py` and the affected `io/` modules.
  Retain normal GRIB identity verification and static CROCO mask checks.
- [x] Update the configuration, inputs, polar methods and troubleshooting
  docs; preserve old diagnostic links. Run the strict Sphinx build and
  publication check. Inspect the rendered pages.
- [x] Re-run the new regressions and nearby polar cases in `frameit_env`.
- Run the default pytest suite in bounded shards with the verified
  `FRAMEIT_CI_DATA_ROOT` fixture. Review the diff and commit locally when
  targeted and documentation checks pass; integrate only after the broader
  verification and whole-branch review.
