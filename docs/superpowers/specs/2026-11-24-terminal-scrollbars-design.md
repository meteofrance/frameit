# Shared terminal scrollbars

**Status:** Approved for implementation.

Make scrolling cues quieter and consistent in `frameit inspect` and
`frameit validate` without moving content or changing how it scrolls.

## Approaches

- **Native shared TCSS (chosen):** In `ReportApp.CSS`, make report, list and
  table scrollbars one cell thick. Use transparent tracks and match the
  corner to the theme background. Dim the existing teal accent at rest,
  brighten it on hover, and use full color while dragging. Remove the old
  focus-specific thumb color.
- **Custom quarter-cell glyphs (conditional):** Consider the documented
  `ScrollBarRender` extension only if the native captures still look too
  heavy. Preserve the full mouse hit area. No global patches, private APIs,
  dependencies, or new styling layer.

Reserve a stable vertical gutter. Only Variables and Validate Details need
horizontal scrolling: reserve their one horizontal row even when no thumb
is needed. Hide the compact source picker’s bar without disabling scrolling
or reserving blank space. Keep bars on longer reports, diagnostics and tables.

Compare the actual Batsirai views before and after at the same size and scroll
position. Check keyboard/wheel navigation, mouse hover and drag, and stable
content geometry. In `frameit_env` (Python 3.13), run only the targeted TUI
tests; the full suite remains deferred. No CLI, configuration, or scientific
output changes.
