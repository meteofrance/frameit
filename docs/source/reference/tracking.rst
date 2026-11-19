Tracking methods
================

Choose :doc:`../tracker/fixed_box` for a stationary region or
:doc:`../tracker/prescribed_track` to use known positions. For calculated
atmospheric centres, compare :doc:`../tracker/pressure_wind_tracker`,
:doc:`../tracker/pressure_centroid` and the experimental
:doc:`../tracker/multifield_vortex`.

Each method lists its required inputs and limits. The beta
:doc:`../tracker/utrack` adapter cannot execute current requests.
For a worked calculation, see :doc:`../task_guides/calculate_track`.
To use positions you already have, see :doc:`../task_guides/moving_region`.

.. toctree::
   :maxdepth: 1

   ../tracker/fixed_box
   ../tracker/prescribed_track
   ../tracker/pressure_wind_tracker
   ../tracker/pressure_centroid
   ../tracker/multifield_vortex
   ../tracker/utrack
