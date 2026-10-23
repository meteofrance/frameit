Experimental polar cells: comparison and method record
======================================================

Purpose and status
------------------

This opt-in experiment evaluates two useful storm-centred representations:
point samples for structure, and scalar cell averages for aggregation/budgets.
It is **experimental**, with no change to ordinary YAML, point products or their
default interpolation. It does not remap velocities or claim mass, momentum,
energy, circulation or flux conservation. It is not a stable diagnostic.

The demonstrated task is sharing storm-centred rainfall-depth cells with explicit
areas and coverage, so a colleague can integrate them without reconstructing the
grid. This fits FrameIt's data-preparation role. Physical diagnostics built from
these data still need their own definitions and validation.

Run the experiment in an environment with the polar dependencies:

.. code-block:: bash

   conda activate frameit_env
   python -m frameit.testing.polar_cell_comparison --output ./runs/polar-cell-comparison
   python -m pytest src/frameit/testing/numerical/test_polar_cells.py

Use a fresh output directory. The command writes ``comparison.json`` and three
small NetCDF products. It records independent overlap checks, analytical errors,
quadrature sensitivity, source refinement, compact-vortex point errors and
single-run build/application times. ``FRAMEIT_BUILD_REVISION`` can supply the code
revision through the existing environment-provenance mechanism. Timings include
first-use initialization and are not an isolated-worker speedup benchmark.

Python opt-in interface
-----------------------

.. code-block:: python

   from frameit.processing.polar.conservative import ConservativePolarPlan

   # source: lon/lat(y, x), explicit lon_b/lat_b(y_b, x_b), all in degrees;
   # y/x are explicit unique index coordinates. No cell corners are inferred.
   plan = ConservativePolarPlan.build(
       source,
       radial_edges_m=[0, 10_000, 20_000, 40_000, 60_000],
       azimuth_count=72,
       center_lon=60., center_lat=-20.,
       earth_radius_m=6_371_000.,
       max_arc_step_deg=1.,
   )
   product = plan.apply(depth, source_representation="scalar_cell_mean")

``depth`` must be a real scalar cell-mean DataArray with declared units, matching
source horizontal index coordinates. When attached, its ``lon``/``lat`` must also
match. The caller must associate the field with the supplied physical grid;
matching array sizes do not establish scientific identity. Point values, cell
totals and categorical values are not supported input interpretations. Native
AROME/Meso-NH adapters do not yet establish these semantics for this interface.

Leading dimensions such as time/level are retained; finite-data coverage is
recomputed per slice. Dask data stay lazy, with one chunk on each horizontal axis
and arbitrary leading chunks. This prototype is for bounded regional inputs, not
full-domain distributed remapping. Each source grid or moving centre needs its
own plan; users can process one time at a time. No implicit geometry reuse occurs.

Method record
-------------

**Quantity, method and maturity.** Scalar cell means, first-order conservative
spherical overlap, experimental. Source values represent piecewise-constant
means on supplied spherical polygons. This preserves that reconstruction's
integral on the shared valid domain; it does not recover unresolved structure or
guarantee exact integrals of an underlying continuous field.

**Reference and established machinery.** The linear-map consistency/conservation
distinction follows Ullrich and Taylor (2015), Section 2a,
DOI ``10.1175/MWR-D-14-00343.1`` (publisher record inspected). Overlap weights are
computed by ESMPy's established ESMF ``CONSERVE`` operation with ``DSTAREA``
normalization. Backend definitions are documented at
https://earthsystemmodeling.org/esmpy/ and
https://xesmf.readthedocs.io/en/stable/notebooks/Compare_algorithms.html.
These references do not constitute independent scientific sign-off on FrameIt's
implementation. The point LocStream path cannot provide this cell operation.

**Inputs, units and geometry.** Supplied 2-D geographic centres and shared corner
arrays, explicit scalar-mean declaration and units, centre, radial edges,
azimuth count, sphere radius, arc subdivision and resource budget. Corner
dimensions are the corresponding centre dimension names with ``_b`` appended,
in the same order. A single sphere defines target distances, polygon edges and
areas. Source polygons are interpreted on that sphere too; this is not an
ellipsoidal physical-area conservation claim.

**Equations and missing data.** With full target area :math:`A_j`, source-target
overlap :math:`A_{ji}`, and finite-value indicator :math:`M_i`,

