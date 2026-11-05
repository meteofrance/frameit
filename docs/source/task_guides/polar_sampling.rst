Sample selected fields on a polar grid
======================================

Use polar point samples for radial/angular comparisons around a continuous
geographical centre. They are not cell averages or a conservative area remap.
The reference environment supplies the optional xESMF/ESMF stack; native
extraction remains usable without it.

Start with the instructional fixed scalar, or adapt a matching real-data starter:

.. code-block:: bash

   frameit init arome-fixed-scalar

Use the input from :doc:`../getting_started/first_run`. Add this fragment to the
generated configuration:

.. code-block:: yaml

   polar:
     enabled: true
     variables:
       surface:
         names: [instructional_scalar]
     radial_step_m: 1500
     azimuth_count: 8
     interpolation_method: bilinear
     missing_data_policy: strict

The 4 km full-width box gives a 2 km outer radius. ``rr`` is in kilometres;
``theta`` is in radians clockwise from north. Eight angles cover 0 through 315
degrees without duplicating 360 degrees. The radial step must not be finer than
the resolved native spacing; the last interval can be shorter to reach the outer
radius. See :doc:`../concepts/sampling_and_frames`.

Choose coverage deliberately
----------------------------

``strict`` requires every contributing sample to be finite. ``renormalize``
instead allows a partial stencil when its valid-weight fraction reaches the
declared threshold. Neither fills an unmapped or all-missing point. Categorical
fields need an appropriate explicit method such as ``nearest_s2d`` rather than
bilinear mixing. Read :doc:`../polar_projection/xESMF_proj` for the equations,
support thresholds and per-field quality variables.

The source halo supplies interpolation neighbours without enlarging Cartesian
products. At a real model boundary, targets can still be unmapped. A larger
halo is not extrapolation. Keep radial/tangential direction undefined at zero
radius; a scalar or speed can remain valid there.

Check, run and read
-------------------

.. code-block:: bash

   frameit validate
   frameit run --dry-run
   frameit run

Check the planned target count and actual radius/angle coordinates. Open the
listed polar product with an ordinary reader. Inspect ``geometry_mapped``,
``<field>_support_fraction`` and ``<field>_interpolation_status`` beside the
physical field. The instructional missing sample must not become zero. Ordinary
means/FFTs require complete endpoint-exclusive rings; partial-sector means need
an explicit coverage choice and can be biased.

Selected atmospheric wind pairs also produce their documented polar components;
no track motion is subtracted. Ocean components have separate eligibility rules.
For multiple sources, choose :doc:`coupled_inputs` before enabling a shared target.
