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
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch  # noqa: E402
from scipy import stats as sstats  # noqa: E402

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
LANG_COL = {"en": AQUA, "zh": YELLOW, "ja": VIOLET}
PERS_COL = {"patient": "#9ec5f4", "nurse": "#2a78d6", "consultant": "#0d366b"}      # one hue, darker with seniority
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
    raw = [t[0] for t in items]
    ys = raw[:]
    for k in range(1, len(ys)):
        ys[k] = max(ys[k], ys[k - 1] + gap)
    shift = sum(a - b for a, b in zip(ys, raw)) / len(ys)
    ys = [a - shift for a in ys]
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
for ax, by, labmap, cols in ((axes[0], "language", LANG_LAB, list(LANG_COL.values())), (axes[1], "perspective", PERS_LAB, list(PERS_COL.values()))):
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
     "conversation and by who is speaking. The patient gives the update in their own words; the nurse and doctor send it as a clinical note. "
     "Speakers are drawn in one blue, darker for the more senior.")

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

# ================================================================ breakdowns by language and speaker, tests, confidence
COMBOS = [(lang, p) for lang in LANG_LAB for p in PERS_LAB]
DIV = LinearSegmentedColormap.from_list("div", [LESS, "#efeeea", MORE])
SEQ = LinearSegmentedColormap.from_list("b", ["#eef4fd", "#9ec5f4", "#2a78d6", "#0d366b"])
EXTRA: dict[str, list[str]] = {}
SEC6 = "Stated confidence and agreement between repeats"


def dev_table(ax, t, base, row_labels, title, span=0.15, col_groups=True):
    """Heat table. Text is the share; colour is the difference from `base` (one value per row), clipped at +/- span."""
    dev = t.values - np.asarray(base, dtype=float)[:, None]
    im = ax.imshow(dev, cmap=DIV, vmin=-span, vmax=span, aspect="auto")
    for i in range(t.shape[0]):
        for j in range(t.shape[1]):
            v = t.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, pct(v), ha="center", va="center", fontsize=9, color="white" if abs(dev[i, j]) > 0.62 * span else INK)
    ax.set_yticks(range(t.shape[0])); ax.set_yticklabels(row_labels)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    if col_groups:
        ax.set_xticks(range(9)); ax.set_xticklabels([PERS_LAB[p] for _, p in COMBOS], fontsize=8.5)
        for gi, lang in enumerate(LANG_LAB):
            ax.text(1 + 3 * gi, -0.72, LANG_LAB[lang], ha="center", va="bottom", fontsize=9.5, color=INK2, fontweight="bold")
        for xv in (2.5, 5.5):
            ax.axvline(xv, color=SURFACE, linewidth=4)
        ax.set_title(title, fontsize=10, pad=24)
    else:
        ax.set_title(title, fontsize=10)
    return im


def dev_bar(fig, im, axes, span, what, pad=0.07):
    cb = fig.colorbar(im, ax=axes, orientation="horizontal", fraction=0.035, pad=pad, aspect=45)
    cb.set_ticks([-span, 0, span])
    cb.set_ticklabels([f"{100 * span:.0f} points below", what, f"{100 * span:.0f} points above"])
    cb.outline.set_visible(False); cb.ax.tick_params(length=0, labelsize=8.5)


def combo_pivot(sub, col, index):
    s = sub.assign(v=sub[col].astype(float))
    t = s.pivot_table(index=index, columns=["language", "perspective"], values="v")
    return t.reindex(columns=pd.MultiIndex.from_tuples(COMBOS))


def group_lines(ax, sub, by, xcol, ycol, colmap, labmap, xend, gap, xlabels=None):
    ends = []
    for key, lab in labmap.items():
        s = sub[sub[by] == key]
        if not len(s):
            continue
        m = s.groupby(xcol)[ycol].mean()
        xs = list(range(len(m))) if xlabels else list(m.index)
        ax.plot(xs, m.values, color=colmap[key], linewidth=2, marker="o", markersize=4.5, markeredgecolor=SURFACE, markeredgewidth=1.1)
        ends.append((m.values[-1], f"{lab} {pct(m.values[-1])}"))
    end_labels(ax, xend, ends, gap)
    return m


def line_handles(colmap, labmap):
    return [plt.Line2D([], [], color=colmap[k], lw=2, marker="o", label=lab) for k, lab in labmap.items()]


def fmt_p(p):
    return "n/a" if p is None or np.isnan(p) else ("&lt; 0.001" if p < 0.001 else f"{p:.3f}")


