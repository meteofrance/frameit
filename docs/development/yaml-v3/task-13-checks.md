# Task13 reproducible checks

Internal implementation evidence, not scientific or human approval.
Base: `69e69923f2d827c724c03812ce248a67e08b41a2`.

Latest: Task13 spec/quality independently approved after two fix rounds; all
four findings and the root-repair follow-up are closed. Final reports127pass.
Full2062/468/2is PRE-FIX1/PRE-FIX2;279Fix1-covered/2021historical full nodes remain
unrun on final code. Historical pending sections below retain original evidence.
Final interfaces/compatibility/limits are in STATE's frozen Task13 handoff.

## Runtime and inputs

Run from this worktree with the existing Conda `frameit_env` (Python 3.13).
Do not install or repair packages to reproduce these results. Use the approved
read-only fixture at `build/yaml-v3-ci-fixture-01`; do not migrate shared fixtures
or write into source datasets.

```bash
conda run -n frameit_env python -c 'import sys; print(sys.version)'
```

Observed 3.13.18. Tests create small synthetic inputs and fresh outputs under
`TMPDIR=/tmp/opencode`. This does not establish suitability for all real inputs.

## Focused report tests

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py
```

Observed **38 passed**. Assertions cover:

- independent file/source/schema/binding errors, actual observed/expected facts,
  authored key/list locations, genuine repeat grouping and blocked dependents;
- unfinished inspection, real copyable 2d/3d selectors and no unsupported
  duplicate-name qualification;
- metadata-only reads, decoded 360-day clocks, bounded coordinate projection and
  NumPy/path/date/binary metadata without mutating scientific facts;
- only selected reader/product/tracker/writer dependencies; offline schema-only
  without datasets or optional dependency probes;
- actual subprocess `validate --json` success, metadata/schema/syntax/missing-file
  failures, one stdout document, stderr logs and nonzero failures;
- human facts/repairs, common validate/run-planning/effective producer identity,
  and wrapping actual execution facts without another preflight;
- failed binding revocation, actual bound product names/dimensions/units and the
  unchanged immutable run-request record schema.

Feature changes have retained RED/GREEN evidence. Calendar/offline and several
existing-boundary assertions were preservation checks that were green when first
added; no per-case RED claim is made for those. Existing tests, shared producers
and scientific assertions were not altered.

## Required command

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_wind_preflight.py
```

Observed **456 passed/17 failed**, exit1. This is a fresh Task13 run, not the saved
prior 473-node inventory presented as a new result. Every old status matches;
the 17 unchanged legacy producers still fail the integer-v3 prerequisite.
Structured error/path/location text is an intentional Task13 change, not a
claim that complete raw failure strings are identical.

## Covering command

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_wind_preflight.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_resources.py src/frameit/testing/numerical/test_v3_run_state.py src/frameit/testing/numerical/test_v3_polar.py
```

Observed **773 passed/17 failed/913 warnings**, exit1. All 752 previously covered
old nodes preserve status; 38 new nodes pass separately. Existing optional polar
backend `ImportError` behavior is preserved. Earlier interrupted/intermediate
runs are retained as such, not counted as successful covering evidence.

## Full diagnostic and evidence

One unfiltered full command is run after source/test freeze:

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q
```

Observed **2062 passed/468 failed/2 errors/6398 warnings/4 subtests passed**,
543.59 s, exit1. All 2494 old node statuses match the mixed-age baseline and all
38 separately new nodes pass. Every failed/error node has a complete before/
after cause pair: 428 retain the inherited version guard with structured C9
diagnostics, 38 have unchanged complete exception/assertion lines and call sites,
and 4 have scratch/line-only differences. No old status change, new-node failure
or unresolved cause comparison was found. This is not a green full suite.

The inherited setup errors are
`src/frameit/testing/numerical/test_hpc_execution.py::test_concurrent_cli_attempts_spawn_and_sync_export_exactly`
and
`docs/test_repository_examples.py::test_independent_checker_accepts_reference_and_rejects_wrong_time_count`.
They still fail unchanged legacy producers at the integer-v3 prerequisite.
The exhaustive failed/error names are in the local `task13-full-node-ledger.md`.
No second full run, warning suppression, fixture conversion or scientific-
assertion weakening was performed.

