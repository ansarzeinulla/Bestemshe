"""bestemshe_core.py — core: position encoding, ranking, tablebase access.

rank()/unrank() are a direct port of Solver.h::IndexBoard /
StateIndex::UnindexState (colexicographical combinatorial number system);
apply_move()/legal_moves() are equivalent to BestemsheCore.h::ExecuteMoveAndFlip;
the terminal rules (empty side / kazan >= 26) match Solver.cpp and query.cpp.

Check without a tablebase:  python make_shards.py --selftest
Check with a tablebase:     python make_shards.py --tb ... --verify 2000
"""
import functools, os
from collections import OrderedDict
from math import comb as _comb
import numpy as np
import zstandard as zstd
from tqdm import tqdm

N_PITS = 10      # 10 pits (5 own + 5 opponent)
STONES = 50      # invariant: sum(pits) + K1 + K2 == 50
KAZANS = [(k1, k2) for k1 in range(0, 26, 2) for k2 in range(0, 26, 2)]  # 169 layers


@functools.lru_cache(maxsize=None)
def comb(n, k):
    return _comb(n, k) if n >= 0 and 0 <= k <= n else 0


def count_states(total, pits=N_PITS):
    """Number of ways to distribute `total` stones over `pits` pits (stars and bars)."""
    return comb(total + pits - 1, pits - 1)


def rank(pits_cfg):
    """Pit configuration -> bit index within the layer.
    Port of Solver.h::IndexBoard (colex combinatorial number system):
    I_B = sum_{i=0..8} C(i + prefix_sum(board[0..i]), i+1)."""
    idx = s = 0
    for i in range(9):
        s += pits_cfg[i]
        idx += comb(i + s, i + 1)
    return idx


def unrank(idx, total, pits=N_PITS):
    """Bit index -> pit configuration (inverse of rank).
    Port of StateIndex::UnindexState (board part)."""
    cfg = [0] * pits
    current_p = 0
    for i in range(8, -1, -1):
        p = i
        while comb(p + 1, i + 1) <= idx:
            p += 1
        idx -= comb(p, i + 1)
        if i == 8:
            cfg[9] = total + 8 - p
        else:
            cfg[i + 1] = current_p - p - 1
        current_p = p
    cfg[0] = current_p
    return cfg


@functools.lru_cache(maxsize=1)
def _weights():
    w = [count_states(STONES - k1 - k2) for k1, k2 in KAZANS]
    s = float(sum(w))
    return tuple(x / s for x in w)


def layer_weights():
    return np.array(_weights())


def sample_position(rng):
    """Layer sampled proportionally to its state count; index within it uniformly."""
    k1, k2 = KAZANS[int(rng.choice(len(KAZANS), p=layer_weights()))]
    total = STONES - k1 - k2
    return (k1, k2, unrank(int(rng.integers(count_states(total))), total))


ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"        # zstd frame magic (little-endian)
BLOCK_BYTES = 33554432 // 8             # 4 MiB — Compressor::CompressMicroLayer


def _unzstd(data, max_size):
    """Decompress a single zstd frame; works even without content-size in the header."""
    dctx = zstd.ZstdDecompressor()
    try:
        return dctx.decompress(data, max_output_size=max_size)
    except zstd.ZstdError:
        return dctx.decompressobj().decompress(data)


def _parse_container(data, expected):
    """Port of Compressor::DecompressMicroLayer: container layout
    [u32 num_blocks][u32 offsets[num_blocks+1]][independent 4 MiB zstd blocks].
    Returns a bitset of exactly `expected` bytes, or None if this is not a container."""
    if len(data) < 8:
        return None
    num_blocks = int.from_bytes(data[:4], "little")
    if not 0 < num_blocks <= expected // BLOCK_BYTES + 2:
        return None
    header = 4 + 4 * (num_blocks + 1)
    if len(data) < header:
        return None
    offsets = np.frombuffer(data[4:header], dtype="<u4").astype(np.int64)
    if offsets[0] != header or offsets[-1] > len(data) or np.any(np.diff(offsets) < 0):
        return None
    dctx = zstd.ZstdDecompressor()
    out = bytearray()
    for b in tqdm(range(num_blocks), desc="decompressing layer", unit="block",
                  leave=False, disable=num_blocks < 8):
        out += dctx.decompress(data[offsets[b]:offsets[b + 1]],
                               max_output_size=BLOCK_BYTES)
    return bytes(out[:expected])