def pts(x):
    return "n/a" if x is None or np.isnan(x) else f"{100 * x:+.1f}"


# ---------------------------------------------------------------- fig 13: every message kind by language and speaker
kinds_here = [k for k in KIND_ORDER if (changed.kind == k).any()]
fig, axes = plt.subplots(2, 1, figsize=(11, 9.2), gridspec_kw={"hspace": 0.42})
for ax, col, ttl, sub in ((axes[0], "u_changed", "Urgency level changed", changed),
                          (axes[1], "dx_moved", "Leading diagnosis changed", changed[changed.dx_moved.notna()])):
    t = combo_pivot(sub, col, "kind").reindex(kinds_here)
    base = sub.assign(v=sub[col].astype(float)).groupby("kind").v.mean().reindex(kinds_here)
    im = dev_table(ax, t, base.values, [f"{KIND_LAB[k]}  (all: {pct(base[k])})" for k in kinds_here], ttl)
dev_bar(fig, im, axes, 0.15, "same as the row's overall share")
fig.suptitle("Share of replies in which the answer changed, by message kind, language and speaker", x=0.01, ha="left", fontweight="bold")
save(fig, "fig13_kinds_by_language_speaker.png", SEC2, "Noise versus evidence, for every language and speaker",
     "Each cell is the share of replies, straight after that kind of message, whose answer differs from the reply before. "
     "The number is the share; the colour shows how far that language and speaker sits from the row's overall share "
     "(red above, blue below, full colour at 15 points). A row that is pale all the way across behaves the same for everyone.")

# ---------------------------------------------------------------- fig 14: the reassuring update, level by level
rev_ids = [v for v in ("V21", "V22", "V23") if (lt.vignette == v).any()]
if rev_ids and (lt.update_kind == "discordant_reassure").any():
    def level_bars(ax, groups, labels):
        yy = np.arange(len(groups))[::-1]
        for i, s in enumerate(groups):
            left = 0
            for lev in "ABCD":
                val = float((s == lev).mean()) if len(s) else 0.0
                ax.barh(yy[i], val, left=left, color=LEVELS[lev], height=0.62, edgecolor=SURFACE, linewidth=1.5)
                if val >= 0.09:
                    ax.text(left + val / 2, yy[i], f"{lev} {pct(val)}", ha="center", va="center", fontsize=8.5,
                            color="white" if lev in "AB" else INK)
                left += val
        ax.set_yticks(yy); ax.set_yticklabels(labels)
        ax.set_xlim(0, 1); ax.set_xticks([0, 0.5, 1.0]); ax.set_xticklabels(["0%", "50%", "100%"])
        clean(ax, grid=None); ax.spines["left"].set_visible(False)

    names_r = lt[lt.vignette.isin(rev_ids)].groupby("vignette").start_dx.first()
    fig, axes = plt.subplots(2, len(rev_ids), figsize=(4.2 * len(rev_ids), 4.6), sharey="row", squeeze=False)
    for r, (k, lab) in enumerate((("discordant_reassure", "Reassuring update"), ("discordant_urgency", "Alarming update"))):
        for c, v in enumerate(rev_ids):
            conv = lt[(lt.vignette == v) & (lt.update_kind == k)]
            at = conv[conv.reply == conv.upd_reply]
            end = conv[(conv.reply == 11) & (conv.update_turn != 10)]
            level_bars(axes[r, c], [at.prev_urgency, at.urgency, end.urgency],
                       ["Reply before the update", "Reply straight after", "End of the conversation"])
            axes[r, c].set_title(f"{lab}\n{v}: {names_r.get(v, '')}" if r == 0 else f"{lab}", fontsize=10)
    fig.legend(handles=[Patch(color=LEVELS[l], label=f"{l}  {t}") for l, t in zip("ABCD", ("emergency", "same day", "within a week", "routine"))],
               ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.06), fontsize=9)
    fig.tight_layout()
    save(fig, "fig14_reassuring_levels.png", SEC2, "The reassuring update: where the urgency went",
         "The urgency level before the update, straight after it, and at the end of the conversation (conversations whose update "
         "came after reply 1, 3 or 5, so that noise turns follow it). The clinicians' reference after the reassuring fill is D in "
         "all three cases. Bottom row: the alarming fill in the same cases, for comparison.")

