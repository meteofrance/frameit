Start and environment
=====================

.. _e0001:

E0001: Command or option not accepted
---------------------------------------

FrameIt could not read the command. It prints usage before the error.
Run ``frameit --help`` to see the commands. If you know the command, run
its help instead, for example ``frameit validate --help``. Use one of
``--overwrite`` and ``--no-overwrite``, not both. Try the corrected
command. It should get past the usage message.

.. _e0999:

E0999: FrameIt could not name the cause
-----------------------------------------

Read the full error, including any traceback. Keep the first message
that names a file, setting, or failed operation. If the run produced
files, check ``run-status.yaml`` before using them. A file alone does
not mean a run finished.

If you report the error, give the command, the code, the output of
``frameit info --short``, and the relevant error lines. Remove private
paths and secrets. Do not attach a whole input archive.

.. _e1001:

E1001: Required Python package did not load
--------------------------------------------

Read the package name in the error. If you use the reference install,
run ``conda activate frameit_env``. Run ``python --version`` and
``python -m pip check`` in that same shell. Follow
:doc:`../getting_started/installation` if the environment is missing or
points to the wrong checkout.

Run ``frameit --help`` and ``frameit info`` again. An optional reader
listed as missing is not an error unless your request needs it.
