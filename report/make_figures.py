"""Figures for "Noise versus evidence in triage conversations", drawn from a scored run.

usage: python report/make_figures.py <scores folder with long_table.csv> <output folder> ["status line"]

Writes fig01_*.png ... and index.html (all figures with captions, self-contained) to the output folder.
Every figure reads the scorer's long table (one row per reply). Urgency figures use every reply; diagnosis
figures use the replies whose diagnosis has been read (see docs/14, "Judging the diagnoses").
"""
from __future__ import annotations

import base64
import html
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch  # noqa: E402

# ---------------------------------------------------------------- look (reference palette, light surface)
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6"
NEUTRAL = "#d9d8d2"                                    # the "nothing changed" middle of a diverging pair
MORE, LESS = "#d03b3b", "#2a78d6"                      # diverging poles: more urgent (warm), less urgent (cool)
LEVELS = {"A": "#104281", "B": "#256abf", "C": "#5598e7", "D": "#9ec5f4", "?": "#d9d8d2"}   # one hue, A darkest
NOISE_COL = {"nondirect": BLUE, "direct": ORANGE}
NOISE_LAB = {"nondirect": "Non-direct noise", "direct": "Direct noise"}
LANG_LAB = {"en": "English", "zh": "Chinese", "ja": "Japanese"}
PERS_LAB = {"patient": "Patient", "nurse": "Nurse", "consultant": "Doctor"}
KIND_LAB = {"noise_nondirect": "Non-direct noise", "noise_direct": "Direct noise", "neutral": "Neutral fact",
            "supportive": "Supportive fact", "discordant_urgency": "Alarming update",
            "discordant_reassure": "Reassuring update", "discordant_dx": "Diagnosis update"}
KIND_ORDER = list(KIND_LAB)
FAMILY_COL = {"noise_nondirect": ORANGE, "noise_direct": ORANGE, "neutral": MUTED, "supportive": MUTED,
              "discordant_urgency": BLUE, "discordant_reassure": BLUE, "discordant_dx": BLUE}

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": INK2, "xtick.labelcolor": INK2, "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": False, "legend.frameon": False, "figure.dpi": 110, "savefig.dpi": 170,
})
FIGS: list[tuple[str, str, str, str]] = []            # file, section, title, caption


def pct(x):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100 * x:.0f}%"


def clean(ax, grid="x"):
    ax.tick_params(length=0)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)


def pct_axis(ax, axis="x", top=1.0):
    ticks = np.arange(0, top + 0.001, 0.25 if top > 0.5 else 0.05)
    if axis == "x":
        ax.set_xlim(0, top); ax.set_xticks(ticks); ax.set_xticklabels([f"{100 * t:.0f}%" for t in ticks])
    else:
        ax.set_ylim(0, top); ax.set_yticks(ticks); ax.set_yticklabels([f"{100 * t:.0f}%" for t in ticks])


def save(fig, name, section, title, caption):
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)
    FIGS.append((name, section, title, caption))
    print("wrote", name)


def stacked_direction(ax, rows, labels, ns):
    """rows: list of (less, same, more) shares. Horizontal 100% bars, less | same | more."""
    y = np.arange(len(rows))[::-1]
    for i, (less, same, more) in enumerate(rows):
        left = 0
        for val, col, txt in ((less, LESS, "white"), (same, NEUTRAL, INK2), (more, MORE, "white")):
            ax.barh(y[i], val, left=left, color=col, height=0.62, edgecolor=SURFACE, linewidth=1.5)
            if val >= 0.06:
                ax.text(left + val / 2, y[i], pct(val), ha="center", va="center", color=txt, fontsize=9)
            left += val
    ax.set_yticks(y); ax.set_yticklabels([f"{lab}\n(n = {n:,})" if n is not None else lab for lab, n in zip(labels, ns)])
    pct_axis(ax, "x"); clean(ax, grid=None)
    ax.spines["left"].set_visible(False)


def direction_legend(fig_or_ax, **kw):
    hs = [Patch(color=LESS, label="Less urgent"), Patch(color=NEUTRAL, label="Unchanged"), Patch(color=MORE, label="More urgent")]
    return fig_or_ax.legend(handles=hs, ncol=3, **kw)


