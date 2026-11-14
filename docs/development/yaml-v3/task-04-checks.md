# Task 04 — metadata-backed field and level binding

Internal, portable evidence; not published user guidance.
Base: `9ad6f19b7f7180528bfb40ffc328f53cdb570569`.
Python **3.13.18**, Conda `frameit_env`, selected checkout via `PYTHONPATH`.
Independent review closed both Important findings: spec PASS, quality APPROVE,
no new Critical/Important fix breakage. The reviewed handoff is frozen in `STATE.md`.
This record includes the approved pre-review FA record-evidence follow-up.

## Scope and scientific limits

- Added an explicit post-inventory binder in `processing/requests.py` and
  `core/preflight.py`. Existing inventory entry points remain inventory-only.
- Added request/unit/support and representation fixtures in the two claimed test
  modules. Existing numerical functions, fixtures and assertions are unchanged.
  `test_native_extraction.py` and `utils/units.py` were not edited.
- No scientific arrays are read or converted. Only already inventoried coordinate
  metadata is selected/converted. There is no interpolation, remapping, masking,
  new diagnostic, provider priority, additional file discovery or wider clock.
- Public field-selection/configuration documentation, STATE/checklist,
  orchestration and adapter integration remain lead-owned.
- The worker's evidence below predates the lead's authorized native-stack repair.
  The worker made no environment change or native-abort probe. Post-repair lead
  checks are recorded separately below; general native qualification remains open.
  No production import reordering or release/finalizer workaround was introduced.
- No full v3 execution, CLI, output writer, ordinary-reader reopening, scientific
  validation, transform implementation or human acceptance is claimed.

## Binding entry points and Task05 handoff

```python
core.preflight.bind_source(
    conf, name, *, representations=None, required_inputs=()
) -> binding

processing.requests.bind_requests(
    source, request, *, representations=None, required_inputs=()
) -> binding
```

`bind_source` consumes an **already populated** source entry at
`conf.simulation_parameter["request_plan"]["sources"][name]` and
`conf.source_requests[name]`. Missing inventory fails actionably.
The pure `bind_requests` does not mutate either argument. `required_inputs`
is an internal list of operation inputs to promote from `record_inventory`,
not a public selector or permission to discover inputs. It does not resolve
the operation's scientific eligibility.

No existing production caller automatically invokes the new binder yet.
Task05 must call it after `inventory_source` / `prepare_sources`, before payload
loading. `prepare_sources` creates independent children and parent snapshots;
bind a child before reading it, and deliberately propagate the bound source/request
snapshot to its parent. Do not call `prepare_sources` again and assume the
newly constructed children retain an earlier binding.

Existing numerical signatures and all five original request-helper function
bodies are preserved:

- `normalize_requests`, `selected_native_indices`, `build_group_ds`:
  `io/netcdf_utils.py` uses all three.
- `io/grib_utils.py` and `io/fa_utils.py`: normalization/building.
- `io/surfex_utils.py`, `tracking/pressure_centroid_inputs.py`: physical positions.
- Legacy preflight: normalization/physical positions and numerical validation.

Those numerical groups are **not** the v3 declaration mapping. Do not feed a
v3 declaration to `normalize_requests` or use its permissive missing-level
handling/backend tolerance as public v3 validation.

### Exact result shape

```text
binding:
  status: bound | pending_method_binding
  products:
    <product>:
      <field-name>:
        field_id: inventoried scientific-array identity
        category: 2d | 3d
        records: [bound_record, ...]
  dependencies:
    <required internal array name, whether exported or not>: same field descriptor
  records: [original candidate-pool scientific/support records actually selected]
  warnings: [plain-English unit warnings]
  deferred_checks: [unresolved method/representation/eligibility checks]

bound_record:
  <all original record fields and locator, including both original indexer maps>
  selection_grid_id: native grid ID or explicitly supplied destination grid ID
  source_positions: [native payload-axis storage positions, in required read order] | null
  vertical: null | {
    dimension: applicable representation's vertical dimension,
    coordinate: its label coordinate name | null,
    positions: [positions on that representation's stored axis],
    source_native_indices: [original zero-based positions on that representation],
    values: [selected existing labels in exported units] | null,
    source_units: observed coordinate units | null,
    units: effective coordinate units | null,
    units_origin: input | user_assumption | unknown,
    coordinates: {
      <vertical label/bounds/dependent coordinate name>:
        dimensions, values, attributes, dtype, <retained original metadata>
    }
  }
```

`selection_grid_id` plus `vertical` describes the bound level representation.
Scientific basis rotation, field-unit transforms and derived-method eligibility
are **not** asserted resolved by this map.
Product records describe output selection. Ancillary dependency records describe
native internal read support, which may include explicitly required neighbours.
One name may occur in both maps with different positions; neither map replaces
the other. Direct non-ancillary operation inputs retain their selector semantics.

Additive FA record contract:

```text
raw FA record (in records / record_inventory / bound raw records):
  <unchanged field_id, name, grid_id, decoded clock/cycle, locator and other fields>
  native_descriptor: deep copy of that provider/sample's existing versioned FA descriptor

synthetic cube record:
  <unchanged identities and cube locator>
  # no raw native_descriptor; resolve each part through matching raw records
```

