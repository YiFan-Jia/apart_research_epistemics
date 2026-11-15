"""Cost and time forecast from a finished run's measured usage (no model call).

Usage:
    python -m src.forecast --from-run v01_en_full --stage pilot --models haiku
    python -m src.forecast --from-run v01_en_full --stage core10 --models haiku

For each target model it takes the mean tokens per conversation measured in the source run (from the same
model if the source run has it, otherwise from the source model named by --like, default the first one
found) and prices them with the target model's prices in config.json. Time is the measured seconds of model
latency per conversation divided by the target's concurrency; it assumes rate limits allow that concurrency,
which only a real run shows. Token use changes with thinking settings and with the model, so a figure
borrowed from another model is a rough guide, and is marked as such.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import db as dbm
from .clients import cost_usd
from .common import NOISE_TYPES, ROOT, UPDATE_TURNS, load_config, read_json, update_conditions

USAGE = ["input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"]


def measured_usage(db) -> dict[str, dict]:
    """Per model: mean tokens and seconds per finished conversation, counting failed attempts' tokens too."""
    out = {}
    for (model,) in db.execute("SELECT DISTINCT model FROM jobs").fetchall():
        n = db.execute("SELECT COUNT(*) FROM jobs WHERE model=? AND status IN ('complete','ended')", (model,)).fetchone()[0]
        if not n:
            continue
        row = db.execute(
            f"SELECT {', '.join(f'COALESCE(SUM({k}),0)' for k in USAGE)}, COALESCE(SUM(latency_s),0) "
            "FROM attempts WHERE model=? AND job_id IN (SELECT job_id FROM jobs WHERE status IN ('complete','ended'))",
            (model,)).fetchone()
        out[model] = {"conversations": n, **{k: row[i] / n for i, k in enumerate(USAGE)}, "latency_s": row[4] / n}
    return out


def conversations_per_model(cfg: dict, stages: list[str], n_vignettes: int | None) -> dict[str, int]:
    """Planned conversations per model for each stage. n_vignettes overrides the count for non-pilot stages."""
    # Conversation types per vignette: taken from the vignette records where there are any (a vignette with no
    # urgency-only update has fewer), else the two-update count (no update + 3 update kinds x 4 timings).
    default = 1 + 3 * len(UPDATE_TURNS)
    conds = {v["id"]: len(update_conditions(v)) for v in _vignettes()}
    mean_conds = sum(conds.values()) / len(conds) if conds else default
    out = {}
    for st in stages:
        sdef = cfg["stages"][st]
        if sdef.get("vignettes") == "pilot" or isinstance(sdef.get("vignettes"), list):
            ids = cfg["pilot_vignettes"] if sdef.get("vignettes") == "pilot" else sdef["vignettes"]
            types = sum(conds.get(i, default) for i in ids)
        elif n_vignettes is not None or not conds:
            types = (n_vignettes if n_vignettes is not None else 20) * mean_conds
        else:
            types = sum(conds.values())
        out[st] = round(types * len(NOISE_TYPES) * len(sdef["languages"]) * len(sdef["perspectives"]) * sdef["repeats"])
    return out


def _vignettes() -> list[dict]:
    p = ROOT / "scenarios" / "vignettes.json"
    if not p.exists():
        return []
    data = read_json(p)
    return data["vignettes"] if isinstance(data, dict) else data


def forecast(cfg: dict, usage: dict[str, dict], stages: list[str], models: list[str], n_vignettes: int | None = None,
             like: str | None = None) -> list[dict]:
    convs = conversations_per_model(cfg, stages, n_vignettes)
    rows = []
    for m in models:
        mc = cfg["models"][m]
        src = m if m in usage else (like or next(iter(usage)))
        u = usage[src]
        per_conv = cost_usd(u, mc["prices_per_mtok"])
        for st in stages:
            n = convs[st]
            rows.append({"model": m, "stage": st, "conversations": n, "usage_from": src, "borrowed": src != m,
                         "usd_per_conversation": per_conv, "usd": per_conv * n,
                         "hours_at_concurrency": u["latency_s"] * n / mc.get("concurrency", 8) / 3600,
                         "concurrency": mc.get("concurrency", 8), "spend_cap_usd": mc.get("spend_cap_usd")})
    return rows


def format_rows(rows: list[dict]) -> str:
    lines = [f"{'model':<8} {'stage':<7} {'convs':>7} {'$/conv':>8} {'$ total':>9} {'hours':>6} {'conc':>5}  usage from"]
    totals: dict[str, float] = {}
    for r in rows:
        totals[r["model"]] = totals.get(r["model"], 0) + r["usd"]
        lines.append(f"{r['model']:<8} {r['stage']:<7} {r['conversations']:>7} {r['usd_per_conversation']:>8.4f} "
                     f"{r['usd']:>9.2f} {r['hours_at_concurrency']:>6.1f} {r['concurrency']:>5}  "
                     f"{r['usage_from']}{' (borrowed: rough)' if r['borrowed'] else ''}")
    caps = {r["model"]: r["spend_cap_usd"] for r in rows}
    for m, t in totals.items():
        cap = caps[m]
        note = "" if cap is None else (" OVER the spend cap" if t > cap else " within the spend cap")
        lines.append(f"{m}: ${t:.2f} for these stages; spend cap ${cap}{note} (a cap applies to one run)")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-run", required=True, help="a finished run whose usage is the basis")
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--stage", action="append", required=True)
    ap.add_argument("--models", nargs="+", default=None)
    ap.add_argument("--vignettes", type=int, default=None, help="vignettes in non-pilot stages (default 20)")
    ap.add_argument("--like", default=None, help="source model to borrow usage from for models not in the source run")
    args = ap.parse_args(argv)
    cfg = load_config()
    usage = measured_usage(dbm.connect(Path(args.results) / args.from_run / "run.sqlite"))
    if not usage:
        print("ERROR: the source run has no finished conversations")
        return 2
    for m, u in usage.items():
        print(f"measured in {args.from_run} [{m}]: {u['conversations']} conversations; per conversation "
              f"{u['input_tokens']:.0f} input, {u['output_tokens']:.0f} output, {u['cache_creation_input_tokens']:.0f} "
              f"cache-write, {u['cache_read_input_tokens']:.0f} cache-read tokens; {u['latency_s']:.0f} s of model time")
    print(format_rows(forecast(cfg, usage, args.stage, args.models or list(cfg["models"]), args.vignettes, args.like)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
