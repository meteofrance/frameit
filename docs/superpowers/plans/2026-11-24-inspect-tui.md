# Terminal Dataset Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let researchers browse one file per source and copy evidence-backed YAML selectors with `frameit inspect`.

**Architecture:** The interactive collector stops after reading sample metadata and uses the existing report envelope. Both terminal views share the report shell and CLI dispatch; text, JSON, and processing keep their existing collectors and behavior.

**Tech Stack:** Python 3.13 in `frameit_env`, `textual>=8.2.8`, pytest, Sphinx.

**Spec:** [Terminal dataset explorer](../specs/2026-11-24-inspect-tui-design.md)

## Global Constraints

- One file per source only in the TUI, in declared path/glob order with sorted matches, exclusions and physical deduplication. Never retry a failed sample.
- In the explorer, no scientific field payloads, binding, cross-source planning, output checks or writes. Keep YAML intact, and distinguish observations from requests.
- No new dependency, public report/configuration schema, or scientific defaults. `--cli`, `--json`, redirects and terminal fallback keep full inspection; `validate` stays unchanged.
- Keep the navy/teal/amber palette and `#DA5656` errors. Use stock widgets, one widget tree, wide mode from 120 columns and 30 rows, and test at `52×16`.
- Work in the existing local worktree, not on `main`/`develop`. Preserve unrelated changes, commit verified changes locally, and do not push.

## Review Focus

- A file with no decoded clock still has inspectable fields; report no phantom times (Task 1).
- Same-name identities across cycles and a duplicate provider within one sample cannot yield misleading selectors (Task 1).
- A redirect of **any** of the three standard streams bypasses Textual and still inspects later files (Task 3).
- Search with no hits, or a refresh that removes the selected field, must not leave a stale copy action (Task 3).
- A non-Gregorian time label and an omitted large-coordinate descriptor must remain distinguishable from ordinary dates and numeric coordinate values (Task 3).

---

### Task 1: Collect sample evidence without archive checks

**Files:** `src/frameit/core/preflight.py`, `src/frameit/core/coupled.py`;
`src/frameit/testing/numerical/test_v3_reports.py`, `src/frameit/testing/numerical/test_inspect_metadata.py`.

**Consumes:** `inventory_source_files(source)`, `_source_file_entries(source, name)`,
the NetCDF/GRIB/FA metadata readers, `_source_runtime(conf, name)`,
`field_candidates(...)`, `_selection_stamp(value, example)`, `project_report(result)`.
**Produces:** `collect_preflight(..., sample_only: bool = False) -> PreflightResult`;
`inventory_source(..., sample_only: bool = False) -> dict`. Sample-only
`data.plan.sources[name]` includes `sample` (`path`, `discovered`, `inspected`),
the existing declaration, requests, inventory and evidence, and
all `record_inventory` records from that file (not `selected_times`).
`available_selectors` additionally carries `field_id` in this private mode.
`request_status` maps field IDs to `requested`, `not_requested` or `unresolved`;
`missing_references`, `unresolved_references` and `time_notes` retain scoped
request observations. `time_notes` entries are `{"subject": ..., "status": ...}`
with `not_seen` or `not_reported` for absent or non-comparable requests.

- [ ] Write `test_sample_inspection_opens_one_file_per_source` using `v3_scene`
  and a second source fixture. In declared glob order, the first match is
  excluded, the next has an inode alias, and another file holds a requested
  field and exact timestamp outside the sample. Guard actual reader opens
  (including format sniffing), guard payload reads, and forbid binding and
  region planning. Assert `opened_paths == {chosen_atmosphere, chosen_ocean}`,
  untouched YAML/source files, no output, and these sample facts:
  ```python
  assert not report["errors"]  # including differing declared and observed units
  assert source["sample"]["inspected"] == 1
  assert source["missing_references"] == ["later_only"]
  assert {r["time"] for r in source["record_inventory"]} == set(sample_timestamps)
  assert source["request_status"][omitted_from_product_id] == "requested"
  assert source["request_status"][product_only_id] == "requested"
  assert source["request_status"][dependency_only_id] == "not_requested"
  ```
  Check declared and observed units separately and progress `0 of 1` to
  `1 of 1` for each source.
- [ ] Write `test_sample_inspection_retains_independent_sources`, parameterized
  for bad YAML (`E1102`), a bad first file followed by a good file (`E1202`),
  and a missing match alongside a valid path (`E1201`). Assert no open at all
  on that source for discovery failure, no retry for a read failure, and
  the healthy source is browsable whenever the YAML parses. Assert a failed
  sample path and unread candidates remain visible with `inspected == 0`.
  Write `test_sample_inspection_without_clock`: the fields and selector remain,
  `record_inventory == []`, and the requested time note is `not_reported`.
