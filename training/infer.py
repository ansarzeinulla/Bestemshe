"""infer.py — standalone single-position inference for the Bestemshe ResMLP
(no repo imports, no ply search).

Requires: torch, plus huggingface_hub to load straight from the Hub.
  pip install torch huggingface_hub

Usage:
  python -m training.infer                                   # pulls the Hub model
  python -m training.infer --model /path/to/latest.pt        # local checkpoint
  python -m training.infer --pits 5,5,5,5,5,5,5,5,5,5 --k1 0 --k2 0
"""
import argparse
import os
import torch
import torch.nn as nn
import torch.nn.functional as F


class ResBlock(nn.Module):
    def __init__(self, w):
        super().__init__()
        self.norm = nn.LayerNorm(w)
        self.fc1 = nn.Linear(w, w)
        self.fc2 = nn.Linear(w, w)

    def forward(self, x):
        return x + self.fc2(F.gelu(self.fc1(self.norm(x))))


class BestemsheNet(nn.Module):
    """embeddings -> residual MLP -> value head (loss/draw/win) + policy head (5 moves)."""

    def __init__(self, width=1024, blocks=8, emb=32):
        super().__init__()
        self.pit_emb = nn.Embedding(51, emb)   # stones per pit: 0..50
        self.kaz_emb = nn.Embedding(13, emb)   # kazan // 2: 0..12
        self.inp = nn.Linear(12 * emb, width)
        self.body = nn.Sequential(*[ResBlock(width) for _ in range(blocks)])
        self.value_head = nn.Linear(width, 3)
        self.policy_head = nn.Linear(width, 5)

    def forward(self, pits, kaz):
        x = torch.cat([self.pit_emb(pits).flatten(1),
                       self.kaz_emb(kaz).flatten(1)], dim=1)
        h = self.body(F.gelu(self.inp(x)))
        return self.value_head(h), self.policy_head(h)


DEFAULT_REPO = "ansarzeinulla/bestemshe-resmlp"


def load_model(source=DEFAULT_REPO, device="cpu", filename="latest.pt"):
    """Load a checkpoint from a local path or a Hugging Face repo id.

    `source` is treated as a local file when it exists on disk, otherwise as a
    Hub repo id (e.g. "ansarzeinulla/bestemshe-resmlp"). Returns (model, step).
    """
    if os.path.exists(source):
        path = source
    else:
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(repo_id=source, filename=filename)
    ckpt = torch.load(path, map_location="cpu")
    args = ckpt["args"]
    model = BestemsheNet(args["width"], args["blocks"]).to(device).eval()
    state_dict = {k.replace("_orig_mod.", ""): v for k, v in ckpt["model"].items()}
    model.load_state_dict(state_dict)
    return model, ckpt.get("step", 0)


@torch.no_grad()
def evaluate_position(model, pits, kazan_self, kazan_opp, device="cpu"):
    """
    pits: list of 10 ints — stones in each pit (0..4 = own side, 5..9 = opponent's)
    kazan_self, kazan_opp: int — each player's kazan (captured stones), 0..24 (even)

    Returns WDL probabilities for the side to move + raw 5-way move-policy logits
    (index 0..4, own pits only) and the argmax policy move as a 1..5 cell number.
    """
    pits_t = torch.tensor([pits], dtype=torch.long, device=device)
    kaz_t = torch.tensor([[kazan_self // 2, kazan_opp // 2]], dtype=torch.long, device=device)

    value_logits, policy_logits = model(pits_t, kaz_t)
    probs = torch.softmax(value_logits[0], dim=0).cpu().numpy()

    return {
        "p_loss": float(probs[0]),
        "p_draw": float(probs[1]),
        "p_win": float(probs[2]),
        "predicted_class": int(value_logits[0].argmax()),  # 0=loss 1=draw 2=win
        "policy_logits": policy_logits[0].cpu().numpy().tolist(),
        "best_move": int(policy_logits[0].argmax()) + 1,   # own cell, 1..5
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_REPO,
                    help="local checkpoint path or a Hugging Face repo id")
    ap.add_argument("--pits", default="5,5,5,5,5,5,5,5,5,5",
                    help="10 comma-separated pit counts (0..4 = mover, 5..9 = opponent)")
    ap.add_argument("--k1", type=int, default=0, help="mover's kazan (even, 0..24)")
    ap.add_argument("--k2", type=int, default=0, help="opponent's kazan (even, 0..24)")
    a = ap.parse_args()

    pits = [int(x) for x in a.pits.split(",")]
    if len(pits) != 10:
        ap.error(f"--pits needs exactly 10 values, got {len(pits)}")
    if sum(pits) + a.k1 + a.k2 != 50:
        ap.error(f"stones must total 50, got {sum(pits) + a.k1 + a.k2}")

    model, step = load_model(a.model)
    print(f"loaded checkpoint step={step}")

    r = evaluate_position(model, pits=pits, kazan_self=a.k1, kazan_opp=a.k2)
    print(f"position   : K1={a.k1} K2={a.k2} pits={pits}")
    print(f"WDL (mover): loss={r['p_loss']:.4f} draw={r['p_draw']:.4f} win={r['p_win']:.4f}")
    print(f"predicted  : {['loss', 'draw', 'win'][r['predicted_class']]}")
    print(f"best move  : cell {r['best_move']}")


if __name__ == "__main__":
    main()
