Multi-field vortex tracking
============================================================

``tracking.method: multifield_vortex`` selects an **experimental built-in
native-grid adaptation** of the ``ALL_NO_THICK`` configuration described by
`Marchok (2021), Important Factors in the Tracking of Tropical Cyclones in
Operational Models <https://doi.org/10.1175/JAMC-D-20-0175.1>`_. It follows one
researcher-seeded lower-tropospheric mass/circulation disturbance. It does not
classify tropical stages or identify genesis. Landfall does not itself terminate
tracking; the declared structure, support and continuity criteria do.

The nine estimates are MSLP; relative vorticity at the surface, 850 and 700 hPa;
geopotential height at 850 and 700 hPa; and wind circulation at the surface,
850 and 700 hPa. Winds at 500 hPa additionally support the next-position guess.
700-hPa contributions are relevant to mountainous crossings: Marchok reports
operational experience that these help when terrain interferes with lower layers.
This evidence is not a qualification of FrameIt's implementation for landfall.

Inputs and explicit conventions
------------------------------------------------------------

AROME requires ``prmsl``, ``u10``, ``v10``, ``u``/``v`` at 850, 700 and
500 hPa, and geopotential ``z`` at 850 and 700 hPa. The current adapter uses
``isobaricInhPa``. Geopotential is converted to geopotential height with
``g0 = 9.80665 m s-2``. A GRIB ``msl`` field is available through the canonical
``prmsl`` alias; the original source variable remains requestable by direct
loader callers. Every required GRIB variable/level/time combination is checked,
not just the union of levels shared by different variables.

Meso-NH requires native-level absolute pressure (``PABST`` or ``PRES``),
physical altitude (``ALT`` or the explicitly supported formula described in
:doc:`pressure_centroid`), horizontal winds, ``MSLP`` and ``UM10``/``VM10``.
One explicitly declared ``UT``/``VT`` or ``UT_ZM``/``VT_ZM`` pair selects the
native winds. The pressure-centroid adapter's supported field discovery and
native physical-level selection are reused. Invalid inputs produce multi-field
specific preparation instructions rather than the centroid's 2-km recipe.

MNH native pressure must bracket the required pressure surfaces in each usable
column. Wind and geometric altitude are interpolated linearly in log-pressure
between adjacent physical levels. Pressure must be positive and strictly
monotone in finite columns. Missing pressure coordinates invalidate the column;
missing bracket values remain missing. There is no below-ground or vertical
extrapolation. A pressure surface outside the available vertical range at every
column is an input error, not track loss.

MNH geometric altitude is not relabelled as geopotential height. Declare the
model's constant gravity via ``mnh_gravity_m_s2``; the adapter explicitly uses
``H = z_geometric * g_model / g0``. This is only applicable to an appropriate
constant-gravity model convention. The value in the example must be checked for
the simulation. Other conventions require a qualified adapter extension.
Existing MNH backup fields may supply all necessary information without
``LTPZH``; a file lacking absolute pressure cannot run this configuration.

Declare wind frames and any rotation with ``input.wind_pairs``. Collocation and
rotation precede pressure-level interpolation; physical east/north components
in m/s are required. No frame is inferred from a filename. Per-file MNH
preparation normalizes pressure/height/winds before concatenation so units cannot
silently inherit the first file's interpretation. Relative vorticity is derived
from those winds; MNH ``POVOT`` is not used as a substitute.

Only stationary regional structured grids, excluding poles and spanning less
than 180 degrees longitude, are supported. Existing extraction/grid-spacing
limits apply. Single-cycle GRIB files containing several forecast steps are
aligned on valid time; a two-dimensional cycle/lead-time axis requires an
explicit single-cycle selection.

Configuration
-------------

.. code-block:: yaml

   tracking:
     method: multifield_vortex
     multifield_vortex:
       profile: all_no_thick
       seed:
         latitude: -20.0
         longitude: 60.0
         time: null
         motion_u_m_s: 0.0
         motion_v_m_s: 0.0
       on_track_loss: stop
       mnh_gravity_m_s2: 9.80665

The seed position and initial eastward/northward motion must be explicitly
supplied; the zero motion above is an example, not an estimate from the data.
``seed.time: null`` declares that the seed applies to the first input timestamp;
a supplied ISO timestamp must match it. Times must be strictly increasing and
valid. A non-equatorial/nonpolar seed fixes the hemisphere convention; crossing
the equator terminates tracking. ``mnh_gravity_m_s2`` is required for MNH and is
unused for AROME. Only ``all_no_thick`` is currently supported.

