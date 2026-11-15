# Task13 shared report contract

Technical handoff within approved C9; not new scientific or human approval.
Base: `69e69923f2d827c724c03812ce248a67e08b41a2`.

## Boundary

Reuse the existing schema, inventory, prepare/bind and plan producers. A small
shared report projection/serializer is justified; another planner, diagnostic
framework, error-rule registry or event service is not.

Keep internal decoded times, bindings and scientific metadata intact. Build a
separate public view; never serialize and feed it back into execution. Native
metadata preflight remains discovery-only, with field/method-dependent facts
pending. Polar method planning keeps its existing selected checks and budgets.
Invalid or unfinished reports are not executable clearance.

Validate, run preparation and effective views must share the existing common
preflight producers/results, not independent reconstructions. Do not add another
preflight before execute_simulation, rebind children, or widen scientific reads.
Task14 consumes the resulting internal interface; freeze its actual signature
and payload in the handover after implementation/review.

## Public envelope

JSON report commands emit exactly these seven top-level keys:

```text
report_version: 1
command: inspect | validate | run | config show --effective | capabilities
status: ok | error
data: {configuration, origins, inputs, plan, pending}
warnings: [...]
errors: [...]
deferred_checks: [...]
```

`command` describes the operation, not the old CLI spelling used to reach it.
The command list reserves Task15 capabilities; it does not implement it now.
Plain authored `config show --json` remains an authored mapping, not this
envelope, when Task15 wires it.

The five data sections remain distinct. Configuration contains valid effective
controls or null when unavailable; pending markers never enter valid scientific
controls. Origins use the existing dotted-source facts. Inputs and plan show
actual metadata/selections/assumptions/dependencies/products/paths/resources,
not invented values for blocked sources. Keep the captured authored mapping
separate through Task12's existing request context.

`ok` means the requested checks/report ran successfully, not scientific validity
or completed execution. Unfinished inspection and offline schema-only can be ok
with explicit pending/deferred work. Required-invalid checks make status error
and a nonzero exit. Logs/progress go to stderr; JSON stdout is one document,
including expected schema/metadata failures. No fallback prose on JSON stdout.

## Diagnostics

Errors identify `path`, `message`, `expected`, `observed`, `repairs` and
`locations`. Use JSON-safe facts, a list of actionable repair strings, and
locations with file/line/column when known. Attach source/file/record context
when available. Explicit null/empty location metadata is appropriate for an
in-memory request without source marks, not a fabricated YAML line.

Preserve actual causes and meaningful scientific distinctions. Group genuine
repeats without dropping affected files/records or combining different expected/
observed physics. Independent source/file errors must survive one pass.
Checks depending on a failed prerequisite are explicitly blocked, with that
prerequisite identified; runtime/value-dependent checks are deferred, not passed.
Use deferred_checks to distinguish blocked, unfinished-selection and
execution-dependent work without introducing another public error service.

Human text must expose the same useful facts and repairs, not raw dictionary
repr or a second scientific interpretation. Keep error/formatting helpers small.

## Serialization and resource limits

Metadata projection must not compute scientific arrays, open more source data
or dump entire physical fields/geometry arrays merely to be JSON-serializable.
Show useful names, dimensions, units, selectors and selection facts; preserve
calendar identifiers with time labels. Do not flatten internal cftime clocks to
strings or infer equivalence/time zones.

Strict valid JSON must distinguish missing/unmeasured metadata from zero. Invalid
scientific nonfinite values remain errors, not silent filled controls. Reuse
the existing strict UniqueLoader; preserve duplicate-key/null/version rejection.
Capture YAML locations from the same authored text used for parsing, not a later
re-read of a potentially edited original.

## Task13 versus later CLI work

Task13 may add `validate --json` and the minimal existing handler/report routing
needed to test a real single-document/nonzero/stderr contract. Reuse common report
functions for current run-planning/effective-view handlers. Do not add another
scientific inspection source parser to repair the old directory CLI here.
Unfinished authored inspection is exercised through the common core report
interface; Task15 owns the complete same-file inspect command.

Retirement of old dry-run/resolved flags, all operational flags, complete
inspect/capabilities/status/editor-schema/init/help conversion remain Task15.
Task14 owns integrated execution/progress. No migration tools or newly
documented obsolete commands. New public command claims require actual tests.

Review this boundary against the brief; these are lead engineering decisions,
not permission to leave any Task13 requirement untested or a claim that later
CLI/producer/HPC/native/human gates pass.
