"""latent_calibration.py — zero-training analytics for the Bestemshe ResMLP.

Two inference-only analyses over the same sample of positions:

  1. Latent space: the 1024-d activation of the final residual block, projected
     to 2-D with t-SNE and coloured by the Oracle's exact WDL label.
  2. Calibration: the value head's softmax confidence against Oracle truth,
     as a reliability diagram plus Expected Calibration Error.

Positions come from sample_symmetric() -- the same forced-symmetric OOD
distribution used for the 2,000-match benchmark -- so these numbers describe
the distribution the paper's degradation result was measured on.

Every position is also labelled "critical" or "forgiving": a position is
critical when the Oracle says some legal moves preserve the value and others
throw it away, and forgiving when every legal move is equivalent. This is the
decision-boundary split that the optimal-move-rate metric is blind to.

Run (pulls the checkpoint from the Hub and the Oracle over HTTP range reads):
    python analysis/latent_calibration.py --n 4000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "bestemshe-mpl"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from sklearn.manifold import TSNE

from evaluation.vs_god import sample_symmetric
from tasks.oracle_client import Oracle, Position
from training.infer import DEFAULT_REPO, load_model

CLASSES = ("loss", "draw", "win")          # value-head index order: 0, 1, 2
CLASS_COLOR = {"loss": "#d62728", "draw": "#7f7f7f", "win": "#1f77b4"}
FIG_DIR = os.path.join(ROOT, "figures")

plt.rcParams.update(
    {
        "font.size": 9,
        "font.family": "serif",
        "axes.labelsize": 10,
        "legend.fontsize": 8,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
    }
)


# --------------------------------------------------------------- data gathering

def label_position(oracle, pos_tuple):
    """Oracle truth for one position.

    Returns (value_index, is_critical) or None if the Oracle cannot resolve it.
    `is_critical` means the legal moves do NOT all share the same outcome, i.e.
    the mover can actually throw the position away here.
    """
    k1, k2, pits = pos_tuple
    pos = Position(k1=k1, k2=k2, pits=tuple(pits))

    verdict = oracle.value(pos)
    if verdict == "unknown":
        return None

    child_vals = {c["value_for_mover"] for c in oracle.children_values(pos)}
    if not child_vals or "unknown" in child_vals:
        return None

    return CLASSES.index(verdict), len(child_vals) > 1


def collect(n, seed, model_source, workers, cache_path=None):
    """Sample n positions, label them with the Oracle, embed them with the net.

    The Oracle pass is ~30 minutes of HTTP range reads, so results are cached to
    an .npz keyed by (n, seed); delete the file to force a refetch.
    """
    if cache_path and os.path.exists(cache_path):
        z = np.load(cache_path, allow_pickle=True)
        if int(z["n_requested"]) == n and int(z["seed"]) == seed:
            print(f"reusing cached Oracle labels from {cache_path}")
            return {k: z[k] for k in ("embeddings", "probs", "y_true", "critical")} | {
                "step": int(z["step"])
            }
        print(f"cache {cache_path} has different (n, seed) -- refetching")

    rng = np.random.default_rng(seed)
    oracle = Oracle()

    # Oversample: some draws are duplicates or Oracle-unresolvable.
    raw, seen = [], set()
    while len(raw) < n:
        k1, k2, pits = sample_symmetric(rng)
        key = (k1, k2, tuple(pits))
        if key not in seen:
            seen.add(key)
            raw.append((k1, k2, list(pits)))

    print(f"labelling {len(raw)} positions via the Oracle ({workers} threads)...")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        labels = list(pool.map(lambda p: label_position(oracle, p), raw))
    print(f"  oracle pass done in {time.time() - t0:.1f}s")

    kept = [(p, lab) for p, lab in zip(raw, labels) if lab is not None]
    dropped = len(raw) - len(kept)
    if dropped:
        print(f"  dropped {dropped} unresolvable positions")

    positions = [p for p, _ in kept]
    y_true = np.array([lab[0] for _, lab in kept], dtype=np.int64)
    critical = np.array([lab[1] for _, lab in kept], dtype=bool)

    model, step = load_model(model_source)
    print(f"loaded checkpoint step={step}")

    # The paper's "final residual block" activation is the input to both heads,
    # so hook model.body rather than re-deriving it.
    captured = {}
    handle = model.body.register_forward_hook(
        lambda _m, _i, out: captured.__setitem__("h", out.detach())
    )

    pits_t = torch.tensor([p[2] for p in positions], dtype=torch.long)
    kaz_t = torch.tensor([[p[0] // 2, p[1] // 2] for p in positions], dtype=torch.long)

    embeddings, probs = [], []
    with torch.no_grad():
        for i in range(0, len(positions), 1024):
            value_logits, _ = model(pits_t[i:i + 1024], kaz_t[i:i + 1024])
            embeddings.append(captured["h"].clone().numpy())
            probs.append(torch.softmax(value_logits, dim=1).numpy())
    handle.remove()

    out = {
        "embeddings": np.concatenate(embeddings),
        "probs": np.concatenate(probs),
        "y_true": y_true,
        "critical": critical,
        "step": step,
    }
    if cache_path:
        np.savez_compressed(cache_path, n_requested=n, seed=seed, **out)
        print(f"cached Oracle labels + embeddings to {cache_path}")
    return out


# ------------------------------------------------------- latent diagnostics

def neighbourhood_heterogeneity(emb, y_true, k=20):
    """For each state, the fraction of its k nearest latent neighbours carrying a
    different Oracle label. High values mark states sitting on a WDL decision
    boundary in representation space."""
    from sklearn.neighbors import NearestNeighbors

    nn = NearestNeighbors(n_neighbors=k + 1).fit(emb)
    _, idx = nn.kneighbors(emb)
    neigh = y_true[idx[:, 1:]]                      # drop self
    return (neigh != y_true[:, None]).mean(axis=1)


# ------------------------------------------------------------------ calibration

def expected_calibration_error(conf, correct, n_bins=15):
    """Standard equal-width binning ECE, plus the per-bin table for plotting."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece, rows = 0.0, []
    for lo, hi in zip(edges[:-1], edges[1:]):
        # Include the left edge on the first bin so conf == 0 is never dropped.
        in_bin = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        count = int(in_bin.sum())
        if count == 0:
            rows.append((lo, hi, 0, np.nan, np.nan))
            continue
        acc = float(correct[in_bin].mean())
        avg_conf = float(conf[in_bin].mean())
        ece += (count / len(conf)) * abs(acc - avg_conf)
        rows.append((lo, hi, count, acc, avg_conf))
    return ece, rows


