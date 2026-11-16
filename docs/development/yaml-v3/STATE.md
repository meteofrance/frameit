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
| 06 | done | Task06 worker + lead + independent reviewer | 05 | `edaf602`; four Important findings closed,64 new nodes pass; reviewed handoff below. |
| 07 | done | Task07 worker + lead + independent reviewer | 05 | `bc2a470`; three Important findings closed;54 new nodes pass; reviewed handoff below. |
| 08 | done | Task08 worker + lead + independent reviewer | 07 | `db6258e`; review approved after two fix rounds; frozen handoff below. |
| 09 | done | Task09 worker + lead + independent reviewer | 06, 08 | `393e7d9`; approved I1/I2 closure; frozen handoff below. Minor3 retained19. |
| 10 | done | Task10 worker + lead + independent reviewer | 09 | `2a77b1d`; C7 approved after I1–I3/N1 closures; frozen handoff below. |
| 11 | done | Task11 worker + lead + independent reviewer | 10 | `c7d1c65`; C8 independently approved after origin fix; frozen handoff below. |
| 12 | done | Task12 worker + lead + independent reviewer | 10,11 | `69e6992`; records/checkpoints approved after I1; frozen handoff below. |
| 13 | done | Task13 worker + lead + independent reviewer | 11, 12 | `106812d`; shared reports/diagnostics approved after two fix rounds; frozen handoff below. |
| 14 | done | Task14 worker + lead + independent reviewer | 13 | `bde826b`; owning plan/progress approved, A1 corrected; frozen handoff below. |
| 15 | done | Task15 worker + lead + independent reviewer | 14 | `40f9bcd`; C9 surface approved after fix1, frozen handoff below. |
| 16 | active | Task16 worker + lead docs | 15 | Direct-v3 producers, callers/checker/benchmark and canonical examples. |
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

## Task 07 work in progress

Base: `edaf6028a581f9031e88047da4239d583e55ca6e`; working tree was clean after
the reviewed Task06 local commit. No push. One fresh Task07 worker owns the
brief's SEA/FA modules and narrowly necessary selected-reader/configuration/
preflight/request integration. Exact bounded claims, safeguards and acceptance
commands are in the plan workspace's task-07-handoff.md. No shared fixture
helper change or second overlapping implementation worker is authorized.

The lead owns public source-interpretation/FA guidance, STATE/checklist and
staging/commits. Existing mathematical/producer/scaling/spectral boundaries
remain; genuine scientific ambiguity fails or is escalated, not guessed.
Metadata declarations do not request numeric transformations. Task06's actual
bindings, source clocks, native geometry/units and protected inputs remain frozen.
Public examples use atmosphere/ocean/surface naming as directed by the user.

The prior five-file inventory contains89 nodes/41pass/48fail, not a Task07 run
or scientific validation. Each later-producer classification requires actual
individual evidence. Compare new full diagnostics with Task06's final2071-node
snapshot:1601pass/468fail/2errors,470 failed/error IDs. No Task07 implementation
or verification result is claimed at this starting point.

Task07's sole implementer is active on those bounded claims. One concrete
integration safeguard was sent: when admitting public projected FA regional
execution, retain the source's established native-CRS lookup/zone/geometry
evidence through reconstructed regional metadata; never fall back silently to
degree-space lookup. This is preservation, not broader projection admission.

Lead documentation draft covers8 directly affected pages: FA input setup,
descriptors, native cubes, environment, geometry and compatibility; SEA
interpretation in the ocean guide; and the canonical declaration explanation.
It teaches source-local profile/native_cubes/field_metadata/fa/reader, explicit
SEA opt-in without a repeated selector, native component copying and operation
separation. Complete illustrative requests use atmosphere/surface names.
No template/CLI producer conversion or new scientific catalogue is claimed.
Schema/build/GUI checks and reconciliation with the worker's eventual report
remain pending; draft prose is not execution or scientific qualification.

Lead schema-only checks pass for3 complete FA/cube/SEA requests and1 explicitly
contextual interpreter fragment; FA point/timeout defaults match current code.
No data availability, payload execution or scientific validation follows.
Strict33 failed3 list-table indentation defects, corrected in34. Strict34/
publication/13unit/4plot-release tests plus2subtests passed; desktop/actual320
inspection exposed unreadably narrow three-column support text. The same
limits now use full-width definition entries, retaining the existing section
anchor and scientific restrictions without theme/artwork/CSS changes.

Draft35 strict/publication/13unit/4plot-release+2subtests pass (15 existing
backend warnings). All8 changed pages were inspected at880px/actual320px;
5 unchanged35 pages equal reviewed34 HTML. No overflow or missing images;
support entries are readable and YAML scrolls to its right edge. Canonical
FA-inputs35 remains live. Runtime examples, provenance/eligibility reconciliation
and independent review still await the original worker's report; no Task07
execution result or scientific approval is claimed.

The original Task07 implementer returned NEEDS_CONTEXT:118 focused passes,
required41pass/48fail, full1627pass/469fail/2errors. All470 prior failed/error
statuses remain; one old passing assertion now fails because it requires blanket
interpretation rejection even when the pressure-wind fixture selects no eligible
SEA quantity. The lead traced the fixture and actual resolver/binder and reproduced
that one failed assertion.

Ruling: authorize only that test's interpretation branch with meaningful positive
binding/empty-SEA/exact-selection/tracker-input/no-FRAC_SEA/no-output checks.
C4 applies SEA rules to selected eligible fields, not every unrelated input.
Risk if wrong: false no-work clearance; independent review must assess the ruling
and replacement assertions. Keep transform/derived/polar rejection cases and
shared fixture unchanged. No production change, scientific admission or weakened
eligible-field check is authorized. Original worker resumes with fresh covering,
required, full-node and Ruff evidence; no Task07 review or commit yet.

Lead reconciled the source guides with actual selected-route provenance and
original native FA index semantics. Three complete YAML requests execute unchanged
against generated compact inputs: coupled GRIB/FA2products, FA native cube1product,
SEA1product. Separate ordinary-reader processes without FrameIt check literal
values, units, masks, zeroes/NaNs, native indices/records/clocks, hybrid coefficients
and source decoder/interpretation provenance. All6 source files remain unchanged.
No runtime overrides, scientific substitutions or shared-fixture edits were used.
Six native FACADI warnings stay visible; this is not real-producer qualification.

Strict iteration36/publication/13documentation unittests/4plot-release tests plus
2subtests pass with15 disclosed backend warnings. Both reconciled pages were
inspected live at880/actual320;6 other pages exactly match reviewed35 HTML.
The same loopback preview remains available; machine-local ownership stays in
the ignored handover. No human acceptance, scientific validity, or Task07
independent review is inferred. Original worker alone refreshes code evidence.

Task07 resumed delivery is ready for independent review. The17-line positive
interpretation branch tests actual binding in child/parent/plan, empty SEA work,
exact scalar exports and tracker inputs/internal records, and no output ownership.
The other three rejection branches and shared helper are unchanged. All10
production files are unchanged during this bounded resume.

Fresh lead four-branch check:4passed/37warnings in0.72s. Lead raw-XML assertions
corroborate focused181pass; covering812pass/38fail; required41pass/48fail;
full1628pass/468fail/2errors. All2071 Task06 statuses and exact470 failed/error
IDs are preserved, with27 new Task07 passes. Each of48 required failures retains
individual baseline/current producer evidence. These remain failed suites,
not exemptions or scientific sign-off. Ruff15changed/new Python files26baseline/
26current/zeroNew; no whole-repo claim.
The original worker is idle. Independent review of the complete code/test/docs
delivery, including the lead's bounded assertion ruling, precedes any Task07
freeze/commit or Task08 dispatch.

Independent Task07 review is active on complete25-file precommit snapshot
`61352b1bd07f99afd778f513eb05cb045e269011`, including new tests, portable
evidence, public guides and the bounded assertion ruling. Both spec and quality
verdicts are required. A temporary index produced the review tree; the real index
is empty and HEAD remains edaf602. No additional code change, Task07 freeze/
commit or Task08 dispatch precedes review closure.

### Task07 independent review: three blocking metadata findings

Spec: issues found. Quality: needs fixes. Reviewer compact probes demonstrated:
an admitted CF clock `t` can bypass temporal-statistic conflict detection;
case folding accepts different MW/mW units while rejecting known SEA aliases;
and raw unit spelling changes field identity before equivalent successive SEA
snapshots can be interpreted. The lead checked the implicated resolver/caller,
clock admission, raw identity and existing snapshot-equivalence regression.
All three enter original-implementer fix round1/5 with focused v3 RED/GREEN,
covering/required/full-node and Ruff evidence.

The bounded no-SEA-work assertion ruling was independently accepted. Warning
Minor4 stays assigned to Task19/final native-warning qualification, with no
package repair or suppression authorized. Public guides retain the intended
conflict/alias behavior; do not weaken them to hide the failures. Each actual
snapshot's metadata/origin must remain inspectable, and generic duplicate-name/
provider/grid/support/statistical safety must not be broadened by the fix.
No Task07 freeze/commit or Task08 implementation before independent closure.

Original implementer returned fix round1 ready for scoped review: four production
files plus the owned interpretation test, with27 new regression nodes. Actual
temporal names/dimensions drive statistic checks; unit comparisons use explicit
same-value aliases; SEA-only identity hashing admits equivalent units while
retaining actual per-record metadata/origins. Global units.py, FA production,
shared producers and previously reviewed tests stay unchanged.

Fresh lead27-case check passes with196 warnings in4.19s. Lead raw-XML assertions
corroborate focused208pass; covering839pass/38fail; required41pass/48fail;
full1655pass/468fail/2errors. All2071 Task06 and2098 reviewed Task07 IDs/statuses
are preserved;54 cumulative additions and27 fix nodes pass. Failed/error IDs
remain exactly470; each48 required failure retains evidence against both
references. Independent finding closure is pending.

Source provenance now retains per-record observed metadata/resolved units/origins
under interpretation.metadata_records; combined variable attributes represent
the first selected record. The lead added that distinction and unit-case guidance
to canonical pages. A final-code rerun of all3 documented examples plus strict37
and documentation checks is active, not yet a reported pass. Minor4 keeps its
later warning/native-qualification owner.

Scoped re-review of findings1–3 and new fix breakage is active on temporary-index
tree `f0706110e312cf4ef82b929d6c6da0b7a27589cc` against reviewed61352b1.
Real index remains empty. Final-code3example rerun passes unchanged, including
all21 SEA metadata records and6 unchanged source hashes. Strict37/publication/
13unit/4plot-release+2subtests pass with15backend warnings;6FACADI native
warnings remain visible. Both changed paragraphs were inspected live at880/
actual320;6 other pages equal reviewed36HTML. The canonical preview is retained.
No additional code change, Task07 freeze/commit or Task08 implementation
precedes the original reviewer's closure verdict.

## Task07 reviewed interpretation handoff

Independent spec and quality gates are approved after fix round1/5: all three
Important findings addressed, no new findings. The no-SEA-work assertion ruling
is independently accepted. Minor4 remains explicitly assigned to Task19/final
native-warning qualification. No human scientific or usability approval.

### Frozen metadata and selected-reader contracts

- Existing source-local schema and `_fa_runtime_options` remain the public
  declaration/reader projection. No new configuration key, format, dependency,
  method/default or stable-diagnostic promotion was introduced.
- `resolve_field_metadata(attributes, declaration, context, *, temporal_names=...)`
  fills genuine stored-value metadata gaps and records input/declaration origins.
  Actual admitted time coordinates/dimensions establish temporal statistics;
  qualifiers do not become extra statistics. Known quantity, temporal, categorical
  and unit contradictions fail without numerical conversion.
- Unit identity admits explicit same-value spellings only, including existing
  narrow SEA aliases. Unknown symbols retain case; MW/mW and different scales
  cannot become equal by normalization. Global unit conversion is unchanged.
- `source_field_metadata(source, field, *, record=None)` uses the actual record's
  observed metadata when available. Bound descriptors carry representative
  `field_metadata: {attributes, origins}`. Selected records may carry their own
  resolved field_metadata; do not replace these with another snapshot's labels.
- NetCDF records retain `temporal_names`. Eligible opted-in SEA records retain
  raw `observed_attributes`. Only their evidenced equivalent units normalize for
  field-identity hashing; all other identity/grid/provider/support/statistical
  conflicts and the generic distinct-name policy remain.
- Selected source interpretation records method, fields and pending value checks.
  For SEA, `metadata_records` additionally retain each field/time/cycle/provider's
  basename, clock, observed attributes, resolved units and origins. Source
  provenance exposes these under `sources.<id>.interpretation.metadata_records`;
  combined attributes represent the first selected record, not all observations.
- SEA interpretation remains explicit and limited to selected eligible fields
  and matching FRAC_SEA support within the closed time/cycle/provider inventory.
  Preflight reads no mask values. Execution validates finite physical support
  within[0,1], masks only known999/unsupported values, preserves zero/fraction,
  and applies no extra fraction weighting or inferred timing/sign/basis.
  Opt-out stays native; no eligible selection requires no SEA support.
- Selected NetCDF/GRIB outputs receive resolved metadata without replacing
  original header/evidence checks. Main/support SEA fields use their own selected
  record metadata; exported/ancillary/internal fraction roles agree.
- FA binding uses the reviewed selected leaf's actual metadata construction,
  not fake executable clearance. Grouped FA reads receive the complete binding
  and owning plan, retain separate native/internal stencils and native
  indices/record IDs/full hybrid coefficients. Source-local raw descriptors,
  producer/profile/geometry/encoding/isolation/resource/mask/scaling gates stay.
  Projected regional metadata retains native CRS/axes/zone lookup facts.
- FA descriptors distinguish explicit source origins and representative scope;
  source provenance/decoder logs retain actual per-file/sample observations.
  Native copying of one component requests no companion/basis/rotation.
  Missing hybrid evidence stays pending; decoder scaling/masks require execution.
- Actual prepared children remain bound once. Interpretation resolves only its
  own proven work. Tracker inputs still require actual method evidence; transforms,
  derived and polar gates cannot be cleared merely by available fields.

### Verification, compatibility and later owners

Fresh lead precommit:
`FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" PYTHONPATH="$PWD/src" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_interpretation.py --tb=short`
passed53 in31.42s with286 disclosed warnings. Separate lead27-case fix check,
raw-XML assertions and independent reviewer evidence confirm all54 added Task07
nodes pass. Final full1655pass/468fail/2errors/2125distinctnodes preserves every
Task06/reviewed-Task07 node/status and exact470 failed/error IDs. Required41pass/
48fail and covering839pass/38fail remain failed suites with individual evidence;
no original assertion hidden behind an old producer is claimed as passed.
Ruff15deliveryfiles26baseline/26current/noNew;5fixfiles20/20/noNew.

All3 documented requests run unchanged against final code with compact generated
inputs. Separate ordinary readers check literal values, clocks, zero/NaN/masks,
units/origins, native FA axes/coefficients/CRS, decoder facts and21 SEA metadata
records. All6 source files remain unchanged. Strict37/publication/13unittests/
4plot-release tests plus2subtests passed. All8 pages have retained desktop/
actual320 inspection; unchanged pages were compared byte-for-byte. No artwork/
theme/CSS change. Preview remains live; agent inspection is not human acceptance.

Scientific impact is the existing explicit stored-value interpretation and
contradiction policy, not new equations or numerical conversions. Metadata/
provenance additions are additive; existing checked native values/units/masks/
indices and source-name parsing remain. Examples use atmosphere/ocean/surface.

Unverified gates retain named owners: old required producers/assertions Tasks16/
19; transform/derived Task08; polar Task09; full coordinate/multigrid writer Task10;
resource measurements Task11; broad native/real-producer and warning qualification
Task19; human scientific/usability Task21. FACADI/binary-size/backend/fixture
warnings remain visible. These limits are not waived by successful generated
fixtures, the metadata review or the baseline-status comparison.

## Task08 work in progress

Base: `bc2a470c53b313edca58effe65e5ea655e0b9ab9`, the reviewed local Task07
commit. The working tree was clean after commit; nothing pushed. One fresh
Task08 implementer owns the brief's request/wind/extraction files and bounded
preflight/coupled/runner/selected-reader integrations. Exact claims, C3/C4
boundaries and verification are in task-08-handoff.md in the plan workspace.
All prior implementers/reviewers are idle; no overlapping code worker.

Ruling: newly executable transform/derived pending-operation assertions may
change only with actual C4 method binding and meaningful result/selection/
metadata checks. A blanket pre-implementation rejection is not permanent policy.
Risk is false clearance; preserve invalid-unit/missing-support/unresolved-polar
negatives and require independent review. Shared fixture helpers remain
lead-owned; no whole-producer conversion is authorized.

Lead owns canonical operation/method guidance, public examples, STATE/checklist
and commits. Existing public methods/keys/defaults remain fixed. Task08 does not
promote radial/tangential helpers to new public diagnostics or claim Task09
polar/Task10 writer completion. Preserve native exports, selected clocks, actual
record metadata/origins, separate internal support and all Task06–07 safety gates.
Public atmospheric examples use atmosphere.

The committed six-file prior inventory has196nodes/161pass/35fail. It is not
a Task08 run or a producer exemption. Compare eventual full evidence with
Task07's final2125nodes:1655pass/468fail/2errors and470failed/error IDs.
No Task08 implementation or verification result is claimed at this start.

