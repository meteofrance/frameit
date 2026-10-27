# Changelog

## Unreleased

- Complete C4 FA cleanup after passing C1--C3/full baselines: remove the parallel
  raw decode/header/date/typed-reader path, manual geometry reconstruction and
  temporary dual comparisons. Keep isolated transport and documented same-resource
  error/type/clock/header/index/scaling evidence checks and independent oracles.
- Make EPyGrAM the sole FA reader/default and consolidate `fa` / compatibility
  `fa-epygram` extras on its unmodified upstream stack. Retain `backend: native`
  as a warned deprecated alias; record requested/effective backend and migration.
  Qualify old single/coupled YAML replay and independently checked exports, preserve
  native cubes and unsupported-family gates, and update examples, CLI/init and CI.

- Qualify the multi-time AROME-convention GRIB / EPyGrAM SURFEX engine workflow on
  independent native grids, with separate source/vertical-qualified products,
  moving centres, exact-common exclusions, strict/cycle/clock/source/scaling failures
  and geometry-before-shared-target budget checks. Verify independent values,
  masks/zeros and exact shared coordinates in fresh ordinary readers for sync/spawn exports.
- Record actual payload resource/accessor evidence in FA decoder logs and per-source
  provenance, and require the primary native/shared-polar CI cases. Update coupled
  examples with explicit vector declarations and selected scalar polar quantities;
  keep real-producer evidence gaps and C4 backend/extra migration prerequisites explicit.

- Adapt qualified EPyGrAM geometry/CRS/CI/C/E zones to the labelled source-grid
  contract, preserving canonical CF origins, native indices, explicit Earth models
  and independent encoded-corner checks. Record additive library geometry provenance.
- Remove redundant selected-field type dispatch and parent hybrid reconstruction;
  check source-level library interface A/B against original normalized A/PREFER
  once per transaction. Preserve sparse cubes, vector dependencies and GRIB/NetCDF
  contracts, with independent geometry/zone and isolated GRIB API regressions.

- Admit evidenced AROME-47 / SURFEX-8.1 dense PACK=0/X1 histories through the
  maintained EPyGrAM adapter. Use one read-only resource per transaction for
  inventory, typed structure and selected data; retain narrow type/error/clock
  observations and the transitional labelled-header adapter. Block incomplete or
  contradictory directories, unsupported layouts and missing native scaling.
- Pin the qualified ctypesForFortran bridge with EPyGrAM's unmodified upstream
  dependencies, add native SURFEX/failure/optionality CI, and record the effective
  backend and actual helper versions. GRIB/SURFEX examples select EPyGrAM with
  scaling fallback disabled; backend defaults and existing product schemas persist.

- Re-establish the C0 reference/EPyGrAM/core regression baseline and record the
  finite SURFEX/AROME-GRIB family matrix, library API evidence, cleanup ledger and
  admission plan. Add a bounded format-isolated investigation probe and compact
  independent SURFEX value/geometry and GRIB metadata/selection checks. Production
  SURFEX EPyGrAM admission, backend migration and legacy retirement remain gated.

- Integrate optional EPyGrAM 2.1.0 behind the isolated FA boundary, with an
  alternative extra, explicit backend/helper selection and FA-only private configuration.
- Assemble declared gridpoint records into native full/interface cubes, retaining
  original labels/indices/record IDs and verified PREFER-scaled hybrid coefficients.
  Preserve sparse selection, native/analysis wind branches and polar auxiliaries;
  require declared collocated physical-vector basis and explicitly requested magnitude.
- Add independent column/vector, failure, optionality and sync/spawn ordinary-reader
  tests. Spectral, physical-coordinate, map-scaled/staggered and FA atmospheric-tracker
  admission remains gated by the documented missing evidence.