def end_labels(ax, x, items, gap):
    """Value labels at the right-hand end of each line, pushed apart so they never overlap. items: (y, text)."""
    items = sorted(items, key=lambda t: t[0])
    ys = [t[0] for t in items]
    for k in range(1, len(ys)):
        if ys[k] - ys[k - 1] < gap:
            mid = (ys[k] + ys[k - 1]) / 2
            ys[k - 1], ys[k] = mid - gap / 2, mid + gap / 2
    for (y0, text), yy in zip(items, ys):
        ax.text(x, yy, text, color=INK2, fontsize=8.5, va="center")


def short(name, n=30):
    name = str(name)
    return name if len(name) <= n else name[:n - 1].rstrip() + "…"


def shares(g):
    n = len(g)
    d = g.urgency_direction
    return ((d == "less_urgent").sum() / n, (d == "same").sum() / n, (d == "more_urgent").sum() / n) if n else (0, 0, 0)


# ---------------------------------------------------------------- data
SCORES, OUT = Path(sys.argv[1]), Path(sys.argv[2])
STATUS = sys.argv[3] if len(sys.argv) > 3 else ""
OUT.mkdir(parents=True, exist_ok=True)
lt = pd.read_csv(SCORES / "long_table.csv", low_memory=False)
lt["kind"] = np.where(lt.turn_kind == "noise", "noise_" + lt.noise_type.astype(str), lt.turn_kind)
lt = lt.sort_values(["job_id", "reply"])
# reply index of the update in each conversation (none in the control arm)
upd_reply = lt[lt.turn_kind.isin(["neutral", "supportive", "discordant_urgency", "discordant_reassure", "discordant_dx",
                                  "discordant"])].groupby("job_id").reply.first()
lt["upd_reply"] = lt.job_id.map(upd_reply)
first = lt[lt.reply == 1].set_index("job_id")
lt["u1"] = lt.job_id.map(first.urgency)
lt["d1"] = lt.job_id.map(first.dx_leading)
n_conv, n_rep = lt.job_id.nunique(), len(lt)
judged = lt.dx_leading.notna()
blocks = lt.groupby("stage").agg(conversations=("job_id", "nunique"), repeats=("repeat", "nunique"), vignettes=("vignette", "nunique"))
changed = lt[lt.reply > 1].copy()
changed["u_changed"] = changed.urgency_direction.isin(["more_urgent", "less_urgent"])
SEC1, SEC2, SEC3, SEC4, SEC5 = ("The design", "Noise versus evidence", "Timing and persistence",
                                "Who is speaking, and in which language", "Vignette by vignette")

# ---------------------------------------------------------------- fig 1: the design
fig, ax = plt.subplots(figsize=(10.5, 4.3))
ax.set_xlim(-0.6, 12.2); ax.set_ylim(-1.6, 5.4); ax.axis("off")
rows_d = [("Update after reply 1", 1), ("Update after reply 3", 3), ("Update after reply 5", 5), ("Update after reply 10", 10),
          ("Control: noise only", None)]
for r, (lab, t) in enumerate(rows_d):
    y = 4.4 - r
    ax.text(-0.5, y, lab, ha="left", va="center", fontsize=9.5, color=INK2)
    ax.add_patch(FancyBboxPatch((2.05, y - 0.3), 0.8, 0.6, boxstyle="round,pad=0.02,rounding_size=0.08", fc=INK2, ec="none"))
    for k in range(1, 11):
        is_upd = t is not None and k == t
        ax.add_patch(FancyBboxPatch((2.05 + k * 0.92, y - 0.3), 0.8, 0.6, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    fc=BLUE if is_upd else "#f3c3ad", ec="none"))
        if is_upd:
            ax.text(2.45 + k * 0.92, y, "update", ha="center", va="center", color="white", fontsize=8)
ax.text(2.45, 5.1, "Opening", ha="center", fontsize=8.5, color=INK2)
for k in range(1, 11):
    ax.text(2.45 + k * 0.92, 5.1, f"Turn {k}", ha="center", fontsize=8.5, color=MUTED)