class Tablebase:
    """Access to the win/draw bitsets. Keeps up to max_layers decompressed layers
    in RAM (the largest, (0,0)_win, is ~1.6 GB expanded)."""

    def __init__(self, root, max_layers=8):
        self.root, self.max_layers = root, max_layers
        self._cache = OrderedDict()

    def _find(self, name):
        """Layer files are looked up in root/ and root/data/ with the suffixes
        .bin.zst (HF dataset), .bin (layers/compressed), .raw (bare bitset)."""
        for sub in ("", "data"):
            for suf in (".bin.zst", ".bin", ".raw"):
                p = os.path.join(self.root, sub, name + suf)
                if os.path.exists(p):
                    return p
        raise FileNotFoundError(
            f"{name}.* not found in {self.root} (searched ./ and data/, "
            f"suffixes .bin.zst/.bin/.raw)")

    def _bits(self, k1, k2, kind):
        key = (k1, k2, kind)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        path = self._find(f"layer_{k1}_{k2}_{kind}")
        with open(path, "rb") as fh:
            data = fh.read()
        # Format autodetection: bare bitset / zstd(bitset) / container /
        # zstd(container). The expected bitset size is known exactly.
        expected = (count_states(STONES - k1 - k2) + 7) // 8
        if data[:4] == ZSTD_MAGIC:
            # the result is either a bitset (expected bytes) or a container (no
            # larger than the bitset plus slack for incompressible blocks and
            # the offset table)
            max_size = expected + expected // 128 + (1 << 20)
            data = _unzstd(data, max_size=max_size)
        if len(data) != expected:
            parsed = _parse_container(data, expected)
            if parsed is None:
                raise ValueError(
                    f"{path}: decompressed to {len(data)} bytes instead of "
                    f"{expected}, and it is not the solver's block container — "
                    f"file format not recognised")
            data = parsed
        if len(data) != expected:
            raise ValueError(f"{path}: bitset is {len(data)} bytes, expected {expected}")
        self._cache[key] = data
        if len(self._cache) > self.max_layers:
            self._cache.popitem(last=False)
        return data

    def value(self, pos):
        """0 = LOSS, 1 = DRAW, 2 = WIN for the side to move.
        Terminal rules mirror Solver.cpp/query.cpp."""
        k1, k2, pits = pos
        if k1 >= 26: return 2            # a kazan >= 26 decides the game immediately
        if k2 >= 26: return 0
        if sum(pits[:5]) == 0: return 0  # empty side to move = loss
        idx = rank(pits)
        w = self._bits(k1, k2, "win")
        if (w[idx >> 3] >> (idx & 7)) & 1: return 2   # LSB-first, as in
        d = self._bits(k1, k2, "draw")                # Solver.cpp/Oracle.h
        if (d[idx >> 3] >> (idx & 7)) & 1: return 1
        return 0


def legal_moves(pos):
    """Own pits are indices 0..4; a move is possible from any non-empty pit."""
    return [i for i in range(5) if pos[2][i] > 0]


def is_terminal_loss(pos):
    """The side to move has already lost by the rules, WITHOUT the tablebase:
    the opponent's kazan is >= 26, or its own side is empty (Solver.cpp / query.cpp)."""
    return pos[1] >= 26 or sum(pos[2][:5]) == 0


def apply_move(pos, move):
    """A move by the side to move. Returns the position FROM THE OPPONENT'S POINT
    OF VIEW (the canonical tablebase form). Line-for-line equivalent to
    BestemsheCore.h::ExecuteMoveAndFlip / Solver.h::execute_move_and_flip."""
    k1, k2, pits = pos
    pits = list(pits)
    stones = pits[move]
    if stones == 1:                      # a lone stone moves to the next pit
        pits[move] = 0
        last = (move + 1) % N_PITS
        pits[last] += 1
    else:                                # leave 1 behind, sow the rest onward
        pits[move] = 1
        cur = move
        for _ in range(stones - 1):
            cur = (cur + 1) % N_PITS
            pits[cur] += 1
        last = cur
    if 5 <= last <= 9 and pits[last] % 2 == 0:   # capture: even opponent pit
        k1 += pits[last]
        pits[last] = 0
    return (k2, k1, pits[5:] + pits[:5])         # flip the board


def verify_consistency(tb, n=1000, seed=0):
    """Game-theoretic self-check: V(pos) == max over moves of (2 - V(child)).
    Catches ANY divergence in rules or indexing from the solver before training."""
    root_v = tb.value((0, 0, [5] * 10))  # anchor: the second player's win is proven
    if root_v != 0:
        print(f"ANCHOR FAILED: value(start) = {root_v}, expected 0 "
              f"(LOSS — forced win for the second player)")
        return False
    rng = np.random.default_rng(seed)
    bad = checked = 0
    for _ in tqdm(range(n), desc="consistency", unit="pos"):
        pos = sample_position(rng)
        moves = legal_moves(pos)
        if not moves:
            continue                     # verify the terminal rules separately
        checked += 1
        best = max(2 - tb.value(apply_move(pos, m)) for m in moves)
        if tb.value(pos) != best:
            bad += 1
    print(f"consistency: {checked - bad}/{checked} ok")
    return bad == 0
