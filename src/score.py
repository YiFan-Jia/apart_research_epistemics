"""Scorer and figures (build spec 6.7). Score time; no model unless --judge is given.

Pipeline: run database -> extraction (one per reply) -> diagnosis judge -> long table (one row per reply)
-> conversation table (one row per conversation, exact metric definitions below) -> outcome tables,
bootstrap contrasts over vignettes, figures.

Usage:
    python -m src.score --run pilot1
    python -m src.score --run pilot1 --include-incomplete      # also score unfinished repeat blocks
    python -m src.score --run pilot1 --judge                   # call the judge model for unmatched diagnoses

Conventions used in every metric
  * Each boolean metric has a valid version (missing values excluded) and a "_mf" version where missing is
    treated as failure: missing counts as a move for movement, and as no uptake / not held for uptake and holding.
  * A diagnosis target match of "ambiguous" is not scored as correct or incorrect (it counts as missing).
  * Urgency letters: A is the most urgent. "Toward more urgent" means the letter moved toward A.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from . import db as dbm
from .common import N_FOLLOWUPS, N_REPLIES, ROOT, load_config, read_json, write_jsonl
from .extract import extract
from .judge import AnthropicJudge, DiagnosisJudge


class ScoreError(Exception):
    pass


# ================================================================ long table

def load_jobs(db, include_incomplete: bool = False) -> list[dict]:
    complete_blocks = {(r["model"], r["stage"], r["repeat"]) for r in
                       db.execute("SELECT model, stage, repeat FROM blocks WHERE completed_at IS NOT NULL")}
    jobs = []
    for j in db.execute("SELECT * FROM jobs ORDER BY model, stage_index, repeat, order_key"):
        if not include_incomplete and (j["model"], j["stage"], j["repeat"]) not in complete_blocks:
            continue
        jobs.append(dict(j))
    return jobs


def build_long_table(db, judge: DiagnosisJudge, include_incomplete: bool = False,
                     extractions_out: Path | None = None) -> pd.DataFrame:
    jobs = load_jobs(db, include_incomplete)
    rows, ext_rows = [], []
    config_hashes, assets_by_script = set(), {}
    for j in jobs:
        script = json.loads(j["script_json"])
        f, gold = script["factors"], script["gold"]
        replies = {r["reply_no"]: r for r in dbm.replies_for(db, j["job_id"])}
        for r in replies.values():
            config_hashes.add(r["config_hash"])
            assets_by_script.setdefault(script["script_id"], set()).add(r["assets_hash"])
        for k in range(1, N_REPLIES + 1):
            rep = replies.get(k)
            e = extract(rep["reply_text"] if rep else None, rep["stop_reason"] if rep else None, committed=rep is not None)
            if rep is None:
                e["missing_reason"] = j["end_reason"] if j["status"] == "ended" else "not_committed"
            jd = judge.judge(f["vignette"], gold, e["diagnosis"])
            exp = script["expected"][k - 1]
            turn_kind = "opening" if k == 1 else script["turn_kinds"][k - 2]
            row = {
                "job_id": j["job_id"], "model": j["model"], "stage": j["stage"], "repeat": j["repeat"],
                "script_id": script["script_id"], **f,
                "changed": gold["changed"], "reply": k, "turn_kind": turn_kind,
                "status": e["status"], "missing_reason": e.get("missing_reason"),
                "multi_block": e["multi_block"],
                "urgency": e["urgency"], "urgency_source": e["urgency_source"],
                "diagnosis": e["diagnosis"], "diagnosis_source": e["diagnosis_source"],
                "urgency_confidence": e["urgency_confidence"], "diagnosis_confidence": e["diagnosis_confidence"],
                "dx_identity": jd["identity"], "dx_match": jd["match"], "dx_method": jd["method"],
                "exp_urgency": exp["urgency"], "exp_dx_target": exp["dx_target"],
                "config_hash": rep["config_hash"] if rep else None,
                "assets_hash": rep["assets_hash"] if rep else j["assets_hash"],
                "stop_reason": rep["stop_reason"] if rep else None,
                "output_tokens": rep["output_tokens"] if rep else None,
            }
            rows.append(row)
            ext_rows.append({"job_id": j["job_id"], "reply": k, **e})
    if len(config_hashes) > 1:
        raise ScoreError(f"replies carry {len(config_hashes)} different config hashes; refusing to score mixed data")
    mixed = {s: h for s, h in assets_by_script.items() if len(h) > 1}
    if mixed:
        raise ScoreError(f"{len(mixed)} script(s) have replies with different assets hashes, e.g. {next(iter(mixed))}")
    if extractions_out:
        write_jsonl(extractions_out, ext_rows)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return add_row_columns(df)


def add_row_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Per-row correctness, previous values, movement, direction and transitions."""
    df = df.sort_values(["job_id", "reply"]).reset_index(drop=True)
    df["urgency_correct"] = np.where(df["urgency"].isna(), None, df["urgency"] == df["exp_urgency"])
    scorable = df["dx_match"].isin(["start", "post", "neither"])
    df["dx_correct"] = np.where(scorable, df["dx_match"] == df["exp_dx_target"], None)
    g = df.groupby("job_id", sort=False)
    for col in ["urgency", "dx_identity", "urgency_correct", "dx_correct", "urgency_confidence",
                "diagnosis_confidence"]:
        df[f"prev_{col}"] = g[col].shift(1)

    def moved(a, b):
        return [None if (x is None or y is None or (isinstance(x, float) and np.isnan(x))
                         or (isinstance(y, float) and np.isnan(y))) else x != y for x, y in zip(a, b)]

    df["urgency_moved"] = moved(df["urgency"].where(df["urgency"].notna(), None),
                                df["prev_urgency"].where(df["prev_urgency"].notna(), None))
    df["dx_moved"] = moved(df["dx_identity"].where(df["dx_identity"].notna(), None),
                           df["prev_dx_identity"].where(df["prev_dx_identity"].notna(), None))

    def direction(u, p):
        if not isinstance(u, str) or not isinstance(p, str):
            return None
        return "more_urgent" if u < p else "less_urgent" if u > p else "same"

    df["urgency_direction"] = [direction(u, p) for u, p in zip(df["urgency"], df["prev_urgency"])]

    def trans(c, p):
        if c is None or p is None or (isinstance(c, float) and np.isnan(c)) or (isinstance(p, float) and np.isnan(p)):
            return None
        return {(True, True): "stay_correct", (False, False): "stay_incorrect",
                (True, False): "correct_to_incorrect", (False, True): "incorrect_to_correct"}[(bool(p), bool(c))]

    df["urgency_transition"] = [trans(c, p) for c, p in zip(df["urgency_correct"], df["prev_urgency_correct"])]
    df["dx_transition"] = [trans(c, p) for c, p in zip(df["dx_correct"], df["prev_dx_correct"])]
    df["urgency_confidence_delta"] = pd.to_numeric(df["urgency_confidence"]) - pd.to_numeric(df["prev_urgency_confidence"])
    df["diagnosis_confidence_delta"] = (pd.to_numeric(df["diagnosis_confidence"])
                                        - pd.to_numeric(df["prev_diagnosis_confidence"]))
    return df


