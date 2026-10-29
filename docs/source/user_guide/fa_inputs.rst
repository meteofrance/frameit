Native FA and coupled sources
========================================

FrameIt can extract selected instantaneous 2-D gridpoint records from native
AROME and AROME-produced SURFEX FA histories. It can also process these alongside
atmospheric GRIB or NetCDF inputs in one run, using one geographical track and
each source's own grid. This is a limited input adapter, not a complete FA
diagnostic catalogue or qualification of every producer's scientific fields.
The maintained reader is **EPyGrAM 2.1.0**. The primary coupled workflow is
AROME GRIB plus dense AROME-47 / SURFEX-8.1 FA histories. Compact generated fields
exercise the multi-time engine, separate grids, moving centres and exports;
they do not establish real-producer units, scaling, physical support or scientific
approval. Explicit native atmospheric cubes are also supported under the
record/vertical contracts described below.

Installation and native isolation
----------------------------------------

The reference ``environment.yaml`` installs FrameIt and the FA/GRIB/NetCDF/polar
stack in one Python-3.13 environment. FA workers use the active Python in fresh
isolated processes; omit ``input.fa.python_executable`` or leave it null.
An explicit override selects a separate coherent runtime containing FrameIt and
the FA stack. ``fa`` is the optional reader extra; ``fa-epygram`` is an identical
installation alias. See :doc:`FA environment and troubleshooting <fa_environment>`
for installation, interpreter selection and fresh-environment migration.
``backend: epygram`` is the default for all FA operations. Legacy ``backend: native``
remains accepted as a deprecated, warned alias with requested/effective provenance.
It selects the same reader and cannot bypass admission checks; see
:doc:`configuration_file` for the settings and migration contract.
Ordinary NetCDF/GRIB processing and schema-only validation do not
require the FA package.

The native FA dependency bundles an ecCodes runtime that cannot reliably coexist
with the conda Python GRIB runtime in one interpreter. FrameIt therefore runs
native FA metadata/decode transactions in fresh helper processes. These helpers
never import Python ecCodes. The parent performs scientific preparation,
tracking, extraction and export as usual. No wheel patch, global library-path
change or full-archive conversion is needed.

Helpers use one native thread and one serialized request at a time per consuming
process. They use their bundled definition/sample tables: inherited parent
``ECCODES_DEFINITION_PATH`` and ``ECCODES_SAMPLES_PATH`` overrides are excluded
only in the helper. The policy and child versions are recorded. Custom FA
definition-table loading is not currently an adapter option. A single installation
does not remove this format-specific process boundary.

Inspect first
-------------

.. code-block:: bash

   frameit inspect ./data --model arome --format fa --pattern "historic.surfex*.fa"
   frameit inspect ./data --model arome --format fa --pattern "historic.surfex*.fa" \
       --fa-profile surfex_history --fa-backend epygram --fa-fields SFX.T2M SFX.SST
   # Add --fa-python /path/to/helper/bin/python for a separate environment.

Inspection returns native headers, record names/lengths, backend versions and
SURFEX typed field-directory metadata. Optional field probes report encoding
flags or native errors without decoding data. Raw inspection does not select
units or infer an Earth model. An atmospheric record rejected with native error
-91 is not automatically treated as harmless metadata.

Continue with the topic relevant to your request:

* :doc:`FA metadata and provenance <fa_contracts>`: native facts, unresolved meaning,
  source assertions, declarations, masks and scaling observations.
* :doc:`FA geometry and centres <fa_geometry>`: native axes, Earth model, zones,
  requested/selected locations and snapping conventions.
* :doc:`Coupled atmosphere/surface sampling <fa_surface>`: independent products,
  shared targets, field distinctions and limits.
* :doc:`Native atmospheric levels and cubes <fa_atmosphere>`: exact record
  associations, full/interface indices and hybrid coefficients, without implicit
  pressure/height diagnosis.
* :doc:`Spectral support and limitations <fa_spectral>`: why coefficients cannot
  be decoded or exported as gridpoint values without a qualified native contract.

