EPyGrAM C5: distribution and resource qualification
======================================================================

The selected C5 row is **distribution/resources**, starting at ``5d990cc``.
This is the C5 snapshot at ``0a328b7``. The subsequent :doc:`fa_environment`
qualifies a fresh single-environment installation while retaining FA subprocess
isolation; the historical overlay failure and measurements below remain evidence.
This increment qualifies the existing dense SURFEX/AROME-GRIB boundary with compact
fixtures. It does not admit a new scientific family. C1--C4's maintained reader,
configuration migration and finite numerical contracts remain the foundation.
The per-row status, dependencies and exact verification commands are recorded in
the packaged manifest below. Successful tests are engineering evidence, not
producer qualification or human scientific approval.

Transfer and failure boundary
-----------------------------

``io/fa_backend.py`` now rejects invalid, negative, Boolean, excessive-rank or
over-budget transfer shapes before opening the array. The existing ``max_points``
budget also bounds each transferred axis and total element count. NumPy maps the
NPY read-only, checks its actual float64 dtype/shape against the response, then
copies the admitted array before removing the private transaction directory.
A corrupt NPY header therefore cannot cause an unchecked eager array allocation.
Malformed JSON and truncated/invalid NPY errors include the source/field context.
This is transfer validation, not a new FA codec or alternate-reader fallback.

The new ``test_fa_resources.py`` uses real disposable processes for SIGSEGV and
timeout injection. It verifies child reaping, removal of partial transfers,
environment isolation, lock release and a successful subsequent request with an
independent NaN/valid-zero reference. Header/dtype and declared-shape failures are
checked before array materialization. A selected helper shim injects truncated
transfers into actual multi-time GRIB/SURFEX runs, including spawned export:
failed status is retained, the surface product is not published, partial output
and ownership locks disappear, and all fixture source bytes remain unchanged.
Already completed other products may remain: publication is atomic per product,
not an all-products transaction. Existing independent ordinary-reader, geometry,
cube, vector, common/strict time and shared-bilinear-target regressions still run.

Resource limits retain their meaning: one fresh helper per transaction, one
native thread, serialized requests per consuming process, selected fields/times
only, and a **full native record** allocation budget even for a tiny crop. These
are point/concurrency/time bounds, not an operating-system RSS quota. Library
workspaces, coordinates, mapped transfer pages and the detached copy contribute
to peak memory. No persistent worker, cache, scan reduction or native-lifecycle
optimization is introduced.

Measured compact workload
--------------------------

The existing production-worker instrumentation in
``test_fa_epygram_surfex.py::test_one_resource_library_structure_and_selected_payload``
now writes ``measurements.json`` into each retained pytest case directory.
It records process and worker wall time, helper CPU/high-water RSS, kernel block
I/O, source/NPY byte counts, native opens/closes, library inventory calls, index
rewinds and selected physical decodes. CI retains these small, value/path-free
measurement files. Counters are asserted; timings are observations without flaky
performance thresholds.

The recorded local workload uses separate 7-by-9 regular-angular and spherical
tangent-Lambert SURFEX files, each 98,304 bytes, with two fields and explicit
NaN/valid-zero truth. One metadata transaction and one selected reversed/strided
3-by-3 read are measured for each geometry. Each transaction has one native
open/close, one ``listfields`` call and two index rewinds (the narrow header
observation and the library inventory). Metadata performs zero physical decodes;
read performs one selected EPyGrAM/FACILO decode, not an unselected SST read.
Nine float64 values are 72 payload bytes and **200 NPY bytes**; metadata transfers
no NPY. The selected native record is still 63 points / 504 decoded bytes.

The focused measurement run observed 0.364--0.474 s per fresh process and
0.236--0.332 s inside initialization/worker execution. Whole-helper high-water
RSS was 361,980--362,108 KiB. Kernel block reads were zero on this cached workload;
block writes were 8,192--1,744,896 bytes, including private library configuration
and other helper I/O, not just the NPY. These are single samples, not a cold-I/O
benchmark, memory scaling law, production estimate or speedup claim. Native code
revision and producer scientific definitions are not established by these counts.

Python-3.13 wheel and deployment boundary
-----------------------------------------

The qualified deployment remains a **GRIB/NetCDF/ESMF parent plus an isolated,
coherent EPyGrAM FA helper**. ``environment.yaml`` and the coupled example identify
that layout. Install FrameIt in both; select the helper with the existing
``input.fa.python_executable`` key. Helper paths remain YAML-relative and venv
symlinks retain their meaning. No YAML schema, field definition, output dimension,
unit, missing policy, precision, compression or chunking changes are required.

