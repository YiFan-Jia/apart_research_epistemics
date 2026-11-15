"""Asset contract and validator (build spec 6.1).

Reads the teammate's files in a scenarios directory and reports, stage by stage, what is
ready and what is missing. This module never writes those files.

Usage:
    python -m src.assets                       # validate scenarios/
    python -m src.assets --scenarios scenarios/fixture
    python -m src.assets --allow-unapproved    # development only
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .common import (
    ASSET_STATUSES, CHANGED_VALUES, LANGUAGES, NOISE_TYPES, N_FOLLOWUPS, PERSPECTIVES, ROOT, SLOTS,
    UNCERTAINTY_VALUES, URGENCY_LEVELS, is_two_update, load_config, read_json, slots_for, update_kinds,
    update_text_field, urgency_rank,
)

VIGNETTE_TEXT_FIELDS = ["id", "clerking", "start_dx", "supportive_update", "discordant_update", "post_dx"]
VIGNETTE_LIST_FIELDS = ["start_accept", "post_accept"]

RE_HAN = re.compile(r"[一-鿿]")
RE_KANA = re.compile(r"[぀-ヿ]")
RE_CJK_ANY = re.compile(r"[぀-ヿ一-鿿]")
RE_LEFTOVER = re.compile(
    r"(\bTODO\b|\bTBD\b|\bFIXME\b|\bXXX\b|\bNOTE\s*:|translator'?s? note|\bplaceholder\b|\[\[|\]\]|\{\{|\}\}|<<|>>"
    r"|^\s*(here is|here's|sure[,!]|translation\s*:|back[- ]translation)|^\s*(patient|nurse|consultant) version\s*:)",
    re.IGNORECASE,
)


def _norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", s).lower().split())


# ---------------------------------------------------------------- loading

@dataclass
class Scenarios:
    vignettes: dict[str, dict]
    assets: dict[tuple, dict]          # (vignette, perspective, language, slot) -> record
    noise: dict[tuple, dict]           # (noise_type, language, position) -> record
    system_prompt: dict | None
    asks: dict[tuple, dict]            # (perspective, language) -> record
    load_errors: list[str] = field(default_factory=list)
    scale_version: str | None = None   # config urgency_scale_version; set by whoever validates against a config


def _load(path: Path, key: str, errors: list[str]):
    if not path.exists():
        return None
    try:
        data = read_json(path)
    except Exception as e:  # noqa: BLE001
        errors.append(f"{path.name}: cannot be read as UTF-8 JSON ({e})")
        return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and key in data:
        return data[key]
    if isinstance(data, dict):
        return data
    errors.append(f"{path.name}: expected an object with '{key}' or a list")
    return None


def load_scenarios(scen_dir: Path | str) -> Scenarios:
    d = Path(scen_dir)
    errors: list[str] = []

    vignettes: dict[str, dict] = {}
    for v in _load(d / "vignettes.json", "vignettes", errors) or []:
        vid = v.get("id") if isinstance(v, dict) else None
        if not vid:
            errors.append("vignettes.json: a record has no id")
            continue
        if vid in vignettes:
            errors.append(f"vignettes.json: duplicate id {vid}")
            continue
        vignettes[vid] = v

    assets: dict[tuple, dict] = {}
    for a in _load(d / "assets.json", "assets", errors) or []:
        k = (a.get("vignette"), a.get("perspective"), a.get("language"), a.get("slot"))
        if k in assets:
            errors.append(f"assets.json: duplicate record for {' '.join(map(str, k))}")
            continue
        assets[k] = a

    noise: dict[tuple, dict] = {}
    for m in _load(d / "noise_bank.json", "messages", errors) or []:
        k = (m.get("noise_type"), m.get("language"), m.get("position"))
        if k in noise:
            errors.append(f"noise_bank.json: duplicate record for {' '.join(map(str, k))}")
            continue
        noise[k] = m

    system_prompt, asks = None, {}
    pdata = None
    if (d / "prompts.json").exists():
        try:
            pdata = read_json(d / "prompts.json")
        except Exception as e:  # noqa: BLE001
            errors.append(f"prompts.json: cannot be read as UTF-8 JSON ({e})")
    if pdata:
        system_prompt = pdata.get("system_prompt")
        for a in pdata.get("asks", []):
            k = (a.get("perspective"), a.get("language"))
            if k in asks:
                errors.append(f"prompts.json: duplicate ask for {' '.join(map(str, k))}")
                continue
            asks[k] = a
    return Scenarios(vignettes, assets, noise, system_prompt, asks, errors)


# ---------------------------------------------------------------- checks

def text_problems(text, language: str | None) -> list[str]:
    """Problems with a single piece of text that the model will see."""
    if not isinstance(text, str) or not text.strip():
        return ["text missing or empty"]
    p = []
    if text != text.strip():
        p.append("leading or trailing whitespace")
    if "  " in text or "\t" in text or "\r" in text or "\n\n\n" in text:
        p.append("stray whitespace (double space, tab, CR or blank lines)")
    if RE_LEFTOVER.search(text):
        p.append("looks like a leftover note or preamble")
    if language == "zh":
        if not RE_HAN.search(text):
            p.append("no Chinese characters")
        if RE_KANA.search(text):
            p.append("contains Japanese kana")
    elif language == "ja":
        if not RE_KANA.search(text):
            p.append("no Japanese kana")
    elif language == "en":
        if RE_CJK_ANY.search(text):
            p.append("contains Chinese or Japanese characters")
    return p


def vignette_problems(v: dict, scale_version: str | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one vignette record.

    scale_version: the config's urgency_scale_version. When given, the record must name the same version, so a
    vignette keyed on a different urgency scale (other wording, or the letters the other way round) is refused
    instead of being scored backwards.
    """
    errs, warns = [], []
    if scale_version is not None and v.get("urgency_scale_version") != scale_version:
        errs.append(f"field 'urgency_scale_version' is {v.get('urgency_scale_version')!r} but config.json uses "
                    f"{scale_version!r}: the urgency answers must be set on the current scale, then this field updated")
    if is_two_update(v):
        return _two_update_problems(v, errs, warns)
    for f in VIGNETTE_TEXT_FIELDS:
        if not isinstance(v.get(f), str) or not v.get(f, "").strip():
            errs.append(f"field '{f}' missing or empty")
    for f in VIGNETTE_LIST_FIELDS:
        val = v.get(f)
        if not isinstance(val, list) or not all(isinstance(x, str) and x.strip() for x in val):
            errs.append(f"field '{f}' must be a list of names (may be empty)")
    for f in ["start_urgency", "post_urgency"]:
        if v.get(f) not in URGENCY_LEVELS:
            errs.append(f"field '{f}' must be one of A, B, C, D (got {v.get(f)!r})")
    if v.get("changed") not in CHANGED_VALUES:
        errs.append(f"field 'changed' must be one of {CHANGED_VALUES} (got {v.get('changed')!r})")
    if v.get("uncertainty") not in UNCERTAINTY_VALUES:
        errs.append(f"field 'uncertainty' must be one of {UNCERTAINTY_VALUES} (got {v.get('uncertainty')!r})")
    if errs:
        return errs, warns
    for f in ["clerking", "supportive_update", "discordant_update"]:
        errs += [f"field '{f}': {p}" for p in text_problems(v[f], "en")]
    s, d, c = _norm(v["supportive_update"]), _norm(v["discordant_update"]), _norm(v["clerking"])
    if s == d:
        errs.append("supportive and discordant updates are the same")
    if s in c or d in c:
        errs.append("an update repeats the clerking text")
    ch = v["changed"]
    if ch in ("urgency", "both") and v["start_urgency"] == v["post_urgency"]:
        errs.append(f"changed is '{ch}' but start and post urgency are both {v['start_urgency']}")
    if ch == "diagnosis" and v["start_urgency"] != v["post_urgency"]:
        errs.append("changed is 'diagnosis' but the urgency differs")
    if ch in ("diagnosis", "both") and _norm(v["start_dx"]) == _norm(v["post_dx"]):
        errs.append(f"changed is '{ch}' but start_dx and post_dx are the same")
    if ch == "urgency" and _norm(v["start_dx"]) != _norm(v["post_dx"]):
        errs.append("changed is 'urgency' but post_dx differs from start_dx")
    if ch in ("diagnosis", "both"):
        start_set = {_norm(x) for x in [v["start_dx"], *v["start_accept"]]}
        post_set = {_norm(x) for x in [v["post_dx"], *v["post_accept"]]}
        overlap = start_set & post_set
        if overlap:
            warns.append(f"start and post accepted names overlap: {sorted(overlap)} (should be mutually exclusive)")
    if not re.fullmatch(r"V\d\d", v["id"]):
        warns.append("id is not of the form V01..V20")
    return errs, warns


