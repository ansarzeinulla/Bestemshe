# Strongly Solving Bestemshe: An 8.3 GB Endgame Oracle, Infinite Cycle Analysis, and Neural Generalization Benchmarks

[![Dataset on HF](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Tablebase%20Dataset-blue)](https://huggingface.co/datasets/ansarzeinulla/bestemshe-tablebase)
[![Model on HF](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-ResMLP%20Model-green)](https://huggingface.co/ansarzeinulla/bestemshe-resmlp)
[![Space on HF](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Interactive%20Arena-orange)](https://huggingface.co/spaces/ansarzeinulla/Bestemshe-God-Algorithm)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Authors:** Ansar Zeinulla & Murat Manassov
**Affiliation:** Nazarbayev University, Kazakhstan

Official implementation and open-science artifacts for the strong solution of
**Bestemshe** (a 5-pit, 50-stone traditional Kazakh mancala variant) and the empirical
evaluation of neural value approximations against the resulting endgame oracle.

---

## Key results

1. **Strong game-theoretic solution.** Parallel retrograde analysis proves Bestemshe is a
   **forced win for the second player**. Every one of the first player's five opening moves
   loses against best play. You can verify this yourself in about twenty seconds, with no
   download — see [Query the oracle](#2-query-the-oracle-no-download-required).

2. **An $O(1)$ compressed endgame oracle.** 169 layers of Zstandard-compressed bitsets
   (8.3 GB, 8,962,782,421 bytes) indexed by a colexicographical ranking bijection $I_B$.
   Lookups touch exactly one 4 MiB block, so a query costs ~20 MB of RSS whether the data
   is memory-mapped locally or fetched by HTTP Range from a remote host.

3. **Infinite draw loops, exhibited concretely.** Drawn positions are drawn because optimal
   play can cycle forever. `tasks/find_draw_cycles.py` traces a concrete **36-ply
   capture-free cycle** in which both sides repeat a position indefinitely. Because a
   capture raises $K_1 + K_2$ irreversibly, no cycle can contain one — but the approach to
   the cycle usually does, so the search must pass through a capturing phase first.

4. **The neural approximation paradox.** A 17.2M-parameter ResMLP distilled from the oracle
   plays the **optimal move 99.69% of the time** (226,232 of 226,933 moves) yet finishes
   **below its theoretical result in 27.8% of games** (556 of 2,000). Games run about
   113 model moves — roughly 227 plies — so a per-move error rate of 0.31% compounds into
   a position-level loss far more often than the local accuracy suggests.

---

## Repository architecture

| Directory | Contents |
|---|---|
| `cpp_solver/` | Parallel C++ retrograde solver, colex state indexing, ZSTD block compressor, the mmap query CLI, and the puzzle extractors. |
| `training/` | PyTorch ResMLP, the `uint8` shard generator, the continuous distillation loop, and standalone inference. |
| `evaluation/` | The symmetric-start benchmark harness and the raw 2,000-game match logs. |
| `tasks/` | HTTP Range oracle client, opening-tree analyser, draw-cycle tracer, forced-win puzzle finder, and the PDF puzzle books. |
| `tests/` | State-encoding correctness and Bellman consistency. |
| `scripts/` | `smoke.sh` — the tiered smoke-test suite. |

The tablebase itself (`layers/`) and model checkpoints (`*.pt`) are deliberately **not** in
this repository; they live on Hugging Face and are gitignored here.

---

## Quickstart

### 1. Installation

```bash
git clone https://github.com/ansarzeinulla/Bestemshe.git
cd Bestemshe
pip install -r requirements.txt
```

### 2. Query the oracle (no download required)

Every lookup fetches only the compressed block holding the bit it needs:

```python
from tasks.oracle_client import Oracle, Position

oracle = Oracle()
start = Position(k1=0, k2=0, pits=(5,) * 10)
print(oracle.value(start))   # 'loss' — the first player loses with perfect play
```

Or from the shell:

```bash
python3 -m tasks.oracle_client --children 0 0 5 5 5 5 5 5 5 5 5 5
```

```
K1=0  [5 5 5 5 5] | [5 5 5 5 5] K2=0
loss

cell         lands  capture  value for mover
   1         own 5    False             loss
   2    opponent 1     True             loss
   3    opponent 2     True             loss
   4    opponent 3     True             loss
   5    opponent 4     True             loss
```

Positions are given as 12 integers `K1 K2 p0..p9` from the side-to-move perspective
(`K1`/`p0..p4` belong to the mover). Stones total 50 and kazans are even. Values are exact
Win/Draw/Loss — **the tablebase stores no distance to mate**, so there is no "mate in N"
lookup; depth is established by explicit search (`tasks/find_forced_wins.py`).

### 3. Build the C++ solver

```bash
cmake -S cpp_solver -B build && cmake --build build -j
```

This produces `bestemshe` (solve / verify / compress), `query` (the mmap explorer),
`generateTasks`, and `generateVictory`. Requires libzstd; OpenMP is optional but the
retrograde sweep is single-threaded without it. On macOS, configure with
`-DCMAKE_CXX_COMPILER=g++-16` (Homebrew GCC) to get OpenMP.
`make -C cpp_solver` is the CMake-free fallback for cluster nodes.

### 4. Run neural inference

```python
from training.infer import load_model, evaluate_position

model, step = load_model("ansarzeinulla/bestemshe-resmlp")
result = evaluate_position(model, pits=[5] * 10, kazan_self=0, kazan_opp=0)
print(result["p_loss"], result["p_draw"], result["p_win"], result["best_move"])
```

### 5. Explore the game theory

```bash
python3 -m tasks.opening_tree --depth 2                    # optimal opening tree
python3 -m tasks.find_draw_cycles --search 200 --seed 11   # an infinite draw loop
python3 -m tasks.find_forced_wins --plies 3 --search 300   # a forced-win puzzle
```

---

## Verification

```bash
scripts/smoke.sh              # tiers 0 and 1
scripts/smoke.sh --offline    # tier 0 only
```

| Tier | Needs | Checks |
|---|---|---|
| 0 | nothing | CMake builds all four binaries; Python imports; rank/unrank bijection against the C++ anchor values; the two independent Python ports of the move rules agree on 2,000 positions; evaluation artifacts parse. |
| 1 | network | The start position evaluates to `loss`; the Bellman identity $V(s) = \max_m (2 - V(s'))$ holds on live tablebase data; the opening tree expands. |
| 2 | the 8.3 GB layers locally (`--with-tablebase DIR`) | Full-size consistency sweep, the local reader and the HTTP client agreeing, and puzzle extraction through the C++ binaries. |
| 3 | torch + a model download (`--with-model`) | ResMLP inference returns a normalized WDL distribution and a legal best move. |

---

## Notes on the numbers

Every figure above was measured from the artifacts in this repository, and a few differ from
earlier drafts of this work:

- The tablebase is **8.3 GB**, not 10 GB (`8,962,782,421` bytes across 338 files).
- The distilled model has **17,214,472 parameters** (width 1024, 8 residual blocks), measured
  from the published checkpoint at step 394,852.
- `evaluation/eval_history.json` aggregates **36 distinct checkpoints** (steps 1 to 158,976)
  from 41 raw result files, four of which were duplicates.
- Training ran 394,852 optimizer steps at batch 32,768 — about 12.9 billion example
  presentations over continuously regenerated 500M-position shard sets.
- The per-checkpoint `optimal_move_rate` in `eval_history.json` saturates near **0.968**
  because `training/eval.py` scores a greedy 1-ply engine. The headline **0.9969** comes
  from the 3-ply minimax engine in `evaluation/vs_god.py`. The two are not interchangeable.
- The `incidents` column in `eval_history.json` is **not** a meaningful metric: every game in
  `training/eval.py` starts from the same root with a deterministic engine and a
  deterministic oracle reply, so all games of a given parity are identical and the count
  scales linearly with `--games`. That degeneracy is precisely why `evaluation/vs_god.py`
  samples random symmetric starts instead; treat `vs_god_results.json` as the benchmark of
  record. Both caveats are recorded in the artifact itself.

---

## Citation

```bibtex
@misc{zeinulla2026bestemshe,
  title={Strongly Solving Bestemshe and Benchmarking Neural Value Approximations
         against an 8.3GB Endgame Oracle},
  author={Zeinulla, Ansar and Manassov, Murat},
  year={2026},
  publisher={GitHub},
  howpublished={\url{https://github.com/ansarzeinulla/Bestemshe}}
}
```

## License

Code in this repository is MIT licensed (see [LICENSE](LICENSE)). The published tablebase
dataset is CC-BY-NC-4.0 and the model is CC-BY-4.0 under their own Hugging Face repository
terms.