def plot_reliability(rows, ece, conf, correct, out_path):
    fig, (ax, ax_hist) = plt.subplots(
        2, 1, figsize=(5.5, 4.4), sharex=True, constrained_layout=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    ax.plot([0, 1], [0, 1], color="black", linestyle="--", linewidth=1.0,
            label="Perfect calibration")

    centers = [(lo + hi) / 2 for lo, hi, _, _, _ in rows]
    accs = [acc for _, _, _, acc, _ in rows]
    widths = (rows[0][1] - rows[0][0]) * 0.9

    ax.bar(centers, accs, width=widths, color="#1f77b4", alpha=0.85,
           edgecolor="black", linewidth=0.5, label="Observed accuracy")
    for c, (_, _, count, acc, avg_conf) in zip(centers, rows):
        if count and not np.isnan(acc):
            ax.plot([c, c], [acc, avg_conf], color="#d62728", linewidth=1.6,
                    solid_capstyle="butt", zorder=4)

    ax.plot([], [], color="#d62728", linewidth=1.6, label="Calibration gap")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Oracle-verified accuracy")
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.legend(loc="upper left")
    ax.text(0.98, 0.05, f"ECE = {ece:.4f}\nMean confidence = {conf.mean():.4f}\n"
                        f"Accuracy = {correct.mean():.4f}",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                      edgecolor="0.7"))

    ax_hist.hist(conf, bins=np.linspace(0, 1, 16), color="0.55",
                 edgecolor="black", linewidth=0.5)
    ax_hist.set_yscale("log")
    ax_hist.set_xlabel("Value-head confidence (max softmax)")
    ax_hist.set_ylabel("Count")
    ax_hist.grid(True, linestyle=":", alpha=0.5)

    fig.savefig(out_path, format="pdf", dpi=300)
    print(f"wrote {out_path}")


# -------------------------------------------------------------------- latent map

def plot_tsne(emb, y_true, y_pred, critical, out_path, seed):
    print(f"running t-SNE on {emb.shape[0]} x {emb.shape[1]} embeddings...")
    t0 = time.time()
    xy = TSNE(n_components=2, perplexity=30, init="pca", learning_rate="auto",
              random_state=seed).fit_transform(emb.astype(np.float32))
    print(f"  t-SNE done in {time.time() - t0:.1f}s")

    fig, axes = plt.subplots(1, 2, figsize=(5.5, 2.9))

    for cls_idx, name in enumerate(CLASSES):
        m = y_true == cls_idx
        axes[0].scatter(xy[m, 0], xy[m, 1], s=3, alpha=0.55,
                        color=CLASS_COLOR[name], linewidths=0, label=name.capitalize())
    axes[0].set_title("Oracle ground truth", fontsize=9)
    axes[0].legend(loc="best", markerscale=3, framealpha=0.9)

    wrong = y_pred != y_true
    axes[1].scatter(xy[~wrong, 0], xy[~wrong, 1], s=3, alpha=0.30, color="0.75",
                    linewidths=0, label="Correct")
    axes[1].scatter(xy[wrong & ~critical, 0], xy[wrong & ~critical, 1], s=9,
                    color="#ff7f0e", linewidths=0, label="Error (forgiving)")
    axes[1].scatter(xy[wrong & critical, 0], xy[wrong & critical, 1], s=9,
                    color="#d62728", marker="x", linewidths=0.8,
                    label="Error (critical)")
    axes[1].set_title("Value-head misclassifications", fontsize=9)
    axes[1].legend(loc="best", markerscale=2, framealpha=0.9)

    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlabel("t-SNE 1")
        ax.set_ylabel("t-SNE 2")

    fig.tight_layout()
    fig.savefig(out_path, format="pdf", dpi=300)
    print(f"wrote {out_path}")
    return xy