ax.legend(handles=[Patch(color=INK2, label="Opening: the vignette and the question"),
                   Patch(color="#f3c3ad", label="Noise turn (direct or non-direct pushback, no clinical content)"),
                   Patch(color=BLUE, label="One clinical update: supportive, neutral fact, alarming, reassuring or diagnosis-changing")],
          loc="lower left", bbox_to_anchor=(0.0, -0.02), ncol=1, fontsize=9)
ax.set_title("One conversation: an opening, then ten turns. At most one turn carries evidence; the rest is noise")
save(fig, "fig01_design.png", SEC1, "The conversation design",
     "After every message the model gives a diagnosis, an urgency level (A emergency to D routine) and its confidence in each, "
     "so each conversation gives 11 answers. Every vignette runs in three languages (English, Chinese, Japanese), for three "
     "speakers (patient, nurse, doctor), with two kinds of noise, and with each update at four timings.")

# ---------------------------------------------------------------- fig 2: noise versus evidence, headline
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
for ax, col, ttl, sub in ((axes[0], "u_changed", "Urgency level changed", changed),
                          (axes[1], "dx_moved", "Leading diagnosis changed", changed[changed.dx_moved.notna()])):
    vals = [sub.loc[sub.kind == k, col].astype(float).mean() if (sub.kind == k).any() else np.nan for k in KIND_ORDER]
    ns = [int((sub.kind == k).sum()) for k in KIND_ORDER]
    y = np.arange(len(KIND_ORDER))[::-1]
    ax.barh(y, vals, color=[FAMILY_COL[k] for k in KIND_ORDER], height=0.62)
    for yi, v, n in zip(y, vals, ns):
        if not np.isnan(v):
            ax.text(v + 0.012, yi, f"{pct(v)}  (n = {n:,})", va="center", fontsize=9, color=INK2)
    ax.set_yticks(y); ax.set_yticklabels([KIND_LAB[k] for k in KIND_ORDER])
    pct_axis(ax, "x", 1.0); ax.set_xlim(0, 1.18); clean(ax); ax.set_title(ttl)
fig.suptitle("Share of replies in which the answer changed, by what the previous message was", x=0.01, ha="left", fontweight="bold")
fig.legend(handles=[Patch(color=ORANGE, label="Noise"), Patch(color=MUTED, label="Facts that should change nothing"),
                    Patch(color=BLUE, label="Evidence that should change the answer")],
           loc="upper left", bbox_to_anchor=(0.005, 0.94), ncol=3, fontsize=9)
fig.tight_layout(rect=(0, 0, 1, 0.9))
save(fig, "fig02_noise_vs_evidence.png", SEC2, "Noise versus evidence",
     "Each bar is the share of replies, straight after that kind of message, whose answer differs from the reply before. "
     "The reassuring update exists only in the three reversal cases and the diagnosis update only in the ten main vignettes. "
     "An alarming update is not meant to change the diagnosis; a diagnosis update usually changes the urgency too.")

# ---------------------------------------------------------------- fig 3: direction
fig, ax = plt.subplots(figsize=(9.5, 4.6))
rows, labs, ns = [], [], []
for k in KIND_ORDER:
    g = changed[changed.kind == k]
    if len(g):
        rows.append(shares(g)); labs.append(KIND_LAB[k]); ns.append(len(g))
stacked_direction(ax, rows, labs, ns)
direction_legend(ax, loc="lower center", bbox_to_anchor=(0.5, 1.0))
ax.set_title("Which way the urgency moved after each kind of message", pad=28)
save(fig, "fig03_direction.png", SEC2, "Direction of the urgency change",
     "The alarming update should move the urgency up and the reassuring update down; the neutral and supportive facts should "
     "leave it where it is. Noise carries no clinical content, so any movement after it is unwanted.")

