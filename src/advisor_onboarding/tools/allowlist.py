"""Hard allowlist: the agent may call exactly three tools."""

from __future__ import annotations

from advisor_onboarding.config import ALLOWED_TOOLS


class ToolNotAllowedError(PermissionError):
    """Raised when code attempts a non-allowlisted tool."""


def assert_allowed(tool_name: str) -> None:
    if tool_name not in ALLOWED_TOOLS:
        raise ToolNotAllowedError(
            f"Tool {tool_name!r} is not allowlisted. Allowed: {sorted(ALLOWED_TOOLS)}"
        )


def list_allowed() -> list[str]:
    return sorted(ALLOWED_TOOLS)
