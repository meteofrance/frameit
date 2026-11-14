# YAML v3 execution state

Internal execution record. This file and the checklist are not published.

## Identity and workflow

- Branch: `feature/yaml-v3`, local only, without an upstream.
- Worktree: this separate `yaml-v3` checkout.
- Starting local `develop`: `8c2d4bb4a6318c49b60ea85a979a3f8f13bef6b4`.
- Remote `develop` and `main` were checked with
  `git ls-remote origin refs/heads/develop refs/heads/main`; both match that commit.
- The starting commit equals the plan's audited baseline. No baseline diff is needed.
- Plan: `CHECKLIST_FOR_AGENTS.md`, copied from the planning repository's
  `yaml-v3/CHECKLIST_FOR_AGENTS.md` at
  `e4be698fedaac1f3a4c16b290717e32af1c8b1f4`.
  Its binding contracts identify planning commit `07b15cf` as their source.
- The original detached worktree and all other worktrees are unchanged.
- Only the lead edits this state. Workers use disjoint file claims; reviewers
  do not author reviewed changes. Review precedes each task commit.
- No publication, pushes, tags, releases, or feature-branch upstreams are authorized.
- Docs: no user-facing impact from this execution record; neither internal file
  is under `docs/source` or linked as a Sphinx download.

## Tasks and ownership

`blocked` means the named dependency or evidence is not available. It is not a pass.
An owner of `lead` on future tasks is a reservation, not a claim of implementation.

| Task | State | Owner | Needs | Claimed files / next action |
|---|---|---|---|---|
| 00 | done | lead | — | Reviewed internal records: `dec4db1`. |
| 01 | done | task-01 worker + independent reviewer | 00 | Reviewed fix committed as `645d7e6`. |
| 02 | done | task-02 worker + independent reviewer | 01 | Reviewed schema and frozen handoffs: `8034a6d`. |
| 03 | done | task-03 worker + independent reviewer | 02 | All nine findings closed; selected-record/grid handoff frozen below. |
| 04 | ready | unassigned | 03 | `requests.py`, `preflight.py`, optional `units.py`, request/grid tests; bind fields and levels. |
| 05 | blocked | lead | 04 | Native execution test and orchestration first; separate adapter claims after native slice review. |
| 06 | blocked | lead | 05 | `coupled.py`, time/track/tracker/extraction files; regions and centre associations. |
| 07 | blocked | unassigned | 05 | SEA/FA files and tests; explicit source declarations. |
| 08 | blocked | unassigned | 07 | Requests, wind, extraction and derived files; explicit transformations. |
| 09 | blocked | lead | 06, 08 | Polar modules and runner/preflight integration; requested products only. |
| 10 | blocked | lead | 09 | Writers, output paths and execution; shared descriptors and stable coordinates. |
| 11 | blocked | lead | 10 | Runtime/resources and chunk integrations; measured bounded layouts. |
| 12 | blocked | lead | 10 | Run state, execution and writer callbacks; early request and publication facts. |
| 13 | blocked | lead | 11, 12 | Preflight/configuration/coupled; common reports and independent errors. |
| 14 | blocked | lead | 13 | Runner/execution/coupled/logging; integrated execution and progress. |
| 15 | blocked | lead | 14 | CLI/configuration/templates/schema assets; preserved init and v3 commands. |
| 16 | blocked | lead | 15 | All producers, canonical examples, public guides and tests; direct v3 guidance. |
| 17 | blocked | lead | 16 | Analytical fixtures and task pages; ocean fixture formula approved, not implemented. |
| 18 | blocked | unassigned | 16 | Repeated-case/Slurm examples and tests. |
| 19 | blocked | lead | 16, 18 | Full integration, wheel and contract evidence matrix. |
| 20 | blocked | lead + fresh reviewers | 17, 19 | Two complete independent documentation passes with path coverage. |
| 21 | blocked | lead + fresh reviewers + human | 20 | Whole-branch reviews and actual human usability acceptance. |

Shared orchestration (`configuration.py`, `settings_class.py`, `preflight.py`,
`runner.py`, `execution.py`, `coupled.py`, `cli.py`) is lead-owned except an
explicit bounded assignment. Shared fixture helpers are lead-owned; a worker
must list importers and obtain an explicit file claim before changing them.

| Fixture path under `src/frameit/testing/` | Shared helpers | Owner |
|---|---|---|
| `numerical/test_configuration_v2_1.py` | `document`, `dataset` | lead |
| `documentation_example.py` | `create_first_run_input` | lead |
| `fa_fixture.py` | `write_fixture` | lead |
| `numerical/test_fa_cubes.py` | `document`, `fixtures` | lead |
| `numerical/test_fa_pipeline.py` | `document` | lead |
| `numerical/test_multifield_vortex.py` | `document` | lead |
| `catalog.py`, `matrix.py`, `catalogs/`, `recipes/` | generated configurations and shared case definitions | lead |

## Baseline evidence

All Python commands use Conda `frameit_env` and select this checkout explicitly.

1. Command:
   ```bash
   PYTHONPATH="$PWD/src" conda run -n frameit_env python -c 'import sys, frameit; from pathlib import Path; assert sys.version_info[:2] == (3, 13); assert Path(frameit.__file__).resolve().is_relative_to(Path("src").resolve()); print(sys.executable); print(frameit.__file__)'
   ```
   Result: exit 0; Python is the `frameit_env` interpreter and FrameIt is
   `src/frameit/__init__.py` in this worktree.
2. Command:
   ```bash
   PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pip check
   ```
   Result: exit 0, `No broken requirements found.`
