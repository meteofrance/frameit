FA environment and troubleshooting
===================================

Follow :doc:`../getting_started/installation` for the reference setup. This page
covers dependency choices, the FA worker runtime and failure diagnosis.

Other Python environments
--------------------------

If you manage your own Python-3.13 environment, install core NetCDF support from
the checkout with:

.. code-block:: bash

   python -m pip install .

Add the extras you need:

* ``.[grib]`` for cfgrib/ecCodes input;
* ``.[fa]`` for the EPyGrAM reader;
* ``.[polar]`` for xESMF/Shapely. A compatible native ESMF/ESMPy installation is
  also required; the pip extra does not supply it;
* ``.[zarr]`` for sharded Zarr v3 output;
* ``.[test]`` for pytest.

For example, ``python -m pip install '.[grib]'`` installs GRIB support.
See :ref:`sharded-zarr-output` for the Zarr requirements.

Native libraries and process isolation
--------------------------------------

Conda owns the shared NetCDF/HDF5/ecCodes/ESMF stack. The declared Python
``netCDF4==1.7.2`` and ``python-eccodes=2.44.0`` packages satisfy the corresponding
EPyGrAM requirements without pip replacing them with wheel-bundled I/O libraries.
The Python ecCodes binding version is distinct from the native library version.
The YAML also selects ESMPy 8.9.1 and xESMF 0.9.2.

The ``fa`` extra installs unmodified EPyGrAM 2.1.0 with ctypesForFortran 1.3.0;
the FA worker also checks falfilfa4py 1.2.1, ecTrans 1.6.0 and netCDF4 1.7.2.
Keep the upstream
requirements intact rather than patching installed tables or package metadata.

Each FA transaction runs in a fresh FA-only process using the active interpreter
(``sys.executable``) by default. GRIB/NetCDF/ESMF processing remains in the
consuming process. Gridpoint FA workers do not import Python GRIB/ecCodes or run
ecTrans transforms. Spectral FA execution is unsupported; see :doc:`fa_spectral`.

Workers use one native thread and one serialized request per consuming process,
with bounded time and selected full-native-record allocations. They exclude
inherited ecCodes definition/sample overrides only in the child, use private
FA-only library configuration and leave parent GRIB settings unchanged. Custom
FA definition-table loading is not an adapter option. See :doc:`fa_inputs` for
read-only source handling, point budgets and unsupported operations.

Optional interpreter override
------------------------------

Use ``input.fa.python_executable`` only when deliberately selecting another
coherent runtime containing FrameIt and the complete maintained FA stack. For
example, within a single-source configuration:

.. code-block:: yaml

   input:
     fa:
       python_executable: ../fa-runtime/bin/python

The path is relative to the YAML file and is made absolute without dereferencing
virtual-environment Python symlinks. In a coupled configuration, put it under
the affected ``input.sources.<id>.input.fa``. Each source may choose its own
runtime. Resolved YAML preserves the selection. A missing interpreter or worker
failure is reported; there is no automatic retry in another environment.
For raw FA CLI inspection, ``--fa-python /path/to/runtime/bin/python`` selects
the interpreter for that invocation.

Troubleshoot failures
---------------------

* **Missing dependency, incompatible version or cannot launch worker:** check
  which Python is active with ``python -c "import sys; print(sys.executable)"``
  and run ``python -m pip check`` there. Check any explicit interpreter override
  as well. The selected runtime must contain FrameIt and the FA extra.
* **Timeout or point-budget failure:** inspect the source dimensions and selected
  fields first. Even a small crop can require decoding a complete native record.
  Change ``input.fa.timeout_seconds`` or ``max_points`` deliberately; a point
  budget is not an operating-system memory quota.
* **FMULTM/FMULTE warning:** this native unknown-parameter warning can coexist
  with encoded factors. Check ``scaling.status`` in decoder provenance: observed
  packing-120 GRIB2 factors are accepted without fallback. If scaling remains
  unresolved, failure is the default; obtain evidence before an explicit
  ``allow_unscaled`` opt-in. See :doc:`fa_contracts` for the exact scope.
* **Native abort or failure during shutdown:** require a normal outer-process
  exit as well as completed products/status. A preceding success message is not
  sufficient. Check the active Python and native package versions. Include them,
  the exit code and the native error logs when reporting the failure.
  FrameIt initializes core PROJ before matrix GRIB inventories; external code
  that preloads conflicting native libraries can still fail. Use a fresh process
  with a coherent stack rather than treating native libraries as unloadable.
* **Unsupported source/record/geometry:** readable headers or an installed library
  do not admit a physical operation. Resolve the stated source, type, time,
  scaling or reference-evidence requirement in :doc:`fa_inputs`.

Run provenance records parent and worker versions, interpreter/backend selection
and per-source observations. Use :doc:`fa_baseline` for supported source layouts
and remaining scientific limits.
