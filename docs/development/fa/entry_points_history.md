# Original FA entry-point passages

Developer evidence frozen from `9b11d602c4fb05fb2adf74b699439de6a0b8625b` on
2026-10-28. These are literal excerpts, not current support or installation advice.
Old links/roles inside the fences intentionally retain their original spelling.
See the [index](README.md) and [destination/removal map](CONTENT_MAP.md) for current
topic links and ownership. No public source is rewritten in this freeze.

## README.md, lines 32–70

```markdown
## Installation

Conda/mamba is recommended for the native scientific stack, particularly
ESMF/ESMPy for optional polar processing. Core NetCDF processing also declares
pip-installable runtime dependencies. The `grib` extra adds cfgrib/ecCodes;
the `polar` extra adds xESMF but still requires a compatible ESMF installation.
The reference `environment.yaml` installs FrameIt and the FA/GRIB/NetCDF/polar stack
in one Python-3.13 Conda environment. Conda owns the shared NetCDF/HDF5/ecCodes
libraries; pip supplies unmodified EPyGrAM and its required FA bindings.
The optional `fa` extra enables the isolated FA reader;
`fa-epygram` remains an installation alias for the identical dependencies.
FA supports explicitly defined instantaneous 2-D gridpoint records on qualified
regional headers; spectral transformations are not implicit.
SURFEX execution requires a complete AROME source/directory with `PACK=0` and
dense horizontal `X1` records. Native vertical-header facts remain inspectable
provenance, without inferred layer axes or atmospheric 3-D processing.
The maintained EPyGrAM path handles
[evidenced dense SURFEX histories](docs/source/user_guide/fa_epygram_c1.rst) and
[explicit native atmospheric cubes](docs/source/user_guide/fa_atmosphere.rst),
retaining full/interface indices and checked hybrid coefficients.
`input.fa.backend: epygram` is now the default. Legacy `backend: native` is a
deprecated alias, with warnings and requested/effective backend provenance;
it selects the same reader. Install the unmodified upstream stack and qualified
ctypesForFortran 1.3.0 bridge in a coherent environment. See the
[C4 cleanup ledger and migration guide](docs/source/user_guide/fa_epygram_c4.rst).
The [unified-environment qualification](docs/source/user_guide/fa_environment.rst)
records clean installation, native lifetime checks and the remaining limits of
older mixed stacks. FA stays in isolated subprocesses using the same Python;
`input.fa.python_executable` is only needed to select a different environment. Native
extraction does not require pressure or height diagnosis.
The [C2 geometry/metadata adapter](docs/source/user_guide/fa_epygram_c2.rst) uses
qualified EPyGrAM axes/CRS/zones while preserving native indices, explicit Earth
model declarations, existing CF origins and selected-only field decoding.
The [P0 baseline and family matrix](docs/source/user_guide/fa_baseline.rst)
separate current evidence from blocked capabilities; full FA compatibility is
not claimed.
The optional [P4 ecTrans candidate evaluation](docs/source/user_guide/fa_spectral.rst)
checks independent regional Fourier modes in an isolated helper; native spectral
FA execution remains gated pending verified coefficient and real-field references.
```

## README.md, lines 184–206

```markdown
For atmospheric GRIB/NetCDF coupled to SURFEX FA, start from
[`example/config_file/coupled_fa.yaml`](example/config_file/coupled_fa.yaml).
The primary integration target is **EPyGrAM-backed SURFEX FA + AROME GRIB**.
The [C1 admission and migration notes](docs/source/user_guide/fa_epygram_c1.rst)
qualify the EPyGrAM reader on compact AROME-47 / SURFEX-8.1 dense fixtures, with
directory, type, clock and scaling guards. Supplied real-field scaling, units,
support and Earth-model evidence remain unresolved. The
[C3 primary-pair qualification](docs/source/user_guide/fa_epygram_c3.rst) exercises
actual GRIB containers plus EPyGrAM-decoded dense SURFEX fixtures at multiple times
on distinct native grids, including moving shared targets and sync/spawn exports.
This is engine evidence, not real-producer scientific qualification.
Other producer or native-container integrations are
outside this increment. A native FA/FA compatibility example is
[`example/config_file/coupled_arome_fa_polar.yaml`](example/config_file/coupled_arome_fa_polar.yaml).
`input.time_alignment: common` selects exact common times by default, warns for
each source losing times and records all exclusions in provenance/final status.
Choose `strict` to fail on unequal source times. Each source retains its own
grid; FA geometry and field meaning/scaling need explicit declarations.
For separate atmospheric/surface products with identical polar target coordinates,
select `polar.shared_target: true`. See the
[cyclone coupled-polar example](example/config_file/coupled_cyclone_polar.yaml) and
[P3 field/evidence notes](docs/source/user_guide/fa_surface.rst). Source masks and
physical definitions remain independent. Marine-model adapters are future work.
```

