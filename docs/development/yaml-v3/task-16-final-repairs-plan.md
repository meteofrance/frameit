# Task16 input-aware validation and CROCO/W repairs

> Execute inline with systematic debugging and TDD under the maintainer's
> 17 November instruction to fix these issues without unnecessary questions.

**Goal:** Close the identified spacing-message, W-selection and CROCO defects
without changing source fixtures, quantities, scientific methods or defaults.

**Authority/design:** The maintainer requires input-aware YAML validation to
reject sub-native polar radial steps, state that finer sampling is not supported
yet, and give a minimum usable value for the selected inputs. W must preserve
native interface exports while the explicitly requested mass representation
uses corresponding mass targets and real native brackets. CROCO must preserve
static-support semantics across files and reject inconsistent selected support.
The existing C7 independent native-grid cropping contract remains authoritative.

**Architecture:** Reuse current sampling resolution, source binding, native
coordinate selection, CROCO validators, selected readers and ordinary writers.
No new configuration keys, interpolation method, dependency or legacy adapter.
Current shared and source-specific targets use the same minimum-step wording.
Explicit grouped W values are resolved on the declared native interface group
before carrying their original positions into the existing mass-index mapping;
flat selectors keep their current per-representation meaning.

**Alternatives:** Do not relax the radial guard, choose nearest W values, alter
fixture coordinates, force xarray merges, or make native masks dynamic. Do not
count a binding failure as proof that the reader rejected changed metadata.

## Global constraints

- Use existing `frameit_env`, Python3.13, source `PYTHONPATH`, bytecode off and
  `/tmp/opencode`; only approved compact inputs. No installs/environment repairs.
- Preserve native values, clocks, masks, formula dependencies and numerical
  tolerances. Internal W bracket reads remain separate from exported selection.
- Diagnostics stay opt-in. No production/cluster jobs, downloads, benchmark
  campaigns or standalone image/screenshot checks.
- This is not a Task16 source/test/asset freeze; do not use its reserved full
  diagnostic while other independently recorded contract failures remain.
- Review changes before local focused commits. Never push or merge.

## Review focus

1. Copying the reported minimum must succeed; a rounded-down number must not
   inadvertently be recommended. Schema-only validation must remain file-free.
2. Shared targets must use the coarsest selected participant and invalidate
   executable bindings after an error.
3. Native and mass W may need different source samples; mass-only/W-only
   requests and reordered selections must not borrow another field's labels.
4. Static CROCO masks must be proven native-static before removing an assembly
   singleton. Native wetting/drying or changing support must not be admitted.
5. Validate only selected CROCO fields/support, without reading current,
   temperature, salinity or sea-level payloads or unrelated/excluded snapshots.

## Task A — actionable radial-step validation

Files: `processing/polar/sampling.py`, `core/coupled.py`, numerical polar/CLI tests.

- [x] Add failing public validation tests for local/shared steps: unsupported-yet
  text, input-dependent minimum, no output creation and no scientific payload reads.
- [x] Reuse existing guard; report an exactly usable minimum and omission repair
  in both local and shared errors. Do not change any requested target.
- [x] Verify copying the minimum binds, and schema-only validation opens no files.
- [x] Keep the original catalogue's2.5km AROME request as a rejection regression;
  exercise YAML/mapping replay separately with explicitly automatic native
  spacing. Do not rewrite the frozen catalogue or call its original request valid.

## Task B — grouped native W values and explicit mass sampling

Files: `processing/requests.py`, numerical operation/catalogue tests.

- [x] Reproduce the original physical-value catalogue failure unchanged.
- [x] Add analytical grouped native/mass W tests, including reordered values,
  W-only output and actual bracket support.
- [x] Resolve explicit native-group W values to their original native positions
  before selecting the corresponding established mass representation. Preserve
  shared-destination selection conflict checks and flat selector behavior.
- [x] Verify original native values `[0,20,50]`, mass labels `[5,25,65]`,
  source immutability, actual outputs and ordinary-reader metadata.
- [x] Preserve requested vertical units during mapping and describe transformed
  product dimensions from the destination grid, not discarded source face names.

## Task C — CROCO support and validation boundaries

