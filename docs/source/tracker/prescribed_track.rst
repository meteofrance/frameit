Prescribed-track method
========================

Set ``region.track.file`` to use an external NetCDF trajectory. FrameIt keeps its
geographical positions and selects native extraction indices on each source grid.
For setup and run checks, use :doc:`../task_guides/moving_region`.

Core assumptions
----------------

- Use a trajectory appropriate to the input simulation and its time convention.
- The default association requires a centre at every selected source timestamp.
  Missing required centres fail; extra trajectory times do not create samples.
- The file provides an unambiguous one-dimensional trajectory with decoded time,
  latitude and longitude. Duplicate times and nonfinite positions fail.

Input and output
----------------

Input dataset
~~~~~~~~~~~~~

Each source supplies its own decoded sample times and native geography through
its adapter. Source timelines need not be identical. A supplied centre is mapped
independently to each required grid; native indices are not shared between grids.

Prescribed track file
~~~~~~~~~~~~~~~~~~~~~

Coordinates are discovered from unambiguous CF metadata or conventional
``time``, ``latitude``/``lat`` and ``longitude``/``lon`` names with consistent
units and dimensions. All three must identify the same one-dimensional
trajectory; equal lengths alone are insufficient.
Missing units, contradictory identification, incompatible dimensions, duplicate
times and nonfinite positions fail. Time must be CF-decodable; export order is
chronological.


Configuration keys
------------------

Set only the file path. This is a fragment of a complete source request:

.. code-block:: yaml

   region:
     track:
       file: ./prescribed_track.nc

``region.sources_coupling_time_association`` defaults to ``exact``.
Every selected source sample must have a centre; missing required centres fail
and extra track times do not create samples. Explicit ``common`` reports exclusions.
The admitted ``preceding_hour`` method has additional sampling and interval
requirements; see :doc:`../concepts/time_support`.
No policy silently interpolates missing positions.


Reuse a FrameIt track
----------------------

Check the earlier run's status and track quality, then use its geographical
positions, not ``cx/cy``:

.. code-block:: yaml

   region:
     track:
       file: ../previous-run/products/case.track.nc

The new run selects points on its own grids, including another compatible source.

Request ``products.track: true`` to export a trajectory. Its coordinates are
``time(time)``, ``latitude(time)`` and ``longitude(time)``, with CF time
units/calendar and geographical units ``degrees_north``/``degrees_east``.
A centre provider alone does not request this file.

Known limitations
------------------

- **Distance metric**: lookup uses squared geographic degrees with longitude
  differences wrapped modulo 360, not geodesic distance. Projected FA uses
  :doc:`source-CRS axes <../user_guide/fa_geometry>`.
- **Missing coordinates**: selected track positions must be finite. Source
  lookup fails if no finite candidate exists.
- **No detection or correction**: the supplied trajectory is trusted; FrameIt
  does not decide whether it follows the intended physical disturbance.
- **Coverage**: required timestamps are not silently omitted. Check explicit
  association exclusions and any permitted incomplete tracker result separately.
- **Native crop**: extraction snaps to native indices and rounded point counts.
  The continuous supplied positions remain the polar origins.
