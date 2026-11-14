# Task05 — native execution and selected-record readers

Internal, portable evidence; not published user guidance.
Base: `37aaf5f9b692cc60f9921a5191e0484fd12e6620`.
Python3.13.18, Conda `frameit_env`, selected checkout via `PYTHONPATH`.
Task05 native/read gate approved after both Important findings closed.

## Scope and current status

The lead implemented the first native NetCDF slice, then an independent reviewer
closed both Important findings before adapter work started. That gate approved
the native slice only. Three disjoint workers extended NetCDF model families,
GRIB and FA. The lead integrated their actual reader interfaces.
No environment/dependency change, native-stack workaround, data download,
production run, shared-fixture edit, push or scientific approval belongs here.

Native field extraction copies values, units, sampling and missingness without
implicit wind companions, collocation, basis rotation, unit normalization,
centres, tracking, polar work or diagnostics. Bound vertical-coordinate metadata
can change labels/units without changing physical arrays.
The synthetic cases establish the stated numerical/reader behavior, not validity
for every producer, grid, regime, packing or calendar.

## Integration and downstream handoff

- `core.coupled.bind_sources(conf)` calls the existing inventory-only
  `prepare_sources`, binds each actual child via `bind_source`, then deliberately
  copies bound request/source snapshots into the parent. It returns
  `(report, children, plans)`; execution uses those same consumers, not rebuilt
  unbound children. Pending maps never authorize public execution.
- `execute_simulation` binds before owning a run root, rejects unresolved region/
  non-native methods, checks an explicit API inventory against bound files, and
  protects product/reserved-record destinations against source-file aliases.
  `FrameitRunner(..., prepared_sources=None)` carries prepared consumers.
- `run_native_sources` loads independent source clocks without intersection.
  `runner.field_products[(source, product)]` holds each native product. Explicit
  output fields that also serve as formula coordinates are promoted consistently
  before exact merging; support-only arrays remain coordinates/internal inputs.
- The native exporter uses the existing atomic writer with the request plan's
  `products/<run>.<source>.model_grid.nc` or `.zarr` paths and writes no trajectory.
  Status, results and provenance tolerate absent track attributes.
  Full writer naming/coordinate qualification remains Task10; per-publication
  failure bookkeeping and common report serialization remain Tasks12–13.
- Native public execution currently dispatches NetCDF/GRIB with actual bound
  records. FA public interpretation/scaling remains pending for Task07.
  Direct numerical APIs retain their omitted-argument behavior.

The three existing grouped loaders accept optional
`selected_records=None, source_plan=None`. On the selected route:

```text
selected_records = complete executable Task04 binding mapping
source_plan = owning inventoried source, including record_inventory/native_grids

return (user_groups, tracker_groups)
user_groups[actual_grid_id] = bound native model-grid fields
tracker_groups["internal"][actual_grid_id] = internal native support
```

`binding.records` is not an export instruction. Product and dependency
descriptors remain separate even for one field name: output `[5,0]` is not the
internal `[5,6,0,1]` read union. No loader may discover another provider, widen
time/cycle selection or choose competing records.

### NetCDF/Meso-NH/NEMO/CROCO

`concat_nc2ds_by_vert_coord` opens backend-lazy originals, applies payload and
coordinate locators plus list-valued native vertical positions, then constructs
Dask chunks from those selected views. Oversized requested time/level chunks
cannot expand logical scientific requests to excluded samples.
Existing coordinate units, bounds, clocks/calendars, native sample indices and
moving geography are retained. A one-dimensional auxiliary clock can swap its
actual native sample axis before normalization; original index labels survive.

NEMO and CROCO reuse existing model admission without invoking ocean-current
analysis. `prepare_croco(ds, conf, *, native_axes=None)` additionally accepts
original coordinate axes for monotonic source-sigma validation after a reversed/
sparse selection. Selected formula coefficients still undergo existing checks;
native-index coordinates are not renumbered.
Already-bound `coordinates`/`formula_terms`/`cell_measures` support accompanies a
product as ordinary-reader coordinates. Ancillary-only inputs are not extra
physical exports. Static arrays from one provider stay static; successive static
providers follow their own selected samples instead of choosing first/last.

Tests instrument real H5NetCDF/NetCDF4 backend `_getitem` requests after xarray
indexing decomposition, not replacement loaders. The central check additionally
covers SciPy/NetCDF3. This measures logical payload requests, not compressed
storage-block read amplification or a whole-run memory ceiling.

