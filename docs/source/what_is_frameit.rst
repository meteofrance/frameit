What is FrameIt
===============

FrameIt turns model outputs into regional datasets for analysis with your own
scripts. A YAML file selects inputs, quantities, levels, a fixed or moving region,
and optional diagnostics. Products use NetCDF or sharded Zarr v3.

Use it to:

* extract native fields around a fixed location or along a track;
* use a prescribed trajectory or an atmospheric tracking method;
* process coupled sources while keeping their grids, masks and quantities distinct;
* sample selected fields on a storm-centred geodesic polar grid.

Input adapters cover AROME, Meso-NH and selected regional NEMO/CROCO NetCDF
layouts. See :doc:`user_guide/input_files` and
:doc:`user_guide/ocean_netcdf` for supported conventions. Native FA has a
:doc:`limited AROME/SURFEX scope <user_guide/fa_baseline>`.

Start with :doc:`getting_started/first_run`, or use
:doc:`getting_started/quick_start` as a CLI reminder. Before comparing results,
check the quantities, units, time support and reference frames in
:doc:`user_guide/output_files`.

To start processing your model outputs, follow the
:doc:`task-oriented guides <task_guides/index>`.
The :doc:`configuration reference <user_guide/configuration_file>` and
:doc:`troubleshooting` remain available without repeating the tutorial.
