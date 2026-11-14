# Task07 source-interpretation evidence

Base: `edaf6028a581f9031e88047da4239d583e55ca6e`.
Current status: **Independently approved after fix round1**. Three Important
findings are closed with no new findings; Minor4 retains its later owner.
The initial NEEDS_CONTEXT, Ruling1 and pending-review snapshots below are
historical; final closure and lead verification are appended at the end.

The pending bounded request is permission to update only the interpretation
branch of:

`src/frameit/testing/numerical/test_v3_regions.py::test_tracker_binding_does_not_clear_unrelated_pending_operations[interpretation]`

That Task06 assertion expects interpretation to remain pending. Its fixture has
no selected eligible SEA fields, and actual tracker inputs resolve; C4 now needs
no mask support there. The transform/derived/polar branches must remain blocked.
The worker has not edited this out-of-claim file. This is a reported failed node,
not an exemption or a passing-full-suite claim.

## Checked behavior and interfaces

- Source declarations describe stored values. Genuine gaps are completed;
  contradictory known units, identity, categories and temporal statistics fail
  without payload reads. No compatible-unit numeric conversion is requested.
- Bound product/dependency descriptors carry
  `field_metadata: {attributes, origins}`. Source preflight/binding records the
  origins in `metadata_origins.field_metadata`; original records stay intact.
- SEA interpretation selects only admitted requested quantities and FRAC_SEA
  support. Preflight checks metadata without reading masks. Execution checks
  selected physical support and preserves fractional values, real zeroes,
  specific sentinels and unrelated legitimate999 values. Ordinary access stays raw.
  Exported, ancillary and internal FRAC_SEA roles remain consistent.
- FA binding uses source-local raw descriptors and the selected leaf's metadata
  checks. Grouped reads consume the complete genuine binding and owning source,
  not a bare record list or artificial bound status. Missing verified hybrid
  evidence stays pending; native scaling/masks remain explicit decode-time checks.
- Native FA labels/indices/coefficients, sampling and producer/geometry gates stay
  intact. One native component needs no companion or basis declaration.
  The real projected regional path retains native CRS/axes/zone lookup facts.
- Real h5netcdf/ecCodes/FA transactions are instrumented. Fresh ordinary readers
  import no FrameIt and check actual outputs, clocks/cycles, units, masks,
  coefficients, provenance and unchanged input bytes.
- Existing schema and `_fa_runtime_options` are reused. No package/environment,
  public configuration key, scientific method, spectral/reconstruction admission,
  transform/derived/polar implementation, staging, commit or push.

## Environment and reproducible commands

All Python commands run in `frameit_env`, Python3.13.18, with explicit worktree
`PYTHONPATH`. Fixture checks use the approved local read-only fixture:

```bash
export PYTHONPATH="$PWD/src"
export FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01"
```

Exact unfiltered brief command:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_mnh_surfex_support.py src/frameit/testing/numerical/test_fa_contracts.py src/frameit/testing/numerical/test_fa_cubes.py src/frameit/testing/numerical/test_fa_pipeline.py src/frameit/testing/numerical/test_fa_spectral.py
```

Initial focused command (historical):

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_source_inventory src/frameit/testing/numerical/test_request_selection.py::test_v3_fa_record_evidence_from_inventory --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-focused-final-02.xml
```

Covering command:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_v3_netcdf_reads.py src/frameit/testing/numerical/test_v3_grib_reads.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_regions.py src/frameit/testing/numerical/test_fa_resources.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-covering-final-02.xml
```

Full diagnostic and comparison/lint commands:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-full-final-02.xml
PYTHONPATH="$PWD/src" conda run -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-evidence.py tests
PYTHONPATH="$PWD/src" conda run -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-evidence.py lint
git diff --check
git diff --cached --quiet
git rev-parse HEAD
```

## Initial observed results (historical; resumed results below)

