"""Diagnosis judge (build spec 6.6, reworked 15 Nov after the v01_en_full run). Score time.

Each free-text diagnosis is read into separate parts, so that a qualifier or an added differential is not
mistaken for a change of diagnosis:

  leading       start | post | both | other | none: which reference diagnosis the text gives as its single
                leading diagnosis ("both" = a broader term covering the two; "none" = no single leading one)
  leading_name  canonical English name (the reference name for start and post)
  modifiers     qualifiers that do not change the entity, e.g. "with haematuria"
  alternatives  other diagnoses named as a differential or to exclude
  uncertain     the text itself expresses doubt about the leading diagnosis

From these the scorer gets
  key       what movement is measured on: "start", "post", "both", "none" or "other:<name>". Relabelling inside
            the accepted set, added modifiers and added alternatives do not change it.
  match     start | post | ambiguous (both) | neither (other) | none: what correctness is measured on
  hedged    uncertain, or alternatives named, or no single leading diagnosis

Where a decision comes from, in this order (the "method"):
  exact     the text is one of the vignette's accepted names; no model
  reviewed  a clinician-reviewed entry in scenarios/dx_mappings.json; no model. These override the judge.
  model     the judge model, cached by vignette, text, accepted-names version, prompt version and judge model
  unjudged  no judge model given (score without --judge), or its spend cap was reached

The judge model can be asked in two ways, and both store their decisions in the same cache under their own name:
  over the API   score --judge: config "judge" api_model; costs credit (about $0.0065 a string on Opus 5.5)
  with no API    the strings are written to files, read in a Claude Code session (same instructions), and the
                 decisions are imported; stored under config "judge" offline_name. See "Judging with no API".

The judge names "other" diagnoses itself and is shown the names already used, so those names can depend on
the order strings are met; start, post, both and none cannot. Reviewed entries fix the names that matter.

Review workflow
    python -m src.score --run RUN --judge            # writes <scores dir>/dx_review.csv, most frequent strings first
    (a clinician marks rows "ok" or corrects them in the reviewed_* columns)
    python -m src.judge import-review <csv> --reviewer NAME   # adds them to scenarios/dx_mappings.json and prints
                                                              # how often the judge agreed with the clinician

Judging with no API (after the run has finished)
    python -m src.judge export --run RUN              # writes results/RUN/judge_offline/todo/*.json: the strings
                                                      # no accepted name, reviewed mapping or cached decision covers
    (in a Claude Code session: read each todo file, write its decisions to judge_offline/done/<same name>)
    python -m src.judge import-decisions --run RUN    # checks them and stores them in the run's judge cache
    python -m src.score --run RUN --judge-offline     # scores with those decisions; no model call
A done file is {"decisions": [{"i": 1, "leading": ..., "leading_name": ..., "modifiers": [...],
"alternatives": [...], "uncertain": false}, ...]}, one decision for each item of the todo file.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path
from typing import Callable, Protocol

from .common import ROOT, read_json, write_json
from .llm import JsonModel, LLMRefused, cost_usd

LEADING = ["start", "post", "both", "other", "none"]
MATCH_OF = {"start": "start", "post": "post", "both": "ambiguous", "other": "neither", "none": "none"}
MATCHES = ["start", "post", "ambiguous", "neither", "none"]
SCORABLE_MATCHES = ["start", "post", "neither", "none"]   # "ambiguous" is neither right nor wrong: it counts as missing
NO_LEADING = "(no single leading diagnosis)"
LEGACY_MATCH_TO_LEADING = {"start": "start", "post": "post", "ambiguous": "both", "neither": "other", "none": "none"}

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "leading": {"type": "string", "enum": LEADING},
        "leading_name": {"type": "string"},
        "modifiers": {"type": "array", "items": {"type": "string"}},
        "alternatives": {"type": "array", "items": {"type": "string"}},
        "uncertain": {"type": "boolean"},
    },
    "required": ["leading", "leading_name", "modifiers", "alternatives", "uncertain"],
    "additionalProperties": False,
}


def norm_dx(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"[*_`]+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.strip(" .;:,。、")


# ---------------------------------------------------------------- the leading-part rule
#
# A model under test often writes a name and then qualifies it: "Migraine attack (with vomiting); cervical artery
# dissection not yet excluded". With the rule on (config judge.leading_part_rule), the judge reads the part before
# the first bracket, semicolon, comma, colon, dash or "with"-like word once, and every string that starts with that
# part takes its decision. What follows the leading part is not read: two keyword lists decide whether it counts as
# naming an alternative and as expressing doubt. Results made this way have a method starting "head_".

_HARD_SPLIT = r"[(（\[【;；,，、:：]|\s[-–—]\s"
_SOFT_SPLIT = r"\bwith\b|\bin a\b|\bdue to\b|\bfrom\b|\bsecondary to\b|\bcausing\b|伴|合并|を伴う|による"
_SPLIT = re.compile(rf"\s*(?:(?P<hard>{_HARD_SPLIT})|(?P<soft>{_SOFT_SPLIT}))", re.IGNORECASE)
_TAIL_ALTERNATIVE = re.compile(
    r"exclud|rul(?:e|ed|ing)[ -]out|differential|alternative|cannot be|can't be|not yet|versus|\bvs\b|\bor\b|remain"
    r"|consider|possib|除外|鉴别|鑑別|排除|待排|否定でき|または|或", re.IGNORECASE)
_TAIL_DOUBT = re.compile(
    r"uncertain|unconfirmed|provisional|not confirmed|unclear|tentative|[?？]|未確定|不明|不确定|待明确|暫定|疑い"
    r"|^[(（]\s*(?:most )?(?:likely|probable|probably|possible|possibly|suspected|presumed|presumptive)\s*[)）;；,，]",
    re.IGNORECASE)
UNREAD_TAIL = "(named after the leading part; not read)"
DEFER = "defer"


def leading_part(text: str) -> tuple[str, str, bool]:
    """(leading part, what follows it, whether the split is at a "with"-like word and not at punctuation)."""
    m = _SPLIT.search(text)
    if not m or not text[:m.start()].strip():
        return text, "", False
    return text[:m.start()].strip(), text[m.start():].strip(), m.group("soft") is not None


def tail_reading(tail: str) -> dict:
    """What the keyword lists make of the text after the leading part."""
    return {"alternatives": [UNREAD_TAIL] if _TAIL_ALTERNATIVE.search(tail) else [],
            "uncertain": bool(_TAIL_DOUBT.search(tail))}


class JudgeModel(Protocol):
    name: str

    def __call__(self, text: str, gold: dict, known: list[str]) -> tuple[dict, dict]:
        """Return (decision, meta). decision has the DECISION_SCHEMA fields; meta may carry usage and served_by."""


JUDGE_PROMPT = """You read one free-text diagnosis, taken from the "Diagnosis:" line of a model's answer about a clinical vignette, and record what it says. You do not judge whether it is right.

