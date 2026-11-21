from advisor_onboarding.agent.loop import run_agent


def test_clean_path_with_gates(store):
    result = run_agent(
        store,
        household_id="HH-0001",
        auto_approve_gates=True,
    )
    assert result["final_status"] == "import_stub_logged"
    assert result["import_log"]["event"] == "import_stub_logged"
    assert (result.get("guardrail") or {}).get("decision") == "ALLOW"


def test_injection_blocked(store):
    result = run_agent(
        store,
        household_id="HH-0001",
        scenario="injection:SRC-INJ-01",
        source_id="SRC-INJ-01",
    )
    assert result["final_status"] == "blocked"
    assert (result.get("guardrail") or {}).get("reason_code") == "injection_blocked"


def test_abstain_unmatched(store):
    result = run_agent(store, household_id="HH-0009")
    assert result["final_status"] == "held"
    assert result.get("abstained")


def test_pause_stale(store):
    result = run_agent(store, household_id="HH-0001", scenario="force_stale")
    assert result["final_status"] == "paused"
    assert result.get("paused")
