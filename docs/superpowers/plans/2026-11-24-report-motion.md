# Report Terminal Motion Implementation Plan

> Use inline execution with focused RED→GREEN checks. The maintainer has
> delegated routine decisions; do not wait for intermediate sign-offs.

**Goal:** Make Inspect and Validate responsive and consistent during real work.
**Architecture:** Extend `ReportApp`, its worker callback, and native widgets;
isolate the supplied logo frames from report collection.
**Spec:** [Motion and feedback in the report terminals](../specs/2026-11-24-report-motion-design.md)

## Constraints and review focus

- Use Conda `frameit_env` (Python 3.13), Textual 8.2.8, and existing dependencies.
- Preserve scientific semantics, inspection scope, CLI/JSON and exit codes.
- Test rapid refresh, stale failure and interrupted readers, reduced motion,
  literal clipboard feedback, sidebar focus on resize, and fast keyboard input.
- Source datasets are read-only. Run the full project suite only once all
  implementation and UX fixes are in place.

### Task 1: Show real work and finish safely

- [x] Add gated Pilot regressions in `test_report_motion.py` for major/compact
  layout, determinate/unknown progress, timer shutdown and worker ownership.
  Update the existing refresh/interrupt tests to expect retained previous
  content and explicit pending cancellation. Run focused tests RED.
- [x] Add cached Braille logo frames and the shared busy composition. Emit a
  `discovery` stage before existing source discovery; keep numeric callbacks
  and report data intact. Track the current threaded worker, throttle counts,
  stop activity on terminal outcomes, and report cancellation cooperatively.
- [x] Keep prior evidence clearly marked on a worker exception; do not reuse
  stale selectors. Preserve Validate tabs/disclosures and Inspect source/field
  evidence, with sensible focus and offset restoration.
- [x] Run the focused report/TUI tests GREEN; inspect start-up and refresh
  captures in both apps before continuing.

### Task 2: Add native feedback and navigation

- [x] Test one summary toast per result or clipboard action, a copy error,
  blocked validation, and the native page-motion policy RED.
- [x] Use `notify(markup=False)` and shared TCSS. Keep diagnostics persistent.
  Reuse the native clipboard; document delivery limits. Use 120 ms page moves
  in shared report scrollers and respect Textual motion settings.
- [x] Test wide sidebars and compact fallback, rapid toggles, resize and focus
  RED. Wire the existing Sources and Findings panes to the same toggle
  mechanism using native width animation and their existing widgets.
- [x] Run focused tests GREEN and inspect captures at 80×24, 120×40 and larger.

### Task 3: Exercise the delivered interface

- [x] Follow the handoff acceptance checklist with real and small synthetic
  inputs, including reduced motion and compact/low-colour behavior.
- [x] Have independent Inspect and Validate users exercise real navigation,
  errors, refresh and resize. Fix reproducible problems without adding
  unrelated features. Recheck affected journeys and captures.
- [x] Update the canonical terminal instructions. Build Sphinx strictly,
  check publication, and preview the rendered pages at both widths.
- [x] Run the configured full pytest suite once on the completed tree:
  3,554 tests and four subtests passed.
  Review the diff, commit locally, and report evidence and limitations.
