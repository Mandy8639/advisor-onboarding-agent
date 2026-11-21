#!/usr/bin/env python3
"""MCP server exposing the 3 allowlisted tools + read-only review_queue.

Enforces the same guardrail and allowlist — not a bypass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from advisor_onboarding.config import ALLOWED_TOOLS, db_path  # noqa: E402
from advisor_onboarding.corpus.governed import GovernedStore  # noqa: E402
from advisor_onboarding.corpus.seed import refresh_updated_at, seed_corpus  # noqa: E402
from advisor_onboarding.guardrail.policy import GuardrailInput, evaluate  # noqa: E402
from advisor_onboarding.guardrail.scanner import scan_text  # noqa: E402
from advisor_onboarding.tools.allowlist import ToolNotAllowedError, assert_allowed  # noqa: E402
from advisor_onboarding.tools.draft_migration_plan import draft_migration_plan  # noqa: E402
from advisor_onboarding.tools.parse_statement import parse_statement  # noqa: E402
from advisor_onboarding.tools.validate_household import validate_household  # noqa: E402

mcp = MCPServer(
    "advisor-onboarding-agent",
    instructions=(
        "Governed tools for advisor onboarding on synthetic data only. "
        f"Allowlisted tools: {sorted(ALLOWED_TOOLS)}. "
        "Never imports data, moves money, or contacts clients. "
        "review_queue is read-only."
    ),
)


def _store() -> GovernedStore:
    path = db_path()
    if not path.exists():
        seed_corpus(path, force=True)
        refresh_updated_at(path)
    return GovernedStore(path)


@mcp.tool()
def parse_statement_tool(source_id: str) -> str:
    """Parse a synthetic source file into structured candidate records."""
    assert_allowed("parse_statement")
    store = _store()
    files = store.source_files(source_id=source_id)
    if not files:
        return json.dumps({"error": "not_found", "source_id": source_id})
    src = files[0]
    # Guardrail on input before parse
    scan = scan_text(src["content"])
    if scan.blocked:
        return json.dumps(
            {
                "ok": False,
                "blocked": True,
                "reason_code": "injection_blocked",
                "rules_fired": scan.rules_fired,
                "detail": scan.detail,
            }
        )
    result = parse_statement(
        content=src["content"],
        source_id=src["id"],
        source_path=src["path"],
        kind=src["kind"],
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def validate_household_tool(household_id: str) -> str:
    """Deterministically validate a household mapping."""
    assert_allowed("validate_household")
    store = _store()
    result = validate_household(store, household_id=household_id)
    g = evaluate(
        GuardrailInput(
            household_id=household_id,
            stage="validate",
            validation=result,
        )
    )
    payload = {"validation": result, "guardrail": {**g.__dict__, "decision": g.decision.value}}
    return json.dumps(payload, indent=2, default=str)


@mcp.tool()
def draft_migration_plan_tool(household_id: str) -> str:
    """Draft a cited-facts-only migration plan (abstains if validation fails)."""
    assert_allowed("draft_migration_plan")
    store = _store()
    validation = validate_household(store, household_id=household_id)
    holdings = store.holdings_for(household_id)
    plan = draft_migration_plan(
        household_id=household_id,
        validation=validation,
        holdings=holdings,
    )
    g = evaluate(
        GuardrailInput(
            household_id=household_id,
            stage="draft",
            validation=validation,
            plan=plan,
        )
    )
    return json.dumps(
        {
            "plan": plan,
            "guardrail": {
                "decision": g.decision.value,
                "reason_code": g.reason_code,
                "detail": g.detail,
            },
        },
        indent=2,
        default=str,
    )


@mcp.resource("review_queue://pending")
def review_queue_resource() -> str:
    """Read-only review queue (Gate 1 / Gate 2). Not a write bypass."""
    items = _store().list_review_queue(status="pending")
    return json.dumps(items, indent=2, default=str)


# Explicitly reject any attempt to register non-allowlisted tools at import time.
def _assert_mcp_allowlist() -> None:
    # The three tools above map to the allowlist; resource is read-only.
    for name in ("parse_statement", "validate_household", "draft_migration_plan"):
        try:
            assert_allowed(name)
        except ToolNotAllowedError:
            raise


_assert_mcp_allowlist()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
