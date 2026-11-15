"""The vignette-checking agent, with a scripted checker and the mock model: no model call."""
import pytest

from src.clients import MockModel, MockParams
from src.common import read_json, write_json
from src.runner import vignette_check_note
from src.vignette_check import (
    FIDELITY_CHECKS, KEY_CHECKS, ClientFactory, MockChecker, check_status, render_markdown, run_check,
)

from conftest import load_scripts, make_cfg


class ScriptedChecker(MockChecker):
    """Passes everything, except the checks named in `verdicts` ({check id: (verdict, comment)}),
    and records which kinds of prompt it was asked."""

    name = "scripted"

    def __init__(self, verdicts=None, facts_added=None):
        self.verdicts, self.facts_added, self.prompts = verdicts or {}, facts_added or {}, []

    def call(self, prompt, schema, system=None):
        self.prompts.append(prompt)
        data, meta = super().call(prompt, schema, system)
        for c in data.get("checks", []):
            if c["id"] in self.verdicts:
                c["verdict"], c["comment"] = self.verdicts[c["id"]]
        if "noise" in data:
            data["noise"] = [{"noise_type": nt, "position": p, "back_translation": "", "verdict": "pass", "comment": ""}
                             for nt in ("nondirect", "direct") for p in range(1, 11)]
            data["asks"] = [{"perspective": p, "back_translation": "", "verdict": "pass", "comment": ""}
                            for p in ("patient", "nurse", "consultant")]
        for marker, facts in self.facts_added.items():
            if "facts_added" in data and marker in prompt:
                data["facts_added"] = facts
        return data, meta


def mock_probe(cfg, **params):
    return {m: ClientFactory(lambda scripts, m=m: MockModel(scripts, MockParams(**params), name=m))
            for m in cfg["vignette_check"]["probe"]["models"]}


def check(tmp_path, scen, cfg, checker, name="c1", **kw):
    return run_check(scen, cfg, tmp_path / "vignette_checks" / name, checker_model=checker, cache_path=None,
                     log=lambda *_: None, **kw)


def test_clean_vignette_passes_and_is_then_known_to_the_runner(tmp_path, scen):
    cfg = make_cfg()
    checker = ScriptedChecker()
    rep = check(tmp_path, scen, cfg, checker,
                probe_clients=mock_probe(cfg, p_correct_baseline=1.0, p_uptake=1.0, p_malformed=0.0))
    assert rep["summary"] == {"V00": "PASS"}
    assert {s["verdict"] for s in rep["shared"].values()} == {"pass"}
    v = rep["vignettes"]["V00"]
    assert len(v["units"]) == 9 and len(v["probe"]) == 2 * 9 and v["probe_flags"] == []
    assert [c["id"] for c in v["key_review"]["key"]["checks"]] == list(KEY_CHECKS)
    # 1 blind + 1 key review, 9 versions, 3 languages of shared material.
    assert len(checker.prompts) == 2 + 9 + 3
    # The blind pass must not be shown the reference answers.
    blind = checker.prompts[0] if "<reference_answers>" not in checker.prompts[0] else checker.prompts[1]
    assert "Acute decompensated heart failure" not in blind and "<reference_answers>" not in blind
    assert "## V00: PASS" in render_markdown(rep)

    units = [("V00", l, p) for l in ("en", "zh", "ja") for p in ("patient", "nurse", "consultant")]
    st = check_status(scen, cfg, units, tmp_path / "vignette_checks")
    assert len(st["checked"]) == 9 and not st["unchecked"] and not st["blocked"]
    scripts = list(load_scripts(scen).values())
    assert vignette_check_note(scen, cfg, scripts, tmp_path) is None
    # Change one version's text: that version is no longer covered by the check, and the runner says so.
    a = read_json(scen / "assets.json")
    for x in a["assets"]:
        if (x["perspective"], x["language"], x["slot"]) == ("nurse", "ja", "opening"):
            x["text"] += "。"
    write_json(scen / "assets.json", a)
    st = check_status(scen, cfg, units, tmp_path / "vignette_checks")
    assert st["unchecked"] == ["V00 ja nurse"]
    assert "1 of 9 version(s) have no vignette check" in vignette_check_note(scen, cfg, scripts, tmp_path)
    # So is every version once the reference answers change.
    v = read_json(scen / "vignettes.json")
    v["vignettes"][0]["post_urgency"] = "B"
    write_json(scen / "vignettes.json", v)
    assert len(check_status(scen, cfg, units, tmp_path / "vignette_checks")["unchecked"]) == 9


