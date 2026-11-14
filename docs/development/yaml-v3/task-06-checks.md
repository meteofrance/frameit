# Task06 regional/time integration evidence

Base: `73c4147ba2bcb45672b56d8808a7ba2dbc86a934`.
Status: **Independently approved after fix round1**.
The original reviewer closed I1–I4 with no new blocking finding. All seven
new fix cases pass; earlier pending-review statements are historical.
All three bounded extensions were authorized and implemented; all 57 new Task06
nodes pass. The current evidence is appended below. The initial
NEEDS_CONTEXT snapshot is retained as history, not a current blocker list.
No passing-full-suite or scientific sign-off claim.

All Python checks use Python3.13.18 in `frameit_env`, with
`PYTHONPATH="$PWD/src"`. Fixture-dependent commands additionally set
`FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01"`.
No environment/package/native-stack changes.

## Checked behavior

- Real NetCDF trajectory coordinate discovery, unique chronological times,
  strict dimensions/units/evidence and finite positions.
- Fixed native rotated crops, partial missing-value padding, outside-footprint
  failure, requested/realised geometry and coverage.
- Exact centres cover the union of unequal source clocks, not their intersection.
  Common-time association reports exclusions and leaves unrelated native
  extraction unchanged.
- The existing narrow AROME/NEMO preceding-hour association retains source sample
  labels, bounds, means and values; `center_time` records association separately.
- Real selected atmospheric pressure-wind reads observed at h5netcdf and ecCodes
  payload boundaries. Renamed/dependency-only atmospheric sources work.
  Defaults preserve the old100/50-km half-width geometry via200/100-km full widths.
- Native level products and internal tracker support remain separate.
  Real MNH centroid and multi-field incomplete/error behavior are tested.
- Ordinary independent readers check native fields, trajectory metadata, masks,
  zeroes and source clocks, including a360-day calendar.
- Unrelated interpretation/transform/derived/polar method gates stay pending.

## Initial verification (historical)

The exact unfiltered seven-file command from Task06's brief ran:
**79 passed,80 failed,0 skipped**. The80 failed/error IDs match the retained
pre-implementation inventory. The new pass checks exact selected-time tracker
merging. These failures are not a passing suite or a scientific exemption.

| Check | Observed result |
|---|---|
| Latest regional/geographic files | 50 passed,2 failed |
| New Task06 nodes only, deduplicated | 40 passed,2 failed |
| Required seven-file command | 79 passed,80 failed |
| Covering configuration/binding/readers/execution/native/HPC/metadata/resource lane | 812 passed,46 failed,1 error |
| Unfiltered full-project diagnostic | 1566 passed,477 failed,2 errors;4 subtests passed |
| Ruff on11 changed Python files versus base | 25→25 diagnostics;0 new |
| `git diff --check` | exit0 |

The full diagnostic predates two inventory-regression fixes and the last focused
checks. Its9 new failures were inspected by name. The later covering run verifies
both inventory cases green. Five direct numerical cases still write unitless
tracks; they are not producer-dependent exemptions. Two owned Task06 cases remain
blocked below. The full diagnostic has not been rerun after those focused fixes.

Across these runs there are **2049 distinct nodes**, using each node's latest
observation:1572 passed,475 failed,2 errors. All470 Task05 failed/error IDs still
fail, with7 additional IDs. Overlapping runs and the4 subtests are not added to
these totals. All failed/error names and raw failures are retained in the
implementation workspace's node/failure ledgers.

The compact new fixtures exercise actual selected pressure/wind and native
centroid backend reads, not replacement loaders. The centroid fixture includes
an excluded middle sample. Explicit compatible angular-unit conversion also
has RED/GREEN coverage; missing trajectory units remain an error.

Commands (all require the environment prefixes above):

