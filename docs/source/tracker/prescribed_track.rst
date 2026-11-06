Prescribed-track method
========================

For setup and run checks, use :doc:`../task_guides/moving_region`.

Purpose
-------

``tracking.method: prescribed_track`` uses positions from an external NetCDF
trajectory. It keeps the supplied geographical centres and selects native grid
indices ``(cy, cx)`` for extraction.

Core assumptions
----------------

- Use a trajectory appropriate to the input simulation and its time convention.
- Timestamps must match **exactly**; only the intersection is processed. An empty
  intersection fails.
- The track file provides, at minimum, time, latitude and longitude time series.

Input and output
----------------

Input dataset
~~~~~~~~~~~~~

The model dataset must include:

- a time coordinate named ``time``,
- latitude and longitude coordinates accessible through configuration keys (default names: ``latitude``, ``longitude``).

Prescribed track file
~~~~~~~~~~~~~~~~~~~~~

The external NetCDF file must contain:

- a coordinate for time (default name: ``time``),
- a latitude variable (default name: ``latitude``),
- a longitude variable (default name: ``longitude``).


Configuration keys
------------------

Set the track path and its coordinate names:

.. code-block:: yaml

   tracking:
     method: prescribed_track
     prescribed_track:
       file: ./prescribed_track.nc
       time_name: time
       latitude_name: latitude
       longitude_name: longitude


Reuse a FrameIt track
----------------------

.. tip::

   A generated ``*.track.nc`` can supply the prescribed positions for another run,
   including extraction from another compatible source. Use its geographical
   coordinates, not its native grid indices:

   .. code-block:: yaml

      tracking:
        method: prescribed_track
        prescribed_track:
          file: ../previous-run/products/case.track.nc
          time_name: time
          latitude_name: lat
          longitude_name: lon

   Check the earlier run's status and track quality first. The new run selects
   native points on its own source grid; it does not reuse the old ``cx/cy``.

Known limitations
------------------

- **Distance metric**: lookup uses squared geographic degrees with longitude
  differences wrapped modulo 360, not geodesic distance. Projected FA uses
  :doc:`source-CRS axes <../user_guide/fa_geometry>`.
- **Missing coordinates**: selected track positions must be finite. Source
  lookup fails if no finite candidate exists.
- **No detection or correction**: the supplied trajectory is trusted; FrameIt
  does not decide whether it follows the intended physical disturbance.
- **Exact times only**: missing timestamps are not interpolated. A shortened
  source track supplies only its accepted times; inspect the resulting coverage.
- **Native crop**: extraction snaps to native indices and rounded point counts.
  The continuous supplied positions remain the polar origins.
