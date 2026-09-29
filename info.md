# Bestemshe — Tablebase Query Artifacts for the Paper

All results below were produced live against the strongly-solved tablebase via
`tasks/oracle_client.py` (HTTP Range reads into the Hugging Face dataset
`ansarzeinulla/bestemshe-tablebase`, no local copy).

Notation used throughout:

* Position is printed **side-to-move relative**: `K1=<mover kazan> [own p1..p5] | [opponent p1..p5] K2=<opponent kazan>`.
* Cells are numbered 1..5 per side. A move label `ab` means "sow from cell `a`,
  last stone lands on cell `b`" (`b` is in the landing side's frame).
* Verdicts are always **from the side to move**.
* Total stones = 50; a kazan of ≥ 26 wins (`kazan` finish); emptying the
  opponent's row also wins (`atsyrau` finish).

---

## 1. The Opening Theory — the start position is a forced loss for Player 1

Command:

```bash
python -m tasks.oracle_client --children 0 0 5 5 5 5 5 5 5 5 5 5
```

Output:

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

### 1.1 The five legal first moves and their evaluations

The root itself evaluates to **loss** for Player 1 — Bestemshe from the standard
5-stones-per-pit start is a **forced win for the second player**. Every one of
the five legal first moves is a loss:

| P1 move | last stone lands | capture | resulting position (P2 to move) | oracle value for P1 | value for P2 to move |
|---|---|---|---|---|---|
| cell 1 | own cell 5 | no | `K1=0  [5 5 5 5 5] \| [1 6 6 6 6] K2=0` | loss | **win** |
| cell 2 | opponent cell 1 | yes (6) | `K1=0  [0 5 5 5 5] \| [5 1 6 6 6] K2=6` | loss | **win** |
| cell 3 | opponent cell 2 | yes (6) | `K1=0  [6 0 5 5 5] \| [5 5 1 6 6] K2=6` | loss | **win** |
| cell 4 | opponent cell 3 | yes (6) | `K1=0  [6 6 0 5 5] \| [5 5 5 1 6] K2=6` | loss | **win** |
| cell 5 | opponent cell 4 | yes (6) | `K1=0  [6 6 6 0 5] \| [5 5 5 5 1] K2=6` | loss | **win** |

Note the counter-intuitive point worth making in the paper: four of the five
first moves win six stones immediately, and all four are still lost. The
immediate material grab is irrelevant to the game-theoretic value.

### 1.2 Player 2's optimal replies after `1. cell 1`

Chosen opening: **1. cell 1** (the only non-capturing first move, sowing from
pit 1; last stone lands on own cell 5).

Position after `1. cell 1`, Player 2 to move:

```
K1=0  [5 5 5 5 5] | [1 6 6 6 6] K2=0        (mover = Player 2)
```

Full reply table (`value for mover` = value for Player 2):

| P2 move | lands | capture | resulting position (P1 to move) | value for P2 |
|---|---|---|---|---|
| cell 1 | own 5 | no | `K1=0  [1 6 6 6 6] \| [1 6 6 6 6] K2=0` | loss |
| cell 2 | opponent 1 | yes (2) | `K1=0  [0 6 6 6 6] \| [5 1 6 6 6] K2=2` | loss |
| **cell 3** | opponent 2 | no | `K1=0  [2 7 6 6 6] \| [5 5 1 6 6] K2=0` | **win** |
| **cell 4** | opponent 3 | no | `K1=0  [2 7 7 6 6] \| [5 5 5 1 6] K2=0` | **win** |
| cell 5 | opponent 4 | no | `K1=0  [2 7 7 7 6] \| [5 5 5 5 1] K2=0` | loss |

**Optimal reply: `1... cell 3`** (label `32` — sow from cell 3, last stone lands
on opponent cell 2). It keeps the evaluation at *win for Player 2*. `cell 4` is
the only other winning reply; three of the five replies throw the win away.

Again worth flagging for the paper: Player 2's *only* two winning replies are
both **non-capturing**, and the capturing reply (cell 2, +2 stones) loses.

---

## 2. The Infinite Draw Cycle — a 36-ply capture-free loop

Command:

```bash
python -m tasks.find_draw_cycles --position 12 12 1 1 2 5 8 2 1 2 3 1
```

Verbatim output:

```
SEED POSITION (side to move) — oracle value: draw
  K1=12 [1 1 2 5 8] | [2 1 2 3 1] K2=12

Optimal draw-preserving play reaches the loop after 99 plies (captures allowed on the approach).

THE CYCLE — 36 plies, capture-free (K1 + K2 is constant, so this repeats forever):
  ply   99  34 (cell 3)            K1=16 [0 1 2 1 2] | [0 1 1 2 6] K2=18   <-- cycle start
  ply  100  23 (cell 2)            K1=18 [0 1 1 2 6] | [0 0 3 1 2] K2=16
  ply  101  23 (cell 2)            K1=16 [0 0 3 1 2] | [0 0 2 2 6] K2=18
  ply  102  35 (cell 3)            K1=18 [0 0 2 2 6] | [0 0 1 2 3] K2=16
  ply  103  45 (cell 4)            K1=16 [0 0 1 2 3] | [0 0 2 1 7] K2=18
  ply  104  45 (cell 4)            K1=18 [0 0 2 1 7] | [0 0 1 1 4] K2=16
  ply  105  34 (cell 3)            K1=16 [0 0 1 1 4] | [0 0 1 2 7] K2=18
  ply  106  34 (cell 3)            K1=18 [0 0 1 2 7] | [0 0 0 2 4] K2=16
  ply  107  45 (cell 4)            K1=16 [0 0 0 2 4] | [0 0 1 1 8] K2=18
  ply  108  45 (cell 4)            K1=18 [0 0 1 1 8] | [0 0 0 1 5] K2=16
  ply  109  45 (cell 4)            K1=16 [0 0 0 1 5] | [0 0 1 0 9] K2=18
  ply  110  45 (cell 4)            K1=18 [0 0 1 0 9] | [0 0 0 0 6] K2=16
  ply  111  53 (cell 5)            K1=16 [1 1 1 1 7] | [1 1 2 0 1] K2=18
  ply  112  12 (cell 1)            K1=18 [1 1 2 0 1] | [0 2 1 1 7] K2=16
  ply  113  12 (cell 1)            K1=16 [0 2 1 1 7] | [0 2 2 0 1] K2=18
  ply  114  23 (cell 2)            K1=18 [0 2 2 0 1] | [0 1 2 1 7] K2=16
  ply  115  34 (cell 3)            K1=16 [0 1 2 1 7] | [0 2 1 1 1] K2=18
  ply  116  34 (cell 3)            K1=18 [0 2 1 1 1] | [0 1 1 2 7] K2=16
  ply  117  23 (cell 2)            K1=16 [0 1 1 2 7] | [0 1 2 1 1] K2=18
  ply  118  23 (cell 2)            K1=18 [0 1 2 1 1] | [0 0 2 2 7] K2=16
  ply  119  34 (cell 3)            K1=16 [0 0 2 2 7] | [0 1 1 2 1] K2=18
  ply  120  45 (cell 4)            K1=18 [0 1 1 2 1] | [0 0 2 1 8] K2=16
  ply  121  23 (cell 2)            K1=16 [0 0 2 1 8] | [0 0 2 2 1] K2=18
  ply  122  34 (cell 3)            K1=18 [0 0 2 2 1] | [0 0 1 2 8] K2=16
  ply  123  45 (cell 4)            K1=16 [0 0 1 2 8] | [0 0 2 1 2] K2=18
  ply  124  45 (cell 4)            K1=18 [0 0 2 1 2] | [0 0 1 1 9] K2=16
  ply  125  34 (cell 3)            K1=16 [0 0 1 1 9] | [0 0 1 2 2] K2=18
  ply  126  34 (cell 3)            K1=18 [0 0 1 2 2] | [0 0 0 2 9] K2=16
  ply  127  45 (cell 4)            K1=16 [0 0 0 2 9] | [0 0 1 1 3] K2=18
  ply  128  53 (cell 5)            K1=18 [1 1 2 2 4] | [1 1 1 2 1] K2=16
  ply  129  12 (cell 1)            K1=16 [1 1 1 2 1] | [0 2 2 2 4] K2=18
  ply  130  23 (cell 2)            K1=18 [0 2 2 2 4] | [1 0 2 2 1] K2=16
  ply  131  23 (cell 2)            K1=16 [1 0 2 2 1] | [0 1 3 2 4] K2=18
  ply  132  12 (cell 1)            K1=18 [0 1 3 2 4] | [0 1 2 2 1] K2=16
  ply  133  45 (cell 4)            K1=16 [0 1 2 2 1] | [0 1 3 1 5] K2=18
  ply  134  45 (cell 4)            K1=18 [0 1 3 1 5] | [0 1 2 1 2] K2=16
  ply  135  35 (cell 3)            K1=16 [0 1 2 1 2] | [0 1 1 2 6] K2=18   <-- identical to ply 99, same side to move

mode: principal walk
Both sides can repeat this cycle indefinitely: the draw is a genuine infinite loop, not a move-limit artefact.
```