3. Command:
   ```bash
   PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v2_1.py src/frameit/testing/numerical/test_templates.py src/frameit/testing/numerical/test_documentation_example.py src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_hpc_execution.py
   ```
   Result on starting commit: **251 passed, 3 failed, 1 error**, 6 warnings,
   22.32 seconds. Failures:
   - `test_exact_first_run_commands_and_fresh_ordinary_reader[starter]`
   - `test_exact_first_run_commands_and_fresh_ordinary_reader[guided-first-run]`
   - `test_quick_start_commands_use_the_selected_mesonh_scalar`
   - setup error in `test_concurrent_cli_attempts_spawn_and_sync_export_exactly`

   Each failed spawned export imports the competing editable checkout's
   `frameit.core.runtime`, not this worktree. It cannot find
   `initialize_export_worker`. The parent traceback belongs to this worktree.
   Observed paths (home prefix replaced by `$HOME`):
   - Parent: `$HOME/.local/share/opencode/worktree/614a69/yaml-v3/src/frameit/core/execution.py`.
   - Worker: `$HOME/work/LACy/frameit/src/frameit/core/runtime.py`.
   This reproduces Task 01's known sanitizer defect, not a v3 regression.
   Warnings: one NumPy binary-size warning and five xarray/netCDF4 shape
   deprecations. They remain visible; no warning filter was added.

Available packages (metadata/spec check, not full scientific qualification):
`netCDF4 1.7.2`, `h5netcdf 1.8.2`, `zarr 3.4.2`, `cfgrib 0.9.15.1`,
`eccodes 2.44.0`, `xesmf 0.9.2`, `esmpy 8.9.1`, `epygram 2.1.0`,
`falfilfa4py 1.2.1`, `ctypesForFortran 1.3.0`, `ectrans4py 1.6.0`,
`sphinx 9.2.0`.

`FRAMEIT_CI_DATA_ROOT` was unset for the baseline and Task 01 tests. No fixture
was downloaded. After those tests, the lead found the approved data-only commit
already in local Git and extracted exactly
`24b63e5683133ddbb349c7c492fa4b517ccbc42a` into the ignored
`build/yaml-v3-ci-fixture-01`. Its `SHA256SUMS` matches runtime CI's manifest hash
`ac631ffed5a99cdc69e4a726f98bfd8b2299b8d9a02d8e15a683ad81a24d4d45`;
`sha256sum --check --strict SHA256SUMS` passed for all nine payloads.
Future source checks needing the fixture must explicitly set
`FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01"`. This does not turn the
earlier missing-input failures into passes. Real-producer qualification remains
evidence-dependent.

## Pre-flight decisions and interface scan

The supplied plan is already the approved design and implementation plan.
Ruling: execute it without a new design/approval round, as explicitly requested
by the maintainer's autonomous-workflow instruction. No public contract changes.

Ruling: create a new separate worktree from `develop`, rather than reuse the
initial isolated detached checkout, because this plan explicitly requires it.
The native worktree API cannot select the base; use the plan's git fallback.

Ruling: use this state as the authoritative durable ledger and keep skill helper
artifacts in the ignored plan workspace. The plan's review-before-commit cycle
overrides generic skill advice to commit before review. Preserve records at
handover rather than deleting them. No failed gate may be parked as passed.

| Task | Internal contract check |
|---|---|
| 00 | Baseline, explicit import selection, copied plan, and local branch agree. |
| 01 | Tests pin exact parent/worker paths and retained user-site exclusion. |
| 02 | Metadata-free schema milestone; retain numerical construction and shared helpers. |
| 03 | Metadata/coordinates only; selected records precede payloads. |
| 04 | Source-wide levels bind separately to each representation; no interpolation. |
| 05 | Native runtime milestone precedes public CLI conversion; adapters keep resource ownership. |
| 06 | Independent extraction clocks remain separate from centre association. |
| 07 | Source declarations do not request numerical conversions or broaden FA admission. |
| 08 | Explicit transforms/results; no implicit wind pairs or exports. |
| 09 | Products determine required work and independent polar support. |
| 10 | One descriptor governs names, dimensions, paths, and actual publications. |
| 11 | One CPU budget covers nested work; chunk scopes remain distinct. |
| 12 | Early immutable request precedes failure; actual publications are not planned products. |
| 13 | Report serialization must not replace decoded internal time types. |
| 14 | Progress cannot force eager reads or invent completion. |
| 15 | Preserve init workflow; remove retired public options only at CLI conversion. |
| 16 | Shared helper importers move together; schema and protocol versions stay distinct. |
| 17 | Ocean formula requires human approval; atmospheric formulas are fixed. |
| 18 | Ordinary complete YAML per run; no scheduler service or compulsory trajectory. |
| 19 | Wheel checks isolated from shared install; fixture absence is not a pass. |
| 20 | Two whole-inventory reviews, not sampled prose or automated style scores. |
| 21 | Human acceptance cannot be replaced by reviewers, tests, or screenshots. |

