EPyGrAM C3: primary coupled workflow qualification
==================================================

C3 starts from ``8b6f438`` and follows :doc:`fa_epygram_c2`. It qualifies the
**coupling engine** for AROME-convention GRIB2 atmospheric containers plus
EPyGrAM-decoded, evidenced AROME-47 / SURFEX-8.1 dense ``PACK=0/X1`` FA fixtures.
All payloads are compact independently prescribed engineering data. They are not
new real-producer measurements, a production-corpus qualification or scientific
approval. Existing gates for real SFX scaling and field-specific intervals apply.

Qualified pair and selected quantities
---------------------------------------

``test_fa_pipeline.primary_pair_document`` generates real GRIB2 messages with
Météo-France centre metadata, instantaneous MSLP/10-m winds and 700/850-hPa
u/v/temperature/relative-humidity/geopotential conventions. The existing
cfgrib/ecCodes reader selects the requested 850-hPa records; it does not substitute
geometric height for geopotential or specific humidity for relative humidity.
The synthetic wind basis is explicitly Earth-relative, checked against encoded
``uvRelativeToGrid=0``. This is not an assertion about every AROME producer stream.

The atmospheric grid is **13 by 15** regular angular points (approximately 1 km).
The surface grid is **9 by 11** spherical tangent-Lambert points at 3000 m, with
an explicitly declared fixture Earth radius of 6371229 m. FA fields are written
using the independent native fixture writer, not EPyGrAM, then read through its
maintained FA resource. Selected original names are ``SFX.T2M`` and ``SFX.SST``;
an unselected logical directory entry stays unselected. Full/native point limits
apply even to small output crops. Dense NaNs, actual undefined masks, support
labels and physical zeroes remain distinct.

Atmosphere contains valid hours 0/1/2; SURFEX contains 1/2/3 from the same reference
cycle. Inputs are deliberately unordered. Default exact-common alignment selects
hours 1 and 2, warns for both sources, and records complete skipped times/files,
missing times and counts in provenance/status. A separate >10-exclusion case
checks that warning previews never truncate the stored report. Selectable strict
alignment, different coupled cycles, mixed cycles within a source, SURFEX
state/header-clock contradictions and source-version conflicts all fail before
product publication. An actual native missing-scaling warning fails selected
payload export with no identity opt-in and leaves a failed final status.

Native grids and continuous shared targets
-------------------------------------------

The prescribed atmospheric centres move from (50 degrees E, 20 degrees S) to
(50.015 degrees E, 19.988 degrees S). Their atmospheric indices are (7,6)/(9,7);
SURFEX independently selects (5,4)/(6,4). Each time retains the continuous requested
centre and source-specific selected point/offset; the secondary fixed-box context
cannot freeze the first centre or reuse atmospheric indices.

With polar disabled, no target is built. Separate Cartesian products retain native
source grids and vertical groups: ``atmosphere.surface``,
``atmosphere.isobaricInhPa`` and ``surfex.surface``. Explicit native Cartesian winds
retain selected component names and values. The shared-polar test selects scalar
fields separately; it does not evaluate unselected wind diagnostics. Existing
single-source/legacy analysis-wind behavior is preserved.

With ``polar.shared_target: true``, **both native geometries are discovered before
common sampling and allocation checks**. The coarsest participating grid sets the
3000-m radial step; the 4-km outer endpoint yields radii 0/3/4 km and 9 azimuths.
Two common times require 54 points per source, fitting a 60-point limit even though
an unused fine-grid target would not fit. A 53-point limit, a target finer than the
surface grid, or a 98-point full-native FA limit fail before payload reads/target
construction. These tests observe call order, not only the final configuration.

Each source/vertical group exports a separate polar file with **exactly equal**
time/radius/azimuth/longitude/latitude and continuous-centre coordinates, plus the
same verified target ID. Source masks are not equated: SST is missing at the first
centre while atmospheric pressure and T2M remain valid. Continuous production
sampling remains bilinear with strict missing-data handling, without area-budget
conservation or an experimental-method switch.

Backend, independent truth and ordinary readers
------------------------------------------------