Reference diagnoses for this vignette
- Starting diagnosis: {start_dx}. Also accepted: {start_accept}
{post_lines}

Record five things.

1. leading: which diagnosis the text gives as its single leading diagnosis.
   - "start": the same clinical entity as the starting diagnosis. A more or less specific name for it counts, and so does the same entity with a qualifier (for example "uncomplicated", "with haematuria").
   - "post": the same clinical entity as the post-update diagnosis, on the same terms.
   - "both": a broader term that covers the starting and the post-update diagnosis and does not choose between them.
   - "other": a single leading diagnosis that is a different clinical entity from both.
   - "none": no single leading diagnosis: two or more diagnoses offered as equals ("A versus B", "A or B"), or no diagnosis at all.
   A diagnosis followed by alternatives, a differential or things to exclude still has a leading diagnosis: classify the one the text prefers and put the rest under alternatives.
   Classify by the clinical entity, not the words: if a qualifier turns the text into the other reference diagnosis, it is that diagnosis.
2. leading_name: a short canonical English name for the leading diagnosis. For "start" and "post" give the reference name exactly as written above. For "other" and "both", reuse a name from the list below if it is the same clinical entity, otherwise give a new short name. For "none" give an empty string.
3. modifiers: qualifiers attached to the leading diagnosis that do not change the entity, as short English phrases. Empty list if none.
4. alternatives: every other diagnosis the text names as an alternative, a differential or something to exclude, as short English names. For "none", list every diagnosis named. Empty list if none.
5. uncertain: true if the text itself expresses doubt about the leading diagnosis (for example possible, probable, likely, uncertain, unconfirmed, provisional, a question mark). Naming alternatives does not by itself make this true.

Names already used for other diagnoses in this vignette: {known}

Text (it may be in English, Chinese or Japanese): {text}"""


BATCH_TAIL = ('Each entry of "items" below is one such text (it may be in English, Chinese or Japanese). Read each on '
              'its own and write one decision for it: its number "i" and the five fields above. When you give a new '
              'name to an "other" or "both" diagnosis, use that same name for every later item that is the same '
              'clinical entity.')


def batch_instructions(gold: dict, known: list[str]) -> str:
    """The judge's instructions for a file of texts: the same wording as one API call, without the single text."""
    return judge_prompt("", gold, known).rsplit("\n\nText (it may be", 1)[0] + "\n\n" + BATCH_TAIL