| Producer task(s) | Consumer task(s) | Shared interface / ordering result |
|---|---|---|
| 01 | 02–21 | Correct selected checkout is required for trustworthy subprocess evidence. |
| 02 | 03–16, 18–19 | Resolver/runtime/source documents; record exact mappings before delegation. |
| 03 | 04–10, 13–14 | Selected physical records and stable grid IDs; freeze before adapter work. |
| 04 | 05, 08–10 | Representation-specific field/level requests; shared selector, separate bindings. |
| 05 | 06–10, 14, 19 | Loaders receive selected records; no discovery outside admitted inventory. |
| 06 | 09–10, 13–14, 17–19 | Centre associations preserve source sample times and independent extraction. |
| 07 | 08–10, 13–17 | Explicit SEA/FA declarations retain scientific admission gates. |
| 08 | 09–10, 13–17 | Native exports, internal inputs, transforms, derived fields remain distinct. |
| 09 | 10–11, 13–19 | Product descriptors and polar preparation; no independent writer naming. |
| 10 | 11–19 | Stored coordinates, paths, encodings and product metadata feed reports/status. |
| 11 | 13–19 | Resource and chunk resolutions feed preflight and execution. |
| 12 | 13–19 | Early request filenames/path bases freeze before status reader implementation. |
| 13 | 14–16, 18–19 | One plan/report contract across validation, effective view and execution. |
| 14 | 15–19 | Execution results and progress agree with actual publications. |
| 15 | 16–19 | Public CLI, preserved init and schema assets ready before producer conversion. |
| 16 | 17–20 | Canonical v3 examples ready before tutorials and batch examples. |
| 17, 19 | 20 | Full documentation review can start early but cannot close on missing pages. |
| 18 | 19–20 | Actual example outputs and independent checker contracts. |
| 20 | 21 | Final documentation review follows both complete passes. |

Overlapping shared files are serialized under the lead's ownership. No concurrent
implementation claims are active. Focused milestone tests in Tasks 02–05 do not
pretend the still-unconverted public suites pass; the plan assigns those to 15–16
and 19. Delivered behavior must not regress.

## Scientific decisions and approvals

### Task 17: proposed paired ocean instructional response (not implemented)

Proposed CROCO scalar temperature on a coarser rho grid:

```text
T(r, z, t) = 300 K + (0.01 K/m) z - (2 K) exp(-(r / 40 km)^2) exp(z / 20 m)
```

Here `z <= 0 m` is height relative to the sea surface and `r` is geodesic
distance from the same prescribed atmospheric centre at the ocean sample time.
Use three declared depths (0, -10, -30 m), instantaneous samples, and a coarser
grid covering the atmospheric event. Its own timestamps remain unchanged; any
centre association is explicit. No motion subtraction, dynamical balance,
ocean-response physics or real-producer validation is claimed. Baseline case has
full finite coverage; a separately labelled missing/category variant carries a
declared static mask and preserves valid zeroes in the appropriate test fields.

The maintainer selected **Approve synthetic formula** in the session question
on 2026-11-13. This approves exactly the proposed instructional response,
not a scientific diagnostic or general scientific validation.
This is a plotting/selection fixture only, not a new scientific diagnostic.
Tasks 18 and 19 must continue independently of this approval.

Task 21: agree the human usability-review protocol before its walkthrough.
No acceptance has been received.

## Review findings, commits, and next action

- Task 00 independent setup review found two recordkeeping gaps:
  missing observed import paths and unnamed shared fixture owners. Both were
  checked against baseline output / fixture definitions and added above.
  Fix round 1: independent reviewer verified both closures; spec and quality
  PASS. No runtime changes or rerun needed.
- Task 00 done: baseline failures are recorded, not hidden. `cmp` confirms the
  unmodified plan copy and `git diff --check` passed before staging.
- Task 00 commit: `dec4db1`.
- Task 01 assigned at `dec4db1` to a bounded worker. Shared fixtures were
  preserved. The lead added the proposed canonical installation pointer.
- Task 01 independent review: spec PASS, quality Approve; no open findings.
  Reviewer inspected actual diff, caller/export interfaces, tests and completed
  full-suite log. No numerical or schema changes.
- Task 01 commit: `645d7e6`.
- Task 02 assigned at `645d7e6`. Its worker owns the four named runtime files
  and new metadata-free schema tests. Lead retains public documentation and state.
  Shared fixture helpers are unchanged unless an explicit caller-wide claim is
  agreed. No metadata/payload implementation belongs in this schema milestone.
- Lead's Task 02 documentation claim:
  `docs/source/user_guide/configuration_file.rst`. It now teaches v3 directly;
  its final syntax/defaults will be checked against the worker's implementation
  before build/review. Existing useful URL and `starter-catalogue` anchor remain.
  The full producer/template/cross-page conversion retains its Tasks 15–16 scope.
- Task 02 milestone checks: new `test_configuration_v3.py` is metadata-free.
  The five Task 01 identity/diagnostic nodes remain delivered regression checks.
  Source-dependent public v2 tests await their owning conversion tasks, as the
  plan explicitly requires at lines 800–806; no such tests may be weakened,
  suppressed or marked passed merely because the new schema rejects their input.
- Task 02 documentation build: strict HTML and publication boundary passed in
  iteration `yaml-v3-02`. Publication unittests exposed the old all-keys download
  and its schema-specific assertions (`test_all_keys_reference_covers_the_current_schema`).
  Ruling: bring forward only `configuration-reference.yaml`,
  `reference/all_keys.rst` and that test's v3 assertions from Task 16 into Task 02.
  They describe this schema and must agree before the required publication check
  can pass; no CLI, template or execution-producer conversion is brought forward.
  The lead owns these three additional files.
- Additional docs command:
  `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_documentation_plots.py docs/test_release.py docs/test_repository_examples.py::test_slurm_launcher_isolates_retries_and_propagates_failure`
  returned 4 passed, 1 failed, 2 subtests passed, 15 existing warnings.
  The Slurm test actually invokes the CLI with its v2 helper; that exact node is
  future-dependent on Tasks 16/18, not an applicable schema-milestone pass.
  Plot/release checks passed. No assertion was disabled or changed for this failure.