```bash
python -m pytest -q src/frameit/testing/numerical/test_geographic_lookup.py src/frameit/testing/numerical/test_wind_pressure_seed.py src/frameit/testing/numerical/test_pressure_centroid.py src/frameit/testing/numerical/test_pressure_centroid_mnh.py src/frameit/testing/numerical/test_multifield_vortex.py src/frameit/testing/numerical/test_nemo_arome_coupling.py src/frameit/testing/numerical/test_croco_mnh_coupling.py
python -m pytest -q src/frameit/testing/numerical/test_v3_regions.py src/frameit/testing/numerical/test_geographic_lookup.py --tb=short
python -m pytest -q --tb=short
```

The covering command names `test_configuration_v3.py`, `test_request_selection.py`,
`test_v3_execution.py`, `test_v3_netcdf_reads.py`, `test_v3_grib_reads.py`,
`test_v3_fa_reads.py`, `test_native_extraction.py`, `test_hpc_execution.py`,
`test_inspect_metadata.py`, `test_fa_resources.py`, `test_v3_regions.py` and
`test_geographic_lookup.py`, all under `src/frameit/testing/numerical/`,
with `-q --tb=short`.

## Initial blockers (historical; authorization subsequently received)

Three bounded caller-wide scope requests await lead authorization:

1. Preserve authored trajectory aliases in `configuration._region`, so overwrite
   protection can retain every required alias in a replaced store. The real
   negative regression currently fails; direct trajectory-destination protection
   already works.
2. Permit the existing checked internal vertical union in selected NetCDF/GRIB
   readers. AROME multifield uses u/v at850/700/500hPa but z only850/700hPa.
   Native product assembly must remain exact; no additional z payload is justified.
   This method currently fails closed before binding/ownership, not as a claimed
   executable pipeline.
3. Add explicit geographic units to five directly affected numerical fixture
   cases, locally in their test functions without changing shared helper APIs
   or numerical assertions.

The7 remaining new failed IDs, relative to `src/frameit/testing/numerical/`:

```text
test_v3_regions.py::test_arome_existing_methods_bind_selected_metadata_and_export_track_only[multifield_vortex]
test_v3_regions.py::test_trajectory_and_required_aliases_are_read_only_before_run_ownership[store_alias_chain]
test_fa_mapping.py::test_fixed_and_prescribed_tracking_keep_requested_centres
test_polar_wind.py::test_supplied_centres_survive_tracker_and_postprocessing[prescribed_track-AROME-1]
test_polar_wind.py::test_supplied_centres_survive_tracker_and_postprocessing[prescribed_track-AROME-2]
test_polar_wind.py::test_supplied_centres_survive_tracker_and_postprocessing[prescribed_track-MNH-1]
test_polar_wind.py::test_supplied_centres_survive_tracker_and_postprocessing[prescribed_track-MNH-2]
```

Polar, source interpretation, complete writer/coordinate qualification, public
CLI/templates and scientific approval retain their separate task owners.
Scalar-spacing and unsupported moving/multigrid geometry limits remain. Fixed or
supplied track-only requests without any bound field/method input are not
qualified by this work. Public documentation/build/GUI verification and independent
review remain with the lead. No files have been staged or committed by the
implementer. The trajectory alias overwrite gap must be fixed before committing.

## Resumed verification after the bounded rulings

The lead authorized trajectory alias preservation, checked internal vertical
assembly and explicit units at the two local fixture-writing sites. No shared
fixture API, numerical assertion, package, environment or scientific method was
changed. Only `region.track.file` uses the existing alias-preserving path option;
execution reuses its existing input-location protection before ownership.
Real file/directory-chain negatives and independent-output positives now pass.

### RED/GREEN evidence

| Change | Observed RED → GREEN |
|---|---|
| Trajectory alias preservation | 2 failed/3 passed → 5 passed |
| Checked internal stencils, both NetCDF engines and ecCodes | 10 failed → 10 passed |
| Provisional AROME multifield method gate | 2 failed/1 passed → 3 passed |
| Five local fixture-unit cases | 5 failed/4 passed → 16 passed including strict invalid-trajectory tests |
| Existing native-index attributes | 1 failed → both complete selected-reader files: 93 passed |

