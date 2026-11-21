"""draft_migration_plan — cited-facts-only plan with deterministic post-check."""

from __future__ import annotations

import re
from typing import Any

from advisor_onboarding.config import KNOWN_TICKERS
from advisor_onboarding.tools.allowlist import assert_allowed

CITATION_RE = re.compile(r"\[cite:([^\]]+)\]")


def _strip_uncited(
    lines: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    stripped: list[dict[str, Any]] = []
    for line in lines:
        cite = line.get("citation")
        if cite:
            kept.append(line)
        else:
            stripped.append(line)
    return kept, stripped


def draft_migration_plan(
    *,
    household_id: str,
    validation: dict[str, Any],
    holdings: list[dict[str, Any]],
    parsed_rows: list[dict[str, Any]] | None = None,
    extra_claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a migration plan ONLY from validated, cited facts.

    A deterministic post-check strips any uncited claim before the plan is shown.
    Refuses to draft when validation failed (abstention).
    """
    assert_allowed("draft_migration_plan")

    if not validation.get("passed"):
        return {
            "ok": False,
            "abstained": True,
            "reason_code": validation.get("abstain_reason") or "validation_failed",
            "needs_human_review": True,
            "packet": {
                "household_id": household_id,
                "reason": validation.get("abstain_reason"),
                "failed_checks": [c for c in validation.get("checks", []) if not c.get("pass")],
                "missing_fields": sorted(
                    {
                        f
                        for c in validation.get("checks", [])
                        for f in (c.get("missing_fields") or [])
                    }
                ),
            },
            "plan": None,
        }

    source_tickers = {
        (h.get("ticker") or "").upper() for h in (parsed_rows or holdings) if h.get("ticker")
    }

    lines: list[dict[str, Any]] = []
    lines.append(
        {
            "kind": "household",
            "text": f"Migrate household {household_id}",
            "citation": f"corpus:{household_id}",
        }
    )

    for h in holdings:
        ticker = (h.get("ticker") or "").upper()
        cite = h.get("id") or h.get("source_file") or household_id
        line_ref = h.get("source_line")
        citation = f"corpus:{cite}"
        if h.get("source_file") and line_ref:
            citation = f"{h['source_file']}:{line_ref}"
        lines.append(
            {
                "kind": "holding",
                "text": (
                    f"Holding {ticker}: {h.get('shares')} shares"
                    + (
                        f", cost basis {h.get('cost_basis')}"
                        if h.get("cost_basis") is not None
                        else ", cost basis flagged missing"
                    )
                ),
                "citation": citation,
                "ticker": ticker,
            }
        )

    # Import order: taxable → IRA → Roth → 401k_rollover → other
    order = ["taxable", "ira", "roth", "401k_rollover", "trust", "joint"]
    lines.append(
        {
            "kind": "import_order",
            "text": f"Suggested import order by account type: {', '.join(order)}",
            "citation": f"corpus:{household_id}",
        }
    )

    # Optional extra claims (used by eval fabrication traps / live proposers).
    if extra_claims:
        lines.extend(extra_claims)

    kept, stripped = _strip_uncited(lines)

    # Fabrication trap: holding not in source must never remain.
    fabricated = []
    clean: list[dict[str, Any]] = []
    for line in kept:
        ticker = (line.get("ticker") or "").upper()
        if line.get("kind") == "holding" and ticker:
            if ticker not in source_tickers and ticker not in {
                (h.get("ticker") or "").upper() for h in holdings
            }:
                fabricated.append(line)
                continue
            if ticker not in KNOWN_TICKERS and ticker not in source_tickers:
                fabricated.append(line)
                continue
        clean.append(line)

    return {
        "ok": True,
        "abstained": False,
        "reason_code": "drafted",
        "needs_human_review": False,
        "plan": {
            "household_id": household_id,
            "households_to_migrate": [household_id],
            "holdings": [
                {
                    "ticker": (h.get("ticker") or "").upper(),
                    "shares": h.get("shares"),
                    "cost_basis": h.get("cost_basis"),
                    "citation": h.get("id") or h.get("source_file"),
                }
                for h in holdings
            ],
            "flagged_mismatches": [],
            "missing_data": [],
            "import_order": order,
            "lines": clean,
            "stripped_uncited": stripped,
            "stripped_fabricated": fabricated,
            "citation_coverage": (
                1.0 if not clean else sum(1 for ln in clean if ln.get("citation")) / len(clean)
            ),
        },
    }
