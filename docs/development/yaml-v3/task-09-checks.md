# Task09 — product-driven polar sampling checks

Base: `db6258e74dd46df069e8e1434b78b2e1f709d587`. These are engineering and
prescribed numerical checks, not independent scientific approval.
Status: independently approved after fix round1/5. Pending-review sections below
are historical delivery snapshots, superseded by the final closure record.

## Implemented handoff

Polar products now carry executable preparation, method, target and native-support
plans through the complete source binding. Readers retain separate native exports
and internal stencils. Actual prepared children bind once.

`binding.operations` remains model-grid-only. Polar preparation is in
`binding.operation_plans`; `binding.polar_plan` records axes, source/centre-time
associations, spacing evidence, support policy and point budget.
`execute_source_polar(...)` supplies the existing source-qualified writer through
`runner.field_products[(source, "polar")]`.

- Polar input support and coordinates do not depend on model-grid crop width.
- Native/coarsest spacing is evidence-based. Rings include the exact outer radius
  and use clockwise-from-north open azimuths.
- Continuous/categorical methods require metadata or a declaration. Nearest uses
  the existing ESMF spherical source-cell footprint without extrapolation.
- Strict/explicit-threshold coverage preserves zeroes, missing/unmapped values
  and field-specific quality flags.
- Speed uses sampled components, not sampled model-grid speed. No extra
  radial/tangential or speed result is inferred from selected U/V.
- W preparation is independent. Native/mass levels, original indices, compatible
  coordinate units and pressure-velocity meaning remain distinct.
- Source-native clocks, calendars, admitted preceding-hour intervals and actual
  per-record geometry/rotation metadata are retained.
- NetCDF and Zarr v3 payloads, uint8 quality and separate NetCDF tracks reopen
  with ordinary readers without importing FrameIt.

No parser/schema/dependency/catalogue change, reader rewrite or shared old
document/fixture-producer conversion. Full multigrid/writer qualification remains
Task10; broad resource tuning remains Task11.

## Commands

Use the selected checkout and the required Python 3.13 environment. Fixture runs
must use the declared read-only fixture root.

Focused:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_polar.py
```

Required six files, unfiltered:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_polar_contracts.py src/frameit/testing/numerical/test_polar_axes.py src/frameit/testing/numerical/test_polar_coverage.py src/frameit/testing/numerical/test_polar_wind.py src/frameit/testing/numerical/test_polar_regrid_plan.py src/frameit/testing/numerical/test_coupled_shared_polar.py
```

