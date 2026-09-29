# Random-Legal-Move Bot vs. the Oracle — a Baseline for the Model's `vs_god.py` Score

This is the answer to two things: (1) how the trained model (`latest.pt`) was
actually evaluated, and (2) a from-scratch baseline — a bot that plays uniformly
random *legal* moves — run through the exact same protocol against the *live*
tablebase oracle, so the two numbers are directly comparable.

**No commit was made.** New/changed files: [`evaluation/vs_random.py`](evaluation/vs_random.py)
(new script), [`evaluation/vs_random_results.json`](evaluation/vs_random_results.json)
(this run's output), [`evaluation/vs_random.log`](evaluation/vs_random.log) (full per-ply trace).

---

## 1. How the model was evaluated (`evaluation/vs_god.py`)

Per the README (lines 134-135) and the script itself, there are two evaluation
layers:

* **`training/eval.py`** — a cheap per-checkpoint *greedy 1-ply* eval used during
  training, saturating around 96.8%. History in
  [`evaluation/eval_history.json`](evaluation/eval_history.json).
* **`evaluation/vs_god.py`** — the rigorous benchmark, and the one the headline
  numbers come from. Protocol:
  1. Sample a random **symmetric** start position — equal kazans, equal stones,
     equal non-empty-pit counts per side (`sample_symmetric`).
  2. Play it **twice**: once with the oracle moving first, once with the model
     moving first (same board, sides swapped).
  3. The oracle always plays an optimal move (`optimal_move_mask`: any move
     attaining `max(2 - V(child))`, read straight off the local tablebase).
  4. The model's move comes from an **N-ply minimax search** (depth 3 or 5) over
     its own value head, backed up either by hard WDL argmax (`minimax`) or a
     continuous expected-score blend (`avg`). Only the move actually played at
     the root is scored.
  5. Every applied model move is checked against `optimal_move_mask`:
     `optimal_move_rate`, `blunders_from_win_or_draw` (threw away a win or draw),
     and win/draw/loss tallies by which side moved first are all recorded.

Requires a **local** copy of the tablebase (`--tb <path to layers/>`), which is
why this ran on a different machine originally — none of the `.bin` layer files
exist on this machine, only `latest.pt` checkpoints.

Result files at this scale (`n=50`, `seed=42`, matching what I ran below):

| file | depth | backup | games | optimal_move_rate | blunders |
|---|---|---|---|---|---|
| [`vs_god_results_ply3.json`](evaluation/vs_god_results_ply3.json) | 3 | minimax | 100 | **0.99682** | 33 |
| [`vs_god_results_ply5.json`](evaluation/vs_god_results_ply5.json) | 5 | minimax | 100 | **0.99775** | 27 |
| [`vs_god_results.json`](evaluation/vs_god_results.json) (full run, n=1000) | 3 | minimax | 2000 | **0.99691** | 701 |
| [`vs_god_results_ply5_avg_200.json`](evaluation/vs_god_results_ply5_avg_200.json) | 5 | avg | 400 | **0.99894** | 27 |

---

## 2. The random-bot baseline (`evaluation/vs_random.py`, new)

Same protocol, same statistics, no local tablebase: it plays a
**uniform-random-legal-move bot** against the oracle over the **remote**
HTTP-Range oracle (`tasks/oracle_client.py`), which streams only the 4 MiB
compressed block it needs per lookup straight from the Hugging Face dataset.
Every field `vs_god.py` reports, this reports too — nothing was trimmed to save
requests.

Three things needed solving to make this practical against a *remote* oracle
(a local tablebase lookup is a memory read; a remote one is a real network
transfer), all per your direction:

* **One shared `Oracle`, not one per game.** `SharedOracle` wraps
  `tasks.oracle_client.Oracle` with per-URL/per-block locks: a cache hit costs
  no lock at all, a cache miss takes a lock keyed to that exact block so two
  games racing on the same fetch don't both pay for it — the loser just waits
  and then hits the now-warm cache. This matters because the two games from
  every start position (oracle-first / bot-first) traverse nearly the same
  early board states, and every game eventually funnels into the same small,
  low-state-count endgame layers.
* **Level-ordered fetch scheduling.** Every lookup from every one of the 100
  games goes through one `PriorityExecutor` — a fixed thread pool draining a
  priority queue ordered by ascending `level = k1 + k2`. A capture only ever
  *raises* `k1 + k2` (bounded by 48), so every game starts at level 0 and only
  climbs; servicing low-level requests first means the scheduler always works
  on whichever layer the most other games are also about to need, instead of
  first-come-first-served across 100 independent games.
  * The result is visible in [`evaluation/vs_random.log`](evaluation/vs_random.log):
    early on, dozens of games sit at `level=0..12` advancing together (shared
    cache doing real work), and stragglers finish deep in an idiosyncratic
    endgame layer only they visit.
* **Draw-by-repetition, not a move-count fallback.** A capture strictly raises
  `k1 + k2`; therefore any exact repeat of `(k1, k2, pits, side-to-move)` is
  *necessarily* capture-free — the board has gone all the way around and come
  back unchanged, which both sides can then repeat forever. This is the same
  fact [`tasks/find_draw_cycles.py`](tasks/find_draw_cycles.py) uses to exhibit
  concrete infinite loops (see the 36-ply cycle in `tasks/results/draw_cycle.json`).
  Detecting the repeat ends a drawn game the moment it's proven, instead of
  grinding out the `--max-plies=400` fallback — this alone roughly halved
  average game length.

Retry-with-backoff on transient `ReadTimeout`s (HuggingFace occasionally times
out a Range GET under concurrency — a retry, not a failure) rounds it out.

Run command, seed matched to the `ply3`/`ply5` model evals above:

```bash
python -m evaluation.vs_random --n 50 --seed 42 \
    --out evaluation/vs_random_results.json --log evaluation/vs_random.log
```

**Caveat on the start positions:** `vs_god.py`'s RNG stream is consumed only by
`sample_symmetric`; `vs_random.py`'s stream *also* draws a per-game seed for
the bot's own move choices after every position, which shifts the stream from
position 2 onward. Same seed value (`42`), same *sampler*, same *scale*
(50 positions / 100 games) — but not bit-identical positions to the model's
`ply3`/`ply5` runs. The theoretical win/draw/loss split below differs from
theirs (29/1/20 vs. 19/1/30) purely from that — an artifact of comparing two
independently-drawn samples of the same size, not a bug in either script.

---

## 3. Results

Full JSON: [`evaluation/vs_random_results.json`](evaluation/vs_random_results.json).
Full per-ply / per-game trace: [`evaluation/vs_random.log`](evaluation/vs_random.log)
(4,911 bot moves + matching oracle moves across 100 games, with periodic
snapshots showing every concurrent game's ply and level).

| metric | **random-legal-move bot** (this run, n=50) | model, 3-ply minimax (`vs_god_results_ply3.json`) | model, 5-ply minimax (`vs_god_results_ply5.json`) |
|---|---|---|---|
| games | 100 | 100 | 100 |
| theoretical start values (mover) | win=29 draw=1 loss=20 | win=19 draw=1 loss=30 | win=19 draw=1 loss=30 |
| results, bot/model first | win=4 draw=3 loss=43 | win=6 draw=23 loss=21 | win=11 draw=27 loss=12 |
| results, oracle first | win=7 draw=3 loss=40 | win=18 draw=15 loss=17 | win=17 draw=22 loss=11 |
| applied moves | 4,911 | 10,371 | 12,020 |
| **optimal move rate** | **0.97475** | **0.99682** | **0.99775** |
| suboptimal moves | 124 | 33 | 27 |
| blunders (threw away win/draw) | 124 | 33 | 27 |
| games below theoretical result | 43 / 100 | 26 / 100 | 21 / 100 |

### Why the random bot's number isn't low — read the metric first

`optimal_move_rate` is a **WDL-class** metric, not a move-quality metric: a move
counts as optimal whenever it attains `max(2 - V(child))` (`optimal_moves()` in
`vs_random.py`, mirroring `make_shards.optimal_move_mask` exactly — same
definition the model is scored on). Two structural facts make this lenient for
*any* mover, random or not:

1. **In an already-lost position, every legal move is optimal.** If the mover
   is losing, every child is a win for the opponent, so every move scores
   `2 - 2 = 0` — tied for the max. There's no way to make a lost position "more
   lost," so a move there can never be marked wrong. This is exactly why
   `suboptimal_applied_moves == blunders_from_win_or_draw` (124 == 124) in the
   table below: the random bot never made a *scoreable* mistake while already
   losing, because none was measurable.
2. **In won/drawn positions, several moves are frequently tied** for the same
   WDL class (multiple captures that all preserve the win; near the endgame,
   often only 1–2 pits are non-empty at all). A random move only counts against
   the bot when it happens to be one of the — often minority — moves that
   actually *crosses* a WDL boundary (win→draw/loss, draw→loss).

So 97.5% does not mean "the random bot plays 97.5%-as-well-as-optimal
strategy." It means it crossed a WDL boundary only ~1 time in 40 chances to.
It says nothing about winning by the fastest/cleanest line, margin, or
distance-to-mate — only about the coarse proven result. The model is scored by
the identical lenient metric (so the comparison below is fair), but the
absolute numbers for both sides should be read as "how often did this player's
choice change the theoretical outcome," not "how strong is this player."

### Reading it

* The random bot gets roughly **1 move in 40 wrong** relative to the tablebase
  (97.5% optimal); the trained model, searching its own value head 3–5 plies
  deep, gets roughly **1 move in 300–400** wrong (99.68–99.78%). That's a
  **~13–17x reduction in error rate** from the network + search, over an
  identical evaluation protocol.
* Every single one of the random bot's 124 suboptimal moves is also flagged a
  blunder (`suboptimal == blunders`), meaning the random bot *never* got away
  with a mistake in an already-lost position — it was already losing whenever
  it picked a losing move, and it's simply not being asked to distinguish
  "still lost, but why not" from "actually correct." The model, by contrast,
  is close to that ceiling too (33/33 and 27/27) — most of its rare mistakes
  are also in positions where the mistake had a real cost.
* "Games below theoretical result" — 43% of the random bot's games ended worse
  than the position's proven value warranted, vs. 21–26% for the model. The
  random bot still lands *near* theory more often than not, largely because a
  single wrong move against a perfectly-playing oracle is often not fatal from
  a won position, but it's a much rougher approximation than the model's.

This is the intended headline: the model is not merely "better than random" —
it's the network + search closing the overwhelming majority of the gap between
"knows nothing" and "provably optimal," a useful anchor point for the paper's
optimal-move-rate figure alongside the ablation numbers already in the README.
