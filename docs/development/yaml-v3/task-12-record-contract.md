# Task12 record contract — frozen for Task15

Technical handoff within the approved checklist, C7 and C9. These are lead
implementation decisions, not additional human/scientific approval.
Base: `c7d1c658f6b9e7df0f69439e014efb42b5abaa57`.

## Approach

Use one new `run-request.yaml` snapshot and extend the existing status/provenance
checkpoints. Separate authored/override files would add unnecessary coordination;
a journal, database or recovery service would exceed this task. No implicit
replay, archive copying, source hashing, resume or data-model change is requested.

## Record names and meaning

All four records live directly under the owned output root:

- `run-request.yaml`: immutable captured request/context for this attempt.
- `resolved-config.yaml`: valid effective v3 controls, not proof of completion.
- `run-provenance.yaml`: available processing facts and actual publications.
- `run-status.yaml`: authoritative last-recorded attempt state and inventory.

Keep the existing status record `schema_version: 1` and state vocabulary.
The request is a metadata envelope, NOT a runnable public configuration:

```text
record_version: 1
request_kind: yaml | mapping | runtime
authored_configuration: original parsed mapping, or null if unavailable
request_path: original absolute YAML filename, or null for non-file callers
path_bases:
  configuration_directory: absolute base used to resolve authored paths
  launch_directory: original absolute launch base for operational path overrides
overrides: original operational override mapping, without scientific selections
requested_execution_options: supplied options before automatic resource resolution
runtime: existing runtime_provenance facts, including available code identity
```

Capture a deep copy BEFORE path/default/override resolution, while loading the
file/mapping. Do not re-read the original YAML during execution. Preserve parsed
values and omissions; this does not promise source bytes, comments, formatting,
or verified identity of input archives. Runtime-only constructors must label
unavailable authored information honestly, not relabel resolved controls as raw.
Nulls here are metadata for unavailable facts, not allowed scientific controls.

Existing `resolve_operational_overrides` semantics remain authoritative:
CLI > YAML > defaults; YAML paths use `configuration_directory`, explicit
operational paths use `launch_directory`. Mapping paths use their captured
configuration base. The saved request retains these bases even if its file is
moved or edited. Do not resolve authored paths against the output root. Source
inputs need not remain available for a later status reader to explain the attempt.

The request is written once after exclusive ownership, before processing.
It participates in no-clobber, source-alias/containment and explicit-replacement
safeguards. A new authorized replacement attempt may replace recognized records;
the running attempt must not rewrite its request as effective facts accumulate.
Unknown files, orphan partials/backups and old failure evidence are not cleanup
targets. Reject unsafe collisions rather than silently deleting them.

## Status and provenance interface

Preserve existing resource/options/runtime/error/tracking fields. Add:

- `request_record: run-request.yaml` (run-relative filename).
- `planned_products`: common request-plan descriptors, with run-relative paths.
- `products`: only actually complete publications, retaining current descriptor
  meanings and run-relative paths; never populate from planned/scheduled work.
- `pending`: a list of unresolved phase names, using `processing`, `publication`,
  and `cleanup` where applicable. Completed work is removed only when observed;
  failed/interrupted work keeps its unresolved phases. No percentage or ETA.
- `updated_at`: ISO UTC time of the last persisted checkpoint, not a heartbeat
  or liveness claim.

Use these fields consistently in status and applicable provenance checkpoints.
Keep valid effective controls separate from pending metadata. Save effective
resources/configuration/known binding facts when available; do not wait for all
scientific processing before creating any provenance.

The parent checkpoints each successful publication after the atomic writer
returns. It must already appear in the running on-disk inventory before later
work can fail. Keep the same completion boundary for synchronous and spawned
exports; never send a status callback into a child worker.
Record complete products even when another product or checkpoint fails; do not
claim failed/partial outputs as complete. Cleanup and normal finalization retain
their existing failure propagation.

## Recovery limits

Use existing atomic YAML and product publication, not a cross-file transaction
or durability guarantee. SIGKILL/native crash/node loss may leave the last
checkpoint running, a lock, an uncheckpointed publication, partial or Zarr backup.
Neither a stale lock nor `running` proves a live process. Do not reclaim ownership,
repair/delete products or scan scientific payloads automatically.

Preserve Zarr replacement's documented visibility gap and rollback on caught
errors. Status summaries must distinguish last-known inventory from a complete
archive audit. Task15 consumes these names/fields; it must not infer success from
an effective configuration, a product path or a merely planned descriptor.

## Acceptance

Task12's exact checklist tests remain binding. Cover early post-ownership failure,
captured YAML edit/move and mapping mutation, separate path bases/overrides,
actual first-publication failure/interruption in both export modes/formats,
existing locks/artifacts/explicit replacement, stale running/partials and Zarr
replacement failure. Preserve all C4/C6/C7/C8 calculations/read boundaries.
Independent review and local commit precede Task13.