Use ``input.format: fa`` for FA-only extraction or named sources for coupling.
Do not put atmospheric and SURFEX companion files into an undifferentiated FA
inventory: they are complementary streams, not duplicate observations.

Named-source configuration
--------------------------

Adapt the paths, geometry, centres and scientific declarations to the simulation:

.. literalinclude:: ../../../example/config_file/coupled_fa.yaml
   :language: yaml
   :start-at: schema_version:

With ``input.sources``:

* Each source owns its ``model``, ``input``, ``variables`` and optional ``polar``
  settings. Discovery/exclusion/NetCDF/wind conventions are the same as ordinary
  inputs. Relative paths use the parent YAML's directory.
* Top-level ``model`` must match ``tracking.source``'s model. Current FA profiles
  require ``model: arome``; this does not make a different producer's FA compatible.
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

The cyclone example additionally separates ``atmosphere.surface`` and
``atmosphere.isobaricInhPa`` products. It declares each selected wind pair, preserves
native Cartesian winds and explicitly selects scalar polar fields. Geopotential
``z`` is not geometric height; selecting it does not diagnose height or pressure.

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
is not conservation or area averaging. Continuous production sampling defaults
to bilinear; conservative/patch/vector-transport experiments are not selected
automatically. Fields retain their independent missing/physical-support masks;
support labels, native undefined values, extension zones and real zeroes are
distinct facts. No missing support is filled with zero.

FA definitions, domain and limits
----------------------------------------

Profiles are ``arome_history`` and ``surfex_history``. The latter reads
AROME-produced SURFEX ``SFX.PACK=0`` histories with horizontal ``X1`` entries
matching the full storage grid. Layer/patch/tile record names and mask labels are
retained, not averaged or assembled into an invented vertical coordinate. Use
the logical ``surface`` group for individually selected 2-D records; this does
not label every quantity as a physical ground-surface variable.

SURFEX execution requires the evidenced source tags
``PROGRAM=AROME, VERSION=8, BUG=1, MASDEV=47, BUGFIX=0``, a complete FBUF
directory, matching CI dimensions and a matching DTCUR/header state clock.
Unmatched releases remain inspectable but require independent structural/type
evidence before execution. This is distinct from the optional ``expected_source``
assertions and does not establish field units or physical support from tables.

``input.fa.expected_source`` accepts exact assertions for ``PROGRAM``, ``VERSION``,
``BUG``, ``MASDEV`` and ``BUGFIX``; it defaults to an empty mapping. Missing or
unequal native values fail even during metadata inventory. Assertions do not
override source facts or supply a missing producer identity. Semantic precedence
is native facts, release-matched documented conventions, then user completion of
unresolved meaning. A declaration cannot overwrite known units/time semantics.
There is no name-based unit/quantity inference or release-qualified physical
catalogue that fills missing declarations automatically.

For atmospheric ``profile: arome_history``, ``input.fa.native_cubes`` explicitly
associates exact gridpoint records with mass/full or interface labels and centre
sampling. Original record IDs and native indices survive sparse selection.
Normalized A, pressure-valued A, dimensionless B and source reference pressure
remain separate metadata. No pressure, height or full-level mean is inferred;
see :doc:`Native atmospheric levels and cubes <fa_atmosphere>` for these contracts
and collocated physical-vector requirements.

Each selected native record requires ``field_metadata``:

* ``units``: actual decoded source units, not a requested conversion;
* ``kind``: ``continuous`` or ``categorical``;
* ``temporal_kind: instantaneous``: currently the only admitted temporal meaning;
* optional descriptive ``long_name`` and correct ``standard_name``;
* optional ``allow_unscaled: true``: explicit permission for an unverified identity
  fallback when a native scaling warning cannot be resolved. Default
  false: uncertainty discovered during decoding fails the operation.

