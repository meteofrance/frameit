# Task16 checks

This is a dated historical record. Later sections and the final handover in
`STATE.md` supersede earlier unresolved/pending statements; old failures are
not relabelled as current green evidence.

## 2026-11-15 — blocked before implementation

Base `40f9bcdb4429fe1755aab871c2b7f9d5916af51e`. No source/test/example/fixture
implementation changes by the Task16 worker; no staging/commit/push.
This is a blocker report, not completed acceptance or a freeze.

### Concrete C3 conflict

The AROME catalogue requests height `u,v` at indices `[0,2,5]` and pressure `u,v`
at values `[1000,850,400]` in the same source. Frozen v3 has ordinary field-name
selectors and one level selector per source, not group-qualified field selectors
or independent group level selections.

The approved BATSIRAI fixture actually contains three distinct `u,v` identities:
`isobaricInhPa`, `heightAboveGround` and `potentialVorticity`. It also repeats
`t`, `r`, `tke` across groups. Actual production preflight rejects a minimal
direct-v3 `variables: {3d: [u, v]}` request on those unchanged five files:

```text
distinct fields share requested name 'u' ... qualified selectors are unsupported
```

Repeated YAML names fail duplicate-name validation; using both original level
strategies fails the exactly-one-selector rule. Deduplication does not recover
the requested physical fields. Two atmospheric sources would also violate C1.
This affects single-group wind/scalar catalogue cases on that inventory too.

No fields/levels/units/basis/masks/times were substituted, no input was filtered
or relabeled, and no runtime migration/selector layer was added.
Lead/maintainer disposition is required before adapting these cases; no
independent scientific ruling is claimed.

### Bounded verification

Environment: Conda `frameit_env`, Python3.13.18, worktree source import, bytecode
off, temporary root `/tmp/opencode`, approved fixture
`build/yaml-v3-ci-fixture-01`, sources read-only.

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-conflict-probe.py
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q 'src/frameit/testing/numerical/test_grib_lifecycle.py::test_v3_grib_metadata_locators_without_value_decoding[name_ambiguity]' 'src/frameit/testing/numerical/test_request_selection.py::test_v3_field_and_level_binding[promoted_ambiguous_name]' --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-conflict-guards.xml
```

* Probe final execution: exit0 with assertion checks, full requests, catalogue
  collision inventory and tracebacks. All12 fixture files hash-exact before/after;
  all9 SHA256SUMS payloads verified. No products or run directory created.
* Initial probe self-check expected different duplicate-error wording and
  exited1; retained, then corrected in the diagnostic only. This was not a
  production failure or a test expectation relaxation.
* Two existing ambiguity-guard tests: **2passed/0failed,0.71s**. They still
  exercise the actual intended unsupported-name behavior.
* Initial actual-path Ruff of the new probe: zero diagnostics. Final proof is
  appended below; no whole-repository clean-lint assertion.

Evidence stays in `.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-*`:
`conflict-probe.py`, `conflict-probe{,-02,-03}.txt`,
`conflict-probe{,-03}.json`, `conflict-guards.txt/.xml`,
`conflict-ruff.json/.stderr`, and `task-16-report.md`.
The probe exclusively creates its JSON evidence; choose a fresh JSON suffix for
a replay rather than overwrite the retained record.

### Interfaces and preservation

No helper signatures changed. Initial actual callers found:

* `catalog.load_cases/resolve_case` → matrix and benchmark; configuration,
  integration, output-layout and wind-preflight tests.
* `checks.check_products` → matrix and benchmark.
* `document/dataset` → configuration integration, HPC, NetCDF assembly, Zarr
  tests and `docs/test_repository_examples.py`.
* `create_first_run_input` → documentation and v3 CLI/execution/output/run-state/
  interpretation/polar tests plus existing PNG smoke consumer.

This is not the requested exhaustive caller/assertion audit. Existing assertions,
generator formula/values/missingness, case IDs and canonical requests are unchanged.
Catalogue schema1/catalogue revision'3', configuration version, artifacts1.0,
report-record1, FA and package versions remain distinct and unchanged.
The static configuration reference is already direct3. Native low-level
`rr/theta` APIs were not renamed.

Scientific impact:none. Compatibility/output/config/default changes:none.
Lead owns README/published prose/STATE/contracts and their separate checks.
No canonical command/output facts beyond the unchanged generator are newly
qualified here.

### Unrun gates

No implementation RED→GREEN cycle, exhaustive inventory, named real-product/
benchmark acceptance tests, Task15 scenario restoration, documented command runs,
required nine-file264-node acceptance, full2751+new recovery/cause audit,
strict docs/publication/GUI check or genuine source/test/asset freeze.
The one authorized post-freeze full has not been run. Neither PNG smoke was run
separately or viewed. No benchmark campaign, downloads, environment repair,
native/installed-wheel/conformance/HPC/human or later-task qualification claim.

### Final blocker-handoff preservation

Executed assertion-based Python check in the same required environment:
`task-16-blocker-preservation.json/.txt` records **244tracked paths byte-exact
against HEAD**, including182 Python paths and3983 unchanged assertion ASTs,
all12 unchanged fixture files/all9 verified payload hashes, and no staging.
This is not the still-pending exhaustive historical-evidence/mutable-history
proof. The lead's documented prose/STATE/checklist changes were not overwritten.

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode conda run --no-capture-output -n frameit_env python -m ruff check --output-format=json .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-conflict-probe.py
```

