# Task12 — request and publication records

Internal development evidence, not a public guide, scientific qualification,
independent review or human approval. Base:
`c7d1c658f6b9e7df0f69439e014efb42b5abaa57`.

Latest: Task12 spec/quality independently approved after the constructor correction
and I1 fix. No open Task12 finding;64focused cases pass. The2015/468/2full is
PRE-CONSTRUCTOR/PRE-I1 only. Historical pending/candidate sections below retain
their original evidence; final interfaces and limits are in STATE's frozen handoff.

## Scope and compatibility

Task12 adds one immutable `run-request.yaml` envelope and extends the existing
status/provenance checkpoints. It does not add a parser, replay/resume service,
new scientific method, public YAML key, dependency or numerical/output-variable
change. Valid effective controls are saved before processing, separately from
pending metadata.

The request retains parsed authored values and omissions, original YAML/mapping
and launch bases, raw operational overrides, requested options and available code
identity. Runtime-only construction labels unavailable authored information
honestly. Editing/moving the original YAML or mutating the original mapping or
override dictionary does not alter the captured request.

The existing configuration loaders accept optional `launch_dir` and `overrides`
keywords. They reuse `resolve_operational_overrides`, preserving its precedence
and origins. Existing callers need no new arguments. Preset loaders already copy
the captured state. `owned_run` adds optional request/provenance arguments;
`export_outputs` adds an optional parent-only v3 `on_published` callback.

Actual publications are checkpointed after the atomic writer returns, in both
synchronous and spawned export. Planned descriptors are never completion facts.
Graceful interruption drains completed worker results; checkpoint failures
propagate rather than producing success. Known processing/resource/binding facts
and unresolved phases remain separate. Record targets join source/alias guards
and no-clobber; explicit replacement refuses unrecognized/malformed metadata.

Worker Python scope:

- `src/frameit/core/configuration.py`: construction-time capture only.
- `src/frameit/core/settings_class.py`: internal copied constructor state only.
- `src/frameit/core/run_state.py`: ownership/recognition/checkpoint lifecycle.
- `src/frameit/core/execution.py`: early facts, parent checkpoint and failure facts.
- `src/frameit/io/netcdf_export.py`: v3 parent completion/draining only.
- New `src/frameit/testing/numerical/test_v3_run_state.py`.

All old test/producers/assertions and scientific/read/bind/cache/resource/encoding
implementations outside that scope remain unchanged. Lead-owned public prose,
`STATE.md`, checklist and frozen record contract are not worker edits.

## Commands

Run from the repository root. All development/checks use the existing Python
3.13 `frameit_env`, the selected worktree, approved read-only fixture and compact
fresh scratch. These exports affect only the check process, not installation.

```bash
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR=/tmp/opencode
export PYTHONPATH="$PWD/src"
export FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01"
E=.superpowers/sdd/CHECKLIST_FOR_AGENTS
```

Exact required test selection, unfiltered:

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_hpc_execution.py \
  src/frameit/testing/numerical/test_output_layout.py \
  src/frameit/testing/numerical/test_zarr_export.py \
  --junitxml="$E/task-12-required.xml"
```

Observed: **45 passed, 16 failed, 1 error**, 146 warnings, 7.98 s, exit 1.
All 62 outcomes match the saved required inventory. They are not waived or called
green. Their normalized primary messages match individually; raw message/trace
pairs are in `task-12-required-trace-pairs/`.

Focused:

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_v3_run_state.py \
  --junitxml="$E/task-12-focused-verified.xml"
```

Covering:

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_v3_run_state.py \
  src/frameit/testing/numerical/test_v3_execution.py \
  src/frameit/testing/numerical/test_v3_outputs.py \
  src/frameit/testing/numerical/test_v3_resources.py \
  src/frameit/testing/numerical/test_hpc_execution.py \
  src/frameit/testing/numerical/test_output_layout.py \
  src/frameit/testing/numerical/test_zarr_export.py \
  src/frameit/testing/numerical/test_configuration_v3.py \
  --junitxml="$E/task-12-covering-verified.xml"
```

Full diagnostic is run once after the genuine code/test freeze:

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q --tb=short \
  --junitxml="$E/task-12-full.xml"
```

Results and final per-node evidence are appended below only after execution.

Final scoped results on the frozen candidate:

| Check | Observed result |
|---|---|
| New focused suite | 55 passed; 175 warnings; 23.43 s; exit 0 |
| Eight-file covering | 573 passed, 16 failed, 1 error; 831 warnings; 114.01 s; exit 1 |
| Required62 final repeat | 45 passed, 16 failed, 1 error; 146 warnings; 7.93 s; exit 1 |
| HEAD-relative Ruff | 41 prior, 39 current, zero new findings |
| Scope/preservation | 181 tracked Python files; all old test ASTs; 4,389 prior evidence hashes; nine fixture hashes |
| Code/test freeze | 172 Python hashes in `task-12-freeze.json` |