def _two_update_problems(v: dict, errs: list[str], warns: list[str]) -> tuple[list[str], list[str]]:
    """Checks for a record in the two-update format: a supportive update, and one or more of an urgency-only
    update, a diagnosis update and a reassuring update; a neutral fact is optional."""
    has_dx = v.get("dx_update") is not None
    has_rsu = v.get("reassuring_update") is not None
    for f in ["id", "clerking", "start_dx", "supportive_update"] + (["dx_update", "post_dx"] if has_dx else []):
        if not isinstance(v.get(f), str) or not v.get(f, "").strip():
            errs.append(f"field '{f}' missing or empty")
    for f in ["reassuring_update", "neutral_update"]:
        if v.get(f) is not None and (not isinstance(v[f], str) or not v[f].strip()):
            errs.append(f"field '{f}' must be text, or left out if the vignette has no such update")
    for f in VIGNETTE_LIST_FIELDS:
        val = v.get(f)
        if not isinstance(val, list) or not all(isinstance(x, str) and x.strip() for x in val):
            errs.append(f"field '{f}' must be a list of names (may be empty)")
    has_urg = v.get("urgency_update") is not None
    if has_urg and (not isinstance(v["urgency_update"], str) or not v["urgency_update"].strip()):
        errs.append("field 'urgency_update' must be text, or null if the vignette has no urgency-only update")
    if not (has_urg or has_dx or has_rsu):
        errs.append("the vignette has no discordant update: it needs an urgency update, a diagnosis update or a "
                    "reassuring update")
    for f in (["start_urgency"] + (["dx_post_urgency"] if has_dx else []) + (["urgency_post_urgency"] if has_urg else [])
              + (["reassuring_post_urgency"] if has_rsu else [])):
        if v.get(f) not in URGENCY_LEVELS:
            errs.append(f"field '{f}' must be one of A, B, C, D (got {v.get(f)!r})")
    if v.get("uncertainty") is not None and v.get("uncertainty") not in UNCERTAINTY_VALUES:
        errs.append(f"field 'uncertainty' must be one of {UNCERTAINTY_VALUES} or null (got {v.get('uncertainty')!r})")
    if errs:
        return errs, warns
    fields = [update_text_field(k) for k in update_kinds(v)]
    for f in ["clerking", *fields]:
        errs += [f"field '{f}': {p}" for p in text_problems(v[f], "en")]
    c = _norm(v["clerking"])
    texts = {f: _norm(v[f]) for f in fields}
    for i, a in enumerate(fields):
        for b in fields[i + 1:]:
            if texts[a] == texts[b]:
                errs.append(f"'{a}' and '{b}' are the same")
        if texts[a] in c:
            errs.append(f"'{a}' repeats the clerking text")
    if has_urg and v["urgency_post_urgency"] == v["start_urgency"]:
        errs.append(f"the urgency update leaves the urgency at {v['start_urgency']}: it cannot work as a discordant "
                    f"update. Change 'urgency_post_urgency', or set 'urgency_update' to null to run this vignette "
                    f"without an urgency-only update")
    if has_rsu and v["reassuring_post_urgency"] == v["start_urgency"]:
        errs.append(f"the reassuring update leaves the urgency at {v['start_urgency']}: it cannot work as a "
                    f"discordant update. Change 'reassuring_post_urgency', or leave 'reassuring_update' out")
    if has_rsu and has_urg and v["reassuring_post_urgency"] == v["urgency_post_urgency"]:
        errs.append("the urgency update and the reassuring update lead to the same urgency")
    if has_dx and _norm(v["start_dx"]) == _norm(v["post_dx"]):
        errs.append("post_dx is the same as start_dx: the diagnosis update must change the diagnosis")
    if not has_urg:
        warns.append("no urgency-only update: this vignette runs without that arm")
    if not has_dx:
        warns.append("no diagnosis update: this vignette runs without that arm")
    start_set = {_norm(x) for x in [v["start_dx"], *v["start_accept"]]}
    post_set = {_norm(x) for x in [v["post_dx"], *v["post_accept"]]} if has_dx else set()
    if start_set & post_set:
        warns.append(f"start and post accepted names overlap: {sorted(start_set & post_set)} (should be mutually exclusive)")
    if not re.fullmatch(r"V\d\d", v["id"]):
        warns.append("id is not of the form V01..V20")
    return errs, warns