``numerics`` controls (defaults):

* ``analysis_step_km: 25``: initial geodesic search spacing.
* ``refinement_km: 2.5``: final search spacing.
* ``max_iterations: 20``: search/refinement budget per parameter.
* ``minimum_support: 0.8``: minimum finite Barnes weight fraction, and finite
  node fraction for the 850-hPa disk-average QC.
* ``minimum_samples: 16``: minimum finite nodes for those calculations.

``quality`` controls (defaults):

* ``minimum_parameters: 2``: minimum number of accepted estimates; the MSLP and
  RV850 fixes must also be accepted for the structural/separation checks.
* ``pressure_rise_pa: 50``: minimum pressure rise from the composite centre to
  the mean of at least one quadrant of a 333-km ring.
* ``vt850_min_m_s: 1.5``: minimum cyclonic tangential wind, averaged over finite
  native nodes within 275 km (excluding the origin).
* ``max_separation_km: 425``: maximum MSLP/RV850 centre separation.
* ``max_speed_m_s: 30.866666666666667``: 60-kt translation limit.
* ``speed_check_interval_hours: 6``: minimum elapsed time between evaluated
  translation checks. Higher-frequency fixes do not trigger hourly speed checks.

Use ``frameit init arome --tracking multifield_vortex --full`` or the ``mesonh``
equivalent to generate all settings. Adapt seed, motion, source conventions and
paths before running. Examples are ``example/config_file/conf_multifield_arome.yml``
and ``example/config_file/conf_multifield_mnh.yml``.

Numerical method and domain support
-----------------------------------

Barnes values use ``sum(exp(-d**2/re**2)*F)/sum(exp(-d**2/re**2))`` at finite
native nodes, without an extra area weight. For nominal physical spacing divided
by 111194.9 m/degree, the e-folding radius is 60 km below 0.1 degree, 75 km below
1.26 degrees, and 150 km otherwise. The influence radius is 150/150/300 km.
Search radii are 150, 200, 300 and 350 km at breakpoints 0.1, 0.4 and 1.26 degrees.
Effective values are recorded by preflight and in the track metadata.

Each parameter starts with a bounded coarse search, followed by local 3x3
refinement/hill climbing. Flat objectives, unresolved support, a boundary optimum
or exhausted iteration budget reject the estimate. Circulation maximizes
``sum(Vt * 2*pi*r/24)`` on seven radii 35:30:215 km and 24 bearings offset by
7.5 degrees, with hemisphere-aware sign. Sampling uses the native quadrilateral
bilinear sampler and terminal-forward WGS84 vector basis. Every circulation arc
must have finite support; incomplete rings are not silently renormalized.

Relative vorticity uses second-order computational-index derivatives and the
geographic Jacobian to calculate the normal curl on the WGS84 ellipsoid:
``[M*dv/dlambda - d(N*cos(phi)*u)/dphi] / (M*N*cos(phi))``. ``M`` and ``N`` are
the ellipsoidal meridional and prime-vertical radii. Masks propagate and the
outermost nodes are excluded. Metrics are evaluated on the reference ellipsoid,
an approximation to the elevated pressure surface.

Regional-source rejection uses an initial 300-km limit, then
``clip(3.75*mean(previous three radial-error standard deviations), 225, 485)`` km.
Candidate errors within 485 km contribute to that history. Accepted longitudes
are unwrapped about the guess; their first mean is refined with weights
``exp(-distance_from_first_mean/(3*max(std(distance),5 km)))``. Standard deviations
use the sample convention. Dispersion is a diagnostic, not calibrated confidence.

The next-position guess averages the diagnosed model-motion vector and the
Barnes-smoothed steering vector. Initial motion comes from the seed. Steering
uses 850/700/500-hPa weights 0.25/0.50/0.25, a 500-km e-folding radius and a
**1000-km influence radius**. No steering layer is replaced or omitted. A valid
next-position estimate is required to accept a nonterminal requested timestamp.
This conservative rule means missing steering support can reject the initial
attempt, even if some individual centre estimates were obtainable.

The input domain must cover these stencils at the candidate/accepted positions;
the extraction box does not limit tracking input. Geographic disk support is
checked with 48 circumference samples; finite-data support is checked separately.
Preflight reports whether the seed has the full steering footprint. Field masks
and support at later positions are checked during execution. Raw 3-D fields are
evaluated one timestamp at a time; cached geometry and a short history are reused.