`fields[field_id].native_descriptor` remains an inventory summary only. It is
not evidence of another selected record's eligibility, labels, shape or clock.
Consumers must preserve the record-local descriptor, including through promotions
and request-map copies; never replace it from the merged field summary.

On `bound`, `bind_source`:

1. Stores the map in both `conf.source_requests[name]["binding"]` and the source
   plan's `requests.binding`, and also exposes `source.field_binding`.
2. Replaces `source.records` with selected candidate-pool records, regenerates
   chronological `source.files`, updates file relevance and clears checked
   provider conflicts. Promoted providers are included, not merely original files.
3. Updates a source-local config's `input_files` and the plan's input inventory.
4. Records warnings in the plan and logs them.

On pending support, the diagnostic map is available as `source.field_binding`,
but both executable `requests.binding` slots remain `None`. Original inventory
records/files/conflicts are retained: pending dependencies do not authorize a
final file-relevance decision. Failed rebinding clears old binding clearance
and `field_binding` before raising.

### Native NetCDF slice instructions

- Require `requests.binding` to be non-`None` and `status == "bound"`; a diagnostic
  pending map is not permission to execute.
- Consume `binding.products["model_grid"][name]["records"]` and required
  `binding.dependencies`, using their original locators. Do not rediscover a
  stream or pass the original unbound file list to an old full-file reader.
- Keep product exports separate from internal dependency reads. A product may
  select `[5,0]` while its ancillary requires `[5,6,0,1]`. Do not deduplicate
  these descriptors by field name, export the neighbour union, or reapply the
  output selector to trim internal support.
- Apply payload `locator.indexers` only to payload dimensions. For native 3D
  data, use `source_positions` as a **list** on the native vertical dimension,
  including a length-one selection. Do not squeeze or renumber.
- Use the actual source `grid_id` to resolve coordinate dependencies and matching
  owning provider/sample provenance. Use full `coordinate_indexers` only on
  matching coordinate dimensions; static payloads may have empty `indexers`.
- `vertical.coordinates` contains selected/converted coordinate metadata.
  Replacing coordinate labels must not multiply, relabel or otherwise change
  the physical field's values/units. Preserve original grid metadata separately.
- A destination binding's source positions are method support, not destination
  positions. The method must perform its approved transform before applying the
  destination selection. That implementation belongs to Task08.

### Representation planner/fixture input

Only an explicitly requested representation may supply a destination:

```text
representations[product][field_name][actual_native_grid_id] = {
  grid_id: destination_grid_id,
  grid: {dimensions: {dim: size, ...}, coordinates: {name: descriptor, ...}},
  sampling: requested_sampling,
  source_positions: {destination_storage_position: [required_native_positions, ...]}
}
```

Model-grid `transforms[].sampling` and polar `polar_options[field].sampling`
are consulted independently. A model-grid W-to-mass request does not remap
native/polar W. Missing destination metadata stays pending; a missing selected
destination level, missing/out-of-range source support, contradictory sampling,
or loss of a 3D axis fails before writing.
The tests supply coordinates/support only, not transformation implementations.

## Identity, availability and coordinate boundaries

All promotion comes from the closed `record_inventory`. The binder recomputes
identity/category and selected-time/cycle/native-member support. It does not
treat an initially empty `provider_conflicts` list as clearance. Different fields
sharing a requested name fail with their definitions/providers and no qualified
selector. Duplicate declarations/resolved level requests fail.

After actual level/support selection, every surviving scientific provider conflict
fails. An unrequested GRIB level's competing providers do not prohibit an
unambiguous selected level. Every selected level must exist at every required
selected sample/member. Metadata equivalence never exempts scientific duplicates.

Coordinate metadata is looked up through each record's **actual owning grid**,
not a source-wide name table. NetCDF provenance must match provider path,
coordinate variable, clock, decoded time/cycle, full coordinate indexers and
coordinate-local payload indexers. Empty provider sample lists are unavailable.
Scientific arrays registered as xarray coordinates remain scientific support,
with candidate records, availability/provider checks and forbidden payload reads.
Shared native vertical dimensions also require the selected original indices and
compatible labels on their array support; unrelated unselected labels are not
used to reject a valid subset.

Known dimensions and one-dimensional vertical metadata establish category, not
array rank, time or axis length. Singleton vertical dimensions remain 3D.
Competing vertical label coordinates/dimensions are not silently chosen.

GRIB axes use only the selected field's candidate messages, not horizontal grid
geometry or another field's levels. Pressure ordering is decreasing; other admitted
axes are increasing, matching the existing cfgrib coordinate convention.
Read-only evidence was the installed cfgrib `dataset.py`: pressure
`stored_direction="decreasing"` and coordinate construction by sorted field labels.
This does not qualify the native decoder or infer packet ordering as a vertical axis.

### FA record-local evidence boundary

The lead approved an additive extension to the frozen inventory: each raw FA
record retains its own descriptor before field summaries merge. The producer
does not attach the first raw descriptor to a synthetic cube record.

Raw eligibility uses that actual record's descriptor and owning grid. Missing/
invalid evidence, inconsistent native identity, unknown/contradictory shape,
blocked eligibility, and contradictory descriptor clocks/native headers fail
with provider/sample context. No field-summary fallback or alternate-provider
choice is allowed.

