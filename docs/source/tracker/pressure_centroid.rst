Adaptive pressure centroid
==========================

Select ``tracking.method: pressure_centroid`` to use the adaptive pressure-deficit
centroid of Nguyen, Molinari and Thomas (2014), DOI
``10.1175/MWR-D-14-00044.1``. Numerical choices and the coupled motion solver
follow the supplied ``compare_batsirai_centers_v1.4.1.py`` implementation. This
is an independent implementation, not a bitwise reproduction of the authors'
analysis code.

Troubleshooting reference-ring coverage
--------------------------------------

The full 500-km reference ring must have finite pressure interpolated to
2,000 m ASL, including the horizontal interpolation stencil. An invalid sample
causes failure, not averaging over a partial ring. The error reports the candidate
centre and invalid sample count. Check whether the centre belongs to the intended
disturbance, whether the ring crosses the atmospheric input boundary, and whether
vertical brackets or masks leave missing pressure at that height. Supply wider
valid atmospheric coverage or choose another suitable tracker when these
requirements cannot be met. Increasing ``domain.size_km`` changes the output box,
not the atmospheric input coverage. The reference radius is not a configuration
workaround. Motion coupling also requires at least two increasing valid times;
a single snapshot can test spatial support but cannot validate a full track.

Inputs and supported grids
--------------------------

The AROME preset requests MSLP, 10-m winds, and U, V and geopotential at all
available isobaric levels. At least two strictly increasing valid times are
required. The grid must be stationary, uniformly spaced latitude/longitude;
descending axes and longitude wrapping are supported. Winds must be
earth-relative and are normalized to metres per second. Pressure inputs normalize
to Pa while exported ``environment_hpa`` remains hPa.

U and V are interpolated linearly in geopotential height to 2,000 m;
pressure is interpolated logarithmically. Geopotential is divided by
9.80665 m s-2. There is no vertical extrapolation. An exact endpoint uses
the endpoint value without requiring a finite zero-weight neighbour.

Meso-NH native-level inputs
--------------------------------------------------

``model: mesonh`` supports NetCDF native-level inputs on a stationary regional
structured grid, including projected grids with two-dimensional geographic
coordinates. The existing grid-spacing support limits still apply (see
:doc:`/user_guide/configuration_file`). Native ``ni``, ``nj`` and ``level``
coordinates and at least two increasing times are required.

The tracker resolves the following quantities independently of the variables
selected for export:

* Absolute model-level pressure: ``PABST`` preferred, otherwise ``PRES``.
  Declared pressure units are required and values are normalized to Pa.
* Model-level physical altitude: ``ALT`` in metres or another supported length
  unit. The adapter interprets native-level MNH ``ALT`` as positive-up altitude
  above mean sea level; contradictory AGL metadata is rejected.
* Horizontal winds: the complete ``UT_ZM``/``VT_ZM`` pair is preferred;
  otherwise the complete native ``UT``/``VT`` pair is used.
* Surface ``MSLP``, ``UM10`` and ``VM10``.

As a second explicit height representation, the adapter accepts the MNH
``level`` coordinate when it declares ``computed_standard_name: altitude``,
``formula_terms: s: level height: ZTOP orog: ZS`` (the referenced field names
may differ), and this exact ``formula_definition``:

.. code-block:: text

   z(n,k,j,i)=s(k)*(height-orog(j,i))/height+orog(j,i)

This evaluates ``z = s*(ZTOP-ZS)/ZTOP + ZS`` using declared length units.
Numeric ``level`` labels alone do not establish physical altitude. Other
coordinate formulas, including SLEVE, require explicit ``ALT`` output.
An available ``ALT`` takes precedence over the formula.

Every selected file must contain a complete input set with consistent field
names, units, wind metadata and native coordinate labels. A missing field in
a later file is an error, even if another file supplies it. Candidate precedence
is recorded; the adapter does not mix pressure or wind sources between times.

Native winds are collocated linearly using the actual mass/staggered coordinate
pairs before height interpolation. Horizontal native coordinates normalize to
metres; missing coordinate units use the documented MNH metre input contract
and the affected coordinate names are recorded in track metadata.
``UT_ZM``/``VT_ZM`` and, independently,
``UM10``/``VM10`` have an earth-relative MNH input contract. Native ``UT``/``VT``
use a grid-relative contract unless source metadata or an explicitly configured
``input.wind_reference_frame`` declares earth-relative components. The global
schema's implicit earth-relative default is not applied to raw native winds.
Explicit per-field wind metadata takes precedence. Contradictory pair metadata
is rejected. Grid-relative winds use a supplied ``grid_rotation`` (radians
counterclockwise from geographic east, with supported angular-unit conversion),
or a rotation derived from WGS84 native-axis directions. Derived rotation
requires an approximately orthogonal, consistently oriented grid (absolute
axis-direction dot product no greater than 0.02). The tracker records the source
frames and rotation method. This preparation is scoped to tracker inputs;
exported user variables retain the existing independent preparation contract.