### GRIB

`concat_grib2ds_by_vert_coord` checks the original closed-pool record and seeks
exact message offsets/lengths. Only selected encoded messages are inspected.
Delayed work creates/release-scopes a handle with the existing cfgrib lock and
decodes that selected message. No persistent native handle or disk index is
needed. Error paths release their own handles and retain registry rollback.

Native pressure/nonpressure level order, singleton axes, cycle/lead/interval
metadata, native member labels, aliases and original units are retained.
Bitmap missingness becomes NaN; valid zeroes and valid sentinel-like numbers
remain data. Each requested message is decoded as a whole horizontal field;
a later horizontal subset does not bound decoder memory to output size.
Header identity checks are not content checksums or cross-decoder qualification.

### FA stage boundary

The grouped FA loader has the optional keywords but still rejects unresolved
public source interpretation/decode-time scaling. It does not turn genuine
pending Task04 maps into executable bindings.

The internal numerical leaf:

```python
fa_selected_array(record, source_plan, *, options, diagnostics_path=None)
```

uses selected raw/cube descriptors from the closed pool on already-admitted,
explicitly declared numerical FA paths. It retains record-local evidence,
provider/time/cycle/zone/shape/eligibility and size/mtime freshness. It reuses the
existing isolated helper and strict scaling/explicit fallback policy.
`FaArray` now compares invariant returned descriptor/shape facts with its
original selected descriptor before returning values. Expected post-decode
mask/scaling observations are not confused with immutable input facts.

Real helper `read` requests prove exclusion of unselected files/times/records,
selected cube order, independent same-name support, lazy construction, failure
cleanup, zero/NaN and original data preservation. This is locator-mechanism
evidence, not public FA grouped output, a new support planner, broader profile
admission or scientific scaling sign-off.

## RED/GREEN and independent native-slice gate

Raw logs live in the ignored plan workspace. All Python commands used
`PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest`.

- First two required execution cases: RED2 at the unbound guard, then GREEN2 with
  independent ordinary-reader reopening, source digests and no-clobber checks.
- Product/input collision and external API inventory: RED2, then both corrected
  before output artifacts. Later combined native checks cover them.
- Native-slice independent findings: log aliases modified inputs and
  `valid_time(sample)` failed concatenation. Covering tests were RED3→GREEN3.
  The shared logging boundary now exclusively creates a file and suffixes
  occupied names; symlinks, hard links and unrelated existing logs are untouched.
  The shared clock normalizer retains native sample labels. Scoped re-review:
  both Important findings ADDRESSED; no new fix breakage; slice spec PASS,
  quality APPROVED. Intentional optional-entrypoint warning accounting remains
  a deferred Minor, not silently suppressed.
- GRIB runner integration: RED1 at absent dispatch→GREEN1. A fresh ordinary
  reader verifies literal native-U values/units, singleton vertical axis,
  selected00:00/02:00 times, no companion/diagnostic and unchanged input bytes.
- CROCO explicit `zeta` output plus temperature formula support: RED1 at
  coordinate/data-variable ambiguity→GREEN1 after consistent output promotion.
  A fresh ordinary reader checks both physical arrays, native sigma selection
  and available formula dependencies without importing FrameIt.
- Existing numerical speed-only caller: RED1 at the new unchecked
  `schema_version` attribute→GREEN1 after optional-version dispatch was restored.
  The original test and numerical configuration are unchanged.

Adapter reports contain exact commands and complete RED/GREEN logs:
NetCDF51 lane cases/156 combined passes at its recorded snapshot; GRIB31 new/
66 scoped passes; FA42 new/69 focused-resource passes and188 binding/inventory
passes. These reported snapshots are not a final lead integration result.
No worker staged/committed or changed shared fixtures/environment.

## Remaining limits and checks

- Several varying native NetCDF sample axes have no admitted assembly contract:
  the reader fails before scientific values instead of flattening or gap filling.
  One varying axis, including selected leads from one cycle, is exercised.
  The unsupported layout is not a successful reader qualification.
- Native GRIB requires compatible time/member/vertical stencils within a role;
  mixed deterministic/member axes, ambiguous surface levels, inconsistent
  interval evidence and changing per-sample support fail explicitly.
  Rectangular inventoried Ni/Nj geometry is tested, not every grid/packing.