Logs retain the `task-06-resume-{red,green}-*` and
`task-06-resume-readers-02.txt` names in the implementation workspace. Earlier
raw artifacts remain unchanged.

### Internal alignment and actual reads

`merge_internal_stencils` aligns only already selected internal vertical axes.
It retains first-seen labels, attributes and native-index correspondence,
checks overlapping values/attributes/calendars, and rejects incompatible
nonvertical dimensions/coordinates. Seven negatives cover time, cycle, member,
horizontal labels, vertical attributes, overlapping native-index conflicts and
reused indices. Structural NaNs are not physical samples, are never filled, and
cannot enter separately assembled exact native products.

- Both h5netcdf and netcdf4 tests observe actual backend `_getitem` requests,
  after xarray's indexing decomposition. Internal reads select times 0/2,
  U/V850/700/500 and Z850/700 only: no time 1, 300-hPa or internal Z500 payload.
  The separate product reads Z500 only. Values, level order, attributes,
  native-index mapping and structural NaNs are checked.
- Actual `codes_get_values` instrumentation observes exactly 16 selected
  internal decodes, then exactly two separate Z500 product decodes. No excluded
  sample/level is decoded; handles are released.
- Real AROME NetCDF centroid/multifield and sparse GRIB multifield integrations
  pass after removing the provisional gate. The GRIB integration selects hours
  0/12, excludes hour 6, and exports native U500 only. An ordinary-reader
  subprocess checks values, clocks, levels and centres without importing
  FrameIt. `rtol=0, atol=1e-4 m/s` bounds the fixture's 24-bit GRIB packing
  error; this is numerical agreement, not bitwise or universal scientific validity.
- The five formerly unitless fixture nodes genuinely pass; they are not
  exempted, skipped or relabelled producer failures. Missing trajectory units
  still fail in C5's strict negative tests.

### Fresh commands and retained results

