#!/usr/bin/env python3
"""find_forced_wins.py — extract "forced win in exactly N moves" tactical puzzles.

A puzzle is a position where the side to move wins by force in exactly N of its
own moves — 2N-1 plies — against every defence, and where exactly one first move
achieves it. Those two conditions are what make a puzzle solvable and fair:
a unique key move, and a horizon the solver can see to the end of.

Winning happens two ways in Bestemshe, and both count as the finish here:
  * atsyrau — the move leaves the opponent's row empty, so they cannot move;
  * kazan   — the move brings the mover's kazan to 26 or more, past half of 50.

This is the mate search from cpp_solver/src/generateTasks.cpp (SolveOurMate /
SolveOppMate / WinningMoves) rewritten against the HTTP Range oracle, so it runs
with no local tablebase. The C++ version is faster and should be preferred when
the 8.3 GB layers are on disk; this one exists so the result is reproducible from
any machine with a network connection.

Note the tablebase stores WIN/DRAW/LOSS only — no distance to mate — so depth is
established by explicit search here, not looked up.

Usage:
    python3 -m tasks.find_forced_wins --plies 3 --search 400 --k1 20 --k2 20
    python3 -m tasks.find_forced_wins --plies 3 --position 20 20 0 1 0 0 4 ...
"""
from __future__ import annotations

import argparse
import json
import random
import sys

from tasks.oracle_client import (NUM_PITS, TOTAL_STONES, Oracle, Position,
                                 apply_move, format_position, legal_pits,
                                 parse_position)


# apply_move returns the child ALREADY FLIPPED, so the mover's own kazan after
# the move is child.position.k2, not .k1.


def move_label(pit: int, land: int) -> str:
    """Two-digit notation <from cell><to cell>, cells 1..5 in the landing frame."""
    return f"{pit + 1}{(land % NUM_PITS) + 1}"


def our_mate(oracle: Oracle, pos: Position, moves_left: int) -> dict | None:
    """Can the side to move force a win in at most `moves_left` of its own moves?

    Returns a proof tree, or None. The first qualifying move is taken: any one
    forced win is a proof, and the caller enforces root uniqueness separately.
    """
    if moves_left <= 0:
        return None
    for pit in legal_pits(pos):
        child = apply_move(pos, pit)
        if child.wins_immediately:
            return {"move": move_label(pit, child.land), "from_cell": pit + 1,
                    "finish": "kazan" if child.position.k2 >= 26 else "atsyrau",
                    "position": child.position, "replies": []}
        if moves_left == 1:
            continue                       # must finish on this move
        if oracle.value(child.position) != "loss":
            continue                       # the defender escapes
        replies = opponent_all_lose(oracle, child.position, moves_left - 1)
        if replies is None:
            continue
        return {"move": move_label(pit, child.land), "from_cell": pit + 1,
                "finish": None, "position": child.position, "replies": replies}
    return None


def opponent_all_lose(oracle: Oracle, pos: Position, moves_left: int) -> list | None:
    """Every legal defence must still leave us a forced win in `moves_left` moves."""
    defences = legal_pits(pos)
    if not defences:
        return []                          # no reply: the game is already over
    out = []
    for pit in defences:
        child = apply_move(pos, pit)
        if child.wins_immediately:
            return None                    # the defender wins instead — not a mate
        follow = our_mate(oracle, child.position, moves_left)
        if follow is None:
            return None
        out.append({"defence": move_label(pit, child.land), "from_cell": pit + 1,
                    "position": child.position, "refutation": follow})
    return out


def analyse(oracle: Oracle, pos: Position, our_moves: int) -> dict | None:
    """A puzzle at exactly `our_moves`: not faster, and with a unique key move."""
    if oracle.value(pos) != "win":
        return None
    if our_mate(oracle, pos, our_moves - 1) is not None:
        return None                        # solvable faster — wrong depth label

    winners = []
    for pit in legal_pits(pos):
        child = apply_move(pos, pit)
        if child.wins_immediately:
            winners.append((pit, {"move": move_label(pit, child.land),
                                  "from_cell": pit + 1,
                                  "finish": "kazan" if child.position.k2 >= 26 else "atsyrau",
                                  "position": child.position, "replies": []}))
            continue
        if oracle.value(child.position) != "loss":
            continue
        replies = opponent_all_lose(oracle, child.position, our_moves - 1)
        if replies is None:
            continue
        winners.append((pit, {"move": move_label(pit, child.land),
                              "from_cell": pit + 1, "finish": None,
                              "position": child.position, "replies": replies}))

    if len(winners) != 1:
        return None                        # not a unique key move
    return {"position": pos, "our_moves": our_moves,
            "plies": 2 * our_moves - 1, "solution": winners[0][1]}


