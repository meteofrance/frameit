HPC and Slurm qualification (including Belenos)
============================================================

FrameIt runs one configuration in one Slurm task on one node. Independent cases
can use separate jobs or arrays. Tracking methods can depend on preceding centres
and neighbouring times; arbitrary time splitting is not equivalent. The runner
does not distribute a simulation over MPI ranks or multiple nodes.

The repository supplies portable launchers, not a verified Belenos site profile.
Obtain the current account, partition/QoS, environment/module setup, and work or
scratch storage/purge policy from the site's documentation. Example CPU, memory
and time requests are pilot values, not measured production requirements.

Prepare the environment before submitting jobs
------------------------------------------------------------

Use the site-approved environment mechanism. Where conda/mamba is permitted,
from the checkout:

.. code-block:: bash

   conda env create -f environment-hpc.yaml
   conda activate frameit_hpc
   python -m pip install --no-deps -e .
   python -m frameit --help

The base environment includes NetCDF processing and pytest, without ESMF,
plotting or documentation dependencies. Add only the selected execution paths:

.. code-block:: bash

   # For GRIB inputs:
   conda install -n frameit_hpc -c conda-forge cfgrib eccodes
   # When polar.enabled is true:
   conda install -n frameit_hpc -c conda-forge xesmf esmpy

Core pip runtime dependencies are also declared. The ``polar`` pip extra adds
xESMF but does not provision its required native ESMF installation. Use a
consistent native-library/MPI stack. Launchers perform no package installation
or downloads during processing.

Create an activation script using the site's actual module or conda paths.
For a conda installation its content resembles:

.. code-block:: bash

   source /path/to/conda/etc/profile.d/conda.sh
   conda activate frameit_hpc

Export its absolute path as ``FRAMEIT_ENV_SCRIPT`` before submission; launchers
source it in their noninteractive shell. Keep the environment and checkout
accessible on compute nodes. After qualification, retain ``conda list --explicit``
and the checkout revision with the run records. A source checkout records its
revision and dirty flag automatically. Wheels without a checkout record no
revision unless ``FRAMEIT_CODE_REVISION`` is supplied as an explicitly unverified
environment claim.

1. Run the compact batch qualification
------------------------------------------------------------

Substitute actual site values below. ``REPO`` and ``RESULTS`` are absolute paths;
the scheduler log directory must already exist before ``sbatch``.

.. code-block:: bash

   export REPO=/path/to/frameit
   export RESULTS=/path/to/work/frameit-qualification
   export FRAMEIT_ENV_SCRIPT=/path/to/activate-frameit.sh
   mkdir -p "$RESULTS"
   sbatch --wait --account=ACCOUNT --partition=PARTITION \
     --output="$RESULTS/qualification-%j.out" \
     "$REPO/example/slurm/qualify.sbatch" "$REPO" "$RESULTS"

The script prints a unique ``qualification-JOBID-*`` directory and preserves
pytest's exit status. It retains:

* ``result.json``: overall exit code and scope;
* ``junit.xml``: individual test results;
* ``runtime.json`` and ``packages.json``: versions and selected Slurm allocation
  metadata, without dumping the environment;
* ``pytest/``: compact fixtures, products, manifests and checker reports.

Tests exercise real CLI spawned and synchronous exports, simultaneous isolated
attempts, same-root exclusion, no-clobber races, failed writes, incomplete-track
policy, SIGTERM and SIGKILL. They check known synthetic wind values and
independently reopen products. They require no GRIB, ESMF, GPU or private data.
Simulated Slurm variables inside individual tests are test inputs;
``runtime.json`` captures the actual enclosing allocation.

Acceptance: successful ``sbatch --wait``, ``result.json`` with ``exit_code: 0``,
and no failed JUnit tests. These are operational/numerical regression checks,
not scientific validation of arbitrary model outputs.

2. Prepare a small representative configuration
------------------------------------------------------------

Choose a short, chronologically ordered real case with the intended input
format, tracker, variables, output engine and polar setting. Keep scientific
settings identical between reference and batch runs. Declare the expected number
of matching timestamps, including any prescribed-track intersection.

Merge this fragment into the existing schema-v2 configuration:

.. code-block:: yaml

   execution:
     dask_scheduler: threads
     dask_workers: 1
     native_threads: 1
     require_complete_tracking: true
   output:
     overwrite: false
     max_workers: 1
     synchronous_export: false

Spawned exports require Python API callers to protect their entry point with
``if __name__ == "__main__":``. Scripts without that guard can select
``output.synchronous_export: true``. The ordinary FrameIt CLI already has the
required entry-point guard. Resource scopes are process-wide; run concurrent
independent cases in separate processes.

