"""Deterministic input/output scanner — 6 injection rules (SkillGate-style).

These six patterns are the wealth-domain set called out in the brief and mirror
instruction-override / system-impersonation patterns already proven blocked by a
deterministic scanner. Do not invent new patterns and claim they were blocked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from advisor_onboarding.config import INJECTION_RULE_COUNT

_FLAGS = re.IGNORECASE

# Exactly 6 rules — reported in README as INJECTION_RULE_COUNT.
INJECTION_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "INJ-001",
        re.compile(r"\bimport\s+all\s+holdings\s+without\s+review\b", _FLAGS),
    ),
    (
        "INJ-002",
        re.compile(r"\bignore\s+the\s+missing\s+cost\s+basis\b", _FLAGS),
    ),
    (
        "INJ-003",
        re.compile(r"\bmark\s+this\s+household\s+as\s+verified\b", _FLAGS),
    ),
    (
        "INJ-004",
        re.compile(r"\badd\s+\d+\s+shares\s+of\s+[A-Z]{1,5}\b", _FLAGS),
    ),
    (
        "INJ-005",
        re.compile(
            r"\b(ignore|disregard)\b[^.\n]{0,40}\b(previous|prior|above)\b[^.\n]{0,40}\b"
            r"(instructions?|prompts?|rules)\b",
            _FLAGS,
        ),
    ),
    (
        "INJ-006",
        re.compile(
            r"\b(system\s+override|skip\s+gate\s*[12]|bypass\s+(the\s+)?(gate|review))\b",
            _FLAGS,
        ),
    ),
]

assert len(INJECTION_RULES) == INJECTION_RULE_COUNT


@dataclass(frozen=True)
class ScanResult:
    blocked: bool
    rules_fired: list[str] = field(default_factory=list)
    detail: str = ""
    risk_score: int = 0


def scan_text(text: str) -> ScanResult:
    """Pattern-match + allowlist screen before any LLM sees the content."""
    fired: list[str] = []
    for rule_id, pattern in INJECTION_RULES:
        if pattern.search(text or ""):
            fired.append(rule_id)
    if fired:
        return ScanResult(
            blocked=True,
            rules_fired=fired,
            detail=f"Injection pattern(s) blocked: {', '.join(fired)}",
            risk_score=min(100, 40 + 15 * len(fired)),
        )
    return ScanResult(blocked=False, detail="ok", risk_score=0)


def rule_count() -> int:
    return len(INJECTION_RULES)
