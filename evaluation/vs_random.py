"""vs_random.py — match a bot that plays uniformly random LEGAL moves against the
"god" oracle (tablebase), under the exact same protocol and full statistics as
evaluation/vs_god.py, but against the remote HTTP-Range oracle
(tasks/oracle_client.py) instead of a local tablebase copy, so it needs no
8+ GB local tablebase.

Same protocol as vs_god.py:
* Random SYMMETRIC start positions (equal kazans, equal stones, equal non-empty
  pit counts per side) — vs_god.sample_symmetric, reproduced here.
* Every position is played twice: oracle-first and bot-first.
* The oracle always plays optimally (any move attaining max(2 - V(child))).
* optimal_move_rate / blunders_from_win_or_draw are tracked for the random bot's
  OWN applied moves exactly as vs_god.py tracks them for the model — every one
  of vs_god.py's statistics is reproduced here so the two are directly
  comparable. Nothing is skipped to save requests: every ply, on both sides,
  is fully evaluated against the oracle.

Three things this version adds over a naive port, because the remote oracle's
real cost is network data volume, not per-call latency:

1. ONE shared Oracle for the entire run (SharedOracle below), not one per
   thread/game. Two games from the same start position (the bot-first/
   god-first pair) traverse nearly the same early positions, and every game
   eventually funnels into the same small, low-state-count endgame layers —
   sharing one cache means a block already downloaded by any game is reused by
   every other game that needs it, instead of being re-fetched per game.
2. Every oracle lookup, from every game, is funneled through ONE priority
   queue of worker threads (PriorityExecutor), ordered by ascending
   level = k1 + k2. A capture only ever raises k1 + k2, so every game starts
   at a low level and only climbs — processing low-level requests first serves
   whichever request the most other games are also about to need, keeping the
   shared cache warmed in the order that benefits the whole run, not just
   whichever game happened to ask first.
3. Draw-by-repetition: a capture strictly raises k1 + k2 (bounded by 48), so
   any exact repeat of (k1, k2, pits, side-to-move) is necessarily
   capture-free — the position has gone all the way around the board and
   returned unchanged, which both sides can then repeat forever
   (tasks/find_draw_cycles.py proves this directly). Detecting the repeat ends
   a drawn game immediately instead of playing it out to --max-plies.

Progress is reported two ways:
* one tqdm bar over total games completed;
* a per-ply, per-game trace written to --log (default evaluation/vs_random.log),
  plus a periodic snapshot block listing every still-running game's current
  ply and level, so you can see exactly where each of the N concurrent games
  is at any moment, not just an aggregate.

    python3 -m evaluation.vs_random --n 50 --seed 42 --out evaluation/vs_random_results.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import queue
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

import numpy as np
import requests
from tqdm import tqdm

from tasks.oracle_client import Oracle, Position, apply_move, legal_pits

VALUE_NUM = {"loss": 0, "draw": 1, "win": 2}
RESULT_NUM = {"win": 2, "draw": 1, "loss": 0}

log = logging.getLogger("vs_random")


# --------------------------------------------------------------- shared oracle

class SharedOracle(Oracle):
    """A single Oracle instance, safe to hit from many threads at once.

    Oracle's own _headers/_blocks dicts are plain dicts: a cache HIT needs no
    lock (dict.get is atomic under the GIL), but a cache MISS takes a lock keyed
    to that specific URL/block so two threads racing on the exact same fetch
    don't both pay for it — the loser just waits and then hits the now-warm
    cache via the parent class's own re-check.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._offsets_guard = threading.Lock()
        self._offsets_locks: dict[str, threading.Lock] = {}
        self._block_guard = threading.Lock()
        self._block_locks: dict[tuple, threading.Lock] = {}

    @staticmethod
    def _keyed_lock(guard, table, key):
        with guard:
            lock = table.get(key)
            if lock is None:
                lock = table[key] = threading.Lock()
            return lock

    def offsets(self, url):
        if url in self._headers:
            return self._headers[url]
        with self._keyed_lock(self._offsets_guard, self._offsets_locks, url):
            return super().offsets(url)

    def block(self, url, block_index):
        key = (url, block_index)
        cached = self._blocks.get(key)
        if cached is not None:
            return cached
        with self._keyed_lock(self._block_guard, self._block_locks, key):
            return super().block(url, block_index)


