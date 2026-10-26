Native FA and coupled sources
========================================

FrameIt can extract selected instantaneous 2-D gridpoint records from native
AROME and AROME-produced SURFEX FA histories. It can also process these alongside
atmospheric GRIB or NetCDF inputs in one run, using one geographical track and
each source's own grid. This is a limited input adapter, not a complete FA
diagnostic catalogue or qualification of every producer's scientific fields.
The active implementation phase is specifically **AROME atmospheric FA plus
AROME-produced SURFEX FA**, with the existing AROME GRIB atmospheric route
preserved. Other producer/native-container integrations are outside this phase.

Installation and native isolation
----------------------------------------

The reference ``environment.yaml`` uses Python 3.13 and installs the published
``falfilfa4py==1.3.0`` wheel. A minimal installation may use the optional ``fa``
extra on a platform/Python version supported by that package. EPyGrAM is not
required. Ordinary NetCDF/GRIB processing and schema-only validation do not
require the FA package.

The published wheel bundles an ecCodes runtime that cannot reliably coexist
with the conda Python GRIB runtime in one interpreter. FrameIt therefore runs
native FA metadata/decode transactions in fresh helper processes. These helpers
never import Python ecCodes. The parent performs scientific preparation,
tracking, extraction and export as usual. No wheel patch, global library-path
change or full-archive conversion is needed.

Helpers use one native thread and one serialized request at a time per consuming
process. They use their bundled definition/sample tables: inherited parent
``ECCODES_DEFINITION_PATH`` and ``ECCODES_SAMPLES_PATH`` overrides are excluded
only in the helper. The policy and child versions are recorded. Custom FA
definition-table loading is not currently an adapter option.

Inspect first
-------------

.. code-block:: bash

   frameit inspect ./data --model arome --format fa --pattern "historic.surfex*.fa"
   frameit inspect ./data --model arome --format fa --pattern "historic.surfex*.fa" \
       --fa-profile surfex_history --fa-fields SFX.T2M SFX.SST

Inspection returns native headers, record names/lengths, backend versions and
SURFEX typed field-directory metadata. Optional field probes report encoding
flags or native errors without decoding data. Raw inspection does not select
units or infer an Earth model. An atmospheric record rejected with native error
-91 is not automatically treated as harmless metadata.

The :doc:`fa_baseline` records the current P0 corpus, finite family/operation
matrix, native -91 reproducer, missing references and P1 admission gates.
The :doc:`fa_contracts` describes the P1 private descriptors, typed structural
metadata, optional exact source-version assertions and declaration precedence.
The :doc:`fa_geometry` records the P2 native-axis lookup repair, numerical
compatibility change, snapping metadata and remaining geometry gates.
The :doc:`fa_surface` records the P3 shared atmosphere/surface polar contract,
selected dense/layer-name tests, cyclone-field priorities and remaining blockers.
The :doc:`fa_spectral` records the P4 optional ecTrans candidate evaluation,
independent Fourier modes and the still-blocked native spectral admission gates.

Use ``input.format: fa`` for FA-only extraction or named sources for coupling.
Do not put atmospheric and SURFEX companion files into an undifferentiated FA
inventory: they are complementary streams, not duplicate observations.

Named-source configuration
--------------------------

Adapt the paths, geometry, centres and scientific declarations to the simulation:

.. literalinclude:: ../../../example/config_file/coupled_fa.yaml
   :language: yaml

With ``input.sources``:

* Each source owns its ``model``, ``input``, ``variables`` and optional ``polar``
  settings. Discovery/exclusion/NetCDF/wind conventions are the same as ordinary
  inputs. Relative paths use the parent YAML's directory.
* Top-level ``model`` must match ``tracking.source``'s model. Current FA profiles
  require ``model: arome``. This phase's atmospheric and SURFEX sources both use
  the actual AROME producer conventions.
* ``tracking.source`` chooses the existing tracker and atmospheric requirements.
  It must name a configured source. FA itself currently supports ``fixed_box`` or
  ``prescribed_track`` tracking; use GRIB/NetCDF for other atmospheric methods.
* Put variables inside each source; top-level ``variables`` must be empty and
  top-level ``polar.variables`` must remain ``all``. Each source may override
  its own polar selection/options.
* Global domain, export, logging and execution settings are shared. Native grids,
  coordinates, masks and units are not merged or silently regridded.

