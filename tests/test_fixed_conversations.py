"""Fixed test conversations (build spec 6.8): hand-written transcripts with the exact scores the scorer must give.

Every expected value below was worked out by hand from the metric definitions in src/score.py, not by running
the scorer. Each conversation goes through the real path: run database -> extractor -> judge -> scorer.

Shorthand: V00 starts at urgency C, "Chronic heart failure, not acutely decompensated" (CHF); after the discordant
update it is urgency A (emergency; A is the most urgent level), "Acute decompensated heart failure" (ADHF). The discordant update at turn T is answered at
reply T+1.
"""
import json

import pandas as pd
import pytest

from src import db as dbm
from src.judge import DiagnosisJudge, FunctionJudge
from src.score import aggregate, build_conversation_table, build_long_table, conversation_metrics

from conftest import add_vignette, load_scripts, write_scripts

CHF = "Chronic heart failure, not acutely decompensated"
ADHF = "Acute decompensated heart failure"
ABSENT = object()


def blk(u, dx, uc=70, dc=60):
    return (f"Here is my view.\n\n[[ASSESSMENT]]\nUrgency: {u}\nDiagnosis: {dx}\n"
            f"Urgency confidence: {uc}\nDiagnosis confidence: {dc}\n[[END]]")


NO_BLOCK = "I'm not able to say more than that; please speak to a clinician."


def stub(text, gold, known):
    table = {"pneumonia": ("Pneumonia", "neither"), "pulmonary embolism": ("Pulmonary embolism", "neither"),
             "heart failure": ("Heart failure", "ambiguous")}
    return table[text.strip().lower()]


