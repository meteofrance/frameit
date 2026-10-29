FA metadata and provenance
==========================

Inspection and outputs distinguish **native observations, explicit declarations
and unresolved scientific meaning**. Use :doc:`fa_inputs` to select records and
:doc:`fa_baseline` to check whether the requested operation is supported.
Metadata readability is not physical decode eligibility.

What a field descriptor means
-----------------------------

Version-1 field descriptors are portable JSON facts carried through inspection,
preflight, decode logs and representative NetCDF variable attributes. They retain:

* ``native_id``, indexed word count, source/profile and exact producer tags;
* directory type/dimensions/support label and selected encoding flags or native error;
* representation, evidenced storage shape and decoded dtype;
* sampling location/basis and native vertical-header facts, with unresolved values
  left explicit rather than inferred from a name;
* units and their origin, scaling status, declared fallback permission and observations;
* masks/undefined-value observations, separate from physical support and valid zeroes;
* reference/valid/lead clocks separately from field temporal kind/bounds;
* semantic evidence origins and per-operation ``eligibility`` with reasons/conditions.

``float64`` describes the maintained reader's physical-array result, not on-disk
packing precision or output storage precision. Native word count is not a decoded
physical/spectral shape. Unprobed encodings, units, coefficient counts, support
maps, vector bases and field-specific intervals remain unresolved unless supported
by the selected contract.

``available`` inspection or typed ``metadata_decode`` does not imply physical
``decode``. ``conditional`` dataset/extraction/polar eligibility still requires
admitted geometry, explicit field meaning, the decode-time scaling check and an
explicit eligible polar selection/method. ``blocked`` operations retain reasons.
Selected -91/-93/-94 errors remain failures, not metadata classifications.
Unknown unselected fields remain indexable without physical payload reads.

Declarations and exact source assertions
----------------------------------------

Precedence is **native facts, then release-matched documented conventions, then
user completion of unresolved meaning**. A declaration cannot overwrite known
units/time semantics; contradictions fail rather than relabelling/converting.
Repeating a native fact does not replace its native evidence origin.

No release-qualified physical catalogue currently fills missing units, sampling
or intervals. Every selected physical record or logical cube therefore needs
``input.fa.field_metadata`` with source ``units``, ``kind`` and
``temporal_kind: instantaneous``. Declarations are user evidence, not independent
scientific validation. There is no filename/record-name inference of quantity or units.

Optional ``input.fa.expected_source`` defaults to ``{}`` and accepts exact native
assertions for ``PROGRAM``, ``VERSION``, ``BUG``, ``MASDEV`` and ``BUGFIX``. Missing
or unequal values fail even in metadata inventory. Each named source resolves
independently; assertions are retained in resolved YAML, preflight and provenance.
They neither supply missing producer identity nor override native facts, and are
separate from the supported-layout check.

Structural types are not scientific fields
--------------------------------------------

The observed layout identifier ``arome-47-surfex-8.1-observed-v1`` requires
``PROGRAM=AROME, VERSION=8, BUG=1, MASDEV=47, BUGFIX=0`` together. It describes
evidenced structure, not an independently reviewed physical-field catalogue.
SURFEX physical execution also requires complete, consistent source/FBUF records,
dense ``PACK=0/X1`` dimensions and matching state/header clocks.

Native structural types include ASCII character ``C0``, integer ``N0``/directory
``N1`` words, 0/1 logical ``L0``, real ``X0`` and the mixed date/IEEE-seconds
``T0`` state record. These are actual native type codes. Large integer words are
retained exactly; non-0/1 logical encodings fail. Nonfinite real metadata uses
JSON tags such as ``{"nonfinite": "nan"}`` or ``inf``/``-inf``, not physical
zeroes or invalid JSON numbers. Unsupported types, lengths, contradictory
directories or unmatched releases fail before selected typed reads.

