"""LangGraph-style flow: parse → validate → Gate 1 → draft → Gate 2 → log-only import."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from advisor_onboarding.agent.llm import propose_plan_action
from advisor_onboarding.corpus.governed import GovernedStore
from advisor_onboarding.guardrail.pause import PauseChecker
from advisor_onboarding.guardrail.policy import Decision, GuardrailInput, evaluate
from advisor_onboarding.guardrail.redact import redact_obj
from advisor_onboarding.tools.draft_migration_plan import draft_migration_plan
from advisor_onboarding.tools.parse_statement import parse_statement
from advisor_onboarding.tools.validate_household import validate_household


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class AgentState(TypedDict, total=False):
    run_id: str
    household_id: str
    source_id: str | None
    scenario: str | None
    auto_approve_gates: bool
    parse_result: dict[str, Any]
    validation: dict[str, Any]
    gate1: dict[str, Any]
    plan_result: dict[str, Any]
    gate2: dict[str, Any]
    guardrail: dict[str, Any]
    import_log: dict[str, Any] | None
    final_status: str
    paused: bool
    pause_reason: str | None
    cost_usd: float
    abstained: bool
    needs_human_review: bool


def build_graph(store: GovernedStore):
    def check_pause(state: AgentState) -> AgentState:
        checker = PauseChecker(store)
        force_stale = (state.get("scenario") or "") == "force_stale"
        pause = checker.check(force_stale=force_stale)
        if store.is_paused() or pause.should_pause:
            if pause.should_pause:
                checker.apply_if_needed(pause, state.get("household_id"))
            return {
                **state,
                "paused": True,
                "pause_reason": pause.reason_code or store.get_control("pause_reason"),
                "final_status": "paused",
                "guardrail": {
                    "decision": Decision.BLOCK.value,
                    "reason_code": pause.reason_code or "agent_paused",
                    "detail": pause.detail,
                },
            }
        return {**state, "paused": False}

    def parse_node(state: AgentState) -> AgentState:
        if state.get("paused"):
            return state
        household_id = state["household_id"]
        source_id = state.get("source_id")
        sources = store.source_files(household_id=household_id)
        if source_id:
            matched = [s for s in store.source_files(source_id=source_id)]
            sources = matched or sources
        # Prefer injection source when scenario requests it.
        scenario = state.get("scenario") or ""
        if scenario.startswith("injection:"):
            inj_id = scenario.split(":", 1)[1]
            matched = store.source_files(source_id=inj_id)
            if matched:
                sources = matched
        if scenario == "unrecognized_format":
            matched = [s for s in sources if s.get("unrecognized_format")]
            if not matched:
                matched = [
                    s
                    for s in store.source_files()
                    if s.get("unrecognized_format") and s.get("household_id") == household_id
                ]
            sources = matched or sources

        if not sources:
            parse_result = {
                "ok": False,
                "reason_code": "unparseable",
                "detail": "No source files",
                "rows": [],
                "confidence": 0.0,
            }
        else:
            src = sources[0]
            parse_result = parse_statement(
                content=src["content"],
                source_id=src["id"],
                source_path=src["path"],
                kind=src["kind"],
            )

        g = evaluate(
            GuardrailInput(
                household_id=household_id,
                stage="parse",
                text_blob=sources[0]["content"] if sources else "",
                parse_result=parse_result,
            )
        )
        out: AgentState = {
            **state,
            "parse_result": parse_result,
            "guardrail": {
                "decision": g.decision.value,
                "reason_code": g.reason_code,
                "detail": g.detail,
                "rules_fired": g.rules_fired,
                "risk_score": g.risk_score,
            },
        }
        if g.decision is Decision.BLOCK:
            out["final_status"] = "blocked"
            out["needs_human_review"] = True
        return out

    def validate_node(state: AgentState) -> AgentState:
        if state.get("paused") or state.get("final_status") == "blocked":
            return state
        parse_result = state.get("parse_result") or {}
        if parse_result.get("reason_code") in {"unrecognized_format", "unparseable"}:
            g = evaluate(
                GuardrailInput(
                    household_id=state["household_id"],
                    stage="parse",
                    parse_result=parse_result,
                )
            )
            review_id = f"RVW-{state['run_id']}-G1"
            store.enqueue_review(
                {
                    "id": review_id,
                    "run_id": state["run_id"],
                    "household_id": state["household_id"],
                    "gate": "gate1",
                    "payload": {"parse_result": redact_obj(parse_result)},
                }
            )
            return {
                **state,
                "validation": {
                    "passed": False,
                    "abstain_reason": parse_result.get("reason_code"),
                    "checks": [],
                    "needs_human_review": True,
                },
                "gate1": {"status": "pending", "review_id": review_id},
                "final_status": "held",
                "needs_human_review": True,
                "abstained": True,
                "guardrail": {
                    "decision": g.decision.value,
                    "reason_code": g.reason_code,
                    "detail": g.detail,
                },
            }

        validation = validate_household(
            store,
            household_id=state["household_id"],
            parsed_rows=parse_result.get("rows"),
        )
        g = evaluate(
            GuardrailInput(
                household_id=state["household_id"],
                stage="validate",
                validation=validation,
                parse_result=parse_result,
            )
        )
        review_id = f"RVW-{state['run_id']}-G1"
        store.enqueue_review(
            {
                "id": review_id,
                "run_id": state["run_id"],
                "household_id": state["household_id"],
                "gate": "gate1",
                "payload": {"validation": redact_obj(validation)},
            }
        )
        gate1 = {"status": "pending", "review_id": review_id}
        if state.get("auto_approve_gates") and validation.get("passed"):
            store.decide_review(
                review_id,
                decision="approved",
                reason="auto-approve for stub eval clean path",
                actor="eval_harness",
            )
            gate1 = {"status": "approved", "review_id": review_id}

        out: AgentState = {
            **state,
            "validation": validation,
            "gate1": gate1,
            "guardrail": {
                "decision": g.decision.value,
                "reason_code": g.reason_code,
                "detail": g.detail,
            },
        }
        if not validation.get("passed"):
            out["final_status"] = "held"
            out["needs_human_review"] = True
            out["abstained"] = True
        return out

    def draft_node(state: AgentState) -> AgentState:
        if state.get("paused") or state.get("final_status") in {"blocked", "held"}:
            # Still allow abstention packet already set.
            if state.get("abstained"):
                return state
            return state
        if (state.get("gate1") or {}).get("status") != "approved":
            return {
                **state,
                "final_status": "awaiting_gate1",
                "needs_human_review": True,
            }

        validation = state.get("validation") or {}
        holdings = store.holdings_for(state["household_id"])
        proposal = propose_plan_action(
            household_id=state["household_id"],
            validation=validation,
            scenario=state.get("scenario"),
        )
        extra = proposal.extra_claims if proposal.action == "fabricate_trap" else None
        plan_result = draft_migration_plan(
            household_id=state["household_id"],
            validation=validation,
            holdings=holdings,
            parsed_rows=(state.get("parse_result") or {}).get("rows"),
            extra_claims=extra,
        )
        # If fabricate trap produced fabricated lines, force BLOCK path via policy.
        g = evaluate(
            GuardrailInput(
                household_id=state["household_id"],
                stage="draft",
                validation=validation,
                plan=plan_result,
            )
        )
        # Fabrication trap: if extra fabricated claims existed, mark fabricated even if stripped.
        if proposal.action == "fabricate_trap":
            g_dict = {
                "decision": Decision.BLOCK.value,
                "reason_code": "fabrication_blocked",
                "detail": "Fabrication trap: holding not in source.",
            }
            store.append_answer(
                case_id=state.get("scenario") or state["run_id"],
                guardrail_verdict="BLOCK",
                reason="fabrication_blocked",
                fabricated=1,
            )
            return {
                **state,
                "plan_result": plan_result,
                "guardrail": g_dict,
                "final_status": "blocked",
                "cost_usd": state.get("cost_usd", 0.0) + proposal.cost_usd,
            }

        review_id = f"RVW-{state['run_id']}-G2"
        store.enqueue_review(
            {
                "id": review_id,
                "run_id": state["run_id"],
                "household_id": state["household_id"],
                "gate": "gate2",
                "payload": {"plan": redact_obj(plan_result.get("plan"))},
            }
        )
        gate2 = {"status": "pending", "review_id": review_id}
        if state.get("auto_approve_gates") and plan_result.get("ok"):
            store.decide_review(
                review_id,
                decision="approved",
                reason="auto-approve for stub eval clean path",
                actor="eval_harness",
            )
            gate2 = {"status": "approved", "review_id": review_id}

        ung = 0
        if plan_result.get("plan") and plan_result["plan"].get("stripped_uncited"):
            ung = 1
        store.append_answer(
            case_id=state.get("scenario") or state["run_id"],
            guardrail_verdict=g.decision.value,
            reason=g.reason_code,
            ungrounded=ung,
        )
        return {
            **state,
            "plan_result": plan_result,
            "gate2": gate2,
            "guardrail": {
                "decision": g.decision.value,
                "reason_code": g.reason_code,
                "detail": g.detail,
            },
            "cost_usd": state.get("cost_usd", 0.0) + proposal.cost_usd,
            "final_status": (
                "awaiting_gate2"
                if gate2["status"] != "approved"
                else ("ready_to_import" if g.decision is Decision.ALLOW else "held")
            ),
            "abstained": bool(plan_result.get("abstained")),
            "needs_human_review": bool(plan_result.get("needs_human_review")),
        }

    def import_stub_node(state: AgentState) -> AgentState:
        if state.get("paused") or state.get("final_status") in {
            "blocked",
            "held",
            "awaiting_gate1",
            "awaiting_gate2",
            "paused",
        }:
            return state
        if (state.get("gate2") or {}).get("status") != "approved":
            return {**state, "final_status": "awaiting_gate2", "needs_human_review": True}

        g = evaluate(
            GuardrailInput(
                household_id=state["household_id"],
                stage="import",
                validation=state.get("validation"),
                plan=state.get("plan_result"),
                gates_passed={
                    "gate1": (state.get("gate1") or {}).get("status") == "approved",
                    "gate2": (state.get("gate2") or {}).get("status") == "approved",
                },
            )
        )
        if g.decision is not Decision.ALLOW:
            return {
                **state,
                "guardrail": {
                    "decision": g.decision.value,
                    "reason_code": g.reason_code,
                    "detail": g.detail,
                },
                "final_status": "held",
            }

        detail = {
            "event": "import_stub_logged",
            "household_id": state["household_id"],
            "note": "Log-only stub — no data written to any external system.",
        }
        store.log_import_stub(
            run_id=state["run_id"],
            household_id=state["household_id"],
            detail=detail,
        )
        return {
            **state,
            "import_log": detail,
            "guardrail": {
                "decision": g.decision.value,
                "reason_code": g.reason_code,
                "detail": g.detail,
            },
            "final_status": "import_stub_logged",
        }

    def route_after_pause(state: AgentState) -> str:
        return "end" if state.get("paused") else "parse"

    def route_after_parse(state: AgentState) -> str:
        if state.get("final_status") == "blocked":
            return "end"
        return "validate"

    def route_after_validate(state: AgentState) -> str:
        if state.get("final_status") in {"blocked", "held"}:
            return "end"
        if (state.get("gate1") or {}).get("status") != "approved":
            return "end"
        return "draft"

    def route_after_draft(state: AgentState) -> str:
        if state.get("final_status") in {"blocked", "held", "awaiting_gate2"}:
            return "end"
        if (state.get("gate2") or {}).get("status") != "approved":
            return "end"
        return "import_stub"

    graph = StateGraph(AgentState)
    graph.add_node("pause", check_pause)
    graph.add_node("parse", parse_node)
    graph.add_node("validate", validate_node)
    graph.add_node("draft", draft_node)
    graph.add_node("import_stub", import_stub_node)
    graph.set_entry_point("pause")
    graph.add_conditional_edges("pause", route_after_pause, {"parse": "parse", "end": END})
    graph.add_conditional_edges("parse", route_after_parse, {"validate": "validate", "end": END})
    graph.add_conditional_edges("validate", route_after_validate, {"draft": "draft", "end": END})
    graph.add_conditional_edges(
        "draft", route_after_draft, {"import_stub": "import_stub", "end": END}
    )
    graph.add_edge("import_stub", END)
    return graph.compile()


def run_agent(
    store: GovernedStore,
    *,
    household_id: str,
    source_id: str | None = None,
    scenario: str | None = None,
    auto_approve_gates: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run one household through the bounded pipeline."""
    # Scenario-driven preseeds for pause controls.
    if scenario == "fabrication_preseed":
        # Need FABRICATION_STREAK_PAUSE consecutive fabrication BLOCKs already present.
        for i in range(2):
            store.append_answer(
                case_id=f"PRE-FAB-{i}",
                guardrail_verdict="BLOCK",
                reason="fabrication_blocked",
                fabricated=1,
            )
    elif scenario == "block_streak_preseed":
        for i in range(3):
            store.append_answer(
                case_id=f"PRE-BLK-{i}",
                guardrail_verdict="BLOCK",
                reason="injection_blocked",
            )
    elif scenario == "auto_allow_preseed":
        # 17/20 ALLOW = 85% > 80% threshold over last 20.
        for i in range(17):
            store.append_answer(
                case_id=f"PRE-ALLOW-{i}",
                guardrail_verdict="ALLOW",
                reason="plan_cited",
            )
        for i in range(3):
            store.append_answer(
                case_id=f"PRE-HOLD-{i}",
                guardrail_verdict="HOLD",
                reason="missing_cost_basis",
            )
    elif scenario == "ungrounded_preseed":
        for i in range(10):
            store.append_answer(
                case_id=f"PRE-UNG-{i}",
                guardrail_verdict="HOLD",
                reason="uncited_claims",
                ungrounded=1,
            )

    rid = run_id or f"RUN-{uuid.uuid4().hex[:12]}"
    app = build_graph(store)
    state: AgentState = {
        "run_id": rid,
        "household_id": household_id,
        "source_id": source_id,
        "scenario": scenario,
        "auto_approve_gates": auto_approve_gates,
        "cost_usd": 0.0,
    }
    result = app.invoke(state)
    store.append_run(
        {
            "id": rid,
            "household_id": household_id,
            "status": result.get("final_status") or "unknown",
            "guardrail_verdict": (result.get("guardrail") or {}).get("decision"),
            "reason_code": (result.get("guardrail") or {}).get("reason_code"),
            "created_at": _now(),
            "detail": redact_obj(
                {
                    "parse_result": result.get("parse_result"),
                    "validation": result.get("validation"),
                    "gate1": result.get("gate1"),
                    "gate2": result.get("gate2"),
                    "plan_result": result.get("plan_result"),
                    "import_log": result.get("import_log"),
                    "paused": result.get("paused"),
                    "scenario": scenario,
                }
            ),
        }
    )
    # Record answers for non-draft terminal paths too (injection blocks, holds).
    terminal = result.get("final_status") in {"blocked", "held", "paused"}
    if terminal and scenario != "fabrication_trap":
        g = result.get("guardrail") or {}
        # Avoid double-append when draft already logged.
        if result.get("plan_result") is None:
            store.append_answer(
                case_id=scenario or rid,
                guardrail_verdict=g.get("decision") or "HOLD",
                reason=g.get("reason_code") or "unknown",
                fabricated=1 if "fabricat" in str(g.get("reason_code", "")).lower() else 0,
                ungrounded=1 if "uncited" in str(g.get("reason_code", "")).lower() else 0,
            )
    return dict(result)
