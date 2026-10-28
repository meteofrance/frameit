FA grids, domain selection and centres
======================================

FrameIt labels FA samples using qualified EPyGrAM axes/CRS/native-zone facts,
with independent original-header admission checks. Geometry success does not
establish field identity, scaling, vector basis or physical vertical coordinates.
See :doc:`fa_inputs` for declarations and :doc:`fa_baseline` for compatibility.

Supported grids and Earth model
-------------------------------

* **Modern regular longitude/latitude:** complete rectangular ``CI`` grid with
  nonzero angular increments. ``subdomain: C`` is not supported on this branch.
* **Modern spherical tangent Lambert:** ``subdomain: CI`` (default) retains the
  central plus intermediate region; ``C`` removes the declared I-zone widths.
  The spectral extension is excluded. ``CIE`` storage bounds are retained as
  metadata, not offered as an output-zone selection.

Projected FA requires explicit positive ``input.fa.earth_radius_m`` based on
producer evidence. The library geoid must match this radius; it is never fitted
to encoded corners. An angular regular grid can leave the Earth model unresolved
and does not thereby acquire the library's default geoid.

Active modern header entries must be finite: ``KNLOPA[:8]`` has integral domain
indices/nonnegative I-zone widths and one-based inclusive CI bounds;
``PSINLA[:16]`` carries active angular parameters in radians. The geographic anchor
is at the CI centre, not the full CIE-storage centre. Rectangular dimensions must
be integers of at least two points. Lambert requires positive projected spacings
and a nondegenerate reference latitude, with tangent-cone magnitude matching
``abs(sin(reference_latitude))`` within ``5e-7``.

Unknown/older headers, rotation/stretch/academic conventions, secant Lambert,
Mercator, stereographic, ellipsoidal, global/reduced, dateline-crossing and polar
grids are not admitted. Additional variants need actual versioned native headers,
Earth models, anchor/scanning/zone conventions and independent geographic checks;
a similarly named library projection is insufficient.

Library axes and CF origin
--------------------------

EPyGrAM centres projected axes on CI. FrameIt translates that library CRS origin
to its CF tangent-latitude origin while preserving the **same physical samples**.
This is an origin translation, not a fitted projection, field interpolation,
vector rotation or pressure/height calculation. Only one-dimensional axes/CRS/zone
facts cross the worker boundary; the parent expands geographic coordinates.
Native point budgets apply before axis allocation and coordinate expansion.

CI/C slices keep original zero-based ``source_i`` and ``source_j``. Masks cannot
become valid geographic coordinates. Library CI corners must agree with original
encoded corners within ``2e-5 degree``, allowing rounded modern header angles.
This is a header-consistency bound, not a producer-Earth-model accuracy claim.
Inactive work-buffer tails and vertical-header inheritance do not determine 2-D
sample locations; native spectral metadata does not establish coefficient geometry.

Within one source's time sequence, the horizontal signature must match. It records
library axes/CRS/zones, selected zone and Earth-model/origin facts; equal array
shapes are insufficient. Separate sources retain independent grids. The signature
is not a field, vertical, spectral-coefficient or content-checksum contract.

Choose a source point without moving the requested centre
---------------------------------------------------------

The admitted projected branch declares ``fa_source_crs_native_axes_v1``.
Fixed-box, prescribed-track and coupled secondary-source lookup transform the
requested geographical centre into **that source's** spherical Lambert CRS, then
select the nearest point independently on its labelled metre axes.
This chooses an index; it does not interpolate the scientific field.

Regular lon/lat FA and other input formats retain their squared-degree lookup,
with equivalent longitudes handled modulo 360. An ordinary CF mapping on another
format does not switch its lookup convention. Neither metric promises the minimum
ground/geodesic distance. For example, the independently specified southern
Lambert fixture at requested projected ``(-4499.99, -2100) m`` selects storage
``(j=1, i=1)`` using native axes but ``(1,0)`` using squared geographic degrees.
The distinction matters near cell boundaries; it is not a new interpolation choice.

Requested ``lat``/``lon`` remain continuous and define polar targets/track
kinematics. They are not replaced by snapped source coordinates. Each source is
located separately; atmospheric ``cx``/``cy`` cannot be reused on a surface grid.

