# FrameIt YAML v3 Implementation Plan

> **For agentic workers:** Use `subagent-driven-development` to execute this plan.
> Use `executing-plans` for a task that the lead must implement directly.
> Independent review agents are required. Track work with the checkboxes below.

**Goal:** Let researchers select, process, and read their data with a small,
clear YAML file and plain-English documentation.

**Architecture:** Keep the current adapters, numerical methods, runner, and writers.
Resolve source metadata before binding field and level requests. Plan only the
work needed by the requested products. Keep scientific choices in the YAML and
record what the run actually used.

**Tech stack:** Python 3.13 in Conda `frameit_env`; the existing Python, xarray,
NetCDF, Zarr, GRIB, FA, and polar dependencies; pytest; Sphinx.

**Spec:** The binding contracts in this file replace `CHECKLIST.md`.
Their source is planning-repository commit `07b15cf`.
`WHAT_IS_URGENT_TO_DEAL_FOR_UX.md` is historical discussion, not a second spec.

**Code baseline:** local FrameIt `develop`,
`8c2d4bb4a6318c49b60ea85a979a3f8f13bef6b4`.
This document is an implementation plan. Its unchecked tasks are not shipped work.

## 1. Start here; resume here

1. Read FrameIt's `AGENTS.md` and this whole plan once.
2. Start Task 00 in the FrameIt repository. Do not implement in the planning repo.
3. On later sessions, read the execution copy of this plan and `STATE.md` first.
4. Resume owned work first. Otherwise select the lowest-numbered ready task: its
   dependencies are done, it has no blocker, and no worker already owns it.
5. Have the lead record its file claims, then follow the task cycle below.
6. After review, commit the task. The lead updates the state and selects the next task.
7. If a task is blocked, record the exact reason and continue other ready tasks.
8. Stop only when all gates pass or no unblocked task remains. Report either state
   plainly. Never mark a blocked check as passed.

### Execution record

Task 00 creates these files on the FrameIt implementation branch:

```text
docs/development/yaml-v3/CHECKLIST_FOR_AGENTS.md  # Copy of this plan.
docs/development/yaml-v3/STATE.md                # Progress, decisions, and evidence.
```

Only the lead edits `STATE.md`; workers report their claims, progress, and results.
Keep these sections in it:

- Branch, worktree, starting `develop` commit, and plan source commit.
- Task ID, state, owner, claimed files, dependencies, and next action.
- Exact test commands, results, relevant commits, and unresolved failures.
- Technical decisions: evidence, chosen rule, affected tasks, and review result.
- Scientific questions that need a maintainer decision.
- Review findings and their fixes, including full-document coverage records.

Use states `ready`, `active`, `blocked`, `review`, and `done`.
Keep unchecked task boxes until the task is `done`. A code commit alone is not done.
Do not publish these agent records through Sphinx or its downloads/search.

### Branch and worktree

Use a new local branch based on local `develop`, named `feature/yaml-v3` if free.
Use a separate worktree and follow `using-git-worktrees`.
Use native worktree tools when they can select the right base. Otherwise use
`git worktree add -b <new-branch> <new-worktree> develop`.
Choose a new name if the branch or directory already exists.

Record the actual starting commit. If `develop` has moved from the audited baseline,
inspect that diff before planning edits. Keep valid newer work. Do not reset it.
Commit focused changes locally. Never push unless the user asks.

## 2. Global constraints

- Use only `conda run -n frameit_env` or an activated `frameit_env`, with Python 3.13.
- Follow the repository's required skills, scientific safeguards, and check commands.
- Preserve source data and unrelated user work. Use small generated fixtures first.
- Keep existing component boundaries. Do not build a general workflow or plugin system.
- Keep diagnostics optional. Native extraction must work without unrelated dependencies.
- Never guess ambiguous units, field identity, wind basis, time meaning, or grid meaning.
- Keep missing values distinct from zero. Do not fill, clip, smooth, or extrapolate silently.
- Record defaults, assumptions, exclusions, methods, conversions, and incomplete work.
- Check numerical changes against independent values and justified tolerances.
- Tests and plausible plots do not establish scientific validity or human approval.
- Reopen scientific outputs with ordinary readers that do not import FrameIt.
- Teach v3 directly. Do not add v2 migration tools, mappings, before/after examples,
  workflows, or compatibility promises.
- Preserve the public behavior of `frameit init`. Its templates must use v3.
- Update affected public docs, examples, help, and template comments with each task.
- Follow the plain-English rules in Section 3 from the first edit.
- Before a docs-impacting commit, run strict Sphinx and publication checks and inspect
  the rendered pages as required by `docs/source/contributing/documentation.rst`.
- Keep the existing artwork, accessible styling, URLs, and scientific figures where valid.

### Decisions agents may make

The lead may choose small internal APIs, helper placement, task splits, report layout,
and test fixtures. Record decisions used by more than one worker before delegation.
Keep approved public names and defaults fixed.

The following technical rules need evidence before they are fixed:

| Rule | Owner | Required evidence |
|---|---|---|
| Level-value roundoff tolerance | Task 04 | Storage precision and compatible-unit conversion; accept roundoff, reject a different nearby level. |
| Stable grid IDs and auxiliary names | Tasks 03 and 10 | Names stay unchanged when fields are reordered, added, or filtered. |
| Selected-time reads in each reader | Tasks 03 and 05 | Instrument actual scientific payload requests, including multi-time files. |
| Automatic chunks/shards and numerical bounds | Tasks 09 and 11 | Bounded synthetic measurements; exact values, precision, and masks retained. |
| Status command/report/exit details | Tasks 12 and 15 | Existing completion rules and the common report contract. |
| Early request record names and path bases | Task 12 | Failed-attempt recovery and correct YAML/CLI-relative paths. |
| Progress update interval | Task 14 | Useful quiet-run updates with bounded log and runtime overhead. |

Choose these rules from evidence and have an independent reviewer check them.
Do not ask the maintainer to repeat an approved decision.

### Decisions agents must not invent

- The paired tutorial ocean response still needs maintainer approval. Task 17 owns
  that question. Prepare one small proposal with its formula, parameters, and limits.
- A reader that cannot meet selected-time reads needs a documented blocker. Do not
  widen time selection or claim unsupported slicing works.
- New scientific methods, changed physical assumptions, or broader method eligibility
  need the review required by `AGENTS.md`.
- Human scientific sign-off and human usability acceptance require a person.
  Agree the usability-review protocol with the maintainer before Task 21's walkthrough.

Gather unresolved scientific questions in `STATE.md`. Ask one focused question when
it blocks a task, while continuing independent work. Full autonomy does not permit
inventing scientific approval or hiding a missing capability.

## 3. Plain English, everywhere researchers read

Apply these rules to the README, published pages, CLI help/errors, examples,
template comments, figure captions, and alternative text.

- Use common words and direct verbs. Write one idea per sentence.
- Prefer short sentences. Split a sentence that needs a second reading.
- Say what the reader must do, which setting matters, and what result to expect.
- Explain a necessary technical term once, beside the choice it affects.
- Delete a sentence unless it helps someone choose, run, read, or fix something.
- Remove repeated explanations. Keep one canonical explanation and link to it.
- Remove slogans, filler, promotional claims, and text about the writing process.
- Avoid phrases such as “seamlessly”, “unlock”, “it is important to note”,
  “as discussed above”, and “this comprehensive guide”.
- Keep agent instructions, review history, implementation updates, and approval
  discussions out of published docs.
- Comments explain a needed reason, unit, assumption, or limit. They do not narrate
  obvious Python, shell, or YAML syntax.
- Keep scientific meaning exact. Shortening must preserve units, defaults,
  missing-data rules, method limits, and source evidence.
- Show complete runnable examples. Keep fragments clearly labelled and supplementary.
- Put the smallest complete plotting script on the task page. Use that same script
  to produce the figure from the demonstrated FrameIt output.
- Explain FrameIt's operation and output. Leave interpretation of the event to the reader.

Example:

```text
Avoid: It is important to note that users should ensure the configuration is
       appropriately validated prior to initiating the processing workflow.
Use:   Run `frameit validate case.yaml`, then fix any reported errors.
```

Tasks 20 and 21 require separate, critical reviews of the entire documentation.

## 4. Task cycle and subagent rules

Use this cycle for every implementation task:

- [ ] Read its contracts, named files, callers, and tests. Check current branch state.
- [ ] Add or update the smallest meaningful test for the changed behavior.
- [ ] Run it and confirm the intended failure before changing implementation code.
- [ ] Implement the smallest complete change. Preserve validation and error handling.
- [ ] Run the task's tests and all affected caller tests. Record exact results.
- [ ] Update the relevant docs, examples, help, and comments in simple English.
- [ ] Run the required documentation checks when public material changes.
- [ ] Get an independent review of the contract, code, tests, and documentation.
- [ ] Fix findings and rerun affected checks. The reviewer must verify each closure.
- [ ] Review the diff, stage only task files, and commit. Report the result to the
  lead for the `STATE.md` update.

For prose-only work, use document review and build checks instead of a contrived
unit test. Do not disable failing tests just to make a task look complete.

### One worker, one bounded task

Give each worker this packet:

```text
Task ID and goal:
Starting commit and assigned worktree:
Read: AGENTS.md, this plan's global rules, relevant contracts, and this task.
Inputs and required interfaces:
Files this worker may edit:
Files owned by the lead or other workers:
Tests, docs, and acceptance checks:
Known blockers and decisions already made:
Return: commit/diff, changed interfaces, exact checks, and unresolved findings.
```

Use separate worker worktrees or disjoint file ownership. Do not let two workers
edit the same shared file. This applies to `configuration.py`, `settings_class.py`,
`preflight.py`, `runner.py`, `execution.py`, `cli.py`, and shared test helpers.
The lead owns integration, the state record, and shared public contracts.

Parallel work is allowed only when dependencies are complete and files do not
overlap. Adapter-specific workers may run together after their common contract is
fixed. Readers and reviewers may work in parallel. Never merge unreviewed results.

An independent reviewer must not have written the work being reviewed. Give the
reviewer the task, spec, code, and evidence; do not ask for approval of a summary.
Require file/line references, a concrete failure or unclear sentence, and a remedy.
The lead verifies the combined result after integration.

## 5. Review focus

These cases cross component boundaries. Their owning tasks must test them.