- Conflicting same-name native-grid coordinates cannot yet share one source
  publication; exact merging fails rather than silently aligning/dropping them.
  Task10 must finish multi-grid qualification and the complete writer contract.
- Public FA interpretation/grouped dispatch, operation-specific tracker/
  transform/polar planners and their eligibility remain later gates.
- The broader worker diagnostics contain named legacy public-v2 producer
  failures. The one real numerical caller regression they exposed is corrected
  above. Fixture-dependent checks must use the approved read-only data root.
- The NetCDF worker's full-suite attempt timed out without captured results;
  it confirmed its child was no longer running. The completed lead diagnostic
  below supersedes that missing result, not its timeout history.
- Strict documentation build/publication, final rendered-page inspection,
  combined independent review, final evidence and a focused local commit remain
  required before Task05 completion.

## Integrated lead verification

The tested code/public-doc checkpoint is staged tree
`d47ff97972f72912b6ef744ed7cf236fcd8b264d`, not a code commit.
Only the figure caption and internal records changed afterward.
All raw logs/XML use `task-05-` names in the ignored plan workspace.

Required command:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py::test_native_scalar_roundtrip src/frameit/testing/numerical/test_v3_execution.py::test_sources_keep_independent_clocks src/frameit/testing/numerical/test_v3_execution.py::test_readers_obey_selected_records
```

**5 passed**,10 warnings. The reader node now covers h5netcdf, netcdf4 and SciPy.

Main combined integration:

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_netcdf_reads.py src/frameit/testing/numerical/test_v3_grib_reads.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_output_layout.py::test_direct_export_uses_products_directory src/frameit/testing/numerical/test_logging.py src/frameit/testing/numerical/test_wind_collocation.py::test_runner_loads_speed_only_native_dependencies --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-05-integrated.xml
```

**467 passed,2 subtests passed**,29 warnings. Includes all136 new Task05 cases,
326 schema checks, direct export, logging and the corrected numerical caller.
Warnings: one existing binary-size warning,27 netCDF4/NumPy shape deprecations
and the deliberate optional-entrypoint warning.

Delivered binding/inventory regression command:

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_grid_representations.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_netcdf_assembly.py src/frameit/testing/numerical/test_grib_lifecycle.py -k v3 --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-05-binding-regressions.xml
```

**233 passed,137 deselected**,19 existing warnings.

HPC/FA resource and numerical callers:

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_fa_io.py src/frameit/testing/numerical/test_fa_resources.py src/frameit/testing/numerical/test_fa_geometry.py src/frameit/testing/numerical/test_fa_spectral.py -k 'not test_invalid_execution_schema and not test_exclusive_run_ownership_and_early_no_clobber and not test_concurrent_cli_attempts_spawn_and_sync_export_exactly and not test_batch_overrides_dry_run_does_not_claim_output and not test_cli_processing_failure_never_marks_completed and not test_incomplete_tracking_is_explicit_and_strict_policy_fails and not test_cancellation_and_same_root_exclusion and not primary_pair_failed_transfer' --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-05-resource-regressions.xml
```

**43 passed,14 deselected**,4 existing warnings. Only known future-dependent
public-v2 execution families are excluded here; the full diagnostic runs them.

The unchanged31-case legacy assembly/import command in
`task-04-checks.md:464-466` was also rerun with an XML report:
**31 passed,33 deselected**,71 existing warnings.
These four combined selections total774 passing targeted cases; the required5
are a subset, not additional distinct cases.

