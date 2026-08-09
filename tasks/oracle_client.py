"""Query the Bestemshe endgame oracle on Hugging Face via HTTP Range requests.

No local tablebase download, no C++ compile step — each lookup fetches only
the 4MiB compressed block that contains the bit it needs.

Needs only: pip install requests zstandard

CLI:
    python -m tasks.oracle_client 0 0 5 5 5 5 5 5 5 5 5 5
    python -m tasks.oracle_client --children 0 0 5 5 5 5 5 5 5 5 5 5
    python -m tasks.oracle_client --locate 0 0 5 5 5 5 5 5 5 5 5 5

The 12 integers are K1 K2 p0..p9 from the side-to-move perspective
(K1/p0-p4 belong to the mover). Stones total 50; kazans are even.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, NamedTuple

import requests
import zstandard

TABLEBASE_DATASET = os.environ.get("BESTEMSHE_DATASET", "ansarzeinulla/bestemshe-tablebase")
BASE_URL = os.environ.get(
    "BESTEMSHE_ORACLE_BASE_URL",
    f"https://huggingface.co/datasets/{TABLEBASE_DATASET}/resolve/main/layers/compressed",
)

TOTAL_STONES = 50          # conserved: k1 + k2 + sum(pits)
NUM_PITS = 5               # pits per side
MAX_KAZAN = 24             # largest kazan the dataset stores
WIN_THRESHOLD = 26         # a kazan this large has already won
BYTES_PER_BLOCK = 33_554_432 // 8   # 4 MiB decompressed per block

Verdict = Literal["win", "loss", "draw", "unknown"]


@dataclass(frozen=True)
class Position:
    """Side-to-move relative. pits[0:5] are the mover's own pits."""
    k1: int
    k2: int
    pits: tuple[int, ...]          # length 10

    def is_valid(self) -> bool:
        if not (0 <= self.k1 <= MAX_KAZAN and self.k1 % 2 == 0):
            return False
        if not (0 <= self.k2 <= MAX_KAZAN and self.k2 % 2 == 0):
            return False
        if len(self.pits) != 10 or any(not 0 <= p < TOTAL_STONES for p in self.pits):
            return False
        return self.k1 + self.k2 + sum(self.pits) == TOTAL_STONES


# ---------------------------------------------------------------- indexing

@lru_cache(maxsize=None)
def n_c_r(n: int, r: int) -> int:
    """Exact binomial; 0 outside the domain, matching StateIndex.h's nCr."""
    if n < 0 or r < 0 or n < r:
        return 0
    if r == 0 or n == r:
        return 1
    r = min(r, n - r)
    result = 1
    for i in range(r):
        result = result * (n - i) // (i + 1)
    return result


def min_kazan(m: int) -> int:
    """Smallest possible side-to-move kazan given m = k1 + k2 captured."""
    return max(0, m - MAX_KAZAN)


def index_state(pos: Position) -> int:
    """The position's rank WITHIN its (k1, k2) layer file.

    Each layer_<k1>_<k2>_*.bin file already isolates one kazan slice, so the
    on-disk bit index is just I_B — the board composition's stars-and-bars
    rank (a multiset rank). This mirrors Oracle.h's TablebaseOracle::query(),
    which computes the same global IndexState (I_K * b_count + I_B) as the
    monolithic in-memory tablebase would use, then reduces it mod b_count to
    land on the per-file offset — equivalent to using I_B alone here.
    """
    i_b = 0
    running = 0
    for i in range(9):                      # 9, not 10: the last pit is implied
        running += pos.pits[i]
        i_b += n_c_r(i + running, i + 1)

    return i_b


class BitLocation(NamedTuple):
    block_index: int
    local_byte: int      # byte offset inside the DECOMPRESSED block
    bit_offset: int      # 0..7, little-endian within the byte


def bit_location(rank: int) -> BitLocation:
    byte_index = rank // 8
    return BitLocation(
        block_index=byte_index // BYTES_PER_BLOCK,
        local_byte=byte_index % BYTES_PER_BLOCK,
        bit_offset=rank % 8,
    )


def layer_urls(pos: Position, base_url: str = BASE_URL) -> tuple[str, str]:
    """(win_url, draw_url) for this position's layer."""
    return (f"{base_url}/layer_{pos.k1}_{pos.k2}_win.bin",
            f"{base_url}/layer_{pos.k1}_{pos.k2}_draw.bin")


# ------------------------------------------------------------------ moves

