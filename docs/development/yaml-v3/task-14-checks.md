# Task14 execution/progress checks

Internal portable handover, not published guidance or scientific approval.
Base `106812d83d0ace0a0930c52409c43b3bbd1d9f32`.
**Source/tests frozen; full diagnostic pending scope clarification.**

## Runtime and boundaries

Public `execute_simulation(config, options=None, *, input_files=None)` and
`FrameitRunner` signatures stay unchanged. Execution wraps its owning facts once
with `preflight_result(config, prepared_sources[0], command="run")`.
`runner.preflight_result` retains the typed result; `runner.prepared_sources`
retains the original tuple and `runner.preflight_report` its facts. Task15 may
project that result for presentation, not re-collect/bind or execute a projection.
It is not added to `SimulationExecutionResult.to_dict` or run records.

Private `_QuietProgress(logger, *, interval=30., clock=time.monotonic)` is in
existing `utils/logging.py`. Its API is
`update(operation, *, source=None, prepared_sources=0, tracking_operations=0,
published_products=0)`, `start()`, `stop()`, `finish(state)`.
`_report(*, force=False, level=logging.INFO)` and `_watch()` implement the owned
scalar reporter. No new module, event framework, dependency, worker hook or pool.
`frameit_logging_scope` has the same signature; a `None` output path provides
early scoped stderr without creating output roots.

Phases name selected metadata preparation, lazy source/graph preparation, actual
tracking, lazy model-grid/polar preparation, combined compute/write export,
cleanup and record/ownership finalization. Prepared sources are not computed
fields; tracking-operation counts do not imply complete tracking; publication
counts come only from existing parent retained-publication callbacks. The active
writer/source is not probed or guessed. Start/terminal and repeated notices go
to stderr/applicable logs at the selected level, never JSON stdout or status
heartbeats. Reporter stop/join precedes handler closure, also on BaseException.
Final success follows input cleanup and final record/ownership exit.

**Frozen interval:30seconds.** Deterministic3600ticks+30boundaries yield122records
including terminals;10000extra updates/checks yield0extra records in0.0025s.
Real shortened-interval test:0.0204s,2records and joined stop. A logging transition
at29s preserves the remaining1s deadline. This is bounded engineering evidence,
not native/HPC performance qualification or a30s real-time wait.

## Environment and commands

From the worktree root, every Python check used these environment values:

```bash
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR=/tmp/opencode
export PYTHONPATH="$PWD/src"
export FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01"
```

Interpreter/import check executed:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run -n frameit_env python -c 'import sys,frameit; from pathlib import Path; assert sys.version_info[:2]==(3,13); assert Path(frameit.__file__).resolve().is_relative_to(Path("src").resolve()); print(sys.executable); print(frameit.__file__); p=Path(".superpowers/sdd/CHECKLIST_FOR_AGENTS"); print("\n".join(str(x) for x in sorted(p.glob("task-14-*"))))'
```

Result: frameit_env Python3.13 and this worktree's `src/frameit/__init__.py`.
No install, native/package/environment repair, warning filter or source-data write.
All XML/log artifacts below are under `.superpowers/sdd/CHECKLIST_FOR_AGENTS`.

Exact final focused command (same environment above):

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_progress.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_logging.py --capture=tee-sys --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-focused-final.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-focused-final.log 2>&1
```

Observed **67passed,213warnings,2subtests,40.65s**, exit0.
The public matrix covers no-region native, independent clocks, sparse actual
tracking/derived reads, explicit hPa->Pa transform, track-only and polar-only.
It asserts typed tuple/facts/child/binding identity, selected backend footprints,
values/units/metadata with fresh ordinary readers and exact source hashes.
The32progress cases cover deterministic rates/activity, real quiet preparation,
lazy source graphs, gated real sync/spawn NetCDF/Zarr compute/write, retained
publication counts, failure/KeyboardInterrupt/SystemExit, cleanup/final-record
failure, quiet tracking/cleanup/finalization, accepted actual incomplete tracking,
repeated runs, selected levels and handler restoration, no status heartbeat or
premature success. The reporter never receives arrays, graphs or futures.

