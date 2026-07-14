---
title: Bestemshe God Algorithm
emoji: 🎯
colorFrom: yellow
colorTo: red
sdk: gradio
sdk_version: 6.20.0
python_version: "3.12"
app_file: app.py
pinned: false
license: cc-by-4.0
---

# Bestemshe — Strongly Solved

Bestemshe is a Mancala variant (2×5 pits, 2 kazans, 50 stones). This repo contains
the HPC retrograde solver that strongly solved the game, the resulting ~8.3GB
zstd-compressed endgame tablebase, and a **Tablebase Explorer** web UI.

**Game-theoretic value of the starting position: the first player LOSES with perfect play.**

## Components

| File | Purpose |
|---|---|
| `main.cpp`, `Solver.{h,cpp}`, `Compressor.{h,cpp}`, `Inference.h` | HPC solver / verifier / compressor (`./bestemshe`) |
| `Oracle.h`, `query.cpp` | Explorer CLI: mmap + single-block zstd decode, ~20MB RSS per query (`./query`) |
| `app.py` | Gradio UI (calls `./query` via subprocess) |
| `layers/compressed/` | Tablebase: `layer_<K1>_<K2>_{win,draw}.bin` (not in the GitHub repo; LFS on the HF Space) |

## Build & run locally

```bash
brew install zstd libomp   # macOS prerequisites (Linux: apt install libzstd-dev)
make            # solver: ./bestemshe
make query      # explorer CLI: ./query
./query 0 0 5 5 5 5 5 5 5 5 5 5   # JSON eval of the start position
pip install -r requirements.txt
python app.py   # http://localhost:7860
```

Position format: 12 integers `K1 K2 p0..p9`, side-to-move perspective
(K1/p0–p4 = mover). Stones total 50; kazans are even. Evaluations are exact
Win/Draw/Loss (the tablebase stores no mate distances).

Set `BESTEMSHE_DATA_DIR` to point at the compressed layers (default `layers/compressed`).

## How the 10GB lookup stays OOM-safe

Each `.bin` stores a header `[u32 num_blocks][u32 offsets[]]` followed by
independently zstd-compressed 4MB blocks. `Oracle.h` mmaps the file (zero-copy,
pages faulted on demand), reads the offset table in place, and decompresses only
the one block containing the queried state's bit — peak RSS stays ~20MB
regardless of tablebase size, well inside the free HF Space's 16GB.

See [DEPLOY.md](DEPLOY.md) for pushing to GitHub (code-only) and the Hugging Face Space (with data).
