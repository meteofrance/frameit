# Task10 C7 checks — frozen verification

This is an internal development record, not published user guidance or scientific
approval. Base: `393e7d92ddafefd31542ea7a7a49751db860efda`.
Latest: Task10 spec and quality independently approved after N1-only round2;
final precommit53output cases pass. See the appended closure and frozen STATE handoff.
I1–I3/M1 are independently ADDRESSED and unchanged; see the appended section.
Earlier results and lead acceptance below are historical, not current-round
review closure.

## Approved polar boundary

The lead approved the additional output-only boundary in `execute_source_polar`.
The existing runner supplies `output_formatter` after per-field calculations,
before field results are combined. The formatter uses the same inventory-derived
layout as model-grid output and planned descriptors. The hook qualifies vertical
axes, original indices, bounds/CF references and quality-array dimensions together;
it does not rename the polar target or change sampling. Removing only that hook
and its optional parameter makes the complete polar function/module AST identical
to the Task09 base. Final full diagnostic results are recorded below.

## Implemented interfaces and output facts

- Writers consume `request_plan["products"]` and
  `runner.field_products[(source, product)]`. The plan is the sole filename rule.
  `OutputPaths.planned_products(descriptors)` validates those paths; it does not
  sanitize or rebuild them. A custom run name such as `My run-7` is retained.
- `output_grid_layout(source)` resolves names from the entire inventoried native
  grid collection, with bound representation-grid metadata for actual operations.
  `format_model_grid(dataset, grid_id, source, layout)` changes output names and
  references, not preparation, sample values, numeric evaluation policy or units.
- One dataset is assembled per source/model-grid product. Native sample grids
  retain independent axes and exact merges; repeated moving-grid records combine
  on their actual source clocks with `join="exact"`, never an outer join.
- Uncolliding horizontal dimensions/geography use C7:
  atmospheric `y,x / latitude,longitude`; MNH U
  `y,x_u / latitude_u,longitude_u`; MNH V
  `y_v,x / latitude_v,longitude_v`; NEMO's admitted native `y,x`
  `y_t,x_t / latitude_t,longitude_t`; CROCO rho/U/V use
  `y_rho,x_rho`, `y_rho,x_u`, `y_v,x_rho` and corresponding rho/U/V geography.
  This table does not admit any new adapter or establish missing geography.
- Horizontal dimension coordinates are zero-based local positions, also in a
  crop. For an unqualified axis, original labels use
  `<native-dimension>_source_coordinate`, and original source-file positions use
  `<native-dimension>_source_native_index`. Examples: `ni_source_coordinate`,
  `nj_source_native_index`, `ni_u_source_coordinate`,
  `xi_rho_source_coordinate`, `x_source_native_index`, and
  `latitude_source_coordinate`. Original units and values are retained. A source
  without an explicit native dimension-coordinate has only the index auxiliary;
  no physical coordinate is invented.
- Distinct colliding axes are qualified with deterministic inventory metadata
  hashes, not field names or encounter counters. Horizontal collisions qualify
  geography as well; their original-coordinate/index auxiliaries use the
  **qualified exported axis** as prefix. Bounds, coefficient and mapping-name
  collisions receive their own deterministic suffixes. CF references are
  rewritten to those stored variable names. The dataset's
  `frameit_output_coordinates_json` records source-grid identities, original
  dimension/geography mappings and original-auxiliary names.
- Polar output records the same inventoried vertical/coordinate identities, not
  a claim that source horizontal axes are target axes. The internal signature is
  `execute_source_polar(internal, source, binding, conf, centres, *,
  plan_cache=None, output_formatter=None)`. Its only production caller supplies
  `partial(format_polar_output, layout=layouts[source])`. The default leaves
  direct numerical calls unchanged; no registry or public setting was added.
