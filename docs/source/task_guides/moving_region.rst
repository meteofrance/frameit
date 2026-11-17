Follow a moving region
======================

Use a supplied geographical track to extract a native-grid window at each time.
Start in the directory from :doc:`generate_fixtures`.

Select a trajectory
--------------------

Save :download:`moving-region.yaml <../../../example/tutorials/moving-region.yaml>`:

.. literalinclude:: ../../../example/tutorials/moving-region.yaml
   :language: yaml

The generated track moves east by 0.1° each hour. Each position selects a
grid-aligned crop; fields are not interpolated onto the continuous centre.
``track: true`` also exports that trajectory for other tools.

The default exact time association requires a centre at each selected input
time. It does not interpolate missing centres. See
:doc:`../tracker/prescribed_track` for the trajectory file contract and
:doc:`../concepts/time_support` for other association policies.

.. _check-and-run:

Run
----

.. container:: frameit-tabs

   .. container:: frameit-tab

      .. rubric:: CLI

      .. code-block:: bash

         frameit run moving-region.yaml

   .. container:: frameit-tab

      .. rubric:: Python API

      .. code-block:: python

         from frameit.core.execution import execute_simulation
         from frameit.core.settings_class import SimulationConfig

         config = SimulationConfig.from_yaml_with_model_preset("moving-region.yaml")
         result = execute_simulation(config)
         print(result.products)

View the output
----------------

The run writes a model-grid pressure file and a track file.
Download :download:`plot_moving_region.py <../../../example/plots/plot_moving_region.py>`:

.. code-block:: bash

   python plot_moving_region.py results/moving-region/products/moving-region.track.nc moving-region.svg

.. figure:: ../_static/figures/tutorial-moving-region.svg
   :target: ../_static/figures/tutorial-moving-region.svg
   :width: 480px
   :alt: Three exported prescribed positions at longitudes 60, 60.1 and 60.2 degrees east on latitude 20 degrees south.

   Exported geographical positions, not native ``cx/cy`` indices.

Adapt to real inputs
---------------------

Replace the fields, trajectory and full crop widths. To calculate centres
instead, replace ``track`` with an explicitly selected
:doc:`atmospheric tracker <../reference/tracking>` and provide its required inputs.