Exact covering command:

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_progress.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_logging.py src/frameit/testing/numerical/test_v3_reports.py src/frameit/testing/numerical/test_v3_run_state.py src/frameit/testing/numerical/test_v3_resources.py src/frameit/testing/numerical/test_v3_outputs.py src/frameit/testing/numerical/test_v3_polar.py src/frameit/testing/numerical/test_v3_regions.py src/frameit/testing/numerical/test_v3_operations.py src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_matrix_progress.py src/frameit/testing/numerical/test_coupled_shared_polar.py --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-covering.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-covering.log 2>&1
```

Observed **637passed,19failed,1error,2335warnings,2subtests,266.70s**, exit1.
619old statuses unchanged;38new nodes pass;2002prior nodes not covered.
This retains Task12 records/publications/clearance/resource/spawn and C4–C8
scientific/selection/clock/W/speed/CF/precision checks without old-test edits.

Exact required modules from the brief, unfiltered (XML/long traceback added):

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_logging.py src/frameit/testing/numerical/test_matrix_progress.py src/frameit/testing/numerical/test_coupled_shared_polar.py --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-required.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-required.log 2>&1
```

Observed **67passed,19failed,1error,157warnings,2subtests,22.53s**, exit1.
All81old statuses/complete exception causes unchanged;6new matrix nodes pass.
The prior61/19/1 is historical evidence, not relabelled as this run.

## RED/GREEN command inventory

Every row uses `conda run --no-capture-output -n frameit_env python -m pytest -q`
after the environment assignments above, followed by the literal targets/flags
below. Each has `--junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/<stem>.xml`
and `> .superpowers/sdd/CHECKLIST_FOR_AGENTS/<stem>.log 2>&1`.
Here `N=src/frameit/testing/numerical` is just table shortening, not an extra flag.

| Artifact stem | Targets and traceback/capture flags | Observed |
|---|---|---|
| task-14-red-selected | `N/test_v3_execution.py::test_selected_execution_owns_one_typed_plan --tb=long` |6failed; one new fixture used an unsupported conversion |
| task-14-red-selected-valid | same target, `--tb=short` |6failed at missing typed wrapper |
| task-14-green-selected-initial | same target, `--tb=long` |6passed/40warnings/8.72s |
| task-14-red-progress | `N/test_v3_progress.py --tb=short` |9failed at missing reporter |
| task-14-green-reporter | `N/test_v3_progress.py::test_clock_bounds_busy_and_quiet_messages_without_resetting_real_activity N/test_v3_progress.py::test_real_quiet_wait_stops_promptly_and_restores_scoped_handlers N/test_logging.py --capture=tee-sys --tb=short` |5passed+2subtests/0.43s |
| task-14-red-finalization | `N/test_v3_progress.py::test_terminal_success_waits_for_cleanup_and_records --tb=long` |3failed: false success, masked primary |
| task-14-green-integration-initial | `N/test_v3_progress.py N/test_v3_execution.py::test_selected_execution_owns_one_typed_plan N/test_logging.py --capture=tee-sys --tb=long` |18passed+2subtests |
| task-14-red-boundaries | `N/test_v3_execution.py::test_selected_execution_owns_one_typed_plan N/test_v3_progress.py::test_quiet_lazy_preparation_has_source_but_no_completed_values 'N/test_v3_progress.py::test_lazy_compute_write_counts_only_parent_retained_publications[completed-sync-netcdf]' --tb=long` |8failed at source/count boundaries |
| task-14-green-boundaries-initial | `N/test_v3_progress.py N/test_v3_execution.py::test_selected_execution_owns_one_typed_plan --tb=long` |28passed/120warnings/25.34s |
| task-14-focused-initial | final focused targets/flags above |63passed/186warnings+2subtests/39.80s |
| task-14-red-deadline | `N/test_v3_progress.py::test_logging_transition_keeps_the_existing_quiet_deadline --tb=long` |1failed,30s versus remaining1s |
| task-14-focused-final | complete literal command above |67passed/213warnings+2subtests/40.65s |