| Case | Expected result | Owner |
|---|---|---|
| A selected multi-time file contains excluded times | No excluded scientific samples are read, even for tracking or derived inputs. | 03, 05, 06, 09 |
| U, V, and W have different native grids | Keep each grid; one selected level stays a length-one axis. | 04, 08, 10 |
| A second source has different times, cycles, or masks | Preserve them unless a requested operation uses an explicit association. | 03, 06, 09, 10 |
| A run fails before or during export | Keep its request and accurate published-product inventory; never claim completion. | 12, 14, 19 |
| Parent and spawned workers can see different editable installs | All workers use the selected FrameIt code; diagnostics show its location. | 01, 19 |

## 6. Binding contracts

Read the relevant contract before each task. The rules below are the approved
behavior. Task implementation must not change them to simplify an adapter.
Example radii, counts, thresholds, CPU counts, and chunk sizes are not defaults.

### C1. Sources and files

- Use top-level `sources`, keyed by user-chosen source names. Single-source runs use
  the same structure. Put `model`, files, selections, and interpretation in each source.
- Remove the top-level model and repeated `input.sources.<name>.input` wrapper.
- Allow one source per physical type: `atmosphere`, `ocean`, and `surface`.
  Atmospheric AROME/Meso-NH are atmosphere; CROCO/NEMO are ocean; a separately
  supplied, supported SURFEX stream is surface.
- Derive the type from the admitted model/file profile and reliable metadata.
  Do not expose a `type` override. Source names and selected fields do not set type.
- AROME atmosphere and AROME-produced SURFEX can both use `model: arome`.
  Their admitted profiles distinguish them. Embedded Meso-NH SURFEX fields remain
  part of that atmospheric source, even if only `SST` is selected.
- Detect model/format only from reliable, unambiguous evidence. Keep explicit
  declarations and report conflicts. Keep reader-library settings separate.
- `files` accepts a path, glob, or list of paths/globs. Retain explicit `exclude`.
  Resolve every YAML path from its YAML directory, including auxiliary files.
- Use only the selected inventory after exclusions. Never discover another format
  or stream to supply missing dependencies.
- Discover supported time-split and field-split layouts without a public layout switch.
  Preserve distinct native grids within one source, including ocean T/U/V/W files.
- Order records by decoded timestamps. Record the selected inventory and order.
- Deduplicate paths, symlinks, and hard links to the same physical file. Report
  overlapping patterns. Separate copies remain separate providers; do not hash
  whole archives to decide whether they are equivalent.
- Different providers for the same requested field/level/time/cycle fail by default.
  Resolve them with `files`, `exclude`, or `time.cycle`. There is no first/last or
  provider-priority option. If whole-file exclusion loses needed records, explain
  that the inputs must be made unambiguous upstream.
- Skip a matched file only when metadata proves it supplies no requested field or
  required dependency. Report why. Unreadable files and competing providers fail.
- Do not add a blanket single-domain or single-ensemble-member restriction.
  Apply the approved source-type and field/provider ambiguity rules.
- Independent native extraction preserves each source's own times, cycles, grids,
  and masks. Associate sources only for an operation that needs it.

Top-level fragment:

```yaml
sources:
  atmosphere:
    model: mesonh
    files: ./data/mesonh/*.nc
    variables:
      2d: [UM10, VM10, MSLP]
      3d: [UT, VT, WT, T]
      levels:
        indices: [0, 5, 10]
  ocean:
    model: croco
    files: ./data/croco/*.nc
    variables:
      3d: [temp, salt]
```

These names are examples. Inspect the actual files before selecting fields.
The ocean keeps all its levels; it does not inherit atmospheric level selection.

### C2. Time selection

- Optional `sources.<name>.time` applies only to that source. Omission keeps all times.
- `start` and `end` select existing decoded timestamps inclusively. Bounds need not
  be stored labels. Preserve the source calendar; an empty result is an error.
- `values` selects exact timestamps instead of a window. Every requested timestamp
  must exist. Process them in chronological order.
- `stride: N` selects every Nth available record after the window, starting with the
  first record. It does not create a regular time series or interpolate.
- Time selection restricts scientific field reads for extraction, trackers, derived
  inputs, and polar processing. Do not read excluded intermediate field samples.
  Metadata and coordinate reads may establish the selected inventory.
- If a method needs unavailable temporal support, fail with that reason. Do not
  silently calculate a denser track and thin only its exports.
- If several forecast cycles exist, require `time.cycle` as an exact reference time.
  It may accompany a window or exact timestamp selection. Do not choose the latest
  cycle or merge cycles silently.
- Different cycles of one physical source type use separate runs. Different physical
  sources may use different explicitly selected cycles. Keep method-specific cycle
  constraints; equal valid timestamps do not prove equal cycles.

Inside `sources.<name>`:

```yaml
time:
  cycle: "2026-01-01T00:00:00"
  start: "2026-01-01T00:00:00"
  end: "2026-01-02T00:00:00"
  stride: 2
```

### C3. Fields and levels

- Use `variables.2d` for horizontal source fields without a selectable vertical axis, and
  `variables.3d` for fields with one. Time is not a spatial axis.
- Discover native groups and dimensions. A single selected level of a 3D field
  remains a `3d` request and retains a vertical dimension of length one.
- A wrong category is an error. Show the source type and corrected YAML.
- Ordinary selectors are source field names. Distinct fields sharing a requested
  name within one source are unsupported. Identify the conflicting fields; never
  choose one or offer a qualified selector. Repeated times of one field are allowed.
- Reject duplicate field requests by resolved identity. Keep name ambiguity separate
  from competing providers of the same record.
- One optional `variables.levels` applies to every requested 3D field and 3D derived
  result in that source, on each requested product's representation. No per-field,
  per-result, or separate polar level overrides exist. It does not affect 2D fields.
- Omission keeps all available levels on each field's grid. Their axis lengths may differ.
- When subsetting, choose exactly one of `indices`, `values`, or `domain: physical`.
  Selection alone never interpolates vertically.
- Indices are zero-based, nonnegative original positions on the applicable grid.
  Allow lists and inclusive ranges: `{start: 0, end: 20, step: 2}`.
- Values select existing labels. Allow lists and inclusive intervals:
  `{min: 700, max: 850}`. Interval bounds need not be stored labels.
- Preserve explicit list order. Intervals and all-level selections keep grid order.
  Reject duplicate or unavailable levels, even if only one selected field lacks them.
- `domain: physical` excludes only adapter-verified extra/boundary levels.
  Unknown physical ranges fail. Do not guess halos or renumber explicit indices.
- After an explicit grid-changing transform, select on the destination grid.
  Native W index 5 is an interface; W remapped to mass points uses mass index 5.
  A model-grid remap does not also remap polar W.
- Use a small, justified roundoff tolerance for value matching. Do not inherit an
  unexplained backend tolerance or accept a genuinely different nearby level.
- Optional `units` describes requested values and exported vertical coordinates.
  It can accompany any strategy or stand alone to convert all coordinates.
- Convert compatible units for matching and export. For example, `850 hPa` selects
  an existing `85000 Pa` coordinate and exports `850 hPa` without interpolation.
- Without requested units, use source or destination coordinate metadata.
  Value selection across axes with different known units requires explicit units.
  Index-only selection does not require equal units across axes.
- If source units are absent and requested units exist, assume the stored numbers
  already use those units. Do not rescale. Warn in validation and logs; record a
  user-supplied assumption, not observed metadata.
- If both units are absent, warn in validation and logs. Do not invent units or fail
  solely for this absence. Other required physical checks may still fail.
- Keep values, units, bounds, and coordinate names consistent. Vertical-coordinate
  conversion does not change the physical data variable's units or values.
- Report the selection grid, source support, units, and unavailable levels before
  writing products. Spatial neighbours may be read only for an explicit method.

Inside `sources.<name>`:

```yaml
variables:
  3d: [u, v, t]
  levels:
    values: [850, 700]
    units: hPa
```

```yaml
variables:
  3d: [UT, VT, WT]
  levels:
    domain: physical
```

### C4. Source meaning, transforms, and derived fields

- Native extraction preserves source samples, grids, units, masks, and quantities.
  Internal tracker preparation must not change exported base fields.
- Put source declarations under `field_metadata`. They describe stored values;
  they do not request numerical conversion. Fill gaps and record their origin.
  Contradictions with reliable metadata fail. Keep any admitted producer-specific
  exception narrow and explicit.
  Declaration keys include `units`, `kind`, and `temporal_kind`. For example,
  `{units: K, kind: continuous, temporal_kind: instantaneous}` describes an eligible
  temperature field; these values are not defaults.
- `interpretation: mesonh_surfex_sea` opts into the existing SEA rules for selected
  eligible fields and their required support data. Remove the repeated
  `surfex_fields` selection. Omission keeps ordinary native access.
- Preserve the SEA producer/quantity limits, fractional support, real zeroes,
  sentinel handling, and unrelated fields for which a number such as 999 is valid.
- Put FA `profile` beside model/format. Keep explicit source-local `native_cubes`.
  Inspection may propose record associations but must not silently decide vertical
  meaning from record names. Select a declared cube through `variables.3d`.
- A cube retains `records`, `vertical_position`, and `sampling`, plus admitted
  `vector_basis` and `component_scaling` for wind cubes.
  `field_metadata.<cube-name>` supplies scientific declarations.
- Keep FA-specific `fa.subdomain`, `fa.earth_radius_m`, and `fa.expected_source`.
  Do not broaden admitted FA profiles, encodings, scaling, or reconstruction methods.
- Put technical options under source `reader`: `engine`, `chunks`,
  `python_executable`, `timeout_seconds`, and `max_points` where applicable.
  NetCDF engines remain `h5netcdf`, `netcdf4`, and `scipy` for their supported encodings.
  The last three options are FA-only: helper interpreter, helper timeout, and
  decode-size guard, respectively. Reject them on other formats.
  Input chunks use input dimension names.
- Native copying of one wind component does not require a pair, basis declaration,
  or unselected companion. Operations that need them use reliable metadata first.
- When needed, declare `wind_pairs` entries with `u`, `v`, and `basis`, without groups.
  Resolve supported rotation from adapter evidence and report the chosen method.
