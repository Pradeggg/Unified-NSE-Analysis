"""Deterministic chair logic for Research Council plan loops."""

from __future__ import annotations

from datetime import UTC, datetime

from terminal.research_council.schemas import Decision, Plan, PlanStep, SuccessCriterion, ToolCall


class HedgeFundOwnerChair:
    name = "hedge_fund_owner"

    def build_market_council_plan(self, *, run_id: str, iteration: int, objective: str) -> Plan:
        return Plan(
            plan_id=f"{run_id}_plan_{iteration}",
            run_id=run_id,
            iteration=iteration,
            central_question=f"Research council evidence plan for: {objective}",
            created_at=datetime.now(UTC),
            steps=[
                PlanStep(
                    step_id="regime",
                    sequence=1,
                    question="Is the current market regime supportive for fresh long research?",
                    tool_calls=[
                        ToolCall("regime.detect"),
                        ToolCall("breadth.summarize"),
                        ToolCall("flows.fii_dii_5d"),
                        ToolCall("macro.proxy_signals"),
                    ],
                    success_criteria=[SuccessCriterion(metric="ok", operator="exists")],
                ),
                PlanStep(
                    step_id="sector_leadership",
                    sequence=2,
                    question="Which sectors show relative strength and healthy breadth?",
                    dependencies=["regime"],
                    tool_calls=[
                        ToolCall("sector.rs_ranking"),
                        ToolCall("sector.breadth_health"),
                        ToolCall("sector.top_stocks"),
                    ],
                    success_criteria=[SuccessCriterion(metric="ok", operator="exists")],
                ),
                PlanStep(
                    step_id="stock_leadership",
                    sequence=3,
                    question="Which stocks are Stage 2 or high relative-strength leaders?",
                    dependencies=["sector_leadership"],
                    tool_calls=[
                        ToolCall("screen.stage2"),
                        ToolCall("screen.high_rs"),
                        ToolCall("screen.momentum_52w"),
                    ],
                    success_criteria=[SuccessCriterion(metric="ok", operator="exists")],
                ),
                PlanStep(
                    step_id="risk_filters",
                    sequence=4,
                    question="Which candidates fail liquidity, extension, or risk filters?",
                    dependencies=["stock_leadership"],
                    tool_calls=[ToolCall("breadth.summarize")],
                    success_criteria=[SuccessCriterion(metric="ok", operator="exists")],
                ),
                PlanStep(
                    step_id="confirmation",
                    sequence=5,
                    question="Which candidates need F&O, result, event, or fundamental confirmation?",
                    dependencies=["stock_leadership"],
                    tool_calls=[
                        ToolCall("fno.buildup"),
                        ToolCall("fund.results_trend"),
                        ToolCall("events.upcoming"),
                        ToolCall("fund.balance_sheet_health"),
                    ],
                    success_criteria=[SuccessCriterion(metric="ok", operator="exists")],
                ),
            ],
        )

    def synthesize_decision(self, state) -> Decision:
        candidates = _candidate_rows(state)
        blocking_critic = _has_blocking_critic(state)
        missing_evidence = list(state.evidence_pack.missing_evidence) if state.evidence_pack else []
        plan_advanced = bool(state.plan_reviews and state.plan_reviews[-1].advance)
        dissent_log = _dissent_log(state)
        quant_sweep = _quant_sweep_summary(state)
        quant_supported = bool(quant_sweep and quant_sweep.get("verdict") == "SUPPORTED")
        sector_confirmation_ok = getattr(state, "mode", None) != "sector_opportunity" or _has_confirmed_sector_candidate(candidates)

        if blocking_critic or state.flags.get("plan_loop_cap_hit"):
            label = "REVIEW_MANUALLY"
        elif not candidates:
            label = "NO_TRADE"
        elif missing_evidence:
            label = "WAIT_FOR_CONFIRMATION"
        elif plan_advanced and (getattr(state, "mode", None) != "sector_opportunity" or (quant_supported and sector_confirmation_ok)):
            label = "RESEARCH_LONG"
        else:
            label = "WATCHLIST"

        confidence = _confidence(
            plan_advanced=plan_advanced,
            blocking_critic=blocking_critic,
            missing_count=len(missing_evidence),
            plan_loop_cap_hit=bool(state.flags.get("plan_loop_cap_hit")),
        )
        return Decision(
            final_label=label,
            confidence=confidence,
            rationale=_rationale(
                label,
                state,
                plan_advanced,
                quant_supported=quant_supported,
                sector_confirmation_ok=sector_confirmation_ok,
            ),
            candidates=candidates,
            dissent_log=dissent_log,
            missing_evidence=missing_evidence,
        )