- Known pressure and height-above-ground axes become `pressure` and
  `height_above_ground`, without converting stored numbers or relabelling units.
  MNH/FA full/interface names, native depths and sigma labels retain their meaning.
  Vertical labels, singleton axes, bounds, original indices and formula support
  survive. Distinct pressure axes in Pa/hPa remain distinct, not aligned by shape.
  NetCDF's CF encoder may elide a bounds variable's redundant units attribute;
  its values then use the units of the coordinate declaring `bounds`. Zarr
  retains the explicit attribute. Tests check the same physical unit in both.
- Regional geography is sampled with each field. Moving geography retains time.
  Cropped original indices are sampled/masked with the same crop as the field.
  Centre clocks and source clocks remain separate. Native grid orientation,
  vector basis, W meaning, missingness and existing scientific tolerances remain.
- NetCDF writes NETCDF4 with `netcdf4` or `h5netcdf`; the configured exported
  dimension chunks are passed in element counts. Zarr remains sharded v3.
  Compression defaults remain level 1, coordinate compression off. Source
  packing/layout encodings are discarded, not reapplied to transformed values or
  coordinates; required CF missing/time/coordinate declarations are retained.
- V3 validates explicit storage dimensions against the union of actual exported
  field dimensions. Options that are not applicable still fail in the unchanged
  schema parser. A Zarr run with a NetCDF track still rejects field-writer
  `engine` and `unlimited_time`. Tracks use NetCDF beside Zarr fields.
- Each successful publication appends an actual descriptor to
  `runner.published_products`; execution uses those facts rather than reconstructing
  filenames. Requested field entries carry source, run-relative dataset path,
  stored name, actual dimensions, units and representation. Encoding facts
  include the actual reopened chunk/shard layout, applicable engine/unlimited
  time, compression policy, reader requirements and publication limits.
  A later write failure retains only earlier complete publications in status.
- Existing exclusive ownership, source/alias/overlap checks, atomic publication
  and no-clobber behavior remain. V3 rejects symlink product paths and unrelated
  pre-existing products even with overwrite enabled. Replacing an owned Zarr
  store retains its documented visibility gap; no transaction, append or resume
  guarantee is added. Metadata annotations remain nested and cannot override
  generated provenance; JSON-attribute naming collisions fail.

## Checks observed so far

Use Python 3.13 in `frameit_env`, worktree `PYTHONPATH`, and the explicit compact
fixture root. No package/native environment repair or warning suppression was
performed.

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" TMPDIR=/tmp/opencode \
  conda run -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_v3_outputs.py --tb=short
```

Real ordinary-reader subprocesses import no FrameIt and verify native
float32/float64 values, NaNs, units, clocks, formulas and storage for both formats.
The approved polar boundary has actual prescribed zero/7 K/missing samples,
float32 evaluation provenance, support/status/valid/ring flags, 30 m/40 m labels,
original index `[1]`, bounds, native/centre clocks and geographic positions.
Four add/reorder/filter selections per format retain both axes and input hashes.
The focused output plus existing v3 polar suites passed 155 tests / 702 warnings.
One further old assertion adapted only the GRIB polar output axis
`isobaricInhPa` → `pressure`; its value `[700.]`, sample zero, selected cycle/
decoder, quality and source hash checks are unchanged, with added hPa/index checks.

Final frozen focused checks now include one additional mixed CROCO Zarr ordinary
reader/formula case: **35/35 new cases pass** (all original 32 retained). The
17 original FA record-evidence cases also pass. They specifically cover the
corrected preview regression for an excluded malformed record; native admission
and reader failure assertions were not changed.

The frozen connected 22-file diagnostic is **1,190 passed / 84 failed / 1 error**.
All 1,240 prior node statuses and failing IDs match Task09, with 35 added passes.
The exact required four-file run remains **59 passed / 31 failed / 1 error**,
matching every prior status. These are red diagnostics, not green scientific
acceptance. Original native-axis reader rejection cases remain unchanged, not
exempted.

The **single final frozen full run** completed with **1,874 passed / 468 failed /
2 errors / 2,344 nodes**, plus 4 passed subtests and 5,927 warnings. All **2,309**
Task09 node statuses and the exact **470** failed/error IDs are unchanged; all
35 additions pass. Every node/status and each original/current failure trace is
retained in the task packet. Of 47 changed messages, 46 differ only in temporary
roots; one also has a random attempt-directory suffix. No failure is suppressed
or reclassified.

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" TMPDIR=/tmp/opencode \
  conda run -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_output_layout.py \
  src/frameit/testing/numerical/test_grid_representations.py \
  src/frameit/testing/numerical/test_zarr_export.py \
  src/frameit/testing/numerical/test_hpc_execution.py
```