Every pytest command below uses this full prefix, explicitly including the
fixture root:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest
```

Append the following argument sets (test paths are under
`src/frameit/testing/numerical/`; actual commands used the full paths):

1. Focused: `-q test_v3_regions.py test_geographic_lookup.py
   test_v3_netcdf_reads.py test_v3_grib_reads.py
   test_fa_mapping.py::test_fixed_and_prescribed_tracking_keep_requested_centres
   test_polar_wind.py::test_supplied_centres_survive_tracker_and_postprocessing
   --tb=short`. **158 passed**, exit 0.
2. Covering: `-q` plus the twelve initial covering files above and complete
   `test_fa_mapping.py test_polar_wind.py --tb=short`.
   **873 passed, 46 failed, 1 error**, exit 1. Every failed/error ID matches Task05.
3. Required: the exact unfiltered seven-file command listed above, freshly run
   with the explicit fixture prefix. **79 passed, 80 failed**, exit 1.
   A second run with `--tb=short` and JUnit XML has the same result. Each of
   those 80 IDs and its actual schema/input failure evidence is retained.
4. Full diagnostic: `-q --tb=short`, unfiltered; the completed result and
   chronological distinct-node totals are recorded below.

The focused, covering, required XML rerun and full commands each additionally
set `--junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-06-resume-<lane>-final-01.xml`,
with lanes `focused`, `covering`, `required` and `full`. Matching TXT files retain
stdout/stderr. `task-06-resume-required-exact-01.txt` retains the unchanged
seven-file command's separate output.

The evidence helper orders historical and resumed XML by suite timestamp,
retains every failed/error ID with Task05/current messages, and counts each
node's latest observation once. Its resumed node/failure/required ledgers use
new filenames. Existing failures remain failures, never a passing-suite claim.

Ruff on all **18 task-related Python files** versus the same base:
**59 → 59 existing diagnostics, zero new**. The three resumed E501 additions
found in the precheck were fixed by line wrapping only. Raw precheck/final
JSON and deltas remain separate. `git diff --check` exits 0. Lead-owned
documentation Python changes are not part of this task-code lint comparison.

Independent review, public documentation/build/GUI verification and any human
scientific acceptance remain lead-owned. No staging, commit, push, subagent,
production run or package/native-stack change was performed.

### Final full diagnostic and distinct totals

The fresh unfiltered full diagnostic completed after the authorized fixes:
**1,594 passed, 468 failed, 2 errors, 4 passing subtests**, exit 1, 319.94 s.
The 470 failed/error IDs **exactly equal** Task05 fix-2's baseline failed/error
set: **zero new and zero removed**. Those failures remain failures; neither a
passing full suite nor scientific qualification is claimed.

| Final check | Observed result |
|---|---|
| Focused | 158 passed |
| Covering | 873 passed, 46 failed, 1 error; all 47 failed/error IDs in Task05 |
| Exact required seven files and XML rerun | 79 passed, 80 failed; all 80 have individual current schema-rejection evidence |
| Unfiltered full | 1,594 passed, 468 failed, 2 errors |
| Distinct nodes, latest observation once | 2,064: 1,594 passed, 468 failed, 2 errors |
| New Task06 nodes | 57 passed, 0 failed/error |
| Five authorized fixture nodes | 5 passed, not exempted or skipped |
| First full Task06 run's nine new failures | All nine now pass in the fresh full run |
| Task-related Python Ruff versus base | 59 → 59 diagnostics, 0 new |
| `git diff --check` | Exit 0 |

The four passing subtests are reported separately, not added as extra nodes.
Individual failed/error names and both Task05/current messages are retained in
the newly named `task-06-resume-failure-ledger.md`,
`task-06-resume-required-failures.md` and `task-06-resume-observed-nodes.md`,
beside the raw TXT/XML. Chronological aggregation and the assert-based final
set/count checks are retained as `task-06-resume-suite-comparison-final-01.txt`
and `task-06-resume-evidence-selfcheck-final-01.txt`. All artifacts are under
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/` in the implementation workspace.

For portable comparison, the following is the **complete failed/error module
distribution**. The comparison was made by full node ID, not merely by matching
counts. `test_repository_examples.py` is under `docs/`; every other module below
is under `src/frameit/testing/numerical/`.

| Failed/error module | Task05 IDs | Resumed IDs | New IDs |
|---|---:|---:|---:|
| `test_repository_examples.py` | 8 | 8 | 0 |
| `test_arome_fa_coupling.py` | 11 | 11 | 0 |
| `test_configuration_integration.py` | 3 | 3 | 0 |
| `test_configuration_v2_1.py` | 100 | 100 | 0 |
| `test_coupled_shared_polar.py` | 13 | 13 | 0 |
| `test_croco_mnh_coupling.py` | 24 | 24 | 0 |
| `test_croco_netcdf.py` | 11 | 11 | 0 |
| `test_croco_vectors.py` | 6 | 6 | 0 |
| `test_documentation_example.py` | 3 | 3 | 0 |
| `test_fa_contracts.py` | 6 | 6 | 0 |
| `test_fa_cubes.py` | 7 | 7 | 0 |
| `test_fa_environment.py` | 2 | 2 | 0 |
| `test_fa_epygram_geometry.py` | 1 | 1 | 0 |
| `test_fa_epygram_surfex.py` | 1 | 1 | 0 |
| `test_fa_mapping.py` | 2 | 2 | 0 |
| `test_fa_pipeline.py` | 19 | 19 | 0 |
| `test_fa_replay.py` | 9 | 9 | 0 |
| `test_fa_resources.py` | 2 | 2 | 0 |
| `test_fa_surface.py` | 4 | 4 | 0 |
| `test_grib_lifecycle.py` | 1 | 1 | 0 |
| `test_grid_representations.py` | 15 | 15 | 0 |
| `test_hpc_execution.py` | 7 | 7 | 0 |
| `test_inspect_metadata.py` | 3 | 3 | 0 |
| `test_mnh_surfex_support.py` | 16 | 16 | 0 |
| `test_multifield_vortex.py` | 13 | 13 | 0 |
| `test_nemo_arome_coupling.py` | 37 | 37 | 0 |
| `test_nemo_netcdf.py` | 20 | 20 | 0 |
| `test_netcdf_assembly.py` | 16 | 16 | 0 |
| `test_polar_axes.py` | 1 | 1 | 0 |
| `test_pressure_centroid_mnh.py` | 5 | 5 | 0 |
| `test_request_selection.py` | 33 | 33 | 0 |
| `test_templates.py` | 46 | 46 | 0 |
| `test_wind_preflight.py` | 14 | 14 | 0 |
| `test_wind_pressure_seed.py` | 1 | 1 | 0 |
| `test_zarr_export.py` | 10 | 10 | 0 |

