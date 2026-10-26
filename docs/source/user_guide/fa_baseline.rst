FA P0 baseline and finite qualification matrix
==============================================

Evidence date: **2026-10-26**. Starting revision:
``06a9d62ae70ed6462e7a1251d50d2af687364087``, clean working tree,
FrameIt 1.1.0. This is the P0 evidence freeze, **not full FA compatibility**.
Every target below is either limited by named evidence or explicitly blocked.
The initial 2026-10-22 handover is historical evidence, not today's test result.
The active phase is now scoped to AROME atmospheric and AROME-produced SURFEX FA.
Other producer/native-container integrations and global/reduced FA are outside
this phase's acceptance matrix; adding them is not a completion prerequisite.

Current checks and corpus
------------------------------------------------------------

The supplied directory contains exactly two FA histories and one GRIB product.
Native FA open/header/date/index operations succeed for both histories; GRIB
message headers identify the third container. No supplied plain LFI or NetCDF
case is present. FA is an overlay on LFI: a successful LFI index alone cannot
identify FA, producer, scientific quantities or release. Unknown files must not
be identified by their suffix alone.

The manifest below retains basenames, stat freshness, native header facts,
selected encoding probes, clocks, runtime and missing references. Source paths,
full indexes and physical arrays are not retained. Size/mtime checks before and
after reads were unchanged; this is not checksum or corruption verification.
Both FA files have only one valid time. Their matching rectangular header facts
do not establish identical masks, physical sampling or vertical coordinates.
The GRIB grid differs and is not a pointwise reference for native FA.

No real physical payload was decoded in P0. Historical selected scalar decodes
and the small three-source exercise are regression context only. In particular,
historical SFX missing-scaling warnings have not acquired an independent physical
reference. ``allow_unscaled`` remains an explicit, justified opt-in, not a
qualification or default fix. Producer Earth radius, release identity and field
definitions remain missing. ``KNIVER=90`` means levels, not header version.

.. literalinclude:: ../../../src/frameit/testing/catalogs/fa_p0.yaml
   :language: yaml

Finite target matrix
--------------------

Operations are **I** inspect, **D** decode, **X** labelled dataset,
**E** native extraction/export, **P** polar sampling, **Q** diagnostic.
``V`` means verified only on the named synthetic scope, ``L`` means
implemented-limited or native metadata observed, ``B`` means blocked by the
listed missing evidence/implementation. No real-producer row is fully verified.
``--`` means inapplicable to the stated operation. The later AROME/SURFEX science
rows remain explicit admission gates; new producer/container and global-grid
extensions are not part of this phase.

.. list-table:: P0 operation eligibility (not an execution configuration)
   :header-rows: 1
   :widths: 24 18 38

   * - Family / scope
     - I D X E P Q
     - Evidence, gate and precise request
   * - Regional instantaneous 2-D scalar histories
     - L L L L L B
     - Modern rectangular regular-lon/lat and tangent-Lambert only.
       Synthetic gridpoint packing-0 has V I/D/X/E, analytical values and
       independent geometry equations; optional polar origin truth only.
       Real 120/16 atmospheric and 120/24 SFX encoding probes succeed.
       Request multi-time trusted values/masks, producer release and Earth model.
   * - Failing atmospheric encodings
     - L B B B B B
     - Three indexed records fail native FANION -91; encoding/representation
       unknown. Request upstream record-header diagnosis and independent decode.
   * - Regional spectral atmosphere
     - L B B B B B
     - S001 temperature/U flags: spectral 103/18. No transform qualified.
       Request coefficient sizes/order/normalization and trusted transformed values.
   * - Native atmospheric 3-D fields
     - L B B B B B
     - Per-level names and hybrid arrays inspectable, not qualified cubes.
       Request full/interface definitions, sampling and independently known columns.
   * - Horizontal/vertical vectors
     - L B B B B B
     - U name/flags are not a wind-basis contract. Request producer pairing,
       staggering, map scaling, frame and independent vector references.
   * - SURFEX dense / packed layouts
     - L L/B L/B L/B L/B B
     - Dense X1 selected-record support only; no general typed/sparse reconstruction.
       Dense synthetic scalar pipeline verified. Packed decode blocked.
       Request PACK variants, support-map order, undefined values and typed truth.
   * - Soil/snow/patch/tile data
     - L B B B B B
     - Directory and individual native names only; no qualified axes/weighting.
       Request native indices/bounds/fractions and trusted layer/tile examples.
   * - Point / interval fields
     - L L/B L/B L/B L/B B
     - Explicit instantaneous scalar branch only; header interval marker is not
       field support. Request mean/accumulation/extreme definitions, resets,
       units, signs and multi-time reference; no implicit deaccumulation.
   * - Additional regional headers/projections
     - B B B B B B
     - No additional sample or header mapping. Request versioned headers,
       Earth models, anchors/orientations and independent geographic checkpoints.
   * - Static/PREP/state products
     - L B B B -- B
     - SFX state timestamp inspected in history only, not a PREP qualification.
       Request static/validity specification and representative product; no
       fabricated dates, track or diagnostic.