- `wind_pairs[].rotation.method` accepts `coordinate`, `geolocation`, or
  `mesonh_projection`. The `coordinate` method uses the `coordinate` setting.
  `mesonh_projection` uses the applicable `BETA`, `RPK`, and `LON0`.
  Missing geometry and conflicts fail. A declaration does not itself rotate exports.
- Source-local `transforms` target explicit `fields`. Separate
  `sampling: native | mass`, `basis: native | earth`, and compatible `units` conversion.
  Unsupported combinations fail. Mass points are model cell centres, not fixed heights.
- Control W separately from U/V. W remapping changes sample locations, not its
  physical quantity. Pressure vertical velocity remains pressure vertical velocity.
- Transforms govern model-grid exports. They do not silently alter polar preparation,
  tracking, or another calculation. Required spatial neighbours remain within selected times.
- Source-local `derived` maps an output name to a supported `method` and explicit
  `inputs`. Do not add speed or radial/tangential winds merely because U/V are selected.
- Load required calculation inputs internally. Export them only when requested.
  Fail on collisions with another exported field; do not rename or overwrite it.
- Calculate only results needed by requested products or another requested operation.
  Each method keeps its own documented preparation and vertical grid.
- Polar wind speed is the magnitude of components sampled at polar points.
  It is not an interpolation of speed calculated earlier on the model grid.
- Expose only admitted methods with honest maturity and requirements. Testing helpers
  do not become stable diagnostics merely because they exist in the repository.

Inside `sources.<name>`:

```yaml
wind_pairs:
  - u: UT
    v: VT
    basis: grid
transforms:
  - fields: [UT, VT]
    sampling: mass
    basis: earth
  - fields: [WT]
    sampling: mass
derived:
  speed:
    method: wind_speed
    inputs: {u: UT, v: VT}
```

### C5. Regions, tracks, and associations

- Use one top-level `region`. Omission means full-domain model-grid extraction,
  without tracking or an invented centre.
- `region.center`, `region.track`, and `region.tracker` are mutually exclusive.
- Fixed centres use named `latitude` and `longitude`. Model-grid crops use
  `region.width_km: {x, y}`, with full widths in kilometres.
- Apply one geographical request independently to each source. Different requests
  use different runs. There are no per-source region overrides or reference-source
  requirements for fixed geometry.
- Crop along each source's native x/y directions. A rotated grid may give a rotated
  crop. Do not interpret this as an Earth-relative east/north rectangle.
- Preserve source samples. Report requested versus realised centres, extents, and
  orientation where needed. Exact recentering requires an explicit transform.
- Pad partially covered crops with missing values and report coverage. A centre
  outside a required source footprint fails; do not move it silently.
- Calculated tracking always uses the atmospheric source, whatever its name.
  Do not expose a tracker-source selector. Require `region.tracker.method` and put
  method settings directly under `tracker`, without repeated method nesting.
- Resolve tracker dependencies separately from exported fields. Explain them in
  preflight. They obey source time selection and do not redefine native exports.
- For `pressure_wind`, `region.tracker.search_width_km` and
  `region.tracker.refine_width_km` are full square widths, defaulting to 200 and
  100 km. Preserve the old 100/50 km half-width geometry.
- Use `*_radius_km` only for genuine circular/geodesic searches, including an initial
  search around a supplied position. Public sizes and steps use kilometres.
  Numerical tolerances may retain explicit metre names such as `tolerance_m`.
- `region.tracker.on_incomplete` defaults to `error`. Allow explicit `keep_prefix`
  only where supported, with incomplete outputs/status clearly marked.
- A supplied trajectory uses only `region.track.file`, a NetCDF path. Discover
  coordinates from file evidence; do not expose coordinate-name overrides.
- Export trajectories as `time(time)`, `latitude(time)`, and `longitude(time)`.
  Use CF-decodable time with explicit units/calendar; latitude/longitude have
  matching standard names and `degrees_north`/`degrees_east` units.
- Trajectory timestamps must be unique; positions finite; export order chronological.
  Accept unambiguous CF metadata or conventional `time`, `latitude`/`lat`, and
  `longitude`/`lon` names with consistent units and dimensions identifying the same
  one-dimensional trajectory. Equal lengths alone are insufficient. Incompatible
  dimensions, ambiguity, missing units, contradictory identification, or duplicate times fail.
- Extra track times are allowed. Missing centres at required source times fail by
  default. Do not interpolate or silently shorten extraction.
- Use `region.sources_coupling_time_association`: default `exact`, explicit `common`,
  or the admitted `preceding_hour` method. Exact means a centre at each selected
  source sample; source timelines need not otherwise be identical.
- Common-time association reports excluded records. Apply association only to the
  operation needing it. Do not widen source selections or alter independent extraction.
- Preserve the narrow AROME/NEMO instantaneous/hourly-mean `preceding_hour` contract.
  Keep source labels, bounds, sampling meaning, and method-specific cycle rules.
  Do not replace it with generic nearest-time matching.
- Preview known coverage and geometry. Mark calculated centres and value-dependent
  checks as pending until execution.

Top-level fragment:

```yaml
region:
  tracker:
    method: pressure_wind
    search_width_km: 200
    refine_width_km: 100
    on_incomplete: error
  sources_coupling_time_association: exact
  width_km: {x: 400, y: 400}
```

### C6. Products and polar sampling

- Top-level `products` requests `model_grid`, `polar`, and/or `track`. Products drive
  computation. Remove independent computation/export switches.
- Omitted `products` means model-grid output only. An explicit empty mapping is an
  error. Omit unrequested products; use `model_grid: true`, `track: true`, or configured
  product mappings. A listed product is the request to produce it.
- Field products reuse source `variables` and `derived`. Optional `fields` gives
  exact lists by source name. It narrows declared requests; unlisted sources/fields
  are excluded. Reject unknown references. Internal inputs need not be exported.
- The source's shared level selector applies to every requested representation.
- Polar output reuses the region's centre provider and requires `radius_km`.
  It does not require model-grid export or `region.width_km`.
- Derive polar input support separately from the exported model-grid crop.
  Changing only the crop must not alter polar coordinates or remove needed support.
- Optional `radial_step_km` defaults to each source's native spacing. Reject
  finer-than-supported-native spacing and report the supporting evidence.
- `azimuth_count` is the sole angular control. Omission uses the documented automatic
  outer-ring spacing rule. Report the resolved count and angular spacing.
- Use full rings clockwise from north, radians plus a degree helper, and no duplicate
  endpoint. Include the exact outer radius; report any shorter last radial interval.
  These are point samples, not area averages or a conservative area remap.
- `shared_grid: true` opts into a common target. Otherwise resolve each source's grid.
  Automatic shared spacing uses the coarsest participating source. Keep source masks,
  vertical grids, quantities, and the explicit time-association policy distinct.
- Default to bilinear interpolation for proven continuous fields and nearest-neighbour
  for proven categorical fields. Evidence may be metadata or a declaration.
  Unresolved kind fails; do not guess it from a name.
- `missing_data_policy` defaults to `strict`. Explicit `renormalize` requires a
  `min_valid_weight_fraction`. Entirely missing or unmapped points remain missing.
  Preserve valid zeroes and export mapping, support, and status information.
- Per-field overrides use `products.polar.field_options.<source>.<field>`.
  Keys are `interpolation: bilinear | nearest`, `missing_data_policy: strict | renormalize`,
  `min_valid_weight_fraction` (required for `renormalize`), and admitted `sampling: native | mass`.
- Options may target exported source fields or internal inputs needed by a polar
  calculation. They do not request exports. Unused targets and inapplicable
  combinations fail, including nearest-neighbour plus partial-stencil renormalization.
- For derived speed, interpolation options apply to U/V inputs. Preserve
  magnitude-after-sampling. Polar W keeps native vertical locations unless its own
  field option explicitly requests supported W-to-mass remapping.
- Derive spatial support automatically. Advanced polar `processing` keys are
  `chunks`, `max_target_points`, `plan_cache.entries`, `plan_cache.max_bytes`,
  `source_halo_points`, `weight_zero_tolerance`, and `profile`.
  Insufficient halos fail. Record numerical weight tolerance in provenance.
  `products.polar.processing.profile` controls performance measurements.
- Preview effective fields, grids, methods, coverage policy, input footprint, and
  target-point counts. Counts are not whole-run memory limits. Fail without silently
  coarsening the grid, dropping fields, or shortening times.
- `products.track: true` explicitly requests a reusable NetCDF trajectory, including
  track-only runs. Load only needed inputs/support. A centre provider alone does not
  request a track file. Field products retain their needed centres and provenance.

Top-level fragment:

```yaml
products:
  model_grid: true
  polar:
    radius_km: 200
    azimuth_count: 180
    fields:
      atmosphere: [MSLP, speed, WT]
    field_options:
      atmosphere:
        UT:
          interpolation: bilinear
        WT:
          sampling: mass
```

The fragment needs source declarations and a centre provider.

### C7. Outputs and coordinates

- `output.format` is `netcdf` by default or `zarr`. Select one field format per run.
  Requested trajectories always use NetCDF, even beside Zarr field products.
- Write one field dataset per source/product. Keep distinct native grids and axes
  within it; do not let xarray align or merge scientifically different coordinates.
- Name fields `<run.name>.<source>.<product>.nc` or `.zarr`, with product
  `model_grid` or `polar`. Name tracks `<run.name>.track.nc`.
  Honor the user's run name; `analysis` is not a fixed prefix.
- Keep `products/`, `logs/`, `cache/`, and run configuration/provenance/status records.
  Resolve `output.directory` relative to the YAML file. Inventory product paths are run-relative.
- Protect paths, source inputs, unrelated files, and filename collisions.
  `output.overwrite` defaults to `false` in runtime, templates, and CLI.
  Explicit replacement retains exclusive ownership and publication safeguards.
- Keep NetCDF4 and sharded Zarr v3 contracts. Compression defaults to level 1,
  with coordinate compression off. Do not add lossy packing or lower precision.
- Under `output.writer`, support applicable `engine`, `unlimited_time`,
  `compression.level`, `compression.coordinates`, `chunks`, and `shards`.
  `engine` and `unlimited_time` are NetCDF-only; `shards` is Zarr-only.
  NetCDF engines are `netcdf4` or `h5netcdf`.
- Reject explicit settings that do not apply. A separate NetCDF track does not make
  NetCDF-only field-writer options valid for Zarr fields. Unlimited time does not
  promise append/resume support.
