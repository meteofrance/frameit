Polar projection with xESMF regridding
======================================

For the workflow, start with :doc:`../task_guides/polar_sampling`. This page
specifies target geometry, interpolation, coverage and numerical conventions.

Polar projection using xESMF
----------------------------

Purpose
~~~~~~~
FrameIt samples selected model fields on a polar grid around a declared
geographical centre. The outputs can be used for downstream radial/angular
analysis; selecting a field does not request additional diagnostics.

FrameIt resolves the required native support and any selected preparation before
sparse selection removes neighbours. It builds a geodesic target (``radius``,
``azimuth``) around the region's continuous centre and samples it with
`xESMF <https://xesmf.readthedocs.io/>`_. Polar input support is independent of
model-grid exports; no crop width or model-grid product is required.
The source's snapped extraction cell does not replace the declared centre.

See :ref:`wind-grid-contract` for the illustrated distinction between native
output and mass-point, eastward/northward analysis components, explicit input
declarations, W choices and level mappings. Cartesian representation choices
do not change polar sampling or tracking.

General strategy
~~~~~~~~~~~~~~~~
1. **Define the target polar grid**

   The target grid is parameterised by:

   - **radius** ``radius`` (km), from 0 to ``products.polar.radius_km``
   - **azimuth** ``azimuth`` (radians), with ``azimuth_degrees`` in degrees, clockwise from North:
     0° North, 90° East, 180° South, 270° West.
   - For each time step, the polar grid points are converted to geographic
     coordinates (lon, lat) using a forward geodesic mapping on the WGS84 ellipsoid.


2. **Interpolate fields onto the polar grid**

   - FrameIt uses xESMF in **LocStream output** mode, which treats the polar grid as a list of target points.
   - Proven continuous fields default to **bilinear**; proven categorical fields
     use nearest-neighbour. The public override is ``interpolation: nearest``;
     its xESMF method name is ``nearest_s2d``.

3. **Preserve time and vertical dimensions**

   - Horizontal sampling retains selected vertical levels. W-to-mass preparation,
     when selected, happens with native brackets available, before sparse subsetting.
   - The source's single level selector applies on each actual representation.
     Native neighbours needed for a remap stay internal, not extra exported levels.

Configuration
~~~~~~~~~~~~~
Enable polar projection
^^^^^^^^^^^^^^^^^^^^^^^
Request a polar product, rather than enabling a separate computation flag.
This fragment supplements a complete source request and region centre provider
such as :doc:`../task_guides/polar_sampling`:

.. code-block:: yaml

   products:
     polar:
       radius_km: 2

Define the polar grid geometry
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The product sets its physical radius and optional sampling. This fragment replaces
the preceding ``products`` mapping, using the instructional guide's centre/input:

.. code-block:: yaml

   products:
     polar:
       radius_km: 2
       radial_step_km: 1.5
       azimuth_count: 8
       processing:
         max_target_points: 2000000

Notes:

- The last radius is exactly ``radius_km``. Its preceding interval can be shorter
  than ``radial_step_km``; use actual coordinates for derivatives.
- ``azimuth`` contains exactly ``N`` samples at :math:`2\pi j/N`, with
  :math:`j=0,\ldots,N-1`. There is no duplicate endpoint at :math:`2\pi`.
- ``azimuth_count`` is the sole angular control and must be at least 3.
  Omission resolves ``N = max(3, ceil(2*pi*radius_km/dr_km))``, targeting the
  resolved radial spacing at the outer ring. For ``N=8`` the step is 45 degrees.
- Omitted ``radial_step_km`` uses supported native spacing. Finer requested
  spacing fails with its source evidence; denser points do not add resolution.
  Spacing uses the larger of the two horizontal-axis median distances, then
  the coarsest participating prepared grid/sample. The finer-spacing comparison
  permits only relative roundoff of :math:`10^{-12}`.
  ``shared_grid: true`` instead uses the coarsest participating native spacing
  when the step is omitted. Masks, vertical axes and time associations stay distinct.
- ``processing.max_target_points`` defaults to 2,000,000. The
  product of time count, radius count and angle count is checked before target
  coordinates are allocated. It bounds geometry points, not the memory of all
  variables and vertical levels. Increase it explicitly for a larger grid;
  the requested resolution is never silently reduced to satisfy the budget.