The adapter respects a declared one-based inclusive vertical
``c_grid_dynamic_range`` to exclude nonphysical levels. It does not blindly
discard the first level of files that already contain physical levels only.
Pressure and winds are interpolated to **2,000 m altitude above mean sea level**,
using linear wind and log-pressure interpolation. Finite height columns must
be strictly monotone. Missing heights invalidate the column; nonpositive
absolute pressure is an error. Missing brackets remain missing: no vertical
extrapolation or substitution of sea-level pressure is performed. Required
reference-ring/R80/integration samples must remain valid.

The MNH geometric-altitude target and the existing AROME geopotential-height
target are distinct vertical definitions, recorded in the track metadata.
Their numerical equivalence is not assumed.

Preparing Meso-NH diagnostics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following settings are documented for `MNH 6.0 NAM_DIAG
<https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/executables_namelists/namelists/nam_diag_general.html>`_.
Merge the necessary settings into ``&NAM_DIAG`` in ``DIAG1.nam`` and run MNH's
``DIAG`` executable on the appropriate synchronous backups:

.. code-block:: fortran

   &NAM_DIAG
     LTPZH    = .TRUE.,
     LVAR_RS  = .TRUE.,
     LWIND_ZM = .TRUE.,
     LMSLP    = .TRUE.
   /

``LTPZH`` writes ``ALT`` and ``PRES`` among other diagnostics;
``LVAR_RS`` with ``LWIND_ZM`` writes ``UT_ZM`` and ``VT_ZM``;
``LMSLP`` writes ``MSLP``. Pressure-containing ``CISO`` selections such as
``'PR'`` also write ``PABST``; this is optional when ``PRES`` is available.
Keep native levels bracketing 2,000 m and a domain covering the entire 500-km
reference ring around every centre. Cropping the extraction box in FrameIt
does not reduce the tracker's input coverage requirement.

``UM10``/``VM10`` availability depends on the surface setup: the `MNH 6.0 DIAG
defaults <https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/executables_namelists/namelists/nam_diag_default.html>`_
document them for ``CSURF='EXTE'``. Use the surface-diagnostic instructions for
your MNH/SURFEX version when they are absent. Do not change the simulated surface
physics just to satisfy the tracker. These recipes are version-specific; other
MNH versions need their corresponding documentation.

Missing-input errors list the missing quantities, affected file/times and the
MNH preparation settings above. Check regenerated inputs with:

.. code-block:: bash

   frameit init mesonh --tracking pressure_centroid --output mnh.yaml
   frameit validate mnh.yaml
   frameit run mnh.yaml --dry-run

Edit the generated paths before validation. A complete example is
``example/config_file/conf_pressure_centroid_mnh.yml``.

Method
------

Initial guesses follow sequential 100-km MSLP search windows and 50-km
wind-minimum refinement windows, converted to index half-widths using the
resolved native grid spacing. The 2-km pressure minimum is searched within
100 km in index space around each MSLP minimum.

Each evaluation first converges a 100-km pressure-deficit centroid. Environmental
pressure is the bilinearly sampled mean over 180 bearings on a 500-km WGS84
ring. AROME native-cell weights are positive pressure deficits multiplied by
cos(latitude). MNH uses positive pressure deficits multiplied by nodal areas:
each native quadrilateral distributes one quarter of its WGS84 polygon area
to each mass-point vertex. This is a nodal quadrature, not a conservative
regridding claim. MNH horizontal sampling inverts the bilinear mapping within
native quadrilaterals in unwrapped geographic coordinates; cell connectivity is
retained and extrapolation is disabled. Cell edges are represented as straight
segments in those coordinates, an approximation to the native map projection.
Folded, concave or degenerate cells are rejected. Regional grids must span less
than 180 degrees longitude and exclude the poles. Integration and centre updates
use exact WGS84 geodesics.
The inner solver allows 40 steps with a 100-m tolerance, requires 16 finite
cells, and rejects steps exceeding 200 km.

The adaptive integration radius is twice the innermost rising crossing of
80 percent of the maximum azimuthal-mean cyclonic tangential wind. Winds
are storm-motion-relative and use the terminal-forward geodesic basis.
Motion uses central time differences and one-sided endpoint differences.
The outer solver couples motion and centres across the entire time sequence.
Convergence always uses the full, unrelaxed displacement residual.

