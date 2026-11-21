"""validate_household — DETERMINISTIC validation (no LLM)."""

from __future__ import annotations

from typing import Any

from advisor_onboarding.config import ACCOUNT_TYPES, KNOWN_TICKERS
from advisor_onboarding.corpus.governed import GovernedStore
from advisor_onboarding.tools.allowlist import assert_allowed


def validate_household(
    store: GovernedStore,
    *,
    household_id: str,
    parsed_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Check candidate mapping: tickers, cost basis, duplicates, beneficiaries, types."""
    assert_allowed("validate_household")

    hh = store.get_household(household_id)
    if hh is None:
        return {
            "household_id": household_id,
            "passed": False,
            "checks": [
                {
                    "name": "household_exists",
                    "pass": False,
                    "reason": f"Unknown household {household_id}",
                }
            ],
            "needs_human_review": True,
            "abstain_reason": "unknown_household",
        }

    holdings = store.holdings_for(household_id)
    if parsed_rows:
        # Prefer parsed rows when provided (migration candidate).
        candidate_holdings = [
            {
                "ticker": r.get("ticker"),
                "cost_basis": r.get("cost_basis"),
                "cost_basis_missing": r.get("cost_basis_missing", r.get("cost_basis") is None),
                "shares": r.get("shares"),
                "source_file": r.get("source_path") or r.get("source_id"),
                "source_line": r.get("source_line"),
            }
            for r in parsed_rows
            if r.get("ticker")
        ]
    else:
        candidate_holdings = holdings

    checks: list[dict[str, Any]] = []

    # Ticker recognition
    bad_tickers = [
        h for h in candidate_holdings if (h.get("ticker") or "").upper() not in KNOWN_TICKERS
    ]
    checks.append(
        {
            "name": "recognized_tickers",
            "pass": len(bad_tickers) == 0,
            "reason": (
                "All tickers recognized"
                if not bad_tickers
                else f"Unrecognized tickers: {[h.get('ticker') for h in bad_tickers]}"
            ),
        }
    )

    # Cost basis
    missing_basis = [
        h for h in candidate_holdings if h.get("cost_basis_missing") or h.get("cost_basis") is None
    ]
    checks.append(
        {
            "name": "cost_basis_present",
            "pass": len(missing_basis) == 0,
            "reason": (
                "Cost basis present for all holdings"
                if not missing_basis
                else f"Missing cost basis on {len(missing_basis)} holding(s)"
            ),
            "missing_fields": ["cost_basis"] if missing_basis else [],
        }
    )

    # Duplicate households
    dups = store.find_duplicate_households(hh["holder_name"])
    dup_ids = sorted({d["id"] for d in dups if d["id"] != household_id})
    # Also treat alt-name pairs as duplicates when alt is set.
    if hh.get("holder_name_alt"):
        alt_dups = store.find_duplicate_households(hh["holder_name_alt"])
        dup_ids = sorted(set(dup_ids) | {d["id"] for d in alt_dups if d["id"] != household_id})
    checks.append(
        {
            "name": "no_duplicate_household",
            "pass": len(dup_ids) == 0,
            "reason": (
                "No duplicate household" if not dup_ids else f"Possible duplicates: {dup_ids}"
            ),
        }
    )

    # Beneficiary completeness / conflicts
    conflict = hh.get("beneficiary_conflict")
    bene = hh.get("beneficiary")
    bene_ok = bool(bene) and not conflict
    checks.append(
        {
            "name": "beneficiary_consistent",
            "pass": bene_ok,
            "reason": (
                "Beneficiary present and non-conflicting"
                if bene_ok
                else (
                    f"Conflicting beneficiaries: {bene!r} vs {conflict!r}"
                    if conflict
                    else "Beneficiary missing"
                )
            ),
            "missing_fields": [] if bene else ["beneficiary"],
        }
    )

    # Account type consistency
    acct = (hh.get("account_type") or "").lower()
    acct_ok = acct in ACCOUNT_TYPES
    checks.append(
        {
            "name": "account_type_consistent",
            "pass": acct_ok,
            "reason": (
                f"Account type {acct!r} recognized"
                if acct_ok
                else f"Unrecognized account type {acct!r}"
            ),
        }
    )

    passed = all(c["pass"] for c in checks)
    fail_names = [c["name"] for c in checks if not c["pass"]]
    abstain_map = {
        "recognized_tickers": "unmatched_ticker",
        "cost_basis_present": "missing_cost_basis",
        "no_duplicate_household": "duplicate_household",
        "beneficiary_consistent": "conflicting_beneficiary",
        "account_type_consistent": "inconsistent_account_type",
    }
    abstain_reason = None
    if not passed:
        abstain_reason = abstain_map.get(fail_names[0], "validation_failed")

    return {
        "household_id": household_id,
        "holder_name_redacted": "[REDACTED]",
        "passed": passed,
        "checks": checks,
        "needs_human_review": not passed,
        "abstain_reason": abstain_reason,
        "holdings_count": len(candidate_holdings),
        "candidate_tickers": [h.get("ticker") for h in candidate_holdings],
    }