Local evidence uses fresh `task13-*` names in
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/`, with corresponding stdout/stderr logs
and JUnit XML. Per-node ledgers retain complete before/after failed/error traces
and classify actual changed causes, not only counts. Baseline age remains
explicit: 2485 pre-constructor/pre-I1 full nodes plus 599 post-I1 covered nodes,
2494 distinct old nodes; 1895 historical nodes were not rerun after I1.
There is no post-I1 Task12 full-suite claim.

Freeze checks retain 174 source/test hashes, 94 old testing paths and 178 other
tracked Python paths unchanged outside the allowed definitions, 9 fixture hashes,
complete prior evidence and the lead's append-only handoff history.
Baseline-relative Ruff covers every changed/new source/test Python path:
46 inherited diagnostics and **0 new**. These checks do not repair unrelated lint.
The two new local evidence scripts also have zero Ruff diagnostics. Final audit
confirms every frozen Python hash and prior evidence/history is preserved.

## Consumer interface and limits

Use `core.preflight.collect_preflight` for authored validation/inspection and
existing planning/effective handlers. `PreflightResult` retains typed internal
facts and its owning configuration. For execution/progress, wrap the existing
owning prepare/bind facts using
`preflight_result(conf, facts, command="run")`; do not inspect or bind again.
`core.reports.project_report`, `serialize_report` and `render_report` provide the
separate JSON-safe/human views.

The seven-key version 1 envelope separates valid effective configuration, origins,
observed inputs, plans and pending work. Schema-only is offline. A report's `ok`
does not mean payload/value checks, execution, publication or scientific
validation succeeded. Unknown or invalid prerequisites remain blocked; runtime
checks are deferred rather than passed.

No new scientific method/default, package dependency, YAML key, scientific output
schema or run-record field was added. No source-data writes, environment/native repair,
HPC run, extra benchmark, warning suppression, separate image/pixel/screenshot
review or human approval are claimed. The requested unfiltered full retains
existing documentation smoke tests, not visual acceptance.
Complete CLI/producers/progress/native/HPC/final/human
gates retain their approved later owners. Canonical documentation builds and
visual acceptance belong to the lead.

## Lead verification before independent review

Fresh lead report module:38passed/3.21s. Lead independently parses raw required,
covering and full XML:456/17,773/17 and2062/468/2 respectively. All2494old full
outcomes and38newpasses retained; every470failed/error pair matches its raw XML.
The428guard/38context/4runtime classes are individually corroborated, including
6explicit guard-wrapper source/repr differences rather than blanket matching.
No inherited failed cause is waived or converted to acceptance.

Fresh audit verifies174freeze hashes,94old tests/178other tracked Python paths,
9fixture hashes and5,885exact prior evidence hashes plus the append-only ledger.
Fresh6path Ruff46inherited/46current/noNew; no clean-lint claim.

All3exact documented validate commands pass on the instructional scalar.
Schema-only also passes with inputs absent. An independent stdlib reader checks
strict one-document7key JSON; two invalid sources exit1 with both exact YAML
locations/observed facts/repairs and blocked prerequisites. Logs remain stderr;
no output directory or source mutation.

Three unchanged scientific harnesses pass4/3/6source hashes with ordinary readers.
Strict64/publication/13unit and text-only live desktop/320px checks pass; preview
retained. No images, extra full run, benchmark or human/scientific approval.
Independent spec/quality review and local commit remain pending.

The preview pointer update after that audit changes a second mutable lead
handover. Current preservation is5,884exact whole-file hashes plus the saved
exact original preview and append-only ledger prefix; all174freeze hashes still
match. No test/full/review evidence changed. This does not retroactively alter
the earlier5,885exact audit result or silently waive evidence preservation.

## Review fix1 — corrected bounded checks

**All preceding full/lead/freeze results are PRE-FIX1.** In particular,
2062 passed/468 failed/2 errors is not a corrected-source result. No second
unfiltered full or benchmark was authorized or run. Author checks do not close
the four independent-review findings.

The corrected freeze is `task13-fix1-freeze.json` in the local evidence directory
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/`. It retains174 source/test hashes against
reviewed tree `3e8518672de975d99ddf86570288af379e750405`; HEAD remains
`69e69923f2d827c724c03812ce248a67e08b41a2`, with no staging/commit/push.
Use only the existing `frameit_env` Python3.13.18 and approved read-only fixture.

