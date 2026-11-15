"""The neutral fact (new but irrelevant: nothing should change) and the reversal cases (a reassuring update
lowers the urgency, the diagnosis stays, and there is no diagnosis update): validator, scripts, mock run,
scorer and importer. No model call."""
import asyncio

import pandas as pd
import pytest

from src.assets import vignette_problems
from src.clients import MockModel, MockParams
from src.common import read_json, update_kinds, write_json
from src.runner import Runner
from src.score import score_run
from src.scripts import build_stage, flat_key, gold_and_expected

from conftest import copy_fixture, load_scripts, make_cfg, write_scripts
from test_two_updates import two_update

NEUTRAL = {"en": "The patient mentions that a neighbour has just bought a new car.",
           "zh": "患者提到，邻居刚买了一辆新车。", "ja": "患者は、隣人が最近新しい車を買ったと話している。"}
REASSURE = {"en": "His weight has been steady for the past month.", "zh": "过去一个月他的体重一直稳定。",
            "ja": "この1か月、体重は変わっていません。"}


def reversal(scen, **fields):
    """V00 as a reversal case: C -> B on the urgency update, C -> D on the reassuring update, a neutral fact,
    and no diagnosis update."""
    two_update(scen)
    vs = read_json(scen / "vignettes.json")
    v = vs["vignettes"][0]
    v.update(reassuring_update=REASSURE["en"], reassuring_post_urgency="D", neutral_update=NEUTRAL["en"],
             dx_update=None, post_dx=None, post_accept=[], dx_post_urgency=None)
    v.update(fields)
    write_json(scen / "vignettes.json", vs)
    a = read_json(scen / "assets.json")
    out = []
    for x in a["assets"]:
        if x["slot"] == "discordant_dx":
            out.append(dict(x, slot="discordant_reassure", text=REASSURE[x["language"]]))
            out.append(dict(x, slot="neutral", text=NEUTRAL[x["language"]]))
            continue
        out.append(x)
    write_json(scen / "assets.json", {"format_version": 2, "assets": out})
    return v


def test_reference_answers_and_scripts_for_the_new_kinds(tmp_path, cfg):
    d = copy_fixture(tmp_path / "s")
    v = reversal(d)
    assert update_kinds(v) == ["supportive", "neutral", "discordant_urgency", "discordant_reassure"]
    down = flat_key(v, "discordant_reassure")
    assert (down["post_urgency"], down["post_dx"], down["changed"]) == ("D", v["start_dx"], "urgency")
    assert flat_key(v, "discordant_urgency")["post_urgency"] == "B"
    for kind in ("none", "supportive", "neutral"):               # no diagnosis update: only the starting answer
        k = flat_key(v, kind)
        assert (k["post_urgency"], k["post_dx"]) == ("C", v["start_dx"])
    _, expected = gold_and_expected(v, "neutral", 3)
    assert {(e["urgency"], e["dx_target"]) for e in expected} == {("C", "start")}
    _, expected = gold_and_expected(v, "discordant_reassure", 3)
    assert [e["urgency"] for e in expected] == ["C"] * 3 + ["D"] * 8
    scripts, rep = build_stage(d, cfg, "pilot")
    assert not rep.errors and any("no diagnosis update" in w for w in rep.warnings)
    assert len(scripts) == 2 * (1 + 4 * 4)                       # 2 noise types x (none + 4 kinds x 4 timings)
    by_id = {s["script_id"]: s for s in scripts}
    s = by_id["V00_en_patient_direct_neu03"]
    assert s["turns"][2] == NEUTRAL["en"] and s["turn_kinds"][2] == "neutral"
    s = by_id["V00_en_patient_nondirect_rsu10"]
    assert s["turns"][9] == REASSURE["en"] and s["gold"]["post_urgency"] == "D"


