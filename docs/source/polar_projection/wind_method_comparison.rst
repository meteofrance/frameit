Experimental wind-method comparison
===================================

Purpose and execution
---------------------

This opt-in experiment compares wind **point** representations for cyclone
structure: component errors, radial leakage, peak winds, RMW, harmonics and centre
sensitivity. Scalar area conservation is not its acceptance criterion. It does
not change the ordinary polar default, admit a stable diagnostic, or remap
momentum, kinetic energy or fluxes conservatively.

.. code-block:: bash

   conda activate frameit_env
   python -m frameit.testing.polar_wind_comparison --output ./runs/wind-methods
   # Add the matrix's frozen, read-only AROME/BATSIRAI winds:
   python -m frameit.testing.polar_wind_comparison --ci --output ./runs/wind-methods-ci

Use fresh or empty output roots outside the source fixture tree. The default
requires the polar dependencies; ``--ci`` additionally requires the GRIB stack
and bundled fixture. All stages run sequentially in one process. Missing or
unsupported requested backends fail instead of silently dropping a candidate.
Failed parent reports retain stage references and never claim completion.

Methods and scope
-----------------

The four methods form a two-by-two comparison, isolating scalar weight order
from tangent-basis treatment:

.. list-table:: Explicitly selected experimental candidates
   :header-rows: 1

   * - Name
     - Spatial weights
     - Vector treatment
   * - ``bilinear_components``
     - Production-compatible xESMF bilinear
     - Interpolate local Earth-relative east/north components independently
   * - ``bilinear_transport``
     - Identical bilinear weights
     - Transport each contributing vector to the target tangent basis first
   * - ``patch_components``
     - ESMF ``PATCH`` polynomial patch-recovery weights
     - Interpolate local east/north components independently
   * - ``patch_transport``
     - Identical ``PATCH`` weights
     - Transport each contributing vector to the target tangent basis first

``PATCH`` is not the same algorithm as the bicubic interpolation used in some
cyclone papers. It has signed weights, is not guaranteed monotone or nodally
interpolatory, and can alter sharp extrema. No clipping is applied. Its behavior
is measured against independent truth rather than justified by its order alone.
The existing production path intentionally still supports its established point
methods and missing-data contract; these candidates live in the testing package.

Inputs must already be collocated, share labelled horizontal locations, and be
explicitly Earth-relative in m/s. Conflicting available GRIB component flags fail.
This comparison does not invent grid rotation or staggered-wind conventions.
Native Meso-NH preparation remains covered by its existing dedicated tests, not
new real-data qualification in this experiment.

Method record: vector transport
----------------------------------------

**Status and geometry.** Experimental numerical representation of horizontal
velocity, using WGS84 shortest-geodesic parallel transport. ESMF's scalar
interpolation weights still use spherical geographic geometry, as in the
baseline. All variants sample identical target points, defined by WGS84 distance
and uniformly periodic, endpoint-exclusive launch angles. The output remains
Earth-relative; aligning tangent bases is not advection of air parcels or
subtraction of storm translation. Reference-surface geometry is used rather
than an altitude-adjusted wind-layer surface.

**Formula and adaptation.** For initial and terminal-forward bearings
:math:`\alpha_1,\alpha_2` of the geodesic from a source point to its target, set
:math:`\delta=\alpha_2-\alpha_1`. Preserving along- and cross-geodesic components
gives

.. math::

   u_t=u_s\cos\delta+v_s\sin\delta,\qquad
   v_t=v_s\cos\delta-u_s\sin\delta.

The geodesic tangent is parallel along its own path; its orthogonal tangent
direction is also parallel. This is the experiment's geometric adaptation,
not a formula claimed to be a cyclone diagnostic from a cited paper. Coincident
endpoints use the identity. Rotated contributions are combined with the same
scalar weights as their component-wise counterpart. Transport rotations are
precomputed as sparse cosine/sine operators for the contributing source/target
pairs. No velocity scaling or map-factor correction is added.

Transport changes the finite-resolution representation: constant local east/north
coefficients need not remain constant after neighbouring vectors are transported.
Scalar constant preservation is not proof of vector consistency. Conversely,
nonnegative bilinear weights bound the resulting speed by the contributing
source speeds, while signed patch weights need not. Independent point truth,
source refinement and peak metrics assess these trade-offs; no component/speed
extrema are clipped to make a candidate look better.

**References and independent checks.** Karney (2013),
DOI ``10.1007/s00190-012-0578-z``, supplies the geodesic algorithms and distinct
endpoint-bearing definitions; existing tests check its published coordinates.
An independent three-dimensional Rodrigues rotation along a spherical great
circle checks transport direction/sign and norm, including dateline crossing.
Direct manufactured wind evaluation checks the complete WGS84 point operation
without the production interpolation or transport helper. These checks are not
independent human scientific sign-off or evidence of universal superiority.