Task08's fresh sole code implementer is active on its bounded claim. The lead's
seven-page documentation draft replaces old wind-output flags with explicit
source transforms/derived examples and removes automatic radial/tangential
claims, preserving equations, method limits, figures and anchors. Two complete
requests and three explicitly contextual fragments resolve schema-only, including
speed-only exports with UM10/VM10 internal inputs. No runtime support is inferred.
Strict38 failed two list indentation errors; corrected39 checks are active.
Final code/example reconciliation, strict/publication/live checks and independent
Task08 review remain required. No Task08 implementation result is claimed.

Draft39/40 strict/publication/13documentation unittests/4plot-release tests
plus2subtests pass with15backend warnings. All7 affected pages inspected live
at880/actual320; no page overflow/missing images, unchanged diagram display bounds,
alt text and full-size targets retained. The old pair-heading anchor is preserved.
Both complete requests and YAML right edges additionally inspected in40;
6 other40pages exactly equal reviewed39HTML. Preview remains live for feedback.
These are draft documentation/schema checks only. The sole worker received the
draft choices for final operation/provenance reconciliation. Actual example
execution, code verification and independent Task08 review remain pending.

Task08 original implementer returned ready for review: focused46pass; covering
914pass/68fail; required161pass/35fail; full1699pass/468fail/2errors. Lead fresh
46-case check passes with441 warnings in23.02s. Raw-XML assertions confirm all2125
prior statuses and exact470 failed/error IDs remain, with44 new passes/no removed
nodes. Each35 required failure retains individual producer evidence. These are
still failed suites. Ruff17changed Python files22baseline/21current/noNew.

Lead executed both complete guide requests unchanged and the transform fragment
in its stated context. Ordinary readers without FrameIt verify literal native
samples, known quarter-turn/3-4-5 vectors, W mass values, masks/zeroes/NaNs,
units/basis/axes/shared indices, optional fields and actual operation provenance.
All3 source hashes remain unchanged. One first-harness assumption about a native
NetCDF index coordinate was corrected to the actual label/resolved-selector
contract; no production or scientific expected value changed.
Guides now state the geometric-W requirement, native-unit consistency and result
metadata meaning. Final strict41/GUI inspection and independent Task08 review
remain required before freeze/commit; original implementer is idle.

Independent Task08 review is active on the complete26-file precommit snapshot
`ca60f6a02b74fbd809ae4417677a482abe30504c`, including new operation tests,
all6 bounded test adaptations, portable evidence and public guides. Both spec
and quality verdicts are required. Temporary index only; real index empty and
HEAD remains bc2a470. Strict41/publication/13unit/4plot-release+2subtests pass
with15 disclosed backend warnings; final3-page live inspection remains next.
No code change, Task08 freeze/commit or Task09 dispatch before review closure.

Final41's three changed paragraphs were inspected live at880/actual320 with
no page overflow or missing images. Four other affected pages exactly match
reviewed40HTML. The owned preview remains available with canonical41 restored.
Lead verification is complete for this snapshot; independent Task08 review
remains active. No human visual/scientific approval or whole-suite success.

### Task08 independent review: blocking operation findings

Spec: issues found. Quality: needs fixes. Three Important cases were reproduced
by the reviewer and traced by the lead: known geometric vertical W can receive
horizontal-wind clearance; changing per-record rotation coordinates changes
mass-grid identity and prevents exact time assembly; native horizontal output
disables an independently requested mass-W remap on the numerical route.
All three enter original-implementer fix round1/5 with regression coverage.

The reviewer also could not verify native FA numerical wind-cube optionality.
A lead header-only probe confirms validate_cube_requests still demands pair
interpretation for a native singleton. The worker receives a bounded fa_cubes
gate/test extension and must prove actual admitted metadata/loader behavior,
without changing shared old-schema producers or weakening explicit analysis.
Minor M1's public projection-precedence contradiction is corrected separately
in its one paragraph; lead retains final documentation verification ownership.

Required producer assertions, polar execution, full writer/resource/general
native qualification and human acceptance retain later named owners. Final41
GUI inspection is already retained; no human approval is inferred. No Task08
freeze/commit or Task09 implementation before scoped independent closure.

Original implementer returned fix round1 with18 new cases, ready for scoped
review. Lead fresh18-case check passes with65 warnings in13.68s. Raw-XML
assertions confirm focused136pass; expanded covering937pass/94fail; required
163pass/35fail; full1717pass/468fail/2errors/2187nodes. All Task07/reviewed
Task08 node/status pairs and exact470 failed/error IDs remain;62 total added
Task08 nodes and18 fix nodes pass. Required/covering/full are still red suites.
Ruff19delivery Python files22baseline/21reviewed/21current/noNew.

Native FA tests now exercise the actual metadata opener and numerical loader
without pair/basis/normalization/companion decoding. The complete direct legacy
preflight formatter separately raises KeyError:'output' from its existing v3
configuration assumption; the trace is retained, no wrapper success or parser
bypass is claimed. Task19 owns that full-wrapper qualification with the existing
Tasks16/19 producer work. Public docs correct projection precedence and describe
per-record angle provenance/time auxiliaries. Final-code examples/strict42/live
inspection and scoped independent closure remain required before commit.

Scoped review is active on complete12-file fix snapshot
`f02a5f3c3f8143dbb2f2a77b4662a10b909d0198` against reviewedca60f6a, including
I1–I3/nativeFA/M1 and actual rotation provenance guidance. Real index remains
empty. Final-code examples03 pass unchanged with independent readers and3
unchanged source hashes; strict42/publication/13unit/4plot-release+2subtests
pass with15backend warnings. Two changed-page live inspections remain next;
neither independent closure nor human approval is claimed.

The five unchanged42 pages exactly match inspected41HTML. The last two changed
pages have a visual-review blocker: the old tab was closed; a new42 tab is open
and focused, but capture reports that the desktop tab is not visible. Browser
content remains connected. No visual pass is claimed; the preview stays available
while the desktop window/Review pane needs to be made visible. Independent fix
review continues. No Task08 commit or Task09 dispatch before required closure.

Fix-round1 review closes I1–I3, M1 and native FA metadata/decode optionality.
One new Important B1 blocks approval: the added angle descriptor retains NumPy
attribute objects, so ordinary numeric valid_range metadata fails YAML provenance
serialization after the transform. The lead traced descriptor/forwarding/writer.
Original implementer resumes bounded fix round2/5 with typed numeric metadata
preservation and real end-to-end RED/GREEN; no global writer workaround or
metadata dropping is allowed. The legacy wrapper limitation remains separate.
The user reports the GUI is visible; final42 inspection can now be retried.

After the user restored visibility, both changed42 pages were inspected live at
desktop1020/actual320 with readable wrapping and no page overflow/missing images.
Five unchanged pages remain byte-equal to41. The same owned preview server and
new retained42 tab stay available. The agent visual blocker is resolved; no
human usability/scientific acceptance is inferred. Only B1's bounded code fix
and its required verification/independent closure remain before Task08 commit.

B1 implementation is ready for scoped closure: only local angle-attribute
normalization and one additive regression differ from fix1. Lead fresh B1/
varying-angle check passes2 with46warnings in3.75s; final-code examples04 pass
unchanged with3 unchanged source hashes. Triple-baseline XML checks confirm
1718pass/468fail/2errors/2188nodes, all earlier statuses/exact470failed-error
IDs preserved, and63 total Task08 added passes. Covering188pass/3fail and
required163pass/35fail remain red with individual old-producer evidence.
Ruff19files22base/21fix1/21current/noNew. Public docs and global writers unchanged;
strict42/live inspection remains the latest verified public-page iteration.
Independent B1 closure and local commit are still pending.

Scoped B1 review is active on complete4-file snapshot
`f6b4d039ab630a876d411bc3cbc87baaf5f6a8f1` against reviewedfix1f02a5f3.
Both closure verdicts are required. Real index empty/HEADbc2a470; original
implementer idle. No Task08 freeze/commit or Task09 dispatch before closure.

## Task08 reviewed operation handoff

Independent spec and quality gates are approved after fix round2/5: I1–I3,
M1, native FA optionality and B1 are closed. No open task-review finding remains.
Detailed interfaces, exact commands and historical evidence: `task-08-checks.md`.

### Frozen interfaces

- `bind_source` binds the actual prepared child once through
  `bind_source_operations`; explicit representation fixtures retain the original
  metadata-only binder contract. Coordinates alone do not prove executable methods.
- Native exports, operation results and internal support stencils are separate.
  Selected readers receive the complete binding and owning source plan, skip
  result descriptors and retain native support independently of export selectors.
- `binding.operations` contains executable model-grid jobs; `operation_plans`
  additionally holds pending polar preparation. `representation_grids` holds
  actual prepared grids separately from `native_grids`. Each job retains complete
  native `input_binding`, selected sample geometry, method, preparation and shared
  original-level support. Destination selectors never renumber a sparse axis.
- `execute_source_operations` computes only requested model-grid results on
  internal native views. It does not change tracker inputs, native exports or
  another calculation's preparation. Unused definitions do no work.
- Native U copying needs no companion/basis/unit normalization. U/V availability
  adds no speed/radial/tangential result. Native numerical multi-file inputs reject
  conflicting units instead of silently inheriting the first label.
- Known component quantity/basis/unit/statistic conflicts fail. Geometric W
  cannot become horizontal U/V; genuine metadata gaps remain gaps. The narrow
  warned Meso-NH missing-projection exception is not widened.
- Sampling, basis and units are independent choices. Existing strict native
  interpolation, three admitted rotations and CROCO joint-mask/rho-angle method
  are reused without new formulas, extrapolation or missing-neighbour substitution.
- W preparation is independent of horizontal output. Numerical native-horizontal
  output can request a mass-W sidecar without U/V analysis or W normalization.
  Pressure velocity retains its quantity/units; geometric conversion is not inferred.
- Operation-only rotation coordinates do not define destination sampling identity.
  Actual per-record `rotation_coordinate: {name, dimensions, values, attributes}`
  or None is retained in source provenance; changing exported angles follow time.
  Numeric NumPy attributes become typed numbers/lists only at this boundary.
- Result frameit_* attributes record operation selectors; native means preserve,
  not an inferred geographic basis. Source operation records retain actual inputs,
  method/preparation/time/cycle/grid/units/shared-level and angle facts.
- Native FA numerical singleton metadata/decode needs no pair/basis/normalization.
  Explicit analysis/speed/polar retains basis/scaling/companion safeguards. All
  producer/profile/geometry/encoding/mask/scaling/resource gates remain.
- The public derived catalogue remains wind_speed. Explicitly named numerical
  calculation APIs retain their behavior; the product pipeline does not infer
  results from available components. Polar descriptors retain shared-level facts
  and magnitude-after-sampling, but remain non-executable until Task09.

### Verification and limits

Fresh lead precommit executes all63 added Task08 cases:63passed/520warnings
in37.93s. Final full1718pass/468fail/2errors/2188nodes preserves all Task07/
original-review/fix1 statuses and exact470 failed/error IDs;63 added passes.
Required163pass/35fail and serialization covering188pass/3fail remain red with
individual producer evidence. Ruff19delivery paths22base/21current/noNew is not
clean lint. Six bounded old test adaptations were independently reviewed;
shared producers and other old assertions remain unchanged.

Both full guide requests execute unchanged plus the transform in its stated
context. Ordinary readers check native samples, known vectors/W, masks/zeroes/
NaNs, axes/units/basis/provenance;3 generated source hashes remain unchanged.
Strict43/publication/13unittests/4plot-release+2subtests pass with15backend
warnings. All7 rendered43 pages exactly equal inspected42HTML; the final changed
paragraphs were inspected at desktop1020/actual320 after window visibility was
restored. Equations/figures/anchors retained; preview stays live.

Scientific impact: corrected eligibility/preparation/provenance boundaries, no
new method/default/diagnostic/dependency or implicit conversion. Compatibility:
existing v3 keys remain; result/provenance facts are additive. Corrected
intermediate prepared-grid IDs do not change native inventory identity.
Examples use atmosphere/ocean/surface without restricting source-name parsing.

Remaining owners: actual polar/legacy-polar integration09, full writer/schema10,
resources11, old producers/assertions16/19, broad native/warning/general-producer
and full direct-numerical formatter qualification19, human scientific/usability21.
The inherited numerical formatter KeyError:'output' remains explicit; real
metadata opening/copying is not full-wrapper success. No gate or warning is waived.
No package repair, source archive write, push, merge or human approval occurred.

## Task09 work in progress

Base `db6258e74dd46df069e8e1434b78b2e1f709d587`, reviewed local Task08 commit.
Tree was clean after commit; nothing pushed/merged. One fresh sole Task09 worker
owns the brief's polar planning/sampling files plus bounded request/operation/
preflight/coupled/runner integration. All earlier workers/reviewers are idle.
Lead owns public docs/examples/figures, STATE/checklist and commits.

Ruling: obsolete pre-implementation polar-pending assertions may change only with
actual C6 target/preparation/support execution and meaningful result/quality/
clock/selection/provenance checks; risk is false clearance. Preserve genuine
scientific/budget/ambiguity failures and shared producer helpers. Independent
review must assess each test adaptation. No new method/schema/dependency.

Consume the reviewed Task06–08 contracts: source-native clocks/centre association,
actual prepared-child binding, separate exports/internal stencils/product results,
real representation levels and typed per-record metadata/angles. Polar speed
must follow component sampling; do not reuse a model-grid speed scalar or infer
radial/tangential requests from U/V. Native and nonpolar work stays optional.
Task10 owns full writer/schema qualification, Task11 resources; existing native/
formatter/old-producer/warning and human-review gates retain their named owners.

The committed prior six-file inventory is175nodes/161pass/14fail, extracted
from Task08's2188-node final diagnostic, not a Task09 run or exemption.
Task09 packet/evidence details stay in the ignored plan workspace; no Task09
implementation or verification result is claimed at dispatch.

The fresh Task09 worker reported a bounded ownership need before implementation:
execution and all3 selected-reader adapters unconditionally reject non-model-grid
products even after binding. Lead traced those4 guards and authorizes only
genuine executable-polar-plan admission, retaining missing/pending/unknown-product
rejection and all complete-binding/owning-source/native-stencil safety. No reader
rewrite or model-grid-only fabricated binding is authorized. Fresh required
baseline:161pass/14fail/175nodes, not a Task09 success or exemption.

The original Task09 worker resumed under that guard extension. Lead's5-page
draft replaces old polar flags/crop-derived geometry with the approved product/
radius/field-option/source-clock contract, retaining equations, references,
figures and anchors. A complete polar-only scalar request plus7 explicitly
contextual fragments resolve schema-only. No runtime admission is inferred.
Strict44/publication/docs checks are active; final actual examples, live
inspection, implementation evidence and independent review remain pending.

Strict44 failed one nested-list indentation; corrected45 strict/publication/
13unit/4plot-release+2subtests pass with15backend warnings. All5 changed pages
were inspected live at desktop1020/actual320, including complete YAML/reader/
support/performance blocks; code right edges remain reachable, no page overflow
or missing images. Existing figures, alt text, links and anchors remain.
Canonical45 preview stays available. The sole worker received these declared
example choices for final method/quality/provenance reconciliation, not as
proof of runtime admission. Actual examples/code evidence/independent review
are still pending; no human or scientific approval is inferred.

Task09's original worker returned DONE_WITH_CONCERNS and is idle. Lead read the
complete report, portable checks and scope proof. Reported focused101pass;
required161pass/14fail; covering1026pass/68fail; full1819pass/468fail/2errors,
with every2188 prior status and exact470 failed/error ID retained. These are
worker results pending fresh lead corroboration and independent review.

Before review, public examples must use radius/azimuth/azimuth_degrees rather
than retained low-level rr/theta names, and explain per-field geometry quality,
speed component policies and nearest spherical-footprint cost. The directly
affected output-guide polar subsection is corrected now with its old anchor
retained; complete writer/schema qualification remains Task10 and full-page
review Task20. Actual examples, final strict/live checks and independent review
remain required. No Task09 commit or Task10 implementation yet.

Fresh lead focused101case run passes with428warnings in37.71s. The actual
unchanged instructional guide request fails, however: 1-D geographic coordinate
names are also dimensions; executor renaming removes longitude/latitude before
the sampler. Original implementer resumes a bounded preparation-boundary fix
and additive real-reader/sampler/output regression. No generator, fixture or
documented scientific choice is changed to avoid the failure. First independent
review remains undispatched; complete example success is still required.

Lead raw-XML assertions corroborate the original delivery counts and exact
preserved prior statuses/failed IDs; all14 required failures retain their
individual old-producer rejection. Six public pages now reconcile public axes/
chunks, field-specific quality, speed policies, nearest-footprint cost and the
direct output subsection (old anchor retained). A real GRIB probe confirms that
the shared fragment needs explicit pressure-kind gap completion; its page now
teaches that declaration, not name inference. Strict46/publication/13unit/
4plot-release+2subtests pass with15warnings; six pages inspected live1020/320.
The preview remains available. Original worker still owns the real rectilinear
example failure; no final runtime acceptance or independent review is inferred.

The rectilinear fix now has a complete worker handoff:103focused; required
161pass/14fail; covering1028pass/68fail; full1821pass/468fail/2errors/2291nodes,
reported unchanged prior statuses. Lead fresh two-case check passes2 with4
warnings in3.16s. Unchanged guide/execution/ordinary reader, partial policy and
both-products4/8km crop-independence checks pass with source preservation.

The same complete example harness found a separate real native2-D FA guard
failure: source_positions=None is treated as cube indices. The original worker
resumes a bounded scalar/cube distinction with actual FA decode/sampler/output
and invalid-support regressions, retaining all locator/owner/cycle/metadata
safeguards. This is pre-first-review acceptance work, not independent closure.
No review/Task09 commit/Task10 dispatch before all actual examples succeed.

