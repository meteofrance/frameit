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
     surface:
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

* ``stored`` (default): retain stored levels, including stored extra levels.
* ``physical``: use the adapter's validated physical range. Ambiguous or missing
  ranges fail; this is not a universal removal of the first and last levels.
* ``{indices: [0, 2]}``: select zero-based **original stored** indices.
* ``{values: [850, 700]}``: select coordinate values in their native units.
  Ocean depth/sigma matching is exact; see :doc:`../user_guide/ocean_netcdf`.

CROCO sigma labels are dimensionless, not metres. NEMO depth labels remain
native coordinates, not newly diagnosed depths. Meso-NH W interfaces and mass
levels have different positions; see :ref:`wind-grid-contract` before selecting
sparse W-to-mass targets.

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
