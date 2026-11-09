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

.. _wind-component-directions:

Which directions do U and V describe?
-------------------------------------

A vector basis specifies the directions along which components are measured:

* **Eastward/northward components** (also called **Earth-relative components**):
  U is positive toward geographic east and V toward geographic north at each
  point. Wind-pair declarations use ``reference_frame: earth``.
* **Grid-aligned components** (also called **grid-relative components**): U and V
  follow the model's local x/y axes, which may not align with east/north.
  Wind-pair declarations use ``reference_frame: grid``.

Rotating grid-aligned components into eastward/northward components represents
the same physical wind using different component directions; it does not
subtract any velocity. Preparing staggered winds can also require moving U/V
samples to a common location; see :ref:`wind-grid-contract` for examples.

Is event motion subtracted?
---------------------------

Not from exported winds or currents. Here **Earth-relative velocity** means
velocity relative to the ground, not to the moving event. A 10 m/s eastward wind
remains 10 m/s in an exported window following a storm moving east at 5 m/s.
Subtracting storm motion would instead give a 5 m/s eastward **storm-relative**
wind. That is a separate downstream scientific choice, not a component rotation
or a consequence of following the storm. Radial/tangential output components
also retain the ground-relative velocity. Some trackers use motion-relative
winds internally; their method records specify this without changing exported
field products.

Use :doc:`../task_guides/scalars_and_vectors` for representation choices and
:doc:`../task_guides/polar_sampling` for target spacing and coverage. The
:doc:`polar reference <../polar_projection/xESMF_proj>` defines angle conventions,
local radial directions and undefined components at the origin.