# ---------------------------------------------------------------- fig 4: reversal cases
rev = changed[changed.vignette.isin(["V21", "V22", "V23"])]
if len(rev):
    names = lt[lt.vignette.isin(["V21", "V22", "V23"])].groupby("vignette").start_dx.first()
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.6), sharey=True)
    for ax, v in zip(axes, ["V21", "V22", "V23"]):
        rows, labs, ns = [], [], []
        for k in ("discordant_urgency", "discordant_reassure", "neutral", "supportive"):
            g = rev[(rev.vignette == v) & (rev.kind == k)]
            rows.append(shares(g)); labs.append(KIND_LAB[k]); ns.append(None)
        stacked_direction(ax, rows, labs, ns)
        ax.set_title(f"{v}: {names.get(v, '')}", fontsize=10)
        ax.set_xticks([0, 0.5, 1.0]); ax.set_xticklabels(["0%", "50%", "100%"])
    direction_legend(fig, loc="upper center", bbox_to_anchor=(0.5, 1.12))
    fig.tight_layout()
    n_cell = int(rev[(rev.vignette == "V21") & (rev.kind == "neutral")].shape[0])
    save(fig, "fig04_reversal_cases.png", SEC2, "The reversal cases: the same missing detail filled in two ways",
         f"Each reversal case withholds one detail. It then arrives as an alarming fill, a reassuring fill, a neutral fact or a "
         f"supportive fact ({n_cell} conversations per bar). The model escalates on the alarming fill almost every time and "
         f"de-escalates on the reassuring fill in one case of three.")

# ---------------------------------------------------------------- fig 5: timing of the update
upd = changed[changed.reply == changed.upd_reply].copy()
panels = [("discordant_urgency", "Alarming update:\nurgency moved up", lambda g: (g.urgency_direction == "more_urgent")),
          ("discordant_reassure", "Reassuring update:\nurgency moved down", lambda g: (g.urgency_direction == "less_urgent")),
          ("discordant_dx", "Diagnosis update:\nnew diagnosis given", lambda g: (g.dx_leading == "post"))]
panels = [p for p in panels if (upd.kind == p[0]).any()]
fig, axes = plt.subplots(1, len(panels), figsize=(4.1 * len(panels), 3.9), sharey=True)
for ax, (k, ttl, fn) in zip(np.atleast_1d(axes), panels):
    g = upd[upd.kind == k]
    if k == "discordant_dx":
        g = g[g.dx_leading.notna()]
    ends = []
    for nt in ("nondirect", "direct"):
        s = g[g.noise_type == nt]
        m = fn(s).groupby(s.update_turn).mean()
        xs = list(range(len(m)))
        ax.plot(xs, m.values, color=NOISE_COL[nt], linewidth=2, marker="o", markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ends.append((m.values[-1], f"{NOISE_LAB[nt].split()[0]} {pct(m.values[-1])}"))
    end_labels(ax, xs[-1] + 0.12, ends, 0.06)
    ax.set_xticks(xs); ax.set_xticklabels([f"after\nreply {int(t)}" for t in m.index])
    ax.set_xlim(-0.3, len(xs) + 0.15); pct_axis(ax, "y"); clean(ax, "y"); ax.set_title(ttl, fontsize=10)
np.atleast_1d(axes)[0].legend(handles=[plt.Line2D([], [], color=NOISE_COL[n], lw=2, marker="o", label=NOISE_LAB[n]) for n in NOISE_COL],
                               loc="lower left", fontsize=8.5)
fig.suptitle("Does noise before the evidence weaken its uptake?", x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, "fig05_timing.png", SEC3, "Uptake of the update by when it arrives",
     "The update arrives after reply 1 (no noise before it), 3, 5 or 10 (nine noise turns before it). Each point is the share of "
     "conversations that responded as the update should make them, at the reply straight after it.")

# ---------------------------------------------------------------- fig 6: drift under noise alone
pre = lt[(lt.upd_reply.isna()) | (lt.reply < lt.upd_reply)].copy()
pre["noise_turns"] = pre.reply - 1
pre["u_same"] = pre.urgency == pre.u1
pre["d_same"] = pre.dx_leading == pre.d1
fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.9), sharey=True)
for ax, col, ttl, sub in ((axes[0], "u_same", "Urgency still as in the first answer", pre),
                          (axes[1], "d_same", "Leading diagnosis still as in the first answer", pre[pre.dx_leading.notna() & pre.d1.notna()])):
    ends = []
    for nt in ("nondirect", "direct"):
        s = sub[sub.noise_type == nt]
        m = s.groupby("noise_turns")[col].mean()
        ax.plot(m.index, m.values, color=NOISE_COL[nt], linewidth=2, marker="o", markersize=5, markeredgecolor=SURFACE, markeredgewidth=1.2)
        ends.append((m.values[-1], f"{NOISE_LAB[nt].split()[0]} {pct(m.values[-1])}"))
    end_labels(ax, 10.25, ends, 0.035)
    ax.set_xticks(range(0, 11)); ax.set_xlim(-0.3, 12.8); ax.set_ylim(0.5, 1.0)
    ax.set_yticks([0.5, 0.6, 0.7, 0.8, 0.9, 1.0]); ax.set_yticklabels(["50%", "60%", "70%", "80%", "90%", "100%"])
    ax.set_xlabel("Noise turns received so far (no evidence yet)"); clean(ax, "y"); ax.set_title(ttl, fontsize=10)
