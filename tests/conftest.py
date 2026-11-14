"""Shared test fixtures: a test config, a temporary copy of the V00 fixture, helpers to run the mock."""
from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.common import load_config, read_json, read_jsonl, write_json  # noqa: E402
from src.scripts import build_all  # noqa: E402

FIXTURE = ROOT / "scenarios" / "fixture"


def make_cfg(**over) -> dict:
    cfg = copy.deepcopy(load_config(ROOT / "config.json"))
    cfg["stated_location"] = "the United Kingdom"
    cfg["pilot_vignettes"] = ["V00"]
    cfg["runner"].update({"backoff_base_s": 0.001, "backoff_max_s": 0.002, "max_retries": 3,
                          "circuit_breaker_failures": 5})
    for m in cfg["models"].values():
        m["spend_cap_usd"] = 1000.0
        m["concurrency"] = 8
    cfg.update(over)
    return cfg


@pytest.fixture
def cfg():
    return make_cfg()


def copy_fixture(dst: Path) -> Path:
    shutil.copytree(FIXTURE, dst)
    return dst


def write_scripts(scen: Path, cfg: dict, allow_unapproved: bool = False) -> list[dict]:
    from src.common import write_jsonl
    scripts, _ = build_all(scen, cfg, None, allow_unapproved)
    write_jsonl(scen / "scripts.jsonl", scripts)
    return scripts


@pytest.fixture
def scen(tmp_path, cfg) -> Path:
    d = copy_fixture(tmp_path / "scenarios")
    write_scripts(d, cfg)
    return d


def add_vignette(scen: Path, vid: str, **fields) -> None:
    """Add a vignette that reuses V00's assets under a new id, with the given vignette fields changed."""
    vs = read_json(scen / "vignettes.json")
    base = dict(vs["vignettes"][0])
    base.update(id=vid, **fields)
    vs["vignettes"].append(base)
    write_json(scen / "vignettes.json", vs)
    a = read_json(scen / "assets.json")
    a["assets"] += [dict(x, vignette=vid) for x in a["assets"] if x["vignette"] == "V00"]
    write_json(scen / "assets.json", a)


def load_scripts(scen: Path) -> dict[str, dict]:
    return {s["script_id"]: s for s in read_jsonl(scen / "scripts.jsonl")}
