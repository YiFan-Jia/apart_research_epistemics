"""Script builder (build spec 6.2). Build time, no model.

A pure function from the six factors to a script. Scripts are built stage by stage: a stage
builds when only the assets it uses are approved.

Usage:
    python -m src.scripts                     # build every stage that is ready, write scenarios/scripts.jsonl
    python -m src.scripts --stage 1
    python -m src.scripts --scenarios scenarios/fixture --out results/fixture_scripts.jsonl --allow-unapproved
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .assets import Scenarios, format_report, load_scenarios, unit_problems, validate
from .common import (
    NOISE_TYPES, N_FOLLOWUPS, N_REPLIES, ROOT, UPDATE_CONDITIONS, load_config, read_jsonl, sha, write_jsonl,
)

SCRIPT_HASH_FIELDS_EXCLUDED = ("assets_hash",)


class BuildError(Exception):
    pass


def condition_code(kind: str, turn: int) -> str:
    return "none" if kind == "none" else f"{kind[:3]}{turn:02d}"


def script_id(vid: str, lang: str, persp: str, noise: str, kind: str, turn: int) -> str:
    return f"{vid}_{lang}_{persp}_{noise}_{condition_code(kind, turn)}"


def render_system_prompt(template: str, cfg: dict, dev: bool = False) -> str:
    loc = (cfg.get("stated_location") or "").strip()
    if not loc:
        if not dev:
            raise BuildError("config.json: stated_location is empty; the team must set it before the pilot")
        loc = "[stated location]"
    return template.replace("{location}", loc).replace("{urgency_levels}", " ".join(cfg["urgency_levels"]))


def accepted_names_version(v: dict) -> str:
    return sha({k: v[k] for k in ["start_dx", "start_accept", "post_dx", "post_accept", "changed"]}, 12)


def build_script(sc: Scenarios, cfg: dict, vid: str, lang: str, persp: str, noise: str, kind: str, turn: int,
                 dev: bool = False) -> dict:
    """Build one script. Raises KeyError if an asset is missing; checking approval is the caller's job."""
    v = sc.vignettes[vid]
    opening_asset = sc.assets[(vid, persp, lang, "opening")]["text"]
    ask = sc.asks[(persp, lang)]["text"]
    noise_msgs = [sc.noise[(noise, lang, pos)]["text"] for pos in range(1, N_FOLLOWUPS + 1)]
    update_text = sc.assets[(vid, persp, lang, kind)]["text"] if kind != "none" else None

    turns, kinds = [], []
    for t in range(1, N_FOLLOWUPS + 1):
        if kind != "none" and t == turn:
            turns.append(update_text)
            kinds.append(kind)
        else:
            turns.append(noise_msgs[t - 1])
            kinds.append("noise")

    # Follow-up turn t is answered at reply t+1. From the discordant update's reply onward the
    # expected answer is the post-update answer. Where only urgency changes there is one diagnosis target.
    dx_post_target = "post" if v["changed"] in ("diagnosis", "both") else "start"
    expected = []
    for r in range(1, N_REPLIES + 1):
        after = kind == "discordant" and r >= turn + 1
        expected.append({
            "reply": r,
            "urgency": v["post_urgency"] if after else v["start_urgency"],
            "dx_target": dx_post_target if after else "start",
        })

    s = {
        "script_id": script_id(vid, lang, persp, noise, kind, turn),
        "factors": {"vignette": vid, "language": lang, "perspective": persp, "noise_type": noise,
                    "update_kind": kind, "update_turn": turn},
        "system_prompt": render_system_prompt(sc.system_prompt["text"], cfg, dev),
        "opening": opening_asset + "\n\n" + ask,
        "turns": turns,
        "turn_kinds": kinds,
        # Scoring only. The runner never sends anything below this line to the model.
        "expected": expected,
        "gold": {
            "start_dx": v["start_dx"], "start_accept": list(v["start_accept"]),
            "post_dx": v["post_dx"], "post_accept": list(v["post_accept"]),
            "start_urgency": v["start_urgency"], "post_urgency": v["post_urgency"],
            "changed": v["changed"], "uncertainty": v["uncertainty"],
            "accepted_names_version": accepted_names_version(v),
        },
    }
    s["assets_hash"] = script_hash(s)
    return s