Cube parts resolve from the closed pool using their name, actual file, decoded
time and cycle. Their local descriptors feed existing `fa_cubes.cube_layouts`
checks: native header bounds, observed labels, unique increasing associations,
declared mass/interface sampling and original native indices. Both axis and
level caches distinguish FA records, even on a shared field/grid identity.
Different selected samples can therefore bind their actual existing labels;
an excluded later file cannot overwrite selected eligibility or labels.

Selected cube locators retain selected raw record names in requested order.
Selected raw support is promoted and every surviving scientific provider conflict
is rechecked. An unselected raw level's competing provider is not read or chosen.
Overlapping cube/raw requests still fail. All original grid/time/cycle/locator
identities and selected-inventory boundaries are preserved.

This closes the first handoff's merged-descriptor evidence gap, without expanding
FA admission. All FA maps still defer Task07 source interpretation and decode-time
scaling eligibility; executable `requests.binding` remains `None`. Synthetic
metadata fixtures do not qualify real FA/native execution.

## Level/unit rule and evidence

- One source selector is applied independently to every requested representation
  and direct 3D operation input. Ancillary internal support instead follows the
  declared native stencil. Omission retains each requested axis's full stored
  order/length.
- Lists preserve order. Inclusive index ranges use original nonnegative zero-based
  positions. Inclusive value intervals preserve grid order; endpoints need not be
  labels. Duplicate/unavailable/resolved-duplicate/ambiguous requests fail.
- Physical selection reuses existing adapter evidence and COMODO's one-based
  inclusive ranges. Unknown physical ranges fail; positive heights do not prove
  a physical range. Only inventoried original-index metadata can justify a range
  extending beyond an already selected axis; the binder does not fabricate that
  provenance from default positions.
- Compatible coordinate units reuse `utils.units.UNITS` / `convert_units`.
  Scaling uses binary64 coordinate arithmetic and updates labels/bounds/units/dtype.
  Source metadata remains unchanged. Same-scale unit spellings are equivalent.
- Value selection across different known numeric unit scales/families requires
  explicit units. Index-only selection does not.
- Absent/blank source units plus requested units: assume the stored numbers already
  use requested units, without rescaling; warn in map/logs and record
  `user_assumption` plus coordinate assumption metadata.
- Both absent: warn, retain unknown units, do not invent them. Needed independent
  physical/support checks can still fail.

For a stored floating label `x` and compatible scale factor `f`, define
`ulp_dtype(x)` as the larger distance to adjacent finite representable values
in the inventoried coordinate dtype; at a finite extreme use the inward neighbour.
Integer storage contributes zero storage-rounding error.

```text
coordinate_error =
    0.5 * ulp_storage(x) * abs(f) + 4 * ulp_float64(converted_x)

explicit-list match:
    abs(converted_x - request) <= coordinate_error + 4 * ulp_float64(request)
```

Intervals are closed, allowing `coordinate_error` at either boundary. No absolute
or relative backend tolerance is inherited. Every candidate in the error band is
counted: more than one is an error, never a closest-level choice. Two requests
matching one stored position are duplicates. Export actual converted stored labels,
not the requested number rounded into the output.

Evidence: stored float32 `0.1` is approximately `0.10000000149011612`.
Its half-ULP is approximately `3.72529e-9`, which covers that storage roundoff.
The compatible Pa-to-hPa factor scales the storage band by `0.01`.
Requests `0.100001` against that float32 label and `0.10000000001` against
float64 `0.1` are rejected. Adjacent float64 labels within the band are ambiguous.
The largest finite float32/float64 labels do not produce infinite tolerances.
`850 hPa` selects stored `85000 Pa`; units-only selection converts all labels/bounds.
No field payload is read or altered in any of these checks. This is numerical
agreement at the stated coordinate-roundoff bound, not bitwise conversion identity
or general scientific validation. The technical rule was independently reviewed
as part of Task04; this is not human scientific sign-off.

## RED evidence

Raw logs are retained in the ignored task workspace, not committed machine state.
All commands below use `PYTHONPATH="$PWD/src" conda run -n frameit_env`.

| Log | Test targets / observed RED |
| --- | --- |
| `task-04-red-initial.txt` | Required command below: **51 failed**, missing `bind_source`, before production code. |
| `task-04-red-support.txt` | `test_v3_binding_final_support`, `test_v3_grib_binding_metadata`, `test_v3_storage_roundoff_boundary`: **9 failed, 4 passed**, one numeric overflow warning. One failure was an incorrect fixture assumption that normalized scalar `files` was a list; corrected, not counted as a production defect. |
| `task-04-red-fa-dtype.txt` | `test_v3_fa_binding_metadata` plus `test_v3_vertical_units[bounds]` and `[bounds_units]`: **6 failed, 3 passed**. |
| `task-04-red-fa-provider.txt` | `test_v3_fa_binding_metadata`: **7 failed, 2 passed** before cube/raw selection/provider binding. |
| `task-04-red-boundaries.txt` | Storage-boundary node plus representation `[destination_loses_axis]`: **2 failed, 1 passed**, one overflow warning. |
| `task-04-red-axis-support.txt` | Final-support node plus units `[blank_source]`: **3 failed, 8 passed**. |
| `task-04-red-inventory-gate.txt` | `test_v3_binding_requires_inventory`: **1 failed**, incidental `KeyError` instead of actionable inventory failure. |
| `task-04-red-fa-provenance.txt` | FA `[sample_specific_evidence]`: **1 failed**, incorrectly bound two samples from merged descriptors. |
| `task-04-red-physical-range.txt` | Field/level `[invalid_physical]`: **1 failed**, default positions were incorrectly treated as original-index evidence for an out-of-range physical end. |