# ---------------------------------------------------------------- fig 15: what the timing effect on the alarming update is
au = upd[upd.kind == "discordant_urgency"].copy()
if len(au):
    au["moved"] = au.urgency_direction == "more_urgent"
    au["above_first"] = au.urgency < au.u1                       # letters sort A (most urgent) to D
    au["pre_above"] = au.prev_urgency < au.u1
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    ends = []
    for col, colr, style, lab in (("above_first", INK2, "-", "More urgent than the first answer, after the update"),
                                  ("moved", BLUE, "-", "Moved up at the update"),
                                  ("pre_above", MUTED, "--", "Already more urgent than the first answer before the update")):
        m = au.groupby("update_turn")[col].mean()
        xs = list(range(len(m)))
        ax.plot(xs, m.values, color=colr, linestyle=style, linewidth=2, marker="o", markersize=5.5, markeredgecolor=SURFACE,
                markeredgewidth=1.3, label=lab)
        ends.append((m.values[-1], pct(m.values[-1])))
    end_labels(ax, xs[-1] + 0.1, ends, 0.06)
    ax.set_xticks(xs); ax.set_xticklabels([f"after\nreply {int(t)}" for t in m.index]); ax.set_xlim(-0.3, len(xs) - 0.55)
    pct_axis(ax, "y"); clean(ax, "y")
    ax.legend(loc="center left", bbox_to_anchor=(0.0, 0.42), fontsize=8.5)
    ax.set_title("Alarming update: why later updates seem to move the urgency less")
    save(fig, "fig15_timing_alarming_explained.png", SEC3, "The alarming update by timing, taken apart",
         "Fewer conversations move up at a late alarming update. The share that ends up more urgent than its own first answer "
         "does not fall: by the time a late update arrives, noise has already pushed some conversations up, so the update has "
         "nothing left to add there.")

# ---------------------------------------------------------------- fig 16: timing by language and by speaker
upd = upd.copy()
for k, _, fn in panels:
    upd.loc[upd.kind == k, "took"] = fn(upd[upd.kind == k]).astype(float)
upd.loc[(upd.kind == "discordant_dx") & upd.dx_leading.isna(), "took"] = np.nan
fig, axes = plt.subplots(2, len(panels), figsize=(4.3 * len(panels), 7.0), sharey=True, squeeze=False)
for r, (by, colmap, labmap) in enumerate((("language", LANG_COL, LANG_LAB), ("perspective", PERS_COL, PERS_LAB))):
    for c, (k, ttl, _) in enumerate(panels):
        ax = axes[r, c]
        g = upd[(upd.kind == k) & upd.took.notna()]
        m = group_lines(ax, g, by, "update_turn", "took", colmap, labmap, 3.12, 0.065, xlabels=True)
        ax.set_xticks(range(len(m))); ax.set_xticklabels([f"after\nreply {int(t)}" for t in m.index])
        ax.set_xlim(-0.3, len(m) + 0.45); pct_axis(ax, "y"); clean(ax, "y")
        ax.set_title(ttl if r == 0 else ttl.split(":")[0], fontsize=10)
    axes[r, 0].legend(handles=line_handles(colmap, labmap), loc="lower left", fontsize=8.5,
                      title="Language" if by == "language" else "Speaker", title_fontsize=8.5)
fig.suptitle("Uptake of the update by when it arrives: by language (top) and by speaker (bottom)", x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, "fig16_timing_by_language_speaker.png", SEC3, "Timing, by language and by speaker",
     "The same measures as the timing figure above. Top row: one line per language. Bottom row: one line per speaker "
     "(darker blue for the more senior speaker). The reassuring update exists only in the three reversal cases, so its lines "
     "rest on 54 conversations per point.")

# ---------------------------------------------------------------- fig 17: timing for every language and speaker
fig, axes = plt.subplots(1, len(panels), figsize=(4.0 * len(panels) + 1.2, 5.2), sharey=True, squeeze=False)
row_labs = [f"{LANG_LAB[lang]} · {PERS_LAB[p]}" for lang, p in COMBOS]
for c, (k, ttl, _) in enumerate(panels):
    ax = axes[0, c]
    g = upd[(upd.kind == k) & upd.took.notna()]
    t = g.pivot_table(index=["language", "perspective"], columns="update_turn", values="took").reindex(pd.MultiIndex.from_tuples(COMBOS))
    overall = float(g.took.mean())
    im = dev_table(ax, t, np.full(len(t), overall), row_labs, f"{ttl}\n(all: {pct(overall)})", span=0.2, col_groups=False)
    ax.set_xticks(range(t.shape[1])); ax.set_xticklabels([f"after\nreply {int(x)}" for x in t.columns], fontsize=8.5)
    for yv in (2.5, 5.5):
        ax.axhline(yv, color=SURFACE, linewidth=4)
