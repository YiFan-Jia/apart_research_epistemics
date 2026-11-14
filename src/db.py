"""Run store (build spec 6.3): one SQLite database per run.

Holds jobs with the script frozen at launch, committed replies, every request attempt, and repeat
block completion. The (job_id, reply_no) primary key makes a duplicate reply impossible; each reply
commits whole in one transaction with its attempt row. One process writes (see RunLock).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from .common import N_REPLIES

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    script_id TEXT NOT NULL,
    repeat INTEGER NOT NULL,
    stage TEXT NOT NULL,
    stage_index INTEGER NOT NULL,
    order_key TEXT NOT NULL,
    script_json TEXT NOT NULL,
    assets_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | complete | ended
    end_reason TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (model, script_id, repeat)
);
CREATE INDEX IF NOT EXISTS jobs_order ON jobs (model, stage_index, repeat, order_key);
CREATE TABLE IF NOT EXISTS replies (
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    reply_no INTEGER NOT NULL CHECK (reply_no BETWEEN 1 AND 11),
    user_text TEXT NOT NULL,
    reply_text TEXT NOT NULL,
    content_json TEXT NOT NULL,
    stop_reason TEXT,
    input_tokens INTEGER, output_tokens INTEGER,
    cache_creation_input_tokens INTEGER, cache_read_input_tokens INTEGER,
    usage_json TEXT,
    latency_s REAL,
    request_id TEXT,
    api_model TEXT,
    created_at TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    assets_hash TEXT NOT NULL,
    PRIMARY KEY (job_id, reply_no)
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    model TEXT NOT NULL,
    reply_no INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    latency_s REAL,
    outcome TEXT NOT NULL,           -- ok | retryable_error | fatal_error | empty_reply
    error_type TEXT, error_message TEXT, http_status INTEGER, request_id TEXT,
    input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
    cache_creation_input_tokens INTEGER DEFAULT 0, cache_read_input_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS attempts_model ON attempts (model);
CREATE TABLE IF NOT EXISTS blocks (
    model TEXT NOT NULL, stage TEXT NOT NULL, repeat INTEGER NOT NULL,
    n_jobs INTEGER NOT NULL, completed_at TEXT,
    PRIMARY KEY (model, stage, repeat)
);
"""


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def connect(path: Path | str) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), isolation_level=None)  # explicit transactions only
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    return db


class RunLock:
    """Exclusive OS-level lock so only one process writes a run. Released automatically if the process dies."""

    def __init__(self, path: Path):
        self.path = path
        self.f = None

    def __enter__(self):
        self.f = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt  # noqa: PLC0415
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl  # noqa: PLC0415
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.close()
            raise RuntimeError(f"another process is writing this run ({self.path})") from None
        return self

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt  # noqa: PLC0415
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self.f.close()


def get_meta(db, key, default=None):
    r = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(r[0]) if r else default


def set_meta(db, key, value):
    db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))


def replies_for(db, job_id) -> list[sqlite3.Row]:
    return db.execute("SELECT * FROM replies WHERE job_id=? ORDER BY reply_no", (job_id,)).fetchall()


def commit_reply(db, job_id: str, model: str, reply_no: int, row: dict, attempt: dict) -> None:
    """Insert the reply and its attempt in one transaction. Raises sqlite3.IntegrityError on a duplicate."""
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute(
            "INSERT INTO replies (job_id, reply_no, user_text, reply_text, content_json, stop_reason, input_tokens, "
            "output_tokens, cache_creation_input_tokens, cache_read_input_tokens, usage_json, latency_s, request_id, "
            "api_model, created_at, config_hash, assets_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, reply_no, row["user_text"], row["reply_text"], row["content_json"], row["stop_reason"],
             row["input_tokens"], row["output_tokens"], row["cache_creation_input_tokens"],
             row["cache_read_input_tokens"], row["usage_json"], row["latency_s"], row["request_id"],
             row["api_model"], now(), row["config_hash"], row["assets_hash"]))
        insert_attempt(db, attempt, in_txn=True)
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def insert_attempt(db, a: dict, in_txn: bool = False) -> None:
    cols = ["job_id", "model", "reply_no", "started_at", "latency_s", "outcome", "error_type", "error_message",
            "http_status", "request_id", "input_tokens", "output_tokens", "cache_creation_input_tokens",
            "cache_read_input_tokens", "cost_usd"]
    db.execute(f"INSERT INTO attempts ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
               [a.get(c) for c in cols])


def mark_job(db, job_id: str, status: str, end_reason: str | None = None) -> None:
    db.execute("UPDATE jobs SET status=?, end_reason=?, completed_at=? WHERE job_id=?",
               (status, end_reason, now(), job_id))


def job_is_finished(db, job_id) -> bool:
    r = db.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    return r is not None and r[0] in ("complete", "ended")


def update_blocks(db) -> list[tuple]:
    """Record completion of any repeat block whose jobs are all finished. Returns newly completed blocks."""
    newly = []
    rows = db.execute(
        "SELECT model, stage, repeat, COUNT(*) n, SUM(status IN ('complete','ended')) done "
        "FROM jobs GROUP BY model, stage, repeat").fetchall()
    for r in rows:
        db.execute("INSERT OR IGNORE INTO blocks (model, stage, repeat, n_jobs) VALUES (?,?,?,?)",
                   (r["model"], r["stage"], r["repeat"], r["n"]))
        db.execute("UPDATE blocks SET n_jobs=? WHERE model=? AND stage=? AND repeat=?",
                   (r["n"], r["model"], r["stage"], r["repeat"]))
        if r["n"] == r["done"]:
            cur = db.execute("UPDATE blocks SET completed_at=? WHERE model=? AND stage=? AND repeat=? "
                             "AND completed_at IS NULL", (now(), r["model"], r["stage"], r["repeat"]))
            if cur.rowcount:
                newly.append((r["model"], r["stage"], r["repeat"]))
    return newly


def spend_by_model(db) -> dict[str, float]:
    return {r[0]: r[1] for r in db.execute("SELECT model, COALESCE(SUM(cost_usd),0) FROM attempts GROUP BY model")}


def progress(db) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT j.model, j.stage, j.repeat, COUNT(*) jobs, SUM(j.status='complete') complete, "
        "SUM(j.status='ended') ended, (SELECT COUNT(*) FROM replies r JOIN jobs j2 ON r.job_id=j2.job_id "
        "WHERE j2.model=j.model AND j2.stage=j.stage AND j2.repeat=j.repeat) replies "
        "FROM jobs j GROUP BY j.model, j.stage, j.repeat ORDER BY j.model, j.stage_index, j.repeat").fetchall()


def n_expected_replies() -> int:
    return N_REPLIES
