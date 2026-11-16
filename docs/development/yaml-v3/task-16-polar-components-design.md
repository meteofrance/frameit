# Explicit polar wind components — bounded design

Status: maintainer-approved design for implementation planning; not implemented
or scientifically qualified.
Base: `9931f5859dbc9db3b57443c167f8b71943728c7a`.
The maintainer first approved drafting, then approved the written design in this
session on2026-11-16. This approves the expression/admission contract below,
not code implementation, a future implementation plan or scientific validity.

## Intent and demonstrated gap

Finish expressing the existing scientific catalogue without dropping its radial
and tangential winds or reintroducing implicit diagnostics. This belongs in
FrameIt because the numerical operation, polar geometry and interpolation already
exist; the missing part is an explicit request through the current v3 path.

`catalog.py::_products_expected` retains `vrad`, `vtan` and `wind_speed` for
`mnh_chido_fixed_polar`. Current `configuration.py::V3_CHOICES["derived"]` admits
only `wind_speed`; `polar_proj.py::execute_source_polar` does not call the legacy
implicit `add_vrad_vtan_from_polar_dict` path. The retained
`task-16-resume-polar-gap.py` probe confirms that speed resolves and radial/
tangential method requests fail without opening source datasets or writing products.

This design closes that expression gap only. Remaining producer/caller conversion
and its catalogue/checker assertions belong to Task16 after a reviewed core handoff.
It does not claim that the whole catalogue then executes or that Task16 is complete.

## Approaches and recommended boundary

1. **Two scalar methods in existing source `derived` — selected.** Reuse its
   one-output-name → one-method contract. Each component can be selected alone;
   existing product filters and qualified input references remain. This is the
   approved realization of the maintainer's explicit-existing-calculation
   direction.
2. **A paired-output method or a new polar-vector block — not recommended.**
   It would introduce output arity, names and selection machinery not needed to
   expose these two existing quantities.
3. **Implicit U/V-triggered outputs or mandatory downstream repair — ruled out.**
   The former contradicts C4 optionality; the latter does not preserve the
   catalogue's requested FrameIt products. Researchers remain free to calculate
   these quantities downstream, but that is not a substitute for this task.

No new vector framework, plugin registry, service, interpolation algorithm,
reference-frame motion correction or dependencies.

## Approved request contract

Add `radial_wind` and `tangential_wind` to the existing derived-method choices.
Both take exactly distinct `inputs: {u: <reference>, v: <reference>}`.
The output alias is user-selected; `vrad` and `vtan` are not reserved auto-exports.
Use existing grouped references when required, such as `heightAboveGround.u`.

Proposed YAML, **not runnable on the base revision**:

```yaml
schema_version: 3
sources:
  atmosphere:
    model: mesonh
    files: ./input.nc
    variables:
      3d: [UT, VT]
      levels: {indices: [1, 3, 5]}
    wind_pairs:
      - u: UT
        v: VT
        basis: grid
        rotation: {method: geolocation}
    derived:
      vrad:
        method: radial_wind
        inputs: {u: UT, v: VT}
      vtan:
        method: tangential_wind
        inputs: {u: UT, v: VT}
region:
  center: {latitude: -10.3, longitude: 55.0}
products:
  model_grid:
    fields: {atmosphere: [UT, VT]}
  polar:
    radius_km: 60
    radial_step_km: 3
    azimuth_count: 36
    fields: {atmosphere: [vrad, vtan]}
output:
  directory: ./output
```

This example declares the existing Meso-NH grid-basis/geolocation convention;
it is not permission to apply that convention to another producer without evidence.
UT/VT export is independent of diagnostic input preparation.

### Admission and optionality

- Initial public admission: atmospheric winds on the existing AROME GRIB/NetCDF
  and Meso-NH NetCDF paths, using their current wind-pair, unit, collocation and
  rotation guards. No new profiles, quantities, grids or time association.
