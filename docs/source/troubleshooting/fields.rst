Fields, levels and units
=============================

.. _e1301:

E1301: No field or track was selected for output
----------------------------------------------------------------------

Run ``frameit inspect frameit.yaml``. It can list fields before you
select any. Use ``--cli`` if fields are spread across files. Copy a selector
for the field you want into that source's ``variables``. If you want only a track,
request a track product with
a region that supplies centres. Run validation and check the product list.

.. _e1302:

E1302: FrameIt cannot select the named field
----------------------------------------------------------------------

Read the source, field, time, and file in the error. In inspection,
check the field's exact name and native group. It must be present
where the request needs it. If two fields share a name, select the
right group. If two files supply the same field at the same time,
use ``files`` or ``exclude`` to keep the intended file. Inspect again
to make sure this did not drop other records you need. Do not substitute
a different quantity. Validate again.

.. _e1303:

E1303: FrameIt cannot select the requested levels
----------------------------------------------------------------------

Check the field's vertical axis in inspection. An index is an
original position in that axis. A value is a label, such as a pressure
level, with units. Do not treat one as the other. Check that the
requested indices or values are present. See
:doc:`../reference/vertical_levels`, then validate and check the selected levels.

.. _e1304:

E1304: The units do not support the requested operation
----------------------------------------------------------------------

Read the units in the error and the source field's metadata. If the
units are missing, get them from the producer. Declare them only when
you know what they are. If the requested units describe a different
quantity, change the request, not the unit label. Validate again and
check the reported conversion.

.. _e1305:

E1305: Selected fields describe incompatible samples
----------------------------------------------------------------------

Check each named field's time support. An instant, a mean over an
interval, and an accumulation cannot be treated as the same sample.
Select fields with the support the method needs. Validate and check
their declared and observed time facts.

.. _e1306:

E1306: A Meso-NH wind rotation needs projection values
----------------------------------------------------------------------

Read the missing names in the error. Get ``BETA``, ``RPK`` and
``LON0`` from the producer. Supply the missing values in the pair's
``rotation`` if they are not in the source. Use degrees for ``BETA``
and ``LON0``. Do not use ``LAT0`` in place of ``LON0``. Validate
again. Here is a fragment to put under the source:

.. code-block:: yaml

   wind_pairs:
     - u: UT
       v: VT
       basis: grid
       rotation:
         method: mesonh_projection
         BETA: 0
         RPK: 0
         LON0: 54.2

These numbers are examples, not defaults. ``RPK`` has no unit and
must be in [-1, 1]. Omitted values must be in the source variables or
attributes. FrameIt keeps an explicit zero and rejects a conflict
with reliable source metadata. See :doc:`../task_guides/scalars_and_vectors`
for a complete request.

.. _e1307:

E1307: The vector basis or rotation does not match the data
----------------------------------------------------------------------

Check the two component names, their sampling positions, their basis,
and the chosen rotation. A basis tells you which directions the
components use. Do not declare Earth directions to bypass a known
grid-direction flag. Use evidence from the files or the producer.
Validate and check the resolved pair. See :ref:`wind-grid-contract`.

.. _e1308:

E1308: Required coordinate or mask data are missing
----------------------------------------------------------------------

Read the missing variable and grid in the error. Use the source file
or supported companion data that supply the coordinate, formula term,
or mask for that field. For example, CROCO current analysis may need
the model's own rho-point land/water mask. Do not fill a missing mask
with ones or zeros. Validate and confirm the required variable is found.

.. _w1301:

W1301: FrameIt used your declared Earth wind directions
----------------------------------------------------------------------

This applies only to a needed, explicitly declared Meso-NH NetCDF
wind pair when projection values are missing and the source metadata
meet the documented conditions. No grid-to-Earth rotation was applied.
Check that the winds can be treated as eastward and northward. If not,
get the producer's projection values and use the correct rotation.
This warning is tied to ``basis: earth`` on the named wind pair.
An Earth declaration does not change the sample locations or remove
the need to place both components on the same grid. It is not allowed
for GRIB, other models, or implicit declarations. FrameIt still fails
if all three projection values are available and the declared basis
conflicts, or if the source evidence is invalid or contradictory.

Check ``wind_reference_frame_override`` in provenance and output.
Original component metadata and superseded dataset flags have ``source_``
prefixes. For example, ``source_wind_reference_frame_metadata: grid``
records the original basis, not the user's declaration. Other raw
pairs keep their own basis metadata. An unused declaration does
not rotate or relabel native fields.

.. _w1302:

W1302: Native levels were kept without a usable altitude formula
----------------------------------------------------------------------

FrameIt kept the source level labels. One or more terms needed to
compute altitude were missing. Read the named term. Do not read the
native labels as physical heights unless their metadata establish that.
Select complete support if the analysis needs altitude.

.. _w1303:

W1303: The source did not say what units its level labels use
----------------------------------------------------------------------

The warning says whether the request supplied an assumption or
whether the units are still unknown. If the request supplied units,
the stored numbers were not rescaled from unknown units. Check the
producer's metadata before using the selected levels.

.. _w1304:

W1304: A level request did not match the older reader's data
----------------------------------------------------------------------

Read the named variable, axis, and labels or indices in the warning.
Check which levels the reader kept. Use available levels on that
axis if they meet your needs. The warning does not mean every
requested level was returned.

.. _e1310:

E1310: The selected field cannot feed the requested method
----------------------------------------------------------------------

Read the operation, field and reason in the validation report.
Check the method's required inputs, grid and levels against
``frameit inspect frameit.yaml --cli``. Remove the operation only if you
do not need it. Do not change the field's meaning to make it fit.
Validate and check which method is now planned.

.. _w1305:

W1305: A field check found missing variables
----------------------------------------------------------------------

Read the group name and missing variables in the warning. Check
the input inventory for those names. Do not assume the group contains
every requested field. Use the actual list when choosing what to analyse.

.. _w1306:

W1306: The catalogue proposed missing field metadata
----------------------------------------------------

Verify the proposed keys against the exact producer release and writer. If
they agree, merge the YAML fragment into ``sources.<id>.field_metadata`` and
run ``frameit validate`` again. The warning does not mean your configuration or
source file was changed.

.. _w1307:

W1307: The metadata catalogue could not be used
-----------------------------------------------

Read the reason in the warning. Check that the installed FrameIt package
contains both catalogue files and the local cache is writable. You can still
declare field metadata from producer evidence and revalidate.

Results that look wrong
-----------------------

Check units, time bounds, and missing-value masks in the output
before comparing it to another product. A valid zero is not a missing
value. Ocean velocity components can be on different native grids.
The location of a storm-centred sample does not change wind directions
or remove the storm's motion. See
:doc:`../task_guides/scalars_and_vectors` and
:doc:`../concepts/missingness_and_status`.
