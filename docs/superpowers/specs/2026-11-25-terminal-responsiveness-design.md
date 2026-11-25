# Terminal report responsiveness

Keep FrameIt's Inspect and Validate terminals responsive while they read and
prepare metadata. On the current branch, the longest measured gap between logo
draws is about 0.5 s in Meso-NH/CROCO Validate and 1.4 s in SURFEX Inspect.
Large metadata serialization and native dependency work can hold Python's
interpreter lock even inside Textual's background thread. Queued Inspect search
events also rebuild the same table repeatedly.

## Approaches

- Reuse a single local helper **behind** the existing Textual worker (approved).
  This isolates the interpreter lock without changing data reads or the report.
  Reuse the helper on refresh to avoid repeating dependency imports. Benchmark
  the extra process's startup and memory cost.
- Keep the same interpreter and optimize drawing and search only. This is
  smaller, but a higher frame rate cannot prevent the measured stalls.
- Alter the readers or coordinate fingerprints to yield more often. Rejected:
  this couples UI latency to individual scientific backends and risks changing
  report identities or making validation slower.

## Design

- Run only live Inspect and Validate collection and canonical projection in the
  helper. One operation at a time. Keep the existing progress stages, warnings,
  completed result and cooperative cancellation. Ctrl+C can be received during a
  native stall; a read may still need to finish before the older view is restored.
  Restart on retry if the helper has exited, and reap it when the app closes.
- Keep the original geometry, colours, two-second sweep, compact fallback and
  reduced motion. Use cached Textual frames and a monotonic clock for a smoother
  24 fps target, without artificial minimum wait times.
- Ignore superseded Inspect search events and reuse the table when the latest
  query leaves its rows unchanged. Keep selection, exact field identities and
  native navigation.
- No new flags, dependencies, scientific methods, backend parallelism, report
  keys, exit codes or changes to non-interactive and historical reports. No
  production processing, downloads, push, merge, or full-suite rerun.