def test_a_failed_reference_answer_blocks_and_an_added_fact_is_reported(tmp_path, scen):
    cfg = make_cfg()
    checker = ScriptedChecker(
        verdicts={"discordant_dx": ("fail", "The update does not point to the post-update diagnosis."),
                  "nothing_added": ("concern", "adds an onset pattern")},
        facts_added={'speaker="consultant"': ["gradual onset"]})
    rep = check(tmp_path, scen, cfg, checker, languages=["en"], skip_probe=True)
    v = rep["vignettes"]["V00"]
    assert rep["summary"] == {"V00": "BLOCK"} and v["n_fail"] == 1 and v["n_concern"] == 3
    assert v["units"]["en consultant"]["facts_added"] == ["gradual onset"]
    assert v["units"]["en patient"]["facts_added"] == []
    md = render_markdown(rep)
    assert "does not point to the post-update diagnosis" in md and "gradual onset" in md
    st = check_status(scen, cfg, [("V00", "en", "patient")], tmp_path / "vignette_checks")
    assert st["blocked"] == ["V00 en patient"]


def test_missing_language_blocks_and_scale_mismatch_is_a_structure_error(tmp_path, scen):
    cfg = make_cfg()
    a = read_json(scen / "assets.json")
    a["assets"] = [x for x in a["assets"] if x["language"] != "zh"]
    write_json(scen / "assets.json", a)
    v = read_json(scen / "vignettes.json")
    v["vignettes"][0]["urgency_scale_version"] = "v2"
    write_json(scen / "vignettes.json", v)
    rep = check(tmp_path, scen, cfg, ScriptedChecker(), skip_probe=True)
    r = rep["vignettes"]["V00"]
    assert r["verdict"] == "BLOCK"
    assert sorted(r["missing_units"]) == ["zh consultant", "zh nurse", "zh patient"]
    assert any("urgency_scale_version" in e for e in r["structure_errors"])
    assert r["units"]["ja patient"]["verdict"] == "pass"


def test_probe_flags_a_model_that_disagrees_with_the_reference(tmp_path, scen):
    cfg = make_cfg()
    # The mock never gives the reference baseline, and never takes up the discordant update.
    rep = check(tmp_path, scen, cfg, ScriptedChecker(), languages=["en"], perspectives=["patient"],
                probe_clients=mock_probe(cfg, p_correct_baseline=0.0, p_uptake=0.0, p_malformed=0.0))
    v = rep["vignettes"]["V00"]
    assert v["verdict"] == "REVIEW" and v["n_fail"] == 0
    flags = " | ".join(v["probe_flags"])
    assert "after the discordant update, urgency" in flags and "reference A" in flags
    cell = v["probe"][0]
    assert cell["conversations"] == 2 * cfg["vignette_check"]["probe"]["repeats"]
    assert cell["reference"]["start_urgency"] == "C" and "C" not in cell["baseline_urgency"]
    assert rep["probe"]["replies"] == 2 * 2 * 2 * cfg["vignette_check"]["probe"]["repeats"]


def test_a_check_the_model_leaves_out_is_a_concern_not_a_pass(tmp_path, scen):
    class Forgetful(ScriptedChecker):
        def call(self, prompt, schema, system=None):
            data, meta = super().call(prompt, schema, system)
            if "facts_added" in data:
                data["checks"] = [c for c in data["checks"] if c["id"] != "speaker"]
            return data, meta

    cfg = make_cfg()
    rep = check(tmp_path, scen, cfg, Forgetful(), languages=["en"], perspectives=["nurse"], skip_probe=True)
    u = rep["vignettes"]["V00"]["units"]["en nurse"]
    assert [c["id"] for c in u["checks"]] == list(FIDELITY_CHECKS)
    assert u["verdict"] == "concern" and rep["summary"] == {"V00": "REVIEW"}
