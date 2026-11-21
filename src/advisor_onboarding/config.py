"""Runtime configuration. Stub mode is the default for all reported metrics."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_SEED = 42
CORPUS_VERSION = "1.0.0"
DEFAULT_MODE = "stub"
DAILY_SPEND_CAP_USD = 1.00

# Pause thresholds (brief §6)
UNGROUNDED_RATE_THRESHOLD = 0.05  # last 10 plans
FABRICATION_STREAK_PAUSE = 2
AUTO_ALLOW_RATE_THRESHOLD = 0.80  # last 20 households
BLOCK_STREAK_PAUSE = 3
UNGROUNDED_WINDOW = 10
AUTO_ALLOW_WINDOW = 20

# Exactly three allowlisted tools — enforced in code.
ALLOWED_TOOLS = frozenset(
    {
        "parse_statement",
        "validate_household",
        "draft_migration_plan",
    }
)

# Recognized tickers in the synthetic universe (demo only).
KNOWN_TICKERS = frozenset(
    {
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "META",
        "NVDA",
        "JPM",
        "V",
        "UNH",
        "XOM",
        "JNJ",
        "PG",
        "HD",
        "CVX",
        "MA",
        "ABBV",
        "COST",
        "PEP",
        "AVGO",
        "KO",
        "WMT",
        "MRK",
        "CSCO",
        "ADBE",
        "CRM",
        "ACWI",
        "SPY",
        "AGG",
        "BND",
        "VXUS",
        "VT",
        "VTI",
        "VEA",
        "VWO",
        "IEF",
        "TIP",
        "GLD",
        "SCHD",
        "QQQ",
        "IWM",
    }
)

ACCOUNT_TYPES = frozenset(
    {
        "taxable",
        "ira",
        "roth",
        "401k_rollover",
        "trust",
        "joint",
    }
)

RECOGNIZED_CUSTODIANS = frozenset(
    {
        "synthetic_schwab",
        "synthetic_fidelity",
        "synthetic_pershing",
        "synthetic_td",
        "synthetic_vanguard",
    }
)

INJECTION_RULE_COUNT = 6  # deterministic scanner rule count reported in README


def db_path() -> Path:
    env = os.environ.get("ADVISOR_DB_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return PROJECT_ROOT / "data" / "advisor.db"


def mode() -> str:
    return os.environ.get("ADVISOR_MODE", DEFAULT_MODE).strip().lower()


def daily_spend_cap() -> float:
    raw = os.environ.get("ADVISOR_DAILY_SPEND_CAP_USD")
    if raw is None:
        return DAILY_SPEND_CAP_USD
    return float(raw)


def database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or None
