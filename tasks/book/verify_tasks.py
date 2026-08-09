#!/usr/bin/env python3
"""
verify_tasks.py — independent checker for a Bestemshe task book.

Re-implements the sowing rule from BestemsheCore.h in Python and replays every
solution stored in the JSON, so a bug in the C++ search cannot hide behind the
data it produced itself. For each task it checks that:

  * the recorded first move is legal and matches its notation;
  * every LEGAL opponent reply is present in the variations (no defence is
    quietly omitted) and no listed reply is illegal;
  * every line ends with the task's goal actually met;
  * the recorded leaf_variations equals the number of complete lines, and
    respects --branching if the book's meta records one;
  * the position filters recorded in meta are satisfied.

Loop tasks are replayed move by move, checking the line is capture-free, stays
legal, and really does revisit a position.

Usage:  python3 verify_tasks.py puzzles/book_v3.json
"""
import json
import sys


def parse_fen(fen):
    """FEN -> (board[10], k_self, k_opp, M), mover-relative."""
    board_part, kazans, _side, m = fen.split(" ")
    ours, theirs = board_part.split("/")
    board = [int(x) for x in ours.split(",")] + [int(x) for x in theirs.split(",")]
    k1, k2 = (int(x) for x in kazans.split(","))
    return board, k1, k2, int(m)


def execute(board, k_self, k_opp, i):
    """Port of ExecuteMoveAndFlip: play pit i, return the flipped state."""
    if board[i] == 0:
        return None
    b = list(board)
    pieces = b[i]
    b[i] = 0
    cur = i
    if pieces == 1:
        cur = (cur + 1) % 10
        b[cur] += 1
    else:
        b[i] = 1
        pieces -= 1
        while pieces > 0:
            cur = (cur + 1) % 10
            b[cur] += 1
            pieces -= 1

    gain = 0
    if 5 <= cur <= 9 and b[cur] % 2 == 0:      # even-parity capture
        gain = b[cur]
        b[cur] = 0
    k_self += gain
    empties = all(b[p] == 0 for p in range(5, 10))

    # Flip to the opponent's perspective.
    flipped = b[5:10] + b[0:5]
    return {"board": flipped, "k_self": k_opp, "k_opp": k_self,
            "landing": cur, "gain": gain, "empties": empties,
            "terminal": empties or k_self >= 26}


def notation(pit, mv):
    to = mv["landing"] + 1 if mv["landing"] <= 4 else mv["landing"] - 4
    s = f"{pit + 1}{to}"
    if mv["gain"] > 0:
        s += "+"
    if mv["terminal"]:
        s += "#"
    return s


def legal_moves(board, k_self, k_opp):
    """{notation: (pit, result)} for every legal move."""
    out = {}
    for i in range(5):
        mv = execute(board, k_self, k_opp, i)
        if mv is not None:
            out[notation(i, mv)] = (i, mv)
    return out


class Bad(Exception):
    pass


def goal_met(spec, mv, gain_so_far):
    kind = spec["type"]
    if kind == "atsyrau":
        return mv["empties"]
    if kind == "capture_total":
        return gain_so_far + mv["gain"] >= spec["k"]
    if kind == "capture_single":
        return mv["gain"] >= spec["k"]
    if kind == "mate":
        return mv["terminal"]
    raise Bad(f"unknown task type {kind}")


def check_node(node, board, k_self, k_opp, spec, gain):
    """Replays one of our moves (plus the opponent replies under it).
    Returns the number of complete lines below it."""
    if isinstance(node, str):
        move_str, variations = node, None
    else:
        move_str, variations = node["move"], node["variations"]

    legal = legal_moves(board, k_self, k_opp)
    if move_str not in legal:
        raise Bad(f"our move {move_str} is not legal; legal = {sorted(legal)}")
    _pit, mv = legal[move_str]

    if variations is None:                       # leaf: the goal must be met
        if not goal_met(spec, mv, gain):
            raise Bad(f"line ends with {move_str} but the goal is not met")
        return 1

    if goal_met(spec, mv, gain):
        raise Bad(f"{move_str} already meets the goal yet has variations")
    if mv["terminal"]:
        raise Bad(f"{move_str} ends the game but has variations")

    # Every legal opponent reply must be answered.
    opp = legal_moves(mv["board"], mv["k_self"], mv["k_opp"])
    listed, actual = set(variations), set(opp)
    if listed != actual:
        raise Bad(f"after {move_str}: replies listed {sorted(listed)} "
                  f"!= legal {sorted(actual)}")

    leaves = 0
    for reply_str, child in variations.items():
        _rp, rmv = opp[reply_str]
        if rmv["terminal"]:
            raise Bad(f"reply {reply_str} ends the game; we never move again")
        leaves += check_node(child, rmv["board"], rmv["k_self"], rmv["k_opp"],
                             spec, gain + mv["gain"])
    return leaves


