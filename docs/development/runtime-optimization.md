# Runtime optimization and native-reader investigation — 2026-11-04

## Scope and numerical contract

The runtime changes retain scientific equations, ESMF-generated point weights,
missing-data rules, coordinate conventions, first-storage-index geographic ties,
output schemas and configuration defaults. They remove redundant execution, not
scientific checks. Passing engineering tests is not scientific approval of every
input or regime.

- Polar application uses batched SciPy CSR multiplication with xarray/Dask.
  Horizontal chunks are combined within each cropped plane; leading time/level
  chunks are retained. Requested output chunks, labels, input precision,
  strict/renormalized masks and quality flags remain supported. Retained CSR
  storage is included in the existing plan-cache byte estimate.
  Target rows are partitioned before multiplication, not merely rechunked after
  allocating the whole target. Borderline partial-support sums are re-evaluated
  with `math.fsum`, using `2 * nonzero_stencil_size * eps64` only to select sums
  for re-evaluation; no acceptance slack or changed scientific cutoff is added.
  This corrects a previously chunk-dependent one-bit threshold decision; literal
  tests also require genuinely subthreshold support to remain invalid.
- Spawned Cartesian/polar export phases share one resource-capped pool, retaining
  their serial phase order, atomic per-product publication and native isolation.
  The existing explicit synchronous-export setting and its default are unchanged.
- Repeated 2-D geographic lookup builds a local candidate index once. Wrapped
  candidates are evaluated with the original squared-degree arithmetic; ties
  select the first storage index. One-point/1-D and extreme-coordinate lookups
  retain the scan; native FA projected lookup is unchanged. Coupled sources still
  perform their existing containment checks before selecting points.
- Native pressure-centroid columns bypass sorting only after the existing strict
  monotonicity checks. Winds remain linear in height and pressure logarithmic,
  with no extrapolation. Legacy unordered-height records still sort.
- Pressure-wind tracking materializes each selected window once, retaining local
  all-NaN/global fallback and failure behavior.

## FA batching: investigated, not shipped

The disposable four-record engineering probe measured 0.626 s for separate
children versus 0.232 s within one child (2.7× startup amortization). It is **not**
a qualified multi-record transaction: it directly invokes worker handlers and
does not provide the parent-side descriptor/NPY validation for a batch.

The production Dask graph owns an independently sliceable `FaArray` for each
native record. This is what permits sparse cube selections to decode only the
selected records. Combining records into a shared array/task before graph culling
can decode excluded levels and retain multiple full native planes; adding an
unused batch API alone would provide no pipeline benefit. Grouping already-culled
requests would require a separately qualified graph/protocol change, with a total
batch memory/transfer limit and per-record freshness, scaling, declaration,
diagnostic and transfer checks. No such change or persistent native service is
introduced here. Existing disposable per-record decoding remains in place.

## BATSIRAI pipeline measurements

The workload is the two-timestamp, 300-km, six-surface-field/five-scalar-cube
selection in [input-reading.md](input-reading.md), at stored indices
`[5, 15, 30, 45, 60, 75]`, with polar sampling explicitly enabled at 3000-m radial
spacing and 180 azimuths. Inputs are the same read-only Meso-NH files, without a
new content-checksum identity claim. The cropped fields have 101 × 101 points.

Baseline `9341f31` was exported to a disposable source-only directory, selected
with `PYTHONPATH`; the optimized code was `6811edc`. Nothing was reinstalled.
Three fresh processes per variant and
export mode, with alternating order, used the same `frameit_env` Python 3.13.18,
one Dask worker/native thread/export worker, existing NetCDF4 level-1 compression
and warm filesystem cache. Timing covers `execute_simulation`, including selected
reads, output publication and cleanup, not interpreter startup/imports. Medians:

| Export mode | Pipeline before → after | Speedup | Parent peak RSS before → after |
| --- | --- | --- | --- |
| Existing spawned default | 7.452 → 4.186 s | 1.78× | 497.6 → 386.9 MiB |
| Explicit synchronous | 4.668 → 3.311 s | 1.41× | 482.4 → 390.0 MiB |

With spawned export, median polar setup/application fell 2.218 → 1.013 s and
export 3.979 → 1.916 s. Choosing the already supported synchronous option gives
2.25× relative to the old spawned case, **not** a new automatic export default.
Do not multiply routine factors or assign these whole-run gains to other models.
RSS is the parent's process-lifetime high-water mark, not summed worker memory.

Spawned three-run ranges were 7.366–7.557 → 4.171–4.188 s. Synchronous ranges were
4.600–7.189 → 3.287–3.383 s; one baseline run had slower polar startup.
Earlier optimized runs also observed startup variability, and a separate profile
showed that ESMF initialization can be a material cost.
No OS cache was flushed; these are not cold-storage/throughput measurements.

