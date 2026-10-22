#!/bin/bash
# Conservative pilot requests; override with measured, site-approved resources.
#SBATCH --job-name=frameit
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=frameit-%A_%a.out

set -euo pipefail

if [[ $# != 2 ]]; then
    printf 'Usage: sbatch [site options] frameit.sbatch CONFIG.yaml EXISTING_OUTPUT_PARENT\n' >&2
    exit 2
fi
: "${SLURM_JOB_ID:?Submit this script with sbatch}"
if [[ ${SLURM_NTASKS:-1} != 1 ]]; then
    printf 'FrameIt requires one Slurm task per configuration.\n' >&2
    exit 2
fi

# This user-supplied script activates the tested site environment/modules.
if [[ -n ${FRAMEIT_ENV_SCRIPT:-} ]]; then
    source "$FRAMEIT_ENV_SCRIPT"
fi
export PYTHONNOUSERSITE=1
export PYTHONUNBUFFERED=1
# Set these before importing Python's native scientific libraries.
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
export MPLBACKEND=Agg

config=$(python -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$1")
parent=$(python -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$2")
if [[ ! -d $parent || ! -w $parent ]]; then
    printf 'Output parent must be an existing writable directory: %s\n' "$parent" >&2
    exit 2
fi
attempt=$(mktemp -d "$parent/frameit-${SLURM_JOB_ID}-${SLURM_ARRAY_TASK_ID:-0}-r${SLURM_RESTART_COUNT:-0}-XXXXXX")
mkdir "$attempt/work"
printf 'FrameIt attempt: %s\n' "$attempt"

# Give optional native backends a private working directory too. All YAML paths
# remain relative to the original YAML, not this working directory.
cd "$attempt/work"
exec srun --nodes=1 --ntasks=1 \
    python -u -m frameit run "$config" \
    --output-directory "$attempt/run" --no-overwrite --require-complete-tracking
