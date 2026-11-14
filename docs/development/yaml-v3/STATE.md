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
| 03 | done | task-03 worker + independent reviewer | 02 | `9ad6f19`; all nine findings closed, record/grid handoff frozen below. |
| 04 | done | task-04 worker + independent reviewer | 03 | `37aaf5f`; both Important findings closed, field/level handoff frozen below. |
| 05 | done | lead + three adapter workers + independent task reviewer | 04 | `73c4147`; native/read gate approved,788 distinct targeted passes and final required5. |
| 06 | done | Task06 worker + lead + independent reviewer | 05 | Four Important findings independently closed; reviewed handoff below,64 new nodes pass. |
| 07 | ready | unassigned | 05 | SEA/FA declarations; shared integration claims start after the Task06 local commit. |
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

Task 03 commit: `9ad6f19`. The working tree was clean after the local commit;
nothing was pushed.

## Task 04 work in progress

Assigned at `9ad6f19` after the inventory freeze. Worker claims
`processing/requests.py`, `core/preflight.py`, `utils/units.py` only if needed,
the request/grid tests, `test_native_extraction.py` only for affected callers,
and `task-04-checks.md`. Shared fixtures, adapters, configuration/settings,
coupled/execution and all other files remain unclaimed.
Lead claims `task_guides/field_selection.rst`, consequential clarifications in
`user_guide/configuration_file.rst`, state/checklist and integration.
The worker must record the exact binding map/entry points and evidence-based
roundoff rule before Task05 consumes them. Representation fixtures belong here;
actual transforms remain Task08. Unknown later method support stays deferred
and must not permit premature execution. Native repair remains unauthorized.

The lead's field-selection draft uses source-wide v3 controls and a complete
illustrative YAML request. The request resolves through `resolve_schema` with
the expected 2D/3D fields and hPa selection; no input availability or execution
was checked. The old strategy-section anchor is preserved. Obsolete CLI/group
examples were removed from this page, not implemented under another command.
Full CLI/cross-page conversion retains Tasks15–16 ownership.
The draft passed:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-11
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-11
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
```

All exit 0: strict build without warnings, publication passed, 13 unittests.
The field-selection page was inspected live at desktop880px and actual320px.
Headings, complete YAML, selector bullets and units/representation prose fit;
no page overflow, and the old strategy anchor remains present. Enter opens and
closes the narrow menu. The canonical page and owned server remain available.
This is agent visual inspection, not human acceptance or binding verification.
The worker's roundoff/binding evidence must be reconciled with this draft before
review and a Task04 commit.

Task04 first report: DONE_WITH_CONCERNS, 55 required / 653 distinct targeted
passes reported. The explicit post-inventory binder preserves Task03's
inventory-only APIs and keeps executable binding unset when scientific method
support remains pending. That integration belongs to Task05, not a public-run
success here. Native qualification remains separately blocked.

The worker identified a real metadata-evidence gap before review: FA field
descriptors are merged by field, losing which provider/sample supplied the
labels. It safely left multi-provider cube label bindings pending rather than
applying the last descriptor to other files.
Ruling: bring forward only the necessary per-record FA metadata retention into
Task04, within the worker's existing `preflight.py` claim. Raw FA records will
retain their own `native_descriptor`; the merged field descriptor remains an
inventory summary, not proof of per-sample eligibility or labels. Binding must
use the matching selected record's descriptor for raw eligibility and cube
labels. Add selected/excluded-file and conflicting/missing-evidence tests before
the correction, then rerun affected checks. This is an additive internal handoff,
not a new FA method, broader admission or source-interpretation clearance.
Cost if wrong: duplicated metadata increases inventory size, and format-specific
consumers must preserve/use the new record evidence; independent review must
check that no last-provider assumption or wider inventory remains.
Task07 still owns scientific source interpretation/decode-time scaling, and the
existing pending-execution safeguards must remain. This correctness concern is
addressed before dispatching Task04's independent review.

Fresh lead required command:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py::test_v3_field_and_level_binding src/frameit/testing/numerical/test_request_selection.py::test_v3_vertical_units src/frameit/testing/numerical/test_grid_representations.py::test_v3_representation_level_binding
```

Result: 55 passed, no warnings, 2.77 seconds. This precedes the FA provenance
follow-up and is not its verification or a completed Task04 claim.
The canonical guide now explains the reported storage/conversion roundoff rule,
with a link from the configuration reference; the rule still awaits independent
review. Missing-unit warnings are described directly. A long formula in
iteration12 scrolled even at desktop width; equivalent three-line arithmetic
fits the desktop block in iteration13 without changing the rule.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-13
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-13
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
```

All exit 0: strict build without warnings, publication passed, 13 unittests.
Iteration12 also passed the same checks and
`PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_documentation_plots.py docs/test_release.py`:
4 passed and 2 subtests, 15 existing warnings.
Both affected iteration13 pages were inspected live at desktop880px and
actual320px: no page overflow, readable prose, valid roundoff-reference target;
the narrow formula scrolls within its block and its right edge is reachable.
The field-selection canonical page is restored and the owned server retained.
No source-method or human acceptance is inferred.

### Native blocker: scoped repair authorization and history

A read-only distribution-metadata check in `frameit_env` confirms
`eccodes`, `findlibs`, `cfgrib` and `pyproj` are Conda-owned. The conflicting
`eccodeslib 2.50.0.33` and `eckitlib 2.5.0.33` are pip-owned.
No installed distribution declares a dependency on `eccodeslib`; only
`eccodeslib` declares a dependency on `eckitlib`. This does not establish that
unregistered external scripts never use those wheels.
Proposed repair is removal of only these two pip binary packages, retaining the
declared Conda stack and all other versions. Shared-environment authorization is
required, and any authorized change must wait until the active worker/checks are
idle. No removal, upgrade or environment modification has occurred.
The maintainer selected **Allow scoped repair** in the session question:
remove only `eccodeslib 2.50.0.33` and `eckitlib 2.5.0.33`, retain the declared
Conda libraries, then run dependency/native-shutdown verification. No upgrades,
other package changes or environment recreation are authorized. This permission
does not clear qualification. The repair is queued until the active Task04
worker/checks are idle; no removal has yet occurred.

### Task04 follow-up ready for review

The original worker's pre-review correctness follow-up reports 55 required,
101 Task04, 123 Task03, 342 delivered and 104 numerical checks:
670 distinct targeted passes. The 27 FA evidence cases are a subset.
The producer→inventory→binder regression was observed RED (15 failures) before
raw FA records retained their own `native_descriptor`. Matching record-local
identity, clocks, native shape/header, eligibility and cube labels now replace
merged-summary assumptions. Synthetic cube records do not inherit a raw part's
descriptor, and FA caches distinguish actual samples.
Multi-provider/excluded-file evidence is no longer an unresolved blanket label
deferral. Task07 interpretation/scaling and Task05 integration remain pending;
no FA execution clearance or source-method validation is claimed.
75 original functions, including all 50 original test/fixture functions, remain
unchanged; `_fa_source_inventory` is the approved original-function exception.
Ruff remains 8/8 baseline/current, zero new. No worker staging/commit occurred.
Fresh independent review will inspect the complete code/docs/evidence, including
the additive record contract and the roundoff rule.

### Authorized native repair and observed verification

After the Task04 worker/checks finished, the lead verified pip ownership,
approved versions and RECORD scope: 69 `eccodeslib` entries and 778 `eckitlib`
entries are confined to their own package/dist-info/bundled-library directories.
No recorded path escapes those directories.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pip uninstall -y eccodeslib eckitlib
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pip check
```