- Task 02 first independent review requested fixes before interface freeze:
  dependency-only atmospheric child handoff; omitted vortex numerical option
  keys; mutable runtime/options aliases into effective controls. The original
  worker owns all three fixes with RED/GREEN evidence and scoped re-review.
  Canonical documentation additions had no contract findings.
  Review checkpoint tree is `2e0e6e76685963107fe8a43d756a81a69f5b9c59`
  (index tree only, not a commit); no task code was committed before review.
- Task 02 canonical docs after reference repair:
  ```bash
  PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-03
  PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-03
  PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
  PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_documentation_plots.py docs/test_release.py
  ```
  All exit 0: strict build without warnings; publication passed; 13 unittests;
  4 plot/release tests and 2 subtests, with the same 15 backend warnings.
  The publication regression resolves the actual annotated YAML and checks the
  literal model-grid/polar field lists, rather than accepting a stale shape.
  The minimal inline YAML was separately resolved without opening any source.
- The canonical configuration and all-keys pages, including rendered reference
  YAML, were inspected live at 880 px and in actual 320-CSS-pixel frame viewports.
  Headings, prose, table wrapping, code scrolling, links and focus were inspected.
  No page overflow or broken images; long YAML lines scroll within their block.
  The reference download returned HTTP 200 and contains integer version 3.
  Enter opened/closed the narrow menu. No new scientific figures or SVGs changed.
  Preview details remain in the ignored handover, not committed machine state.

## Task 02 reviewed interface freeze

Independent reviewer verified all three closures: spec PASS, quality APPROVE;
no new fix breakage or remaining pre-binding interface gap. No scientific
approval, full-suite result or native v3 execution is inferred from that review.

Final lead check:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-04
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-04
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
```

Results: 326 passed (3.81 seconds, no warnings), strict build without warnings,
publication passed, 13 publication unittests passed. Both affected HTML files
were compared byte-for-byte with the desktop/narrow-reviewed iteration 03 and
matched. The retained live preview now shows iteration 04.
The worker also reran 168 applicable numerical/runtime checks; exact supplemental
commands and results are preserved in `task-02-checks.md`.

### Shapes and callers

- `resolve_schema(raw, *, base_dir=None)` retains its three-item return:
  `(resolved_v3_controls, source_requests, polar_fields)`. Public schema accepts
  only integer 3. Unknown metadata is omitted from valid controls, not guessed.
- Each `source_requests[name]` contains
  `fields: {"2d": [...], "3d": [...]}`, `levels`, `derived`,
  `exports: {product: [field/result names]}`, `internal_inputs`, `transforms`,
  `polar_options`, and `binding: None`. This is NOT the existing numerical
  group mapping consumed by `normalize_requests`. Task 04 binds it.
- `polar_fields` maps only participating source names to selected field names.
- `to_runtime(raw, *, base_dir=None)` still returns `SimulationConfig` arguments.
  New fields are `sources`, `source_name`, and `source_requests`.
  `input_sources={}` avoids the old compulsory coupled path. User/tracker
  numerical group requests remain empty until binding. Unknown/multiple-source
  model is `None`; absent region has no tracking method or invented centre.
- `simulation_parameter["request_plan"]` holds:
  ```text
  sources[name]:
    declaration, physical_type, model, profile, files, metadata_origins,
    records, native_grids, requests
  products[]:
    source, product, path, fields, stored_names, dimensions, units,
    representation, time_association
  warnings[]
  deferred_checks[]
  ```
  `physical_type`, resolved `files`, `records`, `native_grids` and binding slots
  remain `None` until the owning metadata task fills them. Product descriptors
  are planned, run-relative publications, not completed outputs.
- `source_document(parent_mapping, name)` retains public valid-source-document
  behavior. It cannot express an unexported dependency as standalone public YAML.
- New shared private handoff `_source_runtime(parent_config, name) -> dict`
  projects an independent pre-binding child with the same numerical argument
  builder as `to_runtime`. Task 03's `coupled.prepare_sources` MUST use this
  route instead of forcing every child through public YAML/preset loading.
  It retains region/dependency context, preserves parent path bases and origins,
  narrows source field products, and removes parent-owned track publication.
  Dependency-only children have `products={}`, no exports/descriptors, and all
  `ExecutionOptions` export switches false. This INTERNAL child view is not
  reloadable public YAML: persist/report the parent request, not the child.
  Public empty-product rejection is unchanged.
- `_runtime_from_resolved` and `_source_document` are private shared builders,
  used only by the public resolver/projection entry points and `_source_runtime`.
  All mutable runtime fields are copied independently of effective controls,
  declarations and plan snapshots. Options likewise own their chunk/shard maps.
- `resolve_operational_overrides(raw, *, base_dir=None, launch_dir=None,
  overrides=None) -> (effective_controls, dotted_origins)` accepts only
  `output_directory`, `cpus`, `overwrite`, `log_level`. Omit unset CLI keys;
  explicit null is invalid, while False must be retained. CLI > YAML > default.
  CLI paths use launch directory; YAML/auxiliary paths use the YAML directory.
- Origins are copied from the parent to source projections, restricted to
  applicable leaves. Do not recompute origins from resolved controls (that
  would relabel defaults as YAML). Projection-only empty blocks are `automatic`.
  Metadata/automatic resource origins are added when observed in Tasks 03/11/13.
- `ExecutionOptions.from_config` reads v3 products, writer and resources.
  New optional `cpus` carries the request; budget enforcement remains Task 11.
  Overwrite defaults false; institutional attribution has no institutional default.
- Existing direct numerical `SimulationConfig` APIs and numerical validators
  remain available. `FA_DEFAULTS` replaces the removed public v2 default path.
  Public version-sensitive branches in settings/execution recognize integer 3.
  Runtime-only omitted vortex keys are supplied without inserting null controls.
- Existing callers: loaders and YAML/mapping classmethods still use
  `load_runtime`/`to_runtime`; preset application skips unknown/multiple reference
  models and does not inject unbound tracker inputs. Preflight/execution/coupled
  still use resolved-config/origin helpers. CLI/templates/producers convert in
  Tasks 15–16. Their future-dependent suites are NOT marked passed.
- Until inventory and binding exist, v3 execution/discovery fails actionably
  before creating output artifacts or falling back to a legacy filename pattern.
  Tasks 03–05 must replace those pending handoffs with selected actual records.

Scientific impact: no new method or numerical change. Public YAML compatibility
changes to v3 only, as approved; no migration/compatibility layer was added.
Shared `dataset`/`document` fixture APIs remain intact; their public producer
conversion stays caller-wide in Task 16. Task 02 is not a runnable v3 pipeline.

## Task 03 implementation and review history

Lead's `input_files.rst` update covers source-local paths, inventory ambiguity,
time/cycle selection, independent clocks and reader costs. Wind declaration
names now use the v3 source syntax; method references and scientific distinctions
remain. The complete inline YAML resolves through `resolve_schema` without
opening inputs; this does not establish input availability or runtime execution.

Strict Sphinx iteration `yaml-v3-05` failed: a lead edit added one space to the
third column's list-table bullets, producing five unexpected-unindent warnings
and a two-level-list error. No preview/publication success is claimed for 05.
The indentation was corrected; iteration 06 strict build/publication and 13
unittests passed. Live 320px inspection then found the three-column wind table
unreadably narrow despite no page overflow. The same four evidence cases were
expressed as two full-width bullets (Earth/grid), without changing their meaning
or site CSS. Iteration 07 passed:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-07
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-07
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
```

