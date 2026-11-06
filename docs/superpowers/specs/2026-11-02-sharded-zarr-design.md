# Optional sharded Zarr v3 output

## Intent and scope

Offer sharded Zarr v3 as an alternative container for the existing track,
Cartesian and polar products. Researchers choose one backend in YAML; product
grouping, scientific calculations, coordinates, masks and metadata meanings stay
unchanged. NetCDF remains the default.

## Approaches

- **Selected by the user:** one optional output backend per run. This preserves
  the existing workflow without duplicating export work or storage.
- **Rejected:** always writing both NetCDF and Zarr. This adds unnecessary I/O
  and storage; comparisons belong in tests.

## Configuration and products

Configuration refined with the user and approved for implementation:

```yaml
output:
  engine: zarr  # netcdf4 (default), h5netcdf, or zarr
  zarr_chunk_size: {time: 1, y: 128, x: 128}  # optional example
  zarr_shard_size: {time: 8, y: 512, x: 512}  # optional example
```

The existing `output.format` remains an optional NetCDF-specific setting and is
unused for Zarr. No separate backend selector is introduced. Selecting Zarr
writes `SIMU.track.zarr`, `SIMU.cart.<group>.zarr` and, when requested,
`SIMU.polar.<group>.zarr`, each a local directory store. Existing export selection
and CLI overrides continue to govern whether products are written; legacy
`netcdf` export switches act as the existing overall export gate for either
backend and are documented as such, without removing or renaming them.

Zarr is an optional dependency, imported only when selected. Unsupported library
versions or missing dependencies fail actionably before processing. The writer
uses Zarr v3 sharding with lossless compression, no additional precision loss,
and documented deterministic, bounded storage defaults. Actual chunk/shard
shapes remain inspectable in store metadata. Explicit sizes must be positive
integers and shards must be integer multiples of chunks; unused dimensions in
a particular product are ignored because track and group dimensions differ.
The exact default sizes and supported dependency floors are builder decisions
to establish from library APIs and small tests, then document.

## Publication and compatibility

Write into a sibling temporary store and publish only after writing succeeds.
Respect overwrite settings and the existing run-root lock. Directory replacement
needs a documented failure-safe protocol; do not claim atomic replacement of
nonempty directories where the filesystem cannot provide it. Inventory reports
store paths and recursive file-byte totals; status remains authoritative.

NetCDF behavior and existing configurations remain unchanged. Zarr products
reopen through ordinary compatible xarray/Zarr readers without importing
FrameIt. Zarr v3 reader support is required; a `.zarr` store is not a NetCDF file.
No scientific method, sampling convention or output variable definition changes.

## Verification and non-goals

Cover YAML validation, missing optional dependencies, actual sharding metadata,
ordinary-reader round trips (values, missingness, coordinates, times and attrs),
track/product references, coupled product groups, inventory sizes, failure and
overwrite handling, and unchanged default NetCDF export. Use compact synthetic
inputs; passing these tests is not scientific validation of arbitrary datasets.

No cloud URLs, append/resume, dual-format runs, new diagnostics, schema redesign,
or production-scale performance claims. Update templates, configuration/output
documentation and packaging with the implementation.

## User-facing explanation of chunks and shards

Documentation must introduce both concepts without assuming Zarr knowledge:

- A **chunk** is an independently encoded/compressed block of array values.
  Small chunks allow selective reading with less unnecessary decompression,
  but too many small chunks add indexing and processing overhead.
- A **shard** groups several chunks into one stored object (a file for the local
  stores supported here), reducing filesystem file counts without making the
  entire shard the unit of decompression. Compatible readers can request
  individual chunks within a shard; actual I/O depends on reader behavior.
- Both settings count array elements along named dimensions, not bytes or a
  number of files. Explain the example above: each chunk covers one time and
  128 by 128 grid points; each full shard covers eight times and 512 by 512
  points, containing 8 * 4 * 4 = 128 chunks. Edge shards can be partially filled.
- Explain defaults, positive integer and divisibility constraints, how overrides
  combine with defaults, absent dimensions, and effects on bounded write memory
  and selective-read performance. Explicitly state that neither setting changes
  resolution, sampling, precision or scientific values.
- Distinguish storage chunks from processing/Dask chunks and describe any writer
  alignment required for safe parallel writes. Do not promise universal optimal
  sizes or benchmark gains without measurements.
