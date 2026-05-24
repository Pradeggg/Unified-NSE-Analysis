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


# ---------------------------------------------------------------------------
# AA-UR-2 — ContextPack contract tests
# ---------------------------------------------------------------------------

from terminal.router import (
    ActiveReport,
    ActiveWorkflow,
    ContextPack,
    PendingOption,
    RecentTurn,
    WorkflowStep,
)


def test_context_pack_to_dict_roundtrips():
    pack = ContextPack(
        session_id="s1",
        recent_turns=(
            RecentTurn(
                turn_index=1,
                user_input="analyse DIXON",
                intent="analysis",
                symbols=("DIXON",),
                tools=("mtf",),
                result_type="mtf_summary",
                source_label="PG",
                freshness="EOD",
                report_paths=("reports/DIXON.md",),
            ),
        ),
        active_symbols=("DIXON",),
        active_indices=("NIFTY50",),
        active_sectors=("IT",),
        active_reports=(
            ActiveReport(path="reports/DIXON.md", report_type="mtf", symbol="DIXON"),
        ),
        active_workflow=ActiveWorkflow(
            workflow_id="wf-1",
            kind="sherlock",
            steps=(
                WorkflowStep(
                    step_id="s1",
                    kind="setup",
                    evidence=({"symbol": "DIXON", "fact": "x", "value": "1"},),
                ),
            ),
        ),
        pending_options=(PendingOption(label="A", text="run scan", bound_action={"cmd": "/scan"}),),
        source_trails=({"source_label": "PG", "freshness": "EOD"},),
        freshness="EOD",
    )
    restored = ContextPack.from_dict(pack.to_dict())
    assert restored.session_id == "s1"
    assert restored.active_symbols == ("DIXON",)
    assert restored.active_workflow.steps[0].evidence[0]["fact"] == "x"
    assert restored.find_pending_option("a").bound_action == {"cmd": "/scan"}
    assert restored.report_for(symbol="DIXON").path == "reports/DIXON.md"


def test_active_workflow_append_step_is_immutable_and_returns_new_instance():
    wf = ActiveWorkflow(workflow_id="wf-1", kind="sherlock")
    step = WorkflowStep(step_id="s1", kind="setup")
    updated = wf.append_step(step)
    assert wf.steps == ()  # original untouched
    assert len(updated.steps) == 1
    assert updated.workflow_id == wf.workflow_id


def test_active_report_requires_non_empty_path():
    import pytest

    with pytest.raises(ValueError):
        ActiveReport(path="")


def test_pending_option_requires_label_and_text():
    import pytest

    with pytest.raises(ValueError):
        PendingOption(label="", text="x")
    with pytest.raises(ValueError):
        PendingOption(label="A", text="")


# ---------------------------------------------------------------------------
# AA-UR-3 — UnifiedRouter wrapper + provider chain
# ---------------------------------------------------------------------------

import pytest

from terminal.router import (
    ContextPack,
    DirectIntentProvider,
    EntityTopicProvider,
    PendingOption,
    PendingOptionProvider,
    RecentTurn,
    RouteCandidate,
    UnifiedRouter,
)
from terminal.router.providers import (
    ContextualFollowupProvider,
    MarketSituationProvider,
    ReportProvider,
    VisualScanProvider,
)


def _empty_pack(**overrides) -> ContextPack:
    base = {"session_id": "s-route"}
    base.update(overrides)
    return ContextPack(**base)


def test_unified_router_default_provider_chain_order():
    router = UnifiedRouter()
    assert router.provider_names == [
        "PendingOptionProvider",
        "ContextualFollowupProvider",
        "EntityTopicProvider",
        "ReportProvider",
        "VisualScanProvider",
        "MarketSituationProvider",
        "DirectIntentProvider",
    ]