Backend algorithm definitions are documented at
https://xesmf.readthedocs.io/en/stable/notebooks/Compare_algorithms.html.
Ryglicki and Hodyss (2016), DOI ``10.1175/JAMC-D-15-0125.1``, and Zhao et al.
(2019), DOI ``10.3390/atmos10060300``, motivate centre-displacement and harmonic
tests. Their use of other interpolation schemes is precedent, not validation
of ESMF ``PATCH`` or this transport implementation. Existing analytical fixture
definitions and departures are in :doc:`scientific_qualification`.

Masks, normalization and failure behavior
-----------------------------------------

Every output vector requires both source components to be finite at **all**
contributing nonzero-weight source points. Both bases of a given spatial method
use exactly the same joint mask. Absolute coefficients at or below ``1e-14``
are removed before stencil tests. Bilinear weights use the production support
operator. Patch rows must preserve scalar constants within ``rtol=1e-10`` and
``atol=1e-12`` before normalizing only row-sum roundoff. Negative patch weights
are retained; no positive-weight support-fraction interpretation is assigned.

Missing values are zeroed only inside masked sparse multiplication, then invalid
results become NaN. No partial-stencil renormalization, extrapolation, nearest
fallback or smoothing beyond the declared spatial operator occurs. Geometry
mapping, joint vector validity and polar-component validity are separate
indicators. At zero radius, U/V and speed can remain valid, while radial/tangential
components are undefined. Native-source NaN padding is trimmed through the
existing finite-footprint contract; missing interior geography fails.

The comparison caps source grids at 100,000 points, target geometry at 50,000
points, geographic source spans at 20 degrees, and target radii at 500 km. These
are workload/scope limits, not universal accuracy criteria or total-memory caps.

Analytical design and acceptance
--------------------------------

Six direct kinematic references cover southern tangential-only flow, compact
northern inflow plus swirl (12-km RMW), 60-degree latitude, an antimeridian
curvilinear grid, a broad vortex plus regularized mode-two streamfunction
perturbation, and a sharp manufactured lognormal tangential jet:

.. math::

   V_t(r)=50\exp\left[-\tfrac12\left(\log(r/30000)/0.12\right)^2\right]
   \quad(r>0),\qquad V_t(0)=0.

Radius in this formula is metres. The lognormal fixture is a manufactured smooth
kinematic stress test, not a claim to implement a published balanced cyclone.
Planar streamfunction components are explicitly interpreted as local east/north
values; their planar vorticity identities are not asserted on an ellipsoid.

Source spacing is refined 4/2/1 km, keeping 1-km target radii to 80 km and 96
angles fixed. Source extent is 110 km on either side, with fractional-cell
alignment (0.17, -0.23). Source and exact target winds are evaluated independently.
Every nonzero-radius target is required: loss of even one required value
invalidates its RMS rather than improving the score by dropping difficult points.
RMS/max component errors are pointwise, not area-weighted integrals.

Metrics distinguish peak absolute **azimuthal-mean tangential wind**, sampled RMW,
and maximum scalar speed on the required nonzero-radius target set. Means are
over launch angle, not area/circumference. RMW is the maximum absolute complete-
ring mean over the entire declared nonzero-radius search. An incomplete ring
makes that search unavailable; it is never silently narrowed. A maximum at a
search boundary is flagged, not established as a physical RMW. RMW errors use
truth on the same target radii, so a zero error is not proof of sub-kilometre
accuracy or perfect peak amplitude.

For each wind component, modes 1--3 use
:math:`c_m=N^{-1}\sum_j q_j e^{-im\theta_j}`. Complex and coefficient-amplitude
errors are retained even when phase is undefined. A non-Nyquist cosine's amplitude
is :math:`2|c_m|`, distinct from the reported coefficient amplitude. Phase is
compared only when both coefficients exceed 0.1 m/s; the strong-mode gate requires
truth amplitude at least 1 m/s. Lost strong phases cannot silently pass.
Incomplete rings are not zero-filled or fed into ordinary Fourier analysis.

Predeclared engineering gates require full analytical target coverage, vector
RMS improvement from 4 to 1 km, finest vector RMS below 0.5 m/s, sampled RMW
within one 1-km target interval, complex harmonic RMS below 0.25 m/s, and strong
peak-direction differences below 5 degrees. The broad 50-m/s wind scale and the
sharp jet's several-kilometre width motivate these experiment bounds; they are
not publication-derived cyclone thresholds or universal guarantees. Production
bilinear parity is checked on all six finest fixtures independently of which
candidate performs best.

