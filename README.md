# advisor-onboarding-agent

**A bounded agent that migrates an advisor firm’s book into a unified household record — with a deterministic guardrail and two human gates.**

> **Demo only.** All data is synthetic. **Not affiliated with, endorsed by, or built for Savvy Wealth.**  
> The agent never moves money, changes a holding, contacts a client, or performs a real import (import is log-only).

## Measured numbers (stub mode)

From committed report [`evals/reports/latest-stub.json`](evals/reports/latest-stub.json) (mode=`stub`, frozen 48-case eval, cost **$0.00**):

<!-- numbers:start -->
| Metric | Value |
| --- | --- |
| Cases passed | 48/48 |
| Migration accuracy | 100.00% |
| Abstention rate (unanswerable) | 100.00% |
| Injection block rate | 6/6 |
| Citation coverage | 100.00% |
| Pause detection | 100.00% |
| Fabrication-trap rate | 100.00% |
| LLM cost (USD) | $0.00 |
<!-- numbers:end -->

These numbers are copied from the committed stub report after `python -m evals.run_evals --mode stub` — not typed from memory. Live-mode numbers are only claimed if a live report is also committed.

Guardrail: **6** deterministic injection rules (`INJ-001`…`INJ-006`).

## What it does

- Ingests messy synthetic source files (CSV statements, CRM exports, custodian blobs).
- Maps holdings into a household record and validates them with **deterministic** checks.
- Drafts a migration plan only from **cited** facts; uncited claims are stripped.
- Stops for **Gate 1** (validation review) and **Gate 2** (plan review) before a log-only import stub.

## What it deliberately does NOT do

- Import, migrate, or write to any real custodian / CRM / portfolio system.
- Move money, rebalance, or change a holding.
- Contact a client or send email.
- Call tools outside the allowlist: `parse_statement`, `validate_household`, `draft_migration_plan`.
- Claim affiliation with Savvy Wealth or that this demo was used by Savvy.

## Architecture

```
source file
   │
   ▼
parse_statement ──► guardrail (injection screen) ──► validate_household
                                                         │
                                                    Gate 1 (human)
                                                         │
                                              draft_migration_plan
                                                         │
                                                    Gate 2 (human)
                                                         │
                                              import stub (log only)
```

Pause conditions (agent stops drafting): stale corpus hash/version; ungrounded-claim rate &gt;5% over last 10 plans; two fabrication BLOCKs in a row; auto-ALLOW &gt;80% over last 20 households; three consecutive BLOCKs.

## How to run

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # optional; stub mode needs no API key
advisor seed --force
python -m evals.run_evals --mode stub
advisor serve                 # dashboard at http://127.0.0.1:8000
```

MCP (same allowlist + guardrail): `python mcp_server.py`

## Savvy Intelligence adaptation

Savvy’s flagship **Savvy Intelligence** (~21 agents across meetings, planning, investments, tax, communications, and client services) promises fiduciary-grade review: nothing reaches a client without the advisor’s sign-off. The same bounded pattern in this demo ports cleanly to a meeting-prep agent: take a household record + meeting transcript, draft prep (what changed, open items, agenda) and a follow-up (recap + tasks + email in the advisor’s voice) with **cited-facts-only** lines and an advisor review gate before anything is sent. Example: transcript cites “HH-0001 increased SPY by 50 shares on 2024-03-12 [cite:SRC-0001:14]”; the prep agent may list that change and must HOLD if it cannot cite a source — the same abstention / Gate pattern as onboarding, applied to client communications rather than book migration. This paragraph is the adaptation proof; the full meeting-prep agent is not built here.

## Honesty

- Corpus seed=`42`, versioned; golden set in `evals/golden_cases.json` is frozen and never edited to make the agent pass.
- Stub eval cost: **$0.00**. Prefer stub for all reported metrics.
- `.env.example` only — no secrets in the repo.