- Record effective encoding and ordinary-reader requirements. Storage chunks/shards
  use exported dimensions and element counts, not physical resolution.
- Map each requested field/result to source, relative dataset path, stored name,
  dimensions, units, and representation. Preview planned paths; record actual publications.
- `run-status.yaml` remains authoritative. Distinguish completed, incomplete, failed,
  interrupted, and last-known running attempts. Preserve per-product publication
  limits, including the Zarr replacement visibility gap.
- Optional `metadata.institution` has no institutional default. `metadata.extra`
  holds annotations. Remove informational `ocean_model`/`wave_model` controls.
  Annotations cannot override generated scientific provenance.

Horizontal model-grid names:

| Grid | Dimensions | Geographic coordinates |
|---|---|---|
| Atmospheric/SURFEX centres | `y`, `x` | `latitude`, `longitude` |
| Meso-NH U | `y`, `x_u` | `latitude_u`, `longitude_u` |
| Meso-NH V | `y_v`, `x` | `latitude_v`, `longitude_v` |
| NEMO T | `y_t`, `x_t` | `latitude_t`, `longitude_t` |
| CROCO rho | `y_rho`, `x_rho` | `latitude_rho`, `longitude_rho` |
| CROCO U | `y_rho`, `x_u` | `latitude_u`, `longitude_u` |
| CROCO V | `y_v`, `x_rho` | `latitude_v`, `longitude_v` |

Horizontal dimension coordinates are local zero-based array positions, even in a
crop. Preserve original native coordinates and indices as auxiliaries. Geography
describes actual sample positions and includes time when positions move. Each field
references its own coordinates. Adding a field must not rename another field's axes.
The table does not admit new grids or adapters.

Vertical names:

| Meaning | Name |
|---|---|
| Pressure | `pressure`, with actual units in metadata |
| Height above ground | `height_above_ground` |
| Meso-NH native levels | `level`, `level_w` |
| FA native full/interface labels | `level`, `level_w` |
| NEMO depth | `deptht`, `depthu`, `depthv`, `depthw` |
| CROCO sigma | `s_rho`, `s_w` |

Preserve original labels, units, definitions, bounds, and formula dependencies.
Native model, hybrid, and sigma coordinates do not become fixed pressure/height/depth.
Qualify colliding distinct axes using inventoried grid identity, resolved before
field filtering. Keep other admitted native names unless a physical mapping justifies
a clearer name. Record original coordinate identity in provenance.

Polar names are `radius(radius)` in `km`, `azimuth(azimuth)` in `rad`, and
`azimuth_degrees(azimuth)` in `degrees`. Fields use their own vertical axis, then
`radius, azimuth`. Geographic sample positions include time when needed.
Centres are `center_latitude(time)` and `center_longitude(time)`.

### C8. Resources and chunks

- Optional `resources.cpus` is the ordinary CPU budget. Omission uses detected
  allocation/affinity limits. Requests above the available limit fail actionably.
- Coordinate reader, compute, export, and native-thread concurrency within that
  budget. Account for nested pools; do not multiply counts into oversubscription.
- Advanced keys are `scheduler: threads | synchronous`, `compute_workers`,
  `export_workers`, `native_threads`, and `synchronous_export`.
  Defaults are `threads`, one native thread, asynchronous export, and automatic workers.
- Use automatic layouts first. Input chunks live under source `reader`;
  computation chunks under each product's `processing`; storage under `output.writer`.
- Fail if an explicit dimension matches no applicable target. Otherwise show which
  datasets use it; it need not exist in every product.
- Report resolved sizes and unresolved runtime choices. Estimate arrays, workspace,
  and storage honestly, including full-record decoder costs. Do not present an
  estimate or point guard as an enforced memory ceiling.

### C9. CLI, reports, and execution UX

- Require integer `schema_version: 3`; reject booleans and unsupported versions.
  Optional controls use omission for defaults. Reject `null` with guidance to omit
  the key. Accept empty mappings only when that block needs no required entries.
  This rule does not restrict arbitrary annotation values in `metadata.extra`.
- Preserve `init` model/named-recipe selection, `--tracking`, `--coupling`, `--output`,
  `--force`, defaults, supported combinations, and named-recipe composition restrictions.
  Default output stays `frameit.yaml`. Do not add `--task` or `--from`.
- Templates retain their selected workflow and clearly marked instructional values.
  Surface any conflict between preserving behavior and updating schema.
- Ordinary commands use the same authored file:
  `inspect <file>`, `validate <file>`, and `run <file>`.
- Inspection accepts unfinished source requests. Show available field types, units,
  levels, times, resolved paths, unresolved facts, and copyable valid selectors.
  Do not offer qualified selectors for unsupported duplicated names.
- `validate` combines schema, metadata/coordinates, required installed dependencies,
  and a readable plan. `--schema-only` opens no input datasets and states what was
  not checked. Ordinary validation and shared preflight read metadata and needed
  coordinates only; they must not read scientific payloads.
- `run` shares preflight semantics. Retire `run --dry-run` and `config show --resolved`.
- `config show` presents the authored request. `config show --effective` presents
  applicable effective settings, origins, inputs, plan, and pending execution facts.
  Do not rewrite the authored file or put pending markers inside valid controls.
- Add `capabilities`: actual source/method support, required inputs/dependencies,
  limits, and documented maturity. Keep its docs tied to implemented support.
- Generate a versioned editor JSON Schema from authoritative configuration definitions.
  Keep field names in inspection and input-dependent scientific checks in preflight.
- Human reports show fields, times/cycles, levels, assumptions, transforms,
  dependencies, associations, regions, products, paths, and resources.
- Collect independent errors across selected files/sources in one pass. Group repeats;
  show affected records, YAML locations, expected/observed facts, and valid repairs.
  Mark checks blocked by another error. Do not make up scientific workarounds.
- Use `--json` on `inspect`, `validate`, `capabilities`, and `config show --effective`.
  Emit one document with `report_version`, `command`, `status`, `data`, `warnings`,
  `errors`, and `deferred_checks`. Logs/progress go to stderr. Failure stays nonzero.
  Plain `config show --json` presents the authored mapping.
- Effective data sections are `configuration`, `origins`, `inputs`, `plan`, and
  `pending`. Origins distinguish YAML, CLI, default, input evidence, and automatic choice.
- Use these operational flags on `validate`, `run`, and `config show --effective`:
  `--output-directory PATH`, `--cpus N`, `--overwrite`, `--no-overwrite`, and
  `--log-level DEBUG|INFO|WARNING|ERROR`.
- Overwrite flags are mutually exclusive. Precedence is CLI, YAML, defaults.
  CLI paths are launch-relative; YAML paths remain YAML-relative. Record origins.
  Scientific selections stay in the YAML.
- Save the authored request, overrides, and available code identity at attempt start.
  Preserve path bases. Add actual resolved facts later and keep pending facts explicit.
- Add a lightweight status entry point and matching final summary. Show completion,
  actual fields/paths, exclusions, warnings, failure context, applicable recovery
  guidance, and ordinary-reader help.
  It must work without the original archive and without full payload scans.
  A last-recorded `running` state does not prove the process is still alive.
- Add rate-limited progress with operation/source, honest completed counts, elapsed
  time, and last activity. Distinguish preparing lazy work from computing/writing it.
  Do not invent percentages or completion estimates, force eager computation, or
  read more data just to report progress.
- Fix CLI user-site filtering so parent and spawned workers keep the selected
  FrameIt installation while retaining the intended user-site-package exclusion.
  Show the imported installation location in diagnostics.
- Document repeated complete-YAML runs and a Slurm-array equivalent. Each attempt
  gets a fresh output root and an accurate result inventory. Preserve each tracking
  timeline and the existing retry/publication policy.

### C10. Tutorials and practical acceptance

- Keep a complete small first run with independently readable outputs.
- Use task pages for native extraction, levels/times, fixed/moving regions, multiple
  sources, transforms, polar products, and reading results. General rules belong in
  general guides, not only in an unrelated model/format page.
- Reuse canonical YAML, generators, and scripts verbatim in docs and automated tests.
  Label instructional data clearly. Preserve existing-file refusal.
- Start analytical cases near 41×41 horizontal points and five times, a few megabytes
  per case. Enlarge only where a method's required support demands it.
- Use stationary and translating cases with known centres and a reusable NetCDF track.
  State motion/vector conventions. Moving sample positions do not subtract storm motion.
- Use three saved levels and four interfaces where needed, with known profiles.
  Include mixed grids, singleton levels, units, and explicit W remapping.
- Add a controlled missing/category variant for strict coverage, renormalization,
  categorical sampling, and valid zeroes.
- Use the prescribed atmospheric formulas below. Reuse the existing analytical
  vortex's geodesic/vector convention. Generate source values directly from formulas,
  not through the production interpolator being tested.

```text
V_theta(r) = V_max * (r / R) * exp((1 - (r / R)^2) / 2)
p(r)       = p_infinity - delta_p * exp(-(r / R)^2)
```

`r` and positive `R` are distances in consistent units. `V_max` is signed;
`delta_p` is positive. Wind magnitude peaks at `r = R`, with zero wind at the centre.
Pressure is minimal at the centre. Record parameters, circulation sign, units,
coordinates, and tolerances for the coarse grid. No dynamical balance is claimed.

The coarser ocean source must describe the same prescribed event, with a stated
relation to its track, timing, and footprint. Preserve its own grid, quantities,
and explicit association. Its response formula and parameters still need maintainer
approval. Keep fixture definitions separate from task instructions and interpretation.

Run complete tasks from setup through independent reading. Cover mixed grids,
singleton levels, sparse times, adding a source, polar-only output, and error repair.
Measure fixture size, generation/run time, and memory. Human review must assess
usability; automated tests cannot substitute for that acceptance.

## 7. Implementation order

The lead owns shared orchestration files. Each task is a reviewable unit, not a
single large commit. Use the task cycle in Section 4 for each tested increment.
Read every listed contract in full; the test cases below highlight likely failures.

Tasks 02–05 first prove the schema, metadata binding, and native execution APIs.
They do not depend on the later CLI/template/catalogue conversion. Their commands
below name focused tests to add for these milestones. Complete public-command and
producer suites run in Tasks 15–16 and 19. For other mixed suites, record the exact
applicable test nodes before starting; assign future-dependent checks to their
owning task. Do not skip a regression in behavior already delivered, weaken an
assertion, or mark a failed check as passed. The final full suite remains required.