Scalar-FA delivery is complete and its original worker idle. Lead fresh five
cases pass in13.58s without warnings. Raw-XML assertions corroborate108focused,
required161pass/14fail, covering1033pass/68fail, full1826pass/468fail/2errors/
2296nodes; every prior status and exact470 failed/error ID remains,108 added
passes. Fresh Ruff15paths23base/23current/noNew and scope preservation checks pass.

Complete lead harness05 now passes unchanged published scalar YAML/Python,
strict/explicit0.75coverage/both-products4/8km crop independence, downstream
helper fragments and shared GRIB/FA contexts. Ordinary readers check prescribed
values/units/clocks/quality/provenance, retain source-specific index auxiliaries
and preserve all6generated source hashes. Strict47/publication/13unit/
4plot-release+2subtests pass with15warnings; six rendered pages equal inspected46.
First independent task review is next; no freeze/commit/Task10 or human/scientific
approval is inferred. All inherited red suites and later qualification owners remain.

First independent Task09 review is active on the complete23-file precommit
snapshot `df10cd7eb4aa34ec5209a5c7b2feb70ca589b19c` against db6258e.
Both spec and quality verdicts are required, including all3 old-test adaptations,
six public pages and actual sampling/representation semantics. The original
implementer is idle; real index empty/HEAD unchanged. No Task09 freeze/commit or
Task10 implementation before independent closure.

Independent Task09 review requires fixes: two Important C6 defects. A provisional
fine-grid target is budgeted before choosing the final shared coarsest target,
rejecting the documented valid54point/60limit case. Integer continuous bilinear
inputs lose fractional values in the reused numerator cast while output status
says valid. Lead traced both connected paths; original implementer resumes
bounded fix round1/5, preserving native exports/ownership/one-bind contracts.
All3 old-test adaptations were independently judged legitimate.
Minor inherited warning debt remains with Task19 qualification and final branch
review, not suppressed or repaired through environment/producer changes.
Original reviewer is idle; no Task09 freeze/commit or Task10 dispatch.

Fix round1 implementation is ready for scoped re-review. Lead fresh13newcase
check passes/80warnings/5.93s; final unchanged example harness06 passes with6
source hashes. Raw-XML checks corroborate121focused; expanded covering1110pass/
68fail; required161pass/14fail; full1839pass/468fail/2errors/2309nodes. All prior
statuses/exact470failed-error IDs remain,121added passes versus Task08.
Base/review-relative Ruff15paths23/23/noNew and scope preservation pass.
The original implementer is idle; findings are not independently closed yet.

Shared plans now retain non-executable prepared/target-pending evidence until
final common axes pass budgets; same real bindings publish without rebinding.
Continuous integer bilinear values use a local float64 view, with numeric dtype/
conversion provenance and unchanged native exports. Canonical docs record that
policy and ordinary floating/large-integer limits. Corrected strict49/publication/
docs checks pass/15warnings after one heading-style failure; final live inspection
and original-reviewer closure remain required before freeze/commit.

Scoped fix1 review is active on complete10-file snapshot
`c1ed1be81a0db7fa5213d3868faf182a220c0a89` against revieweddf10cd7.
Both I1/I2 closure and new fix breakage are assessed, with both verdicts required.
The two changed49 public pages were inspected live1020/actual320 with no page
overflow/missing images; four other affected49 pages equal previously inspected47.
Canonical49 stays available. Original worker idle/real index empty; no Task09
commit or Task10 dispatch before independent closure.

## Task09 reviewed polar handoff

Spec/quality independently approved after fix round1/5; I1/I2 closed, no new
fix finding. Inherited Minor3 warning debt retains Task19/final-branch ownership.
Detailed commands/evidence: `task-09-checks.md`. No scientific/human approval.

### Frozen interfaces

- Actual children bind once; readers receive complete executable bindings and
  owning source plans. Exports/internal stencils/model-grid operations/polar jobs
  stay separate. The4extra adapter/execution changes are admission guards only.
- `bind_polar_plan` validates actual preparation, geometry, kind/method/support
  and spacing. Shared plans remain prepared, binding pending_polar_target and
  descriptors pending_polar_sampling until final shared axes pass. No unfinished
  method/target evidence authorizes payloads.
- `resolve_polar_sampling` resolves final targets/budgets only. Coarsest actual
  prepared spacing uses the larger axis median; finer explicit requests reject,
  allowing1e-12relative roundoff. Open clockwise rings include exact outer radius,
  reported shorter last interval and documented automatic angle counts.
- Private `_publish_source_binding` extracts existing publication, not a second
  bind. Shared bindings publish the same objects only after all final budgets
  succeed. Failure/rebind revokes owning clearance and stale common-target facts.
  A54point target fits60/fails53; unused fine axes/counts are not budgeted.
- `require_executable_products` rejects unfinished/unowned/unknown/invalid product
  evidence. Real scalar FA locators differ from selected cubes; complete owner/
  locator/time/cycle/native-axis/support and decoder safeguards remain.
- `binding.operations` remains model-grid-only. Polar operation_plans retain real
  input bindings/preparation/geometry/options/original-level facts; polar_plan
  records source/centre associations, spacing/support/axes/count/budget facts.
  Native-only/track-only work stays independent of optional polar dependencies.
- `prepare_source_operation` serves calculation-specific preparation.
  `execute_source_polar` uses each source's native clock; `verify_polar_target`
  checks actual coordinates/centres before shared publication. Unequal clocks
  remain distinct; preceding_hour stays AROME/NEMO NetCDF-only.
- Kind needs evidence/declaration; continuous defaults bilinear, categorical
  nearest. Invalid/unused options fail. Strict or explicit-threshold coverage
  preserves zero/NaN/unmapped distinctions. Nearest cannot renormalize/extrapolate;
  an extra geometry-only bilinear build restricts its spherical source-cell
  footprint. Support is independent of exported crop; unavailable targets count.
- Speed takes hypot after component sampling; minimum component support and both
  component validity are explicit. Native U/V adds no diagnostic. W preparation
  is independent, preserving pressure/geometric meaning, own levels and units.
- Rectilinear geographic dimension-coordinates, moving geography/angles, member
  axes, hybrid dependencies and FA record labels retain actual meaning. Sharing
  target coordinates does not equate source-specific auxiliaries or masks.
- Continuous integer bilinear inputs use a local float64 view; native/model-grid
  exports remain unchanged. Floating/nearest inputs keep prepared evaluation
  dtype. JSON polar_numeric_types and per-record numeric_types record actual
  prepared/evaluation types/conversion. Prepared is not encoded storage; ordinary
  rounding/integers beyond2**53 remain limits. Shared numerical helper unchanged.
- Public radius/km, azimuth/rad, azimuth_degrees/degrees and source time/center_time
  are explicit. Per-field geometry/support/status/valid/ring quality is exported;
  global geometry_mapped is the intersection, not a source mask. Provenance
  retains actual methods/options/origins/levels/dtypes/footprints/regrid/cache facts.
- Writers consume field_products[(source,"polar")] and common descriptors with
  stored_names/dimensions/units. Existing numerical rr/theta APIs remain. Cache
  bytes/target counts are not process-memory ceilings or archive benchmarks.
  Task10 still owns full stable mixed-grid/coordinate/encoding compatibility.

### Verification and retained owners

Fresh precommit command in frameit_env3.13 with worktree PYTHONPATH, TMPDIR and
approved fixture root: `python -m pytest -q src/frameit/testing/numerical/test_v3_polar.py --tb=short`
passes121/510warnings in54.97s. Final full1839pass/468fail/2errors/2309nodes
preserves all2188 Task08 statuses/exact470failed-error IDs,121added passes.
Required161pass/14fail and covering1110pass/68fail remain red with individual
old-producer evidence, not scientific assertion passes. Ruff15paths23base/
23current/noNew is not clean lint. All3 old-test adaptations independently
reviewed; shared producers and108pre-fix definitions preserved.

Complete unchanged scalar/coverage/both4/8km-crop/downstream/sharedGRIB-FA
examples pass with prescribed values/units/clocks/quality/provenance and6source
hashes. Strict49/publication/13unit/4plot-release+2subtests pass/15warnings.
Two updated pages inspected live1020/actual320; other4affected49pages equal
inspected47HTML. Equations/figures/references/old output anchor retained; preview
available. No archive run or human acceptance inferred.

Scientific impact: correct declared point sampling/admission/magnitude order,
not new diagnostics, quantity guesses, fallbacks or conservation promises.
Compatibility: existing YAML/defaults/dependencies unchanged; actual polar
products/additive quality/type provenance, native/model-grid values preserved.
Remaining owners: full writer/schema10, resources11, old producers/assertions16/19,
native/legacy/encoding/warnings19, human science/usability21. Minor3 and inherited
direct-numerical formatter limitation remain. No source archive write, environment
repair, push or merge occurred.

## Task10 work in progress

Base393e7d92ddafefd31542ea7a7a49751db860efda, reviewed local Task09 commit.
Postcommit tree clean; nothing pushed/merged. One fresh sole Task10 worker owns
the C7 writer/path/execution brief, plus bounded existing coupled dataset assembly/
regional-output mapping and preflight product-descriptor integration. Lead traced
the actual direct native-grid merge and common field_products writer path; C7
requires a dataset boundary change, not encoding-only edits. No scientific
preparation/target/binding/schema/default/dependency expansion is authorized.

Lead owns public pages/examples/figures/STATE and commits. Original workers and
reviewers are idle. Ruling: old intermediate v3 output-axis assertions may adopt
C7 names only with preserved values/masks/units/original coordinates/indices/
bounds/clocks and explicit stability checks. Source fixture axes/shared producers/
payload assertions/numerical API names are not renamed; every adaptation reviewed.

Task10 prior exact4file inventory91nodes59pass31fail1error is extracted from
Task09's reviewed final XML, not a Task10 run or exemption. All scientific/
resource/native/warning/producer/human qualification retains the stated owners.
No Task10 implementation or verification result is claimed at dispatch.

Fresh sole Task10 worker is active under the bounded packet. Lead's four-page
C7 draft teaches canonical output names, local-zero versus original coordinates,
stable-grid naming and exported storage dimensions without renaming input or
numerical API conventions. Complete scalar context and two supplementary
storage/resource fragments resolve schema-only. One strict50 list-indent error
was corrected; final draft51 raw checks/live inspection remain next. Actual
writer/output examples and independent Task10 review are still pending.

Draft51 strict/publication/13unit/4plot-release+2subtests pass with15backend
warnings. Four draft pages inspected live desktop1020/actual320, including the
coordinate table and code right edges, without page overflow/missing images.
Canonical51 preview remains available. This is documentation-draft inspection,
not runtime C7 qualification or human/scientific approval. The original sole
Task10 worker remains active; lead prepares ordinary-reader examples disjointly.

The original worker returned NEEDS_CONTEXT:31of32 new cases pass, while distinct
valid vertical axes fail at execute_source_polar's exact per-field merge before
runner output qualification can run. Lead read the complete report/actual trace
and reproduced that boundary. A bounded output-only hook there is authorized:
reuse inventory-derived C7 names/references after sampling/quality calculations,
before merging. No preparation, interpolation, quantity, target/budget/binding or
low-level numerical API changes are authorized. Both-format values/metadata and
name-stability checks plus the full frozen diagnostic remain required.
The original worker resumes; no final Task10 handoff, review or commit yet.

First frozen Task10 delivery reports35new passes and full1874pass/468fail/2errors,
all2309 prior statuses retained. Lead fresh35case check passes/210warnings/21.85s;
the frozen Task09 example harness passes unchanged with6source hashes.
Full-domain ordinary NetCDF/Zarr and explicit storage examples pass, but the
documented fixed pilot exposes incorrect cropped dimensions(time,y_box,x).
Lead traced geographic2-D broadcast followed by last-axis lookup in the output
formatter; both native axes map to x_box. The original worker resumes a bounded
formatter correction with actual-generator/crop regressions, without changing
scientific extraction. No first independent Task10 review or commit yet.
The pilot's declaredcpus1 versus effectivebudget16 is separately recorded for
Task11 resource wiring; workers stay1 and no CPU-ceiling check is claimed here.

Canonical draft55 strict/publication/13unit/4plot-release+2subtests pass with15
backend warnings. The mobile coordinate table fit but was cramped; it now uses
the site's existing full-width definition-list style with all7C7 mappings and
the original anchor. Live desktop1020/actual320 inspection shows readable names,
no overflow/missing images; four other affected55pages equal inspected54/52/51.
Original-auxiliary/CF-reference/annotation/storage facts are reconciled with the
reported implementation. This preview remains available, not runtime/scientific/
human acceptance. The original worker still owns the cropped-axis correction.

Task10's cropped correction is delivered and frozen; original worker idle.
Lead fresh39output cases pass/214warnings/25.43s. Saved XML corroborates final
1878pass/468fail/2errors/2348nodes, all2344firstTask10/all2309Task09 statuses and
exact470failed/error IDs,4/39added passes. Required59pass/31fail/1error and
connected1194pass/84fail/1error remain red with per-node evidence, not exemptions.
Fresh14freeze hashes/scope/Ruff12paths23base22current/noNew/9inputhashes pass.

Final lead scalar/readers/storage/pilot, vector/transform and unchanged09harness
pass with4/3/6source hashes. Actual crop axes are(time,y,x), local0..4/native6..10;
values/masks/clocks/units/provenance and default/configured Zarr storage agree.
Strict56/publication/13unit/4plot-release+2subtests pass15warnings; all5pages equal
inspected55/54/52/51HTML. Canonical56 remains available. First independent
spec/quality review is next; no Task10 commit or scientific/human approval yet.

First independent Task10 review is active on the complete19-file snapshot
`42b14ad894a327c69d29179a16859bfb395259a6` against393e7d9. Both spec and quality
verdicts are required, including old output-assertion adaptations, five public
pages and the approved output-only polar hook. The original worker is idle;
real index/HEAD unchanged. No Task10 commit or later task dispatch before closure.

Independent Task10 review requires fixes for three Important C7 defects:
packed fill codes can mask a valid decoded coordinate zero; CF formula semantic
labels are renamed with dependencies; distinct moving grids lose output identity.
Lead traced actual callers and fresh compact probes confirmed all three. The
original worker resumes bounded fix round1/5 in existing output boundaries,
preserving scientific preparation/sampling/binding/targets and prior assertions.
New Zarr tests' avoidable consolidation-fallback warnings receive small explicit
reader cleanup, not global suppression or storage changes. All earlier output-axis
adaptations were independently accepted. Original reviewer idle; no Task10 commit
or Task11 implementation before scoped independent closure.

Fix round1 author delivery is frozen. Lead51output cases pass/282warnings/51.51s;
all39reviewed cases retained, M1 fallback warnings gone. Saved XML corroborates
1890pass/468fail/2errors/2360nodes, all2348reviewed/all2309Task09statuses and exact
470failed/error IDs,12/51added passes. Required59pass/31fail/1error and12file
covering571pass/64fail/1error remain red. Fresh15freeze hashes/scope/9inputhashes
and base/review-relative Ruff23/22→22/noNew pass.
Scalar/vector/unchanged09harness03 pass with4/3/6source hashes. Canonical57
records missing encoding/CF labels/complete trajectory provenance; strict/
publication/docs checks pass15warnings, new notes inspected live1020/320 and
other4pages equal inspected56. Original worker idle; scoped original-reviewer
I1–I3 closure and new fix-breakage assessment remain required before commit.

Scoped fix1 review independently closes I1–I3 and M1, but finds new Important N1:
shared-snapshot field-list selection drops bounds on an extra dimension while
retaining the declaring CF attribute. Lead ordinary-reader checks confirm source
pruning and a successfully published dangling reference; four compact reviewer
inputs remain unchanged. Original worker resumes bounded round2/5 on that output
view only, with first-time/singleton-level both-format regression. The closed
missing-encoding, CF-label and trajectory roots remain intact. No Task10 commit
or Task11 dispatch before N1 closure. Per user preference, further rendered checks
use text-only DOM/HTML/build evidence, not screenshots.

N1 round2 author delivery is frozen: one output-view expression drops other
physical data variables while retaining coordinate/support dimensions. Two new
both-format regressions append to the byte-exact51-case module. Fresh lead
2cases pass/33warnings/5.87s;16freeze hashes, exact2path scope, preserved prior
evidence/reviewer inputs,9fixture hashes and zero new Ruff diagnostics verified.
Required failed/error traces retain their ordered exceptions/locations, not passes.
All3unchanged example harnesses04 pass with4/3/6source hashes. Strict58/publication/
13unit/4plot-release+2subtests pass15warnings; five HTML pages equal57. Text-only
live1020/320 DOM checks show no page overflow; no image capture/pixel/human claim.
Canonical58 remains available. The original worker owns the one final full
diagnostic/comparisons; original reviewer N1/new-fix closure is still required.
No Task10 commit or Task11 implementation yet.

Round2 final full evidence is complete:1892passed/468failed/2errors,2362nodes,
6031warnings/4passed subtests/480.61s/exit1. Lead raw-XML assertions preserve all
2360fix1/all2309Task09 statuses and exact470failed/error IDs;2new/53total additions
pass. Every failed/error message and trace is either423byte-identical or47declared
run-context-only differences against both baselines. Covering366passed and
required59passed/31failed/1error are corroborated. All16freeze hashes still match.
The author also confirms correct both-format bounds on the four unchanged
read-only reviewer inputs in fresh attempts. Full/required red diagnostics and
later producer/native/resource/human gates remain explicit. Original reviewer
must close N1/new-fix breakage before Task10 commit or Task11 dispatch.