- [ ] Extend the existing synthetic GRIB/payload-guard case with
  `test_sample_inspection_selectors_keep_native_identity`: make different
  same-name/same-group identities across two cycles, a different vertical
  group, and a duplicate same-field/time/cycle/level provider. Assert:
  ```python
  assert len({r["cycle"] for r in source["record_inventory"]}) == 2
  assert not ({*ambiguous_ids, duplicate_provider_id} &
              {item["field_id"] for item in source["available_selectors"]})
  assert qualified_selector["field_id"] == uniquely_grouped_id
  ```
  Supply an authored cycle; it must not eliminate the ambiguity. Round-trip
  the qualified selector through existing schema and field selection.
- [ ] Run `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/{test_v3_reports,test_inspect_metadata}.py -k sample_inspection`.
  Expect failures because the sample collection path does not exist.
- [ ] Add the `command="inspect", sample_only=True` branch after schema
  resolution in `collect_preflight`. Extract `_source_child(conf, name) ->
  SimulationConfig` from `_prepare_v3_sources` to share source-local setup.
  Return a `PreflightResult` with per-source sample facts and accumulated
  diagnostics, including partial facts from failed samples; do not call
  archive preparation or convert absence in the sample into diagnostics.
- [ ] In `inventory_source`, restrict the common metadata reader loop to the
  first eligible path before reading, or to no paths on a discovery error.
  Mark the file entries `inspected`, `not_inspected` or `sample_failed`
  and retain known excludes and aliases. `sample["discovered"]` is `None`
  when discovery did not finish. Exit this mode before the existing selection,
  consistency, metadata override and processing checks.
- [ ] Reuse the existing field candidates, native group and selector rules on
  the whole sample. Preserve clockless identities without inventing records.
  Reuse the provider identity key to suppress competing providers; only
  offer qualified selectors when the known group uniquely identifies a row.
  Use `request["fields"]` and explicit product field references, not method
  dependencies. In sample-only selector notes, use the observed records,
  not `selected_times`, as clock evidence. Compare explicit times/cycles
  and range overlap against recorded labels via `_selection_stamp` where
  comparable; do not apply stride, guess gaps or infer absence from an
  undecoded clock. Preserve reported reader, coordinate and default-origin
  evidence without promoting it to eligibility.
- [ ] Run the Task 1 command without `-k`. Expect the sample tests and unchanged
  report/inventory tests to pass. Review the diff and commit the internal
  collector and tests (`Docs: no user-facing impact because the sample path
  is not yet exposed.`).

### Task 2: Share the terminal shell and dispatch

**Files:** create `src/frameit/report_tui.py`; modify `src/frameit/validate_tui.py`,
`src/frameit/cli.py`, `src/frameit/testing/numerical/test_validate_tui.py`.

**Consumes:** existing `ValidationApp`, `_collect_report`, `project_report`, and diagnostic formatters.
**Produces:** `ReportApp(config: Path, collect)` with
`compose_view() -> ComposeResult`, `prepare_view(report: dict)` (worker-side
view data, default `None`), `show_report(report: dict, prepared) -> None`,
shared `compose_findings() -> ComposeResult` and `action_refresh() -> None`;
`_run_report_app(build_app, *, cli_output: bool, json_output: bool) -> int | None`
(`None` only when falling back).

- [ ] Add `test_validation_uses_shared_report_shell`: assert
  `issubclass(ValidationApp, ReportApp)` and retain the existing Pilot
  assertions for Overview, Findings, Details, `1`–`3`, `r`, `q`, busy
  progress/ETA and statuses. Run
  `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_validate_tui.py -k shared_report_shell`;
  expect a missing module before extraction.
- [ ] Move the header/footer, palette, worker, progress, stale-result hiding,
  refresh/quit/interrupt and diagnostic rendering into `ReportApp`. Scope
  findings events to `#finding-list` so a second option list cannot update
  the wrong detail. Keep validation-specific bindings, verdict, tab IDs, and
  formatting (including worker-side YAML) in `ValidationApp`. Move only the
  clock monkeypatch target in `test_live_scan_and_reload`.
- [ ] In `_run_report_app`, call the lazy factory only for usable `TERM` and
  three TTY streams, after flag checks. Catch only a missing `textual` import;
  keep signal handling and exit-code normalization. Use it from `_cmd_validate`
  without changing its collector or signature.
- [ ] Run `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/{test_validate_tui,test_v3_cli}.py`.
  Expect the existing validation dispatch and PTY checks as well as the
  new shell check to pass. Review and commit the extraction
  (`Docs: no user-facing impact because validation behavior is unchanged.`).

### Task 3: Expose and verify the dataset explorer

**Files:** create `src/frameit/inspect_tui.py`,
`src/frameit/testing/numerical/test_inspect_tui.py`; update `src/frameit/cli.py`,
`src/frameit/testing/numerical/{test_v3_cli,test_validate_tui}.py` and
`docs/test_release.py`. Documentation: `README.md`,
`docs/source/{user_guide/input_files,user_guide/configuration_file,getting_started/quick_start}.rst`,
plus full-inventory examples in `task_guides/{forecast_archive,coupled_clocks}.rst`
and `troubleshooting/{inputs,time,fields}.rst` under `docs/source`.