| Done | Task | Needs | Deliverable |
|---|---|---|---|
| [x] | 00 | — | New branch, baseline, state record, ownership map |
| [x] | 01 | 00 | Correct parent/worker installation identity |
| [x] | 02 | 01 | Strict v3 schema and shared execution interfaces |
| [x] | 03 | 02 | Source inventory and selected physical records |
| [x] | 04 | 03 | Field identity and shared level binding |
| [x] | 05 | 04 | Native NetCDF slice, then selected-record adapter reads |
| [ ] | 06 | 05 | Regions, trajectories, tracking, time associations |
| [ ] | 07 | 05 | Explicit SEA and FA source interpretation |
| [ ] | 08 | 07 | Explicit transforms and derived requests |
| [ ] | 09 | 06, 08 | Product-driven polar processing |
| [ ] | 10 | 09 | Complete coordinate and writer contract |
| [ ] | 11 | 10 | CPU budget and chunk/storage settings |
| [ ] | 12 | 10 | Early request records and accurate publication status |
| [ ] | 13 | 11, 12 | Shared preflight, errors, and structured reports |
| [ ] | 14 | 13 | Integrated execution and honest progress |
| [ ] | 15 | 14 | CLI, preserved init, capabilities, editor schema |
| [ ] | 16 | 15 | All config producers and canonical examples use v3 |
| [ ] | 17 | 16 | Analytical tutorial cases and task pages |
| [ ] | 18 | 16 | Repeated-case and Slurm-array examples |
| [ ] | 19 | 16, 18 | Integration, installed-package, and failure checks |
| [ ] | 20 | 17, 19 | Two full documentation review passes |
| [ ] | 21 | 20 | Final independent review, human acceptance, handover |

Task 17's ocean approval must not delay Tasks 18 or 19. Task 20 may review finished
pages early, but cannot close until the complete documentation exists. Request
scientific decisions early; do not leave them until the final gate.

### Shared interfaces

Keep these existing entry points. Change their internals and all callers together.
The signatures below describe the baseline; any necessary signature change must be
recorded with its caller list before another worker uses it.

| File, relative to `src/frameit/` | Entry point and handoff |
|---|---|
| `core/configuration.py` | `resolve_schema(raw, *, base_dir=None)` returns the resolved document and request mappings. `to_runtime(raw, *, base_dir=None)` returns `SimulationConfig` arguments. `source_document(parent, name)` builds a source-local document. |
| `io/loader.py` | `discover_input_files(config)` and `resolve_input_files(files, *, strict=False)` resolve inventory. `DatasetResources` owns opened resources and cleanup. |
| `core/coupled.py` | `prepare_sources(conf, *, check_output=True, execution_options=None)` returns `(plan, children, child_plans)`. Remove compulsory tracking/common-time behavior; retain source-local configurations. |
| `core/preflight.py` | `open_metadata(files, conf, resources, *, chunks=None)` yields `(path, datasets)`. `preflight(conf, *, input_files=None, check_output=True, execution_options=None, resources=None, include_variable_metadata=False)` returns the plan. |
| `processing/requests.py` | `normalize_requests(raw)`, `selected_native_indices(ds, req, vert_dim)`, and `build_group_ds(ds, req, group_key, concat_dimension, float_tol, *, vertical_dims=None)` bind selections. |
| `io/*_utils.py` | `concat_nc2ds_by_vert_coord`, `concat_grib2ds_by_vert_coord`, and `concat_fa2ds_by_vert_coord` return `(user_groups, tracker_groups)`. Add keyword-only `selected_records=None`; v3 calls must supply the source's selected records. Preserve internal numerical callers. |
| `processing/extraction.py` | `extract_data(conf, ds_user, ds_tracker, track_ds, *, native_winds=False)` separates native exports from required calculations. Full-domain extraction must work without a track. |
| `processing/polar/polar_proj.py` | `polar_project(dico_collocated, *, conf, method="bilinear", track=None, plan_cache=None)` consumes source-specific prepared fields and centre associations. |
| `core/execution.py` | `execute_simulation(config, options=None, *, input_files=None)` returns `SimulationExecutionResult`. `ExecutionOptions.from_config` resolves operational settings. |
| `core/run_state.py` | `owned_run(root, *, overwrite, initial)` owns the run directory and status. Extend the existing atomic lifecycle. |

Use the existing plan dictionaries, with these shared entries. Do not create a
general execution framework. Task 02 records the exact mapping shape; Task 03
supplies metadata, Task 09 completes products, and Task 13 formats reports.

| Entry | Required information |
|---|---|
| `sources` | Source-name mapping: physical type, admitted model/profile, resolved files, metadata origins, selected records, and native grids. |
| `records` within each source | Provider path and format locator, field/grid identity, valid time/calendar, cycle, time bounds/sampling meaning, vertical support, and selected sample indices. Keep decoded time types internally. |
| `requests` within each source | Exported fields/results by product, required internal inputs, representation, shared-level binding, and support needed by explicit methods. |
| `products` | One descriptor per requested dataset: source, product, run-relative path, fields, stored names, dimensions, units, representations, and relevant time association. |
| `warnings`, `deferred_checks` | Observed warnings and checks that need execution. Do not encode unknown facts as successful checks or invented coordinates. |

One owner must keep planned descriptors, writer paths, result inventories, and
status records consistent. Record publications separately from planned products.
After Task 03, adapter workers may consume these mappings but must not redefine them.

### Task 00 — Prepare the implementation branch

**Files:** create the execution copy and `STATE.md` from Section 1.
**Read:** `AGENTS.md`, `README.md`, `pyproject.toml`, `.github/workflows/runtime.yml`,
`.github/workflows/docs.yml`, and `docs/source/contributing/documentation.rst`.
**Output:** branch/worktree identity, baseline evidence, task ownership, ready tasks.

- [x] Create the branch from local `develop` as specified in Section 1. Record its
  commit, copy this plan, and preserve unrelated changes.
- [x] Verify Python and imports with Section 8's environment command. Record current
  optional backends and `FRAMEIT_CI_DATA_ROOT` availability without downloading data.
  Set `PYTHONPATH` to this worktree's `src` on each source-check command, including
  worker commands. Changing directory alone does not select an editable installation.
- [x] Run the baseline tests below. Record failures with the imported checkout path;
  do not confuse the known sanitizer defect with a v3 regression.
- [x] List shared files and fixture owners. Ask for Task 17's ocean decision early.
  Record the next task and commit the internal execution record.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v2_1.py src/frameit/testing/numerical/test_templates.py src/frameit/testing/numerical/test_documentation_example.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_hpc_execution.py
```

### Task 01 — Keep the selected installation in every worker

**Contract:** C9. **Files:** `src/frameit/cli.py`,
`src/frameit/testing/numerical/test_hpc_execution.py`; installation/troubleshooting
docs only if the fix changes user guidance.
**Interface:** `_sanitize_sys_path_user_site()` keeps project import paths; spawned
export workers and diagnostic reports identify the same selected installation.

- [x] Add `test_cli_keeps_checkout_under_local_in_parent_and_spawn`: use a temporary
  home with a checkout under `.local` and a competing import location. Assert the
  exact parent/worker `frameit.__file__` paths, not just equal numerical outputs.
  Also prove that actual unwanted user-site entries are still filtered.
- [x] Fix only the overbroad filtering. Exercise ordinary installed/editable imports
  and both synchronous and spawned export paths. Do not reinstall to hide the defect.
- [x] Run the test command, obtain independent review, and commit the fix before
  relying on subprocess results from later tasks.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_documentation_example.py src/frameit/testing/numerical/test_inspect_metadata.py
```

### Task 02 — Define v3 configuration and runtime handoffs

**Contracts:** C1–C9 syntax and defaults. **Files:**
`src/frameit/core/configuration.py`, `src/frameit/core/settings_class.py`,
`src/frameit/core/execution.py`, `src/frameit/io/loader.py`;
create `src/frameit/testing/numerical/test_configuration_v3.py`.
**Interfaces:** resolver/runtime signatures and plan entries above. Keep direct
`SimulationConfig` numerical construction usable; replace the public YAML schema.

- [x] Add schema tests for every approved block, unknown keys, duplicate YAML keys,
  `schema_version: 3` versus `true`, omission versus null, exclusive selectors,
  invalid cross-format options, defaults, and CLI/YAML/default origins.
  Keep `test_configuration_v3.py` metadata-free at this milestone; test the override
  resolver directly. Public CLI checks belong to Task 15.
- [x] Implement strict v3 resolution. Keep source declarations intact until metadata
  can bind them. Separate source identity from the old mandatory coupled branch.
- [x] Record mapping shapes and callers in `STATE.md`. Update version-sensitive
  branches in settings and execution, not only the parser's version guard.
- [x] Update shared config fixtures and their importers together. Do not delete
  `test_configuration_v2_1.py` while other suites import its `dataset`/`document`
  helpers. Retain meaningful rejection tests; no public v2 compatibility is required.
- [x] Review the interface handoff before downstream work starts.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py
```

### Task 03 — Inventory sources and select records before payload reads

**Contracts:** C1, C2, C3 identity. **Files:** `src/frameit/io/loader.py`,
`src/frameit/core/preflight.py`, `src/frameit/core/coupled.py`;
`test_inspect_metadata.py`, `test_netcdf_assembly.py`, `test_grib_lifecycle.py`
under `src/frameit/testing/numerical/`.
**Interfaces:** populate source `records` and grids in the shared plan; only these
records may reach Task 05. Metadata inspection may read needed coordinates.
**New tests:** `test_v3_source_inventory` and `test_v3_time_record_selection` in
`test_inspect_metadata.py`, parameterized over the cases below. Call metadata APIs
directly; the CLI inspection suite closes in Task 15.

- [x] Test aliases/hard links, overlapping patterns, copies with competing records,
  field-split files, unreadable files, proven-irrelevant files, and shuffled filenames.
  Assert chronological decoded order and no provider-priority escape hatch.
- [x] Test physical-type classification independently of source names and field
  selection. Reject two atmosphere sources; accept atmosphere/ocean/surface as admitted.
- [x] Test inclusive windows, exact values, stride after window, empty selection,
  nonstandard calendars, required cycle selection, and distinct forecast intervals.
  Use a multi-time file containing selected and excluded scientific samples.
- [x] Build the selected-record inventory with stable grid identity before filtering
  fields. Instrument metadata inspection to prove no scientific payload processing.
  A dependency outside selected files/times fails instead of extending the inventory.
- [x] Review and freeze the record contract for adapter workers.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_source_inventory src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_time_record_selection
```

