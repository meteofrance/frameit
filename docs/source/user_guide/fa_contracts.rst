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

The maintained native API exposes encoding flags but no qualified structured
multiplier/offset query. ``scaling.status: not_exposed`` with null multiplier/offset
records that gap. **Absence of a warning is neither verified scaling nor identity
scaling.** Source units and plausible ranges cannot establish a missing codec factor.

The native diagnostic ``has no encoded FMULTM and FMULTE`` triggers the missing-
scaling guard. Execution fails unless ``allow_unscaled: true`` was explicitly
declared. The researcher must justify that opt-in; the flag does not verify
physical scaling. Logs retain the warning and permission;
an actually observed permitted identity fallback is recorded as
``identity_explicit_opt_in``. Permission and observed fallback are different facts.
No definition tables or installed-package metadata are silently patched.

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