.. math::

   W_{ji}=A_{ji}/A_j,\qquad
   g_j=\sum_i W_{ji},\qquad
   v_j=\sum_i W_{ji}M_i,\qquad
   N_j=\sum_i W_{ji}M_i\bar q_i.

``geometry_coverage`` is :math:`g_j`. ``valid_area_fraction`` is :math:`v_j`,
relative to the **full** cell, not only the geometrically covered fraction.
``valid_area`` is :math:`A_jv_j`. When :math:`v_j>0`,

.. math::

   \bar q_j^{covered}=N_j/v_j,\qquad I_j^{covered}=A_jN_j.

The full ``cell_mean`` is exposed only when :math:`|v_j-1|\le10^{-8}`. This is a
declared numerical coverage tolerance, not permission to fill substantial gaps.
For zero valid overlap both the covered mean and integral are NaN, while the
valid area is zero. Missing values are zeroed only inside the sparse numerator;
no zero-filled full-cell mean is exported. Raw weights are never normalized to
erase partial geometric coverage. Dynamic masks are not cached in the plan.

For a depth in metres the covered integral has units m3. Other scalar units
produce that unit multiplied by m2; no implicit unit or physical-quantity
conversion is performed. In particular an integral of temperature over area is
not heat content.

**Numerical geometry choices.** Radial edges start at zero. Every angular sector
of the central disk is partitioned into triangles; other cells are partitioned
into quadrilaterals. Constant-radius arcs are approximated with shared spherical
great-circle chords, using ``ceil(sector_width/max_arc_step_deg)`` subsegments.
The seam is closed geometrically, without duplicated output cells. Subcell areas
and weights are aggregated to the requested sectors. Polygonal area differs from
the ideal spherical cap/annulus area; decreasing arc step controls that error.
ESMPy mesh coordinates remain float64. No source corners are guessed, and no
degenerate cells are silently ignored. Native resources are released after
weight construction.

**Applicable scope and failure behavior.** Regional, finite, consistently
connected quadrilateral sources of at most 20 degrees longitude/latitude span;
source absolute latitude below 85 degrees; centre absolute latitude below 80
degrees; target extent at most 500 km. Antimeridian source connectivity is
unwrapped without reordering values. Default ``max_cells=100000`` independently
bounds source cells and target mesh pieces before construction. It is not a
total-memory bound. Missing bounds, mismatched axes, invalid geometry, unsupported
input representation, or budget violations fail explicitly. Source masks should
be represented by missing scalar data; the source dataset's arbitrary ``mask``
variable is not consumed. No extrapolation or nearest-neighbour fallback occurs.

**Independent verification.** Gnomonic projection makes great-circle edges
straight, permitting an independent Shapely polygon intersection oracle. PROJ
evaluates intersection areas on the declared sphere. Tests compare ESMF overlap
areas/integrals to that oracle with relative tolerance ``2e-7`` and small absolute
area tolerances for nearly zero intersections. ESMF source areas are independently
checked within ``1e-9`` relative tolerance. These are numerical implementation
criteria, not universal physical-accuracy guarantees. Cases cover the central
disk, seam, dateline, 60-degree latitude, clipped domains, changing masks,
continuous-centre changes, eager/Dask agreement and ordinary NetCDF reopening.

**Comparison design.** Manufactured localized rainfall has peak depth 0.03 m,
gnomonic centre (13, -7) km and Gaussian widths (8, 12) km. Source spacings are
20, 10 and 5 km; target radii are 0--60 km in 10-km intervals with 24 sectors.
Spherical Gaussian quadrature supplies source cell means and independent target
cell truth; direct centre evaluation supplies source point values and point
truth. Bilinear point sampling, bilinear reconstruction integrated over cells,
and conservative cell means are compared with their appropriate truths.
The source interpretations differ deliberately; model metadata must determine
which interpretation is justified on real data. Bilinear cell integration uses
orders 4 and 8 and reports their difference rather than claiming exactness.
The pass gates cover independent overlap (relative error below ``1e-7``),
analytical quadrature sensitivity (below ``1e-3 m3``), source-refinement improvement
and compact-vortex RMW within one target interval. A passing experiment does not
declare one algorithm universally superior.

A separate full-pipeline WGS84 point-wind baseline uses a compact prescribed
12-km RMW, 50-m/s tangential maximum and 5-m/s inflow, source spacings 4/2/1 km,
500-m target radii and 128 angles. It measures component errors and RMW against
independent truth, without treating conservative scalar remapping as vector
remapping. Existing harmonic and centre-sensitivity qualification remains in
``python -m frameit.testing.polar_qualification``.

