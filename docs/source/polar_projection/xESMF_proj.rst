Polar projection with xESMF regridding
======================================

Request ``products.polar`` to sample selected fields around a fixed or moving
geographical centre. Set the radius, then choose spacing and a missing-data policy.
For a worked run, use :doc:`../task_guides/polar_sampling`.

Polar projection using xESMF
----------------------------

Targets use WGS84 forward geodesics from the continuous centre, not its snapped
extraction cell. ``radius`` is in kilometres; ``azimuth`` runs clockwise from
north in radians (0° north, 90° east, 180° south, 270° west).
`xESMF <https://xesmf.readthedocs.io/>`_ samples them as a LocStream of points.

Continuous fields default to bilinear sampling; categorical fields use
nearest-neighbour (``interpolation: nearest``, backend ``nearest_s2d``).
Kind must be established from evidence. These are point samples, not area averages.

Polar support is resolved independently of model-grid exports; no crop width or
model-grid product is needed. Selected preparation happens before sparse selection
removes neighbours. Levels are selected on each actual representation, without
exporting internal brackets. See :ref:`wind-grid-contract` for collocation,
rotation and W sampling. Model-grid transforms do not control polar preparation,
and field availability does not enable extra diagnostics.

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
Each requested source/product writes one dataset. Polar products contain:

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

The Python numerical APIs use ``rr``, ``theta`` and ``theta_deg``.
Those internal names are not the public product dimensions or chunk keys.

Alignment, native support and missing data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Each source uses its selected native sample clock and the declared region-centre
association. Different sources need not have identical timelines. Within a
sampling job, component/support fields must agree on their actual sample context.
Missing required centres or incompatible calendars fail under the selected policy,
not through silent nearest-time matching. See :doc:`../concepts/time_support`.

Source longitude/latitude are associated through named dimensions, not array shape.
Regional quadrilateral cells must be finite,
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

Zero filling occurs only inside the sparse multiply, followed by masking and
normalization; it never turns missing output into physical zero. This avoids
``0 * NaN`` poisoning exact-node samples. Weights at or below the absolute
zero-weight tolerance are removed before weighting and stencil checks; small
row-sum roundoff is normalized.

Speed samples each component with its declared policy, then takes magnitude.
Both must be valid; support is the minimum component fraction. Radial/tangential
methods instead use strict sampling and a joint finite U/V mask: holes in
different contributors both reduce joint support. They reject renormalization.
The low-level vector API uses its own declared joint-mask policy.

Support within ``2 * n * eps64`` of the threshold is accurately re-summed
(``math.fsum``), where ``n`` is the nonzero stencil size. The cutoff remains
``support >= threshold``: this is **not** acceptance slack. Complete stencils
have unit support; a threshold of one requires every contributor. Genuine
below-threshold support is rejected regardless of chunk/accumulation order.

These fractions describe **interpolation-weight support**, not area coverage or
conservation. The supported point methods are bilinear and nearest-neighbour
(``nearest_s2d`` in the backend); negative-weight/high-order methods need a
different support definition. Kind evidence selects the default method, not
failure of another method. There is no nearest-neighbour fallback.
Nearest-neighbour does not accept partial-stencil renormalization.
Nearest sampling is restricted to the ESMF spherical source-cell footprint,
using an additional geometry-only bilinear weight build, not a planar
longitude/latitude polygon test. This adds geometry work, not scalar payload reads.
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

Status 4 marks requested radial/tangential results at the origin; public U/V
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
See :doc:`../task_guides/scalars_and_vectors` for base-component declarations.
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
``radial_bearing`` are NaN. Component status is 4, validity and ring eligibility
are zero; joint support and geometric mapping evidence are retained separately.
Scalar values and horizontal speed can remain valid. Missing or misaligned
positive-radius bearing fails rather than using launch angle.

Results record ``wind_reference_frame="earth"``,
``vector_basis="terminal_forward_geodesic"``,
``origin_policy="undefined_at_zero_radius"`` and
``polar_support_definition="joint_finite_component_stencil"``.
They have outward/clockwise long names, not eastward/northward standard names.
``frameit_method_maturity="experimental_public_binding"`` marks the method's
qualification status, not stable scientific approval.

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
Independent numerical checks cover cardinal signs, joint masks, endpoint bearings
in both hemispheres/across the dateline, fixed/moving centres, unit/rotation
preparation and ordinary NetCDF/Zarr reopening. Cardinal dot products use a
binary64 absolute tolerance of 1e-12 m/s; compact synthetic readbacks use
2e-10 m/s. Neither is a real-producer accuracy estimate.

Geometry checks include Karney's published example and source-refined analytical
vortex sampling. The geometry follows Karney
(2013), DOI ``10.1007/s00190-012-0578-z``; the emphasis on radial-wind
contamination and centre sensitivity follows Ryglicki and Hodyss (2016), DOI
``10.1175/JAMC-D-15-0125.1``, and Zhao et al. (2019), DOI
``10.3390/atmos10060300``.

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
Start with default chunks/cache limits; tune only after measuring a representative
selection. Weight plans can be shared only for identical source/target geometry,
ordering, method, Earth model, numerical options and backend versions.
A fixed centre or equal array shape is insufficient.

Plans retain read-only geometry/weights, not field arrays or finite-data masks.
Each application recomputes field-specific support. An optional static binary
mask in the Python plan API excludes whole stencils and belongs to the geometry
signature.

.. code-block:: yaml

   processing:
     plan_cache: {entries: 8, max_bytes: 134217728}
     chunks: {radius: 32, azimuth: -1, time: 1}
     profile: false

This fragment belongs inside ``products.polar``. The default cache holds at most
eight plans and an estimated 128 MiB of
geometry/weight arrays. Oversized plans are applied without retention. Setting
either limit to zero disables plan retention and provides an
uncached baseline. Normalized source coordinates have a separate cache of
eight entries/8 MiB. Keep source files and lazy geometry unchanged throughout
execution.

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
These blocks bound interpolation output work as well as final Dask chunks.
Each task uses one cropped horizontal source plane per leading-dimension chunk,
not all times/levels. Unselected target chunks are not multiplied.

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

Reproducible computation benchmark
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Run cached and uncached workflows in fresh workers:

.. code-block:: bash

   python -m frameit.testing.polar_benchmark --output ./runs/polar-benchmark --repeats 2

Use a fresh/empty output directory. ``--data-root`` selects model inputs;
repeat ``--case`` to restrict workloads. The report separates input loading,
computation, weight building/application and export. Fresh workers isolate RSS
high-water marks; ``benchmark.json`` records versions, parameters and comparison
with uncached physical/quality outputs. Results apply to the measured workload,
not a universal speedup.
If the benchmark stops with an error, see :doc:`../troubleshooting`.

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
