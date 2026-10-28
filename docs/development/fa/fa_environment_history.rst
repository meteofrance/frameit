.. note::

   Frozen developer evidence from 9b11d602c4fb05fb2adf74b699439de6a0b8625b.
   Commands, support statements and results below describe historical checkpoints.
   See the `developer index <README.md>`_ for current topics and the removal plan.

One Conda environment, isolated FA processes
======================================================================

``environment.yaml`` now installs FrameIt and the reference FA/GRIB/NetCDF/polar
stack in **one Python-3.13 environment**. No virtual-environment overlay or helper
installation is required. FA still runs in a fresh, FA-only worker process using
the active Python; GRIB/NetCDF/ESMF remain in the consuming process. Matching
package versions are not evidence that FA and GRIB native libraries can safely
share one process, and that boundary has not changed.

This follows the C5 distribution/resource snapshot at ``0a328b7``. The finite
scientific families and all scaling, source/type/time, geometry, mask, spectral,
resource and selected-only execution guards remain unchanged. Optional installed
diagnostics do not execute merely because their inputs or packages are present.

Install and migrate
--------------------

From the checkout containing ``environment.yaml``:

.. code-block:: bash

   conda env create -f environment.yaml --solver libmamba
   conda activate frameit_env
   python -m pip check
   frameit --help

The pip section installs this checkout in editable mode with its maintained FA,
GRIB, polar and test extras, plus development/documentation tools. Conda owns the
shared native I/O libraries. The Python ``netCDF4==1.7.2`` and ``eccodes==2.44.0``
requirements match unmodified EPyGrAM 2.1.0; pip therefore retains those Conda
packages instead of replacing them with wheel-bundled native libraries.
``python-eccodes`` is the Conda Python binding, distinct from the native ``eccodes``
library package. Their version numbers need not be identical. The tested solution
uses serial ESMF and a shared Conda HDF5/NetCDF family; resolved builds/versions are
recorded below. ``dask-core`` supplies the existing array/threaded workflows;
``matplotlib-base`` supplies plotting without introducing a GUI toolkit.

For an older mixed installation, preserve it and create a fresh named environment:

.. code-block:: bash

   conda env create -f environment.yaml --solver libmamba -n frameit_unified
   conda activate frameit_unified

Do not copy a helper path into new input YAML. Omit ``input.fa.python_executable``
or set it to null to use the current Python automatically. Existing explicit
paths, YAML-relative resolution, interpreter symlinks, legacy backend aliases and
resolved-configuration replay remain supported. A deliberately separate runtime
must still contain FrameIt and the qualified FA stack; it is not a fallback.
Editable installation continues to use this checkout, so retain it or install a
built wheel when deploying a detached package.

Standalone core pip installations and the minimal HPC environment remain separate
supported choices; core-only CI still verifies genuine absence of native extras.
The reference environment does not add optional model weights or admit new methods.

Native lifetime evidence and limits
------------------------------------

The C4/C5 old overlay still fails after a bounded AROME polar matrix case finishes:
normal processing prints success, then native teardown aborts. Its netCDF4 wheel
loads HDF5 1.14.2 / NetCDF 4.9.4-development alongside Conda HDF5 1.14.6 / NetCDF
4.10.1 from the MPI stack. Five smaller I/O/regrid probes exit normally, so merely
importing these modules is not a sufficient reproduction or qualification test.

The fresh reference environment loads one Conda HDF5 1.14.6 / NetCDF 4.9.3 family
for netCDF4, h5py and ESMF. Its six-case GRIB/NetCDF/polar matrix exits normally.
Compact primary-pair tests also execute real GRIB containers with EPyGrAM-decoded
SURFEX, independent grids, exact common times, moving centres and a shared bilinear
target, using both synchronous and spawned export. They omit the helper override,
observe actual worker launches through ``sys.executable``, reopen products with
fresh ordinary readers against independent prescribed values/masks/indices, check
provenance and replay, preserve source bytes, and require the outer process to exit
zero after native teardown.

Controls with a same-version netCDF4 pip wheel in a fresh serial stack, and a fresh
MPI/wheel stack, also exit normally for the bounded AROME case. Consequently there
is **no demonstrated single-package cause or universal MPI/wheel incompatibility**.
The original old installation's precise native fault remains unlocalized; the
supported remedy is a measured fresh installation, not an import-order workaround,
suppressed exit or claim that the old prefix has been repaired. Other platforms,
unlocked future resolutions and arbitrary package mixtures need their own checks.
The initial wildcard ESMF-build constraint and several dry-run solves timed out;
the tested YAML relies on compatible Conda dependency resolution and uses libmamba.

The inspection-only EPyGrAM GRIB probe now reports absent pip-only ``eccodeslib``
metadata as null. Conda's binding remains required, and the probe still records
the actual ecCodes C API version. No alternate GRIB reader, optional native failure
suppression or scientific conversion is introduced.

Verification and provenance
----------------------------

The manifest records clean creation from the canonical YAML, actual dependency
and native-library versions, tests, normal process exits, initial failures and
unavailable checks. Existing run provenance retains actual parent/worker versions,
source-qualified descriptors and the effective null/default helper selection.
No scientific output schema, unit, missing policy, precision, compression, chunking
or scientific default changes. Existing compact fixtures verify the engineering
contracts; producer-specific scaling/units/support/Earth-model evidence and human
scientific review remain the separate limits described in `fa_inputs <fa_inputs_history.rst>`_.

Required CI creates this same environment file, checks Conda ownership and exact
EPyGrAM requirements, exercises normal default-interpreter lifetime, preserves
full/native/core-only gates and runs wheel-installed generated primary-pair tests.
Ignored real CI fixture binaries are not downloaded, committed or uploaded by this
change; full real-fixture checks require the existing authorized local corpus.

Local verification reports **708 passed, 3 absence-only skips and 2 subtests** in
the complete suite; native CI checks **221 passed / 3 absence-only skips**;
core-only checks **110 passed / 138 dependency-only skips / 2 subtests**; and
spectral-candidate checks **31 passed**. Wheel-installed primary-pair/lifetime/
resource checks pass **18 cases**, and all six packaged matrix cases finish with
a normal outer process exit. Four schema examples, a default-interpreter shared-
target dry-run, strict docs, changed-file lint, dependency/ownership checks and
wheel/source parity also pass. Repository lint retains the four unchanged
``conservative.py`` findings reproduced from HEAD. The final wheel rebuild adds
the completed evidence metadata to the same tested implementation. Hosted CI,
Python 3.10 locally, other platforms and the precise old-prefix native fault
remain unverified; no required installed backend or valid regression is skipped.

.. literalinclude:: ../../../src/frameit/testing/catalogs/fa_environment.yaml
   :language: yaml
