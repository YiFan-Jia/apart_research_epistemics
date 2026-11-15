"""Vignettes with two discordant updates (urgency-only and diagnosis): validator, scripts, runner, scorer,
checker and the spreadsheet importer. No model call."""
import asyncio
import datetime as dt

import pandas as pd
import pytest

from src.assets import validate
from src.clients import MockModel, MockParams
from src.common import read_json, update_conditions, write_json
from src.runner import Runner
from src.score import score_run
from src.scripts import build_stage, flat_key
from src.vignette_check import key_checks

from conftest import copy_fixture, load_scripts, make_cfg, write_scripts
from test_vignette_check import ScriptedChecker, check, mock_probe

CHF = "Chronic heart failure, not acutely decompensated"
ADHF = "Acute decompensated heart failure"
URG = {"en": "His weight has gone up by four kilograms over the past week.",
       "zh": "过去一周他的体重增加了四公斤。", "ja": "この1週間で体重が4キロ増えています。"}


def two_update(scen, urgency_update=True, **fields):
    """Rewrite the copied V00 fixture in the two-update format: C -> B on the urgency update, C -> A and a new
    diagnosis on the diagnosis update."""
    vs = read_json(scen / "vignettes.json")
    v = vs["vignettes"][0]
    rec = {k: v[k] for k in ["id", "clerking", "start_dx", "start_accept", "start_urgency", "urgency_scale_version",
                             "supportive_update", "post_dx", "post_accept", "uncertainty"]}
    rec.update(urgency_update=URG["en"] if urgency_update else None,
               urgency_post_urgency="B" if urgency_update else None,
               dx_update=v["discordant_update"], dx_post_urgency=v["post_urgency"])
    rec.update(fields)
    write_json(scen / "vignettes.json", {"format_version": 2, "vignettes": [rec]})
    a = read_json(scen / "assets.json")
    out = []
    for x in a["assets"]:
        if x["slot"] == "discordant":
            x = dict(x, slot="discordant_dx")
            if urgency_update:
                out.append(dict(x, slot="discordant_urgency", text=URG[x["language"]]))
        out.append(x)
    write_json(scen / "assets.json", {"format_version": 2, "assets": out})
    return rec


@pytest.fixture
def scen2(tmp_path):
    d = copy_fixture(tmp_path / "scenarios2")
    two_update(d)
    write_scripts(d, make_cfg())
    return d


def test_each_update_kind_has_its_own_reference_answers(scen2, cfg):
    scripts, rep = build_stage(scen2, cfg, "pilot")
    assert not rep.errors and len(scripts) == 2 * 13            # 2 noise types x (none + 3 kinds x 4 timings)
    by = {s["script_id"]: s for s in scripts}
    urg, ddx = by["V00_en_patient_direct_urg03"], by["V00_en_patient_direct_ddx03"]
    assert urg["turn_kinds"][2] == "discordant_urgency" and urg["turns"][2] == URG["en"]
    assert [e["urgency"] for e in urg["expected"]] == ["C"] * 3 + ["B"] * 8
    assert [e["dx_target"] for e in urg["expected"]] == ["start"] * 11           # the diagnosis must not move
    assert urg["gold"]["changed"] == "urgency" and urg["gold"]["post_dx"] == CHF and urg["gold"]["post_accept"] == []
    assert [e["urgency"] for e in ddx["expected"]] == ["C"] * 3 + ["A"] * 8
    assert [e["dx_target"] for e in ddx["expected"]] == ["start"] * 3 + ["post"] * 8
    assert ddx["gold"]["changed"] == "both" and ddx["gold"]["post_dx"] == ADHF
    # Conversations with no discordant update still carry the diagnosis update's names, to recognise a drift.
    assert by["V00_en_patient_direct_none"]["gold"]["post_dx"] == ADHF
    assert by["V00_en_patient_direct_sup01"]["gold"]["post_dx"] == ADHF
    assert urg["gold"]["key_version"] != ddx["gold"]["key_version"]


def test_same_urgency_after_the_diagnosis_update_means_only_the_diagnosis_changes(tmp_path):
    d = copy_fixture(tmp_path / "s")
    rec = two_update(d, dx_post_urgency="C")
    assert flat_key(rec, "discordant_dx")["changed"] == "diagnosis"
    assert not validate(d, make_cfg()).errors


def test_vignette_without_an_urgency_update_runs_without_that_arm(tmp_path, cfg):
    d = copy_fixture(tmp_path / "s")
    rec = two_update(d, urgency_update=False)
    assert [k for k, _ in update_conditions(rec)].count("discordant_urgency") == 0
    scripts, rep = build_stage(d, cfg, "pilot")
    assert len(scripts) == 2 * 9 and not rep.errors
    assert any("no urgency-only update" in w for w in rep.warnings)


