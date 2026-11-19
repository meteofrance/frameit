Regions and tracks
=============================

.. _e1501:

E1501: A region centre is outside a selected grid
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
model, grid, or level type. UTrack cannot execute a v3 request, even
with weights installed. Use a supported method only if it fits the
task. Validate the new request against your files.

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

.. _w1505:

W1505: An older Python tracker argument has a misleading name
----------------------------------------------------------------------

An older Python caller passed ``resolution_km`` to ``PressureWindTracker``.
It has always meant metres in that call. Pass ``grid_spacing_m`` with
the distance in metres. Do not divide an existing metre value by 1,000.
