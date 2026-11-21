"""FastAPI demo API + static dashboard."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from advisor_onboarding.agent.loop import run_agent
from advisor_onboarding.config import INJECTION_RULE_COUNT, PROJECT_ROOT, db_path
from advisor_onboarding.corpus.governed import GovernedStore
from advisor_onboarding.corpus.seed import refresh_updated_at, seed_corpus
from advisor_onboarding.guardrail.scanner import rule_count
from advisor_onboarding.review import queue as review_queue

STATIC_DIR = PROJECT_ROOT / "static"
REPORTS_DIR = PROJECT_ROOT / "evals" / "reports"


def get_store() -> GovernedStore:
    path = db_path()
    if not path.exists():
        seed_corpus(path, force=True)
        refresh_updated_at(path)
    return GovernedStore(path)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    path = db_path()
    seed_corpus(path, force=False)
    refresh_updated_at(path)
    yield


app = FastAPI(
    title="advisor-onboarding-agent",
    description=(
        "Bounded advisor-onboarding demo over synthetic data. "
        "Not affiliated with Savvy Wealth. Never moves money or contacts clients."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


class RunBody(BaseModel):
    household_id: str
    source_id: str | None = None
    scenario: str | None = None
    auto_approve_gates: bool = False


class ReviewBody(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|edit)$")
    reason: str
    actor: str = "advisor_ops"


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "synthetic": True,
        "affiliation": "none",
        "injection_rules": rule_count(),
        "configured_rule_count": INJECTION_RULE_COUNT,
    }


@app.get("/api/households")
def list_households() -> list[dict[str, Any]]:
    rows = get_store().list_households()
    for r in rows:
        r["holder_name"] = "[REDACTED]"
        r["holder_name_alt"] = "[REDACTED]" if r.get("holder_name_alt") else None
        r["beneficiary"] = "[REDACTED]" if r.get("beneficiary") else None
        r["beneficiary_conflict"] = "[REDACTED]" if r.get("beneficiary_conflict") else None
    return rows


@app.get("/api/households/{household_id}")
def get_household(household_id: str) -> dict[str, Any]:
    store = get_store()
    hh = store.get_household(household_id)
    if hh is None:
        raise HTTPException(404, "household not found")
    hh["holder_name"] = "[REDACTED]"
    holdings = store.holdings_for(household_id)
    sources = store.source_files(household_id=household_id)
    for s in sources:
        s.pop("content", None)
    return {"household": hh, "holdings": holdings, "sources": sources}


@app.post("/api/run")
def api_run(body: RunBody) -> dict[str, Any]:
    store = get_store()
    if store.get_household(body.household_id) is None:
        raise HTTPException(404, "household not found")
    return run_agent(
        store,
        household_id=body.household_id,
        source_id=body.source_id,
        scenario=body.scenario,
        auto_approve_gates=body.auto_approve_gates,
    )


@app.get("/api/review")
def api_review_list() -> list[dict[str, Any]]:
    return review_queue.list_pending(get_store())


@app.post("/api/review/{review_id}")
def api_review(review_id: str, body: ReviewBody) -> dict[str, Any]:
    store = get_store()
    try:
        if body.action == "approve":
            return review_queue.approve(store, review_id, reason=body.reason, actor=body.actor)
        if body.action == "edit":
            return review_queue.edit(store, review_id, reason=body.reason, actor=body.actor)
        return review_queue.reject(store, review_id, reason=body.reason, actor=body.actor)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/evals/latest")
def evals_latest(mode: str = "stub") -> dict[str, Any]:
    path = REPORTS_DIR / f"latest-{mode}.json"
    if not path.exists():
        candidates = sorted(REPORTS_DIR.glob(f"*-{mode}.json"))
        if not candidates:
            raise HTTPException(404, "no eval report committed")
        path = candidates[-1]
    return json.loads(path.read_text())


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