| Check | Actual result |
|---|---|
| Focused final02 | 118passed,91 warnings;54.71s |
| Exact unfiltered brief / matching89-node XML | 41passed,48failed,128 warnings;10.04s;exit1 |
| Covering final02, before final focused support/origin checks | 799passed,39failed,467 warnings;exit1 |
| Historical full final01 | 1626passed,469failed,2errors,4subtests,4488 warnings;359.10s |
| Current full final02 | 1627passed,469failed,2errors,4subtests,4495 warnings;342.63s;exit1 |
| Ruff14 changed/new Python files versus exact base | 26baseline/26current/zero new diagnostics |
| Diff whitespace / unchanged empty index | Both commands exit0 |
| HEAD | Exact unchanged base above |
| Approved fixture SHA256 manifest | All9 payloads OK |

Passing selections overlap and are not summed. Full/required failures remain
failures; no test was skipped, assertion weakened or warning globally suppressed.
New generated output tests establish numerical/metadata preservation for those
fixtures, not general scientific or real-producer validity.

The final full comparison contains2098 distinct nodes. All470 Task06 failed/error
nodes keep their individual status; all27 new nodes pass. The sole changed
baseline outcome is the explicitly named interpretation assertion above
(passed → failed). There are841 distinct passing targeted nodes across the
selected runs, not841 additional passes to add to the full run.

The full report is `.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-report.md`.
Its raw RED/GREEN, command logs, JUnit XML and complete per-node failure appendix
`task-07-failure-ledger.md` are retained in that workspace. Each current failed/
error node is compared individually with
`task-06-fix-1-full-final-01.xml` (1601passed/468failed/2errors), including
both failure messages. The prior89-node inventory is not used as a current run.
The separate `task-07-required-failures.md` checks each of the48 required failures
individually; exact-command failed IDs equal required XML failed IDs, and all89
required statuses match Task06. These comparator checks execute as assertions.

## Scientific, documentation and review limits

No scientific-method/default or output-unit conversion is introduced. SEA uses
only the existing explicit mask/sentinel interpretation; FA retains existing
decoder scaling checks and explicit fallback policy. Native output and internal
stencils stay distinct. Unrelated operation/method gates remain.

The lead owns public guide reconciliation/build/GUI review, STATE, staging and
commits. Two draft-guide corrections were identified read-only:

- The selected v3 SEA route records provenance under per-source `interpretation`
  and `field_metadata`; it does not populate the old `surfex_provenance` list.
  The guide must not advertise unbound v3 polar operations as Task07 support.
- FA `levels.indices` retains original zero-based native indices, not relative
  positions in a sparse association list.

No independent task review, stable scientific-method promotion, general native
qualification, documentation visual acceptance or human sign-off is inferred.

## Resumed Ruling1 completion — current

The recorded bounded ruling authorized only the interpretation branch of
`test_tracker_binding_does_not_clear_unrelated_pending_operations`. Its actual
no-SEA-work request now asserts genuine binding in child/parent/source-plan
slots, empty interpreted-field/pending-value-check lists, unchanged scalar
exports, actual MSLP/UM10/VM10 tracker inputs/internal dependencies, exact selected
record names without FRAC_SEA, and no output ownership.

Only that17-line positive branch was added. The other three rejection cases,
their existing assertions, shared fixture helper and all production code are
unchanged. An AST comparison of the complete module after removing only the
added branch equals the base module. SHA256 checks confirm all10 production
files equal their start-of-resume bytes.

### Refreshed commands

Every command below uses the worktree explicitly; fixture checks retain the
approved `FRAMEIT_CI_DATA_ROOT`.

RED reproducer, then GREEN all four cases:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q 'src/frameit/testing/numerical/test_v3_regions.py::test_tracker_binding_does_not_clear_unrelated_pending_operations[interpretation]' --tb=short
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_regions.py::test_tracker_binding_does_not_clear_unrelated_pending_operations --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-resume-green-interpretation-01.xml
```

Focused including all regional/geographic callers, and unfiltered covering:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_source_inventory src/frameit/testing/numerical/test_request_selection.py::test_v3_fa_record_evidence_from_inventory src/frameit/testing/numerical/test_v3_regions.py src/frameit/testing/numerical/test_geographic_lookup.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-resume-focused-final-01.xml
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_v3_netcdf_reads.py src/frameit/testing/numerical/test_v3_grib_reads.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_regions.py src/frameit/testing/numerical/test_geographic_lookup.py src/frameit/testing/numerical/test_fa_resources.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-resume-covering-final-01.xml
```

