#!/usr/bin/env python3
"""
generate_puzzles.py — configurable collection of Bestemshe tasks (schema v3).

Drives the C++ generateTasks binary across every layer listed in an input file, applies the
colour split and the stratification level, and writes a single JSON book.

Usage:
    python3 -m tasks.generate_puzzles --input tasks/input.txt --type atsyrau --moves 2 \\
        --branching 6 --total 60 --black-proportion 0.5 --stratify 0.3 \\
        --output puzzles/book_v3.json

Every option can instead be supplied through --config cfg.json using the same
(underscored) names; explicit command-line flags win over the config file.
"""
import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
from collections import Counter

TASK_TYPES = ["mate", "atsyrau", "capture_total", "capture_single", "loop"]

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


# CLI name -> generateTasks flag, for the twelve position filters.
FILTER_FLAGS = {
    "min_kazan_white": "--minKazanWhite", "max_kazan_white": "--maxKazanWhite",
    "min_kazan_black": "--minKazanBlack", "max_kazan_black": "--maxKazanBlack",
    "min_stones_white": "--minStonesWhite", "max_stones_white": "--maxStonesWhite",
    "min_stones_black": "--minStonesBlack", "max_stones_black": "--maxStonesBlack",
    "min_empty_white": "--minEmptyWhite", "max_empty_white": "--maxEmptyWhite",
    "min_empty_black": "--minEmptyBlack", "max_empty_black": "--maxEmptyBlack",
}


def parse_layer_token(tok: str):
    """Accepts '2_8' or 'layers/compressed/layer_2_8_win.bin' -> (2, 8)."""
    stem = os.path.basename(tok.strip())
    if stem.startswith("layer_"):
        stem = stem[len("layer_"):]
    for suffix in ("_win.bin", "_draw.bin", "_win.raw", "_draw.raw", ".bin", ".raw"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    k1, k2 = stem.split("_")
    return int(k1), int(k2)


def read_input_file(path):
    """One layer token per line; '#' comments and blank lines are ignored."""
    layers = []
    with open(path) as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            try:
                layers.append(parse_layer_token(line))
            except ValueError:
                print(f"[WARN] {path}:{lineno}: cannot parse '{line}', skipped",
                      file=sys.stderr)
    # De-duplicate but keep first-seen order.
    seen, out = set(), []
    for lay in layers:
        if lay not in seen:
            seen.add(lay)
            out.append(lay)
    return out


def in_range(v, lo, hi):
    if lo is not None and v < lo:
        return False
    if hi is not None and v > hi:
        return False
    return True


def run_extract(layer, args, count, seed):
    """Invoke generateTasks for one layer and return the parsed task list."""
    cmd = [_bin("generateTasks"),
           "--layer", f"{layer[0]}_{layer[1]}",
           "--taskType", args.type,
           "--moves", str(args.moves),
           "--minMoves", str(args.min_moves),
           "--count", str(count),
           "--seed", str(seed),
           "--maxAttempts", str(args.max_attempts)]
    if args.branching is not None:
        cmd += ["--branching", str(args.branching)]
    if args.capture_k is not None:
        cmd += ["--captureK", str(args.capture_k)]
    if args.allow_multiple:
        cmd += ["--allowMultiple"]
    for name, flag in FILTER_FLAGS.items():
        val = getattr(args, name)
        if val is not None:
            cmd += [flag, str(val)]

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tmp = tf.name
    try:
        cmd += ["--jsonOut", tmp]
        subprocess.run(cmd, capture_output=True, check=False)
        with open(tmp) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    finally:
        os.unlink(tmp)


def stratify(tasks, level, rng):
    """level=0 -> strictly sorted by difficulty; level=1 -> effectively shuffled.

    Ranks the tasks by a difficulty key, then re-sorts by the rank displaced by
    noise scaled to `level`, so intermediate values interpolate smoothly.
    """
    n = len(tasks)
    if n <= 1:
        return tasks
    ordered = sorted(tasks, key=lambda t: (t["task"]["n"], t["leaf_variations"],
                                           t["layer"]))
    if level <= 0:
        return ordered
    jittered = [(i + level * n * rng.uniform(-0.5, 0.5), t)
                for i, t in enumerate(ordered)]
    jittered.sort(key=lambda pair: pair[0])
    return [t for _, t in jittered]


def build_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="JSON file of defaults (same option names)")
    ap.add_argument("--input", default="input.txt",
                    help="file listing the layers to draw positions from")
    ap.add_argument("--type", choices=TASK_TYPES, default="mate")
    ap.add_argument("--moves", type=int, default=1, help="N")
    ap.add_argument("--min-moves", type=int, default=1,
                    help="reject goals already forced in fewer than this many moves")
    ap.add_argument("--capture-k", type=int, default=None,
                    help="K, for capture_total / capture_single")
    ap.add_argument("--branching", type=int, default=None,
                    help="b: max TOTAL number of variations in the solution")
    ap.add_argument("--total", type=int, default=250, help="how many tasks to collect")
    ap.add_argument("--black-proportion", type=float, default=0.5,
                    help="fraction of tasks shown rotated, as Black (0..1)")
    ap.add_argument("--stratify", type=float, default=1.0,
                    help="0 = sorted by difficulty, 1 = fully stratified")
    ap.add_argument("--allow-multiple", action="store_true",
                    help="accept positions with several solutions (all are written)")
    ap.add_argument("--per-layer", type=int, default=4,
                    help="max tasks taken from one layer in the first pass")
    ap.add_argument("--max-attempts", type=int, default=400000)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--output", default="puzzles/book_v3.json")
    for name in FILTER_FLAGS:
        ap.add_argument("--" + name.replace("_", "-"), type=int, default=None)
    return ap