dev_bar(fig, im, axes, 0.2, "same as the panel's overall share", pad=0.13)
save(fig, "fig17_timing_grid.png", SEC3, "Timing, for every language and speaker together",
     "Each cell is the share of conversations that responded as the update should make them, for one language, one speaker and "
     "one timing. Colour shows the difference from the panel's overall share (full colour at 20 points). Cells hold 72 "
     "conversations for the alarming update, about 55 for the diagnosis update and 18 for the reassuring update, so single "
     "cells of the reassuring panel are rough.")

# ---------------------------------------------------------------- fig 18: drift under noise, by language and speaker
def four_line_panels(specs, xcol, xmax, xlabel, title, fname, sec, ftitle, caption):
    """specs: two rows of (frame, ycol, row title). Columns: non-direct and direct noise, by language then by speaker."""
    fig, axes = plt.subplots(2, 4, figsize=(15.5, 6.6), sharey=True)
    for r, (sub, ycol, rtitle) in enumerate(specs):
        for c, (by, colmap, labmap, nt) in enumerate((("language", LANG_COL, LANG_LAB, "nondirect"), ("language", LANG_COL, LANG_LAB, "direct"),
                                                      ("perspective", PERS_COL, PERS_LAB, "nondirect"), ("perspective", PERS_COL, PERS_LAB, "direct"))):
            ax = axes[r, c]
            s = sub[sub.noise_type == nt]
            if len(s):
                group_lines(ax, s, by, xcol, ycol, colmap, labmap, xmax + 0.25, 0.04)
            ax.set_xticks(range(0, xmax + 1, 2)); ax.set_xlim(-0.3, xmax + 4.4); ax.set_ylim(0.4, 1.0)
            ax.set_yticks([0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]); ax.set_yticklabels(["40%", "50%", "60%", "70%", "80%", "90%", "100%"])
            clean(ax, "y"); ax.set_title(f"{rtitle}\n{NOISE_LAB[nt]}, by {'language' if by == 'language' else 'speaker'}", fontsize=9.5)
            if r == 1:
                ax.set_xlabel(xlabel)
    axes[0, 0].legend(handles=line_handles(LANG_COL, LANG_LAB), loc="lower left", fontsize=8.5)
    axes[0, 2].legend(handles=line_handles(PERS_COL, PERS_LAB), loc="lower left", fontsize=8.5)
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    save(fig, fname, sec, ftitle, caption)


four_line_panels([(pre, "u_same", "Urgency as in the first answer"),
                  (pre[pre.dx_leading.notna() & pre.d1.notna()], "d_same", "Diagnosis as in the first answer")],
                 "noise_turns", 10, "Noise turns received (no evidence yet)",
                 "Drift under noise alone, by language and by speaker", "fig18_drift_by_language_speaker.png", SEC3,
                 "Drift under noise alone, by language and by speaker",
                 "Every reply given before any update has arrived. Top row: urgency. Bottom row: leading diagnosis. The first two "
                 "columns split by language, the last two by speaker; each pair shows non-direct and direct noise. The vertical axis starts at 40%.")

# ---------------------------------------------------------------- fig 19: holding the updated answer, by language and speaker
four_line_panels([(took_u, "held", "Urgency still at the adopted level"), (took_d, "held", "Diagnosis still the new one")],
                 "after", 9, "Noise turns since the update",
                 "Holding the updated answer through later noise, by language and by speaker", "fig19_holding_by_language_speaker.png", SEC3,
                 "Holding the updated answer, by language and by speaker",
                 "Only conversations that took up the update at the reply straight after it. Same layout as the figure above. "
                 "The vertical axis starts at 40%; the right-hand points rest on fewer conversations.")

# ---------------------------------------------------------------- fig 20: persistence for every language and speaker
ctrl_end = pre[(pre.upd_reply.isna()) & (pre.reply == 11)].copy()
ctrl_end["u_lost"] = ~ctrl_end.u_same
ctrl_end["d_lost"] = ~ctrl_end.d_same
end_u = took_u[(took_u.reply == 11) & (took_u.update_turn != 10)].assign(lost=lambda d: ~d.held)
end_d = took_d[(took_d.reply == 11) & (took_d.update_turn != 10)].assign(lost=lambda d: ~d.held)
grid_specs = [[(ctrl_end, "u_lost", "Urgency no longer as in the first answer"),
               (ctrl_end[ctrl_end.dx_leading.notna() & ctrl_end.d1.notna()], "d_lost", "Diagnosis no longer as in the first answer")],
              [(end_u, "lost", "Adopted urgency level given up"), (end_d, "lost", "New diagnosis given up")]]
