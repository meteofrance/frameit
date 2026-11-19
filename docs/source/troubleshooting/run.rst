Running FrameIt
=============================

.. _e0002:

E0002: FrameIt was interrupted
----------------------------------------------------------------------

FrameIt saw a keyboard interrupt or a cancellation signal. Wait for
the process to stop. Read ``run-status.yaml`` if it exists. Earlier
complete products can remain, but they do not make the run complete.
Use a fresh directory to retry. If the process was killed before it
could report, see `The run stopped without a code`_.

.. _e1701:

E1701: The CPU settings do not fit the allocation
----------------------------------------------------------------------

Read the available CPU count and the requested settings in the error.
For Slurm, check CPUs per task, not the total CPUs on the node. Reduce
explicit workers or request a larger allocation. FrameIt counts export
workers, compute workers, and native threads together during export.
Validate and check the effective budget before retrying.
See :doc:`../task_guides/storage_and_resources`.

.. _e1702:

E1702: Python could not allocate enough memory
----------------------------------------------------------------------

Try fewer files, fields, levels, or times in a fresh pilot run. Check
memory for each worker and for the whole job. A small crop or a small
output file does not guarantee low memory use during reading.
Check the resolved chunks and workers. See
:doc:`../task_guides/storage_and_resources` before retrying.

The run stopped without a code
------------------------------

Check stderr and, for a cluster job, the scheduler's final state.
A kill, time limit, node loss, or native crash can stop Python before
FrameIt reports a code. The exit number alone does not prove the cause.
On Slurm, check the job's time limit and memory accounting. See
:doc:`../getting_started/hpc` for a small, one-task pilot.

If a run is quiet, check the latest progress line in stderr or the
run log. It shows the last activity FrameIt could report, not proof
that a native call is moving. A status of ``running`` is a saved fact,
not proof the process is alive.
