Quick start
===========

A short reminder for users who know their data. New to FrameIt? Start with
:doc:`first_run`.

Create, edit, check, run
------------------------------

.. code-block:: bash

   conda activate frameit_env
   frameit init mesonh --tracking fixed_box --output region.yaml
   # Edit region.yaml for your input files, fields, region and output directory.
   frameit validate region.yaml --schema-only
   frameit validate region.yaml
   frameit run region.yaml --dry-run
   frameit run region.yaml

Before running, check these YAML settings:

* ``input``: the selected files and their format. Paths are relative to the YAML.
* ``variables``: source field names and native levels.
* ``tracking`` and ``domain.width_km``: centre or method, and full widths in km.
* ``output.directory``: a fresh run directory. Keep ``overwrite: false`` unless
  replacement is intended.

For winds or currents, also check whether the declared components are
eastward/northward or grid-aligned, and choose the output representation.
See :doc:`../concepts/sampling_and_frames` for component directions and why a
moving window does not subtract storm motion.

Useful commands
---------------

.. code-block:: bash

   # Inspect a selected Meso-NH input stream.
   frameit inspect ./data --model mesonh --format netcdf --pattern '*.nc'
   # Show settings, including defaults.
   frameit config show region.yaml
   # Show settings after input metadata checks.
   frameit config show region.yaml --resolved
   frameit init --help
   frameit run --help

Schema-only checks open no data. Validation and dry-run read metadata and
coordinates, not scientific field values. Execution reads the selected fields.

Templates and results
---------------------

Use the :ref:`starter catalogue <starter-catalogue>` to choose a model or named
workflow. For example:

.. code-block:: bash

   frameit init arome --output atmosphere.yaml
   frameit init nemo --output ocean.yaml
   frameit init mesonh --coupling croco --output coupled.yaml

Edit the starter using your source metadata. Polar sampling stays off unless selected.

Check ``run-status.yaml`` under your output directory, then open the listed
products with an ordinary NetCDF/Zarr reader. Keep ``resolved-config.yaml`` and
``run-provenance.yaml`` with the data.

See :doc:`../task_guides/fixed_region` for a worked extraction,
:doc:`../user_guide/configuration_file` for settings, and
:doc:`../user_guide/output_files` for output contents and completion states.
