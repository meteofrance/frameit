EPyGrAM cleanup C0: baseline, API evidence and admission plan
======================================================================

Evidence date: **2026-10-27**. Inspected and tested starting HEAD:
``799861fee7c6479ac3c5f525d136bba8b872694f`` (FrameIt 1.1.0).
The checkout was not reset. The existing untracked ``opencode.json`` was preserved.
This C0 record supersedes historical test counts as a current baseline; it does
not supersede the scientific limitations in the P0--P5 method notes.

This page is the **historical C0 snapshot**. The subsequent :doc:`fa_epygram_c1`
implements the evidenced dense SURFEX reader and records its current scope,
retained native observations, verification and next-stage gates.

The maintained-reader direction is **EPyGrAM-backed SURFEX FA coupled to AROME
GRIB**, with independent native grids. EPyGrAM independence is no longer a design
constraint. C0 establishes evidence and a finite cleanup plan. SURFEX execution
through FrameIt's EPyGrAM backend is still **blocked**, despite the successful
direct library experiments below. No production backend/default or output schema
changes in C0, and no legacy path is retired.

Reproducible baseline and dependencies
------------------------------------------------------------

The reference environment is ``frameit_env``. The existing Python-3.13 overlay
``build/p5-epygram-env`` supplies EPyGrAM's unmodified dependencies. It passes
``pip check``; no dependency overrides or installed table edits were made.
The reference environment also passes ``pip check``. Version strings describe
the actual distribution/runtime queried, not proof of native coexistence.

.. list-table:: Actual C0 runtimes
   :header-rows: 1
   :widths: 30 24 24 22

   * - Component
     - Reference
     - EPyGrAM overlay
     - Core-only
   * - Python / pytest
     - 3.13.16 / 9.1.1
     - 3.13.16 / 9.1.1
     - 3.13.16 / 9.1.1
   * - NumPy / SciPy / xarray
     - 2.5.4 / 1.18.1 / 2026.9.0
     - Same
     - Same
   * - netCDF4
     - 1.7.4
     - 1.7.2
     - 1.7.4
   * - EPyGrAM / falfilfa4py / ctypesForFortran
     - absent / 1.3.0 / 2.2.1
     - 2.1.0 / 1.2.1 / 1.3.0
     - all absent
   * - FA-bundled ecCodes C API
     - 2.48.0
     - 2.44.0
     - absent
   * - cfgrib / Python eccodes
     - 0.9.15.1 / 2.48.0
     - 0.9.15.1 / 2.44.0
     - both absent
   * - GRIB ecCodes C API
     - 2.50.0
     - 2.50.0 (eccodeslib 2.50.0.33)
     - absent
   * - xESMF / ESMPy
     - 0.9.2 / 8.9.1
     - Same inherited installation
     - both absent
   * - ecTrans
     - absent
     - 1.6.0 installed, not imported by FA gridpoint requests
     - absent

EPyGrAM 2.1.0 declares exact upstream requirements for eccodes 2.44.0,
falfilfa4py 1.2.1, ecTrans bindings ``ectrans4py`` 1.6.0 and netCDF4 1.7.2,
plus bronx, footprints, taylorism, NumPy, pyproj, pytest and PyYAML.
The actual helper has bronx 2.1.2, footprints 2.0.0, taylorism 1.1.0 and
pyproj 3.8.0. The bundled native FA source revision is not independently
verified by these package or ecCodes version strings.
``fa`` still pins falfilfa4py 1.3.0; combining both extras is not a coherent
installation. The separate pre-existing P4 helper has falfilfa4py 1.3.0,
ctypesForFortran 1.3.0 and ecTrans 1.6.0; its applicable native CI modules pass.

The prior core virtual environment now contains GRIB packages and was not used
as evidence of GRIB absence. A fresh ignored ``build/c0-core-env`` was cloned
**offline** from the reference, then its FA, GRIB and ESMF/xESMF packages removed.
``find_spec`` confirms absence of falfilfa4py, ctypesForFortran, EPyGrAM,
ecTrans, cfgrib, eccodes, xesmf, ESMF and esmpy. The original environments were
preserved. The clone is a local optionality check, not a clean-install or wheel
distribution qualification. Hosted CI and Python 3.10 were not executed locally.

