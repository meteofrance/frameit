# Task11 resource, layout and profiling checks

Latest: Task11 spec and quality are independently approved after fix1. Both
findings are closed; all68resource cases pass. Strict61/publication and text-only
GUI checks pass. The1951/468/2full is PRE-FIX evidence only; no post-fix whole-suite
result exists. Earlier rejected-candidate and pending-review sections below are
historical. See the final closure and STATE's frozen handoff.

Development evidence against `2a77b1dcfd06eccbabf10d1a58aac71881b8f6f8`.
Compact synthetic checks do not qualify production archives, scientific
applicability, or HPC performance.

**Incomplete candidate:**the single full diagnostic found15new native-preflight
regressions. Metadata-only inventory is wrongly forced through full binding.
This narrows/rejects deferred requests and blocks completion; it is not inherited
failure debt. Source/tests remain frozen pending lead direction on correction
and subsequent verification. No second full run has occurred.

## Behavior

Explicit `resources.cpus` is honored. Omission uses the strictest machine,
affinity and Slurm limit; excess requests fail before unsafe outputs. Serial
readers and export×compute×native limits fit that budget. Inactive synchronous
pools contribute one. One native thread and asynchronous export remain defaults.

Execution owns a bounded Dask pool, initializes thread-local native limits and
restores the caller's environment, Dask pool/settings and native limits. Actual
v3 NetCDF/Zarr exports use spawned workers unless synchronous.

Reader chunks use native axes after selected backend views. Product chunks use
actual public computational axes, including standard/qualified C7 leading names.
Writer chunks/shards use exported axes. A key must match the applicable requested
product union, not every source. Children receive applicable runtime chunks;
authored/common requested settings remain recorded. Unmatched keys fail before
payload/publication and revoke child/shared-target executable clearance.

`processing.profile:false` performs no optional polar cache/graph/RSS timestamp
measurements. Disabled elapsed values are explicitly unmeasured (`None`); activity,
retention and byte counters remain. True records actual observations, mode,
measured-call counts and cumulative observed-call scope. External-cache mode is
per call, never part of geometry identity. Off/on reuse neither invents earlier
construction time, rebuilds weights, loses history nor changes another caller.
Direct numerical timing defaults stay enabled; ordinary run duration is separate.

Provenance records effective origins, actual reader/product chunks, uncompressed
array sizes, unresolved input costs and reopened encodings. No schema, quantity,
unit/basis, precision, mask, target, admission implementation, coordinate identity,
CF reference or publication/overwrite policy changed.

## Commands and evidence

```bash
export PYTHONPATH="$PWD/src"
export FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01"
export TMPDIR=/tmp/opencode
conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_resources.py
conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_zarr_export.py src/frameit/testing/numerical/test_polar_dask.py src/frameit/testing/numerical/test_fa_resources.py
```

Python3.13.18; no packages/native repairs or warning suppression.
Focused:44passed. Connected:721passed across resources, outputs, execution,
NetCDF reads, polar, operations, v3 configuration and relevant cache/contracts.
Required79:60passed/18failed/1error, individually matching prior causes; these
inherited blocked assertions are not waivers.

The sole frozen unfiltered diagnostic observed1921passed/483failed/2errors, with
6144warnings and4passed subtests. All2362baseline nodes remain:2347same statuses,
15passed→failed regressions. All470old failed/error causes remain, all44new nodes
pass (including original35), and no nodes were removed. Every status/message/
trace change is individually classified;485raw pairs retain the evidence.
The15new failures are not waived. Raw RED/GREEN/logs/XML, AST scope proof,
source/frozen-input hashes, per-node trace pairs and measurements are under
ignored `.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-11-*`.

Regression groups:GRIB metadata inventory4, source inspection6, CF coordinate
metadata4 and metadata-only interpretation1. The root is replacing non-polar
`prepare_sources` inventory with `bind_sources`. Restoring that boundary must
retain full resource/union guards at actual binding/execution, not weaken tests,
scientific admission or old producers. Full details are in
`task-11-report.md`, `task-11-full-classification.json` and
`task-11-full-failures.md` in that ignored evidence directory.

