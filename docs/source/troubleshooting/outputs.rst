Output files, run status and retries
========================================

.. _e1801:

E1801: The run directory is locked
----------------------------------------------------------------------

Another attempt owns the directory, or it left a lock after stopping.
Use a fresh directory for the retry, such as
``frameit run frameit.yaml --output-directory ./retry``. Run
``frameit status ./retry`` to check that attempt. Do not remove
``.frameit-run.lock`` while its owner might still be running.
Any status in the locked directory describes the saved attempt,
not the command that could not acquire the lock.

.. _e1802:

E1802: FrameIt refused to replace an existing file
----------------------------------------------------------------------

Read the named path. FrameIt defaults to no overwrite and refuses to
replace files it does not recognize as its own. Use a fresh output
directory. Do not delete the old products just to make a retry work.

.. _e1803:

E1803: The output destination is not writable
----------------------------------------------------------------------

Check the requested directory and its nearest existing parent. Make
sure the account running FrameIt can create files there and that the
mount is not read-only. Select a writable, fresh directory and
validate the request again.

.. _e1804:

E1804: An output would replace an input
----------------------------------------------------------------------

Read the path in the error. The output cannot replace an input file
or a directory that contains input data. Set ``output.directory`` to
a separate directory. Keep the input unchanged. Validate and retry
with the new path.

.. _e1805:

E1805: The output path or storage layout is not valid
----------------------------------------------------------------------

Read the named setting, dimension, or product path. Use sizes and
dimension names from the planned products. For Zarr, each shard must
contain whole chunks. Use a normal output directory, not a link that
redirects a product. Validate and check the reported layout.
See :doc:`../task_guides/storage_and_resources`.

.. _e1806:

E1806: A product could not be written
----------------------------------------------------------------------

Read the product and original writer error. Check the engine, the
output filesystem, and any worker error in the log. Earlier products
can be complete. Use ``run-status.yaml`` to see which ones were
published. Fix the named cause and try a small selection in a fresh
directory. Do not use a partial file as a product.

.. _e1807:

E1807: There is no usable run status file
----------------------------------------------------------------------

Pass the run directory to ``frameit status``, not the YAML request,
product file, or ``logs`` directory. Look for its original
``run-status.yaml``. If it is missing or not readable, use the command
exit and the log to find where execution stopped. Do not create a
status file to mark a run complete.

.. _e1808:

E1808: Run records or cleanup did not finish
----------------------------------------------------------------------

Read the failed record or cleanup step in the error. The run is not
complete even if some files were published. Keep the log and the last
record. If another error stopped the run first, start with that code.
A failed final write can leave the last saved state at ``running``.
Check output access and make sure the old process has stopped before
starting a new attempt.

.. _e1809:

E1809: The status changed while FrameIt read it
----------------------------------------------------------------------

Run ``frameit status`` again. If a writer is still active, wait for
it to finish before using the record to check completion. FrameIt
does not combine different snapshots of the run.

.. _e1810:

E1810: The output filesystem reported a space or quota limit
----------------------------------------------------------------------

Run ``df -h`` and ``df -i`` on the output directory or its parent to
check free space and free file entries. Check your quota too: free
space on the filesystem does not show your own limit.
Use a fresh directory with enough space. A failed write does not
make a partial product safe to use.

.. _w1801:

W1801: Optional provenance could not be used for this status
----------------------------------------------------------------------

FrameIt could read ``run-status.yaml`` but not matching
``run-provenance.yaml``. Use the status for the saved inventory.
If the run is active, try again after it finishes. Do not use
provenance from an older attempt to explain these products.

No product at the path you expected
------------------------------------------------

Check ``products`` in ``run-status.yaml``. ``planned_products`` is
not a list of files that were written. Check if you asked for that
product or used a ``--no-export`` option. A retry can leave old
unlisted files. Do not use a file just because its name matches.

Use a NetCDF reader for ``.nc`` and a Zarr v3 reader for ``.zarr``.
A Zarr store is a directory. Keep its contents together.
See :doc:`../user_guide/output_files` for reader examples.