The first GREEN had four fixture/message-matching failures: two case-sensitive
error regexes and two synthetic metadata records without their matching coordinate
provider provenance. Those fixtures were made complete; no scientific-read,
provider-conflict or original-index assertion was removed. The first handoff
temporarily narrowed the FA label fixture to one provider after discovering the
merged-descriptor gap. The approved follow-up below restores all two-time fixtures
and replaces the obsolete blanket deferral with actual record-local evidence.

### Pre-review FA correctness follow-up — RED/GREEN

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py::test_v3_fa_record_evidence_from_inventory --tb=short
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py::test_v3_fa_record_evidence_from_inventory src/frameit/testing/numerical/test_request_selection.py::test_v3_fa_binding_metadata --tb=short
```

The first command was observed **15 failed** before production edits
(`task-04-followup-red-record-evidence-valid.txt`). The initial fixture attempt
omitted mandatory cube field declarations; it is retained separately and is not
counted as intended RED. A second-raw-sample eligibility control was then added.
An additional missing-label case was observed RED for an error lacking its owning
file/sample (`task-04-followup-red-local-label-context.txt`) before that context
was added:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q 'src/frameit/testing/numerical/test_request_selection.py::test_v3_fa_record_evidence_from_inventory[missing_cube_label]' --tb=short
```

The second command above is **27 passed**, no warnings, 0.82 s
(`task-04-followup-green-record-evidence.txt`).

The 17 producer→inventory→binder cases use compact metadata responses at the
existing `inspect_fa` boundary, not a replacement inventory or binder. Actual
`_fa_source_inventory`, `inventory_source`, time selection and binding run.
Scientific FA requests are forbidden. They cover:

- Two files with different observed cube labels; selectors bind per sample.
- A requested label missing only in the second file.
- Raw/cube blocked eligibility in the first file and raw blocked eligibility
  in the second, without first/last descriptor or cache assumptions.
- A later excluded file with bad shape/eligibility or different labels.
- Missing raw/part descriptors or cube labels; contradictory native ID, clock,
  shape and header, with owning file/sample errors.
- Selected/unselected scientific provider conflicts.
- Poisoning the merged summary without changing any owning record's evidence.

Assertions check actual selected labels/native indices/raw record names,
provider/time/cycle/grid/zone/freshness identity, unchanged candidate records,
no widened inventory or output directory, and retained Task07/scaling gates.
The ten prior pure-metadata FA cases keep their meaningful checks and now use
two time/provider records, not narrowed one-file fixtures.
All original pre-task tests/helpers remain AST-identical.

## Pre-review verification (before fix round 1)

Run from the repository root. All commands below exited **0** except the explicitly
pre-existing Ruff diagnostics noted under self-review.

### Exact required command

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py::test_v3_field_and_level_binding src/frameit/testing/numerical/test_request_selection.py::test_v3_vertical_units src/frameit/testing/numerical/test_grid_representations.py::test_v3_representation_level_binding
```

**55 passed**, no warnings, 3.64 s.

### All Task04 checks

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_grid_representations.py -k v3 --tb=short
```

**101 passed, 68 deselected**, no warnings, 4.09 s. Required 55 and the 27 FA
follow-up checks are subsets.
The 68 include 20 numerical nodes separately run below and 48 unchanged public-v2
nodes awaiting Tasks15–16; no skip marker/assertion change was introduced.

### Delivered Task03 inventory/read guards

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env env FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" python -m pytest -q src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_netcdf_assembly.py src/frameit/testing/numerical/test_grib_lifecycle.py -k v3 --tb=short
```

**123 passed, 69 deselected, 19 existing warnings**, 20.51 s.
The approved local fixture was read-only; no data were downloaded.
Actual backend scientific-read guards, including arrays registered as coordinates
and contradictory bounds, remain delivered and unchanged.

### Delivered v3 schema and Task01 checks

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_hpc_execution.py -k 'not test_invalid_execution_schema and not test_exclusive_run_ownership_and_early_no_clobber and not test_concurrent_cli_attempts_spawn_and_sync_export_exactly and not test_batch_overrides_dry_run_does_not_claim_output and not test_cli_processing_failure_never_marks_completed and not test_incomplete_tracking_is_explicit_and_strict_policy_fails and not test_cancellation_and_same_root_exclusion' --tb=short
```

**342 passed, 12 deselected, 4 existing warnings**, 7.04 s.
Same frozen milestone selection as Task03; all 326 v3 schema checks are included.
The excluded public-v2 execution/CLI families remain future-dependent, not passed.