- Add an optional, isolated P4 ecTrans 1.6.0 candidate probe with independent
  Fourier-mode/sign/normalization/truncation checks, bounded failure handling and
  atomic evidence reports. Preserve native spectral header facts as unresolved
  contracts and reject coefficient-shaped read responses at the parent boundary.
  Native spectral FA execution remains gated: no coefficient encoding or trusted
  real-field transformation is qualified by the library-only tests.

- Add an opt-in wind point-method comparison separating bilinear/ESMF patch
  weights from component-wise/WGS84 geodesic-transport vector treatment. Retain
  strict joint masks (including signed patch stencils), independent vector/peak/
  RMW/harmonic errors, centre/angular sweeps and production-bilinear parity.
- Add analytical broad/compact/sharp/curvilinear/high-latitude/dateline fixtures,
  optional Earth-relative BATSIRAI CI winds, portable profiles/complex coefficients,
  independent transport/phase oracles, numerical gates and method documentation.
  Candidates remain experimental; ordinary wind defaults and flux semantics are unchanged.

- Add an optional `--ci-thermodynamics` polar-cell comparison for instantaneous
  BATSIRAI temperature, relative humidity and specific TKE at 100/750 m above
  ground. Compare geometric area and equal-cell/sample weighting, conservative
  means and bilinear reconstructions against independent overlap means; retain
  quadrature sensitivity, valid coverage, source ranges and original units.
- Preserve humidity above 100% and original TKE values without clipping/floors;
  retain time-zero temperature/humidity while reporting absent TKE separately.
  Export instantaneous metadata and area-mean numerators explicitly distinguished
  from physical budgets; mark mass weighting unavailable without layer air masses.

- Extend the optional BATSIRAI polar-cell experiment to accumulated `sshf`/`slhf`
  through `polar_cell_comparison --ci-heat-fluxes`. Preserve source signs and time
  bounds, integrate J/m2 to J, and compare independent per-cell energy overlaps
  using an absolute-contribution scale that remains meaningful under cancellation.
  Retain separate reports/NetCDF products, reconstruction comparisons and failure
  reporting for both quantities; ordinary processing defaults are unchanged.

- Exercise experimental polar cells on the matrix's frozen BATSIRAI accumulated
  rain (`tirf`) records through `polar_cell_comparison --ci`. Preserve source
  accumulation bounds and GRIB sphere, declare midpoint analysis-cell semantics,
  verify per-cell rain mass against independent overlap and reopen fixed/moving,
  coarse, clipped and explicitly masked NetCDF products. Report missing time zero,
  verified fixture identity, resource observations and failed/partial attempts.

- Add an opt-in experimental conservative polar-cell scalar API with supplied
  source bounds, float64 ESMPy spherical overlaps, explicit areas and separate
  full/covered means and integrals. Keep ordinary point products/defaults.
- Add independent overlap, mask, Dask and NetCDF checks, a reproducible rainfall
  point/cell/integrated-bilinear comparison, compact-vortex baseline and method
  record. Real-model/vector qualification and scientific review remain open.

- Add optional isolated AROME/SURFEX FA input for explicitly defined instantaneous
  2-D gridpoint records, typed metadata, declared geometry, masks and bounded native
  decoding. Spectral and unsupported encodings remain actionable failures.
- Couple named GRIB/NetCDF/FA sources with one geographical track and independent
  source-grid extraction. Default to exact common times with warnings and complete
  exclusion reports; offer strict exact-time equality as a user choice.
- Export source-qualified products, per-source track indices and native helper
  provenance/diagnostics through existing atomic/final-status handling. Use Python
  3.13 and a published falfilfa4py wheel in the reference environment.

- Add an experimental built-in `multifield_vortex` tracker for AROME and Meso-NH,
  using the nine-parameter ALL_NO_THICK selection from Marchok (2021): Barnes
  mass/vorticity fixes, wind-circulation fixes, weighted combination, steering
  and explicit structural/continuity quality checks. Require a declared seed
  position/motion and record per-parameter fixes, weights and rejection flags.
