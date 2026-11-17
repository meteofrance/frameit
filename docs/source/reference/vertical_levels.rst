Vertical level selection
========================

Selection retains input samples; it does not interpolate new layers. Omitted
``levels`` retains every input level in its original order.

.. _physical-domain-and-input-boundaries:

Choose a selector
------------------

Use one selection strategy:

* ``indices: [0, 2]`` selects original zero-based positions. An inclusive
  range uses ``indices: {start: 0, end: 10, step: 2}``.
* ``values: [850, 700]`` selects existing labels. An inclusive interval uses
  ``values: {min: 700, max: 850}``; endpoints need not be stored labels.
* ``domain: physical`` excludes model halo/boundary levels only when producer
  metadata identifies the physical range. Without that evidence, selection fails.
  This is not a height or finite-value threshold. Pressure-level GRIB axes have
  no additional vertical halo.

Lists keep requested order; intervals keep grid order. Duplicate, unavailable
or ambiguous selections fail. One selected level keeps a length-one vertical axis.

Groups and units
----------------

Use group names reported by ``frameit inspect``. Pressure groups use ``isobaric``;
coordinate units distinguish Pa from hPa. Raw GRIB level-type identifiers are
external decoder/provenance metadata, not YAML group names. NetCDF groups follow
their selectable vertical dimensions; native FA cubes use ``level`` or ``level_w``.

Grouped requests use ``group.field`` everywhere a field is referenced, including
wind pairs, transforms, derived inputs and product filters. Exported grouped
variables retain that qualification: ``ds["isobaric.temperature"]``.
Use local ``levels`` in each group, not source-wide ``variables.levels``.

``levels.units`` controls matching and exported vertical-coordinate units.
For example, 850 hPa selects an existing 85000 Pa label and exports 850 hPa.
Coordinate bounds and range metadata use the same conversion; field values and
their units do not change. ``levels: {units: hPa}`` converts without subsetting.
Without requested units, each coordinate retains its own units.

For an input whose height group is ``height`` and whose ``temperature`` field
has existing 10 m and 1000 m coordinates:

.. code-block:: yaml

   variables:
     3d:
       height:
         names: [temperature]
         levels: {values: [0.01, 1.0], units: km}

This selects those two samples and exports their labels in kilometres; it does
not interpolate. Height group and field names are input-specific: replace them
with the names reported by inspection.

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

For example, a mass-point request for 5 m selects the existing 5 m mass label;
an interface-only 10 m label is not silently replaced by a 15 m mass label.
This also applies to qualified fields such as ``level_w.WT``. Use explicit
indices for corresponding native/mass positions, or separate requests when
the products need different physical-value selections.

Native brackets needed for a remap remain internal reads, not additional
exported levels or times. See :ref:`wind-grid-contract` for locations and
:doc:`../user_guide/ocean_netcdf` for ocean depth/sigma conventions.
