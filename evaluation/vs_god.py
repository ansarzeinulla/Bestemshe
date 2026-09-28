"""vs_god.py — match the model (latest.pt) against the "god" oracle (tablebase).

Random SYMMETRIC positions: equal kazans, an equal number of kumalaks on each
side, and an equal number of non-empty pits per side. Every position is played
twice — first with the oracle to move, then with the order reversed and the
model to move. The oracle always plays optimally from the tablebase.

How the model picks its move (--mover):
  search  (default) an N-ply search over the value head (--depth, default 3):
          the tree is expanded N plies, leaves are scored by the network and
          backed up by minimax (--backup minimax) or an expected-score blend
          (--backup avg). --depth 1 is a greedy one-step value lookup.
  policy  the raw policy head: argmax of the policy logits over legal moves,
          no search at all.
  random  a uniformly random legal move (the baseline).
Only the move actually played at the root enters the statistics. The same
--seed gives the same start positions for every mover, so runs are comparable.

Games longer than --max-plies (default 400) are stopped and scored as draws.
The oracle only knows win/draw/loss (no distance to win), so neither side is
pushed to finish a won game; the record of every game says whether it was
stopped by this cap.

Per-game records (start value for the model, outcome, blunders, first blunder,
moves made in non-lost positions, capped or not) are written to --out, together
with the summary metrics:
  * degradation over DEGRADABLE games only (games the model starts in a won or
    drawn position; a lost start cannot get worse),
  * the blunder rate over model moves made in won or drawn positions,
  * the p^L prediction built from those two quantities.

--tb http uses the published tablebase over HTTP Range (tasks/oracle_client.py)
instead of a local copy: slow, but needs no download (smoke tests).

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


class HttpTablebase:
    """The published tablebase over HTTP Range, with the same value() interface
    as training.bestemshe_core.Tablebase (0 = loss, 1 = draw, 2 = win)."""

    def __init__(self):
        from tasks import oracle_client as oc
        self.oc, self.oracle = oc, oc.Oracle()

    def value(self, pos):
        k1, k2, pits = pos
        if k1 >= 26:
            return 2
        if k2 >= 26 or sum(pits[:5]) == 0:
            return 0
        verdict = self.oracle.value(self.oc.Position(k1, k2, tuple(pits)))
        if verdict == "unknown":
            raise ValueError(f"position not in the tablebase: {pos}")
        return {"loss": 0, "draw": 1, "win": 2}[verdict]

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


def policy_move(model, pos):
    """The raw policy head: argmax of the policy logits over the legal moves."""
    _, logits = predict(model, pos)
    return max(legal_moves(pos), key=lambda m: logits[m])


def play(tb, model, pos, god_first, stats, args, move_rng):
    """One game. Returns (outcome FOR THE MODEL, per-game record)."""
    god_turn = god_first
    rec = {"plies": 0, "capped": False, "model_moves": 0, "model_moves_nonlost": 0,
           "blunders": 0, "first_blunder_model_move": None}
    outcome = None
    for _ in range(args.max_plies):
        if pos[1] >= 26 or sum(pos[2][:5]) == 0:       # the side to move has lost
            outcome = "loss" if not god_turn else "win"
            break
        if pos[0] >= 26:
            outcome = "win" if not god_turn else "loss"
            break
        mask = optimal_move_mask(tb, pos)
        if god_turn:
            m = int(mask).bit_length() - 1
        else:
            if args.mover == "search":
                m = engine_move(model, pos, depth=args.depth, backup=args.backup)
            elif args.mover == "policy":
                m = policy_move(model, pos)
            else:
                m = int(move_rng.choice(legal_moves(pos)))
            v_here = tb.value(pos)
            stats["model_moves"] += 1
            rec["model_moves"] += 1
            if v_here >= 1:
                stats["model_moves_nonlost"] += 1
                rec["model_moves_nonlost"] += 1
            if (mask >> m) & 1:
                stats["optimal_moves"] += 1
            else:
                stats["suboptimal_moves"] += 1
                if v_here >= 1:                        # threw away a win/draw
                    stats["blunders"] += 1
                    rec["blunders"] += 1
                    if rec["first_blunder_model_move"] is None:
                        rec["first_blunder_model_move"] = rec["model_moves"]
        pos = apply_move(pos, m)
        god_turn = not god_turn
        rec["plies"] += 1
    if outcome is None:
        outcome, rec["capped"] = "draw", True
    rec["outcome_for_model"] = outcome
    return outcome, rec


def summarize(games):
    """Metrics over the per-game records (see the module docstring)."""
    score = {"loss": 0, "draw": 1, "win": 2}
    degradable = [g for g in games if g["start_value_for_model"] >= 1]
    degraded = [g for g in degradable if score[g["outcome_for_model"]] < g["start_value_for_model"]]
    with_blunder = [g for g in degradable if g["blunders"] > 0]
    moves_nonlost = sum(g["model_moves_nonlost"] for g in games)
    blunders = sum(g["blunders"] for g in games)
    p = 1 - blunders / moves_nonlost if moves_nonlost else None
    mean_L = (sum(g["model_moves_nonlost"] for g in degradable) / len(degradable)
              if degradable else None)
    return {
        "degradable_games": len(degradable),
        "degraded_games": len(degraded),
        "degradation_rate_degradable": len(degraded) / len(degradable) if degradable else None,
        "degradable_games_with_blunder": len(with_blunder),
        "degraded_games_without_blunder": sum(1 for g in degraded if g["blunders"] == 0),
        "capped_games": sum(1 for g in games if g["capped"]),
        "capped_degraded_games": sum(1 for g in degraded if g["capped"]),
        "model_moves_in_won_or_drawn_positions": moves_nonlost,
        "blunder_rate_nonlost": 1 - p if p is not None else None,
        "p_optimal_nonlost": p,
        "mean_L_nonlost_per_degradable_game": mean_L,
        "predicted_blunder_free_rate_p_pow_L": (
            sum(p ** g["model_moves_nonlost"] for g in degradable) / len(degradable)
            if degradable and p is not None else None),
        "observed_blunder_free_rate_degradable": (
            1 - len(with_blunder) / len(degradable) if degradable else None),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tb", required=True, help="local layers dir, or 'http' for the published copy")
    ap.add_argument("--model", default="latest.pt")
    ap.add_argument("--n", type=int, default=50, help="start positions (2 games each)")
    ap.add_argument("--mover", choices=["search", "policy", "random"], default="search")
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--backup", choices=["minimax", "avg"], default="minimax")
    ap.add_argument("--max-plies", type=int, default=400)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="vs_god_results.json")
    a = ap.parse_args()

    tb = HttpTablebase() if a.tb == "http" else Tablebase(os.path.expanduser(a.tb), max_layers=10)
    model, step = load_model(a.model)
    rng = np.random.default_rng(a.seed)                # start positions only
    move_rng = np.random.default_rng(a.seed + 1)       # random mover's choices
    label = a.mover if a.mover != "search" else f"search depth={a.depth} backup={a.backup}"
    print(f"device={DEV}  step={step}  positions={a.n}  mover={label}"
          f"  (2 games per position, {2 * a.n} games total)")

    stats = {"model_moves": 0, "model_moves_nonlost": 0, "optimal_moves": 0,
             "suboptimal_moves": 0, "blunders": 0}
    res = {k: {"win": 0, "draw": 0, "loss": 0}
           for k in ("model_first", "god_first")}
    theo = {"win": 0, "draw": 0, "loss": 0}          # theoretical result for the first player
    games = []
    underperf = wdl_hit = 0

    def snapshot(n_done):
        opt_rate = stats["optimal_moves"] / max(1, stats["model_moves"])
        out = {
            "step": step, "device": DEV, "mover": a.mover, "depth": a.depth,
            "backup": a.backup, "max_plies": a.max_plies, "seed": a.seed,
            "n_positions": a.n, "n_positions_done": n_done,
            "n_games": 2 * a.n, "n_games_done": 2 * n_done,
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
            **summarize(games),
            "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "games": games,
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
        start = {"k1": pos[0], "k2": pos[1], "pits": list(pos[2])}

        # game 1: the oracle moves first -> the model plays second; its value is 2 - v0
        r, rec = play(tb, model, (pos[0], pos[1], list(pos[2])), True, stats, a, move_rng)
        res["god_first"][r] += 1
        games.append({"start": start, "model_first": False, "start_value_for_model": 2 - v0, **rec})
        if {"win": 2, "draw": 1, "loss": 0}[r] < 2 - v0:
            underperf += 1
        # game 2: the model moves first; its value is v0
        r, rec = play(tb, model, (pos[0], pos[1], list(pos[2])), False, stats, a, move_rng)
        res["model_first"][r] += 1
        games.append({"start": start, "model_first": True, "start_value_for_model": v0, **rec})
        if {"win": 2, "draw": 1, "loss": 0}[r] < v0:
            underperf += 1

        out = snapshot(i + 1)                          # save after each pair of games
        pbar.set_postfix(opt_rate=f"{out['optimal_move_rate']:.4f}",
                         blunders=stats["blunders"], degraded=out["degraded_games"])

    def pct(x):
        return "n/a" if x is None else f"{100 * x:.1f}%"

    print("\n" + "=" * 70)
    print(f"  MATCH AGAINST THE ORACLE  (step={step}, mover={label}, {out['n_games']} games)")
    print("=" * 70)
    print(f"  Theoretical start values (first mover): {theo}")
    print(f"  Model first   : {res['model_first']}")
    print(f"  Oracle first  : {res['god_first']}")
    print(f"  Optimal-move rate (all moves)        : {out['optimal_move_rate']:.5f}")
    print(f"  Blunder rate (won/drawn positions)   : {pct(out['blunder_rate_nonlost'])}")
    print(f"  Degradation (all games, old metric)  : {underperf} / {out['n_games']}")
    print(f"  Degradation (degradable games)       : {out['degraded_games']} / "
          f"{out['degradable_games']} = {pct(out['degradation_rate_degradable'])}")
    print(f"    of which without any blunder       : {out['degraded_games_without_blunder']}")
    print(f"  Games stopped at {a.max_plies} plies            : {out['capped_games']}")
    print(f"  Blunder-free (degradable): observed {pct(out['observed_blunder_free_rate_degradable'])}"
          f" vs p^L {pct(out['predicted_blunder_free_rate_p_pow_L'])}")
    print("=" * 70)
    print(f"results saved: {a.out}")


if __name__ == "__main__":
    main()
