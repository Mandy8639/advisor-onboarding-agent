"""Ensure README metric table matches the committed stub report exactly."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
REPORT = ROOT / "evals" / "reports" / "latest-stub.json"


def main() -> None:
    if not REPORT.exists():
        print(f"Missing {REPORT}; run stub eval first.", file=sys.stderr)
        sys.exit(1)
    report = json.loads(REPORT.read_text())
    m = report["metrics"]
    text = README.read_text()

    checks = {
        "migration_accuracy": f"{m['migration_accuracy']:.2%}",
        "abstention_rate_unanswerable": f"{m['abstention_rate_unanswerable']:.2%}",
        "injection_block_rate": m["injection_block_rate"],
        "citation_coverage": f"{m['citation_coverage']:.2%}",
        "pause_detection": f"{m['pause_detection']:.2%}",
        "fabrication_trap_rate": f"{m['fabrication_trap_rate']:.2%}",
        "llm_cost": f"${m['llm_cost_usd']:.2f}",
        "cases": f"{m['cases_passed']}/{m['cases_total']}",
    }
    missing = [k for k, v in checks.items() if v not in text]
    # Also require mode=stub mention near numbers.
    if "mode=`stub`" not in text and "mode=stub" not in text and "`stub`" not in text:
        missing.append("stub_mode_mention")
    if missing:
        print("README does not contain measured values:", missing, file=sys.stderr)
        print("Expected:", checks, file=sys.stderr)
        sys.exit(1)
    # Guardrail rule count
    if not re.search(r"\b6\b.*injection|injection.*\b6\b|INJ-00", text, re.I):
        if "6 injection" not in text.lower() and "injection rules: **6**" not in text.lower():
            if "6 deterministic injection" not in text.lower():
                print("README should report injection rule count 6", file=sys.stderr)
                sys.exit(1)
    print("README numbers match stub report.")


if __name__ == "__main__":
    main()
