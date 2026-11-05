Installation of FrameIt
=======================

These instructions target **Linux with Python 3.13**. You need Git and Conda
or mamba.

Create the environment
----------------------

Get the code, then create and activate the environment:

.. code-block:: bash

   git clone https://github.com/meteofrance/frameit
   cd frameit
   conda env create -f environment.yaml --solver libmamba
   conda activate frameit_env

``environment.yaml`` installs **FrameIt and its dependencies**, including the
FA, GRIB, NetCDF, Zarr and polar stack. No second environment or separate
``pip install`` step is needed.

FrameIt is installed in **editable mode**. Keep the checkout: this environment
uses its code, so edits to the checkout affect what runs.

Check the installation
-----------------------

.. code-block:: bash

   python -m pip check
   frameit --help

``pip check`` checks dependencies. ``--help`` checks that the command works.
For a small processing test, continue with :doc:`first_run`.

If you manage your own Python environment or need native-library troubleshooting,
see :doc:`../user_guide/fa_environment`. For cluster use, see :doc:`hpc`.
