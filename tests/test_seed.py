from advisor_onboarding.config import CORPUS_SEED, CORPUS_VERSION


def test_seed_counts(store):
    firms = store.list_firms()
    households = store.list_households(limit=100)
    assert len(firms) == 20
    assert len(households) == 40
    assert store.meta("corpus_seed") == str(CORPUS_SEED)
    assert store.meta("corpus_version") == CORPUS_VERSION
    assert store.freshness_check().ok


def test_injection_sources_present(store):
    inj = [s for s in store.source_files() if s["id"].startswith("SRC-INJ-")]
    assert len(inj) == 6
