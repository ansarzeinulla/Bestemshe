"""make_shards.py — generate training shards from the tablebase.

Record format — 14 uint8 bytes:
  [0:10] pits (0..50)    [10] K1//2   [11] K2//2
  [12]   WDL (0=loss, 1=draw, 2=win)
  [13]   bitmask of optimal moves (bits 0..4)

Verify the rank/unrank port WITHOUT a tablebase (free, local):
  python make_shards.py --selftest
Self-check BEFORE generation (mandatory):
  python make_shards.py --tb /workspace/tablebase --verify 2000
Full run (the mode is mandatory: overwrite or append):
  python make_shards.py --tb /workspace/tablebase --out /workspace/shards \
      --n 500_000_000 --workers 24 --mode overwrite

Continuous-learning options:
  --mode overwrite|append  — overwrite: delete the old shard_*.bin before
                             starting and number from 0; append: continue
                             numbering from the last existing shard, leaving
                             the old files untouched.
  generation_status.json  — written into --out atomically (via os.replace)
                             after every finished worker, so that `cat
                             generation_status.json` in another terminal always
                             shows consistent progress/speed/ETA.
"""
import argparse, datetime, glob, json, os, re, time
import numpy as np
from multiprocessing import Pool
from tqdm import tqdm
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from training.bestemshe_core import (Tablebase, KAZANS, sample_position, layer_weights,
                            count_states, rank, unrank, legal_moves, apply_move,
                            verify_consistency, STONES)

BLOCK = 50_000   # consecutive positions from one layer — spares the decompressed-layer cache
STATUS_FILE = "generation_status.json"


def optimal_move_mask(tb, pos):
    """A move is optimal if it attains max(2 - V(child)) — the best outcome for the mover."""
    moves = legal_moves(pos)
    if not moves:
        return 0
    child = {m: tb.value(apply_move(pos, m)) for m in moves}
    best = max(2 - v for v in child.values())
    return sum(1 << m for m, v in child.items() if 2 - v == best)


def _compositions(total, parts):
    """Every distribution of `total` stones over `parts` pits (for exhaustive enumeration)."""
    if parts == 1:
        yield (total,)
        return
    for v in range(total + 1):
        for rest in _compositions(total - v, parts - 1):
            yield (v,) + rest


def selftest():
    """Check that rank/unrank match the solver's indexing (StateIndex.h /
    Solver.h::IndexBoard) without a tablebase. The anchor values were computed
    by the C++ code. NOTE: at R=1 the colex and lex orders coincide, so the
    exhaustive tests start at R>=2."""
    # Anchor from C++ IndexBoard: board (0,2,0,...,0) -> index 52 (lex rank would give 44)
    anchor = (0, 2, 0, 0, 0, 0, 0, 0, 0, 0)
    assert rank(anchor) == 52, f"rank{anchor} = {rank(anchor)}, expected 52 (C++ IndexBoard)"
    assert unrank(52, 2) == list(anchor), f"unrank(52, 2) = {unrank(52, 2)}, expected {list(anchor)}"

    for R in range(2, 6):                # exhaustive: bijection + round-trip
        n = count_states(R)
        seen = set()
        for cfg in tqdm(_compositions(R, 10), total=n,
                        desc=f"selftest R={R}", unit="state", leave=False):
            r = rank(cfg)
            assert 0 <= r < n and r not in seen, f"rank is not a bijection at R={R}: {cfg} -> {r}"
            seen.add(r)
            assert unrank(r, R) == list(cfg), f"round-trip failed: {cfg} -> {r} -> {unrank(r, R)}"
        assert len(seen) == n
        # unrank(0) = (0,...,0,R): consistent with the wrap in Solver.cpp (AdvanceBoard)
        assert unrank(0, R) == [0] * 9 + [R]
        print(f"selftest R={R}: {n} states, bijection and round-trip ok")

    rng = np.random.default_rng(0)       # random round-trips over the full range
    for _ in tqdm(range(2000), desc="round-trip", unit="pos", leave=False):
        R = int(rng.integers(0, 51))
        i = int(rng.integers(count_states(R)))
        assert rank(tuple(unrank(i, R))) == i, f"round-trip failed: R={R}, idx={i}"
    print("selftest: 2000 random round-trips (R up to 50) ok")
    print("selftest: OK — rank/unrank match the solver's indexing")


def _worker(args):
    seed, count, tb_root = args
    rng = np.random.default_rng(seed)
    tb = Tablebase(tb_root)
    out = np.empty((count, 14), dtype=np.uint8)
    i = 0
    while i < count:                     # in blocks drawn from one (K1, K2) layer
        k1, k2 = KAZANS[int(rng.choice(len(KAZANS), p=layer_weights()))]
        n_states = count_states(STONES - k1 - k2)
        for _ in range(min(BLOCK, count - i)):
            pits = unrank(int(rng.integers(n_states)), STONES - k1 - k2)
            pos = (k1, k2, pits)
            out[i, :10] = pits
            out[i, 10], out[i, 11] = k1 // 2, k2 // 2
            out[i, 12] = tb.value(pos)
            out[i, 13] = optimal_move_mask(tb, pos)
            i += 1
    return out