def script_hash(s: dict) -> str:
    return sha({k: val for k, val in s.items() if k not in SCRIPT_HASH_FIELDS_EXCLUDED})


def unit_scripts(sc: Scenarios, cfg: dict, vid: str, lang: str, persp: str, dev: bool = False) -> list[dict]:
    """The 18 scripts for one vignette x language x perspective: 2 noise types x 9 update conditions."""
    return [build_script(sc, cfg, vid, lang, persp, nt, kind, turn, dev)
            for nt in NOISE_TYPES for kind, turn in UPDATE_CONDITIONS]


def build_stage(scen_dir: Path | str, cfg: dict, stage: str, allow_unapproved: bool = False) -> tuple[list[dict], dict]:
    """Scripts for the vignettes that are ready for this stage, and the validation report."""
    rep = validate(scen_dir, cfg, allow_unapproved)
    sc = load_scenarios(scen_dir)
    sdef = cfg["stages"][stage]
    scripts = []
    for vid in rep.ready_vignettes(stage):
        for lang in sdef["languages"]:
            for persp in sdef["perspectives"]:
                scripts += unit_scripts(sc, cfg, vid, lang, persp, dev=allow_unapproved)
    return scripts, rep


def build_all(scen_dir: Path | str, cfg: dict, stages: list[str] | None = None,
              allow_unapproved: bool = False) -> tuple[list[dict], object]:
    stages = stages or list(cfg["stages"])
    by_id: dict[str, dict] = {}
    rep = None
    for st in stages:
        scripts, rep = build_stage(scen_dir, cfg, st, allow_unapproved)
        for s in scripts:
            by_id[s["script_id"]] = s
    return sorted(by_id.values(), key=lambda s: s["script_id"]), rep


def rebuild_scripts(scen_dir: Path | str, cfg: dict, script_ids: list[str], allow_unapproved: bool = False) -> dict:
    """Rebuild the given scripts from the current files: script_id -> script, or -> None if it cannot be built.

    Used by the runner to refuse a resume after any asset a run uses has changed.
    """
    rep = validate(scen_dir, cfg, allow_unapproved)
    sc = load_scenarios(scen_dir)
    out = {}
    for sid in script_ids:
        vid, lang, persp, noise, cond = sid.split("_")
        kind = "none" if cond == "none" else {"sup": "supportive", "dis": "discordant"}[cond[:3]]
        turn = 0 if cond == "none" else int(cond[3:])
        if rep.unit_problems.get((vid, lang, persp)) is None:
            rep.unit_problems[(vid, lang, persp)] = unit_problems(sc, vid, lang, persp, allow_unapproved)
        if rep.unit_problems[(vid, lang, persp)]:
            out[sid] = None
            continue
        try:
            out[sid] = build_script(sc, cfg, vid, lang, persp, noise, kind, turn, dev=allow_unapproved)
        except (KeyError, BuildError):
            out[sid] = None
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenarios", default=str(ROOT / "scenarios"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--stage", action="append", help="stage name; repeatable; default all stages")
    ap.add_argument("--out", default=None, help="default <scenarios>/scripts.jsonl")
    ap.add_argument("--allow-unapproved", action="store_true", help="development and testing only")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.scenarios.rstrip("/\\").endswith("fixture") and args.config is None:
        cfg = dict(cfg, pilot_vignettes=["V00"])
    try:
        scripts, rep = build_all(args.scenarios, cfg, args.stage, args.allow_unapproved)
    except BuildError as e:
        print(f"ERROR: {e}")
        return 2
    print(format_report(rep))
    out = Path(args.out) if args.out else Path(args.scenarios) / "scripts.jsonl"
    # Keep scripts already in the file for stages not rebuilt now, so stages can be built one at a time.
    existing = {s["script_id"]: s for s in read_jsonl(out)} if out.exists() else {}
    existing.update({s["script_id"]: s for s in scripts})
    rows = sorted(existing.values(), key=lambda s: s["script_id"])
    write_jsonl(out, rows)
    print(f"built {len(scripts)} script(s) now; {len(rows)} in {out}")
    if args.allow_unapproved:
        print("WARNING: built with --allow-unapproved; these scripts are for testing only")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