Files: `io/croco_utils.py`, `core/preflight.py`, `processing/derived/wind.py`,
`processing/polar/{contracts,polar_proj}.py`, CROCO/boundary numerical tests.

- [x] Add the one-file/two-file current-analysis regression, retaining real
  static mask shape, analytical current values and independent reopening.
- [x] Restore only assembly-added singleton time on proven static CROCO support
  in the shared operation preparation path; remove redundant scalar-only repair.
- [x] Accept the existing unit registry's singular geographic degree spellings.
- [x] Reuse cross-snapshot coefficient/support validation during binding; bound
  the reads to selected coordinate/formula/static analysis support.
- [x] Pin changed angle/mask/Cs/hc rejection and exclusion/optionality safety.
- [x] Test reader rejection by binding valid fixtures first, then changing the
  synthetic on-disk support before the actual reader; never fabricate binding.
- [x] Resolve the old four-face crop expectation against independently located
  native geography. Fix a demonstrated implementation defect, otherwise correct
  only the obsolete migration expectation and record the contract evidence.
- [x] Keep coefficient comparisons within each native field owner and actual
  selected read positions; preserve distinct owned sigma grids, lazy physical
  support and caller resource reuse.
- [x] Reject a required angle that differs from bound geometry, missing/malformed
  sigma formula metadata, and required dynamic face masks during validation.

## Bounded GRIB reader follow-through

The separate supported-spacing AROME replay exposed an internal scalar-height
merge defect. Surface height10 must not become a selectable upper-air axis or
align onto `[70,20]`. Preserve field-local scalar read views and pass only actual
dimensions to the existing strict internal-stencil merger. Tracker preparation
rejoins compatible surface views strictly before its existing pair normalization;
only genuinely declared initial-gap views remain excluded.

- [x] Reproduce the scalar/upper-air conflict with real compact GRIB messages;
  assert both native heights, dimensions and independently specified values.
- [x] Preserve tracker U/V companion validation, exact coordinates, unit/frame
  preparation and the existing initial-gap restriction. Both exposed tracker
  regressions have complete existing end-to-end tests.

## Task D — connected verification and handover

- [x] Run affected full CROCO modules, W/polar/reader/report modules and approved
  compact catalogue replays; inventory remaining Task16 failures separately.
- [x] Explain residual failures by family, distinguishing implementation defects,
  intentionally unsupported requests and obsolete test expectations.
- [x] Update canonical configuration/ocean/validation docs and internal state.
  Run strict Sphinx/publication and inspect affected text live at1280/320px.
- [x] Obtain fresh bounded review, close findings and prepare only task changes
  for the required local commit. Keep the preview and limitations available.

Record the resulting focused local commit in the session handover. Never push.

## Evidence and remaining Task16 gates

