# Task16 metadata preservation implementation plan

> Use `executing-plans` inline, with TDD and independent review before committing.

**Goal:** Repair the two metadata losses explicitly approved by the maintainer.
**Architecture:** Preserve observed NetCDF temporal evidence and actual selected
index attributes in the existing inventory/executor. No new interface or helper.
**Tech stack:** Python3.13 in `frameit_env`, existing xarray/readers, pytest.
**Spec:** The maintainer's “Yes” to fixes1–2 and a proposal-only treatment of3;
the independent three-core diagnosis, sections1/3, and existing C2/C5/C7 contracts.

## Boundaries

- Preserve strict time guards, `join="exact"`/`compat="identical"`, source clocks,
  samples, indices `[0,2]`/`[2,0]`, units, masks, W and current preparation.
- Do not infer missing temporal evidence or overwrite genuine index attributes.
- No crop/support-layout implementation, source fixture edits, package/environment
  work, standalone image checks, broad caller conversion or Task16 full diagnostic.
- Existing25dirty files are saved separately; leave them byte-exact.

## Review focus

Missing evidence stays missing; contradictory step/mean metadata still fails.
Generated index attributes match native output; supplied attributes survive.
Real index/label/attribute conflicts remain errors, not compatibility overrides.
Ordinary readers recover values, sigma formula support, clocks and metadata.

## A. Temporal metadata

- [x] Add `test_metadata_preservation.py` regressions for all three reference
  fields, no payload reads, instantaneous/absent/average/contradictory metadata,
  and actual preceding-hour execution with unchanged native clocks.
- [x] Observe failures, then preserve observed `GRIB_stepType` in
  `src/frameit/core/preflight.py::_netcdf_inventory`.
- [x] Run new temporal cases and existing preceding-hour guards; run the original
  portable NEMO example without weakening its numerical assertions.

## B. Native-index metadata

- [x] Add mixed native-rho/transformed-current tests, generated/supplied index
  metadata, both index orders and genuine-conflict controls.
- [x] Observe strict-merge failures, then preserve supplied attributes and use
  existing NEMO/CROCO generated-index metadata in
  `src/frameit/processing/derived/wind.py::execute_source_operations`.
- [x] Run new cases, existing operation/output/reader guards and the original
  portable CROCO cases. Report the separate crop failure honestly if still reached.

## C. Verification and handoff

- [x] Record exact results, update affected canonical metadata guidance, run
  strict docs/publication and text-only live HTML checks when prose changes.
- [x] Obtain independent review and resolve findings before the bounded local
  commit. SPEC PASS / QUALITY APPROVE, zero findings; closure in the checks record.
- [x] Prepare real CROCO support-layout alternatives and a recommendation for
  the handover's human decision. No implementation of that third issue.

Python/test prefix:
`PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode conda run --no-capture-output -n frameit_env`.
Self-review: both approved repairs map to A/B; C preserves the separate schema
decision. Existing signatures and scientific methods remain unchanged.
