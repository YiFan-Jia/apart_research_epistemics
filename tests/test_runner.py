"""Run database, runner and mock model, end to end at zero spend."""
import asyncio
import json
import sqlite3
import subprocess
import sys
import time

import pandas as pd
import pytest

from src import db as dbm
from src.clients import FatalError, MockModel, MockParams, RetryableError
from src.common import read_json, read_jsonl, write_json
from src.judge import DiagnosisJudge, FunctionJudge
from src.runner import (
    ALLOWED_REQUEST_KEYS, EXIT_HALTED, EXIT_OK, EXIT_SPEND_CAP, RunRefused, Runner, build_request, export_transcripts,
)
from src.score import aggregate, build_conversation_table, build_long_table

from conftest import ROOT, load_scripts, make_cfg


def make_runner(tmp_path, cfg, scen, models=("haiku",), stage="pilot", mock_params=None, error_plan=None,
                empty_plan=None, run="r1", add=True):
    r = Runner(tmp_path / run, cfg, scen, {}, mock=True, quiet=True, status_every_s=999)
    r.open()
    r.check_assets_unchanged()
    if add:
        r.add_stage(stage, list(models))
    scripts = list(load_scripts(scen).values())
    r.clients = {m: MockModel(scripts, MockParams(**(mock_params or {})), name=m, error_plan=error_plan,
                              empty_plan=empty_plan) for m in models}
    return r


def run(r, models=("haiku",)):
    return asyncio.run(r.execute(list(models)))


def reply_counts(db):
    return {row[0]: row[1] for row in db.execute(
        "SELECT j.job_id, COUNT(r.reply_no) FROM jobs j LEFT JOIN replies r ON r.job_id=j.job_id GROUP BY j.job_id")}


def test_end_to_end_two_models(tmp_path, cfg, scen, capsys):
    r = make_runner(tmp_path, cfg, scen, models=("haiku", "sonnet"))
    assert run(r, ("haiku", "sonnet")) == EXIT_OK
    counts = reply_counts(r.db)
    assert len(counts) == 36 and set(counts.values()) == {11}
    blocks = r.db.execute("SELECT COUNT(*) FROM blocks WHERE completed_at IS NOT NULL").fetchone()[0]
    assert blocks == 2
    # Console shows counts and status only, never reply text.
    out = capsys.readouterr().out
    assert "Mock reply" not in out and "ASSESSMENT" not in out


def test_no_request_contains_gold_or_later_turns(tmp_path, cfg, scen):
    r = make_runner(tmp_path, cfg, scen, models=("haiku", "sonnet"))
    run(r, ("haiku", "sonnet"))
    scripts = list(load_scripts(scen).values())
    gold_words = set()
    for s in scripts:
        g = s["gold"]
        gold_words |= {x.lower() for x in [g["start_dx"], g["post_dx"], *g["start_accept"], *g["post_accept"]]}
    gold_words |= {"supportive", "discordant", "start_urgency", "post_urgency", "expected", "dx_target"}
    for model, client in r.clients.items():
        assert client.requests
        for req in client.requests:
            assert set(req) <= ALLOWED_REQUEST_KEYS
            assert not ({"temperature", "top_p", "top_k"} & set(req))
            assert req["cache_control"] == {"type": "ephemeral"}
            assert req["thinking"] == cfg["models"][model]["request_options"]["thinking"]
            assert req["max_tokens"] == 1024 and req["model"] == cfg["models"][model]["api_model"]
            # What the pipeline sends (system prompt and user turns). The model's own replies are its own words.
            text = (req["system"] + "\n" + "\n".join(m["content"] for m in req["messages"]
                                                     if m["role"] == "user")).lower()
            assert not [w for w in gold_words if w in text]
            assert req["messages"][-1]["role"] == "user"
            for m in req["messages"]:
                assert isinstance(m["content"], str)          # assistant history as text only
    # Each request holds exactly the scripted user turns so far, never a later one.
    by_unit = {}
    for s in scripts:
        by_unit.setdefault((s["system_prompt"], s["opening"]), []).append(s)
    for req in r.clients["haiku"].requests:
        users = [m["content"] for m in req["messages"] if m["role"] == "user"]
        k = len(users)
        cands = [s for s in by_unit[(req["system"], users[0])] if s["turns"][: k - 1] == users[1:]]
        assert cands, "request user turns do not match any script prefix"


def test_build_request_per_model(cfg, scen):
    s = next(iter(load_scripts(scen).values()))
    h = build_request(s, ["first reply"], cfg["models"]["haiku"], cfg)
    assert h["thinking"] == {"type": "disabled"} and h["model"] == "claude-haiku-5-5"
    so = build_request(s, ["first reply"], cfg["models"]["sonnet"], cfg)
    assert so["thinking"] == {"type": "between_tools"} and so["model"] == "claude-sonnet-5-5"
    assert [m["role"] for m in h["messages"]] == ["user", "assistant", "user"]
    assert h["messages"][2]["content"] == s["turns"][0]
    bad = dict(cfg["models"]["haiku"], request_options={"temperature": 0.7})
    with pytest.raises(ValueError):
        build_request(s, [], bad, cfg)