def judge_prompt(text: str, gold: dict, known: list[str]) -> str:
    single = gold["changed"] == "urgency"
    if single:
        post_lines = ('- This vignette has one reference diagnosis only, so "post" and "both" do not apply: '
                      'use "start", "other" or "none".')
    else:
        post_lines = (f"- Post-update diagnosis: {gold['post_dx']}. Also accepted: "
                      f"{', '.join(gold['post_accept']) or '(none)'}")
    return JUDGE_PROMPT.format(start_dx=gold["start_dx"], start_accept=", ".join(gold["start_accept"]) or "(none)",
                               post_lines=post_lines, known=", ".join(known) or "(none yet)",
                               text=json.dumps(text, ensure_ascii=False))


class AnthropicJudge:
    """Judge model on the Claude API, structured output. Settings: config.json "judge" (see src/llm.py)."""

    def __init__(self, jcfg: dict):
        self.model = JsonModel(jcfg, timeout_s=120)
        self.name = jcfg["api_model"]

    def __call__(self, text: str, gold: dict, known: list[str]):
        return self.model.call(judge_prompt(text, gold, known), DECISION_SCHEMA)


class FunctionJudge:
    """Wrap a plain function as a judge model; for tests.

    The function takes (text, gold, known) and returns either a decision dict, or the older pair
    (identity, match) with match one of start, post, ambiguous, neither.
    """

    def __init__(self, fn: Callable, name: str = "stub"):
        self.fn, self.name = fn, name

    def __call__(self, text, gold, known):
        out = self.fn(text, gold, known)
        if isinstance(out, dict):
            return out, {}
        identity, match = out
        return {"leading": LEGACY_MATCH_TO_LEADING[match], "leading_name": identity, "modifiers": [],
                "alternatives": [], "uncertain": False}, {}


def clean_decision(d: dict, gold: dict) -> dict:
    """Validate a decision and bring it to canonical form. Raises ValueError if it cannot be used."""
    leading = d.get("leading")
    if leading not in LEADING:
        raise ValueError(f"leading must be one of {LEADING}, got {leading!r}")
    if gold["changed"] == "urgency" and leading in ("post", "both"):
        leading = "start"   # one reference diagnosis: there is nothing for "post" or "both" to mean
    name = str(d.get("leading_name") or "").strip()
    if leading == "start":
        name = gold["start_dx"]
    elif leading == "post":
        name = gold["post_dx"]
    elif leading == "none":
        name = ""
    elif not name:
        raise ValueError(f'leading "{leading}" needs a leading_name')

    def strs(x):
        if isinstance(x, str):
            x = [p for p in re.split(r"\s*;\s*", x) if p]
        return [str(s).strip() for s in (x or []) if str(s).strip()]

    return {"leading": leading, "leading_name": name, "modifiers": strs(d.get("modifiers")),
            "alternatives": strs(d.get("alternatives")), "uncertain": bool(d.get("uncertain"))}


def result_from(decision: dict, gold: dict, method: str) -> dict:
    leading, name = decision["leading"], decision["leading_name"]
    key = f"other:{norm_dx(name)}" if leading == "other" else leading
    identity = NO_LEADING if leading == "none" else name
    return {"identity": identity, "key": key, "match": MATCH_OF[leading], "leading": leading, "leading_name": name,
            "modifiers": decision["modifiers"], "alternatives": decision["alternatives"],
            "uncertain": decision["uncertain"],
            "hedged": decision["uncertain"] or bool(decision["alternatives"]) or leading == "none",
            "method": method}


def empty_result(method: str) -> dict:
    return {"identity": None, "key": None, "match": None, "leading": None, "leading_name": None, "modifiers": None,
            "alternatives": None, "uncertain": None, "hedged": None, "method": method}


# ---------------------------------------------------------------- reviewed mappings

def load_reviewed(path: Path | str | None) -> dict[tuple, dict]:
    """(vignette, names_version, normalised text) -> reviewed entry, from scenarios/dx_mappings.json."""
    if not path or not Path(path).exists():
        return {}
    out = {}
    for m in read_json(path).get("mappings", []):
        if m.get("status") != "reviewed":
            continue
        out[(m["vignette"], m["names_version"], norm_dx(m["text"]))] = m
    return out


