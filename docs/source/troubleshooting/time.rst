Times and paired sources
=============================

Look at the sample times, forecast cycles, and interval bounds shown
by ``frameit inspect frameit.yaml``. A sample time labels a record.
A cycle is when the forecast started. Bounds mark the start and end
of an interval. They are not the same thing.

.. _e1401:

E1401: FrameIt could not read a consistent clock
-----------------------------------------------------------

Check the named time variable, calendar, units, and bounds in the file
header. Check that all selected files use a compatible clock. Ask the
producer if the meaning is unclear. Do not give dates to undecoded
numbers by guessing. Run inspection again and check the decoded labels.

.. _e1402:

E1402: The time selection left no usable records
-----------------------------------------------------------

Check that the exact requested times are present in the selected
files. For a range, check its start, end, and stride. Compare against
the source's sample times, not its forecast start. Run validation and
check the retained times. Do not round labels to make a match.

.. _e1403:

E1403: The forecast cycle is missing, unclear, or disagrees
-----------------------------------------------------------

Read the forecast reference times in inspection. If more than one
cycle is present, select the intended one with ``sources.<name>.time.cycle``.
If paired sources disagree, check the producer's forecast records.
Validate and confirm which cycle is selected.

.. _e1404:

E1404: Required sample times or centres do not match
-----------------------------------------------------------

Read the missing times in the error. Compare the source labels and,
if used, the track's time coverage. Use requests with the needed exact
times, or choose a different explicit policy only if it suits the data.
Validate and check the paired times. Do not shift a clock to hide gaps.
See :doc:`../concepts/time_support`.

.. _e1405:

E1405: The preceding-hour rule cannot pair the input records
----------------------------------------------------------------------

Check for an AROME reference and NEMO means over the preceding hour.
Each mean needs one interval with the correct bounds and end time.
Do not use this rule for a snapshot or invent missing bounds.
Run validation and check the pairings in the report.
See :doc:`../concepts/time_support` for the exact rule.

.. _e1406:

E1406: The prescribed track could not be read
-----------------------------------------------------------

Check the path under ``region.track.file`` and the error's coordinate
name. The track needs valid times and geographic coordinates on the
same trajectory. Use :doc:`../tracker/prescribed_track` to check the
file, then validate the request. A valid track file can still lack
some source times; see :ref:`e1404`.

.. _w1401:

W1401: Common-time selection skipped samples
-----------------------------------------------------------

The result uses only the shared sample times. Read the skipped times
in the log and ``time_alignment`` in provenance. Check that the
remaining times are enough for your analysis before using the data.

.. _w1402:

W1402: Some preceding-hour pairs were left out
-----------------------------------------------------------

At least one source lacked a match for each omitted pair. Check
``time_alignment`` in provenance for the times and sources. If the
analysis needs those times, get the missing intervals or revise the
request. The warning does not say that missing samples were filled.