Track loss and outputs
----------------------

Malformed/missing required inputs fail explicitly. Dynamic QC or sampling loss
at the initial time also fails because no accepted track exists. Subsequently,
``on_track_loss: error`` raises; ``stop`` exports the accepted prefix and records
why/when tracking terminated. No positions are filled, extrapolated into output,
or labelled as detected after termination. Tracking may follow a weakening
remnant while its criteria remain satisfied; this is not tropical classification.

``lon``, ``lat``, nearest native ``cx``/``cy`` and kinematics retain their normal
``time`` dimension. ``attempt_time`` includes the final rejected attempt, and
``parameter`` names the nine estimates. Additional variables include per-parameter
longitude, latitude, categorical status and composite weight; accepted parameter
count; spread and exclusion radius; guess position; steering; pressure-rise,
850-hPa mean tangential wind, separation and evaluated translation speed.
Integer flags have ``flag_values``/``flag_meanings``. A missing translation speed
means its cadence criterion was not reached. A missing steering value at the
final requested time means no next-position estimate was needed.

Track attributes record maturity, reference revision, seed, controls, effective
radii and ``tracking_complete`` (0/1). Termination attributes and
``tracking_requested_time_count`` distinguish a shortened prefix from full
requested-time coverage. Run provenance retains resolved input requirements and
tracking summary. The Python execution result additionally exposes
``tracking_complete`` and ``tracking_termination_reason``; ``ok`` still describes
processing/export success under the selected policy. Existing extraction selects
only accepted times. The ordinary NetCDF writer/encodings are reused.

Method record and qualification gaps
------------------------------------

* **Quantity/maturity:** combined lower-tropospheric centre, experimental native
  implementation; synthetic verification, no independent scientific sign-off.
* **Primary reference/community use:** Marchok (2021), cited above, evaluates
  GFS/HWRF forecasts from the 2015-2017 Atlantic/eastern Pacific seasons and
  identifies ``ALL_NO_THICK`` as used in NWS operations in 2021.
* **Source inspected:** `NOAA-EMC/TC_tracker v1.3.0
  <https://github.com/NOAA-EMC/TC_tracker/tree/2aadeb97bef5bc1885631ff83ebb305ddcaca9eb>`_,
  ``gettrk_main_gfs.f`` (``find_maxmin``, ``get_wind_circulation``, ``fixcenter``)
  and ``gettrk_modules.f`` (radii, regional limits, steering weights). The source
  uses three prior standard deviations and a distance-weighted refinement of
  the mean, details more specific than the paper's description of a mean fix.
* **Inputs/equations/metadata:** specified above and recorded in effective YAML,
  track metadata and run provenance. No Fortran/NOAA backend is required at runtime.
* **Departures:** native quadrilateral/WGS84 geometry, ellipsoidal derivatives,
  log-pressure MNH preparation, a fixed physical initial search spacing,
  stricter complete circulation rings, explicit finite-support thresholds,
  mandatory MSLP/RV850 fixes, and a conservative quadrant-ring pressure QC.
  Initial-motion and steering advection is one-step geodesic vector averaging.
  These choices are inspectable adaptations, not a bitwise NOAA reproduction.
* **Independent verification:** analytic exponential pressure columns/affine
  fields (absolute height tolerance 1e-11 m in compact profiles); analytic
  ellipsoidal curl including warped grids; direct Gaussian-sum comparison
  (relative tolerance 1e-14); exact tangential-ring samples (relative tolerance
  1e-12); wrapping/outlier and cadence checks; translating vortices in both
  hemispheres on both model representations (15-km bound on approximately
  30-km synthetic grids); end-to-end MNH NetCDF and AROME GRIB, termination,
  per-variable/time inventory checks, and an independent-process NetCDF reader.
* **Unresolved qualification:** unrounded NOAA-executable comparison, representative
  real MNH/AROME landfall cases, mountainous mask sensitivity, resolution and
  basin sensitivity, and reviewed tolerances for native/reference comparisons.
  The packaged cropped MNH fixture lacks pressure and sufficient domain coverage.
  Passing the synthetic tests does not establish accuracy for those real cases.

.. code-block:: bash

   python -m pytest src/frameit/testing/numerical/test_multifield_vortex.py
