Polar projection with xESMF regridding
======================================

Polar projection using xESMF
----------------------------

Purpose
~~~~~~~
FrameIt can regrid selected model fields onto a storm-centred polar grid defined by radius and azimuth. This is useful to compute azimuthal means, radial profiles, tangential and radial components, and to compare structures consistently along a track.

FrameIt prepares analysis winds while native collocation neighbours are
available, then extracts analysis fields on a storm-centred Cartesian box
(``x_box``, ``y_box``). It builds a geodesic polar target grid (``rr``, ``theta``)
around the supplied continuous centre and interpolates the selected fields
using `xESMF <https://xesmf.readthedocs.io/>`_. The extraction centre cell is
used when no continuous centre is supplied.

See :ref:`wind-grid-contract` for the illustrated distinction between native
output and mass/Earth analysis winds, explicit input declarations, W choices,
level mappings. Cartesian representation choices do not change polar sampling
or tracking.

General strategy
~~~~~~~~~~~~~~~~
1. **Define the target polar grid**

   The target grid is parameterised by:

   - **radius** ``rr`` (km), from 0 to half the smaller ``domain.size_km`` width
   - **azimuth** ``theta`` (radians), with ``theta_deg`` in degrees, clockwise from North:
     0° North, 90° East, 180° South, 270° West.
   - For each time step, the polar grid points are converted to geographic
     coordinates (lon, lat) using a forward geodesic mapping on the WGS84 ellipsoid.


2. **Interpolate fields onto the polar grid**

   - FrameIt uses xESMF in **LocStream output** mode, which treats the polar grid as a list of target points.
   - Default interpolation is **bilinear**; ``nearest_s2d`` is an explicit alternative.

3. **Preserve time and vertical dimensions**

   - Horizontal sampling retains selected vertical levels. W-to-mass preparation,
     when selected, happens with native brackets available, before sparse subsetting.
   - Polar requests inherit extraction-level selections; they do not select
     additional vertical levels at this stage.

Configuration
~~~~~~~~~~~~~
Enable polar projection
^^^^^^^^^^^^^^^^^^^^^^^
Set the following flag in the YAML configuration:

.. code-block:: yaml

  polar:
    enabled: true

Define the polar grid geometry
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The polar grid is derived from the extracted storm-centred box size and the requested polar resolution:

.. code-block:: yaml

  domain:
    size_km: {x: 100, y: 100}  # Full widths in kilometres
  polar:
    enabled: true
    radial_step_m: 5000       # Metres; omission means resolved native spacing
    azimuth_step_deg: 2       # Optional maximum angular step in degrees
    # azimuth_count: 180      # Alternative; omit azimuth_step_deg when using count
    max_points: 2000000       # Geometry budget across all output times

Notes:

- The last radius includes ``rmax_km``. Its preceding interval can be shorter
  than ``polar.radial_step_m`` converted to km; use actual coordinates for derivatives.
- ``theta`` contains exactly ``N`` samples at :math:`2\pi j/N`, with
  :math:`j=0,\ldots,N-1`. There is no duplicate endpoint at :math:`2\pi`.
- An explicit angular step selects ``N = ceil(360 / step_deg)``. For example,
  7 degrees produces 52 uniformly spaced angles with an effective step of
  approximately 6.923 degrees, including the seam interval.
- ``polar.azimuth_count`` must be an integer of at least 3. Count and step are
  mutually exclusive in YAML schema version 2.
- Omitting both angular options, or setting both to null, selects
  ``N = max(3, ceil(2*pi*rmax_km/dr_km))``. This targets radial spacing at the
  outer ring, without a one-degree floor. The previous implicit 10-degree
  default is replaced by this automatic rule; explicitly setting 10 degrees
  retains that sampling choice, with 36 analytical angles.
- ``polar.max_points`` is a positive integer, defaulting to 2,000,000. The
  product of time count, radius count and angle count is checked before target
  coordinates are allocated. It bounds geometry points, not the memory of all
  variables and vertical levels. Increase it explicitly for a larger grid;
  the requested resolution is never silently reduced to satisfy the budget.

Storm tracking mode
^^^^^^^^^^^^^^^^^^^
The behaviour differs depending on the tracking method:

- ``tracking.method: fixed_box``
  - The storm centre is taken at the first time step and kept fixed, the same polar grid is reused for all times.

- Any other tracking method ``wind_pressure, prescribed_track...``
  - The storm centre can move in time, the polar grid is recomputed for each time step.

Selecting variables to project
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Polar projection is applied to ``polar.variables``, organized by the same native
groups as extraction outputs. Explicit selections must be subsets of extracted variables.

Example:

.. code-block:: yaml

  polar:
    variables:
      surface:
        names: [prmsl, u10, v10]
      isobaricInhPa:
        names: [u, v]