def _status_ok(rec: dict, allow_unapproved: bool) -> str | None:
    st = rec.get("status")
    if st not in ASSET_STATUSES:
        return f"status {st!r} is not one of {ASSET_STATUSES}"
    if st != "approved" and not allow_unapproved:
        return f"status is {st} (needs approved)"
    return None


@dataclass
class Report:
    errors: list[str]                       # structural problems that make files unreadable or inconsistent
    warnings: list[str]
    unit_problems: dict[tuple, list[str]]   # (vignette, language, perspective) -> problems; empty list = ready
    shared_problems: dict[str, list[str]]   # 'system_prompt', 'ask en patient', 'noise en direct' -> problems
    stages: dict[str, dict]                 # stage -> {"ready": [...], "not_ready": {vid: [problems]}}

    def ready_vignettes(self, stage: str) -> list[str]:
        return self.stages[stage]["ready"]

    def ok(self) -> bool:
        return not self.errors


def unit_problems(sc: Scenarios, vid: str, lang: str, persp: str, allow_unapproved: bool) -> list[str]:
    """Problems with everything one (vignette, language, perspective) needs: its slots, the ask, the noise, the prompt."""
    probs: list[str] = []
    v = sc.vignettes.get(vid)
    if v is None:
        return [f"{vid}: no vignette record"]
    verrs, _ = vignette_problems(v, sc.scale_version)
    probs += [f"{vid} vignette: {e}" for e in verrs]
    texts = {}
    slots = slots_for(v)
    for slot in slots:
        tag = f"{vid} {lang} {persp} {slot}"
        a = sc.assets.get((vid, persp, lang, slot))
        if a is None:
            probs.append(f"{tag}: missing")
            continue
        p = text_problems(a.get("text"), lang)
        st = _status_ok(a, allow_unapproved)
        if st:
            p.append(st)
        probs += [f"{tag}: {x}" for x in p]
        if isinstance(a.get("text"), str):
            texts[slot] = _norm(a["text"])
    if len(texts) == len(slots):
        ups = slots[1:]
        for i, a in enumerate(ups):
            for b in ups[i + 1:]:
                if texts[a] == texts[b]:
                    probs.append(f"{vid} {lang} {persp}: {a} and {b} updates are the same")
            if texts[a] in texts["opening"]:
                probs.append(f"{vid} {lang} {persp} {a}: repeats the opening text")
    ask = sc.asks.get((persp, lang))
    if ask and isinstance(ask.get("text"), str) and "opening" in texts and _norm(ask["text"]) in texts["opening"]:
        probs.append(f"{vid} {lang} {persp} opening: includes the ask (the script builder appends it)")
    return probs