# ----------------------------------------------------------- priority fetcher

class PriorityExecutor:
    """Fixed worker-thread pool draining a priority queue ordered by ascending
    `level` (k1 + k2 of the position being queried). Every lookup in the whole
    run — from every game — goes through this one queue, so the scheduler
    globally favors whichever request is for the lowest-level layer, instead of
    first-come-first-served across N independently running games."""

    def __init__(self, n_workers: int):
        self._q: "queue.PriorityQueue" = queue.PriorityQueue()
        self._counter = itertools.count()
        self.n_workers = n_workers
        self._threads = [threading.Thread(target=self._run, daemon=True) for _ in range(n_workers)]
        for t in self._threads:
            t.start()

    def _run(self):
        while True:
            level, _, fn, args, fut = self._q.get()
            if fut is None:
                self._q.task_done()
                return
            try:
                fut.set_result(fn(*args))
            except BaseException as e:            # noqa: BLE001 - propagate to the caller
                fut.set_exception(e)
            self._q.task_done()

    def submit(self, level: int, fn, *args) -> Future:
        fut: Future = Future()
        self._q.put((level, next(self._counter), fn, args, fut))
        return fut

    def shutdown(self):
        for _ in range(self.n_workers):
            self._q.put((-1, next(self._counter), None, None, None))


def value_with_retry(oracle: Oracle, pos: Position, tries: int = 6) -> str:
    """oracle.value() with exponential backoff on transient network errors —
    under concurrency HuggingFace occasionally read-times-out a Range GET;
    that's a retry, not a failure."""
    delay = 0.5
    for attempt in range(tries):
        try:
            return oracle.value(pos)
        except requests.exceptions.RequestException:
            if attempt == tries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 8.0)


# --------------------------------------------------------------- game sampler

def _random_side(rng: np.random.Generator, stones: int, nonzero: int) -> list[int]:
    """A random layout of `stones` stones over 5 pits with exactly `nonzero` non-empty."""
    cells = rng.choice(5, size=nonzero, replace=False)
    cuts = np.sort(rng.choice(stones - 1, size=nonzero - 1, replace=False)) + 1 \
        if nonzero > 1 else np.array([], dtype=int)
    parts = np.diff(np.concatenate([[0], cuts, [stones]]))
    side = [0] * 5
    for c, p in zip(cells, parts):
        side[int(c)] = int(p)
    return side


def sample_symmetric(rng: np.random.Generator) -> Position:
    """Equal kazans, equal stone totals, and an equal number of non-empty pits per side."""
    while True:
        k = int(rng.choice(np.arange(0, 13))) * 2      # each side's kazan: 0..24
        s = (50 - 2 * k) // 2                           # stones held by each side
        if s < 1:
            continue
        c = int(rng.integers(1, min(5, s) + 1))         # non-empty pits per side
        pos = Position(k1=k, k2=k, pits=tuple(_random_side(rng, s, c) + _random_side(rng, s, c)))
        if pos.is_valid():
            return pos


def optimal_moves(fetch: PriorityExecutor, oracle: Oracle, pos: Position) -> tuple[set[int], int]:
    """Every pit attaining max(2 - V(child)) — mirrors make_shards.optimal_move_mask.
    Also returns that max score, which by the minimax identity V(pos) == max(2 - V(child))
    IS the position's own value — no second lookup needed to learn it."""
    children = [(pit, apply_move(pos, pit)) for pit in legal_pits(pos)]
    to_query = [(pit, c) for pit, c in children if not c.wins_immediately]

    values = {pit: 2 for pit, c in children if c.wins_immediately}
    if to_query:
        futs = {
            fetch.submit(c.position.k1 + c.position.k2, value_with_retry, oracle, c.position): pit
            for pit, c in to_query
        }
        for fut in as_completed(futs):
            values[futs[fut]] = VALUE_NUM[fut.result()]

    best, best_pits = -1, set()
    for pit, _ in children:
        score = 2 - values[pit]
        if score > best:
            best, best_pits = score, {pit}
        elif score == best:
            best_pits.add(pit)
    return best_pits, best


# --------------------------------------------------------------------- games

