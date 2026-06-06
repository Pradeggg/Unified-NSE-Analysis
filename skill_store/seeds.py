from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedBrief:
    id: str
    domain: str
    title: str
    description: str
    input_patterns: tuple[str, ...]
    tags: tuple[str, ...]
    evidence_tables: tuple[str, ...]
    output_contract: tuple[str, ...]


def default_seed_briefs() -> list[SeedBrief]:
    return [
        SeedBrief(
            id="market_3m_rotation_swing",
            domain="market_analysis",
            title="3M Market Rotation Swing Assessment",
            description="Analyze broad market regime, sector leadership, stages, and liquid swing candidates.",
            input_patterns=(
                "last 3 months market analysis",
                "find swing candidates from recent sector rotation",
                "market regime and stage 2 leadership over 3 months",
            ),
            tags=("market_regime", "sector_rotation", "stage_analysis", "swing_trading"),
            evidence_tables=(
                "market.index_eod",
                "market.equity_eod",
                "scores.stage_snapshots",
                "scores.stage2_vcp_picks",
            ),
            output_contract=(
                "as_of_date",
                "index_returns",
                "stage_distribution_change",
                "leading_sectors",
                "primary_candidates",
                "risks",
            ),
        ),
        SeedBrief(
            id="vcp_breakouts_with_fundamentals",
            domain="screening",
            title="VCP Breakouts With Fundamentals",
            description="Find new-high, VCP, and breakout stocks with strong fundamentals and liquidity.",
            input_patterns=(
                "stocks creating new highs or VCP or breakouts with good fundamentals",
                "VCP breakout stocks for TradingView",
                "quality breakouts with strong fundamentals",
            ),
            tags=("vcp", "breakout", "new_high", "fundamentals", "tradingview"),
            evidence_tables=(
                "market.equity_eod",
                "scores.stage_snapshots",
                "scores.stage2_vcp_picks",
            ),
            output_contract=(
                "filters",
                "candidates",
                "tradingview_symbols",
                "evidence",
                "risks",
            ),
        ),
        SeedBrief(
            id="portfolio_incremental_add_trim",
            domain="portfolio_review",
            title="Portfolio Incremental Add Trim Review",
            description="Review current holdings, exposure, stages, signals, and incremental add/trim actions.",
            input_patterns=(
                "should we add incrementally or reduce exposure",
                "portfolio position sizing by sector and stock",
                "review holdings for add trim decisions",
            ),
            tags=("portfolio", "position_sizing", "sector_exposure", "add_trim"),
            evidence_tables=("scores.stage_snapshots", "portfolio.holdings"),
            output_contract=(
                "portfolio_state",
                "sector_exposure",
                "add_candidates",
                "trim_candidates",
                "risk_flags",
            ),
        ),
        SeedBrief(
            id="report_link_data_validation",
            domain="report_qa",
            title="Enhanced Report Data Validation",
            description="Validate enhanced report run metadata, filtered stock rows, populated data, and source trails.",
            input_patterns=(
                "review report links not working",
                "underlying stock html files do not have data",
                "validate generated report links and missing data",
            ),
            tags=("report_qa", "links", "html", "data_validation"),
            evidence_tables=("report.enhanced_runs", "report.enhanced_filtered_stocks"),
            output_contract=("findings", "broken_links", "missing_data", "remediation", "verification"),
        ),
        SeedBrief(
            id="quarterly_results_quality_review",
            domain="fundamental_analysis",
            title="Quarterly Results Quality Review",
            description="Assess latest quarterly results, revenue and PAT growth, margin movement, filing freshness, and narrative quality.",
            input_patterns=(
                "latest quarterly results analysis",
                "analyze result beat miss and margin trend",
                "which companies had strong quarterly results",
            ),
            tags=("quarterly_results", "earnings", "fundamentals", "results_analysis"),
            evidence_tables=("scores.quarterly_results", "scores.results_analysis", "scores.stage_snapshots"),
            output_contract=("filing_window", "beat_miss_summary", "margin_drivers", "ranked_companies", "risks"),
        ),
        SeedBrief(
            id="company_360_research_report",
            domain="fundamental_analysis",
            title="Company 360 Research Report",
            description="Build a comprehensive company research card with overview, financials, fundamentals, technical context, and narrative evidence.",
            input_patterns=(
                "/research RELIANCE comprehensive report",
                "full research report with fundamentals technical charts narrative",
                "institutional grade 360 research for stock",
            ),
            tags=("research", "company_overview", "fundamentals", "technical", "narrative"),
            evidence_tables=(
                "scores.stage_snapshots",
                "scores.quarterly_results",
                "scores.annual_results",
                "scores.balance_sheet",
                "scores.cash_flow",
                "scores.results_analysis",
                "market.equity_eod",
            ),
            output_contract=("company_snapshot", "financial_trends", "technical_setup", "valuation_gaps", "thesis", "risks"),
        ),
        SeedBrief(
            id="data_freshness_readiness_audit",
            domain="data_quality",
            title="Data Freshness Readiness Audit",
            description="Check whether Agent Adda evidence sources are fresh enough for live, EOD, report, and research workflows.",
            input_patterns=(
                "data freshness readiness thresholds",
                "why is market technical narrative unavailable",
                "check DB loader freshness and missing approved history",
            ),
            tags=("data_quality", "freshness", "readiness", "loader", "breadth"),
            evidence_tables=(
                "market.index_eod",
                "market.equity_eod",
                "scores.stage_snapshots",
                "breadth.market_daily",
                "breadth.ma_pct_above",
                "report.enhanced_runs",
            ),
            output_contract=("freshness_matrix", "missing_sources", "blocking_gaps", "loader_actions", "verification_queries"),
        ),
        SeedBrief(
            id="fii_dii_regime_breadth_review",
            domain="market_analysis",
            title="FII DII Regime Breadth Review",
            description="Combine FII/DII flow trend, market regime, breadth, and index evidence to explain market risk-on or risk-off context.",
            input_patterns=(
                "market regime with FII DII and breadth",
                "is the market risk on based on flows and breadth",
                "explain current market breadth and institutional flows",
            ),
            tags=("fii_dii", "regime", "breadth", "market_regime"),
            evidence_tables=("signals.fii_dii_flows", "signals.regime_history", "breadth.market_daily", "market.index_eod"),
            output_contract=("regime", "flow_context", "breadth_context", "index_confirmation", "risk_flags"),
        ),
        SeedBrief(
            id="corporate_events_results_watchlist",
            domain="event_analysis",
            title="Corporate Events Results Watchlist",
            description="Find upcoming or recent corporate events and results-related watchlist actions with source-trail evidence.",
            input_patterns=(
                "upcoming results and corporate events watchlist",
                "stocks with dividends splits bonus or AGM events",
                "event driven stocks to watch after results",
            ),
            tags=("corporate_events", "quarterly_results", "event_analysis", "watchlist"),
            evidence_tables=("signals.corporate_events", "scores.results_analysis", "scores.stage_snapshots"),
            output_contract=("event_calendar", "symbol_watchlist", "result_context", "action_bucket", "source_trail"),
        ),
        SeedBrief(
            id="insider_bulk_deal_signal_review",
            domain="event_analysis",
            title="Insider Bulk Deal Signal Review",
            description="Review insider alerts, bulk or block deals, and technical confirmation for accumulation or distribution clues.",
            input_patterns=(
                "insider buying and bulk deals with technical confirmation",
                "stocks with bulk deals and positive setup",
                "institutional or insider accumulation watchlist",
            ),
            tags=("insider_alerts", "bulk_deals", "event_analysis", "technical_confirmation"),
            evidence_tables=("signals.insider_alerts", "signals.bulk_block_deals", "scores.stage_snapshots", "market.equity_eod"),
            output_contract=("deal_summary", "insider_context", "technical_confirmation", "ranked_symbols", "risk_notes"),
        ),
        SeedBrief(
            id="signal_outcome_feedback_review",
            domain="portfolio_review",
            title="Signal Outcome Feedback Review",
            description="Evaluate prior signals, targets, stops, outcomes, and lessons for improving routes and skill selection.",
            input_patterns=(
                "review prior signals hit target or stop",
                "which recommendations worked and failed",
                "learn from signal outcomes and add to skill store",
            ),
            tags=("signal_log", "learning", "outcome_tracking", "targets", "stop_loss"),
            evidence_tables=("signals.signal_log", "scores.stage_snapshots", "market.equity_eod"),
            output_contract=("outcome_summary", "winner_patterns", "failure_patterns", "route_improvements", "next_checks"),
        ),
        SeedBrief(
            id="portfolio_lab_paper_trading_review",
            domain="portfolio_review",
            title="Portfolio Lab Paper Trading Review",
            description="Review paper trading strategies separately from real holdings, including entries, exits, stops, targets, and exposure.",
            input_patterns=(
                "paper trading portfolio report separate tab",
                "portfolio lab strategy entries exits stop loss targets",
                "review strategy lab without mixing my portfolio",
            ),
            tags=("portfolio", "paper_trading", "strategy_lab", "entry_exit", "stop_loss"),
            evidence_tables=("portfolio.holdings", "signals.signal_log", "scores.stage_snapshots", "market.equity_eod"),
            output_contract=("strategy_state", "open_trades", "entry_exit_rules", "exposure", "exceptions"),
        ),
        SeedBrief(
            id="sector_breadth_rotation_watchlist",
            domain="screening",
            title="Sector Breadth Rotation Watchlist",
            description="Create a sector-relative watchlist using sector breadth, stage migration, RS, and price momentum.",
            input_patterns=(
                "sector rotation watchlist with breadth",
                "which sectors are improving and stocks to add to TradingView",
                "rank sectors by breadth and stage 2 participation",
            ),
            tags=("sector_rotation", "breadth", "stage_analysis", "tradingview", "watchlist"),
            evidence_tables=("breadth.sector_daily", "breadth.ma_pct_above", "scores.stage_snapshots", "market.equity_eod"),
            output_contract=("sector_ranks", "improving_sectors", "candidate_symbols", "tradingview_symbols", "evidence"),
        ),
        SeedBrief(
            id="agent_route_failure_diagnostics",
            domain="data_quality",
            title="Agent Route Failure Diagnostics",
            description="Diagnose Agent Adda route failures, missing tools, wrong symbol resolution, and fallback loops from available evidence.",
            input_patterns=(
                "agent adda going off rails between steps",
                "required tool validation failed missing tool",
                "symbol resolution loop and route diagnostics",
            ),
            tags=("route_diagnostics", "tool_validation", "symbol_resolution", "data_quality"),
            evidence_tables=("report.enhanced_runs", "report.enhanced_filtered_stocks", "scores.stage_snapshots"),
            output_contract=("failure_mode", "source_trail", "route_fix", "tool_gap", "regression_tests"),
        ),
    ]


