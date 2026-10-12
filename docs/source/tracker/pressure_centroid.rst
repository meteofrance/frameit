Adaptive pressure centroid
==========================

Select ``tracking_method: pressure_centroid`` to use the adaptive pressure-deficit
centroid of Nguyen, Molinari and Thomas (2014), DOI
``10.1175/MWR-D-14-00044.1``. Numerical choices and the coupled motion solver
follow the supplied ``compare_batsirai_centers_v1.4.1.py`` implementation. This
is an independent implementation, not a bitwise reproduction of the authors'
analysis code.

Inputs and supported grids
--------------------------

The AROME preset requests MSLP, 10-m winds, and U, V and geopotential at all
available isobaric levels. At least two strictly increasing valid times are
required. The grid must be stationary, uniformly spaced latitude/longitude;
descending axes and longitude wrapping are supported. Winds must be
earth-relative in metres per second. MNH inputs are currently unsupported.

U and V are interpolated linearly in geopotential height to 2,000 m;
pressure is interpolated logarithmically. Geopotential is divided by
9.80665 m s-2. There is no vertical extrapolation.

Method
------

Initial guesses follow sequential 100-km MSLP search windows and 50-km
wind-minimum refinement windows, converted to index half-widths using the
configured model resolution. The 2-km pressure minimum is searched within
100 km in index space around each MSLP minimum.

Each evaluation first converges a 100-km pressure-deficit centroid. Environmental
pressure is the bilinearly sampled mean over 180 bearings on a 500-km WGS84
ring. Native-cell weights are positive pressure deficits multiplied by
cos(latitude). Integration and centre updates use exact WGS84 geodesics.
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

   tracking_method: pressure_centroid
   pressure_centroid_max_iterations: 15
   pressure_centroid_tolerance_m: 250.0
   pressure_centroid_max_motion_iterations: 50
   pressure_centroid_motion_solver: aitken
   pressure_centroid_motion_relaxation: 0.25
   pressure_centroid_motion_tolerance_m: 250.0
   pressure_centroid_r80_max_km: 250.0
   pressure_centroid_dr_km: 2.5
   pressure_centroid_dtheta: 5.0

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

Dedicated verification
----------------------

Run ``python -m pytest tests/test_pressure_centroid.py`` for synthetic-vortex,
interpolation, solver and sub-grid integration checks. This tracker is not
included in the matrix tests. Scientific comparisons require full-domain
inputs covering the 500-km reference ring, rather than cropped CI fixtures.