Output and interoperability
---------------------------

Products deliberately use ``radius_cell``/``azimuth_cell`` dimensions, rather
than the point-product ``rr``/``theta`` contract. Their coordinates are radial
interval and launch-angle midpoints, not area centroids. Means include appropriate
``cell_measures`` and ``cell_methods``. Products contain:

* radial/angular bounds, representative geographic locations and full cell areas;
* actual spherical subcell vertices, areas and C-order parent indices, allowing
  reconstruction of the polygonal geometry without FrameIt;
* geometric coverage, per-field valid areas, covered means/integrals, and full-cell
  means/validity;
* source/target geometry digest, sphere radius, centre, subdivision, normalization,
  backend version and experimental status.

The comparison adds analytical truth and explicitly labelled point samples; those
samples are not advertised as cell means. The ordinary writer supplies existing
FrameIt product metadata and atomic finalization. These small products use its
existing default encoding; no new compression, precision or chunking contract is
introduced. Ordinary xarray/NetCDF readers suffice. Existing point mean/Fourier
helpers intentionally do not accept these cell dimensions.

Bundled BATSIRAI accumulated-rain pilot
---------------------------------------------

The existing ``--ci`` matrix fixture contains accumulated rain even though its
ordinary matrix cases request other fields. Select the dedicated experimental
preset explicitly:

.. code-block:: bash

   python -m frameit.testing.polar_cell_comparison --ci --output ./runs/polar-cell-ci

This uses the same packaged ``AROME/BATSIRAI`` files and recipe/manifest as the
matrix, verified with the existing content-checksum mechanism. It requires the
optional GRIB and polar dependencies, including Shapely 2 for the spatially indexed
independent oracle. It does not change ``frameit run-matrix-test --ci`` cases or
ordinary processing defaults. Packaged numerical tests exercise the complete pilot
when these dependencies and the fixture are present, so ``run-all-tests`` includes
that check through its numerical suite. The command above retains the detailed
JSON and NetCDF evidence in a designated directory.

**Quantity and time contract.** Select only surface GRIB parameter 235015,
``tirf`` (time integral of rain flux), accumulated from forecast hour zero in
``kg m-2``. The four positive leads retain their original 0--6, 0--12, 0--18 and
0--24-hour intervals as ``time_bounds(time,bounds)``. Time labels are interval ends;
no deaccumulation, hourly-rate calculation or density conversion occurs. The
absent time-zero record is reported as an exclusion, not filled with zero. Missing
later records, multiple candidate records or incompatible units/time metadata
fail the pilot. These overlapping cumulative intervals must not be summed as
independent time increments.

**Spatial assumption, not a producer-validated claim.** The stored input is an
81-by-81 regular geographic grid at 0.025-degree spacing, not a documented native
AROME control-volume mesh. This selected preset explicitly reconstructs analysis
cells around stored centres using adjacent-coordinate midpoints and half a grid
interval at the cropped edges. Both descending latitude storage and data order
are preserved. It interprets the stored scalar as a piecewise-constant mean on
those declared analysis cells. This is an experimental numerical representation;
producer evidence that the values are native-model cell means remains absent.
Metadata records that limitation in every product and the report. There is no
implicit general midpoint-bound inference in the conservative core API.

The GRIB-declared sphere, radius 6,371,229 m, is used for distances and areas.
Source-cell edges are great-circle segments between the constructed corners,
not exact constant-latitude small-circle arcs. Conservation is assessed for that
documented polygon reconstruction, not asserted for native-model rain mass or
ellipsoidal physical area. Missing source data follow the GRIB bitmap.

**Five cases, four times each.** All use a 60-km target radius and at most
2.5-degree arc segments:

* ``fixed``: the recipe centre (17.5 S, 60 E), 10-km radial cells and 24 sectors;
* ``moving``: the same latitude with prescribed longitude offsets
  -0.15, -0.05, +0.05 and +0.15 degrees; this is a sensitivity trajectory inside
  the fixture, not a storm tracker or a claim of optimal cyclone centres;
* ``coarse``: the fixed centre, 20-km radial cells and 12 sectors;
* ``clipped``: fixed longitude 60.85 E, exposing the true cropped-input edge;
* ``masked``: the fixed case with an explicitly synthetic five-column missing
  strip, initially x indices 30--34 and shifted one column per successive time.
  This tests changing support; it is not described as an observed coast mask.

