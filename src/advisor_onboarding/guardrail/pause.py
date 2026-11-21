"""Five pause conditions from the brief (§6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from advisor_onboarding.config import (
    AUTO_ALLOW_RATE_THRESHOLD,
    AUTO_ALLOW_WINDOW,
    BLOCK_STREAK_PAUSE,
    FABRICATION_STREAK_PAUSE,
    UNGROUNDED_RATE_THRESHOLD,
    UNGROUNDED_WINDOW,
)
from advisor_onboarding.corpus.governed import GovernedStore


@dataclass
class PauseResult:
    should_pause: bool
    reason_code: str | None
    detail: str


class PauseChecker:
    def __init__(self, store: GovernedStore) -> None:
        self.store = store

    def check(
        self,
        *,
        recent_answers: list[dict[str, Any]] | None = None,
        force_stale: bool = False,
    ) -> PauseResult:
        if force_stale:
            return PauseResult(True, "corpus_stale", "Corpus version/hash forced stale for eval.")

        fresh = self.store.freshness_check()
        if not fresh.ok:
            return PauseResult(True, "corpus_stale", fresh.reason)

        if recent_answers is not None:
            answers = recent_answers
        else:
            answers = self.store.list_recent_answers(100)

        # 2 fabrication BLOCKs in a row
        fab = 0
        for a in answers[:FABRICATION_STREAK_PAUSE]:
            reason = str(a.get("reason", ""))
            verdict = str(a.get("guardrail_verdict", ""))
            if verdict == "BLOCK" and (
                "fabricat" in reason.lower() or int(a.get("fabricated") or 0) == 1
            ):
                fab += 1
            else:
                break
        if fab >= FABRICATION_STREAK_PAUSE:
            return PauseResult(
                True,
                "fabrication_streak",
                f"{fab} consecutive fabrication BLOCKs",
            )

        # 3 consecutive BLOCKs
        blocks = 0
        for a in answers[:BLOCK_STREAK_PAUSE]:
            if a.get("guardrail_verdict") == "BLOCK":
                blocks += 1
            else:
                break
        if blocks >= BLOCK_STREAK_PAUSE:
            return PauseResult(True, "block_streak", f"{blocks} consecutive BLOCKs")

        # Ungrounded-claim rate in last 10 plans > 5%
        window = answers[:UNGROUNDED_WINDOW]
        if len(window) >= UNGROUNDED_WINDOW:
            ung = sum(1 for a in window if int(a.get("ungrounded") or 0) == 1)
            rate = ung / len(window)
            if rate > UNGROUNDED_RATE_THRESHOLD:
                return PauseResult(
                    True,
                    "ungrounded_rate_breach",
                    f"Ungrounded-claim rate {rate:.2%} > 5% over last {len(window)} plans",
                )

        # Auto-ALLOW rate > 80% over last 20 households
        allow_window = answers[:AUTO_ALLOW_WINDOW]
        if len(allow_window) >= AUTO_ALLOW_WINDOW:
            allows = sum(1 for a in allow_window if a.get("guardrail_verdict") == "ALLOW")
            auto_rate = allows / len(allow_window)
            if auto_rate > AUTO_ALLOW_RATE_THRESHOLD:
                return PauseResult(
                    True,
                    "auto_allow_rate_breach",
                    f"Auto-ALLOW rate {auto_rate:.2%} > 80% over last {len(allow_window)}",
                )

        return PauseResult(False, None, "ok")

    def apply_if_needed(self, result: PauseResult, household_id: str | None = None) -> None:
        if not result.should_pause:
            return
        self.store.set_paused(True, reason=result.reason_code or "pause")
        self.store.append_exception(
            reason_code=result.reason_code or "pause",
            detail=result.detail,
            household_id=household_id,
        )
