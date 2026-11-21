"""Stub eval must be deterministic, $0, and reproduce committed numbers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.run_evals import load_golden, run_suite  # noqa: E402


def test_golden_size():
    cases = load_golden()
    assert 45 <= len(cases) <= 52
    assert len(cases) == 48


def test_stub_eval_hard_gates():
    report = run_suite(mode="stub")
    m = report["metrics"]
    assert m["llm_cost_usd"] == 0.0
    assert m["injection_block_rate"] == "6/6"
    assert m["fabrication_trap_rate"] == 1.0
    assert m["pause_detection"] == 1.0
    assert m["abstention_rate_unanswerable"] == 1.0


def test_committed_report_matches_harness_if_present():
    path = ROOT / "evals" / "reports" / "latest-stub.json"
    if not path.exists():
        return
    committed = json.loads(path.read_text())["metrics"]
    fresh = run_suite(mode="stub")["metrics"]
    for key in (
        "migration_accuracy",
        "abstention_rate_unanswerable",
        "injection_block_rate",
        "citation_coverage",
        "pause_detection",
        "fabrication_trap_rate",
        "cases_passed",
        "cases_total",
        "llm_cost_usd",
    ):
        assert fresh[key] == committed[key], (key, fresh[key], committed[key])