def test_duplicate_reply_rejected_and_half_write_rolled_back(tmp_path, cfg, scen, monkeypatch):
    r = make_runner(tmp_path, cfg, scen)
    run(r)
    job = r.db.execute("SELECT job_id FROM jobs LIMIT 1").fetchone()[0]
    row = dict(r.db.execute("SELECT * FROM replies WHERE job_id=? AND reply_no=1", (job,)).fetchone())
    with pytest.raises(sqlite3.IntegrityError):
        dbm.commit_reply(r.db, job, "haiku", 1, row, {"job_id": job, "model": "haiku", "reply_no": 1,
                                                       "started_at": dbm.now(), "outcome": "ok"})
    # A failure between the reply insert and the commit leaves nothing behind.
    db2 = dbm.connect(tmp_path / "x.sqlite")
    db2.execute("INSERT INTO jobs (job_id, model, script_id, repeat, stage, stage_index, order_key, script_json, "
                "assets_hash, created_at) VALUES ('j','m','s',1,'pilot',0,'k','{}','h','t')")

    def boom(*a, **k):
        raise RuntimeError("power cut")

    monkeypatch.setattr(dbm, "insert_attempt", boom)
    with pytest.raises(RuntimeError):
        dbm.commit_reply(db2, "j", "m", 1, row, {})
    assert db2.execute("SELECT COUNT(*) FROM replies").fetchone()[0] == 0