def main():
    ap = build_parser()
    args = ap.parse_args()

    # Config file supplies defaults; anything given on the command line wins.
    if args.config:
        with open(args.config) as f:
            cfg = json.load(f)
        explicit = {a.lstrip("-").replace("-", "_") for a in sys.argv[1:]
                    if a.startswith("--")}
        for key, val in cfg.items():
            key = key.replace("-", "_")
            if key not in explicit and hasattr(args, key):
                setattr(args, key, val)

    if not 0.0 <= args.black_proportion <= 1.0:
        ap.error("--black-proportion must be between 0 and 1")
    if not 0.0 <= args.stratify <= 1.0:
        ap.error("--stratify must be between 0 and 1")
    if args.type in ("capture_total", "capture_single") and args.capture_k is None:
        ap.error(f"--capture-k is required for --type {args.type}")

    rng = random.Random(args.seed)
    layers = read_input_file(args.input)
    if not layers:
        print(f"[FATAL] No layers parsed from {args.input}", file=sys.stderr)
        sys.exit(1)

    # Kazan bounds are fixed per layer, so whole files can be skipped up front.
    eligible = [lay for lay in layers
                if in_range(lay[0], args.min_kazan_white, args.max_kazan_white)
                and in_range(lay[1], args.min_kazan_black, args.max_kazan_black)]
    print(f"[INFO] {len(layers)} layers listed, {len(eligible)} pass the kazan filters")
    if not eligible:
        print("[FATAL] No layer satisfies the kazan filters", file=sys.stderr)
        sys.exit(1)

    order = eligible[:]
    rng.shuffle(order)

    tasks, seen_fens = [], set()
    # Pass 1 takes a small share per layer for spread; pass 2 takes the rest.
    for take_cap in (args.per_layer, args.total):
        for layer in order:
            need = args.total - len(tasks)
            if need <= 0:
                break
            got = run_extract(layer, args, min(need, take_cap), rng.randrange(1 << 30))
            for t in got:
                if t["fen"] in seen_fens:
                    continue
                seen_fens.add(t["fen"])
                tasks.append(t)
                if len(tasks) >= args.total:
                    break
        if len(tasks) >= args.total:
            break

    if not tasks:
        print("[FATAL] No tasks collected", file=sys.stderr)
        sys.exit(1)
    if len(tasks) < args.total:
        print(f"[WARN] Collected only {len(tasks)}/{args.total} tasks", file=sys.stderr)

    # Colour: assign to a random subset so it is independent of layer/difficulty.
    n_black = round(args.black_proportion * len(tasks))
    idx = list(range(len(tasks)))
    rng.shuffle(idx)
    black = set(idx[:n_black])
    for i, t in enumerate(tasks):
        t["color"] = "b" if i in black else "w"

    tasks = stratify(tasks, args.stratify, rng)
    for i, t in enumerate(tasks):
        t["id"] = f"#A{i + 1}"

    meta = {
        "schema": 3,
        "task_type": args.type,
        "moves": args.moves,
        "min_moves": args.min_moves,
        "capture_k": args.capture_k,
        "branching": args.branching,
        "black_proportion": args.black_proportion,
        "stratify": args.stratify,
        "allow_multiple": args.allow_multiple,
        "seed": args.seed,
        "input_file": args.input,
        "count": len(tasks),
        "filters": {k: getattr(args, k) for k in FILTER_FLAGS},
        "layers_used": sorted({t["layer"] for t in tasks}),
    }

    # Self-checks
    assert len({t["fen"] for t in tasks}) == len(tasks), "duplicate FENs"
    colours = Counter(t["color"] for t in tasks)
    assert colours["b"] == n_black, colours
    if args.branching is not None:
        bad = [t["fen"] for t in tasks if t["leaf_variations"] > args.branching]
        assert not bad, f"branching exceeded: {bad[:3]}"
    print(f"[CHECK] {len(tasks)} tasks, colours={dict(colours)}, "
          f"layers={len(meta['layers_used'])}")

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump({"meta": meta, "tasks": tasks}, f, indent=1, ensure_ascii=False)
    print(f"[DONE] {args.output} written")


if __name__ == "__main__":
    main()