Centre sweeps keep the asymmetric source field fixed and displace only the
analysis centre by 0/0.05/0.1/0.25 reference radii along north/east directions, at
4- and 1-km source spacing. Direct truth is recomputed about each displaced
centre. Radial wind and harmonic changes can be physically expected consequences
of centre choice; they are not all spurious interpolation leakage. All required
targets remain scored. Separate 16/32-angle cases compare their direct truth
coefficients with the 96-angle reference, distinguishing sampling differences
from interpolation error without claiming a continuum spectral oracle.
Synthetic clipped/independently masked U/V cases retain coverage differences
rather than claim better accuracy on reduced support.

Real-data pilot and artifacts
-----------------------------

``--ci`` selects instantaneous AROME U/V parameters 131/132 at 100/750 m above
ground in all five BATSIRAI files. Require m/s, exact recipe valid times, matching
grids and explicit ``uvRelativeToGrid=0`` flags. The stored source sphere is
recorded separately from WGS84 target/transport geometry. This is already
collocated, postprocessed geographic input, not validation of native C-grid
preparation or all model projections.

Four cases use a 60-km target, 1-km radii and 96 angles: fixed recipe centre;
prescribed longitude offsets -0.15/-0.075/0/+0.075/+0.15 degrees; fixed longitude
60.85 E exposing the cropped-input limit; and distinct synthetic U column gaps
``30+i:35+i`` and V row gaps ``20+i:23+i`` at recipe index ``i``. These are
sensitivity trajectories/gaps, not an optimal storm tracker or an observed coast
mask. Fixed/moving cases require complete common support. Other cases report
each method's valid count and common observed support. Native comparisons are
**differences from component bilinear**, not truth errors or evidence that real
radial wind is leakage. The original production path is also checked on the
first native snapshot at both heights. Source content hashes are verified again
at completion.

``comparison.json`` contains compact finest results, gates, environment/revision
and stage status. ``analytical/analytical.json`` retains full refinement,
centre/angular sweeps and coverage diagnostics. Six finest analytical NetCDF
files retain point truth. ``ci/ci.json`` and four optional CI NetCDF files retain
real-data comparisons and metadata. The ``wind_method`` dimension avoids
confusing methods with times or heights. Full-ring profiles and split real/imaginary
Fourier coefficients are independently readable with ordinary NetCDF tools.
The existing atomic writer's lossless default compression is used, without a
new precision/encoding requirement.

Weight-build, transport-build and field-application times and shared sparse-array
estimates are recorded. Bases share their spatial operator; their repeated build
diagnostics are not independent additive costs. Transport matrices are listed
separately. The process-lifetime RSS high-water mark includes imports/earlier
cases. Single-run first-use initialization is not a controlled performance
benchmark or a universal speedup claim.

Initial measured observations
----------------------------------------

A local run of code revision ``ef257b6`` in ``frameit_env`` (xESMF 0.9.2,
ESMPy 8.9.1) passed 408 analytical checks and all four native CI cases. At
1-km source spacing, component-wise bilinear had lower pointwise vector RMS
error than component-wise ESMF patch in all six manufactured fixtures:

.. list-table:: Selected finest-source vector RMS errors, in m/s
   :header-rows: 1

   * - Fixture
     - Bilinear components
     - Bilinear transport
     - Patch components
     - Patch transport
   * - Broad southern swirl
     - 0.005918
     - 0.005918
     - 0.011349
     - 0.011349
   * - Compact northern inflow
     - 0.036232
     - 0.036233
     - 0.070038
     - 0.070038
   * - Sharp lognormal eyewall
     - 0.086179
     - 0.086179
     - 0.167814
     - 0.167814

Patch's vector RMS was approximately 1.9 times bilinear's in these finest cases.
Transport changes were small and not consistently beneficial at the tested
regional resolutions. Individual phase/coefficient metrics were not uniformly
ordered, so this is not a claim that every metric favored the same method.
All finest sampled-RMW differences were zero on the 1-km target grid, while
the sharp case's peak mean tangential wind was underestimated by about 0.319 m/s
with bilinear and 0.653 m/s with patch. Thus agreement in sampled RMW does not
establish agreement in intensity or subgrid peak structure.

All candidates met the engineering gates, but meeting a gate is not evidence
of superiority. These results support retaining the current bilinear default
for this tested task; they do not establish general physical accuracy across
models, resolutions, noise regimes or grid conventions. Native CI comparisons
remain differences between reconstructions because no real-field truth was
supplied. Full numerical reports and point values are retained by the command,
rather than reducing the comparison to these selected examples.

Remaining gaps and review status
--------------------------------

All alternatives remain experimental. Representative native-model preparation,
noise sensitivity, wider regimes, independent scientific review, and a justified
production missing-data/default policy remain outstanding. No scalar conservation,
speed-norm identity, good plot or passing synthetic gate establishes momentum,
energy, vorticity/divergence preservation or general real-storm validity. A
default change requires evidence and explicit review beyond this comparison.
