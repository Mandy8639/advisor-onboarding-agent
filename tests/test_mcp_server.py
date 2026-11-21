"""MCP module loads and allowlist is enforced (no live stdio server in unit tests)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from advisor_onboarding.config import ALLOWED_TOOLS
from advisor_onboarding.tools.allowlist import assert_allowed


def test_allowed_tools_are_exactly_three():
    assert ALLOWED_TOOLS == {
        "parse_statement",
        "validate_household",
        "draft_migration_plan",
    }
    for name in ALLOWED_TOOLS:
        assert_allowed(name)


def test_mcp_server_module_imports():
    path = Path(__file__).resolve().parents[1] / "mcp_server.py"
    spec = importlib.util.spec_from_file_location("advisor_mcp_server", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "parse_statement_tool")
    assert hasattr(mod, "validate_household_tool")
    assert hasattr(mod, "draft_migration_plan_tool")
    assert hasattr(mod, "review_queue_resource")