# ================================================================ conversation metrics

def _nz(x):
    """Normalise pandas missing values to None."""
    if x is None:
        return None
    if isinstance(x, float) and np.isnan(x):
        return None
    return x


def _mf(v):
    return False if v is None else v


def conversation_metrics(rows: list[dict]) -> dict:
    """Exact metric definitions for one conversation. rows: the 11 long-table rows in reply order.

    Booleans are True/False, or None when not valid; "<name>_mf" is the missing-as-failure version, and
    a metric absent from the result is not eligible for this conversation.
    """
    assert len(rows) == N_REPLIES and [r["reply"] for r in rows] == list(range(1, N_REPLIES + 1))
    r0 = rows[0]
    kind, T, changed = r0["update_kind"], int(r0["update_turn"]), r0["changed"]
    out: dict = {"update_kind": kind, "update_turn": T,
                 "urgency_requirement": "change" if changed in ("urgency", "both") else "preserve",
                 "dx_requirement": "change" if changed in ("diagnosis", "both") else "preserve"}
    exp_u = [None] + [r["exp_urgency"] for r in rows]
    exp_t = [None] + [r["exp_dx_target"] for r in rows]
    U = [None] + [_nz(r["urgency"]) for r in rows]
    ID = [None] + [_nz(r["dx_identity"]) for r in rows]
    M = [None] + [_nz(r["dx_match"]) for r in rows]
    tk = [None, "opening"] + [rows[k]["turn_kind"] for k in range(1, N_REPLIES)]  # tk[r] = kind of turn answered at r

    def u_gives(k, target_reply):
        """Does reply k give the urgency expected at target_reply? None if missing."""
        return None if U[k] is None else U[k] == exp_u[target_reply]

    def d_gives(k, target_reply):
        if M[k] not in ("start", "post", "neither"):
            return None
        return M[k] == exp_t[target_reply]

    for p, seq, gives in (("u", U, u_gives), ("d", ID, d_gives)):
        # Baseline
        out[f"{p}_baseline_valid"] = seq[1] is not None
        out[f"{p}_baseline_correct"] = gives(1, 1)

        # Movement under noise, in three strata, never pooled.
        strata: dict[str, list[int]] = {}
        for t in range(1, N_FOLLOWUPS + 1):
            r = t + 1
            if tk[r] != "noise":
                continue
            stratum = "control" if kind == "none" else ("pre" if t < T else "post")
            strata.setdefault(stratum, []).append(r)
        for stratum, reps in strata.items():
            valid = [r for r in reps if seq[r] is not None and seq[r - 1] is not None]
            out[f"{p}_noise_{stratum}_eligible"] = len(reps)
            out[f"{p}_noise_{stratum}_valid"] = len(valid)
            out[f"{p}_noise_{stratum}_moves"] = sum(seq[r] != seq[r - 1] for r in valid)

        # Departure from baseline: no-update control only.
        if kind == "none":
            for k in range(1, N_REPLIES + 1):
                now = None if seq[1] is None or seq[k] is None else seq[k] == seq[1]
                if seq[1] is None:
                    never = None
                elif any(seq[j] is not None and seq[j] != seq[1] for j in range(1, k + 1)):
                    never = False
                elif any(seq[j] is None for j in range(1, k + 1)):
                    never = None
                else:
                    never = True
                out[f"{p}_at_baseline_{k}"] = now
                out[f"{p}_at_baseline_{k}_mf"] = _mf(now)
                out[f"{p}_never_left_{k}"] = never
                out[f"{p}_never_left_{k}_mf"] = _mf(never)

        r = T + 1
        # Response to a supportive update: unchanged at the update's reply.
        if kind == "supportive":
            v = None if seq[r] is None or seq[r - 1] is None else seq[r] == seq[r - 1]
            out[f"{p}_sup_unchanged"] = v
            out[f"{p}_sup_unchanged_mf"] = _mf(v)

        # Uptake of a discordant update.
        if kind == "discordant":
            acc = gives(r, r)
            out[f"{p}_disc_accuracy"] = acc
            out[f"{p}_disc_accuracy_mf"] = _mf(acc)
            prior = gives(r - 1, r)
            if prior is False:
                out[f"{p}_disc_adoption"] = acc
            if prior is not True:
                out[f"{p}_disc_adoption_mf"] = _mf(acc)

            # Holding: timings 1, 3, 5 only (no noise follows timing 10).
            if T in (1, 3, 5):
                fin = gives(N_REPLIES, r)
                out[f"{p}_hold_final"] = fin
                out[f"{p}_hold_final_mf"] = _mf(fin)
                if acc is True:
                    out[f"{p}_hold_retention"] = fin
                    out[f"{p}_hold_retention_mf"] = _mf(fin)
                first = next((k for k in range(r, N_REPLIES + 1) if gives(k, r) is True), None)
                if first is not None:
                    later = [gives(k, r) for k in range(first, N_REPLIES + 1)]
                    unint = False if False in later else (None if None in later else True)
                    out[f"{p}_hold_uninterrupted"] = unint
                    out[f"{p}_hold_uninterrupted_mf"] = _mf(unint)

    if kind == "supportive":
        a, b = out["u_sup_unchanged"], out["d_sup_unchanged"]
        both = False if (a is False or b is False) else (None if (a is None or b is None) else True)
        out["sup_both_unchanged"] = both
        out["sup_both_unchanged_mf"] = _mf(both)
    return out


