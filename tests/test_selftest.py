"""Correctness of the state encoding — offline, no tablebase, no network.

Three independent things are checked:

1. The Python rank/unrank port agrees with the C++ solver's colexicographical
   ranking (StateIndex.h / Solver.h::IndexBoard), exhaustively for small stone
   counts and by round-trip over the full range.
2. The two Python ports of the move rules — training/bestemshe_core.py (written
   against Solver.h) and tasks/oracle_client.py (written against
   BestemsheCore.h) — produce identical children for random positions. They were
   written separately, so agreement is real evidence rather than a tautology.
3. The terminal rules match between the two ports.
"""
import random

import pytest

from tasks import oracle_client as oc
from training import bestemshe_core as core
from training.make_shards import selftest as rank_selftest

N_CROSS_CHECK = 2000


def test_rank_unrank_matches_solver():
    """Exhaustive bijection + round-trip against the C++ anchor values."""
    rank_selftest()          # asserts internally; raises on any mismatch


def test_rank_anchor_from_cpp():
    """The single anchor value computed by the C++ IndexBoard."""
    anchor = (0, 2, 0, 0, 0, 0, 0, 0, 0, 0)
    assert core.rank(anchor) == 52          # a lex rank would give 44
    assert core.unrank(52, 2) == list(anchor)


def _random_position(rng):
    """A valid position with a legal move, drawn without using either port."""
    while True:
        k1 = rng.randrange(0, 26, 2)
        k2 = rng.randrange(0, 26, 2)
        remaining = core.STONES - k1 - k2
        if remaining < 1:
            continue
        cuts = sorted(rng.randrange(remaining + 1) for _ in range(9))
        bounds = [0] + cuts + [remaining]
        pits = [bounds[i + 1] - bounds[i] for i in range(10)]
        if sum(pits[:5]) == 0:              # no legal move; skip
            continue
        return k1, k2, pits


def test_move_rules_agree_across_ports():
    """bestemshe_core.apply_move must equal oracle_client.apply_move.

    These are two independently written ports of the same C++ routine
    (ExecuteMoveAndFlip). Any divergence in sowing, capture parity, or the board
    flip shows up here.
    """
    rng = random.Random(12345)
    checked = 0
    for _ in range(N_CROSS_CHECK):
        k1, k2, pits = _random_position(rng)
        core_pos = (k1, k2, list(pits))
        oc_pos = oc.Position(k1=k1, k2=k2, pits=tuple(pits))

        assert core.legal_moves(core_pos) == oc.legal_pits(oc_pos)

        for m in core.legal_moves(core_pos):
            a_k1, a_k2, a_pits = core.apply_move(core_pos, m)
            child = oc.apply_move(oc_pos, m)
            assert (a_k1, a_k2, tuple(a_pits)) == \
                   (child.position.k1, child.position.k2, child.position.pits), \
                f"divergence at {core_pos} move {m}"
            checked += 1
    assert checked > 0


def test_stone_count_is_conserved():
    """Sowing and capturing must never create or destroy a stone."""
    rng = random.Random(999)
    for _ in range(N_CROSS_CHECK // 4):
        k1, k2, pits = _random_position(rng)
        pos = (k1, k2, list(pits))
        for m in core.legal_moves(pos):
            n_k1, n_k2, n_pits = core.apply_move(pos, m)
            assert n_k1 + n_k2 + sum(n_pits) == core.STONES


def test_terminal_rules_agree():
    """`is_terminal_loss` and the oracle client's immediate-win flag must agree."""
    rng = random.Random(4242)
    for _ in range(N_CROSS_CHECK // 4):
        k1, k2, pits = _random_position(rng)
        pos = (k1, k2, list(pits))
        oc_pos = oc.Position(k1=k1, k2=k2, pits=tuple(pits))
        for m in core.legal_moves(pos):
            child_core = core.apply_move(pos, m)
            child_oc = oc.apply_move(oc_pos, m)
            # The child is a loss for the side to move exactly when the mover
            # emptied the opponent's row or reached a winning kazan.
            assert core.is_terminal_loss(child_core) == child_oc.wins_immediately


@pytest.mark.parametrize("k1,k2", [(0, 0), (12, 12), (24, 24)])
def test_index_state_matches_rank(k1, k2):
    """oracle_client.index_state is the same function as bestemshe_core.rank."""
    rng = random.Random(k1 * 100 + k2)
    remaining = core.STONES - k1 - k2
    for _ in range(200):
        cuts = sorted(rng.randrange(remaining + 1) for _ in range(9))
        bounds = [0] + cuts + [remaining]
        pits = tuple(bounds[i + 1] - bounds[i] for i in range(10))
        assert oc.index_state(oc.Position(k1, k2, pits)) == core.rank(pits)