The untouched-HEAD full reference suite reports **604 passed, 1 optional skip,
2 subtests passed**, 722 cfgrib/xarray future warnings, 320.28 s. The untouched-HEAD
EPyGrAM-stack full suite reports **605 passed, no skips, 2 subtests passed**,
2054 warnings, 316.24 s. The reference skip is the absent optional P4 candidate;
that test passes with the candidate installed. Existing native tests were not
skipped in the environments containing their required backends.

Further initial checks: native focused matrix **117 passed, 1 optional skip**;
EPyGrAM CI modules plus spectral module **32 passed**; core CI modules plus the
no-FA NetCDF coupling case **80 passed, 28 dependency-only skips, 2 subtests
passed**; separate P4 native CI modules **22 passed**. Fresh artifacts are under
ignored ``build/c0-*``. Final verification after adding the C0 evidence tests is
recorded in the packaged manifest below.

After the three C0 evidence cases were added, full regression is **607 passed,
1 optional skip, 2 subtests passed** in the reference environment (308.12 s),
and **608 passed, no skips, 2 subtests passed** in the EPyGrAM stack (302.96 s).
The final native focused check is **120 passed, 1 optional skip**; the required
EPyGrAM job's exact modules report **25 passed**; the updated core check is
**80 passed, 31 dependency-only skips, 2 subtests passed**. Warning categories
remain upstream cfgrib/xarray future warnings, netCDF4/NumPy deprecation warnings
and an isolated NumPy/netCDF binary-size runtime warning in focused runs.

The six-case packaged ``--ci --profile core`` matrix passes (AROME GRIB and
Meso-NH NetCDF, native and polar products). Here ``profile core`` is the matrix
profile name, not the extras-absent environment. Four schema-only examples, a
compact NetCDF/native-FA coupled dry-run, strict docs and wheel build pass.
The dry-run records the common-time exclusion warning and creates no output
directory; it is a compatibility check, not the unimplemented primary pair.

Repository-wide ``ruff check src/frameit`` is **not green**: unchanged
``processing/polar/conservative.py`` has E501 at lines 89/153/323 and B905 at
line 300. All four were reproduced by linting ``git show HEAD:...``; neither
the file nor lint rules were changed. Ruff 0.17.1 passes for both C0 Python
files. This is precisely identified baseline lint debt; no regression-test
failure is hidden by it. Initial Sphinx title-underlining warnings were repaired
and the strict build rerun successfully.

Actual library APIs and compact evidence
------------------------------------------------------------

The inspected source is the installed, unmodified EPyGrAM 2.1.0
``formats/FA.py``, ``formats/fafields.py``, ``data/sfxflddesc_mod.F90``,
``formats/GRIB.py`` and ``geometries/{AbstractGeometry,ProjectedGeometry}.py``.
Their function names below are concrete APIs, not inferred future interfaces.
EPyGrAM remains external software under CeCILL-C; no source/tables are vendored.

``frameit.testing.fa_epygram_probe`` is an investigation-only executable. It
opens a single read-only resource, bounds record counts and selected full native
arrays, limits typed records to 4096 words and the existing named structural
layout, and disables core dumps. FA and GRIB run in separate fresh interpreters
with separate format-only private EPyGrAM configurations, one native thread and
no inherited definition overrides. The FA probe instruments native calls in
memory; installed packages are untouched. It returns array counts, not physical
values, and reports native errors separately from the library's classification.
Per-call errors in its JSON are evidence to review, not an overall admission pass.

``test_fa_epygram_probe.py`` constructs deterministic 7-by-9 SURFEX files at hour
1 through the low-level fixture writer. Independent truth is
``280 + 10*j + i``, with an explicit NaN at [1,1] and a valid zero at [2,2].
Direct EPyGrAM reads agree **exactly**, not just with a re-read by the fixture
writer. The regular grid and spherical Lambert geography agree with separate
angular/formula checkpoints within the existing 2e-5-degree header-precision
bound. This is a compact grid/header bound, not a real-producer accuracy claim.
The two-message compact GRIB fixture independently prescribes level/date/unit
metadata and tests an exact selector and ambiguity rejection.