Required native CI now also builds a wheel, installs it into a separate target,
checks that both interpreters import that installation and runs packaged
primary-pair native/shared-target sync/spawn exports and resource regressions.
These fixtures are generated locally and need no private payload or download.
The existing optionality, full/native and spectral-candidate CI gates remain.
The larger bundled real-fixture matrix is a local check: its ignored binary
payloads are not available in a fresh Git checkout and are not added or uploaded
by this increment.

The C4 shared-overlay shutdown defect remains a separate distribution gate.
The C5 wheel matrix rerun completed all six cases, then the overlay process
segfaulted during shutdown; its command failed despite the preceding internal
``Exit code: 0`` message. The same wheel's matrix in the reference parent exited
normally. No cause is localized and no native dependency/import-order workaround
or claimed repair is introduced.
Import order, matching package versions and a passing helper suite cannot qualify
that environment. Broader same-environment/platform or clean-install claims need
a localized upstream/native fix and independent reruns, including normal process
shutdown. Hosted CI and Python 3.10 are not local verification results.

Capability status and next prerequisites
-----------------------------------------

* **Qualified, finite engineering scope:** evidenced AROME-47 / SURFEX-8.1 dense
  PACK=0/X1 instantaneous records; existing regional angular/Lambert grids and
  declared gridpoint full/interface cubes; multi-time primary pair with independent
  source grids and separately selected bilinear targets; tested failure cleanup.
* **Limited:** Python-3.13 Linux distribution in the tested parent/helper layout,
  compact resource measurements and existing explicitly declared collocated
  vectors. Clean installs, other distributions and real-producer scientific
  interpretation require their own evidence/review.
* **Blocked:** packed/support-map SURFEX and physical typed arrays need
  release-matched type/byte/order/map/missing and independent scatter/gather
  references; layer/patch/tile axes need original identities/bounds/fractions;
  per-field intervals/static products need field support, resets, units/signs and
  independent multi-time/static references. Individual dense layer-named records
  retain their existing raw names without invented axes or averaging.
* **Blocked:** selected spectral execution needs constants/zero/single modes,
  coefficient dimensions/order/sign/normalization/truncation and trusted real
  transformed fields. The gridpoint ecTrans import guard is unchanged. Additional
  vector/physical-coordinate operations require independent columns/vectors,
  explicit bases and selection. Atmospheric -91 failures need an upstream header/
  error explanation and trusted decode or known-good independent copy.
* **Unsupported in this increment:** additional regional geometries, other
  producers, global/reduced grids and new containers. Admission requires a selected
  demonstrated need and independent native-zone/geographical/value references.

Primary dense SURFEX/AROME-GRIB delivery remains independent of those blocked rows.
Priority real SFX fields still need producer-specific scaling, units, time support,
masks, Earth model, trusted values and required scientific review. Diagnostics,
pressure/height diagnosis, rates/deaccumulation, averaging, vector conversion and
tracking eligibility remain separate explicit selections.

Verification record
--------------------

Untouched full baseline: **694 passed, 3 absence-only skips, 2 subtests passed**.
After the boundary changes: **706 passed, 3 absence-only skips, 2 subtests passed**.
Core-only CI: **110 passed, 136 dependency-only skips, 2 subtests passed**, with
the native optional packages genuinely absent. The focused resource/measurement/
I/O check passes **20 tests**. No installed required backend is skipped, no legacy
path is retired and no independent tolerance or existing assertion is weakened.
Initial added checks reproduced six boundary failures; the first integration run
also exposed a test shim hard-coded to T2M when a spawned exporter selected SST.
The shim now preserves the actual requested identity; failure assertions remain.
Native CI passes **219 tests** (three absence-only skips); spectral-candidate CI
passes **31**. Wheel-installed primary-pair/resource cases pass **16**, with fresh
ordinary readers and actual helper provenance; the wheel's core-only transfer
check passes **10**. The reference six-case matrix, four schema examples, compact
shared-target dry-run, strict docs, wheel/source/extra checks and changed-file
Ruff pass. Repository Ruff retains four unchanged ``conservative.py`` findings,
reproduced directly from ``git show HEAD``. The shared-overlay matrix is a
**failed command**, not a passing distribution check. Exact commands and gaps
are enumerated below. The code-bearing wheel was tested before final evidence
metadata was filled in; the final rebuild includes that completed manifest.

.. literalinclude:: ../../../src/frameit/testing/catalogs/fa_c5.yaml
   :language: yaml
