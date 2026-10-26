FA P1 field contracts and evidence limits
=========================================

The P1 increment extends the existing worker/backend/loader boundary. Private
protocol version **1** and field descriptor schema version **1** describe selected
records without admitting new physical representations. The :doc:`fa_baseline`
family matrix remains the qualification boundary. Existing explicit
``input.fa.field_metadata`` declarations continue to work; no migration is needed.
Python 3.13, optional native dependencies and FA/GRIB process isolation remain
the reference runtime. EPyGrAM is not installed or imported by this path.

Descriptor and operation contract
---------------------------------

``io/fa_contracts.py`` builds ordinary JSON dictionaries. They contain:

* native identity, indexed word count, source tags and selected profile;
* native directory type/dimensions, encoding flags or native error;
* representation, evidenced storage shape and native-wrapper decoded dtype;
* sampling layout, physical location and vector basis (unknown when not evidenced);
* units, scaling status, support-mask label and observed undefined-value policy;
* header reference/valid/lead time separately from declared field temporal kind;
* semantic evidence origins and per-operation eligibility/conditions.

Unprobed encodings, physical units, on-disk types, spectral sizes, sampling bases,
support maps and field-specific time bounds stay unresolved. ``float64`` is the
existing wrapper's physical-array result type, not a claim about source packing
precision. A source directory type is retained verbatim. Native word count is
not used as a decoded spectral or physical shape.

``available`` inspection or typed ``metadata_decode`` does not imply physical
``decode`` eligibility. Structural metadata stays blocked for physical-array
decoding even after its selected typed value has been read. ``conditional``
capabilities still require admitted geometry, explicit scientific declarations,
the native scaling check and, for polar sampling, explicit selection and an
eligible method. ``blocked`` operations retain reasons. Spectral, packed SURFEX,
nonregional layouts, intervals and diagnostics do not become executable because
their metadata can be described. Unknown selected quantities need explicit
meaning; unknown unselected records remain in the index without payload reads.
Native -91/-93/-94 failures are not metadata classifications.

No file units, handles, locks or native objects enter Dask graphs or resolved
YAML. Lazy array descriptors copy their JSON facts/options at construction.
The backend rejects unknown protocol/descriptor versions, identity mismatches
and inconsistent decoded dtype/array transfers. Source size/mtime checks retain
their existing freshness meaning, not content-integrity proof.

Typed structural metadata: observed release only
-------------------------------------------------

The small definition ``arome-47-surfex-8.1-observed-v1`` requires native
``PROGRAM=AROME, VERSION=8, BUG=1, MASDEV=47, BUGFIX=0`` together. Missing or
different tags do not select this definition. It is an **observed structural
layout**, not an independently reviewed scientific field catalogue.

Selected private metadata reads support known ASCII character records, integer
scalars, integer directory-dimension arrays, 0/1 logical words, real scalars and
the mixed DTCUR date/seconds record. Reals are bit-reinterpreted from native LFI
words, not numerically cast; large integers are preserved exactly. Logical values
other than evidenced 0/1 fail. Nonfinite real metadata is tagged as
``{"nonfinite": "nan"}`` (or ``inf``/``-inf``), not changed to zero or emitted as
invalid JSON. Unsupported types, sizes, directory contradictions and unmatched
releases fail before the selected metadata read. This does not add arbitrary
typed physical arrays, packed masks, character-array products or a plain-LFI adapter.

Metadata values are read only when explicitly requested with ``metadata_fields``
on the private inspector. Header/index and the existing small SURFEX directory/
source/state metadata reads remain necessary for ordinary inventory. No
``wfacilo`` physical payload call is used for metadata-only inspection. Individual
typed reads are limited to 4096 words; required directory/header metadata reads
are bounded at 100000 words. These limits do not relax the physical-point budget.

For example, in a Python process using FrameIt's isolated backend:

.. code-block:: python

   from frameit.io.fa_backend import inspect_fa
   info = inspect_fa(
       "history.fa", None, metadata_fields=["SFX.PROGRAM", "SFX.PACK", "SFX.DTCUR"],
       expected_source={"PROGRAM": "AROME", "MASDEV": 47, "VERSION": 8, "BUG": 1, "BUGFIX": 0},
   )
   print(info["typed_metadata"])