The exact unfiltered five-file brief command was rerun with the same explicit
fixture prefix, then repeated with XML for per-node comparison:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_mnh_surfex_support.py src/frameit/testing/numerical/test_fa_contracts.py src/frameit/testing/numerical/test_fa_cubes.py src/frameit/testing/numerical/test_fa_pipeline.py src/frameit/testing/numerical/test_fa_spectral.py
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_mnh_surfex_support.py src/frameit/testing/numerical/test_fa_contracts.py src/frameit/testing/numerical/test_fa_cubes.py src/frameit/testing/numerical/test_fa_pipeline.py src/frameit/testing/numerical/test_fa_spectral.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-resume-required-final-01.xml
```

Full diagnostic, all-node comparison, all15 delivery Python files' lint and
bounded-scope checks:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-resume-full-final-01.xml
PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-evidence.py tests
PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-evidence.py lint
PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-evidence.py scope
```

### Current observed results

| Check | Actual result |
|---|---|
| Fresh RED, unchanged original interpretation assertion | 1failed,10 warnings;0.64s |
| GREEN, all four branch cases | 4passed,37 warnings;0.73s |
| Focused with all regional/geographic callers | 181passed,432 warnings;74.57s |
| Expanded covering | 812passed,38failed,474 warnings;122.01s;exit1 |
| Exact unfiltered required | 41passed,48failed,128 warnings;10.65s;exit1 |
| Matching required XML run | 41passed,48failed,128 warnings;10.79s;exit1 |
| Unfiltered full diagnostic | 1628passed,468failed,2errors,4subtests,4495 warnings;356.97s;exit1 |
| Ruff, all15 delivery Python files including authorized test | 26baseline/26current/zero new diagnostics |
| AST and production scope verification | exit0; helper/other branches and all10 production hashes unchanged |
| Final whitespace/index/HEAD checks | diff checks exit0; empty index; exact unchanged base |
| Final environment/checkout probe | Python3.13.18 in frameit_env, this worktree selected;exit0 |

The full comparison preserves **all2071 Task06 node statuses** and adds27 passing
Task07 nodes, for2098 distinct nodes. The failed/error IDs and individual states
are exactly the470 baseline IDs; no new failure/error or missing old node.
All2098 previous Task07 final02 node IDs remain, and the only status change from
that historical run is the authorized interpretation assertion failed → passed.
The comparator explicitly asserts an empty changed-baseline-status set.

There are **853 distinct passing targeted nodes** across the resumed selections.
Overlapping focused, covering, required and branch runs and the separate subtests
are not summed again or added to the full run.

New retained report appendices:

- `task-07-resume-failure-ledger.md`: every current failure/error full node ID,
  individual baseline/current status and both failure messages.
- `task-07-resume-required-failures.md`: all48 required failure IDs, per-node
  producer evidence, and both messages. All89 required outcomes match Task06,
  and failed IDs from the exact command equal the XML failed IDs.
- `task-07-resume-suite-comparison-final-01.txt`: executed comparison assertions.
- `task-07-resume-lint-final-01.txt`, `task-07-resume-ruff-summary.txt` and
  separate JSON: baseline-relative15-file lint.
- `task-07-resume-scope-final-01.txt`: executed AST and production-byte checks.

