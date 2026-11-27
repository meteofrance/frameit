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
FA, GRIB, NetCDF, Zarr and polar stack. The terminal view for
``frameit validate`` is included.

FrameIt is installed in **editable mode**. Keep the checkout: this environment
uses its code, so edits to the checkout affect what runs.

Check the installation
-----------------------

.. code-block:: bash

   python -m pip check
   frameit --help

Run ``frameit info`` to show the imported FrameIt file and environment details.
Check this path when more than one checkout or installation is available.
If the command does not start, see :doc:`../troubleshooting/start`.

Refresh editable metadata after a Git update
--------------------------------------------

For an editable install, ``frameit info --short`` and new run provenance
report the version declared by the imported checkout. ``python -m pip show
frameit`` reports the version recorded when pip installed it, which can still
be older after ``git pull``.

To update the pip record, activate the environment for that checkout and run:

.. code-block:: bash

   frameit refresh-install
   python -m pip show frameit

The refresh verifies that the active interpreter's pip editable install
points to the imported checkout. It reinstalls FrameIt using the build tools
already in that environment and checks the resulting version. It leaves
dependencies alone. A wheel install uses the version recorded in its package
metadata; upgrade it through the usual pip installation path.

Continue with :doc:`first_run` for a small processing example.

If you manage your own Python environment or need native-library troubleshooting,
see :doc:`../user_guide/fa_environment`. For cluster use, see :doc:`hpc`.