The complete task packet retains all 91 required and 1,275 connected node
statuses, individual prior/current failure traces and every interim correction.
The mixed-member and excluded-FA preview regressions were fixed in output
projection, not by changing source fixtures, binding/admission or old failure
assertions. No scientific assertion is described as passed when an old producer
fails before reaching it.

Base-relative Ruff has 23 prior / 22 current diagnostics and no new diagnostics
on all 12 changed/new source/test paths; this is not clean lint. The evidence
script's fresh standalone Ruff check passes. The nine compact frozen fixture
hashes match `SHA256SUMS`. Scope checks
preserve the parser, readers, shared fixture producers and scientific numerical
implementations; every old output-assertion adaptation is listed in the detailed
task report.

## Limits and review still required

Independent engineering review, scientific sign-off, human usability acceptance,
archive/HPC runs and general performance qualification remain outstanding.
Canonical docs/examples/figures, strict Sphinx and
publication/rendered-page checks are lead-owned. Earlier direct-numerical
formatter, old-producer and native/warning debt remain with Tasks16/19, including
Task09 Minor3; they are not blanket exemptions. Container-reader compatibility
does not promise that every downstream script accepts the C7 schema unchanged.

## Pre-first-review cropped rectilinear geography correction

The fixed-region instructional guide exposed a missing C7 axis rename after the
first frozen handover. Regional extraction correctly retained 5x5 samples, but
both broadcast geographic arrays had `(time,y_box,x_box)` dimensions. Looking
at their final dimension mapped both native axes to `x_box`, leaving the actual
field and publication descriptor at `(time,y_box,x)`.

`format_model_grid` now uses an existing native dimension, or the unique spatial
dimension of its retained `<native>_source_native_index` auxiliary. It does not
infer a native axis from a geographic array's orientation. Extraction, scientific
values/NaNs, coordinate orientation/units/clocks, binding and the approved polar
hook remain unchanged. No new configuration or public API was needed.

Four additional actual-generator cases cover NetCDF/sharded Zarr fixed crops and
full-domain controls. Before the fix, both crop cases failed on `y_box` while both
controls passed; after it, all four pass. Fresh non-FrameIt readers check exact
two-time 5x5 values including zero/NaN, `y/x=0..4`, source indices 6..10, original
physical labels/units, geographic orientation, native/centre clocks and actual
publication metadata. The unchanged generator supplies read-only inputs whose
hashes remain intact. All 35 earlier new definitions/assertions are preserved.
The output and v3-region modules pass **91 tests / 555 warnings**.

The original first Task10 full results above are historical, not rerun or
overwritten. The completed connected/required checks and new frozen full
diagnostic below compare against both its 2,344 nodes and Task09's 2,309 nodes.
Lead example acceptance and first independent review remain outstanding.
The separate resource-budget gap stays with Task11, not this output-only correction.

### Final correction verification

The correction is frozen and ready for the lead's complete-example rerun.
The output/region focused run remains **91 passed**. The connected run is
**1,194 passed / 84 failed / 1 error**, preserving all 1,275 first-Task10
connected statuses and all 1,240 Task09 statuses. The exact required four-file
command remains **59 passed / 31 failed / 1 error**, with all 91 statuses and
32 failed/error IDs unchanged against both baselines.

