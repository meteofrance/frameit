# Optional C3 groups — verification record

Candidate increment on40f9bcdb4429fe1755aab871c2b7f9d5916af51e, not Task16
completion. The user approved optional groups on2026-11-16. Design/plan:
`c3-grouped-requests-design.md`, `c3-grouped-requests-plan.md`.
Review and commit are still pending.

## Scope and preservation

Keep simple lists/source-wide levels unchanged. Grouped requests use explicit
native identities and local selectors, with `group.field` references and stored
names. Raw inventory/locators remain unchanged. C7 coordinates and C9's version1
seven-key envelope remain. No numerical method, precision, scientific default,
fixture, dependency or environment change.

The lead preserved all29 existing changed files and their tracked binary diff
before core edits. The16 partial Task16 source/example/test files are outside
the C3 implementation claim. Only the UTrack prose and its publication-unit
assertion are brought forward from Task16 to keep required documentation checks
coherent; exact declaration values and the v3 execution limitation remain.
The three separately reported NetCDF/CROCO fixes remain unapproved and untouched.

## Commands

Every command runs from the worktree root using this prefix:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env
```

Python3.13.18 and this worktree's source import were freshly confirmed.
All detailed logs/XML, exact failed node IDs, status comparisons and RED/GREEN
evidence use the new ignored `task-16-c3-*` names; earlier evidence is retained.

| Check | Observed result |
|---|---|
| New grouped module, built incrementally | Syntax RED11failed/2passed; binding RED6failed/15passed; operation/inspection RED3failed; selected-reader RED5failed. Later focused32passed. |
| `python -m pytest -q src/frameit/testing/numerical/test_grouped_requests.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_v3_cli.py::test_editor_schema_is_generated_from_shared_structural_definitions --tb=short` | 340passed in3.91s at the syntax milestone. Shipped schema equals its authoritative generator. |
| Grouped binding, existing field/level binding and two inspection guards | 55passed in3.48s at the operation milestone. No scientific payloads during guarded binding. |
| Initial five-module binding/caller covering command | 275passed/53failed; all21new nodes passed. XML comparison identified52unchanged old failures and one obsolete no-qualified-selector message assertion, then updated without weakening its identity failure. |
| Fourteen-module connected covering command below | 1190passed/53failed/1689warnings in236.33s. One new lookup-order regression and52unchanged old caller failures; not a green suite. |
| `python -m pytest -q src/frameit/testing/numerical/test_grouped_requests.py src/frameit/testing/numerical/test_v3_grib_reads.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_request_selection.py::test_v3_field_and_level_binding --tb=short` | 143passed/35warnings in48.63s after correcting the lookup-order regression. |
| `python -m pytest -q src/frameit/testing/numerical/test_grouped_requests.py src/frameit/testing/numerical/test_v3_cli.py::test_editor_schema_is_generated_from_shared_structural_definitions --tb=short` | Fresh40passed/35warnings in26.85s, including all39grouped cases, the actual BATSIRAI payload-read spy and generator/asset equality. |
| Ruff on all10changed Python paths, compared to HEAD with the same configuration | Baseline36/current35diagnostics, zero new diagnostics. Existing findings are not called clean lint. |

The connected command names:

```text
test_grouped_requests.py test_configuration_v3.py test_v3_cli.py
test_v3_reports.py test_v3_operations.py test_v3_polar.py test_v3_outputs.py
test_v3_netcdf_reads.py test_v3_grib_reads.py test_v3_fa_reads.py
test_request_selection.py test_grid_representations.py test_inspect_metadata.py
test_grib_lifecycle.py
```

All paths are under `src/frameit/testing/numerical/`, passed to
`python -m pytest -q ... --tb=short` with an explicit JUnit destination.
The first attempt was terminated by the tool's120-second timeout at58%; it has
no final result/XML and is not counted as completed. The complete repeat used
no tool timeout. This named covering run is not Task16's authorized full suite.

Merging that covering XML with the current143-node run covers1243distinct IDs:
1191passed/52failed, including39new grouped cases, with no changed old outcomes
against the available mixed-age Task15/partial-Task16 inventory. The52retained
failures are33request-selection callers,15grid-representation callers,
3inspection callers and1matrix/native-shutdown caller awaiting Task16 producer/
caller conversion. Their exact names and statuses are retained in
`task-16-c3-coverage-delta-02.json`; none is skipped, waived or called passed.
This does not supply a corrected full Task15 or Task16 result.

## Scientific and interoperability checks

- Actual multi-axis ecCodes messages: independent height/pressure selections,
  explicit order and compatible coordinate units; excluded times/fields are not
  decoded. NetCDF and Zarr products reopen without importing FrameIt.
- Original BATSIRAI files: unchanged height indices `[0,2,5]`, pressure values
  `[1000,850,400]`hPa and two explicitly selected source samples. A fresh reader
  independently scans the original messages and compares exact native values,
  masks, coordinates and units. Source hashes remain unchanged.
- Grouped NetCDF axes and native W: distinct selections remain separate;
  explicit W remapping still selects destination positions and retains pressure
  vertical-velocity units. Polar speed remains magnitude after component sampling.
- Native FA cube: original admission/declarations/records remain, with qualified
  array naming after admission. A compact actual native decode retains selected
  order, values, zeroes, missingness and native-record auxiliaries.
- Unqualified/within-group ambiguity, competing providers, native-support name
  collisions and forged reference keys fail rather than selecting another field.

New-fixture corrections are not scientific workarounds: ecCodes names10-m U as
the2D parameter165/`10u`, so the new six-level3D fixture uses20–70m for actual
parameter131/`u`. A fresh3D-reader assertion needed its length-one vertical axis
in the expected shape. The real fixture was never edited or filtered.

## Documentation and remaining gates

Strict Sphinx03 and publication03 passed. Strict01/02 failed on the partial
UTrack draft's table indentation; the corrected draft retains its content.
Publication unit03 ran12passes/1error because it still expected the retired
tracking wrapper; after conversion, unit04 ran13passes.
Strict Sphinx04 and publication04 passed after the final input/polar cross-links;
unit04 passed all13checks. Live GUI checks and independent review are pending.
No standalone plot/image/screenshot/pixel check or human acceptance is claimed.

The regenerated schema keeps the generator's original key order. SHA-256:
`319a6aa028ef68b7517040bea72aeee99a08e923b5cf697231cb156a8450cd24`.
This is source-asset evidence, not installed-wheel or standards-conformance proof.

Known limit: unequal group selections landing on one destination output axis
fail in metadata preflight. Matching selectors or separate runs are required;
no sparse padding, implicit alignment or new C7 axis-alias scheme was added.
Independent schema-standards validation, installed-wheel execution, broad native/
HPC qualification, the remaining Task16 work and Tasks17–21 remain open.

## Independent review02 and bounded fix1

The independent reviewer checked all25frozen paths at
`7c489ffe607551077ae71e5af47130381faca1ca`, the16preserved partial Task16 files,
and bounded probes. Verdict: **SPEC ISSUES / QUALITY NEEDS FIXES**, with4Important
findings and no Critical/Minor findings. Report and original tree remain intact.
The same reviewer must close these findings; no fresh whole-task review or
scientific sign-off is inferred.

| Finding | Regression observed before fix | Candidate correction and focused result |
|---|---|---|
| Shared C7 axis across horizontal grids | W/native-U conflict returned no preflight error; equal-selection control passed | Reuse C7's exported vertical-axis identity, not the complete grid ID. Four W controls plus native-axis/GRIB bindings:6passed. |
| Generated tracker support duplicates a grouped export | Flat control passed; grouped pressure export failed duplicate resolved identity | Only exclusively generated method support may reuse identity; keep raw keys/full support and reject authored duplicates. Two tracker controls plus existing native-centroid execution:3passed. |
| Qualified CROCO operation inputs | Grouped equivalent of the admitted flat transform failed its raw-name whitelist | Resolve actual native quantities and adapt names only across existing current preparation. Grouped and unchanged flat end-to-end cases:2passed, with masks, values, rotation, selected reads and ordinary-reader metadata. |
| FA local physical-domain rejection | Flat CLI/schema control passed; grouped form raised KeyError | Report the actual selector at its local path, preserving the FA rejection. Two CLI/schema controls plus10existing admission cases:12passed. |

RED/GREEN logs and XML are new `task-16-c3-fix1-{fa,axis,tracker,croco}-*`
artifacts in the ignored workspace. Each command is
`python -m pytest -q <named nodes> --tb=short --junitxml=<new artifact>`, with
the environment prefix above. Exact nodes:

```text
test_grouped_requests.py::test_fa_physical_selection_rejection_keeps_local_path_and_cli_json
test_configuration_v3.py::test_v3_does_not_broaden_fa_admission
test_grouped_requests.py::test_grouped_w_transform_selects_destination_without_changing_other_group
test_grouped_requests.py::test_grouped_netcdf_axes_keep_different_native_positions
test_grouped_requests.py::test_grouped_grib_binds_exact_fields_and_independent_levels_without_payloads
test_grouped_requests.py::test_tracker_support_keeps_native_keys_and_levels_with_grouped_export
test_v3_regions.py::test_native_centroid_binds_real_support_separately_from_export_levels
test_grouped_requests.py::test_grouped_croco_transform_keeps_native_current_preparation
test_v3_operations.py::test_croco_explicit_transform_reuses_joint_masks_and_rho_rotation
```

The tracker test now also executes the grouped81×81control, comparing its pressure
export and trajectory against the existing independent expectations. The compact
9×9RED reproduction and all earlier evidence are retained, not replaced.

Fresh connected fix1 verification: **986passed/1509warnings in223.11s**. This
includes all46grouped cases and the following command, with the same environment
prefix and new `task-16-c3-fix1-connected.{txt,xml}` artifacts:

```bash
python -m pytest -q \
  src/frameit/testing/numerical/test_grouped_requests.py \
  src/frameit/testing/numerical/test_configuration_v3.py \
  src/frameit/testing/numerical/test_v3_cli.py \
  src/frameit/testing/numerical/test_v3_reports.py \
  src/frameit/testing/numerical/test_v3_operations.py \
  src/frameit/testing/numerical/test_v3_polar.py \
  src/frameit/testing/numerical/test_v3_outputs.py \
  src/frameit/testing/numerical/test_v3_netcdf_reads.py \
  src/frameit/testing/numerical/test_v3_grib_reads.py \
  src/frameit/testing/numerical/test_v3_fa_reads.py \
  src/frameit/testing/numerical/test_request_selection.py::test_v3_field_and_level_binding \
  src/frameit/testing/numerical/test_v3_regions.py::test_native_centroid_binds_real_support_separately_from_export_levels \
  src/frameit/testing/numerical/test_croco_vectors.py::test_croco_current_joint_support_never_fills_missing_or_erases_zero \
  src/frameit/testing/numerical/test_croco_vectors.py::test_croco_analysis_rejects_unresolved_inputs \
  --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-c3-fix1-connected.xml
