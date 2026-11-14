"""Validator: passes the fixture; names each missing slot in a deliberately broken copy; partial deliveries."""
from src.assets import validate
from src.common import read_json, write_json

from conftest import copy_fixture


def test_fixture_passes_every_stage(tmp_path, cfg):
    d = copy_fixture(tmp_path / "s")
    rep = validate(d, cfg)
    assert rep.errors == []
    for stage in cfg["stages"]:
        assert rep.ready_vignettes(stage) == ["V00"], stage


def test_broken_copy_names_each_missing_slot(tmp_path, cfg):
    d = copy_fixture(tmp_path / "s")
    a = read_json(d / "assets.json")
    drop = {("V00", "nurse", "en", "discordant"), ("V00", "patient", "zh", "opening"), ("V00", "consultant", "ja", "supportive")}
    a["assets"] = [x for x in a["assets"] if (x["vignette"], x["perspective"], x["language"], x["slot"]) not in drop]
    write_json(d / "assets.json", a)
    rep = validate(d, cfg)
    text = "\n".join(p for s in rep.stages.values() for ps in s["not_ready"].values() for p in ps)
    assert "V00 en nurse discordant: missing" in text
    assert "V00 zh patient opening: missing" in text
    assert "V00 ja consultant supportive: missing" in text
    # Stages that do not use the missing slots stay ready.
    assert rep.ready_vignettes("pilot") == ["V00"]
    assert rep.ready_vignettes("1") == ["V00"]
    assert rep.ready_vignettes("2") == []
    assert rep.ready_vignettes("3") == []
    assert rep.ready_vignettes("4") == []


def test_partial_delivery_english_patient_only(tmp_path, cfg):
    d = copy_fixture(tmp_path / "s")
    a = read_json(d / "assets.json")
    a["assets"] = [x for x in a["assets"] if x["language"] == "en" and x["perspective"] == "patient"]
    write_json(d / "assets.json", a)
    n = read_json(d / "noise_bank.json")
    n["messages"] = [m for m in n["messages"] if m["language"] == "en"]
    write_json(d / "noise_bank.json", n)
    rep = validate(d, cfg)
    assert rep.errors == []
    assert rep.ready_vignettes("pilot") == ["V00"] and rep.ready_vignettes("1") == ["V00"]
    assert rep.ready_vignettes("2") == [] and rep.ready_vignettes("3") == []
    assert any("noise zh nondirect" in p for p in rep.stages["3"]["blocking"])


def test_content_checks(tmp_path, cfg):
    d = copy_fixture(tmp_path / "s")
    a = read_json(d / "assets.json")
    for x in a["assets"]:
        k = (x["perspective"], x["language"], x["slot"])
        if k == ("patient", "zh", "supportive"):
            x["text"] = "The breathlessness comes on uphill."          # English in the Chinese slot
        if k == ("patient", "ja", "supportive"):
            x["text"] = "我走上坡路时会气喘。"                           # Chinese, no kana, in the Japanese slot
        if k == ("nurse", "en", "supportive"):
            x["text"] = " Leading space and  double space."
        if k == ("consultant", "en", "supportive"):
            x["text"] = "TODO: rewrite this one"
        if k == ("nurse", "zh", "opening"):
            x["status"] = "draft"
        if k == ("consultant", "zh", "discordant"):
            x["text"] = [y for y in a["assets"] if (y["perspective"], y["language"], y["slot"]) ==
                         ("consultant", "zh", "supportive")][0]["text"]
    write_json(d / "assets.json", a)
    rep = validate(d, cfg)
    probs = "\n".join(p for ps in rep.unit_problems.values() for p in ps)
    assert "V00 zh patient supportive: no Chinese characters" in probs
    assert "V00 ja patient supportive: no Japanese kana" in probs
    assert "V00 en nurse supportive: leading or trailing whitespace" in probs
    assert "stray whitespace" in probs
    assert "V00 en consultant supportive: looks like a leftover note" in probs
    assert "V00 zh nurse opening: status is draft (needs approved)" in probs
    assert "V00 zh consultant: supportive and discordant updates are the same" in probs
    rep2 = validate(d, cfg, allow_unapproved=True)
    assert not any("status is draft" in p for ps in rep2.unit_problems.values() for p in ps)


def test_vignette_record_checks(tmp_path, cfg):
    d = copy_fixture(tmp_path / "s")
    v = read_json(d / "vignettes.json")
    bad = dict(v["vignettes"][0], id="V01", start_urgency="E", post_accept="not a list")
    bad2 = dict(v["vignettes"][0], id="V02", changed="diagnosis")         # but urgency differs C -> A
    bad3 = dict(v["vignettes"][0], id="V03", post_accept=["chronic heart failure"])  # overlaps start
    v["vignettes"] += [bad, bad2, bad3, dict(v["vignettes"][0])]           # last one duplicates V00
    write_json(d / "vignettes.json", v)
    rep = validate(d, cfg)
    errs = "\n".join(rep.errors)
    assert "duplicate id V00" in errs
    assert "V01: field 'start_urgency' must be one of A, B, C, D" in errs
    assert "V01: field 'post_accept' must be a list" in errs
    assert "V02: changed is 'diagnosis' but the urgency differs" in errs
    assert any("V03: start and post accepted names overlap" in w for w in rep.warnings)


def test_opening_must_not_include_ask(tmp_path, cfg):
    d = copy_fixture(tmp_path / "s")
    a = read_json(d / "assets.json")
    ask = [x for x in read_json(d / "prompts.json")["asks"] if (x["perspective"], x["language"]) == ("patient", "en")][0]
    for x in a["assets"]:
        if (x["perspective"], x["language"], x["slot"]) == ("patient", "en", "opening"):
            x["text"] = x["text"] + " " + ask["text"]
    write_json(d / "assets.json", a)
    rep = validate(d, cfg)
    assert any("includes the ask" in p for p in rep.unit_problems[("V00", "en", "patient")])
