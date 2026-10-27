EPyGrAM C4: one FA reader and configuration migration
=====================================================

C4 starts at ``7fe6c34`` after the C1--C3 implementation/qualification commits.
Before retirement, both complete untouched suites were rerun: **681 passed,
1 expected optionality skip and 2 subtests passed** in each reference/EPyGrAM
environment. Core-only CI passed **88 tests, 127 dependency-only skips and
2 subtests**. The full post-cleanup suite and native/core checks are recorded below.
These gates qualify the finite engineering contracts, not real-producer scientific
approval. The existing unrelated untracked configuration was preserved.

The sole maintained FA implementation is now **EPyGrAM 2.1.0**. FrameIt retains
its isolated transaction boundary, scientific selection/contracts, labelled
dataset/output adapters and essential failure/evidence/resource checks. There is
no parallel decoder, alternate-reader retry or production comparison execution.
The atmospheric GRIB route remains cfgrib/ecCodes, following the concrete API/
lazy-grouping and Pa/hPa evaluation in :doc:`fa_epygram_c2`. Any GRIB replacement
still requires a separately bounded, independently checked parity step and a
qualified format-specific isolation boundary.

Installation and old YAML migration
------------------------------------

* Install ``frameit[fa]`` (development: ``python -m pip install -e '.[test,grib,fa]'``)
  in a coherent **Python-3.13** environment. The extra supplies EPyGrAM 2.1.0 and
  ctypesForFortran 1.3.0 with unmodified upstream dependencies: falfilfa4py 1.2.1,
  ecTrans 1.6.0, Python eccodes 2.44.0 and netCDF4 1.7.2. ``fa-epygram`` is retained
  as an installation alias with identical requirements; both can be requested
  together. It is no longer an incompatible second stack. Native CI requires this
  stack. ``environment.yaml`` keeps the reference GRIB/ESMF parent and documents a
  helper overlay setup, preserving the qualified native dependency boundary.
* A former standalone falfilfa4py-1.3.0 environment does not contain the maintained
  reader. Install the coherent extra in a dedicated helper and select it using
  ``input.fa.python_executable`` when the parent environment must stay separate.
  No installed tables, dependency metadata or research environment is patched.
  Helper paths remain YAML-relative; virtual-environment Python symlinks are not
  resolved to the base interpreter.
* ``input.fa.backend`` defaults to ``epygram`` for single and coupled sources,
  full init templates, inspection and direct requests. Explicit ``backend: native``
  and ``--fa-backend native`` remain accepted as **deprecated aliases** of that
  same implementation. Schema validation and requests warn; there is no fallback
  ladder or raw-decoder selection. Replace the value with ``epygram`` or omit it.
  There is no announced alias-removal release.
* Resolved YAML preserves an explicit alias so its replay is observable. Inventories
  and run inputs record effective ``backend: epygram`` plus ``requested_backend``.
  Actual helper ``backend_versions`` records ``FA_backend``, ``FA_backend_requested``
  and ``FA_backend_migration`` (message for the alias, otherwise null). Decode
  observations still identify the actual EPyGrAM resource/accessor/read-only mode.
* Existing ``profile``, ``expected_source``, ``subdomain``, ``earth_radius_m``,
  ``field_metadata``, ``native_cubes``, helper, timeout and point-budget settings
  keep their meanings and are replay-tested. No key is ignored. The alias does not
  bypass the C1 evidenced release/directory/clock/type checks or C2 geometry/field
  checks: unmatched SURFEX releases, selected native errors, intervals, unknown
  scaling and unqualified operations remain failures. Raw inventory can still
  report unsupported structures without decoding them.

Completed cleanup ledger
--------------------------

Paths below are relative to ``src/frameit/``. Every removed implementation has
replacement behavior/failure coverage; retained exceptions have production callers
and a concrete upstream or public-contract reason.

