"""Diagnosis judge (build spec 6.6). Score time.

For each diagnosis text it records two separate things:
  identity      a canonical diagnosis name that keeps clinically meaningful distinctions (movement is measured on it)
  target match  start, post, ambiguous or neither (correctness is measured on it)

Normalised exact matches against the accepted names are tried first, with no model call. Everything else
goes to a judge model, which is shown the canonical names already recorded for the vignette and either
picks one or adds a new one. With no judge model, unmatched texts are recorded as 'unjudged'
(identity and match missing). Results are cached by vignette, normalised text, accepted-names version,
judge prompt version and judge model.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import Callable, Protocol

MATCHES = ["start", "post", "ambiguous", "neither"]


def norm_dx(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"[*_`]+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.strip(" .;:,。、")


class JudgeModel(Protocol):
    name: str

    def __call__(self, text: str, gold: dict, known: list[str]) -> tuple[str, str, dict]:
        """Return (identity, match, usage)."""


JUDGE_PROMPT = """You map one free-text diagnosis, taken from a model's answer about a clinical vignette, to two things.

1. identity: a canonical diagnosis name in English. If the text names the same clinical diagnosis as one of the
   names already used for this vignette, return that name exactly. Otherwise return a new short English name.
   Keep clinically meaningful distinctions: for example chronic heart failure and acute decompensated heart failure
   are different identities, and so are pneumonia and pulmonary embolism. Spelling, word order, language and
   abbreviations do not make a different identity.
2. match: which answer set the text belongs to.
   - "start": the same clinical entity as the starting diagnosis
   - "post": the same clinical entity as the post-update diagnosis
   - "ambiguous": it fits both sets (for example a broader term that covers both)
   - "neither": any other diagnosis
{single_target_note}
Starting diagnosis: {start_dx}
Also accepted for the starting diagnosis: {start_accept}
Post-update diagnosis: {post_dx}
Also accepted for the post-update diagnosis: {post_accept}
Names already used for this vignette: {known}

Text (it may be in English, Chinese or Japanese): {text}

