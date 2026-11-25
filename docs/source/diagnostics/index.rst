Post-run diagnostics
====================

``frameit run-diag`` analyses a completed extraction using its saved centres.
It does not rerun tracking or modify parent records and products. Its only
built-in entry is the experimental :doc:`best_track`. Omit ``diagnostics`` or
set ``diagnostics: {}`` to do no diagnostic work. Add the block after extraction
if needed, but keep the parent scientific request unchanged.

``--check`` checks the actual parent and selected inputs without creating a
child attempt. It does not check all values, masks or search-disc coverage.
Use ``--check --json`` for one structured report with facts under ``data.plan``.
Select a relocated parent with ``--run-directory``. As with ``frameit run``,
relative paths in a symlinked request are based on the YAML file it points to.

* ``model_grid`` reads the recorded NetCDF or sharded Zarr v3 native-grid
  product, even if raw files are gone. It does not consult the metadata
  catalogue. Polar products are not inputs to this method.
* ``original`` reads selected NetCDF or supported spherical regular-grid GRIB
  files of the named atmospheric source. It can use extra fields in those
  files but does not expand file patterns, add another ensemble member, or
  change the cycle or time window. The GRIB path admits a narrow set of 10 m
  wind and mean sea-level pressure parameters and budgets complete message
  decodes. Original FA and native staggered-wind preparation are not
  admitted. See ``frameit capabilities --json``.

The parent must be ``completed`` with no pending steps and a saved track.
An older parent may use a recorded public track if its saved scientific
request and product evidence are sufficient. A legacy header fingerprint
cannot prove those bytes were the ones originally published.

Each execution creates a new attempt under ``diagnostics/``. Use
``frameit status <attempt-directory>`` to read its state and products.
A child is committed only when its completed status lists the actual files.
A failure or interruption after the completed receipt is published does
not undo the commit. Check its inventory before retrying. Do not remove a
lock unless its owner is confirmed to have stopped.

The scientific catalog lists calculations. The offline metadata catalogue
fills only evidenced native attribute gaps. :doc:`../troubleshooting/codes`
lists operational codes, not the scientific quality flags in a result.

.. toctree::
   :maxdepth: 1

   best_track