Final current-script result: exit0, `[]`, empty stderr in
`task-16-conflict-ruff-final.json/.stderr`; zero new HEAD findings for the only
new Python path. No existing Python code was edited. No freeze or completed
Task16 assertion follows from these bounded checks.

## 2026-11-16 — independent partial implementation

The lead's independent-work ruling is applied. The original C3 probes/guards
were not repeated or changed. AROME disposition is still pending; no whole-task
completion, source freeze or full diagnostic is claimed.

### Implemented boundary

* `check_products(case, products)` keeps its API and result semantics,
  particularly `reference_validation: not_performed`. It checks actual
  `(role,source)` descriptors, C7 filenames/field dimensions/units, each product's
  source clock, optional exported track, CF track coordinates and C7
  radius/azimuth/degrees. Existing bounded finite-sample, support/status/mask/
  ring and speed checks remain; no directory globs or finite-everywhere rule.
  Actual scope: **NetCDF only** and the existing supported Gregorian/nanosecond
  range. Zarr is explicitly rejected, not silently unchecked.
* Exact named `test_matrix_checks_actual_outputs` runs four real configurations:
  model_grid/polar × omitted/exported track, with independent atmosphere/ocean
  clocks. It rejects wrong clocks/dimensions, duplicate descriptors and the
  unsupported format. It is not a mocked matrix launcher.
* Existing `mnh_chido_surface_polar` alone now emits direct3 and resolves/executes
  through the actual checker. Case ID, fields UM10/VM10/MSLP/LE/H, declared Earth
  basis, original centre-grid lookup,120km full crop,60km radius,3km step,
  36 azimuths and three times remain. UM10/VM10 use original`m s-1`, MSLP`hPa`;
  **LE/H have no source units and no units were invented**. Product axes retain
  actual C7 qualifiers where grids differ.
* Exact named `test_benchmark_small_case` runs that existing MNH case through real
  preparation/execution in two serial fresh workers, capacities2/0, cpus1,
  synchronous compute/export, native-thread budget1 and60s per-worker timeout.
  Existing comparison rtol/atol1e-12 is unchanged; maximum numerical difference0.
  Ordinary-reader subprocesses and source hashes pass. No campaign or speedup
  claim. AROME continuous-origin code retains longitude±0.001°/constant latitude
  with CF coordinates/encoding, but its blocked branch is **unrun**.
* Both Task15 newly rejected report/privacy scenarios now pass through current
  same-file commands, retaining preflight/projection identity and actual native
  private-HOME/metadata-only/selected-interpreter guards. Extra observations
  prove inspect-only helper calls and input-byte preservation.
* First-run starter/guided and quick-start commands now pass, using C7 paths
  and original independent expected values/masks/units/times/tolerances.
  Source bytes and mtime remain unchanged. The unrequested implicit track is
  replaced by assertions on field geographic centres/native source indices.
* Six canonical examples parse directly as3: conf_example,
  conf_pressure_centroid_mnh, conf_multifield_mnh, arome_fa_native_cubes,
  nemo_arome, croco_mesonh. Explicit multifield stop semantics remain
  `on_incomplete: keep_prefix`. NEMO/CROCO execution is **not green**.
* The Batsirai plot consumer uses actual atmosphere model_grid/polar filenames,
  CF trajectory names and radius/azimuth. Footprints come from exported crop
  geography. Both original PNG smoke assertions remain exact and pass only
  inside the unfiltered required suite; none was viewed or run separately.
  The first-run script and static reference were already compatible and unchanged.