Required inventory/source/directory/clock reads do not decode horizontal physical
arrays. Optional selected typed reads are bounded to 4096 words; required
structural columns/header reads are bounded to 100000 words, and the inventory
to 100000 records. These internal limits do not relax ``input.fa.max_points``.
No arbitrary typed physical arrays, character-array products, packed support maps
or plain-LFI adapter follow from structural readability.

The producer-authored ``SFXFLDDESC_MOD`` (Philippe Marguinaud, Météo-France),
`49T1 table hosted by UMR-CNRM
<https://github.com/UMR-CNRM/EPyGrAM/blob/develop/src/epygram/data/sfxflddesc_mod.F90-49T1>`_,
is a different release from MASDEV=47. It is not applied as a matched physical
catalogue. Library tables/defaults cannot fill release-matched byte, field,
scaling or sampling evidence gaps. No EPyGrAM implementation/table is vendored.

Vertical facts versus explicit cube associations
------------------------------------------------

``sampling.native_vertical_header`` retains ``KNIVER``, ``PREFER``, ``PAHYBR``
and ``PBHYBR``, including on surface records sharing that header. Without an
explicit association, ``sampling.vertical_interpretation`` remains unqualified:
the header alone does not define each record's full/interface location, units,
physical coordinate or vector basis, and creates no inferred vertical/layer axis.

For selected atmospheric cubes, native labels and interface A/B/reference pressure
are checked against the library; ``sampling.native_cube`` records the explicit
user association and its evidence origin. A header-wide library ``mass`` default
is not independent per-field sampling proof. Original records/indices survive
selection; see :doc:`fa_atmosphere`. No pressure/height or full-level mean is
diagnosed by retaining coefficients.

Scaling and masks after decoding
--------------------------------

For gridpoint packing **120**, the worker observes explicitly encoded FA factors
in the embedded GRIB2 centre-85 local-section-1 message. It reads the selected
encoded record through the same open FA unit and inspects metadata with the
worker's bundled ecCodes C library; no Python GRIB runtime or second physical
decoder is loaded. EPyGrAM remains the sole physical decoder. The extra encoded
record read is bounded to ``2 * max_points + 4096`` words and released before
physical decoding; it adds I/O and temporary memory, not a full-archive scan.

``scaling.status: encoded`` records the native mantissa/exponent, their
``divisor = FMULTM * 10**FMULTE`` and effective ``multiplier = 1 / divisor`` with
zero offset and ``fallback: null``. **The native decoder has already applied this
factor; do not apply it again to outputs.** Byte offsets and values must agree
with actual encoded sign-magnitude integers: transient/default keys are not
accepted as encoded evidence. Zero, underflowing or nonfinite factors fail even
with ``allow_unscaled: true``. Units/time/support still need their declarations.

The native diagnostic ``has no encoded FMULTM and FMULTE`` can occur even when
these factors are present. The published CNRM implementation emits it for an
unknown parameter number (255), separately from reading the factors. Encoded
observations therefore take precedence over this warning, which remains logged.
If factors cannot be observed, the warning still fails execution by default.
An explicitly justified ``allow_unscaled: true`` retains the legacy unverified
``identity_explicit_opt_in`` fallback; it does not establish physical scaling.
Other encodings retain ``not_exposed`` when no warning is emitted: absence of a
warning is not proof of identity scaling. No installed definitions are patched.

Codec evidence and verification scope:

* `CNRM FADGRA source, lines 172--181 and 234--236
  <https://www.umr-cnrm.fr/surfex/data/BROWSER/doc_surf81/fadgra_8F90_source.html>`_
  reads the divisor and divides unpacked values; the corresponding
  `FACGRM writer, lines 242--244 and 701--711
  <https://www.umr-cnrm.fr/surfex/data/BROWSER/doc_surf81/facgrm_8F90_source.html>`_
  multiplies before packing. These published XRD44 sources explain the convention,
  not the exact build identity of every producer or installed wheel.
* `ecCodes 2.44.0 local.85.1 definition
  <https://github.com/ecmwf/eccodes/blob/2.44.0/definitions/grib2/local.85.1.def>`_
  defines the two eight-octet signed factors with identity defaults. This adapter
  accepts observed encoded values, not those defaults by assumption.