### Applicable numerical request, extraction, FA, tracker and SEA callers

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_request_selection.py::test_selection_preserves_native_values_and_metadata \
  src/frameit/testing/numerical/test_request_selection.py::test_physical_domains_are_axis_specific \
  src/frameit/testing/numerical/test_request_selection.py::test_invalid_comodo_domain_fails \
  src/frameit/testing/numerical/test_request_selection.py::test_positive_mnh_heights_do_not_establish_physical_domain \
  src/frameit/testing/numerical/test_request_selection.py::test_ordinary_grib_axes_have_no_vertical_halo \
  src/frameit/testing/numerical/test_request_selection.py::test_source_native_index_retains_original_positions_after_subset \
  src/frameit/testing/numerical/test_request_selection.py::test_surface_group_copies_global_metadata \
  src/frameit/testing/numerical/test_request_selection.py::test_native_index_and_value_selections_remain_distinct \
  src/frameit/testing/numerical/test_request_selection.py::test_physical_filter_does_not_renumber_explicit_indices \
  src/frameit/testing/numerical/test_native_extraction.py \
  src/frameit/testing/numerical/test_fa_cubes.py::test_hybrid_units_reference_pressure_and_invalid_columns \
  src/frameit/testing/numerical/test_fa_cubes.py::test_epygram_optionality_and_native_contradictions \
  src/frameit/testing/numerical/test_pressure_centroid_mnh.py::test_native_log_pressure_and_affine_wind_interpolation \
  src/frameit/testing/numerical/test_pressure_centroid_mnh.py::test_validated_native_columns_use_brackets_without_sorting \
  src/frameit/testing/numerical/test_pressure_centroid_mnh.py::test_legacy_unordered_height_records_keep_sorting_semantics \
  src/frameit/testing/numerical/test_pressure_centroid_mnh.py::test_bilinear_native_cells_area_wrap_and_strict_support \
  src/frameit/testing/numerical/test_pressure_centroid_mnh.py::test_formula_height_pressure_units_and_level_halos \
  src/frameit/testing/numerical/test_pressure_centroid_mnh.py::test_raw_staggered_wind_rotation_and_surface_basis \
  src/frameit/testing/numerical/test_pressure_centroid_mnh.py::test_missing_vertical_brackets_and_reference_ring_fail_explicitly \
  src/frameit/testing/numerical/test_pressure_centroid_mnh.py::test_inconsistent_sequence_units_and_frames_are_not_silently_combined \
  src/frameit/testing/numerical/test_mnh_surfex_support.py::test_surfex_sea_support_preserves_fraction_and_valid_zero \
  src/frameit/testing/numerical/test_mnh_surfex_support.py::test_surfex_explicit_unit_spelling_equivalence_and_opt_out \
  src/frameit/testing/numerical/test_mnh_surfex_support.py::test_surfex_invalid_required_support_and_metadata_fail \
  src/frameit/testing/numerical/test_mnh_surfex_support.py::test_surfex_empty_units_attribute_is_completed_from_comment \
  src/frameit/testing/numerical/test_mnh_surfex_support.py::test_surfex_stress_comment_units_are_not_interpreted_as_velocity \
  src/frameit/testing/numerical/test_mnh_surfex_support.py::test_surfex_marker_rule_never_reinterprets_croco_water_mask \
  --tb=short
```

**73 passed**, no warnings, 2.04 s. These exact node families/all parameterizations
were recorded in the ignored report before production implementation.

### Applicable assembly/import callers

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_netcdf_assembly.py src/frameit/testing/numerical/test_grib_lifecycle.py::test_discovering_grib_loader_does_not_initialize_optional_native_decoder -k 'not v3 and not test_variable_shards_preflight_companion_inventory_and_replay and not test_netcdf_layout_rejects_invalid_configuration and not test_variable_shard_wind_companion_can_live_in_another_file and not test_runner_reuses_netcdf_metadata_without_reading_fields and not test_standalone_preflight_closes_netcdf and not test_runner_only_prepares_selected_cartesian_branch' --tb=short
```

**31 passed, 33 deselected, 71 existing warnings**, 2.27 s.
The six explicitly named public-v2 families remain Tasks15–16 dependencies;
v3 inventory nodes were run in the 123-case command. No unchanged native
shutdown/abort probe was rerun.

**Distinct targeted total: 670 passed** (101 + 123 + 342 + 73 + 31).
Warnings are the already recorded NumPy/netCDF4 binary-size warning and NumPy 2.5
shape-assignment deprecations; none was suppressed.

## Self-review and remaining work

`git diff --check` passed. A `frameit_env` Python AST comparison against the base
verified **75 original top-level functions unchanged**, including all 50 original
test functions/helpers in the claimed suites and the untouched extraction suite.
The only changed original function is `_fa_source_inventory`, for the explicitly
approved additive record evidence; all other inventory/numerical functions remain
unchanged. Original first-handoff comparison was 76 unchanged before that approval.
Ruff comparison against the same base was **8 → 8** diagnostics, zero new:
seven in unchanged preflight code and one unchanged long test line. The new
request implementation/tests have zero Ruff diagnostics. A first stdin-based
verification wrapper produced no output under `conda run` and is not evidence;
the actual comparison was rerun with `python -c` and inspected.

The complete legacy-node collection is retained in the ignored workspace.
No full legacy suite was rerun: Tasks02–05 explicitly use focused milestone
checks, while public producer/CLI conversion and full integration belong to
Tasks15–16/19. No known future-dependent failure is marked passed.

