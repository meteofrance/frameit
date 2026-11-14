# Task 03 — source and selected-record inventory

Internal evidence, not published user guidance. Base: `8034a6d`.
Commands run from the repository root with the selected checkout inherited by
subprocesses. Python: **3.13.18**, Conda environment: `frameit_env`.
No payload adapter, field/level binding, source association or output writer was
implemented here. Independent review closed all nine findings: spec PASS,
quality APPROVE, no new Critical/Important fix breakage. The lead's reviewed
interface freeze is recorded in `STATE.md`; this file retains its exact shapes,
verification evidence and limitations.
Native qualification remains **blocked by the diagnosed installed native stack**,
not an established Task03 handle bug. No abort probe or environment workaround
was repeated in this round; see the independent diagnosis below.

## Changes and boundaries

- `io/loader.py`: expand declared scalar/list paths and globs (including explicit
  recursive `**`), apply exclusions,
  deduplicate device/inode identities, and report aliases/overlapping matches.
  Separate copies remain separate providers. No archive content hashing.
- `core/preflight.py`: inventory NetCDF, GRIB and admitted FA metadata; classify
  physical sources; preserve decoded clocks, calendars, cycles, intervals and
  native coordinates; select times before any scientific processing.
- `core/coupled.py`: v3 children use `_source_runtime(parent, name)` and the
  internal constructor, including dependency-only children with `products={}`.
  Parent controls/origins are preserved. v3 does not call common-time alignment,
  require a tracking source, compare source cycles, or load a supplied track.
  Profile-only FA children receive canonical FA runtime options and coordinates;
  after inventory, a single-source parent receives an independent options copy
  and the same coordinate names.
- The old numerical loaders, metadata API and explicit numerical time-association
  functions remain available. No default winds, alternate files/streams,
  scientific interpolation, transformations or diagnostics were added.

Physical types use model declarations plus admitted file profiles and observed
metadata. Detection without a declaration requires unambiguous model evidence
(recognized model attributes or the Meso-NH closure marker). Selected names and
source names do not supply that evidence. NEMO retains its native clock/geography
profile; CROCO requires its history-file profile. A declared FA profile implies
the FA reader; a conflicting file header fails. Profiles are checked by the
existing isolated reader. An atmospheric model identity supplied by the declared
FA profile is recorded as YAML-origin, not observed producer evidence.
Verified SURFEX producer metadata is input-origin when no model is declared;
separately supplied SURFEX retains its observed AROME-47/SURFEX-8.1, `PACK=0`
restrictions.

## Handoff for Tasks 04–05 and 10

`preflight(conf)` returns a metadata report. `prepare_sources(conf)` retains its
three-item return `(report, children, source_plans)`. The authoritative source
entries are also copied into
`conf.simulation_parameter["request_plan"]["sources"][name]`.

The source entry retains its declaration/requests and adds:

```text
model, format, profile, physical_type
metadata_origins: {fact: {origin, evidence}}
files: [resolved selected provider paths, in chronological record order]
file_inventory: [
  {path, aliases, patterns,
   identity: {strategy: device_inode, device, inode, size_bytes, mtime_ns},
   fields, unmapped_records, status, reason}
]
excluded_files: [matched excluded paths]
overlapping_patterns: [{path, provider, pattern, previous_patterns}]
fields: {field_id: field metadata}
native_grids: {grid_id: coordinate/grid metadata}
records: [selected native record descriptors]
record_inventory: [all native array record candidates within selected times/cycles]
selected_times: [unique chronological decoded timestamps]
dependency_resolution: declared | pending_method_binding
provider_conflicts: [conflicts awaiting field/method/level binding, if any]
```

File status is `selected`, `time_excluded`, `irrelevant` or `dependency_pending`,
with a reason. Pending operation dependencies are not falsely declared irrelevant.
Unreadable matched inputs fail rather than becoming irrelevant. A readable
clockless file can be proved irrelevant; a required field without a usable sample
clock still fails. Missing declared/ancillary/formula dependencies fail within
the selected inventory; no wider file/time discovery occurs.

Every record has:

```text
field_id, name, grid_id, level
time, calendar, cycle, time_bounds, clock
temporal_metadata
locator
```

GRIB records also retain `native_axes: {number: encoded_member_label}` when an
ensemble member is encoded, plus raw `ensemble_metadata`. Distinct members of
one field are native samples, not competing providers or different field names.
Provider identity includes those native labels; no single-member restriction or
member choice is imposed. NetCDF retains native ensemble dimensions intact.

