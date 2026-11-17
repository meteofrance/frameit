Pressure-wind tracker
=====================

Select ``region.tracker.method: pressure_wind`` to find an MSLP minimum, then
refine it to a nearby 10-m wind-speed minimum at each selected time.
The output ``cy(time)``/``cx(time)`` centres are native grid points, not continuous
sub-grid estimates. For setup and run checks, use :doc:`../task_guides/moving_region`.

Required input fields
---------------------

The atmospheric source must supply:

- Mean sea-level pressure (MSLP),
- 10 m zonal wind component,
- 10 m meridional wind component.

These are internal method inputs from the atmospheric source, independent of
its name. They obey source time selection and need not be exported. Native
exports retain their declared field values, units and sampling.
The selected-input path requires Earth-relative winds with unambiguous metadata
or an explicit wind-pair declaration. This tracker does not rotate grid-relative
surface inputs, and export transforms do not prepare them for tracking. Supply
independently prepared Earth-relative inputs; changing a label is not rotation.

Algorithm
---------

Notation
~~~~~~~~

Let:

- ``mslp(t, y, x)`` be the MSLP field at time index ``t``,
- ``u10(t, y, x)``, ``v10(t, y, x)`` be the 10 m wind components,
- ``W(t, y, x) = sqrt(u10^2 + v10^2)`` be the 10 m wind speed magnitude,
- ``(cy_t, cx_t)`` be the cyclone center indices at time ``t``,
- ``half_search`` be the half-width of the MSLP search window,
- ``half_refine`` be the half-width of the wind refinement window.

Sequential procedure
~~~~~~~~~~~~~~~~~~~~

Initialization (t = 0)
^^^^^^^^^^^^^^^^^^^^^^

1. Find the global MSLP minimum, or restrict candidates with
   `Optional initial position`_. This gives ``(cy_fg, cx_fg)``.

2. Find the minimum ``W`` within ``half_refine`` grid points of that guess.

   If this window is all missing, search wind speed over the full domain.

3. Store the resulting indices as ``(cy_0, cx_0)``.

Tracking for t >= 1
^^^^^^^^^^^^^^^^^^^

At each later time:

1. Find the MSLP minimum within ``half_search`` grid points of the previous
   centre ``(cy_{t-1}, cx_{t-1})``.

   If this window is all missing, search MSLP over the full domain.
   The minimum gives the pressure guess ``(cy_fg, cx_fg)``.

2. Find the minimum ``W`` within ``half_refine`` grid points of the pressure guess.

   If this window is all missing, search wind speed over the full domain.

3. Store the refined indices as ``(cy_t, cx_t)`` and proceed to the next time step.

.. _window-sizes-and-conversion-from-physical-half-widths:

Window sizes and native point counts
------------------------------------

The tracker uses two configurable square **full widths** in kilometres:

- ``region.tracker.search_width_km = 200``: MSLP search,
- ``region.tracker.refine_width_km = 100``: wind refinement.

Convert full widths to index half-widths using resolved native ``grid_spacing_m``:

- ``grid_spacing_km = grid_spacing_m / 1000``,
- ``half_search = ceil(search_width_km / (2 * grid_spacing_km))``,
- ``half_refine = ceil(refine_width_km / (2 * grid_spacing_km))``,

and enforces a minimum of 1 grid point for both. At the defaults the numerical
half-widths are 100 and 50 km. These are native-index squares, not circular
geodesic searches.

Configuration and usage
-----------------------

Add this fragment to a complete atmospheric source request:

.. code-block:: yaml

   region:
     tracker:
       method: pressure_wind
       search_width_km: 200
       refine_width_km: 100


Optional initial position
-------------------------

Restrict the first MSLP search to a user-selected position and radius:

.. code-block:: yaml

   region:
     tracker:
       method: pressure_wind
       initial_guess:
         latitude: -5.8
         longitude: 50.0
         search_radius_km: 100
       search_width_km: 200
       refine_width_km: 100

Adapt these coordinates to the intended disturbance. The seed applies to the
first selected input timestamp; it does not filter input times.
Latitude/longitude are degrees north/east in [-90, 90]/[-180, 180], and the
radius must be finite and positive. Distances use the WGS84 geodesic and include
grid points at the radius. The method searches finite MSLP candidates within
the circle on the available grid; it does not require complete circular coverage.
No valid candidate causes an error, never a global-search fallback at initialization.
Wind refinement may move the centre outside this circle. Later times use the
search and fallback policy described above.

Omit ``initial_guess`` to retain the global initial MSLP
search. The effective configuration and seeded track attributes record the
position, radius and search convention. Check the first centre against the
intended disturbance.

Known limitations
------------------

* **Minima are not unique cyclone identifiers:** another low-pressure system or
  weak-wind area can be selected. Disorganised or asymmetric systems need manual
  inspection; the pressure minimum and wind-refined centre need not coincide.
* **Initial selection:** without ``initial_guess``, the first pressure search is
  global. A seed restricts pressure candidates, not the following wind refinement.
* **Search windows:** large movement between input times or poorly chosen window
  widths can lose the intended disturbance. Windows are square native-index
  searches, not exact geodesic disks.
* **Missing-data fallbacks:** an all-missing local window triggers the documented
  full-domain search. This can jump to another disturbance; inspect the trajectory.
* **Grid-point centres:** positions and Cartesian crops are quantized to native
  points. This method does not diagnose a continuous sub-grid centre or provide
  calibrated position uncertainty.
