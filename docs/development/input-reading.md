# Input-reading profile and optimization — 2026-11-04

## Result

The shared NetCDF path reuses an opened lazy dataset for geography discovery,
per-file checks and loading. Ordinary runner preflight uses the same resource
owner and configured chunks. Native Cartesian groups are no longer constructed
when the selected representation is mass/Earth. Explicit native products,
per-file scientific checks and reader/chunk defaults are unchanged.

No model-specific numerical method, output schema, YAML setting, dependency,
precision, mask or scientific default was changed. Reuse ends on close or failed
load rollback; there is no persistent cache. Coupled source inventories/preflight
retain their independent lifecycles; their loaders still avoid duplicate opens.

## Workload and environment

- Baseline revision: `0f9852031f508fafa9a0cb54fa8fba92891dd8a8`.
- Dataset: the two `BATSIRAI-10mins/1BT01.1.MXX30.00[12]dg.nc` Meso-NH files,
  11,033,046,348 bytes each; no content-checksum identity claim is made.
- Each file: one timestamp (2022-02-01 00:10 / 00:20), 65 variables,
  87 mass/interface labels, 602 × 962 mass-grid points, 3-km projected spacing.
- Fixed geographical centre: 18.48651012957362° S, 55.01422440445546° E;
  300 × 300 km extraction, yielding 101 × 101 points at both times.
- **Surface:** MSLP, UM10, VM10, ACPRR, SST, ZS. The existing automatic
  `wind_speed` accompanying a selected U/V pair is retained in both variants;
  no extra diagnostic or polar processing is selected.
- **Sparse cubes:** the same surface selection plus THT, MRV, REHU, TKET and
  TEMP at stored zero-based indices `[5, 15, 30, 45, 60, 75]`. No physical-height
  interpretation or conversion of these scalar fields is introduced.
- File chunks: surface fields typically `(1, 301, 481)`, scalar cubes
  `(1, 18, 121, 193)`; geography and ZS are contiguous.
- Conda `frameit_env`, Python 3.13.18, Linux, 16 available CPUs, approximately
  30.6 GiB RAM; xarray 2026.9.0, Dask 2026.8.0, h5netcdf 1.8.2, h5py 3.16.0,
  netCDF4 1.7.2, NumPy 2.5.4. No environment upgrade was performed.
- Dask worker, native threads and synchronous export worker: **one each**.
  Output is ordinary NetCDF4 with the existing level-1 compression.

## Measurement scope

Three fresh worker processes per reader/workload/variant; tables show medians.
Timing covers `execute_simulation`: input setup, selected lazy reads, tracking,
extraction, manifests, synchronous export and cleanup. Python startup, initial
script imports and configuration construction are outside the timed interval.
This is pipeline wall time, not a CLI-startup measurement. cProfile was enabled
only for separate investigations, **not** for the timing table.

Inputs are lazy: `loading_data` measures metadata, coordinates, checks and graph
construction, **not all payload I/O**. Physical reads occur during export in
these fixed-box cases. Both loading and whole-pipeline time are therefore shown.
Whole-domain eager benchmark mode was deliberately not used.

The filesystem cache was warm; the first exploratory reads populated it, and
no shared OS cache was flushed. `/proc/self/io` `rchar` records reads reaching
the OS, including metadata and reads served from cache; `read_bytes` records
storage reads and was usually zero during timed repetitions. Neither is the
same as decoded array volume. Peak RSS is the fresh process lifetime high-water
mark, including imports, native caches and exports, not input-only memory.

## Default h5netcdf reader

| Case | Pipeline before → after | Speedup | Loading before → after | Loading speedup | Peak RSS before → after |
| --- | --- | --- | --- | --- | --- |
| Surface | 2.269 → 1.398 s | 1.62× | 1.872 → 0.944 s | 1.98× | 274.6 → 266.1 MiB |
| Sparse cubes | 2.646 → 1.736 s | 1.52× | 1.968 → 0.975 s | 2.02× | 317.0 → 287.2 MiB |