The moving product means **cumulative rain inside each snapshot footprint**, not
rain accumulated along a moving storm domain. No differences between moving
footprint totals are interpreted as rain rates or transport.

**Verification and artifacts.** Independent gnomonic clipping computes each
input analysis cell's overlap with the actual target subcells. Compare accumulated
rain mass in **kg** and valid area per target cell, with ``rtol=2e-7`` and absolute
tolerances 1 kg and 0.05 m2 respectively. Per-cell checks prevent cancellation
from hiding errors in a domain sum. These tolerances allow geometric roundoff;
they are not observational or model-physics accuracy thresholds. No finite native
input is replaced by zero except inside masked sums defining valid overlap.
Unobserved integrals remain NaN in exported products.

Each of the five NetCDF files contains four times, original accumulation bounds,
portable source identifiers, time-varying geographic geometry, representative
centres and geometry signatures, coverage, means and masses. Actual subcell
vertices/areas and static parent indices remain independently readable. Source
content hashes are checked again after execution. ``comparison.json`` retains
the effective preset, source metadata/hashes, exclusions, per-cell-check outcome,
total-mass comparisons, and build/application/oracle times. Memory observations
separate retained plan-array estimates from the process-lifetime RSS high-water
mark, which includes imports and previous cases and is not incremental per-case
memory. This is a bounded 20-snapshot pilot, not a production-performance claim.

An initial report has status ``RUNNING``/``passed=false``. Errors retain a
``FAILED`` report and identify previously completed products; only completion
of all checks and source-integrity verification yields ``PASS``. Outputs must be
fresh and outside the input tree. Ordinary NetCDF reopening verifies values,
time bounds, units and the declared spatial interpretation. A pass establishes
the numerical reconstruction contract on this fixture, not general scientific
validation or admission as a stable method.

The fully covered ``fixed`` and ``coarse`` cases additionally apply bilinear point
sampling and integrated-bilinear reconstruction to the **same stored rain
values**. Their exported fields and reported budget/local differences are
compared to the declared input-cell reconstruction, not to unknown continuous
rainfall truth. Integration-order 4/8 differences are retained. This quantifies
the effect of choosing a reconstruction without claiming either input
interpretation is producer-verified. Local RMS differences weight each polar cell
equally; they are not area-weighted norms. Clipped and masked cases focus on the
independent conservative coverage contract rather than assigning an unsupported
full-cell bilinear average.

Accumulated sensible and latent surface heat exchange
------------------------------------------------------

The same opt-in pilot also selects the two accumulated surface heat quantities
already present in the frozen BATSIRAI GRIB files:

.. code-block:: bash

   python -m frameit.testing.polar_cell_comparison --ci-heat-fluxes --output ./runs/polar-heat-ci

This selection is mutually exclusive with the rainfall ``--ci`` selection. It
creates ``sshf/`` and ``slhf/`` subdirectories, each with five NetCDF products and
a detailed ``comparison.json``, plus an outer completion/failure report. The
rainfall command and its mass/product names remain available. The shared code
handles only these three explicitly declared accumulated scalars; it is not a
generic variable-meaning inference mechanism.

**Quantity contract.** ``sshf`` is parameter 146 (time-integrated surface sensible
heat net flux); ``slhf`` is parameter 147 (time-integrated surface latent heat net
flux). Require surface ``accum`` records in J/m2, with statistical processing
type 1, hour-valued steps starting at zero and the expected recipe end time.
J/m2 remains J/m2 in means; its area integral is **joules**, not watts or joules
per kilogram. The original 0--6/12/18/24-hour bounds are retained. No division by
duration, deaccumulation, density/heat-capacity conversion or summation of the
overlapping cumulative intervals is performed. Missing time-zero records are
reported separately for each quantity; missing positive-lead records fail.

**Signs and physical interpretation.** All finite source signs are preserved.
In this fixture, ``slhf`` is negative everywhere and ``sshf`` includes both
positive and negative values. Neither is clipped to zero or silently inverted.
The outputs describe source-signed cumulative surface heat exchange within each
footprint, not atmospheric/oceanic heat content, nor a complete energy budget.
The producer's physical upward/downward sign interpretation has not been
independently established here; no directional conversion or heat-loss/gain
claim follows from the signs alone. As with rainfall, moving footprints are
snapshot integration domains, not accumulations following a storm trajectory.

