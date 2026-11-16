#!/bin/bash
# One complete YAML per case; tracking timelines are never split.
set -euo pipefail
if [[ $# -lt 2 ]]; then
    printf 'Usage: bash repeat_cases.sh EXISTING_OUTPUT_PARENT CONFIG.yaml [CONFIG.yaml ...]\n' >&2
    exit 2
fi
parent=$(python -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve(strict=True))' "$1")
shift
[[ -d $parent && -w $parent ]] || exit 2
result=0
child=
attempt=
interrupt() {
    trap - INT TERM
    if [[ -n $child ]]; then
        kill -TERM "$child" 2>/dev/null || true
        wait "$child" || true
    fi
    if [[ -n $attempt && ! -f $attempt/exit-code ]]; then
        printf '%s\n' "$1" > "$attempt/exit-code"
    fi
    exit "$1"
}
trap 'interrupt 130' INT
trap 'interrupt 143' TERM
for file in "$@"; do
    config=$(python -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$file")
    attempt=$(mktemp -d "$parent/frameit-local-XXXXXX")
    mkdir "$attempt/work"
    (cd "$attempt/work" && exec python -m frameit run "$config" \
        --output-directory "$attempt/run" --no-overwrite --require-complete-tracking) &
    child=$!
    if wait "$child"; then
        code=0
    else
        code=$?
        result=1
    fi
    child=
    printf '%s\n' "$code" > "$attempt/exit-code"
    printf 'Case: %s | exit: %s | attempt: %s\n' "$config" "$code" "$attempt"
    attempt=
    if [[ $code == 130 || $code == 143 ]]; then
        exit "$code"
    fi
done
exit "$result"
