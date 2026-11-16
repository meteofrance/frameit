# CROCO Owned Support Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task, following the agreed inline workflow.
> Steps use checkbox (`- [ ]`) syntax for tracking. One fresh independent review
> covers the completed bounded change before its local commit.

**Goal:** Make the original CROCO regional native and rho/Earth examples retain
their selected fields and owned support in one correctly linked dataset.

**Architecture:** Normalize bound coordinate roles before the existing strict
merges. Extend the existing output layout for regional model-grid presentation,
splitting face support namespaces without changing source arrays or crop windows.
Use its same dimensions in preview, resource checks and actual publications.

**Tech Stack:** Python3.13 in `frameit_env`, existing xarray/Dask, NetCDF4 and
sharded Zarr v3 readers/writers, pytest and Sphinx. No dependency changes.

**Spec:** `task-16-croco-support-design.md`, approved at commit
`f8e9c879c7e977cbe44d53b8d7df372390821c1b`. Approval covers implementation planning;
wait for the maintainer's review of this plan before writing implementation code.

## Global Constraints

- Keep one field dataset per source/product and the existing flat/grouped field names.
- Preserve native samples, units, sigma labels/indices/order, masks, clocks, W
  location, crop windows and existing declared edge padding.
- Keep `join="exact"` / `compat="identical"`; no support trimming, reconciliation
  padding, implicit alignment, interpolation, physical-depth calculation or new method.
- Names use complete inventoried horizontal-view/trajectory identity, before
  field filtering; no payload hashes, counters or selected-field-list identities.
- Keep uncropped schemas, canonical rho names, polar presentation and C3's
  underlying shared-axis level-selection guard unchanged.
- Keep arrays lazy; retain support even when larger than the field crop. No new
  memory/performance guarantee, public switch, framework, registry or manifest.
- Preserve all25pre-existing dirty paths byte-exact. Do not change their fixtures,
  caller conversions or historical evidence; stop for a lead ruling if necessary.
- No installs, environment repair, production/HPC run, standalone image/plot/
  screenshot check or Task16 post-freeze full diagnostic.

## Review Focus

1. An input-provided index must load and round-trip as a coordinate with its
   authored attributes, not merely pass an executor-only test — Task1.
2. Equal-shaped cropped views must not share names merely by local positions;
   moving support and boundary holes must retain original samples — Task2.
3. A qualified face sigma axis must not bypass C3's earlier selection rejection,
   and alias/filter/order changes must not rename retained views — Task2.
4. Model-grid support aliases must not leak into polar or uncropped layout calls,
   especially when both products are requested — Task2.
5. Support-only dimensions must be valid explicit chunk/shard targets; unknown
   keys and dangling formula/ancillary links must remain actionable errors — Task2.

---

## File map and shared interfaces

Create only `src/frameit/testing/numerical/test_croco_support_views.py` for new
regressions/local fixtures. Reuse `vector_scene` from
`src/frameit/testing/numerical/test_croco_vectors.py`, `DatasetResources` from
`src/frameit/io/loader.py`, and
`configuration(tmp_path,sources,*,region=None,products=None,output=None)` from
`src/frameit/testing/numerical/test_v3_regions.py`, with source declarations
constructed in the new module.
Use the existing ordinary-reader subprocess pattern, not a legacy2.1document.
Do not modify shared fixtures or existing scientific assertions.

Modify existing boundaries only:

| File | Responsibility |
|---|---|
| `src/frameit/io/netcdf_utils.py` | `_selected_netcdf` sample/group role consistency. |
| `src/frameit/processing/derived/wind.py` | `execute_source_operations` bound result roles, not calculation/preparation. |
| `src/frameit/io/netcdf_export.py` | Inventory-stable presentation map and variable-level support formatting. |
| `src/frameit/core/coupled.py` | Pass regional presentation context and retain unchanged crop views. |
| `src/frameit/core/preflight.py` | Planned dimensions and complete applicable storage/computation axes. |
| `docs/source/user_guide/output_files.rst` | Canonical schema correction, support meaning, reader/chunk adaptations. |

Read but do not change `processing/requests.py`'s C3 check, polar formatters,
generic internal merge rules, `prepare_croco_currents`, source time association
and the old acceptance fixtures. The ocean guide already links the canonical
model-grid naming section; put the new explanation there instead of modifying
the preserved dirty `ocean_netcdf.rst` or repeating it in other pages.

Keep existing load/executor/formatter return shapes and signatures. The only
signature extensions are:

```python
output_grid_layout(source, *, regional=False) -> dict
describe_model_grid_output(source, binding, product, *, regional=False) -> None
```

The default layout remains the current layout. The regional option only adds
the approved CROCO face presentation. Its per-grid facts retain `dimensions`,
`horizontal_identity`, `geography`, `coordinates` and `original_coordinates`;
add `support_views` mapping each original support name to its owning identity,
original native-grid/name, stored name and dimension/link mapping. Do not add
top-level entries that existing code would mistake for grid facts.

`format_model_grid(dataset, grid_id, source, layout, *, field=None) -> xr.Dataset`
consumes those facts and extends the existing `frameit_output_coordinates` entry
with the same `support_views` record. Exact nested helper placement remains an
implementation choice; use existing dictionaries and link-renaming helpers.

Python command prefix, from this worktree:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env
```

Commands below follow that prefix. Use new ignored `task-16-croco-support-*`
logs/XML, not earlier metadata/design evidence.

### Task1: Preserve bound coordinate roles through real loading and operations

**Files:** Modify `_selected_netcdf` (`netcdf_utils.py:278–520`) and
`execute_source_operations` (`wind.py:359–434`); create the new regression module.

**Interfaces:** Consume bound source field/grid identities, descriptors and
vertical-coordinate metadata. Produce the existing `{grid_id: Dataset}` user
and internal views with consistent roles; Task2 consumes these native arrays.
No new public function or result type.

- [ ] **Step1 — Write failing real-file regressions.** Add
  `test_croco_supplied_index_round_trip` and
  `test_croco_zeta_coexport_and_transform_roles`. Parametrize both writers and
  index orders `[0,2]`, `[2,0]`; keep `zeta` explicitly requested with native rho
  scalars and a declared rho/Earth current transform. In a new tiny file supply
  `s_rho_source_native_index=("s_rho",[0,1,2], attrs)` with
  `attrs={"units":"1","long_name":"authored native index","note":"retained"}`.
  Set the local copy's `mask_rho[3,2]=0` to exercise the existing joint-mask rule.
  Fresh ordinary-reader subprocess assertions include:

  ```python
  np.testing.assert_array_equal(out.s_rho_source_native_index, indices)
  assert out.s_rho_source_native_index.attrs == attrs
  assert "zeta" in out.data_vars
  assert "s_rho_source_native_index" in out.coords
  np.testing.assert_array_equal(out.zeta, native.zeta)
  assert out.u.attrs["current_reference_frame"] == "earth"
  assert not any(n == "frameit" or n.startswith("frameit.") for n in sys.modules)
  ```

  Check source bytes unchanged, expected rotated finite values `u=-4`, `v=2`
  at `atol=1e-12`, the existing joint-mask/boundary NaNs and no extra base fields.
  Also add `test_croco_role_normalization_preserves_conflict_rejection`: corrupt
  one bound index/label/attribute in fresh merge operands and require strict
  failure, not metadata adoption from the other operand.
- [ ] **Step2 — Observe RED.** Run `python -m pytest -q
  src/frameit/testing/numerical/test_croco_support_views.py --tb=short`.
  Confirm the supplied-index internal merge and explicit `zeta` result merge
  failures, not a schema/import error. Retain raw evidence; no fixture workaround.
- [ ] **Step3 — Normalize roles at their existing bound boundaries.** In
  `_selected_netcdf(files,binding,source,resources,*,engine,chunks)` use actual
  inventoried coordinate/vertical metadata to keep index auxiliaries coordinates.
  Keep scientific dependency fields consistently data variables internally and
  explicitly exported fields data variables in product operands. Apply the same
  exported-role roster before `execute_source_operations` merges a result with
  user data. Do not classify solely by a name suffix, reset every coordinate or
  change native selection/metadata. Existing bound identities plus unchanged
  strict comparisons must reject real differences.
- [ ] **Step4 — Observe GREEN.** Run the new module plus
  `test_metadata_preservation.py` and
  `test_v3_netcdf_reads.py::test_internal_native_index_preserves_existing_coordinate_attributes`.
  Require real file round trips and all original conflict controls to pass.
  This closes only role gates; do not claim the native cropped example passes.
  Record this inline checkpoint; do not commit unreviewed/intermediate work.

### Task2: Retain separately owned regional support and all output consumers

**Files:** Modify `netcdf_export.py:174–464`, `coupled.py` model-grid layout/
assembly and `_regional_dataset`, and `preflight.py:1152–1194,1278–1323`.
Extend the same new test module and the canonical output naming section.

**Interfaces:** Consume Task1 native datasets. Produce the extended regional
layout specified above; preflight, resource validation, formatting and published
descriptors use exactly that map. C3 and polar continue consuming the default
unqualified layout, independently of model-grid presentation aliases.

- [ ] **Step1 — Write layout/selection regressions before changing code.** Add
  `test_croco_regional_layout_is_inventory_stable` and
  `test_croco_face_aliases_preserve_c3_selection_guard`. Use the real binder with
  backend payload guards. Check U's inherited `y_rho_<owner>`, V's
  `x_rho_<owner>`, complete `<base>_support_<owner>` formula closure and canonical
  rho names. Compare retained names across field additions, order/filter changes
  and qualified request aliases. Matching selections bind; unequal grouped
  selections sharing the pre-alias axis still fail before reading payloads.
  Add `test_croco_default_layout_does_not_inherit_model_grid_aliases`: default and
  polar calls stay unchanged even with regional model-grid facts available.
- [ ] **Step2 — Observe RED for those named tests.** Use `python -m pytest -q`
  followed by their exact nodes in the new module and `--tb=short`.
  Expect unsupported `regional`/missing namespaces initially; preserve C3 rejection.
- [ ] **Step3 — Extend the layout and its call sites together.** Implement the
  two optional signatures above. Derive owners from existing complete-inventory
  `horizontal_identity`/trajectory facts. Preserve all default facts.
  `bind_source` and `bind_sources` pass authored regional context to model-grid
  descriptions; model-grid runtime uses the same regional map. Keep the existing
  default layout for polar runtime and `processing/requests.py` C3 validation.
  Do not infer presentation mode from whichever field or source record is first.
- [ ] **Step4 — Write failing numerical/integration regressions.** Add
  `test_croco_owned_support_round_trip` and
  `test_croco_moving_edge_support_preserves_native_samples`. Use local copies of
  `vector_scene`; prescribe nonconstant `u=1000*t+100*k+10*j+i`,
  `v=2000+1000*t+100*k+10*j+i`, `h=20+j+i`, `zeta=t+0.01*j+0.001*i`.
  Retain units/metadata, valid zeroes and distinct field-local NaNs; keep separate
  native `w=0` on `s_rho` and `tracer_w` on its existing `s_w`.
  For the diagnosed interior fixture, copy the existing coupling helper's
  `+0.0065`latitude/`+0.007`longitude shifts, fixed centre `(-20,60)` and
  2km X/Y widths without editing that helper. Moving centres use
  `(-20,60)` then `(-19.9905,60.0095)` on the two source times. The edge fixture
  uses a centre inside every admitted footprint whose existing window needs
  padding, not an out-of-footprint centre that must instead fail.
  Parametrize NetCDF/Zarr, sparse/reversed/singleton levels, fixed/moving centres
  and existing edge padding. Compare each decoded field/geography/support stripe
  by its exported original native indices against independent NumPy indexing of
  its source, including non-domain holes. Require rho3×3, U-support3×7 and
  V-support7×3 for the retained diagnosed interior case; do not trim them.
  Check every formula target, sigma/stretching/index order, metadata and source
  bytes in subprocess readers, not merely successful serialization.
- [ ] **Step5 — Observe the real assembly failure.** Run those two nodes and
  `docs/test_repository_examples.py::test_croco_mnh_portable_example_runs_both_current_representations`.
  The native case must reproduce the known exact support-axis collision before
  formatter changes; record any different cause rather than weakening a test.
- [ ] **Step6 — Format support per variable, not by a blanket dataset rename.**
  Extend `format_model_grid` to split primary and support axis mappings while
  retaining underlying lazy arrays, original auxiliaries and encoding. Reuse
  the existing dependency walk and `_rename_coordinate_links`; namespace the
  complete owner sigma/formula closure. Preserve the current `_regional_dataset`
  crop/index/missingness behavior and carry its actual support view to formatting.
  Rebuild raw variables when one old dimension needs distinct primary/support
  names; do not allow xarray to align them on construction. Leave the final strict
  merge, current preparation and equation untouched. Record ownership in the
  existing output-coordinate metadata, without claiming physical face depths.
- [ ] **Step7 — Pin reporting and explicit storage dimensions.** Add
  `test_croco_owned_support_preview_and_chunk_dimensions` and
  `test_croco_owned_support_rejects_unknown_axes_and_links`. Compare preflight,
  actual product/status field dimensions and metadata. Apply explicit chunks/
  shards to a discovered owned support axis, verify actual stored extents, and
  reject an invented axis. Check mixed model-grid/polar plans retain independent
  naming, without running an unrelated polar qualification campaign. Ambiguous
  owner/collision/dangling-link fixtures must fail actionably, not drop support.
  Extend `describe_v3_resources`' applicable dimensions with the regional
  layout's support axes, including axes absent from primary field dimensions.
- [ ] **Step8 — Observe GREEN and document compatibility.** Run the whole new
  module and both unchanged original portable CROCO nodes. Require their finite/
  NaN/W/sigma assertions to execute. Update `output_files.rst` with owned naming,
  source-index/formula links, larger helper footprint and explicit exported chunk
  keys; keep rho support distinct from physical face depth. Do not edit the
  25preserved paths or original fixtures/assertions to obtain success.

## Final verification, independent review and local commit

- [ ] Run this connected command with the declared prefix, adding a new JUnit
  destination and retaining the complete output:

  ```bash
  python -m pytest -q \
    src/frameit/testing/numerical/test_croco_support_views.py \
    src/frameit/testing/numerical/test_metadata_preservation.py \
    src/frameit/testing/numerical/test_v3_operations.py \
    src/frameit/testing/numerical/test_v3_netcdf_reads.py \
    src/frameit/testing/numerical/test_v3_outputs.py \
    src/frameit/testing/numerical/test_v3_regions.py \
    src/frameit/testing/numerical/test_v3_polar.py \
    src/frameit/testing/numerical/test_grouped_requests.py \
    src/frameit/testing/numerical/test_native_extraction.py::test_native_samples_are_cell_bounding_and_keep_source_basis \
    src/frameit/testing/numerical/test_native_extraction.py::test_boundary_faces_are_nan_without_extrapolation \
    src/frameit/testing/numerical/test_croco_vectors.py::test_croco_current_joint_support_never_fills_missing_or_erases_zero \
    src/frameit/testing/numerical/test_croco_vectors.py::test_croco_analysis_rejects_unresolved_inputs \
    docs/test_repository_examples.py::test_portable_nemo_arome_example_with_preceding_hour_inputs \
    docs/test_repository_examples.py::test_croco_mnh_portable_example_runs_both_current_representations \
    --tb=short
  ```

  Expected: no new/waived failures, all new cases and both original CROCO nodes
  pass. Existing uncropped mixed-grid schema, selected-read, optionality, C3,
  time and metadata assertions remain. Report all actual failures separately;
  this named lane is not the Task16 full diagnostic or producer qualification.
- [ ] Run baseline-relative Ruff on changed Python paths and `git diff --check`;
  require zero new lint findings, not a claim that baseline debt disappeared.
- [ ] Run `sphinx-build -q -W --keep-going -b html docs/source
  build/docs-preview/yaml-v3-croco-support-01`,
  `python docs/check_publication.py build/docs-preview/yaml-v3-croco-support-01`
  and `python -m unittest discover -s docs -p test_check_publication.py`.
  Inspect affected HTML text in the live GUI at desktop/narrow320px widths;
  keep the loopback preview available and record owned process/URL/restart in
  ignored handover notes. No screenshot or standalone figure/image check.
- [ ] Freeze only task-related paths with original25path preservation evidence;
  obtain one fresh independent spec/quality review of this bounded change.
  Resolve blocking findings and rerun affected checks. Do not reopen C3, convert
  other Task16 callers or declare broader scientific/human acceptance.
- [ ] Stage only verified task paths; review staged diff/status and commit locally
  after review. Report commit ID, exact commands/results, output-name migration
  and remaining gates. Never push/merge. Record the resulting frozen handoff for
  unfinished Task16 conversion; its single post-freeze full remains unused here.

## Plan self-review

Coverage: roles/provided-index I/O → Task1; owner/axis/formula names and stable
selection identity → Task2Steps1–3,6; nonconstant fixed/moving/edge samples and
native W → Steps4–6; reader/schema/storage/provenance → Steps4,7–8; docs,
independent review and preservation → final gate. All five review-focus classes
have named tests. Default layout is explicitly separate from regional presentation;
no implementation API mismatch or new scientific decision is left to infer.

This plan records future work, not executed tests or implementation clearance.
Docs: no user-facing impact from this plan-only change because the plan/status
record are internal, outside `docs/source`. The existing inline execution method
is preserved; ask the maintainer to review this plan before implementation.