axes[0].legend(handles=[plt.Line2D([], [], color=NOISE_COL[n], lw=2, marker="o", label=NOISE_LAB[n]) for n in NOISE_COL],
               loc="lower left", fontsize=8.5)
fig.suptitle("Drift under noise alone", x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
n10 = int(pre[pre.noise_turns == 10].job_id.nunique())
save(fig, "fig06_drift_under_noise.png", SEC3, "Drift under noise alone",
     f"Every reply given before any update has arrived, in every arm. The vertical axis starts at 50%. The number of "
     f"conversations falls along the axis as updates arrive: all {n_conv:,} at zero noise turns, {n10:,} (the control arm) at ten.")

# ---------------------------------------------------------------- fig 7: holding the updated answer through later noise
post = lt[lt.upd_reply.notna() & (lt.reply >= lt.upd_reply)].copy()
at_upd = post[post.reply == post.upd_reply].set_index("job_id")
post["u_at_upd"] = post.job_id.map(at_upd.urgency)
post["dir_at_upd"] = post.job_id.map(at_upd.urgency_direction)
post["dx_at_upd"] = post.job_id.map(at_upd.dx_leading)
post["after"] = post.reply - post.upd_reply
took_u = post[((post.update_kind == "discordant_urgency") & (post.dir_at_upd == "more_urgent")) |
              ((post.update_kind == "discordant_reassure") & (post.dir_at_upd == "less_urgent"))].copy()
took_u["held"] = took_u.urgency == took_u.u_at_upd
took_d = post[(post.update_kind == "discordant_dx") & (post.dx_at_upd == "post") & post.dx_leading.notna()].copy()
took_d["held"] = took_d.dx_leading == "post"
fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.9), sharey=True)
for ax, sub, ttl in ((axes[0], took_u, "Urgency still at the level adopted after the update"),
                     (axes[1], took_d, "Diagnosis still the new one")):
    if not len(sub):
        ax.axis("off"); continue
    ends = []
    for nt in ("nondirect", "direct"):
        s = sub[sub.noise_type == nt]
        m = s.groupby("after").held.mean()
        ax.plot(m.index, m.values, color=NOISE_COL[nt], linewidth=2, marker="o", markersize=5, markeredgecolor=SURFACE, markeredgewidth=1.2)
        ends.append((m.values[-1], f"{NOISE_LAB[nt].split()[0]} {pct(m.values[-1])}"))
    end_labels(ax, 9.25, ends, 0.035)
    ax.set_xticks(range(0, 10)); ax.set_xlim(-0.3, 11.8); ax.set_ylim(0.5, 1.0)
    ax.set_yticks([0.5, 0.6, 0.7, 0.8, 0.9, 1.0]); ax.set_yticklabels(["50%", "60%", "70%", "80%", "90%", "100%"])
    ax.set_xlabel("Noise turns since the update"); clean(ax, "y"); ax.set_title(ttl, fontsize=10)
axes[0].legend(handles=[plt.Line2D([], [], color=NOISE_COL[n], lw=2, marker="o", label=NOISE_LAB[n]) for n in NOISE_COL],
               loc="lower left", fontsize=8.5)
