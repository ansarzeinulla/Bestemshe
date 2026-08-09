#!/usr/bin/env python3
"""opening_tree.py — extract the optimal opening tree from the endgame oracle.

Expands the game tree from a root position, keeping at each node only the moves
that attain the node's game-theoretic value (i.e. optimal play for the side to
move). Queries go through tasks/oracle_client.py, so no local tablebase is
needed — only HTTP Range requests against the Hugging Face dataset.

The tablebase stores WIN/DRAW/LOSS only; distance-to-mate was never computed,
so this tool reports values, never "mate in N".

Usage:
    python3 -m tasks.opening_tree --depth 2
    python3 -m tasks.opening_tree --depth 3 --all-moves --json opening.json
    python3 -m tasks.opening_tree --position 0 0 5 5 5 5 5 5 5 5 5 5 --depth 2
"""
from __future__ import annotations

import argparse
import json
import sys

from tasks.oracle_client import (NUM_PITS, Oracle, Position, format_position,
                                 parse_position)

# A parent's value is the inverse of its best child's value, so ranking children
# by how good they are FOR THE MOVER uses this order.
RANK = {"win": 2, "draw": 1, "loss": 0, "unknown": -1}


def move_label(child: dict) -> str:
    """Two-digit notation: <from cell><to cell>, cells 1..5 in the landing side's frame."""
    return f"{child['pit'] + 1}{(child['land'] % NUM_PITS) + 1}"


def expand(oracle: Oracle, pos: Position, depth: int, all_moves: bool,
           stats: dict) -> dict:
    """Recursively expand `pos`, keeping optimal moves (or all with --all-moves)."""
    value = oracle.value(pos)
    stats["queries"] += 1
    node = {
        "position": {"k1": pos.k1, "k2": pos.k2, "pits": list(pos.pits)},
        "value_for_side_to_move": value,
        "moves": [],
    }
    if depth <= 0:
        return node

    children = oracle.children_values(pos)
    if not children:
        node["terminal"] = "no legal move — side to move has lost"
        return node

    best = max(RANK[c["value_for_mover"]] for c in children)
    for c in children:
        optimal = RANK[c["value_for_mover"]] == best
        if not optimal and not all_moves:
            continue
        entry = {
            "move": move_label(c),
            "from_cell": c["pit"] + 1,
            "lands_on": "opponent" if c["land"] >= NUM_PITS else "own",
            "land_cell": (c["land"] % NUM_PITS) + 1,
            "capture": c["capture"],
            "terminal": c["terminal"],
            "optimal": optimal,
            "value_for_mover": c["value_for_mover"],
        }
        if not c["terminal"]:
            entry["reply"] = expand(oracle, c["position"], depth - 1,
                                    all_moves, stats)
        node["moves"].append(entry)
    return node


def print_tree(node: dict, indent: int = 0, prefix: str = "") -> None:
    pos = node["position"]
    pad = "  " * indent
    print(f"{pad}{prefix}{format_position(Position(pos['k1'], pos['k2'], tuple(pos['pits'])))}"
          f"  -> {node['value_for_side_to_move']}")
    if "terminal" in node:
        print(f"{pad}  ({node['terminal']})")
    for m in node["moves"]:
        star = "*" if m["optimal"] else " "
        cap = " capture" if m["capture"] else ""
        term = "  [immediate win]" if m["terminal"] else ""
        print(f"{pad}  {star} {m['move']}  cell {m['from_cell']} -> "
              f"{m['lands_on']} {m['land_cell']}{cap}  "
              f"= {m['value_for_mover']} for mover{term}")
        if "reply" in m:
            print_tree(m["reply"], indent + 2, prefix="")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tasks.opening_tree",
        description="Extract the optimal opening tree from the Bestemshe oracle.")
    ap.add_argument("--position", nargs=12, metavar="N",
                    help="root as K1 K2 p0..p9 (default: the start position)")
    ap.add_argument("--depth", type=int, default=2,
                    help="plies to expand below the root (default 2)")
    ap.add_argument("--all-moves", action="store_true",
                    help="keep suboptimal moves too, flagged optimal=false")
    ap.add_argument("--json", metavar="PATH", help="also write the tree as JSON")
    a = ap.parse_args(argv)

    fields = a.position or ["0", "0"] + ["5"] * 10
    try:
        root = parse_position(list(fields))
    except ValueError as e:
        ap.error(str(e))

    stats = {"queries": 0}
    tree = expand(Oracle(), root, a.depth, a.all_moves, stats)
    print_tree(tree)
    print(f"\n({stats['queries']} oracle lookups; '*' marks an optimal move)",
          file=sys.stderr)

    if a.json:
        with open(a.json, "w") as fh:
            json.dump(tree, fh, indent=2)
        print(f"written: {a.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
