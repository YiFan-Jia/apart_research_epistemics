"""Job queue and runner (build spec 6.3). Run time.

Usage:
    python -m src.runner run --run pilot1 --stage pilot --models haiku              # real API: costs money
    python -m src.runner run --run mock1 --stage pilot --models haiku sonnet --mock # mock model, zero spend
    python -m src.runner run --run pilot1                                           # resume an existing run
    python -m src.runner status --run pilot1
    python -m src.runner export --run pilot1
    python -m src.runner inspect --run smoke-haiku     # per-reply content block types, usage, cache reads

Rules carried out here: the script is frozen in the database when its job is created; a resumed
conversation continues from its last committed reply; requests carry only the system prompt, the scripted
user turns so far and the model's own replies as text; no sampling parameters are sent; rate-limit,
overload and server errors retry with backoff; invalid-request, authentication and billing errors stop
the whole run; a reply with no text ends its conversation; the console never shows reply text.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from . import db as dbm
from .assets import validate
from .clients import AnthropicModel, FatalError, MockModel, MockParams, RetryableError, cost_usd
from .common import (
    N_REPLIES, ROOT, code_version, config_hash, load_config, load_dotenv_if_present, read_json, read_jsonl, sha,
    write_json, write_jsonl,
)
from .scripts import rebuild_scripts

EXIT_OK, EXIT_INCOMPLETE, EXIT_HALTED, EXIT_SPEND_CAP, EXIT_REFUSED = 0, 1, 3, 4, 5


class RunRefused(Exception):
    pass


# ================================================================ request

ALLOWED_REQUEST_KEYS = {"model", "max_tokens", "system", "messages", "cache_control", "thinking", "output_config"}
SAMPLING_KEYS = {"temperature", "top_p", "top_k"}


def build_request(script: dict, reply_texts: list[str], model_cfg: dict, cfg: dict) -> dict:
    """The request for the next reply: system prompt, scripted user turns so far, the model's replies as text."""
    n = len(reply_texts)
    if n >= N_REPLIES:
        raise ValueError("conversation already complete")
    messages = [{"role": "user", "content": script["opening"]}]
    for i, text in enumerate(reply_texts):
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": script["turns"][i]})
    opts = dict(model_cfg.get("request_options", {}))
    bad = SAMPLING_KEYS & set(opts)
    if bad:
        raise ValueError(f"sampling parameters {sorted(bad)} are not accepted by these models; remove them from config")
    req = {"model": model_cfg["api_model"], "max_tokens": cfg["max_tokens"], "system": script["system_prompt"],
           "messages": messages}
    if cfg.get("cache_control"):
        req["cache_control"] = cfg["cache_control"]
    req.update(opts)
    return req


# ================================================================ run setup

def stage_scripts(scripts: list[dict], cfg: dict, stage: str, ready: list[str]) -> list[dict]:
    sdef = cfg["stages"][stage]
    return [s for s in scripts
            if s["factors"]["language"] in sdef["languages"] and s["factors"]["perspective"] in sdef["perspectives"]
            and s["factors"]["vignette"] in ready]


def order_key(seed, script_id, repeat) -> str:
    return sha({"seed": seed, "script": script_id, "repeat": repeat})