### Task 04 — Bind fields and one level selector per source

**Contract:** C3. **Files:** `src/frameit/processing/requests.py`,
`src/frameit/core/preflight.py`, `src/frameit/utils/units.py` if needed;
request/grid/native-extraction suites below.
**Interfaces:** source `requests` map inventoried field identity to each product's
representation, selected vertical positions, coordinate units, and required support.
**New tests:** `test_v3_field_and_level_binding` and `test_v3_vertical_units` in
`test_request_selection.py`; `test_v3_representation_level_binding` in
`test_grid_representations.py`. Use native/destination coordinate fixtures here;
Task 08 tests actual transformations.

- [x] Test wrong 2D/3D categories, duplicate requests, unsupported duplicated names,
  and a singleton 3D axis. Test mixed U/V/W axes and one missing requested level.
- [x] Test `[5, 0]` order, inclusive ranges/intervals, duplicates, unknown physical
  bounds, original indices, and omitted all-level selection on unequal axes.
- [x] Test `850 hPa` against stored `85000 Pa`, incompatible units, units-only
  conversion, and both missing-unit warning cases. Assert field values are unchanged.
- [x] Specify and test the roundoff rule with storage/conversion evidence. Bind
  after an explicit representation change; do not make native/polar W inherit a
  model-grid remap. Known failures must occur before product writing.
- [x] Review level semantics and unit evidence.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py::test_v3_field_and_level_binding src/frameit/testing/numerical/test_request_selection.py::test_v3_vertical_units src/frameit/testing/numerical/test_grid_representations.py::test_v3_representation_level_binding
```

### Task 05 — Prove native execution, then wire every reader

**Contracts:** C1–C3, native C4, basic C7. **Files:** `src/frameit/io/netcdf_utils.py`,
`grib_utils.py`, `fa_utils.py`, `fa_backend.py`, `nemo_utils.py`, `croco_utils.py` in
the same directory; lead-owned runner/coupled/execution/writer integration.
**Interfaces:** each loader consumes `selected_records`; retain its return shape and
`DatasetResources` ownership. No loader may expand the inventory or silently merge
competing providers. Task 10 completes the writer contract begun here.
**Create:** `src/frameit/testing/numerical/test_v3_execution.py` with
`test_native_scalar_roundtrip`, `test_sources_keep_independent_clocks`, and
parameterized `test_readers_obey_selected_records`.

- [x] First prove a complete native NetCDF run using `create_first_run_input(path)`
  in `src/frameit/testing/documentation_example.py`. Preserve zeroes, NaNs, units,
  coordinates, times, source files, and no-clobber behavior. Reopen outside FrameIt.
  Build v3 YAML directly and call `load_runtime`/`execute_simulation`; do not depend
  on unconverted init templates or the old first-run CLI sequence.
- [x] Add an atmosphere plus ocean case with unequal clocks, for example
  `00:00/01:00` versus `00:30/01:30`. Preserve both clocks and one product per source.
  Use no region first; add fixed geometry when Task 06 is ready. Two sources of the
  same physical type are invalid and must not be used to bypass C1.
- [x] Review this runnable slice before parallel adapter work. Wire selected-record
  reads for NetCDF/MNH, NEMO/CROCO, GRIB, and FA in disjoint worker assignments.
- [x] Instrument actual payload requests, including trackers and internal inputs:
  excluded times in retained multi-time files must not be read. Preserve lazy
  loading, bounds, masks, resource rollback, and format-specific admission limits.
  Record an unsupported reader as a blocker, not a pass.
- [x] Run the focused checks below and each lane's applicable loader/resource tests.
  Full public adapter pipelines close after Tasks 07–15. Review the native slice
  and selected-record reads before closing this task.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py::test_native_scalar_roundtrip src/frameit/testing/numerical/test_v3_execution.py::test_sources_keep_independent_clocks src/frameit/testing/numerical/test_v3_execution.py::test_readers_obey_selected_records
```

### Task 06 — Apply regions and centre associations explicitly

**Contracts:** C2, C5. **Files:** `src/frameit/core/coupled.py`,
`src/frameit/core/time_association.py`, `src/frameit/io/track_file.py`,
`src/frameit/tracking/tracker_core.py`, `src/frameit/tracking/geographic.py`,
tracker input helpers, and `src/frameit/processing/extraction.py`.
**Interfaces:** `align_source_times`, `align_preceding_hour`,
`build_tracker_from_config`, and `make_tracking_dataset` use selected source times.
Record source sample time separately from its centre association.

- [x] Test full domains without centres; fixed crops on rotated/shifted grids;
  partial padding; outside-footprint failure; and requested/realised geometry.
- [x] Test atmospheric-source discovery, renamed sources, explicit dependencies,
  sparse tracker payload reads, and unchanged native exports. Assert pressure-wind
  defaults are full widths 200/100 km and preserve the former half-width geometry.
- [x] Test NetCDF trajectory discovery and exact centre coverage with unequal source
  timelines. Reject duplicate times, ambiguous/missing units, conflicting coordinate
  evidence, and missing centres. Extra track times remain valid.
- [x] Test exact/common/preceding-hour associations, cycles, bounds, exclusions,
  incomplete error/keep-prefix states, and no changes to unrelated native extraction.
- [x] Review scientific and time semantics.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_geographic_lookup.py src/frameit/testing/numerical/test_wind_pressure_seed.py src/frameit/testing/numerical/test_pressure_centroid.py src/frameit/testing/numerical/test_pressure_centroid_mnh.py src/frameit/testing/numerical/test_multifield_vortex.py src/frameit/testing/numerical/test_nemo_arome_coupling.py src/frameit/testing/numerical/test_croco_mnh_coupling.py
```

### Task 07 — Keep source interpretation explicit

**Contract:** C4 interpretation/FA. **Files:** `src/frameit/io/surfex_utils.py`,
`fa_contracts.py`, `fa_cubes.py`, `fa_utils.py`, `fa_worker.py` in the same directory;
lead-owned configuration/preflight integrations.
**Interfaces:** source `field_metadata`, `interpretation`, `profile`, `native_cubes`,
`fa`, and `reader` produce observed/declaration origins without requesting transforms.

- [x] Test SEA opt-in versus ordinary access, selected support only, fractional
  masks, valid zeroes, known sentinels, and unrelated legitimate `999` values.
- [x] Test FA cube record associations, vertical meaning, scientific metadata,
  sampling/basis/scaling, and technical-reader scope. Contradictions must fail.
- [x] Adapt declaration placement while retaining FA isolation, geometry, producer
  checks, and existing unsupported/spectral gates. Do not infer cube meaning from names.
- [x] Review source limits, provenance, and updated source guides.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_mnh_surfex_support.py src/frameit/testing/numerical/test_fa_contracts.py src/frameit/testing/numerical/test_fa_cubes.py src/frameit/testing/numerical/test_fa_pipeline.py src/frameit/testing/numerical/test_fa_spectral.py
```

### Task 08 — Separate native exports, transforms, and derived fields

**Contract:** C4, C3 representations. **Files:** `src/frameit/processing/requests.py`,
`wind_collocation.py`, `wind_reference.py`, `extraction.py` in that directory,
`src/frameit/processing/derived/wind.py`, and lead-owned runner/adapter call sites.
**Interfaces:** source `requests` distinguishes exports from internal inputs and
records each result's method, preparation, grid, and shared-level selection.

- [ ] Test that copying U alone needs neither V nor wind interpretation and preserves
  stored units/samples. Selecting U/V must not add speed or radial/tangential winds.
- [ ] Test explicit U/V collocation/rotation, each admitted rotation method, separate
  W remapping, missing geometry, and incompatible units. Use independent known vectors
  and masks; preserve pressure-velocity meaning and documented boundary rules.
- [ ] Test derived inputs without exports, output-name collisions, filtered-out unused
  results, and native/model-grid/polar level binding. Remove implicit calculations
  from all loader/runner/extraction paths, not only the public parser.
- [ ] Review numerical meaning and optionality.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_native_extraction.py src/frameit/testing/numerical/test_wind_collocation.py src/frameit/testing/numerical/test_wind_reference.py src/frameit/testing/numerical/test_wind_preflight.py src/frameit/testing/numerical/test_grid_representations.py src/frameit/testing/numerical/test_croco_vectors.py
```

### Task 09 — Plan products and sample polar fields

**Contract:** C6, related C2–C5. **Files:** `src/frameit/processing/polar/polar_proj.py`,
`contracts.py`, `sampling.py`, `regrid_plan.py` in that directory; lead-owned
preflight/coupled/runner integration.
**Interfaces:** complete the shared product descriptors. Use source-specific time
groups and centre associations; retain cache identity and target verification.

- [ ] Test omitted/empty products, exact source/field filters, internal-only inputs,
  track-only, polar-only without width, and both products together. Assert no unused work.
- [ ] Test crop-independent polar support, exact outer radius, clockwise full rings,
  automatic counts, native/coarsest shared spacing, and finer-spacing rejection.
- [ ] Test evidence-based continuous/category methods, strict and explicit threshold
  coverage, zeroes, all-missing/unmapped points, unused overrides, and insufficient halos.
- [ ] Prove speed is calculated after U/V sampling using a field where reversing
  those operations gives different values. Test independent polar W preparation,
  mixed vertical grids, unequal source clocks/masks, and selected-time payload reads.
- [ ] Test point budgets and optional dependencies with polar disabled/enabled.
  Review sampling, coverage, and representation rules.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_polar_contracts.py src/frameit/testing/numerical/test_polar_axes.py src/frameit/testing/numerical/test_polar_coverage.py src/frameit/testing/numerical/test_polar_wind.py src/frameit/testing/numerical/test_polar_regrid_plan.py src/frameit/testing/numerical/test_coupled_shared_polar.py
```

### Task 10 — Finish datasets, coordinates, and writers

