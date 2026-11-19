Sample a polar grid
===================

Sample an eastward wind component around a fixed centre. Start in the directory
from :doc:`generate_fixtures`. Polar processing runs only because this request
selects it.

Select the polar product
------------------------

Save :download:`polar-sampling.yaml <../../../example/tutorials/polar-sampling.yaml>`:

.. literalinclude:: ../../../example/tutorials/polar-sampling.yaml
   :language: yaml

Omitting ``radial_step_km`` derives a supported step from the prepared input
coordinates. An explicit smaller-than-supported step fails with the calculated
minimum. The bound depends on the selected grid, not a model's nominal resolution.

Continuous fields use bilinear point sampling by default, without an
area-conservation guarantee. The default strict missing-data policy leaves
insufficiently supported points missing. The field stays eastward wind:
polar sample locations do not make it radial wind or subtract centre motion.

Run
----

.. container:: frameit-tabs

   .. container:: frameit-tab

      .. rubric:: CLI

      .. code-block:: bash

         frameit run polar-sampling.yaml

   .. container:: frameit-tab

      .. rubric:: Python API

      .. code-block:: python

         from frameit.core.execution import execute_simulation
         from frameit.core.settings_class import SimulationConfig

         config = SimulationConfig.from_yaml_with_model_preset("polar-sampling.yaml")
         result = execute_simulation(config)
         print(result.products)

View the output
----------------

The run exports native-grid and polar files. Copy this into ``plot_polar_sampling.py``:

.. literalinclude:: ../../../example/plots/plot_polar_sampling.py
   :language: python

Optional: :download:`script file <../../../example/plots/plot_polar_sampling.py>`.

.. code-block:: bash

   python plot_polar_sampling.py results/polar-sampling/products/polar-sampling.atmosphere.polar.nc polar-sampling.svg

.. figure:: ../_static/figures/tutorial-polar-sampling.svg
   :target: ../_static/figures/tutorial-polar-sampling.svg
   :width: 480px
   :alt: Circular polar plot of the eastward wind component, with north at the top, clockwise azimuth and radius in kilometres.

   First output time. The circular display retains the eastward component;
   it does not turn it into radial wind.

Use the output's validity, support-fraction and interpolation-status variables
when analysing missing samples; see :doc:`../concepts/missingness_and_status`.

.. _polar-coverage-check:

Check coverage before using a ring
----------------------------------

For this separate exercise, save
:download:`analytic-missing.yaml <../../../example/tutorials/analytic-missing.yaml>`
and run ``frameit run analytic-missing.yaml``. It uses a fixture with a missing
wind sample. The strict policy leaves a target missing when a required source
value is missing. The ``surface_type`` category uses nearest-neighbour sampling.

Copy this into ``check_polar_coverage.py`` and run ``python check_polar_coverage.py``:

.. literalinclude:: ../../../example/tutorials/check_polar_coverage.py
   :language: python

Optional: :download:`script file <../../../example/tutorials/check_polar_coverage.py>`.

The script finds a point on mapped geometry where ``u`` is missing.
Status ``2`` means that a contributing source value is missing. The
valid-weight fraction is below 1; it is not a fraction of physical area.
``u_full_ring_valid`` is false for this ring, so do not use it for a
full-ring statistic. A valid ``surface_type`` value of ``0`` means water.
It is not a missing value. Do not fill the wind gap with zero.

Adapt to real inputs
---------------------

Replace the input and centre; choose radius and azimuth count for the intended
analysis. Declare unresolved field kind and wind basis from input evidence.
See :doc:`../reference/polar` for methods, budgets and limitations.