Both exit 0: exactly the approved `eccodeslib 2.50.0.33` and `eckitlib 2.5.0.33`
were removed; `No broken requirements found.` No upgrade, replacement, download,
other package change or environment recreation was performed.
Post-repair commands:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_grid_representations.py -k v3 --tb=short
PYTHONPATH="$PWD/src" conda run -n frameit_env env FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" python -m pytest -q src/frameit/testing/numerical/test_inspect_metadata.py src/frameit/testing/numerical/test_netcdf_assembly.py src/frameit/testing/numerical/test_grib_lifecycle.py -k v3 --tb=short
```

Results: 101 passed, 68 deselected, no warnings (3.78 seconds);
123 passed, 69 deselected, 19 existing warnings (19.26 seconds).
These repeat covered checks, not extra distinct passes.

Six fresh-process controls now each exit 0: ecCodes then pyproj; reversed import
order; ecCodes then production imports; unchanged legacy metadata scanner;
v3 inventory scanner; and direct v3 preflight. Actual native/API ecCodes is now
2.46.0. Each process maps one PROJ library, Conda's `libproj.so.25.9.9.0`, and
the Conda ecCodes library; no removed wheel library is mapped.
Scanner/preflight controls retained four opened/four released handles and owned
coordinate arrays, with scientific value access forbidden. Full child
commands/stdout/stderr and code hashes remain in the ignored native handover.
This resolves the reproduced installed mixed-library/import-order blocker in
these controls. It is not general native qualification, all error-path coverage,
a full v3 pipeline, or scientific/bitwise agreement across decoder versions.
Task19's broader native qualification remains open.

The remaining worker regression selections were freshly rerun after repair,
using the exact portable commands in `task-04-checks.md`: 342 delivered passed
(12 deselected, 4 existing warnings); 73 numerical passed without warnings;
31 assembly/import passed (33 deselected, 71 existing warnings).
With the preceding 101/123 runs, all 670 distinct targeted checks now have
post-repair passing evidence, not only the pre-repair worker snapshot.
The existing direct GRIB payload/fresh-shutdown node also passed:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env env FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" python -m pytest -q src/frameit/testing/numerical/test_grib_lifecycle.py::test_direct_grib_loading_and_native_shutdown_in_fresh_interpreter --tb=short
```

Result: 1 passed, no warnings, 1.32 seconds. No whole-suite or general native
qualification is inferred.

Final post-repair documentation checks:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-14
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-14
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_documentation_plots.py docs/test_release.py
cmp build/docs-preview/yaml-v3-13/task_guides/field_selection.html build/docs-preview/yaml-v3-14/task_guides/field_selection.html
cmp build/docs-preview/yaml-v3-13/user_guide/configuration_file.html build/docs-preview/yaml-v3-14/user_guide/configuration_file.html
```

All exit 0: strict build without warnings, publication passed, 13 unittests,
4 tests and 2 subtests with 15 existing warnings; both rendered pages exactly
match the desktop/320px-reviewed iteration13. The retained live preview now
shows iteration14. Independent Task04 review is active; no freeze or commit yet.

Task04 independent review requests changes for two Important defects:
coordinate-unit conversion retains contradictory numeric range attributes, and
destination-grid neighbour support is incorrectly trimmed on ancillary arrays.
The reviewer reproduced both in a focused in-memory probe; the 670 passing
checks do not cover them. Original worker owns round1 RED/GREEN corrections in
the claimed request/grid suites, then scoped independent closure.
Reviewed checkpoint remains `eb810d0878883efeda35ab350357ceb84768775c`.
No binding freeze, Task04 commit or Task05 implementation is authorized yet.
The existing payload/transform/output/large-archive gaps remain assigned to their
owning later tasks, not claimed passed by this review or native-stack repair.

Task04 fix round1 is implemented, not independently closed. The covering cases
were RED (7 failed, 28 passed) before correction and GREEN (35 passed) afterward.
Reported final results: 64 required, 110 Task04 and 679 distinct targeted passes.
The lead inspected covering/required logs and generated a scoped fix package
against the unchanged `eb810d0…` index checkpoint.
Coordinate conversion now scales existing range attributes, and subsetting
refreshes or removes unsupported `actual_range` without fabricating a range.
Internal ancillary read support is separated from product output selection,
including also-exported and nested dependencies; actual missing support fails
and unresolved support stays pending.
The primary portable handoff and canonical guide now reflect those roles.
`binding.dependencies` is not restricted to unexported names; product `[5,0]`
does not become internal `[5,6,0,1]`. Final meaning remains subject to scoped
review before freeze. The original reviewer is checking both closures and new
fix breakage; lead focused110 and strict iteration15 checks are running.
No Task04 commit, Task05 implementation or native-probe rerun has occurred.

Fresh lead fix1 checks:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_request_selection.py src/frameit/testing/numerical/test_grid_representations.py -k v3 --tb=short
PYTHONPATH="$PWD/src" conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/yaml-v3-15
PYTHONPATH="$PWD/src" conda run -n frameit_env python docs/check_publication.py build/docs-preview/yaml-v3-15
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q docs/test_documentation_plots.py docs/test_release.py
cmp build/docs-preview/yaml-v3-14/user_guide/configuration_file.html build/docs-preview/yaml-v3-15/user_guide/configuration_file.html
```

All exit 0: 110 passed, 68 deselected, no warnings (3.84 seconds);
strict build without warnings; publication passed; 13 unittests; 4 tests and
2 subtests with 15 existing backend warnings; unchanged configuration HTML.
The updated field-selection page was inspected live at desktop880px and
actual320px. Range-attribute and ancillary-stencil prose fits without page
overflow. Configuration remains byte-identical to its reviewed iteration14.
The canonical field guide15 and owned server are retained. This is neither
human acceptance nor independent finding closure; scoped review is still active.

## Task 04 reviewed interface freeze

Independent review closed both Important findings: spec PASS, quality APPROVE,
no new Critical/Important fix breakage and no new out-of-scope findings.
No finding is parked. The reviewer checked the seven-failure RED, 35-case
covering GREEN, 64 required and six logs supporting 679 distinct targeted passes.
The lead's fresh 110-case check and strict iteration15/publication/rendered-page
checks above passed on this reviewed code. Task04 is a metadata-binding milestone,
not a completed v3 execution pipeline or scientific-method validation.

### Entry points, mutation and snapshots

- New pure `processing.requests.bind_requests(source, request, *,
  representations=None, required_inputs=()) -> binding` consumes the populated
  source and declaration mapping without mutating them. `required_inputs` is an
  internal closed-pool promotion request, not a public selector.
- New `core.preflight.bind_source(conf, name, *, representations=None,
  required_inputs=()) -> binding` records the result in an inventoried source.
  Existing inventory APIs remain inventory-only and existing numerical request
  helpers retain their signatures/behavior. Current production callers do not
  yet invoke the binder; Task05 owns integration.
- On `status: bound`, both `conf.source_requests[name]["binding"]` and the source
  plan's `requests.binding` receive the map; `source.field_binding` is available
  for inspection. Final array records/files/file decisions are regenerated from
  selected candidate locators, checked provider conflicts are cleared, source-local
  `input_files` and the plan inventory are updated, and warnings are recorded/logged.
- On pending support, only diagnostic `source.field_binding` is available; both
  executable binding slots remain `None`. Records/files/conflicts retain their
  inventory view. A failed rebind clears old executable and diagnostic clearance
  before raising. Pending status is never permission to read payloads.
- Bind after `prepare_sources`, whose children and parent snapshots are independent.
  Task05 must bind each actual consumer child and deliberately propagate bound
  source/request snapshots; rebuilding children does not preserve earlier binding.