**Contract:** C7. **Files:** `src/frameit/io/netcdf_export.py`,
`src/frameit/io/zarr_export.py`, `src/frameit/utils/output_paths.py`,
`src/frameit/core/execution.py`; output/layout/grid suites below.
**Interfaces:** writers consume the common product descriptors; return actual
published paths and field metadata for result/status records. No independent naming rule.

- [ ] Test one dataset per source/product with mixed U/V/W/native ocean axes. Prevent
  automatic alignment between different grids; retain singleton vertical dimensions.
- [ ] Assert every C7 dimension/geographic/vertical/polar name, units, bounds, formula
  dependency, original-index auxiliary, and time-dependent sample position.
  Add/reorder/filter fields and assert existing axis names stay unchanged.
- [ ] Test custom run names, safe path components, collisions, overwrite false,
  NetCDF4 and sharded Zarr v3, compression defaults, precision, and inapplicable options.
  A Zarr field run with a track still rejects writer `engine` and `unlimited_time`.
- [ ] Reopen both formats in fresh processes without importing FrameIt. Check exact
  native values/masks and justified transformed tolerances, metadata, and inventory.
- [ ] Review output schema, publication safety, and output docs.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_output_layout.py src/frameit/testing/numerical/test_grid_representations.py src/frameit/testing/numerical/test_zarr_export.py src/frameit/testing/numerical/test_hpc_execution.py
```

### Task 11 — Resolve resources and chunk settings

**Contract:** C8, advanced C4/C6/C7. **Files:** `src/frameit/core/runtime.py`,
`src/frameit/core/execution.py`, reader/product/writer integration points owned by
their existing workers; HPC/Zarr/polar-Dask tests below.
**Interfaces:** `resolve_execution_resources(options)`, `execution_scope(options)`,
and `runtime_provenance()` expose one effective CPU budget and setting origins.

- [ ] Test omitted and explicit CPU budgets against allocation/affinity, nested
  reader/compute/export/native threads, and excess-budget errors. Keep one native
  thread and asynchronous export as defaults.
- [ ] Test input/product/output chunk namespaces, automatic layouts, mixed products,
  unmatched dimensions, shards, halos, cache limits, and recorded weight tolerance.
  Verify that polar `processing.profile` controls performance measurements.
- [ ] Measure small representative arrays before/after layout choices. Keep precision,
  masks, and values; report time/memory/I/O and unresolved full-record decoder costs.
- [ ] Review budget accounting and estimates.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_zarr_export.py src/frameit/testing/numerical/test_polar_dask.py src/frameit/testing/numerical/test_fa_resources.py
```

### Task 12 — Preserve requests and actual publication state

**Contracts:** C7, C9 early records/status. **Files:**
`src/frameit/core/run_state.py`, `src/frameit/core/execution.py`,
`src/frameit/utils/atomic.py` only if needed; writer completion callbacks and tests.
**Interfaces:** extend `owned_run` and the existing status/provenance records.
Freeze record filenames/path bases for Task 15's reader before delegation.

- [ ] Test failure after ownership but before source processing. Preserve an immutable
  authored request, operational overrides, code identity, and original path bases.
  Editing/moving the original YAML must not change the saved request's meaning.
- [ ] Test failure/interruption after the first successful product publication.
  Inventory that product accurately; distinguish planned, failed, and incomplete work.
- [ ] Test existing locks/artifacts, explicit replacement, orphan partial products,
  stale running status, and the documented Zarr replacement visibility limit.
- [ ] Save actual effective facts as they become known. Keep pending facts explicit;
  do not publish a misleading completed configuration or erase failure evidence.
- [ ] Review recovery behavior and run-directory docs.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_output_layout.py src/frameit/testing/numerical/test_zarr_export.py
```

### Task 13 — Share preflight and report all independent errors

**Contract:** C9 reports/validation, C1–C8 plan facts. **Files:**
`src/frameit/core/preflight.py`, `src/frameit/core/configuration.py`,
`src/frameit/core/coupled.py`, and focused configuration/inspection tests.
**Interfaces:** common plan plus the exact C9 report envelope. Keep authored mapping,
effective configuration, origins, inputs, plan, and pending facts separate.

- [ ] Test two independent invalid sources/files in one request. Both repairs must
  appear once with YAML location and observed/expected facts. Dependent checks must
  be marked blocked rather than run against invented values.
- [ ] Test unfinished inspection, valid copyable selectors, required-only dependency
  checks, offline schema-only checks, and deferred execution-dependent facts.
- [ ] Make validate/run/effective-view share the same preflight result. Serialize
  calendars and origins explicitly without losing internal decoded-time meaning.
- [ ] Test one JSON stdout document with all seven envelope keys, nonzero failure,
  stderr-only logs, and readable human summaries. Do not use snapshots alone.
- [ ] Review reports and error repairs.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_wind_preflight.py
```

### Task 14 — Integrate execution and report real progress

**Contracts:** C1–C9 runtime, especially progress. **Files:**
`src/frameit/core/runner.py`, `src/frameit/core/execution.py`,
`src/frameit/core/coupled.py`, `src/frameit/utils/logging.py`, and writer hooks.
**Interfaces:** `execute_simulation` uses the same selected plan and product
descriptors as preflight. Reuse existing timing/logging rather than an event framework.

- [ ] Test no-region native runs, independent clocks, sparse-time tracking/derived
  inputs, explicit transforms, track-only, and polar-only through public execution.
- [ ] Test slow preparation, lazy compute, export, failure, and interruption. Counts
  describe completed work; elapsed/last-activity messages continue during quiet work.
- [ ] Add rate-limited progress with a testable clock. Assert bounded output and no
  extra payload reads or eager compute merely to update progress. Final states agree
  with Task 12's publications and incomplete tracking.