.. list-table:: FA API findings
   :header-rows: 1
   :widths: 28 42 30

   * - Responsibility / actual API
     - Observed result
     - Admission implication
   * - ``formats.resource(..., fmt='FA', openmode='r')``; ``listfields()``
     - One native open, geometry read and close per direct transaction.
       ``listfields`` excludes the seven cadre records and DATX header.
     - Suitable inventory lifecycle. Preserve duplicate/index-length/budget
       checks with narrow observations on this resource, not another open.
   * - ``readfield(name, getdata=False)``
     - H2D metadata, no FACILO/FACILE/FALAIS payload calls for selected
       gridpoint fields. Unselected SST is not physically read.
     - Use selected-only calls. Calling ``getdata(d4=True)`` safely verifies
       no data; default ``getdata()`` squeezes None in this version.
   * - ``readfield(name)``; ``field.getdata()``
     - One FACILO for requested T2M; exact 7-by-9 values, one NaN and one
       valid zero. Float64 output; no automatic support-label mask.
     - Replaces physical decode/reshape. Preserve native missing handling,
       physical support distinctions and full-native allocation budget.
   * - ``fieldencoding``; ``field_type``; private ``_fanion``
     - Encoding exposes spectral/KNGRIB/KNBITS/KSTRON/KPUILA. ``_fanion``
       converts -91/-93/-94 to Misc; ``field_type`` may override it from tables.
     - Keep a narrow selected native-error observation. Tables and a Misc
       classification cannot establish that a failing physical record is metadata.
   * - ``readfield`` / ``MiscField.getdata``; ``sfxflddesc.get/nature/dim``
     - C0 PROGRAM, N0 VERSION, L0 PACK/L2D, X0 LAT0 match prescribed
       bytes/types (AROME, 8, false/true, -20.25).
     - Reuse matched typed reads; validate source/directory facts and logical
       conventions. Library tables alone are not release-qualified definitions.
   * - Same accessor, ``SFX.DTCUR`` T0
     - Four-word mixed date/real-seconds record becomes scalar integer 2026.
       The synthetic hour-1 clock and real hour-12 clock are lost.
     - Cannot replace state/header clock checks with this scalar. Need upstream
       typed support or a narrow version-matched structural accessor on the same handle.
   * - Same accessor, ``SFX._FBUF_*``
     - No table entries. Fallback returns int64 arrays: SIZE [3], ASCII word
       arrays for NAME/TYPE/MASK, DIM1 [63,63,63], DIM2 [-1,-1,-1].
     - Reuse exposed arrays, retaining a small checked directory adapter
       (32/2/16-character widths, row count, duplicate IDs and exact dimensions).
   * - Typed arrays (installed implementation)
     - N1 copies int64 words. L1 uses a byte-wise bool view; C1 raises
       NotImplementedError. These are source-inspection findings, not qualified layouts.
     - Keep logical/character physical arrays gated. Require independent word,
       endian, shape and logical-value references before admission.
   * - ``geometry.dimensions/grid/geoid/projection``; ``ij2ll``, ``ll2ij``,
       ``ij2xy``, ``get_lonlat_grid``, ``gimme_corners_ij``, ``extract_subzone``
     - Modern regional grids, native CI/C/E facts and pressure-valued interface
       A/B are available. Projected geometry also exposes private ``_proj``.
     - Thin labelled-grid/CRS adapter is viable. Preserve source indices,
       canonical CF coordinates, Earth-model origins and independent checkpoints.

The generic FA reader does not consult the file's FBUF directory when decoding
H2D data; the physical payload supplies the full rectangular shape. It neither
reconstructs an evidenced sparse SURFEX support map nor independently verifies
units or scaling. ``SFX.PACK`` and native ``KNGRIB`` are distinct: the supplied
history has **PACK=0 and FA KNGRIB=120**, not an unpacked native encoding.
No structured FMULTM/FMULTE query was found in the inspected wrapper/API.
Absence of a warning is not evidence of identity scaling.

Bounded supplied-corpus checks
------------------------------

Only the previously supplied two FA histories and one GRIB container were used.
All opens were read-only; size/mtime were unchanged before and after each probe.
This is freshness evidence, not a content checksum, second-copy comparison or
corruption test. No private payload, full index or absolute sample path is stored
in the evidence manifest. No data were downloaded or uploaded.

* Surface: EPyGrAM lists 114 non-header records (122 including headers).
  Selected metadata for T2M/SST/HU2M/TSRAD/TG1P1/WG1P1 succeeds with zero physical
  metadata decodes. One explicitly requested T2M native array was decoded under
  ``max_points=6300000`` (6291456 float64 points, approximately 50.3 MB before
  library/probe copies). It still emits ``has no encoded FMULTM and FMULTE``.
  The upstream API returns an array, but **no physical values or scientific product
  are accepted** by this investigation. Production's missing-scaling failure stays.