Run planning after environment activation, in an allocation appropriate to the
input size:

.. code-block:: bash

   python -m frameit validate /absolute/path/case.yaml --schema-only
   python -m frameit validate /absolute/path/case.yaml
   python -m frameit run /absolute/path/case.yaml --dry-run

Planning reports effective execution resources without writing artifacts.
It does not test native-backend initialization or establish memory/disk quotas.

3. Submit and independently check the real pilot
------------------------------------------------------------

.. code-block:: bash

   sbatch --wait --account=ACCOUNT --partition=PARTITION \
     --output="$RESULTS/pilot-%j.out" \
     "$REPO/example/slurm/frameit.sbatch" /absolute/path/case.yaml "$RESULTS"

The log prints a unique attempt root. Products/manifests are under ``run/``;
native backends also get a private ``work/`` directory. The launcher explicitly
requires no-overwrite and complete-tracking policies. Each retry/requeue creates
a fresh attempt. The output override is launch-directory-relative; original
YAML paths remain YAML-relative. YAML does not expand ``$SLURM_JOB_ID``.

Independently reopen every listed product, supplying the known time count:

.. code-block:: bash

   python "$REPO/example/slurm/check_run.py" /path/to/attempt/run \
     --expected-times N --report "$RESULTS/pilot-check.json"

The checker imports xarray/NetCDF, not FrameIt. It requires a completed manifest,
full tracking, no lock, matching file sizes, readable values, matching time
coordinates, and valid track-file links. It reports dimensions, units, versions
and timing. It fully loads products: use compact qualification cases. NaNs are
retained, not treated as an automatic failure; evaluate the declared coverage
and missing-data policy separately.

For a concurrency regression reference, run the same case in the same
allocation/environment with ``--synchronous-export`` and a fresh
``--output-directory``. Add ``--reference /path/to/reference/run`` to the checker.
It requires exact decoded values, coordinates and variable attributes, allowing
global histories/run metadata to differ. This is not bitwise file identity.
Investigate differences across native stacks and justify quantity-specific
tolerances rather than automatically weakening the check.

Collect actual job and step accounting:

.. code-block:: bash

   sacct -j JOBID --format=JobID,State,ExitCode,Elapsed,AllocCPUS,ReqMem,MaxRSS

Acceptance: scheduler/process success, successful checker, expected time
coverage and scientifically permitted masks, and measured memory/time headroom.
MaxRSS is accounting-plugin/step dependent and need not sum all worker peaks.
Retain resource records and increase input size gradually before selecting
production requests. Chunking does not bound the whole run: GRIB, tracking
preparation, caches and export have separate costs.

4. Cancellation, retries and interpreting status
------------------------------------------------------------

``run-status.yaml`` (schema version 1) has states ``running``, ``completed``,
``incomplete``, ``failed`` and ``interrupted``. ``completed`` is written only
after requested exports and input cleanup; its inventory uses relative product
paths and sizes. It does not establish input content identity or scientific
validity.

Without strict tracking, an accepted shortened trajectory can exit zero but is
marked ``incomplete``. ``execution.require_complete_tracking: true`` or the
matching CLI flag fails before export. This does not redefine prescribed-track
intersections, NaN padding, or tracker fallbacks; still check expected times
and scientifically permitted coverage.

Cancel a disposable pilot with ``scancel JOBID`` and inspect its attempt.
Ordinary SIGTERM permits an ``interrupted`` record and exit 143 when Python
cleanup finishes within the scheduler grace period. Forced kills, native crashes
or node loss can leave ``running``, a lock and hidden ``*.partial`` files.
Neither case is complete. Cleanup is best-effort, especially while waiting for
export workers or native calls.

NetCDF/YAML publication uses same-directory temporary files and POSIX atomic
rename/hard-link operations. These require filesystem support, are not a
power-loss durability guarantee, and do not form a multi-product transaction.
New files honor the job's umask; overwrites retain the previous file permissions.
Earlier complete products may remain after a later export fails. Filenames or
provenance alone do not establish completion.

Use fresh attempts for retries. Never automatically steal ``.frameit-run.lock``;
confirm its owner has stopped before manual removal. ``overwrite: true`` keeps
its existing sequential-rerun meaning and may leave older unlisted products;
use the current manifest inventory.

Return these results for review
------------------------------------------------------------

Provide job IDs/accounting, qualification ``result.json`` and ``junit.xml``,
runtime/package versions, and the real pilot checker JSON plus configuration
and run status/provenance. Include expected times, input scale, selected tracker
and polar settings, and coverage questions. Failed checks need their scheduler
and FrameIt error logs. No Belenos success is established until cluster results
are available.
