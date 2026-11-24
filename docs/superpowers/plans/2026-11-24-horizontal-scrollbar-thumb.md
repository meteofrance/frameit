# Quarter-row Horizontal Scrollbar Thumb Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the horizontal thumb visibly thinner in both Textual TUIs.

**Architecture:** Attach one paint-only renderer to the two horizontal
scrollbar instances in `ReportApp.on_mount`. Stock Textual still owns sizing,
colors, mouse behavior, and layout; shared TCSS does not change.

**Tech Stack:** Python 3.13 in `frameit_env`, Textual `>=8.2.8`, existing Rich render protocol, pytest and Pilot.

**Spec:** [Quarter-row horizontal scrollbar thumbs](../specs/2026-11-24-horizontal-scrollbar-thumb-design.md)

## Global Constraints

- No private APIs, dependencies, new settings, or CLI and scientific changes.
- Keep verification targeted; the full suite remains deferred.
- Preserve native vertical bars, one-row mouse targets, and reserved gutters.

## Review Focus

- Both overflowing panes must render the quarter-row glyph.
- A one-column overflow must still respond to a full-cell drag in both panes.
- Fitting content must keep a blank gutter and the same viewport size.
- Hover and drag contrast, track clicks, and vertical bars must stay native.
- Inspect must still fall back to its text report without Textual and Rich.

### Task 1: Paint the horizontal thumb without changing the scrollbar

**Files:** `src/frameit/report_tui.py`,
`src/frameit/testing/numerical/test_inspect_tui.py`,
`src/frameit/testing/numerical/test_validate_tui.py`.

**Interfaces:** Consumes `ReportApp.on_mount`, Textual's documented
`ScrollBar.renderer`, and the Rich console render protocol. Produces one
private `_QuarterRowThumb(ScrollBarRender)` with `__rich_console__(self, console, options)`.

- [x] In `test_explorer_browses_and_copies_at_both_sizes` and
  `test_details_thumb_is_draggable_with_only_one_clipped_column`, assert
  `"▂" in horizontal_scrollbar.render_line(0).text` before the existing
  one-column drag. After filtering Inspect to one fitting row, assert
  `not bar.render_line(0).text.strip()`. Keep the
  existing viewport and interaction assertions.
- [x] Run the two regressions:

  ```bash
  PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
    src/frameit/testing/numerical/{test_inspect_tui,test_validate_tui}.py \
    -k 'browses_and_copies_at_both_sizes or details_thumb_is_draggable'
  ```

  Expected: both fail because the native thumb has no quarter-row glyph.
- [x] Add `_QuarterRowThumb` in `report_tui.py`. Iterate the stock renderer's
  output via `Console.render`. For thumb segments (an explicit foreground),
  replace the text with one `▂` per terminal cell and turn off reverse video
  against the stock track background. Retain segment style metadata and pass
  other segments through. Load Rich only after Textual. Set
  `widget.horizontal_scrollbar.renderer = _QuarterRowThumb` on
  `DataTable, #details-scroll` during `ReportApp.on_mount`; leave every
  other scrollbar and TCSS unchanged.
- [x] Run the two full TUI test files and existing fallback regression:

  ```bash
  PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
    src/frameit/testing/numerical/{test_inspect_tui,test_validate_tui}.py \
    src/frameit/testing/numerical/test_v3_cli.py::test_inspect_falls_back_without_textual_or_rich
  ```

  Expected: glyph, drag, layout, compact view, and fallback checks pass.
- [x] Recreate the existing *in-use* Batsirai screenshots: Inspect at `124×32`
  with `u10` selected, Coordinates open, and the horizontal thumb held at the
  right end; Validate Details at `88×24`, schema-only, Effective configuration
  open, with a five-screen-row vertical drag and hover after release. Use
  `inspect-horizontal-drag.png` and `validate-vertical-hover.png` as baselines.
  Check the horizontal thumb colors at rest, hover and grab, and that a click
  on its track still pages. Show matched before/after captures in chat and Review.
- [x] Check Ruff and `git diff --check`, record the documentation impact
  (presentation only), and commit the scoped changes, spec, and plan locally.
  Do not push.