.. list-table:: Retired production responsibilities
   :header-rows: 1
   :widths: 28 36 36

   * - Removed path / former callers
     - Replacement
     - Replacement regression anchors
   * - ``fa_worker.handle`` raw FAITOU/KEEP dispatch; ``_inspect`` header/index/date parser;
       ``_native_clocks`` (all FA inventory/load/read callers)
     - One delayed, owned, read-only EPyGrAM resource; library validity, identity and
       ``listfields``; narrow same-unit index/clock evidence only
     - ``test_fa_io``, ``test_fa_baseline``, ``test_fa_epygram_surfex``: one open/close,
       no physical metadata reads, clock/open failures, freshness, native errors
   * - Direct production FACILO decode, reshape and native-sentinel normalization
       branch in ``handle`` (lazy ``FaArray``)
     - Version-matched library H2D accessor/getdata, shape/dtype checks and mask-to-NaN;
       crop/key/transfer remain bounded FrameIt operations
     - ``test_fa_surface``, ``test_fa_io``, ``test_fa_epygram_surfex``: independent
       values/NaNs/zeroes, scalar/reversed/strided/empty selections, scaling failures
   * - ``_words``, ``_integer``, ``_typed_metadata`` raw structural decoder and
       source-optional branches in ``_describe``
     - Library Misc typed reads plus the single checked directory/semantic adapter;
       only evidenced L0/T0 low-level exceptions remain
     - ``test_fa_contracts`` now tests actual library reads against independent IEEE
       words/ASCII/int64 truth and unknown/type failures; C1 malformed structure tests
   * - Manual projection/axis/corner reconstruction and raw-header signature fallback
       in ``fa_geometry`` (preflight/loader)
     - Qualified library axes/CRS/zones through ``geometry_contract`` and the labelled
       parent adapter; missing library facts fail closed
     - ``test_fa_epygram_geometry`` independent Snyder/axes/CI/C/E/corner checks,
       both hemispheres and shifted-grid rejection; ``test_fa_mapping`` lookup guards
   * - Header-only ``hybrid_contract`` fallback; dual legacy/library geometry comparison
     - Required library vertical grid, checked against original normalized A/B/PREFER;
       independent equations and explicitly specified CF origins replace dual execution
     - ``test_fa_cubes`` preserves independent coefficients, invalid columns, sparse
       full/interface IDs and vectors; C2 numerical bounds unchanged
   * - Native/EPyGrAM decoder dispatch and incompatible FA-extra choices
     - One effective reader/default; warned legacy configuration alias; identical extras
     - ``test_fa_migration``, native-alias SURFEX failures/categories and sync/spawn cube
       exports; required CI dependency guards and combined-extra resolution

.. list-table:: Retained adapters and narrow exceptions
   :header-rows: 1
   :widths: 28 42 30

   * - Code / actual caller
     - Reason and retained boundary
     - Regression evidence
   * - ``fa_epygram._inventory`` / ``inspect_resource``
     - Library inventory omits cadre/DATX, lengths and duplicate/count/budget guards;
       bounded observations on its unit, never another open or physical classification
     - C1 inventory/directory/large-int tests; read-only native probe
   * - ``_clocks`` / ``inspect_resource``; L0/T0 in ``structure_value`` / ``_describe``
     - Reject permissive clock/logical normalization; library T0 loses seconds.
       Only allowlisted small structural words; no physical raw-word reader
     - Mixed IEEE-seconds, malformed/nonfinite/conflicting clocks, invalid logical words
   * - ``_active_header``, ``admitted_geometry`` / library geometry adapter;
       ``hybrid_contract`` / selected hybrid-field metadata
     - Original admission flags/CI corners/normalized A/PREFER are omitted or normalized
       in library objects. Keep independent evidence and original indices, not geometry reconstruction
     - Corner/radius contradictions, native storage/budget, header flags, coefficient identity
   * - Selected FANION guard in ``_describe`` / ``inspect_resource``
     - EPyGrAM hides -91/-93/-94 as possible Misc. Fail selected physical errors and
       gate spectral data before H2D/transform construction; no unselected inquiry
     - Three initial errors, later H2D failure, spectral/non-FA physical words
   * - ``_readMiscField``, ``_readH2DField``, ``_proj.crs`` / EPyGrAM adapter
     - Pinned 2.1.0 private APIs avoid broad fallback and supply the unavailable public CRS;
       version guards, actual types/shapes and original corners remain required
     - C1/C2 library instrumentation and independent geometry/field checks
   * - ``fa_contracts``, FBUF ASCII/width adapter, ``fa_cubes`` / worker/preflight/loader
     - Explicit scientific definitions, source/release/support distinctions and exact
       declared axes; library tables/defaults do not establish producer semantics
     - Contract, source, type/layout, unit/frame, sparse/vector/idempotence regressions
   * - ``fa_backend``, worker crop/key/freshness and ``FaArray`` / CLI/loader/export
     - Format-isolated fresh helper, lock/threads, timeout/crash/protocol/NPY cleanup,
       scaling-diagnostic guard, selected-only laziness and full-native allocation limits
     - FA I/O/contracts/surface/pipeline and HPC lifecycle tests; no structured scaling query exists
   * - ``grib_utils``, GRIB preflight, coupled orchestration and ordinary writers / runner
     - Existing lazy GRIB grouping and semantic coverage; independent grids, exact times,
       optional selected processing, atomic publication/status. C2 found no simpler qualified replacement
     - C3 primary pair, existing GRIB/NetCDF and packaged matrix, disabled/shared targets
   * - Native fixture writer and FA/ecTrans/API probes / test and explicit investigation entry points
     - Independent numerical/byte/error oracles and bounded private-data-safe upstream evidence;
       no production reader caller and no implicit scientific operation
     - Probe, analytical Fourier-mode and fresh ordinary-reader tests remain

Compatibility, method scope and evidence gaps
----------------------------------------------