class Runner:
    def __init__(self, run_dir: Path, cfg: dict, scenarios_dir: Path, clients: dict, *, mock: bool = False,
                 allow_unapproved: bool = False, status_every_s: float = 15.0, quiet: bool = False):
        self.run_dir = Path(run_dir)
        self.cfg = cfg
        self.scen = Path(scenarios_dir)
        self.clients = clients              # model name -> client with async create()
        self.mock = mock
        self.allow_unapproved = allow_unapproved
        self.status_every_s = status_every_s
        self.quiet = quiet
        self.chash = config_hash(cfg)
        self.halted: str | None = None
        self.spend_capped: set[str] = set()
        self.db: sqlite3.Connection | None = None

    def log(self, msg: str) -> None:
        if not self.quiet:
            print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)

    # ------------------------------------------------------------ setup and checks

    def open(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.db = dbm.connect(self.run_dir / "run.sqlite")
        existing = dbm.get_meta(self.db, "config_hash")
        if existing is None:
            dbm.set_meta(self.db, "run_name", self.run_dir.name)
            dbm.set_meta(self.db, "created_at", dbm.now())
            dbm.set_meta(self.db, "config_hash", self.chash)
            dbm.set_meta(self.db, "mock", self.mock)
            dbm.set_meta(self.db, "allow_unapproved", self.allow_unapproved)
            dbm.set_meta(self.db, "scenarios_dir", str(self.scen))
            write_json(self.run_dir / "config.json", self.cfg)
        else:
            if existing != self.chash:
                raise RunRefused("config.json has changed since this run started (models, request options, max_tokens, "
                                 "location or urgency wording). Start a new run name.")
            if dbm.get_meta(self.db, "mock") != self.mock:
                raise RunRefused("this run was started with a different client (mock versus real API); "
                                 "never mix them in one run. Start a new run name.")
            if dbm.get_meta(self.db, "allow_unapproved") != self.allow_unapproved:
                raise RunRefused("this run was started with a different --allow-unapproved setting.")

    def check_assets_unchanged(self) -> None:
        """Refuse to continue if any asset used by an existing job has changed since its script was frozen."""
        rows = self.db.execute("SELECT DISTINCT script_id, assets_hash FROM jobs").fetchall()
        if not rows:
            return
        rebuilt = rebuild_scripts(self.scen, self.cfg, [r["script_id"] for r in rows], self.allow_unapproved)
        changed = [r["script_id"] for r in rows
                   if rebuilt.get(r["script_id"]) is None or rebuilt[r["script_id"]]["assets_hash"] != r["assets_hash"]]
        if changed:
            raise RunRefused(f"assets have changed since this run started ({len(changed)} script(s) differ, e.g. "
                             f"{changed[0]}). The runner never mixes asset versions in one run: start a new run name.")

    def add_stage(self, stage: str, models: list[str], limit: int | None = None) -> int:
        if stage not in self.cfg["stages"]:
            raise RunRefused(f"unknown stage {stage!r}; stages are {list(self.cfg['stages'])}")
        path = self.scen / "scripts.jsonl"
        if not path.exists():
            raise RunRefused(f"{path} not found; build the scripts first (python -m src.scripts)")
        rep = validate(self.scen, self.cfg, self.allow_unapproved)
        ready = rep.ready_vignettes(stage)
        if not ready:
            raise RunRefused(f"no vignette is ready for stage {stage}; run python -m src.assets to see why")
        scripts = stage_scripts(read_jsonl(path), self.cfg, stage, ready)
        if limit:
            scripts = scripts[:limit]
        if not scripts:
            raise RunRefused(f"scripts.jsonl has no scripts for stage {stage}; rebuild with python -m src.scripts")
        rebuilt = rebuild_scripts(self.scen, self.cfg, [s["script_id"] for s in scripts], self.allow_unapproved)
        stale = [s["script_id"] for s in scripts
                 if rebuilt.get(s["script_id"]) is None or rebuilt[s["script_id"]]["assets_hash"] != s["assets_hash"]]
        if stale:
            raise RunRefused(f"scripts.jsonl is out of date with the scenario files ({len(stale)} script(s), e.g. "
                             f"{stale[0]}); rebuild with python -m src.scripts")
        stage_index = list(self.cfg["stages"]).index(stage)
        repeats = self.cfg["stages"][stage]["repeats"]
        seed = self.cfg["runner"]["seed"]
        n = 0
        self.db.execute("BEGIN IMMEDIATE")
        try:
            for model in models:
                for s in scripts:
                    for rp in range(1, repeats + 1):
                        cur = self.db.execute(
                            "INSERT OR IGNORE INTO jobs (job_id, model, script_id, repeat, stage, stage_index, order_key, "
                            "script_json, assets_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (f"{model}|{s['script_id']}|r{rp}", model, s["script_id"], rp, stage, stage_index,
                             order_key(seed, s["script_id"], rp), json.dumps(s, ensure_ascii=False), s["assets_hash"],
                             dbm.now()))
                        n += cur.rowcount
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        dbm.update_blocks(self.db)
        return n

    def write_manifest(self, invocation: dict) -> None:
        path = self.run_dir / "manifest.json"
        man = read_json(path) if path.exists() else {
            "run": self.run_dir.name, "created_at": dbm.get_meta(self.db, "created_at"),
            "config_hash": self.chash, "mock": self.mock, "allow_unapproved": self.allow_unapproved,
            "invocations": []}
        rows = self.db.execute("SELECT script_id, assets_hash FROM jobs GROUP BY script_id ORDER BY script_id").fetchall()
        man["assets_hash"] = sha([[r[0], r[1]] for r in rows])
        man["n_jobs"] = self.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        man["invocations"].append(invocation)
        write_json(path, man)

    # ------------------------------------------------------------ execution

    async def execute(self, models: list[str]) -> int:
        cfg, rc = self.cfg, self.cfg["runner"]
        self.halted = None
        self.spend = {m: 0.0 for m in models}
        self.spend.update({m: v for m, v in dbm.spend_by_model(self.db).items() if m in models})
        self.consec_fail = {m: 0 for m in models}
        self.in_flight = {m: 0 for m in models}
        self.replies_done = {m: 0 for m in models}
        self.jobs_done = {m: 0 for m in models}
        self.incomplete = {m: 0 for m in models}
        self.errors = {m: 0 for m in models}

        pending: dict[str, list[sqlite3.Row]] = {}
        for m in models:
            pending[m] = self.db.execute(
                "SELECT job_id, model, stage, stage_index, repeat, script_json FROM jobs WHERE model=? "
                "AND status='pending' ORDER BY stage_index, repeat, order_key", (m,)).fetchall()
        self.total = {m: len(pending[m]) for m in models}
        # Outstanding jobs per (model, block) in this invocation, for gating repeat blocks across models.
        self.outstanding: dict[tuple, int] = {}
        for m in models:
            for j in pending[m]:
                key = (m, (j["stage_index"], j["repeat"]))
                self.outstanding[key] = self.outstanding.get(key, 0) + 1
        self.cond = asyncio.Condition()
        sync = rc.get("sync_blocks_across_models", True)

        async def gate(block):
            if not sync:
                return
            async with self.cond:
                await self.cond.wait_for(lambda: self.halted is not None or all(
                    n == 0 for (mm, b), n in self.outstanding.items() if b < block))

        async def finish(model, block):
            async with self.cond:
                self.outstanding[(model, block)] -= 1
                self.cond.notify_all()

        async def drop_model(model):
            async with self.cond:
                for key in list(self.outstanding):
                    if key[0] == model:
                        self.outstanding[key] = 0
                self.cond.notify_all()

        async def dispatcher(model):
            mcfg = cfg["models"][model]
            sem = asyncio.Semaphore(mcfg.get("concurrency", 8))
            tasks = []
            started = 0
            for j in pending[model]:
                block = (j["stage_index"], j["repeat"])
                await gate(block)
                if self.halted:
                    break
                cap = mcfg.get("spend_cap_usd")
                if cap is not None and self.spend[model] >= cap:
                    self.spend_capped.add(model)
                    self.log(f"[{model}] spend cap ${cap:.2f} reached (${self.spend[model]:.4f}); "
                             f"no new conversations start; {self.in_flight[model]} in flight will finish")
                    break
                await sem.acquire()
                if self.halted:
                    sem.release()
                    break
                started += 1

                async def one(job=j, blk=block):
                    try:
                        await self.run_job(model, job)
                    finally:
                        sem.release()
                        await finish(model, blk)

                tasks.append(asyncio.create_task(one()))
            # Jobs never started (spend cap, halt) will not finish in this invocation: release the gate.
            await asyncio.gather(*tasks)
            await drop_model(model)

        status_task = asyncio.create_task(self._status_loop(models))
        try:
            await asyncio.gather(*(dispatcher(m) for m in models))
        finally:
            status_task.cancel()
            dbm.update_blocks(self.db)
            self._print_status(models, final=True)
        if self.halted:
            self.log(f"RUN HALTED: {self.halted}")
            return EXIT_HALTED
        left = self.db.execute(f"SELECT COUNT(*) FROM jobs WHERE status='pending' AND model IN "
                               f"({','.join('?' * len(models))})", models).fetchone()[0]
        if self.spend_capped and left:
            return EXIT_SPEND_CAP
        return EXIT_INCOMPLETE if left else EXIT_OK

    async def run_job(self, model: str, job) -> None:
        script = json.loads(job["script_json"])
        job_id = job["job_id"]
        replies = dbm.replies_for(self.db, job_id)
        if [r["reply_no"] for r in replies] != list(range(1, len(replies) + 1)):
            raise RuntimeError(f"job {job_id} has non-contiguous replies")  # cannot happen with the unique key
        texts = [r["reply_text"] for r in replies]
        if texts and not texts[-1].strip():
            dbm.mark_job(self.db, job_id, "ended", f"empty_reply_at_{len(texts)}")
            return
        self.in_flight[model] += 1
        try:
            while len(texts) < N_REPLIES:
                if self.halted:
                    return
                k = len(texts) + 1
                req = build_request(script, texts, self.cfg["models"][model], self.cfg)
                got = await self.call_with_retries(model, job_id, k, req)
                if got is None:
                    self.incomplete[model] += 1
                    return
                resp, attempt = got
                row = {
                    "user_text": req["messages"][-1]["content"], "reply_text": resp.text,
                    "content_json": json.dumps(resp.content, ensure_ascii=False), "stop_reason": resp.stop_reason,
                    **{key: resp.usage.get(key) for key in ("input_tokens", "output_tokens",
                                                            "cache_creation_input_tokens", "cache_read_input_tokens")},
                    "usage_json": json.dumps(resp.usage, ensure_ascii=False), "latency_s": resp.latency_s,
                    "request_id": resp.request_id, "api_model": resp.api_model, "config_hash": self.chash,
                    "assets_hash": script["assets_hash"],
                }
                if not resp.text.strip():
                    attempt["outcome"] = "empty_reply"
                dbm.commit_reply(self.db, job_id, model, k, row, attempt)
                self.replies_done[model] += 1
                texts.append(resp.text)
                if not resp.text.strip():
                    # A reply with no text cannot go back as history: the conversation ends here.
                    dbm.mark_job(self.db, job_id, "ended", f"empty_reply_at_{k}")
                    self.jobs_done[model] += 1
                    return
            dbm.mark_job(self.db, job_id, "complete")
            self.jobs_done[model] += 1
            for blk in dbm.update_blocks(self.db):
                self.log(f"[{blk[0]}] repeat block finished: stage {blk[1]}, repeat {blk[2]}")
        finally:
            self.in_flight[model] -= 1

    async def call_with_retries(self, model, job_id, k, req):
        rc = self.cfg["runner"]
        prices = self.cfg["models"][model].get("prices_per_mtok", {})
        client = self.clients[model]
        for attempt_no in range(rc["max_retries"] + 1):
            if self.halted:
                return None
            started = dbm.now()
            t0 = time.perf_counter()
            base = {"job_id": job_id, "model": model, "reply_no": k, "started_at": started}
            try:
                resp = await client.create(req)
            except RetryableError as e:
                self.errors[model] += 1
                dbm.insert_attempt(self.db, {**base, "latency_s": time.perf_counter() - t0,
                                             "outcome": "retryable_error", "error_type": e.error_type,
                                             "error_message": str(e)[:500], "http_status": e.http_status})
                self.consec_fail[model] += 1
                if self.consec_fail[model] >= rc["circuit_breaker_failures"]:
                    self.halt(f"circuit breaker: {self.consec_fail[model]} consecutive failed calls on {model}; "
                              f"last error {e.error_type} {e.http_status}: {str(e)[:200]}")
                    return None
                if attempt_no == rc["max_retries"]:
                    return None
                delay = min(rc["backoff_max_s"], rc["backoff_base_s"] * 2 ** attempt_no) * (0.5 + random.random())
                if e.retry_after:
                    delay = max(delay, e.retry_after)
                await asyncio.sleep(delay)
                continue
            except FatalError as e:
                self.errors[model] += 1
                dbm.insert_attempt(self.db, {**base, "latency_s": time.perf_counter() - t0, "outcome": "fatal_error",
                                             "error_type": e.error_type, "error_message": str(e)[:500],
                                             "http_status": e.http_status})
                self.halt(f"{e.error_type} ({e.http_status}) on {model}: {str(e)[:300]}. Every later call would fail "
                          f"the same way, so the whole run stopped.")
                return None
            self.consec_fail[model] = 0
            c = cost_usd(resp.usage, prices)
            self.spend[model] += c
            attempt = {**base, "latency_s": resp.latency_s or (time.perf_counter() - t0), "outcome": "ok",
                       "request_id": resp.request_id, "cost_usd": c,
                       **{key: resp.usage.get(key) or 0 for key in ("input_tokens", "output_tokens",
                                                                   "cache_creation_input_tokens",
                                                                   "cache_read_input_tokens")}}
            return resp, attempt
        return None

    def halt(self, reason: str) -> None:
        if not self.halted:
            self.halted = reason
            self.log(f"HALT: {reason}")

    async def _status_loop(self, models):
        while True:
            await asyncio.sleep(self.status_every_s)
            self._print_status(models)

    def _print_status(self, models, final=False):
        parts = []
        for m in models:
            parts.append(f"[{m}] conversations {self.jobs_done[m]}/{self.total[m]} | replies {self.replies_done[m]} | "
                         f"in flight {self.in_flight[m]} | left incomplete {self.incomplete[m]} | "
                         f"errors {self.errors[m]} | spend ${self.spend[m]:.4f}")
        self.log(("FINAL " if final else "") + " || ".join(parts))