Fallback warnings are logged and summarized in provenance, including spawned
exporter requests. Packing-120 GRIB2 records with encoded centre-85 local-section-1
factors are observed explicitly; a native unknown-parameter warning alone does
not reject them. Other unresolved warnings still fail by default. Absence of a
scaling warning is not verified identity scaling; see :doc:`fa_contracts`.
Permission to fall back and an actually observed fallback are separate facts.
Permission is not scientific validation. File-level start markers do not
establish every field's interval. Accumulated/averaged FA records,
automatic unit inference, spectral transforms, global/reduced grids, plain LFI
and arbitrary producer conventions are not currently supported.
Packed SURFEX support-map reconstruction, unqualified physical typed arrays and
invented layer/tile axes are also unsupported. Selected native -91/-93/-94 errors
remain failures, not harmless metadata. A transform installation cannot resolve
a native header/encoding failure. Obtain release-specific definitions and trusted
values/masks/coordinates before claiming scientific suitability for a real stream.

Geometry supports modern regular lon/lat and spherical tangent-Lambert headers.
Projected inputs require explicit ``earth_radius_m``. ``subdomain: CI`` (default)
keeps central plus intermediate points; ``C`` excludes the declared I-zone widths.
The spectral extension zone is excluded. Shape/zone indices, angles, radius and
CRS are retained; there is no fitting or guessed Earth-shape default.
Qualified library axes/CRS/zones define the labelled grid; original header
flags/corners remain admission evidence. Provenance records the library-to-CF
origin translation and explicit Earth-model origin.
Dateline-crossing/polar FA grids and unsupported projections fail explicitly.
Existing spacing/anisotropy checks still apply.

``input.fa.max_points`` defaults to 20,000,000 stored points and
``timeout_seconds`` to 120 per transaction. Raise budgets explicitly after
inspection. Decoding can require a full horizontal record even for a tiny crop,
plus coordinate/temporary arrays. Laziness avoids unselected records/times but
does not promise NetCDF-style subrecord I/O. Short-lived helper startup has a
real cost; no throughput improvement is claimed.
Transfers are validated against this point budget before materialization. The
actual NPY dtype/shape is checked read-only before copying out of the owned
temporary directory; malformed/partial transfers fail with source/field context.
Point budgets are not an RSS quota: library workspaces, coordinates, temporary
arrays, mapped transfers and their detached copies contribute to peak memory.
Metadata preflight does not establish native decode throughput or exact peak RSS.

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
``geometry_contract`` records library axes/CRS/native zones
and origin evidence. ``horizontal_header_signature`` has a library-derived JSON
value; consumers must not assume a raw-header layout. This applies to the default
and deprecated alias. ``backend`` / ``FA_backend`` identify
the effective ``epygram`` implementation; ``requested_backend`` /
``FA_backend_requested`` retain the request. ``FA_backend_migration`` records a
legacy alias and its replacement, in addition to visible deprecation warnings.

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
The maintained EPyGrAM path uses library header interpretation and CRS;
the adapter translates its CI-centred axes to the CF origin and expands the
library-derived axes/CRS in the parent. Original encoded corners remain an
independent consistency check; no raw-header geometry reconstruction runs there.

**Independent checks:** asymmetric geometry is checked against separately
evaluated spherical equations in ``test_fa_geometry.py`` (absolute tolerance
:math:`2\times10^{-11}` degrees). Reconstructed CI corners must match encoded
corners within :math:`2\times10^{-5}` degrees, allowing rounded header angles;
this threshold does not permit fitting another CRS. Agreement with encoded
corners is not independent proof of the producer's Earth model.

**Sampling/exclusions:** source-CRS/native-axis point selection applies on the
admitted FA Lambert branch, after checking every geographic sample against its
axes/CRS. Other inputs, including regular lon/lat FA, retain squared-degree
selection. Both conventions handle equivalent longitudes and neither claims a
geodesic-distance minimum. Requested centres, selected points and projected
snapping offsets are distinguished; see
:doc:`FA geometry and centres <fa_geometry>`. Grids, zones, masks, units and
intervals remain distinct.

**Scope/gaps:** generated fixtures verify known values, typed metadata, dates,
readonly bytes, native isolation, multiple times, distinct-grid crops, optional
polar targets, failure handling and ordinary-reader reopening. Physical field/
scaling assumptions still need producer documentation. Spectral records and native
-91 failures need upstream investigation and separate qualification.