* The surface storage is [2048,3072]; native CI is [2037,3061], I-width 16,
  C is [2005,3029], CI offset [0,0]. IMAX/JMAX and DIM_FULL describe CI
  (6235257), while selected X1 directory DIM1 is 6291456 and DIM2 is -1.
  Do not require DIM_FULL to equal storage size or fabricate a support map.
  The 56199 nonfinite returned points numerically equal the storage-minus-CI
  count; this count alone does not establish their positions or mask meaning.
* The native metadata baseline independently reports PROGRAM=AROME, VERSION=8,
  BUG=1, MASDEV=47, BUGFIX=0, PACK=0, matching state/header time at
  2026-10-21 12:00 from reference time 00:00. Support labels are FULL, SEA and
  NATURE. No SEA/NATURE physical payload was read in the real API probe.
* Atmosphere: 1345 indexed records, 1337 excluding headers. CLSTEMPERATURE
  metadata is gridpoint 120/16; three selected native calls (SURFPRESSION,
  S090TEMPERATURE, S090WIND.U.PHYS) still raise **-91** with falfilfa4py 1.2.1.
  EPyGrAM's table calls them H2D, while ``fieldencoding`` reports not H2D after
  its fallback. No atmospheric payload was read. S001TEMPERATURE is spectral
  103/18; even its H2D construction is avoided because spectral size inquiry
  can load ecTrans despite ``getdata=False``.
* GRIB: 574 headers (ceiling 600), grid [899,1395], distinct from FA. Exact
  meanSea, 10u at 10 m and isobaric t at 850 hPa selectors succeed without data.
  Native units, step/cycle keys and ``uvRelativeToGrid=0`` are retained. No real
  GRIB physical array was decoded by the EPyGrAM probe.

**Failure classification:** missing SFX definitions/scaling is an unresolved
decoder/producer-evidence problem; selected atmospheric -91 is a native header
failure of unknown cause; spectral/packed/typed support is representation-specific.
Readability of an index, unchanged file stats or a plausible array does not prove
source integrity. Unsupported headers and source corruption remain distinguishable
hypotheses requiring an authoritative header/error explanation and a trusted
decode or second known-good copy. None is reclassified as harmless metadata.

GRIB simplification decision
----------------------------

``GRIB.listfields(additional_keys=..., select=..., onlykey=...)`` and
``find_fields_in_resource(seed=...)`` can replace repeated hand-written header-key
collection/selection in ``preflight._grib_metadata`` and the coupled-only selector
scan in ``grib_utils.concat_grib2ds_by_vert_coord``. ``iter_messages(headers_only=True)``
is another bounded header API. ``readfield(handgrip, getdata=False,
read_misc_metadata=...)`` supplies selected geometry, validity and metadata.

This is not yet a simpler drop-in xarray loader. ``listfields`` scans headers
and caches by arguments; changing selector/key arguments can rescan. ``readfields``
builds an ecCodes index and eagerly constructs matching fields. ``iter_fields``
uses full messages even with ``getdata=False``. No equivalent lazy multi-file
xarray grouping/level selection/export path is qualified here. Explicit selectors
are still necessary to avoid constructing unrelated or unsupported fields.

A concrete compatibility trap is independently checked: the GRIB selector/native
metadata says **850 hPa**, but the EPyGrAM field's fixed-surface-100 level is
**85000 Pa**. Its object model cannot be relabelled as the current ``isobaricInhPa``
coordinate. Aliases (prmsl/u10/v10), cycles, intervals, units, scan orientation,
unmapped products, per-message grid identity and wind flags remain public-contract
responsibilities. Keep the working cfgrib/ecCodes loader until a separate bounded
GRIB step proves equivalent values/masks/metadata/laziness and independent output
parity through a **GRIB-only** boundary. FA-only and GRIB-only availability were
asserted in the probes; no same-process coexistence experiment is claimed.

Finite family/operation matrix
------------------------------

I = inventory/selected metadata, T = typed structure, D = physical decode,
X/E/P = labelled dataset / native export / optional polar, Q = diagnostics or
physical-coordinate derivation. V = verified compact synthetic scope only;
L = limited/observed; B = blocked; -- = inapplicable. Direct library evidence
does not change FrameIt's currently admitted families.