def test_validator_refuses_a_reassuring_update_that_cannot_work():
    base = {"id": "V00", "clerking": "A case.", "start_dx": "X", "start_accept": [], "start_urgency": "C",
            "supportive_update": "A supportive fact.", "urgency_update": "An alarming fact.",
            "urgency_post_urgency": "B", "dx_update": None, "post_dx": None, "post_accept": [],
            "dx_post_urgency": None, "uncertainty": None, "reassuring_update": "A reassuring fact.",
            "reassuring_post_urgency": "D"}
    assert vignette_problems(base)[0] == []
    errs, _ = vignette_problems(dict(base, reassuring_post_urgency="C"))
    assert any("the reassuring update leaves the urgency at C" in e for e in errs)
    errs, _ = vignette_problems(dict(base, reassuring_post_urgency="B"))
    assert any("lead to the same urgency" in e for e in errs)
    errs, _ = vignette_problems(dict(base, reassuring_update=None, urgency_update=None))
    assert any("no discordant update" in e for e in errs)
    errs, _ = vignette_problems(dict(base, neutral_update="  "))
    assert any("'neutral_update' must be text" in e for e in errs)


def test_mock_run_scores_the_neutral_fact_and_the_reassuring_update(tmp_path):
    d = copy_fixture(tmp_path / "s")
    reversal(d)
    cfg = make_cfg()
    cfg["stages"]["pilot"]["repeats"] = 2
    write_scripts(d, cfg)
    r = Runner(tmp_path / "run", cfg, d, {}, mock=True, quiet=True, status_every_s=999)
    r.open()
    r.add_stage("pilot", ["haiku"])
    r.clients = {"haiku": MockModel(list(load_scripts(d).values()),
                                    MockParams(p_correct_baseline=1.0, p_malformed=0.0, p_uptake=1.0, seed=3), name="haiku")}
    assert asyncio.run(r.execute(["haiku"])) == 0
    r.db.close()
    s = score_run(tmp_path / "run", cfg, n_boot=50, mappings_path=tmp_path / "none.json")
    assert s["warnings"] == []
    out = tmp_path / "run" / "scores" / "s2"
    agg = pd.read_csv(out / "outcomes.csv")
    by_kind = agg[agg.group_by == "update_kind"]
    acc = by_kind[by_kind.measure == "u_disc_accuracy"].set_index("group_value")
    assert set(acc.index) == {"discordant_urgency", "discordant_reassure"} and (acc.rate == 1.0).all()
    assert (acc.eligible == 2 * 4 * 2).all()                     # 2 noise types x 4 timings x 2 repeats each
    dacc = by_kind[by_kind.measure == "d_disc_accuracy"].set_index("group_value")
    assert (dacc.rate == 1.0).all()                              # the diagnosis stays after both
    same = by_kind[by_kind.measure == "u_sup_unchanged"].set_index("group_value")
    assert set(same.index) == {"supportive", "neutral"} and (same.rate == 1.0).all()
    chk = pd.read_csv(out / "baseline_check.csv").set_index("check").reference
    assert chk["discordant_reassure_update_urgency"] == "D" and chk["discordant_urgency_update_urgency"] == "B"
    long = pd.read_csv(out / "long.csv") if (out / "long.csv").exists() else None
    if long is not None:
        down = long[long.turn_kind == "discordant_reassure"]
        assert set(down.urgency_direction) == {"less_urgent"}
        assert set(long[long.turn_kind == "discordant_urgency"].urgency_direction) == {"more_urgent"}
    conf = pd.read_csv(out / "supportive_confidence_vs_control.csv")
    assert set(conf.update_kind) == {"supportive", "neutral"}


