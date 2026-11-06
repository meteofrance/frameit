Select fields and vertical levels
=================================

Inspect the intended stream before choosing native group and variable names:

.. code-block:: bash

   frameit inspect ./data --model arome --format grib --pattern '*.grib'
   frameit init arome --tracking fixed_box

Replace the instructional input paths and scalar in this starter with your
inspected data. Set the geographical centre and full box widths. For example,
this selection requests sea-level pressure and two native pressure levels:

.. code-block:: yaml

   variables:
     fields_2d:
       names: [prmsl]
     isobaricInhPa:
       names: [t]
       levels: {values: [850, 700]}

Values use the native coordinate units: these labels mean hPa only when the
inspected coordinate establishes that unit. They do not request interpolation.
Do not substitute surface pressure for sea-level pressure or geopotential for
height because a preferred name is absent.

Choose one level strategy per group
-----------------------------------

``levels`` chooses which saved vertical layers to keep. It does not calculate
new heights or interpolate between layers. Choose one of these forms:

* **Keep every saved level:** ``levels: stored`` (the default). Some model files
  also save extra boundary levels used by the numerical model; these stay included.
* **Keep only the model's physical levels:** ``levels: physical``. Use this when
  the file identifies which saved levels belong to the physical model domain.
  For example, a file may save 52 levels but identify only 50 as physical. FrameIt
  uses that declaration; it does not guess that the first and last levels are extra.
  Missing required range metadata causes an error.
* **Choose positions in the saved list:** ``levels: {indices: [0, 2]}`` keeps the
  first and third saved levels. Counting starts at zero. These are original file
  positions, not positions in a shortened list after removing boundary levels.
* **Choose existing coordinate labels:** ``levels: {values: [850, 700]}`` keeps
  those pressure levels when the source coordinate is in hPa. The numbers use
  the coordinate's own units; they do not always mean metres or hPa.

For a field under ``fields_2d``, omit ``levels``: it has no selectable vertical
axis. For ocean depth/sigma selections, use :doc:`../user_guide/ocean_netcdf`;
for staggered wind/W locations, use :ref:`wind-grid-contract`.

Check the selection
-------------------

.. code-block:: bash

   frameit validate --schema-only
   frameit validate
   frameit config show --resolved
   frameit run --dry-run
   frameit run

Check the status inventory, output group/level coordinates, units and values
against a small source window. Required internal wind companions can be read
without being exported. Available fields do not select additional diagnostics.
Polar fields inherit these levels and must be a subset of extraction requests;
see :doc:`polar_sampling` and :doc:`scalars_and_vectors`.
