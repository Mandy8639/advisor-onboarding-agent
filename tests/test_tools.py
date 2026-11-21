import pytest

from advisor_onboarding.tools.allowlist import ToolNotAllowedError, assert_allowed, list_allowed
from advisor_onboarding.tools.draft_migration_plan import draft_migration_plan
from advisor_onboarding.tools.parse_statement import parse_statement
from advisor_onboarding.tools.validate_household import validate_household


def test_allowlist_enforced():
    assert list_allowed() == [
        "draft_migration_plan",
        "parse_statement",
        "validate_household",
    ]
    with pytest.raises(ToolNotAllowedError):
        assert_allowed("send_email")


def test_parse_and_validate_clean(store):
    src = store.source_files(household_id="HH-0001")[0]
    parsed = parse_statement(content=src["content"], source_id=src["id"], source_path=src["path"])
    assert parsed["ok"]
    assert parsed["rows"]
    report = validate_household(store, household_id="HH-0001", parsed_rows=parsed["rows"])
    assert report["passed"]


def test_validate_missing_basis(store):
    report = validate_household(store, household_id="HH-0006")
    assert not report["passed"]
    assert report["abstain_reason"] == "missing_cost_basis"


def test_draft_abstains_when_invalid(store):
    validation = validate_household(store, household_id="HH-0006")
    plan = draft_migration_plan(
        household_id="HH-0006",
        validation=validation,
        holdings=store.holdings_for("HH-0006"),
    )
    assert plan["abstained"]
    assert plan["needs_human_review"]


def test_draft_strips_uncited(store):
    validation = validate_household(store, household_id="HH-0001")
    plan = draft_migration_plan(
        household_id="HH-0001",
        validation=validation,
        holdings=store.holdings_for("HH-0001"),
        extra_claims=[{"kind": "note", "text": "uncited claim", "citation": None}],
    )
    assert plan["ok"]
    assert plan["plan"]["stripped_uncited"]
