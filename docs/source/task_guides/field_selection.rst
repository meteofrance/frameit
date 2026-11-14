Select fields and vertical levels
=================================

Inspect field names, dimensions, coordinates and units in the intended stream.
Use source field names under ``variables.2d`` or ``variables.3d``, not native
group names. A 2D field has no selectable vertical axis; time does not count as
a spatial axis. A field with one saved vertical level is still 3D.

This complete request selects sea-level pressure and temperature at two existing
pressure levels. Replace the illustrative paths and names with those in your data:

.. code-block:: yaml

   schema_version: 3
   run:
     name: pressure-levels
   sources:
     weather:
       model: arome
       files: ./data/arome/*.grib
       variables:
         2d: [prmsl]
         3d: [t]
         levels:
           values: [850, 700]
           units: hPa
   output:
     directory: ./results/pressure-levels

The numbers request existing 850 and 700 hPa labels, in that order.
They do not request interpolation. Omitted ``region`` keeps the full domain.
Do not substitute surface pressure for sea-level pressure or geopotential for
height because a preferred name is absent. Ambiguous field names and wrong
2D/3D categories fail rather than selecting another field.

.. _choose-one-level-strategy-per-group:

Choose one level strategy per source
-------------------------------------

One ``variables.levels`` applies to every requested 3D field and 3D derived
result in that source. It does not affect 2D fields or another source.
Selection never calculates new layers. Choose one strategy, or omit it:

* **Keep every saved level:** omit ``levels``. Each field keeps its own grid
  order and axis length, including saved boundary levels.
* **Keep only physical levels:** use ``levels: {domain: physical}``. The adapter
  must verify which extra or boundary levels to exclude. Missing evidence fails;
  positive heights or array length alone do not establish the physical range.
* **Choose saved positions:** use ``levels: {indices: [5, 0]}`` for original
  positions 5 then 0. Counting starts at zero; negative positions are invalid.
  An inclusive range such as ``{indices: {start: 0, end: 20, step: 2}}`` keeps
  every second position from 0 through 20.
* **Choose existing labels:** use ``levels: {values: [850, 700], units: hPa}``.
  An inclusive interval such as ``{values: {min: 700, max: 850}, units: hPa}``
  keeps available labels inside those bounds, in grid order. The interval
  endpoints need not be stored labels.

Lists preserve their written order. Intervals and omitted selections preserve
grid order. Duplicate or unavailable levels fail, even when only one requested
field lacks them. Selecting one level retains a vertical axis of length one.

Units and representations
---------------------------

``levels.units`` describes requested labels and exported vertical coordinates.
Compatible units are converted for matching: 850 hPa can select an existing
85000 Pa label and export it as 850 hPa. Bounds and coordinate metadata change
together; the physical field values and their units do not change.
Coordinate ``valid_min``, ``valid_max`` and ``valid_range`` use the converted
units. An existing ``actual_range`` is updated for the selected coordinates, or
omitted if their finite range is unknown.
``levels: {units: hPa}`` converts all vertical coordinates without subsetting.
Incompatible units fail.

Without requested units, labels use their coordinate's units. Value selection
across axes with different known units requires explicit ``units``; index-only
selection does not require equal units.
If a coordinate has no units, requested units assume the stored numbers already
use them, without rescaling. FrameIt warns and records that assumption.
Without either unit declaration, it warns and records the absence rather than
inventing units.
Other physical checks may still require units.

.. _vertical-level-roundoff:

Matching roundoff
~~~~~~~~~~~~~~~~~

Label matching permits storage and unit-conversion roundoff, not a nearby level.
The limit uses the spacing between neighbouring representable numbers:

.. code-block:: text

   storage_error = 0.5 * stored_spacing * abs(unit_factor)
   coordinate_error = storage_error + 4 * converted_spacing
   list_error = coordinate_error + 4 * requested_spacing

``stored_spacing`` uses the coordinate's stored floating dtype; it is zero for
integer storage. The other spacings use double-precision (binary64) numbers.
Each spacing is the larger finite neighbour distance; a finite extreme uses its
inward neighbour.
An explicit value matches only within ``list_error``. Value intervals allow
``coordinate_error`` at their endpoints.

An explicit value matching several stored levels fails. Two values matching the
same stored level are duplicates. FrameIt exports converted stored labels, not
copies of your request numbers.

Selection grid
~~~~~~~~~~~~~~~

The shared selector is applied separately on each product's representation.
An explicit transform to mass points selects levels on that destination grid.
Native W index 5 remains an interface; mass-point W index 5 is a different
sampling location. A model-grid transform does not also remap polar W.
Native neighbours required by explicit remapping also apply to ancillary inputs.
These internal reads do not add exported levels or widen the time selection.
See :ref:`wind-grid-contract` and :doc:`scalars_and_vectors` for these locations,
and :doc:`../user_guide/ocean_netcdf` for ocean depth and sigma conventions.

Check the selection
-------------------

Review the selection grid, source support, units, warnings and selected positions
before writing products. After export, reopen the listed products with an
ordinary reader and compare dimensions, coordinates, bounds and values with a
small source window. Internal calculation inputs need not be exported.
Available fields do not select additional diagnostics.
See :doc:`../user_guide/configuration_file` for the complete controls and
:doc:`polar_sampling` for polar product selection.