`time`/`cycle` and interval endpoints remain decoded NumPy datetime or `cftime`
objects, not presentation strings. Absent cycle/bounds are `None`. NetCDF/FA
array/cube records have `level=None`; their vertical axes are not selected or
bound here. GRIB message records retain their actual native level.

Locators are **metadata-only**, not payload-reading implementations:

```text
NetCDF:
  {format: netcdf, path, variable,
   indexers: {payload_time_dimension: original_integer_position, ...},
   coordinate_indexers: {all_native_clock_dimensions: original_integer_position, ...}}
GRIB:
  {format: grib, path, message_index, offset, length}
FA:
  {format: fa, path, records: [native record names in declared order],
   zone: [x_start, x_stop, y_start, y_stop], identity: [size_bytes, mtime_ns]}
```

GRIB byte offsets/lengths identify individual messages, not cfgrib groups.
NetCDF `indexers` apply only to dimensions present on the payload array.
`coordinate_indexers` retain the full original clock position, including
multi-dimensional cycle/step clocks. Apply only its matching dimensions when
slicing grid/clock coordinates. Each record's decoded `time`, `cycle` and `clock`
label that original position. Thus a static array retains empty payload indexers
and `time_varying=False`, while moving geography still identifies its selected
sample. This does not authorize temporal interpolation or extra payload reads.
FA zones use the existing reader's half-open indices. FA size/mtime is a
freshness check, not verified content identity.

Fields retain names, native dimension order, dtype when known, attributes and
coordinate names. `grid_ids` inventories every associated native geometry.
`grid_id` is the single ID or `None` when a time-labelled moving field has several
geometries; each record always identifies its actual grid. GRIB fields also
retain native group/available levels. FA fields retain their raw descriptors and
explicit cube declarations; unknown dimensions remain `None`. A header geometry
does not establish that an unsupported FA encoding has gridpoint samples.

NetCDF fields retain `role: array`, `xarray_coordinate: bool`,
`dependencies` and `coordinate_dependencies`. Xarray storage does not authorize
scientific reads. Ancillary flags/uncertainties such as `quality` remain array
candidates even in `.coords`: their metadata, locators and selected-time support
survive, but values are not materialized or hashed into grids. `PS` remains a
scientific formula input, not a hybrid coefficient. No mask or interpretation
is applied.

Proven coordinate metadata belongs to the **owning grid**, not the ordinary
physical-provider table:

```text
native_grids[grid_id]:
  coordinates[name]:
    dimensions, values, attributes, dtype, role: coordinate_metadata
  coordinate_providers[name]: [             # NetCDF provenance only
    {format: netcdf, path, variable,
     samples: [{time, calendar, cycle, time_bounds, clock,
                indexers: {coordinate_dimension: original_position, ...},
                coordinate_indexers: {full_clock_dimension: original_position, ...}}]}
  ]
fields[field_id]:
  role: array
  xarray_coordinate: bool
  dependencies: {scientific_array_name: declaring_attribute}
  coordinate_dependencies: {local_grid_coordinate_name: declaring_attribute}
```

This supersedes fix round 1's coordinate-as-field view. Coordinate metadata is
not promoted into `records`/`record_inventory` as competing scientific arrays.
Resolve `coordinate_dependencies` through each record's actual `grid_id`, never
through a source-wide name exemption. Provider samples retain only the selected
source times/cycles; an empty sample list is inventory provenance, not available
support. Static coordinate payload indexers may be empty while full clock
indexers still identify their association with a selected record.

The narrow added CF recognition covers one-dimensional auxiliary `air_pressure`
coordinates with `axis=Z` and supported pressure units, including declared bounds.
It also recognizes the local `a`/`b` or `ap`, and scalar `p0`, constants declared by
an `atmosphere_hybrid_sigma_pressure_coordinate` axis. Coefficients must match
that axis's dimensions and dimensionless/pressure-unit role; absent dimensionless
units on `a`/`b` retain their original metadata. Ancillary references and flag
attributes do not confer this role. Malformed `term: variable` pairs fail.
This is not a general CF formula implementation or scientific eligibility check.
Coefficient variables need not be xarray coordinates: the local formula
declaration supplies their role.

Before materializing any owning-grid coordinate, the shared grid boundary now
validates every declared bounds reference. The target must exist, retain the
coordinate's ordered dimensions, and add one distinct final endpoint/vertex axis.
An `axis=Z` coordinate requires two endpoints; existing geographic vertex axes,
including four-corner curvilinear bounds, are not forced to length two.
Bounds must not reuse a declared scientific input (`ancillary_variables`,
`cell_measures`, or formula inputs not already proven owning-grid metadata), nor
a target carrying `flag_values`, `flag_masks` or `flag_meanings`.
Contradictions raise a source/file/coordinate/bounds-specific metadata error
before target value access. They are not repaired by reclassification, dropping
dependencies, suppressing backend failures or reading selected scientific samples.
This is a bounded pre-read reference check, not a general CF/scientific validator.