fig, axes = plt.subplots(2, 4, figsize=(15.5, 6.4))
for r, row in enumerate(grid_specs):
    vmax = max(0.2, max(float(sub.groupby(["noise_type", "language", "perspective"])[col].mean().max()) for sub, col, _ in row if len(sub)))
    for c2, (sub, col, lab) in enumerate(row):
        for c3, nt in enumerate(("nondirect", "direct")):
            ax = axes[r, 2 * c2 + c3]
            s = sub[sub.noise_type == nt]
            if not len(s):
                ax.axis("off"); continue
            t = s.assign(v=s[col].astype(float)).pivot_table(index="perspective", columns="language", values="v").reindex(index=list(PERS_LAB), columns=list(LANG_LAB))
            ax.imshow(t.values, cmap=SEQ, vmin=0, vmax=vmax, aspect="auto")
            for i in range(3):
                for j in range(3):
                    v = t.values[i, j]
                    if not np.isnan(v):
                        ax.text(j, i, pct(v), ha="center", va="center", color="white" if v > 0.55 * vmax else INK, fontsize=10)
            ax.set_xticks(range(3)); ax.set_xticklabels(LANG_LAB.values()); ax.set_yticks(range(3)); ax.set_yticklabels(PERS_LAB.values())
            ax.tick_params(length=0)
            for sp in ax.spines.values():
                sp.set_visible(False)
            ax.set_title(f"{lab}\n{NOISE_LAB[nt]}", fontsize=9.5)
fig.suptitle("By the end of the conversation: top, after ten noise turns and no evidence; bottom, after taking up an update",
             x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, "fig20_persistence_grid.png", SEC3, "Persistence, for every language and speaker together",
     f"Top row: the control arm ({ctrl_end.job_id.nunique():,} conversations with ten noise turns and no update), share whose final answer "
     f"differs from the first. Bottom row: conversations that took up an update given after reply 1, 3 or 5, share that no longer "
     f"hold it at the final reply. Darker cells mean the answer was lost more often; each row has its own colour scale. "
     f"Top-row cells hold about {int(ctrl_end.groupby(['noise_type', 'language', 'perspective']).job_id.nunique().median())} conversations each, so differences of a few points there are within chance.")

# ---------------------------------------------------------------- fig 21: stated confidence against agreement between repeats
def agreement_with_repeats(frame, answer, conf):
    key = ["script_id", "reply"]
    m = frame[key + ["repeat", answer, conf]].merge(frame[key + ["repeat", answer]], on=key, suffixes=("", "_o"))
    m = m[m.repeat != m.repeat_o]
    m["same"] = m[answer] == m[answer + "_o"]
    return m.groupby(key + ["repeat"]).agg(same=("same", "mean"), conf=(conf, "first")).reset_index().dropna(subset=["conf"])


