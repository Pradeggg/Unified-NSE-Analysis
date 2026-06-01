from __future__ import annotations

from terminal.research_council.engine import initialize_state
from terminal.research_council.states import route


def test_initialize_state_infers_sector_opportunity_for_nifty_auto_query():
    state = initialize_state("Analyze NIFTY AUTO and identify best potential stocks", dry_run=True)

    assert state.mode == "sector_opportunity"
    assert state.universe_filter == "liquid"


def test_route_expands_sector_query_into_auditable_council_plan():
    state = initialize_state("Analyze NIFTY AUTO and identify best potential stocks", dry_run=True)

    routed = route.run(state)

    decision = routed.route_decision
    assert decision["workflow"] == "sector_opportunity"
    assert decision["sector"] == "NIFTY AUTO"
    assert decision["expanded_objective"].startswith("Find the best research candidates")
    assert decision["coder_quant_policy"] == "shortlist_only"
    assert "sector_rotation" in decision["selected_agents"]
    assert "technical" in decision["selected_agents"]
    assert "fundamental" in decision["selected_agents"]
    assert "coder_quant" in decision["selected_agents"]
    assert any("worth allocating attention" in q for q in decision["sub_questions"])
    assert any("route is testable" in q for q in decision["sub_questions"])


def test_route_uses_explicit_sector_flag_when_objective_is_generic():
    state = initialize_state("/council sector --horizon swing", mode="sector_opportunity", sector="NIFTY AUTO", dry_run=True)

    routed = route.run(state)

    assert routed.route_decision["sector"] == "NIFTY AUTO"
    assert "NIFTY AUTO" in routed.route_decision["expanded_objective"]


def test_route_keeps_strategy_build_query_as_strategy_workflow():
    state = initialize_state("Build a Stage 2 breakout strategy", dry_run=True)

    routed = route.run(state)

    assert routed.mode == "strategy_build"
    assert routed.route_decision["workflow"] == "strategy_build"
    assert routed.route_decision["coder_quant_policy"] == "primary"
