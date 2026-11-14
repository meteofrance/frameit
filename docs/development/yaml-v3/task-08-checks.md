# Task08 — explicit operations and native preservation

Base: `bc2a470c53b313edca58effe65e5ea655e0b9ab9`. Status: independently approved
after two fix rounds. This is engineering evidence, not scientific or human
approval. Initial pending-review snapshots below remain historical.

## Internal handoff

- `preflight.bind_source` binds the actual prepared child once. Without an
  externally supplied representation fixture, it uses
  `requests.bind_source_operations(source, request, conf, ...)`. Explicit
  representation arguments retain the metadata-only `bind_requests` contract:
  supplied coordinates alone do not establish an executable scientific method.
- Operation outputs are separate descriptors marked `operation`, with method,
  actual representation facts, units, preparation and shared-level selections.
  `binding.operations` contains executable model-grid jobs.
  `binding.operation_plans` also contains explicitly pending polar preparation.
  `binding.representation_grids` and the source's corresponding mapping retain
  genuine prepared grids separately from `native_grids`.
- Each job retains its actual selected sample context, geometry and complete
  native `input_binding`. The ordinary binder verifies both real destination
  representations and original-record input stencils. No locator is invented.
  Composite internal stencils can include an also-exported field; their neighbour
  union never becomes that field's export selector.
- Selected NetCDF, GRIB and FA readers still receive the complete binding and
  owning source plan. They skip operation-result descriptors and retain native
  inputs separately. `derived.wind.execute_source_operations` prepares only
  requested results using those internal views. It does not modify native exports
  or tracker inputs.
- Regional geometry is checked against prepared result grids after binding.
  Pre-binding inspection does not mistake a declared mass transform's source
  face grid for its destination. Geometry inspection does not activate polar
  sampling.
- Source provenance records each executed result's method, inputs, preparation,
  source time/cycle, actual grid, units and shared original level identities.
  Result variables carry `frameit_method`, `frameit_preparation`,
  `frameit_sampling`, `frameit_basis`, `frameit_selection_grid` and
  `frameit_shared_levels`, in addition to existing numerical-method metadata.

## Scientific and compatibility boundaries

Native U alone needs no companion, unit normalization or basis interpretation.
Selecting U/V does not request speed, radial or tangential components. Native
units and samples are retained; declarations still describe stored values.
Native numerical multi-file concatenation rejects conflicting stored units rather
than silently inheriting the first file's label.

Model-grid transforms, tracker preparation, derived preparation and later polar
sampling remain separate. The public derived method remains `wind_speed`.
Explicitly named low-level numerical helpers retain their calculation behavior.

Meso-NH sampling reuses strict native-coordinate interpolation. W is a separate
operation; pressure velocity is not converted to geometric vertical velocity.
Selected W destination levels require real native brackets. No extrapolation or
missing-neighbour substitution was added. Exact coordinate hits need no
unnecessary adjacent scientific sample.

Coordinate, geolocation and Meso-NH projection rotation reuse the existing
methods and conventions. Missing/conflicting geometry and incompatible units
fail. The narrow explicit Meso-NH missing-projection Earth declaration exception
is not widened. Regular-latitude/longitude GRIB geography supplies actual native
axis labels for its existing geolocation method; other grids still need admitted
axis evidence.

CROCO's admitted joint-mask midpoint/rho-angle method is reused only for its
supported current pairs with explicit mass/Earth preparation. Static mask values
are checked during execution, not metadata preflight. Unrelated ocean wind
diagnostics and unadmitted remaps are not enabled.
Known basis/rotation/quantity/unit/statistics conflicts fail during metadata
binding. Preparation probes remain lazy; metadata preflight does not allocate
full three-dimensional synthetic field calculations.

Polar shared vertical levels can be inspected, including native versus separately
prepared W and derived component support. Actual polar target planning/sampling
remains blocked. Polar speed must be calculated **after** component sampling;
the model-grid speed result is not reused as a sampled scalar.

NetCDF coordinate bounds may inherit their parent coordinate's units under CF
encoding. Tests check converted numbers and the inherited unit meaning, not an
unnecessary duplicate bounds attribute.

## Verification commands

All Python checks use `frameit_env` Python 3.13 and this checkout explicitly.
Fixture checks set the approved read-only fixture root:

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_operations.py
```

The required command is run without a selection filter:

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_native_extraction.py src/frameit/testing/numerical/test_wind_collocation.py src/frameit/testing/numerical/test_wind_reference.py src/frameit/testing/numerical/test_wind_preflight.py src/frameit/testing/numerical/test_grid_representations.py src/frameit/testing/numerical/test_croco_vectors.py
```

