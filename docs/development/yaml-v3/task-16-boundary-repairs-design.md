# Task16 boundary repairs

The maintainer authorized autonomous continuation on 2026-11-16 after the
default-preserving proposal. This records implementation choices, not scientific
qualification or human usability acceptance.

## Scope and approach

Use the existing configuration, inventory, binding, selected readers, unit
conversion and report helpers. No compatibility layer, replacement catalogue,
new dependency or global permissive default.

1. **Initial absent records.** Add source-local `allow_initial_gaps`, a list of
   explicitly selected field references. Its absence remains strict. It permits
   only a wholly absent field at the first selected source time, provided real
   later records establish its identity, grid, levels and units. Partial levels,
   later gaps, competing providers, missing coordinate/formula support and
   required tracker/derived-method inputs remain errors. Record actual permitted
   absences separately from physical input records. Preserve the source clock
   and export missing values, never zeros or copied physical observations.
   Initial-gap handling must remain lazy and must not invent payload locators.
   The original catalogue's named `tke`, `sshf`, `slhf` exceptions are the
   demonstrated need; no new producer-specific scientific fallback is inferred.

2. **Polar base-field units.** Add `units` to existing
   `products.polar.field_options.<source>.<field>`. Only explicitly selected
   base-field results use it; native units remain the default. Validate compatible
   source units using the existing conversion helper before execution. Convert
   values and metadata together, record source/target units, and preserve masks,
   interpolation quality, sampling, vector basis and model-grid output.
   Derived winds keep their existing m/s method contract.

3. **Per-file wind evidence.** Carry only the dataset attributes selected by
   `inspect_wind_metadata` into each NetCDF inventory entry. Preserve file
   association and opposing variable evidence. Report unknown, invalid and
   conflicting evidence descriptively; do not resolve it, dump unrelated private
   attributes, read field payloads or change wind preparation.

Global leniency, implicit cross-product transform inheritance and upstream
fixture rewriting were rejected because they change unrelated scientific
meaning or conceal missing source information.

## Acceptance and limits

Keep all helper signatures, original fixtures, source files, requested quantities,
five-time clocks, grouped levels, independent numerical assertions and tolerances.
Verify default failures, explicit positive paths, inactive declarations, later
gaps, incompatible units, metadata privacy, read bounds and ordinary-reader
output. Preserve both required PNG smokes only in required unfiltered suites;
no standalone image/plot/screenshot checks.

Each repair is independently testable; integrate them before continuing producer
conversion. Obtain a fresh bounded review before local implementation commits.
Task16's single full diagnostic is reserved for a real source/test/asset freeze.
The approved Tasks17–21 remain authoritative; installation/cluster/image
restrictions and actual human acceptance cannot be silently waived.
