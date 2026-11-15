"""Human-readable markdown transcripts, one file per conversation, plus an index per model.

Written to results/<run>/transcripts/<model>/ alongside the JSONL export. Each file has the conversation's
factors, a summary table of what was extracted from every reply next to the expected answer, the system
prompt, and the conversation itself with each user turn labelled by kind. Thinking blocks are kept,
collapsed. The expected answers shown here were never sent to the model.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import db as dbm
from .common import N_REPLIES, write_text
from .extract import extract

RE_BLOCK = re.compile(r"\[\[\s*assessment\s*\]\].*?(\[\[\s*end\s*\]\]|\Z)", re.IGNORECASE | re.DOTALL)
TURN_LABEL = {"noise": "noise", "supportive": "supportive update", "neutral": "neutral fact",
              "discordant": "discordant update", "discordant_urgency": "urgency update",
              "discordant_reassure": "reassuring update", "discordant_dx": "diagnosis update"}


def _cell(x) -> str:
    if x is None or x == "":
        return "–"
    return str(x).replace("|", "\\|").replace("\n", " ")


def _quote(text: str) -> str:
    return "\n".join("> " + line if line.strip() else ">" for line in text.splitlines()) or ">"


def _fence(text: str) -> str:
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return f"{ticks}text\n{text.strip()}\n{ticks}"


def _reply_body(text: str) -> str:
    """Prose as markdown; each assessment block as a fenced block so its line breaks survive."""
    if not text.strip():
        return "*(empty reply)*"
    out, last = [], 0
    for m in RE_BLOCK.finditer(text):
        out.append(text[last:m.start()].strip())
        out.append(_fence(m.group(0)))
        last = m.end()
    out.append(text[last:].strip())
    return "\n\n".join(p for p in out if p)


def conversation_markdown(job: dict, script: dict, replies: list, run_name: str) -> str:
    f, gold = script["factors"], script["gold"]
    by_no = {r["reply_no"]: r for r in replies}
    api_model = next((r["api_model"] for r in replies if r["api_model"]), "")
    update = "none" if f["update_kind"] == "none" else f"{f['update_kind']} after reply {f['update_turn']}"
    lines = [
        f"# {script['script_id']} · repeat {job['repeat']} · {job['model']}",
        "",
        "| Vignette | Language | Perspective | Noise | Update | Status |",
        "| --- | --- | --- | --- | --- | --- |",
        f"| {f['vignette']} | {f['language']} | {f['perspective']} | {f['noise_type']} | {update} | "
        f"{job['status']}{' (' + job['end_reason'] + ')' if job['end_reason'] else ''} |",
        "",
        f"Run `{run_name}`, stage {job['stage']}, model `{api_model or job['model']}`. "
        f"Expected: start {gold['start_urgency']}, *{gold['start_dx']}*; after the discordant update "
        f"{gold['post_urgency']}, *{gold['post_dx']}* (changed: {gold['changed']}).",
        "",
        "## Summary",
        "",
        "| Reply | Answers | Urgency | Expected | Diagnosis | Urgency conf. | Dx conf. | Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for k in range(1, N_REPLIES + 1):
        r = by_no.get(k)
        e = extract(r["reply_text"] if r else None, r["stop_reason"] if r else None, committed=r is not None)
        kind = "opening" if k == 1 else TURN_LABEL[script["turn_kinds"][k - 2]]
        exp = script["expected"][k - 1]["urgency"]
        lines.append(f"| {k} | {kind} | {_cell(e['urgency'])} | {exp} | {_cell(e['diagnosis'])} | "
                     f"{_cell(e['urgency_confidence'])} | {_cell(e['diagnosis_confidence'])} | {e['status']} |")
    lines += ["", "<details><summary>System prompt</summary>", "", _fence(script["system_prompt"]), "", "</details>",
              "", "## Conversation", ""]
    for k in range(1, N_REPLIES + 1):
        user = script["opening"] if k == 1 else script["turns"][k - 2]
        title = "Opening message" if k == 1 else f"Turn {k - 1}: {TURN_LABEL[script['turn_kinds'][k - 2]]}"
        lines += [f"### {title} (user)", "", _quote(user), ""]
        r = by_no.get(k)
        if r is None:
            reason = job["end_reason"] if job["status"] == "ended" else "not yet run or not committed"
            lines += [f"### Reply {k}", "", f"*Not recorded: {reason}.*", ""]
            if job["status"] == "ended":
                break
            continue
        meta = f"stop: {r['stop_reason']}, output tokens: {r['output_tokens']}"
        lines += [f"### Reply {k}", "", f"<sub>{meta}</sub>", ""]
        for b in json.loads(r["content_json"] or "[]"):
            if b.get("type") == "thinking":
                if (b.get("thinking") or "").strip():
                    lines += ["<details><summary>Thinking</summary>", "", _fence(b["thinking"]), "", "</details>", ""]
                else:
                    lines += ["*(thinking block present; the API did not return its text)*", ""]
            elif b.get("type") == "redacted_thinking":
                lines += ["*(redacted thinking block)*", ""]
        lines += [_reply_body(r["reply_text"]), ""]
    return "\n".join(lines).rstrip() + "\n"


def export_markdown(db, run_dir: Path) -> list[Path]:
    run_name = Path(run_dir).name
    paths = []
    for (model,) in db.execute("SELECT DISTINCT model FROM jobs ORDER BY model").fetchall():
        outdir = Path(run_dir) / "transcripts" / model
        index = [f"# Transcripts: run `{run_name}`, model {model}", "",
                 "| Conversation | Repeat | Noise | Update | Status | Urgency by reply |",
                 "| --- | --- | --- | --- | --- | --- |"]
        for j in db.execute("SELECT * FROM jobs WHERE model=? ORDER BY stage_index, script_id, repeat", (model,)):
            job = dict(j)
            script = json.loads(job["script_json"])
            reps = dbm.replies_for(db, job["job_id"])
            name = f"{script['script_id']}_r{job['repeat']}.md"
            write_text(outdir / name, conversation_markdown(job, script, reps, run_name))
            paths.append(outdir / name)
            f = script["factors"]
            urg = " ".join(extract(r["reply_text"], r["stop_reason"])["urgency"] or "?" for r in reps)
            update = "none" if f["update_kind"] == "none" else f"{f['update_kind']} {f['update_turn']}"
            index.append(f"| [{script['script_id']}]({name}) | {job['repeat']} | {f['noise_type']} | {update} | "
                         f"{job['status']} | {urg or '–'} |")
        write_text(outdir / "index.md", "\n".join(index) + "\n")
        paths.append(outdir / "index.md")
    return paths