All exit 0; no strict warnings, publication passed, 13 unittests passed.
The updated input page was inspected live at desktop880px and320px; the wind
bullets are readable, code scrolls within its block, and there is no page
overflow. Enter opened/closed the menu. Canonical page restored for feedback;
machine-local preview details are kept in the ignored handover.
These are documentation repairs, not scientific or runtime changes.

Task 03 worker handoff reports 488 distinct targeted passes: 78 new inventory
checks (including the 53 required nodes), 342 delivered v3/Task 01 checks, and
68 numerical callers. Exact commands, record/grid/locator shapes, instrumentation
and limitations are in `task-03-checks.md`. Independent review is active.
The lead freshly ran the exact required command:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_source_inventory src/frameit/testing/numerical/test_inspect_metadata.py::test_v3_time_record_selection
```

Result: 53 passed, exit 0, 2.02 seconds, no warnings.

The worker also ran whole-suite diagnostics with the approved local fixture.
Latest snapshot: 468 failed, 1229 passed, 2 errors, 4 subtests passed, 4022
warnings. It predates the final refinements and is NOT a current full-suite pass.
The two setup errors are the old-config CLI fixture in
`test_hpc_execution.py::test_concurrent_cli_attempts_spawn_and_sync_export_exactly`
and its consumer
`docs/test_repository_examples.py::test_independent_checker_accepts_reference_and_rejects_wrong_time_count`.
The producer/conversion and processing integration gaps retain their named later
tasks. Nothing was suppressed or rewritten to hide these failures.

Load-bearing candidate-pool/provider-conflict and operation-dependency rules are
not frozen until the reviewer approves them. Task 04 must enforce any conflicts
that survive actual field/method/level binding before Task 05 can read payloads.

Task 03 independent review requested six focused fixes: retained ancillary
coordinate providers, complete regular-FA geometry, internal-input level-conflict
deferral, moving-coordinate indexers, bounds dimension identity, and harmless
extra timestamp precision. Original worker owns RED/GREEN fixes and a scoped
re-review. Checkpoint tree `c7b93ab91f36a818c6237adc237cafa7dda57f0a` preserves
reviewed files without a code commit. No handoff is frozen yet.

Separate evidence gap: one reviewer helper-based GRIB probe exited 134 at
shutdown, while its direct-constructor repeat exited 0. Exact reproducer has
been retained in the ignored review workspace and forwarded to the worker.
The commands differ in import order, test-module import, core-dump limit and
printing, so they do not isolate a cause. The native diagnostic was
`double free or corruption (!prev)`. No cause or regression attribution is
invented; a bounded controlled check is requested after the six handoff fixes.

Task 03 fix round 1 is implemented, not yet independently closed. Reported final
checks: 98 Task03 (including 75 required/fix cases), 342 delivered regressions and
68 numerical callers: 508 distinct passes. Ancillary scientific flags registered
as coordinates are now included in payload-forbidden checks; no masking method
was added. Revised locator/provider contracts are in `task-03-checks.md`.

The worker reproduced native GRIB SIGABRT after preflight in three controlled
direct/import/helper child variants. Native shutdown qualification remains
blocked. A separate read-only diagnostic agent is investigating causal
boundaries while the original reviewer checks the six fixes. No environment,
library, finalizer or scientific workaround is authorized or presumed.

After the metadata fixes, the lead ran the same strict build/publication/
publication-unittest commands into `build/docs-preview/yaml-v3-08`, plus
`PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_documentation_plots.py docs/test_release.py`.
Results: strict build/publication exit 0; 13 unittests; 4 plot/release tests and
2 subtests passed, with 15 existing backend warnings. The input-page HTML matches
the live desktop/narrow-reviewed iteration 07 byte-for-byte. Preview now shows
08. These documentation checks do not qualify native GRIB shutdown.

Task 03 fix round 1 review: all six original reproductions addressed, but two
new CF-coordinate regressions block freeze. True auxiliary pressure coordinates/
bounds were wrongly excluded; equivalent shared hybrid-coordinate metadata was
wrongly treated as competing scientific providers. Original worker owns round 2
with TDD and scoped re-review. Checkpoint tree:
`cbfd01ee1883e43af9a2655a2df15363404a6358` (not a commit).

Native diagnosis now isolates an installed-library conflict independently of
FrameIt: importing ecCodes before pyproj aborts without generating GRIB or
executing production code. Native ecCodes is actually 2.50.0 from a pip binary
wheel, despite binding metadata 2.44.0; Conda also contains native ecCodes 2.46.0.
The wheel globally loads eckit's bundled PROJ 9.8.1 before pyproj's Conda PROJ
9.9.0. Loading that bundled PROJ globally reproduces SIGABRT; a local-loading
control exits 0. Exact native destructor remains untraced. Both legacy/new
metadata-reader controls exit 0 with four handles opened/released and owned
coordinate arrays. No evidence justifies changing FrameIt handle releases.
No dependencies, environment, imports or finalizers were changed.
Earlier "ecCodes 2.44.0" version evidence describes distribution metadata only;
it is not proof of the actual native decoder version. Native qualification
remains blocked until the mixed stack is resolved and verified.

Task 03 fix round 2 is implemented and under scoped independent review, not
frozen or committed. The worker reports 520 distinct passes: 110 Task03, 342
delivered regressions and 68 numerical callers. All 43 checkpoint test function
ASTs and all 30 pre-Task03 test ASTs remain unchanged; Ruff has zero new
diagnostics against its 22-diagnostic baseline. The portable commands, RED/GREEN
evidence, current owning-grid coordinate/provider shape and limits are in
`task-03-checks.md`. The lead confirmed that the index remains checkpoint tree
`cbfd01ee1883e43af9a2655a2df15363404a6358`; fixes remain unstaged for review.

Fresh lead acceptance on the round-2 tree:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env env FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" python -m pytest -q src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_netcdf_assembly.py src/frameit/testing/numerical/test_grib_lifecycle.py -k v3 --tb=short
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-09
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-09
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_documentation_plots.py docs/test_release.py
cmp build/docs-preview/yaml-v3-08/user_guide/input_files.html build/docs-preview/yaml-v3-09/user_guide/input_files.html
```