# ================================================================ export and inspect

def export_transcripts(db, run_dir: Path) -> list[Path]:
    outdir = run_dir / "transcripts"
    paths = []
    for (model,) in db.execute("SELECT DISTINCT model FROM jobs ORDER BY model").fetchall():
        rows = []
        for j in db.execute("SELECT * FROM jobs WHERE model=? ORDER BY stage_index, repeat, script_id", (model,)):
            script = json.loads(j["script_json"])
            reps = dbm.replies_for(db, j["job_id"])
            rows.append({
                "job_id": j["job_id"], "script_id": j["script_id"], "repeat": j["repeat"], "stage": j["stage"],
                "factors": script["factors"], "status": j["status"], "end_reason": j["end_reason"],
                "system_prompt": script["system_prompt"],
                "turns": [{"reply_no": r["reply_no"], "user": r["user_text"], "assistant": r["reply_text"],
                           "stop_reason": r["stop_reason"], "output_tokens": r["output_tokens"],
                           "cache_read_input_tokens": r["cache_read_input_tokens"]} for r in reps],
            })
        p = outdir / f"{model}.jsonl"
        write_jsonl(p, rows)
        paths.append(p)
    return paths


def inspect_run(db) -> str:
    """Per-reply content block types, stop reason and usage, for checking thinking is off and caching works."""
    lines = []
    for j in db.execute("SELECT job_id, model, status FROM jobs ORDER BY model, job_id LIMIT 5"):
        lines.append(f"{j['job_id']} ({j['status']})")
        for r in dbm.replies_for(db, j["job_id"]):
            types = [b.get("type") for b in json.loads(r["content_json"])]
            lines.append(f"  reply {r['reply_no']:>2}: blocks={types} stop={r['stop_reason']} model={r['api_model']} "
                         f"in={r['input_tokens']} out={r['output_tokens']} cache_write={r['cache_creation_input_tokens']} "
                         f"cache_read={r['cache_read_input_tokens']} chars={len(r['reply_text'])}")
    thinking = sum(1 for (c,) in db.execute("SELECT content_json FROM replies")
                   if any(b.get("type") in ("thinking", "redacted_thinking") for b in json.loads(c)))
    non_text = sum(1 for (c,) in db.execute("SELECT content_json FROM replies")
                   if any(b.get("type") != "text" for b in json.loads(c)))
    no_cache_read = db.execute("SELECT COUNT(*) FROM replies WHERE reply_no >= 2 AND "
                               "COALESCE(cache_read_input_tokens,0) = 0").fetchone()[0]
    lines.append(f"replies with a thinking block: {thinking}; with any non-text block: {non_text}; "
                 f"replies 2-11 with no cache read: {no_cache_read}")
    return "\n".join(lines)