- Prepare MNH native fields on 850/700/500-hPa surfaces without extrapolation;
  require an explicit model-gravity convention for geometric-to-geopotential
  height conversion. Validate inputs per file and document MNH diagnostic settings.
- Export accepted track prefixes under an explicit stop policy, retaining failed
  attempts and termination diagnostics; expose requested-time coverage separately
  from processing success in execution results and run provenance.
- Validate GRIB variable/level/time coverage, align single-cycle multi-step files
  on valid time, and expose canonical MSLP/wind aliases while retaining originals.
- Add AROME/MNH configuration examples, method/provenance documentation, analytic
  kernel and hemisphere tests, GRIB/NetCDF integration, and independent-reader checks.
  **Qualification limit:** native-grid adaptations are experimental; unrounded
  NOAA-reference comparisons, real landfall qualification and scientific review
  remain outstanding. No landfall-accuracy or stable-method claim is made.

- Require explicit wind-pair frames and grid-rotation methods; validate against
  GRIB/CF metadata, with no automatic selection or silent method/frame fallback.
- Make Cartesian native/mass-Earth winds and Cartesian/polar interface/mass W
  selectable; retain defaults `mass_earth`/`interfaces`/`mass`. Native box products
  use distinct U/V axes and bounding faces; tracking/polar analysis stays separate.
- Add stored/physical level selection with original stored indexing, validated
  mass/interface ranges and reported sparse W mapping; preserve other interface fields.
- Normalize NetCDF velocity units per file; share tracker wind preparation and
  enforce coordinate/axis checks, retaining source-frame and transformation metadata.
- Keep AROME pressure velocity `w` (Pa/s) distinct from geometric `wz` (m/s),
  without implicit hydrostatic conversion.
- Add original C-grid/W SVGs, concise configuration/output guides and a numerical
  method record with source references, tests and scientific qualification limits.

### 2026-10-16 — `207b6e8` — Conditional Meso-NH pressure-centroid support

- Extend `pressure_centroid` tracking to Meso-NH native-level NetCDF inputs on
  stationary regional structured grids, including projected grids with 2-D
  geographic coordinates.
- Resolve and validate absolute pressure, physical altitude, model-level winds,
  and required surface fields across every input file. Collocate and rotate
  native winds as needed; interpolate winds linearly and pressure logarithmically
  to 2,000 m geometric altitude above mean sea level without extrapolation.
- Add native-quadrilateral sampling and WGS84 nodal-area weighting; record input
  choices, height reference, wind frames, and transformations in track metadata
  and run provenance. Existing output names, dimensions, units, and encodings
  are retained.
- Document MNH DIAG preparation, explicit failure conditions, and the full
  500-km reference-ring coverage requirement; add an example configuration and
  synthetic numerical, failure-path, and NetCDF reopening tests.
- **Qualification limit:** full-domain real-MNH qualification and independent
  scientific review remain outstanding. MNH geometric altitude and AROME
  geopotential height are distinct definitions, not assumed equivalent.

### 2026-10-16 — `aeae9e8` — Remove example visualization notebook

- Remove `example/Ktests_cyclone/viz.ipynb`.

### 2026-10-16 — `4ec3936` — Correct near-stationary heading threshold units

- Convert the metre-valued `min_step_m` threshold to kilometres before comparing
  it with track step distances, so heading retention uses the intended threshold.

### 2026-10-14 — `014329f` — Fit the BELNA moving-track extraction box

- Allow per-case X/Y box-size overrides in the scientific test catalogue.
- Set the full-domain BELNA pressure-wind case to a 200-km by 40-km box because
  its initial centre is only nine grid points from the input domain's Y boundary.

### 2026-10-14 — `d2a6755` — Versioned YAML and explicit scientific units

- Introduce grouped YAML schema version 2 with strict key/type validation,
  configuration-relative paths, ordinary globs, inventories, and explicit exclusions.
- Add `init`, `inspect`, `config show`, `config migrate`, schema-only validation,
  and `run --dry-run`; persist YAML export options with correct CLI precedence.
