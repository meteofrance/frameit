Scientific simulation matrix
============================

FrameIt provides two native services: preparation of a reproducible small scientific
fixture and execution of a catalog of simulation scenarios. Both ordinary
``frameit run`` and matrix workers use the same execution service. A matrix does not
invoke shell scripts or recursively invoke the CLI.

Ready-to-use CI dataset
-----------------------

The release bundles the frozen simulation fixture, its manifest, and
``MNH/IBTracks_reunion_CHIDO.nc``. Run ``frameit run-matrix-test --ci`` with an
``--output`` directory to use it automatically, from any working directory.
No access to the full source simulations is required.

Reproduce the CI dataset (maintainers)
----------------------------------------

Preparation is optional and is intended for reproducing or updating the fixture.

.. code-block:: bash

   frameit prepare-ci-dataset \
     --source /data/DONEE_TEST_CYCLOPY --output ./ci_dataset

The source tree contains ``AROME/BATSIRAI`` and ``MNH/CHIDO`` simulation directories
and ``MNH/IBTracks_reunion_CHIDO.nc``. An optional ``--track-file`` overrides the
track location for other layouts. The normal layout requires no environment variable.

Preparation uses a packaged, fixed recipe. It retains five BATSIRAI forecast files,
three CHIDO model times, the required atmospheric fields and vertical coordinates,
and the original prescribed NetCDF track. The crops retain the scientific coverage
required by the CI catalog. MesoNH staggered coordinates and raw packing metadata
are preserved. GRIB messages without atmospheric level metadata, including simulated
satellite messages, remain valid messages; they are excluded only from atmospheric
level inventories.

The installed fixture has a default ceiling of 100 decimal MB. Use
``--max-size-mb`` to change it. Preparation builds and verifies a temporary sibling
directory before committing it. ``--force`` replaces an existing destination only
after successful verification and the size check. Source files are never changed.
``--plan-only`` reports the source inventory, crop recipe and planned checks without
writing the fixture; it cannot predict the exact compressed size.

The native manifest records the recipe, crop, source geometry, fields, levels, times,
byte sizes and content hashes, including the track. Existing compatible fixture
manifests are supported through a read-only adapter. Matrix execution verifies the
selected fixture families and does not generate, repair, or download missing data.
The ready-to-use fixture is included as wheel and source-distribution package data.

Run the matrix
--------------

Run all tests with a computation benchmark
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Install pytest (``pip install 'frameit[test]'``), then run:

.. code-block:: bash

   frameit run-all-tests --output ./runs/all-tests
   frameit run-all-tests --data-root /data/DONEE_TEST_CYCLOPY --output ./runs/all-full

The default runs every packaged numerical test, the independent analytical
scientific qualification, and the full CI matrix using the
bundled fixture. ``--data-root`` selects the full-domain matrix instead; optional
UTrack cases accept ``--utrack-weights``. All services run even if one fails.
The output directory must be fresh and must not overlap the input data.

``all-tests.json`` combines exit codes, environment information, suite wall times,
and per-case computation timings. ``numerical.log`` and ``numerical.xml`` contain
pytest results; ``qualification/summary.json`` contains compact convergence evidence,
``qualification/qualification.json`` retains profiles and complex coefficients,
and ``matrix/`` contains the normal matrix artifacts. Exit code 0 means all
services passed, 1 indicates a test failure, 2 a setup error, and 130 interruption.

Benchmark workers load inputs before computation, and materialize lazy results
within the timed processing stages. Computation time is the sum of tracking,
extraction and polar projection (including wind collocation), excluding input
loading, imports, process startup, NetCDF writing and product checks. Only passing
matrix cases enter the benchmark total. Per-stage times are retained for inspection.
This is a single-run wall-clock measurement; OS caches are not flushed. Eager input
loading can require more memory than an ordinary run, especially on full domains.

The numerical tests ship in ``frameit.testing.numerical`` and are also collected by
the repository's ordinary ``pytest`` command.

.. code-block:: bash

   frameit run-matrix-test --ci --output ./runs/ci
   frameit run-matrix-test --data-root /data/DONEE_TEST_CYCLOPY --output ./runs/full
   frameit run-matrix-test --ci --data-root ./ci_dataset \
     --output ./runs/prescribed --case 'mnh_chido_prescribed_*'
   frameit run-matrix-test --ci --output ./runs/plan --plan-only

``--data-root`` overrides the bundled fixture with ``--ci`` and is required otherwise.
``--output`` must be fresh or empty. Its location must not overlap the input tree.
``--profile core|full`` defaults to ``full`` in both modes. Repeat ``--case`` to
select the union of stable IDs or glob patterns within that mode and profile; an
unmatched pattern is an error.

The default ``--input-policy strict`` requires the declared inventory for each
selected required case. Unselected families are irrelevant. ``available`` permits
missing families or shorter full-domain sequences and reports partial input coverage.
It does not relax fields, levels, crop geometry, track compatibility, or output
contracts, and cannot shorten the frozen CI fixture.

Cases run sequentially, each in its own spawned worker. ``--keep-going`` is the
default; ``--fail-fast`` leaves later cases explicitly not run after a failure.
The terminal shows startup settings and planning progress, including each input
file being inspected and elapsed time. All selected cases are planned before
execution starts. Worker output is forwarded live to the terminal and retained in
``cases/<case-id>/logs/frameit.log``. During execution, 30 seconds without worker
output triggers an elapsed-time heartbeat with the log path; this is a progress
indicator, not an execution timeout.
``--log-level`` follows the ordinary CLI convention. Use ``--utrack-weights`` for
full-domain UTrack. UTrack is always excluded in CI, including when a checkpoint
is supplied: the cropped fixture does not guarantee its search context or margins.

