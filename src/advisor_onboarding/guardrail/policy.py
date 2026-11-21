"""Deterministic guardrail: ALLOW / HOLD / BLOCK — no LLM calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from advisor_onboarding.guardrail.scanner import scan_text


class Decision(StrEnum):
    ALLOW = "ALLOW"
    HOLD = "HOLD"
    BLOCK = "BLOCK"


@dataclass
class GuardrailInput:
    household_id: str
    stage: str  # parse | validate | draft | import
    text_blob: str = ""
    validation: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    parse_result: dict[str, Any] | None = None
    gates_passed: dict[str, bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardrailDecision:
    decision: Decision
    reason_code: str
    detail: str
    risk_score: int = 0
    rules_fired: list[str] = field(default_factory=list)


def evaluate(inp: GuardrailInput) -> GuardrailDecision:
    """Evaluate input/output against mandate. Deterministic."""
    # BLOCK: injection in any text blob
    scan = scan_text(inp.text_blob)
    if scan.blocked:
        return GuardrailDecision(
            Decision.BLOCK,
            "injection_blocked",
            scan.detail,
            risk_score=scan.risk_score,
            rules_fired=scan.rules_fired,
        )

    parse = inp.parse_result or {}
    if parse.get("blocked"):
        return GuardrailDecision(
            Decision.BLOCK,
            "injection_blocked",
            parse.get("detail") or "Injection blocked at parse.",
            risk_score=90,
            rules_fired=list(parse.get("rules_fired") or []),
        )

    if parse.get("reason_code") == "unrecognized_format":
        return GuardrailDecision(
            Decision.HOLD,
            "unrecognized_format",
            "Unrecognized custodian format — HOLD for review.",
            risk_score=40,
        )

    if parse.get("reason_code") == "unparseable":
        return GuardrailDecision(
            Decision.HOLD,
            "unparseable",
            parse.get("detail") or "Unparseable source file.",
            risk_score=35,
        )

    if parse and parse.get("confidence", 1.0) < 0.5:
        return GuardrailDecision(
            Decision.HOLD,
            "low_parse_confidence",
            f"Parse confidence {parse.get('confidence')} below threshold.",
            risk_score=30,
        )

    validation = inp.validation or {}
    if validation and not validation.get("passed"):
        reason = validation.get("abstain_reason") or "validation_failed"
        return GuardrailDecision(
            Decision.HOLD,
            reason,
            "Validation failed — abstain from drafting; needs human review.",
            risk_score=50,
        )

    plan = inp.plan or {}
    if plan.get("stripped_fabricated"):
        return GuardrailDecision(
            Decision.BLOCK,
            "fabrication_blocked",
            f"Fabricated holdings stripped/blocked: {plan['stripped_fabricated']}",
            risk_score=95,
        )

    if plan.get("ok") is False and plan.get("abstained"):
        return GuardrailDecision(
            Decision.HOLD,
            plan.get("reason_code") or "abstained",
            "Agent abstained from drafting.",
            risk_score=45,
        )

    # HOLD: unverifiable citations remaining after post-check intent
    if plan.get("plan") and plan["plan"].get("stripped_uncited"):
        return GuardrailDecision(
            Decision.HOLD,
            "uncited_claims",
            "Plan contained uncited claims that were stripped — HOLD.",
            risk_score=55,
        )

    coverage = (plan.get("plan") or {}).get("citation_coverage")
    if coverage is not None and coverage < 1.0:
        return GuardrailDecision(
            Decision.HOLD,
            "citation_incomplete",
            f"Citation coverage {coverage:.0%} < 100%.",
            risk_score=50,
        )

    # ALLOW only when validated, cited, and (for import stage) both gates passed.
    if inp.stage == "import":
        if not (inp.gates_passed.get("gate1") and inp.gates_passed.get("gate2")):
            return GuardrailDecision(
                Decision.HOLD,
                "gates_incomplete",
                "Both human gates must pass before import stub.",
                risk_score=40,
            )

    if validation.get("passed") and (plan.get("ok") or inp.stage in {"validate", "parse"}):
        if inp.stage == "validate" and validation.get("passed"):
            return GuardrailDecision(
                Decision.ALLOW,
                "validation_passed",
                "Validated mapping; awaiting Gate 1 before draft.",
                risk_score=5,
            )
        if inp.stage == "draft" and plan.get("ok"):
            return GuardrailDecision(
                Decision.ALLOW,
                "plan_cited",
                "Validated mapping, all facts cited.",
                risk_score=5,
            )
        if inp.stage == "import":
            return GuardrailDecision(
                Decision.ALLOW,
                "gates_passed",
                "Validated, cited, both gates passed — log-only import stub allowed.",
                risk_score=0,
            )

    if inp.stage == "parse" and parse.get("ok"):
        return GuardrailDecision(
            Decision.ALLOW,
            "parsed_ok",
            "Source parsed without injection.",
            risk_score=5,
        )

    return GuardrailDecision(
        Decision.HOLD,
        "needs_review",
        "Default HOLD — incomplete pipeline state.",
        risk_score=20,
    )
