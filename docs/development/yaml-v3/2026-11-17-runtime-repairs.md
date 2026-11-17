# Retained runtime repairs — 17 November 2026

Internal engineering evidence, not scientific qualification or human acceptance.
Base: `2c295accae8b1267f9f344d149fdced4dc0ec1f4`.
Plan: `2026-11-17-runtime-repairs-plan.md`.

## Scope and contracts

The maintainer authorized repair of the 26 failures retained by the stale-test
audit. All 26 reproduced, with zero errors/skips, in
`/tmp/opencode/frameit-runtime-red-20261117.{log,xml}`.

- Inventory and regional selection now recognize conventional Meso-NH U/V
  geography without requiring redundant CF standard names. Conflicting-identity
  diagnostics retain coordinate attributes, including units and providers.
- Polar sampling retains the operation time on transformed horizontal
  auxiliaries. Exact merges remain enforced; no coordinates/provenance are
  discarded to hide conflicts.
- Native-sampling preparation no longer replaces an inventoried native-grid descriptor
  under that native grid ID. Operation-local prepared geometry remains available,
  but unrelated model-grid axes retain their identity and collocation. Genuine
  remaps retain destination records even when their identity matches an existing
  native mass grid.
- Named-source manifests retain actual CROCO current-preparation records and
  unknown GRIB headers with native attributes/locators. Current records reuse the
  existing method definition and identify actual component input basenames;
  scalar-only work does not acquire current-analysis records.
- Status copies the actual centre time-association record, rather than testing
  a retired configuration branch.
- Centroid admission checks the associated operation sequence, not only the
  atmosphere's source inventory. At least two distinct times remain required;
  native selections are not silently shortened.
- The maintainer explicitly chose geographic trajectories over restoring legacy
  track indices. FA lookup conventions, selected geography, offsets and units are
  retained per source/grid in region provenance. The two reader regressions keep
  their original index/offset truths and tolerances at that location.

No numerical method, interpolation tolerance, masks, unit-conversion rule,
vector basis, physical reference frame, diagnostic default or dependency changed.
Manifest additions and the geographic-track clarification are documented in
canonical output/FA/ocean guidance; centroid guidance identifies the actual
operation-time requirement. There are no configuration keys or migrations.
Sampled horizontal polar auxiliaries now retain time rather than falsely
appearing invariant; untouched leading/scalar metadata keeps its existing axes.

## Later stale assertions exposed

Repairing early failures reached additional assertions that contradicted current
documented contracts. These were replaced without weakening physical checks:

- Native-grid crops are independent, not N+1 cell-bounding collections. Source
  samples are selected independently from each face's own geography and compared
  exactly (or at the unchanged existing analytical tolerance).
- Native coordinates retain original units and flags. Velocity-unit transforms
  do not silently convert coordinate labels or invent basis attributes. Tests
  retain source metadata and explicit-operation sampling/basis checks.
- Timestamp values, exclusions, ordering and associations remain exact; optional
  trailing fractional zeroes are not a scientific difference.
- Input/lazy-view inventories are not payload-read counts. Tests check exact full
  inventory sets separately from exact actual FA payload-read sets, retaining
  exclusion, ordinary-reader, mask/value and source-read-only checks.
- The writer is lossless, not universally float32. The point-sampling check keeps
  its exact original float32-rounded analytic oracle by rounding the comparison,
  without downcasting higher-precision outputs or changing interpolation.

No skips/xfails were added, scientific payload fixtures were not rewritten, and
existing numerical tolerances were not relaxed.

## Verification before integration

All Python checks use Python 3.13 in `frameit_env`, the checkout's absolute source
`PYTHONPATH`, and the approved existing fixture. The audit's one-native-thread,
Agg and `/tmp/opencode` settings are retained.

| Check | Observed result |
|---|---|
| Grid representations + native extraction | 63 passed |
| Native/polar metadata + eager/lazy + two real-FA moving-mask cases | 64 passed |
| Generated AROME/Meso-NH centroid positives and invalid inputs | 9 passed |
| FA mapping/replay + v3 regions | 79 passed |
| Last two shared-polar cases, including native-only invariance and original reader | 2 passed |
| Genuine remapping + complete v3 operations + grid isolation/interpreter cases | 58 passed |
| Final unfiltered feature suite | **3213 passed / zero failures/skips / 4 passing subtests** |
| Strict Sphinx HTML build, iteration `runtime-repairs-05` | Passed |
| Publication boundary/link check | Passed |
| Supplementary publication tests | 16 passed / 40 passing subtests |
| Approved fixture SHA256SUMS before and after final suite | All nine passed |
| `python -B -m pip check` | No broken requirements |

Focused command/result details remain in the task ledger and
`/tmp/opencode/frameit-runtime-*.{log,xml}`. A connected foreground attempt hit
the shell's 120-second timeout and left no surviving test process; its background
retry completed, exposing the later FA assertions described above.