def test_importer_reads_reversal_sheets_and_the_neutral_fact(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from src.import_sheets import COL, EN_HEADERS, convert, find_files

    header = [f"col{i}" for i in range(24)]
    for key, name in EN_HEADERS.items():
        header[COL[key]] = name
    header += ["baseline_accepted_diagnosis_names", "CC_both_pt", "DC_urgency_patient", "DC_Dx_patient"]
    rev_header = header + ["RC_Urgency", "RC_urgency_outcome", "RC_urgency_patient", "notes_for_clinicians"]

    def row(cid, lang, width, start="D", dx="Fever of 39.5 C", post_dx="Meningitis", dx_urg="A", extra=()):
        r = [None] * width
        vals = {"id": cid, "complaint": "Headache", "start_dx": f"{lang}Migraine", "age": 29, "sex": "Female",
                "onset": "Gradual", "character": "Throbbing", "timing": "Episodic", "modifiers": "Worse with light",
                "severity": "5/10", "associated_1": "Nausea", "associated_2": "No aura", "pmh": "Migraines",
                "lifestyle": "plays tennis", "start_urgency": start, "supportive": f"{lang}Not taken her tablets",
                "urgency_update": f"{lang}Cannot keep fluids down", "urgency_post_urgency": "B",
                "dx_update": dx, "post_dx": post_dx, "dx_post_urgency": dx_urg,
                "consultant": f"{lang}I'm a doctor.", "nurse": f"{lang}I'm a nurse.", "patient": f"{lang}I have a headache."}
        for k, val in vals.items():
            r[COL[k]] = val
        r[24:28] = [None, f"{lang}pt supportive", f"{lang}pt alarming", None]
        r[28:28 + len(extra)] = extra
        return r

    def save(path, head, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        wb = openpyxl.Workbook()
        wb.active.append(head)
        for r in rows:
            wb.active.append(r)
        wb.save(path)

    na = "N/A (diagnosis unchanged)"
    save(tmp_path / "CLINICAL SPREADSHEET.xlsx", header, [row("V001", "", 28)])
    save(tmp_path / "Clinical Spreadsheet - Japanese.xlsx", header, [row("V001", "ja ", 28)])
    save(tmp_path / "reversal" / "cases.xlsx", rev_header,
         [row("V021", "", 32, start="C", dx=na, post_dx=na, dx_urg=na,
              extra=["Drinking normally", "D", "I'm drinking normally.", "a note"])])
    save(tmp_path / "reversal" / "cases - Japanese.xlsx", rev_header,
         [row("V021", "ja ", 32, start="C", dx=na, post_dx=na, dx_urg=na,
              extra=["ja Drinking normally", "D", "ja I'm drinking normally.", None])])
    paths = find_files(tmp_path)
    assert {lang: [p.name for p in ps] for lang, ps in paths.items()} == {
        "en": ["CLINICAL SPREADSHEET.xlsx", "cases.xlsx"],
        "ja": ["Clinical Spreadsheet - Japanese.xlsx", "cases - Japanese.xlsx"]}
    neutral = {"en": {"clinician": "A neighbour has a new car.", "patient": "My neighbour has a new car."},
               "ja": {"clinician": "ja neighbour", "patient": "ja my neighbour"}}
    (v1, v21), assets, notes = convert(paths, "v3", "approved", "approved", neutral, "draft")
    assert (v1["id"], v21["id"]) == ("V01", "V21")
    assert v1["dx_update"] == "Fever of 39.5 C" and "reassuring_update" not in v1
    assert (v21["dx_update"], v21["post_dx"], v21["post_accept"], v21["dx_post_urgency"]) == (None, None, [], None)
    assert (v21["reassuring_update"], v21["reassuring_post_urgency"], v21["start_urgency"]) == ("Drinking normally", "D", "C")
    assert v1["neutral_update"] == v21["neutral_update"] == "A neighbour has a new car."
    assert update_kinds(v21) == ["supportive", "neutral", "discordant_urgency", "discordant_reassure"]
    assert vignette_problems(dict(v21, clerking="A case."))[0] == []
    got = {(a["vignette"], a["language"], a["perspective"], a["slot"]): (a["text"], a["status"]) for a in assets}
    assert got[("V21", "en", "patient", "discordant_reassure")] == ("I'm drinking normally.", "approved")
    assert got[("V21", "ja", "nurse", "discordant_reassure")] == ("ja Drinking normally", "approved")
    assert got[("V21", "ja", "patient", "discordant_reassure")] == ("ja I'm drinking normally.", "approved")
    assert got[("V21", "en", "patient", "neutral")] == ("My neighbour has a new car.", "draft")
    assert got[("V01", "ja", "consultant", "neutral")] == ("ja neighbour", "draft")
    assert ("V21", "en", "nurse", "discordant_dx") not in got and ("V01", "en", "nurse", "discordant_dx") in got
    assert len(assets) == 2 * 3 * 5 * 2                          # 2 languages x 3 speakers x 5 slots x 2 vignettes
    assert any("V21: the diagnosis-update cell" in n and "no diagnosis update" in n for n in notes)
    with pytest.raises(ValueError, match="neutral fact: no patient text for ja"):
        convert(paths, "v3", "approved", neutral={"en": neutral["en"], "ja": {"clinician": "x"}})