## Every inherited failure/error and complete evidence

`task-14-covering-comparison.json`, `task-14-required-comparison.json` and their
`*-node-ledger.md` files retain every covered old/new status. Per-node JSON/diffs
in `task-14-{covering,required}-trace-pairs/` retain full prior/current traceback,
message and complete exception lines. All20failed/error causes match; no blanket
numerical validity or lower scientific assertion is inferred:

| Existing node (module prefix omitted) | Actual unchanged cause |
|---|---|
| `test_hpc_execution::test_exclusive_run_ownership_and_early_no_clobber` |old-v2 fixture rejected before execution |
| `test_hpc_execution::test_batch_overrides_dry_run_does_not_claim_output` |old-v2 CLI request exits1 instead of expected0 |
| `test_hpc_execution::test_cli_processing_failure_never_marks_completed` |old-v2 CLI request exits before expected status exists |
| `test_hpc_execution::test_incomplete_tracking_is_explicit_and_strict_policy_fails` |old-v2 fixture rejected before tracking |
| `test_hpc_execution::test_cancellation_and_same_root_exclusion[sigterm]` |old-v2 request never starts the blocking runner/ready file |
| `test_hpc_execution::test_cancellation_and_same_root_exclusion[sigkill]` |same actual ready-file failure |
| `test_hpc_execution::test_concurrent_cli_attempts_spawn_and_sync_export_exactly` (setup error) |old-v2 CLI setup exits1 before attempted concurrent execution |
| `test_coupled_shared_polar::test_shared_target_schema_is_additive_and_global` |old expected `shared_target` error versus actual v3 schema rejection |
| `test_coupled_shared_polar::test_three_products_share_moving_target_but_not_masks[True]` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_three_products_share_moving_target_but_not_masks[False]` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_disabled_shared_target_keeps_base_processing_optional` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_mismatched_actual_targets_fail_before_product_publication` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_shared_target_keeps_atmospheric_vertical_groups_separate` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_dense_fa_surface_moving_polar_values_masks_and_readonly_inputs[True]` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_dense_fa_surface_moving_polar_values_masks_and_readonly_inputs[False]` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_primary_pair_shared_target_geometry_budgets_and_fresh_exports[True]` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_primary_pair_shared_target_geometry_budgets_and_fresh_exports[False]` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_primary_pair_planning_guards_precede_payload_and_target_allocation[target_budget]` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_primary_pair_planning_guards_precede_payload_and_target_allocation[finer]` |old-v2 producer rejected |
| `test_coupled_shared_polar::test_primary_pair_planning_guards_precede_payload_and_target_allocation[native_budget]` |old-v2 producer rejected |

All old shared producers/literals/assertions remain untouched; conversion is
owned by15–16, not a Task14 workaround.

## Scope, hashes, lint and genuine freeze

Commands executed with the same environment prefix:

```bash
conda run --no-capture-output -n frameit_env python -m ruff check src/frameit/core/execution.py src/frameit/core/runner.py src/frameit/core/coupled.py src/frameit/utils/logging.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_progress.py --output-format=json > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-ruff-initial.json
conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-evidence.py compare covering > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-covering-comparison.log 2>&1
conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-evidence.py compare required > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-required-comparison.log 2>&1
conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-evidence.py proof prefreeze > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-prefreeze-proof.log 2>&1
conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-evidence.py proof prefreeze-final > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-prefreeze-final-proof.log 2>&1
conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-evidence.py freeze freeze > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-freeze.log 2>&1
```

Initial lint:14existing+1new test E501, then corrected. Initial evidence-script
proof stopped at3new E501s in that script; corrected without old-source cleanup.
Final proof:14inherited/0added on all6owned source/test paths plus evidence script,
179other tracked Python paths byte-exact; old execution file prefix483lines exact.
Coupled/runner ASTs are exact after stripping added scalar progress assignments;
all untargeted execution/logging definitions exact. Execution's scientific
processing/export/result body is AST-exact after stripping progress and its
old premature success log. Writer, C4–C8 methods, all other old tests/producers,
package/native/environment files are unchanged.

