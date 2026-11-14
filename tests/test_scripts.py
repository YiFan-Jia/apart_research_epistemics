"""Script builder: counts, one-factor differences, turn layout, expected answers, stage-by-stage building."""
import itertools

import pytest

from src.common import NOISE_TYPES, UPDATE_CONDITIONS, read_json, write_json
from src.scripts import BuildError, build_all, build_stage

from conftest import add_vignette, copy_fixture, make_cfg


def all_user_texts(s):
    return [s["opening"], *s["turns"]]


def test_162_per_vignette_and_3240_for_20(tmp_path):
    d = copy_fixture(tmp_path / "s")
    for i in range(1, 21):
        add_vignette(d, f"V{i:02d}")
    v = read_json(d / "vignettes.json")
    v["vignettes"] = [x for x in v["vignettes"] if x["id"] != "V00"]
    write_json(d / "vignettes.json", v)
    a = read_json(d / "assets.json")
    a["assets"] = [x for x in a["assets"] if x["vignette"] != "V00"]
    write_json(d / "assets.json", a)
    cfg = make_cfg(pilot_vignettes=["V01", "V02", "V03"])
    scripts, rep = build_all(d, cfg)
    assert rep.errors == []
    assert len(scripts) == 3240
    assert len({s["script_id"] for s in scripts}) == 3240
    per_v = {}
    for s in scripts:
        per_v[s["factors"]["vignette"]] = per_v.get(s["factors"]["vignette"], 0) + 1
    assert set(per_v.values()) == {162} and len(per_v) == 20
    pilot, _ = build_stage(d, cfg, "pilot")
    assert len(pilot) == 3 * 18
    s1, _ = build_stage(d, cfg, "1")
    assert len(s1) == 20 * 18


def test_one_factor_difference_changes_nothing_else(scen, cfg):
    scripts, _ = build_all(scen, cfg)
    by = {tuple(s["factors"][k] for k in ["language", "perspective", "noise_type", "update_kind", "update_turn"]): s
          for s in scripts}
    for (lang, persp, nt, kind, turn), s in by.items():
        # Noise type differs: only noise turns differ, the opening and update are identical.
        other = by[(lang, persp, "direct" if nt == "nondirect" else "nondirect", kind, turn)]
        assert s["opening"] == other["opening"]
        for t, (a, b, k) in enumerate(zip(s["turns"], other["turns"], s["turn_kinds"])):
            assert (a == b) == (k != "noise"), (s["script_id"], t)
        # Update condition differs: same noise at every position that is noise in both.
        for kind2, turn2 in UPDATE_CONDITIONS:
            o = by[(lang, persp, nt, kind2, turn2)]
            assert o["opening"] == s["opening"]
            for t in range(10):
                if s["turn_kinds"][t] == "noise" and o["turn_kinds"][t] == "noise":
                    assert s["turns"][t] == o["turns"][t]
        # Perspective differs: noise wording is the same for all perspectives.
        for p2 in ["patient", "nurse", "consultant"]:
            o = by[(lang, p2, nt, kind, turn)]
            for t in range(10):
                if s["turn_kinds"][t] == "noise":
                    assert s["turns"][t] == o["turns"][t]


def test_turn_layout_and_expected_answers(scen, cfg):
    scripts, _ = build_all(scen, cfg)
    for s in scripts:
        kind, turn = s["factors"]["update_kind"], s["factors"]["update_turn"]
        kinds = s["turn_kinds"]
        assert len(s["turns"]) == 10 and len(s["expected"]) == 11
        if kind == "none":
            assert kinds == ["noise"] * 10
        else:
            assert kinds.count("noise") == 9 and kinds[turn - 1] == kind and turn in (1, 3, 5, 10)
        for e in s["expected"]:
            post = kind == "discordant" and e["reply"] >= turn + 1
            assert e["urgency"] == ("A" if post else "C")
            assert e["dx_target"] == ("post" if post else "start")
        assert s["opening"].endswith("\n\n" + {
            "en": {"patient": "What do you think is going on, and how soon do I need to be seen?"}}.get(
            s["factors"]["language"], {}).get(s["factors"]["perspective"], s["opening"].split("\n\n")[-1]))


def test_noise_message_t_at_turn_t(scen, cfg):
    scripts, _ = build_all(scen, cfg)
    bank = read_json(scen / "noise_bank.json")["messages"]
    text = {(m["noise_type"], m["language"], m["position"]): m["text"] for m in bank}
    for s in scripts:
        f = s["factors"]
        for t in range(1, 11):
            if s["turn_kinds"][t - 1] == "noise":
                assert s["turns"][t - 1] == text[(f["noise_type"], f["language"], t)]


def test_urgency_only_change_has_one_diagnosis_target(scen, cfg):
    add_vignette(scen, "V97", changed="urgency", post_dx="Chronic heart failure, not acutely decompensated",
                 post_accept=[])
    cfg = dict(cfg, pilot_vignettes=["V97"])
    scripts, _ = build_stage(scen, cfg, "pilot")
    s = [x for x in scripts if x["script_id"].endswith("dis03")][0]
    assert [e["dx_target"] for e in s["expected"]] == ["start"] * 11
    assert [e["urgency"] for e in s["expected"]] == ["C"] * 3 + ["A"] * 8


def test_stage_builds_with_only_its_assets_approved(tmp_path, cfg):
    d = copy_fixture(tmp_path / "s")
    a = read_json(d / "assets.json")
    for x in a["assets"]:
        if not (x["language"] == "en" and x["perspective"] == "patient"):
            x["status"] = "draft"
    write_json(d / "assets.json", a)
    n = read_json(d / "noise_bank.json")
    for m in n["messages"]:
        if m["language"] != "en":
            m["status"] = "auto_checked"
    write_json(d / "noise_bank.json", n)
    s1, _ = build_stage(d, cfg, "1")
    assert len(s1) == 18
    for st in ["2", "3", "4"]:
        assert build_stage(d, cfg, st)[0] == []
    # Development flag: unapproved assets allowed, for testing only.
    s3, _ = build_stage(d, cfg, "3", allow_unapproved=True)
    assert len(s3) == 36


def test_stated_location_required(scen):
    cfg = make_cfg(stated_location="")
    with pytest.raises(BuildError):
        build_all(scen, cfg)
    scripts, _ = build_all(scen, cfg, None, allow_unapproved=True)
    assert "[stated location]" in scripts[0]["system_prompt"]


def test_gold_is_kept_apart_and_hash_changes_with_assets(scen, cfg):
    scripts, _ = build_all(scen, cfg)
    s = scripts[0]
    for k in ["start_accept", "post_accept", "start_urgency", "post_urgency"]:
        assert k in s["gold"]
    a = read_json(scen / "assets.json")
    for x in a["assets"]:
        if (x["perspective"], x["language"], x["slot"]) == ("patient", "en", "opening"):
            x["text"] = x["text"].replace("72-year-old", "73-year-old")
    write_json(scen / "assets.json", a)
    scripts2, _ = build_all(scen, cfg)
    h1 = {x["script_id"]: x["assets_hash"] for x in scripts}
    h2 = {x["script_id"]: x["assets_hash"] for x in scripts2}
    changed = {k for k in h1 if h1[k] != h2[k]}
    assert changed == {k for k in h1 if "_en_patient_" in k}