Storm tracking mode
^^^^^^^^^^^^^^^^^^^
Polar output reuses the region's centre provider:

- ``region.center`` supplies a fixed continuous geographical centre.
- ``region.track`` supplies centres from a trajectory.
- ``region.tracker`` computes centres from its required atmospheric inputs.

Moving centres change the target coordinates at each associated time. A fixed
centre alone does not prove that the source geometry or interpolation weights
are invariant. Only ``products.track: true`` requests a reusable trajectory file.

Selecting variables to project
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Source ``variables`` and ``derived`` declare available requests. Optional product
``fields`` narrows them by exact source name; unlisted fields/sources are excluded.
Unknown references fail, and needed internal inputs need not be exported.
This fragment replaces the region/products blocks of the complete instructional
scalar request, asking for both products:

.. code-block:: yaml

   region:
     center: {latitude: -20, longitude: 60}
     width_km: {x: 4, y: 4}
   products:
     model_grid: true
     polar:
       radius_km: 2
       radial_step_km: 1.5
       azimuth_count: 8
       fields: {atmosphere: [instructional_scalar]}

Omitted ``products`` requests only model-grid output. An explicit empty mapping
is invalid. A centre provider alone requests neither a track file nor polar output.
The applicable source or vertical-group selector applies to both products'
actual representations; see :ref:`explicit-vertical-groups`.

Output structure
~~~~~~~~~~~~~~~~
Public runs write one field dataset per requested source/product. A low-level
``polar_project`` call returns internal grouped datasets; group keys are not the
public filename contract. Polar products typically contain:

