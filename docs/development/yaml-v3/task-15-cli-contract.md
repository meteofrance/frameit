# Task15 CLI consumer boundary

Technical choices within approved C9, not new scientific/human approval.
Basebde826b31957e67808f6219e175d3f960d7fd85e. Actual implementation/test evidence
and independent review must qualify these interfaces before Task16 consumes them.

## Reuse rather than another workflow

Use Task13's shared collectors/typed reports for same-file inspection, validation
and effective configuration. Task14 execution already binds once and wraps its
own facts. Do not preflight again merely to print a final summary.
Task12 portable records own status/actual products; never reconstruct a run from
the original archive to display them. Keep CLI formatting out of scientific math.

C9 exact common operational flags apply to validate/run/config show --effective:
output-directory, cpus, mutually-exclusive overwrite/no-overwrite and log-level.
Resolve CLI>YAML>defaults once with existing path-base/origin/request capture.
Plain config show displays authored data, not defaults or runtime mutation;
its --json is that authored mapping. Other C9 JSON reports use the frozen
version1seven-key envelope and separate effective-data sections, with one stdout
document, nonzero errors and stderr logs. Schema-only stays fully offline.

Retire only the explicitly retired dry-run/resolved public controls and their
help references. Preserve existing non-retired operational run controls unless
an actual C9 scientific-selection conflict is demonstrated. Existing publication
suppression remains an explicit recorded operation, not a new default or permission
to enable undeclared products. Do not add field/method/time-selection flags or
compatibility aliases. Record any necessary public-surface ruling before editing.

## Status spelling and exit choice

Use `frameit status <run-directory>` and a matching human final-run summary.
The exit policy follows Task12's existing acceptance states:

- Last-recorded completed/incomplete:0; label accepted incomplete tracking clearly.
- Last-recorded running/failed/interrupted:1; running is unfinished information,
  not evidence that a process is alive or dead.
- Missing/unrecognized/unreadable required records:1 with actionable guidance.
- Argument syntax errors retain argparse's2.

This is a lead technical choice from actual owned_run/execution states, not a
new completeness policy. Strict incomplete execution already records failed.
Read fixed portable metadata only; optional missing facts stay explicitly absent.
Show actual versus planned products distinctly, fields/paths, warnings/exclusions,
failure/pending context and ordinary-reader help. Do not scan scientific payloads
or claim file integrity/identity merely from a recorded path.
Never present stale/concurrent records as proof of the current failed attempt.
If an owning fact is needed for a truthful failure summary, identify that narrow
boundary before widening execution. Do not build a new run/event/result framework.
C9 requests JSON on inspect/validate/capabilities/effective and plain authored
config show; no additional status option is required for this task.

## Starters and editor information

Preserve write_template(name, path, *, tracking=None, coupling=None, force=False),
all model/named/composed/default/force/refusal behavior and actual selected
workflow. Existing test cases pin fields, levels, widths, wind basis, comments,
no dataset access and source safety; update their v3 structure without deleting
those semantic assertions. Public atmospheric/coupled names are atmosphere/
ocean/surface; parser source names remain arbitrary identifiers.
Do not preserve obsolete v2 text/defaults at the expense of frozen C1–C9 physics;
surface any workflow conflict instead of silently picking a scientific substitute.

Generate `schemas/config-v3.schema.json` from authoritative configuration
definitions. Share existing structural keys/choices/ranges with generation as
needed, without changing accepted scientific controls or building a new grammar/
plugin registry. Keep input-specific field names and scientific eligibility in
inspection/preflight, not the editor. Preserve arbitrary metadata.extra annotations,
omission/default/null rules and schema/version distinctions.
Package the generated asset; no new schema CLI command is requested.
Capabilities report implemented support, inputs/dependencies/limits and actual
documented maturity, not a roadmap or self-declared scientific validation.

The existing environment has build/setuptools/wheel but no jsonschema module.
No package/dependency changes are authorized. Do not install a validator or
write a homemade general JSON Schema engine to hide this. Test authoritative
definition/asset consistency, actual supported controls and wheel asset inclusion;
report unavailable independent standards-conformance validation honestly.
If required acceptance cannot be established, name that affected gate rather
than calling the editor fully qualified or blocking unrelated CLI work.

## Bounded author corrections before freeze

The retained suppression flags must actually filter only the local publication
list, including an empty selection; authored plans/scientific work and requested
track output remain unchanged. Writer retention/callback/drain semantics stay.

Current-attempt failure summaries may consume compact in-memory facts attested
by this invocation's actual yielded ownership context after unwind. Unowned
failures retain explicit unavailable inventory; old/concurrent records are never
used as ownership evidence. New handoff may not change public execution/result/
record schemas or writing, progress, science or resource policy. A finalization
failure cannot be printed as success merely because an earlier state was complete.
These two concrete extensions require TDD/preservation and independent15review;
task-15-boundary-ruling.md records their exact scope.

Review fix1 keeps authored JSON a plain mapping without defaulting or rewriting
the request, using the existing shared metadata projection for YAML-native
annotations: dates/timestamps become ISO strings, sets become arrays, binary
becomes a hex object, non-finite numbers become tagged objects and mapping keys
become strings. Authored YAML values remain parsed YAML values. This is a
representation convention, not a change to accepted scientific controls.
The generated editor's scalar float constraints must match the existing positive
numeric tracker widths; runtime widths/defaults/units remain unchanged.

Final Task15 review approves these consumers after fix1; both Important findings
are closed. STATE's frozen handoff records exact interfaces, current versus
PRE-fix1 evidence and qualification limits. This does not establish independent
schema standards conformance, installed-wheel/native/HPC or human acceptance.