fig.suptitle("After the model has taken up the evidence, does noise undo it?", x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, "fig07_holding_after_update.png", SEC3, "Holding the updated answer through later noise",
     f"Only conversations that took up the update at the reply straight after it ({took_u.job_id.nunique():,} for urgency, "
     f"{took_d.job_id.nunique():,} for diagnosis). The vertical axis starts at 50%. Fewer conversations contribute to the "
     f"right-hand points, because a late update leaves few turns after it.")

# ---------------------------------------------------------------- fig 8: noise by language and speaker (heat maps)
nz = changed[changed.turn_kind == "noise"]
fig, axes = plt.subplots(2, 2, figsize=(9.6, 6.2))
for r, (col, lab, sub) in enumerate((("u_changed", "urgency changed", nz), ("dx_moved", "diagnosis changed", nz[nz.dx_moved.notna()]))):
    vmax = max(0.2, float(sub.groupby(["noise_type", "language", "perspective"])[col].apply(lambda s: s.astype(float).mean()).max()))
    for c, nt in enumerate(("nondirect", "direct")):
        ax = axes[r, c]
        t = sub[sub.noise_type == nt].assign(v=lambda d: d[col].astype(float)).pivot_table(index="perspective", columns="language", values="v")
        t = t.reindex(index=list(PERS_LAB), columns=list(LANG_LAB))
        im = ax.imshow(t.values, cmap=matplotlib.colors.LinearSegmentedColormap.from_list("b", ["#eef4fd", "#9ec5f4", "#2a78d6", "#0d366b"]),
                       vmin=0, vmax=vmax, aspect="auto")
        for i in range(t.shape[0]):
            for j in range(t.shape[1]):
                v = t.values[i, j]
                ax.text(j, i, f"{100 * v:.1f}%", ha="center", va="center", color="white" if v > 0.55 * vmax else INK, fontsize=10)
        ax.set_xticks(range(3)); ax.set_xticklabels(LANG_LAB.values()); ax.set_yticks(range(3)); ax.set_yticklabels(PERS_LAB.values())
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title(f"{NOISE_LAB[nt]}: {lab}", fontsize=10)
fig.suptitle("Share of noise replies in which the answer changed, by speaker and language", x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, "fig08_noise_by_language_speaker.png", SEC4, "Noise, by who speaks and in which language",
     f"{len(nz):,} replies given straight after a noise turn. Darker cells mean the answer changed more often. "
     f"Top row: urgency. Bottom row: leading diagnosis (replies whose diagnosis has been read).")

# ---------------------------------------------------------------- fig 9: uptake by language and speaker
fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.9), sharey=True)
for ax, by, labmap, cols in ((axes[0], "language", LANG_LAB, [BLUE, ORANGE, AQUA]), (axes[1], "perspective", PERS_LAB, [BLUE, ORANGE, AQUA])):
    w = 0.26
    for i, (key, lab) in enumerate(labmap.items()):
        vals = []
        for k, ttl, fn in panels:
            g = upd[(upd.kind == k) & (upd[by] == key)]
            if k == "discordant_dx":
                g = g[g.dx_leading.notna()]
            vals.append(fn(g).mean() if len(g) else np.nan)
        xs = np.arange(len(panels)) + (i - 1) * w
        ax.bar(xs, vals, width=w - 0.03, color=cols[i], label=lab)
        for x, v in zip(xs, vals):
            if not np.isnan(v):
                ax.text(x, v + 0.015, pct(v), ha="center", fontsize=8.5, color=INK2)
    ax.set_xticks(range(len(panels))); ax.set_xticklabels([p[1] for p in panels], fontsize=9)
    pct_axis(ax, "y"); ax.set_ylim(0, 1.12); clean(ax, "y")
    ax.legend(ncol=3, loc="lower right", bbox_to_anchor=(1.0, 1.0), fontsize=9)
    ax.set_title("By language" if by == "language" else "By who gives the update", fontsize=10, pad=10)
fig.tight_layout()
save(fig, "fig09_uptake_by_language_speaker.png", SEC4, "Uptake of the evidence, by language and by speaker",
     "The same three measures as in the timing figure, at the reply straight after the update, split by the language of the "
     "conversation and by who is speaking. The patient gives the update in their own words; the nurse and doctor send it as a clinical note.")