- Dimensions: ``time``, ``radius``, ``azimuth`` (plus each field's own vertical/member dimensions).
- Coordinates:

  - ``radius`` as the physical radius coordinate (km),
  - ``azimuth`` as launch azimuth (radians, clockwise from North),
  - ``azimuth_degrees`` as the degree representation of the launch azimuth,
  - ``radial_bearing(time, radius, azimuth)`` as the terminal-forward geodesic
    bearing, in radians clockwise from local north,
  - geographic longitude/latitude of target points (time-dependent for moving centres),
  - ``radial_spacing_km(radius)``: distance to the next radius, NaN at the last radius,
  - ``max_azimuthal_spacing_m(time, radius)``: maximum geodesic distance between
    cyclic neighbouring samples. This is a point-to-point distance, not a
    circumference arc length or an estimate of the source's effective resolution.

Metadata includes:

- Per-field ``polar_interpolation``, coverage policy and threshold for scalar/
  native component fields; JSON ``polar_component_options`` for derived winds.
- Actual preparation, selected source/centre times and native support in provenance.
- ``n_theta``, ``theta_closed=False``, ``theta_topology="uniform_periodic"``,
  requested/effective sampling settings and ``radial_spacing_uniform``.

The retained low-level numerical APIs use ``rr``, ``theta`` and ``theta_deg``.
Those internal names are not the public product dimensions or chunk keys.

Alignment, native support and missing data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Each source uses its selected native sample clock and the declared region-centre
association. Different sources need not have identical timelines. Within a
sampling job, component/support fields must agree on their actual sample context.
Missing required centres or incompatible calendars fail under the selected policy,
not through silent nearest-time matching. See :doc:`../concepts/time_support`.

Source longitude/latitude are broadcast and transposed using named
``y_box``/``x_box`` dimensions. Regional quadrilateral cells must be finite,
nondegenerate and consistently connected. Antimeridian coordinates are unwrapped
without reordering fields. NaN-padded model-domain edges are trimmed to the valid
rectangular footprint; missing coordinates inside that footprint are rejected,
not filled. Source and target latitude must be geographic latitude.

Model-grid output extent and polar input support are separate. Support is derived
from the polar target and needed native interpolation neighbours, not the exported
crop. The advanced ``products.polar.processing.source_halo_points`` adds native
support; its default is one. Insufficient configured support fails instead of
silently treating available neighbours as missing. At a true source boundary,
outside targets remain unmapped. The requested radius does not promise complete
source coverage; inspect the finite footprint and mapped fraction.

This fragment goes inside an existing ``products.polar`` mapping:

.. code-block:: yaml

   missing_data_policy: renormalize
   min_valid_weight_fraction: 0.75
   processing:
     weight_zero_tolerance: 1.0e-14
     source_halo_points: 1

``strict`` is the default: every contributing source value must be finite.
``renormalize`` enables valid-weight interpolation when its support fraction
reaches ``min_valid_weight_fraction``. All-missing stencils and unmapped points
remain NaN. The threshold applies only to renormalization and must be greater
than zero and no greater than one.

For nonnegative interpolation weights, let :math:`M_j` indicate finite source
data and :math:`s_i=\sum_jW_{ij}`. Valid-weight support is

.. math::

   c_i = \frac{\sum_j W_{ij}M_j}{s_i}, \qquad
   q_i^{\mathrm{renorm}} =
   \frac{\sum_j W_{ij}M_j q_j^{\mathrm{filled}}}{\sum_j W_{ij}M_j}.

Missing values are explicitly filled with zero only for the sparse multiply,
then masked/normalized according to policy. This avoids ``0 * NaN`` poisoning
an exact native-node sample. Coefficients at or below the declared absolute
zero-weight tolerance are removed before both weighting and stencil-validity
checks. Small row-sum roundoff is normalized. Public speed requests apply each
component's declared method/coverage policy, then take magnitude. Both sampled
components must be valid. Reported speed support is the minimum component support,
not a joint-stencil fraction. Explicit radial/tangential methods instead require
strict sampling with a joint finite U/V mask. A U hole and a V hole in different
contributors both reduce their joint support; it is not the minimum of separate
support fractions. Renormalization remains available for speed and other admitted
fields, but is not admitted for these experimental component methods.
The retained low-level vector API can apply its own declared joint-mask policy.

Partial-stencil support within ``2 * n * eps64`` of a renormalization threshold
is re-summed with Python's accurate ``math.fsum`` before the ordinary
``support >= threshold`` comparison; ``n`` is the nonzero stencil size. This
roundoff bound only selects sums to re-evaluate: it is **not** acceptance slack,
and a support fraction genuinely below the threshold remains rejected. Complete
stencils have exactly unit support; a threshold of one still requires every
contributor to be present. This removes borderline mask decisions caused by
floating-point accumulation/chunk order, not a change to the scientific cutoff.

These fractions describe **interpolation-weight support**, not area coverage or
conservation. The supported point methods are bilinear and nearest-neighbour
(``nearest_s2d`` in the backend); negative-weight/high-order methods need a
different support definition. Kind evidence selects the default method, not
failure of another method. There is no nearest-neighbour fallback.
Nearest-neighbour does not accept partial-stencil renormalization.
Nearest weights are restricted to the ESMF spherical source-cell footprint,
determined by an additional geometry-only bilinear weight build. This is not a
planar longitude/latitude polygon test. Its cost does not imply a scalar payload
read; retained-plan counts do not count every native weight constructor.
The sparse linear-map interpretation follows Ullrich and Taylor (2015), Section
2a, DOI ``10.1175/MWR-D-14-00343.1``.

Coverage and validity outputs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Every sampled field has the following additional data variables. They are
marked ``frameit_role="interpolation_quality"`` so analysis code can
distinguish them from physical quantities:

- ``<field>_geometry_mapped(time, radius, azimuth)``: this field's geometric
  mapping indicator,
- ``geometry_mapped``: intersection of all selected field geometry indicators,
  not a shared source mask or proof of valid contributors,
- ``<field>_support_fraction``: valid-weight support, including the field's
  time and vertical dimensions,
- ``<field>_interpolation_status`` and ``<field>_valid``: validity reason and
  valid-value indicator on the same dimensions as the physical field,
- ``<field>_ring_coverage``: fraction of valid launch-angle samples at each
  time, level and radius,
- ``<field>_full_ring_valid``: complete-ring mean/Fourier eligibility.

Status values are encoded with CF ``flag_values`` and ``flag_meanings``:

.. list-table:: Interpolation status
   :header-rows: 1

   * - Value
     - Meaning
   * - 0
     - Valid value
   * - 1
     - Unmapped geometry
   * - 2
     - Missing contributing source data
   * - 3
     - Insufficient valid-weight support for renormalization
   * - 4
     - Undefined radial/tangential component at zero radius

Status4 marks requested radial/tangential results at the origin; public U/V
selection alone does not request them. Scalar speed can be valid at zero radius.
Per-field geometry flags remain available when invalidity causes overlap.
For public speed, validity requires both sampled components; internal component
fields and their quality arrays are not exported unless requested separately.

Units and valid vertical auxiliaries/bounds survive source selection and export.
Horizontally varying scientific coordinates are sampled rather than copied from
the original grid. Source grid mappings, horizontal bounds/cell measures and
obsolete encodings are removed from point values. Source CRS information is
recorded as provenance. Target ellipsoid parameters and the distinction between
ellipsoidal target geodesics and ESMF's spherical interpolation geometry are
explicit in the output attributes.
Integer continuous bilinear inputs use floating evaluation to retain fractions;
native exports are unchanged. See :ref:`polar-numeric-types` for dtype provenance
and floating-point limits.

Azimuthal analysis
~~~~~~~~~~~~~~~~~~~~~
Scientific outputs contain an **endpoint-exclusive** angular axis. An ordinary
complete-ring mean or FFT therefore counts each direction once. The helpers
below validate a uniform open ring, preserve named vertical/time dimensions,
and invalidate rings containing missing or infinite field values:

.. code-block:: python

   from frameit.processing.polar import azimuthal_mean, periodic_fourier_coefficients

   field = polar_dataset["instructional_scalar"]
   radial_profile = azimuthal_mean(field, theta_dim="azimuth")
   coefficients = periodic_fourier_coefficients(field, theta_dim="azimuth")
   wave_one = coefficients.sel(azimuthal_wavenumber=1)

For an explicitly permitted valid-sector mean, request a lower coverage
threshold and retain its coverage/eligibility outputs:

.. code-block:: python

   from frameit.processing.polar import coverage_aware_azimuthal_mean

   partial = coverage_aware_azimuthal_mean(
       field, theta_dim="azimuth", minimum_coverage=0.75)
   profile = partial["azimuthal_mean"]
   coverage = partial["ring_coverage"]

The default threshold is 1.0 (complete rings). Partial means do not reconstruct
unobserved sectors and can be biased relative to full-ring means. A retained
positive half of a cosine ring, for example, averages near :math:`2/\pi`, not
zero. Ordinary Fourier analysis still requires complete rings. Fischer et al.
(2022), Section 3b, DOI ``10.1175/MWR-D-21-0223.1``, provides an example of
explicit coverage screening; its study-specific 50-percent criterion is not
adopted as a universal threshold here.

The mean is an average over **launch angle**. On an ellipsoid it is not exactly
a circumference-weighted mean, and it is not an area-weighted annulus mean.
Fourier coefficients use the clockwise-from-north convention:

.. math::

   c_m = \frac{1}{N}\sum_{j=0}^{N-1}q(\theta_j)e^{-im\theta_j}.

For :math:`A\cos[m(\theta-\theta_0)]`, a positive non-Nyquist coefficient is
:math:`c_m=(A/2)e^{-im\theta_0}`. Its cosine amplitude is :math:`2|c_m|` and
its peak direction is :math:`-\arg(c_m)/m` modulo :math:`2\pi/m`. DC and the
even-grid Nyquist coefficient are not doubled; vanishing coefficients have no
meaningful phase. Both positive and negative integer modes are returned.
Dask fields require a single angular chunk (``field.chunk({"azimuth": -1})``)
for Fourier analysis. Irregular directions supplied to ``PolarLonLatGrid``
are labelled ``directional_samples`` and rejected by these ordinary ring
diagnostics. Missing sectors are not zero-filled or silently partially averaged.

``finalize_polar_output(dataset)`` verifies a closed file's
duplicate column before removing it. An inconsistent endpoint raises an
error; do not blindly remove the last column from every file. A
nonuniform angular grid remains directional sampling after endpoint removal
and needs resampling before ordinary Fourier analysis.
That low-level helper uses its retained ``theta`` naming; it is not needed to
open a public endpoint-exclusive product.

.. _explicit-polar-wind-methods:

Derived wind components
~~~~~~~~~~~~~~~~~~~~~~~
Select ``radial_wind`` or ``tangential_wind`` through source ``derived``, with
explicit ``u``/``v`` source references and a user-chosen output alias.
The public binding is **experimental**, polar-only, and admits atmospheric AROME
GRIB/NetCDF or Meso-NH NetCDF, not FA or ocean currents.
See :doc:`../task_guides/scalars_and_vectors` for a request.
Selecting U/V alone does not request either component; selecting one component
does not export its sibling, speed or internal-only inputs.

Inputs require continuous-kind evidence, compatible velocity units, time support,
levels, basis and rotation metadata. Existing preparation collocates admitted
native grids, converts to m s-1 and rotates to physical east/north. Both inputs
must then share the same grid, interpolation and sampling settings. A single
paired stencil uses the joint finite U/V mask before the retained dot-product
operation. Only strict missing-data policy is admitted; no fallback or motion
subtraction is applied.

- ``radial_wind``: positive **outward** from the centre.
- ``tangential_wind``: positive **clockwise in both hemispheres**, not automatically
  cyclonic. ``vrad`` and ``vtan`` are example aliases, not reserved output names.

The components are derived from the **local terminal-forward bearing**
``radial_bearing`` (denoted :math:`\alpha` below), not from the launch
azimuth :math:`\theta`. These angles generally differ on a curved Earth:

.. math::

   v_\mathrm{rad} = u \sin\alpha + v \cos\alpha

   v_\mathrm{tan} = u \cos\alpha - v \sin\alpha

At zero radius the direction is undefined: both requested components and
``radial_bearing`` are NaN. Component status is4, validity and ring eligibility
are zero; joint support and geometric mapping evidence are retained separately.
Scalar values and horizontal speed can remain valid. Missing or misaligned
positive-radius bearing fails rather than using launch angle.

Results record ``wind_reference_frame="earth"``,
``vector_basis="terminal_forward_geodesic"``,
``origin_policy="undefined_at_zero_radius"`` and
``polar_support_definition="joint_finite_component_stencil"``.
They have outward/clockwise long names, not eastward/northward standard names.
``frameit_method_maturity="experimental_public_binding"`` distinguishes this
interface from stable scientific qualification. The binding reuses the retained
equations and geometry; it adds explicit selection and strict admission limits.

The numerical vector method and public derived speed use collocated
eastward/northward components (U positive eastward, V positive northward).
A separately requested native component instead preserves its own basis/units.
Preparation and the independent vertical W interface/mass
choice are explained once in :ref:`wind-grid-contract`.

All trackers supplying continuous longitude/latitude centres define the polar
origin at those coordinates. Integer extraction indices do not snap the polar
origin. A declared fixed centre stays fixed. Public coordinates
``center_longitude``, ``center_latitude`` and separate ``center_time`` record
the associated geometry; attributes describe the actual Earth model.

``wind_speed`` is the magnitude of the interpolated, collocated components,
not an interpolation of native scalar speed. Speed-only requests load the
required wind pair internally and omit internal-only components from exported
products. Velocity units are normalized to metres per second.

Wind reference frame
~~~~~~~~~~~~~~~~~~~~
Polar positions are centred on the requested location. Prepared eastward/
northward winds remain **Earth-relative**; native component exports retain their
recorded basis. Neither is made storm-relative by moving the target.
Neither sampling on a moving grid nor expressing the wind in radial/tangential
directions subtracts storm translation. See :ref:`wind-component-directions`
for an example. For pair-specific frame validation and
declared rotation methods, see :doc:`/user_guide/configuration_file`; source
references are in :doc:`/user_guide/input_files`. A declaration must agree with
available GRIB component flags and CF metadata; no silent frame/method fallback
is permitted. See :ref:`wind-preparation-method` for numerical conventions and
qualification limits.

Numerical verification
~~~~~~~~~~~~~~~~~~~~~~
``python -m pytest src/frameit/testing/numerical/test_v3_polar_components.py``
checks public selection, joint masks, cardinal signs, endpoint bearings in both
hemispheres across the dateline, fixed/moving centres, selected NetCDF/GRIB reads,
units/rotation, and ordinary NetCDF/sharded-Zarr readback. Cardinal dot products
use a binary64 absolute tolerance of 1e-12 m/s; synthetic public readbacks use
2e-10 m/s. These compact numerical checks are not real-producer qualification.

``python -m pytest src/frameit/testing/numerical/test_polar_wind.py src/frameit/testing/numerical/test_wind_collocation.py``
checks Karney's published geodesic example, endpoint-bearing radial leakage,
cardinal signs, origin handling, continuous centres, wind frame/unit conversion,
native affine-field collocation, sparse W selections and real-xESMF vortex
sampling with a source-grid refinement check. The geometry follows Karney
(2013), DOI ``10.1007/s00190-012-0578-z``; the emphasis on radial-wind
contamination and centre sensitivity follows Ryglicki and Hodyss (2016), DOI
``10.1175/JAMC-D-15-0125.1``, and Zhao et al. (2019), DOI
``10.3390/atmos10060300``.

``src/frameit/testing/numerical/test_polar_contracts.py`` and
``src/frameit/testing/numerical/test_polar_coverage.py`` additionally
exercise exact time alignment, finite footprints, dateline connectivity, changing
source geometry, CF auxiliary/bounds retention through loading and extraction,
weight-based missing-data oracles, joint vector masks, partial-ring eligibility,
lazy/eager equivalence and NetCDF validity metadata with the actual backend.

The references above and :ref:`wind-preparation-method` describe the retained
geometry/preparation conventions. Publication and community-use evidence for
stable promotion of this public binding remain unresolved; passing numerical
tests is not scientific sign-off or validation for every dataset or regime.

Known limitations and caveats
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Interpolation and physical interpretation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
- **Bilinear interpolation is not conservative**, it is appropriate for smoothly varying fields but can smooth sharp gradients.
- Values at target points outside the source domain are set to **NaN** (unmapped points).
- Close to the storm centre (small radii), the polar sampling can become relatively dense in azimuth compared to the effective source grid spacing, depending on your chosen resolutions.

Grid geometry constraints
^^^^^^^^^^^^^^^^^^^^^^^^^
- ``products.polar.radius_km`` sets the target extent independently of a model-grid
  crop. Actual source coverage and interpolation support still limit valid values.
- The polar grid is computed using WGS84 geodesics, which is robust at regional scales, but it remains a sampling of geographic coordinates, not a true conformal map projection.

Performance
~~~~~~~~~~~
``PolarRegridPlan`` separates geometry-owned weights from field application.
Compatible groups and variables share a plan. Across time, reuse requires
identical source and target geometry; a fixed origin alone is not sufficient.
Moving workloads process all groups at one instant before advancing time, so
even a small cache can share a moving-grid plan across those groups.

The in-memory LRU key includes canonical source/target coordinates, ordering,
polar axes, method, periodic/extrapolation options, zero-weight tolerance,
target Earth-model assumptions and backend versions. Shapes or group names
alone never authorize reuse. Plans own read-only geometry snapshots and retain
no field arrays, finite-data masks or valid-weight denominators. Every
application recomputes field-specific support (or the low-level API's joint
vector mask). An optional
static binary source mask at the plan API excludes whole contributing
stencils and is part of the geometry signature.

.. code-block:: yaml

   processing:
     plan_cache: {entries: 8, max_bytes: 134217728}
     chunks: {radius: 32, azimuth: -1, time: 1}
     profile: false

This fragment belongs inside ``products.polar``. The default cache holds at most
eight plans and an estimated 128 MiB of
geometry/weight arrays. Oversized plans are applied without retention. Setting
either limit to zero disables plan retention and provides an
uncached baseline. Normalized source coordinates have a separate small cache
(eight entries, at most 8 MiB). NumPy coordinates are content-fingerprinted;
Dask geometry uses immutable graph tokens to avoid repeatedly loading the
same arrays. Files and lazy geometry sources must remain unchanged while
execution is in progress, as required by the input inventory contract.

These limits bound cache-owned arrays, not total process memory: field outputs,
native backend allocations and pending Dask graphs can retain additional
references. Eviction never invalidates a previously returned lazy result.
There is no automatic disk-weight persistence or shape-derived filename reuse.

Dask field data remain lazy. Backend output blocks default to at most 32
radial rings with the complete angular axis, avoiding tiny LocStream chunks
inferred from the source's horizontal layout. ``products.polar.processing.chunks`` can
override ``radius``, ``azimuth`` and relevant leading dimensions such as ``time``,
``level`` or ``height_above_ground``. Use inventory-qualified names when axes
collide; see :ref:`model-grid-coordinate-names`. Sizes are positive integers or
-1 for a whole axis. A key must match a requested product, not every source.
Unknown dimensions fail clearly. NumPy inputs stay eager.
An explicit angular split still needs consolidation before ordinary Fourier
analysis. Output chunking changes storage/computation layout, not the operator.
CSR target rows are partitioned before multiplication, so these radial blocks
bound executed interpolation outputs as well as final Dask chunks. Each task
uses one cropped horizontal source plane per existing leading-dimension chunk;
it does not combine all times or levels. Selecting a subset of target chunks
does not multiply the unselected target rows.

The projection report includes cache builds, hits, evictions, retained-array
estimates and geometry signatures. In YAML runs,
``products.polar.processing.profile: true`` also records cache-operation timings,
unique Dask task count and the process-lifetime RSS high-water mark. With false,
optional measurements are unmeasured, not zero; cache activity counters remain.
Reused caches distinguish timed calls from earlier unmeasured calls.

Timings cover eager work or Dask graph construction, not later lazy
materialization or export. Graph inspection does not compute physical fields.
RSS includes previous imports/loading, not an incremental interpolation-only
memory measure. Direct low-level cache calls retain timing by default.

For callers reusing a cache across repeated invocations:

.. code-block:: python

   from frameit.processing.polar import PolarRegridPlanCache
   from frameit.processing.polar.polar_proj import polar_project

   cache = PolarRegridPlanCache(maxsize=8, max_bytes=128 * 1024**2)
   output, report = polar_project(source_groups, conf=conf, track=track, plan_cache=cache)

Scientific equivalence and cache lifetime are covered by the packaged
``test_polar_regrid_plan.py`` and ``test_polar_dask.py`` tests. These check
constant preservation, nonnegative weights, linearity for fixed masks,
geometry/mask/backend invalidation, moving-group reuse, eviction, per-field
mask changes and lazy/eager agreement under multiple chunk layouts.

Reproducible computation benchmark
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Run cached and uncached workflows in fresh workers:

.. code-block:: bash

   python -m frameit.testing.polar_benchmark --output ./runs/polar-benchmark --repeats 2

The output directory must be fresh or empty. ``--data-root`` selects full-domain
model inputs; repeated ``--case`` options restrict workloads. The default CI
workloads include fixed AROME/MNH runs, moving MNH tracking and a small explicit
continuous-origin AROME track within the frozen fixture. Input preloading,
computation, weight construction/application and NetCDF export timings are
reported separately. Fresh workers isolate RSS high-water marks; the driver
verifies all physical and quality outputs against the uncached
operator and stores versions, parameters and results in ``benchmark.json``.

A single local CI run observed weight-build reductions of 3 to 1 for fixed
AROME, 2 to 1 for fixed MNH, 6 to 3 for moving MNH and 15 to 5 for continuous
AROME origins. All numerical differences were zero. Projection wall-time
ratios were approximately 1.05, 1.00, 1.01 and 1.25 respectively: application
work dominates these small fixtures. These are measured examples, not a
universal speedup claim or a brittle timing threshold. Use repeated runs and
the recorded environment/memory breakdown for larger workloads.

Software dependencies
~~~~~~~~~~~~~~~~~~~~~
- Polar projection requires **xESMF** and its backend dependencies (typically ESMF/esmpy). Ensure your FrameIt environment provides a working xESMF installation.

Recommendations for robust usage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- Choose ``products.polar.radial_step_km`` comparable to, or coarser than,
  the native horizontal resolution of your input fields.
- Check ``max_azimuthal_spacing_m`` and the effective angular step against the
  scales and azimuthal modes you want to analyse. Fine target spacing does not
  create finer resolved source information. Resolving a band-limited mode
  :math:`m` needs at least :math:`N>2m`; unresolved higher modes can still alias
  into lower ones. Bilinear interpolation is not a specified antialiasing
  filter for coarse angular sampling.

Troubleshooting
~~~~~~~~~~~~~~~
- **No output produced**

  - Check that ``products.polar`` requests the intended declared fields/sources.
  - Inspect the product filter, centre coverage and run's actual publication status.

- **Many NaNs on the polar grid**

  - Inspect geometry mapping, contributing-data support and the field's status flags.
  - Check the requested radius against the actual source coverage and required halo.
    Enlarging only a model-grid export does not change polar support.

- **ImportError for xESMF**

  - Confirm xESMF and its backend are installed in the active environment used to run FrameIt.


For a runnable analytical example and standalone output plot, see
:doc:`../task_guides/polar_sampling`.