The two retained error IDs are:

```text
src/frameit/testing/numerical/test_hpc_execution.py::test_concurrent_cli_attempts_spawn_and_sync_export_exactly
docs/test_repository_examples.py::test_independent_checker_accepts_reference_and_rejects_wrong_time_count
```

No unresolved scope-approval blocker remains. Existing scalar-spacing/moving or
multigrid limits, unbound methods/preparation and empty-input track-only requests
are not newly qualified. The native-extension size warning and deprecation
warnings remain; no environment repair was attempted. Public documentation,
publication/Sphinx/live-GUI verification and independent scientific/task review
remain with the lead. Nothing was staged or committed by this implementer.

## Independent-review fix round 1/5: I1–I4

Base: `73c4147ba2bcb45672b56d8808a7ba2dbc86a934`.
Reviewed tree: `fd69529085a8f87ccda6dbe5b39cf7dcc46f8dee`.
Only `src/frameit/core/coupled.py` and
`src/frameit/testing/numerical/test_v3_regions.py` change in the production/test
fix relative to that tree. Public docs and STATE remain lead-owned; internal
evidence/helper/log updates are separate. No staging, commit, push, subagent,
package/environment change, native repair or warning suppression.

### Changes and RED/GREEN

Each root cause was reproduced and verified before the next production fix.
All pytest commands explicitly set
`FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01"` and use
`PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q`.
Artifacts below live under `.superpowers/sdd/CHECKLIST_FOR_AGENTS/`.

| Finding | Root fix and behavioral check | Observed RED → GREEN |
|---|---|---|
| I1 | Resolve native directions from adapter/axis evidence, never latitude storage order. Real transposed-geography NetCDF crop with unequal x/y widths compares native samples and geographical positions. Ambiguous axes fail rather than being guessed. | 1 failed → 4 passed including native/padding/GRIB controls |
| I2 | Return an existing-unit-normalized metadata-only internal geometry view for containment/lookup. Degree/radian grids select x=4/y=2 and identical native samples. Product geography keeps original numbers/units; added degree coordinates and provenance contain degree-valued positions. | 1 failed at containment → 4 passed |
| I3 | Restore the existing NetCDF-only preceding-hour guard before authorization/ownership, including before deferred-tracker inspection returns. A real GRIB-atmosphere/NEMO-mean bind fails with no payload decode or output root. Existing NetCDF and interval/cycle/bounds cases remain. | Corrected fixture: 1 failed (`DID NOT RAISE`) → 7 passed |
| I4 | Group selected records by path once and reuse the groups for temporal metadata. Keep selected clock/file order and empty/unselected entries; no payload read or archive run. | 4 operation-count failures → 4 passed |

Raw logs: `task-06-fix-1-red-I1.txt` / `green-I1.txt`,
`red-I2.txt` / `green-I2.txt`, `red-I3-02.txt` / `green-I3.txt`,
`red-I4.txt` / `green-I4.txt`, each with the `task-06-fix-1-` prefix.
The first I3 fixture attempt (`red-I3.txt`) used an incorrect GRIB pressure
type and failed on missing `prmsl`; it was corrected to `meanSea` before the
actual RED, without changing production. No historical artifact was overwritten.