The full additional-file AST proof preserves binding/shared-target/revocation and
C7 statements, geometry/hash/weights, numerical apply, masks, halos, limits and
LRU after removing only approved timing instrumentation. Two local test changes
retain scientific assertions:applicable native keys in one reader helper, and
accepting an absent directory on earlier rejection. The lead inspected/accepted
them at the Task11 checkpoint, not in advance. Independent review remains required.

## Bounded final measurements

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
conda run -n frameit_env python .superpowers/sdd/CHECKLIST_FOR_AGENTS/task-11-measure.py --final
```

One final trial per format/dtype/layout after union/timing changes. Two earlier
trials stay historical; timings are not merged across code states. Exactly3total
trials per setting.

Workload:4×3×129×129 synthetic field; selected times0/2; native plus40km/128-azimuth
polar products; zeroes and missing support. Payloads≤1,597,536bytes (<16MiB),
concurrency≤2CPUs and all retained storage76,315,288bytes (<200MiB).
Fresh ordinary readers import no FrameIt and compare all stored values, masks,
coordinates, dimensions, dtypes and variable attributes exactly, including both
retained prior trials.

| Format/dtype | Auto wall s | Explicit wall s | Auto field bytes | Explicit field bytes |
|---|---:|---:|---:|---:|
| NetCDF / float32 |1.871|2.521|714,071|1,169,098|
| NetCDF / float64 |1.892|2.490|820,955|1,481,527|
| Zarr / float32 |2.110|2.843|1,770,884|1,165,209|
| Zarr / float64 |4.598|2.758|2,270,475|1,646,270|

Automatic layouts versus explicit32-cell native blocks,8-radius/32-azimuth polar
blocks and larger Zarr shards. Precision, masks, compression1/coordinate-off,
safe chunks and single codec pool stay unchanged. No general/HPC speedup claim.

Parent RSS332.6–345.7MB; largest waited child327.2–340.4MB:separate lifetime
high-water marks including imports, not summed concurrent memory or incremental
allocation. Parent+waited-child block I/O:0physical reads and4,096–69,632write
bytes/run; caching/deferred writes apply. Logical stored sizes are separate.

GRIB/FA full-record decoding, backend caches and native/transform/mask/interpolation
workspaces remain unresolved. Array estimates/point guards are not memory ceilings.

The lead owns public docs/examples, strict/publication/text-only HTML checks,
independent review, STATE/checklist and commits. No manual images, screenshots or
JPEG inspection, source archive writes, environment changes, subagents, staging,
commits or pushes by this worker.

## Authorized preflight correction and replacement freeze

This append supersedes the incomplete-candidate status above; the rejected
candidate/report/full/freeze/measurements remain preserved separately.

Native preflight again discovers metadata with `prepare_sources`, without
scientific binding, candidate narrowing or payload reads. Effective CPU/worker
budgets and YAML/CLI/automatic origins are reported. Requested layouts remain
inspectable, but applicability/applied settings/storage layouts/estimates requiring
binding are explicitly pending. Polar preflight and actual bind/execution keep
their complete-union/no-payload/failure-revocation guards.

Correction scope is only `core/preflight.py`'s native branch/unbound report and
three appended local test definitions (15cases). All15old regressed assertions
and44prior Task11 cases are unchanged. Other169Python hashes, original resource
test bytes/AST, polar call and bound-resource helper are exact. No method,
scientific default, output/configuration schema or dependency change.

Prescribed frameit_env/Python3.13/worktree/fixture/TMPDIR checks observed:

| Check | Result |
|---|---|
| New guards, valid RED → resource-module GREEN |15failed →59passed |
| Exact15previous regressions |15passed |
| Complete five implicated modules |284passed/20inherited failures |
| Expanded981-node covering |961passed/20inherited failures |
| Exact required79 |60passed/18failed/1error |
| Existing execute/bind path tests, discovery forbidden |11passed |

Every original721covering node is retained passing. Both baseline per-node
comparisons recover all15regressions, retain44passes and identify15new guards
separately. Expanded20failures and required19failed/error causes remain individually
unchanged and unqualified, not waived. Exact commands/logs/XML/trace pairs are in
`task-11-report.md` and new `task-11-preflight-fix-*` evidence.

No further benchmark trials: the retained3per-setting trials/76,315,288bytes
measure the unchanged execute/bind path, not the corrected discovery branch.
Static routing/source-hash proof and11existing tests with discovery forbidden
exercise11actual executions/13binds/13bound-resource reports. No new timing claim.

`task-11-preflight-fix-freeze.json` records the genuine replacement source/test
freeze notified to the lead. The single authorized replacement unfiltered full
is running; the result and complete2362Task10/2406failed-candidate comparisons
will be appended. All9fixture and24benchmark input hashes and prior evidence
remain exact. New Ruff findings: none relative to the failed candidate.

The six public RST edits and STATE are lead-owned, kept separate from worker
scope. Lead draft documentation checks are not worker checks or Task11 runtime
examples; no Task11 runtime example had run before this freeze. Lead owns their
rerun, documentation publication/preview, independent review and commits.
No staging/commit/push, extra benchmarks, source-data writes, package/native
repair, warning suppression or manual image checks by this worker.

### Replacement full result

The single authorized replacement run completed: **1951passed/468failed/2errors**
across2421nodes, with6189warnings and4passed subtests (492.92s; exit1).
All2362Task10 statuses are unchanged. All2406rejected-candidate nodes remain;
exactly the15regressions recover, all44retained cases pass, and15new guards pass.
The exact470prior failed/error IDs retain their causes; no new/removed failure.

Both baselines have complete per-node statuses and955new raw trace pairs.
Task10:399raw-identical,65runtime/frame differences,6inspected context/repr/
summary differences with unchanged causes. Rejected candidate:423raw-identical,
47runtime/frame differences and15recoveries. No unresolved classification.
This is a verified correction, not an all-green suite or scientific sign-off.

New evidence: `task-11-preflight-fix-full-comparison.json`,
`task-11-preflight-fix-full-node-ledger.md`,
`task-11-preflight-fix-final-verification.json` and
`task-11-preflight-fix-proof-handover.json`. All171Python/pre-full artifact hashes
remain exact after the freeze;169other Python files, prior test bytes/AST,
987prior immutable artifact hashes and the full append-authorized report prefix,
9fixture and24benchmark input hashes are preserved.
No new Ruff finding; no additional full/benchmark run or source/test edit.

Independent Task11 review, lead-owned runtime/documentation checks and commits
remain outstanding. Inherited failure causes and scientific applicability limits
remain unqualified; no staging/commit/push or reviewer dispatch by this worker.

## Independent-review fix1: truthful direct-resource origins and reader prose

Against reviewed tree `b51accfed2539f92c7344cb65dd2f7d375077491`:

- Unlabelled direct Python scheduler/native-thread/synchronous-export values now
  compare with declared option-class defaults. Defaults remain `default`;
  differing choices become `explicit`. Supplied YAML/CLI/automatic labels are
  preserved, including repeated resolution and runtime/effective provenance.
- Only the automatic-reader description changed: Dask resolves chunks on selected
  backend views; `applications` records actual sizes. A real stored1×3×3 input
  yielded selected1×9×9 Dask chunks here, with exact values and input hash retained.
  No chunking/read implementation was changed to fit the description.

All59prior resource cases/helpers/assertions remain verbatim. Four appended
definitions add nine cases;168other Python files and all runtime/scientific/read/
bind/cache/thread/export AST outside the two reporting boundaries are unchanged.
No resource value, declared default, output/configuration schema or dependency
change. This is reporting correctness, not new scientific validation.

Prescribed Python3.13.18/`frameit_env` verification:

| Check | Observed result |
|---|---|
| New-case RED |6failed/3passed |
| Origin-only GREEN |8passed |
| Resource module |68passed |
| Final unfiltered six-file covering |555passed/6failed/1error;520warnings;88.33s |
| Exact required79, run once with XML |60passed/18failed/1error;6warnings;12.50s |

```bash
export PYTHONPATH="$PWD/src"
export FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01"
export TMPDIR=/tmp/opencode
conda run -n frameit_env python -m pytest -q --tb=short \
  src/frameit/testing/numerical/test_v3_resources.py \
  src/frameit/testing/numerical/test_hpc_execution.py \
  src/frameit/testing/numerical/test_configuration_v3.py \
  src/frameit/testing/numerical/test_v3_execution.py \
  src/frameit/testing/numerical/test_v3_netcdf_reads.py \
  src/frameit/testing/numerical/test_v3_outputs.py \
  --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-11-fix-1-covering-final.xml