### What changed, without changing science

1. Known v3 schema owners retain actual paths/values/rules/repairs in existing
   diagnostics; the unchanged loader supplies same-text marks. Mapping,
   required-key, range, exclusive and conditional controls are covered. Missing
   keys report absence and a captured parent mark; in-memory input has no marks.
   No new parser, exception-prose inference, defaults or legacy-validator rewrite.
2. Invalid source identifiers join independent per-source errors in both orders;
   effective controls remain unavailable on schema failure. The original
   identifier pattern is unchanged, with no source-name vocabulary.
3. Only explicit binding consumes a private preparation-error handoff of valid
   owning metadata. Each eligible child is inventoried/bound once. Missing-source
   binding, unavailable method dependencies, cross-source geometry/products and
   execution remain blocked. Actual local unit errors still aggregate. Native
   discovery stays unbound; all parent/child/shared-target clearance is revoked
   on error, including successful native local bindings.
4. Writer dependency checks use existing effective configuration/options and
   existing Zarr version requirements. Export-disabled requests probe neither
   authored nor overridden writers or unrelated optional packages.

Only `configuration.py`'s16 relevant diagnostic owners,
`preflight.py::_required_dependencies`, `coupled.py`'s two v3 handoff owners and
appended `test_v3_reports.py` cases changed. The same public constructors,
preflight/binding callers, signatures, success tuples, report/record/resource
contracts and scientific/output semantics remain in place. No migration.

### RED/GREEN reproduction

Local evidence includes matching logs/XML for every stem below. These are the
literal argument suffixes to:

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest <arguments> --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/<stem>.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/<stem>.txt 2>&1
```

| Stem | Arguments | Observed |
|---|---|---|
| `task13-fix1-red-schema` | `-q src/frameit/testing/numerical/test_v3_reports.py -k fix1_owned_schema` | 22 failed |
| `task13-fix1-red-schema-other` | `-q src/frameit/testing/numerical/test_v3_reports.py -k fix1_other_owned_schema` | 27 failed/2 passed |
| `task13-fix1-red-schema-conditional` | `-q src/frameit/testing/numerical/test_v3_reports.py -k fix1_conditional_schema` | 14 failed |
| `task13-fix1-green-schema-final` | `-q src/frameit/testing/numerical/test_v3_reports.py src/frameit/testing/numerical/test_configuration_v3.py` | 429 passed |
| `task13-fix1-red-source-names` | `-q src/frameit/testing/numerical/test_v3_reports.py -k 'fix1_invalid_source_name or fix1_source_identifiers'` | 3 failed |
| `task13-fix1-green-source-names` | `-q src/frameit/testing/numerical/test_v3_reports.py` | 106 passed |
| `task13-fix1-red-mixed-binding` | `-q src/frameit/testing/numerical/test_v3_reports.py -k 'fix1_inventory_error or fix1_partial_inventory'` | 6 failed |
| `task13-fix1-green-mixed-binding-01` | `-q src/frameit/testing/numerical/test_v3_reports.py` | 4 failed/108 passed |
| `task13-fix1-green-mixed-binding-02` | `-q src/frameit/testing/numerical/test_v3_reports.py` | 115 passed |
| `task13-fix1-red-effective-writer` | `-q src/frameit/testing/numerical/test_v3_reports.py -k 'fix1_writer_dependencies or fix1_disabled_export'` | 8 failed/3 passed |
| `task13-fix1-green-effective-writer` | `-q src/frameit/testing/numerical/test_v3_reports.py` | 126 passed |

The intermediate mixed-binding failure identified pending centre/geometry
prerequisites, not extra local errors. Only new test assumptions were corrected;
old assertions were preserved. The native success/clearance and disabled-export
controls include preservation checks, not a per-assertion RED claim.
The appended88 cases comprise65 schema,3 source-name,9 binding and11 writer cases.

### Exact corrected verification commands

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_wind_preflight.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_resources.py src/frameit/testing/numerical/test_v3_run_state.py src/frameit/testing/numerical/test_v3_polar.py --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-covering-final-02.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-covering-final-02.txt 2>&1
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_wind_preflight.py --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-required-final-02.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-required-final-02.txt 2>&1
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py src/frameit/testing/numerical/test_v3_polar.py src/frameit/testing/numerical/test_v3_resources.py -k 'reports or shared or actual_consumers_bind_once or optional_backend_and_point_guard or failed_union_validation_revokes_shared_and_owning_clearance' --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-reports-safety-final.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-reports-safety-final.txt 2>&1
```

