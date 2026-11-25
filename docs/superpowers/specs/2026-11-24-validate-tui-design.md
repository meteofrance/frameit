# Experimental `frameit validate` terminal interface

## Intent and approaches

Test whether a keyboard-first interface helps researchers confirm what FrameIt
understood, find the next repair, and tell whether slow validation is advancing.
The maintainer chose a tabbed overview over one scrollable report with jump keys:
the latter has fewer controls, but long reports can bury the summary.

Use standard Textual widgets and status labels that work without color.
Use navy (`#021633`), off-white (`#E6EDF3`) and slate (`#A6B4C4`) for the
background, body text and secondary text. Reserve teal (`#49C5BC`) for focus,
active tabs and progress, amber (`#F5B55E`) for warnings and repair cues, and
red (`#DA5656`) for errors. Each tab scrolls independently. Tab titles do not
include shortcut numbers; the footer shows `1`, `2`, and `3` for navigation.

## Result views

- **Overview** opens first. Show the config path, check mode, and verdict. Summarize
  the sources, fields, times, region or tracking choice, and planned outputs
  that the report establishes. Distinguish a configured request from a resolved
  plan; label missing or unconfirmed facts. On failure, show the first repair.
  After a full pass, point to `frameit run` with the same operational overrides
  and call out any warnings to review. After a schema-only pass, point to
  input-aware validation. A pass does not establish execution or scientific validity.
- **Findings** shows validation messages, not computed scientific diagnostics.
  Group errors, warnings, blocked checks, and deferred checks separately.
  Browse with the arrow keys. Show error codes, config keys and YAML locations
  where available, repairs, expected and observed evidence, and the existing help
  path. Warnings are non-blocking. Blocked checks name their prerequisites;
  deferred checks explain what was not checked.
- **Details** shows the read-only effective configuration, setting origins,
  and processing plan from the existing report. Label outputs as planned,
  not published. Show when no plan is available.

## Progress and controls

Keep the TUI responsive while the existing validation runs. Show the current
stage and elapsed time. During an input scan, show files checked versus the
total for the current source. After enough files finish to measure a rate,
show a rough ETA for that source's scan only. Reset the estimate for each
source and revalidation. Do not estimate a percentage or finish time for
the rest of validation.

On a completed report, `r` rereads the same YAML and revalidates with the same
flags; `q` returns to the shell so the user can edit and rerun there. Do not
overlap checks or leave old results presented as current during revalidation.
No file watching, editor launch, in-TUI editing, or run action.

## Command and implementation boundaries

`frameit validate config.yaml` opens the experiment on a usable interactive
terminal when the optional Textual extra is installed. `--cli` forces the
existing text view; `--json`, non-interactive use, and environments without
Textual keep their existing behavior. Keep `--schema-only` and operational
flags working. Quitting a completed TUI returns the latest report's existing
validation exit code. A validation without a completed report must not exit
as a success.

The Textual layer consumes the same projected report as text and JSON. Add
only the optional notifications needed at actual validation stages and file
boundaries, with no Textual dependency in the scientific core. The optional
extra adds Textual, which brings Rich for rendering; there is no separate Rich
interface. Do not change validation decisions, report formats, or
`frameit inspect`. Implement on a temporary local branch after approval; do not
push.

## Trial

Use small fixtures for an input-aware pass, invalid YAML, and an incomplete
selection, plus a schema-only check. Verify progress and ETA, narrow terminal
scrolling, deliberate revalidation after editing, and text/JSON exit-code
parity. Give the maintainer commands to repeat the trial and invite feedback on
the summary, repair workflow, and progress during slow checks.