def shared_problems(sc: Scenarios, allow_unapproved: bool) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    sp = sc.system_prompt
    if not sp:
        out["system_prompt"] = ["missing from prompts.json"]
    else:
        p = []
        t = sp.get("text")
        if not isinstance(t, str) or not t.strip():
            p.append("text missing or empty")
        else:
            for tok in ["{urgency_levels}", "[[ASSESSMENT]]", "[[END]]", "Urgency:", "Diagnosis:",
                        "Urgency confidence:", "Diagnosis confidence:"]:
                if tok not in t:
                    p.append(f"does not contain {tok}")
        st = _status_ok(sp, allow_unapproved)
        if st:
            p.append(st)
        out["system_prompt"] = p
    for lang in LANGUAGES:
        for persp in PERSPECTIVES:
            a = sc.asks.get((persp, lang))
            key = f"ask {lang} {persp}"
            if a is None:
                out[key] = ["missing"]
                continue
            p = text_problems(a.get("text"), lang)
            st = _status_ok(a, allow_unapproved)
            if st:
                p.append(st)
            out[key] = p
        for nt in NOISE_TYPES:
            key = f"noise {lang} {nt}"
            p = []
            seen = set()
            for pos in range(1, N_FOLLOWUPS + 1):
                m = sc.noise.get((nt, lang, pos))
                if m is None:
                    p.append(f"message {pos}: missing")
                    continue
                q = text_problems(m.get("text"), lang)
                st = _status_ok(m, allow_unapproved)
                if st:
                    q.append(st)
                if isinstance(m.get("text"), str):
                    n = _norm(m["text"])
                    if n in seen:
                        q.append("duplicates an earlier message")
                    seen.add(n)
                p += [f"message {pos}: {x}" for x in q]
            extra = [k for k in sc.noise if k[0] == nt and k[1] == lang and k[2] not in range(1, N_FOLLOWUPS + 1)]
            if extra:
                p.append(f"unexpected positions {sorted(k[2] for k in extra)}")
            out[key] = p
    return out


