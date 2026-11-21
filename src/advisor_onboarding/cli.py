"""CLI: seed, run, review, evals, serve."""

from __future__ import annotations

import json

import typer
import uvicorn
from rich import print as rprint

from advisor_onboarding.agent.loop import run_agent
from advisor_onboarding.config import db_path
from advisor_onboarding.corpus.governed import GovernedStore
from advisor_onboarding.corpus.seed import refresh_updated_at, seed_corpus
from advisor_onboarding.review import queue as review_queue

app = typer.Typer(add_completion=False, no_args_is_help=True)
review_app = typer.Typer(help="Gate 1 / Gate 2 review queue")
app.add_typer(review_app, name="review")


@app.command()
def seed(force: bool = typer.Option(False, "--force")) -> None:
    """Seed the synthetic corpus (seed=42)."""
    path = db_path()
    result = seed_corpus(path, force=force)
    refresh_updated_at(path)
    rprint(result)


@app.command("run")
def run_household(
    household_id: str,
    source_id: str | None = typer.Option(None, "--source-id"),
    auto_gates: bool = typer.Option(False, "--auto-gates"),
) -> None:
    """Run one household through parse → validate → gates → plan → import stub."""
    path = db_path()
    if not path.exists():
        seed_corpus(path, force=True)
        refresh_updated_at(path)
    store = GovernedStore(path)
    result = run_agent(
        store,
        household_id=household_id,
        source_id=source_id,
        auto_approve_gates=auto_gates,
    )
    rprint(json.dumps(result, indent=2, default=str))


@review_app.command("list")
def review_list() -> None:
    path = db_path()
    store = GovernedStore(path)
    for item in review_queue.list_pending(store):
        rprint(
            f"{item['id']}  gate={item['gate']}  hh={item['household_id']}  status={item['status']}"
        )


@review_app.command("approve")
def review_approve(
    review_id: str,
    reason: str = typer.Option(..., "--reason"),
    actor: str = typer.Option("advisor_ops", "--actor"),
) -> None:
    store = GovernedStore(db_path())
    rprint(review_queue.approve(store, review_id, reason=reason, actor=actor))


@review_app.command("reject")
def review_reject(
    review_id: str,
    reason: str = typer.Option(..., "--reason"),
    actor: str = typer.Option("advisor_ops", "--actor"),
) -> None:
    store = GovernedStore(db_path())
    rprint(review_queue.reject(store, review_id, reason=reason, actor=actor))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the dashboard API."""
    uvicorn.run("advisor_onboarding.api.app:app", host=host, port=port, reload=False)


@app.command()
def clear_pause() -> None:
    store = GovernedStore(db_path())
    store.set_paused(False, reason="")
    rprint({"paused": False})


if __name__ == "__main__":
    app()