2430initial immutable root artifacts remain exact; the2431st initial root entry
is explicitly lead-owned `preview.md`. Nine fixture payload checksums and all12
initial fixture entries remain exact. Proofs copy explicit mutable lead files
(STATE, real checklist, progress contract, two canonical pages, progress/preview/
lead handovers), not wildcard history exclusions. `task-14-freeze.json` records
175source/test hashes and a separate pre-full recursive immutable-evidence
snapshot. No staging or commit occurred; the lead owns both.

## Remaining full gate and limitations

No Task14 full run yet. Prior2621 is still explicitly mixed-age:
600Fix2-covered,279Fix1-only,1742pre-fix-full-only; no corrected13full exists.
Scope conflict: configured unfiltered pytest includes two existing PNG-generation
tests in `docs/test_documentation_plots.py`, while this task prohibits image/plot
checks. Lead must authorize those existing tests or leave the full diagnostic
blocked; silently filtering would not satisfy the one-full/all-prior-node rule.

No scientific/default/output/configuration/dependency change or human approval.
RunTimer/result timing definitions are unchanged, not reinterpreted as measured
deferred numerical computation. No new completion percentage or ETA; old
section-timing shares remain timing, not work progress. The reporter needs a
responsive interpreter and logging handler; an in-flight handler can delay join.
SIGKILL/native loss cannot guarantee Python cleanup/final records. Task12's
secondary record-error behavior is preserved; no status heartbeat, replay, scan,
repair, fsync/cross-record transaction or extra payload/graph reads are added.

Lead owns public prose, strict Sphinx/publication/live GUI acceptance and
independent review. CLI/producers15–16, HPC18, native/warnings/full integration19,
Task09Minor3, docs20 and human scientific/usability21 retain their gates.

## Full-suite scope ruling and one launch

The preceding pending-full note records the earlier handover, not a continuing
ambiguity. `task-14-full-ruling.md` explicitly authorizes the two unchanged PNG
script smoke tests only within the required unfiltered suite. No standalone plot
test, generated-image viewing, pixel/figure inspection, asset/test edit or
screenshot/JPEG is performed. The existing tests retain their original assertions.

Prelaunch175source/test and7447recursive old-evidence hashes matched the genuine
freeze; Python3.13, worktree import, unchanged HEAD and empty index were checked.
There was no earlier Task14 full XML or log. The single background launch is:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-full.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-full.log 2>&1
```

No filter, skip, warning suppression, short timeout or polling. The shell
completion notification supplies the actual result; none is claimed at launch.

## Blocking author finding A1: terminal count misses a retained publication

A read-only check of Task12's callback-entry interruption boundary found a new
Task14 contract gap. The existing unchanged test was probed once, not as another
full run and not as a new source/test edit:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q 'src/frameit/testing/numerical/test_v3_run_state.py::test_parent_retention_boundary_preserves_each_actual_product_once[callback_entry-netcdf]' --capture=tee-sys --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-callback-entry-probe.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-callback-entry-probe.log 2>&1
```

Observed **1passed,5warnings,2.64s**. The old assertions correctly prove2complete
retained/status/provenance products and interruption143. They do not assert the
new terminal progress, which incorrectly reports **published products=1**.
`task-14-callback-entry-finding.json` contains the exact terminal, actual relative
paths, record hashes and pending/error facts.

Writer retention occurs before callback entry. SIGTERM can prevent the execution
callback's count increment, while the existing retained-path guard correctly
prevents replay during drain. Execution recovers records from actual descriptors
but does not reconcile the reporter counter. No source data/product/record loss
was observed; terminal progress is inconsistent with the authoritative inventory.

