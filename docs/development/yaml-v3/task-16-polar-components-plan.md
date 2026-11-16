# Explicit Polar Wind Components Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> inline, preserving the agreed execution method. Steps use checkbox (`- [ ]`)
> syntax. One fresh independent review covers the completed bounded change before
> its local implementation commit; do not commit partial milestones.

**Goal:** Explicitly request the retained outward radial and clockwise tangential
wind calculations without changing base fields, existing speed or other methods.

**Architecture:** Extend existing scalar `derived` choices and selected-operation
admission. Reuse current paired strict interpolation and `polar_wind_components`
after sampling, then publish only the requested alias through existing polar
quality/provenance/writer contracts.

**Tech Stack:** Python3.13 in `frameit_env`; current xarray/Dask, ecCodes,
xESMF/ESMF, pyproj, NetCDF4 and sharded Zarr v3. No dependencies/setup changes.

**Spec:** `task-16-polar-components-design.md`, approved by the maintainer
on2026-11-16 at base9931f5859dbc9db3b57443c167f8b71943728c7a.
This plan is not yet approved for implementation.

## Global Constraints

- Methods are `radial_wind` and `tangential_wind`, distinct `u`/`v` source
  references and arbitrary existing-safe scalar output aliases.
- Initial admission is polar-only, strict paired finite-source interpolation,
  atmospheric AROME GRIB/NetCDF or Meso-NH NetCDF. FA/ocean/renormalize and
  incompatible component settings fail when active; no silent fallback.
- Preserve outward radial, clockwise tangential in both hemispheres, terminal-
  forward bearing, Earth-relative velocity and undefined zero-radius direction.
- Preserve current source unit/basis/rotation/collocation evidence and guards;
  no new scientific assumptions, formula, geometry, units fallback or motion
  subtraction. Source level/time selections and masks stay unchanged.
- Keep native copies, existing `wind_speed` (including supported renormalization),
  model-grid transforms, W, CROCO ownership, C3 and all strict merges unchanged.
- Unselected definitions do not activate dependencies, inputs or diagnostics.
  Selecting U/V does not select any derived result; selecting one component
  does not select its sibling or speed.
- Keep all25pre-existing dirty paths byte-exact; no catalogue/checker/benchmark/
  example/old-fixture conversion in this increment. Preserve all prior evidence.
- No install/environment repair, production/HPC run, benchmark campaign,
  standalone screenshot/image/plot check or Task16 post-freeze full diagnostic.
- Experimental public binding only; no stable-method promotion or invented
  publication/community-use verification. Design approval is not scientific sign-off.

## Review Focus

1. Independent U/V holes must use one joint stencil, not speed's minimum of
   separately sampled support — Task2 joint/public-weight cases.
2. A declared but filtered-out method must not require polar dependencies; implicit
   model-grid selection must fail, not silently remove a result — Task1 cases.
3. Geometry launch angles and target terminal bearings can differ; origin NaNs
   must not poison scalar/speed values or become physical zero — Task2 cases.
4. Qualified aliases, multiple native axes, unequal selectors and changing source/
   centre clocks must retain exact identity and selected payloads — Tasks1/2.
5. Every new result/quality/provenance name must survive ordinary NetCDF/Zarr
   reopening without changing actual base/speed arrays — Task2 compatibility cases.

---

## File map and interface boundaries

Create only `src/frameit/testing/numerical/test_v3_polar_components.py` for new
fixtures/regressions. Reuse `scene`/`configuration` from `test_v3_polar.py`,
`write_messages`/decoder observation patterns from `test_v3_grib_reads.py`,
`grouped_document` from `test_grouped_requests.py`, and the real-weight pattern
in `test_polar_coverage.py`. Do not modify those shared fixture helpers.