INTENT_VARIATIONS = (
    "quick scan",
    "deep institutional review",
    "daily refresh follow-up",
    "watchlist creation",
    "risk-first review",
    "freshness audit",
    "sector-relative comparison",
    "position-sizing context",
    "source-trail validation",
    "TradingView export",
)

TIMEFRAME_VARIATIONS = (
    "today",
    "latest EOD",
    "last 5 sessions",
    "last 20 sessions",
    "last 3 months",
    "quarter to date",
    "post results",
    "pre market",
    "intraday context",
    "weekly review",
)

STYLE_VARIATIONS = (
    "concise table",
    "narrative plus evidence",
    "ranked candidates",
    "exceptions and gaps first",
    "portfolio-aware output",
    "research-only summary",
    "debug trace",
    "QA checklist",
    "action watchlist",
    "comparison matrix",
)


def expanded_seed_briefs(target_count: int) -> list[SeedBrief]:
    if target_count <= 0:
        return []
    base = default_seed_briefs()
    expanded: list[SeedBrief] = []
    for index in range(target_count):
        seed = base[index % len(base)]
        intent = INTENT_VARIATIONS[index % len(INTENT_VARIATIONS)]
        timeframe = TIMEFRAME_VARIATIONS[(index // len(INTENT_VARIATIONS)) % len(TIMEFRAME_VARIATIONS)]
        style = STYLE_VARIATIONS[(index // (len(INTENT_VARIATIONS) * len(TIMEFRAME_VARIATIONS))) % len(STYLE_VARIATIONS)]
        variant_no = index + 1
        expanded.append(
            SeedBrief(
                id=f"{seed.id}_{variant_no:04d}",
                domain=seed.domain,
                title=f"{seed.title} Variant {variant_no:04d}",
                description=(
                    f"{seed.description} Variant focus: {intent}; timeframe: {timeframe}; "
                    f"response style: {style}."
                ),
                input_patterns=tuple(
                    dict.fromkeys(
                        (
                            *seed.input_patterns,
                            f"{intent} for {timeframe}: {seed.input_patterns[0]}",
                            f"{seed.input_patterns[-1]} as {style}",
                        )
                    )
                ),
                tags=tuple(dict.fromkeys((*seed.tags, intent.replace(" ", "_"), timeframe.replace(" ", "_"), style.replace(" ", "_")))),
                evidence_tables=seed.evidence_tables,
                output_contract=seed.output_contract,
            )
        )
    return expanded
