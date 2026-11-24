# Validate Research Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a compact terminal validation view with FrameIt.

**Architecture:** Keep the existing `ValidationApp`, worker, and shared report.
Replace the presentation inside its three tabs and adjust which shortcuts the
footer advertises. Use stock Textual widgets instead of a separate display layer.

**Tech Stack:** Python 3.13 in `frameit_env`, Textual, pytest, Sphinx.

**Spec:** [Research console design](../specs/2026-11-24-validate-tui-research-console-design.md)

## Global Constraints

- Keep work local on `tmp/validate-tui`; `7422468` is the visual comparison
  baseline. Do not merge or push.
- Use stock Textual widgets. Promote Textual to a regular dependency in Task 2.
  Do not change report data or
  scientific behavior, or touch `inspect`, `--cli` or `--json`.
- Keep the existing palette, including error red `#DA5656`, and explicit labels.
- Keep source fixtures read-only. Store captures outside the repository.

## Review Focus

- Schema-only and malformed YAML cannot show a run instruction or imply that inputs were checked.
- Failed binding may leave candidate paths; its first repair stays near the verdict and Details marks the paths unconfirmed.
- Selected times from different sources or calendars must not be combined into a single time span.
- At narrow widths, Details starts collapsed, its titles work with the keyboard, and expanded text scrolls without losing indentation.
- Revalidation hides stale results and unavailable shortcuts; the current scan still shows real counts and only a valid ETA.

### Task 1: Present the same validation in the research console

**Files:** `src/frameit/validate_tui.py`, `src/frameit/testing/numerical/test_validate_tui.py`,
`docs/source/user_guide/configuration_file.rst`, and this spec/plan.

**Consumes:** `_overview(report, config, schema_only, overrides, *, has_warnings)`,
`project_report(result)`, the existing worker and `ValidationApp` bindings.
**Produces:** The same app and exit-code interface, with `#summary`, `#finding-list`,
and three stock collapsibles `#detail-configuration`, `#detail-origins`, `#detail-plan`.

- [ ] Update `test_validation_tabs_show_only_supported_conclusions` first. Assert
  `Inputs`, `Selection`, `Region`, and `Outputs` in a successful summary; the
  sample has two selected times and one model-grid field. Assert full field names
  and paths appear in Details instead, and keep the run-overrides, unused-centre,
  schema-only, and no-output assertions. Add a malformed-YAML variant. In the
  invalid and incomplete cases assert the first repair precedes the request
  summary and no run is offered.
  Verify that Details starts collapsed, `Tab` and `Enter` open a section,
  indented YAML remains literal, the pane scrolls at `52×16`, and the partial
  plan title and candidate paths remain explicit on binding failure.
- [ ] Add a two-source report test with `360_day` and `noleap` time labels.
  Assert that each source's count and endpoints stay on its own summary line
  with the calendar intact, not a combined start and finish.
  In `test_live_scan_and_reload`, assert the busy footer advertises `Ctrl+C`
  rather than `r` and `q`, and those keys return with the completed report.
  Retain the existing count, ETA, stale-result, and interruption assertions.
- [ ] Run `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_validate_tui.py`.
  Expect failures for the missing compact summaries, disclosures, or busy-footer behavior.
- [ ] In `ValidationApp.compose`, use a slim `FrameIt / validate` identity and
  compact status line; keep the tab and scroll IDs. Change `_overview` to show
  the four rows and the next command or first repair. Count only confirmed input
  and product facts, describe times per source, and make absent or partial facts
  explicit. Move raw YAML, full fields and paths into the existing report details.
- [ ] Keep the Findings list and detail pane. Use the stock OptionList's compact
  mode and highlighted-option styling for readable bold focus on a muted surface,
  not a solid teal bar. Keep the code or subject in each title and preserve full
  warnings, evidence and repairs. Replace the single Details dump with three
  `Collapsible` widgets containing literal `Static` text; format their sections
  in the worker and start them collapsed for each new report.
- [ ] Show a scan-only interrupt hint while the report tabs and compact results
  footer are hidden. Restore all result shortcuts after validation; check that
  they fit at `52×16`. Do not change the interrupt handler or ETA calculation.
  Rerun the Pilot tests; expect the updated cases to pass.
- [ ] Update the configuration guide with how to expand sections. Run the
  following in `frameit_env`, using the verified fixture root for the tests:
  `PYTHONPATH="$PWD/src" FRAMEIT_CI_DATA_ROOT="$fixture_root" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/{test_validate_tui,test_v3_cli,test_v3_reports,test_inspect_metadata,test_hpc_execution}.py`.
  Expect all targeted tests to pass. Build with
  `conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/research-console-01`
  and run `conda run -n frameit_env python docs/check_publication.py build/docs-preview/research-console-01`.
  Inspect the live rendered guide at desktop and narrow widths.
- [ ] Validate the manifest-verified Batsirai case and malformed YAML in the real
  app at normal and narrow sizes. Capture Overview, Findings, and an expanded
  Details section with Textual, and send PNGs in chat rather than relying on the
  local preview URL. Check verdict, focus contrast and no written products.
- [ ] Review the diff, stage only the console, tests, guide and spec/plan, and
  commit locally. Report observed checks and the comparison screenshots.

### Task 2: Simplify the text and include the view by default

**Files:** `src/frameit/validate_tui.py`,
`src/frameit/testing/numerical/test_validate_tui.py`, `pyproject.toml`,
`docs/test_release.py`, `docs/source/user_guide/configuration_file.rst`,
`docs/source/getting_started/installation.rst`, `README.md`.

- [ ] Update the Pilot assertions for a filename-only header, `Validation
  passed`, `Fix first`, no generic caveat, and schema-only advice to validate
  without `--schema-only`. Keep the assertions for unconfirmed paths.
  Expect the updated tests to fail on the old copy.
- [ ] In the existing release test, assert the wheel has an unconditional
  `Requires-Dist: textual` requirement and contains `frameit/validate_tui.py`.
  Expect the requirement check to fail before changing dependency metadata.
- [ ] Change the TUI copy and move Textual into regular dependencies at the
  verified version floor. Keep CLI dispatch and the text fallback unchanged.
  Remove the experimental and extra-install instructions in the guide.
- [ ] Run the targeted tests plus `docs/test_release.py`, build and inspect
  a wheel, rebuild/check Sphinx, and refresh the app captures.