* Compact fixtures independently change encoded factor bytes without changing
  packed samples. Checks compare native output to known scalars divided by the
  factor, within one 24-bit packing step rescaled by that divisor, including
  missing samples and valid zeroes. Missing sections and invalid factors fail.
  This is codec engineering verification, not universal physical validation.

SURFEX ``SFX.PACK=0`` describes the dense support layout, not the scaling of each
FA record. A dense ``X1`` field can still have native packing 120 and trigger
this guard. Metadata inspection/preflight does not decode its physical payload,
so successful inspection does not establish that extraction/export will pass.

``mask.undefined`` identifies the EPyGrAM returned mask and normalized NaN
sentinel; its field object does not expose the original native flag/sentinel.
An IEEE NaN need not have a returned mask bit. ``mask.nonfinite_count`` counts
full-native nonfinite values after normalization, **before cropping**. It is not
the output mask, a support map or an archive-wide statistic. FULL/SEA/NATURE
labels, actual missing samples, extension zones and valid physical zeroes remain
distinct. Unsupported support-map reconstruction is not replaced by guessed zeros.

Helpers retain their own definition/sample policy and exclude inherited parent
GRIB overrides only in the child. Custom FA definition-table loading is not an
adapter option. Native decoder/producer revision, matched definitions and trusted
values/masks are needed to resolve scaling uncertainty; see :doc:`fa_environment`.

Read the recorded provenance
----------------------------

Per-file preflight and ``fa_inputs`` retain descriptors, ``expected_source``,
producer/version tags, clocks, geometry and actual backend versions.
``geometry_contract`` records library axes/CRS/native zones, origin translation
and Earth-model evidence; ``horizontal_header_signature`` is a library-derived
JSON signature, not a vertical, quantity or content-checksum contract.

``backend`` and ``backend_versions.FA_backend`` identify effective ``epygram``;
``requested_backend`` / ``FA_backend_requested`` retain the request and
``FA_backend_migration`` reports the deprecated ``native`` alias. The same
scientific/source/resource checks apply to both requests. Parent GRIB versions
and worker-native versions are separate observations.

Decoder JSONL logs retain individual requests and post-read mask/scaling facts.
``fa_decoder.field_observations`` summarizes the last descriptor per source
basename/record; ``payload_reads`` records the actual library/accessor/resource
class/read-only mode after a selected payload call. A successful accessor call
is not scaling approval: the scaling guard can fail afterward. Summaries are not
content hashes or combined multi-time/mask statistics.

NetCDF variables carry JSON ``fa_field_descriptor`` and an explicit
``fa_field_descriptor_scope``: a **representative input-record snapshot**, not
the crop's dimensions, a post-read descriptor or a combined multi-time history.
Unread undefined observations remain ``not_read`` there. Per-file clocks,
encoding and actual decode facts belong to provenance/logs. For an exported FA
variable, ordinary Python readers can inspect it without FrameIt:

.. code-block:: python

   import json
   import xarray as xr

   with xr.open_dataset("products/SIMU.cart.surfex.surface.nc", engine="netcdf4") as ds:
       descriptor = json.loads(ds["SFX.T2M"].attrs["fa_field_descriptor"])
       print(descriptor["units"], descriptor["scaling"], descriptor["sampling"])
       print(ds["SFX.T2M"].attrs["fa_field_descriptor_scope"])

Adapt the path/field to the product inventory. Source size/mtime checks mean
freshness, not checksum/corruption verification. Per-product atomic publication
does not make a multi-product transaction; inspect final status and incomplete
steps as described in :doc:`output_files`.

Independent compact references cover integer/IEEE/ASCII words, large integers,
clocks, selected/unselected failures, contradictory declarations, masks/zeroes
and ordinary-reader exports. They do not replace release-matched physical
definitions, independent real data or scientific review. Unknown layouts/types,
unresolved native errors, scaling, intervals and spectral/vector/vertical
conventions retain the limitations in :doc:`fa_baseline`.