conda run -n frameit_env python -m pytest -q --tb=short \
  src/frameit/testing/numerical/test_hpc_execution.py \
  src/frameit/testing/numerical/test_zarr_export.py \
  src/frameit/testing/numerical/test_polar_dask.py \
  src/frameit/testing/numerical/test_fa_resources.py \
  --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-11-fix-1-required.xml
```

All553covering baseline statuses and all79required statuses/causes match
`task-11-preflight-fix-full.xml`; nine new nodes pass separately. Across both
commands,613distinct nodes were freshly tested, including all59prior resource
controls. Each failed/error ID has a raw trace pair and cause classification;
none is waived or unresolved. All2188prior immutable artifact hashes, report/
portable prefixes,9fixture and24benchmark input hashes are preserved.
Fresh HEAD/review-relative Ruff adds no diagnostics; `git diff --check` exits0.

`task-11-fix-1-freeze.json` records the genuine source/test freeze notified to
the lead. New logs/XML, covered-node inventory/comparisons/trace pairs and scope/
preservation/lint proofs are under ignored `task-11-fix-1-*` artifacts.
The exact RED/GREEN/evidence commands and output details are appended to
`task-11-report.md`.

**No post-fix full diagnostic or new benchmark was run, per ruling.**
The1951/468/2full result above is PRE-FIX reviewed-candidate evidence only.
The15prior recovered nodes retain their unchanged source/tests and historical
passes, but were not rerun in these named selections. No post-fix status is
claimed for1817unrun baseline nodes. Task19/final full integration remains
required. Lead owns examples/docs/STATE and reviewer follow-up; no staging,
commit/push, reviewer/subagent dispatch, environment repair or image checks here.

### Lead verification of the frozen reporting fix

Fresh lead `test_v3_resources.py` run: **68passed/162warnings/19.91s**.
This includes real execution provenance for direct nondefault options and actual
selected-view reader applications, not only mocked labels. Saved covering and
required XML independently retain all604tested baseline statuses/causes plus nine
new passes. No post-fix status is asserted for1817unrun baseline nodes.

Lead verifies171frozen Python hashes,168other unchanged paths, the exact reviewed
copies,59byte-identical prior resource cases,2188immutable artifacts,9fixture
and24benchmark input hashes. Outside the fallback loop/description, module AST
is exact. Fresh baseline/review Ruff adds no findings; diff check passes.

Public pages remain unchanged. Fresh strict61/publication/13unittests pass;
six HTML pages equal60. Live text-only desktop/320px checks show no page overflow;
the preview remains available. No plot/image/screenshot check or human approval.
Earlier example/benchmark results remain pre-fix; no post-fix full was run.
Important1 and new-fix-breakage closure still require the original reviewer.

## Independent closure

The original reviewer closes Important1 and Minor2, approves scoped spec/quality
and finds no new Critical/Important/Minor issue. No Task11 finding remains open
or parked. The reviewer independently audits saved XML and changed-file hashes,
retaining the distinction between613freshly covered nodes and1817unrun nodes.
This is engineering review, not a whole-branch/scientific/human approval.

Fresh lead resource command:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_resources.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-11-lead-fix-1-resource.xml
```

Observed68passed/162warnings/19.91s. Source/tests/public pages match approved
tree6199d8f502432356d307fabfc37997367b202713; only final internal closure/checklist
records change afterward. Strict61/publication/13unittests and HTML/text-only GUI
evidence remain current. No further benchmark, image check or full run.
The final interfaces, compatibility and unresolved gate owners are frozen in
STATE under **Task11 frozen handoff — independently approved**.
