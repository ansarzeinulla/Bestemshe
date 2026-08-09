#!/usr/bin/env python3
"""find_draw_cycles.py — trace infinite draw loops under optimal play.

A drawn Bestemshe position is drawn precisely because both sides can decline to
lose forever. This tool exhibits that concretely: it walks moves that preserve
the draw for the side to move until a position repeats with the same side to
move, closing a cycle optimal play can repeat indefinitely.

Two facts shape the search:

* Every capture moves stones permanently into a kazan, so K1 + K2 rises strictly
  and is bounded by 48. A repetition can therefore never straddle a capture —
  any cycle is capture-free — but the road to the cycle usually is not. Optimal
  play typically trades stones for a while before settling into the loop, so the
  walk must allow captures even though the cycle cannot contain them.
* Sowing only ever moves stones forward around the ring, so a board can only
  recur after a full circuit. Short cycles are structurally implausible; the
  loops this finds run to dozens of plies.

Ported from the `loop` task type in cpp_solver/src/generateTasks.cpp
(LoopMoves / LoopDFS / SolveLoop), rewritten against the HTTP Range oracle so it
runs with no local tablebase.

Usage:
    python3 -m tasks.find_draw_cycles --search 200 --k1 12 --k2 12 --seed 11
    python3 -m tasks.find_draw_cycles --position 16 18 0 1 2 1 2 0 1 1 2 6
    python3 -m tasks.find_draw_cycles --position 16 18 0 1 2 1 2 0 1 1 2 6 \\
        --shortest --max-plies 16
"""
from __future__ import annotations

import argparse
import json
import random
import sys

from tasks.oracle_client import (NUM_PITS, TOTAL_STONES, Oracle, Position,
                                 apply_move, format_position, legal_pits,
                                 parse_position)

WALK_LIMIT = 4000           # plies before the principal walk gives up


def position_key(pos: Position, ply: int) -> tuple:
    """Positions are mover-relative, so a repetition key must also record whose
    turn it is: the same board with the other side to move is a different node."""
    return (pos.k1, pos.k2, pos.pits, ply % 2)


def draw_moves(oracle: Oracle, pos: Position, capture_free: bool = False) -> list[dict]:
    """Moves that keep the position a draw for the side to move.

    With capture_free=True only non-capturing moves are returned — the right
    restriction once the search is looking for the cycle itself rather than the
    approach to it.
    """
    out = []
    for pit in legal_pits(pos):
        child = apply_move(pos, pit)
        if child.wins_immediately:
            continue
        if capture_free and child.capture:
            continue
        value = oracle.value(child.position)      # value for the OPPONENT
        if value != "draw":                       # "draw" is its own inverse
            continue
        out.append({"pit": child.pit, "land": child.land,
                    "position": child.position, "capture": child.capture,
                    "value_for_mover": "draw"})
    return out


def move_label(child: dict) -> str:
    """Two-digit notation: <from cell><to cell>, cells 1..5 in the landing frame."""
    return f"{child['pit'] + 1}{(child['land'] % NUM_PITS) + 1}"


# --------------------------------------------------------------------- walk

def principal_walk(oracle: Oracle, start: Position, limit: int = WALK_LIMIT) -> dict | None:
    """Follow the first draw-preserving move at every ply until a position repeats.

    This is the cheap, reliable way to exhibit a loop: the drawing move is unique
    at most plies, so the line is nearly forced, and the walk naturally passes
    through the capturing phase into the capture-free cycle.
    """
    if oracle.value(start) != "draw":
        return None
    pos = start
    seen = {position_key(pos, 0): 0}
    history = [(None, pos)]
    for ply in range(1, limit + 1):
        moves = draw_moves(oracle, pos)
        if not moves:
            return None                     # the draw is not held from here
        c = moves[0]
        pos = c["position"]
        history.append((c, pos))
        key = position_key(pos, ply)
        if key in seen:
            first = seen[key]
            return {"start": start, "history": history,
                    "cycle_start_ply": first, "cycle_end_ply": ply,
                    "cycle_length": ply - first, "mode": "principal walk"}
        seen[key] = ply
    return None


# ----------------------------------------------------------------- shortest

def shortest_cycle(oracle: Oracle, start: Position, max_plies: int) -> dict | None:
    """Iterative deepening for the shortest capture-free cycle back to `start`.

    Only even depths are tried: returning to the same position with the same
    side to move takes an even number of plies.
    """
    if oracle.value(start) != "draw":
        return None
    target = position_key(start, 0)

    def dfs(pos, ply, limit, path, on_path):
        if ply == limit:
            return None
        for c in draw_moves(oracle, pos, capture_free=True):
            child = c["position"]
            key = position_key(child, ply + 1)
            path.append(c)
            if key == target:
                return list(path)
            if key not in on_path:
                on_path.add(key)
                found = dfs(child, ply + 1, limit, path, on_path)
                if found:
                    return found
                on_path.discard(key)
            path.pop()
        return None

    for limit in range(2, max_plies + 1, 2):
        found = dfs(start, 0, limit, [], {target})
        if found:
            history = [(None, start)]
            for c in found:
                history.append((c, c["position"]))
            return {"start": start, "history": history,
                    "cycle_start_ply": 0, "cycle_end_ply": len(found),
                    "cycle_length": len(found),
                    "mode": f"shortest capture-free cycle (searched to {limit} plies)"}
    return None


