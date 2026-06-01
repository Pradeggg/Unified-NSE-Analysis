"""Build deterministic council evidence plans."""

from __future__ import annotations

from dataclasses import replace

from terminal.research_council.agents.hedge_fund_owner import DEFAULT_CHAIR
from terminal.research_council.schemas import Plan, PlanStep, SuccessCriterion, ToolCall


def run(state):
    if state.flags.get("dry_run"):
        return state
    if state.mode == "sector_opportunity":
        plan = _build_sector_opportunity_plan(state)
        return replace(state, plans=[*state.plans, plan]) if plan else state
    if state.mode != "market_council":
        return state
    iteration = len(state.plans)
    plan = DEFAULT_CHAIR.build_market_council_plan(
        run_id=state.run_id,
        iteration=iteration,
        objective=state.objective,
    )
    return replace(state, plans=[*state.plans, plan])


def _build_sector_opportunity_plan(state) -> Plan | None:
    symbols = _shortlist_symbols(state)
    if not symbols:
        return None
    iteration = len(state.plans)
    sector = (state.route_decision or {}).get("sector") or _sector_from_pack(state) or "sector"
    return Plan(
        plan_id=f"{state.run_id}_plan_{iteration}",
        run_id=state.run_id,
        iteration=iteration,
        central_question=f"Sector opportunity quant sweep for: {sector}",
        steps=[
            PlanStep(
                step_id="coder_quant_shortlist_sweep",
                sequence=1,
                question="Which strategy routes are train/validation-testable across the sector shortlist?",
                required_evidence=["market.equity_eod", "stocks.candidates"],
                tool_calls=[
                    ToolCall(
                        "strategy.build",
                        args={
                            "sweep": True,
                            "source_branch": "sector_opportunity",
                            "hypothesis": f"Sector shortlist momentum and leadership routes for {sector}",
                            "symbols": symbols,
                            "strategy_families": ["stage2_breakout", "fifty_two_week_high", "vcp_breakout"],
                            "allowed_horizons": [5, 10, 20],
                        },
                        timeout_s=180.0,
                    )
                ],
                success_criteria=[SuccessCriterion(metric="ok", operator="==", value=True)],
            )
        ],
    )


def _shortlist_symbols(state) -> list[str]:
    pack = state.evidence_pack
    if not pack:
        return []
    candidates = pack.sections.get("stocks", {}).get("candidates", [])
    symbols = []
    seen = set()
    for row in candidates:
        symbol = str(row.get("symbol") or "").upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def _sector_from_pack(state) -> str | None:
    pack = state.evidence_pack
    if not pack:
        return None
    section = pack.sections.get("sector_opportunity", {})
    return section.get("requested_sector") or section.get("resolved_sector")
