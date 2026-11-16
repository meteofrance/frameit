A question about a key?
=======================

This annotated reference shows public configuration keys and their alternatives.
It combines mutually exclusive choices, so **it is not a runnable configuration**.
Start with the complete example in :doc:`../user_guide/configuration_file` and
select only the options needed for your data.

Values marked as examples are not defaults. Scientific declarations must match
source evidence. Omit optional controls for their defaults; do not write ``null``.

Find the detailed contract
--------------------------

* ``schema_version``, ``run``, ``sources`` and precedence:
  :doc:`../user_guide/configuration_file`.
* Source ``files``, ``exclude``, ``model``, ``format`` and ``reader``:
  :doc:`../user_guide/input_files`.
* Source ``profile``, ``fa``, ``field_metadata`` and ``native_cubes``:
  :doc:`../user_guide/fa_inputs`,
  :doc:`../user_guide/fa_contracts` and :doc:`../user_guide/fa_atmosphere`.
* Independent sources, centre association and shared polar targets:
  :doc:`../task_guides/coupled_inputs` and :doc:`../concepts/time_support`.
* ``region.center`` and ``region.track``:
  :doc:`../tracker/fixed_box` and :doc:`../tracker/prescribed_track`.
* ``region.tracker.method`` and method-specific settings:
  :doc:`../tracker/pressure_wind_tracker`, :doc:`../tracker/pressure_centroid`,
  :doc:`../tracker/multifield_vortex` and :doc:`../tracker/utrack`.
* ``region.width_km``, source ``time`` and ``variables.2d/3d/levels``:
  :doc:`../task_guides/fixed_region` and :doc:`../task_guides/field_selection`.
* Source ``wind_pairs``, ``transforms`` and ``derived``:
  :ref:`wind-grid-contract`.
* ``products.polar`` geometry, interpolation, support and computation settings:
  :doc:`../polar_projection/xESMF_proj`.
* ``output`` formats, compression, chunk/shard sizes, attribution and metadata:
  :doc:`../user_guide/output_files`.
* ``resources`` and worker counts: :doc:`../task_guides/storage_and_resources`
  and :doc:`../getting_started/hpc`.

All-options example
-------------------

Each source has its own field lists and a shared level selector, or explicit
vertical groups with local selectors (see :ref:`explicit-vertical-groups`). ``2d`` means
no selectable vertical axis, not necessarily the ground. FA field/cube names
and annotation keys are user-chosen names. Commented alternatives must replace
the active choice, not be added beside it.

.. literalinclude:: ../_static/configuration-reference.yaml
   :language: yaml
   :linenos:

The :download:`annotated YAML <../_static/configuration-reference.yaml>` is a
reference download only. Use the configuration reference for complete requests,
defaults and failure rules.