Reply with JSON only, on one line: {{"identity": "...", "match": "start|post|ambiguous|neither"}}"""


class AnthropicJudge:
    """Judge model on the Claude API. Thinking off; JSON reply parsed by pattern."""

    def __init__(self, jcfg: dict):
        import anthropic  # noqa: PLC0415
        self.cfg = jcfg
        self.name = jcfg["api_model"]
        self.client = anthropic.Anthropic(max_retries=4, timeout=60)

    def __call__(self, text: str, gold: dict, known: list[str]):
        single = gold["changed"] == "urgency"
        prompt = JUDGE_PROMPT.format(
            single_target_note=("Here the starting and post-update diagnoses are the same, so match is start or "
                                "neither (or ambiguous if unclear).\n") if single else "",
            start_dx=gold["start_dx"], start_accept=", ".join(gold["start_accept"]) or "(none)",
            post_dx=gold["post_dx"], post_accept=", ".join(gold["post_accept"]) or "(none)",
            known=", ".join(known) or "(none yet)", text=json.dumps(text, ensure_ascii=False),
        )
        resp = self.client.messages.create(
            model=self.cfg["api_model"], max_tokens=self.cfg.get("max_tokens", 300),
            messages=[{"role": "user", "content": prompt}], **self.cfg.get("request_options", {}),
        )
        out = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", out, re.DOTALL)
        data = json.loads(m.group(0)) if m else {}
        identity, match = str(data.get("identity", "")).strip(), data.get("match")
        u = resp.usage
        usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                 "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0}
        if not identity or match not in MATCHES:
            raise ValueError("judge reply not parseable")
        return identity, match, usage


class FunctionJudge:
    """Wrap a plain function (text, gold, known) -> (identity, match) as a judge model; for tests."""

    def __init__(self, fn: Callable, name: str = "stub"):
        self.fn, self.name = fn, name

    def __call__(self, text, gold, known):
        identity, match = self.fn(text, gold, known)
        return identity, match, {}


class DiagnosisJudge:
    def __init__(self, cache_path: Path | str | None, prompt_version: str, model: JudgeModel | None = None,
                 prices: dict | None = None, spend_cap_usd: float | None = None):
        self.db = sqlite3.connect(str(cache_path) if cache_path else ":memory:")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS judgements (
                vignette TEXT, norm_text TEXT, names_version TEXT, prompt_version TEXT, judge_model TEXT,
                text TEXT, identity TEXT, match TEXT, method TEXT, created_at TEXT,
                PRIMARY KEY (vignette, norm_text, names_version, prompt_version, judge_model));
            CREATE TABLE IF NOT EXISTS identities (vignette TEXT, names_version TEXT, name TEXT,
                PRIMARY KEY (vignette, names_version, name));
            CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, created_at TEXT, judge_model TEXT,
                input_tokens INTEGER, output_tokens INTEGER, cache_read_input_tokens INTEGER,
                cache_creation_input_tokens INTEGER, cost_usd REAL, outcome TEXT);
        """)
        self.prompt_version = prompt_version
        self.model = model
        self.model_name = model.name if model else "none"
        self.prices = prices or {}
        self.spend_cap = spend_cap_usd
        self.n_model_calls = 0

    def spend(self) -> float:
        return self.db.execute("SELECT COALESCE(SUM(cost_usd),0) FROM calls").fetchone()[0]

    def known(self, vid: str, names_version: str) -> list[str]:
        return [r[0] for r in self.db.execute(
            "SELECT name FROM identities WHERE vignette=? AND names_version=? ORDER BY name", (vid, names_version))]

    def _add_identity(self, vid, nv, name):
        self.db.execute("INSERT OR IGNORE INTO identities VALUES (?,?,?)", (vid, nv, name))

    def judge(self, vid: str, gold: dict, text: str | None) -> dict:
        if text is None or not text.strip():
            return {"identity": None, "match": None, "method": "none"}
        nv = gold["accepted_names_version"]
        nt = norm_dx(text)
        start_set = {norm_dx(x) for x in [gold["start_dx"], *gold["start_accept"]]}
        post_set = {norm_dx(x) for x in [gold["post_dx"], *gold["post_accept"]]}
        single = gold["changed"] == "urgency"
        self._add_identity(vid, nv, gold["start_dx"])
        if not single:
            self._add_identity(vid, nv, gold["post_dx"])
        # Exact match first, no model and no cache needed.
        in_s, in_p = nt in start_set, (nt in post_set and not single)
        if in_s and in_p:
            return {"identity": nt, "match": "ambiguous", "method": "exact"}
        if in_s:
            return {"identity": gold["start_dx"], "match": "start", "method": "exact"}
        if in_p:
            return {"identity": gold["post_dx"], "match": "post", "method": "exact"}
        key = (vid, nt, nv, self.prompt_version, self.model_name)
        row = self.db.execute(
            "SELECT identity, match, method FROM judgements WHERE vignette=? AND norm_text=? AND names_version=? "
            "AND prompt_version=? AND judge_model=?", key).fetchone()
        if row:
            return {"identity": row[0], "match": row[1], "method": row[2]}
        if self.model is None:
            return {"identity": None, "match": None, "method": "unjudged"}
        if self.spend_cap is not None and self.spend() >= self.spend_cap:
            return {"identity": None, "match": None, "method": "unjudged_spend_cap"}
        try:
            identity, match, usage = self.model(text, gold, self.known(vid, nv))
            outcome = "ok"
        except Exception as e:  # noqa: BLE001
            identity, match, usage, outcome = None, None, {}, f"error: {type(e).__name__}"
        self.n_model_calls += 1
        cost = self._cost(usage)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.db.execute("INSERT INTO calls (created_at, judge_model, input_tokens, output_tokens, "
                        "cache_read_input_tokens, cache_creation_input_tokens, cost_usd, outcome) VALUES (?,?,?,?,?,?,?,?)",
                        (now, self.model_name, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                         usage.get("cache_read_input_tokens", 0), usage.get("cache_creation_input_tokens", 0),
                         cost, outcome))
        if identity is None:
            self.db.commit()
            return {"identity": None, "match": None, "method": "judge_error"}
        if single and match == "post":
            match = "start"
        self._add_identity(vid, nv, identity)
        self.db.execute("INSERT OR REPLACE INTO judgements VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (*key, text, identity, match, "model", now))
        self.db.commit()
        return {"identity": identity, "match": match, "method": "model"}

    def _cost(self, usage: dict) -> float:
        p = self.prices
        if not p or not usage:
            return 0.0
        return (usage.get("input_tokens", 0) * p["input"] + usage.get("output_tokens", 0) * p["output"]
                + usage.get("cache_read_input_tokens", 0) * p["cache_read"]
                + usage.get("cache_creation_input_tokens", 0) * p["cache_write"]) / 1e6

    def close(self):
        self.db.commit()
        self.db.close()