| File | Responsibility |
|---|---|
| `src/frameit/core/configuration.py` | Choices, active structural admission, honest capability limits and schema generation. |
| `src/frameit/schemas/config-v3.schema.json` | Regenerate from `configuration_schema()`, preserving generator key order. |
| `src/frameit/processing/requests.py` | Bind new methods as actual atmospheric two-input operations; preserve native/C3/temporal checks. |
| `src/frameit/processing/polar/sampling.py` | Validate effective paired strict options before payloads. |
| `src/frameit/processing/polar/polar_proj.py` | Joint sampling, reuse existing rotation, result-only quality/provenance. |
| `src/frameit/testing/numerical/test_v3_cli.py` | Update only exact capability/schema expectations if required; retain unrelated guards. |
| `docs/source/user_guide/configuration_file.rst`, `output_files.rst`, `docs/source/polar_projection/xESMF_proj.rst`, `docs/source/task_guides/scalars_and_vectors.rst`, `docs/source/_static/configuration-reference.yaml` | Canonical implemented syntax, scope, experimental status and semantics. |

Read/reuse but do not change `derived/wind.py::polar_wind_components`,
`coverage.py`, `PolarLonLatGrid`, writer/resource/reader protocols or scientific
fixture values. No new registry, paired-output type or public switch.

