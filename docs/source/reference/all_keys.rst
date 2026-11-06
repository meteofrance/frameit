A question about a key?
=======================

This annotated reference shows every public configuration key. It deliberately
places alternative input layouts, trackers and output options together: **it is
not a runnable configuration**. Start a real run with ``frameit init <model>``
and select only the options relevant to your data.

The values are examples, not a replacement for complete defaults from
``frameit config show``. Scientific declarations must match source evidence.
``null`` means automatic/unset only where admitted; it does not mean zero.

Find the detailed contract
--------------------------

* ``schema_version``, ``model``, ``run`` and precedence:
  :doc:`../user_guide/configuration_file`.
* ``input.directory/pattern/files/exclude/duplicate_time_policy/netcdf``:
  :doc:`../user_guide/input_files`.
* ``input.fa`` declarations, fields and cubes: :doc:`../user_guide/fa_inputs`,
  :doc:`../user_guide/fa_contracts` and :doc:`../user_guide/fa_atmosphere`.
* ``input.sources/time_alignment`` and ``polar.shared_target``:
  :doc:`../task_guides/coupled_inputs` and :doc:`../concepts/time_support`.
* ``tracking.fixed_box`` and ``tracking.prescribed_track``:
  :doc:`../tracker/fixed_box` and :doc:`../tracker/prescribed_track`.
* ``tracking.pressure_wind``, ``tracking.pressure_centroid``,
  ``tracking.multifield_vortex`` and ``tracking.utrack``:
  :doc:`../tracker/pressure_wind_tracker`, :doc:`../tracker/pressure_centroid`,
  :doc:`../tracker/multifield_vortex` and :doc:`../tracker/utrack`.
* ``domain`` and ``variables.*.names/levels``:
  :doc:`../task_guides/fixed_region` and :doc:`../task_guides/field_selection`.
* ``input.wind_pairs`` and ``output.cartesian/polar`` representations:
  :ref:`wind-grid-contract`.
* Remaining ``polar`` geometry, interpolation, support and execution keys:
  :doc:`../polar_projection/xESMF_proj`.
* ``output`` formats, compression, chunk/shard sizes, attribution and metadata:
  :doc:`../user_guide/output_files`.
* ``execution`` and worker counts: :doc:`../task_guides/storage_and_resources`
  and :doc:`../getting_started/hpc`.

All-options example
-------------------

Each group under ``variables`` accepts ``names`` and one ``levels`` strategy.
``fields_2d`` means no selectable vertical axis, not necessarily the ground.
Named sources have their own ``model``, source-local ``input``, ``variables`` and
optional ``polar`` overrides; the parent supplies run/tracking/output policy.
FA field/cube identifiers and user annotation keys are open maps, not fixed names.

.. literalinclude:: ../_static/configuration-reference.yaml
   :language: yaml
   :linenos:

The :download:`annotated YAML <../_static/configuration-reference.yaml>` is a
reference download only. To check an adapted real configuration, run
``frameit validate --schema-only``, then ``frameit validate`` and
``frameit run --dry-run`` before execution.