Private RED/GREEN logs and XML are retained under
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-fixes-ba15fdc/`.
They are engineering checks, not scientific sign-off.

- Initial RED01:14 failed/44 passed. Full repair/CROCO GREEN11:62 passed.
  Requested kilometre-unit RED12/GREEN13 closes the W units defect.
- Connected14's11 regressions exposed overbroad support reads and ownership
  comparison. The six affected complete modules then passed235 tests (17).
- Review RED20 reproduces ten cases: stale bound angle values/units, missing or
  malformed sigma formula, and dynamic face masks. GREEN21/22/23 pass4/4/2.
- GRIB scalar RED18/GREEN19 covers the actual reader; complete GRIB module plus
  the new regression pass33 tests. Connected24 exposed two tracker regressions
  (1400 passed); GREEN34 passes both and the scalar reader regression.
- Final complete18-module connected closure35: **1402 passed**,3549 warnings,
  424.44s; no failed, errored or skipped cases. All26 new regression cases pass.
  The independent bounded review closes I1/I2/M3, replacement support handling
  and the late GRIB tracking-consumer finding; no scoped finding remains.
- The last complete required Task16 run25 has314 passes/three failures,
  512 warnings and two passing subtests. It is not a Task16 pass.
- A fresh preservation inventory31 retains five failures/three passes: old
  `strict` association, native/no-rotation rejection expectations, and the two
  removed configuration controls. No test was skipped or weakened to retire them.
- Strict Sphinx26/publication28 and13 source-aware publication units30 pass.
  Five changed pages were read in the connected GUI at1280/320px. No screenshots
  or generated images were opened. Runtime36 confirms Python3.13.18 and this
  source checkout; both edited modules' fixture/helper ASTs match `ba15fdc`.
- Final Ruff comparison39:67 existing findings against70 at `ba15fdc`, with
  zero introduced findings. This is not a claim that whole-repository Ruff is clean.

The three current required-suite failure families are:

| Caller | Current failure | Disposition |
|---|---|---|
| `test_named_sources_inherit_only_declared_polar_settings_and_replay` | Removed `sources.ocean.polar` key | Retained migration disagreement; no compatibility alias |
| `test_time_dependent_geometry_and_override_contract` | Removed `sources.atmosphere.grid_spacing_m` key | Retained explicit2600m override request; no inferred-spacing substitution |
| `test_frozen_matrix_yaml_and_mapping_requests_match[AROME]` | Polar merge sees `time` metadata with and without interval bounds | Real remaining field-owned temporal-metadata defect; do not discard bounds or relax identical merge |

The original AROME2.5km catalogue request is deliberately rejected with a
minimum of2.766872308879716km for its selected inputs. Its separate
automatic-native-spacing replay gets past validation and GRIB loading, then
exposes the temporal-metadata merge failure above. Native-spacing selection is
not a waiver of that output failure. The unchanged MNH physical-value catalogue
now executes and passes the ordinary product checker.

No source/test/asset freeze or reserved full diagnostic has occurred.
Historical87-node worker inventories are not a current combined result.
Task17's new plotting evidence, Task19's installed/full qualification and
Task21's final whole-branch/full-documentation reviews and actual human
acceptance remain unavailable. Nothing is pushed or merged.

### Verification commands

Commands are from the worktree root. The installed environment was not changed.
The complete connected closure uses the approved compact catalogue fixture:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_v3_boundary_review.py \
  src/frameit/testing/numerical/test_v3_boundary_repairs.py \
  src/frameit/testing/numerical/test_configuration_v3.py \
  src/frameit/testing/numerical/test_v3_reports.py \
  src/frameit/testing/numerical/test_v3_cli.py \
  src/frameit/testing/numerical/test_v3_netcdf_reads.py \
  src/frameit/testing/numerical/test_v3_grib_reads.py \
  src/frameit/testing/numerical/test_v3_operations.py \
  src/frameit/testing/numerical/test_v3_polar.py \
  src/frameit/testing/numerical/test_v3_polar_components.py \
  src/frameit/testing/numerical/test_inspect_metadata.py \
  src/frameit/testing/numerical/test_netcdf_assembly.py \
  src/frameit/testing/numerical/test_v3_regions.py \
  src/frameit/testing/numerical/test_croco_support_views.py \
  src/frameit/testing/numerical/test_croco_netcdf.py \
  src/frameit/testing/numerical/test_croco_vectors.py \
  src/frameit/testing/numerical/test_v3_outputs.py \
  src/frameit/testing/numerical/test_v3_task16_repairs.py \
  --basetemp="$(mktemp -d /tmp/opencode/frameit-connected-closure-XXXXXX)" --tb=short \
  --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-fixes-ba15fdc/connected-closure-35.xml
```

The complete required Task16 nine-file command25 was:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_configuration_v2_1.py \
  src/frameit/testing/numerical/test_documentation_example.py \
  src/frameit/testing/numerical/test_configuration_integration.py \
  src/frameit/testing/numerical/test_all_tests.py \
  src/frameit/testing/numerical/test_templates.py \
  src/frameit/testing/numerical/test_v3_execution.py \
  docs/test_repository_examples.py docs/test_documentation_plots.py docs/test_release.py \
  --basetemp="$(mktemp -d /tmp/opencode/frameit-task16-final-XXXXXX)" --tb=short \
  --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-fixes-ba15fdc/task16-final-25.xml
```

The three retained failures were also rerun after the tracker caller closure
(37); all three still fail for the same reported reasons. Documentation checks:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-review-10
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode conda run --no-capture-output -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-review-10
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode conda run --no-capture-output -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
git diff --check
```