Command prefix, from this worktree:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env
```

Use new ignored plan-owned logs/JUnit; do not overwrite earlier evidence.

### Task 1: Bind explicit scalar methods and reject unsupported active requests

**Files:** configuration.py `_source`, `_products`, `capabilities`,
`configuration_schema`; requests.py `bind_source_operations`;
polar/sampling.py `bind_polar_plan`; generated asset; new test module.

**Interfaces:** Keep `resolve_schema(raw, *, base_dir=None)`'s three-item return
and existing `configuration_schema()`/`capabilities()` dict shapes.
Keep `bind_source_operations(source, request, conf, *, representations=None,
required_inputs=())` and `bind_polar_plan(source, request, binding, conf, *,
radial_step_km=None)`. Task2 consumes unchanged bound dictionaries, with new
method strings in `operation_plans`, explicit input/selection/preparation facts
and per-input `polar_options`; no new result/registry type.

- [ ] **Step1 — Write structural/optionality RED tests.** Add
  `test_explicit_components_schema_and_capabilities`,
  `test_active_component_product_and_source_admission`,
  `test_unused_component_declaration_does_not_activate_polar`.
  Parameterize each method and both, custom aliases and arbitrary source IDs.
  Assert unchanged authored input, current resolved/export/input-reference shapes,
  both distinct input references, no implicit U/V/speed/sibling exports.
  Active model-grid selection (including `model_grid: true`), FA/ocean source,
  missing/same/ambiguous inputs and result/source collision fail with the owning
  method/product/source path. Inactive new definitions with absent input names
  and polar backends must not affect a valid native-only request or create outputs.
- [ ] **Step2 — Observe RED.** Run with the declared environment prefix:

  ```bash
  python -m pytest -q src/frameit/testing/numerical/test_v3_polar_components.py::test_explicit_components_schema_and_capabilities src/frameit/testing/numerical/test_v3_polar_components.py::test_active_component_product_and_source_admission src/frameit/testing/numerical/test_v3_polar_components.py::test_unused_component_declaration_does_not_activate_polar --tb=short
  ```

  Expect current unsupported method errors in the positive cases; preserve
  negative controls, not schema/import/fixture mistakes.
- [ ] **Step3 — Extend selected-method admission, no numerical implementation.**
  Add the two choices to `V3_CHOICES["derived"]`. Use existing selected product
  rosters to reject active model-grid/source-format combinations; do not reject
  mere unused declarations or auto-filter default product fields. Generalize
  the existing actual wind-input/atmosphere/collision checks, not every operation
  into a wind diagnostic. Preserve units, collocation, selectors, native input
  dependencies and metadata-only failure behavior. Capability limits explicitly
  say experimental, strict, polar-only, atmospheric, non-FA.
- [ ] **Step4 — Add bound-option/identity RED cases.** Add
  `test_component_pair_options_are_strict_and_compatible` and
  `test_component_grouped_binding_preserves_identity_and_guards`.
  Real metadata binding with backend payload guards must accept matching
  effective options and grouped source references. Reject renormalize,
  differing input interpolation/sampling/threshold settings, noncontinuous input,
  temporal/basis/vertical incompatibility, missing rotation and source collisions.
  Compare effective `kind`, `interpolation`, `missing_data_policy`,
  `min_valid_weight_fraction`, `sampling`, **not** `kind_origin` provenance.
  Matching data meaning with different metadata origins must remain valid.
- [ ] **Step5 — Observe RED and validate those metadata-only contracts.** Run:

  ```bash
  python -m pytest -q src/frameit/testing/numerical/test_v3_polar_components.py::test_component_pair_options_are_strict_and_compatible src/frameit/testing/numerical/test_v3_polar_components.py::test_component_grouped_binding_preserves_identity_and_guards --tb=short
  ```

  Expect missing new-method option/guard behavior, not payload reads. Reuse
  the existing bound geometry/pair checks and compare the
  two effective option records in `bind_polar_plan`. Failure must precede actual
  payload decoding. Leave existing speed's per-input preparation/options intact.
  No relaxation of C3 or result-unit/clock/field identity.
- [ ] **Step6 — Regenerate the editor schema and observe GREEN.** After
  implementing these rules, generate the asset from `configuration_schema()`
  with the existing JSON order and run:

  ```bash
  python -m pytest -q src/frameit/testing/numerical/test_v3_polar_components.py::test_explicit_components_schema_and_capabilities src/frameit/testing/numerical/test_v3_polar_components.py::test_active_component_product_and_source_admission src/frameit/testing/numerical/test_v3_polar_components.py::test_unused_component_declaration_does_not_activate_polar src/frameit/testing/numerical/test_v3_polar_components.py::test_component_pair_options_are_strict_and_compatible src/frameit/testing/numerical/test_v3_polar_components.py::test_component_grouped_binding_preserves_identity_and_guards src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_v3_cli.py --tb=short
  ```

  Expected: all named cases pass, generated asset equals its authoritative
  generator, original guards remain. This is a metadata checkpoint, not a public
  execution handoff or commit; Task2 must implement and verify the runtime.

### Task 2: Execute paired polar sampling, preserve scientific outputs and document

**Files:** polar/polar_proj.py `execute_source_polar`; same new regression
module; canonical pages/reference above.

**Interfaces:** Consume Task1's unchanged jobs/options. Keep
`execute_source_polar(internal, source, binding, conf, centres, *, plan_cache=None,
output_formatter=None)` returning `(Dataset, report_dict)`.
Reuse `_sample_piece(source, names, pair, geometry, conf, method, plan_cache,
source_geometry_cache)` and `polar_wind_components(u, v, bearing)` unchanged.
Publish selected aliases through existing per-source polar descriptors/writers;
other products and method results remain unchanged.

- [ ] **Step1 — Write real-path and numerical RED cases.** Add:
  `test_explicit_component_cardinal_signs_and_origin`,
  `test_explicit_components_use_joint_source_support`,
  `test_explicit_component_terminal_bearing_and_motion`,
  `test_explicit_component_selected_reads_and_grouped_levels`,
  `test_explicit_components_round_trip_and_base_speed_invariance`.
  All exercise v3, not only the old helper. Parameterize one component/both,
  NetCDF/sharded Zarr, fixed/continuous centres and source/group selections.
  Low-level independent cardinal assertions use explicit bearing inputs:

  ```python
  np.testing.assert_allclose(radial, [4., 3., -4., -3.], rtol=0, atol=1e-12)
  np.testing.assert_allclose(tangential, [3., -4., -3., 4.], rtol=0, atol=1e-12)
  assert origin_is_nan and origin_status == 4 and origin_full_ring_valid == 0
  assert speed_at_valid_origin == 5.
  ```

  Bearings are0/90/180/270degrees, U=3m/s and V=4m/s. Do not assume public launch
  azimuth equals terminal bearing. Public readbacks independently compute the
  endpoint bearing from centre/target geography (e.g. inverse geodesic
  back-bearing+180degrees), then use scalar dot products, not the production
  rotation helper. Retain existing published-bearing/leakage tolerances.
- [ ] **Step2 — Pin joint masks and optionality in the failing public path.**
  Use real explicit xESMF weights `[.1,.2,.3,.4]` in the existing controlled
  operator test pattern: U missing at weight.2 and V at weight.3 gives joint
  support.5, not minimum separate support.7; strict status2/valueNaN.
  Add a public paired-sampling case whose actual native weights are inspected
  independently to catch an accidental independent-component execution loop.
  Include zero-weight NaNs, all-missing, positive-radius real zeroes, outside/
  edge geometry, origin and different metadata origins.
  Adding a selected component must not change separately requested U/V, scalar
  or speed values/support/status. No implicit sibling or speed, including when
  an unused declaration is present.
- [ ] **Step3 — Observe runtime RED.** Run:

  ```bash
  python -m pytest -q src/frameit/testing/numerical/test_v3_polar_components.py::test_explicit_component_cardinal_signs_and_origin src/frameit/testing/numerical/test_v3_polar_components.py::test_explicit_components_use_joint_source_support src/frameit/testing/numerical/test_v3_polar_components.py::test_explicit_component_terminal_bearing_and_motion src/frameit/testing/numerical/test_v3_polar_components.py::test_explicit_component_selected_reads_and_grouped_levels src/frameit/testing/numerical/test_v3_polar_components.py::test_explicit_components_round_trip_and_base_speed_invariance --tb=short
  ```

  Require actual runtime/missing output/
  wrong joint support failures after Task1 admission; retain complete evidence.
  A schema/fixture error is not an execution regression test.
- [ ] **Step4 — Reuse the paired numerical route.** For only the two new
  methods, prepare/promote the actual numeric component views using existing
  continuous-field rules, then call `_sample_piece` once with both names and
  their pair tuple, common strict settings and target geometry. Do not enter the
  current independent per-input sampling loop for those jobs. Rotate using the
  helper with exact named `rr/theta_deg/time` target bearing before public
  renaming; retain the requested tuple element only. No equation duplication or
  new vector transport. Existing speed/native branches stay behaviorally intact.
- [ ] **Step5 — Carry existing quality/provenance correctly.** Reuse joint
  support/status and geometry; override the new component's origin status to4.
  Reuse `attach_quality` and existing suffixes. Keep geometry map/support distinct
  from undefined direction. Preserve `wind_reference_frame="earth"`,
  `vector_basis="terminal_forward_geodesic"`, existing `origin_policy`, m/s and
  outward/clockwise long names; no false east/north standard name.
  Record `polar_support_definition="joint_finite_component_stencil"`,
  actual `polar_component_options`, numeric/preparation/selection/clock/bearing
  facts and `frameit_method_maturity="experimental_public_binding"`.
  No new public metadata-reader requirement. Missing/misaligned positive-radius
  bearing fails, not a fallback to launch angle.
- [ ] **Step6 — Observe GREEN with independent readers and immutable inputs.**
  Run:

  ```bash
  python -m pytest -q src/frameit/testing/numerical/test_v3_polar_components.py src/frameit/testing/numerical/test_polar_wind.py src/frameit/testing/numerical/test_polar_coverage.py src/frameit/testing/numerical/test_v3_polar.py --tb=short
  ```

  Expected: all pass. Fresh ordinary reader subprocesses import no FrameIt.
  Check exact dimensions/units/metadata/quality links, native level order and
  source/centre clocks; compare values with independent expressions at justified
  tolerances. Source bytes unchanged. New-method addition leaves base/speed
  controls—including existing speed renormalization—unchanged.
- [ ] **Step7 — Update canonical guidance and annotated reference.** Explain
  both scalar methods/aliases and input preparation; explicit combined-product
  filtering; strict joint masks; polar/non-FA atmospheric admission; clockwise/
  outward signs, endpoint bearing, Earth-relative motion, origin and experimental
  status. Keep existing references/method evidence, URLs and low-level numerical
  APIs. Do not claim stable-method validation or alter the25preserved paths.

## Final verification, review and focused local commit

- [ ] Run the following named connected lane with the declared environment prefix
  and new JUnit/full-output destinations. Expected: all pass, no new/waived
  failures, actual backend and original scientific assertions retained:

  ```bash
  python -m pytest -q \
    src/frameit/testing/numerical/test_v3_polar_components.py \
    src/frameit/testing/numerical/test_configuration_v3.py \
    src/frameit/testing/numerical/test_v3_cli.py \
    src/frameit/testing/numerical/test_v3_operations.py \
    src/frameit/testing/numerical/test_v3_polar.py \
    src/frameit/testing/numerical/test_grouped_requests.py \
    src/frameit/testing/numerical/test_polar_wind.py \
    src/frameit/testing/numerical/test_polar_coverage.py \
    src/frameit/testing/numerical/test_v3_netcdf_reads.py \
    src/frameit/testing/numerical/test_v3_grib_reads.py \
    src/frameit/testing/numerical/test_v3_fa_reads.py \
    src/frameit/testing/numerical/test_v3_outputs.py \
    src/frameit/testing/numerical/test_croco_support_views.py \
    docs/test_repository_examples.py::test_croco_mnh_portable_example_runs_both_current_representations \
    --tb=short
  ```

  This is not Task16's single post-freeze full or real-producer qualification.
- [ ] Require baseline-relative Ruff zero new findings and `git diff --check`.
  Compare all25preserved paths/copies with their retained manifest and confirm
  protected numerical helper, geometry, coverage equations and writer code have
  no changes. Review exact task-only diff/claims before freezing.
- [ ] With the declared environment prefix, run:

  ```bash
  sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-polar-components-01
  python docs/check_publication.py build/docs-preview/yaml-v3-polar-components-01
  python -m unittest discover -s docs -p test_check_publication.py
  ```

  Expected: strict build/publication exit0 and13units pass. Inspect affected
  rendered text in the connected GUI at
  desktop and320px; retain server/tab/URL/restart in ignored handover notes.
  No standalone screenshot/image/plot checks. Report any GUI disconnect honestly.
- [ ] Obtain one fresh independent spec/quality review of the bounded implementation.
  Resolve blocking findings with focused RED→GREEN checks and rerun the named
  connected lane. Do not re-review routinely or consume the whole Task16 full.
- [ ] Stage only verified task paths, inspect the staged tree/status and commit
  locally after review. No push/merge or evidence/worktree deletion. Record exact
  commands/results, commit ID, scientific/compatibility limits and retained
  preview. Freeze this core handoff before resuming Task16 producer conversions.

## Plan self-review and execution gate

Coverage: expression/active guards/optionality/schema/capabilities → Task1;
qualified selectors/prepared-grid checks → Task1 with Task2 real reads;
shared masks/signs/bearing/origin/continuous centres → Task2Steps1–6;
metadata/readers/unchanged speed/base/storage → Task2Steps5–6;
canonical docs/strict publication/live preview/preservation/review → Task2Step7
and final gate. All five review-focus classes have named tests.
Existing signatures and dictionary handoffs are preserved. New test helper
placement and idiomatic local factoring are implementation choices, not new APIs.

The maintainer approved the design, not this plan. Ask for plan review before
implementation and preserve inline execution (one final fresh bounded review).
Docs: no user-facing impact because this plan/status is internal and no runtime,
schema asset, scientific method/default or published page has changed.