**Geometry and coverage.** Use the same declared midpoint analysis cells,
GRIB sphere and fixed/moving/coarse/clipped/synthetic-mask cases as rainfall.
No new claim that the postprocessed fields are native-model cell means is made.
Masked or unmapped integrals stay NaN; valid-overlap means and areas remain
distinct from full-cell means. Source files are checksum-verified before and
after each quantity's pilot. Ordinary xarray/NetCDF readers check both values
and original temporal metadata, and direct netCDF4 tests independently check
energy units, negative values, coverage and time bounds.

**Signed numerical verification.** A small signed domain total can result from
large opposing contributions. Check each cell, not only the total. Let

.. math::

   E_j^*=\sum_i A_{ji}q_i,\qquad C_j=\sum_i A_{ji}|q_i|.

Here :math:`q_i` is the stored accumulated J/m2 scalar, :math:`A_{ji}` is the
independently clipped valid overlap in m2, and both :math:`E_j^*` and :math:`C_j`
are energies in joules. Require

.. math::

   |E_j-E_j^*| < 1\ \mathrm{J} + 2\times10^{-7} C_j.

This engineering tolerance controls error relative to the absolute input
contributions even when the net is zero. Positive and negative errors in
different output cells cannot hide each other. For nonnegative rainfall this
reduces to the original absolute-plus-relative per-cell tolerance. The report
also includes :math:`\sum_j|E_j-E_j^*|/\max(\sum_j C_j,1\ \mathrm{J})`, named
``integral_l1_normalized_error``, and the net-to-absolute integral ratio to expose
cancellation. Net-relative differences are descriptive, not the acceptance gate;
they can be ill-conditioned for nearly cancelled totals.

Fixed/coarse cases retain bilinear midpoint and integrated-bilinear comparisons
on identical stored values, including integration-order 4/8 sensitivity.
Local differences have units J/m2 and equally weight polar cells. Comparisons
are against the declared analysis-cell reconstruction, not continuous physical
truth. An initial local ESMPy 8.9.1/xESMF 0.9.2 run passed all 40 snapshots, with
maximum L1-normalized overlap discrepancies approximately ``7e-14`` for each
quantity. This establishes numerical agreement for this fixture under the stated
geometry/representation, not a physical-accuracy guarantee or default promotion.

Both child reports and the outer report record failures. A failed second
quantity retains the first quantity's completed product inventory while leaving
the overall run failed, never successfully complete. The heat-energy tests also
exercise signed cancellation and reject instantaneous/averaged W/m2 records in
this accumulated-energy path. Synthetic sign/cancellation checks and this single
regional case do not establish validity for all model conventions or regimes.

Initial observations and promotion decision
-------------------------------------------

One local run with ESMPy 8.9.1/xESMF 0.9.2 observed:

.. list-table:: Manufactured rainfall; errors in cell averages are millimetres
   :header-rows: 1

   * - Source spacing
     - Conservative cell-mean RMS
     - Integrated-bilinear cell-mean RMS
     - Conservative smooth-truth budget error
     - Bilinear midpoint budget error
   * - 20 km
     - 2.780
     - 1.996
     - -0.0414%
     - +6.95%
   * - 10 km
     - 1.593
     - 0.867
     - -0.00350%
     - +1.12%
   * - 5 km
     - 0.464
     - 0.221
     - -0.000561%
     - +0.397%

Conservation of the piecewise-constant source reconstruction over the shared
domain agreed with independent overlap to roughly ``2e-14`` relative in these
cases. That is a different criterion from error against continuous smooth truth.
Integrated-bilinear quadrature differences were up to 0.024 mm in this run, so its
reported local errors are approximate. Integrated bilinear also greatly improved
the midpoint budget estimate: at 5-km source spacing its smooth-truth budget error
was about +0.00229%. It still does not enforce source-cell integral preservation.
These observations support keeping both representations scientifically explicit;
they do not support a universal conservative default.

**Remaining gaps and review status.** Producer-verified native-model bounds and
field-mean semantics, sharp/discontinuous analytical precipitation, observed
land/coast masks, ellipsoidal
physical-area treatment, larger workload memory measurements, vector/flux
methods, repeated isolated performance runs, and independent scientific review
remain outstanding. There is no stable promotion or default change. The next
decision should use actual user quantities and native-grid metadata, comparing
budget fidelity and structure at the required scales.
