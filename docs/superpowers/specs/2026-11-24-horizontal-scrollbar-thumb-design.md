# Quarter-row horizontal scrollbar thumbs

**Status:** Approved for implementation.

The shared native styling made the tracks quieter, but the horizontal thumb
still paints a full terminal row. In `frameit inspect` Variables and
`frameit validate` Details, paint only the bottom quarter of each thumb cell
with `▂`. Keep the full one-row mouse target and the existing reserved gutters.

## Approaches

- **Keep native TCSS alone:** This is the smallest option, but Textual sizes
  scrollbars in whole cells. More color changes would not thin the thumb.
- **Use Textual's per-instance `ScrollBar.renderer` hook (chosen):** Reuse
  native rendering for geometry, colors, and mouse actions. Change only the
  thumb cells' paint in the two horizontal scrollbars. Do not change vertical
  bars or patch the class globally.

Use Python 3.13 in `frameit_env` and the existing Textual minimum of 8.2.8.
No private APIs, dependencies, new settings, or CLI and scientific changes.
Keep verification targeted; the full suite remains deferred.

Compare matched Batsirai captures of the in-use views: Inspect dragging
horizontally, and Validate scrolled vertically with its horizontal thumb at
rest. Check that a one-column overflow is still draggable, that fitting
content has no visible thumb, and that the table does not move when it fits.