def test_validator_refuses_an_urgency_update_that_changes_nothing_and_a_missing_text(tmp_path, cfg):
    d = copy_fixture(tmp_path / "s")
    two_update(d, urgency_post_urgency="C")                     # same as the starting urgency
    rep = validate(d, cfg)
    assert any("the urgency update leaves the urgency at C" in e for e in rep.errors)
    assert rep.stages["pilot"]["ready"] == []
    two_update(copy_fixture(tmp_path / "t"))
    a = read_json(tmp_path / "t" / "assets.json")
    a["assets"] = [x for x in a["assets"]
                   if (x["perspective"], x["language"], x["slot"]) != ("patient", "en", "discordant_urgency")]
    write_json(tmp_path / "t" / "assets.json", a)
    rep = validate(tmp_path / "t", cfg)
    assert "V00 en patient discordant_urgency: missing" in rep.stages["pilot"]["not_ready"]["V00"]


def test_mock_run_is_scored_by_update_kind(scen2, tmp_path):
    cfg = make_cfg()
    cfg["stages"]["pilot"]["repeats"] = 2
    r = Runner(tmp_path / "run2", cfg, scen2, {}, mock=True, quiet=True, status_every_s=999)
    r.open()
    r.add_stage("pilot", ["haiku"])
    r.clients = {"haiku": MockModel(list(load_scripts(scen2).values()),
                                    MockParams(p_correct_baseline=1.0, p_malformed=0.0, p_uptake=1.0, seed=3), name="haiku")}
    assert asyncio.run(r.execute(["haiku"])) == 0
    r.db.close()
    s = score_run(tmp_path / "run2", cfg, n_boot=50, mappings_path=tmp_path / "none.json")
    assert s["warnings"] == []                 # the mock takes up both updates as the reference answers say
    out = tmp_path / "run2" / "scores" / "s2"
    agg = pd.read_csv(out / "outcomes.csv")
    acc = agg[(agg.group_by == "update_kind") & (agg.measure == "u_disc_accuracy")].set_index("group_value")
    assert set(acc.index) == {"discordant_urgency", "discordant_dx"} and (acc.rate == 1.0).all()
    assert (acc.eligible == 2 * 4 * 2).all()                    # 2 noise types x 4 timings x 2 repeats each
    dacc = agg[(agg.group_by == "update_kind") & (agg.measure == "d_disc_accuracy")].set_index("group_value")
    assert (dacc.rate == 1.0).all()            # urgency update: the diagnosis stayed; diagnosis update: it changed
    chk = pd.read_csv(out / "baseline_check.csv")
    assert {"baseline_urgency", "discordant_urgency_update_urgency", "discordant_dx_update_diagnosis"} <= set(chk.check)
    refs = chk.set_index("check").reference
    assert refs["discordant_urgency_update_urgency"] == "B" and refs["discordant_dx_update_urgency"] == "A"
    assert refs["discordant_urgency_update_diagnosis"] == "start" and refs["discordant_dx_update_diagnosis"] == "post"
    ret = pd.read_csv(out / "retention_by_noise_turns.csv")
    assert set(ret.update_kind) == {"discordant_urgency", "discordant_dx"}
    con = pd.read_csv(out / "contrasts.csv")
    assert {"all", "discordant_urgency", "discordant_dx"} == set(con.update_kind)
    assert (out / "fig3_retention_by_noise_turns.png").exists()


def test_checker_reviews_both_updates_and_the_probe_flags_each(scen2, tmp_path):
    cfg = make_cfg()
    checker = ScriptedChecker(verdicts={"urgency_update_urgency": ("fail", "B is not what most would choose.")})
    rep = check(tmp_path, scen2, cfg, checker,
                probe_clients=mock_probe(cfg, p_correct_baseline=1.0, p_uptake=0.0, p_malformed=0.0))
    v = rep["vignettes"]["V00"]
    rec = read_json(scen2 / "vignettes.json")["vignettes"][0]
    ids = [c["id"] for c in v["key_review"]["key"]["checks"]]
    assert ids == list(key_checks(rec)) and {"urgency_update_dx", "dx_update_dx", "dx_update_single_fact"} <= set(ids)
    assert v["verdict"] == "BLOCK" and v["n_fail"] == 1
    assert set(v["key_review"]["blind"]) == {"baseline", "after_supportive", "after_discordant_urgency",
                                             "after_discordant_dx"}
    assert len(checker.prompts) == 2 + 9 + 3
    blind = next(p for p in checker.prompts if "<further_information_3>" in p)
    assert "<reference_answers>" not in blind and "urgency update" not in blind.split("</study>")[1]
    cell = v["probe"][0]
    assert set(cell["updates"]) == {"discordant_urgency", "discordant_dx"}
    assert cell["updates"]["discordant_urgency"]["reference_urgency"] == "B"
    assert cell["updates"]["discordant_dx"]["reference_dx_target"] == "post"
    flags = " | ".join(v["probe_flags"])
    assert "after the urgency update, urgency" in flags and "after the diagnosis update, diagnosis" in flags
    md = (tmp_path / "vignette_checks" / "c1" / "report.md").read_text(encoding="utf-8")
    assert "## Every fail, in one place" in md and "B is not what most would choose." in md
    assert "Urgency after the urgency update (ref B)" in md