def test_pending_option_provider_short_circuits_without_symbol_resolution():
    """AA-UR-3 acceptance: pending option replies execute bound actions
    without symbol re-resolution.
    """
    pack = _empty_pack(
        pending_options=(
            PendingOption(
                label="A",
                text="run intraday scan for DIXON",
                bound_action={
                    "intent": "intraday_scan",
                    "tool_plan": [
                        {"tool": "run_intraday_screener", "args": {"symbol": "DIXON"}},
                    ],
                },
            ),
        ),
        active_symbols=("DIXON",),
    )
    decision = UnifiedRouter().route("A", pack)
    assert decision.route_type == "direct_tool_plan"
    assert decision.intent == "intraday_scan"
    assert decision.confidence == "high"
    assert decision.reasoning_summary.selected_branch == "PendingOptionProvider"
    assert decision.context_binding.binding_type == "pending_option"
    # The tool args came straight from the bound action — no resolver call.
    tools = decision.tool_plan_tuples()
    assert tools == [("run_intraday_screener", {"symbol": "DIXON"})]
    assert decision.validation.ok is True


def test_pending_option_provider_ignores_unknown_label():
    pack = _empty_pack(
        pending_options=(
            PendingOption(label="A", text="run scan", bound_action={"intent": "x"}),
        ),
    )
    decision = UnifiedRouter().route("Z", pack)
    assert decision.reasoning_summary.selected_branch != "PendingOptionProvider"


def test_pending_option_outranks_market_situation_for_label_reply():
    pack = _empty_pack(
        pending_options=(
            PendingOption(
                label="1",
                text="show top gainers",
                bound_action={
                    "intent": "top_gainers",
                    "tool_plan": [{"tool": "top_gainers", "args": {}}],
                },
            ),
        ),
    )
    decision = UnifiedRouter().route("1", pack)
    assert decision.reasoning_summary.selected_branch == "PendingOptionProvider"
    # MarketSituationProvider would NOT match "1" on its own, but the test
    # asserts the label resolves before any other provider can fire.


def test_contextual_followup_provider_fires_on_above_phrase_with_symbol_context():
    pack = _empty_pack(active_symbols=("DIXON",), freshness="EOD 2026-05-22")
    decision = UnifiedRouter().route(
        "Based on the above what would be your recommendation?", pack
    )
    assert decision.reasoning_summary.selected_branch == "ContextualFollowupProvider"
    assert decision.route_type == "contextual_answer"
    assert decision.context_binding.symbols == ("DIXON",)
    assert decision.context_binding.freshness == "EOD 2026-05-22"
    assert decision.source_policy.allow_stale is False


def test_contextual_followup_requires_some_context():
    """No symbols, no workflow, no recent turns → followup provider doesn't fire."""
    pack = _empty_pack()
    decision = UnifiedRouter().route("based on the above what do you think", pack)
    assert decision.reasoning_summary.selected_branch != "ContextualFollowupProvider"


def test_entity_topic_provider_binds_symbol_and_topic():
    pack = _empty_pack()
    decision = UnifiedRouter().route("DIXON fundamentals please", pack)
    assert decision.reasoning_summary.selected_branch == "EntityTopicProvider"
    assert decision.intent == "entity_topic_fundamentals"
    tools = decision.tool_plan_tuples()
    assert tools == [("fundamentals_for_symbol", {"symbol": "DIXON"})]
    assert decision.validation.ok is True


def test_report_provider_binds_to_active_report():
    from terminal.router import ActiveReport

    pack = _empty_pack(
        active_reports=(
            ActiveReport(path="reports/DIXON_mtf.md", report_type="mtf", symbol="DIXON"),
        ),
        active_symbols=("DIXON",),
    )
    decision = UnifiedRouter().route("Tell me what the report says about it", pack)
    assert decision.reasoning_summary.selected_branch == "ReportProvider"
    assert decision.route_type == "contextual_answer"
    assert "reports/DIXON_mtf.md" in decision.context_binding.report_paths


def test_visual_scan_provider_fires_on_chart_phrase():
    pack = _empty_pack(active_symbols=("RELIANCE",))
    decision = UnifiedRouter().route("Show me the candlestick chart for it", pack)
    assert decision.reasoning_summary.selected_branch == "VisualScanProvider"
    assert decision.tool_plan_tuples()[0][0] == "render_visual_scan"


def test_market_situation_provider_handles_market_wide_ask():
    pack = _empty_pack()
    decision = UnifiedRouter().route("Run an intraday scan across NIFTY", pack)
    assert decision.reasoning_summary.selected_branch == "MarketSituationProvider"
    assert decision.intent == "market_situation"


