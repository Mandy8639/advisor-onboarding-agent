"""Human review queue for Gate 1 and Gate 2."""

from __future__ import annotations

from typing import Any

from advisor_onboarding.corpus.governed import GovernedStore


def list_pending(store: GovernedStore) -> list[dict[str, Any]]:
    return store.list_review_queue(status="pending")


def approve(
    store: GovernedStore,
    review_id: str,
    *,
    reason: str,
    actor: str = "advisor_ops",
) -> dict[str, Any]:
    return store.decide_review(review_id, decision="approved", reason=reason, actor=actor)


def reject(
    store: GovernedStore,
    review_id: str,
    *,
    reason: str,
    actor: str = "advisor_ops",
) -> dict[str, Any]:
    return store.decide_review(review_id, decision="rejected", reason=reason, actor=actor)


def edit(
    store: GovernedStore,
    review_id: str,
    *,
    reason: str,
    actor: str = "advisor_ops",
) -> dict[str, Any]:
    """Record an edit decision — never silently applied to future plans."""
    return store.decide_review(review_id, decision="edited", reason=reason, actor=actor)