Tests are the new nodes in `test_v3_regions.py`, with `--tb=short`:

```text
test_fixed_crop_uses_native_axes_when_geography_is_transposed
test_equivalent_geography_units_keep_native_products_and_degree_grid_facts
test_preceding_hour_rejects_grib_atmosphere_before_binding_or_payloads
test_regional_inventory_groups_records_once_without_changing_clocks
```

The I3 GREEN uses the whole file with `-k preceding_hour`; I4 also uses `-s`
to retain measured counters. Full exact argument lists and controls are in
the implementation report.

The I4 counter results (two metadata sources, no payloads) are:

| Policy / total records | RED visits / time reads | GREEN visits / time reads |
|---|---:|---:|
| Exact / 24 | 2,220 / 2,172 | 72 / 24 |
| Preceding-hour / 24 | 2,436 / 2,208 | 96 / 60 |
| Exact / 48 | 15,672 / 15,576 | 144 / 48 |
| Preceding-hour / 48 | 16,392 / 15,648 | 192 / 120 |

Grouping scans are linear in selected record count; available per-path labels
still need ordering. This is operation-count evidence, not a measured archive
speedup or claim that every workflow stage is linear.

Internal normalization never changes the native product dataset. The I2
ordinary xarray reopen checks also verify unchanged source bytes, NaNs/zeroes,
native geographical attributes, `center_*`/`grid_selected_*` degree units and
degree-normalized `grid_geometry.sample_lat/sample_lon` facts. No numerical
method, format admission, record selection or scientific tolerance was added
or widened. Existing tracker options and internal/product stencils are unchanged.

### Fresh focused/covering checks

Focused `test_v3_regions.py --tb=short` plus JUnit:
**52 passed**, exit 0, 22.29 s.

The original fourteen-file covering lane was rerun with two existing geometry
nodes added from `test_configuration_v2_1.py`:
`test_geometry_rejects_anisotropy_and_conflicting_inputs` and
`test_geodesic_and_projected_unit_equivalence`.
Result: **880 passed, 48 failed, 1 error**, exit 1, 89.34 s.
All 49 failed/error IDs match Task05 and the reviewed snapshot. The two legacy
geometry nodes still fail at their old schema producer before numerical
inspection; they are not passed or skipped geometry validation. The new v3
regressions exercise the actual geometry and crop behavior.

This covering lane includes geographic lookup, all selected readers, native
extraction, v3 execution/metadata, binding/configuration and resource callers;
no narrower shared-caller omission is being hidden. Exact full paths/arguments
are recorded in the implementation report and matching raw
`task-06-fix-1-{focused,covering}-final-01.txt/.xml` artifacts.

Ruff on all 18 Task06 Python files versus both Task05 and the reviewed tree:
**59 → 59 existing diagnostics, zero new**. The precheck's two new E501s and
one explicit-zip validation diagnostic were fixed in the new test only.
Separate reference/current JSON and deltas use
`task-06-fix-1-ruff-{review,task05}-final-01-*` names.
`git diff --check` exits 0; the real index remains empty.

Required/full completion, distinct totals and failed-node comparisons follow
below. M1 remains separately deferred to Task19/final warning triage; no native
stack repair, bounds-encoding/concat cleanup or warning suppression was done.

### Fix-round final verification and comparison

All fixture-dependent commands explicitly used the approved fixture root.
The exact seven-file command above was run unchanged, then repeated with
`--tb=short` and JUnit XML for individual structured failure evidence.
Only one covering and one unfiltered full diagnostic were run this round.

