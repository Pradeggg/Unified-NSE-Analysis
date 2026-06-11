from __future__ import annotations

import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "skill_store_benchmark_queries.yml"


class BenchmarkRepo:
    def __init__(self):
        self.cards = [
            _card(
                "market_3m_rotation_swing_v1",
                "validated",
                "market_analysis",
                "3M Market Rotation Swing",
                [
                    "market_regime",
                    "sector_rotation",
                    "stage_analysis",
                    "swing_trading",
                    "3m",
                    "leadership",
                    "sectors",
                    "leading",
                    "index_returns",
                    "stage_distribution",
                ],
                [
                    "last 3 months market analysis",
                    "find swing candidates from recent sector rotation",
                    "market regime and stage 2 leadership over 3 months",
                    "which sectors are leading over the last 3 months",
                    "broad market regime with sector rotation and swing ideas",
                    "3 month index returns stage distribution and leading sectors",
                    "market leadership stage analysis for swing trades",
                    "recent sector rotation candidates for swing watchlist",
                ],
                ["market.index_eod", "market.equity_eod", "scores.stage_snapshots", "scores.stage2_vcp_picks"],
                ["as_of_date", "index_returns", "stage_distribution_change", "leading_sectors", "ranked_candidates", "risks"],
            ),
            _card(
                "vcp_breakouts_with_fundamentals_v1",
                "validated",
                "screening",
                "VCP Breakouts With Fundamentals",
                [
                    "vcp",
                    "breakout",
                    "new_high",
                    "fundamentals",
                    "fundamental",
                    "tradingview",
                    "quality",
                    "volume",
                    "liquid",
                    "52_week_high",
                    "candidates",
                ],
                [
                    "stocks creating new highs or VCP or breakouts with good fundamentals",
                    "VCP breakout stocks for TradingView",
                    "quality breakouts with strong fundamentals",
                    "new high stocks with volume and fundamental score",
                    "stage 2 VCP setups with good fundamentals",
                    "breakout watchlist with TradingView symbols",
                    "find liquid breakout stocks with quality filters",
                    "VCP candidates making 52 week highs",
                ],
                ["market.equity_eod", "scores.stage_snapshots", "scores.stage2_vcp_picks"],
                ["filters", "candidates", "tradingview_symbols", "evidence", "risks"],
            ),
            _card(
                "portfolio_incremental_add_trim_v1",
                "validated",
                "portfolio_review",
                "Portfolio Incremental Add Trim Review",
                [
                    "portfolio",
                    "position_sizing",
                    "sector_exposure",
                    "add_trim",
                    "holdings",
                    "trim",
                    "trimmed",
                    "incremental",
                    "exposure",
                    "risk_flags",
                    "rebalance",
                ],
                [
                    "should we add incrementally or reduce exposure",
                    "portfolio position sizing by sector and stock",
                    "review holdings for add trim decisions",
                    "current portfolio exposure and incremental additions",
                    "which holdings should be trimmed based on stage and signal",
                    "sector exposure and stock sizing for my portfolio",
                    "portfolio add reduce exposure using current holdings",
                    "rebalance holdings with risk flags and add candidates",
                ],
                ["scores.stage_snapshots", "portfolio.holdings"],
                ["portfolio_state", "sector_exposure", "add_candidates", "trim_candidates", "risk_flags"],
            ),
            _card(
                "company_360_research_report_v1",
                "validated",
                "fundamental_analysis",
                "Company 360 Research Report",
                [
                    "research",
                    "company_overview",
                    "fundamentals",
                    "technical",
                    "narrative",
                    "thesis",
                    "financials",
                    "financial_trends",
                    "valuation_gaps",
                    "risks",
                    "360",
                ],
                [
                    "full research report with fundamentals technical charts narrative",
                    "institutional grade 360 research for stock",
                    "comprehensive company research with fundamentals and technical context",
                    "company overview financial trends technical setup thesis risks",
                    "research report with valuation gaps and financial trends",
                    "build a 360 degree stock research report",
                    "company fundamentals technical narrative and thesis",
                    "deep company report covering overview financials technical risks",
                ],
                [
                    "scores.stage_snapshots",
                    "scores.quarterly_results",
                    "scores.annual_results",
                    "scores.balance_sheet",
                    "scores.cash_flow",
                    "market.equity_eod",
                ],
                ["company_snapshot", "financial_trends", "technical_setup", "valuation_gaps", "thesis", "risks"],
            ),
            _card(
                "report_link_data_validation_v1",
                "validated",
                "report_qa",
                "Enhanced Report Data Validation",
                [
                    "report_qa",
                    "links",
                    "broken_links",
                    "html",
                    "data_validation",
                    "missing_data",
                    "source_trail",
                    "artifacts",
                    "empty_data",
                ],
                [
                    "review report links not working",
                    "underlying stock html files do not have data",
                    "validate generated report links and missing data",
                    "results analysis html links are broken",
                    "enhanced report stock rows missing source trail",
                    "check report artifacts for broken html links",
                    "why do underlying stock pages have empty data",
                    "report qa for generated html missing data",
                ],
                ["report.enhanced_runs", "report.enhanced_filtered_stocks"],
                ["findings", "broken_links", "missing_data", "remediation", "verification"],
            ),
            _card(
                "data_freshness_readiness_audit_v1",
                "validated",
                "data_quality",
                "Data Freshness Readiness Audit",
                [
                    "data_quality",
                    "freshness",
                    "readiness",
                    "loader",
                    "breadth",
                    "approved_history",
                    "postgresql",
                    "missing_sources",
                    "blocking_gaps",
                    "eod",
                ],
                [
                    "data freshness readiness thresholds",
                    "why is market technical narrative unavailable",
                    "check DB loader freshness and missing approved history",
                    "market index history missing from PostgreSQL loader",
                    "freshness matrix for eod live report and research workflows",
                    "readiness audit for missing breadth and market history",
                    "loader actions for stale EOD and missing sources",
                    "blocking data gaps in approved history tables",
                ],
                ["market.index_eod", "market.equity_eod", "scores.stage_snapshots", "breadth.market_daily"],
                ["freshness_matrix", "missing_sources", "blocking_gaps", "loader_actions", "verification_queries"],
            ),
            _card(
                "generated_decoy_v1",
                "generated",
                "screening",
                "Generated Decoy",
                ["vcp", "breakout", "portfolio", "research", "freshness"],
                ["stocks creating new highs", "portfolio position sizing"],
                ["market.equity_eod"],
                ["decoy"],
            ),
            _card(
                "test_failed_decoy_v1",
                "test_failed",
                "market_analysis",
                "Failed Decoy",
                ["market_regime", "sector_rotation", "report_qa"],
                ["market regime and sector rotation"],
                ["market.index_eod"],
                ["decoy"],
            ),
        ]

    def list_runtime_eligible(self, domain=None):
        rows = [row for row in self.cards if row["status"] in {"validated", "production"}]
        if domain:
            rows = [row for row in rows if row["domain"] == domain]
        return rows

    def search_vector_candidates(self, vector, model, *, limit=30, statuses=("validated", "production")):
        return []

    def log_retrieval(self, event):
        return 1