CONF_TXT = ""
if lt.repeat.nunique() >= 2:
    ag_u = agreement_with_repeats(lt[lt.urgency.notna()], "urgency", "urgency_confidence")
    ag_d = agreement_with_repeats(lt[lt.dx_leading.notna()], "dx_key", "diagnosis_confidence")
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.3), sharey=True)
    rho = {}
    for ax, ag, ttl, edges, key in ((axes[0], ag_u, "Urgency level", [0, 49, 59, 69, 79, 89, 100], "u"),
                                    (axes[1], ag_d, "Leading diagnosis", [0, 29, 39, 49, 59, 69, 79, 100], "d")):
        ag = ag.assign(band=pd.cut(ag.conf, edges))
        gb = ag.groupby("band", observed=True).agg(n=("same", "size"), agree=("same", "mean"))
        xs = np.arange(len(gb))
        ax.bar(xs, gb.agree.values, color=BLUE, width=0.66)
        for x, (v, n) in zip(xs, zip(gb.agree.values, gb.n.values)):
            ax.text(x, v + 0.015, f"{pct(v)}\nn = {n:,}", ha="center", va="bottom", fontsize=8.5, color=INK2)
        labs = [f"below {int(iv.right) + 1}" if iv.left == 0 else (f"{int(iv.left) + 1} and over" if iv.right == 100 else f"{int(iv.left) + 1} to {int(iv.right)}")
                for iv in gb.index]
        ax.set_xticks(xs); ax.set_xticklabels(labs, fontsize=9); ax.set_xlabel("Confidence the model stated (0 to 100)")
        pct_axis(ax, "y"); ax.set_ylim(0, 1.2); ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0]); clean(ax, "y"); ax.set_title(ttl, fontsize=10)
        rho[key] = sstats.spearmanr(ag.conf, ag.same).statistic
    axes[0].set_ylabel("Share of the other repeats giving the same answer")
    fig.suptitle("When the model states higher confidence, do repeats of the same conversation agree more often?", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    save(fig, "fig21_confidence_agreement.png", SEC6, "Stated confidence against agreement between repeats",
         f"Every script was run {lt.repeat.nunique()} times. For each reply, the bar shows how often the other repeats of the same script, at the "
         f"same point in the conversation, gave the same urgency level (left) or the same leading diagnosis (right), grouped by the "
         f"confidence the model stated in that reply. Rank correlation between stated confidence and agreement: "
         f"{rho['u']:.2f} for urgency, {rho['d']:.2f} for diagnosis. After the first reply the repeats have seen their own earlier "
         f"answers, which can differ, so agreement measures the whole conversation so far.")
    r1c = lt[lt.reply == 1].assign(cell=lambda d: d.vignette + "|" + d.language + "|" + d.perspective)
    r1c["agree"] = r1c.urgency == r1c.cell.map(r1c.groupby("cell").urgency.agg(lambda s: s.value_counts().idxmax()))
    lo, hi = r1c[r1c.urgency_confidence < 70], r1c[r1c.urgency_confidence >= 80]
    CONF_TXT = (f"<p>The first reply is the cleanest test, because every conversation of one vignette, language and speaker starts from "
                f"the identical message ({int(r1c.groupby('cell').size().median())} replies per starting message). There, replies "
                f"stating a confidence below 70 gave the commonest urgency level {pct(lo.agree.mean())} of the time "
                f"(n = {len(lo):,}); replies stating 80 or more gave it {pct(hi.agree.mean())} of the time (n = {len(hi):,}). "
                f"Stated urgency confidence sits in a narrow band: half of all first replies state between "
                f"{r1c.urgency_confidence.quantile(0.25):.0f} and {r1c.urgency_confidence.quantile(0.75):.0f}.</p>")
    EXTRA.setdefault(SEC6, []).append(CONF_TXT)

# ---------------------------------------------------------------- tests: timing
def timing_test(g, y, n_perm=2000):
    g = g.assign(y=np.asarray(y, dtype=float), x=g.update_turn.map({1: 0, 3: 2, 5: 4, 10: 9}).astype(float))
    codes = pd.factorize(g.vignette + "|" + g.language + "|" + g.perspective + "|" + g.noise_type)[0]
    o = np.argsort(codes, kind="stable")
    codes, x, yv = codes[o], g.x.values[o], g.y.values[o]
    xc = x - pd.Series(x).groupby(codes).transform("mean").values
    yc = yv - pd.Series(yv).groupby(codes).transform("mean").values
    den = float((xc ** 2).sum())
    obs = float((xc * yc).sum() / den)
    rng = np.random.default_rng(20261116)
    hits = sum(abs(float((xc * yc[np.lexsort((rng.random(len(yc)), codes))]).sum()) / den) >= abs(obs) - 1e-12 for _ in range(n_perm))
    pv = g.pivot_table(index="vignette", columns="update_turn", values="y", aggfunc="mean")
    d = (pv[10] - pv[1]).dropna()
    by = g.groupby("update_turn").y.mean()
    return {"n": len(g), "first": by.get(1), "last": by.get(10), "slope9": 9 * obs, "p_within": (hits + 1) / (n_perm + 1),
            "down": int((d < 0).sum()), "up": int((d > 0).sum()), "flat": int((d == 0).sum()), "mean_d": float(d.mean()),
            "p_across": float(sstats.ttest_1samp(d, 0.0).pvalue) if len(d) > 2 and d.std() > 0 else np.nan}


timing_rows = []
if len(au):
    timing_rows.append(("Alarming update: urgency moved up at the update", timing_test(au, au.moved)))
    timing_rows.append(("Alarming update: more urgent than the first answer, after the update", timing_test(au, au.above_first)))
gd = upd[(upd.kind == "discordant_dx") & upd.dx_leading.notna()]
if len(gd):
    timing_rows.append(("Diagnosis update: new diagnosis given", timing_test(gd, gd.dx_leading == "post")))
gr = upd[upd.kind == "discordant_reassure"]
if len(gr):
    timing_rows.append(("Reassuring update: urgency moved down", timing_test(gr, gr.urgency_direction == "less_urgent")))
if timing_rows:
    body = "".join(
        f"<tr><td>{html.escape(lab)}</td><td>{r['n']:,}</td><td>{pct(r['first'])}</td><td>{pct(r['last'])}</td>"
        f"<td>{pts(r['slope9'])}</td><td>{fmt_p(r['p_within'])}</td><td>{r['down']} down, {r['up']} up, {r['flat']} flat</td>"
        f"<td>{pts(r['mean_d'])}</td><td>{fmt_p(r['p_across'])}</td></tr>" for lab, r in timing_rows)
    EXTRA.setdefault(SEC3, []).append(
        "<h3>Is the effect of timing more than chance?</h3><table><thead><tr><th>Outcome at the reply after the update</th><th>Conversations</th>"
        "<th>Update after reply 1</th><th>Update after reply 10</th><th>Trend over nine noise turns (points)</th>"
        "<th>p, within these vignettes</th><th>Vignettes: late minus early</th><th>Mean difference across vignettes (points)</th>"
        "<th>p, across vignettes</th></tr></thead><tbody>" + body + "</tbody></table>"
        "<p><b>Two tests, two questions.</b> The first p-value asks whether timing matters in these conversations: the timings are "
        "shuffled 2,000 times within each vignette, language, speaker and noise type, and the linear trend is compared with the "
        "shuffled ones. The second asks whether the effect would carry over to new vignettes: each vignette gives one number "
        "(uptake after reply 10 minus uptake after reply 1) and a t-test asks whether their mean differs from zero. No correction "
        "for multiple tests has been applied.</p>")

# ---------------------------------------------------------------- tests: language and speaker, vignette by vignette
def contrast(frame, col, mask_a, mask_b):
    a = frame[mask_a].groupby("vignette")[col].apply(lambda s: s.astype(float).mean())
    b = frame[mask_b].groupby("vignette")[col].apply(lambda s: s.astype(float).mean())
    d = (a - b).dropna()
    if not len(d):
        return None
    mean = float(d.mean())
    return {"a": float(a.mean()), "b": float(b.mean()), "mean": mean, "same": int((np.sign(d) == np.sign(mean)).sum()), "n": len(d),
            "p": float(sstats.ttest_1samp(d, 0.0).pvalue) if len(d) > 2 and d.std() > 0 else np.nan}


nz_d = nz[nz.dx_moved.notna()]
dn, dnd = nz[nz.noise_type == "direct"], nz_d[nz_d.noise_type == "direct"]
clin = ["nurse", "consultant"]
crows = [("Urgency changed after noise", "Direct noise", "Non-direct noise", contrast(nz, "u_changed", nz.noise_type == "direct", nz.noise_type == "nondirect")),
         ("Diagnosis changed after noise", "Direct noise", "Non-direct noise", contrast(nz_d, "dx_moved", nz_d.noise_type == "direct", nz_d.noise_type == "nondirect")),
         ("Urgency changed after direct noise", "Doctor", "Patient", contrast(dn, "u_changed", dn.perspective == "consultant", dn.perspective == "patient")),
         ("Urgency changed after direct noise", "Nurse", "Patient", contrast(dn, "u_changed", dn.perspective == "nurse", dn.perspective == "patient")),
         ("Urgency changed after direct noise", "Doctor", "Nurse", contrast(dn, "u_changed", dn.perspective == "consultant", dn.perspective == "nurse")),
         ("Urgency changed after direct noise", "Japanese", "English", contrast(dn, "u_changed", dn.language == "ja", dn.language == "en")),
         ("Urgency changed after direct noise", "Chinese", "English", contrast(dn, "u_changed", dn.language == "zh", dn.language == "en")),
         ("Urgency changed after direct noise, nurse or doctor", "Japanese", "English",
          contrast(dn[dn.perspective.isin(clin)], "u_changed", dn[dn.perspective.isin(clin)].language == "ja", dn[dn.perspective.isin(clin)].language == "en")),
         ("Urgency changed after direct noise, patient", "Japanese", "English",
          contrast(dn[dn.perspective == "patient"], "u_changed", dn[dn.perspective == "patient"].language == "ja", dn[dn.perspective == "patient"].language == "en")),
         ("Diagnosis changed after direct noise", "Doctor", "Patient", contrast(dnd, "dx_moved", dnd.perspective == "consultant", dnd.perspective == "patient")),
         ("Diagnosis changed after direct noise", "Japanese", "English", contrast(dnd, "dx_moved", dnd.language == "ja", dnd.language == "en"))]
ua = upd[(upd.kind == "discordant_urgency") & upd.took.notna()]
ud = upd[(upd.kind == "discordant_dx") & upd.took.notna()]
if len(ua):
    crows += [("Alarming update: urgency moved up", "Patient", "Nurse or doctor", contrast(ua, "took", ua.perspective == "patient", ua.perspective.isin(clin))),
              ("Alarming update: urgency moved up", "Japanese", "English", contrast(ua, "took", ua.language == "ja", ua.language == "en"))]
if len(ud):
    crows += [("Diagnosis update: new diagnosis given", "Patient", "Nurse or doctor", contrast(ud, "took", ud.perspective == "patient", ud.perspective.isin(clin))),
              ("Diagnosis update: new diagnosis given", "Japanese", "English", contrast(ud, "took", ud.language == "ja", ud.language == "en")),
              ("Diagnosis update: new diagnosis given", "Chinese", "English", contrast(ud, "took", ud.language == "zh", ud.language == "en"))]
# interaction: is the Japanese-English gap under direct noise wider for clinicians than for the patient?
def gap(frame):
    j = frame[frame.language == "ja"].groupby("vignette").u_changed.mean(); e = frame[frame.language == "en"].groupby("vignette").u_changed.mean()
    return j - e
inter = (gap(dn[dn.perspective.isin(clin)]) - gap(dn[dn.perspective == "patient"])).dropna()
inter_row = ""
if len(inter) > 2 and inter.std() > 0:
    inter_row = (f"<tr><td>Urgency changed after direct noise: is the Japanese minus English gap wider for a nurse or doctor than for a patient?</td>"
                 f"<td colspan='2'>difference between the two gaps</td><td>{pts(float(inter.mean()))}</td>"
                 f"<td>{int((np.sign(inter) == np.sign(inter.mean())).sum())} of {len(inter)}</td><td>{fmt_p(float(sstats.ttest_1samp(inter, 0.0).pvalue))}</td></tr>")
body = "".join(f"<tr><td>{html.escape(o)}</td><td>{html.escape(a)}: {pct(r['a'])}</td><td>{html.escape(b)}: {pct(r['b'])}</td><td>{pts(r['mean'])}</td>"
               f"<td>{r['same']} of {r['n']}</td><td>{fmt_p(r['p'])}</td></tr>" for o, a, b, r in crows if r)
EXTRA.setdefault(SEC4, []).append(
    "<h3>Language and speaker: which differences hold vignette by vignette?</h3><table><thead><tr><th>Outcome</th><th>Group 1</th><th>Group 2</th>"
    "<th>Difference (points)</th><th>Vignettes with the same direction</th><th>p, across vignettes</th></tr></thead><tbody>" + body + inter_row +
    "</tbody></table><p>Each row compares two groups inside every vignette and then asks whether the vignette-by-vignette differences "
    "have a mean different from zero (t-test, the vignette as the unit). Shares are the mean of the per-vignette shares. "
    "No correction for multiple tests has been applied; with this many rows, treat p-values near 0.05 as weak.</p>")


# ---------------------------------------------------------------- the page
unj = int((lt.dx_method.astype(str) == "unjudged").sum())
stage_lines = "".join(f"<li><b>{html.escape(str(s))}</b>: {int(r.conversations):,} conversations, {int(r.vignettes)} vignettes, "
                      f"{int(r.repeats)} repeat(s)</li>" for s, r in blocks.iterrows())
parts = []
for section in (SEC1, SEC2, SEC3, SEC4, SEC5, SEC6):
    figs = [f for f in FIGS if f[1] == section]
    if not figs and section not in EXTRA:
        continue
    parts.append(f"<h2>{html.escape(section)}</h2>")
    for name, _, title, caption in figs:
        b64 = base64.b64encode((OUT / name).read_bytes()).decode()
        parts.append(f'<figure><h3>{html.escape(title)}</h3><img alt="{html.escape(title)}" src="data:image/png;base64,{b64}">'
                     f"<figcaption>{html.escape(caption)}</figcaption></figure>")
    parts.extend(f'<div class="block">{x}</div>' for x in EXTRA.get(section, []))
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
.block {{ background: #fcfcfb; border: 1px solid rgba(11,11,11,0.10); border-radius: 10px; padding: 18px; margin: 18px 0; overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }}
th, td {{ text-align: left; padding: 7px 10px; border-bottom: 1px solid #e1e0d9; vertical-align: top; color: #0b0b0b; }}
th {{ color: #52514e; font-weight: 600; }}
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