# ------------------------------------------------------------------ search

def random_position(rng: random.Random, k1: int, k2: int) -> Position:
    """Uniform random composition of the remaining stones over the 10 pits."""
    remaining = TOTAL_STONES - k1 - k2
    cuts = sorted(rng.randrange(remaining + 1) for _ in range(9))
    bounds = [0] + cuts + [remaining]
    return Position(k1=k1, k2=k2, pits=tuple(bounds[i + 1] - bounds[i] for i in range(10)))


def search(oracle: Oracle, tries: int, k1: int, k2: int, seed: int,
           limit: int) -> dict | None:
    rng = random.Random(seed)
    for i in range(tries):
        pos = random_position(rng, k1, k2)
        if not pos.is_valid() or not legal_pits(pos):
            continue
        if oracle.value(pos) != "draw":
            continue
        found = principal_walk(oracle, pos, limit)
        if found:
            found["tries"] = i + 1
            return found
    return None


# ------------------------------------------------------------------ report

def report(found: dict) -> None:
    history = found["history"]
    first, last = found["cycle_start_ply"], found["cycle_end_ply"]
    start = found["start"]

    print(f"SEED POSITION (side to move) — oracle value: draw")
    print(f"  {format_position(start)}")
    print()
    if first > 0:
        print(f"Optimal draw-preserving play reaches the loop after {first} plies "
              f"(captures allowed on the approach).")
        print()
    print(f"THE CYCLE — {found['cycle_length']} plies, capture-free "
          f"(K1 + K2 is constant, so this repeats forever):")
    for i in range(first, last + 1):
        c, pos = history[i]
        if c is None:
            label = "seed"
        else:
            label = f"{move_label(c)} (cell {c['pit'] + 1})"
            if c["capture"]:
                label += " capture"
        marker = ""
        if i == first:
            marker = "   <-- cycle start"
        elif i == last:
            marker = f"   <-- identical to ply {first}, same side to move"
        print(f"  ply {i:>4}  {label:<22} {format_position(pos)}{marker}")
    print()
    print(f"mode: {found['mode']}")
    print("Both sides can repeat this cycle indefinitely: the draw is a genuine "
          "infinite loop, not a move-limit artefact.")


def to_json(found: dict) -> dict:
    def pos_json(p):
        return {"k1": p.k1, "k2": p.k2, "pits": list(p.pits)}
    first, last = found["cycle_start_ply"], found["cycle_end_ply"]
    return {
        "seed": pos_json(found["start"]),
        "cycle_start_ply": first,
        "cycle_end_ply": last,
        "cycle_length": found["cycle_length"],
        "mode": found["mode"],
        "line": [
            {"ply": i,
             "move": None if found["history"][i][0] is None else move_label(found["history"][i][0]),
             "capture": None if found["history"][i][0] is None else found["history"][i][0]["capture"],
             "position": pos_json(found["history"][i][1])}
            for i in range(len(found["history"]))
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tasks.find_draw_cycles",
        description="Trace an infinite draw loop under optimal play.")
    ap.add_argument("--position", nargs=12, metavar="N",
                    help="start from this position (K1 K2 p0..p9); must be a draw")
    ap.add_argument("--search", type=int, default=0, metavar="TRIES",
                    help="sample this many random positions until a loop is found")
    ap.add_argument("--k1", type=int, default=12, help="kazan for --search (default 12)")
    ap.add_argument("--k2", type=int, default=12, help="kazan for --search (default 12)")
    ap.add_argument("--shortest", action="store_true",
                    help="search for the shortest capture-free cycle back to --position "
                         "instead of walking the principal line")
    ap.add_argument("--max-plies", type=int, default=WALK_LIMIT,
                    help=f"ply budget (default {WALK_LIMIT}; with --shortest try ~16)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", metavar="PATH", help="also write the result as JSON")
    a = ap.parse_args(argv)

    oracle = Oracle()

    if a.position:
        try:
            start = parse_position(list(a.position))
        except ValueError as e:
            ap.error(str(e))
        value = oracle.value(start)
        if value != "draw":
            print(f"{format_position(start)}\nnot a draw ({value}) — no loop possible",
                  file=sys.stderr)
            return 1
        found = (shortest_cycle(oracle, start, a.max_plies) if a.shortest
                 else principal_walk(oracle, start, a.max_plies))
        if not found and a.shortest:
            print(f"no capture-free cycle of {a.max_plies} plies or fewer returns to "
                  f"this position", file=sys.stderr)
            return 1
    elif a.search:
        found = search(oracle, a.search, a.k1, a.k2, a.seed, a.max_plies)
    else:
        ap.error("pass --position or --search N")

    if not found:
        print("no loop found within the given budget", file=sys.stderr)
        return 1

    report(found)

    if a.json:
        with open(a.json, "w") as fh:
            json.dump(to_json(found), fh, indent=2)
        print(f"written: {a.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