Only metadata with the **same complete owning-grid identity** coalesces.
Native dimensions, coordinate/bounds values, dtype, units and attributes are part
of that identity; all contributing coordinate providers remain in provenance.
Different labels, bounds, constants, units or attributes retain separate grids,
even for same-named coordinates. Complementary fields may use those distinct
grids. Scientific duplicate providers still fail; there is no first/last choice,
archive-content deduplication or approximate metadata equivalence.

Grid IDs are `grid_` plus a full SHA-256 digest of coordinate/grid metadata,
resolved **before field filtering**. They do not include field selection order
or provider path/provenance. Grid entries retain `dimensions`, native coordinate
`dimensions`/`values`/`attributes`/`dtype`, and grid-mapping identity. GRIB also
retains its encoded grid-section identity and level type. FA retains its header,
library geometry attributes and original `source_i`/`source_j` coordinates.
Static geometry excludes clocks/reference times. Time-labelled moving geography
is retained, without treating movement alone as a different field.
Regular FA grids retain both horizontal dimensions and both geographic axes,
even when latitude and longitude are separate one-dimensional arrays.

### Binding obligations, not escape hatches

- Default requested-provider conflicts fail. Distinct fields sharing a requested
  name fail and identify their grids/dimensions/providers; no qualified selector
  or provider priority is offered.
- For a GRIB 3D request or applicable internal derived input with an explicit
  shared level strategy, Task 03 cannot decide
  which level is requested without doing Task 04. It retains **both** providers
  and records the conflict as
  `{field_id, name, time, cycle, level, native_axes, locators,
  status: pending_level_binding}`.
  **Task 04 must reject every conflict surviving level binding.** It must not
  choose a provider. The test has duplicated 850-hPa messages but requests the
  existing 700-hPa label; rejecting the input before binding would wrongly reject
  an unambiguous requested record. No native vertical-axis order is inferred here.
  This also covers nested derived inputs. A conflict at the eventually requested
  level is retained, not cleared. An explicitly declared 2D input is not granted
  this level-selection deferral.
- Dynamic Meso-NH centroid/multifield inputs remain
  `pending_method_binding`. Inventory retains candidates without guessing an
  alternative pressure/wind/height field or demanding every unrelated candidate
  at every time. Method binding must resolve dependencies using only the
  selected records and fail when support is missing.
- `dependency_resolution` is `pending_method_binding` for source interpretation,
  transforms, requested derived inputs, polar products and atmospheric trackers.
  Known dependencies are inventoried and checked, but operation-specific support
  is not declared resolved before binding.
- `record_inventory` retains every candidate locator within the already selected
  source times/cycles, including fields needed by later transform/polar/tracker
  dependency binding. It never widens the clock or discovers another file.
  `records` initially contains known requests/dependencies and unresolved tracker
  candidates. Task 04 must narrow/promote from this pool, update `files`, and
  enforce field/provider ambiguity before Task 05. A selected operation needing
  unavailable support must fail; it must not extend the pool. Unbound candidate
  conflicts remain `pending_method_binding` or `pending_field_binding`, without
  choosing a provider. Known requested-field conflicts still fail by default.
- `requests.binding` remains `None`. Only selected-time records may reach Task
  05, after Task 04 narrows/binds fields and levels. These descriptors do not make
  the old payload loaders safe for public v3 execution.

### Mandatory Task 04 post-promotion checks

1. Final records come **only from `record_inventory`**. Do not discover providers,
   widen selected clocks/cycles or invent missing temporal support.
2. Recompute field identity, category, availability and provider conflicts after
   promotion and method/level binding. `provider_conflicts` inspects the initial
   `records`, **not the entire candidate pool**; an empty list is not clearance.
3. Check every required field and dependency at its bound times/cycles/native
   axes, including ancillary support from array records and coordinate metadata
   from that record's owning grid/provider/sample context. A coordinate name,
   an empty provider sample list or another field's levels proves no availability.
4. Reject every surviving field/provider conflict. Pending field/method/level
   statuses authorize neither choosing/dropping a provider nor payload reads.
   Coordinate-metadata coalescence never exempts scientific duplicate providers.
   GRIB grid identity does not establish native vertical ordering.