```

This is a connected subset, not Task16's full diagnostic. The52earlier legacy
caller failures are retained by name in the earlier covering evidence, not
waived or retrospectively described as passed. Warnings include existing
NetCDF/NumPy deprecations and time-bounds/concat warnings, not clean-warning output.

Ruff on all11changed Python paths:36baseline/35current/zeroNew. `git diff --check`
passes. All16partial Task16 source/example/test hashes remain exact. The three
excluded core boundaries are unchanged: entire crop assembly/writer/current
helper files are byte-exact HEAD, temporal inventory/clock and operation-result
assembly function ASTs equal HEAD. The canonical/native preparation boundary is
the only addition to `derived/wind.py`.

Strict Sphinx05, publication05 and13publication units pass. Seven affected pages
were refreshed in the connected live GUI at1020/320CSS widths: expected text,
no horizontal page overflow, reachable code right edges. Preview retained;
no image/screenshot/human-acceptance claim. Scoped independent closure remains
pending before any local commit.

No crop, native-index construction, temporal-metadata whitelist, scientific
method, mask, velocity basis convention, selected levels, tolerance or strict
merge was changed. The distinct three-core diagnosis remains decision support
only; especially CROCO support representation has no authorization here.

Lead self-review of finding2 also exercised an authored operation that uses raw
and qualified references to the same actual field. The initial fix mislabeled
the raw operation input as generated support: the new regression observed
`DID NOT RAISE`. Preserve the operation's explicit inputs in its existing
subrequest before applying planner selectors. A fresh grouped/operation/polar/
field-binding/centroid command passed **251tests/1136warnings in117.10s** after
that one-line tightening. It includes all47grouped cases and uses the environment
prefix above:

```bash
python -m pytest -q \
  src/frameit/testing/numerical/test_grouped_requests.py \
  src/frameit/testing/numerical/test_v3_operations.py \
  src/frameit/testing/numerical/test_v3_polar.py \
  src/frameit/testing/numerical/test_request_selection.py::test_v3_field_and_level_binding \
  src/frameit/testing/numerical/test_v3_regions.py::test_native_centroid_binds_real_support_separately_from_export_levels \
  --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-c3-fix1-final-operations.xml
```

The986-node result above predates this final authorship correction; the251-node
result verifies its affected operation paths. Neither is a full Task16 result.
Fresh Ruff remains36baseline/35current/zeroNew on all11Python paths.
