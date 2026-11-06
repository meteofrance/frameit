# Shared input-reading optimization

## Intent and scope

Reduce repeated input setup in `frameit run`, primarily in shared routines rather
than Meso-NH-specific numerical methods. The maintainer requested profiling on
the BATSIRAI ten-minute Meso-NH dataset and delegated workload/implementation
choices with “dive in”. The following choices are the implementer's, not separate
human scientific approval.

## Evidence

Two 11,033,046,348-byte files each contain 65 variables, 87 native levels and a
602 × 962 mass grid. Bounded fixed-centre, 300-km Cartesian runs select six
surface fields, optionally five scalar cubes at six sparse levels. Polar
processing is disabled and no extra diagnostic is selected; the existing
automatic surface wind-speed output accompanying U/V is unchanged.
Dask/native/export concurrency is one.

Three fresh-process warm-cache baseline runs with the default h5netcdf reader
take a median 2.269 s (surface) and 2.646 s (sparse cubes). Loading accounts for
1.872 s and 1.968 s respectively. Each file is opened three times: preflight,
geography discovery and lazy loading. cProfile locates most setup overhead in
h5netcdf dimension/shape discovery, not physical-field decoding. Native output
groups are also built even when only mass/Earth output is consumed.

## Approaches

1. Switch the default reader to the installed netcdf4 backend: much faster on
   these files, but higher measured RSS; keep it an existing explicit choice.
2. **Chosen:** reuse raw, lazy NetCDF datasets within their existing resource
   owner's lifetime and skip unused native Cartesian groups. This preserves
   reader defaults and benefits every model using the shared NetCDF loader;
   avoiding unused native groups also applies to the other input formats.
3. Parallel opens or whole-input preloading: rejected because they add resource
   pressure, can defeat spatial chunk culling and do not remove duplicate work.

## Contract and constraints

- Use Conda `frameit_env` with Python 3.13; add no dependencies.
- Keep inputs read-only and generated profiles/products outside the repository.
- Retain the current input engine, chunk defaults, public YAML and output schema.
- Key reuse by path, engine and chunk selection, only inside `DatasetResources`.
  Closing or rolling back resources must discard the corresponding cache entries.
- Standalone validation must still close its inputs and never decode physical
  cubes. Runtime preflight may share lazy, configured-chunk datasets with loading.
- Preserve per-file clock, units, masks, formula, vector and geometry checks;
  preserve duplicate-time precedence and explicit native products.
- Do not remove coordinate equality checks, introduce approximations, eagerly
  load physical cubes, or treat passing tests as scientific validation.
- Coupled sources retain independent resource ownership and time selection.
  Their inventory/preflight scans need not be merged into a new lifecycle here.

## Acceptance

Tests must demonstrate one physical open per file for ordinary NetCDF runner
loading across Meso-NH, AROME, NEMO and CROCO, without unrequested payload reads;
separate readers/chunks and post-close retries must not reuse stale datasets.
Native output must remain correct when selected and absent when unused.
Re-run bounded BATSIRAI workloads in fresh processes, reporting wall time, peak
RSS and both logical backend read volume and OS I/O separately. Independently
reopen products and check exact decoded values, coordinates and scientific
metadata against the baseline and source windows. Document cache effects and
the absence of large real-data speed measurements for other models.
