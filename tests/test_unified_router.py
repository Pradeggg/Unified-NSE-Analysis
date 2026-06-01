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
    CouncilCommandProvider,
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
        "CouncilCommandProvider",
        "ContextualFollowupProvider",
        "CompoundStockProvider",
        "ReportProvider",
        "VisualScanProvider",
        "TopMoversProvider",
        "MarketSituationProvider",
    ]


def test_council_command_routes_to_research_council_tool_not_stock_analysis():
    decision = UnifiedRouter().route(
        "/council stock MODISONLTD --horizon swing",
        _empty_pack(),
    )

    assert decision.route_type == "direct_tool_plan"
    assert decision.intent == "research_council"
    assert decision.reasoning_summary.selected_branch == "CouncilCommandProvider"
    assert decision.tool_plan_tuples() == [
        (
            "run_research_council",
            {
                "objective": "/council stock MODISONLTD --horizon swing",
                "mode": "stock_deep_dive",
                "symbols": ["MODISONLTD"],
                "horizon": "swing",
                "risk_budget": "moderate",
            },
        )
    ]


def test_council_sector_command_routes_with_sector_option():
    decision = UnifiedRouter().route(
        "/council sector NIFTY AUTO --horizon swing",
        _empty_pack(),
    )

    assert decision.route_type == "direct_tool_plan"
    assert decision.intent == "research_council"
    assert decision.tool_plan_tuples() == [
        (
            "run_research_council",
            {
                "objective": "/council sector NIFTY AUTO --horizon swing",
                "mode": "sector_opportunity",
                "symbols": [],
                "horizon": "swing",
                "risk_budget": "moderate",
                "sector": "NIFTY AUTO",
            },
        )
    ]


def test_council_steward_routes_to_data_steward_tool():
    decision = UnifiedRouter().route("/council steward", _empty_pack())

    assert decision.route_type == "direct_tool_plan"
    assert decision.intent == "research_council"
    assert decision.reasoning_summary.selected_branch == "CouncilCommandProvider"
    assert decision.tool_plan_tuples() == [
        ("run_data_steward_check", {"mode": "market_council"})
    ]