## Task10 frozen handoff — independently approved

The original reviewer closes N1 in the second scoped fix round: spec approved,
task quality approved,0Critical/Important/Minor new findings. I1–I3/M1 remain
closed; no Task10 finding is parked or open. Fresh lead precommit command:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" conda run --no-capture-output -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_outputs.py --tb=short --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-10-lead-precommit.xml
```

Observed53passed/314warnings/51.55s. All16frozen hashes and `git diff --check`
pass after review; source/tests/public pages match reviewed tree
`a47b2d8375e7cd05ca3ddf45765785c1632ed91e`. Only final internal closure records
and checklist marks differ. Strict58/publication/examples and text-only live
desktop/narrow evidence above remain current; no new public source changed.

Later tasks consume these interfaces rather than redefining them:

- Common request-plan products supply paths. `OutputPaths.planned_products`
  validates them; writers do not invent another naming map. One field dataset
  is assembled per source/product, preserving each field's native grid.
- `runner.field_products[(source,product)]` carries those datasets;
  `runner.published_products` receives only actual complete publications.
  Result/status fields record source, run-relative path, stored name,
  dimensions, units, representation and actual reopened encoding/layout.
  Preserve earlier complete publications when a later write fails.
- `output_grid_layout(source)` uses complete inventoried grid/trajectory
  identity before filtering; per-field lookup resolves shared snapshots.
  Coordinate names/own geography stay stable under add/reorder/filter. Local
  horizontal positions start at zero, including crops; explicit auxiliaries
  retain original coordinate labels, units and source-native indices.
- `format_model_grid` and `format_polar_output` qualify axes, original
  auxiliaries and CF references without changing scientific values/units.
  Semantic formula/cell-measure labels remain labels. Bounds/support on extra
  dimensions survive field-only output views; singleton vertical levels remain.
- `execute_source_polar(..., *, plan_cache=None, output_formatter=None)` retains
  the single approved output-only hook after calculations and before per-field
  assembly. C6 preparation, targets, sampling, numeric types, speed/W meaning,
  source clocks and centre associations remain frozen.
- NetCDF4 engines and sharded Zarr3 preserve dtype/precision and missingness.
  Decoded floating non-None fill codes become NaN, not masked physical zeroes;
  integer/time handling stays unchanged. Defaults remain compression1/
  coordinate compression off. Writer chunks/shards use exported dimensions;
  storage-option applicability and safety/ownership rules remain strict.

Scientific impact: no new calculation, physical interpretation, method or
scientific approval. C7 output names/local-index auxiliaries and actual encoding/
publication facts are the intended public output contract, documented on the
five affected canonical pages. No new configuration/installation control.
No direct-source/numerical-API rename or blanket downstream-script compatibility
promise. Existing exact/native and justified transformed checks are not general
real-producer validation.

The required59passed/31failed/1error and full1892passed/468failed/2errors remain
red with exact per-node evidence; no passing scientific assertions are inferred.
Remaining owners: CPU wiring/layout resources11, records/CLI/status12–15,
producers/native/backend warnings16/19 and human scientific/usability21.
Inherited Task09 Minor3 remains for19/final branch review. No package repair,
source-data write, screenshot/image capture, push, merge or human approval.

## Task11 active scope

Base is the reviewed local Task10 commit2a77b1dcfd06eccbabf10d1a58aac71881b8f6f8;
tree clean immediately after commit, no push. The exact Task11 brief and bounded
handoff reserve runtime/execution and necessary existing reader/product/writer
resource/chunk integration for one fresh worker. Lead owns canonical docs,
STATE/checklist and final staging/commits. No new scientific method/default,
public key, dependency, scheduler service or status engine is authorized.

The demonstrated cpus1→budget16 mismatch belongs here; enforce effective budgets
and record origins without changing C6 scientific sampling/C7 publication semantics.
Preserve selected backend views before chunks, actual async/spawn publication
facts, all native metadata/CF support and optionality. Small layout measurements
are bounded, not a production/HPC or memory-ceiling claim.

Refreshed prior required inventory comes from committed Task10's frozen full XML:
79nodes60passed/18failed/1error, exact names/messages/traces in the ignored
task-11-committed-baseline-nodes records. This is not a Task11 run or exemption.
Fresh focused/required/covering, independent measurements/reopening and final
full-node evidence are still required. All prior agents are idle; no Task11
implementation or verification is claimed merely by opening this task.

The Task11 worker requests bounded context before freeze:35new focused cases have
33passes/2cross-source-union failures; covering710passes/2failures and required
60passes/18failures/1error preserve the79prior statuses. No final full run exists.
Lead fresh probes confirm the ocean's per-source chunk guard wrongly rejects the
atmospheric height_above_ground key, and profileFalse still invokes cache clocks
14/8times. These are real remaining C8 gaps, not inherited failure waivers.

Ruling: extend the same worker to bind_sources resource/union validation and
child runtime projection, and timing-only boundaries in the existing regrid-plan/
source-geometry cache classes. C8 requires union-wide applicability and optional
performance measurement. Preserve bind-once/failure revocation, geometry hashes,
weights, scientific operations, direct numerical defaults and cache injection.
Disabled timings must be explicitly unmeasured. The exact risks/negative controls/
measurement caps are in the ignored task-11-scope-rulings.md. Lead also inspected
and narrowly accepted the local selected-reader test helper's applicable-key
filter and the earlier no-publication assertion; scientific/payload guards stay.
Original worker resumes; no new scientific policy, human approval, final freeze,
Task11 commit, package repair or image check is implied.

The first frozen Task11 full diagnostic finds15new regressions:
1921passed/483failed/2errors across2406nodes, while44new cases pass and all470prior
failed/error IDs retain their causes. Native preflight was changed from metadata
preparation to full scientific binding, prematurely narrowing candidate pools or
rejecting requests meant to remain pending. Lead reproduces four groups freshly
(4failed/8warnings/0.94s). The candidate is not ready to review or commit.

Ruling: lift that failed freeze only for the native preflight/resource-report
boundary and appended guards. Restore discovery without weakening actual binding/
execution, union checks, failure revocation or payload restrictions. Preserve
all15old assertions and44new cases. The failed source tree/report/freeze/full
evidence is retained; all171Python hashes matched before lifting the freeze.
After expanded coverage and required checks, allow one replacement freeze/full
under new artifact names, with every prior status/cause compared individually.
No more benchmark trials; measured execution-path scope must stay unchanged.
No Task11 lead runtime examples/new published docs have been run yet. Independent
review remains required; no failure waiver, new scientific approval or commit.

The authorized native-preflight correction is frozen and verified. The15old
regressions recover;44retained resource cases and15newguards pass (59total).
Lead fresh four-group GREEN passes4/8warnings/0.86s; raw XML corroborates expanded
covering961passed/20inherited failures and required60passed/18failed/1error.
All171frozen Python hashes,169unchanged correction paths, old44case prefix,
unrelated/bound preflight AST,20prior final artifacts and9fixture hashes match.

Replacement full:1951passed/468failed/2errors/2421nodes,6189warnings/4passed
subtests/492.92s/exit1. Lead raw XML checks preserve every2362Task10 status and
every2406failed-candidate node except exactly15failed→passed recoveries;59new
passes/no removed or new failed IDs. All470inherited failed/error causes remain
individually classified, not passed or waived. Rejected evidence is retained;
no third full or further benchmark trial.

Lead unchanged scalar/vector/frozen09harnesses pass4/3/6source hashes. The actual
pilot reports budget1/nested limits1 with correct origins/layouts. The vector
verification launcher needed a guarded outer entry for actual spawn; original
harness bytes/scientific assertions stay unchanged and the failed attempt remains.
The published guarded polar API also runs as a real script with its ordinary
reader and unchanged source hash. No source fix/freeze lift was needed for those
verification-entry/extraction corrections.

Six canonical pages document C8 facts/current keys/spawn-safe entry. Five YAML
contexts pass schema-only. Strict60/publication/13unit/4plot-release+2subtests
pass15warnings; six HTML pages equal text-DOM-checked59. Text-only1020/320checks
show no page overflow; no image/pixel/human claim. Canonical60 remains available.
Fresh lead14path Ruff73→56/noNew; scientific methods/defaults/precision unchanged.
Complete Task11 independent spec/quality review is next; implementer idle, no
Task11 staging/commit yet.

Independent Task11 review requires one Important fix: direct Python scheduler,
native-thread and synchronous-export choices are mislabelled as defaults when
origins are absent. Lead fresh probes confirm the labels survive incorrectly
through repeated resolution and effective-origin overlay; CPU enforcement itself
is not the defect. A small Minor report string also incorrectly promises backend-
preferred reader chunks. Lead reproduces stored1x3x3 versus selected-view1x9x9
chunks with exact equal values.

The same implementer owns round1/5: fallback-origin labels and the one description
only, plus appended compact tests; no numerical/reader/binding/thread/export
behavior change. All59resource cases and15recovered metadata assertions remain.
Ruling: use focused/named6file covering/required79 checks and exact scope proof
rather than a third whole-suite diagnostic for this metadata-only fix. The full
1951passed/468failed/2errors remains explicitly pre-fix evidence; no post-fix full
outcome is claimed, and final Task19/full integration remains necessary. No
benchmark, image check, Task11 commit or Task12 dispatch before scoped closure.

## Task11 frozen handoff — independently approved

Original review plus fix1 closure approve Task11 spec and quality. Important1
and Minor2 are closed; no new Critical/Important/Minor finding and no open or
parked Task11 finding. Reviewed final tree:
`6199d8f502432356d307fabfc37997367b202713`.

Fresh lead68resource cases pass/162warnings/19.91s, including actual direct-option
execution provenance and selected-view chunk reports. Post-fix covering is
555passed/6failed/1error; required79 is60passed/18failed/1error. Saved XML retains
all604covered baseline statuses/causes plus9newpasses (613distinct nodes).
1817baseline nodes, including15earlier metadata recoveries, were not rerun in
fix1. The1951passed/468failed/2errors full is PRE-FIX only, not a post-fix result.
No third full/extra benchmark or fresh status for unrun nodes is implied.

Final171source/test freeze hashes,168other unchanged Python paths, exact old59
resource cases,2188immutable artifacts,9fixture/24benchmark input hashes and
zero-new-Ruff proofs are recorded. Fresh strict61/publication/13unittests pass;
six public HTML pages equal60 and reviewed public source stays exact. Text-only
live1020/320checks show no page overflow. Earlier scientific-example/benchmark
checks remain pre-fix; unchanged numeric paths and fresh actual-provenance tests
provide the proportionate reporting-fix evidence. No image/pixel/human claim.

Later tasks consume these interfaces:

- `resolve_execution_resources(options)` returns effective options and one budget
  with detected limits, actual worker/native counts, export mode and setting
  origins. Supplied labels survive; unlabelled direct nondefaults are explicit,
  equal-to-default values use default fallback. Constructor intent for equal
  values is not recoverable or claimed. Readers are serial; compute/export are
  successive; export×compute×native must fit the budget.
- `execution_scope` and the existing spawned export pool share effective resource
  facts, limit Dask/native threads and restore outer state. Asynchronous export
  genuinely spawns by default; Python file callers need a main guard or explicit
  synchronous export. Preserve actual complete descriptors on ordinary failures.
- Native metadata preflight remains discovery-only with unbound requests and
  explicitly pending field/method-dependent layout facts. Actual bind/execution
  validates complete product/source/writer chunk applicability before payload
  or publication and revokes clearance on failure; no rebind or wider read.
- `describe_v3_resources` reports resources/layouts/configuration/setting_sources.
  Input keys are native axes, processing/storage keys public product axes.
  Matching uses applicable unions, not every dataset. Actual reader applications,
  product chunks and reopened storage sizes remain separate.
- Selected backend views precede Dask chunks. Automatic reader wording points
  to applications rather than promising backend-preferred blocks. Estimates
  distinguish selected/native arrays and unresolved decoder/workspace/storage
  costs; none is an enforced process-memory ceiling.
- YAML polar profileFalse makes optional timings/graph/RSS measurements unmeasured.
  Cheap cache/retention counters remain. Per-call timing controls preserve injected
  caches and low-level timing defaults; profile is not a geometry-key component.
  Scientific geometry/weights/masks/precision/cache limits remain unchanged.

Scientific impact: no new method, units, interpolation, missing-data policy,
reference frame or scientific approval. C4/C6/C7 values, clocks, W/speed semantics,
stable coordinates/CF support and output ownership remain frozen. Compatibility:
actual default spawned execution, stricter unmatched-dimension errors, additional
resource/layout origins and unmeasured timings are documented on six canonical
pages. No new public key/dependency or migration machinery.

Cannot-verify items retain approved owners rather than fabricated passes:
post-fix whole integration and inherited470failure/error causes/warnings19/final;
request/status/interruption12, CLI/producers13–16, HPC18, documentation20 and
human scientific/usability21. Task09Minor3 remains19/final debt. The reporting
fix's prescribed checks are complete; no unresolved new C8 review gap remains.
No source-data write, package repair, push or merge. Commit locally before12.

## Task12 active scope and record contract

Basec7d1c658f6b9e7df0f69439e014efb42b5abaa57; clean tree verified after commit.
Approved12 remains bounded: extend existing ownership/status/provenance and
parent writer completion, plus necessary authored-context capture at existing
configuration/settings boundaries. No new service/parser/scientific schema or
replay. Lead owns public docs/STATE/contracts/commits; one fresh implementer.

Ruling: use one `run-request.yaml` metadata envelope plus existing records,
not separate authored/override files or a journal. Why: preserve the approved
early snapshot with the smallest shared state. Cost if wrong: reader integration
or capture rework, addressed by Task12 independent review before Task15 consumes it.
`task-12-record-contract.md` freezes record_version1, authored mapping/kind/path,
configuration/launch bases, raw overrides, requested options and runtime/code
identity. Status/provenance retain actual products separately from planned,
pending phases and updated_at. Existing metadata filenames stay unchanged.
Authored mapping capture does not claim original bytes/comments or input identity.

Ruling: retain pre-ownership CPU/source/path/binding safety; only the already-owned
failure window requires early records. Parent callbacks checkpoint actual atomic
returns in both export modes; no eager reads/progress service or altered physics.
Stale running/locks and SIGKILL/Zarr gaps remain honest limits, not auto-recovery.
These are technical decisions within the approved task, not human scientific
choices or a replacement plan requiring repeated scope approval.

Task12 prior required inventory is62nodes45passed/16failed/1error. No post-fix11
full exists: the saved composite2430node baseline combines2421pre-fix full nodes
and613post-fix covered nodes/9newpasses, preserving freshness per node rather than
claiming a current full. Task12 must run its own focused/covering/required checks
and one final full after freeze. No Task12 implementation/result is implied by
opening the task; all11workers/reviewers are idle.

The first frozen Task12 candidate reports55new passes and required62 retains
45passed/16failed/1error. Its single full exercises2485nodes:
2015passed/468failed/2errors, retaining all2430mixed-age baseline outcomes.
This does not cover the separately found positional-constructor defect: the
new internal field shifts old optional arguments. Lead reproduces the actual
old position71 silently binding to request_context instead of infer_grid_geometry.

Ruling: preserve that candidate/full/freeze and lift source freeze only to make
the new field keyword-only, retaining old positional order/defaults and adding
a compact actual-construction regression. No second full for this one-field
correction: the full is explicitly pre-correction; covering/required checks,
exact unchanged-behavior proof and independent review must qualify the final
candidate, with Task19/full integration still required. All prior tests,
evidence/fixture hashes and scientific paths remain unchanged. No Task12 lead
runtime/docs acceptance, source fix or completion is claimed merely by this ruling.

The bounded constructor correction is frozen: kw_onlyTrue restores old optional
positional/order/match-argument semantics. All55prior cases remain byte-exact,
with1newconstructor regression. Fresh lead56passes/175warnings/23.59s; covering
574passed/16failed/1error and required45passed/16failed/1error independently
corroborated, every covered old outcome/complete cause retained.591distinct
post-correction nodes tested;1895full nodes unrun afterward. Full2015/468/2 stays
PRE-CORRECTION only, not a new full result.

All172freeze hashes,170other paths, original tests/artifact contents and9fixture
hashes match. Older evidence has4388exact current files plus append-only lead
ledger prefixes, not4389current whole-file hashes. Fresh aligned6path Ruff41→39/
noNew. All3unchanged scientific harnesses pass4/3/6hashes; four independent YAML
readers verify actual request/base/options/code and status/provenance/inventory
records without FrameIt/archive reads. Strict62/publication/13unit and text-only
live1020/320five-page layout checks pass. Canonical output62 remains available,
no image/pixel/human claim. Fresh independent Task12 spec/quality review is next;
original worker idle, source/tests frozen, no Task12 staging/commit yet.

Independent12review reports0Critical/1Important/0Minor: a yielded successful
future is marked observed before descriptor retention, so caught parent SIGTERM
in that window makes the drain skip its actual completed publication. Lead
reproduces it on the exact current parent loop (retained1control,0/exit143signal),
without source/product writes. This is not the documented uncatchable-loss gap.

Original implementer owns fix1/5 in parent export accounting plus appended
regressions; preserve all56existing cases and every scientific/capture/constructor/
resource/ownership boundary. Actual retention must be exactly once even when a
callback fails after retention. No new scan/service/signal policy.
Ruling: targeted TDD/same8file covering/required62 and exact scope proof, not a
second unfiltered full for this bounded accounting lane. Existing2015/468/2full
remains pre-constructor/pre-I1 only; final19/full integration and scoped independent
closure remain required. No Task12 commit or Task13 dispatch before closure.

Task12 I1 fix1 is frozen and lead-verified: parent guards actual retained paths
and drains successful results without relying on iterator observation. Fresh
lead64cases pass207warnings/38.93s, including real spawned-writer SIGTERM/callback
before/after retention and exactly-once status/provenance/callback checks.
All56old cases exact; scope preserves170other paths and172freeze hashes, prior
evidence contents/explicit mutable-handoff history and9fixture hashes.

Lead raw XML corroborates covering582passed/16failed/1error (591old unchanged+
8newpasses), required45passed/16failed/1error, complete failed/error causes
unchanged.599distinct post-I1 nodes tested;1895historical full nodes unrun.
Full2015/468/2 remains pre-constructor/pre-I1 only. Fresh fix-path Ruff3existing/
noNew. Public source unchanged; strict63/publication/13unit pass,5HTMLpages equal62,
live1020/320text-only bounds pass. No image/pixel/human or extra full/benchmark
claim. Original-reviewer I1/new-fix-breakage closure is next; no Task12 commit.

## Task12 frozen handoff — independently approved

Original review plus scoped fix1 approve spec/quality; I1 closed with no new
Critical/Important/Minor finding. The earlier positional constructor issue is
corrected. No open or parked Task12 finding. Final reviewed tree:
`7add8194bd499560db0ec618395ecb6cd6cac692`.

Task13–15 consume these interfaces without redefining the frozen record contract:

- `to_runtime(raw, *, base_dir=None, launch_dir=None, overrides=None)` and
  `load_runtime(path, *, launch_dir=None, overrides=None)` preserve parsed
  authored values/omissions and original configuration/launch bases before
  resolution. Operational overrides reuse existing precedence/origins, retaining
  raw path text. Presets copy the context; no second parser/precedence system.
- `SimulationConfig.request_context` is a copied, keyword-only internal field.
  Old positional/keyword parameters/defaults/match ordering are preserved.
  Runtime-only callers explicitly lack an authored configuration/base rather
  than inventing one. No new public YAML key.
- `owned_run(root, *, overwrite, initial, request=None, provenance=None)` keeps
  the exclusive lock/yielded status API. The request is written once after
  ownership, before processing; all four records join source/alias/no-clobber/
  recognized-replacement checks. Unsafe pre-ownership guards still fail without
  creating an attempt. Old unknown artifacts/locks/partials are not reclaimed.
- `checkpoint_run(root, status, provenance=None)` persists actual/pending facts
  and UTC updated_at, not liveness. Provenance failure still attempts authoritative
  status; a failed terminal checkpoint cannot claim completed/incomplete.
  Record names/fields/path bases are frozen in task-12-record-contract.md.
- Existing `export_outputs(..., on_published=None)` invokes its optional v3
  callback only in the owning parent after atomic publication/reopened facts.
  Actual retained paths guard duplicate accounting/callback replay; graceful
  drain revisits successful results even if interrupted before retention.
  Execution recovery consumes retained descriptors. No archive scan/worker
  callback/new registry or changed scientific writer.
- Actual products stay separate from common planned descriptors. Processing/
  publication/cleanup pending phases clear only at observed boundaries.
  Known effective controls/resources/binding facts are saved early and later
  source/backend facts refreshed on failures as well as success.

Final lead64passes/207warnings/38.93s; covering582passed/16failed/1error and
required62:45passed/16failed/1error. All591pre-I1 covered outcomes plus8newpasses
are preserved, with complete causes per failed/error node.599distinct post-I1
nodes tested;1895historical full nodes unrun afterward. Full2015/468/2 remains
PRE-CONSTRUCTOR/PRE-I1 only, not a current full-suite result.
172frozen hashes,170other Python paths, original56test prefix, exact non-parent
AST/old evidence contents/explicit mutable handoff history and9input hashes are
verified. Fix-path Ruff3existing/noNew; no unrelated lint/environment repair.

Five canonical pages explain all four records, original bases, pending/actual
facts and failure/retry limits. Strict63/publication/13unit pass; five HTML pages
equal62 with text-only desktop/320bounds checked. Earlier unchanged scientific
harnesses/ordinary metadata readers remain pre-I1; fresh real-writer boundary
tests and exact unchanged numerical/encoding paths support the bounded fix.
No plot/image/pixel/human approval or extra full/benchmark.

Scientific impact: no new method/default, physical quantity/unit/basis, sampling,
mask/clock/precision/grid/coordinate schema or scientific sign-off. Compatibility:
additive request metadata/loader keywords and parent callback, stricter refusal
of unrecognized record replacement; old constructor and ordinary writer usage
remain. Sources/data and agreed C4/C6/C7/C8 safeguards are preserved.

Retained limits: status/provenance are separate atomic checkpoints, not an fsync
or cross-record/product transaction. SIGKILL/native loss may retain last-known
running/locks/partials/uncheckpointed output; Zarr replacement has its visibility
gap. No scan/repair/replay/resume or liveness inference.
Cannot-verify items map to approved later owners, not new unresolved Task12 gaps:
CLI/producers13–16, HPC18, native/warnings/full integration19, docs20, human21.
Inherited470failure/error causes and Task09Minor3 remain explicit. No source-data
write, package repair, push or merge. Commit locally before13.

## Task13 active report boundary

Base69e69923f2d827c724c03812ce248a67e08b41a2; clean tree verified after12commit.
One fresh worker owns preflight/configuration/coupled report/error integration,
with an optional narrow reports module and minimal validate JSON/existing-handler
routing. Lead owns docs/STATE/contracts/commits. No new scientific planner/parser/
service or full CLI rewrite.

Ruling: freeze C9 report_version1 and the seven-key envelope in
task-13-report-contract.md, keeping configuration/origins/inputs/plan/pending
separate and internal decoded clocks untouched. Why:14/15 need one inspectable
report contract, not ad hoc reconstructions. Cost if wrong: report/CLI consumer
rework caught by independent13review before those consumers are implemented.
Independent diagnostics retain actual facts/locations/repairs; blocked/deferred
are not passes or scientific fallback decisions.

Ruling: minimal `validate --json` and shared existing planning/effective routing
belong here to test a real stdout/nonzero/stderr contract. Full same-file inspect,
operational flags/retired options/init/capabilities/status/schema stay15; integrated
execution/progress stays14. Do not add another preflight before execution or
prematurely bind native discovery merely to populate a report.

Prior required473nodes456passed/17failed is a saved inventory, not a13run.
Composite2494uses2485pre-constructor/pre-I1 full nodes overlaid with599post-I1
covered nodes/9newpasses.1895historical full nodes retain older evidence; no
post-I1 Task12 full is invented. Task13 owes focused/covering/required and one
final full after freeze. No Task13 implementation/result is claimed by opening
the task; all12agents are idle.

Task13 implementation is frozen and lead-verified, not yet independently
approved. All174Python hashes/94old tests/178other tracked Python boundaries,
9fixture hashes and5,885prior evidence hashes plus append-only lead history match.
Fresh6path Ruff46inherited/46current/noNew. Fresh lead reports38passes/3.21s.

Raw XML independently corroborates required456passed/17failed, covering773passed/
17failed and full2062passed/468failed/2errors. All2494old full outcomes retained,
38newpasses and no old nodes unrun.470failed/error complete pairs retain causes:
428integer-v3 producer failures with typed wrapper/marks,38context/repr-only,
4runtime-only;6extra guard-wrapper context cases explicitly examined. This full
exercises all formerly mixed-age nodes without retroactively relabelling Task12's
historical runs. Inherited failures remain failures, not scientific/native clearance.

Actual3documented validate commands pass; schema-only works with inputs absent.
Strict JSON independently checks7envelope/5data keys/one document, nonzero two-source
failure with both repairs/locations/observed facts and blocked checks, stderr logs
and no outputs/source mutation. All3unchanged scientific harnesses pass4/3/6hashes.
Strict64/publication/13unit and live text-only1020/320two-page checks pass, no page
overflow/code clipping; canonical64retained, no images/pixel/human claim.
Original implementer idle; fresh independent spec/quality review and local commit
remain pending. No Task14 implementation or Task13 staging/commit yet.

After updating the retained preview pointer, current old evidence preservation
is5,884exact whole-file hashes plus exact original preview bytes and append-only
ledger prefix, not5,885current whole files. Both mutable handovers are explicit;
all174frozen hashes remain exact and no full/test/review evidence changed.

First independent13review: spec❌/qualityNeedsfixes,0Critical/4Important/0Minor.
Lead reproduces all4roots: known schema facts/marks lost to generic prose;
invalid source name discards independent model errors; one inventory failure
blocks unrelated local binding checks; required writer deps use authored rather
than effective options. These are new task gaps, not waived inherited failures.

Original implementer owns fix1/5 within existing v3 schema/required-dependency/
inventory-to-binding diagnostic boundaries and appended tests; old38cases and
scientific/record/resource controls remain frozen. Preserve valid owning metadata
for local checks without re-inventory, premature native binding or partial
execution; any failure still revokes all clearance. Actual schema facts remain
at their owner, not reverse-parsed from text or new validation rules.

Ruling: no second full/benchmark for bounded report/local-check corrections.
Existing2062/468/2full is PRE-FIX1 only; complete reports/same8covering/required473,
extra focused shared-target safety, exact source/evidence/fixture proof and
original-reviewer closure qualify changed lanes. Final19/full integration remains.
Reviewed candidate/tree and1124pre-fix artifacts preserved. No13commit/14dispatch.

Fix1 source/tests frozen; fresh lead158report/safety cases pass159warnings/
14.90s. All126report cases and32existing selected shared-target/bind-once/
clearance checks pass. Scope is3production diagnostic owners plus88appended cases;
all38old cases/662line prefix exact.174hashes/170other reviewed Python paths/
179other tracked Python paths, outer/non-target AST,1124prior artifacts/7020start
evidence contents/explicit mutable history and9fixture hashes verified.
Fresh6path HEAD/review Ruff46→42/noNew.

Raw XML independently retains790pre-fix covered outcomes plus88newpasses:
861passed/17failed, required456passed/17failed. Complete covered messages/traces
match after runtime-only normalization.1742historical full nodes remain unrun
after Fix1;2062/468/2full stays PRE-FIX1. Actual documented CLI/offline and
corrected schema/name failure checks pass with independent strict JSON readers,
no outputs/source mutation. All3unchanged scientific harnesses pass4/3/6hashes.
Strict65/publication/13unit pass/2HTMLequal64/live1020/320textbounds/code scroll.
Original reviewer findings1–4/new-fix closure pending; no13commit/14dispatch.

Fix1 original reviewer closes findings2–4; finding1 remains open only via
new ImportantN1: root required sources gets nonexistent configuration.sources
path/repair. Lead reproduces the missing/wrong nesting/valid root cases offline.
This is changed required-key code, not an untouched-validator scope expansion.
Round1result:3closed/1open,0Critical/1newImportant/0Minor; no duplicate count.

Original implementer owns round2's one missing-key path/repair construction and
one appended regression; old126cases/1230-line prefix and all closed-finding/
scientific/report/record/resource code stay exact. Reviewed75a17b79/174hashes/
1376prior artifacts preserved. Ruling: reports+four-file report/required covering
and exact required473, not another8file/full/benchmark for this narrow fix.
Earlier158safety/examples/full remain PRE-FIX2; fresh focused/CLI/scope proof,
original reviewer and final19/full retain integration risk. No13commit/14dispatch.

Fix2 frozen and lead-verified: one `_keys` root missing-key path/repair normalization
plus one appended regression; all126old cases/1230prefix exact. Fresh127report
passes4.21s; actual schema-only/JSON CLI missingroot→valid repair accepted and
nested prefix preserved, strict independent JSON/exit/no-output checks pass.
174hashes/172other Python/byte+AST/prefixes,1376prior artifacts/7268start evidence
contents/explicit histories and9fixture hashes match. Fresh6path RuffHEAD46→42/
review42→42/noNew. Raw XML corroborates covering583pass17fail/required456pass17fail,
all covered old outcomes/complete causes unchanged; one new Fix2 case separate.
279Fix1-covered/2021historicalfull nodes remain unrun; full2062/468/2PRE-FIX1/
PRE-FIX2only. No broader integration/harness/full/benchmark rerun.
Strict66/publication/13unit pass/2HTMLequal65/live1020/320text bounds/code-scroll.
N1/finding1 and new-fix-only original-reviewer closure next;2–4stayclosed.
No13commit/14dispatch or image/pixel/human claim.

## Task13 frozen handoff — independently approved

Original review and two scoped fix rounds approve spec/quality. Findings1–4
closed, including N1's root-repair correction; no new Critical/Important/Minor
finding, no open or parked Task13 issue. Final reviewed tree:
`3125fe12d847fc0f55cab9bf5ad57f3ffd384806`.

Tasks14/15 consume these existing-producer interfaces:

```python
collect_preflight(request, *, command="validate", schema_only=False,
                  check_output=True, execution_options=None, resources=None)