Final follow-up logs use prefix `task-04-followup-`: `required-final`,
`focused-final`, `inventory-final`, `delivered-final`, `numerical-final`,
`assembly-final` and `self-review-final`, with `.txt` suffixes. Earlier RED/GREEN
logs remain retained; current counts above supersede the first handoff.

Pending work is explicit: native payload adapters and source/parent orchestration
(Task05), scientific source interpretation/decode-time scaling (Task07), actual transforms
and derived-method support (Task08), polar methods (Task09), schema/writer naming
(Task10), and public CLI/producer conversion. Task04's metadata map does not
resolve these operations. General native qualification remains separately open.
Canonical public docs, strict Sphinx/publication checks and live preview
are the lead's responsibility before the task commit.
Record-specific FA descriptors increase metadata storage with raw record count;
no large-archive memory/performance qualification was run or is inferred here.

## Lead-authorized native repair and post-repair checks

After the worker finished, the maintainer approved removing only pip
`eccodeslib 2.50.0.33` and `eckitlib 2.5.0.33`. Their recorded files were confined
to their own package/dist-info/bundled-library directories. No other installed
distribution declared a dependency on the first; only it required the second.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pip uninstall -y eccodeslib eckitlib
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pip check
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_grid_representations.py -k v3 --tb=short
PYTHONPATH="$PWD/src" conda run -n frameit_env env FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" python -m pytest -q src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_netcdf_assembly.py src/frameit/testing/numerical/test_grib_lifecycle.py -k v3 --tb=short
```

All exit 0: exactly the two approved packages removed; no broken requirements;
101 Task04 passed (68 deselected, no warnings); 123 Task03 passed (69 deselected,
19 existing warnings). These repeat covered nodes, not extra distinct passes.
No upgrade, replacement, download or environment recreation was performed.

Six fresh-process controls each exited 0: both ecCodes/pyproj import orders,
ecCodes-before-production import, unchanged legacy and v3 metadata scanners,
and direct v3 preflight. Each loaded actual native ecCodes **2.46.0** and only
Conda **PROJ 9.9.0**, without wheel ecCodes/eckit libraries. Scanner/preflight
controls retained four opened/four released handles and owned coordinate arrays,
with scientific-value access forbidden. Raw commands/child streams remain in
the session handover; portable conclusions are recorded in `STATE.md`.
These controls resolve the reproduced installed mixed-library blocker. They do
not establish general native qualification, full v3 execution, every error path,
or scientific/bitwise equivalence across decoder versions. Task19 remains open.

The lead subsequently reran the remaining delivered/numerical/assembly commands
above under the repaired environment:

| Selection | Post-repair result |
|---|---|
| Delivered schema/Task01 | 342 passed, 12 deselected, 4 existing warnings |
| Numerical request/extraction/FA/tracker/SEA | 73 passed, no warnings |
| Assembly/import | 31 passed, 33 deselected, 71 existing warnings |

Together with 101 Task04 and 123 Task03, all **670 distinct targeted checks**
were freshly rerun post-repair and passed. This is still not the full suite.
The additional existing native payload/shutdown check also passed:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env env FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" python -m pytest -q src/frameit/testing/numerical/test_grib_lifecycle.py::test_direct_grib_loading_and_native_shutdown_in_fresh_interpreter --tb=short
```

**1 passed**, no warnings, 1.32 seconds. This specific payload/control result is
not general native or scientific qualification.

### Exact unconverted request/grid public nodes

These **48** collected nodes construct public v2 documents (including their
intended-negative tests). They were not rerun or reinterpreted as successful v3
checks. Their caller-wide conversion remains Tasks15–16. Paths below are relative
to `src/frameit/testing/numerical/`.