def _candidate_rows(state) -> list[dict]:
    rows_by_symbol: dict[str, dict] = {}
    quant_sweep = _quant_sweep_summary(state)
    sector_evidence = _sector_candidate_evidence(state)
    for summary in state.branch_summaries:
        for symbol in summary.candidates:
            row = rows_by_symbol.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "supporting_branch": summary.branch,
                    "supporting_branches": [],
                    "supporting_agents": [],
                    "risks": [],
                    "source_refs": [],
                },
            )
            _append_unique(row["supporting_branches"], summary.branch)
            for agent in summary.supporting_agents:
                _append_unique(row["supporting_agents"], agent)
            for risk in summary.risks:
                _append_unique(row["risks"], risk)
            _append_unique(row["source_refs"], summary.summary_id)

    rows = []
    for symbol, row in rows_by_symbol.items():
        if quant_sweep and (not quant_sweep.get("symbols") or symbol in quant_sweep.get("symbols", [])):
            row["quant_sweep"] = _quant_for_symbol(quant_sweep, symbol)
        evidence = sector_evidence.get(symbol, {})
        if evidence:
            row["sector_rank"] = evidence.get("rank")
            row["sector_score"] = evidence.get("score")
        score, components = _research_score(row)
        row["research_score"] = score
        row["score_components"] = components
        rows.append(row)
    rows.sort(key=lambda item: item.get("research_score", 0), reverse=True)
    return rows


def _sector_candidate_evidence(state) -> dict[str, dict]:
    pack = getattr(state, "evidence_pack", None)
    if not pack:
        return {}
    rows = (pack.sections.get("stocks", {}) or {}).get("candidates", []) if isinstance(pack.sections, dict) else []
    return {str(row.get("symbol") or "").upper(): row for row in rows if row.get("symbol")}


def _has_confirmed_sector_candidate(candidates: list[dict]) -> bool:
    for row in candidates:
        branches = set(row.get("supporting_branches") or [])
        agents = set(row.get("supporting_agents") or [])
        non_sector_agents = agents - {"sector_rotation"}
        if len(branches) >= 2 or non_sector_agents:
            return True
    return False


def _research_score(row: dict) -> tuple[float, dict]:
    quant = row.get("quant_sweep") or {}
    symbol_attr = quant.get("symbol_attribution") or {}
    sector_rank = _float_or_none(row.get("sector_rank"))
    sector_score = _float_or_none(row.get("sector_score"))
    validation_return = _float_or_zero(quant.get("validation_return_pct")) if quant.get("verdict") == "SUPPORTED" else 0.0
    symbol_return = _float_or_zero(symbol_attr.get("validation_return_pct"))
    supporting_agents = len(row.get("supporting_agents") or [])
    supporting_branches = len(row.get("supporting_branches") or [])
    risk_count = len(row.get("risks") or [])
    verdict_bonus = {
        "SUPPORTED": 20.0,
        "AMBIGUOUS": 7.5,
        "REFUTED": -10.0,
        "UNTESTABLE": -15.0,
        "NO_SYMBOL_TRADE": 0.0,
        "NEGATIVE_CONTRIBUTION": -10.0,
    }.get(
        quant.get("verdict"),
        0.0,
    )
    sector_rank_bonus = max(0.0, 18.0 - max(0.0, (sector_rank or 99.0) - 1.0) * 3.0)
    sector_score_bonus = ((sector_score or 0.0) / 100.0) * 15.0
    score = (
        25.0
        + sector_rank_bonus
        + sector_score_bonus
        + supporting_agents * 4.0
        + supporting_branches * 3.0
        + verdict_bonus
        + validation_return * 0.8
        + symbol_return * 2.0
        - risk_count * 4.0
    )
    components = {
        "sector_rank": sector_rank,
        "sector_score": sector_score,
        "supporting_agents": supporting_agents,
        "supporting_branches": supporting_branches,
        "quant_route_verdict": quant.get("route_verdict"),
        "quant_verdict": quant.get("verdict"),
        "quant_validation_return": quant.get("validation_return_pct"),
        "quant_symbol_return": symbol_attr.get("validation_return_pct"),
        "risk_count": risk_count,
    }
    return round(score, 2), components