The supplied SURFEX sample was checked again read-only on 2026-10-26 with these
release tags plus PACK/L1D/L2D/LAT0/DTCUR. Observations: PACK=false, L1D=false,
L2D=false, LAT0=-15, date 2026-10-21 with 43200 seconds. Size and mtime_ns remained
213098496 and 1792569892000000000. No physical field was decoded. These checks
support the structural interpretation only, not a scientific transformation or
qualification of every field in that release.

Precedence and explicit source assertions
-----------------------------------------

Precedence is **native facts, then release-matched documented conventions, then
user completion of unresolved meaning**. A user declaration may not overwrite
known units/time semantics; a mismatch fails instead of relabelling/converting.
The origin of native facts is retained even when a user repeats the same value.
This precedence is exercised with independently specified contradictory facts.
No release-qualified physical convention currently supplies missing units,
sampling or intervals, so every selected physical record still requires its
explicit ``field_metadata``. Declarations are recorded as user evidence, not
independent scientific validation. There is no name-based unit/quantity inference.

Optional ``input.fa.expected_source`` accepts exact native assertions for
``PROGRAM``, ``VERSION``, ``BUG``, ``MASDEV`` and ``BUGFIX``. It defaults to an
empty mapping, preserving existing YAML behavior. It is resolved independently
for each named source and retained in resolved YAML, preflight and run provenance.
Missing native values and unequal values fail even in metadata inventory; the
mapping neither overrides native metadata nor supplies a producer identity.
The observed typed-layout selection is separate from this user assertion.
Physical fields on other releases retain the existing narrow explicit-declaration
path; no matched layout or scientific approval is implied for those sources.

Scaling and codec definition boundary
--------------------------------------

The installed ``falfilfa4py==1.3.0`` FA wrapper exposes FANION encoding flags and
FACILO undefined-value metadata, but **no structured multiplier/offset query**.
``scaling.status=not_exposed`` and null multiplier/offset explicitly record this
gap. Absence of a warning is neither verified scaling nor inferred identity.
The existing missing-FMULTM/FMULTE diagnostic-text guard remains in force.
Missing scaling fails unless ``allow_unscaled: true`` was explicitly declared;
warnings are retained and actual opt-in fallback observations are recorded as
``identity_explicit_opt_in``. Permission and observed fallback are separate facts.
Synthetic packing-0 fixtures do not emit that GRIB-scaling warning; failure and
fallback logging are also tested with explicit diagnostic injection.

Scientific labels are not codec definitions. No native definition tables are
added, no installed files are edited, and no custom-table configuration is
introduced without a version-matched reference/value corpus. Helpers continue
using wheel MEMFS tables and exclude parent ecCodes definition/sample overrides.
Parent GRIB settings remain unchanged. A future table integration requires the
P0 upstream facts and independently verified decoded values first.

Provenance and ordinary outputs
-------------------------------

Preflight and ``fa_inputs`` retain per-file ``protocol_version``,
``field_descriptors``, ``expected_source`` and source version tags. Decoder logs
retain per-request descriptors with actual native undefined flags/sentinels and
scaling evidence. ``fa_decoder.field_observations`` summarizes the last observed
descriptor per source basename/record in that source's log; the JSONL logs retain
every attempt. It is not an archive checksum or statistical mask summary.

NetCDF variable attributes add a JSON ``fa_field_descriptor`` and an explicit
``fa_field_descriptor_scope``. This is a **representative input-record snapshot**,
not a combined multi-time description or the output crop's dimensions. Full
per-file clocks/encoding and post-read facts are in run provenance/decoder logs;
ordinary output time coordinates retain their existing meaning. Unread native
undefined flags remain ``not_read`` in that inspection snapshot. Existing product
names, values, dimensions, masks, unit declarations, compression and atomic
publication remain unchanged. No new reader dependency is required.

Evidence, qualification and remaining gates
-------------------------------------------

Independent compact tests specify raw integer/IEEE/ASCII words, large integers,
logical values and date/seconds truth. They test typed-directory contradictions,
unknown selected/unselected records, source assertions, protocol serialization,
optional imports and a metadata-only child with physical readers forbidden.
Coupled synchronous/spawn tests reopen NetCDF with an ordinary reader and check
new attributes, per-file provenance, scaling observations and resolved YAML.
The existing no-FA NetCDF, GRIB coexistence, exact-common/strict, native extraction
and explicitly selected bilinear polar tests remain in the regression suite.