For an atmospheric NetCDF source, use its actual model conventions, an explicit
inventory/pattern, ``format: netcdf`` and ordinary ``input.netcdf`` settings inside
that source. AROME NetCDF must already follow the adapter's time/coordinate
conventions; a matching file format does not establish schema compatibility.
Its configured ``valid_time`` dimension is normalized to internal ``time``
without changing timestamps. Conflicting ``time``/``valid_time`` names fail
instead of guessing whether one is a forecast reference clock.

Time choice: common or strict
-----------------------------

``input.time_alignment: common`` is the coupled default: use the **exact
intersection of valid timestamps** from all sources. A prescribed track further
restricts processing to its exact matching times.

Every source losing timestamps produces a warning with source ID, count and a
timestamp preview. The complete ``time_alignment`` report is saved in
``run-provenance.yaml`` and ``run-status.yaml``:

* selected timestamps and available/selected counts per source;
* all skipped timestamps and wholly skipped files;
* times present in other sources but missing from this source.

``strict`` requires identical source timestamp sets and prescribed-track coverage
of them; otherwise the run fails. Extra track points outside the simulation
period do not create model times. Empty intersections, missing/invalid dates,
unsupported calendars, ambiguous forecast cycles and inconsistent SURFEX
state/header clocks fail actionably. Coupling requires Gregorian datetime
coordinates within 1678--2261, one cycle per selected source, and matching
reference cycles wherever multiple sources supply them.

No nearest-time match, temporal interpolation, fill, automatic deaccumulation or
implicit interval conversion is performed. Duplicate first/last policy applies
within a stream, not across companion sources. A permitted intersection completes
the selected plan; structural tracking loss retains its separate incomplete status.

Grids, centres and products
---------------------------

The atmospheric source supplies geographical centres. Each secondary source maps
them onto its own static regional grid using the documented geometric lookup.
Atmospheric ``cx``/``cy`` indices are never reused on another grid. A centre
outside a required secondary footprint fails: no edge-point substitution or
spatial time skipping. Boxes partly outside a grid keep existing NaN padding.

Coupled products use source-qualified groups:

.. code-block:: text

   products/coupled-surface.track.nc
   products/coupled-surface.cart.atmosphere.heightAboveGround.nc
   products/coupled-surface.cart.surfex.surface.nc

Original track indices belong to ``tracking.source``. Additional ``<source>_cx``,
``<source>_cy``, bounds and validity variables describe each source grid. Products
record ``source_id``, ``source_model``, ``source_format`` and ``source_group``. FA
variables retain native names, declarations, source indices, masks, packing and
producer metadata. Existing single-source naming/defaults are preserved.

Polar sampling stays optional. ``polar.shared_target: true`` opts into one target
for participating sources: common exact times, continuous centres, radius/azimuth
and ellipsoid, with exact output-coordinate verification. Explicit radial steps
must agree and be no finer than the coarsest source; otherwise this mode resolves
the coarsest participating native spacing and records that choice. With the
default ``false``, per-source sampling remains independently configurable.
Categorical FA fields selected for polar sampling require ``nearest_s2d``;
different methods are not silently assigned to individual fields. Point sampling
is not conservation or area averaging.

FA definitions, domain and limits
----------------------------------------

Profiles are ``arome_history`` and ``surfex_history``. The latter reads
AROME-produced SURFEX ``SFX.PACK=0`` histories with horizontal ``X1`` entries
matching the full storage grid. Layer/patch/tile record names and mask labels are
retained, not averaged or assembled into an invented vertical coordinate. Use
the logical ``surface`` group for individually selected 2-D records; this does
not label every quantity as a physical ground-surface variable.

Each selected native record requires ``field_metadata``:

* ``units``: actual decoded source units, not a requested conversion;
* ``kind``: ``continuous`` or ``categorical``;
* ``temporal_kind: instantaneous``: currently the only admitted temporal meaning;
* optional descriptive ``long_name`` and correct ``standard_name``;
* optional ``allow_unscaled: true``: explicit permission for identity fallback
  when native registered and encoded scaling factors are both missing. Default
  false: uncertainty discovered during decoding fails the operation.

Fallback warnings are logged and summarized in provenance, including spawned
exporter requests. Permission is not scientific validation. File-level start
markers do not establish every field's interval. Accumulated/averaged FA records,
automatic unit inference, spectral transforms, global/reduced grids, plain LFI
and arbitrary producer conventions are not currently supported.

