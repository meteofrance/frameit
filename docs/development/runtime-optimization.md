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
