#!/bin/bash
# solve_playbook.sh - Automates Pairwise Solving & ZSTD Compression
# Usage: ./solve_playbook.sh <M> <K1> <K2>

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <M> <K1> <K2>"
    exit 1
fi

M=$1
K1=$2
K2=$3
MANIFEST="layers/compressed/compression_map.txt"
STATS_CSV="layers/stats_zstd.csv"
BLOCK_SIZE_BITS=33554432

echo "========================================================"
echo "   BESTEMSHE PAIRWISE SOLVER PIPELINE"
echo "   Solving Pair ($K1, $K2) in Layer M = $M"
echo "========================================================"

# 1. SOLVE THE SYMMETRIC PAIR (Generates raw files directly)
./bestemshe --solve-pair $M $K1 $K2 $MANIFEST
if [ $? -ne 0 ]; then
    echo "FATAL ERROR: Solve failed."
    exit 1
fi

# Determine which files were generated (handles symmetric vs asymmetric pairs)
if [ "$K1" -eq "$K2" ]; then
    PAIRS=("$K1 $K1")
else
    PAIRS=("$K1 $K2" "$K2 $K1")
fi

# 2. COMPRESS THE GENERATED RAW FILES
for pair in "${PAIRS[@]}"; do
    read -r k1 k2 <<< "$pair"
    k_str="${k1}_${k2}"
    
    for type in "win" "draw"; do
        raw_file="layers/layer_${k_str}_${type}.raw"
        zstd_file="layers/compressed/layer_${k_str}_${type}.bin"
        
        if [ -f "$raw_file" ]; then
            echo "[COMPRESSING] $raw_file -> $zstd_file"
            
            # Compress using ZSTD
            ./bestemshe --compress "$raw_file" "$zstd_file" ZSTD $BLOCK_SIZE_BITS
            if [ $? -ne 0 ]; then
                echo "FATAL ERROR: Compression failed."
                exit 1
            fi
            
            # Update the manifest file
            echo "$k1 $k2 $type ZSTD $BLOCK_SIZE_BITS" >> "$MANIFEST"
            
            # Record Compression Statistics in your CSV
            raw_sz=$(stat -f%z "$raw_file" 2>/dev/null || stat -c%s "$raw_file")
            zstd_sz=$(stat -f%z "$zstd_file" 2>/dev/null || stat -c%s "$zstd_file")
            ratio=$(echo "scale=4; $raw_sz / $zstd_sz" | bc)
            
            echo "$M,$k1,$k2,$type,$raw_sz,$zstd_sz,$ratio" >> "$STATS_CSV"
            
            # Remove the raw file safely
            rm "$raw_file"
        fi
    done
done

echo "[SUCCESS] Pair ($K1, $K2) fully processed and compressed."
echo "--------------------------------------------------------"