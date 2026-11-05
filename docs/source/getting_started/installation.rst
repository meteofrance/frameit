Installation of FrameIt
========================

Use **Python 3.13**. The reference workflow targets Linux; these checks do not
certify every distribution, filesystem or cluster, and do not qualify macOS or
Windows. Apply these instructions to the source revision containing this guide,
not an older installed release.

Create the reference environment
---------------------------------

You need a working Conda/mamba installation and a checkout from the
`FrameIt repository <https://github.com/meteofrance/frameit>`_. Run these commands
in the checkout's root, beside ``environment.yaml`` and ``pyproject.toml``:

.. code-block:: bash

   conda env create -f environment.yaml --solver libmamba
   conda activate frameit_env
   python -m pip check
   frameit --help

The YAML installs **FrameIt and the FA/GRIB/NetCDF/Zarr/polar stack in one
Python-3.13 environment**, including test/documentation tools. FrameIt is already
installed when creation finishes; do not add a second environment or repeat the
FrameIt installation afterward.

This is an **editable installation**: it imports code from the checkout. Keep the
checkout accessible; switching or editing its revision changes the code used by
that environment. A separately installed wheel does not depend on this source path.

Conda supplies the shared native libraries; the maintained FA bindings use their
unmodified upstream dependencies. Do not replace individual native packages merely
to suppress a dependency error. FA workers use the active interpreter in isolated
processes: omit ``input.fa.python_executable`` unless deliberately choosing another
coherent runtime. Stack details and failure diagnosis belong in
:doc:`../user_guide/fa_environment`.

``pip check`` verifies dependency metadata; ``--help`` checks the command entry
point. Neither verifies scientific values or native data decoding. Continue with
the :doc:`self-contained first run <quick_start>` for a small executable check.

Core and optional installations
--------------------------------

If you maintain a coherent Python-3.13 environment yourself, core NetCDF extraction
does not require FA, GRIB or polar dependencies. Install from the selected checkout:

.. code-block:: bash

   python -m pip install .

Core includes NumPy, SciPy, xarray/Dask, PyYAML, pyproj and NetCDF/HDF5 readers.
Select extras only for the path you need:

* ``grib``: cfgrib/ecCodes input, for example ``python -m pip install '.[grib]'``.
* ``fa``: maintained EPyGrAM 2.1.0 and ctypesForFortran 1.3.0 stack.
  ``fa-epygram`` is an identical installation alias, not another reader.
* ``polar``: xESMF/Shapely; a compatible native ESMF/ESMPy installation is also
  required. The pip extra alone does not provision it.
* ``zarr``: optional sharded Zarr v3 output (xarray ≥ 2026.9.0 and
  Zarr-Python ≥ 3.4.2, < 4). Select ``output.backend: zarr`` explicitly.
* ``test``: pytest for regression workflows.

The reference YAML already installs these extras. Installing dependencies does
not enable diagnostics or sampling, establish a wind basis, or supply UTrack
weights. Output storage details are in :ref:`sharded-zarr-output`.

Migrate an existing environment
--------------------------------

Preserve an old mixed Conda/pip prefix and create a fresh named prefix using the
procedure in :doc:`../user_guide/fa_environment`. Review any explicit FA interpreter
path: activating another environment does not override that declaration.
Retired YAML needs the separate :doc:`manual upgrade <upgrading_to_v2>`; it is not
made current by changing environments or only changing the version header.

HPC execution is optional. ``environment-hpc.yaml`` describes a smaller NetCDF/Zarr
batch environment, not an additional prerequisite for the reference installation.
Use :doc:`hpc` for site-specific resource and Slurm requirements.