.. list-table:: C0 admission boundary
   :header-rows: 1
   :widths: 25 20 25 30

   * - Family
     - FrameIt I / T / D / X,E,P / Q
     - Direct EPyGrAM evidence
     - Gate / next owner
   * - Dense SURFEX PACK=0, X1, instantaneous scalar
     - Native V / L / V / V,V,L / B; EPyGrAM execution B
     - V selected D and metadata on two regional fixture geometries
     - C1 one-resource admission with semantics/scaling guards; C3 coupled products
   * - Real priority SFX SST/T2M/HU2M/TSRAD
     - L / L / B / B,B,B / B
     - Metadata L; one T2M API read emits missing-scaling warning
     - Release-matched units/scaling/time, trusted values/masks, Earth model
   * - C0/N0/L0/X0 structure; FBUF N1/character words
     - L / V limited / -- / -- / --
     - Scalars and integer directory words match fixtures; directory adapter needed
     - C1 preserve byte/type/count/directory contradictions and metadata budgets
   * - Mixed T0 state date
     - L / V native / -- / -- / --
     - Generic accessor loses all but year
     - C1 narrowly justified same-handle accessor or upstream fix
   * - Packed/support maps, X2, physical N1/L1/C1
     - L / B / B / B,B,B / B
     - No independent packed/type/map reference
     - C5 independent type/order/scatter/gather/missing evidence
   * - Soil/snow/layer/patch/tile
     - L / L / V individual dense names only / V,V,L / B
     - Directory labels observed, no scientific axes/weights qualified
     - C5 original axes/bounds/fractions; no tile averaging by availability
   * - Atmospheric gridpoint scalar / declared P5 cubes
     - V / L / V / V,V,L / B
     - Existing isolated EPyGrAM cube/column/export regressions pass
     - Preserve full/interface labels/indices, A*PREFER/B and sparse selection
   * - Atmospheric -91 records
     - L / -- / B / B,B,B / B
     - Same three native errors on alternative stack; library types conflict
     - Upstream header/error specification and independent decode/copy
   * - Atmospheric spectral 103/18
     - L / -- / B / B,B,B / B
     - Encoding only; P4 analytical transform candidate passes separately
     - C5 coefficient contract and independent real transformed fields
   * - Collocated physical vectors
     - V synthetic / -- / V / V,V,L / selected existing operations only
     - Existing P5 independent both-hemisphere and idempotence cases pass
     - Keep explicit basis/companions; staggered/map-scaled production variants B
   * - Intervals, flux/rain rates, static/PREP
     - L / L / B FA interval execution / B,B,B / B
     - Library validity defaults/tables do not establish field support
     - Multi-time bounds/resets/signs; separately selected conversions
   * - AROME GRIB atmosphere
     - Existing route L / -- / L / L,L,L / separately selected methods
     - Compact and real exact metadata/selection V/L; replacement B
     - Bounded GRIB parity step, Pa/hPa translation and format isolation
   * - GRIB + EPyGrAM SURFEX, distinct grids, multiple times
     - L component metadata / -- / B / B,B,B / --
     - No current end-to-end EPyGrAM SURFEX product
     - C1/C2 then C3 real GRIB containers + synthetic SFX, sync/spawn/fresh readers
   * - Extra projections/global/reduced/other producers
     - B / B / B / B,B,B / B
     - Library capability is broader than FrameIt's qualification
     - Separately scoped evidence; not prerequisites to dense primary delivery

Cleanup ledger (no retirement at C0)
------------------------------------

Paths below are relative to ``src/frameit/``. Each row has a current caller,
concrete replacement or reason to retain it, regression anchor and remaining gate.