5. Regenerate ordered `files` from final bound locators and update file relevance
   only after dependencies are resolved. Preserve original payload and coordinate
   indexers, decoded clock labels, calendars, cycles and intervals.
6. Enforce FA native descriptors, eligibility, scaling and sampling, including
   unknown shapes. Header geometry is not proof of gridpoint eligibility.
   Preserve `_source_runtime`'s independent dependency-only children and origins;
   do not reload their internal empty-product controls as public YAML.

## RED evidence

The two required parameterized nodes were written first:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_source_inventory src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_time_record_selection --tb=short
```

Initial result: **31 failed**, exit 1. The failures were the missing v3 inventory
guard and compulsory legacy common-time preparation, not a successful payload run.
Further tests were observed RED before their fixes: missing FA/GRIB inventories
(9 failures); admitted ocean profiles/nested derived dependencies; unmapped GRIB
names, missing reference clocks, conflicting bounds and sub-microsecond calendar
requests; clock-free irrelevant files/static versus moving grids (3); scalar
path/glob inputs (2); dynamic tracker candidates (1); level-pending conflicts
(1); sub-minute GRIB clocks (1); unknown FA shape (1); FA zone/freshness locators
(2); encoded GRIB ensemble members incorrectly treated as distinct fields (1);
recursive globs (1); missing selected-time dependency pool (1); premature rejection
of an unbound tracker candidate's competing providers (1); FA profile-derived
model origin (1); profile-only FA reader selection (2); misleading profile/header
conflict reporting (1); missing resolved FA parent runtime options (2); prematurely
resolved derived/interpretation dependencies (3).
The last five RED logs are `task-03-red-fa-origin.txt`,
`task-03-red-fa-profile.txt`, `task-03-red-profile-conflict.txt`,
`task-03-red-fa-runtime.txt` and `task-03-red-operation.txt`.
Full commands/results are retained in the ignored task report/logs.

Test-fixture corrections, not weaker requirements: two alias paths, not three;
ecCodes encodes an averaged U field as `avg_u`/parameter 235131, not instantaneous
`u`; unknown GRIB parameters use explicit discipline/category/number 255 rather
than invalid `paramId=0`. Exact native intervals and field identities are retained.

## Final focused checks

The focused commands below were rerun after fix round 3. The whole legacy suite
was deliberately not rerun at this milestone; its final run belongs to Task 19.

Required command:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_source_inventory src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_time_record_selection --tb=short
```

**53 passed**, exit 0, no warnings.

Required cases plus all nine finding regressions:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_source_inventory \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_time_record_selection \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_coordinate_dependency_keeps_provider_and_selected_support \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_fa_inventory_uses_verified_profile_without_physical_reads \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_time_bounds_require_clock_dimension_identity \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_timestamp_precision_is_checked_before_numpy_selection \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_v3_moving_grid_keeps_coordinate_indexers_separate_from_payload \
  'src/frameit/testing/numerical/test_grib_lifecycle.py::test_v3_grib_metadata_locators_without_value_decoding[derived_level_conflict]' \
  'src/frameit/testing/numerical/test_grib_lifecycle.py::test_v3_grib_metadata_locators_without_value_decoding[nested_level_conflict]' \
  'src/frameit/testing/numerical/test_grib_lifecycle.py::test_v3_grib_metadata_locators_without_value_decoding[internal_requested_level_conflict]' \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_v3_cf_auxiliary_pressure_and_bounds_define_the_owning_grid \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_field_split_coalesces_only_owning_grid_coordinate_metadata \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_coordinate_bounds_fail_before_scientific_backend_access \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_v3_geographic_bounds_keep_native_vertex_axes \
  --tb=short
```

**100 passed**, exit 0, no warnings: original 53, 20 round-1 cases, two augmented
regular-FA cases, 12 round-2 cases and 13 round-3 cases. Included in Task 03 below.

All Task 03 checks, including the frozen local fixture:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env env FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" python -m pytest -q src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_netcdf_assembly.py src/frameit/testing/numerical/test_grib_lifecycle.py -k v3 --tb=short
```

**123 passed, 69 deselected, 19 warnings**, exit 0. The two frozen cases inspect
the three Meso-NH files and five AROME GRIB files; neither opens the fixture track
as a source. No fixture was downloaded or changed.

Backend evidence:

- H5NetCDFArrayWrapper, NetCDF4ArrayWrapper and ScipyArrayWrapper actual backend
  indexing is instrumented. Scientific field requests fail the test, including
  selected and excluded samples in a retained four-time file. Coordinates are
  read; all three readers close their owned inputs.
