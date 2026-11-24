# Research console for experimental `frameit validate`

The Batsirai trial made the verdict compete with raw paths, YAML and notes.
Make the result easy to scan before asking the researcher to read the report.
This revises the presentation only, not the
[original prototype's validation scope](2026-11-24-validate-tui-design.md).

## Approaches

The maintainer chose **A: Research console**. It uses a single reading column,
quiet separators and a next-action line. **B: Run dashboard** grouped the same
facts into tiles, which scan well at wide widths but take more space when
stacked. Prefer A for narrow terminals and SSH.

## Views

- **Overview:** Use a slim `FrameIt / validate` header with the configuration
  name. Lead with the verdict and a short Inputs / Selection / Region /
  Outputs summary. Show counts and the selected time span when available;
  keep full field lists and paths in Details. After a pass, show the next
  command with any operational overrides. On failure, surface the first
  repair near the verdict and mark unconfirmed facts as such. No raw YAML.
- **Findings:** Keep errors, warnings, blocked checks, field discovery and
  run-only items distinct. Make each row distinguishable by code or subject;
  retain the full reason, repair, location and evidence in the selected detail.
  Use a quiet, visible focus marker rather than a bright filled selection.
- **Details:** Present effective configuration, setting origins and the plan
  as three labeled, expandable blocks. Start with the blocks collapsed.
  Keep the contents read-only and preserve indentation. Label partial plans
  and candidate output paths explicitly.
- **Progress:** Keep the stage, elapsed time, file count and existing scan-only
  ETA in a compact status line. While checking, show the interrupt shortcut
  instead of advertising inactive revalidate or quit keys. Keep the existing
  shortcuts after completion and each tab independently scrollable.

## Boundaries and trial

Keep the existing navy, teal, amber and error red (`#DA5656`) palette, with
explicit labels and readable focus even without color. Use stock Textual
widgets. Do not add a dependency, change report data or scientific behavior,
or touch `inspect`, `--cli` or `--json`.

Keep the current prototype as a baseline on `tmp/validate-tui`. Compare
real Batsirai and invalid-YAML captures in normal and narrow terminals.
Verify keyboard navigation, scrollable Details and the existing
revalidation and progress behavior. Send screenshots in chat for feedback.