.. list-table:: Responsibility transfer ledger
   :header-rows: 1
   :widths: 24 27 28 21

   * - Current code / callers
     - Replacement / disposition
     - Essential retained contract
     - Tests / evidence gate
   * - ``fa_worker.handle`` raw FAITOU -> ``_inspect`` -> EPyGrAM resource
     - C1 replace double lifecycle with one resource; library geometry/validity/listfields
     - OLD/read-only, KEEP/close, before/after freshness; no fallback reader
     - ``test_fa_io``, new probe; count one open/close in production tests
   * - ``_inspect`` header/date/index; CLI, coupled inventory, preflight, FA loader
     - C1/C2 library validity/geometry/inventory; narrow lengths/clock observations if needed
     - Duplicate IDs, corrupt dates/cycles, selected failures and bounded inventories
     - ``test_fa_baseline``, ``test_fa_contracts``, ``test_fa_pipeline``
   * - ``_words/_text/_integer/_typed_metadata`` and FBUF assembly in ``_inspect``
     - C1 use matched Misc reads; thin directory adapter; document T0 exception
     - Actual word type, source assertions, width/count, PACK/dimensions/state clock
     - ``test_fa_surface``, ``test_fa_contracts``; DTCUR gap blocks wholesale removal
   * - ``_inspect`` direct FANION and spectral/type gates
     - Library ``fieldencoding`` for successful facts; keep small raw error probe
     - Selected -91/-93/-94 fatal; unselected failures not decoded; no coefficients as values
     - ``test_fa_baseline``, ``test_fa_spectral``; library fallback is insufficient
   * - ``handle`` FACILO, reshape/undefined handling
     - C1 ``readfield/getdata`` through existing EPyGrAM adapter
     - Max full native points before allocation, NaNs/valid zeros, selected crop/key before transfer
     - ``test_fa_io``, ``test_fa_surface``; exact and strided/reversed/masked truth
   * - ``fa_geometry`` header reconstruction/signature; preflight and ``fa_utils``
     - C2 thin geometry/zone/CRS adapter, not a second projection engine
     - Earth model origin, CI/C/E offsets, native axes, corners, no fitting;
       preserve existing CF coordinate origins even if library x/y are recentered
     - ``test_fa_geometry``, ``test_fa_mapping``; same-shape different-grid rejection
   * - ``fa_cubes``; ``inspect_fa_inputs``, ``fa_metadata_dataset``, loader
     - Keep public-contract assembly; reuse selected field/vcoordinate facts
     - Exact declared records/full/interface axes; A normalized vs Pa; no pressure diagnosis
     - ``test_fa_cubes``; library sortfields/name grouping is not sampling proof
   * - ``fa_contracts``; worker/backend/preflight/provenance
     - Keep semantic/evidence adapter; reduce duplicate headers only after contract review
     - Native facts versus user completion, explicit units/time/basis, masks and original IDs
     - ``test_fa_contracts``, ``test_fa_cubes``; no unverified table promotion
   * - ``fa_backend.request_fa``; CLI, ``FaArray``, ``inspect_fa``
     - Keep transport boundary, not format logic
     - Lock, fresh interpreter, timeout/crash, threads, environment filtering,
       protocol/NPY validation, transfer cleanup and scaling-diagnostic guard
     - ``test_fa_io``, ``test_fa_contracts``, ``test_hpc_execution``; no structured scaling replacement
   * - ``fa_utils.FaArray``/loader; runner
     - Keep lazy selected-only xarray/Dask and dataset adapter
     - Serializable requests only, crops/indices, source cycles/grid/vertical consistency
     - ``test_fa_pipeline``, ``test_fa_surface``, ``test_fa_cubes``
   * - ``preflight._grib_metadata`` and ``grib_utils`` header-selector scan; coupled/runner
     - Candidate GRIB listfields/select/misc metadata; separate parity step
     - Aliases/units/levels/time, lazy payloads, wind flags, grid identity, unmapped products
     - ``test_output_layout``, ``test_configuration_v2``, ``test_fa_pipeline``, CI matrix
   * - ``grib_utils`` cfgrib grouping/concat/selection; runner
     - Retain until replacement is simpler and independently equivalent
     - Native versus prepared branches, selected levels/neighbours, resource ownership
     - No demonstrated lazy EPyGrAM equivalent; C0 metadata success is not loader parity
   * - ``coupled.prepare_sources``/alignment, preflight, runner/export/execution
     - Keep orchestration and ordinary atomic NetCDF/status mechanisms
     - Common default warnings/full exclusions, strict, independent grids,
       geometry before target/budgets, bilinear continuous sampling, optional diagnostics
     - ``test_arome_fa_coupling``, ``test_coupled_shared_polar``, sync/spawn/fresh readers
   * - Configuration/extras/helper initialization; schema, CLI/templates/examples
     - C1 admit SURFEX; C4 consolidate backend/default/extras after parity
     - Python 3.13, YAML replay/relative paths/interpreter symlinks, absent-stack core
     - ``test_fa_cubes``, schema validations, core/native CI; incompatible pins still separate
   * - Test fixture writer, native/error and ecTrans probes
     - Retain independent evidence tools; no production caller to replace
     - Analytical truth, explicit selected calls, private-data-safe reports
     - New C0 tests and all P0--P5 tests; never replace truth with same-reader expectations

