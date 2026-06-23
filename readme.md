
---

# `README.md`



g++-16 -O3 -std=c++17 pipeline.cpp -o pipeline


# Bestemshe Retrograde Solver Pipeline

A high-performance, block-compressed, $O(1)$ random-access retrograde analysis engine designed to strongly solve the 50-stone mancala variant **Bestemshe**. The architecture decouples solving, splitting, and multi-algorithm compression to run billions of state calculations efficiently within consumer-grade hardware RAM limits.

---

## 1. Prerequisites (macOS Apple Silicon)

Ensure GNU GCC (for native OpenMP support) and the LZ4 compression library are installed via Homebrew:

```bash
brew install gcc lz4 zstd
```

---

## 2. Compilation

Compile the optimized, parallelized binary with aggressive compiler optimizations (`-O3`) and explicit Homebrew library search directories:

```bash
g++-16 -O3 -std=c++17 -fopenmp -I/opt/homebrew/include -L/opt/homebrew/lib \
  main.cpp Solver.cpp Inference.cpp Splitter.cpp Compressor.cpp \
  -llz4 -lzstd -o bestemshe
```

---

## 3. The 5-Step Layer Lifecycle Pipeline

Solving the game requires computing layers backwards from $M=48$ down to $M=0$. For each layer $M$, you must execute the following 5-step lifecycle:

### Step 1: Solve the Layer
Compute the retrograde dependency grid for layer $M$. In-memory calculations are executed in parallel across CPU threads.
* **Command Syntax:** `./bestemshe --solve <M> <manifest_path>`
* **Execution:**
  ```bash
  ./bestemshe --solve 48 layers/compression_map.txt
  ```
  *(Note: If `compression_map.txt` does not exist yet for your first run, the engine gracefully warns and falls back to legacy lookups.)*

### Step 2: Split the Monolith
Slices the massive monolithic output files (`layerM.bin` and `layerM_draw.bin`) into separate, distinct $K_1, K_2$ micro-layer segments.
* **Command Syntax:** `./bestemshe --split <M> <input_dir> <output_dir>`
* **Execution:**
  ```bash
  ./bestemshe --split 48 layers/ layers/
  ```

### Step 3: Compress the Micro-Layers
Pack the flat raw segments into block-chunked, random-access binary formats [1]. We use **LZ4** for the wins database and **RLE** (Run-Length Encoding) for the draws database [1], leveraging a standard 4096-state page-aligned block size.
* **Command Syntax:** `./bestemshe --compress <input_raw> <output_bin> <algo> <block_size>`
* **Execution:**
  ```bash
  # Compress wins
  ./bestemshe --compress layers/layer_24_24_win.raw layers/layer_24_24_win.bin LZ4 4096
  ./bestemshe --compress layers/layer_24_24_draw.raw layers/layer_24_24_draw.bin LZ4 4096


  # Compress draws
  ./bestemshe --compress layers/layer_24_24_draw.raw layers/layer_24_24_draw.bin RLE 4096
  ```

### Step 4: Register in the Manifest
For the solver to read these compressed files when computing lower layers, you must append them to the master registry manifest located at `layers/compression_map.txt`.

Open `layers/compression_map.txt` in your editor and add:
```text
24 24 win LZ4 4096
24 24 draw RLE 4096
```

### Step 5: Clean Up Legacy Raw Files
To prevent disk bloat on large layers, safely delete the uncompressed intermediate monoliths and raw splits:
```bash
rm layers/layer48_win.bin layers/layer48_draw.bin layers/layer_24_24_win.raw layers/layer_24_24_draw.raw
```

---

## 4. Pipeline Verification & Next Step

### Verifying a State Value (Inference)
You can directly query any state inside your newly compressed, block-chunked database at $O(1)$ speed without running the solver. 

To query index `0` of the compressed `24, 24` micro-layer:
```bash
./bestemshe --inference layers/compression_map.txt 24 24 0
```
* **Output Legend:**
  * `0` = LOSS
  * `1` = WIN
  * `2` = DRAW

### Solving the Next Layer ($M=46$)
Now that Layer 48 is compressed and registered in your manifest, you are ready to solve the next layer. Any capture transition during the evaluation of $M=46$ that lands in $M'=48$ will be resolved in microseconds by streaming the LZ4/RLE compressed blocks:

```bash
./bestemshe --solve 46 layers/compression_map.txt
```