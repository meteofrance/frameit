EPyGrAM C1: evidenced dense SURFEX histories
=======================================================

C1 extends the existing isolated EPyGrAM adapter to ``profile: surfex_history``.
Starting revision: ``3998b05``; qualification runtime: **Python 3.13.16**.
The historical :doc:`fa_epygram_c0` supplies the API investigation and cleanup
ledger. This increment qualifies compact engineering fixtures, not arbitrary
producer fields or the full multi-time AROME-GRIB/SURFEX production workflow.
No independent human scientific approval is claimed.

Admitted family and explicit scientific contract
-------------------------------------------------------

Execution requires all of:

* the observed ``PROGRAM=AROME, VERSION=8, BUG=1, MASDEV=47, BUGFIX=0`` structure;
* ``SFX.PACK=0`` and a complete, consistent FBUF directory with unique original
  IDs, matching record existence and checked column lengths;
* selected dense horizontal real ``X1`` entries, ``DIM1=storage X*Y``, ``DIM2=-1``;
* ``IMAX/JMAX`` matching native **CI**, and ``DIM_FULL=IMAX*JMAX`` for this family;
  CI need not equal the full CIE storage grid;
* a finite mixed-word DTCUR state clock matching the FA header validity;
* successful native encoding inquiry, non-spectral H2D library metadata, matching
  native shape and actual float64 decoded dtype;
* the existing admitted geometry and explicit field units/kind/instantaneous
  declaration, followed by the native scaling guard when data are requested.

``PACK=0`` is a SURFEX layout fact, **not FA codec packing 0**. A compact native
packing-120 fixture exercises the actual missing-FMULTM/FMULTE warning. With
``allow_unscaled: false`` it fails; an explicit opt-in records identity fallback,
not verified scaling. Neither qualified native wrapper exposes a structured
multiplier query. No warning means ``not_exposed``, never proven identity.
The supplied real T2M's scaling remains unresolved from C0; this increment does
not accept real physical values or certify its products.

FULL/SEA/NATURE support labels remain separate from physical NaNs/native undefined
samples and valid zeros. Dense layout does not establish a sparse support map.
No absent support is filled with zero. Individual soil/patch/tile names can remain
explicitly declared 2-D records; there is no new layer axis, depth, fraction,
averaging, deaccumulation, pressure/height diagnosis or automatic diagnostic.
Library tables, horizontal/vertical defaults and its default Earth model are
inspectable library information, not producer-specific scientific proof.

One resource, maintained decoding and narrow exceptions
-------------------------------------------------------

``fa_worker.handle`` owns one EPyGrAM FA resource, created delayed and opened
explicitly read-only. Its finally block closes that resource on success and on
inspection/decode failures, including an open-time geometry/validity error.
There is no preceding raw FA open/``_inspect`` call on this path and no retry on
another backend. The native branch remains a regression baseline until C4.

The existing ``_describe`` helper is shared contract assembly, not another
decoder. EPyGrAM supplies inventory, resource validity/identity, typed structural
decoding, field metadata, H2D decoding/reshaping and native masks. Small retained
observations use the **same resource's unit**, inside the native boundary:

.. list-table:: C1 responsibility transfer and remaining exceptions
   :header-rows: 1
   :widths: 25 45 30

   * - Responsibility
     - Maintained API / reason for retained observation
     - Regression / later gate
   * - Inventory and lengths
     - ``listfields()`` owns field discovery. It omits seven cadre records and
       DATX and exposes no lengths/duplicate guard. Bounded LFI index observations
       restore those facts and check the library count; no unselected type inquiry.
     - One open/close, duplicate/missing directory IDs, no physical metadata reads.
   * - Typed structure
     - Version-matched ``_readMiscField`` decodes allowed C0/N0/X0/N1 structure.
       FBUF character columns arrive as exact int64 words and use checked ASCII
       widths. Actual dtype/shape/length is checked before accepting a value.
     - Independent IEEE real, large integer, ASCII and directory references.
   * - L0 and T0 only
     - Narrow LFI observations retain 0/1 logical validity and mixed DTCUR
       integer date / IEEE seconds. Generic library reads lose those facts.
       Physical records can never use this structural-word accessor.
     - Invalid logical words, NaN/short/conflicting clocks, release/type guards.
   * - Physical failures
     - Direct selected FANION preserves -91/-93/-94 errors before the library's
       broad metadata fallback. ``readfield(getdata=False)`` supplies metadata;
       version-matched ``_readH2DField`` supplies data and fails closed if a later
       encoding inquiry fails, without dispatching to Misc/FALAIS.
     - All three initial errors and a later physical inquiry failure; selected
       raw-integer payload cannot masquerade as dense X1.
   * - Original header contract
     - ``_raw_header_get`` retains original flags, CI corners, normalized A and
       PREFER for the existing labelled-grid/signature guards. This is a temporary
       adapter over the library, not another resource or projection implementation.
     - P5 coefficient/cube and current grid regressions; C2 transfers geometry.
   * - Clock consistency
     - Library validity supplies dates/lead/interval marker. A narrow FADIEX
       comparison rejects permissive inconsistent raw-clock normalization.
     - State/header conflicts; no timestamp substitution or time filling.
   * - Transport, scientific meaning, coupling/export
     - Existing worker/backend, descriptors, lazy arrays and source contexts.
       FrameIt owns declarations, budgets, selection, atomic products and provenance.
     - Full regression, optionality and native CI; C3 primary-pair qualification.

