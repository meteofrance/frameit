Installation of FrameIt
=======================

The reference ``environment.yaml`` installs **FrameIt and its FA/GRIB/NetCDF/polar
stack in one Python-3.13 Conda environment**. Use this path when you need the
complete native stack. You need Git and a working Conda/mamba installation.

Create the reference environment
--------------------------------

.. code-block:: bash

   git clone https://github.com/meteofrance/frameit
   cd frameit
   conda env create -f environment.yaml --solver libmamba
   conda activate frameit_env
   python -m pip check
   frameit --help

Run environment creation from the checkout containing ``environment.yaml``. Its
pip section installs ``-e .[test,grib,polar,fa]`` plus development/documentation
tools. FrameIt is already installed when the command completes; a second
environment or a subsequent pip installation is not required.

Conda supplies the shared NetCDF/HDF5/ecCodes/ESMF stack. The declared Python
netCDF4 1.7.2 and python-eccodes 2.44.0 packages match EPyGrAM 2.1.0's requirements;
pip supplies the unmodified FA bindings with ctypesForFortran 1.3.0. Native and
Python-binding version numbers are distinct. Keep a coherent library stack rather
than replacing individual packages to suppress a dependency error.

This is an **editable installation**: the environment imports code from this
checkout. Keep it accessible, and remember that editing or switching its revision
affects every environment using it. A separately deployed wheel does not rely on
that editable source location.

FA metadata and decoding run in fresh isolated worker processes using the active
Python. Omit ``input.fa.python_executable`` or leave it null in the reference
setup. That optional key selects a deliberately separate runtime when needed;
see :doc:`FA environment and troubleshooting <../user_guide/fa_environment>`.

``pip check`` checks installed dependency metadata, and ``--help`` checks the CLI.
Neither verifies native data decoding or scientific suitability. Continue with
:doc:`quick_start` and inspect your own inputs before selecting fields/methods.

Core and optional installations
-------------------------------

The package supports **Python 3.10 or newer**. If you manage a scientific Python
environment yourself and only need core NetCDF processing, install from the
checkout without native extras:

.. code-block:: bash

   python -m pip install .

Core dependencies include NumPy, SciPy, xarray/Dask, PyYAML, pyproj and NetCDF/HDF5
readers. Optional extras are selected only for the paths you need:

.. list-table:: Optional package extras
   :header-rows: 1

   * - Extra
     - Purpose and requirements
   * - ``grib``
     - cfgrib/ecCodes for GRIB input.
   * - ``polar``
     - xESMF and Shapely for polar processing; a compatible native ESMF/ESMPy
       installation is also required. The pip extra alone does not provision it.
   * - ``fa``
     - EPyGrAM 2.1.0 and ctypesForFortran 1.3.0 with unmodified upstream
       dependencies. The reference FA stack uses Python 3.13.
   * - ``fa-epygram``
     - Compatibility installation alias with exactly the same requirements as ``fa``.
   * - ``test``
     - pytest for the optional regression workflows.

For example, ``python -m pip install '.[grib]'`` selects core plus GRIB from the
checkout. The full reference YAML already installs its listed extras. Installed
extras do not enable diagnostics or scientific transformations by themselves;
those follow the selected configuration. Model weights are not supplied by this
environment. See :doc:`../user_guide/fa_inputs` for FA producer/layout limits.

Migrate an existing environment
-------------------------------

For an older mixed Conda/pip installation, preserve it and create a fresh named
environment from the current YAML:

.. code-block:: bash

   conda env create -f environment.yaml --solver libmamba -n frameit_unified
   conda activate frameit_unified
   python -m pip check
   frameit --help

Review an existing explicit ``input.fa.python_executable``: it continues to select
that runtime even after activating the new environment. Omit it or set it to null
to use the new active Python. Legacy ``input.fa.backend: native`` is a deprecated,
warned alias of ``epygram``; replace it with ``epygram`` or omit it. Scientific
declarations and budgets still apply. See :doc:`FA environment and troubleshooting
<../user_guide/fa_environment>` for failure diagnosis and
:doc:`../user_guide/configuration_file` for YAML migration.

HPC execution is optional. ``environment-hpc.yaml`` is a minimal NetCDF/test
environment, not an additional prerequisite for this reference installation.
Use :doc:`hpc` for its setup and site-specific Slurm/resource guidance.
