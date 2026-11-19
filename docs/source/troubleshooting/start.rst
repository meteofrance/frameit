Start and environment
=====================

The command does not start
--------------------------

If the shell says it cannot find ``frameit``, run
``command -v frameit``. Activate ``frameit_env`` first if you used
the reference install. Then run ``frameit --help`` and ``frameit info``.
Check the listed Python and FrameIt location. An editable install
still needs the checkout it points to.

If the shell cannot find ``conda``, open a shell where Conda is set
up. Follow :doc:`../getting_started/installation`. If it works on
your computer but not in a job, check the job's environment and
working directory. See :doc:`../getting_started/hpc`.

.. _e0001:

E0001: Command or option not accepted
---------------------------------------

FrameIt could not read the command. It prints usage before the error.
Run ``frameit --help`` to see the commands. If you know the command, run
its help instead, for example ``frameit validate --help``. Use one of
``--overwrite`` and ``--no-overwrite``, not both. Try the corrected
command. It should get past the usage message.

.. _e0999:

E0999: FrameIt could not name the cause
-----------------------------------------

Read the full error, including any traceback. Keep the first message
that names a file, setting, or failed operation. If the run produced
files, check ``run-status.yaml`` before using them. A file alone does
not mean a run finished.

If you report the error, give the command, the code, the output of
``frameit info --short``, and the relevant error lines. Remove private
paths and secrets. Do not attach a whole input archive.

.. _e1001:

E1001: Required Python package did not load
--------------------------------------------

Read the package name in the error. If you use the reference install,
run ``conda activate frameit_env``. Run ``python --version`` and
``python -m pip check`` in that same shell. Follow
:doc:`../getting_started/installation` if the environment is missing or
points to the wrong checkout.

Run ``frameit --help`` and ``frameit info`` again. An optional reader
listed as missing is not an error unless your request needs it.

.. _e1002:

E1002: The selected GRIB reader did not load
-----------------------------------------------------------

The request uses GRIB. Run ``frameit info`` in the same environment
and check the ecCodes entry. Follow :doc:`../user_guide/fa_environment`
for the GRIB extra and native library. Run ``frameit inspect frameit.yaml``
again. It should list the fields in the GRIB files.

.. _e1003:

E1003: The FA decoder did not return a usable response
-----------------------------------------------------------

Read the decoder exit and error text. Check the Python path in
``sources.<name>.reader.python_executable`` if you set it. That Python
needs FrameIt and the FA libraries. If you did not set it, check the
Python that runs FrameIt. Follow the FA worker steps in
:doc:`../user_guide/fa_environment`. Retry inspection on one FA file
before trying the whole request.

.. _e1004:

E1004: The polar sampling libraries are not available
-----------------------------------------------------------

Polar sampling needs xESMF and a matching ESMF/ESMPy install. Check the
selected environment in ``frameit info``. Follow
:doc:`../user_guide/fa_environment` for the native library as well as
the Python package. Validate again, then try a small polar request.
If you only need model-grid data, use a request without polar products.

.. _e1005:

E1005: The Zarr writer needs a supported version
-----------------------------------------------------------

Check the xarray and Zarr versions in the same Python that runs FrameIt.
The writer needs xarray 2026.9.0 or later and Zarr 3.4.2 through 3.x.
Follow :ref:`sharded-zarr-output` to set up the writer, or select NetCDF
if that format meets your needs. Validate and try a small export in a
new directory.

.. _e1006:

E1006: The selected NetCDF engine is not available
-----------------------------------------------------------

Read the engine name in the error. Check ``sources.<name>.reader.engine``
for input, or ``output.writer.engine`` for output. In the same Python
environment, try importing that engine: ``python -c 'import h5netcdf'``
or ``python -c 'import netCDF4'``. Follow :doc:`../user_guide/fa_environment`
rather than replacing the native HDF5 library on its own. Validate
again with the required engine available.

.. _w1001:

W1001: The old FA backend name is no longer needed
-----------------------------------------------------------

An older caller passed ``native`` to the FA reader. FrameIt used
EPyGrAM. Use ``epygram`` in that caller and keep the FA extra in the
helper's environment. This warning does not say that decoding failed.