class Child(NamedTuple):
    pit: int                    # 0..4, the mover's own pit
    land: int                   # 0..9, where the last sown stone landed (pre-flip board)
    position: "Position"        # the flipped board after the move (always populated,
                                 # even when the move ends the game outright)
    capture: bool
    wins_immediately: bool      # opponent row emptied, or kazan >= 26


def legal_pits(pos: Position) -> list[int]:
    return [i for i in range(NUM_PITS) if pos.pits[i] > 0]


def apply_move(pos: Position, pit: int) -> Child:
    """Sow one pit and return the child ALREADY FLIPPED to the opponent's view."""
    pits = list(pos.pits)
    stones = pits[pit]
    if stones == 0:
        raise ValueError(f"pit {pit} is empty")

    pits[pit] = 0
    if stones == 1:
        last = (pit + 1) % 10
        pits[last] += 1
    else:
        pits[pit] = 1
        last = pit
        for _ in range(stones - 1):
            last = (last + 1) % 10
            pits[last] += 1

    captured = 0
    capture = False
    if last >= NUM_PITS and pits[last] % 2 == 0 and pits[last] > 0:
        captured, pits[last] = pits[last], 0
        capture = True

    mover_kazan = pos.k1 + captured
    opponent_starved = all(p == 0 for p in pits[NUM_PITS:])
    child = Position(
        k1=pos.k2,
        k2=mover_kazan,
        pits=tuple(pits[NUM_PITS:] + pits[:NUM_PITS]),
    )
    wins_immediately = opponent_starved or mover_kazan >= WIN_THRESHOLD
    return Child(pit=pit, land=last, position=child, capture=capture, wins_immediately=wins_immediately)


# ----------------------------------------------------------------- oracle

INVERSE: dict[Verdict, Verdict] = {
    "win": "loss", "loss": "win", "draw": "draw", "unknown": "unknown",
}


class Oracle:
    """Reads single bits out of the remote .bin layers via HTTP Range."""

    def __init__(self, base_url: str = BASE_URL, session: requests.Session | None = None):
        self.base_url = base_url
        self.session = session or requests.Session()
        self._headers: dict[str, list[int] | None] = {}
        self._blocks: dict[tuple[str, int], bytes] = {}

    def _range_get(self, url: str, start: int, end: int) -> bytes | None:
        resp = self.session.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content

    def offsets(self, url: str) -> list[int] | None:
        if url in self._headers:
            return self._headers[url]

        head = self._range_get(url, 0, 4095)
        if head is None:
            self._headers[url] = None
            return None

        num_blocks = int.from_bytes(head[:4], "little")
        need = 4 + 4 * (num_blocks + 1)
        if len(head) < need:
            head = self._range_get(url, 0, need - 1)

        table = [int.from_bytes(head[4 + 4 * i: 8 + 4 * i], "little")
                 for i in range(num_blocks + 1)]
        self._headers[url] = table
        return table

    def block(self, url: str, block_index: int) -> bytes:
        cached = self._blocks.get((url, block_index))
        if cached is not None:
            return cached

        table = self.offsets(url)
        if table is None or block_index + 1 >= len(table):
            return b""

        start, end = table[block_index], table[block_index + 1] - 1
        compressed = self._range_get(url, start, end) or b""
        data = zstandard.ZstdDecompressor().decompress(
            compressed, max_output_size=BYTES_PER_BLOCK)
        self._blocks[(url, block_index)] = data
        return data

    def locate(self, pos: Position) -> dict:
        """Resolve a position to its exact file + byte range without downloading."""
        rank = index_state(pos)
        loc = bit_location(rank)
        win_url, draw_url = layer_urls(pos, self.base_url)

        plan = {"rank": rank, "block_index": loc.block_index,
                "local_byte": loc.local_byte, "bit_offset": loc.bit_offset,
                "files": {}}
        for name, url in (("win", win_url), ("draw", draw_url)):
            table = self.offsets(url)
            if table is None:
                plan["files"][name] = {"url": url, "exists": False}
                continue
            plan["files"][name] = {
                "url": url,
                "exists": True,
                "byte_range": (table[loc.block_index],
                               table[loc.block_index + 1] - 1),
                "compressed_size": table[loc.block_index + 1] - table[loc.block_index],
            }
        return plan

    def value(self, pos: Position) -> Verdict:
        """Verdict from the SIDE TO MOVE's perspective."""
        if not pos.is_valid():
            return "unknown"

        rank = index_state(pos)
        loc = bit_location(rank)
        win_url, draw_url = layer_urls(pos, self.base_url)

        if self.offsets(draw_url) is None or self.offsets(win_url) is None:
            return self._derive(pos)

        def read_bit(url: str) -> int:
            data = self.block(url, loc.block_index)
            if loc.local_byte >= len(data):
                return 0
            return (data[loc.local_byte] >> loc.bit_offset) & 1

        if read_bit(draw_url):
            return "draw"
        return "win" if read_bit(win_url) else "loss"

    def children_values(self, pos: Position) -> list[dict]:
        """Evaluate all legal child moves."""
        out = []
        for pit in legal_pits(pos):
            child = apply_move(pos, pit)
            if child.wins_immediately:
                out.append({"pit": pit, "land": child.land, "position": child.position,
                            "capture": child.capture,
                            "value": "loss", "value_for_mover": "win",
                            "terminal": True})
                continue
            child_value = self.value(child.position)
            out.append({"pit": pit, "land": child.land, "position": child.position,
                        "capture": child.capture,
                        "value": child_value,
                        "value_for_mover": INVERSE[child_value],
                        "terminal": False})
        return out

    def _derive(self, pos: Position) -> Verdict:
        children = self.children_values(pos)
        if not children:
            return "loss"
        if any(c["value_for_mover"] == "win" for c in children):
            return "win"
        if any(c["value"] == "unknown" for c in children):
            return "unknown"
        return "draw" if any(c["value"] == "draw" for c in children) else "loss"