Configuration defaults
----------------------

.. code-block:: yaml

   tracking:
     method: pressure_centroid
     pressure_centroid:
       convergence: {max_iterations: 15, tolerance_m: 250}
       motion:
         max_iterations: 50
         solver: aitken
         relaxation: 0.25
         tolerance_m: 250
       sampling:
         r80_max_distance_km: 250
         radial_step_km: 2.5
         azimuth_step_deg: 5

``fixed`` selects fixed geodesic relaxation. ``aitken`` starts with a full
update, clamps estimated relaxation to 0.15–1.5, guards residual growth,
temporarily falls back to fixed relaxation when stalled, and backtracks up
to three times after invalid accelerated evaluations.

A complete run configuration is provided in
``example/config_file/conf_pressure_centroid.yml``. Set its input and output
directories and run ``frameit run example/config_file/conf_pressure_centroid.yml``.

Missing reference-ring or R80 samples, unresolved R80 crossings, insufficient
finite integration cells, absent pressure deficits and nonconvergence raise
explicit errors. There is no local-reference or fixed-radius fallback.

Outputs
-------

The track NetCDF preserves continuous ``lon`` and ``lat``. Integer ``cx`` and
``cy`` identify the nearest WGS84 native grid cell for Cartesian extraction;
``grid_center_offset_m`` records the resulting offset. Kinematics and polar
origins use continuous centres. Diagnostics include ``r80_km``, ``radius_km``,
``environment_hpa``, ``iterations``, ``motion_residual_m``,
``motion_outer_iterations``, ``translation_u`` and ``translation_v``. Solver
translation uses central differences; the generic exported ``speed`` uses
forward differences. Global attributes record the implementation and settings.
MNH attributes additionally record the selected pressure/height/wind sources,
height reference, vector frames and rotation, quadrilateral interpolation and
nodal area weighting. The implementation identifier is ``frameit_mnh_native_v1``;
its geometry preparation differs from the comparison script. Resolved inputs
are also included in ``run-provenance.yaml``. Existing variable names, dimensions,
units and output encodings are retained.

Dedicated verification
----------------------

Run the dedicated suites:

.. code-block:: bash

   python -m pytest src/frameit/testing/numerical/test_pressure_centroid.py src/frameit/testing/numerical/test_pressure_centroid_mnh.py

These cover synthetic-vortex, interpolation, solver and sub-grid integration
checks, MNH failure messages, and NetCDF end-to-end reopening. This tracker is not
included in the matrix tests. Scientific comparisons require full-domain
inputs covering the 500-km reference ring, rather than cropped CI fixtures.

MNH method record and qualification status
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Quantity/maturity:** implemented MNH input/grid extension to the existing
  adaptive pressure centroid; independently checked on synthetic fields.
  Full-domain real-MNH qualification and independent scientific review remain
  outstanding. Passing the tests is not a claim of validity for all MNH cases.
* **Scientific reference:** the Nguyen, Molinari and Thomas (2014) method and
  comparison implementation cited above are inherited from the existing
  tracker. This extension adds no new stable-method or community-adoption claim.
* **Inputs/conventions:** the quantities, units, mass-grid preparation, height
  reference and candidate precedence are specified above. At least two times
  support the existing storm-motion-coupled solve.
* **Numerical departures:** native absolute-pressure columns and geometric
  altitude replace isobaric/geopotential inputs; geographic quadrilateral
  interpolation and WGS84 nodal areas replace the latitude–longitude sampler
  and latitude-only weights. Solver constants and convergence controls are
  unchanged. Geometry is reused and only 2-D prepared fields are retained across
  times; 3-D inputs are evaluated one timestamp at a time. No ESMF backend is
  required for this tracker.
* **Independent cases/tolerances:** exponential pressure columns and affine
  winds verify exact log/linear interpolation (pressure relative tolerance
  1e-14); analytic bilinear fields verify inverse cell mapping; summed geodesic
  polygon areas verify nodal weights; a stationary and translating analytic
  vortex on a 10-km projected grid must recover centres within 1 km (one tenth
  of the source spacing) and meet the existing 250-m solver residual. These
  synthetic bounds are not operational accuracy estimates.
* **Failure/applicability:** missing inputs, incompatible layouts/units,
  unresolved physical heights, invalid vector frames, unsupported geometry,
  missing required sampling support and nonconvergence fail explicitly.
  No pressure, height, time or reference-radius fallback is introduced.
* **Provenance/review gaps:** source choices and transformations are recorded
  as described above. Real DIAG layouts, mountainous masks, projection
  sensitivity and full-domain scientific comparisons require further
  representative-data qualification; no human scientific sign-off is implied.