# ---------------------------------------------------------------- fig 10: starting point by vignette
r1 = lt[lt.reply == 1]
vs = sorted(r1.vignette.unique())
names = r1.groupby("vignette").start_dx.first()
ref = r1.groupby("vignette").exp_urgency.first()
fig, ax = plt.subplots(figsize=(10.5, 0.42 * len(vs) + 1.6))
y = np.arange(len(vs))[::-1]
for i, v in enumerate(vs):
    g = r1[r1.vignette == v]
    left = 0
    for lev in "ABCD":
        val = (g.urgency == lev).mean()
        ax.barh(y[i], val, left=left, color=LEVELS[lev], height=0.66, edgecolor=SURFACE, linewidth=1.5)
        if val >= 0.07:
            ax.text(left + val / 2, y[i], f"{lev} {pct(val)}", ha="center", va="center", color="white" if lev in "AB" else INK, fontsize=8.5)
        left += val
    ax.text(1.02, y[i], f"reference: {ref[v]}", va="center", fontsize=9, color=INK2)
ax.set_yticks(y); ax.set_yticklabels([f"{v}  {short(names[v])}" for v in vs])
pct_axis(ax, "x"); ax.set_xlim(0, 1.2); clean(ax, grid=None); ax.spines["left"].set_visible(False)
ax.legend(handles=[Patch(color=LEVELS[l], label=f"{l}  {t}") for l, t in zip("ABCD", ("emergency", "same day", "within a week", "routine"))],
          ncol=4, loc="lower center", bbox_to_anchor=(0.45, 1.0), fontsize=9)
ax.set_title("The model's urgency in its first answer, against the clinicians' reference level", pad=28)
save(fig, "fig10_starting_urgency.png", SEC5, "Where the model starts",
     "The urgency level in the first answer, before any noise or update. Where the commonest level differs from the reference, "
     "the model starts more urgent than the clinicians set, so 'correct' rates for that vignette are low for a reason unrelated "
     "to noise. The figures above use the direction of change, which does not depend on the reference.")

# ---------------------------------------------------------------- fig 11: uptake by vignette
fig, axes = plt.subplots(1, 2, figsize=(11.5, 0.36 * len(vs) + 1.6), sharey=True)
for ax, k, ttl, fn in ((axes[0], "discordant_urgency", "Alarming update: urgency moved up", lambda g: (g.urgency_direction == "more_urgent")),
                       (axes[1], "discordant_dx", "Diagnosis update: new diagnosis given", lambda g: (g.dx_leading == "post"))):
    vals = []
    for v in vs:
        g = upd[(upd.kind == k) & (upd.vignette == v)]
        if k == "discordant_dx":
            g = g[g.dx_leading.notna()]
        vals.append(fn(g).mean() if len(g) else np.nan)
    ax.barh(y, [0 if np.isnan(v) else v for v in vals], color=BLUE, height=0.62)
    for yi, v in zip(y, vals):
        ax.text((0 if np.isnan(v) else v) + 0.015, yi, "no such arm" if np.isnan(v) else pct(v), va="center", fontsize=9,
                color=MUTED if np.isnan(v) else INK2)
    ax.set_yticks(y); ax.set_yticklabels([f"{v}  {short(names[v])}" for v in vs])
    pct_axis(ax, "x"); ax.set_xlim(0, 1.22); clean(ax); ax.set_title(ttl, fontsize=10)
fig.tight_layout()
save(fig, "fig11_uptake_by_vignette.png", SEC5, "Uptake of the evidence, vignette by vignette",
     "The reversal cases (V21 to V23) have no diagnosis update, and V06 has no alarming update. Every bar is one vignette "
     "across all languages, speakers, noise types and timings.")

