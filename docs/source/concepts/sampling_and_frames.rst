Sampling locations, vector basis and frame motion
=================================================

Three different questions arise when following an event. Choose the sampling
location first, then check what the exported vector components mean.

.. figure:: ../_static/figures/sampling-frames.svg
   :target: ../_static/figures/sampling-frames.svg
   :width: 540px
   :alt: Three independently labelled operations: spatial sampling, vector-basis rotation, and a separate motion subtraction. Native grid points and polar points are different locations.

   Schematic, not to scale. Polar positions follow the centre, but exported winds
   and ocean currents do not have its translation subtracted.

Where are the samples?
----------------------

A Cartesian crop selects existing native points around a grid-aligned centre.
Polar sampling interpolates selected fields at new points, described by distance
and angle around the continuous geographical centre. Moving either selection
changes where data are sampled, not the wind's physical meaning.

Which directions do U and V describe?
-------------------------------------

In an Earth-relative pair, U points east and V north. A grid-relative pair follows
the model's axes, which may not align with east/north. Rotation changes those
component directions. Preparing staggered winds can also require moving U/V
samples to a common location; see :ref:`wind-grid-contract` for examples.

Is event motion subtracted?
---------------------------

Not from exported winds or currents. A window following an event moving east at
5 m/s does not automatically subtract 5 m/s from U. That is a separate downstream
scientific choice. Some trackers use motion-relative winds internally; their
method records specify this without changing exported field products.

Use :doc:`../task_guides/scalars_and_vectors` for representation choices and
:doc:`../task_guides/polar_sampling` for target spacing and coverage. The
:doc:`polar reference <../polar_projection/xESMF_proj>` defines angle conventions,
local radial directions and undefined components at the origin.