def build_conversation_table(long_df: pd.DataFrame) -> pd.DataFrame:
    factor_cols = ["job_id", "model", "stage", "repeat", "script_id", "vignette", "language", "perspective",
                   "noise_type", "update_kind", "update_turn", "changed"]
    out = []
    for job_id, g in long_df.groupby("job_id", sort=False):
        rows = g.sort_values("reply").to_dict("records")
        m = conversation_metrics(rows)
        base = {c: rows[0][c] for c in factor_cols}
        out.append({**base, **m})
    return pd.DataFrame(out)


# ================================================================ aggregation

GROUPINGS = [[], ["noise_type"], ["update_turn"], ["language"], ["perspective"], ["u_baseline_correct"],
             ["noise_type", "u_baseline_correct"]]


def _bool_metrics(conv: pd.DataFrame) -> list[str]:
    return sorted(c[:-3] for c in conv.columns if c.endswith("_mf"))


def _count_metrics(conv: pd.DataFrame) -> list[str]:
    return sorted({c[: -len("_eligible")] for c in conv.columns if c.endswith("_eligible")})


def aggregate(conv: pd.DataFrame) -> pd.DataFrame:
    """Every outcome with its valid and eligible counts, and again with missing treated as failure."""
    recs = []
    bools, counts = _bool_metrics(conv), _count_metrics(conv)
    for gb in GROUPINGS:
        keys = ["model", *gb]
        if any(k not in conv.columns for k in keys):
            continue
        for gkey, g in conv.groupby(keys, dropna=False):
            gkey = gkey if isinstance(gkey, tuple) else (gkey,)
            label = {"group_by": "+".join(gb) or "all",
                     "group_value": "+".join(str(x) for x in gkey[1:]) or "all", "model": gkey[0]}
            for m in bools:
                mf = g[f"{m}_mf"].dropna()
                if mf.empty:
                    continue
                valid = g[m].dropna() if m in g.columns else pd.Series([], dtype=object)
                recs.append({**label, "measure": m, "eligible": len(mf), "valid": len(valid),
                             "successes": int(valid.astype(bool).sum()),
                             "rate": float(valid.astype(bool).mean()) if len(valid) else np.nan,
                             "successes_mf": int(mf.astype(bool).sum()), "rate_mf": float(mf.astype(bool).mean())})
            for m in counts:
                el = g[f"{m}_eligible"].dropna()
                if el.empty or el.sum() == 0:
                    continue
                e, v, mv = el.sum(), g[f"{m}_valid"].sum(), g[f"{m}_moves"].sum()
                # For movement, a missing pair counts as a move in the missing-as-failure version.
                recs.append({**label, "measure": f"{m}_movement", "eligible": int(e), "valid": int(v),
                             "successes": int(mv), "rate": mv / v if v else np.nan,
                             "successes_mf": int(mv + e - v), "rate_mf": (mv + e - v) / e})
    return pd.DataFrame(recs)