An independent xarray/NumPy process, without importing FrameIt, reopened all
six baseline/optimized pairs: **30 products / 1032 variables**. Values, NaNs,
coordinate roles, dimensions, dtypes and every variable's metadata matched
exactly. Global creation history/profiling records and serialized bytes are not
claimed identical. This is bounded numerical regression verification, not
scientific qualification of every source or interpolation regime.

The production geographical index, measured against the original scan in the
same process for 300 positions on the 602 × 962 BATSIRAI grid, took median
0.123 versus 1.424 s including index construction: **11.6×**, identical indices.
That is lower than the audit's deliberately simpler candidate-only prototype.
The retained vertical/wind probes exercised the shipped code with exact checked
results: native 87 × 160 × 160 interpolation took 5.81 ms (audit baseline
50.7 ms); wind tracking took 50.6 ms (audit baseline 96.7 ms), with selected-field
backend calls **23 → 9** and decoded array bytes 26.64 → 10.42 MB. These last
before/after timings are separate probe sessions, not the paired pipeline study.

## GRIB shutdown failure: isolated cause and scoped fix

The original five-file AROME read returned shape `(5, 1, 81, 81)` and finished
dataset cleanup, then aborted with SIGABRT. Reducing the case showed **no input
file is needed**:

```bash
conda run -n frameit_env python -c 'import eccodes; import pyproj'
# Observed SIGABRT during interpreter shutdown in this installed stack.
conda run -n frameit_env python -c 'import pyproj; import eccodes'
# Observed clean exit.
```

Observed Linux stack: Python ecCodes 2.44.0 selecting the `eccodeslib` 2.50.0.33
wheel/C API 2.50.0; `findlibs` 0.1.3; `eckitlib` 2.5.0.33; pyproj 3.8.0 using
Conda PROJ 9.9.0. `findlibs` recursively preloads eckit shared objects with
`RTLD_GLOBAL`, including its separately bundled PROJ 9.8.1. Loading that bundled
PROJ directly with `ctypes.CDLL(..., mode=RTLD_GLOBAL)` before pyproj reproduced
the abort; `RTLD_LOCAL` or pyproj-first initialization exited cleanly. This
isolates a global native-PROJ collision, consistent with symbol interposition,
not a failed `DatasetResources.close()` or corrupt GRIB payload. GDB observed
allocator failure in libc's interpreter-process exit handlers; the precise
upstream C++ object/destructor defect was not patched or independently proved.

FrameIt now defers optional cfgrib initialization into the actual loader call,
after its core geometry imports. Fresh-process discovery and reading regressions
cover normal interpreter exit, not merely successful return from the loader.
The original unfiltered five-file reproduction also exits cleanly after the fix.
No decoder, definitions, input field, scientific default or environment was
silently substituted.

A real `python -m frameit run` smoke case used the same five packaged files,
explicit Earth-relative U/V at stored index zero, a fixed 20-km box, spawned
export and disabled polar processing. It completed with track and Cartesian
products. An independent process reopened the output and original GRIB fields:
all five valid times and 15 U/V/speed field checks matched exactly.

**Limit:** this corrects FrameIt's own direct-loader initialization order. It
cannot undo an incompatible native library already loaded by external code.
External `eccodes`-first/pyproj-later scripts can still reproduce the upstream
collision. Use a fresh process and a coherent native stack, or initialize pyproj
first when reproducing this particular stack; do not treat arbitrary native
libraries as safely unloadable. A subprocess-only diagnostic with
`FINDLIBS_DISABLE_PACKAGE=yes` selected the installed Conda ecCodes C 2.46.0 and
also exited cleanly in the formerly failing import order. That alternative C
selection was **not** adopted or qualified as a production backend change.

## EPyGrAM GRIB comparison: no production replacement

Three fresh-process repetitions read the same ten requested U/V fields
(1000 hPa, five packaged AROME files, 81 × 81 each). Each process reopened and
read twice; cfgrib's second pass reused its on-disk index. Threads were capped at
one and the filesystem cache was warm. Cleanup is inside read timing; import/
initialization is shown separately. EPyGrAM 2.1.0 ran with a private, GRIB-only
configuration and no FA native backend initialized. Both readers use the same
Python ecCodes/C decoder; changing the high-level reader alone does not remove
the dependency collision.

| Path | Import/init | First read, no existing index | Repeated read | Peak process RSS |
| --- | --- | --- | --- | --- |
| Current selected FrameIt loader | 0.217 s | 4.042 s | 1.467 s | 261.2 MiB |
| Direct filtered cfgrib | 0.250 s | 2.581 s | 0.034 s | 259.1 MiB |
| EPyGrAM `readfield` | 0.144 s | 2.076 s | 1.892 s | 134.1 MiB |
| Disposable EPyGrAM message-stream probe | 0.143 s | 1.191 s | 0.985 s | 134.1 MiB |