References checked for this increment:

* Installed ``falfilfa4py`` 1.3.0 ``LFI.py``: ``wlfilec`` returns integer-word
  arrays; ``FA.py`` documents FANION flags and FACILO undefined data. Its SHA256
  and runtime identities are retained in the P0 manifest.
* The producer-authored ``SFXFLDDESC_MOD`` (Philippe Marguinaud, Météo-France)
  `49T1 table hosted by UMR-CNRM
  <https://github.com/UMR-CNRM/EPyGrAM/blob/develop/src/epygram/data/sfxflddesc_mod.F90-49T1>`_,
  Git blob ``785b1036112bbe2aebdd680d793532ee2ce4bcbf``. This is a different
  release from the supplied MASDEV=47 source and is **not applied** as a matched
  physical catalogue. No EPyGrAM implementation or data table was copied.
* P0 corpus and generated fixtures: observed 47/8.1 source/directory/raw metadata
  evidence, not a replacement for authoritative release-specific byte/physical
  specifications or human scientific review.

Native upstream source remains inaccessible (HTTP 404), and attempted official
SURFEX-8.1 source/browser URLs were unreachable. **Release-matched physical
definitions and structured native scaling remain blocked**: request the
producer's exact 47/8.1 field/byte-layout specification, native library revision,
matched codec definitions and trusted values/masks/time/sampling references.
Unknown logical encodings, other typed layouts and releases remain gated.
The P0 -91, spectral, packed, native 3-D/vector and interval gaps remain required
work, not silently excluded qualifications. No scientific sign-off is claimed.

P2 prerequisites are authoritative active header/projection mappings, actual
Earth models, grid anchors/scanning/zone conventions and independent geographic
checkpoints for each added header family. No P1 descriptor permits guessed grid
identity or relaxes anisotropy/nonuniformity checks. Independent work may continue
on the proven regional scalar branch while blocked families await their evidence.

P1 verification record
-----------------------

Starting revision was ``b5fd38878fa8a6c1dd85adb005c053807a976d01``, clean.
Commands in the Python-3.13.16 reference environment (prefix
``conda run -n frameit_env``):

.. code-block:: bash

   python -m pytest -q src/frameit/testing/numerical/test_fa_contracts.py \
       src/frameit/testing/numerical/test_fa_io.py \
       src/frameit/testing/numerical/test_fa_pipeline.py \
       src/frameit/testing/numerical/test_fa_baseline.py \
       src/frameit/testing/numerical/test_fa_geometry.py
   python -m pytest -q
   ruff check src/frameit/io/fa_contracts.py src/frameit/io/fa_worker.py \
       src/frameit/io/fa_backend.py src/frameit/io/fa_utils.py \
       src/frameit/core/configuration.py src/frameit/core/coupled.py \
       src/frameit/core/preflight.py src/frameit/testing/fa_fixture.py \
       src/frameit/testing/numerical/test_fa_io.py \
       src/frameit/testing/numerical/test_fa_contracts.py \
       src/frameit/testing/numerical/test_fa_pipeline.py
   frameit validate example/config_file/coupled_fa.yaml --schema-only
   LC_ALL=C LANG=C sphinx-build -q -W --keep-going -b html \
       docs/source /tmp/opencode/frameit-fa-p1-docs
   git diff --check

Observed results: final native-focused suite **28 passed**, one NumPy/netCDF
binary-size runtime warning; full suite **515 passed, 2 subtests passed**,
722 cfgrib/xarray future warnings, 233.71 seconds. Ruff, schema validation and
strict Sphinx build passed. Final native admission-guard changes were rechecked
with the focused suite after the full regression.

A separate Python-3.13.16 environment with **no falfilfa4py installed** also ran:

.. code-block:: bash

   python -m pytest -q src/frameit/testing/numerical/test_fa_contracts.py \
       src/frameit/testing/numerical/test_fa_baseline.py \
       src/frameit/testing/numerical/test_fa_pipeline.py::test_coupled_netcdf_sources_do_not_need_fa_backend

Result: **11 passed, 2 skipped** (only the two native fixture cases). GRIB was
installed in that environment; this is not claimed as a no-GRIB environment run.
The native and no-FA CI jobs both include the new contract tests. No large run,
download or private-data upload was performed, and no real-data scientific
qualification is inferred from these tests.