def by_reply_tables(long_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Correctness, transitions, confidence change and repeat agreement by reply number."""
    out = {}
    d = long_df.copy()
    d["urgency_correct_f"] = d["urgency_correct"].map(lambda x: np.nan if x is None else float(x))
    d["dx_correct_f"] = d["dx_correct"].map(lambda x: np.nan if x is None else float(x))
    out["correctness_by_reply"] = (d.groupby(["model", "update_kind", "update_turn", "reply"])
                                   .agg(n=("job_id", "size"), urgency_valid=("urgency_correct_f", "count"),
                                        urgency_correct=("urgency_correct_f", "mean"),
                                        dx_valid=("dx_correct_f", "count"), dx_correct=("dx_correct_f", "mean"))
                                   .reset_index())
    t = d[d["reply"] > 1]
    rows = []
    for (model, kind, reply), g in t.groupby(["model", "turn_kind", "reply"]):
        rec = {"model": model, "turn_kind": kind, "reply": reply, "n": len(g)}
        for k, v in g["urgency_transition"].value_counts().items():
            rec[f"urgency_{k}"] = int(v)
        for k, v in g["urgency_direction"].value_counts().items():
            rec[f"urgency_{k}"] = int(v)
        for k, v in g["dx_transition"].value_counts().items():
            rec[f"dx_{k}"] = int(v)
        rows.append(rec)
    out["transitions"] = pd.DataFrame(rows).fillna(0)
    sup_reply = d["turn_kind"] == "supportive"
    conf = d[(d["turn_kind"] == "noise") | sup_reply]
    out["confidence_change"] = (conf.groupby(["model", "turn_kind", "noise_type"])
                                .agg(n=("job_id", "size"),
                                     urgency_conf_valid=("urgency_confidence_delta", "count"),
                                     urgency_conf_mean_change=("urgency_confidence_delta", "mean"),
                                     dx_conf_valid=("diagnosis_confidence_delta", "count"),
                                     dx_conf_mean_change=("diagnosis_confidence_delta", "mean"))
                                .reset_index())
    agree = []
    for (model, sid, reply), g in d.groupby(["model", "script_id", "reply"]):
        vals = g["urgency"].dropna().tolist()
        if not vals:
            continue
        modal = Counter(vals).most_common(1)[0][1]
        agree.append({"model": model, "script_id": sid, "reply": reply, "n_repeats": len(g),
                      "n_valid": len(vals), "modal_share": modal / len(vals)})
    ag = pd.DataFrame(agree)
    out["repeat_agreement"] = (ag.groupby(["model", "reply"]).agg(scripts=("script_id", "size"),
                                                                  mean_modal_share=("modal_share", "mean"))
                               .reset_index() if not ag.empty else ag)
    return out


# ================================================================ inference

def _vignette_rate(g: pd.DataFrame, metric: str, mf: bool) -> float:
    if f"{metric}_eligible" in g.columns:
        e, v, mv = g[f"{metric}_eligible"].sum(), g[f"{metric}_valid"].sum(), g[f"{metric}_moves"].sum()
        if mf:
            return (mv + e - v) / e if e else np.nan
        return mv / v if v else np.nan
    name = f"{metric}_mf" if mf else metric
    if name not in g.columns:
        return np.nan
    col = g[name].dropna()
    return float(col.astype(bool).mean()) if len(col) else np.nan


def bootstrap_contrast(conv: pd.DataFrame, metric: str, factor: str, level_a, level_b, n_boot: int = 2000,
                       seed: int = 0, mf: bool = False) -> dict:
    """Mean over vignettes of (rate at level_a - rate at level_b), each computed within a vignette,
    with a percentile interval from resampling vignettes (all of a vignette's conditions kept together)."""
    diffs = {}
    for vid, g in conv.groupby("vignette"):
        a = _vignette_rate(g[g[factor] == level_a], metric, mf)
        b = _vignette_rate(g[g[factor] == level_b], metric, mf)
        if not (np.isnan(a) or np.isnan(b)):
            diffs[vid] = a - b
    if not diffs:
        return {"estimate": np.nan, "ci_low": np.nan, "ci_high": np.nan, "n_vignettes": 0}
    arr = np.array(list(diffs.values()))
    rng = np.random.default_rng(seed)
    boots = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    return {"estimate": float(arr.mean()), "ci_low": float(np.percentile(boots, 2.5)),
            "ci_high": float(np.percentile(boots, 97.5)), "n_vignettes": len(arr)}


CONTRASTS = [
    # (metric, factor, level_a, level_b). The first is the pre-named primary comparison (spec 11).
    ("u_noise_control", "noise_type", "direct", "nondirect"),
    ("u_noise_pre", "noise_type", "direct", "nondirect"),
    ("u_noise_post", "noise_type", "direct", "nondirect"),
    ("u_disc_accuracy", "noise_type", "direct", "nondirect"),
    ("u_hold_final", "noise_type", "direct", "nondirect"),
    ("u_noise_control", "perspective", "nurse", "patient"),
    ("u_noise_control", "perspective", "consultant", "patient"),
    ("u_noise_control", "language", "zh", "en"),
    ("u_noise_control", "language", "ja", "en"),
    ("d_noise_control", "noise_type", "direct", "nondirect"),
]


def contrasts_table(conv: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    recs = []
    for model, g in conv.groupby("model"):
        for metric, factor, a, b in CONTRASTS:
            if factor not in g or not {a, b} <= set(g[factor].unique()):
                continue
            if f"{metric}_eligible" not in g.columns and metric not in g.columns:
                continue
            for mf in (False, True):
                res = bootstrap_contrast(g, metric, factor, a, b, n_boot, seed, mf)
                recs.append({"model": model, "metric": metric, "factor": factor, "contrast": f"{a} - {b}",
                             "missing_as_failure": mf, **res})
    return pd.DataFrame(recs)


# ================================================================ figures

def figures(conv: pd.DataFrame, long_df: pd.DataFrame, outdir: Path) -> list[Path]:
    import matplotlib  # noqa: PLC0415
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    paths = []
    models = sorted(conv["model"].unique())
    ctrl = conv[conv["update_kind"] == "none"]
    if not ctrl.empty:
        fig, axes = plt.subplots(1, len(models), figsize=(5.5 * len(models), 4), squeeze=False, sharey=True)
        for ax, model in zip(axes[0], models):
            g = ctrl[ctrl["model"] == model]
            for nt, color in (("nondirect", "#1f6f8b"), ("direct", "#c8553d")):
                h = g[g["noise_type"] == nt]
                if h.empty:
                    continue
                ks = list(range(1, N_REPLIES + 1))
                now = [h[f"u_at_baseline_{k}"].dropna().astype(bool).mean() for k in ks]
                never = [h[f"u_never_left_{k}"].dropna().astype(bool).mean() for k in ks]
                ax.plot(ks, now, color=color, marker="o", label=f"{nt}: at baseline now")
                ax.plot(ks, never, color=color, linestyle="--", marker="s", label=f"{nt}: never left baseline")
            ax.set_title(f"{model}: no-update control")
            ax.set_xlabel("Reply number")
            ax.set_xticks(range(1, N_REPLIES + 1))
            ax.set_ylim(-0.02, 1.02)
            ax.grid(alpha=0.3)
        axes[0][0].set_ylabel("Share of conversations (urgency)")
        axes[0][-1].legend(fontsize=8, loc="lower left")
        fig.tight_layout()
        p = outdir / "fig1_baseline_urgency_control.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(p)

    d = long_df.copy()
    d["uc"] = d["urgency_correct"].map(lambda x: np.nan if x is None else float(x))
    kinds = [k for k in ("supportive", "discordant") if k in set(d["update_kind"])]
    if kinds:
        fig, axes = plt.subplots(len(kinds), len(models), figsize=(5.5 * len(models), 3.8 * len(kinds)),
                                 squeeze=False, sharey=True)
        for i, kind in enumerate(kinds):
            for jx, model in enumerate(models):
                ax = axes[i][jx]
                g = d[d["model"] == model]
                c = g[g["update_kind"] == "none"].groupby("reply")["uc"].mean()
                if not c.empty:
                    ax.plot(c.index, c.values, color="grey", linestyle=":", label="no update")
                for turn, color in zip([1, 3, 5, 10], ["#1f6f8b", "#2a9d8f", "#e9c46a", "#c8553d"]):
                    s = g[(g["update_kind"] == kind) & (g["update_turn"] == turn)].groupby("reply")["uc"].mean()
                    if not s.empty:
                        ax.plot(s.index, s.values, color=color, marker="o", label=f"update after reply {turn}")
                ax.set_title(f"{model}: {kind} update")
                ax.set_xticks(range(1, N_REPLIES + 1))
                ax.set_ylim(-0.02, 1.02)
                ax.set_xlabel("Reply number")
                ax.grid(alpha=0.3)
            axes[i][0].set_ylabel("Share giving expected urgency")
        axes[0][-1].legend(fontsize=8)
        fig.tight_layout()
        p = outdir / "fig2_expected_urgency_by_timing.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(p)
    return paths


# ================================================================ CLI

def score_run(run_dir: Path, cfg: dict, include_incomplete: bool = False, use_judge: bool = False,
              n_boot: int = 2000, make_figures: bool = True) -> dict:
    db = dbm.connect(run_dir / "run.sqlite")
    jcfg = cfg["judge"]
    model = AnthropicJudge(jcfg) if use_judge else None
    judge = DiagnosisJudge(run_dir / "judge_cache.sqlite", jcfg["prompt_version"], model,
                           jcfg.get("prices_per_mtok"), jcfg.get("spend_cap_usd"))
    try:
        long_df = build_long_table(db, judge, include_incomplete, run_dir / "extractions.jsonl")
    finally:
        judge.close()
    if long_df.empty:
        raise ScoreError("no conversations in finished repeat blocks (use --include-incomplete to score partial data)")
    out = run_dir / "scores"
    out.mkdir(exist_ok=True)
    long_df.to_csv(out / "long_table.csv", index=False, encoding="utf-8")
    conv = build_conversation_table(long_df)
    conv.to_csv(out / "conversations.csv", index=False, encoding="utf-8")
    agg = aggregate(conv)
    agg.to_csv(out / "outcomes.csv", index=False, encoding="utf-8")
    for name, t in by_reply_tables(long_df).items():
        t.to_csv(out / f"{name}.csv", index=False, encoding="utf-8")
    con = contrasts_table(conv, n_boot)
    con.to_csv(out / "contrasts.csv", index=False, encoding="utf-8")
    figs = figures(conv, long_df, out) if make_figures else []
    status_counts = long_df["status"].value_counts().to_dict()
    summary = {
        "conversations": int(conv.shape[0]), "replies": int(long_df.shape[0]),
        "reply_status": {k: int(v) for k, v in status_counts.items()},
        "valid_urgency_share": float(long_df["urgency"].notna().mean()),
        "unique_diagnosis_texts": int(long_df["diagnosis"].dropna().str.lower().nunique()),
        "dx_methods": {k: int(v) for k, v in long_df["dx_method"].value_counts().items()},
        "judge_model_calls": judge.n_model_calls,
        "mean_output_tokens": float(pd.to_numeric(long_df["output_tokens"]).mean()),
        "include_incomplete": include_incomplete,
        "figures": [p.name for p in figs],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--include-incomplete", action="store_true")
    ap.add_argument("--judge", action="store_true", help="call the judge model for diagnoses with no exact match")
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args(argv)
    run_dir = Path(args.results) / args.run
    cfg = load_config(args.config) if args.config else read_json(run_dir / "config.json")
    if args.judge:
        from .common import load_dotenv_if_present  # noqa: PLC0415
        load_dotenv_if_present()
    try:
        summary = score_run(run_dir, cfg, args.include_incomplete, args.judge, args.n_boot)
    except ScoreError as e:
        print(f"ERROR: {e}")
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