## CHANGELOG.md, lines 5–64 (Unreleased FA entries)

```markdown
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
```

## docs/source/user_guide/configuration_file.rst, lines 4–22

```rst
For named atmospheric/surface sources, native FA settings and the selectable
``common`` (default) / ``strict`` exact-time policies, see :doc:`fa_inputs` and
``example/config_file/coupled_fa.yaml``. Single-source schema-v2 documents retain
their existing structure. Coupled runs require ``tracking.source`` and keep
variables within each source rather than a shared top-level block.
Set top-level ``polar.shared_target: true`` for the verified common-target
contract in :doc:`fa_surface`; its default is false for compatibility. Enabled,
selected sources inherit the target from ``tracking.source`` and must agree on
its geometry. Sampling methods and physical masks remain source-specific.

``input.fa.backend`` now defaults to ``epygram``. Legacy ``native`` remains an
accepted, deprecated alias for that same reader and emits migration warnings.
``resolved-config.yaml`` preserves an explicit alias for replay; inventories and
decoder provenance record both requested and effective backend. All profile,
Earth-model, field/cube, helper, timeout and point-budget settings still apply.
Both ``fa`` and compatibility ``fa-epygram`` installation extras now select the
same stack. See :doc:`fa_epygram_c4` before replaying a former raw-reader setup.
The unified :doc:`fa_environment` uses the current Python for isolated FA workers;
omit ``input.fa.python_executable`` unless intentionally selecting another runtime.
```

## docs/source/user_guide/output_files.rst, lines 43–86

```rst
Coupled sources keep this layout with source-qualified groups, for example
``SIMU.cart.surfex.surface.nc``. The shared track records per-source indices;
Cartesian grids are not implicitly regridded. Exact-time exclusions and native
FA diagnostics are reported in provenance/final status. See :doc:`fa_inputs`.
FA variables additionally carry a JSON ``fa_field_descriptor`` input snapshot
and its explicit scope. Per-file descriptors and post-decode scaling/mask facts
are retained in run provenance and decoder logs; see :doc:`fa_contracts`.
Spectral FA coefficients have no admitted output contract and cannot be returned
as gridpoint values. The separate P4 candidate evaluation writes an atomic JSON
report, not a physical-field NetCDF product; see :doc:`fa_spectral`.
Opt-in P5 native cubes add separate ``level``/``level_w`` axes, original record
coordinates and pressure-valued/normalized interface coefficients, without
diagnosing physical coordinates; see :doc:`fa_atmosphere`.
The :doc:`fa_epygram_c1` adds effective-backend/helper-version provenance and
post-normalization full-native nonfinite counts in decode observations. Support
labels remain distinct from actual masks; native/source-qualified product schemas
and ordinary-reader requirements are preserved.
The :doc:`fa_epygram_c3` adds ``sources.<id>.fa_decoder.payload_reads`` keyed by
source basename and selected native field. Each successful payload call reports
its actual library/accessor and, for EPyGrAM, resource class and read-only mode.
These post-call observations supplement configured backend labels and actual helper
versions. Decoder JSONL logs retain individual requests; the manifest consolidates
observations per file/field. Scaling admission is still checked separately and may
fail after the library call. This is execution evidence, not producer-scaling proof.
C4 makes these library observations universal for FA, including the deprecated
``native`` alias. Per-input ``backend`` and ``backend_versions.FA_backend`` record
the effective ``epygram`` reader; ``requested_backend`` / ``FA_backend_requested``
retain the request and ``FA_backend_migration`` explains an alias. The default
now also records library geometry/CRS/zone origins and returned-mask provenance.
Scientific variable/dimension names, source/vertical groups, values, units, masks,
precision and storage encoding retain their established contracts; see
:doc:`fa_epygram_c4` for compatibility evidence and remaining limits.
C5 preserves that schema and adds contextual rejection of malformed or over-budget
helper transfers before array materialization. A failed transfer cannot publish
that surface product or mark the run completed; already completed other products
can remain under the per-product atomicity contract. See :doc:`fa_epygram_c5`.
Projected FA tracking adds selected-grid latitude/longitude and source-CRS
snapping offsets to the track, source-prefixed in coupled products. Continuous
``lat``/``lon`` remain requested centres; see :doc:`fa_geometry` for conventions.
With ``polar.shared_target: true``, separate source-qualified polar products share
a verified target ID and exactly matching time/radius/azimuth/lat/lon coordinates.
Source masks and variable meanings remain independent. Vertical-group separation
is retained (several atmospheric groups can still produce several atmosphere
files). See :doc:`fa_surface`; no CROCO/WW3 compatibility is implied.
```