- ecCodes scientific value accessors are forbidden. Metadata retains actual
  message offsets, cycles and forecast intervals, including second-resolution
  reference times/steps. No cfgrib index or scientific array is built.
- FA requests are restricted to `inspect`. The isolated helper's actual
  `fa_epygram.read_values` accessor is forbidden. AROME and SURFEX fixtures retain
  one selected time, their checked profiles and native zone/freshness locators.
- Frozen-fixture NetCDF/GRIB scientific backend access is forbidden as well.
- The CF pressure/hybrid tests also forbid `temperature`, `salinity`, `PS` and
  `quality` payloads. Coordinate labels, bounds and proven constants may be read.
- Finding 9's actual H5NetCDF backend guard records calls before failing them.
  Invalid-bounds cases require an actionable `ValueError` and **zero** `quality`
  requests, so catching/relabeling a backend exception cannot pass the test.

These are **zero scientific-payload-read** checks. They do not prove that Task
05's future payload adapters slice every backend correctly, nor qualify new
FA/spectral methods or all real producers.

Reader package labels recorded: NumPy 2.5.4; xarray 2026.9.0; cftime 1.6.5;
netCDF4 1.7.2; h5netcdf 1.8.2; SciPy 1.18.1; cfgrib 0.9.15.1; EPyGrAM 2.1.0.
The Python ecCodes distribution metadata is 2.44.0, **not the native decoder
identity**. Independent diagnosis measured selected wheel native ecCodes 2.50.0
(`eccodeslib` 2.50.0.33), despite Conda ecCodes 2.46.0 also being installed.
Historical invocations without native maps are not retroactively version-pinned.

## Delivered v3 and Task 01 regression

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_hpc_execution.py -k 'not test_invalid_execution_schema and not test_exclusive_run_ownership_and_early_no_clobber and not test_concurrent_cli_attempts_spawn_and_sync_export_exactly and not test_batch_overrides_dry_run_does_not_claim_output and not test_cli_processing_failure_never_marks_completed and not test_incomplete_tracking_is_explicit_and_strict_policy_fails and not test_cancellation_and_same_root_exclusion' --tb=short
```

**342 passed, 12 deselected, 4 warnings**, exit 0: all 326 delivered v3 schema
checks plus 16 applicable resource/publication/checkout-identity checks, including
fresh/spawned interpreter source identity.

## Numerical callers and resource cleanup

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env env FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" python -m pytest -q src/frameit/testing/numerical/test_netcdf_assembly.py src/frameit/testing/numerical/test_grib_lifecycle.py::test_discovering_grib_loader_does_not_initialize_optional_native_decoder src/frameit/testing/numerical/test_grib_lifecycle.py::test_direct_grib_loading_and_native_shutdown_in_fresh_interpreter src/frameit/testing/numerical/test_inspect_metadata.py::test_wind_metadata_interpretation_retains_evidence_without_mutating src/frameit/testing/numerical/test_inspect_metadata.py::test_metadata_report_keeps_numpy_values_portable_without_dumping_other_attributes src/frameit/testing/numerical/test_fa_io.py src/frameit/testing/numerical/test_nemo_netcdf.py::test_nemo_rejects_conflicting_native_definitions src/frameit/testing/numerical/test_croco_netcdf.py::test_croco_rejects_unresolved_native_definitions src/frameit/testing/numerical/test_fa_pipeline.py::test_common_and_strict_policy_complete_skip_report -k 'not v3 and not test_variable_shards_preflight_companion_inventory_and_replay and not test_netcdf_layout_rejects_invalid_configuration and not test_variable_shard_wind_companion_can_live_in_another_file and not test_runner_reuses_netcdf_metadata_without_reading_fields and not test_standalone_preflight_closes_netcdf and not test_runner_only_prepares_selected_cartesian_branch' --tb=short
```

**68 passed, 33 deselected, 71 warnings**, exit 0. This covers direct assembly,
explicit numerical duplicate policies, lazy data, error cleanup, handle reuse,
FA native metadata/payload error contracts, ocean metadata rejection, legacy
explicit time-association APIs and the existing direct GRIB shutdown node.
That passing node does not qualify the mixed native stack diagnosed below.

Distinct targeted checks: **533 passed** (123 + 342 + 68); required 53 and combined
100 are subsets of 123. Earlier handoff totals were 488, 508 and 520.

Warnings are the existing netCDF4/NumPy ABI-size warning and NumPy 2.5 shape
assignment deprecations. They were reported, not silenced.

## Fix round 1 — RED/GREEN evidence

