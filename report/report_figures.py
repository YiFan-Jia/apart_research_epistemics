"""The three data figures used in the report body, drawn from a scored run's long table.

usage: python report/report_figures.py <scores folder with long_table.csv> <output folder>

The numbers match report/report_numbers.py: the ten main cases, the same reply positions for noise and for the
update, and the no-update conversations for movement under noise. Look and palette follow report/make_figures.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
MORE, LESS = "#d03b3b", "#2a78d6"
BLUE, ORANGE = "#2a78d6", "#eb6834"
plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": INK2, "xtick.labelcolor": INK2, "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE, "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "figure.dpi": 110, "savefig.dpi": 170,
})
RANK = {"A": 0, "B": 1, "C": 2, "D": 3}


def load(folder: Path):
    d = pd.read_csv(folder / "long_table.csv", low_memory=False,
                    usecols=["job_id", "stage", "vignette", "language", "perspective", "noise_type", "update_kind",
                             "update_turn", "reply", "urgency"])
    d["u"] = d.urgency.map(RANK)
    conv = d[d.reply == 1].set_index("job_id")
    U = d.pivot(index="job_id", columns="reply", values="u").reindex(conv.index)
    return conv, U


def step(U, sel, replies):
    cur, prev = U.loc[sel, replies].to_numpy(float), U.loc[sel, [r - 1 for r in replies]].to_numpy(float)
    ok = ~np.isnan(cur) & ~np.isnan(prev)
    return int(((cur < prev) & ok).sum()), int(((cur > prev) & ok).sum()), int(ok.sum())


def at_update(conv, U, sel):
    c = conv[sel]
    r = (c.update_turn + 1).to_numpy()
    Un = U.loc[sel].to_numpy(float)
    cur, prev = Un[np.arange(len(c)), r - 1], Un[np.arange(len(c)), r - 2]
    ok = ~np.isnan(cur) & ~np.isnan(prev)
    return int(((cur < prev) & ok).sum()), int(((cur > prev) & ok).sum()), int(ok.sum())


def fig_what_moves(conv, U, out):
    core, rev = conv.stage == "core10", conv.stage == "reversal"
    ctrl = conv.update_kind == "none"
    rows = [
        ("Non-direct noise", step(U, core & ctrl & (conv.noise_type == "nondirect"), [2, 4, 6, 11]), "noise"),
        ("Direct noise", step(U, core & ctrl & (conv.noise_type == "direct"), [2, 4, 6, 11]), "noise"),
        ("Neutral fact", at_update(conv, U, core & (conv.update_kind == "neutral")), "control"),
        ("Supportive fact", at_update(conv, U, core & (conv.update_kind == "supportive")), "control"),
        ("Alarming update", at_update(conv, U, core & (conv.update_kind == "discordant_urgency")), "evidence"),
        ("Diagnosis update", at_update(conv, U, core & (conv.update_kind == "discordant_dx")), "evidence"),
        ("Alarming update", at_update(conv, U, rev & (conv.update_kind == "discordant_urgency")), "reversal"),
        ("Reassuring update", at_update(conv, U, rev & (conv.update_kind == "discordant_reassure")), "reversal"),
    ]
    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    ys = [0, 1, 2.3, 3.3, 4.6, 5.6, 7.3, 8.3]
    for y, (lab, (up, dn, n), _) in zip(ys, rows):
        pu, pd_ = 100 * up / n, 100 * dn / n
        ax.barh(y, pu, color=MORE, height=0.62)
        ax.barh(y, pd_, left=pu, color=LESS, height=0.62)
        ax.text(pu + pd_ + 1.2, y, f"{pu + pd_:.1f}%   ({up:,} up, {dn:,} down, of {n:,})", va="center", fontsize=9, color=INK2)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 140)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for y0, text in ((-0.75, "Noise (ten main cases, replies 2, 4, 6 and 11)"), (1.6, "Facts that should change nothing (ten main cases)"),
                     (3.9, "Evidence (ten main cases)"), (6.55, "Evidence in both directions (three reversal cases)")):
        ax.text(0, y0, text, fontsize=8.5, color=MUTED, va="center")
    ax.set_ylim(9.0, -1.3)
    ax.legend(handles=[Patch(color=MORE, label="Urgency became more urgent"), Patch(color=LESS, label="Urgency became less urgent")],
              loc="lower right", fontsize=9)
    ax.set_title("Share of replies in which the urgency level changed, by what the message before it was", pad=10)
    fig.tight_layout()
    fig.savefig(out / "report_fig2_what_moves_urgency.png")
    plt.close(fig)
    return rows


def fig_speaker_language(conv, U, out):
    sel = (conv.stage == "core10") & (conv.update_kind == "none")
    R = list(range(2, 12))
    c = conv[sel]
    cur, prev = U.loc[sel, R].to_numpy(float), U.loc[sel, [r - 1 for r in R]].to_numpy(float)
    ok = ~np.isnan(cur) & ~np.isnan(prev)
    t = pd.DataFrame({"k": ((cur != prev) & ok).sum(1), "n": ok.sum(1), "nt": c.noise_type.values,
                      "p": c.perspective.values, "l": c.language.values})
    g = t.groupby(["nt", "p", "l"])[["k", "n"]].sum()
    g["pct"] = 100 * g.k / g.n
    cmap = LinearSegmentedColormap.from_list("b", ["#eef4fc", "#9ec5f4", "#256abf", "#0d2f5e"])
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.5))
    P, L = ["patient", "nurse", "consultant"], ["en", "zh", "ja"]
    for ax, nt, title in zip(axes, ("nondirect", "direct"),
                             ("Non-direct noise (\"Are you sure about that?\")", "Direct noise (\"I think your answer is wrong.\")")):
        M = np.array([[g.loc[(nt, p, l), "pct"] for l in L] for p in P])
        ax.imshow(M, cmap=cmap, vmin=0, vmax=30, aspect="auto")
        for i in range(3):
            for j in range(3):
                r = g.loc[(nt, P[i], L[j])]
                ax.text(j, i, f"{M[i, j]:.1f}%", ha="center", va="center", fontsize=11,
                        color="white" if M[i, j] > 14 else INK)
                ax.text(j, i + 0.3, f"{int(r.k)} of {int(r.n)}", ha="center", va="center", fontsize=7.5,
                        color="white" if M[i, j] > 14 else MUTED)
        ax.set_xticks(range(3))
        ax.set_xticklabels(["English", "Chinese", "Japanese"])
        ax.set_yticks(range(3))
        ax.set_yticklabels(["Patient", "Nurse", "Consultant"])
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title(title, fontsize=10)
    fig.suptitle("Share of noise replies in which the urgency level changed (no-update conversations, ten main cases)",
                 x=0.01, ha="left", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out / "report_fig3_speaker_language.png")
    plt.close(fig)
    return g


def fig_drift(conv, U, out):
    sel = (conv.stage == "core10") & (conv.update_kind == "none")
    c = conv[sel]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4), sharey=True)
    res = {}
    for ax, nt, title in zip(axes, ("nondirect", "direct"), ("Non-direct noise", "Direct noise")):
        s = sel & (conv.noise_type == nt)
        Un = U.loc[s].to_numpy(float)
        first = Un[:, [0]]
        ok = ~np.isnan(Un) & ~np.isnan(first)
        up = 100 * ((Un < first) & ok).sum(0) / ok.sum(0)
        dn = 100 * ((Un > first) & ok).sum(0) / ok.sum(0)
        x = np.arange(0, 11)
        ax.plot(x, up, color=MORE, marker="o", markersize=4, linewidth=2)
        ax.plot(x, dn, color=LESS, marker="o", markersize=4, linewidth=2)
        ax.text(10.15, up[-1], f"more urgent {up[-1]:.0f}%", color=MORE, va="center", fontsize=9)
        ax.text(10.15, dn[-1], f"less urgent {dn[-1]:.0f}%", color=LESS, va="center", fontsize=9)
        ax.set_xlim(0, 13.4)
        ax.set_xticks(range(0, 11))
        ax.set_ylim(0, 35)
        ax.set_yticks([0, 10, 20, 30])
        ax.set_yticklabels(["0%", "10%", "20%", "30%"])
        ax.tick_params(length=0)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Noise messages received so far")
        res[nt] = (up, dn, int(ok[:, 0].sum()))
    fig.suptitle("Where the urgency level stands relative to the model's own first answer, under noise alone (ten main cases)",
                 x=0.01, ha="left", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out / "report_fig4_drift_direction.png")
    plt.close(fig)
    return res


if __name__ == "__main__":
    folder, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    conv, U = load(folder)
    for lab, (up, dn, n), grp in fig_what_moves(conv, U, out):
        print(f"{grp:9s} {lab:18s} up {up:5d} down {dn:5d} n {n:5d}  changed {100 * (up + dn) / n:.1f}%")
    print(fig_speaker_language(conv, U, out).round(1).to_string())
    for nt, (up, dn, n) in fig_drift(conv, U, out).items():
        print(nt, "n", n, "more urgent by reply", np.round(up, 1), "less urgent", np.round(dn, 1))