Results: 110 passed, 69 deselected, 19 existing backend warnings, 20.41 seconds;
strict build and publication exit 0; 13 publication unittests passed;
4 plot/release tests and 2 subtests passed with 15 existing warnings; HTML
comparison exit 0. No whole-suite or unchanged native-abort rerun is inferred.
The live iteration09 input page was inspected at desktop880px and an actual
320-CSS-pixel iframe viewport. No page overflow; YAML blocks and wind bullets
remain readable. Enter opens/closes the narrow menu. The canonical page is
restored and the owned preview is retained. This is agent inspection, not human
acceptance.

Ruling: keep native-stack repair/qualification separate from this metadata-only
milestone. The zero-handle import reproducer establishes an external blocker;
it does not justify changing FrameIt releases or accepting failed native paths.
Continue safe binding/NetCDF work after the inventory review closes, while
Task05's affected native lane and Task19's full qualification remain blocked
until approved repair and fresh-process checks. Cost if wrong: independent native
defects could remain, so no general native-lifecycle or full-run pass is claimed.

Task 03 fix round 2 review independently closed findings7/8 and preserved the
original six covered closures. A new Important finding9 blocks freeze:
an admitted auxiliary pressure coordinate can name a flagged ancillary
scientific array as its bounds. `_native_grid` then reads that array before
checking shape/role, including excluded samples. The reviewer reproduced the
actual backend request with only the second timestamp selected; this failing
negative probe is not included in the 520 passing checks.
The original worker owns round3: establish an actionable metadata failure
before value access, retain legitimate coordinate metadata, add guarded negative
tests and rerun affected checks. Reviewed index checkpoint is now
`9bb7826dfad4ef1e9926f0d3e98b3160716f912a`, not a commit. No public handoff
is frozen and no code commit has been made before review closure.