**A1 blocks Task14 completion.** It is new progress behavior, not inherited old-v2
failure debt or independent review. The lead has been notified. No fix, new test,
callback replay, writer change or second full is made under the frozen-source
instruction. A green existing record test is not a progress-contract pass.

## Final frozen-source result — BLOCKED on A1

The ONE full command completed by shell notification, exit1:
**2189passed,468failed,2errors,6570warnings,4subtests,583.64s**. No polling,
avoidably short timeout, second full, source/test/environment/package/native
change or warning suppression. Both authorized existing PNG smoke tests passed
only within that full; no generated image was opened or visually inspected.

Full comparison/proof commands executed:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-evidence.py compare full > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-full-comparison.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-evidence.py proof full-final > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-full-final-proof.log 2>&1
git diff --check
```

Observed exit0:

- All2659nodes accounted for: every2621old status unchanged, zero old missing/
  recovered/new failures, and all38new Task14 cases passing separately.
- Old freshness is retained:600Fix2-covered,279Fix1-only,1742pre-fix-full-only.
  This fresh Task14 diagnostic does not relabel historical13evidence or make
  the failed full suite green.
- All470failed/error nodes have complete old/current raw messages/traces,
  complete exception/assertion lines and diffs under `task-14-full-trace-pairs/`.
  The2659-node ledger and comparison JSON record every outcome, not only counts.
-197cause pairs differ only under the existing runtime normalization;272retain
  identical complete normalized exception lines/call sites with pytest context/
  repr changes. One Slurm-shim failure was manually examined: the exact remaining
  fragments ending in `.../pytest-187/` and `.../pytest-227/` differ only in the
  generated scratch ID (full observed fragments are in the local adjudication).
  Replacing just those observed fragments makes the whole normalized trace,
  message and all complete exception lines equal. Its source test still imports
  unchanged `test_configuration_v2_1.document`, which emits the same v2 request;
  the v3 CLI guard remains the actual cause.
- The automatic comparison's one review flag is preserved, not overwritten.
  `task-14-full-classified.json` contains that exact adjudication and zero
  unresolved old-cause comparisons. `task-14-full-causes.md` lists every failed/
  error node, actual complete message/exception lines and raw-pair reference.
- `task-14-full-warnings.txt` preserves the raw warning section: ABI warning,
  NumPy2.5NetCDF shape deprecations, cfgrib/xarray default notices and fixture
  time-bounds-unit notices remain visible, not repaired or suppressed.
- Final proof/audit preserves175frozen source/test paths,179other tracked Python
  paths, old execution483-line prefix/all other old tests/producers, exact scoped
  ASTs,2430initial root+7447pre-full recursive immutable artifacts,9fixture
  payloads/all12fixture entries with no added sidecars. HEAD-relative Ruff is
  14existing->14current,0new across6owned source/test paths plus frozen evidence
  script. Explicit lead-history snapshots remain separate from immutable proof.

Audit: `.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-final-audit.json`.
Raw full SHA-256:

```text
task-14-full.log  4e36ee7753ab57a6845195b1a243af3120840132890091010ee6ab7284fdcdba
task-14-full.xml  29a1bd327c376c42d8f03bbd635dcea4c67e05dacd2fa6a068bc1c244f34bccb
```

**A1 remains a new blocking Task14 defect:** callback-entry interruption can
leave2actual retained/status products while terminal progress says1. It is
separate from the470unchanged old test failures/errors. No post-freeze fix or
assertion is added, and this full result cannot validate a future fix.
Lead-authorized thaw/TDD work, lead checks and independent review are needed
before Task14 completion/commit. Scientific values and authoritative records
remain intact in the reproducer; progress inventory reporting is not complete.

No staging, commit or push by the worker. Lead owns public documentation/build/
GUI checks and later local commit. Existing CLI/producers/HPC/native/warnings/
Task09Minor3/docs/human gates remain; no new scientific or visual acceptance.

## Authorized A1 author correction (after the PRE-A1 full)

Lead's `task-14-A1-handoff.md` authorizes only private count reconciliation and
appended progress regressions. This is not independent review or scientific
approval. Every preceding full/freeze/probe/result remains intact; the full
2189passed/468failed/2errors is **PRE-A1**, not a corrected-source result.

### Root, change and consumer

The parent retains complete descriptors before invoking `on_published`.
Callback-entry SIGTERM can skip the progress increment; the existing retained-
path guard correctly prevents callback replay during graceful drain. Existing
records already recover from those retained descriptors.

The correction is one `_execute_simulation` finally-line, after export/drain/
recovery and before cleanup/terminal output:

```python
progress.reconcile_published(len(getattr(runner, "published_products", ())))
```

The only helper addition is
`_QuietProgress.reconcile_published(self, count)`: assign the actual scalar total
under its existing lock. This is absolute/idempotent, not another increment.
It does not emit a message, read a clock, reset activity, change operation/source/
other counts or replay a callback. Existing `update` increment semantics,
30s/rate/wait/thread/logging lifecycle and terminal-after-finalization placement
are unchanged. No field/graph/future/directory scan, added payload read, writer,
record, scientific/resource/API/configuration change.

Production files are byte/AST-exact to PRE-A1 after removing exactly that one
execution line and the five-line scalar helper block. The536-line/32-case
progress prefix is exact. Three appended functions add11cases: all four existing
retention boundaries for NetCDF/Zarr via the unchanged Task12 test, successful
non-double-counting for both formats, and scalar idempotence/activity/increment
compatibility. Reused boundary tests retain actual paths, callback-once, ordinary
readers, source hashes and terminal state/error assertions.

### Exact test commands/results

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_progress.py -k a1 --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-red.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-red.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_progress.py -k a1 --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-green.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-green.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_progress.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_logging.py src/frameit/testing/numerical/test_v3_run_state.py --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-modules-final.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-modules-final.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_logging.py src/frameit/testing/numerical/test_matrix_progress.py src/frameit/testing/numerical/test_coupled_shared_polar.py --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-required.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-required.log 2>&1
```