_SHARD_RE = re.compile(r"shard_(\d+)\.bin$")


def _existing_shards(out_dir):
    """Sorted list of (index, path) for the shards already present in out_dir."""
    found = []
    for p in glob.glob(os.path.join(out_dir, "shard_*.bin")):
        m = _SHARD_RE.search(p)
        if m:
            found.append((int(m.group(1)), p))
    return sorted(found)


class StatusWriter:
    """Writes generation_status.json atomically — you can `cat` it at any moment
    and always get consistent JSON (write to a temp file, then os.replace)."""

    def __init__(self, path, mode, out_dir, target_n, existing_positions, existing_shards):
        self.path = path
        self.mode = mode
        self.out_dir = out_dir
        self.target_n = target_n
        self.existing_positions = existing_positions
        self.existing_shards = existing_shards
        self.generated = 0
        self.shards_written = 0
        self.t0 = time.time()

    def update(self, generated=None, shards_written=None, status="running", extra=None):
        if generated is not None:
            self.generated = generated
        if shards_written is not None:
            self.shards_written = shards_written
        elapsed = time.time() - self.t0
        speed = self.generated / elapsed if elapsed > 0 else 0.0
        remaining = max(0, self.target_n - self.generated)
        eta_sec = remaining / speed if speed > 0 else None
        payload = {
            "status": status,
            "mode": self.mode,
            "out_dir": self.out_dir,
            "generated_this_run": self.generated,
            "target_this_run": self.target_n,
            "shards_written_this_run": self.shards_written,
            "total_positions_on_disk": self.existing_positions + self.generated,
            "total_shards_on_disk": self.existing_shards + self.shards_written,
            "elapsed_sec": round(elapsed, 1),
            "speed_pos_per_sec": round(speed, 1),
            "eta_sec": round(eta_sec, 1) if eta_sec is not None else None,
            "eta_human": str(datetime.timedelta(seconds=int(eta_sec))) if eta_sec is not None else None,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if extra:
            payload.update(extra)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)  # atomic swap — cat never sees a torn JSON file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tb")              # required for everything except --selftest
    ap.add_argument("--out", default="/workspace/shards")
    ap.add_argument("--n", type=int, default=500_000_000)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--shard-size", type=int, default=20_000_000)
    ap.add_argument("--verify", type=int, default=0)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mode", choices=["overwrite", "append"],
                    help="overwrite: delete the old shards and start from 0; "
                         "append: continue numbering from the existing files")
    a = ap.parse_args()

    if a.selftest:                       # rank/unrank check without a tablebase
        selftest()
        raise SystemExit(0)

    if not a.tb:
        ap.error("--tb is required (except in --selftest mode)")

    if a.verify:                         # self-check mode — no generation
        ok = verify_consistency(Tablebase(a.tb), n=a.verify)
        raise SystemExit(0 if ok else
                         "STOP: rules/indexing do NOT match the tablebase")

    if not a.mode:
        ap.error("--mode is required: overwrite or append")

    os.makedirs(a.out, exist_ok=True)

    existing = _existing_shards(a.out)
    if a.mode == "overwrite":
        for _, p in existing:
            os.remove(p)
        start_shard = 0
        existing_positions = 0
        existing_shards = 0
    else:  # append
        start_shard = (existing[-1][0] + 1) if existing else 0
        existing_shards = len(existing)
        # size of the existing files in positions (14 bytes/record) — for the status file
        existing_positions = sum(os.path.getsize(p) // 14 for _, p in existing)

    status = StatusWriter(os.path.join(a.out, STATUS_FILE), a.mode, a.out,
                          a.n, existing_positions, existing_shards)
    status.update(generated=0, shards_written=0)

    per_worker = a.shard_size // a.workers
    n_shards = a.n // a.shard_size
    generated = 0
    try:
        with Pool(a.workers) as pool:
            for s in tqdm(range(n_shards), desc="shards", unit="shard"):
                shard_idx = start_shard + s
                jobs = [(shard_idx * a.workers + w, per_worker, a.tb)
                        for w in range(a.workers)]
                # imap preserves the job order; the bar tracks finished workers of the shard
                chunks = []
                for chunk in tqdm(pool.imap(_worker, jobs), total=len(jobs),
                                  desc=f"shard {shard_idx:04d}", unit="worker", leave=False):
                    chunks.append(chunk)
                    generated += len(chunk)
                    status.update(generated=generated, shards_written=s)
                shard = np.concatenate(chunks)
                shard.tofile(os.path.join(a.out, f"shard_{shard_idx:04d}.bin"))
                status.update(generated=generated, shards_written=s + 1)
                tqdm.write(f"shard {shard_idx:04d} done ({generated:,} positions in this run)")
    except BaseException:
        status.update(status="failed")
        raise
    else:
        status.update(status="done")


if __name__ == "__main__":
    main()