def test_direct_intent_provider_is_last_resort_fallback():
    pack = _empty_pack()
    decision = UnifiedRouter().route("show me the RSI", pack)
    # EntityTopic doesn't fire (no symbol token), Market doesn't fire,
    # so DirectIntent picks up "rsi" → technicals.
    assert decision.reasoning_summary.selected_branch == "DirectIntentProvider"
    assert decision.intent == "direct_technicals"


def test_router_emits_fallback_llm_when_no_provider_proposes():
    pack = _empty_pack()
    decision = UnifiedRouter().route("hello there friend", pack)
    assert decision.route_type == "fallback_llm"
    assert decision.confidence == "low"
    assert decision.reasoning_summary.selected_branch == "<none>"
    # All providers should appear as rejected branches.
    assert "PendingOptionProvider" in decision.reasoning_summary.rejected_branches


def test_route_decision_trace_contains_provider_score_binding_and_reasons():
    """AA-UR-3 acceptance: route trace shows candidate provider, score,
    context binding, and winning reason.
    """
    pack = _empty_pack(active_symbols=("DIXON",))
    decision = UnifiedRouter().route("DIXON technicals", pack)
    trace = decision.to_debug_trace()
    assert trace["selected_branch"] == "EntityTopicProvider"
    assert trace["context"]["symbols"] == ["DIXON"]
    assert trace["route_type"] == "direct_tool_plan"
    assert trace["tools"] == ["technicals_for_symbol"]
    assert decision.reasoning_summary.pot, "winning reason must be recorded"


def test_router_isolates_provider_exceptions():
    class BoomProvider:
        name = "BoomProvider"

        def propose(self, user_input, context_pack):
            raise RuntimeError("boom")

    router = UnifiedRouter(providers=[BoomProvider(), DirectIntentProvider()])
    decision = router.route("fundamentals", _empty_pack())
    # The healthy provider still wins.
    assert decision.reasoning_summary.selected_branch == "DirectIntentProvider"
    # The boom reason appears as a rejected branch.
    rejected = " ".join(decision.reasoning_summary.rejected_branches)
    assert "BoomProvider" in rejected


def test_higher_score_wins_over_registration_order():
    class LowScore:
        name = "LowScore"

        def propose(self, user_input, context_pack):
            return [
                RouteCandidate(
                    provider=self.name,
                    intent="low",
                    route_type="contextual_answer",
                    confidence="low",
                    score=0.2,
                    reasons=("low scorer",),
                )
            ]

    class HighScore:
        name = "HighScore"

        def propose(self, user_input, context_pack):
            return [
                RouteCandidate(
                    provider=self.name,
                    intent="high",
                    route_type="contextual_answer",
                    confidence="high",
                    score=0.9,
                    reasons=("high scorer",),
                )
            ]

    router = UnifiedRouter(providers=[LowScore(), HighScore()])
    decision = router.route("anything", _empty_pack())
    assert decision.reasoning_summary.selected_branch == "HighScore"
    assert decision.intent == "high"


def test_registration_order_breaks_score_ties():
    class A:
        name = "AlphaProvider"

        def propose(self, user_input, context_pack):
            return [
                RouteCandidate(
                    provider=self.name, intent="a",
                    route_type="contextual_answer", confidence="medium",
                    score=0.5, reasons=("a",),
                )
            ]

    class B:
        name = "BetaProvider"

        def propose(self, user_input, context_pack):
            return [
                RouteCandidate(
                    provider=self.name, intent="b",
                    route_type="contextual_answer", confidence="medium",
                    score=0.5, reasons=("b",),
                )
            ]

    decision = UnifiedRouter(providers=[A(), B()]).route("x", _empty_pack())
    assert decision.reasoning_summary.selected_branch == "AlphaProvider"


def test_decision_validation_flags_missing_tool_plan_for_direct_routes():
    class BadProvider:
        name = "BadProvider"

        def propose(self, user_input, context_pack):
            return [
                RouteCandidate(
                    provider=self.name,
                    intent="oops",
                    route_type="direct_tool_plan",
                    confidence="high",
                    score=0.9,
                    reasons=("missing tools",),
                    tool_plan=(),
                )
            ]

    decision = UnifiedRouter(providers=[BadProvider()]).route("x", _empty_pack())
    assert decision.validation.ok is False
    assert any("tool_plan" in err for err in decision.validation.errors)