CI coverage
-----------

The core profile covers BATSIRAI fixed-centre polar extraction and its Cartesian
reference, CHIDO fixed and moving pressure/wind tracking with staggered-grid
collocation, a moving Cartesian reference, and the optional CHIDO prescribed track.
The full CI profile additionally covers all/index/value level selection, surface
and vertical-wind cases, BATSIRAI's generated fixed-position prescribed NetCDF
track, and the CHIDO prescribed Cartesian case.

The external CHIDO track uses exact model/track time intersection. The established
fixture contains model times 11:00, 12:00 and 13:00 on 11 December 2024; only 12:00
matches the external track. No interpolation or timestamp rounding expands this
intersection. A single-time prescribed test does not require motion diagnostics
that need multiple times. ``latitude``/``longitude`` and ``lat``/``lon`` field
names are accepted by the prescribed tracker.

Full-domain coverage
--------------------

The core full-domain profile covers BATSIRAI fixed-centre polar and Cartesian
extraction, BELNA moving pressure/wind tracking, CHIDO fixed and moving tracking,
and an optional external CHIDO prescribed track. The full profile adds BATSIRAI
moving tracking, BELNA fixed tracking, long CHIDO_02 and CHIDO_03 sequences,
the 2-km CHIDO_MXX20 sequence, and optional UTrack.

Results and coverage
--------------------

``PASS`` means that execution and product-contract checks passed. Checks include
the expected product groups, variables, time and level coordinates, finite centre
positions, box geometry, and required derived wind diagnostics. Missing values
are interpreted according to the scenario rather than a universal finite-everywhere
rule. This command does not compare values to a reference simulation.

Polar product checks additionally require a uniform, endpoint-exclusive angular
cycle, radian angles, kilometre radii, consistent degree coordinates and an
explicit open-grid marker. Numerical accuracy and Fourier behaviour are checked
separately by ``tests/test_polar_axes.py`` and
``tests/test_polar_periodic_diagnostics.py``.

Polar outputs must also contain geometric mapping indicators and per-field
support/status/validity arrays, ring coverage and complete-ring eligibility on
the expected dimensions. The independent numerical oracles and scientific
metadata checks are in ``tests/test_polar_contracts.py`` and
``tests/test_polar_coverage.py``.

Numerical tests are packaged in ``src/frameit/testing/numerical`` and run with
``python -m pytest`` or the installed ``run-all-tests`` service. Reusable plan
invariants and chunk equivalence are covered by ``test_polar_regrid_plan.py``
and ``test_polar_dask.py``. A focused cached/uncached benchmark is available as
``python -m frameit.testing.polar_benchmark --output <fresh-directory>``; it
retains separate weight/application/export timings, worker RSS peaks and
numerical equivalence checks. Execution artifacts carry ``regrid_performance``
alongside the existing section timings.

The matrix records optional absence separately from mode exclusions and failed
required coverage. An existing corrupt or incompatible track, a supplied unusable
checkpoint, or an incompatible installed backend is invalid input, not optional
absence. An attempted optional case that fails makes the matrix fail.

.. list-table:: Exit codes
   :header-rows: 1
   :widths: 10 90

   * - Code
     - Meaning
   * - 0
     - Attempted cases succeeded under the requested input policy; consult coverage
       for partial ``available`` runs. Planning-only cases remain planned.
   * - 1
     - Execution, product-contract or input-change failure, or missing required
       inputs under strict policy.
   * - 2
     - Invalid arguments, fixture, selection, backend preflight, or unusable plan.
       A selection with no runnable cases also returns 2 unless strict missing
       required input already requires 1.
   * - 130
     - Interrupted execution.

Artifacts
---------

Each run writes an immutable ``plan.json``, per-case ``result.json`` checkpoints,
an atomic aggregate ``run.json``, and a derived ``summary.tsv``. Generated YAML
configurations can be rerun with ``frameit run``; resolved configurations document
the effective settings. Product descriptors distinguish track, Cartesian and polar
roles and their data groups.

The run records selected, required, optional, excluded, passed, skipped and failed
case IDs; source completeness; checks; worker status; logs; input inventories; and
runtime provenance. Semantic fingerprints include scientific settings and physical
level selections while excluding output locations. Input inventories are consumed
as planned, without a second directory search. File identity is checked before and
after execution. Ordinary size/mtime checks on mutable full-domain inputs do not
provide the same guarantee as verified content hashes or immutable source storage.

Reference comparison and numerical validation
---------------------------------------------

The artifacts are designed to support later ``frameit validate-matrix-test`` and
``frameit full-validation`` services. These commands are not part of this release.
Reference comparison will assess compatible scientific inputs, case contracts and
products across FrameIt versions. The current ``run-all-tests`` command combines
numerical tests with product-contract validation, without reference comparison.

The analytical qualification evaluates source and target truth directly; it is
distinct from a historical simulation-file comparison. The full matrix includes
U-only, V-only, derived-speed-only and scalar-only AROME/MNH products. Product
checks validate finite/support/status masks, coverage fractions and the wind-speed
norm invariant. See :doc:`../polar_projection/scientific_qualification` for the
manufactured fields, numerical gates and scientific interpretation limits.
