# Strongly Solving Bestemshe: An 8.3 GiB Endgame Oracle, Infinite Cycle Analysis, and Neural Generalization Benchmarks

[![Dataset on HF](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Tablebase%20Dataset-blue)](https://huggingface.co/datasets/ansarzeinulla/bestemshe-tablebase)
[![Model on HF](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-ResMLP%20Model-green)](https://huggingface.co/ansarzeinulla/bestemshe-resmlp)
[![Space on HF](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Interactive%20Arena-orange)](https://huggingface.co/spaces/ansarzeinulla/Bestemshe-God-Algorithm)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Authors:** Ansar Zeinulla & Murat Manassov  
**Affiliation:** Nazarbayev University, Kazakhstan  

Official implementation and open-science artifacts for the strong solution of **Bestemshe** (a 5-pit, 50-stone traditional Kazakh mancala variant) and the empirical evaluation of neural value approximations against the resulting perfect-information endgame oracle.

---

## 🏆 Key Results

1. **Strong Game-Theoretic Solution.** Parallel retrograde analysis shows that Bestemshe is a **forced win for the second player (Follower)**. Every one of the first player's five opening moves loses against optimal play. You can verify this in seconds without downloading the dataset — see [Query the oracle](#2-query-the-oracle-no-download-required).
2. **An $O(1)$ Compressed Endgame Oracle.** 169 layers of Zstandard-compressed bitsets (8,962,782,421 bytes = 8.3 GiB) over all 125,698,242,527 ≈ 1.26×10¹¹ positions of the 169 kazan layers, indexed by a colexicographical ranking bijection $I_B$. Lookups touch exactly one 4 MiB block, meaning a query costs ~20 MB of RAM whether the data is memory-mapped locally or fetched via HTTP Range requests from a remote host.
3. **Infinite Draw Loops (Concrete Existence).** Drawn positions are drawn because optimal play can cycle forever. The script `tasks/find_draw_cycles.py` traces a concrete **36-ply capture-free cycle** in which both sides optimally repeat a position indefinitely. Because a capture irreversibly raises $K_1 + K_2$, no cycle can contain one—but reaching the cycle usually requires passing through a capturing phase first.
4. **Neural approximation vs. the oracle.** A 17.2M-parameter ResMLP distilled from the Oracle, choosing each move by a **3-ply minimax over its value head**, plays a value-preserving move **99.69% of the time** (226,232 of 226,933 moves; 701 value-losing moves) in 2,000 games from 1,000 symmetric starts, yet ends below its theoretical result in **556 games — 53.7% of the 1,036 games it starts in a won or drawn position** (27.8% of all 2,000). Games average 113 model moves. Games are stopped at 400 plies and scored as draws, and neither side is pushed to convert a win (the oracle stores win/draw/loss only), so part of this is non-conversion rather than blunders; `evaluation/vs_god.py` now records blunders, caps and outcomes per game. Deeper search helps: 5-ply minimax degraded 21 of 51 degradable games, and a 5-ply averaged backup 20 of 206.

---

## 📂 Repository Architecture

| Directory | Contents |
|---|---|
| `cpp_solver/` | Parallel C++ retrograde solver, colex state indexing, ZSTD block compressor, the mmap query CLI, and puzzle extractors. |
| `training/` | PyTorch ResMLP architecture, `uint8` shard generator, continuous distillation loop, and standalone inference scripts. |
| `evaluation/` | The adversarial symmetric-start benchmark harness and the raw 2,000-game match logs. |
| `tasks/` | HTTP Range oracle client, opening-tree analyzer, draw-cycle tracer, forced-win puzzle finder, and generated puzzle books. |
| `tests/` | State-encoding correctness and game-theoretic Bellman consistency verification. |
| `scripts/` | `smoke.sh` — the tiered automated smoke-test suite. |

*Note: The 8.3 GiB tablebase (`layers/`) and the PyTorch model checkpoints (`*.pt`) are hosted on Hugging Face and are gitignored here.*

---

## 🚀 Quickstart

### 1. Installation

```bash
git clone https://github.com/ansarzeinulla/Bestemshe.git
cd Bestemshe
pip install -r requirements.txt
```

### 2. Query the Oracle (No Download Required)

Every lookup dynamically fetches only the compressed block holding the specific bit it needs over the network:

```python
from tasks.oracle_client import Oracle, Position

oracle = Oracle()
start = Position(k1=0, k2=0, pits=(5,) * 10)
print(oracle.value(start))   # Outputs: 'loss' (The first player loses under perfect play)
```

Or via the command line:

```bash
python3 -m tasks.oracle_client --children 0 0 5 5 5 5 5 5 5 5 5 5
```


```text
K1=0  [5 5 5 5 5] | [5 5 5 5 5] K2=0
loss

cell         lands  capture  value for mover
   1         own 5    False             loss
   2    opponent 1     True             loss
   3    opponent 2     True             loss
   4    opponent 3     True             loss
   5    opponent 4     True             loss
```

*(Positions are structured as 12 integers `K1 K2 p0..p9` from the side-to-move perspective. Stones total 50. Values are exact Win/Draw/Loss).*

### 3. Build the C++ Solver (HPC)

```bash
cmake -S cpp_solver -B build && cmake --build build -j
```

This compiles `bestemshe` (solve/verify/compress), `query` (mmap explorer), `generateTasks`, and `generateVictory`. 
*Requires `libzstd`. OpenMP is highly recommended for multi-threaded retrograde sweeps. On macOS, configure with `-DCMAKE_CXX_COMPILER=g++-16` (Homebrew GCC) to enable OpenMP.*

### 4. Run Neural Network Inference

```python
from training.infer import load_model, evaluate_position

model, step = load_model("ansarzeinulla/bestemshe-resmlp")
result = evaluate_position(model, pits=[5] * 10, kazan_self=0, kazan_opp=0)
print(f"Loss: {result['p_loss']}, Draw: {result['p_draw']}, Win: {result['p_win']}")
```

### 5. Explore Game Theory & Procedural Generation

```bash
python3 -m tasks.opening_tree --depth 2                    # Computes the optimal opening tree
python3 -m tasks.find_draw_cycles --search 200 --seed 11   # Traces an infinite draw loop
python3 -m tasks.find_forced_wins --plies 3 --search 300   # Generates a forced-win tactical puzzle
```

---

## 🧪 Verification & Testing

```bash
scripts/smoke.sh              # Run tiers 0 and 1
scripts/smoke.sh --offline    # Run tier 0 only
```

| Tier | Requirement | Checks |
|---|---|---|
| **0** | *None* | CMake builds all binaries; Python imports succeed; Python rank/unrank bijection matches C++ anchor values; independent Python rules engines agree on 2,000 positions. |
| **1** | *Network* | Validates initial position evaluates to `loss`; Bellman identity $V(s) = \max_m (2 - V(s'))$ holds via live HTTP queries; opening tree expands. |
| **2** | *Local 8.3 GiB DB* | Full-size consistency sweep; local mmap reader and HTTP client agree; puzzle extraction via C++ binaries succeeds. |
| **3** | *PyTorch + Model* | ResMLP inference runs successfully and returns normalized WDL probability distributions. |

---

## 📊 Reproducing the Paper's Numbers

| Result | Command | Output |
|---|---|---|
| Bellman consistency of the published tablebase | `python3 -m pytest -m online tests/` | 4 passed (checked 2026-09-21) |
| Benchmark vs. the oracle (per-game records) | `python3 -m evaluation.vs_god --tb <layers dir> --n 1000 --mover search --depth 3` | `vs_god_results.json` |
| Same starts, other movers | `--mover policy`, `--mover random`, `--mover search --depth 1`, `--depth 5 [--backup avg]` | one JSON each |
| Calibration, t-SNE, latent heterogeneity | `python3 analysis/latent_calibration.py --n 4000` | `analysis/latent_calibration.json` (ECE 0.0098, draw recall 0) |
| Random-move baseline (earlier script) | `python3 -m evaluation.vs_random --n 50` | `evaluation/vs_random_results.json` (97.48%) |
| Opening tree, draw cycle, 3-ply puzzle | `python3 -m tasks.opening_tree`, `tasks.find_draw_cycles`, `tasks.find_forced_wins` | `tasks/results/*.json` |

The benchmark needs a local copy of the tablebase:

```bash
hf download ansarzeinulla/bestemshe-tablebase --repo-type dataset --local-dir tablebase
python3 -m evaluation.vs_god --tb tablebase/layers/compressed --n 1000 --out vs_god_depth3.json
```

It keeps up to 10 decompressed layers in RAM (the largest is 1.6 GB). `--tb http` reads the published copy over HTTP instead: no download, but slow; fine for smoke tests.

---

## 🔬 Methodological & Empirical Notes

All metrics reported are strictly derived from the final generated artifacts in this repository:

- The final tablebase size is **8,962,782,421 bytes (8.3 GiB)** across 338 files.
- The distilled model contains **17,214,472 parameters** (Width 1024, 8 Residual Blocks), measured from the published checkpoint at step 394,852.
- The neural network training ran for 394,852 optimizer steps at a batch size of 32,768, representing roughly **12.9 billion example presentations** continuously regenerated from the Oracle.
- **On Optimal Move Rates:** The per-checkpoint `optimal_move_rate` saturates near **96.8%** under a greedy 1-ply evaluation (`training/eval.py`). The headline **99.69%** rate is achieved using a 3-ply minimax search (`evaluation/vs_god.py`). This demonstrates that while shallow algorithmic search corrects local blunders, it fundamentally cannot rescue deep-tree OOD value degradation over full games.
- **On Incident Counts:** The `incidents` column in early evaluation logs is degenerate because greedy evaluation from a fixed root is fully deterministic. For rigorous generalization metrics, we rely exclusively on `vs_god.py`, which samples random symmetric starts to explicitly measure out-of-distribution compounding errors.

---

## 📜 Citation

```bibtex
@misc{zeinulla2026bestemshe,
  title={Strongly Solving Bestemshe and Benchmarking Neural Value Approximations against an 8.3GB Endgame Oracle},
  author={Zeinulla, Ansar and Manassov, Murat},
  year={2026},
  publisher={GitHub},
  howpublished={\url{https://github.com/ansarzeinulla/Bestemshe}}
}
```

## ⚖️ License

The code in this repository is licensed under the **MIT License**. The published tablebase dataset is licensed under **CC-BY-NC-4.0**, and the model weights under **CC-BY-4.0** according to their respective Hugging Face repository terms.
