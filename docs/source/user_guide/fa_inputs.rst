Native FA and coupled sources
========================================

Use ``format: fa`` with ``profile: arome_history`` for admitted atmospheric
gridpoint records or ``profile: surfex_history`` for dense AROME-produced
SURFEX-8.1 histories. Records must be instantaneous. Native atmospheric cubes
need explicit record associations.

The reader is **EPyGrAM 2.1.0**. Check :doc:`fa_baseline` before selecting fields;
FA support is limited to its listed producers, layouts and operations.

Installation and native isolation
----------------------------------------

FA reads run in isolated processes using the active Python by default. Set
``sources.<id>.reader.python_executable`` to select another runtime containing FrameIt and
the FA stack. See :doc:`fa_environment` for installation and troubleshooting.
NetCDF/GRIB processing does not require the FA package.

Helpers use one native thread and serialize requests per consuming process.
They use bundled definition/sample tables, not inherited
``ECCODES_DEFINITION_PATH``/``ECCODES_SAMPLES_PATH`` overrides. Parent GRIB settings
are unchanged. Custom FA tables are not an adapter option.

Inspect first
-------------

.. code-block:: bash

   frameit inspect frameit.yaml
   frameit inspect frameit.yaml --json

Set source files, ``format: fa`` and ``profile`` before inspection.
Inspection reports native facts, not inferred units or an Earth model.
Selected native errors such as -91 remain failures.

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

Set ``format: fa`` inside each FA source, including a single-source request.
Do not put atmospheric and SURFEX companion files into an undifferentiated FA
inventory: they are complementary streams, not duplicate observations.

Named-source configuration
--------------------------

This complete request copies mean sea-level pressure and one declared SURFEX
quantity on their native grids. Paths and field meanings are illustrative.
The radius below repeats the documented default for supported tangent Lambert
FA. Declare a different radius only from producer evidence:

.. code-block:: yaml

   schema_version: 3
   run:
     name: coupled-surface
   sources:
     atmosphere:
       model: arome
       format: grib
       files: ./data/atmosphere/*.grib
       variables:
         2d: [prmsl]
     surface:
       model: arome
       format: fa
       profile: surfex_history
       files: ./data/historic.surfex*.fa
       variables:
         2d: [SFX.T2M]
       field_metadata:
         SFX.T2M:
           units: K
           kind: continuous
           temporal_kind: instantaneous
       fa:
         subdomain: CI
         earth_radius_m: 6371229
   output:
     directory: ./results/coupled-surface

Keep files, selections, declarations and ``reader`` settings inside their source.
``profile`` and ``native_cubes`` sit beside ``model``/``format``; FA-only options
sit under ``fa``. Both profiles use ``model: arome``. Profile and native evidence
distinguish atmosphere from surface; other producers remain unsupported.

Omitted ``region`` and ``products`` copy full native model-grid fields without
tracking or polar processing. To crop, add one top-level ``region.center`` or
``region.track.file``. Calculated tracking uses the atmospheric source, independent
of its name; FA-driven atmospheric tracking is unsupported. See
:doc:`../task_guides/coupled_inputs` for centre and time requirements.

.. _time-choice-common-or-strict:

Source times and centre coverage
--------------------------------

Each source keeps its own selected clock. Independent extraction does not
require an intersection or an atmospheric reference source.
``region.sources_coupling_time_association`` governs operations needing centres:
the default ``exact`` requires a centre at each selected source sample, while
``common`` explicitly reports excluded records. Extra supplied track times do
not create source samples; missing required centres fail by default.

``preceding_hour`` is restricted to the
:doc:`AROME/NEMO NetCDF contract <../concepts/time_support>`, not FA.
No policy interpolates centres, fills fields, deaccumulates energy or changes
interval meaning. Invalid/ambiguous clocks fail. Association exclusions and
tracker incompleteness are separate facts in provenance/status.

Grids, centres and products
---------------------------

Fixed positions, a supplied trajectory or a calculated atmospheric track provide
geographical centres. Each required source maps them onto its own static regional
grid using the documented geometric lookup.
Atmospheric ``cx``/``cy`` indices are never reused on another grid. A centre
outside a required secondary footprint fails: no edge-point substitution or
spatial time skipping. Boxes partly outside a grid keep existing NaN padding.

Native products are source-qualified:

.. code-block:: text

   products/coupled-surface.atmosphere.model_grid.nc
   products/coupled-surface.surface.model_grid.nc

No trajectory is requested by this example. Select ``products.track`` explicitly
when using a centre provider and needing its reusable NetCDF trajectory.
Inspect each product's coordinates and provenance. FA fields retain source indices,
masks and scientific meaning. Declarations do not request rotation, pressure/height,
speed or polar processing: each operation needs explicit selection and support.
Physical support labels, undefined samples, extension zones and real zeroes remain
distinct; missing support is never zero.

FA definitions, domain and limits
----------------------------------------

Use ``variables.2d`` for individual records, including layer/patch/tile names.
They remain separate 2-D records, not inferred vertical axes or averages.
``surfex_history`` requires dense ``SFX.PACK=0`` horizontal ``X1`` entries matching
the full storage grid; support labels do not determine physical meaning.

SURFEX execution requires the evidenced source tags
``PROGRAM=AROME, VERSION=8, BUG=1, MASDEV=47, BUGFIX=0``, a complete FBUF
directory, matching CI dimensions and a matching DTCUR/header state clock.
Unmatched releases remain inspectable but cannot execute without independent
structural/type evidence. Layout checks do not establish field units/support.

Optionally assert exact ``PROGRAM``, ``VERSION``, ``BUG``, ``MASDEV`` and ``BUGFIX``
under ``fa.expected_source`` (default ``{}``). Missing/unequal native values fail
even at inventory. Assertions neither supply producer identity nor override facts.
Precedence is native facts, release-matched conventions, then user completion of
unresolved meaning. There is no automatic name-based physical catalogue.

For atmospheric cubes, declare exact records, mass/full or interface labels and
centre sampling under ``native_cubes``. Original IDs/indices and distinct native
A/B/reference-pressure metadata survive selection; no pressure, height or full-level
mean is inferred. See :doc:`fa_atmosphere` for the association and wind requirements.

Each selected physical record or logical cube needs source ``field_metadata``:

* ``units``: actual decoded source units, not a requested conversion;
* ``kind``: ``continuous`` or ``categorical``;
* ``temporal_kind: instantaneous``: currently the only admitted temporal meaning;
* optional descriptive ``long_name`` and correct ``standard_name``;
* optional ``allow_unscaled: true``: explicit permission for an unverified identity
  fallback when a native scaling warning cannot be resolved. Default
  false: uncertainty discovered during decoding fails the operation.

Packing-120 GRIB2 records use observed centre-85 local-section-1 scaling factors;
an unknown-parameter warning alone does not reject them. Other unresolved warnings
fail by default. Fallback permission and actual fallback are recorded separately;
neither permission nor absence of warnings proves scaling. See :doc:`fa_contracts`.

Accumulated/averaged fields, spectral transforms, packed support-map reconstruction,
unqualified physical typed arrays and inferred layer/tile axes are unsupported.
File-level time markers do not establish field intervals. Selected -91/-93/-94
errors need producer/upstream evidence, not relabelling or another transform library.
See :doc:`fa_baseline` for all excluded layouts and operations.

Geometry admits modern regular lon/lat and spherical tangent Lambert.
Lambert uses the documented 6,371,229 m radius when ``earth_radius_m`` is
omitted. ``subdomain: CI`` (default) retains
central/intermediate points and ``C`` removes the declared I zone. Spectral extension
points are excluded. Regular lon/lat permits CI only. Unsupported projections,
dateline-crossing/polar grids and excessive spacing variation fail.
:doc:`fa_geometry` explains the radius override, geometry checks, zones and
recorded library-to-CF translation.

Source ``reader.max_points`` defaults to 20,000,000 stored points and
``reader.timeout_seconds`` to 120 per transaction. Raise budgets explicitly after
inspection. Decoding can require a full horizontal record even for a tiny crop,
plus coordinate/temporary arrays. Laziness avoids unselected records/times but
does not provide NetCDF-style subrecord I/O.
Malformed/partial transfers fail with source/field context. Point budgets are not
RSS quotas: library workspaces, coordinates and transfer copies add memory.
Preflight does not measure decode throughput or peak RSS.

Provenance and failure
----------------------

Read ``run-provenance.yaml`` and ``logs/fa-decoder-*.jsonl`` for per-file
descriptors, geometry, source declarations and actual versions/scaling/mask facts.
A variable's JSON descriptor is only a representative input snapshot.
:doc:`fa_contracts` defines these records, including requested versus actual backends.
Size/mtime freshness is not checksum proof.

A required decode/export failure prevents completed status. Publication is per
product, not a multi-product transaction or fsync guarantee; see :doc:`output_files`.

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
metres, one-based inclusive ``KNLOPA`` CI bounds, the resolved spherical radius
from :doc:`fa_geometry`, and the CI-centre geographical anchor.
Only active header entries define geometry; unused work
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
evaluated spherical equations (absolute tolerance :math:`2\times10^{-11}` degrees).
Reconstructed CI corners must match encoded
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

**Scope/gaps:** compact analytical checks do not qualify real-producer field
definitions or scaling. These need release-matched documentation and trusted
values/masks/coordinates. Spectral records and unexplained native errors need
separate qualification.