No new stable diagnostic, vector/vertical transform or conservation claim is
qualified here. FA production eligibility remains explicit instantaneous 2-D
gridpoint selection with declared meaning/scaling and admitted geometry.
The optional production continuous polar method remains bilinear.

Native -91 diagnosis and upstream packet
------------------------------------------------------------

The private-data-free probe implementation is
``src/frameit/testing/fa_native_probe.py``. Run it in a **fresh FA-only process**:

.. code-block:: bash

   python -m frameit.testing.fa_native_probe "$ATMOSPHERE_FA" \
       SURFPRESSION S090TEMPERATURE S090WIND.U.PHYS S001TEMPERATURE CLSTEMPERATURE

It opens OLD, closes KEEP, disables core dumps, bounds native threads, excludes
parent ecCodes definition overrides and only reads the index and encoding flags.
It neither decodes horizontal arrays nor imports FrameIt's reader, GRIB or
EPyGrAM. Source size/mtime is checked. JSON includes selected names, word counts,
call arguments and binding/native API versions; no source path or physical values.
Review native stdout/stderr too before sharing; library diagnostics can disclose
details independently of the JSON. No upload/issue creation is automatic.
The file can also be run directly with ``python fa_native_probe.py`` after
copying only that script into an upstream reproduction environment; FrameIt is
not needed there. Only the optional native package and its dependencies are used.

Observed calls (``wfanion(unit, prefix, level, suffix)``):

* ``SURF, 0, PRESSION``: -91; indexed length 1,410,925 words.
* ``S090, 0, TEMPERATURE`` and ``S, 90, TEMPERATURE``: -91;
  indexed length 1,411,016 words.
* ``S090, 0, WIND.U.PHYS`` and ``S, 90, WIND.U.PHYS``: -91;
  indexed length 1,411,016 words.
* Control ``S001, 0, TEMPERATURE`` and ``S, 1, TEMPERATURE`` both return
  ``[true, true, 103, 18, 0, 0]``.
* Control ``CLST, 0, EMPERATURE`` returns
  ``[true, false, 120, 16, 0, 0]``.

All failures emit ``FANION - ENTETE D'ARTICLE "" INCORRECT``. Classification:

* **Metadata versus physical record:** substantial indexed records are present;
  the error does not establish harmless metadata or quantity meaning.
* **Naming/layout:** both supported wrapper call forms produce the same result;
  the control succeeds in both forms. This weakens a simple prefix/level split
  hypothesis but does not prove all internal name/layout handling correct.
* **Encoding/backend:** native FANION fails without FrameIt or GRIB loaded.
  Binding 1.3.0, ctypesForFortran 2.2.1, wheel-native ecCodes API 24800.
  No encoding ID can be assigned to the failed records from these probes.
  Exact bundled FA source revision/producer compatibility remains unknown.
* **Corruption:** index/header readability and unchanged size/mtime neither prove
  nor exclude corrupted physical record headers. No trusted second copy or decode
  exists. Do not classify the source as corrupt based on -91 alone.

Authoritative API reference checked: the installed 1.3.0 ``falfilfa4py/FA.py``
documents ``wfanion`` prefix(4)/level/suffix(12) and returned encoding flags.
The installed wrapper SHA256 is recorded in the fixture manifest, identifying
the inspected API text without claiming a verified native Fortran revision.
The publisher's `PyPI 1.3.0 record
<https://pypi.org/pypi/falfilfa4py/1.3.0/json>`_ identifies FA as an LFI overlay,
its native dependencies and upstream bug tracker. It provides no trusted decode
or -91 interpretation. The linked ACCORD-NWP/FALFILFA repository/source endpoints
returned HTTP 404 during this investigation. Thus **authoritative native
record-header/error specification and independent decoding are blocked**, rather
than replaced with an inferred error meaning.

Prepared upstream request (maintainer can send after reviewing the output):

