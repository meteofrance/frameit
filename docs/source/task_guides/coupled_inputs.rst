Process coupled sources
=======================

Extract atmosphere and ocean fields without forcing them onto one grid or
clock. Start in the directory from :doc:`generate_fixtures`.

Select independent sources
--------------------------

Save :download:`coupled-inputs.yaml <../../../example/tutorials/coupled-inputs.yaml>`:

.. literalinclude:: ../../../example/tutorials/coupled-inputs.yaml
   :language: yaml

Atmospheric pressure has three times; ocean temperature has two. Each uses
its own native grid and retains its own units. The ocean request selects its
surface rho index, not an assumed depth shared with the atmosphere.

.. _choose-the-reference-and-time-policy:

A fixed centre covers each source's actual times. A supplied or calculated
track instead needs centres at every required time under the default exact
association. See :doc:`moving_region` and :doc:`../concepts/time_support`.

Run
----

.. container:: frameit-tabs

   .. container:: frameit-tab

      .. rubric:: CLI

      .. code-block:: bash

         frameit run coupled-inputs.yaml

   .. container:: frameit-tab

      .. rubric:: Python API

      .. code-block:: python

         from frameit.core.execution import execute_simulation
         from frameit.core.settings_class import SimulationConfig

         config = SimulationConfig.from_yaml_with_model_preset("coupled-inputs.yaml")
         result = execute_simulation(config)
         print(result.products)

View the output
----------------

The completed inventory lists separate atmosphere and ocean NetCDF files.
Download :download:`plot_coupled_inputs.py <../../../example/plots/plot_coupled_inputs.py>`:

.. code-block:: bash

   python plot_coupled_inputs.py results/coupled-inputs/products/coupled-inputs.atmosphere.model_grid.nc coupled-inputs.svg

.. figure:: ../_static/figures/tutorial-coupled-inputs.svg
   :target: ../_static/figures/tutorial-coupled-inputs.svg
   :width: 480px
   :alt: Exported analytical atmospheric-pressure crop from a two-source run.

   Atmospheric product. Ocean temperatures remain in their own product and grid.

Equal shapes or coordinates do not establish physical equivalence. See
:doc:`../user_guide/ocean_netcdf` for native ocean grids, masks and depth conventions.

Adapt to real inputs
---------------------

Replace both adapters, paths, quantities and vertical selections. Inspect each
stream independently and declare the required time association explicitly.
