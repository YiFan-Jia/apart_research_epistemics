"""Scorer and figures (build spec 6.7; scorer version 2, 15 Nov). Score time; no model unless --judge is given.

Pipeline: run database -> extraction (one per reply) -> diagnosis judge -> long table (one row per reply)
-> conversation table (one row per conversation, exact metric definitions below) -> outcome tables,
bootstrap contrasts over vignettes, checks, figures.

Usage:
    python -m src.score --run main                        # writes results/main/scores/s2/  
    python -m src.score --run main --judge                # call the judge model for unmatched diagnoses
    python -m src.score --run main --include-incomplete   # also score unfinished repeat blocks
    python -m src.score --run v01_en_full --judge --keys corrected_vignettes.json --label s2-keys-b
                                                          # same transcripts, corrected reference answers

Outputs are versioned. Each scoring goes to results/<run>/scores/<label>/ with a scoring_manifest.json that
records the scorer version, the judge, the reference answers used and the reviewed diagnosis mappings. A
label is never overwritten by a scoring with different inputs; results written by scorer version 1 sit
directly in results/<run>/scores/ and are left alone.

Conventions used in every metric
  * Each boolean metric has a valid version (missing values excluded) and a "_mf" version where missing is
    treated as failure: missing counts as a move for movement, and as no uptake / not held for uptake and holding.
  * Diagnosis is read by the judge into a leading diagnosis, modifiers, alternatives and stated doubt (src/judge.py).
    Movement is measured on the leading diagnosis: relabelling within the accepted names, an added modifier or an
    added differential is not a move. Hedging (doubt, alternatives, or no single leading diagnosis) is its own outcome.
  * A diagnosis match of "ambiguous" (a broader term covering both reference diagnoses) is not scored as correct
    or incorrect (it counts as missing). "none" (no single leading diagnosis) is scored as incorrect.
  * Which urgency letter is most urgent comes from the run's config, urgency_most_urgent_first.
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
from .common import (
    DISCORDANT_KINDS, KIND_LABELS, N_FOLLOWUPS, N_REPLIES, ROOT, STABLE_KINDS, UPDATE_TURNS, code_version,
    is_discordant,
    load_config, read_json, sha, urgency_rank, write_json, write_jsonl,
)
from .extract import extract, prose_levels
from .judge import SCORABLE_MATCHES, AnthropicJudge, DiagnosisJudge, load_reviewed, norm_dx, write_review_sheet
from .scripts import gold_and_expected, key_version

SCORER_VERSION = "2"
MIN_VIGNETTES_FOR_CI = 2        # below this a bootstrap over vignettes has nothing to resample
FEW_VIGNETTES = 5               # below this the interval is reported but marked unstable
KEY_MISMATCH_SHARE = 0.5        # warn when fewer than this share of answers match the reference answer


class ScoreError(Exception):
    pass


# ================================================================ reference answers

def load_keys(path: Path | str | None) -> dict[str, dict]:
    """Vignette records from a vignettes file, by id, for rescoring against corrected reference answers."""
    if not path:
        return {}
    data = read_json(path)
    recs = data["vignettes"] if isinstance(data, dict) else data
    return {v["id"]: v for v in recs}


def apply_key(script: dict, keys: dict[str, dict], run_scale: str | None) -> tuple[dict, list[dict], str]:
    """(gold, expected, source) for a script: its frozen answers, or the override record for its vignette."""
    vid = script["factors"]["vignette"]
    v = keys.get(vid)
    if v is None:
        return script["gold"], script["expected"], "frozen"
    if v.get("urgency_scale_version") != run_scale:
        raise ScoreError(f"{vid}: the reference answers given are on urgency scale "
                         f"{v.get('urgency_scale_version')!r} but this run's replies used scale {run_scale!r}; "
                         f"urgency letters cannot be compared across scales")
    gold, expected = gold_and_expected(v, script["factors"]["update_kind"], script["factors"]["update_turn"])
    return gold, expected, "override"


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


def _has_thinking(content_json: str | None) -> bool | None:
    try:
        blocks = json.loads(content_json or "[]")
    except (TypeError, ValueError):
        return None
    return any(b.get("type") in ("thinking", "redacted_thinking") for b in blocks)


def diagnosis_items(db, include_incomplete: bool = False, keys: dict[str, dict] | None = None,
                    run_scale: str | None = None) -> list[tuple[str, dict, str | None]]:
    """(vignette, reference answers, diagnosis text) for every reply of the run: what the judge is asked to read."""
    items = []
    for j in load_jobs(db, include_incomplete):
        script = json.loads(j["script_json"])
        gold, _, _ = apply_key(script, keys or {}, run_scale)
        for rep in dbm.replies_for(db, j["job_id"]):
            e = extract(rep["reply_text"], rep["stop_reason"], committed=True)
            items.append((script["factors"]["vignette"], gold, e["diagnosis"]))
    return items


def build_long_table(db, judge: DiagnosisJudge, urgency_order: list[str], include_incomplete: bool = False,
                     extractions_out: Path | None = None, keys: dict[str, dict] | None = None,
                     run_scale: str | None = None, judge_workers: int = 8, log=None) -> pd.DataFrame:
    """urgency_order: the four letters, most urgent first (config urgency_most_urgent_first).

    keys: optional vignette records that replace the reference answers frozen in the run (score --keys).
    """
    jobs = load_jobs(db, include_incomplete)
    rows, ext_rows = [], []
    config_hashes, assets_by_script = set(), {}
    # First pass: extract every reply, and send the diagnosis strings that need the judge model in parallel.
    prepared, to_judge = [], []
    for j in jobs:
        script = json.loads(j["script_json"])
        gold, expected, key_source = apply_key(script, keys or {}, run_scale)
        replies = {r["reply_no"]: r for r in dbm.replies_for(db, j["job_id"])}
        ex = {}
        for k in range(1, N_REPLIES + 1):
            rep = replies.get(k)
            e = extract(rep["reply_text"] if rep else None, rep["stop_reason"] if rep else None, committed=rep is not None)
            if rep is None:
                e["missing_reason"] = j["end_reason"] if j["status"] == "ended" else "not_committed"
            ex[k] = e
            to_judge.append((script["factors"]["vignette"], gold, e["diagnosis"]))
        prepared.append((j, script, gold, expected, key_source, replies, ex))
    judge.prejudge(to_judge, workers=judge_workers, log=log)
    for j, script, gold, expected, key_source, replies, ex in prepared:
        f = script["factors"]
        for r in replies.values():
            config_hashes.add(r["config_hash"])
            assets_by_script.setdefault(script["script_id"], set()).add(r["assets_hash"])
        for k in range(1, N_REPLIES + 1):
            rep = replies.get(k)
            e = ex[k]
            jd = judge.judge(f["vignette"], gold, e["diagnosis"])
            exp = expected[k - 1]
            turn_kind = "opening" if k == 1 else script["turn_kinds"][k - 2]
            named = prose_levels(rep["reply_text"]) if rep else []
            row = {
                "job_id": j["job_id"], "model": j["model"], "stage": j["stage"], "repeat": j["repeat"],
                "script_id": script["script_id"], **f,
                "changed": gold["changed"], "reply": k, "turn_kind": turn_kind,
                "status": e["status"], "missing_reason": e.get("missing_reason"),
                "multi_block": e["multi_block"],
                "urgency": e["urgency"], "urgency_source": e["urgency_source"],
                "diagnosis": e["diagnosis"], "diagnosis_source": e["diagnosis_source"],
                "urgency_confidence": e["urgency_confidence"], "diagnosis_confidence": e["diagnosis_confidence"],
                "dx_identity": jd["identity"], "dx_key": jd["key"], "dx_match": jd["match"], "dx_method": jd["method"],
                "dx_leading": jd["leading"], "dx_hedged": jd["hedged"], "dx_uncertain": jd["uncertain"],
                "dx_modifiers": None if jd["modifiers"] is None else "; ".join(jd["modifiers"]),
                "dx_alternatives": None if jd["alternatives"] is None else "; ".join(jd["alternatives"]),
                "exp_urgency": exp["urgency"], "exp_dx_target": exp["dx_target"],
                "key_version": gold.get("key_version") or key_version(gold), "key_source": key_source,
                "dx_names_version": gold["accepted_names_version"],
                "start_dx": gold["start_dx"], "post_dx": gold["post_dx"],
                "prose_levels": ",".join(named) if named else None,
                "prose_block_conflict": (e["urgency"] not in named) if (named and e["urgency"]) else None,
                "has_thinking": _has_thinking(rep["content_json"]) if rep else None,
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
    return add_row_columns(df, urgency_order)


def add_row_columns(df: pd.DataFrame, urgency_order: list[str]) -> pd.DataFrame:
    """Per-row correctness, previous values, movement, direction and transitions."""
    df = df.sort_values(["job_id", "reply"]).reset_index(drop=True)
    df["urgency_correct"] = np.where(df["urgency"].isna(), None, df["urgency"] == df["exp_urgency"])
    scorable = df["dx_match"].isin(SCORABLE_MATCHES)
    df["dx_correct"] = np.where(scorable, df["dx_match"] == df["exp_dx_target"], None)
    g = df.groupby("job_id", sort=False)
    for col in ["urgency", "dx_identity", "dx_key", "dx_hedged", "urgency_correct", "dx_correct", "urgency_confidence",
                "diagnosis_confidence"]:
        df[f"prev_{col}"] = g[col].shift(1)

    def moved(a, b):
        return [None if (x is None or y is None or (isinstance(x, float) and np.isnan(x))
                         or (isinstance(y, float) and np.isnan(y))) else x != y for x, y in zip(a, b)]

    df["urgency_moved"] = moved(df["urgency"].where(df["urgency"].notna(), None),
                                df["prev_urgency"].where(df["prev_urgency"].notna(), None))
    # Diagnosis movement is on the leading diagnosis (dx_key), not on the wording.
    df["dx_moved"] = moved(df["dx_key"].where(df["dx_key"].notna(), None),
                           df["prev_dx_key"].where(df["prev_dx_key"].notna(), None))

    rank = urgency_rank({"urgency_most_urgent_first": urgency_order})

    def direction(u, p):
        if not isinstance(u, str) or not isinstance(p, str):
            return None
        return "more_urgent" if rank[u] < rank[p] else "less_urgent" if rank[u] > rank[p] else "same"

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
    ID = [None] + [_nz(r.get("dx_key")) for r in rows]          # leading diagnosis: what movement is measured on
    M = [None] + [_nz(r["dx_match"]) for r in rows]
    H = [None] + [_nz(r.get("dx_hedged")) for r in rows]
    H = [None if h is None else bool(h) for h in H]
    tk = [None, "opening"] + [rows[k]["turn_kind"] for k in range(1, N_REPLIES)]  # tk[r] = kind of turn answered at r

    def u_gives(k, target_reply):
        """Does reply k give the urgency expected at target_reply? None if missing."""
        return None if U[k] is None else U[k] == exp_u[target_reply]

    def d_gives(k, target_reply):
        if M[k] not in SCORABLE_MATCHES:
            return None
        return M[k] == exp_t[target_reply]

    # Noise replies by stratum: control (no update), before the update, after it. Never pooled.
    strata: dict[str, list[int]] = {}
    for t in range(1, N_FOLLOWUPS + 1):
        r = t + 1
        if tk[r] != "noise":
            continue
        stratum = "control" if kind == "none" else ("pre" if t < T else "post")
        strata.setdefault(stratum, []).append(r)

    for p, seq, gives in (("u", U, u_gives), ("d", ID, d_gives)):
        # Baseline
        out[f"{p}_baseline_valid"] = seq[1] is not None
        out[f"{p}_baseline_correct"] = gives(1, 1)
        out[f"{p}_baseline_correct_mf"] = _mf(gives(1, 1))

        # Movement under noise.
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
        # Response to a supportive update or a neutral fact: unchanged at the update's reply. The two are told
        # apart by update_kind in every table.
        if kind in STABLE_KINDS:
            v = None if seq[r] is None or seq[r - 1] is None else seq[r] == seq[r - 1]
            out[f"{p}_sup_unchanged"] = v
            out[f"{p}_sup_unchanged_mf"] = _mf(v)

        # Uptake of a discordant update (the urgency-only one, the diagnosis one, or a one-update record's).
        if is_discordant(kind):
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

    # Hedging onset under noise ("h"): a noise reply whose diagnosis is hedged when the reply before was not.
    # Counted like movement, so it is reported as h_noise_<stratum>_movement, with missing counted as an onset
    # in the missing-as-failure version.
    for stratum, reps in strata.items():
        valid = [r for r in reps if H[r] is not None and H[r - 1] is not None]
        out[f"h_noise_{stratum}_eligible"] = len(reps)
        out[f"h_noise_{stratum}_valid"] = len(valid)
        out[f"h_noise_{stratum}_moves"] = sum(H[r] and not H[r - 1] for r in valid)

    if kind in STABLE_KINDS:
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
             ["noise_type", "u_baseline_correct"], ["update_kind"], ["update_kind", "noise_type"],
             ["update_kind", "perspective"]]


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


def _f(series: pd.Series) -> pd.Series:
    """Booleans with None for missing -> floats with NaN, so means and counts skip the missing ones."""
    return series.map(lambda x: np.nan if (x is None or (isinstance(x, float) and np.isnan(x))) else float(x))


def by_reply_tables(long_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Correctness, transitions, confidence change, hedging and repeat agreement by reply number."""
    out = {}
    d = long_df.copy()
    d["urgency_correct_f"] = _f(d["urgency_correct"])
    d["dx_correct_f"] = _f(d["dx_correct"])
    d["hedged_f"] = _f(d["dx_hedged"])
    d["no_leading_f"] = d["dx_leading"].map(lambda x: np.nan if x is None or (isinstance(x, float) and np.isnan(x))
                                            else float(x == "none"))
    out["correctness_by_reply"] = (d.groupby(["model", "update_kind", "update_turn", "reply"])
                                   .agg(n=("job_id", "size"), urgency_valid=("urgency_correct_f", "count"),
                                        urgency_correct=("urgency_correct_f", "mean"),
                                        dx_valid=("dx_correct_f", "count"), dx_correct=("dx_correct_f", "mean"))
                                   .reset_index())
    out["hedging_by_reply"] = (d.groupby(["model", "update_kind", "noise_type", "perspective", "reply"])
                               .agg(n=("job_id", "size"), judged=("hedged_f", "count"),
                                    share_hedged=("hedged_f", "mean"),
                                    share_no_single_leading_dx=("no_leading_f", "mean"))
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
    sup_reply = d["turn_kind"].isin(STABLE_KINDS)
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


# ================================================================ checks against the reference answers

def baseline_check(long_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Do the model's answers and the reference answers describe the same case?

    For each model x vignette x language x perspective: the distribution of urgency and of the diagnosis match
    at the opening reply and at the reply to the discordant update, against the reference answer. Where fewer
    than half the answers match, that is either a model failure the study is about, or a reference answer (or
    scale, or update) that does not say what the clinicians meant; the warning asks for a look before the
    correctness figures for that vignette are read.
    """
    recs, warns = [], []
    cells = ["model", "vignette", "language", "perspective"]
    # One view per discordant update kind in the run: each has its own reference answer.
    views = [("baseline", long_df[long_df["reply"] == 1])] + [
        (f"{kind}_update", long_df[long_df["turn_kind"] == kind])
        for kind in DISCORDANT_KINDS if (long_df["turn_kind"] == kind).any()]
    for where, d in views:
        if d.empty:
            continue
        for key, g in d.groupby(cells):
            for what, col, expcol in (("urgency", "urgency", "exp_urgency"), ("diagnosis", "dx_match", "exp_dx_target")):
                vals = g[col].dropna()
                if what == "diagnosis":
                    vals = vals[vals.isin(SCORABLE_MATCHES)]
                expected = g[expcol].iloc[0]
                if vals.empty:
                    continue
                dist = Counter(vals.tolist())
                modal, n_modal = dist.most_common(1)[0]
                share = dist.get(expected, 0) / len(vals)
                flag = share < KEY_MISMATCH_SHARE
                recs.append({**dict(zip(cells, key)), "check": f"{where}_{what}", "n": len(g), "valid": len(vals),
                             "reference": expected, "modal_answer": modal, "share_matching_reference": share,
                             "distribution": json.dumps(dict(sorted(dist.items())), ensure_ascii=False),
                             "key_version": g["key_version"].iloc[0], "flag": flag})
                if flag:
                    ref_name = expected
                    if what == "diagnosis":
                        ref_name = f"{expected} ({g['post_dx'].iloc[0] if expected == 'post' else g['start_dx'].iloc[0]})"
                    warns.append(
                        f"{' '.join(map(str, key))}: {where.replace('_', ' ')} {what}: reference is {ref_name}, but "
                        f"{dist.get(expected, 0)} of {len(vals)} answers match it (most common answer: {modal}, "
                        f"{n_modal} of {len(vals)}). Check the reference answer before reading correctness here.")
    return pd.DataFrame(recs), warns


# ================================================================ retention and confidence tables

def retention_by_noise_turns(long_df: pd.DataFrame) -> pd.DataFrame:
    """After a discordant update, by number of noise turns since the update (0 = the update's own reply).

    The four update timings leave 9, 7, 5 and 0 noise turns of follow-up, so they are lined up on noise turns
    since the update rather than on reply number. Two measures for urgency and for diagnosis:
      share_reference     share giving the post-update reference answer
      share_same_as_update  share giving the same answer as at the update's own reply, whatever it was
                            (this one does not depend on the reference answers)
    update_turn "pooled" pools the timings that still have follow-up at that point.
    """
    d = long_df[long_df["update_kind"].isin(DISCORDANT_KINDS)].copy()
    if d.empty:
        return pd.DataFrame()
    d["noise_turns_since_update"] = d["reply"] - (d["update_turn"] + 1)
    d = d[d["noise_turns_since_update"] >= 0]
    at_update = d[d["noise_turns_since_update"] == 0].set_index("job_id")
    d["u_at_update"] = d["job_id"].map(at_update["urgency"])
    d["k_at_update"] = d["job_id"].map(at_update["dx_key"])
    d["u_ref"] = _f(d["urgency_correct"])
    d["d_ref"] = _f(d["dx_correct"])
    d["u_same"] = np.where(d["urgency"].notna() & d["u_at_update"].notna(), (d["urgency"] == d["u_at_update"]).astype(float), np.nan)
    d["d_same"] = np.where(d["dx_key"].notna() & d["k_at_update"].notna(), (d["dx_key"] == d["k_at_update"]).astype(float), np.nan)
    recs = []
    for gb in ([], ["noise_type"], ["perspective"], ["language"]):
        for pooled in (False, True):
            keys = ["model", "update_kind", *gb] + ([] if pooled else ["update_turn"]) + ["noise_turns_since_update"]
            for gkey, g in d.groupby(keys):
                gkey = gkey if isinstance(gkey, tuple) else (gkey,)
                kv = dict(zip(keys, gkey))
                recs.append({
                    "model": kv["model"], "update_kind": kv["update_kind"], "group_by": "+".join(gb) or "all",
                    "group_value": "+".join(str(kv[c]) for c in gb) or "all",
                    "update_turn": "pooled" if pooled else int(kv["update_turn"]),
                    "noise_turns_since_update": int(kv["noise_turns_since_update"]),
                    "n": len(g), "timings_in_pool": ",".join(str(int(x)) for x in sorted(g["update_turn"].unique())),
                    "urgency_valid": int(g["u_ref"].count()), "urgency_share_reference": g["u_ref"].mean(),
                    "urgency_share_same_as_update": g["u_same"].mean(),
                    "dx_valid": int(g["d_ref"].count()), "dx_share_reference": g["d_ref"].mean(),
                    "dx_share_same_as_update": g["d_same"].mean(),
                })
    return pd.DataFrame(recs)


def supportive_confidence_vs_control(long_df: pd.DataFrame) -> pd.DataFrame:
    """Confidence change at the supportive update (and at the neutral fact, if the run has one: column
    update_kind), against a noise turn at the same position.

    A supportive update late in a conversation follows noise that has already lowered confidence, so its raw
    rise mixes the effect of the evidence with recovery. The comparison here is the change at reply T+1 in the
    no-update arm of the same model, vignette, language, perspective and noise type, where turn T is noise.
    Differences are taken within that cell (means over repeats), then averaged over cells.
    """
    cell = ["model", "vignette", "language", "perspective", "noise_type", "reply"]
    deltas = ["urgency_confidence_delta", "diagnosis_confidence_delta"]
    ctrl = long_df[(long_df["update_kind"] == "none") & (long_df["reply"].isin([t + 1 for t in UPDATE_TURNS]))]
    recs = []
    for kind in STABLE_KINDS:
        sup = long_df[long_df["turn_kind"] == kind]
        if sup.empty or ctrl.empty:
            continue
        s = sup.groupby(cell)[deltas].mean().add_suffix("_supportive")
        c = ctrl.groupby(cell)[deltas].mean().add_suffix("_control")
        m = s.join(c, how="inner").reset_index()
        if m.empty:
            continue
        m["update_turn"] = m["reply"] - 1
        for gb in ([], ["update_turn"], ["noise_type"], ["perspective"], ["update_turn", "noise_type"]):
            for gkey, g in m.groupby(["model", *gb]):
                gkey = gkey if isinstance(gkey, tuple) else (gkey,)
                rec = {"model": gkey[0], "update_kind": kind, "group_by": "+".join(gb) or "all",
                       "group_value": "+".join(str(x) for x in gkey[1:]) or "all", "cells": len(g)}
                # The "_supportive" columns hold the change at this row's update_kind.
                for name, col in (("urgency_conf", "urgency_confidence_delta"), ("dx_conf", "diagnosis_confidence_delta")):
                    a, b = g[f"{col}_supportive"], g[f"{col}_control"]
                    rec[f"{name}_change_supportive"] = a.mean()
                    rec[f"{name}_change_noise_same_position"] = b.mean()
                    rec[f"{name}_difference"] = (a - b).mean()
                recs.append(rec)
    return pd.DataFrame(recs)


def model_settings(long_df: pd.DataFrame, cfg: dict) -> dict:
    """What each tested model was actually run with: settings sent, and whether thinking blocks came back."""
    out = {}
    for model, g in long_df.groupby("model"):
        mc = cfg.get("models", {}).get(model, {})
        th = g["has_thinking"].dropna()
        out[model] = {
            "api_model": mc.get("api_model"), "request_options": mc.get("request_options", {}),
            "max_tokens": mc.get("max_tokens", cfg.get("max_tokens")),
            "thinking_sent": mc.get("request_options", {}).get("thinking", "not sent (the API default applies)"),
            "share_of_replies_with_a_thinking_block": float(th.astype(bool).mean()) if len(th) else None,
            "mean_output_tokens": float(pd.to_numeric(g["output_tokens"]).mean()),
        }
    return out


def review_rows(long_df: pd.DataFrame) -> list[dict]:
    """One row per unique diagnosis string for the clinicians' review sheet, most frequent first."""
    d = long_df[long_df["diagnosis"].notna()].copy()
    if d.empty:
        return []
    d["norm"] = d["diagnosis"].map(norm_dx)
    rows = []
    for (vid, nv, _), g in d.groupby(["vignette", "dx_names_version", "norm"]):
        r = {k: _nz(v) for k, v in g.iloc[0].items()}
        rows.append({"vignette": vid, "names_version": nv, "n_replies": len(g), "text": r["diagnosis"],
                     "method": r["dx_method"], "leading": r["dx_leading"] or "",
                     "leading_name": (r["dx_identity"] if r["dx_leading"] not in (None, "none") else "") or "",
                     "modifiers": r["dx_modifiers"] or "", "alternatives": r["dx_alternatives"] or "",
                     "uncertain": "" if r["dx_uncertain"] is None else str(bool(r["dx_uncertain"])).lower(),
                     "start_dx": r["start_dx"], "post_dx": r["post_dx"]})
    return sorted(rows, key=lambda r: (r["vignette"], -r["n_replies"], r["text"]))


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
    with a percentile interval from resampling vignettes (all of a vignette's conditions kept together).

    With one vignette there is nothing to resample, so no interval is given; with fewer than five the
    interval is given but marked unstable.
    """
    diffs = {}
    for vid, g in conv.groupby("vignette"):
        a = _vignette_rate(g[g[factor] == level_a], metric, mf)
        b = _vignette_rate(g[g[factor] == level_b], metric, mf)
        if not (np.isnan(a) or np.isnan(b)):
            diffs[vid] = a - b
    if not diffs:
        return {"estimate": np.nan, "ci_low": np.nan, "ci_high": np.nan, "n_vignettes": 0, "ci_note": "no data"}
    arr = np.array(list(diffs.values()))
    n = len(arr)
    if n < MIN_VIGNETTES_FOR_CI:
        return {"estimate": float(arr.mean()), "ci_low": np.nan, "ci_high": np.nan, "n_vignettes": n,
                "ci_note": "one vignette: no interval can be estimated"}
    rng = np.random.default_rng(seed)
    boots = rng.choice(arr, size=(n_boot, n), replace=True).mean(axis=1)
    return {"estimate": float(arr.mean()), "ci_low": float(np.percentile(boots, 2.5)),
            "ci_high": float(np.percentile(boots, 97.5)), "n_vignettes": n,
            "ci_note": f"only {n} vignettes: interval unstable" if n < FEW_VIGNETTES else ""}


CONTRASTS = [
    # (metric, factor, level_a, level_b). The first is the pre-named primary comparison (spec 11).
    ("u_noise_control", "noise_type", "direct", "nondirect"),
    ("u_noise_pre", "noise_type", "direct", "nondirect"),
    ("u_noise_post", "noise_type", "direct", "nondirect"),
    ("u_disc_accuracy", "noise_type", "direct", "nondirect"),
    ("u_hold_final", "noise_type", "direct", "nondirect"),
    ("u_noise_control", "perspective", "nurse", "patient"),
    ("u_noise_control", "perspective", "consultant", "patient"),
    ("u_hold_final", "perspective", "nurse", "patient"),
    ("u_hold_final", "perspective", "consultant", "patient"),
    ("u_noise_control", "language", "zh", "en"),
    ("u_noise_control", "language", "ja", "en"),
    ("d_noise_control", "noise_type", "direct", "nondirect"),
    ("h_noise_control", "noise_type", "direct", "nondirect"),
]


def contrasts_table(conv: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    recs = []
    for model, g in conv.groupby("model"):
        # Pooled over update kinds, then, where a run has more than one discordant kind, the measures that
        # follow a discordant update again for each kind (their reference answers differ).
        subsets = [("all", g)]
        kinds = [k for k in DISCORDANT_KINDS if k in set(g["update_kind"])]
        if len(kinds) > 1:
            subsets += [(k, g[g["update_kind"] == k]) for k in kinds]
        for subset, sg in subsets:
            for metric, factor, a, b in CONTRASTS:
                if subset != "all" and not any(x in metric for x in ("_disc_", "_hold_", "_noise_post")):
                    continue
                if factor not in sg or not {a, b} <= set(sg[factor].unique()):
                    continue
                if f"{metric}_eligible" not in sg.columns and metric not in sg.columns:
                    continue
                for mf in (False, True):
                    res = bootstrap_contrast(sg, metric, factor, a, b, n_boot, seed, mf)
                    recs.append({"model": model, "update_kind": subset, "metric": metric, "factor": factor,
                                 "contrast": f"{a} - {b}", "missing_as_failure": mf, **res})
    return pd.DataFrame(recs)


# ================================================================ figures

TIMING_COLOURS = {1: "#1f6f8b", 3: "#2a9d8f", 5: "#e9c46a", 10: "#c8553d"}


def figures(conv: pd.DataFrame, long_df: pd.DataFrame, outdir: Path, retention: pd.DataFrame | None = None) -> list[Path]:
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
    d["uc"] = _f(d["urgency_correct"])
    kinds = [k for k in (*STABLE_KINDS, *DISCORDANT_KINDS) if k in set(d["update_kind"])]
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
                for turn in UPDATE_TURNS:
                    s = g[(g["update_kind"] == kind) & (g["update_turn"] == turn)].groupby("reply")["uc"].mean()
                    if not s.empty:
                        ax.plot(s.index, s.values, color=TIMING_COLOURS[turn], marker="o",
                                label=f"update after reply {turn}")
                ax.set_title(f"{model}: {KIND_LABELS[kind]}")
                ax.set_xticks(range(1, N_REPLIES + 1))
                ax.set_ylim(-0.02, 1.02)
                ax.set_xlabel("Reply number")
                ax.grid(alpha=0.3)
            axes[i][0].set_ylabel("Share giving the reference urgency")
        axes[0][-1].legend(fontsize=8)
        fig.tight_layout()
        p = outdir / "fig2_expected_urgency_by_timing.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(p)

    if retention is not None and not retention.empty:
        r = retention[(retention["group_by"] == "all") & (retention["update_turn"] != "pooled")]
        panels = [("urgency_share_reference", "Share giving the post-update reference urgency"),
                  ("urgency_share_same_as_update", "Share with the same urgency as at the update reply")]
        rkinds = [k for k in DISCORDANT_KINDS if k in set(r["update_kind"])]
        panel_rows = [(mm, k) for mm in models for k in rkinds]
        fig, axes = plt.subplots(len(panel_rows), 2, figsize=(11, 3.8 * len(panel_rows)), squeeze=False, sharey=True)
        for i, (model, rkind) in enumerate(panel_rows):
            for jx, (col, title) in enumerate(panels):
                ax = axes[i][jx]
                for turn in UPDATE_TURNS:
                    s = r[(r["model"] == model) & (r["update_kind"] == rkind)
                          & (r["update_turn"] == turn)].sort_values("noise_turns_since_update")
                    if not s.empty:
                        ax.plot(s["noise_turns_since_update"], s[col], color=TIMING_COLOURS[turn], marker="o",
                                label=f"update after reply {turn}")
                ax.set_title(f"{model}, {KIND_LABELS[rkind]}: {title}", fontsize=9)
                ax.set_xlabel("Noise turns since the update (0 = the update's own reply)")
                ax.set_xticks(range(0, N_FOLLOWUPS))
                ax.set_ylim(-0.02, 1.02)
                ax.grid(alpha=0.3)
            axes[i][0].set_ylabel("Share of conversations")
        axes[0][-1].legend(fontsize=8, loc="lower left")
        fig.tight_layout()
        p = outdir / "fig3_retention_by_noise_turns.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(p)
    return paths


# ================================================================ CLI

def score_run(run_dir: Path, cfg: dict, include_incomplete: bool = False, use_judge: bool = False,
              n_boot: int = 2000, make_figures: bool = True, label: str | None = None,
              keys_path: Path | str | None = None, mappings_path: Path | str | None = None,
              force: bool = False, judge_model=None, log=None, offline_judge: bool = False) -> dict:
    """Score a run into results/<run>/scores/<label>/. judge_model: a ready judge model (tests); else from config.

    offline_judge: no model call; use the decisions made with no API and imported under config judge.offline_name.
    """
    run_dir = Path(run_dir)
    label = label or f"s{SCORER_VERSION}"
    if keys_path and label == f"s{SCORER_VERSION}":
        raise ScoreError("--keys rescoring needs its own --label (for example s2-keys-b), so the scoring against "
                         "the answers frozen in the run is kept")
    db = dbm.connect(run_dir / "run.sqlite")
    jcfg = cfg["judge"]
    keys = load_keys(keys_path)
    if mappings_path is None:
        mappings_path = ROOT / "scenarios" / "dx_mappings.json"
    reviewed = load_reviewed(mappings_path)
    model = judge_model or (AnthropicJudge(jcfg) if use_judge else None)
    judge = DiagnosisJudge(run_dir / "judge_cache.sqlite", jcfg["prompt_version"], model,
                           jcfg.get("prices_per_mtok"), jcfg.get("spend_cap_usd"), reviewed,
                           offline_name=jcfg.get("offline_name") if offline_judge and model is None else None,
                           head_rule=bool(jcfg.get("leading_part_rule")))
    try:
        long_df = build_long_table(db, judge, cfg["urgency_most_urgent_first"], include_incomplete,
                                   run_dir / "extractions.jsonl", keys, cfg.get("urgency_scale_version"),
                                   jcfg.get("concurrency", 8), log)
        judge_calls, judge_spend = judge.n_model_calls, judge.spend_this_session()
    finally:
        judge.close()
    if long_df.empty:
        raise ScoreError("no conversations in finished repeat blocks (use --include-incomplete to score partial data)")

    key_versions = {v: kv for v, kv in sorted(long_df.groupby("vignette")["key_version"].first().items())}
    manifest = {
        "scorer_version": SCORER_VERSION, "label": label, "run": run_dir.name,
        "urgency_scale_version": cfg.get("urgency_scale_version"),
        "urgency_most_urgent_first": cfg["urgency_most_urgent_first"],
        "judge": {"model": judge.model_name, "prompt_version": jcfg["prompt_version"]},
        "reference_answers": {"source": str(keys_path) if keys_path else "frozen in the run",
                              "overridden_vignettes": sorted(set(keys) & set(long_df["vignette"])),
                              "key_versions": key_versions},
        "dx_mappings": {"path": str(mappings_path), "reviewed_entries": len(reviewed),
                        "hash": sha(sorted([list(map(str, k)) + [m["leading"]] for k, m in reviewed.items()]))},
        "include_incomplete": include_incomplete,
    }
    manifest["scoring_id"] = sha(manifest)
    out = run_dir / "scores" / label
    mpath = out / "scoring_manifest.json"
    if mpath.exists() and not force:
        old = read_json(mpath)
        if old.get("scoring_id") != manifest["scoring_id"]:
            raise ScoreError(f"{out} already holds a scoring made with different inputs (judge, reference answers, "
                             f"reviewed mappings or scorer version). Give a new --label to keep both, or --force "
                             f"to replace it.")
    out.mkdir(parents=True, exist_ok=True)
    manifest.update({"created_at": dbm.now(), "code_version": code_version()})

    long_df.to_csv(out / "long_table.csv", index=False, encoding="utf-8")
    conv = build_conversation_table(long_df)
    conv.to_csv(out / "conversations.csv", index=False, encoding="utf-8")
    agg = aggregate(conv)
    agg.to_csv(out / "outcomes.csv", index=False, encoding="utf-8")
    for name, t in by_reply_tables(long_df).items():
        t.to_csv(out / f"{name}.csv", index=False, encoding="utf-8")
    con = contrasts_table(conv, n_boot)
    con.to_csv(out / "contrasts.csv", index=False, encoding="utf-8")
    checks, warnings = baseline_check(long_df)
    checks.to_csv(out / "baseline_check.csv", index=False, encoding="utf-8")
    retention = retention_by_noise_turns(long_df)
    retention.to_csv(out / "retention_by_noise_turns.csv", index=False, encoding="utf-8")
    supportive_confidence_vs_control(long_df).to_csv(out / "supportive_confidence_vs_control.csv", index=False,
                                                    encoding="utf-8")
    write_review_sheet(out / "dx_review.csv", review_rows(long_df))
    figs = figures(conv, long_df, out, retention) if make_figures else []

    unjudged = long_df["dx_method"].isin(["unjudged", "unjudged_spend_cap", "judge_error", "judge_refused"])
    if unjudged.any():
        warnings.append(f"{int(unjudged.sum())} of {len(long_df)} replies have a diagnosis the judge has not read "
                        f"({ {k: int(v) for k, v in long_df.loc[unjudged, 'dx_method'].value_counts().items()} }); diagnosis and hedging "
                        f"outcomes leave them out. Run with --judge (API; or raise its spend cap), or judge them with "
                        f"no API: python -m src.judge export --run {run_dir.name}")
    named = long_df["prose_block_conflict"].notna()
    status_counts = long_df["status"].value_counts().to_dict()
    hedged = _f(long_df["dx_hedged"])
    summary = {
        "scoring": manifest,
        "conversations": int(conv.shape[0]), "replies": int(long_df.shape[0]),
        "reply_status": {k: int(v) for k, v in status_counts.items()},
        "valid_urgency_share": float(long_df["urgency"].notna().mean()),
        "unique_diagnosis_texts": int(long_df["diagnosis"].dropna().str.lower().nunique()),
        "dx_methods": {k: int(v) for k, v in long_df["dx_method"].value_counts().items()},
        "dx_leading": {k: int(v) for k, v in long_df["dx_leading"].value_counts().items()},
        "share_of_judged_replies_hedged": float(hedged.mean()) if hedged.notna().any() else None,
        "judge_model_calls": judge_calls, "judge_spend_usd": round(judge_spend, 4),
        "models": model_settings(long_df, cfg),
        "prose_block": {
            "replies_whose_prose_names_a_level": int(named.sum()),
            "of_those_block_level_not_among_them": int(long_df.loc[named, "prose_block_conflict"].astype(bool).sum()),
            "note": "narrow check: only levels named outright in the prose, such as (C) or level B",
        },
        "mean_output_tokens": float(pd.to_numeric(long_df["output_tokens"]).mean()),
        "include_incomplete": include_incomplete,
        "warnings": warnings,
        "figures": [p.name for p in figs],
    }
    write_json(mpath, manifest)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["output_dir"] = str(out)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--config", default=None, help="default: the run's own frozen config")
    ap.add_argument("--include-incomplete", action="store_true")
    ap.add_argument("--judge", action="store_true", help="call the judge model for diagnoses with no exact match")
    ap.add_argument("--judge-offline", action="store_true",
                    help="no model call: use the decisions imported with python -m src.judge import-decisions")
    ap.add_argument("--label", default=None, help=f"output folder under scores/ (default s{SCORER_VERSION})")
    ap.add_argument("--keys", default=None, help="a vignettes file whose reference answers replace the frozen ones")
    ap.add_argument("--mappings", default=None, help="reviewed diagnosis mappings (default scenarios/dx_mappings.json)")
    ap.add_argument("--force", action="store_true", help="replace an existing label made with different inputs")
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args(argv)
    run_dir = Path(args.results) / args.run
    cfg = load_config(args.config) if args.config else read_json(run_dir / "config.json")
    # The judge is a scoring tool, not part of what the run measured: its settings come from the live config.
    cfg = dict(cfg, judge=load_config()["judge"]) if args.config is None else cfg
    if args.judge and args.judge_offline:
        print("ERROR: give --judge (API) or --judge-offline (no API), not both")
        return 2
    if args.judge:
        from .common import load_dotenv_if_present  # noqa: PLC0415
        load_dotenv_if_present()
    try:
        summary = score_run(run_dir, cfg, args.include_incomplete, args.judge, args.n_boot, label=args.label,
                            keys_path=args.keys, mappings_path=args.mappings, force=args.force,
                            log=lambda m: print(m, flush=True), offline_judge=args.judge_offline)
    except ScoreError as e:
        print(f"ERROR: {e}")
        return 2
    print(json.dumps({k: v for k, v in summary.items() if k != "warnings"}, indent=2, ensure_ascii=False))
    for w in summary["warnings"]:
        print(f"WARNING: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