```text
test_request_selection.py::test_schema_level_domain_and_no_implicit_wind_declaration[stored-stored]
test_request_selection.py::test_schema_level_domain_and_no_implicit_wind_declaration[physical-physical]
test_request_selection.py::test_strict_wind_pair_declarations[None]
test_request_selection.py::test_strict_wind_pair_declarations[pair1]
test_request_selection.py::test_strict_wind_pair_declarations[pair2]
test_request_selection.py::test_strict_wind_pair_declarations[pair3]
test_request_selection.py::test_strict_wind_pair_declarations[pair4]
test_request_selection.py::test_strict_wind_pair_declarations[pair5]
test_request_selection.py::test_strict_wind_pair_declarations[pair6]
test_request_selection.py::test_strict_wind_pair_declarations[pair7]
test_request_selection.py::test_strict_wind_pair_declarations[pair8]
test_request_selection.py::test_strict_wind_pair_declarations[pair9]
test_request_selection.py::test_duplicate_pair_components_fail_but_different_groups_are_distinct
test_request_selection.py::test_explicit_grid_rotation_roundtrip[coordinate]
test_request_selection.py::test_explicit_grid_rotation_roundtrip[geolocation]
test_request_selection.py::test_explicit_grid_rotation_roundtrip[mesonh_projection]
test_request_selection.py::test_mesonh_projection_yaml_parameters_roundtrip
test_request_selection.py::test_invalid_mesonh_projection_yaml_parameters[BETA-True]
test_request_selection.py::test_invalid_mesonh_projection_yaml_parameters[BETA-0]
test_request_selection.py::test_invalid_mesonh_projection_yaml_parameters[BETA-inf]
test_request_selection.py::test_invalid_mesonh_projection_yaml_parameters[RPK-None]
test_request_selection.py::test_invalid_mesonh_projection_yaml_parameters[RPK-value4]
test_request_selection.py::test_invalid_mesonh_projection_yaml_parameters[RPK-1.1]
test_request_selection.py::test_invalid_mesonh_projection_yaml_parameters[RPK--1.1]
test_request_selection.py::test_invalid_mesonh_projection_yaml_parameters[LON0-nan]
test_request_selection.py::test_projection_parameters_require_projection_method[coordinate]
test_request_selection.py::test_projection_parameters_require_projection_method[geolocation]
test_request_selection.py::test_invalid_output_selectors[cartesian-horizontal_vectors-auto]
test_request_selection.py::test_invalid_output_selectors[cartesian-horizontal_vectors-value1]
test_request_selection.py::test_invalid_output_selectors[cartesian-vertical_velocity-native]
test_request_selection.py::test_invalid_output_selectors[polar-vertical_velocity-False]
test_request_selection.py::test_output_selections_are_preserved
test_request_selection.py::test_no_auto_global_frame
test_grid_representations.py::test_real_mnh_native_faces_match_source_file
test_grid_representations.py::test_sparse_w_only_keeps_selected_mass_targets
test_grid_representations.py::test_cartesian_grid_choices_reopen_with_physical_samples[interfaces-native]
test_grid_representations.py::test_cartesian_grid_choices_reopen_with_physical_samples[interfaces-mass_earth]
test_grid_representations.py::test_cartesian_grid_choices_reopen_with_physical_samples[mass-native]
test_grid_representations.py::test_cartesian_grid_choices_reopen_with_physical_samples[mass-mass_earth]
test_grid_representations.py::test_cartesian_choice_does_not_change_real_polar_or_tracking[interfaces]
test_grid_representations.py::test_cartesian_choice_does_not_change_real_polar_or_tracking[mass]
test_grid_representations.py::test_each_file_normalizes_velocity_units_before_concatenation[native]
test_grid_representations.py::test_each_file_normalizes_velocity_units_before_concatenation[mass_earth]
test_grid_representations.py::test_native_face_geography_normalizes_each_file_before_concat
test_grid_representations.py::test_secondary_declared_pair_normalizes_without_primary_alias_fields
test_grid_representations.py::test_mixed_horizontal_coordinate_units_preserve_physical_faces
test_grid_representations.py::test_native_crop_preserves_faces_with_mixed_horizontal_units
test_grid_representations.py::test_w_interpolation_uses_physical_coordinates_with_km_interfaces
```

## Fix round 1 — range metadata and native ancillary stencils

Reviewed tree: `eb810d0878883efeda35ab350357ceb84768775c` (an index tree,
not a commit); HEAD remains `9ad6f19`. The review findings are corrected for
scoped independent closure; this is not a Task04 freeze or execution clearance.
This section supersedes the first-review result counts and the dependency/
selector clauses above where explicitly changed below. The lead's native-repair
and post-repair evidence above is preserved unchanged.

### Shared-root corrections and exact metadata semantics

1. `_coordinate_units` scales existing `valid_min`, `valid_max`, `valid_range`
   and `actual_range` with the same compatible factor as coordinate labels and
   their referenced bounds. `_bind_vertical` then recomputes an **existing**
   `actual_range` from selected coordinate metadata when all selected values
   are finite numeric values; otherwise it removes the unsupported assertion.
   It does not add an absent range, fill missing bounds, change validity limits
   merely because of subsetting, or alter source descriptors/scientific fields.
   Same-unit subsetting also refreshes `actual_range`.
2. `binding.products[product][name]` remains the requested export selection in
   requested order. Its `vertical` describes the selected representation;
   `source_positions` describes only the native support for that product.
3. `binding.dependencies[name]` is **internal read support**, not necessarily an
   unexported name. A required ancillary can now appear here **and** in products.
   Its `selection_grid_id` remains its actual native `grid_id`; its
   `source_positions`, `vertical.positions`, `vertical.source_native_indices`
   and selected coordinates describe the effective **native read union**, not
   another application of the public output selector.
4. For shared native vertical dimensions, required support propagates by original
   native index from each bound parent stencil to matching dependency records
   at the same time/cycle/native-member context. It accumulates first-required
   storage positions without duplicates and propagates through nested support.
   Existing selected-label/unit compatibility checks still apply on the native
   axes. Direct non-ancillary operation inputs retain their selector semantics.
5. Missing actual native indices fail actionably. Undeclared transform support,
   or a dependency relationship needing a different-axis method, stays explicit
   in `deferred_checks`. With no resolved parent stencil, a 3D ancillary's
   diagnostic `records` is empty rather than a fabricated selected read.
   If another product has known support, its read contribution can be recorded,
   but unresolved methods still keep the whole binding pending.
6. Final selected message/provider checks remain after support selection.
   `binding.records` still contains original candidate-pool identities, not an
   export instruction or permission to widen source files/times. There are no
   new public controls or changes to scientific field units/values.

