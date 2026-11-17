Vertical level selection
========================

Selection retains input samples; it does not interpolate new layers. Omitted
``levels`` retains every input level in its original order.

Physical domain and input boundaries
------------------------------------

Some models include halo or boundary levels used by their numerical scheme.
``levels: {domain: physical}`` excludes those levels only when the adapter has
producer metadata identifying the physical range. It is not a height threshold
or a test for finite values. Without that evidence, physical-domain selection
fails. Pressure-level GRIB axes have no additional vertical halo.

Indices refer to the original selectable axis, counting from zero. Lists keep
their requested order. Inclusive index/value intervals keep grid order.
Duplicate, unavailable or ambiguous selections fail; selecting one level keeps
a length-one vertical axis.

Groups and units
----------------

Use the group names reported by inspection. FrameIt identifies pressure groups
as ``isobaric``; the coordinate units distinguish Pa from hPa. External GRIB
level-type identifiers remain decoder/provenance metadata, not YAML group names.
NetCDF groups otherwise follow their selectable vertical dimensions; native FA
cubes use ``level`` or ``level_w``.

Grouped requests use ``group.field`` everywhere a field is referenced, including
wind pairs, transforms, derived inputs and product filters. Exported grouped
variables retain that qualification: ``ds["isobaric.temperature"]``.
Use local ``levels`` in each group, not source-wide ``variables.levels``.

``levels.units`` controls matching and exported vertical-coordinate units.
For example, 850 hPa selects an existing 85000 Pa label and exports 850 hPa.
Coordinate bounds and range metadata use the same conversion; field values and
their units do not change. ``levels: {units: hPa}`` converts without subsetting.
Without requested units, each coordinate retains its own units.

Value selection across axes with different known units needs explicit units.
An input coordinate without units is not silently rescaled: requested units
become a warned, recorded assumption. Without either declaration, FrameIt
records the missing units. Other operations may still require them.

A vertically varying derived result needs compatible input selectors.
Selections landing on the same output axis must have compatible labels and
units; FrameIt does not silently pad or align incompatible groups.

.. _vertical-level-roundoff:

Matching roundoff
------------------

Label matching permits storage and unit-conversion roundoff, not a nearby level:

.. code-block:: text

   storage_error = 0.5 * stored_spacing * abs(unit_factor)
   coordinate_error = storage_error + 4 * converted_spacing
   list_error = coordinate_error + 4 * requested_spacing

``stored_spacing`` uses the stored floating dtype, or zero for integer storage.
The other spacings use binary64. Each spacing is the larger finite neighbour
distance; a finite extreme uses its inward neighbour. Explicit values match
within ``list_error``; interval endpoints allow ``coordinate_error``.

A value matching several input levels fails. Two values matching one level are
duplicates. Exported labels are converted input labels, not copies of request
numbers.

Selection grid
---------------

Each product applies the selector on its own representation. An explicit
mass-point transform selects on the destination grid. Native W index 5 is an
interface; mass-point W index 5 is a different sampling location. A model-grid
transform does not also remap polar W.

Native brackets needed for a remap remain internal reads, not additional
exported levels or times. See :ref:`wind-grid-contract` for locations and
:doc:`../user_guide/ocean_netcdf` for ocean depth/sigma conventions.