preflight_result(conf, facts, *, command="validate")
```

Both return `core.reports.PreflightResult`; the first accepts YAML path/mapping/
existing config, the second wraps the already-produced typed facts by identity.
**Execution/progress must wrap its existing owning prepared_sources[0] with
command="run"; do not call collect_preflight again, re-inventory, rebind or feed
the serialized view back into execution.** Native discovery remains unbound;
selected polar metadata planning retains its original method/budget/clearance rules.

`core.reports` exposes Diagnostic, PreflightError(ValueError), PreflightResult,
project_report, serialize_report and render_report. The version1seven-key C9
envelope and five separate data sections are frozen in task-13-report-contract.md.
Projection copies metadata/labels calendars/bounds large coordinate descriptions,
without mutating internal decoded times or computing scientific arrays.
Authored context stays in Task12 records; YAML marks are private
simulation_parameter["_yaml_locations"], not new run-request fields.

Known owned schema checks retain actual rule/value/path/repair and same-text
marks; root display labels are not invented YAML paths. Source names collect
independently, preserving the existing identifier rule. Genuine repeats group
only equal causes while retaining affected contexts. Unavailable prerequisites
are blocked; unfinished selection/runtime checks remain explicitly pending.
No invalid report provides execution clearance or partial effective controls.

Explicit binding retains valid owning metadata through inventory errors only
for independent local checks, without a second inventory. Its private error
handoff is not a public plan or replay interface. All failures revoke parent/
child/shared-target clearance; cross-source geometry/product checks stay blocked.
Ordinary discovery still raises without binding. Selected dependency checks use
effective writer options and preserve disabled-export isolation; module/version
presence is not backend initialization or a new engine/format execution promise.

Minimal validate --json and existing planning/effective routing share this result.
Actual stdout is one JSON document/errors nonzero/logs stderr; human rendering
shares useful facts/repairs. Complete same-file inspect, retired flags, init/
capabilities/status/editor-schema/operational flags remain15; progress14.

Final fresh lead127reports pass4.21s. Fix2 covering583passed/17failed and required
456passed/17failed retain all covered old statuses/complete causes plus1new Fix2
case. Prior Fix1 covering861/17/158safety and scientific harness4/3/6hash evidence
are PRE-FIX2, supported by exact unchanged-code proof, not fresh execution.
279Fix1-covered/2021historical full nodes remain unrun after Fix2.
Full2062/468/2 is PRE-FIX1/PRE-FIX2 only; no corrected-source full is claimed.

174frozen hashes/172other Python paths, exact non-missing-branch AST/bytes,
old126case prefix/report/check/evidence histories/1376prior artifacts/7268start
entries and9fixture hashes verified. Fresh6path RuffHEAD46→42/review42→42/noNew,
not clean lint. All old producers/tests/scientific assertions remain intact.
Actual final root/nested CLI repair checks pass with independent strict JSON.
Two canonical pages document commands/report/errors; strict66/publication/13unit
and text-only desktop/320bounds pass, both HTML pages equal65. Preview retained;
no screenshot/image/pixel/human acceptance or extra full/benchmark/harness run.

Scientific impact: none; no method/default, quantity/unit/basis, time/mask/
precision/read/selection/grid/schema or scientific sign-off. Compatibility:
additive versioned JSON/typed diagnostics, intentional human/error-text changes,
same scientific API/record/output contracts; no YAML migration or dependency.
Remaining cannot-verify/later gates retain owners: actual integrated progress14,
complete CLI/producers15–16, HPC18, native/warnings/full integration19, docs20,
human21. Inherited470full failed/error causes and Task09Minor3 remain explicit,
not waived. No source-data write, package repair, push or merge. Commit before14.

## Task14 active execution/progress scope

Base106812d83d0ace0a0930c52409c43b3bbd1d9f32; clean tree verified after13commit.
One fresh worker owns runner/execution/coupled/logging boundaries and necessary
existing writer hooks; lead owns docs/STATE/contracts/commits. No new event
framework, dependency, scientific planner or progress controls.

Ruling: use existing timing/logging plus one small owned quiet-work reporter.
Boundary-only logs miss blocked/quiet synchronous work; an event bus/worker
telemetry service exceeds the task. Cost if wrong: lifecycle/logging integration
rework, covered by deterministic/real gated tests and independent14review.
Technical contract task-14-progress-contract.md distinguishes lazy preparation,
actual compute/write/publication, honest counts/elapsed/last-real-activity and
pending cleanup/records. No extra reads/compute/graph scans, percentages/ETAs,
status heartbeat or premature final success. Reporter stops before handlers close.
Provisional30second quiet interval follows existing matrix precedent;14must
freeze actual interval/API from bounded evidence, not invent approval.

Execution wraps the existing owning prepared facts via Task13 preflight_result,
never recollects/rebinds/serializes a scientific plan. Preserve pre-ownership
safety and Task12 authoritative inventory/draining/capture/record semantics.
Actual final state, not scheduled futures or prepared arrays, governs completion.

Required prior81nodes61passed/19failed/1error is saved inventory, not a14run.
Composite2621nodes is mixed-age:600Fix2-covered/279Fix1-only/1742pre-fix-full-only;
no final corrected13full exists,2021historical full nodes unrun afterFix2.
Task14 owes focused/covering/required and one full after genuine freeze.
No Task14 implementation or results implied by opening the task; all13agents idle.

Task14 author reports frozen source/tests and30sinterval, focused67passes and
required67passed/19failed/1error, retaining all81old outcomes plus6new cases.
These are author claims awaiting lead corroboration/review. Its full has not
yet run; scope question concerns the two unchanged PNG-generating script tests.

Ruling: retain those ordinary script/PNG-signature/overwrite/source-safety smoke
tests in the already-required one unfiltered diagnostic, as explicitly recorded
for13. They use disposable fixtures and do not inspect pixels or establish visual
acceptance. No standalone plot run, screenshots/JPEG/image viewing or new asset/
check is authorized. Do not silently filter an "unfiltered" suite.
Exact scope/rationale: task-14-full-ruling.md in the session ledger workspace.
No source/test edit after freeze, package/native repair, second full or commit.
Lead verification and independent14review remain pending.

Lead frozen checks:67passed/213warnings/2subtests/46.89s; all175source/test hashes
match.179other tracked Python paths, old483-line/26case execution prefix,
scientific processing/export/result AST, writer callbacks,2430immutable root
artifacts and9payload/all12fixture-entry hashes unchanged; Ruff noNew.
Three unchanged scalar/vector/polar harnesses pass4/3/6source hashes and ordinary
readers. Four independent YAML/log checks match terminal counts/state to actual
status/provenance/request products, no pending work or stale lock.

Lead raw scoped XML checks637pass19fail1error covering/67pass19fail1error required:
619old+38new/81old+6new respectively. Every20failed/error raw pair retains complete
exception lines/message/call-site paths;15expanded --tb=long contexts and5runtime-
only pairs explicit. First whole-trace-equality proof failure retained, not a
test regression or waived cause. Full outcome still author-owned/pending.

Strict67/publication/13unit and live text-only1020/320storage/HPC checks pass;
canonical67retained. Exact original66preview bytes saved before pointer update;
mutable lead histories explicitly accounted, no old full/test/review rewrite.
No source/test/plot/image/package change or scientific/native/HPC/human approval.
Fresh independent14review still required before commit/Task15.

Task14 author full is complete:2189passed/468failed/2errors/6570warnings/4subtests/
583.64s, all2621prior statuses/38newpasses; complete causes preserved per author
and awaiting lead raw audit. Frozen175hashes/7447pre-full artifacts still exact.
Author found A1 before review: callback-entry interruption leaves2actual retained
products/status/provenance but terminal progress says1. Lead independently
reproduces the original passing retention test and the new counter mismatch.
This is new Task14 debt, not an inherited cause or independent-review finding.

Ruling: thaw only progress-counter reconciliation in execution/private helper
plus appended progress tests. Writer retention/draining/callback order/records
and all scientific controls remain exact. Preserve PRE-A1 full/freeze/evidence;
175hashes/536progress-test prefix/1148Task14 artifacts copied before thaw.
TDD then progress/execution/logging/run_state plus exact required command,
per-covered causes/unrun full IDs/exact non-target proof and independent14review.
No second full/harness/benchmark for scalar reconciliation;2189/468/2is PRE-A1
only. Missed integration risk remains with exact scope and final19/full gate.
No14commit/15dispatch; original worker resumes A1, lead owns full audit/docs.

Lead full raw audit corroborates all2659nodes/all2621old outcomes/38newpasses and
all470complete raw cause pairs:197runtime-only,272same complete exception/call-site
paths with context/repr,1explicit truncated scratch187/227substitution yielding
whole message/trace equality. Automatic flag/raw pairs preserved; no cause or
numerical assertion waived.175pre-A1snapshot/7447pre-full hashes verified.
Full2189/468/2remains PRE-A1; A1 author correction and independent14review pending.

A1 corrected/refrozen; fresh lead78progress/execution/logging passes253warnings/
2subtests58.27s. Eleven new cases cover both formats/four retention boundaries,
successful non-double-counting and scalar idempotence/activity preservation.
Production delta from PRE-A1 is six counter-only lines;172other Python paths,
old536progress lines/other tests, writer/records/scientific code byte/AST exact.
175corrected hashes/7447pre-full1146Task14 immutable artifacts/explicit histories/
9payload12fixture proof passes; actual HEAD/PRE-A1 Ruff4→4/noNew.
Raw XML corroborates142module passes/67pass19fail1error required:194distinct
corrected nodes,183old statuses/20complete causes unchanged plus11newpasses.
2476full nodes unrun corrected;2189/468/2full and scientific harnesses PRE-A1 only.
Strict68/publication/13unit pass/2HTMLequal live67; canonical67retained without
new image/DOM/human claim. Whole-Task14 independent spec/quality review next;
no14commit/15dispatch.

## Task14 frozen handoff — independently approved

Fresh reviewer approves complete Task14 spec/quality,0Critical/Important/Minor.
A1 was corrected before review and is closed; no open or parked Task14 finding.
Approved tree0114028b1e17632057cbbb560255ae8532ac77bc. Completion is task-scoped,
not a green full suite or scientific/native/HPC/human sign-off.

Public execute_simulation and FrameitRunner signatures and execution-result/
Task12 record serialization remain unchanged. Execution wraps its already-owned
prepared_sources[0] via preflight_result(conf, facts, command="run") once.
runner.preflight_result retains that typed result; prepared tuple/facts/children/
bindings retain identity. Task15 must not collect/bind again or execute a report
projection. No large scientific plan is added to results or portable records.

Private _QuietProgress lives in existing utils/logging.py:

```python
_QuietProgress(logger, *, interval=30., clock=time.monotonic)
update(operation, *, source=None, prepared_sources=0,
       tracking_operations=0, published_products=0)
