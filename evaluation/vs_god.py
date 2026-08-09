"""vs_god.py — match the model (latest.pt) against the "god" oracle (tablebase).

Random SYMMETRIC positions: equal kazans, an equal number of kumalaks on each
side, and an equal number of non-empty pits per side. Every position is played
twice — first with the oracle to move, then with the order reversed and the
model to move. The oracle always plays optimally from the tablebase.

The model's move is chosen by a 3-ply minimax: the full move tree is expanded
3 plies ahead (our move -> opponent reply -> our move), the leaves are scored by
the network (value head), and values are backed up by minimax (the side to move
flips every ply, so a parent takes 2 - max(children)). Internal search nodes are
NOT counted in the optimality statistics — only the move actually played at the
root is.

Results are rewritten to --out after EVERY pair of games (oracle-first and
model-first from the same position), so progress survives an interruption.

  python3 -m evaluation.vs_god --tb ~/Desktop/Bestemshe/layers/compressed \
      --model latest.pt --n 50
"""
import argparse, json, os, sys, time
import numpy as np
import torch
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from training.bestemshe_core import (Tablebase, legal_moves, apply_move,
                                     is_terminal_loss)
from training.make_shards import optimal_move_mask
from training.train import BestemsheNet

DEV = ("mps" if torch.backends.mps.is_available()
       else "cuda" if torch.cuda.is_available() else "cpu")


def load_model(path):
    ck = torch.load(path, map_location="cpu")
    a = ck["args"]
    m = BestemsheNet(a["width"], a["blocks"]).to(DEV).eval()
    sd = {k.replace("_orig_mod.", ""): v for k, v in ck["model"].items()}
    m.load_state_dict(sd)
    return m, ck.get("step", 0)


