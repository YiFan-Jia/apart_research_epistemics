"""Every number quoted in the report, computed from a scored run's long table (one row per reply).

usage: python report/report_numbers.py <scores folder with long_table.csv> [output json]

Definitions follow src/score.py (movement = urgency differs from the reply before; uptake is read at the
update's own reply; holding uses update timings 1, 3 and 5, which have noise after them). What this file adds:
  - the ten main cases and the three reversal cases are reported separately (the reversal cases are built
    from three of the ten, so they are not extra independent cases);
  - intervals come from resampling the ten main cases (cluster bootstrap, 10,000 draws, percentile), and each
    contrast also gets a per-case sign count, which needs no distributional assumption;
  - noise is compared with the neutral fact and the supportive update at the same reply positions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RANK = {"A": 0, "B": 1, "C": 2, "D": 3}          # smaller = more urgent
PARENT = {"V21": "V02", "V22": "V10", "V23": "V09"}
N_BOOT = 10_000
RNG = np.random.default_rng(20261115)


def frac(k, n):
    k, n = int(k), int(n)
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None}


def load(folder: Path):
    d = pd.read_csv(folder / "long_table.csv", low_memory=False)
    d["u"] = d["urgency"].map(RANK)
    conv = d[d.reply == 1].set_index("job_id")[
        ["stage", "repeat", "vignette", "language", "perspective", "noise_type", "update_kind", "update_turn",
         "exp_urgency"]].copy()
    conv = conv.rename(columns={"exp_urgency": "key_start"})
    U = d.pivot(index="job_id", columns="reply", values="u").reindex(conv.index)
    return d, conv, U


def moves(U, replies):
    """(moved, valid) counts per conversation over the given replies (each compared with the reply before)."""
    cur, prev = U[replies].to_numpy(float), U[[r - 1 for r in replies]].to_numpy(float)
    valid = ~np.isnan(cur) & ~np.isnan(prev)
    moved = valid & (cur != prev)
    up = valid & (cur < prev)
    down = valid & (cur > prev)
    return moved.sum(1), valid.sum(1), up.sum(1), down.sum(1)


def boot_ratio_diff(tab: pd.DataFrame, a: str, b: str | None = None):
    """tab: index vignette, columns (level, 'k'|'n'). Ratio of sums for level a minus level b (or a alone),
    resampling vignettes. Returns estimate, CI and the per-vignette sign count."""
    vigs = tab.index.to_numpy()
    ka, na = tab[(a, "k")].to_numpy(float), tab[(a, "n")].to_numpy(float)
    if b is None:
        est = ka.sum() / na.sum()
        idx = RNG.integers(0, len(vigs), (N_BOOT, len(vigs)))
        bs = ka[idx].sum(1) / na[idx].sum(1)
        lo, hi = np.percentile(bs, [2.5, 97.5])
        return {"pct": round(100 * est, 1), "ci": [round(100 * lo, 1), round(100 * hi, 1)], "cases": len(vigs)}
    kb, nb = tab[(b, "k")].to_numpy(float), tab[(b, "n")].to_numpy(float)
    est = ka.sum() / na.sum() - kb.sum() / nb.sum()
    idx = RNG.integers(0, len(vigs), (N_BOOT, len(vigs)))
    bs = ka[idx].sum(1) / na[idx].sum(1) - kb[idx].sum(1) / nb[idx].sum(1)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    per = ka / na - kb / nb
    return {"diff_pts": round(100 * est, 1), "ci": [round(100 * lo, 1), round(100 * hi, 1)],
            "cases_higher": int((per > 0).sum()), "cases_lower": int((per < 0).sum()),
            "cases_equal": int((per == 0).sum()), "cases": len(vigs)}


def by_level(conv, k, n, factor):
    g = pd.DataFrame({"k": k, "n": n, factor: conv[factor].to_numpy()}, index=conv.index).groupby(factor)[["k", "n"]].sum()
    return {str(lv): frac(r.k, r.n) for lv, r in g.iterrows()}


def vig_tab(conv, k, n, factor):
    t = pd.DataFrame({"k": k, "n": n, "v": conv["vignette"].to_numpy(), "f": conv[factor].to_numpy()})
    return t.groupby(["v", "f"])[["k", "n"]].sum().unstack("f").swaplevel(axis=1)


def main(folder: Path) -> dict:
    d, conv, U = load(folder)
    out: dict = {"source": str(folder).replace("\\", "/")}
    core = conv.stage == "core10"
    rev = conv.stage == "reversal"

    # ---------------------------------------------------------------- size
    out["size"] = {
        "conversations": len(conv), "replies": len(d),
        "main_conversations": int(core.sum()), "reversal_conversations": int(rev.sum()),
        "repeats": sorted(int(x) for x in conv.repeat.unique()),
        "by_stage_repeat": {f"{s}|{r}": int(n) for (s, r), n in conv.groupby(["stage", "repeat"]).size().items()},
        "scripts": int(d.script_id.nunique()),
        "replies_with_readable_form": frac(d.urgency.notna().sum(), len(d)),
        "diagnosis_read": frac((~d.dx_method.isin(["unjudged", "none"])).sum(), len(d)),
        "dx_methods": {k: int(v) for k, v in d.dx_method.value_counts().items()},
        "distinct_diagnosis_strings": int(d.diagnosis.nunique()),
        "mean_output_tokens": round(float(d.output_tokens.mean()), 0),
        "cases_main": sorted(conv[core].vignette.unique()), "cases_reversal": sorted(conv[rev].vignette.unique()),
    }

    # ---------------------------------------------------------------- noise, no-update arm
    ctrl = conv.update_kind == "none"
    R = list(range(2, 12))
    mv, va, up, dn = moves(U, R)
    mv, va, up, dn = (pd.Series(x, index=conv.index) for x in (mv, va, up, dn))
    noise = {}
    for name, sel in (("main", core & ctrl), ("reversal", rev & ctrl), ("all", ctrl)):
        c = conv[sel]
        k, n = mv[sel], va[sel]
        first, last = U.loc[sel, 1], U.loc[sel, 11]
        ever = (U.loc[sel, R].ne(first, axis=0) & U.loc[sel, R].notna()).any(axis=1)
        blk = {
            "conversations": int(sel.sum()),
            "moved": frac(k.sum(), n.sum()),
            "to_more_urgent": int(up[sel].sum()), "to_less_urgent": int(dn[sel].sum()),
            "conversations_ever_left_first_answer": frac(ever[first.notna()].sum(), first.notna().sum()),
            "conversations_ending_off_first_answer": frac((last != first)[first.notna() & last.notna()].sum(),
                                                          (first.notna() & last.notna()).sum()),
            "ended_more_urgent": int((last < first).sum()), "ended_less_urgent": int((last > first).sum()),
            "by_noise_type": by_level(c, k, n, "noise_type"),
            "by_speaker": by_level(c, k, n, "perspective"),
            "by_language": by_level(c, k, n, "language"),
            "by_case": by_level(c, k, n, "vignette"),
        }
        if name == "main":
            c2 = c.assign(one="x")
            blk["moved_ci"] = boot_ratio_diff(vig_tab(c2, k, n, "one"), "x")
            for factor, a, b in (("noise_type", "direct", "nondirect"), ("perspective", "nurse", "patient"),
                                 ("perspective", "consultant", "patient"), ("language", "zh", "en"),
                                 ("language", "ja", "en")):
                blk[f"contrast_{a}_minus_{b}"] = boot_ratio_diff(vig_tab(c, k, n, factor), a, b)
            # noise type crossed with speaker and with language
            for factor in ("perspective", "language"):
                t = pd.DataFrame({"k": k, "n": n, "nt": c.noise_type.to_numpy(), "f": c[factor].to_numpy()})
                g = t.groupby(["nt", "f"])[["k", "n"]].sum()
                blk[f"by_noise_type_and_{factor}"] = {f"{a}|{b}": frac(r.k, r.n) for (a, b), r in g.iterrows()}
                for nt in ("direct", "nondirect"):
                    m = (c.noise_type == nt).to_numpy()
                    levels = (("nurse", "patient"), ("consultant", "patient")) if factor == "perspective" else (("zh", "en"), ("ja", "en"))
                    for a, b in levels:
                        blk[f"contrast_{a}_minus_{b}_within_{nt}"] = boot_ratio_diff(vig_tab(c[m], k[m], n[m], factor), a, b)
            # by reply position
            cur, prev = U.loc[sel, R].to_numpy(float), U.loc[sel, [r - 1 for r in R]].to_numpy(float)
            ok = ~np.isnan(cur) & ~np.isnan(prev)
            blk["by_reply"] = {str(r): frac(((cur != prev) & ok)[:, i].sum(), ok[:, i].sum()) for i, r in enumerate(R)}
            # by whether the first answer matched the key
            start_rel = np.sign(first - c.key_start.map(RANK))      # <0: model more urgent than the key
            blk["by_first_answer_vs_key"] = {}
            for lab, s in (("model_more_urgent", -1), ("same", 0), ("model_less_urgent", 1)):
                m = (start_rel == s).to_numpy()
                blk["by_first_answer_vs_key"][lab] = {
                    "conversations": int(m.sum()), "moved": frac(k[m].sum(), n[m].sum()),
                    "to_more_urgent": int(up[sel][m].sum()), "to_less_urgent": int(dn[sel][m].sum())}
        noise[name] = blk
    out["noise_no_update"] = noise

    # all noise replies in every arm
    nz = d[d.turn_kind == "noise"]
    out["noise_all_arms"] = {
        s: {"replies": int(len(g)), "moved": frac((g.urgency_moved == True).sum(), g.urgency_moved.notna().sum()),  # noqa: E712
            "to_more_urgent": int((g.urgency_direction == "more_urgent").sum()),
            "to_less_urgent": int((g.urgency_direction == "less_urgent").sum())}
        for s, g in (("main", nz[nz.stage == "core10"]), ("reversal", nz[nz.stage == "reversal"]), ("all", nz))}

    # ---------------------------------------------------------------- the update's own reply, every arm
    def at_update(sel):
        c = conv[sel]
        r = (c.update_turn + 1).to_numpy()
        Un = U.loc[sel].to_numpy(float)
        cur = Un[np.arange(len(c)), r - 1]
        prev = Un[np.arange(len(c)), r - 2]
        last = Un[:, 10]
        return c, cur, prev, last

    def upd_block(sel, key_after=None):
        c, cur, prev, last = at_update(sel)
        ok = ~np.isnan(cur) & ~np.isnan(prev)
        b = {"conversations": int(len(c)), "unchanged": frac((cur == prev)[ok].sum(), ok.sum()),
             "more_urgent": frac((cur < prev)[ok].sum(), ok.sum()), "less_urgent": frac((cur > prev)[ok].sum(), ok.sum())}
        return b, c, cur, prev, last, ok

    upd = {}
    for name, stage_sel in (("main", core), ("reversal", rev)):
        blk = {}
        for kind in ("neutral", "supportive", "discordant_urgency", "discordant_dx", "discordant_reassure"):
            sel = stage_sel & (conv.update_kind == kind)
            if not sel.any():
                continue
            b, c, cur, prev, last, ok = upd_block(sel)
            b["by_timing"] = {}
            for t in (1, 3, 5, 10):
                m = (c.update_turn == t).to_numpy() & ok
                b["by_timing"][str(t)] = {"unchanged": frac((cur == prev)[m].sum(), m.sum()),
                                          "more_urgent": frac((cur < prev)[m].sum(), m.sum()),
                                          "less_urgent": frac((cur > prev)[m].sum(), m.sum())}
            for factor in ("language", "perspective", "noise_type", "vignette"):
                b[f"by_{factor}"] = {}
                for lv in sorted(c[factor].unique()):
                    m = (c[factor] == lv).to_numpy() & ok
                    b[f"by_{factor}"][str(lv)] = {"unchanged": frac((cur == prev)[m].sum(), m.sum()),
                                                 "more_urgent": frac((cur < prev)[m].sum(), m.sum()),
                                                 "less_urgent": frac((cur > prev)[m].sum(), m.sum())}
            if kind.startswith("discordant"):
                dd = d[d.job_id.isin(c.index)]
                r = (c.update_turn + 1)
                at = dd.merge(r.rename("r"), left_on="job_id", right_index=True)
                at = at[at.reply == at.r].set_index("job_id").reindex(c.index)
                key = at.exp_urgency.map(RANK).to_numpy(float)
                b["key_level_after_update"] = {str(k): int(v) for k, v in at.exp_urgency.value_counts().items()}
                b["on_key_level"] = frac((cur == key)[~np.isnan(cur)].sum(), (~np.isnan(cur)).sum())
                b["more_urgent_than_key"] = frac((cur < key)[~np.isnan(cur)].sum(), (~np.isnan(cur)).sum())
                b["less_urgent_than_key"] = frac((cur > key)[~np.isnan(cur)].sum(), (~np.isnan(cur)).sum())
                b["level_given"] = {lv: int((cur == RANK[lv]).sum()) for lv in "ABCD"}
                b["level_before"] = {lv: int((prev == RANK[lv]).sum()) for lv in "ABCD"}
                if kind == "discordant_dx":
                    judged = at.dx_key.notna() & (at.dx_key != "none")
                    b["diagnosis_read_at_update"] = frac(at.dx_key.notna().sum(), len(at))
                    b["diagnosis_is_new_one"] = frac((at.dx_key == "post").sum(), at.dx_key.notna().sum())
                    b["diagnosis_still_first"] = frac((at.dx_key == "start").sum(), at.dx_key.notna().sum())
                # holding: moved in the warranted direction at the update (timings 1, 3, 5), same level at reply 11
                want_up = kind != "discordant_reassure"
                took = ok & ((cur < prev) if want_up else (cur > prev)) & (c.update_turn != 10).to_numpy()
                lastok = took & ~np.isnan(last)
                b["held_to_end_after_moving"] = frac((last == cur)[lastok].sum(), lastok.sum())
                b["reverted_towards_before"] = frac(((last > cur) if want_up else (last < cur))[lastok].sum(), lastok.sum())
                b["went_further"] = frac(((last < cur) if want_up else (last > cur))[lastok].sum(), lastok.sum())
                if kind == "discordant_urgency":
                    for factor in ("noise_type", "perspective", "language"):
                        b[f"held_by_{factor}"] = {}
                        for lv in sorted(c[factor].unique()):
                            m = lastok & (c[factor] == lv).to_numpy()
                            b[f"held_by_{factor}"][str(lv)] = frac((last == cur)[m].sum(), m.sum())
            blk[kind] = b
        # noise at the same reply positions (2, 4, 6, 11), no-update arm
        sel = stage_sel & ctrl
        m4, v4, u4, d4 = moves(U.loc[sel], [2, 4, 6, 11])
        blk["noise_same_positions"] = {"unchanged": frac(v4.sum() - m4.sum(), v4.sum()),
                                       "more_urgent": frac(u4.sum(), v4.sum()), "less_urgent": frac(d4.sum(), v4.sum())}
        upd[name] = blk
    out["at_update"] = upd

    # per-case comparison: noise against the neutral fact at the same positions (main cases)
    rows = {}
    for v in sorted(conv[core].vignette.unique()):
        s = core & ctrl & (conv.vignette == v)
        m4, v4, _, _ = moves(U.loc[s], [2, 4, 6, 11])
        s2 = core & (conv.update_kind == "neutral") & (conv.vignette == v)
        _, cur, prev, _ = at_update(s2)
        ok = ~np.isnan(cur) & ~np.isnan(prev)
        rows[v] = {"noise_moved": m4.sum() / v4.sum(), "neutral_moved": (cur != prev)[ok].sum() / ok.sum()}
    t = pd.DataFrame(rows).T
    out["noise_vs_neutral_same_positions_by_case"] = {
        "cases_noise_higher": int((t.noise_moved > t.neutral_moved).sum()),
        "cases_noise_lower": int((t.noise_moved < t.neutral_moved).sum()),
        "cases_equal": int((t.noise_moved == t.neutral_moved).sum()),
        "per_case_pct": {v: [round(100 * r.noise_moved, 1), round(100 * r.neutral_moved, 1)] for v, r in t.iterrows()}}

    # ---------------------------------------------------------------- first answer against the key
    first = d[d.reply == 1]
    base = {}
    for name, g in (("main", first[first.stage == "core10"]), ("reversal", first[first.stage == "reversal"])):
        u, key = g.urgency.map(RANK), g.exp_urgency.map(RANK)
        ok = u.notna()
        dxok = g.dx_key.notna()
        base[name] = {
            "urgency_matches_key": frac((u == key)[ok].sum(), ok.sum()),
            "model_more_urgent": frac((u < key)[ok].sum(), ok.sum()),
            "model_less_urgent": frac((u > key)[ok].sum(), ok.sum()),
            "diagnosis_matches_key": frac((g.dx_key == "start")[dxok].sum(), dxok.sum()),
            "by_case": {v: {"key": gg.exp_urgency.iloc[0], "first_diagnosis": gg.start_dx.iloc[0],
                            "levels_given": {lv: int((gg.urgency == lv).sum()) for lv in "ABCD"},
                            "matches_key": frac((gg.urgency == gg.exp_urgency).sum(), gg.urgency.notna().sum())}
                        for v, gg in g.groupby("vignette")},
            "by_language": {lv: frac((gg.urgency == gg.exp_urgency).sum(), gg.urgency.notna().sum())
                            for lv, gg in g.groupby("language")},
            "by_speaker": {lv: frac((gg.urgency == gg.exp_urgency).sum(), gg.urgency.notna().sum())
                           for lv, gg in g.groupby("perspective")},
            "mean_level_by_language": {lv: round(float(gg.urgency.map(RANK).mean()), 2) for lv, gg in g.groupby("language")},
            "mean_level_by_speaker": {lv: round(float(gg.urgency.map(RANK).mean()), 2) for lv, gg in g.groupby("perspective")},
        }
    out["first_answer"] = base

    # ---------------------------------------------------------------- reversal cases beside their parents
    pair = {}
    for child, parent in PARENT.items():
        e = {"parent": parent}
        for kind, lab in (("discordant_urgency", "alarming"), ("discordant_reassure", "reassuring")):
            sel = (conv.vignette == child) & (conv.update_kind == kind)
            c, cur, prev, last = at_update(sel)
            ok = ~np.isnan(cur) & ~np.isnan(prev)
            e[lab] = {"more_urgent": frac((cur < prev)[ok].sum(), ok.sum()), "less_urgent": frac((cur > prev)[ok].sum(), ok.sum()),
                      "unchanged": frac((cur == prev)[ok].sum(), ok.sum()),
                      "level_before": {lv: int((prev == RANK[lv]).sum()) for lv in "ABCD"},
                      "level_after": {lv: int((cur == RANK[lv]).sum()) for lv in "ABCD"}}
        g = first[first.vignette == child]
        e["first_levels"] = {lv: int((g.urgency == lv).sum()) for lv in "ABCD"}
        e["key_start"] = g.exp_urgency.iloc[0]
        pair[child] = e
    out["reversal_pairs"] = pair

    # ---------------------------------------------------------------- confidence and hedging (exploratory)
    conf = {}
    for name, g in (("main", d[d.stage == "core10"]), ("all", d)):
        e = {}
        for tk, gg in g[g.reply > 1].groupby("turn_kind"):
            for nt, g3 in gg.groupby("noise_type"):
                e[f"{tk}|{nt}"] = {"urgency_conf_change": round(float(g3.urgency_confidence_delta.mean()), 2),
                                   "dx_conf_change": round(float(g3.diagnosis_confidence_delta.mean()), 2),
                                   "n": int(g3.urgency_confidence_delta.notna().sum())}
        c = g[g.update_kind == "none"]
        e["no_update_mean_conf_by_reply"] = {
            nt: {str(r): [round(float(x.urgency_confidence.mean()), 1), round(float(x.diagnosis_confidence.mean()), 1)]
                 for r, x in gg.groupby("reply") if r in (1, 6, 11)} for nt, gg in c.groupby("noise_type")}
        hed = c[c.dx_hedged.notna()]
        e["no_update_share_hedged_by_reply"] = {
            nt: {str(r): frac((x.dx_hedged == True).sum(), len(x)) for r, x in gg.groupby("reply") if r in (1, 6, 11)}  # noqa: E712
            for nt, gg in hed.groupby("noise_type")}
        dm = c[(c.reply > 1) & c.dx_moved.notna()]
        e["no_update_leading_dx_changed"] = {nt: frac((gg.dx_moved == True).sum(), len(gg))  # noqa: E712
                                             for nt, gg in dm.groupby("noise_type")}
        # among conversations whose urgency never moved, change in stated urgency confidence from reply 1 to 11
        w = c.pivot(index="job_id", columns="reply", values="urgency")
        still = w.eq(w[1], axis=0).all(axis=1)
        cw = c.pivot(index="job_id", columns="reply", values="urgency_confidence")
        e["urgency_never_moved_conf_first_to_last"] = {
            "conversations": int(still.sum()), "mean_first": round(float(cw.loc[still, 1].mean()), 1),
            "mean_last": round(float(cw.loc[still, 11].mean()), 1)}
        conf[name] = e
    out["confidence_hedging"] = conf
    return out


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    res = main(folder)
    text = json.dumps(res, indent=1, ensure_ascii=False)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text, encoding="utf-8")
        print(f"written {sys.argv[2]}")
    else:
        print(text)