### Complete project diagnostic — not a pass

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-05-full-suite.xml
```

Exit1: **468 failed,1523 passed,2 errors,4 subtests passed**,4049 warnings,
296.79 seconds. No timeout, skip/exclusion filter or failure suppression.
All470 failure/error summary node IDs exactly match each of the three retained
Task03 full-suite logs, with no added or removed failing node.
This is a node-set comparison, not proof of full integration or scientific validity.

The two setup errors remain:

- `test_hpc_execution.py::test_concurrent_cli_attempts_spawn_and_sync_export_exactly`
- `docs/test_repository_examples.py::test_independent_checker_accepts_reference_and_rejects_wrong_time_count`

The XML contains428 strict-v3-admission failures/errors and42 wrapper failures in
CLI/template/optional-import subprocess cases. Their public-v2 producers remain
Tasks15–16 dependencies, not successful public pipelines here.
Every failed/error node is retained by name in
`task-05-full-suite-failures.md`, with full tracebacks in
`task-05-full-suite.txt` and XML; exact comparison is
`task-05-full-suite-delta.txt`. These ignored execution artifacts are preserved
for handover. No complete-suite green or general native qualification is claimed.

### Documentation and review

Strict Sphinx/publication and13 publication unittests pass for iteration21.
The preceding iteration20 additionally passed4 plot/release tests and2 subtests
with15 existing backend warnings. Both affected pages were inspected live at
desktop880px and actual320px; the selected-message cost, native-basis distinction,
multi-axis clock and coordinate-collision limits fit without page overflow.
Existing code scrolling/menu behavior and unmodified figures remain available.
The figure caption now explicitly identifies the regional track/scalar example;
that final caption still needs its strict/reviewed rendered iteration.
No new artwork, scientific figure or site style was introduced.
Combined independent Task05 review is the next gate; no approval is implied.

Final caption verification: iteration22 failed strict figure-caption indentation.
After correction, iteration23 strict Sphinx, publication boundary and13 publication
unittests all passed. Its caption was inspected live at desktop880px and
actual320px; it fits and distinguishes the regional track example from native
full-domain copying. Input HTML23 is byte-identical to inspected21. The canonical
23 output page and owned preview remain available. These are agent checks,
not human acceptance. A fresh full Task05 reviewer is active; approval is pending.

## Full-review fix round1

The full reviewer independently reproduced nested-source deletion on Zarr
replacement and a cross-format execution override publishing under the wrong
planned filename. Both require closure before the Task05 commit.

Corrections:

- `execute_simulation` checks the requested engine against declared
  `output.format` before binding or run ownership. Cross-format overrides fail
  actionably; same-format NetCDF engine overrides remain available.
- Destination protection includes every inventoried path, deduplicated alias and
  declared excluded file. It checks lexical absolute, parent-resolved and fully
  resolved source locations before replacing a directory. Existing same-file/
  hard-link checks remain. No output/status/log is written by these rejections.
- Source `files`/`exclude` retain absolute alias paths through the private
  configuration path helper. The FA interpreter caller still preserves its
  symlink. The NetCDF resource owner resolves only the path handed to xarray,
  retaining declared inventory/cache keys and correct `symlink/../file` meaning.
  This is source-identity preservation, not broader discovery or new schema.

TDD:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py -k 'store_containing_source_paths or format_override_must_match' --tb=short
```

Initial seven cases: RED7 (`DID NOT RAISE`), then GREEN7. Intermediate6-pass/
2-fail covering run exposed aliases erased before inventory. Added parent-
traversal and directory-alias controls were each observed RED before their
corrections. The final central suite has23 cases: seven containment variants,
two conflicting formats and two safe same-format controls, plus the original12.
Safe overwrite runs reopen both NetCDF/h5netcdf and Zarr outside FrameIt and
check values/metadata, filename, actual storage, effective format, status and
unchanged source bytes. No scientific processing or writer algorithm changed.

Final checks reran the exact required command and the four integrated selections
above, with XML names `task-05-fix-1-{integrated,binding,resources,assembly}.xml`:

- required5 passed,10 warnings (2.53s), a subset of main integration;
- main478 passed,2 subtests,41 warnings (40.82s);
- binding/inventory233 passed,137 deselected,19 warnings (25.63s);
- resources43 passed,14 deselected,4 warnings (7.60s);
- numerical assembly31 passed,33 deselected,71 warnings (1.77s).

XML assertions establish785 distinct passing targeted nodes, no overlap,
failures, errors or skips. The11 additional cases raise the Task05 new-case total
from136 to147. Ruff comparison across all15 changed Python files is81 baseline/
81 current with no new diagnostics. The larger baseline includes the newly
claimed configuration/loader files. The first comparison found one new E501;
it was wrapped without semantic changes before the final comparison.
Raw evidence is retained in `task-05-fix-1-required.txt`,
`task-05-fix-1-integrated.txt`, `task-05-fix-1-regressions.txt` and
`task-05-fix-1-preservation.txt`.

