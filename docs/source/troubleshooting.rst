Troubleshooting
===============

Use the failing phase and affected source/field in the error to narrow the
problem. Keep the configuration and logs with the attempt.

Configuration fails before inputs open
--------------------------------------

Run ``frameit validate --schema-only``. Use the exact quoted
``schema_version: "2.1"`` and current key/value spellings. Check duplicate keys,
native group names, one level strategy and mutually exclusive angular options.
Relative YAML paths start at the configuration file, not the launch directory.
See :doc:`user_guide/configuration_file`.

Input or metadata validation fails
----------------------------------

Run ``frameit inspect`` on the affected stream, then ``frameit validate``.
Check selected fields in every file, coordinate units, grids and time/cycle
metadata. Use ``file_layout: variables`` only for complementary fields on the
same grid and clocks; unlike grids need separate sources. Do not fix a scientific
ambiguity by renaming units or selecting a different quantity. See
:doc:`user_guide/input_files`, :doc:`user_guide/fa_inputs` and
:doc:`user_guide/ocean_netcdf`.

For missing readers, native-library conflicts or FA worker errors, use
:doc:`user_guide/fa_environment`. Selecting a reader explicitly avoids unrelated
xarray backend discovery; it does not repair an incompatible native stack.

No common times or a shortened track
------------------------------------

Check decoded labels and prescribed-track coverage. Hourly means centred at
half hours do not exactly match whole-hour snapshots. Do not invent a time shift;
choose an applicable declared policy in :doc:`concepts/time_support`.
For automatic trackers, check required inputs and the method's failure notes.
An incomplete track needs a scientific decision, not automatic gap filling.

Missing polar values or unexpected vector components
----------------------------------------------------

Check actual source coverage, quality flags and the declared missing-data policy.
Radial/tangential components are undefined at zero radius. Finer sampling cannot
create missing source support. Check collocation, basis and units separately;
storm-centred positions do not imply motion-relative velocity. See
:doc:`task_guides/polar_sampling` and :ref:`wind-grid-contract`.

Memory, export or retry problems
--------------------------------

Start with a small selection and bounded workers. Check the resolved CPU budget,
input/processing chunks and storage shards in :doc:`task_guides/storage_and_resources`.
Use the product paths and state in ``run-status.yaml``; file presence alone does
not establish completion. Stop the old writer before inspecting stale locks or
partial/backup products. Keep inputs and prior completed products intact; retry
in a fresh directory. See :doc:`getting_started/hpc` and
:doc:`user_guide/output_files` for publication and overwrite limits.
