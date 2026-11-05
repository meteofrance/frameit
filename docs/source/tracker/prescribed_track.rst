Prescribed-track method
========================

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


Practical considerations and limitations
----------------------------------------

- **Distance metric**: lookup uses squared geographic degrees with longitude
  differences wrapped modulo 360, not geodesic distance. Projected FA uses
  :doc:`source-CRS axes <../user_guide/fa_geometry>`.
- **Missing coordinates**: selected track positions must be finite. Source
  lookup fails if no finite candidate exists.
