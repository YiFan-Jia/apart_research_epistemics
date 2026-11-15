"""Scorer version 2 and the reworked diagnosis judge (15 Nov changes), with no model call."""
import asyncio
import csv
import json

import numpy as np
import pandas as pd
import pytest

from src import db as dbm
from src.clients import MockModel, MockParams
from src.common import read_json, write_json
from src.extract import prose_levels
from src.judge import DiagnosisJudge, FunctionJudge, import_review, load_reviewed, norm_dx
from src.llm import build_json_request
from src.runner import Runner
from src.score import (
    ScoreError, bootstrap_contrast, build_conversation_table, build_long_table, conversation_metrics, score_run,
)

from conftest import load_scripts, make_cfg

CHF = "Chronic heart failure, not acutely decompensated"
ADHF = "Acute decompensated heart failure"
GOLD = {"start_dx": CHF, "start_accept": ["chronic heart failure"], "post_dx": ADHF,
        "post_accept": ["acute heart failure"], "changed": "both", "accepted_names_version": "nv1"}


def decision(leading, name="", modifiers=(), alternatives=(), uncertain=False):
    return {"leading": leading, "leading_name": name, "modifiers": list(modifiers),
            "alternatives": list(alternatives), "uncertain": uncertain}


# ---------------------------------------------------------------- judge

def test_modifier_and_added_differential_do_not_change_the_leading_diagnosis():
    table = {
        "chronic heart failure with ankle oedema": decision("start", CHF, ["with ankle oedema"]),
        "chronic heart failure; pulmonary embolism not excluded": decision("start", CHF, [], ["Pulmonary embolism"]),
        "heart failure versus pulmonary embolism": decision("none", "", [], ["Heart failure", "Pulmonary embolism"]),
        "heart failure": decision("both", "Heart failure"),
        "pneumonia": decision("other", "Pneumonia"),
    }
    calls = []

    def fn(text, gold, known):
        calls.append(text)
        return table[text.lower()]

    j = DiagnosisJudge(None, "t", FunctionJudge(fn))
    exact = j.judge("V00", GOLD, "Chronic heart failure")
    mod = j.judge("V00", GOLD, "Chronic heart failure with ankle oedema")
    alt = j.judge("V00", GOLD, "Chronic heart failure; pulmonary embolism not excluded")
    none = j.judge("V00", GOLD, "Heart failure versus pulmonary embolism")
    both = j.judge("V00", GOLD, "Heart failure")
    other = j.judge("V00", GOLD, "Pneumonia")
    assert exact["method"] == "exact" and exact["key"] == mod["key"] == alt["key"] == "start"
    assert exact["identity"] == mod["identity"] == CHF
    assert (mod["hedged"], alt["hedged"], none["hedged"]) == (False, True, True)
    assert mod["modifiers"] == ["with ankle oedema"] and alt["alternatives"] == ["Pulmonary embolism"]
    assert (none["match"], none["key"]) == ("none", "none")
    assert (both["match"], both["key"]) == ("ambiguous", "both")
    assert (other["match"], other["key"]) == ("neither", "other:pneumonia")
    n = len(calls)
    assert j.judge("V00", GOLD, "pneumonia.")["method"] == "model" and len(calls) == n      # cached, no second call
    assert j.judge("V00", GOLD, None)["method"] == "none"
    assert DiagnosisJudge(None, "t").judge("V00", GOLD, "Pneumonia")["method"] == "unjudged"


def test_one_reference_diagnosis_has_no_post_or_both():
    gold = dict(GOLD, changed="urgency", post_dx=CHF, post_accept=[])
    j = DiagnosisJudge(None, "t", FunctionJudge(lambda t, g, k: decision("post", ADHF)))
    assert j.judge("V97", gold, "Decompensated failure")["key"] == "start"