Observed, on final source:

- Same8 covering: **861 passed/17 failed/913 warnings**,144.79s, exit1.
- Exact required473, unfiltered: **456 passed/17 failed**,22.06s, exit1.
- Full reports + focused safety: **158 passed/157 deselected/159 warnings**,
  14.78s, exit0; all126 report cases and32 existing safety cases passed.

Earlier Fix1 covering/required logs (861/17 and456/17) remain retained. Final
`-02` runs followed six lint-only line wraps; they are byte-current verification,
not another unfiltered full or a rerun just to obtain XML. No warning suppression.

### Every covered status/cause, preservation and limits

Run the new comparison helper against both PRE-FIX1 full/covering XMLs:

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-compare.py task13-fix1-covering task13-fix1-covering-final-02.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-covering-comparison.txt 2>&1
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-compare.py task13-fix1-required task13-fix1-required-final-02.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-required-comparison.txt 2>&1
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-compare.py task13-fix1-reports-safety task13-fix1-reports-safety-final.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-reports-safety-comparison.txt 2>&1
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-audit.py task13-fix1-freeze > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-freeze.txt 2>&1
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-audit.py task13-fix1-final-audit-02 > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-final-audit-02.txt 2>&1
TMPDIR=/tmp/opencode conda run -n frameit_env python -m ruff check .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-audit.py .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-compare.py --output-format=json > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix1-evidence-lint-final-03.json
git diff --check
```

These evidence commands create outputs exclusively: use fresh `task13-fix1-*`
labels/destinations when reproducing, never overwrite earlier artifacts.
All comparison commands exit0. All790 reviewed covering statuses and all473
required statuses match both baselines; all88 Fix1 nodes pass separately.
Every17 failed/error cause pair agrees in its entire message/trace after only
scratch/address/source-line normalization. The same unchanged legacy producers
still fail the integer-v3 guard. Per-node ledgers name them; JSON/trace-pair
directories preserve every complete raw before/after cause, not only counts.

There are **1742 full-baseline nodes not rerun** on corrected source. Their
historical1289 pass/451 fail/2 error statuses are PRE-FIX1 only. Every exact ID
is retained in
`task13-fix1-covering-comparison.json:baselines.full.nodes_not_rerun`.
No corrected full, native/HPC/scientific, warning-clean or human acceptance claim.
The final Task19/full integration gate remains.

The new freeze/final audit preserves170 untouched reviewed Python hashes,
179 other tracked Python paths, exact outer/non-target AST, the original
662-line/38-case test prefix, both report/check prefixes,9 approved fixture
hashes,1124 pre-fix Task13 artifacts and7020 Fix1-start evidence entries
(explicit original-prefix/history accounting for appended reports/lead history).
All three comparison source-hash records equal the174-hash corrected freeze.
Fresh6-path Ruff relative to both HEAD/review is46 baseline/42 current/**0 new**;
both evidence helpers have zero diagnostics. No unrelated lint repair.

Only internal evidence/check appendices were updated; public documentation,
Sphinx/publication/GUI reruns and earlier lead acceptance remain lead-owned and
PRE-FIX1 unless refreshed or supported by an explicit unchanged-path proof.
No new public report/record/resource API, YAML key, scientific output contract,
dependency or scientific default. No source-data/environment/native change,
image/screenshot/plot, extra full/benchmark, subagent/reviewer, staging, commit
or push. Genuine corrected freeze was notified before lead checks and the
original reviewer's still-required scoped closure.

### Lead verification of the corrected freeze

Fresh lead full reports plus selected shared-target/bind-once/clearance safety:
158passed/157deselected/159warnings/14.90s. This includes all126report cases and
32unchanged safety cases. Same-text marks, independent name/binding causes,
selected effective dependencies, no-payload access and revoked clearance checked.

Raw XML lead corroboration retains all790pre-fix covered outcomes plus88new
passes:861passed/17failed; required456passed/17failed. Every covered complete
cause matches after runtime-only normalization against both baselines.1742full
nodes remain unrun after Fix1;2062/468/2full is PRE-FIX1 only.
Fresh174hashes/170other reviewed Python/179tracked paths, exact AST/prefixes,
1124prior artifacts/7020start evidence contents and9fixture hashes verified.
Fresh6path Ruff46→42/noNew; inherited diagnostics/warnings remain.

All3exact documented commands pass again, schema-only with inputs absent too.
Actual schema/name CLI failures retain leaf/rule/value/marks and both causes,
strict independent one-document JSON/nonzero checks, no source mutation/outputs.
All3unchanged scientific harnesses pass4/3/6source hashes with ordinary readers.
Strict65/publication/13unit pass; two HTML pages equal64, live text-only1020/320
bounds/code scrolling pass. Preview retained; no images or human acceptance.
Findings1–4 still require original-reviewer closure before commit.

## Review fix2 — remaining N1 only

The original reviewer closed findings2–4. Finding1 remains open solely for N1,
the missing-root path/repair construction; it is not double-counted. Reviewed
tree: `75a17b7951c04c6be8bbeac4d1d4d32b411a106a`.
Previous Fix1 safety158, examples/harnesses and lead CLI/docs checks above are
**PRE-FIX2**, not fresh Fix2 acceptance.

`_keys`' required-key branch confused the root display label `configuration`
with an authored YAML key. One normalized prefix now gives path `sources` and
repair `Provide sources.` while retaining nested paths such as
`region.center.longitude`. Conditions, messages, expected/present facts,
accepted controls, loader/marks and all other schema/closed-finding code stay
unchanged. One appended offline regression follows the root repair successfully
with an absent input and verifies the nested prefix; the original1230 lines/
126 cases/helpers/assertions remain verbatim.

### Exact bounded commands

Run only in the existing `frameit_env` Python3.13.18, with worktree imports and
the approved read-only fixture. Actual RED/GREEN/covering/required commands:

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py -k fix2_required_key_repair --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-red-root-repair.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-red-root-repair.txt 2>&1
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-green-reports.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-green-reports.txt 2>&1
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_wind_preflight.py --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-covering-final.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-covering-final.txt 2>&1
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_wind_preflight.py --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-required-final.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-required-final.txt 2>&1
```