Covering configuration, preparation, readers, regions, tracking and native
optionality:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_polar.py src/frameit/testing/numerical/test_v3_operations.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_regions.py src/frameit/testing/numerical/test_v3_interpretation.py src/frameit/testing/numerical/test_v3_netcdf_reads.py src/frameit/testing/numerical/test_v3_grib_reads.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_native_extraction.py src/frameit/testing/numerical/test_wind_collocation.py src/frameit/testing/numerical/test_wind_reference.py src/frameit/testing/numerical/test_wind_preflight.py src/frameit/testing/numerical/test_grid_representations.py src/frameit/testing/numerical/test_croco_vectors.py --tb=short
```

Full unfiltered diagnostic:

```bash
FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q --tb=short
```

Raw runs additionally record JUnit XML. Node comparisons use actual testcase IDs,
not overlapping run totals or subtest counts.

## Observed checks

Python: **3.13.18** in `frameit_env`.

| Check | Observed result |
|---|---|
| Focused final | **101 passed**, 428 warnings, 39.01s |
| Required fresh pre-implementation baseline | 161 passed / 14 failed; 175 nodes |
| Required final | **161 passed / 14 failed**; 175 nodes, 166 warnings, 8.55s |
| Covering final | **1026 passed / 68 failed**; 1094 nodes, 2020 warnings, 181.49s |
| Final full | **1819 passed / 468 failed / 2 errors**; 2289 nodes, 5636 warnings, 430.68s |
| Base-relative Ruff, all 15 changed/new Python files | **23 base / 23 current diagnostics, zero new** |

The covering run preserves all 993 baseline nodes/statuses for those exact files
and all 68 failing IDs, adding 101 passing nodes. The final full comparison
preserves every one of Task08's 2188 IDs/statuses and its exact 470 failed/error
IDs. All 101 added nodes pass. Four passing subtests are reported separately,
not added to the 2289 nodes.
Red suites remain red; assertions blocked by old producers are not passing
scientific assertions. Individual current/prior traces are retained in the worker
evidence, not replaced with a blanket exemption.

Three bounded old pending-polar assertions now check actual preparation, output,
coverage and clocks. Invalid units, missing support, geometry, budgets, ambiguity
and missing/pending executable-plan negatives remain.

## Bounded measurement

A 9×9 float64 source, two fields and two moving centres produces 64 geometry
targets and 128 scientific field values. With one cache entry and a 65,536-byte
retention budget, actual sampling recorded:

- 2 plan builds, 2 hits, 4 field applications, 1 eviction;
- 1 peak retained entry and **9,624 estimated retained bytes**;
- radius/azimuth chunks 2×4 and 525 Dask graph tasks;
- 3.434s for the observed run; lifetime peak RSS 307,326,976 bytes.

Independent readers checked float64 fields, uint8 status and prescribed constants
within absolute 1e-10; the source SHA-256 stayed unchanged. This single compact
measurement is not an archive benchmark or a speedup claim. RSS is process
lifetime high-water usage. Target counts/cache retention are not whole-run
memory ceilings. Native decoder/Dask horizontal I/O can exceed the numerical
stencil window.

## Remaining gates

No warning suppression or native environment repair. Native binary-size, backend
deprecations, fixture time-encoding and FA helper warnings remain visible.
General producer/warning qualification and old producers/legacy formatter retain
Tasks16/19 ownership. Public example execution, strict documentation/publication
checks, live visual review and independent task review remain lead-owned.
No staging, commit or push was performed by this worker.

## Pre-review guide acceptance fix: 1-D geography

The original 101 passing cases did not establish guide acceptance. The lead's
unchanged complete polar guide failed on the unchanged instructional generator's
1-D `latitude`/`longitude` dimension-coordinates. Execution's combined rename
renamed the geographic variables to `y_box`/`x_box`, leaving no `longitude` for
the geometry cache. Planning and input preparation had retained genuine geography.

The local executor fix renames dimensions separately from variables, preserving
geographic coordinate names, values, attributes and units. Non-geographic native
axis coordinates retain their prior normalization. No schema, default, method,
clock, level, unit, descriptor or helper interface changes.

Two additive generator-based cases cover the collision and a separate 1-D
noncolliding control, without converting the source to a 2-D fixture. They run
real binding, selected NetCDF reads, bilinear sampling and export. Independent
ordinary readers check 0/1000 origins (absolute 1e-9), native clocks/calendar,
centre times, radii `[0,1.5,2]`, eight clockwise angles, strict missingness and
quality. The two southeast stencils stay missing; zero stays valid; source hashes
and geographic metadata remain intact.

RED: collision fails with the original KeyError; control already passes.
GREEN: both pass. The complete unchanged guide YAML and its execution/reader
Python blocks also pass on the original input in fresh worker-owned output.
This was not a rerun of the lead's complete example/fragment harness.

Focused refresh command (same environment/fixture command above) now observes
**103 passed**,431 warnings,39.75s: all original 101 IDs/statuses preserved plus
two passing 1-D cases. Old evidence above remains historical; refreshed broader
diagnostics and both full-run baseline comparisons are recorded in the worker
report under “Pre-review guide acceptance fix”.

| Refreshed check | Observed result |
|---|---|
| Focused | 103 passed;431 warnings;39.75s |
| Exact required six files | 161 passed/14 failed;166 warnings;6.41s |
| Same 16-file covering command | 1028 passed/68 failed;2023 warnings;179.08s |
| Single final full diagnostic | 1821 passed/468 failed/2 errors;2291 nodes;5639 warnings;433.53s |
| Base-relative Ruff, same 15 Python files | 23 base/23 current;zero new |

Required and covering retain every prior ID/status and failed-node trace; the
two additional 1-D passes are counted separately from the original 101.
The one final unfiltered full command is the same full command above, with raw
artifacts `task-09-example-fix-full-final-01.{txt,xml}`. Exact comparisons preserve
all 2188 Task08 IDs/statuses and all 2289 original Task09 full-final03 IDs/statuses.
It adds 103 passing nodes versus Task08 (original 101 plus two), and only the two
1-D passes versus Task09. No removals, changed statuses, new failing IDs or skips;
the exact 470 failing/error IDs remain. Four passing subtests are separate.
Each failed/error node retains both traces in new dual-baseline ledgers; old
XML/trace artifacts are preserved. These red suites are not presented as green.

An independent check of the actual original-guide output records maximum origin
error 0, four missing values, the original `proleptic_gregorian` calendar and
native source clocks, with unchanged input hash. Actual method/preparation are
`polar_input`/`native_samples`, sampling/basis `native`; kind/time declarations
are recorded as declarations. This synthetic scalar has no physical meaning.

The generator, shared old producers, six public pages, STATE and lead's harness/
preview remain untouched. Lead retains full example execution, strict publication
and visual checks, and first independent review. No staging, commit or push.

## Pre-first-review scalar FA admission fix

The rectilinear full run above remains frozen historical evidence. The lead's
subsequent shared GRIB/FA example exposed a separate guard bug: a native 2-D
`SFX.T2M` locator has a record list but no vertical `source_positions`. The guard
incorrectly attempted a cube subset with `None`.

Only the existing admission guard changes: use the owning field's explicit cube
association to subset cube support; compare scalar locators intact and reject
invented scalar vertical selections. Complete owning-inventory/locator/time/
cycle/native-axis, invalid/pending-plan and native decode/resource checks stay.
No fake indices, dropped metadata, reader rewrite, schema or scientific change.

Five additive real-FA cases retain all prior 103 definitions/cases unchanged:
selected 2-D scalar decoding/sampling/output with prescribed zero/300/missingness,
native clocks/units, no unused time/companion payload and unchanged source hashes;
four scalar/cube corrupted-locator/support negatives. RED was 2 failed/3 passed;
GREEN is 5 passed. Ordinary-reader processes import neither FrameIt nor native
FA libraries. Synthetic packing-0 NaNs do not qualify packed mask reconstruction.

The unchanged actual shared request now executes into fresh worker-owned output,
without rerunning/editing the lead harness or changing its source files. An
independent reader checks the shared targets and observed pressure/FA units,
values, clocks and quality; source-specific native-index auxiliaries are retained.

| Refreshed check | Observed result |
|---|---|
| Focused | 108 passed;431 warnings;50.57s |
| Exact required six files | 161 passed/14 failed;166 warnings;6.37s |
| Same 16-file covering command | 1033 passed/68 failed;1101 nodes;2023 warnings;190.30s |
| Single final full diagnostic | 1826 passed/468 failed/2 errors;2296 nodes;5639 warnings;441.52s |
| Base-relative Ruff, same 15 Python files | 23 base/23 current;zero new |

Exact commands, raw RED/GREEN evidence, scope proof and completed covering/full
three-baseline comparisons are in the existing worker report under
“Pre-first-review scalar FA admission fix”. Historical XML and per-node failed
traces remain preserved. The full comparison retains all 2188 Task08, all 2289
original Task09 and all 2291 rectilinear IDs/statuses. Additions are 108, seven
and five passing nodes respectively; the exact 470 failing/error IDs remain
unchanged. Four passing subtests are separate, not added to node totals.
Source/evidence hashes and the entire original 103-case prefix remain intact.
These inherited red suites are not claimed green or scientifically validated.
Lead retains full example/fragment, publication/visual
and first independent review gates. No staging, commit or push.

## Independent-review fix round 1 — shared budgets and integer fractions

I1 and I2 are implemented and engineering-tested; original-reviewer closure and
lead example checks remain pending. All108 reviewed tests/helpers are unchanged,
with13 additive passing cases.

**Shared target:** preparation/metadata/method/native-spacing/halo facts are
validated before final shared axes. A target-only `pending_polar_target` binding
has no executable owning request or bound polar descriptor. Coarsest axes are
resolved once/source, then each complete-time budget is checked before publication
of the same actual binding objects; no second input bind. Failed finalization/
rebind clears current owner/product clearance and stale common-target facts.
Real1/3-km sources with two times/radius4/count9 (or automatic9) fit60 at54points,
radii0/3/4;53 rejects54 before payload/output. Genuine step/kind/geometry/method/
halo/pending failures and late-participant failure remain closed. The fine grid's
unmapped outer north sample remains missing/status1, not extrapolated or dropped
from allocation counts.

**Integer evaluation:** only prepared integer inputs already admitted as
continuous bilinear are evaluated in float64 on a local v3 polar view. This
preserves 2.5 and -2.5 midpoints within1e-8 without changing exact native int32
values, units, masks or source bytes. Float32/64 and categorical nearest retain
their evaluation policies; the shared coverage helper is unchanged.

`polar_numeric_types` (JSON output attribute) and per-record provenance
`numeric_types` record prepared/evaluation dtypes and conversion, not a new user
option. Actual integer midpoint values are ±2.500000000204945 (absolute error
2.05e-10); source/native int32 and polar float64. Float32 remains float32.
Prepared dtype is after decode/preparation, not necessarily encoded storage.
An output dtype alone is not proof of correct arithmetic. Ordinary float32/64
roundoff remains, not every integer beyond2**53 is exactly representable, and no
bitwise/large-integer exactness or archive-memory claim is made.

| Refreshed check | Observed result |
|---|---|
| I1 distinguishing GREEN | 12 passed;73warnings;7.19s |
| I2 fractional/native/type/mask GREEN | 1 passed;8warnings;4.74s |
| Focused | 121 passed;510warnings;54.77s |
| Covering18files, including coverage/regrid callers | 1110 passed/68 failed;1178nodes;2102warnings;196.94s |
| Exact required6files | 161 passed/14 failed;166warnings;6.40s |
| ONE frozen unfiltered full | 1839 passed/468 failed/2 errors;2309nodes;5718warnings;444.32s |
| Base- and reviewed-tree-relative Ruff, same15files | 23 baseline/23 current each;zero new |

Full comparisons retain all2188 Task08 and all2296 reviewed scalar-FA IDs/statuses,
adding121 and13 passing nodes respectively. Exact470failed/error IDs remain;
no removed/status-changed old nodes, added failures or skips. Four passing subtests
are separate. Per-node current/prior traces and all raw message differences remain
in `task-09-fix-1-*` artifacts, not waived by totals.

Exact commands, interfaces, RED/GREEN evidence, scoped covering files and dtype
facts are appended to the existing worker report under “Independent-review fix
round1/5”. Six reviewed paths change, all within original15 claims; no coverage
helper/new production module/parser/shared-producer edit. Source/review/baseline
hashes and empty-index scope proof are retained.

Minor3 warning qualification remains Task19 debt for later whole-branch review.
No suppression/environment/native repair, public page/harness/STATE/preview edit,
subagent/reviewer dispatch, staging, commit or push. Lead owns examples/canonical
note and original reviewer recheck; these are not self-approved closures.

## Final lead example and publication checks

The lead reran the complete documented scalar request and published execution/
ordinary-reader blocks unchanged. Strict, declared0.75renormalization and
both-products4/8-km crops pass: exact axes/native clocks, origin0/1000, units,
missingness, field geometry/support/status/ring flags and portable provenance.
All polar variables/coordinates and metadata are crop-independent while actual
model-grid shapes differ. Downstream mean/Fourier/partial-mean fragments execute
with the explicit public angular dimension.

The shared GRIB/FA example also passes in its explicitly stated source/centre/
pressure-kind context. Ordinary readers without FrameIt/native FA imports check
prescribed100500Pa/280K, source-native clocks, coarsest shared target, quality and
native provenance. Source-specific index auxiliaries are retained; shared
coordinates are not an instruction to equate those auxiliaries. All6 generated
source hashes remain unchanged. This is compact prescribed engineering evidence,
not real-producer/scientific qualification.

Fresh lead scalar-FA5case check passes; raw-XML assertions corroborate all108 added
Task09 passes and exact preserved baseline failures. Required/full remain red.
Fresh Ruff15paths23base/23current/noNew and scope preservation checks pass.
Strict47/publication/13unit/4plot-release+2subtests pass with15backend warnings;
all6 affected rendered pages match live desktop/narrow-inspected46HTML.
First independent task review remains required; nothing staged/committed/pushed.

## Independent closure and final verification

I1/I2 are independently addressed; spec and quality approved with no new finding.
All3 old-test adaptations are legitimate. Minor3 inherited warnings remain
Task19/final-branch qualification debt, not suppressed or scientifically cleared.

Fresh lead precommit command:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_polar.py --tb=short
```

Observed121passed/510warnings/54.97s. Final unfiltered full1839pass/468fail/2errors
preserves every Task08/reviewed status and exact470failed-error IDs,121new passes;
required161pass/14fail remains red with individual producer traces. No passing
scientific assertion is inferred from a blocked old producer.

Final-code complete examples06 pass with6 unchanged source hashes. Strict49/
publication/13unit/4plot-release+2subtests pass with15warnings. Both updated dtype
notes inspected live at1020/actual320, no overflow/missing images; four other
affected49pages equal previously inspected47HTML. Preview remains available.
Canonical numeric-type provenance and ordinary roundoff/large-integer limits
match actual evaluation. No scientific/human acceptance or archive benchmark.