Shortcut to project all extracted variables:

.. code-block:: yaml

  polar:
    variables: all

Important behaviour:

- Vertical selection belongs only under ``variables``; polar selections inherit it.
- Dataset preflight checks selected fields; per-file gaps remain visible in the inventory.

Output structure
~~~~~~~~~~~~~~~~
The polar-projected datasets are returned as a dictionary of xarray datasets, keyed by group. Each dataset typically contains:

- Dimensions: ``time``, ``rr``, ``theta`` (plus any vertical dimensions present in the source data).
- Coordinates:

  - ``rr`` as the physical radius coordinate (km),
  - ``theta`` as launch azimuth (radians, clockwise from North),
  - ``theta_deg`` as the degree representation of the launch azimuth,
  - ``radial_bearing(time, rr, theta)`` as the terminal-forward geodesic
    bearing, in radians clockwise from local north,
  - ``lon`` and ``lat`` of the polar grid points (time-dependent if the centre moves),
  - optional diagnostics: ``x_km`` and ``y_km`` (Cartesian offsets in km).
  - ``radial_spacing_km(rr)``: distance to the next radius, NaN at the last radius,
  - ``max_azimuthal_spacing_m(time, rr)``: maximum geodesic distance between
    cyclic neighbouring samples. This is a point-to-point distance, not a
    circumference arc length or an estimate of the source's effective resolution.

Metadata includes:

- ``polar_proj_backend = "xesmf"``
- ``polar_proj_method`` (for example ``"bilinear"``)
- provenance of requested, source, and output groups.
- ``n_theta``, ``theta_closed=False``, ``theta_topology="uniform_periodic"``,
  requested/effective sampling settings and ``radial_spacing_uniform``.

Alignment, native support and missing data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The required time axis comes from the surface group, or the first source group
when surface is absent. It must have unique, increasing labels. Every source
group must contain exactly those times; differently ordered groups are selected
by label. Missing, duplicate, extra group times and incompatible calendars raise
an error. Track positions must cover the required times; unused extra track
positions are counted in the projection report.

Source longitude/latitude are broadcast and transposed using named
``y_box``/``x_box`` dimensions. Regional quadrilateral cells must be finite,
nondegenerate and consistently connected. Antimeridian coordinates are unwrapped
without reordering fields. NaN-padded model-domain edges are trimmed to the valid
rectangular footprint; missing coordinates inside that footprint are rejected,
not filled. Source and target latitude must be geographic latitude.

Cartesian output extent and polar input support are separate. The runner adds
``polar.source_halo_points`` native points to the actual rounded extraction
half-widths before polar interpolation. The default is one point. Cartesian
products retain their configured extent. At a true model boundary, unavailable
targets remain unmapped; the requested radius is not assumed to have complete
source coverage. The report records the finite source footprint and mapped
fraction at every time/radius. Increase the halo explicitly when the model's
geometry requires more support.

.. code-block:: yaml

   polar:
     missing_data_policy: strict
     min_valid_weight_fraction: 0.5
     weight_zero_tolerance: 1.0e-14
     source_halo_points: 1
     ellipsoid: WGS84

``strict`` is the default: every contributing source value must be finite.
``renormalize`` explicitly enables valid-weight interpolation, provided its
support fraction reaches ``polar.min_valid_weight_fraction``. All-missing
stencils and unmapped points remain NaN even if the threshold is zero. The
threshold applies only to the renormalized policy.

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
checks. Small row-sum roundoff is normalized. U/V requested together use the
same joint finite-data mask and denominator; independently normalized component
stencils are not used to form a vector.

These fractions describe **interpolation-weight support**, not area coverage or
conservation. The current supported point methods are ``bilinear`` and explicit
``nearest_s2d``; negative-weight/high-order methods need a different support
definition. The default is bilinear; there is no nearest-neighbour fallback.
The sparse linear-map interpretation follows Ullrich and Taylor (2015), Section
2a, DOI ``10.1175/MWR-D-14-00343.1``.

Coverage and validity outputs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Every sampled field has the following additional data variables. They are
marked ``frameit_role="interpolation_quality"`` so plotting/analysis code can
distinguish them from physical quantities:

- ``geometry_mapped(time, rr, theta)``: geometric mapping indicator, shared by
  fields using the same source footprint,
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

The zero-radius vector status is distinct from mapping coverage. Scalar speed
may be valid there while radial/tangential components are undefined. The shared
geometry flag remains available when more than one invalidity cause applies.
Derived wind diagnostics inherit their joint vector support; internal speed-only
dependencies and their quality arrays are removed from output.