These artifacts and each matching raw command log/XML are under
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/`; earlier snapshots and ledgers remain
historical, not overwritten or reclassified as passes.

No scientific/numerical or production change was made in this resume. The
context request is closed; independent task review is next. Full/required suites
remain failed as recorded, without skips, warning suppression, weakened negative
cases or blanket scientific approval. The lead retains public docs/example
execution/STATE/staging/commit ownership; no such worker result is inferred.

## Independent-review fix round1/5 — current

Reviewed tree: `61352b1bd07f99afd778f513eb05cb045e269011`.
Base/HEAD remains `edaf6028a581f9031e88047da4239d583e55ca6e`.
Findings1–3 are implemented for independent re-review, not independently closed.
The original no-SEA assertion ruling was accepted and required no further edit.
Its authorization was the lead's bounded technical ruling, not new human
scientific approval.

### Changed behavior and handoff

- Admitted CF clock names and their actual dimensions travel as record
  `temporal_names`. The metadata resolver uses them to interpret `cell_methods`
  without conflating mean, maximum or accumulated values. Parenthesized CF
  qualifiers are not additional temporal methods.
- Explicit same-value unit aliases replace arbitrary case folding in the new
  declaration path and necessary SEA boundary. MW and mW remain distinct;
  unknown spellings gain no guessed case equivalence. Admitted kelvin/K,
  W/m2/W m-2 and Pa/N/m2 still agree. Observed labels/origins are retained;
  no numeric conversion or global `utils/units.py` change occurs.
- Opted-in eligible SEA inventory normalizes only evidenced unit spelling for
  field identity before ambiguity checks. All other attributes and real grid,
  provider, support, quantity and statistic conflicts remain significant.
- Each eligible snapshot retains raw `observed_attributes`; selected records
  carry their own `field_metadata: {attributes, origins}`. Selected main fields
  and FRAC_SEA support use those records, not another snapshot's metadata.
  Descriptor and combined-product metadata remain representative of the first
  selected record.
- `sources.<id>.interpretation.metadata_records` in source/run provenance adds
  one entry per selected eligible field/time/cycle/provider, including field,
  basename source ID, time, cycle, clock, raw observed attributes, resolved units
  and origins. It preserves spelling/origin differences between snapshots.

Four production files differ from the reviewed tree: `core/preflight.py`,
`processing/requests.py`, `io/surfex_utils.py`, `io/netcdf_utils.py` under
`src/frameit/`. The owned `test_v3_interpretation.py` adds27 nodes (6 clock,
11 unit,10 snapshot cases), for53 nodes. All previous test/helper function ASTs
are unchanged; no shared fixture producer or FA production code changed.

### Exact RED/GREEN commands

All commands use `frameit_env` Python3.13 with explicit worktree `PYTHONPATH`.
The fixture root is explicit and read-only. Output logs are under
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/`.

I1 RED (`task-07-fix-1-red-I1.txt`), initial GREEN
(`task-07-fix-1-green-I1.txt`), qualifier RED
(`task-07-fix-1-red-I1-qualifier.txt`) and final GREEN
(`task-07-fix-1-green-I1-final-01.txt`), in that order:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py -k cf_temporal --tb=short
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py -k 'cf_temporal or contradictory' --tb=short
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py -k interval_qualifier --tb=short
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py -k 'cf_temporal or interval_qualifier or contradictory' --tb=short
```

I2 RED (`task-07-fix-1-red-I2.txt`) and GREEN
(`task-07-fix-1-green-I2.txt`):

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py -k 'stored_unit_comparison or distinct_si or alias_declaration or case_fold' --tb=short
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py -k 'stored_unit_comparison or distinct_si or alias_declaration or case_fold or grib_declarations' --tb=short
```

I3 RED (`task-07-fix-1-red-I3.txt`) and GREEN
(`task-07-fix-1-green-I3.txt`) used the same command before and after its fix:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py -k 'equivalent_sea_snapshots or snapshot_aliases' --tb=short
```

### Final focused, covering, required and full commands

Raw `.txt` output is retained beside each named XML. The exact required command
has its separate `task-07-fix-1-required-exact-01.txt` log.

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_source_inventory src/frameit/testing/numerical/test_request_selection.py::test_v3_fa_record_evidence_from_inventory src/frameit/testing/numerical/test_v3_regions.py src/frameit/testing/numerical/test_geographic_lookup.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-fix-1-focused-final-01.xml
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_v3_netcdf_reads.py src/frameit/testing/numerical/test_v3_grib_reads.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_regions.py src/frameit/testing/numerical/test_geographic_lookup.py src/frameit/testing/numerical/test_fa_resources.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-fix-1-covering-final-02.xml
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_mnh_surfex_support.py src/frameit/testing/numerical/test_fa_contracts.py src/frameit/testing/numerical/test_fa_cubes.py src/frameit/testing/numerical/test_fa_pipeline.py src/frameit/testing/numerical/test_fa_spectral.py
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_mnh_surfex_support.py src/frameit/testing/numerical/test_fa_contracts.py src/frameit/testing/numerical/test_fa_cubes.py src/frameit/testing/numerical/test_fa_pipeline.py src/frameit/testing/numerical/test_fa_spectral.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-fix-1-required-final-01.xml
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-fix-1-full-final-01.xml
```