Shared helper signatures/fixtures remain byte-exact; their direct3 conversion
and all dependent callers are **not yet implemented**. Unconverted catalogue
definitions retain the exact old grouped literal while the scientific boundary
is unresolved; this interim mixed catalogue is not release-ready and does not
add a legacy runtime path or unsupported-case status.

### Static caller/assertion inventory

The private baseline manifest records388 tracked hashes,209 actual static call
expressions,51 imports,648 retired-name/control mentions,3983 assertion ASTs and
complete old definitions/signatures, with raw relevant producer/test/example
copies. This does not claim every caller has been semantically converted.

Actual consumer links:

* Catalogue → matrix/benchmark/configuration-integration/configuration/
  output-layout/wind-preflight callers.
* Checker → actual matrix and benchmark workers; named real-output acceptance.
* `document/dataset` → HPC, configuration integration, NetCDF assembly, Zarr,
  repository examples; dataset also supplies inspection/documentation fixtures.
* Instructional generator → documentation and v3 CLI/execution/output/run-state/
  interpretation/polar tests; its formula and mask are unchanged.
* Canonical examples → repository tests; scripts → the two existing PNG smokes.

Per-function removed/added assertion maps and unchanged definitions are in the
private proof JSON. All original v3 execution tests are an exact632-line prefix;
all prior required264 IDs remain. Structural maps are:
retired planning commands→validate/effective; cart/group files→C7 source products;
track-only centre assertions→actual field centre/native-index coordinates;
explicit native/rho-Earth source transforms→the same original numerical arrays/
masks/tolerances. No skips/xfails or tolerance relaxation.

### Exact verification

All commands ran from the worktree with Python3.13.18 in frameit_env, worktree
PYTHONPATH, bytecode off, TMPDIR=/tmp/opencode and the approved fixture. Prefix:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env
```

After that prefix:

| Command | Observed |
|---|---|
| `python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py -k test_matrix_checks_actual_outputs` | RED4fail → GREEN4pass |
| `python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py -k test_benchmark_small_case` | RED1fail → final GREEN1pass/1warning/14.64s |
| `python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py::test_existing_planning_handlers_share_one_preflight_and_projection src/frameit/testing/numerical/test_fa_cubes.py::test_private_epygram_configuration_and_metadata_only_cli` | RED2fail → GREEN2pass |
| `python -m pytest -q src/frameit/testing/numerical/test_documentation_example.py` | RED3fail/3pass → GREEN6pass/3warnings/16.64s |
| `python -m pytest -q docs/test_repository_examples.py -k test_unambiguous_examples` | RED6fail → GREEN6pass |
| `python -m pytest -q docs/test_repository_examples.py` | 7fail/6pass/1error/173warnings/3.16s |
| `python -m pytest -q src/frameit/testing/numerical/test_output_layout.py` | 3pass; its “red” evidence filename is not a RED result |
| `python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py src/frameit/testing/numerical/test_fa_cubes.py src/frameit/testing/numerical/test_matrix_progress.py` | 140pass/7fail/3warnings/13.19s |

Exact required nine-file run:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v2_1.py src/frameit/testing/numerical/test_documentation_example.py src/frameit/testing/numerical/test_configuration_integration.py src/frameit/testing/numerical/test_all_tests.py src/frameit/testing/numerical/test_templates.py src/frameit/testing/numerical/test_v3_execution.py docs/test_repository_examples.py docs/test_documentation_plots.py docs/test_release.py --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-independent-required.xml
```

**164passed/110failed/1error,293warnings,2subtests passed,57.60s,exit1.**
All264 prior required IDs appear:150 former passes preserved,3 old failures
recover,11 additions pass. This is not green acceptance. Both PNG smokes pass
inside this run only; no generated image was opened or published.

Initial benchmark attempts retained failures for real qualified native axes,
2D-per-file concatenated time dimensions and the new test's mistaken assumption
that LE/H units were present. Original source metadata was inspected and the
new metadata assertion made exact for absent units; no fixture/formula/expected
physical array/tolerance was substituted.

Private evidence helper commands, with the same prefix:

```text
python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-independent-inventory.py
python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-independent-compare.py
python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-independent-history-proof.py
python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-independent-proof.py verified
```

The last performs `python -m ruff check --output-format=json --stdin-filename
<actual-path> -` on HEAD/current content:25 baseline/19 current/0new findings.
Initial capture/proof self-check and five introduced line-length diagnostics
were retained and corrected. Whole-repository clean lint is not claimed.

