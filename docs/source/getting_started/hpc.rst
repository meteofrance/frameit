HPC and Slurm
==============

FrameIt runs one configuration in one Slurm task on one node. Independent cases
can use separate jobs or arrays. Tracking methods can depend on preceding centres
and neighbouring times; arbitrary time splitting is not equivalent. The runner
does not distribute a simulation over MPI ranks or multiple nodes.

Get account, partition/QoS, module setup and scratch-storage rules from your HPC
documentation. Adapt the example CPU, memory and time requests after a pilot run.

Prepare the environment before submitting jobs
------------------------------------------------------------

Use the site-approved environment mechanism. Where conda/mamba is permitted,
from the checkout:

.. code-block:: bash

   conda env create -f environment.yaml --solver libmamba
   conda activate frameit_env
   python -m pip check
   python -m frameit --help

This is the same environment as :doc:`installation`, including FrameIt's
editable installation and the GRIB/FA/polar/Zarr dependencies. Keep a consistent
native-library stack and make the checkout accessible on compute nodes.

Create an activation script using the site's actual module or conda paths.
For a conda installation its content resembles:

.. code-block:: bash

   source /path/to/conda/etc/profile.d/conda.sh
   conda activate frameit_env

Export its absolute path as ``FRAMEIT_ENV_SCRIPT`` before submission; launchers
source it in their noninteractive shell.

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

Tests check synthetic wind values, exports, concurrent attempts, overwrite
protection and cancellation. Products are reopened independently. The tests use
compact generated NetCDF inputs.

Acceptance: successful ``sbatch --wait``, ``result.json`` with ``exit_code: 0``,
and no failed JUnit tests. These are operational/numerical regression checks,
not scientific validation of arbitrary model outputs.

2. Prepare a small representative configuration
------------------------------------------------------------

Choose a short, chronologically ordered real case with the intended input
format, tracker, variables, output engine and polar setting. Keep scientific
settings identical between reference and batch runs. Declare the expected number
of matching timestamps, including any prescribed-track intersection.

Merge this fragment into your configuration:

.. code-block:: yaml

   resources:
     cpus: 1
     scheduler: threads
     compute_workers: 1
     native_threads: 1
     export_workers: 1
     synchronous_export: false
   output:
     overwrite: false

For tracked runs, keep ``region.tracker.on_incomplete: error``.

Spawned exports require Python API callers to protect their entry point with
``if __name__ == "__main__":``. Scripts without that guard can select
``resources.synchronous_export: true``. The ordinary FrameIt CLI already has the
required entry-point guard. Resource scopes are process-wide; run concurrent
independent cases in separate processes.

Run planning after environment activation, in an allocation appropriate to the
input size:

.. code-block:: bash

   python -m frameit validate /absolute/path/case.yaml --schema-only
   python -m frameit validate /absolute/path/case.yaml
   python -m frameit config show /absolute/path/case.yaml --effective

Use the :ref:`estimated RAM allocation <estimate-run-ram>` as an initial
``sbatch --mem`` request, with the same worker counts and output settings.
Measure memory, disk use and runtime in the pilot. The modeled peak and median
are not scheduler-accounted measurements.

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

The checker imports xarray/NetCDF, not FrameIt. It checks compact NetCDF cases
against each source's recorded clock and product dimensions/units.
Zarr is not supported by this checker. It requires a completed manifest, full tracking, no lock,
matching file sizes and readable values. Product identity uses role and source;
centre times follow recorded associations. When a trajectory is exported,
products carrying centres must link to its corresponding samples. It reports
dimensions, units, versions and timing. It fully loads products: use compact
qualification cases. NaNs are
retained, not treated as an automatic failure; evaluate the declared coverage
and missing-data policy separately.
An exported trajectory is optional. ``--expected-times`` checks its count when
present; otherwise it checks each field product's count. Omit this single count
for independently timed sources with different counts; recorded source clocks
are still checked.

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

During quiet work, the progress line reports the operation/source,
completed counts and last recorded activity. Early preparation notices can
appear on standard error before a run log exists. A repeated notice is not
evidence that a native call is advancing or that the run has completed.
See :ref:`execution-progress` for a quiet run.

4. Cancellation, retries and interpreting status
------------------------------------------------------------

``run-status.yaml`` (schema version 1) has states ``running``, ``completed``,
``incomplete``, ``failed`` and ``interrupted``. ``completed`` is written only
after requested exports and input cleanup; its inventory uses relative product
paths and sizes. Check the expected times and permitted masks before using products.
Running checkpoints retain observed complete publications separately from planned
products. ``updated_at`` records a checkpoint, not proof that the process is alive.

Without strict tracking, an accepted shortened trajectory can exit zero but is
marked ``incomplete``. Keep ``region.tracker.on_incomplete: error`` for tracked
batch runs, or require completion through ``--require-complete-tracking``.
The strict policy fails before export. This does not redefine prescribed-track
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

Use ``frameit run-diag config.yaml --check --json`` against the completed
parent before submitting a post-run diagnostic. It uses one CPU with
synchronous computation and does not need an export worker pool. Schedule
the child after its parent; they use the same exclusion lock.

Repeat complete cases
---------------------

Keep one complete YAML per scientific case, including its tracking timeline.
For a local serial loop, with an existing output parent:

.. code-block:: bash

   mkdir -p "$RESULTS/attempts"
   bash "$REPO/example/repeat_cases.sh" "$RESULTS/attempts" \
     /absolute/path/case-a.yaml /absolute/path/case-b.yaml

Each attempt has a unique directory, private ``work/``, ``run/`` records when
execution reaches that stage, and an ``exit-code`` receipt. The loop continues
after an ordinary failed case and returns nonzero if any case failed. Retrying a
YAML creates another attempt and preserves earlier outputs. Interrupted runs
stop the loop rather than starting the next case.

For the equivalent Slurm array, put one absolute YAML path per line in
``cases.txt``. Paths may contain spaces; filenames containing newlines are not
supported. This two-case example caps concurrent tasks at two:

.. code-block:: bash

   printf '%s\n' /absolute/path/case-a.yaml /absolute/path/case-b.yaml > cases.txt
   sbatch --wait --array=0-1%2 --account=ACCOUNT --partition=PARTITION \
     --output="$RESULTS/array-%A_%a.out" \
     "$REPO/example/slurm/array.sbatch" "$PWD/cases.txt" "$RESULTS/attempts" \
     "$REPO/example/slurm/frameit.sbatch"

The explicit final argument identifies the launcher even when Slurm runs a
spool copy of the array script. The array delegates each complete case to it and inherits its
allocation-aware resource handling, fresh-attempt naming and no-overwrite
policy. Collect every array element's exit status, not only the submission
command's status. Local launcher tests exercise the shell/process boundary;
actual scheduling, accounting and filesystem behavior require a site pilot.

Keep the run records
------------------------------------------------------------

Keep job accounting, checker reports and all four :doc:`run records
<../user_guide/output_files>` with the products. ``run-request.yaml`` retains the
authored request, overrides and original path bases even if the original YAML
is edited or moved. For a failed run, include scheduler and FrameIt error logs
when asking for help.