Each finding regression was observed RED before its production change.
Raw logs use the prefix `task-03-fix1-` in the ignored task workspace.

| Finding | RED log/result | GREEN log/result |
| --- | --- | --- |
| Coordinate providers/ancillary boundary | `red-coordinate.txt`: 5 failed, including forbidden `quality` read in the same-file case | `green-coordinate.txt`: 58 passed, including the original 53 |
| Complete regular FA geometry | `red-fa-grid.txt`: 2 failed at missing x dimension | `green-fa-grid.txt`: 2 passed with actual FA payload accessor forbidden |
| Internal/nested derived level conflicts | `red-internal-levels.txt`: 3 failed at premature rejection | `green-internal-levels.txt`: 14 passed, 3 deselected |
| Moving geography/static payload indexers | `red-moving-indexers.txt`: 2 failed at missing coordinate indexers | `green-moving-indexers.txt`: 11 passed, 46 deselected, 19 warnings |
| Bounds dimension identity | `red-bounds-dimensions.txt`: 2 failed, 1 positive control passed | `green-bounds-dimensions.txt`: 24 passed |
| Timestamp precision/range | `red-timestamp.txt`: 7 failed, including overflow and wrapped selection | `green-timestamp.txt`: 28 passed |

Bounds must have the clock dimensions in their original order, followed by a
distinct endpoint axis of length two. Unsupported transposed or unrelated
dimension layouts fail even when their shape is square `(2, 2)`.
NumPy requests normalize harmless fractional trailing zeroes, retain up to
nanosecond precision and round-trip-check the common source/request datetime
representation before selection. Unsupported nonzero precision, range or timezone
overflow fails actionably, without truncation. `cftime` retains its existing
microsecond precision check and native calendar.

Final logs are `task-03-fix1-original-required-final.txt`,
`task-03-fix1-required-final.txt`, `task-03-fix1-focused-final.txt`,
`task-03-fix1-delivered-final.txt` and `task-03-fix1-numerical-final.txt`.

## Fix round 2 — RED/GREEN and compatibility

Checkpoint/index tree: `cbfd01ee1883e43af9a2655a2df15363404a6358`, not a commit.
Findings 7/8 were read verbatim from the ignored round-2 findings packet.

- `task-03-fix2-red-coordinate-metadata.txt`: **8 failed, 3 passed** before the
  correction. Four pressure cases lost labels/bounds; four field-split cases
  rejected repeated coordinate metadata. Scientific-duplicate and missing-input
  controls already failed as required.
- `task-03-fix2-red-formula-terms.txt`: **1 failed** before paired-term validation;
  a dangling hybrid formula token was incorrectly accepted.
- `task-03-fix2-green-coordinate-metadata.txt`: **17 passed**: all 12 new cases
  plus the five original ancillary-provider guards. The identical hybrid case
  also checks constants stored as ordinary NetCDF variables, not only `.coords`.
- An intermediate assertion omitted the fixture's declared latitude/longitude
  coordinate links. It now checks those links explicitly; scientific-read and
  duplicate-provider requirements were not weakened. The intermediate log is
  retained as `task-03-fix2-intermediate-coordinate-links.txt`.

Final logs use prefix `task-03-fix2-`: `original-required-final.txt`,
`required-final.txt`, `focused-final.txt`, `delivered-final.txt`,
`numerical-final.txt`. Those round-2 results are retained; current counts are above.
All **43** pre-round-2 test function ASTs, including the original six regressions,
match the reviewed checkpoint; the **30** pre-Task03 test ASTs match `8034a6d`.

Internal compatibility: Task04 must use owning-grid metadata/provider groups
instead of searching `fields` for `role=coordinate_metadata`. Grid identities
now preserve CF pressure/bounds/constants; input paths and provider provenance
do not enter their hashes. No public YAML, numerical API, scientific method,
payload adapter or output schema was changed.

## Fix round 3 — finding 9, pre-read bounds boundary

Checkpoint/index tree: `9bb7826dfad4ef1e9926f0d3e98b3160716f912a`, not a commit.
The exact reviewer reproduction/cause/remedy was read from the ignored
`task-03-findings-round3.md` before editing production code.

### Intended RED and observed GREEN

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_coordinate_bounds_fail_before_scientific_backend_access \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_v3_geographic_bounds_keep_native_vertex_axes \
  --tb=short