- Infer native X/Y grid geometry before tracker construction, retain provenance,
  and reject unsupported anisotropy/nonuniformity instead of silently averaging it.
- Centralize lazy unit conversion; harmonize wind, radius, angle, pressure,
  geopotential, and prescribed-track coordinate boundaries. Preserve native
  vertical selections and existing physical output conventions.
- Save reloadable resolved configuration and run provenance; update templates,
  examples, documentation, and the scientific CI matrix to exercise schema v2.
- **Migration required:** ordinary loading rejects legacy flat YAML. Use
  `frameit config migrate old.yml --output frameit.yaml --launch-directory /original/workdir`.
  The internal flat Python interface remains available; the misleading tracker
  `resolution_km` keyword is deprecated with its original metre meaning preserved.

### 2026-10-14 — `f795da4` — Correct full-domain AROME vertical requests

**Issue:** Six AROME matrix cases failed preflight with `Missing requested vertical group level` and exit code 2.

- Remove the unsupported `level` wind request from the shared full-domain AROME
  fragment; BATSIRAI and BELNA GRIB inventories contain no such vertical group.
- Retain height-above-ground winds at selected indices `[0, 2, 5]` (20, 100,
  and 750 m), pressure-level winds at 1000, 850, and 400 hPa, and surface fields.

### 2026-10-14 — `bbc32df` — Matrix progress and live logs

**Issue:** Silent planning and hidden worker output made runs appear stalled.

- Show matrix startup settings, per-case planning progress, input-file inspection,
  and elapsed times.
- Stream worker logs to the terminal while retaining them in each case's log file;
  emit a heartbeat after 30 seconds without worker output.
- Add regression tests for quiet workers and complete forwarding of final log output.

### 2026-10-14 — `6da0adc` — Consistent run artifacts and AROME requests

**Issue:** Inconsistent output paths, GRIB cache collisions, and unnecessary AROME `w` requests.

- Standardize ordinary runs, matrix cases, and polar benchmarks on `products/`,
  `logs/`, and `cache/` beneath the run root.
- Keep GRIB indexes inside the run cache; distinguish source paths and cfgrib
  indexing keys to prevent collisions and permit reuse.
- Remove unused AROME vertical-velocity (`w`) requests from the full matrix and
  BATSIRAI example; add output-layout and cache-isolation regression tests.

### 2026-10-13 — `3986386` — Scientific polar qualification

**Issue:** Product-contract checks alone did not establish numerical accuracy or convergence.

- Add independent analytical scalar/vortex references and a qualification workflow
  measuring convergence, wind errors, harmonic amplitude/phase, and centre sensitivity.
- Check changing masks, clipped domains, cached/uncached and eager/Dask equivalence,
  and NetCDF reloads; export numerical reports, diagnostic plots, and example products.
- Integrate qualification into `frameit run-all-tests`; expand AROME/MNH matrix
  cases to U-only, V-only, speed-only, and scalar-only products, with quality-mask
  and wind-speed invariant checks. Document numerical-product migration.

### 2026-10-13 — `c190906` — Logging cleanup

**Issue:** Verbose logs and dependency notices obscured useful progress and warnings.

- Use compact console records and timestamped file records, with source locations
  in DEBUG; route Python warnings through scoped logging.
- Suppress selected dependency performance/default-change notices outside DEBUG
  and move verbose processing details to DEBUG.
- Clarify run-completion and stage-timing summaries; test formatting, warning
  visibility, and logging-scope restoration.

### 2026-10-13 — `ef7f842` — Reusable polar regridding plans

**Issue:** Identical geometries repeatedly rebuilt interpolation weights.

- Separate geometry-owned interpolation weights from field application; share
  plans across compatible groups and times using geometry/backend-aware keys.
- Add bounded in-memory LRU caching, configurable Dask output chunks, and plan
  build/hit/eviction, timing, and optional task/memory diagnostics.