reconcile_published(count)
start()
stop()
finish(state)
```

Updates add observed preparation/tracking/publication counts and real activity.
Reconciliation sets the actual retained publication total under the scalar lock,
without callback replay, emission or new activity. It runs after export/drain/
recovery before cleanup/terminal reporting. Writer retention/draining and records
remain authoritative and unchanged. Task15 summaries must use actual products,
not infer them from a progress line or scheduled work.

One passive parent thread,30srate limit, shared deadline across logging transition,
no thread at INFO-disabled levels. Early frameit_logging_scope(None, ...) owns
stderr only/no paths; owned file scope remains alive through cleanup and final
record/ownership exit. Stop/join precedes handler close. Final complete/incomplete/
failed/interrupted notice follows those owning exits; primary processing errors
survive added progress/cleanup faults. No payload/graph/future/directory scans,
status heartbeat, percentages or ETA. Unknown spawned source stays unknown.

Latest lead78passes/253warnings/2subtests58.27s on corrected source. Author full
four modules142passes and exact required67passed/19failed/1error; raw XML confirms
194distinct corrected nodes,183old outcomes/20complete causes unchanged plus11
A1 passes. The one full2189passed/468failed/2errors is strictly PRE-A1.
2476full nodes remain unrun after A1; every ID/historical status is recorded.
PRE-A1 full raw audit confirms all2621prior outcomes/38then-new passes/470causes.
No second full/harness/benchmark; final19/full remains required.

175corrected hashes/172other package Python paths, production outside six A1
lines/old536progress prefix/writer records/scientific code,7447pre-full/1146Task14
immutable artifacts/explicit report-history prefixes/9payload12fixture proof pass.
No added Ruff findings; inherited warnings/diagnostics retained. Three unchanged
scientific harnesses/ordinary readers remain PRE-A1, with exact counter-only scope,
not fresh corrected-source scientific qualification.

Storage/HPC prose documents actual progress and limits. Strict68/publication/
13unit pass; affected HTML equals checked67. Same67preview retained with prior
text-only1020/320inspection; no new image/DOM/human claim.
Scientific impact: none. Compatibility: intentional progress wording/correct
terminal counts, no scientific/output/configuration/schema/dependency change.

Cannot-verify notes are retained limits, not new unresolved Task14 requirements:
hard native/GIL/log-I/O timing and SIGKILL finalization are not promised; existing
Task12 record-write failure/transaction behavior is unchanged; inherited failures/
ABI warnings remain19debt. CLI/producers15–16, HPC18, native/warnings/integration19,
docs20/human21/Task09Minor3 retain named owners. Human acceptance is not invented.
Local commit precedes15; no source data/package changes, push or merge.

## Task15 active CLI boundary

Basebde826b31957e67808f6219e175d3f960d7fd85e; clean tree verified after14commit.
One fresh worker owns CLI/configuration/templates/editor asset and bounded
presentation/read-only status additions; lead owns public prose/contracts/
STATE/commits. Task13 reports,14one-owning execution/progress and12portable records
are consumed, not replaced by a new planner/workflow or science/runtime changes.

Ruling: status spelling `frameit status <run-directory>`, exits0for recorded
completed/accepted-incomplete,1for unfinished/failed/interrupted or unreadable
records,2for syntax errors. This follows actual12acceptance states; running is
not a liveness observation. Ordinary metadata/status/final summary never requires
the archive, payload scans or claims that stale/concurrent records are current.
Cost if wrong: CLI contract rework before15review, not scientific default change.
Exact common flags/JSON/authored-versus-effective behavior and status policy:
task-15-cli-contract.md. Existing non-retired operational run controls remain;
explicit dry-run/resolved retire, no new scientific-selection flags/aliases.

Generate packaged schemas/config-v3.schema.json from authoritative definitions,
not another validator/registry or input-specific field list. Preserve all init
workflows/quantities/safety/comments in v3; report scientific conflicts explicitly.
jsonschema is unavailable; build/setuptools/wheel are already present. No new
dependency/environment/package install. Actual definition/asset/wheel inclusion
checks proceed; independent standards-conformance validation stays an explicit
missing check unless available evidence genuinely establishes it.

Prior inventory540required=484passed/55failed/1error,2670mixed-age total=
194post-A1/2476PRE-A1. Not a15run or corrected14full. Task15 owes focused/
covering/required and one full after genuine freeze; source/evidence protections
and the existing no-separate-image/full-smoke boundary remain.
No Task15 implementation/result is claimed by opening the task.

Task15 author blocked/not frozen:120focused passes/1publication-suppression failure,
wheel asset/identity/proof claims saved; covering/required/full not yet run.
Lead independently reproduces suppressionfalse→actualmodel-grid output and a
real owned CLI failure retaining one ordinary-reader-verified product whose
current summary lacks inventory. Current unowned fallback is safe but insufficient
for known owned partial failure. All export/ownership/count callers traced.

Ruling B1: permit only v3 writer local-publication filtering by existing export
flags and safe empty selection, retaining requested track/plan/science/encodings/
retention-before-callback/dedup/drain semantics. B2: permit compact in-memory
owner-attested failure facts from yielded ownership after unwind; no disk-based
ownership guesses, public result/record change or new event/status framework.
Pre-ownership failures remain inventory-unavailable; finalization failure must
not print success or promise a checkpoint that did not persist.
176pre-extension source hashes/111Task15 artifacts and original code/test/report
copies preserved. Exact TDD/non-target/safety proofs, covering including relevant
writer callers, required540/freeze/one full/review remain. Cost if wrong: bounded
rework before review, not changed physics or weakened data safety. No15commit/
review yet; independent JSON Schema conformance remains unavailable.

Task15 source/tests/assets genuinely frozen; author single full is running,
not a result yet. Lead fresh146focused passes/60warnings/21.58s.188freeze hashes,
352outside tracked paths/45expanded old config ASTs,8704immutable old artifacts/
explicit histories/9payload12fixture checks pass; actual-path Ruff49→36/noNew.
Pyproject only adds schema package-data, no dependency/version/environment change.

All9exact first-run commands and original5×5values/mask/units/times/CF geography
pass independent ordinary readers; one actual atmosphere.model_grid product/
no track/source/request unchanged.28CLI commands verify same-file views, strict
seven-key JSON/raw authored mapping, path/origin precedence, retired/conflicting
flags, status/schema-only with input absent and both independent repairable causes.
Actual B1suppression/B2partial-owned-failure facts verified without stale-root
guess or false persistence claim. Initial human warning-wrap probe assertion is
retained; whitespace-only proof correction, no source/test fix.

Lead raw scoped XML corroborates530/9/1required540IDs/46starter recoveries/56pairs;
cover1012/20/1old961+new72/46recoveries/one retired-handler new failure/67pairs.
Three cause changes match explicit C9argparse retirement. First proof's XML-only
guard assumption retained:9guard traces in XML,37in original captured full-log
sections, all46roots corroborated. No numerical/HPC waiver or full outcome claim.

Existing pre-boundary wheel asset bytes/isolated resource match frozen schema,
not final-code wheel execution; independent conformance still unavailable.
Strict69/publication/13unit/all12changed pages live text-only1020/320pass;
canonical69retained, original67preview saved exactly. No images/pixel/human
claim. Author full/cause audit then fresh15spec+quality review/commit remain.

Task15 full handover received/read through281. Single frozen diagnostic:
2316passed/424failed/2errors6669warnings4subtests608.79s/exit1. All2742nodes:
2670prior+72newpasses/no prior unrun. Lead independently checks every472raw
before/after pair and470before/426after complete captured sections against
original XML/logs.46starter recoveries and2old-pass→failure C9CLI rejections:
planning handler and FA directory-inspection/privacy caller. Their scientific/
privacy assertions remain unexecuted, not waived or qualified.

404retained causes:360whole runtime-normalized/43complete exceptions+callsites/
1exact truncated scratch227→267pair.20same-status changed roots:4dry-run,
2old starter-version assertions,9coupled raw.input.sources consumers,1quick-start
input consumer,1unselected FA-backend lookup,2old directory inspectors and1MNH
root-input/caplog consumer with full stdout diagnostic/location/repair/blocked
plan. Original producer/FA/test bytes intact; Task16 owns conversion.
Both existing PNG smoke tests pass only inside this full; no image review.

Lead proof assumptions about imported setup-fixture path and Python quote style
failed, preserved, and corrected with exact observed evidence; no code/test/result
fix followed. Fresh188freeze/352outside/8704immutable/45configAST/9payload12fixture/
noNewRuff proofs pass. Existing strict69/live12page checks and real commands remain
lead-accepted, not human approval. Conformance unavailable and asset-only wheel
limits explicit. Source/tests/assets frozen/authoridle/HEADbde826b/indexempty;
complete15diff packaging/fresh independent spec+quality review next, no commit16.

Task15 independent review returns spec❌/qualityNeedsfixes:2Important,0Critical/
Minor. F1editor's scalar default branch emits string constraints for the two
numeric pressure-wind widths; F2authored JSON fails on accepted YAML annotation
dates. Lead verifies both against actual callers/validators/projection and fresh
in-memory CLI probes. These are real Task15 gaps, not unavailable-validator debt.

Fix1/5: thaw only configuration_schema float branch/generated asset, authored
JSON use of existing _metadata_view, appended CLI regressions and the lead's
small canonical convention paragraph. No runtime/scientific/default/record/
progress/writer/template change.188pre-fix hashes/34reviewed paths/2365Task15
artifacts and14source/test/asset/history copies saved before thaw.
TDD/four complete CLI-template-config-report modules, new wheel asset check,
exact non-target/prefix/evidence/fixture/no-new-Ruff proof and scoped re-review.
No second full/old540/1033covering/harness/benchmark for two presentation fixes;
2316/424/2full and530/9/1required now PRE-fix1 only. Integration risk remains with
exact unchanged-code proof/fresh covering/reviewer and final19/full gate.
No15commit16dispatch. Independent conformance and human acceptance remain absent.

Fix1 corrected/refrozen. Fresh lead155passes/60warnings21.27s; all9new width/
annotation regressions included. Raw covering607pass1oldfail:599old statuses/
complete argparse cause unchanged,9newpasses,2143old full IDs unrun corrected.
All9TDD RED→GREEN IDs verified. Full2316/424/2andrequired530/9/1PRE-fix1 only.
Only two production substitutions/two-property asset delta/82test-line append.
188newhashes/184other/774prefix/352outside/2365+8704evidence/9payload12fixture
exact; Ruff49→36/36→36/noNew. Three actual authored JSON/YAML/offline commands
and new wheel ZIP/resource check match corrected conventions/asset. No install/
conformance claim. Strict70/publication13unit/config live1020/320pass;11other
pages equal checked69. Same70preview retained/exactoldcopy/no images.
Authoridle/source-tests-assetsfrozen/HEADbde826b/indexempty; scoped review next.
BothImportantopen until reviewer closure; no15commit16implementation.

## Task15 frozen handoff — independently approved after fix1

Original complete34file review and scoped8file fix1review together approve the
Task15 specification and quality. Both Important findings closed;0open/parked/
new findings. Reviewed final treec3765d530bc86f69f6a75de8491dc5ad7b274827.
Completion is task-scoped, not a green full suite, scientific qualification,
installed-wheel/native/HPC acceptance or human sign-off.

Consumers16–19 use the same authored YAML for inspect/validate/run. Task13's
shared collector/report and Task14's one owning execution remain authoritative.
No extra collect/bind to print summaries; no presentation plan executed.
Authored config show retains the raw mapping/no defaults; its JSON uses existing
metadata projection for YAML-native annotations. Authored YAML remains unchanged.
Effective JSON keeps the version1seven-key envelope and separate configuration/
origins/inputs/plan/pending sections. Logs/progress go to stderr; errors nonzero.
Common operational flags/precedence/path bases and early request capture remain
as documented. Retired dry-run/resolved and directory-inspector flags stay retired.
No public compatibility converter or scientific-selection CLI is introduced.

write_template(name, path, *, tracking=None, coupling=None, force=False)
retains model/named/composed/default/force/no-clobber/source-safety behavior.
All74starter scenarios preserve quantities/levels/widths/basis/comments in v3.
Public atmosphere/ocean/surface examples do not restrict arbitrary parser IDs.
configuration_schema() generates schemas/config-v3.schema.json from shared
definitions; capabilities() reports actual support/dependencies/maturity/limits.
Corrected schema SHA256:
6b9f8b00f094eeb15f9c6fe43eede3940dd71da8cbf7cabb193a03e412fbac36.
Both numeric pressure-wind widths match existing positive-number runtime
controls/defaults; no scientific value, unit or eligibility change.

`frameit status <run-directory>` uses fixed portable records only:
completed/accepted-incomplete exit0; running/failed/interrupted/unreadable
required records exit1; argument syntax exit2. Actual publications and plans
are distinct. Running is not liveness; no archive/payload-integrity scan.
Available recorded warnings are shown; absent optional warnings stay unknown,
not a claim that none occurred. Current successful/B2failure summaries use known
plan warnings. Preservation of every execution warning remains unestablished
recording/Task19qualification debt, not an invented status fact.

B1 filters only the writer-local publication list by existing suppression flags,
retaining independently requested track and handling an empty list safely.
Plans/scientific work/encoding/retention-before-callback/dedup/drain stay exact.
B2attaches compact private _frameit_failure only after this invocation's yielded
owner unwinds; unowned failure inventory stays unavailable. No stale/concurrent
disk attribution, changed public result/record schema or persistence guarantee.
Task12writing/ownership and Task14/A1progress lifetimes remain unchanged.

Latest corrected lead155CLI/template passes/60warnings21.27s. Four complete
modules607passed/1unchanged legacy CLI failure:599old outcomes/complete cause
exact plus9newpasses;2143full IDs unrun corrected, each historical status listed.
One full2316passed/424failed/2errors6669warnings/4subtests608.79s and required
530passed/9failed/1error are PRE-fix1 only. Their all2742nodes/472raw pairs/
470before426after complete captured sections have a lead audit.46starter
recoveries/2new rejected old callers/20same-status root changes are explicit;
unreached scientific/privacy assertions are not passed or waived. Task16 must
restore those scenarios with current v3 producers without weakening guards.

188corrected hashes/184non-target paths/old774CLI-test lines, exact other
AST/bytes after two substitutions/two-property asset delta,352outside paths,
2365+8704immutable evidence with explicit history copies,9payload12fixture
and no new HEAD/review-tree Ruff findings pass. This is not clean lint/native.
New wheel ZIP/isolated resource matches the corrected asset without installation.
Independent JSON Schema standards conformance and installed-wheel execution
remain missing qualification checks; Task19 retains the affected gates.

Strict70/publication/13unit and configuration live text-only1020/320pass;
other11affected HTML pages equal checked69. Same70preview/tab/server/restart
retained; no screenshot/image/pixel or human acceptance. The old first-run
scientific readbacks remain PRE-fix1, with exact unchanged scientific scope.
Scientific impact:none. Compatibility:intentional approved v3 CLI/starters/
editor/status plus actual suppression and private failure facts; no scientific/
output/record-schema/dependency/environment change. Local commit precedes16.
Producer16/tutorial17/HPC18/native-integration19/docs20/human21/Task09Minor3
retain named gates. No push or merge.

## Task16 active producer/example boundary

Base40f9bcdb4429fe1755aab871c2b7f9d5916af51e; clean tree verified after15commit.
Fresh sole worker owns testing producers/catalogues/recipes, canonical YAML and
plot consumers, static reference YAML and affected tests/caller conversion.
Lead owns README/published prose/STATE/contract/commits. No runtime/reader/
scientific/writer/ownership/progress changes without a concrete authorized
boundary. Shared helper signatures and scientific/privacy/safety assertions stay.
Convert directly to3; no public v2 converter or second planner.

Actual-descriptor checker/per-product source clocks/optional trajectory and the
two named real execution/checker/one-small-benchmark tests are required.
Catalogue1/artifact1.0/report-record1/FA/package versions remain distinct.
Exact first-run/quick-start outputs/independent readbacks and canonical guidance
must agree. Both Task15newly rejected callers and20changed-root scenarios need
restoration without weakening their unexecuted scientific/privacy guards.
The remaining red-suite causes also retain their actual identities/dispositions.

Prior inventory2751nodes:608post-fix1/2143PRE-fix1,2325passed424failed2errors;
required264IDs=150passed113failed1error. Not a16run or corrected15full.
Task16 owes focused/caller-covering/exact required then one full after genuine
freeze and independent task-walkthrough review. No benchmark campaign/download/
installation/environment repair. Existing PNGsmokes stay inside required
unfiltered suites only; no standalone plotting/image/screenshot/pixel review.
Canonical70is prior checked preview until new commands/strictdocs/text-GUI checks.
Scientific conflicts must be surfaced, not settled by substituting quantities/
units/bases/masks/times.17tutorials/18HPC/19integration-native/20docs/21human gates
and independent schema conformance/installed-wheel limits remain.
task-16-producer-contract.md records the consumer boundary; no16result claimed.

Task16 worker reports a real C3conflict before implementation: existing AROME
catalogue requests distinct u/v identities on pressure/height/PV grids and
different per-group level strategies. Frozen C3 forbids ambiguous/qualified
names and permits one selector per source; C1forbids two atmospheric sources.
Lead reads128report lines/catalogue/C3 and independently reproduces the three
intended rejections.12fixture/9payload hashes exact/no output/source edit.
The244path/3983assertion preservation and2passing guard tests are bounded
blocker evidence, not implementation or scientific qualification.

No data/fields/levels/cases or guard is silently changed. Maintainer disposition
is requested: retain C3and explicitly accept unsupported catalogue coverage, or
authorize a separately designed/reviewed selector-level contract revision.
Until decided, do not invent an unsupported-case representation, preprocessing
workaround, qualified selector or false success. AROME adaptation/Task16closure
and affected later qualification remain blocked.

Ruling: same worker continues independent Meso-NH/synthetic/shared-helper/
actual-checker/one-small-benchmark and unaffected example/caller units under
the original safeguards. Do not replace an AROME case with those passing cases.
No Task16freeze/full/review/completion while the disposition is open; the one
post-freeze full remains unused. Cost: bounded rework, not changed science/data.
task-16-independent-work-ruling.md records the temporary scope.

### 2026-11-16 — maintainer-approved C3 revision

The maintainer approved the optional grouped-request approach: “Perfect lets do
that revised version then”. Keep flat `variables.3d` lists and source-wide
`variables.levels` for simple requests. Add explicit vertical groups with `names`
and local `levels` for requests needing field disambiguation or different level
selections. Grouped requests cannot also set source-wide levels.

Qualification is required whenever a requested name denotes distinct fields in
the selected inventory, including when only one of them is wanted. Unrequested
ambiguous names do not matter. Repeated timestamps or levels of one field are
not name ambiguity. A qualified group must still identify exactly one field.
This approval changes request expressiveness, not quantities, original catalogue
levels, clocks, bases, masks, scientific methods or validation standards.

This supersedes the temporary prohibition on designing/implementing that C3
extension above and in `task-16-independent-work-ruling.md`. It does not authorize
the three separately reported NetCDF/CROCO fixes, environment changes, fixture
filtering/relabeling, source splitting or weakened assertions. Task16 remains
unfinished; its post-freeze full diagnostic is unused.

Before core edits, the lead preserved all29 existing changed files, their hashes
and the tracked binary diff in the ignored `task-16-c3-approved-baseline/`.
HEAD remains40f9bcd and the index is untouched. `frameit_env` is Python3.13.18;
the explicit source import selects this worktree. The lead owns C3 design,
configuration/binding integration and its tests/docs. A read-only exploration
agent traces downstream identity propagation; it owns no implementation files.
No fresh C3 result, freeze, review or completion is claimed.

### C3 implementation candidate and verification

The bounded extension now has39new cases. Fresh final grouped/schema-asset
acceptance:40passed/35existing backend warnings in26.85s. A current four-scope
reader/binding command passed143nodes/35warnings in48.63s. The14-module
covering run returned1190passed/53failed; one new closed-inventory lookup-order
regression was observed and fixed, then verified by the143-node command.
Merged evidence covers1243IDs=1191passed/52failed, with no old status changes
against the available mixed-age/partial inventory. The52old caller failures
remain real failures, assigned to unfinished Task16 conversion, not waived.
Exact commands, failure IDs and limitations: `c3-grouped-requests-checks.md`
and the ignored `task-16-c3-*` evidence. An earlier covering attempt timed out
at120seconds/58% and has no completed result. No Task16 full was consumed.

All16partial Task16 source/example/test files remain byte-exact against the
pre-C3 snapshot. Native fixture files were not changed. Only UTrack prose and
its publication-unit assertion are brought forward from Task16: required checks
exposed its draft table indentation and old wrapper assertion. Its existing
v3 execution gate and declaration values are preserved.

Ruling: unequal group selections on the same transformed output axis fail in
metadata preflight. C7 does not authorize padding, implicit alignment or a new
axis-alias scheme. Matching selections/separate runs remain necessary for that
combination; native mixed-axis AROME is unaffected. This is a technical limit,
not human scientific approval or permission to alter requested levels.

Strict Sphinx04/publication04 and13publication unittests pass. Ruff on the10
changed Python files is36baseline/35current/zeroNew, not whole-repository clean.
The editor asset equals the authoritative generator; its SHA-256 is
`319a6aa028ef68b7517040bea72aeee99a08e923b5cf697231cb156a8450cd24`.
Live text-only GUI inspection and fresh independent review remain pending.
No push/merge, environment change, standalone plot/image check, native/HPC/
installed-wheel/standards-conformance or human acceptance is claimed.

### C3 independent review — fixes required

Reviewer `ses_e1d31d5edffe5NSLDKoqFNOp6A` independently checked the frozen25paths
at tree7c489ffe607551077ae71e5af47130381faca1ca, all16preserved partial Task16
files and bounded reproductions. Verdict: **SPEC ISSUES / QUALITY NEEDS FIXES**;
four Important findings, no Critical or Minor findings. Complete report:
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-c3-review-02.md`.

