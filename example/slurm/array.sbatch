#!/bin/bash
# One complete YAML per element; adapt these pilot resources to your site.
#SBATCH --job-name=frameit-array
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=frameit-%A_%a.out
set -euo pipefail
if [[ $# != 3 || ! ${SLURM_ARRAY_TASK_ID:-} =~ ^(0|[1-9][0-9]*)$ ]]; then
    printf 'Usage: sbatch --array=0-N array.sbatch CONFIG_LIST OUTPUT_PARENT ABSOLUTE_LAUNCHER\n' >&2
    exit 2
fi
mapfile -t configs < "$1"
index=$SLURM_ARRAY_TASK_ID
if (( index < 0 || index >= ${#configs[@]} )) || [[ ${configs[index]} != /* ]]; then
    printf 'Array index must select an absolute YAML path, one per line.\n' >&2
    exit 2
fi
[[ $3 == /* && -f $3 ]] || exit 2
# Slurm runs a spool copy, so its directory does not identify the checkout.
exec bash "$3" "${configs[index]}" "$2"