Covering selection:

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_operations.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_regions.py src/frameit/testing/numerical/test_v3_interpretation.py src/frameit/testing/numerical/test_v3_netcdf_reads.py src/frameit/testing/numerical/test_v3_grib_reads.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_native_extraction.py src/frameit/testing/numerical/test_wind_collocation.py src/frameit/testing/numerical/test_wind_reference.py src/frameit/testing/numerical/test_wind_preflight.py src/frameit/testing/numerical/test_grid_representations.py src/frameit/testing/numerical/test_croco_vectors.py --tb=short
```

Full diagnostic:

```bash
PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q --tb=short
```

The ignored packet retains raw command logs/JUnit, a per-node failure ledger,
exact-six-file failure evidence, base-relative Ruff JSON, and a scope/producer
preservation check. Overlapping selections and subtests are not added together.
Final results and exact artifact names are recorded in the Task08 report.

## Recorded final observations

All results use the commands above and the declared environment/fixture root:

| Check | Result |
|---|---|
| Focused operation tests plus two affected GRIB cases | 46 passed, including all 44 new nodes |
| Covering selection | 914 passed / 68 failed; 982 distinct nodes |
| Exact required six files | 161 passed / 35 failed; 196 distinct nodes |
| Unfiltered full diagnostic | 1699 passed / 468 failed / 2 errors; 2169 distinct nodes |
| Base-relative Ruff on 17 claimed Python paths | 22 base / 21 current diagnostics; zero new |

The final full run is `task-08-full-final-04.xml`; the focused run is
`task-08-focused-final-07.xml`. Per-node comparison preserves every one of the
2125 Task07 statuses and all 470 failed/error IDs, with no removed IDs and
44 added passes. The overlapping targeted runs contain 914 distinct passing
nodes, not their summed totals. Four passing subtests are reported separately.
All 35 required failures still stop at old-schema producers; their scientific
assertions did not pass. Complete individual current/prior messages remain in
the ignored `task-08-failure-ledger.md` and `task-08-required-failures.md`.

These are regression observations, not a green-suite claim or independent
scientific approval. Public-example execution and final public-doc build/live
review remain lead-owned.

## Limits and later owners

These compact fixtures verify prescribed values, masks, axes and read footprints;
they do not qualify all real producers, all grids or every scientific regime.
There is no full-archive performance or resource-budget claim. Actual polar
sampling remains Task09; complete multigrid/writer qualification remains Task10.
Existing producer conversion, native-warning qualification and human review keep
their later owners. No package/native repair, warning suppression, shared
producer conversion, staging, commit or push is part of this worker's delivery.

Operations still require matching full U/V preparation-axis metadata. This does
not newly admit partially overlapping but different native vertical axes.

## Independent-review fix round 1

This section supersedes the original delivery's affected behavior and evidence;
it is not an independent closure verdict. Task07 remains the commit base;
the reviewed Task08 tree is `ca60f6a02b74fbd809ae4417677a482abe30504c`.

- **I1, quantity eligibility:** the shared `validate_pair_frame` now rejects a
  nonempty supplied `standard_name` that disagrees with its horizontal U/V role,
  including geometric W. Missing identity stays a gap; no quantity is inferred
  from a variable name. Native copies of the same W remain unchanged. Known
  horizontal and narrow Meso-NH basis-exception controls remain covered.
- **I2, sample-grid identity:** `_grid_from_geometry(geometry, dimensions, *,
  rotation_coordinate=None)` excludes operation-only rotation evidence from the
  destination sampling descriptor. Real axes/geography/bounds/CRS checks and
  native inventory grids remain unchanged. Each operation and source-provenance
  record retains `rotation_coordinate: {name, dimensions, values, attributes}`
  or `None`; changing angle auxiliaries remain time-dependent in output.
  Prepared grid IDs can therefore differ from the reviewed intermediate IDs.
  No exact joins were relaxed.
- **I3, independent W preparation:** the numerical NetCDF loader prepares the
  existing mass-W sidecar for an explicit Cartesian mass-W choice or enabled
  numerical polar mass-W choice, independently of horizontal/speed processing.
  It uses `collocate_mnh_component(..., vertical=True)` without normalizing W or
  interpreting U/V. Sparse brackets and strict missing-neighbour behavior remain.
- **Native FA singleton:** `validate_cube_requests` uses the existing native
  dependency gate for native horizontal copies with polar processing disabled.
  A real admitted wind cube passes the actual preflight metadata opener and
  numerical loader without pair/basis/normalization or V decode. Independent
  prescribed values/NaNs/zeroes, stored knots, native indices and source bytes
  are checked. Horizontal analysis, explicit speed and enabled polar processing
  keep their explicit metadata requirements. All old FA document/fixture producer
  content is unchanged; tests are additive.
- **M1:** only the transferred troubleshooting projection paragraph was changed
  publicly. It now states gap filling, reliable-conflict failure and explicit
  zero handling. Lead owns the final build/publication/live inspection.

Meaningful RED logs are `task-08-fix-1-i1-red.txt`, `-i2-red.txt`, `-i3-red.txt`
and `-fa-red-03.txt` in the ignored packet. Corresponding GREEN checks pass;
the full report records exact commands, setup corrections and each result.
Focused verification observes 136 passes. The 17-module covering run observes
937 passed / 94 failed (1031 nodes); the exact six-file run observes
163 passed / 35 failed (198 nodes). The covering run adds FA modules absent from
the original covering selection; its old statuses match the reviewed full XML.
Ruff on all 19 claimed Python paths observes 22 base / 21 reviewed / 21 current
diagnostics, zero new versus either reference, not a clean lint claim.
The one final full diagnostic observes **1717 passed / 468 failed / 2 errors**
(2187 distinct nodes), plus four passing subtests reported separately.
The dual-baseline comparison preserves all 2125 Task07 and 2169 reviewed Task08
statuses, with no removed IDs or status changes and the same 470 failed/error
IDs. All 18 added fix-round nodes pass (62 added passes since Task07).
Overlapping targeted selections contain 937 distinct passing nodes. The
individual current/Task07/reviewed failure messages remain in
`task-08-fix-1-failure-ledger.md`; IDs/deltas are in
`task-08-fix-1-node-comparison.json`. Required/covering/full suites remain red,
not exempted or scientifically passed.

### Round-1 verification commands

Run from the checkout. Full exact RED/GREEN and final commands with output
paths are also in the appended worker report. The FA tests below use the
ordinary numerical constructor and actual isolated native writer/reader.

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_operations.py src/frameit/testing/numerical/test_wind_collocation.py src/frameit/testing/numerical/test_wind_reference.py src/frameit/testing/numerical/test_fa_cubes.py::test_native_wind_cube_singleton_metadata_and_numerical_copy src/frameit/testing/numerical/test_fa_cubes.py::test_explicit_wind_cube_analysis_retains_metadata_requirements src/frameit/testing/numerical/test_wind_preflight.py::test_grib_per_file_units_rotation_and_native_branch src/frameit/testing/numerical/test_wind_preflight.py::test_grib_later_frame_conflict_is_checked_before_concatenation --tb=short
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_operations.py src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_v3_regions.py src/frameit/testing/numerical/test_v3_interpretation.py src/frameit/testing/numerical/test_v3_netcdf_reads.py src/frameit/testing/numerical/test_v3_grib_reads.py src/frameit/testing/numerical/test_v3_fa_reads.py src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_native_extraction.py src/frameit/testing/numerical/test_wind_collocation.py src/frameit/testing/numerical/test_wind_reference.py src/frameit/testing/numerical/test_wind_preflight.py src/frameit/testing/numerical/test_grid_representations.py src/frameit/testing/numerical/test_croco_vectors.py src/frameit/testing/numerical/test_fa_cubes.py src/frameit/testing/numerical/test_fa_pipeline.py --tb=short
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_native_extraction.py src/frameit/testing/numerical/test_wind_collocation.py src/frameit/testing/numerical/test_wind_reference.py src/frameit/testing/numerical/test_wind_preflight.py src/frameit/testing/numerical/test_grid_representations.py src/frameit/testing/numerical/test_croco_vectors.py
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q --tb=short
```

