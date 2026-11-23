# Polar Kind from Evidence Implementation Plan

> Historical plan; superseded by [optional polar kind](2026-11-23-optional-polar-kind.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Default a missing polar kind from supported evidence, and report each completion.

**Architecture:** Add the CF sea-height evidence rule to the existing selected-record kind completion. Share the bound decision and warnings with input-aware validation and execution.

**Tech Stack:** FrameIt v3, Python 3.13 in `frameit_env`, xarray, pytest, Sphinx.

**Spec:** [Default polar kind from selected input evidence](../specs/2026-11-20-polar-kind-from-evidence-design.md)

## Global Constraints

- No new YAML settings, numerical methods, or input or output formats.
- Known kind, categorical flags, and valid declarations take precedence; unresolved kinds and contradictions still fail.
- Do not infer units, datums, time statistics, or masks or loosen existing layout and reader checks.
- Run in the existing local worktree; commit only this change. Do not merge or push.

## Review Focus

- Name or dtype alone, unrecognized labels, or an incompatible unit still yields E1603.
- A later selected wide integer cannot borrow eligibility from an earlier float.
- Explicit kind and categorical flags cause no kind-completion warning; conflicting declarations fail.
- Validate does not read field values or create a run directory. Native-only copies do not acquire kind.
- Repeated sampled times produce one warning per field; excluded and absent rows do not acquire evidence.

## Task 1: Bind and report one missing fact

**Files:** `src/frameit/io/nemo_utils.py`, `src/frameit/processing/requests.py`,
`src/frameit/processing/polar/sampling.py`, `src/frameit/core/coupled.py`,
`src/frameit/utils/diagnostics.py`, `src/frameit/testing/numerical/test_v3_polar.py`.

- [ ] Add `test_nemo_cf_sea_height_kind_without_yaml` using the declared-kind
  comparison helper. Assert off-node bilinear values `[1., 3.]` from neighbours
  `[0., 4.]` and `[2., 6.]`, missingness, native time and unchanged units. Check
  rule `nemo.cf.sea_surface_height_above_geoid.kind.v1`, one W1603 in validation
  and provenance across both times, no warning with a declaration, no science
  read in validation, and no completion for a native-only copy.
- [ ] Add negatives for a missing or incompatible CF header, a later wide
  integer, and observed/declared kind including categorical flags and conflicts.
  Extend the existing documented-kind comparisons to cover W1603, while keeping
  the existing `common` and initial-gap provenance controls.
- [ ] Run `conda run --no-capture-output -n frameit_env python -B -m pytest -q -p no:cacheprovider src/frameit/testing/numerical/test_v3_polar.py -k 'nemo_cf or documented_mesonh'`.
  Expect E1603 for eligible NEMO without kind and no W1603 for the previous
  producer match before implementation.
- [ ] Implement `nemo_sea_height_kind_evidence(source, record, attrs)` returning
  the rule, observed standard name and units plus the reference, or `None`.
  Use only observed headers, native `time_counter` samples on the admitted
  horizontal grid, and the existing numeric gate. Wire it into
  `complete_documented_polar_kind` for direct, unchanged NEMO NetCDF jobs.
- [ ] Aggregate the rules used on real participating records from the final
  polar binding. Emit W1603 once per source/field in the owning validation
  report and use the existing run provenance.
- [ ] Repeat the tests, then run the full polar, NEMO, CROCO, GRIB and CLI
  controls with checkout imports. Verify authored YAML validation and run
  agree, including the JSON warning, and reopen outputs with an ordinary reader.
- [ ] Update input and ocean guidance and the W1603 help and index. Build Sphinx
  strictly, check publication boundaries, and inspect the rendered desktop and
  narrow preview. Review and commit the focused change locally.