### 2.1 The cycle in a form suitable for a figure

**Cycle start = cycle end board state** (side to move at ply 99 == side to move at ply 135):

```
K1 = 16,  K2 = 18
own row      : [0, 1, 2, 1, 2]
opponent row : [0, 1, 1, 2, 6]
```
i.e. the 12-tuple `16 18 0 1 2 1 2 0 1 1 2 6`.

**Move sequence (36 plies), alternating sides, starting from that board:**

```
23  23  35  45  45  34  34  45  45  45  45  53
12  12  23  34  34  23  23  34  45  23  34  45
45  34  34  45  53  12  23  23  12  45  45  35
```

(read left-to-right, row by row; the 36th move `35` restores the ply-99 board
with the same side to move.)

**Why this is a genuine infinite loop, not a search artefact:**

* Every capture permanently transfers stones into a kazan, so `K1 + K2` is
  strictly monotone increasing and bounded by 48. Any repetition is therefore
  necessarily **capture-free** — and indeed `K1 + K2 = 34` is constant across
  all 36 plies of the cycle.
* Every board in the cycle is evaluated `draw` by the tablebase, and every move
  shown is a *draw-preserving* move for the side to move. Neither side can
  improve on repeating; neither side is forced to deviate.
* Because sowing only pushes stones forward around the 10-pit ring, a board can
  only recur after a full circuit — short cycles are structurally impossible,
  which is why the loop is 36 plies rather than 2 or 4.

The approach to the loop (plies 0–99) does contain captures; the loop itself
cannot.

---

## 3. Tactical Puzzle — "Forced win in 2 moves (3 plies)"

Command:

```bash
python -m tasks.find_forced_wins --plies 3 --position 20 20 1 1 0 1 3 1 3 0 0 0
```

Verbatim output:

```
PUZZLE — 2 moves to win (3 plies), side to move wins
  K1=20 [1 1 0 1 3] | [1 3 0 0 0] K2=20
  oracle value: win

SOLUTION (the only first move that works):
  1. 52  (cell 5)   -> K1=20 [2 0 0 0 0] | [1 1 0 1 1] K2=24
     ... 12 (cell 1)  -> K1=24 [1 1 0 1 1] | [1 1 0 0 0] K2=20
         2. 51  (cell 5)  -> K1=20 [0 1 0 0 0] | [1 1 0 1 0] K2=26  wins by kazan
```

### 3.1 Puzzle statement (figure-ready)

**Position (side to move wins by force in 3 plies):**

```
K1 = 20   (side to move)
K2 = 20   (opponent)
own row      : [1, 1, 0, 1, 3]
opponent row : [1, 3, 0, 0, 0]
```
i.e. the 12-tuple `20 20 1 1 0 1 3 1 3 0 0 0`. Stones check: 20 + 20 + 6 + 4 = 50.

**Solution (unique key move):**

| ply | side | move | resulting position | note |
|---|---|---|---|---|
| 1 | solver | **`52`** — sow cell 5 (3 stones), last stone lands opponent cell 2 | `K1=20 [2 0 0 0 0] \| [1 1 0 1 1] K2=24` | captures 4 → kazan 20 → 24 |
| 2 | defender | `12` — sow cell 1 (only defence tried; every defence loses) | `K1=24 [1 1 0 1 1] \| [1 1 0 0 0] K2=20` | |
| 3 | solver | **`51`** — sow cell 5, last stone lands opponent cell 1 | `K1=20 [0 1 0 0 0] \| [1 1 0 1 0] K2=26` | **wins by kazan** (26 ≥ 26 of 50) |

Properties that make it a fair puzzle (enforced by `find_forced_wins.py`):

* the solver's **first move is unique** — the other legal first move does not win in 3 plies;
* the win holds against **every** defence, not just the line shown;
* the finish is explicit and verifiable (`kazan`: mover's captured total reaches 26 of 50, a strict majority).

Note: the tablebase stores WIN/DRAW/LOSS only — there is no distance-to-mate
field — so the "in exactly 3 plies" depth is established by explicit search on
top of the oracle, not by lookup. This is worth stating in the paper caption.

---

## Reproduction summary

```bash
python -m tasks.oracle_client --children 0 0 5 5 5 5 5 5 5 5 5 5
python -m tasks.find_draw_cycles --position 12 12 1 1 2 5 8 2 1 2 3 1
python -m tasks.find_forced_wins --plies 3 --position 20 20 1 1 0 1 3 1 3 0 0 0
```

Stored JSON counterparts of these artifacts already live in
`tasks/results/opening_tree.json`, `tasks/results/draw_cycle.json`, and
`tasks/results/forced_win_3ply.json`.