* Subject: ``falfilfa4py 1.3.0 FANION -91 on three indexed regional FA records``.
* Attach only reviewed probe code/output, runtime/manifest facts and exact calls.
  Include successful 103/18 spectral and 120/16 gridpoint controls.
* Ask which native revision/encoding families are bundled, what -91 means at
  this failure site, whether that producer/release is supported and which
  upstream-supported backend/definition versions should read these records.
* Ask for a licensed minimal synthetic reproduction or producer-approved reduced
  file plus trusted native-tool decode, mask and active header/encoding report.
  Request matched producer/build metadata and a second known-good copy/checksum
  to distinguish unsupported headers from corruption. Do not submit private
  records, raw words or full archives without explicit permission.

No native-code workaround, error-code metadata fallback, inferred identity
scaling or binary codec is introduced. Selected failures remain fatal, while
unselected records remain indexable.

Verification and P1 admission
-----------------------------

Reference environment command prefix is ``conda run -n frameit_env`` (the local
launcher was resolved explicitly during P0). Initial baseline command:

.. code-block:: bash

   python -m pytest -q src/frameit/testing/numerical/test_fa_io.py \
       src/frameit/testing/numerical/test_fa_geometry.py \
       src/frameit/testing/numerical/test_fa_pipeline.py

Result: **16 passed**, one NumPy/netCDF binary-size runtime warning. This is a
current compact synthetic regression, not scientific validation of real files.
The additional ``test_fa_baseline.py`` checks -91/-93/-94 selected-failure versus
raw-inspection behavior without native packages, and exercises the upstream
probe on generated read-only data when the optional wheel is installed.
Existing tests cover exact-common/strict exclusion reports, no-FA NetCDF
coupling, isolated GRIB coexistence, synchronous/spawn exports, ordinary-reader
reopening and explicitly selected polar origin truth.

Final P0 verification (same Python-3.13 environment):

.. code-block:: bash

   python -m pytest -q src/frameit/testing/numerical/test_fa_baseline.py \
       src/frameit/testing/numerical/test_fa_io.py \
       src/frameit/testing/numerical/test_fa_geometry.py \
       src/frameit/testing/numerical/test_fa_pipeline.py
   python -m pytest -q
   ruff check src/frameit/testing/fa_native_probe.py \
       src/frameit/testing/numerical/test_fa_baseline.py
   frameit validate example/config_file/coupled_fa.yaml --schema-only
   LC_ALL=C LANG=C sphinx-build -q -W --keep-going -b html \
       docs/source /tmp/opencode/frameit-fa-p0-docs
   git diff --check

Focused suite: **21 passed**, one NumPy/netCDF binary-size warning. Full suite:
**508 passed, 2 subtests passed**, 722 cfgrib/xarray future warnings, 229.52 s.
Ruff and schema validation pass. The first strict documentation build found two
short title underlines, corrected before the final build. The strengthened
optional-import check was then rerun with ``python -m pytest -q
src/frameit/testing/numerical/test_fa_baseline.py``: **5 passed**.
No production run, large download, real-sample diagnostic or real-sample
physical-coordinate derivation was performed.
Existing YAML, output semantics and run provenance mechanisms are unchanged;
this manifest adds investigation provenance, not an automatic capability gate.

P1 can develop versioned descriptors on the proven synthetic/dense scalar
branch. Before promoting any real family, obtain its producer/release and native
build identity, authoritative types/scaling/units/time/sampling definitions,
independent decoded values/masks and geographic checkpoints with justified
tolerances. Obtain at least two times per real stream and explicit cycle/reset
examples for the AROME/SURFEX families being admitted.
For the -91 branch, obtain the native header/error specification and trusted
decode or upstream-supported resolution first. Typed/scalar metadata may inform
P1 contracts without admitting packed, spectral, 3-D, vector or interval
execution. Permission to retain/redistribute real reduced fixtures and human
review of scientific conventions remain open. No scientific approval is claimed.

P1 follow-up
-------------

The :doc:`fa_contracts` adds versioned descriptors and selected typed structural
metadata on the observed AROME-47/SURFEX-8.1 branch. It does not promote any
blocked physical family in this frozen P0 matrix. In particular, the -91,
release-matched scientific definitions, trusted decodes and multi-time real-data
gaps remain unresolved.

The :doc:`fa_geometry` records a subsequent bounded P2 repair of already admitted
modern regional headers and Lambert index lookup. Additional projections, Earth
models require references before new AROME/SURFEX variants are admitted.
Global/reduced active metadata belongs to a future, separately scoped reader.