def test_council_review_file_routes_to_report_review_engine():
    decision = UnifiedRouter().route("/council review --file /tmp/broken_report.md", _empty_pack())

    assert decision.route_type == "direct_tool_plan"
    assert decision.intent == "research_council"
    assert decision.tool_plan_tuples() == [
        (
            "run_research_council",
            {
                "objective": "/council review --file /tmp/broken_report.md",
                "mode": "report_review",
                "symbols": [],
                "horizon": "swing",
                "risk_budget": "moderate",
                "report_path": "/tmp/broken_report.md",
            },
        )
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
    decision = UnifiedRouter(providers=[EntityTopicProvider()]).route("DIXON fundamentals please", pack)
    assert decision.reasoning_summary.selected_branch == "EntityTopicProvider"
    assert decision.intent == "entity_topic_fundamentals"
    tools = decision.tool_plan_tuples()
    # AA-UR-5: provider now binds a real TOOL_REGISTRY tool.
    assert tools == [("search_yahoo_finance", {"symbol": "DIXON"})]
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
    assert decision.tool_plan_tuples()[0][0] == "run_visual_scan"


def test_market_situation_provider_handles_market_wide_ask():
    pack = _empty_pack()
    decision = UnifiedRouter().route("Run an intraday scan across NIFTY", pack)
    assert decision.reasoning_summary.selected_branch == "MarketSituationProvider"
    assert decision.intent == "market_situation"


def test_direct_intent_provider_is_last_resort_fallback():
    pack = _empty_pack()
    decision = UnifiedRouter(providers=[DirectIntentProvider()]).route("show me the RSI", pack)
    # AA-UR-5: keyword without a symbol now yields a clarification so the
    # router never executes a tool with missing required args.
    assert decision.reasoning_summary.selected_branch == "DirectIntentProvider"
    assert decision.intent == "direct_technicals_clarify"
    assert decision.route_type == "clarification"


def test_direct_intent_provider_binds_pack_symbol_when_available():
    pack = _empty_pack(active_symbols=("RELIANCE",))
    decision = UnifiedRouter(providers=[DirectIntentProvider()]).route("show me the RSI", pack)
    assert decision.reasoning_summary.selected_branch == "DirectIntentProvider"
    assert decision.intent == "direct_technicals"
    assert decision.tool_plan_tuples() == [
        ("resolve_symbol", {"query": "RELIANCE"}),
        ("get_symbol_snapshot", {"symbol": "RELIANCE"}),
        ("get_technical_setup", {"symbol": "RELIANCE"}),
    ]


def test_router_emits_fallback_llm_when_no_provider_proposes():
    pack = _empty_pack()
    decision = UnifiedRouter().route("hello there friend", pack)
    assert decision.route_type == "fallback_llm"
    assert decision.confidence == "low"
    assert decision.reasoning_summary.selected_branch == "<none>"
    # All providers should appear as rejected branches.
    assert "PendingOptionProvider" in decision.reasoning_summary.rejected_branches


def test_route_decision_trace_contains_provider_score_binding_and_reasons():
    """Route trace shows candidate provider, score, context binding, and winning reason."""
    pack = _empty_pack()
    decision = UnifiedRouter().route("market situation today", pack)
    trace = decision.to_debug_trace()
    assert trace["selected_branch"] == "MarketSituationProvider"
    assert trace["route_type"] == "direct_tool_plan"
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
    """AA-UR-5: a direct_tool_plan with no tools is rewritten to
    blocked_ungrounded rather than executed.
    """
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
    assert decision.route_type == "blocked_ungrounded"
    assert decision.tool_plan == ()
    assert any(
        "AA-UR-5 blocked" in reason
        for reason in decision.reasoning_summary.rejected_branches
    )


# ---------------------------------------------------------------------------
# AA-UR-4 — CompoundStockProvider
# ---------------------------------------------------------------------------

from terminal.router import CompoundStockProvider
from terminal.router.compound_stock import coverage_map, _detect_timeframe


COMPOUND_DIXON_PROMPT = (
    "live pricies for dixon tech and the analysis of the F&O data "
    "and intraday tradesetup in 5 mins"
)


def test_compound_stock_provider_is_registered_in_default_chain():
    assert "CompoundStockProvider" in UnifiedRouter().provider_names


def test_compound_dixon_prompt_routes_to_dixon_not_nifty():
    """AA-UR-4 acceptance: the exact compound prompt routes to DIXON,
    never to NIFTY, and produces the five-tool compound_plan.
    """
    decision = UnifiedRouter().route(COMPOUND_DIXON_PROMPT, _empty_pack())
    assert decision.route_type == "compound_plan"
    assert decision.reasoning_summary.selected_branch == "CompoundStockProvider"
    assert decision.confidence == "high"

    tools = decision.tool_plan_tuples()
    tool_names = [t for t, _ in tools]
    assert tool_names == [
        "resolve_symbol",
        "get_live_quote",
        "get_fno_overview",
        "explain_intraday_setup",
        "get_intraday_analysis",
    ]
    # Every symbol-bound tool resolves to DIXON. Crucially, none point at NIFTY.
    bound_symbols = {
        args.get("symbol")
        for name, args in tools
        if name != "resolve_symbol" and isinstance(args, dict) and "symbol" in args
    }
    assert bound_symbols == {"DIXON"}
    assert "NIFTY" not in bound_symbols
    # Binding surfaces DIXON even though the pack started empty.
    assert "DIXON" in decision.context_binding.symbols
    assert "NIFTY" not in decision.context_binding.symbols


def test_compound_provider_marks_fno_as_optional_evidence():
    """F&O unavailable path must be explicit: the evidence requirement
    is flagged optional, while live + intraday remain required.
    """
    cand = CompoundStockProvider().propose(COMPOUND_DIXON_PROMPT, _empty_pack())[0]
    cov = coverage_map(cand)
    assert cov == {
        "live_quote": ["get_live_quote"],
        "fno_overview": ["get_fno_overview"],
        "intraday_setup": ["explain_intraday_setup", "get_intraday_analysis"],
    }
    by_name = {req.name: req for req in cand.evidence_requirements}
    assert by_name["fno_overview"].optional is True
    assert by_name["live_quote"].optional is False
    assert by_name["intraday_setup"].optional is False


def test_compound_provider_requires_two_facets():
    """A single-facet ask (just live quote) must NOT win compound."""
    decision = UnifiedRouter().route("show me the live price of dixon tech", _empty_pack())
    assert decision.reasoning_summary.selected_branch != "CompoundStockProvider"


def test_compound_provider_emits_clarification_when_symbol_missing():
    """Compound shape detected but symbol unresolvable → clarification,
    not a silent NIFTY fallback.
    """
    decision = UnifiedRouter().route(
        "give me the live price F&O data and intraday tradesetup", _empty_pack()
    )
    assert decision.reasoning_summary.selected_branch == "CompoundStockProvider"
    assert decision.route_type == "clarification"
    assert decision.confidence == "low"
    # No symbol arg leaks into the trace.
    assert all("symbol" not in (spec.args or {}) for spec in decision.tool_plan)


def test_compound_provider_prefers_stock_over_nifty_when_both_match():
    """Even if 'nifty' appears, a stock match (RELIANCE) must win."""
    prompt = (
        "live price for reliance and F&O overview vs nifty plus intraday setup"
    )
    decision = UnifiedRouter().route(prompt, _empty_pack())
    assert decision.reasoning_summary.selected_branch == "CompoundStockProvider"
    bound = {
        args.get("symbol")
        for name, args in decision.tool_plan_tuples()
        if name != "resolve_symbol" and isinstance(args, dict) and "symbol" in args
    }
    assert "RELIANCE" in bound
    assert "NIFTY" not in bound


def test_compound_provider_detects_timeframe_15m():
    decision = UnifiedRouter().route(
        "live price for dixon tech with F&O analysis on the 15m intraday setup",
        _empty_pack(),
    )
    args_by_tool = {t: a for t, a in decision.tool_plan_tuples()}
    assert args_by_tool["get_intraday_analysis"]["timeframe"] == "15m"


def test_detect_timeframe_helper():
    assert _detect_timeframe("foo 5m bar") == "5m"
    assert _detect_timeframe("foo 15 min bar") == "15m"
    assert _detect_timeframe("foo 30min bar") == "30m"
    assert _detect_timeframe("no timeframe here") == "5m"


def test_compound_validation_passes_for_target_prompt():
    decision = UnifiedRouter().route(COMPOUND_DIXON_PROMPT, _empty_pack())
    assert decision.validation.ok is True
    assert "get_live_quote" in decision.validation.checked_tools
    assert "get_fno_overview" in decision.validation.checked_tools


def test_compound_does_not_fire_for_unrelated_market_ask():
    decision = UnifiedRouter().route("run an intraday scan across NIFTY", _empty_pack())
    assert decision.reasoning_summary.selected_branch != "CompoundStockProvider"


# ---------------------------------------------------------------------------
# AA-UR-5 — Route Validation + Executable NEXT OPTIONS
# ---------------------------------------------------------------------------

from dataclasses import replace as _replace

from terminal.router import (
    ContextBinding,
    NextOption,
    RouteDecision,
    enforce_validation,
    filter_invalid_options,
    match_option_reply,
    validate_decision,
)
from terminal.router.schema import RouteReasoningSummary


def _direct_decision(*, tools, options=()):
    return RouteDecision(
        decision_id="d1",
        intent="test",
        route_type="direct_tool_plan",
        confidence="high",
        user_is_asking="test",
        context_binding=ContextBinding(),
        tool_plan=tools,
        next_options=options,
        reasoning_summary=RouteReasoningSummary(),
        validation=RouteValidation(ok=False),
    )


def test_validate_decision_accepts_known_tool_with_required_args():
    decision = _direct_decision(
        tools=(ToolCallSpec(tool="get_live_quote", args={"symbol": "DIXON"}),),
    )
    result = validate_decision(decision)
    assert result.ok is True
    assert result.errors == ()
    assert "get_live_quote" in result.checked_tools


def test_validate_decision_flags_unknown_tool():
    decision = _direct_decision(
        tools=(ToolCallSpec(tool="not_a_real_tool", args={}),),
    )
    result = validate_decision(decision)
    assert result.ok is False
    assert any("unknown tool" in err for err in result.errors)


def test_validate_decision_flags_missing_required_arg():
    decision = _direct_decision(
        tools=(ToolCallSpec(tool="get_live_quote", args={}),),
    )
    result = validate_decision(decision)
    assert result.ok is False
    assert any("missing required arg 'symbol'" in err for err in result.errors)


def test_validate_decision_flags_empty_string_required_arg():
    decision = _direct_decision(
        tools=(ToolCallSpec(tool="get_live_quote", args={"symbol": "   "}),),
    )
    result = validate_decision(decision)
    assert result.ok is False
    assert any("is empty" in err for err in result.errors)


def test_validate_decision_rejects_index_only_symbol_binding():
    """AA-UR-5: silent NIFTY fallback must be caught at validation time."""
    decision = _direct_decision(
        tools=(ToolCallSpec(tool="get_live_quote", args={"symbol": "NIFTY"}),),
    )
    result = validate_decision(decision)
    assert result.ok is False
    assert any("indices" in err.lower() or "nifty" in err.lower() for err in result.errors)


def test_validate_decision_accepts_mixed_index_and_stock_symbols():
    decision = _direct_decision(
        tools=(
            ToolCallSpec(tool="get_live_quote", args={"symbol": "NIFTY"}),
            ToolCallSpec(tool="get_live_quote", args={"symbol": "DIXON"}),
        ),
    )
    result = validate_decision(decision)
    assert result.ok is True


def test_validate_compound_evidence_coverage():
    """Compound route missing a required evidence tool fails validation."""
    decision = RouteDecision(
        decision_id="d1",
        intent="compound",
        route_type="compound_plan",
        confidence="high",
        user_is_asking="x",
        context_binding=ContextBinding(),
        tool_plan=(
            ToolCallSpec(tool="get_live_quote", args={"symbol": "DIXON"}),
        ),
        evidence_requirements=(
            EvidenceRequirement(
                name="intraday_setup",
                required_tools=("explain_intraday_setup",),
            ),
        ),
        validation=RouteValidation(ok=False),
    )
    result = validate_decision(decision)
    assert result.ok is False
    assert any("intraday_setup" in err and "not covered" in err for err in result.errors)


def test_validate_compound_evidence_skips_optional_requirements():
    decision = RouteDecision(
        decision_id="d1",
        intent="compound",
        route_type="compound_plan",
        confidence="high",
        user_is_asking="x",
        context_binding=ContextBinding(),
        tool_plan=(
            ToolCallSpec(tool="get_live_quote", args={"symbol": "DIXON"}),
        ),
        evidence_requirements=(
            EvidenceRequirement(
                name="fno_overview",
                required_tools=("get_fno_overview",),
                optional=True,
            ),
        ),
        validation=RouteValidation(ok=False),
    )
    result = validate_decision(decision)
    assert result.ok is True


def test_enforce_validation_rewrites_invalid_direct_route_to_blocked_ungrounded():
    decision = _direct_decision(
        tools=(ToolCallSpec(tool="not_a_real_tool", args={}),),
    )
    rewritten = enforce_validation(decision)
    assert rewritten.route_type == "blocked_ungrounded"
    assert rewritten.tool_plan == ()
    assert rewritten.confidence == "low"
    # Original provider name preserved so audit trail survives.
    assert rewritten.reasoning_summary.selected_branch == decision.reasoning_summary.selected_branch
    assert any(
        "AA-UR-5 blocked" in r for r in rewritten.reasoning_summary.rejected_branches
    )


def test_enforce_validation_strips_broken_next_options_and_keeps_route():
    good = NextOption(
        label="A",
        text="run scan",
        bound_action={
            "intent": "scan",
            "tool_plan": [{"tool": "scan_intraday_market", "args": {}}],
        },
    )
    bad = NextOption(
        label="B",
        text="do unknown",
        bound_action={
            "intent": "x",
            "tool_plan": [{"tool": "no_such_tool", "args": {}}],
        },
    )
    decision = _direct_decision(
        tools=(ToolCallSpec(tool="get_live_quote", args={"symbol": "DIXON"}),),
        options=(good, bad),
    )
    rewritten = enforce_validation(decision)
    assert rewritten.route_type == "direct_tool_plan"  # core route survives
    assert [opt.label for opt in rewritten.next_options] == ["A"]
    assert any(
        "dropped NEXT OPTION 'B'" in r
        for r in rewritten.reasoning_summary.rejected_branches
    )


def test_filter_invalid_options_reports_reasons():
    bad = NextOption(label="A", text="x", bound_action={})
    kept, reasons = filter_invalid_options([bad])
    assert kept == ()
    assert reasons and "empty bound_action" in reasons[0]


def test_match_option_reply_handles_label_and_text_and_punctuation():
    opt_a = NextOption(label="A", text="Run intraday scan", bound_action={"intent": "x"})
    opt_1 = NextOption(label="1", text="Show top gainers", bound_action={"intent": "x"})
    pool = [opt_a, opt_1]
    assert match_option_reply("A", pool) is opt_a
    assert match_option_reply("a", pool) is opt_a
    assert match_option_reply("A.", pool) is opt_a
    assert match_option_reply("A)", pool) is opt_a
    assert match_option_reply("1", pool) is opt_1
    assert match_option_reply("show top gainers", pool) is opt_1
    assert match_option_reply("Run intraday scan", pool) is opt_a
    assert match_option_reply("nope", pool) is None
    assert match_option_reply("", pool) is None


def test_router_returns_validated_decision_for_compound_dixon_prompt():
    """End-to-end: target compound prompt passes AA-UR-5 validation."""
    decision = UnifiedRouter().route(COMPOUND_DIXON_PROMPT, _empty_pack())
    assert decision.route_type == "compound_plan"
    assert decision.validation.ok is True
    assert "get_live_quote" in decision.validation.checked_tools


# ---------------------------------------------------------------------------
# AA-UR-7: Sherlock / multi-step workflow binding
# ---------------------------------------------------------------------------

from terminal.router import (
    ActiveWorkflow as _UR7_ActiveWorkflow,
    ContextPack as _UR7_ContextPack,
    WorkflowStep as _UR7_WorkflowStep,
    UnifiedRouter as _UR7_UnifiedRouter,
)
from terminal.router.providers import ContextualFollowupProvider as _UR7_FollowupProvider


def _ur7_sample_workflow(symbol: str = "MANINDS") -> _UR7_ActiveWorkflow:
    steps = (
        _UR7_WorkflowStep(
            step_id="s1", kind="Live Quote", summary="price 123",
            evidence=(
                {"fact": "live_quote", "value": "Rs 123 +1.2%",
                 "symbol": symbol, "source_label": "NSE live", "freshness": "as of 09:30 IST",
                 "stance": "bullish"},
            ),
            source_label="NSE live", freshness="as of 09:30 IST",
        ),
        _UR7_WorkflowStep(
            step_id="s2", kind="Technical Setup", summary="stage 2 RSI 62",
            evidence=(
                {"fact": "weinstein_stage", "value": "Stage 2",
                 "symbol": symbol, "source_label": "tech engine",
                 "freshness": "EoD 2026-05-22", "stance": "bullish"},
            ),
            source_label="tech engine", freshness="EoD 2026-05-22",
        ),
        _UR7_WorkflowStep(
            step_id="s3", kind="Fundamentals", summary="P/E 28",
            evidence=(
                {"fact": "pe_ratio", "value": "28x",
                 "symbol": symbol, "source_label": "screener.in",
                 "freshness": "FY26 Q4", "stance": "neutral"},
            ),
            source_label="screener.in", freshness="FY26 Q4",
        ),
        _UR7_WorkflowStep(
            step_id="s4", kind="News & Catalysts", summary="order win",
            evidence=(
                {"fact": "news", "value": "Order win 200cr",
                 "symbol": symbol, "source_label": "yfinance news",
                 "freshness": "2026-05-21", "stance": "bullish"},
            ),
            source_label="yfinance news", freshness="2026-05-21",
        ),
        _UR7_WorkflowStep(
            step_id="s5", kind="Trade Setup", summary="entry 120 SL 115",
            evidence=(
                {"fact": "trade_setup", "value": "Long 120 SL 115 T 135",
                 "symbol": symbol, "source_label": "intraday engine",
                 "freshness": "15:00 IST", "stance": "bullish"},
            ),
            source_label="intraday engine", freshness="15:00 IST",
        ),
    )
    return _UR7_ActiveWorkflow(workflow_id="ric_sherlock_maninds", kind="sherlock", steps=steps)


def test_ur7_contextual_followup_binds_to_full_workflow():
    pack = _UR7_ContextPack(
        session_id="s",
        active_symbols=("MANINDS",),
        active_workflow=_ur7_sample_workflow(),
    )
    cands = _UR7_FollowupProvider().propose(
        "Based on the above what would be your recommendation", pack
    )
    assert len(cands) == 1
    cand = cands[0]
    assert cand.intent == "contextual_followup_workflow"
    assert cand.route_type == "contextual_answer"
    # All five step kinds surface in route reasons.
    reasons_blob = " ".join(cand.reasons).lower()
    for kind in ("live quote", "technical setup", "fundamentals", "news", "trade setup"):
        assert kind in reasons_blob
    # One evidence requirement per unique step kind.
    req_kinds = {req.name for req in cand.evidence_requirements}
    assert {"live_quote", "technical_setup", "fundamentals", "news_&_catalysts", "trade_setup"} <= req_kinds


def test_ur7_router_binding_includes_workflow_symbols():
    pack = _UR7_ContextPack(
        session_id="s",
        active_symbols=(),  # empty pack — symbols must come from the workflow
        active_workflow=_ur7_sample_workflow("MANINDS"),
    )
    decision = _UR7_UnifiedRouter().route(
        "Based on the above what would be your recommendation", pack
    )
    assert decision.route_type == "contextual_answer"
    assert "MANINDS" in decision.context_binding.symbols
    assert decision.context_binding.workflow_id == "ric_sherlock_maninds"


def test_ur7_followup_flags_freshness_divergence():
    pack = _UR7_ContextPack(
        session_id="s",
        active_symbols=("MANINDS",),
        active_workflow=_ur7_sample_workflow(),
    )
    cands = _UR7_FollowupProvider().propose("based on the above tell me", pack)
    reasons_blob = " ".join(cands[0].reasons).lower()
    assert "freshness divergence" in reasons_blob


def test_ur7_followup_flags_conflicting_stances():
    base = _ur7_sample_workflow()
    bearish_step = _UR7_WorkflowStep(
        step_id="s6", kind="Risk",
        evidence=(
            {"fact": "risk", "value": "high debt",
             "symbol": "MANINDS", "source_label": "screener.in",
             "freshness": "FY26 Q4", "stance": "bearish"},
        ),
    )
    wf = _UR7_ActiveWorkflow(
        workflow_id=base.workflow_id, kind=base.kind, steps=(*base.steps, bearish_step),
    )
    pack = _UR7_ContextPack(
        session_id="s", active_symbols=("MANINDS",), active_workflow=wf,
    )
    cands = _UR7_FollowupProvider().propose("based on the above recommend", pack)
    reasons_blob = " ".join(cands[0].reasons).lower()
    assert "conflicting stances" in reasons_blob
    assert "bullish" in reasons_blob and "bearish" in reasons_blob


def test_ur7_followup_falls_back_when_no_workflow():
    pack = _UR7_ContextPack(
        session_id="s",
        active_symbols=("MANINDS",),
        active_workflow=None,
    )
    cands = _UR7_FollowupProvider().propose("based on the above recommend", pack)
    assert cands and cands[0].intent == "contextual_followup"
    # No workflow evidence requirements when no workflow.
    assert cands[0].evidence_requirements == ()