Thus a transaction has **one native open and one close**, but currently **two
FACIES and two FADIEX inquiries**: the library's initial reads and the documented
original-header/clock observations. C1 removes the duplicate full raw-reader
prepass; it does not claim the C2 geometry transfer or an optimized scan count.
The production test forbids the legacy prepass and any physical raw-word decode.

Resource/optionality policy is unchanged: fresh helper interpreter per request,
one native thread, a serialized request per consuming process, timeout/crash
reporting, no parent GRIB definition overrides and no Python GRIB/ecTrans imports
in a gridpoint FA child. Installing ecTrans as an upstream dependency does not
activate a transform. Inventory is bounded at 100000 records, FBUF columns at
100000 words and selected typed metadata at 4096 words. The full native point
budget is checked before any physical decode; cropping/key selection precedes
NPY transfer. This is not subrecord I/O or a throughput qualification.

Configuration, coherent dependencies and migration
-------------------------------------------------------

.. code-block:: yaml

   input:
     format: fa
     fa:
       backend: epygram
       # python_executable: /path/to/qualified-helper/bin/python
       profile: surfex_history
       expected_source: {PROGRAM: AROME, VERSION: 8, BUG: 1, MASDEV: 47, BUGFIX: 0}
       # Confirm actual producer geometry; this is not a universal FA radius.
       earth_radius_m: 6371229.0
       field_metadata:
         SFX.T2M:
           units: K  # explicit source declaration requiring producer evidence
           kind: continuous
           temporal_kind: instantaneous
           allow_unscaled: false
   variables:
     surface: {names: [SFX.T2M]}

The Python-3.13 helper must contain FrameIt and ``FrameIt[fa-epygram]``. EPyGrAM
2.1.0's upstream requirements are unmodified: falfilfa4py 1.2.1, ecTrans 1.6.0,
eccodes 2.44.0 and netCDF4 1.7.2. The extra now also declares the previously
runtime-required **ctypesForFortran 1.3.0** bridge. No dependency override,
``--no-deps`` dependency installation or installed-package/table edit is needed.
The existing evaluated overlay passes ``pip check`` and an offline resolver
dry-run of the actual editable extra; dependencies are already satisfied.
That is coherent-runtime/resolution evidence, not a clean-install or hosted-CI run.

Do not combine the legacy ``fa`` extra's falfilfa4py 1.3.0 with EPyGrAM's exact
upstream pin. Use a coherent helper via ``python_executable`` if the parent uses
another stack; YAML-relative interpreter paths and venv symlinks are preserved.
The default backend is still ``native``. Existing scalar/coupled YAML and P5
atmospheric cubes retain their meanings. Moving a SURFEX source to EPyGrAM is an
explicit backend selection, with the additional evidenced-release, DTCUR and
CI/directory checks described above. Unmatched/unsupported structures remain
inspectable; they are not admitted by a generic library table.

``coupled_fa.yaml`` and ``coupled_cyclone_polar.yaml`` now select EPyGrAM for
SURFEX. The former's historical identity-fallback opt-in is changed to **false**;
an old engineering permission must not become a new scientific default. Review
source units/scaling/geometry and adapt paths before running these examples.
The FA/FA compatibility example retains its explicit legacy workflow.