Numerical association, boundaries and ties
------------------------------------------

Projected lookup requires explicit spherical Lambert CF metadata, static labelled
latitude/longitude in degrees and finite monotone regular X/Y axes in metres.
Lookup supports ascending/descending storage, subject to the native-header
admission rules. Before choosing centres, **every** geographic sample is projected
and compared to its labelled axes in blocks of at most 32 rows. This checks
interior association, not just corners/equal shapes. Scientific payloads stay
lazy, but coordinate I/O and projection have a real cost; no production-throughput
claim follows from this bounded processing.

The internal double-precision sample/CRS consistency tolerance is ``1e-5 m``.
Axis regularity, boundary roundoff and ties use the greater of ``1e-5 m`` and
``64 * machine_epsilon * coordinate_magnitude``. Exact/roundoff ties choose the
first **storage index**, including descending axes. These are numerical roundoff
bounds, not physical footprint extensions, CRS fitting or relaxed header checks.

A required coupled source rejects centres outside its native point-axis envelope
apart from numerical roundoff: no edge substitution or spatial time skip.
Single-source edge-nearest selection retains its recorded offset. A box extending
beyond a source keeps NaN padding. CI/C offsets stay attached to original indices.
Existing core scalar-spacing guards still reject more than 10% X/Y spacing
difference or 20% within-axis variation, even with a nominal spacing override;
separate X/Y lookup distances do not add anisotropic extraction support.

Track and provenance interpretation
-----------------------------------

Preflight/input records carry ``horizontal_header_signature`` and ``grid_lookup``;
``grid_geometry.index_lookup`` and track summary ``tracking_grid_lookup``,
``tracking_snap_convention`` and ``tracking_grid_ties`` identify the convention.
``geometry_contract`` and ``fa_geometry_origin`` / ``fa_earth_model_origin``
retain library zones/CRS, origin translation and declared versus unresolved facts.

Projected FA tracks record:

* ``grid_selected_latitude`` / ``grid_selected_longitude``: actual selected source point;
* ``grid_snap_dx_m`` / ``grid_snap_dy_m``: selected minus requested source-CRS X/Y;
* ``grid_snap_distance_m``: Euclidean norm of projected offsets, **not ground distance**.

Coupled tracks prefix these variables with the source ID, for example
``surfex_grid_snap_dx_m``. Source-prefixed indices/offsets remain independent;
base ``cx``/``cy`` belong to the tracking source. One source's observations are
cleared before locating another source. Exported local box axes are not thereby
reinterpretable as original source-projection axes. Read each product's actual
coordinates and units; see :doc:`output_files`.

Method, verification scope and limitations
------------------------------------------

The mathematical basis is the spherical tangent-Lambert mapping in John P. Snyder
(1987), *Map projections: A working manual*, USGS Professional Paper 1395,
`doi:10.3133/pp1395 <https://doi.org/10.3133/pp1395>`_. The equations and signed
southern-cone convention are retained in :ref:`fa-geometry-method`. The library
owns current header/CRS interpretation; independent equations, encoded corners
and labelled-axis checks serve distinct purposes.

Independent compact checks use Snyder equations in both hemispheres, off-origin
anchors, asymmetric offset CI/C/E zones, descending/equivalent-longitude lookup,
ties, coverage and shifted-grid rejection. Specified agreement bounds are
``1e-7 m`` for canonical axes, ``2e-11 degree`` for inverse-equation geography,
and ``1e-10 degree`` for regular angular axes. These are fixture/float64 numerical
bounds, distinct from the ``2e-5 degree`` native-header precision check and
``1e-5 m`` internal consistency tolerance. A pyproj round trip alone is not the
independent scientific oracle.

Compact native extraction/coupling checks reopen values and metadata through
ordinary NetCDF readers. They do not independently confirm a real producer's
Earth model, geographic checkpoints, physical definitions or vector/vertical
sampling. Those references and scientific review remain required. Geometry does
not resolve unknown scaling, native errors, packed/typed support, intervals or
spectral execution. Continuous production polar sampling defaults to bilinear
point interpolation without conservation; no experimental method is activated
by a grid being readable.
