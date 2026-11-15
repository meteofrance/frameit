# Task14 execution/progress boundary

Technical handoff within the approved C9 checklist, not new human/scientific
approval. Base106812d83d0ace0a0930c52409c43b3bbd1d9f32.

Final: Task14 independently approved after the A1 correction. The candidate/
pending notes below retain their historical wording; STATE's frozen Task14
handoff records final interfaces, verification limits and downstream consumers.

## Smallest approach

Reuse RunTimer, scoped standard logging and existing operation/publication
boundaries. Boundary-only logging cannot explain long quiet work. A general
event bus, worker telemetry service or payload/task-progress scanner is unnecessary.
Use one small owned quiet-work reporter in utils/logging.py, with a testable
monotonic clock, bounded waits and a minimal current-operation/source/count state.
A passive owned thread is permitted for quiet synchronous/native work; no
additional computation or multiprocessing pool.

The existing matrix uses a30second quiet notice. Treat30seconds as the initial
internal interval candidate, not an evidence-free frozen default. Prove useful
quiet updates and bounded messages/overhead with deterministic clocks and one
small synchronized real quiet-work check, then record the chosen default and
actual helper signatures. No new YAML/CLI progress control is requested.

## Selected plan and completion boundaries

execute_simulation consumes its existing owning prepared_sources tuple once.
Wrap prepared_sources[0] using preflight_result(conf, facts, command="run");
preserve facts identity/decoded clocks and common product descriptors. Do not
call collect_preflight or a second inventory/binder, serialize an executable
plan back into execution, or copy scientific selections into another planner.
Do not dump large typed plans into SimulationExecutionResult.to_dict or run records.

Progress distinguishes:

- preparing metadata/selected source plans;
- preparing/loading lazy source views and calculation graphs;
- actual tracking/calculation when it really occurs;
- computing/writing exports and observed complete publications;
- cleanup and finalizing records.

Preparing a lazy dataset is not completed computation. Never force a compute,
read a physical field, enumerate a graph or scan output data to obtain progress.
Existing parent publication descriptors/callbacks are the source of completed
product counts. Scheduled futures and planned products are not completions.
Counts and labels may cover observed prepared sources or completed operations,
but must state that unit rather than imply completed field values.

A new progress message identifies current operation/source where known, honest
completed counts, elapsed time and age of last real boundary activity.
Quiet notices must not themselves advance counts or last real activity.
No percentages, ETAs or performance/memory guarantees. Rate-limit repeated
activity as well as quiet updates; allow bounded start/terminal notices.

## Lifecycle and safety

Logs/progress stay on stderr and applicable existing log files; never contaminate
C9 JSON stdout. Honor existing log levels and restore caller handlers/settings.
Slow preparation needs progress before scientific binding completes, without
creating output roots/log files before ownership/path/resource safety allows it.

Every reporter must stop/join on success, incomplete tracking, exception and
BaseException interruption. Stop it before its handlers close. Keep scalar
snapshots thread-safe; reporter code must not touch datasets, native backends,
writer futures or scientific mutable plans. No orphan reporter after a run,
repeated run, scoped logging change or spawned-worker completion.

Task12 status/provenance remain authoritative. Do not write status on heartbeat,
change updated_at into liveness, duplicate publication callbacks, skip graceful
draining or replace actual descriptors with counters. Preserve pending/error/
cleanup facts and earlier complete products.
Never announce final success before cleanup and ownership/record finalization
succeed. Distinguish an accepted incomplete track from completed work. Do not
hide a primary scientific error behind progress teardown.
SIGKILL/native crash/node loss still cannot guarantee Python cleanup or final logs.

Existing scientific methods/defaults, selected reads, units/axes/clocks, W/speed,
mask/precision/CF, resource/chunk/cache/profile and ownership contracts are frozen.
No UI dependency, mandatory diagnostic, output schema or package dependency.
Full CLI flags/final command/status presentation remain Task15.

## Acceptance

Task14 brief/exact command remain binding. Use compact public-execution cases
for no-region native, independent clocks, sparse tracking/derived support,
explicit transforms, track-only and polar-only. Check original values/metadata/
source hashes with ordinary readers, not only log snapshots.
Quiet preparation/lazy compute/export and failure/interruption tests must assert
no extra scientific reads/eager compute, bounded messages, last-activity honesty,
stopped threads/restored logging, and agreement with actual final publications/
incomplete status. Final helper/interval choices are evidence-backed and receive
independent review before Task15 consumes them.

## Frozen candidate interval and interfaces — review pending

The implementer selected30seconds with deterministic3600tick/30boundary output
bounds and one synchronized real shortened-interval thread/stop check.
Repeated INFO notices are bounded to120/hour plus start/terminal notices.
This is not a real-time/native-throughput guarantee; interpreter/GIL or logging
I/O can delay notices/stop. No new public control is added.

Candidate implementation uses _QuietProgress in existing utils/logging.py with
update/start/stop/finish and an injected monotonic clock. Public execute/runner/
logging signatures remain; logging scope accepts None for early stderr-only
ownership. Execution wraps its already-owned typed preflight facts and keeps
the same tuple/children/bindings. Final logging lifetime includes cleanup and
run-record/ownership finalization. Actual writer/source during spawned export
is explicitly unknown, not inferred from future scheduling.
These are frozen author interfaces/claims, pending lead evidence and independent
spec/quality review; not new human or scientific approval.

A1 correction adds reconcile_published(count): set the actual retained total
under the existing scalar lock, without advancing activity or emitting.
Execution calls it after export/drain/recovery before cleanup/terminal output.
This closes missed-callback counting without callback replay or double count;
writer retention and Task12 records remain authoritative and unchanged.
The corrected candidate is still awaiting independent whole-Task14 review.