def check_loop(sol, board, k_self, k_opp, n):
    """Replays a loop line and confirms it really revisits a position."""
    line = sol["line"]
    seen = {(tuple(board), 0 % 2)}
    for ply, move_str in enumerate(line):
        legal = legal_moves(board, k_self, k_opp)
        if move_str not in legal:
            raise Bad(f"ply {ply}: {move_str} not legal; legal={sorted(legal)}")
        _pit, mv = legal[move_str]
        if mv["gain"] != 0:
            raise Bad(f"ply {ply}: {move_str} captures, so no position can recur")
        board, k_self, k_opp = mv["board"], mv["k_self"], mv["k_opp"]
        key = (tuple(board), (ply + 1) % 2)
        if key in seen:
            if ply != sol["loop_at"]:
                raise Bad(f"loop closes at ply {ply}, but loop_at={sol['loop_at']}")
            our_moves = (ply + 2) // 2
            if our_moves > n:
                raise Bad(f"loop needs {our_moves} of our moves > N={n}")
            return
        seen.add(key)
    raise Bad("line ended without repeating a position")


def check_filters(task, filters):
    pairs = [
        ("min_kazan_white", "kazan_white", "min"), ("max_kazan_white", "kazan_white", "max"),
        ("min_kazan_black", "kazan_black", "min"), ("max_kazan_black", "kazan_black", "max"),
        ("min_stones_white", "stones_white", "min"), ("max_stones_white", "stones_white", "max"),
        ("min_stones_black", "stones_black", "min"), ("max_stones_black", "stones_black", "max"),
        ("min_empty_white", "empty_white", "min"), ("max_empty_white", "empty_white", "max"),
        ("min_empty_black", "empty_black", "min"), ("max_empty_black", "empty_black", "max"),
    ]
    for key, field, kind in pairs:
        lim = filters.get(key)
        if lim is None:
            continue
        val = task[field]
        if kind == "min" and val < lim:
            raise Bad(f"{field}={val} violates {key}={lim}")
        if kind == "max" and val > lim:
            raise Bad(f"{field}={val} violates {key}={lim}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "puzzles/book_v3.json"
    with open(path) as f:
        data = json.load(f)
    meta, tasks = (({}, data) if isinstance(data, list)
                   else (data.get("meta", {}), data["tasks"]))
    filters = meta.get("filters", {})
    branching = meta.get("branching")

    failures = 0
    for i, task in enumerate(tasks):
        tid = task.get("id", f"#{i + 1}")
        try:
            board, k1, k2, _m = parse_fen(task["fen"])
            # Recorded counts must match the FEN.
            if task["stones_white"] != sum(board[:5]) or \
               task["stones_black"] != sum(board[5:]):
                raise Bad("stone counts disagree with the FEN")
            if task["empty_white"] != sum(1 for x in board[:5] if x == 0) or \
               task["empty_black"] != sum(1 for x in board[5:] if x == 0):
                raise Bad("empty-cell counts disagree with the FEN")
            if (task["kazan_white"], task["kazan_black"]) != (k1, k2):
                raise Bad("kazans disagree with the FEN")
            check_filters(task, filters)

            spec = task["task"]
            if spec["type"] == "loop":
                for sol in task["solutions"]:
                    check_loop(sol, board, k1, k2, spec["n"])
            else:
                for sol in task["solutions"]:
                    node = ({"move": sol["first_move"], "variations": sol["variations"]}
                            if "variations" in sol else sol["first_move"])
                    leaves = check_node(node, board, k1, k2, spec, 0)
                    if leaves != task["leaf_variations"]:
                        raise Bad(f"leaf_variations={task['leaf_variations']} "
                                  f"but replay counted {leaves}")
                    if branching is not None and leaves > branching:
                        raise Bad(f"{leaves} variations exceeds branching={branching}")
        except Bad as e:
            failures += 1
            print(f"[FAIL] {tid} {task['fen']}: {e}")

    print(f"[{'FAIL' if failures else 'OK'}] {len(tasks) - failures}/{len(tasks)} "
          f"tasks verified from {path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
