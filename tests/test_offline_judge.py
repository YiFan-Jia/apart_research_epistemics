"""Judging the free-text diagnoses with no API: export the strings, import the decisions, score from the cache."""
from src.common import read_json, write_json
from src.judge import DiagnosisJudge, export_todo, import_done

GOLD = {"start_dx": "Migraine", "start_accept": ["migraine without aura"], "post_dx": "Meningitis",
        "post_accept": [], "changed": "both", "accepted_names_version": "nv1"}
NAME = "session-judge"


def judge(tmp_path, name=NAME):
    return DiagnosisJudge(tmp_path / "cache.sqlite", "judge-v2", None, offline_name=name)


def test_strings_are_exported_decided_outside_and_read_back_from_the_cache(tmp_path):
    items = [("V01", GOLD, "Migraine"),                          # an accepted name: never exported
             ("V01", GOLD, "Probable migraine; exclude meningitis"),
             ("V01", GOLD, "probable migraine; exclude meningitis."),   # the same string after normalising
             ("V01", GOLD, "细菌性脑膜炎"), ("V01", GOLD, "Tension headache"), ("V01", GOLD, None)]
    j = judge(tmp_path)
    out = tmp_path / "judge_offline"
    res = export_todo(j, items, out, chunk=2)
    assert (res["strings"], res["files"]) == (3, 2)
    first = read_json(out / "todo" / "V01_nv1_001.json")
    assert "Starting diagnosis: Migraine" in first["instructions"] and '"items"' in first["instructions"]
    assert first["judge_name"] == NAME and [it["i"] for it in first["items"]] == [1, 2]

    def decide(text):
        if "脑膜炎" in text:
            return {"leading": "post", "leading_name": "x", "modifiers": ["bacterial"], "alternatives": [], "uncertain": False}
        if "migraine" in text.lower():
            return {"leading": "start", "leading_name": "", "modifiers": [], "alternatives": ["Meningitis"], "uncertain": True}
        return {"leading": "other", "leading_name": "Tension-type headache", "modifiers": [], "alternatives": [], "uncertain": False}

    # Only the first file is answered, and one of its decisions cannot be used.
    ds = [dict(decide(it["text"]), i=it["i"]) for it in first["items"]]
    bad = dict(ds[1], leading="maybe")
    write_json(out / "done" / "V01_nv1_001.json", {"decisions": [ds[0], bad]})
    res = import_done(j, out)
    assert res["stored"] == 1 and res["files_waiting"] == ["V01_nv1_002.json"]
    assert len(res["problems"]) == 1 and "maybe" in res["problems"][0]
    assert len(j.pending(items)) == 2

    for name in ("V01_nv1_001.json", "V01_nv1_002.json"):
        todo = read_json(out / "todo" / name)
        write_json(out / "done" / name, {"decisions": [dict(decide(it["text"]), i=it["i"]) for it in todo["items"]]})
    res = import_done(j, out)
    assert res["stored"] == 3 and not res["problems"] and not res["files_waiting"] and j.pending(items) == []
    got = j.judge("V01", GOLD, "Probable migraine; exclude meningitis")
    assert (got["method"], got["match"], got["hedged"], got["leading_name"]) == ("model", "start", True, "Migraine")
    assert j.judge("V01", GOLD, "细菌性脑膜炎")["match"] == "post"
    assert j.judge("V01", GOLD, "Tension headache")["key"] == "other:tension-type headache"
    assert j.known("V01", "nv1") == ["Tension-type headache"]
    assert j.n_model_calls == 0 and j.spend() == 0
    assert export_todo(j, items, out)["files"] == 0 and not list((out / "todo").glob("*.json"))
    j.close()

    # The decisions belong to that judge name: another judge, or none, does not see them.
    other = judge(tmp_path, name=None)
    assert other.judge("V01", GOLD, "Tension headache")["method"] == "unjudged"
    other.close()
