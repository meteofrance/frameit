# CROCO regional support views — bounded design

Status: proposed design, not implemented or scientifically qualified.
Base: `63431908c64bc72fd6e8beaa6ee2a2a93fce7f8c`.
The maintainer approved option1 **for a bounded design** on2026-11-16.
The technical choices below are proposals for approval, not prior agreements.
Implementation planning begins only after approval of this document.

## Intent and observed boundary

Let the existing CROCO example export independently cropped native fields and
their original sigma support in one ordinary-reader dataset. This belongs in
FrameIt because cropping, required support and output assembly are already its
responsibility; researchers should not repair an unmergeable product downstream.

The retained diagnosis observes a3×3rho crop, a U view retaining3×7rho support
and a V view retaining7×3rho support. Formatting calls different extents `y_rho`
or `x_rho`; the final exact merge correctly rejects them. After the separately
committed index-metadata repair, the rho/Earth example instead reaches a `zeta`
coordinate/data-variable role conflict. Input-provided native indices also expose
that role boundary in internal support assembly. These are unresolved engineering
gates, not evidence that field locations or the scientific transform must change.

Evidence: `task-16-metadata-fixes-checks.md` and the retained independent
`task-16-three-core-independent-diagnosis.md` / `task-16-metadata-review-01.md`.
The latter two are internal review artifacts, not published scientific references.

## Approaches and selected direction

1. **Retain separately owned support views — selected for design.** Keep existing
   field and support samples, qualify their conflicting coordinate identities,
   and preserve explicit links. More helper data, less numerical/boundary risk.
2. **Trim support to minimal native windows — not selected.** Smaller products,
   but introduces additional index-window and edge decisions.

No support trimming, global grid, extra product files, new YAML switch, dependency,
diagnostic, current method, depth calculation or writer redesign is proposed.
Do not align, pad, interpolate or discard a support array to make merging succeed.
Existing declared crop-edge padding remains; this design adds no missing samples
or padding to reconcile views.

## Proposed output contract

### Ownership and stable names

Keep one field dataset per source/product and the existing flat/grouped field
names. A view belongs to its inventoried horizontal grid/trajectory and selected
representation, not to a field's request order or alias. Reuse the identity facts
already resolved by `output_grid_layout`; do not introduce a second grid registry.
Resolve names against the complete source inventory before product filtering.
Do not hash scientific payloads or the first selected snapshot to choose names.

For a **regional native face view**, use `<base>_support_<owner>` for cross-grid
helper variables and their axes. `<owner>` is the existing stable inventoried
horizontal-view identity, including trajectory identity where present. The full
token is retained; counters, selected-field lists and shape-only identity are
forbidden. For example, the U view's bathymetry becomes `h_support_<U-owner>` on
its own `y_rho_support_<U-owner>, x_rho_support_<U-owner>`. Retain matching source
coordinate/index auxiliaries and actual support geography under that namespace.
Copying these labels does not resample the arrays.

Two details prevent collisions from merely moving elsewhere:

- An inherited primary rho axis in an independently cropped face view uses
  existing C7 identity qualification: U's `y_rho_<U-owner>` and V's
  `x_rho_<V-owner>`. Use these names even if one particular crop happens to match
  the scalar window. Native face axes `x_u/y_v` keep their existing names unless
  inventory already requires qualification. Canonical rho fields retain
  `y_rho/x_rho`. This is a disclosed dimension-name correction, not just renaming
  `h/zeta`.
- A sigma coordinate cannot retain one global `formula_terms` string while
  referring to different support views. The cropped face's complete sigma/formula
  closure therefore uses its owner namespace, including its sigma dimension/
  coordinate, selected stretching curve and referenced helper variables. Preserve
  the same labels, original indices, attributes and numerical equation; rewrite
  only actual variable/dimension links. Rho-grid fields, including native W stored
  on `s_rho`, retain their original `s_rho/s_w` identity.

Do not deduplicate separate owner namespaces just because their values happen to
match. This keeps names filter/order-stable and avoids eager equality reads.
Existing sharing within the same owning view remains subject to strict identity.
Uncropped mixed-grid naming stays unchanged. Rho/Earth results use their existing
rho target view, not a native face support namespace.

These presentation aliases MUST NOT bypass C3's existing rejection of unequal
level selections sharing an underlying output-axis identity. Keep that selection
compatibility identity separate from owner-qualified stored names. No new way to
request unequal levels, no implicit vertical alignment and no relaxed guard.

### Coordinate roles and formula meaning

Normalize roles before the merge that currently fails, not only in the writer.
An explicitly selected field such as `zeta` remains a data variable in its owning
product view. A support-only alias remains a coordinate; native-index auxiliaries
remain coordinates. Internal dependency views use one consistent role for each
actual field/index. A name must never be both a data variable and a coordinate
across operands belonging to the same view.

Reconcile roles only for the same bound native identity and selected mapping;
keep exact comparison of values and scientific attributes. Differing owned views
get separate aliases before assembly. Do not take arbitrary first metadata or use
`compat="override"`, outer alignment, or a blanket coordinate reset.