def random_position(rng: random.Random, k1: int, k2: int) -> Position:
    remaining = TOTAL_STONES - k1 - k2
    cuts = sorted(rng.randrange(remaining + 1) for _ in range(9))
    bounds = [0] + cuts + [remaining]
    return Position(k1=k1, k2=k2, pits=tuple(bounds[i + 1] - bounds[i] for i in range(10)))


def search(oracle: Oracle, tries: int, our_moves: int, k1: int, k2: int,
           seed: int) -> dict | None:
    rng = random.Random(seed)
    for i in range(tries):
        pos = random_position(rng, k1, k2)
        if not pos.is_valid() or not legal_pits(pos):
            continue
        if all(p == 0 for p in pos.pits[NUM_PITS:]):
            continue                       # the opponent is already starved
        found = analyse(oracle, pos, our_moves)
        if found:
            found["tries"] = i + 1
            return found
    return None


def report(found: dict) -> None:
    pos = found["position"]
    print(f"PUZZLE — {found['our_moves']} moves to win "
          f"({found['plies']} plies), side to move wins")
    print(f"  {format_position(pos)}")
    print(f"  oracle value: win")
    print()
    print("SOLUTION (the only first move that works):")
    sol = found["solution"]
    print(f"  1. {sol['move']}  (cell {sol['from_cell']})   -> {format_position(sol['position'])}")
    if sol["finish"]:
        print(f"     wins at once by {sol['finish']}")
        return
    if not sol["replies"]:
        print("     the opponent has no legal reply")
        return
    for r in sol["replies"]:
        print(f"     ... {r['defence']} (cell {r['from_cell']})  "
              f"-> {format_position(r['position'])}")
        f = r["refutation"]
        print(f"         2. {f['move']}  (cell {f['from_cell']})  "
              f"-> {format_position(f['position'])}  wins by {f['finish']}")


def to_json(found: dict) -> dict:
    def pos_json(p):
        return {"k1": p.k1, "k2": p.k2, "pits": list(p.pits)}

    def sol_json(s):
        return {"move": s["move"], "from_cell": s["from_cell"],
                "finish": s["finish"], "position": pos_json(s["position"]),
                "replies": [{"defence": r["defence"], "from_cell": r["from_cell"],
                             "position": pos_json(r["position"]),
                             "refutation": sol_json(r["refutation"])}
                            for r in s["replies"]]}

    return {"position": pos_json(found["position"]),
            "our_moves": found["our_moves"], "plies": found["plies"],
            "unique_key_move": True, "solution": sol_json(found["solution"])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tasks.find_forced_wins",
        description="Find a forced-win-in-N tactical puzzle using the HTTP oracle.")
    ap.add_argument("--position", nargs=12, metavar="N",
                    help="analyse this position (K1 K2 p0..p9)")
    ap.add_argument("--search", type=int, default=0, metavar="TRIES",
                    help="sample this many random positions until a puzzle is found")
    ap.add_argument("--plies", type=int, default=3,
                    help="win in this many plies; must be odd (default 3)")
    ap.add_argument("--k1", type=int, default=20, help="kazan for --search (default 20)")
    ap.add_argument("--k2", type=int, default=20, help="kazan for --search (default 20)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", metavar="PATH", help="also write the puzzle as JSON")
    a = ap.parse_args(argv)

    if a.plies % 2 == 0 or a.plies < 1:
        ap.error("--plies must be a positive odd number (the mover plays first and last)")
    our_moves = (a.plies + 1) // 2

    oracle = Oracle()
    if a.position:
        try:
            pos = parse_position(list(a.position))
        except ValueError as e:
            ap.error(str(e))
        found = analyse(oracle, pos, our_moves)
        if not found:
            print(f"{format_position(pos)}\nnot a forced win in exactly {a.plies} "
                  f"plies with a unique key move (value: {oracle.value(pos)})",
                  file=sys.stderr)
            return 1
    elif a.search:
        found = search(oracle, a.search, our_moves, a.k1, a.k2, a.seed)
        if not found:
            print("no puzzle found within the given budget", file=sys.stderr)
            return 1
    else:
        ap.error("pass --position or --search N")

    report(found)
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(to_json(found), fh, indent=2)
        print(f"written: {a.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