- Initially **polar-only, strict interpolation support**. Reject an active
  `renormalize` request; do not fall back to strict. Require both components'
  effective interpolation/support settings to match and both to be continuous.
  They must occupy one common prepared grid; unresolved native staggering fails.
- FA and ocean-current variants are outside this initial public binding.
  Existing FA, NEMO, CROCO, native-copy and speed behavior remains unchanged.
  Their numerical similarity does not establish additional public admission.
- New methods are active only when selected by a field product. An unselected
  declaration must not load inputs, require a polar backend or change base outputs.
  Inputs can be internal-only; no implicit U/V, speed or other component export.
- If selected by `model_grid`, fail before payload reads/output creation with the
  method/product path and advice to select it only in `products.polar.fields`.
  `model_grid: true` still means all declared fields: no silent filtering of
  unsupported methods. Combined runs must explicitly filter model-grid fields.
- Preserve distinct-input, source/result collision, missing/ambiguous field,
  unit/basis/rotation, time/interval/calendar, C3 selector and destination-axis
  checks. Inputs are actual source fields, not a new derived-result graph.
- Preserve sparse/reversed/singleton levels, native clocks and selected-read
  stencils. One 3D result uses the common selector of its varying inputs.

The strict-only limit is deliberate: the retained numerical vector path uses
joint finite U/V stencils, while current v3 speed samples components separately.
Under renormalization, those can describe different reconstructed vectors.
Do not change `wind_speed`, its masks or its results when a new method is enabled.
A future renormalized public vector contract needs separate design/verification.
The original catalogue requests use the existing strict default; no catalogue
selection, threshold or quantity is changed to fit this limit.

## Numerical and missing-data contract

Reuse `wind.py::polar_wind_components`, `PolarLonLatGrid` and the existing paired
`polar_proj.py::_sample_piece` path. Do not copy their equations into a second
production implementation. The execution order is:

1. Bind the actual U/V identities and selected native support.
2. Use the existing operation preparation to collocate where required, convert
   velocity units to m/s and rotate grid-basis inputs to physical east/north.
3. Sample both components in one paired `_sample_piece` call on the same target,
   weights and **joint finite-source mask**, not independent component masks.
4. Apply the retained basis rotation at the target point using
   `target.radial_bearing`, before public dimension renaming.
   Keep named axes/labels exactly aligned; do not broadcast a second angular axis.
5. Retain only the requested scalar result. Calling the existing two-result helper
   must not export or force evaluation of the unused result.

For local terminal-forward bearing `alpha`, clockwise from north:

```text
radial     = u_east * sin(alpha) + v_north * cos(alpha)
tangential = u_east * cos(alpha) - v_north * sin(alpha)
```

Radial is positive **outward**. Tangential is positive **clockwise in both
hemispheres**, not automatically cyclonic. Use the endpoint bearing, not launch
azimuth. Preserve the existing Earth model, continuous centre and source/centre
time association. Moving the target does not subtract storm translation.
This is a basis change of Earth-relative wind, not storm-relative velocity.

At radius zero, both components are NaN and their status is existing code4
(`undefined_vector_origin`), even if source sampling itself succeeds. Reuse
`attach_quality`: validity/ring coverage/full-ring eligibility reflect that
undefined value. Keep the joint interpolation-support fraction and geometry-map
evidence separate; do not label the origin unmapped merely because direction is
undefined. Speed, native U/V and scalar origin values remain unchanged.

Positive-radius values keep existing strict missing/unmapped/edge rules and valid
physical zeroes. There is no gap filling, smoothing, extrapolation or motion
subtraction. Missing/misaligned bearing evidence fails; no launch-angle fallback.
Keep the existing cache, chunking, bounded task/resource controls and lazy arrays.
Separate requested component jobs may reuse geometry/weight plans; there is no
new sampled-array cache or performance/memory-ceiling promise.