```

`task-03-fix3-red-bounds.txt`: **8 failed, 3 passed**, exit 1. The exact
`pressure(level).bounds="quality"` case, with flagged ancillary
`quality(time,level,y,x)` and only the second timestamp selected, intercepted an
actual scientific backend request covering **all** time/spatial positions.
The shape-only, endpoint-count and role-only negatives also intercepted reads;
the missing-target case incorrectly succeeded. Valid bounds and the two
geographic controls already passed.

Two additional shape-correct controls isolate declared scientific roles without
flags/ancillary markers:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
  'src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_coordinate_bounds_fail_before_scientific_backend_access[cell_measure_only]' \
  'src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_coordinate_bounds_fail_before_scientific_backend_access[formula_input_only]' \
  --tb=short
```

`task-03-fix3-red-scientific-roles.txt`: **2 failed**, exit 1, before extending
the same pre-read check to these already-declared input roles.

Final covering command:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_coordinate_bounds_fail_before_scientific_backend_access \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_v3_geographic_bounds_keep_native_vertex_axes \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_v3_cf_auxiliary_pressure_and_bounds_define_the_owning_grid \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_field_split_coalesces_only_owning_grid_coordinate_metadata \
  src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_coordinate_dependency_keeps_provider_and_selected_support \
  --tb=short
```

`task-03-fix3-green-bounds.txt`: **30 passed**, exit 0, no warnings.
The 13 new cases keep shape and role checks independent: square transposed bounds
and wrong endpoint count without scientific markers; correct shapes with
ancillary, measure, formula-input or separate flag attributes; and a missing
target. Positive controls retain a genuinely valid bounds variable even named
`quality`, plus native one-dimensional/two-endpoint and two-dimensional/four-corner
geographic bounds. The flagged ancillary reproduction is rejected, never retyped.
All negative cases assert no target backend call, not merely a caught exception.

Final logs use prefix `task-03-fix3-`: `original-required-final.txt` (**53**),
`required-final.txt` (**100**), `focused-final.txt` (**123**),
`delivered-final.txt` (**342**) and `numerical-final.txt` (**68**).
Exact commands/results are the current selections above. All **45** checkpoint
test-function ASTs and all **30** pre-Task03 test ASTs remain unchanged.
Ruff remains baseline/current **22/22**, with zero new diagnostics.

Compatibility/limits: successful record/grid/provider shapes and valid geometry
definitions are unchanged; only contradictory bounds now fail before access.
No unit transformation, scientific method, masking, payload adapter or general
CF-validation framework was added. Existing owning-grid, selected-clock,
post-promotion conflict and native-qualification conditions remain in force.
No whole legacy-suite or unchanged native abort probe was repeated.

## Historical standalone GRIB probe — subsequently diagnosed environment

The historical reviewer probes differed in import surface/order, core-dump
limits and printing; their exit 134 versus 0 was not a controlled comparison.
After the six fixes, one small three-variant experiment held the generated
four-message input, request, import order, payload guards, printing and
process-local `RLIMIT_CORE=(0, 0)` constant:

| Variant | Single change from preceding variant | Child result |
| --- | --- | --- |
| Direct production constructor/preflight | Baseline; no test-module import; NumPy/ecCodes before production imports | SIGABRT, return code `-6` |
| Same direct call plus test-module import | Import `v3_config`'s module | SIGABRT, return code `-6` |
| Helper call after the same imports | Call `v3_config` instead of the equivalent direct mapping constructor | SIGABRT, return code `-6` |

All three accepted four metadata records and retained the duplicated 850-hPa
providers as `pending_level_binding`. All printed the pre-teardown marker, then
aborted with `corrupted size vs. prev_size while consolidating`.
The exit codes, not that marker, establish the observed shutdown failure.
Scientific value accessors were forbidden during preflight.

The exact child program, separate stdout/stderr, return codes and current
production-file hashes are retained in ignored
`task-03-fix1-shutdown.json`; the earlier commands remain in
`task-03-shutdown-probe.md`. Each new variant ran once. This experiment includes
fixture creation, metadata preflight and teardown; that experiment alone did not
isolate the cause or replay the historical production-before-ecCodes order.
No probe from this section was repeated in fix rounds 2 or 3.

## Independent native diagnosis — repair and qualification still blocked

The later read-only `task-03-native-diagnosis.md` independently reproduced the
abort with ecCodes followed by pyproj imports alone: no FrameIt production
imports, GRIB generation, handles or inventory are needed. The causal control
loads eckit's bundled PROJ 9.8.1 globally before pyproj's Conda PROJ 9.9.0:
`RTLD_GLOBAL` aborts; changing only to `RTLD_LOCAL` exits 0 with both files mapped.
The stack includes selected wheel ecCodes 2.50.0, `eckitlib` 2.5.0.33 and
pyproj 3.8.0; Conda's installed ecCodes 2.46.0 is not the selected decoder.

This isolates an installed mixed-library/global-visibility boundary outside
FrameIt. ELF symbol interposition is the likely mechanism; the exact colliding
global object and destructor registrations are not fully traced.
It is **not evidence of a Task03 handle bug or helper defect**.
Independent legacy/v3 scanner controls each exited 0, opened/released exactly
four handles, and returned owned NumPy coordinate arrays. These one-run controls
are not general lifecycle qualification.

No unchanged abort probes, dependency/environment changes, import reordering,
array-copy workaround, release removal or finalizer bypass were made in this
round. **Native-stack repair requires approval; native qualification remains
blocked pending that repair and Task19 verification** of the relevant import,
constructor/preflight, successful/rejected-request and independent-reader paths.
Fresh-process exit 0, actual loaded versions and library identities are required;
passing focused tests or pre-teardown markers do not clear this gate.

## Whole-suite diagnostic and unchanged future-dependent nodes

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env env FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" python -m pytest -q --tb=short
```