The final required repeat uses the same unfiltered command above with
`task-12-required-verified.xml` as its XML destination. Covering retains all 535
old node outcomes and adds 55 passes; no old assertion was lowered. All 62
required outcomes retain their baseline status.

## TDD and checks

Task-prefixed raw logs/XML preserve each RED and GREEN:

- `task-12-red-capture`: six missing-request failures at the processing boundary.
- `task-12-green-capture`: new-test scalar-path expectation corrected after
  reading the existing `_paths` contract; retained failed attempt.
- `task-12-green-capture-2`: six passes.
- `task-12-red-overrides` / `task-12-green-overrides`: missing optional capture
  handoff → eight passes, preserving raw overrides and both path bases.
- `task-12-red-publication` / `task-12-green-publication`: all eight real
  format/mode/failure combinations lacked an on-disk publication checkpoint →
  16 combined passes.
- `task-12-red-recovery` / `task-12-green-recovery`: lost drained spawned
  completions and unrecognized metadata replacement → 36 combined passes.
- `task-12-red-edge-cases` / `task-12-green-edge-cases`: PathLike metadata
  serialization and a new-test YAML ordering correction → 49 combined passes.
- `task-12-red-last-facts` / `task-12-focused-final`: provenance failure could
  block authoritative status and observed processing facts could be lost →
  51 combined passes.
- `task-12-red-finalization`: final provenance failure left completed status;
  the primary-error preservation control already passed.
- `task-12-focused-verified`: includes the terminal-checkpoint fix, existing
  shortened-track policy controls and explicit persisted-checkpoint IPC
  acknowledgement for scheduling-independent spawn tests.

No pre-existing test helper, scientific literal, expectation, assertion or
warning filter was changed. Fresh ordinary-reader child processes import no
FrameIt and check exact values, dtype, missingness, metadata and independent
source clocks for the compact NetCDF/Zarr publications.
Signal probes use direct v3 core execution and `termination_scope`; they do not
claim that the still-unconverted public CLI cancellation workflow is qualified.
All 20 scoped pytest command/environment/argument/result records are in
`task-12-exact-scoped-commands.json`, with untouched logs/XML beside them.

`task-12-evidence.py` in the ignored evidence directory reproduces node
inventories, raw trace pairs, mixed-age comparisons, HEAD-relative Ruff and
source/evidence/fixture proofs:

```bash
conda run --no-capture-output -n frameit_env python "$E/task-12-evidence.py" lint final
conda run --no-capture-output -n frameit_env python "$E/task-12-evidence.py" scope final
conda run --no-capture-output -n frameit_env python "$E/task-12-evidence.py" compare required
```

The saved baseline is **mixed age**, not a Task12 run or a fresh Task11 full:
2,421 pre-fix full nodes overlaid with 613 post-fix covered nodes, including nine
added cases, for 2,430 total. Exactly 1,817 baseline nodes were not rerun in
Task11 fix1. Task12 compares individual outcomes/causes against both original and
fresh scoped inventories; newly added nodes are listed separately.

## Limits and retained gates

- No transaction across records/products, fsync guarantee, implicit replay/resume,
  stale-lock reclamation, automatic product audit or orphan cleanup.
- SIGKILL/native crash/node loss can leave last-known running status, a lock,
  partial or uncheckpointed publication. `updated_at` is not a heartbeat.
- Zarr replacement has its existing visibility gap; caught failures restore the
  earlier store. Tests inspect that gap/rollback without claiming atomic exchange.
- A persistent status-device failure can prevent any new status checkpoint.
  Exceptions propagate; the previous record remains last-known evidence.
- No production/archive/cluster run, benchmark, dependency/native repair,
  warning suppression, screenshot/image check or human scientific acceptance.
- Lead owns canonical documentation/strict build/publication/text-only GUI
  acceptance, independent review and commits. Worker does not stage or commit.
- CLI/producers13–16, HPC18, native/warnings/integration19, docs20 and human21
  retain their separate gates. Task09 Minor3 remains19/final debt.

## Single frozen-candidate full result

Observed once, after the notified freeze:
**2,015 passed, 468 failed, 2 errors**, 6,366 warnings, four passed subtests,
525.62 s, exit 1, across **2,485 distinct nodes**.

