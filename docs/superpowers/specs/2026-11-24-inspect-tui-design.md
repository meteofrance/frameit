# Terminal dataset explorer for `frameit inspect`

**Status:** Approved for implementation: layout A and interactive-only sampling.

`inspect` helps a researcher see what is in their inputs and choose YAML
selectors. `validate` checks the requested processing plan. The two commands
share a terminal shell, not a meaning for a successful report.

## Approach

- **A — Wide workspace, numbered views when narrow (chosen).** Show sources,
  the field table and selected field together, with source tabs below. Use
  the same widgets and selection state at narrower sizes, one pane at a time.
- **B — Numbered views at every width.** Simpler layout, but it takes a view
  switch to compare a field with its details.
- Do not fork the validation app or add a plugin system. Extract only the
  pieces both commands actually use.

## One file per source

Sample only in interactive `inspect`. Keep the existing
full-inventory reports for `inspect --cli`, `inspect --json`, redirected
commands and terminal fallback. Changing what those reports describe would
change their meaning for existing scripts. `validate` keeps its current checks.

1. Use existing file discovery: declared path/glob order, sorted matches
   within each glob, exclusions, and physical-file deduplication. Pick the
   first eligible file in that order for each source. This is not a claim
   that it is the earliest timestamp or that the files are identical. If
   discovery returns an error, show it and do not open partial matches
   for that source. Continue to the other sources.
2. Read metadata from that file only. Discovery may list and stat other
   files, but must not open them as datasets. If the sample cannot be read,
   show its path and error; do not try a second file. If another source
   succeeds, keep it browsable.
3. Show the sample filename and `1 of N files inspected`. The Files tab
   distinguishes the sample, uninspected matches, and excludes. Keep
   known exclusions and failure reasons from discovery. Do not describe
   an unopened file as readable, structurally compatible, or selected by
   a time window.
4. Inventory the whole chosen file without applying the YAML's field,
   time or cycle selection. Show sample timestamps, clocks, calendars and
   reported intervals separately from the requested time window. Do not
   calculate archive coverage, gaps or cross-source alignment from a
   sample. A requested field, time or cycle not seen in that file is
   **Not seen in sample**, not an error about the archive. List absent
   field references separately from native variables.
5. Keep YAML syntax/schema, file discovery and metadata reader errors.
   Do not add request-to-data validation (for example, comparing
   declared units with file units) to the preview. Show those values
   separately when both are available; leave the existing comparisons
   to the full commands. For a selector, use the existing rules on the
   sample itself, without using the requested time or cycle to discard
   evidence of ambiguity.

Reuse `inventory_source_files`, the existing inventory scan and source
readers. Apply the one-file limit at the metadata-read boundary, before
archive selection and cross-source planning. Keep the resolved request
intact; do not drop YAML settings just to make ordinary full inspection
pass. Reuse discovered identities and the existing selector rules on
sample-local evidence. No payload reads, extra scan on navigation, or
new scientific matching rules.

## Shared code and CLI

- Extract the terminal dispatch and SIGTERM handling from `cli.py` once.
  Preserve the checks for all three TTY streams and usable `TERM`, the
  missing-Textual fallback, and `--json` taking precedence over `--cli`.
  Text and JSON paths keep the current collector, renderer and exit codes.
- Extract the existing header, footer, theme, worker, progress/ETA,
  refresh, status and diagnostic presentation into one shared shell.
  Compose it with a built-in validation or inspection view. Retain the
  `ValidationApp` entry point, widget IDs and keyboard behavior. Reuse
  `project_report`, the YAML and calendar-label formatters, and the
  existing diagnostic list/detail. No new dependency.
- Add `frameit inspect [config]`, defaulting to `frameit.yaml` like
  `validate`, and `--cli` for the existing text view. A missing default
  file yields the ordinary missing-config diagnostic; do not scan the
  directory for datasets. Only the interactive explorer uses the
  narrow sampling path. Forward existing metadata progress events to
  the shell. The scan total is one sample, not the number of matches;
  the shared ETA rule will not estimate from one file. Quit returns 0
  for inspection without errors and 1 on error, even with usable
  metadata from another source. Preserve Ctrl+C and terminal restoration.

## Explorer

Use standard Textual widgets: a source list, `Input` for search, a
`DataTable`, scrollable field details, and `TabbedContent` for source
details. Use Textual breakpoints for the layout rather than adjusting
font size. Start with wide mode at 120 columns and 30 rows; test compact
mode at 52×16 and a live resize. One widget tree; resizing must preserve
the selected source, row and filter. Keep the navy, teal and amber
palette, red error text, and plain status headings.

```text
FrameIt / inspect                                          frameit.yaml
Sources                 Variables                        Field
> atmosphere            Name  Units   Dims  Requested    Native metadata
  1 of 355 inspected    ...                              YAML selector
  surface
  1 of 12 inspected

Source [Overview] Coordinates Time Grids Files Origins Diagnostics
Sample: <filename>  ·  1 of 355 files inspected

1 Sources  2 Variables  3 Field  4 Source  r Refresh  q Quit
```

- Numbers focus panes in wide mode and open them in compact mode.
  Tab and arrow keys navigate; `/` searches, `s` selects a sort,
  `f` filters request status, and `c` copies the selected selector.
  Typing into search must not activate those shortcuts. Use a compact
  footer so `r` and `q` are visible at the tested narrow width. Keep the
  active source and sample scope visible in compact views.
- Keep separate rows by source and native field ID. Show reported units,
  dimensions and group/grid evidence. **Requested** means the field is
  uniquely named by `sources.*.variables` or an explicit product field
  list. Show ambiguous references as **Unresolved**, and other fields
  as **Not requested**. Dependency-only roles belong in the detail, not
  the requested filter. Copy availability is separate from request
  status. Display shape, coordinates, origins, reported roles and method
  evidence only when established; otherwise show **Not reported**. Do
  not infer method eligibility.
- Copy one report-provided YAML fragment and show its destination under
  `sources.<source>.variables`. Use Textual's clipboard API; keep the
  fragment visible if a terminal refuses the copy. Do not merge into or
  write YAML. Only associate a selector with a row when the report makes
  the match unique; otherwise list it with the source. Never offer a
  selector for an unresolved name as if it were valid.
- On refresh, re-read the saved YAML and clear stale copy/results while
  checking. Restore the selected source/field if still present. No
  selection required to browse; with malformed YAML or no readable
  sample, focus the shared diagnostics. Show scoped errors without
  hiding readable sources.

## Verification

- Reuse the validation TUI tests and mirror its dispatch matrix for
  `inspect`, including flags, redirects, absent Textual and interruptions.
  Compare old text/JSON reports and exit codes on explicit paths.
- Cover complete, unfinished, malformed and partially failed requests.
  Spy on file opens for two multi-file sources: one distinct dataset
  path per source, after excludes/deduplication, and no retry if the
  sample fails. Check that a discovery error does not open a partial
  match. Reuse NetCDF/GRIB payload guards. Include a time window and
  a configured field found only in an unopened file: neither is a
  sample failure. Cover duplicate field names across cycles without
  copying a misleading selector.
- Exercise keyboard navigation, search/sort/filter, resize, selector
  YAML round trips, ambiguous or same-name fields, and refresh. No
  source files or YAML are modified and no processing outputs appear.

Do not add an archive auditor, sample picker, YAML editor, plots, or
heuristic gap/eligibility rules. Keep the existing full inspection path
available for researchers whose files differ.