- [ ] Review integrated execution and progress reporting.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_logging.py src/frameit/testing/numerical/test_matrix_progress.py src/frameit/testing/numerical/test_coupled_shared_polar.py
```

### Task 15 — Complete the CLI, starters, capabilities, and editor schema

**Contract:** C9. **Files:** `src/frameit/cli.py`,
`src/frameit/core/configuration.py`, `src/frameit/templates/*.yaml`,
`pyproject.toml` for packaged schema assets if needed; template/configuration tests.
**Interfaces:** preserve `write_template(name, path, *, tracking=None, coupling=None,
force=False)`. Use Task 13 reports and Task 12 run records. Record the chosen status
command/exit contract; `frameit status <run-directory>` is only a candidate spelling.

- [ ] Test every existing init model/recipe/composition/default/force rule with v3
  output. Do not invent task-based starters or change the selected workflow.
- [ ] Implement inspect/validate/run on the same YAML; authored/effective config;
  exact operational flags, path bases, precedence, and JSON behavior from C9.
  Remove the retired public dry-run/resolved options and their help references.
- [ ] Build capabilities and versioned JSON Schema from authoritative definitions.
  Test actual support/maturity/dependencies and packaged schema availability.
- [ ] Implement lightweight status and matching final summary. Test with original
  inputs absent; show actual fields/paths, warnings/exclusions, failures, and ordinary
  reader guidance. Do not infer liveness from an old running record.
- [ ] Review complete command, help, and error text.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py src/frameit/testing/numerical/test_templates.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_hpc_execution.py
```

### Task 16 — Update every configuration producer and canonical example

**Contracts:** C9, C10. **Files:** `src/frameit/testing/catalog.py`, `matrix.py`,
`checks.py`, `polar_benchmark.py`,
`catalogs/`, `recipes/`, `documentation_example.py` under `src/frameit/testing/`;
`example/config_file/`, `example/plots/`, README, reference YAML, first-run/quick-start,
configuration/output/time guides, and documentation contribution guidance.
**Interfaces:** existing generators emit valid v3; examples use the same commands,
paths, fields, and dimensions as real products. Preserve shared test helper APIs.

- [ ] Find every public YAML producer/consumer and old option/name. Update callers,
  packaged assets, documentation tests, and CI file lists together. Keep schema,
  package, FA-protocol, and manifest versions separate.
- [ ] Run the exact first-run and quick-start commands with fresh outputs. Check
  source immutability and independent reopening. First run teaches; quick start
  remains a short reminder. Update the contribution guide's current-schema sentence.
- [ ] Update `check_products` for v3 dimensions, products, optional tracks, and
  source-specific clocks. Add `test_matrix_checks_actual_outputs` to
  `test_v3_execution.py`: generate compact real products and run the actual checker.
  Mocked matrix-launch tests do not cover this contract.
- [ ] Update benchmark configuration edits and generated trajectories to v3. Add
  `test_benchmark_small_case` in the same test file: run one small case through the
  real preparation/execution path with bounded resources. Do not run the full benchmark.
- [ ] Replace schema history with direct v3 guidance. Keep useful page URLs, figures,
  method evidence, and simple template comments. Put general rules in general guides.
- [ ] Run the checks below plus strict docs/publication/preview checks from Section 8.
  Obtain an independent task-walkthrough review and commit.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v2_1.py src/frameit/testing/numerical/test_documentation_example.py src/frameit/testing/numerical/test_configuration_integration.py src/frameit/testing/numerical/test_all_tests.py src/frameit/testing/numerical/test_templates.py src/frameit/testing/numerical/test_v3_execution.py docs/test_repository_examples.py docs/test_documentation_plots.py docs/test_release.py
```

### Task 17 — Build small analytical tutorials and complete task pages

**Contract:** C10. **Files:** `src/frameit/testing/documentation_example.py`,
existing analytical vortex helpers under `src/frameit/testing/`, canonical examples
under `example/`, and `docs/source/task_guides/`; extend documentation-example tests.
**Interfaces:** generators write deterministic instructional inputs; scripts consume
actual FrameIt products. Fixture definitions remain separate from task instructions.

- [ ] Write the ocean-response proposal: formula, parameters/units, relation to the
  shared event and track, temporal meaning, masks, and limits. Record actual maintainer
  approval before implementing this response. Continue the atmospheric cases meanwhile.
- [ ] Generate C10's stationary, translating, layered/interface, and missing/category
  cases directly from the approved formulas. Check known centres/profiles/rotation
  independently; justify numerical tolerances. Do not call them real-producer validation.
- [ ] Complete pages for native extraction, levels/times, fixed/moving regions,
  multiple sources, transforms, polar-only/combined products, reading, and error repair.
  Each page has complete YAML, commands, expected files/fields, and the necessary limits.
- [ ] Put minimal complete plotting scripts inline and reuse them verbatim to render
  the demonstrated products. Check size, generation/run time, memory, overwrite
  refusal, captions, units, and alternative text.
- [ ] Run tutorial/plot tests and Section 8 docs checks. Obtain numerical and plain-
  English review; close only after the approved paired-ocean case also passes.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_documentation_example.py src/frameit/testing/numerical/test_polar_qualification.py docs/test_documentation_plots.py docs/test_repository_examples.py
```

### Task 18 — Repeat cases locally and through a Slurm array

**Contracts:** C8, C9 batch examples. **Files:** `example/slurm/`,
`docs/source/getting_started/hpc.rst`, `docs/test_repository_examples.py`;
add one canonical repeated-case example under `example/`.
**Interfaces:** reuse ordinary complete-YAML runs, current launchers, and the status
inventory. Update `example/slurm/check_run.py` for independent source/product clocks.

- [ ] Add a short shell or Python loop and matching Slurm-array example with one
  complete YAML per case, a fresh attempt directory including retries, and accurate
  per-attempt success/failure results. Preserve each calculated tracking timeline.
- [ ] Test a successful case, failed case, and retry without clobbering prior outputs.
  Reuse allocation-aware launching; keep paths and scheduler settings site-neutral.
- [ ] Fix the checker assumption that every field has one track's timestamps. Check
  each product against its recorded contract. Also remove its compulsory exported-
  track assumption: opening/linking a track is conditional on the requested products.
  Test default model-grid and polar runs without an exported trajectory.
  Its NetCDF-only scope must be explicit unless another format is implemented and tested.
- [ ] Run local example tests and docs checks; distinguish them from real cluster
  execution. Obtain independent example review and commit.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_repository_examples.py src/frameit/testing/numerical/test_hpc_execution.py
```

### Task 19 — Verify the integrated branch and installed package

**Contracts:** C1–C9. **Files:** affected tests, `.github/workflows/runtime.yml`,
`.github/workflows/docs.yml`, `pyproject.toml` packaged assets, and `STATE.md`.
**Output:** evidence matrix linking each contract and review-focus case to a passing
test or an explicit missing check. Existing failures need cause and disposition.

- [ ] Exercise the five cross-component cases in Section 5 end to end, including
  wrong-checkout workers, actual sparse payload reads, and partial publication.
- [ ] Run the full suite and isolated installed-wheel checks from Section 8. Verify
  installed templates/schema/examples and selected installation identity. Do not
  modify the shared Conda install merely to test a wheel.
- [ ] Exercise enabled and disabled optional paths. Record skips/backends and fixture
  limits; use only already available approved data. Missing required evidence blocks
  the affected qualification, not unrelated tasks.
- [ ] Have a fresh reviewer inspect implementation, tests, outputs, and the contract
  matrix. Fix findings, rerun affected checks, and commit reviewed changes.

### Task 20 — Review the whole documentation twice

**Contracts:** Section 3 and C10; all scientific/public contracts remain binding.
**Scope:** every published page, README, CLI help/errors, canonical examples,
template comments, captions, and alternative text—not only changed paragraphs.
**Output:** complete coverage and closed findings in `STATE.md`.

- [ ] Inventory the scope by path and rendered page. Assign disjoint page sets to
  independent review agents; include a separate reviewer for cross-page consistency.
  Each report must identify every item reviewed, including CLI help and error text.
  Sampling is not a full review.
- [ ] **Pass 1: correctness and task completion.** Review against the code and actual
  outputs. Check that each task page tells users what to edit, what to run, which
  files and fields to expect, how to fix errors, and which scientific limits apply.
  Check all advertised capabilities.
- [ ] Fix every accepted finding. For a rejected finding, record evidence and obtain
  reviewer agreement. Rebuild, rerun affected examples, and verify rendered changes.
- [ ] **Pass 2: plain English and deletion.** Use fresh reviewers who did not write
  the pages or conduct Pass 1. Read the whole inventory again. Flag every confusing,
  repeated, filler, promotional, or out-of-context sentence with a shorter correction
  or deletion. Check comments and help text as carefully as prose pages.
- [ ] Apply the edits, then have a scientific/technical reviewer verify that shortening
  preserved defaults, units, assumptions, masks, method limits, and error behavior.
  Reviewers verify closure; the lead resolves cross-page contradictions.
- [ ] Run strict docs/publication/tests and inspect all affected rendered pages at
  desktop and narrow widths. Keep the live GUI preview available. Commit only after
  both full passes have coverage records and no unresolved blocking findings.

Do not use sentence-length scores, a banned-word scan, or an author's own reread
as a substitute for either independent pass. Use extra passes when fixes introduce
new problems. Do not repeat passed checks without a change or unresolved concern.

### Task 21 — Final independent review and human acceptance

**Scope:** the combined branch and complete user journey. **Output:** final evidence,
local commits, remaining limitations, and the exact next action.

- [ ] Dispatch a fresh whole-branch reviewer for contract coverage, scientific/output
  meaning, installation/package behavior, failure safety, and unnecessary code.
  Dispatch a separate fresh documentation reviewer for the entire inventory after
  Task 20's edits. Neither reviewer may have authored the reviewed work.
- [ ] Fix findings and verify their closure with the reviewers. Run the affected
  checks and final docs/publication checks against the reviewed revision.
- [ ] Ask the human reviewer to perform the documented tasks: sparse times and a
  singleton level, add a different physical source, polar-only output, locate/read
  results, and repair a reported error. Record their actual observations and acceptance.
  Subagent approval or a screenshot is not human usability acceptance.
- [ ] Apply the completion gates in Section 8. If evidence or human approval is
  missing, record the task as blocked and give the exact next action. Otherwise mark
  all tasks done, commit the final state, and hand over locally without pushing.

## 8. Verification and completion gates

Run commands from the implementation worktree root. Use `PYTHONPATH="$PWD/src"`
for source checks; subprocesses must inherit it. Apply this in every shell call
and worker worktree. Wheel checks instead select only their installed target.
Every command below is a
future check, not evidence that the feature already works. Record the exact command,
revision, result, skips, and reason for any unavailable check in `STATE.md`.

### Environment and tests

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -c 'import sys, frameit; from pathlib import Path; assert sys.version_info[:2] == (3, 13); assert Path(frameit.__file__).resolve().is_relative_to(Path("src").resolve()); print(sys.executable); print(frameit.__file__)'
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pip check
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q
```

Confirm that the printed module belongs to the intended worktree before trusting
test results. A full suite with optional-backend or fixture skips is not full native
qualification. Follow the current runtime CI's backend requirements where available;
do not install a new environment or download a large fixture without authorization.

Use fresh numbered build/install directories for package checks:

```bash
conda run -n frameit_env python -m pip wheel --no-deps --no-build-isolation . -w build/yaml-v3-wheel-01
conda run -n frameit_env python -m pip install --no-deps --no-index --target build/yaml-v3-install-01 build/yaml-v3-wheel-01/frameit-*.whl
PYTHONPATH="$PWD/build/yaml-v3-install-01" conda run -n frameit_env python -c 'import frameit; from pathlib import Path; assert Path(frameit.__file__).is_relative_to(Path("build/yaml-v3-install-01").resolve())'
PYTHONPATH="$PWD/build/yaml-v3-install-01" conda run -n frameit_env python -m pytest -q build/yaml-v3-install-01/frameit/testing/numerical/test_templates.py build/yaml-v3-install-01/frameit/testing/numerical/test_fa_environment.py build/yaml-v3-install-01/frameit/testing/numerical/test_fa_resources.py
```

Also run the installed primary-pair/shared-polar cases named by the current runtime
CI when their approved fixture/backends are available. Keep package tests separate
from source-tree results. Check new schema assets through the installed package.

### Documentation checks and live preview

Use a new iteration directory after each meaningful revision. These commands
follow the existing documentation guide without deleting prior previews:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-01
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-01
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_documentation_plots.py docs/test_repository_examples.py docs/test_release.py
```

Required result: zero exit status, no strict-build warnings, passing publication
checks, and passing applicable tests. Fix a failed build before calling it a preview.

For agent previews, start this command with the OpenCode shell tool's background
mode. Choose another free port if needed; do not stop someone else's process.

```bash
conda run --no-capture-output -n frameit_env python -m http.server 8765 --bind 127.0.0.1 --directory build/docs-preview
```

Load the browser skill and open
`http://127.0.0.1:8765/yaml-v3-01/index.html` in the live OpenCode GUI. Keep its tab ID.
Inspect affected pages at desktop width and at 320 px, including menu/keyboard use,
tables, code blocks, figures, captions, alternative text, and links. Check SVG text
bounds, not just image boxes. Keep the preview available for feedback. Record the
owned server process, URL, tab, and restart command in the session handover, not in
committed machine state. A disconnected GUI is a visual-review blocker.

### Final checklist

- [ ] Every task has an owner, reviewed result, test evidence, and local commit.
- [ ] Each binding contract maps to implementation and a meaningful check.
- [ ] All five cross-component review cases pass end to end.
- [ ] Source data and unrelated work remain intact; no private data or machine state
  is committed. Diffs contain only approved work.
- [ ] Scientific choices, numerical tolerances, warnings, method maturity, and
  unresolved limits match the evidence. Required maintainer approval is recorded.
- [ ] Optional diagnostics remain optional. Native extraction works without them.
- [ ] Ordinary readers reopen supported outputs with the expected values/metadata.
- [ ] Documentation, examples, help, schema assets, templates, and package checks agree.
- [ ] Two full documentation passes and the final independent reviews are closed.
- [ ] Strict docs/publication checks and live desktop/narrow review pass.
- [ ] Actual human usability acceptance is recorded, or completion remains blocked.
- [ ] Task-related work is committed locally. Nothing is pushed without a request.

### Handover

Keep the final reply short:

```text
Changed: main behavior and paths; branch and commit IDs.
Scientific impact: methods, assumptions, defaults, and approval status.
Compatibility: public YAML/output changes; v3 is taught directly.
Verification: exact commands and observed results, including skips.
Limitations: missing evidence/review and the next action, or none.
Preview: owned server process, URL, tab ID, and restart command.
```

Never describe an unchecked task, unavailable backend, or unreceived human decision
as complete. If work stops, `STATE.md` must identify what the next agent should do.
