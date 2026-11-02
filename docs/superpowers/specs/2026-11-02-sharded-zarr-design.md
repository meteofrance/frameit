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

Proposed configuration (implementation choices, pending approval):

```yaml
output:
  backend: zarr  # netcdf (default) or zarr
  zarr:
    chunks: {}  # optional dimension-to-size overrides
    shards: {}  # optional dimension-to-size overrides
```

The existing `output.format` remains a NetCDF-specific setting. Selecting Zarr
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