There are two independent duplication scales: **within each EPyGrAM transaction**,
``fa_worker.py`` opens raw FA and calls ``_inspect`` before checking the profile
and opening EPyGrAM; **between transactions**, coupled inventory, preflight,
loader construction and selected Dask reads may inspect again. C1 removes the
former; caching/process-lifecycle optimization of the latter needs measured costs
and freshness/resource preservation. No persistent service is justified by C0.

Concrete C1 admission and regression plan
------------------------------------------------------------

1. Retain the isolated worker/backend and introduce one EPyGrAM resource owner
   inside the existing adapter. Transfer qualified inventory/validity/H2D reads
   first. Replace both atmospheric-only checks (``configuration.validate_fa_options``
   and ``fa_worker.handle``) only when SURFEX admission tests exercise real reads.
   Do not relabel SURFEX as atmospheric or merely delete the checks.
2. Admit **AROME, dense PACK=0, X1, DIM2=-1, DIM1=storage X*Y** first, with
   complete, consistent FBUF/source metadata. Preserve CI versus storage and
   extension zones. Read structural metadata through EPyGrAM where trustworthy;
   implement only the documented small same-resource adapter for directory words
   and mixed DTCUR where required. No physical raw-word codec or alternate decoder.
3. Preserve explicit producer assertions and field declarations, native error
   observations and missing-scaling failure. Add typed scalar/array/mixed-date
   references, complete/incomplete/reordered/duplicate directories, wrong source,
   PACK/type/shape contradictions, state/header conflict and valid-zero/NaN tests.
   Keep unsupported selected records fatal and unsupported unselected records inert.
4. Demonstrate one open/close, no physical metadata reads and only selected
   FACILO payloads through the **production** worker. Reuse existing domain/key,
   reversed/strided, freshness, budget, timeout/crash/partial-transfer tests.
   Preserve no-GRIB/no-ecTrans imports in gridpoint children. The direct C0 probe
   is not that production-worker acceptance test.
5. Keep P5 atmospheric cubes, scalar YAML, NetCDF-only/core and existing native
   GRIB regressions. Run all focused and full suites and applicable CI jobs with
   required stacks present. Update actual backend/version provenance, examples
   and migration notes only to describe the admitted behavior. Canonical extra
   consolidation/default changes and legacy deletion await C4 parity.
6. Carry C2 geometry qualification forward using independent CI/C/E offset and
   both-hemisphere checks, grid identity and canonical CF origin parity. Then C3
   must exercise at least two times with real GRIB containers and EPyGrAM-decoded
   synthetic SURFEX on distinct grids, common/strict exclusions and moving centres,
   disabled/shared polar paths, exact common targets and sync/spawn exports reopened
   by a fresh ordinary reader. A GRIB implementation switch is not a C1 prerequisite.

Real-producer admission additionally needs release-matched units/scaling/time and
support definitions, verified Earth model/geographic checkpoints, trusted physical
values/masks and multiple times. The supplied single-time corpus cannot supply
those references. Atmospheric spectral/-91, additional packed/types/layers and
physical-coordinate/vector transformations retain their separate evidence gates.
No automatic diagnostic, deaccumulation, pressure/height calculation, vector
conversion, support filling, or human scientific approval follows from C0.

Verification commands and investigation provenance
--------------------------------------------------

Commands below use the current checkout, the reference conda launcher on PATH,
and **fresh** designated output directories. All test/native commands used
``TMPDIR="$PWD/build" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1``.
``/tmp`` was nearly full; no unrelated temporary files were removed. The
reference test prefix additionally selects the existing EPyGrAM helper:

.. code-block:: bash

   export TMPDIR="$PWD/build" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
   export FRAMEIT_TEST_EPYGRAM_PYTHON="$PWD/build/p5-epygram-env/bin/python"
   conda run --no-capture-output -n frameit_env python -m pytest -q \
       --basetemp build/c0-reference-full --junitxml=build/c0-reference-full.xml
   conda run --no-capture-output -n frameit_env build/p5-epygram-env/bin/python \
       -m pytest -q --basetemp build/c0-epygram-full --junitxml=build/c0-epygram-full.xml
   conda run --no-capture-output -n frameit_env python -m pytest -q \
       src/frameit/testing/numerical/test_fa_*.py \
       src/frameit/testing/numerical/test_arome_fa_coupling.py \
       src/frameit/testing/numerical/test_coupled_shared_polar.py \
       --basetemp build/c0-native-focused --junitxml=build/c0-native-focused.xml
   conda run --no-capture-output -n frameit_env build/p5-epygram-env/bin/python \
       -m pytest -q src/frameit/testing/numerical/test_fa_cubes.py \
       src/frameit/testing/numerical/test_fa_io.py \
       src/frameit/testing/numerical/test_fa_pipeline.py \
       src/frameit/testing/numerical/test_fa_spectral.py \
       --basetemp build/c0-epygram-ci --junitxml=build/c0-epygram-ci.xml