Task 03 fix round 3 is implemented and under scoped independent review.
The exact malformed-bounds case, separate dimensional/scientific-role controls
and missing target were observed RED. The covering 30 cases are GREEN,
including legitimate pressure/hybrid and geographic bounds. Reported distinct
total is 533: 123 Task03, 342 delivered and 68 numerical callers; required53 and
combined100 are subsets. All 45 checkpoint / 30 baseline test function ASTs
are unchanged, zero new Ruff diagnostics against22, and diff check passes.
The lead verified the RED/backend trace and GREEN logs, generated a fresh scoped
review package, and confirmed the index remains `9bb7826…`. Final lead acceptance
returned 123 passed, 69 deselected and 19 existing backend warnings in 20.86 seconds
with the same source-selected Task03 command above.
Final documentation commands:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-10
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-10
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_documentation_plots.py docs/test_release.py
cmp build/docs-preview/yaml-v3-09/user_guide/input_files.html build/docs-preview/yaml-v3-10/user_guide/input_files.html
```

All exit 0: strict build without warnings, publication passed, 13 unittests,
4 tests and 2 subtests with 15 existing warnings, and byte-identical input HTML.
The retained live preview now shows 10, identical to the desktop/320px-reviewed 09;
desktop bounds and updated prose were rechecked. No whole-suite, native-lifecycle
or human-acceptance success is inferred.
- Task 02 commit: `8034a6d`. Portable evidence and final record correction were
  independently approved. No further interface freeze is pending.
- Task 03 assigned at `8034a6d`: worker claims the three named production files,
  the three named inventory/assembly/GRIB test modules, and its internal evidence
  appendix. Lead owns public `input_files.rst`, state and integration.
- Next: Task 04 consumes the reviewed freeze below.

## Task 03 reviewed interface freeze

Independent scoped review closed finding9 and confirmed preservation of
findings1–8: spec PASS, quality APPROVE, no new Critical/Important fix breakage
and no new unrelated findings. The reviewer verified RED/backend and final
GREEN evidence rather than replacing it with another suite run. All nine
findings are closed; none is parked. The lead's final 123-case run and strict
iteration10 documentation checks above passed on the reviewed code.
The portable full mapping, exact commands and limitations are in
`task-03-checks.md`; the following is the binding downstream handoff.

### Entry points and callers

- New `io.loader.inventory_source_files(source)` returns
  `(file_inventory, excluded_files, overlapping_patterns)` from declared paths
  only. Physical identity uses device/inode, not archive hashes. Aliases and
  overlaps remain inspectable; separate copies remain separate providers.
- New `core.preflight.inventory_source(conf, name, *, resources=None)` populates
  and returns that source's existing `request_plan` entry. It updates the source
  child's discovered model/format, input files and recorded inventory.
- `prepare_sources(conf, *, check_output=True, execution_options=None,
  resources=None)` retains `(report, children, source_plans)`. The new optional
  resource owner is passed by v3 `preflight`; old numerical callers omit it.
  Other callers are `coupled.run_coupled` and the AROME/FA, NEMO/AROME,
  CROCO/MNH and inspect-metadata tests. Existing numerical behavior is retained.
- V3 children use `_source_runtime(parent, name)`, not reloadable public YAML.
  Independent source clocks/cycles remain independent; no track/common-time
  alignment runs here. Dependency-only children retain their internal empty
  products. Profile-only FA children receive canonical FA options/coordinates;
  a single-source parent receives independent option copies.
- `preflight` and `open_metadata` retain their signatures. The v3 preflight report
  includes effective configuration/origins, sources, file decisions, planned
  products, warnings and deferred checks. These are plans, not publications.

### Records, grids and coordinate provenance

- Each source adds `model`, `format`, `profile`, `physical_type`,
  `metadata_origins`, chronological `files`, `file_inventory`, `excluded_files`,
  `overlapping_patterns`, `fields`, `native_grids`, `records`, `record_inventory`,
  `selected_times`, `dependency_resolution` and `provider_conflicts`.
- Records retain `field_id`, `name`, actual `grid_id`, `level`, decoded `time`,
  `calendar`, `cycle`, `time_bounds`, `clock`, `temporal_metadata` and `locator`.
  NumPy/cftime objects remain decoded internally. GRIB also retains native
  ensemble labels/metadata; a member label is neither a physical source type nor
  a provider-selection permission.
- NetCDF locators retain original payload-dimension `indexers` separately from
  full-clock `coordinate_indexers`. Static payloads may have empty indexers
  while moving geography still needs the selected clock positions.
  GRIB locators retain message index, byte offset and length. FA retains native
  record names, checked half-open zone and size/mtime freshness identity.
- Grid IDs are `grid_` plus a full SHA-256 of grid/coordinate metadata before
  field filtering. Provider paths/provenance and field order do not enter the
  geometry hash. Static grids omit clocks; moving metadata retains its labels.
  A field may list several `grid_ids`; every record identifies its actual grid.
- NetCDF `fields` contains scientific array candidates (`role: array`),
  including unproven auxiliary arrays in `.coords`. `dependencies` identifies
  scientific array support; `coordinate_dependencies` identifies local metadata.
  Needed coordinate metadata lives in `native_grids[grid_id].coordinates` with
  dimensions, values, attributes, dtype and `role: coordinate_metadata`.
- `native_grids[grid_id].coordinate_providers[name]` retains all contributing
  NetCDF provider paths/variables and their selected-time/cycle sample context,
  with both indexer maps. Only equal complete owning grids coalesce. Different
  labels, bounds, coefficients, units or attributes remain distinct.
  Resolve coordinates through the actual owning grid and matching provider/sample
  context; an empty provider sample list establishes no availability.
- Added CF recognition is narrow: admitted one-dimensional `axis=Z`
  air-pressure coordinates/bounds and declared local hybrid-pressure constants.
  It is not a general CF formula implementation or scientific eligibility claim.
  Ancillary/flag/formula scientific inputs remain unread array candidates.
  Declared bounds are validated for existence, ordered dimensions, endpoint
  requirements and conflicting scientific/flag roles before value access.
  Legitimate geographic vertex layouts remain supported.

### Binding and execution gates

- `record_inventory` is the closed candidate pool within selected source
  times/cycles. `records` initially contains known requests/dependencies and
  unresolved method candidates. Final scientific records may be narrowed/promoted
  only from that pool, never discovered from another file or a wider clock.
- Pending field/method/level conflicts retain every locator. They authorize
  neither a provider choice nor payload reads. Task04 must recompute identity,
  category, bound-time/native-axis availability and all provider conflicts after
  promotion and actual binding; an initially empty conflict list is not clearance.
  Reject every surviving conflict. Metadata coalescence never exempts scientific
  duplicate providers. Shared GRIB geometry does not establish vertical ordering.
- Regenerate chronological `files` from final bound locators and resolve file
  relevance only after dependencies bind. Preserve both indexer mappings,
  calendars, cycles, intervals and FA eligibility/scaling/sampling safeguards.
- `requests.binding` remains `None` here. Existing execution guards still reject
  unbound v3 processing before outputs. Actual adapters, scientific support,
  units/levels, associations and output schemas remain their owning later tasks.
  Metadata-only backend guards do not prove future selected-time payload slicing.
- Native-stack repair/qualification remains explicitly blocked as described
  above. It is not an established Task03 handle defect and has no code workaround.

Scientific impact: metadata discovery/selection only; no new scientific method,
field conversion, interpolation, masking or diagnostic. Compatibility: no
additional public YAML or output-schema change in Task03; direct numerical APIs
remain. No source dataset or shared environment was modified.

## Task 01 evidence

Root cause: CLI removed all paths below `~/.local`, including the selected
worktree. The parent retained its cached package, but spawned workers selected
the competing editable installation. The sole sanitizer call remains at CLI
import. It now removes only `site.getusersitepackages()` and descendants,
including an explicit `PYTHONUSERBASE`, while retaining sibling paths and order.
Ordinary `frameit info` reports `frameit.__file__`; `info --short` is unchanged.

TDD commands (all in `frameit_env`, selected source via `PYTHONPATH="$PWD/src"`):

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_hpc_execution.py -k 'test_cli_keeps_checkout_under_local_in_parent_and_spawn or test_cli_info_reports_selected_installation' --tb=short
```