Units and valid vertical auxiliaries/bounds survive source selection and export.
Horizontally varying scientific coordinates are sampled rather than copied from
the original grid. Source grid mappings, horizontal bounds/cell measures and
obsolete encodings are removed from point values. Source CRS information is
recorded as provenance. Target ellipsoid parameters and the distinction between
ellipsoidal target geodesics and ESMF's spherical interpolation geometry are
explicit in the output attributes.

Analysis and plotting
~~~~~~~~~~~~~~~~~~~~~
Scientific outputs contain an **endpoint-exclusive** angular axis. An ordinary
complete-ring mean or FFT therefore counts each direction once. The helpers
below validate a uniform open ring, preserve named vertical/time dimensions,
and invalidate rings containing missing or infinite field values:

.. code-block:: python

   from frameit.processing.polar import azimuthal_mean, periodic_fourier_coefficients

   radial_profile = azimuthal_mean(polar_dataset["vtan"])
   coefficients = periodic_fourier_coefficients(polar_dataset["vtan"])
   wave_one = coefficients.sel(azimuthal_wavenumber=1)

For an explicitly permitted valid-sector mean, request a lower coverage
threshold and retain its coverage/eligibility outputs:

.. code-block:: python

   from frameit.processing.polar import coverage_aware_azimuthal_mean

   partial = coverage_aware_azimuthal_mean(polar_dataset["vtan"], minimum_coverage=0.75)
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
Dask fields require a single angular chunk (``field.chunk({"theta": -1})``)
for Fourier analysis. Irregular directions supplied to ``PolarLonLatGrid``
are labelled ``directional_samples`` and rejected by these ordinary ring
diagnostics. Missing sectors are not zero-filled or silently partially averaged.

Close a separate view only when plotting requires a cyclic endpoint:

.. code-block:: python

   from frameit.viz import close_theta_for_plot, setup_geodesic_polar_ax

   plot_view = close_theta_for_plot(polar_dataset.isel(time=0, level=0))
   plot_view["vtan"].plot.contourf(ax=ax, x="theta", y="rr")
   setup_geodesic_polar_ax(ax)

Plot closure is idempotent and does not modify the analytical dataset. It
checks actual endpoint coordinates and angular values, including auxiliary
coordinates such as ``radial_bearing``, rather than trusting an attribute.
``close_theta`` remains a compatibility alias for this plotting helper.

For older closed files, ``finalize_polar_output(dataset)`` verifies the
duplicate column before removing it. An inconsistent endpoint raises an
error; do not blindly remove the last column from every file. A legacy
nonuniform angular grid remains directional sampling after endpoint removal
and needs resampling before ordinary Fourier analysis.

Derived wind components
~~~~~~~~~~~~~~~~~~~~~~~
If the zonal (``u``) and meridional (``v``) wind components are included in
``polar.variables``, FrameIt automatically computes the radial and tangential
wind components on the polar grid and adds them to the output dataset:

- ``vrad``: radial wind component, positive **outward** from the storm centre.
- ``vtan``: tangential wind component, positive for **clockwise** rotation.

The components are derived from the **local terminal-forward bearing**
``radial_bearing`` (denoted :math:`\alpha` below), not from the launch
azimuth ``theta``. These angles generally differ on a curved Earth:

.. math::

   v_\mathrm{rad} = u \sin\alpha + v \cos\alpha

   v_\mathrm{tan} = u \cos\alpha - v \sin\alpha

Diagnostics are generated for groups containing the configured wind pair;
surface winds use the separate 10-m aliases. At zero radius, the radial
direction is undefined: ``vrad``, ``vtan`` and ``radial_bearing`` are NaN,
while scalar values and horizontal speed remain available.

Polar horizontal winds use collocated Earth-relative components on ``rr`` /
``theta``. Their preparation and the independent vertical W interface/mass
choice are explained once in :ref:`wind-grid-contract`.

All trackers supplying continuous longitude/latitude centres define the polar
origin at those coordinates. Integer extraction indices do not snap the polar
origin. Fixed-box mode freezes the initial origin. Output coordinates
``center_lon``, ``center_lat`` and (for extracted boxes) ``center_grid_offset_m``
record this geometry, and attributes describe the actual Earth model.

``wind_speed`` is the magnitude of the interpolated, collocated components,
not an interpolation of native scalar speed. Speed-only requests load the
required wind pair internally and omit internal-only components from exported
products. Velocity units are normalized to metres per second.

Wind reference frame
~~~~~~~~~~~~~~~~~~~~
Polar positions are storm-centred, but velocities remain **earth-relative**;
no storm translation is subtracted. For pair-specific frame validation and
declared rotation methods, see :doc:`/user_guide/configuration_file`; source
references are in :doc:`/user_guide/input_files`. A declaration must agree with
available GRIB component flags and CF metadata; no silent frame/method fallback
is permitted. See :ref:`wind-preparation-method` for numerical conventions and
qualification limits.

Numerical verification
~~~~~~~~~~~~~~~~~~~~~~
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


