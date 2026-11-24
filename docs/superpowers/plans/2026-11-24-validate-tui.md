# Experimental Validate TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `frameit validate config.yaml` useful interactively while retaining
the existing text and JSON interfaces.

**Architecture:** Pass an optional progress callback through the existing
validation entry point, without changing its decisions or report. A single
Textual worker calls that entry point and the shared `project_report`, then
presents the projected data in standard widgets. Only the interactive `validate`
branch imports Textual.

**Tech Stack:** Python 3.13, argparse, Textual (with Rich transitively), pytest, Sphinx.

**Spec:** [Experimental validation TUI](../specs/2026-11-24-validate-tui-design.md)

## Global Constraints

- Use `frameit_env`. On approval of this plan, check status and create
  `tmp/validate-tui` from the current isolated worktree's HEAD. Commit locally;
  do not push or integrate it.
- Keep `frameit inspect`, scientific checks, operational override precedence,
  JSON schema, and existing non-interactive behavior unchanged. Do not write
  the request, source data, or products.
- Add only the optional `tui = ["textual"]` extra. Keep all UI and styles in one
  module. No separate Rich layer, editor launch, file watch, or run action.
- Use the approved palette: navy `#021633`, off-white `#E6EDF3`, slate `#A6B4C4`,
  teal `#49C5BC`, amber `#F5B55E`, error red `#DA5656`. Explicit text labels
  carry the meaning.

## Review Focus

- A schema-only pass cannot claim input or execution checks or offer `run` as the next step.
- A partial report may have candidate outputs after an error; show them as unconfirmed, not a resolved plan.
- A slow first file, another source, and planning after the scan cannot inherit a previous estimate.
- Saving malformed YAML then pressing `r` replaces the old pass, and repeated `r` while busy cannot queue another validation.
- A terminal with redirected streams, `TERM=dumb`, or no Textual must still use batch behavior. JSON and forced text never import the TUI, even at a terminal.

### Task 1: Observe the existing validation

**Files:** `src/frameit/cli.py`, `src/frameit/core/preflight.py`, `src/frameit/core/coupled.py`, `src/frameit/testing/numerical/test_v3_reports.py`.

**Produces:** `_collect_report(path, *, command, schema_only=False, overrides=None, progress=None) -> PreflightResult`.
The optional callable accepts `(stage: str, source: str | None, checked: int | None, total: int | None)`.

- [ ] Add `test_validation_progress_leaves_report_unchanged`. Write three small
  `v3_scene(hours=(hour,))` files, guard the requested payload, and use a YAML
  request. Assert `project(observed) == project(plain)` and
  `files == [("metadata", "weather", i, 3) for i in range(4)]` for events with
  counts, and that `"configuration"`, `"binding"`, and `"plan"` occur in order.
  For a schema-only call assert `stages == ["configuration"]`. Assert no output directory.
- [ ] Run `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_reports.py -k validation_progress`.
  Expect a failure on the missing `progress` argument.
- [ ] Report `"configuration"` in `_collect_report` before loading YAML. Forward
  the callback through `collect_preflight`, `bind_sources`, `prepare_sources`,
  and `_prepare_v3_sources` into `inventory_source`, all with `progress=None`
  defaults. Report `"metadata"` for input preparation and per-source file
  discovery; at the existing loop report `0/N`, then counts when each attempt
  finishes, including a handled failure. Report `"binding"` per source and
  `"plan"` before final product checks. Leave validation decisions alone.
- [ ] Rerun the report tests and `test_inspect_metadata.py`. Commit the checked
  changes and approved spec/plan. Record `Docs: no user-facing impact` for
  this internal plumbing.

### Task 2: Implement and exercise the Textual view

**Files:** New `src/frameit/validate_tui.py` and `src/frameit/testing/numerical/test_validate_tui.py`.

**Consumes:** A callable accepting the Task 1 progress callback and returning `PreflightResult`.
**Produces:** `ValidationApp(config: Path, collect, *, schema_only=False, overrides=None)`, a Textual app returning the validation exit code.