### Exact mapping roles for adapters

- `binding` contains `status`, `products`, `dependencies`, original selected
  `records`, `warnings` and `deferred_checks`. Each product/field descriptor has
  `field_id`, `category` and bound `records`.
- Bound records retain all original identities, decoded clocks/calendars/cycles/
  intervals and locators, including both indexer maps. They add
  `selection_grid_id`, native read `source_positions`, and `vertical` metadata.
  `vertical` retains dimension/coordinate name, representation positions,
  original `source_native_indices`, selected labels/units/origins and selected
  coordinate/bounds descriptors. Full literal shapes are in `task-04-checks.md`.
- Product records govern requested output order/coordinates. Internal ancillary
  `binding.dependencies` describes native read support and is not restricted to
  unexported names. One name may appear in both maps: exported `[5,0]` and internal
  `[5,6,0,1]` remain distinct. Do not deduplicate descriptors by field name, export
  the neighbour union, or reapply the output selector to trim internal support.
  Nested support propagates by original index in matching time/cycle/member
  contexts; unsupported axes/methods remain explicit pending diagnostics.
- All scientific promotion and final availability/provider checks stay within
  `record_inventory`. Coordinate support resolves through each actual owning
  grid/provider/sample context. Metadata equivalence never clears scientific
  conflicts; no broader clock/file discovery or provider selection is allowed.
- Representation input is
  `representations[product][field][actual_native_grid_id] = {grid_id, grid,
  sampling, source_positions: {destination_position: [native_positions]}}`.
  A supplied destination must correspond to an explicitly requested sampling.
  Native/model-grid/polar W bind separately; no actual transform is implemented
  by a coordinate fixture. Genuine missing selected levels/neighbours fail.
- Raw FA records now additionally retain their own copied `native_descriptor`.
  Synthetic cube records have no raw descriptor; resolve their parts through
  matching raw records. The merged field descriptor is summary only.
  Local identity/clock/shape/header/eligibility/labels are checked before binding;
  excluded-file summaries cannot supply another sample's evidence. Preserve
  descriptors through promotion/snapshot copies. FA interpretation/scaling remains
  pending Task07 and does not receive executable clearance here.

### Numerical and metadata contract

- One source selector binds each requested representation independently.
  Explicit list order/original nonnegative indices, inclusive ranges/intervals,
  native grid order, singleton vertical axes and verified physical ranges are
  preserved. Missing/duplicate/ambiguous levels fail before writing.
- Compatible coordinate conversions use the existing unit definitions.
  Missing source units with requested units are an explicit unscaled user
  assumption; both missing remain unknown. Both cases warn and are recorded.
  Physical field values/units and source descriptors remain unchanged.
- Matching error is half the inventoried floating spacing scaled to target units,
  plus four binary64 converted-label spacings; explicit lists add four requested
  value spacings. Integer storage adds no storage error. Use finite inward
  spacing at extremes, count all matches and reject ambiguity/resolved duplicates.
  Intervals use the coordinate error at closed endpoints. Export converted stored
  labels, not copies of request numbers. Evidence/rule are independently reviewed.
- Labels/bounds and existing `valid_min`, `valid_max`, `valid_range` use consistent
  converted units. Existing `actual_range` is refreshed after subsetting or removed
  when its finite numeric assertion is unsupported; absent ranges are not invented.
- GRIB axis order follows the existing cfgrib convention per inventoried field:
  decreasing pressure, increasing other admitted labels. Horizontal grid identity
  and message ordering alone are not vertical support.

Scientific impact: explicit existing-label binding and coordinate-unit metadata
conversion only; no scientific array reads, interpolation, masking or new
diagnostic. Compatibility: no new public YAML keys/defaults or output schema;
internal ancillary support roles and FA record metadata are specified above.
Native-stack repair is complete for the reproduced blocker; general native,
payload/transform/output and large-archive qualification remain their later gates.
No source data or unrelated user work was modified.

Task04 commit: `37aaf5f`. The working tree was clean immediately afterward;
nothing was pushed.

## Task 05 work in progress — native slice first

Starting commit: `37aaf5f9b692cc60f9921a5191e0484fd12e6620`.
The lead implements the first runnable slice inline under the approved task
plan/TDD, with independent review before adapter delegation. No Task05 completion
or general native qualification is claimed.

Lead claims: `core/runner.py`, `core/coupled.py`, `core/execution.py`,
`io/netcdf_utils.py`, `io/netcdf_export.py`, new
`testing/numerical/test_v3_execution.py`, basic native-output guidance in
`docs/source/user_guide/output_files.rst`, input-reader guidance only if affected,
internal evidence and state/checklist. Shared fixtures, the frozen request/
inventory APIs, configuration/settings and other adapters remain unchanged
unless a necessary caller-wide claim is explicitly recorded.
The existing `create_first_run_input` helper is reused without modification.

Acceptance starts with complete YAML → `load_runtime` → `execute_simulation`
→ ordinary-reader reopening of the native scalar. Tests must catch changed
values/units/masks/coordinates/times, accidental track/diagnostic output, source
mutation and clobbering. Then atmosphere/ocean unequal clocks must remain separate.
Only after the native slice's review will selected-record adapter assignments
be split into disjoint claims. Later region/transform/polar/full-schema work keeps
its owning tasks; incomplete paths must fail explicitly, not fall back to legacy
group selection, read excluded samples or invent centres.