Admitted families remain evidenced AROME-47 / SURFEX-8.1 **dense PACK=0/X1**
instantaneous records, qualified regional regular angular or spherical tangent-
Lambert CI/C geometry, individually declared dense layer/patch names, and explicitly
associated atmospheric gridpoint full/interface cubes. C3's multi-time GRIB plus
EPyGrAM SURFEX pair on different native grids still passes with disabled polar or
an explicitly shared bilinear target. Existing FA/FA and NetCDF pairs remain.

Old single/coupled YAML with omitted or explicit legacy backend is loaded from
disk, resolved, reloaded and executed. Fresh ordinary xarray/NetCDF4 readers compare
two-time values, NaNs, valid zeroes, units, original names and per-time source indices
to prescribed independent arrays. Native cube alias tests cover synchronous and
spawn exports, original full/interface IDs, A/B/PREFER, sparse levels and masks.
No existing independent tolerance is widened; same-library round trips are not
the numerical oracle. Tests of retired private parsers now exercise the surviving
contract/failure behavior or actual library reads.

Scientific data names/dimensions, native/source/vertical-qualified groups, units,
missing policy, output precision/compression/chunking and ordinary-reader contract
are preserved. Provenance changes are explicit: default/alias runs now carry the
C2 library geometry signature/origins and selected field metadata; undefined-value
origin is the library-returned mask, not a raw FACILO sentinel. Raw IEEE NaNs need
not have a library mask bit. Full-native nonfinite count, physical support labels,
extension zones and valid zeroes remain separate facts.

There is no new diagnostic, vector basis conversion, pressure/height diagnosis,
deaccumulation, extrapolation, support filling or tile averaging. Exact-common
times remain the coupled default with complete exclusions and warnings; strict
remains selectable. Native geometry precedes shared-target resolution/budgets.
Continuous production polar sampling remains bilinear without conservation claims.

**C5 prerequisites:** select a demonstrated capability row and obtain independent
release-matched types/maps/order/values/missing references for packed or typed
SURFEX; original axes/bounds/fractions for layers/patches/tiles; field-specific
intervals/resets/signs for temporal operations; analytical plus trusted real-field
references for selected spectral/vector/physical-coordinate operations. Real
priority SFX quantities still need units/scaling/time/support/Earth-model evidence
and required scientific review. Supplied -91 records and missing FMULTM/FMULTE are
unresolved, not reclassified as metadata or validated by library defaults. No new
private corpus read, large run, download or upload was needed for C4.

Verification and actual dependencies
--------------------------------------

The packaged record contains exact command arguments, actual versions, results,
initial assertion corrections and unavailable checks. Local launchers/environments
are described by portable names; artifacts are in ignored fresh ``build/c4-*``
paths. The reference environment was preserved; the post-retirement native suite
uses the sole coherent EPyGrAM stack. The core clone genuinely lacks optional
backends; it is an offline optionality check, not a clean-install qualification.
Hosted CI, Python 3.10 and new real-producer scientific evidence remain separate.

Final complete regression: **694 passed, 3 absence-only skips, 2 subtests passed**.
Native CI/focused: **207 passed, 3 absence-only skips**; spectral CI: **31 passed**.
Core-only CI: **100 passed, 134 dependency-only skips, 2 subtests passed**. All three
absence cases also pass in the preserved raw-only reference environment, proving
that neither an omitted backend nor the legacy alias silently retries that decoder.
Changed Python files pass Ruff. Repository Ruff retains four unchanged findings
in ``processing/polar/conservative.py`` (E501 89/153/323, B905 300), reproduced by
linting ``git show HEAD:...``. Four schema examples and the compact primary-pair
dry-run pass; dry-run publishes no output directory. Strict documentation and
wheel/combined-extra resolution checks pass.

The built wheel's six-case GRIB/NetCDF/polar matrix **passes and exits zero in the
reference parent**. Four packaged primary-pair native/shared-target sync/spawn tests
also pass there with the maintained FA helper. A separate invocation in the
EPyGrAM overlay completes all six cases but **aborts at process shutdown** with
``free(): invalid pointer``. The same matrix on an untouched ``7fe6c34`` worktree,
using the same verified fixture and overlay, reproduces shutdown
``double free or corruption (!prev)``. That command is a failure, not a matrix pass.
The native cause is not localized; this is pre-existing runtime/distribution debt,
not evidence of safe same-process native coexistence. No exit suppression,
import-order workaround or dependency patch was added. Keep the reference
GRIB/ESMF parent plus FA-only helper; broader shared-environment distribution
qualification requires resolving the teardown defect and clean-install/hosted
checks in C5. The first detached-worktree attempt lacked ignored fixture payloads
and failed inventory; the reproduction explicitly supplies the verified wheel fixture.

.. literalinclude:: ../../../src/frameit/testing/catalogs/fa_c4.yaml
   :language: yaml
