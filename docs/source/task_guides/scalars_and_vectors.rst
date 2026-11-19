Choose scalar and vector representations
========================================

Copy native components or explicitly request a derived wind speed.
Start in the directory from :doc:`generate_fixtures`.

.. _declare-atmospheric-wind-pairs:

Declare the components
----------------------

Save :download:`scalars-and-vectors.yaml <../../../example/tutorials/scalars-and-vectors.yaml>`:

.. literalinclude:: ../../../example/tutorials/scalars-and-vectors.yaml
   :language: yaml

The fixture's U/V components are collocated and Earth-relative.
``basis: earth`` declares their east/north directions; it does not rotate values.
The selected ``speed`` result is their magnitude in m s-1.
Copying native components alone needs no wind pair and does not calculate speed.

Sampling locations, basis rotation and subtraction of centre motion are separate
operations. See :ref:`wind-grid-contract` for native/mass locations and
:doc:`../reference/polar` for explicitly requested polar wind methods.

Run
----

.. container:: frameit-tabs

   .. container:: frameit-tab

      .. rubric:: CLI

      .. code-block:: bash

         frameit run scalars-and-vectors.yaml

   .. container:: frameit-tab

      .. rubric:: Python API

      .. code-block:: python

         from frameit.core.execution import execute_simulation
         from frameit.core.settings_class import SimulationConfig

         config = SimulationConfig.from_yaml_with_model_preset("scalars-and-vectors.yaml")
         result = execute_simulation(config)
         print(result.products)

View the output
----------------

Copy this into ``plot_scalars_and_vectors.py``:

.. literalinclude:: ../../../example/plots/plot_scalars_and_vectors.py
   :language: python

Optional: :download:`script file <../../../example/plots/plot_scalars_and_vectors.py>`.

.. code-block:: bash

   python plot_scalars_and_vectors.py results/scalars-and-vectors/products/scalars-and-vectors.atmosphere.model_grid.nc scalars-and-vectors.svg

.. figure:: ../_static/figures/tutorial-scalars-and-vectors.svg
   :target: ../_static/figures/tutorial-scalars-and-vectors.svg
   :width: 480px
   :alt: Wind-speed magnitude calculated from the generated stationary analytical vector field, in metres per second.

   Requested speed. The exported U/V components retain their Earth-relative basis.

.. _prepare-interface-input:

For an explicit interface-to-mass W example, the generated ``interfaces.nc``
also works with
:download:`analytic-interfaces.yaml <../../../example/tutorials/analytic-interfaces.yaml>`.
Native index 1 is W=0.5 m s-1 at 500 m; its explicitly requested polar mass
index 1 is W=1 m s-1 at 1000 m. Equal index numbers do not mean equal locations.
See :doc:`../reference/vertical_levels` for selection on destination grids.

Compare two wind representations
--------------------------------

Use ``staggered-winds/mesonh.nc`` for this separate exercise. In the fixture,
``UT`` points along the grid's x direction and is stored on x faces.
``VT`` points along y and is stored on y faces. The two components are
not at the same points.

First, save and run
:download:`staggered-winds-native.yaml <../../../example/tutorials/staggered-winds-native.yaml>`.
It copies the two components at their original locations.

.. literalinclude:: ../../../example/tutorials/staggered-winds-native.yaml
   :language: yaml

Next, save and run
:download:`staggered-winds-earth.yaml <../../../example/tutorials/staggered-winds-earth.yaml>`.
It keeps the same crop and level but requests two changes:

* ``sampling: mass`` places both components at the cell centres.
* ``basis: earth`` expresses the vector as eastward and northward components.
  The rotation uses ``angle`` in the input file. Here it is a quarter-turn.

.. literalinclude:: ../../../example/tutorials/staggered-winds-earth.yaml
   :language: yaml

.. code-block:: bash

   frameit inspect staggered-winds-earth.yaml
   frameit run staggered-winds-native.yaml
   frameit run staggered-winds-earth.yaml

In the native file, ``UT`` has axis ``x_u`` and ``VT`` has axis ``y_v``.
The x faces at −500 and +500 m carry ``UT`` values 9.5 and 10.5 m/s.
At the centre between them, the grid components are (10, 0) m/s.
After rotation, they are (0, 10) m/s eastward and northward.

Both variables in the second file use ``y, x``. Check the centre and the
next x point:

.. code-block:: python

   import xarray as xr

   path = "results/staggered-winds-earth/products/staggered-winds-earth.atmosphere.model_grid.nc"
   with xr.open_dataset(path) as data:
       wind = data[["UT", "VT"]].isel(time=0, level=0, y=1, x=[1, 2])
       print(wind.UT.values.round(9))  # [0. 0.], eastward in m/s
       print(wind.VT.values.round(9))  # [10. 11.], northward in m/s

The quarter-turn is set by this fixture, not a Meso-NH default. The
transforms change sample locations and component directions. They do not
subtract storm motion.

Adapt to real inputs
---------------------

Replace names and verify units, staggering and vector basis from producer
metadata. Grid-relative winds need evidenced rotation; changing a label to
``earth`` is not a conversion. A W remap retains its physical quantity and units.
See :ref:`E1306 <e1306>` if your Meso-NH rotation needs projection values.