- Add cached-versus-uncached benchmarks and tests for geometry invalidation,
  changing field masks, cache eviction, and lazy/eager equivalence.

### 2026-10-13 — `c0858ee` — Automated test and benchmark command

**Issue:** Separate test workflows and deferred computation complicated validation and timing.

- Add `frameit run-all-tests` to run packaged numerical tests and the simulation
  matrix, retaining both suites' results even when one fails.
- Report computation-stage timings separately from loading and export; eagerly
  materialize benchmark inputs/results so lazy work is timed in the correct stage.
- Package numerical tests under `frameit.testing.numerical`, add the `test`
  dependency extra, and write combined JSON, pytest log, and JUnit artifacts.

### 2026-10-13 — `c7f1eed` — Correct polar geometry, winds, and interpolation

**Issue:** Incorrect wind basis/collocation and ambiguous angular/missing-data handling distorted polar diagnostics.

- Use continuous storm centres and terminal-forward geodesic bearings for wind
  rotation; make radial/tangential winds undefined at zero radius and validate
  wind units/reference frames, including explicit grid-to-earth rotation.
- Collocate MNH winds on native mass coordinates before cropping/level selection;
  compute speed from interpolated components and support speed-only requests.
- Enforce uniform endpoint-exclusive angular sampling, configurable sample counts
  and allocation limits, exact time alignment, valid source footprints, and a
  separate native-source halo for polar interpolation.
- Add explicit strict/renormalized missing-data policies, joint vector masks,
  support/status/ring-coverage outputs, metadata handling, azimuthal mean/Fourier
  diagnostics, plotting-only closure, and numerical regression tests.

### 2026-10-12 — `9d4b888` — Adaptive pressure-centroid tracker

**Issue:** Adaptive pressure-centroid tracking and subgrid-centre preservation were missing.

- Add `pressure_centroid` tracking for regular AROME latitude/longitude grids,
  using 2-km-height pressure/winds, a 500-km environmental-pressure ring, and an
  adaptive pressure-deficit centroid coupled to storm motion.
- Provide fixed/Aitken motion solvers, configurable tolerances, explicit failure
  conditions, AROME field presets, an example configuration, and synthetic tests.
- Preserve continuous track centres for kinematics and polar origins; retain
  nearest-grid extraction indices and export centre-offset/solver diagnostics.

### 2026-10-12 — `40349f2` — Latitude-aware UTrack inputs

**Issue:** Missing latitude prevented hemisphere-aware vorticity preprocessing; field validation was skipped.

- Pass NumPy wind/vorticity arrays and latitude to UTrack preprocessing for its
  Southern Hemisphere vorticity-sign correction.
- Declare UTrack's required logical fields correctly and document the requirement
  to supply raw signed absolute vorticity.

### 2026-10-09 — `6347f65` — Native scientific simulation matrix

**Issue:** No native reproducible simulation matrix; prescribed-track time/coordinate alignment was fragile.

- Add `frameit prepare-ci-dataset` and `frameit run-matrix-test`, scientific case
  catalogs, reproducible fixture preparation/verification, and CI/full-domain modes.
- Run cases in isolated workers with input preflight, output-contract checks,
  immutable plans, per-case checkpoints, aggregate reports, and provenance.
- Share execution/configuration resolution with ordinary runs; manage dataset
  handles through export and support synchronous NetCDF writes in matrix workers.
- Validate prescribed tracks, accept `lat`/`lon` aliases and configurable coordinate
  names, and align extraction to exact common times. Update package/documentation
  version metadata to `1.1.0` and add Maxence to citation authors.

### 2026-10-09 — `4769693` — Python environment and GRIB concatenation

**Issue:** Outdated environment settings and implicit xarray defaults hindered dependency updates.

- Move the Conda environment to Python 3.14 and remove selected dependency minimum
  pins so Conda resolves compatible versions.
- Specify xarray GRIB concatenation options explicitly, preserving conflict,
  coordinate, join, and attribute behavior as upstream defaults evolve.
