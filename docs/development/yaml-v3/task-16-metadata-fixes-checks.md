# Task16 approved metadata repairs — verification

Base9847bd618c3cd937ca447ec9d4c47afa73b88b5b. The maintainer approved the two
metadata repairs, not the CROCO support-layout change. Independent review has
approved the frozen candidate; the local commit follows final scope checks.
No scientific method, masks, samples, selected indices,
time guard, strict merge, writer encoding, dependency or environment was changed.

## Scope and preservation

`core/preflight.py::_netcdf_inventory` retains observed `GRIB_stepType`, without
inventing missing evidence. `processing/derived/wind.py::execute_source_operations`
retains supplied native-index attributes and uses the existing NEMO/CROCO generated
description. Source clocks, original indices/order and numerical arrays remain.
The new tests distinguish actual round trips from executor-boundary checks.

All25pre-existing dirty files and their binary diff are saved in the ignored
`task-16-metadata-approved-baseline/`; they remain outside this change.
The two canonical prose additions explain time evidence and index metadata only.

All commands run at the worktree root with:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env
```

Python3.13.18/worktree import was confirmed. New `task-16-metadata-*` logs/XML
retain full errors; earlier C3/Task16 evidence is unchanged.

## RED/GREEN

- Time RED:6failed/3passed. Four lost-attribute assertions, a wrongly rejected
  instantaneous reference and a wrongly accepted contradictory avg/point reference.
  After preserving the observed key:17passed/229warnings, including the original
  portable NEMO example and existing interval/mean/GRIB guards.
- Index initial full co-export cases:8failed at the original strict index merge;
  the three genuine-conflict controls passed. The metadata correction then exposed
  separate coordinate/data-variable role conflicts for exported `zeta` and an
  input-supplied index. Those attempts remain recorded, not called passed.
- The final isolated index cases were watched fail again with only our index
  change temporarily removed: all6failed at the original index-metadata conflict.
  These exercise four mixed-native/transformed NetCDF/Zarr round trips and two
  real executor checks preserving supplied attributes. Supplied-index file loading
  remains an unresolved ownership boundary, not a passing round-trip claim.
- Final new module:18passed/69warnings in13.85s. Round trips retain native fields,
  W zeroes, sigma support, both `[0,2]`/`[2,0]` orders, rotated currents, NaNs,
  raw source bytes and ordinary-reader metadata without importing FrameIt.
  Wrong indices, labels or attributes still fail the unchanged strict merge.

New test commands are `python -m pytest -q` followed by the named nodes in
`test_metadata_preservation.py`, `--tb=short` and a new JUnit destination.
The full new module command uses
`--junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-metadata-boundaries-green.xml`.

## Connected result — not a green whole suite

**429passed/2failed/2026warnings in226.12s** using:

```bash
python -m pytest -q \
  src/frameit/testing/numerical/test_metadata_preservation.py \
  src/frameit/testing/numerical/test_v3_operations.py \
  src/frameit/testing/numerical/test_v3_netcdf_reads.py \
  src/frameit/testing/numerical/test_v3_outputs.py \
  src/frameit/testing/numerical/test_v3_regions.py \
  src/frameit/testing/numerical/test_v3_polar.py \
  src/frameit/testing/numerical/test_grouped_requests.py \
  src/frameit/testing/numerical/test_nemo_arome_coupling.py::test_preceding_hour_selects_bounds_not_nearest_and_warns \
  src/frameit/testing/numerical/test_nemo_arome_coupling.py::test_preceding_hour_rejects_unresolved_inputs \
  src/frameit/testing/numerical/test_nemo_arome_coupling.py::test_preceding_hour_relabels_coordinates_without_recomputing_values \
  src/frameit/testing/numerical/test_croco_vectors.py::test_croco_current_joint_support_never_fills_missing_or_erases_zero \
  src/frameit/testing/numerical/test_croco_vectors.py::test_croco_analysis_rejects_unresolved_inputs \
  docs/test_repository_examples.py::test_portable_nemo_arome_example_with_preceding_hour_inputs \
  docs/test_repository_examples.py::test_croco_mnh_portable_example_runs_both_current_representations \
  --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-metadata-connected.xml
```

The only failures are the unchanged original portable CROCO nodes:

- `[native]`: exact alignment fails on `y_rho`, the diagnosed crop/support mismatch.
- `[mass_earth]`: index metadata now passes; `zeta` is a coordinate in one view and
  a data variable in another. This is a separate support-ownership conflict.

Their original numerical/NaN/W/sigma assertions remain intact and unreached in
these runs. No fixture, co-export or assertion was removed from either original
test. The new isolated round trip retains `zeta` as ordinary formula support,
not as an explicit co-export; it does not replace these required cases.
The remaining ownership/layout work is proposal-only. No waiver/full Task16
result, installed-wheel, broad producer/HPC or scientific/human acceptance.

## Documentation and lint

Strict Sphinx/publication01 and all13publication units pass in `frameit_env`.
The two changed pages were inspected in the live GUI at1020/320CSS widths:
changed text present, no horizontal page overflow, reachable code right edges.
The output-page text check was corrected for Sphinx's typographic apostrophe;
no rendering or source change was needed. Preview/server details stay in the
ignored handover, not committed machine state. No image/plot/screenshot checks.

Ruff three changed Python paths:6baseline/6current/zeroNew. The first lint pass
found one long line in the new test; wrapping it removed the new finding.
Existing warnings include NetCDF/NumPy deprecations, binary-size and time-bounds
warnings; no clean-warning or environment-repair claim.

## Independent review closure

Fresh review of tree `c70c011e656ab8e95b6033397b9f0ad7e6ad785b` returned
**SPEC PASS / QUALITY APPROVE**, zero Critical/Important/Minor findings. The
reviewer independently checked the exact eight-path patch, all candidate hashes,
the empty real index and all25preserved paths. Its43targeted tests passed with
296warnings in27.26s;36additional actual-executor controls and an independent-reader
NEMO round trip also passed. Exact commands and raw artifact locations are in
the retained `task-16-metadata-review-01.md` report. It did not rerun the full/
connected suites, documentation build, lint or GUI checks.

The lead verified that the reviewed bytes and preserved paths were unchanged
before recording this closure. Post-review edits are confined to status in this
record, the plan and STATE; production, regressions and canonical prose remain
exactly reviewed. The local commit is restricted to the original eight paths.
The CROCO layout alternatives remain proposals, not new scientific/schema
authorization. All previously reported failures and unexecuted gates remain.

Final precommit verification repeated the complete new module:
`python -m pytest -q src/frameit/testing/numerical/test_metadata_preservation.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-metadata-final.xml`:
18passed/69warnings in13.85s. Strict Sphinx/publication02 and13publication units
passed with the declared environment prefix and:

```bash
sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-metadata-02
python docs/check_publication.py build/docs-preview/yaml-v3-metadata-02
python -m unittest discover -s docs -p test_check_publication.py
```

Both affected HTML files are byte-exact to the retained live-reviewed01pages;
the existing preview remains available. The five production/test/canonical
paths remain byte-exact to the independent review, all25previous paths remain
preserved, and `git diff --check` passes.