Latest whole-suite diagnostic: **468 failed, 1229 passed, 2 errors,
4 subtests passed, 4022 warnings**, exit 1. No Task 03 v3 node failed.
This snapshot includes the earlier FA metadata/locator and native ensemble-axis
refinements. It predates the final recursive-glob, selected-time candidate-pool,
unbound-provider, FA profile/origin/runtime and operation-dependency refinements;
the latest 123-node focused run includes them and all three handoff fix rounds.
Earlier whole-suite
diagnostics had 1213 and 1227 passed with the same 468 failures and two errors.
The ignored full logs retain every failing node and traceback.
This is **not a green whole-project suite**.

The two setup errors are:

- `test_hpc_execution.py::test_concurrent_cli_attempts_spawn_and_sync_export_exactly`
- `docs/test_repository_examples.py::test_independent_checker_accepts_reference_and_rejects_wrong_time_count`

Public/schema/template/catalogue/CLI producers still emit or expect retired
documents. Their caller-wide conversion belongs to Tasks 15–16/19; remaining
processing/association/writer integration also needs Tasks 04–14.
They were not rewritten, skipped, disabled or made less strict.
An AST comparison against base `8034a6d` confirms all 30 existing test functions
in the three owned numerical modules are unchanged.
All 45 test functions present at the round-3 checkpoint are also unchanged.

Exact future-dependent nodes in the three owned modules remain unchanged:

- `test_inspect_metadata.py::test_netcdf_inspect_keeps_file_context_and_reads_no_field_payloads`
- `test_inspect_metadata.py::test_ordinary_preflight_does_not_add_inspection_metadata`
- `test_inspect_metadata.py::test_grib_inspect_preserves_same_name_in_different_groups_without_payload_reads`
- `test_netcdf_assembly.py::test_variable_shards_preflight_companion_inventory_and_replay`
- `test_netcdf_assembly.py::test_netcdf_layout_rejects_invalid_configuration[mixed|1|None]`
- `test_netcdf_assembly.py::test_variable_shard_wind_companion_can_live_in_another_file`
- `test_netcdf_assembly.py::test_runner_reuses_netcdf_metadata_without_reading_fields`
  for all eight model/engine cases (`mesonh|arome|nemo|croco` × `h5netcdf|netcdf4`)
- `test_netcdf_assembly.py::test_standalone_preflight_closes_netcdf`
- `test_netcdf_assembly.py::test_runner_only_prepares_selected_cartesian_branch[native|mass_earth]`
- `test_grib_lifecycle.py::test_matrix_fixture_planning_and_native_shutdown_in_fresh_interpreter`

## Remaining limits

No scientific payload slicing/export, scientific sign-off, new decoder
qualification, large-run resource benchmark or production run is claimed.
Grid coordinate metadata is materialized; whole-run memory bounds are not
established here. Clock-free files containing required fields are not assigned an
invented clock. FA native eligibility/scaling remains in its original descriptors
and must be enforced at binding/decode, not inferred from a header grid.

The final diff passes `git diff --check`. Ruff reports the same **22 existing
diagnostics** on these six files as base `8034a6d`, with **zero new diagnostics**;
the whole-file linter is not claimed green.

Canonical/public docs, strict Sphinx/publication/live preview, STATE and final
integration are lead-owned. Documentation edits are limited to internal evidence.
The worker did not stage, commit or publish, and performed no independent review.
The lead's staged reviewed tree remains preserved; fix-round-3 edits are unstaged.
