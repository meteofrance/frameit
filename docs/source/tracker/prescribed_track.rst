Prescribed-track method
========================

Purpose
-------

The prescribed-track tracker (``tracking.method: prescribed_track``) uses an external NetCDF track file to locate, at each time step, the model grid point closest to the cyclone position provided in the track. The output is a time series of grid indices ``(cy, cx)`` defined on the set of timestamps common to both the model dataset and the track file.

This method is intended for reproducible diagnostics when a reliable cyclone trajectory is already available (e.g., produced by a prior workflow or an operational tracking).

Core assumptions
----------------

This method relies on strong assumptions:

- The prescribed track file has been built from the *same simulation outputs* as those provided to FrameIt (same time step, same calendar, same experiment).
- Common timestamps between the model dataset and the prescribed track are assumed to match **exactly** (no temporal tolerance is applied).
- The track file provides, at minimum, time, latitude and longitude time series.

Input and output
----------------

Input dataset
~~~~~~~~~~~~~

The tracker is applied to a flattened dataset created by the tracking pipeline (internally, FrameIt provides a "flat" dataset containing at least spatial coordinates and a time coordinate). The model dataset must include:

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

To activate this tracker fill the following variables in the configuration file:

``tracking.method``
   Tracking method : ``"prescribed_track"``

``tracking.prescribed_track.file``
   Path to the external NetCDF file containing the prescribed cyclone trajectory.

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

- **Exact time matching**: no time tolerance is implemented. If the track timestamps and model timestamps differ (even by seconds), the intersection may be empty.
- **Distance metric**: the closest-grid search is performed in latitude/longitude space using a squared Euclidean metric. This is adequate for small domains but is not a true geodesic distance.
- **Longitude convention**: the track file and the model dataset must use a consistent longitude convention (e.g., both in ``[-180, 180]`` or both in ``[0, 360]``). Otherwise, the closest-point selection may be incorrect.
- **NaNs**: the tracker uses ``nanargmin`` for robust selection when NaNs exist in the coordinate arrays. If all candidate distances are NaN, ``nanargmin`` will raise.
