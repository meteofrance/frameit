FA environment and troubleshooting
===================================

The reference installation uses **one Python-3.13 environment** for FrameIt,
FA, GRIB, NetCDF and polar processing. From the checkout containing
``environment.yaml``:

.. code-block:: bash

   conda env create -f environment.yaml --solver libmamba
   conda activate frameit_env
   python -m pip check
   frameit --help

The YAML installs this checkout in editable mode with ``test,grib,polar,fa``
extras and development/documentation tools. No additional FrameIt installation
or second environment is needed. Keep the checkout accessible; editing it affects
environments that import this editable installation. See
:doc:`../getting_started/installation` for core-only installations (Python 3.10+)
and optional dependencies.

Native libraries and process isolation
--------------------------------------

Conda owns the shared NetCDF/HDF5/ecCodes/ESMF stack. The declared Python
``netCDF4==1.7.2`` and ``python-eccodes=2.44.0`` packages satisfy the corresponding
EPyGrAM requirements without pip replacing them with wheel-bundled I/O libraries.
The Python ecCodes binding version is distinct from the native library version.
The YAML also selects ESMPy 8.9.1 and xESMF 0.9.2.

The ``fa`` extra installs unmodified EPyGrAM 2.1.0 with ctypesForFortran 1.3.0;
``fa-epygram`` is an identical installation alias. The FA worker checks
falfilfa4py 1.2.1, ecTrans 1.6.0 and netCDF4 1.7.2 as well. Keep the upstream
requirements intact rather than patching installed tables or package metadata.

Each FA transaction runs in a fresh FA-only process using the active interpreter
(``sys.executable``) by default. GRIB/NetCDF/ESMF processing remains in the
consuming process. Gridpoint FA workers do not import Python GRIB/ecCodes or run
ecTrans transforms. Installing a transform dependency does not admit spectral FA.
Matching package versions do not establish safe FA/GRIB native coexistence in
one process; the isolation boundary remains necessary.

Workers use one native thread and one serialized request per consuming process,
with bounded time and selected full-native-record allocations. They exclude
inherited ecCodes definition/sample overrides only in the child, use private
FA-only library configuration and leave parent GRIB settings unchanged. Custom
FA definition-table loading is not an adapter option. See :doc:`fa_inputs` for
read-only source handling, point budgets and unsupported operations.

Fresh-environment migration
---------------------------

Preserve an older mixed Conda/pip installation and create a fresh named prefix:

.. code-block:: bash

   conda env create -f environment.yaml --solver libmamba -n frameit_unified
   conda activate frameit_unified
   python -m pip check
   frameit --help

Review existing YAML after activating the new environment. An explicit
``input.fa.python_executable`` continues to select its old runtime; omit it or
set it to null to use the new active Python. Environments sharing one editable
checkout also share that checkout's code.

``input.fa.backend`` defaults to ``epygram``. Legacy ``native`` is an accepted,
deprecated alias of the same reader, with warnings and requested/effective-backend
provenance. Replace it with ``epygram`` or omit it. The alias cannot select a
different decoder or bypass source, geometry, field/scaling or resource checks.
All other existing declarations and budgets retain their meanings. For legacy
flat YAML, use :doc:`configuration_file` to migrate the configuration explicitly.

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
* **Missing FMULTM/FMULTE scaling:** an installation check or a plausible value
  range cannot establish physical scaling. The default is failure; obtain
  producer/decoder evidence before any explicit ``allow_unscaled`` opt-in.
  See :doc:`fa_inputs` for declarations and recorded fallback behavior.
* **Native abort or failure during shutdown:** require a normal outer-process
  exit as well as completed products/status. A preceding success message is not
  sufficient. Use a fresh coherent installation rather than an import-order
  workaround or suppressed exit. The precise fault in older mixed prefixes is
  unresolved; no single-package cause or universal MPI/wheel incompatibility is
  established. Other platforms and future dependency resolutions need checks of
  their own.
* **Unsupported source/record/geometry:** readable headers or an installed library
  do not admit a physical operation. Resolve the stated source, type, time,
  scaling or reference-evidence requirement in :doc:`fa_inputs`.

Run provenance records actual parent and worker versions, interpreter/backend
selection and per-source observations. Package versions do not identify an
independently verified native-code revision or validate physical fields.
Compact generated-fixture checks cover the documented engine/isolation contracts;
producer-specific units/scaling/support/Earth-model evidence and scientific review
remain separate requirements. Optional diagnostics and transformations execute
only when selected, not because dependencies or input fields happen to exist.