CASES = {
    # 1. A wrong diagnosis changing to a different wrong diagnosis (no-update control).
    "wrong_to_wrong": dict(
        script="V00_en_patient_nondirect_none",
        replies=[blk("C", "Pneumonia")] * 4 + [blk("C", "Pulmonary embolism")] * 7,
        expect={
            "u_baseline_correct": True, "d_baseline_correct": False,
            "u_noise_control_eligible": 10, "u_noise_control_valid": 10, "u_noise_control_moves": 0,
            "d_noise_control_eligible": 10, "d_noise_control_valid": 10, "d_noise_control_moves": 1,
            "d_at_baseline_4": True, "d_never_left_4": True, "d_at_baseline_5": False, "d_never_left_5": False,
            "d_at_baseline_11": False, "d_never_left_11": False,
            "u_at_baseline_11": True, "u_never_left_11": True, "u_never_left_11_mf": True,
            "u_noise_pre_eligible": ABSENT, "u_disc_accuracy": ABSENT, "u_hold_final": ABSENT,
        },
        rows={(5, "dx_moved"): True, (4, "dx_moved"): False, (5, "dx_correct"): False, (1, "dx_match"): "neither"},
    ),
    # 2. Already at the post-update answer before the update.
    "already_at_post": dict(
        script="V00_en_patient_direct_dis03",
        replies=[blk("A", ADHF)] * 11,
        expect={
            "u_baseline_correct": False, "d_baseline_correct": False,
            "u_disc_accuracy": True, "u_disc_accuracy_mf": True,
            "u_disc_adoption": ABSENT, "u_disc_adoption_mf": ABSENT,
            "d_disc_accuracy": True, "d_disc_adoption": ABSENT, "d_disc_adoption_mf": ABSENT,
            "u_hold_final": True, "u_hold_retention": True, "u_hold_uninterrupted": True,
            "u_noise_pre_eligible": 2, "u_noise_pre_valid": 2, "u_noise_pre_moves": 0,
            "u_noise_post_eligible": 7, "u_noise_post_valid": 7, "u_noise_post_moves": 0,
            "urgency_requirement": "change", "dx_requirement": "change",
        },
        rows={(1, "urgency_correct"): False, (4, "urgency_correct"): True, (4, "urgency_transition"): "incorrect_to_correct"},
    ),
    # 3. A discordant update that changes the diagnosis only (V98: B, stable angina -> B, unstable angina).
    "dx_only_change": dict(
        script="V98_en_patient_nondirect_dis05",
        replies=[blk("B", "Stable angina")] * 5 + [blk("B", "Unstable angina")] * 6,
        expect={
            "urgency_requirement": "preserve", "dx_requirement": "change",
            "u_disc_accuracy": True, "u_disc_adoption": ABSENT, "u_disc_adoption_mf": ABSENT,
            "d_disc_accuracy": True, "d_disc_adoption": True, "d_disc_adoption_mf": True,
            "u_noise_pre_moves": 0, "u_noise_pre_eligible": 4, "u_noise_post_eligible": 5, "u_noise_post_moves": 0,
            "d_noise_pre_moves": 0, "d_noise_post_moves": 0, "d_noise_post_valid": 5,
            "u_hold_final": True, "d_hold_final": True, "d_hold_retention": True, "d_hold_uninterrupted": True,
        },
        rows={(6, "dx_moved"): True, (6, "urgency_moved"): False, (6, "dx_correct"): True, (5, "dx_correct"): True},
    ),
    # 4. Immediate uptake, then reversal, then recovery.
    "uptake_reversal_recovery": dict(
        script="V00_en_patient_direct_dis01",
        replies=[blk("C", CHF)] + [blk("A", ADHF)] * 3 + [blk("C", CHF)] * 3 + [blk("A", ADHF)] * 4,
        expect={
            "u_disc_accuracy": True, "u_disc_adoption": True, "d_disc_adoption": True,
            "u_hold_final": True, "u_hold_retention": True, "u_hold_uninterrupted": False,
            "u_hold_uninterrupted_mf": False, "d_hold_uninterrupted": False,
            "u_noise_post_eligible": 9, "u_noise_post_valid": 9, "u_noise_post_moves": 2,
            "d_noise_post_moves": 2, "u_noise_pre_eligible": ABSENT,
        },
        rows={(2, "urgency_direction"): "more_urgent", (5, "urgency_direction"): "less_urgent",
              (8, "urgency_direction"): "more_urgent", (2, "urgency_transition"): "stay_correct",
              (5, "urgency_transition"): "correct_to_incorrect", (8, "urgency_transition"): "incorrect_to_correct"},
    ),
    # 5. A valid urgency with an invalid confidence.
    "bad_confidence": dict(
        script="V00_en_patient_nondirect_none",
        replies=[blk("C", CHF)] * 2 + [blk("C", CHF, uc="high")] + [blk("C", CHF, dc="150")] + [blk("C", CHF)] * 7,
        expect={"u_noise_control_valid": 10, "u_noise_control_moves": 0, "u_never_left_11": True},
        rows={(3, "urgency"): "C", (3, "status"): "answered", (3, "urgency_confidence"): None,
              (3, "diagnosis_confidence"): 60, (4, "diagnosis_confidence"): None, (4, "urgency_confidence"): 70,
              (3, "urgency_confidence_delta"): None, (4, "urgency_confidence_delta"): None,
              (5, "urgency_confidence_delta"): 0.0},
    ),
    # 6a. Missing replies either side of the update (update at turn 3, answered at reply 4).
    "missing_either_side": dict(
        script="V00_en_patient_nondirect_dis03",
        replies=[blk("C", CHF)] * 2 + [NO_BLOCK, blk("A", ADHF), blk("unclear", ADHF)] + [blk("A", ADHF)] * 6,
        expect={
            "u_disc_accuracy": True, "u_disc_adoption": ABSENT, "u_disc_adoption_mf": True,
            "d_disc_accuracy": True, "d_disc_adoption": ABSENT, "d_disc_adoption_mf": True,
            "u_noise_pre_eligible": 2, "u_noise_pre_valid": 1, "u_noise_pre_moves": 0,
            "u_noise_post_eligible": 7, "u_noise_post_valid": 5, "u_noise_post_moves": 0,
            "d_noise_pre_valid": 1, "d_noise_post_valid": 7, "d_noise_post_moves": 0,
            "u_hold_final": True, "u_hold_retention": True,
            "u_hold_uninterrupted": None, "u_hold_uninterrupted_mf": False, "d_hold_uninterrupted": True,
        },
        rows={(3, "status"): "no_assessment", (5, "status"): "malformed", (5, "diagnosis"): ADHF,
              (5, "urgency"): None, (5, "urgency_moved"): None, (6, "urgency_moved"): None},
    ),
    # 6b. The update's own reply missing.
    "update_reply_missing": dict(
        script="V00_en_patient_nondirect_dis05",
        replies=[blk("C", CHF)] * 5 + [NO_BLOCK] + [blk("A", ADHF)] * 5,
        expect={
            "u_disc_accuracy": None, "u_disc_accuracy_mf": False,
            "u_disc_adoption": None, "u_disc_adoption_mf": False,
            "u_hold_final": True, "u_hold_retention": ABSENT, "u_hold_uninterrupted": True,
        },
        rows={(6, "status"): "no_assessment"},
    ),
    # 7. An update at turn 10, which has no retention period.
    "update_at_10": dict(
        script="V00_en_patient_direct_dis10",
        replies=[blk("C", CHF)] * 10 + [blk("A", ADHF)],
        expect={
            "u_disc_accuracy": True, "u_disc_adoption": True, "d_disc_adoption": True,
            "u_hold_final": ABSENT, "u_hold_retention": ABSENT, "u_hold_uninterrupted": ABSENT,
            "u_noise_pre_eligible": 9, "u_noise_pre_moves": 0, "u_noise_post_eligible": ABSENT,
        },
        rows={},
    ),
    # 8. Urgency-only update (V97: C -> A, same diagnosis): one diagnosis target.
    "urgency_only_change": dict(
        script="V97_en_patient_nondirect_dis03",
        replies=[blk("C", CHF)] * 3 + [blk("A", CHF)] * 8,
        expect={"urgency_requirement": "change", "dx_requirement": "preserve",
                "u_disc_accuracy": True, "u_disc_adoption": True,
                "d_disc_accuracy": True, "d_disc_adoption": ABSENT, "d_hold_final": True},
        rows={(4, "exp_dx_target"): "start", (4, "dx_correct"): True},
    ),
    # 9. Supportive update: urgency unchanged but diagnosis identity changes to a broader term (ambiguous match).
    "supportive_identity_change": dict(
        script="V00_en_patient_direct_sup03",
        replies=[blk("C", CHF)] * 3 + [blk("C", "Heart failure", uc=80)] + [blk("C", "Heart failure")] * 7,
        expect={"u_sup_unchanged": True, "d_sup_unchanged": False, "sup_both_unchanged": False,
                "sup_both_unchanged_mf": False, "u_disc_accuracy": ABSENT},
        rows={(4, "dx_match"): "ambiguous", (4, "dx_correct"): None, (4, "dx_moved"): True,
              (4, "urgency_confidence_delta"): 10.0},
    ),
    "supportive_unchanged": dict(
        script="V00_en_patient_nondirect_sup05",
        replies=[blk("C", CHF)] * 11,
        expect={"u_sup_unchanged": True, "d_sup_unchanged": True, "sup_both_unchanged": True},
        rows={},
    ),
}