The correction's one final frozen full run completed:
**1,878 passed / 468 failed / 2 errors / 2,348 nodes**, with 5,931 warnings and
4 passed subtests. Every **2,344** first-Task10 status and every **2,309** Task09
status is preserved, including the exact **470** failed/error IDs. All **39**
Task10 additions pass: the original 35 are unchanged, plus four crop/control
cases. This is not a green suite or scientific approval.

Both full comparisons retain each prior/current failure trace. Against each
baseline, 423 messages/traces are byte-identical; 47 differ only by temporary
roots, including one random attempt-directory suffix. The literal required
command's auto/short traceback rendering difference was checked per node for
matching ordered source locations and exception lines; no failures were hidden
or reclassified. Full commands and individual evidence are in the detailed
task report under the cropped-geography resumption.

All 12 source/test Python files and both baseline XMLs remain at the new frozen
hashes. Scope proof preserves the first full run and all other frozen source/
test paths, including the polar hook, numerical code and binding. Ruff remains
23 baseline / 22 current diagnostics with zero new; the evidence helper passes
standalone Ruff. All nine frozen input hashes match `SHA256SUMS`.

No staging/commit/push, source or frozen-harness writes, warning suppression,
environment repair, public documentation/checker edit or independent review
was performed. Lead example/documentation/preview acceptance remains pending;
Tasks11/16/19/21 retain their separate resource, producer/native/warning and
human acceptance responsibilities, including Task09 Minor3.

## Lead runtime/publication acceptance before first review

Fresh lead output-module run passes39cases/214warnings/25.43s. Saved-XML checks
independently corroborate final2348nodes1878pass/468fail/2errors, every prior
status and exact470failed/error IDs. Required/connected suites remain red,
not scientifically waived. Freeze/scope checks and all9source hashes agree;
Ruff12paths23base/22current/noNew is not clean lint.

The canonical scalar request, published ordinary NetCDF/Zarr readers, explicit
storage fragment and fixed-region resource context execute with exact values/
masks/clocks/units, original auxiliaries and4source hashes. Corrected crop axes
use y/x with local0..4 and original6..10. Both Zarr layouts and gzip1/coordinate
compression settings are inspected. Native/vector/transform guide examples pass
with3source hashes; only2scratch output-axis checks change. The frozen Task09
harness also passes unchanged, preserving all6source hashes and C6 assertions.
The declared/reported CPU-budget difference remains explicit Task11 work.

Strict56/publication/13unit/4plot-release+2subtests pass15warnings. All5affected
pages equal live desktop/320px-inspected55/54/52/51HTML; the coordinate mappings
use readable full-width definitions without changing names or the old anchor.
The preview stays available. First independent Task10 review remains required;
no scientific/human sign-off or Task10 commit is claimed.

## Independent-review fix round 1/5 — output policies and verification

Author fixes for I1–I3 and M1 are frozen, **not independently approved**.
The reviewed object is tree `42b14ad894a327c69d29179a16859bfb395259a6`, not a
commit. Only the shared NetCDF/Zarr preparation/layout exporter, coupled output
assembly, planned model-grid descriptor lookup and output tests changed this round.
No reader/admission, scientific calculation, binding decision or approved polar
hook was changed. No new parser, public YAML, dependency or production module.

### Effective output policies

- **Decoded missing encoding:** after dropping source packing, the shared
  `_prepare_dataset` changes a non-`None` floating `_FillValue` to NaN. A packed
  code such as 0 must not mask a valid decoded physical zero. Explicit `None`,
  non-floating and time/calendar encoding handling remain unchanged at that
  boundary. No cast, repacking, masking or field-value calculation is introduced.
  Ordinary-reader controls preserve exact `[0.,1.,NaN]` for data, coordinates
  and original-coordinate auxiliaries with coordinate compression off, plus
  int16 `[0,1,2]`, datetime64[ns], times and calendar.
