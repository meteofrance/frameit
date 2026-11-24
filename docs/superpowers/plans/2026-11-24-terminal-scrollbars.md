# Shared Terminal Scrollbars Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give both Textual TUIs the same quiet, layout-stable scrollbars.

**Architecture:** Use the existing `ReportApp.CSS` for both views. Keep Textual’s built-in scrollbar geometry and interaction.

**Tech Stack:** Python 3.13 in `frameit_env`, Textual (existing `>=8.2.8`), pytest and Pilot.

**Spec:** [Shared terminal scrollbars](../specs/2026-11-24-terminal-scrollbars-design.md)

## Global Constraints

- One-cell native bars. No global patches, private APIs, dependencies, or new styling layer.
- Run only the targeted TUI tests; the full suite remains deferred.
- Keep work in the existing local worktree. No CLI, configuration, or scientific output changes.

## Review Focus

- Expanding long YAML in Validate must not move the visible content area; Right must still scroll it.
- Filtering Inspect’s table from horizontal overflow to a fit must not resize its viewport.
- The hidden source-picker bar must not take space or prevent arrow or wheel navigation.
- The thumb must brighten on hover and drag while the track and corner stay invisible.
- The compact view must retain its refresh and quit shortcuts.

### Task 1: Apply and verify one shared scrollbar style

**Files:** `src/frameit/report_tui.py`, `src/frameit/validate_tui.py`,
`src/frameit/testing/numerical/test_validate_tui.py` and `src/frameit/testing/numerical/test_inspect_tui.py`.

**Consumes:** `ReportApp.CSS`, `ValidationApp`, `InspectionApp`; the existing
`{validate,inspect}-before.png` captures.
**Produces:** The same Python and CLI interfaces with shared native scrollbar styling.

- [x] Extend `test_details_render_long_nested_yaml_lines_without_wrapping` to save
  `details.scrollable_size` before opening the disclosure. After it opens, check
  the same size, `details.scrollbars_space == (1, 1)`, and the corner's rendered
  background. Keep the existing Right-key check.
- [x] In `test_explorer_browses_and_copies_at_both_sizes`, give the unrequested `alpha`
  row units long enough to overflow the wide table without changing its Units sort
  position. Check that `table.scrollable_size` stays the same when filtering to the
  requested `zeta` row, but `table.max_scroll_x` goes from positive to zero.
  Retain source switching, filtering, and the `r`/`q` check at `52×16`.
- [x] Run `PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/{test_inspect_tui,test_validate_tui}.py -k 'browses_and_copies or scrolls_source_picker or long_nested_yaml'`. Expect native default sizes or a changing scrollable region to fail.
- [x] In `ReportApp.CSS`, style `VerticalScroll`, `OptionList` and `DataTable` with
  `scrollbar-size: 1 1`, `scrollbar-gutter: stable`, transparent tracks, a
  theme-matched corner, and `$accent` at 55%, 78% and full strength for resting,
  hover and active thumbs. Remove `VerticalScroll:focus`’s thumb override. Give `#sources`
  size `0 0`. Set `overflow-x: scroll` on `DataTable` and `#details-scroll`
  in the shared rules; remove Details’ local `overflow-x: auto`.
- [x] Run the same two test files without `-k`. Expect all tests to pass. Exercise
  a visible one-cell thumb with Pilot’s public hover, mouse-down/move/up and
  keyboard interactions. Verify the thumb changes contrast and dragging scrolls.
  With enough sources to overflow the picker, verify that the wheel moves its
  viewport even though it has no visible scrollbar.
- [x] Capture Validate Details at `88×24` (Batsirai, schema-only, Effective
  configuration expanded) and Inspect at `124×32` (Batsirai, `u10`, Coordinates).
  Show matched before/after captures in chat and the OpenCode Review pane.
  Only investigate the documented renderer if normal native bars still look too
  heavy; otherwise keep this CSS-only.
- [x] Review `git diff --check`, record the documentation impact (appearance
  only, no change to commands or guidance), stage only the relevant files, and
  commit locally. Keep captures available; do not push.

## Review follow-up

Textual needs `overflow: scroll` on both the Variables table and Validate
Details to size the horizontal thumb against the vertical gutter. Regressions
check that the thumb can be dragged with exactly one clipped column and no
vertical overflow. Below ten rows, Inspect omits the Variables heading to keep
the field row visible without losing its controls or moving the gutter.
