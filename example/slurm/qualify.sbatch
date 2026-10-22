#!/bin/bash
# Compact synthetic qualification; pilot requests, not production sizing.
#SBATCH --job-name=frameit-check
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=frameit-check-%j.out

set -euo pipefail
if [[ $# != 2 ]]; then
    printf 'Usage: sbatch [site options] qualify.sbatch CHECKOUT EXISTING_RESULTS_PARENT\n' >&2
    exit 2
fi
: "${SLURM_JOB_ID:?Submit this script with sbatch}"
if [[ ${SLURM_NTASKS:-1} != 1 || ${SLURM_CPUS_PER_TASK:-1} -lt 2 ]]; then
    printf 'Qualification requires one task and at least two CPUs.\n' >&2
    exit 2
fi
if [[ -n ${FRAMEIT_ENV_SCRIPT:-} ]]; then
    source "$FRAMEIT_ENV_SCRIPT"
fi
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
checkout=$(python -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$1")
parent=$(python -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$2")
test_dir="$checkout/src/frameit/testing/numerical"
[[ -f $test_dir/test_hpc_execution.py && -d $parent && -w $parent ]]
results=$(mktemp -d "$parent/qualification-${SLURM_JOB_ID}-XXXXXX")
printf 'FrameIt qualification results: %s\n' "$results"
cd "$results"
python -c 'import json; from frameit.core.runtime import runtime_provenance; print(json.dumps(runtime_provenance(), indent=2))' > runtime.json
python -m pip list --format=json > packages.json
rc=0
srun --nodes=1 --ntasks=1 python -m pytest -q \
    "$test_dir/test_hpc_execution.py" "$test_dir/test_logging.py" \
    --basetemp="$results/pytest" --junitxml="$results/junit.xml" || rc=$?
python -c 'import json, sys; print(json.dumps({"exit_code": int(sys.argv[1]), "scope": "synthetic single-node batch qualification"}, indent=2))' "$rc" > result.json
exit "$rc"