def test_reviewed_mapping_overrides_the_judge_and_import_reports_agreement(tmp_path):
    sheet = tmp_path / "dx_review.csv"
    cols = ["vignette", "names_version", "n_replies", "text", "method", "leading", "leading_name", "modifiers",
            "alternatives", "uncertain", "start_dx", "post_dx", "review", "reviewed_leading", "reviewed_leading_name",
            "reviewed_modifiers", "reviewed_alternatives", "reviewed_uncertain", "note"]
    rows = [
        # accepted as the judge read it
        dict(vignette="V00", names_version="nv1", text="CCF with oedema", method="model", leading="start",
             leading_name=CHF, modifiers="with oedema", alternatives="", uncertain="false", review="ok"),
        # corrected by the clinician: the judge said other, it is the post-update diagnosis
        dict(vignette="V00", names_version="nv1", text="Acute pulmonary oedema", method="model", leading="other",
             leading_name="Pulmonary oedema", modifiers="", alternatives="", uncertain="false",
             reviewed_leading="post"),
        # not reviewed: left out
        dict(vignette="V00", names_version="nv1", text="Pneumonia", method="model", leading="other",
             leading_name="Pneumonia", modifiers="", alternatives="", uncertain="false"),
    ]
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({**{c: "" for c in cols}, **r})
    mappings = tmp_path / "dx_mappings.json"
    res = import_review(sheet, mappings, "Dr A")
    assert (res["added"], res["judge_rows_compared"], res["judge_agreed"]) == (2, 2, 1)
    assert res["disagreements"][0]["clinician"] == "post"
    reviewed = load_reviewed(mappings)
    assert set(k[2] for k in reviewed) == {norm_dx("CCF with oedema"), norm_dx("Acute pulmonary oedema")}

    def must_not_be_called(*a):
        raise AssertionError("a reviewed string must not reach the judge model")

    j = DiagnosisJudge(None, "t", FunctionJudge(must_not_be_called), reviewed=reviewed)
    r = j.judge("V00", GOLD, "acute pulmonary oedema")
    assert (r["method"], r["match"], r["identity"]) == ("reviewed", "post", ADHF)
    # A mapping made for other accepted names does not apply once the names change.
    assert DiagnosisJudge(None, "t", reviewed=reviewed).judge("V00", dict(GOLD, accepted_names_version="nv2"),
                                                              "acute pulmonary oedema")["method"] == "unjudged"
    assert import_review(sheet, mappings, "Dr A")["updated"] == 2       # importing again replaces, does not duplicate


def test_json_request_keeps_effort_beside_the_format():
    req = build_json_request({"api_model": "m", "max_tokens": 50, "request_options": {"output_config": {"effort": "low"}}},
                             "p", {"type": "object"}, system="s")
    assert req["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": {"type": "object"}}}
    assert req["system"] == "s" and req["max_tokens"] == 50 and "request_options" not in req


def test_prose_levels_reads_only_levels_named_outright():
    text = "Treat as urgent (C) if stable. **Go to the ER now (D)** if clots.\n\n[[ASSESSMENT]]\nUrgency: B\n[[END]]"
    assert prose_levels(text) == ["C", "D"]
    assert prose_levels("This is a level B problem.") == ["B"]
    assert prose_levels("With urgency a doctor (a GP) should see you about a plan.") == []
    assert prose_levels("我的评估是（Ｂ）。") == ["B"]


# ---------------------------------------------------------------- conversation metrics

def rows_for(dx_keys, hedged, urgencies=None, kind="none", turn=0):
    """Eleven long-table rows for a V00-like conversation, built by hand."""
    urgencies = urgencies or ["C"] * 11
    out = []
    for i in range(11):
        k = i + 1
        tk = "opening" if k == 1 else (kind if (kind != "none" and k == turn + 1) else "noise")
        out.append({"reply": k, "turn_kind": tk, "update_kind": kind, "update_turn": turn, "changed": "both",
                    "exp_urgency": "C", "exp_dx_target": "start", "urgency": urgencies[i], "dx_key": dx_keys[i],
                    "dx_match": {"start": "start", "none": "none"}.get(dx_keys[i], "neither"), "dx_hedged": hedged[i]})
    return out


