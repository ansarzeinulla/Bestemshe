#!/usr/bin/env python3
"""
generate_puzzles_stratified.py — stratified collection of 250 win-in-1 Bestemshe tasks.

Distribution:
  from-cell 1..5           : 50 each
  win type per cell        : atsyrau 10, kazan26 20, capture_atsyrau 20
  color per (cell, type)   : half White, half Black (rotate display)
  layer sourcing           : all layers/compressed pairs, shuffled; even share,
                             deficits roll over to the next layer

Output: puzzles/book250.json (fresh puzzles/ dir), positions in random order.

Usage: python3 -m tasks.generate_puzzles_stratified [--seed 12345] [--per-layer 4]
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

# Per-cell quotas. Cell-5 atsyrau is impossible (every move from cell 5 sows
# into the enemy row, so a non-capturing move can't leave it empty); its share
# is spread over cells 1-4. Row sums stay 50; column sums 50/100/100.
# The C++ extractors are built by cpp_solver (cmake -S cpp_solver -B build).
# Override with BESTEMSHE_BIN_DIR when they live somewhere else.
BIN_DIR = os.environ.get("BESTEMSHE_BIN_DIR", "build")


def _bin(name):
    """Absolute path to a built extractor; fails loudly if it is missing."""
    path = os.path.join(BIN_DIR, name)
    if not os.path.exists(path):
        raise SystemExit(
            f"{path} not found. Build it first:\n"
            f"    cmake -S cpp_solver -B build && cmake --build build -j\n"
            f"or set BESTEMSHE_BIN_DIR to the directory holding {name}.")
    return os.path.abspath(path)


# Directory holding layer_<K1>_<K2>_{win,draw}.bin (the 8.3 GB tablebase).
LAYER_DIR = os.environ.get("BESTEMSHE_DATA_DIR", "layers/compressed")


QUOTAS = {
    1: {"atsyrau": 13, "kazan26": 18, "capture_atsyrau": 19},
    2: {"atsyrau": 13, "kazan26": 19, "capture_atsyrau": 18},
    3: {"atsyrau": 12, "kazan26": 19, "capture_atsyrau": 19},
    4: {"atsyrau": 12, "kazan26": 19, "capture_atsyrau": 19},
    5: {"atsyrau": 0,  "kazan26": 25, "capture_atsyrau": 25},
}
CELLS = [1, 2, 3, 4, 5]


def list_layers():
    pairs = set()
    for f in os.listdir(LAYER_DIR):
        if f.startswith("layer_") and f.endswith("_win.bin"):
            k1, k2 = f[len("layer_"):-len("_win.bin")].split("_")
            pairs.add((int(k1), int(k2)))
    return sorted(pairs)


def run_extract(layer, cell, wtype, count, seed, max_attempts):
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tmp = tf.name
    try:
        subprocess.run(
            [_bin("generateVictory"), "--layer", f"{layer[0]}_{layer[1]}",
             "--moves", "1", "--variationsMin", "1", "--variationsMax", "9",
             "--count", str(count), "--seed", str(seed),
             "--fromPit", str(cell), "--winType", wtype,
             "--maxAttempts", str(max_attempts), "--jsonOut", tmp],
            capture_output=True, check=False)
        with open(tmp) as f:
            return json.load(f)
    finally:
        os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--per-layer", type=int, default=4,
                    help="max positions taken from one layer per bucket pass")
    ap.add_argument("--max-attempts", type=int, default=400000)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    layers = list_layers()
    print(f"[INFO] {len(layers)} layers found")

    seen_fens = set()
    buckets = {}  # (cell, wtype) -> list of puzzles

    for cell in CELLS:
        for wtype, quota in QUOTAS[cell].items():
            if quota == 0:
                continue
            key = (cell, wtype)
            buckets[key] = []
            order = layers[:]
            rng.shuffle(order)
            # Pass 1: small share per layer; pass 2: take whatever remains
            for round_no, take_cap in enumerate([args.per_layer, quota]):
                for layer in order:
                    need = quota - len(buckets[key])
                    if need <= 0:
                        break
                    got = run_extract(layer, cell, wtype, min(need, take_cap),
                                      rng.randrange(1 << 30), args.max_attempts)
                    for p in got:
                        if p["fen"] in seen_fens:
                            continue
                        seen_fens.add(p["fen"])
                        buckets[key].append(p)
                        if len(buckets[key]) >= quota:
                            break
                if len(buckets[key]) >= quota:
                    break
            n = len(buckets[key])
            status = "OK" if n >= quota else "SHORT"
            print(f"[{status}] cell {cell} / {wtype}: {n}/{quota}")
            if n < quota:
                print(f"[FATAL] Could not fill bucket cell={cell} type={wtype}",
                      file=sys.stderr)
                sys.exit(1)

    # Assign colors: half of each bucket black; odd buckets give their extra
    # task to whichever color is behind, keeping the global 125/125 split.
    tasks = []
    black_total = white_total = 0
    for (cell, wtype), plist in buckets.items():
        rng.shuffle(plist)
        n_black = len(plist) // 2
        if len(plist) % 2 == 1 and black_total <= white_total:
            n_black += 1
        black_total += n_black
        white_total += len(plist) - n_black
        for i, p in enumerate(plist):
            tasks.append({
                "color": "b" if i < n_black else "w",
                "fen": p["fen"],
                "layer": p["layer"],
                "from_cell": p["from_cell"],
                "to_cell": p["to_cell"],
                "win_type": p["win_type"],
                "notation": p["notation"],
            })

    rng.shuffle(tasks)

    # Self-check the distribution
    from collections import Counter
    assert len(tasks) == 250, len(tasks)
    assert len({t["fen"] for t in tasks}) == 250
    cc = Counter(t["from_cell"] for t in tasks)
    tc = Counter(t["win_type"] for t in tasks)
    col = Counter(t["color"] for t in tasks)
    lc = Counter(t["layer"] for t in tasks)
    assert all(cc[c] == 50 for c in CELLS), cc
    assert tc == Counter({"kazan26": 100, "capture_atsyrau": 100, "atsyrau": 50}), tc
    assert col == Counter({"w": 125, "b": 125}), col
    print(f"[CHECK] cells={dict(cc)} types={dict(tc)} colors={dict(col)}")
    print(f"[CHECK] distinct source layers: {len(lc)}")

    if os.path.isdir("puzzles"):
        shutil.rmtree("puzzles")
    os.makedirs("puzzles")
    with open("puzzles/book250.json", "w") as f:
        json.dump(tasks, f, indent=1, ensure_ascii=False)
    print("[DONE] puzzles/book250.json written (250 tasks, shuffled)")


if __name__ == "__main__":
    main()
