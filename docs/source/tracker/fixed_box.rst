Fixed-box method
================

Use ``region.center`` for a fixed geographical region, including when tracking
fields are unavailable. The centre stays fixed at every selected source time,
even if the event leaves the box. For a worked run, use
:doc:`../task_guides/fixed_region`.

Configuration
-------------

Add this region fragment to a complete source request:

.. code-block:: yaml

   region:
     center: {latitude: -17.5, longitude: 60.0}  # Degrees north/east
     width_km: {x: 400, y: 400}

Each source needs an identified sample clock and stationary native geography:
1-D latitude/longitude axes or matching 2-D grids. It selects its own indices
independently, without intersecting source clocks or requiring an atmosphere.
The continuous requested position remains the polar origin.

Algorithm
---------

For NetCDF/GRIB and regular lon/lat FA, FrameIt minimizes squared distance in
latitude/longitude space, with longitude differences wrapped modulo 360.
Projected FA uses :doc:`source-CRS axes <../user_guide/fa_geometry>` instead.

Rectilinear grid (latitude 1D, longitude 1D)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   cy = argmin_j (lat[j] - lat0)^2
   cx = argmin_i wrap(lon[i] - lon0)^2

Curvilinear grid (latitude 2D, longitude 2D)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   dist2(j, i) = (lat(j, i) - lat0)^2 + wrap(lon(j, i) - lon0)^2
   (cy, cx) = argmin_{j,i} dist2(j, i)

Output
~~~~~~

The selected ``cy`` and ``cx`` remain constant along that source's time axis.
The centre does not request a trajectory file; select ``products.track: true``
when a reusable NetCDF trajectory is needed.

Known limitations
------------------

* **Grid-aligned extraction:** a native point supplies ``cx/cy``. Requested widths
  round to native point counts; neither location nor extent is imposed by regridding.
  A rotated source grid can give a rotated crop.
  The requested geographical centre remains the polar origin.
* **Lookup convention:** ordinary geographic lookup uses squared degrees, not
  geodesic distance. Admitted projected FA uses its declared source CRS.
* **Coverage:** a centre outside a required footprint or no finite candidate
  causes failure. A partially covered crop retains its shape with missing padding.
* **Stationary geometry:** this lookup does not implement an evolving source mesh.