def _quant_sweep_summary(state) -> dict | None:
    for plan_results in (getattr(state, "execution_results", {}) or {}).values():
        result = _mapping_get(plan_results, "coder_quant_shortlist_sweep")
        if not result or _mapping_get(result, "status") != "success":
            continue
        for output in _mapping_get(result, "outputs", []) or []:
            if not isinstance(output, dict) or output.get("ok") is False:
                continue
            best = output.get("best") or {}
            request = best.get("request") or {}
            result_payload = best.get("result") or {}
            metrics = result_payload.get("metrics") or {}
            validation = (metrics.get("splits") or {}).get("validation") or {}
            horizons = request.get("allowed_horizons") or []
            return {
                "verdict": result_payload.get("verdict"),
                "route_verdict": result_payload.get("verdict"),
                "strategy_family": request.get("strategy_family"),
                "horizon_days": horizons[0] if horizons else None,
                "validation_return_pct": validation.get("return_pct"),
                "validation_sharpe": validation.get("sharpe"),
                "validation_trade_count": validation.get("trade_count"),
                "rank_score": best.get("rank_score"),
                "routes_ranked": len(output.get("ranked_options") or []),
                "routes_untestable": len(output.get("untestable") or []),
                "symbols": output.get("symbols") or [],
                "symbol_attribution": best.get("symbol_attribution") or {},
            }
    return None


def _quant_for_symbol(quant_sweep: dict, symbol: str) -> dict:
    row = dict(quant_sweep)
    attribution = quant_sweep.get("symbol_attribution") or {}
    if symbol in attribution:
        row["symbol_attribution"] = attribution[symbol]
    else:
        row.pop("symbol_attribution", None)
    row["route_verdict"] = quant_sweep.get("route_verdict") or quant_sweep.get("verdict")
    row["verdict"] = _candidate_quant_verdict(row["route_verdict"], row.get("symbol_attribution"))
    return row


def _candidate_quant_verdict(route_verdict: str | None, symbol_attribution: dict | None) -> str | None:
    if route_verdict != "SUPPORTED":
        return route_verdict
    if not symbol_attribution:
        return "NO_SYMBOL_TRADE"
    trades = _float_or_zero(symbol_attribution.get("validation_trade_count"))
    return_pct = _float_or_none(symbol_attribution.get("validation_return_pct"))
    if trades <= 0 or return_pct is None:
        return "NO_SYMBOL_TRADE"
    if return_pct < 0:
        return "NEGATIVE_CONTRIBUTION"
    return "SUPPORTED"


def _append_unique(values: list, value) -> None:
    if value and value not in values:
        values.append(value)


def _float_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_zero(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _mapping_get(payload, key, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _has_blocking_critic(state) -> bool:
    for review_group in state.critic_reviews:
        for review in review_group:
            if review.severity_max == "block" or any(finding.severity == "block" for finding in review.findings):
                return True
    return False


def _dissent_log(state) -> list[str]:
    log = []
    for summary in state.branch_summaries:
        for agent in summary.dissenting_agents:
            log.append(f"{agent} dissented on {summary.branch}")
        log.extend(summary.risks)
    return log


def _confidence(
    *,
    plan_advanced: bool,
    blocking_critic: bool,
    missing_count: int,
    plan_loop_cap_hit: bool,
) -> float:
    score = 0.55
    if plan_advanced:
        score += 0.2
    if missing_count:
        score -= min(0.2, missing_count * 0.05)
    if blocking_critic:
        score -= 0.25
    if plan_loop_cap_hit:
        score -= 0.15
    return round(max(0.05, min(0.95, score)), 2)


def _rationale(label: str, state, plan_advanced: bool, *, quant_supported: bool = False, sector_confirmation_ok: bool = True) -> str:
    parts = [f"Final label {label} selected from deterministic council policy."]
    if plan_advanced:
        parts.append("Latest plan review advanced.")
    if _plan_has_degraded_quant_sweep(state):
        parts.append("Quant route sweep was degraded; no trade-ready route should be inferred from this run.")
    if getattr(state, "mode", None) == "sector_opportunity" and not sector_confirmation_ok:
        if quant_supported:
            parts.append("Quant route is supported, but sector-only evidence needs another confirming branch before RESEARCH_LONG.")
        else:
            parts.append("Sector-only evidence needs another confirming branch before RESEARCH_LONG.")
    if state.flags.get("plan_loop_cap_hit"):
        parts.append("Downgraded because plan loop cap was hit.")
    if state.evidence_pack and state.evidence_pack.missing_evidence:
        parts.append("Confirmation is pending because required evidence is missing.")
    return " ".join(parts)


def _plan_has_degraded_quant_sweep(state) -> bool:
    for review in getattr(state, "plan_reviews", []) or []:
        for verdict in getattr(review, "step_verdicts", []) or []:
            if verdict.get("step_id") == "coder_quant_shortlist_sweep" and verdict.get("status") == "degraded":
                return True
    return False


DEFAULT_CHAIR = HedgeFundOwnerChair()
