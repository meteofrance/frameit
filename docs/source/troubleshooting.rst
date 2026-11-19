Troubleshooting
===============

* **I have a code.** Find it in the :doc:`troubleshooting/codes`.
  Start with the first error that names a cause, not a later message
  that says the run failed.
* **I have no code.** If the command does not start, see
  :doc:`troubleshooting/start`. If the run stopped or went quiet, see
  :doc:`troubleshooting/run`.
* **My result looks wrong.** Start with the
  :doc:`saved run status <troubleshooting/outputs>`. Then check the
  :doc:`fields <troubleshooting/fields>` or :doc:`polar values <troubleshooting/polar>`.

.. toctree::
   :maxdepth: 1

   troubleshooting/codes
   troubleshooting/start
   troubleshooting/configuration
   reference/all_keys
   troubleshooting/inputs
   troubleshooting/fields
   troubleshooting/time
   troubleshooting/regions
   troubleshooting/polar
   troubleshooting/run
   troubleshooting/outputs

Quick checks
------------

1. Run ``frameit --help`` to check that FrameIt starts. Run
   ``frameit info --short`` to see the version.
2. Run ``frameit validate frameit.yaml --schema-only`` to check the
   YAML without opening data.
3. Run ``frameit inspect frameit.yaml`` to see what is in the files.
   Run ``frameit validate frameit.yaml`` to check the request against
   those files. Use ``--json`` for one structured report.
4. Try a small run in a new output directory. Check the exit status
   and read ``frameit status path/to/run``. Replace ``path/to/run``
   with your output directory. Validation is not proof that the
   result is scientifically valid.

Configuration fails before inputs open
--------------------------------------

See :doc:`troubleshooting/configuration`. Fix an error before trying
any check it blocked. A deferred check still needs to run.

Input or metadata validation fails
----------------------------------

See :doc:`troubleshooting/inputs` for files and readers. If FrameIt
can open the files but cannot use a field, see :doc:`troubleshooting/fields`.

.. _missing-mesonh-wind-projection:

Meso-NH wind projection parameters are missing
------------------------------------------------

See :ref:`e1306` for the missing values. See :ref:`w1301` if FrameIt
used your declared Earth directions without rotation.

No common times or a shortened track
------------------------------------

See :ref:`e1404` when the source or track times do not match. If
tracking stopped early, see :ref:`e1504` or :ref:`w1501`.

Missing polar values or unexpected vector components
----------------------------------------------------

See :doc:`troubleshooting/polar` for missing coverage and :doc:`troubleshooting/fields`
for vector directions. Do not replace missing values with zeros.

Memory, export or retry problems
--------------------------------

See :doc:`troubleshooting/run` for memory or CPU problems.
See :doc:`troubleshooting/outputs` before retrying a failed write.

What to share when you ask for help
------------------------------------------

Send the command, the first relevant message and its code, your FrameIt
and Python versions, and the final exit number. Include just the YAML
settings, input headers, and run records needed to explain the problem.
Remove secrets and private paths. Do not share a whole data archive.

If the code is not listed, check that you opened the docs for your
version. Older builds may not print codes. Use the symptom and the
message text to find the closest entry.