- All 2,430 mixed-age baseline nodes retain their outcomes.
- All 55 Task12-added nodes pass separately.
- All 2,421 original pre-fix-full nodes and all 613 post-fix covered nodes are
  present and unchanged. The 1,817 previously unrun nodes were freshly exercised
  here; this does not create a post-fix Task11 full retroactively.
- All 470 prior failed/error nodes remain individually classified with retained
  raw message/trace pairs. 162 traces are raw-identical; 307 retain the complete
  normalized exception lines and primary message. The remaining Slurm node
  differs only in its generated attempt suffix, inspected explicitly.
- No old test status changed and no new failed/error node was observed. This is
  not an all-green suite or evidence against the separately reproduced
  optional-positional constructor defect, which the suite does not cover.

Evidence: `task-12-full-summary.json`, `task-12-full-classified.json`,
`task-12-full-failures.md`, `task-12-full-trace-pairs/` and
`task-12-full-slurm-diff.txt`, under the ignored task evidence directory.
Raw XML SHA-256:
`376ce6adb6cb405bdea9bf5862a09d38cbf36b0ed0d2b565a40f98ef6ea1dd5f`;
raw log SHA-256:
`276f95d9bb3240b91d856766faeae39efcdb55d781438cb5703d26c5517c568d`.

Post-full freeze, scope, nine fixture hashes, 4,389 prior evidence hashes,
unchanged test ASTs and bounded production-definition AST checks pass.
HEAD-relative Ruff remains 41 prior → 39 current, zero new; the task evidence
helper also passes Ruff. The index is empty and HEAD remains the supplied base.

**Handover: NEEDS_CONTEXT.** The frozen candidate remains unchanged. The smallest
proposed compatibility correction is to make only the new `request_context`
dataclass field keyword-only, with a baseline-positional-constructor regression.
Lead ruling is required before lifting the freeze or changing the agreed
single-full verification policy. No post-freeze fix, second full, stage or commit
is claimed. Exact constructor evidence and the complete handover are in
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-12-report.md` and
`task-12-positional-compatibility-probe.txt`.
`task-12-artifact-hashes.json` indexes the final worker evidence and this checks
file without changing or replacing prior task evidence.

## Authorized constructor correction — latest handover

This append supersedes the earlier constructor warning/NEEDS_CONTEXT, preserving
the original report/checks bytes and evidence. The lead's bounded ruling is
`task-12-compatibility-correction.md`; original candidate tree:
`ca00d21690f39e61c85c4a0cb04fa8bbbeffd11c`.

Only `SimulationConfig.request_context` gains `kw_only=True`. All old fields,
defaults, positional order and methods stay unchanged. The original test module
prefix and55cases remain byte-for-byte intact. One appended regression covers
the actual optional-positional call at71, positional/match-argument order and
explicit keyword context with independent nested copying. No Git-dependent test,
giant signature fixture or source dataset is used.

Using the environment exports above, the exact correction selections were:

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_v3_run_state.py::test_request_context_preserves_positional_constructor_and_keyword_copy \
  --junitxml="$E/task-12-compat-red.xml"
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_v3_run_state.py \
  --junitxml="$E/task-12-compat-focused.xml"
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_v3_run_state.py \
  src/frameit/testing/numerical/test_v3_execution.py \
  src/frameit/testing/numerical/test_v3_outputs.py \
  src/frameit/testing/numerical/test_v3_resources.py \
  src/frameit/testing/numerical/test_hpc_execution.py \
  src/frameit/testing/numerical/test_output_layout.py \
  src/frameit/testing/numerical/test_zarr_export.py \
  src/frameit/testing/numerical/test_configuration_v3.py \
  --junitxml="$E/task-12-compat-covering.xml"
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_hpc_execution.py \
  src/frameit/testing/numerical/test_output_layout.py \
  src/frameit/testing/numerical/test_zarr_export.py \
  --junitxml="$E/task-12-compat-required.xml"
```

Raw stdout/stderr is retained in matching new `task-12-compat-*.log` files.

| Correction check | Observed result |
|---|---|
| RED positional regression | 1 failed at the real misplaced positional value;0.50s;exit1 |
| Complete new module | 56 passed;175warnings;23.53s;exit0 |
| Same eight-file covering | 574 passed,16 failed,1error;831warnings;114.28s;exit1 |
| Exact required62 | 45 passed,16 failed,1error;146warnings;7.92s;exit1 |
| Ruff, committed/candidate/corrected | 1/1/1existing finding;zero new; helper clean |
| New corrected freeze | 172hashes in `task-12-compat-freeze.json` |

