# Report Terminal Review Follow-up Implementation Plan

> Use inline execution with focused RED→GREEN checks. The maintainer has
> delegated routine decisions; do not wait for intermediate sign-offs.

**Goal:** Make the report terminals easier to read and check the sample views
with additional local producers.
**Architecture:** Extend the shared report lifecycle and native scrollbar
renderer. Keep the sticky section label local to Validate Details.
**Spec:** [Follow-up review](../specs/2026-11-24-report-motion-design.md#follow-up-review-2026-11-25)

## Constraints and review focus

- Use `frameit_env` Python 3.13 and the existing Textual APIs and dependencies.
- No changes to scientific methods, output semantics, or non-interactive CLI.
- Exercise both scrollbar orientations and keep native track and drag behavior.
- Retain the active tab, open disclosure, focus and scroll on cancellation;
  make first-check cancellation and the compact fallback explicit.
- Check that the pinned title follows the section actually being read and clears
  when that section is collapsed or no longer owns the top of the viewport.
- Use existing local inputs read-only and bounded metadata/preflight checks.
  No production runs, downloads, or second full-suite run for this review.

### Task 1: Match the reports visually

- [x] Extend the Validate scrollbar check: a pure black background, a `┃`
  vertical thumb, native drag and track clicks. Reuse the Inspect table check
  for the unchanged `━` horizontal thumb and full-cell drag behavior.
- [x] Observe RED, then paint a centered stroke in the existing shared renderer
  and switch the base report theme to black. Verify GREEN and rendered previews.

### Task 2: Restore context in Validate

- [x] Gate a validation refresh in Pilot; require branded activity and a
  hidden report, then require the same report, tab, scroll and focus after
  cancellation with a previous-report label. Retain exit 130 on quit until
  a later refresh produces a report. Update genuine refresh expectations;
  observe RED.
- [x] Reuse the startup layout for Validate refresh and restore the view on
  worker completion, cancelling without taking down the app. Verify GREEN.
- [x] Test scroll-in, scroll-out and collapse of the pinned Details title RED.
  Use the existing top spacing for the label and native scroll/disclosure
  events to keep it current. Verify GREEN.

### Task 3: Verify real inputs and hand over

- [x] Run focused report and relevant reader tests. Exercise bounded real
  NEMO/AROME, CROCO/Meso-NH and SURFEX samples with actual report widgets.
- [x] Inspect terminal screenshots while working. Update the Validate guide,
  run strict Sphinx and publication checks, and inspect the rendered guide.
- [x] Review the diff, commit locally, and report producer-level evidence and
  limitations without publishing or launching production processing.
