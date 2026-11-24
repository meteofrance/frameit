# Motion and feedback in the report terminals

Adapt the supplied motion handoff incrementally in both report commands.
Native Textual remains responsible for scrolling, workers, progress, toasts
and layout. Keep the existing theme, scrollbars, report projection, one-file
Inspect scope, validation semantics and CLI dispatch.

- Start-up: contextual status, native progress, and the supplied Braille mark
  where it fits. Cache the 24 frames; only the orange trajectory moves. On
  reduced motion or constrained terminals show readable static feedback;
  compact full-motion views can use Textual's small loading indicator.
- Refresh: previous evidence remains visible, explicitly identified, while a
  single worker checks saved edits. If no replacement report can be produced,
  mark the old report stale. A completed report with diagnostics replaces the
  old one. Copy actions cannot send stale evidence. Interrupt requests wait
  for the current reader to reach a safe boundary and retain exit code 130.
- Feedback: use only observed stage and per-source file counts. No invented
  aggregate percentage. Native toasts summarize results and actions, never
  replace persistent diagnostics or claim that OSC 52 reached a clipboard.
  In cramped layouts the notice uses one title row, not the report area.
- Interaction: native page scrolling is short; row and source selection are
  immediate. Keep focus and offsets when the same view and evidence survive
  refresh. A shared wide-view sidebar toggle hides the Inspect source picker
  or the Validate Findings list, never removes their content, and yields the
  space to the main pane. Compact views retain ordinary navigation; Inspect
  also has a direct Diagnostics shortcut for off-screen tabs.

Use Python 3.13 in `frameit_env` and the installed Textual 8.2.8 APIs. No new
runtime dependencies, configuration schema changes or changed scientific
methods. Inspect rendered captures before finalizing. Run independent
interactive usability passes, then the full suite once after their fixes.
