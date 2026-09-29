#!/bin/bash
# The seven same-start benchmark runs (fix 4), in chunks you can stop and restart.
#
#   bash bes_run_day.sh          work for 120 minutes, then stop cleanly
#   bash bes_run_day.sh 45       work for 45 minutes
#   bash bes_run_day.sh 0        no time limit: run until all seven are finished
#
# Ctrl+C is safe at any moment: every finished start position is already on disk,
# and re-running this script continues from the next one. Finished runs are
# skipped. Overrides: TB=... M=... N=... bash bes_run_day.sh 60
#
# Run it under caffeinate so the Mac does not sleep mid-run:
#   caffeinate -i bash bes_run_day.sh 120

set -u
# Work in the repository root: $BESTEMSHE, else the parent of this script if that
# is the repository, else the default location.
here=$(cd "$(dirname "$0")" && pwd)
if [ -n "${BESTEMSHE:-}" ]; then root=$BESTEMSHE
elif [ -f "$here/../evaluation/vs_god.py" ]; then root=$here/..
else root=$HOME/Desktop/Bestemshe
fi
cd "$root" || exit 1

BUDGET=${1:-120}
TB=${TB:-layers/compressed}
M=${M:-$HOME/Desktop/Bestemshe-Ai/latest.pt}
N=${N:-1000}
LOG=runs/log.txt
mkdir -p runs runs_cap1000

[ -e "$TB" ] || { echo "tablebase not found at $TB (fix 4, step 1)"; exit 1; }
[ -e "$M" ]  || { echo "checkpoint not found at $M"; exit 1; }

END=$(( $(date +%s) + BUDGET * 60 ))

run() {
    out=$1; shift
    limit=""
    if [ "$BUDGET" -gt 0 ]; then
        left=$(( END - $(date +%s) ))
        if [ "$left" -le 60 ]; then
            echo "--- time budget spent; stopping before $out. Re-run this script to continue."
            exit 3
        fi
        limit="--stop-after $(awk -v s="$left" 'BEGIN{printf "%.2f", s/60}')"
    fi
    echo "=== $out  $*  ($(date '+%H:%M')) ==="
    python3 -m evaluation.vs_god --tb "$TB" --model "$M" --n "$N" --seed 42 \
        --out "$out" $limit "$@" 2>&1 | tee -a "$LOG"
    st=${PIPESTATUS[0]}
    case "$st" in
        0)   echo "--- $out finished" ;;
        3)   echo "--- stopped on the time budget. Re-run this script to continue."; exit 3 ;;
        130|2) echo "--- interrupted. Nothing is lost; re-run this script to continue."; exit 130 ;;
        *)   echo "--- $out FAILED (exit $st). Stopping; later runs were not started."; exit "$st" ;;
    esac
}

run runs/search3.json          --mover search --depth 3
run runs/policy.json           --mover policy
run runs/random.json           --mover random
run runs/search1.json          --mover search --depth 1
run runs/search5.json          --mover search --depth 5
run runs/search5avg.json       --mover search --depth 5 --backup avg
run runs_cap1000/search3.json  --mover search --depth 3 --max-plies 1000

echo
echo "ALL SEVEN RUNS FINISHED. Next: bes_table.py (fix 4, step 3)."