**Task05 handoff change:** consume products for exports and dependencies for
internal reads, even when their names match. Never replace a product selection
with the dependency union or reapply `requests.levels` to truncate read support.
For the covered W-to-mass declaration, destination selection stays `[5,0]`;
native W/ancillary reads include `[5,6,0,1]`. An explicitly exported native
ancillary still exports `[5,0]`, not the neighbour union. Keep the existing
`status == "bound"` / non-`None` executable-binding gate and original locators,
coordinate provenance and source/parent snapshot requirements. No Task05
implementation or payload slicing was added here.

### TDD evidence and covering commands

Before either production correction, four range cases and five ancillary cases
were added to the two named covering tests:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py::test_v3_vertical_units src/frameit/testing/numerical/test_grid_representations.py::test_v3_representation_level_binding --tb=short
```

Observed intended RED: **7 failed, 28 passed**, exit 1, retained as
`task-04-fix-1-red.txt`. The four range cases exposed stale scale-dependent
attributes or stale same-unit `actual_range`; complete, separately exported and
nested ancillary cases exposed the false missing `[5,6,0,1]` error.
The missing-support and unresolved-method cases were safety controls.

After the range correction alone:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py::test_v3_vertical_units --tb=short
```

**21 passed**, no warnings, exit 0 (`task-04-fix-1-green-ranges.txt`).
After both corrections the covering command is **35 passed**, no warnings,
exit 0 (`task-04-fix-1-green-covering-final.txt`). Original no-ancillary cases
remain. The genuine missing-index assertion now specifically requires `[6]`.
The unresolved ancillary control was strengthened to have no other resolved
product stencil: both transformed W and ancillary read records stay empty,
with explicit pending diagnostics and no executable binding.

All new paths assert no scientific reads and no widening of selected files/times.
Range cases check both labels and bounds, including units-only conversion,
same-unit subsetting and removal of unsupported nonfinite-bounds `actual_range`;
source coordinate descriptors and scientific values/units remain unchanged.

### Fresh scoped regression evidence

The six exact commands in the earlier **Final verification** subsections were
rerun under Python **3.13.18** in `frameit_env`, without any environment change.
The same milestone exclusions, read-only CI fixture and numerical node list
were used; no native-import/payload/shutdown probe was rerun.

| Command subsection above | Fix-round raw log | Observed result |
| --- | --- | --- |
| Exact required command | `task-04-fix-1-required-final.txt` | **64 passed**, no warnings |
| All Task04 checks | `task-04-fix-1-focused-final.txt` | **110 passed, 68 deselected**, no warnings |
| Delivered Task03 inventory/read guards | `task-04-fix-1-inventory-final.txt` | **123 passed, 69 deselected, 19 existing warnings** |
| Delivered v3 schema and Task01 | `task-04-fix-1-delivered-final.txt` | **342 passed, 12 deselected, 4 existing warnings** |
| Applicable numerical callers | `task-04-fix-1-numerical-final.txt` | **73 passed**, no warnings |
| Applicable assembly/import callers | `task-04-fix-1-assembly-final.txt` | **31 passed, 33 deselected, 71 existing warnings** |

All exit 0. **679 distinct targeted passes** = 110 + 123 + 342 + 73 + 31;
the covering 35 and required 64 are subsets. This is nine more cases than the
reviewed snapshot, not 679 new cases. The existing NumPy/netCDF4 warnings were
not suppressed.

### Self-review, preservation and remaining limits

- Checkpoint-relative AST/Ruff comparison is retained in
  `task-04-fix-1-self-review-final.txt`: only `_coordinate_units`, `_bind_vertical`,
  `bind_requests` and the two named covering tests changed. All other functions,
  including FA producer/local-evidence handling, remain identical to review.
  Ruff is **8 → 8**, zero new diagnostics; the first check caught two new long
  lines, which were wrapped without behavior changes (`task-04-fix-1-ruff.txt`).
  Final request implementation/tests are clean (`task-04-fix-1-ruff-new-final.txt`).
- `git diff --check` passed. The index still resolves to the reviewed tree.
  The lead's unstaged STATE and portable native-check additions were preserved;
  no public docs, shared fixtures, dependencies or environment were edited.
  `task-04-fix-1-preservation-final.txt` verifies the saved STATE delta and
  byte-identical pre-fix portable content, with only an appended worker section.
- `task-04-fix-1.diff` is the owned tracked-path diff against the reviewed tree,
  including portable evidence, excluding STATE/public docs. Because of that
  baseline it also contains the lead's already-present portable appendix;
  those lines were preserved, not authored or re-executed by this worker.
- Independent closure belongs to the original reviewer via the lead. Actual
  payload slicing, transformations, ordinary-reader outputs and large-archive
  resource qualification remain later-task evidence, not established here.
  Task07/scaling and general native qualification gates remain open/pending.
  The reproduced mixed-library blocker was repaired by the lead as recorded
  above; this worker did not repeat those controls or claim broader clearance.
- No full legacy suite, native probe, Sphinx/publication build or GUI review was
  run in this internal-evidence fix. Canonical public docs/build/preview remain
  lead-owned before the task commit. No subagent, staging, commit or push.