Geometry supports modern regular lon/lat and spherical tangent-Lambert headers.
Projected inputs require explicit ``earth_radius_m``. ``subdomain: CI`` (default)
keeps central plus intermediate points; ``C`` excludes the declared I-zone widths.
The spectral extension zone is excluded. Shape/zone indices, angles, radius and
CRS are retained; there is no fitting or guessed Earth-shape default.
Dateline-crossing/polar FA grids and unsupported projections fail explicitly.
Existing spacing/anisotropy checks still apply.

``input.fa.max_points`` defaults to 20,000,000 stored points and
``timeout_seconds`` to 120 per transaction. Raise budgets explicitly after
inspection. Decoding can require a full horizontal record even for a tiny crop,
plus coordinate/temporary arrays. Laziness avoids unselected records/times but
does not promise NetCDF-style subrecord I/O. Short-lived helper startup has a
real cost; no throughput improvement is claimed.

Provenance and failure
----------------------

Run provenance records inventories, geometry, units, winds, time alignment,
FA declarations/encoding and child-native versions separately from the parent
ecCodes version. Diagnostics are retained in ``logs/fa-decoder-*.jsonl`` and
summarized after exporters complete. Size/mtime freshness is not checksum proof.
Per-file versioned field descriptors retain unresolved facts explicitly. Decode
logs and ``fa_decoder.field_observations`` add observed undefined-value and
scaling-warning/fallback facts. A representative input descriptor is also stored
as a JSON variable attribute; it does not replace per-file run provenance.

Existing atomic publication, exclusive run ownership and final ``run-status.yaml``
handle helper/export failures. Failed required sources never publish a completed
run status. Atomicity is per product, not a multi-product transaction or an fsync
durability guarantee.

.. _fa-geometry-method:

Geometry method and verification record
---------------------------------------

**Status:** implemented for the limited headers above; no independent scientific
sign-off is claimed for arbitrary real producers or field meanings.

**Basis:** standard spherical Lambert conformal conic equations in John P. Snyder
(1987), *Map projections: A working manual*, USGS Professional Paper 1395,
`doi:10.3133/pp1395 <https://doi.org/10.3133/pp1395>`_. The authoritative USGS
record describes established Lambert conformal mapping use. Header interpretation
also uses the native ``wfacies`` API and observed modern conventions; binary I/O
is not presented as a peer-reviewed scientific diagnostic.

**Inputs/conventions:** modern ``PSINLA`` radians, positive projected spacing in
metres, one-based inclusive ``KNLOPA`` CI bounds, explicit radius and CI-centre
geographical anchor. Only active header entries define geometry; unused work
buffers can contain NaNs/unrelated tails. Tangent-cone magnitude must match its
reference latitude. Regular lon/lat uses native centre and angular increments.

**Equations/numerics:** pyproj constructs the corresponding CF/PROJ CRS. With
tangent latitude :math:`\phi_0`, :math:`n=\sin\phi_0`,
:math:`F=\cos\phi_0\tan(\pi/4+\phi_0/2)^n/n`, and
:math:`\rho=RF/\tan(\pi/4+\phi/2)^n`; inverse equations retain the signed southern
cone. Native offsets locate the CI centre; C selection changes slices, not the
anchor. Geometry construction never interpolates physical fields.

**Independent checks:** asymmetric geometry is checked against separately
evaluated spherical equations in ``test_fa_geometry.py`` (absolute tolerance
:math:`2\times10^{-11}` degrees). Reconstructed CI corners must match encoded
corners within :math:`2\times10^{-5}` degrees, allowing rounded header angles;
this threshold does not permit fitting another CRS. The supplied 1300-metre
history also agrees with its encoded corners under an explicit inspection
radius; that is not independent proof of the producer's Earth model.

**Sampling/exclusions:** P2 uses source-CRS/native-axis point selection on the
admitted FA Lambert branch, after checking every geographic sample against its
axes/CRS. Other inputs, including regular lon/lat FA, retain squared-degree
selection. Both conventions handle equivalent longitudes and neither claims a
geodesic-distance minimum. Requested centres, selected points and projected
snapping offsets are distinguished; see :doc:`fa_geometry`. Grids, zones, masks,
units and intervals remain distinct.

**Scope/gaps:** generated fixtures verify known values, typed metadata, dates,
readonly bytes, native isolation, multiple times, distinct-grid crops, optional
polar targets, failure handling and ordinary-reader reopening. Physical field/
scaling assumptions still need producer documentation. Spectral records and native
-91 failures need upstream investigation and separate qualification.
