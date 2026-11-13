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
| 01 | done | task-01 worker + independent reviewer | 00 | Narrowed filtering; reviewed fix ready for focused commit. |
| 02 | ready | lead | 01 | `configuration.py`, `settings_class.py`, `execution.py`, `loader.py`, `test_configuration_v3.py`; define strict syntax and runtime handoffs. |
| 03 | blocked | lead | 02 | `loader.py`, `preflight.py`, `coupled.py`, inventory tests; freeze records and grid identities. |
| 04 | blocked | unassigned | 03 | `requests.py`, `preflight.py`, optional `units.py`, request/grid tests; bind fields and levels. |
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
- Next: commit Task 01, then assign Task 02.

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