The streaming probe is promising for one-pass sparse selection, but is **not**
a compatible FrameIt adapter. Standard EPyGrAM reads were slower on repeats, and
cached direct cfgrib was much faster. FrameIt's extra group/selection/alias/
derived-field work is not present in either raw-reader row; raw-reader RSS is not
a demonstrated FrameIt pipeline memory saving. These results do not establish
a universally faster backend or justify replacing the supported reader.

Independent comparisons covered 180 field arrays, units, valid times, pressure
levels, coordinate grids and the Earth/grid wind flag. EPyGrAM reversed latitude
storage order and returned float64 rather than cfgrib's default float32. After
**explicit** axis reversal and casting to the existing output precision, checked
values/masks matched exactly; native-value differences before casting reached
1.90e-6 m s-1. Coordinate differences were below 2e-12 degrees. These selected
winds had no missing cells: bitmap/missing-field compatibility, other GRIB grid
types, statistical intervals, ambiguous messages, lazy xarray integration and
the full supported metadata contract were not qualified for a replacement.

## Reproduction artifacts and remaining scope

Disposable scripts, paired configurations, numerical products and JSON results
are retained locally under `/tmp/opencode/frameit-performance-audit/` and
`/tmp/opencode/frameit-grib-investigation/`; no private datasets or bulk outputs
are committed. The pipeline configuration is reproduced by the selection in
`input-reading.md` with `polar.enabled: true`, `radial_step_m: 3000` and
`azimuth_count: 180`. Use fresh output directories for each variant.

No production-scale CROCO/NEMO/AROME, cold/network storage, GPU/UTrack, cluster
or exhaustive experimental-method performance claim is made. FA batching and
an EPyGrAM-to-xarray GRIB adapter remain unimplemented, not advertised support.

## Local implementation commits

- `c9bc30b`: bounded implementation/investigation plan.
- `9bb96f4`: batched polar CSR application and regression coverage.
- `bda189a`: shared bounded spawned export pool.
- `bc2ec66`: indexed geographical lookup, including coupled mapping.
- `cebca6f`: native vertical brackets and one-time tracking-window evaluation.
- `e70bdbe`: documented FA batching admission boundary.
- `7381f82`: serializable module-level polar block callable, with a failing-then-
  passing spawn-pickling regression and subsequent successful pipeline exports.
- `30a6a3d`: deferred cfgrib initialization and fresh-interpreter lifecycle tests.
- `6811edc`: final review fixes: bound executed target blocks/culling and accurately
  re-sum borderline support without acceptance slack, with red/green regressions.

No commits were pushed. Scientific methods/defaults and output/configuration
schemas are unchanged; no migration is required.

## Final verification and review

On `6811edc` in `frameit_env`, Python 3.13.18:

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q
# 1062 passed, 2 subtests passed, 4588 warnings in 559.12 s.

git diff --name-only 9341f31..HEAD -- '*.py' | \
  xargs conda run -n frameit_env ruff check --select F,I
# All checks passed (changed Python files; not a whole-repository lint claim).

conda run --no-capture-output -n frameit_env \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python -m sphinx -b html -E docs/source /tmp/opencode/frameit-runtime-docs
# Successful HTML build; the two pre-existing warnings below remain.

git diff --check
# Passed.
```

Existing Sphinx warnings remain in `tracker/pressure_centroid.rst:12` (title
underline) and `tracker/pressure_wind_tracker.rst:142` (markup/blank line).
Strict warning-as-error documentation mode was not rerun. Existing NumPy/
NetCDF/cfgrib warnings remain; they are not represented as new scientific
validation failures or as evidence of scientific validity.

A fresh-context, read-only engineering review identified two important gaps:
post-hoc target rechunking did not bound actual multiplication, and accumulation
roundoff could flip a support-threshold mask. Both were independently reproduced
in new failing tests, fixed in one pass, and followed by **119 passing focused
tests and the full suite above**. Tests exercise actual multiplied row counts,
unselected-target culling, exact-threshold and genuinely subthreshold stencils.
No second independent review or human scientific sign-off is claimed.

Final paired-run evidence is `final-paired-timings.json`,
`final-pipeline-summary.json` and `final-comparison.json` in the performance
artifact directory. GRIB evidence includes `proj-collision.json`,
`reader-timings.json`, `reader-comparison.json` and `cli-smoke-check.json` in the
native-reader investigation directory.

Decisions retained: work stayed on the existing local development branch with
unrelated files preserved; coupled lookup shares the indexed path only after
its existing containment checks; FA batching and an EPyGrAM adapter remain
deferred at their documented performance cost. Roundoff is corrected by more
accurate summation, not a looser scientific threshold. Unchanged methods still
require researcher judgment, and externally preloaded incompatible native
libraries remain outside the scoped loader fix.