Known limitations and caveats
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Interpolation and physical interpretation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
- **Bilinear interpolation is not conservative**, it is appropriate for smoothly varying fields but can smooth sharp gradients.
- Values at target points outside the source domain are set to **NaN** (unmapped points).
- Close to the storm centre (small radii), the polar sampling can become relatively dense in azimuth compared to the effective source grid spacing, depending on your chosen resolutions.

Grid geometry constraints
^^^^^^^^^^^^^^^^^^^^^^^^^
- The maximum usable radius is limited by the extracted box size:
  ``rmax_km = 0.5 * min(domain.size_km.x, domain.size_km.y)``.
  If your need larger radii, increase the extraction box size accordingly.
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
application recomputes support, including the joint U/V mask. An optional
static binary source mask at the plan API excludes whole contributing
stencils and is part of the geometry signature.

.. code-block:: yaml

   polar:
     plan_cache: {entries: 8, max_bytes: 134217728}
     chunks: {rr: 32, theta: -1, time: 1}
     profile: false

The default cache holds at most eight plans and an estimated 128 MiB of
geometry/weight arrays. Oversized plans are applied without retention. Setting
either limit to zero disables plan retention and provides the corrected
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
inferred from the source's horizontal layout. ``polar.chunks`` can
override ``rr``, ``theta`` and relevant leading dimensions such as ``time``,
``level`` or ``heightAboveGround``. Sizes are positive integers or -1 for a
whole axis. Unknown output dimensions fail clearly. NumPy inputs stay eager.
An explicit angular split still needs consolidation before ordinary Fourier
analysis. Output chunking changes storage/computation layout, not the operator.

The projection report and ordinary execution result include
``regrid_performance``: plan builds, hits, evictions, retained-array estimates,
normalization/fingerprinting time, weight-construction time, field-application
time, and geometry signatures with row-sum/mapping diagnostics. Application
time is NumPy computation or Dask graph construction; it does not silently
include later lazy materialization. ``polar.profile: true`` additionally
records unique Dask task count and the process-lifetime RSS high-water mark.
Graph inspection does not compute physical fields. RSS includes previous
imports/loading and is not an incremental interpolation-only memory measure.

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
Run corrected cached and uncached workflows in fresh workers:

.. code-block:: bash

   python -m frameit.testing.polar_benchmark --output ./runs/polar-benchmark --repeats 2

The output directory must be fresh or empty. ``--data-root`` selects full-domain
model inputs; repeated ``--case`` options restrict workloads. The default CI
workloads include fixed AROME/MNH runs, moving MNH tracking and a small explicit
continuous-origin AROME track within the frozen fixture. Input preloading,
computation, weight construction/application and NetCDF export timings are
reported separately. Fresh workers isolate RSS high-water marks; the driver
verifies all physical and quality outputs against the corrected uncached
operator and stores versions, parameters and results in ``benchmark.json``.

A single local CI run observed weight-build reductions of 3 to 1 for fixed
AROME, 2 to 1 for fixed MNH, 6 to 3 for moving MNH and 15 to 5 for continuous
AROME origins. All numerical differences were zero. Projection wall-time
ratios were approximately 1.05, 1.00, 1.01 and 1.25 respectively: application
work dominates these small fixtures. These are measured examples, not a
universal speedup claim or a brittle timing threshold. Use repeated runs and
the recorded environment/memory breakdown for larger workloads.

The xESMF spherical point operator remains the numerical reference. A
native-CRS rectilinear interpolation path would require independent accuracy
tests because changing interpolation coordinates changes the operator.

Software dependencies
~~~~~~~~~~~~~~~~~~~~~
- Polar projection requires **xESMF** and its backend dependencies (typically ESMF/esmpy). Ensure your FrameIt environment provides a working xESMF installation.

Recommendations for robust usage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- Choose ``polar.radial_step_m`` (metres) comparable to, or slightly coarser than,
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
  - Check ``polar.enabled: true`` and that ``polar.variables`` selects extracted fields.
  - Ensure the requested group exists in the extracted outputs.

- **Many NaNs on the polar grid**
  - Adjust ``domain.size_km.x`` and ``.y`` to change the extraction extent and ``rmax_km``.
  - Verify the storm centre remains inside the extracted box for moving-centre configurations.

- **ImportError for xESMF**
  - Confirm xESMF and its backend are installed in the active environment used to run FrameIt.


Illustration
------------

Here is an illustration for the tropical cyclone CHIDO, first row shows the cartesian coordinates, the second one shows the polar coordinates.

.. figure:: ../_static/figures/Fig.cart_Chido.png
   :width: 80%
   :align: center

.. figure:: ../_static/figures/Fig.polar_Chido.png
   :width: 80%
   :align: center

   Example of polar projection.