Raw paired logs/XML use the `task-08-fix-1-focused-final-01`,
`task-08-fix-1-covering-final-01`, `task-08-fix-1-required-final-01` and
`task-08-fix-1-full-final-01` prefixes; the unmodified required invocation is
`task-08-fix-1-required-exact-01.txt`. Scope preserves all old file content in
the three additively extended test modules, including all old FA producers.
The supplementary `task-08-fix-1-native-w-probe.txt` also verifies the native
output dictionary consumed by the runner; it is not another counted test node.

The complete direct-numerical `preflight()` wrapper separately reaches an
existing public-YAML formatter `KeyError: 'output'` after metadata checks. These
tests use its actual `open_metadata` entry and numerical consumer, not a fake
v3 configuration/runtime bypass. No outer-wrapper success is claimed. Broader
producer/polar/writer/resource and human-review gates retain their original
owners. No files were staged or committed, and nothing was pushed.

## Independent-review fix round 2 — numeric angle metadata

I1–I3, M1 and the native FA gate were independently closed before this round.
Only B1 is addressed here: valid numeric NetCDF angle attributes previously
reached the required YAML writer as NumPy objects.

At construction of `rotation_coordinate.attributes`, `np.ndarray` and
`np.generic` values now use `.tolist()`; other values retain their existing
deep copy. Arrays stay numeric lists of the same shape, floating scalars stay
numbers and integer scalars stay integers. Names/units and scientific values
are unchanged. No new descriptor key/signature, global YAML representer,
serializer framework, geometry relaxation or public schema was added.
Absent-angle `None` and varying-angle handling remain unchanged.