- **CF references:** `formula_terms` and `cell_measures` retain their semantic
  labels; only referenced stored variables change. Variable lists and simple/
  expanded grid mappings rename reference tokens. `cell_methods` renames
  coordinate references outside comments, preserving methods, reserved
  `area`/`volume` and parenthetical content. Attributes and encoding dictionaries
  are both handled; unrelated free text is untouched. This is not a general CF
  validator.
- **Moving-grid identity:** complete native-inventory field/grid associations
  and timestamped coordinate metadata define trajectory hashes, including
  calendar/cycle/bounds, spatial axes, geography attributes, dtype and values.
  Field names/IDs, paths, scientific payloads, encounter counters and selected
  field order are not hash inputs. Whole-file and successive-file packaging have stable
  identities. Independent trajectories that share one snapshot retain separate
  output views rather than being joined through that snapshot.
- **Interfaces/provenance:** `output_grid_layout(source)` supplies model-grid
  and polar output plus planned descriptors. Internal
  `format_model_grid(dataset, grid_id, source, layout, *, field=None)` uses
  `_output_grid_facts(layout, grid_id, field=None)` for ambiguous shared snapshots.
  Only those snapshots get per-field output views after unchanged extraction.
  Exact combines/merges remain exact. Coordinate provenance entries add
  `native_grid_id`, preserving origin when the entry key is an output-view ID.
  Qualified axes, geography and original labels/indices remain associated.
- **M1:** known non-consolidated test readers explicitly use
  `xr.open_zarr(..., consolidated=False)`. Storage and global warning policy
  are unchanged.

The original hybrid test keeps its node ID and every old physical/reference
check, now running both formats with exact `a/b/ps/p0` labels. Fresh ordinary
readers reconstruct **20,000 Pa / 40,000 Pa**, `rtol=0, atol=1e-10`; supplemental
controls check every coefficient, scalar p0, ps array, dimension and unit.
Both-container cell measures retain correct labels and exact area/volume arrays.
The new time-unit check accepts the equivalent midnight epoch spellings with
or without `00:00:00`; decoded times/calendar remain exact.

Six new moving-grid cases cover NetCDF/Zarr and whole/successive/shared-snapshot
packaging, each running AB/A/BA/B output selections. Ordinary readers check own
axes/geography, values/zeros/NaNs/dtypes, clocks/metadata/units/references,
original labels/indices, planned/actual dimensions and source hashes.
The actual reviewer A/B files also pass both-format checks without changing
their hashes or reusing the original failed output attempt.

### Observed checks

All checks used Python **3.13.18** in `frameit_env`, worktree `PYTHONPATH`,
the approved compact fixture root and `TMPDIR=/tmp/opencode`.

| Check | Observed result |
|---|---|
| I1 corrected RED → GREEN | 2 failed / 1 passed → 5 passed with existing precision controls |
| I2 RED → GREEN | 4 failed → 7 passed, including I1 |
| I3 RED → GREEN | 6 failed → 9 passed with original moving/static controls |
| Output module, pre-freeze | 51 passed / 282 warnings |
| Final-candidate minimum 12-file covering | 571 passed / 64 failed / 1 error / 636 nodes / 2,090 warnings |
| Exact required four files | 59 passed / 31 failed / 1 error / 91 nodes / 401 warnings |
| ONE frozen full diagnostic | 1,890 passed / 468 failed / 2 errors / 2,360 nodes / 5,999 warnings / 495.26s |

The full run reports four passed subtests and exits 1. Every **2,348 reviewed**
and **2,309 Task09** status is preserved, including the exact **470 failed/error
IDs**. The covering subset preserves **624 / 585** statuses and exact 65
failed/error IDs; required preserves all 91 statuses and exact 32 failed/error
IDs against both. No removed nodes, changed statuses or added/removed failing IDs.

