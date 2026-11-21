"""SQLite schema for the synthetic governed store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS firms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    custodian TEXT NOT NULL,
    crm_system TEXT NOT NULL,
    statement_format TEXT NOT NULL,
    household_count INTEGER NOT NULL,
    source_label TEXT NOT NULL,
    version TEXT NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS households (
    id TEXT PRIMARY KEY,
    firm_id TEXT NOT NULL REFERENCES firms(id),
    holder_name TEXT NOT NULL,
    holder_name_alt TEXT,
    account_type TEXT NOT NULL,
    dob_redacted TEXT NOT NULL DEFAULT '[REDACTED]',
    beneficiary TEXT,
    beneficiary_conflict TEXT,
    source_label TEXT NOT NULL,
    version TEXT NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS holdings (
    id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL REFERENCES households(id),
    ticker TEXT NOT NULL,
    shares REAL NOT NULL,
    cost_basis REAL,
    cost_basis_missing INTEGER NOT NULL DEFAULT 0,
    purchase_date TEXT,
    source_file TEXT NOT NULL,
    source_line INTEGER,
    source_sheet TEXT,
    source_label TEXT NOT NULL,
    version TEXT NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS source_files (
    id TEXT PRIMARY KEY,
    firm_id TEXT NOT NULL REFERENCES firms(id),
    household_id TEXT,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    parseable INTEGER NOT NULL DEFAULT 1,
    injected INTEGER NOT NULL DEFAULT 0,
    unrecognized_format INTEGER NOT NULL DEFAULT 0,
    source_label TEXT NOT NULL,
    version TEXT NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    household_id TEXT,
    status TEXT NOT NULL,
    guardrail_verdict TEXT,
    reason_code TEXT,
    created_at TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS review_queue (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    household_id TEXT NOT NULL,
    gate TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    decision TEXT,
    decision_reason TEXT,
    actor TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS import_log (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    household_id TEXT NOT NULL,
    event TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    guardrail_verdict TEXT NOT NULL,
    reason TEXT NOT NULL,
    ungrounded INTEGER NOT NULL DEFAULT 0,
    fabricated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS controls (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reason_code TEXT NOT NULL,
    detail TEXT NOT NULL,
    household_id TEXT,
    created_at TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
