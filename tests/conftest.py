"""Shared fixtures — isolated temp DB per test."""

from __future__ import annotations

from pathlib import Path

import pytest

from advisor_onboarding.corpus.governed import GovernedStore
from advisor_onboarding.corpus.seed import refresh_updated_at, seed_corpus


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    seed_corpus(path, force=True)
    refresh_updated_at(path)
    return path


@pytest.fixture()
def store(db: Path) -> GovernedStore:
    return GovernedStore(db)