### Partial cause audit and frozen-core boundary

The comparison covers414 old IDs, explicitly retaining2337 unrun old IDs and
their mixed-age evidence.608post-fix1/2143PRE-fix1 remains prior freshness, not a
corrected full.123 raw old/new cause pairs contain full exceptions and complete
stdout/stderr sections. Seven nontrivial comparisons are manually disposed:

* Shipped-schema loop advances from converted FA YAML to untouched AROME YAML.
* Catalogue test now hits its obsolete all2.1 assertion; blocked AROME physical
  assertions remain unchanged/unreached.
* Imported HPC fixture error and Slurm-launch failure retain the same2.1 helper
  cause, differing only in scratch suffixes/reprs; downstream checks are unrun.
* NEMO now reaches the strict instantaneous guard: original NetCDF
  `GRIB_stepType: instant` is dropped from record temporal_metadata before
  preceding-hour association. No guard weakening or fixture edit.
* CROCO native reaches unequal y_rho exact-merge failure at coupled.py:1009.
* CROCO mass/Earth reaches conflicting s_rho_source_native_index at
  derived/wind.py:421. Original values2/-4, NaN mask, W/sigma and1e-12 assertions
  remain unchanged and unreached; no alignment override or filling.

These three actual runtime failures require a specific lead core-boundary
authorization/disposition; core remains byte-exact. An ineffective attempted
canonical temporal-kind declaration was removed, with failed attempt evidence
retained. The existing science was not changed to fit execution.

All22 Task15 linked scenarios have individual private dispositions:5 restored,
3 still fail,14 unrun. This does not assert that the other intended scientific/
privacy guards have executed.

### Preservation, effects and limits

* 355 non-target tracked paths exact, including all frozen core/science/reader/
  writer/runtime/ownership/progress and published figures/artwork/CSS.
* Original execution-test632-line prefix and all PNG smoke assertions exact.
* All9 payload/12 fixture hashes exact.
* 22 original Task16 immutable artifacts exact; both old reports retained as
  raw copies with append-only prefixes. Explicit lead histories copied.
* All8704 earlier evidence entries and2362/2365 Task15 entries exact; the other
  three are explicit inherited mutable histories with retained originals and
  current copies. No unexplained historical evidence change.
* Actual-path HEAD Ruff adds0 findings. No dependency/environment/package/FA/
  catalogue/artifact/report version change; no new CI/file-list requirement.

Scientific algorithms/source values/units/bases/masks/levels/clocks/tolerances
are unchanged. Candidate structural compatibility changes are direct3 controls,
C7 names/axes, explicit optional track and current CLI projections; red runtime
cases are not qualified examples yet.

Evidence remains under `task-16-independent-*`: baseline manifest/copies,
RED/GREEN/required/covering XML and logs, per-node comparison/raw pairs,
Task15 scenario map, root dispositions, doc facts, proof/assertion maps and
history proof. No stage/commit/push/subagent/reviewer/download/environment/native
repair, production/HPC job, benchmark campaign or independent approval.

Shared-helper/caller and remaining producer/example conversion, full semantic
inventory, strict docs/publication/live GUI and conformance/installed-wheel/
native/HPC/human/Tasks17–21 gates remain outstanding. ABI/NumPy warnings were
not suppressed. Lead owns prose and rendered acceptance.
**No genuine source/test/asset freeze; the one full diagnostic remains unused.**

### 2026-11-16 — final partial-handoff verification

