#!/usr/bin/env bash
# Smoke tests for the Bestemshe repository.
#
#   scripts/smoke.sh                        tiers 0 and 1
#   scripts/smoke.sh --offline              tier 0 only (no network)
#   scripts/smoke.sh --with-tablebase DIR   also tier 2 (needs the 8.3 GB layers)
#   scripts/smoke.sh --with-model           also tier 3 (needs torch + a model download)
#
# Tier 0  offline    build, imports, encoding correctness, artefact integrity
# Tier 1  network    the published tablebase over HTTP Range
# Tier 2  local data the full-size checks and the C++ puzzle extractors
# Tier 3  model      ResMLP inference from the Hugging Face Hub
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)

RUN_NETWORK=1
TABLEBASE=""
WITH_MODEL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --offline)         RUN_NETWORK=0; shift ;;
    --with-tablebase)  TABLEBASE="${2:?--with-tablebase needs a directory}"; shift 2 ;;
    --with-model)      WITH_MODEL=1; shift ;;
    -h|--help)         sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

PASS=0; FAIL=0; SKIP=0
LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT

check() {           # check <name> <command...>
  local name="$1"; shift
  printf '  %-52s' "$name"
  if "$@" >"$LOG" 2>&1; then
    echo "PASS"; PASS=$((PASS + 1))
  else
    echo "FAIL"; FAIL=$((FAIL + 1))
    sed 's/^/      | /' "$LOG" | tail -25
  fi
}

skip() { printf '  %-52s%s\n' "$1" "SKIP ($2)"; SKIP=$((SKIP + 1)); }

# Helpers that need a shell body get their own function so `check` stays simple.
query_usage_is_rejected() { ! ./build/query >/dev/null 2>&1; }

no_cyrillic_left() {
  ! grep -rlP '[\x{0400}-\x{04FF}]' training evaluation tasks tests 2>/dev/null | grep -q .
}

start_position_is_a_loss() {
  local out
  out=$(python3 -m tasks.oracle_client 0 0 5 5 5 5 5 5 5 5 5 5 2>&1) || return 1
  echo "$out"
  echo "$out" | tail -1 | grep -qx loss
}

echo "=============================================================="
echo " Tier 0 — offline (no network, no tablebase, no torch)"
echo "=============================================================="
check "cmake configure"            cmake -S cpp_solver -B build
check "cmake build (4 binaries)"   cmake --build build -j
check "binary: bestemshe"          test -x build/bestemshe
check "binary: query"              test -x build/query
check "binary: generateTasks"      test -x build/generateTasks
check "binary: generateVictory"    test -x build/generateVictory
check "query rejects empty args"   query_usage_is_rejected
check "python imports"             python3 -c \
  "import training.bestemshe_core, training.make_shards, training.train, \
          tasks.oracle_client, tasks.opening_tree, tasks.find_draw_cycles, \
          tasks.find_forced_wins"
check "rank/unrank self-test"      python3 -m training.make_shards --selftest
check "pytest: encoding + rules"   python3 -m pytest tests/test_selftest.py -q
check "no untranslated Cyrillic"   no_cyrillic_left
check "evaluation artefacts parse" python3 - <<'PY'
import json
r = json.load(open("evaluation/vs_god_results.json"))
assert 0.99 <= r["optimal_move_rate"] <= 1.0, r["optimal_move_rate"]
assert r["n_games"] == 2000, r["n_games"]
h = json.load(open("evaluation/eval_history.json"))
assert h["n_checkpoints"] == len(h["checkpoints"])
assert h["checkpoints"] == sorted(h["checkpoints"], key=lambda c: c["step"])
PY

if [ "$RUN_NETWORK" = 1 ]; then
  echo
  echo "=============================================================="
  echo " Tier 1 — the published tablebase over HTTP Range"
  echo "=============================================================="
  check "start position evaluates to LOSS" start_position_is_a_loss
  check "pytest: Bellman identity"         python3 -m pytest tests/test_bellman.py -q
  check "opening tree, depth 1"            python3 -m tasks.opening_tree --depth 1
else
  echo; echo " Tier 1 skipped (--offline)"
fi

if [ -n "$TABLEBASE" ]; then
  echo
  echo "=============================================================="
  echo " Tier 2 — local tablebase: $TABLEBASE"
  echo "=============================================================="
  if [ -d "$TABLEBASE" ]; then
    export BESTEMSHE_DATA_DIR="$TABLEBASE"
    check "pytest: full-size Bellman"  python3 -m pytest tests/test_bellman.py -q
    check "consistency sweep (2000)"   python3 -m training.make_shards --tb "$TABLEBASE" --verify 2000
    check "puzzle extraction"          python3 -m tasks.find_forced_wins --plies 3 --search 50
  else
    skip "tier 2" "$TABLEBASE is not a directory"
  fi
fi

if [ "$WITH_MODEL" = 1 ]; then
  echo
  echo "=============================================================="
  echo " Tier 3 — ResMLP inference (downloads the model from HF)"
  echo "=============================================================="
  check "infer.py on the start position" python3 - <<'PY'
from training.infer import load_model, evaluate_position
model, step = load_model("ansarzeinulla/bestemshe-resmlp")
r = evaluate_position(model, pits=[5] * 10, kazan_self=0, kazan_opp=0)
total = r["p_loss"] + r["p_draw"] + r["p_win"]
assert abs(total - 1.0) < 1e-4, total
assert 1 <= r["best_move"] <= 5, r["best_move"]
print(f"step={step} loss={r['p_loss']:.4f} draw={r['p_draw']:.4f} "
      f"win={r['p_win']:.4f} best_move={r['best_move']}")
PY
fi

echo
echo "=============================================================="
printf ' %d passed, %d failed, %d skipped\n' "$PASS" "$FAIL" "$SKIP"
echo "=============================================================="
[ "$FAIL" -eq 0 ]
