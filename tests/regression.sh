#!/usr/bin/env bash
# Build, solve the golden layers, assert byte-identical monoliths + passing selftest.
set -euo pipefail
cd "$(dirname "$0")/.."
MANIFEST=layers/compressed/compression_map.txt
LAYERS="48 46 44 40"
MODE="${1:-auto}"   # forwarded as BESTEMSHE_STORE_MODE (honored from Task 3 on)
g++-16 -O3 -std=c++17 -fopenmp -I/opt/homebrew/include -L/opt/homebrew/lib \
  main.cpp Solver.cpp Inference.cpp Splitter.cpp Compressor.cpp -llz4 -lzstd -o bestemshe
fail=0
for M in $LAYERS; do
  BESTEMSHE_STORE_MODE="$MODE" ./bestemshe --solve "$M" "$MANIFEST" >/dev/null
  for T in win draw; do
    if cmp -s "layers/layer${M}_${T}.bin" "tests/golden/layer${M}_${T}.bin"; then
      echo "  M=$M $T  OK"
    else
      echo "  M=$M $T  MISMATCH"; fail=1
    fi
    rm -f "layers/layer${M}_${T}.bin"
  done
done
for M in 48 46 44; do
  if ./bestemshe --selftest "$M" | grep -q "SELFTEST PASS"; then echo "  selftest M=$M OK"; else echo "  selftest M=$M FAIL"; fail=1; fi
done
if [ "$fail" -eq 0 ]; then echo "REGRESSION PASS (mode=$MODE)"; else echo "REGRESSION FAIL"; exit 1; fi
