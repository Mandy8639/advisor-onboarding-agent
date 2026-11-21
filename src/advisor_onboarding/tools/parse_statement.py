"""parse_statement — structured parse of CSV / CRM / custodian text. Never free text."""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from advisor_onboarding.guardrail.scanner import scan_text
from advisor_onboarding.tools.allowlist import assert_allowed

HEADER_ALIASES = {
    "household_id": {"household_id", "hh_id", "household", "client_id"},
    "holder_name": {"holder_name", "name", "client_name", "contact", "holder"},
    "account_type": {"account_type", "acct_type", "type"},
    "ticker": {"ticker", "symbol", "security"},
    "shares": {"shares", "qty", "quantity", "units"},
    "cost_basis": {"cost_basis", "basis", "cost"},
    "purchase_date": {"purchase_date", "date", "acquired"},
    "beneficiary": {"beneficiary", "bene", "primary_beneficiary"},
    "notes": {"notes", "note", "comment", "comments"},
}


def _normalize_header(cell: str) -> str | None:
    key = re.sub(r"[^a-z0-9_]+", "_", cell.strip().lower()).strip("_")
    for canonical, aliases in HEADER_ALIASES.items():
        if key in aliases:
            return canonical
    return None


def _find_header_row(lines: list[list[str]]) -> tuple[int, dict[int, str]] | None:
    for idx, row in enumerate(lines[:12]):
        mapping: dict[int, str] = {}
        for col, cell in enumerate(row):
            canon = _normalize_header(cell or "")
            if canon:
                mapping[col] = canon
        if "ticker" in mapping.values() or "holder_name" in mapping.values():
            return idx, mapping
    return None


def parse_statement(
    *,
    content: str,
    source_id: str,
    source_path: str = "",
    kind: str = "csv_statement",
) -> dict[str, Any]:
    """Parse a source file into structured candidate rows with citations.

    Blocks injected instructions before any LLM would see the content.
    """
    assert_allowed("parse_statement")

    scan = scan_text(content)
    if scan.blocked:
        return {
            "ok": False,
            "blocked": True,
            "reason_code": "injection_blocked",
            "rules_fired": scan.rules_fired,
            "detail": scan.detail,
            "rows": [],
            "source_id": source_id,
            "source_path": source_path,
            "confidence": 0.0,
        }

    if kind == "unrecognized" or "|||CUSTODIAN_BLOB|||" in content:
        return {
            "ok": False,
            "blocked": False,
            "reason_code": "unrecognized_format",
            "detail": "Custodian/format not recognized; needs human review.",
            "rows": [],
            "source_id": source_id,
            "source_path": source_path,
            "confidence": 0.0,
        }

    # Strip leading junk / blank rows typical of CRM exports.
    reader = csv.reader(io.StringIO(content))
    lines = [row for row in reader]
    if not lines:
        return {
            "ok": False,
            "blocked": False,
            "reason_code": "unparseable",
            "detail": "Empty file.",
            "rows": [],
            "source_id": source_id,
            "source_path": source_path,
            "confidence": 0.0,
        }

    header = _find_header_row(lines)
    if header is None:
        return {
            "ok": False,
            "blocked": False,
            "reason_code": "unparseable",
            "detail": "No recognizable header row.",
            "rows": [],
            "source_id": source_id,
            "source_path": source_path,
            "confidence": 0.0,
        }

    header_idx, mapping = header
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(lines[header_idx + 1 :], start=header_idx + 2):
        if not any((c or "").strip() for c in raw):
            continue
        record: dict[str, Any] = {
            "source_id": source_id,
            "source_path": source_path or source_id,
            "source_line": line_no,
        }
        for col, canon in mapping.items():
            if col < len(raw):
                record[canon] = (raw[col] or "").strip()
        # Skip noise rows without a ticker or holder.
        if not record.get("ticker") and not record.get("holder_name"):
            continue
        if record.get("shares"):
            try:
                record["shares"] = float(str(record["shares"]).replace(",", ""))
            except ValueError:
                record["shares_raw"] = record["shares"]
                record["shares"] = None
        if "cost_basis" in record:
            raw_basis = record.get("cost_basis")
            if raw_basis in (None, ""):
                record["cost_basis"] = None
                record["cost_basis_missing"] = True
            else:
                try:
                    record["cost_basis"] = float(str(raw_basis).replace(",", ""))
                    record["cost_basis_missing"] = False
                except ValueError:
                    record["cost_basis"] = None
                    record["cost_basis_missing"] = True
        rows.append(record)

    confidence = 0.95 if rows else 0.2
    if kind == "crm_export":
        confidence = min(confidence, 0.85)

    return {
        "ok": bool(rows),
        "blocked": False,
        "reason_code": "parsed" if rows else "empty_rows",
        "detail": f"Parsed {len(rows)} candidate row(s).",
        "rows": rows,
        "source_id": source_id,
        "source_path": source_path,
        "confidence": confidence,
    }