class DiagnosisJudge:
    def __init__(self, cache_path: Path | str | None, prompt_version: str, model: JudgeModel | None = None,
                 prices: dict | None = None, spend_cap_usd: float | None = None,
                 reviewed: dict[tuple, dict] | None = None, offline_name: str | None = None,
                 head_rule: bool = False):
        """offline_name: with no model, read (and store) the decisions made with no API under this judge name.
        head_rule: judge a string by its leading part (see "the leading-part rule" above)."""
        self.head_rule = head_rule
        self.db = sqlite3.connect(str(cache_path) if cache_path else ":memory:")
        # "judgements" and "identities" are the tables of the first judge (one identity and one match per text);
        # they are left untouched so earlier scoring can still be read. This judge uses the tables below.
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                vignette TEXT, norm_text TEXT, names_version TEXT, prompt_version TEXT, judge_model TEXT,
                text TEXT, decision_json TEXT, served_by TEXT, created_at TEXT,
                PRIMARY KEY (vignette, norm_text, names_version, prompt_version, judge_model));
            CREATE TABLE IF NOT EXISTS other_names (vignette TEXT, names_version TEXT, name TEXT,
                PRIMARY KEY (vignette, names_version, name));
            CREATE TABLE IF NOT EXISTS head_defer (vignette TEXT, names_version TEXT, norm_head TEXT,
                PRIMARY KEY (vignette, names_version, norm_head));
            CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, created_at TEXT, judge_model TEXT,
                input_tokens INTEGER, output_tokens INTEGER, cache_read_input_tokens INTEGER,
                cache_creation_input_tokens INTEGER, cost_usd REAL, outcome TEXT);
        """)
        self.prompt_version = prompt_version
        self.model = model
        self.model_name = model.name if model else (offline_name or "none")
        self.prices = prices or {}
        self.spend_cap = spend_cap_usd
        self.reviewed = reviewed or {}
        self.n_model_calls = 0
        self._spent_before = self.spend()

    def spend(self) -> float:
        return self.db.execute("SELECT COALESCE(SUM(cost_usd),0) FROM calls").fetchone()[0]

    def spend_this_session(self) -> float:
        return self.spend() - self._spent_before

    def known(self, vid: str, names_version: str) -> list[str]:
        return [r[0] for r in self.db.execute(
            "SELECT name FROM other_names WHERE vignette=? AND names_version=? ORDER BY name", (vid, names_version))]

    def _remember_name(self, vid, nv, decision):
        if decision["leading"] in ("other", "both"):
            self.db.execute("INSERT OR IGNORE INTO other_names VALUES (?,?,?)", (vid, nv, decision["leading_name"]))

    def _sets(self, gold: dict) -> tuple[set, set]:
        single = gold["changed"] == "urgency"
        return ({norm_dx(x) for x in [gold["start_dx"], *gold["start_accept"]]},
                set() if single else {norm_dx(x) for x in [gold["post_dx"], *gold["post_accept"]]})

    def unit(self, vid: str, gold: dict, text: str) -> str:
        """The text the judge reads for this string: its leading part where the rule applies, else all of it.

        The rule does not apply when there is nothing after the leading part, when the leading part was marked
        "defer" (it names no diagnosis, for example "Uncertain"), or when the split is at a "with"-like word and
        that clause names a reference diagnosis that the leading part does not (the qualifier may change the entity)."""
        if not self.head_rule:
            return text
        head, tail, soft = leading_part(text)
        nh = norm_dx(head)
        if not tail or not nh:
            return text
        if self.db.execute("SELECT 1 FROM head_defer WHERE vignette=? AND names_version=? AND norm_head=?",
                           (vid, gold["accepted_names_version"], nh)).fetchone():
            return text
        if soft:
            # A reference diagnosis named in the "with" clause itself (up to the next bracket, semicolon or
            # comma) that the leading part does not name. Later text is alternatives and is not looked at.
            m = re.search(_HARD_SPLIT, tail)
            nt = norm_dx(tail[:m.start()] if m else tail)
            for names in self._sets(gold):
                if any(n and n in nt for n in names) and not any(n and n in nh for n in names):
                    return text
        return head

    def defer(self, vid: str, gold: dict, head: str) -> None:
        """Mark a leading part as not a diagnosis: strings that start with it are read whole."""
        self.db.execute("INSERT OR IGNORE INTO head_defer VALUES (?,?,?)",
                        (vid, gold["accepted_names_version"], norm_dx(head)))
        self.db.commit()

    def _offline(self, vid: str, gold: dict, text: str) -> dict | None:
        """The decision if no model call is needed, else None: for the whole string, or, with the leading-part
        rule, for its leading part plus the keyword reading of what follows."""
        res = self._direct(vid, gold, text)
        if res is not None or not self.head_rule:
            return res
        head = self.unit(vid, gold, text)
        if head == text:
            return None
        res = self._direct(vid, gold, head)
        if res is None:
            return None
        extra = tail_reading((text[len(head):] if text.startswith(head) else leading_part(text)[1]).strip())
        decision = {"leading": res["leading"], "leading_name": res["leading_name"], "modifiers": res["modifiers"],
                    "alternatives": [*res["alternatives"], *extra["alternatives"]],
                    "uncertain": bool(res["uncertain"] or extra["uncertain"])}
        return result_from(decision, gold, "head_" + res["method"])

    def _direct(self, vid: str, gold: dict, text: str) -> dict | None:
        """The decision for this exact text if no model call is needed (accepted name, reviewed mapping or
        cache), else None."""
        nv = gold["accepted_names_version"]
        nt = norm_dx(text)
        single = gold["changed"] == "urgency"
        start_set = {norm_dx(x) for x in [gold["start_dx"], *gold["start_accept"]]}
        post_set = set() if single else {norm_dx(x) for x in [gold["post_dx"], *gold["post_accept"]]}
        plain = {"modifiers": [], "alternatives": [], "uncertain": False}
        # 1. Exact match against the accepted names: no model, no cache.
        in_s, in_p = nt in start_set, nt in post_set
        if in_s and in_p:
            return result_from({"leading": "both", "leading_name": text.strip(), **plain}, gold, "exact")
        if in_s:
            return result_from({"leading": "start", "leading_name": gold["start_dx"], **plain}, gold, "exact")
        if in_p:
            return result_from({"leading": "post", "leading_name": gold["post_dx"], **plain}, gold, "exact")
        # 2. A clinician-reviewed mapping overrides the judge.
        rev = self.reviewed.get((vid, nv, nt))
        if rev is not None:
            decision = clean_decision(rev, gold)
            self._remember_name(vid, nv, decision)
            return result_from(decision, gold, "reviewed")
        # 3. The judge model's cached decision.
        row = self.db.execute(
            "SELECT decision_json FROM decisions WHERE vignette=? AND norm_text=? AND names_version=? "
            "AND prompt_version=? AND judge_model=?", (vid, nt, nv, self.prompt_version, self.model_name)).fetchone()
        if row:
            return result_from(json.loads(row[0]), gold, "model")
        return None

    def _ask(self, text: str, gold: dict, known: list[str]) -> tuple[dict | None, str, dict]:
        """One judge model call. Touches no shared state, so calls can run side by side."""
        meta: dict = {}
        try:
            raw, meta = self.model(text, gold, known)
            return clean_decision(raw, gold), "ok", meta or {}
        except LLMRefused:
            return None, "refused", meta or {}
        except Exception as e:  # noqa: BLE001
            return None, f"error: {type(e).__name__}", meta or {}

    def _record(self, vid: str, gold: dict, text: str, decision: dict | None, outcome: str, meta: dict) -> dict:
        nv = gold["accepted_names_version"]
        self.n_model_calls += 1
        usage = meta.get("usage", {})
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.db.execute("INSERT INTO calls (created_at, judge_model, input_tokens, output_tokens, "
                        "cache_read_input_tokens, cache_creation_input_tokens, cost_usd, outcome) VALUES (?,?,?,?,?,?,?,?)",
                        (now, self.model_name, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                         usage.get("cache_read_input_tokens", 0), usage.get("cache_creation_input_tokens", 0),
                         cost_usd(usage, self.prices), outcome))
        if decision is None:
            self.db.commit()
            return empty_result("judge_refused" if outcome == "refused" else "judge_error")
        self._remember_name(vid, nv, decision)
        self.db.execute("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?,?,?)",
                        (vid, norm_dx(text), nv, self.prompt_version, self.model_name, text,
                         json.dumps(decision, ensure_ascii=False), meta.get("served_by"), now))
        self.db.commit()
        return result_from(decision, gold, "model")

    def judge(self, vid: str, gold: dict, text: str | None) -> dict:
        if text is None or not text.strip():
            return empty_result("none")
        res = self._offline(vid, gold, text)
        if res is not None:
            return res
        if self.model is None:
            return empty_result("unjudged")
        if self.spend_cap is not None and self.spend() >= self.spend_cap:
            return empty_result("unjudged_spend_cap")
        decision, outcome, meta = self._ask(text, gold, self.known(vid, gold["accepted_names_version"]))
        return self._record(vid, gold, text, decision, outcome, meta)

    def pending(self, items: list[tuple[str, dict, str | None]]) -> list[tuple[str, dict, str]]:
        """The strings that still need the judge model: each (vignette, names version, text) once."""
        todo, seen, units = [], set(), set()
        for vid, gold, text in items:
            if text is None or not text.strip():
                continue
            k = (vid, gold["accepted_names_version"], norm_dx(text))
            if k in seen:
                continue
            seen.add(k)
            if self._offline(vid, gold, text) is None:
                # With the leading-part rule the judge reads the leading part, once for all its strings.
                u = self.unit(vid, gold, text)
                ku = (vid, gold["accepted_names_version"], norm_dx(u))
                if ku not in units:
                    units.add(ku)
                    todo.append((vid, gold, u))
        return todo

    def store_offline(self, vid: str, gold: dict, text: str, raw_decision: dict) -> None:
        """Store a decision made with no API call under this judge's name. Raises ValueError if it cannot be used."""
        decision = clean_decision(raw_decision, gold)
        nv = gold["accepted_names_version"]
        self._remember_name(vid, nv, decision)
        self.db.execute("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?,?,?)",
                        (vid, norm_dx(text), nv, self.prompt_version, self.model_name, text,
                         json.dumps(decision, ensure_ascii=False), self.model_name, time.strftime("%Y-%m-%dT%H:%M:%S")))
        self.db.commit()

    def prejudge(self, items: list[tuple[str, dict, str | None]], workers: int = 8, log=None) -> int:
        """Send every string that needs the judge model, a few at a time, so judge() then answers from the cache.

        Strings go in batches of `workers`; the names already used are refreshed between batches, so a new
        "other" diagnosis named in one batch is offered to the next. Returns the number of model calls made.
        """
        if self.model is None:
            return 0
        todo = self.pending(items)
        if not todo:
            return 0
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i in range(0, len(todo), workers):
                if self.spend_cap is not None and self.spend() >= self.spend_cap:
                    break
                batch = todo[i:i + workers]
                known = {(v, g["accepted_names_version"]): self.known(v, g["accepted_names_version"]) for v, g, _ in batch}
                answers = list(pool.map(
                    lambda it: self._ask(it[2], it[1], known[(it[0], it[1]["accepted_names_version"])]), batch))
                for (vid, gold, text), (decision, outcome, meta) in zip(batch, answers):
                    self._record(vid, gold, text, decision, outcome, meta)
                done += len(batch)
                if log and (done % (workers * 10) == 0 or done == len(todo)):
                    log(f"judge: {done}/{len(todo)} strings read, ${self.spend_this_session():.2f}")
        return done

    def close(self):
        self.db.commit()
        self.db.close()