## Outputs, provenance and compatibility

Keep C7 source/product filenames and one dataset per source/product. Each selected
alias is a data variable with existing named axes:
`time`, any retained native vertical/member axes, `radius`, `azimuth`.
Its coordinate/provenance mapping comes from the same bound layout as other polar
results. No changes to uncropped/regional model-grid schemas or CROCO support.

Reuse the helper's `units="m s-1"`, outward/clockwise long name,
`wind_reference_frame="earth"`, `vector_basis="terminal_forward_geodesic"` and
`origin_policy="undefined_at_zero_radius"`. Do not assign an eastward/northward
CF standard name to these components or invent another standard name.
Job `basis="earth"` describes prepared inputs; output direction is documented by
`vector_basis`, the selected method and the long name, not mislabelled east/north.

Reuse existing per-field quality suffixes, ancillary links, component-option/
numeric-type records, preparation/rotation facts, selected levels, source clock,
centre time, sampling reports and run provenance. Record joint-stencil semantics
explicitly on the new results, plus the public binding's experimental status.
There is no new manifest or required FrameIt reader.

Capabilities/editor-schema choices must agree with validation. Describe
experimental/polar-only/strict/atmospheric limits through the existing
capability limits and canonical docs; do not introduce a registry to describe two
methods. Existing `wind_speed` and all absent-new-method requests retain behavior.
Both NetCDF and sharded Zarr must reopen with ordinary readers without FrameIt.
Compression, precision, overwrite, atomic publication and chunk/shard policies
are unchanged.

Task16 later names per-group results explicitly when multiple vertical groups
would otherwise collide in one dataset. Its checker must retain independent
numerical/coordinate/mask assertions, using actual aliases/descriptors rather
than guessing from a universal `vrad` name. For matching strict preparation,
`hypot(vrad, vtan) == speed` is checked where all are finite; it does not make
the origin defined or replace independent sign/bearing checks.

## Existing boundaries and future implementation scope

| Existing file | Necessary responsibility after design/plan approval |
|---|---|
| `src/frameit/core/configuration.py` | Method choices, active product/model/format/policy diagnostics, capabilities and authoritative schema generation. |
| `src/frameit/schemas/config-v3.schema.json` | Regenerated editor asset; no hand-maintained parallel rules. |
| `src/frameit/processing/requests.py` | Share existing two-input preparation/admission with speed where appropriate; preserve C3/selection/identity guards and reject invalid active products. |
| `src/frameit/processing/polar/sampling.py` | Validate the new methods' effective paired strict options on metadata before reads. |
| `src/frameit/processing/polar/polar_proj.py` | Paired sampling, existing rotation helper, origin/quality/provenance, selected alias only. |
| `src/frameit/processing/derived/wind.py` | Read/reuse the numerical helper; no equation, unit, sign, frame or existing speed change. |
| Existing configuration/CLI/operation/grouped/polar tests, plus a small new regression module | Real selection, failure, ordinary-reader and independent numerical cases. |
| Canonical configuration/output/polar/scalar-vector pages and annotated reference YAML | Exact method syntax, admission, sign/frame/origin/missingness and optionality. |

No writer redesign, tracker, geometry algorithm, optional-dependency change,
new numerical diagnostic, or producer/fixture migration belongs in this increment.
Keep all25pre-existing dirty paths byte-exact; in particular do not consume their
partial catalogue/checker/benchmark/example conversions in the core commit.
Any required frozen-core boundary beyond the listed responsibilities must be
demonstrated, not silently expanded.

## Acceptance required before a public-binding handoff

All items below are **future checks**, not results from drafting this document.

1. TDD structural/admission tests: each method separately/both; custom aliases;
   qualified inputs and unchanged C3 rejection; native inputs not exported;
   unused declarations with polar dependencies absent; active model-grid/FA/ocean/
   renormalize/mismatched-option requests fail at actionable paths before payloads.
   Generated schema and CLI capabilities agree. No published v2 converter.
