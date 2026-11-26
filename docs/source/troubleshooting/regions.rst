Regions and tracks
=============================

.. _e1501:

E1501: A region centre could not be used
----------------------------------------------------------------------

Read the source and centre in the error. Check longitude, latitude,
and units. For a moving region, check every affected centre against
each selected source grid. Use a valid domain or a scientifically
justified selection of times. Do not move centres to the grid edge
just to get output. Validate and try a small run.

.. _e1502:

E1502: The tracker cannot run with these inputs
----------------------------------------------------------------------

Check the tracker name and source profile with ``frameit capabilities``
and :doc:`../reference/tracking`. A tracker can require a particular
model, grid, or level type. For :doc:`../tracker/utrack`, check the AROME inputs,
optional packages and trusted checkpoint path. Use a supported method only
if it fits the task. Validate the new request against your files.

.. _e1503:

E1503: The tracker does not have the support it needs
----------------------------------------------------------------------

Read the missing input, seed, geometry, or time in the error.
Check the required fields and sample count for that method. A check
of metadata does not check the actual pressure or wind values.
If validation passes but tracking fails, check the named sample and
the method's limits. Try a small run with valid inputs.

.. _e1504:

E1504: The request requires a complete track
----------------------------------------------------------------------

Read why the tracker stopped. The strict policy stopped the run
before export. Check the inputs and the failed time for that method.
Use a new attempt directory after fixing the cause. Accept a shorter
track only if your analysis can use the part that remains.

.. _w1501:

W1501: The run kept a shorter track than requested
----------------------------------------------------------------------

The run can exit zero and still be ``incomplete``. Compare the
retained times with the requested times. Read the termination reason
in ``run-status.yaml``. Use the published part only if those samples
are enough for your analysis. Do not treat the track as complete.

.. _w1502:

W1502: The experimental vortex tracker stopped early
----------------------------------------------------------------------

Read the first rejected time and the reason in the log. Check the
domain and the method's quality conditions at that time. The accepted
track does not include the rejected part. Do not fill its gaps to
make it look complete. See :doc:`../reference/tracking`.

.. _w1503:

W1503: FrameIt could not calculate track motion
----------------------------------------------------------------------

Read the named time dimension, position, or coordinate in the log.
Check that the track centres have valid times and geographic
coordinates on the selected grid. Do not assume that a track with
centres also has usable speed or motion direction.

.. _w1504:

W1504: The extraction window has unexpected grid coordinates
----------------------------------------------------------------------

Check the source grid and the extracted box named in the warning.
Confirm that its dimensions, orientation, longitude and latitude
are what your analysis needs. Do not use a box index as a geographic
coordinate. Run a small selection and check it with an ordinary reader.

.. _w1505:

W1505: An older Python tracker argument has a misleading name
----------------------------------------------------------------------

An older Python caller passed ``resolution_km`` to ``PressureWindTracker``.
It has always meant metres in that call. Pass ``grid_spacing_m`` with
the distance in metres. Do not divide an existing metre value by 1,000.

.. _w1506:

W1506: An older UTrack caller did not detect a centre
----------------------------------------------------------------------

The legacy caller returned the index pair ``(0, 0)`` for that sample.
It is not a detected centre. Current UTrack runs fail at a time without a
detection; see :ref:`e1503`.

.. _w1507:

W1507: An older reader did not create the tracker input group
----------------------------------------------------------------------

The named tracker did not match an input group in that caller.
Check which groups are present. Do not expect tracking fields in
a group the reader did not create. For current YAML, use
:doc:`../reference/tracking` to choose inputs and a method.