def stage_vignette_ids(cfg: dict, stage: str, sc: Scenarios) -> list[str]:
    sdef = cfg["stages"][stage]
    if sdef.get("vignettes") == "pilot":
        return [v for v in cfg["pilot_vignettes"]]
    if isinstance(sdef.get("vignettes"), list):
        return list(sdef["vignettes"])
    return sorted(sc.vignettes)


def validate(scen_dir: Path | str, cfg: dict, allow_unapproved: bool = False) -> Report:
    sc = load_scenarios(scen_dir)
    sc.scale_version = cfg.get("urgency_scale_version")
    errors = list(sc.load_errors)
    warnings: list[str] = []
    try:
        urgency_rank(cfg)
    except ValueError as e:
        errors.append(str(e))
    for vid, v in sorted(sc.vignettes.items()):
        e, w = vignette_problems(v, sc.scale_version)
        errors += [f"{vid}: {x}" for x in e]
        warnings += [f"{vid}: {x}" for x in w]
    for k, a in sorted(sc.assets.items(), key=lambda kv: tuple(map(str, kv[0]))):
        vid, persp, lang, slot = k
        tag = " ".join(map(str, k))
        if vid not in sc.vignettes:
            errors.append(f"asset {tag}: no vignette record {vid}")
        if persp not in PERSPECTIVES or lang not in LANGUAGES or slot not in SLOTS:
            errors.append(f"asset {tag}: unknown perspective, language or slot")
        elif vid in sc.vignettes and slot not in slots_for(sc.vignettes[vid]):
            warnings.append(f"asset {tag}: this vignette has no '{slot}' update, so the text is not used")
        if a.get("status") not in ASSET_STATUSES:
            errors.append(f"asset {tag}: status {a.get('status')!r} is not one of {ASSET_STATUSES}")
    for k, m in sc.noise.items():
        if k[0] not in NOISE_TYPES or k[1] not in LANGUAGES or not isinstance(k[2], int):
            errors.append(f"noise {' '.join(map(str, k))}: unknown noise type, language or position")

    shared = shared_problems(sc, allow_unapproved)
    units: dict[tuple, list[str]] = {}
    stages: dict[str, dict] = {}
    for stage, sdef in cfg["stages"].items():
        # Problems shared by every vignette in the stage: system prompt, asks, noise bank.
        blocking = [f"system prompt: {x}" for x in shared["system_prompt"]]
        for lang in sdef["languages"]:
            for nt in NOISE_TYPES:
                blocking += [f"noise {lang} {nt}: {x}" for x in shared[f"noise {lang} {nt}"]]
            for persp in sdef["perspectives"]:
                blocking += [f"ask {lang} {persp}: {x}" for x in shared[f"ask {lang} {persp}"]]
        ready, not_ready = [], {}
        for vid in stage_vignette_ids(cfg, stage, sc):
            probs: list[str] = []
            for lang in sdef["languages"]:
                for persp in sdef["perspectives"]:
                    key = (vid, lang, persp)
                    if key not in units:
                        units[key] = unit_problems(sc, vid, lang, persp, allow_unapproved)
                    probs += units[key]
            if probs:
                not_ready[vid] = probs
            elif not blocking:
                ready.append(vid)
        stages[stage] = {"ready": ready, "blocking": blocking, "not_ready": not_ready,
                         "vignettes_considered": stage_vignette_ids(cfg, stage, sc)}
    return Report(errors, warnings, units, shared, stages)