The large connected run reached **535 passed / four failed / zero skips**.
A fresh bounded read-only review found one Important issue, no Critical/Minor
issues and no declined judgments: the four reader failures exposed actual
optional-polar interference with native model-grid axis identity, not obsolete
index-name coverage. The reader checks remain intact. A new comparison reproduces
the change against native-only output, including accidental independent axes for
collocated fields; native inventory is now kept authoritative.

The new native-only comparison failed before the registration fix and passes
after it. Both standalone interpreter cases and the Meso-NH positive guard pass.
A retained-node run then reached 26 passes / two later quality-field assertions;
adding the documented per-field geometry flags to the exact expected inventory
and checking their role/values brings both final cases to passes in 44.93 s.
The existing independent native reader was not relaxed or replaced.

The first unfiltered runtime suite completed with **3212 passed / one failed /
zero skips / four passing subtests**, 9756 warnings, 1537.00 s, exit 1. All 26
original retained nodes pass. The single new regression is
`test_v3_operations.py::test_mass_transform_keeps_one_sampling_grid_with_per_record_rotation`:
the initial grid-ID membership guard suppressed a genuine mass-remap destination
whose identity equals a native mass grid. The test is retained unchanged.
Registration now distinguishes native sampling from actual remapping instead of
assuming every native-ID match is a native-copy operation.

The refinement passes **58 focused checks**, zero failures/errors/skips, 529
warnings, in 102.37 s. This includes the complete operations module and both
native-grid invariance/ordinary-reader and interpreter shutdown paths. The second
unfiltered feature suite is **green: 3213 passed, zero failures/errors/skips,
four passing subtests, 9756 warnings, 1531.65 s**, exit 0. XML counts 3217 cases
including the four subtests. All 26 original retained failure nodes pass.

Exact first full command from the repository root:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLBACKEND=Agg TMPDIR=/tmp/opencode conda run --no-capture-output -n frameit_env python -B -m pytest -q --junitxml=/tmp/opencode/frameit-runtime-full-20261117.xml > /tmp/opencode/frameit-runtime-full-20261117.log 2>&1
```

No modules, nodes or markers are selected/excluded, fail-fast is not used, and
warning/collection policy and approved fixtures are unchanged. All 18 modified
source/test/public-doc files were SHA256-snapshotted before this run in
`/tmp/opencode/frameit-runtime-frozen-inputs-20261117.json`.
The second full run uses exactly the same command/environment with
`frameit-runtime-full-02-20261117` log/XML names, against the refined registration
condition; its 18-file snapshot is
`/tmp/opencode/frameit-runtime-frozen-inputs-02-20261117.json`.
All 18 frozen files still match after that green run. The three additional
ordinary tests are the separate U/V inconsistent-geography cases, the sampled
horizontal auxiliary-clock guard and native model-grid/mass-polar optionality.
The previously existing mass-transform regression remains unchanged.
Latest Ruff comparison: 90 baseline / 88 current diagnostics, zero introduced;
this is not a clean-repository lint claim.

## Documentation impact and integration gate

Commands, configuration keys/defaults and installation dependencies are unchanged.
Processing restores declared native-grid, sampling-clock and tracker-admission
contracts. Output changes are additive provenance records and correct time axes
for sampled horizontal auxiliaries; native model-grid naming is stable across
optional polar processing. Canonical output, FA geometry, ocean and centroid
guidance is updated. No figures or template commands needed changes.

The maintainer authorized a local commit followed by merging into `develop` after
the green feature suite. Commit and local integration are the next operations;
the merged result must pass the same unfiltered suite before final handover.
This is not permission to push, release or claim scientific/human qualification.

## Limits and resource boundaries

The four changed documentation pages were opened in the live GUI. Rendered
layout/text checks at desktop and an actual 320-CSS-pixel iframe viewport found
no horizontal overflow. Screenshot inspection was blocked by a non-visible
desktop tab; pixel-level review and actual human acceptance remain open. The
preview is retained; its local server/tab ownership is in the session handover,
not committed machine state.

Existing NumPy binary-size and netCDF4/xarray deprecation/future warnings remain;
no environment repair was attempted. These engineering checks do not establish
general real-producer or scientific validity, installed-package qualification or
merge/release readiness.

The maintainer subsequently authorized local commit/merge into `develop` after a
green full suite, with a full verification on the merged result. Screenshots are
explicitly unavailable; rendered layout checks and retained preview are used
without a pixel/human-acceptance claim.

No installations, production/HPC jobs, downloads, benchmark campaigns, reserved
full-diagnostic campaign or pushes were performed. PNG smokes remain
restricted to the final unfiltered suite; their generated images are not viewed.
