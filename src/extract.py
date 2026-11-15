"""Extractor (build spec 6.5). Score time.

Reads urgency, diagnosis and the two confidences from the last [[ASSESSMENT]] block of a reply.
Each field is parsed and validated on its own: a malformed confidence never discards a valid urgency.
Confidence is taken only from the block, never inferred from words. If a field cannot be read it is
missing; nothing is guessed.

The model fallback for missing urgency or diagnosis (spec 6.5) is not built: build it only if the
pilot shows more than about 1% of replies need it. Until then those fields are missing (source 'none').
"""
from __future__ import annotations

import re
import unicodedata

STATUSES = ["answered", "no_assessment", "refusal", "truncated", "malformed", "technical_failure"]

RE_BLOCK_START = re.compile(r"\[\[\s*assessment\s*\]\]", re.IGNORECASE)
RE_BLOCK_END = re.compile(r"\[\[\s*end\s*\]\]", re.IGNORECASE)
RE_URGENCY = re.compile(r"^(?:level\s*|urgency\s*)?\(?([ABCD])\)?(?![A-Za-z0-9])", re.IGNORECASE)
RE_CONF = re.compile(r"^(\d{1,3})(?:\.0+)?\s*%?$")
RE_MARKUP = re.compile(r"[*_`#>]+")
EMPTY_DX = {"", "n/a", "na", "none", "unknown", "-", "--", "?", "not sure", "unsure",
            "the single most likely diagnosis"}
FIELDS = ["urgency", "diagnosis", "urgency_confidence", "diagnosis_confidence"]


def normalise(text: str) -> str:
    """NFKC turns full-width letters, digits, colons and brackets into ASCII; also unify odd spaces."""
    t = unicodedata.normalize("NFKC", text)
    return t.replace("　", " ").replace(" ", " ")


def find_blocks(text: str) -> list[str]:
    """Bodies of every assessment block. An unterminated last block runs to the end of the text."""
    starts = [m for m in RE_BLOCK_START.finditer(text)]
    bodies = []
    for i, m in enumerate(starts):
        nxt = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        seg = text[m.end():nxt]
        e = RE_BLOCK_END.search(seg)
        bodies.append(seg[: e.start()] if e else seg)
    return bodies


def _label_kind(label: str) -> str | None:
    lab = label.lower()
    if "confidence" in lab or "certainty" in lab:
        if "urgency" in lab:
            return "urgency_confidence"
        if "diagnos" in lab:
            return "diagnosis_confidence"
        return None
    if "urgency" in lab:
        return "urgency"
    if "diagnos" in lab:
        return "diagnosis"
    return None


def _split_lines(body: str) -> list[tuple[str, str]]:
    out = []
    for raw in body.splitlines():
        line = RE_MARKUP.sub("", raw).strip()
        line = re.sub(r"^[-•・]\s*", "", line)  # bullets: - • ・
        if not line:
            continue
        m = re.match(r"^([^:=]{1,60}?)\s*[:=]\s*(.*)$", line)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def parse_urgency(value: str | None) -> str | None:
    if value is None:
        return None
    v = RE_MARKUP.sub("", value).strip().strip(".").strip()
    m = RE_URGENCY.match(v)
    if not m:
        return None
    rest = v[m.end():]
    # "B or C", "B/C", "B-C": two levels named, so no single answer.
    if re.search(r"(?<![A-Za-z])[ABCD](?![A-Za-z])", rest):
        return None
    return m.group(1).upper()


def parse_confidence(value: str | None) -> int | None:
    if value is None:
        return None
    v = RE_MARKUP.sub("", value).strip().rstrip(".").strip()
    m = RE_CONF.match(v)
    if not m:
        return None
    n = int(m.group(1))
    return n if 0 <= n <= 100 else None


def parse_diagnosis(value: str | None) -> str | None:
    if value is None:
        return None
    v = RE_MARKUP.sub("", value).strip().strip(".").strip()
    if v.lower() in EMPTY_DX:
        return None
    return v


def parse_block(body: str) -> dict:
    """Raw field strings from one block body, by label, else by position where the four lines are in order."""
    lines = _split_lines(body)
    by_label: dict[str, str] = {}
    for label, value in lines:
        k = _label_kind(label)
        if k and k not in by_label:
            by_label[k] = value
    if len(by_label) == 4:
        return by_label
    if len(lines) == 4:
        # Translated labels: take the four fields in order, if any English labels found agree with position.
        positional = dict(zip(FIELDS, [v for _, v in lines]))
        if all(positional[k] == by_label[k] for k in by_label):
            return positional
    return by_label


def extract(reply_text: str | None, stop_reason: str | None = None, committed: bool = True) -> dict:
    """Extraction for one reply. committed=False means no reply exists (technical failure)."""
    out = {
        "status": None, "multi_block": False, "n_blocks": 0,
        "urgency": None, "urgency_source": "none",
        "diagnosis": None, "diagnosis_source": "none",
        "urgency_confidence": None, "urgency_confidence_source": "none",
        "diagnosis_confidence": None, "diagnosis_confidence_source": "none",
    }
    if not committed or reply_text is None:
        out["status"] = "technical_failure"
        return out
    if not reply_text.strip():
        out["status"] = "refusal" if stop_reason == "refusal" else "technical_failure"
        return out
    text = normalise(reply_text)
    blocks = find_blocks(text)
    out["n_blocks"] = len(blocks)
    out["multi_block"] = len(blocks) > 1
    if blocks:
        raw = parse_block(blocks[-1])
        parsed = {
            "urgency": parse_urgency(raw.get("urgency")),
            "diagnosis": parse_diagnosis(raw.get("diagnosis")),
            "urgency_confidence": parse_confidence(raw.get("urgency_confidence")),
            "diagnosis_confidence": parse_confidence(raw.get("diagnosis_confidence")),
        }
        for k, val in parsed.items():
            if val is not None:
                out[k] = val
                out[f"{k}_source"] = "block"
    if stop_reason == "refusal":
        out["status"] = "refusal"
    elif stop_reason == "max_tokens":
        out["status"] = "truncated"
    elif not blocks:
        out["status"] = "no_assessment"
    elif out["urgency"] is None:
        out["status"] = "malformed"
    else:
        out["status"] = "answered"
    return out


RE_PROSE_LEVEL = re.compile(r"\(\s*([ABCD])\s*\)|\b(?i:level|urgency)\s*:?\s*([ABCD])\b(?!['’-])")


def prose_levels(reply_text: str | None) -> list[str]:
    """Urgency letters the prose names outright, outside the assessment block: "(C)", "level B", "urgency: A".

    Used only to flag a reply whose prose names urgency levels that do not include the level in its block.
    It is deliberately narrow: capital letters only, and it cannot read "come in today" as a level. So it
    finds some contradictions, not all of them.
    """
    if not reply_text:
        return []
    text = normalise(reply_text)
    m = RE_BLOCK_START.search(text)
    prose = RE_MARKUP.sub("", text[: m.start()] if m else text)
    return sorted({g.group(1) or g.group(2) for g in RE_PROSE_LEVEL.finditer(prose)})