Task05 native-slice TDD: the two required end-to-end cases were observed RED at
the unbound guard, then GREEN through execution and independent reader reopening.
Two additional safety cases were RED before input-collision and external-inventory
checks. Latest focused command:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py src/frameit/testing/numerical/test_output_layout.py::test_direct_export_uses_products_directory src/frameit/testing/numerical/test_configuration_v3.py --tb=short
```

Result: 333 passed, 12 warnings; six native cases, 326 schema cases and one
existing direct-export caller. Actual h5netcdf/netCDF4 payload guards saw only
selected sample1 with requested time chunks of2. Binary/shape warnings remain;
the optionality test also exposes xarray's optional-entrypoint probe warning when
ecCodes imports are unavailable. No optional-backend dependency is required for
the checked native execution. The earlier 18-failure diagnostic found one new
SimpleNamespace exporter regression, now corrected and green, and 17 unchanged
public-v2 producer failures. Raw exact names/results remain in the review packet.

Ruling: `selected_records` on the v3 loader route carries the complete executable
binding mapping, not the original `binding.records` list, because product and
internal same-name stencils must remain distinct. `source_plan` supplies the
owning grid/provenance metadata. Existing numerical signatures/return nesting
remain usable when these optional arguments are omitted. Native user groups use
actual grid IDs; internal groups use `tracker["internal"][grid_id]`. The same
prepared child consumers pass from binding to execution rather than rebuilding
them. These are provisional internal APIs pending the native-slice review, not
an adapter-delegation freeze. Cost if wrong: downstream adapter work must wait
and may require this small handoff to change; no public selector/schema changes.

Native-slice independent review requests two Important corrections: an occupied
log path can alias and modify a source, and an admitted `valid_time(sample)` clock
fails concatenation. Lead fixround1 owns the original code and the narrowly
necessary `utils/logging.py` write boundary. New real-run tests were RED3, then
GREEN3. Logging now exclusively creates a fresh file, suffixing occupied names;
the shared time normalizer swaps a one-dimensional clock's actual axis and keeps
its original sample-index auxiliary. No code or environment workaround was added.

Fresh covering command adds `src/frameit/testing/numerical/test_logging.py` to
the preceding native/schema/direct-export command: 339 passed,2 subtests passed,
16 warnings. The original31-case numerical assembly/import selection also passes
after the shared clock correction,33 deselected and71 existing warnings.
Ruff comparison is23→23 with no new diagnostics; diff check passes.
Original reviewer must verify both closures and new fix-diff breakage before any
adapter delegation. Reviewed index checkpoint is
`2801dba49d72daa9b48646f9d034e38498140bbc`; this is not a task commit.
The deliberate optional-entrypoint warning is a recorded deferred Minor for
whole-branch triage, not silently suppressed.

Output-guide draft now describes native full-domain copying, source/product
paths, independent clocks, reader checks and applicable v3 storage keys without
enabling diagnostics. Iteration16 failed because of list-table indentation;
that table was replaced by readable full-width bullets. Strict Sphinx,
publication checks and13 publication unittests pass in17/18/19. The18 output page
was inspected live at desktop880px and actual320px: no page overflow, code's
right edge reachable and images loaded; Enter opens/closes the native menu.
Iteration19 adds the fresh-log policy; its rendered delta remains to inspect.
These documentation changes still need final Task05 review. No scientific or
human acceptance is implied.

The added iteration19 log paragraph is now inspected live at desktop880px and an
actual320px iframe: it fits, without page overflow. The canonical output page19
is restored in the retained tab; server/restart details remain in the ignored
preview handover. Independent native-slice scoped review is active; no adapter
assignment or closure has occurred.

Native-slice scoped re-review independently closes both Important findings:
spec PASS, quality APPROVED for this gate, no new fix-diff breakage. Minor warning
accounting remains deferred. This permits adapter assignments, not Task05 closure.
Reviewed native checkpoint is now staged tree
`d9ca115c20c06e05241216566280c7708460430b`; HEAD remains37aaf5f.
The loader/consumer mapping above is frozen for these bounded assignments.

Adapter claims are disjoint: one NetCDF/MNH/NEMO/CROCO worker owns
`io/netcdf_utils.py`, `nemo_utils.py`, `croco_utils.py` and new
`test_v3_netcdf_reads.py`; GRIB owns `grib_utils.py` and new
`test_v3_grib_reads.py`; FA owns `fa_utils.py`, `fa_backend.py` only if needed,
and new `test_v3_fa_reads.py`. Each writes its own ignored report/logs and must
preserve the reviewed baseline, existing fixtures and numerical paths. Lead
retains runner/coupled/execution/writer, central tests, docs/state and all staging.

Ruling: combine the two NetCDF model-family lanes under one owner because their
selected-read and admission paths share `netcdf_utils.py`; GRIB and FA remain
parallel disjoint work. Cost if wrong: that lane may take longer, but there is no
overlapping implementation authority or duplicated scientific default.
FA must prove the selected-locator mechanism on already-admitted explicit direct
numerical paths while public method/scaling binding remains Task07-pending.
No artificial bound map or full public FA pipeline pass is authorized. An exact
shared-interface need must come back to the lead before a conflicting change.

FA lane first report implements an internal `fa_selected_array(record,
source_plan, *, options, diagnostics_path=None)` leaf and optional grouped-loader
keywords, while keeping genuine public FA interpretation/scaling rejection.
This is consistent with the assigned stage boundary; it does not establish
public FA dispatch or method clearance. The worker reports42 new cases plus27
unchanged numerical/resource checks passing,188 v3 binding/inventory checks
passing with the approved fixture, clean scoped Ruff and unchanged staged tree.
The broader regression diagnostic records57 unchanged public-v2 schema failures;
all exact node names and logs are in its ignored report.

The lead inspected its owned production diff and test surface, without replacing
independent review. A bounded wording follow-up is active in the same worker:
remove the internal task number from the new user-visible pending-FA error,
preserving the failure and scientific/payload assertions. NetCDF/GRIB workers
remain active in disjoint files. All lanes will enter combined independent
Task05 review after integration; none is independently approved yet.

FA wording follow-up returned: all42 new cases and both gate checks pass, scoped
Ruff clean; the error no longer names an internal task. Public FA interpretation/
scaling rejection remains intact. The final lane still awaits independent review.

GRIB lane reports31 new selected-message cases and66 scoped covering passes,
with exact real ecCodes read/handle instrumentation. Its one unchanged public-v2
matrix-planning failure and explicit reader limits are named in its ignored
report; they are not passed qualifications. The lead read its interface/evidence
and added a direct public YAML/API native-U integration case. It was observed RED
at the missing runner dispatch, then GREEN after native loader dispatch was
connected through the shared selected-record arguments:

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_execution.py::test_native_grib_component_roundtrip --tb=short
```

Result:1 passed, no warnings. A fresh ordinary-reader process checks literal
values, native field units, a singleton pressure axis and selected00:00/02:00
times; no V companion/diagnostic is exported, input bytes remain unchanged and
no index appears beside the source. No all-GRIB or scientific qualification is
inferred. Input-reader guidance now explains selected-message decoding and
whole-message memory cost; updated output prose avoids implying that native
copying applies analysis basis exceptions. These newest doc deltas still need
strict build/publication/live inspection. NetCDF worker remains active.

### Task05 integrated verification and full-review gate

All three adapter workers have returned and are idle. NetCDF reports51 new
real-backend cases, GRIB31 and FA42. Lead integration adds full public native
GRIB-U and CROCO formula-support/output cases and covers SciPy/NetCDF3 selection.
The latter actual backend check reads only selected sample1, like h5netcdf and
netcdf4. Existing fixture helpers remain unchanged.

Two real integration defects were observed RED and corrected: the new runner
version check broke an existing SimpleNamespace numerical caller, and explicit
`zeta` output conflicted with its role as another field's formula coordinate.
Optional-version dispatch and consistent explicit-output promotion now preserve
those caller/value contracts. No scientific field conversion or guessed assembly.

Final source checkpoint is staged tree
`d47ff97972f72912b6ef744ed7cf236fcd8b264d`, not a task commit. The lead freshly ran
the exact commands in `task-05-checks.md`:

- required5 passed/10 warnings;
- main integration467 passed,2 subtests/29 warnings;
- delivered binding/inventory233 passed,137 deselected/19 warnings;
- HPC/FA resources43 passed,14 deselected/4 warnings;
- existing legacy assembly31 passed,33 deselected/71 warnings.

JUnit comparison confirms774 distinct targeted nodes, no overlap/failures/errors/
skips. All136 new Task05 cases are included. All13 changed Python files compare
Ruff50baseline→50current, no new diagnostics. Diff check passes.
Known external and deliberately induced warning debt remains visible.

The full project command also completed in frameit_env with the approved
read-only fixture and no selection filter:468 failed,1523 passed,2 errors,
4 subtests,4049 warnings,296.79 seconds. All470 exact failure/error node IDs match
each of three retained Task03 full-suite logs, with no new or removed failed node.
The two setup errors remain the old public CLI fixture in
`test_hpc_execution.py::test_concurrent_cli_attempts_spawn_and_sync_export_exactly`
and `docs/test_repository_examples.py::test_independent_checker_accepts_reference_and_rejects_wrong_time_count`.
428 XML failures/errors hit strict v3 admission;42 are CLI/template wrapper cases.
All names, raw tracebacks and exact delta are retained in the ignored named
reports referenced by `task-05-checks.md`. This is not full-suite green.

Unsupported multi-varying-axis NetCDF assembly, GRIB stencil/layout restrictions,
public FA interpretation/grouped dispatch and conflicting-grid writer publication
remain explicit limits, not passed qualifications. No pending binding is treated
as executable. Full method/coordinate/writer/report/CLI gates retain their
assigned later tasks. The combined reviewer must judge this against Task05's
own native/read-mechanism stage requirements, not infer scientific validation.