The initial core command enumerated the current ``core-batch`` workflow modules
and added ``test_fa_pipeline.py::test_coupled_netcdf_sources_do_not_need_fa_backend``.
Final commands use the same modules plus the new C0 module; the exact module lists
and results are in the packaged manifest. The spectral helper executed exactly
``test_fa_spectral.py test_fa_io.py test_fa_pipeline.py`` with ``--basetemp
build/c0-spectral-ci --junitxml=build/c0-spectral-ci.xml``. Native CI job definitions
remain active; C0 probes are added to the required EPyGrAM job and core optionality job.

Ancillary commands (reference environment; all pass except the four baseline
repository-wide Ruff findings identified above):

.. code-block:: bash

   frameit validate example/config_file/coupled_fa.yaml --schema-only
   frameit validate example/config_file/coupled_cyclone_polar.yaml --schema-only
   frameit validate example/config_file/coupled_arome_fa_polar.yaml --schema-only
   frameit validate example/config_file/arome_fa_native_cubes.yaml --schema-only
   frameit run build/c0-api/coupled-dryrun.yaml --dry-run
   frameit run-matrix-test --ci --profile core --output build/c0-matrix
   ruff check src/frameit
   ruff check src/frameit/testing/fa_epygram_probe.py \
       src/frameit/testing/numerical/test_fa_epygram_probe.py
   LC_ALL=C LANG=C sphinx-build -q -W --keep-going -b html \
       docs/source build/c0-docs-handover
   python -m pip wheel --no-deps --no-build-isolation . -w build/c0-wheel-handover
   git diff --check

API probe recipe (select an authorized read-only sample; no full-archive run):

.. code-block:: bash

   # PYTHON selects the qualified helper; use a fresh process for EACH format.
   "$PYTHON" -m frameit.testing.fa_epygram_probe FA "$SURFACE_FA" \
       --fields SFX.T2M SFX.SST SFX.HU2M SFX.TSRAD SFX.TG1P1 SFX.WG1P1 \
       --read-fields SFX.T2M --max-points 6300000 \
       --metadata-fields SFX.PROGRAM SFX.VERSION SFX.PACK SFX.DTCUR \
       SFX._FBUF_SIZE SFX.IMAX SFX.JMAX SFX.DIM_FULL
   "$PYTHON" -m frameit.testing.fa_epygram_probe FA "$ATMOSPHERE_FA" \
       --fields CLSTEMPERATURE SURFPRESSION S090TEMPERATURE S090WIND.U.PHYS S001TEMPERATURE
   "$PYTHON" -m frameit.testing.fa_epygram_probe GRIB "$ATMOSPHERE_GRIB" \
       --max-records 600 \
       --selectors '[{"typeOfLevel":"meanSea"},{"shortName":"10u","level":10},{"shortName":"t","typeOfLevel":"isobaricInhPa","level":850}]'

These commands were bounded to 120 s per invocation by the execution harness.
Future invocations should use an equivalent external timeout. Review both JSON
and native stdout/stderr before sharing: native diagnostics/errors can disclose
information beyond the deliberately omitted source-path/physical-array fields.

.. literalinclude:: ../../../src/frameit/testing/catalogs/fa_c0.yaml
   :language: yaml

Migration and outputs: **none in C0**. Existing single-source/coupled YAML,
``backend: native`` and the atmospheric EPyGrAM cube example retain their meanings.
Changing a SURFEX example to ``backend: epygram`` still fails. Existing NetCDF
dimensions, units, native/vertical/source-qualified products, common/strict time
policies, bilinear defaults, diagnostics optionality and run provenance are
unchanged. This document and manifest add investigation provenance, not a producer
preset or automatic capability switch. C1 admission and later C4 migration require
their own verified changes and explicit effective-backend provenance.
