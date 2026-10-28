FrameIt Quick Start
===================

Use :doc:`installation` to create and activate the single reference environment
first. The workflow is **inspect, select, check, run, then interpret**. You supply
the model inputs; the commands below do not download them.

Check the active installation
-----------------------------

.. code-block:: bash

   frameit --help
   frameit info

``info`` reports the active Python and available dependency versions. FA libraries
are reported without importing their native runtime in the parent. If the
``frameit`` executable is not on PATH, use the same environment's Python:

.. code-block:: bash

   python -m frameit --help

Inspect a selected input stream
-------------------------------

Choose the actual model, format and inventory rather than searching unrelated
files in a broad directory:

.. code-block:: bash

   frameit inspect ./data --model arome --format grib --pattern '*.grib'
   # For Meso-NH NetCDF:
   frameit inspect ./data --model mesonh --format netcdf --pattern '*.nc'

Inspection reports metadata, quantity names, available units/levels/times and grid
facts. Check that they match the intended scientific quantities and sampling.
Finding a field does not choose its interpretation or verify its decoded values.
For FA records and named sources use :doc:`../user_guide/fa_inputs`.

Select the requested processing
-------------------------------

.. code-block:: bash

   frameit init arome
   # Or: frameit init mesonh --output chido.yaml
   # Show every supported setting:
   frameit init arome --full --output full.yaml

Edit ``frameit.yaml`` before running it:

* Set ``input.directory`` and one of ``input.pattern`` or ``input.files``.
* Select extracted variables and levels, the tracker and its required inputs,
  and the domain. Declare wind pairs/frames and review source units.
* Choose a designated ``output.directory``. Use a fresh location for a new
  attempt; ``output.overwrite: false`` or ``--no-overwrite`` rejects prior artifacts.
* Leave ``polar.enabled: false`` unless polar sampling is wanted. When enabled,
  its selected fields are a subset of extraction requests; it does not select
  everything in the input archive. Production continuous sampling defaults to
  bilinear point interpolation, without area-budget conservation.

Relative input, output, track and interpreter paths are resolved from the YAML
file, not the launch directory. Requests can load necessary tracking/wind
companions internally; available inputs do not enable unrelated diagnostics.
See :doc:`../user_guide/configuration_file` for selections, scientific defaults
and migration from flat YAML.

Check schema and preview metadata
----------------------------------

.. code-block:: bash

   frameit validate --schema-only
   frameit validate
   frameit run --dry-run

* ``validate --schema-only`` checks YAML types, keys, declarations and selections
  without opening datasets or requiring optional readers.
* ``validate`` opens metadata/coordinates and checks inventories, required
  variables/levels, available units, geometry and output accessibility.
* ``run --dry-run`` uses metadata preflight too, and prints the effective plan:
  settings and their origins, selected inputs, resources, grid/sampling information
  and planned products. It accepts the same execution overrides as ``run``.

Preflight can perform coordinate I/O and native metadata inquiries. It does not
decode scientific field payloads, run a tracker, verify scaling that is only
exposed during decoding, or write scientific products. Point/resource estimates
are not exact memory/runtime predictions. A successful plan is not scientific
validation, and a selected data record can still fail during execution.

Run and review completion
--------------------------

.. code-block:: bash

   frameit run
   # A named configuration is also accepted:
   frameit run path/to/config.yml --no-overwrite

Without a configuration argument, ``run`` and ``validate`` use ``frameit.yaml``.
Explicit CLI overrides take precedence over YAML; omitted flags preserve YAML
values. For example, ``--compress-level 2`` overrides the default compression
level of 1. ``--output-directory`` is a launch-directory-relative override.

NetCDF, Cartesian and polar export switches default to true, but writing requires
an available product. Polar computation is enabled separately with
``polar.enabled``. ``--no-export-polar`` disables its writing, not its computation;
``--no-export-cart`` omits Cartesian files, and ``--no-export-netcdf`` disables
all NetCDF writing. Only the selected processing should be enabled when it is
needed.

Logs and products are written under ``output.directory``. Inspect
``run-status.yaml`` for the final state, tracking completeness and product
inventory. A required-source or export failure cannot mark the run completed;
already published products can remain because atomicity is per product.
A permitted shortened track is marked incomplete even if the CLI exits zero.
Set ``execution.require_complete_tracking: true`` or
``--require-complete-tracking`` to require a complete track before export.

``resolved-config.yaml`` records effective settings and
``run-provenance.yaml`` records input, geometry, units and execution facts.
Open listed products with an ordinary reader, for example after the default
AROME template run:

.. code-block:: python

   import xarray as xr

   with xr.open_dataset("output/products/analysis.track.nc", engine="netcdf4") as track:
       print(track.sizes)
       print(track.data_vars)

Adapt the path to the actual manifest. For variable meanings, missing values,
coordinates and coupled products see :doc:`../user_guide/output_files`. A NetCDF
container does not guarantee that an existing script expects its schema or
physical definitions.

Help and optional batch execution
----------------------------------

.. code-block:: bash

   frameit run --help
   frameit validate --help
   frameit inspect --help

Errors produce a nonzero exit status and details in logs or stderr. The CLI
removes ``HDF5_DEBUG`` during execution by default; use ``--no-hdf5-debug-pop``
to preserve it. For one-task/one-node Slurm execution, resource limits,
cancellation and retries, use :doc:`hpc` and the portable ``example/slurm/``
launchers. A cluster account is not required for local use.