Strict/publication/13 publication unittests pass21;20 also passed4 plot/release
and2 subtests. Both affected pages were inspected live desktop880/actual320,
including reader cost and declared layout/grid limits, without page overflow.
The preview tab was re-resolved after the original tab became unavailable; the
GUI remains connected and the new retained tab shows21. No human acceptance.
Final figure-caption22 failed strict indentation; corrected23 is building and
must be inspected before any commit. All final scientific/artwork content remains
unchanged apart from clarifying that the regional schematic requests a track.

Next: one fresh independent full Task05 review of code/tests/docs/evidence, close
findings with covering checks and scoped re-review, freeze the complete handoff
and commit locally. No Task05 approval, completion or commit is claimed.

Full Task05 reviewer is now active on precommit tree
`aa12b4ebca5f64232b018f2febd0393569213de1`, package
`task-05-review.diff`. This includes all17 code/test/docs/evidence/state paths.
All implementation workers and the earlier native-slice reviewer are idle.
No fix or Task06 implementation starts before this independent verdict.

Final caption23 strict build/publication/13 unittests passed after22 failed.
Its rendered caption was inspected desktop880px and actual320px; no overflow,
all images loaded and the regional/non-track distinction is readable.
Input HTML23 exactly matches the already-inspected21. Canonical output23 is
retained in the live GUI. These final record-only updates remain unstaged while
the reviewed index checkpoint is preserved. No human acceptance is inferred.

### Task05 full-review fix round1

Full review returned spec issues / quality Needs fixes. The reviewer independently
reproduced two Important defects not covered by the774 passing checks:

1. Replacing an existing Zarr store can delete an inventoried source nested inside
   it. Same-file protection does not establish directory non-containment.
2. A cross-format execution-engine override can publish a Zarr directory under a
   planned NetCDF filename, disagreeing with effective configuration and status.

The lead owns focused corrections in `core/execution.py` and the central
`test_v3_execution.py`. The reviewed index remains
`aa12b4ebca5f64232b018f2febd0393569213de1`; the original full reviewer will check
only these closures and new fix-diff breakage. No Task05 commit or Task06 work
before closure.

Ruling: reject cross-format API engine overrides before source binding or run
ownership, with an error directing callers to `output.format`. Keep same-format
NetCDF engine selection available. Replanning an already-resolved configuration
would introduce unnecessary format/path mutation into this native milestone.
Cost if wrong: callers wanting another format must resolve a configuration with
that declared format instead of changing only `ExecutionOptions.engine`.

Source preservation must include inventoried paths, deduplicated aliases and
declared excluded paths, checking their parent-resolved directory entries as well
as their resolved physical targets. A leaf symlink inside a replaced store is
itself a source path even when its target is outside. Existing same-file/hard-link
protection remains required. Tests use only disposable generated stores/inputs.
Initial seven-case run was RED7: each completed instead of rejecting its unsafe
request. The first containment correction preserved nested/excluded files but
left leaf/deduplicated symlink cases RED2 (6 covering cases passed). Investigation
traced those two failures to `_paths` resolving explicit source symlinks before
inventory, erasing the very alias that directory replacement removes.
Necessary scope extension: `core/configuration.py` now preserves source
`files`/`exclude` aliases as absolute paths, leaving device/inode deduplication to
the existing inventory. The private `_path` keyword is renamed from the
interpreter-specific name to `preserve_symlink`; its FA helper caller keeps the
same behavior. No public YAML key, new dependency or scientific decision changes.

Additional bounded claim: `io/loader.py` resolves a NetCDF input's physical path
only when calling xarray. A new `symlink/../source.nc` control was RED because
lexical `abspath` collapsed its parent incorrectly; retaining that path then
exposed xarray's own lexical normalization. Using `Path.absolute` for declarations
and `Path.resolve` at the backend boundary preserves the original file meaning.
The resource key and inventory retain the declared path. A separate directory-
alias-inside-store control was RED and is protected by retaining the lexical
absolute location as well as parent-resolved and fully resolved locations.
These are source-identity corrections, not additional discovery or new formats.

The original seven regressions are GREEN. The expanded native suite passed22
before the directory-alias control; the final integrated run includes all23
central cases, seven source-containment variants, both conflicting formats and
two safe same-format/overwrite controls. Ordinary readers reopen the positive
NetCDF/h5netcdf and Zarr products without importing FrameIt; filenames, status,
effective format, scalar values/metadata and input bytes agree on both runs.
Latest integrated result:478 passed/2 subtests/41 warnings. The same delivered
selections pass233 binding/inventory,43 resource and31 numerical assembly cases.
XML assertions establish785 distinct passing targeted nodes without overlap,
failures/errors/skips. Required5 freshly pass with10 warnings (2.53s).

Strict Sphinx iteration24, publication boundary,13 publication unittests and4
plot/release tests plus2 subtests passed. The changed input/output paragraphs were
inspected live at desktop880px and actual320px, with no page overflow or missing
images. Canonical output24 and the owned preview remain available. No human
acceptance is inferred. A new E501 in the first Ruff comparison was wrapped;
the final15-file comparison is81baseline/81current with no new diagnostics.
The larger baseline includes newly claimed configuration/loader files.
Full-suite fix diagnostic completed:
468 failed,1534 passed,2 errors,4 subtests and4061 warnings in302.30 seconds.
All470 failure/error nodes match the preceding Task05 run and all three Task03
diagnostics exactly; this is not a passing full suite.

Original full reviewer is now checking findings1/2 and new fix-diff breakage
against `task-05-full-review-fix-1.diff`. The reviewed index remainsaa12b4e;
all fixes are unstaged. No implementation worker or test command is active.
Only read-only Task06 preparation may proceed before closure/Task05 commit.

Full-review fixround1 verdict: Important2 ADDRESSED, Important1 NOT ADDRESSED
completely; spec issues / quality Needs fixes. An outside input alias can resolve
through an intermediate link inside the replaced store to an outside physical
file. Replacement leaves the declared input dangling, despite unchanged physical
bytes. This is the same source-preservation finding, not a new scientific defect.
The lead owns fixround2 with real leaf/directory/excluded chain regressions.
The fix1 working-tree snapshot is tree
`9c98132bd5dc965b6cc87d8dbe1ac23571cbcb7a`, produced with a separate temporary
Git index; the real index remainsaa12b4e. Original format closure must be retained.
No Task05 commit or Task06 implementation has occurred.

Fixround2 observed RED3 for file/directory/excluded two-hop aliases, then GREEN26
central cases. `_input_path_locations` now follows required symlink targets and
parent-directory links with a visited-path set, preserving declared paths and
physical targets without another filesystem resolver. Only execution and the
central tests changed; Important2's early format guard is unchanged.
Fresh combined verification:481+233+43+31=788 distinct targeted passing nodes,
confirmed from XML without overlap/failures/errors/skips. All150 new Task05
cases are included. Ruff15files81baseline/81current/noNew. Strict25/publication/
13 unittests passed; both affected HTML files match desktop/320-reviewed24.
Canonical25 is retained. The full diagnostic completed:468 failed,1537 passed,
2 errors,4 subtests,4064 warnings in304.31 seconds. All470 failure/error node
IDs exactly match fix1, the preceding Task05 run and all three Task03 runs.
This is not full-suite green. The original reviewer must close the remaining
containment finding before any commit.

Deferred Minors from this full review:

