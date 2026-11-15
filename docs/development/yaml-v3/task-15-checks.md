# Task15 checks — scope blocker, not frozen

Base: `bde826b31957e67808f6219e175d3f960d7fd85e`.
This is an interim implementation handoff, not completed Task15 acceptance.
No files were staged or committed. The lead's public documentation changes are
separate and were not edited by this implementer.

## Necessary scope decisions

1. **Retained publication controls are ignored by the existing v3 writer.**
   `test_nonretired_publication_suppression_is_recorded_without_selecting_products[--no-export-cartesian-export_cart-False]`
   records `export_cart: false`, but an actual model-grid product is still
   published. `io/netcdf_export.py::export_outputs`'s v3 branch takes every common
   planned descriptor at line1128; its filtering by export_cart/export_polar only
   exists in the older branch at lines1249–1253. This is not a schema/default/
   scientific-selection problem and cannot be correctly repaired by changing
   authored products, making another plan, or globally suppressing unrelated track/
   polar products in the CLI.

   Proposed narrow ownership extension: filter only the local publication work
   list in `export_outputs` by its existing export_cart/export_polar arguments;
   return an empty actual inventory when no publications remain. Keep the common
   plan, scientific processing, ownership checks, callbacks, draining, encodings,
   records and all scientific quantities unchanged. Add mixed/track-retention and
   suppression checks before editing. **Not implemented; permission required.**

2. **Failure summaries have no current-attempt ownership snapshot.**
   The execution return value carries actual products on success. Exceptions do
   not expose whether ownership was acquired or which publications/pending facts
   belong to that attempt. Reading an existing output root after failure would
   misattribute earlier or concurrent records. The current CLI deliberately says
   “Inventory unavailable” and never performs that read.

   For a failure summary with actual retained publications, propose the smallest
   in-memory exception/status handoff from the existing ownership/finalization
   boundary, without a new record/schema, second bind, scan or event framework.
   This extends the permitted read-only run_state scope and needs a lead ruling
   before implementation. An explicit inventory-unavailable summary is the safe
   existing alternative, not a claim that no products were published.

No genuine freeze has been declared. Covering, required540 and the one unfiltered
full diagnostic have **not** run. The full must follow resolution of these
boundaries, passing focused checks and a genuine source/test/asset freeze.

## Implemented consumer interfaces

- `inspect <file>` uses Task13 collect_preflight(command="inspect") without binding
  native discovery. `validate <file>` and `config show <file> --effective` use the
  same shared collector/result/projection, not separate metadata planners.
- CLI loading reuses load_runtime's override/path-base/request capture and the
  existing `_apply_model_presets` projection. Metadata logging uses the existing
  stderr-only logging scope, including the YAML logging level.
- Plain `config show` strictly parses but does not default or mutate the authored
  mapping. Its `--json` is that mapping. The other JSON commands use report_version1,
  exactly seven envelope keys and five data sections. Schema/metadata failures
  stay nonzero with one JSON stdout document; logs stay on stderr.
- Common flags on validate/run/effective show:
  `--output-directory PATH`, `--cpus N`, exclusive `--overwrite`/`--no-overwrite`,
  `--log-level DEBUG|INFO|WARNING|ERROR`. Existing resolver precedence is
  CLI > YAML > defaults. CLI paths use launch directory; authored paths use YAML
  directory. Origins and original overrides are captured rather than reconstructed.
- Run consumes Task14 execute_simulation once. Its owning bind is observed once;
  no extra collect_preflight/inventory/bind is added for presentation. The selected
  plan is never serialized back into execution. Existing non-retired run flags
  remain, with requested options and explicit compression/institution origins
  recorded. The publication-suppression defect above remains RED.
- Explicit dry-run/resolved flags are rejected and absent from help.
  Directory-inspector model/format/pattern/FA-selection flags are not aliases:
  C9's same-YAML, source-scoped declarations replace that old command shape.
  Arbitrary source names and multiple readers make a global source-selection
  override scientifically ambiguous. The older direct-handler tests remain
  unchanged for Task16; their retired-call conflicts are not passes.
- `write_template(name, path, *, tracking=None, coupling=None, force=False)` is
  preserved. All eight assets now contain real v3 sources/regions/products.
  Model/named/composed/default/refusal/force cases, fields, levels, widths, Earth
  wind basis, source conventions, adaptation comments, atomic generation and
  source-symlink protection remain tested. Old Earth-centered wind output is
  expressed by explicit mass/Earth transforms, not a new numerical method.
- Capabilities is an offline report of actual model/format/method/dependency scope,
  not scientific sign-off. In particular UTrack's configured optional adapter is
  **not v3-executable**, FA tracking is gated, multifield_vortex remains
  experimental_native_grid_adaptation, and experimental conservative/patch
  comparisons are not advertised as public v3 polar selectors.

## Status rules

`frameit status <run-directory>`; no additional JSON option.

- Recorded completed/accepted-incomplete:0.
- Recorded running/failed/interrupted:1.
- Missing/unrecognized/unreadable required status:1.
- Argument syntax:argparse2.

`core.run_state.read_run_status(root)` reads fixed run-status.yaml and optional
run-provenance.yaml only. It does not open products, archives, original YAML,
locks or arbitrary paths from metadata, and does not scan directories.
Run-status version1 remains authoritative. Supplemental provenance is used only
when updated_at/state/products/pending match that checkpoint; mismatches or absent
optional facts are reported unavailable. Re-reading status detects a changed
checkpoint during reading. This is not a cross-file transaction or integrity/
liveness guarantee.