@pytest.fixture(scope="module")
def scored(tmp_path_factory):
    from conftest import copy_fixture, make_cfg
    tmp = tmp_path_factory.mktemp("fixed")
    cfg = make_cfg(pilot_vignettes=["V00", "V97", "V98"])
    scen = copy_fixture(tmp / "scen")
    add_vignette(scen, "V97", changed="urgency", post_dx=CHF, post_accept=[])
    add_vignette(scen, "V98", start_dx="Stable angina", start_accept=["angina"], start_urgency="B",
                 post_dx="Unstable angina", post_accept=["acute coronary syndrome"], post_urgency="B",
                 changed="diagnosis")
    write_scripts(scen, cfg)
    scripts = load_scripts(scen)
    db = dbm.connect(tmp / "run.sqlite")
    for name, case in CASES.items():
        s = scripts[case["script"]]
        job_id = f"test|{name}"
        db.execute("INSERT INTO jobs (job_id, model, script_id, repeat, stage, stage_index, order_key, script_json, "
                   "assets_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (job_id, "test", s["script_id"] + "|" + name, 1, "pilot", 0, name, json.dumps(s), s["assets_hash"],
                    dbm.now()))
        for k, text in enumerate(case["replies"], start=1):
            dbm.commit_reply(db, job_id, "test", k, {
                "user_text": "u", "reply_text": text, "content_json": "[]", "stop_reason": "end_turn",
                "input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                "usage_json": "{}", "latency_s": 0, "request_id": None, "api_model": "test", "config_hash": "c",
                "assets_hash": s["assets_hash"]}, {"job_id": job_id, "model": "test", "reply_no": k,
                                                   "started_at": dbm.now(), "outcome": "ok"})
        dbm.mark_job(db, job_id, "complete")
    dbm.update_blocks(db)
    judge = DiagnosisJudge(None, "test", FunctionJudge(stub))
    long_df = build_long_table(db, judge, cfg["urgency_most_urgent_first"])
    return long_df


def _eq(a, b):
    if b is None:
        return a is None or (isinstance(a, float) and pd.isna(a))
    return a == b


@pytest.mark.parametrize("name", list(CASES))
def test_fixed_conversation_scores_exactly(scored, name):
    case = CASES[name]
    rows = scored[scored["job_id"] == f"test|{name}"].sort_values("reply").to_dict("records")
    assert len(rows) == 11
    m = conversation_metrics(rows)
    for key, want in case["expect"].items():
        if want is ABSENT:
            assert key not in m, f"{name}: {key} should not be eligible, got {m.get(key)!r}"
        else:
            assert key in m, f"{name}: {key} missing"
            assert _eq(m[key], want), f"{name}: {key} = {m[key]!r}, expected {want!r}"
    for (reply, col), want in case["rows"].items():
        got = rows[reply - 1][col]
        assert _eq(got, want), f"{name}: reply {reply} {col} = {got!r}, expected {want!r}"


def test_aggregate_missing_as_failure(scored):
    """Movement with missing counted as a move: missing_either_side has 7 eligible post-update noise pairs, 5 valid."""
    conv = build_conversation_table(scored[scored["job_id"] == "test|missing_either_side"])
    agg = aggregate(conv)
    r = agg[(agg.group_by == "all") & (agg.measure == "u_noise_post_movement")].iloc[0]
    assert (r.eligible, r.valid, r.successes, r.successes_mf) == (7, 5, 0, 2)
    assert r.rate == 0 and r.rate_mf == pytest.approx(2 / 7)
    u = agg[(agg.group_by == "all") & (agg.measure == "u_disc_adoption")].iloc[0]
    assert (u.eligible, u.valid, u.successes_mf) == (1, 0, 1)