All590covered old outcomes match the **pre-correction** `task-12-full.xml`;
one new regression passes separately. All17covered failed/error nodes retain
their normalized primary messages and complete exception lines, with individual
causes and raw message/trace pairs saved under the new correction prefix.
The56module cases include all55original cases unchanged. Required62 has no new
node and no changed old status/cause.

**No second unfiltered full or benchmark was run, per the lead ruling.**
The2015passed/468failed/2errors full is **PRE-CORRECTION ONLY**. Exactly1,895of
its nodes were not rerun after the correction. Do not infer their final freshness
from the scoped result; Task19/final integration remains required.

`task-12-compat-code-delta.diff` and the correction scope/hash proofs establish
the single flag plus append,170other unchanged Python files, original97/1,211
Task12artifact contents, original report/checks prefixes and all nine fixture
hashes. Of4,389older evidence entries,4,388current whole-file hashes match; the
lead appended to `progress.md` before/during this correction. Both its original
and resume-time SHA-256 contents remain exact byte prefixes, proven explicitly.
No worker reset or overwrite of the lead ledger occurred.

The original freeze/full/scoped evidence and all baseline copies remain intact.
New evidence/helper writes use new `task-12-compat-*` destinations; no prior
fixed-name destination was overwritten. The real index remains empty and
`git diff --check` passes.

**Latest status: DONE_WITH_CONCERNS.** Constructor compatibility is corrected;
no scientific/default/record/path behavior changed. Inherited failures/warnings,
unrun final integration, lead runtime/docs verification and independent review
remain. Corrected freeze was notified for lead checks without claiming that those
checks or any human acceptance had already occurred. No stage or commit.
Final correction evidence/report hashes are in
`task-12-compat-artifact-hashes.json`; the original artifact index remains intact.

## Lead checks on the corrected freeze

Fresh lead full run-state module:56passed/175warnings/23.59s, including actual
positional construction. Lead raw XML corroborates574passed/16failed/1error
covering and45passed/16failed/1error required, with all covered old statuses/
complete causes retained.591distinct nodes are freshly covered;1895pre-correction
full nodes remain unrun after the keyword-only correction. Full2015/468/2 is
PRE-CORRECTION only.

Lead verifies172freeze hashes,170other unchanged paths, exact one-flag replacement/
55case prefix, original artifact/report contents and9fixture hashes. Older
evidence is4388exact whole files plus the append-only lead ledger, not4389
unchanged current hashes. Fresh aligned Ruff41→39/noNew; no lint cleanup.

All three unchanged scientific example harnesses pass, with4/3/6source hashes.
Four ordinary YAML readers, importing no FrameIt and reading no source archive,
verify captured request/base/options/code identity, pending/completion and
planned-versus-actual records. Strict62/publication/13unittests and text-only live
desktop/320px layout checks pass. Preview retained; no screenshots/image review.
Independent Task12 spec/quality approval and local commit are still pending.

## Independent-review fix1/5 — I1 author verification

I1 is “A parent signal can mark a successful future consumed before its product
is recorded.” Reviewed tree:
`105fbd2a47d34f4668941b6fc95fdeccf05dee2f`.

The v3 parent no longer uses iterator observation as completion accounting.
Retention is idempotent against the existing actual-descriptor list, and the
drain reconsiders future results without duplicating products or callbacks
already retained. The existing execution checkpoint consumer/recovery is
unchanged. No registry, scan, worker replay/callback or signal suppression.

Only that parent v3 function portion and an appended integration test changed.
All56old cases and their801-line prefix remain exact. Eight new cases use real
spawned writers and actual parent SIGTERM before retention, at callback entry,
after the real checkpoint, or an error after that checkpoint, for both formats.
They check exactly-once descriptor/callback accounting, authoritative
status/provenance, ordinary-reader values/metadata and source hashes.

Using the existing environment exports, exact test selections were:

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_v3_run_state.py::test_parent_retention_boundary_preserves_each_actual_product_once \
  --junitxml="$E/task-12-fix-1-red.xml"
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_v3_run_state.py \
  --junitxml="$E/task-12-fix-1-focused.xml"
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_v3_run_state.py \
  src/frameit/testing/numerical/test_v3_execution.py \
  src/frameit/testing/numerical/test_v3_outputs.py \
  src/frameit/testing/numerical/test_v3_resources.py \
  src/frameit/testing/numerical/test_hpc_execution.py \
  src/frameit/testing/numerical/test_output_layout.py \
  src/frameit/testing/numerical/test_zarr_export.py \
  src/frameit/testing/numerical/test_configuration_v3.py \
  --junitxml="$E/task-12-fix-1-covering.xml"
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_hpc_execution.py \
  src/frameit/testing/numerical/test_output_layout.py \
  src/frameit/testing/numerical/test_zarr_export.py \
  --junitxml="$E/task-12-fix-1-required.xml"