`core.reports.render_run_summary(facts, *, root, recorded=False)` provides matching
human presentation, separating actual publications from plans, showing available
fields/paths/warnings/exclusions/error/pending facts and ordinary xarray reader
guidance. Success summaries use the execution result and already-owned facts,
not another preflight or a potentially replaced root. Failed-run inventory is
explicitly unavailable pending the owning-fact ruling above.

## Editor asset and package check

`configuration_schema()` generates
`src/frameit/schemas/config-v3.schema.json`. V3_KEYS/V3_CHOICES/V3_LIMITS and
COMPRESSION_DEFAULTS are shared with the existing validator. This is a structural
editor asset, not an input-dependent field catalogue or a second scientific
validator. Existing schema diagnostic bodies/accepted controls/defaults are
unchanged after expansion of those constants (45 old functions checked by AST).
Metadata.extra permits arbitrary annotation values, including null; scientific
controls use omission, not null. Configuration3/report1/FA/record/package versions
remain distinct.

Exact generation command:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -c 'import json; from pathlib import Path; from frameit.core.configuration import configuration_schema; path = Path("src/frameit/schemas/config-v3.schema.json"); path.parent.mkdir(exist_ok=True); path.write_text(json.dumps(configuration_schema(), indent=2, ensure_ascii=False, allow_nan=False) + "\n"); print(path)'
```

Package-data change only: add `schemas/*.json`; no dependency/version change.

```bash
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-wheel-check.py
```

Result:exit0. Builds with existing build/setuptools/wheel using
`python -m build --wheel --no-isolation --outdir <fresh scratch>/dist`, against
a fresh scratch copy of current tracked packaging/source/assets plus the new
schema. No wheel is installed. ZIP bytes equal the generated asset; a fresh
`python -I -S` process reads the asset through importlib.resources directly from
the wheel. Wheel asset SHA256:
`16f4a599862c1f6012cf1ce899441f3416721fbda25d292d8edeab79a28e2715`.

`jsonschema` is absent in frameit_env. No installation, package repair or homemade
validation engine was attempted. Independent JSON Schema standards-conformance
validation remains unavailable; definition/asset/ZIP/resource checks do not
replace that gate or qualify every editor.

## TDD and observed verification

All commands use frameit_env Python3.13.18, worktree PYTHONPATH and
TMPDIR=/tmp/opencode. Logs/XML are new task-15-* artifacts under
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/`; previous evidence remains unchanged.

For the commands below, `W=.superpowers/sdd/CHECKLIST_FOR_AGENTS` is a portable
abbreviation for the literal output path used:

```bash
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py --junitxml=$W/task-15-cli-red.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py --junitxml=$W/task-15-cli-green-01.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py --junitxml=$W/task-15-cli-green-02.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_templates.py --junitxml=$W/task-15-templates-red.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_templates.py --junitxml=$W/task-15-templates-green-01.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k 'capabilities or editor_schema or annotation' --junitxml=$W/task-15-schema-red.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_templates.py --junitxml=$W/task-15-schema-green-01.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k 'status or failure or failed_run' --junitxml=$W/task-15-status-red.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py --junitxml=$W/task-15-status-green-01.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py::test_yaml_log_level_applies_to_report_logging --junitxml=$W/task-15-log-level-red.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k 'log_level or logs_go' --junitxml=$W/task-15-log-level-green.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k 'run_binds_once or nonretired or status_syntax' --junitxml=$W/task-15-options-red.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py src/frameit/testing/numerical/test_templates.py --junitxml=$W/task-15-focused.xml
```

| Artifact | Observed result |
|---|---|
| cli-red |20failed/5passed:missing flags/same-file/authored/summary behavior|
| cli-green-01 |24passed/1failed:pytest intercepted logging, not actual stderr loss|
| cli-green-02 |25passed/7existing warnings|
| templates-red |46failed/28passed:v2 assets rejected|
| templates-green-01 |74passed|
| schema-red |2failed/3passed:missing capabilities/generator|
| schema-green-01 |429passed/1failed:capability limitation wording assertion;326schema cases pass|
| status-red |12failed/12passed:missing status/current-failure presentation|
| status-green-01 |42passed/8existing warnings|
| log-level-red |1failed:YAML verbosity not applied to metadata logs|
| log-level-green |2passed/41deselected/2existing warnings|
| options-red |2failed/3passed/42deselected:explicit option origins plus writer-suppression defect|
| focused |120passed/1failed/11existing warnings; explicit option origins now pass, writer defect remains|

The remaining failed focused node is named in the scope decision above.
Its complete original trace and actual published descriptor are retained in
task-15-focused.xml/.log and task-15-options-red.xml/.log.
No expected scientific assertion was changed to hide it.

Installation-identity check:

```bash
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_hpc_execution.py -k 'test_cli_keeps_checkout_under_local_in_parent_and_spawn or test_cli_info_reports_selected_installation' --junitxml=$W/task-15-identity.xml
```

Result:5passed/23deselected/1existing warning. The sanitizer already correctly
excludes actual user-site packages, not all of ~/.local; its AST and info's
installation diagnostics remain exact.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-proof.py scope-blocked
git diff --check
```

Both exit0. Proof:355 tracked paths outside explicit worker/lead ownership exact;
45old configuration functions AST-exact after shared literal expansion; old
run-state/report definitions exact; original template function/scenario IDs and
model/format/width/comment expectations retained; all other tests/producers/
scientific code unchanged. 8,704 immutable prior evidence entries match; original
mutable ledger/preview bytes and explicit lead histories are retained. All9signed
payloads and all12fixture-entry hashes match. Actual-path HEAD Ruff:42prior,
29current, **zero new** diagnostics; this is not clean lint. Earlier failed proof
attempts are preserved and documented by task-15-proof-precheck*.log.

## Remaining checks and effects

After scope decisions:finish focused TDD, run covering modules, then the exact
required command:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_templates.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_hpc_execution.py
```

Save logs/XML in those final executions, notify genuine freeze, then run exactly
one unfiltered full diagnostic with the approved fixture. Retain the existing two
PNG script/file-safety smoke tests inside that suite only; no images/screenshots/
standalone plot runs are authorized. Compare every2670mixed-age prior node plus
new nodes, preserving complete failed/error causes and contract evidence for
each recovered/changed node. No Task15 full/node-cause comparison exists yet.
The prior540 inventory and mixed-age2670 are not Task15 results.

Scientific impact:no new method, default, read policy, resource choice, physical
quantity, units, sampling, wind basis, mask, clock, precision or scientific
qualification. Compatibility:intentional v3 public CLI/template/editor/report
surface changes; no migration layer, output schema or dependency change. Public
docs/build/GUI acceptance remain lead-owned and unclaimed. Producer conversion16,
tutorials17, HPC18, native/warnings/full integration19, docs20/human21 and
Task09Minor3 retain their gates. No source-data/environment/native changes,
downloads, warning suppression, benchmark campaign, subagents/reviewers, image
viewing, staging, commit or push.

## B1/B2 authorized corrections and pre-freeze verification

This appended section supersedes the two earlier blockers, while preserving the
original report/evidence. Lead rulings are
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-boundary-ruling.md`.

### Exact boundary deltas

- B1:`io.netcdf_export.export_outputs` now filters **only its local v3
  publication list** by the existing export_cart/export_polar arguments.
  Requested track is retained; an empty list returns an empty actual inventory
  before dataset/track dimension access or pool creation. The common plan,
  scientific work, paths, encodings, callbacks, retention/deduplication/draining
  and legacy branch are unchanged. A byte proof permits only this five-line
  local substitution.
- B2:`execution._execute_owned_simulation` remembers status **only after the
  actual owned_run context yields**. After that context unwinds, an escaping
  exception may carry private `_frameit_failure = {"root": ..., "facts": ...}`.
  Facts copy only existing completed-product descriptors, pending/tracking/
  timestamps, warning/exclusion facts and the current exception. No plan, config,
  dataset, graph, future or disk-record reference is attached. Public signatures,
  result/record schemas, owned_run/checkpoint_run bodies, preflight/binding/reads,
  resources and Task14 progress/A1 remain unchanged.
- The failure facts' `state` describes the current failed/interrupted invocation;
  `observed_owner_state` describes its last in-memory owner state, including
  possible completed state before final-record failure. The text explicitly says
  final record persistence is **not verified**. Product completion is not labelled
  checkpoint persistence. A real publication/checkpoint failure test proves an
  ordinary-reader product can exist while disk status still records no product.
- CLI consumes only that handoff, never reads a root to infer ownership, and
  retains unavailable-inventory fallback before yield. Optional attachment/
  rendering failures cannot replace the original exception.
- Covering exposed one additional CLI regression:the new scoped metadata logger
  changed `INFO:` to column-formatted `INFO |`, breaking an existing Task13 real
  subprocess assertion. The existing test was kept. Metadata-owned stderr
  handlers now retain the previous formatter while honoring YAML/CLI verbosity.
  No shared logging/progress implementation or lifetime changed.

The only earlier Task15 assertion updated is the authorized owned-failure
presentation assertion. Its request/override/safety checks remain. All other
pre-boundary test/helper ASTs are exact; new B1/B2 tests were appended.

### Boundary TDD

All commands retain `PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode` and
`conda run -n frameit_env python -m pytest -q`. Literal output paths are under
`W=.superpowers/sdd/CHECKLIST_FOR_AGENTS`; logs use the same stem as XML.

```bash
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k 'publication_filter or nonretired_publication' --junitxml=$W/task-15-boundary-B1-red.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k 'publication_filter or nonretired_publication' --junitxml=$W/task-15-boundary-B1-red-02.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k 'publication_filter or nonretired_publication' --junitxml=$W/task-15-boundary-B1-green.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k 'publication_filter or nonretired_publication' --junitxml=$W/task-15-boundary-B1-green-02.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k 'owned_failure or final_record_failure or real_unowned or summary_failure' --junitxml=$W/task-15-boundary-B2-red.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k 'owned_failure or final_record_failure or real_unowned or summary_failure' --junitxml=$W/task-15-boundary-B2-green.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q 'src/frameit/testing/numerical/test_v3_reports.py::test_actual_validate_cli_emits_one_json_document_and_nonzero_errors' src/frameit/testing/numerical/test_v3_cli.py -k 'actual_validate_cli or logs_go or log_level' --junitxml=$W/task-15-boundary-log-format-green.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py::test_failed_publication_checkpoint_does_not_turn_memory_facts_into_persistence --junitxml=$W/task-15-boundary-persistence-red.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py src/frameit/testing/numerical/test_templates.py --junitxml=$W/task-15-boundary-focused-qualified.xml
```

Observed:

- Initial B1 RED:13failed/2passed;10new polar fixture cases used an inappropriately
  fine 1km radial step. Correcting only the instructional request to2km exposes
  the actual suppression defect:11failed/4passed. No scientific rule was relaxed.
- Initial B1 GREEN:13passed/2failed; two native-only fixtures still selected a
  center, so an internal track legitimately existed. Removing region only in
  those native-only fixtures preserves the `runner.track is None` assertion.
  Corrected B1 GREEN:15passed/44deselected/16existing warnings.
- B2 RED:11failed/2passed; one initial-record test wrongly assumed authorized
  overwrite could not update status before yield. Its assertion now follows the
  unchanged Task12 writer policy, while inventory-unavailable/no-stale-facts
  assertions remain. B2 GREEN:13passed/58deselected/38existing warnings.
- Existing metadata_ok logger-format RED is retained in the first covering
  XML/log; corrected real-CLI/log-level checks:8passed/69deselected/2warnings.
- The publication/checkpoint wording RED is1failed. Final focused checks:
  **146passed**,60existing warnings,20.62s. These include all74starter cases and
  all72new CLI cases, actual NetCDF/Zarr mixed/suppressed/track products, callback/
  status/provenance agreement, partial/interrupted/initial/final-record failures,
  primary-exception preservation and fresh ordinary readers/source hashes.

### Covering and required history

The covering command uses these13modules, with the approved fixture:

```bash
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py src/frameit/testing/numerical/test_templates.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_v3_reports.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_progress.py src/frameit/testing/numerical/test_v3_run_state.py src/frameit/testing/numerical/test_v3_resources.py src/frameit/testing/numerical/test_v3_outputs.py src/frameit/testing/numerical/test_output_layout.py src/frameit/testing/numerical/test_zarr_export.py --junitxml=$W/task-15-boundary-covering-qualified.xml
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_templates.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_hpc_execution.py --junitxml=$W/task-15-boundary-required-qualified.xml
```

The exact required540module selection has now run, not merely been inferred.
The final qualified required run is530passed/9failed/1error,4existing warnings,
27.77s. Its earlier `required` and `required-final` runs have the same outcomes
and separate immutable XML/logs. The qualified covering is running at this
append; no result is inferred until its command completes.

First covering:1010passed/21failed/1error,1136warnings. After the metadata
formatter correction:1011passed/20failed/1error,1136warnings,215.03s
(`task-15-boundary-covering-final.xml`), before the final one-sentence persistence
clarification/new regression test. Those older results remain explicitly older.
No extra run was performed merely to acquire XML.

Per-node comparisons preserve all540required prior nodes/46starter recoveries,
and961covered prior nodes plus71then-new cases/47changed old outcomes.
All56required and67covering failure-or-recovery pairs retain complete raw
before/after messages/traces and exception lines. The three changed-cause pairs
are individually reviewed in `task-15-boundary-covered-cause-review.json`:
the old dry-run caller now fails argparse2 instead of integer-v3 validation;
two old directory-inspector callers likewise fail their removed source-selection
flags instead of constructing rejected v2.1 controls. The additional old
planning-handler pass→failure is the explicit C9 dry-run/resolved retirement,
with the new rejection tests as per-node contract evidence. No old scientific,
HPC, Zarr, schema or source-safety assertion was weakened.

### Source and evidence safeguards before freeze

`task-15-boundary-proof.py` extends the original proof with only explicit B1/B2
production claims, the existing CLI logger-formatter repair and the new summary
wording. It verifies the original176Python and111Task15-artifact baseline, exact
non-target source/AST/old-test bodies, source/fixture hashes, original report/check
prefixes and actual-path HEAD Ruff. The lead-owned `fa_environment.rst` and
append-only lead doc notes are explicit exceptions, not wildcard exclusions.
The old doc-notes prefix was recovered byte-exactly and independently SHA-checked
against the saved manifest:1831bytes,
`dfaa588d72c736d788868405f83e7077f74a236ead71096e6655572c089e4277`.
Original and failed proof attempts remain intact.

Before the persistence wording correction, the proof passed with352out-of-scope
tracked paths exact,8704immutable prior artifacts, all9payload/all12fixture hashes,
45expanded old configuration functions and original ownership/report/processing/
progress/callback/drain bodies exact. Actual-path HEAD Ruff:49prior→36current,
zero new. A fresh freeze proof is still required for the last presentation word
and test; this older proof is not labelled final-source evidence.

All13complete help pages were captured/reviewed in
`task-15-boundary-help-review.json`, including the exact common flags and removal
of retired/source-selection references. Public docs/build/GUI acceptance remain
lead-owned. The generated schema/package-data/asset bytes and previous wheel ZIP/
isolated-resource evidence are unchanged; independent JSON Schema conformance
remains unavailable. No full run or freeze is claimed by this interim append.

## Genuine freeze and qualified scoped results

The source/test/asset freeze is genuine and was declared at
`2026-11-15T17:34:51.550947+00:00`, before starting the full diagnostic.
`task-15-boundary-freeze.json` records188source/test/asset hashes and all352
outside-scope tracked hashes. No code, test or asset edits are authorized afterward.
Lead-owned documentation and append-only evidence/reports are separate.

Fresh freeze commands:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-boundary-proof.py freeze
PYTHONPATH="$PWD/src" conda run -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-boundary-compare.py covering-qualified
PYTHONPATH="$PWD/src" conda run -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-boundary-compare.py required-qualified
git diff --check
```

All exit0. Qualified covering completed: **1012passed/20failed/1error**,
1137existing warnings,214.26s,1033nodes=961prior+72new. Qualified required:
**530passed/9failed/1error**,4existing warnings,27.77s,all540prior IDs.
Final focused:146passed. Every72new CLI case and74starter case passes.
The writer callers include v3_outputs/output_layout/zarr_export and the unchanged
Task14 progress/A1/run-state/resource cases.

The20covering failures/1error are retained, not counted as passes. All67covered
and56required failure-or-recovery pairs retain complete raw causes. Qualified
flagged pairs have exactly the same complete exception lines as the individually
reviewed dry-run/directory-inspection causes; see
`task-15-boundary-qualified-cause-review.json`.46starter recoveries and the one
explicit retired-planning-handler pass→failure have individual contract/test
evidence in both per-node comparisons. No unexplained covered cause change remains.

The freeze proof includes the last persistence-wording test/change, all original
176Python/111Task15-artifact baseline checks,45expanded old configuration bodies,
unchanged ownership/checkpoint/report/scientific/progress/callback/drain code and
old test/helper preservation. All9signed payloads/all12fixture entries match.
HEAD Ruff49prior→36current,zero new; not clean lint. Original report/check
prefixes and original mutable lead histories remain exact.

The **single unfiltered full diagnostic** was then launched with:

```bash
PYTHONPATH="$PWD/src" TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-boundary-full.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-boundary-full.log 2>&1
```

No `-k`, marker filter, skip, maxfail or warning suppression is added.
The two existing PNG script/file-safety smoke tests remain inside that suite
only; no images are opened. Its result and2670prior/new-node comparison are still
pending at this append. Lead command/docs/GUI checks may now use the frozen tree.

## Final author handover — frozen full diagnostic complete

This is the latest state; earlier blocked/pending sections are preserved history.
No source, test or asset changed after the genuine freeze.

The **one** unfiltered full command above completed with exit1:
**2316passed/424failed/2errors**,6669warnings,4subtests passed,608.79s.
All2742nodes are accounted for:all2670mixed-age prior nodes plus72new CLI cases.
No old node is unrun; every72new case passes. This is a current Task15 full
diagnostic, not a green suite, scientific/native qualification, or a retroactive
corrected Task14 full.

Exact comparison and preservation commands:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-boundary-compare.py full
PYTHONPATH="$PWD/src" conda run -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-boundary-proof.py post-full
```

Both exit0. The full comparison/ledger stores every2742outcome, original prior
freshness, all72new nodes and all48changed old statuses. It retains472complete
before/after failure-or-recovery pairs:470prior failed/error nodes plus2formerly
passed nodes. A further independent raw-log extraction retains the complete
stdout/stderr/trace section for every failed/error side:470before sections and
426after sections, each uniquely matched to its node name. Passed sides are
explicitly absent (46recoveries and2old passes), not missing error evidence.

Primary artifacts under `.superpowers/sdd/CHECKLIST_FOR_AGENTS/`:

- `task-15-boundary-full.xml` and `.log`:the untouched actual execution.
- `task-15-boundary-full-comparison.json` and `-node-ledger.md`:all outcomes,
  changed statuses, prior ages and raw-pair references.
- `task-15-boundary-full-pairs/`:472raw before/after messages/traces, complete
  exception-line sequences and diffs.
- `task-15-boundary-full-complete-captures.json` and
  `task-15-boundary-full-complete-captures/`:complete per-node terminal sections,
  including captured output omitted from JUnit's failure body.
- `task-15-boundary-full-reviewed-causes.json` and
  `task-15-boundary-full-reviewed-node-ledger.md`:every failure/recovery cause,
  all22individually flagged reviews and per-node contract evidence.
- `task-15-boundary-post-full-proof.json`/`-delta.json`/`-proof.log`:
  fresh source/AST/old-test/producer/evidence/fixture/HEAD-Ruff proof.

### Every changed status and cause

- **46failed→passed:**the existing starter-generation cases. Each node has its
  own C9/test evidence and original failure in the comparison. All74starter
  cases retain scientific fields/levels/widths/basis/comments and safety checks.
- **2passed→failed:**the unchanged Task13 planning-handler test calls the
  explicitly retired dry-run/resolved options; the unchanged FA metadata/privacy
  CLI test calls the retired directory/model/format/pattern/FA-selector shape.
  Both stop at argparse2. The latter's native-helper privacy/metadata assertions
  are **not** described as executed or qualified by that failing old caller.
  Task16 must express that scenario with the same-file v3 source controls.
  FA worker/read/encoding code is unchanged; no compatibility alias was invented.
- **404retained complete causes:**360whole messages/traces match after runtime
  path/address/attempt/line normalization;43retain exactly the complete exception
  sequences and call-site paths with only pytest context/repr differences; one
  Slurm case has an additional truncated `pytest-227`→`pytest-267` scratch-ID
  difference. Its **whole** normalized message and trace were separately checked
  equal. Original raw bytes remain.
- **20old failed-node cause changes:**four old dry-run callers now fail the
  retired flag rather than earlier invalid-v2 generation/loading; two old model
  starter tests now reach their obsolete `schema_version == "2.1"` assertion;
  nine coupled generated-document consumers index old `raw.input.sources`;
  one quick-start test indexes the old input block; one GRIB-starter test asks
  for an unrelated, unselected FA backend; two old directory-inspector callers
  fail argument parsing; one Meso-NH test inserts an invalid legacy root input
  into valid v3 and then expects a scientific diagnostic in caplog.

These20causes are not grouped only by counts:every concrete node, before/after
complete exception lines, helper/call-site root, capture path and disposition is
in the reviewed JSON/Markdown. In particular the Meso-NH captured stdout retains
`Error at input: Unknown key configuration.input`, its YAML line1location,
accepted keys, valid repair and explicitly blocked plan. It did not reach its
missing-height/LTPZH check. The nine coupled cases likewise did not reach the
requested height/time/wind-basis scientific assertions; no such assertion is
waived or called passed. Shared producer/helper/scientific test conversion remains
Task16, and all their source/AST/formulas remain intact.

Both existing PNG smoke nodes ran **inside this full only** and passed:
`docs/test_documentation_plots.py::test_batsirai_plot_cli_reads_time_dependent_cartesian_coordinates`
and
`docs/test_documentation_plots.py::test_first_run_plot_cli_reads_only_the_selected_time`.
No image was opened or visually accepted. Four existing subtests also pass.

### Final effects, limits and remaining ownership

Changed:the approved CLI/template/capabilities/editor/status consumer surface,
the bounded B1publication filter and B2private failure facts. Scientific impact:
no new numerical method, scientific default, field interpretation/unit/basis,
sampling/mask/clock/grid/precision policy or scientific approval. Output encodings,
schemas, callbacks/draining and ownership/checkpoint writing remain unchanged.
Compatibility:intentional v3 CLI/starter/editor changes and actual suppression
of explicitly disabled publications; no public execution/result/record API,
migration alias, new dependency or installation change.

The188frozen source/test/asset hashes remain the acceptance reference; all352
outside-scope tracked paths, original176Python/111Task15-artifact baseline,
old report/check prefixes, explicit lead histories,8704immutable earlier evidence
entries,9signed payloads and all12fixture entries remain verified. Actual-path
HEAD Ruff49→36/noNew is not clean lint. No source-data/environment/native changes,
downloads, warning suppression, extra full or benchmark, subagents/reviewers,
staging/commit/push or independent human/scientific sign-off occurred.

Unresolved gates are explicit:the full still has424failures/2errors with their
actual causes retained; broad producer conversion16, tutorials17, HPC18,
native/warnings/integrated acceptance19, docs20/human21 and Task09Minor3 remain.
Independent JSON Schema standards-conformance validation is unavailable. The
previous asset-definition/ZIP/isolated-resource checks remain valid for the
unchanged schema/package-data, not proof of every editor or scientific request.
Lead actual-command/docs/GUI verification and independent review/commits are
lead-owned and are not claimed here. No additional boundary or source fix is
requested by this author handover.

## Lead checks before independent review

Fresh lead CLI/template command, with the same modules as focused verification
and `--tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-lead-focused.xml`,
passes146cases/60warnings/21.58s in frameit_env3.13. Twenty-eight actual command
checks include all nine first-run lines. An ordinary reader verifies original
5×5values/mask/zero/units/times/CF geography; source/request bytes are unchanged.
Actual suppression and owner-attested partial-failure summaries are checked,
including persistence uncertainty and status without the original input.

Lead independently corroborates the one full2316/424/2:all2670prior+72newpasses,
472raw pairs and470before/426after complete captured original-log sections.
Every recovery/new failure/changed cause is classified; no scientific/privacy
assertion is waived or called passed when its caller stopped earlier.
Fresh188freeze/352outside/8704immutable/45old-config-AST/9payload12fixture and
no-new-Ruff proofs pass. Full remains red; independent schema conformance absent.

Strict Sphinx69/publication/13unit and all12changed published pages in live
text-only1020/320checks pass. Canonical69preview remains available; no screenshot/
image/pixel/human claim. Existing wheel checks cover the unchanged schema asset,
not final-code installed-wheel execution. Whole-Task15 spec/quality review and
local commit still remain; no Task16 implementation, push or merge.

## Task15 fix1 — two review corrections, awaiting scoped reviewer closure

This appended section is current fix1 author evidence, not reviewer closure.
The earlier 188-hash freeze, 146-focused/1033-covering/540-required/full results,
lead command/docs checks and old wheel evidence above are **PRE-fix1 only**.
In particular, 2316passed/424failed/2errors is not a full result for corrected
source, and 530passed/9failed/1error is not a corrected required540 result.
The lead's fix1 packet explicitly forbids repeating those suites.

Read the fix1 handoff first and all208review lines. The preserved baseline is
`task-15-fix1-baseline/manifest.json`:188old frozen hashes,34reviewed path hashes
for tree `1c41a69242cb9c0a197c4d03b8cc1f31c1fb5128`,2365Task15 artifacts,
14exact source/test/asset/report/history copies and the774-line old CLI-test
prefix. HEAD remains `bde826b31957e67808f6219e175d3f960d7fd85e`.

### Roots and exact delta

1. `configuration_schema`'s scalar-default branch fell through from bool/int to
   text for float defaults. Both valid pressure-wind widths therefore referenced
   string-only text despite their numeric defaults and existing numeric runtime
   validation. The only generator edit adds the existing `positive` float case,
   as already used for nested defaults. Default widths remain200/100km, runtime
   validation remains exact and strings remain rejected. The regenerated asset
   changes **only** these two definitions to number/exclusiveMinimum0 with their
   original numeric defaults.
2. The authored JSON branch of the actual handler `cli._cmd_config` passed
   parsed YAML directly to `json.dumps`. Valid date/timestamp/set/binary
   annotations raised TypeError; allowed non-finite annotations failed strict
   JSON encoding. The only CLI edit locally imports and applies the existing
   `reports._metadata_view` before the same strict dump. Its body, authored YAML,
   effective reports, errors, parser and all other CLI definitions are unchanged.
   No defaulting, envelope, request rewrite, preflight, binding or dataset access
   was added. `_cmd_config_show` in the packet denotes this authored-show path,
   not a new or renamed API.

The existing projection recursively copies mappings/sequences: dates and
timestamps use `isoformat()` strings (UTC becomes `+00:00`, without a new time
conversion); sets become arrays with no ordering guarantee; bytes become
`{"hex": "<lowercase hex>"}`; NaN/infinities become
`{"nonfinite": "nan"|"inf"|"-inf"}`. Nulls, finite values and Unicode remain.
It stringifies mapping keys; the unchanged strict YAML loader already requires
string keys. This is a representation convention, not new accepted controls.
Lead owns the canonical paragraph, STATE/contract, documentation and preview.

Only `configuration.py`, `cli.py`, the generated schema asset and appended
`test_v3_cli.py` regressions changed in this fix. The old774-line test prefix is
byte-exact. Shared reports/projections, runtime validation/defaults/science,
Task14/A1 progress, B1/B2 publication/ownership, templates, package metadata,
all other tests and source data remain exact.

### TDD commands and observed results

Each finding was reproduced in appended regressions before its one narrow fix.
These are the actual commands; XML and complete logs use matching stems.

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py::test_editor_pressure_wind_widths_match_runtime_positive_numbers --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-widths-red.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-widths-red.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py::test_editor_pressure_wind_widths_match_runtime_positive_numbers --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-widths-green.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-widths-green.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py::test_authored_json_projects_yaml_annotations_without_defaults_or_mutation --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-authored-json-red.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-authored-json-red.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py::test_authored_json_projects_yaml_annotations_without_defaults_or_mutation --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-authored-json-green.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-authored-json-green.log 2>&1
```

Widths: **2failed** RED,0.53s,exit1, after runtime accepted both defaults and
integer/float overrides but rejected their quoted strings. Failure was exactly
the emitted text reference instead of a positive-number schema.
GREEN: **2passed**,0.53s,exit0, checking both generator and actual asset.
Authored JSON: **7failed** RED,0.56s,exit1 (date/datetime/set/bytes TypeErrors and
the three strict non-finite errors). GREEN: **7passed**,0.49s,exit0.
All nine are new nodes, not rewritten earlier scenarios. The JSON cases use the
real strict reader and CLI, independent literal expectations, nested null/Unicode,
dataset/collector guards, unchanged loaded objects and exact request/source bytes.
Plain authored YAML still retains its parsed YAML values. No output/default
directory or effective-report envelope appears.

### The one authorized current covering and complete cause comparison

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py src/frameit/testing/numerical/test_templates.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_v3_reports.py --tb=long --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-covering.xml > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-covering.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-compare.py > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-covering-comparison.log 2>&1
```

The four **complete** modules ran once: **607passed/1failed**,60existing warnings,
27.38s,exit1. Module counts:CLI81passed;templates74passed;configuration_v3
326passed;v3_reports126passed/1failed. No skip/filter/maxfail/warning suppression.
The comparison exits0:all599covered old outcomes are unchanged (598pass/1fail);
all9new regression nodes pass. No new or changed old failure cause.

The sole retained failure is
`src/frameit/testing/numerical/test_v3_reports.py::test_existing_planning_handlers_share_one_preflight_and_projection`.
Its unchanged old caller invokes retired `--dry-run`; argparse exits2 before
the subsequent run/effective assertions. The whole normalized terminal section,
complete `SystemExit: 2`, stderr and raw JUnit message/trace match PRE-fix1,
apart from scratch paths/addresses. The test was not converted or weakened.
`task-15-fix1-covering-pairs/task-15-fix1-2b83a350fbe11a8f0879.json` and its
`.diff` preserve both complete causes/captures;
`task-15-fix1-covered-cause-review.json` records the concrete root, not a debt label.

`task-15-fix1-covering-comparison.json` and `-node-ledger.md` enumerate every
covered old/new node and **every2143unrun** PRE-fix1 full ID, including its old
status:1718passed/423failed/2errors. Thus599covered+2143unrun=2742old full IDs.
Those2143statuses are historical only, not corrected-code results. Neither the
old full nor required540/1033covering/harness/benchmark was rerun.

### Corrected asset, fresh wheel and preservation

Generation used `frameit.core.configuration.configuration_schema()` and wrote
only `src/frameit/schemas/config-v3.schema.json` as
`json.dumps(configuration_schema(), indent=2, ensure_ascii=False) + "\n"` in
frameit_env3.13 with worktree PYTHONPATH and bytecode disabled.
`task-15-fix1-asset-generation.json` retains old/new hashes and serialization.
Old asset SHA256:`16f4a599862c1f6012cf1ce899441f3416721fbda25d292d8edeab79a28e2715`;
**new:**`6b9f8b00f094eeb15f9c6fe43eede3940dd71da8cbf7cabb193a03e412fbac36`.
Exact parsed delta and generator/asset byte equality are independently asserted
by the fix1 proof; this is not a general JSON Schema validation engine.

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-wheel-check.py > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-wheel-check.log 2>&1
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-proof.py precover-02 > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-precover-02-proof.log 2>&1
git diff --check
```

All exit0. One wheel was rebuilt from a fresh source copy under
`/tmp/opencode/task-15-fix1-wheel-sxernmnr`, using the existing
`python -m build --wheel --no-isolation --outdir <scratch>/dist`.
Wheel:`frameit-2.0.0rc2+hotfix1-py3-none-any.whl`;
SHA256:`1f4f12c68ff2a12db9fba9269c919d23c7f93221d839b0b0e2da9b73c3ffdd8a`.
Ordinary ZIP bytes and an isolated `python -I -S` importlib.resources read both
match the **new** asset/hash and both corrected numeric definitions.
`task-15-fix1-wheel-result.json`, `-wheel-build.log` and `-wheel-resource.log`
retain the exact paths/commands/results. No wheel was installed; no installed-
wheel final-code execution or independent standards-conformance claim is made.
The old wheel/result is immutable but no longer qualifies the corrected asset.
The two build warnings only report disabled byte-compilation; no warnings were
suppressed and no package/environment/native repair was attempted.

Precover-02 verifies184non-target frozen paths, exact old AST/whole-file bytes
after only the two specific substitutions, all old774test lines/helper ASTs,
2365Task15+8704earlier evidence with exact copied mutable prefixes,352outside
paths,9signed payloads/12fixture entries and all34reviewed path hashes/copies.
Reports._metadata_view and all runtime/Task14/B1/B2/template/package bodies are
byte-exact. Actual-path Ruff:HEAD49→36,review-tree36→36,zero added findings
against either; this is not clean lint. The first precover proof stopped only
on four E501 lines in the **new proof helper**; wrapping those strings/dict
entries corrected it. That failed proof/log remains, with no production/test fix
or repeated suite caused by the helper formatting.

Scientific impact:none. Compatibility:editor now accepts the already-valid
numeric widths; authored JSON now projects valid YAML annotations by the existing
convention. No API/default/grammar/output-record/encoding/dependency change.
Corrected source/test/asset freeze follows a fresh final preservation proof;
the old freeze is not relabelled. Both Important findings remain open until
scoped reviewer closure. Lead owns documentation/GUI verification and commits.
No staging/commit/push, subagents/reviewers, images/plots or extra harness/full.
Independent JSON Schema conformance remains unavailable. Integration outside
these unchanged lanes is untested on corrected code; scoped review and final
Task19/full retain that risk and gate. No historical failure or unreached
scientific/privacy assertion is waived.

### Corrected freeze declared

Fresh `task-15-fix1-proof.py freeze` exited0 after the covering/build and report
append; `git diff --check` also exited0. Actual command:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-proof.py freeze > .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-15-fix1-freeze-proof.log 2>&1
```

The **genuine corrected freeze** is `2026-11-15T18:52:10.525077+00:00`;
`task-15-fix1-freeze.json` records188corrected hashes, the exact four authorized
deltas/184unchanged paths,352outside hashes, existing fix1 evidence hashes and
the new asset/wheel reference. Corrected hashes equal the precover-02 snapshot,
so the sole covering and wheel tested these exact bytes. Both HEAD/review-tree
Ruff comparisons remain noNew (49→36/36→36), not clean lint.
No source/test/asset edit after this declaration; reports/new verification
evidence and explicitly lead-owned prose remain separate. Lead may now run
documented-command/docs/GUI checks and arrange scoped re-review. Both Important
findings remain open until that reviewer closes them; no author acceptance,
stage/commit/push or rerun of the PRE-fix1 full/required is claimed.

### Lead checks before scoped review

Fresh complete CLI/template check155passed/60warnings/21.27s. Raw XML
corroborates607passed/1oldfailed:599old statuses and complete argparse/stderr/
terminal cause unchanged,9newpasses/all9RED→GREEN IDs verified.
2143old full IDs remain unrun corrected; full2316/424/2andrequired530/9/1are
PRE-fix1 only. No new full/required/harness run.

Fresh184other hashes/774line prefix/two-production-substitution/schema-delta/
352outside/2365+8704evidence/9payload12fixture/no-new-Ruff proof passes.
All188corrected hashes match. Actual authored JSON/YAML/offline commands
confirm7annotation conversions without mutation/defaults/envelope.
New wheel ZIP/isolated-resource matches the corrected asset; no install or
independent standards-conformance validation.

Strict70/publication/13unit/live text-only1020/320configuration checks pass.
Other11affected HTML pages equal checked69; canonical70retained. No image/
pixel/human acceptance. Both findings still await scoped reviewer closure.

### Independent closure

Original whole-Task15 review plus scoped fix1re-review approve specification
and quality. Both Important findings addressed;0open/parked/new findings.
Final reviewed treec3765d530bc86f69f6a75de8491dc5ad7b274827; source/tests/assets/
public prose remain byte-exact. Only internal completion records now change.
Latest155lead passes/607pass1oldfail/strict70/publication13unit remain current;
2143full IDs unrun corrected, full2316/424/2andrequired530/9/1PRE-fix1 only.
Conformance/installed-wheel/native/HPC/human and named later gates remain.
Local commit follows checked staging; no push or merge.
