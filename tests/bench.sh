#!/usr/bin/env bash
# Print value-iteration wall time for a layer, for before/after throughput comparison.
set -euo pipefail
cd "$(dirname "$0")/.."
M="${1:-40}"; MODE="${2:-auto}"
MANIFEST=layers/compressed/compression_map.txt
BESTEMSHE_STORE_MODE="$MODE" ./bestemshe --solve "$M" "$MANIFEST" 2>&1 | grep -E "Total Value Iteration"
rm -f "layers/layer${M}_win.bin" "layers/layer${M}_draw.bin"