The appended end-to-end test
`test_numeric_angle_metadata_survives_required_portable_provenance` observes the
real required-writer `RepresenterError` before the fix and passes afterward.
It uses actual NetCDF `valid_range=[0, pi]`, float32/float64 scalar limits and an
int32 revision. A subprocess without FrameIt reopens NetCDF and
`run-provenance.yaml`, checks prescribed -4 m s-1 samples and strict NaN masks,
selected hours 0/2, the shared original level index and numeric metadata/list
types. The read-only source bytes remain unchanged, including on RED.

In the actual portable descriptor, the scalar angle has `dimensions: []`,
`values: 1.5707963267948966`, and attributes:

```yaml
units: rad
valid_range: [0.0, 3.141592653589793]
valid_min: 0.0
valid_max: 3.141592653589793
calibration_revision: 7
```

The B1 GREEN observes 1 pass. Unfiltered operations/execution/inspection covering
observes 188 passed / 3 failed (191 nodes); each selected old status matches
fix1. Exact required verification observes 163 passed / 35 failed (198 nodes).
The one final full diagnostic observes **1718 passed / 468 failed / 2 errors**
(2188 distinct nodes), with four passing subtests reported separately. Triple
comparison preserves all 2125 Task07 / 2169 original reviewed Task08 / 2187 fix1
statuses and the same 470 failed/error IDs, with no removed IDs or status changes.
Added passing nodes are 63 / 19 / 1 against those respective baselines; the sole
new B1 node passes. The distinct targeted passing union is 351, not a sum of
overlapping checks/subtests. Base/fix1 Ruff on all 19 claimed Python paths
observes 22 / 21 / 21 diagnostics, zero new, not lint-clean.

Exact RED/GREEN and final commands/output paths are in the appended report.
The covering command is:

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_operations.py src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_inspect_metadata.py --tb=short
```

Raw artifacts use `task-08-fix-2-b1-red.txt`, `task-08-fix-2-b1-green.txt` and
the `task-08-fix-2-covering-final-01`, `task-08-fix-2-required-final-01`,
`task-08-fix-2-required-exact-01`, `task-08-fix-2-full-final-01` prefixes.
`task-08-fix-2-failure-ledger.md` retains every current failure/error with all
three prior messages; `task-08-fix-2-node-comparison.json` records exact ID deltas.
The 35 exact-required failed IDs match JUnit. Required/covering/full suites
remain red, not exempted or scientifically passed. The actual published
descriptor/types are retained in `task-08-fix-2-descriptor-observation.txt`.
The scope proof preserves all old operation-test content, every shared producer
and every public source-doc file. Public docs/GUI42 remain lead-owned and were
not touched; existing scientific/qualification gates retain their owners.
Independent B1 closure is pending. Nothing was staged, committed or pushed.

## Independent closure and final lead checks

Spec and quality are independently approved after two fix rounds. I1–I3,
M1, native FA optionality and B1 are closed, with no open task-review finding.
The separate legacy preflight formatting limitation and all later qualification
gates remain recorded; no scientific or human sign-off is inferred.

Fresh precommit command:

```bash
TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_operations.py src/frameit/testing/numerical/test_wind_collocation.py::test_native_horizontal_output_keeps_independent_sparse_mass_w src/frameit/testing/numerical/test_fa_cubes.py::test_native_wind_cube_singleton_metadata_and_numerical_copy src/frameit/testing/numerical/test_fa_cubes.py::test_explicit_wind_cube_analysis_retains_metadata_requirements --tb=short
```

Observed63 passed/520warnings in37.93s: all added Task08 nodes. Final full
1718pass/468fail/2errors and required163pass/35fail remain red; every old status
and exact470 failed/error ID is retained, not an exemption or assertion success.
Final-code guide examples04 pass unchanged with independent readers and3 unchanged
source hashes. The B1 regression separately reopens NetCDF/YAML numeric metadata.

Final documentation commands use frameit_env Python3.13 and worktree PYTHONPATH:

```bash
sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-43
python docs/check_publication.py build/docs-preview/yaml-v3-43
python -m unittest discover -s docs -p test_check_publication.py
python -m pytest -q docs/test_documentation_plots.py docs/test_release.py
```

Strict/publication/13unit/4pytest+2subtests passed with15backend warnings.
All7 affected43 pages exactly equal inspected42HTML. Desktop/narrow checks and
retained preview cover the new guidance without inventing human acceptance.
