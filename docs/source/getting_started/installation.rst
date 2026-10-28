Installation of FrameIt
=======================

In this section, we describe the minimal steps required to install **FrameIt** for development and reproducible scientific workflows.

1. Prerequisites
----------------

- **Python**: 3.10 or newer.
- **Git**: to clone the repository.
- **a dedicated environment manager** : conda/mamba.

2. Get the source code
----------------------

In a terminal, go to your installation directory and run:

.. code-block:: bash

   git clone <FrameIt_REPO_URL>
   cd frameit

You should end up with a structure similar to:

.. code-block:: text

   .
   ├── docs
   ├── environment.yaml
   ├── pyproject.toml
   ├── scripts
   └── src

``environment.yaml`` installs **FrameIt and its reference FA/GRIB/NetCDF/polar
stack into one Python-3.13 environment**. Conda supplies the shared native
NetCDF/HDF5/ecCodes/ESMF libraries; the pip section installs this checkout and the
unmodified EPyGrAM 2.1.0 bindings with ctypesForFortran 1.3.0. The optional ``fa``
extra and identical ``fa-epygram`` alias remain available for other installations.
FA runs in disposable isolated processes using the active Python by default;
omit ``input.fa.python_executable`` in this setup. A separate interpreter remains
selectable for existing deployments. See :doc:`../user_guide/fa_environment` for
qualification, native-stack limits and migration from an older mixed installation,
and :doc:`../user_guide/fa_inputs` for supported families and declarations.

3. Create and activate the Python environment using a conda/mamba environment
-----------------------------------------------------------------------------


If you already have conda/mamba installed, use the file ``environment.yaml``:

.. code-block:: bash

   conda env create -f environment.yaml --solver libmamba
   conda activate frameit_env


4. Verify the installation
---------------------------

Environment creation installs FrameIt in editable mode from the checkout containing
``environment.yaml``. No second environment or subsequent pip installation is needed.
For migration, preserve the old environment and create a fresh named one:

.. code-block:: bash

   conda env create -f environment.yaml --solver libmamba -n frameit_unified
   conda activate frameit_unified

Quick verification:

.. code-block:: bash

   python -c "import frameit; print('frameit import OK')"
   python -m pip check
   frameit --help