Observed: RED1 failed/126 deselected (wrong root path),0.49s, exit1;
complete reports **127 passed**,3.69s, exit0; four-file covering **583 passed/
17 failed**,25.27s, exit1; exact required473, run once unfiltered, **456 passed/
17 failed**,22.24s, exit1. Every run retains XML/logs. The17 inherited legacy
producers still fail their integer-v3 prerequisite; no green-suite claim.

### Comparisons, preservation and corrected freeze

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-verify.py task13-fix2-freeze > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-freeze.txt 2>&1
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-verify.py task13-fix2-final-audit > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-final-audit.txt 2>&1
TMPDIR=/tmp/opencode conda run -n frameit_env python -m ruff check .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-verify.py --output-format=json > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-evidence-lint-final.json
git diff --check
```

These are exclusive evidence producers: use fresh Fix2 labels/destinations for
reproduction; never replace earlier artifacts. The freeze compares every
covered status and complete cause against Fix1 covering and PRE-FIX1 full:
599 and511 covering outcomes, respectively, unchanged; required473 unchanged
against both. All17 entire failure messages/traces match after only runtime
scratch/address/source-line normalization. One new Fix2 case passes separately;
the88 Fix1 report cases remain old reviewed cases, not new Fix2 cases.
`task13-fix2-freeze-node-ledger.md` names all failed nodes and links complete
raw before/after JSON pairs and unfiltered diffs under new trace-pair directories.

`task13-fix2-freeze.json` retains174 hashes and exhaustive per-run
`comparisons.<run>.baselines.<baseline>.nodes_not_rerun` inventories. It proves
172 other reviewed Python paths exact, configuration outside `_keys` byte-exact,
all AST outside the single missing-key branch exact, the original test/report/
check prefixes preserved,1376 prior Task13 artifacts/7268 initial evidence
entries retained with explicit original/prefix/history accounting, and9 fixture
hashes unchanged. Closed binding/dependency/scientific/record/resource code is
not rewritten. The genuine freeze was notified before lead/reviewer checks.

Fresh Ruff on all6 changed/new Task13 Python paths used the exact stdin command
`python -m ruff check --output-format=json --stdin-filename <path> -` over
HEAD/review/current texts: **46→42** HEAD, **42→42** reviewed, **0 new**.
Raw diagnostics and source hashes are in `task13-fix2-lint.json`; inherited lint
is not called clean. The new evidence helper has zero final diagnostics.

### Unrun checks and remaining gates

**279 Fix1-covered nodes and2021 historical full nodes were not rerun** on Fix2;
their exact IDs/status ages are in the freeze's covering inventories. No
eight-file integration, extra polar/resource/writer suite, scientific harness,
full or benchmark rerun for this one construction. The2062/468/2full is strictly
PRE-FIX1/PRE-FIX2; unchanged-code evidence does not replace final Task19/full.

Scientific/default/output and public report/record/resource contracts are
unchanged; no migration or new dependency. Only internal evidence appendices
changed. Public docs/STATE, CLI/docs/publication/GUI checks stay lead-owned.
No source-data/environment/native/package change, image/screenshot, subagent/
reviewer, staging/commit/push or Task14 dispatch. Original-reviewer N1/finding1
closure is still required; author verification is not closure.

### Lead Fix2 verification

Fresh lead127report cases pass4.21s. Actual schema-only/JSON CLI checks missing
root sources, a successful repair following its actual reported path, and
unchanged nested longitude guidance. Independent strict JSON/exit checks pass,
no input datasets/output directories.

Lead raw XML corroborates583passed/17failed covering and456passed/17failed
required, with all covered old outcomes/complete causes runtime-normalized exact
against both baselines. One new Fix2 case separate;279Fix1-covered/2021historical
full nodes remain unrun. No fresh broader-integration/harness/full claim.
Fresh174hash/172other Python/byte+AST/prefix/1376prior artifacts/7268start contents/
9fixture checks pass; actual fresh6path Ruff46→42/42→42/noNew.

Strict66/publication/13unit pass; both HTML pages equal65, public source unchanged.
Text-only live1020/320bounds/code-scroll pass; preview retained/no images/human
acceptance. Original-reviewer N1/finding1 closure remains pending; no commit.

## Independent closure

Original reviewer closes N1/original finding1; findings2–4 remain closed.
Spec✅/qualityApproved/0new Critical/Important/Minor; no open or parked Task13
finding. Reviewed final tree3125fe12d847fc0f55cab9bf5ad57f3ffd384806.
This is engineering task approval, not corrected-full, scientific/native/HPC or
human acceptance. All stated unrun/inherited gates remain.

Fresh lead final command:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task13-fix2-lead-reports.xml
```

Observed127passed/4.21s. Final source/tests/public docs/report contract remain
byte-exact to approved tree; only internal checklist/closure notes change after
review. Strict66/publication/13unit/text-only GUI and final CLI evidence above
remain current. Local commit precedes Task14; no push or merge.