# --------------------------------------------------------------------------- #
# CLI


def parse_position(fields: list[str]) -> Position:
    """12 integers K1 K2 p0..p9 -> Position. Raises ValueError on bad input."""
    if len(fields) != 12:
        raise ValueError(f"expected 12 integers (K1 K2 p0..p9), got {len(fields)}")
    vals = [int(f) for f in fields]
    pos = Position(k1=vals[0], k2=vals[1], pits=tuple(vals[2:]))
    if not pos.is_valid():
        raise ValueError(
            f"invalid position: kazans must be even in 0..{MAX_KAZAN} and "
            f"K1 + K2 + sum(pits) must equal {TOTAL_STONES} "
            f"(got {vals[0]} + {vals[1]} + {sum(vals[2:])})")
    return pos


def format_position(pos: Position) -> str:
    own = " ".join(str(p) for p in pos.pits[:NUM_PITS])
    opp = " ".join(str(p) for p in pos.pits[NUM_PITS:])
    return f"K1={pos.k1:<2} [{own}] | [{opp}] K2={pos.k2}"


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(
        prog="tasks.oracle_client",
        description="Query the Bestemshe tablebase over HTTP Range (no download).")
    ap.add_argument("fields", nargs="*", metavar="N",
                    help="12 integers: K1 K2 p0..p9 (default: the start position)")
    ap.add_argument("--children", action="store_true",
                    help="also evaluate every legal move")
    ap.add_argument("--locate", action="store_true",
                    help="print the file + byte range for this position instead of querying")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    a = ap.parse_args(argv)

    fields = a.fields or ["0", "0"] + ["5"] * 10
    try:
        pos = parse_position(fields)
    except ValueError as e:
        ap.error(str(e))

    oracle = Oracle()

    if a.locate:
        plan = oracle.locate(pos)
        print(json.dumps(plan, indent=2))
        return 0

    verdict = oracle.value(pos)

    if a.json:
        out: dict = {"position": {"k1": pos.k1, "k2": pos.k2, "pits": list(pos.pits)},
                     "value": verdict}
        if a.children:
            out["moves"] = [
                {"pit": c["pit"], "cell": c["pit"] + 1,
                 "land_cell": (c["land"] % NUM_PITS) + 1,
                 "lands_on_opponent": c["land"] >= NUM_PITS,
                 "capture": c["capture"], "terminal": c["terminal"],
                 "value_for_mover": c["value_for_mover"]}
                for c in oracle.children_values(pos)]
        print(json.dumps(out, indent=2))
        return 0

    print(format_position(pos))
    print(verdict)

    if a.children:
        print()
        print(f"{'cell':>4}  {'lands':>12}  {'capture':>7}  {'value for mover':>15}")
        for c in oracle.children_values(pos):
            side = "opponent" if c["land"] >= NUM_PITS else "own"
            lands = f"{side} {(c['land'] % NUM_PITS) + 1}"
            note = " (terminal)" if c["terminal"] else ""
            print(f"{c['pit'] + 1:>4}  {lands:>12}  {str(c['capture']):>7}  "
                  f"{c['value_for_mover']:>15}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