| Run | Actual result |
|---|---|
| RED |3failed/8passed/32deselected/41warnings/17.47s; missing assertion catches terminal1versus actual2 for both formats, plus missing scalar method |
| GREEN |11passed/32deselected/41warnings/17.19s |
| Final complete progress/execution/logging/run_state |142passed/459warnings/+2subtests/95.40s |
| Exact required modules, unfiltered |67passed/19failed/1error/157warnings/+2subtests/22.08s |

The first complete-module run (`task-14-A1-modules` with identical targets/flags)
passed142/459warnings/+2subtests/95.45s. Initial proof found four unique new
E501s, only in two appended assertions and two evidence-script lines. They were
wrapped without changing assertions/production logic; final complete modules
were rerun on the final test bytes, not merely to regenerate XML. The first
failed proof and both runs remain separate immutable A1 artifacts.

### Every covered old/new result and unrun full node

The A1 module/required comparison JSONs and node ledgers compare against the
PRE-A1 `task-14-full.xml`. Every covered old status and all20covered complete
failed/error causes are preserved with full old/current messages/traces,
exception lines and raw diffs. No newly changed old status or unresolved cause.

`task-14-A1-combined.json`:194distinct corrected nodes,174passed/19failed/1error;
183old statuses preserved,11new A1 cases listed separately. The2476old full
nodes not rerun after correction are listed individually in that JSON and
`task-14-A1-unrun-full-nodes.md`:2026PRE-A1passes/449failures/1error, strictly
historical, not corrected-source results.

No second full, old covering, scientific harness or benchmark was run. No plot/
image check or image viewing. Untouched-code proof plus fresh bounded execution/
publication checks does not establish whole-suite, native/HPC, scientific or
human qualification. Lead owns full raw-cause audit/public docs/STATE and fresh
whole-Task14 independent review before a later local commit.

### Corrected freeze and exact preservation checks