# ---------------------------------------------------------------- fig 12: confidence
fig, axes = plt.subplots(1, 2, figsize=(11, 4.0), sharey=True)
for ax, col, ttl in ((axes[0], "urgency_confidence_delta", "Confidence in the urgency level"),
                     (axes[1], "diagnosis_confidence_delta", "Confidence in the diagnosis")):
    vals = [changed.loc[changed.kind == k, col].mean() if (changed.kind == k).any() else np.nan for k in KIND_ORDER]
    y2 = np.arange(len(KIND_ORDER))[::-1]
    ax.barh(y2, vals, color=[FAMILY_COL[k] for k in KIND_ORDER], height=0.62)
    for yi, v in zip(y2, vals):
        if not np.isnan(v):
            ax.text(v + (0.25 if v >= 0 else -0.25), yi, f"{v:+.1f}", va="center", ha="left" if v >= 0 else "right", fontsize=9, color=INK2)
    ax.axvline(0, color=AXIS, linewidth=1)
    ax.set_yticks(y2); ax.set_yticklabels([KIND_LAB[k] for k in KIND_ORDER]); clean(ax)
    lim = max(np.nanmax(np.abs([changed.loc[changed.kind == k, c].mean() for k in KIND_ORDER if (changed.kind == k).any()]))
              for c in ("urgency_confidence_delta", "diagnosis_confidence_delta")) * 1.3 + 1
    ax.set_xlim(-lim, lim); ax.set_xlabel("Mean change in stated confidence (points out of 100)"); ax.set_title(ttl, fontsize=10)
fig.suptitle("How the model's stated confidence moves after each kind of message", x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, "fig12_confidence.png", SEC2, "Stated confidence",
     "Mean change, from the reply before, in the confidence the model states (0 to 100). Orange: noise. Grey: facts that should "
     "change nothing. Blue: evidence that should change the answer.")

# ---------------------------------------------------------------- the page
unj = int((lt.dx_method.astype(str) == "unjudged").sum())
stage_lines = "".join(f"<li><b>{html.escape(str(s))}</b>: {int(r.conversations):,} conversations, {int(r.vignettes)} vignettes, "
                      f"{int(r.repeats)} repeat(s)</li>" for s, r in blocks.iterrows())
parts, cur = [], None
for name, section, title, caption in FIGS:
    if section != cur:
        parts.append(f"<h2>{html.escape(section)}</h2>"); cur = section
    b64 = base64.b64encode((OUT / name).read_bytes()).decode()
    parts.append(f'<figure><h3>{html.escape(title)}</h3><img alt="{html.escape(title)}" src="data:image/png;base64,{b64}">'
                 f"<figcaption>{html.escape(caption)}</figcaption></figure>")
page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Noise versus evidence in triage conversations: results</title>
<style>
body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: #f9f9f7; color: #0b0b0b; margin: 0; }}
main {{ max-width: 1080px; margin: 0 auto; padding: 28px 20px 60px; }}
h1 {{ font-size: 26px; margin: 0 0 6px; }} h2 {{ font-size: 20px; margin: 44px 0 6px; border-top: 1px solid #e1e0d9; padding-top: 22px; }}
h3 {{ font-size: 15px; margin: 0 0 10px; }}
p, li {{ line-height: 1.5; color: #52514e; }} .lead {{ color: #0b0b0b; }}
figure {{ background: #fcfcfb; border: 1px solid rgba(11,11,11,0.10); border-radius: 10px; padding: 18px; margin: 18px 0; }}
figure img {{ width: 100%; height: auto; display: block; }}
figcaption {{ color: #52514e; font-size: 14px; line-height: 1.5; margin-top: 10px; }}
.note {{ background: #fcfcfb; border-left: 3px solid #eda100; padding: 10px 14px; margin: 14px 0; }}
</style></head><body><main>
<h1>Noise versus evidence in triage conversations</h1>
<p class="lead">Results for Claude Haiku. {html.escape(STATUS)}</p>
<p>{n_conv:,} conversations and {n_rep:,} replies are in these figures:</p><ul>{stage_lines}</ul>
<div class="note"><p><b>How to read these.</b> Urgency figures use the direction of change (more urgent, unchanged, less urgent),
which does not depend on the clinicians' reference level. Diagnosis figures use the replies whose diagnosis has been read
({unj:,} of {n_rep:,} replies have not been read and are left out). Diagnoses were judged by their leading part, with a
rule checked against full readings on 150 strings; no clinician has reviewed the readings.</p></div>
{''.join(parts)}
</main></body></html>"""
(OUT / "index.html").write_text(page, encoding="utf-8", newline="\n")
print("wrote index.html", len(page) // 1024, "KB")