- [ ] Install Textual into `frameit_env` for the trial, without changing the default
  Conda environment definition. Add Pilot tests with `asyncio.run` and
  `pytest.importorskip("textual")`. Use a real instructional pass, incomplete
  field selection, and schema-only request. Assert `instructional_scalar` and
  a planned output on a full pass, `E1301` plus a repair on an incomplete
  selection, and input-aware validation (not `frameit run`) as the next step
  on schema-only. Use a partial report with a candidate path to assert it is
  labeled unconfirmed.
- [ ] Add `test_live_scan_and_reload` with a worker gated by events and a controlled
  clock. Assert `2 of 6` and `ETA ~00:08` after 4 seconds of scan time; assert no
  ETA for a new source at `0 of 1` or in planning. From a pass, replace the YAML
  with malformed text and press `r`, then press it again while busy. Assert
  exactly two collections, no old verdict during recheck, `E1102` and a location
  afterward, and `q` returns `1`. At a narrow size verify tabs and independent
  scrolling by keyboard. Assert `Ctrl+C` cannot turn a pending check into a pass.
- [ ] Run `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_validate_tui.py`.
  Expect failure on the missing module.
- [ ] Implement one App using `TabbedContent`, independently scrollable stock
  widgets, and `Footer`. Overview shows mode, verdict, first repair or next
  command, source/field/time summary, region or tracker and planned paths from
  the projection. Never treat authored choices or candidate paths as confirmed.
  Suggest `frameit run` with the same overrides only after full checks pass.
  Findings lists errors, warnings, blocked, then deferred; show selected
  details and original help paths as literal text. Details displays effective
  config, origins and plan without edits. `1`/`2`/`3` change tabs; `r` restarts
  only after completion; `q` exits with the latest completed report's code.
- [ ] Use one thread worker and Textual's thread-safe signalling. Publish a
  progress view before collecting, clear stale results on reload, and update
  elapsed time on a timer. Compute `ceil(scan_elapsed * (total - checked) / checked)`
  only after at least two completed files with files remaining. Measure
  `scan_elapsed` from the `0/N` notification; reset between sources and stages.
  Keep interrupts non-successful without promising to cancel a native call immediately.
- [ ] Rerun the Pilot tests. Commit the view with its entry point in Task 3.

### Task 3: Expose the experiment and verify compatibility

**Files:** `src/frameit/cli.py`, `pyproject.toml`, `src/frameit/testing/numerical/test_v3_cli.py`, `docs/source/user_guide/configuration_file.rst`.

**Consumes:** `ValidationApp` and the existing `_collect_report` and `_print_preflight`.

- [ ] Add `test_validate_selects_output_mode` covering a usable terminal with
  Textual, `--cli`, `--json`, one redirected stream, no usable `TERM`, and
  unavailable Textual. Assert `tui_calls == 1` only in the first case; in bypass
  cases compare output and exit code against the existing renderer, with no
  TUI import in forced or redirected modes. Check an error still returns `1`,
  and `--cli` is not an `inspect` option.
- [ ] Run `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_v3_cli.py -k validate_selects_output_mode`.
  Expect `--cli` or interactive dispatch assertions to fail.
- [ ] Add `--cli` only to `validate` and `tui = ["textual"]` in `pyproject.toml`.
  In `_cmd_validate`, pass the same schema and override options to the chosen
  renderer. Skip the import for `--cli`, `--json`, non-TTY streams, missing
  `TERM`, and `TERM=dumb`; fall back when Textual is absent. Keep the current
  print and exit path otherwise unchanged.
- [ ] Document experimental install, auto-selection, the `--cli`/`--json` paths,
  controls, and scan-only ETA in the validation report section of the config guide.
- [ ] Run `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/{test_validate_tui,test_v3_cli,test_v3_reports,test_inspect_metadata,test_hpc_execution}.py`.
  Expect all relevant tests to pass. Use the instructional fixture and
  `frameit init arome-fixed-scalar` in a fresh directory to smoke-test a real
  terminal and compare CLI, JSON and TUI exit codes on valid, malformed and
  incomplete YAML.
- [ ] Run `conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/validate-tui-01`
  and `conda run -n frameit_env python docs/check_publication.py build/docs-preview/validate-tui-01`.
  Expect both to pass. Inspect the guide at desktop and narrow widths in
  the live OpenCode GUI; keep its loopback preview running or report a
  disconnected GUI. Review the diff and commit. Hand over the branch,
  commit IDs, exact verification and fixture commands, and prototype limitations.