Outputs retain ordinary NetCDF names, dimensions, units and encoding. Additive
provenance includes ``backend_versions.FA_backend`` (effective implementation),
actual helper Python/EPyGrAM/falfilfa4py/bridge/native ecCodes versions and required
ecTrans/netCDF4 distribution versions. Typed observations identify their accessor.
``mask.nonfinite_count`` counts full-native nonfinite values after native-mask
normalization, before cropping; it does not identify a surface-support map.
Undefined observations identify the EPyGrAM returned mask or the legacy native
flag as their origin. EPyGrAM does not expose the original flag/sentinel; a
returned IEEE NaN may have no mask bit (including the packing-120 fixture).
The nonfinite count must not be interpreted as that flag or a support map. Decode logs
record actual scaling failures/permissions; representative NetCDF descriptors
retain their existing input-snapshot scope.

Qualification, remaining evidence and next prerequisites
---------------------------------------------------------

Independent numerical truth is the asymmetric 7-by-9 field ``280+10*j+i`` with a
NaN at [1,1] and real zero at [2,2], plus categorical codes and selected 2-D layer
names. Arrays, reversed/strided/point selections and original directory order
agree exactly. Regular lon/lat and spherical southern-Lambert fixtures exercise
the production path; C0's independent angular/spherical geography references
remain in the regression suite. Native/categorical exports reopen through fresh
ordinary xarray/NetCDF readers without importing FrameIt or EPyGrAM. These are
engineering/numerical contracts, not validation of all real fields.

Required CI now includes C1 SURFEX success/failure/lifecycle tests, both native
surface backend variants and P5 regressions. Core CI checks absent FA/GRIB/polar
packages explicitly and runs schema/optional-dependency and no-FA NetCDF coupling
cases. Existing native and spectral-candidate jobs remain active. The exact local
commands, actual versions, results and finite operation matrix are recorded below.

Local final regression: **657 passed, 2 subtests passed** in each full reference
and EPyGrAM-stack suite. The reference skips only its absent optional spectral
candidate; the EPyGrAM suite skips only the test that explicitly requires that
dependency to be absent. Native CI is **136 passed / 1 absent-candidate skip**,
EPyGrAM CI **105 passed / 1 absence-only skip**, the separate spectral-native CI
**22 passed**, and core-only CI **84 passed / 100 confirmed dependency-only
skips / 2 subtests passed**. No installed required backend is skipped. The focused
SURFEX check reports **69 passed**. Times/warning counts are evidence records,
not a throughput benchmark.

The six-case packaged core-profile matrix, four schema-only examples, wheel and
strict docs build pass. A compact **GRIB + EPyGrAM SURFEX dry-run** also resolves
one exact common time, independent 5-by-7 / 7-by-9 native grids, explicit backend
provenance and separate planned products without physical decoding or an output
directory. It is planning evidence, not C3's multi-time product qualification.

Repository-wide ``ruff check src/frameit`` remains blocked by the same four C0
findings in unchanged ``processing/polar/conservative.py``: E501 at 89/153/323
and B905 at 300. All four were independently reproduced from ``git show HEAD``
through Ruff stdin. Changed Python files pass Ruff 0.17.1. Hosted CI, local Python
3.10, clean EPyGrAM installation and new private-corpus evidence were not executed.

Remaining gates:

* **C2:** transfer canonical labelled geometry/CI/C/E zones and original grid
  identity to qualified library APIs, with independent corners/offsets, both
  hemispheres and P5 sparse/full/interface coefficient parity. Preserve explicit
  Earth model and existing source axes/CF origin. Evaluate GRIB metadata APIs in
  their own isolated, independently checked parity step; C0 found no drop-in lazy
  xarray replacement, so the working cfgrib/ecCodes route remains the baseline.
* **C3:** actual GRIB containers plus EPyGrAM-decoded SURFEX at multiple times and
  distinct grids, source-qualified sync/spawn products, moving centres, exact
  common/default warnings and complete exclusions, selectable strict times,
  disabled/shared bilinear polar targets and fresh ordinary readers.
* **Real producers:** release-matched units/scaling/time/support, trusted
  values/masks, independent Earth-model/geographic checkpoints and multiple times.
  No new private corpus was decoded in C1; the single-time C0 observations do not
  fill these gaps. AROME atmospheric -91 and spectral records remain blocked.
* **C4/C5:** full regression parity before backend/default/extra consolidation or
  legacy retirement; independent type/map/order/value references before packed,
  X2/N1/L1/C1 physical arrays, full layer/tile axes, intervals or transforms.

.. literalinclude:: ../../../src/frameit/testing/catalogs/fa_c1.yaml
   :language: yaml