- RED before production edits: 5 failed, 23 deselected; four exact worker-path
  mismatches and one absent diagnostic line. Parent paths were correct.
- GREEN: 5 passed, 23 deselected.
- Final `.pth` editable cases were mutation-checked against the old exclusion:
  four expected failures, then the production fix restored.

Required acceptance command:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_documentation_example.py src/frameit/testing/numerical/test_inspect_metadata.py
```

Final result: **54 passed, 6 existing warnings**, exit 0, 22.25 seconds.
This includes real sync/spawn export and independent reopening. The lead's
fresh import probe also confirmed that cached and fresh lookup origins retain
this checkout after CLI import.

Supplemental full suite, before the local fixture was materialized:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q --tb=short
```

Result: **1280 passed, 18 failed, 4 subtests passed**, exit 1, 365.02 seconds.
All failed nodes required absent frozen files; their absence was confirmed.
No baseline full-suite delta is claimed. Exact failures (relative to
`src/frameit/testing/numerical/`):

```text
test_configuration_integration.py::test_frozen_matrix_yaml_and_mapping_requests_match[AROME]
test_configuration_integration.py::test_frozen_matrix_yaml_and_mapping_requests_match[MNH]
test_grib_lifecycle.py::test_direct_grib_loading_and_native_shutdown_in_fresh_interpreter
test_grib_lifecycle.py::test_matrix_fixture_planning_and_native_shutdown_in_fresh_interpreter
test_grid_representations.py::test_real_mnh_native_faces_match_source_file
test_output_layout.py::test_grib_cache_is_local_distinct_and_reused
test_polar_heat_flux_ci.py::test_real_heat_records_preserve_signed_values_and_energy_units[sshf-146]
test_polar_heat_flux_ci.py::test_real_heat_records_preserve_signed_values_and_energy_units[slhf-147]
test_polar_heat_flux_ci.py::test_heat_flux_ci_energy_coverage_bounds_and_ordinary_reader
test_polar_heat_flux_ci.py::test_missing_heat_record_retains_completed_quantity_and_failed_child
test_polar_rainfall_ci.py::test_real_record_retains_mass_units_and_cumulative_time
test_polar_rainfall_ci.py::test_ci_pilot_independent_mass_coverage_time_and_plain_netcdf
test_polar_rainfall_ci.py::test_missing_required_rainfall_leaves_a_failed_report
test_polar_thermodynamics_ci.py::test_real_snapshot_preserves_levels_time_zero_and_relative_humidity_above_100
test_polar_thermodynamics_ci.py::test_ci_thermodynamic_representations_weighting_and_netcdf
test_polar_thermodynamics_ci.py::test_missing_positive_lead_tke_fails_instead_of_dropping_times
test_polar_wind_comparison.py::test_full_analytical_and_native_comparison_exports_with_plain_readers
test_pressure_centroid_mnh.py::test_bundled_mnh_header_identifies_pressure_as_missing
```

Full-suite warnings: one existing NumPy binary-size warning and 3096 existing
xarray/netCDF4 shape deprecations. No warnings/failures were suppressed.
These fixture checks must run with the approved local data during integrated
verification; they are not marked passed here.

Docs: the additive diagnostic is documented in
`docs/source/getting_started/installation.rst`. Commands:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-01
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-01
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
```

All exit 0: no strict Sphinx warnings, publication boundary passed, 13 unittests
passed. The full pytest run also covered the documentation pytest files.
The installation page was inspected in the live GUI at 880 px and in an actual
320-CSS-pixel iframe viewport. New prose, links, focus, code-block scrolling and
page bounds were inspected; no page overflow. The native menu opened and closed
with Enter (`shift` classes appeared/disappeared). The canonical page was
restored in the retained preview tab. This is agent review, not human acceptance.
Server/tab/restart details are kept only in the ignored session handover.

Scientific impact: none. Configuration/output compatibility: unchanged.
No packages were reinstalled; no source datasets or unrelated work were changed.