2. Independent cardinal values for `u=3, v=4` at bearings0/90/180/270degrees:
   radial `[4,3,-4,-3]`, tangential `[3,-4,-3,4]`, absolute tolerance1e-12m/s
   for binary64 synthetic arithmetic. Preserve existing numerical tests/tolerances,
   including terminal-versus-launch leakage and hemisphere/dateline cases.
3. Use actual known weights `[.1,.2,.3,.4]` with U missing at weight.2 and V
   missing at weight.3: joint support is.5, not minimum separate support.7.
   Strict value is NaN with missing-source status2. Check zero-weight missingness,
   all-missing, valid zeroes, edge geometry and origin NaN/status4/eligibility.
   Reuse the existing real-weight test pattern, not a mocked sampler.
4. Compact end-to-end real NetCDF and GRIB inputs through v3 preparation/sampling,
   fixed and continuously moving centres, grouped sparse/reversed/singleton levels
   and unit/basis conversion. Fresh ordinary NetCDF/Zarr readers check independent
   values, metadata, all quality links, source/centre clocks, axes and storage.
   Compare source bytes; payload guards prove excluded samples stay unread.
5. Request one component alone: no other component, speed or internal-only U/V in
   output. Add the other component/base fields and confirm retained values do not
   change. Existing native U/V and speed controls remain unchanged, including
   their origin values and existing supported renormalization behavior.
6. Keep current configuration, operation, grouped, polar, numerical wind/coverage
   and CROCO support regression assertions. Run a named connected lane, baseline-
   relative Ruff and diff-check. Exact commands are fixed in the later approved
   implementation plan; no exploratory full Task16 diagnostic.
7. Strict Sphinx/publication/live desktop+narrow text checks for affected pages;
   independent bounded review before a focused local implementation commit.
   No standalone screenshot/image/plot checks; the two PNG smoke cases remain
   only inside required unfiltered suites.

## Concise scientific method record and approval gate

- Quantity/method/status: outward radial and clockwise tangential components of
  atmospheric Earth-relative wind; retained numerical operation, proposed
  **experimental public binding**, not a new stable-diagnostic claim.
- Inputs/units/grid: collocated physical east/north m/s components, one strict
  joint stencil, existing polar geometry/bearing in radians and selected native
  levels/source clocks.
- Equations/constants: the two dot products above; existing Earth model/target,
  no new empirical constants, interpolation or reference-frame motion.
- Differences from retained method: explicit opt-in aliases and product/
  admission guards only; initially strict, polar-only and non-FA atmospheric.
- Applicability/failure: admitted regional structured geometry; no current/FA
  extension, unresolved staggering/basis/metadata fails, origin undefined.
- Independent verification: retained tests are relevant evidence to rerun, not
  proof that the unimplemented public route passes; acceptance cases above add
  independent signs, native selections, joint support and reader/provenance checks.
- References/community use: existing scientific notes are in
  `docs/source/polar_projection/xESMF_proj.rst` and
  `docs/source/polar_projection/scientific_qualification.rst`
  (`wind-preparation-method`).
  Their publication/community-use evidence has not been reverified by this
  design task. Do not infer new stable-method admission from those citations.
- Remaining gaps/review: public-route implementation/verification, authoritative
  reference/community-use assessment for any stable promotion, independent
  implementation review and human scientific acceptance remain unresolved.

The design approval selects these expression/admission semantics; it does not
certify scientific validity or authorize unrelated Task16 changes. Prepare and
obtain review of the implementation plan before editing code.
No installation/environment repair, benchmark campaign, production/HPC run,
source-data change, whole-Task16 diagnostic or runtime implementation was performed
to draft this design.

Docs: no user-facing impact from this design-only commit because it changes only
internal design/state outside `docs/source`; public method/configuration/schema/
default/output/installation behavior is unchanged.
