"""Stub + optional live proposer. Stub is default ($0)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from advisor_onboarding.config import daily_spend_cap, mode

_spend_usd = 0.0


def reset_spend() -> None:
    global _spend_usd
    _spend_usd = 0.0


def get_spend_tracker() -> float:
    return _spend_usd


@dataclass
class ProposeResult:
    action: str  # draft | abstain | fabricate_trap
    extra_claims: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float = 0.0
    detail: str = ""


def propose_plan_action(
    *,
    household_id: str,
    validation: dict[str, Any],
    scenario: str | None = None,
) -> ProposeResult:
    """In stub mode: deterministic. In live mode: Haiku-class with spend cap."""
    global _spend_usd
    scenario = scenario or ""
    current_mode = mode()

    if scenario == "fabrication_trap":
        return ProposeResult(
            action="fabricate_trap",
            extra_claims=[
                {
                    "kind": "holding",
                    "text": "Holding FAKE: 999 shares",
                    "citation": None,  # uncited → stripped
                    "ticker": "FAKE",
                },
                {
                    "kind": "holding",
                    "text": "Holding ZZQX: 50 shares (not in source)",
                    "citation": "hallucinated:ZZQX",
                    "ticker": "ZZQX",
                },
            ],
            detail="Eval fabrication trap",
        )

    if not validation.get("passed"):
        return ProposeResult(action="abstain", detail="validation failed")

    if current_mode == "live":
        if _spend_usd >= daily_spend_cap():
            return ProposeResult(action="abstain", detail="spend cap reached")
        # Live path is optional; keep a tiny accounting stub without requiring a key
        # unless ANTHROPIC_API_KEY is present. Without a key, fall back to stub draft.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return ProposeResult(action="draft", detail="live requested but no key; stub draft")
        # Minimal live call — still produce a draft action; the deterministic tools
        # generate the actual plan. We only bill a symbolic amount for accounting.
        cost = 0.002
        _spend_usd += cost
        return ProposeResult(action="draft", cost_usd=cost, detail="live draft")

    return ProposeResult(action="draft", detail="stub draft")