- Binding warnings precede the retained run logger; recorded coordinate
  `unit_assumption` attributes remain intact. Task14 owns replay/deduplication of
  actual prepared warnings after logging opens, without moving safety binding
  after run ownership. Task19 must verify the retained-log assertion.
- The later polar filename heading still says `SIMU.polar.<group>.nc`. Task10's
  writer-contract documentation must use the source/product name and reconcile
  its explanation. Task20 must include this page in the full documentation pass.

The earlier intentional optional-entrypoint-warning Minor remains deferred to
Task19/whole-branch triage. None of these is an approval or a silently fixed item.

## Task 05 reviewed execution handoff

Full integration review and both scoped rounds are complete. Important1 is
ADDRESSED, Important2's closure is preserved, and no new fix-diff breakage or
additional out-of-scope finding remains. Spec PASS and task quality APPROVED
apply to this native/read-mechanism gate only. Three Minors remain explicitly
deferred above. No scientific, human-usability, general-resource or later-pipeline
approval is inferred.

The reviewer saw the last full diagnostic as pending. The lead subsequently
verified its completed output and exact470-node comparison above; the pending
review wording is not a waiver or a passing-suite claim. Fresh precommit required
command (the Task05 command in the checklist) passed5/10 warnings in2.57 seconds.
Final tested source is unchanged from the approved fixround2.

### Frozen consumers and selected reads

- `coupled.bind_sources(conf)` returns `(report, children, plans)` with the actual
  prepared children bound exactly once. Parent source/request snapshots are
  deliberately copied. Execute those same children; never rebuild unbound ones.
- `FrameitRunner(..., prepared_sources=None)` carries that handoff. Native source
  execution uses each selected source's own clock and native grids, without a
  reference source, centre, trajectory, implicit companion or diagnostic.
- Selected grouped-reader arguments are `selected_records=<complete executable
  binding>, source_plan=<owning inventoried source>`, not `binding.records`.
  Return shape remains `(user_groups, tracker_groups)` with native grid IDs and
  internal support under `tracker_groups["internal"][grid_id]`.
- Product descriptors govern exported positions/order. Internal dependency
  descriptors govern required support. Same-name output `[5,0]` and internal
  `[5,6,0,1]` stay distinct; never use their union as an export selector.
- NetCDF subsets original payload/coordinate indexers and list-valued vertical
  positions before Dask chunk construction. Original resources stay owned until
  execution/export finish; failures roll back. Auxiliary sample labels and bounds
  survive clock normalization. The physical path handed to xarray is resolved,
  while inventory/cache identity retains the declared path.
- GRIB uses the selected offset/length, existing native lock and one scoped
  decoder handle per message. Native units, level/member/cycle/interval evidence,
  zero and bitmap missingness remain distinct. It does not discover neighbours
  or decode an excluded message. A selected message is a whole horizontal field.