def format_report(rep: Report, max_lines_per_vignette: int = 12) -> str:
    lines = []
    if rep.errors:
        lines.append(f"ERRORS ({len(rep.errors)}):")
        lines += [f"  - {e}" for e in rep.errors]
    if rep.warnings:
        lines.append(f"WARNINGS ({len(rep.warnings)}):")
        lines += [f"  - {w}" for w in rep.warnings]
    for stage, s in rep.stages.items():
        lines.append(f"STAGE {stage}: {len(s['ready'])} vignette(s) ready: {', '.join(s['ready']) or 'none'}")
        if not s["vignettes_considered"]:
            lines.append("  no vignette records found")
        if s["blocking"]:
            lines.append(f"  blocked for every vignette by {len(s['blocking'])} shared problem(s):")
            for p in s["blocking"][:max_lines_per_vignette]:
                lines.append(f"    - {p}")
            if len(s["blocking"]) > max_lines_per_vignette:
                lines.append(f"    ... and {len(s['blocking']) - max_lines_per_vignette} more")
        for vid, probs in s["not_ready"].items():
            lines.append(f"  {vid} not ready ({len(probs)} problem(s)):")
            for p in probs[:max_lines_per_vignette]:
                lines.append(f"    - {p}")
            if len(probs) > max_lines_per_vignette:
                lines.append(f"    ... and {len(probs) - max_lines_per_vignette} more")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenarios", default=str(ROOT / "scenarios"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--allow-unapproved", action="store_true", help="development only")
    ap.add_argument("--all", action="store_true", help="list every problem, not the first few per vignette")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.scenarios.rstrip("/\\").endswith("fixture") and args.config is None:
        cfg = dict(cfg, pilot_vignettes=["V00"])
    rep = validate(args.scenarios, cfg, args.allow_unapproved)
    print(format_report(rep, 10**6 if args.all else 12))
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