def play(game_id: str, fetch: PriorityExecutor, oracle: Oracle, rng: np.random.Generator,
         pos: Position, god_first: bool, max_plies: int,
         status: dict, status_lock: threading.Lock) -> dict:
    """One game. Returns a small stats dict the main thread aggregates (no shared
    mutable state besides the read-only oracle/fetch queue and the status board)."""
    local = {"bot_moves": 0, "optimal_moves": 0, "suboptimal_moves": 0, "blunders": 0}
    god_turn = god_first
    outcome = "draw"
    ply = 0
    seen = {(pos.k1, pos.k2, pos.pits, god_turn)}

    def update_status(done=False, outcome_=None):
        with status_lock:
            status[game_id] = {"ply": ply, "level": pos.k1 + pos.k2, "k1": pos.k1, "k2": pos.k2,
                                "done": done, "outcome": outcome_}

    update_status()
    for ply in range(1, max_plies + 1):
        if pos.k2 >= 26 or sum(pos.pits[:5]) == 0:      # side to move has already lost
            outcome = "loss" if not god_turn else "win"
            break
        if pos.k1 >= 26:
            outcome = "win" if not god_turn else "loss"
            break

        pits = legal_pits(pos)
        best, v_before = optimal_moves(fetch, oracle, pos)  # v_before == V(pos), full stats always computed
        mover = "god" if god_turn else "bot"
        if god_turn:
            m = next(iter(best))                             # any optimal move is fine for god
        else:
            m = int(rng.choice(pits))
            local["bot_moves"] += 1
            if m in best:
                local["optimal_moves"] += 1
            else:
                local["suboptimal_moves"] += 1
                if v_before >= 1:                            # threw away a win/draw
                    local["blunders"] += 1

        pos = apply_move(pos, m).position
        god_turn = not god_turn
        log.info("%-16s ply=%-4d level=%-2d k1=%-2d k2=%-2d mover=%-4s move=cell%d",
                  game_id, ply, pos.k1 + pos.k2, pos.k1, pos.k2, mover, m + 1)
        update_status()

        key = (pos.k1, pos.k2, pos.pits, god_turn)
        if key in seen:                                      # exact repeat -> forced draw
            outcome = "draw"
            break
        seen.add(key)
    else:
        outcome = "draw"                                      # hit max_plies without resolving

    local["outcome"] = outcome
    log.info("%-16s FINISHED outcome=%s after %d plies", game_id, outcome, ply)
    update_status(done=True, outcome_=outcome)
    return local


