#!/usr/bin/env python3
"""Generate the two data figures for the Beamer deck (slides 2 and 3).

Colors are the validated dark-surface categorical palette (see dataviz
validator: all six checks PASS against metropolis dark surface #23373B).
Backgrounds are transparent so the slide surface shows through.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

BLUE, ORANGE, GREEN = "#3F8FCC", "#C2761B", "#269966"
INK, MUTED = "#EAEAEA", "#9BA7A9"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": INK,
    "axes.edgecolor": MUTED,
    "savefig.transparent": True,
})


def ssc_comparison(path):
    """Slide 2 — state-space complexity across the mancala/solving frontier."""
    rows = [
        ("Awari\n(Romein & Bal, 2002)",   12.0, BLUE,   "Strongly solved"),
        ("Bestemshe\n(this work)",        12.0, GREEN,  "Strongly solved (this work)"),
        ("Checkers\n(Schaeffer, 2007)",   20.7, BLUE,   "Strongly solved"),
        ("Togyzkumalak\n(this work)",     25.2, ORANGE, "Mapped, unsolved"),
    ]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ys = range(len(rows))
    for y, (label, val, color, _) in zip(ys, rows):
        ax.barh(y, val, height=0.55, color=color, zorder=3)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([r[0] for r in rows], fontsize=10)

    notes = [r"$10^{12}$", r"$10^{12}$", r"$5\times10^{20}$", r"$1.51\times10^{25}$"]
    for y, (_, val, _, _), note in zip(ys, rows, notes):
        ax.text(val + 0.4, y, note, va="center", ha="left", fontsize=11, color=INK)

    ax.set_xlim(0, 30)
    ax.set_xlabel(r"State-space complexity, $\log_{10}$ (positions)")
    ax.xaxis.set_major_locator(MultipleLocator(5))
    ax.grid(axis="x", color=MUTED, alpha=0.25, lw=0.6, zorder=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(length=0)
    ax.invert_yaxis()

    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (BLUE, GREEN, ORANGE)]
    ax.legend(handles, ["Strongly solved (prior work)", "Strongly solved (this work)",
                        "Mapped, unsolved (this work)"],
              loc="upper right", frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(path, transparent=True)
    plt.close(fig)


def ssc_funnel(path):
    """Slide 3 — successive structural reductions of the Togyzkumalak bound."""
    stages = [
        ("Naive stars-and-bars", 7.94, "#BDD9EF"),
        ("+ active kazan limits", 6.18, "#8FBEE2"),
        ("+ kazan parity", 3.02, "#5FA3D4"),
        ("+ rotational quotient", 1.51, "#3F8FCC"),
    ]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ys = range(len(stages))
    for y, (label, val, color) in zip(ys, stages):
        ax.barh(y, val, height=0.6, color=color, zorder=3)
        ax.text(val + 0.15, y, rf"${val}\times10^{{25}}$", va="center",
                ha="left", fontsize=11, color=INK)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([s[0] for s in stages], fontsize=10)
    ax.set_xlim(0, 9.6)
    ax.set_xlabel(r"Configurations ($\times 10^{25}$)")
    ax.grid(axis="x", color=MUTED, alpha=0.25, lw=0.6, zorder=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(length=0)
    ax.invert_yaxis()
    ax.text(9.4, 3, r"$5.3\times$ total reduction", va="center", ha="right",
            fontsize=10, color=MUTED)
    fig.tight_layout()
    fig.savefig(path, transparent=True)
    plt.close(fig)


if __name__ == "__main__":
    ssc_comparison("ssc_comparison.pdf")
    ssc_funnel("ssc_funnel.pdf")
    print("wrote ssc_comparison.pdf, ssc_funnel.pdf")