**Consumes:** `ReportApp`, `_run_report_app`, the sample `PreflightResult` facts.
**Produces:** `InspectionApp(config: Path, collect)`; `_collect_report(...,
sample_only: bool = False)`; `frameit inspect [config] [--cli] [--json]`.
IDs for Pilot: `#sources`, `#field-search`, `#fields`, `#field-details`,
`#source-tabs`, and the existing diagnostics IDs.

- [ ] Replace `test_inspect_keeps_its_existing_options` with a dispatch matrix.
  Assert the default YAML (missing gives `E1101`), explicit path, each
  redirected stream, missing/empty/`dumb` `TERM`, missing Textual and flags
  including JSON precedence. On a two-file fixture, assert fallback/redirect/
  `--cli` text equals the old full render, JSON equals the old full projection,
  and only app mode receives sample scope. Check exit 0 and 1. Parameterize the
  existing Linux PTY test for `inspect`; it must restore TTY settings and
  return 143 on SIGTERM. Retain validation coverage.
- [ ] Write Pilot tests `test_explorer_browses_and_copies_at_both_sizes` and
  `test_explorer_refreshes_without_stale_selection`. Assert four panes at
  `120×30`, one view at `52×16` with `r` and `q` visible, and selection/filter
  preserved across resize. Check numbered views, arrows/tabs, `/` search
  (typing shortcut letters stays in search), `s` sort, `f` filter, `c` copy
  and the `yaml.safe_load` of the exact clipboard text. Test an ambiguous
  row, no search hits, and a refresh that removes a row: no stale copy.
  Test the seven source tabs, a `360_day` date (e.g. `2001-02-30`), and a
  coordinate descriptor showing omission rather than numeric values. Check
  one failed source does not hide a readable source, a malformed/empty
  inventory focuses diagnostics, `r` rereads saved YAML once, one-file progress
  has no ETA, `q` returns 0/1 and Ctrl+C returns 130.
- [ ] Run `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/{test_inspect_tui,test_v3_cli}.py`.
  Expect failure for the missing app/module and options.
- [ ] Compose the three upper panes and source tabs with stock Textual widgets
  in `InspectionApp`. Bind `1`–`4` to focus or show panes, use width/height
  breakpoints and one table keyed by native IDs, and keep source/sample scope
  visible in compact mode. Put search/sort/filter/copy hints by the controls
  so the compact footer fits. Show units, dimensions, native group and
  request status in the table; use the detail for raw field evidence.
  Use the Overview, Coordinates, Time, Grids, Files, Origins and Diagnostics
  tabs for source-level evidence. Use **Not seen in sample** for an absent
  request and **Not reported** for unavailable evidence; keep recorded
  times, calendars and configured windows distinct. Label the result as
  sample inspection, never as clearance to run. Render an exact report selector under
  `sources.<source>.variables` and copy with `copy_to_clipboard`. Do not
  regenerate selectors in the view. Reuse the shared diagnostics for errors
  and keep healthy sources accessible; refresh clears stale results and
  restores a still-present source/field.
- [ ] Add optional `config` and `--cli` to the inspect parser. Use
  `_run_report_app` to give `InspectionApp` the sample collector, and only
  call the existing full collector/render path if the app was bypassed.
  Do not add `--sample` or alter validation arguments.
- [ ] Add both new modules to the existing wheel/sdist asset test. Update
  the canonical input guide with first-file choice and limits, shortcuts,
  clipboard fallback, and `--cli`/`--json` for full reports. Keep explicit
  paths in examples; use `--cli` where an example relies on archive-wide
  or selected-time evidence. No change to the YAML templates or outputs.
- [ ] Run the targeted regressions and packaging check. Expect no failures:
  ```sh
  PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
    src/frameit/testing/numerical/{test_inspect_tui,test_validate_tui,test_v3_cli,test_v3_reports,test_inspect_metadata,test_fa_cubes,test_hpc_execution}.py \
    docs/test_release.py
  ```
  Run `conda run -n frameit_env ruff check` on edited Python files and
  `git diff --check`. Build a local wheel without dependencies using
  `conda run -n frameit_env python -m pip wheel --no-deps --no-build-isolation --wheel-dir "$wheel_dir" .`;
  install into a temporary `--target` (not `frameit_env`) and exercise the
  installed `python -m frameit inspect` in a PTY, and with `--cli` and `--json`.
- [ ] Run the strict Sphinx build and publication check:
  ```sh
  conda run -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/inspect-01
  conda run -n frameit_env python docs/check_publication.py build/docs-preview/inspect-01
  ```
  Follow the documentation contribution guide to preview changed pages in
  OpenCode at desktop and narrow widths. Use a verified local Batsirai fixture
  if available and a small broken/unfinished request for live TUI captures;
  send wide and narrow screenshots in chat. Report unavailable checks, open
  visual review and any preview server run details without committing them.
- [ ] Review the implementation against the spec, stage only related files
  and commit. Hand over the commit IDs, shared vs. new code, the one-file
  limit, unchanged scientific/output contract, observed verification and
  terminal clipboard limitations.
