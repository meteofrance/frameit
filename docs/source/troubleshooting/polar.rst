Polar sampling
=============================

.. _e1601:

E1601: The radial step is smaller than the input supports
----------------------------------------------------------------------

Read the minimum ``radial_step_km`` in the error. Use at least that
value, or leave the setting out to use the native spacing. A shared
target must meet the limit of the coarsest participating grid.
Run input-aware validation again. Schema-only validation cannot
check file spacing.

.. _e1602:

E1602: The selected data or settings cannot make this polar grid
----------------------------------------------------------------------

Read the named fields, grids, or methods in the error. Check the
requested geometry and interpolation against
:doc:`../task_guides/polar_sampling`. A shared target needs compatible
settings and centres. It does not make the source masks or physical
quantities equal. Validate after fixing the specific conflict.

.. _e1603:

E1603: FrameIt does not know the field's sampling kind
----------------------------------------------------------------------

Check whether the field holds values that can vary continuously or
codes for categories. Get that information from the producer, flags,
or field definition. Declare ``field_metadata.kind`` only when you
know it. Do not pick a kind from a name or number type alone.
See :doc:`../user_guide/input_files` for the documented matches that do not
need a declaration.
If you want nearest-neighbour samples of an unchanged floating-point field
from Meso-NH or AROME NetCDF, set ``interpolation: nearest`` in its
``products.polar.field_options`` entry instead. Validate and check the
chosen interpolation.

.. _e1604:

E1604: The polar target has too many points
----------------------------------------------------------------------

Read the count and limit in the error. Check the radius and angular
and radial spacing you asked for. Use a smaller target or coarser
spacing only if it is still suitable for the task. Raise the limit
only after checking memory and cost. Validate the new request.

.. _w1601:

W1601: The older polar path ignored a level selection
----------------------------------------------------------------------

Read which group and controls were ignored. Check the actual levels
in the product. For current YAML, select levels under the source's
``variables``. See :doc:`../reference/vertical_levels`.

.. _w1602:

W1602: An older Python caller used native spacing for its radial step
----------------------------------------------------------------------

No radial spacing was supplied to that caller. Check the spacing in
the warning against the input grid. For current YAML, use
``products.polar.radial_step_km`` if you need to set the step.
Read :ref:`e1601` before choosing a smaller step.

.. _w1603:

W1603: Input evidence established a missing polar kind
----------------------------------------------------------------------

Check the named field and rule against :doc:`../user_guide/input_files`.
FrameIt used ``continuous`` where neither the input kind nor YAML declared
it. If the rule describes your data, no YAML change is needed. The run records
the evidence for each affected sample in ``run-provenance.yaml``.

Missing values in a polar result
--------------------------------

Check the field's coverage and quality flags. A target can lack
source coverage or valid samples. Radial and tangential directions
are undefined at radius zero. Finer spacing does not create missing
values, and default point sampling does not conserve area totals.
