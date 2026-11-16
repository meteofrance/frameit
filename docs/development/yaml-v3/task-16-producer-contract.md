# Task16 producer and example boundary

Technical consumer handoff within approved C9/C10, not new scientific approval.
Base40f9bcdb4429fe1755aab871c2b7f9d5916af51e. Task15's frozen handoff owns CLI,
starters/status/schema; C1–C9 own scientific and output meaning.

## Approved C3 extension

On2026-11-16 the maintainer approved optional vertical-group requests with
`names` and local `levels`, retaining flat lists/source-wide levels for simple
requests. This supersedes the temporary C3 disposition hold, not the scientific
preservation requirements below. The core extension needs its own specification,
tests, end-to-end verification and independent review before producers consume a
frozen handoff. Preserve height indices `[0,2,5]`, pressure values
`[1000,850,400]`hPa and all original AROME field identities.

The partial producer work is preserved, not complete. The three separately
reported NetCDF/CROCO core defects remain outside this authorization.

## Reuse existing producers and actual products

Convert the existing catalogue/recipes, matrix, benchmark and canonical examples
directly to v3. Preserve case IDs, source quantities/units, grids, levels, clocks,
missing values, vector conventions and requested workflow. Do not add a public
v2 converter, compatibility aliases, second planner or replacement catalogue.
Catalogue1, artifact1.0, report/record1, package and FA-protocol versions are
separate from configuration3.

Keep existing helper and producer signatures, including document(tmp_path,
**sections), dataset(...), check_products(case, products) and catalogue entry
points. Update all callers together; a flexible **sections signature is not a
requirement to keep accepting retired public configuration blocks. Do not make
production runtime accept old syntax to avoid converting tests.

check_products must use actual execution descriptors and C7source/product paths,
dimensions/coordinates and each product's declared source clock. A shared centre
or exported trajectory does not give every source the same time axis. An exported
track is optional. Preserve existing numerical/coordinate/mask checks and the
explicit distinction between contract checking and independent scientific reference
validation. No globs, universal finite-everywhere rule or scientific threshold
invented to make a checker pass. State the checker's actual format scope.

The two named new acceptance tests exercise real execution/checker and one small
benchmark preparation/execution path, with bounded resources and ordinary-reader
checks. Mocked launch tests are not substitutes. Preserve the benchmark's declared
continuous origin motion and numerical comparisons; do not run a campaign.

## Caller and scientific safeguards

Restore old scientific/privacy/error scenarios with valid v3 requests, rather
than expecting an earlier argparse/unknown-key failure. Task15's two newly
rejected callers and20changed-root cases are linked in task-16-preparation.md.
Keep native FA privacy/runtime/metadata-only assertions, selected-read guards,
source/no-clobber checks and independent values/tolerances intact.
Do not replace a quantity, infer a basis/unit, widen a time selection, change a
physical mask/default or lower an assertion merely to recover a test.

If a legacy example cannot express the same science under an admitted v3 method,
record the concrete conflict and stop that adaptation for a lead/scientific
ruling. Do not silently present another workflow as equivalent. Runtime science,
reader/writer/resource/ownership/progress code remains frozen unless a necessary
bug boundary is demonstrated and explicitly authorized.

Public examples use atmosphere/ocean/surface; arbitrary source identifiers remain
valid. General rules belong in general guides. Keep URLs, valid figures, method
evidence and adaptation comments. First run teaches the original scalar example;
quick start remains short. No new analytical tutorial/ocean response is implemented
in Task16. Task17's separately recorded approval is not general scientific sign-off.

The two existing PNG script/file-safety smoke cases remain inside required
unfiltered suites only. Preserve their source/overwrite/selected-time guards;
no standalone plot/image run, generated-image opening, screenshot/JPEG/pixel
inspection or visual-acceptance claim.