The unfiltered full-project diagnostic was rerun:

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-05-fix-1-full-suite.xml
```

Exit1:468 failed,1534 passed,2 errors,4 subtests,4061 warnings,302.30s.
All470 failure/error summary nodes match the preceding Task05 diagnostic and all
three Task03 diagnostics exactly. Full names, tracebacks and delta remain in
`task-05-fix-1-full-suite-failures.md`, `.txt`, `.xml` and
`task-05-fix-1-full-suite-delta.txt`. This is not full-suite green.

Documentation:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-24
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-24
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_documentation_plots.py docs/test_release.py
```

All exit0: strict build without warnings, publication passed,13 unittests,
4 tests plus2 subtests/15 existing warnings. Changed input/output paragraphs
were inspected live desktop880px and actual320px, with no page overflow or
missing images. Canonical output24 and the owned server remain available.
This is agent inspection, not human acceptance.

Deferred Minors remain in `STATE.md`: binding-warning log retention (Task14),
the later polar filename heading (Task10) and optional-entrypoint-warning
accounting (Task19/whole-branch triage). Scientific/format eligibility, whole-
archive resources and all earlier stated later-task gates remain unresolved.
Scoped independent closure of the two Important findings is the next gate.

## Full-review fix round2 — intermediate symlinks

Scoped round1 closed the format finding but reproduced a remaining source-path
loss: an outside declared link could pass through an inside-store link to an
outside physical file. The store replacement removed that required middle link.
Physical bytes were unchanged, but the declared input became unreadable.
Important1 remained open; no separate new regression was reported.

The shared execution guard now collects physical targets and every required
symlink entry, including parent-directory links and relative link targets.
A visited-path set avoids repeat traversal. It uses ordinary `Path` operations
rather than implementing another filesystem resolver. Same-file/hard-link and
cross-format checks are unchanged. Only execution and its central test changed.
No extra user-facing prose is needed: this makes the documented alias-preservation
rule hold for intermediate links as well.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py -k two_hop --tb=short
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py --tb=short
```

RED3: leaf, directory and excluded two-hop aliases all completed instead of
rejecting the replacement. GREEN26 central cases/39 existing warnings (8.85s),
including all three new cases, previous safety/format controls and normal runs.
The negative cases assert early failure, unchanged prior store contents and
still-readable declared input bytes, with no run status or log created.
Raw evidence: `task-05-fix-2-red.txt/.xml` and `task-05-fix-2-covering.txt/.xml`.
The current integration/full-project/documentation commands are running and are
not yet results. The original reviewer will verify this focused correction.

Subsequent integrated verification:481 passed/2 subtests/44 warnings (40.05s),
233 binding/inventory/19 warnings (26.54s),43 resources/4 warnings (7.58s) and31
assembly/71 warnings (1.61s). The same four commands/selections from round1 were
rerun, using `task-05-fix-2-*.xml`; their combined raw output is
`task-05-fix-2-integrated-regressions.txt`. XML assertions confirm788 distinct
targeted passes without overlap/failures/errors/skips. All150 new Task05 cases
are included. Fifteen-file Ruff remains81baseline/81current/no new diagnostics.
Strict25/publication/13 unittests passed; both affected HTML pages exactly match
desktop/320px-reviewed24. The retained live preview now shows25.

Final unfiltered diagnostic:

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-05-fix-2-full-suite.xml
```

Exit1:468 failed,1537 passed,2 errors,4 subtests,4064 warnings,304.31s.
All470 failure/error IDs match fix1, the preceding Task05 run and all three
Task03 runs exactly. Names, tracebacks, XML and asserted delta are retained as
`task-05-fix-2-full-suite-failures.md`, `.txt`, `.xml` and
`task-05-fix-2-full-suite-delta.txt`; comparison output is appended to
`task-05-fix-2-preservation.txt`. This is not full-suite green.
Scoped independent closure remains pending.

## Final independent closure and precommit check

Scoped fixround2 independently closes Important1, preserves Important2 and finds
no new breakage or additional out-of-scope issue. Spec PASS, task quality APPROVED
for this milestone. The reviewer's full-diagnostic wording was pending at its
snapshot; the lead's completed full result and470-node comparison above are the
final diagnostic evidence, not a full-suite pass.

The exact checklist command was rerun after closure:5 passed/10 warnings/2.57s,
on unchanged approved source. Raw `task-05-precommit-required.txt`.
The handoff is frozen in `STATE.md`; a focused local commit follows.
Binding-warning log retention, the later polar heading and optional-entrypoint
warning accounting remain explicitly deferred to their owning tasks.