Every `formula_terms`, geography, bounds and ancillary link must name the actual
retained variable. Each sigma formula's `s` and `C` terms use that closure's selected
vertical axis; its `eta`/`depth` remain the **original rho support**, with their
actual dimensions, source indices, geography, time dependence and units.
Do not advertise these as physical depths at U/V face locations or infer a
face-depth interpolation. A reader can inspect the original equation/support;
automatic physical-depth decoding for arbitrary face-aware applications is not
promised. If correct links require a new numerical/scientific interpretation,
stop and return that choice to the maintainer.

### Reporting, storage and migration

Extend the existing `frameit_output_coordinates` record with the support-owner
mapping: original native grid/coordinate identity, owning view, stored names,
dimensions and formula links. Reuse the current JSON-attribute/provenance path;
no new manifest or mandatory reader. Planned field dimensions and actual product/
status descriptors must agree with the same layout.

This is an output-schema correction. Document the qualified face/sigma/support
names and how ordinary readers follow links, rather than promising scripts will
work unchanged. Explicit computation/writer chunk keys must use actual exported
dimensions and be validated accordingly; unknown keys remain errors. Preserve
compression, precision, sharding, overwrite and atomic-publication contracts.
No configuration syntax/default or method changes are proposed.

## Narrow implementation boundary after approval

| Existing boundary | Necessary responsibility |
|---|---|
| `io/netcdf_utils.py::_selected_netcdf` | Consistent selected-field/index/support roles; preserve bound lazy views. |
| `processing/derived/wind.py::execute_source_operations` | Same ownership/role policy at result merge; calculations/preparation unchanged. |
| `core/coupled.py::_regional_dataset` / `run_native_sources` | Keep crop windows and existing padding; carry ownership through exact assembly. |
| `io/netcdf_export.py::output_grid_layout` / `format_model_grid` | One inventory-stable namespace, complete support closure and rewritten links. |
| `core/preflight.py::describe_model_grid_output` and resource descriptions; `processing/requests.py` C3 check | Same planned/stored dimensions; preserve the pre-qualification selection guard. |
| Affected output/reader/operation tests and canonical output/ocean guidance | Compatibility, independent-reader and failure evidence; no fixture weakening. |

Reuse existing dictionaries and link-renaming helpers. Local helper placement is
the implementer's call; no generic support framework or unrelated adapter rewrite.
Generic merge semantics, `prepare_croco_currents`, vector masks, collocation,
rotation, time association and source scientific metadata remain unchanged.

## Required acceptance before claiming a fix

- The two original portable CROCO nodes in `docs/test_repository_examples.py`
  must complete their unchanged finite-current, NaN, W-zero and sigma-location
  assertions. They are not cleared by isolated support-only tests.
- Add compact nonconstant rho/U/V fields and compare each exported sample and
  geography against its own original indices. Check both level orders `[0,2]`/
  `[2,0]`, singleton and true `s_w` cases; never infer W location from its name.
- Cover fixed/moving centres, an interior shift and declared crop-edge padding.
  Check each retained support stripe, source-index mask, formula closure and
  time-dependent `zeta`; structural holes must not become physical zeroes.
- Cover explicit `zeta` co-export and a real input-provided native-index coordinate
  through loading, operation assembly and output reopening, not only executor
  fixtures. Wrong values, labels, definitions and unresolved owners still fail.
- Adding, reordering, aliasing or filtering fields must not rename another
  retained field/support view. C3 unequal shared-axis selections must still fail
  before payload reads, including when presentation names differ.
- Reopen NetCDF and sharded Zarr with ordinary readers in fresh processes without
  FrameIt. Check values, dtype, missingness, native indices/metadata, all links,
  descriptors and explicit chunk/shard handling. Existing uncropped output guards
  must keep their schemas and assertions.
- Run the existing focused CROCO/native-reader/output/grouped/time/metadata guards,
  strict Sphinx/publication and live text-only affected-page checks. Obtain fresh
  independent review before a focused local implementation commit.

All development checks use `frameit_env` Python3.13. Preserve the25existing dirty
paths, all prior failure evidence and source bytes. No installations/environment
repairs, production/HPC runs or standalone image/plot/screenshot checks. The two
PNG smoke cases stay only within their required unfiltered suites. Do not consume
Task16's single post-freeze full diagnostic during design or exploratory fixes.

## Cost, limits and approval gate

Retained rho support can remain much larger than the exported face window, and
separate formula namespaces can duplicate metadata/helper storage. Keep arrays
lazy; do not materialize a full array merely to label or compare ownership. This
is not a performance improvement and promises no new memory ceiling.

No new diagnostic or stable-method claim is made. Numerical-copy agreement,
formula-link correctness and engineering integration are separate from real-data
scientific qualification. Broader producer, installed-wheel, Task16/full-branch
and human-acceptance gates remain open.

Docs: no user-facing impact from this design-only change because it is an internal
proposal outside `docs/source`; no command, runtime, schema or published page has
changed. Canonical compatibility guidance belongs with the eventual implementation.
Approve this design before implementation planning; approving option1 alone did
not approve these detailed names or authorize code changes.