# ================================================================ CLI

def make_clients(models: list[str], cfg: dict, mock: bool, scripts: list[dict], mock_params: dict | None):
    if mock:
        params = MockParams(**(mock_params or {}))
        return {m: MockModel(scripts, MockParams(**{**params.__dict__, "seed": params.seed + i}), name=m)
                for i, m in enumerate(models)}
    load_dotenv_if_present()
    import os  # noqa: PLC0415
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RunRefused("ANTHROPIC_API_KEY is not set; copy .env.example to .env and add the key")
    client = AnthropicModel(cfg["runner"].get("timeout_s", 120))
    return {m: client for m in models}


def cmd_run(args) -> int:
    run_dir = Path(args.results) / args.run
    exists = (run_dir / "run.sqlite").exists()
    cfg = load_config(args.config) if (args.config or not exists) else read_json(run_dir / "config.json")
    if exists and args.config is None:
        # Resuming: the run's own frozen config, except for operational settings that may be changed.
        live = load_config()
        for m in cfg["models"]:
            if m in live["models"]:
                for key in ("concurrency", "spend_cap_usd"):
                    if key in live["models"][m]:
                        cfg["models"][m][key] = live["models"][m][key]
    scen = Path(args.scenarios)
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        with dbm.RunLock(run_dir / "run.lock"):
            r = Runner(run_dir, cfg, scen, {}, mock=args.mock, allow_unapproved=args.allow_unapproved,
                       status_every_s=args.status_every)
            r.open()
            r.check_assets_unchanged()
            models = args.models or [row[0] for row in r.db.execute("SELECT DISTINCT model FROM jobs")]
            unknown = [m for m in models if m not in cfg["models"]]
            if unknown:
                raise RunRefused(f"unknown model(s) {unknown}; config has {list(cfg['models'])}")
            for st in args.stage or []:
                n = r.add_stage(st, models, args.limit)
                r.log(f"stage {st}: {n} new job(s) created")
            if not models:
                raise RunRefused("no jobs in this run; give --stage and --models")
            scripts = [json.loads(x[0]) for x in r.db.execute("SELECT DISTINCT script_json FROM jobs")]
            r.clients = make_clients(models, cfg, args.mock, scripts, json.loads(args.mock_params) if args.mock_params else None)
            invocation = {"started_at": dbm.now(), "code_version": code_version(), "models": models,
                          "stages_added": args.stage or [], "mock": args.mock}
            r.log(f"run {args.run}: models {models}; {'MOCK' if args.mock else 'REAL API'}; "
                  f"config {r.chash}; code {invocation['code_version']}")
            code = EXIT_INCOMPLETE
            try:
                code = asyncio.run(r.execute(models))
            finally:
                invocation.update({"finished_at": dbm.now(), "exit_code": code, "halted": r.halted,
                                   "spend_usd": dbm.spend_by_model(r.db)})
                r.write_manifest(invocation)
                export_transcripts(r.db, run_dir)
            return code
    except RunRefused as e:
        print(f"REFUSED: {e}")
        return EXIT_REFUSED