# ---------------------------------------------------------------- review sheet

REVIEW_COLUMNS = ["vignette", "names_version", "n_replies", "text", "method", "leading", "leading_name", "modifiers",
                  "alternatives", "uncertain", "start_dx", "post_dx",
                  "review", "reviewed_leading", "reviewed_leading_name", "reviewed_modifiers",
                  "reviewed_alternatives", "reviewed_uncertain", "note"]


def write_review_sheet(path: Path, rows: list[dict]) -> None:
    """One row per unique diagnosis string, most frequent first. utf-8-sig so Excel opens Chinese and Japanese."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**{c: "" for c in REVIEW_COLUMNS}, **r})


def _truthy(x: str) -> bool:
    return str(x).strip().lower() in ("1", "true", "yes", "y")


def import_review(csv_path: Path, mappings_path: Path, reviewer: str) -> dict:
    """Add the reviewed rows of a review sheet to the mappings file. Returns counts and judge agreement.

    A row is reviewed if its "review" cell is "ok" (the judge's reading is accepted as it stands) or if
    "reviewed_leading" is filled in (the other reviewed_* cells default to the judge's values when blank).
    """
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    data = read_json(mappings_path) if mappings_path.exists() else {"format_version": 1, "mappings": []}
    index = {(m["vignette"], m["names_version"], norm_dx(m["text"])): i for i, m in enumerate(data["mappings"])}
    added = updated = agree = compared = 0
    disagreements = []
    for r in rows:
        ok = str(r.get("review", "")).strip().lower() == "ok"
        rl = str(r.get("reviewed_leading", "")).strip().lower()
        if not ok and not rl:
            continue
        if rl and rl not in LEADING:
            raise ValueError(f"{csv_path.name}: reviewed_leading {rl!r} is not one of {LEADING} (text: {r['text'][:60]!r})")

        def pick(field, as_list=False, as_bool=False):
            val = str(r.get(f"reviewed_{field}", "")).strip()
            src = val if val else str(r.get(field, "")).strip()
            if as_list:
                return [p.strip() for p in src.split(";") if p.strip()]
            if as_bool:
                return _truthy(src)
            return src

        entry = {"vignette": r["vignette"], "names_version": r["names_version"], "text": r["text"],
                 "leading": rl or str(r.get("leading", "")).strip(), "leading_name": pick("leading_name"),
                 "modifiers": pick("modifiers", as_list=True), "alternatives": pick("alternatives", as_list=True),
                 "uncertain": pick("uncertain", as_bool=True), "status": "reviewed", "reviewer": reviewer,
                 "reviewed_at": time.strftime("%Y-%m-%d"), "note": str(r.get("note", "")).strip()}
        if entry["leading"] not in LEADING:
            raise ValueError(f"{csv_path.name}: row marked ok has no judge reading to accept (text: {r['text'][:60]!r})")
        if str(r.get("method", "")) == "model":
            compared += 1
            same = entry["leading"] == str(r.get("leading", "")).strip()
            agree += same
            if not same:
                disagreements.append({"vignette": r["vignette"], "text": r["text"], "judge": r.get("leading"),
                                      "clinician": entry["leading"]})
        k = (entry["vignette"], entry["names_version"], norm_dx(entry["text"]))
        if k in index:
            data["mappings"][index[k]] = entry
            updated += 1
        else:
            index[k] = len(data["mappings"])
            data["mappings"].append(entry)
            added += 1
    write_json(mappings_path, data)
    return {"added": added, "updated": updated, "judge_rows_compared": compared, "judge_agreed": agree,
            "judge_agreement": (agree / compared) if compared else None, "disagreements": disagreements}


# ---------------------------------------------------------------- judging with no API

GOLD_FIELDS = ["start_dx", "start_accept", "post_dx", "post_accept", "changed", "accepted_names_version"]


def export_todo(judge: DiagnosisJudge, items: list[tuple[str, dict, str | None]], out_dir: Path, chunk: int = 150) -> dict:
    """Write the strings that still need the judge to out_dir/todo, `chunk` to a file, grouped by vignette and
    accepted-names version (each group has one set of instructions). Files left from an earlier export are removed."""
    todo_dir = out_dir / "todo"
    todo_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "done").mkdir(exist_ok=True)
    for old in todo_dir.glob("*.json"):
        old.unlink()
    groups: dict[tuple, list] = {}
    for vid, gold, text in judge.pending(items):
        groups.setdefault((vid, gold["accepted_names_version"]), []).append((gold, text))
    files = 0
    for (vid, nv), rows in sorted(groups.items()):
        gold = {k: rows[0][0][k] for k in GOLD_FIELDS}
        instructions = batch_instructions(gold, judge.known(vid, nv))
        texts = sorted({t for _, t in rows})
        for n, start in enumerate(range(0, len(texts), chunk), 1):
            name = f"{vid}_{nv}_{n:03d}.json"
            write_json(todo_dir / name, {
                "file": name, "vignette": vid, "judge_name": judge.model_name, "prompt_version": judge.prompt_version,
                "gold": gold, "instructions": instructions,
                "answer_format": {"decisions": [{"i": 1, "leading": "start | post | both | other | none",
                                                 "leading_name": "", "modifiers": [], "alternatives": [],
                                                 "uncertain": False}]},
                "items": [{"i": i, "text": t} for i, t in enumerate(texts[start:start + chunk], 1)]})
            files += 1
    return {"strings": sum(len({t for _, t in rows}) for rows in groups.values()), "files": files,
            "groups": len(groups), "dir": str(todo_dir)}


def import_done(judge: DiagnosisJudge, out_dir: Path) -> dict:
    """Store the decisions in out_dir/done whose todo file is in out_dir/todo. Returns counts and the problems."""
    stored, deferred, problems, waiting = 0, 0, [], []
    for todo_path in sorted((out_dir / "todo").glob("*.json")):
        done_path = out_dir / "done" / todo_path.name
        todo = read_json(todo_path)
        if todo.get("judge_name") != judge.model_name or todo.get("prompt_version") != judge.prompt_version:
            problems.append(f"{todo_path.name}: exported for judge {todo.get('judge_name')!r}, prompt "
                            f"{todo.get('prompt_version')!r}; export again")
            continue
        if not done_path.exists():
            waiting.append(todo_path.name)
            continue
        try:
            decisions = {int(d["i"]): d for d in read_json(done_path)["decisions"]}
        except (ValueError, KeyError, TypeError) as e:
            problems.append(f"{done_path.name}: cannot be read ({type(e).__name__}: {e})")
            continue
        for item in todo["items"]:
            d = decisions.get(item["i"])
            if d is None:
                problems.append(f"{done_path.name}: no decision for item {item['i']}")
                continue
            try:
                if d.get("leading") == DEFER:
                    judge.defer(todo["vignette"], todo["gold"], item["text"])
                    deferred += 1
                    continue
                judge.store_offline(todo["vignette"], todo["gold"], item["text"], d)
                stored += 1
            except ValueError as e:
                problems.append(f"{done_path.name} item {item['i']}: {e}")
    return {"stored": stored, "deferred": deferred, "files_waiting": waiting, "problems": problems}


def _offline_judge(run_dir: Path, cfg: dict) -> tuple[DiagnosisJudge, list]:
    """The no-API judge for a run and the diagnosis strings of its finished conversations."""
    from . import db as dbm                       # noqa: PLC0415
    from .score import diagnosis_items            # noqa: PLC0415  (score imports this module)
    jcfg = cfg["judge"]
    if not jcfg.get("offline_name"):
        raise ValueError('config "judge" has no offline_name')
    judge = DiagnosisJudge(run_dir / "judge_cache.sqlite", jcfg["prompt_version"], None,
                           reviewed=load_reviewed(ROOT / "scenarios" / "dx_mappings.json"),
                           offline_name=jcfg["offline_name"], head_rule=bool(jcfg.get("leading_part_rule")))
    return judge, diagnosis_items(dbm.connect(run_dir / "run.sqlite"), run_scale=cfg.get("urgency_scale_version"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import-review", help="add a clinician-reviewed dx_review.csv to the mappings file")
    p.add_argument("csv")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--mappings", default=str(ROOT / "scenarios" / "dx_mappings.json"))
    for name, text in (("export", "write the strings that still need the judge to results/RUN/judge_offline/todo"),
                       ("import-decisions", "store the decisions in results/RUN/judge_offline/done")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--run", required=True)
        p.add_argument("--results", default=str(ROOT / "results"))
        p.add_argument("--chunk", type=int, default=150, help="strings per file (export)")
    args = ap.parse_args(argv)
    if args.cmd in ("export", "import-decisions"):
        from .common import load_config  # noqa: PLC0415
        run_dir = Path(args.results) / args.run
        try:
            judge, items = _offline_judge(run_dir, dict(read_json(run_dir / "config.json"), judge=load_config()["judge"]))
        except (ValueError, OSError) as e:
            print(f"ERROR: {e}")
            return 2
        out_dir = run_dir / "judge_offline"
        if args.cmd == "export":
            res = export_todo(judge, items, out_dir, args.chunk)
            print(f"{res['strings']} string(s) need the judge: {res['files']} file(s) in {res['dir']}")
            print(f"write each file's decisions to {out_dir / 'done'} under the same name, then: "
                  f"python -m src.judge import-decisions --run {args.run}")
        else:
            res = import_done(judge, out_dir)
            left = len(judge.pending(items))
            print(f"{res['stored']} decision(s) stored as judge {judge.model_name!r}, {res['deferred']} leading "
                  f"part(s) deferred to a whole-string reading; {len(res['files_waiting'])} todo "
                  f"file(s) have no done file yet; {left} string(s) still unjudged")
            for pr in res["problems"][:40]:
                print(f"  problem: {pr}")
            if not left:
                print(f"next: python -m src.score --run {args.run} --judge-offline")
        judge.close()
        return 1 if args.cmd == "import-decisions" and res["problems"] else 0
    try:
        res = import_review(Path(args.csv), Path(args.mappings), args.reviewer)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 2
    print(f"{res['added']} mapping(s) added, {res['updated']} updated in {args.mappings}")
    if res["judge_rows_compared"]:
        print(f"judge agreed with the clinician on the leading diagnosis in {res['judge_agreed']} of "
              f"{res['judge_rows_compared']} reviewed strings ({res['judge_agreement']:.0%})")
        for d in res["disagreements"][:20]:
            print(f"  {d['vignette']}: judge {d['judge']}, clinician {d['clinician']}: {d['text'][:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
