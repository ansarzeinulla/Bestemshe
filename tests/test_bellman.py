"""Game-theoretic consistency of the tablebase: V(s) = max_m (2 - V(apply(s, m))).

If the retrograde solver, the state indexing, or either Python port of the move
rules were wrong, this identity would break somewhere. It is the strongest
correctness statement available short of re-solving the game.

Two backends:

  * online (default) — queries the published tablebase over HTTP Range via
    tasks/oracle_client.py. Needs a network connection but no local data.
    Deselect with `-m "not online"`.
  * local — set BESTEMSHE_DATA_DIR to a directory of layer_<K1>_<K2>_*.bin files
    and the local-tablebase tests run too, at a much larger sample size.

Sample sizes are tuned so the online tests stay under a minute: each lookup is
an HTTPS range request, though the per-block cache makes positions from an
already-touched layer nearly free.
"""
import os
import random

import pytest

from tasks import oracle_client as oc

DATA_DIR = os.environ.get("BESTEMSHE_DATA_DIR")

ONLINE_SAMPLES = int(os.environ.get("BESTEMSHE_ONLINE_SAMPLES", "25"))
LOCAL_SAMPLES = int(os.environ.get("BESTEMSHE_LOCAL_SAMPLES", "2000"))

# The oracle client speaks verdict strings; the numeric scale is
# 0 = loss, 1 = draw, 2 = win, so that the identity reads V = max(2 - V_child).
SCORE = {"loss": 0, "draw": 1, "win": 2}


def _sampled_positions(k1, k2, n, seed):
    """Uniform random compositions of the remaining stones over the 10 pits."""
    rng = random.Random(seed)
    remaining = oc.TOTAL_STONES - k1 - k2
    out = []
    while len(out) < n:
        cuts = sorted(rng.randrange(remaining + 1) for _ in range(9))
        bounds = [0] + cuts + [remaining]
        pits = tuple(bounds[i + 1] - bounds[i] for i in range(10))
        pos = oc.Position(k1=k1, k2=k2, pits=pits)
        if pos.is_valid() and oc.legal_pits(pos):
            out.append(pos)
    return out


# --------------------------------------------------------------- online


@pytest.fixture(scope="module")
def oracle():
    return oc.Oracle()


@pytest.mark.online
def test_start_position_is_a_loss_for_the_first_player(oracle):
    """The headline result of the whole project, checked against live data.

    The starting position (both kazans empty, 5 stones in every pit) is a LOSS
    for the side to move — Bestemshe is a forced win for the second player.
    """
    start = oc.Position(k1=0, k2=0, pits=(5,) * 10)
    assert oracle.value(start) == "loss"


@pytest.mark.online
def test_every_opening_move_loses(oracle):
    """A corollary: with the root lost, no first move can save the first player."""
    start = oc.Position(k1=0, k2=0, pits=(5,) * 10)
    children = oracle.children_values(start)
    assert len(children) == 5
    assert all(c["value_for_mover"] == "loss" for c in children)


@pytest.mark.online
@pytest.mark.parametrize("k1,k2", [(16, 16), (20, 20)])
def test_bellman_identity_online(oracle, k1, k2):
    """V(s) == max over legal moves of (2 - V(child)), on live tablebase data.

    Layers with high kazans are chosen deliberately: their bitsets fit in a
    single 4 MiB block, so the whole sample is served from one cached fetch.
    """
    checked = 0
    for pos in _sampled_positions(k1, k2, ONLINE_SAMPLES, seed=k1 * 31 + k2):
        value = oracle.value(pos)
        if value == "unknown":
            continue
        best = None
        for c in oracle.children_values(pos):
            score = 2 if c["terminal"] else 2 - SCORE[c["value"]]
            best = score if best is None else max(best, score)
        assert best is not None
        assert SCORE[value] == best, (
            f"Bellman violation at K1={k1} K2={k2} pits={pos.pits}: "
            f"stored {value}, children imply {best}")
        checked += 1
    assert checked > 0, "no position was actually checked"


# ---------------------------------------------------------------- local


needs_local = pytest.mark.skipif(
    not DATA_DIR,
    reason="set BESTEMSHE_DATA_DIR to a directory of layer_*.bin files "
           "to run the full-size local checks")


@needs_local
def test_bellman_identity_local():
    """The same identity at full sample size against a local tablebase."""
    from training.bestemshe_core import Tablebase, verify_consistency
    assert verify_consistency(Tablebase(DATA_DIR), n=LOCAL_SAMPLES), \
        "the tablebase is not game-theoretically consistent"


@needs_local
def test_local_and_online_agree():
    """The local reader and the HTTP client must return the same verdicts."""
    from training.bestemshe_core import Tablebase
    tb = Tablebase(DATA_DIR)
    oracle = oc.Oracle()
    names = {0: "loss", 1: "draw", 2: "win"}
    for pos in _sampled_positions(16, 16, 50, seed=7):
        local = names[tb.value((pos.k1, pos.k2, list(pos.pits)))]
        assert local == oracle.value(pos), f"disagreement at {pos}"