# -------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4000, help="positions to sample")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--model", default=DEFAULT_REPO,
                    help="local checkpoint path or Hugging Face repo id")
    ap.add_argument("--workers", type=int, default=16,
                    help="parallel Oracle HTTP range requests")
    ap.add_argument("--bins", type=int, default=15)
    ap.add_argument("--out", default=os.path.join(ROOT, "analysis",
                                                  "latent_calibration.json"))
    ap.add_argument("--cache", default=os.path.join(ROOT, "analysis",
                                                    "latent_calibration_cache.npz"))
    a = ap.parse_args()

    os.makedirs(FIG_DIR, exist_ok=True)
    data = collect(a.n, a.seed, a.model, a.workers, a.cache)

    emb, probs = data["embeddings"], data["probs"]
    y_true, critical = data["y_true"], data["critical"]
    y_pred = probs.argmax(axis=1)
    conf = probs.max(axis=1)
    correct = (y_pred == y_true)

    ece, rows = expected_calibration_error(conf, correct, a.bins)
    plot_reliability(rows, ece, conf, correct,
                     os.path.join(FIG_DIR, "calibration.pdf"))
    plot_tsne(emb, y_true, y_pred, critical,
              os.path.join(FIG_DIR, "latent_tsne.pdf"), a.seed)

    def subset(mask):
        if mask.sum() == 0:
            return None
        sub_ece, _ = expected_calibration_error(conf[mask], correct[mask], a.bins)
        return {
            "n": int(mask.sum()),
            "accuracy": float(correct[mask].mean()),
            "mean_confidence": float(conf[mask].mean()),
            "ece": float(sub_ece),
        }

    # Does the value head ever commit to "draw", and where does draw mass go?
    p_draw = probs[:, 1]
    draw_rank = (probs > p_draw[:, None]).sum(axis=1)   # 0 = draw is argmax
    is_draw = y_true == 1

    # Are errors concentrated where the latent neighbourhood is label-mixed?
    het = neighbourhood_heterogeneity(emb, y_true)
    order = np.argsort(het)
    deciles = np.array_split(order, 10)

    summary = {
        "checkpoint_step": int(data["step"]),
        "n_positions": int(len(y_true)),
        "n_bins": a.bins,
        "seed": a.seed,
        "accuracy": float(correct.mean()),
        "mean_confidence": float(conf.mean()),
        "ece": float(ece),
        "overconfidence": float(conf.mean() - correct.mean()),
        "mean_confidence_when_wrong": float(conf[~correct].mean()) if (~correct).any() else None,
        "mean_confidence_when_right": float(conf[correct].mean()) if correct.any() else None,
        "frac_errors_above_0.99_confidence": (
            float((conf[~correct] > 0.99).mean()) if (~correct).any() else None
        ),
        "critical": subset(critical),
        "forgiving": subset(~critical),
        "true_class_distribution": {
            name: int((y_true == i).sum()) for i, name in enumerate(CLASSES)
        },
        "confusion_true_by_pred": [
            [int(((y_true == t) & (y_pred == p)).sum()) for p in range(3)]
            for t in range(3)
        ],
        "draw_head": {
            "n_true_draws": int(is_draw.sum()),
            "n_predicted_draw": int((y_pred == 1).sum()),
            "max_p_draw_anywhere": float(p_draw.max()),
            "mean_p_draw_all": float(p_draw.mean()),
            "mean_p_draw_on_true_draws": float(p_draw[is_draw].mean()) if is_draw.any() else None,
            "draw_is_second_choice_rate": float((draw_rank == 1).mean()),
            "draw_is_second_choice_rate_on_true_draws": (
                float((draw_rank[is_draw] == 1).mean()) if is_draw.any() else None
            ),
            "recall_draw": 0.0 if is_draw.any() else None,
        },
        "latent_boundary": {
            "knn_k": 20,
            "mean_heterogeneity": float(het.mean()),
            "error_rate_by_heterogeneity_decile": [
                float((~correct[d]).mean()) for d in deciles
            ],
            "mean_heterogeneity_when_wrong": float(het[~correct].mean()),
            "mean_heterogeneity_when_right": float(het[correct].mean()),
        },
    }

    with open(a.out, "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