The initial covering used the same11-file selection with
`--junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-fix-1-covering-final-01.xml`.
It preceded the new qualifier case and is historical, not the final gate.

Comparison, scope and lint:

```bash
PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-fix-1-evidence.py tests
PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-fix-1-evidence.py lint
PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-fix-1-evidence.py scope
PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m ruff check .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-07-fix-1-evidence.py
```

Interpreter/worktree check, and fixture manifest command run from its root:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -c 'import pathlib, sys, frameit; assert sys.version_info[:2] == (3, 13); assert pathlib.Path(sys.prefix).name == "frameit_env"; assert pathlib.Path(frameit.__file__).resolve() == pathlib.Path("src/frameit/__init__.py").resolve(); print(sys.version); print(sys.executable); print(frameit.__file__)'
# Working directory: build/yaml-v3-ci-fixture-01
sha256sum --check --strict SHA256SUMS
```

### Observed results

| Check | Actual result |
|---|---|
| I1 RED / initial GREEN | 5failed,11 warnings,1.29s /14passed,29 warnings,1.49s |
| I1 qualifier RED / final I1 GREEN | 1failed,3 warnings,0.59s /15passed,31 warnings,1.51s |
| I2 RED / GREEN including GRIB controls | 8failed/3passed,24 warnings,0.73s /13passed,24 warnings,2.18s |
| I3 RED / GREEN | 2failed/8passed,161 warnings,0.93s /10passed,161 warnings,2.65s |
| Focused, all regional/geographic callers | **208passed**,627 warnings,83.42s;exit0 |
| Initial covering before qualifier addition/fix | 838passed/38failed,667 warnings,109.82s;exit1 |
| Final unfiltered covering | **839passed/38failed**,669 warnings,122.80s;exit1 |
| Exact required / matching XML | **41passed/48failed**,128 warnings;11.38s /11.80s;both exit1 |
| Unfiltered full diagnostic | **1655passed/468failed/2errors**,4 passing subtests,4690 warnings,361.48s;exit1 |
| Dual-reference comparison | exit0; no removed old node or changed old status against either reference |
| Delivery Ruff versus Task06 | all15 Python files;26baseline/26current/**zero new diagnostics** |
| Delivery Ruff versus reviewed Task07 | five fix-different files;20baseline/20current/**zero new diagnostics** |
| Scope and prior-test ASTs | exit0; only four production files and owned test differ from reviewed tree |
| Evidence script Ruff | exit0; all checks passed |
| Interpreter/worktree | exit0; Python3.13.18, frameit_env, worktree source imported |
| Approved fixture manifest | all9 payloads OK; read-only check |

The full comparison has **2125 distinct nodes**. All2071 Task06 and all2098
reviewed Task07 node IDs retain their individual statuses. All54 additions since
Task06 and all27 fix additions since reviewed Task07 pass. Every addition is
listed individually against each reference. Old status changes are `[]` against
both; the failed/error set is exactly the same470 IDs with their individual
states retained.

Every selected XML node agrees with the final full status. All89 required
statuses match both references, and the48 exact-command failed IDs equal the
required XML failed IDs. Each required failure has individual old-producer/error
evidence checked against both references, not a counts-only exemption.
The fix selections contain880 distinct passing targeted nodes; overlaps with
other selections/full runs and subtests are not counted twice.

Current appendices, all under `.superpowers/sdd/CHECKLIST_FOR_AGENTS/`:

- `task-07-fix-1-failure-ledger.md`: every failed/error node with current and both
  reference messages, individual additions/status comparisons and retained RED
  node results.
- `task-07-fix-1-required-failures.md`: all48 required failures with both references.
- `task-07-fix-1-suite-comparison-final-02.txt`: executed comparison assertions.
- `task-07-fix-1-lint-final-01.txt`, separate Task06/reviewed Ruff JSON and summary
  files: actual command/path/source-line diagnostics, not whole-project clean lint.
- `task-07-fix-1-scope-final-02.txt`, `task-07-fix-1-environment-final-01.txt`,
  `task-07-fix-1-evidence-lint-final-02.txt`: final checks.

The initial delivery lint found one new unused loop variable, fixed before the
final full/covering runs. The optional evidence-script lint found one overlong
string; wrapping it changed no delivery code/tests, and both that script's lint
and executed comparison were rerun. Earlier evidence remains historical.

### Scientific, compatibility and review limits

No numeric conversion, new scientific method, public configuration key,
dependency or new backend is introduced. Existing opt-in SEA value/mask policy,
source-local FA descriptors, selected clocks/cycles, separate internal/product
stencils and safety gates remain. Ordinary independent readers check generated
values, times, units, origins, fractions and per-snapshot provenance; source
bytes remain unchanged. This is not general real-producer/native qualification.

The lead owns public guides/examples, STATE, strict Sphinx/publication/GUI checks
and commits. The new per-snapshot provenance and representative-product metadata
facts above are the documentation handoff; the worker did not edit or verify
those lead-owned public surfaces.

Minor4 remains deferred to Task19/native-warning triage. FACADI, NumPy binary-size,
backend-deprecation and fixture-encoding warnings remain disclosed and unsuppressed.
No package/native repair, source archive write, subagent/reviewer dispatch,
staging, commit or push was performed. Required, covering and full failures remain
failures, not scientific passes. Original-reviewer closure of findings1–3 and
human scientific/usability acceptance remain pending.

Final workspace commands:

```bash
git diff --check
git diff --cached --quiet
git rev-parse HEAD
git status --short --branch
```

Both diff checks exit0; the real index is empty and HEAD is the exact base above.
The new test and this portable evidence remain untracked. Their actual contents
were also compared directly with reviewed-tree copies using `git diff --no-index`
(exit1 means differences, not a failed acceptance check). The lead's next review
snapshot must include both on-disk files; ordinary tree-relative diff output can
otherwise display them as deletions. Lead-owned guide/STATE changes are preserved.

## Independent closure and final lead verification

The original independent reviewer approved both spec and quality after closing
all three Important findings, with no new finding. The no-SEA-work assertion
ruling was independently accepted. Minor4 is deferred to Task19/final native
warning qualification, not suppressed or explained away.

Fresh lead precommit command:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py --tb=short
```

Observed53 passed/286 warnings in31.42s. Final full remains1655passed/468failed/
2errors; all54 added Task07 nodes pass and every earlier node/status is preserved.
Required41pass/48fail and covering839pass/38fail are not green suites. Their
failures and the original assertions still blocked by old producers retain the
named later owners, rather than being claimed as scientific successes.

All three complete guide requests run unchanged against final code with generated
fixtures and separate ordinary readers. They check literal values, units/origins,
native masks/zeroes/NaNs/clocks/axes/FA coefficients and actual provenance,
including21 SEA metadata entries. All6 source files remain unchanged.

Final documentation commands use the same frameit_env/PYTHONPATH prefix:

```bash
sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-37
python docs/check_publication.py build/docs-preview/yaml-v3-37
python -m unittest discover -s docs -p test_check_publication.py
python -m pytest -q docs/test_documentation_plots.py docs/test_release.py
```

Strict/publication/13unit/4pytest plus2subtests passed with15backend warnings.
All8 affected pages have live desktop/actual320 inspection;6 unchanged final
pages exactly match earlier reviewed HTML. The preview remains available.
Six native FACADI warnings persist in the cube example. No general native/
real-producer scientific or human acceptance follows from these checks.