`task-14-A1-freeze.json` records the genuine corrected175-path source/test
freeze. A1 is author-corrected in the tested lanes, not independently reviewed.
No production/test change follows that freeze; handovers/explicit lead histories
may append. No source data, status/provenance semantics or scientific default
changed.

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-verify.py compare modules > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-modules-comparison.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-verify.py compare modules-final > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-modules-final-comparison.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-verify.py compare required > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-required-comparison.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-verify.py proof prefreeze > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-prefreeze-proof.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-verify.py proof prefreeze-clean > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-prefreeze-clean-proof.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-verify.py proof freeze > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-14-A1-freeze-proof.log 2>&1
git diff --check
```

All exit0 except the preserved first prefreeze lint failure described above.
Observed final proof:

- Only execution/logging and appended progress tests differ from PRE-A1.
  Removing one added execution call and the five-line scalar method block gives
  byte/AST-exact production files; all existing helper behavior is unchanged.
-172other package Python paths and179other original tracked Python files are
  exact. The536-line/32-case progress prefix and all other old tests/producers/
  assertions remain intact. Writer retention/callback/drain/records and all
  scientific/resource paths are byte-exact.
-7447pre-full artifacts exact. Of1148prior Task14 artifacts,1146are immutable
  and exact; author/lead reports use explicit preserved copies/prefixes. All8
  baseline copies remain exact. Original portable-check/report prefixes and
  named mutable lead report/progress/preview histories are separately retained,
  not excluded by wildcard.
-9approved payloads/all12fixture entries exact, with no added sidecars.
- Fresh actual-path Ruff compares all3A1 source/test paths plus the A1 evidence
  script against HEAD and PRE-A1 copies:4existing->4current,0new against both.
  No inherited lint cleanup or warning suppression.
- `task-14-A1-source.diff`, proof/freeze JSONs and raw XML/logs preserve exact
  deltas, hashes, command outcomes and complete per-node cause evidence.

No second full/old covering/harness/benchmark. The2189/468/2full remains strictly
PRE-A1;2476full nodes are not retested on corrected source. Lead checks and fresh
whole-Task14 independent review, final19full and the retained scientific/native/
HPC/docs/human gates remain necessary. No public API/schema/default/dependency
change, stage, commit, push, subagent/reviewer, image/screenshot or source-data
write by this worker.

## Lead verification of the corrected freeze — review pending

Fresh lead complete progress/execution/logging check:78passed/253warnings/
2subtests/58.27s, including all11A1 regressions. Actual retention/record/
ordinary-reader/source-hash/callback-once assertions remain intact.
Fresh175hashes/172other Python/byte+AST outside six additions/536line prefix/
7447pre-full1146Task14 immutable artifacts/explicit histories/9payload12fixture
proof passes; HEAD/PRE-A1 Ruff4→4/noNew, not clean whole-repo lint.

Lead raw XML corroborates142module passes and67/19/1required,194distinct
corrected nodes/183old statuses/11newpasses. Every20required complete cause
pair is runtime-normalized exact.2476full nodes remain unrun after A1;
full2189/468/2strictly PRE-A1. Scientific harnesses also remain PRE-A1.
Strict68/publication/13unit pass; both public HTML pages equal live-checked67.
Canonical67retained with earlier text-only1020/320inspection; no new image or
human claim. Fresh whole-Task14 independent review/local commit still pending.

## Independent closure

Fresh whole-Task14 reviewer approves spec and quality,0Critical/Important/Minor.
The complete11file2387line reviewed tree is0114028b1e17632057cbbb560255ae8532ac77bc.
A1 corrected/closed, no open or parked Task14 issue. Source/tests/public prose
remain byte-exact to that tree; only internal checklist/closure records change.
Latest lead78passes/253warnings/2subtests58.27s and strict68/publication/13unit
evidence remain on unchanged source. Task14's full2189/468/2remains PRE-A1;
2476full nodes unrun corrected, inherited failures/warnings and later19/full/
scientific/native/HPC/human gates remain explicit. Preview67retained/no images.
Local commit precedes15; no push or merge.