def cmd_status(args) -> int:
    db = dbm.connect(Path(args.results) / args.run / "run.sqlite")
    for r in dbm.progress(db):
        print(f"[{r['model']}] stage {r['stage']} repeat {r['repeat']}: {r['complete']} complete, {r['ended']} ended, "
              f"{r['jobs']} jobs, {r['replies']} replies")
    for m, s in dbm.spend_by_model(db).items():
        print(f"[{m}] spend ${s:.4f}")
    for b in db.execute("SELECT * FROM blocks WHERE completed_at IS NOT NULL ORDER BY model, stage, repeat"):
        print(f"[{b['model']}] finished block: stage {b['stage']} repeat {b['repeat']} at {b['completed_at']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "status", "export", "inspect"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
        p.add_argument("--results", default=str(ROOT / "results"))
        if name == "run":
            p.add_argument("--stage", action="append", help="add this stage's jobs (repeatable)")
            p.add_argument("--models", nargs="+")
            p.add_argument("--config", default=None, help="default: config.json for a new run, the run's copy on resume")
            p.add_argument("--scenarios", default=str(ROOT / "scenarios"))
            p.add_argument("--mock", action="store_true", help="use the mock model (zero spend)")
            p.add_argument("--mock-params", default=None, help='JSON, e.g. {"p_uptake": 0.5}')
            p.add_argument("--allow-unapproved", action="store_true", help="development only")
            p.add_argument("--limit", type=int, default=None, help="only the first N scripts of each stage (smoke tests)")
            p.add_argument("--status-every", type=float, default=15.0)
    args = ap.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "status":
        return cmd_status(args)
    db = dbm.connect(Path(args.results) / args.run / "run.sqlite")
    if args.cmd == "export":
        for p in export_transcripts(db, Path(args.results) / args.run):
            print(f"wrote {p}")
        return 0
    print(inspect_run(db))
    return 0


if __name__ == "__main__":
    sys.exit(main())