FA decoder JSONL records now include ``payload_read`` after the actual selected
accessor returns. ``sources.surfex.fa_decoder.payload_reads`` consolidates these
facts per input basename/native field: ``library: EPyGrAM``, actual
``epygram.formats.FA.FA`` resource class, ``_readH2DField(getdata=True)`` and
``openmode: r``. The existing helper-version and field/mask/scaling observations
remain. Metadata-only inspection emits no payload observation. A separate
instrumented production-worker test observes the actual library H2D payload call,
counts native opens/closes/decodes and forbids legacy full inspection/fallbacks.
Configured labels alone cannot satisfy these assertions.

Both synchronous and spawn exports reopen in a fresh xarray/NetCDF4 process using
an explicit ordinary reader; neither FrameIt, EPyGrAM nor FA/GRIB readers is
imported. Checks compare all selected native values against prescribed array
formulae, GRIB bitmap NaNs, independent SST NaNs and stored zeroes. They verify
original names, units, support/flag metadata, source-qualified groups and per-time
indices. Polar pressure at both continuous centres is checked against an
independent affine lon/lat solution, including the established float32 export
rounding; constant polar temperatures use the existing 1e-9 bound. Shared target
coordinates use exact equality, not a relaxed numerical tolerance. Inputs are
read-only and their bytes remain unchanged.

The FA helper remains a fresh Python-3.13 format-isolated process, with one native
thread and bounded requests. The GRIB implementation remains the C2-evaluated
baseline: EPyGrAM's APIs did not eliminate grouping/lazy-selection/coverage
responsibilities without another boundary/adapter. No GRIB switch or same-process
native coexistence claim is made. Existing FA/FA, NetCDF, no-FA, cube/vector,
failure/resource and source-conflict regressions remain compatibility gates.

Examples, migration and remaining evidence
--------------------------------------------

Start from ``example/config_file/coupled_fa.yaml`` for base extraction, or
``coupled_cyclone_polar.yaml`` for selected scalar polar products with a supplied
moving track. The latter now explicitly declares both wind pairs, preserves native
Cartesian winds, and selects scalar polar quantities; adapt the track path and
check declarations against actual producer metadata. Existing YAML meanings,
single-source/coupled defaults, backend choices, extras and scientific output
schema/precision/compression remain. The new decode observations are additive.

Real priority SFX fields still need release-matched scaling, units, time support,
mask/point-order and Earth-model evidence. Missing ``FMULTM/FMULTE`` is fatal by
default; absence of its diagnostic is not identity-scaling proof. No rain/flux
interval conversion, deaccumulation, pressure/height diagnosis, layer/tile average
or spectral operation is admitted by this stage. EPyGrAM tables/defaults do not
resolve those scientific gaps. No private corpus read, large run, download or
upload is needed for this compact qualification.

**C4 prerequisites:** retain passing full regressions and close each removal-ledger
row with equivalent admitted behavior/failure coverage; explicitly qualify old YAML
reload/replay, backend/default/extra migration and deprecation reporting before
retiring a legacy path. Native low-level safety/evidence exceptions require their
documented callers; real-producer gaps cannot be reclassified as scientific approval.

Actual runtime versions, exact verification commands/results and unavailable checks
are recorded below. Hosted CI execution and a clean dependency installation remain
separate from these local checks.

Both complete suites pass **681 tests plus 2 subtests**, each with one expected
optionality skip. Focused C3/backend checks pass 70 tests; native focused checks
pass 194, native CI 150, EPyGrAM/shared-polar CI 179, and spectral CI 31. Core-only
CI passes 88 with 127 confirmed dependency-only skips. The six-case packaged matrix,
four schema examples and compact primary-pair dry-run pass. Changed Python files
pass Ruff; repository Ruff reproduces the four pre-existing
``processing/polar/conservative.py`` findings (E501 89/153/323, B905 300).
Strict docs and the wheel build pass; the wheel uses workspace temporary storage
and a fresh build staging directory after the full system ``/tmp`` caused an
initial build failure. No scientific tolerances or regression assertions were
weakened to obtain these results.

.. literalinclude:: ../../../src/frameit/testing/catalogs/fa_c3.yaml
   :language: yaml