All original **32/35/39** output cases remain; all **51** now pass, with **12**
current-round additions. All 22 prior test definitions, signatures/decorators
and assertions are retained. Only the hybrid test gains stronger checks;
M1 changes reader options, not expectations. Previously approved output-axis
adaptations are unchanged.

Each saved comparison retains all nodes and each prior/current failed trace.
Per-node context checks find no unexplained differences. Full comparisons have
423 byte-identical messages/traces and 47 context-only changes against each
baseline: 46 temporary-root-only and one additional random Slurm-attempt suffix.
Covering has six temporary-root changes; required has six message-path changes
and 32 auto/short trace-rendering differences with matching ordered locations
and exception lines. None is hidden, reclassified or described as passing.

The round's manifest verifies **15 unchanged hashes**: 12 source/test paths
and three historical XMLs. Reviewed-tree and Task09-relative scope/AST proofs
pass; numerical/reader/polar code and historical evidence remain preserved.
Ruff across all 12 changed/new Python paths is **23 base / 22 current, zero new**,
and **22 reviewed / 22 current, zero new**, not clean lint. The evidence helper
passes standalone Ruff. All nine frozen input hashes and both reviewer-input
hashes match. HEAD remains the base, index empty; `git diff --check` passes.

### Documentation impact and remaining gates

User-facing facts for lead integration are the safe floating missing encoding,
CF reference grammar, complete-trajectory suffix identity, optional internal
`field` argument and additive `native_grid_id` provenance. No input/YAML,
dependency or installation migration. Do not promise identical old moving-grid
hashes or unchanged behavior of every downstream script.

The full diagnostic remains red at its prior 468 failures and two errors.
Native binary/deprecation/future warnings, wind-frame responsibility and existing
time-bound fixture warnings remain; known consolidated-fallback noise is absent
from the new output/full summaries. Supplemental controls retain a heredoc
invalid-escape SyntaxWarning and known space-in-path `getfattr` messages.
No suppression, package repair or broad scientific-validity claim was added.
Task09 Minor3/native/backend/producer/legacy qualification remains Tasks16/19.

Lead complete examples, canonical docs/checkers/STATE, strict Sphinx/publication,
live preview and commits remain lead-owned. Original-reviewer I1–I3 and
new-breakage closure is still required after those examples; author checks are
not that approval. CPU wiring remains Task11, wider CLI/status Tasks12–15/19,
human science/usability Task21. No transaction/append/kill, archive/HPC or
performance guarantee. Nothing staged, committed or pushed by this worker.

### Fix1 lead checks before scoped re-review

Fresh lead output-module run passes51/282warnings/51.51s; all39reviewed nodes
remain. Saved XML independently corroborates2360nodes1890pass/468fail/2errors,
all2348reviewed/all2309Task09statuses and exact470failed/error IDs,12/51added
passes. Required59pass/31fail/1error and12file covering571pass/64fail/1error
agree. Every full-run failure remains a failure, with raw trace/context evidence.
Fresh15freeze hashes/scope/both Ruff comparisons/9inputhashes pass; no new lint
diagnostic is not clean lint or scientific qualification.

Unchanged scalar/vector/frozen09example harnesses03 pass with4/3/6source hashes.
Both formats, encoded layouts, exact crop indices and all existing values/masks/
clocks/units/provenance remain checked. Canonical57 describes decoded missing
encoding, CF labels and native_grid_id/trajectory identity. Strict/publication/
13unit/4plot-release+2subtests pass15warnings; policy notes inspected live1020/320
without overflow/missing images, other4pages equal inspected56HTML. The preview
stays available. Original-reviewer closure remains required; no self-approval.

## Independent-review fix round 2/5 — N1 coordinate-support preservation

The scoped fix starts from reviewed tree
`ccff69263d473ffc876aac66c47ac2d79d0898c5`. Closed I1–I3/M1 are not reopened.
Only `core/coupled.py` output-view construction changes in production:
`ds[[field]]` becomes `ds.drop_vars(set(ds.data_vars) - {field})`.
There is no signature change, new helper, dependency or configuration control.