def test_kill_and_resume_no_duplicates_or_gaps(tmp_path, scen):
    """Kill the runner process part-way, resume it, and check every conversation has replies 1..11 exactly once."""
    cfg = make_cfg()
    cfg["stages"]["1"]["repeats"] = 3
    cfg_path = tmp_path / "cfg.json"
    write_json(cfg_path, cfg)
    results = tmp_path / "results"
    base = [sys.executable, "-m", "src.runner", "run", "--run", "killme", "--results", str(results),
            "--scenarios", str(scen), "--mock", "--mock-params", json.dumps({"latency_s": 0.01})]
    p = subprocess.Popen(base + ["--stage", "1", "--models", "haiku", "--config", str(cfg_path)], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    dbp = results / "killme" / "run.sqlite"
    deadline = time.time() + 60
    n = 0
    while time.time() < deadline:
        if dbp.exists():
            try:
                c = sqlite3.connect(dbp)
                n = c.execute("SELECT COUNT(*) FROM replies").fetchone()[0]
                c.close()
            except sqlite3.Error:
                n = 0
            if n >= 80:
                break
        time.sleep(0.05)
    p.kill()
    p.wait()
    assert 80 <= n < 54 * 11, f"kill happened at an unhelpful point ({n} replies)"
    c = sqlite3.connect(dbp)
    partial = c.execute("SELECT COUNT(*) FROM replies").fetchone()[0]
    c.close()
    assert partial < 54 * 11
    res = subprocess.run(base, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert res.returncode == 0, res.stdout + res.stderr
    db = dbm.connect(dbp)
    rows = db.execute("SELECT job_id, GROUP_CONCAT(reply_no) FROM replies GROUP BY job_id").fetchall()
    assert len(rows) == 54
    for job, nos in rows:
        assert sorted(map(int, nos.split(","))) == list(range(1, 12)), job
    assert db.execute("SELECT COUNT(*) FROM jobs WHERE status='complete'").fetchone()[0] == 54


def test_empty_reply_ends_conversation(tmp_path, cfg, scen):
    noise3 = "Could you reconsider?"
    r = make_runner(tmp_path, cfg, scen,
                    empty_plan=lambda req, k: k == 4 and req["messages"][-1]["content"] == noise3)
    assert run(r) == EXIT_OK
    ended = r.db.execute("SELECT job_id, end_reason FROM jobs WHERE status='ended'").fetchall()
    # Nondirect scripts whose turn 3 is noise: the control and every update not at turn 3.
    assert len(ended) == 7 and {e[1] for e in ended} == {"empty_reply_at_4"}
    counts = reply_counts(r.db)
    assert all(counts[e[0]] == 4 for e in ended)
    dbm.update_blocks(r.db)
    long_df = build_long_table(r.db, DiagnosisJudge(None, "t"))
    rows = long_df[long_df.job_id == ended[0][0]].sort_values("reply")
    assert rows.iloc[3]["status"] == "technical_failure"
    assert set(rows.iloc[4:]["status"]) == {"technical_failure"}
    assert set(rows.iloc[4:]["missing_reason"]) == {"empty_reply_at_4"}


def test_spend_cap_stops_new_conversations(tmp_path, scen):
    cfg = make_cfg()
    cfg["models"]["sonnet"]["concurrency"] = 2
    cfg["models"]["sonnet"]["spend_cap_usd"] = 0.03
    r = make_runner(tmp_path, cfg, scen, models=("sonnet",))
    assert run(r, ("sonnet",)) == EXIT_SPEND_CAP
    spend = dbm.spend_by_model(r.db)["sonnet"]
    per_conv = [row[0] for row in r.db.execute(
        "SELECT SUM(cost_usd) FROM attempts GROUP BY job_id")]
    started = len(per_conv)
    assert 0 < started < 18
    # Overshoot is at most the conversations in flight when the cap was reached.
    assert spend >= 0.03 and spend <= 0.03 + 2 * max(per_conv)
    assert r.db.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0] == 18 - started


def test_fatal_error_stops_run_at_once(tmp_path, cfg, scen):
    r = make_runner(tmp_path, cfg, scen,
                    error_plan=lambda req, i: FatalError("credit balance too low", 400, "BadRequestError") if i >= 3 else None)
    assert run(r) == EXIT_HALTED
    fatal = r.db.execute("SELECT COUNT(*) FROM attempts WHERE outcome='fatal_error'").fetchone()[0]
    calls = r.clients["haiku"].calls
    # Every request after the first fatal one would fail the same way: at most the in-flight requests are made.
    assert fatal >= 1 and calls <= 2 + cfg["models"]["haiku"]["concurrency"]
    assert "BadRequestError" in r.halted
    assert r.db.execute("SELECT COUNT(*) FROM jobs WHERE status='complete'").fetchone()[0] == 0


def test_retryable_errors_are_retried(tmp_path, cfg, scen):
    r = make_runner(tmp_path, cfg, scen,
                    error_plan=lambda req, i: RetryableError("overloaded", 529, None, "OverloadedError") if i % 4 == 0 else None)
    assert run(r) == EXIT_OK
    assert set(reply_counts(r.db).values()) == {11}
    retries = r.db.execute("SELECT COUNT(*) FROM attempts WHERE outcome='retryable_error'").fetchone()[0]
    ok = r.db.execute("SELECT COUNT(*) FROM attempts WHERE outcome='ok'").fetchone()[0]
    assert retries > 0 and ok == 18 * 11


def test_circuit_breaker(tmp_path, cfg, scen):
    r = make_runner(tmp_path, cfg, scen, error_plan=lambda req, i: RetryableError("server error", 500))
    assert run(r) == EXIT_HALTED
    assert "circuit breaker" in r.halted
    n = r.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    assert n <= cfg["runner"]["circuit_breaker_failures"] + cfg["models"]["haiku"]["concurrency"]


def test_resume_refused_after_assets_change(tmp_path, cfg, scen):
    r = make_runner(tmp_path, cfg, scen)
    run(r)
    r.db.close()
    # Changing an asset the run does not use (Chinese) is fine.
    a = read_json(scen / "assets.json")
    for x in a["assets"]:
        if (x["perspective"], x["language"], x["slot"]) == ("patient", "zh", "supportive"):
            x["text"] = "我走上坡路时会气喘，休息几分钟后就能缓解。"
    write_json(scen / "assets.json", a)
    make_runner(tmp_path, cfg, scen, add=False)
    # Changing an asset the run uses is refused.
    for x in a["assets"]:
        if (x["perspective"], x["language"], x["slot"]) == ("patient", "en", "supportive"):
            x["text"] = "The breathlessness comes on when I walk up a hill and settles after a few minutes of rest."
    write_json(scen / "assets.json", a)
    with pytest.raises(RunRefused, match="assets have changed"):
        make_runner(tmp_path, cfg, scen, add=False)
    # So is a changed config, or switching between mock and real.
    with pytest.raises(RunRefused, match="config.json has changed"):
        Runner(tmp_path / "r1", make_cfg(max_tokens=2048), scen, {}, mock=True, quiet=True).open()
    with pytest.raises(RunRefused, match="mock versus real"):
        Runner(tmp_path / "r1", cfg, scen, {}, mock=False, quiet=True).open()


def test_stale_scripts_file_refused(tmp_path, cfg, scen):
    a = read_json(scen / "assets.json")
    for x in a["assets"]:
        if (x["perspective"], x["language"], x["slot"]) == ("patient", "en", "opening"):
            x["text"] = x["text"].replace("72-year-old", "73-year-old")
    write_json(scen / "assets.json", a)
    with pytest.raises(RunRefused, match="out of date"):
        make_runner(tmp_path, cfg, scen)


def test_scorer_recovers_mock_rates(tmp_path, scen):
    cfg = make_cfg()
    cfg["stages"]["1"]["repeats"] = 20
    cfg["models"]["haiku"]["concurrency"] = 32
    params = {"p_correct_baseline": 0.75, "p_flip": {"nondirect": 0.10, "direct": 0.35}, "p_uptake": 0.6,
              "p_malformed": 0.03, "seed": 7}
    r = make_runner(tmp_path, cfg, scen, stage="1", mock_params=params)
    assert run(r) == EXIT_OK
    judge = DiagnosisJudge(None, "t", FunctionJudge(lambda t, g, k: ("Mock wrong diagnosis", "neither")))
    long_df = build_long_table(r.db, judge)
    conv = build_conversation_table(long_df)
    agg = aggregate(conv)

    def rate(measure, gb="noise_type", gv=None):
        a = agg[(agg.measure == measure) & (agg.group_by == gb)]
        if gv is not None:
            a = a[a.group_value == gv]
        sub = a.iloc[0]
        return sub.successes / sub.valid, sub.valid

    for nt, p in params["p_flip"].items():
        moves = valid = 0
        for stratum in ["control", "pre", "post"]:
            a = agg[(agg.measure == f"u_noise_{stratum}_movement") & (agg.group_by == "noise_type") & (agg.group_value == nt)]
            moves += a.successes.sum()
            valid += a.valid.sum()
        se = (p * (1 - p) / valid) ** 0.5
        assert abs(moves / valid - p) < 4 * se, (nt, moves / valid, p)
    est, n = rate("u_disc_adoption", "all", "all")
    assert abs(est - params["p_uptake"]) < 4 * (0.24 / n) ** 0.5, est
    est, n = rate("u_baseline_correct", "all", "all") if "u_baseline_correct" in set(agg.measure) else (None, 0)
    base = conv["u_baseline_correct"].dropna().astype(bool)
    assert abs(base.mean() - params["p_correct_baseline"]) < 4 * (0.19 / len(base)) ** 0.5
    malformed = (long_df["status"] == "malformed").mean()
    assert abs(malformed - params["p_malformed"]) < 0.015


class CJKMock(MockModel):
    """Answers in the user's language with a full-width block, to test the round trip and the extractor."""

    async def create(self, request):
        resp = await super().create(request)
        last = request["messages"][-1]["content"]
        tbl = str.maketrans({c: chr(ord(c) + 0xFEE0) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:[]"})
        head, block = resp.text.split("[[ASSESSMENT]]")
        block = "[[ASSESSMENT]]" + block
        lines = block.split("\n")
        lines = [ln.translate(tbl) if not ln.startswith("Diagnosis:") else ln.split(":")[0].translate(tbl) + "：" +
                 ln.split(":", 1)[1] for ln in lines]
        resp.text = f"您好，こんにちは。您说：「{last[:20]}」\n\n" + "\n".join(lines)
        resp.content = [{"type": "text", "text": resp.text}]
        return resp


def test_chinese_and_japanese_round_trip(tmp_path, cfg, scen):
    r = make_runner(tmp_path, cfg, scen, stage="3")
    scripts = list(load_scripts(scen).values())
    r.clients = {"haiku": CJKMock(scripts, MockParams(p_malformed=0), name="haiku")}
    assert run(r) == EXIT_OK
    s_by = load_scripts(scen)
    for job_id, sid in r.db.execute("SELECT job_id, script_id FROM jobs").fetchall():
        reps = dbm.replies_for(r.db, job_id)
        assert reps[0]["user_text"] == s_by[sid]["opening"]
        assert [x["user_text"] for x in reps[1:]] == s_by[sid]["turns"]
        assert "こんにちは" in reps[0]["reply_text"]
    paths = export_transcripts(r.db, tmp_path / "r1")
    rows = read_jsonl(paths[0])
    js = {row["job_id"]: row for row in rows}
    one = r.db.execute("SELECT job_id, script_id FROM jobs WHERE script_id LIKE '%_ja_%' LIMIT 1").fetchone()
    assert js[one[0]]["turns"][0]["user"] == s_by[one[1]]["opening"]
    dbm.update_blocks(r.db)
    long_df = build_long_table(r.db, DiagnosisJudge(None, "t"), extractions_out=tmp_path / "ext.jsonl")
    assert long_df["urgency"].notna().all()      # full-width blocks parsed
    p = tmp_path / "long.csv"
    long_df.to_csv(p, index=False, encoding="utf-8")
    back = pd.read_csv(p, encoding="utf-8")
    assert back["diagnosis"].tolist() == long_df["diagnosis"].tolist()
    ext = read_jsonl(tmp_path / "ext.jsonl")
    assert len(ext) == len(long_df)
