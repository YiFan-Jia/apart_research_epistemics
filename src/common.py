"""Shared constants, UTF-8 file helpers, hashing and config loading.

Every file is read and written as UTF-8 with the encoding stated explicitly:
Windows defaults would corrupt the Chinese and Japanese text otherwise.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent

LANGUAGES = ["en", "zh", "ja"]
PERSPECTIVES = ["patient", "nurse", "consultant"]
NOISE_TYPES = ["nondirect", "direct"]
UPDATE_TURNS = [1, 3, 5, 10]
# Update kinds. A vignette record is in one of two formats (see scenarios/README.md):
#   two-update   an urgency-only update ("discordant_urgency", may be absent) and a diagnosis update
#                ("discordant_dx", may be absent); the format the clinicians deliver from 15 Nov. Such a record
#                may also have a reassuring update ("discordant_reassure": the urgency goes down and the
#                diagnosis stays; the reversal cases) and a neutral fact ("neutral": new but irrelevant)
#   one-update   a single "discordant" update with a "changed" field; the fixture and the runs before 15 Nov
# After a stable kind nothing should change; after a discordant kind the reference answer changes.
STABLE_KINDS = ["supportive", "neutral"]
DISCORDANT_KINDS = ["discordant", "discordant_urgency", "discordant_reassure", "discordant_dx"]
SLOTS = ["opening", *STABLE_KINDS, *DISCORDANT_KINDS]      # every slot name an asset record may carry
KIND_CODES = {"supportive": "sup", "neutral": "neu", "discordant": "dis", "discordant_urgency": "urg",
              "discordant_reassure": "rsu", "discordant_dx": "ddx"}
KIND_LABELS = {"supportive": "supportive update", "neutral": "neutral fact", "discordant": "discordant update",
               "discordant_urgency": "urgency update", "discordant_reassure": "reassuring update",
               "discordant_dx": "diagnosis update"}
# The one-update conditions; update_conditions(record) gives the conditions of a particular vignette.
UPDATE_CONDITIONS = [("none", 0)] + [("supportive", t) for t in UPDATE_TURNS] + [
    ("discordant", t) for t in UPDATE_TURNS
]
URGENCY_LEVELS = ["A", "B", "C", "D"]  # which end is most urgent is config: urgency_most_urgent_first
N_FOLLOWUPS = 10
N_REPLIES = 11
CHANGED_VALUES = ["diagnosis", "urgency", "both"]
UNCERTAINTY_VALUES = ["low", "medium", "high"]
ASSET_STATUSES = ["draft", "auto_checked", "flagged", "approved"]


def is_discordant(kind: str | None) -> bool:
    return kind in DISCORDANT_KINDS


def is_two_update(v: dict) -> bool:
    """True for a vignette record in the two-update format."""
    return "dx_update" in v or "urgency_update" in v


def update_kinds(v: dict) -> list[str]:
    """The update kinds a vignette record has, in the order they are built."""
    if not is_two_update(v):
        return ["supportive", "discordant"]
    return (["supportive"] + (["neutral"] if v.get("neutral_update") else [])
            + (["discordant_urgency"] if v.get("urgency_update") else [])
            + (["discordant_reassure"] if v.get("reassuring_update") else [])
            + (["discordant_dx"] if v.get("dx_update") else []))


def update_conditions(v: dict) -> list[tuple[str, int]]:
    """(kind, turn) for every conversation type of a vignette: no update, then each update at each timing."""
    return [("none", 0)] + [(k, t) for k in update_kinds(v) for t in UPDATE_TURNS]


def slots_for(v: dict) -> list[str]:
    """The asset slots a vignette needs for each perspective and language."""
    return ["opening", *update_kinds(v)]


def update_text_field(kind: str) -> str:
    """The vignette-record field that holds the English text of an update kind."""
    return {"supportive": "supportive_update", "neutral": "neutral_update", "discordant": "discordant_update",
            "discordant_urgency": "urgency_update", "discordant_reassure": "reassuring_update",
            "discordant_dx": "dx_update"}[kind]


# ---------------------------------------------------------------- files

def read_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def read_json(path: Path | str) -> Any:
    return json.loads(read_text(path))


def _atomic_write(path: Path, data: str) -> None:
    """Write via a temp file and rename, so an interrupted write never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_text(path: Path | str, text: str) -> None:
    _atomic_write(Path(path), text)


def write_json(path: Path | str, obj: Any) -> None:
    _atomic_write(Path(path), json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def read_jsonl(path: Path | str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(path: Path | str, rows: Iterable[dict]) -> None:
    _atomic_write(Path(path), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


# ---------------------------------------------------------------- hashing

def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(obj: Any, n: int = 16) -> str:
    data = obj if isinstance(obj, str) else canonical(obj)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:n]


# ---------------------------------------------------------------- config

def load_config(path: Path | str | None = None) -> dict:
    return read_json(path or ROOT / "config.json")


def config_hash(cfg: dict) -> str:
    """Hash of the config settings that change what the tested model sees or how it samples.

    Concurrency, spend caps and retry settings are left out: changing them does not change the data.
    """
    gen = {
        "stated_location": cfg.get("stated_location"),
        "urgency_levels": cfg.get("urgency_levels"),
        **({"urgency_scale_version": cfg["urgency_scale_version"]} if cfg.get("urgency_scale_version") else {}),
        "max_tokens": cfg.get("max_tokens"),
        "cache_control": cfg.get("cache_control"),
        "models": {
            name: {"api_model": m["api_model"], "request_options": m.get("request_options", {}),
                   "max_tokens": m.get("max_tokens", cfg.get("max_tokens"))}
            for name, m in sorted(cfg["models"].items())
        },
    }
    return sha(gen)


def urgency_rank(cfg: dict) -> dict[str, int]:
    """Letter -> rank, 0 = most urgent, from config urgency_most_urgent_first (a permutation of A-D)."""
    order = cfg.get("urgency_most_urgent_first")
    if sorted(order or []) != URGENCY_LEVELS:
        raise ValueError("config.json: urgency_most_urgent_first must list A, B, C and D once each, most urgent first")
    return {u: i for i, u in enumerate(order)}


def stage_names(cfg: dict) -> list[str]:
    return list(cfg["stages"].keys())


def code_version() -> str:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "src", "config.json"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return head + ("+dirty" if dirty else "") if head else "unknown"
    except Exception:
        return "unknown"


def load_dotenv_if_present() -> None:
    """Load ANTHROPIC_API_KEY etc. from the gitignored .env. Never print the values."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in read_text(env).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v and k not in os.environ:
            os.environ[k] = v