Field-list selection silently pruned coordinates on extra dimensions such as
`level_bounds(level,nv)` while retaining the declaring `level.bounds` attribute.
The corrected shared-snapshot view removes other physical data variables and
retains all already-bound coordinate/support variables regardless of their
dimensions or names. The same rule covers retained bounds/formula/mapping/
measure/ancillary support; it is not new dependency discovery or metadata repair.
Extraction, selection, inventory, binding, trajectory identity, exact merges,
scientific calculations, writers and the approved polar hook remain unchanged.

Two new actual-reader format cases select only **2026-01-01T00:00:00** and native
level index **0** from labels **[10,30] m**, bounds **[[0,20],[20,40]] m**.
Complete-inventory trajectories share that first snapshot and diverge later.
Each case runs AB/A/B products; ordinary readers importing no FrameIt resolve
every bounds reference and check exact **[[0,20]] m**, `(level,nv)`/`(1,2)`,
owning/inherited units, original level/index, values/zero/NaN/float32, own axes/
geography, clocks, original labels/indices, publication metadata and input hashes.
Unrequested physical fields stay absent. No invalid extra-axis formula fixture
was introduced; the existing both-format formula controls remain required.

Observed before/after: both formats fail with the exact dangling
`('level','level_bounds')` reference, then both pass after the one-expression fix.
RED: **2 failed / 33 warnings / 2.31s**. GREEN:
**2 passed / 33 warnings / 5.34s**. All prior 51 tests remain verbatim as a
byte-exact prefix; focused output tests are **53 passed / 314 warnings / 52.30s**.

The minimum six-file covering diagnostic is **366 passed / 1,722 warnings /
169.34s**, preserving all 364 fix1 and 313 Task09 subset statuses. The exact
required suite remains **59 passed / 31 failed / 1 error / 401 warnings**:
all 91 statuses and exact 32 failed/error IDs match both baselines. Raw traces
are retained, not treated as passing assertions.

Genuine freeze follows those diagnostics: 16 hashes cover 12 source/test files
and four historical full XMLs. The lead was notified for disjoint examples and
the exact fix2-relative scope/required-rendering proof. The historical fix1 proof
hardcodes the deliberately replaced view and was not modified or rerun.
Existing generic Task09 scope checks pass but do not replace that lead-owned
proof. The exact scope and required auto/short classification were supplied
after freeze; pointers and the completed single full result are recorded below.

Initial Ruff is **23 base / 22 current** and **22 fix1 / 22 current**, zero new
diagnostics on all 12 changed/new Python paths, not clean lint. All nine frozen
input hashes and four reviewer-input hashes match. Historical artifacts are
preserved. Checks use Python 3.13.18 in `frameit_env`, worktree `PYTHONPATH`,
the approved fixture root and `TMPDIR=/tmp/opencode`; exact commands and raw
artifacts are in the same Task10 report.

This corrects output support loss, not numerical methods, units, missing-data
policy, YAML, installation or storage semantics. It supplies internal doc facts
for lead integration; canonical docs/STATE/checkers/commits remain lead-owned.
No screenshot/JPEG capture or other image inspection is used; the lead retains
text-only HTML/DOM/publication/live preview. Original-reviewer N1/new-breakage
closure and human science/usability acceptance remain required. No staging,
commit/push, subagents/reviewers, package/native change, warning suppression,
existing source-data write or Task11 implementation/redispatch.

### Final N1 full comparison and lead evidence

**DONE_WITH_CONCERNS:** the one frozen full run completed with **1,892 passed /
468 failed / 2 errors / 2,362 nodes**, 6,031 warnings, four passed subtests and
480.61s, exit 1. All **2,360 fix1** and **2,309 Task09** statuses and exact
**470 failed/error IDs** are preserved. Both current additions pass; all original
32/35/39/51 output IDs remain within the 53 passing output cases. No status or
failing ID was removed, changed or added.