def monitor(status: dict, status_lock: threading.Lock, stop_event: threading.Event, interval: float):
    """Periodically logs a full table of every game's current ply/level, so the
    log file shows exactly where each concurrent game stands, not just totals."""
    while not stop_event.wait(interval):
        with status_lock:
            snap = dict(status)
        running = [(gid, s) for gid, s in snap.items() if not s["done"]]
        done_n = sum(1 for s in snap.values() if s["done"])
        log.info("=== snapshot: %d running, %d finished ===", len(running), done_n)
        for gid, s in sorted(running, key=lambda kv: -kv[1]["level"]):
            log.info("    %-16s ply=%-4d level=%-2d (k1=%d k2=%d)",
                      gid, s["ply"], s["level"], s["k1"], s["k2"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="number of symmetric start positions")
    ap.add_argument("--max-plies", type=int, default=400)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--game-workers", type=int, default=0,
                     help="game-driver threads in flight (default: all games at once, 2*n)")
    ap.add_argument("--fetch-workers", type=int, default=32,
                     help="worker threads servicing the shared, level-ordered fetch queue")
    ap.add_argument("--out", default="evaluation/vs_random_results.json")
    ap.add_argument("--log", default="evaluation/vs_random.log")
    ap.add_argument("--snapshot-interval", type=float, default=5.0,
                     help="seconds between full per-game status snapshots in --log")
    a = ap.parse_args()

    logging.basicConfig(filename=a.log, filemode="w", level=logging.INFO,
                         format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    oracle = SharedOracle()
    fetch = PriorityExecutor(a.fetch_workers)
    rng = np.random.default_rng(a.seed)
    game_workers = a.game_workers or 2 * a.n
    print(f"positions={a.n}  (2 games per position, {2 * a.n} games total)  seed={a.seed}  "
          f"game_workers={game_workers}  fetch_workers={a.fetch_workers}  log={a.log}")

    jobs = []
    theo = {"win": 0, "draw": 0, "loss": 0}
    for i in range(a.n):
        pos = sample_symmetric(rng)
        v0 = VALUE_NUM[fetch.submit(pos.k1 + pos.k2, value_with_retry, oracle, pos).result()]
        theo[["loss", "draw", "win"][v0]] += 1
        for god_first in (True, False):
            game_seed = int(rng.integers(0, 2**32 - 1))
            gid = f"pos{i:03d}-{'god' if god_first else 'bot'}first"
            jobs.append({"id": gid, "idx": i, "pos": pos, "v0": v0, "god_first": god_first,
                         "rng": np.random.default_rng(game_seed)})

    stats = {"bot_moves": 0, "optimal_moves": 0, "suboptimal_moves": 0, "blunders": 0}
    res = {k: {"win": 0, "draw": 0, "loss": 0} for k in ("bot_first", "god_first")}
    underperf = 0
    n_done = 0
    lock = threading.Lock()
    status: dict[str, dict] = {}
    status_lock = threading.Lock()
    stop_event = threading.Event()
    mon = threading.Thread(target=monitor, args=(status, status_lock, stop_event, a.snapshot_interval),
                            daemon=True)
    mon.start()

    def snapshot() -> dict:
        opt_rate = stats["optimal_moves"] / max(1, stats["bot_moves"])
        out = {
            "opponent": "random_legal_move_bot",
            "n_positions": a.n, "n_positions_done": a.n,
            "n_games": 2 * a.n, "n_games_done": n_done,
            "theoretical_start_values_for_side_to_move": dict(theo),
            "results_bot_first": dict(res["bot_first"]),
            "results_god_first": dict(res["god_first"]),
            "total_applied_bot_moves": stats["bot_moves"],
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

    pbar = tqdm(total=len(jobs), desc="games", unit="game")
    with ThreadPoolExecutor(max_workers=game_workers) as pool:
        futs = {
            pool.submit(play, job["id"], fetch, oracle, job["rng"], job["pos"], job["god_first"],
                        a.max_plies, status, status_lock): job
            for job in jobs
        }
        for fut in as_completed(futs):
            job = futs[fut]
            r = fut.result()
            side = "god_first" if job["god_first"] else "bot_first"
            with lock:
                res[side][r["outcome"]] += 1
                stats["bot_moves"] += r["bot_moves"]
                stats["optimal_moves"] += r["optimal_moves"]
                stats["suboptimal_moves"] += r["suboptimal_moves"]
                stats["blunders"] += r["blunders"]
                theory_floor = (2 - job["v0"]) if job["god_first"] else job["v0"]
                if RESULT_NUM[r["outcome"]] < theory_floor:
                    underperf += 1
                n_done += 1
                out = snapshot()
            pbar.update(1)
            pbar.set_postfix(opt_rate=f"{out['optimal_move_rate']:.4f}",
                              blunders=stats["blunders"], worse_than_theory=underperf)
    pbar.close()
    stop_event.set()
    fetch.shutdown()

    print("\n" + "=" * 66)
    print(f"  RANDOM-LEGAL-MOVE BOT AGAINST THE GOD ORACLE  ({out['n_games']} games)")
    print("=" * 66)
    print(f"  Theoretical start values (mover): win={theo['win']} "
          f"draw={theo['draw']} loss={theo['loss']}")
    print(f"  Bot first     : {res['bot_first']}")
    print(f"  Oracle first  : {res['god_first']}")
    print(f"  Bot moves played          : {stats['bot_moves']:,}")
    print(f"  Optimal                   : {stats['optimal_moves']:,} "
          f"({out['optimal_move_rate']:.5f})")
    print(f"  Suboptimal                : {stats['suboptimal_moves']:,}")
    print(f"  Blunders from win/draw    : {stats['blunders']}")
    print(f"  Games below theory        : {underperf} / {out['n_games']}")
    print("=" * 66)
    print(f"results saved: {a.out}")
    print(f"per-ply log:   {a.log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