Three-run pipeline ranges: surface 2.265–2.304 → 1.372–1.415 s;
sparse cubes 2.602–2.667 → 1.708–1.748 s.

| Work / I/O counter | Surface before → after | Sparse cubes before → after |
| --- | --- | --- |
| Actual `xr.open_dataset` calls | 6 → 2 | 6 → 2 |
| Backend indexing calls, including coordinates | 130 → 82 | 192 → 138 |
| Logical bytes returned by h5netcdf indexing | 142.2 → 141.5 MiB | 350.2 → 323.0 MiB |
| Of those, during loading | 89.2 → 88.4 MiB | 142.2 → 115.0 MiB |
| OS `rchar`, whole timed pipeline | 178.9 → 160.2 MiB | 387.0 → 341.9 MiB |

Backend instrumentation counts array bytes returned, not compressed storage
chunks or disk traffic. Most improvement is avoiding repeated metadata setup,
not reading less physical data. Some coordinate work now uses Dask during
runtime preflight; fewer opens does not imply fewer Dask tasks in every case.

## Root cause

Before optimization each source was opened for metadata preflight, reopened to
discover geographic variable names, then opened again for lazy field loading.
The h5netcdf profile spent approximately 2.99 of 4.41 profiled seconds in those
six opens for the surface case. Its repeated variable shape/chunk discovery
visits the HDF5 dimension reference lists, including the unlimited time axis.
This is library/header overhead even when almost all scientific payloads remain
unread. The optimization does not patch or monkeypatch that library.

Independent per-file normalization is necessary: units, vector bases, clocks,
native sigma definitions and masks cannot safely inherit the first file's
interpretation. That work and exact coordinate/auxiliary equality checks remain.
Only the redundant raw opens and unused native-output branch are removed.
Existing spatial and sparse-level chunk culling already works; these workloads
do **not** load both complete 11-GB files into memory.

## Existing netcdf4 input option

| Case | Pipeline before → after | Loading before → after | Peak RSS before → after |
| --- | --- | --- | --- |
| Surface | 0.814 → 0.814 s | 0.500 → 0.429 s | 309.8 → 300.9 MiB |
| Sparse cubes | 1.071 → 1.076 s | 0.578 → 0.483 s | 509.5 → 485.5 MiB |

The existing alternative reader has much cheaper metadata opens here. Sharing
reduces its loading time and memory, but gives **no demonstrated whole-pipeline
speedup** for these small products. Its optimized sparse-cube RSS is about
198 MiB higher than h5netcdf. Backend/native chunk caching and export contribute
to the process peak; no memory limit or universal backend ranking is implied.
For these files, explicitly choosing `input.netcdf.engine: netcdf4` is faster
overall than the default, at a memory cost. The default is deliberately unchanged.

## Numerical and compatibility verification

An independent process imported xarray/NumPy, **not FrameIt**, and reopened all
12 baseline/optimized run pairs. Products, dimensions, coordinate roles, every
decoded value (including NaNs) and every variable's attributes matched exactly.
The only observed global attribute difference was export-time `history`.
Two further comparisons checked matching products between the input readers.

One hundred independent native field/geography window checks used the saved
track bounds, original files and explicit stored level indices. Copied fields
matched exactly; surface speed matched a direct NumPy Euclidean magnitude.
This checks decoded numerical identity, **not byte-identical NetCDF files** or
general scientific validity of the source fields or native vertical formulae.

Regression coverage includes both installed readers for compact Meso-NH,
AROME, NEMO and CROCO inputs; one open per source file; no selected/unrequested
field payload reads during setup; stored chunk preservation; close/reopen and
failure/retry; engine/chunk cache separation; standalone preflight cleanup;
explicit native winds and the mass-W sidecar. Existing native, coupled,
variable-shard, metadata-conflict and optional-dependency regressions remain
the compatibility checks for their respective contracts.

