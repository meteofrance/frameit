Fixed-box method
================

For a worked run, use :doc:`../task_guides/fixed_region`.

Overview
--------

``tracking.method: fixed_box`` keeps one geographical centre at every time.
FrameIt selects its native grid indices once and repeats them along the time axis.
The requested latitude/longitude remain the polar origin.

This option is useful when:

- the region of interest is fixed (site-focused diagnostics),
- tracking variables (MSLP, winds) are not available or not reliable.

Inputs and outputs
------------------

Input dataset
~~~~~~~~~~~~~

The model dataset must provide:

- a time coordinate named ``time``,
- latitude and longitude coordinates, either:
  - 1D latitude and 1D longitude (typical AROME-like rectilinear grid), or
  - 2D latitude and 2D longitude (typical Meso-NH curvilinear grid).

Configuration
-------------

Minimal configuration
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tracking:
     method: fixed_box
     fixed_box:
       center: {latitude: -17.5, longitude: 60.0}  # Degrees north/east

Algorithm
---------

For NetCDF/GRIB and regular lon/lat FA, FrameIt minimizes squared distance in
latitude/longitude space, with longitude differences wrapped modulo 360.
Projected FA uses :doc:`source-CRS axes <../user_guide/fa_geometry>` instead.

Rectilinear grid (latitude 1D, longitude 1D)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If latitude and longitude are 1D arrays:

.. code-block:: text

   cy = argmin_j (lat[j] - lat0)^2
   cx = argmin_i wrap(lon[i] - lon0)^2

Curvilinear grid (latitude 2D, longitude 2D)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If latitude and longitude are 2D arrays:

.. code-block:: text

   dist2(j, i) = (lat(j, i) - lat0)^2 + wrap(lon(j, i) - lon0)^2
   (cy, cx) = argmin_{j,i} dist2(j, i)

Output
~~~~~~

The index pair ``(cy, cx)`` is repeated for each model timestamp, producing:

- ``cy(time) = constant``
- ``cx(time) = constant``

Practical considerations and limitations
----------------------------------------

- **Distance metric**: squared geographic degrees are not a geodesic distance.
- **Masked coordinates**: if latitude/longitude contain NaNs (masked areas), the minimization must avoid all-NaN distance fields. If all candidate distances are NaN, the selection will fail.
- **Fixed-box versus extraction box**: the fixed-box tracker defines the *center* used by FrameIt.
  The extraction domain size is controlled separately by ``domain.width_km.x`` and ``.y``.

Example
-------

.. code-block:: yaml

   model: arome
   tracking:
     method: fixed_box
     fixed_box:
       center: {latitude: -18, longitude: 58}
   domain:
     width_km: {x: 500, y: 500}


Illustration
------------

Fixed-box extraction for tropical cyclone Batsirai:

.. figure:: ../_static/figures/Fig.FixedBox_Batsirai.png
   :target: ../_static/figures/Fig.FixedBox_Batsirai.png
   :width: 100%
   :align: center
