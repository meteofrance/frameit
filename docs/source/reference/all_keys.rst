A question about a key?
=======================

Find a key in the annotated YAML below, then follow its detailed reference.
The example combines mutually exclusive choices: **it is not runnable**.
For a complete request, start with :doc:`../user_guide/configuration_file`.

Example values are not defaults. Match scientific declarations to source evidence.
Omit optional controls to use defaults; do not write ``null``.

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

Each source uses field lists with a shared level selector, or
:ref:`vertical groups with local selectors <explicit-vertical-groups>`.
``2d`` means no selectable vertical axis, not necessarily the ground.
FA logical cube names and annotation keys are user-chosen; native record IDs
must match the input. Replace active choices with their commented alternatives;
do not add both.

.. literalinclude:: ../_static/configuration-reference.yaml
   :language: yaml
   :linenos:

Download the :download:`annotated YAML <../_static/configuration-reference.yaml>`
for lookup, not as a starter.