def test_spreadsheets_are_imported_without_changing_the_clinical_content(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from src.import_sheets import COL, EN_HEADERS, convert, find_files

    def sheet(name, header, rows):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(header)
        for r in rows:
            ws.append(r)
        wb.save(tmp_path / name)

    header = [f"col{i}" for i in range(24)]
    for key, name in EN_HEADERS.items():
        header[COL[key]] = name

    def row(cid, sev, urg_update, urg_out, dx_urg, lang=""):
        r = [None] * 24
        vals = {"id": cid, "complaint": "Headache", "start_dx": "Migraine", "age": 29.0, "sex": "Female",
                "onset": "Gradual", "character": "Throbbing", "timing": "Episodic", "modifiers": "Worse with light",
                "severity": sev, "associated_1": "Nausea", "associated_2": "No aura", "pmh": "Migraines",
                "lifestyle": "plays tennis", "start_urgency": "D", "supportive": f"{lang}Has not taken her tablets",
                "urgency_update": urg_update, "urgency_post_urgency": urg_out, "dx_update": f"{lang}She has a fever. ",
                "post_dx": "Meningitis", "dx_post_urgency": dx_urg,
                "consultant": f"{lang}I'm a doctor.\n Throbbing headache.", "nurse": f"{lang}I'm a nurse.",
                "patient": f"{lang}I have a headache."}
        for k, val in vals.items():
            r[COL[k]] = val
        return r

    sheet("CLINICAL SPREADSHEET.xlsx", header, [row("V001", dt.datetime(2026, 10, 5), "Cannot keep fluids down", "B", "A"),
                                                row("V002", "Mild", "None", "D", "A ")])
    sheet("Clinical Spreadsheet - Japanese.xlsx", ["x"] * 24, [row("V001", "5/10", "水分がとれない", "B", "A", "日本語 "),
                                                               row("V002", "軽度", "なし", "D", "A", "日本語 ")])
    paths = find_files(tmp_path)
    assert set(paths) == {"en", "ja"}
    vignettes, assets, notes = convert(paths, "v3", "approved")
    v1, v2 = vignettes
    assert (v1["id"], v1["source_id"], v2["id"]) == ("V01", "V001", "V02")
    assert "Severity: 5/10." in v1["clerking"] and v1["clerking"].startswith("29-year-old female.")
    assert v1["urgency_update"] == "Cannot keep fluids down" and v1["urgency_post_urgency"] == "B"
    assert v2["urgency_update"] is None and v2["urgency_post_urgency"] is None and v2["dx_post_urgency"] == "A"
    assert v1["dx_update"] == "She has a fever." and v1["urgency_scale_version"] == "v3"
    text = {(a["vignette"], a["language"], a["perspective"], a["slot"]): a["text"] for a in assets}
    assert text[("V01", "en", "consultant", "opening")] == "I'm a doctor.\nThrowbing headache.".replace("Throwbing", "Throbbing")
    assert text[("V01", "ja", "patient", "discordant_urgency")] == "水分がとれない"
    assert ("V02", "en", "patient", "discordant_urgency") not in text
    assert len(assets) == 2 * 3 * 4 + 2 * 3 * 3                  # V01: 4 slots; V02: no urgency update
    joined = " | ".join(notes)
    assert "severity cell holds the date" in joined and "no urgency-only update" in joined and "'A '" in joined


def test_patient_voice_and_accepted_name_columns_are_read_in_the_sheets_layout(tmp_path):
    """The layout of 15 Nov (evening): accepted names, then the three updates in the patient's voice. The
    Chinese sheet translates its headings, so its columns are found by position."""
    openpyxl = pytest.importorskip("openpyxl")
    from src.import_sheets import COL, EN_HEADERS, convert

    header = [f"col{i}" for i in range(24)]
    for key, name in EN_HEADERS.items():
        header[COL[key]] = name
    header += ["baseline_accepted_diagnosis_names", "CC_both_pt", "DC_urgency_patient", "DC_Dx_patient"]

    def row(lang, start_dx, post_dx, accept, pt):
        r = [None] * 28
        vals = {"id": "V001", "complaint": "Headache", "start_dx": start_dx, "age": 29, "sex": "Female",
                "onset": "Gradual", "character": "Throbbing", "timing": "Episodic", "modifiers": "Worse with light",
                "severity": "5/10", "associated_1": "Nausea", "associated_2": "No aura", "pmh": "Migraines",
                "lifestyle": "plays tennis", "start_urgency": "D", "supportive": f"{lang}Not taken her tablets",
                "urgency_update": f"{lang}Cannot keep fluids down", "urgency_post_urgency": "B",
                "dx_update": f"{lang}Fever of 39.5 C", "post_dx": post_dx, "dx_post_urgency": "A",
                "consultant": f"{lang}I'm a doctor.", "nurse": f"{lang}I'm a nurse.", "patient": f"{lang}I have a headache."}
        for k, val in vals.items():
            r[COL[k]] = val
        r[24:28] = [accept, *pt]
        return r

    def save(name, head, r):
        wb = openpyxl.Workbook()
        wb.active.append(head)
        wb.active.append(r)
        wb.save(tmp_path / name)

    save("en.xlsx", header, row("", "Migraine",
                                "Meningitis\nAccepted alternatives: bacterial meningitis; unstable angina (a remark)\n"
                                "Review note: check this", "migraine without aura; Migraine; acute migraine attack",
                                ["I haven't taken my tablets.", "I can't keep fluids down.", None]))   # one cell empty
    save("zh.xlsx", ["标题"] * 28, row("中文 ", "偏头痛", "脑膜炎\n可接受的其他名称：细菌性脑膜炎；病毒性脑膜炎", "无先兆偏头痛；偏头痛",
                                     ["我还没吃药。", "我喝什么都吐。", "我发烧了。"]))
    paths = {"en": tmp_path / "en.xlsx", "zh": tmp_path / "zh.xlsx"}
    (v,), assets, notes = convert(paths, "v3", "approved")
    assert v["start_dx"] == "Migraine" and v["post_dx"] == "Meningitis"
    assert v["start_accept"] == ["migraine without aura", "acute migraine attack", "偏头痛", "无先兆偏头痛"]
    assert v["post_accept"] == ["bacterial meningitis", "unstable angina", "脑膜炎", "细菌性脑膜炎", "病毒性脑膜炎"]
    got = {(a["language"], a["perspective"], a["slot"]): (a["text"], a["status"]) for a in assets}
    assert got[("en", "patient", "supportive")] == ("I haven't taken my tablets.", "draft")
    assert got[("en", "patient", "discordant_urgency")] == ("I can't keep fluids down.", "draft")
    assert got[("en", "patient", "discordant_dx")] == ("Fever of 39.5 C", "approved")     # empty cell: the note is used
    assert got[("en", "nurse", "supportive")] == ("Not taken her tablets", "approved")
    assert got[("en", "consultant", "discordant_urgency")] == ("Cannot keep fluids down", "approved")
    assert got[("zh", "patient", "discordant_dx")] == ("我发烧了。", "draft")
    assert got[("zh", "nurse", "discordant_dx")] == ("中文 Fever of 39.5 C", "approved")
    joined = " | ".join(notes)
    assert "DC_Dx_patient cell is empty" in joined and "unresolved review note" in joined
    assert "remark in brackets" in joined and "no column headed" not in joined
    _, assets, _ = convert(paths, "v3", "approved", patient_update_status="approved")
    assert all(a["status"] == "approved" for a in assets)

    # A reference that still reads as several diagnoses is imported as it stands and reported.
    save("en.xlsx", header, row("", "Stable angina", "STEMI; unstable angina; NSTEMI", None, [None, None, None]))
    (v,), _, notes = convert({"en": tmp_path / "en.xlsx"}, "v3", "approved")
    assert v["post_dx"] == "STEMI; unstable angina; NSTEMI" and v["post_accept"] == [] and v["start_accept"] == []
    assert any("reads as several diagnoses" in n for n in notes)

    # The earlier headings (CC_both_patient, DC_Urgency_patient) are still found, anywhere after the fixed columns.
    old = header[:24] + ["CC_both_patient", "DC_Urgency_patient", "DC_Dx_patient"]
    r = row("", "Migraine", "Meningitis", None, [None, None, None])[:24] + ["Mine one.", "Mine two.", "Mine three."]
    save("en.xlsx", old, r)
    _, assets, _ = convert({"en": tmp_path / "en.xlsx"}, "v3", "approved")
    got = {(a["perspective"], a["slot"]): a["text"] for a in assets}
    assert (got[("patient", "supportive")], got[("patient", "discordant_dx")]) == ("Mine one.", "Mine three.")
