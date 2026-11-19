Process a small prescribed event
================================

Combine selected times and levels with independent atmosphere/ocean products
and opt-in polar sampling. Start in the directory from :doc:`generate_fixtures`.
The prescribed analytical event is instructional, not a dynamical simulation.

Select the event
----------------

Save :download:`analytic-moving.yaml <../../../example/tutorials/analytic-moving.yaml>`:

.. literalinclude:: ../../../example/tutorials/analytic-moving.yaml
   :language: yaml

Atmospheric times 1 and 2 retain the 1000 m temperature layer. Ocean times 0
and 2 retain their own three rho indices. Exact association uses supplied
centres at those actual times, without time interpolation.

Only the selected polar product calculates ``speed``. Shared polar coordinates
use the coarser prepared spacing; source clocks, masks and quantities stay separate.
No centre-motion velocity is subtracted.

Run
----

.. container:: frameit-tabs

   .. container:: frameit-tab

      .. rubric:: CLI

      .. code-block:: bash

         frameit run analytic-moving.yaml

   .. container:: frameit-tab

      .. rubric:: Python API

      .. code-block:: python

         from frameit.core.execution import execute_simulation
         from frameit.core.settings_class import SimulationConfig

         config = SimulationConfig.from_yaml_with_model_preset("analytic-moving.yaml")
         result = execute_simulation(config)
         print(result.products)

View the output
----------------

The inventory lists model-grid/polar products for each source and a track file.
Copy this into ``plot_analytical_event.py``:

.. literalinclude:: ../../../example/plots/plot_analytical_event.py
   :language: python

Optional: :download:`script file <../../../example/plots/plot_analytical_event.py>`.

.. code-block:: bash

   python plot_analytical_event.py results/analytic-moving/products/analytic-moving.atmosphere.polar.nc analytical-event.svg

.. figure:: ../_static/figures/tutorial-analytical-event.svg
   :target: ../_static/figures/tutorial-analytical-event.svg
   :width: 480px
   :alt: Circular polar wind-speed plot at 01:00, with clockwise azimuth from north, radius in kilometres and speed in metres per second.

   First retained atmospheric time, 01:00. Speed is calculated from the sampled
   Earth-relative components, without subtracting the centre's motion.

For a worked check of missing wind and a valid category zero, see
:ref:`polar-coverage-check`.

Adapt to real inputs
---------------------

Replace paths, quantities, levels and the track; verify coverage of all required
centre times. Keep diagnostics opt-in and retain the effective configuration
and provenance with the outputs.