The latest proof, including polar-math AST preservation and Ruff coverage of the
history-proof script, ran successfully:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-independent-proof.py handoff > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-independent-handoff-proof.txt 2>&1
git diff --check
```

Both exited0. Complete JSON/text evidence: `task-16-independent-handoff-proof.*`.
355 non-target paths,22 original immutable Task16 artifacts,12 fixture files/
9 payloads, the original execution-test prefix and PNG assertions remain exact.
Polar speed math is exact; polar quality math is exact after only the C7
theta→azimuth dimension rename. Actual-path HEAD Ruff25/current19/new0, including
0 findings in the history-proof script. Both original report prefixes and22
separate current lead-history copies are retained. Only these report appends
follow the proof; no further implementation/test/example change.

Required164pass/110fail/1error and covering140pass/7fail remain the recorded red
results; neither suite was rerun for handoff. Shared helpers/callers and remaining
producers/examples are unfinished. Specific core-boundary authorization is
requested for lost instantaneous NetCDF metadata, native CROCO exact crop
assembly and the transformed CROCO native-index merge conflict. No guard,
fixture, expected value or tolerance was weakened, and core remains unchanged.
No repeated AROME ruling request, staging/commit/push, freeze, full diagnostic
or image viewing.

## 2026-11-16 — inline resumption after frozen core increments

Execution base `6abe753339fbd37d68488612bc44eb538eb8f481` includes reviewed C3,
metadata, CROCO owned-support and experimental explicit polar-component handoffs.
The last increment passed1090connected cases, strict docs03/publication/13units
and live text checks; its25prior dirty paths/copies remained byte-exact through
the commit. These partial Task16 paths are now resumed, not discarded or
represented as reviewed completion.

`task-16-resume-6abe753/` under the main ignored workspace preserves402tracked
hashes,4263assertion ASTs, raw testing files,25partial-path copies and the original
mutable ledger/brief before this resumption. Existing evidence is retained.
The exact required nine-file lane (the command above, with worktree PYTHONPATH,
bytecode off, `/tmp/opencode`, approved CI fixture and new XML/log destinations)
freshly reports **167passed/107failed/1error,293warnings,2subtests,63.71s**.
Full output/XML: `required-red-01.*`. No old red result is relabelled green.
Both PNG smokes ran only within that unfiltered required suite; no image opened.

A metadata-only source-clock probe found a further catalogue expression boundary.
AROME's declared initial gaps remain `heightAboveGround.tke`, `sshf` and `slhf`
at`2022-02-01T00:00:00`. Each field binds alone on its four available sample
times, but combining it with the original all-five-time `prmsl` clock fails at
the actual unavailable-field/time guard. The original catalogue expects missing
values at that first time. No current v3 declaration admits that known absent
record on the shared clock. Probe JSONs retain both the single-field positive
controls and mixed-clock failures; ecCodes scientific payload reads were forbidden,
no outputs created and no source field/time/mask substituted.

This is not permission to weaken strict binding, drop the first time/fields,
add a legacy parser, rewrite source data or invent a new missing-record option.
The affected catalogue lane remains blocked pending a separately approved
expression/core-boundary decision. Continue independent shared-helper/caller
conversion; no new runtime/core or scientific-policy implementation is authorized.
There is still no genuine Task16 freeze; its single full diagnostic remains unused.

### Caller continuation and current held boundaries

The shared helper signatures and the complete `dataset()` AST remain unchanged.
Callers now use actual v3 sections, source/grid-owned metadata, explicit selected
transforms/diagnostics, current validation reports and role/source descriptors.
The compact local lifecycle/Zarr/launcher/checker lane reached32passes; the
NetCDF assembly caller lane reached16passes. The final combined converted-caller
lane, including the whole NetCDF assembly and local lifecycle modules plus the
specific Zarr/example/launcher checks, passed **107tests/111warnings in21.91s**
(`converted-caller-lane-05.*`). This is not an HPC or benchmark campaign.

The exact required nine-file command, with the same source-selected environment
and fresh evidence destinations, now reports **293passed/6failed,302warnings,
2subtests,72.19s** (`required-callers-04.*`). The remaining failures are:

- `test_catalog_emits_current_requests_without_legacy_conversion`;
- `test_new_yaml_real_pipeline_exports_and_replay`;
- `test_frozen_matrix_yaml_and_mapping_requests_match[AROME]`;
- `test_frozen_matrix_yaml_and_mapping_requests_match[MNH]`;
- `test_all_shipped_example_yaml_uses_new_schema`;
- `test_source_examples_declare_conventions`.

No waiver, skip or earlier-parser failure is presented as recovered coverage.
Both PNG smokes ran only within the unfiltered required suite; no output image
was opened. Earlier failed intermediate runs and the malformed-node command
evidence remain distinctly labelled, not overwritten.

The unit integration now reaches real output. On its unchanged36km/h fixture,
the requested model-grid transform produces10m/s; derived polar speed is10m/s,
but polar base `UM10` retains km/h. Source transforms apply to model-grid exports
only, and there is no declared polar base-unit transform. The original m/s
assertion remains failing. The bounded input/output fixture is retained under
`unit-boundary-fixture-01`; ordinary-reader facts are in
`polar-base-unit-expression-boundary.json`. Exact equality with36 is not promised
for interpolated binary64 values: its finite values differ by ordinary rounding.
Do not change units labels, replace quantities, mutate the source fixture or
weaken its assertion to close this expression boundary.

The restored NetCDF inspect case reaches another actual metadata gap:
the report omits the second file's dataset-level
`wind_reference_frame: grid` evidence while its variable evidence says Earth.
`inspection-callers-02.txt` records1failure/2passes at the missing-context
assertion, after payload guards and input-byte/mtime checks. The metadata-only
probe/report remains under `inspection-context-probe-01` and
`inspection-context-report-01.json`. No core fix or new report interface has been
authorized. Retain that conflicting source evidence rather than silently infer
which declaration is right.

Five unambiguous examples were converted directly: AROME pressure-centroid/
multi-field and three atmosphere/SURFEX scalar requests. Five added cases observed
RED on the retired schema, then the example lane passed11cases. The read-only
`example-preservation-01.json` checks original paths/models, fields/order, levels,
FA declarations/guards, region/output and polar settings. The four K-test
configurations and remaining catalogue/consumer work are still outstanding.
This is parser/contract evidence, not real-producer scientific qualification.

The existing independent `example/slurm/check_run.py` now consumes actual
role/source identities and centre/time linkage instead of the retired
`track_filename` attribute. It retains compact NetCDF/exact-clock scope, source/
size/path/value/time checks, and a bad-centre-copy rejection test. The HPC guide
states that scope and current strict-tracking controls.

Strict Sphinx, publication and13publication units passed for the callers01
artifact. Live GUI rendered-text checks at1280px/320px covered the changed guide
paragraphs; no root overflow or screenshot. Caller lint is17baseline/13current/
zero new; diff-check passed. All82frozen core/reader/writer/scientific/template
paths, helper signatures and fixture AST remain exact (`caller-scope-02.json`).
No fresh Task16 review, commit, freeze, full diagnostic, environment repair,
production/cluster run or push/merge is claimed. Scientific expression/core
decisions remain held for specific approval.

## 2026-11-17 — reviewed increments committed, qualification still blocked

The later authorized default-preserving boundary design/plan led to `95c0f31`.
Caller preservation is committed in `5f82964` and `d82ef1f`; producer/assets in
`6426e40`; batch examples in `bd882c2`; wording closure in `2095dd8`.
Fresh bounded reviews closed their Important findings before these commits.

The current core connected lane95 has1227 passes, and staged-only source105
has63 passes without installation or unstaged callers. Producer111 has10 passes;
connected112 has21 passes with real checker outputs, unchanged MNH replay and
the one required small benchmark. These are not whole-branch qualification.

Five preservation substitutions were removed rather than declared recovery:
literal strict-equality demands, absent-rotation rejection, actual representation
selector leaves, the2600m override and inactive source-local polar inheritance.
Selection104 now has3 passes/five intentional contract failures. Full
request-selection114 has147 passes/two retained rejection conflicts.

The CROCO reader context formerly caught binding failure before reading.
False-green119 reproduced that outcome. The corrected context binds outside
`pytest.raises`; latest whole CROCO/Zarr run120 has54 passes/five failures:

- `test_croco_native_nminus1_faces_keep_locations[native]`: three faces versus
  the unchanged four-face oracle;
- `test_croco_analysis_sequence_rejects_changed_support_or_companion_metadata[angle]`
  and `[mask_rho]`: required historical rejections do not occur;
- that same test's `[v]`: real binding prevents reaching the reader; not coverage;
- `test_coupled_preview_and_execution`: the original two atmospheric physical
  sources remain a C1 conflict. No source was reclassified.

All six actual Zarr writer-size guards pass. Eight downstream FA ports retain
their historical worker failures, including track/provenance, partial publication
and `source_i` merge contracts. No skips/xfails or numerical weakening hide them.
Fifteen complete scientific fixture/helper ASTs remain identical to `6abe753`.

Final exact Task17 suite121 has53 passes; Task18 suite122 has58 passes.
Strict Sphinx/publication09,13 publication units, release2 tests/two subtests,
scoped producer Ruff, shell syntax and diff checks pass. Both full documentation
passes and technical shortening are closed for their recorded scope;44 optional
groups plus subparts are deferred. Only required unfiltered suites ran PNG smokes;
no generated image was opened.

Task16 still has no freeze: original AROME2.5km/native2.766872km and MNH W
physical-value/mass-target demands remain blocked, along with retained caller
contracts. The single full diagnostic is unused. No installed-wheel, production,
cluster, benchmark-campaign, final whole-branch or human scientific/usability
acceptance is claimed. Exact commands and evidence limits are in
`task-19-evidence.md`; `STATE.md` gives the next actions.