Every full failed/error message and trace is classified separately against each
baseline: 423 byte-identical pairs; 47 context-only differences, comprising
46 temporary-root-only messages and one also carrying the random Slurm-attempt
suffix. Raw trace pairs are retained. Required classifications account for all
32 nodes: 26 identical/6 temporary-root messages, 32 auto/short renderings with
matching ordered locations and exception lines. Covering has no failures.
Nothing is waived, suppressed or described as a green scientific suite.

Evidence pointers in `.superpowers/sdd/CHECKLIST_FOR_AGENTS/`:

- `task-10-fix-2-full-final.txt/.xml`, `-full-comparisons.txt`, both
  `-full-vs-{fix1,task09}-comparison.json`/`-failures.md`/`-failure-context.json`:
  complete full-node/status/raw-trace comparisons.
- `task-10-fix-2-new-node-statuses.json`, `-message-classification.json` and
  `-final-inventory.txt`: retained original IDs, the two additions and each
  changed full message.
- `task-10-fix-2-scope-proof.json`: lead proof of only one coupled expression
  and appended tests; coupled file otherwise byte-identical, prior 51-case
  module byte-exact, other reviewed Python files unchanged.
- `task-10-lead-fix-2-verification.txt`: 16 frozen hashes, all 41 initial
  source/artifact entries except the two authorized changed paths, four reviewer
  sources, nine frozen fixtures and scientific boundaries preserved. Fresh
  12-path Ruff is 23→22 base, 22→22 fix1, zero new, not clean lint.
- `task-10-fix-2-required-rendering.txt` and both
  `task-10-fix-2-required-vs-{fix1,task09}-failure-context.json`: lead's per-node
  rendering proof, with positive and changed-exception/line negative controls
  reported by the lead. Historical fix1 checks/helper were not modified.
- `task-10-lead-fix-2-focused.txt/.xml`: lead N1 **2 passed / 33 warnings / 5.87s**.
  `task-10-fix-2-N1-reviewer-inputs.txt`: author's fresh both-format execution of
  the actual four read-only reviewer inputs, bounds `[[0,20]] m` and metadata
  preserved, all hashes unchanged and original failed attempt untouched.

Lead acceptance is recorded in the N1 round2 entry of
`docs/development/yaml-v3/STATE.md`: three unchanged example04 harnesses pass
with 4/3/6 input hashes; strict58/publication/13 unit/4 plot-release checks plus
two subtests pass with 15 warnings. Five HTML pages equal 57; text-only live DOM
at 1020/320 shows no page overflow. Canonical58 preview stays available. These
lead-owned checks were consumed, not rerun or claimed as author execution.

Source/tests remain frozen and uncommitted. No screenshots/JPEG/image inspection,
checker/history edit, source-data writes, Task11 work, package repair or new
warning policy. Original-reviewer N1/new-breakage closure and human scientific/
usability acceptance remain required; inherited failures/warnings retain their
owners. Exact author commands and remaining limits are in the same Task10 report.

## Independent closure and precommit verification

The original reviewer independently marks N1 addressed, spec approved and task
quality approved, with0new Critical/Important/Minor findings. I1–I3/M1 remain
closed; no Task10 review finding is open or parked. This is scoped engineering
approval, not whole-branch, scientific or human acceptance.

Fresh lead precommit:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_outputs.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-10-lead-precommit.xml
```

Observed **53passed/314warnings/51.55s**; all16frozen hashes and diff checks pass.
Reviewed source/tests/public pages remain unchanged. Final internal records and
checklist marks do not alter published documentation; strict58, publication,
example and text-only GUI evidence stays current. No new image capture.

The frozen interfaces, documentation/compatibility assessment and explicit
remaining red-suite/resource/producer/native/human gates are in
`STATE.md` under **Task10 frozen handoff — independently approved**.
Completed verified changes are committed locally before Task11; no push or merge.
