import pytest

from terminal.router import (
    ContextBinding,
    EvidenceRequirement,
    NextOption,
    RouteCandidate,
    RouteDecision,
    RouteReasoningSummary,
    RouteValidation,
    SourcePolicy,
    ToolCallSpec,
)


def test_route_decision_serializes_debug_trace_and_tool_plan():
    decision = RouteDecision(
        decision_id="route-001",
        intent="compound_stock_intraday_fno",
        route_type="compound_plan",
        confidence="high",
        user_is_asking="Live price, F&O data, and 5m intraday setup for DIXON.",
        context_binding=ContextBinding(
            binding_type="new_direct",
            symbols=("DIXON",),
            freshness="live",
        ),
        evidence_requirements=(
            EvidenceRequirement(name="live_quote", required_tools=("get_live_quote",)),
            EvidenceRequirement(name="fno_overview", required_tools=("get_fno_overview",)),
        ),
        tool_plan=(
            ToolCallSpec("resolve_symbol", {"query": "dixon tech"}),
            ToolCallSpec("get_live_quote", {"symbol": "DIXON"}),
        ),
        next_options=(
            NextOption(
                label="A",
                text="Run 5m intraday follow-up",
                bound_action={
                    "decision": "run_tool_plan",
                    "tool_plan": [("get_intraday_analysis", {"symbol": "DIXON", "interval": "5m"})],
                },
            ),
        ),
        source_policy=SourcePolicy(required_freshness="live", allow_stale=False),
        reasoning_summary=RouteReasoningSummary(
            pot=("Bind explicit DIXON entity.", "Cover all requested tasks."),
            selected_branch="compound_stock_intraday_fno",
            rejected_branches=("generic_fno_overview",),
        ),
        validation=RouteValidation(ok=True, checked_tools=("resolve_symbol", "get_live_quote")),
    )

    assert decision.is_executable is True
    assert decision.tool_plan_tuples() == [
        ("resolve_symbol", {"query": "dixon tech"}),
        ("get_live_quote", {"symbol": "DIXON"}),
    ]
    assert decision.to_debug_trace() == {
        "decision_id": "route-001",
        "intent": "compound_stock_intraday_fno",
        "route_type": "compound_plan",
        "confidence": "high",
        "context": {
            "binding_type": "new_direct",
            "symbols": ["DIXON"],
            "indices": [],
            "sectors": [],
            "report_paths": [],
            "workflow_id": "",
            "freshness": "live",
        },
        "tools": ["resolve_symbol", "get_live_quote"],
        "next_options": ["A"],
        "validation": {"ok": True, "errors": [], "checked_tools": ["resolve_symbol", "get_live_quote"]},
        "selected_branch": "compound_stock_intraday_fno",
        "rejected_branches": ["generic_fno_overview"],
    }


def test_route_candidate_score_and_to_decision_preserve_reasoning():
    candidate = RouteCandidate(
        provider="CompoundStockProvider",
        intent="compound_stock_intraday_fno",
        route_type="compound_plan",
        confidence="medium",
        score=0.82,
        reasons=("explicit symbol", "covers live and intraday"),
        tool_plan=(ToolCallSpec("get_live_quote", {"symbol": "DIXON"}),),
    )

    decision = candidate.to_decision(
        decision_id="candidate-001",
        user_is_asking="Compound stock request.",
        context_binding=ContextBinding(binding_type="new_direct", symbols=("DIXON",)),
        validation=RouteValidation(ok=True, checked_tools=("get_live_quote",)),
    )

    assert decision.intent == "compound_stock_intraday_fno"
    assert decision.reasoning_summary.selected_branch == "CompoundStockProvider"
    assert decision.reasoning_summary.pot == ("explicit symbol", "covers live and intraday")


def test_invalid_route_contract_values_raise_value_error():
    with pytest.raises(ValueError, match="route_type"):
        RouteDecision(
            decision_id="bad",
            intent="bad",
            route_type="unknown",
            confidence="high",
            user_is_asking="Bad route.",
            context_binding=ContextBinding(),
            validation=RouteValidation(ok=False),
        )

    with pytest.raises(ValueError, match="confidence"):
        RouteCandidate(
            provider="x",
            intent="x",
            route_type="direct_tool_plan",
            confidence="certain",
            score=0.5,
        )


def test_blocked_route_is_not_executable_and_validation_errors_are_serialized():
    decision = RouteDecision(
        decision_id="blocked",
        intent="intraday_scan",
        route_type="blocked_ungrounded",
        confidence="low",
        user_is_asking="Run a grounded scan without enough scope.",
        context_binding=ContextBinding(binding_type="none"),
        validation=RouteValidation(
            ok=False,
            errors=("Missing symbol universe.", "No grounded tool plan."),
        ),
    )

    assert decision.is_executable is False
    assert decision.to_debug_trace()["validation"] == {
        "ok": False,
        "errors": ["Missing symbol universe.", "No grounded tool plan."],
        "checked_tools": [],
    }