The lead accepts the four verified boundaries for correction: compare actual C7
vertical-axis identity across horizontal grids; distinguish generated tracker
support from duplicate authored aliases; resolve native CROCO quantity names at
the admitted current-preparation boundary; and preserve C9 errors for forbidden
FA local physical-domain selectors. Each needs a failing regression and scoped
review closure. No guards, masks, clocks, levels or scientific methods may be
weakened. The frozen tree/evidence stay intact; no commit or clearance is granted.

A separate read-only diagnosis of the three older NetCDF/CROCO reports is active
in `ses_e1d2b3c19ffeeCxGc44mDEo44S`. It has no implementation authorization and
must not be confused with the grouped-path CROCO review finding.

### C3 review fix1 — bounded corrections, closure pending

All four findings have failing regression evidence and a bounded candidate fix.
FA selector rejection now uses the actual local path/selector, retaining the
flat diagnostic and the scientific gate. Its2CLI/schema controls plus10existing
FA admission cases pass. The shared-axis guard reuses C7 exported axis identity,
including differing horizontal grids;4W controls plus2native/GRIB binding cases
pass. Generated support may reuse a field identity only when not authored;
the2tracker controls and unchanged native-centroid execution case pass, with
duplicate authored aliases still rejected.

Qualified CROCO inputs now pass the same native-name quantity checks and are
renamed only across the existing current-preparation boundary, then restored.
The new grouped end-to-end and unchanged flat counterpart both pass, retaining
selected time/level reads, masks, exact native source bytes, rho rotation and
ordinary-reader metadata. No interpolation, masking, tolerance or strict merge
change. Connected verification and the same reviewer's scoped closure remain
pending; this is not a C3 freeze or a Task16 full-suite result.