def test_hedging_is_its_own_outcome_and_not_a_diagnosis_move():
    # Same leading diagnosis throughout; a differential is added at reply 3 and kept, dropped at 8, added again at 10.
    hedged = [False, False, True, True, True, True, True, False, False, True, True]
    m = conversation_metrics(rows_for(["start"] * 11, hedged))
    assert (m["d_noise_control_eligible"], m["d_noise_control_moves"]) == (10, 0)
    assert (m["h_noise_control_eligible"], m["h_noise_control_valid"], m["h_noise_control_moves"]) == (10, 10, 2)
    assert m["d_never_left_11"] is True and m["d_baseline_correct"] is True and m["d_baseline_correct_mf"] is True
    # Losing the single leading diagnosis is a move, and is scored as not correct.
    keys = ["start"] * 4 + ["none"] * 7
    m = conversation_metrics(rows_for(keys, [False] * 4 + [True] * 7))
    assert m["d_noise_control_moves"] == 1 and m["d_at_baseline_11"] is False
    # Unjudged diagnoses are missing for both.
    m = conversation_metrics(rows_for(["start"] * 5 + [None] * 6, [False] * 5 + [None] * 6))
    assert (m["h_noise_control_valid"], m["d_noise_control_valid"]) == (4, 4)


def test_no_interval_from_one_vignette():
    def conv(vids):
        recs = []
        for v in vids:
            for nt, moves in (("direct", 3), ("nondirect", 1)):
                recs.append({"vignette": v, "noise_type": nt, "u_noise_control_eligible": 10,
                             "u_noise_control_valid": 10, "u_noise_control_moves": moves})
        return pd.DataFrame(recs)
    one = bootstrap_contrast(conv(["V01"]), "u_noise_control", "noise_type", "direct", "nondirect")
    assert one["estimate"] == pytest.approx(0.2) and np.isnan(one["ci_low"]) and np.isnan(one["ci_high"])
    assert one["n_vignettes"] == 1 and "one vignette" in one["ci_note"]
    three = bootstrap_contrast(conv(["V01", "V02", "V03"]), "u_noise_control", "noise_type", "direct", "nondirect")
    assert not np.isnan(three["ci_low"]) and "unstable" in three["ci_note"]
    six = bootstrap_contrast(conv([f"V0{i}" for i in range(1, 7)]), "u_noise_control", "noise_type", "direct", "nondirect")
    assert six["ci_note"] == ""


# ---------------------------------------------------------------- score_run end to end on a mock run

@pytest.fixture
def mock_run(tmp_path, scen):
    cfg = make_cfg()
    cfg["stages"]["pilot"]["repeats"] = 4
    r = Runner(tmp_path / "run1", cfg, scen, {}, mock=True, quiet=True, status_every_s=999)
    r.open()
    r.add_stage("pilot", ["haiku"])
    r.clients = {"haiku": MockModel(list(load_scripts(scen).values()),
                                    MockParams(p_correct_baseline=1.0, p_malformed=0.0, p_uptake=0.8, seed=3), name="haiku")}
    assert asyncio.run(r.execute(["haiku"])) == 0
    r.db.close()
    return tmp_path / "run1", cfg, scen