def test_skill_store_benchmark_queries_select_expected_skill_or_abstain():
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(cases) >= 50
    assert {
        "market_analysis",
        "swing_screening",
        "portfolio_review",
        "stock_research",
        "report_qa",
        "data_debugging",
    }.issubset({case["category"] for case in cases})

    repo = BenchmarkRepo()
    failures = []
    correct = 0
    selected_ids = set()
    for case in cases:
        outcome = _evaluate(case["query"], repo)
        selected_ids.add(outcome.get("selected_skill_id"))
        if _matches(case, outcome):
            correct += 1
        else:
            failures.append((case, outcome))

    accuracy = correct / len(cases)
    assert accuracy >= 0.90, f"accuracy={accuracy:.1%}, failures={failures[:10]}"
    assert "generated_decoy_v1" not in selected_ids
    assert "test_failed_decoy_v1" not in selected_ids


def _evaluate(query: str, repo: BenchmarkRepo) -> dict:
    from terminal.skills.retriever import retrieve_skill_candidates
    from terminal.skills.reranker import rerank_skill_candidates
    from terminal.skills.reviewer import review_skill_candidates

    if query.strip().startswith("/"):
        return {"decision": "abstain", "selected_skill_id": None}
    candidates = retrieve_skill_candidates(query, repo=repo, log_event=False, top_n=5)
    if not candidates:
        return {"decision": "abstain", "selected_skill_id": None}
    reranked = rerank_skill_candidates(candidates, abstain_threshold=0.35)
    if reranked.abstain:
        return {"decision": "abstain", "selected_skill_id": None}
    decision = review_skill_candidates(query, reranked)
    return decision.to_dict()


def _matches(case: dict, outcome: dict) -> bool:
    if case.get("expected_skill_id"):
        return outcome.get("decision") == "select" and outcome.get("selected_skill_id") == case["expected_skill_id"]
    if case.get("expected_decision") == "abstain":
        return outcome.get("decision") in {"abstain", "reject", "fallback_to_router", "ask_clarification"}
    return False


def _card(skill_id, status, domain, title, tags, input_patterns, tables, output_contract):
    return {
        "id": skill_id,
        "version": 1,
        "status": status,
        "domain": domain,
        "title": title,
        "tags": tags,
        "input_patterns": input_patterns,
        "metadata": {"intent_score": 0.8},
        "card_payload": {
            "id": skill_id,
            "version": 1,
            "status": status,
            "domain": domain,
            "title": title,
            "description": title,
            "input_patterns": input_patterns,
            "tags": tags,
            "evidence_required": {"tables": tables},
            "available_tables": tables,
            "tool_plan_template": [],
            "sql_templates": [],
            "output_contract": output_contract,
            "validation_rules": ["required_tables_exist", "sql_is_read_only"],
            "synthesis_guidance": "Use validated evidence only.",
            "intent_score": 0.8,
            "runtime_success_rate": 0.8,
        },
    }
