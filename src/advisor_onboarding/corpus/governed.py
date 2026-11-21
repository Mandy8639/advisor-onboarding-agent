"""Governed read/append API over the synthetic SQLite store."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from advisor_onboarding.config import CORPUS_VERSION
from advisor_onboarding.corpus.schema import connect


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Freshness:
    ok: bool
    reason: str
    expected_hash: str | None = None
    actual_hash: str | None = None


class GovernedStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _conn(self) -> sqlite3.Connection:
        return connect(self.path)

    def meta(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return None if row is None else row["value"]

    def freshness_check(self) -> Freshness:
        version = self.meta("corpus_version")
        pinned = self.meta("corpus_hash")
        if version != CORPUS_VERSION:
            return Freshness(False, f"corpus version {version!r} != pinned {CORPUS_VERSION!r}")
        from advisor_onboarding.corpus.seed import corpus_hash

        with self._conn() as conn:
            actual = corpus_hash(conn)
        if pinned and actual != pinned:
            return Freshness(False, "corpus hash mismatch", pinned, actual)
        return Freshness(True, "ok", pinned, actual)

    def list_households(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM households ORDER BY id LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_household(self, household_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM households WHERE id=?", (household_id,)).fetchone()
            return None if row is None else dict(row)

    def holdings_for(self, household_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM holdings WHERE household_id=? ORDER BY id",
                (household_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def source_files(
        self, *, household_id: str | None = None, source_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if source_id:
                rows = conn.execute(
                    "SELECT * FROM source_files WHERE id=?", (source_id,)
                ).fetchall()
            elif household_id:
                rows = conn.execute(
                    "SELECT * FROM source_files WHERE household_id=? ORDER BY id",
                    (household_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM source_files ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def find_duplicate_households(self, holder_name: str) -> list[dict[str, Any]]:
        """Return households that share this holder name or a seeded alt spelling."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM households WHERE holder_name=? OR holder_name_alt=?",
                (holder_name, holder_name),
            ).fetchall()
            matches = {r["id"]: dict(r) for r in rows}
            # If this name is itself an alt on another row, include that row's primary too.
            for r in rows:
                primary = r["holder_name"]
                alt = r["holder_name_alt"]
                for name in {primary, alt} - {None, ""}:
                    for other in conn.execute(
                        "SELECT * FROM households WHERE holder_name=? OR holder_name_alt=?",
                        (name, name),
                    ).fetchall():
                        matches[other["id"]] = dict(other)
            return list(matches.values())

    def append_run(self, run: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO runs(id, household_id, status, guardrail_verdict, reason_code, "
                "created_at, detail_json) VALUES (?,?,?,?,?,?,?)",
                (
                    run["id"],
                    run.get("household_id"),
                    run["status"],
                    run.get("guardrail_verdict"),
                    run.get("reason_code"),
                    run.get("created_at", _now()),
                    json.dumps(run.get("detail") or {}),
                ),
            )
            conn.commit()

    def append_answer(
        self,
        *,
        case_id: str,
        guardrail_verdict: str,
        reason: str,
        ungrounded: int = 0,
        fabricated: int = 0,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO answers(case_id, guardrail_verdict, reason, ungrounded, "
                "fabricated, created_at) VALUES (?,?,?,?,?,?)",
                (case_id, guardrail_verdict, reason, ungrounded, fabricated, _now()),
            )
            conn.commit()

    def list_recent_answers(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM answers ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def is_paused(self) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM controls WHERE key='paused'").fetchone()
            return bool(row and row["value"] == "1")

    def set_paused(self, paused: bool, reason: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO controls(key, value) VALUES('paused', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("1" if paused else "0",),
            )
            conn.execute(
                "INSERT INTO controls(key, value) VALUES('pause_reason', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (reason,),
            )
            conn.commit()

    def get_control(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM controls WHERE key=?", (key,)).fetchone()
            return None if row is None else row["value"]

    def append_exception(
        self, *, reason_code: str, detail: str, household_id: str | None = None
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO exceptions(reason_code, detail, household_id, created_at) "
                "VALUES (?,?,?,?)",
                (reason_code, detail, household_id, _now()),
            )
            conn.commit()

    def enqueue_review(self, item: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO review_queue(id, run_id, household_id, gate, status, "
                "payload_json, created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    item["id"],
                    item["run_id"],
                    item["household_id"],
                    item["gate"],
                    item.get("status", "pending"),
                    json.dumps(item.get("payload") or {}),
                    item.get("created_at", _now()),
                ),
            )
            conn.commit()

    def list_review_queue(self, status: str | None = "pending") -> list[dict[str, Any]]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM review_queue WHERE status=? ORDER BY created_at",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM review_queue ORDER BY created_at").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["payload"] = json.loads(d.pop("payload_json"))
                except json.JSONDecodeError:
                    d["payload"] = {}
                out.append(d)
            return out

    def decide_review(
        self,
        review_id: str,
        *,
        decision: str,
        reason: str,
        actor: str,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM review_queue WHERE id=?", (review_id,)).fetchone()
            if row is None:
                raise KeyError(review_id)
            conn.execute(
                "UPDATE review_queue SET status=?, decision=?, decision_reason=?, "
                "actor=?, decided_at=? WHERE id=?",
                (decision, decision, reason, actor, _now(), review_id),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM review_queue WHERE id=?", (review_id,)).fetchone()
            d = dict(updated)
            d["payload"] = json.loads(d.pop("payload_json"))
            return d

    def log_import_stub(self, *, run_id: str, household_id: str, detail: dict[str, Any]) -> None:
        """Log-only import stub — never writes holdings into an external system."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO import_log(id, run_id, household_id, event, detail_json, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    f"IMP-{run_id}",
                    run_id,
                    household_id,
                    "import_stub_logged",
                    json.dumps(detail),
                    _now(),
                ),
            )
            conn.commit()

    def list_firms(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM firms ORDER BY id")]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return None
            d = dict(row)
            try:
                d["detail"] = json.loads(d.pop("detail_json"))
            except json.JSONDecodeError:
                d["detail"] = {}
            return d
