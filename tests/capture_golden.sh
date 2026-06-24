#!/usr/bin/env bash
# Capture golden monoliths from the CURRENT (pre-Phase-1) binary. Run ONCE.
set -euo pipefail
cd "$(dirname "$0")/.."
MANIFEST=layers/compressed/compression_map.txt
LAYERS="48 46 44 40"
mkdir -p tests/golden
g++-16 -O3 -std=c++17 -fopenmp -I/opt/homebrew/include -L/opt/homebrew/lib \
  main.cpp Solver.cpp Inference.cpp Splitter.cpp Compressor.cpp -llz4 -lzstd -o bestemshe
for M in $LAYERS; do
  ./bestemshe --solve "$M" "$MANIFEST" >/dev/null
  cp "layers/layer${M}_win.bin"  "tests/golden/layer${M}_win.bin"
  cp "layers/layer${M}_draw.bin" "tests/golden/layer${M}_draw.bin"
  rm -f "layers/layer${M}_win.bin" "layers/layer${M}_draw.bin"
done
echo "golden captured for layers: $LAYERS"