- FA's selected numerical leaf is `fa_selected_array(record, source_plan, *,
  options, diagnostics_path=None)`. Use each raw record's `native_descriptor`,
  never a merged field summary. Existing isolated decoding/scaling/fallback and
  freshness checks remain. Public interpretation/grouped execution stays genuinely
  pending for Task07; no artificial bound map is permitted.

### Native publication, safety and remaining owners

- Native `runner.field_products[(source, product)]` uses the existing writer and
  planned source/product paths. Explicit outputs that also serve as formula
  coordinates remain outputs; support-only fields are not extra exports.
- Binding and source/destination safety precede run ownership. Every inventoried,
  deduplicated-alias and excluded path is protected, including required symlink
  chains. Same-file/hard-link checks remain. Cross-format API engine overrides
  fail early; select `output.format` in the configuration instead.
- Native scalar values, units, zeroes/NaNs and independent source clocks were
  reopened outside FrameIt. This is checked numerical preservation, not blanket
  scientific validation or bitwise-output identity.
- Several varying NetCDF sample axes remain explicitly unsupported. Conflicting
  native-grid coordinates fail exact merging. These failures do not grant reader/
  multi-grid writer qualification; Task10 owns the complete writer contract.
- Task06 owns regions, actual tracker dependency binding, trajectories and centre
  association; Task07 owns source interpretation; Tasks08–09 own transformations/
  polar planners. Pending methods must remain blocked until their owning gates.
- Tasks11–14 retain resource/report/publication/progress integration; Tasks15–16
  retain public CLI/templates/producers; Task19 retains full green integration and
  native/scientific qualification. The unchanged470 full-suite failure/error nodes
  are retained by name, not suppressed or marked passed.

Verification:788 distinct targeted nodes, final required5, Ruff81→81/noNew,
strict25/publication/13 unittests, and reviewed desktop/actual320 HTML identical
to24. Exact commands, outputs and limits are in `task-05-checks.md`.
Docs: canonical input/output guides cover native behavior, costs, limitations,
source preservation and format selection. No installation/dependency change,
new scientific method or additional public configuration key belongs to Task05.
The local commit is the next operation; nothing will be pushed.

Task05 commit: `73c4147ba2bcb45672b56d8808a7ba2dbc86a934`. The working tree was
clean immediately after the local commit; nothing was pushed.

## Task 06 work in progress

Starting commit: `73c4147ba2bcb45672b56d8808a7ba2dbc86a934`, after Task05 review/
freeze/local commit. Existing linked worktree isolation was verified; no new
worktree, environment or package setup is needed.

One worker owns Task06's brief files and the necessary bounded preflight/runner/
execution/basic-writer/method-binding integration. Exact claims, interfaces,
test policy and limits are in the ignored `task-06-handoff.md`. Shared fixture
helpers, configuration/settings, adapters and public docs remain unclaimed by
that worker unless a necessary caller-wide extension is recorded first.
Lead owns canonical moving-region/prescribed-track/time/coupled/pressure-wind
guidance, STATE/checklist, integration review and the eventual local commit.
No second implementation worker overlaps these claims.

The exact pre-implementation mixed-suite inventory contains78 passing and80
failed/error nodes across the seven required files, extracted read-only from the
completed Task05 fix1 full XML. Each future-dependency classification must be
verified against retained failure evidence. Plan lines803–806 permit recording
applicable numerical nodes while the public producers remain Tasks15–16/19;
no failed check is a pass and no delivered numerical behavior may regress.

Task06 must preserve the reviewed Task05 selection and source-path protections.
Resolve genuine tracker dependencies/centre associations; never clear an unrelated
pending method or invent executable binding. Scientific defaults and C5 trajectory
rules are already approved in the plan, not an invitation to add new methods.
Task05 Minors retain their later owners. No Task06 test or implementation result
has yet been reported.

The bounded implementer is active; the lead is updating public guidance in
parallel. Prescribed NetCDF trajectories must also enter source/destination
protection before ownership. A necessary trajectory-alias normalization change
would require a recorded narrow configuration-file claim first. No other worker
owns overlapping production files.

Lead documentation draft covers moving/fixed/coupled task pages, prescribed/
fixed/pressure-wind method pages, the time-support concept and the directly
affected FA/ocean centre-association sections. It uses C5's centre provider,
full-width, exact/common/preceding-hour and strict trajectory rules; unconverted
starter generation is not presented as a verified v3 regional workflow.
The fixed instructional example now uses complete v3 YAML and a direct Python
API call; its runtime and ordinary-reader assertions still require reconciliation
with the worker's final code before any runnable-example claim or commit.

All10 edited YAML blocks resolved metadata-free (context-completed where clearly
labelled fragments); defaults assert exact association and pressure-wind200/100km.
No source discovery/availability, numerical execution or scientific approval is
inferred. The first ad-hoc extractor incorrectly included a tip's following prose;
its indentation handling was corrected without changing a YAML example.
Strict iteration26 failed one fixed-box list-indent warning. That indentation is
corrected; iteration27 strict/publication/13unittests/plot-release checks are
running. Live desktop/320 inspection is still required after a successful build.
The retained preview remains25 until that success. No worker report is pending
to be read; await its automatic completion rather than polling.

Iteration27 strict build/publication/13 unittests and4 plot/release tests plus2
subtests passed (15 existing backend warnings). All9 changed pages were inspected
live at desktop880px and actual320px, including the fixed API/ordinary-reader
section. No page overflow or missing images; code blocks retain their own
horizontal scrolling. Canonical fixed27 is retained for feedback. No artwork or
site style changed, and no human acceptance is inferred.
Before final Task06 documentation closure, execute the fixed example against the
reported final code and reconcile exact stored clocks/association metadata and
method limitations. Preserve the old moving-page `check-and-run` anchor when
finalizing its renamed result section. Whole-page producer/template conversion
outside the directly changed C5 text remains Task16; these checks are not full
documentation acceptance.

### Task06 bounded blocker decisions

The implementer returned NEEDS_CONTEXT, not a completed task. Its latest focused
snapshot is50 passed/2 failed; the unfiltered full snapshot is1566 passed/477
failed/2 errors and predates two later inventory fixes. All470 Task05 failed/error
IDs remain. The latest deduplicated observations retain7 additional unresolved
IDs: trajectory-alias safety, AROME multifield assembly and5 unitless fixtures.
These are not exempted as producer failures, and no independent Task06 review has
started. Full evidence and all node names remain in this plan's ignored report.

Ruling: preserve the authored `region.track.file` alias using configuration's
existing `_path(..., preserve_symlink=True)` option. This narrowly extends the
original worker claim; the existing pre-ownership input-location collector must
protect declarations, required intermediate symlinks and physical targets.
Reason: trajectories are read-only scientific inputs under C5. Cost if wrong:
a replaced store could still destroy a required alias despite retaining its data.

Ruling: extend that worker's claim to selected NetCDF/GRIB internal assembly and
their two reader tests. Align only already selected internal vertical stencils
with checked coordinate/native-index consistency and exact nonvertical alignment.
Public product assembly stays exact; records and scientific payload reads must
not widen. Structural missing entries cannot become data, zeroes or exports.
Reason: the existing AROME multifield method requires u/v850/700/500hPa but
z850/700hPa. Cost if wrong: alignment could hide incompatible source evidence;
actual backend instrumentation and incompatible-coordinate negatives are required.
The provisional method gate may be removed only after those checks pass.

Ruling: add explicit degrees_north/degrees_east only to the synthetic trajectory
writes in the requested FA-mapping and polar-wind tests. Keep their numerical
assertions and all missing-unit rejection tests unchanged; shared fixture APIs
remain unclaimed. Reason: C5 intentionally rejects unitless trajectories. Cost if
wrong: the fixture could misrepresent its known synthetic geographic values.

The original implementer resumes these bounded corrections and fresh focused,
covering, required and full diagnostics. The lead retains public docs/state,
runtime-example verification and review-before-commit ownership. These technical
rulings neither change scientific methods/defaults nor supply scientific approval.

The lead executed the fixed-region page's exact YAML and Python blocks in a fresh
instructional directory using `frameit_env` Python3.13.18. The run wrote one
model-grid product; a separate ordinary-reader process imported no FrameIt,
verified exact2×5×5 values, units, the physical zero and missing values, and
confirmed native `time` and equal exact-association `center_time`. Source bytes
were unchanged. This precedes the worker's remaining corrections, so the same
check must be repeated against the final reviewed code before commit.
The old moving-page `check-and-run` anchor is restored. Canonical time guidance
now names the separate stored coordinates explicitly; these small docs changes
need a fresh strict build/publication/live inspection before commit.

Documentation iteration29's strict build, publication check and13 publication
unittests passed with the worktree's explicit `PYTHONPATH`. The separately
corrected pytest command passed4 plot/release tests plus2 subtests (15 existing
backend warnings). Attempt28 omitted that path for unittests and imported the
main checkout's older schema, proven by read-only import-path controls; its
failure is retained. Attempt29 initially used unittest discovery for pytest-only
plot tests (0 tests/exit5); it was corrected without source changes and is not
counted as a successful test run. No environment or package change was made.
The time-coordinate/basis prose and restored moving-page anchor were inspected
live at880px/actual320px. No overflow or missing images; the6 other affected
pages exactly match previously reviewed iteration27 HTML. Canonical fixed29
remains live for feedback. Agent inspection is not human acceptance.

User direction: use `atmosphere`, not illustrative aliases such as `weather`, in
public atmospheric source examples. The lead applied this to all5 matching
public pages, including the fixed-run output path. This is documentation naming,
not a schema restriction or a change to physical-type discovery. Internal
renamed-source acceptance tests remain necessary under C5. The extra input-files
and field-selection pages join Task06's documentation verification/review scope.
Fresh example, schema, strict/publication and live preview checks follow.
The matching coupled example and output-file example also use `ocean` instead
of the analogous illustrative `water` name.
The downloadable all-keys reference uses `atmosphere` too, including its product
field maps; its documentation test checks the same name. Field placeholders
remain unchanged. No parser, runtime default or scientific behavior changed.

Fresh naming checks: no `weather` remains in published sources;5 complete YAML
examples resolve without metadata reads. The verbatim fixed example writes the
atmosphere-qualified product; its separate ordinary reader again checks exact
2×5×5 values, zero, NaN, units and unchanged input bytes. Strict iterations30/31,
publication checks,13 documentation unittests and4 plot/release tests plus2
subtests passed (15 existing backend warnings). The current coupled
atmosphere/ocean mapping also resolves.
All renamed pages and the all-keys/output additions were inspected live at880px
and actual320px;4 unchanged iteration31 pages exactly equal reviewed30 HTML.
No overflow or missing images; the reference code can scroll to its right edge.
Canonical fixed31 remains available. These naming changes join Task06's
independent review/local commit; they do not change its unresolved code status.

### Task06 ready for independent review

The original implementer returned DONE_WITH_CONCERNS after all3 bounded fixes.
Fresh full diagnostic:1594 passed,468 failed,2 errors,4 passing subtests,
4368 warnings in319.94s. Its470 failed/error node IDs exactly equal Task05's
baseline: zero new and zero removed. All57 new Task06 nodes and all5 corrected
unit fixtures pass; all9 earlier new failures pass in this full run.
Covering873passed/46failed/1error; focused158passed; exact required7files
79passed/80failed. Each required failure retains individual schema/input evidence;
these are not passing suites or scientific clearance.

Lead rechecked raw XML counts/set equality and every required failure's
baseline/current message. The final-code verbatim fixed example again passes
in a separate ordinary reader with unchanged source bytes. A fresh lead158-node
focused run passed in28.22s with310 warnings, including6 fixture time/bounds
encoding warnings and1 concat-default FutureWarning. No warnings were suppressed.
Code Ruff18files59baseline/59current, no new diagnostics;
full-repository clean lint is not claimed. Existing native-size/deprecation
warnings remain, without environment repair or suppression.

Provisional internal handoff: `merge_internal_stencils` aligns only already
selected internal vertical coordinates, preserves their native-index mapping,
checks overlaps/attributes/calendars, and keeps other coordinates exact.
Structural NaNs never enter products. Both selected readers use it only for
dependencies; native export assembly stays exact. Actual NetCDF and ecCodes
requests prove no widened scientific reads. `_region` retains authored trajectory
aliases for the existing pre-ownership protection. These are not independently
frozen yet. Shared selectors keep their original iterable behavior; mapping-valued
required_inputs supports method-specific internal selectors.

No new correctness/scope concern remains in the implementer's final report;
baseline failures, later-task limits and independent review remain open.
Full code/test/docs/evidence review follows before any local Task06 commit.
All implementation workers are idle; the original Task06 implementer retains
any subsequent fix ownership. Task07 is only prepared, not dispatched.

Independent Task06 review is active on the complete34-file precommit snapshot
`fd69529085a8f87ccda6dbe5b39cf7dcc46f8dee`, including the new tests, portable
evidence and lead-owned documentation/naming changes. A temporary index built
this review tree; the real index remains empty and HEAD remains73c4147.
Both spec and quality verdicts are required. Original implementer is idle and
retains fix ownership. No code changes, Task07 dispatch, freeze or commit precedes
review closure.

### Task06 independent review: four blocking findings

Spec compliance: issues found. Task quality: needs fixes. Four Important findings
were demonstrated by small reviewer probes and checked against the implicated
paths by the lead:

1. `_region_grid` derives native x/y from latitude's stored dimension order;
   transposed geography can silently select the wrong unequal-width rectangle.
2. Geometry inspection normalizes explicit radians, but containment/lookup uses
   raw coordinate numbers against degree-valued centres.
3. The new preceding-hour path omits the established NetCDF-only format guard,
   incidentally admitting an unqualified GRIB atmosphere.
4. Regional inventory construction scans file×selected-time×records, giving
   cubic work for ordinary one-time-per-file inputs.

The original implementer owns fix round1/5, preserving source semantics,
native output, selected reads and the existing scientific admission boundaries.
RED/GREEN and covering/full evidence must precede the original reviewer's scoped
closure. No Task06 freeze/commit or Task07 dispatch occurs first.
Minor M1 (new fixture time/bounds encoding and concat-default warnings) is
deferred explicitly to Task19/final warning triage; no global suppression or
environment repair is authorized. Review artifacts and machine-local probes
remain in the ignored plan workspace; no scientific sign-off is implied.

The original implementer returned fix1 ready for closure. Only coupled.py and
test_v3_regions.py change in production/tests beyond the reviewed tree. New
tests reproduce and cover all4 findings;7 new nodes pass. Fresh full1601passed/
468failed/2errors/4subtests/4405warnings in302.18s retains the exact470-node
failed/error set against both earlier references, with all old node states
preserved. Covering880pass/48fail/1error, required79pass/80fail, focused52pass.
Lead raw-XML assertions independently corroborate all counts/set comparisons
and each required failure's baseline/current schema evidence.

Original reviewer resumed on the652-line scoped package fromfd695290 to
temporary-index treea098755b6286f1027cd54859ddca9140a7328093. The real index
is empty. No fix is independently closed yet and no additional code change
precedes that verdict.

Final-code verbatim fixed example04 and strict documentation iteration32,
publication,13unit and4plot/release tests plus2subtests pass. All13 affected
HTML pages equal desktop/actual320-reviewed31 bytes; canonical fixed32 is live.
No artwork/style changed and no human acceptance is inferred. Code Ruff18files
59→59 plus lead documentation test5→5 gives19files64→64/no new diagnostics;
full-project clean lint is not claimed. M1 remains assigned to Task19/final
warning triage. No new scientific assumption/default or format admission is
approved by these bug fixes.

## Task 06 reviewed regional handoff

Independent spec and quality gates are approved after fix round1/5: I1–I4
addressed, no new Critical/Important/Minor breakage. M1 remains explicitly
deferred to Task19/final warning triage. No scientific/human approval is inferred.

### Frozen interfaces and semantics

- Bind actual prepared children once, then execute them. Selected readers keep
  the complete executable binding and owning source plan; never pass a bare
  record list or merge exported and internal stencils.
- `resolve_tracker_support(conf, source)` resolves actual selected method inputs,
  units, native/pressure support and wind basis before ordinary binding.
  `tracker_support` records method, input selectors, selected-time count and
  pending value checks. It cannot clear unrelated operation gates.
- `bind_requests(required_inputs=...)` retains iterable/shared-selector behavior;
  mapping-valued method inputs carry individual internal vertical selectors.
  Existing closed-pool/provider/time/cycle checks remain binding authority.
- `make_tracking_dataset(..., selected_times=...)` uses the explicit operation
  clock without outer-time gap filling. Omitted keyword retains direct-call behavior.
- `merge_internal_stencils(datasets, vertical_dims)` aligns already selected
  internal vertical coordinates only. Overlapping labels/attributes/calendars/
  native indices must agree; nonvertical coordinates stay exact. Structural NaNs
  are not observations and cannot enter separately assembled native products.
- Region omission preserves independent full domains. Centres map separately to
  each required native grid. Adapter/axis evidence, not geographical storage
  order, establishes directions. A metadata-only internal geometry view normalizes
  explicit units; native product geography keeps its stored numbers/units.
- Region `associations` pair `source_time` and `coupling_time`. Grid facts retain
  geometry, requested/realised positions/extents, indices, coverage and pending/
  checked centres. Crops keep native `time` and separate `center_time(time)`.
- Exact covers every selected source sample without requiring equal clocks.
  Common/permitted incomplete-prefix exclusions affect centre-dependent work,
  not unrelated full-domain exports. Preceding-hour remains AROME/NEMO
  **NetCDF-only**, with established interval, sampling and cycle rules.
- Native crops preserve orientation, values, zeroes and missingness. Partial
  coverage pads missing; outside-footprint centres fail. Records group once by
  path for inventories/temporal metadata; local sorting remains. Operation counts
  were measured, not archive wall-time speedups.
- Requested tracks are chronological `time/latitude/longitude` NetCDF with explicit
  time/calendar and geographic metadata, also beside Zarr fields. Input discovery
  requires unambiguous shared trajectory dimensions, explicit compatible units,
  unique times and finite positions. Missing units intentionally fail. Authored
  paths, required aliases and physical targets are protected before ownership.

### Verification and later owners

Fresh lead precommit command:
`FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_regions.py --tb=short`
passed52 in22.38s with342 disclosed warnings. Final full:1601passed/468failed/
2errors; all2071 nodes preserve previous statuses, with64 new Task06 passes
and the exact unchanged470 failed/error IDs. Required79pass/80fail and covering
880pass/48fail/1error remain failed suites, with individual evidence rather than
blanket exemptions. Exact broader commands are in task-06-checks.md. Ruff19
changed Python files64baseline/64current/zeroNew; no whole-repo clean claim.

The final-code fixed page runs verbatim; a separate ordinary reader checks exact
2×5×5 values, zero, NaN, units, clocks and unchanged input bytes. Strict Sphinx32/
publication/13unittests/4plot-release tests plus2subtests passed. All13 affected
HTML pages equal desktop/actual320-reviewed31 bytes; the live32 preview remains
available. Agent inspection is not human acceptance. Public examples/reference
use atmosphere/ocean as requested; this is not a schema name restriction.

Remaining reviewer boundaries have explicit owners, not claimed successes:
old producer workflows Tasks15–16/19; empty-input fixed/supplied track-only and
complete polar/coordinate/writer qualification Tasks09–10; human review Task21.
Task07 may resolve source interpretation through real binding but must not clear
unresolved transforms/derived/polar/tracker work. Preserve source-local FA
native_descriptor and the selected leaf locator contract. Unsupported UTrack/
wind preparation stays unadvertised. No new equation, threshold, default,
approximation or stable-method promotion was introduced; broader scientific
validity remains unresolved.

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
