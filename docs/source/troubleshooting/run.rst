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

.. _e1901:

E1901: FrameIt could not create the test inputs
----------------------------------------------------------------------

Read the path and cause in the error. The tutorial generator needs a
new path. For example, run
``frameit generate-tests-fixtures --output tutorial-data-retry``.
It lists each file it created. Do not replace a research directory
with test inputs.

For ``frameit prepare-ci-dataset``, use ``--plan-only`` to check the
source files and track without writing the fixture. Give ``--output``
a path outside the source tree. A successful plan does not verify
the installed size or file contents.

.. _e1902:

E1902: A test case or its inputs could not be set up
----------------------------------------------------------------------

Check ``--case``, ``--profile`` and ``--data-root`` against the
command and named case in the error. For ``run-all-tests``,
``FRAMEIT_CI_DATA_ROOT`` must point to the reduced fixture directory,
not your full archive. If a planned file changed, keep the old plan
and check the intended input before making a new plan.

Add ``--plan-only`` to ``frameit run-matrix-test`` and give
``--output`` a fresh directory. Read the case status and its reason
in ``run.json``. A case marked ``PLANNED`` was selected, not run.

.. _e1903:

E1903: A test command reported a failure
----------------------------------------------------------------------

This is a summary. Look in ``run.json`` for a matrix run or
``all-tests.json`` for the combined command. Open the failed case's
log or the named test report. For the standalone polar tools, use
the printed check or traceback and any report in ``--output``.
Follow the first specific code if there is one.

After fixing the cause, retry the smallest affected case in a fresh
directory. Check that the case or test passes. Do not loosen a
numerical check just to make it pass.

.. _w1901:

W1901: Fixture preparation kept its old backup
----------------------------------------------------------------------

``frameit prepare-ci-dataset --force`` installed the new fixture but
could not remove the old copy. Check the backup path in ``warnings``
and the new ``manifest_path`` in the JSON report. The backup is not
the new fixture. Keep it until you know it is no longer needed.

The run stopped without a code
------------------------------

Check stderr and, for a cluster job, the scheduler's final state.
A kill, time limit, node loss, or native crash can stop Python before
FrameIt reports a code. The exit number alone does not prove the cause.
On Slurm, get the recorded reason with:

.. code-block:: bash

   sacct -j JOBID --format=JobID,State,ExitCode,Elapsed,MaxRSS

Replace ``JOBID`` with your job number. For a reported time limit or
out-of-memory stop, try a smaller selection first. See
:doc:`../getting_started/hpc` for a small, one-task pilot. If no
job log was created, check the job's output directory exists and
is writable before submission.

.. _execution-progress:

The job is pending or the run is quiet
--------------------------------------

For a pending Slurm job, run ``squeue -j JOBID`` and read its reason in
the last column. If the run started, check the latest progress line in
stderr or its run log. It shows the last activity FrameIt could report,
not proof that a native call is moving. ``running`` is a saved state,
not proof the process is alive. See :doc:`../user_guide/output_files` for
the recorded products and completion state.