The separate diagnosis has arrived:
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-three-core-independent-diagnosis.md`.
It confirms three latent frozen-v3 defects, not scientific acceptance: NetCDF
record inventory drops existing GRIB_stepType evidence; independently cropped
CROCO face fields retain perpendicular full-rho support under the same C7 axis;
and equal transformed/native index values differ in generated long_name metadata.
Each correction boundary still requires separate authorization. CROCO support
ownership/representation has a public-schema decision; no support names, crop
indices or formula links are changed here. The diagnosis's baseline byte checks
precede the bounded C3 canonical/native preparation change above.

Fresh connected fix1 command:986passed/1509warnings in223.11s, including all46
grouped cases, all current v3 configuration/CLI/report/operation/polar/output/
reader modules and named flat-centroid/CROCO scientific guards. This is a named
subset, not the unused Task16 full diagnostic. Earlier52old failed callers remain
recorded, not waived. Exact command/result: `c3-grouped-requests-checks.md`.

Strict Sphinx05/publication05/13units pass; seven affected pages refreshed in the
live GUI at1020/320CSS widths with no page overflow or inaccessible code edge.
Ruff11Python paths:36baseline/35current/zeroNew. The16partial Task16 files remain
byte-exact. Excluded core boundaries are verified unchanged; only canonical/native
preparation in `derived/wind.py` differs. Scoped review closure and local commit
are still pending.

Lead self-review additionally reproduced an operation-authorship subcase of
finding2: raw and qualified inputs to one authored calculation were projected
as generated support. Preserving those input names in the operation subrequest
restores duplicate-identity rejection without restricting genuine tracker support.
The986-node result precedes this last tightening; the subsequent affected-path
command passed251tests/1136warnings in117.10s, including all47grouped cases.
Fresh Ruff remains36baseline/35current/zeroNew. No new scientific choice or core
authorization. Scoped review closure remains required.

### Maintainer decision — two metadata repairs approved

C3 was committed locally as9847bd618c3cd937ca447ec9d4c47afa73b88b5b, exactly
approved tree963560dd0e3d1d595b257dc782001de570520869. Its original independent
review plus fix1closure are complete:4addressed/0open/0parked/0new. Final
precommit48passed; Sphinx06/publication06/13units passed and affected HTML was
byte-exact to the retained live-reviewed05pages. No push/merge.

After requesting a plain explanation and explicitly pausing, the maintainer
answered “Yes” to fixing (1) lost NetCDF instantaneous evidence and (2) mismatched
generated native-index metadata, then presenting (3) a CROCO support-layout
proposal before implementing it. This supersedes the earlier no-authorization
ruling for those two metadata boundaries only. It does not approve cropping,
support naming, changed samples/methods, relaxed time guards or non-strict merges.
The previously chosen inline/review-before-commit workflow remains; no repeated
routine approval round is needed for these explicitly described repairs.

Current HEAD9847bd6/index empty; all25pre-existing dirty paths and binary diff
saved in `task-16-metadata-approved-baseline/`. Python3.13.18/worktree import
freshly confirmed. Exact bounded plan: `task-16-metadata-fixes-plan.md`.
The third issue remains proposal-only. Task16's post-freeze full is still unused.

### Approved metadata candidate — verification before review

The time repair is one observed metadata key in NetCDF inventory. The index
repair preserves actual index attributes and matches the existing NEMO/CROCO
generated description. No time guard, source selection, current preparation,
mask, strict merge or cropping implementation changed. New regressions were
watched fail first; final module18passed/69warnings. Four round trips use
ordinary NetCDF/Zarr readers; provided-index attributes also have two real
executor-boundary checks, not a claimed source-file round trip.

Initial wider index cases exposed additional support-role conflicts after the
metadata error: explicit `zeta` co-export and input-provided index ownership.
These remain proposal-only and retained in raw evidence. The isolated new cases
do not replace or weaken the original portable tests.

Current connected command:429passed/2failed/2026warnings in226.12s. Only the
original portable CROCO `[native]` (crop `y_rho`) and `[mass_earth]` (now `zeta`
coordinate/data-role mismatch) fail. Their numerical/mask/W/sigma assertions
remain unchanged and unreached. The original portable NEMO example now passes.
This is not Task16 completion or its unused post-freeze full diagnostic.
Exact commands and limits: `task-16-metadata-fixes-checks.md`.

Strict Sphinx01/publication01/13publication units pass; two affected pages checked
live at1020/320CSS widths. Ruff3Python paths:6baseline/6current/zeroNew.
Independent review and local commit are pending. No installation, native repair,
standalone image/plot/screenshot, production run, push or merge.

### Metadata review closed — bounded local commit handoff

Fresh independent review of treec70c011e656ab8e95b6033397b9f0ad7e6ad785b:
SPEC PASS / QUALITY APPROVE, zero findings. The reviewer independently verified
the eight-path patch/hashes, empty index and all25preserved paths;43targeted tests
passed/296warnings in27.26s, plus36actual-executor controls and a NEMO ordinary-reader
round trip. It did not repeat full/connected, docs, lint or GUI checks. Its retained
report is `task-16-metadata-review-01.md`.

The lead freshly checked the reviewed bytes/base/index and preservation before
recording closure. Subsequent edits only update review status in this internal
STATE, plan and checks record; production, regressions and canonical prose stay
exactly reviewed. The resulting local commit will be reported in the handover.
No push/merge or CROCO layout implementation is authorized. The two original
CROCO failures and supplied-index loading role conflict remain real unpassed gates.
Prepared alternatives preserve all field samples and strict merges in one
source/product dataset: retain distinct owned support views (recommended), or
trim support to minimal native windows with additional boundary/index verification.
The maintainer must choose before a layout design/implementation is undertaken.
Final precommit module18passed/69warnings in13.85s; strict Sphinx/publication02/
13units passed. The two rebuilt HTML pages are byte-exact to retained live01.
All five production/test/canonical paths remain exactly reviewed, all25previous
paths preserved, and diff check passes. Commit scope remains the original8paths.

### CROCO option1 — bounded design authorized, implementation not authorized

Metadata fixes were committed locally as63431908c64bc72fd6e8beaa6ee2a2a93fce7f8c,
tree407369fc21da1a8fad71ecf47effd61be03ed43a. Postcommit checks confirmed the
exact8paths, empty index and all25previous dirty paths unchanged; no push/merge.

The maintainer answered “Approved” to option1 **for a bounded design**: retain
separately owned support views rather than trim support to minimal windows.
This authorizes writing/checking the design, not implementation or scientific
approval. Proposed details and acceptance are in `task-16-croco-support-design.md`;
inherited primary rho-axis and sigma/formula qualifications are disclosed schema
choices requiring approval of that document. A fresh builder check precedes
handover; no source, fixture, canonical page or environment changes are authorized.
The original CROCO support/layout and provided-index loading gates remain open.
Python3.13.18/worktree import and all25preserved paths were freshly checked;
the baseline is retained in `task-16-croco-design-baseline.json`.

The fresh builder check of treedcc559a657729440503750b572d33b45d4901ad2 returned
“0ranked questions — nothing important left.” It verified the exact two-path
design-only scope and all25preserved paths, with no material proposal outside
the selected approach/safeguards. This is not approval of the detailed schema,
implementation clearance or runtime/scientific acceptance. No runtime checks ran.
The lead freshly verified the candidate hashes/diff, base HEAD, empty index and
all25preserved paths before recording closure here; the design itself remains
exactly reviewed. `git diff --check` and the publication-boundary check against
the retained metadata02build passed. No Sphinx rebuild/GUI or runtime suite is
needed for this internal-only proposal; the existing preview remains available.
Docs: no user-facing impact because only an unpublished proposed design and this
internal status record change. Detailed design approval remains the next gate.

### CROCO detailed design approved — implementation planning

The maintainer answered “Approved” to the detailed design at
f8e9c879c7e977cbe44d53b8d7df372390821c1b, authorizing implementation planning.
The accepted specification is `task-16-croco-support-design.md`; its earlier
proposed-status wording records the preapproval document, not a new hold.
No runtime changes or implementation approval are implied by this planning step.
The previously agreed inline workflow and independent review before commit remain.

The bounded plan is `task-16-croco-support-plan.md`. It separates bound-role
repair from regional presentation, preserves default C3/polar/uncropped layout
calls, and connects planned, stored and resource dimensions. Canonical naming
guidance goes in the already-linked output guide; all25pre-existing dirty paths,
including the partial ocean guide, remain byte-exact. The fresh planning baseline
is `task-16-croco-plan-baseline.json` (HEADf8e9c87, Python3.13.18, empty index).
Plan self-review and scoped review precede local plan commit/handover; the
maintainer's review of the implementation plan remains required before coding.
All prior CROCO, Task16/full and qualification gates remain open.

Scoped plan review of treec2bee67f2d5cf6857d5cf3e559a090b5da25d1d5 returned
PLAN READY with zero Critical/Important findings. Its one Minor helper-module
attribution was checked against the defining symbols and corrected; no interface,
test requirement or design decision changed. The reviewer independently verified
19existing references, both candidate hashes, the exact two-path scope and
all25preserved paths, with index/HEAD unchanged. No runtime, build or visual
check was performed. The lead verified the frozen bytes before the attribution/
status corrections. The plan's tests remain future work, not acceptance evidence.
Docs: no user-facing impact because this local change is only an unpublished
implementation plan and its status record. Human plan review remains the next gate.
Final static checks verified21existing literal references and all3corrected helper
definitions; the approved design and25prior paths remain unchanged. Diff and
publication-boundary checks pass. No new test module or runtime implementation
was created; only the plan and this record are included in the local commit.

### CROCO implementation plan approved — inline execution active

The maintainer approved plan990f29b95348270058e49a3762c9d6303a1fd16d for inline
implementation, with one fresh independent review before the focused local
implementation commit. No repeated routine approval rounds or per-step commits.
The accepted design remainsf8e9c87; its numerical/mask/time/level/crop safeguards
and the25prior dirty-path preservation requirements are binding.

The existing linked workspace/environment are verified; all25prior files were
freshly copied with manifest/status/binary diff into the new plan-owned workspace
`.superpowers/sdd/task-16-croco-support-plan/`. Its `progress.md` records exact
task steps, interface checks and any rulings. Skill `task-start` cannot parse
the approved `Task1/Task2` headings (exit3), so exact briefs were extracted without
modifying the approved plan. No installations, source changes or full diagnostic
were performed during setup. Earlier evidence and the retained preview remain.

Inline Task1 bound roles: new tests first failed8cases at the observed index/zeta
role merges, with3genuine-conflict controls passing. The reader now retains an
actual source coordinate and its attributes before generating any missing native
index; the executor matches only actual user-field roles before the unchanged
strict merge. Fresh task completion30passed/68warnings in35.11s, including real
NetCDF/Zarr supplied-index/co-export round trips. No commit yet; Task2 regional
layout, connected verification/docs and final independent review remain pending.

### CROCO implementation verified — independent review pending

Inline Task2 now carries independently cropped CROCO face support in owner-qualified
rho/sigma/formula namespaces, retaining the original support extents and arrays.
Preflight, processing/writer applicable dimensions and runtime use the same
regional map. Default/C3/polar/uncropped layouts and exact/identical guards remain.
Required cross-grid support survives field filtering; authored CROCO coordinate
metadata survives extraction, and padded support/source coordinates follow the
already declared crop mask instead of exposing clipped repeated source samples.
No current calculation, field samples, crop window, level/clock or physical-depth
method changed. Canonical output guidance documents naming, larger footprints,
formula meaning, storage keys and downstream schema adaptation.

The initial overbroad coordinate-role promotion broke two Meso-NH controls; it
was narrowed to the actual bound native-index coordinate. The resulting reader/
metadata/grouped-W lane passed94cases. All earlier failures and fixture setup
errors remain in the plan-specific ledger/logs, not relabelled as passes.

Final approved connected command (the exact named lane in the implementation
plan, with its declared environment/fixture prefix and new JUnit output):
**481passed,2026warnings,281.30s**, zero failures/errors/skips. Three formatting
wraps followed; the final Task2 rerun then passed**38cases,143warnings,60.42s**:
36new cases plus both original portable CROCO cases, whose scientific assertions
and fixtures were unchanged. Fresh ordinary NetCDF/Zarr reader processes check
nonconstant fixed/moving/edge samples, zeroes/NaNs, selected sigma order, complete
formula targets, authored source indices, metadata and actual chunks/shards.
The mixed polar/model-grid case checks planning, not broader polar qualification.

Strict Sphinx build/publication check and13publication units passed. Live
text-only GUI inspection at1020px/320px found no page overflow or unreachable
code blocks; preview is retained. Baseline-relative Ruff is19baseline/19current/
0new findings, not zero historical debt. `git diff --check` passed.
All25pre-existing dirty paths and their baseline copies were checked against the
original SHA256 manifest and match exactly; the real index was empty.

Exact commands/results, bounded rulings, preserved evidence and machine-local
preview/server/restart details are in the ignored plan workspace's `progress.md`,
`checks-and-handover.md`, `connected-01.xml/.txt`,
`task-2-tests.log` and `ruff-02-and-preservation.json`.
The next gate is one fresh independent review of a frozen task-only tree, then
a focused local commit; implementation is not committed yet. No push/merge,
installation, environment repair, standalone screenshot/image/plot check or
Task16 post-freeze full diagnostic occurred. Whole Task16/caller conversion,
broader producer/native/HPC, installed-wheel and human acceptance gates stay open.

### CROCO review01 — five Important findings, bounded fix pass

The one fresh reviewer rejected frozen treea7ed7d97 with five Important findings
(no Critical/Minor): partial auxiliary-grid planning crash; owner aliases leaking
into centre-only uncropped output; distinct sigma identities collapsing; valid
rho-geography bounds missing from closure/resources; and present, already-bound
nested ancillary arrays missing from the product. Original review/diff/hashes
remain in the plan-owned workspace. This is not an independent approval.

All five reproduced before production fixes:11failed/1passed/3.19s. Focused
corrections now pass:6cases for partial-grid/actual crop-active callers;8for
distinct sigma definitions plus original level copies;2for positive geographic
bounds and nv chunks/shards;8for lazy nested ancillary closure plus unchanged
genuine missing/owner/collision failures. One bounds attempt still failed because
rho metadata is absent from the face grid; its failed log is preserved. The fix
walks existing complete-inventory metadata, not arbitrary first-file payloads.
Other model support roles and all scientific calculations remain unchanged.

The approved connected fix lane is running; no green-suite/commit claim yet.
Post-fix Ruff is19baseline/19current/0new after correcting one introduced loop
variable shadow. All25preserved paths/copies remain byte-exact. Strict Sphinx02,
publication02 and13publication units pass; the corrected canonical text passed
live1020px/320px text checks without overflow/unreachable code. Preview retained.
The named CROCO C3 check proves matching/pre-alias identity, not an authored
unequal per-field selector; those fields share one group selector. Existing
generic transformed/native C3 positive/negative controls remain in the connected
lane, and requests.py/default layout are unchanged. This coverage limit is
recorded rather than inventing a new scientific profile or request protocol.
No repeated reviewer, full Task16 diagnostic, environment or image check.

### CROCO review fix pass verified — local commit ready

All five Important findings now have observed RED→GREEN regressions and the
approved connected fix lane passes**492cases,2026warnings,296.41s**, zero
failures/errors/skips. After the lint-only local-variable rename, the final new
module plus both unchanged original portable CROCO cases passes**49cases,
143warnings,74.91s** (47new+2original). No production/test/published-source
edits followed. Strict docs/publication02,13units and live1020/320px text checks
passed; preview remains available. Ruff remains19baseline/19current/0new;
diff-check and all25preserved file/copy hashes pass.

The original review remains a failed verdict on its initial tree; it is not
rewritten as independent approval of the final tree. The lead closed the findings
with focused regressions and a green connected suite, without a second reviewer,
as required by the approved inline workflow. No Minor findings were reported.
Only the eight task paths will be staged for the focused local commit. No push,
merge, worktree/evidence deletion, environment repair, standalone image/plot run
or post-freeze Task16 full. Whole Task16/legacy conversion and all previously
named qualification/human gates remain open; resume producer/caller work next.

### Explicit polar wind components — bounded design in progress

The CROCO increment was committed locally as
`9931f5859dbc9db3b57443c167f8b71943728c7a`; its final eight-path tree and all25
earlier dirty files/copies were post-commit verified. No push/merge occurred.
Task16 resumption found another expression boundary: its retained catalogue
expects `vrad`/`vtan`, but current v3 derived choices admit only `wind_speed`.
An assertion-based schema/producer probe confirms the gap without dataset reads
or output products; its final lint is clean. No producer fields were dropped.

The maintainer answered yes to drafting a bounded design reusing the existing
radial/tangential calculations. This is design authorization, not implementation
or scientific sign-off. `task-16-polar-components-design.md` proposes two scalar
source-derived methods with explicit aliases, polar-only strict shared U/V
stencils, unchanged outward/clockwise signs and Earth-relative motion convention,
undefined origin and existing quality metadata. Initial FA/ocean and
renormalized-vector admission remain out of scope; current speed is unchanged.
The strict shared-mask boundary matters because existing v3 speed samples input
components separately, unlike the retained numerical paired-vector path.

Only the new internal design and this state are claimed; all25pre-existing dirty
paths remain protected. A fresh builder/design check and static/preservation
verification precede the local design-only commit. Detailed design approval and
an implementation plan remain required before code. Whole Task16/full, broader
qualification and human acceptance gates stay open; its one full remains unused.
Docs: no user-facing impact because no published page, runtime/schema, defaults,
outputs or installation behavior changes in this internal design increment.

The maintainer then approved the written polar-component design in this session.
That selects the proposed scalar methods, strict shared-mask/polar-only/
non-FA atmospheric admission and retained scientific conventions; it does not
certify validity or approve code. The implementation plan is now
`task-16-polar-components-plan.md`, preserving inline execution and one fresh
bounded final review before the implementation commit. Two TDD milestones cover
metadata/active admission, then real paired execution/quality/reader invariance
and canonical docs. Plan review remains required before code. A fresh
design/plan builder check precedes their local documentation-only handoff.

The fresh read-only builder/design-plan check of tree
`4ee076b1251109dfa19319c3b0a2d6956065d5cb` returned **nothing important left**,
no blocking findings, ready for human plan review. It verified the referenced
current interfaces and exactly three frozen documentation paths. No new
scientific choice arose; no implementation or scientific approval was inferred.
The lead freshly verified frozen hashes, all25prior paths, unchanged HEAD/empty
index and working/frozen diff-check. Publication boundary against the unchanged
existing CROCO02 artifact passed, not a new build/visual acceptance.

Design and plan content stay unchanged after review; only this closure record
is appended for the focused local documentation commit. The user must still
review the implementation plan before inline execution. No runtime, schema asset,
new regression module, numerical run, installation/environment change or Task16
post-freeze full occurred. Docs: no user-facing impact from these internal records.

### Explicit polar wind components — approved implementation increment

The maintainer approved `task-16-polar-components-plan.md` after local design/
plan commit `f889907990186b271f1cb633c8bba6ea853b5d3a`. Its historical pending-
approval wording is superseded by that answer. Execution remains inline, with
one fresh bounded implementation review before the local commit.

The implementation adds `radial_wind` and `tangential_wind` as explicitly selected
scalar aliases. Active model-grid/FA/ocean requests fail; unused definitions stay
inert. Metadata binding reuses actual atmospheric input preparation and C3 guards,
then requires continuous inputs with matching effective strict pair options
(not identical metadata-origin provenance). Runtime uses one retained paired
sampler and the unchanged terminal-bearing rotation helper, with joint support,
Earth-relative outward/clockwise conventions and origin NaN/status4.
Existing speed's independent sampling and renormalization remain unchanged.
The public binding is experimental, not scientific qualification or stable
promotion. No new numerical formula, source interpretation, dependency or writer.

TDD evidence: structural RED24unsupported-method failures; corrected option
RED8missing guards/22existing passes; runtime RED24missing-dispatch failures
plus5bearing/speed/GRIB cases. Task1's exact metadata lane passed461cases.
Task2's exact component/wind/coverage/polar lane passed284cases, including
independent endpoint/sign/joint-weight oracles, selected reads and ordinary
NetCDF/sharded-Zarr readers. The new synthetic GRIB constants were made binary-
exact after independent ecCodes decoding identified packing error; no old
fixture, selected level/time or numerical tolerance changed.

The five named canonical pages/reference describe syntax, admission, signs,
origin, quality/provenance and experimental limits. Strict docs01 found an
accidental caption indent; corrected docs02 built and passed publication plus
13publication units. Live GUI rendered-text checks at1280px and320px frame
viewports covered all four affected HTML pages; no root horizontal overflow.
The preview remains available; no screenshot/image/plot check or human visual/
scientific acceptance is claimed. Final connected verification and fresh
implementation review are the pre-commit gate.

The named final connected lane passed1030tests (344.46s); XML/full output are
retained. This includes the actual optional backends and original CROCO portable
example check, not Task16's post-freeze full or whole-branch acceptance.
Ruff is279baseline/279current/zero new; diff-check and authoritative schema/
copied reference checks pass. Existing NumPy/backend and fixture time-bounds
warnings remain visible, with no environment repair or waiver. The fresh bounded
implementation review is next, before staging or local commit.

The fresh bounded implementation review found one Important data-integrity issue
and no Critical/Minor findings: an active `geometry_mapped` component alias could
be overwritten by the global quality flag; `radial_bearing` failed late.
The fix rejects active new-method aliases colliding with generated polar
coordinates/quality names during metadata binding, including actual retained
native/public vertical coordinates and native-index names. Existing output layout
metadata is reused; numerical helpers, writers and old fields are unchanged.
Focused regressions observed57missing-check failures before the fix, then62passes
with payload guards, including unused-name and valid-suffix controls.
The approved connected lane is rerunning after this single fix pass. No routine
second review or whole Task16 full is authorized or inferred.

Final post-review connected02 passed1090tests/zero failures or skips in347.83s,
including all57collision regressions and retained controls. Ruff remains
279baseline/279current/zero new. Strict docs03, publication and13units pass;
the updated configuration section was rechecked live at1280/320px and the other
three affected HTML pages/reference are byte-exact to inspected docs02.
The single Important finding is closed by RED→GREEN and the green connected
suite; no second reviewer or scientific sign-off is claimed. Final staging is
limited to the12core-increment paths; resume producer/caller conversion after
the local commit and25-path postcommit preservation proof.

All25earlier dirty paths/copies remain byte-exact and excluded from this core
increment. No install/repair, production/HPC, benchmark campaign, push/merge or
Task16 post-freeze full. Whole Task16 producer/caller conversion, its retained
legacy failures and all wider qualification/human gates remain open.

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