```

Matching new `.log` files retain stdout/stderr/warnings.

| I1 check | Observed result |
|---|---|
| RED boundary cases | 2failed,6passed;33warnings;14.63s;exit1 |
| Complete new module | 64passed;207warnings;38.70s;exit0 |
| Eight-file covering | 582passed,16failed,1error;863warnings;167.54s;exit1 |
| Exact required62 | 45passed,16failed,1error;146warnings;7.95s;exit1 |
| Ruff HEAD/review/fixed | 3/3/3existing findings;zero new; helper clean |
| New freeze | 172hashes in `task-12-fix-1-freeze.json` |

Both RED failures were actual before-retention omissions: the successful product
independently reopened, SIGTERM143 propagated, but its descriptor count was zero.
All six after-retention/error controls passed before the fix and remain covered.

All591pre-I1 covering outcomes match `task-12-compat-covering.xml`;8new I1 cases
pass separately. All590covered historical-full outcomes match
`task-12-full.xml`; its9additional covered nodes are the constructor regression
plus8I1 cases. Required62 outcomes are unchanged against both baselines.
Every covered failed/error primary message and complete exception lines match;
individual raw pairs and causes remain under new fix1 comparison/pair paths.

**No second full or benchmark.** The2015/468/2full is explicitly
**PRE-CONSTRUCTOR/PRE-I1**;1,895of its nodes were not rerun for I1.
Final Task19/integration remains required, not inferred from scoped coverage.

Scope/AST/hash proofs retain170other Python files, the old56case prefix,
outer/legacy/worker/encoding paths, all prior review/full/freezes/correction
evidence and original report/checks prefixes. All9fixture hashes match.
The5,696path I1-start snapshot is preserved except authorized append-only
reports/lead ledger. In the older4,389index, lead `progress.md` is append-only
with its original byte-prefix hash, and the live lead `preview.md` pointer had
already changed before I1 but still matches its I1-start hash; the other4,387
whole-file hashes match. These mutable handoff differences are recorded, not
silently reset or called unchanged historical files.

**Latest author status: DONE_WITH_CONCERNS.** I1's reproduced omission is fixed
in the bounded lane, but author verification does not independently close I1.
Lead scoped checks and original-reviewer closure still precede commit/Task13.
No scientific/default/public-docs change, stage/commit/push, reviewer/subagent,
native/environment change or image check. Corrected freeze was notified.
Final source/evidence proofs and current-report checksums are indexed under
`task-12-fix-1-scope-handover.json`, `task-12-fix-1-freeze-verified.json` and
`task-12-fix-1-artifact-hashes.json`, without replacing previous indexes.

### Lead verification before scoped I1 re-review

Fresh lead run-state module:64passed/207warnings/38.93s. This includes8new
real spawned-writer interruption/callback cases, exactly-once persisted inventory
and ordinary-reader/source-hash checks. All56prior cases remain verbatim/passing.

Lead raw XML checks preserve all591pre-I1 covered outcomes plus8newpasses:
covering582passed/16failed/1error; required45passed/16failed/1error. Complete
failed/error causes match both baselines.599distinct fresh nodes;1895historical
full nodes unrun. No post-I1 full exists;2015/468/2 is PRE-CONSTRUCTOR/PRE-I1 only.

All172freeze hashes/170other source paths, exact parent-only AST/test prefix,
5696prior artifact contents and9fixture hashes verified. Historical mutable
preview/ledger differences remain explicit, not blanket whole-file preservation.
Fresh fix-path Ruff3existing/noNew. Public pages equal the reviewed tree;
strict63/publication/13unittests pass and5HTMLpages equal62. Text-only live
desktop/320checks pass; preview retained, no images or human acceptance.
Original reviewer I1/new-fix closure remains pending; no Task12 commit.

## Independent closure and handoff

Original reviewer closes I1 and approves fix1 spec/quality with0new
Critical/Important/Minor findings; no Task12 finding remains open or parked.
Constructor and all other original task assessments remain accepted. This is not
whole-branch, scientific, human or post-fix-full approval.

Fresh lead command, required environment:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_run_state.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-12-lead-fix-1-focused.xml
```

Observed64passed/207warnings/38.93s. Saved covering/required/freeze/strict63/
publication/text-only GUI evidence above remains current. Source/tests/public
pages and record contract match reviewed7add8194bd499560db0ec618395ecb6cd6cac692;
only final internal checklist/closure records change after approval.
STATE's frozen Task12 handoff records interfaces, compatibility and unresolved
gate owners. Commit locally before Task13; no push or merge.