@torch.no_grad()
def predict(model, pos):
    k1, k2, pits = pos
    v, pol = model(torch.tensor([pits], device=DEV),
                   torch.tensor([[k1 // 2, k2 // 2]], device=DEV))
    return int(v.argmax()), pol[0].float().cpu().numpy()


def _build_ply_tree(pos, depth):
    """A search-tree node. `depth` is how many more plies to expand from here.
    terminal: the side to move has already lost (no network call, value=0).
    leaf: depth exhausted, the value comes from the network (filled in as a batch).
    Otherwise: expanded over every legal move (children); `pos` is stored on
    internal nodes too, because the avg backup needs each node's own score."""
    if is_terminal_loss(pos):
        return {"terminal": True}
    if depth == 0:
        return {"terminal": False, "leaf": True, "pos": pos, "value": None}
    children = [(m, _build_ply_tree(apply_move(pos, m), depth - 1))
                for m in legal_moves(pos)]
    return {"terminal": False, "leaf": False, "pos": pos, "value": None,
            "children": children}


def _collect_nodes(node, out, internal_too):
    if node["terminal"]:
        return
    if node["leaf"] or internal_too:
        out.append(node)
    if not node["leaf"]:
        for _, c in node["children"]:
            _collect_nodes(c, out, internal_too)


def _backup_minimax(node):
    """Minimax: the side to move flips every ply, so a parent gets
    2 - max(children's values)."""
    if node["terminal"]:
        return 0.0
    if node["leaf"]:
        return node["value"]
    return max(2 - _backup_minimax(c) for _, c in node["children"])


def _backup_avg(node):
    """Mixed backup: a node's value is the mean of its OWN network score and the
    mean over its children (2 - child value). A terminal node is 0."""
    if node["terminal"]:
        return 0.0
    if node["leaf"]:
        return node["value"]
    child_mean = sum(2 - _backup_avg(c)
                     for _, c in node["children"]) / len(node["children"])
    return (node["value"] + child_mean) / 2


@torch.no_grad()
def engine_move(model, pos, depth=3, backup="minimax"):
    """The model's move via a full search `depth` plies ahead.
    backup='minimax': leaves take the argmax WDL class, parents take 2 - max(children).
    backup='avg':     every node gets the continuous expected score
                      E = 2*P(win) + P(draw) from the softmax value head;
                      a node's value is mean(own score, mean(2 - children)).
    Only the chosen root move enters the optimality statistics."""
    root_children = [(m, _build_ply_tree(apply_move(pos, m), depth - 1))
                      for m in legal_moves(pos)]

    nodes = []
    for _, c in root_children:
        _collect_nodes(c, nodes, internal_too=(backup == "avg"))
    if nodes:
        pits = torch.tensor([n["pos"][2] for n in nodes], device=DEV)
        kaz = torch.tensor([[n["pos"][0] // 2, n["pos"][1] // 2]
                            for n in nodes], device=DEV)
        v, _ = model(pits, kaz)
        if backup == "avg":
            probs = torch.softmax(v.float(), dim=1).cpu().numpy()
            vals = 2 * probs[:, 2] + probs[:, 1]      # E over WDL
        else:
            vals = v.argmax(1).cpu().numpy().astype(float)
        for n, val in zip(nodes, vals):
            n["value"] = float(val)

    back = _backup_avg if backup == "avg" else _backup_minimax
    best_m, best_v = None, -1.0
    for m, c in root_children:
        val = 2 - back(c)
        if val > best_v:
            best_m, best_v = m, val
    return best_m


def _random_side(rng, stones, nonzero):
    """A random layout of `stones` stones over 5 pits with exactly `nonzero` non-empty."""
    cells = rng.choice(5, size=nonzero, replace=False)
    # composition of `stones` into `nonzero` parts >= 1 (stars and bars, uniform)
    cuts = np.sort(rng.choice(stones - 1, size=nonzero - 1, replace=False)) + 1 \
        if nonzero > 1 else np.array([], dtype=int)
    parts = np.diff(np.concatenate([[0], cuts, [stones]]))
    side = [0] * 5
    for c, p in zip(cells, parts):
        side[int(c)] = int(p)
    return side


def sample_symmetric(rng):
    """Equal kazans, equal stone totals, and an equal number of non-empty pits per side."""
    while True:
        k = int(rng.choice(np.arange(0, 13))) * 2      # each side's kazan: 0..24
        s = (50 - 2 * k) // 2                          # stones held by each side
        if s < 1:
            continue
        c = int(rng.integers(1, min(5, s) + 1))        # non-empty pits per side
        return (k, k, _random_side(rng, s, c) + _random_side(rng, s, c))


def play(tb, model, pos, god_first, stats, depth, backup):
    """One game. Returns the outcome FOR THE MODEL: 'win'/'draw'/'loss'."""
    god_turn = god_first
    for _ in range(400):
        if pos[1] >= 26 or sum(pos[2][:5]) == 0:       # the side to move has lost
            return "loss" if not god_turn else "win"
        if pos[0] >= 26:
            return "win" if not god_turn else "loss"
        mask = optimal_move_mask(tb, pos)
        if god_turn:
            m = int(mask).bit_length() - 1
        else:
            m = engine_move(model, pos, depth=depth, backup=backup)  # the move actually played
            stats["model_moves"] += 1
            if (mask >> m) & 1:
                stats["optimal_moves"] += 1
            else:
                stats["suboptimal_moves"] += 1
                if tb.value(pos) >= 1:                 # threw away a win/draw
                    stats["blunders"] += 1
        pos = apply_move(pos, m)
        god_turn = not god_turn
    return "draw"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tb", required=True)
    ap.add_argument("--model", default="latest.pt")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--backup", choices=["minimax", "avg"], default="minimax")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="vs_god_results.json")
    a = ap.parse_args()

    tb = Tablebase(os.path.expanduser(a.tb), max_layers=10)
    model, step = load_model(a.model)
    rng = np.random.default_rng(a.seed)
    print(f"device={DEV}  step={step}  positions={a.n}  depth={a.depth}"
          f"  (2 games per position, {2 * a.n} games total)")

    stats = {"model_moves": 0, "optimal_moves": 0, "suboptimal_moves": 0,
             "blunders": 0}
    res = {k: {"win": 0, "draw": 0, "loss": 0}
           for k in ("model_first", "god_first")}
    theo = {"win": 0, "draw": 0, "loss": 0}          # theoretical result for the first player
    underperf = wdl_hit = 0

    def snapshot(n_done):
        n_games_done = 2 * n_done
        opt_rate = stats["optimal_moves"] / max(1, stats["model_moves"])
        out = {
            "step": step, "device": DEV, "depth": a.depth, "backup": a.backup,
            "n_positions": a.n, "n_positions_done": n_done,
            "n_games": 2 * a.n, "n_games_done": n_games_done,
            "start_wdl_accuracy": wdl_hit / max(1, n_done),
            "theoretical_start_values_for_side_to_move": dict(theo),
            "results_model_first": dict(res["model_first"]),
            "results_god_first": dict(res["god_first"]),
            "total_applied_model_moves": stats["model_moves"],
            "optimal_applied_moves": stats["optimal_moves"],
            "suboptimal_applied_moves": stats["suboptimal_moves"],
            "optimal_move_rate": opt_rate,
            "blunders_from_win_or_draw": stats["blunders"],
            "games_below_theoretical_result": underperf,
            "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(a.out, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        return out

    pbar = tqdm(range(a.n), desc="positions", unit="pos")
    for i in pbar:
        pos = sample_symmetric(rng)
        v0 = tb.value(pos)                            # ground truth for the side to move
        theo[["loss", "draw", "win"][v0]] += 1
        wdl_hit += (predict(model, pos)[0] == v0)

        # game 1: the oracle moves first -> the model plays as the second player
        r = play(tb, model, (pos[0], pos[1], list(pos[2])), True, stats, a.depth, a.backup)
        res["god_first"][r] += 1
        # the theoretical result for the model-as-second is the inversion of v0
        if {"win": 2, "draw": 1, "loss": 0}[r] < 2 - v0:
            underperf += 1
        # game 2: the model moves first
        r = play(tb, model, (pos[0], pos[1], list(pos[2])), False, stats, a.depth, a.backup)
        res["model_first"][r] += 1
        if {"win": 2, "draw": 1, "loss": 0}[r] < v0:
            underperf += 1

        out = snapshot(i + 1)                          # save after each pair of games
        pbar.set_postfix(opt_rate=f"{out['optimal_move_rate']:.4f}",
                          blunders=stats["blunders"],
                          worse_than_theory=underperf)

    print("\n" + "=" * 66)
    print(f"  MATCH AGAINST THE GOD ORACLE  (step={step}, depth={a.depth}, "
          f"{out['n_games']} games)")
    print("=" * 66)
    print(f"  Theoretical start values (mover): win={theo['win']} "
          f"draw={theo['draw']} loss={theo['loss']}")
    print(f"  WDL accuracy on starts   : {out['start_wdl_accuracy']:.4f}")
    print(f"  Model first   : {res['model_first']}")
    print(f"  Oracle first  : {res['god_first']}")
    print(f"  Model moves played       : {stats['model_moves']:,}")
    print(f"  Optimal                  : {stats['optimal_moves']:,} "
          f"({out['optimal_move_rate']:.5f})")
    print(f"  Suboptimal               : {stats['suboptimal_moves']:,}")
    print(f"  Blunders from win/draw   : {stats['blunders']}")
    print(f"  Games below theory       : {underperf} / {out['n_games']}")
    print("=" * 66)
    print(f"results saved: {a.out}")


if __name__ == "__main__":
    main()
