FA grids, domain selection and centres
======================================

Choose ``fa.subdomain`` for the retained zone. For a nonstandard projected
grid, declare the producer's ``fa.earth_radius_m``. These rules determine
sample locations, not field identity, scaling, vector basis or physical height.
See :doc:`fa_inputs` for a complete request and :doc:`fa_baseline` for compatibility.

Supported grids and Earth model
-------------------------------

* **Modern regular longitude/latitude:** complete rectangular ``CI`` grid with
  nonzero angular increments. ``subdomain: C`` is not supported on this branch.
* **Modern spherical tangent Lambert:** ``subdomain: CI`` (default) retains the
  central plus intermediate region; ``C`` removes the declared I-zone widths.
  The spectral extension is excluded. ``CIE`` storage bounds are retained as
  metadata, not offered as an output-zone selection.

If ``sources.<id>.fa.earth_radius_m`` is omitted for supported AROME or
SURFEX tangent Lambert FA, FrameIt uses **6,371,229 m**, the spherical radius
documented in the `AROME projection guide (section 4.3.1 D)
<https://www.cnrm.meteo.fr/gmapdoc/IMG/pdf_PROJECTIONS_GB_72-1.pdf>`_ and
`SURFEX v8.1 source <https://www.umr-cnrm.fr/surfex/data/BROWSER/doc_surf81/ini__csts_8F90_source.html#l00116>`_.
FrameIt warns when it uses the default and records the value and origin in
``run-provenance.yaml``.

An explicit positive radius takes precedence. FrameIt checks the library
geometry against the encoded grid corners with either radius. If they
disagree, supply the producer's actual radius; FrameIt does not fit or try
another value. Regular longitude/latitude grids do not acquire a default
Earth model.

Active modern header entries must be finite: ``KNLOPA[:8]`` has integral domain
indices/nonnegative I-zone widths and one-based inclusive CI bounds;
``PSINLA[:16]`` carries active angular parameters in radians. The geographic anchor
is at the CI centre, not the full CIE-storage centre. Rectangular dimensions must
be integers of at least two points. Lambert requires positive projected spacings
and a nondegenerate reference latitude, with tangent-cone magnitude matching
``abs(sin(reference_latitude))`` within ``5e-7``.

Unknown/older headers, rotation/stretch/academic conventions, secant Lambert,
Mercator, stereographic, ellipsoidal, global/reduced, dateline-crossing and polar
grids are unsupported. A similarly named library projection does not establish
their native header, Earth-model, scanning or zone conventions.

Library axes and CF origin
--------------------------

EPyGrAM centres projected axes on CI. FrameIt translates that origin to the CF
tangent-latitude origin while preserving the **same physical samples**.
It does not fit a projection, interpolate fields, rotate vectors or calculate
pressure/height. Native point budgets apply before axes/geography are allocated.

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
ground/geodesic distance; they can select different points near cell boundaries.

Requested ``lat``/``lon`` remain continuous and define polar targets/track
kinematics. They are not replaced by snapped source coordinates. Each source is
located separately; atmospheric ``cx``/``cy`` cannot be reused on a surface grid.

Numerical association, boundaries and ties
------------------------------------------

Projected lookup requires explicit spherical Lambert CF metadata, static labelled
latitude/longitude in degrees and finite monotone regular X/Y axes in metres.
Lookup supports ascending/descending storage, subject to the native-header
admission rules. Before choosing centres, **every** geographic sample is projected
and compared to its labelled axes. Interior association is checked, not just
corners/shapes. Coordinate I/O and projection add to preflight cost; scientific
payloads stay lazy.

The internal double-precision sample/CRS consistency tolerance is ``1e-5 m``.
Axis regularity, boundary roundoff and ties use the greater of ``1e-5 m`` and
``64 * machine_epsilon * coordinate_magnitude``. Exact/roundoff ties choose the
first **storage index**, including descending axes. These are numerical roundoff
bounds, not physical footprint extensions, CRS fitting or relaxed header checks.

A centre outside a required source's native point-axis envelope fails, apart
from numerical roundoff: no edge substitution or spatial time skip.
A box extending beyond a source keeps NaN padding. CI/C offsets stay attached
to original indices.
Existing core scalar-spacing guards still reject more than 10% X/Y spacing
difference or 20% within-axis variation, even with a nominal spacing override;
separate X/Y lookup distances do not add anisotropic extraction support.

Track and provenance interpretation
-----------------------------------

Preflight/input records carry the source geometry and lookup convention.
``grid_geometry.index_lookup`` identifies the native point-selection method.
``geometry_contract`` and ``fa_geometry_origin`` / ``fa_earth_model_origin``
retain library zones/CRS, origin translation and whether the radius was explicit,
defaulted or unresolved.

Cropped field products distinguish requested ``center_latitude``/
``center_longitude`` from ``grid_selected_latitude``/``grid_selected_longitude``.
Per-source region provenance records native indices, realised extents and coverage.
For projected FA, ``sources.<id>.region.grids.<grid>.grid_lookup`` also records
the lookup method, offset/tie conventions and selected geography/snapping offsets.
Its ``variables`` entries carry ``values`` and ``units``; arrays follow that
source's ``region.associations`` order (or the individual grid record's source time).
These locations and indices belong to that source's grid; they cannot be reused
on a shifted surface or atmospheric grid.

A requested trajectory exports geographical ``latitude``/``longitude`` against
time, not a universal grid-index system. Do not assume that it contains every
source's indices or snapping offsets. A source-CRS Euclidean snapping distance
is not ground/geodesic distance. Exported local box axes are not original
source-projection axes. Read each product's actual coordinates and units;
see :doc:`output_files`.

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

These numerical bounds do not confirm a real producer's Earth model, geographic
checkpoints, physical definitions or vector/vertical sampling. Trusted references
and scientific review remain required; see :doc:`fa_baseline`.
