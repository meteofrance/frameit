Choose storage and resource limits
==================================

Begin with a small field/time/level selection in a fresh output directory:

.. code-block:: bash

   frameit init arome-fixed-scalar

Keep the generated overwrite refusal. NetCDF is the default; choose Zarr only
when your downstream reader supports sharded v3 stores. The reference environment
includes both. Core-only installations need the optional ``zarr`` extra for Zarr
export; see :ref:`sharded-zarr-output` for versions and ordinary-reader examples.

Separate the three chunk choices
--------------------------------

.. figure:: ../_static/figures/chunks-shards.svg
   :target: ../_static/figures/chunks-shards.svg
   :width: 540px
   :alt: Source input chunks and processing chunks schedule computation. In storage, each shard contains multiple independently compressed chunks. All extents count elements along named dimensions, not bytes or resolution.

   Schematic. Compute chunks schedule work; storage chunks encode values; shards
   group storage chunks into fewer files. None changes scientific resolution.

* ``sources.<id>.reader.chunks`` uses source dimension names; ``{}`` respects native
  storage chunks. A whole-axis ``-1`` can read far more than a small crop needs.
* ``products.polar.processing.chunks`` controls polar computation using
  ``radius/azimuth`` and its retained leading dimensions.
* ``output.writer.chunks`` and ``output.writer.shards`` control storage in
  **elements**, not bytes. Shards apply only to Zarr.

Start with defaults. For example, a Zarr time chunk of 1 and spatial chunks of
128×128 can be packed in a shard of 8×512×512: 128 chunks per full shard.
Explicit shard extents must be multiples of explicit chunk extents. Use actual
output dimensions (for example ``y/x`` or ``radius/azimuth``), not input dimension
names. A key may apply to only some field datasets; a key matching none fails.
See :ref:`model-grid-coordinate-names` for staggered/ocean grids.
Large shards can increase write memory. See :doc:`../user_guide/output_files`
for automatic layouts and the directory-replacement visibility limit.

Cap concurrency before tuning
-----------------------------

This fragment supplements a complete request such as :doc:`fixed_region`:

.. code-block:: yaml

   resources:
     cpus: 1
     scheduler: synchronous
     native_threads: 1
     synchronous_export: true
     export_workers: 1

This is a bounded pilot, not a universal fastest configuration. Threaded Dask
work, native threads and spawned export processes share the CPU budget. Requests
above affinity/machine/Slurm limits fail. ``synchronous_export`` avoids the export
pool; it does not change sampling or select a different numerical method.

.. code-block:: bash

   frameit validate
   frameit run --dry-run
   frameit run

Inspect effective worker counts, planned products and polar geometry points.
``products.polar.processing.max_target_points`` bounds target geometry, not every variable/level array or
peak memory. FA decode budgets can apply to a full native horizontal record even
for a small crop. Measure whole-run wall time, peak memory and I/O with the same
selection and numerical checks before increasing concurrency. Use
:doc:`../getting_started/hpc` for site-neutral Slurm launchers and retry policy.