| Fix-round lane | Observed result | Delta versus reviewed full and Task05 |
|---|---|---|
| Focused regional file | 52 passed | All seven new fix cases pass |
| Covering | 880 passed, 48 failed, 1 error | All 49 failed/error IDs already present |
| Exact required seven files and XML rerun | 79 passed, 80 failed | All 80 IDs already present, with individually checked current/Task05 schema-rejection messages |
| Unfiltered full | 1,601 passed, 468 failed, 2 errors; 4 passing subtests | Exact same 470 failed/error IDs, zero new/removed |
| Distinct nodes, latest observation once | 2,071: 1,601 passed, 468 failed, 2 errors | Every old reviewed and Task05 node retains its observed status |
| Cumulative Task06 new nodes | 64 passed | Includes seven new fix-round nodes |
| Authorized unit-fixture nodes | 5 passed | No exemption, skip or weakened assertion |
| Ruff, both references | 59 → 59 existing diagnostics | Zero new |
| Whitespace/index | `git diff --check`: exit 0; real index empty | No staging/commit |

Full wall time: 302.18 s; exit 1; 4,405 warnings, no skips. Passing subtests
are not counted as extra distinct nodes. The full suite remains failed;
the old producer-blocked workflows are not verified successes.

The full command was:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-06-fix-1-full-final-01.xml
```

The exact required command is the seven-file command listed above with the
same fixture/environment prefix; the XML rerun additionally used
`--tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-06-fix-1-required-final-01.xml`.
Fresh TXT/XML use `task-06-fix-1-{focused,covering,required,full}-final-01`;
the separate exact required output is `task-06-fix-1-required-exact-01.txt`.

`task-06-fix-1-suite-comparison-final-01.txt` and
`task-06-fix-1-evidence-selfcheck-final-01.txt` assert exact failed/error set
equality with both baselines and complete preservation of all existing node
statuses. The seven new full-suite nodes are genuine passes. The earlier
portable 35-module failed/error distribution and the two error IDs remain
unchanged, verified by full node identity rather than counts alone.

Every failed/error name and Task05/reviewed/current message remains in
`task-06-fix-1-failure-ledger.md`; the exact required comparison is in
`task-06-fix-1-required-failures.md`; deduplicated latest statuses are in
`task-06-fix-1-observed-nodes.md`. These and all raw artifacts reside under
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/` in the implementation workspace.
Historical snapshots/ledgers remain unchanged. The evidence helper aggregates
the new snapshots chronologically rather than relabelling old failures.

The restored scientific contract is native directions and consistent internal
unit interpretation, not a new method. The fixed transposed crop changes its
previously wrong samples; equivalent radian geometry works without changing
native product geography. Unsupported preceding-hour GRIB now fails under the
existing NetCDF boundary. Grouping preserves selection and metadata meaning.
All selected-reader/payload-stencil regressions remain covered and passing.

M1 and existing warnings remain deferred; the old 470 failed/error nodes are
still limitations. Public documentation/STATE/build/GUI work remains with the
lead. No source-data mutation, package/environment/native repair, warning
suppression, subagent, staging, commit or push was performed. The original
reviewer's I1–I4 closure and new-fix-diff breakage review remain required.

## Independent closure and final lead checks

The independent reviewer closed I1–I4 after fix round1/5 and approved Task06
spec and quality, with no new Critical/Important/Minor breakage. M1 remains
assigned to Task19/final warning triage. No human scientific/usability approval.

Lead raw-XML assertions corroborate all node/status preservation and each
required failure's baseline/current schema evidence. Fresh precommit:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_regions.py --tb=short
```

Observed52 passed/342 warnings in22.38s. Final full1601pass/468fail/2errors is
still not green. Combined source/test and documentation-test Ruff covers19
changed Python files:64baseline/64current/zero new diagnostics.

The final-code fixed page executes verbatim; its separate ordinary reader checks
exact2×5×5 values, units, zero/NaN, both clocks and unchanged input bytes.
Strict Sphinx32/publication/13unit/4plot-release tests plus2subtests pass. All13
affected HTML pages equal desktop/actual320-reviewed31 bytes; live32 remains
available. No source-data mutation, package change, push or method promotion.