def test_score_run_writes_versioned_outputs_and_new_tables(mock_run, tmp_path):
    run_dir, cfg, scen = mock_run
    mappings = tmp_path / "none.json"
    s = score_run(run_dir, cfg, n_boot=50, mappings_path=mappings)
    out = run_dir / "scores" / "s2"
    for name in ["long_table.csv", "outcomes.csv", "contrasts.csv", "baseline_check.csv", "hedging_by_reply.csv",
                 "retention_by_noise_turns.csv", "supportive_confidence_vs_control.csv", "dx_review.csv",
                 "scoring_manifest.json", "summary.json", "fig3_retention_by_noise_turns.png"]:
        assert (out / name).exists(), name
    man = read_json(out / "scoring_manifest.json")
    assert man["scorer_version"] == "2" and man["reference_answers"]["source"] == "frozen in the run"
    assert man["urgency_scale_version"] == cfg["urgency_scale_version"]
    assert s["models"]["haiku"]["share_of_replies_with_a_thinking_block"] == 0.0
    assert s["warnings"] == []                                   # the mock answers match the reference at baseline
    con = pd.read_csv(out / "contrasts.csv")
    assert con["ci_low"].isna().all() and (con["n_vignettes"] == 1).all()
    agg = pd.read_csv(out / "outcomes.csv")
    b = agg[(agg.group_by == "all") & (agg.measure == "u_baseline_correct")].iloc[0]
    assert b.rate == 1.0 and b.valid == b.eligible == 72         # baseline correctness is reported, not blank
    ret = pd.read_csv(out / "retention_by_noise_turns.csv")
    t10 = ret[(ret.group_by == "all") & (ret.update_turn == "10")]
    assert list(t10.noise_turns_since_update) == [0]             # an update at turn 10 has no noise after it
    assert ret[(ret.group_by == "all") & (ret.update_turn == "1")].noise_turns_since_update.max() == 9
    assert (ret[ret.noise_turns_since_update == 0].urgency_share_same_as_update == 1.0).all()
    sup = pd.read_csv(out / "supportive_confidence_vs_control.csv")
    row = sup[sup.group_by == "all"].iloc[0]
    assert row.dx_conf_change_supportive == pytest.approx(10.0)  # the mock adds 10 at a supportive update
    assert row.dx_conf_change_noise_same_position == pytest.approx(0.0) and row.dx_conf_difference == pytest.approx(10.0)
    # Scoring again with the same inputs is fine; a different judge under the same label is refused.
    score_run(run_dir, cfg, n_boot=50, mappings_path=mappings)
    other_judge = FunctionJudge(lambda t, g, k: decision("other", "X"), name="another-judge")
    with pytest.raises(ScoreError, match="different inputs"):
        score_run(run_dir, cfg, n_boot=50, mappings_path=mappings, judge_model=other_judge)
    score_run(run_dir, cfg, n_boot=50, mappings_path=mappings, judge_model=other_judge, label="s2-other-judge")
    assert (run_dir / "scores" / "s2-other-judge" / "summary.json").exists() and (out / "summary.json").exists()


def test_rescoring_against_corrected_reference_answers(mock_run, tmp_path):
    run_dir, cfg, scen = mock_run
    mappings = tmp_path / "none.json"
    keys = read_json(scen / "vignettes.json")
    keys["vignettes"][0]["start_urgency"] = "B"                  # the clinicians now say B, the model said C
    kpath = tmp_path / "corrected.json"
    write_json(kpath, keys)
    with pytest.raises(ScoreError, match="needs its own --label"):
        score_run(run_dir, cfg, n_boot=50, keys_path=kpath, mappings_path=mappings)
    s = score_run(run_dir, cfg, n_boot=50, keys_path=kpath, mappings_path=mappings, label="s2-keys-b")
    man = s["scoring"]
    assert man["reference_answers"]["overridden_vignettes"] == ["V00"]
    lt = pd.read_csv(run_dir / "scores" / "s2-keys-b" / "long_table.csv")
    assert set(lt[lt.reply == 1].exp_urgency) == {"B"} and set(lt.key_source) == {"override"}
    # Every baseline answer now differs from the reference: the scorer says so instead of leaving it to be found.
    assert any("baseline urgency: reference is B, but 0 of" in w for w in s["warnings"])
    checks = pd.read_csv(run_dir / "scores" / "s2-keys-b" / "baseline_check.csv")
    assert checks[checks.check == "baseline_urgency"].flag.all()
    # Reference answers on another scale cannot be compared with this run's letters.
    keys["vignettes"][0]["urgency_scale_version"] = "v2"
    write_json(kpath, keys)
    with pytest.raises(ScoreError, match="urgency scale"):
        score_run(run_dir, cfg, n_boot=50, keys_path=kpath, mappings_path=mappings, label="s2-keys-c")