Verification in `frameit_env`:

- `conda run -n frameit_env python -m pytest -q`: **1006 passed**, two subtests
  passed, 4585 warnings, 667.33 s. Existing NumPy/NetCDF/cfgrib warnings remain.
- `conda run -n frameit_env ruff check --select F,I` on the five changed Python
  files: passed. This is import/undefined-name checking, not a whole-repo lint claim.
- `conda run -n frameit_env python -m sphinx -b html -E docs/source <output>`:
  successful HTML build with the two existing warnings listed below. Adding
  `-W --keep-going` fails on those warnings.
- `git diff --check`: passed.

A subsequent actual `frameit run` CLI smoke run on the same sparse-cube
configuration completed with three products. Its decoded outputs and variable
metadata matched the baseline, with another 32 independent native-window checks.
A fresh-context, read-only code review found no critical, important or minor
issues; its additional focused tests and raw-dataset isolation/rollback checks
passed. That engineering review is not scientific sign-off.

## Reproduce or profile another selection

Use the same environment and separate baseline/optimized source checkouts with
`PYTHONPATH=<checkout>/src`; do not reinstall or upgrade dependencies between
variants. Set paths relative to the following YAML, with fresh output directories:

```yaml
schema_version: 2
model: mesonh
run: {name: input-benchmark}
input:
  directory: ./data/BATSIRAI-10mins
  pattern: '*.nc'
  format: netcdf
  netcdf: {engine: h5netcdf, chunks: {}}
  wind_pairs:
    - {group: surface, u: UM10, v: VM10, reference_frame: earth}
tracking:
  method: fixed_box
  fixed_box:
    center: {latitude: -18.48651012957362, longitude: 55.01422440445546}
domain:
  size_km: {x: 300, y: 300}
variables:
  surface: {names: [MSLP, UM10, VM10, ACPRR, SST, ZS]}
  level:
    names: [THT, MRV, REHU, TKET, TEMP]
    levels: {indices: [5, 15, 30, 45, 60, 75]}
polar: {enabled: false}
execution: {dask_workers: 1, native_threads: 1}
output:
  directory: ./input-benchmark-output
  overwrite: false
  synchronous_export: true
  max_workers: 1
```

Remove the `level` block for the surface workload. The following portable CLI
measurements include startup, so their totals will differ from the table:

```bash
conda run -n frameit_env /usr/bin/time -v python -m frameit run benchmark.yaml \
  --output-directory ./measure-01 --no-overwrite
conda run -n frameit_env python -m cProfile -o input-reading.prof -m frameit \
  run benchmark.yaml --output-directory ./profile-01 --no-overwrite
conda run -n frameit_env python -m pstats input-reading.prof
```

Repeat with new directories and alternate variant order. Compare both total and
section time, RSS and scientific outputs; do not infer disk throughput from
warm-cache timing. Local investigation artifacts include per-run JSON metrics,
configurations, profiles, ordinary NetCDF products and the independent comparison
report; private input data and generated bulk products are not committed.

## Limits / intentionally not done

- Only two real timestamps: no long-series or large-file-count scaling claim.
- No cold-storage, network-filesystem, production-cluster or parallel-I/O claim.
- No large real CROCO/NEMO/AROME speed measurements; their shared-path behavior
  is regression-tested on compact fixtures, not assigned the Meso-NH speedup.
- No FA/GRIB decoder redesign, default-reader change, global cache, whole-input
  preloading, aggressive concurrency or weakening of scientific checks.
- Warm before/after batches were measured sequentially, not a randomized study;
  the reported ranges describe these runs, not a performance guarantee.
- The HTML documentation builds, but strict warning-as-error mode encounters
  existing warnings in `tracker/pressure_centroid.rst:12` (title underline) and
  `tracker/pressure_wind_tracker.rst:142` (markup spacing), outside this change.
